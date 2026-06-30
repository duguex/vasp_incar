"""omx-gen — OpenMX input file generator."""

import argparse
import json
import os
import sys
from pathlib import Path

from omx_tools._utils import load_json, die_json
from omx_tools.intent import CalculationIntent
from omx_tools.writers.openmx import write_dat, to_ase_key

PKG_DIR = Path(__file__).resolve().parent
SCHEMA_PATH = PKG_DIR / "schemas" / "keywords.json"
TEMPLATES_PATH = PKG_DIR / "schemas" / "templates.json"


def generate_input(structure_path, template_name, overrides, schema,
                   templates, kspacing, dry_run, verbose, output_path,
                   json_output=False):
    """Thin backward-compat wrapper.  Delegates to :func:`write_dat`."""
    intent = CalculationIntent(
        template=template_name,
        params=overrides,
        structure_path=structure_path,
    )
    return write_dat(
        intent,
        kspacing=kspacing,
        dry_run=dry_run,
        verbose=verbose,
        output_path=output_path,
        json_output=json_output,
        schema_path=SCHEMA_PATH,
        templates_path=TEMPLATES_PATH,
    )


def lookup_templates_json(templates):
    """Return templates as JSON-serializable list of dicts."""
    return [
        {"name": name, "description": t.get("description"),
         "auto_kpoints": t.get("auto_kpoints"),
         "requires_prior_scf": t.get("requires_prior_scf"),
         "keywords": t["keywords"]}
        for name, t in sorted(templates.items())
    ]


def lookup_keywords_json(schema):
    """Return keyword schema as JSON-serializable list, sorted by name."""
    return [{"name": k, **v} for k, v in sorted(schema.items())]


def cli():
    parser = argparse.ArgumentParser(
        description="Generate OpenMX .dat input files from structure + templates",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("structure", nargs="?",
                        help="Input structure file (CIF, XYZ, POSCAR, ...)")
    parser.add_argument("-t", "--template", default="scf_band",
                        help="Calculation template (default: scf_band)")
    parser.add_argument("-o", "--output", help="Output .dat file")
    parser.add_argument("--list-templates", action="store_true",
                        help="List available templates")
    parser.add_argument("--list-keywords", action="store_true",
                        help="List all known keywords with type info")
    parser.add_argument("--type",
                        help="Filter by type (string, integer, float, bool, tuple_integer, tuple_float, matrix)")
    parser.add_argument("--keyword", metavar="KEY",
                        help="Show structured metadata for a single keyword")
    parser.add_argument("-k", "--kpoints", type=int, nargs=3,
                        metavar=("NX", "NY", "NZ"),
                        help="Override k-point grid")
    parser.add_argument("--kspacing", type=float, default=0.33,
                        help="k-point spacing in 1/Å (default: 0.33)")
    parser.add_argument("-x", "--xc",
                        help="Override XC functional (PBE, LDA, etc.)")
    parser.add_argument("--spin", help="Override spin: Off | On | NC")
    parser.add_argument("--cutoff", type=float,
                        help="Override energy cutoff (eV)")
    parser.add_argument("-s", "--set", action="append", default=[],
                        metavar="KEY=VALUE",
                        help="Set an arbitrary OpenMX keyword")
    parser.add_argument("-d", "--dry-run", action="store_true",
                        help="Print to stdout instead of writing file")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Show keyword resolution")
    parser.add_argument("-j", "--json", action="store_true",
                        help="JSON output (machine-readable)")

    args = parser.parse_args()
    schema = load_json(SCHEMA_PATH, "keywords.json")
    templates = load_json(TEMPLATES_PATH, "templates.json")

    if args.list_templates:
        if args.json:
            print(json.dumps(lookup_templates_json(templates), indent=2, ensure_ascii=False))
        else:
            print("Available templates:")
            for name, t in sorted(templates.items()):
                auto = " [auto-kpoints]" if t.get("auto_kpoints") else ""
                prior = " [requires prior SCF]" if t.get("requires_prior_scf") else ""
                desc = t.get("description", "")
                print(f"  {name}{auto}{prior}")
                if desc:
                    print(f"        {desc}")
                for key, val in t["keywords"].items():
                    val_str = json.dumps(val) if val is not None else "auto"
                    print(f"          {key} = {val_str}")
        return

    if args.list_keywords:
        if args.json:
            kw_list = lookup_keywords_json(schema)
            if args.type:
                kw_list = [e for e in kw_list if e.get("type") == args.type]
            print(json.dumps(kw_list, indent=2, ensure_ascii=False))
        else:
            print("Known keywords:")
            for kw, entry in sorted(schema.items()):
                if entry["type"]:
                    print(f"  {kw}  [{entry['type']}]", end="")
                    if entry.get("default"):
                        print(f"  default={entry['default']}", end="")
                    if entry.get("unit"):
                        print(f"  ({entry['unit']})", end="")
                    print()
                else:
                    print(f"  {kw}  [untyped — manual section keyword]")
        return

    if args.keyword:
        kw = args.keyword
        if kw not in schema:
            die_json(f"Keyword '{kw}' not found in schema", json_output=args.json)
        if args.json:
            print(json.dumps(schema[kw], indent=2, ensure_ascii=False))
        else:
            entry = schema[kw]
            print(f"{kw}:")
            print(f"  type:        {entry.get('type', 'null')}")
            print(f"  ase_key:     {entry.get('ase_key', 'null')}")
            print(f"  default:     {json.dumps(entry.get('default'))}")
            print(f"  valid:       {json.dumps(entry.get('valid_values'))}")
            print(f"  unit:        {json.dumps(entry.get('unit'))}")
            print(f"  section:     {entry.get('section', 'null')}")
            print(f"  source:      {entry.get('source', 'null')}")
            if entry.get("description"):
                print(f"  description: {entry['description']}")
        return

    if not args.structure:
        die_json("STRUCTURE file is required. Use --help for usage.", json_output=args.json)

    if not os.path.isfile(args.structure):
        die_json(f"structure file '{args.structure}' not found", json_output=args.json)

    overrides = {}
    for arg in args.set:
        if "=" not in arg:
            print(f"Warning: --set '{arg}' missing '=', skipping", file=sys.stderr)
            continue
        key, _, raw_val = arg.partition("=")
        ase_key = to_ase_key(key.strip(), schema)
        raw_val = raw_val.strip()
        try:
            val = float(raw_val) if ("." in raw_val or "e" in raw_val.lower()) else int(raw_val)
        except (ValueError, TypeError):
            val = raw_val
        overrides[ase_key] = val

    if args.kpoints:
        overrides["kpts"] = tuple(args.kpoints)
    if args.xc:
        overrides["scf_xctype"] = args.xc
    if args.spin:
        overrides["scf_spinpolarization"] = args.spin
    if args.cutoff:
        overrides["energy_cutoff"] = args.cutoff

    generate_input(
        structure_path=args.structure,
        template_name=args.template,
        overrides=overrides,
        schema=schema,
        templates=templates,
        kspacing=args.kspacing,
        dry_run=args.dry_run,
        verbose=args.verbose,
        output_path=args.output,
        json_output=args.json,
    )


if __name__ == "__main__":
    cli()
