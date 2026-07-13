# Agent notes (vasp_wiki)

> CLI detail and gotchas that lived only in the former CLAUDE dump.  
> Canonical rules: [`../AGENTS.md`](../AGENTS.md). Conventions: [`agent-conventions.md`](./agent-conventions.md).

### Gotchas
- `vasp_query/data/*.json` are git-tracked (large files ~6 MB each).
- Set `USE_TF=0` before importing sentence-transformers if TensorFlow not needed.
- pydantic is a hard runtime dep (now in `pyproject.toml`).
- `docs/MIGRATION.md` references the removed MCP server — outdated.
- `aliases.json` version may lag behind code version; triggers a `UserWarning` until next `preprocess`.
- omx-tools `tests/test_integration.py` requires Singularity container at `/mnt/shared/` — skipped when absent.

## Quality metrics

| Category | What to watch | Why it matters |
|----------|---------------|----------------|
| **Coverage** | % of VASP parameters captured (target: 90%+) | Users can't query what isn't indexed |
| **Search accuracy** | Top-3 hit rate; false positive rate | Core UX for both humans and agents |
| **Data freshness** | `_version` sync between code and data files | Stale data silently misleads users |
| **Parse stability** | Wiki/HTML format changes break nothing | VASP wiki and OpenMX markup not guaranteed stable |
| **Latency** | Time from query to response | Above ~500ms degrades CLI experience |
| **Test coverage** | CLI pytest (22 vasp + 110 omx) | Low coverage makes regression easy |
| **Error UX** | Every error must include actionable `suggestion` | `"not found"` without next step is useless to agents |


## CLI reference

### VASP commands (`vasp-query`)

```bash
python3 -m vasp_query tag ENCUT          # tag description, default, related, url
python3 -m vasp_query tag ENCUT -H       # human-readable Markdown
python3 -m vasp_query search "EFG"       # hybrid search (tags + wiki pages)
python3 -m vasp_query search "HSE" --type=tag --debug  # filter + pipeline trace
python3 -m vasp_query search "POSCAR" -H # human-readable
python3 -m vasp_query stats [TAG]        # frequency + top values; omit TAG to list all
python3 -m vasp_query stats ENCUT -k 2   # top 2 values only
python3 -m vasp_query list              # all known tag names
python3 -m vasp_query list -H           # one per line
python3 -m vasp_query related QUAD_EFG   # wiki-related tags
python3 -m vasp_query fullwiki LEFG      # full cleaned wiki content
python3 -m vasp_query fullwiki LEFG -H   # plain-text
python3 -m vasp_query incar ENCUT=400 NSW=0       # match-all INCAR filter
python3 -m vasp_query incar ENCUT=400 NSW=0 --any-match  # match-any
python3 -m vasp_query cooccur ENCUT PREC          # co-occurrence stats
python3 -m vasp_query cooccur ISMEAR SIGMA -H     # human-readable
python3 -m vasp_query fetch              # fetch latest wiki data from vasp.at
python3 -m vasp_query fetch --check      # detect wiki changes (~2s)
python3 -m vasp_query preprocess         # rebuild all data files
python3 -m vasp_query preprocess --check # detect stale data
```

All output is JSON on stdout by default. `-H` / `--human` → Markdown. `--debug` traces search tiers.

### OpenMX commands (`omx-db`, `omx-gen`, `vasp2omx`, `omp2vasp`)

```bash
# Manual database queries
omx-db search "SCF convergence"          # FTS5 full-text search
omx-db search "SCF" --json               # JSON output
omx-db hybrid "mixing parameters" --debug  # FTS5 + semantic RRF
omx-db rag "how to tune SCF"             # semantic search (loads embedding model)
omx-db keyword "scf.Kgrid"               # keyword → section lookup
omx-db keyword scf.Kgrid --json          # JSON with structured metadata
omx-db section 16                        # read chapter §16
omx-db section 8.2                       # read subsection §8.2
omx-db list                              # all sections
omx-db files                             # file inventory
omx-db files --type pdf                  # only PDFs
omx-db stats                             # database statistics

# Input generation
omx-gen structure.cif -t scf_band -o calc.dat        # generate .dat
omx-gen POSCAR -t scf_band_metal --cutoff 400 -k 8 8 8  # metal with overrides
omx-gen h2o.xyz -t scf_cluster                        # molecule (no k-points)
omx-gen structure.cif -t geom_opt -o opt.dat           # geometry optimization
omx-gen --list-templates                               # available templates
omx-gen --keyword scf.EigenvalueSolver                 # keyword metadata

# Format conversion
vasp2omx INCAR POSCAR -o input.dat     # VASP → OpenMX
omp2vasp input.dat -o INCAR            # OpenMX → VASP
```

`omx-db` accepts `--json` as a global flag. omx-gen/vasp2omx/omp2vasp use `--json` for structured output. Errors: `{"error": "...", "exit": N}` with exit code 0 (JSON always last on stdout).

### Templates (omx-gen)

| Template | Use case | Auto k-points |
|----------|----------|---------------|
| `scf_band` | Crystal SCF + band diagonalization | ✅ |
| `scf_band_metal` | Metallic system (Kerker, high smearing) | ✅ |
| `scf_cluster` | Molecule/cluster (no k-points) | ❌ |
| `geom_opt` | Geometry optimization | ✅ |
| `band_dispersion` | Post-SCF band structure | ❌ |

