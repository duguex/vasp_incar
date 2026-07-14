#!/usr/bin/env python3
"""E2E demo: real Si8 structure × generate × advise loop × roundtrip.

Uses repo ``work/Si8.cif`` (Materials Studio Si8 cell).

Does **not** require a full SCF by default. Optional OpenMX dry-run needs
``OPENMX_DFT_DATA_PATH`` / ``/mnt/shared/DFT_DATA19``.

Examples::

    python3 scripts/e2e_si8_advise_loop.py
    python3 scripts/e2e_si8_advise_loop.py --with-omx-gen
    python3 scripts/e2e_si8_advise_loop.py --json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

SI8 = _REPO / "work" / "Si8.cif"
DFT_DATA = Path(os.environ.get("OPENMX_DFT_DATA_PATH", "/mnt/shared/DFT_DATA19"))


def _step(name: str, payload: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps({"step": name, **payload}, ensure_ascii=False, default=str))
    else:
        print(f"\n=== {name} ===")
        for k, v in payload.items():
            if k == "findings" and isinstance(v, list):
                print(f"  findings: {len(v)}")
                for f in v[:5]:
                    print(f"    [{f.get('severity')}] {f.get('code')}: {f.get('message')}")
                    kn = f.get("knowledge") or []
                    if kn and kn[0].get("found"):
                        print(f"      knowledge: {(kn[0].get('description') or '')[:100]}…")
            else:
                print(f"  {k}: {v}")


def run(*, with_omx_gen: bool, as_json: bool) -> int:
    if not SI8.is_file():
        print(json.dumps({
            "error": f"missing {SI8}",
            "suggestion": "run from dft-tools repo with work/Si8.cif",
        }))
        return 1

    report: dict = {
        "structure": str(SI8),
        "ok": True,
        "steps": [],
    }

    # --- 1) Knowledge: Si / cutoff context ---
    from vasp_query._common import load_tag_index, resolve_tag, query_tag, load_data, TAG_STATS

    idx = load_tag_index()
    encut = resolve_tag("ENCUT", idx) if idx else None
    if isinstance(encut, dict):
        q = query_tag(encut, stats=load_data(TAG_STATS))
        _step("knowledge.vasp_encut", {
            "title": q.get("info", {}).get("title"),
            "description": (q.get("info", {}).get("description") or "")[:200],
            "top_values": (q.get("stats") or {}).get("top_values", [])[:3],
        }, as_json)
        report["steps"].append("knowledge.vasp_encut")

    # --- 2) Generate VASP INCAR (scf) + KPOINTS for Si8 ---
    from vasp_query.generator import generate

    outdir = Path(tempfile.mkdtemp(prefix="e2e_si8_"))
    gen_res = generate(
        "scf",
        structure=str(SI8),
        kspacing=0.35,
        write_poscar=True,
        output=str(outdir) + "/",
        verbose=False,
    )
    incar_path = outdir / "INCAR"
    _step("generate.vasp_scf", {
        "outdir": str(outdir),
        "written": gen_res.get("written"),
        "template": "scf",
    }, as_json)
    report["steps"].append("generate.vasp_scf")
    report["outdir"] = str(outdir)

    # --- 3) Advise loop on generated INCAR (knowledge attached) ---
    from omx_tools.semantic.advise import advise_vasp_file

    adv = advise_vasp_file(str(incar_path), fetch_knowledge=True, auto_fix=False)
    _step("advise.generated", {
        "ok": adv.get("ok"),
        "n_error": adv.get("n_error"),
        "n_warning": adv.get("n_warning"),
        "calc_class_hint": adv.get("calc_class_hint"),
        "loop": adv.get("loop"),
        "findings": adv.get("findings"),
    }, as_json)
    report["steps"].append("advise.generated")
    report["advise_ok"] = adv.get("ok")

    # --- 4) Intentional bad INCAR → advise --fix ---
    bad = {
        "ENCUT": 80,
        "NSW": 40,
        "IBRION": -1,
        "ISMEAR": 0,
        "SIGMA": 0.05,
        "EDIFF": 1e-5,
        "NELM": 100,
        "ISPIN": 1,
        "GGA": "PE",
    }
    from omx_tools.semantic.advise import advise_vasp
    from vasp_query.generator import render_incar

    bad_path = outdir / "INCAR.bad"
    bad_path.write_text(render_incar(bad, comments=["intentional bad Si8-like INCAR"]))
    fixed_path = outdir / "INCAR.fixed"
    adv_fix = advise_vasp(
        bad, path=str(bad_path), fetch_knowledge=True, auto_fix=True, max_rounds=3,
    )
    if adv_fix.get("incar_changed"):
        fixed_path.write_text(
            render_incar(
                adv_fix["incar_final"],
                comments=["e2e_si8 advise --fix"],
            )
        )
    _step("advise.fix_bad_incar", {
        "ok": adv_fix.get("ok"),
        "fixes_applied": adv_fix.get("fixes_applied"),
        "incar_changed": adv_fix.get("incar_changed"),
        "n_error": adv_fix.get("n_error"),
        "findings_codes": [f.get("code") for f in (adv_fix.get("findings") or [])],
        "fixed_path": str(fixed_path) if fixed_path.exists() else None,
    }, as_json)
    report["steps"].append("advise.fix_bad_incar")
    report["fix_demo_ok"] = bool(adv_fix.get("fixes_applied"))

    # --- 5) Semantic roundtrip on generated INCAR ---
    from omx_tools.semantic import roundtrip_vasp_ir
    from omx_tools.semantic.cli import _parse_incar_file

    incar_dict = _parse_incar_file(incar_path)
    # strip comments-only keys if any
    rt = roundtrip_vasp_ir(incar_dict)
    _step("roundtrip.generated", {
        "ok": rt.ok,
        "missing": rt.missing,
        "changed": rt.changed,
    }, as_json)
    report["steps"].append("roundtrip.generated")
    report["roundtrip_ok"] = rt.ok
    if not rt.ok:
        report["ok"] = False

    # --- 6) Optional OpenMX generate + advise-omx ---
    if with_omx_gen:
        if not DFT_DATA.is_dir():
            _step("omx_gen.skip", {
                "reason": f"DFT_DATA not found: {DFT_DATA}",
            }, as_json)
            report["steps"].append("omx_gen.skip")
        else:
            os.environ.setdefault("OPENMX_DFT_DATA_PATH", str(DFT_DATA))
            from omx_tools.generator import generate_input
            from omx_tools._utils import load_json
            from pathlib import Path as P
            pkg = _REPO / "omx_tools"
            schema = load_json(str(pkg / "schemas" / "keywords.json"), "keywords.json")
            templates = load_json(str(pkg / "schemas" / "templates.json"), "templates.json")
            # templates may be envelope
            if isinstance(templates, dict) and "data" in templates:
                templates = templates["data"]
            dat_path = outdir / "Si8_scf.dat"
            try:
                generate_input(
                    str(SI8), "scf_band", {}, schema, templates,
                    0.4, False, False, str(dat_path),
                )
                from omx_tools.semantic.advise import advise_openmx_dat
                oadv = advise_openmx_dat(str(dat_path), fetch_knowledge=True)
                _step("omx_gen_and_advise", {
                    "dat": str(dat_path),
                    "advise_ok": oadv.get("ok"),
                    "n_warning": oadv.get("n_warning"),
                    "findings": oadv.get("findings"),
                }, as_json)
                report["steps"].append("omx_gen_and_advise")
            except Exception as e:
                _step("omx_gen.error", {"error": str(e)}, as_json)
                report["steps"].append("omx_gen.error")
                report["ok"] = False

    # --- summary ---
    if not as_json:
        print("\n=== SUMMARY ===")
        print(json.dumps({
            k: report[k] for k in report if k != "steps"
        }, indent=2))
    else:
        print(json.dumps({"step": "summary", **{k: report[k] for k in report if k != "steps"}},
                         ensure_ascii=False))
    return 0 if report.get("ok") and report.get("roundtrip_ok") else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--with-omx-gen", action="store_true",
                   help="Also omx-gen Si8 + advise-omx (needs DFT_DATA19)")
    p.add_argument("--json", action="store_true", help="JSON lines per step")
    args = p.parse_args(argv)
    return run(with_omx_gen=args.with_omx_gen, as_json=args.json)


if __name__ == "__main__":
    raise SystemExit(main())
