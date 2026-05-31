"""
Sales Return / Refund router
────────────────────────────
  GET    /sales/{sale_id}/returnable     What can still be returned per sold line
  GET    /sales/{sale_id}/returns        Returns recorded against a sale
  POST   /sales-returns/                 Record a return (restores stock + ledger)
  GET    /sales-returns/                 List returns (filters)
  GET    /sales-returns/{id}             One return
  DELETE /sales-returns/{id}             Reverse a return (re-deducts stock)

Returning goods ADDS them back to stock_master for the (item, batch) and writes a
stock_ledger IN row (reference_type='sale-return'). Deleting a return reverses both.
If a refund amount + mode is given and the sale had a customer, a matching money-OUT
payment is recorded so the refund shows up in the Cash / Bank / Day book.
"""
from datetime import date
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models.item_master import ItemMaster
from app.models.payment_mode_master import PaymentModeMaster
from app.models.purchase_payment import PaymentMaster
from app.models.sales_master import SalesItem, SalesMaster
from app.models.sales_return import SalesReturnItem, SalesReturnMaster
from app.models.stock_master import StockLedger, StockMaster
from app.schemas.sales_return import (
    ReturnableLine,
    ReturnableResponse,
    SalesReturnCreate,
    SalesReturnItemResponse,
    SalesReturnResponse,
)

router = APIRouter(tags=["Sales Returns"])

ZERO = Decimal("0")


# ── helpers ──────────────────────────────────────────────────────────────────

def _returned_by_sales_item(db: Session, sales_id: int) -> dict:
    """sales_item_id → already-returned qty, for one sale."""
    rows = (
        db.query(SalesReturnItem.sales_item_id, func.coalesce(func.sum(SalesReturnItem.quantity), 0))
        .join(SalesReturnMaster, SalesReturnItem.return_id == SalesReturnMaster.id)
        .filter(SalesReturnMaster.sales_id == sales_id)
        .group_by(SalesReturnItem.sales_item_id)
        .all()
    )
    return {r[0]: (r[1] or ZERO) for r in rows}


def _restore_stock(db: Session, ret_id: int, line: SalesReturnItem):
    """Add a returned line back to inventory + write an IN ledger row."""
    qty = line.quantity or ZERO
    if qty <= 0 or not line.batch_no:
        return
    stock = (
        db.query(StockMaster)
        .filter(StockMaster.item_id == line.item_id, StockMaster.batch_no == line.batch_no)
        .first()
    )
    if stock:
        stock.quantity = (stock.quantity or ZERO) + qty
    else:
        # Batch was fully sold out / pruned — recreate it from the returned line.
        db.add(StockMaster(
            item_id       = line.item_id,
            batch_no      = line.batch_no,
            quantity      = qty,
            free_quantity = ZERO,
            mrp           = line.mrp,
            sale_rate     = line.sale_rate,
            expiry_date   = line.expiry_date,
        ))
    db.add(StockLedger(
        item_id        = line.item_id,
        batch_no       = line.batch_no,
        movement_type  = "IN",
        quantity       = qty,
        free_quantity  = ZERO,
        reference_type = "sale-return",
        reference_id   = ret_id,
        mrp            = line.mrp,
    ))


def _reverse_stock(db: Session, ret: SalesReturnMaster):
    """Undo a return: pull the goods back out of stock + write OUT ledger rows."""
    for line in ret.items:
        qty = line.quantity or ZERO
        if qty <= 0 or not line.batch_no:
            continue
        stock = (
            db.query(StockMaster)
            .filter(StockMaster.item_id == line.item_id, StockMaster.batch_no == line.batch_no)
            .first()
        )
        if stock:
            stock.quantity = (stock.quantity or ZERO) - qty
        db.add(StockLedger(
            item_id        = line.item_id,
            batch_no       = line.batch_no,
            movement_type  = "OUT",
            quantity       = qty,
            free_quantity  = ZERO,
            reference_type = "sale-return-reversal",
            reference_id   = ret.id,
            mrp            = line.mrp,
        ))


