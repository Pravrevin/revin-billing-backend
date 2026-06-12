from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth.deps import get_tenant_db as get_db
from app.models.marketer_master import MarketerMaster
from app.schemas.marketer_master import (
    MarketerMasterCreate, MarketerMasterResponse, MarketerMasterUpdate,
)

router = APIRouter(prefix="/marketer-master", tags=["Marketer Master"])


def _generate_marketer_code(db: Session) -> str:
    rows = db.query(MarketerMaster.marketer_code).filter(
        MarketerMaster.marketer_code.like("MKT%")
    ).all()
    max_num = 0
    for (code,) in rows:
        if code and code.startswith("MKT"):
            try:
                num = int(code[3:])
                if num > max_num:
                    max_num = num
            except ValueError:
                pass
    return f"MKT{max_num + 1:04d}"


@router.post("/", response_model=MarketerMasterResponse, status_code=status.HTTP_201_CREATED)
def create_marketer(payload: MarketerMasterCreate, db: Session = Depends(get_db)):
    marketer = MarketerMaster(
        marketer_code=_generate_marketer_code(db),
        **payload.model_dump(),
    )
    db.add(marketer)
    db.commit()
    db.refresh(marketer)
    return marketer


@router.get("/", response_model=List[MarketerMasterResponse])
def list_marketers(
    is_active: Optional[bool] = Query(None),
    search:    Optional[str]  = Query(None),
    db:        Session        = Depends(get_db),
):
    query = db.query(MarketerMaster)
    if is_active is not None:
        query = query.filter(MarketerMaster.is_active == is_active)
    if search:
        query = query.filter(MarketerMaster.marketer_name.ilike(f"%{search}%"))
    return query.all()


@router.get("/{marketer_id}", response_model=MarketerMasterResponse)
def get_marketer(marketer_id: int, db: Session = Depends(get_db)):
    marketer = db.query(MarketerMaster).filter(MarketerMaster.id == marketer_id).first()
    if not marketer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Marketer not found.")
    return marketer


@router.patch("/{marketer_id}", response_model=MarketerMasterResponse)
def update_marketer(marketer_id: int, payload: MarketerMasterUpdate, db: Session = Depends(get_db)):
    marketer = db.query(MarketerMaster).filter(MarketerMaster.id == marketer_id).first()
    if not marketer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Marketer not found.")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(marketer, field, value)
    db.commit()
    db.refresh(marketer)
    return marketer


@router.delete("/{marketer_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_marketer(marketer_id: int, db: Session = Depends(get_db)):
    marketer = db.query(MarketerMaster).filter(MarketerMaster.id == marketer_id).first()
    if not marketer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Marketer not found.")
    db.delete(marketer)
    db.commit()
