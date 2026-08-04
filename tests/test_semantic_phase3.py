"""Phase-3: encode_omx_dat, cross-code grade, dft semantic CLI."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from omx_tools.semantic import (
    cross_roundtrip_vasp,
    encode_omx_dat,
    encode_vasp,
    roundtrip_vasp_ir,
)
from omx_tools.semantic.encode_omx import infer_template_from_ase

ROOT = Path(__file__).resolve().parent.parent
VASP_FIX = ROOT / "tests" / "fixtures" / "semantic" / "vasp"
OMX_FIX = ROOT / "tests" / "fixtures" / "omx_examples"


def _parse_simple_incar(path: Path) -> dict:
    out: dict = {}
    for line in path.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip().upper(), v.strip()
        try:
            if "." in v or "e" in v.lower():
                out[k] = float(v)
            else:
                out[k] = int(v)
        except ValueError:
            if v.upper() in (".TRUE.", "TRUE", "T"):
                out[k] = True
            elif v.upper() in (".FALSE.", "FALSE", "F"):
                out[k] = False
            else:
                out[k] = v
    return out


def test_infer_template_metal_and_opt():
    assert infer_template_from_ase({"scf_electronictemperature": 1500}) == "scf_band_metal"
    assert infer_template_from_ase({"md_type": "Opt"}) == "geom_opt"
    assert infer_template_from_ase({"scf_eigenvaluesolver": "Cluster"}) == "scf_cluster"


def test_encode_omx_dat_fixture():
    path = OMX_FIX / "input_example" / "scf_mix.dat"
    ir = encode_omx_dat(path)
    assert ir.provenance.source_code == "openmx"
    assert ir.ase_params  # from parse_dat
    assert ir.code_native.openmx  # raw keywords
    assert "scf.XcType" in ir.code_native.openmx or "scf.Mixing.Type" in ir.code_native.openmx
    env = ir.to_envelope()
    assert env["_version"]
    assert env["data"]["schema"] == "dft_semantic_ir"


def test_cross_roundtrip_nupdown_is_explicit_loss():
    rep = cross_roundtrip_vasp({
        "ENCUT": 400, "ISPIN": 2, "NUPDOWN": 2,
        "EDIFF": 1e-5, "NELM": 100, "GGA": "PE", "NSW": 0,
    })
    assert rep["ok_core"]
    assert "NUPDOWN" in rep["expected_loss"]


def test_cross_roundtrip_core_ok_insulator():
    incar = _parse_simple_incar(VASP_FIX / "scf_insulator.INCAR")
    rep = cross_roundtrip_vasp(incar)
    assert rep["grade"] == "cross_code_lossy"
    assert rep["ok_core"], rep
    assert rep["class_stable"]
    # static NSW loss is expected under cross-code
    assert "ISMEAR" in rep["expected_loss"] or "ISMEAR" not in incar


def test_cross_roundtrip_metal_core():
    incar = _parse_simple_incar(VASP_FIX / "scf_metal.INCAR")
    rep = cross_roundtrip_vasp(incar)
    assert rep["ok_core"], rep
    # exact ALGO Fast is expected loss without preserve on writer path
    assert "ALGO" in rep["expected_loss"] or rep["restored"].get("ALGO")


def test_same_code_still_strict():
    incar = _parse_simple_incar(VASP_FIX / "scf_metal.INCAR")
    assert roundtrip_vasp_ir(incar).ok


def test_dft_semantic_cli_show_and_roundtrip():
    incar = VASP_FIX / "scf_insulator.INCAR"
    r = subprocess.run(
        [sys.executable, "-m", "dft_utils.cli", "semantic", "show", str(incar)],
        capture_output=True, text=True, timeout=60, cwd=str(ROOT),
    )
    assert r.returncode == 0, r.stderr + r.stdout
    data = json.loads(r.stdout)
    assert data["_version"]
    assert data["data"]["physics"]["cutoff_eV"] == pytest.approx(400.0)

    r2 = subprocess.run(
        [sys.executable, "-m", "dft_utils.cli", "semantic", "roundtrip", str(incar)],
        capture_output=True, text=True, timeout=60, cwd=str(ROOT),
    )
    assert r2.returncode == 0, r2.stderr + r2.stdout
    rep = json.loads(r2.stdout)
    assert rep["ok"] is True
    assert rep["grade"] == "same_code_strict"


def test_dft_semantic_cross_cli():
    incar = VASP_FIX / "scf_insulator.INCAR"
    r = subprocess.run(
        [sys.executable, "-m", "dft_utils.cli", "semantic", "cross", str(incar)],
        capture_output=True, text=True, timeout=60, cwd=str(ROOT),
    )
    assert r.returncode == 0, r.stderr + r.stdout
    rep = json.loads(r.stdout)
    assert rep["ok_core"] is True
    assert rep["grade"] == "cross_code_lossy"


def test_dft_semantic_show_omx():
    path = OMX_FIX / "geoopt_example" / "relax_diis.dat"
    r = subprocess.run(
        [sys.executable, "-m", "dft_utils.cli", "semantic", "show-omx", str(path)],
        capture_output=True, text=True, timeout=60, cwd=str(ROOT),
    )
    assert r.returncode == 0, r.stderr + r.stdout
    data = json.loads(r.stdout)
    assert data["data"]["provenance"]["source_code"] == "openmx"
