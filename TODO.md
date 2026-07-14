# TODO

See `ROADMAP.md` for detailed planning. Status as of 2026-07-14.

## Done (v0.3.x)

1. [x] Rebuild VASP data / version envelopes
2. [x] Fix `_search_fts5` `row_factory` in `omx_tools/database.py`
3. [x] Unify semantic search backend via `dft_utils.embedding`
4. [x] Workflow examples — `docs/WORKFLOWS.md`
5. [x] PLAN Phase 0–5 framework (plugin registry, `dft` CLI, convert registry)
6. [x] Archive standalone `~/omx` → `~/archive/2026-07-dft-merge/omx`
7. [x] Advise loop + Si8 E2E (`dft semantic advise` / `e2e_si8_advise_loop.py`)
8. [x] Engine self-tests + true cross-engine examples
9. [x] Cross ΔE Ecoh (Si, C) + **physics gates** (`run_cross_gates.py`)
10. [x] KS eigenvalues Si/C + light a_eq + crystal force gates

## Optional / backlog (not current focus)

1. [ ] Third DFT code (QE or CASTEP) — only when extending the plugin story
2. [ ] Post-processing output parsers — `dft extract` / `dft_utils.extract`
3. [ ] Policy-driven defaults for gen (shared rules with advise)
4. [ ] Light EOS / a_eq cross-check

## Known polish / follow-ups

- Hybrid ranking for broad queries (e.g. `"SCF"`) may still elevate Index pages
- Phase 4 partial: mapping JSON still under `omx_tools/schemas/` (not root `schemas/`)
- ENCUT ↔ `scf.energycutoff` is a **×2 heuristic**, not physical eV↔Ry equivalence
- Keep `tests/test_unified_cli.py` covering `dft convert` remainder args

## Verification commands

```bash
pytest tests/ -q
python3 scripts/run_cross_gates.py --check-only --elements Si C
```
