"""CLI for semantic IR: show / roundtrip / cross / lint.

Usage (via ``dft semantic …`` or ``python -m omx_tools.semantic.cli``)::

    dft semantic show INCAR
    dft semantic roundtrip INCAR
    dft semantic cross INCAR
    dft semantic lint INCAR
    dft semantic lint-omx input.dat
    dft semantic show-omx input.dat
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _parse_incar_file(path: Path) -> dict[str, Any]:
    try:
        from omx_tools.parsers.vasp import parse_incar
        return parse_incar(str(path))
    except Exception:
        # minimal fallback
        out: dict[str, Any] = {}
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.split("#", 1)[0].strip()
            if not line or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip().upper(), v.strip()
            try:
                if "." in v or "e" in v.lower():
                    out[k] = float(v)
                else:
                    out[k] = int(v)
            except ValueError:
                if v.upper() in (".TRUE.", "TRUE", "T"):
                    out[k] = True
                elif v.upper() in (".FALSE.", "FALSE", "F"):
                    out[k] = False
                else:
                    out[k] = v
        return out


def cmd_show(path: Path, as_json: bool = True) -> int:
    from omx_tools.semantic import encode_vasp

    if not path.is_file():
        print(json.dumps({"error": f"file not found: {path}",
                          "suggestion": "Pass a VASP INCAR path"}))
        return 1
    incar = _parse_incar_file(path)
    ir = encode_vasp(incar, structure_path=str(path.parent))
    env = ir.to_envelope()
    if as_json:
        print(json.dumps(env, indent=2, ensure_ascii=False))
    else:
        print(f"calc_class={ir.calc_class} template={ir.openmx_template}")
        print(f"cutoff_eV={ir.physics.cutoff_eV} spin={ir.physics.spin} "
              f"NSW={ir.ionic.max_steps}")
        print(f"unmapped={ir.provenance.unmapped}")
        print(f"dropped={[d.get('tag') for d in ir.provenance.dropped]}")
    return 0


def cmd_show_omx(path: Path, as_json: bool = True) -> int:
    from omx_tools.semantic.encode_omx import encode_omx_dat

    if not path.is_file():
        print(json.dumps({"error": f"file not found: {path}",
                          "suggestion": "Pass an OpenMX .dat path"}))
        return 1
    ir = encode_omx_dat(path)
    env = ir.to_envelope()
    if as_json:
        print(json.dumps(env, indent=2, ensure_ascii=False))
    else:
        print(f"calc_class={ir.calc_class} template={ir.openmx_template}")
        print(f"ase_keys={len(ir.ase_params)} raw_omx={len(ir.code_native.openmx)}")
    return 0


def cmd_roundtrip(path: Path, as_json: bool = True) -> int:
    from omx_tools.semantic import roundtrip_vasp_ir

    if not path.is_file():
        print(json.dumps({"error": f"file not found: {path}",
                          "suggestion": "Pass a VASP INCAR path"}))
        return 1
    incar = _parse_incar_file(path)
    rep = roundtrip_vasp_ir(incar, structure_path=str(path.parent))
    payload = rep.as_dict()
    payload["grade"] = "same_code_strict"
    payload["path"] = str(path)
    if as_json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"ok={rep.ok} missing={rep.missing} changed={list(rep.changed)}")
    return 0 if rep.ok else 1


def cmd_cross(path: Path, as_json: bool = True) -> int:
    from omx_tools.semantic.equiv import cross_roundtrip_vasp

    if not path.is_file():
        print(json.dumps({"error": f"file not found: {path}",
                          "suggestion": "Pass a VASP INCAR path"}))
        return 1
    incar = _parse_incar_file(path)
    rep = cross_roundtrip_vasp(incar, structure_path=str(path.parent))
    rep["path"] = str(path)
    if as_json:
        print(json.dumps(rep, indent=2, ensure_ascii=False, default=str))
    else:
        print(f"ok_core={rep['ok_core']} class_stable={rep['class_stable']} "
              f"expected_loss={rep['expected_loss']}")
    return 0 if rep.get("ok_core") else 1


def cmd_lint(path: Path, as_json: bool = True) -> int:
    from omx_tools.semantic.lint import lint_vasp_incar

    if not path.is_file():
        print(json.dumps({
            "error": f"file not found: {path}",
            "suggestion": "Pass a VASP INCAR path",
        }))
        return 1
    incar = _parse_incar_file(path)
    rep = lint_vasp_incar(incar, path=str(path))
    payload = rep.as_dict()
    if as_json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"ok={rep.ok} errors={rep.n_error} warnings={rep.n_warning} "
              f"info={rep.n_info} class={rep.calc_class_hint}")
        for f in rep.findings:
            tags = ",".join(f.tags) if f.tags else "-"
            print(f"  [{f.severity}] {f.code}: {f.message}")
            print(f"           suggestion: {f.suggestion}")
            print(f"           tags: {tags}")
    return 0 if rep.ok else 1


def cmd_lint_omx(path: Path, as_json: bool = True) -> int:
    from omx_tools.semantic.lint import lint_openmx_dat

    if not path.is_file():
        print(json.dumps({
            "error": f"file not found: {path}",
            "suggestion": "Pass an OpenMX .dat path",
        }))
        return 1
    rep = lint_openmx_dat(str(path))
    payload = rep.as_dict()
    if as_json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"ok={rep.ok} errors={rep.n_error} warnings={rep.n_warning}")
        for f in rep.findings:
            print(f"  [{f.severity}] {f.code}: {f.message}")
            print(f"           → {f.suggestion}")
    return 0 if rep.ok else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="dft semantic",
        description="Semantic IR show / round-trip / lint tools",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    for name, help_ in (
        ("show", "Encode VASP INCAR to Semantic IR JSON"),
        ("roundtrip", "Same-code VASP→IR→VASP report"),
        ("cross", "Cross-code lossy VASP→OMX→VASP report"),
        ("show-omx", "Encode OpenMX .dat to Semantic IR JSON"),
        ("lint", "Physics/consistency lint for VASP INCAR"),
        ("lint-omx", "Physics/consistency lint for OpenMX .dat"),
    ):
        sp = sub.add_parser(name, help=help_)
        sp.add_argument("path", type=Path, help="Input file")
        sp.add_argument("-H", "--human", action="store_true",
                        help="Human-readable instead of JSON")
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    as_json = not getattr(args, "human", False)
    path: Path = args.path
    if args.cmd == "show":
        return cmd_show(path, as_json=as_json)
    if args.cmd == "roundtrip":
        return cmd_roundtrip(path, as_json=as_json)
    if args.cmd == "cross":
        return cmd_cross(path, as_json=as_json)
    if args.cmd == "show-omx":
        return cmd_show_omx(path, as_json=as_json)
    if args.cmd == "lint":
        return cmd_lint(path, as_json=as_json)
    if args.cmd == "lint-omx":
        return cmd_lint_omx(path, as_json=as_json)
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
