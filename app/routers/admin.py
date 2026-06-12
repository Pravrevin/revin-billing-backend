"""
Admin router (/api/v1/admin) — superadmin only
───────────────────────────────────────────────
Manage tenants (pharmacies), their login users, per-user menu permissions, and
view cross-pharmacy + menu-usage insights.

Uses an UNSCOPED session (get_db): the superadmin is not tied to any pharmacy,
so tenant filtering is intentionally off here. Aggregates group by pharmacy_id.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth.deps import require_superadmin
from app.auth.security import hash_password
from app.database import get_db
from app.models.auth import AppUser, MenuAccessLog, Pharmacy, UserPermission
from app.models.expense import ExpenseMaster
from app.models.item_master import ItemMaster
from app.models.purchase_master import PurchaseMaster
from app.models.purchase_payment import PartyCreditConfig
from app.models.sales_master import SalesMaster
from app.schemas.auth import (
    PermissionItem,
    PermissionsUpdate,
    PharmacyCreate,
    PharmacyResponse,
    PharmacyUpdate,
    UserCreate,
    UserResponse,
    UserUpdate,
)

router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
    dependencies=[Depends(require_superadmin)],
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _pharmacy_out(db: Session, p: Pharmacy) -> PharmacyResponse:
    count = db.query(func.count(AppUser.id)).filter(AppUser.pharmacy_id == p.id).scalar() or 0
    return PharmacyResponse(
        id=p.id, name=p.name, code=p.code, address=p.address,
        phone=p.phone, is_active=p.is_active, user_count=count,
    )


def _get_pharmacy(db: Session, pharmacy_id: int) -> Pharmacy:
    p = db.query(Pharmacy).filter(Pharmacy.id == pharmacy_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Pharmacy not found.")
    return p


def _get_user(db: Session, user_id: int) -> AppUser:
    u = db.query(AppUser).filter(AppUser.id == user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="User not found.")
    return u


def _replace_permissions(db: Session, user_id: int, perms: List[PermissionItem]) -> None:
    db.query(UserPermission).filter(UserPermission.user_id == user_id).delete()
    seen = set()
    for p in perms:
        key = (p.menu_id, p.sub_id)
        if key in seen:
            continue
        seen.add(key)
        db.add(UserPermission(user_id=user_id, menu_id=p.menu_id, sub_id=p.sub_id))


# ── pharmacies ──────────────────────────────────────────────────────────────────

@router.post("/pharmacies", response_model=PharmacyResponse, status_code=201)
def create_pharmacy(payload: PharmacyCreate, db: Session = Depends(get_db)):
    if payload.code:
        exists = db.query(Pharmacy).filter(Pharmacy.code == payload.code).first()
        if exists:
            raise HTTPException(status_code=400, detail="Pharmacy code already in use.")
    p = Pharmacy(
        name=payload.name, code=payload.code,
        address=payload.address, phone=payload.phone, is_active=True,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    # Seed this pharmacy's global default credit terms (party_id NULL = default).
    db.add(PartyCreditConfig(pharmacy_id=p.id, party_id=None, credit_days=30, overdue_grace_days=0))
    db.commit()
    return _pharmacy_out(db, p)


@router.get("/pharmacies", response_model=List[PharmacyResponse])
def list_pharmacies(db: Session = Depends(get_db)):
    return [_pharmacy_out(db, p) for p in db.query(Pharmacy).order_by(Pharmacy.id).all()]


@router.get("/pharmacies/{pharmacy_id}", response_model=PharmacyResponse)
def get_pharmacy(pharmacy_id: int, db: Session = Depends(get_db)):
    return _pharmacy_out(db, _get_pharmacy(db, pharmacy_id))


@router.patch("/pharmacies/{pharmacy_id}", response_model=PharmacyResponse)
def update_pharmacy(pharmacy_id: int, payload: PharmacyUpdate, db: Session = Depends(get_db)):
    p = _get_pharmacy(db, pharmacy_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(p, field, value)
    db.commit()
    db.refresh(p)
    return _pharmacy_out(db, p)


# ── users ─────────────────────────────────────────────────────────────────────

@router.get("/users", response_model=List[UserResponse])
def list_users(
    pharmacy_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(AppUser).filter(AppUser.role != "superadmin")
    if pharmacy_id is not None:
        q = q.filter(AppUser.pharmacy_id == pharmacy_id)
    return q.order_by(AppUser.id).all()


@router.get("/pharmacies/{pharmacy_id}/users", response_model=List[UserResponse])
def list_pharmacy_users(pharmacy_id: int, db: Session = Depends(get_db)):
    _get_pharmacy(db, pharmacy_id)
    return (
        db.query(AppUser)
        .filter(AppUser.pharmacy_id == pharmacy_id)
        .order_by(AppUser.id)
        .all()
    )


@router.post("/pharmacies/{pharmacy_id}/users", response_model=UserResponse, status_code=201)
def create_user(pharmacy_id: int, payload: UserCreate, db: Session = Depends(get_db)):
    _get_pharmacy(db, pharmacy_id)
    username = (payload.username or "").strip()
    if not username or not payload.password:
        raise HTTPException(status_code=400, detail="Username and password are required.")
    if db.query(AppUser).filter(AppUser.username == username).first():
        raise HTTPException(status_code=400, detail="Username already taken.")
    user = AppUser(
        pharmacy_id=pharmacy_id,
        username=username,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
        role="pharmacy_user",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    if payload.permissions:
        _replace_permissions(db, user.id, payload.permissions)
        db.commit()
    return user


@router.patch("/users/{user_id}", response_model=UserResponse)
def update_user(user_id: int, payload: UserUpdate, db: Session = Depends(get_db)):
    user = _get_user(db, user_id)
    if user.role == "superadmin":
        raise HTTPException(status_code=400, detail="Cannot modify the superadmin here.")
    data = payload.model_dump(exclude_unset=True)
    if "password" in data and data["password"]:
        user.password_hash = hash_password(data.pop("password"))
    else:
        data.pop("password", None)
    for field, value in data.items():
        setattr(user, field, value)
    db.commit()
    db.refresh(user)
    return user


# ── permissions ──────────────────────────────────────────────────────────────

@router.get("/users/{user_id}/permissions", response_model=List[PermissionItem])
def get_permissions(user_id: int, db: Session = Depends(get_db)):
    _get_user(db, user_id)
    rows = db.query(UserPermission).filter(UserPermission.user_id == user_id).all()
    return [PermissionItem(menu_id=r.menu_id, sub_id=r.sub_id) for r in rows]


@router.put("/users/{user_id}/permissions", response_model=List[PermissionItem])
def set_permissions(user_id: int, payload: PermissionsUpdate, db: Session = Depends(get_db)):
    _get_user(db, user_id)
    _replace_permissions(db, user_id, payload.permissions)
    db.commit()
    rows = db.query(UserPermission).filter(UserPermission.user_id == user_id).all()
    return [PermissionItem(menu_id=r.menu_id, sub_id=r.sub_id) for r in rows]


# ── insights ──────────────────────────────────────────────────────────────────

def _pharmacy_metrics(db: Session, pharmacy_id: int) -> dict:
    sales_total = (
        db.query(func.coalesce(func.sum(SalesMaster.net_amount), 0))
        .filter(SalesMaster.pharmacy_id == pharmacy_id).scalar() or 0
    )
    sales_count = (
        db.query(func.count(SalesMaster.id))
        .filter(SalesMaster.pharmacy_id == pharmacy_id).scalar() or 0
    )
    purchase_total = (
        db.query(func.coalesce(func.sum(PurchaseMaster.net_amount), 0))
        .filter(PurchaseMaster.pharmacy_id == pharmacy_id).scalar() or 0
    )
    expense_total = (
        db.query(func.coalesce(func.sum(ExpenseMaster.amount), 0))
        .filter(ExpenseMaster.pharmacy_id == pharmacy_id).scalar() or 0
    )
    item_count = (
        db.query(func.count(ItemMaster.id))
        .filter(ItemMaster.pharmacy_id == pharmacy_id).scalar() or 0
    )
    user_count = (
        db.query(func.count(AppUser.id))
        .filter(AppUser.pharmacy_id == pharmacy_id).scalar() or 0
    )
    return {
        "sales_total": round(float(sales_total), 2),
        "sales_count": int(sales_count),
        "purchase_total": round(float(purchase_total), 2),
        "expense_total": round(float(expense_total), 2),
        "item_count": int(item_count),
        "user_count": int(user_count),
    }


def _menu_usage(db: Session, pharmacy_id: Optional[int] = None, limit: int = 10) -> list[dict]:
    q = db.query(
        MenuAccessLog.menu_id,
        MenuAccessLog.sub_id,
        func.count(MenuAccessLog.id).label("hits"),
    )
    if pharmacy_id is not None:
        q = q.filter(MenuAccessLog.pharmacy_id == pharmacy_id)
    rows = (
        q.group_by(MenuAccessLog.menu_id, MenuAccessLog.sub_id)
        .order_by(func.count(MenuAccessLog.id).desc())
        .limit(limit)
        .all()
    )
    return [{"menu_id": m, "sub_id": s, "hits": int(h)} for (m, s, h) in rows]


@router.get("/insights")
def global_insights(db: Session = Depends(get_db)):
    pharmacies = db.query(Pharmacy).order_by(Pharmacy.id).all()
    per_pharmacy = []
    totals = {"sales_total": 0.0, "purchase_total": 0.0, "sales_count": 0}
    for p in pharmacies:
        m = _pharmacy_metrics(db, p.id)
        per_pharmacy.append({"id": p.id, "name": p.name, "is_active": p.is_active, **m})
        totals["sales_total"] += m["sales_total"]
        totals["purchase_total"] += m["purchase_total"]
        totals["sales_count"] += m["sales_count"]
    return {
        "pharmacy_count": len(pharmacies),
        "active_pharmacy_count": sum(1 for p in pharmacies if p.is_active),
        "totals": {k: round(v, 2) if isinstance(v, float) else v for k, v in totals.items()},
        "per_pharmacy": per_pharmacy,
        "top_menus": _menu_usage(db, None),
    }


@router.get("/pharmacies/{pharmacy_id}/insights")
def pharmacy_insights(pharmacy_id: int, db: Session = Depends(get_db)):
    p = _get_pharmacy(db, pharmacy_id)
    return {
        "id": p.id,
        "name": p.name,
        "is_active": p.is_active,
        "metrics": _pharmacy_metrics(db, p.id),
        "top_menus": _menu_usage(db, p.id),
    }
