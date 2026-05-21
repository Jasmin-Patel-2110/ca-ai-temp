from __future__ import annotations
import json
from enum import Enum
from typing import Optional, List, Any
from pydantic import BaseModel, field_validator, model_validator


class Industry(str, Enum):
    """Allowed industry values for invoice extraction."""
    TEXTILE_MANUFACTURING = "Textile Manufacturing"
    TEXTILE_JOBWORK = "Textile Jobwork"
    SUPARI = "Supari"
    LABOUR = "Labour"
    JEWELLERS = "Jewellers"
    IT = "IT"
    GOV = "Gov"
    HOSPITAL = "Hospital"
    DIAMOND = "Diamond"


INDUSTRY_VALUES = [e.value for e in Industry]

# Industry-wise category -> sub_category taxonomy (from app.taxonomy). Used for GET /categories.
from app.taxonomy import INDUSTRY_CATEGORY_TAXONOMY

CATEGORY_TAXONOMY = INDUSTRY_CATEGORY_TAXONOMY  # For GET /categories


def _coerce_industry(v: Any) -> Optional[str]:
    """Coerce input to valid Industry enum value or None."""
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    s = str(v).strip()
    if not s:
        return None
    # Exact match (case-insensitive)
    for val in INDUSTRY_VALUES:
        if s.lower() == val.lower():
            return val
    # Common mappings for extracted values
    _MAP = {
        "healthcare": Industry.HOSPITAL.value,
        "retail": Industry.TEXTILE_MANUFACTURING.value,
        "electronics": Industry.IT.value,
        "jewellery": Industry.JEWELLERS.value,
        "jeweler": Industry.JEWELLERS.value,
        "gems & jewellery": Industry.JEWELLERS.value,
        "jwellers": Industry.JEWELLERS.value,
        "government": Industry.GOV.value,
        "textile": Industry.TEXTILE_MANUFACTURING.value,
    }
    return _MAP.get(s.lower(), None)


class DocumentData(BaseModel):
    id:          int
    doc_id:      str
    doc_name:    str
    preview_url: Optional[str] = None  # Pre-signed URL for PDF preview (30 min expiry)
    created_at:  Optional[str] = None  # ISO format e.g. "2026-03-16T06:31:33"


def _coerce_float(v: Any) -> Optional[float]:
    """Coerce str/int/float to float for DB values that may be stored as string or number."""
    if v is None or v == "" or (isinstance(v, str) and v.strip().lower() in ("none", "null", "")):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.replace(",", "").strip())
        except ValueError:
            return None
    return None


class InvoiceData(BaseModel):
    id:               int
    invoice_number:   Optional[str] = None
    user_id:          str
    doc_id:           str
    client_name:      Optional[str] = None
    buyer_party_name:   Optional[str] = None
    seller_party_name:  Optional[str] = None
    product_name:       Optional[str] = None
    industry:         Optional[str] = None
    category:         Optional[str] = None
    sub_category:      Optional[str] = None
    transaction_type: Optional[str] = None
    status:           Optional[str] = None
    invoice_date: Optional[Any] = None
    buyer_pan_number: Optional[str] = None
    seller_pan_number: Optional[str] = None
    buyer_gst_number: Optional[str] = None
    seller_gst_number: Optional[str] = None
    buyer_contact_number: Optional[str] = None
    seller_contact_number: Optional[str] = None
    buyer_location:   Optional[str] = None
    seller_location:  Optional[str] = None
    gst:              Optional[float] = None
    cgst:             Optional[float] = None
    sgst:             Optional[float] = None
    igst:             Optional[float] = None
    total:            Optional[float] = None
    quantity:         Optional[float] = None
    rate:             Optional[float] = None
    amount:           Optional[float] = None
    amount_paid:      Optional[float] = None
    balance_amount:   Optional[float] = None
    payment_mode:     Optional[str] = None
    additional_detail: Optional[Any] = None
    document:         Optional[DocumentData] = None  # only for GET /invoices/{id}
    created_datetime: Optional[Any] = None
    updated_datetime: Optional[Any] = None

    @model_validator(mode="after")
    def _strip_line_items_from_additional_detail(self) -> "InvoiceData":
        ad = self.additional_detail
        if isinstance(ad, dict) and ("line_items" in ad or "lineItems" in ad):
            self.additional_detail = {k: v for k, v in ad.items() if k not in ("line_items", "lineItems")}
        return self

    @field_validator(
        "gst", "cgst", "sgst", "igst", "total", "quantity", "rate",
        "amount", "amount_paid", "balance_amount",
        mode="before",
    )
    @classmethod
    def _coerce_numeric(cls, v: Any) -> Optional[float]:
        return _coerce_float(v)

    @field_validator("industry", mode="before")
    @classmethod
    def _coerce_industry_field(cls, v: Any) -> Optional[str]:
        return _coerce_industry(v)

    @field_validator("additional_detail", mode="before")
    @classmethod
    def ensure_additional_detail_is_dict(cls, v: Any) -> Optional[dict]:
        """Ensure additional_detail is a dict in the response (parse JSON string if needed)."""
        if v is None:
            return None
        if isinstance(v, dict):
            return v
        if isinstance(v, str) and v.strip():
            try:
                return json.loads(v)
            except (json.JSONDecodeError, ValueError):
                return None
        return None

    class Config:
        from_attributes = True


