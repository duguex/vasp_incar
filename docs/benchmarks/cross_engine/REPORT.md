# Cross-engine examples

Geometry from official examples of code A is SCF'd on code B. Energies are not required to match across codes.

- ok: **True** (6/6)
- np: 4

| direction | case | ok | energy | wall_s |
|-----------|------|:--:|-------:|-------:|
| openmx→vasp | `Ndia2` | Y | -17.385861 | 2.19 |
| openmx→vasp | `Graphite4` | Y | -36.491826 | 2.68 |
| openmx→vasp | `Methane` | Y | -24.024263 | 5.47 |
| openmx→vasp | `H2O` | Y | -14.213647 | 8.15 |
| vasp→openmx | `bulk_BN_PBEsol` | Y | -358.1568476203714 | 81.44 |
| vasp→openmx | `DFT_OatomPBE` | Y | -436.3665600605104 | 5.92 |

## Pass criteria

1. Geometry extracted from source official example
2. Target engine SCF completes with finite total energy
3. Energies across codes are **informational only** (different basis/PP)

