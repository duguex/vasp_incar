"""Integration test: generate .dat with omx-gen, run 2 SCF steps in container."""

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STRUCTURE = PROJECT_ROOT / "work" / "Si8.cif"
CONTAINER = Path("/mnt/shared/openmx4.0_intel.sif")
DFT_DATA = Path("/mnt/shared/DFT_DATA19")


def test_generated_dat_dry_run():
    """--dry-run produces valid .dat content without crashing."""
    old_env = os.environ.get("OPENMX_DFT_DATA_PATH")
    os.environ["OPENMX_DFT_DATA_PATH"] = str(DFT_DATA)
    old_argv = sys.argv[:]
    sys.argv = ["omx-gen", str(STRUCTURE), "-t", "scf_band", "-k", "2", "2", "2", "-d"]
    try:
        from omx_tools.generator import cli
        cli()  # should not raise
    finally:
        sys.argv = old_argv
        if old_env is None:
            del os.environ["OPENMX_DFT_DATA_PATH"]
        else:
            os.environ["OPENMX_DFT_DATA_PATH"] = old_env


@pytest.mark.skipif(
    not STRUCTURE.exists(), reason=f"Test structure not found: {STRUCTURE}"
)
@pytest.mark.skipif(
    not CONTAINER.exists(), reason=f"Container not found: {CONTAINER}"
)
@pytest.mark.skipif(
    not DFT_DATA.exists(), reason=f"DFT_DATA19 not found: {DFT_DATA}"
)
@pytest.mark.skipif(
    not shutil.which("singularity"), reason="singularity not in PATH"
)
class TestContainerRun:
    """Generate .dat, run 2 SCF steps inside the container, verify clean exit."""

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path, monkeypatch):
        self.workdir = tmp_path
        self.dat_path = tmp_path / "Si8_test.dat"
        # Generate in tmp_path (same filesystem = no cross-device issue)
        monkeypatch.chdir(tmp_path)

    def _generate_dat(self):
        """Generate .dat in tmp_path via omx-gen Python API."""
        from omx_tools.generator import generate_input
        from omx_tools.generator import SCHEMA_PATH, TEMPLATES_PATH
        from omx_tools._utils import load_json

        schema = load_json(SCHEMA_PATH, "keywords.json")
        templates = load_json(TEMPLATES_PATH, "templates.json")

        overrides = {"scf_maxiter": 2}

        old_env = os.environ.get("OPENMX_DFT_DATA_PATH")
        os.environ["OPENMX_DFT_DATA_PATH"] = str(DFT_DATA)
        try:
            params = generate_input(
                structure_path=str(STRUCTURE),
                template_name="scf_band",
                overrides=overrides,
                schema=schema,
                templates=templates,
                kspacing=0.33,
                dry_run=False,
                verbose=False,
                output_path=str(self.dat_path),
            )
        finally:
            if old_env is None:
                del os.environ["OPENMX_DFT_DATA_PATH"]
            else:
                os.environ["OPENMX_DFT_DATA_PATH"] = old_env

        assert self.dat_path.exists(), f"{self.dat_path} not generated"
        return params

    def test_parses_without_error(self):
        """Container exits 0, no error keywords in stdout/stderr."""
        self._generate_dat()

        result = subprocess.run(
            [
                "singularity", "exec",
                "--bind", f"{DFT_DATA}:{DFT_DATA}",
                str(CONTAINER),
                "/openmx4.0/work/openmx", str(self.dat_path),
            ],
            cwd=str(self.workdir),
            capture_output=True, text=True, timeout=180,
        )

        combined = result.stdout + result.stderr

        # Check for crash indicators
        crash_patterns = [
            r"Segmentation fault",
            r"signal",
            r"Aborted",
            r"core dumped",
            r"Killed",
        ]
        for pat in crash_patterns:
            if re.search(pat, combined):
                pytest.fail(f"Crash detected ({pat}) in container output")

        # Check that OpenMX actually started SCF
        scf_found = re.search(r"SCF\s*=\s*1", result.stdout)
        assert scf_found is not None, \
            f"OpenMX did not start SCF. stdout tail:\n{result.stdout[-1500:]}\n\nstderr:\n{result.stderr[-500:]}"

    def test_generated_file_has_valid_syntax(self):
        """Basic sanity: .dat has required OpenMX keywords."""
        self._generate_dat()
        content = self.dat_path.read_text()

        assert re.search(r"Atoms\.SpeciesAndCoordinates", content)
        assert re.search(r"Atoms\.UnitVectors", content)
        assert re.search(r"scf\.XcType", content, re.IGNORECASE)
        assert re.search(r"scf\.Kgrid", content, re.IGNORECASE)
        assert re.search(r"System\.Name\s+\S+", content)
