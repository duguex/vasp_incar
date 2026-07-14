# Si diamond PBE / OpenMX benchmark

## Setup

- Code: OpenMX 4.0  XC: GGA-PBE
- Basis: `Si8.0-s2p2d1 / Si_PBE19`
- Energy cutoff: 150.0 Ry
- Bulk k-grid: [4, 4, 4]
- MPI: `-np 8`
- Lattice: fixed cubic a0 = 5.431 Å (experimental)

## Results

| Quantity | Value | Reference | Δ |
|----------|------:|----------:|--:|
| a0 (Å) | 5.431 | 5.431 | fixed |
| Ecoh (eV/atom) | 4.6311 | 4.63 | +0.0011 |
| E_bulk/atom (eV) | -111.7945 | — | — |
| E_atom (eV) | -107.1634 | — | — |

- Bulk SCF: n=16 NormRD=1.21e-10
- Atom SCF: n=15 NormRD=9.9e-11
- Wall (s): bulk=20.19 atom=17.14

## Caveats

- **Not** a full EOS / lattice optimization — a0 is clamped to experiment.
- Cohesive energy depends on free-atom setup (spin, box, mixing).
- Agreement with experiment can be partly fortuitous for a given basis;
  treat as pipeline validation + order-of-magnitude physics check.

- ok=True

