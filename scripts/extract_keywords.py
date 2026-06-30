#!/usr/bin/env python3
"""
Extract structured keyword metadata from three sources:

Source 1 — ASE parameters.py (typed keyword lists + unit info)
Source 2 — MinerU-parsed v3.9 manual HTML tables (defaults + valid values)
Source 3 — v4.0 HTML manual §8.2 (descriptions)

Plus openmx.db for section mapping.
"""

import json
import os
import re
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCHEMAS_DIR = PROJECT_ROOT / "omx_tools" / "schemas"

# ── Helpers ──────────────────────────────────────────────────────────

ASE_KEY_RENAME = {
    # These ASE snake_case keys don't cleanly round-trip from OpenMX dot-case
    "scf_ngrid": "scf.Ngrid",
    "scf_kgrid": "scf.Kgrid",
    "dos_kgrid": "Dos.Kgrid",
    "scf_electric_field": "scf.Electric.Field",
    "scf_fixed_grid": "scf.fixed.grid",
    "level_of_stdout": "level.of.stdout",
    "level_of_fileout": "level.of.fileout",
    "species_number": "Species.Number",
    "atoms_number": "Atoms.Number",
    "scf_maxiter": "scf.maxIter",
    "scf_mixing_history": "scf.Mixing.History",
    "scf_mixing_startpulay": "scf.Mixing.StartPulay",
    "scf_mixing_everypulay": "scf.Mixing.EveryPulay",
    "onedfft_numgridk": "1DFFT.NumGridK",
    "onedfft_numgridr": "1DFFT.NumGridR",
    "orbitalopt_scf_maxiter": "orbitalOpt.scf.maxIter",
    "orbitalopt_opt_maxiter": "orbitalOpt.Opt.maxIter",
    "orbitalopt_opt_method": "orbitalOpt.Opt.Method",
    "orbitalopt_historypulay": "orbitalOpt.HistoryPulay",
    "num_cntorb_atoms": "Num.CntOrb.Atoms",
    "ordern_krylovh_order": "orderN.KrylovH.order",
    "ordern_krylovs_order": "orderN.KrylovS.order",
    "md_maxiter": "MD.maxIter",
    "md_opt_diis_history": "MD.Opt.DIIS.History",
    "md_opt_startdiis": "MD.Opt.StartDIIS",
    "band_nkpath": "Band.Nkpath",
    "num_homos": "num.HOMOs",
    "num_lumos": "num.LUMOs",
    "mo_nkpoint": "MO.Nkpoint",
    "md_current_iter": "MD.Current.Iter",
    "scf_constraint_nc_spin_v": "scf.Constraint.NC.Spin.v",
    "scf_electronictemperature": "scf.ElectronicTemperature",
    "scf_energycutoff": "scf.energycutoff",
    "scf_init_mixing_weight": "scf.Init.Mixing.Weight",
    "scf_min_mixing_weight": "scf.Min.Mixing.Weight",
    "scf_max_mixing_weight": "scf.Max.Mixing.Weight",
    "scf_kerker_factor": "scf.Kerker.factor",
    "scf_criterion": "scf.criterion",
    "scf_system_charge": "scf.system.charge",
    "onedfft_energycutoff": "1DFFT.EnergyCutoff",
    "orbitalopt_sd_step": "orbitalOpt.SD.step",
    "orbitalopt_criterion": "orbitalOpt.criterion",
    "ordern_hoppingranges": "orderN.HoppingRanges",
    "md_timestep": "MD.TimeStep",
    "md_opt_criterion": "MD.Opt.criterion",
    "nh_mass_heatbath": "NH.Mass.HeatBath",
    "scf_nc_mag_field_spin": "scf.NC.Mag.Field.Spin",
    "scf_nc_mag_field_orbital": "scf.NC.Mag.Field.Orbital",
    "system_currentdirectory": "System.CurrentDirectory",
    "system_name": "System.Name",
    "data_path": "DATA.PATH",
    "atoms_speciesandcoordinates_unit": "Atoms.SpeciesAndCoordinates.Unit",
    "atoms_unitvectors_unit": "Atoms.UnitVectors.Unit",
    "scf_xctype": "scf.XcType",
    "scf_spinpolarization": "scf.SpinPolarization",
    "scf_hubbard_occupation": "scf.Hubbard.Occupation",
    "scf_eigenvaluesolver": "scf.EigenvalueSolver",
    "scf_mixing_type": "scf.Mixing.Type",
    "orbitalopt_method": "orbitalOpt.Method",
    "orbitalopt_startpulay": "orbitalOpt.StartPulay",
    "md_type": "MD.Type",
    "wannier_initial_projectors_unit": "Wannier.Initial.Projectors.Unit",
    "scf_partialcorecorrection": "scf.partialCoreCorrection",
    "scf_hubbard_u": "scf.Hubbard.U",
    "scf_constraint_nc_spin": "scf.Constraint.NC.Spin",
    "scf_proexpn_vna": "scf.ProExpn.VNA",
    "scf_spinorbit_coupling": "scf.SpinOrbit.Coupling",
    "cntorb_fileout": "CntOrb.fileout",
    "ordern_exact_inverse_s": "orderN.Exact.Inverse.S",
    "ordern_recalc_buffer": "orderN.Recalc.Buffer",
    "ordern_expand_core": "orderN.Expand.Core",
    "band_dispersion": "Band.Dispersion",
    "scf_restart": "scf.restart",
    "mo_fileout": "MO.fileout",
    "dos_fileout": "Dos.fileout",
    "hs_fileout": "HS.fileout",
    "voronoi_charge": "Voronoi.charge",
    "scf_nc_zeeman_spin": "scf.NC.Zeeman.Spin",
    "scf_stress_tensor": "scf.stress.tensor",
    "energy_decomposition": "Energy.Decomposition",
    "dos_erange": "Dos.Erange",
    "definition_of_atomic_species": "Definition.of.Atomic.Species",
    "atoms_speciesandcoordinates": "Atoms.SpeciesAndCoordinates",
    "atoms_unitvectors": "Atoms.UnitVectors",
    "hubbard_u_values": "Hubbard.U.values",
    "atoms_cont_orbitals": "Atoms.Cont.Orbitals",
    "md_fixed_xyz": "MD.Fixed.XYZ",
    "md_tempcontrol": "MD.TempControl",
    "md_init_velocity": "MD.Init.Velocity",
    "band_kpath_unitcell": "Band.KPath.UnitCell",
    "band_kpath": "Band.kpath",
    "mo_kpoint": "MO.kpoint",
    "wannier_initial_projectors": "Wannier.Initial.Projectors",
}

