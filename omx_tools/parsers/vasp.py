"""VASP INCAR parser — parse .incar → typed dict, detect intent."""

import json
import sys


def parse_incar(path: str) -> dict:
    """Parse a VASP INCAR file using pymatgen.

    Returns a typed dict {key: value} with numeric types preserved,
    bools converted from .TRUE./.FALSE., and comments stripped.
    """
    try:
        from pymatgen.io.vasp import Incar
    except ImportError:
        print(json.dumps({
            "error": "pymatgen required",
            "suggestion": "pip install pymatgen",
        }))
        sys.exit(1)

    d = Incar.from_file(path).as_dict()
    # Strip pymatgen metadata keys (@module, @class)
    return {k: v for k, v in d.items() if not k.startswith("@")}


def detect_intent_from_incar(params: dict) -> str:
    """Detect the OpenMX template name from VASP INCAR parameters.

    Rules are evaluated in priority order (highest first). Returns the
    name of a template registered in templates.json.
    """
    # 1. Band structure (post-SCF)
    if params.get("ICHARG") == 11:
        return "band_dispersion"

    # 2. Optics (no dedicated OpenMX template — use SCF as proxy)
    if params.get("LOPTICS") is True:
        return "scf_band"

    # 3. Geometry relaxation
    nsw = params.get("NSW", 0)
    ibrion = params.get("IBRION")
    if nsw > 0 and ibrion in (1, 2, 3):
        return "geom_opt"

    # 4. Metallic SCF (large smearing)
    if (nsw == 0
            and params.get("ISMEAR") in (0, 1)
            and params.get("SIGMA", 0) > 0.1):
        return "scf_band_metal"

    # 5. Spin-polarised (non-metal template is fine)
    if params.get("ISPIN") == 2:
        return "scf_band"

    # 6. Default
    return "scf_band"


def parse_potcar_species(path: str) -> list[dict]:
    """Extract species info (symbol, ZVAL) from POTCAR in file order.

    Parameters
    ----------
    path : str
        Path to POTCAR file.

    Returns
    -------
    list[dict]
        Each entry: {"symbol": str, "zval": float}, in POTCAR order.
    """
    species: list[dict] = []
    current: dict | None = None
    with open(path) as f:
        for line in f:
            if line.startswith("   TITEL"):
                # TITEL = PAW_PBE N 08Apr2002 → symbol is 4th field (index 3)
                parts = line.split()
                if len(parts) >= 5:
                    if current is not None:
                        species.append(current)
                    current = {"symbol": parts[3], "zval": None}
            if "ZVAL" in line and "=" in line and current is not None:
                parts = line.split(";")
                for part in parts:
                    if "ZVAL" in part:
                        val_str = part.split("=")[1].strip().split()[0]
                        current["zval"] = float(val_str)
    if current is not None:
        species.append(current)
    return species


def parse_potcar_zvals(path: str) -> list[float]:
    """Extract ZVAL values per species (backward-compat, returns zvals only)."""
    return [s["zval"] for s in parse_potcar_species(path)]

def _count_atoms_in_structure(structure_path: str) -> dict[str, int]:
    """Count atoms per element symbol from a structure file.

    Uses pymatgen to parse POSCAR/CIF/XYZ.
    Falls back to manual POSCAR header parsing if pymatgen unavailable.
    """
    try:
        from pymatgen.core import Structure
        try:
            s = Structure.from_file(structure_path)
            counts: dict[str, int] = {}
            for site in s:
                sym = site.specie.symbol
                counts[sym] = counts.get(sym, 0) + 1
            return counts
        except Exception:
            pass
    except ImportError:
        pass

    # Fallback: manual POSCAR header parsing
    counts = {}
    with open(structure_path) as f:
        lines = f.readlines()
    # Line 5: element symbols  e.g. "C N" or "Si C"
    # Line 6: counts per element e.g. "510 1"
    if len(lines) >= 6:
        elem_line = lines[5].strip()
        count_line = lines[6].strip()
        elems = elem_line.split()
        nums = [int(x) for x in count_line.split()]
        if len(elems) == len(nums):
            counts = dict(zip(elems, nums))
    return counts


def compute_charge_from_nelect(
    nelect: float,
    structure_path: str,
    potcar_path: str,
) -> float:
    """Compute the charge state from NELECT, structure, and POTCAR.

    Formula: charge = sum(ZVAL × count) - NELECT

    For a neutral system, NELECT = sum of valence electrons.
    If NELECT > neutral_sum, the system has extra electrons (negative charge).

    Returns the charge state (positive = hole doping).
    """
    species = parse_potcar_species(potcar_path)
    species_counts = _count_atoms_in_structure(structure_path)

    if not species or not species_counts:
        return nelect  # can't compute, passthrough

    neutral_sum = 0.0
    for entry in species:
        sym = entry["symbol"]
        zval = entry["zval"]
        if zval is None or sym not in species_counts:
            return nelect  # missing data, passthrough
        neutral_sum += zval * species_counts[sym]

    if neutral_sum == 0:
        return nelect

    return neutral_sum - nelect
