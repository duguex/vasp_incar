"""Search helpers — keyword matching and FTS5 query construction."""

import re


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
    """Build a safe FTS5 MATCH query from a plain-text keyword.

    Each word is quoted to prevent FTS5 syntax injection.
    Words are OR-combined for best-match ranking.
    """
    return " OR ".join(
        f'"{w}"' if " " in w else w
        for w in keyword.split()
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
                 Results with the same key from different signals
                 have their scores accumulated.
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
