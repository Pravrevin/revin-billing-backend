from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, Field, model_validator


class StockMasterBase(BaseModel):
    item_id:            int
    batch_no:           str             = Field(..., max_length=50)
    manufacture_date:   Optional[date]  = None
    expiry_date:        Optional[date]  = None

    mrp:                Optional[Decimal] = None
    purchase_rate:      Optional[Decimal] = None
    sale_rate:          Optional[Decimal] = None

    quantity:           Optional[Decimal] = None
    free_quantity:      Optional[Decimal] = None

    warehouse_id:       Optional[int]   = None
    rack_location:      Optional[str]   = None

    extra_data:         Optional[Any]   = None


class StockMasterCreate(StockMasterBase):
    pass


class StockMasterUpdate(BaseModel):
    batch_no:           Optional[str]     = None
    manufacture_date:   Optional[date]    = None
    expiry_date:        Optional[date]    = None
    mrp:                Optional[Decimal] = None
    purchase_rate:      Optional[Decimal] = None
    sale_rate:          Optional[Decimal] = None
    quantity:           Optional[Decimal] = None
    free_quantity:      Optional[Decimal] = None
    warehouse_id:       Optional[int]     = None
    rack_location:      Optional[str]     = None
    extra_data:         Optional[Any]     = None


class StockMasterResponse(StockMasterBase):
    id:         int
    created_at: datetime
    updated_at: datetime
    item_name:  Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def extract_item_name(cls, data):
        if hasattr(data, "item") and data.item is not None:
            data.__dict__["item_name"] = data.item.item_name
        return data

    model_config = {"from_attributes": True}


# ── Stock Ledger ───────────────────────────────────────────────────────────────

class StockLedgerResponse(BaseModel):
    id:             int
    item_id:        int
    batch_no:       Optional[str]     = None
    movement_type:  str
    quantity:       Optional[Decimal] = None
    free_quantity:  Optional[Decimal] = None
    reference_type: Optional[str]    = None
    reference_id:   Optional[int]    = None
    purchase_rate:  Optional[Decimal] = None
    mrp:            Optional[Decimal] = None
    created_at:     datetime
    item_name:      Optional[str]    = None

    @model_validator(mode="before")
    @classmethod
    def extract_item_name(cls, data):
        if hasattr(data, "item") and data.item is not None:
            data.__dict__["item_name"] = data.item.item_name
        return data

    model_config = {"from_attributes": True}
