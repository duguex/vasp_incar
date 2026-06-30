"""Tests for omx-db (omx_tools.database)."""

import json
import sys
from pathlib import Path

import pytest

from omx_tools.database import (
    cli,
    strip_ansi,
    DB_PATH,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent


# ── helpers ──────────────────────────────────────────────────────────

def run_db(argv, capsys):
    old = sys.argv[:]
    sys.argv = argv
    code = 0
    try:
        cli()
    except SystemExit as e:
        code = e.code or 0
    finally:
        sys.argv = old
    out, err = capsys.readouterr()
    return out, err, code


@pytest.fixture(autouse=True)
def requires_db():
    """Skip all tests if database is missing."""
    if not DB_PATH.exists():
        pytest.skip(f"Database not found at {DB_PATH}")


# ── helpers ────────────────────────────────────────────────────────

class TestHelpers:
    def test_strip_ansi(self):
        assert strip_ansi("\033[32mhello\033[0m") == "hello"
        assert strip_ansi("no ansi") == "no ansi"
        assert strip_ansi("\033[1m\033[36m§8.2\033[0m") == "§8.2"

    def test_db_path(self):
        assert DB_PATH.exists()


# ── search ──────────────────────────────────────────────────────────

class TestSearch:
    def test_json(self, capsys):
        out, err, code = run_db(["omx-db", "search", "SCF", "--json"], capsys)
        assert code == 0
        data = json.loads(out)
        assert "results" in data
        assert data["count"] > 0
        for r in data["results"]:
            assert "sec_num" in r
            assert "title" in r
            assert "snippet" in r
        # snippets are clean (no ANSI)
        assert "\033" not in data["results"][0]["snippet"]

    def test_text(self, capsys):
        out, err, code = run_db(["omx-db", "search", "SCF"], capsys)
        assert code == 0
        assert "results for" in out or "SCF" in out
        # ANSI escape codes present in text mode
        if out.strip() and not out.startswith("No results"):
            assert "\033" in out

    def test_empty_query(self, capsys):
        out, err, code = run_db(["omx-db", "search"], capsys)
        assert code == 0
        assert "Usage" in out or "error" in out

    def test_no_results_json(self, capsys):
        out, err, code = run_db(
            ["omx-db", "search", "XYZZY_NONEXISTENT", "--json"], capsys
        )
        assert code == 0
        data = json.loads(out)
        assert data["results"] == []
        assert data["count"] == 0


# ── keyword ──────────────────────────────────────────────────────────

class TestKeyword:
    def test_json_exact_schema(self, capsys):
        """Exact schema match returns the schema entry."""
        out, err, code = run_db(
            ["omx-db", "keyword", "scf.Kgrid", "--json"], capsys
        )
        assert code == 0
        data = json.loads(out)
        assert "type" in data  # schema entry

    def test_json_no_results(self, capsys):
        """Keyword with no schema match and no DB match."""
        out, err, code = run_db(
            ["omx-db", "keyword", "XYZZY_IMPROBABLE", "--json"], capsys
        )
        assert code == 0
        data = json.loads(out)
        assert data["results"] == []

    def test_text(self, capsys):
        out, err, code = run_db(["omx-db", "keyword", "scf.Kgrid"], capsys)
        assert code == 0
        assert "scf.Kgrid" in out

    def test_no_keyword(self, capsys):
        out, err, code = run_db(["omx-db", "keyword"], capsys)
        assert code == 0
        assert "Usage" in out or "error" in out


# ── section ──────────────────────────────────────────────────────────

class TestSection:
    def test_json_existing(self, capsys):
        out, err, code = run_db(["omx-db", "section", "8.2", "--json"], capsys)
        assert code == 0
        data = json.loads(out)
        assert data["sec_num"] == "8.2"
        assert "title" in data
        assert "content" in data
        assert "file" in data
        assert "depth" in data

    def test_json_deep_section(self, capsys):
        out, err, code = run_db(
            ["omx-db", "section", "52.4.1", "--json"], capsys
        )
        assert code == 0
        data = json.loads(out)
        assert data["sec_num"] == "52.4.1"

    def test_json_not_found(self, capsys):
        out, err, code = run_db(
            ["omx-db", "section", "99.99", "--json"], capsys
        )
        assert code == 0
        data = json.loads(out)
        assert "error" in data
        assert "99.99" in data["error"]
        assert "suggestions" in data

    def test_text(self, capsys):
        out, err, code = run_db(["omx-db", "section", "8.2"], capsys)
        assert code == 0
        assert "§8.2" in out
        assert "Keywords" in out

    def test_no_section(self, capsys):
        out, err, code = run_db(["omx-db", "section"], capsys)
        assert code == 0
        assert "Usage" in out or "error" in out


# ── list ──────────────────────────────────────────────────────────────

class TestList:
    def test_json(self, capsys):
        out, err, code = run_db(["omx-db", "list", "--json"], capsys)
        assert code == 0
        data = json.loads(out)
        assert "sections" in data
        assert len(data["sections"]) > 50
        for s in data["sections"]:
            assert "sec_num" in s
            assert "title" in s
            assert "depth" in s

    def test_text(self, capsys):
        out, err, code = run_db(["omx-db", "list"], capsys)
        assert code == 0
        assert "Manual Contents" in out or "§" in out


# ── files ─────────────────────────────────────────────────────────────

class TestFiles:
    def test_json_all(self, capsys):
        out, err, code = run_db(["omx-db", "files", "--json"], capsys)
        assert code == 0
        data = json.loads(out)
        assert "files" in data
        assert len(data["files"]) > 200
        for f in data["files"]:
            assert "path" in f
            assert "type" in f
            assert "size_bytes" in f

    def test_json_filter_type(self, capsys):
        out, err, code = run_db(
            ["omx-db", "files", "--type", "pdf", "--json"], capsys
        )
        assert code == 0
        data = json.loads(out)
        assert all(f["type"] == "pdf" for f in data["files"])

    def test_text(self, capsys):
        out, err, code = run_db(["omx-db", "files"], capsys)
        assert code == 0
        assert "files" in out or "KB" in out or "MB" in out


# ── stats ─────────────────────────────────────────────────────────────

class TestStats:
    def test_json(self, capsys):
        out, err, code = run_db(["omx-db", "stats", "--json"], capsys)
        assert code == 0
        data = json.loads(out)
        assert "tables" in data
        assert "sections" in data["tables"]
        assert data["tables"]["sections"] > 200
        assert "files_by_category" in data
        assert "files_by_type" in data
        assert "db_size_mb" in data
        assert data["db_size_mb"] > 0

    def test_text(self, capsys):
        out, err, code = run_db(["omx-db", "stats"], capsys)
        assert code == 0
        assert "Database Statistics" in out
        assert "sections" in out


# ── rag (error paths only — model loading is expensive) ────────────────

class TestRag:
    def test_no_query(self, capsys):
        out, err, code = run_db(["omx-db", "rag"], capsys)
        assert code == 0
        assert "Usage" in out or "error" in out

    def test_no_query_json(self, capsys):
        out, err, code = run_db(["omx-db", "rag", "--json"], capsys)
        assert code == 0
        data = json.loads(out)
        assert "error" in data

    # Full rag test is skipped — requires embedding model load (~9s)
    # and can't be run in a CI-like environment without the model cached.
