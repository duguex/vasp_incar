# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.1] - 2026-06-12

### Fixed

- **`hybrid_search` Signal B executed 5× per query** ([#1](https://github.com/duguex/vasp_incar/issues/1), PR [#7](https://github.com/duguex/vasp_incar/pull/7))
  The "Signal B: tag-only semantic" block was mis-indented inside the Signal A `for` loop in `vasp_query/_common.py:390-402`, causing 5× wasted work per hybrid search (reloading `tag_vectors.npy`, recomputing `np.dot`, and over-weighting the top tag-only doc by 5× via repeated RRF accumulation). Dedented to be a sibling of the Signal A loop.

- **`--type` filter silently switched search algorithms** ([#2](https://github.com/duguex/vasp_incar/issues/2), PR [#7](https://github.com/duguex/vasp_incar/pull/7))
  In `cmd_search`, the T3 hybrid search was gated by `if not args.type:`. Passing `--type` skipped the entire BM25 + semantic tier and fell through to the T4 legacy keyword fallback — a different algorithm with no warning. Moved the type filter to apply as a post-filter on the hybrid results.

- **Dead Tier 2 file-page scan in `cmd_search`** ([#2](https://github.com/duguex/vasp_incar/issues/2), PR [#7](https://github.com/duguex/vasp_incar/pull/7))
  The 10-line T2 block manually re-scanned `non_tag` for file pages, but `resolve_tag` with `non_tag=non_tag` already does the same scan and returns via T1b. T2 was unreachable on hit and dead on miss. Removed.

### Performance

- **Cache `TAG_CONFIGS` / `TAG_STATS` / `TAG_COOCCUR` at MCP server module load** ([#3](https://github.com/duguex/vasp_incar/issues/3), PR [#8](https://github.com/duguex/vasp_incar/pull/8))
  `search_tags` re-parsed ~700 KB of JSON on every request, even though the data is immutable after `preprocess`. Mirrors the pattern already used for `_INDEX` / `_NON_TAG` / `_STATS` / `_FULLWIKI`.

- **Avoid re-encoding the tag subset in `build_search_indexes`** ([#6](https://github.com/duguex/vasp_incar/issues/6), PR [#8](https://github.com/duguex/vasp_incar/pull/8))
  `model.encode()` was called twice: once for all 1,183 doc texts and once for the 676 tag docs. The tag docs are a strict subset of the full docs, so the second pass can be replaced with `embeddings[list(tag_indices)]`. Output is bit-identical to a slice of `doc_vectors.npy` (no float32 noise from a separate encode). Roughly halves embedding compute in `preprocess`.

### Changed

- **Deleted `_match_keyword_legacy` / `_score_keyword_legacy`** ([#4](https://github.com/duguex/vasp_incar/issues/4), PR [#10](https://github.com/duguex/vasp_incar/pull/10))
  `vasp_query/mcp_server.py` defined these as byte-equivalent duplicates of `match_keyword` / `score_keyword` in `vasp_query/_common.py` (which `query.py` already imports from). The local copies also did `import re` inside the function body on every call. Replaced with imports from `_common`.

- **Data-driven alias map** ([#5](https://github.com/duguex/vasp_incar/issues/5), PR [#10](https://github.com/duguex/vasp_incar/pull/10))
  The hardcoded `_TERM_MAP` is now a built-in fallback; the user-editable `data/aliases.json` takes precedence and is loaded via the new `load_aliases()` helper. Adding a new alias (`"dft-d3": "IVDW"`, `"pbe0": "HFSCREEN"`, etc.) is a data change, not a code change.

- **Skipped-page auto-discovery for `generate_missing_tags`** ([#5](https://github.com/duguex/vasp_incar/issues/5), PR [#10](https://github.com/duguex/vasp_incar/pull/10))
  `parse_wiki_to_index` now persists the list of wiki titles that failed parsing to `data/skipped_pages.json`. `generate_missing_tags` reads it and unions with the `MINIMUM_OVERRIDE` set (`{ENMAX, ENMIN, EXX}`). The hardcoded 3-tag band-aid is now augmented by auto-discovery of any other silently dropped tags.

### Added

- `data/aliases.json` — user-editable alias map (13 entries, mirrors the built-in defaults).
- `data/skipped_pages.json` — list of wiki titles dropped by `_parse_tag_page`'s heuristics; drives `generate_missing_tags` auto-discovery.

### Tests

- 16 → 21 tests in `test_cli.py` (added 4 new tests: alias loading, alias override, data-driven resolve, skipped-pages persistence).
- 75 → 78 tests in `test_mcp.py` (added 3 new tests: Signal B called once, search-tags caching, search-files shape fix).
- `test_search_files` updated to accept both T1b (raw `title` at top level) and T1 (`info.title`) result shapes.

## [0.2.0] - 2026-06-09

### Added

- Hybrid search pipeline (tantivy BM25 + sentence-transformers BGE-small semantic embeddings → RRF fusion).
- Tiered search (T1 exact → T1b file page → T2 file-page fallback → T3 hybrid → T4 legacy keyword).
- Fetcher (`vasp_query/fetcher.py`) — VASP wiki scraper with `fetch` and `fetch --check` subcommands.
- Co-occurrence matrix (`data/tag_cooccur.json`).
- Tag config samples (`data/tag_configs.json`).
- Auto-generated tag entries from `incar_data.json` for tags missing from the wiki.
- New CLI subcommands: `fetch`, `cooccur`.
- New CLI flags: `-H` / `--human`, `--debug`, `--type`, `-k` / `--top-k`, `--check` (preprocess).

### Changed

- MCP server refactored: `create_app()` factory + import-safe tool functions (no module-level argument parsing).
- `load_data()` adds a `{"_version": ..., "data": ...}` envelope to all generated JSON files.
- README + CLAUDE.md aligned with the actual MCP server surface.

[0.1.0] and earlier — pre-MCP redesign.
