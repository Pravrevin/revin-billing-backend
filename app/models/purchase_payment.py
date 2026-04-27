from datetime import datetime

from sqlalchemy import BigInteger, Column, Date, ForeignKey, Integer, Numeric, String, Text, TIMESTAMP
from sqlalchemy.orm import relationship

from app.database import Base


class PartyCreditConfig(Base):
    """
    Overdue / credit-days configuration.
    party_id = NULL  → global default (exactly one such row is seeded).
    party_id = X     → override for that specific party.
    """
    __tablename__ = "party_credit_config"

    id                 = Column(BigInteger, primary_key=True, autoincrement=True)
    party_id           = Column(BigInteger, ForeignKey("party_master.id", ondelete="CASCADE"),
                                unique=True, nullable=True)
    credit_days        = Column(Integer, nullable=False, default=30)
    overdue_grace_days = Column(Integer, nullable=False, default=0)
    created_at         = Column(TIMESTAMP, default=datetime.utcnow)
    updated_at         = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)

    party              = relationship("PartyMaster", backref="credit_config")


class PaymentMaster(Base):
    """
    Unified payment table.
      txn_type = RECEIPT  — money received from a customer  (reference_type='sale')
      txn_type = PAYMENT  — money paid out to a distributor (reference_type='purchase')
    """
    __tablename__ = "payment_master"

    id              = Column(BigInteger, primary_key=True, autoincrement=True)

    party_id        = Column(BigInteger, ForeignKey("party_master.id", ondelete="RESTRICT"),
                             nullable=False)

    txn_type        = Column(String(20), nullable=False)   # RECEIPT / PAYMENT
    reference_type  = Column(String(20))                   # sale / purchase / advance
    reference_id    = Column(BigInteger)                   # sales_master.id or purchase_master.id

    txn_date        = Column(Date, nullable=False)
    amount          = Column(Numeric(12, 2), nullable=False)

    payment_mode_id = Column(BigInteger, ForeignKey("payment_mode_master.id", ondelete="SET NULL"),
                             nullable=True)
    reference_no    = Column(String(100))
    notes           = Column(Text)

    created_at      = Column(TIMESTAMP, default=datetime.utcnow)
    updated_at      = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)

    party           = relationship("PartyMaster",       backref="payments")
    payment_mode    = relationship("PaymentModeMaster", foreign_keys=[payment_mode_id])