def ase_key_to_openmx(ase_key):
    """Convert ASE snake_case to OpenMX dot-case."""
    return ASE_KEY_RENAME.get(ase_key, ase_key.replace("_", "."))


# ── Source 1: ASE parameters.py ──────────────────────────────────────

def parse_ase_parameters(py_path):
    """Import parameter key lists from ASE's parameters.py via exec."""
    ns = {}
    with open(py_path) as f:
        code = f.read()
    exec(code, ns)

    type_map = {}

    # Map of OpenMX key -> type
    for keylist_name, type_name in [
        ("integer_keys", "integer"),
        ("float_keys", "float"),
        ("string_keys", "string"),
        ("bool_keys", "bool"),
        ("tuple_integer_keys", "tuple_integer"),
        ("tuple_float_keys", "tuple_float"),
        ("matrix_keys", "matrix"),
        ("list_float_keys", "list_float"),
    ]:
        for kw in ns.get(keylist_name, []):
            # ASE key list already has OpenMX dot-form
            type_map[kw] = type_name

    # Unit info
    unit_map = dict(ns.get("unit_dat_keywords", {}))

    # The default_dictionary from ASE - not used directly but we capture the
    # omx_parameter_defaults for the ASE-key -> OpenMX-key mapping
    return type_map, unit_map


# ── Source 2: MinerU tables ──────────────────────────────────────────

