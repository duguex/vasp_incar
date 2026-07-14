"""Semantic intermediate representation for DFT inputs.

See ``docs/superpowers/specs/2026-07-14-semantic-roundtrip-design.md``.
"""

from omx_tools.semantic.ir import SemanticIR, IR_SCHEMA, IR_VERSION
from omx_tools.semantic.encode_vasp import encode_vasp
from omx_tools.semantic.decode_vasp import decode_vasp
from omx_tools.semantic.decode_omx import decode_omx
from omx_tools.semantic.encode_omx import encode_omx
from omx_tools.semantic.equiv import roundtrip_vasp_ir, EquivalenceReport

__all__ = [
    "SemanticIR",
    "IR_SCHEMA",
    "IR_VERSION",
    "encode_vasp",
    "decode_vasp",
    "encode_omx",
    "decode_omx",
    "roundtrip_vasp_ir",
    "EquivalenceReport",
]
