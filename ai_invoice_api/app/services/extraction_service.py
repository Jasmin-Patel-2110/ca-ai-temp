"""
Standalone invoice extraction service.

Calls a vLLM OpenAI-compatible vision endpoint (Qwen2.5-VL, etc.) — no dependency on demo.py.

Supported file types: .jpg / .jpeg / .png  (image)
                      .pdf                  (rendered via PyMuPDF)
"""
from __future__ import annotations

import base64
import json
import logging

logger = logging.getLogger(__name__)
import os
import re
from io import BytesIO
from typing import Optional

import requests
from PIL import Image

VLLM_BASE_URL = os.getenv("VLLM_BASE_URL", "http://127.0.0.1:8001").rstrip("/")
VISION_MODEL = os.getenv("VLLM_MODEL", "Qwen/Qwen2.5-VL-7B-Instruct")
_VLLM_API_KEY = os.getenv("VLLM_API_KEY", "").strip()
# Bookkeeping entity (e.g. "Satyawani"). If set: entity in Bill To/client → Purchase; entity as supplier → Sales
INVOICE_BOOK_COMPANY_NAME = os.getenv("INVOICE_BOOK_COMPANY_NAME", "").strip()

VLLM_MAX_PIXELS = int(os.getenv("VLLM_MAX_PIXELS", "602112"))  # must match --mm-processor-kwargs

# ── image helpers ─────────────────────────────────────────────────────────────


def _make_divisible(val: int, divisor: int = 28) -> int:
    """Ensure image dimensions are perfectly divisible by ViT patch size to avoid llama.cpp GGML crashes."""
    return max(divisor, (val // divisor) * divisor)


def _pil_to_b64(img: Image.Image) -> str:
    """Encode PIL image as base64 JPEG. Resize if exceeds max for speed. Forces dims to be divisible by 28."""
    img = img.convert("RGB")
    w, h = img.size
    if max(w, h) > 1120 or w % 28 != 0 or h % 28 != 0:
        if max(w, h) > 1120:
            scale = 1120 / max(w, h)
            new_w, new_h = int(w * scale), int(h * scale)
        else:
            new_w, new_h = w, h
        
        new_w = _make_divisible(new_w)
        new_h = _make_divisible(new_h)
        img = img.resize((new_w, new_h), Image.LANCZOS)
        
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=85)  # 85 is visually identical, smaller payload
    return base64.b64encode(buf.getvalue()).decode()


def _pil_to_b64_resize(img: Image.Image, max_size: int | None = None) -> str:
    """Resize image so longest side is max_size, then encode as base64 JPEG. Used for PDFs. Forces dims to be divisible by 28."""
    if max_size is None:
        max_size = 1120  # reverted to 1120 for best accuracy
    img = img.convert("RGB")
    w, h = img.size
    
    if max(w, h) > max_size or w % 28 != 0 or h % 28 != 0:
        if max(w, h) > max_size:
            scale = max_size / max(w, h)
            new_w, new_h = int(w * scale), int(h * scale)
        else:
            new_w, new_h = w, h
            
        new_w = _make_divisible(new_w)
        new_h = _make_divisible(new_h)
        img = img.resize((new_w, new_h), Image.LANCZOS)
        
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()


def _pdf_to_pages(file_path: str):
    """
    Render every PDF page as a PIL image and extract embedded text.
    Returns list of (PIL.Image, raw_text_str).
    Requires PyMuPDF (fitz).
    """
    import fitz  # PyMuPDF

    doc = fitz.open(file_path)
    results = []
    for page in doc:
        raw_text = page.get_text("text") or ""
        mat = fitz.Matrix(2.0, 2.0)
        clip = page.get_pixmap(matrix=mat)
        img = Image.frombytes("RGB", [clip.width, clip.height], clip.samples)
        results.append((img, raw_text.strip()))
    doc.close()
    return results


# ── prompt builder ────────────────────────────────────────────────────────────

def _build_prompt(raw_text: Optional[str] = None, known_client_name: Optional[str] = None, is_multi_page: bool = False) -> str:
    """
    Build the vision-LLM extraction prompt.

    Key design: the prompt ends with a JSON TEMPLATE that the model fills in.
    This is far more reliable than asking the model to invent its own JSON
    structure — it just fills the pre-defined keys and returns valid JSON.
    """
    known_client_name_clean = (known_client_name or "").strip()
    
    print(f"[extraction___client_name] Known client name: {known_client_name_clean}")
    logger.info(f"[extraction___client_name] Known client name: {known_client_name_clean}")

    intro_text = (
        "Carefully analyze the provided sequence of document images (which may contain multiple pages "
        "of the same invoice, or multiple distinct invoices) and extract all relevant and visible information.\n\n"
    ) if is_multi_page else (
        "Carefully analyze the provided invoice image and extract all relevant "
        "and visible information.\n\n"
    )

    header = intro_text + (
        "ACCURACY: For IRN, GSTIN, e-way bill, contact — read digit-by-digit. One wrong character = wrong.\n"
        "  GSTIN: verify Q vs O, 0 vs O. IRN: 64 hex chars, d/6/e/c often confused. E-way: 10–11 digits.\n\n"
        "Return the extracted data strictly in valid JSON format.\n"
        "STRICT RULES:\n"
        "- Return ONLY valid JSON — no markdown fences, no preamble, no explanation\n"
        "- If a field is not visible → set to null\n"
        "- Do NOT guess — only extract what is clearly visible\n"
        "- All currency/numeric values → plain numbers only (e.g. 1500.00 not '₹1,500')\n"
        "- ALL NAME FIELDS: copy character-by-character exactly as printed — preserve dashes,\n"
        "  dots, brackets, slashes, year suffixes. NEVER simplify, shorten, or reformat names.\n"
        "  Example: 'A-1 SUPARI (2024-2025)' must NOT become 'A 1 SUPARI' or 'A-1 SUPARI'\n\n"
        "EXTRACTION GUIDE:\n"
        "SUPPLIER: the business issuing this invoice (name at the top, or in the footer as "
        "\"For [Name]\" / \"Authorized Signatory for [Name]\" next to the signature).\n"
        "BUYER: the party who is being billed (Bill To / Buyer To Party only — never the footer signatory).\n\n"
        "  STEP 1 — Find a section labelled ANY of:\n"
        "    'Buyer To Party', 'Buyer To', 'Bill To Party', 'Bill To', 'Billed To', 'Sold To', 'Customer',\n"
        "    'Ship To Party', 'Ship To', 'Buyer', 'Party', 'Consignee',\n"
        "    'Patient', 'Client', 'Receiver', 'To', 'M/s', 'Account Holder'\n"
        "  STEP 2 — The FIRST bold/large text inside that section is buyer_name (e.g. 'M/S.: N N Traders Botad Chq').\n"
        "  STEP 3 — If no such section exists at all → set buyer_name to null.\n"
        f"KNOWN_CLIENT_NAME: {known_client_name_clean}\n"
        "IMPORTANT CONTEXT: We are processing documents for the KNOWN_CLIENT_NAME above.\n"
        "  - The printed name on the invoice may be similar to KNOWN_CLIENT_NAME, but not identical.\n"
        "  - Determine if KNOWN_CLIENT_NAME is the SUPPLIER or the BUYER on this/these invoice(s).\n"
        "  - If KNOWN_CLIENT_NAME matches the SUPPLIER: set transaction_type to 'Sales'. `client_name` is the exact printed SUPPLIER name.\n"
        "  - If KNOWN_CLIENT_NAME matches the BUYER: set transaction_type to 'Purchase'. `client_name` is the exact printed BUYER name.\n"
        "  - All buyer_*/seller_* field extraction must be anchored accurately based on who the KNOWN_CLIENT_NAME is.\n"
        "  - If KNOWN_CLIENT_NAME matches neither: set transaction_type to null and client_name to null.\n\n"
    )

    header += (
        "PAYMENT MODE: look in 'Payment Details', 'Mode', 'Payment Method' sections.\n"
        "  Map these to standard names:\n"
        "  'CC', 'Credit Card', 'CC APP'        → 'Credit Card'\n"
        "  'DC', 'Debit Card'                   → 'Debit Card'\n"
        "  'CHQ', 'Cheque', 'Check'             → 'Cheque'\n"
        "  'UPI', 'GPay', 'PhonePe', 'Paytm'   → 'UPI'\n"
        "  'NEFT', 'RTGS', 'IMPS', 'Net Banking'→ 'Bank Transfer'\n"
        "  'Cash', 'COD'                        → 'Cash'\n"
        "  'CC APP/CHQ/OTP' or combined modes   → use the FIRST method listed\n\n"
        "DATE: look for 'Invoice Date', 'Bill Date', 'Date of Issue', 'Billing Date'.\n"
        "  Accept any format: 25-Aug-2025, 25-Aug-25, 25.08.2025, 25/08/25, 25 Jan 23, etc.\n"
        "  Extract exactly as shown on the invoice.\n\n"
        "INVOICE NUMBER:\n"
        "  Extract exact invoice number as printed (examples: 53/25-26, JB/2526/05).\n"
        "  Never invent placeholder values like INV-001. If not clearly visible, return null.\n\n"
        "CONTACTS:\n"
        "  buyer_contact_number is the phone from BUYER section only.\n"
        "  seller_contact_number is the phone from SUPPLIER section only.\n"
        "  buyer_gst_number / buyer_pan_number are on BUYER section when visible; otherwise null.\n"
        "  seller_gst_number / seller_pan_number are on SUPPLIER section when visible; otherwise null.\n\n"
        "AMOUNT FIELDS — very important, read carefully:\n"
        "  amount         → TAXABLE / pre-tax subtotal (before GST is added)\n"
        "                   Look for: 'Taxable Amount', 'Basic Amount', 'Sub Total', line 'Amount In INR'\n"
        "  total          → GRAND TOTAL including GST — use the FOOTER / summary row only:\n"
        "                   'Total Amount after Tax', 'Net Payable', 'Total Due', 'Invoice Total' (with tax).\n"
        "                   NEVER copy the line-item or table 'Total' / 'Amount In INR' into `total` when GST is shown separately below.\n"
        "  gst            → TAX ONLY rupee amount (NOT the grand total)\n"
        "                   = cgst + sgst   OR   = igst\n"
        "  rate           → per-unit SELLING PRICE of one item (NOT the total)\n"
        "  round_off      → Round-off / rounding adjustment (often ±0.50 near grand total). Use 0 or null if not visible.\n"
        "  ⚠ amount + gst (+ round_off) = total. If unsure: amount = total - gst\n"
        "  ⚠ NEVER put the grand total in the gst or amount field\n"
        "  amount_paid    → Actual payment received; if 'Balance 0' / 'Paid in full', usually equals `total` (after tax), not the taxable subtotal.\n\n"
        "GST AMOUNTS (extract the RUPEE AMOUNT, not the rate %):\n"
        "  - Look in the SUMMARY / FOOTER section for CGST Total and SGST Total\n"
        "  - cgst / sgst: the column TOTAL at the bottom, not per-line values\n"
        "  - gst = cgst + sgst (intra-state) OR igst alone (inter-state)\n"
        "  - Do NOT put grand total in gst field\n\n"
        "BALANCE:\n"
        "  balance_amount → amount still owed = total - amount_paid\n"
        "  If 'Payment: ₹X' or 'Balance: 0.00' visible → balance_amount = 0\n\n"
        "INDUSTRY: MANDATORY — pick EXACTLY ONE from this list (match by goods/services on invoice):\n"
        "  Textile Manufacturing | Textile Jobwork | Supari | Labour | Jewellers | IT | Gov | Hospital | Diamond\n"
        "  Map: healthcare/medical → Hospital; jewellery/gems → Jewellers; government → Gov; textiles → Textile Manufacturing or Textile Jobwork.\n"
        "  If unclear, choose the closest match. Never use values outside this list.\n\n"
        "PRODUCT_NAME: The primary good or service on this invoice.\n"
        "  If multiple line items exist, provide the FIRST VALID item's name from the item table.\n"
        "  Look at 'Description', 'Particulars', 'Item' columns.\n"
        "  Do NOT concatenate multiple items. Just one item exactly as written.\n"
        "  Never return generic labels like 'Product' or 'Description'.\n\n"
        "FIELD MAPPING:\n"
        "  client_name    → Copy EXACTLY from invoice text character-by-character based on whether they are SUPPLIER or BUYER.\n"
        "  transaction_type → 'Sales' if KNOWN_CLIENT_NAME is supplier, 'Purchase' if buyer. Exactly one of: Sales | Purchase.\n"
        "  seller_party_name → Legal name of the INVOICE ISSUER / SUPPLIER copied EXACTLY as printed\n"
        "                      character-by-character from invoice header (top-left or 'Sold By').\n"
        "                      Preserve all dashes, dots, brackets, year suffixes.\n"
        "                      Example: 'A-1 SUPARI (2024-2025)' NOT 'A 1 SUPARI'.\n"
        "                      Must match supplier_name in additional_details.\n"
        "  buyer_party_name  → Legal name from Bill To / Buyer To Party / Billed To only — NOT the supplier.\n"
        "                      Copy exactly as printed. Never copy seller_party_name here.\n"
        "  buyer_contact_number → BUYER's phone from Bill To / Ship To ONLY. Do NOT use supplier section contacts.\n"
        "    If supplier shows 'Pravin 25362 / Paresh 25363', ignore those — extract the phone from Bill To section.\n"
        "  buyer_location       → BUYER's address (Bill To / Ship To), NOT the supplier's address.\n"
        "  payment_mode   → look in 'Payment Details' / 'Mode' section:\n"
        "    CC/Credit Card → 'Credit Card', DC/Debit Card → 'Debit Card',\n"
        "    UPI/GPay → 'UPI', CHQ/Cheque → 'Cheque', NEFT/RTGS → 'Bank Transfer',\n"
        "    Cash/COD → 'Cash'. Combined 'CC APP/CHQ/OTP' → first method = 'Credit Card'\n"
    )

    if raw_text and raw_text.strip():
        img_ref = "images below" if is_multi_page else "image below"
        header = (
            "RAW TEXT EXTRACTED FROM THIS DOCUMENT:\n"
            "────────────────────────────────────────\n"
            f"{raw_text[:3000]}\n"
            "────────────────────────────────────────\n"
            f"Use the raw text above AND the {img_ref} to fill every field accurately.\n"
            "WARNING: Raw text may have OCR errors — always prefer the visual image for name fields.\n\n"
        ) + header

    template = """
Fill in this JSON template exactly. Use null for missing fields. Numbers as plain decimals.
ADDRESSES: single line, max 80 chars. Do NOT repeat words.
AMOUNTS: amount = pre-tax subtotal. total = grand total WITH tax. gst = TAX ONLY (not grand total).
NAME FIELDS: copy character-by-character from invoice — preserve dashes, brackets, year suffixes exactly.
product_name: name of the main product or service described on this invoice (e.g. "LG Air Conditioner 1.5T", "Consulting Services", "DECOB PAD").
"""
    if is_multi_page:
        template += """
DOCUMENT CONTAINS MULTIPLE PAGES: Group pages belonging to the SAME invoice together into ONE invoice object. 
If the document contains MULTIPLE DIFFERENT invoices, extract EACH distinct invoice as a separate object in the array.
{
  "invoices": [
"""

    template += """{
  "client_name":       null,
  "product_name":      null,
  "buyer_party_name": null,
  "seller_party_name": null,
  "industry":          null,
  "category":          null,
  "sub_category":      null,
  "transaction_type":  null,
  "date":              null,
  "buyer_pan_number":  null,
  "seller_pan_number": null,
  "buyer_gst_number":  null,
  "seller_gst_number": null,
  "buyer_contact_number": null,
  "seller_contact_number": null,
  "buyer_location":    null,
  "seller_location":   null,
  "gst":               null,
  "cgst":              null,
  "sgst":              null,
  "igst":              null,
  "total":             null,
  "quantity":          null,
  "rate":              null,
  "amount":            null,
  "amount_paid":       null,
  "balance_amount":    null,
  "round_off":         null,
  "payment_mode":      null,
  "line_items":        [],
  "additional_details": {}
}

seller_gst_number: the SUPPLIER's GST registration number (GSTIN) — 15-char alphanumeric (e.g. 24ABLFA1617K1ZJ). Read char-by-char: Q vs O, 0 vs O, 1 vs I are commonly confused. Set to null if not visible.
buyer_gst_number: the BUYER's GST registration number (GSTIN) — 15-char alphanumeric. Set to null if not visible.

ADDITIONAL_DETAILS — MANDATORY: You MUST populate additional_details with ALL visible supplementary data.
Extract every field below when visible. Do NOT return empty additional_details {} if any of these exist on the invoice:
  - supplier_name: copy EXACTLY as printed on invoice header character-by-character, including dashes,
    brackets, year suffixes (e.g. 'A-1 SUPARI (2024-2025)' NOT 'A 1 SUPARI' or 'A-1 SUPARI').
    NEVER simplify, shorten, or reformat the supplier name.
  - supplier_address, supplier_gstin (same value as seller_gst_number above — include for completeness)
  - supplier_phone, supplier_contact (SUPPLIER phone from the supplier section only)
  - bill_to_name, bill_to_party_name, buyer_name (Bill To / Buyer To Party legal name — copy exactly as printed)
  - buyer_phone, buyer_address, client_address (Bill To contact and address; buyer_phone = phone IN Bill To section)
  - buyer_pan, buyer_pancard (PAN on BUYER section when visible)
  - buyer_gstin (GSTIN on BUYER section when visible; if only supplier GSTIN exists then keep null)
  - transporter_gstin = TRANSPORTER/carrier GSTIN only (e.g. Jay Transport 24AZGPS0073E1ZL). NOT buyer or supplier GSTIN
  - invoice_number, acknowledgement_number, acknowledgement_date
  - irn (IRN hash — 64 hex chars; read carefully, d/6/e/c often confused)
  - eway_bill_number = e-way bill no ONLY when labelled 'E-Way Bill'/'EBN'. If no e-way bill → null. Never put invoice number here
  - vehicle_number = vehicle registration ONLY (e.g. KA21B1539). If vehicle is blank → null. Never put transporter GSTIN here
  - hsn_sac_code, tax_rate, tax_amount, taxable_value
  - motor_vehicle_no (only if different from vehicle_number)
  - line_items: array of ALL products, each with product_name, quantity, rate, amount (e.g. [{"product_name":"Choll Moti Second","quantity":1235.0,"rate":290.0,"amount":358150.0},{"product_name":"Choll Mora Second","quantity":325.0,"rate":290.0,"amount":94250.0}])
  - bank_name, bank_account_number, rtgs_ifsc_code
  - terms, declaration, authorized_signatory
Use descriptive snake_case keys. Do NOT include null keys — only add keys where a value is clearly visible.
}
"""
    if is_multi_page:
        template += """  ]
}
"""
    # Keep template client_name unforced; model must extract it from invoice text.
    return header + template


# ── vLLM (OpenAI-compatible) caller ───────────────────────────────────────────

def _call_vision_llm(b64_images: list[str], prompt: str) -> str:
    """POST to vLLM's OpenAI-compatible /v1/chat/completions (no OpenAI SDK)."""
    max_tokens = min(16384, 2048 * max(1, len(b64_images)))
    content: list[dict] = []
    for b64 in b64_images:
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
            }
        )
    content.append({"type": "text", "text": prompt})

    url = f"{VLLM_BASE_URL}/v1/chat/completions"
    headers = {"Content-Type": "application/json"}
    if _VLLM_API_KEY:
        headers["Authorization"] = f"Bearer {_VLLM_API_KEY}"

    payload = {
        "model": VISION_MODEL,
        "messages": [{"role": "user", "content": content}],
        "max_tokens": max_tokens,
        "temperature": 0.02,
        "top_p": 0.95,
    }

    try:
        http = requests.post(url, json=payload, headers=headers, timeout=1200)
    except requests.RequestException as e:
        raise RuntimeError(f"vLLM request failed: {e}") from e

    if not http.ok:
        err_body = (http.text or "")[:800]
        raise RuntimeError(
            f"vLLM request failed: {http.status_code} {http.reason}. {err_body}"
        )

    try:
        data = http.json()
    except json.JSONDecodeError as e:
        raise RuntimeError(f"vLLM returned non-JSON: {e}") from e

    raw = ""
    choices = data.get("choices") if isinstance(data, dict) else None
    if choices and isinstance(choices, list) and choices:
        msg = choices[0].get("message") if isinstance(choices[0], dict) else None
        if isinstance(msg, dict):
            raw = (msg.get("content") or "").strip()

    print(f"[extraction] vLLM raw response ({len(raw)} chars): {raw[:800]}")
    logger.info(f"[extraction] vLLM raw response ({len(raw)} chars): {raw[:800]}")
    return raw


