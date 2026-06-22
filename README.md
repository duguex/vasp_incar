# VASP INCAR Knowledge Base

A comprehensive VASP parameter knowledge base designed for LLM agents, built around the `vasp-query` CLI tool and Skill interface.

## What's inside

- **1,273 VASP Wiki pages** — scraped and structured from the official VASP documentation
- **10,176 real INCAR configurations** — collected from production calculations across multiple materials systems
- **Skill interface** (`skills/vasp-query/SKILL.md`) — primary agent integration via registered Skill
- **CLI tool** (`vasp_query/`) — 12 subcommands for tag lookup, hybrid search, statistics, and more

## Quick start

```bash
# Tag lookup
python3 -m vasp_query tag ENCUT

# Hybrid search (BM25 + semantic)
python3 -m vasp_query search "energy cutoff"
```

## Skill Registration

The primary agent interface is the Skill file at `skills/vasp-query/SKILL.md`. Register it:

```bash
mkdir -p ~/.hermes/skills/research/vasp-query
ln -s ~/vasp_incar/skills/vasp-query/SKILL.md ~/.hermes/skills/research/vasp-query/SKILL.md
```

## CLI Subcommands

| Subcommand | Purpose |
|------------|---------|
| `tag` | Look up a specific INCAR tag with full documentation |
| `search` | Hybrid search across tags and wiki pages (BM25 + semantic) |
| `stats` | Real-world usage statistics for each tag (from 10K+ configs) |
| `incar` | Query INCAR configurations by tag conditions |
| `related` | Wiki-related tags for a given tag |
| `list` | All known tag names |
| `fullwiki` | Full cleaned wiki content for a tag or file-format page |
| `cooccur` | Co-occurrence analysis from real INCAR configurations |
| `preprocess` | Rebuild structured data from raw inputs |
| `fetch` | Fetch latest wiki data from vasp.at |

## Data

Knowledge data lives in `vasp_query/data/` and `data/raw/`:

- `vasp_query/data/tag_index.json` — 676 INCAR tags with descriptions, defaults, related tags
- `vasp_query/data/non_tag_index.json` — 507 tutorial/how-to/file-format pages
- `vasp_query/data/tag_stats.json` — Frequency + top values per tag from 10K+ configs
- `vasp_query/data/search.db` — SQLite FTS5 search index (auto-built, zero-dependency)
- `data/raw/incar_data.json` — 10,176 real INCAR configurations
- `data/raw/vasp_wiki_all_data.json` — full VASP Wiki dump

## Installation

```bash
pip install pydantic sentence-transformers   # tag lookup + semantic search
pip install tantivy                          # optional: BM25 search (sqlite3 stdlib used otherwise)
```
