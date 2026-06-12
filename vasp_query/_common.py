"""Shared utilities, data models, and paths for vasp_query."""

import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel


# ── Data version ───────────────────────────────────────────────────────

DATA_VERSION = "0.2.0"


# ── Pydantic models ────────────────────────────────────────────────────

class TagEntry(BaseModel):
    title: str
    value: str
    default: str
    description: str
    related: list[str]
    url: str


class NonTagEntry(BaseModel):
    title: str
    type: str
    summary: str
    url: str
    is_file_page: bool


class TagStatsDetail(BaseModel):
    value: str
    count: int


class TagStatsEntry(BaseModel):
    count: int
    total_configs: int
    frequency: float
    top_values: list[TagStatsDetail]


class WikiFullEntry(BaseModel):
    content: str
    url: str


# ── Data paths ─────────────────────────────────────────────────────────

_VASP_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(__file__).resolve().parent / "data"
RAW_DIR = _VASP_ROOT / "data" / "raw"

# Generated
TAG_INDEX = DATA_DIR / "tag_index.json"
NON_TAG_INDEX = DATA_DIR / "non_tag_index.json"
TAG_STATS = DATA_DIR / "tag_stats.json"
WIKI_FULL = DATA_DIR / "wiki_full.json"
TAG_CONFIGS = DATA_DIR / "tag_configs.json"
TAG_COOCCUR = DATA_DIR / "tag_cooccur.json"
SEARCH_INDEX = DATA_DIR / "search_index"
TAG_VECTORS = DATA_DIR / "tag_vectors.npy"
TAG_META = DATA_DIR / "tag_meta.json"
DOC_VECTORS = DATA_DIR / "doc_vectors.npy"
DOC_META = DATA_DIR / "doc_meta.json"
# User-editable: domain abbreviations that resolve to canonical tag names.
# Issue #5: was hardcoded as _TERM_MAP in this file; now data-driven so new
# abbreviations can be added without a code change.
ALIASES = DATA_DIR / "aliases.json"
# Written by the preprocessor: list of wiki titles that failed parsing.
# Lets generate_missing_tags auto-discover dropped tags instead of relying
# on a hardcoded OVERRIDE set.
SKIPPED_PAGES = DATA_DIR / "skipped_pages.json"

# Raw inputs
WIKI_RAW = RAW_DIR / "vasp_wiki_all_data.json"
INCAR_DATA = RAW_DIR / "incar_data.json"
RAW_META = DATA_DIR / "raw_meta.json"
FETCH_META = RAW_DIR / "_meta.json"


# ── JSON loader ────────────────────────────────────────────────────────

def load_json(path: Path) -> Any | None:
    """Load a JSON file, returning None if it doesn't exist."""
    if not path.exists():
        return None
    with open(path, "r") as f:
        return json.load(f)


def load_data(path: Path, default: Any = None, model: type[BaseModel] | None = None) -> Any | None:
    """Load a data JSON file, check version compatibility, and strip the version envelope.

    Supports two on-disk formats:
      ``{"_version": "...", "data": <actual content>}``  — wrapped envelope (preferred)
      ``<actual content>``                                — raw (backward-compat)

    If the envelope is present the version is checked against ``DATA_VERSION``
    and a warning is printed when they differ. The envelope is transparently
    stripped so consumers never see ``_version``.

    Returns ``default`` (or ``None``) if the file does not exist.
    """
    raw = load_json(path)
    if raw is None:
        return default

    data = raw
    if isinstance(raw, dict) and "_version" in raw:
        ver = raw.pop("_version")
        if ver != DATA_VERSION:
            import warnings
            warnings.warn(
                f"{path.name} version {ver!r} != expected {DATA_VERSION!r}. "
                "Run: python -m vasp_query preprocess"
            )
        data = raw.get("data") if "data" in raw else raw

    if model is not None:
        if isinstance(data, list):
            return [model.model_validate(item) for item in data]
        return model.model_validate(data)

    return data


