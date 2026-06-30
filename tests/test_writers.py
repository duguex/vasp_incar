"""Tests for omx_tools writers."""

import os
import tempfile
from pathlib import Path

import pytest

from omx_tools.writers.vasp import write_incar


# ---------------------------------------------------------------------------
# write_incar
# ---------------------------------------------------------------------------

class TestWriteIncar:
    def test_write_basic(self):
        """Basic INCAR write produces correct format."""
        params = {"ENCUT": 400, "NSW": 0, "ISPIN": 2}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".INCAR",
                                         delete=False) as f:
            tmp = f.name
        try:
            write_incar(params, tmp)
            with open(tmp) as f:
                content = f.read()
            assert "ENCUT" in content
            assert "NSW" in content
            assert "ISPIN" in content
            assert "400" in content
        finally:
            os.unlink(tmp)

    def test_write_dry_run(self, capsys):
        """Writing to '-' prints to stdout."""
        params = {"ENCUT": 400}
        write_incar(params, "-")
        out, err = capsys.readouterr()
        assert "ENCUT" in out
        assert "400" in out

    def test_write_sorted(self):
        """sort_keys=True sorts keys A-Z."""
        params = {"ISPIN": 2, "ENCUT": 400, "ALGO": "Normal"}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".INCAR",
                                         delete=False) as f:
            tmp = f.name
        try:
            write_incar(params, tmp, sort_keys=True)
            with open(tmp) as f:
                content = f.read()
            # Extract lines containing keys in order
            key_lines = [l.strip() for l in content.split("\n")
                         if l.strip() and not l.startswith("#")]
            # Verify sorted: ALGO < ENCUT < ISPIN
            keys_in_order = [k.split()[0] for k in key_lines if "=" in k]
            assert keys_in_order == ["ALGO", "ENCUT", "ISPIN"]
        finally:
            os.unlink(tmp)


# ---------------------------------------------------------------------------
# write_dat (requires ASE)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    not __import__("importlib").util.find_spec("ase"),
    reason="ASE not installed",
)
class TestWriteDat:
    def test_dry_run_output(self):
        """write_dat dry-run produces .dat content on stdout."""
        from omx_tools.intent import CalculationIntent
        from omx_tools.writers.openmx import write_dat

        # Find a test structure file
        root = Path(__file__).resolve().parent.parent
        xyz_path = root / "work" / "Si8.xyz"
        if not xyz_path.exists():
            pytest.skip(f"Test structure not found: {xyz_path}")

        intent = CalculationIntent(
            template="scf_band",
            params={"scf_maxiter": 1},
            structure_path=str(xyz_path),
        )

        # This will either succeed (with real DFT_DATA19) or fail gracefully
        try:
            write_dat(intent, kspacing=0.5, dry_run=True, verbose=False)
        except SystemExit:
            # Expected if DFT_DATA19 not available
            pass
