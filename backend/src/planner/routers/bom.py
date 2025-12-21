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
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return schemas.BomGenerateResponse(**result)

