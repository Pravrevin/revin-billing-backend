from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.brand_master import BrandMaster
from app.schemas.brand_master import (
    BrandMasterCreate, BrandMasterResponse, BrandMasterUpdate,
)

router = APIRouter(prefix="/brand-master", tags=["Brand Master"])


@router.post("/", response_model=BrandMasterResponse, status_code=status.HTTP_201_CREATED)
def create_brand(payload: BrandMasterCreate, db: Session = Depends(get_db)):
    existing = db.query(BrandMaster).filter(
        BrandMaster.brand_name == payload.brand_name
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Brand '{payload.brand_name}' already exists.",
        )
    brand = BrandMaster(**payload.model_dump())
    db.add(brand)
    db.commit()
    db.refresh(brand)
    return brand


@router.get("/", response_model=List[BrandMasterResponse])
def list_brands(
    is_active: Optional[bool] = Query(None),
    search:    Optional[str]  = Query(None, description="Search by brand name"),
    db:        Session        = Depends(get_db),
):
    query = db.query(BrandMaster)
    if is_active is not None:
        query = query.filter(BrandMaster.is_active == is_active)
    if search:
        query = query.filter(BrandMaster.brand_name.ilike(f"%{search}%"))
    return query.all()


@router.get("/{brand_id}", response_model=BrandMasterResponse)
def get_brand(brand_id: int, db: Session = Depends(get_db)):
    brand = db.query(BrandMaster).filter(BrandMaster.id == brand_id).first()
    if not brand:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brand not found.")
    return brand


@router.patch("/{brand_id}", response_model=BrandMasterResponse)
def update_brand(brand_id: int, payload: BrandMasterUpdate, db: Session = Depends(get_db)):
    brand = db.query(BrandMaster).filter(BrandMaster.id == brand_id).first()
    if not brand:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brand not found.")
    if payload.brand_name and payload.brand_name != brand.brand_name:
        clash = db.query(BrandMaster).filter(
            BrandMaster.brand_name == payload.brand_name
        ).first()
        if clash:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Brand '{payload.brand_name}' already exists.",
            )
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(brand, field, value)
    db.commit()
    db.refresh(brand)
    return brand


@router.delete("/{brand_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_brand(brand_id: int, db: Session = Depends(get_db)):
    brand = db.query(BrandMaster).filter(BrandMaster.id == brand_id).first()
    if not brand:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brand not found.")
    db.delete(brand)
    db.commit()
