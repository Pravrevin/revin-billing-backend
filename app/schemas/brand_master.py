from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class BrandMasterCreate(BaseModel):
    brand_name: str  = Field(..., max_length=255)
    is_active:  bool = True


class BrandMasterUpdate(BaseModel):
    brand_name: Optional[str]  = None
    is_active:  Optional[bool] = None


class BrandMasterResponse(BaseModel):
    id:         int
    brand_name: str
    is_active:  bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
