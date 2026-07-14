"""Parser tests for scripts/bench_si_pbe_openmx.py (no container required)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "bench_si_pbe_openmx.py"


def _load_mod():
    spec = importlib.util.spec_from_file_location("bench_si_pbe_openmx", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def bench():
    return _load_mod()


def test_parse_utot_and_scf(tmp_path, bench):
    sample = """\
   SCF=  14  NormRD=  0.000000000409  Uele= -9.894254882959
   SCF=  15  NormRD=  0.000000000187  Uele= -9.894254883032

        Total energy (Hartree) at MD = 1
  Utot.        -32.866972813372
  Utot = Ukin+UH0+...
The calculation was normally finished.
"""
    p = tmp_path / "Si_bulk.out"
    p.write_text(sample)
    r = bench.parse_openmx_out(p)
    assert r["converged"] is True
    assert r["n_scf"] == 15
    assert abs(r["utot_ha"] + 32.866972813372) < 1e-9
    assert r["utot_ev"] is not None
    assert r["finished_banner"] is True


def test_ecoh_formula(bench):
    """Ecoh = E_atom - E_bulk/N  (positive when bulk lower)."""
    Ha = bench.HARTREE_EV
    e_bulk = -32.866972813372
    e_atom = -3.938182792578
    n = 8
    ecoh = (e_atom - e_bulk / n) * Ha
    assert 4.0 < ecoh < 5.5  # sane Si window for PBE-like


def test_write_markdown(tmp_path, bench):
    report = {
        "ok": True,
        "method": {
            "code": "OpenMX 4.0",
            "xc": "GGA-PBE",
            "basis": "Si8.0-s2p2d1",
            "energycutoff_Ry": 150,
            "kgrid_bulk": [4, 4, 4],
            "mpi_np": 8,
            "a0_input_A": 5.431,
        },
        "structure": {"a0_input_A": 5.431, "a0_exp_A": 5.431},
        "energies": {
            "Ecoh_eV_per_atom": 4.6311,
            "Ecoh_exp_eV_per_atom": 4.63,
            "delta_Ecoh_eV": 0.0011,
            "E_bulk_per_atom_eV": -111.79,
            "E_atom_eV": -107.16,
        },
        "bulk": {"n_scf": 15, "normrd": 1e-10},
        "atom": {"n_scf": 15, "normrd": 1e-10},
        "bulk_wall_s": 20.0,
        "atom_wall_s": 17.0,
    }
    md = tmp_path / "REPORT.md"
    bench.write_markdown(report, md)
    text = md.read_text()
    assert "Ecoh" in text
    assert "4.6311" in text
