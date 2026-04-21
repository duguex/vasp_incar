"""CLI query tool for VASP INCAR tags and configurations."""

import argparse
import json
import re
import sys
from pathlib import Path

from vasp_query.processor import (
    _VASP_BASE,
    TAG_INDEX,
    NON_TAG_INDEX,
    TAG_STATS,
    WIKI_FULL,
    INCAR_DATA,
    preprocess,
)


def _load_json(path: Path) -> list | dict:
    if not path.exists():
        return None
    with open(path, "r") as f:
        return json.load(f)


# ── Commands ──────────────────────────────────────────────────────────


def cmd_tag(args) -> int:
    """Look up a specific tag by name."""
    index = _load_json(TAG_INDEX)
    if index is None:
        print(json.dumps({"error": "tag_index.json not found. Run: python -m vasp_query preprocess"}))
        return 1

    tag_name = args.tag.upper()
    for entry in index:
        if entry["title"] == tag_name:
            print(json.dumps(entry, indent=2, ensure_ascii=False))
            return 0

    # Partial match
    matches = [e for e in index if tag_name in e["title"]]
    if matches:
        if len(matches) == 1:
            print(json.dumps(matches[0], indent=2, ensure_ascii=False))
            return 0
        print(json.dumps({"hint": f"Did you mean one of these?", "matches": [m["title"] for m in matches]}, indent=2, ensure_ascii=False))
        return 1

    # Case-insensitive match
    matches = [e for e in index if e["title"].upper() == tag_name]
    if matches:
        print(json.dumps(matches[0], indent=2, ensure_ascii=False))
        return 0

    print(json.dumps({"error": f"Tag '{tag_name}' not found.", "suggestion": "Use 'search' to find similar tags"}, indent=2, ensure_ascii=False))
    return 1


def _match_keyword(kw: str, text: str) -> bool:
    """Match keyword against text using word-level matching."""
    if kw in text:
        return True
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


def cmd_search(args) -> int:
    """Search tags and wiki pages by keyword."""
    index = _load_json(TAG_INDEX)
    non_tag = _load_json(NON_TAG_INDEX)
    if index is None:
        print(json.dumps({"error": "tag_index.json not found. Run: python -m vasp_query preprocess"}))
        return 1

    keyword = args.keyword.lower()
    results = []

    # Search tag index
    for entry in index:
        score = 0
        if entry["title"].lower() == keyword:
            score = 100
        elif keyword in entry["title"].lower():
            score = 50
        if _match_keyword(keyword, entry.get("description", "").lower()):
            score = max(score, _score_keyword(keyword, entry.get("description", "").lower()))
        if score > 0:
            results.append({
                "type": "tag",
                "tag": entry["title"],
                "score": score,
                "default": entry.get("default", ""),
                "description": entry.get("description", ""),
                "url": entry.get("url", ""),
            })

    # Search non-tag pages (tutorials, how-tos, best practices, file formats)
    if non_tag:
        for entry in non_tag:
            if entry["title"].startswith("Category:"):
                continue
            score = 0
            if _match_keyword(keyword, entry["title"].lower()):
                if entry.get("is_file_page"):
                    score = max(score, 80)
                else:
                    score = max(score, 40)
            if _match_keyword(keyword, entry.get("summary", "").lower()):
                score = max(score, 25)
            if score > 0:
                results.append({
                    "type": entry["type"],
                    "title": entry["title"],
                    "score": score,
                    "summary": entry.get("summary", ""),
                })

    results.sort(key=lambda x: -x["score"])
    results = results[:args.limit]

    if not results:
        print(json.dumps({"error": f"No results found matching '{args.keyword}'"}, indent=2, ensure_ascii=False))
        return 1

    print(json.dumps({"query": args.keyword, "count": len(results), "results": results}, indent=2, ensure_ascii=False))
    return 0


def cmd_stats(args) -> int:
    """Show tag statistics or list all tags with counts."""
    stats = _load_json(TAG_STATS)
    if stats is None:
        print(json.dumps({"error": "tag_stats.json not found. Run: python -m vasp_query preprocess"}))
        return 1

    if args.tag:
        tag = args.tag.upper()
        if tag not in stats:
            # Try partial match
            matches = [k for k in stats if tag in k]
            if matches:
                if len(matches) == 1:
                    tag = matches[0]
                else:
                    print(json.dumps({"error": f"Ambiguous tag '{tag}'", "matches": matches}, indent=2, ensure_ascii=False))
                    return 1
            else:
                print(json.dumps({"error": f"Tag '{tag}' not found in stats database"}, indent=2, ensure_ascii=False))
                return 1
        print(json.dumps({tag: stats[tag]}, indent=2, ensure_ascii=False))
    else:
        # List all tags with counts, sorted by frequency
        all_tags = [
            {"tag": k, "count": v["count"], "frequency_pct": v["frequency"]}
            for k, v in stats.items()
        ]
        all_tags.sort(key=lambda x: -x["count"])
        print(json.dumps(all_tags, indent=2, ensure_ascii=False))

    return 0