# ── JSON parser ───────────────────────────────────────────────────────────────

def _repair_truncated_json(text: str) -> dict:
    """
    Recover usable fields from a JSON string that was cut off mid-token.

    Strategy:
      Walk the text character-by-character tracking string/depth state.
      Record the position of every top-level comma that separates complete
      key-value pairs.  On parse failure, truncate at the last such position,
      close all open braces, and retry.
    """
    last_safe = -1     # index of last comma at depth == 1 (top-level field boundary)
    in_string = False
    escape_next = False
    depth = 0

    for i, ch in enumerate(text):
        if escape_next:
            escape_next = False
            continue
        if ch == "\\" and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch in "{[":
            depth += 1
        elif ch in "}]":
            depth -= 1
        elif ch == "," and depth == 1:
            last_safe = i

    if last_safe == -1:
        return {}

    truncated = text[:last_safe].rstrip().rstrip(",")
    # Close any unclosed braces/brackets
    open_braces   = truncated.count("{") - truncated.count("}")
    open_brackets = truncated.count("[") - truncated.count("]")
    truncated += "]" * max(open_brackets, 0)
    truncated += "}" * max(open_braces, 0)

    try:
        return json.loads(truncated)
    except json.JSONDecodeError:
        return {}


def _parse_json(raw: str) -> dict:
    """
    Extract the JSON object from the model's raw text response.
    Falls back to _repair_truncated_json when the response is cut off mid-token
    (happens when a field value fills up the num_predict budget).
    """
    clean = raw.strip()

    # Strip markdown fences (```json ... ```)
    if "```" in clean:
        for part in clean.split("```"):
            p = part.strip()
            if p.startswith("json"):
                p = p[4:].strip()
            if p.startswith("{"):
                clean = p
                break

    clean = clean.strip()

    # Find the outermost { ... } block
    s = clean.find("{")
    e = clean.rfind("}") + 1
    if s != -1 and e > s:
        clean = clean[s:e]

    # ── First attempt: parse as-is ────────────────────────────────────────────
    try:
        result = json.loads(clean)
        print(f"[extraction] Parsed OK — keys: {list(result.keys())}")
        logger.info(f"[extraction] Parsed OK — keys: {list(result.keys())}")
        return result
    except json.JSONDecodeError as exc:
        print(f"[extraction] JSON truncated ({exc}), attempting repair...")
        logger.info(f"[extraction] JSON truncated ({exc}), attempting repair...")

    # ── Second attempt: repair truncated JSON ─────────────────────────────────
    # Use the raw {…} block (may not have a closing })
    fragment = raw[raw.find("{"):] if raw.find("{") != -1 else raw
    repaired = _repair_truncated_json(fragment)
    if repaired:
        print(f"[extraction] Repair succeeded — keys: {list(repaired.keys())}")
        logger.info(f"[extraction] Repair succeeded — keys: {list(repaired.keys())}")
        return repaired

    print(f"[extraction] Repair failed — raw (first 400 chars): {raw[:400]}")
    logger.info(f"[extraction] Repair failed — raw (first 400 chars): {raw[:400]}")
    return {}


# ── normalization ─────────────────────────────────────────────────────────────

def _safe_float(val) -> Optional[float]:
    try:
        if val is None:
            return None
        if isinstance(val, (int, float)):
            return float(val)
        txt = str(val).strip()
        for ch in ["₹", "$", "€", ","]:
            txt = txt.replace(ch, "")
        return float(txt) if txt else None
    except (TypeError, ValueError):
        return None


def _money_close(a: Optional[float], b: Optional[float], *, abs_tol: float = 1.0) -> bool:
    if a is None or b is None:
        return False
    scale = max(abs(a), abs(b), 1000.0)
    return abs(a - b) <= max(abs_tol, 0.002 * scale)


def _collect_taxable_reference_amounts(data: dict, ad: dict) -> list[float]:
    """Amounts that usually represent taxable / line value (before GST) for reconciliation."""
    out: list[float] = []
    li = ad.get("line_items") if isinstance(ad.get("line_items"), list) else []
    for item in li[:20]:
        if not isinstance(item, dict):
            continue
        for k in ("taxable_value", "taxableValue", "amount", "total", "line_total", "lineTotal"):
            v = _safe_float(item.get(k))
            if v is not None and v > 0:
                out.append(v)
                break
    q, r = _safe_float(data.get("quantity")), _safe_float(data.get("rate"))
    if q and r:
        out.append(round(q * r, 2))
    for k in (
        "taxable_amount",
        "taxableAmount",
        "taxable_value",
        "taxableValue",
        "total_amount_before_tax",
        "amount_before_tax",
    ):
        v = _safe_float(ad.get(k) or data.get(k))
        if v is not None and v > 0:
            out.append(v)
    gd = ad.get("gst_details") if isinstance(ad.get("gst_details"), dict) else {}
    if gd:
        for k in ("taxable_value", "taxableValue", "taxable_amount", "taxableAmount"):
            v = _safe_float(gd.get(k))
            if v is not None and v > 0:
                out.append(v)
    return sorted({x for x in out if x and x > 0})


