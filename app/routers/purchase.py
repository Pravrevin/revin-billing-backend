import os
from datetime import date
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session, joinedload

from app.auth.deps import get_tenant_db as get_db
from app.models.party_master import PartyMaster
from app.models.purchase_master import PurchaseItem, PurchaseMaster
from app.models.stock_master import StockLedger, StockMaster
from app.schemas.purchase import (
    PurchaseItemResponse,
    PurchaseMasterCreate,
    PurchaseMasterResponse,
    PurchaseMasterUpdate,
)
from app.schemas.stock_master import StockLedgerResponse
from app.services.bill_mapper import map_extraction_to_purchase
from app.services.pdf_extractor import IMAGE_MIME_TYPES, PdfExtractor

router = APIRouter(prefix="/purchases", tags=["Purchase"])

# Max upload size per file (10 MB) for AI bill extraction.
_MAX_BILL_FILE_BYTES = 10 * 1024 * 1024


def _generate_invoice_no(db: Session) -> str:
    year = date.today().year
    prefix = f"PUR-{year}-"
    rows = db.query(PurchaseMaster.invoice_no).filter(
        PurchaseMaster.invoice_no.like(f"{prefix}%")
    ).all()
    max_num = 0
    for (inv_no,) in rows:
        if inv_no and inv_no.startswith(prefix):
            try:
                num = int(inv_no[len(prefix):])
                if num > max_num:
                    max_num = num
            except ValueError:
                pass
    return f"{prefix}{max_num + 1:04d}"


def _calculate_item_amounts(item_data) -> dict:
    """Auto-calculate gross_amount, discount_amount, tax_amount, total from base fields."""
    qty           = item_data.quantity      or Decimal("0")
    rate          = item_data.purchase_rate or Decimal("0")
    disc_pct      = item_data.discount      or Decimal("0")
    gst_pct       = item_data.gst_percent   or Decimal("0")

    gross_amount    = qty * rate
    discount_amount = gross_amount * disc_pct / Decimal("100")
    taxable         = gross_amount - discount_amount
    tax_amount      = taxable * gst_pct / Decimal("100")
    total           = taxable + tax_amount

    return {
        "gross_amount":    round(gross_amount,    2),
        "discount_amount": round(discount_amount, 2),
        "tax_amount":      round(tax_amount,      2),
        "total":           round(total,           2),
    }


def _upsert_stock_and_ledger(db: Session, purchase_id: int, item_data):
    """Update stock_master quantity and write a ledger entry for one purchase item."""
    qty        = item_data.quantity       or Decimal("0")
    free_qty   = item_data.free_quantity  or Decimal("0")

    stock = (
        db.query(StockMaster)
        .filter(
            StockMaster.item_id  == item_data.item_id,
            StockMaster.batch_no == item_data.batch_no,
        )
        .first()
    )

    if stock:
        stock.quantity      = (stock.quantity      or Decimal("0")) + qty
        stock.free_quantity = (stock.free_quantity or Decimal("0")) + free_qty
        if item_data.mrp:
            stock.mrp = item_data.mrp
        if item_data.purchase_rate:
            stock.purchase_rate = item_data.purchase_rate
        if item_data.sale_rate:
            stock.sale_rate = item_data.sale_rate
        if item_data.expiry_date:
            stock.expiry_date = item_data.expiry_date
    else:
        stock = StockMaster(
            item_id       = item_data.item_id,
            batch_no      = item_data.batch_no,
            quantity      = qty,
            free_quantity = free_qty,
            mrp           = item_data.mrp,
            purchase_rate = item_data.purchase_rate,
            sale_rate     = item_data.sale_rate,
            expiry_date   = item_data.expiry_date,
        )
        db.add(stock)

    ledger = StockLedger(
        item_id        = item_data.item_id,
        batch_no       = item_data.batch_no,
        movement_type  = "IN",
        quantity       = qty,
        free_quantity  = free_qty,
        reference_type = "purchase",
        reference_id   = purchase_id,
        purchase_rate  = item_data.purchase_rate,
        mrp            = item_data.mrp,
    )
    db.add(ledger)


