from sqlalchemy import BigInteger, Column, create_engine, event
from sqlalchemy.orm import (
    DeclarativeBase,
    Session,
    sessionmaker,
    with_loader_criteria,
)

from app.config import settings

engine = create_engine(settings.database_url, echo=False)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


class TenantBase(Base):
    """
    Abstract base for every per-pharmacy (tenant-scoped) table.

    Subclasses automatically get a ``pharmacy_id`` column. Reads are filtered
    and writes are stamped with the session's active pharmacy via the event
    listeners below — routers never have to add the filter by hand.
    """

    __abstract__ = True

    pharmacy_id = Column(BigInteger, nullable=False, index=True)


# Session.info key holding the active pharmacy id for the current request.
PHARMACY_KEY = "pharmacy_id"


def get_db():
    """Unscoped session (no tenant filtering). Used by auth/admin code only."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@event.listens_for(Session, "do_orm_execute")
def _apply_tenant_filter(execute_state):
    """Auto-scope every SELECT on a TenantBase model to the session's pharmacy."""
    if not execute_state.is_select:
        return
    if execute_state.is_column_load or execute_state.is_relationship_load:
        return
    pid = execute_state.session.info.get(PHARMACY_KEY)
    if pid is None:
        return
    execute_state.statement = execute_state.statement.options(
        with_loader_criteria(
            TenantBase,
            lambda cls: cls.pharmacy_id == pid,
            include_aliases=True,
        )
    )


@event.listens_for(Session, "before_flush")
def _stamp_tenant_on_insert(session, flush_context, instances):
    """Stamp pharmacy_id on new tenant rows that don't already have one."""
    pid = session.info.get(PHARMACY_KEY)
    if pid is None:
        return
    for obj in session.new:
        if isinstance(obj, TenantBase) and getattr(obj, "pharmacy_id", None) is None:
            obj.pharmacy_id = pid
