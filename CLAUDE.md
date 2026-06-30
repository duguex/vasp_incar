# CLAUDE.md

This file provides guidance when working with code in this repository.

## Project overview

A framework for connecting natural language queries to DFT program knowledge and input generation.
**VASP** and **OpenMX** are the first two integrated codes — the architecture is designed to extend
to CASTEP, QE, FHI-aims, etc.

| Package | Code | Knowledge | Input gen | Conversion |
|---------|------|-----------|-----------|------------|
| `vasp_query/` | VASP | 676 INCAR tags + 10K configs + wiki | — | vasp2omx → |
| `omx_tools/` | OpenMX | 281 manual sections + 304 keywords | ✅ omx-gen | ← omp2vasp |
| `dft_utils/` | shared | version envelope, debug_log, JSON helpers | — | — |

Each DFT code gets its own package, Skill file, and set of CLI entry points.
Shared `dft_utils/` provides the common infrastructure.  Adding a new code:
index its manual → write parsers/writers → extend mapping schemas → register Skill.  The
mapping layer (`schemas/*.json`) enables cross-code parameter conversion.

## Layout

```
./
├── dft_utils/                    # shared: debug_log, DATA_VERSION, die_json
├── vasp_query/                   # VASP INCAR tag query CLI
│   ├── query.py                  # argparse, 12 subcommands (tag, search, stats, …)
│   ├── _common.py                # resolve_tag, hybrid_search, load_data, format_*_human
│   ├── processor.py              # wiki/INCAR → structured JSON preprocessor
│   ├── fetcher.py                # VASP wiki scraper (requests + bs4)
│   ├── test_cli.py               # 22 pytest tests
│   └── data/                     # generated VASP knowledge files
│       ├── tag_index.json        # 676 INCAR tags
│       ├── non_tag_index.json    # 507 wiki pages
│       ├── tag_stats.json        # frequency + top values (10K+ configs)
│       ├── tag_configs.json      # typical INCAR contexts
│       ├── tag_cooccur.json      # co-occurrence matrix (207 tags)
│       ├── search.db             # SQLite FTS5 index (1,698 docs)
│       ├── doc_vectors.npy       # sentence-transformers embeddings (384-dim)
│       └── raw/                  # raw fetch output + meta
├── omx_tools/                    # OpenMX CLI tools
│   ├── database.py               # omx-db: FTS5+semantic search, keyword/section lookup
│   ├── generator.py              # omx-gen: structure → .dat input file
│   ├── vasp2omx.py               # INCAR → OpenMX converter
│   ├── omp2vasp.py               # .dat → INCAR converter
│   ├── mapping/                  # bidirectional VASP↔ASE parameter mapping
│   │   └── __init__.py           # forward() / reverse() with 12 conversion rules
│   ├── parsers/                  # input parsers
│   │   ├── vasp.py               # INCAR → dict via pymatgen
│   │   └── openmx.py             # .dat → dict
│   ├── writers/                  # output writers
│   │   ├── openmx.py             # .dat generation via ASE
│   │   └── vasp.py               # INCAR generation via pymatgen
│   ├── schemas/                  # JSON data files
│   │   ├── keywords.json         # 304+ keyword entries (3,781 lines)
│   │   ├── templates.json        # 5 calculation templates
│   │   └── vasp_to_ase.json      # 27 mapping rules
│   │   └── __init__.py
├── tests/                        # omx_tools test suite (5 files, 110+ tests)
│   ├── conftest.py               # invoke_gen / invoke_db fixtures
│   ├── test_database.py          # 24 tests for omx-db
│   ├── test_generator.py         # 21 tests for omx-gen
│   ├── test_vasp2omx.py          # 50 tests for parsers + mapping
│   ├── test_parsers.py           # 9 tests for .dat parsing
│   └── test_writers.py           # 4 tests for INCAR/.dat writing
├── data/raw/                     # raw VASP wiki + INCAR configs
├── openmx.db                     # OpenMX v4.0 manual SQLite DB (281 sections, 3.4 MB)
├── openmx4.0_manual/             # v4.0 HTML manual (263 pages)
├── skills/
│   ├── vasp-query/SKILL.md       # VASP agent interface (bilingual)
│   └── omx-tools/SKILL.md        # OpenMX agent interface (bilingual)
├── aliases.json                  # shared domain abbreviation map
├── docs/                         # MIGRATION.md (Chinese), QWEN.md (Chinese)
├── legacy_scripts/               # older pymatgen INCAR utilities
├── rag/                          # dormant LangChain/Chroma RAG prototype
├── mlff_tutorial/                # VASP MLFF training tutorials (Chinese)
├── work/                         # test structure files for omx_tools
├── scripts/                      # keyword schema extractor for openmx.db
└── tuning_guide.md               # OpenMX performance tuning guide (Chinese)
```

