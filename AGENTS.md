# Agent instructions

> Entrypoint only. Prefer repo docs and code over pretraining.  
> Adapters (`CLAUDE.md`) must not carry a second full rule body.  
> **Human start:** [`README.md`](README.md).

## Precedence

1. User’s current explicit message  
2. This file  
3. Linked docs (`docs/agent-conventions.md`, skills, package code)

## Always-on

- **What this is**: multi-code DFT **knowledge + input generation + conversion + advice on existing inputs** — `vasp_query/`, `omx_tools/`, `dft_utils/`, `omx_tools/semantic/`. **Not** a DFT engine.  
- **Goals**: (1) query docs/tags, (2) generate inputs, (3) convert VASP↔OpenMX via semantic IR, (4) **lint existing INCAR/`.dat` with structured suggestions**, (5) round-trip self-consistency. GT: pymatgen / vaspkit checklist / pydefect boundary.  
- **Install extras**: `pip install -e ".[vasp]"` | `".[omx]"` | `".[all]"`.  
- **CLIs**: `vasp-query`; `vasp-gen`; `omx-db`; `omx-gen`; `vasp2omx`/`omp2vasp`; `dft` including `dft semantic {show,lint,lint-omx,roundtrip,cross,show-omx}`.  
- **Data**: version envelope via `load_data()`; mismatch warns.  
- **Search**: VASP cascade + hybrid/rag; OpenMX FTS5/hybrid/rag/related/example.  
- **Tests**: real data preferred — `python3 -m vasp_query.test_cli`; `pytest tests/` (needs `openmx.db`).  
- **Do not invent** INCAR/OpenMX keyword meanings — query DBs; for advice use lint + cite `vasp-query`/`omx-db` in suggestions.  
- **Secrets**: no API keys in tree; wiki scrape is public.  

## Development commands

```bash
pip install -e ".[all]"

# VASP
vasp-query tag ENCUT
vasp-query search "hybrid functional"
python3 -m vasp_query.test_cli

# OpenMX
omx-db search "SCF convergence"
omx-gen structure.cif -t scf_band -o calc.dat
python3 -m pytest tests/
```

## Read on demand

| When | Read first |
|------|------------|
| Architecture, conventions, files | [`docs/agent-conventions.md`](docs/agent-conventions.md) |
| CLI detail / gotchas (ex-CLAUDE) | [`docs/agent-lessons.md`](docs/agent-lessons.md) |
| Adding a DFT code | [`docs/ADDING_A_CODE.md`](docs/ADDING_A_CODE.md) |
| Skills | `skills/vasp-query/SKILL.md`, `skills/omx-tools/SKILL.md` |
| Human overview | [`README.md`](README.md) |
| Migration / setup | [`docs/MIGRATION.md`](docs/MIGRATION.md) |
| Planned work | [`ROADMAP.md`](ROADMAP.md), [`PLAN.md`](PLAN.md), semantic IR [`docs/superpowers/specs/2026-07-14-semantic-roundtrip-design.md`](docs/superpowers/specs/2026-07-14-semantic-roundtrip-design.md), vaspkit GT [`docs/vaspkit-checklist.md`](docs/vaspkit-checklist.md) |

## Keep in sync

| Topic | Files |
|-------|--------|
| Agent rules | This file canonical; `CLAUDE.md` = short + `@AGENTS.md` |
| Knowledge data | regenerate scripts ↔ `vasp_query/data/` / `openmx.db` |
| Human README | install + quick start ↔ real entry points |
