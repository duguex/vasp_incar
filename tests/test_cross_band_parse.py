"""Parser tests for cross_band_si (no engine)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "cross_band.py"
REPORT = ROOT / "docs" / "benchmarks" / "cross_band_si" / "report.json"


def _load():
    spec = importlib.util.spec_from_file_location("cross_band_si", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_spectrum_metrics_gap():
    mod = _load()
    # 16 occupied; G direct gap 1.0 eV; X has lower CB → fund. gap 0.5 eV
    e_g = np.concatenate([np.linspace(-5, 0, 16), np.linspace(1.0, 5, 8)])
    e_x = np.concatenate([np.linspace(-5, -0.1, 16), np.linspace(0.5, 5, 8)])
    m = mod.spectrum_metrics({"G": e_g, "X": e_x}, n_occ=16)
    assert m["ok"]
    assert abs(m["gap_fundamental_eV"] - 0.5) < 1e-9
    assert abs(m["gap_direct_G_eV"] - 1.0) < 1e-9


def test_compare_and_gate():
    mod = _load()
    e = np.concatenate([np.linspace(-4, 0, 16), np.linspace(0.7, 4, 8)])
    v = mod.spectrum_metrics({"G": e, "X": e}, n_occ=16)
    o = mod.spectrum_metrics({"G": e + 0.05, "X": e + 0.05}, n_occ=16)
    # after VBM align both zero at vbm — adding const before metrics changes raw but align resets
    # build omx slightly different gap
    e2 = np.concatenate([np.linspace(-4, 0, 16), np.linspace(0.85, 4, 8)])
    o = mod.spectrum_metrics({"G": e2, "X": e2}, n_occ=16)
    cmp = mod.compare_spectra(v, o)
    assert cmp["ok"]
    assert cmp["gap_abs_diff_eV"] == pytest.approx(0.15, abs=1e-9)
    g = mod.gate_result(cmp, tol_gap=0.25, tol_rms=0.5)
    assert g["ok"] is True


@pytest.mark.skipif(not REPORT.is_file(), reason="cross_band_si report not published yet")
def test_docs_report_gate():
    import json

    mod = _load()
    rep = json.loads(REPORT.read_text())
    g = mod.gate_result(rep["compare"], tol_gap=0.25, tol_rms=0.20)
    assert g["ok"] is True
