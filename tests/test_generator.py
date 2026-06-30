"""Tests for omx-gen (omx_tools.generator)."""

import json
import sys
from pathlib import Path

import pytest

from omx_tools.generator import (
    cli,
    lookup_templates_json,
    lookup_keywords_json,
    SCHEMA_PATH,
    TEMPLATES_PATH,
)
from omx_tools._utils import load_json, die_json


# ── helpers ──────────────────────────────────────────────────────────

def run_gen(argv, capsys):
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


# ── unit tests ────────────────────────────────────────────────────────

class TestHelpers:
    def test_lookup_templates_json(self):
        templates = load_json(TEMPLATES_PATH, "templates.json")
        result = lookup_templates_json(templates)
        assert isinstance(result, list)
        assert len(result) == len(templates)
        for t in result:
            assert "name" in t
            assert "description" in t
            assert "keywords" in t

    def test_lookup_keywords_json(self):
        schema = load_json(SCHEMA_PATH, "keywords.json")
        result = lookup_keywords_json(schema)
        assert isinstance(result, list)
        assert len(result) == len(schema)
        for e in result:
            assert "name" in e
            assert "type" in e

    def test_die_json_text(self, capsys):
        with pytest.raises(SystemExit) as exc:
            die_json("test error", json_output=False, code=1)
        assert exc.value.code == 1
        out, err = capsys.readouterr()
        assert "Error: test error" in err

    def test_die_json_json(self, capsys):
        with pytest.raises(SystemExit) as exc:
            die_json("test error", json_output=True, code=1)
        assert exc.value.code == 0
        out, err = capsys.readouterr()
        data = json.loads(out)
        assert data["error"] == "test error"
        assert data["exit"] == 1

    def test_load_json(self):
        data = load_json(SCHEMA_PATH, "keywords.json")
        assert isinstance(data, dict)
        assert len(data) > 200

    def test_load_json_not_found(self, capsys):
        with pytest.raises(SystemExit):
            load_json(Path("/nonexistent"), "test")


# ── --list-templates ─────────────────────────────────────────────────

class TestListTemplates:
    def test_json(self, capsys):
        out, err, code = run_gen(["omx-gen", "--list-templates", "--json"], capsys)
        assert code == 0
        data = json.loads(out)
        assert isinstance(data, list)
        assert len(data) >= 5
        names = {t["name"] for t in data}
        assert "scf_band" in names
        assert "band_dispersion" in names

    def test_text(self, capsys):
        out, err, code = run_gen(["omx-gen", "--list-templates"], capsys)
        assert code == 0
        assert "Available templates:" in out
        assert "scf_band" in out
        assert out.strip().startswith("Available")


# ── --list-keywords ──────────────────────────────────────────────────

class TestListKeywords:
    def test_json_all(self, capsys):
        out, err, code = run_gen(["omx-gen", "--list-keywords", "--json"], capsys)
        assert code == 0
        data = json.loads(out)
        assert isinstance(data, list)
        assert len(data) > 200

    def test_json_filter_type(self, capsys):
        out, err, code = run_gen(
            ["omx-gen", "--list-keywords", "--type", "string", "--json"], capsys
        )
        assert code == 0
        data = json.loads(out)
        assert all(e["type"] == "string" for e in data)

    def test_json_filter_nonexistent_type(self, capsys):
        out, err, code = run_gen(
            ["omx-gen", "--list-keywords", "--type", "nonexistent", "--json"], capsys
        )
        assert code == 0
        data = json.loads(out)
        assert data == []

    def test_text(self, capsys):
        out, err, code = run_gen(["omx-gen", "--list-keywords"], capsys)
        assert code == 0
        assert "Known keywords:" in out
        assert "scf.XcType" in out or "scf.Kgrid" in out


# ── --keyword ─────────────────────────────────────────────────────────

class TestKeyword:
    def test_json_existing(self, capsys):
        out, err, code = run_gen(
            ["omx-gen", "--keyword", "scf.XcType", "--json"], capsys
        )
        assert code == 0
        data = json.loads(out)
        assert data["type"] == "string"

    def test_json_not_found(self, capsys):
        out, err, code = run_gen(
            ["omx-gen", "--keyword", "scf.NonexistentKeyword", "--json"], capsys
        )
        assert code == 0  # die_json exits 0 for JSON mode
        data = json.loads(out)
        assert "error" in data
        assert data["exit"] == 1  # intended exit code embedded in JSON
        assert "NonexistentKeyword" in data["error"]

    def test_text_existing(self, capsys):
        out, err, code = run_gen(["omx-gen", "--keyword", "scf.XcType"], capsys)
        assert code == 0
        assert "scf.XcType:" in out
        assert "type:" in out

    def test_text_not_found(self, capsys):
        out, err, code = run_gen(
            ["omx-gen", "--keyword", "scf.NonexistentKeyword"], capsys
        )
        assert code == 1
        assert "not found" in err


# ── error paths ───────────────────────────────────────────────────────

class TestErrors:
    def test_no_structure_json(self, capsys):
        out, err, code = run_gen(["omx-gen", "--json"], capsys)
        assert code == 0
        data = json.loads(out)
        assert "error" in data
        assert "STRUCTURE" in data["error"]

    def test_no_structure_text(self, capsys):
        out, err, code = run_gen(["omx-gen"], capsys)
        assert code == 1
        assert "Error:" in err
        assert "STRUCTURE" in err

    def test_file_not_found_json(self, capsys):
        out, err, code = run_gen(
            ["omx-gen", "/tmp/definitely_not_a_file.cif", "--json"], capsys
        )
        assert code == 0
        data = json.loads(out)
        assert "error" in data

    def test_file_not_found_text(self, capsys):
        out, err, code = run_gen(
            ["omx-gen", "/tmp/definitely_not_a_file.cif"], capsys
        )
        assert code == 1
        assert "Error:" in err


# ── --dry-run (requires ASE + test structure) ─────────────────────────

class TestDryRun:
    def test_dry_run_json_error_path(self, capsys):
        """dry-run on nonexistent file -> JSON error."""
        out, err, code = run_gen(
            ["omx-gen", "/tmp/nope.cif", "--dry-run", "--json"], capsys
        )
        assert code == 0
        data = json.loads(out)
        assert "error" in data
