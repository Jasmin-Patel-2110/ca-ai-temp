"""
classifier_service.py
─────────────────────
Incremental ML classifier for invoice category and sub-category prediction.

Uses River's TFIDF + ARFClassifier pipeline for online / incremental learning.

Public API:
    load()          → Load models from disk (or pre-train on CSV on first boot)
    predict(data)   → {"category": str|None, "sub_category": str|None}
    train_one(data) → Incrementally train on one verified invoice + persist
    reset()         → Wipe pickles, re-train from CSV + verified DB, return total count
"""
from __future__ import annotations

import csv
import json
import logging
import pickle
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────────────────
_PROJECT_ROOT   = Path(__file__).resolve().parent.parent.parent
_MODEL_DIR      = _PROJECT_ROOT / "ml_models"
_CAT_MODEL_PATH = _MODEL_DIR / "category_model.pkl"
_SUB_MODEL_PATH = _MODEL_DIR / "sub_category_model.pkl"
_CSV_PATH       = _PROJECT_ROOT / "training_data/invoice_classifier_training_data.csv"
_MAPPING_PATH   = _PROJECT_ROOT / "Industry, Catagory and Sub-Catagory 1.json"

# ── Module-level state ─────────────────────────────────────────────────────────
_lock             = threading.Lock()
_category_model: Any = None
_sub_category_model: Any = None
_industry_mapping = None
_initialized      = False


# ── Industry mapping (hierarchy validation) ────────────────────────────────────

