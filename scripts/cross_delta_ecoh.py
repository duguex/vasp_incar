#!/usr/bin/env python3
"""Differential Ecoh: diamond-structure bulk + free atom on VASP and OpenMX.

Supports ``--element Si`` (default) and ``--element C``.

Ecoh = E(atom) − E(bulk)/N_atoms   [eV/atom]

Absolute total energies are not compared across codes.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

HA_TO_EV = 27.211386245988

# Experimental references (room-temp / standard tabulations; for soft check only)
ELEMENT_CFG = {
    "Si": {
        "a0_A": 5.431,
        "ecoh_exp_eV": 4.63,
        "omx_species": "Si  Si8.0-s2p2d1  Si_PBE19",
        "atom_up_down": (3.0, 1.0),  # valence-like init
        "magmom": 2,
    },
    "C": {
        "a0_A": 3.567,
        "ecoh_exp_eV": 7.37,  # diamond cohesive energy ~7.37 eV/atom
        "omx_species": "C  C6.0-s2p2d1  C_PBE19",
        "atom_up_down": (3.0, 1.0),
        "magmom": 2,
    },
}

OMX_SIF = Path(os.environ.get("OPENMX_SIF", "/mnt/shared/openmx4.0_intel.sif"))
VASP_SIF = Path(os.environ.get("VASP_SIF", "/mnt/shared/vasp_latest.sif"))
DFT_DATA = Path(os.environ.get("OPENMX_DFT_DATA_PATH", "/mnt/shared/DFT_DATA19"))
POT_ROOT = Path(
    os.environ.get("VASP_PP_PATH", "/mnt/shared/VASP_POT/POT_GGA_PAW_PBE_54")
)
VASP_PREFIX = os.environ.get("VASP_PREFIX", "/opt/vasp.6.5.1")
OMX_BIN = "/openmx4.0/work/openmx"


def _runner() -> str:
    if shutil.which("singularity"):
        return "singularity"
    if shutil.which("apptainer"):
        return "apptainer"
    raise RuntimeError("need singularity/apptainer")


def write_structures(outdir: Path, element: str, a0: float) -> tuple[Path, Path]:
    from ase.build import bulk
    from ase import Atoms
    from ase.io import write

    bulk_at = bulk(element, "diamond", a=a0, cubic=True)
    bulk_pos = outdir / "POSCAR_bulk"
    write(bulk_pos, bulk_at, format="vasp", vasp5=True, direct=False)
    atom = Atoms(element, positions=[[0, 0, 0]], cell=[16, 16, 16], pbc=True)
    atom_pos = outdir / "POSCAR_atom"
    write(atom_pos, atom, format="vasp", vasp5=True, direct=False)
    return bulk_pos, atom_pos


def run_vasp(case_dir: Path, nprocs: int, timeout: int) -> dict:
    t0 = time.time()
    inner = (
        "source /opt/intel/oneapi/setvars.sh >/dev/null 2>&1 || true; "
        "export PATH=/opt/intel/oneapi/mpi/latest/bin:$PATH; "
        f"mpirun -np {int(nprocs)} {VASP_PREFIX}/bin/vasp_std"
    )
    proc = subprocess.run(
        [
            _runner(), "exec",
            "--bind", f"{case_dir}:{case_dir}",
            "--bind", f"{POT_ROOT}:{POT_ROOT}",
            "--pwd", str(case_dir),
            str(VASP_SIF), "bash", "-lc", inner,
        ],
        capture_output=True, text=True, timeout=timeout,
    )
    log = (proc.stdout or "") + "\n" + (proc.stderr or "")
    (case_dir / "vasp.log").write_text(log, encoding="utf-8")
    energy = None
    osz = case_dir / "OSZICAR"
    if osz.is_file():
        for line in osz.read_text(errors="replace").splitlines()[::-1]:
            m = re.search(r"F=\s*([-\d.E+]+)", line)
            if m:
                energy = float(m.group(1))
                break
    return {
        "ok": energy is not None and "I REFUSE" not in log,
        "energy_eV": energy,
        "wall_s": round(time.time() - t0, 2),
    }


def prepare_vasp_job(
    work: Path,
    poscar: Path,
    element: str,
    *,
    spin: bool,
    kmesh: str,
    encut: float,
    magmom: float,
) -> Path:
    work.mkdir(parents=True, exist_ok=True)
    shutil.copy(poscar, work / "POSCAR")
    pot = POT_ROOT / element / "POTCAR"
    if not pot.is_file():
        raise FileNotFoundError(f"missing POTCAR {pot}")
    shutil.copy(pot, work / "POTCAR")
    incar = f"""SYSTEM = {element} cross Ecoh
