from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, Field


class ItemMasterBase(BaseModel):
    item_name:              str           = Field(..., max_length=255)
    generic_name:           Optional[str] = None
    brand_name:             Optional[str] = None
    composition:            Optional[str] = None

    strength:               Optional[str] = None
    dosage_form:            Optional[str] = None

    category_name:          Optional[str] = None
    sub_category_name:      Optional[str] = None

    packing_type:           Optional[str] = None
    pack_size:              Optional[int] = None
    unit_name:              Optional[str] = None
    conversion_factor:      Optional[Decimal] = None

    gst_percent:            Optional[Decimal] = None
    cgst:                   Optional[Decimal] = None
    sgst:                   Optional[Decimal] = None
    igst:                   Optional[Decimal] = None
    cess_percent:           Optional[Decimal] = None
    hsn_code:               Optional[str] = None
    tax_type:               Optional[str] = Field(None, description="inclusive or exclusive")

    min_discount:           Optional[Decimal] = None
    max_discount:           Optional[Decimal] = None
    is_discount_allowed:    bool = True

    pricing_type:           Optional[str] = Field(None, description="MRP or RATE")

    min_stock_level:        Optional[int] = None
    max_stock_level:        Optional[int] = None
    reorder_level:          Optional[int] = None

    is_batch_required:      bool = True
    is_expiry_required:     bool = True

    shelf_life_days:        Optional[int] = None
    lead_time_days:         Optional[int] = None

    schedule_type:          Optional[str] = Field(None, description="H, H1, X, OTC")
    is_narcotic:            bool = False
    is_psychotropic:        bool = False
    prescription_required:  bool = False
    drug_license_required:  bool = False
    regulatory_category:    Optional[str] = None

    barcode:                Optional[str] = None
    qr_code:                Optional[str] = None
    sku_code:               Optional[str] = None
    external_code:          Optional[str] = None

    is_active:              bool = True
    extra_data:             Optional[Any] = None


class ItemMasterCreate(ItemMasterBase):
    pass


class ItemMasterUpdate(BaseModel):
    """All fields optional for partial update (PATCH)."""
    item_name:              Optional[str] = None
    generic_name:           Optional[str] = None
    brand_name:             Optional[str] = None
    composition:            Optional[str] = None
    strength:               Optional[str] = None
    dosage_form:            Optional[str] = None
    category_name:          Optional[str] = None
    sub_category_name:      Optional[str] = None
    packing_type:           Optional[str] = None
    pack_size:              Optional[int] = None
    unit_name:              Optional[str] = None
    conversion_factor:      Optional[Decimal] = None
    gst_percent:            Optional[Decimal] = None
    cgst:                   Optional[Decimal] = None
    sgst:                   Optional[Decimal] = None
    igst:                   Optional[Decimal] = None
    cess_percent:           Optional[Decimal] = None
    hsn_code:               Optional[str] = None
    tax_type:               Optional[str] = None
    min_discount:           Optional[Decimal] = None
    max_discount:           Optional[Decimal] = None
    is_discount_allowed:    Optional[bool] = None
    pricing_type:           Optional[str] = None
    min_stock_level:        Optional[int] = None
    max_stock_level:        Optional[int] = None
    reorder_level:          Optional[int] = None
    is_batch_required:      Optional[bool] = None
    is_expiry_required:     Optional[bool] = None
    shelf_life_days:        Optional[int] = None
    lead_time_days:         Optional[int] = None
    schedule_type:          Optional[str] = None
    is_narcotic:            Optional[bool] = None
    is_psychotropic:        Optional[bool] = None
    prescription_required:  Optional[bool] = None
    drug_license_required:  Optional[bool] = None
    regulatory_category:    Optional[str] = None
    barcode:                Optional[str] = None
    qr_code:                Optional[str] = None
    sku_code:               Optional[str] = None
    external_code:          Optional[str] = None
    is_active:              Optional[bool] = None
    extra_data:             Optional[Any] = None


class ItemMasterResponse(ItemMasterBase):
    id:         int
    item_code:  str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