def parse_mineru_tables(md_path):
    """Extract keyword -> (value, comment) from HTML table rows in paper.md."""
    entries = {}
    with open(md_path, encoding="utf-8") as f:
        content = f.read()

    # Pattern: <tr><td>KEYWORD</td><td>VALUE</td><td>#COMMENT</td></tr>
    pattern = re.compile(
        r"<tr><td>([^<]+)</td><td>([^<]*)</td><td>#\s*(.*?)</td></tr>"
    )
    for m in pattern.finditer(content):
        keyword = m.group(1).strip()
        example_value = m.group(2).strip()
        comment = m.group(3).strip()

        # Only accept keyword-like names (contain dots)
        if "." not in keyword:
            continue

        default = None
        valid_values = None

        # Extract default from comment
        default_m = re.search(r"default\s*=\s*([\d\.\+\-eE]+)", comment, re.I)
        if default_m:
            raw = default_m.group(1)
            try:
                if "." in raw or "e" in raw.lower():
                    default = float(raw)
                else:
                    default = int(raw)
            except ValueError:
                default = raw

        # Extract valid_values from comment (pipe-separated or listed)
        # Common pattern: "Val1|Val2|Val3" or "Val1|Val2/Val3|Val4"
        if "|" in comment and "default" not in comment.split("|")[0]:
            # Pipe separators define valid options
            parts = [p.strip() for p in comment.split("|")]
            # Remove the default= part from the last element
            cleaned = []
            for p in parts:
                p = re.sub(r"#.*$", "", p).strip()
                if p and "default" not in p.lower():
                    cleaned.append(p)
            if cleaned:
                valid_values = cleaned

        # Also parse from specific patterns
        if not valid_values and "|" in comment:
            parts = [p.strip() for p in re.split(r"[|/]", comment)]
            cleaned = []
            for p in parts:
                p = re.sub(r"default.*$", "", p, flags=re.I).strip()
                p = re.sub(r"#.*$", "", p).strip()
                if p and "default" not in p.lower():
                    cleaned.append(p)
            if cleaned:
                valid_values = cleaned

        entries[keyword] = {
            "example_value": example_value,
            "default": default,
            "valid_values": valid_values,
        }

    return entries


# ── Source 3: v4.0 HTML descriptions ─────────────────────────────────

def parse_html_descriptions(html_path):
    """Extract keyword -> description from v4.0 HTML §8.2."""
    descriptions = {}
    with open(html_path, encoding="utf-8") as f:
        content = f.read()

    # Find all keyword headings
    kw_pattern = re.compile(
        r'<span class="ltx_text ltx_font_bold openmx_kwhead openmx_kwgap">([^<]+)</span>'
    )
    matches = list(kw_pattern.finditer(content))

    for i, m in enumerate(matches):
        keyword = m.group(1).strip()

        # Skip non-keyword entries
        if keyword.lower() in ("a", "b", "c", "on", "off"):
            continue

        # Get text between this heading and the next one
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        section_text = content[start:end]

        # Find the first <p> or following text that has meaningful description
        # Remove HTML tags
        text = re.sub(r"<[^>]+>", " ", section_text)
        text = re.sub(r"\s+", " ", text).strip()

        # Extract first sentence
        # Look for sentence-like patterns
        sentences = re.split(r'(?<=[.!?])\s+', text)
        if sentences:
            desc = sentences[0].strip()
            # Clean up
            desc = desc.replace("\n", " ")
            desc = re.sub(r"\s+", " ", desc).strip()
            if len(desc) > 10:  # Must be meaningful
                descriptions[keyword] = desc

    return descriptions


# ── Section info from openmx.db ──────────────────────────────────────

def get_section_info(db_path):
    """Get keyword -> section mapping from openmx.db index_entries."""
    kw_to_sections = {}
    conn = sqlite3.connect(str(db_path))
    for row in conn.execute(
        "SELECT keyword, file_path, section_ref FROM index_entries"
    ):
        kw = row[0]
        sec = row[2]
        if kw not in kw_to_sections:
            kw_to_sections[kw] = []
        if sec not in kw_to_sections[kw]:
            kw_to_sections[kw].append(sec)
    conn.close()
    return kw_to_sections


# ── Build schema ─────────────────────────────────────────────────────

