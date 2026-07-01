# Future Work — dft-tools Roadmap

Current: `dft-tools v0.3.0` — framework ready, two DFT code plugins (VASP, OpenMX).

---

## Item 1: Rebuild VASP data (～5 min)

The data files in `vasp_query/data/` are version `0.2.0` while the code is `0.3.0`.
Every CLI call prints warnings and the `aliases.json` version check fails in tests.

```bash
python3 -m vasp_query preprocess
```

**Acceptance:** `python3 -m vasp_query tag ENCUT` shows no warnings; aliases test
generates no UserWarning.

**Risk:** The preprocessor may fail if `data/raw/incar_data.json` or
`data/raw/vasp_wiki_all_data.json` have drifted. If they're stale, may need a
`python3 -m vasp_query fetch` first (hits vasp.at — internet required).

---

## Item 2: Fix `_search_fts5` in `omx_tools/database.py` (～15 min)

The `_search_fts5()` function (line 309) and `_search_semantic()` line 348)
connect to the database without setting `conn.row_factory = sqlite3.Row`.
This causes FTS5 results to be tuples instead of dicts, breaking downstream
code that accesses by column name (e.g. `r["sec_num"]`, `r["title"]`).

**Impact:** `cmd_search` and `cmd_hybrid` produce the `"FTS5 error: tuple
indices must be integers or slices, not str"` message in debug logs and fall
back to semantic-only results silently.

**Fix:** Add `db.row_factory = sqlite3.Row` after each `sqlite3.connect()`
call in `_search_fts5()` and `_search_semantic()` (both in `database.py`).

**Acceptance:** `omx-db hybrid "SCF" --json --debug` shows `"FTS5: ... hits"`
instead of `"FTS5 error: tuple indices..."`.

---

## Item 3: Unify semantic search backend — Ollama embeddings (～2-3 days)

**Current state:** Two independent SentenceTransformer setups:

| | vasp_query | omx_tools |
|---|---|---|
| Backend | In-process `SentenceTransformer('BAAI/bge-small-en-v1.5')` | Subprocess `python3 -c "from sentence_transformers ..."` |
| Cold start | ~15s (model load) | ~9s (subprocess import) |
| Cache | Module-level `_MODEL_CACHE` global | OS-level (subprocess exits after each query) |
| Model | BGE-small-en-v1.5 (384-dim) | Same model |

**Target:** Both packages query a local Ollama instance for embeddings.

```
dft_utils/
└── embedding.py          ← single embedding client

    embed(text) → list[float]
        Uses ollama Python library (ollama>=0.4) to call local model.
        Falls back to sentence-transformers if ollama unavailable.

    EmbeddingConfig:
        backend: "ollama" | "sentence_transformers" | "subprocess"
        model: str = "nomic-embed-text" or "bge-m3"
        ollama_url: str = "http://localhost:11434"
```

### Why Ollama

- Single model server shared by all processes — no more duplicate model loading
- `nomic-embed-text` (768-dim) or `bge-m3` (1024-dim) support multilingual + up to 8192 tokens
- No Python GIL contention for model inference
- Existing data files (`.npy` embeddings at 384-dim) need re-indexing if model changes — can batch via `embedding.py`

### Migration plan

1. **Create `dft_utils/embedding.py`**
   - `EmbeddingClient` class with abstracted backend
   - `ollama` Python client as primary backend
   - `sentence_transformers` as fallback
   - Dimension-agnostic: output is always `list[float]`

2. **Rebuild VASP embedding index**
   - `python3 -m vasp_query preprocess` already rebuilds `doc_vectors.npy`
   - Swap the embedding call in `processor.py:build_search_indexes()` to use `dft_utils.embedding`

3. **Rebuild OpenMX embedding index**
   - `section_embeddings` table in `openmx.db` was built by `scripts/extract_keywords.py`
   - Need a similar rebuild script that uses `dft_utils.embedding`

4. **Update hybrid search**
   - `vasp_query/_common.py:hybrid_search()` — replace in-process SentenceTransformer with `dft_utils.embedding`
   - `omx_tools/database.py:_search_semantic()` — replace subprocess with `dft_utils.embedding`
   - Both now share the same client and model, eliminating the subprocess hack

5. **Remove subprocess semantic search**
   - Delete the inline Python script in `_search_semantic()`
   - Cold start becomes ~1s (Ollama keeps model in memory)

### Acceptance

```bash
# Both packages use the same embedding
python3 -c "from dft_utils.embedding import embed; print(len(embed('test')))"
# → 768 (or whatever the model dim is)

# Hybrid search shows no model-load latency on second query
omx-db hybrid "SCF convergence" --json   # first call: ~1s
omx-db hybrid "mixing parameters" --json  # second call: <200ms
```

### Risk

- Ollama must be installed and running (`ollama serve`). Need clear error message
  when it's not available.
- Embedding dimension changes require re-indexing all `.npy` and DB tables.
  `nomic-embed-text` is 768-dim vs current 384-dim — the `.npy` files grow ~2×.
- If user doesn't have Ollama, `sentence_transformers` fallback preserves
  functionality but keeps the cold-start problem.

---

## Item 4: End-to-end workflow examples (～1 day)

Write a `docs/WORKFLOWS.md` with real scenarios:

