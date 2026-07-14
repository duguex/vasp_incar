#!/usr/bin/env python3
"""Backward-compatible Si Ecoh entry → scripts/cross_delta_ecoh.py --element Si."""
from __future__ import annotations
import importlib.util
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "cross_delta_ecoh",
    Path(__file__).resolve().parent / "cross_delta_ecoh.py",
)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)
raise SystemExit(mod.main(["--element", "Si", *sys.argv[1:]]))
