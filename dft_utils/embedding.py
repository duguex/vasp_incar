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
