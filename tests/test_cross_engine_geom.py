"""Unit tests for OpenMX→structure extraction (no SCF)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "cross_engine_examples.py"
EXAMPLE = (
    ROOT / "work" / "benchmarks" / "official_runtest" / "input_example" / "Ndia2.dat"
)


def _load():
    spec = importlib.util.spec_from_file_location("cross_engine_examples", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.skipif(not EXAMPLE.is_file(), reason="official Ndia2.dat cache missing")
def test_atoms_from_ndia2():
    mod = _load()
    atoms = mod.atoms_from_omx_dat(EXAMPLE)
    assert len(atoms) == 2
    assert set(atoms.get_chemical_symbols()) == {"C"}
    assert abs(float(np.linalg.det(atoms.cell.array))) > 1.0


def test_atoms_from_inline_molecule(tmp_path):
    mod = _load()
    dat = tmp_path / "mol.dat"
    dat.write_text(
        """
Atoms.Number 2
<Atoms.SpeciesAndCoordinates
 1  H  0.0  0.0  0.0  0.5 0.5
 2  H  0.74 0.0  0.0  0.5 0.5
Atoms.SpeciesAndCoordinates>
# no unit vectors → vacuum box
"""
    )
    atoms = mod.atoms_from_omx_dat(dat)
    assert len(atoms) == 2
    assert float(np.linalg.det(atoms.cell.array)) > 100.0
