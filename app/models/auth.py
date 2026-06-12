from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    ForeignKey,
    Integer,
    String,
    TIMESTAMP,
    UniqueConstraint,
)

from app.database import Base


class Pharmacy(Base):
    """A tenant — one pharmacy / clinic the admin onboards."""

    __tablename__ = "pharmacy"

    id         = Column(BigInteger, primary_key=True, autoincrement=True)
    name       = Column(String(255), nullable=False)
    code       = Column(String(50), unique=True)
    address    = Column(String(500))
    phone      = Column(String(30))
    is_active  = Column(Boolean, default=True, nullable=False)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)


class AppUser(Base):
    """
    A login user. ``role='superadmin'`` users have ``pharmacy_id=NULL`` and
    manage all tenants; ``role='pharmacy_user'`` users belong to one pharmacy.
    """

    __tablename__ = "app_user"

    id            = Column(BigInteger, primary_key=True, autoincrement=True)
    pharmacy_id   = Column(BigInteger, ForeignKey("pharmacy.id", ondelete="CASCADE"))
    username      = Column(String(150), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    full_name     = Column(String(255))
    role          = Column(String(30), nullable=False, default="pharmacy_user")
    is_active     = Column(Boolean, default=True, nullable=False)
    created_at    = Column(TIMESTAMP, default=datetime.utcnow)


class UserPermission(Base):
    """
    One granted menu (or menu+sub-menu) for a user. ``sub_id IS NULL`` means the
    whole menu is granted. Menu/sub ids mirror the frontend catalog in menus.ts.
    """

    __tablename__ = "user_permission"
    __table_args__ = (
        UniqueConstraint("user_id", "menu_id", "sub_id", name="uq_user_menu_sub"),
    )

    id      = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False)
    menu_id = Column(Integer, nullable=False)
    sub_id  = Column(Integer)  # nullable -> whole menu granted


class MenuAccessLog(Base):
    """Records each menu/sub-menu open, powering admin usage insights."""

    __tablename__ = "menu_access_log"

    id          = Column(BigInteger, primary_key=True, autoincrement=True)
    pharmacy_id = Column(BigInteger, index=True)
    user_id     = Column(BigInteger, index=True)
    menu_id     = Column(Integer, nullable=False)
    sub_id      = Column(Integer)
    accessed_at = Column(TIMESTAMP, default=datetime.utcnow, index=True)
