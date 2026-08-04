# Workflow Examples

End-to-end scenarios demonstrating how `dft-tools` bridges natural language, VASP, and OpenMX.

---

## 1. VASP → OpenMX migration

**Scenario:** You have a working VASP INCAR for a Si band structure calculation and want to migrate to OpenMX.

### Step 1: Understand your VASP parameters

```bash
# Look up key INCAR tags
python3 -m vasp_query tag ENCUT
python3 -m vasp_query tag ISMEAR
python3 -m vasp_query tag KSPACING

# Search for band structure best practices
python3 -m vasp_query search "band structure Si"
# → Finds: Fcc Si bandstructure, Si HSE bandstructure, Si bandstructure
```

### Step 2: Convert to OpenMX

```bash
# Direct conversion (INCAR + structure → OpenMX .dat)
vasp2omx INCAR POSCAR -o Si.dat

# Or use the unified CLI
dft convert vasp:omx INCAR POSCAR -o Si.dat
```

### Step 3: Verify and refine

```bash
# Browse OpenMX keywords for SCF settings
omx-db keyword scf.energycutoff
omx-db keyword scf.Kgrid

# Search the manual for band structure setup
omx-db search "band structure"
omx-db section 10.2           # read about k-path generation
```

### Step 4: Generate a fresh input from structure (alternative to conversion)

```bash
# Generate SCF + band calculation
omx-gen POSCAR -t scf_band -o Si_band.dat

# For metallic systems
omx-gen POSCAR -t scf_band_metal --cutoff 400 -k 4 4 4 -o Si_metal.dat
```

---

## 2. Cross-code concept lookup

**Scenario:** You know a concept in VASP and want to find the equivalent in OpenMX (or vice versa).

### DFT+U / Hubbard correction

```bash
# In VASP
python3 -m vasp_query search "DFT+U Hubbard"
# → LDAU, LDAUU, LDAUJ, LDAUL, LDAUTYPE tags with docs

# In OpenMX
omx-db search "Hubbard U LDA+U"
omx-db keyword scf.Hubbard.U.values
omx-db section 40              # read about DFT+U in OpenMX
```

### Energy cutoff

```bash
# VASP: what cutoff should I use?
python3 -m vasp_query tag ENCUT
# → Default from POTCAR, typically 400-520 eV

# OpenMX: equivalent parameter
omx-db keyword scf.energycutoff
# → Note: OpenMX uses Ry, not eV. Conversion heuristic applied.
```

### SCF convergence

```bash
# VASP: mixing parameters and algorithms
python3 -m vasp_query tag AMIX
python3 -m vasp_query tag IMIX
python3 -m vasp_query search "SCF convergence"

# OpenMX: mixing and convergence
omx-db rag "how to tune SCF mixing for metallic systems"
omx-db keyword scf.Mixing.Type
omx-db keyword scf.Kerker.factor
omx-db section 16              # full SCF convergence chapter
```

### Spin polarization

```bash
# VASP
python3 -m vasp_query tag ISPIN
python3 -m vasp_query tag MAGMOM

# OpenMX
omx-db keyword scf.SpinPolarization
omx-db keyword Atoms.Cont.Orbitals
```

---

## 3. Natural language → calculation

**Scenario:** Tell the tools what you want to compute, and they generate the input file.

### "Run an SCF calculation for this crystal"

```bash
# Use omx-gen with default template
omx-gen structure.cif -t scf_band -o calc.dat
```

### "I need a geometry optimization for a molecule"

```bash
# Molecule → no k-points, use cluster solver
omx-gen molecule.xyz -t scf_cluster -o molecule.dat

# With geometry optimization
omx-gen molecule.xyz -t geom_opt -o opt.dat
```

### "Check what parameters I need for a specific OpenMX keyword"

```bash
# Natural language search of the manual
omx-db rag "how to set initial magnetic moments"

# Structured keyword metadata
omx-gen --keyword scf.SpinPolarization --json
# → {"name": "scf.SpinPolarization", "type": "string",
#     "default": "Off", "valid_values": ["Off", "On", "NC"], ...}
```

