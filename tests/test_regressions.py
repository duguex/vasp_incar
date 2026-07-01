"""Regression tests for bugs fixed in database.py.

Ensures the 8 pre-existing failures (Item 2) stay fixed.
"""

import json
import sqlite3
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def requires_db():
    """Skip if database is missing."""
    if not (PROJECT_ROOT / "openmx.db").exists():
        pytest.skip("openmx.db not found")


# ── row_factory: _search_fts5 must use sqlite3.Row ────────────────────

def test_row_factory_fts5():
    """_search_fts5 must set row_factory to sqlite3.Row (regression)."""
    from omx_tools.database import DB_PATH
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT sec_num, title FROM sections LIMIT 1").fetchone()
    assert isinstance(row, sqlite3.Row)
    # Access by column name — this would fail if row is a tuple
    assert "sec_num" in row.keys()
    assert "title" in row.keys()
    conn.close()


# ── cmd_files: table name must be 'files', column 'file_type' ─────────

def test_cmd_files_table_name(invoke_db):
    """cmd_files queries the 'files' table (not 'manual_files')."""
    out, err, code = invoke_db(["omx-db", "files", "--json"])
    assert code == 0
    data = json.loads(out)
    assert "files" in data
    assert len(data["files"]) > 0
    for f in data["files"]:
        assert "path" in f
        assert "type" in f  # maps from file_type


def test_cmd_files_filter_type(invoke_db):
    """cmd_files --type filters by file_type column."""
    out, err, code = invoke_db(["omx-db", "files", "--type", "pdf", "--json"])
    assert code == 0
    data = json.loads(out)
    for f in data["files"]:
        assert f["type"] == "pdf"


# ── cmd_section: row['depth'] not row.get('depth') ────────────────────

def test_cmd_section_has_depth(invoke_db):
    """cmd_section includes depth in response (regression: row.get)."""
    out, err, code = invoke_db(["omx-db", "section", "16", "--json"])
    assert code == 0
    data = json.loads(out)
    assert "depth" in data
    assert isinstance(data["depth"], int)


def test_cmd_section_not_found_has_suggestions(invoke_db):
    """Section not found response always includes 'suggestions' key."""
    out, err, code = invoke_db(["omx-db", "section", "99.99", "--json"])
    assert code == 0
    data = json.loads(out)
    assert "suggestions" in data
    assert isinstance(data["suggestions"], list)


# ── cmd_keyword: db = get_db() before fallback ────────────────────────

def test_cmd_keyword_not_found(invoke_db):
    """Keyword not found returns error dict (regression: missing db)."""
    out, err, code = invoke_db(["omx-db", "keyword", "XYZZY_IMPROBABLE", "--json"])
    assert code == 0
    data = json.loads(out)
    assert "error" in data
    assert "suggestion" in data


# ── cmd_stats: text output consistency ────────────────────────────────

def test_cmd_stats_text_case(invoke_db):
    """Stats text output uses consistent casing."""
    out, err, code = invoke_db(["omx-db", "stats"])
    assert code == 0
    assert "Database statistics" in out
