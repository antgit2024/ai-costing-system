from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import models, schemas
from ..dependencies import get_db_session, require_admin_key


router = APIRouter(prefix="/taxonomy", tags=["Taxonomy"])


DEFAULT_SCOPE_OPTIONS = ["布艺", "画艺"]
UNIVERSAL_SCOPE = "*"


def _normalize_scopes(scopes: List[str]) -> List[str]:
    cleaned: list[str] = []
    for s in scopes or []:
        v = str(s).strip()
        if not v:
            continue
        cleaned.append(v)
    # de-dup while preserving order
    seen = set()
    out: list[str] = []
    for v in cleaned:
        if v in seen:
            continue
        seen.add(v)
        out.append(v)
    return out


class TaxonomyItemCreateRequest(BaseModel):
    domain: str = Field(..., max_length=64)
    name: str = Field(..., max_length=128)
    scopes: List[str] = Field(..., min_items=1)
    is_active: bool = True
    sort_order: int = 0
    source: str = Field("local", max_length=32)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @validator("scopes")
    def _validate_scopes(cls, v: List[str]):
        vv = _normalize_scopes(v)
        if not vv:
            raise ValueError("scopes is required")
        return vv


class TaxonomyItemUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, max_length=128)
    scopes: Optional[List[str]] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None

    @validator("scopes")
    def _validate_scopes(cls, v: Optional[List[str]]):
        if v is None:
            return v
        vv = _normalize_scopes(v)
        if not vv:
            raise ValueError("scopes is required")
        return vv


class TaxonomyMappingCreateRequest(BaseModel):
    domain: str = Field(..., max_length=64)
    external_system: str = Field("yida", max_length=32)
    external_value: str = Field(..., max_length=255)
    taxonomy_item_id: str = Field(..., max_length=36)


class TaxonomyMappingUpdateRequest(BaseModel):
    taxonomy_item_id: str = Field(..., max_length=36)


@router.get("/scope-options", response_model=schemas.TaxonomyScopeOptionsResponse)
def get_scope_options() -> schemas.TaxonomyScopeOptionsResponse:
    """
    Frontend helper:
    - default scope tags: 布艺 / 画艺
    - universal tag: *
    """
    return schemas.TaxonomyScopeOptionsResponse(
        universal_scope=UNIVERSAL_SCOPE,
        default_scopes=DEFAULT_SCOPE_OPTIONS,
    )


@router.get("/items", response_model=schemas.TaxonomyItemListResponse)
def list_taxonomy_items(
    domain: str = Query(..., max_length=64),
    include_inactive: bool = Query(False),
    db: Session = Depends(get_db_session),
) -> schemas.TaxonomyItemListResponse:
    q = db.query(models.TaxonomyItem).filter(
        models.TaxonomyItem.domain == domain,
        models.TaxonomyItem.is_archived.is_(False),
    )
    if not include_inactive:
        q = q.filter(models.TaxonomyItem.is_active.is_(True))
    items = q.order_by(models.TaxonomyItem.sort_order.asc(), models.TaxonomyItem.name.asc()).all()
    return schemas.TaxonomyItemListResponse(items=[schemas.TaxonomyItemRead.from_orm(it) for it in items])


@router.post("/items", response_model=schemas.TaxonomyItemRead, status_code=status.HTTP_201_CREATED)
def create_taxonomy_item(
    payload: TaxonomyItemCreateRequest,
    db: Session = Depends(get_db_session),
    _: None = Depends(require_admin_key),
) -> schemas.TaxonomyItemRead:
    item = models.TaxonomyItem(
        domain=payload.domain.strip(),
        name=payload.name.strip(),
        scopes_json=_normalize_scopes(payload.scopes),
        is_active=payload.is_active,
        sort_order=payload.sort_order,
        source=payload.source.strip() or "local",
        metadata_json=payload.metadata or {},
        is_archived=False,
    )
    db.add(item)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Taxonomy item already exists (domain+name)")
    db.refresh(item)
    return schemas.TaxonomyItemRead.from_orm(item)


