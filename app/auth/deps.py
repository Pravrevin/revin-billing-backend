from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth.security import decode_token
from app.database import PHARMACY_KEY, SessionLocal
from app.models.auth import UserPermission

SUPERADMIN = "superadmin"

_bearer = HTTPBearer(auto_error=False)


@dataclass
class CurrentUser:
    user_id: int
    pharmacy_id: Optional[int]
    role: str
    username: str

    @property
    def is_superadmin(self) -> bool:
        return self.role == SUPERADMIN


def get_current_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> CurrentUser:
    if creds is None or not creds.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_token(creds.credentials)
    if not payload or "user_id" not in payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return CurrentUser(
        user_id=int(payload["user_id"]),
        pharmacy_id=payload.get("pharmacy_id"),
        role=payload.get("role", "pharmacy_user"),
        username=payload.get("username", ""),
    )


def get_tenant_db(user: CurrentUser = Depends(get_current_user)):
    """
    Tenant-scoped DB session. For pharmacy users the session is stamped with
    their pharmacy_id so all reads/writes are auto-isolated. Superadmins get an
    unscoped session (they manage all tenants).
    """
    db = SessionLocal()
    if not user.is_superadmin:
        if user.pharmacy_id is None:
            db.close()
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User is not assigned to a pharmacy.",
            )
        db.info[PHARMACY_KEY] = user.pharmacy_id
    try:
        yield db
    finally:
        db.close()


def require_superadmin(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if not user.is_superadmin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator access required.",
        )
    return user


def user_has_menu(user_id: int, menu_id: int) -> bool:
    db = SessionLocal()
    try:
        return (
            db.query(UserPermission.id)
            .filter(UserPermission.user_id == user_id, UserPermission.menu_id == menu_id)
            .first()
            is not None
        )
    finally:
        db.close()


def require_menu(menu_id: int):
    """Dependency factory: 403 unless the user is granted the given menu."""

    def _checker(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.is_superadmin:
            return user
        if not user_has_menu(user.user_id, menu_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this module.",
            )
        return user

    return _checker
