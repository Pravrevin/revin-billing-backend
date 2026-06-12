"""
Reports API — aggregated business intelligence over sales, purchases, stock.

All endpoints are read-only and return plain dicts (FastAPI's jsonable_encoder
turns Decimal → float and date → ISO string automatically). Numbers are
rounded to 2 dp on the way out so the UI never has to guess.

Date filters use the document's `invoice_date`. When omitted, the range
defaults to the last 30 days ending today.
"""
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth.deps import get_tenant_db as get_db, require_menu
from app.models.item_master import ItemMaster
from app.models.party_master import PartyMaster
from app.models.purchase_master import PurchaseItem, PurchaseMaster
from app.models.sales_master import SalesItem, SalesMaster
from app.models.stock_master import StockMaster

# Menu 7 = Reports (see frontend menus.ts)
router = APIRouter(prefix="/reports", tags=["Reports"], dependencies=[Depends(require_menu(7))])

NEAR_EXPIRY_DAYS = 30


# ── Helpers ──────────────────────────────────────────────────────────────────

def _f(value) -> float:
    """Decimal/None → rounded float."""
    if value is None:
        return 0.0
    return round(float(value), 2)


def _resolve_range(date_from: Optional[date], date_to: Optional[date]):
    """Default to the trailing 30 days when no range is supplied."""
    today = date.today()
    end = date_to or today
    start = date_from or (end - timedelta(days=29))
    if start > end:
        start, end = end, start
    return start, end


def _fill_daily(rows, start: date, end: date):
    """
    Turn sparse (date, total, count) rows into a continuous day-by-day series
    so the chart has no gaps. Caps the range at 180 points to stay light.
    """
    by_day = {r[0]: (r[1], r[2]) for r in rows if r[0] is not None}
    span = (end - start).days
    if span > 180:                       # keep the payload sane for long ranges
        start = end - timedelta(days=180)
        span = 180
    series = []
    for i in range(span + 1):
        day = start + timedelta(days=i)
        total, count = by_day.get(day, (0, 0))
        series.append({
            "date": day.isoformat(),
            "total": _f(total),
            "count": int(count or 0),
        })
    return series


# ── Sales Report ─────────────────────────────────────────────────────────────

@router.get("/sales")
def sales_report(
    date_from: Optional[date] = Query(None),
    date_to:   Optional[date] = Query(None),
    db:        Session        = Depends(get_db),
):
    start, end = _resolve_range(date_from, date_to)
    rng = (SalesMaster.invoice_date >= start, SalesMaster.invoice_date <= end)

    gross, net, disc, tax, bills, customers = (
        db.query(
            func.coalesce(func.sum(SalesMaster.total_amount), 0),
            func.coalesce(func.sum(SalesMaster.net_amount), 0),
            func.coalesce(func.sum(SalesMaster.discount), 0),
            func.coalesce(func.sum(SalesMaster.tax_amount), 0),
            func.count(SalesMaster.id),
            func.count(func.distinct(SalesMaster.customer_id)),
        )
        .filter(*rng)
        .one()
    )

    qty_sold = (
        db.query(func.coalesce(func.sum(SalesItem.quantity), 0))
        .join(SalesMaster, SalesItem.sales_id == SalesMaster.id)
        .filter(*rng)
        .scalar()
    )

    daily_rows = (
        db.query(
            SalesMaster.invoice_date,
            func.coalesce(func.sum(SalesMaster.net_amount), 0),
            func.count(SalesMaster.id),
        )
        .filter(*rng)
        .group_by(SalesMaster.invoice_date)
        .all()
    )

    top_items = (
        db.query(
            ItemMaster.id,
            ItemMaster.item_name,
            func.coalesce(func.sum(SalesItem.quantity), 0),
            func.coalesce(func.sum(SalesItem.total), 0),
        )
        .join(SalesMaster, SalesItem.sales_id == SalesMaster.id)
        .join(ItemMaster, SalesItem.item_id == ItemMaster.id)
        .filter(*rng)
        .group_by(ItemMaster.id, ItemMaster.item_name)
        .order_by(func.sum(SalesItem.total).desc())
        .limit(10)
        .all()
    )

    pay_rows = (
        db.query(
            SalesMaster.payment_status,
            func.count(SalesMaster.id),
            func.coalesce(func.sum(SalesMaster.net_amount), 0),
        )
        .filter(*rng)
        .group_by(SalesMaster.payment_status)
        .all()
    )

    recent = (
        db.query(SalesMaster, PartyMaster.party_name)
        .outerjoin(PartyMaster, SalesMaster.customer_id == PartyMaster.id)
        .filter(*rng)
        .order_by(SalesMaster.invoice_date.desc().nullslast(), SalesMaster.id.desc())
        .limit(8)
        .all()
    )

    bill_count = int(bills or 0)
    net_f = _f(net)
    return {
        "range": {"from": start.isoformat(), "to": end.isoformat()},
        "summary": {
            "net_sales":        net_f,
            "gross_sales":      _f(gross),
            "discount":         _f(disc),
            "tax":              _f(tax),
            "bill_count":       bill_count,
            "avg_bill":         round(net_f / bill_count, 2) if bill_count else 0.0,
            "qty_sold":         _f(qty_sold),
            "unique_customers": int(customers or 0),
        },
        "daily": _fill_daily(daily_rows, start, end),
        "top_items": [
            {"item_id": i, "item_name": n, "qty": _f(q), "revenue": _f(r)}
            for i, n, q, r in top_items
        ],
        "payment_breakdown": [
            {"status": s or "Unknown", "count": int(c or 0), "amount": _f(a)}
            for s, c, a in pay_rows
        ],
        "recent": [
            {
                "id": s.id,
                "invoice_no": s.invoice_no,
                "invoice_date": s.invoice_date.isoformat() if s.invoice_date else None,
                "customer_name": name or "Walk-in",
                "net_amount": _f(s.net_amount),
                "payment_status": s.payment_status,
            }
            for s, name in recent
        ],
    }


