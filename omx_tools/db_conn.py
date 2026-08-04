"""Database connection, path, and version plumbing for the OpenMX manual DB.

Owns the resolved ``openmx.db`` path (honouring ``OPENMX_DB_PATH``), the
connection helper, ANSI stripping, and the data-envelope version check.
"""

from __future__ import annotations

import os
import re
import sqlite3
import sys
from pathlib import Path

from dft_utils import DATA_VERSION, debug_log

PKG_DIR = Path(__file__).resolve().parent
SCHEMA_PATH = PKG_DIR / "schemas" / "keywords.json"
_default_db = Path(os.environ.get("OPENMX_DB_PATH", str(PKG_DIR.parent / "openmx.db")))
DB_PATH = _default_db.resolve()


def check_version(db) -> bool:
    """Check the meta table version vs code version. Returns True if match or unavailable."""
    try:
        row = db.execute("SELECT value FROM meta WHERE key='version'").fetchone()
        if row and row["value"] != DATA_VERSION:
            debug_log(f"  DB version mismatch: db={row['value']} code={DATA_VERSION}")
        return True
    except Exception:
        return True  # no meta table yet


def strip_ansi(text):
    """Strip ANSI escape sequences from text."""
    return re.sub(r'\x1b\[[0-9;]*m', '', text)


def get_db():
    if not os.path.exists(DB_PATH):
        print(f"Error: database not found at {DB_PATH}", file=sys.stderr)
        print("  Set OPENMX_DB_PATH to the correct openmx.db path.", file=sys.stderr)
        sys.exit(1)
    db = sqlite3.connect(str(DB_PATH))
    db.row_factory = sqlite3.Row
    check_version(db)
    return db