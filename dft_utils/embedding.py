"""Unified embedding client — Ollama primary, sentence-transformers fallback.

Both vasp_query and omx_tools use this module for semantic search,
ensuring a single model is shared across all processes.

Environment
-----------
OLLAMA_URL   : override default Ollama endpoint (default http://localhost:11434)
OLLAMA_MODEL : override embedding model   (default nomic-embed-text)
"""

from __future__ import annotations
import os
from typing import Any
# ── Config ────────────────────────────────────────────────────────────

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "nomic-embed-text")
EMBEDDING_DIM: int | None = None  # set after first call


class EmbeddingDimError(ValueError):
    """Query vector and indexed vectors are not the same dimension.

    Raised rather than silently degrading so a backend/model change never
    produces subtly-wrong rankings.
    """


# ── Backends ──────────────────────────────────────────────────────────

def _ollama_available() -> bool:
    """Check if the Ollama server is reachable."""
    try:
        import urllib.request
        req = urllib.request.Request(f"{OLLAMA_URL}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=2) as resp:
            return resp.status == 200
    except Exception:
        return False


def _embed_ollama(texts: list[str]) -> list[list[float]]:
    """Embed via local Ollama instance."""
    import ollama

    results: list[list[float]] = []
    for text in texts:
        r = ollama.embeddings(model=OLLAMA_MODEL, prompt=text)
        results.append(r["embedding"])
    return results


def _embed_sentence_transformers(texts: list[str]) -> list[list[float]]:
    """Embed via SentenceTransformer (in-process fallback)."""
    os.environ.setdefault("USE_TF", "0")
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer("BAAI/bge-small-en-v1.5")
    import numpy as np
    vecs = model.encode(texts, show_progress_bar=False)
    return vecs.tolist() if isinstance(vecs, np.ndarray) else list(vecs)


# ── Public API ────────────────────────────────────────────────────────

_EMBED_BACKEND: str | None = None


def embed(text: str) -> list[float]:
    """Embed a single text string.

    Returns a list of floats (dimension depends on model).
    """
    return embed_batch([text])[0]


def embed_batch(texts: list[str]) -> list[list[float]]:
    """Embed a list of texts.

    Returns ``list[list[float]]``, one embedding per input text.
    Uses Ollama if available, falls back to sentence-transformers.
    """
    global _EMBED_BACKEND, EMBEDDING_DIM

    if _EMBED_BACKEND is None:
        if _ollama_available():
            _EMBED_BACKEND = "ollama"
        else:
            _EMBED_BACKEND = "sentence_transformers"

    backend = _EMBED_BACKEND

    if backend == "ollama":
        results = _embed_ollama(texts)
    else:
        results = _embed_sentence_transformers(texts)

    if results and EMBEDDING_DIM is None:
        EMBEDDING_DIM = len(results[0])

    return results


def embed_numpy(texts: list[str]) -> "Any":
    """Embed texts and return a numpy array (for bulk indexing)."""
    import numpy as np
    vecs = embed_batch(texts)
    return np.array(vecs, dtype=np.float32)


def available_backend() -> str:
    """Return the active backend name ('ollama' or 'sentence_transformers')."""
    if _EMBED_BACKEND is None:
        embed("ping")
    return _EMBED_BACKEND or "none"


# ── Similarity helpers (shared by all code adapters) ──────────────────

def embedding_dim() -> int:
    """Dimension of the currently-active embedding backend.

    Trigger an embed if not yet known. Raises if no backend is available.
    """
    if EMBEDDING_DIM is None:
        embed("ping")
    if EMBEDDING_DIM is None:
        raise EmbeddingDimError("embedding backend unavailable; cannot determine dim")
    return EMBEDDING_DIM


def array_dim(rows: "Any") -> int:
    """Column dimension of a 2-D numpy array (rows x D)."""
    import numpy as np
    arr = np.asarray(rows)
    if arr.ndim != 2:
        raise EmbeddingDimError(f"expected 2-D [N, D] array, got shape {arr.shape}")
    return int(arr.shape[1])


def normalize_array(rows: "Any") -> "Any":
    """L2-normalize each row of a ``[N, D]`` array in place-safe manner.

    Zero-norm rows stay zero (avoids NaN). Returns a new array.
    """
    import numpy as np
    arr = np.asarray(rows, dtype=np.float32)
    if arr.ndim != 2:
        raise EmbeddingDimError(f"expected 2-D [N, D] array, got shape {arr.shape}")
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return arr / norms


def normalize_vector(v: "Any") -> "Any":
    """L2-normalize a single ``[D]`` vector."""
    import numpy as np
    vec = np.asarray(v, dtype=np.float32)
    norm = float(np.linalg.norm(vec))
    return vec / norm if norm > 0 else vec


def cosine_row_scores(query_vec: "Any", doc_rows: "Any") -> "Any":
    """Cosine similarity of ``query_vec`` against every row of ``doc_rows``.

    Guards that both sides share a dimension before any dot product, and
    L2-normalizes both sides so the result is a true cosine in ``[-1, 1]``.
    Raises :class:`EmbeddingDimError` on mismatch — never silently degrades.
    """
    import numpy as np
    q = np.asarray(query_vec, dtype=np.float32)
    docs = np.asarray(doc_rows, dtype=np.float32)
    if q.ndim == 1:
        q = q.reshape(1, -1)
    if q.ndim != 2 or docs.ndim != 2:
        raise EmbeddingDimError(
            f"expected 2-D query [{q.shape}] and docs [{docs.shape}]"
        )
    if q.shape[1] != docs.shape[1]:
        raise EmbeddingDimError(
            f"query dim {q.shape[1]} != indexed dim {docs.shape[1]}; "
            "embedding backend changed or index was built with a different model"
        )
    q_n = normalize_vector(q[0]).reshape(1, -1)
    docs_n = normalize_array(docs)
    return np.dot(docs_n, q_n.T).flatten()
