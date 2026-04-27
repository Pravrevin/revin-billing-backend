from datetime import datetime
from sqlalchemy import Boolean, Column, String, TIMESTAMP

from app.database import Base


class UnitMaster(Base):
    __tablename__ = "unit_master"

    unit_name   = Column(String(50), primary_key=True)

    is_active   = Column(Boolean, default=True)
    created_at  = Column(TIMESTAMP, default=datetime.utcnow)
    updated_at  = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)
