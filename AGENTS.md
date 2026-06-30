# Repository Guidelines

## Project Overview

A framework for connecting natural language queries to DFT program knowledge and input generation.
VASP and OpenMX are the first two integrated codes — the architecture is designed to extend
to CASTEP, QE, FHI-aims, etc.

| Package | Code | Knowledge | Input gen | Cross-code conversion |
|---------|------|-----------|-----------|----------------------|
| `vasp_query/` | VASP | 676 INCAR tags + 10K configs + wiki | — | vasp2omx |
| `omx_tools/` | OpenMX | 281 manual sections + 304 keywords | ✅ omx-gen | omp2vasp |
| `dft_utils/` | shared | version envelope, debug_log, JSON helpers | — | — |

Each DFT code gets its own package, Skill file, and CLI entry points. Shared `dft_utils/`
provides the common infrastructure.  Adding a new code: index its manual → write parsers →
write writers → extend mapping schemas → register Skill.  The mapping layer (`schemas/*.json`)
enables cross-code parameter conversion.

Supplementary contents: MLFF tutorials (`mlff_tutorial/`), legacy Python scripts, and an old
LangChain/Chroma RAG prototype.

## Architecture & Data Flow

```
                        ┌─────────────────────────────────────────────┐
                        │             dft_utils/ (shared)              │
                        │  DATA_VERSION, debug_log, load_json, die_json│
                        └─────────────────────────────────────────────┘

┌─────────────────────────────┐    ┌─────────────────────────────────────┐
│       vasp_query/            │    │          omx_tools/                 │
│                              │    │                                     │
│  vasp.at/wiki  ──[fetcher]──►│    │  openmx4.0_manual/ → [keyword DB]  │
│       + incar_data.json      │    │       + openmx.db                  │
│              │               │    │            │                       │
│              ▼               │    │            ▼                       │
│     [processor.py]           │    │  omx-db (FTS5 + semantic RRF)      │
│              │               │    │  omx-gen (structure → .dat)        │
│              ▼               │    │  vasp2omx (INCAR ↔ .dat)           │
│  tag_index.json, search.db   │    │  omp2vasp (.dat → INCAR)           │
│  tag_stats.json, doc_vectors │    │                                     │
│                              │    │                                     │
│  query.py (CLI dispatch)     │    │  4 entry points (omx-db, omx-gen,  │
│  12 subcommands              │    │  vasp2omx, omp2vasp)               │
└─────────────────────────────┘    └─────────────────────────────────────┘
```

### VASP search pipeline (4 tiers)
1. **T1 — `resolve_tag`:** exact uppercase match → alias map → file page → fuzzy (difflib, 0.5 cutoff) → substring
2. **T2 — file page:** fallback for POSCAR/OUTCAR etc.
3. **T3 — `hybrid_search`:** SQLite FTS5 (primary, zero-dep) + sentence-transformers BAAI/bge-small-en-v1.5 (384-dim) with RRF fusion (`1/(60+rank)`). Tag-only corpus gets 1.5× weight. Falls back to tantivy BM25, then empty.
4. **T4 — legacy keyword:** substring + heuristic scoring

### OpenMX database search
- FTS5 full-text search (BM25 ranked)
- Semantic search (sentence-transformers, subprocess)
- Hybrid RRF fusion (same algorithm as vasp-query)
- Keyword index lookup (799 entries, 295 unique keywords)

All data files use a **version envelope**: `{"_version": "0.3.0", "data": <content>}`. `load_data()` warns on mismatch.

## Key Directories

