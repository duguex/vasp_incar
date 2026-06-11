"""CLI query tool for VASP INCAR tags and configurations."""

import argparse
import json
import sys

from vasp_query._common import (
    load_data,
    load_json,
    match_keyword,
    score_keyword,
    format_tag_human,
    format_search_item_human,
    format_stats_human,
    resolve_tag,
    query_tag,
    hybrid_search,
    debug_log,
    get_debug_log,
    clear_debug_log,
    TAG_INDEX,
    NON_TAG_INDEX,
    TAG_STATS,
    TAG_CONFIGS,
    TAG_COOCCUR,
    WIKI_FULL,
    INCAR_DATA,
)
from vasp_query.processor import preprocess


# ── Commands ──────────────────────────────────────────────────────────


def cmd_tag(args) -> int:
    """Look up a specific tag by name."""
    index = load_data(TAG_INDEX)
    if index is None:
        print(json.dumps({"error": "tag_index.json not found. Run: python -m vasp_query preprocess"}))
        return 1

    resolved = resolve_tag(args.tag, index)
    if resolved is None:
        print(json.dumps({"error": f"Tag '{args.tag}' not found.",
                          "suggestion": "Use 'search' to find similar tags"},
                          indent=2, ensure_ascii=False))
        return 1

    if isinstance(resolved, list):
        if len(resolved) == 1:
            resolved = resolved[0]
        else:
            print(json.dumps({"hint": "Did you mean one of these?",
                              "matches": [t["title"] for t in resolved]},
                              indent=2, ensure_ascii=False))
            return 1

    configs = load_data(TAG_CONFIGS)
    stats = load_data(TAG_STATS)
    cooccur = load_data(TAG_COOCCUR)
    result = query_tag(resolved, configs=configs, stats=stats, cooccur=cooccur)

    if args.human:
        print(format_tag_human(resolved))
        c = result.get("configs")
        if c and c.get("common_contexts"):
            print(f"\n**典型配置 ({c['total']} 个样本)**:")
            for ctx in c["common_contexts"][:3]:
                pairs = "  ".join(f"{k}={v}" for k, v in ctx.items() if k != "count")
                print(f"- {pairs}  ({ctx['count']} 次)")
        s = result.get("stats")
        if s:
            print(f"\n**统计**: 频率 {s['frequency']}%  top: {', '.join(str(t['value']) for t in s['top_values'][:3])}")
    else:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def cmd_search(args) -> int:
    """Search tags and wiki pages by keyword."""
    clear_debug_log()
    keyword = args.keyword.lower().strip()
    debug_log(f"=== search({keyword!r}) ===")

    index = load_data(TAG_INDEX)
    non_tag = load_data(NON_TAG_INDEX)
    if index is None:
        print(json.dumps({"error": "tag_index.json not found. Run: python -m vasp_query preprocess"}))
        return 1

    # Tier 1: resolve_tag — exact match or file page
    debug_log("Tier 1: resolve_tag")
    resolved = resolve_tag(keyword, index, non_tag=non_tag)
    if isinstance(resolved, dict) and resolved.get("_match") == "exact":
        debug_log(f"  -> TIER 1 HIT: exact → {resolved['title']}")
        configs = load_data(TAG_CONFIGS)
        stats = load_data(TAG_STATS)
        cooccur = load_data(TAG_COOCCUR)
        result = query_tag(resolved, configs=configs, stats=stats, cooccur=cooccur)
        result["_match"] = "exact"
        if args.debug:
            result["_debug"] = get_debug_log()
        if args.human:
            print(f"## Tag: {resolved['title']} (exact match)\n")
            print(format_tag_human(resolved))
        else:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    # Tier 1b: resolve_tag matched a file page
    if isinstance(resolved, dict) and resolved.get("_match") == "file":
        debug_log(f"  -> TIER 2: file page {resolved['title']}")
        if args.human:
            print(f"## File: {resolved['title']}\n")
            print(resolved.get("summary", "")[:500])
        else:
            print(json.dumps(resolved, indent=2, ensure_ascii=False))
        return 0

    # Tier 2: File page exact match (fallback, if resolve_tag missed it)
    if non_tag:
        for entry in non_tag:
            if entry.get("is_file_page") and entry["title"].lower() == keyword:
                if args.human:
                    print(f"## File: {entry['title']}\n")
                    print(entry.get("summary", "")[:500])
                else:
                    print(json.dumps(entry, indent=2, ensure_ascii=False))
                return 0

    # Tier 3: Hybrid search (BM25 + semantic)
    debug_log("Tier 3: hybrid_search")
    if not args.type:
        try:
            hybrid_results = hybrid_search(keyword, top_k=args.limit)
            if hybrid_results:
                debug_log(f"  -> TIER 3: {len(hybrid_results)} results from hybrid search")
                if args.human:
                    print(f"## Search results for '{args.keyword}' ({len(hybrid_results)} found)\n")
                    for item in hybrid_results:
                        tag_name = item.get("tag") or item.get("title", "?")
                        print(f"**`{tag_name}`** ({item.get('type', '?')}, score={item.get('score', 0)})")
                        print()
                else:
                    result = {"query": args.keyword, "count": len(hybrid_results),
                              "results": hybrid_results}
                    if args.debug:
                        result["_debug"] = get_debug_log()
                    print(json.dumps(result, indent=2, ensure_ascii=False))
                return 0
            debug_log("  -> TIER 3: no results")
        except Exception as e:
            debug_log(f"  -> TIER 3: error {e}")

    # Tier 4: Legacy fallback search (for --type filter or if hybrid fails)
    debug_log("Tier 4: legacy fallback")
    type_filter = args.type
    results = []

    for entry in index:
        score = 0
        if entry["title"].lower() == keyword:
            score = 100
        elif keyword in entry["title"].lower():
            score = 50
        if match_keyword(keyword, entry.get("description", "").lower()):
            score = max(score, score_keyword(keyword, entry.get("description", "").lower()))
        if score > 0:
            results.append({
                "type": "tag",
                "tag": entry["title"],
                "score": score,
                "default": entry.get("default", ""),
                "description": entry.get("description", ""),
                "url": entry.get("url", ""),
            })

    # Search non-tag pages
    if non_tag:
        for entry in non_tag:
            if entry["title"].startswith("Category:"):
                continue
            score = 0
            if match_keyword(keyword, entry["title"].lower()):
                if entry.get("is_file_page"):
                    score = max(score, 80)
                else:
                    score = max(score, 40)
            if match_keyword(keyword, entry.get("summary", "").lower()):
                score = max(score, 25)
            if score > 0:
                results.append({
                    "type": entry["type"],
                    "title": entry["title"],
                    "score": score,
                    "summary": entry.get("summary", ""),
                })

    results.sort(key=lambda x: -x["score"])

    # Apply type filter
    if type_filter:
        results = [r for r in results if r["type"] == type_filter]

    results = results[:args.limit]

    if not results:
        debug_log("  -> TIER 4: no results")
        out = {"error": f"No results found matching '{args.keyword}'"}
        if args.debug:
            out["_debug"] = get_debug_log()
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return 1

    debug_log(f"  -> TIER 4: {len(results)} results (after filter/limit)")
    if args.debug:
        for r in results[:3]:
            debug_log(f"    #{results.index(r)}: {r.get('tag') or r.get('title','?')} score={r.get('score',0)}")

    if args.human:
        print(f"## Search results for '{args.keyword}' ({len(results)} found)\n")
        for item in results:
            print(format_search_item_human(item))
            print()
    else:
        out = {"query": args.keyword, "count": len(results), "results": results}
        if args.debug:
            out["_debug"] = get_debug_log()
        print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


