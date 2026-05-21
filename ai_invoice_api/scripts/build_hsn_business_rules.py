#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from app.database import get_connection


def _extract_hsn(additional_detail) -> str | None:
    if isinstance(additional_detail, str):
        try:
            additional_detail = json.loads(additional_detail)
        except Exception:
            return None
    if not isinstance(additional_detail, dict):
        return None
    for k in ("hsn_sac_code", "hsn_code", "hsn", "hsnSacCode"):
        v = additional_detail.get(k)
        if isinstance(v, str) and v.strip():
            return "".join(ch for ch in v if ch.isdigit()) or None
    return None


def main() -> None:
    conn = get_connection()
    counts: dict[str, dict[str, int]] = defaultdict(dict)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT industry, category, sub_category, additional_detail
                FROM invoices
                WHERE label_type = 'business'
                  AND industry IS NOT NULL AND industry != ''
                  AND category IS NOT NULL AND category != ''
                """
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    for r in rows:
        hsn = _extract_hsn(r.get("additional_detail"))
        if not hsn:
            continue
        label = f"{r.get('industry','')}||{r.get('category','')}||{r.get('sub_category') or ''}"
        for n in (8, 6, 4, 2):
            if len(hsn) >= n:
                p = hsn[:n]
                bucket = counts.setdefault(p, {})
                bucket[label] = bucket.get(label, 0) + 1

    out: dict[str, dict[str, str]] = {}
    for pref, bucket in counts.items():
        label = max(bucket.items(), key=lambda kv: kv[1])[0]
        ind, cat, sub = label.split("||", 2)
        out[pref] = {
            "industry": ind or None,
            "category": cat or None,
            "sub_category": sub or None,
        }

    model_dir = Path(os.getenv("RIVER_MODEL_DIR", "models/river"))
    model_dir.mkdir(parents=True, exist_ok=True)
    path = model_dir / "hsn_business_rules.json"
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved {len(out)} HSN prefixes to {path}")


if __name__ == "__main__":
    main()

