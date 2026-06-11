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
    # HSE now goes through T3 hybrid search (no alias table)
    r = _cli("search", "HSE")
    assert r.returncode == 0, f"search failed: {r.stderr}"
    d = json.loads(r.stdout)
    # Should return results with HFSCREEN or HSE-related content
    results = d.get("results", [])
    assert len(results) > 0
    # At least one result should be tag or how_to about HSE
    titles = [r.get("tag") or r.get("title", "") for r in results]
    assert any("HSE" in t or "HFSCREEN" in t for t in titles)


def test_search_human():
    # POSCAR resolves as file page (T2), not through hybrid search
    r = _cli("search", "POSCAR", "-H")
    assert r.returncode == 0
    assert "## File: POSCAR" in r.stdout


def test_search_hybrid():
    # Hybrid search should always return results (BM25 + semantic)
    r = _cli("search", "phonon")
    assert r.returncode == 0
    d = json.loads(r.stdout)
    assert "results" in d and len(d["results"]) > 0


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
