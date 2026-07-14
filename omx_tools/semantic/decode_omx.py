"""SemanticIR → OpenMX template + ASE-keyed overrides."""

from __future__ import annotations

from typing import Any

from omx_tools.mapping import for_openmx_writer
from omx_tools.semantic.ir import CLASS_TO_TEMPLATE, SemanticIR


def decode_omx(ir: SemanticIR) -> tuple[str, dict[str, Any]]:
    """Return ``(template_name, ase_overrides)`` for OpenMX writers.

    Uses adapter ``ase_params`` when present (from encode_vasp), otherwise
    projects physics/ionic into ASE keys.
    """
    template = ir.openmx_template or CLASS_TO_TEMPLATE.get(ir.calc_class, "scf_band")

    if ir.ase_params:
        # Prefer bridge params from encode_vasp (includes convert rules)
        overrides = for_openmx_writer(dict(ir.ase_params))
        return template, overrides

    # Fallback projection from IR fields
    overrides: dict[str, Any] = {}
    p = ir.physics
    ion = ir.ionic
    if p.cutoff_eV is not None:
        overrides["scf_energycutoff"] = float(p.cutoff_eV) / 2.0
    if p.spin == "off":
        overrides["scf_spinpolarization"] = "Off"
    elif p.spin == "collinear":
        overrides["scf_spinpolarization"] = "On"
    elif p.spin == "noncollinear":
        overrides["scf_spinpolarization"] = "NC"
    if p.ediff_eV is not None:
        overrides["scf_criterion"] = p.ediff_eV
    if p.max_scf is not None:
        overrides["scf_maxiter"] = p.max_scf
    if p.charge is not None:
        overrides["scf_system_charge"] = p.charge
    if p.xc:
        xc = p.xc.upper()
        overrides["scf_xctype"] = {
            "PBE": "GGA-PBE",
            "PW91": "GGA-PW91",
            "LDA": "LDA-CA",
        }.get(xc, p.xc)
    if ion.max_steps is not None:
        overrides["md_maxiter"] = max(int(ion.max_steps), 1)
    if ion.force_crit_eV_A is not None:
        overrides["md_opt_criterion"] = abs(float(ion.force_crit_eV_A))
    if ir.electronics_algo.omx_eigenvalue_solver:
        overrides["scf_eigenvaluesolver"] = ir.electronics_algo.omx_eigenvalue_solver

    # merge any openmx natives
    overrides.update(ir.code_native.openmx or {})
    return template, for_openmx_writer(overrides)
