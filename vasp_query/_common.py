"""Shared utilities, data models, and paths for vasp_query."""

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from dft_utils import DATA_VERSION, debug_log, get_debug_log, clear_debug_log
from dft_utils.version import load_data, load_json as _load_json
from dft_utils.search import match_keyword, score_keyword, make_fts5_query
from dft_utils.embedding import EmbeddingDimError

# Re-export for downstream (vasp_query/query.py etc.)
load_json = _load_json

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
SEARCH_DB = DATA_DIR / "search.db"
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


def _search_fts5(keyword: str, top_k: int) -> list[dict]:
    """Search via SQLite FTS5 backend. Returns empty list if unavailable."""
    import sqlite3
    try:
        if not SEARCH_DB.exists():
            debug_log("  FTS5 db not found")
            return []
        conn = sqlite3.connect(str(SEARCH_DB))
        conn.row_factory = sqlite3.Row
        fts_query = make_fts5_query(keyword)
        rows = conn.execute("""
            SELECT id, title, type, rank
            FROM search_index
            WHERE search_index MATCH ?
            ORDER BY rank
            LIMIT ?
        """, (fts_query, top_k * 3)).fetchall()
        conn.close()
        if not rows:
            debug_log("  FTS5: no results")
            return []
        debug_log(f"  FTS5: {len(rows)} hits")
        results = []
        for rank, r in enumerate(rows):
            doc_id = r["id"]
            rrf = 1.0 / (60 + rank)
            results.append({"id": doc_id, "rrf": rrf, "bm25_score": -r["rank"]})
            debug_log(f"    FTS5 #{rank}: {doc_id} rrf={rrf:.4f}")
        return results
    except Exception as e:
        debug_log(f"  FTS5 error: {e}")
        return []


def _tag_extra(doc_id: str) -> dict:
    """Record shape for an FTS5/BM25 hit id (``tag:ENCUT`` or page id)."""
    if isinstance(doc_id, str) and doc_id.startswith("tag:"):
        return {"type": "tag", "tag": doc_id[4:]}
    return {"type": "page", "tag": doc_id if isinstance(doc_id, str) else ""}


class _Fts5Backend:
    """FTS5 BM25 signal over the prebuilt SQLite ``search_index``."""

    name = "bm25"

    def search(self, query: str, top_k: int) -> list:
        from dft_utils.search import SearchHit

        hits = _search_fts5(query, top_k * 3)
        return [
            SearchHit(
                id=r["id"],
                title=r["id"],
                score=0.0,
                source=self.name,
                extra=_tag_extra(r["id"]),
            )
            for r in hits
        ]


class _SemanticBackend:
    """Full-corpus semantic signal over doc vectors."""

    name = "semantic"

    def __init__(self, kw_vectors, kw_meta):
        self.vectors = kw_vectors
        self.meta = kw_meta

    def search(self, query: str, top_k: int) -> list:
        import numpy as np
        from dft_utils.embedding import EmbeddingDimError, cosine_row_scores, embed
        from dft_utils.search import SearchHit

        try:
            query_vec = np.asarray(embed(query), dtype=np.float32)
        except EmbeddingDimError:
            raise
        except Exception:
            return []  # embedding backend unavailable -> degrade to other signals
        scores = cosine_row_scores(query_vec, self.vectors)
        top_idx = np.argsort(-scores)[: top_k * 3]
        out = []
        for idx in top_idx:
            m = self.meta[idx]
            doc_id = m["id"]
            out.append(
                SearchHit(
                    id=doc_id,
                    title=m.get("title", doc_id),
                    score=float(scores[idx]),
                    source=self.name,
                    extra=_tag_extra(doc_id),
                )
            )
        return out


