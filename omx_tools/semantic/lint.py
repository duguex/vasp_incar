"""Physics / consistency lint for VASP INCAR and OpenMX inputs.

Not a full convergence expert — cheap rule checks that emit
``{severity, code, message, suggestion, tags}`` findings.

Integrates with Semantic IR when useful (calc_class hints).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Severity = Literal["error", "warning", "info"]


@dataclass
class LintFinding:
    severity: Severity
    code: str
    message: str
    suggestion: str
    tags: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LintReport:
    ok: bool
    n_error: int
    n_warning: int
    n_info: int
    findings: list[LintFinding] = field(default_factory=list)
    calc_class_hint: str | None = None
    path: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "n_error": self.n_error,
            "n_warning": self.n_warning,
            "n_info": self.n_info,
            "calc_class_hint": self.calc_class_hint,
            "path": self.path,
            "findings": [f.as_dict() for f in self.findings],
        }


def _f(incar: dict[str, Any], key: str) -> Any | None:
    if key in incar:
        return incar[key]
    ku = key.upper()
    for k, v in incar.items():
        if str(k).upper() == ku:
            return v
    return None


def _as_int(v: Any) -> int | None:
    if v is None:
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _as_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def lint_vasp_incar(
    incar: dict[str, Any],
    *,
    path: str | None = None,
    use_ir_hint: bool = True,
) -> LintReport:
    """Lint a VASP INCAR parameter dict."""
    findings: list[LintFinding] = []
    src = {str(k).upper(): v for k, v in incar.items()}

    calc_class_hint = None
    if use_ir_hint:
        try:
            from omx_tools.semantic.encode_vasp import encode_vasp

            ir = encode_vasp(src)
            calc_class_hint = ir.calc_class
        except Exception:
            calc_class_hint = None

    encut = _as_float(_f(src, "ENCUT"))
    ismear = _as_int(_f(src, "ISMEAR"))
    sigma = _as_float(_f(src, "SIGMA"))
    nsw = _as_int(_f(src, "NSW"))
    ibrion = _as_int(_f(src, "IBRION"))
    ispin = _as_int(_f(src, "ISPIN"))
    ediff = _as_float(_f(src, "EDIFF"))
    ediffg = _as_float(_f(src, "EDIFFG"))
    isif = _as_int(_f(src, "ISIF"))
    nelm = _as_int(_f(src, "NELM"))
    icharg = _as_int(_f(src, "ICHARG"))
    lsorbit = _f(src, "LSORBIT")
    algo = _f(src, "ALGO")

    # --- ENCUT ---
    if encut is None:
        findings.append(LintFinding(
            "warning", "encut.missing",
            "ENCUT is not set; VASP will use max ENMAX from POTCAR.",
            "Set ENCUT explicitly (often 1.3× max ENMAX). "
            "Query: vasp-query tag ENCUT",
            ["ENCUT"],
        ))
    elif encut < 150:
        findings.append(LintFinding(
            "error", "encut.too_low",
            f"ENCUT={encut} eV is unusually low for plane-wave DFT.",
            "Raise ENCUT (typical metals/semiconductors ~300–520 eV; "
            "check POTCAR ENMAX). vasp-query tag ENCUT",
            ["ENCUT"],
        ))
    elif encut < 250:
        findings.append(LintFinding(
            "warning", "encut.low",
            f"ENCUT={encut} eV may be low depending on elements (e.g. O, F, 3d).",
            "Compare with ENMAX in POTCAR; consider ≥1.3× ENMAX. "
            "vasp-query tag ENCUT",
            ["ENCUT"],
        ))

    # --- Ionic / electronic consistency ---
    if nsw is not None and ibrion is not None:
        if nsw == 0 and ibrion not in (-1, None) and ibrion != -1:
            # ibrion can be -1 or unset for static; 0 with NSW=0 is also odd
            if ibrion >= 0:
                findings.append(LintFinding(
                    "warning", "ionic.nsw0_ibrion",
                    f"NSW=0 but IBRION={ibrion}: ionic algorithm set for a static run.",
                    "For single-point SCF use IBRION=-1 (or omit) with NSW=0. "
                    "vasp-query tag IBRION",
                    ["NSW", "IBRION"],
                ))
        if nsw is not None and nsw > 0 and ibrion in (-1,):
            findings.append(LintFinding(
                "error", "ionic.nsw_positive_ibrion_fixed",
                f"NSW={nsw} but IBRION=-1 (no ionic updates).",
                "Set IBRION=2 (CG) or 1 for relaxation, or NSW=0 for static. "
                "vasp-query tag NSW",
                ["NSW", "IBRION"],
            ))
        if nsw is not None and nsw > 0 and ibrion == 0:
            findings.append(LintFinding(
                "info", "ionic.md_mode",
                f"NSW={nsw}, IBRION=0 suggests MD.",
                "Confirm MDALGO/POTIM/TEBEG for AIMD; template: vasp-gen -t md",
                ["NSW", "IBRION"],
            ))

    if nsw is not None and nsw > 0 and ediffg is None:
        findings.append(LintFinding(
            "warning", "ionic.ediffg_missing",
            "Relaxation/MD with NSW>0 but EDIFFG unset.",
            "Set EDIFFG (e.g. -0.02 for forces eV/Å). vasp-query tag EDIFFG",
            ["NSW", "EDIFFG"],
        ))

    if isif is not None and nsw is not None and nsw == 0 and isif not in (None, 2):
        # weak info only
        findings.append(LintFinding(
            "info", "ionic.isif_static",
            f"ISIF={isif} with NSW=0 does not relax cell/ions.",
            "ISIF matters when NSW>0 / IBRION allows motion. vasp-query tag ISIF",
            ["ISIF", "NSW"],
        ))

    # --- Smearing ---
    if ismear is not None and ismear >= 1:
        if sigma is not None and sigma < 0.1:
            findings.append(LintFinding(
                "warning", "smearing.metal_sigma_low",
                f"ISMEAR={ismear} (MP) with SIGMA={sigma} eV may be tight for metals.",
                "For metals try SIGMA~0.15–0.2 eV; check entropy T*S. "
                "vasp-query tag ISMEAR; vasp-gen -t scf_metal",
                ["ISMEAR", "SIGMA"],
            ))
        if calc_class_hint == "scf" and ismear >= 1:
            findings.append(LintFinding(
                "info", "smearing.metal_like",
                "Methfessel-Paxton smearing usually indicates metallic occupation.",
                "Prefer scf_metal template / denser k-mesh. "
                "omx side: scf_band_metal if converting.",
                ["ISMEAR"],
            ))

    if ismear == 0 and sigma is not None and sigma > 0.2:
        findings.append(LintFinding(
            "warning", "smearing.gaussian_sigma_high",
            f"ISMEAR=0 (Gaussian) with SIGMA={sigma} eV is large for insulators.",
            "For semiconductors/insulators SIGMA~0.05 eV is common; "
            "for metals prefer ISMEAR=1/2. vasp-query tag SIGMA",
            ["ISMEAR", "SIGMA"],
        ))

    if ismear == -5 and sigma is not None and sigma != 0:
        findings.append(LintFinding(
            "info", "smearing.tetrahedron_sigma",
            "ISMEAR=-5 (tetrahedron): SIGMA is ignored for occupations.",
            "OK for DOS/insulators with dense k-mesh; not for metals during relax.",
            ["ISMEAR", "SIGMA"],
        ))

    # --- Spin ---
    if ispin == 2:
        findings.append(LintFinding(
            "info", "spin.collinear",
            "ISPIN=2: collinear spin polarized.",
            "Consider MAGMOM initialization for TM oxides/defects. "
            "vasp-query tag MAGMOM",
            ["ISPIN"],
        ))
    if lsorbit is not None:
        ls = str(lsorbit).upper()
        if ls in (".TRUE.", "TRUE", "T", "1"):
            if ispin != 2 and ispin is not None:
                findings.append(LintFinding(
                    "warning", "spin.soc_ispin",
                    "LSORBIT=.TRUE. typically requires ISPIN=2 and non-collinear setup caveats.",
                    "Check VASP wiki SOC recipe (LNONCOLLINEAR/LSORBIT). "
                    "vasp-query tag LSORBIT",
                    ["LSORBIT", "ISPIN"],
                ))

    # --- Electronic convergence ---
    if ediff is not None and ediff > 1e-4:
        findings.append(LintFinding(
            "warning", "elec.ediff_loose",
            f"EDIFF={ediff} is loose for production energies/forces.",
            "Common production EDIFF is 1e-5–1e-6. vasp-query tag EDIFF",
            ["EDIFF"],
        ))
    if nelm is not None and nelm < 60:
        findings.append(LintFinding(
            "info", "elec.nelm_low",
            f"NELM={nelm} may be low if SCF struggles.",
            "Increase NELM or improve mixing (AMIX/BMIX) if not converging.",
            ["NELM"],
        ))

    # --- Band / ICHARG ---
    if icharg == 11 and (nsw is None or nsw == 0):
        findings.append(LintFinding(
            "info", "band.icharg11",
            "ICHARG=11: non-SCF from CHGCAR (band/DOS style).",
            "Ensure prior SCF CHGCAR exists; use line-mode KPOINTS for bands. "
            "vasp-gen -t band; docs/vaspkit-checklist.md",
            ["ICHARG"],
        ))
    if icharg == 11 and nsw is not None and nsw > 0:
        findings.append(LintFinding(
            "error", "band.icharg11_with_nsw",
            "ICHARG=11 with NSW>0 is an unusual combination.",
            "Non-SCF band runs should use NSW=0. Separate SCF and band steps.",
            ["ICHARG", "NSW"],
        ))

    # --- ALGO ---
    if algo is not None:
        a = str(algo).upper().rstrip(".")
        if a in ("A", "ALL") and ismear is not None and ismear >= 0:
            findings.append(LintFinding(
                "info", "algo.all",
                f"ALGO={algo} (All) can be robust but slower; watch for metallic cases.",
                "For metals ALGO=Normal/Fast is common. vasp-query tag ALGO",
                ["ALGO"],
            ))

    # --- Empty / minimal ---
    if not src:
        findings.append(LintFinding(
            "error", "incar.empty",
            "No INCAR tags parsed.",
            "Check file format (KEY = value). parse with vasp-query or pymatgen.",
            [],
        ))

    n_err = sum(1 for f in findings if f.severity == "error")
    n_warn = sum(1 for f in findings if f.severity == "warning")
    n_info = sum(1 for f in findings if f.severity == "info")
    return LintReport(
        ok=(n_err == 0),
        n_error=n_err,
        n_warning=n_warn,
        n_info=n_info,
        findings=findings,
        calc_class_hint=calc_class_hint,
        path=path,
    )


def lint_openmx_params(
    params: dict[str, Any],
    *,
    raw: dict[str, Any] | None = None,
    path: str | None = None,
) -> LintReport:
    """Lint OpenMX ASE-keyed and/or raw dotted keywords."""
    findings: list[LintFinding] = []
    ase = {str(k).lower(): v for k, v in params.items()}
    raw = raw or {}
    raw_l = {str(k): v for k, v in raw.items()}

    def raw_get(*names: str) -> Any:
        for n in names:
            if n in raw_l:
                return raw_l[n]
            for k, v in raw_l.items():
                if k.lower() == n.lower():
                    return v
        return None

    cutoff = _as_float(ase.get("scf_energycutoff") or raw_get("scf.energycutoff"))
    # OpenMX cutoff often in Ry
    if cutoff is not None and cutoff < 100:
        findings.append(LintFinding(
            "warning", "omx.cutoff_low",
            f"scf.energycutoff={cutoff} Ry looks low for many solids.",
            "Typical examples use ~150–300 Ry; see omx-db example / section 14. "
            "omx-db rag 'energy cutoff'",
            ["scf.energycutoff"],
        ))

    maxiter = _as_int(ase.get("scf_maxiter") or raw_get("scf.maxIter", "scf.maxiter"))
    if maxiter is not None and maxiter < 30:
        findings.append(LintFinding(
            "info", "omx.maxiter_low",
            f"scf.maxIter={maxiter} may be low if SCF oscillates.",
            "Increase scf.maxIter or tune Mixing (Rmm-Diisk/Kerker for metals). "
            "omx-db section 16",
            ["scf.maxIter"],
        ))

    te = _as_float(
        ase.get("scf_electronictemperature")
        or raw_get("scf.ElectronicTemperature")
    )
    mix = str(
        ase.get("scf_mixing_type") or raw_get("scf.Mixing.Type") or ""
    ).lower()
    if te is not None and te < 500 and ("kerker" in mix or mix.endswith("k")):
        findings.append(LintFinding(
            "info", "omx.metal_mix_low_te",
            "Kerker-like mixing with low ElectronicTemperature.",
            "Metals often use higher scf.ElectronicTemperature; "
            "template scf_band_metal. omx-db rag 'metallic SCF'",
            ["scf.ElectronicTemperature", "scf.Mixing.Type"],
        ))

    md = str(ase.get("md_type") or raw_get("MD.Type") or "").lower()
    md_max = _as_int(ase.get("md_maxiter") or raw_get("MD.maxIter"))
    if md in {"opt", "diis", "ef", "rf", "bfgs"} and md_max == 1:
        findings.append(LintFinding(
            "warning", "omx.opt_maxiter_one",
            "Geometry optimization MD.Type but MD.maxIter=1.",
            "Raise MD.maxIter for real relaxations. omx-gen -t geom_opt",
            ["MD.Type", "MD.maxIter"],
        ))

    if not ase and not raw:
        findings.append(LintFinding(
            "error", "omx.empty",
            "No OpenMX parameters parsed.",
            "Check .dat path; try omx-db example or parse_dat.",
            [],
        ))

    n_err = sum(1 for f in findings if f.severity == "error")
    n_warn = sum(1 for f in findings if f.severity == "warning")
    n_info = sum(1 for f in findings if f.severity == "info")
    return LintReport(
        ok=(n_err == 0),
        n_error=n_err,
        n_warning=n_warn,
        n_info=n_info,
        findings=findings,
        calc_class_hint=None,
        path=path,
    )


def lint_openmx_dat(path: str) -> LintReport:
    """Lint an OpenMX .dat file on disk."""
    from pathlib import Path
    from omx_tools.parsers.openmx import parse_dat
    from omx_tools.examples_corpus import extract_openmx_scalars

    p = Path(path)
    ase = parse_dat(str(p)) if p.is_file() else {}
    raw = extract_openmx_scalars(p) if p.is_file() else {}
    return lint_openmx_params(ase, raw=raw, path=str(p))
