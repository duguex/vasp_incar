"""Tests for the shared hybrid-search orchestrator and embedding guards.

These use synthetic data only — no openmx.db, no live embedding model —
so they always run.
"""

import numpy as np
import pytest

from dft_utils.embedding import (
    EmbeddingDimError,
    cosine_row_scores,
    normalize_array,
    normalize_vector,
)
from dft_utils.search import SearchBackend, SearchHit, hybrid_search


# ── cosine_row_scores: normalization correctness ───────────────────────

class TestCosineRowScores:
    def test_unit_cosine_zero(self):
        # Orthogonal/near-orthogonal vectors should score ~0, not scaled by
        # row magnitude (which a raw dot product would bias).
        q = np.array([1.0, 0.0], dtype=np.float32)
        rows = np.array([[0.0, 1.0], [0.0, 10.0], [0.0, 100.0]], dtype=np.float32)
        scores = cosine_row_scores(q, rows)
        assert np.allclose(scores, 0.0, atol=1e-6)

    def test_aligned_scores_one_regardless_of_magnitude(self):
        q = np.array([1.0, 2.0], dtype=np.float32)
        rows = np.array([[1.0, 2.0], [10.0, 20.0], [50.0, 100.0]], dtype=np.float32)
        scores = cosine_row_scores(q, rows)
        # All parallel to q -> cosine ~1 despite very different norms.
        assert np.allclose(scores, 1.0, atol=1e-5)

    def test_ordering_matches_normalized_cosine(self):
        q = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        rows = np.array(
            [[3.0, 1.0, 0.0], [0.1, 0.0, 0.0], [1.0, 4.0, 2.0]], dtype=np.float32
        )
        got = cosine_row_scores(q, rows)
        expect = normalize_array(rows) @ normalize_vector(q)
        assert np.allclose(got, expect, atol=1e-5)

    def test_dimension_mismatch_raises(self):
        q = np.array([1.0, 2.0, 3.0, 4.0], dtype=np.float32)  # 4-d
        rows = np.zeros((5, 768), dtype=np.float32)            # 768-d
        with pytest.raises(EmbeddingDimError):
            cosine_row_scores(q, rows)

    def test_empty_rows_ok(self):
        q = np.array([1.0, 0.0], dtype=np.float32)
        rows = np.zeros((3, 2), dtype=np.float32)  # zero-norm rows stay zero
        scores = cosine_row_scores(q, rows)
        assert np.allclose(scores, 0.0)
        assert not np.isnan(scores).any()


# ── normalize helpers ──────────────────────────────────────────────────

class TestNormalize:
    def test_rows_unit_norm(self):
        rows = np.array([[3.0, 4.0], [0.0, 0.0]], dtype=np.float32)
        out = normalize_array(rows)
        assert np.allclose(np.linalg.norm(out[0]), 1.0)
        assert np.allclose(out[1], 0.0)  # zero row not NaN

    def test_vector_unit_norm(self):
        v = normalize_vector(np.array([3.0, 4.0]))
        assert np.allclose(np.linalg.norm(v), 1.0)


# ── shared hybrid_search orchestrator ──────────────────────────────────

class _FakeBackend:
    """Bare backends for orchestrator tests; satisfy SearchBackend by shape."""

    def __init__(self, name, ids, order, extra=None):
        self.name = name
        self._ids = ids
        self._order = order
        self._extra = extra or {}

    def search(self, query, top_k):
        pool = self._ids[: top_k * 3]
        seen = 0
        out = []
        for doc_id in pool:
            out.append(
                SearchHit(
                    id=doc_id,
                    title=doc_id,
                    score=0.0,
                    source=self.name,
                    extra={"type": "fake", **self._extra.get(doc_id, {})},
                )
            )
        return out


class TestOrchestrator:
    def test_protocol_accepts_backends(self):
        b = _FakeBackend("fts5", ["a", "b", "c"], 0)
        assert isinstance(b, SearchBackend)

    def test_single_backend_ordering_preserved(self):
        b = _FakeBackend("semantic", ["x", "y", "z"], 0)
        hits = hybrid_search("q", [b], top_k=3)
        assert [h.id for h in hits] == ["x", "y", "z"]
        assert all(h.source == "semantic" for h in hits)

    def test_overlap_rises_via_rrf(self):
        # Both backends rank 'a' highly -> fused 'a' should be first.
        fts = _FakeBackend("fts5", ["a", "b", "c", "d", "e", "f", "g"], 0)
        sem = _FakeBackend("semantic", ["a", "h", "i", "j", "k", "l", "m"], 0)
        hits = hybrid_search("q", [fts, sem], top_k=3)
        assert hits[0].id == "a"
        assert hits[0].source == "hybrid"

    def test_weights_tune_fusion(self):
        # With a large weight on fts5, fts's rank-2 'b' beats semantic's rank-1.
        fts = _FakeBackend("fts5", ["a", "b"], 0)
        sem = _FakeBackend("semantic", ["z", "y", "x", "w", "v", "u", "t"], 0)
        hits = hybrid_search(
            "q", [fts, sem], top_k=2, weights={"fts5": 5.0, "semantic": 0.2}
        )
        assert hits[0].id == "a"
        assert hits[1].id == "b"

    def test_no_backends_returns_empty(self):
        assert hybrid_search("q", []) == []

    def test_all_backends_empty_returns_empty(self):
        class _Empty:
            name = "e"

            def search(self, query, top_k):
                return []

        assert hybrid_search("q", [_Empty()]) == []