class InvoiceListItem(BaseModel):
    """Invoice for list endpoints - no document field."""
    id:               int
    invoice_number:   Optional[str] = None
    user_id:          str
    doc_id:           str
    client_name:      Optional[str] = None
    buyer_party_name:   Optional[str] = None
    seller_party_name:  Optional[str] = None
    product_name:       Optional[str] = None
    industry:         Optional[str] = None
    category:         Optional[str] = None
    sub_category:      Optional[str] = None
    transaction_type: Optional[str] = None
    status:           Optional[str] = None
    invoice_date: Optional[Any] = None
    buyer_pan_number: Optional[str] = None
    seller_pan_number: Optional[str] = None
    buyer_gst_number: Optional[str] = None
    seller_gst_number: Optional[str] = None
    buyer_contact_number: Optional[str] = None
    seller_contact_number: Optional[str] = None
    buyer_location:   Optional[str] = None
    seller_location:  Optional[str] = None
    gst:              Optional[float] = None
    cgst:             Optional[float] = None
    sgst:             Optional[float] = None
    igst:             Optional[float] = None
    total:            Optional[float] = None
    quantity:         Optional[float] = None
    rate:             Optional[float] = None
    amount:           Optional[float] = None
    amount_paid:      Optional[float] = None
    balance_amount:   Optional[float] = None
    payment_mode:     Optional[str] = None
    additional_detail: Optional[Any] = None
    created_datetime: Optional[Any] = None
    updated_datetime: Optional[Any] = None

    @model_validator(mode="after")
    def _strip_line_items_from_additional_detail(self) -> "InvoiceListItem":
        ad = self.additional_detail
        if isinstance(ad, dict) and ("line_items" in ad or "lineItems" in ad):
            self.additional_detail = {k: v for k, v in ad.items() if k not in ("line_items", "lineItems")}
        return self

    @field_validator(
        "gst", "cgst", "sgst", "igst", "total", "quantity", "rate",
        "amount", "amount_paid", "balance_amount",
        mode="before",
    )
    @classmethod
    def _coerce_numeric(cls, v: Any) -> Optional[float]:
        return _coerce_float(v)

    @field_validator("industry", mode="before")
    @classmethod
    def _coerce_industry_field(cls, v: Any) -> Optional[str]:
        return _coerce_industry(v)

    @field_validator("additional_detail", mode="before")
    @classmethod
    def ensure_additional_detail_is_dict(cls, v: Any) -> Optional[dict]:
        if v is None:
            return None
        if isinstance(v, dict):
            return v
        if isinstance(v, str) and v.strip():
            try:
                return json.loads(v)
            except (json.JSONDecodeError, ValueError):
                return None
        return None

    class Config:
        from_attributes = True


class UpdateInvoiceRequest(BaseModel):
    invoice_number:   Optional[str] = None
    client_name:       Optional[str]   = None
    product_name:      Optional[str]   = None
    line_items:        Optional[List[dict]] = None
    industry:          Optional[str]   = None  # Must be one of Industry enum values
    category:          Optional[str]   = None
    sub_category:       Optional[str]   = None
    transaction_type:  Optional[str]   = None
    status:            Optional[str]   = None
    invoice_date:  Optional[str]   = None
    buyer_party_name:   Optional[str]   = None
    seller_party_name:  Optional[str]   = None
    buyer_pan_number: Optional[str]   = None
    seller_pan_number: Optional[str]   = None
    buyer_gst_number: Optional[str]   = None
    seller_gst_number: Optional[str]   = None
    buyer_contact_number: Optional[str]   = None
    seller_contact_number: Optional[str]   = None
    buyer_location:    Optional[str]   = None
    seller_location:   Optional[str]   = None
    gst:               Optional[float]   = None
    cgst:              Optional[float]   = None
    sgst:              Optional[float]   = None
    igst:              Optional[float]   = None
    total:             Optional[float]   = None
    quantity:          Optional[float]   = None
    rate:              Optional[float]   = None
    amount:            Optional[float] = None
    amount_paid:       Optional[float] = None
    balance_amount:    Optional[float] = None
    payment_mode:      Optional[str]   = None
    additional_detail: Optional[Any]   = None

    @field_validator("industry", mode="before")
    @classmethod
    def _coerce_industry_field(cls, v: Any) -> Optional[str]:
        return _coerce_industry(v) if v is not None else None


class InvoiceUploadResponse(BaseModel):
    status:   int
    message:  str
    known_client_name: Optional[str] = None
    invoices: Optional[List[InvoiceListItem]] = None  # all invoices (no document)


class UpdateInvoiceResponse(BaseModel):
    status:  int
    message: str
    invoice: InvoiceData


class InvoiceListResponse(BaseModel):
    status:   int
    message:  str
    invoices: List[InvoiceListItem]
