"""omx-db — OpenMX manual database query tool.

Cross-pollination features ported from vasp_incar:
  - Hybrid search (FTS5 + semantic → RRF)          (Issue 1)
  - Alias/term mapping                              (Issue 2)
  - --debug flag for search/hybrid                  (Issue 3)
  - Pydantic data models                            (Issue 4)
  - Error suggestion field                          (Issue 5)
  - Data version envelope (meta table)              (Issue 6)
"""
import json
import re
import os
import sqlite3
import sys
import textwrap
from pathlib import Path
from pydantic import BaseModel

PKG_DIR = Path(__file__).resolve().parent
SCHEMA_PATH = PKG_DIR / "schemas" / "keywords.json"
_default_db = Path(os.environ.get("OPENMX_DB_PATH", str(PKG_DIR.parent / "openmx.db")))
DB_PATH = _default_db.resolve()
ALIASES_PATH = PKG_DIR.parent / "aliases.json"

# ── Data version ───────────────────────────────────────────────────────

from dft_utils import DATA_VERSION, debug_log, get_debug_log, clear_debug_log
from dft_utils.search import make_fts5_query


# ── Pydantic models (Issue 4) ──────────────────────────────────────────

class SearchResult(BaseModel):
    sec_num: str | None = None
    title: str
    rank: float
    snippet: str = ""


class SearchResponse(BaseModel):
    results: list[SearchResult] = []
    count: int = 0
    query: str = ""
    _debug: list[str] | None = None


class HybridResult(BaseModel):
    sec_num: str | None = None
    title: str
    score: float
    source: str  # "fts5" | "semantic" | "hybrid"


class HybridResponse(BaseModel):
    results: list[HybridResult] = []
    count: int = 0
    query: str = ""
    _debug: list[str] | None = None


class KeywordEntry(BaseModel):
    keyword: str | None = None
    sec_num: str | None = None
    title: str | None = None


class SectionEntry(BaseModel):
    sec_num: str
    title: str
    depth: int = 1
    file: str | None = None
    content: str | None = None


class ErrorResponse(BaseModel):
    error: str
    suggestion: str = ""


class SectionSuggestions(BaseModel):
    error: str
    suggestion: str = ""
    suggestions: list[dict] = []




# ── Alias / term mapping (Issue 2) ────────────────────────────────────

# Built-in fallback for common abbreviations
_BUILTIN_ALIASES: dict[str, str] = {
    "diis": "Rmm-Diis",
    "diisk": "Rmm-Diisk",
    "kerker": "Rmm-Diisk",
    "pbe": "GGA-PBE",
    "pbesol": "GGA-PBEsol",
    "revpbe": "GGA-revPBE",
    "lda": "LDA",
    "lda-pw": "LDA-PW",
    "lda-ca": "LDA-CA",
    "hse": "HSE",
    "hse06": "HSE",
    "pbe0": "PBE0",
    "b3lyp": "B3LYP",
    "scissor": "scissor",
    "kgrid": "scf.Kgrid",
    "kpoints": "scf.Kgrid",
    "energy cutoff": "scf.energycutoff",
    "cutoff": "scf.energycutoff",
}

_ALIASES_CACHE: dict[str, str] | None = None


def load_aliases() -> dict[str, str]:
    """Load alias map: user file (aliases.json) merged on top of built-in fallback."""
    global _ALIASES_CACHE
    if _ALIASES_CACHE is not None:
        return _ALIASES_CACHE
    merged = dict(_BUILTIN_ALIASES)
    if ALIASES_PATH.exists():
        try:
            user = json.loads(ALIASES_PATH.read_text())
            if isinstance(user, dict):
                merged.update(user)
        except (json.JSONDecodeError, OSError):
            pass
    _ALIASES_CACHE = merged
    return merged


def resolve_alias(input: str) -> str:
    """Resolve input through alias map, returning the canonical keyword name or the original."""
    aliases = load_aliases()
    return aliases.get(input.lower(), input)


# ── Version check (Issue 6) ────────────────────────────────────────────

