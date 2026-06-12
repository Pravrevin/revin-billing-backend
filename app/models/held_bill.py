from datetime import datetime

from sqlalchemy import BigInteger, Column, Date, ForeignKey, Integer, Numeric, String, Text, TIMESTAMP
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.database import TenantBase as Base


class HeldBill(Base):
    """
    A parked / draft sales bill. NO stock is reserved or deducted — that only
    happens when the bill is resumed and processed into a real sale.
    `payload` stores the full editable draft so the UI can resume it exactly.
    """
    __tablename__ = "held_bill"

    id              = Column(BigInteger, primary_key=True, autoincrement=True)
    hold_no         = Column(String(50))

    customer_id     = Column(BigInteger, ForeignKey("party_master.id", ondelete="SET NULL"), nullable=True)
    customer_name   = Column(String(255))
    invoice_no      = Column(String(50))
    invoice_date    = Column(Date)
    doctor_name     = Column(String(255))
    payment_status  = Column(String(20))

    net_amount      = Column(Numeric(12, 2))
    item_count      = Column(Integer)
    note            = Column(Text)

    payload         = Column(JSONB)

    created_at      = Column(TIMESTAMP, default=datetime.utcnow)
    updated_at      = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)

    customer        = relationship("PartyMaster", foreign_keys=[customer_id])
