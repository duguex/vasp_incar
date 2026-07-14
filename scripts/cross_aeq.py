#!/usr/bin/env python3
"""Light lattice scan: estimate a_eq from E(a) on VASP and OpenMX.

Protocol
--------
- Diamond cubic 8-atom cell (Si or C)
- Scales of experimental a0: default 0.98 … 1.02 (5 points)
- Fixed k-mesh / cutoff per code; single-point SCF each
- Fit E(s) = c0 + c1 s + c2 s^2  with s = a/a0_exp; a_eq = a0_exp * (-c1/(2 c2))

Compares a_eq across codes and to experiment (soft). Absolute E not compared.

Examples::

    python3 scripts/cross_aeq.py --element Si --np 4
    python3 scripts/cross_aeq.py --element C --np 4 --scales 0.98 1.00 1.02
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

import numpy as np

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

HA_TO_EV = 27.211386245988
ELEMENT_CFG = {
    "Si": {"a0_exp": 5.431},
    "C": {"a0_exp": 3.567},
}

OMX_SIF = Path(os.environ.get("OPENMX_SIF", "/mnt/shared/openmx4.0_intel.sif"))
VASP_SIF = Path(os.environ.get("VASP_SIF", "/mnt/shared/vasp_latest.sif"))
DFT_DATA = Path(os.environ.get("OPENMX_DFT_DATA_PATH", "/mnt/shared/DFT_DATA19"))
POT_ROOT = Path(
    os.environ.get("VASP_PP_PATH", "/mnt/shared/VASP_POT/POT_GGA_PAW_PBE_54")
)
VASP_PREFIX = os.environ.get("VASP_PREFIX", "/opt/vasp.6.5.1")
OMX_BIN = "/openmx4.0/work/openmx"

# hard: |a_eq_V - a_eq_O| / a0_exp
TOL_AEQ_REL = float(os.environ.get("CROSS_AEQ_TOL_REL", "0.01"))  # 1%


def _runner() -> str:
    if shutil.which("singularity"):
        return "singularity"
    if shutil.which("apptainer"):
        return "apptainer"
    raise RuntimeError("need singularity/apptainer")


def fit_aeq(scales: list[float], energies: list[float], a0_exp: float) -> dict:
    s = np.array(scales, float)
    e = np.array(energies, float)
    # E = c0 + c1 s + c2 s^2
    A = np.column_stack([np.ones_like(s), s, s ** 2])
    coef, *_ = np.linalg.lstsq(A, e, rcond=None)
    c0, c1, c2 = coef
    if abs(c2) < 1e-12:
        return {"ok": False, "error": "flat fit"}
    s_eq = -c1 / (2 * c2)
    a_eq = a0_exp * float(s_eq)
    return {
        "ok": True,
        "a_eq_A": a_eq,
        "s_eq": float(s_eq),
        "coef": {"c0": float(c0), "c1": float(c1), "c2": float(c2)},
        "E_min_eV": float(c0 + c1 * s_eq + c2 * s_eq ** 2),
    }


def run_vasp_point(
    work: Path, element: str, a: float, nprocs: int, timeout: int, encut: float
) -> float:
    from ase.build import bulk
    from ase.io import write

    work.mkdir(parents=True, exist_ok=True)
    write(work / "POSCAR", bulk(element, "diamond", a=a, cubic=True), format="vasp", vasp5=True)
    shutil.copy(POT_ROOT / element / "POTCAR", work / "POTCAR")
    (work / "INCAR").write_text(
        f"""SYSTEM = {element} a={a:.5f}
