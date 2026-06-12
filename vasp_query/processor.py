"""Parse raw VASP wiki and incar_data into structured queryable JSON files."""

import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

from vasp_query._common import (
    DATA_VERSION,
    DATA_DIR,
    RAW_DIR,
    SEARCH_INDEX,
    RAW_META,
    FETCH_META,
    WIKI_RAW,
    INCAR_DATA,
    TagEntry,
    NonTagEntry,
    WikiFullEntry,
)

# Section markers that end the description block
_DESCRIPTION_ENDERS = re.compile(
    r"(?:\n|\n)(?:Output|Recommendations|Advice|Mind:\s*|Important:\s*|Tip:\s*|"
    r"Related tags and articles|Examples|References|Retrieved from|"
    r"Learn\s|Step\s+\d|Subcategories|Pages in category)",
    re.IGNORECASE,
)


def _clean_text(raw: str) -> str:
    """Convert escaped \\n to real newlines, then collapse whitespace."""
    text = raw.replace("\\n", "\n")
    text = re.sub(r"\[math\].*?\[/math\]", "", text, flags=re.DOTALL)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _parse_tag_page(item: dict) -> dict | None:
    """Extract structured fields from a single wiki page."""
    title = item.get("title", "")
    content = item.get("content", "")

    if not re.match(r"^[A-Z][A-Z0-9_]*$", title):
        return None

    raw = _clean_text(content)
    lines = [l.strip() for l in raw.split("\n") if l.strip()]

    first_word = lines[0] if lines else ""
    if not first_word or not first_word[0].isupper():
        return None
    has_tag_def = any(line.startswith("= ") or line.startswith("=.") or line == f"{title}=" for line in lines[:10])
    if not has_tag_def:
        return None
    has_marker = any(re.search(r"(?:description|descprition|definition|default)\s*:", l, re.IGNORECASE) for l in lines)
    if not has_marker:
        return None

    value_format = ""
    default_value = ""

    for i, line in enumerate(lines):
        if line.startswith("=") and len(line) > 1 and not line.lower().startswith("default"):
            if value_format:
                continue
            value_format = line[1:].strip()
        if line.startswith("=") and i > 0 and lines[i-1] == title and default_value:
            continue
        if line.lower().startswith("default:") and i + 1 < len(lines):
            if i + 2 < len(lines) and lines[i + 2].startswith("="):
                default_value = lines[i + 2][1:].strip()

    description = ""
    for i, line in enumerate(lines):
        if re.match(r"(?:description|descprition|definition)\s*:", line, re.IGNORECASE):
            rest = line.split(":", 1)[-1].strip()
            if rest:
                description = rest
            for j in range(i + 1, len(lines)):
                ls = lines[j].lower()
                if any(ls.startswith(marker) for marker in
                       ("output", "recommendation", "related", "examples",
                        "references", "retrieved", "learn", "subcategor")):
                    break
                description += " " + lines[j]
            description = description.strip()
            break

    related_tags = []
    for line in lines:
        if line.lower().startswith("related tags and articles"):
            idx = lines.index(line)
            for rl in lines[idx + 1:]:
                rl = rl.strip()
                if rl and re.match(r"^[A-Z][A-Z0-9_]*$", rl) and rl not in related_tags:
                    related_tags.append(rl)
                elif rl.startswith("Examples") or rl.startswith("References") or rl.startswith("Retrieved"):
                    break
            break

    return {
        "title": title,
        "value": value_format,
        "default": default_value,
        "description": description,
        "related": related_tags,
        "url": item.get("url", ""),
    }


def _classify_non_tag_page(title: str) -> str:
    """Classify a non-tag wiki page into a type."""
    t = title.lower()
    if "tutorial" in t:
        return "tutorial"
    if "how to" in t or "how-to" in t:
        return "how_to"
    if "best practices" in t or "best-practices" in t:
        return "best_practices"
    if "faq" in t or "faq" in title:
        return "faq"
    if "how to calculate" in t:
        return "how_to"
    if "how to perform" in t:
        return "how_to"
    if "pseudopotential" in t or "available pseudopotential" in t:
        return "reference"
    return "other"


