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
