from datetime import date, datetime
from decimal import Decimal
from typing import Any, List, Optional

from pydantic import BaseModel, Field, model_validator


# ── Sales Item ─────────────────────────────────────────────────────────────────

class SalesItemBase(BaseModel):
    item_id:     int
    batch_no:    Optional[str]     = None
    quantity:    Optional[Decimal] = None
    mrp:         Optional[Decimal] = None
    sale_rate:   Optional[Decimal] = None
    discount:    Optional[Decimal] = None
    gst_percent: Optional[Decimal] = None
    tax_amount:  Optional[Decimal] = None
    expiry_date: Optional[date]    = None
    total:       Optional[Decimal] = None


class SalesItemCreate(SalesItemBase):
    pass


class SalesItemUpdate(BaseModel):
    batch_no:    Optional[str]     = None
    quantity:    Optional[Decimal] = None
    mrp:         Optional[Decimal] = None
    sale_rate:   Optional[Decimal] = None
    discount:    Optional[Decimal] = None
    gst_percent: Optional[Decimal] = None
    tax_amount:  Optional[Decimal] = None
    expiry_date: Optional[date]    = None
    total:       Optional[Decimal] = None


class SalesItemResponse(SalesItemBase):
    id:       int
    sales_id: int

    model_config = {"from_attributes": True}


# ── Sales Master ───────────────────────────────────────────────────────────────

class SalesMasterBase(BaseModel):
    invoice_no:      Optional[str]     = None
    invoice_date:    Optional[date]    = None
    customer_id:     Optional[int]     = None
    doctor_name:     Optional[str]     = None
    total_amount:    Optional[Decimal] = None
    discount:        Optional[Decimal] = None
    tax_amount:      Optional[Decimal] = None
    net_amount:      Optional[Decimal] = None
    payment_mode_id: Optional[int]     = None
    payment_status:  Optional[str]     = Field(None, description="Paid / Unpaid / Partial")
    extra_data:      Optional[Any]     = None


class SalesMasterCreate(SalesMasterBase):
    items: List[SalesItemCreate] = []


class SalesMasterUpdate(BaseModel):
    invoice_no:      Optional[str]     = None
    invoice_date:    Optional[date]    = None
    customer_id:     Optional[int]     = None
    doctor_name:     Optional[str]     = None
    total_amount:    Optional[Decimal] = None
    discount:        Optional[Decimal] = None
    tax_amount:      Optional[Decimal] = None
    net_amount:      Optional[Decimal] = None
    payment_mode_id: Optional[int]     = None
    payment_status:  Optional[str]     = None
    extra_data:      Optional[Any]     = None


class SalesMasterResponse(SalesMasterBase):
    id:                int
    created_at:        datetime
    updated_at:        datetime
    items:             List[SalesItemResponse] = []
    payment_mode_name: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def extract_payment_mode_name(cls, data):
        if hasattr(data, "payment_mode") and data.payment_mode is not None:
            data.__dict__["payment_mode_name"] = data.payment_mode.mode_name
        return data

    model_config = {"from_attributes": True}
