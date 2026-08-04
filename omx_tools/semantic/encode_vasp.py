"""VASP INCAR dict → SemanticIR."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from omx_tools._utils import load_json
from omx_tools.mapping import forward, load_mapping_table
from omx_tools.parsers.vasp import detect_intent_from_incar
from omx_tools.semantic.ir import (
    CLASS_TO_TEMPLATE,
    TEMPLATE_TO_CLASS,
    CodeNative,
    ElectronicsAlgo,
    Ionic,
    Physics,
    Provenance,
    SemanticIR,
    Smearing,
    gga_to_xc,
    ibrion_to_motion,
    ismear_to_method,
    ispin_to_spin,
)

_PKG = Path(__file__).resolve().parent.parent
_MAP = _PKG / "schemas" / "vasp_to_ase.json"


def _mapping() -> dict:
    return load_mapping_table(load_json(str(_MAP), "vasp_to_ase.json"))


def encode_vasp(
    incar: dict[str, Any],
    *,
    structure_path: str | None = None,
    template: str | None = None,
    mapping: dict | None = None,
    source_code: str = "vasp",
) -> SemanticIR:
    """Build SemanticIR from a VASP INCAR parameter dict."""
    mapping = mapping or _mapping()
    src = {str(k).upper(): v for k, v in incar.items()}

    tmpl = template or detect_intent_from_incar(src)
    calc_class = TEMPLATE_TO_CLASS.get(tmpl, "scf")

    overrides, report = forward(src, mapping, return_report=True)

    ispin = src.get("ISPIN")
    ismear = src.get("ISMEAR")
    try:
        ismear_i = int(ismear) if ismear is not None else None
    except (TypeError, ValueError):
        ismear_i = None
    try:
        ispin_i = int(ispin) if ispin is not None else None
    except (TypeError, ValueError):
        ispin_i = None
    try:
        nsw = int(src["NSW"]) if "NSW" in src else None
    except (TypeError, ValueError):
        nsw = None
    try:
        ibrion = int(src["IBRION"]) if "IBRION" in src else None
    except (TypeError, ValueError):
        ibrion = None

    physics = Physics(
        xc=gga_to_xc(src.get("GGA")),
        spin=ispin_to_spin(ispin_i),
        ispin=ispin_i,
        nupdown=float(src["NUPDOWN"]) if "NUPDOWN" in src else None,
        cutoff_eV=float(src["ENCUT"]) if "ENCUT" in src else None,
        smearing=Smearing(
            method=ismear_to_method(ismear_i),
            sigma_eV=float(src["SIGMA"]) if "SIGMA" in src else None,
            ismear=ismear_i,
        ),
        ediff_eV=float(src["EDIFF"]) if "EDIFF" in src else None,
        max_scf=int(src["NELM"]) if "NELM" in src else None,
        charge=float(src["NELECT"]) if "NELECT" in src else None,
    )

    force = None
    if "EDIFFG" in src:
        force = float(src["EDIFFG"])

    ionic = Ionic(
        motion=ibrion_to_motion(ibrion, nsw),
        ibrion=ibrion,
        max_steps=nsw,
        force_crit_eV_A=force,
        isif=int(src["ISIF"]) if "ISIF" in src else None,
    )

    # code_native: dropped tags values + unmapped tags for same-code restore
    native_vasp: dict[str, Any] = {}
    for item in report.get("dropped") or []:
        tag = item.get("tag")
        if tag and tag in src:
            native_vasp[tag] = src[tag]
    for tag in report.get("unmapped") or []:
        if tag in src:
            native_vasp[tag] = src[tag]
    # Also stash ICHARG if present
    if "ICHARG" in src:
        native_vasp.setdefault("ICHARG", src["ICHARG"])

    notes: list[str] = []
    if "ALGO" in src:
        notes.append("ALGO stored exactly in electronics_algo.vasp_algo")

    ir = SemanticIR(
        calc_class=calc_class,  # type: ignore[arg-type]
        structure_ref=structure_path,
        physics=physics,
        ionic=ionic,
        electronics_algo=ElectronicsAlgo(
            vasp_algo=str(src["ALGO"]) if "ALGO" in src else None,
            omx_eigenvalue_solver=overrides.get("scf_eigenvaluesolver"),
        ),
        code_native=CodeNative(vasp=native_vasp, openmx={}),
        provenance=Provenance(
            source_code=source_code,
            unmapped=list(report.get("unmapped") or []),
            dropped=list(report.get("dropped") or []),
            notes=notes,
        ),
        ase_params=dict(overrides),
        openmx_template=tmpl or CLASS_TO_TEMPLATE.get(calc_class, "scf_band"),
    )
    return ir
