import json
import logging
import re
from app.database import get_connection
import app.models.document as document_model
from app.services.s3_service import delete_from_s3


class SplitInvoiceGroupError(Exception):
    """Kept for import compatibility — no longer raised by delete_invoice."""
    pass


def _parse_date(value) -> str | None:
    """
    Convert any recognisable date string to MySQL-compatible 'YYYY-MM-DD'.

    Handles formats like:
      25.01.2023  → 2023-01-25   (DD.MM.YYYY)
      25/01/2023  → 2023-01-25   (DD/MM/YYYY)
      01-25-2023  → 2023-01-25   (MM-DD-YYYY)
      2023-01-25  → 2023-01-25   (already correct)
      25 Jan 2023 → 2023-01-25
      Jan 25 2023 → 2023-01-25
      25-Aug-25   → 2025-08-25   (DD-Mon-YY, 2-digit year)
      25.08.25    → 2025-08-25   (DD.MM.YY)
      Aug 25, 25  → 2025-08-25   (Mon DD, YY)
    """
    if not value:
        return None
    s = str(value).strip()
    if not s or s.lower() in ("null", "none", "n/a", "-"):
        return None

    if re.match(r"^\d{4}-\d{2}-\d{2}", s):
        return s[:10]

    _MONTHS = {
        "jan": "01", "feb": "02", "mar": "03", "apr": "04",
        "may": "05", "jun": "06", "jul": "07", "aug": "08",
        "sep": "09", "oct": "10", "nov": "11", "dec": "12",
    }

    m = re.match(r"(\d{1,2})[\s\-/]([A-Za-z]{3,9})[\s\-/](\d{4})", s)
    if m:
        mon = _MONTHS.get(m.group(2).lower()[:3])
        if mon:
            return f"{m.group(3)}-{mon}-{int(m.group(1)):02d}"

    m = re.match(r"([A-Za-z]{3,9})[\s\-/,](\d{1,2})[,\s]+(\d{4})", s)
    if m:
        mon = _MONTHS.get(m.group(1).lower()[:3])
        if mon:
            return f"{m.group(3)}-{mon}-{int(m.group(2)):02d}"

    m = re.match(r"(\d{1,2})[\s\-/]([A-Za-z]{3,9})[\s\-/](\d{2})\b", s)
    if m:
        mon = _MONTHS.get(m.group(2).lower()[:3])
        if mon:
            yy = int(m.group(3))
            yyyy = 2000 + yy if yy < 30 else 1900 + yy
            return f"{yyyy}-{mon}-{int(m.group(1)):02d}"

    m = re.match(r"([A-Za-z]{3,9})[\s\-/,]+(\d{1,2})[\s,]+(\d{2})\b", s)
    if m:
        mon = _MONTHS.get(m.group(1).lower()[:3])
        if mon:
            yy = int(m.group(3))
            yyyy = 2000 + yy if yy < 30 else 1900 + yy
            return f"{yyyy}-{mon}-{int(m.group(2)):02d}"

    parts = re.split(r"[.\-/]", s)
    if len(parts) == 3:
        a, b, c = parts
        if len(c) == 4:
            return f"{c}-{int(b):02d}-{int(a):02d}"
        if len(a) == 4:
            return f"{a}-{int(b):02d}-{int(c):02d}"
        if len(c) == 2 and a.isdigit() and b.isdigit() and c.isdigit():
            yy = int(c)
            yyyy = 2000 + yy if yy < 30 else 1900 + yy
            return f"{yyyy}-{int(b):02d}-{int(a):02d}"
        if len(a) == 2 and a.isdigit() and b.isdigit() and c.isdigit():
            yy = int(a)
            yyyy = 2000 + yy if yy < 30 else 1900 + yy
            return f"{yyyy}-{int(b):02d}-{int(c):02d}"

    return None