def check_version(db) -> bool:
    """Check the meta table version vs code version. Returns True if match or unavailable."""
    try:
        row = db.execute("SELECT value FROM meta WHERE key='version'").fetchone()
        if row and row["value"] != DATA_VERSION:
            debug_log(f"  DB version mismatch: db={row['value']} code={DATA_VERSION}")
        return True
    except Exception:
        return True  # no meta table yet


# ── Database ───────────────────────────────────────────────────────────

def strip_ansi(text):
    """Strip ANSI escape sequences from text."""
    return re.sub(r'\x1b\[[0-9;]*m', '', text)


def get_db():
    if not os.path.exists(DB_PATH):
        print(f"Error: database not found at {DB_PATH}", file=sys.stderr)
        print("  Set OPENMX_DB_PATH to the correct openmx.db path.", file=sys.stderr)
        sys.exit(1)
    db = sqlite3.connect(str(DB_PATH))
    db.row_factory = sqlite3.Row
    check_version(db)
    return db


# ── FTS5 search ────────────────────────────────────────────────────────

def cmd_search(args, json_output=False):
    query = " ".join(args)
    if not query:
        if json_output:
            print(json.dumps({"error": "No query provided", "suggestion": "Pass a search term like 'omx-db search scf convergence'."}))
        else:
            print("Usage: omx-db search <query>")
        return

    # Resolve alias (Issue 2)
    resolved = resolve_alias(query)
    if resolved != query:
        search_query = resolved
        debug_log(f"  alias: '{query}' -> '{resolved}'")
    else:
        search_query = query
    db = get_db()

    fts_query = make_fts5_query(search_query)
    rows = db.execute("""
        SELECT rowid, sec_num, title, rank,
               snippet(sections_fts, 2, '\033[33m', '\033[0m', '...', 50) AS ctx
        FROM sections_fts
        WHERE sections_fts MATCH ?
        ORDER BY rank
        LIMIT 20
    """, (fts_query,)).fetchall()
    if not rows:
        if json_output:
            resp = {"results": [], "count": 0, "query": query}
            if get_debug_log():
                resp["_debug"] = get_debug_log()
            print(json.dumps(resp))
        else:
            print(f"No results for: {query}")
        db.close()
        return
    if json_output:
        resp = {
            "results": [
                {"sec_num": r["sec_num"], "title": r["title"],
                 "rank": r["rank"], "snippet": strip_ansi(r["ctx"])}
                for r in rows
            ],
            "count": len(rows),
            "query": query,
        }
        if get_debug_log():
            resp["_debug"] = get_debug_log()
        print(json.dumps(resp, indent=2, ensure_ascii=False))
    else:
        print(f'\033[32m🔍 {len(rows)} results for "{query}"\033[0m\n')
        for r in rows:
            sec = f'§{r["sec_num"]}' if r["sec_num"] else ""
            print(f'  \033[36m{sec:>12s}\033[0m  \033[1m{r["title"]}\033[0m')
            print(f'  {r["ctx"]}')
            print()
    db.close()
    clear_debug_log()


# ── Hybrid search (FTS5 + semantic → RRF) (Issue 1) ───────────────────