# ── Purchase Report ──────────────────────────────────────────────────────────

@router.get("/purchase")
def purchase_report(
    date_from: Optional[date] = Query(None),
    date_to:   Optional[date] = Query(None),
    db:        Session        = Depends(get_db),
):
    start, end = _resolve_range(date_from, date_to)
    rng = (PurchaseMaster.invoice_date >= start, PurchaseMaster.invoice_date <= end)

    gross, net, disc, tax, bills, suppliers = (
        db.query(
            func.coalesce(func.sum(PurchaseMaster.total_amount), 0),
            func.coalesce(func.sum(PurchaseMaster.net_amount), 0),
            func.coalesce(func.sum(PurchaseMaster.discount_amount), 0),
            func.coalesce(func.sum(PurchaseMaster.tax_amount), 0),
            func.count(PurchaseMaster.id),
            func.count(func.distinct(PurchaseMaster.supplier_id)),
        )
        .filter(*rng)
        .one()
    )

    qty_bought = (
        db.query(func.coalesce(func.sum(PurchaseItem.quantity), 0))
        .join(PurchaseMaster, PurchaseItem.purchase_id == PurchaseMaster.id)
        .filter(*rng)
        .scalar()
    )

    daily_rows = (
        db.query(
            PurchaseMaster.invoice_date,
            func.coalesce(func.sum(PurchaseMaster.net_amount), 0),
            func.count(PurchaseMaster.id),
        )
        .filter(*rng)
        .group_by(PurchaseMaster.invoice_date)
        .all()
    )

    top_suppliers = (
        db.query(
            PartyMaster.id,
            PartyMaster.party_name,
            func.coalesce(func.sum(PurchaseMaster.net_amount), 0),
            func.count(PurchaseMaster.id),
        )
        .join(PartyMaster, PurchaseMaster.supplier_id == PartyMaster.id)
        .filter(*rng)
        .group_by(PartyMaster.id, PartyMaster.party_name)
        .order_by(func.sum(PurchaseMaster.net_amount).desc())
        .limit(10)
        .all()
    )

    top_items = (
        db.query(
            ItemMaster.id,
            ItemMaster.item_name,
            func.coalesce(func.sum(PurchaseItem.quantity), 0),
            func.coalesce(func.sum(PurchaseItem.total), 0),
        )
        .join(PurchaseMaster, PurchaseItem.purchase_id == PurchaseMaster.id)
        .join(ItemMaster, PurchaseItem.item_id == ItemMaster.id)
        .filter(*rng)
        .group_by(ItemMaster.id, ItemMaster.item_name)
        .order_by(func.sum(PurchaseItem.total).desc())
        .limit(10)
        .all()
    )

    recent = (
        db.query(PurchaseMaster, PartyMaster.party_name)
        .outerjoin(PartyMaster, PurchaseMaster.supplier_id == PartyMaster.id)
        .filter(*rng)
        .order_by(PurchaseMaster.invoice_date.desc().nullslast(), PurchaseMaster.id.desc())
        .limit(8)
        .all()
    )

    bill_count = int(bills or 0)
    net_f = _f(net)
    return {
        "range": {"from": start.isoformat(), "to": end.isoformat()},
        "summary": {
            "net_purchase":     net_f,
            "gross_purchase":   _f(gross),
            "discount":         _f(disc),
            "tax":              _f(tax),
            "bill_count":       bill_count,
            "avg_bill":         round(net_f / bill_count, 2) if bill_count else 0.0,
            "qty_bought":       _f(qty_bought),
            "unique_suppliers": int(suppliers or 0),
        },
        "daily": _fill_daily(daily_rows, start, end),
        "top_suppliers": [
            {"supplier_id": i, "name": n, "amount": _f(a), "bills": int(c or 0)}
            for i, n, a, c in top_suppliers
        ],
        "top_items": [
            {"item_id": i, "item_name": n, "qty": _f(q), "amount": _f(a)}
            for i, n, q, a in top_items
        ],
        "recent": [
            {
                "id": p.id,
                "invoice_no": p.invoice_no,
                "invoice_date": p.invoice_date.isoformat() if p.invoice_date else None,
                "supplier_name": name or "—",
                "net_amount": _f(p.net_amount),
            }
            for p, name in recent
        ],
    }


