"""NEWCODE CLI — knowledge base search and input generation.

Usage::

    dft newcode search "keyword"
    dft newcode list
    dft newcode --help
"""

import argparse
import json
import sys
from pathlib import Path

from dft_utils import make_fts5_query, rrf_merge, make_error

PKG_DIR = Path(__file__).resolve().parent


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="newcode-tools")
    sub = parser.add_subparsers(dest="command")

    p_search = sub.add_parser("search", help="Search knowledge base")
    p_search.add_argument("keyword", help="Search query")
    p_search.add_argument("--json", action="store_true", help="JSON output")

    sub.add_parser("list", help="List available knowledge topics")

    return parser


def cmd_search(keyword: str, json_output: bool = False) -> int:
    """Search the NEWCODE knowledge base."""
    # TODO: implement FTS5 + semantic search via openmx.db or custom DB
    # See dft_utils.search.rrf_merge for shared RRF fusion
    results = []
    if not results:
        if json_output:
            print(json.dumps({"results": [], "count": 0, "query": keyword}))
        else:
            print(f"No results for: {keyword}")
        return 0

    if json_output:
        print(json.dumps({"results": results, "count": len(results), "query": keyword}))
    else:
        for r in results:
            print(f"  {r.get('title', '?')}")
    return 0


def cmd_list(json_output: bool = False) -> int:
    """List available topics."""
    # TODO: list from knowledge DB
    topics = []
    if json_output:
        print(json.dumps({"topics": topics, "count": len(topics)}))
    else:
        for t in topics:
            print(t)
    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "search":
        return cmd_search(args.keyword, json_output=getattr(args, "json", False))
    elif args.command == "list":
        return cmd_list(json_output=getattr(args, "json", False))
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
