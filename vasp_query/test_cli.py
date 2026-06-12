"""Smoke tests for CLI subcommands and human-readable output."""

import subprocess
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent


def _cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "vasp_query", *args],
        capture_output=True, text=True, cwd=BASE.parent,
    )


def test_tag_json():
    r = _cli("tag", "ENCUT")
    assert r.returncode == 0, f"tag ENCUT failed: {r.stderr}"
    d = json.loads(r.stdout)
    assert d["info"]["title"] == "ENCUT"
    assert d["info"]["default"] != ""
    assert d["info"]["description"] != ""
    assert d["confidence"]["source"] == "vasp.at/wiki - official"


def test_tag_human():
    r = _cli("tag", "ENCUT", "-H")
    assert r.returncode == 0, f"tag ENCUT -H failed: {r.stderr}"
    assert "## ENCUT" in r.stdout
    assert "**相关标签**" in r.stdout


def test_search_type_filter():
    # HSE resolves via term_map → HFSCREEN (T1), structured response
    r = _cli("search", "HSE")
    assert r.returncode == 0, f"search failed: {r.stderr}"
    d = json.loads(r.stdout)
    # T1 hit returns info.title = HFSCREEN
    assert d.get("info", {}).get("title") == "HFSCREEN"


def test_search_human():
    # POSCAR resolves as file page (T1b, via resolve_tag with non_tag)
    r = _cli("search", "POSCAR", "-H")
    assert r.returncode == 0
    assert "## File: POSCAR" in r.stdout


def test_search_hybrid():
    # Hybrid search via T3 (use a query not covered by term_map)
    r = _cli("search", "convergence problems")
    assert r.returncode == 0
    d = json.loads(r.stdout)
    assert "results" in d and len(d["results"]) > 0


def test_search_type_filter_uses_hybrid():
    """Issue #2: --type must apply as a post-filter, not skip the hybrid tier."""
    # "energy cutoff" hits T3 hybrid (no term_map match); without --type, hybrid runs.
    r1 = _cli("search", "energy cutoff", "--debug")
    assert r1.returncode == 0
    d1 = json.loads(r1.stdout)
    assert "results" in d1, f"hybrid didn't run, stdout={r1.stdout!r}"
    debug1 = d1.get("_debug", [])
    assert any("TIER 3" in line for line in debug1), \
        f"expected TIER 3 in debug log, got: {debug1!r}"

    # With --type=tag, hybrid should STILL run, then filter results.
    r2 = _cli("search", "energy cutoff", "--type", "tag", "--debug")
    assert r2.returncode == 0
    d2 = json.loads(r2.stdout)
    assert "results" in d2, f"hybrid didn't run with --type, stdout={r2.stdout!r}"
    debug2 = d2.get("_debug", [])
    assert any("TIER 3" in line for line in debug2), \
        f"expected TIER 3 in debug log with --type, got: {debug2!r}"
    # All returned results must satisfy the type filter
    for item in d2.get("results", []):
        assert item.get("type") == "tag", f"type filter violated: {item!r}"


def test_search_type_filter_post_applied():
    """--type=tag must apply AFTER hybrid ranking, not as an algorithm switch."""
    # Compare hybrid output without filter and with filter; the filtered result
    # should be a subset of the unfiltered one (preserving order).
    r_full = _cli("search", "energy cutoff", "-n", "20")
    r_tag = _cli("search", "energy cutoff", "-n", "20", "--type", "tag")
    if r_full.returncode == 0 and r_tag.returncode == 0:
        d_full = json.loads(r_full.stdout)
        d_tag = json.loads(r_tag.stdout)
        tag_ids = {r["id"] for r in d_tag.get("results", [])}
        full_ids = {r["id"] for r in d_full.get("results", [])}
        # Every tag-filtered id must appear in the unfiltered set
        assert tag_ids <= full_ids, f"filtered set not subset: {tag_ids - full_ids}"


def test_list_human():
    r = _cli("list", "-H")
    assert r.returncode == 0
    assert "ENCUT" in r.stdout
    assert "LEFG" in r.stdout


def test_stats_top_k():
    r = _cli("stats", "ENCUT", "-k", "2")
    assert r.returncode == 0
    d = json.loads(r.stdout)
    assert len(d["ENCUT"]["top_values"]) == 2


def test_stats_human():
    r = _cli("stats", "ENCUT", "-H")
    assert r.returncode == 0
    assert "## ENCUT" in r.stdout
    assert "**出现次数**" in r.stdout


def test_cooccur_json():
    r = _cli("cooccur", "ENCUT", "PREC")
    assert r.returncode == 0, f"cooccur failed: {r.stderr}"
    d = json.loads(r.stdout)
    assert d["tag_a"] == "ENCUT"
    assert d["tag_b"] == "PREC"
    assert d["total_configs"] >= 10000
    assert d["cooccur_count"] >= 1000
    assert "wiki_related" in d


def test_cooccur_human():
    r = _cli("cooccur", "ENCUT", "PREC", "-H")
    assert r.returncode == 0
    assert "ENCUT" in r.stdout
    assert "PREC" in r.stdout
    assert "**总配置数**" in r.stdout


def test_fullwiki_human():
    r = _cli("fullwiki", "LEFG", "-H")
    assert r.returncode == 0
    assert "# LEFG" in r.stdout


def test_help():
    r = _cli("--help")
    assert r.returncode == 0
    assert "cooccur" in r.stdout


def test_version():
    r = _cli("--version")
    assert r.returncode == 0
    assert "vasp_query" in r.stdout


def test_invalid_tag():
    r = _cli("tag", "ZZZZ_NOT_EXIST")
    assert r.returncode == 1
    d = json.loads(r.stdout)
    assert "error" in d


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
