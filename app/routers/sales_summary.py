"""
Sales Day Summary (/api/v1/sales-summary)
─────────────────────────────────────────
A point-of-sale "day book / Z-report" for sales. Works for a single date or
any date range (calendar pick). Nets returns against sales and shows how money
was collected.

  GET /sales-summary?date_from=&date_to=
      • both omitted  → today
      • only one set  → that single day
      • both set      → inclusive range
"""
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.auth.deps import get_tenant_db as get_db
from app.models.item_master import ItemMaster
from app.models.party_master import PartyMaster
from app.models.payment_mode_master import PaymentModeMaster
from app.models.purchase_payment import PaymentMaster
from app.models.sales_master import SalesItem, SalesMaster
from app.models.sales_return import SalesReturnItem, SalesReturnMaster

router = APIRouter(prefix="/sales-summary", tags=["Sales Summary"])


def _f(v) -> float:
    return round(float(v), 2) if v is not None else 0.0


def _resolve(date_from: Optional[date], date_to: Optional[date]):
    today = date.today()
    if not date_from and not date_to:
        return today, today
    start = date_from or date_to
    end = date_to or date_from
    if start > end:
        start, end = end, start
    return start, end


def _fill_daily(sales_rows, return_rows, start: date, end: date):
    sales_by = {r[0]: (r[1], r[2]) for r in sales_rows if r[0] is not None}
    ret_by = {r[0]: r[1] for r in return_rows if r[0] is not None}
    span = (end - start).days
    if span > 180:
        start = end - timedelta(days=180)
        span = 180
    out = []
    for i in range(span + 1):
        d = start + timedelta(days=i)
        sv, sc = sales_by.get(d, (0, 0))
        rv = ret_by.get(d, 0)
        out.append({
            "date": d.isoformat(),
            "sales": _f(sv),
            "returns": _f(rv),
            "net": _f((sv or 0) - (rv or 0)),
            "bills": int(sc or 0),
        })
    return out