### "Set up a band structure calculation"

```bash
# 1. First run SCF
omx-gen structure.cif -t scf_band -o scf.dat

# 2. Then band dispersion (requires prior SCF)
omx-gen structure.cif -t band_dispersion -o bands.dat
```

---

## 4. Troubleshooting convergence

**Scenario:** Your SCF isn't converging and you need advice.

```bash
# Ask the knowledge base
omx-db rag "SCF not converging for metallic system"
# → Returns relevant manual sections on mixing methods

# Read the convergence guide
omx-db section 16              # SCF convergence basics
omx-db section 16.3            # On-the-fly parameter adjustment

# Search VASP knowledge for complementary advice
python3 -m vasp_query search "charge sloshing" --debug
-> Traces search pipeline: exact → alias → FTS5+semantic → legacy
```

### Common convergence fixes

| Symptom | VASP parameter | OpenMX keyword |
|---------|---------------|----------------|
| Charge sloshing | `IMIX=4`, `BMIX` | `scf.Mixing.Type` → Kerker |
| Slow convergence | `AMIX=0.2`, `AMIX_MAG=0.4` | `scf.Mixing.StartPulay` |
| Oscillating energy | `NELMDL=-5` | `scf.maxIter` |
| Metal convergence | `ISMEAR=1`, `SIGMA=0.2` | `scf.ElectronicTemperature` |
| Spin instability | `MAGMOM` initialization | `scf.SpinPolarization` |

---

## 5. Explore the knowledge bases

### VASP tag landscape

```bash
# List all known INCAR tags
python3 -m vasp_query list | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'{d[\"count\"]} tags')"

# Top 5 most common tags in real calculations
python3 -m vasp_query stats | python3 -c "
import sys,json
d=json.load(sys.stdin)
for t, s in sorted(d.items(), key=lambda x: -x[1]['count'])[:5]:
    print(f'{t}: {s[\"count\"]}/{s[\"total_configs\"]} ({s[\"frequency\"]}%)')
" 2>/dev/null

# Tags that commonly appear together
python3 -m vasp_query cooccur ENCUT ISMEAR -H
```

### OpenMX manual structure

```bash
# List all sections
omx-db list

# Count entries by type
omx-db stats --json | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Sections: {d[\"tables\"][\"sections\"]}, Keywords: {d[\"tables\"][\"index_entries\"]}')"

# Find keywords by topic
omx-db keyword scf.Kgrid
omx-db keyword md.maxIter
```

---

## 6. Si8 real-structure E2E — generate ↔ advise ↔ knowledge

**Scenario:** Use the repo’s real `work/Si8.cif` (Si bulk cell) to prove that
**generation**, **lint/advise**, and the **knowledge base** run as one loop —
not only unit fixtures.

### One-shot demo script

```bash
# Always (VASP gen + advise + roundtrip + intentional bad INCAR --fix)
python3 scripts/e2e_si8_advise_loop.py

# Also OpenMX generate + advise-omx (needs DFT_DATA19)
export OPENMX_DFT_DATA_PATH=/mnt/shared/DFT_DATA19   # or your path
python3 scripts/e2e_si8_advise_loop.py --with-omx-gen
```

### What the loop does

1. **Know** — `vasp-query` ENCUT description + community top values  
2. **Generate** — `vasp-gen` `scf` on `work/Si8.cif` → `INCAR` + `KPOINTS` + `POSCAR`  
3. **Advise** — `advise` on generated INCAR (lint + knowledge attach)  
4. **Fix demo** — intentional bad INCAR (`NSW>0`+`IBRION=-1`, low ENCUT) → `--fix` safe repairs (IBRION/EDIFFG); ENCUT still warned (not auto-raised)  
5. **Self-consistency** — `roundtrip_vasp_ir` on generated tags  
6. **Optional OpenMX** — `omx-gen` Si8 + `advise-omx`  

### Manual equivalent

