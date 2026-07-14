# Design: VASP ↔ OpenMX CLI Capability Symmetry

**Date:** 2026-07-14  
**Status:** Approved for implementation planning  
**Package:** `dft-tools` 0.3.x (`~/vasp_wiki`)  
**Approach:** A — command-surface mirror + shared protocol + light `vasp-gen`

---

## 1. Problem

VASP and OpenMX plugins share a monorepo framework but expose **asymmetric CLIs**:

| Capability | VASP today | OpenMX today |
|------------|------------|--------------|
| Knowledge search | `search` (hybrid inside) | `search`, `hybrid`, `rag` |
| Param lookup | `tag` | `keyword` |
| Full text unit | `fullwiki` | `section` |
| Related | `related` | — |
| Stats / list | yes | yes |
| Real-config corpus | `incar`, `stats`, `cooccur` | — (no corpus) |
| Input generation | — (removed historically) | `omx-gen` |
| Cross convert | `vasp2omx` | `omp2vasp` |

Agents and humans cannot assume a parallel command map. Goal is **CLI capability symmetry**, not identical internal data models.

---

## 2. Goals

1. Same **logical command set** on both codes where meaningful:
   `search`, `hybrid`, `rag`, `tag`↔`keyword`, `section`↔`fullwiki`, `list`, `stats`, `related`, `gen`, plus shared `dft convert`.
2. Light **`vasp-gen`**: structure optional + templates → **INCAR only** (not POTCAR/KPOINTS workflow).
3. Keep **backward compatibility** for existing entry points and subcommands.
4. Unified `dft vasp|omx <cmd>` routing mirrors native CLIs.
5. Tests prove symmetry of **dispatch and happy paths**, not fake OpenMX corpora.

## 3. Non-goals

- Fabricating OpenMX real-input corpora for `incar` / `cooccur`.
- Restoring heavy historical `incar-gen` or full VASP input suites.
- Post-processing (`dft extract` / OUTCAR / `.EV`) — separate roadmap item.
- Third DFT code (QE/CASTEP).
- Moving mapping JSON to root `schemas/` (unrelated cleanup).
- Perfect ranking quality for hybrid/rag (only expose + contract stability).

---

## 4. Command matrix (target)

| Logical cmd | `dft vasp …` / `vasp-query` | `dft omx …` / `omx-db` | Notes |
|-------------|----------------------------|------------------------|--------|
| `search` | existing | existing | keep |
| `hybrid` | **add** explicit subcommand | existing | VASP may delegate to current hybrid path |
| `rag` | **add** | existing | semantic top-k snippets |
| `tag` | existing | **alias → keyword** | |
| `keyword` | **alias → tag** | existing | |
| `fullwiki` | existing | **alias → section** | |
| `section` | **alias → fullwiki** | existing | |
| `list` | existing | existing | |
| `stats` | existing | existing | different payload OK |
| `related` | existing | **add** | OpenMX: keyword/section neighbors |
| `gen` | **add `vasp-gen`** | `omx-gen` | INCAR vs `.dat` |
| `incar` / `cooccur` | existing | **not added** | `dft omx incar` → clear error + suggestion |
| `convert` | `dft convert vasp:omx` | `dft convert omx:vasp` | already bidirectional |

Native CLIs keep old names; aliases are additive.

---

## 5. Architecture

```
User / Agent
    │
    ├─ vasp-query <cmd>          omx-db <cmd>
    ├─ vasp-gen                  omx-gen
    └─ dft {vasp|omx|convert}
            │
    ┌───────┴────────┐
    ▼                ▼
vasp_query/       omx_tools/
  query.py          database.py
  generator.py NEW  generator.py
  plugin.py         plugin.py
    │                │
    └───────┬────────┘
            ▼
      dft_utils/  (embedding, search.rrf_merge, error, cli)
```

**Principles:**
- Prefer thin wrappers over duplicated search engines.
- Aliases resolved inside each package’s CLI dispatcher (not only in `dft`).
- Generators register on `CodePlugin.generators`.
- JSON error shape remains `{"error","suggestion"}` with non-zero exit.

---

## 6. Feature specs

### 6.1 VASP `hybrid`

- **CLI:** `vasp-query hybrid <query> [--json] [--debug]`
- **Behavior:** Call existing hybrid search used by `search` (FTS5 + embeddings RRF). Do not invent a second ranker.
- **Output:** Same family as `search` results list: items with id/title/score/source fields already used by hybrid enrichment.
- **dft:** `dft vasp hybrid "..."`

### 6.2 VASP `rag`

