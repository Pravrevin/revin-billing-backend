"""
Accounts router (/api/v1/accounts)
──────────────────────────────────
Aggregated cash-flow & ledger views for the Accounts / Payments module:

  GET /accounts/overview                 KPI snapshot (payables, receivables, balances)
  GET /accounts/cash-book?date_from&date_to   Cash-mode money in/out with running balance
  GET /accounts/bank-book?date_from&date_to   Bank-mode (UPI/Card/Cheque/…) money in/out
  GET /accounts/day-book?day             Every voucher on a single day
  GET /accounts/supplier-wise            Payments grouped by supplier + outstanding

Money movements come from three sources:
  • RECEIPT payments  → cash/bank IN
  • PAYMENT payments  → cash/bank OUT
  • expenses          → cash/bank OUT
"Cash" = payment mode named 'Cash'. "Bank" = any non-cash, non-credit mode.
"""
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models.expense import ExpenseMaster
from app.models.party_master import PartyMaster
from app.models.payment_mode_master import PaymentModeMaster
from app.models.purchase_master import PurchaseMaster
from app.models.purchase_payment import PartyCreditConfig, PaymentMaster
from app.models.sales_master import SalesMaster

router = APIRouter(prefix="/accounts", tags=["Accounts"])

# Modes that are neither cash nor a real money movement are excluded from books.
_NON_BANK = {"cash", "credit"}


def _f(value) -> float:
    return round(float(value), 2) if value is not None else 0.0


def _mode_class_maps(db: Session):
    """Return (cash_ids, bank_ids) sets based on payment-mode names."""
    cash_ids, bank_ids = set(), set()
    for m in db.query(PaymentModeMaster).all():
        name = (m.mode_name or "").strip().lower()
        if name == "cash":
            cash_ids.add(m.id)
        elif name not in _NON_BANK:
            bank_ids.add(m.id)
    return cash_ids, bank_ids


def _paid_map(db: Session, reference_type: str, txn_type: str):
    """reference_id → total settled, for one txn/reference type."""
    rows = (
        db.query(PaymentMaster.reference_id, func.coalesce(func.sum(PaymentMaster.amount), 0))
        .filter(PaymentMaster.reference_type == reference_type, PaymentMaster.txn_type == txn_type)
        .group_by(PaymentMaster.reference_id)
        .all()
    )
    return {r[0]: (r[1] or Decimal("0")) for r in rows}


def _global_credit_days(db: Session) -> int:
    cfg = db.query(PartyCreditConfig).filter(PartyCreditConfig.party_id.is_(None)).first()
    return cfg.credit_days if cfg else 30


# ── Overview ─────────────────────────────────────────────────────────────────