def cmd_stats(args) -> int:
    """Show tag statistics or list all tags with counts."""
    stats = load_data(TAG_STATS)
    if stats is None:
        print(json.dumps({"error": "tag_stats.json not found. Run: python -m vasp_query preprocess"}))
        return 1

    if args.tag:
        tag = args.tag.upper()
        if tag not in stats:
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

        top_k = args.top_k
        entry = stats[tag]
        if top_k and top_k < len(entry.get("top_values", [])):
            entry = {**entry, "top_values": entry["top_values"][:top_k]}

        if args.human:
            print(format_stats_human({tag: entry}, tag))
        else:
            print(json.dumps({tag: entry}, indent=2, ensure_ascii=False))
    else:
        all_tags = [
            {"tag": k, "count": v["count"], "frequency_pct": v["frequency"]}
            for k, v in stats.items()
        ]
        all_tags.sort(key=lambda x: -x["count"])
        if args.human:
            print(f"# Tag statistics ({len(all_tags)} tags)\n")
            print(f"{'Tag':<20} {'Count':<8} {'Freq%':<8}")
            print(f"{'-'*20} {'-'*8} {'-'*8}")
            for t in all_tags[:40]:
                print(f"{t['tag']:<20} {t['count']:<8} {t['frequency_pct']:<8}")
            if len(all_tags) > 40:
                print(f"\n... and {len(all_tags) - 40} more (use --json for full list)")
        else:
            print(json.dumps(all_tags, indent=2, ensure_ascii=False))

    return 0


