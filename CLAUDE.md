# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

The repo is organized into focused subdirectories:

1. **`skills/vasp-query/`** — Skill file (`SKILL.md`) registered as the primary agent interface.
2. **`vasp_query/`** — Python package that exposes VASP INCAR tag knowledge (description, default, related tags, wiki content, frequency stats from real configurations) via a CLI. Target consumers are LLMs/agents that need authoritative VASP parameter info.
3. **`legacy_scripts/`** — older `pymatgen`-based utilities for INCAR validation, reference generation, batch extraction, comparison, and tag-driven editing. These predate `vasp_query` and remain useful for ad‑hoc HPC workflows. See `legacy_scripts/README.md` for caveats.
4. **`data/raw/`** — raw inputs to the preprocessor (`incar_data.json`, `vasp_wiki_all_data.json`).
5. **`docs/`** — `MIGRATION.md` (Chinese setup walkthrough for a new machine), `QWEN.md` (context dump for handoff between agents).
6. **`examples/`** — sample inputs (currently just `POSCAR`).
7. **`rag/`** — separate LangChain/Chroma RAG prototype, dormant.
## `vasp_query` package

### Layout

```
vasp_query/
├── __init__.py         # exposes __version__
├── __main__.py         # entry: sys.exit(main()) from query.main
├── _common.py          # shared: pydantic models, load_data(), resolve_tag(), hybrid_search()
├── query.py            # argparse CLI; 12 subcommands
├── processor.py        # one-shot wiki/INCAR → structured JSON preprocessor
├── fetcher.py          # VASP wiki scraper (requests + BeautifulSoup)
├── test_cli.py         # pytest suite for CLI subcommands (cooccur, -H, --type, --top-k, --debug)
└── data/               # generated structured data (version envelope)
    ├── tag_index.json     # 676 INCAR tags (647 wiki + 29 auto-generated)
    ├── non_tag_index.json # 507 tutorials / how-tos / best practices / file pages
    ├── tag_stats.json     # frequency + top-5 values per tag (from incar_data.json)
    ├── tag_configs.json   # typical INCAR context configs per tag (from 10,176 real configs)
    ├── tag_cooccur.json   # precomputed co-occurrence matrix (207 tags)
    ├── wiki_full.json     # 1,107 cleaned wiki pages (full content + url)
    ├── search_index/      # tantivy BM25 index (1,183 docs)
    ├── doc_vectors.npy    # sentence-transformers embeddings (1,183×384)
    ├── doc_meta.json      # doc mapping for vector index
    └── raw/               # raw inputs and fetch metadata
        ├── incar_data.json     # 10,176 real INCAR configurations
        ├── vasp_wiki_all_data.json # 1,273 scraped VASP wiki pages
        └── _meta.json          # fetch metadata (page titles, timestamps)
```

Raw inputs the preprocessor reads from `data/raw/`:
- `incar_data.json` — 10,176 real INCAR configurations
- `vasp_wiki_all_data.json` — 1,273 scraped VASP wiki pages

### CLI

```bash
python3 -m vasp_query tag ENCUT          # tag description, default, related, url
python3 -m vasp_query tag ENCUT -H       # same, human-readable Markdown
python3 -m vasp_query search "EFG"       # searches tag_index + non_tag_index
python3 -m vasp_query search "HSE" --type=tag   # filter by result type
python3 -m vasp_query search "POSCAR" -H # human-readable, file-format pages rank higher
python3 -m vasp_query search "phonon" --debug   # show intermediate search steps
python3 -m vasp_query stats [TAG]        # frequency + top values; omit TAG to list all
python3 -m vasp_query stats ENCUT -k 2   # show only top 2 values
python3 -m vasp_query list              # all known tag names
python3 -m vasp_query list -H           # one per line
python3 -m vasp_query related QUAD_EFG   # wiki-related tags
python3 -m vasp_query fullwiki LEFG      # full cleaned wiki content
python3 -m vasp_query fullwiki LEFG -H   # plain-text content
python3 -m vasp_query incar ENCUT=400 NSW=0   # match-all filter; --any-match inverts
python3 -m vasp_query cooccur ENCUT PREC      # co-occurrence stats from 10k+ configs
python3 -m vasp_query cooccur ISMEAR SIGMA -H # human-readable with wiki relationship
python3 -m vasp_query fetch              # fetch latest wiki data from vasp.at
python3 -m vasp_query fetch --check      # check remote wiki for changes (~2s)
python3 -m vasp_query preprocess         # rebuild data/*.json from raw inputs
python3 -m vasp_query preprocess --check # detect stale data without running
```
All output is JSON on stdout by default. Add `-H` / `--human` for Markdown, `--debug` for search to trace intermediate steps. Errors come back as `{"error": ..., "suggestion": ...}` (or `"matches": [...]` for ambiguous tags) with non-zero exit code.

