"""
payments router  (/api/v1/payments, /api/v1/purchases/outstanding, etc.)
────────────────────────────────────────────────────────────────────────
CRUD
  POST   /payments/                  Record a payment (RECEIPT or PAYMENT)
  GET    /payments/                  List with filters
  GET    /payments/{id}              Single payment
  PATCH  /payments/{id}              Correct a payment
  DELETE /payments/{id}              Reverse / delete + recalculate invoice status

Outstanding
  GET    /purchases/outstanding       Unpaid/partial purchase invoices
  GET    /sales/outstanding           Unpaid/partial sales invoices (receivables)

Payments per document
  GET    /purchases/{id}/payments     All payments for one purchase invoice
  GET    /sales/{id}/receipts         All receipts for one sales invoice

Distributor endpoints
  GET    /distributors/               List all distributors
  GET    /distributors/{id}/invoices/{invoice_id}/payments
                                      Payment details for a specific invoice of a specific distributor

Party ledger & summary
  GET    /parties/{id}/ledger         Full running ledger (invoices + payments)
  GET    /parties/{id}/outstanding-summary   Balance totals
"""

import os
import re
import shutil
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.auth.deps import get_tenant_db as get_db
from app.models.party_master import PartyMaster
from app.models.purchase_master import PurchaseMaster
from app.models.purchase_payment import PartyCreditConfig, PaymentMaster
from app.models.sales_master import SalesMaster
from app.schemas.party_master import PartyMasterResponse
from app.schemas.purchase_payment import (
    OutstandingInvoice,
    OutstandingSale,
    PartyLedgerEntry,
    PartyOutstandingSummary,
    PaymentMasterCreate,
    PaymentMasterResponse,
    PaymentMasterUpdate,
    SupplierLedgerResponse,
    SupplierLedgerRow,
)

router = APIRouter(tags=["Payments & Ledger"])

# ── Receipt upload config ────────────────────────────────────────────────────────
# Images are stored on disk under data/payment_receipts/ and served read-only
# under the /media/payment-receipts URL prefix (mounted in app/main.py).
RECEIPTS_DIR        = os.path.join(os.path.dirname(__file__), "..", "..", "data", "payment_receipts")
RECEIPTS_URL_PREFIX = "/media/payment-receipts"
ALLOWED_RECEIPT_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".pdf"}


# ── internal helpers ───────────────────────────────────────────────────────────

def _pay_to_response(pay: PaymentMaster, doc_no: Optional[str] = None) -> PaymentMasterResponse:
    return PaymentMasterResponse(
        id                = pay.id,
        party_id          = pay.party_id,
        party_name        = pay.party.party_name           if pay.party        else None,
        txn_type          = pay.txn_type,
        reference_type    = pay.reference_type,
        reference_id      = pay.reference_id,
        reference_no_doc  = doc_no,
        txn_date          = pay.txn_date,
        amount            = pay.amount,
        payment_mode_id   = pay.payment_mode_id,
        payment_mode_name = pay.payment_mode.mode_name     if pay.payment_mode else None,
        reference_no      = pay.reference_no,
        notes             = pay.notes,
        receipt_path      = pay.receipt_path,
        created_at        = pay.created_at,
        updated_at        = pay.updated_at,
    )


def _get_credit_cfg(db: Session, party_id: int) -> tuple[int, int]:
    """Return (credit_days, grace_days) — party override → global default → (30, 0)."""
    cfg = db.query(PartyCreditConfig).filter(PartyCreditConfig.party_id == party_id).first()
    if cfg:
        return cfg.credit_days, cfg.overdue_grace_days
    default = db.query(PartyCreditConfig).filter(PartyCreditConfig.party_id.is_(None)).first()
    if default:
        return default.credit_days, default.overdue_grace_days
    return 30, 0


def _total_paid_for(db: Session, reference_type: str, reference_id: int) -> Decimal:
    return db.query(
        func.coalesce(func.sum(PaymentMaster.amount), Decimal("0"))
    ).filter(
        PaymentMaster.reference_type == reference_type,
        PaymentMaster.reference_id   == reference_id,
    ).scalar() or Decimal("0")


