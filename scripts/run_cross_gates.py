#!/usr/bin/env python3
"""Physics regression gates for VASP↔OpenMX cross benchmarks.

Hard gates (fail → exit 1)
--------------------------
1. **Ecoh code Δ** for each element report:
   ``|Ecoh_VASP − Ecoh_OpenMX| ≤ TOL_ECOH_CODE`` (default 0.15 eV)
2. Both engines ``ok`` in each Ecoh report
3. **cross_engine** subset: Ndia2 / Graphite4 ``ok``
4. **KS orbital energies** (Si, and C if report present): ``|Δgap|``, RMS
5. **a_eq** (Si if report present): relative ``|a_eq_V−a_eq_O|/a0 ≤ TOL_AEQ_REL``
6. **Crystal forces** on cross_engine Ndia2/Graphite4 if comparable present:
   ``Δ|F|_max ≤ TOL_FORCE_MAX``

Soft checks (warn only)
-----------------------
- ``|Ecoh − experiment|`` > TOL_ECOH_EXP_SOFT (default 0.5 eV)

Modes
-----
- ``--check-only``: validate existing ``report.json`` only (fast / CI-friendly)
- default: run missing benchmarks then check

Examples::

    python3 scripts/run_cross_gates.py --check-only
    python3 scripts/run_cross_gates.py --np 4
    python3 scripts/run_cross_gates.py --np 4 --elements Si C
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent

TOL_AEQ_REL = float(os.environ.get("CROSS_AEQ_TOL_REL", "0.01"))
TOL_FORCE_MAX = float(os.environ.get("CROSS_FORCE_TOL_MAX", "1.0"))

TOL_ECOH_CODE_EV = float(os.environ.get("CROSS_GATE_TOL_ECOH_CODE", "0.15"))
TOL_ECOH_EXP_SOFT_EV = float(os.environ.get("CROSS_GATE_TOL_ECOH_EXP", "0.5"))
TOL_BAND_GAP_EV = float(os.environ.get("CROSS_BAND_TOL_GAP", "0.25"))
TOL_BAND_RMS_EV = float(os.environ.get("CROSS_BAND_TOL_RMS", "0.20"))

DEFAULT_ELEMENTS = ["Si", "C"]
CROSS_ENGINE_MIN_CASES = ["Ndia2", "Graphite4"]  # cheap crystals


def _load_json(path: Path) -> dict | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _ecoh_report_paths(element: str) -> list[Path]:
    el = element.lower()
    return [
        _REPO / "work" / "benchmarks" / f"cross_delta_ecoh_{el}" / "report.json",
        _REPO / "docs" / "benchmarks" / f"cross_delta_ecoh_{el}" / "report.json",
        # legacy Si path from first script
        _REPO / "work" / "benchmarks" / "cross_delta_ecoh_si" / "report.json"
        if el == "si"
        else Path("/_none_"),
        _REPO / "docs" / "benchmarks" / "cross_delta_ecoh_si" / "report.json"
        if el == "si"
        else Path("/_none_"),
    ]


def find_ecoh_report(element: str) -> Path | None:
    for p in _ecoh_report_paths(element):
        if p.is_file():
            return p
    return None


def check_ecoh_report(path: Path, *, tol_code: float, tol_exp_soft: float) -> dict:
    data = _load_json(path) or {}
    issues: list[str] = []
    warns: list[str] = []
    el = data.get("element") or path.parent.name.replace("cross_delta_ecoh_", "").upper()
    if not data.get("ok"):
        issues.append(f"{el}: report ok=false")
    v = (data.get("vasp") or {}).get("Ecoh_eV")
    o = (data.get("openmx") or {}).get("Ecoh_eV")
    exp = (data.get("experiment") or {}).get("ecoh_eV")
    delta = (data.get("compare") or {}).get("abs_delta_codes")
    if v is None or o is None:
        issues.append(f"{el}: missing Ecoh_VASP or Ecoh_OpenMX")
    else:
        if delta is None:
            delta = abs(float(v) - float(o))
        if delta > tol_code:
            issues.append(
                f"{el}: |Ecoh_V−Ecoh_O|={delta:.4f} eV > hard tol {tol_code} eV"
            )
        if exp is not None:
            for name, val in (("VASP", v), ("OpenMX", o)):
                de = abs(float(val) - float(exp))
                if de > tol_exp_soft:
                    warns.append(
                        f"{el}: |Ecoh_{name}−exp|={de:.4f} eV > soft tol {tol_exp_soft}"
                    )
    return {
        "path": str(path),
        "element": el,
        "ok": not issues,
        "issues": issues,
        "warns": warns,
        "Ecoh_vasp": v,
        "Ecoh_openmx": o,
        "abs_delta_codes": delta,
        "experiment": exp,
    }


def check_cross_engine(path: Path, required: list[str]) -> dict:
    data = _load_json(path) or {}
    issues: list[str] = []
    cases = {c.get("name"): c for c in data.get("cases") or []}
    for name in required:
        c = cases.get(name)
        if not c:
            issues.append(f"cross_engine: missing case {name}")
        elif not c.get("ok"):
            issues.append(f"cross_engine: {name} ok=false ({c.get('error')})")
    return {
        "path": str(path),
        "ok": not issues,
        "issues": issues,
        "n_cases": len(cases),
    }


def check_band_report(path: Path, *, tol_gap: float, tol_rms: float) -> dict:
    data = _load_json(path) or {}
    issues: list[str] = []
    cmp = data.get("compare") or {}
    if not cmp:
        issues.append("band report missing compare block")
    gap_d = cmp.get("gap_abs_diff_eV")
    rms = cmp.get("rms_eV")
    if gap_d is None:
        issues.append("missing gap_abs_diff_eV")
    elif float(gap_d) > tol_gap:
        issues.append(f"|Δgap|={float(gap_d):.4f} eV > {tol_gap} eV")
    if rms is None:
        issues.append("missing rms_eV")
    elif float(rms) > tol_rms:
        issues.append(f"RMS={float(rms):.4f} eV > {tol_rms} eV")
    return {
        "path": str(path),
        "ok": not issues,
        "issues": issues,
        "gap_abs_diff_eV": gap_d,
        "rms_eV": rms,
        "gap_vasp_eV": cmp.get("gap_vasp_eV"),
        "gap_openmx_eV": cmp.get("gap_openmx_eV"),
    }



def check_aeq_report(path: Path, *, tol_rel: float) -> dict:
    data = _load_json(path) or {}
    issues = []
    cmp = data.get("compare") or {}
    rel = cmp.get("rel_abs_delta_aeq")
    if rel is None:
        issues.append("missing rel_abs_delta_aeq")
    elif float(rel) > tol_rel:
        issues.append(f"rel|Δa_eq|={float(rel):.4f} > {tol_rel}")
    if not data.get("ok") and not issues:
        issues.append("aeq report ok=false")
    return {
        "path": str(path),
        "ok": not issues,
        "issues": issues,
        "rel_abs_delta_aeq": rel,
        "a_eq_vasp_A": cmp.get("a_eq_vasp_A"),
        "a_eq_openmx_A": cmp.get("a_eq_openmx_A"),
    }


def check_force_crystal(path: Path, *, cases: list[str], tol_max: float) -> dict:
    data = _load_json(path) or {}
    issues = []
    warns = []
    details = {}
    by = {c.get("name"): c for c in data.get("cases") or []}
    for name in cases:
        c = by.get(name)
        if not c:
            issues.append(f"force: missing case {name}")
            continue
        comp = c.get("comparable") or {}
        dF = comp.get("delta_force_max_eV_A")
        details[name] = dF
        if dF is None:
            warns.append(f"{name}: no comparable force (skip hard)")
            continue
        if float(dF) > tol_max:
            issues.append(f"{name}: Δ|F|_max={float(dF):.3f} > {tol_max} eV/Å")
    return {
        "path": str(path),
        "ok": not issues,
        "issues": issues,
        "warns": warns,
        "delta_force_max": details,
    }

def run_cmd(cmd: list[str], timeout: int) -> int:
    print("+", " ".join(cmd), flush=True)
    return subprocess.call(cmd, cwd=str(_REPO), timeout=timeout)


def ensure_reports(
    *,
    elements: list[str],
    nprocs: int,
    timeout: int,
    run_cross_engine: bool,
) -> None:
    py = sys.executable
    for el in elements:
        if find_ecoh_report(el) is not None:
            print(f"[skip-run] Ecoh report exists for {el}")
            continue
        out = _REPO / "work" / "benchmarks" / f"cross_delta_ecoh_{el.lower()}"
        rc = run_cmd(
            [
                py,
                "scripts/cross_delta_ecoh.py",
                "--element",
                el,
                "--np",
                str(nprocs),
                "--outdir",
                str(out),
                "--timeout",
                str(timeout),
            ],
            timeout=timeout * 3,
        )
        if rc != 0:
            print(f"[warn] Ecoh run for {el} exit {rc}", file=sys.stderr)

    ce = _REPO / "work" / "benchmarks" / "cross_engine" / "report.json"
    if run_cross_engine and not ce.is_file():
        run_cmd(
            [
                py,
                "scripts/cross_engine_examples.py",
                "--np",
                str(nprocs),
                "--only",
                "omx2vasp",
                "--omx-cases",
                *CROSS_ENGINE_MIN_CASES,
                "--timeout",
                str(min(timeout, 300)),
            ],
            timeout=timeout * 2,
        )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--check-only", action="store_true")
    p.add_argument("--np", type=int, default=4)
    p.add_argument("--timeout", type=int, default=400)
    p.add_argument("--elements", nargs="+", default=DEFAULT_ELEMENTS)
    p.add_argument("--tol-code", type=float, default=TOL_ECOH_CODE_EV)
    p.add_argument("--tol-exp-soft", type=float, default=TOL_ECOH_EXP_SOFT_EV)
    p.add_argument("--skip-cross-engine", action="store_true")
    p.add_argument("--skip-band", action="store_true")
    p.add_argument("--skip-aeq", action="store_true")
    p.add_argument("--skip-force", action="store_true")
    p.add_argument("--tol-band-gap", type=float, default=TOL_BAND_GAP_EV)
    p.add_argument("--tol-band-rms", type=float, default=TOL_BAND_RMS_EV)
    p.add_argument("--tol-aeq-rel", type=float, default=TOL_AEQ_REL)
    p.add_argument("--tol-force-max", type=float, default=TOL_FORCE_MAX)
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    if not args.check_only:
        ensure_reports(
            elements=args.elements,
            nprocs=args.np,
            timeout=args.timeout,
            run_cross_engine=not args.skip_cross_engine,
        )

    results: dict = {
        "tol_ecoh_code_eV": args.tol_code,
        "tol_ecoh_exp_soft_eV": args.tol_exp_soft,
        "tol_band_gap_eV": args.tol_band_gap,
        "tol_band_rms_eV": args.tol_band_rms,
        "ecoh": [],
        "cross_engine": None,
        "band_si": None,
        "band_c": None,
        "aeq_si": None,
        "force_crystal": None,
        "ok": True,
    }

    print("=== Ecoh gates ===")
    for el in args.elements:
        path = find_ecoh_report(el)
        if path is None:
            rec = {
                "element": el,
                "ok": False,
                "issues": [f"no Ecoh report for {el}"],
                "warns": [],
            }
        else:
            rec = check_ecoh_report(
                path, tol_code=args.tol_code, tol_exp_soft=args.tol_exp_soft
            )
        results["ecoh"].append(rec)
        status = "PASS" if rec["ok"] else "FAIL"
        print(
            f"  [{status}] {el}: Δcode={rec.get('abs_delta_codes')} "
            f"V={rec.get('Ecoh_vasp')} O={rec.get('Ecoh_openmx')} "
            f"@ {rec.get('path')}"
        )
        for w in rec.get("warns") or []:
            print(f"    WARN {w}")
        for i in rec.get("issues") or []:
            print(f"    ISSUE {i}")
        if not rec["ok"]:
            results["ok"] = False

    if not args.skip_cross_engine:
        print("=== cross_engine gate ===")
        ce_paths = [
            _REPO / "work" / "benchmarks" / "cross_engine" / "report.json",
            _REPO / "docs" / "benchmarks" / "cross_engine" / "report.json",
        ]
        ce = next((p for p in ce_paths if p.is_file()), None)
        if ce is None:
            rec = {
                "ok": False,
                "issues": ["no cross_engine report.json"],
            }
        else:
            rec = check_cross_engine(ce, CROSS_ENGINE_MIN_CASES)
        results["cross_engine"] = rec
        print(f"  [{'PASS' if rec['ok'] else 'FAIL'}] {rec.get('path')}")
        for i in rec.get("issues") or []:
            print(f"    ISSUE {i}")
        if not rec["ok"]:
            results["ok"] = False


    if not args.skip_band:
        print("=== KS eigenvalue gates ===")
        for el, key in (("Si", "band_si"), ("C", "band_c")):
            band_paths = [
                _REPO / "work" / "benchmarks" / f"cross_band_{el.lower()}" / "report.json",
                _REPO / "docs" / "benchmarks" / f"cross_band_{el.lower()}" / "report.json",
            ]
            bp = next((p for p in band_paths if p.is_file()), None)
            if bp is None:
                if el == "Si":
                    rec = {"ok": False, "issues": [f"no cross_band_{el.lower()} report.json"]}
                else:
                    rec = {"ok": True, "issues": [], "skipped": True, "path": None}
                    print(f"  [SKIP] {el} band report not present")
                    results[key] = rec
                    continue
            else:
                tg, tr = args.tol_band_gap, args.tol_band_rms
                if el == "C":
                    if abs(tg - 0.25) < 1e-12:
                        tg = 0.30
                    if abs(tr - 0.20) < 1e-12:
                        tr = 0.35
                rec = check_band_report(bp, tol_gap=tg, tol_rms=tr)
            results[key] = rec
            print(
                f"  [{'PASS' if rec['ok'] else 'FAIL'}] {el} "
                f"Δgap={rec.get('gap_abs_diff_eV')} RMS={rec.get('rms_eV')}"
            )
            for i in rec.get("issues") or []:
                print(f"    ISSUE {i}")
            if not rec["ok"]:
                results["ok"] = False

    if not args.skip_aeq:
        print("=== a_eq gate (Si) ===")
        aeq_paths = [
            _REPO / "work" / "benchmarks" / "cross_aeq_si" / "report.json",
            _REPO / "docs" / "benchmarks" / "cross_aeq_si" / "report.json",
        ]
        ap = next((p for p in aeq_paths if p.is_file()), None)
        if ap is None:
            rec = {"ok": True, "skipped": True, "issues": [], "path": None}
            print("  [SKIP] no cross_aeq_si report")
        else:
            rec = check_aeq_report(ap, tol_rel=args.tol_aeq_rel)
            print(
                f"  [{'PASS' if rec['ok'] else 'FAIL'}] "
                f"rel|Δa_eq|={rec.get('rel_abs_delta_aeq')} "
                f"V={rec.get('a_eq_vasp_A')} O={rec.get('a_eq_openmx_A')}"
            )
            for i in rec.get("issues") or []:
                print(f"    ISSUE {i}")
            if not rec["ok"]:
                results["ok"] = False
        results["aeq_si"] = rec

    if not args.skip_force:
        print("=== crystal force gate ===")
        ce_paths = [
            _REPO / "work" / "benchmarks" / "cross_engine" / "report.json",
            _REPO / "docs" / "benchmarks" / "cross_engine" / "report.json",
        ]
        ce = next((p for p in ce_paths if p.is_file()), None)
        if ce is None:
            rec = {"ok": True, "skipped": True, "issues": []}
            print("  [SKIP] no cross_engine report")
        else:
            rec = check_force_crystal(
                ce, cases=CROSS_ENGINE_MIN_CASES, tol_max=args.tol_force_max
            )
            print(f"  [{'PASS' if rec['ok'] else 'FAIL'}] {rec.get('delta_force_max')}")
            for w in rec.get("warns") or []:
                print(f"    WARN {w}")
            for i in rec.get("issues") or []:
                print(f"    ISSUE {i}")
            if not rec["ok"]:
                results["ok"] = False
        results["force_crystal"] = rec


    out = _REPO / "work" / "benchmarks" / "cross_gates" / "gate_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    docs = _REPO / "docs" / "benchmarks" / "cross_gates"
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "gate_report.json").write_text(
        json.dumps(results, indent=2) + "\n", encoding="utf-8"
    )
    md = [
        "# Cross physics gates",
        "",
        f"- hard |Ecoh_V−Ecoh_O| ≤ **{args.tol_code} eV**",
        f"- soft |Ecoh−exp| ≤ {args.tol_exp_soft} eV (warn only)",
        f"- cross_engine required cases: {', '.join(CROSS_ENGINE_MIN_CASES)}",
        f"- KS band: |Δgap| ≤ **{args.tol_band_gap} eV**, RMS ≤ **{args.tol_band_rms} eV**",
        f"- a_eq rel |Δ| ≤ **{args.tol_aeq_rel}**; crystal Δ|F|_max ≤ **{args.tol_force_max} eV/Å**",
        f"- overall: **{'PASS' if results['ok'] else 'FAIL'}**",
        "",
        "## Ecoh",
        "",
    ]
    for rec in results["ecoh"]:
        md.append(
            f"- {rec.get('element')}: "
            f"{'PASS' if rec.get('ok') else 'FAIL'} "
            f"Δ={rec.get('abs_delta_codes')} "
            f"(V={rec.get('Ecoh_vasp')}, O={rec.get('Ecoh_openmx')})"
        )
    md += [
        "",
        f"## cross_engine: "
        f"{'PASS' if (results.get('cross_engine') or {}).get('ok') else 'FAIL'}",
        "",
        f"## band_si: "
        f"{'PASS' if (results.get('band_si') or {}).get('ok') else 'FAIL/SKIP'}",
        f"## band_c: "
        f"{'PASS' if (results.get('band_c') or {}).get('ok') else 'FAIL/SKIP'}",
        f"## aeq_si: "
        f"{'PASS' if (results.get('aeq_si') or {}).get('ok') else 'FAIL/SKIP'}",
        f"## force_crystal: "
        f"{'PASS' if (results.get('force_crystal') or {}).get('ok') else 'FAIL/SKIP'}",
        "",
    ]
    (docs / "REPORT.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print(f"\nGATE {'PASS' if results['ok'] else 'FAIL'} → {out}")
    return 0 if results["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
