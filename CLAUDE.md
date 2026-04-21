# VASP INCAR Query Tool

This directory contains `vasp_query`, a CLI tool for querying VASP INCAR parameters and configurations.

## Quick reference

```bash
python3 -m vasp_query tag LEFG           # Look up a tag
python3 -m vasp_query search "EFG"       # Search tags by keyword
python3 -m vasp_query stats ENCUT        # Show tag statistics
python3 -m vasp_query list               # List all tags
python3 -m vasp_query related QUAD_EFG   # Show related tags
python3 -m vasp_query fullwiki LEFG      # Get full wiki content
```

All output is JSON for machine parsing.

## MCP server

The MCP server is registered in `.mcp.json`. When Claude Code starts in this directory, the `vasp-query` MCP server will be available with these tools:

- `get_tag(name)` — Get tag description, default value, related tags
- `search_tags(keyword, limit=20)` — Search tags by keyword
- `get_tag_stats(name?)` — Tag frequency and common values
- `list_tags()` — List all known tags
- `get_related_tags(name)` — Wiki-related tags
- `get_fullwiki(title)` — Full wiki page content

## Data

- `incar_data.json` — 10,176 real INCAR configurations
- `vasp_wiki_all_data.json` — ~1,186 VASP wiki pages
- `vasp_query/data/` — Preprocessed structured data (run `python3 -m vasp_query preprocess` to regenerate)
