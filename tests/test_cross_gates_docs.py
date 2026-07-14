"""Always-on docs artifact gate checks (no container)."""
from __future__ import annotations
import importlib.util
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "run_cross_gates.py"


def _load():
    spec = importlib.util.spec_from_file_location("run_cross_gates", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_docs_ecoh_si_and_c_pass():
    mod = _load()
    for el in ("Si", "C"):
        path = mod.find_ecoh_report(el)
        assert path is not None, el
        rec = mod.check_ecoh_report(path, tol_code=0.15, tol_exp_soft=0.5)
        assert rec["ok"], rec


def test_docs_band_si_pass():
    mod = _load()
    p = ROOT / "docs" / "benchmarks" / "cross_band_si" / "report.json"
    if not p.is_file():
        pytest.skip("band si report missing")
    rec = mod.check_band_report(p, tol_gap=0.25, tol_rms=0.20)
    assert rec["ok"], rec


def test_docs_cross_engine_min_cases():
    mod = _load()
    p = ROOT / "docs" / "benchmarks" / "cross_engine" / "report.json"
    if not p.is_file():
        pytest.skip("cross_engine report missing")
    rec = mod.check_cross_engine(p, ["Ndia2", "Graphite4"])
    assert rec["ok"], rec