| Path | Purpose |
|------|---------|
| `vasp_query/` | VASP INCAR tag query tool: CLI, processor, fetcher, tests |
| `omx_tools/` | OpenMX toolchain: generator, database, format converters, tests |
| `dft_utils/` | Shared utilities: version, debug log, JSON helpers |
| `vasp_query/data/` | Preprocessed VASP tag knowledge (tracked in git) |
| `data/raw/` | Raw inputs: `vasp_wiki_all_data.json` (5.9 MB), `incar_data.json` (16 MB) |
| `openmx.db` | OpenMX v4.0 manual FTS5 database (3.4 MB) |
| `openmx4.0_manual/` | OpenMX v4.0 HTML manual (263 pages) |
| `skills/vasp-query/` | VASP skill interface (`SKILL.md`) |
| `skills/omx-tools/` | OpenMX skill interface (`SKILL.md`) |
| `legacy_scripts/` | Older pymatgen-based INCAR utilities |
| `docs/` | `MIGRATION.md` (Chinese setup guide), `QWEN.md` (legacy-scripts overview) |
| `examples/` | Sample inputs (currently `POSCAR`) |
| `rag/` | Dormant LangChain/Chroma RAG prototype |
| `mlff_tutorial/` | MLFF training tutorials (Chinese-named subdirs) |
| `scripts/` | Keyword extraction script for OpenMX manual DB |
| `aliases.json` | User-editable domain abbreviation map (shared) |

## Development Commands

```bash
# VASP CLI
python3 -m vasp_query tag ENCUT
python3 -m vasp_query search "HSE06" --debug
python3 -m vasp_query --version

# OpenMX CLI
omx-db search "SCF convergence"
omx-db rag "mixing parameters"
omx-gen structure.cif -t scf_band -o calc.dat
vasp2omx INCAR POSCAR -o input.dat
omp2vasp input.dat -o INCAR

# Run VASP tests
python3 -m vasp_query.test_cli           # 22 pytest tests

# Run OpenMX tests
cd ~/vasp_wiki && python3 -m pytest tests/  # 111+ pytest tests
# (requires openmx.db at the repo root)

# Regenerate VASP data
python3 -m vasp_query fetch              # scrape latest from vasp.at
python3 -m vasp_query preprocess         # rebuild all structured data

# Install
pip install -e ".[vasp]"                 # VASP tools
pip install -e ".[omx]"                  # OpenMX tools
pip install -e ".[all]"                  # everything
```

## Code Conventions & Common Patterns

### Error handling
- All errors returned as JSON dicts to stdout (never stderr) with non-zero exit: `{"error": "...", "suggestion": "..."}`.
- `--debug` flag injects `_debug` key with intermediate search steps.
- Optional backend failures (tantivy, sentence-transformers) caught silently, logged to `_DEBUG_LOG`, never propagated.
- Ambiguous tag matches: `{"hint": "Did you mean one of these?", "matches": [...]}`.
- `die_json()` in `dft_utils` for omx-gen/writer components: `{"error": "...", "exit": N}`.

### Naming
- **snake_case** for everything (functions, variables, files).
- **PascalCase** for Pydantic models (`TagEntry(BaseModel)`, `SearchResult`, etc.).
- **UPPER_CASE** for module-level constants (`DATA_VERSION`, `TAG_INDEX`).
- **Leading underscore** for private helpers (`_parse_tag_page`, `_INDEX_CACHE`).

### Type annotations
- Present on function signatures (return types inconsistent — `cmd_*` functions lack return annotations).
- Sparse on local variables.
- Pydantic models only used for validation in processor.py / database.py; data flows as plain `dict` elsewhere.

### Async / sync
- **Zero async code** anywhere. All synchronous: `requests` (not `aiohttp`), no `asyncio`.

### Imports
- Strict grouping: stdlib → blank line → third-party → blank line → local.
- Heavy/optional deps imported **inside functions** (lazy): `sentence_transformers`, `tantivy`, `numpy`, `ase`, `pymatgen`, `sqlite3`.

### CLI patterns
- `argparse` with subparsers, no click/typer/rich.
- vasp-query: dispatch via dict `commands = {"tag": cmd_tag, ...}`. Shared `_add_human_arg()` for `-H`/`--human`.
- omx-db: single argparser with subcommands (search, keyword, section, list, files, stats, hybrid, rag).
- omx-gen/vasp2omx/omp2vasp: standalone argparsers per entry point.
- JSON output: `json.dumps(result, indent=2, ensure_ascii=False, default=str)`.

