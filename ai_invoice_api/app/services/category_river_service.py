from __future__ import annotations

import json
import os
import pickle
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
except Exception as e:  # pragma: no cover
    raise RuntimeError(
        "scikit-learn is required for category/sub_category prediction. "
        "Run: pip install scikit-learn"
    ) from e

from app.services.extraction_service import apply_government_industry_override
from app.taxonomy import get_categories_for_industry, suggest_taxonomy_labels


def _alias_subcategory_when_same_as_product(
    product_name: Optional[str],
    sub_category: Optional[str],
) -> Optional[str]:
    """
    If sub_category is exactly the same as product_name, return a cleaner alias.
    Example: "Construction Work Income 18% GST" -> "Construction Work Income".
    """
    if not product_name or not sub_category:
        return sub_category
    p = str(product_name).strip()
    s = str(sub_category).strip()
    if not p or not s:
        return sub_category
    if p.lower() != s.lower():
        return sub_category

    alias = s
    # Remove trailing GST/IGST rates like "18% GST", "GST@18%", "[GST@18%]".
    alias = re.sub(r"\s*\[\s*(?:i?gst)\s*@?\s*\d+(?:\.\d+)?%\s*\]\s*$", "", alias, flags=re.I)
    alias = re.sub(r"\s+(?:i?gst)\s*@?\s*\d+(?:\.\d+)?%\s*$", "", alias, flags=re.I)
    alias = re.sub(r"\s+\d+(?:\.\d+)?%\s*(?:i?gst)\s*$", "", alias, flags=re.I)
    alias = re.sub(r"\s+", " ", alias).strip(" -")
    return alias or sub_category


def _is_taxonomy_pair_valid(industry: Optional[str], category: Optional[str], sub_category: Optional[str]) -> bool:
    cats = get_categories_for_industry(industry)
    if not cats:
        return True
    if not category or not str(category).strip():
        return False
    cat_key = None
    for k in cats:
        if k.lower() == str(category).strip().lower():
            cat_key = k
            break
    if not cat_key:
        return False
    if not sub_category or not str(sub_category).strip():
        return False
    return any(s.lower() == str(sub_category).strip().lower() for s in cats.get(cat_key, []))


def build_feature_text(invoice_row: dict[str, Any]) -> str:
    """
    Build a single text blob from extracted invoice fields for River.

    We intentionally use structured extracted fields (product_name + line item text)
    rather than raw OCR strings.
    """

    parts: list[str] = []

    def _add(v: Any) -> None:
        if v is None:
            return
        if isinstance(v, str):
            s = v.strip()
            if s:
                parts.append(s)
        else:
            parts.append(str(v))

    # Top-level fields
    _add(invoice_row.get("industry"))
    _add(invoice_row.get("product_name"))
    _add(invoice_row.get("buyer_party_name"))
    _add(invoice_row.get("seller_party_name"))
    _add(invoice_row.get("client_name"))

    # additional_detail is stored in DB as `additional_detail`, while extraction returns `additional_details`.
    ad = invoice_row.get("additional_detail") or invoice_row.get("additional_details")
    if isinstance(ad, str) and ad.strip():
        try:
            ad = json.loads(ad)
        except (json.JSONDecodeError, ValueError):
            ad = None

    if isinstance(ad, dict):
        line_items = ad.get("line_items") or ad.get("lineItems") or []
        if isinstance(line_items, list):
            for item in line_items:
                if not isinstance(item, dict):
                    continue
                _add(item.get("product_name"))
                _add(item.get("description"))
                _add(item.get("item_name"))
                _add(item.get("particulars"))
                _add(item.get("name"))

    # Hard truncate to keep text vectorization bounded.
    text = " ".join(parts)
    max_len = int(os.getenv("RIVER_MAX_TEXT_LEN", "8000"))
    text = text[:max_len]
    return text


def choose_labels_prefer_model(
    llm_category: Optional[str],
    llm_sub_category: Optional[str],
    model_category: Optional[str],
    model_sub_category: Optional[str],
    model_confidence: float,
    min_confidence: float,
) -> tuple[Optional[str], Optional[str]]:
    """
    Merge logic for category and sub_category.
    - If model is highly confident, it overrides LLM extraction.
    - If LLM is missing a field, fallback to model prediction.
    """
    cat = llm_category
    sub = llm_sub_category

    if model_confidence >= min_confidence:
        if model_category:
            cat = model_category
        if model_sub_category:
            sub = model_sub_category

    if not cat or not cat.strip():
        cat = model_category
    if not sub or not sub.strip():
        sub = model_sub_category

    return (cat, sub)