def _parse_non_tag_page(item: dict) -> dict | None:
    """Extract structured fields from a non-tag wiki page."""
    title = item.get("title", "")
    content = item.get("content", "")

    _KNOWN_FILES = frozenset(("POSCAR", "KPOINTS", "KPOINTS_OPT", "KPOINTS_ELPH",
        "POTCAR", "INCAR", "ICONST", "PENALTYPOT", "GAMMA", "STOPCAR", "TMPCAR",
        "OUTCAR", "OSZICAR", "CHGCAR", "CONTCAR", "DOSCAR", "EIGENVAL", "LOCPOT",
        "PROCAR", "PROCAR_OPT", "WAVECAR", "XDATCAR", "HESSEMAT", "HILLSPOT",
        "PCDAT", "PROJCAR", "PROOUT", "POT", "QPOINTS", "IBZKPT", "UIJKL", "VIJKL",
        "BSEFATBAND", "DYNMATFULL", "ML_HIS", "NMRCURBX", "REPORT",
        "CHG", "ELFCAR", "PARCHG", "WAVEDER", "POSNICS", "WANPROJ",
        "ML_AB", "ML_ABN", "ML_EATOM", "ML_FF", "ML_FFN", "ML_HEAT", "ML_LOGFILE", "ML_REG",
        "MP2", "NICS",
        # Additional file format pages
        "ABCAR", "ABNCAR", "FFCAR", "FFNCAR", "HISCAR", "IRCCAR", "REGCAR", "TAUCAR"))
    if re.match(r"^[A-Z][A-Z0-9_]*$", title) and title not in _KNOWN_FILES:
        return None

    if not content or len(content) < 50:
        return None

    clean = _clean_text(content)
    page_type = _classify_non_tag_page(title)
    summary = clean[:1000].strip()

    return {
        "title": title,
        "type": page_type,
        "summary": summary,
        "url": item.get("url", ""),
        "is_file_page": title in _KNOWN_FILES,
    }


def parse_wiki_to_index() -> list[dict]:
    """Parse vasp_wiki_all_data.json into structured tag_index.json."""
    with open(WIKI_RAW, "r") as f:
        data = json.load(f)

    tags = []
    skipped = 0
    for item in data:
        result = _parse_tag_page(item)
        if result:
            try:
                TagEntry.model_validate(result)
            except Exception as e:
                logger.warning("Tag %s failed validation: %s", result.get("title"), e)
            tags.append(result)
        else:
            skipped += 1

    with open(DATA_DIR / "tag_index.json", "w") as f:
        json.dump({"_version": DATA_VERSION, "data": tags}, f, ensure_ascii=False, indent=2)

    logger.info("Parsed %d INCAR tags, skipped %d pages", len(tags), skipped)
    return tags


def parse_non_tag_to_index() -> list[dict]:
    """Parse non-tag wiki pages (tutorials, how-tos, best practices) into JSON."""
    with open(WIKI_RAW, "r") as f:
        data = json.load(f)

    pages = []
    skipped = 0
    for item in data:
        result = _parse_non_tag_page(item)
        if result:
            try:
                NonTagEntry.model_validate(result)
            except Exception as e:
                logger.warning("Non-tag page %s failed validation: %s", result.get("title"), e)
            pages.append(result)
        else:
            skipped += 1

    seen = set()
    deduped = []
    for p in pages:
        if p["title"] not in seen:
            seen.add(p["title"])
            deduped.append(p)

    with open(DATA_DIR / "non_tag_index.json", "w") as f:
        json.dump({"_version": DATA_VERSION, "data": deduped}, f, ensure_ascii=False, indent=2)

    logger.info("Parsed %d non-tag pages (%d skipped)", len(deduped), skipped)
    return deduped


def make_wiki_full() -> None:
    """Save clean full wiki content for detailed lookups."""
    with open(WIKI_RAW, "r") as f:
        data = json.load(f)

    full = {}
    for item in data:
        title = item.get("title", "")
        if title:
            entry = {
                "content": _clean_text(item.get("content", "")),
                "url": item.get("url", ""),
            }
            try:
                WikiFullEntry.model_validate(entry)
            except Exception as e:
                logger.warning("Wiki page %s failed validation: %s", title, e)
            full[title] = entry

    with open(DATA_DIR / "wiki_full.json", "w") as f:
        json.dump({"_version": DATA_VERSION, "data": full}, f, ensure_ascii=False, indent=2)

    logger.info("Wrote %d wiki pages to wiki_full.json", len(full))