@router.get("/overview")
def overview(db: Session = Depends(get_db)):
    today = date.today()
    month_start = today.replace(day=1)
    credit_days = _global_credit_days(db)

    purchase_paid = _paid_map(db, "purchase", "PAYMENT")
    sale_recv     = _paid_map(db, "sale", "RECEIPT")

    # Payables — what we owe suppliers
    payables = overdue_payables = Decimal("0")
    payable_bills = overdue_payable_bills = 0
    for p in db.query(PurchaseMaster).all():
        net = p.net_amount or Decimal("0")
        out = max(net - purchase_paid.get(p.id, Decimal("0")), Decimal("0"))
        if out <= 0:
            continue
        payables += out
        payable_bills += 1
        due = p.due_date or ((p.invoice_date + timedelta(days=credit_days)) if p.invoice_date else None)
        if due and today > due:
            overdue_payables += out
            overdue_payable_bills += 1

    # Receivables — what customers owe us
    receivables = overdue_receivables = Decimal("0")
    receivable_bills = overdue_receivable_bills = 0
    for s in db.query(SalesMaster).all():
        net = s.net_amount or Decimal("0")
        out = max(net - sale_recv.get(s.id, Decimal("0")), Decimal("0"))
        if out <= 0:
            continue
        receivables += out
        receivable_bills += 1
        due = (s.invoice_date + timedelta(days=credit_days)) if s.invoice_date else None
        if due and today > due:
            overdue_receivables += out
            overdue_receivable_bills += 1

    # Cash / Bank balances (all-time): receipts IN − payments OUT − expenses OUT
    cash_ids, bank_ids = _mode_class_maps(db)

    def _flow(ids):
        if not ids:
            return Decimal("0"), Decimal("0")
        receipts = db.query(func.coalesce(func.sum(PaymentMaster.amount), 0)).filter(
            PaymentMaster.txn_type == "RECEIPT", PaymentMaster.payment_mode_id.in_(ids)
        ).scalar() or Decimal("0")
        payments = db.query(func.coalesce(func.sum(PaymentMaster.amount), 0)).filter(
            PaymentMaster.txn_type == "PAYMENT", PaymentMaster.payment_mode_id.in_(ids)
        ).scalar() or Decimal("0")
        expenses = db.query(func.coalesce(func.sum(ExpenseMaster.amount), 0)).filter(
            ExpenseMaster.payment_mode_id.in_(ids)
        ).scalar() or Decimal("0")
        return receipts, payments + expenses

    cash_in, cash_out = _flow(cash_ids)
    bank_in, bank_out = _flow(bank_ids)

    # Today's flow (all modes)
    today_in = db.query(func.coalesce(func.sum(PaymentMaster.amount), 0)).filter(
        PaymentMaster.txn_type == "RECEIPT", PaymentMaster.txn_date == today
    ).scalar() or Decimal("0")
    today_pay = db.query(func.coalesce(func.sum(PaymentMaster.amount), 0)).filter(
        PaymentMaster.txn_type == "PAYMENT", PaymentMaster.txn_date == today
    ).scalar() or Decimal("0")
    today_exp = db.query(func.coalesce(func.sum(ExpenseMaster.amount), 0)).filter(
        ExpenseMaster.expense_date == today
    ).scalar() or Decimal("0")

    month_exp = db.query(func.coalesce(func.sum(ExpenseMaster.amount), 0)).filter(
        ExpenseMaster.expense_date >= month_start, ExpenseMaster.expense_date <= today
    ).scalar() or Decimal("0")

    payments_count = db.query(func.count(PaymentMaster.id)).scalar() or 0
    expenses_count = db.query(func.count(ExpenseMaster.id)).scalar() or 0

    return {
        "as_of": today.isoformat(),
        "payables": {
            "outstanding": _f(payables),
            "overdue":     _f(overdue_payables),
            "bills":       payable_bills,
            "overdue_bills": overdue_payable_bills,
        },
        "receivables": {
            "outstanding": _f(receivables),
            "overdue":     _f(overdue_receivables),
            "bills":       receivable_bills,
            "overdue_bills": overdue_receivable_bills,
        },
        "balances": {
            "cash_in_hand": _f(cash_in - cash_out),
            "bank_balance": _f(bank_in - bank_out),
        },
        "today": {
            "money_in":  _f(today_in),
            "money_out": _f(today_pay + today_exp),
            "net":       _f(today_in - today_pay - today_exp),
        },
        "month_expenses": _f(month_exp),
        "net_position":   _f(receivables - payables),
        "counts": {"payments": int(payments_count), "expenses": int(expenses_count)},
    }


# ── Cash / Bank book ───────────────────────────────────────────────────────────