1. **VASP → OpenMX migration**
   ```bash
   # User has a working VASP INCAR for a Si bandstructure calculation
   python3 -m vasp_query tag ENCUT        # check cutoff energy docs
   python3 -m vasp_query search "band structure Si"  # find setup tips
   vasp2omx INCAR POSCAR -o Si.dat        # convert to OpenMX
   omx-gen POSCAR -t band_dispersion -k 4 4 4 -o Si_bands.dat  # or generate fresh
   ```

2. **Cross-code concept lookup**
   ```bash
   # "How do I set up DFT+U in both codes?"
   python3 -m vasp_query search "DFT+U Hubbard"
   omx-db search "Hubbard U LDA+U"
   ```

3. **Natural language → calculation**
   ```bash
   # "Run an SCF calculation for this structure with default parameters"
   omx-gen input.cif -t scf_band -o calc.dat
   ```

4. **Troubleshooting convergence**
   ```bash
   omx-db rag "my SCF isn't converging for a metallic system"
   python3 -m vasp_query search "charge sloshing" --debug
   ```

Also update `README.md` to link to this file from the quick-start section.

---

## Item 5: Add third DFT code + standardize onboarding (～3-5 days)

### Goal

Add **Quantum ESPRESSO** or **CASTEP** as the third plugin to validate the
framework's extensibility.  This will uncover gaps in the plugin protocol,
the template skeleton, and the onboarding docs.

### Standardization deliverables

Based on experience adding the third code, update:

| Artifact | What to add |
|----------|-------------|
| `docs/ADDING_A_CODE.md` | Concrete gotchas discovered during the third integration |
| `dft_utils/templates/code_skeleton/` | Fill gaps found during the process |
| `dft_utils/protocol.py` | Add any missing fields to `CodePlugin` |
| `dft_utils/cli.py` | Handle any new subcommand patterns |
| `pyproject.toml` | Add third code to `packages.find` |
| `AGENTS.md` | Updated extension section with real lessons learned |

### Suggested first target: Quantum ESPRESSO

**Why:** Open-source, widely used, has a Python API (`ase` can parse its input),
and has an HTML/PDF manual that can be indexed the same way as OpenMX.

**Minimal scope (1-2 days):**
- Knowledge base: index the PWscf input variable table (from theQE manual) → FTS5 DB
- Query CLI: `dft qe search "ecutwfc"` returns variable description
- Plugin: register `qe` code

**Full scope (3-5 days):**
- Parser: `pw.x` input file → typed dict
- Writer: typed dict → `pw.x` input file
- Converter: QE → VASP and QE → OpenMX (via ASE intermediate)
- Generator: `qe-gen` from structure file

### Acceptance

```bash
dft --list-codes | grep qe
# → qe  Quantum ESPRESSO   ...

dft qe search "ecutwfc"
# → {"results": [...], "count": 5}

dft convert qe:vasp pw.in POSCAR -o INCAR
```

---

## Item 6: Post-processing (～1 week)

### Goal

Extend the framework beyond input generation to **output analysis** — extract
convergence data, energy trends, forces, and properties from calculation results.

### Architecture

```
dft_tools/
└── extract/                 ← new shared package
    ├── __init__.py            registry for output parsers
    ├── vasp.py                OUTCAR, OSZICAR, vasprun.xml parsers
    └── openmx.py              .EV, .md, .ene parsers
```

Each code's output parser registers with `dft_utils.extract`:

```python
from dft_utils.extract import register
register("vasp", "outcar", parse_outcar)
register("omx", "ev", parse_ev)
```

### What to extract (per code)

| Property | VASP source | OpenMX source |
|----------|------------|---------------|
| Total energy | OUTCAR `energy(sigma->0)` | `.EV` `Utot` |
| Forces | OUTCAR `TOTAL-FORCE` | `.md` `Total Force` |
| Stress | OUTCAR `in kB` | `.md` `Total Stress` |
| SCF convergence | OSZICAR (dE per step) | `.ene` `dE` |
| Timing | OUTCAR `LOOP+` | `.EV` `elapsed_time` |

### CLI

```bash
dft extract vasp:outcar OUTCAR --json
# → {"energy": -123.45, "forces": [...], "stress": [...], "scf_steps": 12, "wall_time": "34.2s"}

dft extract omx:ev Si8_test.EV --json
# → {"energy": -456.78, "scf_steps": 16}
```

### Reuse existing work

The `legacy_scripts/` directory already has scripts that parse INCAR and
OUTCAR.  The `extract_incar.py` and `incar.py` logic can inform the design
of `dft_utils.extract`.

### Phased delivery

| Step | Scope | Time |
|------|-------|------|
| 6a | VASP OUTCAR energy + forces | 1 day |
| 6b | OpenMX `.EV` + `.md` parsing | 1 day |
| 6c | VASP OSZICAR convergence trace | 0.5 day |
| 6d | Unified CLI `dft extract` | 0.5 day |

---

## Summary timeline

| # | Item | Effort | Dependencies |
|---|------|--------|-------------|
| 1 | Rebuild VASP data | 5 min | — |
| 2 | Fix `_search_fts5` row_factory | 15 min | — |
| 3 | Ollama embedding unification | 2-3 days | Ollama installed |
| 4 | Workflow examples | 1 day | 1, 2, 3 complete |
| 5 | Third DFT code + onboarding | 3-5 days | 4 complete (docs stable) |
| 6 | Post-processing | ~1 week | — (can start in parallel with 3-5) |
