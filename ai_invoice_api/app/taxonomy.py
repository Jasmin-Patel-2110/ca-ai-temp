"""
Industry-wise category and sub_category taxonomy.

Structure: industry -> { category_name: [sub_category1, sub_category2, ...] }
- category: high-level grouping (e.g. Sales Accounts, Purchase Accounts)
- sub_category: specific type under a category (e.g. Supari Sales - Taxable)
- sub_category must belong to its parent category; category depends on industry.

Used by: GET /categories API.
"""
import re
from typing import Any

# Tokens of length >= 3 for fuzzy overlap between product text and subcategory labels.
_TOKEN_RE = re.compile(r"[a-zA-Z0-9]{3,}")


def _text_tokens(s: str) -> set[str]:
    return {m.group(0).lower() for m in _TOKEN_RE.finditer(s or "")}


def _gst_rate_pct(s: str) -> int | None:
    """First NN in 'NN% ...' (GST / tax rate on invoice lines)."""
    m = re.search(r"(\d{1,2})\s*%", s or "", re.I)
    return int(m.group(1)) if m else None


def _sub_sort_key(sub: str, hay_tokens: set[str], pr: int | None) -> tuple[int, int, int]:
    st = _text_tokens(sub)
    inter = len(st & hay_tokens)
    extra = len(st - hay_tokens)
    sr = _gst_rate_pct(sub)
    rate_match = 1 if (pr is not None and sr is not None and sr == pr) else 0
    return (inter, -extra, rate_match)


def _resolve_category_key(cats: dict[str, list[str]], category: str | None) -> str | None:
    if not category or not str(category).strip():
        return None
    c = str(category).strip()
    for k in cats:
        if k.lower() == c.lower():
            return k
    return None


def _pick_subcategory(
    subs: list[str],
    hay_tokens: set[str],
    *,
    product_name: str | None = None,
) -> tuple[str, int]:
    """
    Return best subcategory label and overlap score.

    On equal token overlap, prefer labels with fewer extra words not present in the
    product text (avoids e.g. 'Construction Road Work...' when the line item says
    'Construction Work Income...'). When overlap still ties, prefer matching GST % to
    the product line (12% vs 18% are not in 3+ char tokens).
    """
    if not subs:
        raise ValueError("subs must be non-empty")
    pr = _gst_rate_pct(product_name or "")
    best_sub = subs[0]
    best_key = _sub_sort_key(best_sub, hay_tokens, pr)
    best_score = len(_text_tokens(best_sub) & hay_tokens)
    for sub in subs[1:]:
        k = _sub_sort_key(sub, hay_tokens, pr)
        if k > best_key:
            best_sub = sub
            best_key = k
            best_score = len(_text_tokens(sub) & hay_tokens)
    return (best_sub, best_score)