def _book(db: Session, mode_ids: set, start: date, end: date):
    """
    Build a money-in / money-out statement with opening + running balance for the
    given set of payment-mode ids over [start, end].
    """
    if not mode_ids:
        return {
            "opening_balance": 0.0, "rows": [],
            "total_in": 0.0, "total_out": 0.0, "closing_balance": 0.0,
        }

    # Opening balance = everything strictly before `start`
    def _sum_before(model, date_col, type_filter):
        q = db.query(func.coalesce(func.sum(model.amount), 0)).filter(date_col < start)
        for f in type_filter:
            q = q.filter(f)
        return q.scalar() or Decimal("0")

    opening = (
        _sum_before(PaymentMaster, PaymentMaster.txn_date,
                    [PaymentMaster.txn_type == "RECEIPT", PaymentMaster.payment_mode_id.in_(mode_ids)])
        - _sum_before(PaymentMaster, PaymentMaster.txn_date,
                      [PaymentMaster.txn_type == "PAYMENT", PaymentMaster.payment_mode_id.in_(mode_ids)])
        - _sum_before(ExpenseMaster, ExpenseMaster.expense_date,
                      [ExpenseMaster.payment_mode_id.in_(mode_ids)])
    )

    # Collect rows in the window
    raw = []  # (date, order, particulars, voucher_type, voucher_no, money_in, money_out)

    pays = (
        db.query(PaymentMaster)
        .options(joinedload(PaymentMaster.party), joinedload(PaymentMaster.payment_mode))
        .filter(
            PaymentMaster.payment_mode_id.in_(mode_ids),
            PaymentMaster.txn_date >= start,
            PaymentMaster.txn_date <= end,
        )
        .all()
    )
    for p in pays:
        party = p.party.party_name if p.party else "—"
        mode = p.payment_mode.mode_name if p.payment_mode else ""
        if p.txn_type == "RECEIPT":
            raw.append((p.txn_date, 0, f"Receipt — {party}", "Receipt", p.reference_no or mode,
                        p.amount or Decimal("0"), Decimal("0")))
        else:
            raw.append((p.txn_date, 1, f"Payment — {party}", "Payment", p.reference_no or mode,
                        Decimal("0"), p.amount or Decimal("0")))

    exps = (
        db.query(ExpenseMaster)
        .options(joinedload(ExpenseMaster.payment_mode))
        .filter(
            ExpenseMaster.payment_mode_id.in_(mode_ids),
            ExpenseMaster.expense_date >= start,
            ExpenseMaster.expense_date <= end,
        )
        .all()
    )
    for e in exps:
        label = e.category or "Expense"
        if e.description:
            label = f"{label} — {e.description}"
        raw.append((e.expense_date, 2, label, "Expense", e.reference_no, Decimal("0"), e.amount or Decimal("0")))

    raw.sort(key=lambda r: (r[0], r[1]))

    running = opening
    total_in = total_out = Decimal("0")
    rows = []
    for (d, _o, particulars, vtype, vno, mi, mo) in raw:
        running += mi - mo
        total_in += mi
        total_out += mo
        rows.append({
            "date":         d.isoformat(),
            "particulars":  particulars,
            "voucher_type": vtype,
            "voucher_no":   vno,
            "money_in":     _f(mi),
            "money_out":    _f(mo),
            "balance":      _f(running),
        })

    return {
        "opening_balance": _f(opening),
        "rows": rows,
        "total_in": _f(total_in),
        "total_out": _f(total_out),
        "closing_balance": _f(running),
    }


def _resolve_range(date_from: Optional[date], date_to: Optional[date]):
    today = date.today()
    end = date_to or today
    start = date_from or (end - timedelta(days=29))
    if start > end:
        start, end = end, start
    return start, end


@router.get("/cash-book")
def cash_book(
    date_from: Optional[date] = Query(None),
    date_to:   Optional[date] = Query(None),
    db:        Session        = Depends(get_db),
):
    start, end = _resolve_range(date_from, date_to)
    cash_ids, _ = _mode_class_maps(db)
    book = _book(db, cash_ids, start, end)
    book["range"] = {"from": start.isoformat(), "to": end.isoformat()}
    book["book"] = "cash"
    return book


@router.get("/bank-book")
def bank_book(
    date_from: Optional[date] = Query(None),
    date_to:   Optional[date] = Query(None),
    db:        Session        = Depends(get_db),
):
    start, end = _resolve_range(date_from, date_to)
    _, bank_ids = _mode_class_maps(db)
    book = _book(db, bank_ids, start, end)
    book["range"] = {"from": start.isoformat(), "to": end.isoformat()}
    book["book"] = "bank"
    return book


# ── Day book ────────────────────────────────────────────────────────────────────

