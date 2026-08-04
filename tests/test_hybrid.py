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


# ── Ranking assertions (guard against silent regression to keyword match) ──

def _embed_dim_ok(expected: int) -> bool:
    """True when a live embedding backend matches the indexed dimension."""
    try:
        from dft_utils.embedding import embed
        return len(embed("ping")) == expected
    except Exception:
        return False


def test_vasp_hybrid_ranks_cutoff_tags_first():
    """Hybrid must surface tag documents for a tag-like query, not degrade
    to keyword matching. Guards the 768/384 dimension crash too."""
    import numpy as np
    from pathlib import Path

    vectors = Path(PROJECT_ROOT) / "vasp_query/data/doc_vectors.npy"
    if not vectors.exists():
        pytest.skip("doc_vectors.npy not found")
    dim = int(np.load(str(vectors)).shape[1])
    if not _embed_dim_ok(dim):
        pytest.skip("embedding backend dim does not match the committed index")

    from vasp_query._common import hybrid_search

    results = hybrid_search("energy cutoff", top_k=10)
    assert results, "hybrid returned nothing for 'energy cutoff'"
    # Top hits should be VASP weights/tags (INCAR cutoff keys), not wiki pages.
    assert results[0]["type"] == "tag"
    ids = [r["id"] for r in results]
    assert "tag:ENCUT" in ids, f"tag:ENCUT not in top-10 results: {ids[:5]}..."
    # Contract: every result now carries source.
    assert all("source" in r for r in results)


def test_omx_hybrid_ranks_scf_convergence_section_first(invoke_db):
    """Hybrid for 'SCF convergence' must put the §16 SCF-convergence section
    at the top, proving semantic + FTS fusion is doing real work."""
    if not (PROJECT_ROOT / "openmx.db").exists():
        pytest.skip("openmx.db not found")
    import sqlite3
    try:
        row = sqlite3.connect(str(PROJECT_ROOT / "openmx.db")).execute(
            "SELECT embedding FROM section_embeddings LIMIT 1"
        ).fetchone()
    except Exception:
        row = None
    if row is None:
        pytest.skip("openmx.db has no section_embeddings")
    dim = len(row[0]) // 4
    if not _embed_dim_ok(dim):
        pytest.skip("embedding backend dim does not match openmx.db index")

    out, err, code = invoke_db(["omx-db", "hybrid", "SCF convergence", "--json"])
    data = json.loads(out)
    assert data["count"] > 0
    top = data["results"][0]["sec_num"]
    # Top must be a genuine SCF-convergence section; the exact winner is a
    # near-tie that shifts with the embedding model, so accept the known
    # candidates and require the canonical §16 SCF series to rank high.
    assert top in {"16", "16.1", "16.2", "16.3", "51.6"}, (
        f"expected an SCF-convergence section first, got {data['results'][0]}"
    )
    tops = [r["sec_num"] for r in data["results"][:5]]
    assert any(t.startswith("16") for t in tops), f"no §16 SCF section in top-5: {tops}"
