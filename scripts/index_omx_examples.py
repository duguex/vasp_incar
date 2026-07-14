#!/usr/bin/env python3
"""Index OpenMX official work/**/*.dat examples into JSON corpus files.

Example:
  python3 scripts/index_omx_examples.py \\
      --root ~/openmx_container/openmx4.0/work \\
      --out data/omx_examples
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from omx_tools.examples_corpus import (  # noqa: E402
    envelope,
    extract_openmx_scalars,
    infer_intent,
)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def index_tree(root: Path, source_label: str = "openmx/work") -> list[dict]:
    root = root.resolve()
    by_hash: dict[str, dict] = {}
    errors = 0
    scanned = 0

    for path in sorted(root.rglob("*.dat")):
        if not path.is_file():
            continue
        scanned += 1
        try:
            rel = str(path.relative_to(root)).replace("\\", "/")
            digest = _sha256(path)
            keywords = extract_openmx_scalars(path)
            rec = {
                "id": rel,
                "path": rel,
                "sha256": digest,
                "intent": infer_intent(rel, keywords),
                "keywords": keywords,
                "keyword_names": sorted(keywords.keys()),
                "source": source_label,
                "bytes": path.stat().st_size,
            }
            if digest in by_hash:
                prev = by_hash[digest]
                if len(rel) < len(prev["id"]):
                    by_hash[digest] = rec
            else:
                by_hash[digest] = rec
        except Exception as e:
            errors += 1
            print(f"[warn] skip {path}: {e}", file=sys.stderr)

    records = sorted(by_hash.values(), key=lambda r: r["id"])
    print(
        f"scanned={scanned} unique={len(records)} errors={errors} root={root}",
        file=sys.stderr,
    )
    return records


def build_stats_sidecar(records: list[dict], top_k: int = 100) -> dict:
    from collections import Counter

    freq: Counter[str] = Counter()
    for rec in records:
        for kn in rec.get("keyword_names") or []:
            freq[kn] += 1
    total = len(records)
    return {
        "total_examples": total,
        "top_keywords": [
            {
                "keyword": k,
                "count": c,
                "frequency_pct": round(c / total * 100, 1) if total else 0.0,
            }
            for k, c in freq.most_common(top_k)
        ],
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--root",
        type=Path,
        default=Path.home() / "openmx_container" / "openmx4.0" / "work",
        help="Root directory to scan for .dat files",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=_REPO / "data" / "omx_examples",
        help="Output directory for JSON index files",
    )
    p.add_argument(
        "--source-label",
        default="openmx4.0/work",
        help="Value stored in each record's source field",
    )
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)

    if not args.root.is_dir():
        print(f"error: root not a directory: {args.root}", file=sys.stderr)
        return 1

    records = index_tree(args.root, source_label=args.source_label)
    args.out.mkdir(parents=True, exist_ok=True)
    index_path = args.out / "examples_index.json"
    stats_path = args.out / "examples_stats.json"

    index_path.write_text(
        json.dumps(envelope(records), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    stats_path.write_text(
        json.dumps(envelope(build_stats_sidecar(records)), indent=2, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )
    print(f"wrote {index_path} ({len(records)} records)")
    print(f"wrote {stats_path}")
    if args.verbose and records:
        print(
            "sample:",
            records[0]["id"],
            records[0]["intent"],
            len(records[0].get("keyword_names") or []),
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
