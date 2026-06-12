from datetime import datetime
from sqlalchemy import BigInteger, Boolean, Column, String, TIMESTAMP

from app.database import TenantBase as Base


class BrandMaster(Base):
    __tablename__ = "brand_master"

    id          = Column(BigInteger, primary_key=True, autoincrement=True)
    brand_name  = Column(String(255), unique=True, nullable=False)

    is_active   = Column(Boolean, default=True)
    created_at  = Column(TIMESTAMP, default=datetime.utcnow)
    updated_at  = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)
