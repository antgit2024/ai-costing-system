from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..dependencies import get_db_session
from ..schemas import (
    AfterSalesExceptionRead,
    AfterSalesImportBatchRead,
    AfterSalesLineRead,
    PaginatedAfterSalesImportBatchResponse,
)
from ..services import after_sales_import_service


router = APIRouter(prefix="/after-sales", tags=["AfterSales"])


@router.post("/import", response_model=AfterSalesImportBatchRead)
async def import_after_sales_xlsx(
    file: UploadFile = File(...),
    export_date: str | None = Form(None),
    requested_by: str | None = Form(None),
    db: Session = Depends(get_db_session),
):
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Empty file")
    batch = after_sales_import_service.import_after_sales_xlsx(
        db,
        file_name=file.filename or "after_sales.xlsx",
        file_bytes=contents,
        export_date=export_date,
        requested_by=requested_by,
    )
    return batch


@router.get("/import-batches", response_model=PaginatedAfterSalesImportBatchResponse)
def list_import_batches(
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db_session),
):
    total, items = after_sales_import_service.list_batches(db, page=page, page_size=page_size)
    return {"total": total, "page": page, "page_size": page_size, "items": items}


@router.get("/import-batches/{batch_id}", response_model=AfterSalesImportBatchRead)
def get_import_batch(batch_id: str, db: Session = Depends(get_db_session)):
    batch = after_sales_import_service.get_batch(db, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    return batch


@router.get("/lines", response_model=list[AfterSalesLineRead])
def list_lines(
    batch_id: str | None = None,
    limit: int = 200,
    db: Session = Depends(get_db_session),
):
    return after_sales_import_service.list_lines(db, batch_id=batch_id, limit=limit)


@router.get("/exceptions", response_model=list[AfterSalesExceptionRead])
def list_exceptions(
    batch_id: str | None = None,
    resolved: bool | None = None,
    limit: int = 200,
    db: Session = Depends(get_db_session),
):
    return after_sales_import_service.list_exceptions(db, batch_id=batch_id, resolved=resolved, limit=limit)

