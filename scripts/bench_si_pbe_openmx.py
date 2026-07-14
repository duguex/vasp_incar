#!/usr/bin/env python3
"""Si diamond PBE benchmark via omx-gen + OpenMX (MPI).

Compares:
  - lattice fixed at experimental cubic a0 = 5.431 Å
  - cohesive energy Ecoh = E(atom) − E(bulk)/N  vs experiment ~4.63 eV/atom

Requires:
  - singularity/apptainer + OpenMX SIF
  - DFT_DATA19 (OPENMX_DFT_DATA_PATH)
  - Intel MPI inside container (``mpirun -np N``)

Example::

    python3 scripts/bench_si_pbe_openmx.py --np 8
    python3 scripts/bench_si_pbe_openmx.py --np 8 --outdir work/benchmarks/si_pbe
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

HARTREE_EV = 27.211386245988
EXP_A0_A = 5.431  # cubic diamond Si, Å
EXP_ECOH_EV = 4.63  # eV/atom (room-temp experimental cohesive energy)
DEFAULT_CONTAINER = Path("/mnt/shared/openmx4.0_intel.sif")
DEFAULT_DFT_DATA = Path(
    os.environ.get("OPENMX_DFT_DATA_PATH", "/mnt/shared/DFT_DATA19")
)
DEFAULT_OPENMX_BIN = "/openmx4.0/work/openmx"


def parse_openmx_out(path: Path) -> dict:
    """Parse SCF history and Utot from OpenMX ``.out``."""
    text = path.read_text(encoding="utf-8", errors="replace")
    scf = re.findall(
        r"SCF=\s*(\d+)\s+NormRD=\s*([0-9.eE+\-nanNAN]+)\s+Uele=\s*([-\d.eE+nanNAN]+)",
        text,
    )
    utot = re.findall(r"Utot\.\s+([-\d.]+)", text)
    finished = "normally finished" in text.lower()
    last = scf[-1] if scf else None
    normrd = None
    if last:
        try:
            normrd = float(last[1])
        except ValueError:
            normrd = None
    utot_ha = float(utot[-1]) if utot else None
    return {
        "path": str(path),
        "finished_banner": finished,
        "n_scf": int(last[0]) if last else None,
        "normrd": normrd,
        "utot_ha": utot_ha,
        "utot_ev": utot_ha * HARTREE_EV if utot_ha is not None else None,
        "converged": (normrd is not None and normrd < 1e-8 and utot_ha is not None),
    }


def _write_structures(outdir: Path) -> tuple[Path, Path]:
    from ase.build import bulk
    from ase import Atoms
    from ase.io import write

    bulk_atoms = bulk("Si", "diamond", a=EXP_A0_A, cubic=True)
    bulk_cif = outdir / "Si8_cubic_exp.cif"
    write(str(bulk_cif), bulk_atoms)

    atom = Atoms("Si", positions=[[0.0, 0.0, 0.0]], cell=[20.0, 20.0, 20.0], pbc=True)
    atom_xyz = outdir / "Si_atom.xyz"
    write(str(atom_xyz), atom)
    return bulk_cif, atom_xyz


def _generate_inputs(
    outdir: Path,
    bulk_cif: Path,
    atom_xyz: Path,
    *,
    energycutoff: float,
    kgrid: tuple[int, int, int],
    scf_maxiter: int,
) -> tuple[Path, Path]:
    import json as _json
    from omx_tools.generator import generate_input, SCHEMA_PATH, TEMPLATES_PATH
    from omx_tools._utils import load_json

    schema = load_json(SCHEMA_PATH, "keywords.json")
    templates = _json.loads(Path(TEMPLATES_PATH).read_text(encoding="utf-8"))

    bulk_dat = outdir / "Si_bulk.dat"
    atom_dat = outdir / "Si_atom_sp.dat"

    os.environ["OPENMX_DFT_DATA_PATH"] = str(DEFAULT_DFT_DATA)

    generate_input(
        structure_path=str(bulk_cif),
        template_name="scf_band",
        overrides={
            "scf_maxiter": scf_maxiter,
            "scf_energycutoff": energycutoff,
            "scf_criterion": 1e-9,
            "scf_kgrid": list(kgrid),
        },
        schema=schema,
        templates=templates,
        kspacing=0.5,
        dry_run=False,
        verbose=False,
        output_path=str(bulk_dat),
    )
    # force System.Name
    btxt = bulk_dat.read_text(encoding="utf-8")
    btxt = re.sub(r"System\.Name\s+\S+", "System.Name        Si_bulk", btxt, count=1)
    if not re.search(r"scf\.Kgrid", btxt):
        btxt += f"\nscf.Kgrid        {kgrid[0]} {kgrid[1]} {kgrid[2]}\n"
    else:
        btxt = re.sub(
            r"scf\.Kgrid\s+\S+\s+\S+\s+\S+",
            f"scf.Kgrid        {kgrid[0]} {kgrid[1]} {kgrid[2]}",
            btxt,
        )
    bulk_dat.write_text(btxt)

    # spin-polarized free atom (triplet-like init occupations)
    atom_body = f"""System.Name        Si_atom_sp