@router.get("/day-book")
def day_book(
    day: Optional[date] = Query(None),
    db:  Session        = Depends(get_db),
):
    target = day or date.today()
    vouchers = []

    for s in (
        db.query(SalesMaster).options(joinedload(SalesMaster.customer))
        .filter(SalesMaster.invoice_date == target).all()
    ):
        vouchers.append({
            "type": "Sales Invoice",
            "voucher_no": s.invoice_no or f"#{s.id}",
            "party": s.customer.party_name if s.customer else "Walk-in",
            "amount": _f(s.net_amount),
            "direction": "in",
        })

    for p in (
        db.query(PurchaseMaster).options(joinedload(PurchaseMaster.supplier))
        .filter(PurchaseMaster.invoice_date == target).all()
    ):
        vouchers.append({
            "type": "Purchase Invoice",
            "voucher_no": p.invoice_no or f"#{p.id}",
            "party": p.supplier.party_name if p.supplier else "—",
            "amount": _f(p.net_amount),
            "direction": "out",
        })

    for pay in (
        db.query(PaymentMaster).options(joinedload(PaymentMaster.party), joinedload(PaymentMaster.payment_mode))
        .filter(PaymentMaster.txn_date == target).all()
    ):
        mode = pay.payment_mode.mode_name if pay.payment_mode else ""
        is_receipt = pay.txn_type == "RECEIPT"
        vouchers.append({
            "type": "Receipt" if is_receipt else "Payment",
            "voucher_no": pay.reference_no or mode or f"#{pay.id}",
            "party": pay.party.party_name if pay.party else "—",
            "amount": _f(pay.amount),
            "direction": "in" if is_receipt else "out",
            "mode": mode,
        })

    for e in (
        db.query(ExpenseMaster).options(joinedload(ExpenseMaster.payment_mode))
        .filter(ExpenseMaster.expense_date == target).all()
    ):
        vouchers.append({
            "type": "Expense",
            "voucher_no": e.reference_no or f"#{e.id}",
            "party": e.category or "Expense",
            "amount": _f(e.amount),
            "direction": "out",
            "mode": e.payment_mode.mode_name if e.payment_mode else "",
        })

    sales      = sum(v["amount"] for v in vouchers if v["type"] == "Sales Invoice")
    purchases  = sum(v["amount"] for v in vouchers if v["type"] == "Purchase Invoice")
    receipts   = sum(v["amount"] for v in vouchers if v["type"] == "Receipt")
    payments   = sum(v["amount"] for v in vouchers if v["type"] == "Payment")
    expenses   = sum(v["amount"] for v in vouchers if v["type"] == "Expense")

    return {
        "day": target.isoformat(),
        "summary": {
            "sales": round(sales, 2),
            "purchases": round(purchases, 2),
            "receipts": round(receipts, 2),
            "payments": round(payments, 2),
            "expenses": round(expenses, 2),
            "cash_in": round(receipts, 2),
            "cash_out": round(payments + expenses, 2),
            "net_cash": round(receipts - payments - expenses, 2),
        },
        "vouchers": vouchers,
    }


# ── Supplier-wise payments ───────────────────────────────────────────────────────

@router.get("/supplier-wise")
def supplier_wise(db: Session = Depends(get_db)):
    """Per-supplier rollup: billed, paid, outstanding, last payment date."""
    purchase_paid = _paid_map(db, "purchase", "PAYMENT")

    billed: dict = {}
    for p in db.query(PurchaseMaster).all():
        agg = billed.setdefault(p.supplier_id, {"net": Decimal("0"), "paid": Decimal("0"), "bills": 0})
        agg["net"] += p.net_amount or Decimal("0")
        agg["paid"] += purchase_paid.get(p.id, Decimal("0"))
        agg["bills"] += 1

    # last payment date per supplier
    last_rows = (
        db.query(PaymentMaster.party_id, func.max(PaymentMaster.txn_date))
        .filter(PaymentMaster.txn_type == "PAYMENT")
        .group_by(PaymentMaster.party_id)
        .all()
    )
    last_paid = {r[0]: r[1] for r in last_rows}

    names = {
        pid: name
        for pid, name in db.query(PartyMaster.id, PartyMaster.party_name).all()
    }

    out = []
    for supplier_id, agg in billed.items():
        if supplier_id is None:
            continue
        outstanding = max(agg["net"] - agg["paid"], Decimal("0"))
        out.append({
            "supplier_id": supplier_id,
            "supplier_name": names.get(supplier_id, f"#{supplier_id}"),
            "bills": agg["bills"],
            "billed": _f(agg["net"]),
            "paid": _f(agg["paid"]),
            "outstanding": _f(outstanding),
            "last_payment": last_paid[supplier_id].isoformat() if last_paid.get(supplier_id) else None,
        })
    out.sort(key=lambda r: r["outstanding"], reverse=True)
    return {"suppliers": out}
