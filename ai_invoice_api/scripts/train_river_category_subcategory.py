#!/usr/bin/env python3
"""
Train sklearn logistic models for invoice `category` and `sub_category`.

Trains:
1. One category classifier per `industry` (multiclass logistic).
2. One sub-category classifier per `(industry, category)` (multiclass logistic).

Input labels come from DB columns: invoices.category / invoices.sub_category.
Features come from extracted text fields stored in:
- product_name
- buyer_party_name / seller_party_name
- additional_detail.line_items[*]

Run:
  python scripts/train_river_category_subcategory.py
"""

from __future__ import annotations

import argparse
import os
import pickle
import sys
from pathlib import Path
from collections import defaultdict


_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from app.database import get_connection
from app.models.invoice import _parse_row
from app.services.category_river_service import build_feature_text, _new_text_classifier


def main() -> None:
    parser = argparse.ArgumentParser(description="Train sklearn logistic category/sub_category classifiers")
    parser.add_argument("--model-dir", default=os.getenv("RIVER_MODEL_DIR", "models/river"))
    parser.add_argument("--limit", type=int, default=0, help="Max labeled rows to use (0 = all)")
    args = parser.parse_args()

    out_dir = Path(args.model_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "logistic_models.pkl"

    # Training buffers
    cat_texts_by_industry: dict[str, list[str]] = defaultdict(list)
    cat_labels_by_industry: dict[str, list[str]] = defaultdict(list)

    sub_texts_by_key: dict[str, list[str]] = defaultdict(list)
    sub_labels_by_key: dict[str, list[str]] = defaultdict(list)

    cat_count_by_industry: dict[str, dict[str, int]] = defaultdict(dict)
    sub_count_by_ind_cat: dict[str, dict[str, int]] = defaultdict(dict)
    sub_count_by_category: dict[str, dict[str, int]] = defaultdict(dict)

    sql = """
        SELECT
            id,
            user_id,
            doc_id,
            industry,
            category,
            sub_category,
            client_name,
            buyer_party_name,
            seller_party_name,
            product_name,
            additional_detail
        FROM invoices
        WHERE industry IS NOT NULL AND industry != ''
          AND category IS NOT NULL AND category != ''
          -- sub_category can be NULL/empty; we encode it as a placeholder in the combined label
        ORDER BY id DESC
    """
    if args.limit:
        sql += f" LIMIT {int(args.limit)}"

    labeled_rows: list[dict] = []
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            labeled_rows = cur.fetchall()
    finally:
        conn.close()

    if not labeled_rows:
        print("No labeled invoices found for training (industry + category). Nothing to do.")
        sys.exit(1)

    used_rows = 0
    for raw_row in labeled_rows:
        try:
            row = _parse_row(dict(raw_row))
        except Exception:
            continue
        if not row:
            continue

        ind = (row.get("industry") or "").strip()
        cat = (row.get("category") or "").strip()
        sub = (row.get("sub_category") or "").strip()

        if not ind or not cat:
            continue

        text = build_feature_text(row)
        if not text.strip():
            continue

        # Category training by industry
        cat_texts_by_industry[ind].append(text)
        cat_labels_by_industry[ind].append(cat)
        cat_bucket = cat_count_by_industry.setdefault(ind, {})
        cat_bucket[cat] = cat_bucket.get(cat, 0) + 1

        # Subcategory training by (industry, category), only when sub exists
        if sub:
            key = f"{ind}||{cat}"
            sub_texts_by_key[key].append(text)
            sub_labels_by_key[key].append(sub)

            bucket_ind_cat = sub_count_by_ind_cat.setdefault(key, {})
            bucket_ind_cat[sub] = bucket_ind_cat.get(sub, 0) + 1

            bucket_cat = sub_count_by_category.setdefault(cat, {})
            bucket_cat[sub] = bucket_cat.get(sub, 0) + 1
        used_rows += 1

    category_models_by_industry: dict[str, object] = {}
    for ind, texts in cat_texts_by_industry.items():
        labels = cat_labels_by_industry.get(ind, [])
        if len(texts) < 2 or len(set(labels)) < 2:
            # Need at least 2 classes for multinomial logistic.
            continue
        model = _new_text_classifier()
        model.fit(texts, labels)
        category_models_by_industry[ind] = model

    most_category_by_industry: dict[str, str] = {}
    for ind, cat_counts in cat_count_by_industry.items():
        if not cat_counts:
            continue
        most_cat = max(cat_counts.items(), key=lambda kv: kv[1])[0]
        most_category_by_industry[ind] = most_cat

    subcategory_models_by_ind_cat: dict[str, object] = {}
    for key, texts in sub_texts_by_key.items():
        labels = sub_labels_by_key.get(key, [])
        if len(texts) < 2 or len(set(labels)) < 2:
            continue
        model = _new_text_classifier()
        model.fit(texts, labels)
        subcategory_models_by_ind_cat[key] = model

    most_sub_by_ind_cat: dict[str, str] = {}
    for key, sub_counts in sub_count_by_ind_cat.items():
        if not sub_counts:
            continue
        most_sub_by_ind_cat[key] = max(sub_counts.items(), key=lambda kv: kv[1])[0]

    most_sub_by_category: dict[str, str] = {}
    for cat_value, sub_counts in sub_count_by_category.items():
        if not sub_counts:
            continue
        most_sub = max(sub_counts.items(), key=lambda kv: kv[1])[0]
        most_sub_by_category[cat_value] = most_sub

    payload = {
        "category_models_by_industry": category_models_by_industry,
        "subcategory_models_by_ind_cat": subcategory_models_by_ind_cat,
        "most_category_by_industry": most_category_by_industry,
        "most_sub_by_ind_cat": most_sub_by_ind_cat,
        "most_sub_by_category": most_sub_by_category,
    }

    tmp_path = out_path.with_suffix(".pkl.tmp")
    with open(tmp_path, "wb") as f:
        pickle.dump(payload, f)
    os.replace(tmp_path, out_path)

    print(f"Trained category models: {len(category_models_by_industry)}")
    print(f"Trained subcategory models: {len(subcategory_models_by_ind_cat)}")
    print(f"Used labeled rows: {used_rows}")
    print(f"Saved: {out_path}")


if __name__ == "__main__":
    main()

