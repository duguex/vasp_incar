# Context (domain + architecture)

> Machine- and human-readable record of the project's domain vocabulary and the
> load-bearing architecture decisions. Architecture reviews should use this
> vocabulary and should **not re-litigate** the decisions marked *settled* below.

## What this is

Multi-code DFT **knowledge + input generation + conversion + advice**, plus a
**verification** path that checks generated inputs produce sensible physics.
The product is **not a DFT engine** and product CLIs are **not an integration
dependency**.

## Layers (plug-ins over a neutral substrate)

- `dft_utils` — the **neutral substrate** every code package depends on. Owns
  shared search orchestration, the semantic IR, the verification seam, version
  envelope, protocol/plugin registry.
- `vasp_query`, `omx_tools` — **peer code plugins** (VASP, OpenMX) that
  implement input generation, conversion, and per-code search adapters, sitting
  *above* `dft_utils`.
- `dft_utils.verify` — the **verification seam**: defines engine *jobs* and
  their analysis; execution is delegated elsewhere (see decisions).

## Domain vocabulary

- **Module / interface / depth / seam / adapter / leverage / locality** — the
  codebase-design vocabulary (see skill `codebase-design`). Use these terms,
  not "component"/"service"/"API".
- **SemanticIR** — the canonical, physics-level cross-code intermediate
  representation (`dft_utils.ir`). Distinguish from **mapping** (`omx_tools.mapping`),
  the low-level code-native keyword adapter.
- **SearchBackend** — a per-code adapter producing one ranked retrieval signal
  (FTS5, BM25, semantic, tag-only) fused by the shared `dft_utils` orchestrator.
- **VerificationRunner** — the seam `dft_utils.verify` uses to hand engine runs
  to an executing backend. **CRISP** is the production backend.

## Architecture decisions

### 1. Calculation execution is delegated to CRISP  *(settled)*
- Real VASP/OpenMX engine runs are submitted through the **CRISP Python facade**
  (`crisp_api`), writing an async `submit` row that the CRISP daemon schedules.
- Product CLIs are **not** an integration dependency; `vasp_wiki` never shells
  out to `crisp submit` and never imports CRISP internals (`shared`/`daemon`/`cli`/`webui`)
  or reads `agent.db`.
- `scripts/*` container runs are **compatibility/testing only**, not production.
- Verification is **non-blocking and async-by-construct**: `plan → submit →
  poll → collect → analyze`, no synced engine RPC, no `asyncio`.

### 2. SemanticIR lives in the neutral substrate  *(settled)*
- `SemanticIR` and its schema/envelope helpers live in `dft_utils/ir`.
- `omx_tools.semantic.ir` is a backward-compatible re-export shim only.
- This makes the cross-code round-trip symmetric (VASP *and* OpenMX depend on
  the same neutral IR) rather than one-sided.

### 3. Hybrid search is unified in `dft_utils`  *(settled)*
- One orchestrator (`dft_utils.search.hybrid_search` + `SearchBackend`/
  `SearchHit`) is the single fusion point; both codes are thin adapters.
- Semantic scores are **true cosine** (L2-normalized) with a **dimension guard**
  (`EmbeddingDimError`) — a mismatch fails loudly instead of silently degrading.
- Ranking is *changed* by this normalization; relevance tests are the guard net.

### 4. `omx_tools` query layer is split  *(settled)*
- `db_models`, `aliases`, `db_conn`, `search` are single-responsibility modules;
  `omx_tools.database` is the CLI/facade.

### 5. Conversion adapter hierarchy is consolidated  *(settled)*
- One downward chain: `dft_utils.ir` (physics seam) → `omx_tools/semantic`
  (IR↔code encoders/decoders, no duplicated field-mapping copy) →
  `omx_tools.mapping` (single keyword adapter + `default_mapping()` cache) →
  `schemas/vasp_to_ase.json` (single mapping data table).
- The legacy `omx_tools/semantic_roundtrip.py` is gone; equivalence-report
  helpers live in the neutral `dft_utils.equiv`.
- The VASP-side enum vocabulary (ISPIN, GGA) has a **single source of truth**:
  `dft_utils.ir`; `mapping` composes it and keeps only OpenMX literal wording.

## Deferred / open (worth exploring, not settled)

- Dead tantivy BM25 path: **removed** (untracked `search_index/`, builder
  dropped from `processor.py`); hybrid uses FTS5 + semantic + tag now.
- OpenMX manual DB is now **reproducible**: `scripts/build_openmx_db.py`
  rebuilds `openmx.db` from the tracked `openmx4.0_manual/` HTML; `openmx.db`
  is untracked/gitignored, and its `section_embeddings` `dim`/`file_path` and
  version `meta` are now correct.
- VASP search artifacts are **reproducible**: `python -m vasp_query preprocess`
  rebuilds `search.db` (deterministic) + `doc_vectors.npy`/`tag_vectors.npy`
  from the committed `data/raw/` corpus; all three are untracked/gitignored.
  (Rebuild required lowering the embedding-text truncation 8k→4k chars to fit
  the Ollama context window.)
- The omx DB version check is renamed `warn_on_version_mismatch`; the only
  `check_version` is now the shared `dft_utils.version` envelope check
  (ambiguity resolved).