# Official engine tests

- MPI np: 8
- overall ok: **True**

## OpenMX `-runtest`

- cases: 14/14 pass
- total elapsed (engine): 97.22 s
- wall: 99.57 s
- criterion: |diff Utot|,|diff Force| < 1e-06

| # | case | ΔUtot | ΔForce | t(s) | pass |
|---|------|------:|-------:|-----:|:----:|
| 1 | `input_example/Benzene.dat` | 0.000e+00 | 0.000e+00 | 3.60 | Y |
| 2 | `input_example/C60.dat` | 4.000e-12 | 0.000e+00 | 13.40 | Y |
| 3 | `input_example/CO.dat` | 0.000e+00 | 1.300e-11 | 6.24 | Y |
| 4 | `input_example/Cr2.dat` | 0.000e+00 | 3.000e-12 | 5.77 | Y |
| 5 | `input_example/Crys-MnO.dat` | 1.500e-11 | 1.000e-12 | 12.05 | Y |
| 6 | `input_example/GaAs.dat` | 1.000e-12 | 0.000e+00 | 21.87 | Y |
| 7 | `input_example/Glycine.dat` | 0.000e+00 | 0.000e+00 | 3.52 | Y |
| 8 | `input_example/Graphite4.dat` | 0.000e+00 | 0.000e+00 | 2.85 | Y |
| 9 | `input_example/H2O-EF.dat` | 0.000e+00 | 1.000e-12 | 3.08 | Y |
| 10 | `input_example/H2O.dat` | 0.000e+00 | 0.000e+00 | 2.59 | Y |
| 11 | `input_example/HMn.dat` | 0.000e+00 | 0.000e+00 | 9.96 | Y |
| 12 | `input_example/Methane.dat` | 6.500e-11 | 0.000e+00 | 2.08 | Y |
| 13 | `input_example/Mol_MnO.dat` | 0.000e+00 | 0.000e+00 | 6.22 | Y |
| 14 | `input_example/Ndia2.dat` | 0.000e+00 | 1.000e-12 | 3.98 | Y |

## Tooling cross (official OpenMX inputs)

- parse ok: 14/14
- lint no-error: 14/14

## How this differs from Ecoh/experiment

- **Engine runtest**: numerical regression vs **code-shipped** references (install/correctness).
- **Si Ecoh benchmark**: physics vs **experiment** (order-of-magnitude).
- **Tooling cross**: dft-tools still understands official inputs.

