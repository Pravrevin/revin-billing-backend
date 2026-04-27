from datetime import datetime
from sqlalchemy import (
    BigInteger, Boolean, Column, Integer, Numeric,
    String, Text, TIMESTAMP
)
from sqlalchemy.dialects.postgresql import JSONB

from app.database import Base


class ItemMaster(Base):
    __tablename__ = "item_master"

    id                    = Column(BigInteger, primary_key=True, autoincrement=True)
    item_code             = Column(String(50),  unique=True, nullable=False)
    item_name             = Column(String(255), nullable=False)
    generic_name          = Column(String(255))
    brand_name            = Column(String(255))
    composition           = Column(Text)

    # Pharmaceutical
    strength              = Column(String(50))
    dosage_form           = Column(String(50))

    # Category / Classification — stored as names, validated against master tables
    category_name         = Column(String(255))
    sub_category_name     = Column(String(255))

    # Packaging — stored as packing_type, validated against packaging_master
    packing_type          = Column(String(50))

    # Packing
    pack_size             = Column(Integer)

    # Unit — stored as unit_name, validated against unit_master
    unit_name             = Column(String(50))

    # Units
    conversion_factor     = Column(Numeric(10, 2))

    # GST / Tax
    gst_percent           = Column(Numeric(5, 2))
    cgst                  = Column(Numeric(5, 2))
    sgst                  = Column(Numeric(5, 2))
    igst                  = Column(Numeric(5, 2))
    cess_percent          = Column(Numeric(5, 2))
    hsn_code              = Column(String(20))
    tax_type              = Column(String(20))   # inclusive / exclusive

    # Discount
    min_discount          = Column(Numeric(5, 2))
    max_discount          = Column(Numeric(5, 2))
    is_discount_allowed   = Column(Boolean, default=True)

    # Pricing
    pricing_type          = Column(String(20))   # MRP / RATE

    # Stock levels
    min_stock_level       = Column(Integer)
    max_stock_level       = Column(Integer)
    reorder_level         = Column(Integer)

    # Batch / Expiry
    is_batch_required     = Column(Boolean, default=True)
    is_expiry_required    = Column(Boolean, default=True)

    # Shelf / Lead time
    shelf_life_days       = Column(Integer)
    lead_time_days        = Column(Integer)

    # Regulatory
    schedule_type         = Column(String(10))   # H, H1, X, OTC
    is_narcotic           = Column(Boolean, default=False)
    is_psychotropic       = Column(Boolean, default=False)
    prescription_required = Column(Boolean, default=False)
    drug_license_required = Column(Boolean, default=False)
    regulatory_category   = Column(String(50))

    # Codes / Identifiers
    barcode               = Column(String(100))
    qr_code               = Column(Text)
    sku_code              = Column(String(100))
    external_code         = Column(String(100))

    # Status
    is_active             = Column(Boolean, default=True)

    # Audit
    created_at            = Column(TIMESTAMP, default=datetime.utcnow)
    updated_at            = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Extra metadata
    extra_data            = Column(JSONB)
