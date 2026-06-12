"""
Map a generic PdfExtractor result onto the purchase-entry form shape.
─────────────────────────────────────────────────────────────────────
The extractor returns arbitrary column names ("Sr.No", "Item Description",
"Qty", "P.Rate"...). This module classifies those columns into the fixed
purchase line fields the UI expects (item / batch / qty / rate / mrp / ...),
parses messy cell values into numbers and ISO dates, and does a best-effort
match of supplier name → party_master and item name → item_master.

Nothing here calls an LLM — it's pure heuristics over the already-extracted
JSON, so it's instant and deterministic. Unmatched items are returned with
their extracted_name so the user can pick / create the medicine manually.
"""

import re
from datetime import date
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.item_master import ItemMaster
from app.models.party_master import PartyMaster

# Fields the purchase-entry row understands. Order = assignment priority
# (most specific first, so e.g. "Free Qty" is claimed before plain "Qty").
_FIELD_ORDER = [
    "free_quantity",
    "quantity",
    "mrp",
    "sale_rate",
    "purchase_rate",
    "discount",
    "gst_percent",
    "expiry_date",
    "batch_no",
    "item_name",
]


def _norm(s: Any) -> str:
    """Lowercase, strip everything except a-z0-9 — for fuzzy header/name compares."""
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def _matches(col_norm: str, field: str) -> bool:
    """Does a normalised column name look like the given purchase field?"""
    if field == "free_quantity":
        return any(k in col_norm for k in ("free", "scheme", "bonus"))
    if field == "quantity":
        return any(k in col_norm for k in ("qty", "quantity", "qnty")) or col_norm in ("nos", "units")
    if field == "mrp":
        return "mrp" in col_norm
    if field == "sale_rate":
        return any(k in col_norm for k in ("salerate", "saleprice", "sellrate", "sellingprice", "selling", "retail", "srate", "mktrate")) \
            or col_norm in ("sale", "sp")
    if field == "purchase_rate":
        # any "rate"/"price"/"cost"/"ptr" — mrp/sale already claimed earlier in the order
        return any(k in col_norm for k in ("rate", "price", "cost", "ptr", "pts", "purch")) \
            and not any(k in col_norm for k in ("gst", "tax", "disc", "net", "total", "amount", "value"))
    if field == "discount":
        return "disc" in col_norm
    if field == "gst_percent":
        return "gst" in col_norm or "igst" in col_norm or ("tax" in col_norm and ("rate" in col_norm or "per" in col_norm or "%" in col_norm))
    if field == "expiry_date":
        return col_norm.startswith("exp") or "expiry" in col_norm or "expdt" in col_norm or "expdate" in col_norm
    if field == "batch_no":
        return "batch" in col_norm or col_norm in ("lot", "bno", "lotno")
    if field == "item_name":
        return any(k in col_norm for k in ("item", "product", "description", "particular", "medicine", "goods", "drug", "article", "name"))
    return False


def _classify_columns(columns: List[str]) -> Dict[str, str]:
    """Return {purchase_field: source_column}. Each column is used at most once."""
    mapping: Dict[str, str] = {}
    used: set[str] = set()
    for field in _FIELD_ORDER:
        for col in columns:
            if col in used:
                continue
            if _matches(_norm(col), field):
                mapping[field] = col
                used.add(col)
                break
    return mapping


