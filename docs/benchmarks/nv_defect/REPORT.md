# NV⁻ defect: VASP/OpenMX reference comparison

## Scope

This is a reference result for a charged, spin-polarized NV-like defect in a 215-atom diamond supercell (`C214N1`). It records the existing VASP/OpenMX outputs and the optional projection/MO analysis performed for this instance.

The report follows the cross-band convention used by `docs/benchmarks/cross_band_*`:

- Γ point only;
- each code aligned to its own global VBM = 0 eV;
- near-edge RMS is an **ordinal-spectrum comparison**, not a wavefunction identity test.

Raw `OUTCAR`, `vasprun.xml`, `PROCAR`, OpenMX `input.out`, and cube files are not committed. Their local generation paths and SHA256 identifiers are in [`report.json`](report.json). `/tmp/...` paths are local provenance only, not permanent repository paths.

## Inputs and provenance

| item | VASP | OpenMX |
|---|---|---|
| engine | VASP 6.5.1 (10Mar25; build 2025-12-01) | OpenMX 4.0 |
| XC | PBE (`GGA=Pe`) | GGA-PBE |
| structure | `C214N1`, 215 atoms, cubic `a=10.6674194336 Å` | same geometry |
| charge | `NELECT=862`, corresponding to charge state −1 | `scf.system.charge=-1` |
| spin | `ISPIN=2`, `NUPDOWN=2` | `scf.SpinPolarization=On`, total spin moment `2.0 μB` |
| cutoff | `ENCUT=520 eV` | `scf.energycutoff=260 Ry` |
| k-point | Γ (`1×1×1`) | Γ (`1×1×1`) |
The `ENCUT=520 eV` → `scf.energycutoff=260 Ry` mapping is the project's ×2 numeric heuristic; it is not an eV↔Ry unit conversion and does not assert physically equivalent cutoffs.

The VASP static input has `LORBIT=0`; its `OUTCAR` already contains the KS eigenvalues. A separate fixed-geometry VASP run with `LORBIT=11` produced `PROCAR` for the optional projection analysis. The OpenMX SCF output already contains eigenvalues; a separate run with `MO.fileout=on` produced the optional MO cubes.

## Eigenvalue results

| quantity | VASP | OpenMX | OpenMX − VASP |
|---|---:|---:|---:|
| Γ global HOMO–LUMO gap (eV) | 1.2636 | 1.2981 | +0.0345 |
| `E_HOMO↑ − E_HOMO↓` edge offset (eV) | 0.6388 | 0.6379 | −0.0009 |
| ordinal spectrum: 16-level RMS (eV) |  |  | 0.0571 |
| ordinal spectrum: maximum absolute difference (eV) |  |  | 0.0727 |
The complete 16-record ordinal pairing is stored in `report.json` under `compare.ordinal_spectrum.records`, so the RMS and maximum can be independently recomputed from the committed summary.

The up/down HOMO indices are 432 and 430 in both outputs. Because the indices differ between spin channels and no same-orbital overlap was computed, the edge offset is not called an exchange or spin splitting.

## Near-degenerate groups

The following groups were compared as subspaces rather than individual bands:

| spin | group | VASP span (eV) | OpenMX span (eV) |
|---|---|---:|---:|
| ↑ | LUMO/LUMO+1 | 0.0001 | 0.0001 |
| ↓ | HOMO−2/HOMO−1 | 0.0001 | 0.0002 |
| ↓ | LUMO/LUMO+1 | 0.0027 | 0.0028 |
| ↓ | LUMO+2/LUMO+3 | 0.0001 | 0.0001 |

No one-to-one physical orbital identity is claimed for these groups.

## Optional orbital/localization comparison

The VASP column is the normalized sum of PAW-sphere `PROCAR` projections on N plus its three nearest C atoms (atom indices 215, 80, 188, 134, one-based). The OpenMX column is the normalized real-space integral of `|ψ_r|² + |ψ_i|²`, including both cube components and voxel volume, over 2-bohr spheres around the same four atoms.
The table is derived from 32 cube files: `homo/lumo × spin(0/1) × n(0..3) × component(r/i)`. The complete set is identified by the aggregate SHA256 recorded in `report.json`.

These are different observables. Their absolute percentages must not be equated; only qualitative localization trends are compared.
The VASP `s/p` values are normalized within `s+p` (`s/(s+p)` and `p/(s+p)`). The PROCAR header also contains five d channels; `d(total)` is reported separately against the total projection and is 0.0% for all rows at the source precision.

| spin/group | VASP defect-region projection | VASP `s/(s+p)` | VASP `p/(s+p)` | VASP `d(total)` | OpenMX cube region density |
|---|---:|---:|---:|---:|---:|
| ↑ HOMO−3 | 0.97% | 0.3% | 99.7% | 0.0% | 1.21% |
| ↑ HOMO−2 | **40.61%** | 5.1% | 94.9% | 0.0% | **33.63%** |
| ↑ HOMO−1 | 0.35% | 9.4% | 90.6% | 0.0% | 0.54% |
| ↑ HOMO | 0.34% | 9.3% | 90.7% | 0.0% | 0.54% |
| ↑ LUMO/LUMO+1 | 1.85% | 49.8% | 50.2% | 0.0% | 1.55% |
| ↑ LUMO+2 | 3.68% | 43.9% | 56.1% | 0.0% | 2.97% |
| ↑ LUMO+3 | 0.27% | 52.9% | 47.1% | 0.0% | 0.78% |
| ↓ HOMO−3 | 0.55% | 0.1% | 99.9% | 0.0% | 0.95% |
| ↓ HOMO−2/HOMO−1 | 1.03% | 0.2% | 99.8% | 0.0% | 1.30% |
| ↓ HOMO | **31.34%** | 6.5% | 93.5% | 0.0% | **23.60%** |
| ↓ LUMO/LUMO+1 | 0.19% | 11.8% | 88.2% | 0.0% | 0.51% |
| ↓ LUMO+2/LUMO+3 | 1.73% | 50.1% | 49.9% | 0.0% | 1.53% |

Both codes identify ↑ HOMO−2 and ↓ HOMO as defect-region localization candidates. This is compatible localization evidence, not proof that the two codes produced the same physical orbital. OpenMX LCAO coefficients were not converted into weights by coefficient-squaring because the required overlap-aware Mulliken/Löwdin data are not present in this artifact set.

## Claim boundary

This report supports:

- Γ-point edge metrics;
- spin-channel edge offsets;
- ordinal-spectrum comparison;
- group-level near-degenerate comparisons;
- qualitative agreement of defect-region localization candidates.

It does not support:

- same-state one-to-one matching;
- exchange splitting of a single orbital;
- direct numerical equality of VASP PAW and OpenMX orbital weights;
- a complete cross-code `s/p/d` comparison;
- wavefunction overlap claims.
