#!/usr/bin/env python3
"""Official engine tests + dft-tools cross-check on their inputs.

Layers
------
1. **OpenMX engine**: ``mpirun -np N openmx -runtest`` (14 input_example cases,
   compares Utot/Force to bundled ``*.out`` references — installation truth).
2. **VASP engine** (optional): VASP 6.5.1 ``testsuite`` + ``vasp_std`` from the
   **same container** (``vasp_latest.sif`` / ``/opt/vasp.6.5.1``). Do not mix with
   host ``~/hack_vasp`` unless versions match.
3. **Tooling cross** (no/cheap SCF): parse + lint/advise official OpenMX ``.dat``
   (and VASP INCAR fixtures when present) through dft-tools APIs.

Examples::

    python3 scripts/run_official_engine_tests.py --np 8
    python3 scripts/run_official_engine_tests.py --np 8 --with-vasp
    python3 scripts/run_official_engine_tests.py --np 4 --with-vasp \\
        --vasp-tests DFT_OatomPBE bulk_BN_PBEsol
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
DEFAULT_VASP_SIF = Path(
    os.environ.get("VASP_SIF", "/mnt/shared/vasp_latest.sif")
)
DEFAULT_VASP_PREFIX = os.environ.get("VASP_PREFIX", "/opt/vasp.6.5.1")
DEFAULT_VASP_SUITE_HOST = Path(
    os.environ.get(
        "VASP_TESTSUITE_ROOT",
        str(Path.home() / "hack_vasp" / "testsuite"),
    )
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
    timeout: int,
    sif: Path = DEFAULT_VASP_SIF,
    prefix: str = DEFAULT_VASP_PREFIX,
    host_suite: Path | None = None,
) -> dict:
    """Run VASP official testsuite using **matching** bin+suite in container.

    Preferred path: copy ``{prefix}/testsuite`` out of ``sif`` to a writable
    host dir, then ``singularity exec`` with ``mpirun -np N {prefix}/bin/vasp_*``.
    """
    if not sif.is_file():
        return {
            "ok": False,
            "skipped": True,
            "error": f"VASP SIF missing: {sif}",
            "engine": "VASP testsuite (container)",
        }

    # Probe container tree
    probe = subprocess.run(
        [
            _runner(), "exec", str(sif), "bash", "-lc",
            f"test -x {prefix}/bin/vasp_std && test -f {prefix}/testsuite/runtest && echo OK",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if "OK" not in (probe.stdout or ""):
        return {
            "ok": False,
            "skipped": True,
            "error": f"container missing {prefix}/bin or testsuite",
            "probe": (probe.stdout or "") + (probe.stderr or ""),
            "engine": "VASP testsuite (container)",
        }

    work = Path(tempfile.mkdtemp(prefix="vasp_suite_"))
    suite_host = work / "testsuite"
    cp = subprocess.run(
        [
            _runner(), "exec",
            "--bind", f"{work}:{work}",
            str(sif), "bash", "-lc",
            f"cp -a {prefix}/testsuite {suite_host}",
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if cp.returncode != 0 or not (suite_host / "runtest").is_file():
        return {
            "ok": False,
            "error": f"failed to copy testsuite: {(cp.stderr or cp.stdout)[-500:]}",
            "engine": "VASP testsuite (container)",
        }

    # Try build compare helper (optional; suite has text fallbacks)
    subprocess.run(
        [
            _runner(), "exec",
            "--bind", f"{work}:{work}",
            "--pwd", str(suite_host),
            str(sif), "bash", "-lc",
            "make numbertable 2>/dev/null || make -C tools 2>/dev/null || true",
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )

    tests_s = " ".join(tests)
    inner = f"""
source /opt/intel/oneapi/setvars.sh >/dev/null 2>&1 || true
export PATH=/opt/intel/oneapi/mpi/latest/bin:$PATH
export VASP_TESTSUITE_EXE_STD="mpirun -np {int(np)} {prefix}/bin/vasp_std"
export VASP_TESTSUITE_EXE_NCL="mpirun -np {int(np)} {prefix}/bin/vasp_ncl"
export VASP_TESTSUITE_EXE_GAM="mpirun -np {int(np)} {prefix}/bin/vasp_gam"
export VASP_TESTSUITE_TESTS="{tests_s}"
export VASP_TESTSUITE_RUN_FAST=""
unset VASP_TESTSUITE_RUN_FAST
./runtest
"""
    t0 = time.time()
    proc = subprocess.run(
        [
            _runner(), "exec",
            "--bind", f"{work}:{work}",
            "--pwd", str(suite_host),
            str(sif), "bash", "-lc", inner,
        ],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    wall = round(time.time() - t0, 2)
    failed: list[str] = []
    m = re.search(
        r"The following tests failed[^\n]*:\n((?:.+\n)+?)(?:\n|$)",
        out,
    )
    if m:
        failed = [ln.strip() for ln in m.group(1).splitlines() if ln.strip()]
    success = "SUCCESS: ALL SELECTED TESTS PASSED" in out and not failed
    runtime_bug = "Fortran runtime error" in out or "Error termination" in out
    energies_ok = "the energies are correct, run successful" in out

    # Persist log under repo work/ if possible
    log_dir = _REPO / "work" / "benchmarks" / "official_runtest"
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / "vasp_container_runtest.log").write_text(out, encoding="utf-8")

    return {
        "ok": bool(success and not runtime_bug),
        "wall_s": wall,
        "returncode": proc.returncode,
        "tests": tests,
        "failed": failed,
        "runtime_bug": runtime_bug,
        "energies_correct_banner": energies_ok,
        "engine": "VASP testsuite (container vasp.6.5.1)",
        "sif": str(sif),
        "prefix": prefix,
        "suite_host_copy": str(suite_host),
        "np": np,
        "note": (
            "Uses matching /opt/vasp.6.5.1 bin+testsuite inside the SIF. "
            "Host ~/hack_vasp is intentionally not the default."
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
    suite = DEFAULT_VASP_SUITE_HOST
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
    p.add_argument("--with-vasp", action="store_true",
                   help="Run VASP 6.5.1 official suite from container (matched bin+suite)")
    p.add_argument(
        "--vasp-tests",
        nargs="+",
        default=["DFT_OatomPBE"],
        help="VASP testsuite case names",
    )
    p.add_argument("--vasp-sif", type=Path, default=DEFAULT_VASP_SIF)
    p.add_argument("--vasp-prefix", default=DEFAULT_VASP_PREFIX,
                   help="Path inside VASP SIF, e.g. /opt/vasp.6.5.1")
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
            np=min(args.np, 4),  # suite refs often generated with 4 ranks
            timeout=args.timeout,
            sif=args.vasp_sif,
            prefix=args.vasp_prefix,
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
