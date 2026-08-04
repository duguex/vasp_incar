"""Parity between omx_tools.mapping and dft_utils.ir for spin/xc enums.

Guards the C6 single-sourcing invariant: the VASP→neutral-token tables live
only in dft_utils.ir, and mapping's forward/reverse compose them. If the two
drift apart, round-trips would silently corrupt ISPIN / GGA.
"""

from dft_utils.ir import gga_to_xc, ispin_to_spin, spin_to_ispin, xc_to_gga
from omx_tools.mapping import default_mapping, forward, reverse

# OpenMX literal ↔ neutral token maps (the only mapping-local tables)
_OPENMX_SPIN = {"Off": "off", "On": "collinear", "NC": "noncollinear"}
_OPENMX_XC = {"GGA-PBE": "PBE", "GGA-PW91": "PW91", "LDA-CA": "LDA"}


def test_spin_forward_agrees_with_ir_token():
    m = default_mapping()
    for ispin, literal in [(1, "Off"), (2, "On"), (3, "NC")]:
        token = ispin_to_spin(ispin)
        assert _OPENMX_SPIN[literal] == token
        got = forward({"ISPIN": ispin}, m).get("scf_spinpolarization")
        assert got == literal, f"ISPIN={ispin} → {got!r}, expected {literal!r}"


def test_spin_reverse_agrees_with_ir_token():
    m = default_mapping()
    for ispin in (1, 2, 3):
        token = ispin_to_spin(ispin)
        literal = next(k for k, v in _OPENMX_SPIN.items() if v == token)
        got = reverse({"scf_spinpolarization": literal}, m).get("ISPIN")
        assert got == ispin, f"{literal} → {got}, expected {ispin}"


def test_spin_roundtrip_identity():
    m = default_mapping()
    for ispin in (1, 2, 3):
        mid = forward({"ISPIN": ispin}, m)
        back = reverse(mid, m).get("ISPIN")
        assert back == ispin


def test_xc_forward_agrees_with_ir_token():
    m = default_mapping()
    for gga, literal in [("PE", "GGA-PBE"), ("91", "GGA-PW91"), ("CA", "LDA-CA")]:
        token = gga_to_xc(gga)
        assert _OPENMX_XC[literal] == token
        got = forward({"GGA": gga}, m).get("scf_xctype")
        assert got == literal, f"GGA={gga} → {got!r}, expected {literal!r}"


def test_xc_reverse_agrees_with_ir_token():
    m = default_mapping()
    for gga in ("PE", "91", "CA"):
        literal = forward({"GGA": gga}, m)["scf_xctype"]
        got = reverse({"scf_xctype": literal}, m).get("GGA")
        assert got == gga, f"{literal} → {got}, expected {gga}"
        assert xc_to_gga(literal) == gga


def test_xc_unknown_passthrough():
    m = default_mapping()
    got = forward({"GGA": "CUSTOM"}, m).get("scf_xctype")
    assert got == "CUSTOM"
    back = reverse({"scf_xctype": "CUSTOM"}, m).get("GGA")
    # unknown stays un-mapped (reverse leaves it out; forward keeps literal)
    assert back is None or back == "CUSTOM"