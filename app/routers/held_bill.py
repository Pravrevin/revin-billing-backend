"""
Held Bills router (/api/v1/held-bills)
──────────────────────────────────────
Park an in-progress sales bill and resume it later. A held bill is a DRAFT —
no stock is reserved or deducted. When the cashier resumes it and completes the
sale (POST /sales/), stock is deducted there and the held bill is deleted by
the client.

  POST   /held-bills/        Park a draft bill
  GET    /held-bills/        List parked bills (newest first)
  GET    /held-bills/{id}    One parked bill (full payload to resume)
  DELETE /held-bills/{id}    Discard a parked bill
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth.deps import get_tenant_db as get_db
from app.models.held_bill import HeldBill
from app.schemas.held_bill import HeldBillCreate, HeldBillResponse

router = APIRouter(prefix="/held-bills", tags=["Held Bills"])


@router.post("/", response_model=HeldBillResponse, status_code=status.HTTP_201_CREATED)
def create_held_bill(payload: HeldBillCreate, db: Session = Depends(get_db)):
    bill = HeldBill(**payload.model_dump())
    db.add(bill)
    db.flush()                       # need id for hold_no
    bill.hold_no = f"HOLD-{bill.id:05d}"
    db.commit()
    db.refresh(bill)
    return bill


@router.get("/", response_model=List[HeldBillResponse])
def list_held_bills(
    skip:  int = Query(0,   ge=0),
    limit: int = Query(100, ge=1, le=500),
    db:    Session = Depends(get_db),
):
    return (
        db.query(HeldBill)
        .order_by(HeldBill.created_at.desc(), HeldBill.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


@router.get("/{held_id}", response_model=HeldBillResponse)
def get_held_bill(held_id: int, db: Session = Depends(get_db)):
    bill = db.query(HeldBill).filter(HeldBill.id == held_id).first()
    if not bill:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Held bill not found.")
    return bill


@router.delete("/{held_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_held_bill(held_id: int, db: Session = Depends(get_db)):
    bill = db.query(HeldBill).filter(HeldBill.id == held_id).first()
    if not bill:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Held bill not found.")
    db.delete(bill)
    db.commit()
