# TODO

See `ROADMAP.md` for detailed planning. Status as of 2026-07-14.

## Done (v0.3.x)

1. [x] Rebuild VASP data / version envelopes (tag_index, wiki, etc.; aliases now 0.3.0)
2. [x] Fix `_search_fts5` `row_factory` in `omx_tools/database.py`
3. [x] Unify semantic search backend via `dft_utils.embedding` (Ollama + ST fallback)
4. [x] Workflow examples — `docs/WORKFLOWS.md`
5. [x] PLAN Phase 0–5 framework (plugin registry, `dft` CLI, convert registry, skeleton docs)
6. [x] Archive standalone `~/omx` → `~/archive/2026-07-dft-merge/omx`

## Current priority

1. [ ] Third DFT code (QE or CASTEP) to validate plugin protocol end-to-end
2. [ ] Post-processing output parsers — `dft extract` / `dft_utils.extract`

## Known polish / follow-ups

- Hybrid ranking for broad queries (e.g. `"SCF"`) still elevates Index; tune boosts further if needed
- Phase 4 partial: mapping JSON still under `omx_tools/schemas/` (not root `schemas/`); converters work via registry
- `dft convert` remainder-arg wiring fixed 2026-07-14 — keep covered by `tests/test_unified_cli.py`
