"""Tests for dft_utils.embedding — unified embedding client."""

import numpy as np
import pytest


def test_embed_returns_list():
    """embed() returns a list of floats."""
    from dft_utils.embedding import embed
    v = embed("test query")
    assert isinstance(v, list)
    assert len(v) > 0
    assert all(isinstance(x, float) for x in v)


def test_embed_deterministic():
    """Same input produces same embedding (within tolerance)."""
    from dft_utils.embedding import embed
    v1 = embed("hello world")
    v2 = embed("hello world")
    assert len(v1) == len(v2)
    assert all(abs(a - b) < 1e-5 for a, b in zip(v1, v2))


def test_different_inputs_different_embeddings():
    """Different inputs produce different embeddings."""
    from dft_utils.embedding import embed
    v1 = embed("alpha")
    v2 = embed("beta")
    diff = sum(abs(a - b) for a, b in zip(v1, v2))
    assert diff > 0.01, f"embeddings too similar: diff={diff}"


def test_embed_batch():
    """embed_batch returns one vector per input."""
    from dft_utils.embedding import embed_batch
    texts = ["first", "second", "third"]
    vectors = embed_batch(texts)
    assert len(vectors) == 3
    assert len(vectors[0]) == len(vectors[1])
    assert len(vectors[0]) > 0


def test_embed_numpy():
    """embed_numpy returns float32 array of expected shape."""
    from dft_utils.embedding import embed_numpy
    texts = ["a", "b"]
    arr = embed_numpy(texts)
    assert isinstance(arr, np.ndarray)
    assert arr.dtype == np.float32
    assert arr.shape[0] == 2  # 2 texts
    assert arr.shape[1] > 0   # embedding dim
    # Vectors differ
    assert not np.allclose(arr[0], arr[1])


def test_available_backend():
    """available_backend returns a known backend name."""
    from dft_utils.embedding import available_backend, _EMBED_BACKEND
    # Trigger detection
    backend = available_backend()
    assert backend in ("ollama", "sentence_transformers", "none")


@pytest.mark.skipif(
    not __import__("importlib").util.find_spec("ollama"),
    reason="ollama not installed",
)
def test_ollama_backend_detected():
    """When Ollama is available, backend is 'ollama'."""
    from dft_utils.embedding import available_backend
    assert available_backend() == "ollama"