```bash
# Generate suite for Si8
vasp-gen work/Si8.cif -t scf --kspacing 0.35 --poscar -o /tmp/si8/

# Organic coupling: lint findings + knowledge snippets
dft semantic advise /tmp/si8/INCAR -H

# Mapping self-consistency
dft semantic roundtrip /tmp/si8/INCAR

# Generate → advise in one call
dft semantic gen-advise -t scf

# OpenMX side (needs OPENMX_DFT_DATA_PATH)
omx-gen work/Si8.cif -t scf_band -o /tmp/si8/Si8.dat
dft semantic advise-omx /tmp/si8/Si8.dat -H
```

### Tests

```bash
# Core E2E (needs work/Si8.cif + pymatgen)
pytest tests/test_e2e_si8_loop.py -q

# Optional OpenMX engine SCF (container) — existing
pytest tests/test_integration.py -q
```

### Limits

- Default E2E does **not** claim energy/convergence validation against experiment.
- It validates: real structure path, file generation, advise↔knowledge wiring, semantic round-trip, optional OpenMX syntax generation.

---

## 7. Energy / experiment benchmark (Si diamond, OpenMX PBE)

**Scenario:** Beyond file-level E2E, validate that **generated inputs actually run** and that a physical observable is in the experimental ballpark.

### Run (MPI `-np 8`)

```bash
export OPENMX_DFT_DATA_PATH=/mnt/shared/DFT_DATA19
# needs singularity + OpenMX SIF at /mnt/shared/openmx4.0_intel.sif
python3 scripts/bench_si_pbe_openmx.py --np 8 \
  --outdir work/benchmarks/si_pbe
```

What it does:

1. Build cubic Si₈ at experimental **a0 = 5.431 Å** (ASE)
2. `omx-gen` bulk SCF (PBE, `Si8.0-s2p2d1`, default k=4×4×4, 150 Ry)
3. Spin-polarized Si free atom (cluster solver)
4. `mpirun -np 8 openmx …` inside the container
5. Parse `Utot` → **Ecoh = E_atom − E_bulk/8**

### Reference result (this workstation)

| Quantity | Computed | Experiment | Δ |
|----------|----------:|----------:|--:|
| a0 (Å) | 5.431 (fixed) | 5.431 | — |
| Ecoh (eV/atom) | **4.6311** | 4.63 | +0.001 |

Artifacts (inputs + report, no cubes): [`docs/benchmarks/si_pbe/`](../benchmarks/si_pbe/).

### Caveats

- **a0 is fixed** — not an EOS / lattice relaxation benchmark.
- Ecoh depends on free-atom spin/box; near-exact match to experiment can be partly fortuitous for a given PAO basis.
- Use this as **pipeline + physics order-of-magnitude** evidence, not a published basis-set convergence study.

### Parser unit tests (no container)

```bash
pytest tests/test_bench_si_parse.py -q
```

---

## 8. Official engine tests (OpenMX `-runtest` + tooling cross)

**Scenario:** Use **vendor-shipped** tests as the ground truth for “does the
binary work?” and “do our tools still understand official inputs?”

### Why this is better than only Ecoh

| Layer | Ground truth | What it proves |
|-------|--------------|----------------|
| OpenMX `-runtest` | Code-bundled `*.out` (14 cases) | Install/MPI/numerical regression |
| VASP `testsuite` | Code-bundled OUTCAR.ref | Same for VASP (needs matching version) |
| Tooling cross | parse/lint/advise on those inputs | dft-tools I/O + rules on real corpus |
| Si Ecoh (§7) | Experiment | Physics order-of-magnitude |

### Run OpenMX official suite (`mpirun -np 8`)

```bash
export OPENMX_DFT_DATA_PATH=/mnt/shared/DFT_DATA19
python3 scripts/run_official_engine_tests.py --np 8 \
  --workdir work/benchmarks/official_runtest
```

Manual equivalent (writable copy of OpenMX `work/`):

```bash
mpirun -np 8 openmx -runtest          # → runtest.result
# large / perf: mpirun -np 112 openmx -runtestL
```