_INVOICE_COLS = (
    "id, user_id, doc_id, invoice_number, client_name, product_name, industry, "
    "category, sub_category, "
    "transaction_type, status, invoice_date, "
    "buyer_party_name, seller_party_name, "
    "buyer_contact_number, seller_contact_number, "
    "buyer_pan_number, seller_pan_number, "
    "buyer_gst_number, seller_gst_number, "
    "buyer_location, seller_location, "
    "gst, cgst, sgst, igst, total, quantity, rate, "
    "amount, amount_paid, balance_amount, payment_mode, "
    "additional_detail, is_line_item_split, created_datetime, updated_datetime"
)


def _get_nested(d: dict, *keys) -> any:
    for k in keys:
        v = d.get(k)
        if v is not None:
            return v
    return None


def _safe_float(val) -> float | None:
    if val is None or val in ("", "None", "nan"):
        return None
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        s = val.replace(",", "").replace("₹", "").replace("$", "").replace(" ", "").strip()
        if not s:
            return None
        try:
            return float(s)
        except ValueError:
            return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _parse_row(row: dict | None) -> dict | None:
    if row is None:
        return None
    raw = row.get("additional_detail")
    if isinstance(raw, str) and raw.strip():
        try:
            row["additional_detail"] = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            row["additional_detail"] = None

    for field in ("gst", "cgst", "sgst", "igst", "total", "quantity", "rate", "amount", "amount_paid", "balance_amount"):
        if field in row:
            val = row[field]
            if val in ("", "None", "null") or val is None:
                row[field] = None
            elif isinstance(val, str):
                try:
                    row[field] = float(val.replace(",", ""))
                except ValueError:
                    row[field] = None

    ad = row.get("additional_detail")
    if isinstance(ad, dict):
        gd = _get_nested(ad, "gst_details", "gstDetails") or {}
        if isinstance(gd, dict):
            if row.get("cgst") is None:
                row["cgst"] = _safe_float(gd.get("cgst_amount") or gd.get("cgstAmount"))
            if row.get("sgst") is None:
                row["sgst"] = _safe_float(gd.get("sgst_amount") or gd.get("sgstAmount"))
            if row.get("igst") is None:
                row["igst"] = _safe_float(gd.get("igst_amount") or gd.get("igstAmount"))
            if row.get("gst") is None:
                row["gst"] = _safe_float(gd.get("total_gst") or gd.get("totalGst"))
                if row.get("gst") is None and (row.get("cgst") or row.get("sgst")):
                    row["gst"] = (row.get("cgst") or 0.0) + (row.get("sgst") or 0.0)

        for keys, col in [
            (("total", "grand_total", "grandTotal", "invoice_total", "invoiceTotal", "net_payable", "netPayable"), "total"),
            (("amount", "taxable_amount", "taxableAmount", "subtotal", "base_amount", "baseAmount"), "amount"),
            (("amount_paid", "amountPaid", "paid_amount", "paidAmount"), "amount_paid"),
            (("balance_due", "balanceDue", "balance_amount", "balanceAmount"), "balance_amount"),
        ]:
            if row.get(col) is None:
                for k in keys:
                    v = ad.get(k)
                    if v is not None:
                        row[col] = _safe_float(v)
                        break

        li = _get_nested(ad, "line_items", "lineItems")
        if isinstance(li, list) and li and isinstance(li[0], dict):
            f = li[0]
            if row.get("quantity") is None:
                row["quantity"] = _safe_float(f.get("quantity") or f.get("qty"))
            if row.get("rate") is None:
                row["rate"] = _safe_float(f.get("rate") or f.get("unit_price") or f.get("unitPrice"))
            if row.get("amount") is None:
                row["amount"] = _safe_float(f.get("amount") or f.get("total") or f.get("taxable_value") or f.get("taxableValue"))

    if "industry" in row:
        from app.schemas.invoice import _coerce_industry
        row["industry"] = _coerce_industry(row.get("industry"))

    db_inv = row.get("invoice_number")
    if db_inv and isinstance(db_inv, str) and db_inv.strip() not in ("null", "None", ""):
        row["invoice_number"] = db_inv.strip()
    else:
        extracted_inv = None
        if isinstance(ad, dict):
            extracted_inv = ad.get("invoice_number") or ad.get("invoiceNumber")
        if extracted_inv and isinstance(extracted_inv, str) and extracted_inv.strip() not in ("null", "None", ""):
            row["invoice_number"] = extracted_inv.strip()
        else:
            row["invoice_number"] = None

    if "id" in row and row["id"] is not None:
        row["invoice_number_fallback"] = f"INV-{row['id']:03d}"
    else:
        row["invoice_number_fallback"] = None

    return row


