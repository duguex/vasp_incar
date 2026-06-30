"""Tests for vasp2omx — VASP INCAR ↔ OpenMX .dat converter."""

import json
import os
import tempfile
from pathlib import Path
import pytest

from omx_tools.parsers.vasp import (
    parse_incar,
    detect_intent_from_incar,
    parse_potcar_zvals,
    compute_charge_from_nelect,
)
from omx_tools.mapping import forward, reverse

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mapping():
    """Load the real vasp_to_ase.json mapping table."""
    path = (Path(__file__).resolve().parent.parent
            / "omx_tools" / "schemas" / "vasp_to_ase.json")
    with open(path) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# INCAR parsing (needs pymatgen)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    not __import__("importlib").util.find_spec("pymatgen"),
    reason="pymatgen not installed",
)
class TestParseIncar:
    def test_basic_parsing(self):
        """Verify ENCUT, NSW have correct types."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".INCAR",
                                         delete=False) as f:
            f.write("ENCUT = 400\nNSW = 0\n")
            tmp = f.name
        try:
            d = parse_incar(tmp)
            assert "ENCUT" in d
            assert "NSW" in d
            # pymatgen returns ENCUT as float, NSW as int
            assert isinstance(d["ENCUT"], (int, float))
            assert isinstance(d["NSW"], int)
            assert d["NSW"] == 0
        finally:
            os.unlink(tmp)

    def test_comment_and_type(self):
        """Comments are stripped, .TRUE. becomes bool True."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".INCAR",
                                         delete=False) as f:
            f.write('# commented\nENCUT = 400\nLWAVE = .TRUE.\n')
            tmp = f.name
        try:
            d = parse_incar(tmp)
            assert d["ENCUT"] == 400.0
            assert d["LWAVE"] is True
        finally:
            os.unlink(tmp)

    def test_no_metadata_keys(self):
        """@module / @class keys are stripped."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".INCAR",
                                         delete=False) as f:
            f.write("ENCUT = 400\n")
            tmp = f.name
        try:
            d = parse_incar(tmp)
            assert not any(k.startswith("@") for k in d)
        finally:
            os.unlink(tmp)

    def test_file_not_found(self):
        """Missing file should raise FileNotFoundError (via pymatgen)."""
        with pytest.raises(FileNotFoundError):
            parse_incar("/tmp/nonexistent_incar_xyzzy.INCAR")


# ---------------------------------------------------------------------------
# Intent detection
# ---------------------------------------------------------------------------

class TestDetectIntent:
    def test_scf_default(self):
        """Default returns scf_band."""
        assert detect_intent_from_incar({"NSW": 0, "IBRION": -1}) == "scf_band"

    def test_relaxation(self):
        """NSW > 0 and IBRION in (1,2,3) → geom_opt."""
        assert detect_intent_from_incar({"NSW": 100, "IBRION": 2}) == "geom_opt"
        assert detect_intent_from_incar({"NSW": 50, "IBRION": 1}) == "geom_opt"
        assert detect_intent_from_incar({"NSW": 10, "IBRION": 3}) == "geom_opt"

    def test_metallic(self):
        """NSW=0, ISMEAR in (0,1), SIGMA > 0.1 → scf_band_metal."""
        result = detect_intent_from_incar({"NSW": 0, "ISMEAR": 1, "SIGMA": 0.2})
        assert result == "scf_band_metal"

    def test_metallic_island_smear(self):
        """ISMEAR=0 also triggers metallic."""
        result = detect_intent_from_incar({"NSW": 0, "ISMEAR": 0, "SIGMA": 0.5})
        assert result == "scf_band_metal"

    def test_band_post_scf(self):
        """ICHARG=11 → band_dispersion (highest priority)."""
        assert detect_intent_from_incar({"ICHARG": 11}) == "band_dispersion"
        # even if other conditions also match
        result = detect_intent_from_incar({"ICHARG": 11, "NSW": 100, "IBRION": 2})
        assert result == "band_dispersion"

    def test_optics(self):
        """LOPTICS=True → scf_band."""
        result = detect_intent_from_incar({"LOPTICS": True, "NSW": 0})
        assert result == "scf_band"

    def test_spin(self):
        """ISPIN=2 → scf_band."""
        assert detect_intent_from_incar({"ISPIN": 2}) == "scf_band"

    def test_empty_params(self):
        """Empty dict returns scf_band."""
        assert detect_intent_from_incar({}) == "scf_band"

    def test_missing_optional_keys(self):
        """Keys not present should not raise."""
        assert detect_intent_from_incar({"NSW": 0}) == "scf_band"


# ---------------------------------------------------------------------------
# Parameter mapping — forward (VASP → ASE)
# ---------------------------------------------------------------------------

class TestMapForward:
    def test_encut_div2(self, mapping):
        """ENCUT=400 eV → scf_energycutoff=200 Ry (÷2 heuristic)."""
        result = forward({"ENCUT": 400}, mapping)
        assert result == {"scf_energycutoff": 200}

    def test_encut_div2_float(self, mapping):
        result = forward({"ENCUT": 400.0}, mapping)
        assert result == {"scf_energycutoff": 200.0}


    def test_spin_conversion(self, mapping):
        """ISPIN=2 → 'On'."""
        result = forward({"ISPIN": 2}, mapping)
        assert result == {"scf_spinpolarization": "On"}

    def test_spin_off(self, mapping):
        """ISPIN=1 → 'Off'."""
        result = forward({"ISPIN": 1}, mapping)
        assert result == {"scf_spinpolarization": "Off"}

    def test_spin_nc(self, mapping):
        """ISPIN=3 → 'NC'."""
        result = forward({"ISPIN": 3}, mapping)
        assert result == {"scf_spinpolarization": "NC"}

    def test_abs_to_pos_ediffg(self, mapping):
        """Negative EDIFFG → positive md_opt_criterion."""
        result = forward({"EDIFFG": -0.02}, mapping)
        assert result == {"md_opt_criterion": 0.02}

    def test_xc_pe(self, mapping):
        """GGA=PE → GGA-PBE."""
        result = forward({"GGA": "PE"}, mapping)
        assert result == {"scf_xctype": "GGA-PBE"}

    def test_xc_91(self, mapping):
        """GGA=91 → GGA-PW91."""
        result = forward({"GGA": "91"}, mapping)
        assert result == {"scf_xctype": "GGA-PW91"}

    def test_xc_ca(self, mapping):
        """GGA=CA → LDA-CA."""
        result = forward({"GGA": "CA"}, mapping)
        assert result == {"scf_xctype": "LDA-CA"}

    def test_nsw_passthrough(self, mapping):
        result = forward({"NSW": 50}, mapping)
        assert result == {"md_maxiter": 50}

    def test_ediff_passthrough(self, mapping):
        result = forward({"EDIFF": 1e-6}, mapping)
        assert result == {"scf_criterion": 1e-6}

    def test_nelm_passthrough(self, mapping):
        result = forward({"NELM": 200}, mapping)
        assert result == {"scf_maxiter": 200}

    def test_algo_normal(self, mapping):
        """ALGO=Normal → Band."""
        result = forward({"ALGO": "Normal"}, mapping)
        assert result == {"scf_eigenvaluesolver": "Band"}

    def test_algo_N(self, mapping):
        """ALGO=N → Band."""
        result = forward({"ALGO": "N"}, mapping)
        assert result == {"scf_eigenvaluesolver": "Band"}

    def test_multiple_params(self, mapping):
        """Multiple mapped params produce combined result."""
        result = forward({
            "ENCUT": 500,
            "ISPIN": 2,
            "EDIFF": 1e-5,
        }, mapping)
        assert result == {
            "scf_energycutoff": 250,
            "scf_spinpolarization": "On",
            "scf_criterion": 1e-5,
        }


# ---------------------------------------------------------------------------
# Parameter mapping — reverse (ASE → VASP)
# ---------------------------------------------------------------------------

class TestMapReverse:
    def test_reverse_spin_on(self, mapping):
        """scf_spinpolarization=On → ISPIN=2."""
        result = reverse({"scf_spinpolarization": "On"}, mapping)
        assert result == {"ISPIN": 2}

    def test_reverse_spin_off(self, mapping):
        """scf_spinpolarization=Off → ISPIN=1."""
        result = reverse({"scf_spinpolarization": "Off"}, mapping)
        assert result == {"ISPIN": 1}

    def test_reverse_spin_nc(self, mapping):
        """scf_spinpolarization=NC → ISPIN=3."""
        result = reverse({"scf_spinpolarization": "NC"}, mapping)
        assert result == {"ISPIN": 3}

    def test_reverse_xc_pbe(self, mapping):
        """scf_xctype=GGA-PBE → GGA=PE."""
        result = reverse({"scf_xctype": "GGA-PBE"}, mapping)
        assert result == {"GGA": "PE"}

    def test_reverse_xc_pw91(self, mapping):
        """scf_xctype=GGA-PW91 → GGA=91."""
        result = reverse({"scf_xctype": "GGA-PW91"}, mapping)
        assert result == {"GGA": "91"}

    def test_reverse_xc_lda(self, mapping):
        """scf_xctype=LDA-CA → GGA=CA."""
        result = reverse({"scf_xctype": "LDA-CA"}, mapping)
        assert result == {"GGA": "CA"}

    def test_reverse_xc_unknown(self, mapping):
        """Unknown XC passthrough."""
        result = reverse({"scf_xctype": "GGA-RPBE"}, mapping)
        assert result == {"GGA": "GGA-RPBE"}

    def test_reverse_negate(self, mapping):
        """md_opt_criterion=0.02 → EDIFFG=-0.02."""
        result = reverse({"md_opt_criterion": 0.02}, mapping)
        assert result == {"EDIFFG": -0.02}

    def test_reverse_algo_band(self, mapping):
        """scf_eigenvaluesolver=Band → ALGO=Normal."""
        result = reverse({"scf_eigenvaluesolver": "Band"}, mapping)
        assert result == {"ALGO": "Normal"}

    def test_reverse_algo_other(self, mapping):
        """Other solver passthrough."""
        result = reverse({"scf_eigenvaluesolver": "Cluster"}, mapping)
        assert result == {"ALGO": "Cluster"}

    def test_reverse_encut(self, mapping):
        """scf_energycutoff=400 Ry → ENCUT=200 eV (reverse of ×2)."""
        result = reverse({"scf_energycutoff": 400}, mapping)
        assert result == {"ENCUT": 200.0}


    def test_reverse_passthrough_nsw(self, mapping):
        """md_maxiter=50 → NSW=50 (passthrough)."""
        result = reverse({"md_maxiter": 50}, mapping)
        assert result == {"NSW": 50}

    def test_reverse_passthrough_ediff(self, mapping):
        """scf_criterion=1e-6 → EDIFF=1e-6 (passthrough)."""
        result = reverse({"scf_criterion": 1e-6}, mapping)
        assert result == {"EDIFF": 1e-6}

    def test_reverse_encut(self, mapping):
        """scf_energycutoff=400 Ry → ENCUT=800 eV (reverse of ÷2)."""
        result = reverse({"scf_energycutoff": 400}, mapping)
        assert result == {"ENCUT": 800.0}

    def test_reverse_unknown_ase_key(self, mapping):
        """ASE key not in mapping → skipped."""
        result = reverse({"scf_nonexistent": 42}, mapping)
        assert result == {}

    def test_reverse_nelect(self, mapping):
        """scf_system_charge → NELECT passthrough."""
        result = reverse({"scf_system_charge": -1.0}, mapping)
        assert result == {"NELECT": -1.0}

    def test_reverse_nelect_positive(self, mapping):
        """Positive charge (holes) passthrough."""
        result = reverse({"scf_system_charge": 1.0}, mapping)
        assert result == {"NELECT": 1.0}


class TestNELECT:
    def test_nelect_forward_mapped(self, mapping):
        """NELECT is in the mapping table."""
        assert "NELECT" in mapping

    def test_nelect_forward_has_omx_key(self, mapping):
        """NELECT maps to scf_system_charge."""
        assert mapping["NELECT"]["omx_key"] == "scf_system_charge"

    def test_nelect_reverse_convert_exists(self, mapping):
        """NELECT has reverse_convert=nelect_rev."""
        assert mapping["NELECT"].get("reverse_convert") == "nelect_rev"


class TestPOTCAR:
    """Tests for POTCAR ZVAL parsing and charge computation."""

    def test_parse_potcar_zvals_nv(self):
        """Parse real NV- POTCAR, verify ZVALs for N and C."""
        potcar = ("/mnt/shared/home/2sidesniddle/vasp/archive/"
                  "2023_prb_nv/nv_phonon_sub/POTCAR")
        if not Path(potcar).exists():
            pytest.skip("NV- POTCAR not found")
        zvals = parse_potcar_zvals(potcar)
        assert zvals == [5.0, 4.0], f"Expected [5.0, 4.0] got {zvals}"

    def test_parse_potcar_zvals_sic(self):
        """Parse real SiC POTCAR, verify ZVALs for Si and C."""
        potcar = ("/mnt/shared/home/c606/tangpb/4H-SiC/orth/"
                  "Va_Sik_-1/POTCAR")
        if not Path(potcar).exists():
            pytest.skip("SiC POTCAR not found")
        zvals = parse_potcar_zvals(potcar)
        assert zvals == [4.0, 4.0], f"Expected [4.0, 4.0] got {zvals}"

    def test_parse_potcar_file_not_found(self):
        """Missing POTCAR raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            parse_potcar_zvals("/tmp/nonexistent_potcar")

    def test_compute_charge_nv(self):
        """NV-: NELECT=2046, 1N(ZVAL=5)+510C(ZVAL=4) → charge=-1."""
        potcar = ("/mnt/shared/home/2sidesniddle/vasp/archive/"
                  "2023_prb_nv/nv_phonon_sub/POTCAR")
        struct = ("/mnt/shared/home/2sidesniddle/vasp/archive/"
                  "2023_prb_nv/nv_phonon_sub/CONTCAR")
        if not Path(potcar).exists() or not Path(struct).exists():
            pytest.skip("NV- files not found")
        charge = compute_charge_from_nelect(2046, struct, potcar)
        assert charge == -1.0, f"Expected -1.0 got {charge}"

    def test_compute_charge_sic(self):
        """SiC divacancy: NELECT=2301, verify charge computation."""
        potcar = ("/mnt/shared/home/c606/tangpb/4H-SiC/orth/"
                  "Va_Sik_-1/POTCAR")
        struct = ("/mnt/shared/home/c606/tangpb/4H-SiC/orth/"
                  "Va_Sik_-1/CONTCAR")
        if not Path(potcar).exists() or not Path(struct).exists():
            pytest.skip("SiC files not found")
        charge = compute_charge_from_nelect(2301, struct, potcar)
        # neutral sum = Si_valence*count + C_valence*count
        # Both have ZVAL=4, so neutral = 4 * total_atoms
        # charge = neutral - 2301 should be -1
        assert charge == -1.0, f"Expected -1.0 got {charge}"
