from datetime import date, datetime
from decimal import Decimal
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


# ── Party Credit Config ────────────────────────────────────────────────────────

class PartyCreditConfigBase(BaseModel):
    party_id:           Optional[int] = Field(None, description="NULL = global default")
    credit_days:        int           = Field(30, ge=0)
    overdue_grace_days: int           = Field(0,  ge=0)


class PartyCreditConfigCreate(PartyCreditConfigBase):
    pass


class PartyCreditConfigUpdate(BaseModel):
    credit_days:        Optional[int] = Field(None, ge=0)
    overdue_grace_days: Optional[int] = Field(None, ge=0)


class PartyCreditConfigResponse(PartyCreditConfigBase):
    id:         int
    party_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Payment Master ─────────────────────────────────────────────────────────────

class PaymentMasterCreate(BaseModel):
    party_id:        int
    txn_type:        Literal["RECEIPT", "PAYMENT"]
    reference_type:  Optional[Literal["sale", "purchase", "advance", "adjustment"]] = None
    reference_id:    Optional[int]     = None
    txn_date:        date
    amount:          Decimal           = Field(..., gt=0)
    payment_mode_id: Optional[int]     = None
    reference_no:    Optional[str]     = None
    notes:           Optional[str]     = None


class PaymentMasterUpdate(BaseModel):
    txn_date:        Optional[date]    = None
    amount:          Optional[Decimal] = Field(None, gt=0)
    payment_mode_id: Optional[int]     = None
    reference_no:    Optional[str]     = None
    notes:           Optional[str]     = None


class PaymentMasterResponse(BaseModel):
    id:                int
    party_id:          int
    party_name:        Optional[str]  = None
    txn_type:          str
    reference_type:    Optional[str]  = None
    reference_id:      Optional[int]  = None
    reference_no_doc:  Optional[str]  = None   # invoice_no of the linked doc
    txn_date:          date
    amount:            Decimal
    payment_mode_id:   Optional[int]  = None
    payment_mode_name: Optional[str]  = None
    reference_no:      Optional[str]  = None
    notes:             Optional[str]  = None
    receipt_path:      Optional[str]  = None   # URL of uploaded receipt, if any
    created_at:        datetime
    updated_at:        datetime

    model_config = {"from_attributes": True}


# ── Outstanding Invoice (purchase) ─────────────────────────────────────────────

class OutstandingInvoice(BaseModel):
    id:                 int
    invoice_no:         Optional[str]     = None
    invoice_date:       Optional[date]    = None
    entry_date:         Optional[date]    = None
    due_date:           Optional[date]    = None
    effective_due_date: Optional[date]    = None
    supplier_id:        Optional[int]     = None
    supplier_name:      Optional[str]     = None
    net_amount:         Optional[Decimal] = None
    total_paid:         Decimal           = Decimal("0")
    outstanding_amount: Decimal           = Decimal("0")
    payment_status:     Optional[str]     = None   # computed: Paid / Partial / Unpaid
    is_overdue:         bool              = False
    days_overdue:       int               = 0
    credit_days:        int               = 30
    payments:           List[PaymentMasterResponse] = []


# ── Outstanding Sale (receivable) ──────────────────────────────────────────────

class OutstandingSale(BaseModel):
    id:                 int
    invoice_no:         Optional[str]     = None
    invoice_date:       Optional[date]    = None
    customer_id:        Optional[int]     = None
    customer_name:      Optional[str]     = None
    net_amount:         Optional[Decimal] = None
    total_received:     Decimal           = Decimal("0")
    outstanding_amount: Decimal           = Decimal("0")
    payment_status:     Optional[str]     = None
    is_overdue:         bool              = False
    days_overdue:       int               = 0
    credit_days:        int               = 30
    receipts:           List[PaymentMasterResponse] = []


# ── Party Ledger Entry ─────────────────────────────────────────────────────────

class PartyLedgerEntry(BaseModel):
    """
    One row in the running ledger for a party.

    For a DISTRIBUTOR (payable):
      debit  = invoice raised (we owe them)
      credit = payment made   (we paid them)

    For a CUSTOMER (receivable):
      debit  = sale invoice   (they owe us)
      credit = receipt        (they paid us)
    """
    entry_date:     date
    entry_type:     str            # INVOICE / RECEIPT / PAYMENT
    reference_type: Optional[str] = None
    reference_id:   Optional[int] = None
    doc_no:         Optional[str] = None
    description:    str
    debit:          Decimal       = Decimal("0")
    credit:         Decimal       = Decimal("0")
    balance:        Decimal       = Decimal("0")   # running balance (positive = still owes)


# ── Party Outstanding Summary ──────────────────────────────────────────────────

class PartyOutstandingSummary(BaseModel):
    party_id:           int
    party_name:         Optional[str]  = None
    party_type:         Optional[str]  = None
    total_invoiced:     Decimal        = Decimal("0")
    total_settled:      Decimal        = Decimal("0")
    total_outstanding:  Decimal        = Decimal("0")
    overdue_amount:     Decimal        = Decimal("0")
    invoice_count:      int            = 0
    overdue_count:      int            = 0
    credit_days:        int            = 30


# ── Supplier (creditor) ledger — industry-standard statement ────────────────────

class SupplierLedgerRow(BaseModel):
    """
    One line of a supplier account statement (buyer's books, creditor account).

      Purchase Invoice  → CREDIT (our payable to the supplier increases)
      Payment made      → DEBIT  (payable decreases)

    `balance` is the absolute running balance and `balance_type` is 'Cr'
    (we still owe the supplier) or 'Dr' (we are in advance / overpaid).
    """
    entry_date:   date
    particulars:  str                       # "Purchase Invoice", "Payment - Cash", "Opening Balance"
    voucher_type: str                       # Opening / Purchase / Payment
    voucher_no:   Optional[str] = None
    debit:        Decimal       = Decimal("0")
    credit:       Decimal       = Decimal("0")
    balance:      Decimal       = Decimal("0")
    balance_type: str           = "Cr"


class SupplierLedgerResponse(BaseModel):
    party_id:             int
    party_name:           Optional[str] = None
    party_code:           Optional[str] = None
    gstin:                Optional[str] = None
    from_date:            Optional[date] = None
    to_date:              Optional[date] = None
    opening_balance:      Decimal = Decimal("0")
    opening_balance_type: str     = "Cr"
    rows:                 List[SupplierLedgerRow] = []
    total_debit:          Decimal = Decimal("0")
    total_credit:         Decimal = Decimal("0")
    closing_balance:      Decimal = Decimal("0")
    closing_balance_type: str     = "Cr"
