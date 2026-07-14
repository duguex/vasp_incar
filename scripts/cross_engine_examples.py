#!/usr/bin/env python3
"""Cross-engine examples: geometry from code A runs SCF on code B.

This is **true cross** (not each-code self-test):

1. **OpenMX → VASP**: official ``input_example/*.dat`` geometries → POSCAR/INCAR/KPOINTS
   + PAW POTCAR → ``vasp_std`` in container.
2. **VASP → OpenMX**: VASP testsuite geometries (POSCAR+INCAR) → ``omx-gen`` ``.dat``
   → ``openmx`` in container.

Mapping of every keyword is **lossy**. Cross success means:

- structure transferred
- target engine **SCF finishes** with finite energy
- (optional) report both energies — they are **not** expected to match numerically

Examples::

    python3 scripts/cross_engine_examples.py --np 4
    python3 scripts/cross_engine_examples.py --np 4 --only omx2vasp
    python3 scripts/cross_engine_examples.py --np 4 --only vasp2omx
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

OMX_SIF = Path(os.environ.get("OPENMX_SIF", "/mnt/shared/openmx4.0_intel.sif"))
VASP_SIF = Path(os.environ.get("VASP_SIF", "/mnt/shared/vasp_latest.sif"))
DFT_DATA = Path(os.environ.get("OPENMX_DFT_DATA_PATH", "/mnt/shared/DFT_DATA19"))
POT_ROOT = Path(
    os.environ.get("VASP_PP_PATH", "/mnt/shared/VASP_POT/POT_GGA_PAW_PBE_54")
)
VASP_PREFIX = os.environ.get("VASP_PREFIX", "/opt/vasp.6.5.1")
OMX_BIN = "/openmx4.0/work/openmx"

# Official OpenMX cases portable enough for a quick VASP SCF (common elements)
DEFAULT_OMX_CASES = ["Ndia2", "Graphite4", "Methane", "H2O"]
# VASP suite cases → OpenMX
DEFAULT_VASP_CASES = ["bulk_BN_PBEsol", "DFT_OatomPBE"]


def _runner() -> str:
    if shutil.which("singularity"):
        return "singularity"
    if shutil.which("apptainer"):
        return "apptainer"
    raise RuntimeError("singularity/apptainer not in PATH")


def atoms_from_omx_dat(path: Path):
    """Parse geometry from OpenMX .dat → ASE Atoms (right-handed cell)."""
    from ase import Atoms

    t = path.read_text(encoding="utf-8", errors="replace")
    m = re.search(
        r"<Atoms\.SpeciesAndCoordinates[^\n]*\n(.*?)\nAtoms\.SpeciesAndCoordinates>",
        t,
        re.S,
    )
    if not m:
        raise ValueError(f"no coordinates in {path}")
    syms, pos = [], []
    for line in m.group(1).splitlines():
        p = line.split()
        if len(p) >= 5:
            syms.append(p[1])
            pos.append([float(p[2]), float(p[3]), float(p[4])])
    um = re.search(
        r"<Atoms\.UnitVectors[^\n]*\n(.*?)\nAtoms\.UnitVectors>",
        t,
        re.S,
    )
    cell = None
    if um:
        cell_lines = []
        for line in um.group(1).splitlines():
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            nums = [float(x) for x in s.split()[:3]]
            if len(nums) == 3:
                cell_lines.append(nums)
        if len(cell_lines) == 3:
            cell = np.array(cell_lines, float)
    if cell is None or abs(float(np.linalg.det(cell))) < 1e-8:
        p = np.array(pos, float)
        L = max(12.0, float((p.max(0) - p.min(0)).max()) + 10.0)
        cell = np.eye(3) * L
        pos = (p - p.mean(0) + L / 2.0).tolist()
    elif float(np.linalg.det(cell)) < 0:
        cell = cell.copy()
        cell[0] *= -1
    return Atoms(symbols=syms, positions=pos, cell=cell, pbc=True)


def write_potcar(elements: list[str], dest: Path) -> None:
    chunks = []
    for el in elements:
        pot = POT_ROOT / el / "POTCAR"
        if not pot.is_file():
            # try bare element name variants
            alts = list(POT_ROOT.glob(f"{el}/POTCAR")) + list(
                POT_ROOT.glob(f"{el}_*/POTCAR")
            )
            if not alts:
                raise FileNotFoundError(f"POTCAR for {el} not under {POT_ROOT}")
            pot = alts[0]
        chunks.append(pot.read_text(encoding="utf-8", errors="replace"))
    dest.write_text("".join(chunks), encoding="utf-8")


def prepare_omx_example_dir(workdir: Path) -> Path:
    """Ensure official input_example exists under workdir."""
    ex = workdir / "input_example"
    if ex.is_dir() and any(ex.glob("*.dat")):
        return ex
    workdir.mkdir(parents=True, exist_ok=True)
    # prefer repo cache from previous runtest
    cached = _REPO / "work" / "benchmarks" / "official_runtest" / "input_example"
    if cached.is_dir():
        shutil.copytree(cached, ex, dirs_exist_ok=True)
        return ex
    r = subprocess.run(
        [
            _runner(),
            "exec",
            "--bind",
            f"{workdir}:{workdir}",
            str(OMX_SIF),
            "bash",
            "-lc",
            f"cp -a /openmx4.0/work/input_example {ex}",
        ],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        raise RuntimeError(f"copy input_example failed: {r.stderr}")
    return ex

HA_TO_EV = 27.211386245988
BOHR_TO_A = 0.529177210903
# F(eV/Å) = F(Ha/Bohr) * HA_TO_EV / BOHR_TO_A
FORCE_HA_BOHR_TO_EV_A = HA_TO_EV / BOHR_TO_A


def extract_vasp_observables(case_dir: Path) -> dict:
    """Zero-point-independent-ish quantities from VASP OUTCAR."""
    outcar = case_dir / "OUTCAR"
    if not outcar.is_file():
        return {}
    text = outcar.read_text(encoding="utf-8", errors="replace")
    obs: dict = {}
    m = re.search(r"external pressure\s*=\s*([-\d.]+)\s*kB", text)
    if m:
        obs["pressure_kbar"] = float(m.group(1))  # VASP "kB" = kbar
    # last TOTAL-FORCE block
    blocks = list(
        re.finditer(
            r"TOTAL-FORCE \(eV/Angst\)\s*\n\s*-+\s*\n(.*?)\n\s*-+",
            text,
            re.S,
        )
    )
    if blocks:
        forces = []
        for line in blocks[-1].group(1).splitlines():
            p = line.split()
            if len(p) >= 6:
                try:
                    forces.append([float(p[3]), float(p[4]), float(p[5])])
                except ValueError:
                    continue
        if forces:
            f = np.array(forces, float)
            norms = np.linalg.norm(f, axis=1)
            obs["force_max_eV_A"] = float(norms.max())
            obs["force_rms_eV_A"] = float(np.sqrt((f ** 2).mean() * 3 / f.size * f.shape[0]) if f.size else 0.0)
            # RMS per atom of |F|
            obs["force_rms_eV_A"] = float(np.sqrt((norms ** 2).mean()))
            obs["n_force_atoms"] = int(len(norms))
    return obs


def extract_openmx_observables(case_dir: Path) -> dict:
    """Forces from OpenMX .out ``<coordinates.forces`` (Hartree/Bohr → eV/Å)."""
    obs: dict = {}
    for op in case_dir.glob("*.out"):
        text = op.read_text(encoding="utf-8", errors="replace")
        m = re.search(
            r"<coordinates\.forces\s*\n(.*?)\ncoordinates\.forces>",
            text,
            re.S,
        )
        forces = []
        if m:
            for line in m.group(1).splitlines():
                p = line.split()
                if len(p) == 1:
                    continue  # atom count
                # idx species x y z fx fy fz
                if len(p) >= 8:
                    try:
                        forces.append([float(p[5]), float(p[6]), float(p[7])])
                    except ValueError:
                        continue
        if forces:
            f = np.array(forces, float) * FORCE_HA_BOHR_TO_EV_A
            norms = np.linalg.norm(f, axis=1)
            obs["force_max_eV_A"] = float(norms.max())
            obs["force_rms_eV_A"] = float(np.sqrt((norms ** 2).mean()))
            obs["n_force_atoms"] = int(len(norms))
            obs["force_unit_converted_from"] = "Ha/Bohr"
            break
    return obs



def run_vasp_scf(case_dir: Path, nprocs: int, timeout: int) -> dict:
    t0 = time.time()
    inner = (
        "source /opt/intel/oneapi/setvars.sh >/dev/null 2>&1 || true; "
        "export PATH=/opt/intel/oneapi/mpi/latest/bin:$PATH; "
        f"mpirun -np {int(nprocs)} {VASP_PREFIX}/bin/vasp_std"
    )
    proc = subprocess.run(
        [
            _runner(),
            "exec",
            "--bind",
            f"{case_dir}:{case_dir}",
            "--bind",
            f"{POT_ROOT}:{POT_ROOT}",
            "--pwd",
            str(case_dir),
            str(VASP_SIF),
            "bash",
            "-lc",
            inner,
        ],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    (case_dir / "vasp_run.log").write_text(out, encoding="utf-8")
    energy = None
    osz = case_dir / "OSZICAR"
    if osz.is_file():
        for line in osz.read_text(errors="replace").splitlines()[::-1]:
            m = re.search(r"F=\s*([-\d.E+]+)", line)
            if m:
                energy = float(m.group(1))
                break
    ok = energy is not None and "I REFUSE TO CONTINUE" not in out
    obs = extract_vasp_observables(case_dir)
    return {
        "ok": ok,
        "energy_eV": energy,
        "observables": obs,
        "wall_s": round(time.time() - t0, 2),
        "returncode": proc.returncode,
        "log_tail": out[-1500:],
    }


def run_openmx_scf(case_dir: Path, dat_name: str, nprocs: int, timeout: int) -> dict:
    t0 = time.time()
    inner = (
        "source /opt/intel/oneapi/setvars.sh >/dev/null 2>&1 || true; "
        "export PATH=/opt/intel/oneapi/mpi/latest/bin:$PATH; "
        f"mpirun -np {int(nprocs)} {OMX_BIN} {dat_name}"
    )
    proc = subprocess.run(
        [
            _runner(),
            "exec",
            "--bind",
            f"{case_dir}:{case_dir}",
            "--bind",
            f"{DFT_DATA}:{DFT_DATA}",
            "--pwd",
            str(case_dir),
            str(OMX_SIF),
            "bash",
            "-lc",
            inner,
        ],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    (case_dir / "openmx_run.log").write_text(out, encoding="utf-8")
    # System.Name drives .out name
    outs = list(case_dir.glob("*.out"))
    energy_ha = None
    for op in outs:
        m = re.findall(r"Utot\.\s+([-\d.]+)", op.read_text(errors="replace"))
        if m:
            energy_ha = float(m[-1])
    finished = "normally finished" in out.lower() or energy_ha is not None
    obs = extract_openmx_observables(case_dir)
    return {
        "ok": bool(finished and energy_ha is not None),
        "energy_Ha": energy_ha,
        "energy_eV": energy_ha * HA_TO_EV if energy_ha is not None else None,
        "observables": obs,
        "wall_s": round(time.time() - t0, 2),
        "returncode": proc.returncode,
        "log_tail": out[-1500:],
    }


def omx_to_vasp_case(
    name: str,
    dat: Path,
    outdir: Path,
    nprocs: int,
    timeout: int,
) -> dict:
    from ase.io import write

    outdir.mkdir(parents=True, exist_ok=True)
    rec: dict = {
        "direction": "openmx→vasp",
        "source": str(dat),
        "name": name,
        "case_dir": str(outdir),
    }
    try:
        atoms = atoms_from_omx_dat(dat)
        write(outdir / "POSCAR", atoms, vasp5=True, sort=True)
        # target-native safe INCAR (lossy mapping on purpose)
        formula = atoms.get_chemical_formula()
        incar = f"""SYSTEM = cross from OpenMX {name} ({formula})
