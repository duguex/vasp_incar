"""OpenMX .dat writer — consumes CalculationIntent to produce .dat files."""

import os
import sys
import tempfile
from pathlib import Path

from omx_tools._utils import load_json, auto_kgrid, die_json
from omx_tools.intent import CalculationIntent

PKG_DIR = Path(__file__).resolve().parent.parent
SCHEMA_PATH = PKG_DIR / "schemas" / "keywords.json"
TEMPLATES_PATH = PKG_DIR / "schemas" / "templates.json"


def to_ase_key(openmx_key: str, schema: dict) -> str:
    """Convert an OpenMX keyword string to an ASE key string."""
    if openmx_key in schema:
        entry = schema[openmx_key]
        if entry.get("ase_key"):
            return entry["ase_key"]
    parts = openmx_key.split(".")
    return "_".join(parts).lower()


def _add_shorthand_units(params: dict) -> None:
    """Add ASE shorthand keys for unit conversion (eV→Ha, eV/Å→Ha/Bohr).

    ``scf_energycutoff`` is NOT handled here — it uses a heuristic ×2
    mapping in ``mapping.forward()`` (ENCUT eV → OpenMX Ry).
    """
    from ase.units import Bohr, Ha

    if "scf_criterion" in params and "convergence" not in params:
        params["convergence"] = params["scf_criterion"]
    if "md_opt_criterion" in params:
        params["md_opt_criterion"] = params["md_opt_criterion"] / (Ha / Bohr)


def write_dat(
    intent: CalculationIntent,
    *,
    kspacing: float = 0.33,
    dry_run: bool = False,
    verbose: bool = False,
    output_path: str | None = None,
    json_output: bool = False,
    schema_path: str | Path | None = None,
    templates_path: str | Path | None = None,
) -> dict:
    """Generate an OpenMX .dat input file from a *CalculationIntent*."""
    try:
        from ase.io import read
        from ase.calculators.openmx import OpenMX
    except ImportError:
        die_json(
            "omx-gen requires ASE. Install with: pip install 'omx-tools[gen]'",
            json_output=json_output,
        )

    schema = load_json(schema_path or SCHEMA_PATH, "keywords.json")
    templates = load_json(templates_path or TEMPLATES_PATH, "templates.json")

    if verbose:
        print(f"Reading structure: {intent.structure_path}", file=sys.stderr)
    try:
        atoms = read(intent.structure_path)
    except Exception as e:
        die_json(
            f"reading structure file '{intent.structure_path}': {e}",
            json_output=json_output,
        )

    if verbose:
        print(
            f"  Atoms: {len(atoms)}, formula: {atoms.get_chemical_formula()}",
            file=sys.stderr,
        )

    if intent.template not in templates:
        die_json(
            f"unknown template '{intent.template}'. "
            f"Available: {', '.join(sorted(templates.keys()))}",
            json_output=json_output,
        )

    template = templates[intent.template]
    params: dict = dict(template["keywords"])

    if verbose:
        print(
            f"Using template: {intent.template} — "
            f"{template.get('description', '')}",
            file=sys.stderr,
        )

    # Auto k-points
    if template.get("auto_kpoints") and "kpts" not in intent.params:
        kgrid = auto_kgrid(atoms, kspacing)
        params["kpts"] = tuple(kgrid)
        if verbose:
            print(
                f"  Auto kpts: {tuple(kgrid)} (kspacing={kspacing} 1/Å)",
                file=sys.stderr,
            )

    # Apply overrides
    for key, value in intent.params.items():
        params[key] = value
        if verbose:
            print(f"  Override: {key} = {value}", file=sys.stderr)

    # Resolve None defaults from schema
    for key in list(params.keys()):
        if params[key] is None:
            for omx_k, entry in schema.items():
                if entry.get("ase_key") == key and entry.get("default") is not None:
                    params[key] = entry["default"]
                    if verbose:
                        print(
                            f"  Schema default: {key} = {entry['default']}",
                            file=sys.stderr,
                        )
                    break

    # Resolve DATA.PATH
    if "data_path" not in params or not params.get("data_path"):
        env_path = os.environ.get("OPENMX_DFT_DATA_PATH")
        if env_path:
            params["data_path"] = env_path
            if verbose:
                print(f"  Using OPENMX_DFT_DATA_PATH: {env_path}", file=sys.stderr)
        else:
            bundled = PKG_DIR.parent / "openmx4.0" / "DFT_DATA19"
            if bundled.is_dir():
                params["data_path"] = str(bundled.resolve())
                if verbose:
                    print(f"  Using bundled DFT_DATA19: {bundled}", file=sys.stderr)
            else:
                die_json(
                    "DATA.PATH not set. Set OPENMX_DFT_DATA_PATH to your DFT_DATA19 "
                    "directory (e.g. /mnt/shared/DFT_DATA19).",
                    json_output=json_output,
                )

    data_path = params["data_path"]
    vps_dir = os.path.join(data_path, "VPS")
    if not os.path.isdir(vps_dir):
        die_json(f"VPS directory not found at {vps_dir}", json_output=json_output)

    # ASE shorthand keys for unit conversion
    _add_shorthand_units(params)

    # Generate output stem
    if output_path:
        stem = Path(output_path).stem
    else:
        stem = Path(intent.structure_path).stem

    # Write input
    if dry_run:
        with tempfile.TemporaryDirectory() as tmpdir:
            calc = OpenMX(label=os.path.join(tmpdir, stem), command="", **params)
            calc.write_input(atoms)
            dat_path = os.path.join(tmpdir, f"{stem}.dat")
            with open(dat_path) as f:
                content = f.read()
        content = "\n".join(
            l
            for l in content.split("\n")
            if not l.strip().startswith("System.CurrentDirectory")
        )
        sys.stdout.write(content)
        if verbose:
            print("(dry-run: printed to stdout)", file=sys.stderr)
    else:
        out_path = output_path or f"{stem}.dat"
        calc = OpenMX(label=os.path.join(os.getcwd(), stem), command="", **params)
        calc.write_input(atoms)
        written = f"{stem}.dat"
        if (
            os.path.abspath(written) != os.path.abspath(out_path)
            and os.path.exists(written)
        ):
            import shutil
            shutil.move(written, out_path)
        with open(out_path) as f:
            lines = f.readlines()
        kept = [
            l for l in lines if not l.strip().startswith("System.CurrentDirectory")
        ]
        if len(kept) != len(lines):
            with open(out_path, "w") as f:
                f.writelines(kept)
        if verbose:
            print(f"Written: {out_path}", file=sys.stderr)

    return params