# ── Profit Report ────────────────────────────────────────────────────────────

def _cost_lookup(db: Session):
    """(item_id, batch_no) → purchase_rate, from the current stock book."""
    lookup = {}
    for item_id, batch, rate in db.query(
        StockMaster.item_id, StockMaster.batch_no, StockMaster.purchase_rate
    ).all():
        lookup[(item_id, batch)] = rate or Decimal("0")
    return lookup


@router.get("/profit")
def profit_report(
    date_from: Optional[date] = Query(None),
    date_to:   Optional[date] = Query(None),
    db:        Session        = Depends(get_db),
):
    start, end = _resolve_range(date_from, date_to)
    costs = _cost_lookup(db)

    rows = (
        db.query(
            SalesItem.item_id,
            SalesItem.batch_no,
            SalesItem.quantity,
            SalesItem.total,
            SalesItem.tax_amount,
            SalesMaster.invoice_date,
            ItemMaster.item_name,
        )
        .join(SalesMaster, SalesItem.sales_id == SalesMaster.id)
        .join(ItemMaster, SalesItem.item_id == ItemMaster.id)
        .filter(SalesMaster.invoice_date >= start, SalesMaster.invoice_date <= end)
        .all()
    )

    total_rev = total_cost = Decimal("0")
    by_day: dict = {}
    by_item: dict = {}
    for item_id, batch, qty, total, tax, inv_date, name in rows:
        qty = qty or Decimal("0")
        rev = (total or Decimal("0")) - (tax or Decimal("0"))   # revenue ex-tax
        cost = qty * costs.get((item_id, batch), Decimal("0"))
        profit = rev - cost
        total_rev += rev
        total_cost += cost

        if inv_date is not None:
            d = by_day.setdefault(inv_date, Decimal("0"))
            by_day[inv_date] = d + profit

        agg = by_item.setdefault(item_id, {"name": name, "rev": Decimal("0"),
                                           "cost": Decimal("0"), "qty": Decimal("0")})
        agg["rev"] += rev
        agg["cost"] += cost
        agg["qty"] += qty

    gross_profit = total_rev - total_cost
    margin = float(gross_profit / total_rev * 100) if total_rev else 0.0

    daily_rows = [(d, by_day[d], 0) for d in by_day]

    top = sorted(by_item.values(), key=lambda a: a["rev"] - a["cost"], reverse=True)[:10]

    return {
        "range": {"from": start.isoformat(), "to": end.isoformat()},
        "summary": {
            "revenue":      _f(total_rev),
            "cost":         _f(total_cost),
            "gross_profit": _f(gross_profit),
            "margin_pct":   round(margin, 2),
            "lines":        len(rows),
        },
        "daily": _fill_daily(daily_rows, start, end),
        "top_items": [
            {
                "item_name": a["name"],
                "qty":       _f(a["qty"]),
                "revenue":   _f(a["rev"]),
                "cost":      _f(a["cost"]),
                "profit":    _f(a["rev"] - a["cost"]),
                "margin_pct": round(float((a["rev"] - a["cost"]) / a["rev"] * 100), 2)
                              if a["rev"] else 0.0,
            }
            for a in top
        ],
    }


