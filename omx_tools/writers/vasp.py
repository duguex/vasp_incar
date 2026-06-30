"""VASP INCAR writer — consumes CalculationIntent to produce INCAR files."""

import json
import sys


def write_incar(
    params: dict,
    output_path: str,
    *,
    sort_keys: bool = True,
    verbose: bool = False,
) -> None:
    """Write a VASP INCAR file from a VASP-tagged parameter dict.

    Parameters
    ----------
    params : dict
        VASP tag → value dict (e.g. from ``mapping.reverse()``).
    output_path : str
        Path to write the INCAR file.
    sort_keys : bool
        Sort INCAR keys alphabetically (default True).
    verbose : bool
        Show write confirmation on stderr.
    """
    try:
        from pymatgen.io.vasp import Incar
    except ImportError:
        print(json.dumps({
            "error": "pymatgen required",
            "suggestion": "pip install pymatgen",
        }))
        sys.exit(1)

    incar = Incar(params)
    content = incar.get_str(pretty=True, sort_keys=sort_keys)

    if output_path == "-":
        sys.stdout.write(content)
        if verbose:
            print("(dry-run: printed to stdout)", file=sys.stderr)
    else:
        with open(output_path, "w") as f:
            f.write(content)
        if verbose:
            print(f"Written: {output_path}", file=sys.stderr)
