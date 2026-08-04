"""Phase-1 VASP semantic round-trip tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from omx_tools.mapping import forward, load_mapping_table, reverse
from dft_utils.equiv import MUST_PRESERVE
from omx_tools.semantic.equiv import roundtrip_vasp_ir as roundtrip_vasp

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures" / "semantic" / "vasp"
MAPPING_PATH = ROOT / "omx_tools" / "schemas" / "vasp_to_ase.json"


@pytest.fixture
def mapping():
    raw = json.loads(MAPPING_PATH.read_text())
    return load_mapping_table(raw)


def _parse_simple_incar(path: Path) -> dict:
    """Minimal INCAR parser for fixtures (no pymatgen required)."""
    out: dict = {}
    for line in path.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip().upper()
        v = v.strip()
        if v.upper() in (".TRUE.", "TRUE", "T"):
            out[k] = True
        elif v.upper() in (".FALSE.", "FALSE", "F"):
            out[k] = False
        else:
            try:
                if "." in v or "e" in v.lower():
                    out[k] = float(v)
                else:
                    out[k] = int(v)
            except ValueError:
                out[k] = v
    return out


def test_nsw_zero_preserved(mapping):
    mid = forward({"NSW": 0}, mapping)
    assert mid["md_maxiter"] == 1  # OpenMX writer clamp
    assert mid["vasp_nsw"] == 0
    back = reverse(mid, mapping)
    assert back["NSW"] == 0


def test_nupdown_roundtrip(mapping):
    src = {"NUPDOWN": 2, "ISPIN": 2}
    mid = forward(src, mapping)
    # NUPDOWN is a preserve-only key (no global OpenMX keyword).
    assert mid["vasp_nupdown"] == 2
    back = reverse(mid, mapping)
    assert back["NUPDOWN"] == 2


def test_ismear_sigma_roundtrip(mapping):
    src = {"ISMEAR": 1, "SIGMA": 0.2, "NSW": 0, "ENCUT": 400}
    mid = forward(src, mapping)
    back = reverse(mid, mapping)
    assert back["ISMEAR"] == 1
    assert float(back["SIGMA"]) == pytest.approx(0.2)
    assert back["NSW"] == 0
    assert float(back["ENCUT"]) == pytest.approx(400.0)


def test_algo_preserve_exact(mapping):
    mid = forward({"ALGO": "Fast"}, mapping)
    assert mid.get("vasp_algo") == "Fast"
    back = reverse(mid, mapping)
    assert back["ALGO"] == "Fast"


def test_unmapped_and_dropped_report(mapping):
    src = {"ENCUT": 400, "PREC": "Accurate", "ZZZCUSTOM": 1}
    mid, report = forward(src, mapping, return_report=True)
    assert "scf_energycutoff" in mid
    assert "ZZZCUSTOM" in report["unmapped"]
    drop_tags = {d["tag"] for d in report["dropped"]}
    assert "PREC" in drop_tags


def test_fixture_scf_insulator_roundtrip():
    incar = _parse_simple_incar(FIXTURES / "scf_insulator.INCAR")
    rep = roundtrip_vasp(incar)
    assert rep.ok, rep.as_dict()
    assert rep.restored["NSW"] == 0
    assert rep.restored["ISMEAR"] == 0


def test_fixture_scf_metal_roundtrip():
    incar = _parse_simple_incar(FIXTURES / "scf_metal.INCAR")
    rep = roundtrip_vasp(incar)
    assert rep.ok, rep.as_dict()
    assert rep.restored["NSW"] == 0
    assert rep.restored["ISMEAR"] == 1
    assert float(rep.restored["SIGMA"]) == pytest.approx(0.2)
    assert rep.restored["ALGO"] == "Fast"


def test_fixture_relax_roundtrip():
    incar = _parse_simple_incar(FIXTURES / "relax_isif3.INCAR")
    rep = roundtrip_vasp(incar)
    assert rep.ok, rep.as_dict()
    assert rep.restored["NSW"] == 100
    assert rep.restored["IBRION"] == 2
    assert rep.restored["ISIF"] == 3
    assert float(rep.restored["EDIFFG"]) == pytest.approx(-0.02)


def test_must_preserve_set_documented():
    assert "NSW" in MUST_PRESERVE
    assert "ISMEAR" in MUST_PRESERVE
    assert "SIGMA" in MUST_PRESERVE
