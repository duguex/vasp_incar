"""Unified ``dft`` CLI — single entry point for all DFT code plugins.

Usage::

    dft vasp tag ENCUT
    dft vasp search "energy cutoff"
    dft omx search "SCF convergence"
    dft omx gen structure.cif -t scf_band
    dft convert vasp:omx INCAR POSCAR -o input.dat
    dft --list-codes
    dft --version
"""

from __future__ import annotations

import argparse
import sys
from dft_utils import DATA_VERSION, discover, list_all, get


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dft",
        description="DFT calculation toolchain — unified CLI for VASP, OpenMX, and more",
    )
    parser.add_argument(
        "--version", action="version",
        version=f"dft-tools {DATA_VERSION}",
    )
    parser.add_argument(
        "--list-codes", action="store_true",
        help="List all registered DFT code plugins",
    )

    subparsers = parser.add_subparsers(dest="code", help="DFT code")

    for name, plugin in sorted(list_all().items()):
        p = subparsers.add_parser(name, help=plugin.description)
        p.add_argument("args", nargs=argparse.REMAINDER,
                       help=f"Arguments forwarded to {plugin.cli_module}")

    # Special top-level commands
    subparsers.add_parser("convert", help="Convert between DFT code formats")

    return parser


def cmd_list_codes() -> None:
    """Print registered plugins as a table."""
    print(f"Registered DFT codes ({len(list_all())}):")
    for name, p in sorted(list_all().items()):
        gen = f", gen: {', '.join(p.generators)}" if p.generators else ""
        conv = f", convert: {p.converters}" if p.converters else ""
        print(f"  {name:12s}  {p.display_name:10s}  {p.description[:70]}{gen}{conv}")
        for skill in p.skills:
            print(f"               skill: {skill}")


def cmd_code(plugin_name: str, args: list[str]) -> int:
    """Dispatch to a plugin's CLI module."""
    plugin = get(plugin_name)
    if plugin is None:
        print(f"Unknown code: {plugin_name}")
        print(f"Available: {', '.join(list_all().keys())}")
        return 1

    # Build argv as the target module expects it
    target_argv = [plugin_name] + args

    # Handle plugin-specific subcommands that live in different modules
    if args and args[0] == "gen":
        # omx-gen lives in generator.py, not database.py
        try:
            mod = __import__("omx_tools.generator", fromlist=["cli"])
            old = sys.argv[:]
            sys.argv = [plugin_name + "-gen"] + args[1:]
            try:
                mod.cli()
            except SystemExit as e:
                return e.code or 0
            finally:
                sys.argv = old
        except ImportError as e:
            print(f"generator not available: {e}", file=sys.stderr)
            return 1
        return 0

    # Generic dispatch via cli_module
    try:
        mod = __import__(plugin.cli_module, fromlist=["main", "cli"])
    except ImportError as e:
        print(f"plugin module {plugin.cli_module} not found: {e}",
              file=sys.stderr)
        return 1

    entry = getattr(mod, "main", None) or getattr(mod, "cli", None)
    if entry is None:
        print(f"plugin {plugin_name} has no main() or cli() entry point")
        return 1

    old = sys.argv[:]
    sys.argv = target_argv
    try:
        if entry.__name__ == "main":
            return entry()
        else:
            entry()
            return 0
    except SystemExit as e:
        return e.code or 0
    finally:
        sys.argv = old


def cmd_convert(args: list[str]) -> int:
    """Run cross-code format conversion.

    Usage: dft convert <src_code>:<dst_code> <input_file> [structure_file]
    """
    if not args:
        print("Usage: dft convert <src>:<dst> <input> [structure] [-o output]")
        print("Example: dft convert vasp:omx INCAR POSCAR")
        return 1

    mapping = args[0]
    if ":" not in mapping:
        print(f"Invalid conversion specifier: {mapping!r} (expected src:dst)")
        return 1

    src, dst = mapping.split(":", 1)
    input_file = args[1] if len(args) > 1 else ""
    structure_file = args[2] if len(args) > 2 else ""

    # Map to known converters
    if (src, dst) == ("vasp", "omx"):
        try:
            from omx_tools.vasp2omx import cli as conv_cli
            argv = ["vasp2omx", input_file, structure_file] + args[3:]
            old = sys.argv[:]
            sys.argv = argv
            try:
                conv_cli()
            except SystemExit as e:
                return e.code or 0
            finally:
                sys.argv = old
        except ImportError as e:
            print(f"converter vasp2omx not available: {e}", file=sys.stderr)
            return 1
        return 0

    if (src, dst) == ("omx", "vasp"):
        try:
            from omx_tools.omp2vasp import cli as conv_cli
            argv = ["omp2vasp", input_file, structure_file] + args[3:]
            old = sys.argv[:]
            sys.argv = argv
            try:
                conv_cli()
            except SystemExit as e:
                return e.code or 0
            finally:
                sys.argv = old
        except ImportError as e:
            print(f"converter omp2vasp not available: {e}", file=sys.stderr)
            return 1
        return 0

    print(f"No converter found for {src} -> {dst}")
    return 1


def main() -> int:
    discover()
    parser = build_parser()
    args = parser.parse_args()

    if args.list_codes:
        cmd_list_codes()
        return 0

    if args.code == "convert":
        return cmd_convert(sys.argv[2:])

    if args.code:
        return cmd_code(args.code, args.args)

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
