from datetime import datetime
from sqlalchemy import BigInteger, Boolean, Column, String, TIMESTAMP

from app.database import TenantBase as Base


class PaymentModeMaster(Base):
    __tablename__ = "payment_mode_master"

    id          = Column(BigInteger, primary_key=True, autoincrement=True)
    mode_name   = Column(String(50), unique=True, nullable=False)
    is_active   = Column(Boolean, default=True)

    created_at  = Column(TIMESTAMP, default=datetime.utcnow)
    updated_at  = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)