def _compute_purchase_payment_status(total_paid: Decimal, net_amount: Decimal) -> str:
    if total_paid <= 0:
        return "Unpaid"
    if total_paid >= net_amount:
        return "Paid"
    return "Partial"


def _sync_sale_status(db: Session, sale: SalesMaster) -> None:
    received = _total_paid_for(db, "sale", sale.id)
    net      = sale.net_amount or Decimal("0")
    if received <= 0:
        sale.payment_status = "Unpaid"
    elif received >= net:
        sale.payment_status = "Paid"
    else:
        sale.payment_status = "Partial"


def _load_pays_for(db: Session, reference_type: str, reference_id: int) -> List[PaymentMaster]:
    return (
        db.query(PaymentMaster)
        .options(joinedload(PaymentMaster.party), joinedload(PaymentMaster.payment_mode))
        .filter(
            PaymentMaster.reference_type == reference_type,
            PaymentMaster.reference_id   == reference_id,
        )
        .order_by(PaymentMaster.txn_date)
        .all()
    )


def _build_outstanding_purchase(db: Session, p: PurchaseMaster, today: date) -> OutstandingInvoice:
    credit_days, grace = _get_credit_cfg(db, p.supplier_id)
    if p.due_date:
        eff_due = p.due_date
    elif p.invoice_date:
        eff_due = p.invoice_date + timedelta(days=credit_days)
    else:
        eff_due = None

    total_paid  = _total_paid_for(db, "purchase", p.id)
    net         = p.net_amount or Decimal("0")
    outstanding = max(net - total_paid, Decimal("0"))

    is_overdue, days_overdue = False, 0
    if outstanding > 0 and eff_due:
        cutoff = eff_due + timedelta(days=grace)
        if today > cutoff:
            is_overdue   = True
            days_overdue = (today - cutoff).days

    pays = _load_pays_for(db, "purchase", p.id)

    return OutstandingInvoice(
        id                 = p.id,
        invoice_no         = p.invoice_no,
        invoice_date       = p.invoice_date,
        entry_date         = p.entry_date,
        due_date           = p.due_date,
        effective_due_date = eff_due,
        supplier_id        = p.supplier_id,
        supplier_name      = p.supplier.party_name if p.supplier else None,
        net_amount         = net,
        total_paid         = total_paid,
        outstanding_amount = outstanding,
        payment_status     = _compute_purchase_payment_status(total_paid, net),
        is_overdue         = is_overdue,
        days_overdue       = days_overdue,
        credit_days        = credit_days,
        payments           = [_pay_to_response(x, p.invoice_no) for x in pays],
    )


def _build_outstanding_sale(db: Session, s: SalesMaster, today: date) -> OutstandingSale:
    credit_days, grace = _get_credit_cfg(db, s.customer_id)
    eff_due = s.invoice_date + timedelta(days=credit_days) if s.invoice_date else None

    total_received = _total_paid_for(db, "sale", s.id)
    net            = s.net_amount or Decimal("0")
    outstanding    = max(net - total_received, Decimal("0"))

    is_overdue, days_overdue = False, 0
    if outstanding > 0 and eff_due:
        cutoff = eff_due + timedelta(days=grace)
        if today > cutoff:
            is_overdue   = True
            days_overdue = (today - cutoff).days

    receipts = _load_pays_for(db, "sale", s.id)

    return OutstandingSale(
        id                 = s.id,
        invoice_no         = s.invoice_no,
        invoice_date       = s.invoice_date,
        customer_id        = s.customer_id,
        customer_name      = s.customer.party_name if s.customer else None,
        net_amount         = net,
        total_received     = total_received,
        outstanding_amount = outstanding,
        payment_status     = s.payment_status,
        is_overdue         = is_overdue,
        days_overdue       = days_overdue,
        credit_days        = credit_days,
        receipts           = [_pay_to_response(x, s.invoice_no) for x in receipts],
    )


# ── Payment CRUD ───────────────────────────────────────────────────────────────