PREC = Normal
ENCUT = 400
EDIFF = 1E-5
NELM = 40
ISMEAR = 0
SIGMA = 0.1
ALGO = Fast
LWAVE = .FALSE.
LCHARG = .FALSE.
NSW = 0
IBRION = -1
ISPIN = 1
"""
        (outdir / "INCAR").write_text(incar)
        # k-mesh: Gamma 3x3x3 crystals; 1x1x1 molecules-ish
        cell_vol = abs(float(np.linalg.det(atoms.cell.array)))
        if cell_vol > 800 or len(atoms) <= 5 and max(atoms.cell.lengths()) > 10:
            kpts = "1 1 1"
        else:
            kpts = "3 3 3"
        (outdir / "KPOINTS").write_text(
            f"Auto from cross_engine\n0\nGamma\n{kpts}\n0 0 0\n"
        )
        # unique elements in POSCAR order
        from ase.io import read

        a2 = read(outdir / "POSCAR")
        # preserve POSCAR element order
        lines = (outdir / "POSCAR").read_text().splitlines()
        elems = lines[5].split()
        write_potcar(elems, outdir / "POTCAR")
        rec["elements"] = elems
        rec["n_atoms"] = len(atoms)
        rec["kpoints"] = kpts
        run = run_vasp_scf(outdir, nprocs=nprocs, timeout=timeout)
        rec["run_vasp"] = run
        rec["run"] = run  # backward compatible

        # Same geometry on OpenMX (source .dat) for comparable force/pressure-like metrics
        omx_dir = outdir / "openmx_same_geom"
        omx_dir.mkdir(exist_ok=True)
        dat_copy = omx_dir / f"{name}.dat"
        text = dat.read_text(encoding="utf-8", errors="replace")
        text = re.sub(
            r"DATA\.PATH\s+\S+",
            f"DATA.PATH        {DFT_DATA}",
            text,
        )
        # shorten SCF if maxIter huge
        text = re.sub(r"scf\.maxIter\s+\d+", "scf.maxIter        40", text, flags=re.I)
        dat_copy.write_text(text, encoding="utf-8")
        run_omx = run_openmx_scf(omx_dir, dat_copy.name, nprocs=nprocs, timeout=timeout)
        rec["run_openmx_same_geom"] = run_omx

        # Comparable observables (NOT absolute energy)
        vobs = run.get("observables") or {}
        oobs = run_omx.get("observables") or {}
        comparable: dict = {
            "note": (
                "Absolute total energy is NOT comparable across codes. "
                "Forces at the same geometry and ΔE-type quantities are."
            ),
            "vasp_force_max_eV_A": vobs.get("force_max_eV_A"),
            "vasp_force_rms_eV_A": vobs.get("force_rms_eV_A"),
            "vasp_pressure_kbar": vobs.get("pressure_kbar"),
            "openmx_force_max_eV_A": oobs.get("force_max_eV_A"),
            "openmx_force_rms_eV_A": oobs.get("force_rms_eV_A"),
            "vasp_energy_eV": run.get("energy_eV"),
            "openmx_energy_eV": run_omx.get("energy_eV"),
        }
        if (
            vobs.get("force_max_eV_A") is not None
            and oobs.get("force_max_eV_A") is not None
        ):
            comparable["delta_force_max_eV_A"] = abs(
                vobs["force_max_eV_A"] - oobs["force_max_eV_A"]
            )
            comparable["delta_force_rms_eV_A"] = abs(
                (vobs.get("force_rms_eV_A") or 0)
                - (oobs.get("force_rms_eV_A") or 0)
            )
        rec["comparable"] = comparable
        rec["ok"] = bool(run.get("ok"))  # primary: cross-engine VASP ran
        rec["ok_both_engines"] = bool(run.get("ok") and run_omx.get("ok"))
    except Exception as e:
        rec["ok"] = False
        rec["error"] = str(e)
    return rec


def fetch_vasp_suite_case(name: str, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    src_host = Path.home() / "hack_vasp" / "testsuite" / "tests" / name
    if src_host.is_dir() and (src_host / "POSCAR").is_file():
        for f in src_host.iterdir():
            if f.is_file():
                shutil.copy2(f, dest / f.name)
        return dest
    # from container
    r = subprocess.run(
        [
            _runner(),
            "exec",
            "--bind",
            f"{dest.parent}:{dest.parent}",
            str(VASP_SIF),
            "bash",
            "-lc",
            f"cp -a {VASP_PREFIX}/testsuite/tests/{name}/. {dest}/",
        ],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0 or not (dest / "POSCAR").is_file():
        raise FileNotFoundError(f"VASP suite case {name} not found: {r.stderr}")
    return dest


def vasp_to_omx_case(
    name: str,
    outdir: Path,
    nprocs: int,
    timeout: int,
) -> dict:
    from omx_tools.generator import generate_input, SCHEMA_PATH, TEMPLATES_PATH
    from omx_tools._utils import load_json
    import json as _json

    outdir.mkdir(parents=True, exist_ok=True)
    rec: dict = {
        "direction": "vasp→openmx",
        "name": name,
        "case_dir": str(outdir),
    }
    try:
        suite_dir = outdir / "suite_src"
        fetch_vasp_suite_case(name, suite_dir)
        poscar = suite_dir / "POSCAR"
        # pick first INCAR.* 
        incars = sorted(suite_dir.glob("INCAR*"))
        if not incars:
            raise FileNotFoundError("no INCAR in suite case")
        shutil.copy(poscar, outdir / "POSCAR")
        shutil.copy(incars[0], outdir / "INCAR.source")

        os.environ["OPENMX_DFT_DATA_PATH"] = str(DFT_DATA)
        schema = load_json(SCHEMA_PATH, "keywords.json")
        templates = _json.loads(Path(TEMPLATES_PATH).read_text(encoding="utf-8"))
        dat = outdir / "input.dat"
        # structure-first generation with safe OpenMX defaults (not broken GGA map)
        generate_input(
            structure_path=str(outdir / "POSCAR"),
            template_name="scf_band" if name != "DFT_OatomPBE" else "scf_cluster",
            overrides={
                "scf_xctype": "GGA-PBE",
                "scf_energycutoff": 150.0,
                "scf_maxiter": 50,
                "scf_criterion": 1e-8,
            },
            schema=schema,
            templates=templates,
            kspacing=0.5,
            dry_run=False,
            verbose=False,
            output_path=str(dat),
        )
        # force System.Name
        text = dat.read_text(encoding="utf-8")
        text = re.sub(r"System\.Name\s+\S+", f"System.Name        {name.replace('=', '_')}", text, count=1)
        if "scf.EigenvalueSolver" not in text and name == "DFT_OatomPBE":
            text += "\nscf.EigenvalueSolver        Cluster\n"
        dat.write_text(text)
        rec["dat"] = str(dat)
        run = run_openmx_scf(outdir, dat.name, nprocs=nprocs, timeout=timeout)
        rec["run"] = run
        rec["ok"] = bool(run.get("ok"))
    except Exception as e:
        rec["ok"] = False
        rec["error"] = str(e)
    return rec


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--np", type=int, default=4)
    p.add_argument(
        "--outdir",
        type=Path,
        default=_REPO / "work" / "benchmarks" / "cross_engine",
    )
    p.add_argument("--timeout", type=int, default=300)
    p.add_argument("--only", choices=["omx2vasp", "vasp2omx", "all"], default="all")
    p.add_argument("--omx-cases", nargs="+", default=DEFAULT_OMX_CASES)
    p.add_argument("--vasp-cases", nargs="+", default=DEFAULT_VASP_CASES)
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    outdir = args.outdir.resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    report: dict = {
        "kind": "cross_engine_examples",
        "definition": (
            "Geometry from official examples of code A is SCF'd on code B. "
            "Absolute total energies are NOT comparable; forces at the same "
            "geometry, pressure/stress, and ΔE-type quantities are."
        ),
        "comparable_quantities": [
            "force_max / force_rms at identical geometry (eV/Å)",
            "external pressure / stress (same cell)",
            "energy differences ΔE (Ecoh, isomer gaps) — not absolute E",
            "relaxed lattice constants / bond lengths",
        ],
        "np": args.np,
        "cases": [],
        "ok": False,
    }

    if args.only in ("omx2vasp", "all"):
        ex = prepare_omx_example_dir(outdir / "omx_sources")
        for name in args.omx_cases:
            dat = ex / f"{name}.dat"
            if not dat.is_file():
                report["cases"].append({
                    "direction": "openmx→vasp",
                    "name": name,
                    "ok": False,
                    "error": f"missing {dat}",
                })
                continue
            rec = omx_to_vasp_case(
                name, dat, outdir / "omx2vasp" / name, args.np, args.timeout,
            )
            report["cases"].append(rec)
            status = "OK" if rec.get("ok") else "FAIL"
            e = (rec.get("run") or {}).get("energy_eV")
            comp = rec.get("comparable") or {}
            print(
                f"[openmx→vasp] {name}: {status} "
                f"E_vasp={e} |F|_max V/O="
                f"{comp.get('vasp_force_max_eV_A')}/"
                f"{comp.get('openmx_force_max_eV_A')} "
                f"Δ|F|_max={comp.get('delta_force_max_eV_A')}"
            )

    if args.only in ("vasp2omx", "all"):
        for name in args.vasp_cases:
            rec = vasp_to_omx_case(
                name, outdir / "vasp2omx" / name, args.np, args.timeout,
            )
            report["cases"].append(rec)
            status = "OK" if rec.get("ok") else "FAIL"
            e = (rec.get("run") or {}).get("energy_eV")
            print(f"[vasp→openmx] {name}: {status} E={e}")

    n = len(report["cases"])
    n_ok = sum(1 for c in report["cases"] if c.get("ok"))
    report["n_cases"] = n
    report["n_ok"] = n_ok
    report["ok"] = n > 0 and n_ok == n

    (outdir / "report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    # markdown
    lines = [
        "# Cross-engine examples",
        "",
        report["definition"],
        "",
        "### What is comparable?",
        "",
    ]
    for q in report.get("comparable_quantities") or []:
        lines.append(f"- {q}")
    lines += [
        "",
        f"- ok: **{report['ok']}** ({n_ok}/{n})",
        f"- np: {args.np}",
        "",
        "| direction | case | ok | E (target eV) | |F|_max VASP | |F|_max OMX | Δ|F|_max | P (kbar) |",
        "|-----------|------|:--:|-------------:|------------:|-----------:|---------:|---------:|",
    ]
    for c in report["cases"]:
        run = c.get("run") or {}
        e = run.get("energy_eV")
        comp = c.get("comparable") or {}
        vobs = (run.get("observables") or {})
        lines.append(
            f"| {c.get('direction')} | `{c.get('name')}` | "
            f"{'Y' if c.get('ok') else 'N'} | "
            f"{e if e is not None else c.get('error', '')} | "
            f"{comp.get('vasp_force_max_eV_A', vobs.get('force_max_eV_A', ''))} | "
            f"{comp.get('openmx_force_max_eV_A', '')} | "
            f"{comp.get('delta_force_max_eV_A', '')} | "
            f"{comp.get('vasp_pressure_kbar', vobs.get('pressure_kbar', ''))} |"
        )
    lines += [
        "",
        "## Pass criteria",
        "",
        "1. Geometry from official source example",
        "2. Target engine SCF finishes with finite energy (cross runnable)",
        "3. Absolute E is **not** a pass criterion across codes",
        "4. When both engines run same geom: report |F| and pressure for comparison",
        "",
    ]
    (outdir / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"\n=== cross-engine summary: {n_ok}/{n} ok ===")
        print(f"report: {outdir / 'report.json'}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
