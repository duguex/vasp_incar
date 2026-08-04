"""Bidirectional VASP ↔ ASE/OpenMX parameter mapping with round-trip support.

Phase 1 semantic contract (see docs/superpowers/specs/2026-07-14-semantic-roundtrip-design.md):
- Must-preserve tags survive forward→reverse (including NSW=0, ISMEAR, SIGMA).
- OpenMX engine clamps (e.g. md_maxiter≥1) must not destroy reverse fidelity.
- Unmapped / declared-drop tags are reportable via ``return_report=True``.
"""

from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

from dft_utils.ir import gga_to_xc, ispin_to_spin, spin_to_ispin, xc_to_gga


def _load_mapping_data(mapping: dict) -> dict:
    """Accept raw rule dict or an explicit version envelope."""
    if (
        isinstance(mapping, dict)
        and "_version" in mapping
        and "data" in mapping
        and isinstance(mapping["data"], dict)
    ):
        return mapping["data"]
    return mapping


def load_mapping_table(mapping: dict) -> dict:
    """Public unwrap for JSON envelope or bare rule dict."""
    return _load_mapping_data(mapping)


_MAPPING_DEFAULT_PATH = Path(__file__).resolve().parent.parent / "schemas" / "vasp_to_ase.json"


@lru_cache(maxsize=1)
def default_mapping() -> dict:
    """The single, cached VASP→ASE/OpenMX keyword table.

    ``load_json`` (via ``dft_utils.version.load_data``) already strips the
    ``_version``/``data`` envelope, so the result is ready to pass to
    :func:`forward` / :func:`reverse` without a second unwrap.
    """
    from omx_tools._utils import load_json
    return load_json(str(_MAPPING_DEFAULT_PATH), "vasp_to_ase.json")



def for_openmx_writer(overrides: dict) -> dict:
    """Drop VASP preserve-only keys (``vasp_*``) before ASE OpenMX write."""
    return {
        k: v for k, v in overrides.items()
        if not str(k).startswith("vasp_")
    }



def forward(
    params: dict,
    mapping: dict,
    verbose: bool = False,
    return_report: bool = False,
) -> dict | tuple[dict, dict]:
    """Map VASP INCAR parameters to ASE/OpenMX override keys.

    Parameters
    ----------
    return_report:
        If True, return ``(overrides, report)`` where report has
        ``unmapped`` (list[str]) and ``dropped`` (list[{tag, reason}]).
    """
    mapping = _load_mapping_data(mapping)
    overrides: dict[str, Any] = {}
    unmapped: list[str] = []
    dropped: list[dict[str, str]] = []

    for vasp_key, vasp_val in params.items():
        key = str(vasp_key)
        if key not in mapping:
            unmapped.append(key)
            continue

        entry = mapping[key]
        omx_key = entry.get("omx_key")
        if omx_key is None:
            dropped.append({
                "tag": key,
                "reason": entry.get("note") or "declared_drop",
            })
            continue

        convert = entry.get("convert")
        preserve_key = entry.get("preserve_key")
        try:
            if preserve_key:
                # Exact VASP value for reverse (even if omx_key is clamped/lossy)
                overrides[preserve_key] = vasp_val

            if convert == "passthrough":
                overrides[omx_key] = vasp_val

            elif convert == "encut":
                overrides[omx_key] = float(vasp_val) / 2.0

            elif convert == "nsw":
                v = int(vasp_val)
                # OpenMX writer needs ≥1; exact NSW is in preserve_key vasp_nsw
                overrides[omx_key] = max(v, 1)
                if not preserve_key:
                    overrides["vasp_nsw"] = v
                if verbose and v == 0:
                    print(
                        "[INFO] NSW=0 preserved as vasp_nsw; "
                        "md_maxiter=1 for OpenMX writer only",
                        file=sys.stderr,
                    )

            elif convert == "bool":
                overrides[omx_key] = bool(vasp_val)

            elif convert == "spin":
                # VASP ispin → neutral SpinKind (in dft_utils.ir) → OpenMX literal
                token = ispin_to_spin(int(vasp_val))
                overrides[omx_key] = {
                    "off": "Off",
                    "collinear": "On",
                    "noncollinear": "NC",
                }.get(token, "Off")

            elif convert == "xc":
                # VASP GGA code → neutral xc token (in dft_utils.ir) → OpenMX literal
                token = gga_to_xc(vasp_val)
                overrides[omx_key] = {
                    "PBE": "GGA-PBE",
                    "PW91": "GGA-PW91",
                    "LDA": "LDA-CA",
                }.get(token, vasp_val)

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
                if not preserve_key:
                    overrides["vasp_algo"] = vasp_val

            elif convert == "nelect":
                overrides[omx_key] = float(vasp_val)

            elif convert is None:
                # omx_key set but no convert — treat as passthrough
                overrides[omx_key] = vasp_val

        except (ValueError, TypeError, AttributeError) as exc:
            if verbose:
                print(
                    f"[WARN] skipping {vasp_key}={vasp_val}: {exc}",
                    file=sys.stderr,
                )

    report = {"unmapped": unmapped, "dropped": dropped}
    if return_report:
        return overrides, report
    return overrides


def _apply_reverse(value, convert_rule, verbose: bool = False):
    """Apply a reverse_convert rule to an ASE value, returning a VASP tag value."""
    try:
        if convert_rule == "spin_rev":
            s = str(value).strip()
            token = {"off": "off", "on": "collinear", "nc": "noncollinear"}.get(
                s.lower()
            )
            if token is None:
                return value
            return spin_to_ispin(token, fallback=value)

        if convert_rule == "xc_rev":
            s = str(value).upper()
            result = xc_to_gga(s)
            # xc_to_gga returns `s` unchanged for unknown -> keep original
            return value if result == s else result

        if convert_rule == "negate":
            return -float(value)

        if convert_rule == "algo_rev":
            # Prefer exact preserve via reverse() before calling this
            s = str(value).upper()
            if s == "BAND":
                return "Normal"
            return value

        if convert_rule == "nelect_rev":
            return float(value)

        if convert_rule == "encut_rev":
            return float(value) * 2.0

        if convert_rule == "nsw_rev":
            return int(value)

        return value

    except (ValueError, TypeError, AttributeError) as exc:
        if verbose:
            print(f"[WARN] reverse converting {value}: {exc}", file=sys.stderr)
        return value


def reverse(params: dict, mapping: dict, verbose: bool = False) -> dict:
    """Map ASE/OpenMX override keys back to VASP INCAR tags.

    Prefers ``preserve_key`` values when present so engine clamps do not
    destroy VASP round-trip fidelity.
    """
    mapping = _load_mapping_data(mapping)
    vasp_result: dict[str, Any] = {}

    for vasp_key, entry in mapping.items():
        omx_key = entry.get("omx_key")
        if omx_key is None:
            continue

        preserve_key = entry.get("preserve_key")
        if preserve_key and preserve_key in params:
            vasp_result[vasp_key] = params[preserve_key]
            continue

        # Preserve-style passthrough keys equal omx_key (vasp_ismear, …)
        if omx_key in params and str(omx_key).startswith("vasp_"):
            vasp_result[vasp_key] = params[omx_key]
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
