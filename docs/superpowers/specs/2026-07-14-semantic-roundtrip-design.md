# Design: Semantic Isomorphism & Round-Trip Self-Consistency

**Date:** 2026-07-14  
**Status:** Draft for implementation planning  
**Package:** `dft-tools` (`~/vasp_wiki`)  
**Related:** CLI symmetry (done); OpenMX example corpus (done); mapping in `omx_tools/schemas/vasp_to_ase.json`

---

## 1. Problem

The project already converts VASP ↔ OpenMX via a thin intermediate (`CalculationIntent` + ASE-keyed params). In practice:

1. **Parameter spaces are not treated as near-isomorphic** — only ~9 of ~1136 VASP tags have real `omx_key` mappings; ~16 more are intent-only drops.
2. **“Self-consistency” was never defined as round-trip fidelity** — `forward` then `reverse` fails on common cases (e.g. `NSW=0` → `1`, `ISMEAR`/`SIGMA` lost, `ALGO=Fast` → `Normal`).
3. **Mature VASP tools are not ground truth** — pymatgen/vaspkit/pydefect are used opportunistically (e.g. KPOINTS), not as authorities for encode/decode correctness.

Without an explicit semantic layer contract and round-trip tests, cross-code conversion and template generation cannot be trusted for agent workflows.

---

## 2. Goals

1. Treat **three spaces as approximately isomorphic**:
   - VASP parameter space (INCAR tags + values + combination constraints)
   - **Semantic / label space** (canonical intermediate representation)
   - OpenMX parameter space (keywords / ASE keys / templates)
2. Define **self-consistency** as: for a calculation in space X,  
   `X → semantic → X'` recovers the original **up to a declared equivalence class**.
3. Use **pymatgen + vaspkit + pydefect as ground truth (GT)** for the **VASP input side** (shape, defaults, legal combinations), not as things to reimplement.
4. Make unmapped / lossy fields **explicit** (never silent drop of must-preserve tags).
5. Drive development with **round-trip tests + GT diffs**, not feature-list symmetry.

## 3. Non-goals

- Full 1:1 mapping of all 1136 VASP tags or all 304 OpenMX keywords.
- Bit-identical INCAR files (comments, tag order, float formatting may differ).
- Replacing pydefect / vaspkit / pymatgen workflows.
- OpenMX post-processing or DFT execution.
- Workshop-scale VASP INCAR corpus (explicitly low value for this project).
- Perfect cross-code physical equivalence for all methods (GW, hybrid, DFT+U, SOC, …) in v1.

---

## 4. Conceptual model

```
                 ┌──────────────────────────────────────┐
                 │  GT: pymatgen / vaspkit / pydefect     │
                 │  (VASP input shape & legal defaults)   │
                 └──────────────────┬───────────────────┘
                                    │ calibrates decode/encode
                                    ▼
   VASP params  ◄──encode/decode──►  SEMANTIC IR  ◄──encode/decode──►  OpenMX params
   (INCAR dict)                      (versioned)                      (.dat / ASE keys)
         ▲                                ▲
         │                                │
    round-trip                       isomorphism
    VASP→S→VASP                      constraint
```

### 4.1 Three spaces

| Space | Concrete objects today | Target objects |
|-------|------------------------|----------------|
| VASP params | `dict[str, Any]` from `parse_incar` | Same + optional structure/KPOINTS/POTCAR refs |
| Semantic IR | `CalculationIntent(template, params, structure_path)` | Versioned schema (below) |
| OpenMX params | ASE-keyed overrides + template + `.dat` text | Same; raw OpenMX dotted keys allowed in IR sidecar |

**Isomorphism** here means: there exists a semantic point that both codes can project to/from for the **supported calculation classes**, with declared loss for the rest — not a bijection on all of DFT parameter space.

### 4.2 Calculation classes (v1 supported)

| Class id | VASP signals (illustrative) | OpenMX template |
|----------|----------------------------|-----------------|
| `scf` | NSW=0, IBRION=-1/none, insulator-ish smearing | `scf_band` / `scf_cluster` |
| `scf_metal` | NSW=0, ISMEAR=1/2, higher SIGMA | `scf_band_metal` |
| `relax` | NSW>0, IBRION=1/2, ISIF | `geom_opt` |
| `band` | ICHARG=11 or post-SCF band intent | `band_dispersion` |
| `md` | IBRION=0, MDALGO… | future / limited |