def _reconcile_amount_total_when_equal(data: dict, ad: dict) -> None:
    """
    When `amount` and `total` are equal but GST is non-zero, the model often duplicated
    the taxable line in both fields. Use line/qty×rate/taxable hints to either:
      - set `total` = taxable + GST + round_off, or
      - set `amount` = total - GST when both fields duplicated the grand total.
    Avoids the bad rule 'amount = total - gst' when both were actually the taxable figure.
    """
    amount_f = _safe_float(data.get("amount"))
    total_f = _safe_float(data.get("total"))
    gst_f = _safe_float(data.get("gst"))
    if amount_f is None or total_f is None or not gst_f or gst_f <= 0:
        return
    if not _money_close(amount_f, total_f):
        return

    ro = _safe_float(data.get("round_off") or ad.get("round_off") or ad.get("rounding_off") or ad.get("rounding"))
    ro = ro if ro is not None else 0.0
    expected_grand = round(amount_f + gst_f + ro, 2)
    derived_taxable = round(total_f - gst_f, 2)

    refs = _collect_taxable_reference_amounts(data, ad)
    match_amt = any(_money_close(amount_f, r) for r in refs) if refs else False
    match_derived = any(_money_close(derived_taxable, r) for r in refs) if refs else False

    if match_amt and not match_derived:
        data["total"] = expected_grand
        return
    if match_derived and not match_amt:
        data["amount"] = derived_taxable
        return
    if match_amt and match_derived and abs(expected_grand - total_f) > 0.02:
        data["total"] = expected_grand


def _apply_bill_total_amount_check(data: dict, ad: dict) -> None:
    """
    Validate bill arithmetic for UI / QA:
      - quantity × rate ≈ amount (line)
      - amount + tax (gst or cgst+sgst / igst) + round_off ≈ total (grand)
      - total − amount_paid ≈ balance_amount (payment)

    Writes `additional_details['bill_total_check']` with booleans and computed values.
    If the line check passes but grand total does not, sets `total` from components (conservative fix).
    """
    amt = _safe_float(data.get("amount"))
    tot = _safe_float(data.get("total"))
    q = _safe_float(data.get("quantity"))
    r = _safe_float(data.get("rate"))
    ro = _safe_float(data.get("round_off") or ad.get("round_off") or ad.get("rounding_off") or ad.get("rounding"))
    ro = 0.0 if ro is None else ro

    cgst = _safe_float(data.get("cgst"))
    sgst = _safe_float(data.get("sgst"))
    igst = _safe_float(data.get("igst"))
    gst_t = _safe_float(data.get("gst"))

    tax_sum: Optional[float] = None
    if (cgst or 0) != 0 or (sgst or 0) != 0:
        tax_sum = round((cgst or 0.0) + (sgst or 0.0), 2)
    elif igst is not None and igst != 0:
        tax_sum = igst
    elif gst_t is not None:
        tax_sum = gst_t

    ap = _safe_float(data.get("amount_paid"))
    bal = _safe_float(data.get("balance_amount"))

    def _tol(base: float) -> float:
        return max(1.5, 0.003 * max(abs(base), 1.0))

    check: dict = {}

    line_ok: Optional[bool] = None
    if q is not None and r is not None and amt is not None:
        line_amt = round(q * r, 2)
        check["qty_times_rate"] = line_amt
        line_ok = abs(line_amt - amt) <= _tol(amt)
        check["line_amount_matches"] = line_ok

    expected_grand: Optional[float] = None
    grand_ok: Optional[bool] = None
    if amt is not None and tax_sum is not None:
        expected_grand = round(amt + tax_sum + ro, 2)
        check["expected_grand_total"] = expected_grand
        if tot is not None:
            grand_ok = abs(expected_grand - tot) <= _tol(tot)
            check["grand_total_matches_components"] = grand_ok
            if not grand_ok:
                check["grand_total_delta"] = round(tot - expected_grand, 2)

    pay_ok: Optional[bool] = None
    if tot is not None and ap is not None and bal is not None:
        exp_bal = round(tot - ap, 2)
        check["expected_balance"] = exp_bal
        pay_ok = abs(exp_bal - bal) <= _tol(tot)
        check["payment_balance_matches"] = pay_ok

    check["summary_ok"] = not any(v is False for v in (line_ok, grand_ok, pay_ok))

    if (
        line_ok is True
        and grand_ok is False
        and expected_grand is not None
        and tot is not None
        and abs(expected_grand - tot) > _tol(tot)
    ):
        data["total"] = expected_grand
        check["total_auto_corrected"] = True
        check["grand_total_matches_components"] = True
        amt_now = _safe_float(data.get("amount"))
        if (bal is None or bal <= 0.02) and ap is not None and amt_now is not None:
            if _money_close(ap, amt_now) and expected_grand > ap + 0.02:
                data["amount_paid"] = expected_grand
                check["amount_paid_synced_to_total"] = True

    ad["bill_total_check"] = check


def _normalize_for_text_match(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _is_similar_party_name(a: Optional[str], b: Optional[str]) -> bool:
    if not a or not b:
        return False
    na = _normalize_for_text_match(str(a))
    nb = _normalize_for_text_match(str(b))
    if not na or not nb:
        return False
    return na == nb or na in nb or nb in na


def _hint_matches_party_name(hint: Optional[str], name: Optional[str]) -> bool:
    """
    True if user hint refers to the same party as `name`.
    Requires len(hint.strip()) >= 3 to avoid single-letter false positives.
    """
    if not hint or not name:
        return False
    h = str(hint).strip()
    if len(h) < 3:
        return False
    if _is_similar_party_name(hint, name):
        return True
    parts = h.split()
    t_hint = parts[0] if parts else h
    if len(t_hint) < 3:
        return False
    n = str(name).strip()
    if not n:
        return False
    return _is_similar_party_name(t_hint, n) or _is_similar_party_name(t_hint, name)


def _clean_party_display_name(name: Optional[str]) -> Optional[str]:
    if not name or not isinstance(name, str):
        return None
    s = name.strip()
    if not s:
        return None
    # Footer/signature text often prefixes names with "For ...".
    s = re.sub(r"(?i)^\s*for\s+[:\-]?\s*", "", s).strip()
    s = re.sub(r"(?i)^\s*authorized\s+signatory\s+(?:for\s+)?[:\-]?\s*", "", s).strip()
    return s or None


def _best_invoice_name_for_hint(hint: Optional[str], candidates: list) -> Optional[str]:
    """Longest invoice-printed name that matches the user hint (deduped by normalized form)."""
    if not hint or len(str(hint).strip()) < 3:
        return None
    seen: set[str] = set()
    matches: list[str] = []
    for c in candidates:
        if not isinstance(c, str) or not c.strip():
            continue
        s_raw = c.strip()
        s = _clean_party_display_name(s_raw) or s_raw
        key = _normalize_for_text_match(s)
        if not key or key in seen:
            continue
        if _hint_matches_party_name(hint, s):
            seen.add(key)
            matches.append(s)
    if not matches:
        return None
    return max(matches, key=len)


_AD_SKIP_KEYS = frozenset({
    "irn", "eway_bill_number", "e_way_bill_number", "eway_bill", "ewb_no",
    "vehicle_number", "motor_vehicle_no", "transporter_gstin",
    "invoice_number", "invoicenumber", "acknowledgement_number", "hsn_sac_code",
    "tax_rate", "rtgs_ifsc_code", "ifsc", "bank_account_number",
    "line_items", "gst_details", "quality_flags", "product_name_confidence",
    "invoice_number_confidence",
})


def _looks_like_party_name_value(val: str) -> bool:
    t = val.strip()
    if len(t) < 4 or len(t) > 220:
        return False
    if not re.search(r"[A-Za-z]", t):
        return False
    compact = re.sub(r"\s+", "", t.upper())
    if re.fullmatch(r"\d{2}[A-Z]{5}\d{4}[A-Z]\d[Z][A-Z0-9]", compact):
        return False
    digits = sum(c.isdigit() for c in t)
    if digits > len(t) * 0.6 and len(t) > 12:
        return False
    return True


def _signoff_supplier_bias(s: str) -> bool:
    """Footer / signatory phrasing often names the invoice issuer."""
    return bool(re.search(r"(?i)\bfor\s+[A-Za-z]", s))


def _extract_supplier_signoff_names(ad: Optional[dict], _depth: int = 0) -> list[str]:
    """
    Extract supplier-like names from footer/signatory text patterns like:
    'For Arish Impex', 'Authorized Signatory for Arish Impex'.
    """
    if not isinstance(ad, dict) or _depth > 8:
        return []
    out: list[str] = []
    seen: set[str] = set()

    def add_from_text(text: str) -> None:
        s = text.strip()
        if not s:
            return
        for pat in (
            r"(?i)\bfor\s+([A-Za-z][A-Za-z0-9&.,()\-/'\s]{2,120})",
            r"(?i)\bauthorized\s+signatory\s+(?:for\s+)?([A-Za-z][A-Za-z0-9&.,()\-/'\s]{2,120})",
        ):
            m = re.search(pat, s)
            if not m:
                continue
            candidate = _clean_party_display_name(m.group(1)) or m.group(1).strip()
            key = _normalize_for_text_match(candidate)
            if key and key not in seen and _looks_like_party_name_value(candidate):
                seen.add(key)
                out.append(candidate)

    def walk(obj: object, depth: int) -> None:
        if depth > 8:
            return
        if isinstance(obj, dict):
            for v in obj.values():
                walk(v, depth + 1)
        elif isinstance(obj, list):
            for item in obj:
                walk(item, depth + 1)
        elif isinstance(obj, str):
            add_from_text(obj)

    walk(ad, _depth)
    return out


def _collect_ad_name_like_strings(ad: Optional[dict], _depth: int = 0) -> list[str]:
    """Flat list of human-readable strings from additional_details for hint / party expansion."""
    if not isinstance(ad, dict) or _depth > 8:
        return []
    out: list[str] = []
    seen: set[str] = set()

    def add(s: str) -> None:
        clean = _clean_party_display_name(s) or s
        if not _looks_like_party_name_value(clean):
            return
        key = _normalize_for_text_match(clean)
        if key and key not in seen:
            seen.add(key)
            out.append(clean.strip())

    def walk(obj: object, depth: int) -> None:
        if depth > 8:
            return
        if isinstance(obj, dict):
            for k, v in obj.items():
                lk = str(k).lower()
                if lk in _AD_SKIP_KEYS or lk.endswith("_confidence"):
                    continue
                if lk in ("line_items", "gst_details", "quality_flags"):
                    continue
                walk(v, depth + 1)
        elif isinstance(obj, list):
            for item in obj:
                walk(item, depth + 1)
        elif isinstance(obj, str):
            add(obj)

    walk(ad, _depth)
    return out


def _matches_known_buyer_name(s: str, ad: dict, data: dict) -> bool:
    for b in (
        ad.get("bill_to_party_name"),
        ad.get("bill_to_name"),
        ad.get("buyer_name"),
        data.get("buyer_party_name"),
    ):
        if b and _parties_match_normalized(s, b):
            return True
    return False


def _matches_known_supplier_name(s: str, ad: dict, data: dict) -> bool:
    for x in (ad.get("supplier_name"), data.get("seller_party_name")):
        if x and _parties_match_normalized(s, x):
            return True
    return False


def _extra_hint_matches_supplier(ad_strings: list[str], hint: str, ad: dict, data: dict) -> bool:
    for s in ad_strings:
        if not _hint_matches_party_name(hint, s):
            continue
        if _signoff_supplier_bias(s) or _matches_known_supplier_name(s, ad, data):
            return True
    return False


def _extra_hint_matches_buyer(ad_strings: list[str], hint: str, ad: dict, data: dict) -> bool:
    for s in ad_strings:
        if not _hint_matches_party_name(hint, s):
            continue
        if _matches_known_buyer_name(s, ad, data):
            return True
    return False


def _gstin_norm(g: Optional[str]) -> str:
    if not g or not isinstance(g, str):
        return ""
    return re.sub(r"\s+", "", g.strip().upper())


def _gstins_equal(a: Optional[str], b: Optional[str]) -> bool:
    return bool(a and b and _gstin_norm(a) == _gstin_norm(b))


def _maybe_swap_supplier_buyer_in_ad(data: dict, ad: dict) -> None:
    """
    If additional_details has supplier/buyer GSTIN slots crossed vs top-level
    seller_gst_number / buyer_gst_number, swap supplier vs buyer blocks in ad.
    """
    if not isinstance(ad, dict):
        return
    sg = _gstin_norm(data.get("seller_gst_number"))
    bg = _gstin_norm(data.get("buyer_gst_number"))
    ad_sg = _gstin_norm(ad.get("supplier_gstin"))
    ad_bg = _gstin_norm(ad.get("buyer_gstin"))
    if not (sg and bg and ad_sg and ad_bg):
        return
    if ad_sg != bg or ad_bg != sg:
        return

    keys = (
        "supplier_name", "supplier_address", "supplier_gstin", "supplier_phone",
        "supplier_contact", "supplier_pan",
        "bill_to_party_name", "bill_to_name", "buyer_name",
        "buyer_address", "client_address", "bill_to_address", "ship_to_address",
        "buyer_gstin", "buyer_phone", "bill_to_phone",
        "buyer_pan", "buyer_pancard",
    )
    snap = {k: ad.get(k) for k in keys}

    b_party = snap.get("bill_to_party_name") or snap.get("bill_to_name") or snap.get("buyer_name")
    b_addr = snap.get("buyer_address") or snap.get("client_address") or snap.get("bill_to_address")
    b_ph = snap.get("buyer_phone") or snap.get("bill_to_phone")
    b_pan = snap.get("buyer_pan") or snap.get("buyer_pancard")

    ad["supplier_name"] = b_party
    ad["supplier_address"] = b_addr
    ad["supplier_gstin"] = snap.get("buyer_gstin")
    ad["supplier_phone"] = b_ph or snap.get("supplier_phone")
    ad["supplier_contact"] = b_ph or snap.get("supplier_contact")
    if b_pan:
        ad["supplier_pan"] = b_pan

    ad["bill_to_party_name"] = snap.get("supplier_name")
    ad["bill_to_name"] = snap.get("supplier_name")
    ad["buyer_name"] = snap.get("supplier_name")
    ad["buyer_address"] = snap.get("supplier_address")
    ad["client_address"] = snap.get("supplier_address")
    ad["bill_to_address"] = snap.get("supplier_address") or snap.get("bill_to_address")
    ad["ship_to_address"] = snap.get("ship_to_address")
    ad["buyer_gstin"] = snap.get("supplier_gstin")
    ad["buyer_phone"] = snap.get("supplier_phone")
    ad["bill_to_phone"] = snap.get("supplier_phone") or snap.get("supplier_contact")
    if snap.get("supplier_pan"):
        ad["buyer_pan"] = snap.get("supplier_pan")


def _seller_gst_aligns_with_ad_supplier(data: dict, ad: dict) -> bool:
    sg = data.get("seller_gst_number")
    ad_sg = ad.get("supplier_gstin")
    return _gstins_equal(sg, ad_sg)


def _parties_match_normalized(a: Optional[str], b: Optional[str]) -> bool:
    if not a or not b:
        return False
    na = _normalize_for_text_match(str(a))
    nb = _normalize_for_text_match(str(b))
    if not na or not nb:
        return False
    return na == nb or na in nb or nb in na


def _value_exists_in_text(value: str, raw_text: Optional[str]) -> bool:
    if not value or not raw_text:
        return False
    return _normalize_for_text_match(value) in _normalize_for_text_match(raw_text)


def _value_loosely_in_text(value: str, raw_text: Optional[str]) -> bool:
    """When strict match fails (OCR spacing/punctuation differs), require digit run to appear in OCR."""
    if not value or not raw_text:
        return False
    dv = "".join(c for c in value if c.isdigit())
    dt = "".join(c for c in raw_text if c.isdigit())
    if len(dv) < 4 or len(dv) > 22:
        return False
    return dv in dt


def _extract_invoice_number_from_text(raw_text: Optional[str]) -> Optional[str]:
    if not raw_text:
        return None
    patterns = [
        r"(?:invoice|inv)\.?\s*(?:no|number|#)?\s*[:#.\-\s]*\s*([A-Za-z0-9][A-Za-z0-9/\-]{1,39})",
        r"(?:bill\s*(?:no|number)?)\s*[:#.\-\s]*\s*([A-Za-z0-9][A-Za-z0-9/\-]{1,39})",
        r"(?:invoice\s*(?:no|number)?|bill\s*(?:no|number)?)\s*[:#\-]?\s*([A-Za-z0-9][A-Za-z0-9/\-]{2,39})",
        r"\b([A-Za-z]{1,6}/\d{1,4}(?:[-/]\d{1,4}){0,2})\b",
    ]
    for pattern in patterns:
        m = re.search(pattern, raw_text, re.I)
        if m:
            return m.group(1).strip()
    return None


def _extract_product_name_from_text(raw_text: Optional[str]) -> Optional[str]:
    if not raw_text:
        return None
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in raw_text.splitlines()]
    lines = [ln for ln in lines if ln]
    for idx, line in enumerate(lines):
        key = line.lower()
        if "product name" in key or "particular" in key or "description" in key or "item" in key:
            for nxt in lines[idx + 1 : idx + 6]:
                # Skip lines that are mostly numeric/table metadata.
                if re.fullmatch(r"[\d\s.,/%\-:]+", nxt):
                    continue
                if len(re.findall(r"[A-Za-z]", nxt)) < 3:
                    continue
                return nxt[:500]
    return None