def suggest_taxonomy_labels(
    industry: str | None,
    transaction_type: str | None,
    *,
    product_name: str | None = None,
    extra_text: str = "",
    existing_category: str | None = None,
) -> tuple[str | None, str | None]:
    """
    Heuristic category/sub_category from INDUSTRY_CATEGORY_TAXONOMY when ML is unavailable.

    - Uses transaction_type (Sales -> Sales Accounts, Purchase -> Purchase Accounts) when present.
    - Picks sub_category by token overlap with product_name and extra_text, else first listed sub.
    - If existing_category is set and matches taxonomy, only refines sub_category within that group.
    - If transaction_type does not map, scores all subcategories under the industry and picks the best match.
    - Last resort: Sales Accounts + first subcategory if that group exists.
    """
    cats = get_categories_for_industry(industry)
    if not cats:
        return (None, None)

    hay = " ".join(
        [
            product_name or "",
            extra_text or "",
            transaction_type or "",
        ]
    )
    hay_tokens = _text_tokens(hay)
    pr = _gst_rate_pct(product_name or "")

    # Only refine subcategory when category is already known (e.g. LLM set category only).
    resolved_existing = _resolve_category_key(cats, existing_category)
    if resolved_existing:
        subs = cats.get(resolved_existing, [])
        if not subs:
            return (resolved_existing, None)
        sub, _ = _pick_subcategory(subs, hay_tokens, product_name=product_name)
        return (resolved_existing, sub)

    tt = (transaction_type or "").strip().lower()

    def hinted_sales() -> bool:
        return tt in ("sales", "sale") or "sales" in tt

    def hinted_purchase() -> bool:
        return tt in ("purchase",) or "purchase" in tt

    hinted_cat: str | None = None
    if hinted_sales() and "Sales Accounts" in cats:
        hinted_cat = "Sales Accounts"
    elif hinted_purchase() and "Purchase Accounts" in cats:
        hinted_cat = "Purchase Accounts"

    if hinted_cat:
        subs = cats[hinted_cat]
        sub, _ = _pick_subcategory(subs, hay_tokens, product_name=product_name)
        return (hinted_cat, sub)

    # Global best match across all categories (e.g. missing or uncommon transaction_type).
    best_cat: str | None = None
    best_sub: str | None = None
    best_key: tuple[int, int, int] | None = None
    for cat_name, subs in cats.items():
        for sub in subs:
            k = _sub_sort_key(sub, hay_tokens, pr)
            if best_key is None or k > best_key:
                best_key = k
                best_cat, best_sub = cat_name, sub

    best_score = len(_text_tokens(best_sub) & hay_tokens) if best_sub else -1
    if best_score > 0 and best_cat and best_sub:
        return (best_cat, best_sub)

    if "Sales Accounts" in cats and cats["Sales Accounts"]:
        subs = cats["Sales Accounts"]
        sub, _ = _pick_subcategory(subs, hay_tokens, product_name=product_name)
        return ("Sales Accounts", sub)

    for cat_name, subs in cats.items():
        if subs:
            sub, _ = _pick_subcategory(subs, hay_tokens, product_name=product_name)
            return (cat_name, sub)

    return (None, None)