def _get_industry_mapping() -> dict:
    """Load the JSON mapping once and cache it as a fast O(1) lookup dict."""
    global _industry_mapping
    if _industry_mapping is not None:
        return _industry_mapping
    try:
        with open(_MAPPING_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Normalize industry names to match the Industry enum values used at runtime.
        # The JSON uses "Government" but the enum/CSV uses "Gov".
        _INDUSTRY_NAME_ALIASES = {
            "government": "Gov",
        }

        _industry_mapping = {}
        for block in data:
            if not block.get("industry"):
                continue
            ind_key = block["industry"]
            # Normalise: if the JSON key has an alias, use the canonical enum value
            canonical = _INDUSTRY_NAME_ALIASES.get(ind_key.lower(), ind_key)
            _industry_mapping[canonical] = {
                cat: set(subcats)
                for cat, subcats in (block.get("category") or {}).items()
            }
    except Exception as e:
        print(f"⚠️  [ML] Failed to load mapping JSON: {e}")
        logger.warning(f"⚠️  [ML] Failed to load mapping JSON: {e}")
        _industry_mapping = {}
    return _industry_mapping


# ── River model factory ────────────────────────────────────────────────────────

def _stringify_keys(x: dict) -> dict:
    """Convert ngram tuple keys from TF-IDF to strings (required by ARFClassifier)."""
    return {" ".join(k) if isinstance(k, tuple) else str(k): v for k, v in x.items()}


def _make_fresh_models():
    """Return two untrained River pipelines: (category_model, sub_category_model)."""
    from river.compose import FuncTransformer
    from river.drift import ADWIN
    from river.feature_extraction import TFIDF
    from river.forest import ARFClassifier

    cat_model = (
        TFIDF(ngram_range=(1, 2), lowercase=True)
        | FuncTransformer(_stringify_keys)
        | ARFClassifier(
            n_models=15, max_features="sqrt", lambda_value=6,
            drift_detector=ADWIN(delta=0.002), warning_detector=ADWIN(delta=0.02),
            disable_weighted_vote=False, seed=42,
        )
    )
    sub_model = (
        TFIDF(ngram_range=(1, 3), lowercase=True)
        | FuncTransformer(_stringify_keys)
        | ARFClassifier(
            n_models=25, max_features="log2", lambda_value=3,
            drift_detector=ADWIN(delta=0.001), warning_detector=ADWIN(delta=0.01),
            disable_weighted_vote=False, seed=42,
        )
    )
    return cat_model, sub_model


# ── Feature engineering ────────────────────────────────────────────────────────

def _normalize_row(data: dict) -> dict:
    """
    Map any data source (CSV row or DB invoice row) into a single standard dict.

    Field differences handled:
      CSV source     → seller_name, hsn_sac_code (top-level), tax_rate (pre-computed "5%")
      DB/live source → seller_party_name, gst+amount, additional_detail (nested)
    """
    tx_type = (data.get("transaction_type") or "").strip()

    # Seller resolution ───────────────────────────────────────────────────────
    # Always use seller identity directly from normalized source fields.
    seller = str(
        data.get("seller_name")
        or data.get("seller_party_name")
        or data.get("supplier_name")
        or ""
    ).strip()
    if seller in ("nan", "None"):
        seller = ""

    # HSN resolution ───────────────────────────────────────────────────────────
    # Check top-level field (CSV) first, then nested additional_detail dict (DB)
    hsn = str(data.get("hsn_sac_code") or "").strip()
    if not hsn:
        ad = data.get("additional_detail") or data.get("additional_details") or {}
        if isinstance(ad, dict):
            for key in ("hsn_sac_code", "hsn_code", "sac_code", "hsn", "sac"):
                val = str(ad.get(key) or "").strip()
                if val and val not in ("nan", "None"):
                    hsn = val
                    break

    # Tax rate resolution ──────────────────────────────────────────────────────
    # Use the pre-computed string from CSV if available, otherwise compute from gst/amount
    tax_rate = str(data.get("tax_rate") or "").strip()
    if not tax_rate or tax_rate in ("nan", "None", "unknown"):
        tax_rate = ""
        try:
            gst    = data.get("gst")
            amount = data.get("amount") or data.get("total")
            if gst is not None and amount and float(amount) > 0:
                rate = (float(gst) / float(amount)) * 100
                for slab in (0, 1.5, 3, 5, 12, 18, 28):
                    if abs(rate - slab) < 1.5:
                        tax_rate = f"{slab}%"
                        break
        except (TypeError, ValueError, ZeroDivisionError):
            pass

    return {
        "transaction_type":  tx_type,
        "product_name":      (data.get("product_name")  or "").strip(),
        "industry":          (data.get("industry")       or "").strip(),
        "payment_mode":      (data.get("payment_mode")   or "").strip(),
        "seller_name":       seller,
        "hsn":               hsn,
        "tax_rate":          tax_rate,
    }


def _build_feature_text(data: dict) -> str:
    """
    Build the TF-IDF feature string from any raw data source.

    Format: "seller_name: value | product: value | industry: value | ..."
    This format is identical to the 'feature_string' column we used to use in the training CSV
    so training (CSV/DB) and prediction (live invoices) always use the same structure.
    """
    norm = _normalize_row(data)
    parts = []

    if v := norm["seller_name"]:
        parts.append(f"seller_name: {v.lower()}")
    if v := norm["product_name"]:
        parts.append(f"product: {v.lower()}")
    if v := norm["industry"]:
        parts.append(f"industry: {v.lower()}")
    if v := norm["transaction_type"]:
        parts.append(f"transaction: {v.lower()}")
    if v := norm["hsn"]:
        parts.append(f"hsn: {v}")
    if v := norm["tax_rate"]:
        parts.append(f"tax_rate: {v}")
    if v := norm["payment_mode"]:
        parts.append(f"payment: {v.lower()}")

    return " | ".join(parts)


def _build_log_context(data: dict, *, include_labels: bool = False) -> dict[str, Any]:
    """Build a small normalized context dict for prediction/training logs."""
    norm = _normalize_row(data)
    context: dict[str, Any] = {
        "id": data.get("id"),
        "transaction_type": norm["transaction_type"],
        "industry": norm["industry"],
        "seller_name": norm["seller_name"],
        "product_name": norm["product_name"],
        "payment_mode": norm["payment_mode"],
        "tax_rate": norm["tax_rate"],
        "hsn": norm["hsn"],
    }
    if include_labels:
        context["category"] = (data.get("category") or "").strip() or None
        context["sub_category"] = (data.get("sub_category") or "").strip() or None
    return context


# ── DB helpers ─────────────────────────────────────────────────────────────────

def _db_execute(sql: str, *, commit: bool = False) -> None:
    """Open a DB connection, execute one SQL statement, optionally commit, then close."""
    from app.database import get_connection
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
        if commit:
            conn.commit()
    finally:
        conn.close()


def _db_ensure_meta_row() -> None:
    """Create the classifier_meta row if it does not yet exist."""
    from app.database import get_connection
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM classifier_meta LIMIT 1")
            if not cur.fetchone():
                cur.execute(
                    "INSERT INTO classifier_meta (trained_samples, reset_count) VALUES (0, 0)"
                )
        conn.commit()
    finally:
        conn.close()


def _db_increment_samples() -> None:
    _db_execute("""
        UPDATE classifier_meta
        SET trained_samples = trained_samples + 1,
            last_trained_at = NOW()
        WHERE id = (SELECT id FROM (SELECT id FROM classifier_meta LIMIT 1) t)
    """, commit=True)


def _db_reset_meta() -> None:
    _db_execute("""
        UPDATE classifier_meta
        SET trained_samples = 0,
            reset_count     = reset_count + 1,
            last_trained_at = NULL
        WHERE id = (SELECT id FROM (SELECT id FROM classifier_meta LIMIT 1) t)
    """, commit=True)


# ── Model persistence ──────────────────────────────────────────────────────────

def _save_models(cat_model, sub_model) -> None:
    _MODEL_DIR.mkdir(parents=True, exist_ok=True)
    with open(_CAT_MODEL_PATH, "wb") as f:
        pickle.dump(cat_model, f)
    with open(_SUB_MODEL_PATH, "wb") as f:
        pickle.dump(sub_model, f)
    print(f"💾 [ML] Models saved to {_MODEL_DIR}")
    logger.info(f"💾 [ML] Models saved to {_MODEL_DIR}")


def _load_models_from_disk():
    """Return (cat_model, sub_model) from disk, or (None, None) if unavailable."""
    if _CAT_MODEL_PATH.exists() and _SUB_MODEL_PATH.exists():
        try:
            with open(_CAT_MODEL_PATH, "rb") as f:
                cat_model = pickle.load(f)
            with open(_SUB_MODEL_PATH, "rb") as f:
                sub_model = pickle.load(f)
            print("📂 [ML] Loaded models from disk.")
            logger.info("📂 [ML] Loaded models from disk.")
            return cat_model, sub_model
        except Exception as e:
            print(f"⚠️  [ML] Failed to load pickles: {e} — retraining.")
            logger.warning(f"⚠️  [ML] Failed to load pickles: {e} — retraining.")
    return None, None


# ── Training helpers ───────────────────────────────────────────────────────────

def _learn_batch(rows, cat_model, sub_model) -> int:
    """
    Train both models on an iterable of dicts (CSV rows or DB rows).
    Each dict must have 'category' and optionally 'sub_category'.
    Returns the count of rows actually learned.
    """
    count = 0
    skipped_no_category = 0
    skipped_no_features = 0
    sub_trained = 0
    sub_skipped = 0

    for row in rows:
        category     = (row.get("category")     or "").strip()
        sub_category = (row.get("sub_category") or "").strip()
        if not category:
            skipped_no_category += 1
            continue

        feature_text = _build_feature_text(row)
        if not feature_text:
            skipped_no_features += 1
            continue

        cat_model.learn_one(feature_text, category)
        if sub_category:
            sub_model.learn_one(feature_text + f" | category: {category.lower()}", sub_category)
            sub_trained += 1
        else:
            sub_skipped += 1

        count += 1

    print(
        f"[classifier][learn_batch] Learned: {count} | Skipped (no category): {skipped_no_category} | "
        f"Skipped (no features): {skipped_no_features} | Sub-category trained: {sub_trained} | Sub-category skipped: {sub_skipped}"
    )
    return count


def _pretrain_from_csv(cat_model, sub_model) -> int:
    """Train from the static CSV file. Returns rows learned."""
    if not _CSV_PATH.exists():
        print(f"⚠️  [ML] Training CSV not found at {_CSV_PATH} — skipping CSV pre-training.")
        logger.warning(f"⚠️  [ML] Training CSV not found at {_CSV_PATH} — skipping CSV pre-training.")
        return 0
    print(f"📂 [ML] Loading training CSV: {_CSV_PATH}")
    logger.info(f"📂 [ML] Loading training CSV: {_CSV_PATH}")
    with open(_CSV_PATH, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    print(f"📊 [ML] CSV loaded — {len(rows)} rows. Starting pre-training...")
    logger.info(f"📊 [ML] CSV loaded — {len(rows)} rows. Starting pre-training...")
    count = _learn_batch(rows, cat_model, sub_model)
    print(f"✅ [ML] Pre-trained on {count} CSV rows.")
    logger.info(f"✅ [ML] Pre-trained on {count} CSV rows.")
    print(f"✅ [ML] CSV pre-training complete — {count}/{len(rows)} rows learned.")
    logger.info(f"✅ [ML] CSV pre-training complete — {count}/{len(rows)} rows learned.")
    return count


def _pretrain_from_db(cat_model, sub_model) -> int:
    """Train from all verified DB invoices. Returns rows learned."""
    try:
        from app.database import get_connection
        conn = get_connection()
    except Exception as e:
        print(f"⚠️  [ML] DB unavailable for verified-invoice pre-training: {e}")
        logger.warning(f"⚠️  [ML] DB unavailable for verified-invoice pre-training: {e}")
        return 0
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT transaction_type, product_name, industry, payment_mode,
                                             seller_party_name,
                       gst, amount, category, sub_category
                FROM invoices
                WHERE status = 'verified'
                  AND category IS NOT NULL AND category != ''
            """)
            rows = cur.fetchall()
        print(f"📊 [ML] DB verified invoices found: {len(rows)}. Starting pre-training...")
        logger.info(f"📊 [ML] DB verified invoices found: {len(rows)}. Starting pre-training...")
        count = _learn_batch(rows, cat_model, sub_model)
        print(f"✅ [ML] Re-trained on {count} verified DB invoices.")
        logger.info(f"✅ [ML] Re-trained on {count} verified DB invoices.")
        print(f"✅ [ML] DB pre-training complete — {count}/{len(rows)} rows learned.")
        logger.info(f"✅ [ML] DB pre-training complete — {count}/{len(rows)} rows learned.")
        return count
    except Exception as e:
        print(f"⚠️  [ML] DB pre-training failed: {e}")
        logger.warning(f"⚠️  [ML] DB pre-training failed: {e}")
        return 0
    finally:
        conn.close()


# ── Public API ─────────────────────────────────────────────────────────────────

def load() -> None:
    """
    Load models from disk if available; otherwise pre-train on CSV.
    Called once at server startup. Thread-safe.
    """
    global _category_model, _sub_category_model, _initialized

    with _lock:
        if _initialized:
            return

        print("🤖 [ML] Initializing classifier...")
        logger.info("🤖 [ML] Initializing classifier...")
        try:
            _db_ensure_meta_row()
        except Exception as e:
            print(f"⚠️  [ML] DB meta init failed (non-fatal): {e}")
            logger.warning(f"⚠️  [ML] DB meta init failed (non-fatal): {e}")

        cat_model, sub_model = _load_models_from_disk()

        if cat_model is None:
            print("⚙️  [ML] No saved models found — starting fresh pre-training from CSV...")
            logger.info("⚙️  [ML] No saved models found — starting fresh pre-training from CSV...")
            cat_model, sub_model = _make_fresh_models()
            try:
                _pretrain_from_csv(cat_model, sub_model)
                _save_models(cat_model, sub_model)
                print(f"💾 [ML] Models saved to {_MODEL_DIR}")
                logger.info(f"💾 [ML] Models saved to {_MODEL_DIR}")
            except Exception as e:
                print(f"❌ [ML] CSV pre-training failed: {e}")
                logger.error(f"❌ [ML] CSV pre-training failed: {e}")
        else:
            print(f"💾 [ML] Loaded existing models from {_MODEL_DIR}")
            logger.info(f"💾 [ML] Loaded existing models from {_MODEL_DIR}")

        _category_model = cat_model
        _sub_category_model = sub_model
        _initialized = True
        print("✅ [ML] Classifier ready.")
        logger.info("✅ [ML] Classifier ready.")


def predict(invoice_data: dict) -> dict:
    """
    Predict category and sub_category for an invoice dict.
    Validates predictions against the industry→category→sub_category hierarchy.
    Returns {"category": str|None, "sub_category": str|None}.
    Safe to call when model is not initialized (returns nulls).
    """
    result: dict[str, str | None] = {"category": None, "sub_category": None}
    try:
        context = _build_log_context(invoice_data)
        # print(f"[classifier][predict] Input context: {context}") # Optional: keep very noisy ones commented out if you prefer, but the user asked for logs.
        print(f"[classifier][predict] Input context: {context}")
        logger.info(f"[classifier][predict] Input context: {context}")

        with _lock:
            if _category_model is None or _sub_category_model is None:
                print(f"⚠️  [ML] Predict called but model not initialized. id={context.get('id')}")
                logger.warning(f"⚠️  [ML] Predict called but model not initialized. id={context.get('id')}")
                return result

            feature_text = _build_feature_text(invoice_data)
            if not feature_text:
                print(f"⚠️  [ML] Predict skipped — no usable feature fields for invoice id={context.get('id')}")
                logger.warning(f"⚠️  [ML] Predict skipped — no usable feature fields for invoice id={context.get('id')}")
                return result
            print(f"[classifier][predict] Feature text id={context.get('id')}: {feature_text}")
            logger.info(f"[classifier][predict] Feature text id={context.get('id')}: {feature_text}")

            category = _category_model.predict_one(feature_text)
            print(f"[classifier][predict] Category candidate id={context.get('id')}: {category!r}")
            logger.info(f"[classifier][predict] Category candidate id={context.get('id')}: {category!r}")
            if not category:
                print(f"⚠️  [ML] Category prediction returned None (model untrained?) for id={context.get('id')}")
                logger.warning(f"⚠️  [ML] Category prediction returned None (model untrained?) for id={context.get('id')}")
                return result

            # Validate category against the industry mapping
            industry = (invoice_data.get("industry") or "").strip()
            mapping  = _get_industry_mapping()
            ind_map  = mapping.get(industry) if industry and mapping else None

            if not ind_map and industry:
                print(f"[classifier][predict] No mapping found for industry={industry!r} — skipping hierarchy validation. id={context.get('id')}")
                logger.info(f"[classifier][predict] No mapping found for industry={industry!r} — skipping hierarchy validation. id={context.get('id')}")

            if ind_map and str(category) not in ind_map:
                # Case-insensitive check
                matched_cat = next((k for k in ind_map if k.lower() == str(category).lower()), None)
                if not matched_cat:
                    print(f"🚫 [ML] Category {category!r} rejected (not valid for industry={industry!r}) id={context.get('id')}")
                    logger.warning(f"🚫 [ML] Category {category!r} rejected (not valid for industry={industry!r}) id={context.get('id')}")
                    return result

            result["category"] = str(category)

            # Predict sub_category (append category context to feature string)
            sub_feature  = feature_text + f" | category: {str(category).lower()}"
            print(f"[classifier][predict] Sub feature text id={context.get('id')}: {sub_feature}")
            logger.info(f"[classifier][predict] Sub feature text id={context.get('id')}: {sub_feature}")
            sub_category = _sub_category_model.predict_one(sub_feature)
            print(f"[classifier][predict] Sub-category candidate id={context.get('id')}: {sub_category!r}")
            logger.info(f"[classifier][predict] Sub-category candidate id={context.get('id')}: {sub_category!r}")

            if sub_category and ind_map:
                # Case-insensitive category key lookup to tolerate minor model casing differences
                allowed: set = set()
                for map_cat, map_subs in ind_map.items():
                    if map_cat.lower() == str(category).lower():
                        allowed = map_subs
                        break
                if str(sub_category) in allowed:
                    result["sub_category"] = str(sub_category)
                else:
                    # Fallback: case-insensitive sub_category match
                    sub_lower = str(sub_category).lower()
                    matched = None
                    for allowed_sub in allowed:
                        if allowed_sub.lower() == sub_lower:
                            matched = allowed_sub
                            break
                    if matched:
                        result["sub_category"] = matched
                        print(f"[classifier][predict] Sub-category matched via case-insensitive fallback: {sub_category!r} → {matched!r} id={context.get('id')}")
                        logger.info(f"[classifier][predict] Sub-category matched via case-insensitive fallback: {sub_category!r} → {matched!r} id={context.get('id')}")
                    else:
                        print(f"🚫 [ML] Sub-category {sub_category!r} rejected (not allowed for {category!r}/{industry!r}) id={context.get('id')}")
                        logger.warning(f"🚫 [ML] Sub-category {sub_category!r} rejected (not allowed for {category!r}/{industry!r}) id={context.get('id')}")
            elif sub_category and not ind_map:
                # No mapping to validate against — trust the model
                result["sub_category"] = str(sub_category)

            print(
                f"✅ [ML] Final prediction id={context.get('id')}: category={result['category']!r} sub_category={result['sub_category']!r}"
            )
            print(
                f"🎯 [ML] Prediction id={context.get('id')} | "
                f"industry='{industry}' | category='{result['category']}' | sub_category='{result['sub_category']}'"
            )

    except Exception as e:
        print(f"❌ [ML] Prediction error (non-fatal): {e}")
        logger.error(f"❌ [ML] Prediction error (non-fatal): {e}")

    return result


def train_one(invoice_data: dict) -> None:
    """
    Incrementally train on one verified invoice, save models, and update DB counter.
    Called in a background thread from PATCH /invoices/{id}.
    """
    global _category_model, _sub_category_model

    category     = (invoice_data.get("category")     or "").strip()
    sub_category = (invoice_data.get("sub_category") or "").strip()
    context = _build_log_context(invoice_data, include_labels=True)
    # print(f"[classifier][train_one] Input context: {context}") # Optional noise
    print(f"[classifier][train_one] Input context: {context}")
    logger.info(f"[classifier][train_one] Input context: {context}")

    if not category:
        print(f"⚠️  [ML] train_one skipped — invoice id={context.get('id')} has no category.")
        logger.warning(f"⚠️  [ML] train_one skipped — invoice id={context.get('id')} has no category.")
        return

    try:
        feature_text = _build_feature_text(invoice_data)
        if not feature_text:
            print(f"⚠️  [ML] train_one skipped — no usable feature fields for id={context.get('id')}")
            logger.warning(f"⚠️  [ML] train_one skipped — no usable feature fields for id={context.get('id')}")
            return
        print(f"[classifier][train_one] Feature text id={context.get('id')}: \"{feature_text}\"")
        logger.info(f"[classifier][train_one] Feature text id={context.get('id')}: \"{feature_text}\"")

        with _lock:
            if _category_model is None or _sub_category_model is None:
                print(f"⚠️  [ML] train_one skipped — model not initialized for id={context.get('id')}")
                logger.warning(f"⚠️  [ML] train_one skipped — model not initialized for id={context.get('id')}")
                return
            _category_model.learn_one(feature_text, category)
            print(f"[classifier][train_one] Category model updated: id={context.get('id')} category={category!r}")
            logger.info(f"[classifier][train_one] Category model updated: id={context.get('id')} category={category!r}")

            if sub_category:
                _sub_category_model.learn_one(
                    feature_text + f" | category: {category.lower()}", sub_category
                )
                print(f"[classifier][train_one] Sub-category model updated: id={context.get('id')} sub_category={sub_category!r}")
                logger.info(f"[classifier][train_one] Sub-category model updated: id={context.get('id')} sub_category={sub_category!r}")
            else:
                print(f"[classifier][train_one] Sub-category skipped — no label. id={context.get('id')}")
                logger.info(f"[classifier][train_one] Sub-category skipped — no label. id={context.get('id')}")

            _save_models(_category_model, _sub_category_model)
            print(f"[classifier][train_one] Models persisted to disk for id={context.get('id')}.")
            logger.info(f"[classifier][train_one] Models persisted to disk for id={context.get('id')}.")

        _db_increment_samples()
        print(f"✅ [ML] train_one Done id={context.get('id')} category={category!r} sub_category={sub_category!r}")
        logger.info(f"✅ [ML] train_one Done id={context.get('id')} category={category!r} sub_category={sub_category!r}")
        print(f"✅ [ML] Trained on Invoice {invoice_data.get('id')} "
              f"[Cat: {category} | Sub: {sub_category or '(none)'}]")

    except Exception as e:
        print(f"❌ [ML] train_one failed for id={invoice_data.get('id')}: {e}")
        logger.error(f"❌ [ML] train_one failed for id={invoice_data.get('id')}: {e}")


def reset() -> int:
    """
    Wipe saved models and fully retrain from CSV + all verified DB invoices.
    Returns total rows learned. Blocks until complete.
    """
    global _category_model, _sub_category_model, _initialized

    with _lock:
        for path in (_CAT_MODEL_PATH, _SUB_MODEL_PATH):
            path.unlink(missing_ok=True)

        cat_model, sub_model = _make_fresh_models()
        csv_count = db_count = 0

        try:
            csv_count = _pretrain_from_csv(cat_model, sub_model)
        except Exception as e:
            print(f"❌ [ML] CSV pre-training failed: {e}")
            logger.error(f"❌ [ML] CSV pre-training failed: {e}")

        try:
            db_count = _pretrain_from_db(cat_model, sub_model)
        except Exception as e:
            print(f"❌ [ML] DB pre-training failed: {e}")
            logger.error(f"❌ [ML] DB pre-training failed: {e}")

        try:
            _save_models(cat_model, sub_model)
        except Exception as e:
            print(f"❌ [ML] Failed to save models: {e}")
            logger.error(f"❌ [ML] Failed to save models: {e}")

        _category_model     = cat_model
        _sub_category_model = sub_model
        _initialized        = True

    try:
        _db_reset_meta()
    except Exception as e:
        print(f"⚠️  [ML] DB reset meta failed (non-fatal): {e}")
        logger.warning(f"⚠️  [ML] DB reset meta failed (non-fatal): {e}")

    total = csv_count + db_count
    print(f"✅ [ML] Reset complete — CSV: {csv_count} | DB: {db_count} | Total: {total}")
    logger.info(f"✅ [ML] Reset complete — CSV: {csv_count} | DB: {db_count} | Total: {total}")
    print(f"🔁 [ML Reset] CSV: {csv_count} | DB verified: {db_count} | Total: {total}")
    logger.info(f"🔁 [ML Reset] CSV: {csv_count} | DB verified: {db_count} | Total: {total}")
    return total
