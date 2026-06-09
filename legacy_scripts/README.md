# legacy_scripts/

These are the original `pymatgen`-based INCAR utilities that predate the
`vasp_query` MCP tool. They are kept here for ad-hoc HPC workflows but are
**not actively maintained** — for tag lookups, search, and stats, use
`vasp_query` (CLI or MCP) instead.

## Files

| File                     | Purpose                                                                              |
| ------------------------ | ------------------------------------------------------------------------------------ |
| `incar.py`               | Validate a directory's `INCAR` against a reference JSON (POSCAR required in CWD)     |
| `incar_ref.py`           | Query `incar_data.json` by KEY=VALUE; emit INCAR text with most-frequent values      |
| `compare_incar.py`       | Diff two INCAR files (`INCAR_6` vs `INCAR_8`, hardcoded in `__main__`)               |
| `extract_incar.py`       | Walk a tree, parse all INCARs (multiprocess), dedupe, write JSON                    |
| `find_missing_tags.py`   | Compare tags in a directory of INCARs vs. `incar_data.json`                          |
| `tag_incar.py`           | High-level tag aliases (`soc`, `hse0`, `pbe0`, `scan`, `spin`, `phonon`, ...)        |
| `sample_incar.sh`        | Random-sample INCAR files under `./katze/` into `./incar_smp/`                       |
| `vasp_wiki_scraper.py`   | Original scraper for `https://vasp.at/wiki/` (predecessor of `vasp_query.processor`) |
| `vasp_wiki_real_pages.json` | Intermediate output from the scraper (page-name list)                              |
| `incar_page_content.json`  | Single INCAR wiki page content snapshot                                            |

## Running

All scripts hard-code a shebang for `~/miniconda3/envs/pydefect/bin/python`,
e.g. `incar.py`:
```python
#!/home/duguex/.conda/envs/pydefect/bin/python
```

If that env does not exist on the current machine, either:
- edit the shebang to point at any Python 3 with `pymatgen` and `tqdm` installed, or
- invoke explicitly: `python3 path/to/legacy_scripts/incar.py`

Required non-stdlib packages: `pymatgen`, `tqdm` (only `extract_incar.py` and
`find_missing_tags.py` need `tqdm`).

## Path quirks after the 2026-06-09 reorg

The raw data files used to live in the repo root and were moved to
`../data/raw/` and `../examples/`. The scripts themselves still hard-code
their old assumptions; before running, either:

- `incar.py` reads `POSCAR` from the **current working directory**. Either
  `cd` into `../examples/` and copy `INCAR` there, or pass a path (the script
  has no `--poscar` flag; you'd need to patch it).
- The other scripts that read `incar_data.json` were designed for a flat
  layout. Either symlink it back, edit the hard-coded path, or run from
  inside `data/raw/`.