def cmd_hybrid(args, json_output=False):
    """Hybrid search: FTS5 + semantic embeddings fused via Reciprocal Rank Fusion."""
    query = " ".join(args)
    if not query:
        if json_output:
            print(json.dumps({"error": "No query provided", "suggestion": "Pass a search term like 'omx-db hybrid scf convergence'."}))
        else:
            print("Usage: omx-db hybrid <query>")
        return

    debug_flag = False
    if "--debug" in query:
        debug_flag = True
        args = [a for a in args if a != "--debug"]
        query = " ".join(args)

    clear_debug_log()
    debug_log(f"hybrid_search(query={query!r})")

    # Step 1+2+3: FTS5 + semantic signals fused by the shared orchestrator.
    from dft_utils.embedding import EmbeddingDimError
    from dft_utils.search import hybrid_search as _shared_hybrid

    backends = []
    if os.path.exists(DB_PATH):
        backends.append(_OmxFts5Backend())
        backends.append(_OmxSemanticBackend())

    try:
        hits = _shared_hybrid(
            query,
            backends,
            top_k=20,
            weights={"fts5": 2.0, "semantic": 0.5},
        )
    except EmbeddingDimError as exc:
        resp = {"error": str(exc), "results": [], "count": 0, "query": query}
        if debug_flag or get_debug_log():
            resp["_debug"] = get_debug_log()
        if json_output:
            print(json.dumps(resp, indent=2, ensure_ascii=False))
        else:
            print(f"⚠ Embedding dimension mismatch: {exc}")
        return

    ranked = [
        {
            "sec_num": h.extra.get("sec_num", ""),
            "title": h.title,
            "score": h.score,
            "source": h.source,
        }
        for h in hits
    ]

    if not ranked:
        resp = {"results": [], "count": 0, "query": query}
        if debug_flag or get_debug_log():
            resp["_debug"] = get_debug_log()
        if json_output:
            print(json.dumps(resp))
        else:
            print(f"No results for: {query}")
        return

    if json_output:
        resp = {
            "results": ranked,
            "count": len(ranked),
            "query": query,
        }
        if debug_flag or get_debug_log():
            resp["_debug"] = get_debug_log()
        print(json.dumps(resp, indent=2, ensure_ascii=False))
    else:
        print(f'\033[32m🔍 Hybrid: {len(ranked)} results for "{query}"\033[0m\n')
        for r in ranked:
            sec = f'§{r["sec_num"]}' if r["sec_num"] else ""
            source_tag = "F+S" if r["source"] == "hybrid" else ("F" if r["source"] == "fts5" else "S")
            print(f'  \033[36m{sec:>12s}\033[0m  \033[1m{r["title"]}\033[0m  [{source_tag}]')
            print(f'    score={r["score"]:.4f}')
            print()

    clear_debug_log()


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
        import sqlite3 as _sq
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

        db = _sq.connect(str(DB_PATH))
        db.row_factory = _sq.Row
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


# ── Keyword lookup ─────────────────────────────────────────────────────

def cmd_keyword(args, json_output=False):
    keyword = " ".join(args)
    if not keyword:
        if json_output:
            print(json.dumps({"error": "No keyword provided", "suggestion": "Pass a keyword name like 'omx-db keyword scf.Kgrid'."}))
        else:
            print("Usage: omx-db keyword <keyword>")
        return

    # Resolve alias (Issue 2)
    resolved = resolve_alias(keyword)
    if resolved != keyword:
        search_key = resolved
    else:
        search_key = keyword

    # Try exact schema match first
    schema_path = PKG_DIR / "schemas" / "keywords.json"
    if schema_path.exists():
        schema = json.loads(schema_path.read_text())
        if isinstance(schema, dict):
            if search_key in schema:
                entry = schema[search_key]
                entry.setdefault("keyword", search_key)
                entry["_resolved_from"] = keyword if resolved != keyword else keyword
                if json_output:
                    print(json.dumps(entry, indent=2, ensure_ascii=False))
                else:
                    print(f"{'keyword':.<20s} {search_key}")
                    print(f"{'type':.<20s} {entry.get('type', 'null')}")
                    print(f"{'default':.<20s} {json.dumps(entry.get('default'))}")
                    print(f"{'unit':.<20s} {json.dumps(entry.get('unit'))}")
                    print(f"{'section':.<20s} {entry.get('section', 'null')}")
                    desc = entry.get('description', '')
                    if desc:
                        print(f"\n{desc[:300]}")
                return
            # Also try lower-case alias match
            if search_key.lower() in {k.lower(): k for k in schema}:
                canonical = {k.lower(): k for k in schema}[search_key.lower()]
                entry = schema[canical]
                entry.setdefault("keyword", canonical)
                if json_output:
                    print(json.dumps(entry, indent=2, ensure_ascii=False))
                else:
                    print(f"{'keyword':.<20s} {canical}")
                    print(f"{'type':.<20s} {entry.get('type', 'null')}")
                    print(f"{'default':.<20s} {json.dumps(entry.get('default'))}")
                return

    # Fall back to DB index search
    db = get_db()

    keyword_pattern = f"%{search_key}%"
    rows = db.execute("""
        SELECT ie.keyword, ie.section_ref,
               s.sec_num, s.title
        FROM index_entries ie
        LEFT JOIN sections s ON s.sec_num = REPLACE(ie.section_ref, '\u00a7', '')
        WHERE ie.keyword LIKE ?
        ORDER BY ie.keyword
        LIMIT 20
    """, (keyword_pattern,)).fetchall()

    if not rows:
        if json_output:
            resp = {"error": f"Keyword '{keyword}' not found", "suggestion": "Try 'omx-db list' to see available sections, then browse for keywords manually."}
            print(json.dumps(resp))
        else:
            print(f"No results for keyword: {keyword}")
        db.close()
        return

    if json_output:
        print(json.dumps({
            "results": [{"keyword": r["keyword"], "sec_num": r["sec_num"],
                         "title": r["title"]} for r in rows],
            "count": len(rows),
        }, indent=2, ensure_ascii=False))
    else:
        print(f'\033[32m\u270d {len(rows)} keyword results for "{keyword}"\033[0m\n')
        for r in rows:
            sec = f'\u00a7{r["sec_num"]}' if r["sec_num"] else ""
            print(f'  \033[36m{sec:>12s}\033[0m  {r["keyword"]:.<25s} {r["title"]}')
    db.close()