def cmd_incar(args) -> int:
    """Query INCAR configurations by conditions."""
    conditions = {}
    for cv in args.conditions:
        if "=" not in cv:
            print(json.dumps({"error": f"Invalid condition '{cv}', use KEY=VALUE"}))
            return 1
        k, v = cv.split("=", 1)
        try:
            v = int(v)
        except ValueError:
            try:
                v = float(v)
            except ValueError:
                pass
        conditions[k] = v

    incar_data = load_json(INCAR_DATA)
    if incar_data is None:
        print(json.dumps({"error": f"Cannot load {INCAR_DATA}. Check that data/raw/incar_data.json exists."}))
        return 1

    def match_all(item):
        incar = item.get("incar", {})
        return all(incar.get(k) == v for k, v in conditions.items())

    def match_any(item):
        incar = item.get("incar", {})
        return any(incar.get(k) == v for k, v in conditions.items())

    matcher = match_any if args.any_match else match_all
    matches = [item for item in incar_data if matcher(item)]

    result = {
        "conditions": {k: str(v) for k, v in conditions.items()},
        "match_mode": "any" if args.any_match else "all",
        "count": len(matches),
    }

    if len(matches) <= 100:
        result["configs"] = matches[:100]
    else:
        result["configs"] = matches[:3]
        result["note"] = f"Showing 3 of {len(matches)} matches. Use --limit to adjust."

    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    return 0


def cmd_related(args) -> int:
    """Show wiki-related tags for a given tag."""
    index = load_data(TAG_INDEX)
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

    # Case-insensitive fallback
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
    index = load_data(TAG_INDEX)
    if index is None:
        print(json.dumps({"error": "tag_index.json not found. Run: python -m vasp_query preprocess"}))
        return 1

    names = [entry["title"] for entry in index]
    if args.human:
        for name in names:
            print(name)
    else:
        print(json.dumps({"count": len(names), "tags": names}, indent=2, ensure_ascii=False))
    return 0


def cmd_fetch(args) -> int:
    """Fetch VASP wiki data."""
    from vasp_query.fetcher import fetch_all, fetch_check

    if args.check:
        result = fetch_check()
        if result["changed"]:
            print(f"Remote VASP wiki has changed since last fetch ({result.get('last_fetch', 'never')}).")
            print(f"  Pages: {result['page_count']} (was {result['last_page_count']})")
            print(f"  Last modified: {result['last_modified']}")
            if result["new_pages"]:
                print(f"  New pages: {', '.join(result['new_pages'][:10])}")
            if result["removed_pages"]:
                print(f"  Removed: {', '.join(result['removed_pages'][:5])}")
            print(f"  Run: python3 -m vasp_query fetch")
            return 1
        else:
            print(f"VASP wiki unchanged since {result.get('last_fetch', 'never')}.")
            print(f"  Pages: {result['page_count']}")
            print(f"  Last modified: {result['last_modified']}")
            return 0

    print("Fetching VASP wiki data (this may take ~15-20 minutes)...")
    count = fetch_all()
    print(f"Fetched {count} pages. Run: python3 -m vasp_query preprocess")
    return 0


