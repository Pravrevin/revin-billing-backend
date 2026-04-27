from datetime import datetime
from sqlalchemy import BigInteger, Boolean, Column, ForeignKey, String, Text, TIMESTAMP
from sqlalchemy.orm import relationship

from app.database import Base


class CategoryMaster(Base):
    __tablename__ = "category_master"

    id            = Column(BigInteger, primary_key=True, autoincrement=True)
    category_code = Column(String(50), unique=True, nullable=False)
    category_name = Column(String(255), nullable=False)
    description   = Column(Text)
    is_active     = Column(Boolean, default=True)
    created_at    = Column(TIMESTAMP, default=datetime.utcnow)
    updated_at    = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)

    sub_categories = relationship("SubCategoryMaster", back_populates="category", cascade="all, delete-orphan")


class SubCategoryMaster(Base):
    __tablename__ = "sub_category_master"

    id                = Column(BigInteger, primary_key=True, autoincrement=True)
    sub_category_code = Column(String(50), unique=True, nullable=False)
    sub_category_name = Column(String(255), nullable=False)
    category_id       = Column(BigInteger, ForeignKey("category_master.id", ondelete="RESTRICT"), nullable=False)
    description       = Column(Text)
    is_active         = Column(Boolean, default=True)
    created_at        = Column(TIMESTAMP, default=datetime.utcnow)
    updated_at        = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)

    category = relationship("CategoryMaster", back_populates="sub_categories")
