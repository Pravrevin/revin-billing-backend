"""
Auth router (/api/v1/auth)
──────────────────────────
  POST /auth/login        { username, password } → JWT + user + permissions
  GET  /auth/me                                  → current user + permissions
  POST /auth/log-access   { menu_id, sub_id }    → record a menu open (insights)

Uses an UNSCOPED session (get_db) — the auth tables are not tenant-filtered.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.deps import CurrentUser, get_current_user
from app.auth.security import create_access_token, verify_password
from app.database import get_db
from app.models.auth import AppUser, MenuAccessLog, Pharmacy, UserPermission
from app.schemas.auth import (
    LogAccessRequest,
    LoginRequest,
    LoginResponse,
    MeResponse,
    PermissionItem,
    PharmacyBrief,
    UserInfo,
)

router = APIRouter(prefix="/auth", tags=["Auth"])


def _permissions_for(db: Session, user_id: int) -> list[PermissionItem]:
    rows = db.query(UserPermission).filter(UserPermission.user_id == user_id).all()
    return [PermissionItem(menu_id=r.menu_id, sub_id=r.sub_id) for r in rows]


def _user_info(db: Session, user: AppUser) -> UserInfo:
    pharmacy = None
    if user.pharmacy_id:
        p = db.query(Pharmacy).filter(Pharmacy.id == user.pharmacy_id).first()
        if p:
            pharmacy = PharmacyBrief(id=p.id, name=p.name, code=p.code)
    return UserInfo(
        id=user.id,
        username=user.username,
        full_name=user.full_name,
        role=user.role,
        pharmacy=pharmacy,
    )


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    username = (payload.username or "").strip()
    user = db.query(AppUser).filter(AppUser.username == username).first()
    if not user or not verify_password(payload.password or "", user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account is disabled. Contact your administrator.",
        )

    # A pharmacy user whose pharmacy is disabled cannot log in.
    if user.pharmacy_id:
        pharmacy = db.query(Pharmacy).filter(Pharmacy.id == user.pharmacy_id).first()
        if pharmacy and not pharmacy.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This pharmacy is currently disabled.",
            )

    token = create_access_token(
        {
            "user_id": user.id,
            "pharmacy_id": user.pharmacy_id,
            "role": user.role,
            "username": user.username,
        }
    )
    return LoginResponse(
        access_token=token,
        user=_user_info(db, user),
        permissions=_permissions_for(db, user.id),
    )


@router.get("/me", response_model=MeResponse)
def me(current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    user = db.query(AppUser).filter(AppUser.id == current.user_id).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found.")
    return MeResponse(
        user=_user_info(db, user),
        permissions=_permissions_for(db, user.id),
    )


@router.post("/log-access", status_code=status.HTTP_204_NO_CONTENT)
def log_access(
    payload: LogAccessRequest,
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Superadmin navigation is not tracked as pharmacy usage.
    if current.is_superadmin:
        return
    db.add(
        MenuAccessLog(
            pharmacy_id=current.pharmacy_id,
            user_id=current.user_id,
            menu_id=payload.menu_id,
            sub_id=payload.sub_id,
        )
    )
    db.commit()
