# Cross ΔE: C cohesive energy (VASP vs OpenMX)

Protocol: fixed a0 = 3.567 Å cubic C₈ + spin atom; Ecoh = E_atom − E_bulk/8 (eV/atom). Absolute E not compared.

| engine | Ecoh (eV/atom) | vs exp | E_bulk/atom (eV) | E_atom (eV) |
|--------|---------------:|-------:|-----------------:|------------:|
| experiment | 7.37 | — | — | — |
| VASP | 7.8154 | +0.4454 | -9.0955 | -1.2802 |
| OpenMX | 7.8861 | +0.5161 | -158.8827 | -150.9967 |

- |Ecoh_VASP − Ecoh_OpenMX| = 0.07069878765494231
- ok: **True**

