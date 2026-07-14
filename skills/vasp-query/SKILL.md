---
name: vasp-query
description: |
  Toolkit for querying VASP INCAR parameter knowledge. Provides vasp-query for
  tag lookup, hybrid/rag search, INCAR statistics, co-occurrence analysis, and
  light INCAR generation via vasp-gen. Use this skill when the user asks about
  VASP calculations, INCAR parameters, DFT input preparation, SCF convergence,
  functionals (PBE, HSE, SCAN, etc.), k-point sampling, relaxation setups, band
  structure, DOS, or any VASP-related computation. Also use when the user needs
  help with VASP wiki documentation, tag meanings, or real-world INCAR usage
  statistics.
---

# vasp-query — VASP INCAR parameter knowledge base
## 项目位置

- **仓库/项目目录:** `~/vasp_wiki/`
- **源 SKILL.md:** `~/vasp_wiki/skills/vasp-query/SKILL.md`
- **注册到 Hermes 的方式:** 软链接 `~/.hermes/skills/research/vasp-query/SKILL.md → ~/vasp_wiki/skills/vasp-query/SKILL.md`（项目文件更新后自动同步）
- **CLI 工具代码:** `~/vasp_wiki/vasp_query/`
- **知识数据:** `~/vasp_wiki/vasp_query/data/`（676 个 INCAR 标签 + 507 个 wiki 页面 + 统计 + 共现矩阵）
- **原始数据:** `~/vasp_wiki/data/raw/`（10,176 个真实 INCAR 配置、1,273 个 VASP Wiki 页面）

This skill provides CLI tools that output **JSON** by default, with `-H`/`--human` for Markdown. Error responses always have the shape `{"error": "<message>", "suggestion": "<actionable advice>"}` with a non-zero exit code. When a tag name is ambiguous, the response is `{"hint": "<input>", "matches": [...]}`.

## 1. `vasp-query` — Tag query and search

Run via `python3 -m vasp_query <command> [options]`.

### 1.1 Tag lookup

```
python3 -m vasp_query tag <TAG> [-H]
```

JSON output:

```json
{
  "title": "ENCUT",
  "value": "[real]",
  "default": "Default: maximum ENMAX across POTCAR files",
  "description": "ENCUT sets the cutoff energy for the plane-wave basis set…",
  "related": ["ENMAX", "ENAUG", "PREC", "NGX"],
  "config_samples": {"ISMEAR": 6, "PREC": "Accurate", …},
  "stats": {"count": 8765, "common_values": [{"value": "400", "count": 2800}, …]},
  "url": "https://vasp.at/wiki/ENCUT"
}
```

Not found: `{"hint": "ENCUTX", "matches": ["ENCUT", "ENCUTGW", "ENCUTGWSOFT"]}`.

### 1.2 Hybrid search

```
python3 -m vasp_query search <query> [--type=tag|page|all] [--top-k N] [--debug] [-H]
```

Two-stage context7-inspired pipeline:
- **T1** — exact tag title match, file page exact match (covers ~90% of human queries, ~10ms)
- **T2** — file page fallback for formats like POSCAR, OUTCAR (~2ms)
- **T3** — hybrid BM25 (tantivy) + semantic (sentence-transformers BGE-small-384) → Reciprocal Rank Fusion (~15s CLI first call)
- **T4** — legacy substring + heuristic scoring safety net

JSON output:

```json
{
  "results": [
    {"id": "tag:ENCUT", "type": "tag", "score": 8.5},
    {"id": "page:Energy cutoff", "type": "page", "title": "Energy cutoff", "score": 6.2}
  ],
  "query": "energy cutoff"
}
```

Empty results: `{"results": [], "query": "..."}`.

### 1.2b Explicit hybrid + RAG + aliases

```
python3 -m vasp_query hybrid <query> [-n N] [--debug] [-H]
python3 -m vasp_query rag <query> [-k N] [-H]
python3 -m vasp_query keyword ENCUT     # alias of tag
python3 -m vasp_query section ENCUT     # alias of fullwiki
vasp-gen -t scf -o INCAR                # light INCAR templates
dft vasp gen -t relax -d
```

