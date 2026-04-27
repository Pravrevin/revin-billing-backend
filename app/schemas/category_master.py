from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class CategoryMasterCreate(BaseModel):
    category_name: str           = Field(..., max_length=255)
    description:   Optional[str] = None
    is_active:     bool          = True


class CategoryMasterUpdate(BaseModel):
    category_name: Optional[str] = None
    description:   Optional[str] = None
    is_active:     Optional[bool] = None


class CategoryMasterResponse(BaseModel):
    id:            int
    category_code: str
    category_name: str
    description:   Optional[str] = None
    is_active:     bool
    created_at:    datetime
    updated_at:    datetime

    model_config = {"from_attributes": True}


# ── Sub Category ───────────────────────────────────────────────────────────────

class SubCategoryMasterCreate(BaseModel):
    sub_category_name: str           = Field(..., max_length=255)
    category_id:       int
    description:       Optional[str] = None
    is_active:         bool          = True


class SubCategoryMasterUpdate(BaseModel):
    sub_category_name: Optional[str] = None
    category_id:       Optional[int] = None
    description:       Optional[str] = None
    is_active:         Optional[bool] = None


class SubCategoryMasterResponse(BaseModel):
    id:               int
    sub_category_code: str
    sub_category_name: str
    category_id:       int
    category_name:     Optional[str] = None
    description:       Optional[str] = None
    is_active:         bool
    created_at:        datetime
    updated_at:        datetime

    model_config = {"from_attributes": True}
