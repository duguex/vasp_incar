"""Shared utilities for DFT tool packages (vasp_query, omx_tools).

Sub-modules
-----------
version  — DATA_VERSION, load_data(), check_version()
search   — match_keyword(), score_keyword(), make_fts5_query()
error    — make_error(), make_suggestion_response(), print_error()
"""

import json
import sys
from typing import Any

# ── Version identifiers ────────────────────────────────────────────────

# Data envelope compatibility version.  Keep independent from the product
# release and semantic IR schema versions.
PRODUCT_VERSION = "0.3.0"
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
        sys.exit(code)
    else:
        print(f"Error: {msg}", file=sys.stderr)
        sys.exit(code)


# ── Sub-module re-exports (convenience) ────────────────────────────────

from dft_utils.version import load_data, check_version  # noqa: E402, F401
from dft_utils.search import match_keyword, score_keyword, make_fts5_query, rrf_merge  # noqa: E402, F401
from dft_utils.error import make_error, make_suggestion_response, print_error  # noqa: E402, F401

from dft_utils.protocol import CodePlugin, register, get, list_all, discover  # noqa: E402, F401
from dft_utils.convert import convert, register as register_conv, list_converters  # noqa: E402, F401
