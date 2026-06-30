"""Standardized error response helpers for DFT tool CLIs."""

import json


def make_error(msg: str, suggestion: str = "", **extra) -> dict:
    """Build a standard error dict: ``{"error": msg, "suggestion": ...}``.

    Extra keyword arguments are merged into the dict for code-specific fields.
    """
    resp: dict = {"error": msg}
    if suggestion:
        resp["suggestion"] = suggestion
    resp.update(extra)
    return resp


def make_suggestion_response(
    hint: str,
    matches: list[str],
    **extra,
) -> dict:
    """Build an ambiguous-match response: ``{"hint": ..., "matches": [...]}``."""
    resp: dict = {"hint": hint, "matches": matches}
    resp.update(extra)
    return resp


def print_error(msg: str, suggestion: str = "", **extra) -> None:
    """Print a JSON error to stdout and exit with code 1."""
    print(json.dumps(make_error(msg, suggestion, **extra)))
    import sys
    sys.exit(1)


def make_debug_response(data: dict, debug_log: list[str]) -> dict:
    """Inject a ``_debug`` key into a response dict."""
    data["_debug"] = debug_log
    return data
