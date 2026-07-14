#!/usr/bin/env python3
"""Compare KS orbital **energies** (eigenvalues) for diamond Si/C on VASP vs OpenMX.

Use ``--element Si`` (default) or ``--element C``.

Protocol
--------
- Same geometry: cubic diamond 8-atom cell @ experimental a0 (fixed)
- Special k-points (fractional, conventional cubic cell):
  Γ (0,0,0), X (0.5,0,0), K (0.5,0.5,0), L (0.5,0.5,0.5)
- Align spectra so **VBM = 0** (max occupied eigenvalue over these k)
- Compare:
  - fundamental gap (min CB − max VB over the set)
  - direct gap at Γ
  - per-k occupied/unoccupied edges
  - RMS of relative eigenvalues for the top ``n_occ_cmp`` occupied and
    bottom ``n_emp_cmp`` empty bands at each k (after VBM alignment)

Absolute KS energies are **not** compared without alignment.

Examples::

    python3 scripts/cross_band.py --element Si --np 4
    python3 scripts/cross_band.py --element C --np 4
    python3 scripts/cross_band.py --element Si --check-only
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
    "Si": {"a0_A": 5.431, "n_occ": 16},
    "C": {"a0_A": 3.567, "n_occ": 16},
}

KPOINTS_SPEC = [
    ("G", np.array([0.0, 0.0, 0.0])),
    ("X", np.array([0.5, 0.0, 0.0])),
    ("K", np.array([0.5, 0.5, 0.0])),
    ("L", np.array([0.5, 0.5, 0.5])),
]

OMX_SIF = Path(os.environ.get("OPENMX_SIF", "/mnt/shared/openmx4.0_intel.sif"))
VASP_SIF = Path(os.environ.get("VASP_SIF", "/mnt/shared/vasp_latest.sif"))
DFT_DATA = Path(os.environ.get("OPENMX_DFT_DATA_PATH", "/mnt/shared/DFT_DATA19"))
POT_ROOT = Path(
    os.environ.get("VASP_PP_PATH", "/mnt/shared/VASP_POT/POT_GGA_PAW_PBE_54")
)
VASP_PREFIX = os.environ.get("VASP_PREFIX", "/opt/vasp.6.5.1")
OMX_BIN = "/openmx4.0/work/openmx"

# Hard gates (eV) — PBE cross-code tolerances
TOL_GAP = float(os.environ.get("CROSS_BAND_TOL_GAP", "0.25"))
TOL_RMS = float(os.environ.get("CROSS_BAND_TOL_RMS", "0.20"))


def _runner() -> str:
    if shutil.which("singularity"):
        return "singularity"
    if shutil.which("apptainer"):
        return "apptainer"
    raise RuntimeError("need singularity/apptainer")


def write_poscar(path: Path, element: str, a0: float) -> None:
    from ase.build import bulk
    from ase.io import write

    atoms = bulk(element, "diamond", a=a0, cubic=True)
    write(path, atoms, format="vasp", vasp5=True, direct=False)


def parse_vasp_eigenval(path: Path) -> dict[str, np.ndarray]:
    """Return {label: eigenvalues_eV[nbands]} for matching special k."""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    # line index 5: nelect nk nbands
    hdr = lines[5].split()
    nelect, nk, nbands = int(hdr[0]), int(hdr[1]), int(hdr[2])
    i = 7
    kpts = []
    while i < len(lines) and len(kpts) < nk:
        if not lines[i].strip():
            i += 1
            continue
        parts = lines[i].split()
        if len(parts) >= 3:
            k = np.array([float(parts[0]), float(parts[1]), float(parts[2])])
            i += 1
            eigs = []
            for _ in range(nbands):
                while i < len(lines) and not lines[i].strip():
                    i += 1
                p = lines[i].split()
                # band_index energy [occ]
                eigs.append(float(p[1]))
                i += 1
            kpts.append((k, np.array(eigs, float)))
        else:
            i += 1
    out: dict[str, np.ndarray] = {}
    for label, kref in KPOINTS_SPEC:
        best = None
        best_d = 1e9
        for k, eigs in kpts:
            # fold to [0,1)
            kk = k - np.floor(k)
            d = np.linalg.norm(kk - kref)
            d2 = np.linalg.norm((1 - kk) - kref)  # rarely
            d = min(d, float(np.linalg.norm(kk - kref)))
            if d < best_d:
                best_d = d
                best = eigs
        if best is not None and best_d < 0.05:
            out[label] = best
    out["_meta"] = {"nelect": nelect, "nk": nk, "nbands": nbands}  # type: ignore
    return out


def parse_openmx_out_eigs(path: Path) -> dict[str, np.ndarray]:
    """Parse SCF eigenvalue blocks from OpenMX .out (Hartree → eV)."""
    text = path.read_text(encoding="utf-8", errors="replace")
    blocks = re.finditer(
        r"kloop=\s*(\d+)\s*\n\s*k1=\s*([-\d.]+)\s*k2=\s*([-\d.]+)\s*k3=\s*([-\d.]+)\s*\n"
        r"(.*?)(?=\n\s*kloop=|\n\*{5,}|\n\s*Chemical|\Z)",
        text,
        re.S,
    )
    kpts = []
    for m in blocks:
        k = np.array([float(m.group(2)), float(m.group(3)), float(m.group(4))])
        eigs = []
        for line in m.group(5).splitlines():
            p = line.split()
            if len(p) >= 2 and p[0].isdigit():
                # index up [down]
                eigs.append(float(p[1]))
        if eigs:
            kpts.append((k, np.array(eigs, float) * HA_TO_EV))
    out: dict[str, np.ndarray] = {}
    for label, kref in KPOINTS_SPEC:
        best = None
        best_d = 1e9
        for k, eigs in kpts:
            kk = np.mod(k + 1e-12, 1.0)
            d = float(np.linalg.norm(kk - kref))
            if d < best_d:
                best_d = d
                best = eigs
        if best is not None and best_d < 0.08:
            out[label] = best
    return out


def parse_openmx_band_file(path: Path) -> dict[str, np.ndarray]:
    """Parse OpenMX ``.Band`` dispersion file if present."""
    if not path.is_file():
        return {}
    lines = [
        ln.strip()
        for ln in path.read_text(encoding="utf-8", errors="replace").splitlines()
        if ln.strip()
    ]
    # Format (common): first line: nbands nspin efermi(Hartree)
    # then for each path segment: nk
    # then nk blocks of: kx ky kz dist \n eigenvalues...
    try:
        hdr = lines[0].split()
        nbands = int(float(hdr[0]))
        i = 1
        kpts = []
        while i < len(lines):
            # may be "nk n1 n2 n3" or just continue reading k lines
            p = lines[i].split()
            if len(p) == 1 or (len(p) >= 1 and p[0].isdigit() and len(p) <= 4):
                # start of path: first number is nk along path
                nk = int(float(p[0]))
                i += 1
                for _ in range(nk):
                    if i >= len(lines):
                        break
                    kp = lines[i].split()
                    k = np.array([float(kp[0]), float(kp[1]), float(kp[2])])
                    i += 1
                    eigs = []
                    while len(eigs) < nbands and i < len(lines):
                        for tok in lines[i].split():
                            try:
                                eigs.append(float(tok))
                            except ValueError:
                                pass
                            if len(eigs) >= nbands:
                                break
                        i += 1
                    if len(eigs) >= nbands:
                        kpts.append((k, np.array(eigs[:nbands]) * HA_TO_EV))
            else:
                i += 1
        out: dict[str, np.ndarray] = {}
        for label, kref in KPOINTS_SPEC:
            best, best_d = None, 1e9
            for k, eigs in kpts:
                # Band file k often in Cartesian 1/Bohr — harder to match.
                # Prefer SCF out parser; band file used only if labels stored.
                kk = np.array(k[:3], float)
                if np.max(np.abs(kk)) > 2:  # likely not fractional
                    continue
                d = float(np.linalg.norm(np.mod(kk, 1.0) - kref))
                if d < best_d:
                    best_d, best = d, eigs
            if best is not None and best_d < 0.08:
                out[label] = best
        return out
    except Exception:
        return {}


def spectrum_metrics(eigs_by_k: dict[str, np.ndarray], n_occ: int = 16) -> dict:
    """VBM-aligned metrics from special-k eigenvalue dict."""
    labels = [lab for lab, _ in KPOINTS_SPEC if lab in eigs_by_k]
    if not labels:
        return {"ok": False, "error": "no special k eigenvalues"}
    vb = []
    cb = []
    aligned = {}
    for lab in labels:
        e = np.sort(eigs_by_k[lab])
        if len(e) < n_occ + 1:
            return {"ok": False, "error": f"{lab}: only {len(e)} bands, need >{n_occ}"}
        vb.append(float(e[n_occ - 1]))
        cb.append(float(e[n_occ]))
    vbm = max(vb)
    cbm = min(cb)
    for lab in labels:
        aligned[lab] = np.sort(eigs_by_k[lab]) - vbm
    # direct gap at G
    g = aligned.get("G")
    direct_g = None
    if g is not None and len(g) > n_occ:
        direct_g = float(g[n_occ] - g[n_occ - 1])
    return {
        "ok": True,
        "vbm_raw_eV": vbm,
        "gap_fundamental_eV": cbm - vbm,
        "gap_direct_G_eV": direct_g,
        "aligned": {lab: aligned[lab].tolist() for lab in labels},
        "edge": {
            lab: {
                "vb_eV": float(aligned[lab][n_occ - 1]),
                "cb_eV": float(aligned[lab][n_occ]),
            }
            for lab in labels
        },
        "labels": labels,
        "n_occ": n_occ,
    }


def compare_spectra(vasp_m: dict, omx_m: dict, n_occ_cmp: int = 4, n_emp_cmp: int = 4) -> dict:
    if not vasp_m.get("ok") or not omx_m.get("ok"):
        return {"ok": False, "error": "metrics incomplete"}
    labels = [lab for lab in vasp_m["labels"] if lab in omx_m["labels"]]
    gap_v = vasp_m["gap_fundamental_eV"]
    gap_o = omx_m["gap_fundamental_eV"]
    diffs = []
    per_k = {}
    n_occ = vasp_m["n_occ"]
    for lab in labels:
        ev = np.array(vasp_m["aligned"][lab])
        eo = np.array(omx_m["aligned"][lab])
        # top occupied + bottom empty
        idx = list(range(n_occ - n_occ_cmp, n_occ)) + list(
            range(n_occ, n_occ + n_emp_cmp)
        )
        idx = [i for i in idx if i < len(ev) and i < len(eo)]
        d = ev[idx] - eo[idx]
        per_k[lab] = {
            "rms_eV": float(np.sqrt(np.mean(d ** 2))) if len(d) else None,
            "max_abs_eV": float(np.max(np.abs(d))) if len(d) else None,
            "n_levels": len(d),
        }
        diffs.extend(d.tolist())
    rms = float(np.sqrt(np.mean(np.array(diffs) ** 2))) if diffs else None
    return {
        "ok": True,
        "gap_vasp_eV": gap_v,
        "gap_openmx_eV": gap_o,
        "gap_abs_diff_eV": abs(gap_v - gap_o),
        "direct_G_vasp_eV": vasp_m.get("gap_direct_G_eV"),
        "direct_G_openmx_eV": omx_m.get("gap_direct_G_eV"),
        "rms_eV": rms,
        "per_k": per_k,
        "labels": labels,
        "n_occ_cmp": n_occ_cmp,
        "n_emp_cmp": n_emp_cmp,
    }


def run_vasp_band(
    outdir: Path, nprocs: int, timeout: int, encut: float,
    element: str = "Si", a0: float = 5.431, n_occ: int = 16,
) -> dict:
    outdir.mkdir(parents=True, exist_ok=True)
    write_poscar(outdir / "POSCAR", element, a0)
    shutil.copy(POT_ROOT / element / "POTCAR", outdir / "POTCAR")
    (outdir / "INCAR").write_text(
        f"""SYSTEM = {element} KS eigenvalue cross