def cmd_preprocess(args) -> int:
    """Run data preprocessing."""
    if args.check:
        stale = preprocess(check_only=True)
        if stale:
            print("Run: python -m vasp_query preprocess")
            return 1
        print("All data up to date.")
        return 0
    preprocess()
    return 0


def cmd_fullwiki(args) -> int:
    """Look up full wiki page content by title."""
    full = load_data(WIKI_FULL)
    if full is None:
        print(json.dumps({"error": "wiki_full.json not found. Run: python -m vasp_query preprocess"}))
        return 1

    title = args.title
    if title in full:
        if args.human:
            d = full[title]
            print(f"# {title}\n")
            print(d.get("content", ""))
            url = d.get("url", "")
            if url:
                print(f"\n📎 {url}")
        else:
            print(json.dumps(full[title], indent=2, ensure_ascii=False))
    else:
        matches = [k for k in full if title.lower() in k.lower()]
        if matches:
            print(json.dumps({"hint": f"Found {len(matches)} similar pages", "matches": matches}, indent=2, ensure_ascii=False))
        else:
            print(json.dumps({"error": f"Page '{title}' not found"}, indent=2, ensure_ascii=False))
        return 1
    return 0


def cmd_cooccur(args) -> int:
    """Analyze co-occurrence of two tags in real INCAR configurations."""
    import json as _json
    from collections import Counter

    tag_a = args.tag_a.upper()
    tag_b = args.tag_b.upper()

    incar_data = load_json(INCAR_DATA)
    if incar_data is None:
        print(_json.dumps({"error": f"Cannot load {INCAR_DATA}."}))
        return 1

    total = len(incar_data)
    count_a = count_b = count_both = 0
    a_values: list[str] = []
    b_values: list[str] = []
    ab_pairs: list[tuple[str, str]] = []

    for item in incar_data:
        incar = item.get("incar", {})
        has_a = tag_a in incar
        has_b = tag_b in incar
        if has_a:
            count_a += 1
            a_values.append(str(incar[tag_a]))
        if has_b:
            count_b += 1
            b_values.append(str(incar[tag_b]))
        if has_a and has_b:
            count_both += 1
            ab_pairs.append((str(incar[tag_a]), str(incar[tag_b])))

    # Also get wiki relationship
    index = load_data(TAG_INDEX)
    wiki_related = False
    for entry in index or []:
        if entry["title"] == tag_a and tag_b in entry.get("related", []):
            wiki_related = True
            break
        if entry["title"] == tag_b and tag_a in entry.get("related", []):
            wiki_related = True
            break

    def top_n(items: list[str], n: int = 5):
        return [{"value": v, "count": c} for v, c in Counter(items).most_common(n)]

    def top_pairs(items: list[tuple[str, str]], n: int = 5):
        return [{"pair": f"{a}={b}", "count": c}
                for (a, b), c in Counter(items).most_common(n)]

    result = {
        "tag_a": tag_a,
        "tag_b": tag_b,
        "total_configs": total,
        "count_a": count_a,
        "frequency_a_pct": round(count_a / total * 100, 1) if total else 0,
        "count_b": count_b,
        "frequency_b_pct": round(count_b / total * 100, 1) if total else 0,
        "cooccur_count": count_both,
        "cooccur_pct": round(count_both / total * 100, 1) if total else 0,
        "wiki_related": wiki_related,
        "top_a_values": top_n(a_values),
        "top_b_values": top_n(b_values),
        "top_pairs": top_pairs(ab_pairs) if ab_pairs else [],
    }

    if args.human:
        print(f"## Co-occurrence: `{tag_a}` × `{tag_b}`\n")
        print(f"**总配置数**: {total}")
        print(f"**{tag_a} 出现**: {count_a} ({result['frequency_a_pct']}%)")
        print(f"**{tag_b} 出现**: {count_b} ({result['frequency_b_pct']}%)")
        print(f"**同时出现**: {count_both} ({result['cooccur_pct']}%)")
        print(f"**Wiki 关联**: {'✅ 是' if wiki_related else '❌ 否'}")
        if result["top_pairs"]:
            print(f"\n**常见组合**:")
            for p in result["top_pairs"]:
                print(f"  {p['pair']} — {p['count']} 次")
    else:
        print(_json.dumps(result, indent=2, ensure_ascii=False))

    return 0


