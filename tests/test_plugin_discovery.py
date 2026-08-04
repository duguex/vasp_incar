"""Plugin discovery and unified CLI capability contract tests."""

from __future__ import annotations

from pathlib import Path

from dft_utils.protocol import CodePlugin


class _EntryPoint:
    def __init__(self, name: str, plugin: CodePlugin):
        self.name = name
        self._plugin = plugin

    def load(self):
        return self._plugin


def _plugin(name: str) -> CodePlugin:
    return CodePlugin(
        name=name,
        display_name=name.upper(),
        description=f"{name} test plugin",
        version="0.0.0",
        package_dir=Path("/tmp") / name,
    )


def test_discover_loads_all_entry_points_after_partial_registration(monkeypatch):
    import dft_utils.protocol as protocol

    first = _plugin("first")
    second = _plugin("second")
    entries = [_EntryPoint("first", first), _EntryPoint("second", second)]
    old_registry = protocol._registry.copy()
    old_discovered = protocol._discovered
    try:
        protocol._registry.clear()
        protocol._registry["partial"] = _plugin("partial")
        protocol._discovered = False
        monkeypatch.setattr(protocol.metadata, "entry_points", lambda group: entries)
        found = protocol.discover(force=True)
        assert {"partial", "first", "second"} <= set(found)
    finally:
        protocol._registry.clear()
        protocol._registry.update(old_registry)
        protocol._discovered = old_discovered


def test_discover_falls_back_when_entry_point_fails(monkeypatch):
    import dft_utils.protocol as protocol

    class BrokenEntryPoint:
        name = "broken"

        def load(self):
            raise ImportError("missing dependency")

    old_registry = protocol._registry.copy()
    old_discovered = protocol._discovered
    try:
        protocol._registry.clear()
        protocol._discovered = False
        monkeypatch.setattr(protocol.metadata, "entry_points", lambda group: [BrokenEntryPoint()])
        found = protocol.discover(force=True)
        assert {"vasp", "omx"} <= set(found)
    finally:
        protocol._registry.clear()
        protocol._registry.update(old_registry)
        protocol._discovered = old_discovered


def test_plugin_capabilities_declare_dispatch_modules():
    from dft_utils import discover

    plugins = discover()
    assert plugins["vasp"].generator_module == "vasp_query.generator"
    assert plugins["omx"].generator_module == "omx_tools.generator"
    assert "omx_tools.vasp2omx" in plugins["vasp"].converter_modules
    assert "omx_tools.omp2vasp" in plugins["omx"].converter_modules
    assert plugins["omx"].semantic_module == "omx_tools.semantic.cli"
