"""Equivalence reports via Semantic IR (same-code and cross-code)."""

from __future__ import annotations

from typing import Any

from omx_tools.semantic.decode_omx import decode_omx
from omx_tools.semantic.decode_vasp import decode_vasp
from omx_tools.semantic.encode_omx import encode_omx
from omx_tools.semantic.encode_vasp import encode_vasp
from omx_tools.semantic_roundtrip import (
    MUST_PRESERVE,
    EquivalenceReport,
    _norm_key,
    _values_close,
)

# Physics core expected to survive VASP → OpenMX projection → back
# (without vasp_* preserve keys on the OpenMX writer path)
CROSS_CODE_CORE = frozenset({
    "ENCUT", "ISPIN", "EDIFF", "NELM", "GGA",
})

# Known lossy under cross-code (stripped before ASE write or no OpenMX equivalent)
CROSS_CODE_EXPECTED_LOSS = frozenset({
    "ISMEAR", "SIGMA", "IBRION", "ISIF", "ICHARG", "ALGO",
    "PREC", "LWAVE", "LCHARG", "LREAL", "ISYM", "LORBIT", "NELMIN",
    "ADDGRID", "NBANDS", "MAGMOM", "IVDW",
})


def roundtrip_vasp_ir(
    incar: dict[str, Any],
    *,
    must_preserve: frozenset[str] | None = None,
    structure_path: str | None = None,
) -> EquivalenceReport:
    """VASP → IR → VASP' fidelity report (same-code, strict)."""
    must = must_preserve or MUST_PRESERVE
    src = {_norm_key(k): v for k, v in incar.items()}
    ir = encode_vasp(src, structure_path=structure_path)
    back = decode_vasp(ir)
    back_n = {_norm_key(k): v for k, v in back.items()}

    missing: list[str] = []
    changed: dict[str, dict[str, Any]] = {}
    for tag in sorted(must):
        if tag not in src:
            continue
        if tag not in back_n:
            missing.append(tag)
            continue
        if not _values_close(src[tag], back_n[tag]):
            changed[tag] = {"original": src[tag], "restored": back_n[tag]}

    ok = not missing and not changed
    return EquivalenceReport(
        ok=ok,
        missing=missing,
        changed=changed,
        unmapped=list(ir.provenance.unmapped),
        dropped=list(ir.provenance.dropped),
        restored=back_n,
    )


def cross_roundtrip_vasp(
    incar: dict[str, Any],
    *,
    structure_path: str | None = None,
    core: frozenset[str] | None = None,
) -> dict[str, Any]:
    """Lossy grade: VASP → IR → OpenMX overrides → IR' → VASP'.

    Asserts ``CROSS_CODE_CORE`` physics where present. NSW=0 may become 1
    (OpenMX md_maxiter clamp) and is reported under ``expected_loss`` when so.
    """
    core = core or CROSS_CODE_CORE
    src = {_norm_key(k): v for k, v in incar.items()}

    ir1 = encode_vasp(src, structure_path=structure_path)
    template, ase_writer = decode_omx(ir1)
    # Writer path has no vasp_* preserves
    ir2 = encode_omx(ase_writer, template=template, structure_path=structure_path)
    back = decode_vasp(ir2)
    back_n = {_norm_key(k): v for k, v in back.items()}

    missing: list[str] = []
    changed: dict[str, dict[str, Any]] = {}
    for tag in sorted(core):
        if tag not in src:
            continue
        if tag not in back_n:
            missing.append(tag)
            continue
        if not _values_close(src[tag], back_n[tag]):
            changed[tag] = {"original": src[tag], "restored": back_n[tag]}

    expected_loss: list[str] = []
    for tag in sorted(CROSS_CODE_EXPECTED_LOSS):
        if tag in src and (tag not in back_n or not _values_close(src[tag], back_n.get(tag))):
            expected_loss.append(tag)

    # NSW special case: static 0 often becomes 1 after OpenMX clamp
    if "NSW" in src and src["NSW"] == 0:
        if back_n.get("NSW") not in (0, None) and not _values_close(0, back_n.get("NSW")):
            expected_loss.append("NSW")

    core_ok = not missing and not changed
    return {
        "grade": "cross_code_lossy",
        "ok_core": core_ok,
        "calc_class_in": ir1.calc_class,
        "calc_class_out": ir2.calc_class,
        "template": template,
        "missing_core": missing,
        "changed_core": changed,
        "expected_loss": sorted(set(expected_loss)),
        "restored": back_n,
        "class_stable": ir1.calc_class == ir2.calc_class,
    }
