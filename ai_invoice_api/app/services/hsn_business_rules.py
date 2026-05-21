from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional


def _rules_path() -> Path:
    model_dir = Path(os.getenv("RIVER_MODEL_DIR", "models/river"))
    return model_dir / "hsn_business_rules.json"


def load_hsn_rules() -> dict[str, dict[str, str]]:
    path = _rules_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def resolve_by_hsn_prefix(
    hsn_code: Optional[str],
    rules: Optional[dict[str, dict[str, str]]] = None,
) -> tuple[Optional[str], Optional[str], Optional[str], bool]:
    """
    Longest-prefix HSN lookup in order: 8, 6, 4, 2.
    Returns (industry, category, sub_category, matched).
    """
    if not hsn_code:
        return None, None, None, False
    h = "".join(ch for ch in str(hsn_code) if ch.isdigit())
    if len(h) < 2:
        return None, None, None, False

    data = rules if rules is not None else load_hsn_rules()
    if not data:
        return None, None, None, False

    for n in (8, 6, 4, 2):
        if len(h) >= n:
            pref = h[:n]
            rec = data.get(pref)
            if rec:
                return (
                    rec.get("industry"),
                    rec.get("category"),
                    rec.get("sub_category"),
                    True,
                )
    return None, None, None, False

