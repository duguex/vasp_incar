# vaspkit convention checklist (VASP input GT)

> Ground-truth **conventions** for everyday VASP task inputs.  
> Not a Python dependency — use as review checklist when extending `vasp-gen` / semantic IR.  
> Spec: `docs/superpowers/specs/2026-07-14-semantic-roundtrip-design.md` §8.

## Role vs this project

| Tool | Owns |
|------|------|
| **dft-tools** | Knowledge query, light INCAR templates, KPOINTS/POTCAR helpers, VASP↔OpenMX IR |
| **pymatgen** | Structural GT (Structure, Kpoints, Incar, Potcar objects) |
| **vaspkit** | Workflow file checklists & post-processing culture (this doc) |
| **pydefect** | Defect supercells, charge corrections, defect JSON artifacts |

## Minimal SCF package

Expected files (aligned with `vasp-gen` suite mode):

- [ ] `INCAR`
- [ ] `POSCAR` (or `CONTCAR` restart)
- [ ] `KPOINTS`
- [ ] `POTCAR` (local PSP only; never in git)

Generate:

```bash
vasp-gen POSCAR -t scf --kspacing 0.3 --poscar --potcar -o calc/
```

## Geometry relaxation

- [ ] `IBRION=2` (or 1), `NSW>0`, `EDIFFG` set
- [ ] `ISIF` matches goal (2 ions, 3 ions+cell, …)
- [ ] Same four files as SCF

Template: `vasp-gen … -t relax`

## Metallic SCF

- [ ] `ISMEAR=1` or `2`, adequate `SIGMA`
- [ ] Prefer denser k-mesh / smaller `--kspacing`

Template: `-t scf_metal`

## Band structure (workflow culture)

vaspkit-style two-step:

1. SCF → `CHGCAR`
2. Non-SCF bands: `ICHARG=11`, line-mode `KPOINTS`, often `LORBIT`

dft-tools:

- Template `-t band` sets `ICHARG=11` skeleton
- Line-mode KPOINTS **not** auto-generated in v1 (use pymatgen `automatic_linemode` / vaspkit manually)
- Semantic IR: `calc_class=band`

## What vaspkit often adds that we do **not** own

- DOS/band plotting, fatband, effective mass
- ELFCAR / PROCAR analysis
- Automated multi-step job scripts for hybrid/GW/BSE

Point agents to **vaspkit** or **pymatgen** for those — do not reimplement in dft-tools.

## Defect calculations

- SCF suite above is necessary but not sufficient
- pydefect extras (examples): `supercell_info.json`, `defect_entry.json`, corrections, band-edge JSON
- See `omx_tools.semantic.gt.PYDEFECT_DEFECT_EXTRA` and `probe_pydefect_shape()`

## Review questions before adding a VASP feature

1. Does pymatgen already expose a correct object/API? → wrap, don't fork.
2. Is this a post-processing plot / DOS path? → vaspkit, not dft-tools.
3. Is this defect-specific bookkeeping? → pydefect.
4. Does it break VASP→IR→VASP must-preserve? → add round-trip test first.
