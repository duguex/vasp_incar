"""NEWCODE DFT code plugin registration."""

from pathlib import Path

from dft_utils.protocol import CodePlugin, register

_PKG = Path(__file__).resolve().parent

plugin = CodePlugin(
    name="newcode",                      # CLI short name: dft newcode search "..."
    display_name="NEWCODE",              # Human-readable name
    description="NEWCODE DFT code knowledge base and tools",
    version="0.1.0",
    package_dir=_PKG,
    skills=[_PKG.parent / "skills" / "newcode" / "SKILL.md"],
    cli_module="newcode_tools.query",
    generators=[],                       # e.g. ["newcode-gen"]
    generator_module="",                # e.g. "newcode_tools.generator"
    converters=[],                       # e.g. [("newcode", "vasp")]
    converter_modules=[],                # e.g. ["newcode_tools.converters"]
    semantic_module=None,                 # one shared semantic provider only
)
register(plugin)
