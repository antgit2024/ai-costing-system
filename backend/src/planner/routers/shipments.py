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
    ShipmentLineComputeSnapshotRequest,
    ShipmentLineComputeSnapshotResponse,
    ShipmentLineClearSnapshotsRequest,
    ShipmentLineClearSnapshotsResponse,
    ShipmentExceptionRead,
    ShipmentExceptionRetryRequest,
    ShipmentExceptionRetryResponse,
    ShipmentImportBatchRead,
    ShipmentProfitLinesResponse,
    ShipmentCostingResultRead,
    ShipmentInventoryDeductionLineRead,
    ShipmentProcessCostLineRead,
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
    sku_code: str | None = None,
    channel: str | None = None,
    spec_text: str | None = None,
    limit: int = 200,
    db: Session = Depends(get_db_session),
):
    return shipment_import_service.list_exceptions(
        db,
        batch_id=batch_id,
        resolved=resolved,
        sku_code=sku_code,
        channel=channel,
        spec_text=spec_text,
        limit=limit,
    )


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


@router.get("/bom-snapshots/{snapshot_id}", response_model=BomSnapshotRead)
def get_bom_snapshot(snapshot_id: str, db: Session = Depends(get_db_session)):
    snap = shipment_import_service.get_bom_snapshot(db, snapshot_id=snapshot_id)
    if not snap:
        raise HTTPException(status_code=404, detail="BOM快照不存在")
    return snap


@router.get("/lines/{shipment_line_id}/costing", response_model=ShipmentCostingResultRead)
def get_costing_result(shipment_line_id: str, db: Session = Depends(get_db_session)):
    row = shipment_import_service.get_costing_result(db, shipment_line_id=shipment_line_id)
    if not row:
        raise HTTPException(status_code=404, detail="计价结果不存在")
    return row


@router.get("/lines/{shipment_line_id}/deductions", response_model=list[ShipmentInventoryDeductionLineRead])
def list_deduction_lines(shipment_line_id: str, db: Session = Depends(get_db_session)):
    return shipment_import_service.list_deduction_lines(db, shipment_line_id=shipment_line_id)


@router.get("/lines/{shipment_line_id}/processes", response_model=list[ShipmentProcessCostLineRead])
def list_process_cost_lines(shipment_line_id: str, db: Session = Depends(get_db_session)):
    return shipment_import_service.list_process_cost_lines(db, shipment_line_id=shipment_line_id)


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
    batch_id: str | None = Query(None, description="导入批次ID（发货作业中心用）"),
    status: str | None = Query(None, description="processed | pending"),
    channel: str | None = None,
    sku_code: str | None = None,
    shipment_no: str | None = None,
    order_no: str | None = None,
    product_link_id: str | None = None,
    spec_text: str | None = None,
    bound_target_kind: str | None = Query(None, description="any | model | bundle"),
    bound_model_code: str | None = None,
    bound_version_label: str | None = None,
    bundle_preset_selector: str | None = Query(None, description="套装二级 selector（例如 AE）"),
    unresolved_reason: str | None = Query(None, description="例如：SKU_NOT_BOUND / SPEC_EMPTY / BOM_GENERATION_FAILED"),
    suspected_mismatch: bool | None = Query(None, description="仅疑似绑错（软提示）"),
    include_issue_hints: bool | None = Query(None, description="是否返回“疑似绑错/尺寸异常”等核对提示（较慢）"),
    ready_to_generate: bool | None = Query(None, description="仅返回“可生成快照”的待处理行（本批次常用）"),
    need_rebuild_snapshot: bool | None = Query(None, description="仅返回“需要覆盖重算快照”的已处理行（绑定变更/清空后常用）"),
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
            batch_id=batch_id,
            channel=channel,
            sku_code=sku_code,
            shipment_no=shipment_no,
            order_no=order_no,
            product_link_id=product_link_id,
            status=status,
            spec_text=spec_text,
            bound_target_kind=bound_target_kind,
            bound_model_code=bound_model_code,
            bound_version_label=bound_version_label,
            bundle_preset_selector=bundle_preset_selector,
            unresolved_reason=unresolved_reason,
            suspected_mismatch=suspected_mismatch,
            include_issue_hints=include_issue_hints,
            ready_to_generate=ready_to_generate,
            need_rebuild_snapshot=need_rebuild_snapshot,
        )
        return payload
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/lines/{shipment_line_id}/compute-snapshot", response_model=ShipmentLineComputeSnapshotResponse)
def compute_snapshot_for_shipment_line(
    shipment_line_id: str,
    payload: ShipmentLineComputeSnapshotRequest,
    db: Session = Depends(get_db_session),
):
    try:
        return shipment_import_service.compute_snapshot_for_shipment_line(
            db,
            shipment_line_id=shipment_line_id,
            operator_id=payload.operator_id,
            overwrite=bool(payload.overwrite),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/lines/clear-snapshots", response_model=ShipmentLineClearSnapshotsResponse)
def clear_shipment_line_snapshots(
    payload: ShipmentLineClearSnapshotsRequest,
    db: Session = Depends(get_db_session),
):
    try:
        return shipment_import_service.clear_shipment_line_snapshots(
            db,
            shipment_line_ids=payload.shipment_line_ids,
            operator_id=payload.operator_id,
            reason=payload.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
