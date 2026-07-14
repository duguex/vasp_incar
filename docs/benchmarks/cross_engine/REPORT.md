# Cross-engine examples

Geometry from official examples of code A is SCF'd on code B. Absolute total energies are NOT comparable; forces at the same geometry, pressure/stress, and ΔE-type quantities are.

### What is comparable?

- force_max / force_rms at identical geometry (eV/Å)
- external pressure / stress (same cell)
- energy differences ΔE (Ecoh, isomer gaps) — not absolute E
- relaxed lattice constants / bond lengths

| case (OMX geom) | |F|_max VASP (eV/Å) | |F|_max OpenMX (eV/Å) | Δ|F|_max | P_VASP (kbar) |
|-----------------|-------------------:|---------------------:|--------:|--------------:|
| `Ndia2` | 4.2988 | 4.7757 | 0.4770 | 98.3000 |
| `Graphite4` | 0.4629 | 0.1922 | 0.2707 | 6.5300 |
| `Methane` | 0.2334 | 4.0878 | 3.8544 | -0.1000 |
| `H2O` | 0.8980 | 0.7972 | 0.1008 | -0.2600 |

Absolute total energies remain non-comparable (different PP/basis zero).
Force differences of ~0.1–0.5 eV/Å on crystals are typical for PBE PAW vs PAO;
large Δ (e.g. Methane) often means residual geometry/box mismatch, not a pass gate.