# Map industry (Industry enum value) -> { category: [subcategories] }
# Gov = Government in UI
INDUSTRY_CATEGORY_TAXONOMY: dict[str, dict[str, list[str]]] = {
    "Textile Jobwork": {
        "Opening Stock": [
            "Closing Stock"
        ],
        "Purchase Accounts": [
            "Discount on Non GST",
            "Discount on Purchase",
            "Inter Purchase Tax Invoice",
            "Jari Purchase",
            "Jari Purchase Taxable 12%",
            "Jari Purchase Tax Invoice",
            "Jari Purchase Tax Invoice - 5%",
            "Job Work Exps Tax Invoice",
            "Job Work Exps - URD",
            "Jobwork Exps [URD]",
            "Material Purchase",
            "Material Purchase NON GST",
            "Material Purchase Tax Invoice - 12%",
            "Material Purchase Tax Invoice 5%",
            "Material Purchase [IGST@5%]",
            "Mobile Purchase",
            "Purchase",
            "Purchase - Tex Invoice",
            "Rafrigerator Purchase",
            "Roof Top System - 12%",
            "Roof Top System - 18%"
        ],
        "Direct Expenses": [
            "Dhaga Cutting Expense",
            "Factory Rent Expenses",
            "Light Bill Exps [000008201344]",
            "Light Bill Exps [000008201348]",
            "Salary & Wages",
            "Spare Part Exp. [GST]-12%",
            "Spare Parts Exps",
            "Tempo Rent Exps"
        ],
        "Indirect Expenses": [
            "Accounting Fees Exps",
            "Alter Exp-Non Gst",
            "Bank Charge",
            "Brijeshkumar-Salary",
            "Brokrage & Other Exps",
            "Conveyance Exp.",
            "Depriciation",
            "Designer Salary",
            "Discount in Purchase[IGST@5%]",
            "Factory Expences[GST@5%]",
            "Factory Exps",
            "Factory Exp[GST@12%]",
            "Factory Exp [GST@18%]",
            "Fright Exp [IGST@5%]",
            "GST Exp",
            "GST Late Fees",
            "Interenet Exps",
            "Interest Exps",
            "Interest on GST",
            "Interest on Tds",
            "Legal Exps",
            "Loan Processing Charge",
            "Machinery Rent",
            "Miscellanous Expense",
            "Professional Fees",
            "Professional Fees Non GST",
            "Repairing & Maintaince Exps",
            "Roll Polish Expenses",
            "Rounding Off",
            "Salary Exp",
            "S M C Tax",
            "Spare Parts Exps [GST]",
            "Stationary & Printing Exp.",
            "Telephone Expense",
            "Vatav Kasar",
            "Water Expenses",
            "W Off Debtors"
        ],
        "Sales Accounts": [
            "Discount on Sales",
            "Discount on Sale [GST@5%]",
            "Embroidery Job Work Income",
            "Embroidery Job Work Income Non GST",
            "Embroidery Job Work Income Tax Invoice",
            "Job Work Before GST",
            "Rate Difference [GST@5%]"
        ],
        "Direct Incomes": [
            "Gift & Other Income",
            "Rent Income"
        ],
        "Indirect Incomes": [
            "Dividend Income",
            "Interest Bank",
            "Interest - FD",
            "Interest Subsidy",
            "Subsidy",
            "W Off Creditors"
        ],
        "Closing Stock": [
            "Closing Stock"
        ]
    },
    "Supari": {
        "Opening Stock": [
            "Opening Stock of Goods"
        ],
        "Purchase Accounts": [
            "Purchase",
            "Purchase - Tax Invoice",
            "Purchase - URD",
            "Supari Purchase",
            "Supari Purchase - Taxable",
            "Supari Purchase - URD",
            "Packing Material Purchase",
            "Rate Difference Purchase",
            "Discount on Purchase"
        ],
        "Direct Expenses": [
            "Loading & Unloading Charges",
            "Labour Charges",
            "Transport Charges",
            "Godown Rent",
            "Sorting & Cleaning Expenses",
            "Wages Expenses"
        ],
        "Indirect Expenses": [
            "Accounting Charges",
            "Audit Fees",
            "Bank Charges",
            "Commission Expenses",
            "Conveyance Expenses",
            "Depreciation",
            "Electricity Expenses",
            "GST Expenses",
            "Insurance",
            "Interest Expenses",
            "Legal Fees",
            "Miscellaneous Expenses",
            "Office Expenses",
            "Professional Fees",
            "Repair & Maintenance",
            "Salary Expenses",
            "Stationery & Printing",
            "Telephone Expenses",
            "Travel Expenses",
            "Vatav Kasar",
            "Write Off Debtors"
        ],
        "Sales Accounts": [
            "Sales",
            "Sales - Tax Invoice",
            "Sales - URD",
            "Supari Sales",
            "Supari Sales - Taxable",
            "Rate Difference Sales",
            "Discount on Sales"
        ],
        "Indirect Incomes": [
            "Bank Interest",
            "Interest on FD",
            "Interest on IT Refund",
            "Other Income",
            "Commission Income"
        ],
        "Closing Stock": [
            "Closing Stock of Goods"
        ]
    },
    "Labour": {
        "Opening Stock": [
            "Opening Stock"
        ],
        "Purchase Accounts": [
            "Purchase",
            "Purchase - Tax Invoice",
            "Purchase - URD",
            "Material Purchase",
            "Material Purchase - Taxable",
            "Rate Difference Purchase",
            "Discount on Purchase"
        ],
        "Direct Expenses": [
            "Labour Charges",
            "Contract Labour Expenses",
            "Site Expenses",
            "Wages Expenses",
            "Loading & Unloading Charges",
            "Transport Charges"
        ],
        "Indirect Expenses": [
            "Accounting Charges",
            "Audit Fees",
            "Bank Charges",
            "Commission Expenses",
            "Conveyance Expenses",
            "Depreciation",
            "Electricity Expenses",
            "GST Expenses",
            "Insurance",
            "Interest Expenses",
            "Legal Fees",
            "Miscellaneous Expenses",
            "Office Expenses",
            "Professional Fees",
            "Repair & Maintenance",
            "Salary Expenses",
            "Stationery & Printing",
            "Telephone Expenses",
            "Travel Expenses",
            "Vatav Kasar",
            "Write Off Debtors"
        ],
        "Sales Accounts": [
            "Labour Income",
            "Contract Income",
            "Service Income",
            "Rate Difference Sales",
            "Discount on Sales"
        ],
        "Indirect Incomes": [
            "Bank Interest",
            "Interest on FD",
            "Interest on IT Refund",
            "Other Income",
            "Commission Income"
        ],
        "Closing Stock": [
            "Closing Stock"
        ]
    },
    "Jewellers": {
        "Opening Stock": [
            "Opening Stock of Gold",
            "Opening Stock of Silver",
            "Opening Stock of Jewellery"
        ],
        "Purchase Accounts": [
            "Gold Purchase",
            "Silver Purchase",
            "Jewellery Purchase",
            "Purchase - Tax Invoice",
            "Purchase - URD",
            "Bullion Purchase",
            "Hallmark Charges Purchase",
            "Making Charges Purchase",
            "Rate Difference Purchase",
            "Discount on Purchase"
        ],
        "Direct Expenses": [
            "Making Charges",
            "Labour Charges",
            "Karigar Expenses",
            "Polishing Charges",
            "Hallmark Charges",
            "Refining Charges"
        ],
        "Indirect Expenses": [
            "Accounting Charges",
            "Audit Fees",
            "Bank Charges",
            "Commission Expenses",
            "Conveyance Expenses",
            "Depreciation",
            "Electricity Expenses",
            "GST Expenses",
            "Insurance",
            "Interest Expenses",
            "Legal Fees",
            "Miscellaneous Expenses",
            "Office Expenses",
            "Professional Fees",
            "Repair & Maintenance",
            "Salary Expenses",
            "Security Charges",
            "Shop Expenses",
            "Stationery & Printing",
            "Telephone Expenses",
            "Travel Expenses",
            "Vatav Kasar",
            "Write Off Debtors"
        ],
        "Sales Accounts": [
            "Gold Sales",
            "Silver Sales",
            "Jewellery Sales",
            "Sales - Tax Invoice",
            "Sales - URD",
            "Making Charges Income",
            "Rate Difference Sales",
            "Discount on Sales"
        ],
        "Indirect Incomes": [
            "Bank Interest",
            "Interest on FD",
            "Interest on IT Refund",
            "Other Income",
            "Commission Income"
        ],
        "Closing Stock": [
            "Closing Stock of Gold",
            "Closing Stock of Silver",
            "Closing Stock of Jewellery"
        ]
    },
    "IT": {
        "Purchase Accounts": [
            "Computer Accesaries",
            "Constulting Expenses (GST @ 18%)",
            "Contract Expense (GST @ 18%)",
            "Glass",
            "Purchase - AC",
            "Purchase - Computer",
            "Purchase - LED TV",
            "Purchase - Leptop",
            "Purchase - Tablet"
        ],
        "Direct Expenses": [
            "Advertistment Expenses",
            "Advertistment Expenses - GST",
            "Audit Fees",
            "Bank Charges",
            "Constulting Expenses 10%",
            "Consulting Fees Interstate",
            "Consulting Fees Other",
            "Corporate Plan Expenses",
            "Deffered Tax Expenses",
            "Depreciation & Amortisation Expenses",
            "Discount",
            "DLT Registration Charges",
            "Domain Renewal Expenses",
            "Donation Expenses",
            "DSC Expenses",
            "Employee Insurance Expenses",
            "GST Expenses",
            "HR Services for Project Implementation Expenses",
            "Income Tax Expenses",
            "Insurance Expenses",
            "Interest Expenses - Mortgage Loan",
            "Interest On TDS",
            "Internet Expenses",
            "Internet Expenses (GST @ 18%)",
            "Light Bill Expense",
            "Loan Processing Charge",
            "Miscellaneous Expenses",
            "Mortgage Advocate Fees",
            "Mortgage Registration Fees",
            "Mortgage Stamp Duty Exps",
            "Office Construcation Work  Expenses (GST @ 18%)",
            "Office Expenses",
            "Office Expenses (GST @ 18%)",
            "Office Expenses (GST @ 5%)",
            "Office Expenses (IGST @ 18%)",
            "Office Labour Work Expenses",
            "Office Maintanance Expe-Diamond World",
            "Office Rent - Ahmedabad",
            "Office Tour Expenses",
            "Other Charges",
            "Professional Fees Expenses",
            "Professional Fees Expenses - GST",
            "Professional Fees Expenses - TDS",
            "Professional Fees-TDS",
            "Professional Tax",
            "ROC Fees Expenses",
            "Rounding Off",
            "Salary Expenses",
            "Server Purchase-GST",
            "Server Renewal Expenses",
            "Service Expenses",
            "SMC Tax",
            "SMS Services",
            "Social Media Marketing Expenses",
            "Software Expenses",
            "Stationery Expenses",
            "Subleting Devlopement Service Expenses",
            "Telephone Expenses",
            "Travelling Expenses (GST @ 12%)",
            "Travelling Expenses (GST @ 18%)",
            "Travelling Expenses (GST @ 5%)",
            "Travelling Expenses (IGST @ 18%)",
            "Travelling Expenses (IGST @ 5%)",
            "Travelling Expenses - Non GST",
            "Vatav Kasar",
            "Web Devlopment Expenses",
            "Website Expense",
            "Website Exps-GST"
        ],
        "Sales Accounts": [
            "Consulting Fees Income",
            "Consulting Fees Income-Interstate",
            "Consulting Fees Income - Local",
            "Consulting Fees Income - LUT",
            "Rate Difference",
            "Software Devlopment Income"
        ],
        "Indirect Incomes": [
            "Deffrred Tax Income",
            "Interest - FD",
            "Interest I.T.Refund",
            "Interest - Other (Torrent Power)"
        ]
    },
    "Gov": {
        "Opening Stock": [
            "Closing Stock - Raw Material",
            "Closing Stock - W.I.P",
            "Oppening Stock"
        ],
        "Purchase Accounts": [
            "Discount on Purchase",
            "Purchase 18%",
            "Purchase 5% IGST",
            "Purchase 12% GST",
            "Purchase 12% IGST",
            "Purchase 18% GST",
            "Purchase 18% IGST",
            "Purchase 28% GST",
            "Purchase 28% IGST",
            "Purchase 5% GST",
            "Purchase Exempted",
            "Purchase URD"
        ],
        "Direct Expenses": [
            "Carting Expense 12% GST",
            "Carting Expense 18% GST",
            "Electricity Exp Office",
            "GST Expenses of Turnover [Guj]",
            "GST on Turnover Expenses [MP]",
            "Machinery Rent 18% IGST",
            "Machinery Rent Expenses",
            "Stamp Paper Charges",
            "Tender Fee",
            "Testing Charge",
            "Testing Charge 18% IGST",
            "Carting Expense URD",
            "Construction Labour 18% GST",
            "Construction Labour 18% IGST",
            "Construction Labour Exp",
            "Construction Sublet 18% GST",
            "Construction Sublet 18% IGST",
            "Diesel Purchase Exp",
            "Electricity Exp Site",
            "Labour Cess",
            "Labour Expense",
            "Machinery Rent 18% GST",
            "Machinery Rent Exp",
            "Security Expense 18% GST",
            "Testing Charge 18% GST",
            "Wages & Salary Expenses",
            "Write Off Sentring Material"
        ],
        "Indirect Expenses": [
            "Advertisement Expense 5% GST",
            "Bank Charge",
            "Bank Charge 18% GST",
            "Bank Charge 18% IGST",
            "Bank Charges",
            "Bank Facilities Renewal Charges - GST 18%",
            "Bank Guarantee  18% GST",
            "Bank Interest- Exp",
            "BG Commission Non GST",
            "Discount Purchase A/c.",
            "ESIC Exp",
            "Insurance Expenses Non GST",
            "Interest On TDS",
            "Late Fees GST",
            "Loan Processing Charge 18% IGST",
            "Office Exp",
            "Packing & Forwarding Charges",
            "Pre - Paid BG Insurance",
            "Professional Fee 18% IGST",
            "Professional Fees - Non GST",
            "Professional Tax",
            "Provident Fund Exp",
            "Registration  Fee 18% GST",
            "Registration Fee Non GST",
            "Remuneration To Partner",
            "Repair & Maintenance 18% GST",
            "Software Expenses",
            "Time Limit Penalty Expense",
            "Transpostation Expense 18% IGST",
            "Audit Fees",
            "Depreciation",
            "Donetion",
            "Insurance Expense",
            "Insurance Expense 12% GST",
            "Insurance Expense 18% GST",
            "Insurance Expense 18% IGST",
            "Interest On GST",
            "Loan Interest Expense",
            "Loan Processing Charges",
            "Miscellaneous Expenses",
            "Professional Fee 18% GST",
            "Rent Expenses",
            "Repair & Maintenance",
            "Round Off",
            "Salary Expenses",
            "Site Expense",
            "Traveling Exp Non GST",
            "Vatav Kasar",
            "Write Off"
        ],
        "Sales Accounts": [
            "Construction Road Work Income 18% GST",
            "Construction Work Income 18% IGST",
            "General Cons.Work of Water Supply Pipeline 18% GST",
            "GST of Sales Turnover [Guj]",
            "GST of Sales Turnover [MP]",
            "Construction Work Income 12% GST",
            "Construction Work Income 18% GST"
        ],
        "Direct Incomes": [
            "Material Recovery"
        ],
        "Indirect Incomes": [
            "Interest Income-FD",
            "Interest Income on IT Refund"
        ],
        "Closing Stock": [
            "Closing Stock - Raw Material",
            "Closing Stock - W.I.P",
            "Oppening Stock"
        ]
    },
    "Hospital": {
        "Opening Stock": [
            "Closing Stock [Medical]"
        ],
        "Purchase Accounts": [
            "Opening Stock",
            "Purchase Return [Param Medical Store]",
            "Purchase [Param Medical Store]"
        ],
        "Direct Expenses": [
            "Consumable Expenses",
            "Food Service Expenses",
            "House Keeping Expenses",
            "Light Bill Expenses [DGSM4173]",
            "Light Bill Expenses [DGSM4174]",
            "Medicine Purchase",
            "Out Side Lab Testing Expenses",
            "Patient Implant Expenses",
            "Professional Fees",
            "Staff Salary & Bonus Exps",
            "Visiting & Consulting Fees Expenses"
        ],
        "Indirect Expenses": [
            "ICU Related Expenses",
            "Medical Store Related Expenses",
            "Advertisement Expenses",
            "Ambulance Services Expenses",
            "Audit Fees",
            "Bank Charges",
            "Bio Medical Waste Expenses",
            "Bonus Expenses",
            "Bussiness Promotion Expenses",
            "Cartige Refill & Printer Service Expenses",
            "CME Expenses",
            "Conferance Expenses",
            "Consulting Fees",
            "Credit Card Charges",
            "Depreciation",
            "Donation",
            "Fire Safety Expenses",
            "Fuel Expenses",
            "GPCB Fees",
            "Hospital Expenses",
            "Hospital Registraion Charges",
            "Hospital Security & Cleaning Expenses",
            "Instrument Reparing & Maintenance Expenses",
            "Insurance",
            "Interest Expenses Car Loan",
            "Interest Expenses - Hdfc Bank Professional Loan",
            "Interest Expenses-Icici Loan [LDSUR00044449125]",
            "Interest Expenses-Icici Loan [LDSUR00044449151]",
            "Interest Expenses-Icici Loan [LDSUR00044449202]",
            "Interest Expenses-Icici Loan [LDSUR00044449227]",
            "Interest Expenses - Sutex Bank Loan [24801783328]",
            "Interest Expenses - Sutex Bank Loan [24801787333]",
            "Interest on Tds",
            "Internet Expenses",
            "Laboratory Materials Purchase",
            "Lab Testing Expenses",
            "Light Bill Expenses [DGC39901]",
            "Light Bill Expenses [DGC39902]",
            "Light Bill Expenses [DGC90352]",
            "Loan Processing Charges",
            "Maa Card & Aayushman Card Refund",
            "Maa Card Patient Payment",
            "Membership Fees",
            "NABH Fees",
            "Oxygen Refill Expenses",
            "Payment to Patient for Diagnostic & Blood",
            "PF Administration Charges",
            "PF Expenses",
            "Processing Charges",
            "Professional Tax",
            "Property Tax",
            "Registration Fees",
            "Rent Expenses",
            "Software Maintenance Expenses",
            "Staff House Rent Expenses",
            "Staff Welfare Expenses",
            "Stationery & Printing Expenses",
            "Tds Return Late Filling Fees",
            "Tea & Refreshment Expenses",
            "Telephone Expenses",
            "Uniform & Linen Expenses",
            "Vaccine Purchase of Covid",
            "Vatav Kasar",
            "Vehicle Reparing Expenses",
            "Water Expenses",
            "X-Ray Film Purchase"
        ],
        "Sales Accounts": [
            "Diagnostics Income",
            "Dialysis Income",
            "Advertisement Conract Income",
            "Consulting Income",
            "Contract Income",
            "Professional Fees Income",
            "Sales Return [Param Medical Store]",
            "Sales [Param Medical Store]",
            "Vaccine Sales of Covid"
        ],
        "Direct Incomes": [
            "ECG Income",
            "ICU Related Income",
            "Indoor Bill Income",
            "Laboratory Income",
            "OPD Income",
            "X-Ray Income",
            "Echo Income",
            "MOU Discount",
            "Visiting Fees Income"
        ],
        "Closing Stock": [
            "Closing Stock [Medical]"
        ],
        "Indirect Incomes": [
            "Dividend Income",
            "Interest - FD",
            "Interest IT Refund",
            "Interest on It Refund",
            "Rent Income ICU Transfer"
        ]
    },
    "Diamond": {
        "Opening Stock": [
            "Closing Stock"
        ],
        "Purchase Accounts": [
            "AC Purchase",
            "IGST Purchase-Polish Diamond [0.25%]",
            "IGST-Purchase Polished Diamond - 1.5%",
            "Purchase - Polish Diamond[0.25%]",
            "Purchase-Polished Diamond [GST@1.5%]"
        ],
        "Indirect Expenses": [
            "Accountant Salary",
            "Audit Fees",
            "Bank Charges",
            "Depreciation",
            "DSC Expenses",
            "GST Late Fees",
            "Interest on Capital",
            "Interest on Car Loan",
            "Interest on Tds",
            "Light Bill Expenses",
            "Loan Processing Charge",
            "Maintainance Exps",
            "Professional Fees",
            "Remuneration to Partners",
            "Rounding Off",
            "Staff Salary Exps",
            "Vatav Kasar"
        ],
        "Sales Accounts": [
            "Sales - Interstate [0.25%]",
            "Sales - Interstate [1.5%]",
            "Sales Local [GST@1.5%]",
            "Sales - PD Local [0.25%]"
        ],
        "Indirect Incomes": [
            "IT Refund Int."
        ],
        "Closing Stock": [
            "Closing Stock"
        ]
    }
}