# ── Search helpers (legacy) ────────────────────────────────────────────

def match_keyword(kw: str, text: str) -> bool:
    """Match keyword against text using word-level matching."""
    if kw in text:
        return True
    words = re.findall(r'[a-z]+', kw.lower())
    if words and len(words) > 1:
        return all(w in text for w in words)
    return False


def score_keyword(kw: str, text: str) -> int:
    """Score relevance of keyword match."""
    if kw.lower() == text.lower():
        return 100
    if kw.lower() in text.lower():
        return 50
    words = re.findall(r'[a-z]+', kw.lower())
    if words and len(words) > 1:
        matched = sum(1 for w in words if w in text.lower())
        if matched == len(words):
            return 70
        return matched * 10
    return 0


# ── Output helpers ─────────────────────────────────────────────────────

def format_tag_human(entry: dict) -> str:
    """Render a TagEntry as human-readable Markdown."""
    lines = [
        f"## {entry['title']}",
        f"**类型**: `{entry.get('value', '')}`  **默认**: `{entry.get('default', '')}`",
        "",
        entry.get("description", ""),
    ]
    related = entry.get("related", [])
    if related:
        lines.append("")
        lines.append(f"**相关标签**: {', '.join(f'`{r}`' for r in related)}")
    url = entry.get("url", "")
    if url:
        lines.append("")
        lines.append(f"📎 [{url}]({url})")
    return "\n".join(lines)


def format_search_item_human(item: dict) -> str:
    """Render a single search result as Markdown."""
    t = item.get("type", "?")
    score = item.get("score", 0)
    if t == "tag":
        tag = item.get("tag", "?")
        desc = item.get("description", "")
        return f"**`{tag}`** (tag, score={score})\n  {desc[:200]}"
    title = item.get("title", "?")
    summary = item.get("summary", "")
    return f"**{title}** ({t}, score={score})\n  {summary[:200]}"


def format_stats_human(entry: dict, tag: str) -> str:
    """Render a TagStatsEntry as Markdown."""
    d = entry.get(tag, entry)
    lines = [
        f"## {tag}",
        f"**出现次数**: {d.get('count', '?')}  **频率**: {d.get('frequency', '?')}%",
        "",
        "**常用值**:",
    ]
    for tv in d.get("top_values", []):
        lines.append(f"- `{tv['value']}` — {tv['count']} 次")
    return "\n".join(lines)


# ── Tag resolution (Context7-style two-stage query) ──────────────────

import difflib

_DEBUG_LOG: list[str] = []


def debug_log(msg: str) -> None:
    _DEBUG_LOG.append(msg)


def get_debug_log() -> list[str]:
    return _DEBUG_LOG


def clear_debug_log() -> None:
    _DEBUG_LOG.clear()


# Built-in fallback for the alias map. Used when data/aliases.json is missing
# or fails to load. User overrides in data/aliases.json take precedence.
_BUILTIN_ALIASES: dict[str, str] = {
    "soc": "LSORBIT",
    "dft+u": "LDAU",
    "dft": "GGA",
    "gga": "GGA",
    "pbe": "GGA",
    "hse": "HFSCREEN",
    "gw": "ALGO",
    "vdw": "IVDW",
    "bse": "ALGO",
    "phonon": "IBRION",
    "hubbard": "LDAU",
    "hubbard u": "LDAU",
    "molecular dynamics": "IBRION",
}

_ALIASES_CACHE: dict[str, str] | None = None


def load_aliases() -> dict[str, str]:
    """Load the user-editable alias map from data/aliases.json, merged on top
    of the built-in fallback. Cached at module level.

    Returns a dict mapping lowercase alias -> canonical tag name. Adding a
    new alias is a data change, not a code change. The built-in map covers
    the abbreviations that BGE-small can't bridge semantically.
    """
    global _ALIASES_CACHE
    if _ALIASES_CACHE is not None:
        return _ALIASES_CACHE
    user = load_data(ALIASES) or {}
    # User file takes precedence over built-in. Both are merged.
    merged = {**_BUILTIN_ALIASES, **{k.lower().strip(): v for k, v in user.items()}}
    _ALIASES_CACHE = merged
    return merged


