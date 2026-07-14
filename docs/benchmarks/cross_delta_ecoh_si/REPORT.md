# Cross ΔE: Si cohesive energy (VASP vs OpenMX)

Protocol: fixed a0 = 5.431 Å cubic Si₈ + spin atom; Ecoh = E_atom − E_bulk/8 (eV/atom). Absolute E not compared.

| engine | Ecoh (eV/atom) | vs exp | E_bulk/atom (eV) | E_atom (eV) |
|--------|---------------:|-------:|-----------------:|------------:|
| experiment | 4.63 | — | — | — |
| VASP | 4.5744 | -0.0556 | -5.4198 | -0.8454 |
| OpenMX | 4.6310 | +0.0010 | -111.7945 | -107.1635 |

- |Ecoh_VASP − Ecoh_OpenMX| = 0.05655732364652266
- ok: **True**

