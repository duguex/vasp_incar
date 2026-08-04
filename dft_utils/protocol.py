"""DFT code plugin protocol and registry.

Each DFT code package (vasp_query, omx_tools, etc.) exposes a ``plugin.py``
that creates a ``CodePlugin`` record and calls ``register()``.  The registry
enables the unified ``dft`` CLI and tool discovery.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from importlib import metadata
from pathlib import Path
from types import ModuleType
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
    generator_module:
        Optional module exposing the plugin's generator ``cli()`` entry point.
    converter_modules:
        Modules imported to register this plugin's converters.
    semantic_module:
        Optional module exposing the shared semantic CLI ``main()`` entry point.
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
    generator_module: str | None = None
    converter_modules: list[str] = field(default_factory=list)
    semantic_module: str | None = None


# ── Registry ───────────────────────────────────────────────────────────

_registry: dict[str, CodePlugin] = {}
_discovered = False


def register(plugin: CodePlugin) -> None:
    """Register a DFT code plugin."""
    _registry[plugin.name] = plugin


def get(name: str) -> CodePlugin | None:
    """Look up a plugin by name."""
    return _registry.get(name)


def list_all() -> dict[str, CodePlugin]:
    """Return all registered plugins."""
    return dict(_registry)


_FALLBACK_PACKAGES = (
    "vasp_query.plugin",
    "omx_tools.plugin",
)


def _load_plugin_object(obj: object, source: str) -> None:
    if isinstance(obj, CodePlugin):
        register(obj)
        return
    if isinstance(obj, ModuleType):
        raise TypeError(f"{source} must expose a CodePlugin object")
    raise TypeError(f"{source} did not provide a CodePlugin")


def _load_module(module_name: str, source: str) -> bool:
    try:
        module = __import__(module_name, fromlist=["plugin"])
        plugin = getattr(module, "plugin", None)
        if not isinstance(plugin, CodePlugin):
            raise TypeError(f"{source} must expose a CodePlugin object")
        register(plugin)
        return True
    except Exception as exc:
        print(f"[dft_utils] failed to load plugin {source}: {exc}", file=sys.stderr)
        return False


def discover(force: bool = False) -> dict[str, CodePlugin]:
    """Discover installed plugins, with a source-tree compatibility fallback."""
    global _discovered
    if _discovered and not force:
        return dict(_registry)

    loaded = False
    try:
        entry_points = tuple(metadata.entry_points(group="dft_tools.plugins"))
    except Exception as exc:
        entry_points = ()
        print(f"[dft_utils] failed to enumerate plugins: {exc}", file=sys.stderr)

    for entry_point in entry_points:
        try:
            _load_plugin_object(entry_point.load(), entry_point.name)
            loaded = True
        except Exception as exc:
            print(f"[dft_utils] failed to load plugin {entry_point.name}: {exc}", file=sys.stderr)

    for module_name in _FALLBACK_PACKAGES:
        loaded = _load_module(module_name, module_name) or loaded

    _discovered = loaded
    return dict(_registry)