@router.post("/payments/", response_model=PaymentMasterResponse, status_code=status.HTTP_201_CREATED)
def create_payment(payload: PaymentMasterCreate, db: Session = Depends(get_db)):
    """
    Record a payment.

    - `txn_type=RECEIPT`  → money received from a customer against a sales invoice
    - `txn_type=PAYMENT`  → money paid to a distributor against a purchase invoice

    Automatically recalculates the linked sale invoice's payment_status.
    """
    if not db.query(PartyMaster).filter(PartyMaster.id == payload.party_id).first():
        raise HTTPException(404, "Party not found.")

    # overpayment guard on purchase invoice
    if payload.reference_type == "purchase" and payload.reference_id:
        doc = db.query(PurchaseMaster).filter(PurchaseMaster.id == payload.reference_id).first()
        if not doc:
            raise HTTPException(404, "Purchase invoice not found.")
        already_paid = _total_paid_for(db, "purchase", doc.id)
        net = doc.net_amount or Decimal("0")
        if already_paid + payload.amount > net:
            raise HTTPException(400,
                f"Payment {payload.amount} exceeds outstanding {max(net - already_paid, 0)} "
                f"on invoice {doc.invoice_no}.")

    # overpayment guard on sales invoice
    if payload.reference_type == "sale" and payload.reference_id:
        doc = db.query(SalesMaster).filter(SalesMaster.id == payload.reference_id).first()
        if not doc:
            raise HTTPException(404, "Sales invoice not found.")
        already_recv = _total_paid_for(db, "sale", doc.id)
        net = doc.net_amount or Decimal("0")
        if already_recv + payload.amount > net:
            raise HTTPException(400,
                f"Receipt {payload.amount} exceeds outstanding {max(net - already_recv, 0)} "
                f"on invoice {doc.invoice_no}.")

    pay = PaymentMaster(**payload.model_dump())
    db.add(pay)
    db.flush()

    # sync sale invoice status (purchase status is now computed dynamically)
    if payload.reference_type == "sale" and payload.reference_id:
        sale = db.query(SalesMaster).filter(SalesMaster.id == payload.reference_id).first()
        if sale:
            _sync_sale_status(db, sale)

    db.commit()
    db.refresh(pay)
    pay = db.query(PaymentMaster).options(
        joinedload(PaymentMaster.party),
        joinedload(PaymentMaster.payment_mode),
    ).filter(PaymentMaster.id == pay.id).first()
    return _pay_to_response(pay)


@router.get("/payments/", response_model=List[PaymentMasterResponse])
def list_payments(
    skip:            int            = Query(0,   ge=0),
    limit:           int            = Query(100, ge=1, le=1000),
    party_id:        Optional[int]  = Query(None),
    txn_type:        Optional[str]  = Query(None, description="RECEIPT or PAYMENT"),
    reference_type:  Optional[str]  = Query(None, description="sale or purchase"),
    reference_id:    Optional[int]  = Query(None),
    payment_mode_id: Optional[int]  = Query(None),
    date_from:       Optional[date] = Query(None, description="txn_date >="),
    date_to:         Optional[date] = Query(None, description="txn_date <="),
    db:              Session        = Depends(get_db),
):
    q = db.query(PaymentMaster).options(
        joinedload(PaymentMaster.party),
        joinedload(PaymentMaster.payment_mode),
    )
    if party_id:        q = q.filter(PaymentMaster.party_id        == party_id)
    if txn_type:        q = q.filter(PaymentMaster.txn_type        == txn_type.upper())
    if reference_type:  q = q.filter(PaymentMaster.reference_type  == reference_type)
    if reference_id:    q = q.filter(PaymentMaster.reference_id    == reference_id)
    if payment_mode_id: q = q.filter(PaymentMaster.payment_mode_id == payment_mode_id)
    if date_from:       q = q.filter(PaymentMaster.txn_date        >= date_from)
    if date_to:         q = q.filter(PaymentMaster.txn_date        <= date_to)
    pays = q.order_by(PaymentMaster.txn_date.desc()).offset(skip).limit(limit).all()
    return [_pay_to_response(p) for p in pays]


