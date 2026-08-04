"""OpenMX code-specific search adapters (FTS5 + semantic).

These implement the shared :class:`dft_utils.search.SearchBackend` protocol
so ``omx-db hybrid``/``rag`` fuse through the common orchestrator. The DB
connection details live in :mod:`omx_tools.db_conn`.
"""

from __future__ import annotations

import os
import sqlite3

from dft_utils import debug_log
from dft_utils.search import make_fts5_query

from .db_conn import DB_PATH


def _search_fts5(query: str) -> list[dict]:
    """Run FTS5 search and return results."""
    try:
        db = sqlite3.connect(str(DB_PATH))
        db.row_factory = sqlite3.Row
        fts_query = make_fts5_query(query)
        rows = db.execute("""
            SELECT sec_num, title, rank
            FROM sections_fts
            WHERE sections_fts MATCH ?
            ORDER BY rank
            LIMIT 30
        """, (fts_query,)).fetchall()
        db.close()
        return [{"sec_num": r["sec_num"], "title": r["title"], "rank": r["rank"]} for r in rows]
    except Exception as e:
        debug_log(f"  FTS5 error: {e}")
        return []


def _search_semantic(query: str) -> list[dict]:
    """Semantic search over section embeddings (kept for callers that need
    the raw ranked signal).  Uses the shared cosine helper so normalization
    and the dimension guard apply here too."""
    backend = _OmxSemanticBackend()
    return [
        {"sim": h.score, "sec_num": h.extra.get("sec_num", ""), "title": h.title}
        for h in backend.search(query, 30)
    ]


class _OmxFts5Backend:
    """FTS5 signal over ``sections_fts``."""

    name = "fts5"

    def search(self, query: str, top_k: int) -> list:
        from dft_utils.search import SearchHit

        rows = _search_fts5(query)
        debug_log(f"  FTS5: {len(rows)} hits")
        return [
            SearchHit(
                id=f"{r.get('sec_num') or ''}:{r['title']}",
                title=r["title"],
                score=0.0,
                source=self.name,
                extra={"sec_num": r.get("sec_num") or ""},
            )
            for r in rows[: top_k * 3]
        ]


class _OmxSemanticBackend:
    """Semantic signal over the ``section_embeddings`` table."""

    name = "semantic"

    def search(self, query: str, top_k: int) -> list:
        import numpy as np
        from dft_utils.embedding import EmbeddingDimError, cosine_row_scores, embed
        from dft_utils.search import SearchHit

        if not os.path.exists(DB_PATH):
            return []
        try:
            q = np.asarray(embed(query), dtype=np.float32)
        except EmbeddingDimError:
            raise
        except Exception:
            return []  # embedding backend unavailable -> degrade

        db = sqlite3.connect(str(DB_PATH))
        db.row_factory = sqlite3.Row
        rows = db.execute(
            "SELECT section_id, sec_num, title, embedding FROM section_embeddings"
        ).fetchall()
        db.close()
        if not rows:
            debug_log("  Semantic: 0 hits")
            return []

        embs = np.stack(
            [np.frombuffer(r["embedding"], dtype=np.float32) for r in rows]
        )
        secs = [r["sec_num"] for r in rows]
        titles = [r["title"] for r in rows]
        scores = cosine_row_scores(q, embs)
        order = np.argsort(-scores)
        debug_log(f"  Semantic: {len(rows)} hits")
        out = []
        for idx in order[: top_k * 3]:
            i = int(idx)
            out.append(
                SearchHit(
                    id=f"{secs[i] or ''}:{titles[i]}",
                    title=titles[i],
                    score=float(scores[i]),
                    source=self.name,
                    extra={"sec_num": secs[i] or ""},
                )
            )
        return out