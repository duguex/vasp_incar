# Adding a New DFT Code to dft-tools

This guide walks through integrating a new DFT code (e.g. CASTEP, Quantum ESPRESSO, FHI-aims) into the `dft-tools` framework. The process has 6 steps; each is independent and commit-able.

**Prerequisites:** You've read `PLAN.md` and understand the plugin architecture.

---

## Step 1: Create the package skeleton

```bash
cd dft-tools/
mkdir -p newcode_tools/{parsers,writers,schemas,data,tests}
touch newcode_tools/__init__.py
```

Or copy the template:

```bash
cp -r dft_utils/templates/code_skeleton/ newcode_tools/
```

Register the package in `pyproject.toml`:

```toml
[tool.setuptools.packages.find]
include = ["vasp_query*", "omx_tools*", "dft_utils*", "newcode_tools*"]
```

---

## Step 2: Index the manual

Build a searchable knowledge base from the code's documentation.

**Option A — SQLite FTS5** (recommended for HTML/PDF manuals):

```python
import sqlite3

db = sqlite3.connect("newcode.db")
db.execute("CREATE VIRTUAL TABLE docs USING fts5(title, content)")
# Parse HTML/PDF, insert sections
db.executemany("INSERT INTO docs(title, content) VALUES (?, ?)", sections)
db.commit()
```

**Option B — JSON index** (simpler, for structured data):

```python
import json
index = [{"title": "...", "content": "...", "keywords": [...]}]
json.dump(index, open("newcode_tools/data/index.json", "w"))
```

**Schema conventions:**

| Table | Purpose | Example |
|-------|---------|---------|
| `sections` | Document sections with hierarchy | `sec_num`, `title`, `file_path` |
| `sections_fts` | FTS5 full-text search | title + content indexed |
| `section_embeddings` | Semantic search vectors | `section_id`, `embedding` BLOB |
| `keywords` | Keyword-to-section mapping | `keyword`, `sec_num`, `title` |

See `omx_tools/scripts/extract_keywords.py` for a real extraction pipeline.

---

## Step 3: Write parsers and writers

Create input file parsers in `newcode_tools/parsers/`:

```python
# newcode_tools/parsers/input_file.py
def parse_input(path: str) -> dict:
    """Parse a NEWCODE input file into a typed dict."""
    # Use pymatgen, ASE, or custom parser
    params = {}
    with open(path) as f:
        for line in f:
            if "=" in line:
                k, v = line.split("=", 1)
                params[k.strip()] = v.strip()
    return params
```

Create output writers in `newcode_tools/writers/`:

```python
# newcode_tools/writers/input_file.py
from dft_utils import die_json

def write_input(params: dict, path: str, json_output: bool = False) -> None:
    """Write a NEWCODE input file from typed dict."""
    try:
        with open(path, "w") as f:
            for k, v in params.items():
                f.write(f"{k} = {v}\n")
    except OSError as e:
        die_json(f"cannot write {path}: {e}", json_output=json_output)
```

**Error conventions:**
- Fatal errors: `die_json(msg, json_output=json_output)` (prints JSON, exits 0)
- Returnable errors: `make_error(msg, suggestion=...)` (returns dict)
- All JSON output to stdout, never stderr

---

## Step 4: Create the plugin

```python
# newcode_tools/plugin.py
from pathlib import Path
from dft_utils.protocol import CodePlugin, register

_PKG = Path(__file__).resolve().parent

plugin = CodePlugin(
    name="newcode",
    display_name="NEWCODE",
    description="NEWCODE knowledge base and tools",
    version="0.1.0",
    package_dir=_PKG,
    skills=[_PKG.parent / "skills" / "newcode" / "SKILL.md"],
    cli_module="newcode_tools.query",
    generators=[],
    converters=[],
)
register(plugin)
```

Verify it's discovered:

```bash
python3 -c "from dft_utils import discover; print(discover().keys())"
# → dict_keys(['vasp', 'omx', 'newcode'])
```

---

## Step 5: Implement CLI commands

Create `newcode_tools/query.py` with `build_parser()` and `main()`. See `vasp_query/query.py` for a complete example with argparse + subparsers.

**Available shared utilities:**

| Function | From | Purpose |
|----------|------|---------|
| `make_fts5_query(keyword)` | `dft_utils.search` | Build FTS5-safe MATCH string |
| `rrf_merge(signals, key_fn, ...)` | `dft_utils.search` | Fuse multiple ranked lists |
| `load_data(path, model=...)` | `dft_utils.version` | Load JSON with version envelope |
| `check_version(version, source)` | `dft_utils.version` | Warn on data version mismatch |
| `make_error(msg, suggestion)` | `dft_utils.error` | Build error dict |
| `die_json(msg, json_output)` | `dft_utils` | Print JSON error and exit |
| `debug_log`, `get_debug_log` | `dft_utils` | Debug tracing |

**Register entry points** in `pyproject.toml`:

```toml
[project.scripts]
newcode-query = "newcode_tools.query:main"
```

---

## Step 6: Add cross-code converters (optional)

Register a converter to/from another DFT code:

```python
# newcode_tools/converters.py
from dft_utils.convert import register

def newcode_to_vasp(input_path: str, **kwargs) -> str:
    """Convert NEWCODE input to VASP INCAR."""
    # ... implementation ...
    return output_path

register("newcode", "vasp", newcode_to_vasp, "NEWCODE → VASP INCAR")
```

The converter is auto-imported when `dft convert` is called.

---

## Verification checklist

```bash
# 1. Plugin discovery works
python3 -c "from dft_utils import discover; assert 'newcode' in discover()"

# 2. CLI works
dft newcode search "test"
dft newcode --help

# 3. Tests pass
python3 -m pytest newcode_tools/tests/

# 4. Converter works (if implemented)
dft convert newcode:vasp input.in -o INCAR

# 5. Skill registration paths are valid
ls -la skills/newcode/SKILL.md

# 6. dft --list-codes shows new entry
dft --list-codes | grep newcode
```

---

## Template reference

| File | Purpose |
|------|---------|
| `dft_utils/templates/code_skeleton/__init__.py` | Package init with version |
| `dft_utils/templates/code_skeleton/plugin.py` | Plugin registration |
| `dft_utils/templates/code_skeleton/query.py` | Basic CLI with search + list |
| `dft_utils/templates/code_skeleton/tests/conftest.py` | Test fixture with capsys |