### Regenerating structured data

Whenever raw inputs change, or the preprocessor logic is modified:

```bash
python3 -m vasp_query fetch              # fetch latest wiki data from vasp.at
python3 -m vasp_query fetch --check      # check remote wiki for changes (~2s)
python3 -m vasp_query preprocess         # rebuild all data
python3 -m vasp_query preprocess --check # detect staleness without running
```

This calls `processor.preprocess()` which runs four steps in order:
1. `parse_wiki_to_index()` → `data/tag_index.json`
2. `parse_non_tag_to_index()` → `data/non_tag_index.json`
3. `make_wiki_full()` → `data/wiki_full.json`
4. `extract_tag_stats()` → `data/tag_stats.json`

Additional data generated:
- `extract_tag_configs()` → `data/tag_configs.json` (INCAR config samples per tag)
- `extract_tag_cooccur()` → `data/tag_cooccur.json` (co-occurrence matrix)
- `generate_missing_tags()` → appends auto-generated entries for Wannier90 params etc.
- `build_search_indexes()` → `data/search_index/` (tantivy BM25) + `data/search.db` (SQLite FTS5) + `data/doc_vectors.npy` (embeddings)

Each output file is wrapped in a version envelope: `{"_version": "...", "data": <actual content>}`.
The version is checked on load by `_common.load_data()` — warnings are emitted if out of sync.
`preprocess --check` compares the fetch timestamp vs preprocess timestamp to detect staleness.

The parser heuristics are tightly coupled to VASP wiki markup conventions — see `_parse_tag_page` (looks for `TITLE`, `= value`, `Default:`, `Description:` markers) and `_KNOWN_FILES` (whitelist of file-format pages like POSCAR, KPOINTS, etc. that the non-tag path lets through).

### Tests

```bash
python3 -m vasp_query.test_cli               # 14 pytest tests — CLI subcommands
```

Expects the data files to exist. Exits non-zero on any failure.

### Installation / setup

```bash
pip install pydantic sentence-transformers               # core + semantic search
pip install tantivy                                       # optional: BM25 search (SQLite FTS5 is built-in fallback)
pip install requests beautifulsoup4 tqdm                  # fetcher dependencies
```

The Skill file `skills/vasp-query/SKILL.md` is the primary agent interface. Register it via hermes:

```bash
mkdir -p ~/.hermes/skills/research/vasp-query
ln -s ~/vasp_incar/skills/vasp-query/SKILL.md ~/.hermes/skills/research/vasp-query/SKILL.md
```

**`hybrid_search()`** (`_common.py`): SQLite FTS5 (primary, zero-dep) + semantic (sentence-transformers BGE-small, 384-dim) → Reciprocal Rank Fusion. Falls back to tantivy BM25 when SQLite unavailable.
Two-stage context7-inspired pipeline:
**Tiered search (`search` command):**
- **T1 — `resolve_tag`:** exact title match, file page exact match. Covers ~90% of human CLI queries. Latency: ~10ms.
- **T2 — file page:** fallback for file formats like POSCAR, OUTCAR. Latency: ~2ms.
- **T3 — `hybrid_search`:** SQLite FTS5 (or tantivy BM25 fallback) + semantic (sentence-transformers BGE-small). Used for agent-style natural language queries and when T1/T2 miss. Latency: ~15s CLI (model loaded fresh per invocation).
- **T4 — legacy keyword fallback:** original substring + heuristic scoring as safety net.

Debug log: add `--debug` to `search` to trace the pipeline (which tier, alias match, BM25/semantic scores, RRF fusion).

