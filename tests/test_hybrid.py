"""Tests for omx-db hybrid search (FTS5 + semantic RRF)."""

import json
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def requires_db():
    """Skip if database is missing."""
    if not (PROJECT_ROOT / "openmx.db").exists():
        pytest.skip("openmx.db not found")


def test_hybrid_json(invoke_db):
    """Hybrid search returns valid JSON with results."""
    out, err, code = invoke_db(["omx-db", "hybrid", "SCF", "--json"])
    assert code == 0
    data = json.loads(out)
    assert "results" in data
    assert data["count"] > 0
    for r in data["results"]:
        assert "sec_num" in r
        assert "title" in r
        assert "score" in r
        assert "source" in r
        assert r["source"] in ("fts5", "semantic", "hybrid")


def test_hybrid_empty_query(invoke_db):
    """Empty query returns usage."""
    out, err, code = invoke_db(["omx-db", "hybrid"])
    assert "Usage" in out or "error" in out


def test_hybrid_debug_flag(invoke_db):
    """--debug injects _debug key with FTS5+Semantic trace."""
    out, err, code = invoke_db(["omx-db", "hybrid", "SCF", "--json", "--debug"])
    assert code == 0
    data = json.loads(out)
    assert "_debug" in data
    assert any("FTS5" in l for l in data["_debug"])
    assert any("Semantic" in l for l in data["_debug"])


def test_hybrid_fusion_ordering(invoke_db):
    """Results sorted by descending score (RRF fusion)."""
    out, err, code = invoke_db(["omx-db", "hybrid", "SCF", "--json"])
    data = json.loads(out)
    scores = [r["score"] for r in data["results"]]
    assert scores == sorted(scores, reverse=True)
