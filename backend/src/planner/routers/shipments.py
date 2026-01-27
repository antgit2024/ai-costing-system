from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from ..dependencies import get_db_session
from ..schemas import (
    BomSnapshotRead,
    BomSnapshotRecomputeRequest,
    PaginatedShipmentImportBatchResponse,
    PaginatedShipmentLineResponse,
  ShipmentImportPreviewResponse,
  ShipmentImportExecuteRequest,
    ShipmentExceptionRead,
    ShipmentExceptionRetryRequest,
    ShipmentExceptionRetryResponse,
    ShipmentImportBatchRead,
    ShipmentProfitLinesResponse,
)
from ..services import shipment_import_service


router = APIRouter(prefix="/shipments", tags=["Shipments"])


@router.post("/import", response_model=ShipmentImportBatchRead)
async def import_shipments_xlsx(
    file: UploadFile = File(...),
    export_date: str | None = Form(None),
    requested_by: str | None = Form(None),
    db: Session = Depends(get_db_session),
):
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Empty file")
    batch = shipment_import_service.import_shipment_xlsx(
        db,
        file_name=file.filename or "shipment.xlsx",
        file_bytes=contents,
        export_date=export_date,
        requested_by=requested_by,
    )
    return batch


@router.post("/import/preview", response_model=ShipmentImportPreviewResponse)
async def preview_shipments_xlsx(
    file: UploadFile = File(...),
    export_date: str | None = Form(None),
    requested_by: str | None = Form(None),
    db: Session = Depends(get_db_session),
):
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Empty file")
    return shipment_import_service.preview_shipment_xlsx(
        db,
        file_name=file.filename or "shipment.xlsx",
        file_bytes=contents,
        export_date=export_date,
        requested_by=requested_by,
    )


@router.post("/import/execute", response_model=ShipmentImportBatchRead)
def execute_shipments_from_preview(
    payload: ShipmentImportExecuteRequest,
    db: Session = Depends(get_db_session),
):
    try:
        return shipment_import_service.execute_shipment_xlsx_from_preview(
            db,
            preview_id=payload.preview_id,
            file_name=payload.file_name,
            export_date=payload.export_date,
            requested_by=payload.requested_by,
            mode=getattr(payload, "mode", "2026"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/import-batches", response_model=PaginatedShipmentImportBatchResponse)
def list_import_batches(
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db_session),
):
    total, items = shipment_import_service.list_batches(db, page=page, page_size=page_size)
    return {"total": total, "page": page, "page_size": page_size, "items": items}


@router.get("/import-batches/{batch_id}", response_model=ShipmentImportBatchRead)
def get_import_batch(batch_id: str, db: Session = Depends(get_db_session)):
    batch = shipment_import_service.get_batch(db, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    return batch


@router.get("/exceptions", response_model=list[ShipmentExceptionRead])
def list_exceptions(
    batch_id: str | None = None,
    resolved: bool | None = None,
    limit: int = 200,
    db: Session = Depends(get_db_session),
):
    return shipment_import_service.list_exceptions(db, batch_id=batch_id, resolved=resolved, limit=limit)


@router.post("/exceptions/retry", response_model=ShipmentExceptionRetryResponse)
def retry_exceptions_by_batch(
    payload: ShipmentExceptionRetryRequest,
    db: Session = Depends(get_db_session),
):
    try:
        return shipment_import_service.retry_exceptions_by_batch(
            db,
            batch_id=payload.batch_id,
            only_unresolved=payload.only_unresolved,
            limit=payload.limit,
            operator_id=payload.operator_id,
            reason=payload.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/bom-snapshots", response_model=list[BomSnapshotRead])
def list_bom_snapshots(
    batch_id: str | None = None,
    sku_code: str | None = None,
    shipment_no: str | None = None,
    spec_hash: str | None = None,
    limit: int = 200,
    db: Session = Depends(get_db_session),
):
    return shipment_import_service.list_bom_snapshots(
        db,
        batch_id=batch_id,
        sku_code=sku_code,
        shipment_no=shipment_no,
        spec_hash=spec_hash,
        limit=limit,
    )


@router.post("/bom-snapshots/{snapshot_id}/recompute", response_model=BomSnapshotRead)
def recompute_bom_snapshot(
    snapshot_id: str,
    payload: BomSnapshotRecomputeRequest,
    db: Session = Depends(get_db_session),
):
    try:
        return shipment_import_service.recompute_bom_snapshot(
            db, snapshot_id=snapshot_id, operator_id=payload.operator_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/profit-lines", response_model=ShipmentProfitLinesResponse)
def profit_lines_by_batch(
    batch_id: str,
    limit: int = 2000,
    include_missing: bool = False,
    db: Session = Depends(get_db_session),
):
    try:
        return shipment_import_service.list_profit_lines_by_batch(
            db,
            batch_id=batch_id,
            limit=limit,
            include_missing=include_missing,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/lines", response_model=PaginatedShipmentLineResponse)
def list_shipment_lines(
    page: int = 1,
    page_size: int = 50,
    start: str | None = Query(None, description="ISO datetime, e.g. 2026-01-01T00:00:00Z"),
    end: str | None = Query(None, description="ISO datetime, e.g. 2026-02-01T00:00:00Z"),
    status: str | None = Query(None, description="processed | pending"),
    channel: str | None = None,
    sku_code: str | None = None,
    shipment_no: str | None = None,
    order_no: str | None = None,
    product_link_id: str | None = None,
    db: Session = Depends(get_db_session),
):
    def parse_dt(s: str) -> datetime:
        v = (s or "").strip()
        if v.endswith("Z"):
            v = v[:-1] + "+00:00"
        dt = datetime.fromisoformat(v)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    try:
        payload = shipment_import_service.list_shipment_lines(
            db,
            page=page,
            page_size=page_size,
            start=parse_dt(start) if start else None,
            end=parse_dt(end) if end else None,
            channel=channel,
            sku_code=sku_code,
            shipment_no=shipment_no,
            order_no=order_no,
            product_link_id=product_link_id,
            status=status,
        )
        return payload
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