def extract_tag_stats() -> dict:
    """Extract tag frequency and common values from incar_data.json."""
    with open(INCAR_DATA, "r") as f:
        data = json.load(f)

    tag_counts: dict[str, int] = {}
    tag_values: dict[str, dict] = {}

    for config in data:
        incar = config.get("incar", {})
        for key, value in incar.items():
            tag_counts[key] = tag_counts.get(key, 0) + 1
            val_str = json.dumps(value, ensure_ascii=False, default=str)
            if key not in tag_values:
                tag_values[key] = {}
            tag_values[key][val_str] = tag_values[key].get(val_str, 0) + 1

    stats = {}
    for tag in sorted(tag_counts):
        count = tag_counts[tag]
        values = tag_values.get(tag, {})
        top_values = sorted(values.items(), key=lambda x: -x[1])[:5]
        stats[tag] = {
            "count": count,
            "total_configs": len(data),
            "frequency": round(count / len(data) * 100, 1),
            "top_values": [
                {"value": v, "count": c} for v, c in top_values
            ],
        }

    with open(DATA_DIR / "tag_stats.json", "w") as f:
        json.dump({"_version": DATA_VERSION, "data": stats}, f, ensure_ascii=False, indent=2)

    logger.info("Extracted stats for %d tags from %d configs", len(stats), len(data))
    return stats


def extract_tag_configs() -> None:
    """Extract typical context configurations per tag from incar_data.json."""
    from collections import Counter

    with open(INCAR_DATA, "r") as f:
        data = json.load(f)

    tag_contexts: dict[str, list[tuple[str, ...]]] = {}
    for item in data:
        incar = item.get("incar", {})
        for key in incar:
            if key not in tag_contexts:
                tag_contexts[key] = []
            context = tuple(
                f"{k}={v}" for k, v in sorted(incar.items())
                if k in ("ENCUT", "PREC", "ISMEAR", "SIGMA", "ISPIN", "GGA", "IBRION", "NSW", "EDIFF", "LREAL", "ALGO", "LORBIT", "ISIF")
            )
            tag_contexts[key].append(context)

    configs = {}
    for tag, ctx_list in tag_contexts.items():
        top_ctx = Counter(ctx_list).most_common(5)
        configs[tag] = {
            "total": len(ctx_list),
            "common_contexts": [
                {
                    k: v for k, v in (pair.split("=", 1) for pair in ctx)
                } | {"count": count}
                for ctx, count in top_ctx
            ],
        }

    with open(DATA_DIR / "tag_configs.json", "w") as f:
        json.dump({"_version": DATA_VERSION, "data": configs}, f, ensure_ascii=False, indent=2)

    logger.info("Extracted config contexts for %d tags", len(configs))


def extract_tag_cooccur() -> None:
    """Precompute co-occurrence matrix from incar_data.json."""
    from collections import defaultdict

    with open(INCAR_DATA, "r") as f:
        data = json.load(f)

    cooccur: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for item in data:
        incar = item.get("incar", {})
        tags = list(incar.keys())
        for i, a in enumerate(tags):
            for b in tags[i + 1:]:
                cooccur[a][b] = cooccur[a].get(b, 0) + 1
                cooccur[b][a] = cooccur[b].get(a, 0) + 1

    result = {k: dict(v) for k, v in cooccur.items()}

    with open(DATA_DIR / "tag_cooccur.json", "w") as f:
        json.dump({"_version": DATA_VERSION, "data": result}, f, ensure_ascii=False, indent=2)

    logger.info("Extracted co-occurrence for %d tags", len(result))


