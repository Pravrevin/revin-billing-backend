from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class PackagingMasterCreate(BaseModel):
    packing_type:   str           = Field(..., max_length=50)
    unit_primary:   Optional[str] = Field(None, max_length=50)
    unit_secondary: Optional[str] = Field(None, max_length=50)
    is_active:      bool          = True


class PackagingMasterUpdate(BaseModel):
    packing_type:   Optional[str]  = None
    unit_primary:   Optional[str]  = None
    unit_secondary: Optional[str]  = None
    is_active:      Optional[bool] = None


class PackagingMasterResponse(BaseModel):
    id:             int
    packing_type:   str
    unit_primary:   Optional[str] = None
    unit_secondary: Optional[str] = None
    is_active:      bool
    created_at:     datetime
    updated_at:     datetime

    model_config = {"from_attributes": True}
