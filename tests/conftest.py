"""Fixtures for omx_tools tests."""

import json
import sys
from pathlib import Path

import pytest


@pytest.fixture
def invoke_gen(capsys):
    """Run omx-gen cli() with given argv.  Returns (stdout, stderr, exit_code)."""

    from omx_tools.generator import cli

    def run(argv):
        old = sys.argv[:]
        sys.argv = argv
        code = 0
        try:
            cli()
        except SystemExit as e:
            code = e.code or 0
        finally:
            sys.argv = old
        out, err = capsys.readouterr()
        return out, err, code

    return run


@pytest.fixture
def invoke_db(capsys):
    """Run omx-db cli() with given argv.  Returns (stdout, stderr, exit_code)."""

    from omx_tools.database import cli

    def run(argv):
        old = sys.argv[:]
        sys.argv = argv
        code = 0
        try:
            cli()
        except SystemExit as e:
            code = e.code or 0
        finally:
            sys.argv = old
        out, err = capsys.readouterr()
        return out, err, code

    return run