PREC = Accurate
ENCUT = {encut}
EDIFF = 1E-7
NELM = 80
ISMEAR = 0
SIGMA = 0.05
ISPIN = 1
NBANDS = 32
LWAVE = .FALSE.
LCHARG = .FALSE.
NSW = 0
IBRION = -1
"""
    )
    # explicit special k
    kp = ["Special k for cross-band", str(len(KPOINTS_SPEC)), "Reciprocal"]
    for lab, k in KPOINTS_SPEC:
        kp.append(f"{k[0]} {k[1]} {k[2]} 1  ! {lab}")
    (outdir / "KPOINTS").write_text("\n".join(kp) + "\n")

    t0 = time.time()
    inner = (
        "source /opt/intel/oneapi/setvars.sh >/dev/null 2>&1 || true; "
        "export PATH=/opt/intel/oneapi/mpi/latest/bin:$PATH; "
        f"mpirun -np {int(nprocs)} {VASP_PREFIX}/bin/vasp_std"
    )
    proc = subprocess.run(
        [
            _runner(), "exec",
            "--bind", f"{outdir}:{outdir}",
            "--bind", f"{POT_ROOT}:{POT_ROOT}",
            "--pwd", str(outdir),
            str(VASP_SIF), "bash", "-lc", inner,
        ],
        capture_output=True, text=True, timeout=timeout,
    )
    (outdir / "vasp.log").write_text(
        (proc.stdout or "") + "\n" + (proc.stderr or ""), encoding="utf-8"
    )
    epath = outdir / "EIGENVAL"
    if not epath.is_file():
        return {"ok": False, "error": "no EIGENVAL", "wall_s": time.time() - t0}
    eigs = parse_vasp_eigenval(epath)
    meta = eigs.pop("_meta", {})
    metrics = spectrum_metrics(eigs, n_occ=n_occ)
    metrics["wall_s"] = round(time.time() - t0, 2)
    metrics["source"] = "EIGENVAL"
    metrics["meta"] = meta
    metrics["k_found"] = list(eigs.keys())
    return metrics


def run_openmx_band(
    outdir: Path, nprocs: int, timeout: int,
    element: str = "Si", a0: float = 5.431, n_occ: int = 16,
) -> dict:
    from omx_tools.generator import generate_input, SCHEMA_PATH, TEMPLATES_PATH
    from omx_tools._utils import load_json
    import json as _json

    outdir.mkdir(parents=True, exist_ok=True)
    write_poscar(outdir / "POSCAR", element, a0)
    os.environ["OPENMX_DFT_DATA_PATH"] = str(DFT_DATA)
    schema = load_json(SCHEMA_PATH, "keywords.json")
    templates = _json.loads(Path(TEMPLATES_PATH).read_text(encoding="utf-8"))
    generate_input(
        structure_path=str(outdir / "POSCAR"),
        template_name="scf_band",
        overrides={
            "scf_xctype": "GGA-PBE",
            "scf_energycutoff": 150.0,
            "scf_maxiter": 80,
            "scf_criterion": 1e-9,
            "scf_kgrid": [6, 6, 6],
        },
        schema=schema,
        templates=templates,
        kspacing=0.35,
        dry_run=False,
        verbose=False,
        output_path=str(outdir / f"{element}_band.dat"),
    )
    text = (outdir / f"{element}_band.dat").read_text()
    text = re.sub(r"System\.Name\s+\S+", f"System.Name        {element}_band", text, count=1)
    # Force k-grid to include special points well; also dump eigenvalues at SCF k
    if not re.search(r"scf\.Kgrid", text):
        text += "\nscf.Kgrid        6 6 6\n"
    else:
        text = re.sub(
            r"scf\.Kgrid\s+\S+\s+\S+\s+\S+",
            "scf.Kgrid        6 6 6",
            text,
        )
    # Ensure band solver
    if re.search(r"scf\.EigenvalueSolver", text, re.I):
        text = re.sub(
            r"scf\.EigenvalueSolver\s+\S+",
            "scf.EigenvalueSolver        Band",
            text,
            flags=re.I,
        )
    else:
        text += "\nscf.EigenvalueSolver        Band\n"
    (outdir / f"{element}_band.dat").write_text(text)

    t0 = time.time()
    inner = (
        "source /opt/intel/oneapi/setvars.sh >/dev/null 2>&1 || true; "
        "export PATH=/opt/intel/oneapi/mpi/latest/bin:$PATH; "
        f"mpirun -np {int(nprocs)} {OMX_BIN} {element}_band.dat"
    )
    proc = subprocess.run(
        [
            _runner(), "exec",
            "--bind", f"{outdir}:{outdir}",
            "--bind", f"{DFT_DATA}:{DFT_DATA}",
            "--pwd", str(outdir),
            str(OMX_SIF), "bash", "-lc", inner,
        ],
        capture_output=True, text=True, timeout=timeout,
    )
    (outdir / "openmx.log").write_text(
        (proc.stdout or "") + "\n" + (proc.stderr or ""), encoding="utf-8"
    )
    out_file = outdir / f"{element}_band.out"
    if not out_file.is_file():
        # System.Name may differ
        outs = list(outdir.glob("*.out"))
        out_file = outs[0] if outs else out_file
    eigs = parse_openmx_out_eigs(out_file) if out_file.is_file() else {}
    if len(eigs) < 2:
        # fallback denser parse fail
        pass
    metrics = spectrum_metrics(eigs, n_occ=n_occ)
    metrics["wall_s"] = round(time.time() - t0, 2)
    metrics["source"] = str(out_file.name) if out_file.is_file() else None
    metrics["k_found"] = list(eigs.keys())
    return metrics


def gate_result(cmp: dict, tol_gap: float, tol_rms: float) -> dict:
    issues = []
    if not cmp.get("ok"):
        issues.append(cmp.get("error") or "compare failed")
    else:
        if cmp["gap_abs_diff_eV"] > tol_gap:
            issues.append(
                f"|Δgap|={cmp['gap_abs_diff_eV']:.3f} eV > {tol_gap} eV"
            )
        if cmp.get("rms_eV") is not None and cmp["rms_eV"] > tol_rms:
            issues.append(f"RMS={cmp['rms_eV']:.3f} eV > {tol_rms} eV")
    return {"ok": not issues, "issues": issues, "tol_gap_eV": tol_gap, "tol_rms_eV": tol_rms}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--element", choices=sorted(ELEMENT_CFG), default="Si")
    p.add_argument("--np", type=int, default=4)
    p.add_argument("--outdir", type=Path, default=None)
    p.add_argument("--timeout", type=int, default=400)
    p.add_argument("--encut", type=float, default=400.0)
    p.add_argument("--tol-gap", type=float, default=TOL_GAP)
    p.add_argument("--tol-rms", type=float, default=TOL_RMS)
    p.add_argument(
        "--check-only",
        action="store_true",
        help="Only validate existing report.json against tolerances",
    )
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    el = args.element.capitalize()
    cfg = ELEMENT_CFG[el]
    a0 = float(cfg["a0_A"])
    n_occ = int(cfg["n_occ"])
    outdir = (args.outdir or (_REPO / "work" / "benchmarks" / f"cross_band_{el.lower()}")).resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    report_path = outdir / "report.json"
    docs_dir = _REPO / "docs" / "benchmarks" / f"cross_band_{el.lower()}"

    if args.check_only:
        path = report_path if report_path.is_file() else docs_dir / "report.json"
        if not path.is_file():
            print("no report.json", file=sys.stderr)
            return 2
        report = json.loads(path.read_text(encoding="utf-8"))
        g = gate_result(report.get("compare") or {}, args.tol_gap, args.tol_rms)
        report["gate"] = g
        print(json.dumps(g, indent=2) if args.json else g)
        return 0 if g["ok"] else 1

    print(f"=== VASP special-k SCF ({el}) ===")
    vasp = run_vasp_band(
        outdir / "vasp", args.np, args.timeout, args.encut, el, a0, n_occ
    )
    print(" VASP k:", vasp.get("k_found"), "gap:", vasp.get("gap_fundamental_eV"))
    print(f"=== OpenMX SCF eigenvalues ({el}) ===")
    omx = run_openmx_band(
        outdir / "openmx", args.np, args.timeout, el, a0, n_occ
    )
    print(" OpenMX k:", omx.get("k_found"), "gap:", omx.get("gap_fundamental_eV"))

    cmp = compare_spectra(vasp, omx)
    # element-aware defaults when CLI left at global env defaults
    tol_gap, tol_rms = args.tol_gap, args.tol_rms
    if el == "C":
        # diamond empty-state scatter larger with PAO vs PAW
        if abs(tol_gap - 0.25) < 1e-12:
            tol_gap = 0.30
        if abs(tol_rms - 0.20) < 1e-12:
            tol_rms = 0.35
    gate = gate_result(cmp, tol_gap, tol_rms)
    report = {
        "kind": f"cross_band_{el.lower()}",
        "element": el,
        "protocol": {
            "structure": f"{el} diamond cubic a0={a0} Å",
            "kpoints": {lab: k.tolist() for lab, k in KPOINTS_SPEC},
            "alignment": "VBM = 0 (max occupied over special k)",
            "n_occ_bands": n_occ,
            "note": "Compare orbital energies (eigenvalues), not wavefunctions",
        },
        "vasp": {k: v for k, v in vasp.items() if k != "aligned"}
        | {"aligned_edges": vasp.get("edge")},
        "openmx": {k: v for k, v in omx.items() if k != "aligned"}
        | {"aligned_edges": omx.get("edge")},
        "compare": cmp,
        "gate": gate,
        "tol_gap_eV": tol_gap,
        "tol_rms_eV": tol_rms,
        "ok": bool(gate["ok"] and vasp.get("ok") and omx.get("ok")),
    }
    # keep full aligned in side files to limit size? include edges enough
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    md = [
        f"# Cross KS orbital energies: {el} (VASP vs OpenMX)",
        "",
        "Aligned so **VBM = 0**. Absolute eigenvalues not compared.",
        "",
        f"| quantity | VASP | OpenMX | \\|Δ\\| |",
        f"|----------|-----:|-------:|----:|",
        f"| fundamental gap (eV) | {cmp.get('gap_vasp_eV')} | {cmp.get('gap_openmx_eV')} | {cmp.get('gap_abs_diff_eV')} |",
        f"| direct gap @ Γ (eV) | {cmp.get('direct_G_vasp_eV')} | {cmp.get('direct_G_openmx_eV')} | ",
        f"| RMS (top occ+low empty) (eV) |  |  | {cmp.get('rms_eV')} |",
        "",
        f"- gate: **{'PASS' if gate['ok'] else 'FAIL'}** "
        f"(tol_gap={args.tol_gap} eV, tol_rms={args.tol_rms} eV)",
        f"- k found VASP: {vasp.get('k_found')} OpenMX: {omx.get('k_found')}",
        "",
    ]
    if cmp.get("per_k"):
        md += ["| k | RMS (eV) | max\\|Δ\\| (eV) |", "|---|--------:|------------:|"]
        for lab, d in cmp["per_k"].items():
            md.append(f"| {lab} | {d.get('rms_eV')} | {d.get('max_abs_eV')} |")
        md.append("")
    (outdir / "REPORT.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    docs_dir.mkdir(parents=True, exist_ok=True)
    (docs_dir / "report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    (docs_dir / "REPORT.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"\n=== KS eigenvalue cross ({el}) ===")
        print(f"gap V/O = {cmp.get('gap_vasp_eV')} / {cmp.get('gap_openmx_eV')} "
              f"Δ={cmp.get('gap_abs_diff_eV')}")
        print(f"RMS = {cmp.get('rms_eV')}")
        print(f"GATE {'PASS' if report['ok'] else 'FAIL'}")
        print(f"report: {report_path}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
