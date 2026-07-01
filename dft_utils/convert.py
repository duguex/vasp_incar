"""Cross-code format conversion — registry and dispatch.

Every converter is a callable that follows this convention:

    def converter(input_path: str, structure_path: str = "", **kwargs) -> str:
        \"\"\"Convert an input file and return the output path.\"\"\"
        ...

Converters register themselves for a ``(src_code, dst_code)`` pair.
The ``convert()`` function looks up the registry and delegates.
"""

from __future__ import annotations


from typing import Callable

# ── Registry ───────────────────────────────────────────────────────────
# Maps (src_code, dst_code) → (callable, description)

_registry: dict[tuple[str, str], tuple[Callable, str]] = {}


def register(
    src: str,
    dst: str,
    fn: Callable,
    description: str = "",
) -> None:
    """Register a conversion function for *(src, dst)*."""
    _registry[(src, dst)] = (fn, description)


def convert(
    src: str,
    dst: str,
    input_path: str,
    structure_path: str = "",
    **kwargs,
) -> str | None:
    """Convert *input_path* from *src* format to *dst* format.

    Returns the output file path on success, or ``None`` if the converter
    is not found.
    """
    key = (src, dst)
    if key not in _registry:
        return None
    fn, _ = _registry[key]
    return fn(input_path, structure_path=structure_path, **kwargs)


def list_converters() -> list[dict]:
    """Return all registered converters as a list of dicts."""
    return [
        {"from": src, "to": dst, "description": desc}
        for (src, dst), (_, desc) in sorted(_registry.items())
    ]


def available_pairs() -> list[tuple[str, str]]:
    """Return list of ``(src, dst)`` pairs with registered converters."""
    return list(_registry.keys())
