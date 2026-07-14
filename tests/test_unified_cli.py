"""Tests for the unified dft CLI (dft_utils.cli)."""

import json
import subprocess
import sys
from pathlib import Path


def _dft(args: list[str]) -> tuple[str, str, int]:
    """Run dft CLI and return (stdout, stderr, exit_code)."""
    cmd = [sys.executable, "-m", "dft_utils.cli"] + args
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return r.stdout, r.stderr, r.returncode


def test_version():
    """dft --version returns version string."""
    out, err, rc = _dft(["--version"])
    assert rc == 0
    assert "dft-tools" in out
    assert "0.3.0" in out


def test_list_codes():
    """dft --list-codes shows registered plugins."""
    out, err, rc = _dft(["--list-codes"])
    assert rc == 0
    assert "vasp" in out
    assert "omx" in out
    assert "VASP" in out
    assert "OpenMX" in out


def test_vasp_tag():
    """dft vasp tag ENCUT returns valid tag info."""
    out, err, rc = _dft(["vasp", "tag", "ENCUT"])
    assert rc == 0
    data = json.loads(out)
    assert data["info"]["title"] == "ENCUT"
    assert len(data["info"]["related_tags"]) > 5
    assert "stats" in data


def test_vasp_list():
    """dft vasp list returns tag list."""
    out, err, rc = _dft(["vasp", "list"])
    assert rc == 0
    data = json.loads(out)
    assert data["count"] > 100
    assert len(data["tags"]) > 100


def test_omx_search():
    """dft omx search SCF --json returns search results."""
    out, err, rc = _dft(["omx", "search", "SCF", "--json"])
    assert rc == 0
    data = json.loads(out)
    assert data["count"] > 0
    for r in data["results"]:
        assert "sec_num" in r
        assert "title" in r


def test_omx_section():
    """dft omx section 16 returns section content."""
    out, err, rc = _dft(["omx", "section", "16", "--json"])
    assert rc == 0
    data = json.loads(out)
    assert data["sec_num"] == "16"
    assert data["title"] == "SCF convergence"
    assert len(data.get("content", "")) > 100


def test_convert_no_args():
    """dft convert without args shows usage."""
    out, err, rc = _dft(["convert"])
    assert "Usage" in out
    assert "vasp" in out or "omx" in out


def test_convert_vasp_to_omx_dry_run(tmp_path):
    """dft convert vasp:omx accepts remainder args and runs the converter."""
    import os
    import textwrap

    root = Path(__file__).resolve().parent.parent
    # Minimal crystal + clean INCAR so ASE OpenMX writer accepts XC
    poscar = tmp_path / "POSCAR"
    poscar.write_text(textwrap.dedent("""\
        Si
        1.0
        5.43 0 0
        0 5.43 0
        0 0 5.43
        Si
        2
        Direct
        0 0 0
        0.25 0.25 0.25
    """))
    incar = tmp_path / "INCAR"
    incar.write_text("ENCUT = 400\nISMEAR = 0\nSIGMA = 0.05\nEDIFF = 1e-5\nISPIN = 1\nNSW = 0\n")

    dft_data = Path(os.environ.get("OPENMX_DFT_DATA_PATH", "/mnt/shared/DFT_DATA19"))
    cmd = [
        sys.executable, "-m", "dft_utils.cli",
        "convert", "vasp:omx", str(incar), str(poscar), "--dry-run",
    ]
    env = os.environ.copy()
    if dft_data.is_dir():
        env["OPENMX_DFT_DATA_PATH"] = str(dft_data)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60, env=env)

    # Argparse must accept remainder args (the original bug)
    assert "unrecognized arguments" not in r.stderr
    assert "No converter found" not in (r.stdout + r.stderr)

    if not dft_data.is_dir():
        # Without DFT data, generation fails later — wiring is still validated above
        return

    assert r.returncode == 0, f"stderr={r.stderr!r} stdout={r.stdout[:400]!r}"
    combined = r.stdout + r.stderr
    assert any(k in combined for k in ("scf.", "Species", "Atoms.Number", "System.Name")), (
        f"expected OpenMX-ish output, got stdout={r.stdout[:400]!r} err={r.stderr[:200]!r}"
    )


def test_unknown_code():
    """dft nonexistent shows error (argparse exits with 2 on invalid choice)."""
    out, err, rc = _dft(["nonexistent", "tag", "ENCUT"])
    assert rc == 2


def test_help():
    """dft --help or no args shows help."""
    out, err, rc = _dft([])
    assert "usage:" in out.lower()
    assert "vasp" in out
    assert "omx" in out
    assert "convert" in out
