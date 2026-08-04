#!/usr/bin/env python3
"""Rebuild openmx.db from the OpenMX 4.0 manual HTML corpus.

The database (previously a committed 4.1MB binary with no builder) is now
reproducible: its tables are derived deterministically from
``openmx4.0_manual/`` (LaTeXML HTML) plus a hardcoded PDF metadata table, and
its semantic embeddings are recomputed with the shared embedding backend.

Usage:
  python3 scripts/build_openmx_db.py                # rebuild openmx.db in place
  python3 scripts/build_openmx_db.py \\
      --manual openmx4.0_manual --out /tmp/openmx_rebuilt.db
  python3 scripts/build_openmx_db.py --skip-embeddings   # skip semantic vectors

Verifiable invariants (must hold after a full build):
  sections 281 / section_content 281 / sections_fts 281
  index_entries 799 / files 282 / section_embeddings 281
  sections_fts.rowid == sections.id
"""

from __future__ import annotations

import argparse
import os
import re
import sqlite3
import sys
from pathlib import Path

import bs4

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


# ── PDF metadata (hardcoded: these files are not shipped with the repo) ──
# (path, size_bytes, category) — title/file_type defaults apply.
_PDF_ROWS: list[tuple[str, int, str]] = [
    ("openmx3.9_manual.pdf", 17147185, "manual"),
    ("docs/ADPACK_Manual.pdf", 255310, "tech_doc"),
    ("docs/New_Features_OpenMX3.9.pdf", 2051403, "tech_doc"),
    ("docs/OpenMX-Compile.pdf", 670497, "tech_doc"),
    ("docs/Recursion_Methods.pdf", 1298246, "tech_doc"),
    ("docs/TechNotes_TotalEnergy.pdf", 134605, "tech_doc"),
    ("docs/Viewer_Manual.pdf", 13397516, "tech_doc"),
    ("workshop/OpenMX-1.pdf", 2649725, "workshop"),
    ("workshop/OpenMX-2.pdf", 2203096, "workshop"),
    ("workshop/OpenMX-General.pdf", 3265275, "workshop"),
    ("workshop/OpenMX-Geo.pdf", 1636656, "workshop"),
    ("workshop/OpenMX-NEGF.pdf", 1384623, "workshop"),
    ("workshop/OpenMX-XPS.pdf", 548864, "workshop"),
    ("video_lec/OpenMX-2015-Oct-15.pdf", 2256536, "lecture"),
    ("video_lec/OpenMX-2015-Oct-22.pdf", 1786137, "lecture"),
    ("video_lec/OpenMX-Compile-2014Oct10.pdf", 1348330, "lecture"),
    ("video_lec/OpenMX-Hands-on-2014Oct10.pdf", 3301700, "lecture"),
    ("video_lec/OrderN-Part1.pdf", 3480252, "lecture"),
    ("video_lec/OrderN-Part2.pdf", 3792896, "lecture"),
]

_NAVIGATION_FILES = frozenset({"contents.html", "index.html"})

_SCHEMA = """
CREATE TABLE files (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        path        TEXT UNIQUE NOT NULL,
        title       TEXT DEFAULT '',
        file_type   TEXT NOT NULL DEFAULT 'html',
        size_bytes  INTEGER DEFAULT 0,
        category    TEXT DEFAULT ''
    );
CREATE TABLE index_entries (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        keyword     TEXT NOT NULL,
        file_path   TEXT DEFAULT '',
        anchor      TEXT DEFAULT '',
        section_ref TEXT DEFAULT ''
    );
CREATE TABLE sections (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        sec_num     TEXT NOT NULL,
        title       TEXT NOT NULL,
        file_path   TEXT NOT NULL,
        anchor      TEXT DEFAULT '',
        depth       INTEGER NOT NULL DEFAULT 1,
        parent_num  TEXT DEFAULT ''
    );
CREATE TABLE section_content (
        section_id  INTEGER PRIMARY KEY REFERENCES sections(id),
        raw_text    TEXT
    );
CREATE TABLE section_embeddings (
        section_id INTEGER PRIMARY KEY REFERENCES sections(id),
        sec_num TEXT NOT NULL,
        title TEXT NOT NULL,
        file_path TEXT DEFAULT '',
        embedding BLOB NOT NULL,
        dim INTEGER NOT NULL DEFAULT 384
    );
CREATE VIRTUAL TABLE sections_fts USING fts5(
        sec_num, title, raw_text
    );
CREATE INDEX idx_index_keyword ON index_entries(keyword);
CREATE INDEX idx_sections_file ON sections(file_path);
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
"""

_NORM_WS = lambda s: re.sub(r"\s+", " ", s)  # noqa: E731


def _soup(path: Path):
    return bs4.BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")


def parse_sections(contents: Path) -> list[dict]:
    """Sections in document order of ``li.ltx_tocentry`` in contents.html."""
    soup = _soup(contents)
    out: list[dict] = []
    for li in soup.select("li.ltx_tocentry"):
        a = li.find("a", class_="ltx_ref")
        tt = a.find("span", class_="ltx_ref_title")
        tag = tt.find("span", class_="ltx_tag")
        sec_num = tag.get_text().strip() if tag else ""  # bib/index have no number
        if tag:
            tag.extract()
        title = _NORM_WS(tt.get_text(" "))
        file_path, _, anchor = a["href"].partition("#")
        depth = sec_num.count(".") + 1 if sec_num else 1
        parent = ".".join(sec_num.split(".")[:-1]) if "." in sec_num else ""
        out.append({
            "sec_num": sec_num, "title": title,
            "file_path": file_path, "anchor": anchor,
            "depth": depth, "parent_num": parent,
        })
    return out


