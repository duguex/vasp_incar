# Cross KS orbital energies: Si (VASP vs OpenMX)

Aligned so **VBM = 0**. Absolute eigenvalues not compared.

| quantity | VASP | OpenMX | \|Δ\| |
|----------|-----:|-------:|----:|
| fundamental gap (eV) | 0.6544429999999997 | 0.7757988591328853 | 0.1213558591328856 |
| direct gap @ Γ (eV) | 0.6544429999999997 | 0.7757988591328853 | 
| RMS (top occ+low empty) (eV) |  |  | 0.13640210602811542 |

- gate: **PASS** (tol_gap=0.25 eV, tol_rms=0.2 eV)
- k found VASP: ['G', 'X', 'K', 'L'] OpenMX: ['G', 'X', 'K', 'L']

| k | RMS (eV) | max\|Δ\| (eV) |
|---|--------:|------------:|
| G | 0.08716445379447951 | 0.12135585977697927 |
| X | 0.22492903308584775 | 0.4365921806611932 |
| K | 0.10215763507165494 | 0.14242006130497575 |
| L | 0.07612649855315286 | 0.10386031200949963 |