def generate_missing_tags() -> list[dict]:
    """Generate tag_index entries for tags found in incar_data but missing from wiki."""
    from collections import Counter

    def _unquote(s):
        if s.startswith('"') and s.endswith('"'):
            return json.loads(s)
        return s

    tags_raw = json.load(open(DATA_DIR / "tag_index.json"))
    if isinstance(tags_raw, dict) and "data" in tags_raw:
        existing = tags_raw["data"]
    else:
        existing = tags_raw
    existing_titles = {t["title"] for t in existing}

    with open(INCAR_DATA, "r") as f:
        incar_data = json.load(f)

    tag_counts: dict[str, int] = {}
    tag_values: dict[str, Counter] = {}
    for item in incar_data:
        incar = item.get("incar", {})
        for k, v in incar.items():
            if k in existing_titles:
                continue
            tag_counts[k] = tag_counts.get(k, 0) + 1
            if k not in tag_values:
                tag_values[k] = Counter()
            tag_values[k][json.dumps(v, ensure_ascii=False, default=str)] += 1

    generated = []
    OVERRIDE = {"ENMAX", "ENMIN", "EXX"}
    for tag in OVERRIDE:
        if tag in existing_titles:
            continue
        tc = tag_counts.get(tag, 0)
        tv = tag_values.get(tag, Counter())
        topv = tv.most_common(3)
        top_str = ", ".join(f"{_unquote(v)} ({c}x)" for v, c in topv) if topv else "(not in dataset)"
        generated.append({
            "title": tag,
            "value": " | ".join(_unquote(v) for v, _ in topv) if topv else "",
            "default": "",
            "description": f"{tag} is a VASP input parameter. Appears in {tc} configurations. Common values: {top_str}.",
            "related": [], "url": "", "auto_generated": True,
        })

    MIN_FREQ = 50
    for tag, count in sorted(tag_counts.items(), key=lambda x: -x[1]):
        if count < MIN_FREQ:
            continue
        topv = tag_values[tag].most_common(3)
        top_str = ", ".join(f"{_unquote(v)} ({c}x)" for v, c in topv)
        generated.append({
            "title": tag,
            "value": " | ".join(_unquote(v) for v, _ in topv),
            "default": "",
            "description": (
                f"{tag} is a VASP input parameter. "
                f"Appears in {count} of {len(incar_data)} real INCAR configurations "
                f"({round(count / len(incar_data) * 100, 1)}%). "
                f"Common values: {top_str}."
            ),
            "related": [], "url": "", "auto_generated": True,
        })

    if generated:
        existing.extend(generated)
        with open(DATA_DIR / "tag_index.json", "w") as f:
            json.dump({"_version": DATA_VERSION, "data": existing}, f, ensure_ascii=False, indent=2)
        logger.info("Generated %d missing tag entries (e.g. %s)", len(generated), generated[0]["title"])

    return generated


def build_search_indexes() -> None:
    """Build tantivy BM25 index + sentence-transformers embeddings for search."""
    import numpy as np
    from tantivy import Index, SchemaBuilder, Document

    # Load co-occurrence data for text enrichment
    import json as _json
    cooccur_path = DATA_DIR / "tag_cooccur.json"
    if cooccur_path.exists():
        cooccur_raw = _json.load(open(cooccur_path))
        if isinstance(cooccur_raw, dict) and "data" in cooccur_raw:
            cooccur_data = cooccur_raw["data"]
        else:
            cooccur_data = {}
    else:
        cooccur_data = {}

    tags = json.load(open(DATA_DIR / "tag_index.json"))
    if isinstance(tags, dict) and "data" in tags:
        tags = tags["data"]
    non_tags = json.load(open(DATA_DIR / "non_tag_index.json"))
    if isinstance(non_tags, dict) and "data" in non_tags:
        non_tags = non_tags["data"]

    docs = []
    for t in tags:
        title = t['title']
        text = f"{title} {t.get('description', '')} {t.get('default', '')} {t.get('value', '')}"
        # Enrich with top co-occurring tags (from incar_data) for semantic bridging
        if cooccur_data and title in cooccur_data:
            top_cooc = sorted(cooccur_data[title].items(), key=lambda x: -x[1])[:5]
            names = [c[0] for c in top_cooc]
            text += " " + " ".join(names)
        docs.append({
            "id": f"tag:{title}", "title": title,
            "text": text, "type": "tag",
        })
    for n in non_tags:
        docs.append({
            "id": f"page:{n['title']}", "title": n["title"],
            "text": f"{n['title']} {n.get('summary', '')}",
            "type": n.get("type", "other"),
        })

    schema = (SchemaBuilder()
              .add_text_field("id", stored=True).add_text_field("title", stored=True)
              .add_text_field("text", stored=False).add_text_field("type", stored=True).build())
    import shutil
    if SEARCH_INDEX.exists():
        shutil.rmtree(SEARCH_INDEX)
    SEARCH_INDEX.mkdir(parents=True, exist_ok=True)
    index = Index(schema, path=str(SEARCH_INDEX))
    writer = index.writer()
    for d in docs:
        doc = Document()
        doc.add_text("id", d["id"]); doc.add_text("title", d["title"])
        doc.add_text("text", d["text"]); doc.add_text("type", d["type"])
        writer.add_document(doc)
    writer.commit()
    logger.info("Built tantivy index with %d docs at %s", len(docs), SEARCH_INDEX)

    try:
        import os as _os
        _os.environ["USE_TF"] = "0"
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer("BAAI/bge-small-en-v1.5")
        texts = [d["text"] for d in docs]
        embeddings = model.encode(texts, show_progress_bar=True)
        np.save(str(DATA_DIR / "doc_vectors.npy"), embeddings)
        meta = [{"id": d["id"], "title": d["title"], "type": d["type"]} for d in docs]
        with open(DATA_DIR / "doc_meta.json", "w") as f:
            json.dump(meta, f, ensure_ascii=False)
        logger.info("Generated embeddings: %d docs x %d dim", len(embeddings), embeddings.shape[1])

        # Also generate tag-only embeddings for focused semantic matching.
        # Issue #6: slice the existing embeddings matrix instead of re-encoding.
        # The tag docs are a strict subset of `docs`, so the tag vectors are
        # already rows of `embeddings` — no second model.encode() pass needed.
        tag_docs = [(i, d) for i, d in enumerate(docs) if d["type"] == "tag"]
        if tag_docs:
            tag_indices, tag_entries = zip(*tag_docs)
            tag_embeddings = embeddings[list(tag_indices)]
            np.save(str(DATA_DIR / "tag_vectors.npy"), tag_embeddings)
            tag_meta = [{"idx": i, "id": d["id"], "title": d["title"]} for i, d in tag_docs]
            with open(DATA_DIR / "tag_meta.json", "w") as f:
                json.dump(tag_meta, f, ensure_ascii=False)
            logger.info("Generated tag-only embeddings: %d tags x %d dim (sliced from doc_embeddings, no re-encoding)",
                        len(tag_embeddings), tag_embeddings.shape[1])
    except Exception as e:
        logger.warning("sentence-transformers embedding failed (skip): %s", e)


