from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class MarketerMasterCreate(BaseModel):
    marketer_name: str           = Field(..., max_length=255)
    address:       Optional[str] = None
    city:          Optional[str] = None
    state:         Optional[str] = None
    pincode:       Optional[str] = None
    phone:         Optional[str] = None
    email:         Optional[str] = None
    gstin:         Optional[str] = None
    is_active:     bool          = True
    extra_data:    Optional[Any] = None


class MarketerMasterUpdate(BaseModel):
    marketer_name: Optional[str] = None
    address:       Optional[str] = None
    city:          Optional[str] = None
    state:         Optional[str] = None
    pincode:       Optional[str] = None
    phone:         Optional[str] = None
    email:         Optional[str] = None
    gstin:         Optional[str] = None
    is_active:     Optional[bool] = None
    extra_data:    Optional[Any]  = None


class MarketerMasterResponse(BaseModel):
    id:            int
    marketer_code: str
    marketer_name: str
    address:       Optional[str] = None
    city:          Optional[str] = None
    state:         Optional[str] = None
    pincode:       Optional[str] = None
    phone:         Optional[str] = None
    email:         Optional[str] = None
    gstin:         Optional[str] = None
    is_active:     bool
    created_at:    datetime
    updated_at:    datetime

    model_config = {"from_attributes": True}