@router.get("/payments/{payment_id}", response_model=PaymentMasterResponse)
def get_payment(payment_id: int, db: Session = Depends(get_db)):
    pay = db.query(PaymentMaster).options(
        joinedload(PaymentMaster.party),
        joinedload(PaymentMaster.payment_mode),
    ).filter(PaymentMaster.id == payment_id).first()
    if not pay:
        raise HTTPException(404, "Payment not found.")
    return _pay_to_response(pay)


@router.patch("/payments/{payment_id}", response_model=PaymentMasterResponse)
def update_payment(payment_id: int, payload: PaymentMasterUpdate, db: Session = Depends(get_db)):
    pay = db.query(PaymentMaster).filter(PaymentMaster.id == payment_id).first()
    if not pay:
        raise HTTPException(404, "Payment not found.")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(pay, field, value)
    db.flush()
    # re-sync linked sale invoice (purchase status is computed dynamically)
    if pay.reference_type == "sale" and pay.reference_id:
        s = db.query(SalesMaster).filter(SalesMaster.id == pay.reference_id).first()
        if s:
            _sync_sale_status(db, s)
    db.commit()
    pay = db.query(PaymentMaster).options(
        joinedload(PaymentMaster.party),
        joinedload(PaymentMaster.payment_mode),
    ).filter(PaymentMaster.id == payment_id).first()
    return _pay_to_response(pay)


