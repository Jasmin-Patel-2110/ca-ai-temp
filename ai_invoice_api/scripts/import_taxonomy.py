"""
Import industry/category/sub_category taxonomy into app/taxonomy.py.

Usage:
  python scripts/import_taxonomy.py --input taxonomy_input.txt

Input format accepted:
- Proper JSON list of objects:
    [{"industry":"Supari","category":{"Sales Accounts":["Sales"]}}]
- JS-like list used in chats (keys without quotes):
    [{ industry: "Supari", category: { "Sales Accounts": ["Sales"] } }]
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
TAXONOMY_PY = WORKSPACE_ROOT / "app" / "taxonomy.py"


def _extract_json_array_blob(raw: str) -> str:
    # Preferred: explicit array wrapper
    start = raw.find("[")
    end = raw.rfind("]")
    if start != -1 and end != -1 and end > start:
        candidate = raw[start : end + 1]
        # Guard against selecting a bracket from inside labels like "GST@12%]".
        if re.search(r"\[\s*\{", candidate):
            return candidate

    # Recovery path for chat-pasted partial blocks:
    # find first industry object and reconstruct an array from there.
    m = re.search(r"\{\s*(?:\"industry\"|industry)\s*:", raw)
    if not m:
        raise ValueError("Input must contain taxonomy objects with 'industry' key")
    obj_start = m.start()
    tail = raw[obj_start:]
    tail = tail.lstrip(", \r\n\t")

    end = tail.rfind("]")
    if end != -1:
        tail = tail[: end + 1]
    # If no outer [ ... ], wrap recovered content.
    if not tail.lstrip().startswith("["):
        tail = f"[{tail}]"
    return tail


def _js_like_to_json(raw: str) -> str:
    # Quote object keys when missing quotes: industry: -> "industry":
    s = re.sub(r'([{\[,]\s*)([A-Za-z_][A-Za-z0-9_]*)\s*:', r'\1"\2":', raw)
    # Remove trailing commas before } or ]
    s = re.sub(r",\s*([}\]])", r"\1", s)
    return s


def _find_matching_brace(s: str, start_idx: int) -> int:
    depth = 0
    in_str = False
    esc = False
    for i in range(start_idx, len(s)):
        ch = s[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
    return -1


def _extract_industry_objects(raw: str) -> str:
    blocks: list[str] = []
    for m in re.finditer(r"\{\s*(?:\"industry\"|industry)\s*:", raw):
        sidx = m.start()
        eidx = _find_matching_brace(raw, sidx)
        if eidx == -1:
            continue
        block = raw[sidx : eidx + 1].strip()
        if block:
            blocks.append(block)
    if not blocks:
        raise ValueError("No complete industry taxonomy objects found in input")
    return "[\n" + ",\n".join(blocks) + "\n]"


def _normalize_taxonomy(items: list[dict]) -> dict[str, dict[str, list[str]]]:
    out: dict[str, dict[str, list[str]]] = {}
    for row in items:
        if not isinstance(row, dict):
            continue
        industry = str(row.get("industry") or "").strip()
        category = row.get("category")
        if not industry or not isinstance(category, dict):
            continue
        if industry.lower() == "government":
            industry = "Gov"

        cat_map: dict[str, list[str]] = {}
        for cat_name, subs in category.items():
            if not isinstance(cat_name, str):
                continue
            if not isinstance(subs, list):
                continue
            clean_subs = [str(s).strip() for s in subs if str(s).strip()]
            cat_map[cat_name.strip()] = clean_subs
        out[industry] = cat_map
    return out


def _replace_taxonomy_block(taxonomy_py_text: str, new_map: dict[str, dict[str, list[str]]]) -> str:
    start_marker = "INDUSTRY_CATEGORY_TAXONOMY: dict[str, dict[str, list[str]]] = "
    end_marker = "\ndef get_categories_for_industry("

    start = taxonomy_py_text.find(start_marker)
    end = taxonomy_py_text.find(end_marker)
    if start == -1 or end == -1 or end <= start:
        raise RuntimeError("Could not locate taxonomy block in app/taxonomy.py")

    serialized = json.dumps(new_map, ensure_ascii=True, indent=4)
    replacement = f'{start_marker}{serialized}\n'
    return taxonomy_py_text[:start] + replacement + taxonomy_py_text[end:]


def main() -> None:
    parser = argparse.ArgumentParser(description="Import taxonomy into app/taxonomy.py")
    parser.add_argument("--input", required=True, help="Path to taxonomy input file")
    args = parser.parse_args()

    input_path = Path(args.input).expanduser().resolve()
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    raw = input_path.read_text(encoding="utf-8")
    arr_blob = _extract_json_array_blob(raw)
    json_like = _js_like_to_json(arr_blob)
    try:
        items = json.loads(json_like)
    except json.JSONDecodeError:
        recovered = _extract_industry_objects(raw)
        items = json.loads(_js_like_to_json(recovered))
    if not isinstance(items, list):
        raise ValueError("Top-level taxonomy input must be a list")

    normalized = _normalize_taxonomy(items)
    if not normalized:
        raise ValueError("No valid taxonomy rows found in input")

    taxonomy_src = TAXONOMY_PY.read_text(encoding="utf-8")
    updated = _replace_taxonomy_block(taxonomy_src, normalized)
    TAXONOMY_PY.write_text(updated, encoding="utf-8")

    print(f"Imported industries: {len(normalized)}")
    print(f"Updated: {TAXONOMY_PY}")


if __name__ == "__main__":
    main()

