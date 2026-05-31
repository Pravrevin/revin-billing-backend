from datetime import date, datetime
from decimal import Decimal
from typing import Any, List, Optional

from pydantic import BaseModel, Field


# ── Return Item ──────────────────────────────────────────────────────────────

class SalesReturnItemCreate(BaseModel):
    sales_item_id: Optional[int]     = None
    item_id:       int
    batch_no:      Optional[str]     = None
    quantity:      Decimal           = Field(..., gt=0)
    mrp:           Optional[Decimal] = None
    sale_rate:     Optional[Decimal] = None
    gst_percent:   Optional[Decimal] = None
    tax_amount:    Optional[Decimal] = None
    total:         Optional[Decimal] = None
    expiry_date:   Optional[date]    = None


class SalesReturnItemResponse(BaseModel):
    id:            int
    return_id:     int
    sales_item_id: Optional[int]     = None
    item_id:       int
    item_name:     Optional[str]     = None
    batch_no:      Optional[str]     = None
    quantity:      Optional[Decimal] = None
    mrp:           Optional[Decimal] = None
    sale_rate:     Optional[Decimal] = None
    gst_percent:   Optional[Decimal] = None
    tax_amount:    Optional[Decimal] = None
    total:         Optional[Decimal] = None
    expiry_date:   Optional[date]    = None


# ── Return Master ────────────────────────────────────────────────────────────

class SalesReturnCreate(BaseModel):
    sales_id:       int
    return_date:    Optional[date]    = None
    reason:         Optional[str]     = None
    notes:          Optional[str]     = None
    refund_amount:  Optional[Decimal] = Field(None, ge=0)
    refund_mode_id: Optional[int]     = None
    refund_status:  Optional[str]     = None
    items:          List[SalesReturnItemCreate] = []


class SalesReturnResponse(BaseModel):
    id:                int
    return_no:         Optional[str]     = None
    return_date:       date
    sales_id:          Optional[int]     = None
    invoice_no:        Optional[str]     = None
    customer_id:       Optional[int]     = None
    customer_name:     Optional[str]     = None
    total_amount:      Optional[Decimal] = None
    tax_amount:        Optional[Decimal] = None
    refund_amount:     Optional[Decimal] = None
    refund_mode_id:    Optional[int]     = None
    refund_mode_name:  Optional[str]     = None
    refund_status:     Optional[str]     = None
    reason:            Optional[str]     = None
    notes:             Optional[str]     = None
    created_at:        Optional[datetime] = None
    updated_at:        Optional[datetime] = None
    extra_data:        Optional[Any]      = None
    items:             List[SalesReturnItemResponse] = []


# ── Returnable summary (per sold line) ───────────────────────────────────────

class ReturnableLine(BaseModel):
    sales_item_id: int
    item_id:       int
    item_name:     Optional[str]     = None
    batch_no:      Optional[str]     = None
    sold_qty:      Decimal
    returned_qty:  Decimal
    returnable_qty: Decimal
    mrp:           Optional[Decimal] = None
    sale_rate:     Optional[Decimal] = None
    gst_percent:   Optional[Decimal] = None
    expiry_date:   Optional[date]    = None


class ReturnableResponse(BaseModel):
    sales_id:      int
    invoice_no:    Optional[str]  = None
    invoice_date:  Optional[date] = None
    customer_id:   Optional[int]  = None
    customer_name: Optional[str]  = None
    lines:         List[ReturnableLine] = []