PREC = Normal
ENCUT = {encut}
EDIFF = 1E-6
NELM = 60
ISMEAR = 0
SIGMA = 0.05
ISPIN = 1
LWAVE = .FALSE.
LCHARG = .FALSE.
NSW = 0
IBRION = -1
"""
    )
    (work / "KPOINTS").write_text("M\n0\nGamma\n3 3 3\n0 0 0\n")
    inner = (
        "source /opt/intel/oneapi/setvars.sh >/dev/null 2>&1 || true; "
        "export PATH=/opt/intel/oneapi/mpi/latest/bin:$PATH; "
        f"mpirun -np {int(nprocs)} {VASP_PREFIX}/bin/vasp_std"
    )
    subprocess.run(
        [
            _runner(), "exec",
            "--bind", f"{work}:{work}",
            "--bind", f"{POT_ROOT}:{POT_ROOT}",
            "--pwd", str(work),
            str(VASP_SIF), "bash", "-lc", inner,
        ],
        capture_output=True, text=True, timeout=timeout,
    )
    osz = work / "OSZICAR"
    if not osz.is_file():
        raise RuntimeError(f"VASP failed at a={a}")
    for line in osz.read_text(errors="replace").splitlines()[::-1]:
        m = re.search(r"F=\s*([-\d.E+]+)", line)
        if m:
            return float(m.group(1))
    raise RuntimeError(f"no energy a={a}")


def run_openmx_point(
    work: Path, element: str, a: float, nprocs: int, timeout: int
) -> float:
    from ase.build import bulk
    from ase.io import write
    from omx_tools.generator import generate_input, SCHEMA_PATH, TEMPLATES_PATH
    from omx_tools._utils import load_json
    import json as _json

    work.mkdir(parents=True, exist_ok=True)
    write(work / "POSCAR", bulk(element, "diamond", a=a, cubic=True), format="vasp", vasp5=True)
    os.environ["OPENMX_DFT_DATA_PATH"] = str(DFT_DATA)
    schema = load_json(SCHEMA_PATH, "keywords.json")
    templates = _json.loads(Path(TEMPLATES_PATH).read_text(encoding="utf-8"))
    dat = work / f"{element}_a.dat"
    generate_input(
        structure_path=str(work / "POSCAR"),
        template_name="scf_band",
        overrides={
            "scf_xctype": "GGA-PBE",
            "scf_energycutoff": 150.0,
            "scf_maxiter": 60,
            "scf_criterion": 1e-8,
            "scf_kgrid": [3, 3, 3],
        },
        schema=schema,
        templates=templates,
        kspacing=0.5,
        dry_run=False,
        verbose=False,
        output_path=str(dat),
    )
    text = dat.read_text()
    name = f"{element}_a{a:.4f}".replace(".", "p")
    text = re.sub(r"System\.Name\s+\S+", f"System.Name        {name}", text, count=1)
    if not re.search(r"scf\.Kgrid", text):
        text += "\nscf.Kgrid        3 3 3\n"
    dat.write_text(text)
    inner = (
        "source /opt/intel/oneapi/setvars.sh >/dev/null 2>&1 || true; "
        "export PATH=/opt/intel/oneapi/mpi/latest/bin:$PATH; "
        f"mpirun -np {int(nprocs)} {OMX_BIN} {dat.name}"
    )
    subprocess.run(
        [
            _runner(), "exec",
            "--bind", f"{work}:{work}",
            "--bind", f"{DFT_DATA}:{DFT_DATA}",
            "--pwd", str(work),
            str(OMX_SIF), "bash", "-lc", inner,
        ],
        capture_output=True, text=True, timeout=timeout,
    )
    outs = list(work.glob("*.out"))
    if not outs:
        raise RuntimeError(f"OpenMX no out a={a}")
    # prefer matching system name
    text = max(outs, key=lambda p: p.stat().st_mtime).read_text(errors="replace")
    ms = re.findall(r"Utot\.\s+([-\d.]+)", text)
    if not ms:
        raise RuntimeError(f"OpenMX no Utot a={a}")
    return float(ms[-1]) * HA_TO_EV


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--element", choices=sorted(ELEMENT_CFG), default="Si")
    p.add_argument("--np", type=int, default=4)
    p.add_argument("--timeout", type=int, default=180)
    p.add_argument("--encut", type=float, default=400.0)
    p.add_argument(
        "--scales",
        type=float,
        nargs="+",
        default=[0.98, 0.99, 1.00, 1.01, 1.02],
    )
    p.add_argument("--outdir", type=Path, default=None)
    p.add_argument("--tol-rel", type=float, default=TOL_AEQ_REL)
    p.add_argument("--check-only", action="store_true")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    el = args.element.capitalize()
    a0_exp = ELEMENT_CFG[el]["a0_exp"]
    outdir = (
        args.outdir or _REPO / "work" / "benchmarks" / f"cross_aeq_{el.lower()}"
    ).resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    report_path = outdir / "report.json"
    docs = _REPO / "docs" / "benchmarks" / f"cross_aeq_{el.lower()}"

    if args.check_only:
        path = report_path if report_path.is_file() else docs / "report.json"
        data = json.loads(path.read_text())
        d = data.get("compare") or {}
        ok = d.get("rel_abs_delta_aeq", 1e9) <= args.tol_rel and data.get("ok")
        print({"ok": ok, "rel_abs_delta_aeq": d.get("rel_abs_delta_aeq")})
        return 0 if ok else 1

    scales = [float(s) for s in args.scales]
    vasp_E, omx_E = [], []
    points = []
    t0 = time.time()
    for s in scales:
        a = a0_exp * s
        print(f"=== scale={s} a={a:.5f} VASP ===")
        ev = run_vasp_point(
            outdir / f"vasp_s{s:.3f}", el, a, args.np, args.timeout, args.encut
        )
        print(f"  E={ev}")
        print(f"=== scale={s} OpenMX ===")
        eo = run_openmx_point(
            outdir / f"omx_s{s:.3f}", el, a, args.np, args.timeout
        )
        print(f"  E={eo}")
        vasp_E.append(ev)
        omx_E.append(eo)
        points.append({"scale": s, "a_A": a, "E_vasp_eV": ev, "E_openmx_eV": eo})

    fit_v = fit_aeq(scales, vasp_E, a0_exp)
    fit_o = fit_aeq(scales, omx_E, a0_exp)
    cmp = {"a0_exp_A": a0_exp}
    if fit_v.get("ok") and fit_o.get("ok"):
        cmp["a_eq_vasp_A"] = fit_v["a_eq_A"]
        cmp["a_eq_openmx_A"] = fit_o["a_eq_A"]
        cmp["abs_delta_aeq_A"] = abs(fit_v["a_eq_A"] - fit_o["a_eq_A"])
        cmp["rel_abs_delta_aeq"] = cmp["abs_delta_aeq_A"] / a0_exp
        cmp["vasp_minus_exp_A"] = fit_v["a_eq_A"] - a0_exp
        cmp["openmx_minus_exp_A"] = fit_o["a_eq_A"] - a0_exp
    gate_ok = (
        fit_v.get("ok")
        and fit_o.get("ok")
        and cmp.get("rel_abs_delta_aeq", 1.0) <= args.tol_rel
    )
    report = {
        "kind": f"cross_aeq_{el.lower()}",
        "element": el,
        "protocol": {
            "scales": scales,
            "kmesh": "3x3x3 Gamma",
            "vasp_encut_eV": args.encut,
            "openmx_cutoff_Ry": 150,
            "fit": "E = c0 + c1 s + c2 s^2, s=a/a0_exp",
        },
        "points": points,
        "vasp_fit": fit_v,
        "openmx_fit": fit_o,
        "compare": cmp,
        "gate": {"ok": gate_ok, "tol_rel": args.tol_rel},
        "ok": gate_ok,
        "wall_s": round(time.time() - t0, 2),
    }
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    md = [
        f"# Cross a_eq: {el} (VASP vs OpenMX)",
        "",
        f"| | a_eq (Å) | vs exp {a0_exp} |",
        f"|--|--------:|-------------:|",
        f"| VASP | {fit_v.get('a_eq_A')} | {cmp.get('vasp_minus_exp_A')} |",
        f"| OpenMX | {fit_o.get('a_eq_A')} | {cmp.get('openmx_minus_exp_A')} |",
        f"| \\|V−O\\| | {cmp.get('abs_delta_aeq_A')} | rel={cmp.get('rel_abs_delta_aeq')} |",
        "",
        f"- gate: **{'PASS' if gate_ok else 'FAIL'}** (rel tol {args.tol_rel})",
        "",
    ]
    (outdir / "REPORT.md").write_text("\n".join(md) + "\n")
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    (docs / "REPORT.md").write_text("\n".join(md) + "\n")

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"\n=== a_eq {el} ===")
        print(f"VASP   a_eq = {fit_v.get('a_eq_A')}")
        print(f"OpenMX a_eq = {fit_o.get('a_eq_A')}")
        print(f"exp    a0   = {a0_exp}")
        print(f"|Δ|/a0 = {cmp.get('rel_abs_delta_aeq')}")
        print(f"GATE {'PASS' if gate_ok else 'FAIL'}")
    return 0 if gate_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