_INDUSTRY_VALID = frozenset({
    "Textile Manufacturing", "Textile Jobwork", "Supari", "Labour",
    "Jewellers", "IT", "Gov", "Hospital", "Diamond",
})

_TRANSACTION_TYPE_VALID = frozenset({"Sales", "Purchase"})


def _coerce_transaction_type(v) -> str | None:
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    s = str(v).strip()
    if not s:
        return None
    if s in ("Sales", "Purchase"):
        return s
    low = s.lower()
    if low in ("sales", "sale", "sold"):
        return "Sales"
    if low in ("purchase", "purchased", "expense", "expenses", "bought", "cost", "other"):
        return "Purchase"
    return None


def create_invoice(data: dict) -> dict | list[dict]:
    """Insert invoice rows and return the full inserted record(s).

    If `additional_detail.line_items` contains multiple items, this function inserts
    multiple DB rows with the same invoice_number (one row per line item).
    Each split row is marked with is_line_item_split=1.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            additional = data.get("additional_details") or data.get("additional_detail")
            ad_dict = None
            if isinstance(additional, dict):
                ad_dict = additional
            if isinstance(additional, dict):
                additional = json.dumps(additional, default=str)

            if ad_dict is None and isinstance(additional, str):
                try:
                    ad_dict = json.loads(additional)
                except (json.JSONDecodeError, ValueError):
                    ad_dict = None
            if not isinstance(ad_dict, dict):
                ad_dict = {}

            invoice_number_to_store = (
                data.get("invoice_number")
                or ad_dict.get("invoice_number")
                or ad_dict.get("invoiceNumber")
            )

            industry = data.get("industry")
            if industry not in _INDUSTRY_VALID:
                industry = None

            transaction_type = _coerce_transaction_type(data.get("transaction_type"))
            status = data.get("status", "pending_verification")
            if status not in ("pending_extraction", "pending_verification", "verified", "error"):
                status = "pending_verification"

            is_line_item_split = 1 if data.get("is_line_item_split") else 0

            ad_line_items = ad_dict.get("line_items")
            should_split = isinstance(ad_line_items, list) and len(ad_line_items) > 1

            if transaction_type is None:
                known = (data.get("client_name") or "").strip().lower()
                supplier_from_ad = (ad_dict.get("supplier_name") or "").strip().lower()
                buyer_name = (data.get("buyer_party_name") or "").strip().lower()
                seller_name = (data.get("seller_party_name") or "").strip().lower()

                if known and supplier_from_ad and (
                    known == supplier_from_ad or known in supplier_from_ad or supplier_from_ad in known
                ):
                    transaction_type = "Sales"
                elif known and seller_name and (
                    known == seller_name or known in seller_name or seller_name in known
                ):
                    transaction_type = "Sales"
                elif known and buyer_name and (
                    known == buyer_name or known in buyer_name or buyer_name in known
                ):
                    transaction_type = "Purchase"
                else:
                    transaction_type = "Purchase"

            if should_split:
                inserted: list[dict] = []
                for item in ad_line_items:
                    if not isinstance(item, dict):
                        continue

                    item_ad = dict(ad_dict)
                    item_ad["line_items"] = [item]

                    product_name = (
                        item.get("product_name")
                        or item.get("description")
                        or item.get("item_name")
                        or item.get("particulars")
                        or item.get("name")
                        or data.get("product_name")
                    )
                    quantity = item.get("quantity") or item.get("qty")
                    rate = item.get("rate") or item.get("unit_price") or item.get("unitPrice")
                    amount = (
                        item.get("amount")
                        or item.get("total")
                        or item.get("taxable_value")
                        or item.get("taxableValue")
                    )

                    row_data = dict(data)
                    row_data["product_name"] = product_name
                    row_data["quantity"] = quantity
                    row_data["rate"] = rate
                    row_data["amount"] = amount
                    row_data["additional_details"] = item_ad
                    row_data["is_line_item_split"] = 1
                    row_data.pop("additional_detail", None)

                    inserted_row = create_invoice(row_data)
                    if isinstance(inserted_row, dict):
                        inserted.append(inserted_row)

                return inserted

            cur.execute(
                """INSERT INTO invoices
                   (user_id, doc_id, invoice_number, client_name, product_name, industry,
                    category, sub_category,
                    transaction_type, status, invoice_date,
                    buyer_party_name, seller_party_name,
                    buyer_contact_number, seller_contact_number,
                    buyer_pan_number, seller_pan_number,
                    buyer_gst_number, seller_gst_number,
                    buyer_location, seller_location,
                    gst, cgst, sgst, igst, total, quantity, rate,
                    amount, amount_paid, balance_amount, payment_mode,
                    additional_detail, is_line_item_split)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    str(data.get("user_id", "")),
                    str(data.get("doc_id", "")),
                    invoice_number_to_store,
                    data.get("client_name"),
                    data.get("product_name"),
                    industry,
                    data.get("category"),
                    data.get("sub_category"),
                    transaction_type,
                    status,
                    _parse_date(data.get("invoice_date") or data.get("date")),
                    data.get("buyer_party_name"),
                    data.get("seller_party_name"),
                    data.get("buyer_contact_number"),
                    data.get("seller_contact_number"),
                    data.get("buyer_pan_number"),
                    data.get("seller_pan_number"),
                    data.get("buyer_gst_number"),
                    data.get("seller_gst_number"),
                    data.get("buyer_location"),
                    data.get("seller_location"),
                    str(data.get("gst") or ""),
                    str(data.get("cgst") or ""),
                    str(data.get("sgst") or ""),
                    str(data.get("igst") or ""),
                    str(data.get("total") or ""),
                    str(data.get("quantity") or ""),
                    str(data.get("rate") or ""),
                    _safe_float(data.get("amount")),
                    _safe_float(data.get("amount_paid")),
                    _safe_float(data.get("balance_amount")),
                    data.get("payment_mode"),
                    additional,
                    is_line_item_split,
                ),
            )
            conn.commit()
            new_id = cur.lastrowid
            cur.execute(f"SELECT {_INVOICE_COLS} FROM invoices WHERE id = %s", (new_id,))
            return _parse_row(cur.fetchone())
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _format_doc_created_at(val) -> str | None:
    if val is None:
        return None
    if hasattr(val, "isoformat"):
        return val.isoformat().split(".")[0]
    return str(val)


