"""VASP DFT code plugin registration."""

from pathlib import Path

from dft_utils.protocol import CodePlugin, register

_PKG = Path(__file__).resolve().parent

plugin = CodePlugin(
    name="vasp",
    display_name="VASP",
    description="VASP INCAR parameter knowledge base — tag lookup, hybrid search, INCAR statistics, co-occurrence analysis",
    version="0.3.0",
    package_dir=_PKG,
    skills=[_PKG.parent / "skills" / "vasp-query" / "SKILL.md"],
    cli_module="vasp_query.query",
    generators=[],
    converters=[("vasp", "omx")],
)
register(plugin)
