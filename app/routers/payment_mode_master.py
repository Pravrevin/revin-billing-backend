from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth.deps import get_tenant_db as get_db
from app.models.payment_mode_master import PaymentModeMaster
from app.schemas.payment_mode_master import (
    PaymentModeMasterCreate,
    PaymentModeMasterResponse,
    PaymentModeMasterUpdate,
)

router = APIRouter(prefix="/payment-modes", tags=["Payment Mode Master"])


@router.get("/", response_model=List[PaymentModeMasterResponse])
def list_payment_modes(
    is_active: Optional[bool] = Query(None),
    db:        Session        = Depends(get_db),
):
    query = db.query(PaymentModeMaster)
    if is_active is not None:
        query = query.filter(PaymentModeMaster.is_active == is_active)
    return query.order_by(PaymentModeMaster.id).all()


@router.post("/", response_model=PaymentModeMasterResponse, status_code=status.HTTP_201_CREATED)
def create_payment_mode(payload: PaymentModeMasterCreate, db: Session = Depends(get_db)):
    existing = db.query(PaymentModeMaster).filter(
        PaymentModeMaster.mode_name == payload.mode_name
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Payment mode '{payload.mode_name}' already exists.",
        )
    mode = PaymentModeMaster(**payload.model_dump())
    db.add(mode)
    db.commit()
    db.refresh(mode)
    return mode


@router.get("/{mode_id}", response_model=PaymentModeMasterResponse)
def get_payment_mode(mode_id: int, db: Session = Depends(get_db)):
    mode = db.query(PaymentModeMaster).filter(PaymentModeMaster.id == mode_id).first()
    if not mode:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment mode not found.")
    return mode


@router.patch("/{mode_id}", response_model=PaymentModeMasterResponse)
def update_payment_mode(mode_id: int, payload: PaymentModeMasterUpdate, db: Session = Depends(get_db)):
    mode = db.query(PaymentModeMaster).filter(PaymentModeMaster.id == mode_id).first()
    if not mode:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment mode not found.")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(mode, field, value)
    db.commit()
    db.refresh(mode)
    return mode


@router.delete("/{mode_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_payment_mode(mode_id: int, db: Session = Depends(get_db)):
    mode = db.query(PaymentModeMaster).filter(PaymentModeMaster.id == mode_id).first()
    if not mode:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment mode not found.")
    db.delete(mode)
    db.commit()
