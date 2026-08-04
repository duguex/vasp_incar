"""Alias / term mapping for the OpenMX manual database.

Resolves user shorthand (``diis``, ``pbe``, ``cutoff``, ...) and the
user-provided ``aliases.json`` override onto canonical OpenMX keyword names.
"""

from __future__ import annotations

import json
from pathlib import Path

_PKG = Path(__file__).resolve().parent
ALIASES_PATH = _PKG.parent / "aliases.json"

# Built-in fallback for common abbreviations
_BUILTIN_ALIASES: dict[str, str] = {
    "diis": "Rmm-Diis",
    "diisk": "Rmm-Diisk",
    "kerker": "Rmm-Diisk",
    "pbe": "GGA-PBE",
    "pbesol": "GGA-PBEsol",
    "revpbe": "GGA-revPBE",
    "lda": "LDA",
    "lda-pw": "LDA-PW",
    "lda-ca": "LDA-CA",
    "hse": "HSE",
    "hse06": "HSE",
    "pbe0": "PBE0",
    "b3lyp": "B3LYP",
    "scissor": "scissor",
    "kgrid": "scf.Kgrid",
    "kpoints": "scf.Kgrid",
    "energy cutoff": "scf.energycutoff",
    "cutoff": "scf.energycutoff",
}

_ALIASES_CACHE: dict[str, str] | None = None


def load_aliases() -> dict[str, str]:
    """Load alias map: user file (aliases.json) merged on top of built-in fallback."""
    global _ALIASES_CACHE
    if _ALIASES_CACHE is not None:
        return _ALIASES_CACHE
    merged = dict(_BUILTIN_ALIASES)
    if ALIASES_PATH.exists():
        try:
            user = json.loads(ALIASES_PATH.read_text())
            if isinstance(user, dict):
                merged.update(user)
        except (json.JSONDecodeError, OSError):
            pass
    _ALIASES_CACHE = merged
    return merged


def resolve_alias(input: str) -> str:
    """Resolve input through alias map, returning the canonical keyword name or the original."""
    aliases = load_aliases()
    return aliases.get(input.lower(), input)