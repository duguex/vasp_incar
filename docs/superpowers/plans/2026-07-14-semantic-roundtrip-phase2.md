# Plan: Semantic Round-Trip Phase 2 (done)

> Spec: `docs/superpowers/specs/2026-07-14-semantic-roundtrip-design.md`

**Goal:** Explicit Semantic IR module; VASP encode/decode; `vasp2omx` via IR.

## Delivered

| Path | Role |
|------|------|
| `omx_tools/semantic/ir.py` | Pydantic IR + calc_class tables |
| `omx_tools/semantic/encode_vasp.py` | INCAR → IR |
| `omx_tools/semantic/decode_vasp.py` | IR → INCAR |
| `omx_tools/semantic/decode_omx.py` | IR → (template, ASE overrides) |
| `omx_tools/semantic/encode_omx.py` | ASE → IR (via reverse+encode_vasp) |
| `omx_tools/semantic/equiv.py` | `roundtrip_vasp_ir` |
| `omx_tools/vasp2omx.py` | Uses encode_vasp → decode_omx |
| `tests/test_semantic_ir.py` | Snapshots + round-trips |

## Next (Phase 3)

- Stronger encode_omx from raw `.dat`
- Cross-code grade reports
- Optional CLI `dft semantic show|roundtrip`