# ── Section reader ─────────────────────────────────────────────────────

def cmd_section(args, json_output=False):
    num = " ".join(args)
    if not num:
        if json_output:
            print(json.dumps({"error": "No section number provided", "suggestion": "Pass a section number like 'omx-db section 16' or 'omx-db section 8.2'."}))
        else:
            print("Usage: omx-db section <num>")
        return
    db = get_db()
    # Try exact, then prefix
    row = db.execute("SELECT * FROM sections WHERE sec_num = ?", (num,)).fetchone()
    if not row:
        row = db.execute("SELECT * FROM sections WHERE sec_num LIKE ? ORDER BY length(sec_num) LIMIT 1", (f"{num}.%",)).fetchone()
    if not row:
        # Suggest similar sections
        suggestions = db.execute("SELECT sec_num, title FROM sections WHERE sec_num LIKE ? OR title LIKE ? LIMIT 5",
                                 (f"%{num}%", f"%{num}%")).fetchall()
        if json_output:
            resp = {"error": f"Section not found: {num}", "suggestion": "Use 'omx-db list' to browse all sections."}
            resp["suggestions"] = [{"sec_num": s["sec_num"], "title": s["title"]} for s in suggestions] if suggestions else []
            print(json.dumps(resp, indent=2, ensure_ascii=False))
        else:
            print(f"Section not found: {num}")
            if suggestions:
                print("\nDid you mean?")
                for s in suggestions:
                    print(f"  §{s['sec_num']:>8s}  {s['title']}")
        db.close()
        return
    file_path = row["file_path"]
    content = ""
    if file_path:
        fp = PKG_DIR.parent / "openmx4.0_manual" / file_path
        if fp.exists():
            content = fp.read_text(encoding="utf-8", errors="replace")[:2000]
    if json_output:
        print(json.dumps({
            "sec_num": row["sec_num"],
            "title": row["title"],
            "file": file_path,
            "depth": row["depth"],
            "content": content,
        }, indent=2, ensure_ascii=False))
    else:
        print(f'\033[36m§{row["sec_num"]}\033[0m  \033[1m{row["title"]}\033[0m')
        if file_path:
            print(f'  \033[2m{file_path}\033[0m')
        if content:
            clean = re.sub(r'<[^>]+>', '', content[:1200])
            print(f'\n{clean[:800]}')
    db.close()


# ── List sections ──────────────────────────────────────────────────────

