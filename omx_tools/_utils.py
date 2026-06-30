"""Shared utilities for omx_tools modules."""

import json
import sys
from pathlib import Path

from dft_utils import die_json  # noqa: F401 — re-exported for callers


def load_json(path: str | Path, name: str) -> dict:
    """Load a JSON file, exiting with error on FileNotFoundError."""
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: {name} not found at {path}", file=sys.stderr)
        sys.exit(1)


def auto_kgrid(atoms, kspacing: float) -> list[int]:
    """Compute Monkhorst-Pack k-grid from cell vectors and target spacing."""
    import numpy as np
    cell = atoms.cell
    recip = cell.reciprocal() * (2 * np.pi)
    lengths = np.linalg.norm(recip, axis=1)
    return [max(1, int(np.floor(l / kspacing))) for l in lengths]
