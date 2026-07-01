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
import subprocess
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

    # Step 1: FTS5 search
    fts5_results = _search_fts5(query)
    debug_log(f"  FTS5: {len(fts5_results)} hits")

    # Step 2: Semantic search (subprocess, cached model)
    semantic_results = _search_semantic(query)
    debug_log(f"  Semantic: {len(semantic_results)} hits")

    # Step 3: RRF fusion via shared dft_utils
    from dft_utils.search import rrf_merge
    kw_key = lambda r: f"{r.get('sec_num', '')}:{r['title']}"
    signals = []
    if fts5_results:
        signals.append((fts5_results, "fts5", 1.0))
    if semantic_results:
        signals.append((semantic_results, "semantic", 1.0))
    ranked = rrf_merge(signals, key_fn=kw_key, top_k=20)

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
            "results": [
                {"sec_num": r["sec_num"], "title": r["title"],
                 "score": round(r["score"], 4), "source": r["source"]}
                for r in ranked
            ],
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
    """Run semantic search via subprocess (model cached after first call)."""
    if not os.path.exists(DB_PATH):
        return []
    env = os.environ.copy()
    env["HF_HUB_OFFLINE"] = "1"
    env["TRANSFORMERS_OFFLINE"] = "1"
    script = """
import os, sys, sqlite3, json, numpy as np
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
from sentence_transformers import SentenceTransformer
model = SentenceTransformer('BAAI/bge-small-en-v1.5', device='cpu')
q = sys.argv[1]
q_emb = model.encode(q, normalize_embeddings=True)
db = sqlite3.connect(sys.argv[2])
db.row_factory = sqlite3.Row
rows = db.execute('SELECT section_id, sec_num, title, file_path, embedding FROM section_embeddings').fetchall()
results = []
for r in rows:
    emb = np.frombuffer(r['embedding'], dtype=np.float32)
    sim = float(np.dot(q_emb, emb))
    results.append((sim, r['sec_num'], r['title']))
results.sort(reverse=True)
print(json.dumps([{'sim': s, 'sec_num': n, 'title': t} for s,n,t in results[:30]]))
"""
    try:
        result = subprocess.run(
            [sys.executable, "-c", script, query, str(DB_PATH)],
            capture_output=True, text=True, timeout=120, env=env
        )
        if result.returncode != 0:
            debug_log(f"  Semantic subprocess error: {result.stderr[:200]}")
            return []
        hits = json.loads(result.stdout.strip())
        return hits
    except (subprocess.TimeoutExpired, json.JSONDecodeError) as e:
        debug_log(f"  Semantic error: {e}")
        return []


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
        rows = db.execute("SELECT category, file_type, COUNT(*) AS c FROM files GROUP BY category, file_type").fetchall()
        for r in rows:
            files_by_cat[r["category"]] = files_by_cat.get(r["category"], 0) + r["c"]
            files_by_type[r["file_type"]] = files_by_type.get(r["file_type"], 0) + r["c"]
    except Exception:
        pass
    db_size = os.path.getsize(DB_PATH) / (1024 * 1024) if os.path.exists(DB_PATH) else 0

    # Version info
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


# ── Semantic / RAG search (existing, preserved) ────────────────────────

def cmd_rag(args, json_output=False):
    query = " ".join(args)
    if not query:
        if json_output:
            print(json.dumps({"error": "No query provided", "suggestion": "Pass a search term like 'omx-db rag scf convergence'."}))
        else:
            print("Usage: omx-db rag <query>")
        return
    if not json_output:
        print("\033[2mLoading embedding model...\033[0m", flush=True)
    env = os.environ.copy()
    env["HF_HUB_OFFLINE"] = "1"
    env["TRANSFORMERS_OFFLINE"] = "1"
    script = """
import os, sys, sqlite3, json, numpy as np
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
from sentence_transformers import SentenceTransformer
model = SentenceTransformer('BAAI/bge-small-en-v1.5', device='cpu')
q = sys.argv[1]
q_emb = model.encode(q, normalize_embeddings=True)
db = sqlite3.connect(sys.argv[2])
db.row_factory = sqlite3.Row
rows = db.execute('SELECT section_id, sec_num, title, file_path, embedding FROM section_embeddings').fetchall()
results = []
for r in rows:
    emb = np.frombuffer(r['embedding'], dtype=np.float32)
    sim = float(np.dot(q_emb, emb))
    results.append((sim, r['sec_num'], r['title'], r['file_path']))
results.sort(reverse=True)
print(json.dumps([{'sim': s, 'sec_num': n, 'title': t, 'file': f} for s,n,t,f in results[:10]]))
"""
    try:
        result = subprocess.run(
            [sys.executable, "-c", script, query, str(DB_PATH)],
            capture_output=True, text=True, timeout=120, env=env
        )
        if result.returncode != 0:
            if json_output:
                print(json.dumps({"error": result.stderr[:500], "suggestion": "Check that sentence-transformers is installed."}))
            else:
                print(f"Error: {result.stderr[:500]}")
            return
        hits = json.loads(result.stdout.strip())
    except subprocess.TimeoutExpired:
        if json_output:
            print(json.dumps({"error": "embedding query timed out", "suggestion": "Try a shorter query or use 'omx-db search' instead."}))
        else:
            print("Error: embedding query timed out")
        return
    except json.JSONDecodeError as e:
        if json_output:
            print(json.dumps({"error": f"Error parsing results: {e}", "suggestion": "Check that the database contains embeddings."}))
        else:
            print(f"Error parsing results: {e}")
        return
    if not hits:
        if json_output:
            print(json.dumps({"results": [], "count": 0}))
        else:
            print("No results.")
        return
    if json_output:
        print(json.dumps(hits, indent=2, ensure_ascii=False))
    else:
        print(f'\033[32m🔍 Semantic search: "{query}"\033[0m\n')
        for h in hits:
            sec = f'§{h["sec_num"]}' if h["sec_num"] else ""
            bar_len = int(h["sim"] * 30)
            bar = "█" * bar_len + "░" * (30 - bar_len)
            print(f'  \033[36m{sec:>12s}\033[0m  \033[1m{h["title"]}\033[0m')
            print(f"  {bar}  {h['sim']:.3f}")
            print()
        print('  \033[2m(query took ~9s first call, model loaded in subprocess)\033[0m')


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
        "section": cmd_section,
        "list": cmd_list,
        "files": cmd_files,
        "stats": cmd_stats,
    }
    if cmd in cmds:
        cmds[cmd](args, json_output=use_json)
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)


if __name__ == "__main__":
    cli()