def parse_files(manual_dir: Path) -> list[dict]:
    """HTML content files (exclude navigation) plus hardcoded PDF rows."""
    rows: list[dict] = []
    for f in sorted(manual_dir.iterdir()):
        if not (f.is_file() and f.suffix == ".html" and f.name not in _NAVIGATION_FILES):
            continue
        soup = _soup(f)
        t = soup.title.get_text(" ", strip=True) if soup.title else ""
        rows.append({
            "path": f.name, "title": _NORM_WS(t), "file_type": "html",
            "size_bytes": f.stat().st_size, "category": "manual_v4",
        })
    for path, size, category in _PDF_ROWS:
        rows.append({
            "path": path, "title": "", "file_type": "pdf",
            "size_bytes": size, "category": category,
        })
    return rows


def extract_page_text(manual_dir: Path, file_path: str) -> str:
    """Full normalized text of one manual page ('div.ltx_page_content')."""
    soup = _soup(manual_dir / file_path)
    el = soup.select_one("div.ltx_page_content")
    if el is None:
        return ""
    for x in el.select("nav"):
        x.decompose()
    for x in el.select("footer"):
        x.decompose()
    return _NORM_WS(el.get_text(" ")).strip()


def parse_index_entries(idx: Path) -> list[tuple[str, str, str, str]]:
    """(keyword, file_path, anchor, section_ref) from idx.html."""
    soup = _soup(idx)
    out: list[tuple[str, str, str, str]] = []
    for li in soup.select("li.ltx_indexentry"):
        kw_el = li.find("span", class_="ltx_indexphrase")
        keyword = _NORM_WS(kw_el.get_text(" ")) if kw_el else ""
        refs = li.find("span", class_="ltx_indexrefs")
        if refs is None:
            continue
        for a in refs.find_all("a", class_="ltx_ref"):
            file_path, _, anchor = a["href"].partition("#")
            tag = a.find("span", class_="ltx_ref_tag")
            section_ref = tag.get_text(" ").strip() if tag else ""
            out.append((keyword, file_path, anchor, section_ref))
    return out


def build(manual_dir: Path, out: Path, *, skip_embeddings: bool) -> None:
    contents = manual_dir / "contents.html"
    idx = manual_dir / "idx.html"
    if not (contents.exists() and idx.exists() and manual_dir.is_dir()):
        raise SystemExit(f"manual corpus incomplete under {manual_dir}")

    sections = parse_sections(contents)
    files = parse_files(manual_dir)
    entries = parse_index_entries(idx)

    conn = sqlite3.connect(str(out))
    conn.executescript(_SCHEMA)

    # files
    conn.executemany(
        "INSERT INTO files(path, title, file_type, size_bytes, category) "
        "VALUES (?,?,?,?,?)",
        [(f["path"], f["title"], f["file_type"], f["size_bytes"], f["category"])
         for f in files],
    )

    # sections + section_content + sections_fts (rowid == sections.id)
    text_cache: dict[str, str] = {}
    for i, s in enumerate(sections, 1):
        conn.execute(
            "INSERT INTO sections(id, sec_num, title, file_path, anchor, depth, parent_num) "
            "VALUES (?,?,?,?,?,?,?)",
            (i, s["sec_num"], s["title"], s["file_path"], s["anchor"],
             s["depth"], s["parent_num"]),
        )
        raw = text_cache.get(s["file_path"])
        if raw is None:
            raw = extract_page_text(manual_dir, s["file_path"])
            text_cache[s["file_path"]] = raw
        conn.execute(
            "INSERT INTO section_content(section_id, raw_text) VALUES (?,?)", (i, raw)
        )
        conn.execute(
            "INSERT INTO sections_fts(rowid, sec_num, title, raw_text) VALUES (?,?,?,?)",
            (i, s["sec_num"], s["title"], raw),
        )

    # index_entries
    conn.executemany(
        "INSERT INTO index_entries(keyword, file_path, anchor, section_ref) VALUES (?,?,?,?)",
        entries,
    )

    # embeddings (unless skipped) + version envelope
    if not skip_embeddings:
        from dft_utils.embedding import embed_numpy

        texts = [f"{s['sec_num']} {s['title']}"[:8000] for s in sections]
        vecs = embed_numpy(texts)
        dim = int(vecs.shape[1])
        conn.executemany(
            "INSERT INTO section_embeddings"
            "(section_id, sec_num, title, file_path, embedding, dim) VALUES (?,?,?,?,?,?)",
            [(i, s["sec_num"], s["title"], s["file_path"],
              vecs[i - 1].astype("<f4").tobytes(), dim) for i, s in enumerate(sections, 1)],
        )
        print(f"[embeddings] wrote {len(sections)} x {dim} dim", file=sys.stderr)

    from dft_utils import DATA_VERSION
    conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES ('version', ?)",
                 (DATA_VERSION,))
    conn.commit()
    conn.close()

    print(
        f"[ok] {out}  sections={len(sections)} entries={len(entries)} files={len(files)}",
        file=sys.stderr,
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Rebuild openmx.db from the manual corpus.")
    p.add_argument("--manual", default=str(_REPO / "openmx4.0_manual"),
                   help="manual HTML directory (default repo openmx4.0_manual)")
    p.add_argument("--out", default=str(_REPO / "openmx.db"), help="output sqlite path")
    p.add_argument("--skip-embeddings", action="store_true",
                   help="skip semantic embeddings (FTS5 search still works)")
    p.add_argument("--force", action="store_true", help="overwrite an existing output DB")
    args = p.parse_args(argv)

    out = Path(args.out)
    if out.exists() and not args.force:
        raise SystemExit(
            f"{out} already exists (use --force to overwrite, or --out to a new path)"
        )
    build(Path(args.manual), out, skip_embeddings=args.skip_embeddings)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())