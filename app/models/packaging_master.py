from datetime import datetime
from sqlalchemy import BigInteger, Boolean, Column, String, TIMESTAMP

from app.database import Base


class PackagingMaster(Base):
    __tablename__ = "packaging_master"

    id              = Column(BigInteger, primary_key=True, autoincrement=True)
    packing_type    = Column(String(50),  unique=True, nullable=False)
    unit_primary    = Column(String(50))
    unit_secondary  = Column(String(50))

    is_active       = Column(Boolean, default=True)
    created_at      = Column(TIMESTAMP, default=datetime.utcnow)
    updated_at      = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)
