from datetime import date, datetime
from decimal import Decimal
from typing import Any, List, Optional

from pydantic import BaseModel, Field, model_validator


# ── Purchase Item ──────────────────────────────────────────────────────────────

class PurchaseItemBase(BaseModel):
    item_id:         int
    batch_no:        Optional[str]     = None
    quantity:        Optional[Decimal] = None
    free_quantity:   Optional[Decimal] = None
    purchase_rate:   Optional[Decimal] = None
    mrp:             Optional[Decimal] = None
    sale_rate:       Optional[Decimal] = None
    gross_amount:    Optional[Decimal] = None
    discount:        Optional[Decimal] = None   # percentage
    discount_amount: Optional[Decimal] = None
    gst_percent:     Optional[Decimal] = None   # percentage
    tax_amount:      Optional[Decimal] = None
    total:           Optional[Decimal] = None
    expiry_date:     Optional[date]    = None


class PurchaseItemCreate(PurchaseItemBase):
    pass


class PurchaseItemUpdate(BaseModel):
    batch_no:        Optional[str]     = None
    quantity:        Optional[Decimal] = None
    free_quantity:   Optional[Decimal] = None
    purchase_rate:   Optional[Decimal] = None
    mrp:             Optional[Decimal] = None
    sale_rate:       Optional[Decimal] = None
    gross_amount:    Optional[Decimal] = None
    discount:        Optional[Decimal] = None
    discount_amount: Optional[Decimal] = None
    gst_percent:     Optional[Decimal] = None
    tax_amount:      Optional[Decimal] = None
    total:           Optional[Decimal] = None
    expiry_date:     Optional[date]    = None


class PurchaseItemResponse(PurchaseItemBase):
    id:          int
    purchase_id: int
    item_name:   Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def extract_item_name(cls, data):
        if hasattr(data, "item") and data.item is not None:
            data.__dict__["item_name"] = data.item.item_name
        return data

    model_config = {"from_attributes": True}


# ── Purchase Master ────────────────────────────────────────────────────────────

class PurchaseMasterBase(BaseModel):
    invoice_no:          Optional[str]     = None
    invoice_date:        Optional[date]    = None
    entry_date:          Optional[date]    = None
    due_date:            Optional[date]    = None
    supplier_id:         Optional[int]     = None
    total_amount:        Optional[Decimal] = None
    discount_percentage: Optional[Decimal] = None
    discount_amount:     Optional[Decimal] = None
    tax_percentage:      Optional[Decimal] = None
    tax_amount:          Optional[Decimal] = None
    net_amount:          Optional[Decimal] = None
    extra_data:          Optional[Any]     = None


class PurchaseMasterCreate(PurchaseMasterBase):
    items: List[PurchaseItemCreate] = []


class PurchaseMasterUpdate(BaseModel):
    invoice_no:          Optional[str]     = None
    invoice_date:        Optional[date]    = None
    entry_date:          Optional[date]    = None
    due_date:            Optional[date]    = None
    supplier_id:         Optional[int]     = None
    total_amount:        Optional[Decimal] = None
    discount_percentage: Optional[Decimal] = None
    discount_amount:     Optional[Decimal] = None
    tax_percentage:      Optional[Decimal] = None
    tax_amount:          Optional[Decimal] = None
    net_amount:          Optional[Decimal] = None
    extra_data:          Optional[Any]     = None


class PurchaseMasterResponse(PurchaseMasterBase):
    id:            int
    created_at:    datetime
    updated_at:    datetime
    items:         List[PurchaseItemResponse] = []
    supplier_name: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def extract_related_names(cls, data):
        if hasattr(data, "supplier") and data.supplier is not None:
            data.__dict__["supplier_name"] = data.supplier.party_name
        return data

    model_config = {"from_attributes": True}
