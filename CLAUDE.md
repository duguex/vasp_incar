# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

The repo is organized into focused subdirectories:

1. **`vasp_query/`** — agent-friendly Python package that exposes VASP INCAR tag knowledge (description, default, related tags, wiki content, frequency stats from real configurations) via a CLI and an MCP server. Target consumers are LLMs/agents that need authoritative VASP parameter info.
2. **`legacy_scripts/`** — older `pymatgen`-based utilities for INCAR validation, reference generation, batch extraction, comparison, and tag-driven editing. These predate `vasp_query` and remain useful for ad‑hoc HPC workflows. See `legacy_scripts/README.md` for caveats.
3. **`data/raw/`** — raw inputs to the preprocessor (`incar_data.json`, `vasp_wiki_all_data.json`).
4. **`docs/`** — `MIGRATION.md` (setup walkthrough), `QWEN.md` (context dump).
5. **`examples/`** — sample inputs (currently just `POSCAR`).
6. **`vasp-mcp-systemd-services/`** — optional systemd --user unit that exposes the MCP server over HTTP.
7. **`rag/`** — separate LangChain/Chroma RAG prototype, dormant.

## `vasp_query` package

### Layout

```
vasp_query/
├── __init__.py         # exposes __version__
├── __main__.py         # entry: sys.exit(main()) from query.main
├── query.py            # argparse CLI; 8 subcommands
├── processor.py        # one-shot wiki/INCAR → structured JSON preprocessor
├── mcp_server.py       # FastMCP server (stdio or HTTP on :8932)
├── test_mcp.py         # self-contained smoke test for the 6 MCP tools
└── data/               # generated structured data (gitignored? not in .gitignore — see below)
    ├── tag_index.json     # 630 structured INCAR tags
    ├── non_tag_index.json # tutorials / how-tos / best practices / file pages
    ├── tag_stats.json     # frequency + top-5 values per tag (from incar_data.json)
    └── wiki_full.json     # 1,036 cleaned wiki pages (full content + url)
```

Raw inputs the preprocessor reads from `data/raw/`:
- `incar_data.json` — 10,176 real INCAR configurations
- `vasp_wiki_all_data.json` — 1,186 scraped VASP wiki pages

### CLI

```bash
python3 -m vasp_query tag LEFG           # tag description, default, related, url
python3 -m vasp_query search "EFG"       # searches tag_index + non_tag_index
python3 -m vasp_query search "POSCAR"    # file-format pages rank higher
python3 -m vasp_query stats [TAG]        # frequency + top values; omit TAG to list all
python3 -m vasp_query list              # all known tag names
python3 -m vasp_query related QUAD_EFG   # wiki-related tags
python3 -m vasp_query fullwiki LEFG      # full cleaned wiki content
python3 -m vasp_query incar ENCUT=400 NSW=0   # match-all filter; --any-match inverts
python3 -m vasp_query preprocess         # rebuild data/*.json from raw inputs
```

All output is JSON on stdout. Errors come back as `{"error": ..., "suggestion": ...}` (or `"matches": [...]` for ambiguous tags) with non-zero exit code.

### MCP server

Configured in `.mcp.json` at the repo root using **stdio** transport. The systemd unit in `vasp-mcp-systemd-services/` exposes the same server over **HTTP** on `0.0.0.0:8932` (`/mcp` path, `streamable-http` transport) for remote clients. Both can coexist; the HTTP one is for cross-machine access only.

Tools exposed (6, all return JSON strings):

| Tool              | Purpose                                                    |
| ----------------- | ---------------------------------------------------------- |
| `get_tag`         | Look up a tag by name (case-insensitive, fuzzy fallback)  |
| `search_tags`     | Cross-search tags + non-tag wiki pages (file pages boosted)|
| `get_tag_stats`   | Frequency + top values; omit name to list all              |
| `list_tags`       | All known tag names                                        |
| `get_related_tags`| Wiki-related tags for a given tag                          |
| `get_fullwiki`    | Full cleaned content for tag or file-format page           |

### Regenerating structured data

Whenever raw inputs change, or the preprocessor logic is modified:

```bash
python3 -m vasp_query preprocess
```

This calls `processor.preprocess()` which runs four steps in order:
1. `parse_wiki_to_index()` → `data/tag_index.json`
2. `parse_non_tag_to_index()` → `data/non_tag_index.json`
3. `make_wiki_full()` → `data/wiki_full.json`
4. `extract_tag_stats()` → `data/tag_stats.json`

The parser heuristics are tightly coupled to VASP wiki markup conventions — see `_parse_tag_page` (looks for `TITLE`, `= value`, `Default:`, `Description:` markers) and `_KNOWN_FILES` (whitelist of file-format pages like POSCAR, KPOINTS, etc. that the non-tag path lets through).

### MCP smoke tests

```bash
python3 -m vasp_query.test_mcp               # all 16 suites / ~75 assertions
python3 -m vasp_query.test_mcp --tool get_tag # single tool
python3 -m vasp_query.test_mcp --quiet       # only failures + summary
```

Expects the `mcp_server` module to import successfully (i.e. `mcp` / `fastmcp` packages installed) and the data files to exist. Exits non-zero on any failure.

### Installation / setup

```bash
pip install mcp fastmcp      # only non-stdlib dependency
# Optional: HTTP service for remote clients
(cd vasp-mcp-systemd-services && ./setup.sh)   # installs vasp-query.service to systemd --user
```

`.mcp.json` already wires up stdio transport; Claude Code loads it automatically when started in this directory. The `MIGRATION.md` file is a Chinese-language walkthrough for setting this up on a new machine.

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
| `vasp_wiki_scraper.py`  | Original scraper for `https://vasp.at/wiki/` — used to produce `vasp_wiki_all_data.json`; rare to re-run |

## Conventions & gotchas

- `vasp_query.mcp_server.py` parses `--host/--port/--transport` at **module import time** via `argparse`, so it must be invoked as `python3 mcp_server.py` (never `import mcp_server` from a parent process — arguments would be intercepted).
- Tag lookups are case-insensitive on the title field but exact match is preferred. Partial matches return `{"hint": ..., "matches": [...]}` rather than guessing.
- Search uses a custom scorer (see `_match_keyword` / `_score_keyword` in `query.py` and `mcp_server.py` — they are intentionally kept in sync; if you change one, change the other). Scores: exact title=100, substring=50, all-words-present=70, per-word hit=10.
- `vasp_query/data/*.json` files are generated, not hand-edited. After touching the parser, always re-run `preprocess` and re-run `test_mcp` to catch regressions.
- `.gitignore` is minimal (`__pycache__/`, `*.pyc`); the large `*.json` data files (raw + preprocessed) are tracked. `data/raw/incar_data.json` is ~16 MB, `data/raw/vasp_wiki_all_data.json` ~5.9 MB, `rag/vasp_wiki_all_data.json` ~5.7 MB.
