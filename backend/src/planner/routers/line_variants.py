from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import models, schemas
from ...database import get_db
from ..services import audit_service, line_variant_service


router = APIRouter(tags=["Line Variants"])


@router.get(
    "/product-model-versions/{version_id}/line-variants",
    response_model=List[schemas.LineVariantDetailRead],
)
def list_line_variants(
    version_id: str,
    base_line_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    variants = line_variant_service.list_variants(
        db,
        version_id=version_id,
        base_line_id=base_line_id,
    )
    return [_serialize_variant(v) for v in variants]


@router.post(
    "/product-model-versions/{version_id}/line-variants",
    response_model=schemas.LineVariantDetailRead,
    status_code=status.HTTP_201_CREATED,
)
def create_line_variant(
    version_id: str,
    payload: schemas.LineVariantCreateRequest,
    db: Session = Depends(get_db),
):
    if payload.version_id != version_id:
        raise HTTPException(status_code=400, detail="payload.version_id 与路径参数不一致")
    try:
        variant = line_variant_service.create_variant(
            db,
            version_id=version_id,
            base_line_id=payload.base_line_id,
            priority=payload.priority,
            enabled=payload.enabled,
            action=payload.action,
            stop_on_hit=payload.stop_on_hit,
            notes=payload.notes,
            conditions=payload.conditions.dict(exclude_none=True),
            metadata=payload.metadata,
            items=[item.dict(by_alias=True, exclude_none=True) for item in payload.items],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit_service.log_audit_event(
        db,
        target_type="line_variant",
        target_id=variant.id,
        action="create",
        actor_id=payload.operator_id or "system",
        payload=payload.dict(exclude_none=True),
    )
    db.commit()
    return _serialize_variant(variant)


@router.get(
    "/line-variants/{variant_id}",
    response_model=schemas.LineVariantDetailRead,
)
def get_line_variant(
    variant_id: str,
    db: Session = Depends(get_db),
):
    variant = _get_variant_or_404(db, variant_id)
    return _serialize_variant(variant)


@router.patch(
    "/line-variants/{variant_id}",
    response_model=schemas.LineVariantDetailRead,
)
def update_line_variant(
    variant_id: str,
    payload: schemas.LineVariantUpdateRequest,
    db: Session = Depends(get_db),
):
    variant = _get_variant_or_404(db, variant_id)
    try:
        updated = line_variant_service.update_variant(
            db,
            variant,
            base_line_id=payload.base_line_id,
            priority=payload.priority,
            enabled=payload.enabled,
            action=payload.action,
            stop_on_hit=payload.stop_on_hit,
            notes=payload.notes,
            conditions=payload.conditions.dict(exclude_none=True) if payload.conditions else None,
            metadata=payload.metadata,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit_service.log_audit_event(
        db,
        target_type="line_variant",
        target_id=variant_id,
        action="update",
        actor_id=payload.operator_id or "system",
        payload=payload.dict(exclude_none=True),
    )
    db.commit()
    return _serialize_variant(updated)


@router.delete(
    "/line-variants/{variant_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_line_variant(
    variant_id: str,
    db: Session = Depends(get_db),
):
    variant = _get_variant_or_404(db, variant_id)
    line_variant_service.delete_variant(db, variant)
    audit_service.log_audit_event(
        db,
        target_type="line_variant",
        target_id=variant_id,
        action="delete",
        actor_id="system",
        payload={},
    )
    db.commit()


@router.get(
    "/line-variants/{variant_id}/items",
    response_model=List[schemas.LineVariantItemRead],
)
def list_variant_items(
    variant_id: str,
    db: Session = Depends(get_db),
):
    variant = _get_variant_or_404(db, variant_id)
    return _serialize_items(variant.items or [])


@router.put(
    "/line-variants/{variant_id}/items",
    response_model=schemas.LineVariantDetailRead,
)
def replace_variant_items(
    variant_id: str,
    payload: schemas.LineVariantItemsReplaceRequest,
    db: Session = Depends(get_db),
):
    variant = _get_variant_or_404(db, variant_id)
    updated = line_variant_service.replace_items(
        db,
        variant,
        items=[item.dict(by_alias=True, exclude_none=True) for item in payload.items],
    )
    audit_service.log_audit_event(
        db,
        target_type="line_variant",
        target_id=variant_id,
        action="replace_items",
        actor_id="system",
        payload=payload.dict(exclude_none=True),
    )
    db.commit()
    return _serialize_variant(updated)


def _get_variant_or_404(db: Session, variant_id: str) -> models.ProductModelLineVariant:
    variant = line_variant_service.get_variant(db, variant_id)
    if not variant:
        raise HTTPException(status_code=404, detail="Line variant not found")
    return variant


def _serialize_variant(variant: models.ProductModelLineVariant) -> schemas.LineVariantDetailRead:
    return schemas.LineVariantDetailRead(
        id=variant.id,
        version_id=variant.version_id,
        base_line_id=variant.base_line_id,
        priority=variant.priority,
        enabled=variant.enabled,
        action=variant.action,
        stop_on_hit=variant.stop_on_hit,
        notes=variant.notes,
        conditions=variant.conditions_json or {},
        metadata=variant.metadata_json or {},
        items=_serialize_items(list(variant.items or [])),
        created_at=variant.created_at,
        updated_at=variant.updated_at,
    )


def _serialize_items(items: List[models.ProductModelLineVariantItem]) -> List[schemas.LineVariantItemRead]:
    result: List[schemas.LineVariantItemRead] = []
    for item in items:
        result.append(
            schemas.LineVariantItemRead(
                id=item.id,
                sequence_order=item.sequence_order,
                material_kind=item.material_kind,
                material_ref_id=item.material_ref_id,
                material_code=item.material_code,
                material_name=item.material_name,
                unit_of_measure=item.unit_of_measure,
                calculation_method=item.calculation_method,
                base_quantity=item.base_quantity,
                fixed_quantity=item.fixed_quantity,
                coverage_ratio=item.coverage_ratio,
                loss_rate=item.loss_rate,
                metadata=item.metadata_json or {},
                created_at=item.created_at,
                updated_at=item.updated_at,
            )
        )
    return result

