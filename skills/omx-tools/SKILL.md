---
name: omx-tools
description: |
  Toolkit for working with OpenMX (DFT software). Provides omx-db for querying
  the full OpenMX v4.0 manual (FTS5 search, keyword lookup, section browsing,
  semantic search via RAG) and omx-gen for generating .dat input files from
  structure files (CIF/XYZ/POSCAR) using calculation templates. Use this skill
  when the user asks about OpenMX calculations, DFT input preparation, SCF
  convergence, mixing methods, k-point sampling, OpenMX keywords, manual
  sections, or any OpenMX-related materials science computation. Also use when
  the user wants to search technical documentation, look up calculation
  parameters, or prepare batch jobs for HPC clusters.
---

# omx-tools — OpenMX input generation and manual database

## 项目位置

- **仓库/项目目录:** `~/vasp_wiki/`
- **源 SKILL.md:** `~/vasp_wiki/skills/omx-tools/SKILL.md`
- **注册到 Hermes 的方式:** 软链接 `~/.hermes/skills/research/omx-tools/SKILL.md → ~/vasp_wiki/skills/omx-tools/SKILL.md`（项目文件更新后自动同步）
- **CLI 工具代码:** `~/vasp_wiki/omx_tools/`
- **SQLite 数据库:** `~/vasp_wiki/openmx.db`
- **HPC 作业提交:** 通过 `crisp` skill 提交生成的 `.dat` 文件到集群。crisp 负责 auto-detect → sbatch → running → fetch。详见 `skill_view(name='crisp')`。

This skill provides two CLI tools that output **JSON** when called with `--json`.
Always prefer `--json` for machine-readable output.  Error responses always
have the shape `{"error": "<message>", "exit": <code>}` and exit code 0 (so the
JSON is always the last thing on stdout).

## 1. `omx-db` — Manual database query

Query the OpenMX v4.0 manual database (`openmx.db`).  All subcommands accept
`--json` as a **global** flag (place it anywhere in argv after `omx-db`).

Symmetry aliases (match vasp-query naming): `tag`→`keyword`, `fullwiki`→`section`.
Related: `omx-db related <keyword|section> [--json]`.

Example corpus (official OpenMX `work/**/*.dat`, not multi-user stats):
```
omx-db example Kerker --json
omx-db example --intent geom_opt --json
omx-db cooccur scf.Mixing.Type scf.Kerker.factor --json
omx-db stats --examples --json
# rebuild: python3 scripts/index_omx_examples.py --root ~/openmx_container/openmx4.0/work --out data/omx_examples
```

### 1.1 FTS5 search

```
omx-db search <query> [--json]
```

JSON output:

```json
{
  "results": [
    {
      "sec_num": "16.1",
      "title": "SCF convergence basics",
      "rank": -6.13,
      "snippet": "…relevant text excerpt…"
    }
  ],
  "count": 20,
  "query": "user query"
}
```

Empty results: `{"results": [], "count": 0, "query": "..."}`.

### 1.2 Keyword lookup

```
omx-db keyword <keyword> [--json]
```

- If the keyword matches an **exact schema entry** (`schemas/keywords.json`),
  returns that entry directly as a dict with fields like `type`, `ase_key`,
  `default`, `valid_values`, `section`, `description`, `unit`, `source`.
- If no exact schema match, falls back to **DB index search** (fuzzy match
  against index_entries table).

DB fallback output:

```json
{
  "results": [
    {"keyword": "scf.Kgrid", "sec_num": "8.2", "title": "Keywords", "file": "s8_2_keywords.html"}
  ],
  "count": 27
}
```

Empty results: `{"results": [], "count": 0}`.

### 1.3 Section reader

```
omx-db section <num> [--json]
```

Section number formats: `"16"` (chapter), `"8.2"` (subsection), `"52.4.1"` (subsubsection).

JSON output (found):