# ── Reject PAN fields that are actually GSTINs (model misread) ───────────
def _clean_pan(pan: Optional[str]) -> Optional[str]:
    """Return None if the value looks like a GSTIN instead of a PAN."""
    if not pan or not isinstance(pan, str):
        return None
    p = pan.strip().upper()
    # Valid PAN: exactly 10 chars, 5 letters + 4 digits + 1 letter
    if re.fullmatch(r"[A-Z]{5}[0-9]{4}[A-Z]", p):
        return p
    return None


def _fix_gstin_ocr(gstin: Optional[str]) -> Optional[str]:
    """
    Auto-correct common OCR misreads in GSTIN (always 15 chars):
    - Positions 0-1: state code, must be digits  → 'O' becomes '0'
    - Position 12:   entity number, must be digit → 'O' becomes '0'
    - Position 13:   always 'Z'                  → '0','2','7' become 'Z'
    - Position 14:   checksum is alphanumeric; OCR often reads trailing '0' as 'O'
                     in invoices, so normalize final 'O' to '0'.
    """
    if not gstin or not isinstance(gstin, str):
        return gstin
    g = list(gstin.strip().upper())
    if len(g) != 15:
        return gstin
    # Positions 0-1: must be digits
    for i in range(2):
        if g[i] == "O":
            g[i] = "0"
    # Position 12: must be digit
    if g[12] == "O":
        g[12] = "0"
    # Position 13: must be 'Z'
    if g[13] in ("0", "2", "7"):
        g[13] = "Z"
    # Position 14: checksum is alphanumeric; normalize OCR 'O' to '0'
    if g[14] == "O":
        g[14] = "0"
    return "".join(g)


def _extract_pan_from_gstin(gst_number: Optional[str]) -> Optional[str]:
    """
    Derive PAN from GSTIN by removing the first 2 chars and last 3 chars.
    Example: 27ANUPI8536L1Z4 -> ANUPI8536L
    """
    if not gst_number or not isinstance(gst_number, str):
        return None
    gst = gst_number.strip().upper().replace(" ", "")
    if len(gst) < 15:
        return None
    candidate = gst[2:12]  # 10 chars PAN in standard GSTIN format
    # PAN: 5 letters + 4 digits + 1 letter (e.g. ANUPI8536L)
    if re.fullmatch(r"[A-Z]{5}[0-9]{4}[A-Z]", candidate):
        return candidate
    return None


def _validate_invoice_number(candidate: Optional[str], raw_text: Optional[str]) -> tuple[Optional[str], str, Optional[str]]:
    if not candidate or not isinstance(candidate, str):
        return None, "low", "invoice_number_missing"
    value = candidate.strip()
    if not value:
        return None, "low", "invoice_number_missing"

    # Reject generic label words that appear on invoices as stamps but are NOT invoice numbers
    _INVOICE_NUMBER_BLOCKLIST = {
        "original", "copy", "duplicate", "triplicate", "quadruplicate",
        "buyer", "seller", "supplier", "customer", "recipient",
        "invoice", "bill", "receipt", "voucher", "challan",
        "na", "n/a", "nil", "none", "not applicable",
    }
    if value.lower() in _INVOICE_NUMBER_BLOCKLIST:
        return None, "low", "invoice_number_generic_label"

    if re.fullmatch(r"INV-\d{3,}", value.upper()):
        if raw_text and _value_exists_in_text(value, raw_text):
            return value, "high", None
        if raw_text and _value_loosely_in_text(value, raw_text):
            return value, "medium", "invoice_number_loose_ocr_match"
        return None, "low", "invoice_number_synthetic_pattern"

    if len(value) < 2 or len(value) > 40:
        return None, "low", "invoice_number_length_invalid"

    if raw_text:
        if _value_exists_in_text(value, raw_text):
            return value, "high", None
        if _value_loosely_in_text(value, raw_text):
            return value, "medium", "invoice_number_loose_ocr_match"
        return None, "low", "invoice_number_not_found_in_ocr_text"

    # No raw_text available — require alphanumeric pattern
    if re.search(r"[A-Za-z]", value) and re.search(r"\d", value):
        return value, "medium", None
    if value.isdigit() and len(value) >= 2:
        return value, "medium", None
    return None, "low", "invoice_number_pattern_weak"


def _validate_product_name(candidate: Optional[str], raw_text: Optional[str]) -> tuple[Optional[str], str, Optional[str]]:
    if not candidate or not isinstance(candidate, str):
        return None, "low", "product_name_missing"
    value = re.sub(r"\s+", " ", candidate).strip()
    if not value:
        return None, "low", "product_name_missing"
    if len(value) < 3 or len(value) > 500:
        return None, "low", "product_name_length_invalid"

    generic = {
        "product", "products", "item", "items", "description", "particular",
        "particulars", "goods", "service", "services",
    }
    if value.lower() in generic:
        return None, "low", "product_name_generic_label"

    if raw_text:
        if _value_exists_in_text(value, raw_text):
            return value, "high", None
        return value, "medium", "product_name_not_found_in_ocr_text"
    return value, "medium", None


def _resolve_product_name(data: dict, ad: dict) -> Optional[str]:
    """Resolve product_name from top-level, additional_details, or line_items. Return JUST the first item's name."""
   
    # Ensure any top-level line_items (from the updated template) get saved to the DB via ad
    if "line_items" in data and isinstance(data["line_items"], list) and data["line_items"]:
        ad["line_items"] = data["line_items"]
       
    line_items = ad.get("line_items")
    if isinstance(line_items, list) and len(line_items) >= 1:
        for item in line_items:
            if isinstance(item, dict):
                for k in ("product_name", "description", "item_name", "particulars", "name"):
                    v = item.get(k)
                    if isinstance(v, str) and v.strip():
                        return v.strip()[:500]
    for key in ("product_name", "item_name", "description", "goods_description",
                "item_description", "product", "particulars", "product_description"):
        val = data.get(key) or ad.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()[:500]
    return None


def _resolve_payment_mode(
    raw: Optional[str],
    amount_paid: Optional[float] = None,
    balance: Optional[float] = None,
) -> Optional[str]:
    """Normalise raw payment strings like 'CC APP/CHQ/OTP' → 'Credit Card'."""
    if not raw:
        # Fallback: if paid in full with no mode → assume Cash
        if amount_paid and amount_paid > 0 and not balance:
            return "Cash"
        return None

    r = str(raw).upper()

    if any(k in r for k in ("CREDIT", "CC APP", " CC", "CC/")):
        return "Credit Card"
    if any(k in r for k in ("DEBIT", "DC APP", " DC", "DC/")):
        return "Debit Card"
    if any(k in r for k in ("UPI", "GPAY", "PHONEPE", "PAYTM", "BHIM")):
        return "UPI"
    if any(k in r for k in ("NEFT", "RTGS", "IMPS", "NET BANKING", "NETBANKING")):
        return "Bank Transfer"
    if any(k in r for k in ("CHQ", "CHEQUE", "CHECK")):
        return "Cheque"
    if any(k in r for k in ("CASH", "COD")):
        return "Cash"
    if any(k in r for k in ("CARD",)):
        return "Card"
    if any(k in r for k in ("OTP", "APP", "ONLINE")):
        return "Online"

    # Return title-cased raw value if nothing matched
    return raw.strip().title()


def _digits_only_phone(s: str) -> str:
    d = "".join(c for c in (s or "") if c.isdigit())
    if len(d) >= 12 and d.startswith("91"):
        d = d[-10:]
    return d if len(d) >= 10 else d


def _extract_valid_indian_phone(phone_value: object) -> Optional[str]:
    """
    Return a normalized 10-digit phone string only if `phone_value` contains
    a valid phone pattern. Rejects strings like "Pravin 25362 / Paresh 25363".
    """
    if phone_value is None:
        return None
    if not isinstance(phone_value, str):
        phone_value = str(phone_value)

    s = phone_value.strip()
    if not s:
        return None

    # Accept:
    # - optional +/91 prefix, then 10 consecutive digits
    # - optional +/91 prefix, then 5 digits + separators + 5 digits (digits separated only by whitespace/-/slash)
    #
    # Important: we deliberately do NOT allow alphabetic tokens between the digit groups.
    patterns = (
        re.compile(r"(?:\+?91[\s\-/]*)?(\d{10})"),
        re.compile(r"(?:\+?91[\s\-/]*)?(\d{5})[\s\-/]*(\d{5})"),
    )
    for pat in patterns:
        m = pat.search(s)
        if not m:
            continue
        if m.lastindex == 1:
            digits = m.group(1)
        else:
            digits = m.group(1) + m.group(2)
        if len(digits) == 10:
            return digits
    return None


def _apply_book_company_transaction_type(data: dict, ad: dict) -> None:
    """
    When INVOICE_BOOK_COMPANY_NAME is set (e.g. Satyawani): match entity role on invoice.
    Company in Bill To / client_name → Purchase. Company as supplier → Sales.
    """
    book = INVOICE_BOOK_COMPANY_NAME
    if not book:
        return
    q = book.lower()
    supplier = (data.get("supplier_name") or ad.get("supplier_name") or "").lower()
    client = (data.get("client_name") or "").lower()
    in_client = q in client
    in_supplier = q in supplier
    if in_client and not in_supplier:
        data["transaction_type"] = "Purchase"
    elif in_supplier and not in_client:
        data["transaction_type"] = "Sales"


