from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models.sales_master import SalesItem, SalesMaster
from app.schemas.sales import (
    SalesItemResponse,
    SalesMasterCreate,
    SalesMasterResponse,
    SalesMasterUpdate,
)

router = APIRouter(prefix="/sales", tags=["Sales"])


# ── Sales Master ───────────────────────────────────────────────────────────────

@router.post("/", response_model=SalesMasterResponse, status_code=status.HTTP_201_CREATED)
def create_sale(payload: SalesMasterCreate, db: Session = Depends(get_db)):
    data = payload.model_dump(exclude={"items"})
    sale = SalesMaster(**data)
    db.add(sale)
    db.flush()  # get sale.id before inserting items

    for item_data in payload.items:
        item = SalesItem(sales_id=sale.id, **item_data.model_dump())
        db.add(item)

    db.commit()
    db.refresh(sale)
    return sale


@router.get("/", response_model=List[SalesMasterResponse])
def list_sales(
    skip:           int            = Query(0, ge=0),
    limit:          int            = Query(50, ge=1, le=500),
    customer_id:    Optional[int]  = Query(None),
    payment_status: Optional[str]  = Query(None),
    db:             Session        = Depends(get_db),
):
    query = db.query(SalesMaster).options(
        joinedload(SalesMaster.items),
        joinedload(SalesMaster.payment_mode),
    )
    if customer_id:
        query = query.filter(SalesMaster.customer_id == customer_id)
    if payment_status:
        query = query.filter(SalesMaster.payment_status == payment_status)
    return query.offset(skip).limit(limit).all()


@router.get("/{sale_id}", response_model=SalesMasterResponse)
def get_sale(sale_id: int, db: Session = Depends(get_db)):
    sale = (
        db.query(SalesMaster)
        .options(
            joinedload(SalesMaster.items),
            joinedload(SalesMaster.payment_mode),
        )
        .filter(SalesMaster.id == sale_id)
        .first()
    )
    if not sale:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sale not found.")
    return sale


@router.patch("/{sale_id}", response_model=SalesMasterResponse)
def update_sale(sale_id: int, payload: SalesMasterUpdate, db: Session = Depends(get_db)):
    sale = db.query(SalesMaster).filter(SalesMaster.id == sale_id).first()
    if not sale:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sale not found.")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(sale, field, value)
    db.commit()
    db.refresh(sale)
    return sale


@router.delete("/{sale_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sale(sale_id: int, db: Session = Depends(get_db)):
    sale = db.query(SalesMaster).filter(SalesMaster.id == sale_id).first()
    if not sale:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sale not found.")
    db.delete(sale)
    db.commit()


# ── Sales Items (sub-resource) ─────────────────────────────────────────────────

@router.get("/{sale_id}/items", response_model=List[SalesItemResponse])
def list_sale_items(sale_id: int, db: Session = Depends(get_db)):
    sale = db.query(SalesMaster).filter(SalesMaster.id == sale_id).first()
    if not sale:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sale not found.")
    return sale.items


@router.delete("/{sale_id}/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sale_item(sale_id: int, item_id: int, db: Session = Depends(get_db)):
    item = (
        db.query(SalesItem)
        .filter(SalesItem.id == item_id, SalesItem.sales_id == sale_id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sales item not found.")
    db.delete(item)
    db.commit()
