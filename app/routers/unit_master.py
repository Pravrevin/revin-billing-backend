from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.unit_master import UnitMaster
from app.schemas.unit_master import (
    UnitMasterCreate, UnitMasterResponse, UnitMasterUpdate,
)

router = APIRouter(prefix="/unit-master", tags=["Unit Master"])


@router.post("/", response_model=UnitMasterResponse, status_code=status.HTTP_201_CREATED)
def create_unit(payload: UnitMasterCreate, db: Session = Depends(get_db)):
    existing = db.query(UnitMaster).filter(
        UnitMaster.unit_name == payload.unit_name
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Unit '{payload.unit_name}' already exists.",
        )
    unit = UnitMaster(**payload.model_dump())
    db.add(unit)
    db.commit()
    db.refresh(unit)
    return unit


@router.get("/", response_model=List[UnitMasterResponse])
def list_units(
    is_active: Optional[bool] = Query(None),
    search:    Optional[str]  = Query(None, description="Search by unit name"),
    db:        Session        = Depends(get_db),
):
    query = db.query(UnitMaster)
    if is_active is not None:
        query = query.filter(UnitMaster.is_active == is_active)
    if search:
        query = query.filter(UnitMaster.unit_name.ilike(f"%{search}%"))
    return query.all()


@router.get("/{unit_name}", response_model=UnitMasterResponse)
def get_unit(unit_name: str, db: Session = Depends(get_db)):
    unit = db.query(UnitMaster).filter(UnitMaster.unit_name == unit_name).first()
    if not unit:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unit not found.")
    return unit


@router.patch("/{unit_name}", response_model=UnitMasterResponse)
def update_unit(unit_name: str, payload: UnitMasterUpdate, db: Session = Depends(get_db)):
    unit = db.query(UnitMaster).filter(UnitMaster.unit_name == unit_name).first()
    if not unit:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unit not found.")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(unit, field, value)
    db.commit()
    db.refresh(unit)
    return unit


@router.delete("/{unit_name}", status_code=status.HTTP_204_NO_CONTENT)
def delete_unit(unit_name: str, db: Session = Depends(get_db)):
    unit = db.query(UnitMaster).filter(UnitMaster.unit_name == unit_name).first()
    if not unit:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unit not found.")
    db.delete(unit)
    db.commit()
