"""CLI capability symmetry: VASP ↔ OpenMX command surface."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _run(args: list[str], env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, *args],
        capture_output=True,
        text=True,
        timeout=90,
        cwd=str(ROOT),
        env=env,
    )


def test_vasp_keyword_alias_for_tag():
    r = _run(["-m", "vasp_query", "keyword", "ENCUT"])
    assert r.returncode == 0, r.stderr + r.stdout
    data = json.loads(r.stdout)
    assert data["info"]["title"] == "ENCUT"


def test_vasp_section_alias_for_fullwiki():
    r = _run(["-m", "vasp_query", "section", "ENCUT"])
    # fullwiki may 0 or 1 depending on title; must not be unknown command
    assert "invalid choice" not in (r.stderr + r.stdout).lower()
    assert "unrecognized" not in (r.stderr + r.stdout).lower()


def test_vasp_hybrid_subcommand():
    r = _run(["-m", "vasp_query", "hybrid", "energy cutoff", "-n", "5"])
    assert r.returncode in (0, 1), r.stderr + r.stdout
    data = json.loads(r.stdout)
    assert "query" in data or "error" in data
    if "results" in data:
        assert data["count"] == len(data["results"])


def test_vasp_rag_subcommand():
    r = _run(["-m", "vasp_query", "rag", "ENCUT cutoff energy", "-k", "5"])
    assert r.returncode in (0, 1), r.stderr + r.stdout
    data = json.loads(r.stdout)
    if "error" in data:
        # embedding backend missing — still a structured response
        assert "suggestion" in data
        return
    assert data["query"]
    assert data["count"] == len(data["results"])
    assert data["count"] >= 1
    assert "title" in data["results"][0]


def test_omx_tag_alias_for_keyword():
    r = _run(["-m", "omx_tools.database", "tag", "scf.Kgrid", "--json"])
    # omx-db strips --json from argv after detection; order: cmd then args
    # module cli reads sys.argv — --json anywhere works
    assert "Unknown command" not in r.stdout
    # may be results or single entry
    assert r.returncode == 0 or r.stdout.strip().startswith("{")


def test_omx_related_section():
    r = _run(["-m", "omx_tools.database", "related", "16", "--json"])
    assert "Unknown command" not in r.stdout
    data = json.loads(r.stdout)
    assert data["query"] == "16"
    assert "related" in data
    assert data["count"] == len(data["related"])
    assert data["count"] >= 1


def test_omx_related_keyword():
    r = _run(["-m", "omx_tools.database", "related", "scf.Mixing.Type", "--json"])
    data = json.loads(r.stdout)
    assert data["query"] == "scf.Mixing.Type"
    assert "related" in data


def test_vasp_gen_list_templates():
    r = _run(["-m", "vasp_query.generator", "--list-templates", "-j"])
    assert r.returncode == 0, r.stderr + r.stdout
    data = json.loads(r.stdout)
    ids = {t["id"] for t in data["templates"]}
    assert {"scf", "relax", "scf_metal", "band", "md"} <= ids


def test_vasp_gen_scf_dry_run():
    r = _run(["-m", "vasp_query.generator", "-t", "scf", "-d", "-s", "ENCUT=400"])
    assert r.returncode == 0, r.stderr + r.stdout
    assert "ENCUT" in r.stdout
    assert "NSW" in r.stdout


def test_dft_vasp_gen():
    r = _run(["-m", "dft_utils.cli", "vasp", "gen", "-t", "scf", "-d"])
    assert r.returncode == 0, r.stderr + r.stdout
    assert "IBRION" in r.stdout or "NSW" in r.stdout


def test_plugins_advertise_generators():
    from dft_utils.protocol import discover, list_all

    discover()
    codes = list_all()
    assert "vasp" in codes and "omx" in codes
    assert "vasp-gen" in codes["vasp"].generators
    assert "omx-gen" in codes["omx"].generators