def _to_response(db: Session, ret: SalesReturnMaster) -> SalesReturnResponse:
    names = dict(
        db.query(ItemMaster.id, ItemMaster.item_name)
        .filter(ItemMaster.id.in_([li.item_id for li in ret.items] or [0]))
        .all()
    )
    invoice_no = None
    if ret.sales_id:
        sale = db.query(SalesMaster.invoice_no).filter(SalesMaster.id == ret.sales_id).first()
        invoice_no = sale[0] if sale else None
    return SalesReturnResponse(
        id               = ret.id,
        return_no        = ret.return_no,
        return_date      = ret.return_date,
        sales_id         = ret.sales_id,
        invoice_no       = invoice_no,
        customer_id      = ret.customer_id,
        customer_name    = ret.customer.party_name if ret.customer else None,
        total_amount     = ret.total_amount,
        tax_amount       = ret.tax_amount,
        refund_amount    = ret.refund_amount,
        refund_mode_id   = ret.refund_mode_id,
        refund_mode_name = ret.refund_mode.mode_name if ret.refund_mode else None,
        refund_status    = ret.refund_status,
        reason           = ret.reason,
        notes            = ret.notes,
        created_at       = ret.created_at,
        updated_at       = ret.updated_at,
        extra_data       = ret.extra_data,
        items            = [
            SalesReturnItemResponse(
                id            = li.id,
                return_id     = li.return_id,
                sales_item_id = li.sales_item_id,
                item_id       = li.item_id,
                item_name     = names.get(li.item_id),
                batch_no      = li.batch_no,
                quantity      = li.quantity,
                mrp           = li.mrp,
                sale_rate     = li.sale_rate,
                gst_percent   = li.gst_percent,
                tax_amount    = li.tax_amount,
                total         = li.total,
                expiry_date   = li.expiry_date,
            )
            for li in ret.items
        ],
    )


def _load(db: Session, ret_id: int) -> SalesReturnMaster:
    ret = (
        db.query(SalesReturnMaster)
        .options(
            joinedload(SalesReturnMaster.items),
            joinedload(SalesReturnMaster.customer),
            joinedload(SalesReturnMaster.refund_mode),
        )
        .filter(SalesReturnMaster.id == ret_id)
        .first()
    )
    if not ret:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sales return not found.")
    return ret


# ── Returnable summary ─────────────────────────────────────────────────────────

@router.get("/sales/{sale_id}/returnable", response_model=ReturnableResponse)
def returnable(sale_id: int, db: Session = Depends(get_db)):
    sale = (
        db.query(SalesMaster)
        .options(joinedload(SalesMaster.items), joinedload(SalesMaster.customer))
        .filter(SalesMaster.id == sale_id)
        .first()
    )
    if not sale:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sale not found.")

    returned = _returned_by_sales_item(db, sale_id)
    names = dict(
        db.query(ItemMaster.id, ItemMaster.item_name)
        .filter(ItemMaster.id.in_([it.item_id for it in sale.items] or [0]))
        .all()
    )

    lines = []
    for it in sale.items:
        sold = it.quantity or ZERO
        done = returned.get(it.id, ZERO)
        lines.append(ReturnableLine(
            sales_item_id  = it.id,
            item_id        = it.item_id,
            item_name      = names.get(it.item_id),
            batch_no       = it.batch_no,
            sold_qty       = sold,
            returned_qty   = done,
            returnable_qty = max(sold - done, ZERO),
            mrp            = it.mrp,
            sale_rate      = it.sale_rate,
            gst_percent    = it.gst_percent,
            expiry_date    = it.expiry_date,
        ))

    return ReturnableResponse(
        sales_id      = sale.id,
        invoice_no    = sale.invoice_no,
        invoice_date  = sale.invoice_date,
        customer_id   = sale.customer_id,
        customer_name = sale.customer.party_name if sale.customer else None,
        lines         = lines,
    )


@router.get("/sales/{sale_id}/returns", response_model=List[SalesReturnResponse])
def returns_for_sale(sale_id: int, db: Session = Depends(get_db)):
    rets = (
        db.query(SalesReturnMaster)
        .options(joinedload(SalesReturnMaster.items),
                 joinedload(SalesReturnMaster.customer),
                 joinedload(SalesReturnMaster.refund_mode))
        .filter(SalesReturnMaster.sales_id == sale_id)
        .order_by(SalesReturnMaster.id.desc())
        .all()
    )
    return [_to_response(db, r) for r in rets]


# ── Create return ────────────────────────────────────────────────────────────

