"""MCP server for VASP INCAR tag queries."""

import json
import sys
import argparse
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from vasp_query._common import (
    load_data,
    DATA_DIR,
    TagEntry,
    resolve_tag,
    query_tag,
    hybrid_search,
    TAG_CONFIGS,
    TAG_STATS,
    TAG_COOCCUR,
)

# ── Load data (module-level, no side effects beyond file I/O) ──────────

_INDEX = load_data(DATA_DIR / "tag_index.json", default=[])
_NON_TAG = load_data(DATA_DIR / "non_tag_index.json", default=[])
_STATS = load_data(DATA_DIR / "tag_stats.json", default={})
_FULLWIKI = load_data(DATA_DIR / "wiki_full.json", default={})

if not _INDEX:
    print("[ERROR] tag_index.json not found. Run: python -m vasp_query preprocess",
          file=sys.stderr)


# ── Internal helpers ───────────────────────────────────────────────────

def _find_tag(name: str):
    tag = name.upper()
    for e in _INDEX:
        if e["title"].upper() == tag:
            return e
    fuzzy = [e for e in _INDEX if tag in e["title"]]
    return fuzzy or []


# ── Tool functions (plain callables, usable without MCP server) ────────

def get_tag(name: str) -> str:
    """Look up a specific VASP INCAR tag by name. Returns JSON with description, default value, and related tags."""
    e = _find_tag(name)
    if isinstance(e, list):
        if len(e) == 1:
            return json.dumps(e[0], indent=2, ensure_ascii=False)
        if e:
            return json.dumps({"error": "Multiple matches", "suggestions": [t["title"] for t in e]}, indent=2)
    if e:
        return json.dumps(e, indent=2, ensure_ascii=False)
    return json.dumps({"error": f"Tag '{name}' not found"}, indent=2)


def search_tags(keyword: str, limit: int = 20) -> str:
    """Search INCAR tags, wiki pages (tutorials, how-tos, best practices) and VASP file formats by keyword. Uses hybrid BM25 + semantic search for relevant results."""
    # T1: resolve_tag
    resolved = resolve_tag(keyword, _INDEX, non_tag=_NON_TAG)
    if isinstance(resolved, dict) and resolved.get("_match") == "exact":
        configs = load_data(TAG_CONFIGS)
        stats = load_data(TAG_STATS)
        cooccur = load_data(TAG_COOCCUR)
        result = query_tag(resolved, configs=configs, stats=stats, cooccur=cooccur)
        return json.dumps({"query": keyword, "count": 1, "results": [result]}, indent=2, ensure_ascii=False)

    if isinstance(resolved, dict) and resolved.get("_match") == "file":
        return json.dumps({"query": keyword, "count": 1, "results": [resolved]}, indent=2, ensure_ascii=False)

    # T2: hybrid search
    try:
        hybrid_results = hybrid_search(keyword, top_k=limit)
        if hybrid_results:
            return json.dumps({"query": keyword, "count": len(hybrid_results), "results": hybrid_results},
                              indent=2, ensure_ascii=False)
    except Exception:
        pass

    # T3: legacy keyword fallback
    kw = keyword.lower()
    results = []
    for e in _INDEX:
        score = 0
        if e["title"].lower() == kw:
            score = 100
        elif kw in e["title"].lower():
            score = 50
        if _match_keyword_legacy(kw, e.get("description", "").lower()):
            score = max(score, _score_keyword_legacy(kw, e.get("description", "").lower()))
        if score > 0:
            results.append({
                "type": "tag", "tag": e["title"], "score": score,
                "default": e.get("default", ""), "description": e.get("description", ""),
            })
    for e in _NON_TAG:
        if e["title"].startswith("Category:"):
            continue
        score = 0
        if _match_keyword_legacy(kw, e["title"].lower()):
            score = 80 if e.get("is_file_page") else 40
        if _match_keyword_legacy(kw, e.get("summary", "").lower()):
            score = max(score, 25)
        if score > 0:
            results.append({"type": e["type"], "title": e["title"], "score": score,
                            "summary": e.get("summary", "")})
    results.sort(key=lambda x: -x["score"])
    return json.dumps({"query": keyword, "count": len(results), "results": results[:limit]},
                      indent=2, ensure_ascii=False)