- **CLI:** `vasp-query rag <query> [--json] [--top-k N]`
- **Behavior:**
  1. Embed query via `dft_utils.embedding.embed`.
  2. Score against existing VASP document/tag vectors (`doc_vectors.npy` / metadata).
  3. Return top-k passages: `{title, score, snippet|description, url?}` .
- **Output (JSON):**
  ```json
  {
    "query": "...",
    "count": 5,
    "results": [
      {"title": "ENCUT", "score": 0.42, "snippet": "...", "url": "https://vasp.at/wiki/..."}
    ]
  }
  ```
- Align field names with `omx-db rag` where practical (`query`, `count`, `results`); omx-specific keys (`sec_num`) remain omx-only.
- **dft:** `dft vasp rag "..."`

### 6.3 OpenMX `related`

- **CLI:** `omx-db related <query> [--json]`
- **Query forms:**
  - Keyword name (e.g. `scf.Mixing.Type`) → other keywords in same manual sections + index neighbors.
  - Section number (e.g. `16` or `16.1`) → sibling/child sections from `sections` table + index entries pointing at that section.
- **Output (JSON):**
  ```json
  {
    "query": "scf.Mixing.Type",
    "count": N,
    "related": [
      {"kind": "keyword"|"section", "id": "...", "title": "...", "reason": "same_section"|"index"}
    ]
  }
  ```
- Empty result: `count: 0` with optional `suggestion`.
- **dft:** `dft omx related ...`

### 6.4 Aliases

| Package | Alias | Target |
|---------|-------|--------|
| vasp-query | `keyword` | `tag` |
| vasp-query | `section` | `fullwiki` |
| omx-db | `tag` | `keyword` |
| omx-db | `fullwiki` | `section` |

Aliases are first-class argv tokens in the command map (same flags as target).

### 6.5 `vasp-gen` (light INCAR templates)

**Entry points:**
- Console: `vasp-gen`
- Module: `vasp_query.generator:cli`
- Unified: `dft vasp gen …`
- Plugin: `generators=["vasp-gen"]`

**CLI shape (mirror omx-gen where sensible):**
```text
vasp-gen [structure] -t TEMPLATE -o INCAR
vasp-gen --list-templates
vasp-gen --list-keywords   # optional thin list from tag_index titles or skip if costly
vasp-gen POSCAR -t relax -s ENCUT=520 --spin 2 -d -j
```

**Flags (minimum):**
| Flag | Meaning |
|------|---------|
| `structure` | optional POSCAR/CIF/XYZ (ASE if available) |
| `-t/--template` | template id (default `scf`) |
| `-o/--output` | INCAR path |
| `-s/--set KEY=VAL` | override tags (repeatable) |
| `--spin` | map to ISPIN 1/2 |
| `--cutoff` | ENCUT eV |
| `-d/--dry-run` | stdout |
| `-v/--verbose` | stderr notes |
| `-j/--json` | machine-readable tag dict |
| `--list-templates` | list ids + descriptions |

**Templates file:** `vasp_query/schemas/templates.json`  
Envelope: `{"_version": "0.3.0", "data": { ... }}`

| id | Purpose | Core tags (illustrative) |
|----|---------|---------------------------|
| `scf` | static SCF | NSW=0, IBRION=-1, ISMEAR=0, SIGMA=0.05, EDIFF=1e-5, PREC=Accurate |
| `scf_metal` | metallic SCF | ISMEAR=1, SIGMA=0.2, NSW=0, … |
| `relax` | ionic relaxation | IBRION=2, ISIF=2, NSW=100, EDIFFG=-0.02, … |
| `band` | static for bands | NSW=0, ICHARG=11 comment/note in verbose, … |
| `md` | AIMD skeleton | IBRION=0, MDALGO=2, POTIM=1.0, NSW=1000, … |

**Behavior rules:**
- Output **only INCAR** (never silent POTCAR/KPOINTS writes).
- If structure provided: may add comment lines (`# formula`, atom count) when safe; structure parse failure → JSON error + suggestion.
- Unknown template → error + list available templates in suggestion.
- No requirement on `OPENMX_DFT_DATA_PATH`.
- Optional ASE dependency under existing `gen` or `vasp` extras; pure INCAR path works without structure.

**Writer:** simple deterministic INCAR serializer (tag order: template order then overrides). Prefer small local writer over pymatgen dependency for gen core; pymatgen remains optional elsewhere.

### 6.6 Unified CLI (`dft_utils/cli.py`)

- Extend `cmd_code` so `dft vasp gen …` imports `vasp_query.generator` (symmetric to `dft omx gen` → `omx_tools.generator`).
- No change to convert remainder-arg design already shipped.