@router.post("/sales-returns/", response_model=SalesReturnResponse, status_code=status.HTTP_201_CREATED)
def create_return(payload: SalesReturnCreate, db: Session = Depends(get_db)):
    sale = (
        db.query(SalesMaster)
        .options(joinedload(SalesMaster.items))
        .filter(SalesMaster.id == payload.sales_id)
        .first()
    )
    if not sale:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sale not found.")
    if not payload.items:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one return line is required.")

    sold_lines = {it.id: it for it in sale.items}
    already = _returned_by_sales_item(db, sale.id)

    # Validate every line before touching stock.
    for line in payload.items:
        if line.sales_item_id is not None:
            orig = sold_lines.get(line.sales_item_id)
            if not orig:
                raise HTTPException(400, f"Sales line {line.sales_item_id} does not belong to this invoice.")
            remaining = (orig.quantity or ZERO) - already.get(line.sales_item_id, ZERO)
            if line.quantity > remaining:
                raise HTTPException(
                    400,
                    f"Cannot return {line.quantity} of item {line.item_id}; only {max(remaining, ZERO)} left to return.",
                )

    total = sum((li.total or ZERO) for li in payload.items)
    tax   = sum((li.tax_amount or ZERO) for li in payload.items)
    refund = payload.refund_amount if payload.refund_amount is not None else total
    refund_status = payload.refund_status or ("Refunded" if refund and refund > 0 else "Pending")

    ret = SalesReturnMaster(
        return_date    = payload.return_date or date.today(),
        sales_id       = sale.id,
        customer_id    = sale.customer_id,
        total_amount   = total,
        tax_amount     = tax,
        refund_amount  = refund,
        refund_mode_id = payload.refund_mode_id,
        refund_status  = refund_status,
        reason         = payload.reason,
        notes          = payload.notes,
    )
    db.add(ret)
    db.flush()                       # get ret.id
    ret.return_no = f"SR-{ret.id:05d}"

    for line in payload.items:
        ri = SalesReturnItem(
            return_id     = ret.id,
            sales_item_id = line.sales_item_id,
            item_id       = line.item_id,
            batch_no      = line.batch_no,
            quantity      = line.quantity,
            mrp           = line.mrp,
            sale_rate     = line.sale_rate,
            gst_percent   = line.gst_percent,
            tax_amount    = line.tax_amount,
            total         = line.total,
            expiry_date   = line.expiry_date,
        )
        db.add(ri)
        _restore_stock(db, ret.id, ri)      # ← inventory goes back UP

    # Record the cash/bank outflow for the refund so the books reflect it.
    if refund and refund > 0 and sale.customer_id and payload.refund_mode_id:
        db.add(PaymentMaster(
            party_id        = sale.customer_id,
            txn_type        = "PAYMENT",            # money OUT to the customer
            reference_type  = "adjustment",
            reference_id    = ret.id,
            txn_date        = ret.return_date,
            amount          = refund,
            payment_mode_id = payload.refund_mode_id,
            reference_no    = ret.return_no,
            notes           = "Sales return refund",
        ))

    db.commit()
    return _to_response(db, _load(db, ret.id))


# ── List / get / delete ──────────────────────────────────────────────────────

@router.get("/sales-returns/", response_model=List[SalesReturnResponse])
def list_returns(
    skip:        int            = Query(0,   ge=0),
    limit:       int            = Query(100, ge=1, le=500),
    sales_id:    Optional[int]  = Query(None),
    customer_id: Optional[int]  = Query(None),
    date_from:   Optional[date] = Query(None),
    date_to:     Optional[date] = Query(None),
    db:          Session        = Depends(get_db),
):
    q = db.query(SalesReturnMaster).options(
        joinedload(SalesReturnMaster.items),
        joinedload(SalesReturnMaster.customer),
        joinedload(SalesReturnMaster.refund_mode),
    )
    if sales_id:    q = q.filter(SalesReturnMaster.sales_id == sales_id)
    if customer_id: q = q.filter(SalesReturnMaster.customer_id == customer_id)
    if date_from:   q = q.filter(SalesReturnMaster.return_date >= date_from)
    if date_to:     q = q.filter(SalesReturnMaster.return_date <= date_to)
    rets = q.order_by(SalesReturnMaster.id.desc()).offset(skip).limit(limit).all()
    return [_to_response(db, r) for r in rets]


@router.get("/sales-returns/{return_id}", response_model=SalesReturnResponse)
def get_return(return_id: int, db: Session = Depends(get_db)):
    return _to_response(db, _load(db, return_id))


@router.delete("/sales-returns/{return_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_return(return_id: int, db: Session = Depends(get_db)):
    ret = _load(db, return_id)
    _reverse_stock(db, ret)                 # pull goods back out of inventory
    # remove the linked refund payment, if any
    db.query(PaymentMaster).filter(
        PaymentMaster.reference_type == "adjustment",
        PaymentMaster.reference_id   == ret.id,
    ).delete(synchronize_session=False)
    db.delete(ret)
    db.commit()
