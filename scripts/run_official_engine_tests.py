#!/usr/bin/env python3
"""Official engine tests + dft-tools cross-check on their inputs.

Layers
------
1. **OpenMX engine**: ``mpirun -np N openmx -runtest`` (14 input_example cases,
   compares Utot/Force to bundled ``*.out`` references — installation truth).
2. **VASP engine** (optional): VASP 6.x ``testsuite/runtest`` for selected cases.
   Requires matching binary ↔ suite version; often fails across releases.
3. **Tooling cross** (no/cheap SCF): parse + lint/advise official OpenMX ``.dat``
   (and VASP INCAR fixtures when present) through dft-tools APIs.

Examples::

    python3 scripts/run_official_engine_tests.py --np 8
    python3 scripts/run_official_engine_tests.py --np 8 --skip-engine   # tooling only
    python3 scripts/run_official_engine_tests.py --np 8 --with-vasp \\
        --vasp-tests DFT_OatomPBE
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

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

DEFAULT_OMX_SIF = Path("/mnt/shared/openmx4.0_intel.sif")
DEFAULT_DFT_DATA = Path(
    os.environ.get("OPENMX_DFT_DATA_PATH", "/mnt/shared/DFT_DATA19")
)
DEFAULT_OPENMX_BIN = "/openmx4.0/work/openmx"
DEFAULT_VASP_SUITE = Path(
    os.environ.get(
        "VASP_TESTSUITE_ROOT",
        str(Path.home() / "hack_vasp" / "testsuite"),
    )
)
DEFAULT_VASP_BIN = Path(
    os.environ.get("VASP_BIN_DIR", str(Path.home() / "hack_vasp" / "bin"))
)

# Official OpenMX criterion: |ΔUtot|, |ΔForce| within ~1e-7 (7th decimal)
OMX_DIFF_TOL = 1e-6


def _runner() -> str:
    if shutil.which("singularity"):
        return "singularity"
    if shutil.which("apptainer"):
        return "apptainer"
    raise RuntimeError("singularity/apptainer not in PATH")


def parse_openmx_runtest_result(text: str) -> dict:
    """Parse ``runtest.result`` table into structured rows."""
    rows = []
    for line in text.splitlines():
        m = re.match(
            r"\s*(\d+)\s+(\S+)\s+Elapsed time\(s\)=\s*([\d.]+)\s+"
            r"diff Utot=\s*([-\d.eE+]+)\s+diff Force=\s*([-\d.eE+]+)",
            line,
        )
        if not m:
            continue
        idx, path, elapsed, du, df = m.groups()
        rows.append({
            "index": int(idx),
            "path": path,
            "elapsed_s": float(elapsed),
            "diff_utot": float(du),
            "diff_force": float(df),
            "pass": abs(float(du)) < OMX_DIFF_TOL and abs(float(df)) < OMX_DIFF_TOL,
        })
    total_m = re.search(r"Total elapsed time \(s\)\s+([\d.]+)", text)
    n_pass = sum(1 for r in rows if r["pass"])
    return {
        "n_cases": len(rows),
        "n_pass": n_pass,
        "n_fail": len(rows) - n_pass,
        "total_elapsed_s": float(total_m.group(1)) if total_m else None,
        "rows": rows,
        "ok": bool(rows) and n_pass == len(rows),
        "criterion": f"|diff Utot|,|diff Force| < {OMX_DIFF_TOL}",
    }


def prepare_openmx_workdir(workdir: Path, sif: Path, dft_data: Path) -> Path:
    """Copy ``input_example`` from SIF into writable workdir; fix DATA.PATH."""
    workdir.mkdir(parents=True, exist_ok=True)
    example = workdir / "input_example"
    if example.exists():
        shutil.rmtree(example)
    r = subprocess.run(
        [
            _runner(),
            "exec",
            str(sif),
            "bash",
            "-lc",
            f"cp -a /openmx4.0/work/input_example {example}",
        ],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0 or not example.is_dir():
        raise RuntimeError(
            f"failed to copy input_example from SIF: {r.stderr or r.stdout}"
        )
    for dat in example.glob("*.dat"):
        text = dat.read_text(encoding="utf-8", errors="replace")
        text2 = re.sub(
            r"DATA\.PATH\s+\S+",
            f"DATA.PATH        {dft_data}",
            text,
        )
        if text2 != text:
            dat.write_text(text2, encoding="utf-8")
    return example


def run_openmx_runtest(
    *,
    np: int,
    sif: Path,
    dft_data: Path,
    workdir: Path,
    timeout: int,
) -> dict:
    if not sif.is_file():
        return {"ok": False, "error": f"SIF missing: {sif}", "skipped": True}
    if not dft_data.is_dir():
        return {"ok": False, "error": f"DFT_DATA missing: {dft_data}", "skipped": True}

    prepare_openmx_workdir(workdir, sif, dft_data)
    t0 = time.time()
    inner = (
        "source /opt/intel/oneapi/setvars.sh >/dev/null 2>&1 || true; "
        "export PATH=/opt/intel/oneapi/mpi/latest/bin:$PATH; "
        f"mpirun -np {int(np)} {DEFAULT_OPENMX_BIN} -runtest"
    )
    cmd = [
        _runner(),
        "exec",
        "--bind",
        f"{workdir}:{workdir}",
        "--bind",
        f"{dft_data}:{dft_data}",
        "--pwd",
        str(workdir),
        str(sif),
        "bash",
        "-lc",
        inner,
    ]
    proc = subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout,
    )
    wall = round(time.time() - t0, 2)
    result_path = workdir / "runtest.result"
    console = (proc.stdout or "") + "\n" + (proc.stderr or "")
    (workdir / "console.log").write_text(console, encoding="utf-8")

    if not result_path.is_file():
        return {
            "ok": False,
            "error": "runtest.result not produced",
            "wall_s": wall,
            "returncode": proc.returncode,
            "console_tail": console[-2000:],
        }

    parsed = parse_openmx_runtest_result(result_path.read_text(encoding="utf-8"))
    parsed.update({
        "wall_s": wall,
        "returncode": proc.returncode,
        "result_file": str(result_path),
        "np": np,
        "workdir": str(workdir),
        "engine": "OpenMX -runtest",
    })
    return parsed


def run_vasp_tests(
    *,
    tests: list[str],
    np: int,
    suite: Path,
    bin_dir: Path,
    timeout: int,
) -> dict:
    """Optional VASP official testsuite subset."""
    if not suite.is_dir() or not (suite / "runtest").is_file():
        return {
            "ok": False,
            "skipped": True,
            "error": f"VASP testsuite not found: {suite}",
        }
    std = bin_dir / "vasp_std"
    if not std.is_file():
        return {
            "ok": False,
            "skipped": True,
            "error": f"vasp_std missing: {std}",
        }
    env = os.environ.copy()
    env["VASP_TESTSUITE_EXE_STD"] = f"mpirun -np {np} {std}"
    env["VASP_TESTSUITE_EXE_NCL"] = f"mpirun -np {np} {bin_dir / 'vasp_ncl'}"
    env["VASP_TESTSUITE_EXE_GAM"] = f"mpirun -np {np} {bin_dir / 'vasp_gam'}"
    env["VASP_TESTSUITE_TESTS"] = " ".join(tests)
    # Do not force FAST-only filter — selected tests may be NOCUDA etc.
    env["VASP_TESTSUITE_RUN_FAST"] = ""
    t0 = time.time()
    proc = subprocess.run(
        ["./runtest"],
        cwd=str(suite),
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    wall = round(time.time() - t0, 2)
    failed = []
    m = re.search(
        r"The following tests failed[^\n]*:\n((?:.+\n)+?)(?:\n|$)",
        out,
    )
    if m:
        failed = [ln.strip() for ln in m.group(1).splitlines() if ln.strip()]
    success = "SUCCESS: ALL SELECTED TESTS PASSED" in out and not failed
    # detect format/runtime crash
    runtime_bug = "Fortran runtime error" in out or "Error termination" in out
    return {
        "ok": success and not runtime_bug,
        "wall_s": wall,
        "returncode": proc.returncode,
        "tests": tests,
        "failed": failed,
        "runtime_bug": runtime_bug,
        "engine": "VASP testsuite",
        "suite": str(suite),
        "np": np,
        "note": (
            "VASP suite must match the binary version; format errors usually "
            "mean suite↔binary mismatch, not physics failure."
            if runtime_bug
            else None
        ),
        "console_tail": out[-2500:],
    }


def tooling_cross_openmx(example_dir: Path) -> dict:
    """Parse + lint + advise official OpenMX input_example .dat files."""
    from omx_tools.parsers.openmx import parse_dat
    from omx_tools.semantic.lint import lint_openmx_dat
    from omx_tools.semantic.advise import advise_openmx_dat

    dats = sorted(example_dir.glob("*.dat"))
    results = []
    for dat in dats:
        entry: dict = {"path": str(dat), "name": dat.name}
        try:
            params = parse_dat(str(dat))
            entry["parse_ok"] = True
            entry["n_keys"] = len(params) if isinstance(params, dict) else None
        except Exception as e:
            entry["parse_ok"] = False
            entry["parse_error"] = str(e)
            results.append(entry)
            continue
        try:
            rep = lint_openmx_dat(str(dat))
            entry["lint_n_error"] = sum(
                1 for f in rep.findings if f.severity == "error"
            )
            entry["lint_n_warning"] = sum(
                1 for f in rep.findings if f.severity == "warning"
            )
            entry["lint_ok"] = entry["lint_n_error"] == 0
        except Exception as e:
            entry["lint_ok"] = False
            entry["lint_error"] = str(e)
        try:
            adv = advise_openmx_dat(str(dat), fetch_knowledge=False)
            entry["advise_ok"] = bool(adv.get("ok", True) or adv.get("n_error", 0) == 0)
            entry["advise_n_error"] = adv.get("n_error")
        except Exception as e:
            entry["advise_ok"] = False
            entry["advise_error"] = str(e)
        results.append(entry)

    n = len(results)
    n_parse = sum(1 for r in results if r.get("parse_ok"))
    n_lint = sum(1 for r in results if r.get("lint_ok"))
    return {
        "ok": n > 0 and n_parse == n,
        "n_files": n,
        "n_parse_ok": n_parse,
        "n_lint_ok": n_lint,
        "cases": results,
        "layer": "tooling_cross_openmx",
    }


def tooling_cross_vasp_fixture() -> dict:
    """Lint/advise a few VASP testsuite INCARs if suite is present."""
    suite = DEFAULT_VASP_SUITE
    candidates = [
        suite / "tests" / "DFT_OatomPBE" / "INCAR.1.STD",
        suite / "tests" / "bulk_BN_PBEsol" / "INCAR.1.STD",
        suite / "tests" / "CrS" / "INCAR.1.STD",
    ]
    from omx_tools.semantic.advise import advise_vasp_file

    cases = []
    for p in candidates:
        if not p.is_file():
            continue
        # advise expects free INCAR; copy to temp without suffix quirks
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
            # strip VASP testsuite-only lines that aren't tags if needed
            tmp = Path(tempfile.mkdtemp()) / "INCAR"
            tmp.write_text(text)
            adv = advise_vasp_file(str(tmp), fetch_knowledge=False, auto_fix=False)
            cases.append({
                "path": str(p),
                "ok": True,
                "n_error": adv.get("n_error"),
                "n_warning": adv.get("n_warning"),
                "calc_class_hint": adv.get("calc_class_hint"),
            })
        except Exception as e:
            cases.append({"path": str(p), "ok": False, "error": str(e)})
    return {
        "ok": bool(cases) and all(c.get("ok") for c in cases),
        "n_files": len(cases),
        "cases": cases,
        "layer": "tooling_cross_vasp",
        "skipped": not cases,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--np", type=int, default=8)
    p.add_argument("--sif", type=Path, default=DEFAULT_OMX_SIF)
    p.add_argument("--dft-data", type=Path, default=DEFAULT_DFT_DATA)
    p.add_argument(
        "--workdir",
        type=Path,
        default=_REPO / "work" / "benchmarks" / "official_runtest",
    )
    p.add_argument("--timeout", type=int, default=600)
    p.add_argument("--skip-engine", action="store_true", help="Skip OpenMX -runtest")
    p.add_argument("--with-vasp", action="store_true")
    p.add_argument(
        "--vasp-tests",
        nargs="+",
        default=["DFT_OatomPBE"],
        help="VASP testsuite case names",
    )
    p.add_argument("--vasp-suite", type=Path, default=DEFAULT_VASP_SUITE)
    p.add_argument("--vasp-bin", type=Path, default=DEFAULT_VASP_BIN)
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    report: dict = {
        "layers": {},
        "ok": False,
        "np": args.np,
    }

    example_dir: Path | None = None
    if not args.skip_engine:
        workdir = args.workdir.resolve()
        workdir.mkdir(parents=True, exist_ok=True)
        omx = run_openmx_runtest(
            np=args.np,
            sif=args.sif,
            dft_data=args.dft_data,
            workdir=workdir,
            timeout=args.timeout,
        )
        report["layers"]["openmx_engine"] = omx
        example_dir = workdir / "input_example"
    else:
        # still try tooling if a previous workdir exists
        cand = args.workdir.resolve() / "input_example"
        if cand.is_dir():
            example_dir = cand
        else:
            # extract only for tooling
            td = Path(tempfile.mkdtemp(prefix="omx_ex_"))
            try:
                example_dir = prepare_openmx_workdir(td, args.sif, args.dft_data)
            except Exception as e:
                report["layers"]["openmx_engine"] = {
                    "skipped": True,
                    "error": str(e),
                }
                example_dir = None

    if example_dir and example_dir.is_dir():
        report["layers"]["tooling_openmx"] = tooling_cross_openmx(example_dir)

    report["layers"]["tooling_vasp"] = tooling_cross_vasp_fixture()

    if args.with_vasp:
        report["layers"]["vasp_engine"] = run_vasp_tests(
            tests=args.vasp_tests,
            np=args.np,
            suite=args.vasp_suite,
            bin_dir=args.vasp_bin,
            timeout=args.timeout,
        )

    # overall: OpenMX engine is the gate when run; else tooling parse gate
    omx_eng = report["layers"].get("openmx_engine") or {}
    tool = report["layers"].get("tooling_openmx") or {}
    if omx_eng.get("skipped"):
        report["ok"] = bool(tool.get("ok"))
    elif "ok" in omx_eng:
        report["ok"] = bool(omx_eng.get("ok") and tool.get("ok", True))
    else:
        report["ok"] = bool(tool.get("ok"))

    out_json = args.workdir.resolve() / "report.json"
    args.workdir.resolve().mkdir(parents=True, exist_ok=True)
    # slim report for disk (drop huge console if present)
    slim = json.loads(json.dumps(report))
    for layer in slim.get("layers", {}).values():
        if isinstance(layer, dict) and "console_tail" in layer:
            layer["console_tail"] = (layer["console_tail"] or "")[-500:]
    out_json.write_text(json.dumps(slim, indent=2) + "\n", encoding="utf-8")

    # markdown summary
    md_lines = [
        "# Official engine tests",
        "",
        f"- MPI np: {args.np}",
        f"- overall ok: **{report['ok']}**",
        "",
    ]
    if omx_eng and not omx_eng.get("skipped"):
        md_lines += [
            "## OpenMX `-runtest`",
            "",
            f"- cases: {omx_eng.get('n_pass')}/{omx_eng.get('n_cases')} pass",
            f"- total elapsed (engine): {omx_eng.get('total_elapsed_s')} s",
            f"- wall: {omx_eng.get('wall_s')} s",
            f"- criterion: {omx_eng.get('criterion')}",
            "",
            "| # | case | ΔUtot | ΔForce | t(s) | pass |",
            "|---|------|------:|-------:|-----:|:----:|",
        ]
        for r in omx_eng.get("rows") or []:
            md_lines.append(
                f"| {r['index']} | `{r['path']}` | {r['diff_utot']:.3e} | "
                f"{r['diff_force']:.3e} | {r['elapsed_s']:.2f} | "
                f"{'Y' if r['pass'] else 'N'} |"
            )
        md_lines.append("")
    if tool:
        md_lines += [
            "## Tooling cross (official OpenMX inputs)",
            "",
            f"- parse ok: {tool.get('n_parse_ok')}/{tool.get('n_files')}",
            f"- lint no-error: {tool.get('n_lint_ok')}/{tool.get('n_files')}",
            "",
        ]
    vasp_e = report["layers"].get("vasp_engine")
    if vasp_e:
        md_lines += [
            "## VASP testsuite (optional)",
            "",
            f"- ok: {vasp_e.get('ok')} skipped={vasp_e.get('skipped')}",
            f"- failed: {vasp_e.get('failed')}",
            f"- note: {vasp_e.get('note')}",
            "",
        ]
    md_lines += [
        "## How this differs from Ecoh/experiment",
        "",
        "- **Engine runtest**: numerical regression vs **code-shipped** references "
        "(install/correctness).",
        "- **Si Ecoh benchmark**: physics vs **experiment** (order-of-magnitude).",
        "- **Tooling cross**: dft-tools still understands official inputs.",
        "",
    ]
    (args.workdir.resolve() / "REPORT.md").write_text(
        "\n".join(md_lines) + "\n", encoding="utf-8"
    )

    if args.json:
        print(json.dumps(slim, indent=2))
    else:
        print("=== official engine tests ===")
        print(f"ok: {report['ok']}")
        if omx_eng and not omx_eng.get("skipped"):
            print(
                f"OpenMX -runtest: {omx_eng.get('n_pass')}/{omx_eng.get('n_cases')} "
                f"pass in {omx_eng.get('total_elapsed_s')}s (np={args.np})"
            )
        if tool:
            print(
                f"tooling parse: {tool.get('n_parse_ok')}/{tool.get('n_files')} "
                f"lint_ok: {tool.get('n_lint_ok')}/{tool.get('n_files')}"
            )
        if vasp_e:
            print(
                f"VASP: ok={vasp_e.get('ok')} skipped={vasp_e.get('skipped')} "
                f"failed={vasp_e.get('failed')}"
            )
        print(f"report: {out_json}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
