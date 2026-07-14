"""OpenMX official-example corpus: extract, index, query, CLI."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures" / "omx_examples"


def _index_fixtures(out: Path) -> Path:
    script = ROOT / "scripts" / "index_omx_examples.py"
    r = subprocess.run(
        [sys.executable, str(script), "--root", str(FIXTURES), "--out", str(out)],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=str(ROOT),
    )
    assert r.returncode == 0, r.stderr + r.stdout
    return out / "examples_index.json"


def test_extract_openmx_scalars():
    from omx_tools.examples_corpus import extract_openmx_scalars

    p = FIXTURES / "input_example" / "scf_mix.dat"
    kws = extract_openmx_scalars(p)
    assert kws["scf.XcType"] == "GGA-PBE"
    assert kws["scf.Mixing.Type"] == "Rmm-Diis"
    assert kws["scf.Kerker.factor"] == 1.0


def test_infer_intent_from_path():
    from omx_tools.examples_corpus import infer_intent

    assert infer_intent("geoopt_example/relax_diis.dat") == "geom_opt"
    assert infer_intent("negf_example/wire.dat") == "negf"
    assert infer_intent("input_example/scf_mix.dat") == "scf"


def test_indexer_on_fixtures(tmp_path):
    index_path = _index_fixtures(tmp_path / "idx")
    payload = json.loads(index_path.read_text())
    assert payload["_version"] == "0.3.0"
    records = payload["data"]
    assert len(records) == 3
    assert any(r["intent"] == "geom_opt" for r in records)
    assert any(r["intent"] == "negf" for r in records)


def test_search_cooccur_stats(tmp_path):
    from omx_tools.examples_corpus import (
        example_cooccur,
        example_stats,
        load_index,
        search_examples,
    )

    index_path = _index_fixtures(tmp_path / "idx")
    records = load_index(index_path)

    assert len(search_examples(records, query="Kerker")) >= 1
    assert len(search_examples(records, intent="geom_opt")) == 1
    assert len(search_examples(records, keyword="scf.Mixing.Type")) >= 2

    st = example_stats(records)
    assert st["total_examples"] == 3
    assert st["top_keywords"]

    st_kw = example_stats(records, keyword="scf.Mixing.Type")
    assert st_kw["count"] >= 2

    co = example_cooccur(records, "scf.Mixing.Type", "scf.Kerker.factor")
    assert co["cooccur_count"] >= 2


def test_cmd_example_and_cooccur(tmp_path, monkeypatch, capsys):
    from omx_tools import database as db
    import omx_tools.examples_corpus as ec

    index_path = _index_fixtures(tmp_path / "idx")
    monkeypatch.setattr(ec, "default_index_path", lambda: index_path)

    db.cmd_example(["Kerker"], json_output=True)
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["count"] >= 1
    assert data["results"]

    db.cmd_example(["--intent", "geom_opt"], json_output=True)
    data2 = json.loads(capsys.readouterr().out)
    assert data2["count"] == 1

    db.cmd_cooccur(["scf.Mixing.Type", "scf.Kerker.factor"], json_output=True)
    co = json.loads(capsys.readouterr().out)
    assert co["cooccur_count"] >= 2

    db.cmd_stats(["--examples"], json_output=True)
    st = json.loads(capsys.readouterr().out)
    assert st["total_examples"] == 3