def resolve_tag(input: str, index: list[dict], non_tag: list[dict] | None = None) -> dict | list[dict] | None:
    """Resolve user input to a tag. Stages: exact -> term map -> file page -> fuzzy -> substring.

    Returns a single tag dict (exact/file page match), a list (fuzzy/substring),
    or None (not found).
    """
    inp = input.upper().strip()
    debug_log(f"resolve_tag(input={input!r}) -> normalized={inp}")

    for t in index:
        if t["title"] == inp:
            debug_log(f"  exact: {t['title']}")
            return {**t, "_match": "exact"}

    # 2. Domain abbreviation map (data-driven: see load_aliases)
    key = input.lower().strip()
    aliases = load_aliases()
    if key in aliases:
        target = aliases[key].upper()
        debug_log(f"  term_map: '{key}' -> '{target}'")
        for t in index:
            if t["title"] == target:
                return {**t, "_match": "term_map"}

    if non_tag:
        for n in non_tag:
            if n.get("is_file_page") and n["title"].upper() == inp:
                debug_log(f"  file page: {n['title']}")
                return {**n, "_match": "file", "_type": "file_page"}

    titles = [t["title"] for t in index]
    fuzzy = difflib.get_close_matches(inp, titles, n=3, cutoff=0.5)
    if fuzzy:
        debug_log(f"  fuzzy: {fuzzy}")
        return [t for t in index if t["title"] in fuzzy]

    submatch = [t for t in index if inp in t["title"]]
    if submatch:
        debug_log(f"  substring: {len(submatch)} matches")
        return submatch

    debug_log("  no match")
    return None


def query_tag(resolved: dict, configs: dict | None = None,
              stats: dict | None = None, cooccur: dict | None = None) -> dict:
    """Build structured product response for a resolved tag."""
    result = {
        "info": {
            "title": resolved["title"],
            "value": resolved.get("value", ""),
            "default": resolved.get("default", ""),
            "description": resolved.get("description", ""),
            "url": resolved.get("url", ""),
            "related_tags": resolved.get("related", []),
        },
        "confidence": {
            "source": "vasp.at/wiki - official",
            "description_length": len(resolved.get("description", "")),
            "has_samples": False,
        },
    }
    title = resolved["title"]
    if configs and title in configs:
        result["configs"] = configs[title]
        result["confidence"]["has_samples"] = True
    if stats and title in stats:
        result["stats"] = stats[title]
    if cooccur and title in cooccur:
        related = sorted(cooccur[title].items(), key=lambda x: -x[1])[:5]
        result.setdefault("related", {})["cooccur"] = [
            {"tag": t, "cooccur_count": c} for t, c in related
        ]
    return result


# ── Hybrid search (tantivy BM25 + sentence-transformers semantic) ────

_INDEX_CACHE = None
_SEARCHER_CACHE = None
_MODEL_CACHE = None


