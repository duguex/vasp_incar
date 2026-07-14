"""OpenMX → SemanticIR (from ASE params and/or .dat files)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from omx_tools._utils import load_json
from omx_tools.mapping import load_mapping_table, reverse
from omx_tools.parsers.openmx import parse_dat
from omx_tools.semantic.encode_vasp import encode_vasp
from omx_tools.semantic.ir import (
    CLASS_TO_TEMPLATE,
    TEMPLATE_TO_CLASS,
    SemanticIR,
)

_PKG = Path(__file__).resolve().parent.parent
_MAP = _PKG / "schemas" / "vasp_to_ase.json"


def _mapping() -> dict:
    return load_mapping_table(load_json(str(_MAP), "vasp_to_ase.json"))


def infer_template_from_ase(ase_params: dict[str, Any]) -> str:
    """Heuristic template from ASE-keyed OpenMX params."""
    md = str(ase_params.get("md_type", "")).lower()
    if md in {"opt", "diis2", "ef", "rf", "bfgs", "diis"}:
        return "geom_opt"
    # metal-ish: high electronic temperature
    te = ase_params.get("scf_electronictemperature")
    try:
        if te is not None and float(te) >= 1000:
            return "scf_band_metal"
    except (TypeError, ValueError):
        pass
    mix = str(ase_params.get("scf_mixing_type", "")).lower()
    if "kerker" in mix or mix.endswith("k"):
        return "scf_band_metal"
    solver = str(ase_params.get("scf_eigenvaluesolver", "")).lower()
    if solver == "cluster":
        return "scf_cluster"
    # band post-scf: maxiter 1 + restart
    try:
        if int(ase_params.get("scf_maxiter", 100)) <= 1 and ase_params.get("scf_restart"):
            return "band_dispersion"
    except (TypeError, ValueError):
        pass
    return "scf_band"


def encode_omx(
    ase_params: dict[str, Any],
    *,
    template: str | None = None,
    structure_path: str | None = None,
    raw_openmx: dict[str, Any] | None = None,
) -> SemanticIR:
    """Encode OpenMX/ASE params into SemanticIR.

    Strategy: reverse-map to VASP tags (including any ``vasp_*`` preserve
    keys), then ``encode_vasp``. Original ASE + raw OpenMX keywords kept on IR.
    """
    mapping = _mapping()
    vasp = reverse(ase_params, mapping)
    tmpl = template or infer_template_from_ase(ase_params)
    ir = encode_vasp(
        vasp,
        structure_path=structure_path,
        template=tmpl,
        source_code="openmx",
    )
    ir.ase_params = dict(ase_params)
    ir.openmx_template = tmpl
    ir.calc_class = TEMPLATE_TO_CLASS.get(tmpl, ir.calc_class)  # type: ignore[assignment]
    ir.provenance.source_code = "openmx"
    if raw_openmx:
        ir.code_native.openmx = dict(raw_openmx)
        # keywords not reverse-mapped stay as unmapped openmx natives note
        ir.provenance.notes.append(
            f"raw OpenMX keywords stored: {len(raw_openmx)}"
        )
    return ir


def encode_omx_dat(
    path: str | Path,
    *,
    template: str | None = None,
    structure_path: str | None = None,
) -> SemanticIR:
    """Parse an OpenMX ``.dat`` file and encode to SemanticIR.

    Combines schema-based ASE extraction (``parse_dat``) with raw scalar
    keyword extraction for ``code_native.openmx``.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f".dat not found: {path}")

    ase_params = parse_dat(str(path))
    raw: dict[str, Any] = {}
    try:
        from omx_tools.examples_corpus import extract_openmx_scalars

        raw = extract_openmx_scalars(path)
    except Exception:
        raw = {}

    # path-based intent hint if template not given
    tmpl = template
    if tmpl is None:
        from omx_tools.examples_corpus import infer_intent

        intent = infer_intent(path.name, raw)
        # map corpus intent → template
        tmpl = {
            "geom_opt": "geom_opt",
            "scf": "scf_band",
            "band": "band_dispersion",
            "negf": "scf_band",
            "ml": "scf_band",
            "force": "scf_band",
        }.get(intent)
        if tmpl is None:
            tmpl = infer_template_from_ase(ase_params)

    return encode_omx(
        ase_params,
        template=tmpl,
        structure_path=structure_path or str(path),
        raw_openmx=raw,
    )
