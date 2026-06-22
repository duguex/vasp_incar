# Changelog

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
