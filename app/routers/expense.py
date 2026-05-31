"""
Expenses router (/api/v1/expenses)
──────────────────────────────────
CRUD over day-to-day business expenses (rent, salary, utilities, …).
Each expense is money OUT and feeds the Cash / Bank Book and Day Book.
"""
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models.expense import ExpenseMaster
from app.schemas.expense import ExpenseCreate, ExpenseResponse, ExpenseUpdate

router = APIRouter(prefix="/expenses", tags=["Expenses"])

# A sensible default category list the UI can offer alongside any already used.
DEFAULT_CATEGORIES = [
    "Rent", "Salary", "Electricity", "Water", "Internet & Phone",
    "Transport", "Maintenance", "Stationery", "Marketing", "Bank Charges",
    "Taxes & Fees", "Miscellaneous",
]


def _to_response(e: ExpenseMaster) -> ExpenseResponse:
    return ExpenseResponse(
        id                = e.id,
        expense_date      = e.expense_date,
        category          = e.category,
        description       = e.description,
        amount            = e.amount,
        payment_mode_id   = e.payment_mode_id,
        payment_mode_name = e.payment_mode.mode_name if e.payment_mode else None,
        reference_no      = e.reference_no,
        notes             = e.notes,
        created_at        = e.created_at,
        updated_at        = e.updated_at,
    )


@router.post("/", response_model=ExpenseResponse, status_code=status.HTTP_201_CREATED)
def create_expense(payload: ExpenseCreate, db: Session = Depends(get_db)):
    exp = ExpenseMaster(**payload.model_dump())
    db.add(exp)
    db.commit()
    db.refresh(exp)
    exp = (
        db.query(ExpenseMaster)
        .options(joinedload(ExpenseMaster.payment_mode))
        .filter(ExpenseMaster.id == exp.id)
        .first()
    )
    return _to_response(exp)


@router.get("/categories", response_model=List[str])
def expense_categories(db: Session = Depends(get_db)):
    """Distinct categories already used, merged with the default suggestions."""
    used = [
        c[0] for c in db.query(ExpenseMaster.category)
        .filter(ExpenseMaster.category.isnot(None))
        .distinct()
        .all()
        if c[0]
    ]
    merged = list(dict.fromkeys([*DEFAULT_CATEGORIES, *used]))
    return merged


@router.get("/", response_model=List[ExpenseResponse])
def list_expenses(
    skip:      int            = Query(0,   ge=0),
    limit:     int            = Query(200, ge=1, le=1000),
    category:  Optional[str]  = Query(None),
    date_from: Optional[date] = Query(None),
    date_to:   Optional[date] = Query(None),
    db:        Session        = Depends(get_db),
):
    q = db.query(ExpenseMaster).options(joinedload(ExpenseMaster.payment_mode))
    if category:  q = q.filter(ExpenseMaster.category == category)
    if date_from: q = q.filter(ExpenseMaster.expense_date >= date_from)
    if date_to:   q = q.filter(ExpenseMaster.expense_date <= date_to)
    rows = q.order_by(ExpenseMaster.expense_date.desc(), ExpenseMaster.id.desc()).offset(skip).limit(limit).all()
    return [_to_response(e) for e in rows]


@router.get("/{expense_id}", response_model=ExpenseResponse)
def get_expense(expense_id: int, db: Session = Depends(get_db)):
    exp = (
        db.query(ExpenseMaster)
        .options(joinedload(ExpenseMaster.payment_mode))
        .filter(ExpenseMaster.id == expense_id)
        .first()
    )
    if not exp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Expense not found.")
    return _to_response(exp)


@router.patch("/{expense_id}", response_model=ExpenseResponse)
def update_expense(expense_id: int, payload: ExpenseUpdate, db: Session = Depends(get_db)):
    exp = db.query(ExpenseMaster).filter(ExpenseMaster.id == expense_id).first()
    if not exp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Expense not found.")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(exp, field, value)
    db.commit()
    exp = (
        db.query(ExpenseMaster)
        .options(joinedload(ExpenseMaster.payment_mode))
        .filter(ExpenseMaster.id == expense_id)
        .first()
    )
    return _to_response(exp)


@router.delete("/{expense_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_expense(expense_id: int, db: Session = Depends(get_db)):
    exp = db.query(ExpenseMaster).filter(ExpenseMaster.id == expense_id).first()
    if not exp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Expense not found.")
    db.delete(exp)
    db.commit()
