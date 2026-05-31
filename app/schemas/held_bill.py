from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel


class HeldBillCreate(BaseModel):
    customer_id:    Optional[int]     = None
    customer_name:  Optional[str]     = None
    invoice_no:     Optional[str]     = None
    invoice_date:   Optional[date]    = None
    doctor_name:    Optional[str]     = None
    payment_status: Optional[str]     = None
    net_amount:     Optional[Decimal] = None
    item_count:     Optional[int]     = None
    note:           Optional[str]     = None
    payload:        Any                       # full editable draft (rows + header)


class HeldBillResponse(BaseModel):
    id:             int
    hold_no:        Optional[str]      = None
    customer_id:    Optional[int]      = None
    customer_name:  Optional[str]      = None
    invoice_no:     Optional[str]      = None
    invoice_date:   Optional[date]     = None
    doctor_name:    Optional[str]      = None
    payment_status: Optional[str]      = None
    net_amount:     Optional[Decimal]  = None
    item_count:     Optional[int]      = None
    note:           Optional[str]      = None
    payload:        Any                 = None
    created_at:     Optional[datetime] = None
    updated_at:     Optional[datetime] = None

    model_config = {"from_attributes": True}
