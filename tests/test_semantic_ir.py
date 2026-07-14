"""Phase-2 Semantic IR: encode/decode and IR-based round-trip."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from omx_tools.semantic import (
    decode_omx,
    decode_vasp,
    encode_vasp,
    roundtrip_vasp_ir,
)
from omx_tools.semantic.ir import IR_SCHEMA, IR_VERSION

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures" / "semantic" / "vasp"


def _parse_simple_incar(path: Path) -> dict:
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


def test_encode_vasp_envelope_shape():
    incar = _parse_simple_incar(FIXTURES / "scf_insulator.INCAR")
    ir = encode_vasp(incar)
    env = ir.to_envelope()
    assert env["_version"] == IR_VERSION
    data = env["data"]
    assert data["schema"] == IR_SCHEMA
    assert data["calc_class"] in ("scf", "scf_metal", "relax", "band")
    assert data["physics"]["cutoff_eV"] == pytest.approx(400.0)
    assert data["ionic"]["max_steps"] == 0
    assert data["physics"]["smearing"]["ismear"] == 0


def test_encode_decode_vasp_roundtrip_metal():
    incar = _parse_simple_incar(FIXTURES / "scf_metal.INCAR")
    rep = roundtrip_vasp_ir(incar)
    assert rep.ok, rep.as_dict()
    assert rep.restored["ISMEAR"] == 1
    assert rep.restored["ALGO"] == "Fast"
    assert rep.restored["NSW"] == 0


def test_encode_decode_vasp_roundtrip_relax():
    incar = _parse_simple_incar(FIXTURES / "relax_isif3.INCAR")
    rep = roundtrip_vasp_ir(incar)
    assert rep.ok, rep.as_dict()
    assert rep.restored["IBRION"] == 2
    assert rep.restored["ISIF"] == 3
    assert float(rep.restored["EDIFFG"]) == pytest.approx(-0.02)


def test_decode_omx_strips_preserve_keys():
    incar = _parse_simple_incar(FIXTURES / "scf_metal.INCAR")
    ir = encode_vasp(incar)
    template, overrides = decode_omx(ir)
    assert template in ("scf_band_metal", "scf_band")
    assert not any(str(k).startswith("vasp_") for k in overrides)
    assert "scf_energycutoff" in overrides
    # NSW=0 → md_maxiter clamped for writer
    assert overrides.get("md_maxiter") == 1


def test_code_native_restores_prec():
    incar = {"ENCUT": 400, "PREC": "Accurate", "NSW": 0, "ISMEAR": 0}
    ir = encode_vasp(incar)
    assert "PREC" in ir.code_native.vasp or "PREC" in {
        d.get("tag") for d in ir.provenance.dropped
    }
    back = decode_vasp(ir)
    # PREC is declared drop but stored in code_native → restored for same-code
    assert back.get("PREC") == "Accurate"
    assert back.get("NSW") == 0


def test_ir_json_roundtrip_model():
    incar = _parse_simple_incar(FIXTURES / "scf_insulator.INCAR")
    ir = encode_vasp(incar)
    raw = json.loads(json.dumps(ir.to_envelope()))
    from omx_tools.semantic.ir import SemanticIR

    ir2 = SemanticIR.from_envelope(raw)
    assert ir2.physics.cutoff_eV == pytest.approx(400.0)
    assert ir2.calc_class == ir.calc_class
