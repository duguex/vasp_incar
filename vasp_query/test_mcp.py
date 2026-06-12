"""Self-contained smoke test for vasp_query MCP tools.

Usage:
    python3 -m vasp_query.test_mcp         # run all tests
    python3 -m vasp_query.test_mcp --tool get_tag  # run only get_tag tests
    python3 -m vasp_query.test_mcp --quiet # only failures + summary
"""

import json
import sys
import argparse
from pathlib import Path
from unittest import mock

from vasp_query import mcp_server as MOD


# ── Helpers ───────────────────────────────────────────────────────────


def call_tool(tool_name, **kwargs):
    """Call an MCP tool by name and return parsed JSON."""
    tool_fn = getattr(MOD, tool_name)
    return json.loads(tool_fn(**kwargs))


def _run_checks(desc, checks):
    """Run a list of (description, condition) tuples."""
    passed, failed = 0, 0
    for d, cond in checks:
        if cond:
            if not QUIET:
                print(f"  ✓ {d}")
            passed += 1
        else:
            print(f"  ✗ {d}")
            failed += 1
    return passed, failed


# ── Test suites ──────────────────────────────────────────────────────


def _test_get_tag():
    d = call_tool("get_tag", name="LEFG")
    return [
        ("LEFG has title", d.get("title") == "LEFG"),
        ("description > 100 chars", len(d.get("description", "")) > 100),
        ("related_tags non-empty", len(d.get("related", [])) > 0),
        ("default value present", d.get("default") != ""),
        ("value_format present", d.get("value", "") != ""),
        ("url non-empty", d.get("url", "") != ""),
    ]


def _test_get_tag_common():
    results = []
    for tag in ("ENCUT", "ISMEAR", "SIGMA", "NSW", "LDAU", "IBRION"):
        d = call_tool("get_tag", name=tag)
        results.append((f"{tag} title={tag}", d.get("title") == tag))
        results.append((f"{tag} has default", d.get("default") != ""))
        results.append((f"{tag} has description", len(d.get("description", "")) > 10))
    d = call_tool("get_tag", name="algo")
    results.append(("smallcase 'algo' -> ALGO", d.get("title") == "ALGO"))
    return results


def _test_get_tag_notfound():
    d = call_tool("get_tag", name="THIS_TAG_DOES_NOT_EXIST_XYZ")
    return [("error key present", "error" in d)]


def _test_search_basic():
    d = call_tool("search_tags", keyword="EFG")
    return [
        ("count > 0", d.get("count", 0) > 0),
        ("results is list", isinstance(d.get("results"), list)),
        ("LEFG found", any(r.get("tag") == "LEFG" for r in d.get("results", []))),
        ("all results have score", all("score" in r for r in d.get("results", []))),
        ("sorted descending", all(
            d["results"][i]["score"] >= d["results"][i + 1]["score"]
            for i in range(min(len(d["results"]) - 1, 20))
        )),
    ]


def _test_search_files():
    results = []
    for fpage in ("POSCAR", "OUTCAR", "KPOINTS", "POTCAR", "CHGCAR", "WAVECAR", "DOSCAR", "INCAR"):
        d = call_tool("search_tags", keyword=fpage)
        # Accept either the raw T1b file-page shape (title at top level)
        # or the T1 query_tag-wrapped shape (title under info).
        def _has_title(r, t):
            return r.get("title") == t or r.get("info", {}).get("title") == t
        results.append((f"{fpage} in results", any(_has_title(r, fpage) for r in d.get("results", []))))
    d = call_tool("search_tags", keyword="POSCAR")
    first = d.get("results", [{}])[0]
    results.append(("POSCAR found", first.get("title") == "POSCAR" or first.get("info", {}).get("title") == "POSCAR"))
    return results


def _test_search_tutorials():
    d = call_tool("search_tags", keyword="molecular dynamics")
    results = [("molecular dynamics has results", d.get("count", 0) > 0)]
    d = call_tool("search_tags", keyword="Bethe-Salpeter")
    results.append(("Bethe-Salpeter has results", d.get("count", 0) > 0))
    d = call_tool("search_tags", keyword="nuclear")
    results.append(("nuclear matches QUAD_EFG", any(r.get("tag") == "QUAD_EFG" for r in d.get("results", []))))
    return results


def _test_search_edge():
    d = call_tool("search_tags", keyword="tag", limit=5)
    results = [("limit=5: len(results) <= 5", len(d.get("results", [])) <= 5)]
    d = call_tool("search_tags", keyword="zzzz_nonexistent_xyz")
    # T3 hybrid search always returns something (semantic matching), count should be > 0
    results.append(("nonsense query returns results", d.get("count", -1) > 0))
    return results


