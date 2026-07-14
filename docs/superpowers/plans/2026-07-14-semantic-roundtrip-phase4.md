# Plan: Semantic Round-Trip Phase 4 — GT expansion (done)

> Spec §8 / §10 Phase 4

## Delivered

| Item | Location |
|------|----------|
| pymatgen KPOINTS file == policy rebuild | `gt.probe_kpoints_roundtrip_file`, `tests/test_semantic_gt.py` |
| pymatgen `Incar` accepts decode_vasp / vasp-gen | `probe_incar_pymatgen_accepts` |
| pydefect boundary | `probe_pydefect_shape`, optional SupercellInfo import smoke |
| vaspkit conventions | `docs/vaspkit-checklist.md` (no Python dep) |

## GT hierarchy (locked)

1. **pymatgen** — structural / object correctness  
2. **vaspkit checklist** — workflow file culture  
3. **pydefect** — defect package extras outside dft-tools scope  

## Spec phases complete

- Phase 1: preserve-key round-trip  
- Phase 2: Semantic IR + vasp2omx  
- Phase 3: encode_omx_dat + cross grade + CLI  
- Phase 4: GT probes + docs  
