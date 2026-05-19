# VASP INCAR Knowledge Base & MCP Server

A comprehensive VASP parameter knowledge base designed for LLM agents, built around the `vasp_query` MCP (Model Context Protocol) server.

## What's inside

- **1,186 VASP Wiki pages** — scraped and structured from the official VASP documentation
- **10,176 real INCAR configurations** — collected from production calculations across multiple materials systems
- **MCP server** (`vasp_query/`) — 6 tools exposing tag lookup, search, statistics, and INCAR comparison to AI agents

## MCP Tools

| Tool | Description |
|------|-------------|
| `get_tag` | Look up a specific VASP INCAR tag with full documentation |
| `search_tags` | Search tags by keyword or category |
| `get_tag_stats` | Real-world usage statistics for each tag (from 10K+ configs) |
| `list_categories` | Browse tags by functional category |
| `compare_incar` | Side-by-side comparison of two INCAR files |
| `suggest_tags` | Suggest relevant tags for a given calculation type |

## Why this exists

LLMs know what VASP is, but they don't know what parameters to use for a specific material system. This MCP server gives AI agents access to structured VASP knowledge — both the official documentation AND real-world usage patterns — so they can autonomously configure and submit DFT calculations.

## Usage

```bash
# Start the MCP server
python vasp_query/mcp_server.py

# Or run queries directly
python -c "from vasp_query.processor import VaspQuery; vq = VaspQuery(); print(vq.get_tag('ENCUT'))"
```

## Data

- `vasp_wiki_all_data.json` — full VASP Wiki dump
- `incar_data.json` — 10,176 real INCAR tag statistics
- `POSCAR/` — reference POSCAR files for various material systems