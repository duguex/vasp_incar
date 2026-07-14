"""OpenMX ASE params / template → SemanticIR (Phase 2 minimal)."""

from __future__ import annotations

from typing import Any

from omx_tools.mapping import reverse, load_mapping_table
from omx_tools._utils import load_json
from omx_tools.semantic.encode_vasp import encode_vasp
from omx_tools.semantic.ir import (
    TEMPLATE_TO_CLASS,
    SemanticIR,
)
from pathlib import Path

_PKG = Path(__file__).resolve().parent.parent
_MAP = _PKG / "schemas" / "vasp_to_ase.json"


def encode_omx(
    ase_params: dict[str, Any],
    *,
    template: str | None = None,
    structure_path: str | None = None,
) -> SemanticIR:
    """Encode OpenMX/ASE params by reversing to VASP then encode_vasp.

    This reuses the VASP IR path so round-trip tests stay consistent.
    Preserve keys in ase_params (vasp_*) improve fidelity.
    """
    mapping = load_mapping_table(load_json(str(_MAP), "vasp_to_ase.json"))
    vasp = reverse(ase_params, mapping)
    tmpl = template or "scf_band"
    ir = encode_vasp(
        vasp,
        structure_path=structure_path,
        template=tmpl,
        source_code="openmx",
    )
    # keep original ase adapter
    ir.ase_params = dict(ase_params)
    ir.openmx_template = tmpl
    ir.calc_class = TEMPLATE_TO_CLASS.get(tmpl, ir.calc_class)  # type: ignore[assignment]
    ir.provenance.source_code = "openmx"
    return ir
