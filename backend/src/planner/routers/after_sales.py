from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..dependencies import get_db_session
from ..schemas import (
    AfterSalesExceptionRead,
    AfterSalesImportBatchRead,
    AfterSalesLineRead,
    AfterSalesModelOptionsResponse,
    AfterSalesReasonOptionsResponse,
    PaginatedAfterSalesLineResponse,
    PaginatedAfterSalesImportBatchResponse,
)
from ..services import after_sales_import_service


router = APIRouter(prefix="/after-sales", tags=["AfterSales"])


def _parse_dt(s: str | None) -> datetime | None:
    if s is None:
        return None
    v = (s or "").strip()
    if not v:
        return None
    if v.endswith("Z"):
        v = v[:-1] + "+00:00"
    dt = datetime.fromisoformat(v)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


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


@router.get("/lines/search", response_model=PaginatedAfterSalesLineResponse)
def search_lines(
    start: str | None = None,
    end: str | None = None,
    channel: str | None = None,
    sku_code: str | None = None,
    product_link_id: str | None = None,
    reason: str | None = None,
    model_code: str | None = None,
    page: int = 1,
    page_size: int = 50,
    db: Session = Depends(get_db_session),
):
    total, items = after_sales_import_service.search_lines(
        db,
        start=_parse_dt(start),
        end=_parse_dt(end),
        channel=channel,
        sku_code=sku_code,
        product_link_id=product_link_id,
        reason=reason,
        model_code=model_code,
        page=page,
        page_size=page_size,
    )
    return {"total": total, "page": page, "page_size": page_size, "items": items}


@router.get("/reason-options", response_model=AfterSalesReasonOptionsResponse)
def reason_options(
    start: str | None = None,
    end: str | None = None,
    channel: str | None = None,
    sku_code: str | None = None,
    model_code: str | None = None,
    limit: int = 200,
    db: Session = Depends(get_db_session),
):
    items = after_sales_import_service.reason_options(
        db,
        start=_parse_dt(start),
        end=_parse_dt(end),
        channel=channel,
        sku_code=sku_code,
        model_code=model_code,
        limit=limit,
    )
    return {"items": items}


@router.get("/model-options", response_model=AfterSalesModelOptionsResponse)
def model_options(
    start: str | None = None,
    end: str | None = None,
    channel: str | None = None,
    sku_code: str | None = None,
    reason: str | None = None,
    limit: int = 200,
    db: Session = Depends(get_db_session),
):
    items = after_sales_import_service.model_options(
        db,
        start=_parse_dt(start),
        end=_parse_dt(end),
        channel=channel,
        sku_code=sku_code,
        reason=reason,
        limit=limit,
    )
    return {"items": items}


@router.get("/exceptions", response_model=list[AfterSalesExceptionRead])
def list_exceptions(
    batch_id: str | None = None,
    resolved: bool | None = None,
    limit: int = 200,
    db: Session = Depends(get_db_session),
):
    return after_sales_import_service.list_exceptions(db, batch_id=batch_id, resolved=resolved, limit=limit)