def build_document_response(doc: dict | None, include_preview_url: bool = True) -> dict | None:
    if not doc:
        return None
    preview_url = None
    if include_preview_url and doc.get("s3_key"):
        try:
            from app.services.s3_service import generate_presigned_url
            preview_url = generate_presigned_url(doc["s3_key"], expiry_seconds=1800)
        except Exception:
            pass
    return {
        "id": doc["id"],
        "doc_id": doc["doc_id"],
        "doc_name": doc["doc_name"],
        "preview_url": preview_url,
        "created_at": _format_doc_created_at(doc.get("created_at")),
    }


def _enrich_invoices_with_documents(invoices: list[dict]) -> list[dict]:
    if not invoices:
        return invoices
    doc_ids = [r["doc_id"] for r in invoices if r and r.get("doc_id")]
    docs = document_model.get_documents_by_doc_ids(doc_ids)
    for inv in invoices:
        if inv and inv.get("doc_id"):
            doc = docs.get(inv["doc_id"])
            if doc:
                inv["document"] = build_document_response(doc)
            else:
                inv["document"] = None
    return invoices


def get_invoice_by_id(invoice_id: int) -> dict | None:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT {_INVOICE_COLS} FROM invoices WHERE id = %s LIMIT 1",
                (invoice_id,),
            )
            row = _parse_row(cur.fetchone())
            if row:
                _enrich_invoices_with_documents([row])
            return row
    finally:
        conn.close()


