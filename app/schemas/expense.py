from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class ExpenseCreate(BaseModel):
    expense_date:    date
    category:        Optional[str]     = None
    description:     Optional[str]     = None
    amount:          Decimal           = Field(..., gt=0)
    payment_mode_id: Optional[int]     = None
    reference_no:    Optional[str]     = None
    notes:           Optional[str]     = None


class ExpenseUpdate(BaseModel):
    expense_date:    Optional[date]    = None
    category:        Optional[str]     = None
    description:     Optional[str]     = None
    amount:          Optional[Decimal] = Field(None, gt=0)
    payment_mode_id: Optional[int]     = None
    reference_no:    Optional[str]     = None
    notes:           Optional[str]     = None


class ExpenseResponse(BaseModel):
    id:                int
    expense_date:      date
    category:          Optional[str]      = None
    description:       Optional[str]      = None
    amount:            Decimal
    payment_mode_id:   Optional[int]      = None
    payment_mode_name: Optional[str]      = None
    reference_no:      Optional[str]      = None
    notes:             Optional[str]      = None
    created_at:        Optional[datetime] = None
    updated_at:        Optional[datetime] = None
