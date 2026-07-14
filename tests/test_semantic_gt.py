"""Phase-4 ground-truth probes: pymatgen (required), pydefect (optional)."""

from __future__ import annotations

from pathlib import Path

import pytest

from omx_tools.semantic.gt import (
    PYDEFECT_DEFECT_EXTRA,
    VASP_GEN_SUITE_FILES,
    probe_incar_pymatgen_accepts,
    probe_kpoints_roundtrip_file,
    probe_pydefect_shape,
    pymatgen_available,
    pydefect_available,
)
from omx_tools.semantic import decode_vasp, encode_vasp
from vasp_query.generator import generate

pytestmark = pytest.mark.skipif(
    not pymatgen_available(),
    reason="pymatgen not installed",
)

ROOT = Path(__file__).resolve().parent.parent
VASP_FIX = ROOT / "tests" / "fixtures" / "semantic" / "vasp"


def _si_poscar(tmp_path: Path) -> Path:
    p = tmp_path / "POSCAR"
    p.write_text(
        "Si\n1.0\n"
        "5.43 0 0\n0 5.43 0\n0 0 5.43\n"
        "Si\n2\nDirect\n"
        "0 0 0\n0.25 0.25 0.25\n"
    )
    return p


def test_vasp_gen_kpoints_matches_pymatgen_policy(tmp_path):
    pos = _si_poscar(tmp_path)
    out = tmp_path / "run"
    generate(
        "scf",
        structure=str(pos),
        kspacing=0.3,
        write_poscar=True,
        output=str(out) + "/",
    )
    kp = out / "KPOINTS"
    assert kp.is_file()
    rep = probe_kpoints_roundtrip_file(pos, kp, kspacing=0.3, gamma=True)
    assert rep["ok"], rep


def test_decode_vasp_accepted_by_pymatgen_incar():
    text = (VASP_FIX / "scf_metal.INCAR").read_text()
    incar: dict = {}
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip().upper(), v.strip()
        try:
            if "." in v or "e" in v.lower():
                incar[k] = float(v)
            else:
                incar[k] = int(v)
        except ValueError:
            if v.upper() in (".TRUE.", "T", "TRUE"):
                incar[k] = True
            elif v.upper() in (".FALSE.", "F", "FALSE"):
                incar[k] = False
            else:
                incar[k] = v

    ir = encode_vasp(incar)
    decoded = decode_vasp(ir)
    # SYSTEM free text may exist — Incar accepts most tags
    decoded.pop("SYSTEM", None)
    rep = probe_incar_pymatgen_accepts(decoded)
    assert rep["ok"]
    assert "ENCUT" in rep["tags"]
    assert "NSW" in rep["tags"]


def test_vasp_gen_incar_pymatgen_accepts(tmp_path):
    pos = _si_poscar(tmp_path)
    out = tmp_path / "suite"
    generate("relax", structure=str(pos), kspacing=0.25, output=str(out) + "/")
    from pymatgen.io.vasp.inputs import Incar

    incar = Incar.from_file(str(out / "INCAR"))
    # comments stripped by pymatgen; tags present
    assert "ENCUT" in incar or "encut" in {k.upper() for k in incar}
    # NSW for relax template
    keys = {str(k).upper() for k in incar.keys()}
    assert "NSW" in keys or "IBRION" in keys


def test_pydefect_shape_boundary():
    rep = probe_pydefect_shape()
    assert set(rep["vasp_gen_suite"]) == VASP_GEN_SUITE_FILES
    # Defect JSON artifacts are outside generator scope
    assert set(rep["pydefect_extra_json_artifacts"]) == PYDEFECT_DEFECT_EXTRA
    assert VASP_GEN_SUITE_FILES.isdisjoint(PYDEFECT_DEFECT_EXTRA)

    if pydefect_available():
        assert rep["available"] is True
        assert rep["version"]
    else:
        assert rep["available"] is False


@pytest.mark.skipif(not pydefect_available(), reason="pydefect not installed")
def test_pydefect_import_and_supercell_info_symbol():
    """Light API smoke: pydefect exposes SupercellInfo (defect GT surface)."""
    from pydefect.input_maker.supercell_info import SupercellInfo

    assert SupercellInfo is not None