def cmd_list(args, json_output=False):
    db = get_db()
    rows = db.execute("SELECT sec_num, title, COALESCE(depth, 1) AS depth FROM sections ORDER BY sec_num").fetchall()
    if not rows:
        if json_output:
            print(json.dumps({"error": "No sections found", "suggestion": "The database may be empty."}))
        else:
            print("No sections found in the database.")
        db.close()
        return
    if json_output:
        print(json.dumps({
            "sections": [{"sec_num": r["sec_num"], "title": r["title"], "depth": r["depth"]} for r in rows]
        }, indent=2, ensure_ascii=False))
    else:
        for r in rows:
            indent = "  " * (min(r["depth"], 3) - 1)
            print(f'{indent}\033[36m§{r["sec_num"]:>8s}\033[0m  {r["title"]}')
    db.close()


# ── File inventory ─────────────────────────────────────────────────────

def cmd_files(args, json_output=False):
    file_type = None
    if args and args[0] in ("--type", "-t"):
        if len(args) > 1:
            file_type = args[1]
        args = args[2:]
    db = get_db()
    if file_type:
        rows = db.execute(
            "SELECT path, file_type, category, size_bytes FROM files WHERE file_type = ? ORDER BY path",
            (file_type,)
        ).fetchall()
    else:
        rows = db.execute("SELECT path, file_type, category, size_bytes FROM files ORDER BY path").fetchall()
    if json_output:
        resp = {
            "files": [{"path": r["path"], "type": r["file_type"],
                        "category": r["category"], "size_bytes": r["size_bytes"]}
                      for r in rows]
        }
        print(json.dumps(resp, indent=2, ensure_ascii=False))
    else:
        print(f"Files ({len(rows)} total):")
        for r in rows:
            print(f"  [{r['file_type']:>4s}] {r['path']}")
    db.close()
# ── Database stats ─────────────────────────────────────────────────────

def cmd_stats(args, json_output=False):
    """DB table stats, or example-corpus stats with --examples."""
    # omx-db stats --examples [keyword]
    if "--examples" in args or "-e" in args:
        rest = [a for a in args if a not in ("--examples", "-e")]
        keyword = " ".join(rest).strip() or None
        try:
            from omx_tools.examples_corpus import example_stats, load_index
            records = load_index()
            resp = example_stats(records, keyword=keyword)
        except FileNotFoundError as e:
            resp = {
                "error": str(e),
                "suggestion": (
                    "python3 scripts/index_omx_examples.py "
                    "--root ~/openmx_container/openmx4.0/work "
                    "--out data/omx_examples"
                ),
            }
            print(json.dumps(resp, indent=2, ensure_ascii=False) if json_output else resp["error"])
            return
        if json_output:
            print(json.dumps(resp, indent=2, ensure_ascii=False))
        else:
            print(f"Example corpus statistics (total={resp.get('total_examples', 0)})")
            if keyword:
                print(f"  keyword: {resp.get('keyword')}  count={resp.get('count')}  "
                      f"({resp.get('frequency_pct')}%)")
                for v in resp.get("top_values") or []:
                    print(f"    {v['value']}: {v['count']}")
            else:
                for row in (resp.get("top_keywords") or [])[:20]:
                    print(f"  {row['keyword']:<28s} {row['count']:>5d}  ({row['frequency_pct']}%)")
        return

    db = get_db()
    tables = {}
    for t in ("sections", "index_entries", "section_embeddings", "meta"):
        try:
            row = db.execute(f"SELECT COUNT(*) AS c FROM {t}").fetchone()
            tables[t] = row["c"]
        except Exception:
            pass
    files_by_cat = {}
    files_by_type = {}
    try:
        rows = db.execute(
            "SELECT category, file_type, COUNT(*) AS c FROM files "
            "GROUP BY category, file_type"
        ).fetchall()
        for r in rows:
            files_by_cat[r["category"]] = files_by_cat.get(r["category"], 0) + r["c"]
            files_by_type[r["file_type"]] = files_by_type.get(r["file_type"], 0) + r["c"]
    except Exception:
        pass
    db_size = os.path.getsize(DB_PATH) / (1024 * 1024) if os.path.exists(DB_PATH) else 0

    version_info = {}
    try:
        vrow = db.execute("SELECT value FROM meta WHERE key='version'").fetchone()
        if vrow:
            version_info["version"] = vrow["value"]
    except Exception:
        pass

    if json_output:
        resp = {
            "tables": tables,
            "files_by_category": files_by_cat,
            "files_by_type": files_by_type,
            "db_size_mb": round(db_size, 1),
        }
        if version_info:
            resp["version"] = version_info
        print(json.dumps(resp, indent=2, ensure_ascii=False))
    else:
        print("Database statistics:")
        for name, count in sorted(tables.items()):
            print(f"  {name}: {count}")
        for cat, count in sorted(files_by_cat.items()):
            print(f"  files ({cat}): {count}")
        print(f"  db_size: {round(db_size, 1)} MB")
        if version_info:
            print(f"  version: {version_info['version']}")
    db.close()


