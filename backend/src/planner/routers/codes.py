from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...database import get_db
from .. import schemas
from ..services import code_generator_service

router = APIRouter(prefix="/codes", tags=["codes"])


@router.post("/next", response_model=schemas.CodeGenerateResponse)
def generate_next_code(payload: schemas.CodeGenerateRequest, db: Session = Depends(get_db)):
    try:
        code = code_generator_service.allocate_code(db, prefix=payload.prefix, width=payload.width)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return schemas.CodeGenerateResponse(code=code)


@router.post("/random", response_model=schemas.RandomCodeGenerateResponse)
def generate_random_code(payload: schemas.RandomCodeGenerateRequest, db: Session = Depends(get_db)):
    try:
        code = code_generator_service.generate_random_code(db, kind=payload.kind, length=payload.length)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return schemas.RandomCodeGenerateResponse(code=code)




