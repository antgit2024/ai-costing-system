from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import schemas
from ...database import get_db
from ..services import bom_generation_service


router = APIRouter(prefix="/bom", tags=["Dynamic BOM"])


@router.post(
    "/generate",
    response_model=schemas.BomGenerateResponse,
    status_code=status.HTTP_200_OK,
)
def generate_bom(
    payload: schemas.BomGenerateRequest,
    db: Session = Depends(get_db),
) -> schemas.BomGenerateResponse:
    try:
        result = bom_generation_service.generate_bom(
            db,
            spec_text=payload.spec_text,
            model_version_id=payload.model_version_id,
            sku_code=payload.sku_code,
            quantity=payload.quantity,
            include_disabled_variants=bool(getattr(payload, "include_disabled_variants", False)),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return schemas.BomGenerateResponse(**result)


@router.post(
    "/generate-bundle",
    response_model=schemas.BomGenerateBundleResponse,
    status_code=status.HTTP_200_OK,
)
def generate_bom_bundle(
    payload: schemas.BomGenerateBundleRequest,
    db: Session = Depends(get_db),
) -> schemas.BomGenerateBundleResponse:
    """
    Generate BOM for a bundle/set (组合装/套装) by aggregating multiple explicit components.
    NOTE: component sizes are NOT parsed from spec_text; they must be provided explicitly.
    """
    try:
        result = bom_generation_service.generate_bom_bundle(
            db,
            model_version_id=payload.model_version_id,
            sku_code=payload.sku_code,
            components=[c.dict() for c in payload.components],
            include_disabled_variants=bool(payload.include_disabled_variants),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return schemas.BomGenerateBundleResponse(**result)


@router.post(
    "/generate-multi-bundle",
    response_model=schemas.BomGenerateMultiBundleResponse,
    status_code=status.HTTP_200_OK,
)
def generate_bom_multi_bundle(
    payload: schemas.BomGenerateMultiBundleRequest,
    db: Session = Depends(get_db),
) -> schemas.BomGenerateMultiBundleResponse:
    """
    Generate BOM for a multi-model bundle/set:
    - each component can choose its own model_version_id.
    - sizes are explicit, not parsed from spec_text.
    """
    try:
        result = bom_generation_service.generate_bom_multi_bundle(
            db,
            sku_code=payload.sku_code,
            components=[c.dict() for c in payload.components],
            include_disabled_variants=bool(payload.include_disabled_variants),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return schemas.BomGenerateMultiBundleResponse(**result)


@router.post(
    "/generate-by-spec",
    response_model=schemas.BomGenerateResponse,
    status_code=status.HTTP_200_OK,
)
def generate_bom_by_spec(
    payload: schemas.BomGenerateBySpecRequest,
    db: Session = Depends(get_db),
) -> schemas.BomGenerateResponse:
    """
    Generate BOM by customer-facing spec_text token(s).
    Currently supports:
    - BUNDLE:<code> (bundle template code)
    """
    try:
        result = bom_generation_service.generate_bom_by_spec(
            db,
            spec_text=payload.spec_text,
            sku_code=payload.sku_code,
            include_disabled_variants=bool(payload.include_disabled_variants),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return schemas.BomGenerateResponse(**result)