def _corpus_error(exc: Exception, json_output: bool) -> None:
    resp = {
        "error": str(exc),
        "suggestion": (
            "python3 scripts/index_omx_examples.py "
            "--root ~/openmx_container/openmx4.0/work --out data/omx_examples"
        ),
    }
    if json_output:
        print(json.dumps(resp, indent=2, ensure_ascii=False))
    else:
        print(resp["error"])
        print(f"  suggestion: {resp['suggestion']}")


def cmd_example(args, json_output=False):
    """Search official OpenMX example .dat corpus."""
    intent = None
    keyword = None
    query_parts: list[str] = []
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("--intent", "-t") and i + 1 < len(args):
            intent = args[i + 1]
            i += 2
            continue
        if a in ("--keyword", "-k") and i + 1 < len(args):
            keyword = args[i + 1]
            i += 2
            continue
        if a.startswith("--intent="):
            intent = a.split("=", 1)[1]
            i += 1
            continue
        if a.startswith("--keyword="):
            keyword = a.split("=", 1)[1]
            i += 1
            continue
        query_parts.append(a)
        i += 1
    query = " ".join(query_parts).strip() or None

    if not query and not intent and not keyword:
        msg = {
            "error": "No query provided",
            "suggestion": (
                "omx-db example Kerker --json | "
                "omx-db example --intent geom_opt --json | "
                "omx-db example --keyword scf.Mixing.Type --json"
            ),
        }
        print(json.dumps(msg, indent=2, ensure_ascii=False) if json_output else msg["error"])
        return

    try:
        from omx_tools.examples_corpus import load_index, search_examples
        records = load_index()
        results = search_examples(
            records, query=query, intent=intent, keyword=keyword,
        )
    except FileNotFoundError as e:
        _corpus_error(e, json_output)
        return

    resp = {
        "query": query,
        "intent": intent,
        "keyword": keyword,
        "count": len(results),
        "results": results,
        "corpus": "official OpenMX work/ examples (not multi-user INCAR-scale)",
    }
    if json_output:
        print(json.dumps(resp, indent=2, ensure_ascii=False))
    else:
        print(f'📂 {len(results)} examples  query={query!r} intent={intent!r}')
        for r in results:
            print(f"  [{r.get('intent', '?'):<8s}] {r.get('id')}")
            if r.get("matches"):
                print(f"             matches: {', '.join(r['matches'][:6])}")


def cmd_cooccur(args, json_output=False):
    """Keyword co-occurrence across official example .dat files."""
    toks = [a for a in args if not a.startswith("-")]
    if len(toks) < 2:
        msg = {
            "error": "Need two keywords",
            "suggestion": "omx-db cooccur scf.Mixing.Type scf.Kerker.factor --json",
        }
        print(json.dumps(msg, indent=2, ensure_ascii=False) if json_output else msg["error"])
        return
    kw_a, kw_b = toks[0], toks[1]
    try:
        from omx_tools.examples_corpus import example_cooccur, load_index
        records = load_index()
        resp = example_cooccur(records, kw_a, kw_b)
    except FileNotFoundError as e:
        _corpus_error(e, json_output)
        return

    if json_output:
        print(json.dumps(resp, indent=2, ensure_ascii=False))
    else:
        print(f"Co-occurrence: {kw_a} × {kw_b}")
        print(f"  total_examples: {resp['total_examples']}")
        print(f"  count_a: {resp['count_a']} ({resp['frequency_a_pct']}%)")
        print(f"  count_b: {resp['count_b']} ({resp['frequency_b_pct']}%)")
        print(f"  cooccur: {resp['cooccur_count']} ({resp['cooccur_pct']}%)")
        for p in resp.get("top_pairs") or []:
            print(f"    {p['pair']}: {p['count']}")