def _fix_contact_near_pravin(data: dict, ad: dict) -> None:
    """
    When supplier_contact lists Pravin vs Paresh with numbers differing by last digit (e.g. ...62 vs ...63),
    use the 10-digit number immediately after 'Pravin' for buyer_contact_number.
    """
    text = ad.get("supplier_contact") or ad.get("supplier_phone") or ""
    if not text or not re.search(r"pravin", text, re.I):
        return
    cur = _digits_only_phone(str(data.get("buyer_contact_number") or ""))
    if len(cur) != 10:
        return
    for m in re.finditer(r"pravin", text, re.I):
        tail = text[m.end() : m.end() + 55]
        dig = "".join(c for c in tail if c.isdigit())
        if len(dig) < 10:
            continue
        pravin_num = dig[:10]
        if pravin_num == cur:
            return
        if len(pravin_num) == 10 and pravin_num[:9] == cur[:9] and pravin_num[-1] != cur[-1]:
            data["buyer_contact_number"] = pravin_num
            return



def _normalize(data: dict, raw_text: Optional[str] = None, known_client_name: Optional[str] = None) -> dict:
    """
    Post-process the raw extracted dict:
    - Pull useful fields out of additional_details into top-level
    - Resolve client_name from buyer aliases
    - Clean up numeric fields
    - Ensure all expected keys are present
    """
    if not isinstance(data, dict):
        return {}

    ad = data.get("additional_details") or {}
    if not isinstance(ad, dict):
        ad = {}
    data["additional_details"] = ad

    extracted_role: Optional[str] = None
    _maybe_swap_supplier_buyer_in_ad(data, ad)

    # ── Pull from additional_details into top-level if missing ───────────────
    if not data.get("date"):
        data["date"] = (
            ad.get("invoice_date") or ad.get("bill_date") or ad.get("date_of_invoice")
            or ad.get("billing_date") or ad.get("invoice_date_only") or ad.get("date")
        )
    if not data.get("seller_pan_number"):
        data["seller_pan_number"] = (
            ad.get("supplier_pan")
            or ad.get("seller_pan")
            or ad.get("pan_number")
        )
    if not data.get("buyer_contact_number"):
        data["buyer_contact_number"] = (
            ad.get("buyer_phone") or ad.get("bill_to_phone") or ad.get("customer_phone")
            or ad.get("buyer_contact")
        )
    if not data.get("buyer_location"):
        data["buyer_location"] = (
            ad.get("bill_to_address")
            or ad.get("ship_to_address")
            or ad.get("buyer_address")
            or ad.get("client_address")
            or ad.get("place_of_supply")
            or ad.get("supplier_address")
        )
    supplier_addr = (ad.get("supplier_address") or data.get("supplier_address") or "").strip()
    client_addr = (ad.get("client_address") or ad.get("buyer_address") or "").strip()
    if client_addr and supplier_addr and data.get("buyer_location"):
        loc = str(data.get("buyer_location") or "").strip()
        if loc and (loc == supplier_addr or supplier_addr in loc):
            data["buyer_location"] = client_addr

    buyer_phone = (ad.get("buyer_phone") or ad.get("bill_to_phone") or ad.get("customer_phone") or "").strip()
    supplier_phone = (ad.get("supplier_phone") or ad.get("supplier_contact") or "").strip()
    current_contact = str(data.get("buyer_contact_number") or "").replace(" ", "").replace("-", "").strip()
    if buyer_phone:
        buyer_clean = buyer_phone.replace(" ", "").replace("-", "").strip()
        digits = "".join(c for c in buyer_clean if c.isdigit())
        if len(digits) >= 10:
            data["buyer_contact_number"] = buyer_phone
        elif current_contact and supplier_phone:
            sup_clean = supplier_phone.replace(" ", "").replace("-", "").strip()
            if sup_clean and (current_contact == sup_clean or current_contact.endswith(sup_clean[-10:])):
                data["buyer_contact_number"] = buyer_phone

    _fix_contact_near_pravin(data, ad)

    # ── Resolve client_name from buyer aliases ────────────────────────────────
    _FALLBACK_STRINGS = {"walk-in customer", "walk in customer", "n/a", "na", "nil", "-"}
    if not data.get("client_name"):
        _BUYER_KEYS = (
            "buyer_name", "buyer_to_party", "buyer_to",
            "party_name", "bill_to", "billed_to",
            "sold_to", "ship_to", "consignee", "customer_name",
            "patient_name", "client", "receiver", "account_holder",
            "m_s", "ms",
        )
        supplier = (data.get("supplier_name") or ad.get("supplier_name") or "").lower()
        for key in _BUYER_KEYS:
            candidate = ad.get(key) or data.get(key)
            if isinstance(candidate, dict):
                candidate = candidate.get("name")
            if isinstance(candidate, str) and candidate.strip():
                val = candidate.strip()
                if val.lower() not in _FALLBACK_STRINGS and val.lower() != supplier:
                    data["client_name"] = val
                    break
        if not data.get("client_name"):
            data["client_name"] = "Walk-in Customer"

    # ── Enforce known-name similarity: pick best invoice-text match ───────────
    # Goal: client_name and seller_party_name must reflect ACTUAL invoice text,
    # not the request value. We use known_client_name only as a fuzzy anchor.
    known_client_name_clean = (known_client_name or "").strip()
    hint = known_client_name_clean
    if known_client_name_clean:

        def _acceptable_invoice_name(v: Optional[str]) -> bool:
            if not isinstance(v, str):
                return False
            s = v.strip()
            if not s:
                return False
            return _is_similar_party_name(s, known_client_name_clean)

        def _first_matching_party_name(candidates: list, h: str) -> Optional[str]:
            for c in candidates:
                if isinstance(c, str) and c.strip() and _hint_matches_party_name(h, c):
                    return c.strip()
            return None

        supplier_name_from_ad = (ad.get("supplier_name") or "").strip()

        if hint and len(hint) >= 3:
            prev_client = (data.get("client_name") or "").strip()
            ad_name_strings = _collect_ad_name_like_strings(ad)
            signoff_supplier_names = _extract_supplier_signoff_names(ad)
            sup_cands = [
                ad.get("supplier_name"),
                data.get("seller_party_name"),
                *signoff_supplier_names,
                *ad_name_strings,
            ]
            buy_cands = [
                ad.get("bill_to_party_name"),
                ad.get("bill_to_name"),
                ad.get("buyer_name"),
                data.get("buyer_party_name"),
                *ad_name_strings,
            ]
            best_sup = _best_invoice_name_for_hint(hint, sup_cands)
            best_buy = _best_invoice_name_for_hint(hint, buy_cands)

            hint_ms_sup = any(
                _hint_matches_party_name(hint, x)
                for x in (ad.get("supplier_name"), data.get("seller_party_name"))
                if x
            ) or any(
                _hint_matches_party_name(hint, x)
                for x in signoff_supplier_names
                if x
            ) or _extra_hint_matches_supplier(ad_name_strings, hint, ad, data)
            hint_ms_buy = any(
                _hint_matches_party_name(hint, x)
                for x in (
                    ad.get("bill_to_party_name"),
                    ad.get("bill_to_name"),
                    ad.get("buyer_name"),
                    data.get("buyer_party_name"),
                )
                if x
            ) or _extra_hint_matches_buyer(ad_name_strings, hint, ad, data)

            sg_top = _gstin_norm(data.get("seller_gst_number"))
            bg_top = _gstin_norm(data.get("buyer_gst_number"))
            asup = _gstin_norm(ad.get("supplier_gstin"))
            abuy = _gstin_norm(ad.get("buyer_gstin"))
            gst_sup_ok = bool(sg_top and asup and sg_top == asup)
            gst_buy_ok = bool(bg_top and abuy and bg_top == abuy)

            if hint_ms_sup and not hint_ms_buy:
                extracted_role = "sales"
            elif hint_ms_buy and not hint_ms_sup:
                extracted_role = "purchase"
            elif hint_ms_sup and hint_ms_buy:
                if gst_sup_ok and not gst_buy_ok:
                    extracted_role = "sales"
                elif gst_buy_ok and not gst_sup_ok:
                    extracted_role = "purchase"
                elif gst_sup_ok and _hint_matches_party_name(hint, str(ad.get("supplier_name") or "")):
                    extracted_role = "sales"
                elif gst_buy_ok and _hint_matches_party_name(
                    hint,
                    str(ad.get("bill_to_party_name") or ad.get("buyer_name") or ""),
                ):
                    extracted_role = "purchase"
                else:
                    extracted_role = None
            else:
                extracted_role = None

            if extracted_role == "sales":
                chosen = _first_matching_party_name(sup_cands, hint)
                data["client_name"] = (
                    best_sup
                    or chosen
                    or supplier_name_from_ad
                    or ((data.get("seller_party_name") or "").strip() or None)
                )
            elif extracted_role == "purchase":
                chosen = _first_matching_party_name(buy_cands, hint)
                data["client_name"] = best_buy or chosen
            else:
                _client_candidates = [
                    ad.get("supplier_name"),
                    ad.get("bill_to_party_name"),
                    ad.get("bill_to_name"),
                    ad.get("buyer_name"),
                    ad.get("buyer_to_party"),
                    data.get("buyer_party_name"),
                    data.get("seller_party_name"),
                    data.get("client_name"),
                ]
                selected_client = next(
                    (
                        c.strip()
                        for c in _client_candidates
                        if isinstance(c, str) and c.strip() and _acceptable_invoice_name(c)
                    ),
                    None,
                )
                data["client_name"] = selected_client
                if not (data.get("client_name") or "").strip():
                    if best_sup and not best_buy:
                        data["client_name"] = best_sup
                    elif best_buy and not best_sup:
                        data["client_name"] = best_buy
                    elif best_sup and best_buy:
                        if gst_sup_ok and not gst_buy_ok:
                            data["client_name"] = best_sup
                        elif gst_buy_ok and not gst_sup_ok:
                            data["client_name"] = best_buy
                        else:
                            data["client_name"] = max(best_sup, best_buy, key=len)
                    elif prev_client and prev_client.lower() not in _FALLBACK_STRINGS:
                        data["client_name"] = prev_client

            cur_cn = (data.get("client_name") or "").strip()
            if cur_cn and _normalize_for_text_match(cur_cn) == _normalize_for_text_match(hint):
                alt = (
                    (best_sup if extracted_role == "sales" else None)
                    or (best_buy if extracted_role == "purchase" else None)
                    or best_sup
                    or best_buy
                )
                if alt and len(alt) > len(cur_cn):
                    data["client_name"] = alt

            if not (data.get("client_name") or "").strip():
                data["client_name"] = (
                    best_sup
                    or best_buy
                    or (
                        prev_client
                        if prev_client and prev_client.lower() not in _FALLBACK_STRINGS
                        else None
                    )
                )

            hint_long = len(hint) >= 3
            model_seller_nm = (data.get("seller_party_name") or "").strip()
            hint_ok_sup = _hint_matches_party_name(hint, supplier_name_from_ad)
            model_agrees_sup = _parties_match_normalized(
                supplier_name_from_ad, model_seller_nm
            )
            anchor_from_ad = bool(
                supplier_name_from_ad
                and (
                    (not hint_long)
                    or hint_ok_sup
                    or (
                        _seller_gst_aligns_with_ad_supplier(data, ad)
                        and model_agrees_sup
                    )
                )
            )
            if anchor_from_ad:
                data["seller_party_name"] = supplier_name_from_ad
            elif not data.get("seller_party_name") and extracted_role != "sales":
                data["seller_party_name"] = None
        else:
            _client_candidates = [
                ad.get("supplier_name"),
                ad.get("bill_to_party_name"),
                ad.get("bill_to_name"),
                ad.get("buyer_name"),
                ad.get("buyer_to_party"),
                data.get("buyer_party_name"),
                data.get("seller_party_name"),
                data.get("client_name"),
            ]
            selected_client = next(
                (
                    c.strip()
                    for c in _client_candidates
                    if isinstance(c, str) and c.strip() and _acceptable_invoice_name(c)
                ),
                None,
            )
            data["client_name"] = selected_client

            if supplier_name_from_ad:
                data["seller_party_name"] = supplier_name_from_ad
            elif not data.get("seller_party_name"):
                data["seller_party_name"] = None

    # ── Clean up: remove "Walk-in Customer" from additional_details fields ────
    for field in ("buyer_name", "buyer_address"):
        if isinstance(ad.get(field), str) and ad[field].lower() in _FALLBACK_STRINGS:
            ad[field] = None

    # ── Pull cgst/sgst/igst/gst from gst_details when top-level is null ──────
    gst_details = ad.get("gst_details") if isinstance(ad.get("gst_details"), dict) else {}
    if gst_details:
        if data.get("cgst") is None and gst_details.get("cgst_amount") is not None:
            data["cgst"] = _safe_float(gst_details.get("cgst_amount"))
        if data.get("sgst") is None and gst_details.get("sgst_amount") is not None:
            data["sgst"] = _safe_float(gst_details.get("sgst_amount"))
        if data.get("igst") is None and gst_details.get("igst_amount") is not None:
            data["igst"] = _safe_float(gst_details.get("igst_amount"))
        if data.get("gst") is None and gst_details.get("total_gst") is not None:
            data["gst"] = _safe_float(gst_details.get("total_gst"))

    # ── Grand total fallback ──────────────────────────────────────────────────
    _TOTAL_ALIASES = [
        "grand_total", "invoice_total", "total_amount",
        "net_payable", "total_payable", "payable_amount",
        "amount_with_gst",
        "total_amount_after_tax", "total_after_tax", "grand_total_after_tax",
        "net_amount_payable", "amount_due", "total_due", "total_invoice_amount",
    ]
    if not data.get("total"):
        for alias in _TOTAL_ALIASES:
            v = data.get(alias) or ad.get(alias)
            if v:
                data["total"] = v
                break

    # ── Amount (subtotal before tax) fallback ─────────────────────────────────
    if not data.get("amount"):
        for alias in ("taxable_amount", "subtotal", "base_amount", "net_amount"):
            v = data.get(alias) or ad.get(alias)
            if v:
                data["amount"] = v
                break

    # ── quantity / rate from line_items when top-level is null ───────────────
    line_items = ad.get("line_items") if isinstance(ad.get("line_items"), list) else []
    if line_items and isinstance(line_items[0], dict):
        first = line_items[0]
        if data.get("quantity") is None and first.get("quantity") is not None:
            data["quantity"] = _safe_float(first.get("quantity"))
        if data.get("rate") is None and first.get("rate") is not None:
            data["rate"] = _safe_float(first.get("rate") or first.get("unit_price"))
        if data.get("amount") is None and first.get("amount") is not None:
            data["amount"] = _safe_float(first.get("amount") or first.get("total"))

    # ── balance_amount fallback ───────────────────────────────────────────────
    if not data.get("balance_amount"):
        v = ad.get("balance_due") or data.get("balance_due")
        if v is not None:
            data["balance_amount"] = v

    # ── Compute gst if missing but cgst/sgst present ──────────────────────────
    if not data.get("gst"):
        cgst = _safe_float(data.get("cgst"))
        sgst = _safe_float(data.get("sgst"))
        igst = _safe_float(data.get("igst"))
        if igst:
            data["gst"] = igst
        elif cgst or sgst:
            data["gst"] = (cgst or 0.0) + (sgst or 0.0)

    # ── Prefer cgst+sgst over model gst when both present ────────────────────
    cgst = _safe_float(data.get("cgst"))
    sgst = _safe_float(data.get("sgst"))
    if cgst is not None and sgst is not None and (cgst != 0 or sgst != 0):
        data["gst"] = round(cgst + sgst, 2)

    # ── Sanity-check: gst must be less than total ─────────────────────────────
    total_f  = _safe_float(data.get("total"))
    gst_f    = _safe_float(data.get("gst"))
    amount_f = _safe_float(data.get("amount"))

    if gst_f and total_f and gst_f >= total_f * 0.9:
        cgst = _safe_float(data.get("cgst"))
        sgst = _safe_float(data.get("sgst"))
        igst = _safe_float(data.get("igst"))
        recomputed = None
        if igst and igst < total_f * 0.9:
            recomputed = igst
        elif (cgst or sgst):
            s = (cgst or 0.0) + (sgst or 0.0)
            if s < total_f * 0.9:
                recomputed = s
        if recomputed is not None:
            data["gst"] = recomputed
            gst_f = recomputed
        else:
            data["gst"] = None
            gst_f = None

    _reconcile_amount_total_when_equal(data, ad)

    total_f = _safe_float(data.get("total"))
    gst_f = _safe_float(data.get("gst"))
    amount_f = _safe_float(data.get("amount"))

    if not data.get("amount") and total_f and gst_f:
        data["amount"] = round(total_f - gst_f, 2)

    # ── amount_paid: default to corrected total; fix paid-in-full vs taxable confusion ──
    total_f = _safe_float(data.get("total"))
    amount_f = _safe_float(data.get("amount"))
    if not data.get("amount_paid") and total_f:
        data["amount_paid"] = total_f
    ap_f = _safe_float(data.get("amount_paid"))
    bal_f = _safe_float(data.get("balance_amount"))
    if (
        total_f
        and amount_f is not None
        and ap_f is not None
        and _money_close(ap_f, amount_f)
        and total_f > ap_f + 0.02
        and (bal_f is None or bal_f <= 0.02)
    ):
        data["amount_paid"] = total_f

    # ── Fix balance_amount ────────────────────────────────────────────────────
    total_f = _safe_float(data.get("total"))
    amount_paid_f = _safe_float(data.get("amount_paid"))
    balance_f = _safe_float(data.get("balance_amount"))
    if total_f and amount_paid_f and balance_f and abs(balance_f - total_f) < 0.01:
        data["balance_amount"] = round(max(0.0, total_f - amount_paid_f), 2)

    # ── invoice_number + product_name quality checks ──────────────────────────
    quality_flags: list[str] = []
    candidate_inv = (
        data.get("invoice_number")
        or ad.get("invoice_number")
        or data.get("invoiceNumber")
    )
    ocr_extracted = _extract_invoice_number_from_text(raw_text)
    if not candidate_inv:
        candidate_inv = ocr_extracted
    clean_inv, inv_conf, inv_flag = _validate_invoice_number(candidate_inv, raw_text)
    if not clean_inv and ocr_extracted:
        clean2, conf2, flag2 = _validate_invoice_number(ocr_extracted, raw_text)
        if clean2:
            clean_inv, inv_conf, inv_flag = clean2, conf2, flag2
    if clean_inv:
        ad["invoice_number"] = clean_inv
    else:
        ad.pop("invoice_number", None)
        ad.pop("invoiceNumber", None)
    if inv_flag:
        quality_flags.append(inv_flag)
    ad["invoice_number_confidence"] = inv_conf

    product_name = _resolve_product_name(data, ad)
    if not product_name:
        product_name = ad.get("product_name") or ad.get("description")
        if isinstance(product_name, str):
            product_name = product_name.strip()[:500]
        else:
            product_name = None
    if not product_name:
        product_name = _extract_product_name_from_text(raw_text)
    clean_product, product_conf, product_flag = _validate_product_name(product_name, raw_text)
    data["product_name"] = clean_product
    ad["product_name_confidence"] = product_conf
    if product_flag:
        quality_flags.append(product_flag)
    if quality_flags:
        ad["quality_flags"] = quality_flags
    elif "quality_flags" in ad:
        ad.pop("quality_flags", None)

    # ── gst: if model put GSTIN in gst field, clear it ───────────────────────
    gst_val = data.get("gst")
    if isinstance(gst_val, str) and gst_val.strip():
        s = gst_val.strip()
        if len(s) >= 12 and len(s) <= 16 and s[:2].isdigit() and not s.replace(".", "").replace(",", "").replace(" ", "").isdigit():
            data["gst"] = None
    if not data.get("gst"):
        cgst = _safe_float(data.get("cgst"))
        sgst = _safe_float(data.get("sgst"))
        igst = _safe_float(data.get("igst"))
        if igst:
            data["gst"] = igst
        elif cgst or sgst:
            data["gst"] = (cgst or 0.0) + (sgst or 0.0)

    # ── Derive missing gst from total and amount ──────────────────────────────
    amount_f = _safe_float(data.get("amount"))
    total_f  = _safe_float(data.get("total"))
    gst_f    = _safe_float(data.get("gst"))

    if not gst_f and total_f and amount_f and total_f >= amount_f:
        gst_f = round(total_f - amount_f, 2)
        data["gst"] = gst_f
        if not data.get("igst") and not data.get("cgst") and not data.get("sgst"):
            data["cgst"] = round(gst_f / 2, 2)
            data["sgst"] = round(gst_f / 2, 2)
            data["igst"] = 0.0

    # ── Coerce industry to enum values ────────────────────────────────────────
    from app.schemas.invoice import _coerce_industry
    industry_raw = data.get("industry") or ad.get("industry")
    data["industry"] = _coerce_industry(industry_raw)

    # ── invoice_date: parse any date format to YYYY-MM-DD ────────────────────
    from app.models.invoice import _parse_date
    raw_date = data.get("date") or ad.get("invoice_date") or ad.get("date")
    invoice_date = _parse_date(raw_date) if raw_date else None

    # ── category / sub_category ───────────────────────────────────────────────
    category = data.get("category") or ad.get("category")
    sub_category = data.get("sub_category") or ad.get("sub_category") or data.get("subcategory") or ad.get("subcategory")
    if isinstance(category, str):
        category = category.strip()[:255] or None
    if isinstance(sub_category, str):
        sub_category = sub_category.strip()[:255] or None

    # ── round_off ─────────────────────────────────────────────────────────────
    round_off = _safe_float(data.get("round_off") or ad.get("round_off") or ad.get("rounding_off") or ad.get("rounding"))
    if round_off is not None:
        ad["round_off"] = round_off

    # ── Fix vehicle_number vs transporter_gstin ───────────────────────────────
    for key in ("vehicle_number", "motor_vehicle_no"):
        vn = ad.get(key)
        if isinstance(vn, str) and vn.strip():
            vn_clean = vn.strip().upper()
            if len(vn_clean) >= 14 and vn_clean[:2].isdigit() and any(c.isalpha() for c in vn_clean[2:6]):
                ad["transporter_gstin"] = vn.strip()
                ad[key] = None

    # ── Fix transporter_gstin: must NOT be buyer or supplier GSTIN ───────────
    tg = ad.get("transporter_gstin")
    buyer_gstin = (ad.get("buyer_gstin") or ad.get("client_gstin") or "").strip().upper()
    supplier_gstin = (ad.get("supplier_gstin") or data.get("supplier_gstin") or "").strip().upper()
    if isinstance(tg, str) and tg.strip():
        tg_clean = tg.strip().upper()
        if buyer_gstin and tg_clean == buyer_gstin:
            ad["transporter_gstin"] = None
        elif supplier_gstin and tg_clean == supplier_gstin:
            ad["transporter_gstin"] = None

    # ── Fix eway_bill_number: reject GSTINs and invoice-number patterns ───────
    for ebn_key in ("eway_bill_number", "e_way_bill_number", "eway_bill", "ewb_no"):
        ebn = ad.get(ebn_key)
        if isinstance(ebn, str) and ebn.strip():
            ebn_clean = ebn.strip().upper()
            if re.fullmatch(r"\d{2}[A-Z]{5}\d{4}[A-Z]\d[Z][A-Z0-9]", ebn_clean):
                ad[ebn_key] = None
            elif "/" in ebn_clean:
                ad[ebn_key] = None

    # ── seller_gst_number: prefer top-level, fall back to additional_details ─
    seller_gst_number = (
        data.get("seller_gst_number")
        or ad.get("supplier_gstin")
        or ad.get("gstin")
        or ad.get("gst_number")
        or ad.get("supplier_gst_number")
    )
    if isinstance(seller_gst_number, str):
        seller_gst_number = seller_gst_number.strip() or None

    # ── seller_pan_number: validate and derive from GSTIN if needed ───────────
    seller_pan_number = data.get("seller_pan_number")
    if isinstance(seller_pan_number, str):
        seller_pan_number = seller_pan_number.strip().upper() or None

    if isinstance(seller_pan_number, str) and len(seller_pan_number) == 15:
        seller_pan_number = _extract_pan_from_gstin(seller_pan_number)

    if isinstance(seller_pan_number, str) and seller_pan_number:
        if not re.fullmatch(r"[A-Z]{5}[0-9]{4}[A-Z]", seller_pan_number):
            seller_pan_number = None

    if seller_gst_number:
        derived_pan = _extract_pan_from_gstin(seller_gst_number)
        if derived_pan and seller_pan_number != derived_pan:
            seller_pan_number = derived_pan
            data["seller_pan_number"] = derived_pan
            if isinstance(ad, dict):
                ad["supplier_pan"] = derived_pan

    # ── Buyer/Seller party fields ─────────────────────────────────────────────
    # seller_party_name: always anchor to ad.supplier_name (invoice header text)
    # This is the most reliable source — never polluted by known_client_name
    seller_party_name = (
        (data.get("seller_party_name") or "").strip()
        or (data.get("supplier_name") or "").strip()
        or (ad.get("supplier_name") or "").strip()
        or None
    )

    buyer_party_name = data.get("buyer_party_name")
    bill_to_party_name = (
        ad.get("bill_to_party_name")
        or ad.get("bill_to_name")
        or ad.get("buyer_name")
        or ad.get("buyer_party")
        or ad.get("bill_to_party")
    )
    if isinstance(bill_to_party_name, str):
        bill_to_party_name = bill_to_party_name.strip() or None
    if not buyer_party_name:
        # Determine if known client is the supplier
        client_nm = data.get("client_name") or ""
        if known_client_name_clean and len(known_client_name_clean.strip()) >= 3:
            supplier_is_known_client = _hint_matches_party_name(
                known_client_name_clean, seller_party_name or ""
            ) or _parties_match_normalized(client_nm, seller_party_name or "")
        else:
            known_for_party = client_nm.strip().lower()
            seller_norm_for_party = (seller_party_name or "").lower()
            supplier_is_known_client = bool(
                known_for_party
                and seller_norm_for_party
                and (
                    known_for_party == seller_norm_for_party
                    or known_for_party in seller_norm_for_party
                    or seller_norm_for_party in known_for_party
                )
            )
        if not supplier_is_known_client:
            buyer_party_name = data.get("client_name")
        else:
            buyer_party_name = bill_to_party_name

    buyer_contact_number = data.get("buyer_contact_number")
    seller_contact_number = (
        ad.get("supplier_phone")
        or ad.get("supplier_contact")
        or data.get("seller_contact_number")
        or ad.get("seller_phone")
    )

    buyer_location = data.get("buyer_location")
    seller_location = data.get("seller_location") or ad.get("supplier_address") or data.get("supplier_address")

    buyer_gst_number = (
        data.get("buyer_gst_number")
        or ad.get("buyer_gst_number")
        or ad.get("buyer_gstin")
        or data.get("buyer_gstin")
    )
    if isinstance(buyer_gst_number, str):
        buyer_gst_number = buyer_gst_number.strip() or None

    # ── buyer_pan_number: validate and derive from GSTIN if needed ────────────
    buyer_pan_number = (
        data.get("buyer_pan_number")
        or ad.get("buyer_pan_number")
        or ad.get("buyer_pan")
        or ad.get("buyer_pancard")
        or data.get("buyer_pan")
    )
    if isinstance(buyer_pan_number, str):
        buyer_pan_number = buyer_pan_number.strip().upper() or None

    if isinstance(buyer_pan_number, str) and len(buyer_pan_number) == 15:
        buyer_pan_number = _extract_pan_from_gstin(buyer_pan_number)

    if not buyer_pan_number and buyer_gst_number:
        buyer_pan_number = _extract_pan_from_gstin(buyer_gst_number)

    if isinstance(buyer_pan_number, str) and buyer_pan_number:
        if not re.fullmatch(r"[A-Z]{5}[0-9]{4}[A-Z]", buyer_pan_number):
            buyer_pan_number = None

    # ── Realign swapped buyer/seller roles ────────────────────────────────────
    supplier_from_ad_name  = (ad.get("supplier_name") or "").strip()
    supplier_from_ad_gstin = (ad.get("supplier_gstin") or "").strip()
    client_for_match = data.get("client_name") or ""
    known = client_for_match.strip().lower()

    supplier_name_norm  = supplier_from_ad_name.lower()
    supplier_gstin_norm = supplier_from_ad_gstin.lower()

    supplier_matched = _parties_match_normalized(client_for_match, supplier_from_ad_name)
    if (
        not supplier_matched
        and known_client_name_clean
        and len(known_client_name_clean.strip()) >= 3
        and supplier_name_norm
    ):
        supplier_matched = _hint_matches_party_name(known_client_name_clean, supplier_from_ad_name)

    seller_gst_norm = (seller_gst_number or "").strip().lower()
    buyer_gst_norm  = (buyer_gst_number or "").strip().lower()

    seller_gst_matches = bool(
        supplier_gstin_norm
        and seller_gst_norm
        and (supplier_gstin_norm == seller_gst_norm or supplier_gstin_norm in seller_gst_norm or seller_gst_norm in supplier_gstin_norm)
    )
    buyer_gst_matches = bool(
        supplier_gstin_norm
        and buyer_gst_norm
        and (supplier_gstin_norm == buyer_gst_norm or supplier_gstin_norm in buyer_gst_norm or buyer_gst_norm in supplier_gstin_norm)
    )

    gst_swapped = supplier_matched and supplier_gstin_norm and buyer_gst_matches and not seller_gst_matches

    buyer_name_norm  = (buyer_party_name or "").strip().lower()
    seller_name_norm = (seller_party_name or "").strip().lower()
    buyer_name_matches = bool(
        supplier_name_norm and buyer_name_norm and (supplier_name_norm == buyer_name_norm or supplier_name_norm in buyer_name_norm or buyer_name_norm in supplier_name_norm)
    )
    seller_name_matches = bool(
        supplier_name_norm and seller_name_norm and (supplier_name_norm == seller_name_norm or supplier_name_norm in seller_name_norm or seller_name_norm in supplier_name_norm)
    )
    name_swapped = supplier_matched and not gst_swapped and buyer_name_matches and not seller_name_matches

    roles_swapped = gst_swapped or name_swapped
    if roles_swapped:
        buyer_party_name,     seller_party_name    = seller_party_name,    buyer_party_name
        buyer_contact_number, seller_contact_number = seller_contact_number, buyer_contact_number
        buyer_pan_number,     seller_pan_number    = seller_pan_number,    buyer_pan_number
        buyer_gst_number,     seller_gst_number    = seller_gst_number,    buyer_gst_number
        buyer_location,       seller_location      = seller_location,      buyer_location
        if supplier_from_ad_name:
            seller_party_name = supplier_from_ad_name
    else:
        seller_name_norm = (seller_party_name or "").strip().lower()
        seller_matches_supplier = bool(
            supplier_name_norm
            and seller_name_norm
            and (
                supplier_name_norm == seller_name_norm
                or supplier_name_norm in seller_name_norm
                or seller_name_norm in supplier_name_norm
            )
        )
        if supplier_matched and supplier_name_norm and not seller_matches_supplier:
            buyer_party_name,     seller_party_name    = seller_party_name,    buyer_party_name
            buyer_contact_number, seller_contact_number = seller_contact_number, buyer_contact_number
            buyer_pan_number,     seller_pan_number    = seller_pan_number,    buyer_pan_number
            buyer_gst_number,     seller_gst_number    = seller_gst_number,    buyer_gst_number
            buyer_location,       seller_location      = seller_location,      buyer_location
            if supplier_from_ad_name:
                seller_party_name = supplier_from_ad_name

    # ── Anchor seller_party_name to ad.supplier_name when consistent ─────────
    if supplier_from_ad_name:
        hint_long = len((known_client_name_clean or "").strip()) >= 3
        hint_ok = hint_long and _hint_matches_party_name(
            known_client_name_clean, supplier_from_ad_name
        )
        model_seller_nm = (data.get("seller_party_name") or "").strip()
        model_agrees_sup = _parties_match_normalized(
            supplier_from_ad_name, model_seller_nm
        )
        gst_ok = _seller_gst_aligns_with_ad_supplier(data, ad)
        no_hint = not (known_client_name_clean or "").strip()
        if no_hint or hint_ok or (gst_ok and (not hint_long or model_agrees_sup)):
            seller_party_name = supplier_from_ad_name

    # If role is Sales and footer/signatory names match hint, they are often
    # the true issuer even when ad.supplier_name was mis-assigned to Bill To.
    if extracted_role == "sales" and len((known_client_name_clean or "").strip()) >= 3:
        signoff_best = _best_invoice_name_for_hint(
            known_client_name_clean,
            _extract_supplier_signoff_names(ad),
        )
        if signoff_best:
            seller_party_name = signoff_best

    data["client_name"] = _clean_party_display_name(data.get("client_name")) or data.get("client_name")
    data["buyer_party_name"]  = buyer_party_name
    data["seller_party_name"] = seller_party_name

    # ── transaction_type ──────────────────────────────────────────────────────
    known = (data.get("client_name") or "").strip().lower()
    buyer  = (data.get("buyer_party_name") or "").strip().lower()
    seller = (data.get("seller_party_name") or "").strip().lower()
    supplier_from_ad_name_lc = (ad.get("supplier_name") or "").strip().lower()

    if extracted_role == "sales":
        data["transaction_type"] = "Sales"
    elif extracted_role == "purchase":
        data["transaction_type"] = "Purchase"
    elif _parties_match_normalized(data.get("client_name"), ad.get("supplier_name")):
        data["transaction_type"] = "Sales"
    elif _parties_match_normalized(data.get("client_name"), data.get("seller_party_name")):
        data["transaction_type"] = "Sales"
    elif _parties_match_normalized(data.get("client_name"), data.get("buyer_party_name")):
        data["transaction_type"] = "Purchase"
    elif known and supplier_from_ad_name_lc and (
        known == supplier_from_ad_name_lc
        or known in supplier_from_ad_name_lc
        or supplier_from_ad_name_lc in known
    ):
        data["transaction_type"] = "Sales"
    elif known and seller and (known == seller or known in seller or seller in known):
        data["transaction_type"] = "Sales"
    elif known and buyer and (known == buyer or known in buyer or buyer in known):
        data["transaction_type"] = "Purchase"
    elif len((known_client_name_clean or "").strip()) >= 3:
        hint_tt = known_client_name_clean.strip()
        ad_strings_tt = _collect_ad_name_like_strings(ad)
        signoff_supplier_tt = _extract_supplier_signoff_names(ad)
        sup_from_ad = [
            s
            for s in ad_strings_tt
            if _signoff_supplier_bias(s) or _matches_known_supplier_name(s, ad, data)
        ]
        buy_from_ad = [
            s for s in ad_strings_tt if _matches_known_buyer_name(s, ad, data)
        ]
        sup_names_tt = (
            ad.get("supplier_name"),
            data.get("seller_party_name"),
            seller_party_name,
            *signoff_supplier_tt,
            *sup_from_ad,
        )
        buy_names_tt = (
            ad.get("bill_to_party_name"),
            ad.get("bill_to_name"),
            ad.get("buyer_name"),
            data.get("buyer_party_name"),
            buyer_party_name,
            *buy_from_ad,
        )
        if any(
            _hint_matches_party_name(hint_tt, x)
            for x in sup_names_tt
            if x
        ):
            data["transaction_type"] = "Sales"
        elif any(
            _hint_matches_party_name(hint_tt, x)
            for x in buy_names_tt
            if x
        ):
            data["transaction_type"] = "Purchase"
        else:
            data["transaction_type"] = "Purchase"
    else:
        data["transaction_type"] = "Purchase"

    # GSTIN tie-break
    sg_ad     = (ad.get("supplier_gstin") or "").strip().upper()
    sg_seller = (data.get("seller_gst_number") or "").strip().upper()
    sg_buyer  = (data.get("buyer_gst_number") or "").strip().upper()
    if sg_ad and sg_seller and sg_ad == sg_seller and sg_buyer and sg_ad != sg_buyer:
        if known and supplier_from_ad_name_lc and (
            known == supplier_from_ad_name_lc
            or known in supplier_from_ad_name_lc
            or supplier_from_ad_name_lc in known
        ):
            data["transaction_type"] = "Sales"
        elif known and buyer and (known == buyer or known in buyer or buyer in known):
            data["transaction_type"] = "Purchase"

    _apply_book_company_transaction_type(data, ad)
    if data.get("transaction_type") not in ("Sales", "Purchase"):
        data["transaction_type"] = "Purchase"

    if data.get("transaction_type") == "Purchase":
        should_sync_buyer = (not known_client_name_clean) or (extracted_role == "purchase")
        if should_sync_buyer:
            client_name_value = data.get("client_name")
            if isinstance(client_name_value, str) and client_name_value.strip():
                buyer_party_name = client_name_value.strip()
                data["buyer_party_name"] = buyer_party_name

    # ── Strict phone validation ───────────────────────────────────────────────
    buyer_contact_number  = _extract_valid_indian_phone(buyer_contact_number)
    seller_contact_number = _extract_valid_indian_phone(seller_contact_number)

    bill_to_phone = (
        ad.get("buyer_phone")
        or ad.get("bill_to_phone")
        or ad.get("customer_phone")
        or ad.get("buyer_contact")
    )
    bill_to_phone_digits = "".join(c for c in str(bill_to_phone or "") if c.isdigit())
    if data.get("transaction_type") == "Purchase" and len(bill_to_phone_digits) < 10:
        if buyer_contact_number and seller_contact_number and buyer_contact_number == seller_contact_number:
            buyer_contact_number = None

    # ── Auto-correct OCR misreads in all GSTINs ───────────────────────────────
    buyer_gst_number  = _fix_gstin_ocr(buyer_gst_number)
    seller_gst_number = _fix_gstin_ocr(seller_gst_number)
    if ad.get("supplier_gstin"):
        ad["supplier_gstin"]    = _fix_gstin_ocr(ad["supplier_gstin"])
    if ad.get("buyer_gstin"):
        ad["buyer_gstin"]       = _fix_gstin_ocr(ad["buyer_gstin"])
    if ad.get("transporter_gstin"):
        ad["transporter_gstin"] = _fix_gstin_ocr(ad["transporter_gstin"])

    # ── Re-derive PANs after GSTIN OCR fix ───────────────────────────────────
    if not seller_pan_number and seller_gst_number:
        seller_pan_number = _extract_pan_from_gstin(seller_gst_number)
    if not buyer_pan_number and buyer_gst_number:
        buyer_pan_number = _extract_pan_from_gstin(buyer_gst_number)

    buy_only = (
        ad.get("bill_to_address")
        or ad.get("ship_to_address")
        or ad.get("buyer_address")
        or ad.get("client_address")
    )
    if isinstance(buy_only, str) and buy_only.strip():
        buyer_location = buy_only.strip()
    sup_addr = (ad.get("supplier_address") or data.get("supplier_address") or "").strip()
    if sup_addr:
        seller_location = sup_addr

    # If we inferred Sales from footer/signoff issuer text but seller location is
    # identical to buyer location, it's usually a mis-assigned supplier_address.
    if extracted_role == "sales":
        signoff_names = _extract_supplier_signoff_names(ad)
        if signoff_names:
            b_loc = _normalize_for_text_match(str(buyer_location or ""))
            s_loc = _normalize_for_text_match(str(seller_location or ""))
            if b_loc and s_loc and (b_loc == s_loc or b_loc in s_loc or s_loc in b_loc):
                seller_location = None

    data["buyer_contact_number"]  = buyer_contact_number
    data["seller_contact_number"] = seller_contact_number
    data["buyer_pan_number"]      = buyer_pan_number
    data["seller_pan_number"]     = seller_pan_number
    data["buyer_gst_number"]      = buyer_gst_number
    data["seller_gst_number"]     = seller_gst_number
    data["buyer_location"]        = buyer_location
    data["seller_location"]       = seller_location

    _apply_bill_total_amount_check(data, ad)

    # ── Build final dict with all expected keys ───────────────────────────────
    return {
        "client_name":           data.get("client_name"),
        "product_name":          data.get("product_name"),
        "buyer_party_name":      data.get("buyer_party_name"),
        "seller_party_name":     data.get("seller_party_name"),
        "industry":              data.get("industry"),
        "category":              category,
        "sub_category":          sub_category,
        "transaction_type":      data.get("transaction_type") or data.get("type_of_bill"),
        "date":                  data.get("date"),
        "invoice_date":          invoice_date,
        "buyer_contact_number":  data.get("buyer_contact_number"),
        "seller_contact_number": data.get("seller_contact_number"),
        "buyer_pan_number":      data.get("buyer_pan_number"),
        "seller_pan_number":     data.get("seller_pan_number"),
        "buyer_gst_number":      data.get("buyer_gst_number"),
        "seller_gst_number":     data.get("seller_gst_number"),
        "buyer_location":        data.get("buyer_location"),
        "seller_location":       data.get("seller_location"),
        "gst":                   _safe_float(data.get("gst")),
        "cgst":                  _safe_float(data.get("cgst") or 0.0),
        "sgst":                  _safe_float(data.get("sgst") or 0.0),
        "igst":                  _safe_float(data.get("igst") or 0.0),
        "total":                 _safe_float(data.get("total")),
        "quantity":              _safe_float(data.get("quantity")),
        "rate":                  _safe_float(data.get("rate")),
        "amount":                _safe_float(data.get("amount")),
        "amount_paid":           _safe_float(data.get("amount_paid")),
        "balance_amount":        _safe_float(data.get("balance_amount") or 0.0),
        "payment_mode":          _resolve_payment_mode(
            data.get("payment_mode")
            or ad.get("payment_mode")
            or ad.get("mode")
            or ad.get("payment_method")
            or ad.get("mode_of_payment")
            or ad.get("paid_by")
            or ad.get("payment_type"),
            amount_paid=_safe_float(data.get("amount_paid")),
            balance=_safe_float(data.get("balance_amount")),
        ),
        "round_off":             round_off,
        "additional_details":    ad if ad else None,
    }