Out-of-v1 classes (defect, hybrid HSE detail, GW, NEB, …): may encode as `unsupported` with explicit error, or partial map with large drop sets — **must not pretend full round-trip**.

---

## 5. Semantic IR (target)

### 5.1 Document shape

Versioned envelope (`DATA_VERSION` = `0.3.0` initially; bump when IR fields change):

```json
{
  "_version": "0.3.0",
  "data": {
    "schema": "dft_semantic_ir",
    "calc_class": "scf",
    "structure_ref": "optional path or hash",
    "physics": {
      "xc": "PBE",
      "spin": "collinear",
      "cutoff_eV": 400.0,
      "smearing": {"method": "gaussian", "sigma_eV": 0.05},
      "ediff_eV": 1e-5,
      "max_scf": 100,
      "charge": 0.0
    },
    "ionic": {
      "motion": "fixed",
      "max_steps": 0,
      "force_crit_eV_A": null,
      "isif": null
    },
    "electronics_algo": {
      "vasp_algo": null,
      "omx_eigenvalue_solver": null
    },
    "code_native": {
      "vasp": {},
      "openmx": {}
    },
    "provenance": {
      "source_code": "vasp",
      "unmapped": [],
      "dropped": [],
      "notes": []
    }
  }
}
```

### 5.2 Field roles

| Block | Role |
|-------|------|
| `calc_class` | Coarse intent (template selection) |
| `physics` / `ionic` | **Must-preserve semantic core** for round-trip |
| `electronics_algo` | Best-effort; lossy across codes |
| `code_native` | Pass-through bucket for tags with no shared meaning (still available for same-code round-trip) |
| `provenance.unmapped` | Present in source, no rule |
| `provenance.dropped` | Rule says drop (intent-only / no equivalent) |

### 5.3 Relation to current code

| Today | Target |
|-------|--------|
| `CalculationIntent.template` | `calc_class` (+ template binding table) |
| `CalculationIntent.params` (ASE keys) | Projection of `physics`/`ionic` into ASE keys for OpenMX writers |
| `vasp_to_ase.json` | Becomes **projections** IR↔VASP and IR↔OpenMX (or stays as VASP↔ASE view generated from IR schema) |
| Silent `continue` on unknown tags | Record in `provenance.unmapped` |

Migration may keep ASE keys as an adapter layer under IR for one release to avoid big-bang rewrites.

---

## 6. Equivalence classes (round-trip contract)

### 6.1 Definitions

For same-code round-trip `X → IR → X'`:

**Strict equality (must-preserve):**  
After normalize (uppercase tags, bool canonicalization, float tolerance), values equal.

**Class equivalence:**  
Recovered calculation is in the same `calc_class` and physics core matches; some natives may live only in `code_native`.

**Declared drop:**  
Listed in `provenance.dropped` with reason; absence in `X'` is OK.

**Failure:**  
Must-preserve key missing/changed without declaration → test fail / runtime error in strict mode.

### 6.2 VASP must-preserve set (v1)

| Tag | Semantic field | Notes |
|-----|----------------|-------|
| ENCUT | `physics.cutoff_eV` | Ry conversion only on OpenMX leg |
| ISPIN | `physics.spin` | 1/2/(3→NC) |
| EDIFF | `physics.ediff_eV` | |
| NELM | `physics.max_scf` | |
| NSW | `ionic.max_steps` | **0 must remain 0** (bug today: forced ≥1 on OpenMX leg only — IR must store 0) |
| IBRION | `ionic.motion` + calc_class | Not only template side-effect |
| ISMEAR | `physics.smearing.method` | Map 0/-5/1/2… |
| SIGMA | `physics.smearing.sigma_eV` | |
| GGA / XC family | `physics.xc` | |
| EDIFFG | `ionic.force_crit_eV_A` | sign convention explicit |
| NELECT / charge | `physics.charge` | via POTCAR when available |

### 6.3 VASP declared-drop (v1 defaults)

PREC, LREAL, ISYM, LWAVE, LCHARG, LORBIT, NELMIN, ADDGRID, NBANDS (often auto), and tags never seen in mapping — unless present in `code_native.vasp` for same-code round-trip.

**Policy:**  
- **Same-code VASP→IR→VASP:** prefer putting unknown tags into `code_native.vasp` so round-trip can restore them.  
- **Cross-code VASP→IR→OpenMX:** only shared IR fields + documented drops; natives stay in provenance.