# ── Daily Report ─────────────────────────────────────────────────────────────

@router.get("/daily")
def daily_report(
    day: Optional[date] = Query(None),
    db:  Session        = Depends(get_db),
):
    target = day or date.today()

    s_net, s_gross, s_tax, s_bills = (
        db.query(
            func.coalesce(func.sum(SalesMaster.net_amount), 0),
            func.coalesce(func.sum(SalesMaster.total_amount), 0),
            func.coalesce(func.sum(SalesMaster.tax_amount), 0),
            func.count(SalesMaster.id),
        )
        .filter(SalesMaster.invoice_date == target)
        .one()
    )

    p_net, p_bills = (
        db.query(
            func.coalesce(func.sum(PurchaseMaster.net_amount), 0),
            func.count(PurchaseMaster.id),
        )
        .filter(PurchaseMaster.invoice_date == target)
        .one()
    )

    pay_rows = (
        db.query(
            SalesMaster.payment_status,
            func.count(SalesMaster.id),
            func.coalesce(func.sum(SalesMaster.net_amount), 0),
        )
        .filter(SalesMaster.invoice_date == target)
        .group_by(SalesMaster.payment_status)
        .all()
    )

    top_items = (
        db.query(
            ItemMaster.item_name,
            func.coalesce(func.sum(SalesItem.quantity), 0),
            func.coalesce(func.sum(SalesItem.total), 0),
        )
        .join(SalesMaster, SalesItem.sales_id == SalesMaster.id)
        .join(ItemMaster, SalesItem.item_id == ItemMaster.id)
        .filter(SalesMaster.invoice_date == target)
        .group_by(ItemMaster.item_name)
        .order_by(func.sum(SalesItem.total).desc())
        .limit(10)
        .all()
    )

    bills = (
        db.query(SalesMaster, PartyMaster.party_name)
        .outerjoin(PartyMaster, SalesMaster.customer_id == PartyMaster.id)
        .filter(SalesMaster.invoice_date == target)
        .order_by(SalesMaster.id.desc())
        .limit(20)
        .all()
    )

    return {
        "day": target.isoformat(),
        "summary": {
            "sales_net":     _f(s_net),
            "sales_gross":   _f(s_gross),
            "sales_tax":     _f(s_tax),
            "sales_bills":   int(s_bills or 0),
            "purchase_net":  _f(p_net),
            "purchase_bills": int(p_bills or 0),
            "net_cash":      _f((s_net or 0) - (p_net or 0)),
        },
        "payment_breakdown": [
            {"status": s or "Unknown", "count": int(c or 0), "amount": _f(a)}
            for s, c, a in pay_rows
        ],
        "top_items": [
            {"item_name": n, "qty": _f(q), "revenue": _f(r)}
            for n, q, r in top_items
        ],
        "bills": [
            {
                "id": s.id,
                "invoice_no": s.invoice_no,
                "customer_name": name or "Walk-in",
                "net_amount": _f(s.net_amount),
                "payment_status": s.payment_status,
            }
            for s, name in bills
        ],
    }


# ── GST Report ───────────────────────────────────────────────────────────────

@router.get("/gst")
def gst_report(
    date_from: Optional[date] = Query(None),
    date_to:   Optional[date] = Query(None),
    db:        Session        = Depends(get_db),
):
    start, end = _resolve_range(date_from, date_to)

    # Output GST (on sales). taxable = total − tax.
    out_rows = (
        db.query(
            SalesItem.gst_percent,
            func.coalesce(func.sum(SalesItem.total - func.coalesce(SalesItem.tax_amount, 0)), 0),
            func.coalesce(func.sum(SalesItem.tax_amount), 0),
        )
        .join(SalesMaster, SalesItem.sales_id == SalesMaster.id)
        .filter(SalesMaster.invoice_date >= start, SalesMaster.invoice_date <= end)
        .group_by(SalesItem.gst_percent)
        .order_by(SalesItem.gst_percent)
        .all()
    )

    # Input GST (on purchases).
    in_rows = (
        db.query(
            PurchaseItem.gst_percent,
            func.coalesce(func.sum(PurchaseItem.total - func.coalesce(PurchaseItem.tax_amount, 0)), 0),
            func.coalesce(func.sum(PurchaseItem.tax_amount), 0),
        )
        .join(PurchaseMaster, PurchaseItem.purchase_id == PurchaseMaster.id)
        .filter(PurchaseMaster.invoice_date >= start, PurchaseMaster.invoice_date <= end)
        .group_by(PurchaseItem.gst_percent)
        .order_by(PurchaseItem.gst_percent)
        .all()
    )

    def _slabs(rows):
        out = []
        for rate, taxable, tax in rows:
            tax_f = _f(tax)
            out.append({
                "rate":    _f(rate),
                "taxable": _f(taxable),
                "cgst":    round(tax_f / 2, 2),
                "sgst":    round(tax_f / 2, 2),
                "tax":     tax_f,
            })
        return out

    output_slabs = _slabs(out_rows)
    input_slabs = _slabs(in_rows)
    output_total = round(sum(s["tax"] for s in output_slabs), 2)
    input_total = round(sum(s["tax"] for s in input_slabs), 2)

    return {
        "range": {"from": start.isoformat(), "to": end.isoformat()},
        "summary": {
            "output_gst": output_total,
            "input_gst":  input_total,
            "net_payable": round(output_total - input_total, 2),
        },
        "output_slabs": output_slabs,
        "input_slabs": input_slabs,
    }


