from datetime import datetime
from sqlalchemy import BigInteger, Boolean, Column, Integer, Numeric, String, Text, TIMESTAMP
from sqlalchemy.dialects.postgresql import JSONB

from app.database import Base


class PartyMaster(Base):
    __tablename__ = "party_master"

    id                  = Column(BigInteger, primary_key=True, autoincrement=True)
    party_code          = Column(String(50), unique=True)
    party_name          = Column(String(255))

    party_type          = Column(String(20))   # Customer / Distributor

    mobile              = Column(String(20))
    email               = Column(String(100))

    gstin               = Column(String(20))
    drug_license_no     = Column(String(50))

    address             = Column(Text)
    city                = Column(String(100))
    state               = Column(String(100))
    pincode             = Column(String(10))

    credit_limit        = Column(Numeric(12, 2))
    credit_days         = Column(Integer)

    opening_balance     = Column(Numeric(12, 2))

    pan_card            = Column(String(10))    # Distributor only, optional
    bank_details        = Column(JSONB)         # Distributor only, optional

    is_active           = Column(Boolean, default=True)

    created_at          = Column(TIMESTAMP, default=datetime.utcnow)
    updated_at          = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)

    extra_data          = Column(JSONB)
