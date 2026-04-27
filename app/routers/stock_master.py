from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models.item_master import ItemMaster
from app.models.stock_master import StockLedger, StockMaster
from app.schemas.stock_master import StockLedgerResponse, StockMasterCreate, StockMasterResponse, StockMasterUpdate

router = APIRouter(prefix="/stock-master", tags=["Stock Master"])


@router.post("/", response_model=StockMasterResponse, status_code=status.HTTP_201_CREATED)
def create_stock(payload: StockMasterCreate, db: Session = Depends(get_db)):
    item = db.query(ItemMaster).filter(ItemMaster.id == payload.item_id).first()
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Item with id {payload.item_id} not found.",
        )
    stock = StockMaster(**payload.model_dump())
    db.add(stock)
    db.commit()
    db.refresh(stock)
    return stock


@router.get("/", response_model=List[StockMasterResponse])
def list_stocks(
    skip:         int           = Query(0, ge=0),
    limit:        int           = Query(50, ge=1, le=500),
    item_id:      Optional[int] = Query(None),
    warehouse_id: Optional[int] = Query(None),
    batch_no:     Optional[str] = Query(None),
    db:           Session       = Depends(get_db),
):
    query = db.query(StockMaster).options(joinedload(StockMaster.item))
    if item_id:
        query = query.filter(StockMaster.item_id == item_id)
    if warehouse_id:
        query = query.filter(StockMaster.warehouse_id == warehouse_id)
    if batch_no:
        query = query.filter(StockMaster.batch_no.ilike(f"%{batch_no}%"))
    return query.offset(skip).limit(limit).all()


@router.get("/{stock_id}", response_model=StockMasterResponse)
def get_stock(stock_id: int, db: Session = Depends(get_db)):
    stock = db.query(StockMaster).options(joinedload(StockMaster.item)).filter(StockMaster.id == stock_id).first()
    if not stock:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stock entry not found.")
    return stock


@router.patch("/{stock_id}", response_model=StockMasterResponse)
def update_stock(stock_id: int, payload: StockMasterUpdate, db: Session = Depends(get_db)):
    stock = db.query(StockMaster).filter(StockMaster.id == stock_id).first()
    if not stock:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stock entry not found.")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(stock, field, value)
    db.commit()
    db.refresh(stock)
    return stock


@router.delete("/{stock_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_stock(stock_id: int, db: Session = Depends(get_db)):
    stock = db.query(StockMaster).filter(StockMaster.id == stock_id).first()
    if not stock:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stock entry not found.")
    db.delete(stock)
    db.commit()


# ── Stock Ledger ───────────────────────────────────────────────────────────────

@router.get("/ledger", response_model=List[StockLedgerResponse])
def list_stock_ledger(
    skip:           int            = Query(0, ge=0),
    limit:          int            = Query(100, ge=1, le=1000),
    item_id:        Optional[int]  = Query(None),
    batch_no:       Optional[str]  = Query(None),
    movement_type:  Optional[str]  = Query(None, description="IN or OUT"),
    reference_type: Optional[str]  = Query(None, description="purchase or sale"),
    purchase_id:    Optional[int]  = Query(None, description="Filter by purchase_master id"),
    db:             Session        = Depends(get_db),
):
    """
    Stock movement ledger.  Use `purchase_id` to see all stock changes
    that were triggered by a specific purchase.
    """
    query = db.query(StockLedger).options(joinedload(StockLedger.item))
    if item_id:
        query = query.filter(StockLedger.item_id == item_id)
    if batch_no:
        query = query.filter(StockLedger.batch_no.ilike(f"%{batch_no}%"))
    if movement_type:
        query = query.filter(StockLedger.movement_type == movement_type.upper())
    if reference_type:
        query = query.filter(StockLedger.reference_type == reference_type)
    if purchase_id:
        query = query.filter(
            StockLedger.reference_type == "purchase",
            StockLedger.reference_id   == purchase_id,
        )
    return query.order_by(StockLedger.id.desc()).offset(skip).limit(limit).all()
