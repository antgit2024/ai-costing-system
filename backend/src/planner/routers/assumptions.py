from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from .. import models, schemas
from ..dependencies import get_db_session

router = APIRouter(tags=["Input Assumptions"])


@router.get("/assumptions", response_model=List[schemas.AssumptionRead])
def list_assumptions(
    initiative_id: Optional[str] = None,
    assumption_type: Optional[str] = Query(None, alias="type"),
    db: Session = Depends(get_db_session),
):
    query = db.query(models.InputAssumption)
    if initiative_id:
        query = query.filter(models.InputAssumption.initiative_id == initiative_id)
    if assumption_type:
        query = query.filter(models.InputAssumption.type == assumption_type)
    return query.order_by(models.InputAssumption.effective_date.desc()).all()


@router.post(
    "/assumptions",
    response_model=schemas.AssumptionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_assumption(payload: schemas.AssumptionCreate, db: Session = Depends(get_db_session)):
    initiative = db.get(models.CostInitiative, payload.initiative_id)
    if not initiative or initiative.is_archived:
        raise HTTPException(status_code=400, detail="Initiative does not exist")

    existing = (
        db.query(models.InputAssumption)
        .filter(
            models.InputAssumption.initiative_id == payload.initiative_id,
            models.InputAssumption.type == payload.type,
            models.InputAssumption.effective_date == payload.effective_date,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="Assumption version already exists")

    data = payload.dict()
    metadata = data.pop("metadata", {})
    assumption = models.InputAssumption(**data, metadata_json=metadata)
    db.add(assumption)
    db.commit()
    db.refresh(assumption)
    return assumption


@router.get("/assumptions/latest", response_model=List[schemas.AssumptionLatestResponse])
def latest_assumptions(
    initiative_id: str = Query(..., description="Filter assumptions by initiative"),
    assumption_type: Optional[str] = Query(None, alias="type"),
    db: Session = Depends(get_db_session),
):
    query = db.query(models.InputAssumption).filter(
        models.InputAssumption.initiative_id == initiative_id
    )
    if assumption_type:
        latest = (
            query.filter(models.InputAssumption.type == assumption_type)
            .order_by(models.InputAssumption.effective_date.desc())
            .first()
        )
        return [
            schemas.AssumptionLatestResponse(
                initiative_id=initiative_id,
                type=assumption_type,
                latest=latest,
            )
        ]

    types = [row[0] for row in query.with_entities(models.InputAssumption.type).distinct()]
    responses: List[schemas.AssumptionLatestResponse] = []
    for assumption_type in types:
        latest = (
            query.filter(models.InputAssumption.type == assumption_type)
            .order_by(models.InputAssumption.effective_date.desc())
            .first()
        )
        responses.append(
            schemas.AssumptionLatestResponse(
                initiative_id=initiative_id,
                type=assumption_type,
                latest=latest,
            )
        )
    return responses


@router.get("/assumptions/{assumption_id}", response_model=schemas.AssumptionRead)
def get_assumption(assumption_id: str, db: Session = Depends(get_db_session)):
    assumption = db.get(models.InputAssumption, assumption_id)
    if not assumption:
        raise HTTPException(status_code=404, detail="Assumption not found")
    return assumption
