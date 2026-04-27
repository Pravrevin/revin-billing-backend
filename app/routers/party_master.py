from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.party_master import PartyMaster
from app.schemas.party_master import PartyMasterCreate, PartyMasterResponse, PartyMasterUpdate, PartyType

router = APIRouter(prefix="/party-master", tags=["Party Master"])

PARTY_CODE_PREFIX = {
    PartyType.customer:    "CUST",
    PartyType.distributor: "SUPP",
}


def _generate_party_code(db: Session, party_type: PartyType) -> str:
    prefix = PARTY_CODE_PREFIX[party_type]
    rows = (
        db.query(PartyMaster.party_code)
        .filter(PartyMaster.party_code.like(f"{prefix}%"))
        .all()
    )
    max_num = 0
    for (code,) in rows:
        if code and code.startswith(prefix):
            try:
                num = int(code[len(prefix):])
                if num > max_num:
                    max_num = num
            except ValueError:
                pass
    return f"{prefix}{max_num + 1:04d}"


@router.get("/party-types", response_model=List[str], tags=["Party Master"])
def get_party_types():
    """Returns the allowed party types."""
    return [t.value for t in PartyType]


@router.post("/", response_model=PartyMasterResponse, status_code=status.HTTP_201_CREATED)
def create_party(payload: PartyMasterCreate, db: Session = Depends(get_db)):
    data = payload.model_dump()

    if not data.get("party_code"):
        data["party_code"] = _generate_party_code(db, payload.party_type)
    else:
        existing = db.query(PartyMaster).filter(PartyMaster.party_code == data["party_code"]).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Party with code '{data['party_code']}' already exists.",
            )

    party = PartyMaster(**data)
    db.add(party)
    db.commit()
    db.refresh(party)
    return party


@router.get("/", response_model=List[PartyMasterResponse])
def list_parties(
    skip:       int                  = Query(0, ge=0),
    limit:      int                  = Query(50, ge=1, le=500),
    party_type: Optional[PartyType]  = Query(None, description="Customer or Distributor"),
    is_active:  Optional[bool]       = Query(None),
    search:     Optional[str]        = Query(None, description="Search by party name, code or mobile"),
    db:         Session              = Depends(get_db),
):
    query = db.query(PartyMaster)
    if party_type:
        query = query.filter(PartyMaster.party_type == party_type.value)
    if is_active is not None:
        query = query.filter(PartyMaster.is_active == is_active)
    if search:
        pattern = f"%{search}%"
        query = query.filter(
            PartyMaster.party_name.ilike(pattern)
            | PartyMaster.party_code.ilike(pattern)
            | PartyMaster.mobile.ilike(pattern)
        )
    return query.offset(skip).limit(limit).all()


@router.get("/{party_id}", response_model=PartyMasterResponse)
def get_party(party_id: int, db: Session = Depends(get_db)):
    party = db.query(PartyMaster).filter(PartyMaster.id == party_id).first()
    if not party:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Party not found.")
    return party


@router.patch("/{party_id}", response_model=PartyMasterResponse)
def update_party(party_id: int, payload: PartyMasterUpdate, db: Session = Depends(get_db)):
    party = db.query(PartyMaster).filter(PartyMaster.id == party_id).first()
    if not party:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Party not found.")
    if payload.pan_card is not None or payload.bank_details is not None:
        effective_type = (payload.party_type or party.party_type)
        if effective_type != PartyType.distributor.value:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="pan_card and bank_details are only applicable for Distributor party type",
            )
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(party, field, value)
    db.commit()
    db.refresh(party)
    return party


@router.delete("/{party_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_party(party_id: int, db: Session = Depends(get_db)):
    party = db.query(PartyMaster).filter(PartyMaster.id == party_id).first()
    if not party:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Party not found.")
    db.delete(party)
    db.commit()