@router.patch("/items/{item_id}", response_model=schemas.TaxonomyItemRead)
def update_taxonomy_item(
    item_id: str,
    payload: TaxonomyItemUpdateRequest,
    db: Session = Depends(get_db_session),
    _: None = Depends(require_admin_key),
) -> schemas.TaxonomyItemRead:
    item = db.get(models.TaxonomyItem, item_id)
    if not item or item.is_archived:
        raise HTTPException(status_code=404, detail="Taxonomy item not found")
    if payload.name is not None:
        item.name = payload.name.strip()
    if payload.scopes is not None:
        item.scopes_json = _normalize_scopes(payload.scopes)
    if payload.is_active is not None:
        item.is_active = payload.is_active
    if payload.sort_order is not None:
        item.sort_order = payload.sort_order
    if payload.metadata is not None:
        item.metadata_json = payload.metadata
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Taxonomy item conflict (domain+name)")
    db.refresh(item)
    return schemas.TaxonomyItemRead.from_orm(item)


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_taxonomy_item(
    item_id: str,
    db: Session = Depends(get_db_session),
    _: None = Depends(require_admin_key),
):
    item = db.get(models.TaxonomyItem, item_id)
    if not item or item.is_archived:
        raise HTTPException(status_code=404, detail="Taxonomy item not found")
    item.is_archived = True
    db.commit()
    return None


@router.get("/mappings", response_model=schemas.TaxonomyMappingListResponse)
def list_taxonomy_mappings(
    domain: str = Query(..., max_length=64),
    external_system: str = Query("yida", max_length=32),
    db: Session = Depends(get_db_session),
) -> schemas.TaxonomyMappingListResponse:
    items = (
        db.query(models.TaxonomyMapping)
        .filter(models.TaxonomyMapping.domain == domain, models.TaxonomyMapping.external_system == external_system)
        .order_by(models.TaxonomyMapping.external_value.asc())
        .all()
    )
    return schemas.TaxonomyMappingListResponse(items=[schemas.TaxonomyMappingRead.from_orm(it) for it in items])


@router.post("/mappings", response_model=schemas.TaxonomyMappingRead, status_code=status.HTTP_201_CREATED)
def create_taxonomy_mapping(
    payload: TaxonomyMappingCreateRequest,
    db: Session = Depends(get_db_session),
    _: None = Depends(require_admin_key),
) -> schemas.TaxonomyMappingRead:
    item = db.get(models.TaxonomyItem, payload.taxonomy_item_id)
    if not item or item.is_archived:
        raise HTTPException(status_code=404, detail="Taxonomy item not found")
    mapping = models.TaxonomyMapping(
        domain=payload.domain.strip(),
        external_system=payload.external_system.strip() or "yida",
        external_value=payload.external_value.strip(),
        taxonomy_item_id=item.id,
    )
    db.add(mapping)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Mapping already exists (domain+system+value)")
    db.refresh(mapping)
    return schemas.TaxonomyMappingRead.from_orm(mapping)


@router.patch("/mappings/{mapping_id}", response_model=schemas.TaxonomyMappingRead)
def update_taxonomy_mapping(
    mapping_id: str,
    payload: TaxonomyMappingUpdateRequest,
    db: Session = Depends(get_db_session),
    _: None = Depends(require_admin_key),
) -> schemas.TaxonomyMappingRead:
    mapping = db.get(models.TaxonomyMapping, mapping_id)
    if not mapping:
        raise HTTPException(status_code=404, detail="Mapping not found")
    item = db.get(models.TaxonomyItem, payload.taxonomy_item_id)
    if not item or item.is_archived:
        raise HTTPException(status_code=404, detail="Taxonomy item not found")
    mapping.taxonomy_item_id = item.id
    db.commit()
    db.refresh(mapping)
    return schemas.TaxonomyMappingRead.from_orm(mapping)


@router.delete("/mappings/{mapping_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_taxonomy_mapping(
    mapping_id: str,
    db: Session = Depends(get_db_session),
    _: None = Depends(require_admin_key),
):
    mapping = db.get(models.TaxonomyMapping, mapping_id)
    if not mapping:
        raise HTTPException(status_code=404, detail="Mapping not found")
    db.delete(mapping)
    db.commit()
    return None


