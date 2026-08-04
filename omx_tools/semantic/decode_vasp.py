"""SemanticIR → VASP INCAR dict."""

from __future__ import annotations

from typing import Any

from omx_tools.semantic.ir import (
    SemanticIR,
    method_to_ismear,
    spin_to_ispin,
    xc_to_gga,
)


def decode_vasp(ir: SemanticIR) -> dict[str, Any]:
    """Project IR back to a VASP INCAR parameter dict.

    Restores must-preserve physics/ionic fields and merges ``code_native.vasp``.
    """
    out: dict[str, Any] = {}
    p = ir.physics
    ion = ir.ionic
    el = ir.electronics_algo

    if p.cutoff_eV is not None:
        out["ENCUT"] = p.cutoff_eV
    ispin = p.ispin if p.ispin is not None else spin_to_ispin(p.spin)
    if ispin is not None:
        out["ISPIN"] = ispin
    if p.nupdown is not None:
        out["NUPDOWN"] = p.nupdown
    if p.ediff_eV is not None:
        out["EDIFF"] = p.ediff_eV
    if p.max_scf is not None:
        out["NELM"] = p.max_scf
    if p.charge is not None:
        out["NELECT"] = p.charge

    ismear = p.smearing.ismear
    if ismear is None:
        ismear = method_to_ismear(p.smearing.method)
    if ismear is not None:
        out["ISMEAR"] = ismear
    if p.smearing.sigma_eV is not None:
        out["SIGMA"] = p.smearing.sigma_eV

    gga = xc_to_gga(p.xc)
    if gga is not None:
        out["GGA"] = gga

    if ion.max_steps is not None:
        out["NSW"] = ion.max_steps
    if ion.ibrion is not None:
        out["IBRION"] = ion.ibrion
    if ion.isif is not None:
        out["ISIF"] = ion.isif
    if ion.force_crit_eV_A is not None:
        out["EDIFFG"] = ion.force_crit_eV_A

    if el.vasp_algo is not None:
        out["ALGO"] = el.vasp_algo

    # Merge natives (do not override already-set must-preserve)
    for k, v in (ir.code_native.vasp or {}).items():
        key = str(k).upper()
        if key not in out:
            out[key] = v

    return out
