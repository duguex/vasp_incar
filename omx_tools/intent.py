"""Canonical intermediate representation for DFT calculation intents."""

from dataclasses import dataclass, field


@dataclass
class CalculationIntent:
    """Canonical representation of a DFT calculation intent.

    template   — template name (scf_band, geom_opt, scf_band_metal, band_dispersion)
    params     — ASE-keyed parameter dict (scf_energycutoff, scf_spinpolarization, ...)
    structure  — path to structure file (POSCAR/CIF/XYZ)
    """
    template: str
    params: dict = field(default_factory=dict)
    structure_path: str = ""