```json
{
  "sec_num": "16",
  "title": "SCF convergence",
  "file": "s16_scf.html",
  "depth": 1,
  "content": "…first 2000 chars of section text…"
}
```

JSON output (not found):

```json
{
  "error": "Section not found: 99.99",
  "suggestions": [
    {"sec_num": "…", "title": "…"}
  ]
}
```

### 1.4 List sections

```
omx-db list [--json]
```

JSON output:

```json
{
  "sections": [
    {"sec_num": "5", "title": "Test calculation", "depth": 1}
  ]
}
```

### 1.5 File inventory

```
omx-db files [--type <html|pdf>] [--json]
```

JSON output:

```json
{
  "files": [
    {"path": "s16_scf.html", "type": "html", "category": "manual_v4", "size_bytes": 12345}
  ]
}
```

### 1.6 Database statistics

```
omx-db stats [--json]
```

JSON output:

```json
{
  "tables": {"sections": 281, "index_entries": 799, …},
  "files_by_category": {"manual_v4": 263, …},
  "files_by_type": {"html": 263, "pdf": 19},
  "db_size_mb": 3.4
}
```

### 1.7 Hybrid search (FTS5 + semantic → RRF)

```
omx-db hybrid <query> [--json] [--debug]
```

Combines FTS5 keyword search and semantic embedding search via Reciprocal Rank
Fusion (RRF).  Results show a `source` field: `"fts5"`, `"semantic"`, or
`"hybrid"` (both signals contributed).

Use `--debug` to trace the FTS5 scores, semantic similarities, and RRF fusion
weights.

JSON output:

```json
{
  "results": [
    {
      "sec_num": "16.1",
      "title": "SCF convergence basics",
      "score": 0.0325,
      "source": "hybrid"
    }
  ],
  "count": 20,
  "query": "scf convergence",
  "_debug": ["FTS5: 12 hits", "Semantic: 10 hits", "..."]
}
```

### 1.8 Semantic / RAG search

```
omx-db rag <query> [--json]
```

- Loads an embedding model (~9s on first call, cached subsequently).
- Returns top-10 results ranked by cosine similarity.
- In JSON mode the `--json` output skips the "Loading embedding model…"
  message.

JSON output:

```json
[
  {
    "sim": 0.752,
    "sec_num": "16.1",
    "title": "SCF convergence basics",
    "file": "s16_scf.html"
  }
]
```

### 1.9 Error shapes (omx-db)

All error responses include a `"suggestion"` field with an actionable next step
for the agent.

```
# Missing required argument
{"error": "No query provided", "suggestion": "Pass a search term like 'omx-db search scf convergence'."}
{"error": "No section number provided", "suggestion": "Pass a section number like 'omx-db section 16'."}

# Not found
{"error": "Section not found: 99.99", "suggestion": "Use 'omx-db list' to browse all sections.", "suggestions": [...]}
{"error": "Keyword 'foo' not found", "suggestion": "Try 'omx-db list' to see available sections, then browse for keywords manually."}
```

## 2. `omx-gen` — Input file generation

Generate OpenMX `.dat` input files from structure files (CIF, XYZ, POSCAR,
VASP, etc.).  Requires ASE (`pip install "omx-tools[gen]"`) and
`OPENMX_DFT_DATA_PATH` pointing to a DFT_DATA19 directory.

### 2.1 List templates

```
omx-gen --list-templates [--json]
```

JSON output (list of template objects):

```json
[
  {
    "name": "scf_band",
    "description": "SCF single-point with band structure (default for crystalline solids)",
    "auto_kpoints": true,
```

Available templates: `scf_band`, `scf_band_metal`, `scf_cluster`,
`geom_opt`, `band_dispersion`.

### 2.2 List keyword schema

```
omx-gen --list-keywords [--type <type>] [--json]
```

Optional `--type` filter: `string`, `integer`, `float`, `bool`,
`tuple_integer`, `tuple_float`, `matrix`.

