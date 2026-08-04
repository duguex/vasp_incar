"""Shared utilities for omx_tools modules."""

import sys
from pathlib import Path

from dft_utils import die_json  # noqa: F401 — re-exported for callers
from dft_utils.version import load_data


def load_json(path: str | Path, name: str) -> dict:
    """Load JSON data through the shared version-envelope loader."""
    data = load_data(Path(path))
    if data is None:
        print(f"Error: {name} not found at {path}", file=sys.stderr)
        sys.exit(1)
    return data


def auto_kgrid(atoms, kspacing: float) -> list[int]:
    """Compute Monkhorst-Pack k-grid from cell vectors and target spacing."""
    import numpy as np
    cell = atoms.cell
    recip = cell.reciprocal() * (2 * np.pi)
    lengths = np.linalg.norm(recip, axis=1)
    return [max(1, int(np.floor(l / kspacing))) for l in lengths]