def build_schema(
    ase_types, ase_units, mineru_entries, html_descriptions, section_map
):
    """Merge all sources into unified keyword schema."""
    schema = {}

    # All keyword names from all sources
    all_keywords = set()
    all_keywords.update(ase_types.keys())
    all_keywords.update(mineru_entries.keys())
    all_keywords.update(html_descriptions.keys())
    all_keywords.update(section_map.keys())

    for kw in sorted(all_keywords):
        entry = {
            "ase_key": None,
            "type": None,
            "default": None,
            "valid_values": None,
            "description": None,
            "section": None,
            "unit": None,
            "source": [],
        }

        # Determine ASE key
        # Reverse lookup: find which ase_key maps to this OpenMX keyword
        for ase_k, omx_k in ASE_KEY_RENAME.items():
            if omx_k == kw:
                entry["ase_key"] = ase_k
                break
        if entry["ase_key"] is None:
            # Try direct conversion
            candidate = kw.replace(".", "_").lower()
            # Remove some irregular conversions
            entry["ase_key"] = candidate

        # Source 1: ASE type + unit
        if kw in ase_types:
            entry["type"] = ase_types[kw]
            entry["source"].append("ase")
        if kw in ase_units:
            entry["unit"] = ase_units[kw]
            # Don't re-add source ase, already done

        # Source 2: MinerU defaults/valid
        if kw in mineru_entries:
            mineru = mineru_entries[kw]
            if entry["default"] is None and mineru["default"] is not None:
                entry["default"] = mineru["default"]
            if entry["valid_values"] is None and mineru["valid_values"]:
                entry["valid_values"] = mineru["valid_values"]
            entry["source"].append("mineru")

        # Source 3: HTML descriptions
        if kw in html_descriptions:
            desc = html_descriptions[kw]
            if entry["description"] is None or len(desc) > len(
                entry["description"] or ""
            ):
                entry["description"] = desc
            entry["source"].append("html")

        # Section from DB
        if kw in section_map:
            entry["section"] = "; ".join(section_map[kw])

        # Deduplicate sources
        entry["source"] = list(dict.fromkeys(entry["source"]))
        if not entry["source"]:
            entry["source"] = ["manual_only"]

        schema[kw] = entry

    return schema


# ── Main ─────────────────────────────────────────────────────────────

def main():
    ase_param_path = os.path.expanduser(
        "~/.conda/envs/dgkan_rocm_3.11/lib/python3.11/"
        "site-packages/ase/calculators/openmx/parameters.py"
    )
    mineru_path = PROJECT_ROOT / "parsed" / "openmx3_9_manual" / "paper.md"
    html_path = PROJECT_ROOT / "openmx4.0_manual" / "s8_2_keywords.html"
    db_path = PROJECT_ROOT / "openmx.db"

    print("[1/4] Parsing ASE parameters.py ...")
    ase_types, ase_units = parse_ase_parameters(ase_param_path)
    print(f"       ASE types: {len(ase_types)} keywords")
    print(f"       ASE units: {len(ase_units)} keywords")

    print("[2/4] Parsing MinerU tables ...")
    mineru_entries = parse_mineru_tables(mineru_path)
    print(f"       MinerU entries: {len(mineru_entries)} keywords")

    print("[3/4] Parsing HTML descriptions ...")
    html_descriptions = parse_html_descriptions(html_path)
    print(f"       HTML descriptions: {len(html_descriptions)} keywords")

    print("[4/4] Querying openmx.db sections ...")
    section_map = get_section_info(db_path)
    print(f"       Indexed keywords: {len(section_map)}")

    print("\nMerging sources ...")
    schema = build_schema(
        ase_types, ase_units, mineru_entries, html_descriptions, section_map
    )

    SCHEMAS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = SCHEMAS_DIR / "keywords.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(schema, f, indent=2, ensure_ascii=False)
    print(f"\nWrote {len(schema)} keywords to {out_path}")

    # Summary
    from collections import Counter
    sources = Counter()
    for v in schema.values():
        for s in v["source"]:
            sources[s] += 1
    print(f"By source: {dict(sources)}")
    typed = sum(1 for v in schema.values() if v["type"] is not None)
    with_default = sum(1 for v in schema.values() if v["default"] is not None)
    with_desc = sum(1 for v in schema.values() if v["description"])
    with_section = sum(1 for v in schema.values() if v["section"])
    print(f"With type: {typed}")
    print(f"With default: {with_default}")
    print(f"With description: {with_desc}")
    print(f"With section: {with_section}")


if __name__ == "__main__":
    main()