DATA.PATH        {DEFAULT_DFT_DATA}
Species.Number        1
<Definition.of.Atomic.Species
    Si  Si8.0-s2p2d1  Si_PBE19
Definition.of.Atomic.Species>

Atoms.Number        1
Atoms.SpeciesAndCoordinates.Unit        Ang
<Atoms.SpeciesAndCoordinates
    1  Si  0.0  0.0  0.0  3.0  1.0
Atoms.SpeciesAndCoordinates>

Atoms.UnitVectors.Unit        Ang
<Atoms.UnitVectors
    20.0  0.0  0.0
    0.0  20.0  0.0
    0.0  0.0  20.0
Atoms.UnitVectors>

scf.SpinPolarization        On
scf.maxIter        {max(scf_maxiter, 150)}
scf.Mixing.History        15
scf.Mixing.Type        Rmm-Diisk
scf.Mixing.StartPulay        6
scf.ElectronicTemperature        300
scf.energycutoff        {energycutoff}
scf.criterion        1.0e-9
scf.XcType        GGA-PBE
scf.EigenvalueSolver        Cluster
MD.maxIter        1
MD.Type        Nomd
"""
    atom_dat.write_text(atom_body)
    return bulk_dat, atom_dat


def run_openmx(
    dat: Path,
    *,
    np: int,
    container: Path,
    cwd: Path,
    timeout: int,
) -> subprocess.CompletedProcess:
    """``mpirun -np N openmx input.dat`` inside the SIF."""
    if not container.is_file():
        raise FileNotFoundError(f"OpenMX container missing: {container}")
    if not shutil.which("singularity") and not shutil.which("apptainer"):
        raise RuntimeError("singularity/apptainer not in PATH")
    runner = "singularity" if shutil.which("singularity") else "apptainer"
    # Shell inside container: source oneAPI if present, then mpirun
    inner = (
        "source /opt/intel/oneapi/setvars.sh >/dev/null 2>&1 || true; "
        "export PATH=/opt/intel/oneapi/mpi/latest/bin:$PATH; "
        f"mpirun -np {int(np)} {DEFAULT_OPENMX_BIN} {dat.name}"
    )
    cmd = [
        runner,
        "exec",
        "--bind",
        f"{DEFAULT_DFT_DATA}:{DEFAULT_DFT_DATA}",
        str(container),
        "bash",
        "-lc",
        inner,
    ]
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def run_benchmark(
    *,
    outdir: Path,
    np: int,
    container: Path,
    energycutoff: float,
    kgrid: tuple[int, int, int],
    scf_maxiter: int,
    timeout: int,
    skip_run: bool,
) -> dict:
    outdir.mkdir(parents=True, exist_ok=True)
    report: dict = {
        "method": {
            "code": "OpenMX 4.0",
            "xc": "GGA-PBE",
            "basis": "Si8.0-s2p2d1 / Si_PBE19",
            "energycutoff_Ry": energycutoff,
            "kgrid_bulk": list(kgrid),
            "mpi_np": np,
            "a0_input_A": EXP_A0_A,
            "lattice": "fixed experimental cubic (no EOS relaxation)",
        },
        "references": {
            "a0_exp_A": EXP_A0_A,
            "ecoh_exp_eV": EXP_ECOH_EV,
            "notes": (
                "Experimental cohesive energy ~4.63 eV/atom (Si diamond). "
                "PBE literature often ~4.55–4.65 depending on basis/pseudopotential. "
                "This run fixes a0; Ecoh is not from a fully optimized EOS."
            ),
        },
        "ok": False,
    }

    bulk_cif, atom_xyz = _write_structures(outdir)
    bulk_dat, atom_dat = _generate_inputs(
        outdir,
        bulk_cif,
        atom_xyz,
        energycutoff=energycutoff,
        kgrid=kgrid,
        scf_maxiter=scf_maxiter,
    )
    report["inputs"] = {
        "bulk_structure": str(bulk_cif),
        "atom_structure": str(atom_xyz),
        "bulk_dat": str(bulk_dat),
        "atom_dat": str(atom_dat),
        "natoms_bulk": 8,
    }

    if not skip_run:
        t0 = time.time()
        rb = run_openmx(bulk_dat, np=np, container=container, cwd=outdir, timeout=timeout)
        (outdir / "Si_bulk.mpirun.log").write_text(
            (rb.stdout or "") + "\n" + (rb.stderr or "")
        )
        report["bulk_wall_s"] = round(time.time() - t0, 2)

        t1 = time.time()
        ra = run_openmx(atom_dat, np=np, container=container, cwd=outdir, timeout=timeout)
        (outdir / "Si_atom_sp.mpirun.log").write_text(
            (ra.stdout or "") + "\n" + (ra.stderr or "")
        )
        report["atom_wall_s"] = round(time.time() - t1, 2)

    bulk_out = outdir / "Si_bulk.out"
    atom_out = outdir / "Si_atom_sp.out"
    if not bulk_out.is_file() or not atom_out.is_file():
        report["error"] = "missing .out files — OpenMX run failed or --skip-run without prior outputs"
        report["bulk_out_exists"] = bulk_out.is_file()
        report["atom_out_exists"] = atom_out.is_file()
        return report

    bulk = parse_openmx_out(bulk_out)
    atom = parse_openmx_out(atom_out)
    report["bulk"] = bulk
    report["atom"] = atom

    n = 8
    if bulk["utot_ha"] is None or atom["utot_ha"] is None:
        report["error"] = "could not parse Utot"
        return report

    e_bulk_atom_ha = bulk["utot_ha"] / n
    ecoh_ha = atom["utot_ha"] - e_bulk_atom_ha
    ecoh_ev = ecoh_ha * HARTREE_EV
    report["energies"] = {
        "E_bulk_total_Ha": bulk["utot_ha"],
        "E_bulk_total_eV": bulk["utot_ev"],
        "E_bulk_per_atom_Ha": e_bulk_atom_ha,
        "E_bulk_per_atom_eV": e_bulk_atom_ha * HARTREE_EV,
        "E_atom_Ha": atom["utot_ha"],
        "E_atom_eV": atom["utot_ev"],
        "Ecoh_eV_per_atom": ecoh_ev,
        "Ecoh_exp_eV_per_atom": EXP_ECOH_EV,
        "delta_Ecoh_eV": ecoh_ev - EXP_ECOH_EV,
        "rel_err_pct": 100.0 * (ecoh_ev - EXP_ECOH_EV) / EXP_ECOH_EV,
    }
    report["structure"] = {
        "a0_input_A": EXP_A0_A,
        "a0_exp_A": EXP_A0_A,
        "delta_a0_A": 0.0,
        "note": "a0 fixed at experiment; no cell relaxation in this benchmark",
    }
    report["ok"] = bool(bulk.get("converged") and atom.get("converged"))
    return report


def write_markdown(report: dict, path: Path) -> None:
    e = report.get("energies") or {}
    m = report.get("method") or {}
    lines = [
        "# Si diamond PBE / OpenMX benchmark",
        "",
        "## Setup",
        "",
        f"- Code: {m.get('code')}  XC: {m.get('xc')}",
        f"- Basis: `{m.get('basis')}`",
        f"- Energy cutoff: {m.get('energycutoff_Ry')} Ry",
        f"- Bulk k-grid: {m.get('kgrid_bulk')}",
        f"- MPI: `-np {m.get('mpi_np')}`",
        f"- Lattice: fixed cubic a0 = {m.get('a0_input_A')} Å (experimental)",
        "",
        "## Results",
        "",
        "| Quantity | Value | Reference | Δ |",
        "|----------|------:|----------:|--:|",
    ]
    if e:
        lines += [
            f"| a0 (Å) | {report['structure']['a0_input_A']:.3f} | "
            f"{report['structure']['a0_exp_A']:.3f} | fixed |",
            f"| Ecoh (eV/atom) | {e['Ecoh_eV_per_atom']:.4f} | "
            f"{e['Ecoh_exp_eV_per_atom']:.2f} | {e['delta_Ecoh_eV']:+.4f} |",
            f"| E_bulk/atom (eV) | {e['E_bulk_per_atom_eV']:.4f} | — | — |",
            f"| E_atom (eV) | {e['E_atom_eV']:.4f} | — | — |",
            "",
            f"- Bulk SCF: n={report['bulk'].get('n_scf')} "
            f"NormRD={report['bulk'].get('normrd')}",
            f"- Atom SCF: n={report['atom'].get('n_scf')} "
            f"NormRD={report['atom'].get('normrd')}",
            f"- Wall (s): bulk={report.get('bulk_wall_s')} atom={report.get('atom_wall_s')}",
        ]
    lines += [
        "",
        "## Caveats",
        "",
        "- **Not** a full EOS / lattice optimization — a0 is clamped to experiment.",
        "- Cohesive energy depends on free-atom setup (spin, box, mixing).",
        "- Agreement with experiment can be partly fortuitous for a given basis;",
        "  treat as pipeline validation + order-of-magnitude physics check.",
        "",
        f"- ok={report.get('ok')}",
        "",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--np", type=int, default=8, help="MPI ranks (default 8)")
    p.add_argument(
        "--outdir",
        type=Path,
        default=_REPO / "work" / "benchmarks" / "si_pbe",
    )
    p.add_argument("--container", type=Path, default=DEFAULT_CONTAINER)
    p.add_argument("--energycutoff", type=float, default=150.0, help="Ry")
    p.add_argument("--kgrid", type=int, nargs=3, default=[4, 4, 4])
    p.add_argument("--scf-maxiter", type=int, default=80)
    p.add_argument("--timeout", type=int, default=600)
    p.add_argument(
        "--skip-run",
        action="store_true",
        help="Only parse existing .out in outdir (no OpenMX launch)",
    )
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    if not DEFAULT_DFT_DATA.is_dir() and not args.skip_run:
        print(
            json.dumps({
                "error": f"DFT_DATA missing: {DEFAULT_DFT_DATA}",
                "hint": "export OPENMX_DFT_DATA_PATH=...",
            }),
            file=sys.stderr,
        )
        return 2

    report = run_benchmark(
        outdir=args.outdir.resolve(),
        np=args.np,
        container=args.container,
        energycutoff=args.energycutoff,
        kgrid=tuple(args.kgrid),
        scf_maxiter=args.scf_maxiter,
        timeout=args.timeout,
        skip_run=args.skip_run,
    )
    args.outdir.mkdir(parents=True, exist_ok=True)
    (args.outdir / "report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    write_markdown(report, args.outdir / "REPORT.md")

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        e = report.get("energies") or {}
        print("=== Si PBE OpenMX benchmark ===")
        print(f"outdir: {args.outdir}")
        print(f"ok: {report.get('ok')}")
        if e:
            print(
                f"Ecoh = {e['Ecoh_eV_per_atom']:.4f} eV/atom "
                f"(exp {e['Ecoh_exp_eV_per_atom']:.2f}, "
                f"Δ={e['delta_Ecoh_eV']:+.4f}, "
                f"{e['rel_err_pct']:+.2f}%)"
            )
            print(f"a0 fixed at {EXP_A0_A} Å (experimental)")
        if report.get("error"):
            print("error:", report["error"])
        print(f"report: {args.outdir / 'report.json'}")
        print(f"md:     {args.outdir / 'REPORT.md'}")
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