## CLI reference

### VASP commands (`vasp-query`)

```bash
python3 -m vasp_query tag ENCUT          # tag description, default, related, url
python3 -m vasp_query tag ENCUT -H       # human-readable Markdown
python3 -m vasp_query search "EFG"       # hybrid search (tags + wiki pages)
python3 -m vasp_query search "HSE" --type=tag --debug  # filter + pipeline trace
python3 -m vasp_query search "POSCAR" -H # human-readable
python3 -m vasp_query stats [TAG]        # frequency + top values; omit TAG to list all
python3 -m vasp_query stats ENCUT -k 2   # top 2 values only
python3 -m vasp_query list              # all known tag names
python3 -m vasp_query list -H           # one per line
python3 -m vasp_query related QUAD_EFG   # wiki-related tags
python3 -m vasp_query fullwiki LEFG      # full cleaned wiki content
python3 -m vasp_query fullwiki LEFG -H   # plain-text
python3 -m vasp_query incar ENCUT=400 NSW=0       # match-all INCAR filter
python3 -m vasp_query incar ENCUT=400 NSW=0 --any-match  # match-any
python3 -m vasp_query cooccur ENCUT PREC          # co-occurrence stats
python3 -m vasp_query cooccur ISMEAR SIGMA -H     # human-readable
python3 -m vasp_query fetch              # fetch latest wiki data from vasp.at
python3 -m vasp_query fetch --check      # detect wiki changes (~2s)
python3 -m vasp_query preprocess         # rebuild all data files
python3 -m vasp_query preprocess --check # detect stale data
```

All output is JSON on stdout by default. `-H` / `--human` → Markdown. `--debug` traces search tiers.

### OpenMX commands (`omx-db`, `omx-gen`, `vasp2omx`, `omp2vasp`)

```bash
# Manual database queries
omx-db search "SCF convergence"          # FTS5 full-text search
omx-db search "SCF" --json               # JSON output
omx-db hybrid "mixing parameters" --debug  # FTS5 + semantic RRF
omx-db rag "how to tune SCF"             # semantic search (loads embedding model)
omx-db keyword "scf.Kgrid"               # keyword → section lookup
omx-db keyword scf.Kgrid --json          # JSON with structured metadata
omx-db section 16                        # read chapter §16
omx-db section 8.2                       # read subsection §8.2
omx-db list                              # all sections
omx-db files                             # file inventory
omx-db files --type pdf                  # only PDFs
omx-db stats                             # database statistics

# Input generation
omx-gen structure.cif -t scf_band -o calc.dat        # generate .dat
omx-gen POSCAR -t scf_band_metal --cutoff 400 -k 8 8 8  # metal with overrides
omx-gen h2o.xyz -t scf_cluster                        # molecule (no k-points)
omx-gen structure.cif -t geom_opt -o opt.dat           # geometry optimization
omx-gen --list-templates                               # available templates
omx-gen --keyword scf.EigenvalueSolver                 # keyword metadata

# Format conversion
vasp2omx INCAR POSCAR -o input.dat     # VASP → OpenMX
omp2vasp input.dat -o INCAR            # OpenMX → VASP
```

`omx-db` accepts `--json` as a global flag. omx-gen/vasp2omx/omp2vasp use `--json` for structured output. Errors: `{"error": "...", "exit": N}` with exit code 0 (JSON always last on stdout).

### Templates (omx-gen)

| Template | Use case | Auto k-points |
|----------|----------|---------------|
| `scf_band` | Crystal SCF + band diagonalization | ✅ |
| `scf_band_metal` | Metallic system (Kerker, high smearing) | ✅ |
| `scf_cluster` | Molecule/cluster (no k-points) | ❌ |
| `geom_opt` | Geometry optimization | ✅ |
| `band_dispersion` | Post-SCF band structure | ❌ |

## Search architecture

### VASP (4-tier cascade in `cmd_search`)
- **T1 — `resolve_tag`:** exact uppercase → alias map → file page → fuzzy (difflib 0.5) → substring
- **T2 — file page:** POSCAR/OUTCAR etc. (embedded in T1)
- **T3 — `hybrid_search`:** SQLite FTS5 (primary) + sentence-transformers BGE-small (384-dim) → RRF fusion (`1/(60+rank)`; tag-only 1.5× weight). Falls back to tantivy BM25.
- **T4 — legacy keyword:** substring + heuristic scoring

### OpenMX (3 modes in `omx-db`)
- **FTS5 search** — `cmd_search()`: BM25-ranked FTS5 on `sections_fts` virtual table
- **Semantic / RAG** — `cmd_rag()`: subprocess-based sentence-transformers inference, cosine similarity
- **Hybrid** — `cmd_hybrid()`: FTS5 + semantic → RRF fusion (same algorithm as vasp-query)
- **Keyword index** — `cmd_keyword()`: exact schema match → lower-case alias → DB index_entries fallback

