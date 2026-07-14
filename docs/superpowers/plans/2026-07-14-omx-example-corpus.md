# Plan: OpenMX Official Example Corpus (stats / cooccur / example)

**Date:** 2026-07-14  
**Status:** Planned (not implemented)  
**Depends on:** local OpenMX tree with `work/**/*.dat` (default `~/openmx_container/openmx4.0/work`)  
**Spec intent:** CLI symmetry follow-up — OpenMX side “real config corpus” analogue of VASP `incar`/`stats`/`cooccur`.

---

## 1. Goal

Index **official OpenMX `.dat` examples** into a queryable corpus so agents can:

| Command (proposed) | Purpose |
|--------------------|---------|
| `omx-db example <query>` | Find example inputs by keyword / path / intent tag |
| `omx-db stats [keyword]` | Frequency of keywords / common values across examples |
| `omx-db cooccur <kw_a> <kw_b>` | Co-occurrence of two keywords in the same `.dat` |

**Corpus character:** *official demonstration set* (~300–500 unique inputs), **not** a large multi-user INCAR dump. Docs must say so.

---

## 2. Data sources (priority order)

| Priority | Source | Notes |
|----------|--------|-------|
| **P0** | `~/openmx_container/openmx4.0/work/**/*.dat` | Already on disk: **~511 files / ~323 unique basenames**; includes `input_example/`, `geoopt_example/`, `negf_example/`, `large_*`, `ml_example`, … |
| **P1** | Manual §78 “Included input examples” cross-links | Optional enrichment (title ↔ file) |
| **P2** | OpenMX website / workshop tarballs | Incremental; do **not** block P0 |

**Out of scope for v1:** scraping user HPC histories; shipping binary DB built from non-redistributable paths without a rebuild script.

---

## 3. Architecture

```
openmx_container/.../work/**/*.dat
            │
            ▼
   scripts/index_omx_examples.py
     - walk + hash dedupe
     - parse via omx_tools.parsers.openmx.parse_dat
     - intent heuristic (path + keywords)
            │
            ▼
   data/omx_examples/  (or repo root)
     examples_index.json   {_version, data: [records]}
     examples_stats.json   {_version, data: {kw: {...}}}
     examples_cooccur.json optional
            │
            ▼
   omx_tools/database.py  (or omx_tools/examples.py)
     cmd_example / cmd_stats_examples / extend stats / cmd_cooccur
```

Prefer **JSON + version envelope** first (match vasp_query data style). SQLite optional later if size grows.

### Record schema (v1)

```json
{
  "id": "geoopt_example/Methane_DIIS.dat",
  "path": "/abs/or/relative",
  "sha256": "...",
  "intent": "geom_opt",
  "keywords": {"scf.XcType": "GGA-PBE", "scf.Kgrid": [2,2,2], "...": "..."},
  "keyword_names": ["scf.XcType", "scf.Kgrid", "..."],
  "source": "openmx4.0/work",
  "bytes": 1234
}
```

### Intent heuristic (v1, path-first)

| Path / signal | intent |
|---------------|--------|
| `geoopt_example`, `cellopt_example` | `geom_opt` |
| `negf_example` | `negf` |
| `ml_example` | `md` / `ml` |
| `force_example` | `force` |
| `*Band*`, `scf.restart` | `band` |
| default | `scf` |

Refine with keyword presence later (`MD.Type`, `NEGF.*`).

---

## 4. CLI design

### 4.1 `omx-db example`

```bash
omx-db example "Kerker" --json
omx-db example --intent geom_opt --json
omx-db example --keyword scf.Mixing.Type --json
```

Output:
```json
{
  "query": "Kerker",
  "count": N,
  "results": [
    {"id": "...", "intent": "scf", "matches": ["scf.Mixing.Type"], "path": "..."}
  ]
}
```

### 4.2 `omx-db cooccur` (OpenMX)

```bash
omx-db cooccur scf.Mixing.Type scf.Kerker.factor --json
```

