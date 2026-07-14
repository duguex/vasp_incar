"""Equivalence reports via Semantic IR."""

from __future__ import annotations

from typing import Any

from omx_tools.semantic.decode_vasp import decode_vasp
from omx_tools.semantic.encode_vasp import encode_vasp
from omx_tools.semantic_roundtrip import (
    MUST_PRESERVE,
    EquivalenceReport,
    _values_close,
    _norm_key,
)


def roundtrip_vasp_ir(
    incar: dict[str, Any],
    *,
    must_preserve: frozenset[str] | None = None,
    structure_path: str | None = None,
) -> EquivalenceReport:
    """VASP → IR → VASP' fidelity report (Phase 2 path)."""
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
