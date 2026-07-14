# CLI Symmetry Implementation Plan

> **For agentic workers:** Implement task-by-task. Spec: `docs/superpowers/specs/2026-07-14-cli-symmetry-design.md`.

**Goal:** Make VASP and OpenMX CLI surfaces symmetric: aliases, hybrid/rag, related, light `vasp-gen`.

**Architecture:** Thin wrappers over existing hybrid/embedding; OpenMX related via SQLite; new `vasp_query/generator.py` + templates JSON; `dft vasp gen` mirrors `dft omx gen`.

**Tech Stack:** Python 3.10+, existing `dft_utils.embedding` / `hybrid_search`, argparse, pytest.

## Global Constraints

- No fabricated OpenMX config corpus.
- `vasp-gen` writes **INCAR only** (no POTCAR/KPOINTS files).
- Keep backward-compatible entry points.
- JSON errors: `{"error","suggestion"}`.
- DATA_VERSION envelope `0.3.0` for new JSON data files.

---

### Task 1: CLI aliases

**Files:**
- Modify: `vasp_query/query.py` (argparse aliases + command map)
- Modify: `omx_tools/database.py` (alias map in `cli()`)
- Test: `vasp_query/test_cli.py`, `tests/test_unified_cli.py` or new tests

- [ ] VASP: `tag` aliases `keyword`; `fullwiki` aliases `section`
- [ ] OpenMX: `tag`→`keyword`, `fullwiki`→`section`
- [ ] Tests: subprocess invoke aliases

### Task 2: VASP hybrid + rag

**Files:**
- Modify: `vasp_query/query.py`
- Modify: `vasp_query/_common.py` if rag helper extracted
- Test: `vasp_query/test_cli.py`

- [ ] `cmd_hybrid` → `hybrid_search`, JSON (+ optional human/debug)
- [ ] `cmd_rag` → embed + `doc_vectors.npy` / `doc_meta`, top-k results with `query`/`count`/`results`
- [ ] Wire subparsers + commands dict

### Task 3: OpenMX related

**Files:**
- Modify: `omx_tools/database.py`
- Test: `tests/test_database.py` or new case

- [ ] `cmd_related`: section number → sibling sections + index keywords; keyword → same-section keywords
- [ ] JSON shape per spec

### Task 4: vasp-gen

**Files:**
- Create: `vasp_query/schemas/templates.json`
- Create: `vasp_query/generator.py`
- Modify: `vasp_query/plugin.py`, `pyproject.toml`, `dft_utils/cli.py`
- Test: `tests/test_vasp_gen.py` (new)

- [ ] Templates: scf, scf_metal, relax, band, md
- [ ] CLI: list-templates, -t, -o, -s, --spin, --cutoff, -d, -j
- [ ] Entry: `vasp-gen`, `dft vasp gen`
- [ ] package-data includes schemas

### Task 5: Docs + design-intent

**Files:** README, AGENTS, skills, WORKFLOWS, CHANGELOG, `tests/test_design_intent.py`

- [ ] Document symmetric surface
- [ ] Assert plugins list generators for both codes

### Task 6: Verify

- [ ] `pytest` targeted suites green
- [ ] Manual smoke: aliases, rag, related, vasp-gen, dft vasp gen
- [ ] Commit + push
