from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload

from app.auth.deps import get_tenant_db as get_db
from app.models.purchase_payment import PartyCreditConfig
from app.schemas.purchase_payment import (
    PartyCreditConfigCreate,
    PartyCreditConfigResponse,
    PartyCreditConfigUpdate,
)

router = APIRouter(prefix="/party-credit-config", tags=["Party Credit Config"])


def _to_response(cfg: PartyCreditConfig) -> PartyCreditConfigResponse:
    return PartyCreditConfigResponse(
        id                 = cfg.id,
        party_id           = cfg.party_id,
        credit_days        = cfg.credit_days,
        overdue_grace_days = cfg.overdue_grace_days,
        created_at         = cfg.created_at,
        updated_at         = cfg.updated_at,
        party_name         = cfg.party.party_name if cfg.party else "Global Default",
    )


@router.get("/", response_model=List[PartyCreditConfigResponse])
def list_configs(
    party_id: Optional[int] = Query(None, description="Filter by party id"),
    db: Session = Depends(get_db),
):
    """
    List all credit configurations.
    The row where party_id IS NULL is the global default that applies to
    all parties without a specific override.
    """
    q = db.query(PartyCreditConfig).options(joinedload(PartyCreditConfig.party))
    if party_id is not None:
        q = q.filter(PartyCreditConfig.party_id == party_id)
    cfgs = q.order_by(PartyCreditConfig.party_id.asc().nullsfirst()).all()
    return [_to_response(c) for c in cfgs]


@router.post("/", response_model=PartyCreditConfigResponse, status_code=status.HTTP_201_CREATED)
def create_config(payload: PartyCreditConfigCreate, db: Session = Depends(get_db)):
    """
    Create a credit config.
    - Pass `party_id: null` to update/create the global default.
    - Pass a party_id to override for that specific party.
    """
    existing = (
        db.query(PartyCreditConfig)
        .filter(
            PartyCreditConfig.party_id == payload.party_id
            if payload.party_id is not None
            else PartyCreditConfig.party_id.is_(None)
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail=(
                "A config for this party already exists. "
                f"Use PATCH /party-credit-config/{existing.id} to update it."
            ),
        )
    cfg = PartyCreditConfig(**payload.model_dump())
    db.add(cfg)
    db.commit()
    db.refresh(cfg)
    cfg = db.query(PartyCreditConfig).options(joinedload(PartyCreditConfig.party)).filter(
        PartyCreditConfig.id == cfg.id
    ).first()
    return _to_response(cfg)


@router.get("/{config_id}", response_model=PartyCreditConfigResponse)
def get_config(config_id: int, db: Session = Depends(get_db)):
    cfg = (
        db.query(PartyCreditConfig)
        .options(joinedload(PartyCreditConfig.party))
        .filter(PartyCreditConfig.id == config_id)
        .first()
    )
    if not cfg:
        raise HTTPException(status_code=404, detail="Config not found.")
    return _to_response(cfg)


@router.patch("/{config_id}", response_model=PartyCreditConfigResponse)
def update_config(config_id: int, payload: PartyCreditConfigUpdate, db: Session = Depends(get_db)):
    cfg = db.query(PartyCreditConfig).filter(PartyCreditConfig.id == config_id).first()
    if not cfg:
        raise HTTPException(status_code=404, detail="Config not found.")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(cfg, field, value)
    db.commit()
    db.refresh(cfg)
    cfg = db.query(PartyCreditConfig).options(joinedload(PartyCreditConfig.party)).filter(
        PartyCreditConfig.id == config_id
    ).first()
    return _to_response(cfg)


@router.delete("/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_config(config_id: int, db: Session = Depends(get_db)):
    cfg = db.query(PartyCreditConfig).filter(PartyCreditConfig.id == config_id).first()
    if not cfg:
        raise HTTPException(status_code=404, detail="Config not found.")
    if cfg.party_id is None:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete the global default config. Update it instead.",
        )
    db.delete(cfg)
    db.commit()