### VASP (container-matched 6.5.1)

Default is **not** host `~/hack_vasp` (easy to mix versions). Use the SIF tree
where `bin` and `testsuite` are the same release:

```bash
# harness: singularity + /opt/vasp.6.5.1/{bin,testsuite} inside vasp_latest.sif
python3 scripts/run_official_engine_tests.py --np 4 --skip-engine --with-vasp \
  --vasp-tests DFT_OatomPBE
```

Reference (this workstation): **DFT_OatomPBE PASS** (`vasp.6.5.1` in
`/mnt/shared/vasp_latest.sif`; energy/force/stress match ref).

Host `~/hack_vasp` only if its `bin` and `testsuite` are known-matching.

### Reference results

- OpenMX `-runtest`: **14/14 pass**, ~97 s (`np=8`)
- Tooling: **14/14 parse + lint** on `input_example/*.dat`
- VASP container: **DFT_OatomPBE pass**
- Artifacts: [`docs/benchmarks/official_runtest/`](../benchmarks/official_runtest/)


---

## 9. True cross-engine examples (A’s geometry on B’s code)

**Not** “each code self-test”. **Yes**: official example geometry from code A
must **SCF on code B**.

| Direction | Source | Target run |
|-----------|--------|------------|
| OpenMX → VASP | `input_example` (Ndia2, Graphite4, Methane, H2O) | container `vasp.6.5.1` |
| VASP → OpenMX | suite `bulk_BN_PBEsol`, `DFT_OatomPBE` | container OpenMX 4.0 |

Keyword mapping is **lossy** on purpose: structure + safe target defaults.

**Not comparable:** absolute total energy (different PP/basis zero).

**Comparable (reported):** forces at the **same geometry** (|F|_max/rms in eV/Å),
pressure/stress; later: ΔE (Ecoh, isomer gaps), relaxed lattice/bond lengths.

### Run

```bash
export OPENMX_DFT_DATA_PATH=/mnt/shared/DFT_DATA19
export VASP_PP_PATH=/mnt/shared/VASP_POT/POT_GGA_PAW_PBE_54
python3 scripts/cross_engine_examples.py --np 4
```

### Pass criteria

1. Geometry extracted from official source example  
2. Target engine SCF finishes with finite total energy  
3. Report both directions in one table  

### Reference (this workstation)

- **6/6 OK** (4 omx→vasp + 2 vasp→omx)  
- Artifacts: [`docs/benchmarks/cross_engine/`](../benchmarks/cross_engine/)  

---


---

## 10. Cross ΔE Ecoh + physics gates (P0/P1)

### Differential Ecoh (Si and C)

Same protocol on VASP and OpenMX:

- bulk: diamond cubic 8 atoms @ experimental a0 (fixed)
- atom: spin-polarized free atom
- **Ecoh = E_atom − E_bulk/8** (eV/atom) — absolute E not compared

```bash
export OPENMX_DFT_DATA_PATH=/mnt/shared/DFT_DATA19
export VASP_PP_PATH=/mnt/shared/VASP_POT/POT_GGA_PAW_PBE_54
python3 scripts/cross_delta_ecoh.py --element Si --np 4
python3 scripts/cross_delta_ecoh.py --element C --np 4
# alias:
python3 scripts/cross_delta_ecoh_si.py --np 4
```

| element | a0 (Å) | exp Ecoh | VASP | OpenMX | \|V−O\| |
|---------|-------:|---------:|-----:|-------:|------:|
| Si | 5.431 | 4.63 | 4.574 | 4.631 | **0.057** |
| C  | 3.567 | 7.37 | 7.815 | 7.886 | **0.071** |

Artifacts: [`cross_delta_ecoh_si`](../benchmarks/cross_delta_ecoh_si/),
[`cross_delta_ecoh_c`](../benchmarks/cross_delta_ecoh_c/).

### P0 physics gates

