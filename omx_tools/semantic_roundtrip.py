"""Phase-1 VASP semantic round-trip helpers.

See ``docs/superpowers/specs/2026-07-14-semantic-roundtrip-design.md``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from omx_tools.mapping import forward, load_mapping_table, reverse
from omx_tools._utils import load_json

PKG_DIR = Path(__file__).resolve().parent
DEFAULT_MAPPING = PKG_DIR / "schemas" / "vasp_to_ase.json"

# Spec §6.2 — must survive VASP → params → VASP
MUST_PRESERVE = frozenset({
    "ENCUT", "ISPIN", "EDIFF", "NELM", "NSW", "IBRION",
    "ISMEAR", "SIGMA", "GGA", "EDIFFG", "NELECT", "ALGO",
    "ISIF", "ICHARG",
})


@dataclass
class EquivalenceReport:
    ok: bool
    missing: list[str] = field(default_factory=list)
    changed: dict[str, dict[str, Any]] = field(default_factory=dict)
    unmapped: list[str] = field(default_factory=list)
    dropped: list[dict[str, str]] = field(default_factory=list)
    restored: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "missing": self.missing,
            "changed": self.changed,
            "unmapped": self.unmapped,
            "dropped": self.dropped,
            "restored": self.restored,
        }


def _norm_key(k: str) -> str:
    return str(k).upper().strip()


def _values_close(a: Any, b: Any) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        return bool(a) == bool(b)
    try:
        fa, fb = float(a), float(b)
        return math.isclose(fa, fb, rel_tol=1e-9, abs_tol=1e-12)
    except (TypeError, ValueError):
        return str(a).strip().upper() == str(b).strip().upper()


def get_default_mapping() -> dict:
    return load_mapping_table(load_json(str(DEFAULT_MAPPING), "vasp_to_ase.json"))


def roundtrip_vasp(
    incar: dict[str, Any],
    mapping: dict | None = None,
    *,
    must_preserve: frozenset[str] | None = None,
) -> EquivalenceReport:
    """Encode VASP params through mapping and decode back; report fidelity."""
    mapping = mapping or get_default_mapping()
    mapping = load_mapping_table(mapping)
    must = must_preserve or MUST_PRESERVE

    # Normalize input keys to uppercase for comparison
    src = {_norm_key(k): v for k, v in incar.items()}
    overrides, report = forward(src, mapping, return_report=True)
    back = reverse(overrides, mapping)
    back_n = {_norm_key(k): v for k, v in back.items()}

    missing: list[str] = []
    changed: dict[str, dict[str, Any]] = {}
    for tag in sorted(must):
        if tag not in src:
            continue  # not present in this calculation — N/A
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
        unmapped=list(report.get("unmapped") or []),
        dropped=list(report.get("dropped") or []),
        restored=back_n,
    )