@router.get("")
@router.get("/")
def day_summary(
    date_from: Optional[date] = Query(None),
    date_to:   Optional[date] = Query(None),
    db:        Session        = Depends(get_db),
):
    start, end = _resolve(date_from, date_to)
    single = start == end
    s_rng = (SalesMaster.invoice_date >= start, SalesMaster.invoice_date <= end)
    r_rng = (SalesReturnMaster.return_date >= start, SalesReturnMaster.return_date <= end)

    gross, discount, tax, bills, customers = (
        db.query(
            func.coalesce(func.sum(SalesMaster.net_amount), 0),
            func.coalesce(func.sum(SalesMaster.discount), 0),
            func.coalesce(func.sum(SalesMaster.tax_amount), 0),
            func.count(SalesMaster.id),
            func.count(func.distinct(SalesMaster.customer_id)),
        )
        .filter(*s_rng)
        .one()
    )

    items_sold = (
        db.query(func.coalesce(func.sum(SalesItem.quantity), 0))
        .join(SalesMaster, SalesItem.sales_id == SalesMaster.id)
        .filter(*s_rng)
        .scalar()
    )

    returns_value, return_count = (
        db.query(
            func.coalesce(func.sum(SalesReturnMaster.total_amount), 0),
            func.count(SalesReturnMaster.id),
        )
        .filter(*r_rng)
        .one()
    )
    items_returned = (
        db.query(func.coalesce(func.sum(SalesReturnItem.quantity), 0))
        .join(SalesReturnMaster, SalesReturnItem.return_id == SalesReturnMaster.id)
        .filter(*r_rng)
        .scalar()
    )

    bill_count = int(bills or 0)
    gross_f = _f(gross)
    returns_f = _f(returns_value)

    # Payment status split (from the sales themselves)
    status_rows = (
        db.query(
            SalesMaster.payment_status,
            func.count(SalesMaster.id),
            func.coalesce(func.sum(SalesMaster.net_amount), 0),
        )
        .filter(*s_rng)
        .group_by(SalesMaster.payment_status)
        .all()
    )

    # Collections by payment mode (actual receipts in the window)
    mode_rows = (
        db.query(
            func.coalesce(PaymentModeMaster.mode_name, "Unspecified"),
            func.coalesce(func.sum(PaymentMaster.amount), 0),
            func.count(PaymentMaster.id),
        )
        .outerjoin(PaymentModeMaster, PaymentMaster.payment_mode_id == PaymentModeMaster.id)
        .filter(
            PaymentMaster.txn_type == "RECEIPT",
            PaymentMaster.txn_date >= start,
            PaymentMaster.txn_date <= end,
        )
        .group_by(PaymentModeMaster.mode_name)
        .all()
    )
    collected = _f(sum((r[1] or Decimal("0")) for r in mode_rows))

    # Daily trend
    sales_daily = (
        db.query(SalesMaster.invoice_date,
                 func.coalesce(func.sum(SalesMaster.net_amount), 0),
                 func.count(SalesMaster.id))
        .filter(*s_rng).group_by(SalesMaster.invoice_date).all()
    )
    returns_daily = (
        db.query(SalesReturnMaster.return_date,
                 func.coalesce(func.sum(SalesReturnMaster.total_amount), 0))
        .filter(*r_rng).group_by(SalesReturnMaster.return_date).all()
    )

    # Top items
    top_items = (
        db.query(ItemMaster.item_name,
                 func.coalesce(func.sum(SalesItem.quantity), 0),
                 func.coalesce(func.sum(SalesItem.total), 0))
        .join(SalesMaster, SalesItem.sales_id == SalesMaster.id)
        .join(ItemMaster, SalesItem.item_id == ItemMaster.id)
        .filter(*s_rng)
        .group_by(ItemMaster.item_name)
        .order_by(func.sum(SalesItem.total).desc())
        .limit(10)
        .all()
    )

    # Bills list
    bill_rows = (
        db.query(SalesMaster, PartyMaster.party_name, PaymentModeMaster.mode_name,
                 func.count(SalesItem.id))
        .outerjoin(PartyMaster, SalesMaster.customer_id == PartyMaster.id)
        .outerjoin(PaymentModeMaster, SalesMaster.payment_mode_id == PaymentModeMaster.id)
        .outerjoin(SalesItem, SalesItem.sales_id == SalesMaster.id)
        .filter(*s_rng)
        .group_by(SalesMaster.id, PartyMaster.party_name, PaymentModeMaster.mode_name)
        .order_by(SalesMaster.invoice_date.desc(), SalesMaster.id.desc())
        .all()
    )

    # Returns list
    return_list = (
        db.query(SalesReturnMaster, PartyMaster.party_name)
        .outerjoin(PartyMaster, SalesReturnMaster.customer_id == PartyMaster.id)
        .filter(*r_rng)
        .order_by(SalesReturnMaster.return_date.desc(), SalesReturnMaster.id.desc())
        .all()
    )

    return {
        "range": {"from": start.isoformat(), "to": end.isoformat(), "single_day": single},
        "summary": {
            "gross_sales":    gross_f,
            "returns":        returns_f,
            "net_sales":      round(gross_f - returns_f, 2),
            "bill_count":     bill_count,
            "return_count":   int(return_count or 0),
            "items_sold":     _f(items_sold),
            "items_returned": _f(items_returned),
            "discount":       _f(discount),
            "tax":            _f(tax),
            "avg_bill":       round(gross_f / bill_count, 2) if bill_count else 0.0,
            "unique_customers": int(customers or 0),
            "collected":      collected,
        },
        "payment_status": [
            {"status": s or "Unknown", "count": int(c or 0), "amount": _f(a)}
            for s, c, a in status_rows
        ],
        "payment_modes": [
            {"mode": m, "amount": _f(a), "count": int(c or 0)}
            for m, a, c in mode_rows
        ],
        "daily": _fill_daily(sales_daily, returns_daily, start, end),
        "top_items": [
            {"item_name": n, "qty": _f(q), "revenue": _f(r)}
            for n, q, r in top_items
        ],
        "bills": [
            {
                "id": s.id,
                "invoice_no": s.invoice_no or f"#{s.id}",
                "invoice_date": s.invoice_date.isoformat() if s.invoice_date else None,
                "customer_name": name or "Walk-in",
                "items": int(icount or 0),
                "gross": _f(s.total_amount),
                "discount": _f(s.discount),
                "tax": _f(s.tax_amount),
                "net": _f(s.net_amount),
                "payment_status": s.payment_status,
                "payment_mode": mode,
            }
            for s, name, mode, icount in bill_rows
        ],
        "returns": [
            {
                "id": r.id,
                "return_no": r.return_no or f"#{r.id}",
                "return_date": r.return_date.isoformat() if r.return_date else None,
                "customer_name": name or "Walk-in",
                "amount": _f(r.total_amount),
                "refund_amount": _f(r.refund_amount),
                "reason": r.reason,
            }
            for r, name in return_list
        ],
    }
