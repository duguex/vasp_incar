## [0.3.0] - 2026-06-30

### Added
- **Merged project**: `dft-tools` — combines `vasp-query` (v0.2.0) and `omx-tools` (v0.1.0) under a single package
- **Shared `dft_utils` package**: `DATA_VERSION`, debug_log, die_json, load_json — common utilities for both sub-packages
- **OpenMX toolchain** (`omx_tools/`): `omx-db`, `omx-gen`, `vasp2omx`, `omp2vasp` — manual database query, input generation, bidirectional VASP↔OpenMX format conversion
- **5 entry points**: `vasp-query`, `omx-db`, `omx-gen`, `vasp2omx`, `omp2vasp`
- **SQLite FTS5 manual database** (`openmx.db`): 281 sections, 799 index entries from OpenMX v4.0 HTML manual
- **OpenMX input templates**: `scf_band`, `scf_band_metal`, `scf_cluster`, `geom_opt`, `band_dispersion`
- **VASP↔OpenMX parameter mapping**: 27 mapping rules in `omx_tools/schemas/vasp_to_ase.json`
- **omx_tools test suite** (110+ tests): database, generator, parsers, writers, vasp2omx, integration

### Changed
- **Package name**: `vasp-query` → `dft-tools` (v0.3.0)
- **pydantic** now properly declared as hard dependency in `pyproject.toml`
- **Optional extras** restructured: `semantic` (shared), `search`/`fetch` (vasp), `gen`/`vasp2omx` (omx), `vasp`/`omx`/`all` (combos)
- **CLAUDE.md** rewritten to cover both toolchains
- **README.md** rewritten with merged project info
- **AGENTS.md** rewritten with complete monorepo structure
- **Skill files** path references moved from `~/vasp_incar/` / `~/openmx_container/` to `~/vasp_wiki/`
- `.gitignore` extended for standard Python artifacts

### Fixed
- `dft_utils.load_json()` now returns `None` on `FileNotFoundError` (was `sys.exit()` in omx_tools version)

## [0.2.0] - 2026-06-22

### Added
- **Skill interface** (`skills/vasp-query/SKILL.md`): primary agent interface
- **Keyword schema** (`schemas/keywords.json`): 623 keywords with type annotations (~86% auto-inferred from wiki data)
- **SQLite FTS5 search backend**: zero-dependency alternative to tantivy, auto-built during preprocess
- **`pyproject.toml`**: proper Python package with entry points and dependency groups
- Version bumped to 0.2.0

### Removed
- **MCP server** (`mcp_server.py`, `test_mcp.py`, `vasp-mcp-systemd-services/`): fully removed. Agent integration now uses Skill only.
- **INCAR input generator** (`incar-gen` command, `schemas/templates.json`): removed. Mature tools like pymatgen/ASE already handle this.
- `.mcp.json` and `.claude/settings.local.json` removed
- MCP references removed from all documentation

## [0.1.0] - 2026-06-12
...