# ── CLI ──────────────────────────────────────────────────────────────


def _add_human_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("-H", "--human", action="store_true", dest="human",
                        help="Human-readable output (Markdown) instead of JSON")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vasp_query",
        description="VASP INCAR Tag Query Tool — agent-friendly CLI for querying VASP parameters",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__import__('vasp_query').__version__}"
    )

    parser.set_defaults(human=False, debug=False)
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # tag
    p_tag = subparsers.add_parser("tag", help="Look up a specific INCAR tag")
    p_tag.add_argument("tag", help="Tag name (e.g., LEFG, ENCUT)")
    _add_human_arg(p_tag)

    # search
    p_search = subparsers.add_parser("search", help="Search tags, wiki pages, and VASP file formats by keyword")
    p_search.add_argument("keyword", help="Search keyword")
    p_search.add_argument("-n", "--limit", type=int, default=20, help="Max results (default: 20)")
    p_search.add_argument("-t", "--type", choices=["tag", "tutorial", "how_to", "best_practices", "faq", "reference", "other"],
                          help="Filter by result type")
    p_search.add_argument("--debug", action="store_true", help="Show intermediate search steps")
    _add_human_arg(p_search)

    # stats
    p_stats = subparsers.add_parser("stats", help="Show tag statistics")
    p_stats.add_argument("tag", nargs="?", help="Tag name (omit to list all)")
    p_stats.add_argument("-k", "--top-k", type=int, help="Number of top values to show (default: all)")
    _add_human_arg(p_stats)

    # incar
    p_incar = subparsers.add_parser("incar", help="Query INCAR configs by conditions")
    p_incar.add_argument("conditions", nargs="+", help="KEY=VALUE conditions")
    p_incar.add_argument("--any-match", action="store_true", help="Match any condition instead of all")

    # related
    p_related = subparsers.add_parser("related", help="Show wiki-related tags for a given tag")
    p_related.add_argument("tag", help="Tag name")

    # list
    p_list = subparsers.add_parser("list", help="List all known tags")
    _add_human_arg(p_list)

    # preprocess
    p_pre = subparsers.add_parser("preprocess", help="Parse wiki and data files into structured JSON")
    p_pre.add_argument("--check", action="store_true", help="Detect stale raw data without running")

    # fetch
    p_fetch = subparsers.add_parser("fetch", help="Fetch latest VASP wiki data from vasp.at")
    p_fetch.add_argument("--check", action="store_true", help="Check remote for changes without downloading")
    _add_human_arg(p_fetch)

    # fullwiki
    p_fw = subparsers.add_parser("fullwiki", help="Get full wiki page content")
    p_fw.add_argument("title", help="Wiki page title")
    _add_human_arg(p_fw)

    # cooccur
    p_co = subparsers.add_parser("cooccur", help="Analyze co-occurrence of two tags in real INCAR configs")
    p_co.add_argument("tag_a", help="First tag")
    p_co.add_argument("tag_b", help="Second tag")
    _add_human_arg(p_co)

    return parser


def main() -> int:
    parser = build_parser()
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
        "fetch": cmd_fetch,
        "fullwiki": cmd_fullwiki,
        "cooccur": cmd_cooccur,
    }

    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
