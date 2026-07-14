"""Advise loop: lint ↔ knowledge ↔ safe fix."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from omx_tools.semantic.advise import (
    advise_vasp,
    apply_safe_fixes,
    attach_knowledge,
    generate_and_advise_vasp,
)

ROOT = Path(__file__).resolve().parent.parent


def test_attach_knowledge_encut():
    findings = [{
        "severity": "error",
        "code": "encut.too_low",
        "message": "low",
        "suggestion": "raise",
        "tags": ["ENCUT"],
    }]
    out = attach_knowledge(findings, code="vasp")
    assert out[0]["knowledge"]
    k = out[0]["knowledge"][0]
    assert k.get("found") is True
    assert "description" in k
    assert "ENCUT" in (k.get("tag") or "")


def test_safe_fix_nsw_ibrion():
    fixed, notes = apply_safe_fixes({"NSW": 40, "IBRION": -1, "ENCUT": 400})
    assert fixed["IBRION"] == 2
    assert notes


def test_advise_loop_with_fix():
    incar = {
        "ENCUT": 400,
        "NSW": 40,
        "IBRION": -1,
        "ISMEAR": 0,
        "SIGMA": 0.05,
        "EDIFF": 1e-5,
    }
    rep = advise_vasp(incar, auto_fix=True, fetch_knowledge=True)
    assert rep["fixes_applied"]
    assert rep["incar_final"]["IBRION"] == 2
    # EDIFFG may be added for NSW>0
    assert "EDIFFG" in rep["incar_final"]
    # knowledge present on findings when not empty
    assert rep["loop"].startswith("lint")


def test_generate_and_advise():
    rep = generate_and_advise_vasp(template="scf", fetch_knowledge=False)
    assert rep.get("generated_template") == "scf"
    assert "findings" in rep
    assert "generate" in rep.get("loop", "")


def test_cli_advise_fix():
    with tempfile.NamedTemporaryFile("w", suffix=".INCAR", delete=False) as f:
        f.write("ENCUT = 400\nNSW = 30\nIBRION = -1\nISMEAR = 0\nSIGMA = 0.05\n")
        path = f.name
    out = path + ".fixed"
    r = subprocess.run(
        [
            sys.executable, "-m", "dft_utils.cli", "semantic", "advise", path,
            "--fix", "-o", out,
        ],
        capture_output=True, text=True, timeout=90, cwd=str(ROOT),
    )
    assert r.returncode in (0, 1), r.stderr + r.stdout
    data = json.loads(r.stdout)
    assert data.get("fixes_applied")
    assert Path(out).is_file()
    text = Path(out).read_text()
    assert "IBRION" in text