# ── Related keywords / sections (CLI symmetry with vasp-query related) ─

def cmd_related(args, json_output=False):
    """Find related keywords or sibling sections for a query."""
    query = " ".join(args).strip()
    if not query:
        if json_output:
            print(json.dumps({
                "error": "No query provided",
                "suggestion": "Usage: omx-db related scf.Mixing.Type  OR  omx-db related 16",
            }))
        else:
            print("Usage: omx-db related <keyword|section>")
        return

    db = get_db()
    related: list[dict] = []
    seen: set[tuple[str, str]] = set()

    def _add(kind: str, rid: str, title: str, reason: str) -> None:
        key = (kind, str(rid))
        if key in seen or not rid:
            return
        seen.add(key)
        related.append({
            "kind": kind,
            "id": str(rid),
            "title": title or str(rid),
            "reason": reason,
        })

    q_clean = query.replace("§", "").strip()
    is_section_query = bool(re.match(r"^[\d]+(\.[\d]+)*$", q_clean))

    if is_section_query:
        sec = db.execute(
            "SELECT sec_num, title FROM sections WHERE sec_num = ? OR sec_num LIKE ? "
            "ORDER BY length(sec_num) LIMIT 1",
            (q_clean, f"{q_clean}.%"),
        ).fetchone()
        if sec:
            base = sec["sec_num"]
            parent = ".".join(base.split(".")[:-1]) if "." in base else ""
            if parent:
                rows = db.execute(
                    "SELECT sec_num, title FROM sections "
                    "WHERE sec_num LIKE ? AND sec_num != ? ORDER BY sec_num LIMIT 30",
                    (f"{parent}.%", base),
                ).fetchall()
                reason = "sibling_section"
            else:
                rows = db.execute(
                    "SELECT sec_num, title FROM sections "
                    "WHERE sec_num LIKE ? AND sec_num != ? ORDER BY sec_num LIMIT 30",
                    (f"{base}.%", base),
                ).fetchall()
                reason = "child_section"
            for r in rows:
                _add("section", r["sec_num"], r["title"], reason)
            krows = db.execute(
                "SELECT keyword FROM index_entries "
                "WHERE section_ref LIKE ? OR section_ref LIKE ? LIMIT 40",
                (f"%{base}%", f"%§{base}%"),
            ).fetchall()
            for r in krows:
                _add("keyword", r["keyword"], r["keyword"], "index")

    # Keyword path (also runs for non-section queries; for section queries as extra)
    schema: dict = {}
    schema_path = PKG_DIR / "schemas" / "keywords.json"
    if schema_path.exists():
        try:
            raw = json.loads(schema_path.read_text())
            if isinstance(raw, dict):
                schema = raw
        except Exception:
            schema = {}

    resolved = resolve_alias(query)
    entry = schema.get(resolved)
    if entry is None:
        lower_map = {k.lower(): k for k in schema}
        canon = lower_map.get(resolved.lower())
        if canon:
            resolved = canon
            entry = schema.get(resolved)

    if entry is not None:
        sec_ref = str(entry.get("section") or "")
        for k, v in schema.items():
            if k == resolved:
                continue
            if sec_ref and str(v.get("section") or "") == sec_ref:
                _add("keyword", k, k, "same_section")
        if sec_ref:
            _add("section", sec_ref, sec_ref, "keyword_section")
        krows = db.execute(
            "SELECT keyword FROM index_entries "
            "WHERE keyword LIKE ? OR section_ref LIKE ? LIMIT 40",
            (f"%{resolved}%", f"%{sec_ref}%"),
        ).fetchall()
        for r in krows:
            if r["keyword"] != resolved:
                _add("keyword", r["keyword"], r["keyword"], "index")

    if not related:
        rows = db.execute(
            "SELECT keyword FROM index_entries WHERE keyword LIKE ? LIMIT 20",
            (f"%{query}%",),
        ).fetchall()
        for r in rows:
            _add("keyword", r["keyword"], r["keyword"], "index")

    db.close()
    out: dict = {"query": query, "count": len(related), "related": related}
    if not related:
        out["suggestion"] = "Try omx-db list or omx-db keyword <name>"
    if json_output:
        print(json.dumps(out, indent=2, ensure_ascii=False))
    else:
        print(f'\033[32m🔗 {len(related)} related for "{query}"\033[0m\n')
        for r in related:
            print(f'  [{r["kind"]}] {r["id"]:<28s} {r["title"]}  ({r["reason"]})')



