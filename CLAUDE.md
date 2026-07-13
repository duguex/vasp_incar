# CLAUDE.md

Claude Code loads this file every session. **Canonical rules:** [`AGENTS.md`](AGENTS.md).  
Local block = fallback if import is declined + high-frequency footguns.

> **Humans:** [`README.md`](README.md).

## Local hard constraints (fallback)

- Two packages: `vasp_query` (INCAR/wiki) + `omx_tools` (manual DB + generators) + `dft_utils`.  
- Prefer DB/query CLIs over guessing tags/keywords.  
- Tests use **real** knowledge files — do not mock `tag_index.json` / `openmx.db` away.  
- Full conventions: `docs/agent-conventions.md`. CLI/gotchas: `docs/agent-lessons.md`.

## Commands (quick)

```bash
pip install -e ".[all]"
python3 -m vasp_query.test_cli
python3 -m pytest tests/
vasp-query tag ENCUT
omx-db search "mixing"
```

## Where to go next

| Need | File |
|------|------|
| Full agent entry | `AGENTS.md` |
| Conventions | `docs/agent-conventions.md` |
| CLI detail | `docs/agent-lessons.md` |

## Claude Code notes

- If prompted to approve imports, **allow `@AGENTS.md`**.

@AGENTS.md