PREC = Accurate
ENCUT = {encut}
EDIFF = 1E-6
NELM = 80
ALGO = Normal
LWAVE = .FALSE.
LCHARG = .FALSE.
NSW = 0
IBRION = -1
ISMEAR = 0
SIGMA = 0.05
ISPIN = {2 if spin else 1}
"""
    if spin:
        incar += f"MAGMOM = {magmom}\n"
    (work / "INCAR").write_text(incar)
    (work / "KPOINTS").write_text(f"Gamma\n0\nGamma\n{kmesh}\n0 0 0\n")
    return work


def run_openmx(case_dir: Path, dat_name: str, nprocs: int, timeout: int) -> dict:
    t0 = time.time()
    inner = (
        "source /opt/intel/oneapi/setvars.sh >/dev/null 2>&1 || true; "
        "export PATH=/opt/intel/oneapi/mpi/latest/bin:$PATH; "
        f"mpirun -np {int(nprocs)} {OMX_BIN} {dat_name}"
    )
    proc = subprocess.run(
        [
            _runner(), "exec",
            "--bind", f"{case_dir}:{case_dir}",
            "--bind", f"{DFT_DATA}:{DFT_DATA}",
            "--pwd", str(case_dir),
            str(OMX_SIF), "bash", "-lc", inner,
        ],
        capture_output=True, text=True, timeout=timeout,
    )
    log = (proc.stdout or "") + "\n" + (proc.stderr or "")
    (case_dir / "openmx.log").write_text(log, encoding="utf-8")
    energy_ha = None
    for op in case_dir.glob("*.out"):
        ms = re.findall(r"Utot\.\s+([-\d.]+)", op.read_text(errors="replace"))
        if ms:
            energy_ha = float(ms[-1])
    return {
        "ok": energy_ha is not None,
        "energy_Ha": energy_ha,
        "energy_eV": energy_ha * HA_TO_EV if energy_ha is not None else None,
        "wall_s": round(time.time() - t0, 2),
    }


def prepare_openmx_jobs(
    outdir: Path,
    bulk_pos: Path,
    element: str,
    cfg: dict,
) -> tuple[Path, Path]:
    from omx_tools.generator import generate_input, SCHEMA_PATH, TEMPLATES_PATH
    from omx_tools._utils import load_json
    import json as _json

    os.environ["OPENMX_DFT_DATA_PATH"] = str(DFT_DATA)
    schema = load_json(SCHEMA_PATH, "keywords.json")
    templates = _json.loads(Path(TEMPLATES_PATH).read_text(encoding="utf-8"))

    bulk_dir = outdir / "omx_bulk"
    bulk_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(bulk_pos, bulk_dir / "POSCAR")
    generate_input(
        structure_path=str(bulk_dir / "POSCAR"),
        template_name="scf_band",
        overrides={
            "scf_xctype": "GGA-PBE",
            "scf_energycutoff": 150.0,
            "scf_maxiter": 80,
            "scf_criterion": 1e-9,
            "scf_kgrid": [4, 4, 4],
        },
        schema=schema,
        templates=templates,
        kspacing=0.4,
        dry_run=False,
        verbose=False,
        output_path=str(bulk_dir / f"{element}_bulk.dat"),
    )
    bt = (bulk_dir / f"{element}_bulk.dat").read_text()
    bt = re.sub(
        r"System\.Name\s+\S+",
        f"System.Name        {element}_bulk",
        bt,
        count=1,
    )
    if not re.search(r"scf\.Kgrid", bt):
        bt += "\nscf.Kgrid        4 4 4\n"
    else:
        bt = re.sub(
            r"scf\.Kgrid\s+\S+\s+\S+\s+\S+",
            "scf.Kgrid        4 4 4",
            bt,
        )
    (bulk_dir / f"{element}_bulk.dat").write_text(bt)

    up, down = cfg["atom_up_down"]
    atom_dir = outdir / "omx_atom"
    atom_dir.mkdir(parents=True, exist_ok=True)
    (atom_dir / f"{element}_atom_sp.dat").write_text(
        f"""System.Name        {element}_atom_sp
