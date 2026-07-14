"""Parser unit tests — no container required."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "run_official_engine_tests.py"


def _load():
    spec = importlib.util.spec_from_file_location("run_official_engine_tests", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


SAMPLE = """\
   1  input_example/Benzene.dat        Elapsed time(s)=    4.26  diff Utot= 0.000000000000  diff Force= 0.000000000000
   2  input_example/C60.dat            Elapsed time(s)=   12.87  diff Utot= 0.000000000004  diff Force= 0.000000000000
  12  input_example/Methane.dat        Elapsed time(s)=    2.13  diff Utot= 0.000000000065  diff Force= 0.000000000000
  14  input_example/Ndia2.dat          Elapsed time(s)=    3.77  diff Utot= 0.000000010000  diff Force= 0.000000000001


Total elapsed time (s)       95.64
"""


def test_parse_runtest_result():
    mod = _load()
    r = mod.parse_openmx_runtest_result(SAMPLE)
    assert r["n_cases"] == 4
    # 1e-8 is still within OMX_DIFF_TOL (1e-6)
    assert r["n_pass"] == 4
    assert r["ok"] is True
    assert r["total_elapsed_s"] == 95.64
    assert r["rows"][0]["path"].endswith("Benzene.dat")


def test_parse_detects_fail():
    mod = _load()
    bad = SAMPLE.replace("0.000000010000", "0.000100000000")
    r = mod.parse_openmx_runtest_result(bad)
    assert r["n_fail"] == 1
    assert r["ok"] is False
