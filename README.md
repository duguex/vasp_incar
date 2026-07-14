# DFT Tools — Knowledge, Inputs, Advice for DFT Codes

Bridge **natural language / agents** to DFT **knowledge**, **input generation**, **cross-code conversion**, and **advice on existing inputs**. **VASP** and **OpenMX** are first-class; the layout extends to QE, CASTEP, etc.

### Project goals

| Goal | What it means | Primary surface |
|------|----------------|-----------------|
| **Know** | Query manuals/wiki/tags without inventing parameters | `vasp-query`, `omx-db` |
| **Generate** | Templates → INCAR / `.dat` (+ optional KPOINTS/POTCAR) | `vasp-gen`, `omx-gen` |
| **Convert** | VASP ↔ OpenMX via semantic IR | `vasp2omx`, `omp2vasp`, `dft convert` |
| **Advise** | Review **existing** inputs; lint + **knowledge-backed** suggestions; optional safe fix loop | `dft semantic advise` / `gen-advise` |
| **Self-consistent map** | VASP ⇄ semantic ⇄ OpenMX under declared equivalence | `dft semantic roundtrip` / `cross` |
**Not a DFT engine** (does not run VASP/OpenMX). Heavy workflows stay with **pymatgen / vaspkit / pydefect** (GT + checklist).

```
User / Agent
        │
        ▼
   Skill + CLI (search, gen, convert, lint, semantic)
        │
   ┌────┴────┐
   ▼         ▼
vasp_query  omx_tools
   │         │
   └────┬────┘
        ▼
  semantic IR + mapping  ← lint / round-trip / cross-code
```

## Documentation roles

| Audience | File | Role |
|----------|------|------|
| Humans | This README | Install, quick start, structure |
| Coding agents | [AGENTS.md](AGENTS.md) | **Canonical** agent rules (short) |
| Claude Code | [CLAUDE.md](CLAUDE.md) | Adapter + `@AGENTS.md` — **not** a second rulebook |
| Deep conventions | [docs/agent-conventions.md](docs/agent-conventions.md) | Architecture & patterns |
| CLI / gotchas | [docs/agent-lessons.md](docs/agent-lessons.md) | Ex-CLAUDE detail |

## Currently integrated

| Code | Package | Knowledge | Input gen | Conversion | Advise existing inputs |
|------|---------|-----------|-----------|------------|------------------------|
| **VASP** | `vasp_query/` + semantic | tags + wiki + configs | `vasp-gen` | vasp2omx | `dft semantic lint` |
| **OpenMX** | `omx_tools/` | manual DB + examples | `omx-gen` | omp2vasp | `dft semantic lint-omx` |

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
vasp-query rag "hybrid functional ENCUT"
omx-db rag "how to tune SCF mixing for metallic systems"
omx-db example Kerker --json          # official OpenMX work/ examples
omx-db cooccur scf.Mixing.Type scf.Kerker.factor --json

# Semantic IR (round-trip / cross-code grade / lint)
dft semantic show INCAR
dft semantic lint INCAR              # physics/consistency suggestions
dft semantic roundtrip INCAR
dft semantic cross INCAR

# Generate inputs
# Advise loop: lint → knowledge → optional safe fix
dft semantic advise INCAR
dft semantic advise INCAR --fix -o INCAR.fixed
dft semantic gen-advise -t scf_metal    # generate then advise
dft semantic lint INCAR                # lint only (no knowledge fetch)
dft semantic roundtrip INCAR
dft semantic cross INCAR
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
