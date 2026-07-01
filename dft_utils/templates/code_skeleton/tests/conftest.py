"""Fixtures for NEWCODE tools tests."""

import sys
from pathlib import Path

import pytest


@pytest.fixture
def invoke_cli(capsys):
    """Run the CLI with given argv.  Returns (stdout, stderr, exit_code)."""
    from newcode_tools.query import main

    def run(argv):
        old = sys.argv[:]
        sys.argv = argv
        code = 0
        try:
            code = main()
        except SystemExit as e:
            code = e.code or 0
        finally:
            sys.argv = old
        out, err = capsys.readouterr()
        return out, err, code

    return run
