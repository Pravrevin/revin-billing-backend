from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.category_master import CategoryMaster, SubCategoryMaster
from app.models.packaging_master import PackagingMaster
from app.models.brand_master import BrandMaster
from app.models.unit_master import UnitMaster
from app.models.item_master import ItemMaster
from app.schemas.item_master import ItemMasterCreate, ItemMasterResponse, ItemMasterUpdate

router = APIRouter(prefix="/item-master", tags=["Item Master"])


def _generate_item_code(db: Session) -> str:
    rows = db.query(ItemMaster.item_code).filter(
        ItemMaster.item_code.like("ITM%")
    ).all()
    max_num = 0
    for (code,) in rows:
        if code and code.startswith("ITM"):
            try:
                num = int(code[3:])
                if num > max_num:
                    max_num = num
            except ValueError:
                pass
    return f"ITM{max_num + 1:04d}"


def _validate_names(payload, db: Session):
    if payload.category_name:
        exists = db.query(CategoryMaster).filter(
            CategoryMaster.category_name == payload.category_name
        ).first()
        if not exists:
            raise HTTPException(status_code=400, detail=f"Category '{payload.category_name}' not found.")

    if payload.sub_category_name:
        exists = db.query(SubCategoryMaster).filter(
            SubCategoryMaster.sub_category_name == payload.sub_category_name
        ).first()
        if not exists:
            raise HTTPException(status_code=400, detail=f"Sub-category '{payload.sub_category_name}' not found.")

    if payload.packing_type:
        exists = db.query(PackagingMaster).filter(
            PackagingMaster.packing_type == payload.packing_type
        ).first()
        if not exists:
            raise HTTPException(status_code=400, detail=f"Packing type '{payload.packing_type}' not found.")

    if payload.brand_name:
        exists = db.query(BrandMaster).filter(
            BrandMaster.brand_name == payload.brand_name
        ).first()
        if not exists:
            raise HTTPException(status_code=400, detail=f"Brand '{payload.brand_name}' not found.")

    if payload.unit_name:
        exists = db.query(UnitMaster).filter(
            UnitMaster.unit_name == payload.unit_name
        ).first()
        if not exists:
            raise HTTPException(status_code=400, detail=f"Unit '{payload.unit_name}' not found.")


@router.post("/", response_model=ItemMasterResponse, status_code=status.HTTP_201_CREATED)
def create_item(payload: ItemMasterCreate, db: Session = Depends(get_db)):
    _validate_names(payload, db)
    item = ItemMaster(
        item_code=_generate_item_code(db),
        **payload.model_dump(),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.get("/", response_model=List[ItemMasterResponse])
def list_items(
    skip:      int           = Query(0, ge=0),
    limit:     int           = Query(50, ge=1, le=500),
    is_active: Optional[bool] = Query(None),
    search:    Optional[str]  = Query(None, description="Search by item name or code"),
    db:        Session        = Depends(get_db),
):
    query = db.query(ItemMaster)
    if is_active is not None:
        query = query.filter(ItemMaster.is_active == is_active)
    if search:
        pattern = f"%{search}%"
        query = query.filter(
            ItemMaster.item_name.ilike(pattern) | ItemMaster.item_code.ilike(pattern)
        )
    return query.offset(skip).limit(limit).all()


@router.get("/{item_id}", response_model=ItemMasterResponse)
def get_item(item_id: int, db: Session = Depends(get_db)):
    item = db.query(ItemMaster).filter(ItemMaster.id == item_id).first()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found.")
    return item


@router.patch("/{item_id}", response_model=ItemMasterResponse)
def update_item(item_id: int, payload: ItemMasterUpdate, db: Session = Depends(get_db)):
    item = db.query(ItemMaster).filter(ItemMaster.id == item_id).first()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found.")
    _validate_names(payload, db)
    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(item, field, value)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(item_id: int, db: Session = Depends(get_db)):
    item = db.query(ItemMaster).filter(ItemMaster.id == item_id).first()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found.")
    db.delete(item)
    db.commit()
