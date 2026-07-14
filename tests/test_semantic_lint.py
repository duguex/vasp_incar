"""Input lint: inappropriate settings + suggestions."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from omx_tools.semantic.lint import lint_openmx_dat, lint_vasp_incar

ROOT = Path(__file__).resolve().parent.parent
VASP_FIX = ROOT / "tests" / "fixtures" / "semantic" / "vasp"
OMX_FIX = ROOT / "tests" / "fixtures" / "omx_examples"


def test_lint_good_scf_no_errors():
    incar = {
        "ENCUT": 400, "ISMEAR": 0, "SIGMA": 0.05, "NSW": 0,
        "IBRION": -1, "EDIFF": 1e-5, "NELM": 100, "ISPIN": 1,
    }
    rep = lint_vasp_incar(incar)
    assert rep.ok
    assert rep.n_error == 0


def test_lint_encut_too_low():
    rep = lint_vasp_incar({"ENCUT": 50, "NSW": 0, "IBRION": -1})
    codes = {f.code for f in rep.findings}
    assert "encut.too_low" in codes
    assert not rep.ok
    f = next(x for x in rep.findings if x.code == "encut.too_low")
    assert "ENCUT" in f.suggestion or "ENMAX" in f.suggestion


def test_lint_nsw_ibrion_conflict():
    rep = lint_vasp_incar({
        "ENCUT": 400, "NSW": 50, "IBRION": -1, "ISMEAR": 0, "SIGMA": 0.05,
    })
    codes = {f.code for f in rep.findings}
    assert "ionic.nsw_positive_ibrion_fixed" in codes
    assert not rep.ok


def test_lint_metal_sigma_warning():
    rep = lint_vasp_incar({
        "ENCUT": 400, "NSW": 0, "IBRION": -1,
        "ISMEAR": 1, "SIGMA": 0.05,
    })
    codes = {f.code for f in rep.findings}
    assert "smearing.metal_sigma_low" in codes


def test_lint_icharg11_with_nsw_error():
    rep = lint_vasp_incar({
        "ENCUT": 400, "ICHARG": 11, "NSW": 20, "IBRION": 2,
    })
    codes = {f.code for f in rep.findings}
    assert "band.icharg11_with_nsw" in codes


def test_lint_fixture_metal_info():
    text = (VASP_FIX / "scf_metal.INCAR").read_text()
    incar = {}
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip().upper(), v.strip()
        try:
            incar[k] = float(v) if ("." in v or "e" in v.lower()) else int(v)
        except ValueError:
            incar[k] = v
    rep = lint_vasp_incar(incar)
    # metal file should be ok (no hard errors) with SIGMA=0.2
    assert rep.ok
    assert rep.calc_class_hint in ("scf_metal", "scf", None)


def test_lint_openmx_opt_maxiter():
    path = OMX_FIX / "geoopt_example" / "relax_diis.dat"
    # fixture has MD.maxIter 50 — should not warn opt_maxiter_one
    rep = lint_openmx_dat(str(path))
    codes = {f.code for f in rep.findings}
    assert "omx.opt_maxiter_one" not in codes


def test_dft_semantic_lint_cli():
    # write temp bad incar
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".INCAR", delete=False) as f:
        f.write("ENCUT = 80\nNSW = 40\nIBRION = -1\nISMEAR = 1\nSIGMA = 0.05\n")
        path = f.name
    r = subprocess.run(
        [sys.executable, "-m", "dft_utils.cli", "semantic", "lint", path],
        capture_output=True, text=True, timeout=60, cwd=str(ROOT),
    )
    assert r.returncode == 1
    data = json.loads(r.stdout)
    assert data["ok"] is False
    codes = {f["code"] for f in data["findings"]}
    assert "encut.too_low" in codes or "encut.low" in codes
    assert "ionic.nsw_positive_ibrion_fixed" in codes
    assert any("suggestion" in f and f["suggestion"] for f in data["findings"])
