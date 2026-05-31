from datetime import datetime

from sqlalchemy import BigInteger, Column, Date, ForeignKey, Numeric, String, Text, TIMESTAMP
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.database import Base


class SalesReturnMaster(Base):
    """
    Credit note — goods returned by a customer against a sales invoice.
    Returning stock is handled in the router (stock_master += qty and a
    stock_ledger IN row with reference_type='sale-return').
    """
    __tablename__ = "sales_return_master"

    id              = Column(BigInteger, primary_key=True, autoincrement=True)
    return_no       = Column(String(50))
    return_date     = Column(Date, nullable=False)

    sales_id        = Column(BigInteger, ForeignKey("sales_master.id", ondelete="SET NULL"))
    customer_id     = Column(BigInteger, ForeignKey("party_master.id", ondelete="SET NULL"))

    total_amount    = Column(Numeric(12, 2))
    tax_amount      = Column(Numeric(10, 2))
    refund_amount   = Column(Numeric(12, 2))
    refund_mode_id  = Column(BigInteger, ForeignKey("payment_mode_master.id", ondelete="SET NULL"), nullable=True)
    refund_status   = Column(String(20))

    reason          = Column(String(255))
    notes           = Column(Text)

    created_at      = Column(TIMESTAMP, default=datetime.utcnow)
    updated_at      = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)

    extra_data      = Column(JSONB)

    customer        = relationship("PartyMaster", foreign_keys=[customer_id])
    refund_mode     = relationship("PaymentModeMaster", foreign_keys=[refund_mode_id])
    items           = relationship("SalesReturnItem", back_populates="sales_return",
                                   cascade="all, delete-orphan")


class SalesReturnItem(Base):
    __tablename__ = "sales_return_items"

    id              = Column(BigInteger, primary_key=True, autoincrement=True)
    return_id       = Column(BigInteger, ForeignKey("sales_return_master.id", ondelete="CASCADE"))

    sales_item_id   = Column(BigInteger)
    item_id         = Column(BigInteger, ForeignKey("item_master.id", ondelete="RESTRICT"))
    batch_no        = Column(String(50))

    quantity        = Column(Numeric(10, 2))
    mrp             = Column(Numeric(10, 2))
    sale_rate       = Column(Numeric(10, 2))
    gst_percent     = Column(Numeric(5, 2))
    tax_amount      = Column(Numeric(10, 2))
    total           = Column(Numeric(12, 2))
    expiry_date     = Column(Date)

    sales_return    = relationship("SalesReturnMaster", back_populates="items")
    item            = relationship("ItemMaster", backref="sales_return_items")