### 6.4 Float / bool normalize

- Floats: `math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-12)` unless tag-specific.
- Bools: `.TRUE./.FALSE./True/False/T/F` → bool.
- ENCUT: compare in eV on VASP side always.

### 6.5 Known bugs to fix under this contract

| Issue | Today | Required |
|-------|-------|----------|
| NSW=0 | `max(v,1)` in forward | IR keeps 0; OpenMX writer may still use ≥1 for engine, but reverse must restore NSW=0 |
| ISMEAR/SIGMA | intent only, lost | IR physics.smearing; reverse restores |
| ALGO | many → Band; reverse → Normal | Either map through IR with multi-value loss note, or code_native for exact ALGO |
| Silent skip | unmapped ignored | provenance.unmapped |

---

## 7. Encode / decode API (target)

```text
omx_tools/semantic/
  ir.py           # pydantic models for IR
  encode_vasp.py  # INCAR dict (+ optional structure meta) → IR
  decode_vasp.py  # IR → INCAR dict
  encode_omx.py   # .dat / ASE dict → IR
  decode_omx.py   # IR → ASE overrides + template choice
  equiv.py        # normalize + compare + EquivalenceReport
```

Public functions (names indicative):

```python
def encode_vasp(incar: dict, *, structure_path: str | None = None) -> SemanticIR: ...
def decode_vasp(ir: SemanticIR) -> dict: ...
def encode_omx(params: dict, *, template: str | None = None) -> SemanticIR: ...
def decode_omx(ir: SemanticIR) -> tuple[str, dict]:  # template, ase overrides
def roundtrip_vasp(incar: dict) -> EquivalenceReport: ...
def roundtrip_omx(params: dict, template: str) -> EquivalenceReport: ...
```

CLI (optional v1.1):

```bash
dft semantic roundtrip vasp INCAR --json
dft semantic show INCAR --json   # dump IR
```

Existing `vasp2omx` / `omp2vasp` should call encode/decode rather than ad-hoc forward-only paths (phased migration).

---

## 8. Ground truth (VASP input)

### 8.1 Roles

| Tool | GT role | Use in tests |
|------|---------|----------------|
| **pymatgen** | Structure, Kpoints, Potcar, Incar objects; MP input sets as reference shapes | Compare `vasp-gen` KPOINTS; optional Incar key presence |
| **vaspkit** | Human workflow conventions (what files a task needs) | Doc alignment + optional golden file lists — **not** required as Python import if unavailable |
| **pydefect** | Defect calculation input packages | Later phase: one minimal defect fixture directory as shape GT |

### 8.2 GT principles

1. When our VASP decode/encode disagrees with pymatgen on **structural facts** (lattice, kmesh formula, element order for POTCAR), **pymatgen wins**.
2. When disagreement is **scientific default choice** (ENCUT=520 vs 400), IR stores explicit value; templates may differ from MP sets but must round-trip **their own** values.
3. pydefect GT is about **completeness of an input set** for defect flows, not about OpenMX.
4. Never vendor POTCARs; GT tests that need POTCAR skip unless `PMG_VASP_PSP_DIR` is set.

### 8.3 GT fixtures (repo)

```
tests/fixtures/semantic/
  vasp/
    scf_insulator.INCAR
    scf_metal.INCAR
    relax_isif3.INCAR
    band_icharg11.INCAR
  reports/   # optional checked-in expected IR snapshots
```

Goldens authored/reviewed against pymatgen-readable inputs; pydefect fixture optional under `tests/fixtures/semantic/pydefect_min/` when added.

---

## 9. Testing strategy

### 9.1 Unit: pure mapping

- Each must-preserve tag: encode→decode value preserved.
- NSW=0 regression.
- ISMEAR/SIGMA pair preserved on VASP round-trip.

### 9.2 Round-trip: file-level

```python
report = roundtrip_vasp(parse_incar(path))
assert report.ok, report.diff
```

`EquivalenceReport`: `{ok, missing, changed, unexpected_drops, unmapped}`.

### 9.3 Cross-code (lossy, separate grade)

```text
VASP → IR → OpenMX → IR' → VASP'
```

Assert: must-preserve physics core equal within tolerance; `calc_class` stable; allow listed cross-code drops (e.g. PREC).

### 9.4 GT probes

