from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class UnitMasterCreate(BaseModel):
    unit_name: str  = Field(..., max_length=50)
    is_active: bool = True


class UnitMasterUpdate(BaseModel):
    is_active: Optional[bool] = None


class UnitMasterResponse(BaseModel):
    unit_name:  str
    is_active:  bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
