from datetime import datetime
from sqlalchemy import BigInteger, Boolean, Column, String, TIMESTAMP

from app.database import TenantBase as Base


class UnitMaster(Base):
    __tablename__ = "unit_master"

    # Composite PK (pharmacy_id, unit_name): the same unit name may exist in
    # different pharmacies. Overrides the plain pharmacy_id from TenantBase.
    pharmacy_id = Column(BigInteger, primary_key=True, nullable=False)
    unit_name   = Column(String(50), primary_key=True)

    is_active   = Column(Boolean, default=True)
    created_at  = Column(TIMESTAMP, default=datetime.utcnow)
    updated_at  = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)