### Version envelope
Every data file wrapped: `{"_version": "0.3.0", "data": ...}`. `load_data()` in `dft_utils` strips it and warns on mismatch.

### Caching pattern
Module-level lazy caches (`_INDEX_CACHE`, `_MODEL_CACHE`, `_ALIASES_CACHE`) set via `global` inside load functions.

## Important Files

| File | Role |
|------|------|
| `dft_utils/__init__.py` | Shared utilities: DATA_VERSION, debug_log, load_json, die_json |
| `vasp_query/__main__.py` | VASP CLI entry point: `sys.exit(main())` |
| `vasp_query/query.py` | VASP CLI: argparse, 12 subcommand handlers, dispatch |
| `vasp_query/_common.py` | VASP shared: models, loaders, `resolve_tag`, `hybrid_search`, formatters |
| `vasp_query/processor.py` | VASP pipeline: raw → structured JSON + search indexes + embeddings |
| `vasp_query/fetcher.py` | VASP wiki scraper (requests + BeautifulSoup) |
| `vasp_query/test_cli.py` | 22 integration tests for VASP CLI |
| `omx_tools/database.py` | omx-db CLI: FTS5 + semantic search, keyword/section lookup (758 lines) |
| `omx_tools/generator.py` | omx-gen CLI: input file generation from structure + templates |
| `omx_tools/vasp2omx.py` | VASP→OpenMX converter CLI |
| `omx_tools/omp2vasp.py` | OpenMX→VASP converter CLI |
| `omx_tools/mapping/__init__.py` | Bidirectional VASP↔ASE parameter mapping (12 conversion rules) |
| `omx_tools/schemas/vasp_to_ase.json` | 27 VASP→ASE mapping entries |
| `omx_tools/schemas/templates.json` | 5 calculation templates |
| `omx_tools/schemas/keywords.json` | 304+ OpenMX keyword entries (3781 lines) |
| `tests/` | 111+ pytest tests for omx_tools |
| `openmx.db` | OpenMX v4.0 manual SQLite database (3.4 MB) |
| `skills/vasp-query/SKILL.md` | VASP agent interface (bilingual) |
| `skills/omx-tools/SKILL.md` | OpenMX agent interface (bilingual) |
| `CLAUDE.md` | Most authoritative guide: architecture, conventions, quality metrics |
| `pyproject.toml` | PEP 621 build config, 5 entry points, optional extras |

## Runtime / Tooling Preferences

- **Python >= 3.10** required.
- **No package manager preference** — pip-based (no uv/poetry lockfile).
- **pydantic is a hard runtime dependency** — now properly declared in `pyproject.toml`.
- `USE_TF=0` should be set before importing `sentence-transformers` if TensorFlow is not needed.
- Large data files (~16 MB + ~5.9 MB + 3.4 MB DB) are tracked in git. `.gitignore` covers standard Python artifacts.

## Testing & QA

### VASP tests
- 22 integration tests via `subprocess.run(['python', '-m', 'vasp_query', ...])`.
- No fixtures, no mocking — all tests use real on-disk data files.
- Run: `python3 -m vasp_query.test_cli`

### OpenMX tests
- 111+ pytest tests across 5 test files.
- Uses `capsys` fixtures and `conftest.py` with `invoke_gen` / `invoke_db` helpers.
- Tests skip gracefully when `openmx.db` or optional deps are missing.
- Run: `python3 -m pytest tests/`

### Quality metrics (from CLAUDE.md)
- Coverage: 90%+ of VASP parameters captured
- Search accuracy: top-3 hit rate, false positive rate
- Data freshness: `_version` sync between code and data
- Parse stability: wiki format changes break nothing
- Latency: current ~6 MB JSON loaded per call
- Error UX: every error includes actionable `suggestion`