def preprocess(check_only: bool = False) -> bool:
    """Run all preprocessing steps. If *check_only*, detect staleness and return True."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if check_only:
        return check_stale(verbose=True)

    _record_meta()
    parse_wiki_to_index()
    parse_non_tag_to_index()
    make_wiki_full()
    extract_tag_stats()
    extract_tag_configs()
    extract_tag_cooccur()
    generate_missing_tags()
    build_search_indexes()
    logger.info("Preprocessing complete.")
    return False


def _record_meta() -> None:
    """Record preprocess timestamp and fetch status."""
    from datetime import datetime, timezone
    meta = {"last_preprocess": datetime.now(timezone.utc).isoformat()}

    fetch_meta = json.load(open(FETCH_META)) if FETCH_META.exists() else {}
    if fetch_meta:
        meta["last_fetch"] = fetch_meta.get("last_fetch", "unknown")
        meta["wiki_page_count"] = fetch_meta.get("page_count", 0)

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    with open(RAW_META, "w") as f:
        json.dump({"_version": DATA_VERSION, "data": meta}, f, indent=2)


def check_stale(verbose: bool = False) -> bool:
    """Check if fetched data hasn't been preprocessed, or no fetch exists."""
    raw_meta = json.load(open(RAW_META)) if RAW_META.exists() else {}
    if isinstance(raw_meta, dict) and "data" in raw_meta:
        raw_meta = raw_meta["data"]

    fetch_meta = json.load(open(FETCH_META)) if FETCH_META.exists() else {}

    if not fetch_meta:
        if verbose:
            logger.info("No fetch metadata found. Run: python3 -m vasp_query fetch")
        return True

    if not raw_meta:
        if verbose:
            logger.info("Fetched data not yet preprocessed. Run: python3 -m vasp_query preprocess")
        return True

    fetch_time = fetch_meta.get("last_fetch", "")
    preprocess_time = raw_meta.get("last_preprocess", "")

    if fetch_time > preprocess_time:
        if verbose:
            logger.info("Wiki data fetched at %s, but preprocessed at %s. Run preprocess to update.", fetch_time[:19], preprocess_time[:19])
        return True

    if verbose:
        logger.info("Data up to date (fetched %s, preprocessed %s).", fetch_time[:19], preprocess_time[:19])
    return False
