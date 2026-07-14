#!/usr/bin/env python3
"""Backward-compatible entry → cross_band.py --element Si."""
from __future__ import annotations
import importlib.util
import sys
from pathlib import Path

def _load():
    spec = importlib.util.spec_from_file_location(
        "cross_band", Path(__file__).resolve().parent / "cross_band.py"
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod

if __name__ == "__main__":
    mod = _load()
    raise SystemExit(mod.main(["--element", "Si", *sys.argv[1:]]))