Templates: `scf`, `scf_metal`, `relax`, `band`, `md`. INCAR only (no POTCAR/KPOINTS).

### 1.3 Tag statistics

```
python3 -m vasp_query stats [TAG] [-k N] [-H]
```

With a tag name: frequency and top N most common values from 10K+ real INCARs.

```json
{
  "ENCUT": {"count": 8765, "top_values": [{"value": "400", "count": 2800}, …]}
}
```

Without a tag name: all tags with counts.

### 1.4 List all tags

```
python3 -m vasp_query list [-H]
```

Returns all 676 known INCAR tag names.

### 1.5 Related tags

```
python3 -m vasp_query related <TAG> [-H]
```

Returns wiki-related tags (tags appearing together in wiki documentation).

### 1.6 Full wiki content

```
python3 -m vasp_query fullwiki <TAG> [-H]
```

Returns the full cleaned wiki content for a tag or file-format page.

### 1.7 INCAR config query

```
python3 -m vasp_query incar KEY=VALUE [KEY=VALUE ...] [--any-match] [-H]
```

Match-all (default) or match-any filter against 10K+ real INCAR configurations.

### 1.8 Co-occurrence analysis

```
python3 -m vasp_query cooccur <TAG1> <TAG2> [-H]
```

Co-occurrence statistics from 10K+ configurations, with wiki relationship info.

### 1.9 Wiki fetch

```
python3 -m vasp_query fetch [--check]
```

Fetch latest wiki data from vasp.at. Use `--check` to detect changes (~2s).

### 1.10 Data preprocess

```
python3 -m vasp_query preprocess [--check]
```

Rebuild all structured data from raw inputs. Use `--check` to detect staleness.

### 1.11 Error shapes

```
# Tag not found (ambiguous)
{"hint": "ENCU", "matches": ["ENCUT", "ENCUTGW", "ENCUTGWSOFT", ...]}

# Tag not found (no match)
{"error": "tag 'XYZZY' not found", "suggestion": "use 'list' to see all tags"}

# Search error
{"error": "search failed: <reason>", "suggestion": "...", "partial": [...]}
```

## Backends

The `vasp-query` tool supports two search backends:

- **Tantivy BM25** (default) — fast full-text search, requires `tantivy` package
- **SQLite FTS5** (fallback) — zero extra dependencies, auto-used when tantivy unavailable

The CLI auto-detects which backend is available. Semantic search (sentence-transformers) is an additional layer on top of either backend, enabled when `sentence-transformers` is installed.

## Data

Knowledge data lives in `vasp_query/data/` and `data/raw/`:

| File | Contents |
|------|----------|
| `tag_index.json` | 676 INCAR tags with descriptions, defaults, related tags |
| `non_tag_index.json` | 507 tutorial/how-to/file-format pages |
| `wiki_full.json` | 1,107 cleaned wiki pages with full content |
| `tag_stats.json` | Frequency + top values per tag from 10K+ configs |
| `tag_configs.json` | Typical INCAR context configs per tag |
| `tag_cooccur.json` | Precomputed co-occurrence matrix (207 tags) |
| `search_index/` | Tantivy BM25 index (1,183 docs) |
| `search.db` | SQLite FTS5 search index (zero-dependency fallback) |
| `doc_vectors.npy` | Sentence-transformers embeddings (1,183×384) |
| `raw/incar_data.json` | 10,176 real INCAR configurations |
| `raw/vasp_wiki_all_data.json` | 1,273 scraped VASP wiki pages |
| `raw/_meta.json` | Fetch metadata |

## Quality / gotchas

- Tag lookups are case-insensitive but exact match is preferred. Partial matches return `{"hint": ..., "matches": [...]}`.
- `data/*.json` files are generated by `preprocess`, not hand-edited. After touching the parser, re-run `preprocess`.
- ANSI escape codes are never output in JSON mode.
- Set `USE_TF=0` before importing sentence-transformers if TensorFlow is not needed.
