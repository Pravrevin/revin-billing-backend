from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, List, Optional

from pydantic import BaseModel, EmailStr, Field, model_validator


class PartyType(str, Enum):
    customer    = "Customer"
    distributor = "Distributor"


class PartyMasterBase(BaseModel):
    party_code:         Optional[str]       = Field(None, max_length=50)
    party_name:         Optional[str]       = Field(None, max_length=255)
    party_type:         Optional[PartyType] = None

    mobile:             Optional[str]     = None
    email:              Optional[str]     = None

    gstin:              Optional[str]     = None
    drug_license_no:    Optional[str]     = None

    address:            Optional[str]     = None
    city:               Optional[str]     = None
    state:              Optional[str]     = None
    pincode:            Optional[str]     = None

    credit_limit:       Optional[Decimal] = None
    credit_days:        Optional[int]     = None

    opening_balance:    Optional[Decimal] = None

    pan_card:           Optional[str]     = Field(None, max_length=10, description="PAN card number (Distributor only)")
    bank_details:       Optional[Any]     = Field(None, description="Bank details (Distributor only)")

    is_active:          bool              = True
    extra_data:         Optional[Any]     = None


class PartyMasterCreate(PartyMasterBase):
    party_name: str        = Field(..., max_length=255)
    party_type: PartyType  = Field(..., description="Customer or Distributor")

    @model_validator(mode="after")
    def distributor_only_fields(self):
        if self.party_type != PartyType.distributor:
            if self.pan_card is not None or self.bank_details is not None:
                raise ValueError("pan_card and bank_details are only applicable for Distributor party type")
        return self


class PartyMasterUpdate(BaseModel):
    party_name:         Optional[str]       = None
    party_type:         Optional[PartyType] = None
    mobile:             Optional[str]     = None
    email:              Optional[str]     = None
    gstin:              Optional[str]     = None
    drug_license_no:    Optional[str]     = None
    address:            Optional[str]     = None
    city:               Optional[str]     = None
    state:              Optional[str]     = None
    pincode:            Optional[str]     = None
    credit_limit:       Optional[Decimal] = None
    credit_days:        Optional[int]     = None
    opening_balance:    Optional[Decimal] = None
    pan_card:           Optional[str]     = None
    bank_details:       Optional[Any]     = None
    is_active:          Optional[bool]    = None
    extra_data:         Optional[Any]     = None


class PartyMasterResponse(PartyMasterBase):
    id:         int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
