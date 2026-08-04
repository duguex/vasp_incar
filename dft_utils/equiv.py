"""Shared equivalence-report helpers for semantic round-trip grading.

These live in the neutral ``dft_utils`` layer (alongside `SemanticIR`) so the
upper package (``omx_tools.semantic``) does not depend on a legacy root-level
Phase-1 module.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

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


def norm_key(k: str) -> str:
    return str(k).upper().strip()


def values_close(a: Any, b: Any) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        return bool(a) == bool(b)
    try:
        fa, fb = float(a), float(b)
        return math.isclose(fa, fb, rel_tol=1e-9, abs_tol=1e-12)
    except (TypeError, ValueError):
        return str(a).strip().upper() == str(b).strip().upper()