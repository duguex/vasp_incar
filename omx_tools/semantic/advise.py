"""Advise loop: lint ↔ knowledge ↔ (optional) safe fix ↔ re-lint.

Organically couples **input review** with the **knowledge bases**:

1. lint findings
2. attach knowledge snippets per tag (vasp_query / omx schema+examples)
3. optional safe auto-fix + re-lint (bounded)
4. single JSON report for agents

Does not run DFT. Does not invent tag meanings beyond rules + DB text.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable


def _parse_incar_simple(path: Path) -> dict[str, Any]:
    try:
        from omx_tools.parsers.vasp import parse_incar
        return {str(k).upper(): v for k, v in parse_incar(str(path)).items()}
    except Exception:
        out: dict[str, Any] = {}
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.split("#", 1)[0].strip()
            if not line or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip().upper(), v.strip()
            try:
                if "." in v or "e" in v.lower():
                    out[k] = float(v)
                else:
                    out[k] = int(v)
            except ValueError:
                if v.upper() in (".TRUE.", "TRUE", "T"):
                    out[k] = True
                elif v.upper() in (".FALSE.", "FALSE", "F"):
                    out[k] = False
                else:
                    out[k] = v
        return out


def _vasp_knowledge_for_tag(tag: str) -> dict[str, Any]:
    try:
        from vasp_query._common import (
            TAG_CONFIGS,
            TAG_COOCCUR,
            TAG_STATS,
            load_data,
            load_tag_index,
            query_tag,
            resolve_tag,
        )
    except Exception as e:
        return {"tag": tag, "found": False, "error": f"vasp_query unavailable: {e}"}

    tag_u = tag.upper().strip()
    index = load_tag_index()
    if not index:
        return {"tag": tag_u, "found": False, "suggestion": "run vasp_query preprocess"}
    resolved = resolve_tag(tag_u, index)
    if resolved is None:
        return {
            "tag": tag_u,
            "found": False,
            "suggestion": f"vasp-query search '{tag_u}'",
        }
    if isinstance(resolved, list):
        return {
            "tag": tag_u,
            "found": False,
            "matches": [t.get("title") for t in resolved[:8]],
            "suggestion": "vasp-query tag <match>",
        }
    try:
        full = query_tag(
            resolved,
            configs=load_data(TAG_CONFIGS),
            stats=load_data(TAG_STATS),
            cooccur=load_data(TAG_COOCCUR),
        )
        info = full.get("info") or resolved
        stats = full.get("stats") or {}
        return {
            "tag": info.get("title") or tag_u,
            "found": True,
            "default": info.get("default"),
            "description": (info.get("description") or "")[:400],
            "url": info.get("url"),
            "top_values": (stats.get("top_values") or [])[:3],
            "related_tags": (info.get("related") or [])[:8],
            "cli": f"vasp-query tag {info.get('title') or tag_u}",
        }
    except Exception as e:
        return {"tag": tag_u, "found": False, "error": str(e)}


def _omx_knowledge_for_tag(tag: str) -> dict[str, Any]:
    out: dict[str, Any] = {"tag": tag, "found": False}
    try:
        import json
        schema_path = Path(__file__).resolve().parent.parent / "schemas" / "keywords.json"
        schema = json.loads(schema_path.read_text())
        entry = schema.get(tag)
        if entry is None:
            lower = {k.lower(): k for k in schema}
            canon = lower.get(tag.lower())
            if canon:
                tag = canon
                entry = schema.get(canon)
        if entry:
            out.update({
                "found": True,
                "keyword": tag,
                "type": entry.get("type"),
                "default": entry.get("default"),
                "section": entry.get("section"),
                "description": (entry.get("description") or "")[:400],
                "cli": f"omx-db keyword {tag}",
            })
    except Exception as e:
        out["schema_error"] = str(e)
    try:
        from omx_tools.examples_corpus import load_index, search_examples
        hits = search_examples(load_index(), keyword=tag, limit=3)
        if not hits:
            hits = search_examples(load_index(), query=tag, limit=3)
        if hits:
            out["found"] = True
            out["examples"] = [
                {"id": h.get("id"), "intent": h.get("intent")} for h in hits
            ]
            out["cli_examples"] = f"omx-db example --keyword {tag}"
    except Exception:
        pass
    return out


def attach_knowledge(
    findings: list[dict[str, Any]],
    *,
    code: str = "vasp",
) -> list[dict[str, Any]]:
    enriched = []
    cache: dict[str, Any] = {}
    for f in findings:
        item = dict(f)
        know = []
        for tag in f.get("tags") or []:
            key = f"{code}:{tag}"
            if key not in cache:
                cache[key] = (
                    _vasp_knowledge_for_tag(tag)
                    if code == "vasp"
                    else _omx_knowledge_for_tag(tag)
                )
            if cache[key]:
                know.append(cache[key])
        item["knowledge"] = know
        enriched.append(item)
    return enriched


def _fix_nsw_ibrion(incar: dict[str, Any]) -> tuple[dict[str, Any], str] | None:
    try:
        nsw_i = int(incar["NSW"]) if "NSW" in incar else None
        ibr_i = int(incar["IBRION"]) if "IBRION" in incar else None
    except (TypeError, ValueError, KeyError):
        return None
    if nsw_i is not None and nsw_i > 0 and ibr_i == -1:
        out = dict(incar)
        out["IBRION"] = 2
        return out, "Set IBRION=2 because NSW>0 with IBRION=-1 cannot move ions"
    if nsw_i == 0 and ibr_i is not None and ibr_i > 0:
        out = dict(incar)
        out["IBRION"] = -1
        return out, "Set IBRION=-1 for static run (NSW=0)"
    return None


def _fix_icharg_nsw(incar: dict[str, Any]) -> tuple[dict[str, Any], str] | None:
    try:
        icharg = int(incar["ICHARG"]) if "ICHARG" in incar else None
        nsw = int(incar["NSW"]) if "NSW" in incar else None
    except (TypeError, ValueError, KeyError):
        return None
    if icharg == 11 and nsw is not None and nsw > 0:
        out = dict(incar)
        out["NSW"] = 0
        out["IBRION"] = -1
        return out, "ICHARG=11 non-SCF: force NSW=0, IBRION=-1"
    return None


def _fix_ediffg_for_relax(incar: dict[str, Any]) -> tuple[dict[str, Any], str] | None:
    try:
        nsw = int(incar["NSW"]) if "NSW" in incar else None
    except (TypeError, ValueError, KeyError):
        return None
    if nsw is not None and nsw > 0 and "EDIFFG" not in incar:
        out = dict(incar)
        out["EDIFFG"] = -0.02
        return out, "Added EDIFFG=-0.02 for ionic relaxation (NSW>0)"
    return None


SAFE_FIXES: list[Callable[[dict[str, Any]], tuple[dict[str, Any], str] | None]] = [
    _fix_nsw_ibrion,
    _fix_icharg_nsw,
    _fix_ediffg_for_relax,
]


def apply_safe_fixes(incar: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    out = {str(k).upper(): v for k, v in incar.items()}
    notes: list[str] = []
    for fn in SAFE_FIXES:
        res = fn(out)
        if res:
            out, note = res
            notes.append(note)
    return out, notes


def advise_vasp(
    incar: dict[str, Any],
    *,
    path: str | None = None,
    fetch_knowledge: bool = True,
    auto_fix: bool = False,
    max_rounds: int = 3,
) -> dict[str, Any]:
    """Lint → knowledge → optional safe-fix loop for VASP INCAR tags."""
    from omx_tools.semantic.lint import lint_vasp_incar

    original = {str(k).upper(): v for k, v in incar.items()}
    current = dict(original)
    history: list[dict[str, Any]] = []
    all_fixes: list[str] = []
    rounds = max(1, max_rounds if auto_fix else 1)

    for i in range(rounds):
        rep = lint_vasp_incar(current, path=path, use_ir_hint=True)
        findings = [f.as_dict() for f in rep.findings]
        if fetch_knowledge:
            findings = attach_knowledge(findings, code="vasp")
        history.append({
            "round": i,
            "ok": rep.ok,
            "n_error": rep.n_error,
            "n_warning": rep.n_warning,
            "calc_class_hint": rep.calc_class_hint,
            "findings": findings,
        })
        if not auto_fix or rep.ok:
            break
        new_incar, notes = apply_safe_fixes(current)
        if not notes or new_incar == current:
            break
        all_fixes.extend(notes)
        current = new_incar
    else:
        rep = lint_vasp_incar(current, path=path, use_ir_hint=True)
        findings = [f.as_dict() for f in rep.findings]
        if fetch_knowledge:
            findings = attach_knowledge(findings, code="vasp")
        history.append({
            "round": len(history),
            "ok": rep.ok,
            "n_error": rep.n_error,
            "n_warning": rep.n_warning,
            "calc_class_hint": rep.calc_class_hint,
            "findings": findings,
            "after_fixes": True,
        })

    # ensure final rep matches last history
    last = history[-1]
    return {
        "ok": last["ok"],
        "path": path,
        "loop": "lint → knowledge → [safe fix → lint]*",
        "auto_fix": auto_fix,
        "fixes_applied": all_fixes,
        "incar_final": current,
        "incar_changed": current != original,
        "calc_class_hint": last.get("calc_class_hint"),
        "n_error": last["n_error"],
        "n_warning": last["n_warning"],
        "findings": last["findings"],
        "history": history if auto_fix else [],
    }


def advise_vasp_file(
    path: str,
    *,
    fetch_knowledge: bool = True,
    auto_fix: bool = False,
    max_rounds: int = 3,
    write_fixed: str | None = None,
) -> dict[str, Any]:
    p = Path(path)
    incar = _parse_incar_simple(p)
    report = advise_vasp(
        incar,
        path=str(p),
        fetch_knowledge=fetch_knowledge,
        auto_fix=auto_fix,
        max_rounds=max_rounds,
    )
    if write_fixed and report.get("incar_changed"):
        from vasp_query.generator import render_incar
        text = render_incar(
            report["incar_final"],
            comments=["written by dft semantic advise --fix"],
        )
        Path(write_fixed).write_text(text, encoding="utf-8")
        report["written"] = write_fixed
    return report


def generate_and_advise_vasp(
    *,
    template: str = "scf",
    structure: str | None = None,
    sets: list[str] | None = None,
    fetch_knowledge: bool = True,
    auto_fix: bool = False,
) -> dict[str, Any]:
    """generate (template) → advise loop — couples generation with knowledge."""
    from vasp_query.generator import _load_templates, apply_overrides

    templates = _load_templates()
    if template not in templates:
        return {
            "ok": False,
            "error": f"unknown template {template}",
            "suggestion": "vasp-gen --list-templates",
        }
    tags = dict(templates[template].get("tags") or {})
    tags = apply_overrides(tags, sets=sets or [])
    report = advise_vasp(
        tags,
        path=f"<generated:{template}>",
        fetch_knowledge=fetch_knowledge,
        auto_fix=auto_fix,
    )
    report["generated_template"] = template
    report["structure"] = structure
    report["loop"] = "generate → lint → knowledge → [safe fix → lint]*"
    return report


def advise_openmx_dat(
    path: str,
    *,
    fetch_knowledge: bool = True,
) -> dict[str, Any]:
    from omx_tools.semantic.lint import lint_openmx_dat

    rep = lint_openmx_dat(path)
    findings = [f.as_dict() for f in rep.findings]
    if fetch_knowledge:
        findings = attach_knowledge(findings, code="omx")
    return {
        "ok": rep.ok,
        "path": path,
        "loop": "lint-omx → knowledge (schema + examples)",
        "n_error": rep.n_error,
        "n_warning": rep.n_warning,
        "n_info": rep.n_info,
        "findings": findings,
        "auto_fix": False,
    }
