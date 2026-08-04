"""SemanticIR → OpenMX template + ASE-keyed overrides."""

from __future__ import annotations

from typing import Any

from omx_tools.mapping import default_mapping, for_openmx_writer, forward
from omx_tools.semantic.decode_vasp import decode_vasp
from dft_utils.ir import CLASS_TO_TEMPLATE, SemanticIR


def decode_omx(ir: SemanticIR) -> tuple[str, dict[str, Any]]:
    """Return ``(template_name, ase_overrides)`` for OpenMX writers.

    Uses the ``ase_params`` adapter snapshot when present (from
    ``encode_vasp``). Only when it is absent (hand-built IR) does it project
    the IR's physics/ionic fields through :func:`decode_vasp` +
    :func:`forward`, so ÷2 / clamp / enum semantics stay solely in the
    keyword mapping table instead of a second hand-written copy.
    """
    template = ir.openmx_template or CLASS_TO_TEMPLATE.get(ir.calc_class, "scf_band")

    if ir.ase_params:
        return template, for_openmx_writer(dict(ir.ase_params))

    # Fallback projection: IR → VASP INCAR → keyword mapping.
    incar = decode_vasp(ir)
    overrides, _ = forward(incar, default_mapping(), return_report=True)
    overrides.update(ir.code_native.openmx or {})
    return template, for_openmx_writer(overrides)