Mirror VASP fields where sensible: `count_a`, `count_b`, `cooccur_count`, `total_configs`, `top_pairs` (value pairs if both scalar).

### 4.3 `omx-db stats` extension

**Option A (recommended):** keep current DB table `stats` as-is; add:

```bash
omx-db stats --examples [keyword]
```

**Option B:** separate `omx-db exstats`. Prefer A to avoid command sprawl.

When examples index missing → error + suggestion to run indexer.

---

## 5. Indexer CLI

```bash
python3 scripts/index_omx_examples.py \
  --root ~/openmx_container/openmx4.0/work \
  --out data/omx_examples \
  --verbose
```

Acceptance:
- Idempotent rebuild
- Dedup by sha256 (keep shortest relative path as id)
- Skip unreadable files with warning count
- Writes `_version: "0.3.0"` envelopes

Config env (optional): `OPENMX_EXAMPLES_ROOT`.

---

## 6. Implementation tasks (when approved)

| # | Task | Files | Est. |
|---|------|-------|------|
| A1 | Indexer script + JSON outputs | `scripts/index_omx_examples.py`, `data/omx_examples/*` | 2–3 h |
| A2 | Loader helpers | `omx_tools/examples_corpus.py` | 1 h |
| A3 | `cmd_example` + wire CLI | `omx_tools/database.py` | 1 h |
| A4 | `cmd_cooccur` for examples | same | 1–2 h |
| A5 | `stats --examples` | same | 1 h |
| A6 | Tests with **fixture mini-corpus** (3–5 tiny `.dat` under `tests/fixtures/omx_examples/`) — do not depend on `~/openmx_container` in CI | `tests/test_omx_examples.py` | 1–2 h |
| A7 | Docs: README, skills, WORKFLOWS, CHANGELOG; note corpus = official examples | docs | 0.5 h |

**Total:** ~1 day focused work.

### Test strategy

- Unit-test indexer on `tests/fixtures/omx_examples/*.dat` (hand-written minimal inputs).
- Optional `@pytest.mark.integration` if `OPENMX_EXAMPLES_ROOT` exists (full work/ tree).
- Never require workshop download in default pytest.

---

## 7. Non-goals (v1)

- Workshop web scraper
- Embedding search over full `.dat` bodies (can add later via `dft_utils.embedding`)
- Claiming statistical parity with VASP’s 10k INCAR corpus
- Shipping someone else’s full OpenMX tree inside `vasp_wiki` git (generate locally; gitignore large dumps or commit only compact JSON index if license-ok)

**License note:** OpenMX examples are part of the OpenMX distribution; redistributing raw `.dat` inside this repo needs a quick license check. Safer: **commit indexer + tiny fixtures + generated compact JSON index only if redistribution is clearly allowed**; otherwise generate index on install/first run.

---

## 8. Success criteria

- [ ] `index_omx_examples.py` builds index from default work/ root  
- [ ] `omx-db example` returns ≥1 hit for a known keyword present in fixtures  
- [ ] `omx-db cooccur` returns structured counts  
- [ ] `omx-db stats --examples` shows top keywords  
- [ ] Docs state corpus provenance (official work/ examples)  
- [ ] Default tests green without `openmx_container`

---

## 9. Suggested execution order

1. A6 fixtures first (TDD)  
2. A1 indexer against fixtures  
3. A2–A5 CLI  
4. Run indexer once on full `work/` for local agent use  
5. A7 docs  

---

## 10. Open decisions (for implementer / user)

| Decision | Default recommendation |
|----------|------------------------|
| Commit full-tree JSON index to git? | **No** if large; commit fixtures + optional small committed sample index |
| Command name `example` vs `examples` | `example` (verb-like, match `tag`) |
| Merge into existing `stats` vs flag | `--examples` flag |
| Workshop scrape in v1? | **No** |

---

## 11. Relation to completed work

- **B done:** `vasp-gen` KPOINTS/POTCAR/POSCAR (`b3ee54b`)  
- **A next:** this plan — implement when user says go  
