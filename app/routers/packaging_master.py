from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.packaging_master import PackagingMaster
from app.schemas.packaging_master import (
    PackagingMasterCreate, PackagingMasterResponse, PackagingMasterUpdate,
)

router = APIRouter(prefix="/packaging-master", tags=["Packaging Master"])


@router.post("/", response_model=PackagingMasterResponse, status_code=status.HTTP_201_CREATED)
def create_packaging(payload: PackagingMasterCreate, db: Session = Depends(get_db)):
    existing = db.query(PackagingMaster).filter(
        PackagingMaster.packing_type == payload.packing_type
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Packing type '{payload.packing_type}' already exists.",
        )
    packaging = PackagingMaster(**payload.model_dump())
    db.add(packaging)
    db.commit()
    db.refresh(packaging)
    return packaging


@router.get("/", response_model=List[PackagingMasterResponse])
def list_packaging(
    is_active: Optional[bool] = Query(None),
    search:    Optional[str]  = Query(None, description="Search by packing type"),
    db:        Session        = Depends(get_db),
):
    query = db.query(PackagingMaster)
    if is_active is not None:
        query = query.filter(PackagingMaster.is_active == is_active)
    if search:
        query = query.filter(PackagingMaster.packing_type.ilike(f"%{search}%"))
    return query.all()


@router.get("/{packaging_id}", response_model=PackagingMasterResponse)
def get_packaging(packaging_id: int, db: Session = Depends(get_db)):
    packaging = db.query(PackagingMaster).filter(PackagingMaster.id == packaging_id).first()
    if not packaging:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Packaging not found.")
    return packaging


@router.patch("/{packaging_id}", response_model=PackagingMasterResponse)
def update_packaging(packaging_id: int, payload: PackagingMasterUpdate, db: Session = Depends(get_db)):
    packaging = db.query(PackagingMaster).filter(PackagingMaster.id == packaging_id).first()
    if not packaging:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Packaging not found.")
    if payload.packing_type and payload.packing_type != packaging.packing_type:
        clash = db.query(PackagingMaster).filter(
            PackagingMaster.packing_type == payload.packing_type
        ).first()
        if clash:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Packing type '{payload.packing_type}' already exists.",
            )
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(packaging, field, value)
    db.commit()
    db.refresh(packaging)
    return packaging


@router.delete("/{packaging_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_packaging(packaging_id: int, db: Session = Depends(get_db)):
    packaging = db.query(PackagingMaster).filter(PackagingMaster.id == packaging_id).first()
    if not packaging:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Packaging not found.")
    db.delete(packaging)
    db.commit()
