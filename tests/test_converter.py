"""End-to-end tests for vasp2omx and omp2vasp CLI converters."""

import json
import os
import tempfile
from pathlib import Path

import pytest


# ── Fixtures ──────────────────────────────────────────────────────────

@pytest.fixture
def sample_incar():
    """Write a minimal INCAR to a temp file and return its path."""
    content = "ENCUT = 400\nISMEAR = 0\nSIGMA = 0.05\nNSW = 0\n"
    with tempfile.NamedTemporaryFile(mode="w", suffix=".INCAR",
                                     delete=False) as f:
        f.write(content)
        tmp = f.name
    yield tmp
    os.unlink(tmp)


@pytest.fixture
def sample_structure():
    """Return path to a POSCAR from examples/."""
    p = Path(__file__).resolve().parent.parent / "examples" / "POSCAR"
    if not p.exists():
        pytest.skip(f"Structure file not found: {p}")
    return str(p)


# ── vasp2omx ─────────────────────────────────────────────────────────

@pytest.mark.skipif(
    not __import__("importlib").util.find_spec("pymatgen"),
    reason="pymatgen not installed",
)
@pytest.mark.skipif(
    not Path("/mnt/shared/DFT_DATA19").is_dir(),
    reason="DFT_DATA19 not found at /mnt/shared/DFT_DATA19",
)
def test_vasp2omx_dry_run(sample_incar, sample_structure, capsys):
    """vasp2omx --dry-run produces .dat content to stdout."""
    from omx_tools.vasp2omx import cli
    old_argv = os.sys.argv[:]
    os.sys.argv = ["vasp2omx", sample_incar, sample_structure, "--dry-run"]
    dft_path = os.environ.get("OPENMX_DFT_DATA_PATH")
    if not dft_path:
        dft_path = "/mnt/shared/DFT_DATA19"
        os.environ["OPENMX_DFT_DATA_PATH"] = dft_path
    try:
        cli()
    except SystemExit:
        pass
    finally:
        os.sys.argv = old_argv
        if dft_path != os.environ.get("OPENMX_DFT_DATA_PATH"):
            os.environ.pop("OPENMX_DFT_DATA_PATH", None)
    out, err = capsys.readouterr()
    assert "scf.XcType" in out or "System.Name" in out or "Atoms.Number" in out


@pytest.mark.skipif(
    not __import__("importlib").util.find_spec("pymatgen"),
    reason="pymatgen not installed",
)
def test_vasp2omx_error_missing_incar(capsys):
    """vasp2omx with missing INCAR prints JSON error."""
    from omx_tools.vasp2omx import cli
    old = os.sys.argv[:]
    os.sys.argv = ["vasp2omx", "/nonexistent/INCAR", "/nonexistent/POSCAR"]
    try:
        cli()
    except SystemExit:
        pass
    finally:
        os.sys.argv = old
    out, err = capsys.readouterr()
    data = json.loads(out)
    assert "error" in data
    assert "INCAR" in data["error"]


# ── omp2vasp ──────────────────────────────────────────────────────────

def test_omp2vasp_error_missing_dat(capsys):
    """omp2vasp with missing .dat prints JSON error."""
    from omx_tools.omp2vasp import cli
    old = os.sys.argv[:]
    os.sys.argv = ["omp2vasp", "/nonexistent/input.dat"]
    try:
        cli()
    except SystemExit:
        pass
    finally:
        os.sys.argv = old
    out, err = capsys.readouterr()
    data = json.loads(out)
    assert "error" in data