# ── Inventory Report ─────────────────────────────────────────────────────────

@router.get("/inventory")
def inventory_report(db: Session = Depends(get_db)):
    today = date.today()
    near_cut = today + timedelta(days=NEAR_EXPIRY_DAYS)

    items, batches, total_qty, val_cost, val_mrp = (
        db.query(
            func.count(func.distinct(StockMaster.item_id)),
            func.count(StockMaster.id),
            func.coalesce(func.sum(StockMaster.quantity), 0),
            func.coalesce(func.sum(StockMaster.quantity * func.coalesce(StockMaster.purchase_rate, 0)), 0),
            func.coalesce(func.sum(StockMaster.quantity * func.coalesce(StockMaster.mrp, 0)), 0),
        )
        .filter(StockMaster.quantity > 0)
        .one()
    )

    out_of_stock = (
        db.query(func.count(StockMaster.id))
        .filter(StockMaster.quantity <= 0)
        .scalar()
    )
    expired = (
        db.query(func.count(StockMaster.id))
        .filter(StockMaster.quantity > 0, StockMaster.expiry_date < today)
        .scalar()
    )
    near_expiry = (
        db.query(func.count(StockMaster.id))
        .filter(
            StockMaster.quantity > 0,
            StockMaster.expiry_date >= today,
            StockMaster.expiry_date <= near_cut,
        )
        .scalar()
    )

    top_value = (
        db.query(
            ItemMaster.item_name,
            func.coalesce(func.sum(StockMaster.quantity), 0),
            func.coalesce(func.sum(StockMaster.quantity * func.coalesce(StockMaster.purchase_rate, 0)), 0),
        )
        .join(ItemMaster, StockMaster.item_id == ItemMaster.id)
        .filter(StockMaster.quantity > 0)
        .group_by(ItemMaster.item_name)
        .order_by(func.sum(StockMaster.quantity * func.coalesce(StockMaster.purchase_rate, 0)).desc())
        .limit(10)
        .all()
    )

    category_rows = (
        db.query(
            func.coalesce(ItemMaster.category_name, "Uncategorised"),
            func.coalesce(func.sum(StockMaster.quantity * func.coalesce(StockMaster.purchase_rate, 0)), 0),
        )
        .join(ItemMaster, StockMaster.item_id == ItemMaster.id)
        .filter(StockMaster.quantity > 0)
        .group_by(ItemMaster.category_name)
        .order_by(func.sum(StockMaster.quantity * func.coalesce(StockMaster.purchase_rate, 0)).desc())
        .limit(8)
        .all()
    )

    val_cost_f = _f(val_cost)
    val_mrp_f = _f(val_mrp)
    return {
        "as_of": today.isoformat(),
        "summary": {
            "items_in_stock":   int(items or 0),
            "batches":          int(batches or 0),
            "total_qty":        _f(total_qty),
            "stock_value_cost": val_cost_f,
            "stock_value_mrp":  val_mrp_f,
            "potential_margin": round(val_mrp_f - val_cost_f, 2),
            "out_of_stock":     int(out_of_stock or 0),
            "near_expiry":      int(near_expiry or 0),
            "expired":          int(expired or 0),
        },
        "top_value_items": [
            {"item_name": n, "qty": _f(q), "value": _f(v)}
            for n, q, v in top_value
        ],
        "category_breakdown": [
            {"category": c, "value": _f(v)}
            for c, v in category_rows
        ],
    }
