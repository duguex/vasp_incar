# DFT Tools — Natural Language ↔ DFT Program Bridge

A framework for connecting natural language queries to DFT program knowledge and input generation. **VASP** and **OpenMX** are the first two integrated codes — the architecture is designed to extend to CASTEP, QE, FHI-aims, etc.

```
User / Agent (natural language)
        │
        ▼
   ┌────────────────────┐
   │  Skill interface   │  ← Hermes-registered SKILL.md per code
   │  CLI (search, tag, │
   │  query, rag)       │
   └────────┬───────────┘
            │
    ┌───────┴───────┐
    ▼               ▼
┌──────────┐  ┌──────────┐
│ vasp_    │  │ omx_     │  ← per-code packages
│ query/   │  │ tools/   │
│          │  │          │
│ Tag DB   │  │ Manual   │  ← knowledge indexed from docs
│ 676 tags │  │ 281 secs │
│ 10K cfg  │  │ 304 kw   │
└────┬─────┘  └────┬─────┘
     │             │
     └──────┬──────┘
            ▼
     ┌──────────────┐
     │   Mapping    │  ← schemas/vasp_to_ase.json
     │   Layer      │     + future: omx_to_ase, castep_to_ase, ...
     └──────┬──────┘
            ▼
     ┌──────────────┐
     │  Cross-code  │  ← vasp2omx, omp2vasp
     │  Conversion  │     + future: vasp2qe, omx2castep, ...
     └──────────────┘
```

## Currently integrated

| Code | Package | Knowledge | Input gen | Conversion |
|------|---------|-----------|-----------|------------|
| **VASP** | `vasp_query/` | 676 INCAR tags + 10K configs + wiki | — | vasp2omx |
| **OpenMX** | `omx_tools/` | 281 manual sections + 304 keywords | ✅ omx-gen | omp2vasp |

## Architecture for adding a new DFT code

1. **Create a package** (e.g. `castep_tools/`)
2. **Index its manual** — parse HTML/PDF docs into structured JSON + FTS5 db
3. **Write the parsers** — input file → typed dict (like `parsers/vasp.py`)
4. **Write the writers** — typed dict → input file (like `writers/openmx.py`)
5. **Extend the mapping schema** — add CAStep parameters to `schemas/*.json`
6. **Register a Skill** — `skills/castep-tools/SKILL.md`

Shared infrastructure (`dft_utils/`) handles: version envelope, debug logging, JSON error format, search algorithm.

## Quick start

```bash
# Natural language search across knowledge bases
python3 -m vasp_query search "energy cutoff for transition metals"
omx-db rag "how to tune SCF mixing for metallic systems"

# Generate inputs
omx-gen structure.cif -t scf_band -o calc.dat

# Convert between codes
vasp2omx INCAR POSCAR -o input.dat
omp2vasp input.dat -o INCAR
```

Full walkthroughs: [`docs/WORKFLOWS.md`](docs/WORKFLOWS.md) — VASP↔OpenMX migration,
cross-code concept lookup, natural language → calculation, convergence troubleshooting.

## Installation

```bash
pip install -e .                       # core (pydantic)
pip install -e ".[vasp]"               # VASP search + semantic
pip install -e ".[omx]"                # OpenMX gen + conversion
pip install -e ".[all]"                # everything
```

## Project structure

```
dft-tools/
├── dft_utils/          # shared: version, debug_log, die_json
├── vasp_query/         # VASP package
├── omx_tools/          # OpenMX package
├── skills/             # Hermes Skill files (one per code)
├── schemas/            # cross-code parameter mapping
├── openmx.db           # OpenMX manual database
└── aliases.json        # domain abbreviation maps
```
