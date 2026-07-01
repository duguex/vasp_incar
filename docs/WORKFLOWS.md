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

## Environment setup quick reference

```bash
# dft-tools
export OLLAMA_URL="http://localhost:11434"     # default
export OLLAMA_MODEL="nomic-embed-text"          # default

# OpenMX runtime
export OPENMX_DB_PATH="/path/to/openmx.db"     # default: <repo>/openmx.db
export OPENMX_DFT_DATA_PATH="/path/to/DFT_DATA19"  # required for omx-gen
```
