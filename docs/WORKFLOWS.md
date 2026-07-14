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

# optional VASP subset (binary must match suite version)
python3 scripts/run_official_engine_tests.py --np 8 --skip-engine --with-vasp \
  --vasp-tests DFT_OatomPBE
```

Manual equivalent (from a **writable** copy of `work/`):

```bash
mpirun -np 8 openmx -runtest          # → runtest.result
# large / perf variants:
### VASP (container-matched 6.5.1)

Default is **not** host `~/hack_vasp` (easy to mix versions). Use the SIF tree
where `bin` and `testsuite` are the same release:

```bash
# inside harness: singularity + /opt/vasp.6.5.1/{bin,testsuite}
python3 scripts/run_official_engine_tests.py --np 4 --skip-engine --with-vasp \
  --vasp-tests DFT_OatomPBE
```

Reference (this workstation): **DFT_OatomPBE PASS** with `vasp.6.5.1` in
`/mnt/shared/vasp_latest.sif` (energy/force/stress match ref).


`~/hack_vasp/testsuite` + `vasp_std` may **version-skew**. A Fortran format
error or energy table shape mismatch usually means suite≠binary, not bad
physics. Prefer OpenMX `-runtest` as the always-on engine gate here.

---

## Environment setup quick reference

```bash
# dft-tools
export OLLAMA_URL="http://localhost:11434"     # default
export OLLAMA_MODEL="nomic-embed-text"          # default

# OpenMX runtime
export OPENMX_DB_PATH="/path/to/openmx.db"     # default: <repo>/openmx.db
export OPENMX_DFT_DATA_PATH="/path/to/DFT_DATA19"  # required for omx-gen
```