def _extract_key_fields_fallback(b64_images: list[str], raw_text: Optional[str] = None, is_multi_page: bool = False) -> dict:
    """
    Focused second-pass extraction for key fields when first pass is low confidence.
    Keeps payload tiny to reduce truncation risk.
    """
    prompt = "Extract ONLY these fields from invoice image and return strict JSON only:\n"
    if is_multi_page:
        prompt += "{\n  \"invoices\": [\n    {\n      \"invoice_number\": null,\n      \"product_name\": null,\n      \"line_items\": []\n    }\n  ]\n}\n"
    else:
        prompt += "{\n  \"invoice_number\": null,\n  \"product_name\": null,\n  \"line_items\": []\n}\n"
        
    prompt += (
        "Rules:\n"
        "- invoice_number: exact value printed near labels Invoice No/Invoice Number/Bill No. Do not invent values.\n"
        "- product_name: first valid item name from product/description/particulars table.\n"
        "- line_items: include at least first item with product_name if visible.\n"
        "- If not visible, keep null/empty.\n"
    )
    if raw_text and raw_text.strip():
        # Pass more text context for multi-page
        prompt = (
            "Use this OCR text plus image:\n"
            f"{raw_text[:20000]}\n\n"
        ) + prompt
    print(f"[extraction] Fallback prompt:\n{prompt}")
    logger.info(f"[extraction] Fallback prompt:\n{prompt}")
    raw = _call_vision_llm(b64_images, prompt)
    return _parse_json(raw)


