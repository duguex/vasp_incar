# Agent instructions

> Entrypoint only. Prefer repo docs and code over pretraining.  
> Adapters (`CLAUDE.md`) must not carry a second full rule body.  
> **Human start:** [`README.md`](README.md).

## Precedence

1. User’s current explicit message  
2. This file  
3. Linked docs (`docs/agent-conventions.md`, skills, package code)

## Always-on

- **What this is**: multi-code DFT **knowledge + input generation + conversion + advice on existing inputs** — `vasp_query/`, `omx_tools/`, `dft_utils/`, `omx_tools/semantic/`. Product CLIs are **not** a DFT engine or an integration dependency. Production verification is delegated through the CRISP Python facade; optional `scripts/*` may drive local container OpenMX/VASP for compatibility/testing only.
- **Goals**: (1) query docs/tags, (2) generate inputs, (3) convert via semantic IR, (4) **advise existing inputs** (`lint` + knowledge attach + optional safe fix loop), (5) round-trip self-consistency. GT: pymatgen / vaspkit / pydefect boundary.  
- **Install extras**: `pip install -e ".[vasp]"` | `".[omx]"` | `".[all]"`.  
- **CLIs**: `vasp-query`; `vasp-gen`; `omx-db`; `omx-gen`; converters; `dft semantic {show,lint,advise,gen-advise,advise-omx,roundtrip,cross,show-omx}`.  
- **Data**: version envelope via `load_data()`; mismatch warns.  
- **Search**: VASP cascade + hybrid/rag; OpenMX FTS5/hybrid/rag/related/example.  
- **Tests**: real data preferred — `python3 -m vasp_query.test_cli`; `pytest tests/` (needs `openmx.db`). Physics gates (when reports present): `python3 scripts/run_cross_gates.py --check-only`.  
- **Do not invent** INCAR/OpenMX keyword meanings — query DBs; for advice use lint + cite `vasp-query`/`omx-db` in suggestions. ENCUT↔`scf.energycutoff` is a **×2 heuristic**, not eV↔Ry physics.  
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

# Physics gates (no SCF if reports already present)
python3 scripts/run_cross_gates.py --check-only --elements Si C
```

## Read on demand

| When | Read first |
|------|------------|
| Domain vocabulary + settled architecture decisions | [`CONTEXT.md`](CONTEXT.md) |
| Architecture, conventions, files | [`docs/agent-conventions.md`](docs/agent-conventions.md) |
| CLI detail / gotchas (ex-CLAUDE) | [`docs/agent-lessons.md`](docs/agent-lessons.md) |
| Adding a DFT code | [`docs/ADDING_A_CODE.md`](docs/ADDING_A_CODE.md) |
| Skills | `skills/vasp-query/SKILL.md`, `skills/omx-tools/SKILL.md` |
| Human overview | [`README.md`](README.md) |
| Migration / setup | [`docs/MIGRATION.md`](docs/MIGRATION.md) |
| Workflows / engine verification | [`docs/WORKFLOWS.md`](docs/WORKFLOWS.md) §6–10, [`docs/benchmarks/`](docs/benchmarks/) |
| Planned work | [`ROADMAP.md`](ROADMAP.md), [`PLAN.md`](PLAN.md), semantic IR [`docs/superpowers/specs/2026-07-14-semantic-roundtrip-design.md`](docs/superpowers/specs/2026-07-14-semantic-roundtrip-design.md), vaspkit GT [`docs/vaspkit-checklist.md`](docs/vaspkit-checklist.md) |

## Keep in sync

| Topic | Files |
|-------|--------|
| Agent rules | This file canonical; `CLAUDE.md` = short + `@AGENTS.md` |
| Knowledge data | regenerate scripts ↔ `vasp_query/data/` / `openmx.db` |
| Human README | install + quick start ↔ real entry points |
