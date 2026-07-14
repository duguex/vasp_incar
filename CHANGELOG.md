## [Unreleased]

### Added
- **CLI symmetry (VASP ↔ OpenMX)**:
  - `vasp-query hybrid` / `vasp-query rag` (semantic doc vectors)
  - `omx-db related` (keyword/section neighbors)
  - Cross aliases: VASP `keyword`→tag, `section`→fullwiki; OpenMX `tag`→keyword, `fullwiki`→section
  - **`vasp-gen`**: light INCAR templates (`scf`, `scf_metal`, `relax`, `band`, `md`); `dft vasp gen`
- **`vasp-gen` suite**: optional `KPOINTS` via pymatgen (`--kspacing` / `--kdensity` / `--kpoints`), optional `POSCAR` rewrite, optional `POTCAR` when `PMG_VASP_PSP_DIR` is set (never redistributed).
- **OpenMX example corpus**: index official `work/**/*.dat` → `data/omx_examples/`; CLI `omx-db example`, `omx-db cooccur`, `omx-db stats --examples` (demonstration corpus, not multi-user INCAR-scale).
- **Semantic round-trip Phase 1**: VASP→mapping→VASP preserves NSW=0, ISMEAR/SIGMA, IBRION/ISIF, exact ALGO; `forward(..., return_report=True)` for unmapped/dropped; `omx_tools/semantic_roundtrip.py` + fixtures under `tests/fixtures/semantic/vasp/`. Spec: `docs/superpowers/specs/2026-07-14-semantic-roundtrip-design.md`.
- Spec/plan: `docs/superpowers/specs/2026-07-14-cli-symmetry-design.md`, `docs/superpowers/plans/2026-07-14-cli-symmetry.md`

### Fixed
- **`dft convert` argparse**: convert subparser accepts remainder args (`src:dst input …`).
- **`aliases.json` version envelope**: `_version: 0.3.0`.

### Changed
- **Archive standalone `~/omx`**: `~/archive/2026-07-dft-merge/omx` (2026-07-14).
- **Hermes skills**: point at `~/vasp_wiki/skills/…`.
- **TODO / ROADMAP**: Items 1–4 marked done.

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
