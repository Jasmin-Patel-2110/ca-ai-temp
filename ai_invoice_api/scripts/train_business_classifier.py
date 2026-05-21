#!/usr/bin/env python3
from __future__ import annotations

import os
import pickle
import sys
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression

_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from app.database import get_connection
from app.services.business_classifier_service import build_business_input_text
from app.services.business_industry_normalizer import normalize_business_industry


def main() -> None:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT industry, category, sub_category, product_name, additional_detail
                FROM invoices
                WHERE label_type = 'business'
                  AND industry IS NOT NULL AND industry != ''
                  AND category IS NOT NULL AND category != ''
                  AND sub_category IS NOT NULL AND sub_category != ''
                """
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    if not rows:
        print("No business-labeled rows found.")
        sys.exit(1)

    texts: list[str] = []
    labels: list[str] = []
    for r in rows:
        ind = normalize_business_industry(r.get("industry"))
        text = build_business_input_text(r, ind)
        if not text.strip():
            continue
        label = f"{ind} > {r.get('category')} > {r.get('sub_category')}"
        texts.append(text)
        labels.append(label)

    if len(set(labels)) < 2:
        print("Need at least 2 distinct business labels to train classifier.")
        sys.exit(1)

    from sentence_transformers import SentenceTransformer

    model_name = os.getenv(
        "BUSINESS_EMBED_MODEL",
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    )
    embedder = SentenceTransformer(model_name)
    X = embedder.encode(texts, normalize_embeddings=True)

    clf = LogisticRegression(
        C=10,
        max_iter=1000,
        multi_class="multinomial",
    )
    clf.fit(np.asarray(X), np.asarray(labels))

    model_dir = Path(os.getenv("RIVER_MODEL_DIR", "models/river"))
    model_dir.mkdir(parents=True, exist_ok=True)
    out = model_dir / "business_classifier.pkl"
    payload = {"clf": clf, "labels": list(clf.classes_)}
    with open(out, "wb") as f:
        pickle.dump(payload, f)
    print(f"Saved business classifier to {out} (classes={len(clf.classes_)})")


if __name__ == "__main__":
    main()

