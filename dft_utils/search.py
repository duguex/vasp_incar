"""Search helpers — keyword matching, FTS5 query construction, and the
shared hybrid-search orchestrator.

``hybrid_search`` is the single fusion point used by every code adapter
(VASP, OpenMX, ...). Each code supplies :class:`SearchBackend` adapters
that return ranked hits; this module fuses them via Reciprocal Rank Fusion
and emits a canonical :class:`SearchHit` shape.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, Sequence, runtime_checkable


def match_keyword(kw: str, text: str) -> bool:
    """Match keyword against text using word-level matching."""
    if kw in text:
        return True
    words = re.findall(r'[a-z]+', kw.lower())
    if words and len(words) > 1:
        return all(w in text for w in words)
    return False


def score_keyword(kw: str, text: str) -> int:
    """Score relevance of keyword match (0-100)."""
    if kw.lower() == text.lower():
        return 100
    if kw.lower() in text.lower():
        return 50
    words = re.findall(r'[a-z]+', kw.lower())
    if words and len(words) > 1:
        matched = sum(1 for w in words if w in text.lower())
        if matched == len(words):
            return 70
        return matched * 10
    return 0


def make_fts5_query(keyword: str) -> str:
    """Build a safe FTS5 MATCH query from plain-text keyword.

    Special characters (+ - * etc.) are stripped so they are not
    interpreted as FTS5 operators.  Known compound terms are expanded
    into phrase queries for better token matching.
    Words are OR-combined for best-match BM25 ranking.
    """
    kw = keyword.lower().strip()
    if not kw:
        return ""

    # Pre-process known compound patterns (before special-char stripping)
    _PHRASES: dict[str, str] = {
        "dft+u": "hubbard",
        "dft_u": "hubbard",
    }
    for pattern, replacement in _PHRASES.items():
        kw = kw.replace(pattern, replacement)

    # Strip FTS5 special chars that act as operators
    kw = re.sub(r'[+\-*()\[\]{}^~:!<>@#?]', ' ', kw)

    # Expand compound words for FTS5 hyphenated indexing
    _COMPOUNDS: dict[str, str] = {
        "kpoint": "k point",
        "kpoints": "k point",
        "kgrid": "k grid",
        "kpath": "k path",
    }
    tokens = kw.split()
    expanded: list[str] = []
    for tok in tokens:
        if tok in _COMPOUNDS:
            expanded.append(_COMPOUNDS[tok])
        else:
            expanded.append(tok)

    if not expanded:
        return ""

    return " OR ".join(
        f'"{w}"' if " " in w else w
        for w in expanded
    )


# ── RRF fusion ────────────────────────────────────────────────────────

def rrf_merge(
    signals: list[tuple[list[dict], str, float]],
    key_fn,
    top_k: int = 10,
    rrf_k: int = 60,
) -> list[dict]:
    """Fuse multiple ranked result lists via Reciprocal Rank Fusion.

    Args:
        signals: Each entry is ``(results, source_name, weight)``.
                 Results must be ranked best-to-worst.
        key_fn:  Callable(result_dict) → hashable merge key.
        top_k:   Number of results to return.
        rrf_k:   RRF constant (higher = more weight to top ranks).

    Returns:
        List of dicts with keys: ``score``, ``source``, plus any
        keys from the first signal's result dicts.
    """
    merged: dict[str, dict] = {}

    for results, source, weight in signals:
        for rank, entry in enumerate(results):
            key = key_fn(entry)
            rrf = weight / (rrf_k + rank)
            if key in merged:
                merged[key]["score"] += rrf
                if merged[key]["source"] != source:
                    merged[key]["source"] = "hybrid"
            else:
                merged[key] = dict(entry)
                merged[key]["score"] = rrf
                merged[key]["source"] = source

    ranked = sorted(merged.values(), key=lambda x: -x["score"])[:top_k]
    for r in ranked:
        r["score"] = round(r["score"], 4)
    return ranked


# ── Shared hybrid orchestrator ────────────────────────────────────────


@dataclass(frozen=True)
class SearchHit:
    """Canonical hybrid-search result shared by every code adapter.

    ``extra`` carries code-specific fields (e.g. ``sec_num``, ``tag``,
    ``type``) without widening this interface.
    """

    id: str
    title: str
    score: float
    source: str  # "fts5"|"bm25"|"semantic"|"tag"|... or "hybrid" when fused
    extra: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class SearchBackend(Protocol):
    """A single retrieval signal (FTS5, BM25, semantic, tag-only, ...).

    ``search`` must return hits ranked best-to-worst.
    """

    name: str

    def search(self, query: str, top_k: int) -> list[SearchHit]: ...


def _hit_id(hit: SearchHit) -> str:
    return hit.id


def _hit_to_dict(hit: SearchHit) -> dict[str, Any]:
    d: dict[str, Any] = {"id": hit.id, "title": hit.title, "source": hit.source}
    d.update(hit.extra)
    return d


def hybrid_search(
    query: str,
    backends: Sequence[SearchBackend],
    top_k: int = 10,
    weights: dict[str, float] | None = None,
    key_fn: Callable[[SearchHit], Any] = _hit_id,
) -> list[SearchHit]:
    """Fuse several ranked backends via RRF and normalize to :class:`SearchHit`.

    Args:
        query:     The user query string.
        backends:  One or more search signals, ranked best-to-worst.
        top_k:     Number of fused hits to return.
        weights:   Per-backend-name RRF weight. Defaults to 1.0 each.
        key_fn:    Merge key for a hit (defaults to ``hit.id``).

    Each backend is polled for ``top_k * 3`` candidates, then fused through
    :func:`rrf_merge` so the highest-ranked overlapping hits rise.
    """
    weights = weights or {}
    signals: list[tuple[list[dict], str, float]] = []
    for backend in backends:
        if backend is None:
            continue
        name = backend.name
        hits = backend.search(query, top_k * 3)
        if not hits:
            continue
        signals.append(
            ([_hit_to_dict(h) for h in hits], name, weights.get(name, 1.0))
        )

    if not signals:
        return []

    fused = rrf_merge(signals, key_fn=lambda d: d.get("id", d), top_k=top_k)

    results: list[SearchHit] = []
    for item in fused:
        item_id = item.get("id", "")
        title = item.get("title", item_id)
        source = item.get("source", "hybrid")
        extra_keys = [k for k in item if k not in ("id", "title", "score", "source")]
        results.append(
            SearchHit(
                id=item_id,
                title=title,
                score=float(item["score"]),
                source=source,
                extra={k: item[k] for k in extra_keys},
            )
        )
    return results
