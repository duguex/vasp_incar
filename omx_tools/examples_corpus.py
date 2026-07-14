"""Official OpenMX .dat example corpus — index load/query helpers.

Corpus is built by ``scripts/index_omx_examples.py`` from an OpenMX ``work/``
tree (demonstration inputs, not a multi-user INCAR-scale dump).
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from dft_utils import DATA_VERSION
from dft_utils.version import load_data

PKG_DIR = Path(__file__).resolve().parent
REPO_ROOT = PKG_DIR.parent

# Preferred locations (first existing wins for default load)
_DEFAULT_INDEX_CANDIDATES = [
    REPO_ROOT / "data" / "omx_examples" / "examples_index.json",
    PKG_DIR / "data" / "omx_examples" / "examples_index.json",
]

_LINE_KW = re.compile(
    r"^(?P<key>[A-Za-z][A-Za-z0-9_./]*)\s+(?P<val>\S.*?)(?:\s*#.*)?$"
)


def extract_openmx_scalars(path: Path | str) -> dict[str, Any]:
    """Extract scalar OpenMX keywords (dotted names) from a .dat file.

    Skips ``<Block ... Block>`` sections. Values coerced to int/float when possible.
    """
    path = Path(path)
    result: dict[str, Any] = {}
    in_block = False
    with path.open(encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("<"):
                in_block = True
                continue
            if in_block:
                # end of block: line equals BlockName> without leading <
                if line.endswith(">") and not line.startswith("<"):
                    in_block = False
                continue
            m = _LINE_KW.match(line)
            if not m:
                continue
            key = m.group("key")
            # skip obvious non-keywords / paths-only noise
            if key.lower() in {"system.currrentdirectory"}:
                # still record for completeness
                pass
            val_s = m.group("val").strip()
            # multi-token grids: take full remainder as string or tuple of numbers
            parts = val_s.split()
            if len(parts) > 1:
                nums: list[Any] = []
                ok = True
                for p in parts:
                    try:
                        nums.append(int(p))
                    except ValueError:
                        try:
                            nums.append(float(p))
                        except ValueError:
                            ok = False
                            break
                result[key] = nums if ok else val_s
            else:
                result[key] = _coerce(val_s)
    return result


def _coerce(s: str) -> Any:
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        return s


def infer_intent(rel_path: str, keywords: dict[str, Any] | None = None) -> str:
    """Path-first intent tag for an example file."""
    p = rel_path.replace("\\", "/").lower()
    if "geoopt" in p or "cellopt" in p:
        return "geom_opt"
    if "negf" in p:
        return "negf"
    if "ml_example" in p or "/md" in p or p.startswith("md"):
        return "ml"
    if "force_example" in p:
        return "force"
    if "band" in p or "dispersion" in p:
        return "band"
    if "unfold" in p:
        return "unfold"
    if "cwf" in p or "wannier" in p:
        return "wannier"
    kw = keywords or {}
    md = str(kw.get("MD.Type", kw.get("md.type", ""))).lower()
    if md in {"opt", "diis2", "ef", "rf", "bfgs"}:
        return "geom_opt"
    if any(k.upper().startswith("NEGF") for k in kw):
        return "negf"
    return "scf"


def default_index_path() -> Path | None:
    for p in _DEFAULT_INDEX_CANDIDATES:
        if p.is_file():
            return p
    return None


def load_index(path: Path | str | None = None) -> list[dict[str, Any]]:
    """Load examples index records (list). Raises FileNotFoundError if missing."""
    if path is None:
        found = default_index_path()
        if found is None:
            raise FileNotFoundError(
                "examples_index.json not found. Run: "
                "python3 scripts/index_omx_examples.py --root <openmx/work>"
            )
        path = found
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(str(path))
    data = load_data(path)
    if data is None:
        raise FileNotFoundError(str(path))
    if isinstance(data, dict) and "records" in data:
        data = data["records"]
    if not isinstance(data, list):
        raise ValueError(f"invalid examples index format: {path}")
    return data


def search_examples(
    records: list[dict[str, Any]],
    *,
    query: str | None = None,
    intent: str | None = None,
    keyword: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Filter example records by free text, intent, and/or keyword presence."""
    q = (query or "").strip().lower()
    intent_f = (intent or "").strip().lower()
    kw_f = (keyword or "").strip()

    out: list[dict[str, Any]] = []
    for rec in records:
        if intent_f and str(rec.get("intent", "")).lower() != intent_f:
            continue
        names = rec.get("keyword_names") or list((rec.get("keywords") or {}).keys())
        kws = rec.get("keywords") or {}
        if kw_f:
            # exact then case-insensitive
            if kw_f not in kws and kw_f not in names:
                lower_map = {n.lower(): n for n in names}
                if kw_f.lower() not in lower_map:
                    continue
        matches: list[str] = []
        if q:
            blob_parts = [
                str(rec.get("id", "")),
                str(rec.get("path", "")),
                str(rec.get("intent", "")),
                " ".join(names),
            ]
            blob = " ".join(blob_parts).lower()
            if q not in blob:
                # also match keyword values
                val_hit = False
                for kn, kv in kws.items():
                    if q in kn.lower() or q in str(kv).lower():
                        matches.append(kn)
                        val_hit = True
                if not val_hit:
                    continue
            else:
                for kn in names:
                    if q in kn.lower():
                        matches.append(kn)
        if kw_f:
            matches.append(kw_f)
        out.append({
            "id": rec.get("id"),
            "intent": rec.get("intent"),
            "path": rec.get("path"),
            "matches": sorted(set(matches)) if matches else ([] if not q and not kw_f else [kw_f] if kw_f else []),
            "n_keywords": len(names),
        })
        if len(out) >= limit:
            break
    return out


