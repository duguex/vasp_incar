"""Unified ``dft`` CLI — single entry point for all DFT code plugins.

Usage::

    dft vasp tag ENCUT
    dft vasp search "energy cutoff"
    dft omx search "SCF convergence"
    dft omx gen structure.cif -t scf_band
    dft convert vasp:omx INCAR POSCAR -o input.dat
    dft semantic show INCAR --json
    dft semantic lint INCAR
    dft semantic advise INCAR
    dft semantic gen-advise -t scf
    dft semantic roundtrip INCAR
    dft --list-codes
    dft --version
"""

from __future__ import annotations

import argparse
import json
import sys
from dft_utils import PRODUCT_VERSION, discover, list_all, get


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dft",
        description="DFT calculation toolchain — unified CLI for VASP, OpenMX, and more",
    )
    parser.add_argument(
        "--version", action="version",
        version=f"dft-tools {PRODUCT_VERSION}",
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

    # Special top-level commands (REMAINDER so "src:dst ..." is not argparse'd away)
    convert_p = subparsers.add_parser("convert", help="Convert between DFT code formats")
    convert_p.add_argument(
        "args",
        nargs=argparse.REMAINDER,
        help="src:dst input [structure] [-o out] [--dry-run] [-t template]",
    )

    semantic_p = subparsers.add_parser(
        "semantic", help="Semantic IR show / round-trip / cross-code grade",
    )
    semantic_p.add_argument(
        "args",
        nargs=argparse.REMAINDER,
        help="show|roundtrip|cross|show-omx <path> [-H]",
    )

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

    # Show available converters
    convs = _get_available_convs()
    if convs:
        print(f"\nAvailable converters ({len(convs)}):")
        for s, t in convs:
            from dft_utils.convert import list_converters as _lc
            for c in _lc():
                if (c['from'], c['to']) == (s, t):
                    print(f"  {s:>10s} → {t:<10s}  {c['description']}")


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
        if not plugin.generator_module:
            print(json.dumps({
                "error": f"generator not available for {plugin_name}",
                "suggestion": "Plugin does not declare generator_module",
            }))
            return 1
        try:
            mod = __import__(plugin.generator_module, fromlist=["cli", "main"])
        except ImportError as exc:
            print(json.dumps({
                "error": f"generator module unavailable: {exc}",
                "suggestion": "Install the plugin's generator dependencies",
            }))
            return 1
        entry = getattr(mod, "main", None) or getattr(mod, "cli", None)
        if entry is None:
            print(json.dumps({
                "error": f"generator {plugin.generator_module} has no main() or cli()",
                "suggestion": "Declare a generator module with a CLI entry point",
            }))
            return 1
        old = sys.argv[:]
        sys.argv = [plugin_name + "-gen"] + args[1:]
        try:
            return int(entry() or 0)
        except SystemExit as exc:
            return exc.code or 0
        finally:
            sys.argv = old

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
        return int(entry() or 0)
    except SystemExit as e:
        return e.code or 0
    finally:
        sys.argv = old


def _get_available_convs() -> list[tuple[str, str]]:
    """Load converter modules declared by discovered plugins."""
    for plugin in list_all().values():
        for mod_name in plugin.converter_modules:
            try:
                __import__(mod_name)
            except ImportError:
                pass
    from dft_utils.convert import available_pairs
    return available_pairs()


def cmd_convert(args: list[str]) -> int:
    """Run cross-code format conversion via registered converters.

    Usage: dft convert <src_code>:<dst_code> <input_file> [structure_file]
    """
    if not args:
        pairs = _get_available_convs()
        pair_str = ", ".join(f"{s}->{t}" for s, t in pairs)
        print("Usage: dft convert <src>:<dst> <input> [structure] [-o output]")
        print("Example: dft convert vasp:omx INCAR POSCAR")
        if pair_str:
            print(f"Available: {pair_str}")
        return 1
    mapping = args[0]
    if ":" not in mapping:
        print(f"Invalid conversion specifier: {mapping!r} (expected src:dst)")
        return 1

    src, dst = mapping.split(":", 1)

    # Ensure converter modules register themselves
    _get_available_convs()
    from dft_utils.convert import convert, available_pairs

    input_file = args[1] if len(args) > 1 else ""
    structure_file = args[2] if len(args) > 2 else ""

    extras = {}
    for i in range(3, len(args)):
        if args[i] == "-o" and i + 1 < len(args):
            extras["output"] = args[i + 1]
        if args[i] == "--dry-run":
            extras["dry_run"] = True
        if args[i] == "-t" and i + 1 < len(args):
            extras["template"] = args[i + 1]

    result = convert(src, dst, input_file, structure_path=structure_file, **extras)
    if result is None:
        pairs = available_pairs()
        pair_str = ", ".join(f"{s}->{t}" for s, t in pairs)
        print(f"No converter found for {src} -> {dst}")
        print(f"Available: {pair_str}")
        return 1
    return 0


def main() -> int:
    discover()
    parser = build_parser()
    args = parser.parse_args()

    if args.list_codes:
        cmd_list_codes()
        return 0

    if args.code == "convert":
        # Drop optional leading "--" inserted by argparse REMAINDER
        conv_args = list(getattr(args, "args", []) or [])
        if conv_args and conv_args[0] == "--":
            conv_args = conv_args[1:]
        return cmd_convert(conv_args)

    if args.code == "semantic":
        sem_args = list(getattr(args, "args", []) or [])
        if sem_args and sem_args[0] == "--":
            sem_args = sem_args[1:]
        semantic_modules = {
            p.semantic_module for p in list_all().values() if p.semantic_module
        }
        if len(semantic_modules) != 1:
            print(json.dumps({
                "error": "semantic command provider is unavailable or ambiguous",
                "suggestion": "Declare exactly one semantic_module provider",
            }))
            return 1
        semantic_module = next(iter(semantic_modules))
        try:
            mod = __import__(semantic_module, fromlist=["main"])
        except ImportError as exc:
            print(json.dumps({
                "error": f"semantic module unavailable: {exc}",
                "suggestion": "Install the semantic provider dependencies",
            }))
            return 1
        return int(mod.main(sem_args) or 0)

    if args.code:
        return cmd_code(args.code, args.args)

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
