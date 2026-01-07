from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ...database import get_db
from .. import schemas
from ..services import bundle_template_service


router = APIRouter(prefix="/bundle-templates", tags=["Bundle Templates"])

def _components_payload(items: list[schemas.BundleTemplateComponent]) -> list[dict]:
    # Pydantic's dict() keeps Decimal; JSON columns (especially SQLite tests) need JSON-serializable primitives.
    return [json.loads(it.json(exclude_none=True)) for it in (items or [])]


def _serialize(t) -> schemas.BundleTemplateRead:
    return schemas.BundleTemplateRead(
        id=t.id,
        code=t.code,
        name=t.name,
        components=[schemas.BundleTemplateComponent(**x) for x in (t.components_json or [])],
        metadata=t.metadata_json or {},
        is_archived=bool(t.is_archived),
        created_at=getattr(t, "created_at", None),
        updated_at=getattr(t, "updated_at", None),
    )


@router.post("", response_model=schemas.BundleTemplateRead, status_code=status.HTTP_201_CREATED)
def create_bundle_template(
    payload: schemas.BundleTemplateCreateRequest,
    db: Session = Depends(get_db),
) -> schemas.BundleTemplateRead:
    try:
        t = bundle_template_service.create_template(
            db,
            name=payload.name,
            components=_components_payload(payload.components),
            metadata=payload.metadata or {},
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _serialize(t)


@router.get("/by-code/{code}", response_model=schemas.BundleTemplateRead, status_code=status.HTTP_200_OK)
def get_bundle_template_by_code(
    code: str,
    db: Session = Depends(get_db),
) -> schemas.BundleTemplateRead:
    try:
        t = bundle_template_service.get_by_code(db, code)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _serialize(t)


@router.get("", response_model=schemas.PaginatedBundleTemplateResponse)
def list_bundle_templates(
    search: Optional[str] = Query(None, max_length=128),
    category: Optional[str] = Query(None, max_length=128),
    tag: Optional[str] = Query(None, max_length=128),
    include_archived: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
) -> schemas.PaginatedBundleTemplateResponse:
    filters = bundle_template_service.BundleTemplateFilters(
        search=search,
        category=category,
        tag=tag,
        include_archived=include_archived,
    )
    total, items = bundle_template_service.list_templates(db, filters=filters, page=page, page_size=page_size)
    return schemas.PaginatedBundleTemplateResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=[_serialize(x) for x in items],
    )


@router.get("/{template_id}", response_model=schemas.BundleTemplateRead, status_code=status.HTTP_200_OK)
def get_bundle_template(template_id: str, db: Session = Depends(get_db)) -> schemas.BundleTemplateRead:
    t = bundle_template_service.get_template(db, template_id, include_archived=True)
    if not t:
        raise HTTPException(status_code=404, detail="套装模板不存在")
    return _serialize(t)


@router.patch("/{template_id}", response_model=schemas.BundleTemplateRead, status_code=status.HTTP_200_OK)
def update_bundle_template(
    template_id: str,
    payload: schemas.BundleTemplateUpdateRequest,
    db: Session = Depends(get_db),
) -> schemas.BundleTemplateRead:
    try:
        t = bundle_template_service.update_template(
            db,
            template_id=template_id,
            name=payload.name,
            components=_components_payload(payload.components) if payload.components is not None else None,
            metadata=payload.metadata,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _serialize(t)


@router.post("/{template_id}/clone", response_model=schemas.BundleTemplateRead, status_code=status.HTTP_201_CREATED)
def clone_bundle_template(
    template_id: str,
    payload: schemas.BundleTemplateCloneRequest,
    db: Session = Depends(get_db),
) -> schemas.BundleTemplateRead:
    try:
        t = bundle_template_service.clone_template(db, template_id=template_id, name=payload.name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _serialize(t)


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_bundle_template(template_id: str, db: Session = Depends(get_db)):
    try:
        bundle_template_service.archive_template(db, template_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