JSON output (list of keyword entries):

```json
[
  {
    "name": "scf.Kgrid",
    "ase_key": "scf_kgrid",
    "type": "tuple_integer",
    "default": null,
    "valid_values": null,
    "description": "…",
    "section": "§8.1; §8.2; …",
    "unit": null,
    "source": ["ase", "html"]
  }
]
```

### 2.3 Single keyword detail

```
omx-gen --keyword <KEY> [--json]
```

Returns the schema entry for a single keyword (same shape as list-keywords
entries, without the `name` field prepended).

### 2.4 Generate input file

```
omx-gen <structure.cif> -t <template> [options] [--json]
```

Required: structure file path + `-t` / `--template`.

Key options:
- `-o <file>` — output path (default: `<stem>.dat`)
- `-k NX NY NZ` — override k-point grid
- `--kspacing F` — auto k-point spacing in 1/Å (default 0.33)
- `-x <XC>` — override XC functional (PBE, LDA, etc.)
- `--spin <Off|On|NC>` — spin polarization
- `--cutoff N` — energy cutoff in eV
- `-s KEY=VALUE` — set arbitrary keyword (repeatable)
- `-d` / `--dry-run` — print to stdout instead of writing file
- `-v` — verbose (stderr)

The `-d` / `--dry-run` flag prints the `.dat` content to stdout
(not wrapped in JSON — use for pipe to file).

### 2.5 omx-gen error shapes

```
# No structure file provided
{"error": "STRUCTURE file is required. Use --help for usage.", "exit": 1}

# File not found
{"error": "structure file 'nonexistent.cif' not found", "exit": 1}

# Unknown keyword
{"error": "Keyword 'NotExist' not found in schema", "exit": 1}

# Missing DFT_DATA19
{"error": "DATA.PATH not set. Set OPENMX_DFT_DATA_PATH to your DFT_DATA19 directory (e.g. /mnt/shared/DFT_DATA19).", "exit": 1}
```

## 3. Environment variables

| Variable | Tool | Purpose | Default |
|---|---|---|---|
| `OPENMX_DB_PATH` | omx-db | Path to `openmx.db` | `<package_dir>/../openmx.db` |
| `OPENMX_DFT_DATA_PATH` | omx-gen | Path to DFT_DATA19 directory | Falls back to `<workspace>/openmx4.0/DFT_DATA19`, then error |

## 4. Common workflows

### 4.1 Research a topic → read the section

```bash
omx-db search "SCF convergence metallic" --json
omx-db section 16 --json        # §16 SCF convergence
omx-db section 16.1 --json      # §16.1 SCF convergence basics
```

### 4.2 Find a keyword → understand its type

```bash
omx-db keyword scf.Mixing.Type --json
omx-gen --keyword scf.Mixing.Type --json
```

Both tools can look up a keyword; `omx-db keyword` tries the schema first
then falls back to the DB index, while `omx-gen --keyword` only checks
the schema (and errors if not found).

### 4.3 Generate an input file

```bash
# 1. Pick a template
omx-gen --list-templates --json

# 2. Generate
omx-gen structure.cif -t scf_band -k 4 4 4 -o myjob.dat

# 3. Dry-run to preview
omx-gen structure.cif -t scf_band -d > myjob.dat
```

### 4.4 Semantic search (vague queries)

```bash
omx-db rag "how to improve SCF convergence for metallic systems" --json
```

## 5. JSON output conventions

- **Success**: varies by command (see above).  Always valid JSON.
- **Error**: always `{"error": "<message>", "exit": <code>}`.
- **Empty results**: `{"results": [], "count": 0}` (omx-db) or `[]` (omx-gen
  listing with no match).
- **Exit code**: always 0 for JSON mode (so piped JSON parsing never breaks).
  Intended exit code is embedded in the `"exit"` field of error responses.
- **ANSI escape codes**: stripped in JSON mode.  No `\033[...m` in output.
