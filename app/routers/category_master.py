from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.category_master import CategoryMaster, SubCategoryMaster
from app.schemas.category_master import (
    CategoryMasterCreate, CategoryMasterResponse, CategoryMasterUpdate,
    SubCategoryMasterCreate, SubCategoryMasterResponse, SubCategoryMasterUpdate,
)

router = APIRouter(prefix="/category-master", tags=["Category Master"])


def _generate_category_code(db: Session) -> str:
    rows = db.query(CategoryMaster.category_code).filter(
        CategoryMaster.category_code.like("CAT%")
    ).all()
    max_num = 0
    for (code,) in rows:
        if code and code.startswith("CAT"):
            try:
                num = int(code[3:])
                if num > max_num:
                    max_num = num
            except ValueError:
                pass
    return f"CAT{max_num + 1:04d}"


def _generate_sub_category_code(db: Session) -> str:
    rows = db.query(SubCategoryMaster.sub_category_code).filter(
        SubCategoryMaster.sub_category_code.like("SUB%")
    ).all()
    max_num = 0
    for (code,) in rows:
        if code and code.startswith("SUB"):
            try:
                num = int(code[3:])
                if num > max_num:
                    max_num = num
            except ValueError:
                pass
    return f"SUB{max_num + 1:04d}"


# ── Category ───────────────────────────────────────────────────────────────────

@router.post("/", response_model=CategoryMasterResponse, status_code=status.HTTP_201_CREATED)
def create_category(payload: CategoryMasterCreate, db: Session = Depends(get_db)):
    category = CategoryMaster(
        category_code=_generate_category_code(db),
        **payload.model_dump(),
    )
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


@router.get("/", response_model=List[CategoryMasterResponse])
def list_categories(
    is_active: Optional[bool] = Query(None),
    search:    Optional[str]  = Query(None),
    db:        Session        = Depends(get_db),
):
    query = db.query(CategoryMaster)
    if is_active is not None:
        query = query.filter(CategoryMaster.is_active == is_active)
    if search:
        query = query.filter(CategoryMaster.category_name.ilike(f"%{search}%"))
    return query.all()


@router.get("/{category_id}", response_model=CategoryMasterResponse)
def get_category(category_id: int, db: Session = Depends(get_db)):
    category = db.query(CategoryMaster).filter(CategoryMaster.id == category_id).first()
    if not category:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found.")
    return category


@router.patch("/{category_id}", response_model=CategoryMasterResponse)
def update_category(category_id: int, payload: CategoryMasterUpdate, db: Session = Depends(get_db)):
    category = db.query(CategoryMaster).filter(CategoryMaster.id == category_id).first()
    if not category:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found.")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(category, field, value)
    db.commit()
    db.refresh(category)
    return category


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(category_id: int, db: Session = Depends(get_db)):
    category = db.query(CategoryMaster).filter(CategoryMaster.id == category_id).first()
    if not category:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found.")
    db.delete(category)
    db.commit()


# ── Sub Category ───────────────────────────────────────────────────────────────

@router.post("/sub-category", response_model=SubCategoryMasterResponse, status_code=status.HTTP_201_CREATED)
def create_sub_category(payload: SubCategoryMasterCreate, db: Session = Depends(get_db)):
    category = db.query(CategoryMaster).filter(CategoryMaster.id == payload.category_id).first()
    if not category:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parent category not found.")
    sub = SubCategoryMaster(
        sub_category_code=_generate_sub_category_code(db),
        **payload.model_dump(),
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)
    result = SubCategoryMasterResponse.model_validate(sub)
    result.category_name = sub.category.category_name
    return result


@router.get("/sub-category/all", response_model=List[SubCategoryMasterResponse])
def list_sub_categories(
    category_id: Optional[int]  = Query(None),
    is_active:   Optional[bool] = Query(None),
    db:          Session        = Depends(get_db),
):
    query = db.query(SubCategoryMaster)
    if category_id:
        query = query.filter(SubCategoryMaster.category_id == category_id)
    if is_active is not None:
        query = query.filter(SubCategoryMaster.is_active == is_active)
    return query.all()


@router.patch("/sub-category/{sub_id}", response_model=SubCategoryMasterResponse)
def update_sub_category(sub_id: int, payload: SubCategoryMasterUpdate, db: Session = Depends(get_db)):
    sub = db.query(SubCategoryMaster).filter(SubCategoryMaster.id == sub_id).first()
    if not sub:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sub-category not found.")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(sub, field, value)
    db.commit()
    db.refresh(sub)
    return sub


@router.delete("/sub-category/{sub_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sub_category(sub_id: int, db: Session = Depends(get_db)):
    sub = db.query(SubCategoryMaster).filter(SubCategoryMaster.id == sub_id).first()
    if not sub:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sub-category not found.")
    db.delete(sub)
    db.commit()
