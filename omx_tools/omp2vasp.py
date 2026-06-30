"""omp2vasp — Convert OpenMX .dat to VASP INCAR.

Translates OpenMX calculation parameters back into an equivalent VASP
INCAR file, enabling round-trip conversion between the two formats.
"""

import argparse
import json
import sys
from pathlib import Path

from omx_tools._utils import load_json
from omx_tools.parsers.openmx import parse_dat
from omx_tools.mapping import reverse
from omx_tools.writers.vasp import write_incar

PKG_DIR = Path(__file__).resolve().parent
VASP_MAPPING_PATH = PKG_DIR / "schemas" / "vasp_to_ase.json"


def cli():
    """Command-line entry point for omp2vasp."""
    parser = argparse.ArgumentParser(
        description="Convert OpenMX .dat to VASP INCAR",
    )
    parser.add_argument("dat_file", help="Path to OpenMX .dat file")
    parser.add_argument("structure", nargs="?",
                        default="",
                        help="Path to structure file (optional, for consistency)")
    parser.add_argument("-o", "--output", help="Output INCAR path (default: stdout)")
    parser.add_argument("-t", "--template", default="scf_band",
                        help="Template name (default: scf_band)")
    parser.add_argument("-d", "--dry-run", action="store_true",
                        help="Print INCAR to stdout")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Show parameter mapping details on stderr")

    args = parser.parse_args()

    # ── Step 1: Validate inputs ──────────────────────────────────────────
    dat_path = args.dat_file
    if not Path(dat_path).is_file():
        err = {"error": f".dat file not found: {dat_path}",
               "suggestion": "Check the path and try again"}
        print(json.dumps(err))
        sys.exit(1)

    # ── Step 2: Parse .dat → ASE params ──────────────────────────────────
    if args.verbose:
        print(f"[INFO] Parsing {dat_path}", file=sys.stderr)

    keywords = load_json(str(PKG_DIR / "schemas" / "keywords.json"),
                         "keywords.json")
    ase_params = parse_dat(dat_path, keywords=keywords)

    if args.verbose:
        print(f"[INFO] Extracted {len(ase_params)} ASE parameters",
              file=sys.stderr)
        for k, v in sorted(ase_params.items()):
            print(f"  {k} = {v}", file=sys.stderr)

    # ── Step 3: Load mapping table ───────────────────────────────────────
    mapping = load_json(str(VASP_MAPPING_PATH), "vasp_to_ase.json")

    # ── Step 4: Reverse map: ASE params → VASP tags ──────────────────────
    vasp_params = reverse(ase_params, mapping, verbose=args.verbose)

    if args.verbose:
        print(f"[INFO] Mapped {len(vasp_params)} VASP parameters",
              file=sys.stderr)
        for k, v in sorted(vasp_params.items()):
            print(f"  {k} = {v}", file=sys.stderr)

    # ── Step 5: Write INCAR ──────────────────────────────────────────────
    if args.dry_run or args.output == "-":
        write_incar(vasp_params, "-", verbose=args.verbose)
    else:
        out = args.output or Path(dat_path).stem + ".INCAR"
        write_incar(vasp_params, out, verbose=args.verbose)


if __name__ == "__main__":
    cli()
