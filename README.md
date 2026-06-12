# VASP INCAR Knowledge Base & MCP Server

A comprehensive VASP parameter knowledge base designed for LLM agents, built around the `vasp_query` MCP (Model Context Protocol) server.

## What's inside

- **1,273 VASP Wiki pages** — scraped and structured from the official VASP documentation
- **10,176 real INCAR configurations** — collected from production calculations across multiple materials systems
- **MCP server** (`vasp_query/`) — 6 tools exposing tag lookup, hybrid search, statistics, related tags, and full wiki content to AI agents

## MCP Tools

| Tool | Description |
|------|-------------|
| `get_tag` | Look up a specific VASP INCAR tag with full documentation |
| `search_tags` | Hybrid search across tags and wiki pages (BM25 + semantic) |
| `get_tag_stats` | Real-world usage statistics for each tag (from 10K+ configs) |
| `list_tags` | All known tag names |
| `get_related_tags` | Wiki-related tags for a given tag |
| `get_fullwiki` | Full cleaned wiki content for a tag or file-format page |

## Why this exists

LLMs know what VASP is, but they don't know what parameters to use for a specific material system. This MCP server gives AI agents access to structured VASP knowledge — both the official documentation AND real-world usage patterns — so they can autonomously configure and submit DFT calculations.

## Usage

```bash
# Start the MCP server (stdio transport; also auto-loaded via .mcp.json)
python3 vasp_query/mcp_server.py

# Rebuild preprocessed indexes from raw data
python3 -m vasp_query preprocess

# CLI examples
python3 -m vasp_query tag ENCUT
python3 -m vasp_query search "energy cutoff"
```

## Data

Raw inputs live in `data/raw/`:
- `data/raw/incar_data.json` — 10,176 real INCAR tag statistics
- `data/raw/vasp_wiki_all_data.json` — full VASP Wiki dump
- `examples/POSCAR` — reference POSCAR for SiC supercell

Legacy `pymatgen`-based utilities are in `legacy_scripts/` (see `legacy_scripts/README.md`).