# ── Semantic / RAG search (existing, preserved) ────────────────────────

def cmd_rag(args, json_output=False):
    query = " ".join(args)
    if not query:
        if json_output:
            print(json.dumps({"error": "No query provided", "suggestion": "Pass a search term like 'omx-db rag scf convergence'."}))
        else:
            print("Usage: omx-db rag <query>")
        return

    try:
        from dft_utils.embedding import embed, cosine_row_scores
        import numpy as np
        import sqlite3

        if not json_output:
            print("\033[2mEmbedding query via Ollama...\033[0m", flush=True)

        q_vec = np.array([embed(query)], dtype=np.float32)

        db = sqlite3.connect(str(DB_PATH))
        db.row_factory = sqlite3.Row
        rows = db.execute(
            "SELECT section_id, sec_num, title, file_path, embedding FROM section_embeddings"
        ).fetchall()
        db.close()

        embs = np.stack(
            [np.frombuffer(r["embedding"], dtype=np.float32) for r in rows]
        )
        scores = cosine_row_scores(q_vec, embs)

        results = []
        for i, r in enumerate(rows):
            results.append(
                (float(scores[i]), r["sec_num"], r["title"], r["file_path"])
            )

        results.sort(reverse=True)
        hits = [{"sim": s, "sec_num": n, "title": t, "file": f}
                for s, n, t, f in results[:10]]

        if not hits:
            if json_output:
                print(json.dumps({"results": [], "count": 0}))
            else:
                print("No results.")
            return

        if json_output:
            print(json.dumps(hits, indent=2, ensure_ascii=False))
        else:
            print(f'\033[32m🔍 Top {len(hits)} RAG results for "{query}"\033[0m\n')
            for r in hits:
                sec = f'\u00a7{r["sec_num"]}' if r["sec_num"] else ""
                print(f'  \033[36m{sec:>12s}\033[0m  \033[1m{r["title"]}\033[0m  (sim={r["sim"]:.3f})')
            print('  \033[2m(embeddings via Ollama)\033[0m')

    except Exception as e:
        if json_output:
            print(json.dumps({"error": f"RAG search failed: {e}", "suggestion": "Check that Ollama is running and the database contains embeddings."}))
        else:
            print(f"RAG search failed: {e}")


# ── CLI dispatch ───────────────────────────────────────────────────────

def cli():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    use_json = "--json" in sys.argv
    if use_json:
        sys.argv = [a for a in sys.argv if a != "--json"]
    cmd = sys.argv[1]
    args = sys.argv[2:]
    cmds = {
        "rag": cmd_rag,
        "search": cmd_search,
        "hybrid": cmd_hybrid,
        "keyword": cmd_keyword,
        "tag": cmd_keyword,          # alias (CLI symmetry with vasp-query)
        "section": cmd_section,
        "fullwiki": cmd_section,     # alias
        "related": cmd_related,
        "list": cmd_list,
        "files": cmd_files,
        "stats": cmd_stats,
        "example": cmd_example,
        "examples": cmd_example,     # alias
        "cooccur": cmd_cooccur,
    }
    if cmd in cmds:
        cmds[cmd](args, json_output=use_json)
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)


if __name__ == "__main__":
    cli()
