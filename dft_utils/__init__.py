"""Shared utilities for DFT tool packages (vasp_query, omx_tools)."""

import json
import sys
from typing import Any

# ── Data version ───────────────────────────────────────────────────────
# Bumped to 0.3.0 when vasp-query (0.2.0) and omx-tools (0.1.0) merged.

DATA_VERSION = "0.3.0"


# ── Debug log ──────────────────────────────────────────────────────────

_DEBUG_LOG: list[str] = []


def debug_log(msg: str) -> None:
    _DEBUG_LOG.append(msg)


def get_debug_log() -> list[str]:
    return _DEBUG_LOG


def clear_debug_log() -> None:
    _DEBUG_LOG.clear()


# ── JSON helpers ───────────────────────────────────────────────────────

def load_json(path: str | Any, name: str = "") -> Any | None:
    """Load a JSON file, returning None if not found."""
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return None


def die_json(msg: str, json_output: bool = False, code: int = 1):
    """Print JSON error and exit, or print text error and exit with code."""
    if json_output:
        print(json.dumps({"error": msg, "exit": code}))
        sys.exit(0)
    else:
        print(f"Error: {msg}", file=sys.stderr)
        sys.exit(code)