Hard fail if any Ecoh report has `|Ecoh_VASP − Ecoh_OpenMX| > 0.15 eV`,
or required cross_engine cases (Ndia2, Graphite4) are not ok.

```bash
# validate existing reports only
python3 scripts/run_cross_gates.py --check-only --elements Si C

# run missing benches then gate
python3 scripts/run_cross_gates.py --np 4 --elements Si C
```

Tolerances (override via env): `CROSS_GATE_TOL_ECOH_CODE` (default 0.15),
`CROSS_GATE_TOL_ECOH_EXP` soft (default 0.5, warn only).

Gate report: [`docs/benchmarks/cross_gates/`](../benchmarks/cross_gates/).



---

## 11. Cross KS orbital energies (Si eigenvalues)

Compare **orbital energies** (not wavefunctions) on the same Si₈ cell:

- k: Γ, X, K, L (conventional cubic fractional)
- align **VBM = 0**
- report fundamental gap, Γ direct gap, RMS of top occupied + low empty levels

```bash
python3 scripts/cross_band_si.py --np 4
python3 scripts/cross_band_si.py --check-only
```

### Reference (this workstation)

| | VASP | OpenMX | \|Δ\| |
|--|-----:|-------:|----:|
| fundamental gap (eV) | 0.654 | 0.776 | **0.121** |
| eigenvalue RMS (eV) | | | **0.136** |

Gates (hard): `|Δgap| ≤ 0.25 eV`, `RMS ≤ 0.20 eV` (env `CROSS_BAND_TOL_GAP` / `CROSS_BAND_TOL_RMS`).

Included in `python3 scripts/run_cross_gates.py --check-only`.

Artifacts: [`docs/benchmarks/cross_band_si/`](../benchmarks/cross_band_si/).



---

## 12. Cross a_eq (light lattice scan)

5-point E(a) scan → parabolic a_eq for Si (and optionally C):

```bash
python3 scripts/cross_aeq.py --element Si --np 4
```

Reference Si: VASP a_eq≈5.472 Å, OpenMX≈5.499 Å, exp 5.431; rel |Δ|≈0.49% (tol 1%).

C band eigenvalues: `python3 scripts/cross_band.py --element C` (tol RMS 0.35 eV).


---

## 13. NV⁻ defect: existing-output and orbital comparison

Reference report: [`docs/benchmarks/nv_defect/REPORT.md`](benchmarks/nv_defect/REPORT.md).

This 215-atom `C214N1` Γ-point case documents the boundary between existing-output analysis and optional projection calculations:

- VASP `OUTCAR` and OpenMX `input.out` already contain spin-resolved KS eigenvalues; do not rerun merely to obtain eigenvalues.
- VASP `PROCAR` requires a fixed-geometry projection calculation with `LORBIT=11`.
- OpenMX MO cubes require `MO.fileout=on`, `num.HOMOs`, `num.LUMOs`, and explicit `MO.kpoint` settings.
- The 16-level RMS is an **ordinal-spectrum comparison**, not a same-state error.
- `E_HOMO↑ − E_HOMO↓` is a spin-channel edge offset, not a same-orbital exchange splitting.
- Near-degenerate bands are compared as subspaces; VASP PAW projections and OpenMX cube densities are method-specific and must not be treated as identical weights.
- The defect-region analysis uses N215 plus vacancy-facing C61/C127/C185 around fractional vacancy center `(0.5, 0.5, 0.5)`; VASP angular columns are whole-cell PROCAR sums, while localization columns use the four-atom region.

Large raw outputs remain external artifacts. The committed report records local source paths, input/output SHA256 values, engine settings, and claim limitations.

## Environment setup quick reference

```bash
# dft-tools
export OLLAMA_URL="http://localhost:11434"     # default
export OLLAMA_MODEL="nomic-embed-text"          # default

# OpenMX runtime
export OPENMX_DB_PATH="/path/to/openmx.db"     # default: <repo>/openmx.db
export OPENMX_DFT_DATA_PATH="/path/to/DFT_DATA19"  # required for omx-gen
```