def example_stats(
    records: list[dict[str, Any]],
    keyword: str | None = None,
    top_k: int = 20,
) -> dict[str, Any]:
    """Keyword frequency and optional value distribution across examples."""
    total = len(records)
    freq: Counter[str] = Counter()

    if keyword:
        count = 0
        val_counter: Counter[str] = Counter()
        for rec in records:
            kws = rec.get("keywords") or {}
            hit = None
            for kn, kv in kws.items():
                if kn.lower() == keyword.lower():
                    hit = kv
                    break
            if hit is not None:
                count += 1
                val_counter[str(hit)] += 1
        return {
            "total_examples": total,
            "keyword": keyword,
            "count": count,
            "frequency_pct": round(count / total * 100, 1) if total else 0.0,
            "top_values": [
                {"value": v, "count": c}
                for v, c in val_counter.most_common(top_k)
            ],
        }

    for rec in records:
        kws = rec.get("keywords") or {}
        for kn in kws:
            freq[kn] += 1

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


def example_cooccur(
    records: list[dict[str, Any]],
    kw_a: str,
    kw_b: str,
    top_pairs: int = 10,
) -> dict[str, Any]:
    """Co-occurrence of two keywords across example files."""
    total = len(records)
    count_a = count_b = count_both = 0
    pairs: Counter[tuple[str, str]] = Counter()

    def _get(kws: dict, name: str) -> Any | None:
        if name in kws:
            return kws[name]
        for kn, kv in kws.items():
            if kn.lower() == name.lower():
                return kv
        return None

    for rec in records:
        kws = rec.get("keywords") or {}
        va = _get(kws, kw_a)
        vb = _get(kws, kw_b)
        has_a = va is not None
        has_b = vb is not None
        if has_a:
            count_a += 1
        if has_b:
            count_b += 1
        if has_a and has_b:
            count_both += 1
            pairs[(str(va), str(vb))] += 1

    return {
        "keyword_a": kw_a,
        "keyword_b": kw_b,
        "total_examples": total,
        "count_a": count_a,
        "frequency_a_pct": round(count_a / total * 100, 1) if total else 0.0,
        "count_b": count_b,
        "frequency_b_pct": round(count_b / total * 100, 1) if total else 0.0,
        "cooccur_count": count_both,
        "cooccur_pct": round(count_both / total * 100, 1) if total else 0.0,
        "top_pairs": [
            {"pair": f"{a}|{b}", "count": c}
            for (a, b), c in pairs.most_common(top_pairs)
        ],
    }


def envelope(data: Any, version: str = DATA_VERSION) -> dict[str, Any]:
    return {"_version": version, "data": data}