def get_invoices_by_user(user_id: str) -> list[dict]:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT {_INVOICE_COLS} FROM invoices WHERE user_id = %s ORDER BY id DESC",
                (user_id,),
            )
            return [_parse_row(r) for r in cur.fetchall()]
    finally:
        conn.close()


def get_dashboard_stats(user_id: str) -> dict:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    COUNT(*)                                 AS total_invoices,
                    SUM(status = 'pending_verification')     AS total_pending_verification,
                    SUM(DATE(created_datetime) = CURDATE())  AS total_created_today
                FROM invoices
                WHERE user_id = %s
                """,
                (user_id,),
            )
            row = cur.fetchone()
            return {
                "total_invoices":             int(row["total_invoices"] or 0),
                "total_pending_verification": int(row["total_pending_verification"] or 0),
                "total_created_today":        int(row["total_created_today"] or 0),
            }
    finally:
        conn.close()


def get_recent_invoices(user_id: str, limit: int = 5) -> list[dict]:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, client_name, status, total,
                          invoice_date, created_datetime
                   FROM invoices
                   WHERE user_id = %s
                   ORDER BY id DESC
                   LIMIT %s""",
                (user_id, limit),
            )
            return cur.fetchall()
    finally:
        conn.close()


def get_all_invoices() -> list[dict]:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT {_INVOICE_COLS} FROM invoices ORDER BY id DESC")
            return [_parse_row(r) for r in cur.fetchall()]
    finally:
        conn.close()


def search_invoice_by_keyword(user_id: str, keyword: str) -> list[dict]:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            search_id = None
            kw_clean = keyword.strip().upper()
            if kw_clean.startswith("INV-"):
                num_part = kw_clean.replace("INV-", "").lstrip("0") or "0"
                if num_part.isdigit():
                    search_id = int(num_part)
            elif kw_clean.isdigit():
                search_id = int(kw_clean)

            like_term = f"%{keyword.strip()}%"

            if search_id is not None:
                cur.execute(
                    f"SELECT {_INVOICE_COLS} FROM invoices WHERE user_id = %s AND (id = %s OR client_name LIKE %s OR additional_detail LIKE %s) ORDER BY id DESC",
                    (user_id, search_id, like_term, like_term)
                )
            else:
                cur.execute(
                    f"SELECT {_INVOICE_COLS} FROM invoices WHERE user_id = %s AND (client_name LIKE %s OR additional_detail LIKE %s) ORDER BY id DESC",
                    (user_id, like_term, like_term)
                )
            return [_parse_row(r) for r in cur.fetchall()]
    finally:
        conn.close()