# ── Purchase Master ────────────────────────────────────────────────────────────

@router.post("/", response_model=PurchaseMasterResponse, status_code=status.HTTP_201_CREATED)
def create_purchase(payload: PurchaseMasterCreate, db: Session = Depends(get_db)):
    data = payload.model_dump(exclude={"items"})

    # Auto-generate invoice number if not provided
    if not data.get("invoice_no"):
        data["invoice_no"] = _generate_invoice_no(db)

    purchase = PurchaseMaster(**data)
    db.add(purchase)
    db.flush()  # get purchase.id before inserting items

    total_gross    = Decimal("0")
    total_discount = Decimal("0")
    total_tax      = Decimal("0")
    total_net      = Decimal("0")

    for item_data in payload.items:
        item_dict = item_data.model_dump()
        calculated = _calculate_item_amounts(item_data)
        item_dict.update(calculated)
        item = PurchaseItem(purchase_id=purchase.id, **item_dict)
        db.add(item)
        _upsert_stock_and_ledger(db, purchase.id, item_data)

        total_gross    += calculated["gross_amount"]
        total_discount += calculated["discount_amount"]
        total_tax      += calculated["tax_amount"]
        total_net      += calculated["total"]

    # Overwrite header totals with sum of item calculations
    purchase.total_amount    = round(total_gross,    2)
    purchase.discount_amount = round(total_discount, 2)
    purchase.tax_amount      = round(total_tax,      2)
    purchase.net_amount      = round(total_net,      2)

    db.commit()
    db.refresh(purchase)
    return purchase


@router.post("/extract-bill")
async def extract_bill(files: List[UploadFile] = File(...), db: Session = Depends(get_db)):
    """
    Run AI (Mistral OCR + LLM) over an uploaded supplier bill and return a
    prefill payload for the purchase-entry form.

    Accepts one of:
      • a single PDF (any number of pages), or
      • a single image, or
      • multiple images (e.g. a multi-page scan, up to 10).

    The response maps the extracted table onto purchase line fields and
    best-effort-matches the supplier and each medicine against the masters.
    Unmatched items still come back (with extracted_name) for manual picking.
    """
    if not files:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No file uploaded.")

    # Read + classify every uploaded file.
    pdfs: List[bytes] = []
    images: List[tuple[bytes, str]] = []
    image_names: List[str] = []
    for f in files:
        content = await f.read()
        if not content:
            continue
        if len(content) > _MAX_BILL_FILE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"'{f.filename}' is larger than 10 MB.",
            )
        ext = os.path.splitext(f.filename or "")[1].lower()
        ctype = (f.content_type or "").lower()
        if ext == ".pdf" or ctype == "application/pdf":
            pdfs.append(content)
        elif ext in IMAGE_MIME_TYPES or ctype.startswith("image/"):
            mime = IMAGE_MIME_TYPES.get(ext) or (ctype if ctype.startswith("image/") else "image/jpeg")
            images.append((content, mime))
            image_names.append(f.filename or f"image-{len(image_names) + 1}")
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported file '{f.filename}'. Upload a PDF or image(s).",
            )

    if not pdfs and not images:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No readable file content.")
    if pdfs and images:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Upload either a single PDF or one-or-more images — not both at once.",
        )
    if len(pdfs) > 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please upload only one PDF at a time.",
        )
    if len(images) > 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum 10 images per bill.",
        )

    extractor = PdfExtractor()
    try:
        if pdfs:
            extraction = await extractor.extract_from_pdf_bytes(pdfs[0])
        elif len(images) == 1:
            extraction = await extractor.extract_from_image_bytes(images[0][0], images[0][1])
        else:
            extraction = await extractor.extract_from_images_bytes(images, image_names)
    except Exception as exc:  # OCR/LLM failures → 502 with the message surfaced
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Bill extraction failed: {exc}",
        )

    return map_extraction_to_purchase(extraction, db)


