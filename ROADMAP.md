# Future Work — dft-tools Roadmap

Current: `dft-tools v0.3.0` — framework ready, two DFT code plugins (VASP, OpenMX).

Status refreshed: **2026-07-14**. Items 1–4 below are **done**; remaining work starts at Item 5.

---

## Done

### Item 1: Rebuild VASP data — done

Data files under `vasp_query/data/` use `_version: 0.3.0` envelopes (including `aliases.json`).

### Item 2: Fix `_search_fts5` row_factory — done

`omx_tools/database.py` sets `sqlite3.Row`; hybrid debug shows `FTS5: N hits`. Covered by `tests/test_regressions.py`.

### Item 3: Unify semantic search backend — done

`dft_utils/embedding.py` with Ollama primary + sentence-transformers fallback. Both VASP hybrid search and OpenMX semantic/RAG use `embed()` / `embed_numpy()`.

### Item 4: End-to-end workflow examples — done

`docs/WORKFLOWS.md` + README links. Framework docs: `docs/ADDING_A_CODE.md`, `dft_utils/templates/code_skeleton/`.

### Framework (PLAN Phase 0–5) — done

Shared `dft_utils` (search, embedding, protocol, CLI, convert, error, version), plugins for `vasp`/`omx`, unified `dft` CLI, converter registry, agent docs.

---

## Item 5: Add third DFT code + harden onboarding (～3-5 days)

### Goal

Add **Quantum ESPRESSO** or **CASTEP** as the third plugin to validate extensibility.

### Standardization deliverables

| Artifact | What to add |
|----------|-------------|
| `docs/ADDING_A_CODE.md` | Gotchas from third integration |
| `dft_utils/templates/code_skeleton/` | Fill gaps found in practice |
| `dft_utils/protocol.py` | Any missing `CodePlugin` fields |
| `dft_utils/cli.py` | New subcommand patterns if needed |
| `pyproject.toml` | Third package include |
| `AGENTS.md` | Extension lessons |

### Suggested first target: Quantum ESPRESSO

**Minimal:** PWscf variable table → FTS5; `dft qe search "ecutwfc"`; register plugin.  
**Full:** parser/writer, ASE-mediated convert, `qe-gen`.

### Acceptance

```bash
dft --list-codes | grep qe
dft qe search "ecutwfc"
# optional full:
dft convert qe:vasp pw.in -o INCAR
```

---

## Item 6: Post-processing (～1 week)

### Goal

Output analysis: energy, forces, stress, SCF traces.

```
dft_utils/extract/   # or top-level extract/
  vasp.py            # OUTCAR, OSZICAR, vasprun.xml
  openmx.py          # .EV, .md, .ene
```

### CLI sketch

```bash
dft extract vasp:outcar OUTCAR --json
dft extract omx:ev Si8.EV --json
```

Reuse ideas from `legacy_scripts/` INCAR/OUTCAR parsers. Can proceed in parallel with Item 5.

---

## Optional polish

| Item | Notes |
|------|--------|
| Root `schemas/` move | PLAN Phase 4 leftover; converters already registered |
| Hybrid ranking | Broad terms still rank Index high |
| GitHub rename | Remote still `vasp_incar`; local dir `vasp_wiki` |

---

## Summary

| # | Item | Status |
|---|------|--------|
| 1 | Rebuild VASP data | **done** |
| 2 | FTS5 row_factory | **done** |
| 3 | Ollama embedding unify | **done** |
| 4 | Workflow examples | **done** |
| 5 | Third DFT code | **open** |
| 6 | Post-processing extract | **open** |