def update_invoice(invoice_id: int, fields: dict) -> dict | None:
    """Update only the supplied non-None fields of an invoice row."""
    if "line_items" in fields:
        incoming_items = fields.get("line_items")
        if isinstance(incoming_items, list):
            row = get_invoice_by_id(invoice_id)
            if not row:
                return None

            existing_ad = row.get("additional_detail")
            if not isinstance(existing_ad, dict):
                existing_ad = {}

            items = [it for it in incoming_items if isinstance(it, dict)]

            if len(items) > 1:
                first_item = items[0]
                rest_items = items[1:]

                first_ad = dict(existing_ad)
                first_ad["line_items"] = [first_item]

                product_name = (
                    first_item.get("product_name")
                    or first_item.get("description")
                    or first_item.get("item_name")
                    or first_item.get("particulars")
                    or first_item.get("name")
                    or row.get("product_name")
                )
                quantity = first_item.get("quantity") or first_item.get("qty")
                rate = first_item.get("rate") or first_item.get("unit_price") or first_item.get("unitPrice")
                amount = (
                    first_item.get("amount")
                    or first_item.get("total")
                    or first_item.get("taxable_value")
                    or first_item.get("taxableValue")
                )

                fields.pop("line_items", None)
                fields["additional_detail"] = first_ad
                fields["product_name"] = product_name
                fields["quantity"] = quantity
                fields["rate"] = rate
                fields["amount"] = amount
                fields["is_line_item_split"] = 1

                base = dict(row)
                base.pop("id", None)
                base.pop("additional_detail", None)
                base["is_line_item_split"] = 1

                for it in rest_items:
                    it_ad = dict(existing_ad)
                    it_ad["line_items"] = [it]

                    it_product_name = (
                        it.get("product_name")
                        or it.get("description")
                        or it.get("item_name")
                        or it.get("particulars")
                        or it.get("name")
                        or base.get("product_name")
                    )
                    it_quantity = it.get("quantity") or it.get("qty")
                    it_rate = it.get("rate") or it.get("unit_price") or it.get("unitPrice")
                    it_amount = (
                        it.get("amount")
                        or it.get("total")
                        or it.get("taxable_value")
                        or it.get("taxableValue")
                    )

                    insert_payload = dict(base)
                    insert_payload["product_name"] = it_product_name
                    insert_payload["quantity"] = it_quantity
                    insert_payload["rate"] = it_rate
                    insert_payload["amount"] = it_amount
                    insert_payload["additional_details"] = it_ad
                    insert_payload["additional_detail"] = it_ad

                    create_invoice(insert_payload)

            else:
                ad = existing_ad
                ad["line_items"] = incoming_items
                fields.pop("line_items", None)
                fields["additional_detail"] = ad
        else:
            pass

    _ALLOWED = {
        "invoice_number", "client_name", "industry", "category", "sub_category",
        "transaction_type", "status", "invoice_date",
        "product_name",
        "buyer_party_name", "seller_party_name",
        "buyer_contact_number", "seller_contact_number",
        "buyer_pan_number", "seller_pan_number",
        "buyer_gst_number", "seller_gst_number",
        "buyer_location", "seller_location",
        "gst", "cgst", "sgst", "igst", "total", "quantity", "rate",
        "amount", "amount_paid", "balance_amount", "payment_mode",
        "additional_detail", "is_line_item_split",
    }
    updates = {k: v for k, v in fields.items() if k in _ALLOWED and v is not None}

    if not updates:
        return get_invoice_by_id(invoice_id)

    learn_should_run = (
        ("category" in updates and bool(str(updates.get("category") or "").strip()))
        or ("sub_category" in updates and bool(str(updates.get("sub_category") or "").strip()))
        or (updates.get("status") == "verified")
    )

    if "additional_detail" in updates and isinstance(updates["additional_detail"], dict):
        updates["additional_detail"] = json.dumps(updates["additional_detail"], default=str)

    if "invoice_date" in updates:
        updates["invoice_date"] = _parse_date(updates["invoice_date"])

    if "industry" in updates and updates["industry"] not in _INDUSTRY_VALID:
        updates["industry"] = None

    if "transaction_type" in updates:
        updates["transaction_type"] = _coerce_transaction_type(updates["transaction_type"])

    _STATUS_VALID = frozenset({"pending_extraction", "pending_verification", "verified", "error"})
    if "status" in updates and updates["status"] not in _STATUS_VALID:
        updates["status"] = "pending_verification"

    set_clause = ", ".join(f"`{col}` = %s" for col in updates)
    values = list(updates.values()) + [invoice_id]

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(f"UPDATE invoices SET {set_clause} WHERE id = %s", values)
            conn.commit()
            cur.execute(f"SELECT {_INVOICE_COLS} FROM invoices WHERE id = %s", (invoice_id,))
            updated_row = _parse_row(cur.fetchone())

            if updated_row and learn_should_run:
                try:
                    from app.services.category_river_service import get_category_river_service
                    service = get_category_river_service()
                    service.learn_from_row(
                        updated_row,
                        updated_row.get("category"),
                        updated_row.get("sub_category"),
                    )
                except Exception:
                    pass

            return updated_row
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def delete_invoice(invoice_id: int) -> bool:
    """Delete an invoice by its ID. Returns True if a row was deleted, False if not found.

    Core logic:
      1. Find the doc_id for this invoice.
      2. Count how many OTHER invoices share the same doc_id (excluding this one).
      3. If other invoices exist with the same doc_id:
           → Delete only this invoice row. Document and S3 are untouched.
      4. If NO other invoices share this doc_id (this is the last one):
           → Delete invoice row + Doc DB record + S3 file.

    ┌─────────────────────────────────────────────┬────────────┬──────────┬──────────┐
    │ Scenario                                    │ Invoice DB │ Doc DB   │ S3       │
    ├─────────────────────────────────────────────┼────────────┼──────────┼──────────┤
    │ Other invoices still reference this doc_id  │ ✅ Delete  │ ❌ Keep  │ ❌ Keep  │
    │ No invoices left for this doc_id (last one) │ ✅ Delete  │ ✅ Delete│ ✅ Delete│
    └─────────────────────────────────────────────┴────────────┴──────────┴──────────┘
    """
    conn = get_connection()
    doc_id = None
    s3_key = None
    is_last = False

    try:
        with conn.cursor() as cur:
            # Step 1: Get this invoice's doc_id
            cur.execute(
                "SELECT doc_id FROM invoices WHERE id = %s",
                (invoice_id,),
            )
            row = cur.fetchone()
            if not row:
                logging.warning(f"[delete] invoice_id={invoice_id} not found in DB")
                return False

            doc_id = row["doc_id"]

            # Step 2: Count other invoices sharing the same doc_id (excluding this one)
            cur.execute(
                "SELECT COUNT(*) AS c FROM invoices WHERE doc_id = %s AND id != %s",
                (doc_id, invoice_id),
            )
            other_invoices_count = cur.fetchone()["c"]
            is_last = (other_invoices_count == 0)

            # Step 3: If this is the last invoice, fetch s3_key NOW before deleting
            if is_last:
                cur.execute(
                    "SELECT s3_key FROM documents WHERE doc_id = %s LIMIT 1",
                    (doc_id,),
                )
                doc_row = cur.fetchone()
                s3_key = doc_row["s3_key"] if doc_row else None

            logging.info(
                f"[delete] invoice_id={invoice_id} doc_id={doc_id} "
                f"other_invoices_count={other_invoices_count} is_last={is_last} "
                f"s3_key={s3_key}"
            )
    finally:
        conn.close()

    # Step 4: If last invoice → delete Doc DB + S3
    if is_last:
        if s3_key:
            try:
                delete_from_s3(s3_key)
                logging.info(f"[delete] S3 deleted: {s3_key}")
            except Exception as e:
                logging.error(f"[delete] S3 delete failed for {s3_key}: {e}")

        if doc_id:
            try:
                document_model.delete_document_by_doc_id(doc_id)
                logging.info(f"[delete] Doc DB deleted: doc_id={doc_id}")
            except Exception as e:
                logging.warning(f"[delete] Doc DB delete failed: {e}")
    else:
        logging.info(
            f"[delete] Doc DB + S3 kept — "
            f"{other_invoices_count} other invoice(s) still reference doc_id={doc_id}"
        )

    # Step 5: Always delete the invoice row
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM invoices WHERE id = %s", (invoice_id,))
            conn.commit()
            deleted = cur.rowcount > 0
            logging.info(f"[delete] invoice_id={invoice_id} deleted={deleted}")
            return deleted
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()