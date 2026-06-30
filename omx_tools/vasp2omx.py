"""vasp2omx — Convert VASP INCAR to OpenMX .dat input file.

Translates VASP calculation intent and parameters into an equivalent
OpenMX .dat input using the three-layer translator architecture.

Usage:
    vasp2omx INCAR POSCAR [-o output.dat] [-t template] [--dry-run] [-v]
"""

import argparse
import json
import sys
from pathlib import Path

from omx_tools._utils import load_json
from omx_tools.parsers.vasp import (
    parse_incar,
    detect_intent_from_incar,
    compute_charge_from_nelect,
)
from omx_tools.mapping import forward
from omx_tools.intent import CalculationIntent
from omx_tools.writers.openmx import write_dat

PKG_DIR = Path(__file__).resolve().parent
VASP_MAPPING_PATH = PKG_DIR / "schemas" / "vasp_to_ase.json"


def _find_potcar(incar_path: str) -> str | None:
    """Look for POTCAR alongside the INCAR file."""
    incar_dir = Path(incar_path).parent
    potcar_path = incar_dir / "POTCAR"
    if potcar_path.is_file():
        return str(potcar_path)
    return None


def cli():
    """Command-line entry point for vasp2omx."""
    parser = argparse.ArgumentParser(
    )
    parser.add_argument("incar", help="Path to VASP INCAR file")
    parser.add_argument("structure", help="Path to structure file (POSCAR/CIF/XYZ)")
    parser.add_argument("-o", "--output", help="Output .dat path (default: <stem>.dat)")
    parser.add_argument("-t", "--template",
                        help="Override auto-detected template name")
    parser.add_argument("-d", "--dry-run", action="store_true",
                        help="Print .dat to stdout instead of writing")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Show parameter mapping details on stderr")
    parser.add_argument("--kspacing", type=float, default=0.33,
                        help="k-point spacing in 1/Å (default: 0.33)")
    parser.add_argument("--charge", type=float, default=None,
                        help="Override charge state (auto-detected from NELECT+POTCAR)")

    args = parser.parse_args()

    # ── Step 1: Read INCAR ──────────────────────────────────────────────
    incar_path = args.incar
    if not Path(incar_path).is_file():
        err = {"error": f"INCAR file not found: {incar_path}",
               "suggestion": "Check the path and try again"}
        print(json.dumps(err))
        sys.exit(1)

    try:
        params = parse_incar(incar_path)
    except Exception as exc:
        err = {"error": f"Failed to parse INCAR: {exc}",
               "suggestion": "Ensure the file is a valid VASP INCAR"}
        print(json.dumps(err))
        sys.exit(1)

    if args.verbose:
        print(f"[INFO] Parsed {len(params)} parameters from {incar_path}",
              file=sys.stderr)

    # ── Step 2: Load mapping table ──────────────────────────────────────
    mapping = load_json(str(VASP_MAPPING_PATH), "vasp_to_ase.json")

    # ── Step 3: Detect intent (or override) ──────────────────────────────
    template = args.template or detect_intent_from_incar(params)
    if args.verbose:
        print(f"[INFO] Template: {template}"
              + (" (auto-detected)" if not args.template else " (user override)"),
              file=sys.stderr)

    # ── Step 4: Map parameters ───────────────────────────────────────────
    overrides = forward(params, mapping, verbose=args.verbose)
    if args.verbose:
        print(f"[INFO] Mapped {len(overrides)} parameters", file=sys.stderr)

    # ── Step 5: Report unmappable parameters with notes ──────────────────
    if args.verbose:
        for vasp_key, vasp_val in params.items():
            entry = mapping.get(vasp_key)
            if entry and entry.get("omx_key") is None:
                note = entry.get("note")
                if note:
                    print(f"[WARN] {vasp_key}={vasp_val} — {note}",
                          file=sys.stderr)

    # ── Step 5a: Auto-detect charge from NELECT + POTCAR ─────────────────
    nelect = params.get("NELECT")
    if nelect is not None and args.charge is None:
        potcar_path = _find_potcar(incar_path)
        if potcar_path:
            try:
                charge = compute_charge_from_nelect(
                    float(nelect), args.structure, potcar_path,
                )
                if charge != float(nelect):  # successfully computed
                    overrides["scf_system_charge"] = charge
                    if args.verbose:
                        print(
                            f"[INFO] NELECT={nelect} → charge={charge:.1f} "
                            f"(auto-detected from POTCAR)",
                            file=sys.stderr,
                        )
                else:
                    if args.verbose:
                        print(
                            f"[WARN] Could not compute charge from NELECT={nelect}",
                            file=sys.stderr,
                        )
            except Exception as exc:
                if args.verbose:
                    print(f"[WARN] Failed to parse POTCAR: {exc}",
                          file=sys.stderr)
        else:
            if args.verbose:
                print(f"[WARN] No POTCAR found near INCAR, NELECT={nelect} "
                      f"not converted to charge. Use --charge FLOAT to set manually.",
                      file=sys.stderr)

    # ── Step 5b: Apply --charge override ─────────────────────────────────
    if args.charge is not None:
        overrides["scf_system_charge"] = args.charge
        if args.verbose:
            print(f"[INFO] --charge={args.charge}: overrides NELECT mapping",
                  file=sys.stderr)

    # ── Step 6: Build CalculationIntent and write ───────────────────────
    intent = CalculationIntent(
        template=template,
        params=overrides,
        structure_path=args.structure,
    )

    try:
        write_dat(
            intent,
            kspacing=args.kspacing,
            dry_run=args.dry_run,
            verbose=args.verbose,
            output_path=args.output,
        )
    except Exception as exc:
        err = {"error": f"Failed to generate OpenMX input: {exc}",
               "suggestion": "Check the structure file and template"}
        print(json.dumps(err))
        sys.exit(1)


if __name__ == "__main__":
    cli()