### 6.7 Explicit omissions (must fail clearly)

If user runs unsupported corpus commands on OpenMX:
```text
dft omx incar ...
→ exit ≠ 0
{"error": "OpenMX has no real-input config corpus",
 "suggestion": "Use omx-db search/related, or vasp-query incar for VASP configs"}
```
Only required if we add a shared command table that would otherwise route unknown cmds; if omx CLI simply has no `incar` subcommand, argparse unknown-command is acceptable **if** message is understandable. Prefer explicit handler when implementing a shared command allowlist.

---

## 7. Files to touch (implementation)

| Path | Action |
|------|--------|
| `vasp_query/query.py` | add `hybrid`, `rag`; aliases `keyword`, `section` |
| `vasp_query/_common.py` | helpers for rag scoring if needed |
| `vasp_query/generator.py` | **new** vasp-gen |
| `vasp_query/schemas/templates.json` | **new** |
| `vasp_query/plugin.py` | `generators=["vasp-gen"]` |
| `vasp_query/test_cli.py` | tests for new cmds / aliases |
| `omx_tools/database.py` | `related`; aliases `tag`, `fullwiki` |
| `tests/test_*.py` | omx related + generator + unified CLI gen |
| `dft_utils/cli.py` | `dft vasp gen` dispatch |
| `pyproject.toml` | `vasp-gen` script entry |
| `README.md`, `AGENTS.md`, skills, `docs/WORKFLOWS.md`, `CHANGELOG.md` | document symmetry |

---

## 8. Testing strategy

1. **Unit / CLI subprocess** (existing style in `vasp_query/test_cli.py`, `tests/test_unified_cli.py`):
   - aliases dispatch without "unknown command"
   - `vasp-query rag ENCUT` → `count >= 1` when vectors present
   - `vasp-query hybrid "energy cutoff"` → results non-empty or structured empty
   - `omx-db related 16` → related sections/keywords
   - `vasp-gen --list-templates` includes `scf`, `relax`
   - `vasp-gen -t scf -d` stdout contains `ENCUT` or `NSW`
   - `dft vasp gen -t scf -d` return code 0
2. **Design-intent:** extend `tests/test_design_intent.py` with a small symmetry class asserting both plugins advertise `gen` and both support rag entry points.
3. **No network** in default tests; no requirement to fetch wiki.

---

## 9. Documentation & skills

- README capability table: VASP Input gen → ✅ light templates (`vasp-gen`).
- `skills/vasp-query/SKILL.md`: document `rag`, `hybrid`, `vasp-gen`, aliases.
- `skills/omx-tools/SKILL.md`: document `related`, aliases.
- `docs/WORKFLOWS.md`: one VASP template path + existing OpenMX path side-by-side.
- CHANGELOG `[Unreleased]`.

---

## 10. Implementation order

1. Aliases (both packages) — lowest risk  
2. VASP `hybrid` + `rag`  
3. OpenMX `related`  
4. `vasp-gen` + templates + entry point + plugin + `dft vasp gen`  
5. Docs + design-intent symmetry tests  

Each step is independently committable and test-gated.

---

## 11. Acceptance criteria

- [ ] Command matrix in §4 implemented (except explicit non-goals).
- [ ] `vasp-gen -t scf -d` prints a valid-looking INCAR.
- [ ] `dft vasp gen` and `dft omx gen` both work.
- [ ] `vasp-query rag` and `omx-db rag` both return JSON with `query`/`count`/`results` (or omx equivalent results list).
- [ ] `omx-db related` returns structured related list for at least one known section and one keyword.
- [ ] Aliases work on both CLIs.
- [ ] Pre-commit / targeted pytest green.
- [ ] README + skills updated so agents see symmetric surfaces.

---

## 12. Risks & mitigations

| Risk | Mitigation |
|------|------------|
| VASP rag vector/metadata shape mismatch | Reuse preprocess outputs only; skip/fail with suggestion if files missing |
| Template INCAR bikeshedding | Keep 5 templates minimal; overrides via `--set` |
| Alias confusion in help text | List aliases in help epilog; skills document mapping |
| Scope creep into KPOINTS/POTCAR | Spec forbids; review rejects such PRs |

---

## 13. Decisions log

| Decision | Choice |
|----------|--------|
| Symmetry layer | CLI commands, not identical data backends |
| VASP generation | Light INCAR templates only |
| OpenMX corpus cmds | Not stubbed |
| Approach | A (command mirror + light vasp-gen) |
| Approved | 2026-07-14 by user |
