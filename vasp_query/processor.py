"""Parse raw VASP wiki and incar_data into structured queryable JSON files."""

import json
import re
from pathlib import Path

_VASP_BASE = Path(__file__).resolve().parent.parent  # /home/duguex/vasp_incar/
WIKI_RAW = _VASP_BASE / "vasp_wiki_all_data.json"
WIKI_FULL = Path(__file__).resolve().parent / "data" / "wiki_full.json"
TAG_INDEX = Path(__file__).resolve().parent / "data" / "tag_index.json"
INCAR_DATA = _VASP_BASE / "incar_data.json"
TAG_STATS = Path(__file__).resolve().parent / "data" / "tag_stats.json"

# Section markers that end the description block
_DESCRIPTION_ENDERS = re.compile(
    r"(?:\n|\n)(?:Output|Recommendations|Advice|Mind:\s*|Important:\s*|Tip:\s*|"
    r"Related tags and articles|Examples|References|Retrieved from|"
    r"Learn\s|Step\s+\d|Subcategories|Pages in category)",
    re.IGNORECASE,
)


def _clean_text(raw: str) -> str:
    """Convert escaped \\n to real newlines, then collapse whitespace."""
    text = raw.replace("\\n", "\n")
    # Replace [math]...</[math] with plain text
    text = re.sub(r"\[math\].*?\[/math\]", "", text, flags=re.DOTALL)
    # Collapse multiple spaces/newlines
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _parse_tag_page(item: dict) -> dict | None:
    """Extract structured fields from a single wiki page."""
    title = item.get("title", "")
    content = item.get("content", "")

    # Skip non-tag pages (tutorials, categories, etc.)
    if not re.match(r"^[A-Z][A-Z0-9_]*$", title):
        return None

    # Check if this page describes an INCAR tag
    # Tag pages have: TITLE\n= value\nDefault:\nTITLE\n= default_value\nDescription: ...
    lines_raw = content.split("\\n") if "\\n" in content else [content]
    first_word = lines_raw[0].strip() if lines_raw else ""
    if not first_word:
        return None
    # Quick heuristic: tag names are uppercase, and content has "= " on a following line
    if not first_word[0].isupper():
        return None
    # Also check there's a line with just "=" or "= value" (the tag definition)
    has_tag_def = any(line.strip() == "=" or line.strip().startswith("= ") or line.strip().startswith("=.") or line.strip() == f"{title}=" for line in lines_raw[:10])
    if not has_tag_def:
        return None

    raw = _clean_text(content)
    lines = [l.strip() for l in raw.split("\n") if l.strip()]

    # Extract value format and default
    # Line structure: TITLE, "= value", "Default:", TITLE, "= default", "Description: ...", ...
    value_format = ""
    default_value = ""

    for i, line in enumerate(lines):
        # Value format line: starts with "=" (after the title line)
        if line.startswith("=") and len(line) > 1 and not line.lower().startswith("default"):
            if value_format:
                continue  # Skip if already found one (could be default value line)
            value_format = line[1:].strip()  # Remove leading "="
        # Default value: line starting with "=" that appears after "Default:"
        if line.startswith("=") and i > 0 and lines[i-1] == title and default_value:
            continue  # Skip if already found one
        if line.lower().startswith("default:") and i + 1 < len(lines):
            # Next line should be title, then the one after is the value
            if i + 2 < len(lines) and lines[i + 2].startswith("="):
                default_value = lines[i + 2][1:].strip()

    # Extract description: everything after "Description:" line
    description = ""
    for i, line in enumerate(lines):
        if line.lower().startswith("description:"):
            rest = line.split(":", 1)[-1].strip()
            if rest:
                description = rest
            # Collect subsequent non-header lines
            for j in range(i + 1, len(lines)):
                ls = lines[j].lower()
                if any(ls.startswith(marker) for marker in
                       ("output", "recommendation", "related", "examples",
                        "references", "retrieved", "learn", "subcategor")):
                    break
                description += " " + lines[j]
            description = description.strip()
            break

    # Extract related tags
    related_tags = []
    for line in lines:
        if line.lower().startswith("related tags and articles"):
            idx = lines.index(line)
            for rl in lines[idx + 1:]:
                rl = rl.strip()
                if rl and re.match(r"^[A-Z][A-Z0-9_]*$", rl) and rl not in related_tags:
                    related_tags.append(rl)
                elif rl.startswith("Examples") or rl.startswith("References") or rl.startswith("Retrieved"):
                    break
            break

    url = item.get("url", "")

    return {
        "title": title,
        "value": value_format,
        "default": default_value,
        "description": description,
        "related": related_tags,
        "url": url,
    }


def parse_wiki_to_index() -> list[dict]:
    """Parse vasp_wiki_all_data.json into structured tag_index.json."""
    with open(WIKI_RAW, "r") as f:
        data = json.load(f)

    tags = []
    skipped = 0
    for item in data:
        result = _parse_tag_page(item)
        if result:
            tags.append(result)
        else:
            skipped += 1

    with open(TAG_INDEX, "w") as f:
        json.dump(tags, f, ensure_ascii=False, indent=2)

    print(f"Parsed {len(tags)} INCAR tags, skipped {skipped} pages")
    return tags


def make_wiki_full() -> None:
    """Save clean full wiki content for detailed lookups."""
    with open(WIKI_RAW, "r") as f:
        data = json.load(f)

    full = {}
    for item in data:
        title = item.get("title", "")
        if title:
            full[title] = {
                "content": _clean_text(item.get("content", "")),
                "url": item.get("url", ""),
            }

    with open(WIKI_FULL, "w") as f:
        json.dump(full, f, ensure_ascii=False, indent=2)

    print(f"Wrote {len(full)} wiki pages to wiki_full.json")


def extract_tag_stats() -> dict:
    """Extract tag frequency and common values from incar_data.json."""
    with open(INCAR_DATA, "r") as f:
        data = json.load(f)

    tag_counts: dict[str, int] = {}
    tag_values: dict[str, dict] = {}

    for config in data:
        incar = config.get("incar", {})
        for key, value in incar.items():
            tag_counts[key] = tag_counts.get(key, 0) + 1
            val_str = json.dumps(value, ensure_ascii=False, default=str)
            if key not in tag_values:
                tag_values[key] = {}
            tag_values[key][val_str] = tag_values[key].get(val_str, 0) + 1

    # Build summary: top 5 values per tag
    stats = {}
    for tag in sorted(tag_counts):
        count = tag_counts[tag]
        values = tag_values.get(tag, {})
        top_values = sorted(values.items(), key=lambda x: -x[1])[:5]
        stats[tag] = {
            "count": count,
            "total_configs": len(data),
            "frequency": round(count / len(data) * 100, 1),
            "top_values": [
                {"value": v, "count": c} for v, c in top_values
            ],
        }

    with open(TAG_STATS, "w") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    print(f"Extracted stats for {len(stats)} tags from {len(data)} configs")
    return stats


def preprocess() -> None:
    """Run all preprocessing steps."""
    Path(TAG_INDEX).parent.mkdir(parents=True, exist_ok=True)
    parse_wiki_to_index()
    make_wiki_full()
    extract_tag_stats()
    print("Preprocessing complete.")
