#!/usr/bin/env python3
"""Bootstrap an OpenMX calculation from vasp_cache VASP references.

Usage:
    python scripts/cache_bootstrap_openmx.py nv_structure.cif -o nv_calc/ \
        --spin collinear --charge -1 --template scf_band

Flow:
    1. Generate VASP inputs from structure (vasp-gen)
    2. Query vasp_cache for matching calculations
    3. Fetch OUTCAR/CONTCAR as reference (lattice, energy, magnetic state)
    4. vasp2omx convert VASP inputs → OpenMX input.dat
    5. Override OpenMX params with reference OUTCAR data
    6. dft semantic advise-omx for safety check
"""

from __future__ import annotations

import argparse
import json
import sys
import textwrap
from pathlib import Path

_HAS_CACHE: bool | None = None


def _check_cache() -> bool:
    global _HAS_CACHE
    if _HAS_CACHE is not None:
        return _HAS_CACHE
    try:
        import vasp_cache  # noqa: F401
        _HAS_CACHE = True
    except ImportError:
        _HAS_CACHE = False
    return _HAS_CACHE


def _print_step(label: str, *lines: str) -> None:
    width = 72
    print(f"\n{'─' * width}")
    print(f"  {label}")
    print(f"{'─' * width}")
    for line in lines:
        print(f"  {line}")


# ── Step 1: VASP input generation ────────────────────────────────────


def step_gen_vasp(
    structure_path: str,
    template: str,
    spin: int | None,
    cutoff: float | None,
    charge: int | None,
    output_dir: Path,
) -> dict:
    """Run vasp-gen to produce INCAR+KPOINTS+POSCAR in *output_dir*."""
    from vasp_query.generator import generate, load_structure, kpoints_from_structure

    generate(
        template,
        structure=structure_path,
        spin=spin,
        cutoff=cutoff,
        sets=[f"NELECT={charge}"] if charge is not None else None,
        output=str(output_dir),
        write_poscar=True,
        write_kpoints=True,
    )
    # Also generate KPOINTS from structure if not already done
    incar_path = output_dir / "INCAR"
    poscar_path = output_dir / "POSCAR"
    kpoints_path = output_dir / "KPOINTS"
    if not kpoints_path.is_file() and poscar_path.is_file():
        struct = load_structure(str(poscar_path))
        kpts = kpoints_from_structure(struct)
        kpts.write_file(str(kpoints_path))

    # Read back INCAR tags for display
    from pymatgen.io.vasp.inputs import Incar
    incar = Incar.from_file(str(incar_path))

    return {
        "incar": dict(incar),
        "output_dir": str(output_dir),
        "has_incar": incar_path.is_file(),
        "has_poscar": poscar_path.is_file(),
        "has_kpoints": kpoints_path.is_file(),
    }


# ── Step 2—3: Cache lookup + reference extraction ────────────────────


def step_cache_lookup(
    output_dir: Path,
    match_threshold: float,
) -> dict | None:
    """Query vasp_cache for VASP calculations matching the generated inputs.

    Returns reference metadata if a close match is found, else None.
    """
    import vasp_cache  # noqa: F811
    from vasp_cache.fingerprint import content_hash as cache_content_hash

    # Quick exact match first
    if vasp_cache.has(str(output_dir)):
        vasp_cache.fetch(str(output_dir))
        from vasp_cache.parse import summarize_calc
        ref = summarize_calc(output_dir)
        ref["match_type"] = "exact"
        _print_step(
            "Cache 命中 (exact)",
            f"  content_hash: {cache_content_hash(output_dir)}",
            f"  total_energy = {ref.get('total_energy', 'N/A')} eV",
        )
        return ref

    # Fallback: query by formula + tags
    import pymatgen.core as pmg
    from vasp_cache.api import query

    poscar = output_dir / "POSCAR"
    if not poscar.is_file():
        return None

    struct = pmg.Structure.from_file(str(poscar))
    formula = struct.composition.reduced_formula
    nsites = struct.num_sites

    results = query(formula=formula, limit=5)
    if not results:
        return None

    # Score by similarity: prefer same nsites, same spacegroup, close lattice
    def _score(r: dict) -> float:
        score = 0.0
        if r.get("nsites") == nsites:
            score += 10
        elif r.get("nsites") is not None:
            score -= abs(r["nsites"] - nsites) * 0.1
        return score

    results.sort(key=_score, reverse=True)
    best = results[0]
    if _score(best) < match_threshold:
        return None

    from vasp_cache.api import get_meta
    meta = get_meta(content_hash=best.get("content_hash"))
    if meta is None:
        return None

    ref = {
        "match_type": "similar",
        "content_hash": best.get("content_hash"),
        "total_energy": best.get("total_energy"),
        "nsites": best.get("nsites"),
        "a": best.get("a"),
        "b": best.get("b"),
        "c": best.get("c"),
        "space_group": best.get("space_group"),
        "tags": best.get("tags", ""),
        "converged": best.get("converged"),
    }

    _print_step(
        "Cache 最近匹配 (similar)",
        f"  formula={formula}, nsites={nsites} ≈ ref nsites={best.get('nsites')}",
        f"  content_hash: {best.get('content_hash')}",
        f"  total_energy = {ref['total_energy']} eV",
    )
    return ref


