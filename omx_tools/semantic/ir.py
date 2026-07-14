"""Versioned semantic IR models (DFT calculation intermediate)."""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from dft_utils import DATA_VERSION

IR_SCHEMA = "dft_semantic_ir"
IR_VERSION = DATA_VERSION  # 0.3.0

CalcClass = Literal["scf", "scf_metal", "relax", "band", "md", "unsupported"]
SpinKind = Literal["off", "collinear", "noncollinear"]
IonicMotion = Literal["fixed", "ions", "cell", "md", "unknown"]


class Smearing(BaseModel):
    method: Optional[str] = None  # gaussian | mp | tetrahedron | fermi | ...
    sigma_eV: Optional[float] = None
    ismear: Optional[int] = None  # raw VASP code when known


class Physics(BaseModel):
    xc: Optional[str] = None
    spin: Optional[SpinKind] = None
    ispin: Optional[int] = None
    cutoff_eV: Optional[float] = None
    smearing: Smearing = Field(default_factory=Smearing)
    ediff_eV: Optional[float] = None
    max_scf: Optional[int] = None
    charge: Optional[float] = None


class Ionic(BaseModel):
    motion: Optional[IonicMotion] = None
    ibrion: Optional[int] = None
    max_steps: Optional[int] = None  # NSW
    force_crit_eV_A: Optional[float] = None  # signed EDIFFG convention
    isif: Optional[int] = None


class ElectronicsAlgo(BaseModel):
    vasp_algo: Optional[str] = None
    omx_eigenvalue_solver: Optional[str] = None


class CodeNative(BaseModel):
    vasp: dict[str, Any] = Field(default_factory=dict)
    openmx: dict[str, Any] = Field(default_factory=dict)


class Provenance(BaseModel):
    source_code: Optional[str] = None
    unmapped: list[str] = Field(default_factory=list)
    dropped: list[dict[str, str]] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class SemanticIR(BaseModel):
    """Canonical intermediate representation for a DFT input."""

    schema_name: str = Field(default=IR_SCHEMA, alias="schema")
    version: str = Field(default=IR_VERSION)
    calc_class: CalcClass = "scf"
    structure_ref: Optional[str] = None
    physics: Physics = Field(default_factory=Physics)
    ionic: Ionic = Field(default_factory=Ionic)
    electronics_algo: ElectronicsAlgo = Field(default_factory=ElectronicsAlgo)
    code_native: CodeNative = Field(default_factory=CodeNative)
    provenance: Provenance = Field(default_factory=Provenance)
    # Adapter: ASE-keyed overrides for OpenMX writers (Phase 2 bridge)
    ase_params: dict[str, Any] = Field(default_factory=dict)
    openmx_template: Optional[str] = None

    model_config = {"populate_by_name": True}

    def to_envelope(self) -> dict[str, Any]:
        """JSON envelope for snapshots / persistence."""
        payload = self.model_dump(by_alias=True, exclude_none=False)
        return {"_version": self.version, "data": payload}

    @classmethod
    def from_envelope(cls, raw: dict[str, Any]) -> "SemanticIR":
        data = raw.get("data", raw)
        return cls.model_validate(data)


# Template ↔ calc_class tables
TEMPLATE_TO_CLASS: dict[str, CalcClass] = {
    "scf_band": "scf",
    "scf_cluster": "scf",
    "scf_band_metal": "scf_metal",
    "geom_opt": "relax",
    "band_dispersion": "band",
}

CLASS_TO_TEMPLATE: dict[str, str] = {
    "scf": "scf_band",
    "scf_metal": "scf_band_metal",
    "relax": "geom_opt",
    "band": "band_dispersion",
    "md": "scf_band",  # no dedicated template yet
    "unsupported": "scf_band",
}


def ismear_to_method(ismear: int | None) -> str | None:
    if ismear is None:
        return None
    table = {
        -5: "tetrahedron",
        -4: "tetrahedron_blochl",
        -1: "fermi",
        0: "gaussian",
        1: "mp",
        2: "mp2",
    }
    return table.get(int(ismear), f"ismear_{ismear}")


def method_to_ismear(method: str | None, fallback: int | None = None) -> int | None:
    if method is None:
        return fallback
    inv = {
        "tetrahedron": -5,
        "tetrahedron_blochl": -4,
        "fermi": -1,
        "gaussian": 0,
        "mp": 1,
        "mp2": 2,
    }
    m = method.lower()
    if m in inv:
        return inv[m]
    if m.startswith("ismear_"):
        try:
            return int(m.split("_", 1)[1])
        except ValueError:
            return fallback
    return fallback


def ispin_to_spin(ispin: int | None) -> SpinKind | None:
    if ispin is None:
        return None
    if int(ispin) == 1:
        return "off"
    if int(ispin) == 2:
        return "collinear"
    if int(ispin) == 3:
        return "noncollinear"
    return "off"


def spin_to_ispin(spin: SpinKind | None, fallback: int | None = None) -> int | None:
    if spin is None:
        return fallback
    return {"off": 1, "collinear": 2, "noncollinear": 3}.get(spin, fallback)


def ibrion_to_motion(ibrion: int | None, nsw: int | None) -> IonicMotion:
    if nsw is not None and int(nsw) == 0:
        return "fixed"
    if ibrion is None:
        return "unknown"
    b = int(ibrion)
    if b in (-1,):
        return "fixed"
    if b == 0:
        return "md"
    if b in (1, 2, 3):
        return "ions"
    return "unknown"


def gga_to_xc(gga: Any) -> str | None:
    if gga is None:
        return None
    s = str(gga).upper()
    return {
        "PE": "PBE",
        "PBE": "PBE",
        "91": "PW91",
        "PW91": "PW91",
        "CA": "LDA",
        "LDA": "LDA",
        "PS": "PBE",  # common alias confusion; keep note in provenance if needed
    }.get(s, s)


def xc_to_gga(xc: str | None) -> str | None:
    if xc is None:
        return None
    s = xc.upper()
    return {
        "PBE": "PE",
        "GGA-PBE": "PE",
        "PW91": "91",
        "GGA-PW91": "91",
        "LDA": "CA",
        "LDA-CA": "CA",
    }.get(s, s)
