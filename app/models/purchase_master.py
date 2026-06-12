from datetime import date, datetime
from sqlalchemy import BigInteger, Column, Date, ForeignKey, Numeric, String, TIMESTAMP
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.database import TenantBase as Base


class PurchaseMaster(Base):
    __tablename__ = "purchase_master"

    id                  = Column(BigInteger, primary_key=True, autoincrement=True)
    invoice_no          = Column(String(50))
    invoice_date        = Column(Date)
    entry_date          = Column(Date)
    due_date            = Column(Date)

    supplier_id         = Column(BigInteger, ForeignKey("party_master.id", ondelete="RESTRICT"))

    total_amount        = Column(Numeric(12, 2))
    discount_percentage = Column(Numeric(5, 2))
    discount_amount     = Column(Numeric(10, 2))
    tax_percentage      = Column(Numeric(5, 2))
    tax_amount          = Column(Numeric(10, 2))
    net_amount          = Column(Numeric(12, 2))

    created_at          = Column(TIMESTAMP, default=datetime.utcnow)
    updated_at          = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)

    extra_data          = Column(JSONB)

    supplier            = relationship("PartyMaster", backref="purchases")
    items               = relationship("PurchaseItem", back_populates="purchase", cascade="all, delete-orphan")


class PurchaseItem(Base):
    __tablename__ = "purchase_items"

    id              = Column(BigInteger, primary_key=True, autoincrement=True)
    purchase_id     = Column(BigInteger, ForeignKey("purchase_master.id", ondelete="CASCADE"))

    item_id         = Column(BigInteger, ForeignKey("item_master.id", ondelete="RESTRICT"))
    batch_no        = Column(String(50))

    quantity        = Column(Numeric(10, 2))
    free_quantity   = Column(Numeric(10, 2))

    purchase_rate   = Column(Numeric(10, 2))
    mrp             = Column(Numeric(10, 2))
    sale_rate       = Column(Numeric(10, 2))

    gross_amount    = Column(Numeric(12, 2))   # quantity × purchase_rate
    discount        = Column(Numeric(5, 2))    # discount percentage
    discount_amount = Column(Numeric(10, 2))   # gross × discount%
    gst_percent     = Column(Numeric(5, 2))    # GST percentage
    tax_amount      = Column(Numeric(10, 2))   # taxable × gst%
    total           = Column(Numeric(12, 2))   # taxable + tax_amount

    expiry_date     = Column(Date)

    purchase        = relationship("PurchaseMaster", back_populates="items")
    item            = relationship("ItemMaster", backref="purchase_items")
