"""DFT code plugin protocol and registry.

Each DFT code package (vasp_query, omx_tools, etc.) exposes a ``plugin.py``
that creates a ``CodePlugin`` record and calls ``register()``.  The registry
enables the unified ``dft`` CLI and tool discovery.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


# ── Plugin record ──────────────────────────────────────────────────────

@dataclass
class CodePlugin:
    """Registration record for a DFT code plugin.

    Attributes
    ----------
    name:
        Short identifier used in CLI (e.g. ``"vasp"``, ``"omx"``).
    display_name:
        Human-readable name (e.g. ``"VASP"``, ``"OpenMX"``).
    description:
        One-line description of the code's capabilities.
    version:
        Plugin version string.
    package_dir:
        Path to the package directory (for finding data files, skills, etc.).
    skills:
        Paths to SKILL.md files for Hermes registration.
    cli_module:
        Fully-qualified module name for CLI dispatch
        (e.g. ``"vasp_query.query"``).
    search_fn:
        Optional callable ``search(keyword, **kwargs) → list[dict]``.
    generators:
        List of generator names (e.g. ``["omx-gen"]``).
    converters:
        List of ``(from_code, to_code)`` pairs this plugin can convert.
    """

    name: str
    display_name: str
    description: str
    version: str
    package_dir: Path
    skills: list[Path] = field(default_factory=list)
    cli_module: str = ""
    search_fn: Callable | None = None
    generators: list[str] = field(default_factory=list)
    converters: list[tuple[str, str]] = field(default_factory=list)


# ── Registry ───────────────────────────────────────────────────────────

_registry: dict[str, CodePlugin] = {}


def register(plugin: CodePlugin) -> None:
    """Register a DFT code plugin."""
    _registry[plugin.name] = plugin


def get(name: str) -> CodePlugin | None:
    """Look up a plugin by name."""
    return _registry.get(name)


def list_all() -> dict[str, CodePlugin]:
    """Return all registered plugins."""
    return dict(_registry)


def discover() -> dict[str, CodePlugin]:
    """Auto-discover plugins by importing known packages.

    Each DFT package in ``_PACKAGES`` is imported if available, triggering
    its ``plugin.py`` ``register()`` call.  Already-registered plugins are
    returned immediately.
    """
    if _registry:
        return dict(_registry)

    # Known DFT code packages to attempt discovery for
    _PACKAGES = [
        "vasp_query.plugin",
        "omx_tools.plugin",
    ]

    for mod_name in _PACKAGES:
        try:
            __import__(mod_name)
        except ImportError:
            pass
        except Exception as exc:
            print(f"[dft_utils] failed to load plugin {mod_name}: {exc}",
                  file=sys.stderr)

    return dict(_registry)