@router.delete("/payments/{payment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_payment(payment_id: int, db: Session = Depends(get_db)):
    pay = db.query(PaymentMaster).filter(PaymentMaster.id == payment_id).first()
    if not pay:
        raise HTTPException(404, "Payment not found.")
    ref_type, ref_id = pay.reference_type, pay.reference_id
    db.delete(pay)
    db.flush()
    # re-sync linked sale invoice (purchase status is computed dynamically)
    if ref_type == "sale" and ref_id:
        s = db.query(SalesMaster).filter(SalesMaster.id == ref_id).first()
        if s:
            _sync_sale_status(db, s)
    db.commit()


# ── Payment receipt upload (UPI / Card proof) ───────────────────────────────────

@router.post("/payments/{payment_id}/receipt", response_model=PaymentMasterResponse)
def upload_payment_receipt(
    payment_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    Attach a payment receipt image (e.g. UPI / Card slip) to a payment.

    The file is saved under data/payment_receipts/ with a descriptive name
    (`payment_<id>_<timestamp>_<original>.<ext>`) and the public URL is stored
    on the payment's `receipt_path`, served read-only under /media/payment-receipts.
    """
    pay = db.query(PaymentMaster).filter(PaymentMaster.id == payment_id).first()
    if not pay:
        raise HTTPException(404, "Payment not found.")

    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_RECEIPT_EXT:
        raise HTTPException(
            400,
            f"Unsupported file type '{ext or '?'}'. Allowed: {', '.join(sorted(ALLOWED_RECEIPT_EXT))}",
        )

    os.makedirs(RECEIPTS_DIR, exist_ok=True)
    raw_stem  = os.path.splitext(os.path.basename(file.filename or "receipt"))[0]
    safe_stem = re.sub(r"[^A-Za-z0-9_-]+", "_", raw_stem)[:40] or "receipt"
    stamp     = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    filename  = f"payment_{payment_id}_{stamp}_{safe_stem}{ext}"
    dest      = os.path.join(RECEIPTS_DIR, filename)

    with open(dest, "wb") as out:
        shutil.copyfileobj(file.file, out)

    pay.receipt_path = f"{RECEIPTS_URL_PREFIX}/{filename}"
    db.commit()

    pay = db.query(PaymentMaster).options(
        joinedload(PaymentMaster.party),
        joinedload(PaymentMaster.payment_mode),
    ).filter(PaymentMaster.id == payment_id).first()
    return _pay_to_response(pay)


# ── Outstanding purchase invoices ──────────────────────────────────────────────

@router.get("/purchases/outstanding", response_model=List[OutstandingInvoice])
def purchase_outstanding(
    party_id:        Optional[int]     = Query(None),
    party_type:      Optional[str]     = Query(None, description="e.g. Distributor"),
    overdue_only:    bool              = Query(False),
    date_from:       Optional[date]    = Query(None, description="invoice_date >="),
    date_to:         Optional[date]    = Query(None, description="invoice_date <="),
    payment_status:  Optional[str]     = Query(None, description="Unpaid / Partial / Paid"),
    min_outstanding: Optional[Decimal] = Query(None),
    skip:  int = Query(0,   ge=0),
    limit: int = Query(200, ge=1, le=1000),
    db:    Session = Depends(get_db),
):
    """
    Purchase payables — what we owe to distributors.
    Each invoice includes `total_paid`, `outstanding_amount`, `is_overdue`,
    `days_overdue`, computed `payment_status` and the list of payments already made.
    """
    q = db.query(PurchaseMaster).options(
        joinedload(PurchaseMaster.supplier),
    )
    if party_id:
        q = q.filter(PurchaseMaster.supplier_id == party_id)
    if party_type:
        q = (q.join(PartyMaster, PurchaseMaster.supplier_id == PartyMaster.id)
               .filter(PartyMaster.party_type == party_type))
    if date_from:
        q = q.filter(PurchaseMaster.invoice_date >= date_from)
    if date_to:
        q = q.filter(PurchaseMaster.invoice_date <= date_to)

    today = date.today()
    results = []
    for p in q.order_by(PurchaseMaster.invoice_date.desc()).offset(skip).limit(limit):
        oi = _build_outstanding_purchase(db, p, today)
        if payment_status and oi.payment_status != payment_status:
            continue
        if min_outstanding is not None and oi.outstanding_amount < min_outstanding:
            continue
        if overdue_only and not oi.is_overdue:
            continue
        results.append(oi)
    return results


# ── Outstanding sales invoices (receivables) ───────────────────────────────────

@router.get("/sales/outstanding", response_model=List[OutstandingSale])
def sales_outstanding(
    party_id:        Optional[int]     = Query(None),
    party_type:      Optional[str]     = Query(None, description="e.g. Customer"),
    overdue_only:    bool              = Query(False),
    date_from:       Optional[date]    = Query(None, description="invoice_date >="),
    date_to:         Optional[date]    = Query(None, description="invoice_date <="),
    payment_status:  Optional[str]     = Query(None, description="Unpaid / Partial / Paid"),
    min_outstanding: Optional[Decimal] = Query(None),
    skip:  int = Query(0,   ge=0),
    limit: int = Query(200, ge=1, le=1000),
    db:    Session = Depends(get_db),
):
    """
    Sales receivables — what customers owe us.
    Each invoice includes `total_received`, `outstanding_amount`, `is_overdue`.
    """
    q = db.query(SalesMaster).options(
        joinedload(SalesMaster.customer),
        joinedload(SalesMaster.payment_mode),
    )
    if party_id:
        q = q.filter(SalesMaster.customer_id == party_id)
    if party_type:
        q = (q.join(PartyMaster, SalesMaster.customer_id == PartyMaster.id)
               .filter(PartyMaster.party_type == party_type))
    if date_from:
        q = q.filter(SalesMaster.invoice_date >= date_from)
    if date_to:
        q = q.filter(SalesMaster.invoice_date <= date_to)
    if payment_status:
        q = q.filter(SalesMaster.payment_status == payment_status)

    today = date.today()
    results = []
    for s in q.order_by(SalesMaster.invoice_date.desc()).offset(skip).limit(limit):
        os_ = _build_outstanding_sale(db, s, today)
        if min_outstanding is not None and os_.outstanding_amount < min_outstanding:
            continue
        if overdue_only and not os_.is_overdue:
            continue
        results.append(os_)
    return results


# ── Payments per document ──────────────────────────────────────────────────────

@router.get("/purchases/{purchase_id}/payments", response_model=List[PaymentMasterResponse])
def purchase_payments(purchase_id: int, db: Session = Depends(get_db)):
    """All payments made against a specific purchase invoice."""
    if not db.query(PurchaseMaster).filter(PurchaseMaster.id == purchase_id).first():
        raise HTTPException(404, "Purchase not found.")
    pays = _load_pays_for(db, "purchase", purchase_id)
    return [_pay_to_response(p) for p in pays]


@router.get("/sales/{sale_id}/receipts", response_model=List[PaymentMasterResponse])
def sale_receipts(sale_id: int, db: Session = Depends(get_db)):
    """All receipts collected against a specific sales invoice."""
    if not db.query(SalesMaster).filter(SalesMaster.id == sale_id).first():
        raise HTTPException(404, "Sale not found.")
    pays = _load_pays_for(db, "sale", sale_id)
    return [_pay_to_response(p) for p in pays]


# ── Distributor endpoints ──────────────────────────────────────────────────────

@router.get("/distributors/", response_model=List[PartyMasterResponse])
def list_distributors(
    skip:   int           = Query(0,  ge=0),
    limit:  int           = Query(50, ge=1, le=500),
    search: Optional[str] = Query(None, description="Search by name, code or mobile"),
    db:     Session       = Depends(get_db),
):
    """List all distributors (party_type = Distributor)."""
    q = db.query(PartyMaster).filter(PartyMaster.party_type == "Distributor")
    if search:
        pattern = f"%{search}%"
        q = q.filter(
            PartyMaster.party_name.ilike(pattern)
            | PartyMaster.party_code.ilike(pattern)
            | PartyMaster.mobile.ilike(pattern)
        )
    return q.order_by(PartyMaster.party_name).offset(skip).limit(limit).all()


@router.get(
    "/distributors/{distributor_id}/invoices/{invoice_id}/payments",
    response_model=List[PaymentMasterResponse],
)
def distributor_invoice_payments(
    distributor_id: int,
    invoice_id:     int,
    db:             Session = Depends(get_db),
):
    """
    Payment details for a specific purchase invoice of a specific distributor.

    Returns all payment transactions recorded against this invoice,
    each with payment_mode, amount, date, and reference details.
    """
    distributor = db.query(PartyMaster).filter(
        PartyMaster.id == distributor_id,
        PartyMaster.party_type == "Distributor",
    ).first()
    if not distributor:
        raise HTTPException(404, "Distributor not found.")

    invoice = db.query(PurchaseMaster).filter(
        PurchaseMaster.id          == invoice_id,
        PurchaseMaster.supplier_id == distributor_id,
    ).first()
    if not invoice:
        raise HTTPException(404, "Invoice not found for this distributor.")

    pays = _load_pays_for(db, "purchase", invoice_id)
    return [_pay_to_response(p, invoice.invoice_no) for p in pays]


# ── Supplier (creditor) ledger — industry-standard statement ────────────────────

@router.get("/distributors/{distributor_id}/ledger", response_model=SupplierLedgerResponse)
def distributor_ledger(
    distributor_id: int,
    date_from: Optional[date] = Query(None, description="entries on/after this date"),
    date_to:   Optional[date] = Query(None, description="entries on/before this date"),
    db:        Session        = Depends(get_db),
):
    """
    Supplier account statement (buyer's books, creditor account):

      • Opening balance (from party_master.opening_balance) — Cr if we owe.
      • Purchase invoices  → CREDIT (payable increases).
      • Payments made      → DEBIT  (payable decreases).
      • Running balance shown as Dr / Cr, with closing balance + totals.
    """
    party = db.query(PartyMaster).filter(PartyMaster.id == distributor_id).first()
    if not party:
        raise HTTPException(404, "Supplier not found.")

    opening = party.opening_balance or Decimal("0")   # +ve = Cr (we owe)

    # (date, order, voucher_type, particulars, voucher_no, debit, credit)
    raw: List[tuple] = []

    pq = db.query(PurchaseMaster).filter(PurchaseMaster.supplier_id == distributor_id)
    if date_from: pq = pq.filter(PurchaseMaster.invoice_date >= date_from)
    if date_to:   pq = pq.filter(PurchaseMaster.invoice_date <= date_to)
    for p in pq.all():
        d = p.invoice_date or p.entry_date or (p.created_at.date() if p.created_at else date.today())
        raw.append((d, 0, "Purchase", "Purchase Invoice", p.invoice_no, Decimal("0"), p.net_amount or Decimal("0")))

    paysq = (
        db.query(PaymentMaster)
        .options(joinedload(PaymentMaster.payment_mode))
        .filter(PaymentMaster.party_id == distributor_id, PaymentMaster.txn_type == "PAYMENT")
    )
    if date_from: paysq = paysq.filter(PaymentMaster.txn_date >= date_from)
    if date_to:   paysq = paysq.filter(PaymentMaster.txn_date <= date_to)
    for pay in paysq.all():
        mode = pay.payment_mode.mode_name if pay.payment_mode else ""
        particulars = f"Payment - {mode}" if mode else "Payment"
        raw.append((pay.txn_date, 1, "Payment", particulars, pay.reference_no, pay.amount or Decimal("0"), Decimal("0")))

    raw.sort(key=lambda r: (r[0], r[1]))

    running      = opening
    total_debit  = Decimal("0")
    total_credit = Decimal("0")
    rows: List[SupplierLedgerRow] = []
    for (d, _ord, vtype, particulars, vno, debit, credit) in raw:
        running       += credit - debit
        total_debit   += debit
        total_credit  += credit
        rows.append(SupplierLedgerRow(
            entry_date   = d,
            particulars  = particulars,
            voucher_type = vtype,
            voucher_no   = vno,
            debit        = debit,
            credit       = credit,
            balance      = abs(running),
            balance_type = "Cr" if running >= 0 else "Dr",
        ))

    return SupplierLedgerResponse(
        party_id             = party.id,
        party_name           = party.party_name,
        party_code           = party.party_code,
        gstin                = party.gstin,
        from_date            = date_from,
        to_date              = date_to,
        opening_balance      = abs(opening),
        opening_balance_type = "Cr" if opening >= 0 else "Dr",
        rows                 = rows,
        total_debit          = total_debit,
        total_credit         = total_credit,
        closing_balance      = abs(running),
        closing_balance_type = "Cr" if running >= 0 else "Dr",
    )


# ── Party running ledger ───────────────────────────────────────────────────────

@router.get("/parties/{party_id}/ledger", response_model=List[PartyLedgerEntry])
def party_ledger(
    party_id:   int,
    date_from:  Optional[date] = Query(None),
    date_to:    Optional[date] = Query(None),
    db:         Session        = Depends(get_db),
):
    """
    Full chronological ledger for a party.

    Distributor ledger  → purchase invoices as debits, payments as credits.
    Customer ledger     → sales invoices as debits, receipts as credits.

    Returns rows sorted by date with a running `balance` column.
    """
    party = db.query(PartyMaster).filter(PartyMaster.id == party_id).first()
    if not party:
        raise HTTPException(404, "Party not found.")

    entries: List[PartyLedgerEntry] = []

    # ── purchase invoices (debit — we owe them) ──
    pq = db.query(PurchaseMaster).filter(PurchaseMaster.supplier_id == party_id)
    if date_from: pq = pq.filter(PurchaseMaster.invoice_date >= date_from)
    if date_to:   pq = pq.filter(PurchaseMaster.invoice_date <= date_to)
    for p in pq.all():
        entries.append(PartyLedgerEntry(
            entry_date     = p.invoice_date or p.entry_date or p.created_at.date(),
            entry_type     = "INVOICE",
            reference_type = "purchase",
            reference_id   = p.id,
            doc_no         = p.invoice_no,
            description    = f"Purchase Invoice {p.invoice_no or p.id}",
            debit          = p.net_amount or Decimal("0"),
            credit         = Decimal("0"),
        ))

    # ── sales invoices (debit — they owe us) ──
    sq = db.query(SalesMaster).filter(SalesMaster.customer_id == party_id)
    if date_from: sq = sq.filter(SalesMaster.invoice_date >= date_from)
    if date_to:   sq = sq.filter(SalesMaster.invoice_date <= date_to)
    for s in sq.all():
        entries.append(PartyLedgerEntry(
            entry_date     = s.invoice_date or s.created_at.date(),
            entry_type     = "INVOICE",
            reference_type = "sale",
            reference_id   = s.id,
            doc_no         = s.invoice_no,
            description    = f"Sales Invoice {s.invoice_no or s.id}",
            debit          = s.net_amount or Decimal("0"),
            credit         = Decimal("0"),
        ))

    # ── payments (credit — money moved) ──
    paysq = db.query(PaymentMaster).options(
        joinedload(PaymentMaster.payment_mode)
    ).filter(PaymentMaster.party_id == party_id)
    if date_from: paysq = paysq.filter(PaymentMaster.txn_date >= date_from)
    if date_to:   paysq = paysq.filter(PaymentMaster.txn_date <= date_to)
    for pay in paysq.all():
        mode = pay.payment_mode.mode_name if pay.payment_mode else ""
        label = "RECEIPT" if pay.txn_type == "RECEIPT" else "PAYMENT"
        entries.append(PartyLedgerEntry(
            entry_date     = pay.txn_date,
            entry_type     = label,
            reference_type = pay.reference_type,
            reference_id   = pay.reference_id,
            doc_no         = pay.reference_no,
            description    = (
                f"{label} via {mode}"
                + (f" (Ref: {pay.reference_no})" if pay.reference_no else "")
            ),
            debit          = Decimal("0"),
            credit         = pay.amount,
        ))

    # sort by date, then invoices before payments on same day
    entries.sort(key=lambda e: (e.entry_date, 0 if e.entry_type == "INVOICE" else 1))

    # compute running balance
    balance = Decimal("0")
    for e in entries:
        balance += e.debit - e.credit
        e.balance = balance

    return entries


# ── Party outstanding summary ──────────────────────────────────────────────────

@router.get("/parties/{party_id}/outstanding-summary", response_model=PartyOutstandingSummary)
def party_outstanding_summary(party_id: int, db: Session = Depends(get_db)):
    """
    One-line balance snapshot for a party:
    total_invoiced, total_settled, total_outstanding, overdue_amount.
    Works for both distributors (purchases) and customers (sales).
    """
    party = db.query(PartyMaster).filter(PartyMaster.id == party_id).first()
    if not party:
        raise HTTPException(404, "Party not found.")

    credit_days, _ = _get_credit_cfg(db, party_id)
    today = date.today()

    total_invoiced    = Decimal("0")
    total_settled     = Decimal("0")
    total_outstanding = Decimal("0")
    overdue_amount    = Decimal("0")
    invoice_count     = 0
    overdue_count     = 0

    # purchases (payable to this party)
    for p in db.query(PurchaseMaster).filter(PurchaseMaster.supplier_id == party_id).all():
        oi = _build_outstanding_purchase(db, p, today)
        total_invoiced    += oi.net_amount or Decimal("0")
        total_settled     += oi.total_paid
        total_outstanding += oi.outstanding_amount
        invoice_count     += 1
        if oi.is_overdue:
            overdue_amount += oi.outstanding_amount
            overdue_count  += 1

    # sales (receivable from this party)
    for s in db.query(SalesMaster).filter(SalesMaster.customer_id == party_id).all():
        os_ = _build_outstanding_sale(db, s, today)
        total_invoiced    += os_.net_amount or Decimal("0")
        total_settled     += os_.total_received
        total_outstanding += os_.outstanding_amount
        invoice_count     += 1
        if os_.is_overdue:
            overdue_amount += os_.outstanding_amount
            overdue_count  += 1

    return PartyOutstandingSummary(
        party_id          = party_id,
        party_name        = party.party_name,
        party_type        = party.party_type,
        total_invoiced    = total_invoiced,
        total_settled     = total_settled,
        total_outstanding = total_outstanding,
        overdue_amount    = overdue_amount,
        invoice_count     = invoice_count,
        overdue_count     = overdue_count,
        credit_days       = credit_days,
    )