def _needs_key_field_retry(out: dict) -> bool:
    ad = (out or {}).get("additional_details") or {}
    if not isinstance(ad, dict):
        return True
    inv_conf = ad.get("invoice_number_confidence")
    prod_conf = ad.get("product_name_confidence")
    return (inv_conf == "low") or (prod_conf == "low")


def _merge_key_fields(
    primary: dict,
    fallback: dict,
    raw_text: Optional[str] = None,
    known_client_name: Optional[str] = None,
) -> dict:
    """
    Merge fallback key fields into primary extraction and re-normalize once.
    """
    merged = dict(primary or {})
    ad = merged.get("additional_details")
    if not isinstance(ad, dict):
        ad = {}

    fb_ad = (fallback or {}).get("additional_details")
    if not isinstance(fb_ad, dict):
        fb_ad = {}

    fb_inv = fb_ad.get("invoice_number") or fallback.get("invoice_number")
    if fb_inv and not ad.get("invoice_number"):
        fb_inv_conf = fb_ad.get("invoice_number_confidence")
        allow_merge = False
        if fb_inv_conf == "high":
            allow_merge = True
        elif fb_inv_conf is None:
            _, vconf, _ = _validate_invoice_number(fb_inv, raw_text)
            allow_merge = vconf in ("high", "medium")
        if allow_merge:
            ad["invoice_number"] = fb_inv

    fb_product = fallback.get("product_name")
    if not fb_product:
        fb_items = fb_ad.get("line_items") if isinstance(fb_ad.get("line_items"), list) else []
        if fb_items and isinstance(fb_items[0], dict):
            fb_product = fb_items[0].get("product_name") or fb_items[0].get("description")
    if fb_product and not merged.get("product_name"):
        merged["product_name"] = fb_product

    if isinstance(fb_ad.get("line_items"), list) and fb_ad.get("line_items") and not ad.get("line_items"):
        ad["line_items"] = fb_ad.get("line_items")
    elif isinstance(fallback.get("line_items"), list) and fallback.get("line_items") and not ad.get("line_items"):
        ad["line_items"] = fallback.get("line_items")

    merged["additional_details"] = ad
    return _normalize(merged, raw_text=raw_text, known_client_name=known_client_name)