@router.get("/", response_model=List[PurchaseMasterResponse])
def list_purchases(
    skip:        int           = Query(0, ge=0),
    limit:       int           = Query(50, ge=1, le=500),
    supplier_id: Optional[int] = Query(None),
    party_id:    Optional[int] = Query(None, description="Filter by party_master.id"),
    party_type:  Optional[str] = Query(None, description="Filter by party type, e.g. Distributor, Supplier"),
    db:          Session       = Depends(get_db),
):
    query = db.query(PurchaseMaster).options(
        joinedload(PurchaseMaster.supplier),
        joinedload(PurchaseMaster.items).joinedload(PurchaseItem.item),
    )

    # party_id / party_type filters — join party_master only when needed
    if party_id or party_type:
        query = query.join(PartyMaster, PurchaseMaster.supplier_id == PartyMaster.id)
        if party_id:
            query = query.filter(PartyMaster.id == party_id)
        if party_type:
            query = query.filter(PartyMaster.party_type == party_type)
    elif supplier_id:
        query = query.filter(PurchaseMaster.supplier_id == supplier_id)

    return query.offset(skip).limit(limit).all()


@router.get("/{purchase_id}", response_model=PurchaseMasterResponse)
def get_purchase(purchase_id: int, db: Session = Depends(get_db)):
    purchase = (
        db.query(PurchaseMaster)
        .options(
            joinedload(PurchaseMaster.supplier),
            joinedload(PurchaseMaster.items).joinedload(PurchaseItem.item),
        )
        .filter(PurchaseMaster.id == purchase_id)
        .first()
    )
    if not purchase:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Purchase not found.")
    return purchase


@router.patch("/{purchase_id}", response_model=PurchaseMasterResponse)
def update_purchase(purchase_id: int, payload: PurchaseMasterUpdate, db: Session = Depends(get_db)):
    purchase = db.query(PurchaseMaster).filter(PurchaseMaster.id == purchase_id).first()
    if not purchase:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Purchase not found.")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(purchase, field, value)
    db.commit()
    db.refresh(purchase)
    return purchase


@router.delete("/{purchase_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_purchase(purchase_id: int, db: Session = Depends(get_db)):
    purchase = db.query(PurchaseMaster).filter(PurchaseMaster.id == purchase_id).first()
    if not purchase:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Purchase not found.")
    db.delete(purchase)
    db.commit()


# ── Purchase Items (sub-resource) ──────────────────────────────────────────────

@router.get("/{purchase_id}/items", response_model=List[PurchaseItemResponse])
def list_purchase_items(purchase_id: int, db: Session = Depends(get_db)):
    purchase = db.query(PurchaseMaster).filter(PurchaseMaster.id == purchase_id).first()
    if not purchase:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Purchase not found.")
    return purchase.items


@router.get("/{purchase_id}/stock-movements", response_model=List[StockLedgerResponse])
def get_purchase_stock_movements(purchase_id: int, db: Session = Depends(get_db)):
    """Return all stock ledger entries created by this purchase."""
    purchase = db.query(PurchaseMaster).filter(PurchaseMaster.id == purchase_id).first()
    if not purchase:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Purchase not found.")
    return (
        db.query(StockLedger)
        .options(joinedload(StockLedger.item))
        .filter(StockLedger.reference_type == "purchase", StockLedger.reference_id == purchase_id)
        .order_by(StockLedger.id)
        .all()
    )


@router.delete("/{purchase_id}/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_purchase_item(purchase_id: int, item_id: int, db: Session = Depends(get_db)):
    item = (
        db.query(PurchaseItem)
        .filter(PurchaseItem.id == item_id, PurchaseItem.purchase_id == purchase_id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Purchase item not found.")
    db.delete(item)
    db.commit()
