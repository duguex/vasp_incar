# Plan: Semantic Round-Trip Phase 1

> Spec: `docs/superpowers/specs/2026-07-14-semantic-roundtrip-design.md`  
> Scope: Phase 1 only — VASP→params→VASP fidelity without full IR package.

**Goal:** Must-preserve VASP tags survive `forward`→`reverse`; unmapped/dropped are reported; fixtures + tests lock the contract.

**Architecture:** Extend `omx_tools/mapping` + `vasp_to_ase.json` with preserve keys for engine-clamped fields; `forward(..., return_report=True)` inventory; pure round-trip helper used by tests (and later IR).

---

### Task 1: Mapping table + convert rules

**Files:** `omx_tools/schemas/vasp_to_ase.json`, `omx_tools/mapping/__init__.py`

- NSW: store `vasp_nsw` exact + `md_maxiter=max(n,1)` for OpenMX writer
- ISMEAR, SIGMA, IBRION: passthrough preserve keys (`vasp_ismear`, `vasp_sigma`, `vasp_ibrion`)
- reverse prefers preserve keys; NSW uses `nsw_rev` / preserve
- `forward(..., return_report=True) -> (overrides, report)`
- report: `{unmapped: [], dropped: [{tag, reason}]}`

### Task 2: Round-trip helper

**Files:** `omx_tools/semantic_roundtrip.py` (lightweight Phase 1)

- `roundtrip_vasp(incar: dict) -> EquivalenceReport`
- must-preserve set from spec §6.2
- float tolerance; bool normalize

### Task 3: Fixtures + tests

**Files:** `tests/fixtures/semantic/vasp/*.INCAR`, `tests/test_semantic_roundtrip.py`

- scf_insulator, scf_metal, relax fixtures
- assert NSW=0, ISMEAR/SIGMA, ISPIN, ENCUT round-trip
- assert unmapped collected for unknown tags

### Task 4: Docs

- CHANGELOG; pointer from AGENTS to spec