def _to_number(val: Any) -> Optional[float]:
    """Parse '1,234.50', '₹120', '12%' → float. Returns None when not numeric."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = re.sub(r"[^0-9.\-]", "", str(val))
    if s in ("", "-", ".", "-."):
        return None
    try:
        return float(s)
    except ValueError:
        return None


_DATE_PATTERNS = [
    ("%Y-%m-%d", False), ("%d-%m-%Y", False), ("%d/%m/%Y", False),
    ("%d.%m.%Y", False), ("%d-%m-%y", False), ("%d/%m/%y", False),
    ("%m/%d/%Y", False), ("%Y/%m/%d", False),
    ("%d %b %Y", False), ("%d-%b-%Y", False), ("%d-%b-%y", False),
    ("%b %Y", True), ("%b-%Y", True), ("%m/%Y", True), ("%m-%Y", True),
    ("%m/%y", True), ("%m-%y", True),
]


def _to_iso_date(val: Any) -> Optional[str]:
    """Parse common invoice / expiry date strings → 'YYYY-MM-DD'.

    Month-only expiries (e.g. '07/26', 'Jul 2026') map to the 1st of that month.
    """
    if not val:
        return None
    from datetime import datetime
    s = str(val).strip()
    for fmt, month_only in _DATE_PATTERNS:
        try:
            dt = datetime.strptime(s, fmt)
        except ValueError:
            continue
        if month_only:
            return date(dt.year, dt.month, 1).isoformat()
        return dt.date().isoformat()
    return None


def _match_supplier(db: Session, name: Optional[str]) -> tuple[Optional[int], Optional[str]]:
    """Best-effort match of an extracted company name to a Distributor party."""
    if not name:
        return None, None
    target = _norm(name)
    if len(target) < 3:
        return None, None
    parties = (
        db.query(PartyMaster.id, PartyMaster.party_name)
        .filter(PartyMaster.party_type == "Distributor")
        .all()
    )
    # exact normalised match first
    for pid, pname in parties:
        if _norm(pname) == target:
            return pid, pname
    # then containment either direction (longest match wins)
    best: tuple[Optional[int], Optional[str], int] = (None, None, 0)
    for pid, pname in parties:
        pn = _norm(pname)
        if not pn:
            continue
        if pn in target or target in pn:
            score = min(len(pn), len(target))
            if score > best[2]:
                best = (pid, pname, score)
    return best[0], best[1]


def _match_item(name: Optional[str], items: List[tuple]) -> tuple[Optional[int], Optional[str]]:
    """Match an extracted item name to item_master. `items` = [(id, name, generic, brand)]."""
    if not name:
        return None, None
    target = _norm(name)
    if len(target) < 3:
        return None, None
    for iid, iname, _generic, _brand in items:
        if _norm(iname) == target:
            return iid, iname
    best: tuple[Optional[int], Optional[str], int] = (None, None, 0)
    for iid, iname, generic, brand in items:
        for cand in (iname, generic, brand):
            cn = _norm(cand)
            if len(cn) < 3:
                continue
            if cn in target or target in cn:
                score = min(len(cn), len(target))
                if score > best[2]:
                    best = (iid, iname, score)
    return best[0], best[1]


def map_extraction_to_purchase(extraction: Dict[str, Any], db: Session) -> Dict[str, Any]:
    """
    Convert a raw PdfExtractor result into a purchase-form prefill payload.

    Returns:
        {
          "header": {supplier_id, supplier_name_guess, invoice_no, invoice_date},
          "items":  [{item_id, extracted_name, matched_name, batch_no, quantity,
                      free_quantity, purchase_rate, mrp, sale_rate, discount,
                      gst_percent, expiry_date}],
          "unmatched_count": int,
          "raw": {...original extraction...}
        }
    """
    header_raw = extraction.get("header") or {}
    columns    = extraction.get("table_columns") or []
    rows       = extraction.get("items") or []

    col_map = _classify_columns([c for c in columns if c])

    # ── Header ────────────────────────────────────────────────────────────────
    company = header_raw.get("company_name") or header_raw.get("supplier") or header_raw.get("seller")
    invoice_no = (
        header_raw.get("invoice_no")
        or header_raw.get("invoice_number")
        or header_raw.get("bill_no")
        or header_raw.get("invoice")
    )
    invoice_date = _to_iso_date(
        header_raw.get("date")
        or header_raw.get("invoice_date")
        or header_raw.get("bill_date")
    )
    supplier_id, supplier_name = _match_supplier(db, company)

    # ── Items ─────────────────────────────────────────────────────────────────
    item_rows = db.query(
        ItemMaster.id, ItemMaster.item_name, ItemMaster.generic_name, ItemMaster.brand_name
    ).all()

    mapped_items: List[Dict[str, Any]] = []
    unmatched = 0
    for row in rows:
        if not isinstance(row, dict):
            continue

        def cell(field: str) -> Any:
            col = col_map.get(field)
            return row.get(col) if col else None

        extracted_name = cell("item_name")
        item_id, matched_name = _match_item(extracted_name, item_rows)
        if extracted_name and item_id is None:
            unmatched += 1

        batch_val = cell("batch_no")
        mapped_items.append({
            "item_id":        item_id,
            "extracted_name": str(extracted_name).strip() if extracted_name else None,
            "matched_name":   matched_name,
            "batch_no":       str(batch_val).strip() if batch_val else None,
            "quantity":       _to_number(cell("quantity")),
            "free_quantity":  _to_number(cell("free_quantity")),
            "purchase_rate":  _to_number(cell("purchase_rate")),
            "mrp":            _to_number(cell("mrp")),
            "sale_rate":      _to_number(cell("sale_rate")),
            "discount":       _to_number(cell("discount")),
            "gst_percent":    _to_number(cell("gst_percent")),
            "expiry_date":    _to_iso_date(cell("expiry_date")),
        })

    # Drop rows that carry no usable signal at all (no name, no qty, no rate).
    mapped_items = [
        it for it in mapped_items
        if it["extracted_name"] or it["quantity"] is not None or it["purchase_rate"] is not None
    ]

    return {
        "header": {
            "supplier_id":         supplier_id,
            "supplier_name_guess": supplier_name or (str(company).strip() if company else None),
            "invoice_no":          str(invoice_no).strip() if invoice_no else None,
            "invoice_date":        invoice_date,
        },
        "items":           mapped_items,
        "unmatched_count": unmatched,
        "column_map":      col_map,
        "raw":             extraction,
    }