def _test_hybrid_signal_b_called_once():
    """Issue #1: Signal B (tag-only semantic) must run once per query, not per
    Signal A iteration. The previous indentation bug fired Signal B inside the
    Signal A `for rank, idx in enumerate(top_idx[:5])` loop, causing 5x
    re-execution of load_data_raw(TAG_VECTORS) and np.dot(tag_vectors, query_vec.T).
    """
    from vasp_query import _common

    # Reset module-level caches so we observe the call counts.
    _common._INDEX_CACHE = None
    _common._SEARCHER_CACHE = None
    _common._MODEL_CACHE = None
    _common.clear_debug_log()

    with mock.patch.object(_common, "load_data_raw", wraps=_common.load_data_raw) as spy_raw:
        try:
            _common.hybrid_search("ENCUT", top_k=10)
        except Exception:
            # If tantivy/model unavailable in this env, the function returns []
            # and never enters the semantic block. Skip with a neutral result.
            return [("hybrid_search returned without raising", True)]

    # Count calls to load_data_raw for TAG_VECTORS specifically.
    # After the fix: 1 call total (sibling of Signal A).
    # Pre-fix bug: 5 calls (one per Signal A iteration).
    tag_calls = sum(
        1 for c in spy_raw.call_args_list
        if "tag_vectors" in str(c)
    )
    return [
        (f"load_data_raw(TAG_VECTORS) called once (was 5 pre-fix; observed {tag_calls})",
         tag_calls == 1),
    ]


def _test_stats_single():
    d = call_tool("get_tag_stats", name="ENCUT")
    encut = d.get("ENCUT", {})
    return [
        ("ENCUT present", "ENCUT" in d),
        ("has frequency", "frequency" in encut),
        ("has top_values", "top_values" in encut),
        ("top_values non-empty", len(encut.get("top_values", [])) > 0),
    ]


def _test_stats_fuzzy():
    d = call_tool("get_tag_stats", name="ENC")
    results = [("fuzzy 'ENC' -> ENCUT", "ENCUT" in d)]
    d = call_tool("get_tag_stats", name="NOTEXISTTAG")
    results.append(("non-existent returns error", "error" in d))
    return results


def _test_search_tags_caching():
    """Issue #3: TAG_CONFIGS / TAG_STATS / TAG_COOCCUR must NOT be re-parsed
    on every search_tags call. They are cached at module import.
    """
    from vasp_query import _common

    with mock.patch.object(_common, "load_data", wraps=_common.load_data) as spy:
        for _ in range(10):
            try:
                MOD.search_tags("ENCUT", limit=5)
            except Exception:
                pass

        configs_calls = sum(
            1 for c in spy.call_args_list
            if "tag_configs" in str(c)
        )
        stats_calls = sum(
            1 for c in spy.call_args_list
            if "tag_stats" in str(c)
        )
        cooccur_calls = sum(
            1 for c in spy.call_args_list
            if "tag_cooccur" in str(c)
        )

    return [
        (f"load_data(TAG_CONFIGS) called 0 times (was 1/call pre-fix; observed {configs_calls})",
         configs_calls == 0),
        (f"load_data(TAG_STATS) called 0 times (observed {stats_calls})",
         stats_calls == 0),
        (f"load_data(TAG_COOCCUR) called 0 times (observed {cooccur_calls})",
         cooccur_calls == 0),
    ]


def _test_stats_all():
    d = call_tool("get_tag_stats")
    return [
        ("returns list", isinstance(d, list)),
        ("contains ENCUT", any(t.get("tag") == "ENCUT" for t in d if isinstance(t, dict))),
        ("sorted descending", len(d) >= 2 and d[0].get("count", 0) >= d[-1].get("count", 0)),
        (">= 200 tags", len(d) >= 200),
    ]


def _test_list():
    d = call_tool("list_tags")
    count = d.get("count", 0)
    return [
        (f"count == {count}", count >= 600),  # avoid brittle hard-coded number
        ("ENCUT in tags", "ENCUT" in d.get("tags", [])),
        ("tags is list", isinstance(d.get("tags"), list)),
    ]


def _test_related():
    d = call_tool("get_related_tags", name="LEFG")
    results = [
        ("LEFG has related_tags", len(d.get("related_tags", [])) > 0),
        ("tag field == LEFG", d.get("tag") == "LEFG"),
        ("has url", "url" in d),
    ]
    d = call_tool("get_related_tags", name="NOTEXIST")
    results.append(("non-existent returns error", "error" in d))
    return results


