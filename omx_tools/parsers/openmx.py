"""OpenMX .dat parser — extract ASE-keyed scalar parameters."""

import json
from pathlib import Path
from typing import Any


def _parse_value_str(s: str) -> Any:
    """Convert a string value to int/float/str as appropriate."""
    s = s.strip()
    # Try int first
    try:
        return int(s)
    except ValueError:
        pass
    # Try float
    try:
        return float(s)
    except ValueError:
        pass
    # Keep as string
    return s


def _load_keywords() -> dict:
    """Load keywords.json from the package schemas directory."""
    pkg_dir = Path(__file__).resolve().parent.parent
    path = pkg_dir / "schemas" / "keywords.json"
    with open(path) as f:
        return json.load(f)


def parse_dat(path: str, keywords: dict | None = None) -> dict[str, Any]:
    """Parse an OpenMX .dat file and return ASE-keyed parameter dict.

    Only scalar (non-block) keywords defined in *keywords* are extracted.
    Section blocks (``<BlockName ... BlockName>``) are skipped.

    Parameters
    ----------
    path : str
        Path to the .dat file.
    keywords : dict or None
        Keyword schema dict (from keywords.json). Loaded from the package
        schemas directory when None.

    Returns
    -------
    dict[str, Any]
        ASE key → parsed value.

    Raises
    ------
    FileNotFoundError
        When *path* does not exist.
    """
    if keywords is None:
        keywords = _load_keywords()

    result: dict[str, Any] = {}
    in_block = False

    with open(path) as f:
        for line in f:
            # Strip comments
            if "#" in line:
                line = line.split("#", 1)[0]

            line = line.strip()
            if not line:
                continue

            # Track section blocks
            if line.startswith("<") and not line.startswith("<<"):
                in_block = True
                continue
            if line.endswith(">"):
                in_block = False
                continue

            # Skip lines inside blocks
            if in_block:
                continue

            # Parse keyword-value pair
            parts = line.split(None, 1)
            if len(parts) != 2:
                continue

            kw_str, val_str = parts
            kw_str = kw_str.strip()

            # Look up in keyword schema
            entry = keywords.get(kw_str)
            if entry is None:
                continue
            ase_key = entry.get("ase_key")
            if not ase_key:
                continue

            val = _parse_value_str(val_str)
            result[ase_key] = val

    return result
