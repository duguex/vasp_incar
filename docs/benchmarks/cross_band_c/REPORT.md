# Cross KS orbital energies: C (VASP vs OpenMX)

Aligned so **VBM = 0**. Absolute eigenvalues not compared.

| quantity | VASP | OpenMX | \|Δ\| |
|----------|-----:|-------:|----:|
| fundamental gap (eV) | 4.368278 | 4.554947021962495 | 0.18666902196249513 |
| direct gap @ Γ (eV) | 4.655738999999999 | 5.0574481792198505 | 
| RMS (top occ+low empty) (eV) |  |  | 0.29743876636568306 |

- gate: **FAIL** (tol_gap=0.25 eV, tol_rms=0.2 eV)
- k found VASP: ['G', 'X', 'K', 'L'] OpenMX: ['G', 'X', 'K', 'L']

| k | RMS (eV) | max\|Δ\| (eV) |
|---|--------:|------------:|
| G | 0.28589959316773483 | 0.40190897941439374 |
| X | 0.4254505237618352 | 0.824891494589199 |
| K | 0.24867446263255438 | 0.3479083925126556 |
| L | 0.1711536299360071 | 0.2382803330124652 |