def _new_text_classifier() -> Any:
    """
    Text + multinomial logistic regression classifier.
    """
    return make_pipeline(
        TfidfVectorizer(lowercase=True, ngram_range=(1, 2)),
        LogisticRegression(
            max_iter=2000,
            solver="lbfgs",
        ),
    )


def _predict_top_label(model: Any, text: str) -> tuple[Optional[str], float]:
    """
    Predict top label and confidence from either sklearn-style or River-style model.
    """
    if hasattr(model, "predict_proba_one"):
        proba = model.predict_proba_one(text) or {}
        if not proba:
            return (None, 0.0)
        label = max(proba.items(), key=lambda kv: kv[1])[0]
        conf = float(max(proba.values()))
        return (str(label), conf)

    if hasattr(model, "predict_proba") and hasattr(model, "classes_"):
        probs = model.predict_proba([text])[0]
        classes = list(model.classes_)
        if len(classes) == 0:
            return (None, 0.0)
        best_idx = max(range(len(classes)), key=lambda i: probs[i])
        return (str(classes[best_idx]), float(probs[best_idx]))

    return (None, 0.0)


@dataclass
class PredictionResult:
    category: Optional[str]
    sub_category: Optional[str]
    confidence: float


class CategoryRiverService:
    def __init__(self, model_dir: str | Path | None = None):
        self.model_dir = Path(model_dir or os.getenv("RIVER_MODEL_DIR", "models/river"))
        self.artifact_path = self.model_dir / "logistic_models.pkl"

        self._lock = threading.RLock()
        self._loaded = False
        self._category_models_by_industry: dict[str, Any] = {}
        self._subcategory_models_by_ind_cat: dict[str, Any] = {}
        self._most_category_by_industry: dict[str, str] = {}
        self._most_sub_by_ind_cat: dict[str, str] = {}
        self._most_sub_by_category: dict[str, str] = {}

    @property
    def has_artifacts(self) -> bool:
        return self.artifact_path.exists()

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            if self.artifact_path.exists():
                with open(self.artifact_path, "rb") as f:
                    payload = pickle.load(f)
                # Migration guard: old artifact formats fallback to no-op.
                self._category_models_by_industry = payload.get("category_models_by_industry", {}) or {}
                self._subcategory_models_by_ind_cat = payload.get("subcategory_models_by_ind_cat", {}) or {}
                self._most_category_by_industry = payload.get("most_category_by_industry", {}) or {}
                self._most_sub_by_ind_cat = payload.get("most_sub_by_ind_cat", {}) or {}
                self._most_sub_by_category = payload.get("most_sub_by_category", {}) or {}
            self._loaded = True

    def _save_artifacts(self) -> None:
        self.model_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "category_models_by_industry": self._category_models_by_industry,
            "subcategory_models_by_ind_cat": self._subcategory_models_by_ind_cat,
            "most_category_by_industry": self._most_category_by_industry,
            "most_sub_by_ind_cat": self._most_sub_by_ind_cat,
            "most_sub_by_category": self._most_sub_by_category,
        }
        tmp_path = self.artifact_path.with_suffix(".pkl.tmp")
        with open(tmp_path, "wb") as f:
            pickle.dump(payload, f)
        os.replace(tmp_path, self.artifact_path)

    def predict_category_subcategory(self, invoice_row: dict[str, Any]) -> PredictionResult:
        self._ensure_loaded()

        industry = (invoice_row.get("industry") or "").strip()
        if not industry:
            return PredictionResult(category=None, sub_category=None, confidence=0.0)

        text = build_feature_text(invoice_row)
        if not text.strip():
            return PredictionResult(category=None, sub_category=None, confidence=0.0)

        category_model = self._category_models_by_industry.get(industry)
        if category_model is None:
            cat = self._most_category_by_industry.get(industry)
            cat_conf = 0.51 if cat else 0.0
        else:
            cat, cat_conf = _predict_top_label(category_model, text)
        if not cat:
            return PredictionResult(category=None, sub_category=None, confidence=0.0)

        key = f"{industry}||{cat}"
        sub = None
        sub_conf = 0.0
        sub_model = self._subcategory_models_by_ind_cat.get(key)
        if sub_model is not None:
            sub, sub_conf = _predict_top_label(sub_model, text)

        if not sub:
            sub = self._most_sub_by_ind_cat.get(key) or self._most_sub_by_category.get(cat)

        conf = min(cat_conf, sub_conf) if sub_conf > 0 else cat_conf
        return PredictionResult(category=cat, sub_category=sub, confidence=conf)

    def learn_from_row(
        self,
        invoice_row: dict[str, Any],
        category: Optional[str],
        sub_category: Optional[str],
    ) -> None:
        """
        No-op for sklearn LogisticRegression.

        LogisticRegression is batch-trained. Keep this method to preserve existing
        call sites in PATCH flow without runtime errors.
        """
        return

    def fill_labels_on_extracted_invoice(
        self,
        extracted: dict[str, Any],
        *,
        prefer_river: bool = True,
    ) -> None:
        """
        Mutates `extracted` in-place.

        - If LLM labels are missing, fill with sklearn model predictions when artifacts exist.
        - Else if model confidence exceeds threshold, override.
        - If category/sub_category are still empty, fill from INDUSTRY_CATEGORY_TAXONOMY heuristics
          (transaction_type + keyword overlap with product text).
        """
        apply_government_industry_override(extracted)

        llm_category = extracted.get("category")
        llm_sub = extracted.get("sub_category")

        min_conf = float(os.getenv("RIVER_OVERRIDE_MIN_CONFIDENCE", "0.6"))
        model_pred = PredictionResult(category=None, sub_category=None, confidence=0.0)
        if self.has_artifacts:
            model_pred = self.predict_category_subcategory(extracted)

        if model_pred.category or model_pred.sub_category:
            chosen_category, chosen_sub = choose_labels_prefer_model(
                llm_category=llm_category,
                llm_sub_category=llm_sub,
                model_category=model_pred.category,
                model_sub_category=model_pred.sub_category,
                model_confidence=model_pred.confidence,
                min_confidence=min_conf,
            )
        else:
            chosen_category, chosen_sub = llm_category, llm_sub

        extra = build_feature_text(extracted)
        need_cat = not (chosen_category and str(chosen_category).strip())
        need_sub = not (chosen_sub and str(chosen_sub).strip())
        if need_cat or need_sub:
            t_cat, t_sub = suggest_taxonomy_labels(
                extracted.get("industry"),
                extracted.get("transaction_type"),
                product_name=extracted.get("product_name"),
                extra_text=extra,
                existing_category=chosen_category if not need_cat else None,
            )
            if need_cat and t_cat:
                chosen_category = t_cat
            if need_sub and t_sub:
                chosen_sub = t_sub

        # Strict taxonomy clamp: if chosen labels are outside configured taxonomy for
        # that industry (e.g. stale model predicts legacy labels), replace with taxonomy suggestion.
        if not _is_taxonomy_pair_valid(extracted.get("industry"), chosen_category, chosen_sub):
            t_cat, t_sub = suggest_taxonomy_labels(
                extracted.get("industry"),
                extracted.get("transaction_type"),
                product_name=extracted.get("product_name"),
                extra_text=extra,
                existing_category=None,
            )
            if t_cat:
                chosen_category = t_cat
            if t_sub:
                chosen_sub = t_sub

        if chosen_category is not None:
            extracted["category"] = chosen_category
        if chosen_sub is not None:
            extracted["sub_category"] = _alias_subcategory_when_same_as_product(
                extracted.get("product_name"),
                chosen_sub,
            )

        if prefer_river:
            # Keep behavior explicit: do not change other fields.
            return


_SERVICE: CategoryRiverService | None = None
_SERVICE_LOCK = threading.RLock()


def get_category_river_service() -> CategoryRiverService:
    """
    Thread-safe singleton for production inference.
    """
    global _SERVICE
    with _SERVICE_LOCK:
        if _SERVICE is None:
            _SERVICE = CategoryRiverService()
        return _SERVICE

