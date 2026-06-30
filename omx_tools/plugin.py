"""OpenMX DFT code plugin registration."""

from pathlib import Path

from dft_utils.protocol import CodePlugin, register

_PKG = Path(__file__).resolve().parent

plugin = CodePlugin(
    name="omx",
    display_name="OpenMX",
    description="OpenMX input generator and manual database — FTS5 + semantic search, keyword lookup, input file generation, VASP format conversion",
    version="0.3.0",
    package_dir=_PKG,
    skills=[_PKG.parent / "skills" / "omx-tools" / "SKILL.md"],
    cli_module="omx_tools.database",
    generators=["omx-gen"],
    converters=[("omx", "vasp")],
)
register(plugin)
