from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class PaymentModeMasterBase(BaseModel):
    mode_name:  str            = Field(..., max_length=50)
    is_active:  bool           = True


class PaymentModeMasterCreate(PaymentModeMasterBase):
    pass


class PaymentModeMasterUpdate(BaseModel):
    mode_name:  Optional[str]  = None
    is_active:  Optional[bool] = None


class PaymentModeMasterResponse(PaymentModeMasterBase):
    id:         int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