class _TagSemanticBackend:
    """Tag-only semantic signal (boosted), over the sliced tag vectors."""

    name = "tag"

    def __init__(self, tag_vectors, tag_meta):
        self.vectors = tag_vectors
        self.meta = tag_meta

    def search(self, query: str, top_k: int) -> list:
        import numpy as np
        from dft_utils.embedding import EmbeddingDimError, cosine_row_scores, embed
        from dft_utils.search import SearchHit

        try:
            query_vec = np.asarray(embed(query), dtype=np.float32)
        except EmbeddingDimError:
            raise
        except Exception:
            return []
        scores = cosine_row_scores(query_vec, self.vectors)
        top_idx = np.argsort(-scores)[: top_k * 3]
        out = []
        for idx in top_idx:
            doc_id = self.meta[idx]["id"]
            out.append(
                SearchHit(
                    id=doc_id,
                    title=doc_id,
                    score=float(scores[idx]),
                    source=self.name,
                    extra=_tag_extra(doc_id),
                )
            )
        return out


def hybrid_search(keyword: str, top_k: int = 10) -> list[dict]:
    """Run FTS5/BM25 + semantic/tag search, fused via the shared hybrid
    orchestrator.  Backends degrade independently; a dimension mismatch is
    surfaced as a structured error instead of a silent wrong ranking.
    """
    import numpy as np
    from dft_utils.search import SearchBackend, SearchHit, hybrid_search as _shared

    clear_debug_log()
    debug_log(f"hybrid_search(keyword={keyword!r}, top_k={top_k})")

    # ── Build per-signal backends ─────────────────────────────────────
    backends: list[SearchBackend] = []
    if SEARCH_DB.exists():
        backends.append(_Fts5Backend())

    vectors = load_data_raw(DOC_VECTORS) if DOC_VECTORS.exists() else None
    meta = load_data(DOC_META) or []
    if vectors is not None and meta:
        backends.append(_SemanticBackend(kw_vectors=vectors, kw_meta=meta))
        tag_vectors = load_data_raw(TAG_VECTORS) if TAG_VECTORS.exists() else None
        tag_meta = load_data(TAG_META) or []
        if tag_vectors is not None and tag_meta:
            backends.append(_TagSemanticBackend(tag_vectors, tag_meta))

    if not backends:
        debug_log("  no search backend -> empty")
        return []

    try:
        hits = _shared(
            keyword,
            backends,
            top_k=top_k,
            weights={"bm25": 1.5, "semantic": 0.75, "tag": 1.0},
        )
    except EmbeddingDimError as exc:
        debug_log(f"  embedding dimension mismatch: {exc}")
        raise

    # Enrich non-tag hits with their real page title/type (mirrors the
    # pre-fusion enrichment the original fused directly did).
    meta_by_id = {m["id"]: m for m in (meta if isinstance(meta, list) else [])}
    output = []
    for h in hits:
        if h.extra.get("type") == "tag":
            output.append(_hit_to_record(h))
            continue
        m = meta_by_id.get(h.id)
        if m is not None:
            record = _hit_to_record(h)
            record["type"] = m.get("type", record.get("type", "page"))
            record["title"] = m.get("title", record.get("title", h.id))
            output.append(record)
        else:
            output.append(_hit_to_record(h))
    debug_log(f"  -> {len(output)} final results")
    return output


def _hit_to_record(hit) -> dict:
    """Convert a shared SearchHit back to vasp_query's record shape,
    now also carrying ``source`` (previously dropped)."""
    record: dict = {"id": hit.id, "score": hit.score, "source": hit.source}
    if hit.extra.get("type"):
        record["type"] = hit.extra["type"]
    if hit.extra.get("tag"):
        record["tag"] = hit.extra["tag"]
    record["title"] = hit.extra.get("tag", hit.title)
    return record


def load_data_raw(path: Path) -> Any | None:
    """Load a .npy file."""
    try:
        import numpy as np
        return np.load(str(path))
    except Exception:
        return None

def load_tag_index() -> list[dict] | None:
    """Load tag_index.json, returning a list of tag dicts.

    Handles both dict format (keyed by title) and legacy list format.
    """
    raw = load_data(TAG_INDEX)
    if raw is None:
        return None
    if isinstance(raw, dict):
        return list(raw.values())
    if isinstance(raw, list):
        return raw
    return None
