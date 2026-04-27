from datetime import date, datetime
from sqlalchemy import BigInteger, Column, Date, ForeignKey, Numeric, String, TIMESTAMP
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.database import Base


class StockMaster(Base):
    __tablename__ = "stock_master"

    id                  = Column(BigInteger, primary_key=True, autoincrement=True)
    item_id             = Column(BigInteger, ForeignKey("item_master.id", ondelete="RESTRICT"), nullable=False)

    # Batch / Dates
    batch_no            = Column(String(50), nullable=False)
    manufacture_date    = Column(Date)
    expiry_date         = Column(Date)

    # Pricing
    mrp                 = Column(Numeric(10, 2))
    purchase_rate       = Column(Numeric(10, 2))
    sale_rate           = Column(Numeric(10, 2))

    # Quantity
    quantity            = Column(Numeric(10, 2))
    free_quantity       = Column(Numeric(10, 2))

    # Location
    warehouse_id        = Column(BigInteger)
    rack_location       = Column(String(100))

    # Audit
    created_at          = Column(TIMESTAMP, default=datetime.utcnow)
    updated_at          = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)

    extra_data          = Column(JSONB)

    item                = relationship("ItemMaster", backref="stock_entries")


class StockLedger(Base):
    __tablename__ = "stock_ledger"

    id              = Column(BigInteger, primary_key=True, autoincrement=True)
    item_id         = Column(BigInteger, ForeignKey("item_master.id", ondelete="RESTRICT"))
    batch_no        = Column(String(50))

    movement_type   = Column(String(10), nullable=False)   # IN / OUT
    quantity        = Column(Numeric(10, 2))
    free_quantity   = Column(Numeric(10, 2))

    reference_type  = Column(String(20))   # purchase / sale / adjustment
    reference_id    = Column(BigInteger)   # purchase_master.id or sales_master.id

    purchase_rate   = Column(Numeric(10, 2))
    mrp             = Column(Numeric(10, 2))

    created_at      = Column(TIMESTAMP, default=datetime.utcnow)

    item            = relationship("ItemMaster", backref="ledger_entries")
