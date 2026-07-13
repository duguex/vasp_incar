# Agent instructions

> Entrypoint only. Prefer repo docs and code over pretraining.  
> Adapters (`CLAUDE.md`) must not carry a second full rule body.  
> **Human start:** [`README.md`](README.md).

## Precedence

1. User’s current explicit message  
2. This file  
3. Linked docs (`docs/agent-conventions.md`, skills, package code)

## Always-on

- **What this is**: multi-code DFT knowledge + input generation framework — packages `vasp_query/`, `omx_tools/`, shared `dft_utils/`. Not a DFT engine.  
- **Install extras**: `pip install -e ".[vasp]"` | `".[omx]"` | `".[all]"`.  
- **CLIs**: `vasp-query` (12 subcommands); `omx-db`, `omx-gen`, `vasp2omx`, `omp2vasp`.  
- **Data**: version envelope `{"_version": …, "data": …}` via `load_data()`; mismatch warns.  
- **Search**: VASP 4-tier cascade (`resolve_tag` → file page → hybrid FTS5+embeddings RRF → keyword); OpenMX FTS5/semantic/hybrid.  
- **Tests**: real data, no mocking of knowledge files — `python3 -m vasp_query.test_cli`; `python3 -m pytest tests/` (needs `openmx.db` at root).  
- **Do not invent** new INCAR tag semantics or OpenMX keyword meanings — query the DBs.  
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
| Planned work | [`ROADMAP.md`](ROADMAP.md), [`PLAN.md`](PLAN.md), [`TODO.md`](TODO.md) |

## Keep in sync

| Topic | Files |
|-------|--------|
| Agent rules | This file canonical; `CLAUDE.md` = short + `@AGENTS.md` |
| Knowledge data | regenerate scripts ↔ `vasp_query/data/` / `openmx.db` |
| Human README | install + quick start ↔ real entry points |