Data files generated by `preprocess`:
- `tag_index.json`, `non_tag_index.json`, `wiki_full.json`, `tag_stats.json`
- `tag_configs.json` — INCAR config samples per tag (from 10,176 real configs)
- `tag_cooccur.json` — precomputed co-occurrence matrix (207×207)
- `search_index/` — tantivy BM25 index (1,698 docs)
- `search.db` — SQLite FTS5 search index (1,698 docs, zero-dependency fallback)
- `doc_vectors.npy` — sentence-transformers embeddings (1,698×384)
- `doc_meta.json` — doc id mapping for vector index

## Legacy scripts (in `legacy_scripts/`)

These all hard-code `#!/home/duguex/.conda/envs/pydefect/bin/python` (or `dgkan_rocm_3.11` in the systemd unit) — adjust the shebang or use the right `conda activate` before running. They depend on `pymatgen` and `tqdm`. See `legacy_scripts/README.md` for full notes on path quirks after the 2026-06-09 reorg (in particular, `incar.py` expects `POSCAR` in the cwd — see `examples/POSCAR`).

| Script                  | What it does                                                                            |
| ----------------------- | --------------------------------------------------------------------------------------- |
| `extract_incar.py`      | Walk a directory tree, parse all `INCAR` files (multiprocess), dedupe, write JSON       |
| `find_missing_tags.py`  | Compare tags in a directory of INCARs vs. `incar_data.json` to find untracked tags      |
| `incar_ref.py`          | Query `incar_data.json` by KEY=VALUE; emit INCAR text with most-frequent values + alt    |
| `incar.py`              | Validate a directory's `INCAR` against a reference JSON (`/mnt/shared/rc-tmp` or `~/rc-tmp`) keyed by element tuple; requires local `POSCAR` |
| `compare_incar.py`      | Diff two INCAR files; fixed paths `INCAR_6` vs `INCAR_8` (hardcoded in `__main__`)      |
| `tag_incar.py`          | Read INCAR, expose high-level tag aliases (`soc`, `hse0`, `pbe0`, `scan`, `spin`, `phonon`, `relax2/3`, …) and rewrite INCAR with the right `LSORBIT`/`LHFCALC`/etc. settings; interactive mode |
| `sample_incar.sh`       | Random sample of INCAR files under `./katze/` into `./incar_smp/` (defaults; edit)      |
| `vasp_wiki_scraper.py`  | Original scraper for `https://vasp.at/wiki/` — replaced by `vasp_query fetch` |

## Quality metrics

| Category | What to watch | Why it matters |
|----------|---------------|----------------|
| **Coverage** | % of VASP parameters captured (target: 90%+) | Users can't query what isn't indexed |
| **Search accuracy** | Top-3 hit rate; false positive rate; empty-result rate | Core UX metric for both humans and agents |
| **Data freshness** | `_version` match between code and preprocessed files | Stale data silently misleads users |
| **Parse stability** | Wiki format changes break nothing on re-preprocess | VASP wiki markup is not guaranteed stable |
| **Latency** | Time from query to response (current ~6 MB JSON loaded per call) | Above ~500 ms degrades CLI experience |
| **Test coverage** | CLI pytest (14 tests) | Low coverage makes regression easy |
| **Error UX** | Every error must include actionable `suggestion` | `"not found"` without next step is useless to agents |

## Conventions & gotchas

- Tag lookups are case-insensitive on the title field but exact match is preferred. Partial matches return `{"hint": ..., "matches": [...]}` rather than guessing.
- Search uses a hybrid approach: SQLite FTS5 (primary) or tantivy BM25 (fallback) + sentence-transformers semantic embeddings → RRF fusion. See `hybrid_search()` in `_common.py`.
- `vasp_query/data/*.json` files are generated, not hand-edited. After touching the parser, always re-run `preprocess` and re-run the test suite to catch regressions.
- `.gitignore` is minimal (`__pycache__/`, `*.pyc`); the large `*.json` data files (raw + preprocessed) are tracked. `data/raw/incar_data.json` is ~16 MB, `data/raw/vasp_wiki_all_data.json` ~5.9 MB, `rag/vasp_wiki_all_data.json` ~5.7 MB.
- Set `USE_TF=0` before importing sentence-transformers if TensorFlow is not needed (transformers compat workaround).