DATA.PATH        {DFT_DATA}
Species.Number        1
<Definition.of.Atomic.Species
    {cfg["omx_species"]}
Definition.of.Atomic.Species>

Atoms.Number        1
Atoms.SpeciesAndCoordinates.Unit        Ang
<Atoms.SpeciesAndCoordinates
    1  {element}  0.0  0.0  0.0  {up}  {down}
Atoms.SpeciesAndCoordinates>

Atoms.UnitVectors.Unit        Ang
<Atoms.UnitVectors
    16.0  0.0  0.0
    0.0  16.0  0.0
    0.0  0.0  16.0
Atoms.UnitVectors>

scf.SpinPolarization        On
scf.maxIter        150
scf.Mixing.History        15
scf.Mixing.Type        Rmm-Diisk
scf.Mixing.StartPulay        6
scf.ElectronicTemperature        300
scf.energycutoff        150
scf.criterion        1.0e-9
scf.XcType        GGA-PBE
scf.EigenvalueSolver        Cluster
MD.maxIter        1
MD.Type        Nomd
"""
    )
    return bulk_dir, atom_dir


def run_element(
    element: str,
    *,
    outdir: Path,
    nprocs: int,
    timeout: int,
    encut: float,
) -> dict:
    element = element.capitalize()
    if element not in ELEMENT_CFG:
        raise SystemExit(f"unsupported element {element}; use {list(ELEMENT_CFG)}")
    cfg = ELEMENT_CFG[element]
    outdir.mkdir(parents=True, exist_ok=True)
    bulk_pos, atom_pos = write_structures(outdir, element, cfg["a0_A"])
    n_bulk = 8

    report: dict = {
        "kind": "cross_delta_ecoh",
        "element": element,
        "protocol": {
            "structure_bulk": f"{element} diamond cubic a0={cfg['a0_A']} Å fixed",
            "structure_atom": f"{element} free atom, 16 Å box, spin-polarized",
            "ecoh": f"E_atom - E_bulk/{n_bulk}  (eV/atom)",
            "xc": "PBE",
            "note": "Absolute E not compared; Ecoh is a ΔE.",
        },
        "experiment": {"a0_A": cfg["a0_A"], "ecoh_eV": cfg["ecoh_exp_eV"]},
        "ok": False,
    }

    print(f"=== VASP {element} bulk ===")
    vb = prepare_vasp_job(
        outdir / "vasp_bulk",
        bulk_pos,
        element,
        spin=False,
        kmesh="4 4 4",
        encut=encut,
        magmom=cfg["magmom"],
    )
    rb = run_vasp(vb, nprocs, timeout)
    print(" bulk", rb)
    print(f"=== VASP {element} atom ===")
    va = prepare_vasp_job(
        outdir / "vasp_atom",
        atom_pos,
        element,
        spin=True,
        kmesh="1 1 1",
        encut=encut,
        magmom=cfg["magmom"],
    )
    ra = run_vasp(va, nprocs, timeout)
    print(" atom", ra)

    vasp_ok = bool(rb.get("ok") and ra.get("ok"))
    vasp_ecoh = None
    if vasp_ok:
        vasp_ecoh = ra["energy_eV"] - rb["energy_eV"] / n_bulk
    report["vasp"] = {
        "ok": vasp_ok,
        "E_bulk_eV": rb.get("energy_eV"),
        "E_atom_eV": ra.get("energy_eV"),
        "Ecoh_eV": vasp_ecoh,
        "bulk_wall_s": rb.get("wall_s"),
        "atom_wall_s": ra.get("wall_s"),
        "encut_eV": encut,
        "kmesh_bulk": "4 4 4",
    }

    print(f"=== OpenMX {element} bulk+atom ===")
    ob, oa = prepare_openmx_jobs(outdir, bulk_pos, element, cfg)
    rob = run_openmx(ob, f"{element}_bulk.dat", nprocs, timeout)
    print(" bulk", rob)
    roa = run_openmx(oa, f"{element}_atom_sp.dat", nprocs, timeout)
    print(" atom", roa)
    omx_ok = bool(rob.get("ok") and roa.get("ok"))
    omx_ecoh = None
    if omx_ok:
        omx_ecoh = roa["energy_eV"] - rob["energy_eV"] / n_bulk
    report["openmx"] = {
        "ok": omx_ok,
        "E_bulk_eV": rob.get("energy_eV"),
        "E_atom_eV": roa.get("energy_eV"),
        "Ecoh_eV": omx_ecoh,
        "bulk_wall_s": rob.get("wall_s"),
        "atom_wall_s": roa.get("wall_s"),
        "species": cfg["omx_species"],
        "energycutoff_Ry": 150,
        "kmesh_bulk": "4 4 4",
    }

    exp = cfg["ecoh_exp_eV"]
    cmp: dict = {"experiment_ecoh_eV": exp}
    if vasp_ecoh is not None:
        cmp["vasp_minus_exp"] = vasp_ecoh - exp
    if omx_ecoh is not None:
        cmp["openmx_minus_exp"] = omx_ecoh - exp
    if vasp_ecoh is not None and omx_ecoh is not None:
        cmp["vasp_minus_openmx"] = vasp_ecoh - omx_ecoh
        cmp["abs_delta_codes"] = abs(vasp_ecoh - omx_ecoh)
    report["compare"] = cmp
    report["ok"] = bool(vasp_ok and omx_ok)

    (outdir / "report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    md = [
        f"# Cross ΔE: {element} cohesive energy (VASP vs OpenMX)",
        "",
        f"Protocol: fixed a0 = {cfg['a0_A']} Å cubic {element}₈ + spin atom; "
        f"Ecoh = E_atom − E_bulk/{n_bulk} (eV/atom). Absolute E not compared.",
        "",
        "| engine | Ecoh (eV/atom) | vs exp | E_bulk/atom (eV) | E_atom (eV) |",
        "|--------|---------------:|-------:|-----------------:|------------:|",
        f"| experiment | {exp:.2f} | — | — | — |",
    ]
    for eng, key in [("VASP", "vasp"), ("OpenMX", "openmx")]:
        b = report[key]
        if b.get("Ecoh_eV") is None:
            md.append(f"| {eng} | FAIL | | | |")
        else:
            de = b["Ecoh_eV"] - exp
            md.append(
                f"| {eng} | {b['Ecoh_eV']:.4f} | {de:+.4f} | "
                f"{b['E_bulk_eV']/n_bulk:.4f} | {b['E_atom_eV']:.4f} |"
            )
    md += [
        "",
        f"- |Ecoh_VASP − Ecoh_OpenMX| = {cmp.get('abs_delta_codes', 'n/a')}",
        f"- ok: **{report['ok']}**",
        "",
    ]
    (outdir / "REPORT.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--element", choices=sorted(ELEMENT_CFG), default="Si")
    p.add_argument("--np", type=int, default=4)
    p.add_argument("--outdir", type=Path, default=None)
    p.add_argument("--timeout", type=int, default=400)
    p.add_argument("--encut", type=float, default=400.0)
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    el = args.element.capitalize()
    outdir = args.outdir or (
        _REPO / "work" / "benchmarks" / f"cross_delta_ecoh_{el.lower()}"
    )
    report = run_element(
        el,
        outdir=outdir.resolve(),
        nprocs=args.np,
        timeout=args.timeout,
        encut=args.encut,
    )
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"\n=== {el} Ecoh cross-ΔE ===")
        print(f"VASP   Ecoh = {report['vasp'].get('Ecoh_eV')}")
        print(f"OpenMX Ecoh = {report['openmx'].get('Ecoh_eV')}")
        print(f"exp    Ecoh = {report['experiment']['ecoh_eV']}")
        print(f"|VASP-OpenMX| = {report['compare'].get('abs_delta_codes')}")
        print(f"report: {outdir / 'report.json'}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