## Data management

### VASP data regeneration

```bash
python3 -m vasp_query fetch              # scrape vasp.at/wiki (requests+bs4)
python3 -m vasp_query fetch --check      # remote change detection (~2s)
python3 -m vasp_query preprocess         # rebuild all data/*.json
python3 -m vasp_query preprocess --check # staleness detection
```

Preprocess runs: `parse_wiki_to_index` → `parse_non_tag_to_index` → `make_wiki_full` → `extract_tag_stats` → `extract_tag_configs` → `extract_tag_cooccur` → `generate_missing_tags` → `build_search_indexes` (FTS5 + embeddings).

### OpenMX database rebuild

The `openmx.db` is prebuilt. To rebuild from HTML sources:
```bash
cd scripts && python3 extract_keywords.py    # rebuild keywords.json from ASE + HTML
# then rebuild openmx.db via database.py internals
```

## Testing

```bash
# VASP tests (real data, no mocking)
python3 -m vasp_query.test_cli               # 22 tests, ~30-120s (slow: model load)

# OpenMX tests (capsys, no container needed for most)
python3 -m pytest tests/ --ignore=tests/test_integration.py  # 109 tests, ~2s

# Full suite including container test (needs /mnt/shared/openmx4.0_intel.sif)
python3 -m pytest tests/                     # 110 tests
```

## Installation

```bash
pip install -e .                             # core (pydantic)
pip install -e ".[vasp]"                     # VASP tag lookup + semantic search
pip install -e ".[omx]"                      # OpenMX gen + format conversion
pip install -e ".[all]"                      # everything
```

Optional extras: `semantic` (sentence-transformers), `search` (tantivy), `fetch` (requests+bs4+tqdm), `gen` (ase), `vasp2omx` (pymatgen), `vasp`, `omx`, `all`.

## Conventions & gotchas

### Error handling
- VASP errors: `{"error": "...", "suggestion": "..."}` to stdout, `sys.exit(1)`.
- omx errors: `{"error": "...", "exit": N}` to stdout, `sys.exit(0)` (JSON always last on stdout).
- Both include actionable `suggestion` field when applicable.
- `die_json()` in `dft_utils` for omx-gen/writer components.

### Version envelope
All data files wrapped as `{"_version": "0.3.0", "data": <content>}`. `dft_utils.load_json()` strips it. Mismatch warns.

### Caching
Module-level lazy caches (`_INDEX_CACHE`, `_MODEL_CACHE`, `_ALIASES_CACHE`) via `global`. Heavy deps (sentence-transformers) loaded once per process.

### Async
Zero async. All synchronous — `requests` (not `aiohttp`), no `asyncio`.

### Named data files
- VASP: `vasp_query/data/*.json` — generated, never hand-edited. After parser change, re-run `preprocess`.
- OpenMX: `openmx.db` — prebuilt SQLite FTS5 database. `openmx4.0_manual/` for section content retrieval.

### Environment variables
| Variable | Tool | Default |
|----------|------|---------|
| `OPENMX_DB_PATH` | `omx-db` | `<repo>/openmx.db` |
| `OPENMX_DFT_DATA_PATH` | `omx-gen` | (required for ASE-based generation) |

### Gotchas
- `vasp_query/data/*.json` are git-tracked (large files ~6 MB each).
- Set `USE_TF=0` before importing sentence-transformers if TensorFlow not needed.
- pydantic is a hard runtime dep (now in `pyproject.toml`).
- `docs/MIGRATION.md` references the removed MCP server — outdated.
- `aliases.json` version may lag behind code version; triggers a `UserWarning` until next `preprocess`.
- omx-tools `tests/test_integration.py` requires Singularity container at `/mnt/shared/` — skipped when absent.

## Quality metrics

| Category | What to watch | Why it matters |
|----------|---------------|----------------|
| **Coverage** | % of VASP parameters captured (target: 90%+) | Users can't query what isn't indexed |
| **Search accuracy** | Top-3 hit rate; false positive rate | Core UX for both humans and agents |
| **Data freshness** | `_version` sync between code and data files | Stale data silently misleads users |
| **Parse stability** | Wiki/HTML format changes break nothing | VASP wiki and OpenMX markup not guaranteed stable |
| **Latency** | Time from query to response | Above ~500ms degrades CLI experience |
| **Test coverage** | CLI pytest (22 vasp + 110 omx) | Low coverage makes regression easy |
| **Error UX** | Every error must include actionable `suggestion` | `"not found"` without next step is useless to agents |
