"""Bidirectional VASP ↔ ASE parameter mapping."""

import sys


def forward(params: dict, mapping: dict, verbose: bool = False) -> dict:
    """Map VASP INCAR parameters to ASE/OpenMX override keys."""
    overrides: dict = {}

    for vasp_key, vasp_val in params.items():
        if vasp_key not in mapping:
            continue

        entry = mapping[vasp_key]
        omx_key = entry.get("omx_key")
        if omx_key is None:
            continue

        convert = entry.get("convert")
        try:
            if convert == "passthrough":
                overrides[omx_key] = vasp_val

            elif convert == "encut":
                overrides[omx_key] = float(vasp_val) / 2.0

            elif convert == "nsw":
                v = int(vasp_val)
                overrides[omx_key] = max(v, 1)
                if verbose and v == 0:
                    print(f"[INFO] NSW={v} → md_maxiter=1 (OpenMX requires ≥1)",
                          file=sys.stderr)

            elif convert == "bool":
                overrides[omx_key] = bool(vasp_val)

            elif convert == "spin":
                v = int(vasp_val)
                if v == 1:
                    overrides[omx_key] = "Off"
                elif v == 2:
                    overrides[omx_key] = "On"
                elif v == 3:
                    overrides[omx_key] = "NC"
                else:
                    overrides[omx_key] = "Off"

            elif convert == "xc":
                s = str(vasp_val).upper()
                if s == "PE":
                    overrides[omx_key] = "GGA-PBE"
                elif s == "91":
                    overrides[omx_key] = "GGA-PW91"
                elif s == "CA":
                    overrides[omx_key] = "LDA-CA"
                else:
                    overrides[omx_key] = vasp_val

            elif convert == "abs_to_pos":
                overrides[omx_key] = abs(float(vasp_val))

            elif convert == "algo":
                s = str(vasp_val).upper().rstrip(".")
                if s in ("N", "NORMAL", "F", "FAST", "V", "VERYFAST", "D", "DAMPED"):
                    overrides[omx_key] = "Band"
                elif s in ("A", "ALL"):
                    overrides[omx_key] = "Band"
                else:
                    overrides[omx_key] = vasp_val

            elif convert == "nelect":
                overrides[omx_key] = float(vasp_val)

        except (ValueError, TypeError, AttributeError) as exc:
            if verbose:
                print(f"[WARN] skipping {vasp_key}={vasp_val}: {exc}",
                      file=sys.stderr)

    return overrides


def _apply_reverse(value, convert_rule, verbose: bool = False):
    """Apply a reverse_convert rule to an ASE value, returning a VASP tag value."""
    try:
        if convert_rule == "spin_rev":
            s = str(value).strip()
            if s.lower() == "off":
                return 1
            elif s.lower() == "on":
                return 2
            elif s.lower() == "nc":
                return 3
            return value

        elif convert_rule == "xc_rev":
            s = str(value).upper()
            if s == "GGA-PBE":
                return "PE"
            elif s == "GGA-PW91":
                return "91"
            elif s == "LDA-CA":
                return "CA"
            return value

        elif convert_rule == "negate":
            return -float(value)

        elif convert_rule == "algo_rev":
            s = str(value).upper()
            if s == "BAND":
                return "Normal"
            return value

        elif convert_rule == "nelect_rev":
            return float(value)

        elif convert_rule == "encut_rev":
            return float(value) * 2.0

        return value

    except (ValueError, TypeError, AttributeError) as exc:
        if verbose:
            print(f"[WARN] reverse converting {value}: {exc}",
                  file=sys.stderr)
        return value


def reverse(params: dict, mapping: dict, verbose: bool = False) -> dict:
    """Map ASE/OpenMX override keys back to VASP INCAR tags."""
    vasp_result: dict = {}

    for vasp_key, entry in mapping.items():
        omx_key = entry.get("omx_key")
        if omx_key is None:
            continue

        if omx_key not in params:
            continue

        ase_val = params[omx_key]
        reverse_rule = entry.get("reverse_convert")

        if reverse_rule:
            val = _apply_reverse(ase_val, reverse_rule, verbose=verbose)
        else:
            val = ase_val

        vasp_result[vasp_key] = val

    return vasp_result
