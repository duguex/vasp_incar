"""MCP server for VASP INCAR tag queries."""

import json
import re
from pathlib import Path
from mcp.server.fastmcp import FastMCP

BASE = Path(__file__).resolve().parent / "data"
_load_json = lambda p: json.load(open(p, "r")) if p.exists() else None

_INDEX = _load_json(BASE / "tag_index.json")
_NON_TAG = _load_json(BASE / "non_tag_index.json")
_STATS = _load_json(BASE / "tag_stats.json")
_FULLWIKI = _load_json(BASE / "wiki_full.json")

if _INDEX is None:
    print("[ERROR] tag_index.json not found. Run: python -m vasp_query preprocess")
    _INDEX = []
if _NON_TAG is None:
    _NON_TAG = []
if _STATS is None:
    _STATS = {}
if _FULLWIKI is None:
    _FULLWIKI = {}

mcp = FastMCP("vasp-query")


def _find_tag(name: str):
    tag = name.upper()
    for e in _INDEX:
        if e["title"].upper() == tag:
            return e
    # fuzzy
    return [e for e in _INDEX if tag in e["title"]] or []


@mcp.tool()
def get_tag(name: str) -> str:
    """Look up a specific VASP INCAR tag by name. Returns JSON with description, default value, and related tags."""
    e = _find_tag(name)
    if isinstance(e, list):
        if len(e) == 1:
            return json.dumps(e[0], indent=2, ensure_ascii=False)
        return json.dumps({"error": f"Multiple matches", "suggestions": [t["title"] for t in e]}, indent=2)
    if e:
        return json.dumps(e, indent=2, ensure_ascii=False)
    return json.dumps({"error": f"Tag '{name}' not found"}, indent=2)


def _match_keyword(kw: str, text: str) -> bool:
    """Match keyword against text using word-level matching (handles hyphens, spaces)."""
    if kw in text:
        return True
    # Word-level: split keyword into words, all must appear in text
    words = re.findall(r'[a-z]+', kw.lower())
    if words and len(words) > 1:
        return all(w in text for w in words)
    return False


def _score_keyword(kw: str, text: str) -> int:
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


@mcp.tool()
def search_tags(keyword: str, limit: int = 20) -> str:
    """Search INCAR tags, wiki pages (tutorials, how-tos, best practices) and VASP file formats (POSCAR, OUTCAR, etc.) by keyword. Returns ranked results with file pages getting higher priority."""
    kw = keyword.lower()
    results = []

    # Search tag index
    for e in _INDEX:
        score = 0
        if e["title"].lower() == kw:
            score = 100
        elif kw in e["title"].lower():
            score = 50
        if _match_keyword(kw, e.get("description", "").lower()):
            score = max(score, _score_keyword(kw, e.get("description", "").lower()))
        if score > 0:
            results.append({
                "type": "tag",
                "tag": e["title"],
                "score": score,
                "default": e.get("default", ""),
                "description": e.get("description", ""),
            })

    # Search non-tag index (tutorials, how-tos, best practices, file formats)
    for e in _NON_TAG:
        if e["title"].startswith("Category:"):
            continue
        score = 0
        if _match_keyword(kw, e["title"].lower()):
            # Known VASP file pages get priority over description matches
            if e.get("is_file_page"):
                score = max(score, 80)
            else:
                score = max(score, 40)
        if _match_keyword(kw, e.get("summary", "").lower()):
            score = max(score, 25)
        if score > 0:
            results.append({
                "type": e["type"],
                "title": e["title"],
                "score": score,
                "summary": e.get("summary", ""),
            })

    results.sort(key=lambda x: -x["score"])
    return json.dumps({"query": keyword, "count": len(results), "results": results[:limit]}, indent=2, ensure_ascii=False)


@mcp.tool()
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


@mcp.tool()
def list_tags() -> str:
    """List all known INCAR tags with count."""
    names = [e["title"] for e in _INDEX]
    return json.dumps({"count": len(names), "tags": names}, indent=2, ensure_ascii=False)


@mcp.tool()
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


@mcp.tool()
def get_fullwiki(title: str) -> str:
    """Get full wiki page content by title. Supports tag names and VASP file names (POSCAR, OUTCAR, etc.)."""
    if title in _FULLWIKI:
        return json.dumps(_FULLWIKI[title], indent=2, ensure_ascii=False)
    matches = [k for k in _FULLWIKI if title.lower() in k.lower()]
    if matches:
        return json.dumps({"hint": f"Found {len(matches)} similar pages", "matches": matches}, indent=2)
    return json.dumps({"error": f"Page '{title}' not found"}, indent=2)


if __name__ == "__main__":
    mcp.run()
