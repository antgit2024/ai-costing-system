from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ...database import get_db
from .. import schemas
from ..services import bundle_template_service


router = APIRouter(prefix="/bundle-templates", tags=["Bundle Templates"])


@router.post("", response_model=schemas.BundleTemplateRead, status_code=status.HTTP_201_CREATED)
def create_bundle_template(
    payload: schemas.BundleTemplateCreateRequest,
    db: Session = Depends(get_db),
) -> schemas.BundleTemplateRead:
    try:
        t = bundle_template_service.create_template(
            db,
            name=payload.name,
            components=[c.dict(exclude_none=True) for c in payload.components],
            metadata=payload.metadata or {},
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return schemas.BundleTemplateRead(
        id=t.id,
        code=t.code,
        name=t.name,
        components=[schemas.BundleTemplateComponent(**x) for x in (t.components_json or [])],
        metadata=t.metadata_json or {},
        is_archived=bool(t.is_archived),
    )


@router.get("/by-code/{code}", response_model=schemas.BundleTemplateRead, status_code=status.HTTP_200_OK)
def get_bundle_template_by_code(
    code: str,
    db: Session = Depends(get_db),
) -> schemas.BundleTemplateRead:
    try:
        t = bundle_template_service.get_by_code(db, code)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return schemas.BundleTemplateRead(
        id=t.id,
        code=t.code,
        name=t.name,
        components=[schemas.BundleTemplateComponent(**x) for x in (t.components_json or [])],
        metadata=t.metadata_json or {},
        is_archived=bool(t.is_archived),
    )