# ── Step 4: Convert VASP inputs → OpenMX input.dat ───────────────────


def step_vasp2omx(
    output_dir: Path,
    template: str,
    spin: str | None,
    charge: int | None,
) -> dict:
    """Encode VASP INCAR → SemanticIR → decode as OpenMX → write .dat."""
    from omx_tools.parsers.vasp import parse_incar
    from omx_tools.semantic import encode_vasp, decode_omx
    from omx_tools.writers.openmx import write_dat
    from omx_tools.intent import CalculationIntent

    incar_path = output_dir / "INCAR"
    poscar_path = output_dir / "POSCAR"
    incar_data = parse_incar(str(incar_path))

    ir = encode_vasp(
        incar_data,
        structure_path=str(poscar_path),
        template=template if template in ("scf_band", "scf_band_metal", "scf_cluster",
                                          "geom_opt", "band_dispersion") else None,
    )
    omx_template, overrides = decode_omx(ir)
    if template:
        omx_template = template

    intent = CalculationIntent(
        template=omx_template,
        params=overrides,
        structure_path=str(poscar_path),
    )
    result = write_dat(intent, output_path=str(output_dir / "input.dat"))

    dat_path = output_dir / "input.dat"
    _print_step(
        "vasp2omx 转换完成",
        f"  input.dat → {dat_path}",
        f"  OMX template: {omx_template}",
        f"  VASP keys mapped: {len(overrides)}",
    )
    return {
        "dat_path": str(dat_path),
        "exists": dat_path.is_file(),
        "template": omx_template,
    }


# ── Step 5: Override OpenMX params with cache reference ──────────────


def step_override_with_reference(
    output_dir: Path,
    ref: dict | None,
    spin: str | None,
    charge: int | None,
) -> list[str]:
    """Edit input.dat to incorporate reference OUTCAR data.

    Returns list of applied overrides.
    """
    import re

    dat_path = output_dir / "input.dat"
    if not dat_path.is_file():
        return ["[skipped] input.dat not found"]

    text = dat_path.read_text()
    _: list[tuple[str, str, str]] = []  # (keyword, old_val, new_val)  unused
    changes: list[str] = []

    # ── 5a: Spin polarization from reference or CLI ──
    target_spin = None
    if ref and ref.get("converged"):
        # Check content_hash for INCAR parameters (contains ISPIN/NUPDOWN etc.)
        ch = ref.get("content_hash", "")
        has_spin = "ISPIN=2" in ch or "NUPDOWN" in ch
        target_spin = "On" if has_spin else "Off"
    elif spin:
        target_spin = {"off": "Off", "collinear": "On", "noncollinear": "NC"}.get(
            spin.lower(), None)
    if target_spin:
        # Check if spinpolarization already set correctly
        m = re.search(r"^scf\.spinpolarization\s+(\S+)", text,
                      flags=re.MULTILINE | re.IGNORECASE)
        current = m.group(1) if m else None
        if current and current.lower() == target_spin.lower():
            changes.append(f"scf.spinpolarization = {current} (already set by vasp2omx)")
        else:
            text, n = re.subn(
                r"^(scf\.spinpolarization)\s+\S+",
                lambda mo: f"{mo.group(1)}  {target_spin}",
                text,
                count=1,
                flags=re.MULTILINE | re.IGNORECASE,
            )
            if n:
                changes.append(f"scf.spinpolarization → {target_spin}")
    contcar = output_dir / "CONTCAR"
    if contcar.is_file() and ref and ref.get("a", 0) > 0:
        # CONTCAR from cache has relaxed lattice — note it for user
        changes.append(
            f"lattice from CONTCAR: a={ref['a']:.4f}, b={ref['b']:.4f}, "
            f"c={ref['c']:.4f} Å"
        )

    # ── 5c: System charge ────────────────────────────────────────────
    if charge is not None and charge != 0:
        changes.append(f"system charge: {charge} (set --charge {charge})")
        # vasp2omx already maps NELECT → scf.system.charge via semantic IR.
        # Only insert definition_of_amount_of_charge if scf.system.charge
        # is NOT already present.
        has_sys_charge = bool(re.search(
            r"^scf\.system\.charge\s+\S+",
            text, flags=re.MULTILINE | re.IGNORECASE,
        ))
        has_def = bool(re.search(
            r"^definition_of_amount_of_charge\s+\S+",
            text, flags=re.MULTILINE,
        ))
        if not has_def and not has_sys_charge:
            text, n = re.subn(
                r"^(scf\.(energycutoff|spinpolarization)\s+\S+)",
                f"\\1\ndefinition_of_amount_of_charge  {charge}",
                text, count=1,
                flags=re.MULTILINE | re.IGNORECASE,
            )
            if n:
                changes.append(f"definition_of_amount_of_charge → {charge}")
    # ── 5d: Energy cutoff from reference ──
    if ref and ref.get("tags"):
        tags_str: str = ref["tags"]
        for tok in tags_str.split(","):
            if tok.startswith("ENCUT="):
                vasp_encut = float(tok.split("=")[1])
                omx_cutoff = vasp_encut / 2.0
                # Update scf.energycutoff in input.dat
                text, n = re.subn(
                    r"^(scf\.energycutoff)\s+([\d.]+)",
                    f"\\1  {omx_cutoff}",
                    text,
                    count=1,
                    flags=re.MULTILINE,
                )
                if n:
                    changes.append(
                        f"scf.energycutoff → {omx_cutoff} Ry "
                        f"(from VASP ENCUT={vasp_encut:.0f})"
                    )
                break

    # ── Write back ──
    if text != dat_path.read_text():
        # Catch inadvertent no-ops
        pass
    dat_path.write_text(text)

    if not changes:
        changes.append("(no reference-driven overrides applicable)")

    _print_step("参考数据精修", *changes)

    return changes