def _match_keyword_legacy(kw: str, text: str) -> bool:
    if kw in text:
        return True
    import re
    words = re.findall(r'[a-z]+', kw.lower())
    if words and len(words) > 1:
        return all(w in text for w in words)
    return False


def _score_keyword_legacy(kw: str, text: str) -> int:
    if kw.lower() == text.lower():
        return 100
    if kw.lower() in text.lower():
        return 50
    import re
    words = re.findall(r'[a-z]+', kw.lower())
    if words and len(words) > 1:
        matched = sum(1 for w in words if w in text.lower())
        if matched == len(words):
            return 70
        return matched * 10
    return 0


def get_tag_stats(name: str | None = None) -> str:
    """Show tag statistics (frequency, common values). If name is omitted, list all tags with counts."""
    if name:
        tag = name.upper()
        if tag in _STATS:
            return json.dumps({tag: _STATS[tag]}, indent=2, ensure_ascii=False)
        matches = [k for k in _STATS if tag in k]
        if matches:
            return json.dumps({matches[0]: _STATS[matches[0]]}, indent=2, ensure_ascii=False)
        return json.dumps({"error": f"Tag '{name}' not found"}, indent=2)
    all_tags = [
        {"tag": k, "count": v["count"], "frequency_pct": v["frequency"]}
        for k, v in _STATS.items()
    ]
    all_tags.sort(key=lambda x: -x["count"])
    return json.dumps(all_tags, indent=2, ensure_ascii=False)


def list_tags() -> str:
    """List all known INCAR tags with count."""
    names = [e["title"] for e in _INDEX]
    return json.dumps({"count": len(names), "tags": names}, indent=2, ensure_ascii=False)


def get_related_tags(name: str) -> str:
    """Show wiki-related tags for a given tag."""
    e = _find_tag(name)
    if isinstance(e, list) and len(e) == 1:
        e = e[0]
    if isinstance(e, dict):
        return json.dumps({
            "tag": e["title"],
            "related_tags": e.get("related", []),
            "url": e.get("url", ""),
        }, indent=2, ensure_ascii=False)
    return json.dumps({"error": f"Tag '{name}' not found"}, indent=2)


def get_fullwiki(title: str) -> str:
    """Get full wiki page content by title. Supports tag names and VASP file names (POSCAR, OUTCAR, etc.)."""
    if title in _FULLWIKI:
        return json.dumps(_FULLWIKI[title], indent=2, ensure_ascii=False)
    matches = [k for k in _FULLWIKI if title.lower() in k.lower()]
    if matches:
        return json.dumps({"hint": f"Found {len(matches)} similar pages", "matches": matches}, indent=2)
    return json.dumps({"error": f"Page '{title}' not found"}, indent=2)


# ── Tool registry ──────────────────────────────────────────────────────

TOOLS = [
    get_tag,
    search_tags,
    get_tag_stats,
    list_tags,
    get_related_tags,
    get_fullwiki,
]


# ── App factory ────────────────────────────────────────────────────────

def create_app(*, transport: str = "http", host: str = "0.0.0.0", port: int = 8932) -> FastMCP:
    """Create and configure a FastMCP instance with all tools registered."""
    if transport == "http":
        mcp = FastMCP("vasp-query", host=host, port=port, stateless_http=True)
    else:
        mcp = FastMCP("vasp-query")

    for fn in TOOLS:
        mcp.tool()(fn)

    return mcp


# ── CLI entry point ────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="VASP INCAR tag query MCP server")
    parser.add_argument("--port", type=int, default=8932, help="HTTP port (default: 8932)")
    parser.add_argument("--host", default="0.0.0.0", help="HTTP host (default: 0.0.0.0)")
    parser.add_argument("--transport", choices=["stdio", "http"], default="http",
                        help="Transport mode")
    args = parser.parse_args()

    app = create_app(transport=args.transport, host=args.host, port=args.port)

    if args.transport == "http":
        app.run(transport="streamable-http")
    else:
        app.run()


if __name__ == "__main__":
    main()
