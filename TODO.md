# TODO

See `ROADMAP.md` for detailed planning.

## Current priority

1. [ ] Rebuild VASP data (`python3 -m vasp_query preprocess`)
2. [ ] Fix `_search_fts5` row_factory in `omx_tools/database.py`

## Next

3. [ ] Unify semantic search backend (Ollama) — `dft_utils/embedding.py`
4. [ ] Write workflow examples — `docs/WORKFLOWS.md`
5. [ ] Add third DFT code + standardize onboarding
6. [ ] Post-processing output parsers — `dft_utils/extract/`

## Known bugs (code)

- `omx_tools/database.py:_search_fts5()` missing `conn.row_factory = sqlite3.Row`
- `omx_tools/database.py:cmd_rag()` subprocess model load is ~9s cold, ~0 warm — should use same backend as hybrid search
- VASP data files at version 0.2.0 need regeneration to match code 0.3.0
