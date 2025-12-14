from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from .. import models, schemas
from ..dependencies import PaginationParams, get_db_session

router = APIRouter(tags=["Initiatives"])


@router.get("/initiatives", response_model=schemas.PaginatedInitiativeResponse)
def list_initiatives(
    status_filter: Optional[str] = Query(None, alias="status"),
    owner_id: Optional[str] = None,
    tag: Optional[str] = None,
    pagination: PaginationParams = Depends(),
    db: Session = Depends(get_db_session),
):
    query = db.query(models.CostInitiative).filter(models.CostInitiative.is_archived.is_(False))

    if status_filter:
        query = query.filter(models.CostInitiative.status == status_filter)
    if owner_id:
        query = query.filter(models.CostInitiative.owner_id == owner_id)
    if tag:
        query = query.filter(models.CostInitiative.tags.contains([tag]))

    total = query.count()
    items = (
        query.order_by(models.CostInitiative.created_at.desc())
        .offset((pagination.page - 1) * pagination.page_size)
        .limit(pagination.page_size)
        .all()
    )

    return schemas.PaginatedInitiativeResponse(
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
        items=items,
    )


@router.post(
    "/initiatives",
    response_model=schemas.InitiativeRead,
    status_code=status.HTTP_201_CREATED,
)
def create_initiative(
    payload: schemas.InitiativeCreate,
    db: Session = Depends(get_db_session),
):
    existing = (
        db.query(models.CostInitiative)
        .filter(models.CostInitiative.code == payload.code)
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="Initiative code already exists")

    initiative = models.CostInitiative(**payload.dict())
    db.add(initiative)
    db.commit()
    db.refresh(initiative)
    return initiative


@router.get("/initiatives/{initiative_id}", response_model=schemas.InitiativeRead)
def get_initiative(initiative_id: str, db: Session = Depends(get_db_session)):
    initiative = db.get(models.CostInitiative, initiative_id)
    if not initiative or initiative.is_archived:
        raise HTTPException(status_code=404, detail="Initiative not found")
    return initiative


@router.put("/initiatives/{initiative_id}", response_model=schemas.InitiativeRead)
def update_initiative(
    initiative_id: str,
    payload: schemas.InitiativeUpdate,
    db: Session = Depends(get_db_session),
):
    initiative = db.get(models.CostInitiative, initiative_id)
    if not initiative or initiative.is_archived:
        raise HTTPException(status_code=404, detail="Initiative not found")

    update_data = payload.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(initiative, key, value)
    db.commit()
    db.refresh(initiative)
    return initiative


@router.delete(
    "/initiatives/{initiative_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_initiative(initiative_id: str, db: Session = Depends(get_db_session)):
    initiative = db.get(models.CostInitiative, initiative_id)
    if not initiative or initiative.is_archived:
        raise HTTPException(status_code=404, detail="Initiative not found")

    initiative.is_archived = True
    db.commit()
    return None