def hybrid_search(keyword: str, top_k: int = 10) -> list[dict]:
    """Run BM25 + semantic search, return RRF-fused results."""
    global _INDEX_CACHE, _SEARCHER_CACHE, _MODEL_CACHE

    import numpy as np

    clear_debug_log()
    debug_log(f"hybrid_search(keyword={keyword!r}, top_k={top_k})")

    try:
        if _SEARCHER_CACHE is None:
            from tantivy import Index
            _INDEX_CACHE = Index.open(str(SEARCH_INDEX))
            _SEARCHER_CACHE = _INDEX_CACHE.searcher()
        searcher = _SEARCHER_CACHE
        index_obj = _INDEX_CACHE
        debug_log(f"  tantivy index loaded")
    except Exception as e:
        searcher = None
        index_obj = None
        debug_log(f"  tantivy unavailable: {e}")

    vectors = load_data_raw(DOC_VECTORS) if DOC_VECTORS.exists() else None
    debug_log(f"  doc_vectors: {'loaded' if vectors is not None else 'not found'}")

    meta = load_data(DOC_META) or []
    debug_log(f"  doc_meta: {len(meta)} entries")

    if searcher is None and vectors is None:
        debug_log("  no search backend -> empty")
        return []

    kw = keyword.lower()
    results: dict[str, float] = {}

    if searcher is not None and index_obj is not None:
        try:
            query = index_obj.parse_query(kw, ["text"])
            search_result = searcher.search(query, top_k * 3)
            bm25_hits = search_result.hits
            debug_log(f"  BM25: {len(bm25_hits)} hits from tantivy")
            for rank, (bm25_score, doc_addr) in enumerate(bm25_hits[:5]):
                doc = searcher.doc(doc_addr)
                doc_id = doc["id"][0]
                rrf = 1.0 / (60 + rank)
                results[doc_id] = results.get(doc_id, 0) + rrf
                debug_log(f"    BM25 #{rank}: {doc_id} bm25={bm25_score:.2f} rrf={rrf:.4f}")
        except Exception as e:
            debug_log(f"  BM25 error: {e}")

    if vectors is not None:
        try:
            if _MODEL_CACHE is None:
                import os as _os
                _os.environ["USE_TF"] = "0"
                from sentence_transformers import SentenceTransformer
                _MODEL_CACHE = SentenceTransformer("BAAI/bge-small-en-v1.5")
            model = _MODEL_CACHE
            query_vec = model.encode([kw], show_progress_bar=False)

            # Signal A: full semantic (all docs)
            scores = np.dot(vectors, query_vec.T).flatten()
            top_idx = np.argsort(-scores)[:top_k * 3]
            debug_log(f"  Full semantic: top {len(top_idx)} from {len(scores)}")
            for rank, idx in enumerate(top_idx[:5]):
                doc_id = meta[idx]["id"]
                rrf = 1.0 / (60 + rank)
                results[doc_id] = results.get(doc_id, 0) + rrf
                debug_log(f"    FULL #{rank}: {doc_id} cos={scores[idx]:.4f} rrf={rrf:.4f}")

            # Signal B: tag-only semantic (boosted weight)
            # Sibling of Signal A loop — runs once per query, not per Signal A iteration.
            # (Fix for issue #1: previously mis-indented inside the Signal A for-loop.)
            tag_vectors = load_data_raw(TAG_VECTORS) if TAG_VECTORS.exists() else None
            tag_meta = load_data(TAG_META) or []
            if tag_vectors is not None and tag_meta:
                tag_scores = np.dot(tag_vectors, query_vec.T).flatten()
                tag_top = np.argsort(-tag_scores)[:top_k * 2]
                debug_log(f"  Tag-only semantic: top {len(tag_top)} from {len(tag_scores)}")
                for rank, idx in enumerate(tag_top[:5]):
                    entry = tag_meta[idx]
                    doc_id = entry["id"]
                    rrf = 1.5 / (60 + rank)
                    results[doc_id] = results.get(doc_id, 0) + rrf
                    debug_log(f"    TAG #{rank}: {doc_id} cos={tag_scores[idx]:.4f} rrf={rrf:.4f}")
        except Exception as e:
            debug_log(f"  Semantic error: {e}")

    ranked = sorted(results.items(), key=lambda x: -x[1])[:top_k]
    output = []
    for doc_id, score in ranked:
        for m in meta:
            if m["id"] == doc_id:
                item = {"id": doc_id, "score": round(score, 3)}
                if doc_id.startswith("tag:"):
                    item["type"] = "tag"
                    item["tag"] = doc_id[4:]
                else:
                    item["type"] = m.get("type", "page")
                    item["title"] = m.get("title", doc_id)
                output.append(item)
                break

    debug_log(f"  -> {len(output)} final results")
    return output


def load_data_raw(path: Path) -> Any | None:
    """Load a .npy file."""
    try:
        import numpy as np
        return np.load(str(path))
    except Exception:
        return None
