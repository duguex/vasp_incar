"""Tests for omx_tools parsers."""

import tempfile
from pathlib import Path

import pytest

from omx_tools.parsers.openmx import parse_dat, _parse_value_str


# ---------------------------------------------------------------------------
# _parse_value_str
# ---------------------------------------------------------------------------

class TestParseValue:
    def test_int(self):
        assert _parse_value_str("42") == 42
        assert _parse_value_str("-1") == -1

    def test_float(self):
        assert _parse_value_str("3.14") == 3.14
        assert _parse_value_str("1e-6") == 1e-6
        assert _parse_value_str("-0.5") == -0.5

    def test_string(self):
        assert _parse_value_str("On") == "On"
        assert _parse_value_str("GGA-PBE") == "GGA-PBE"
        assert _parse_value_str("Nomd") == "Nomd"


# ---------------------------------------------------------------------------
# parse_dat
# ---------------------------------------------------------------------------

SAMPLE_DAT = """System.Name        Si8_test
DATA.PATH        /mnt/shared/DFT_DATA19
Species.Number        1
<Definition.of.Atomic.Species
    Si  Si8.0-s2p2d1  Si_PBE19
Definition.of.Atomic.Species>
Atoms.Number        8
scf.Kgrid        3 3 3
scf.maxIter        2
scf.energycutoff        300
scf.criterion        1e-06
scf.XcType        GGA-PBE
scf.EigenvalueSolver        Band
# This is a comment
scf.Mixing.Type        Rmm-Diis
MD.maxIter        1
MD.Type        Nomd
"""

SAMPLE_DAT_WITH_COMMENTS = """System.Name        Si8_test
# A comment line
scf.energycutoff        300
scf.criterion        1e-06   # inline comment
"""


@pytest.fixture
def keywords():
    """Return a minimal keyword schema for testing."""
    return {
        "System.Name": {"ase_key": "system_name", "type": "string"},
        "DATA.PATH": {"ase_key": "data_path", "type": "string"},
        "Species.Number": {"ase_key": "species_number", "type": "integer"},
        "Atoms.Number": {"ase_key": "atoms_number", "type": "integer"},
        "scf.Kgrid": {"ase_key": "kpts", "type": "tuple_integer"},
        "scf.maxIter": {"ase_key": "scf_maxiter", "type": "integer"},
        "scf.energycutoff": {"ase_key": "scf_energycutoff", "type": "float"},
        "scf.criterion": {"ase_key": "scf_criterion", "type": "float"},
        "scf.XcType": {"ase_key": "scf_xctype", "type": "string"},
        "scf.EigenvalueSolver": {"ase_key": "scf_eigenvaluesolver", "type": "string"},
        "scf.Mixing.Type": {"ase_key": "scf_mixing_type", "type": "string"},
        "MD.maxIter": {"ase_key": "md_maxiter", "type": "integer"},
        "MD.Type": {"ase_key": "md_type", "type": "string"},
    }


class TestParseDat:
    def test_basic_parsing(self, keywords):
        """Parse sample .dat content, verify ASE keys extracted."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".dat",
                                         delete=False) as f:
            f.write(SAMPLE_DAT)
            tmp = f.name
        try:
            result = parse_dat(tmp, keywords=keywords)
            assert result["system_name"] == "Si8_test"
            assert result["scf_energycutoff"] == 300
            assert result["scf_criterion"] == 1e-06
            assert result["scf_xctype"] == "GGA-PBE"
            assert result["scf_maxiter"] == 2
            assert result["md_maxiter"] == 1
            assert result["atoms_number"] == 8
            assert result["species_number"] == 1
        finally:
            import os
            os.unlink(tmp)

    def test_block_sections_skipped(self, keywords):
        """Section blocks (<...>) should not produce parameters."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".dat",
                                         delete=False) as f:
            f.write(SAMPLE_DAT)
            tmp = f.name
        try:
            result = parse_dat(tmp, keywords=keywords)
            # Block keywords like inner ones should not appear
            assert "Si" not in result
        finally:
            import os
            os.unlink(tmp)

    def test_comments_stripped(self, keywords):
        """Lines with # comments are handled."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".dat",
                                         delete=False) as f:
            f.write(SAMPLE_DAT_WITH_COMMENTS)
            tmp = f.name
        try:
            result = parse_dat(tmp, keywords=keywords)
            assert result["system_name"] == "Si8_test"
            assert result["scf_energycutoff"] == 300
            assert result["scf_criterion"] == 1e-06
        finally:
            import os
            os.unlink(tmp)

    def test_unknown_keyword_skipped(self, keywords):
        """Keywords not in schema are silently skipped."""
        content = "Scf.UnknownKey  42\nscf.energycutoff  300\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".dat",
                                         delete=False) as f:
            f.write(content)
            tmp = f.name
        try:
            result = parse_dat(tmp, keywords=keywords)
            assert "scf_energycutoff" in result
            assert len(result) == 1
        finally:
            import os
            os.unlink(tmp)

    def test_file_not_found(self):
        """Missing file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            parse_dat("/tmp/nonexistent_dat_xyzzy.dat")

    def test_real_dat_file(self):
        """Parse the real Si8_test.dat and verify key params."""
        root = Path(__file__).resolve().parent.parent
        dat_path = root / "Si8_test.dat"
        if not dat_path.exists():
            pytest.skip("Si8_test.dat not found")
        result = parse_dat(str(dat_path))
        assert result.get("scf_maxiter") is not None
        assert result.get("scf_energycutoff") is not None
        assert result.get("scf_xctype") is not None
