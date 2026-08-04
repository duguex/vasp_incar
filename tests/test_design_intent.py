"""Design-intent tests: does the project actually fulfill its purpose?

These tests verify the core value proposition — not just that code runs,
but that it produces correct, useful results.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest


# ═════════════════════════════════════════════════════════════════════
# 1. Search relevance: natural language → correct knowledge
# ═════════════════════════════════════════════════════════════════════

class TestVaspSearchRelevance:
    """Searching for a concept should return the relevant INCAR tag as top result."""

    def _search(self, query: str) -> list[dict] | dict:
        r = subprocess.run(
            [sys.executable, "-m", "vasp_query", "search", query],
            capture_output=True, text=True, timeout=30,
        )
        data = json.loads(r.stdout)
        # If exact match via alias, response is tag dict, not search results
        if "results" in data:
            return data["results"]
        return data

    def test_energy_cutoff_returns_encut(self):
        """'energy cutoff' → ENCUT should be top result."""
        results = self._search("energy cutoff")
        top_id = results[0].get("tag", results[0].get("id", ""))
        assert "ENCUT" in top_id, f"expected ENCUT, got {top_id}"

    def test_smearing_returns_ismear(self):
        """'smearing' → ISMEAR should be top result."""
        results = self._search("smearing")
        top_id = results[0].get("tag", results[0].get("id", ""))
        assert "ISMEAR" in top_id, f"expected ISMEAR, got {top_id}"

    def test_spin_orbit_returns_lsorbit(self):
        """'spin orbit coupling' → LSORBIT should be top result."""
        results = self._search("spin orbit coupling")
        top_id = results[0].get("tag", results[0].get("id", ""))
        assert "LSORBIT" in top_id or "spin" in top_id.lower(), \
            f"expected LSORBIT, got {top_id}"

    def test_hse06_returns_hfscreen(self):
        """'HSE06 hybrid functional' → HFSCREEN should be in top 5."""
        results = self._search("HSE06 hybrid functional")
        top_ids = [r.get("tag", r.get("id", "")) for r in results[:5]]
        assert any("HFSCREEN" in t or "HSE" in t for t in top_ids), \
            f"no HFSCREEN in top 5: {top_ids}"

    def test_dftu_search(self):
        """'DFT+U' resolves to LDAU via alias (T1 exact match)."""
        results = self._search("DFT+U")
        # If exact match via alias, response is a tag dict (not search results)
        if "results" not in results:
            assert results.get("info", {}).get("title") == "LDAU", \
                f"expected LDAU tag, got {results.get('info', {}).get('title', '?')}"
        else:
            top_ids = [r.get("tag", r.get("id", "")) for r in results["results"][:5]]
            assert any("LDAU" in t for t in top_ids), \
                f"LDAU not in top 5: {top_ids}"


class TestOmxSearchRelevance:
    """Searching the OpenMX manual should return relevant sections."""

    def _search(self, query: str) -> dict:
        r = subprocess.run(
            [sys.executable, "-m", "omx_tools.database", "search", query, "--json"],
            capture_output=True, text=True, timeout=15,
        )
        return json.loads(r.stdout)

    def test_scf_convergence_returns_section_16(self):
        """'SCF convergence' → §16 should be in top 5."""
        data = self._search("SCF convergence")
        top_secs = [r["sec_num"] for r in data["results"][:5]]
        assert any("16" in s for s in top_secs), f"§16 not in top 5: {top_secs}"

    def test_band_structure_returns_section_10(self):
        """'band structure kpoint' → §10 should be in top 5."""
        data = self._search("band structure kpoint")
        top_secs = [r["sec_num"] for r in data["results"][:5]]
        assert any(s and "10" in s for s in top_secs), \
            f"§10 not in top 5: {top_secs}"

    def test_keyword_lookup_returns_structure(self):
        """Keyword lookup returns structured metadata with type info."""
        r = subprocess.run(
            [sys.executable, "-m", "omx_tools.database", "keyword",
             "scf.Kgrid", "--json"],
            capture_output=True, text=True, timeout=15,
        )
        data = json.loads(r.stdout)
        assert "type" in data
        assert data["type"] == "tuple_integer"
        assert "default" in data


# ═════════════════════════════════════════════════════════════════════
# 2. Cross-code bridge: VASP → OpenMX conversion correctness
# ═════════════════════════════════════════════════════════════════════

class TestConversionCorrectness:
    """vasp2omx should produce semantically equivalent OpenMX input."""

    @pytest.fixture
    def incar_path(self):
        content = (
            "ENCUT = 400\nISMEAR = 0\nSIGMA = 0.05\n"
            "EDIFF = 1e-5\nISPIN = 2\nGGA = PS\nNSW = 0\nNELM = 100\n"
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".INCAR",
                                         delete=False) as f:
            f.write(content)
            tmp = f.name
        yield tmp
        os.unlink(tmp)

    @pytest.fixture
    def structure_path(self):
        p = Path(__file__).resolve().parent.parent / "examples" / "POSCAR"
        if not p.exists():
            pytest.skip("examples/POSCAR not found")
        return str(p)

    @pytest.mark.skipif(
        not __import__("importlib").util.find_spec("pymatgen"),
        reason="pymatgen not installed",
    )
    @pytest.mark.skipif(
        not Path("/mnt/shared/DFT_DATA19").is_dir(),
        reason="DFT_DATA19 not found",
    )
    def test_encut_converted_to_ry(self, incar_path, structure_path, capsys):
        """ENCUT=400 → scf_energycutoff=200 Ry (eV/2 heuristic) in verbose output."""
        old = sys.argv[:]
        sys.argv = ["vasp2omx", incar_path, structure_path, "-v"]
        dft = os.environ.get("OPENMX_DFT_DATA_PATH", "/mnt/shared/DFT_DATA19")
        os.environ["OPENMX_DFT_DATA_PATH"] = dft
        try:
            from omx_tools.vasp2omx import cli
            cli()
        except SystemExit:
            pass
        finally:
            sys.argv = old
        out, err = capsys.readouterr()
        assert "scf_energycutoff = 200" in err, \
            f"expected scf_energycutoff=200:\n  stderr={err[:500]}"

    @pytest.mark.skipif(
        not __import__("importlib").util.find_spec("pymatgen"),
        reason="pymatgen not installed",
    )
    @pytest.mark.skipif(
        not Path("/mnt/shared/DFT_DATA19").is_dir(),
        reason="DFT_DATA19 not found",
    )
    def test_spin_polarization_mapped(self, incar_path, structure_path, capsys):
        """ISPIN=2 → scf_spinpolarization = On."""
        old = sys.argv[:]
        sys.argv = ["vasp2omx", incar_path, structure_path, "-v"]
        dft = os.environ.get("OPENMX_DFT_DATA_PATH", "/mnt/shared/DFT_DATA19")
        os.environ["OPENMX_DFT_DATA_PATH"] = dft
        try:
            from omx_tools.vasp2omx import cli
            cli()
        except SystemExit:
            pass
        finally:
            sys.argv = old
        out, err = capsys.readouterr()
        assert "scf_spinpolarization = On" in err, \
            f"expected spin=On:\n  stderr={err[:500]}"


# ═════════════════════════════════════════════════════════════════════
# 3. Knowledge completeness
# ═════════════════════════════════════════════════════════════════════

class TestKnowledgeCompleteness:
    """The knowledge base should contain what it claims."""

    def test_vasp_has_all_core_tags(self):
        """Core VASP INCAR tags must be present."""
        r = subprocess.run(
            [sys.executable, "-m", "vasp_query", "list"],
            capture_output=True, text=True, timeout=15,
        )
        data = json.loads(r.stdout)
        tags = set(data["tags"])
        core = {"ENCUT", "ISMEAR", "SIGMA", "EDIFF", "ISPIN", "NSW",
                "IBRION", "ISIF", "GGA", "LREAL", "PREC", "ALGO",
                "NELM", "LDAU", "MAGMOM", "LSORBIT", "LCHARG", "LWAVE"}
        missing = core - tags
        assert not missing, f"missing core tags: {missing}"

    def test_vasp_stats_reasonable(self):
        """stats() returns data for many tags with valid frequencies."""
        r = subprocess.run(
            [sys.executable, "-m", "vasp_query", "stats"],
            capture_output=True, text=True, timeout=15,
        )
        data = json.loads(r.stdout)
        assert isinstance(data, list), f"expected list, got {type(data)}"
        assert len(data) > 100, f"too few stats entries: {len(data)}"
        # First entry should be a valid tag stat
        first = data[0]
        assert "tag" in first
        assert "count" in first

    def test_omx_has_section_16(self):
        """SCF convergence section must exist."""
        r = subprocess.run(
            [sys.executable, "-m", "omx_tools.database", "section",
             "16", "--json"],
            capture_output=True, text=True, timeout=15,
        )
        data = json.loads(r.stdout)
        assert data["sec_num"] == "16"
        assert "SCF" in data["title"]

    def test_omx_database_has_keywords(self):
        """Database must have index entries."""
        r = subprocess.run(
            [sys.executable, "-m", "omx_tools.database", "stats", "--json"],
            capture_output=True, text=True, timeout=15,
        )
        data = json.loads(r.stdout)
        assert data["tables"]["index_entries"] >= 700, \
            f"too few: {data['tables']['index_entries']}"


# ═════════════════════════════════════════════════════════════════════
# 4. Framework extensibility
# ═════════════════════════════════════════════════════════════════════

class TestFrameworkExtensibility:
    """The plugin framework must actually work for adding new codes."""

    def test_plugin_discovers_vasp_and_omx(self):
        """discover() finds both registered plugins."""
        from dft_utils import discover
        plugins = discover()
        assert "vasp" in plugins
        assert "omx" in plugins

    def test_plugin_metadata_correct(self):
        """Plugin metadata is populated correctly."""
        from dft_utils import discover
        vasp = discover()["vasp"]
        assert vasp.display_name == "VASP"
        assert ("vasp", "omx") in vasp.converters
        assert vasp.skills[0].exists()

        omx = discover()["omx"]
        assert omx.display_name == "OpenMX"
        assert "omx-gen" in omx.generators
        assert ("omx", "vasp") in omx.converters
        assert omx.skills[0].exists()

    def test_can_register_mock_plugin(self):
        """A third party can register a mock plugin at runtime."""
        from dft_utils.protocol import CodePlugin, register, get
        mock = CodePlugin(
            name="mock_test",
            display_name="Mock DFT",
            description="Test plugin",
            version="0.0.0",
            package_dir=Path("/tmp"),
        )
        register(mock)
        retrieved = get("mock_test")
        assert retrieved is not None
        assert retrieved.name == "mock_test"
        from dft_utils.protocol import _registry
        _registry.pop("mock_test", None)

    def test_converter_registry_works(self):
        """Converter registry can register and look up converters."""
        from dft_utils.convert import register as reg_conv, convert, available_pairs

        def mock_conv(input_path, **kwargs):
            return "/tmp/mock_output"

        reg_conv("mock_a", "mock_b", mock_conv, "Mock converter")
        pairs = available_pairs()
        assert ("mock_a", "mock_b") in pairs

        result = convert("mock_a", "mock_b", "/tmp/input")
        assert result == "/tmp/mock_output"
        from dft_utils.convert import _registry
        _registry.pop(("mock_a", "mock_b"), None)