# ── public API ────────────────────────────────────────────────────────────────

def extract_from_pdf_all_pages(file_path: str, known_client_name_hint: Optional[str] = None) -> list[dict]:
    """
    Processes all pages of a PDF in a single LLM call.
    Dynamically maps multi-page inputs to an array of output invoices.
    """
    pages = _pdf_to_pages(file_path)
    if not pages:
        raise ValueError("PDF has no pages")
        
    if len(pages) > 10:
        raise ValueError(f"PDF exceeds maximum allowed pages (10). Uploaded: {len(pages)}")

    b64_images = []
    combined_raw_text = []
    for _, (img, raw_text) in enumerate(pages):
        b64_images.append(_pil_to_b64_resize(img))
        if raw_text and raw_text.strip():
            combined_raw_text.append(raw_text.strip())
            
    combined_text_str = "\\n\\n--- NEXT PAGE ---\\n\\n".join(combined_raw_text)
    
    prompt = _build_prompt(combined_text_str or None, known_client_name=known_client_name_hint, is_multi_page=True)
    print(f"[extraction] PDF multi-page combined prompt:\n{prompt}")
    logger.info(f"[extraction] PDF multi-page combined prompt:\n{prompt}")
    
    try:
        raw = _call_vision_llm(b64_images, prompt)
    except Exception as e:
        raise RuntimeError(f"vLLM request failed: {e}") from e

    if not (raw and raw.strip()):
        print("[extraction] vLLM empty — retrying once")
        logger.info("[extraction] vLLM empty — retrying once")
        raw = _call_vision_llm(b64_images, prompt)
        
    parsed = _parse_json(raw) if (raw and raw.strip()) else {}
    invoices = parsed.get("invoices", []) if isinstance(parsed, dict) else []
    
    # Fallback to single if model failed to return an array
    if not invoices and isinstance(parsed, dict) and "client_name" in parsed:
        invoices = [parsed]
        
    results = []
    for invoice_obj in invoices:
        out = _normalize(invoice_obj, raw_text=combined_text_str, known_client_name=known_client_name_hint)
        if _needs_key_field_retry(out):
            try:
                # Run full fallback array and match blindly or by confidence. 
                fb_raw = _extract_key_fields_fallback(b64_images, raw_text=combined_text_str, is_multi_page=True)
                fb_invoices = fb_raw.get("invoices", []) if isinstance(fb_raw, dict) else []
                if not fb_invoices and isinstance(fb_raw, dict) and "invoice_number" in fb_raw:
                    fb_invoices = [fb_raw]
                
                matched_fb = {}
                if len(fb_invoices) == 1 and len(invoices) == 1:
                    matched_fb = fb_invoices[0]
                elif len(fb_invoices) == len(invoices):
                    idx = invoices.index(invoice_obj)
                    matched_fb = fb_invoices[idx]
                
                out = _merge_key_fields(out, matched_fb, raw_text=combined_text_str, known_client_name=known_client_name_hint)
            except Exception as e:
                print(f"[extraction] key-field fallback failed: {e}")
                logger.info(f"[extraction] key-field fallback failed: {e}")
        results.append(out)
    return results


def extract_from_file(file_path: str, known_client_name_hint: Optional[str] = None) -> dict:
    """
    Extract invoice data from an image or PDF file.

    Args:
        file_path: Absolute path to the uploaded invoice file.

    Returns:
        dict with keys matching the `invoices` DB table + additional_details.

    Raises:
        RuntimeError: if vLLM is unreachable or returns an error.
        ValueError: if the file type is unsupported.
    """
    ext = os.path.splitext(file_path)[1].lower()

    if ext in (".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"):
        img = Image.open(file_path)
        b64 = _pil_to_b64(img)
        prompt = _build_prompt(known_client_name=known_client_name_hint)
        print(f"[extraction] Prompt:\n{prompt}")
        logger.info(f"[extraction] Prompt:\n{prompt}")
        print(f"[extraction] Prompt: {prompt}")
        logger.info(f"[extraction] Prompt: {prompt}")
        try:
            raw = _call_vision_llm([b64], prompt)
        except Exception as e:
            raise RuntimeError(f"vLLM request failed: {e}") from e
        result = _normalize(_parse_json(raw), known_client_name=known_client_name_hint)
        if _needs_key_field_retry(result):
            try:
                fb_raw = _extract_key_fields_fallback([b64])
                result = _merge_key_fields(result, fb_raw, known_client_name=known_client_name_hint)
            except Exception as e:
                print(f"[extraction] key-field fallback failed for image: {e}")
                logger.info(f"[extraction] key-field fallback failed for image: {e}")
        return result

    elif ext == ".pdf":
        pages = _pdf_to_pages(file_path)
        if not pages:
            raise ValueError("PDF has no pages")
        img, raw_text = pages[0]
        b64 = _pil_to_b64_resize(img)
        prompt = _build_prompt(raw_text or None, known_client_name=known_client_name_hint)
        print(f"[extraction] Prompt: {prompt}")
        logger.info(f"[extraction] Prompt: {prompt}")
        try:
            raw = _call_vision_llm([b64], prompt)
        except Exception as e:
            raise RuntimeError(f"vLLM request failed: {e}") from e
        if not (raw and raw.strip()):
            print("[extraction] vLLM returned empty response for PDF — retrying once with same page")
            logger.info("[extraction] vLLM returned empty response for PDF — retrying once with same page")
            raw = _call_vision_llm([b64], prompt)
        if not (raw and raw.strip()):
            result = _normalize(_parse_json("{}"), raw_text=raw_text, known_client_name=known_client_name_hint)
        else:
            result = _normalize(_parse_json(raw), raw_text=raw_text, known_client_name=known_client_name_hint)
        if _needs_key_field_retry(result):
            try:
                fb_raw = _extract_key_fields_fallback([b64], raw_text=raw_text)
               
                result = _merge_key_fields(result, fb_raw, raw_text=raw_text, known_client_name=known_client_name_hint)
            except Exception as e:
                print(f"[extraction] key-field fallback failed for pdf: {e}")
                logger.info(f"[extraction] key-field fallback failed for pdf: {e}")
        return result

    else:
        raise ValueError(
            f"Unsupported file type '{ext}'. Supported: jpg, jpeg, png, pdf"
        )