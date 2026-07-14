"""Gate logic tests using fixture-like report dicts / docs artifacts."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "run_cross_gates.py"
SI_REPORT = ROOT / "docs" / "benchmarks" / "cross_delta_ecoh_si" / "report.json"


def _load():
    spec = importlib.util.spec_from_file_location("run_cross_gates", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_check_ecoh_si_docs_artifact():
    mod = _load()
    if not SI_REPORT.is_file():
        pytest.skip("Si Ecoh docs report missing")
    rec = mod.check_ecoh_report(
        SI_REPORT, tol_code=0.15, tol_exp_soft=0.5
    )
    assert rec["ok"] is True
    assert rec["abs_delta_codes"] < 0.15


def test_check_ecoh_fails_large_delta(tmp_path):
    mod = _load()
    p = tmp_path / "report.json"
    p.write_text(
        json.dumps({
            "ok": True,
            "element": "Si",
            "vasp": {"Ecoh_eV": 5.0},
            "openmx": {"Ecoh_eV": 4.0},
            "experiment": {"ecoh_eV": 4.63},
            "compare": {"abs_delta_codes": 1.0},
        })
    )
    rec = mod.check_ecoh_report(p, tol_code=0.15, tol_exp_soft=0.5)
    assert rec["ok"] is False
    assert any("hard tol" in i for i in rec["issues"])


def test_cross_engine_required_cases(tmp_path):
    mod = _load()
    p = tmp_path / "report.json"
    p.write_text(
        json.dumps({
            "cases": [
                {"name": "Ndia2", "ok": True},
                {"name": "Graphite4", "ok": True},
            ]
        })
    )
    rec = mod.check_cross_engine(p, ["Ndia2", "Graphite4"])
    assert rec["ok"] is True
    p.write_text(json.dumps({"cases": [{"name": "Ndia2", "ok": False}]}))
    rec2 = mod.check_cross_engine(p, ["Ndia2", "Graphite4"])
    assert rec2["ok"] is False