def cmd_incar(args) -> int:
    """Query INCAR configurations by conditions."""
    index = _load_json(TAG_INDEX)
    if index is None:
        print(json.dumps({"error": "tag_index.json not found. Run: python -m vasp_query preprocess"}))
        return 1

    # Parse conditions
    conditions = {}
    for cv in args.conditions:
        if "=" not in cv:
            print(json.dumps({"error": f"Invalid condition '{cv}', use KEY=VALUE"}))
            return 1
        k, v = cv.split("=", 1)
        # Try numeric conversion
        try:
            v = int(v)
        except ValueError:
            try:
                v = float(v)
            except ValueError:
                pass
        conditions[k] = v

    # Load incar data
    incar_data = _load_json(INCAR_DATA)
    if incar_data is None:
        # Fallback: load directly
        try:
            with open(_VASP_BASE / "incar_data.json", "r") as f:
                incar_data = json.load(f)
        except Exception as e:
            print(json.dumps({"error": f"Cannot load incar_data.json: {e}"}))
            return 1

    # Filter
    def match_all(item):
        incar = item.get("incar", {})
        return all(
            incar.get(k) == v
            for k, v in conditions.items()
        )

    def match_any(item):
        incar = item.get("incar", {})
        return any(
            incar.get(k) == v
            for k, v in conditions.items()
        )

    matcher = match_any if args.any_match else match_all
    matches = [item for item in incar_data if matcher(item)]

    # Return summary
    result = {
        "conditions": {k: str(v) for k, v in conditions.items()},
        "match_mode": "any" if args.any_match else "all",
        "count": len(matches),
    }

    if len(matches) <= 100:
        result["configs"] = matches[:100]
    else:
        # Just show first few + count
        result["configs"] = matches[:3]
        result["note"] = f"Showing 3 of {len(matches)} matches. Use --limit to adjust."

    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    return 0


def cmd_related(args) -> int:
    """Show wiki-related tags for a given tag."""
    index = _load_json(TAG_INDEX)
    if index is None:
        print(json.dumps({"error": "tag_index.json not found. Run: python -m vasp_query preprocess"}))
        return 1

    tag = args.tag.upper()
    for entry in index:
        if entry["title"] == tag:
            related = entry.get("related", [])
            print(json.dumps({
                "tag": tag,
                "related_tags": related,
                "url": entry.get("url", ""),
            }, indent=2, ensure_ascii=False))
            return 0

    # Case-insensitive
    for entry in index:
        if entry["title"].upper() == tag:
            related = entry.get("related", [])
            print(json.dumps({
                "tag": entry["title"],
                "related_tags": related,
                "url": entry.get("url", ""),
            }, indent=2, ensure_ascii=False))
            return 0

    print(json.dumps({"error": f"Tag '{tag}' not found"}, indent=2, ensure_ascii=False))
    return 1


def cmd_list(args) -> int:
    """List all available tags."""
    index = _load_json(TAG_INDEX)
    if index is None:
        print(json.dumps({"error": "tag_index.json not found. Run: python -m vasp_query preprocess"}))
        return 1

    names = [entry["title"] for entry in index]
    print(json.dumps({"count": len(names), "tags": names}, indent=2, ensure_ascii=False))
    return 0


def cmd_preprocess(args) -> int:
    """Run data preprocessing."""
    preprocess()
    return 0


def cmd_fullwiki(args) -> int:
    """Look up full wiki page content by title."""
    full = _load_json(WIKI_FULL)
    if full is None:
        print(json.dumps({"error": "wiki_full.json not found. Run: python -m vasp_query preprocess"}))
        return 1

    title = args.title
    if title in full:
        print(json.dumps(full[title], indent=2, ensure_ascii=False))
    else:
        # Fuzzy match
        matches = [k for k in full if title.lower() in k.lower()]
        if matches:
            print(json.dumps({"hint": f"Found {len(matches)} similar pages", "matches": matches}, indent=2, ensure_ascii=False))
        else:
            print(json.dumps({"error": f"Page '{title}' not found"}, indent=2, ensure_ascii=False))
        return 1
    return 0


# ── CLI ──────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="vasp_query",
        description="VASP INCAR Tag Query Tool — agent-friendly CLI for querying VASP parameters",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__import__('vasp_query').__version__}"
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # tag
    p_tag = subparsers.add_parser("tag", help="Look up a specific INCAR tag")
    p_tag.add_argument("tag", help="Tag name (e.g., LEFG, ENCUT)")

    # search
    p_search = subparsers.add_parser("search", help="Search tags, wiki pages, and VASP file formats by keyword")
    p_search.add_argument("keyword", help="Search keyword")
    p_search.add_argument("-n", "--limit", type=int, default=20, help="Max results (default: 20)")

    # stats
    p_stats = subparsers.add_parser("stats", help="Show tag statistics")
    p_stats.add_argument("tag", nargs="?", help="Tag name (omit to list all)")

    # incar
    p_incar = subparsers.add_parser("incar", help="Query INCAR configs by conditions")
    p_incar.add_argument("conditions", nargs="+", help="KEY=VALUE conditions")
    p_incar.add_argument("--any-match", action="store_true", help="Match any condition instead of all")

    # related
    p_related = subparsers.add_parser("related", help="Show wiki-related tags for a given tag")
    p_related.add_argument("tag", help="Tag name")

    # list
    subparsers.add_parser("list", help="List all known tags")

    # preprocess
    subparsers.add_parser("preprocess", help="Parse wiki and data files into structured JSON")

    # fullwiki
    p_fw = subparsers.add_parser("fullwiki", help="Get full wiki page content")
    p_fw.add_argument("title", help="Wiki page title")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    commands = {
        "tag": cmd_tag,
        "search": cmd_search,
        "stats": cmd_stats,
        "incar": cmd_incar,
        "related": cmd_related,
        "list": cmd_list,
        "preprocess": cmd_preprocess,
        "fullwiki": cmd_fullwiki,
    }

    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
