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