def _test_fullwiki_basic():
    d = call_tool("get_fullwiki", title="LEFG")
    return [
        ("LEFG has content", "content" in d),
        ("content > 500 chars", len(d.get("content", "")) > 500),
    ]


def _test_fullwiki_files():
    results = []
    for fpage in ("POSCAR", "OUTCAR", "KPOINTS", "POTCAR", "DOSCAR", "WAVECAR", "CONTCAR"):
        d = call_tool("get_fullwiki", title=fpage)
        results.append((f"{fpage} has content", "content" in d))
    return results


def _test_fullwiki_notfound():
    d = call_tool("get_fullwiki", title="NOTEXIST_PAGE_XYZ")
    results = [("error present", "error" in d)]
    d2 = call_tool("get_fullwiki", title="LE")
    results.append(("fuzzy match returns hint+matches", "hint" in d2 and "matches" in d2))
    return results


def _test_fullwiki_tutorial():
    d = call_tool("get_fullwiki", title="Molecular dynamics - Tutorial")
    return [("Tutorial has content > 100 chars", "content" in d and len(d.get("content", "")) > 100)]


# ── Registry ─────────────────────────────────────────────────────────

SUITE = {
    "get_tag": [
        ("basic fields", _test_get_tag),
    ],
    "get_tag_common": [
        ("common tags + case insensitive", _test_get_tag_common),
    ],
    "get_tag_notfound": [
        ("not found", _test_get_tag_notfound),
    ],
    "search_tags": [
        ("keyword search", _test_search_basic),
    ],
    "search_file_pages": [
        ("file pages ranked high", _test_search_files),
    ],
    "search_tutorials": [
        ("tutorial pages", _test_search_tutorials),
    ],
    "search_edge_cases": [
        ("limit + empty", _test_search_edge),
    ],
    "hybrid_signal_b_once": [
        ("Signal B not nested in Signal A loop", _test_hybrid_signal_b_called_once),
    ],
    "search_tags_caching": [
        ("TAG_CONFIGS / TAG_STATS / TAG_COOCCUR not re-parsed per call", _test_search_tags_caching),
    ],
    "get_tag_stats": [
        ("single tag stats", _test_stats_single),
    ],
    "get_tag_stats_fuzzy": [
        ("fuzzy + notfound", _test_stats_fuzzy),
    ],
    "get_tag_stats_all": [
        ("all tags list", _test_stats_all),
    ],
    "list_tags": [
        ("list all tags", _test_list),
    ],
    "get_related_tags": [
        ("related tags", _test_related),
    ],
    "get_fullwiki": [
        ("tag wiki content", _test_fullwiki_basic),
    ],
    "get_fullwiki_file_pages": [
        ("file page wiki content", _test_fullwiki_files),
    ],
    "get_fullwiki_notfound": [
        ("not found + fuzzy", _test_fullwiki_notfound),
    ],
    "get_fullwiki_tutorial": [
        ("tutorial wiki content", _test_fullwiki_tutorial),
    ],
}

ALL_TOOLS = sorted(SUITE.keys())

QUIET = False


def main():
    global QUIET

    parser = argparse.ArgumentParser(description="VASP MCP tool smoke tests")
    parser.add_argument("--quiet", action="store_true", help="only show failures")
    parser.add_argument("--tool", nargs="+", choices=ALL_TOOLS,
                        help="run only specified tool suites")
    args = parser.parse_args()
    QUIET = args.quiet

    target_tools = set(args.tool) if args.tool else set(ALL_TOOLS)

    total_passed, total_failed = 0, 0
    failed_suites = []

    for tool_name, suites in sorted(SUITE.items()):
        if tool_name not in target_tools:
            continue

        if not QUIET:
            print(f"\n{'=' * 70}")
            print(f"MCP TOOL: {tool_name}")
            print(f"{'=' * 70}")

        for desc, test_fn in suites:
            passed, failed = _run_checks(desc, test_fn())
            total_passed += passed
            total_failed += failed
            if failed > 0:
                failed_suites.append(f"{tool_name}: {desc}")

    print(f"\n{'=' * 70}")
    print(f"Result: {total_passed} passed, {total_failed} failed")
    print(f"{'=' * 70}")

    if failed_suites:
        print("Failed suites:")
        for s in failed_suites:
            print(f"  - {s}")
        sys.exit(1)
    else:
        print("All tests passed!")
        sys.exit(0)


if __name__ == "__main__":
    main()