- `vasp-gen --kspacing` mesh vs `Kpoints` from same structure/spacing policy.
- Optional: pymatgen `Incar.from_file` accepts our decode output.

### 9.5 Non-tests

- Do not require identity of comment lines or tag order.
- Do not fail on declared drops.

---

## 10. Phased delivery

### Phase 0 — Contract freeze (this spec)

- Agree must-preserve / drop sets.
- Document known lossy ALGO behavior.

### Phase 1 — Fix VASP→ASE→VASP without full IR rewrite

- Stop treating NSW=0 as 1 in the **semantic store** (OpenMX writer may clamp; reverse uses IR).
- Carry ISMEAR/SIGMA through params or parallel IR fields.
- `provenance.unmapped` / verbose inventory.
- Round-trip tests on fixtures.

### Phase 2 — Explicit Semantic IR module

- Pydantic IR + encode_vasp/decode_vasp.
- Migrate `vasp2omx` to encode_vasp → decode_omx.
- Snapshot tests for IR JSON.

### Phase 3 — OpenMX encode/decode + cross-code grade

- encode_omx/decode_omx.
- Cross-code report (lossy grade).
- Align omx templates with `calc_class` table.

### Phase 4 — GT expansion

- pymatgen KPOINTS/INCAR probes in CI.
- Optional pydefect minimal package shape test.
- vaspkit checklist in docs only unless API available.

Each phase independently mergeable; Phase 1 unblocks trust without boiling the ocean.

---

## 11. Current baseline (2026-07-14 audit)

| Metric | Value |
|--------|-------|
| Mapping rules | 25 |
| True omx_key links | 9 |
| Explicit reverse_convert | 6 |
| VASP tag index | ~1136 |
| OpenMX keyword schema | ~304 |
| NSW=0 round-trip | **FAIL** |
| ISMEAR/SIGMA round-trip | **FAIL** |
| Design-intent tests | conversion smoke only, not full round-trip |
| GT-driven tests | essentially none (KPOINTS suite exists separately) |

---

## 12. Acceptance criteria (spec done when…)

**Phase 1 complete when:**

- [ ] Documented must-preserve set implemented for VASP→(intent/params)→VASP.
- [ ] `NSW=0` round-trip passes.
- [ ] `ISMEAR`+`SIGMA` round-trip passes for scf + scf_metal fixtures.
- [ ] Unmapped tags appear in a structured report (verbose or IR provenance).
- [ ] `tests/fixtures/semantic/vasp/*` goldens + pytest green.

**Phase 2 complete when:**

- [ ] Versioned IR JSON dumpable from any INCAR fixture.
- [ ] `vasp2omx` uses encode/decode path.
- [ ] IR schema version bump process noted in CHANGELOG.

**Phase 3–4:** as in §10.

---

## 13. Risks

| Risk | Mitigation |
|------|------------|
| Over-large IR scope | v1 physics+ionic only; natives bucket |
| OpenMX engine requires md_maxiter≥1 | Clamp only at write boundary; IR stores true NSW |
| ALGO many-to-one | Declare lossy; store exact in code_native.vasp |
| GT tools not installed in CI | Skip markers; never fail core suite |
| Silent behavior change for vasp2omx users | Changelog + verbose unmapped warnings |

---

## 14. Decisions log

| Decision | Choice |
|----------|--------|
| Self-consistency definition | Round-trip X→semantic→X' under equivalence class |
| Isomorphism | Approximate, per calc_class, not full DFT |
| VASP GT | pymatgen primary; vaspkit conventions; pydefect later for defects |
| OpenMX GT | Manual + official work/ examples (weaker) |
| NSW=0 | Must preserve in IR; writer may clamp |
| Same-code natives | `code_native` bucket for full VASP restore |
| Cross-code | Lossy grade separate from same-code strict |
| Implementation start | Phase 1 before full IR package |

---

## 15. Next step after approval

1. User reviews this spec.  
2. Write implementation plan: `docs/superpowers/plans/YYYY-MM-DD-semantic-roundtrip.md` (Phase 1 tasks first).  
3. Implement Phase 1 with TDD on semantic fixtures.

---

## 16. One-line summary

**VASP, semantic labels, and OpenMX are near-isomorphic views of a calculation; self-consistency means round-trip restore under an explicit equivalence class; pymatgen/vaspkit/pydefect calibrate the VASP view as ground truth.**
