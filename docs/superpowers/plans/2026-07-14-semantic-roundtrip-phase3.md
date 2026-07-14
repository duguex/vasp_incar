# Plan: Semantic Round-Trip Phase 3 (done)

> Spec: `docs/superpowers/specs/2026-07-14-semantic-roundtrip-design.md`

## Delivered

| Item | Location |
|------|----------|
| Stronger OpenMX encode from `.dat` | `encode_omx_dat`, `infer_template_from_ase` |
| Cross-code lossy report | `cross_roundtrip_vasp` — `ok_core` + `expected_loss` |
| CLI | `dft semantic show\|roundtrip\|cross\|show-omx` |
| Tests | `tests/test_semantic_phase3.py` |

## Grades

- **same_code_strict**: `roundtrip` / `roundtrip_vasp_ir` — must-preserve full set
- **cross_code_lossy**: core ENCUT/ISPIN/EDIFF/NELM/GGA; ISMEAR/ALGO/NSW=0 etc. listed as expected loss

## Phase 4 next

- pymatgen KPOINTS/INCAR GT probes in CI
- optional pydefect minimal package shape
- vaspkit checklist docs
