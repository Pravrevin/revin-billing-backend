from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models.sales_master import SalesItem, SalesMaster
from app.models.stock_master import StockLedger, StockMaster
from app.schemas.sales import (
    SalesItemResponse,
    SalesMasterCreate,
    SalesMasterResponse,
    SalesMasterUpdate,
)

router = APIRouter(prefix="/sales", tags=["Sales"])


# ── Stock helpers ────────────────────────────────────────────────────────────────

def _deduct_stock_and_ledger(db: Session, sale_id: int, item_data):
    """
    Reduce stock_master for one sold line and write a ledger OUT entry.
    Sales must come from inventory: the (item_id, batch_no) batch must exist
    with enough quantity, otherwise the whole sale is rejected.
    """
    qty = item_data.quantity or Decimal("0")
    if qty <= 0:
        return

    if not item_data.batch_no:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Batch number is required to sell item {item_data.item_id} from stock.",
        )

    stock = (
        db.query(StockMaster)
        .filter(
            StockMaster.item_id  == item_data.item_id,
            StockMaster.batch_no == item_data.batch_no,
        )
        .first()
    )
    if not stock:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Batch '{item_data.batch_no}' of item {item_data.item_id} is not in stock.",
        )

    available = stock.quantity or Decimal("0")
    if qty > available:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Insufficient stock for batch '{item_data.batch_no}': "
                   f"requested {qty}, available {available}.",
        )

    stock.quantity = available - qty

    db.add(StockLedger(
        item_id        = item_data.item_id,
        batch_no       = item_data.batch_no,
        movement_type  = "OUT",
        quantity       = qty,
        free_quantity  = Decimal("0"),
        reference_type = "sale",
        reference_id   = sale_id,
        mrp            = item_data.mrp,
    ))


def _restore_stock_and_ledger(db: Session, sale: SalesMaster):
    """Put sold quantities back when a sale is deleted, and write reversing ledger rows."""
    for item in sale.items:
        qty = item.quantity or Decimal("0")
        if qty <= 0 or not item.batch_no:
            continue
        stock = (
            db.query(StockMaster)
            .filter(StockMaster.item_id == item.item_id, StockMaster.batch_no == item.batch_no)
            .first()
        )
        if stock:
            stock.quantity = (stock.quantity or Decimal("0")) + qty
        db.add(StockLedger(
            item_id        = item.item_id,
            batch_no       = item.batch_no,
            movement_type  = "IN",
            quantity       = qty,
            free_quantity  = Decimal("0"),
            reference_type = "sale-reversal",
            reference_id   = sale.id,
            mrp            = item.mrp,
        ))


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
        _deduct_stock_and_ledger(db, sale.id, item_data)

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
    sale = (
        db.query(SalesMaster)
        .options(joinedload(SalesMaster.items))
        .filter(SalesMaster.id == sale_id)
        .first()
    )
    if not sale:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sale not found.")
    _restore_stock_and_ledger(db, sale)   # return goods to inventory
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