def get_categories_for_industry(industry: str | None) -> dict[str, list[str]]:
    """Return category -> subcategories for the given industry. Empty dict if unknown."""
    if not industry or not industry.strip():
        return {}
    # Map Government to Gov
    ind = industry.strip()
    if ind.lower() == "government":
        ind = "Gov"
    return INDUSTRY_CATEGORY_TAXONOMY.get(ind, {})


def get_subcategories_for_category(industry: str | None, category: str | None) -> list[str]:
    """Return subcategory list for industry+category. Empty if not found."""
    cats = get_categories_for_industry(industry)
    if not category or not category.strip():
        return []
    return cats.get(category.strip(), [])


def validate_category_subcategory(
    industry: str | None, category: str | None, sub_category: str | None
) -> tuple[str | None, str | None]:
    """Validate and coerce category/sub_category against industry taxonomy. Returns (category, sub_category) or (None, None)."""
    cats = get_categories_for_industry(industry)
    if not cats:
        return (category, sub_category) if category or sub_category else (None, None)

    # Validate category
    cat_valid = None
    if category and category.strip():
        for k in cats:
            if k.lower() == category.strip().lower():
                cat_valid = k
                break
        if not cat_valid:
            cat_valid = category.strip()[:255]  # Allow custom if not in list

    # Validate sub_category against category
    sub_valid = None
    if sub_category and sub_category.strip():
        subs = cats.get(cat_valid or "", []) if cat_valid else []
        for s in subs:
            if s.lower() == sub_category.strip().lower():
                sub_valid = s
                break
        if not sub_valid:
            sub_valid = sub_category.strip()[:255]  # Allow custom

    return (cat_valid, sub_valid)