# ── Step 6: semantic advise ──────────────────────────────────────────


def step_advise(output_dir: Path, ref: dict | None) -> dict:
    """Run dft semantic advise-omx on the generated input.dat."""
    from omx_tools.semantic.advise import advise_openmx_dat

    dat_path = output_dir / "input.dat"
    if not dat_path.is_file():
        return {"skipped": "input.dat not found"}

    result = advise_openmx_dat(str(dat_path), fetch_knowledge=True)

    n_error = result.get("n_error", 0)
    n_warn = result.get("n_warning", 0)
    findings = result.get("findings", [])

    _print_step(
        "dft semantic advise-omx",
        f"  errors: {n_error}   warnings: {n_warn}",
        *([f"  ⚠ {f.get('tag','')}: {f.get('message','')[:100]}"
           for f in findings[:5]] or ["  ✓ 无问题"]),
    )

    return result


# ── Main ──────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Bootstrap OpenMX calculation from vasp_cache VASP references",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Example:
              # NV⁻ center in diamond (3×3×3 supercell, ~215 atoms)
              python scripts/cache_bootstrap_openmx.py nv_supercell.cif \\
                  -o nv_calc/ --spin collinear --charge -1 --template scf_band

            Requires:
              pip install -e "~/vasp_wiki[all]"   # vasp-wiki
              pip install -e "~/vasp_cache"        # vasp-cache (optional)
        """),
    )

    parser.add_argument("structure", help="Structure file (CIF/POSCAR/XYZ)")
    parser.add_argument("-o", "--output", default="omx_calc",
                        help="Output directory (default: omx_calc)")
    parser.add_argument("-t", "--template", default="scf_band",
                        choices=["scf_band", "scf_band_metal", "scf_cluster",
                                 "geom_opt", "band_dispersion"],
                        help="OpenMX template (default: scf_band)")
    parser.add_argument("--spin", default=None,
                        choices=["off", "collinear", "noncollinear"],
                        help="Override spin polarization")
    parser.add_argument("--charge", type=int, default=None,
                        help="System charge (e.g. -1 for NV⁻)")
    parser.add_argument("--cutoff", type=float, default=None,
                        help="Override ENCUT in eV (→ OpenMX Ry/2)")
    parser.add_argument("--vasp-template", default="scf",
                        choices=["scf", "scf_metal", "relax", "band", "md"],
                        help="VASP template for intermediate input gen")
    parser.add_argument("--match-threshold", type=float, default=5.0,
                        help="Min similarity score for cache fuzzy match (default: 5)")
    parser.add_argument("--no-cache", action="store_true",
                        help="Skip cache lookup even if vasp_cache is installed")

    args = parser.parse_args()

    structure_path = args.structure
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    has_cache = _check_cache() and not args.no_cache

    # ──────────────────────────────────────────────────────────────────
    print(f"{'=' * 72}")
    print(f"  cache_bootstrap_openmx")
    print(f"  structure: {structure_path}")
    print(f"  OpenMX template: {args.template}")
    print(f"  vasp_cache: {'✓ available' if has_cache else '✗ not found'}")
    print(f"{'=' * 72}")

    # ── Step 1: VASP input generation ─────────────────────────────────
    _print_step("Step 1/5", "Generate intermediate VASP inputs (vasp-gen)")
    vasp_result = step_gen_vasp(
        structure_path=structure_path,
        template=args.vasp_template,
        spin={"off": 1, "collinear": 2, "noncollinear": 3}.get(
            args.spin) if args.spin else None,
        cutoff=args.cutoff,
        charge=args.charge,
        output_dir=output_dir,
    )

    incar = vasp_result.get("incar", {})
    print(f"  ENCUT={incar.get('ENCUT', 'template')} eV "
          f"→ scf.energycutoff={incar.get('ENCUT', 520) / 2:.0f} Ry")

    # ── Step 2—3: Cache lookup ───────────────────────────────────────
    ref: dict | None = None
    if has_cache:
        _print_step("Step 2/5", "Query vasp_cache for matching calculations")
        ref = step_cache_lookup(output_dir, args.match_threshold)
        if ref is None:
            print("  (no match in cache — proceeding without reference)")
    else:
        print("\n  (skipping cache — install vasp_cache or use --no-cache)")

    # ── Step 4: vasp2omx ─────────────────────────────────────────────
    _print_step("Step 3/5", "Convert VASP inputs → OpenMX input.dat (vasp2omx)")
    _ = step_vasp2omx(
        output_dir=output_dir,
        template=args.template,
        spin=args.spin,
        charge=args.charge,
    )

    # ── Step 5: Reference overrides ──────────────────────────────────
    _print_step("Step 4/5", "Apply reference data to OpenMX input")
    overrides = step_override_with_reference(
        output_dir=output_dir,
        ref=ref,
        spin=args.spin,
        charge=args.charge,
    )

    # ── Step 6: Advisory ─────────────────────────────────────────────
    _print_step("Step 5/5", "Semantic advisory on final input.dat")
    advise_result = step_advise(output_dir=output_dir, ref=ref)

    # ── Summary ──────────────────────────────────────────────────────
    dat_path = output_dir / "input.dat"
    summary = {
        "structure": structure_path,
        "omx_template": args.template,
        "vasp_template": args.vasp_template,
        "output_dir": str(output_dir),
        "files": {
            "input.dat": dat_path.is_file(),
            "INCAR": (output_dir / "INCAR").is_file(),
            "POSCAR": (output_dir / "POSCAR").is_file(),
            "KPOINTS": (output_dir / "KPOINTS").is_file(),
        },
        "cache_match": ref["match_type"] if ref else None,
        "cache_energy_eV": ref.get("total_energy") if ref else None,
        "cache_converged": ref.get("converged") if ref else None,
        "applied_overrides": overrides,
        "advise_errors": advise_result.get("n_error", 0),
        "advise_warnings": advise_result.get("n_warning", 0),
    }

    summary_path = output_dir / "_bootstrap_summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False)
    )

    # ── Print final instructions ──────────────────────────────────────
    print(f"\n{'=' * 72}")
    print(f"  ✅ 完成 — OpenMX 输入已生成于 {output_dir}/")
    print(f"  ────────────────────────────────────────────────────")
    if dat_path.is_file():
        print(f"  input.dat     {dat_path}")
    print(f"  参考 OUTCAR    {'已从 cache 恢复 ✓' if ref else '无 cache 匹配'}")
    print(f"  建议查阅      {summary_path}")
    print()
    if ref and ref.get("total_energy") is not None:
        print(f"  VASP 参考能量:  {ref['total_energy']:.6f} eV")
        print(f"  (OpenMX 运行后可与 VASP 能量对账)")
    print()

    # NV⁻ specific hints
    if args.charge == -1 and args.spin == "collinear":
        print(f"  NV⁻ 色心提示:")
        print(f"    • spin=On (S=1 三重态)")
        print(f"    • 电荷 = {args.charge}")
        print(f"    • 建议超胞 ≥ 215 原子以解耦缺陷-缺陷相互作用")
        print()

    print(f"  运行 OpenMX:")
    print(f"    OpenMX -s  {output_dir / 'input.dat'}")
    print()
    print(f"  与 VASP 结果对比确认后, 写入 cache:")
    print(f"    vasp-cache put {output_dir}")
    print(f"{'=' * 72}")

    return 0 if advise_result.get("n_error", 0) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
