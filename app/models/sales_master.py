from datetime import date, datetime
from sqlalchemy import BigInteger, Column, Date, ForeignKey, Numeric, String, TIMESTAMP
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.database import Base


class SalesMaster(Base):
    __tablename__ = "sales_master"

    id              = Column(BigInteger, primary_key=True, autoincrement=True)
    invoice_no      = Column(String(50))
    invoice_date    = Column(Date)

    customer_id     = Column(BigInteger, ForeignKey("party_master.id", ondelete="RESTRICT"))

    doctor_name     = Column(String(255))

    total_amount    = Column(Numeric(12, 2))
    discount        = Column(Numeric(10, 2))
    tax_amount      = Column(Numeric(10, 2))
    net_amount      = Column(Numeric(12, 2))

    payment_mode_id = Column(BigInteger, ForeignKey("payment_mode_master.id", ondelete="SET NULL"), nullable=True)
    payment_status  = Column(String(20))

    created_at      = Column(TIMESTAMP, default=datetime.utcnow)
    updated_at      = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)

    extra_data      = Column(JSONB)

    customer        = relationship("PartyMaster", backref="sales")
    payment_mode    = relationship("PaymentModeMaster", foreign_keys=[payment_mode_id])
    items           = relationship("SalesItem", back_populates="sale", cascade="all, delete-orphan")


class SalesItem(Base):
    __tablename__ = "sales_items"

    id              = Column(BigInteger, primary_key=True, autoincrement=True)
    sales_id        = Column(BigInteger, ForeignKey("sales_master.id", ondelete="CASCADE"))

    item_id         = Column(BigInteger, ForeignKey("item_master.id", ondelete="RESTRICT"))
    batch_no        = Column(String(50))

    quantity        = Column(Numeric(10, 2))

    mrp             = Column(Numeric(10, 2))
    sale_rate       = Column(Numeric(10, 2))

    discount        = Column(Numeric(10, 2))
    gst_percent     = Column(Numeric(5, 2))
    tax_amount      = Column(Numeric(10, 2))

    expiry_date     = Column(Date)

    total           = Column(Numeric(12, 2))

    sale            = relationship("SalesMaster", back_populates="items")
    item            = relationship("ItemMaster", backref="sales_items")
