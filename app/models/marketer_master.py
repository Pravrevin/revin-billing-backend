from datetime import datetime
from sqlalchemy import BigInteger, Boolean, Column, String, Text, TIMESTAMP
from sqlalchemy.dialects.postgresql import JSONB

from app.database import TenantBase as Base


class MarketerMaster(Base):
    __tablename__ = "marketer_master"

    id            = Column(BigInteger, primary_key=True, autoincrement=True)
    marketer_code = Column(String(50), unique=True, nullable=False)
    marketer_name = Column(String(255), nullable=False)
    address       = Column(Text)
    city          = Column(String(100))
    state         = Column(String(100))
    pincode       = Column(String(10))
    phone         = Column(String(20))
    email         = Column(String(100))
    gstin         = Column(String(20))
    is_active     = Column(Boolean, default=True)
    created_at    = Column(TIMESTAMP, default=datetime.utcnow)
    updated_at    = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)
    extra_data    = Column(JSONB)
