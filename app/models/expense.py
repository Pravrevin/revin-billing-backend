from datetime import datetime

from sqlalchemy import BigInteger, Column, Date, ForeignKey, Numeric, String, Text, TIMESTAMP
from sqlalchemy.orm import relationship

from app.database import Base


class ExpenseMaster(Base):
    """
    Day-to-day business expenses (rent, salary, utilities, misc).
    Money OUT that is not a supplier payment — feeds the Cash / Bank Book.
    """
    __tablename__ = "expense_master"

    id              = Column(BigInteger, primary_key=True, autoincrement=True)

    expense_date    = Column(Date, nullable=False)
    category        = Column(String(100))
    description     = Column(Text)
    amount          = Column(Numeric(12, 2), nullable=False)

    payment_mode_id = Column(BigInteger, ForeignKey("payment_mode_master.id", ondelete="SET NULL"),
                             nullable=True)
    reference_no    = Column(String(100))
    notes           = Column(Text)

    created_at      = Column(TIMESTAMP, default=datetime.utcnow)
    updated_at      = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)

    payment_mode    = relationship("PaymentModeMaster", foreign_keys=[payment_mode_id])
