"""E2E: real Si8 structure through generate → advise → roundtrip.

Heavy OpenMX container SCF is left to tests/test_integration.py.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SI8 = PROJECT_ROOT / "work" / "Si8.cif"
DFT_DATA = Path(os.environ.get("OPENMX_DFT_DATA_PATH", "/mnt/shared/DFT_DATA19"))
SCRIPT = PROJECT_ROOT / "scripts" / "e2e_si8_advise_loop.py"

pytestmark = pytest.mark.skipif(
    not SI8.is_file(),
    reason=f"Si8 structure missing: {SI8}",
)


def test_si8_generate_advise_roundtrip(tmp_path):
    """Core loop without OpenMX binary: vasp-gen + advise + roundtrip."""
    from omx_tools.semantic.advise import advise_vasp_file
    from omx_tools.semantic import roundtrip_vasp_ir
    from omx_tools.semantic.cli import _parse_incar_file
    from vasp_query.generator import generate

    out = tmp_path / "si8"
    generate(
        "scf",
        structure=str(SI8),
        kspacing=0.4,
        write_poscar=True,
        output=str(out) + "/",
    )
    incar = out / "INCAR"
    assert incar.is_file()
    assert (out / "KPOINTS").is_file()
    assert (out / "POSCAR").is_file()

    adv = advise_vasp_file(str(incar), fetch_knowledge=True, auto_fix=False)
    assert "findings" in adv
    assert adv.get("loop", "").startswith("lint")
    # generated scf template should not hard-error
    assert adv.get("n_error", 0) == 0

    # knowledge attach: if any finding has tags, knowledge list present
    for f in adv.get("findings") or []:
        if f.get("tags"):
            assert "knowledge" in f

    tags = _parse_incar_file(incar)
    # drop free-text
    tags.pop("SYSTEM", None)
    rt = roundtrip_vasp_ir(tags)
    assert rt.ok, rt.as_dict()


def test_si8_bad_incar_advise_fix(tmp_path):
    from omx_tools.semantic.advise import advise_vasp
    from vasp_query.generator import render_incar

    bad = {
        "ENCUT": 400,
        "NSW": 25,
        "IBRION": -1,
        "ISMEAR": 0,
        "SIGMA": 0.05,
        "EDIFF": 1e-5,
        "NELM": 80,
    }
    rep = advise_vasp(bad, auto_fix=True, fetch_knowledge=False)
    assert rep["fixes_applied"]
    assert rep["incar_final"]["IBRION"] == 2
    assert "EDIFFG" in rep["incar_final"]
    # write for inspection
    (tmp_path / "INCAR.fixed").write_text(
        render_incar(rep["incar_final"], comments=["si8 e2e fix"])
    )


def test_si8_e2e_script_smoke():
    """Run the demo script (no omx-gen) — requires pymatgen for CIF."""
    pytest.importorskip("pymatgen")
    r = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(PROJECT_ROOT),
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "advise.generated" in r.stdout or "SUMMARY" in r.stdout
    assert "roundtrip" in r.stdout.lower() or "roundtrip.generated" in r.stdout


@pytest.mark.skipif(not DFT_DATA.is_dir(), reason="DFT_DATA19 not available")
def test_si8_omx_gen_and_advise_omx(tmp_path):
    """Optional: omx-gen Si8 + advise-omx (no container SCF)."""
    os.environ["OPENMX_DFT_DATA_PATH"] = str(DFT_DATA)
    from omx_tools.generator import generate_input
    from omx_tools._utils import load_json
    from omx_tools.semantic.advise import advise_openmx_dat

    pkg = PROJECT_ROOT / "omx_tools"
    schema = load_json(str(pkg / "schemas" / "keywords.json"), "kw")
    templates = load_json(str(pkg / "schemas" / "templates.json"), "tmpl")
    if isinstance(templates, dict) and "data" in templates:
        # envelope?
        sample = next(iter(templates["data"].values()), None)
        if isinstance(sample, dict) and "tags" in sample or (
            isinstance(sample, dict) and "description" in sample
        ):
            templates = templates["data"]

    # templates.json for omx is not version-enveloped the same way — load raw
    import json
    templates = json.loads((pkg / "schemas" / "templates.json").read_text())

    dat = tmp_path / "Si8.dat"
    generate_input(
        str(SI8), "scf_band", {}, schema, templates,
        0.4, False, False, str(dat),
    )
    assert dat.is_file()
    content = dat.read_text()
    assert "System.Name" in content or "scf." in content.lower() or "Species" in content

    adv = advise_openmx_dat(str(dat), fetch_knowledge=True)
    assert "findings" in adv
    assert adv.get("loop", "").startswith("lint-omx")
