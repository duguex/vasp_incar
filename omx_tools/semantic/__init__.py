"""Semantic intermediate representation for DFT inputs.

See ``docs/superpowers/specs/2026-07-14-semantic-roundtrip-design.md``.
"""

from omx_tools.semantic.ir import SemanticIR, IR_SCHEMA, IR_VERSION
from omx_tools.semantic.encode_vasp import encode_vasp
from omx_tools.semantic.decode_vasp import decode_vasp
from omx_tools.semantic.decode_omx import decode_omx
from omx_tools.semantic.encode_omx import encode_omx, encode_omx_dat
from omx_tools.semantic.equiv import (
    roundtrip_vasp_ir,
    cross_roundtrip_vasp,
    EquivalenceReport,
)
from omx_tools.semantic.gt import (
    probe_incar_pymatgen_accepts,
    probe_kpoints_roundtrip_file,
    probe_pydefect_shape,
    pymatgen_available,
    pydefect_available,
)

__all__ = [
    "SemanticIR",
    "IR_SCHEMA",
    "IR_VERSION",
    "encode_vasp",
    "decode_vasp",
    "encode_omx",
    "encode_omx_dat",
    "decode_omx",
    "roundtrip_vasp_ir",
    "cross_roundtrip_vasp",
    "EquivalenceReport",
    "probe_incar_pymatgen_accepts",
    "probe_kpoints_roundtrip_file",
    "probe_pydefect_shape",
    "pymatgen_available",
    "pydefect_available",
]
