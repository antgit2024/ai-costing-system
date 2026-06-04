from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import text
from sqlalchemy.orm import Session

from .. import models
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
    ShipmentLineResolveRequest,
    ShipmentLineResolveResponse,
    ShipmentLineBulkResolveRequest,
    ShipmentLineBulkResolveResponse,
    ShipmentLinesAutoResolveRequest,
    ShipmentLinesAutoResolvePreviewResponse,
    ShipmentLinesAutoResolveExecuteResponse,
    ShipmentLinesRecentStatsResponse,
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
        preview_id = (payload.preview_id or "").strip()
        if not preview_id:
            raise ValueError("preview_id 不能为空")
        if not shipment_import_service.preview_cache_exists(preview_id):
            raise ValueError("预览缓存文件不存在，请重新预览上传")

        # Create (or reuse) a batch quickly; real execution is handled by the worker loop.
        batch = db.query(models.ShipmentImportBatch).filter(models.ShipmentImportBatch.file_hash == preview_id).first()
        if batch and batch.status in ("success", "queued"):
            return batch
        if batch and batch.status == "processing":
            # If it looks stale (no progress + old heartbeat), re-queue for worker retry.
            no_progress = (
                int(batch.total_rows or 0) == 0
                and int(batch.inserted_rows or 0) == 0
                and int(batch.skipped_rows or 0) == 0
                and int(batch.exception_rows or 0) == 0
            )
            idle_seconds = None
            if no_progress:
                try:
                    idle_seconds = db.execute(
                        text("select extract(epoch from (now() - updated_at)) from shipment_import_batches where id = :id"),
                        {"id": batch.id},
                    ).scalar()
                except Exception:
                    idle_seconds = None

            if no_progress and idle_seconds is not None and float(idle_seconds) > 300:
                batch.status = "queued"
                db.commit()
                db.refresh(batch)
            return batch

        if not batch:
            batch = models.ShipmentImportBatch(
                file_name=payload.file_name or f"preview:{preview_id}.xlsx",
                file_hash=preview_id,
                export_date=payload.export_date,
                requested_by=payload.requested_by,
                status="queued",
            )
            db.add(batch)
            db.flush()
            batch.result_json = {
                "mode": getattr(payload, "mode", "2026"),
                "process_snapshots": bool(getattr(payload, "process_snapshots", True)),
            }
        else:
            # retry for non-success batches (typically failed)
            batch.file_name = payload.file_name or batch.file_name
            batch.export_date = payload.export_date
            batch.requested_by = payload.requested_by
            batch.status = "queued"
            batch.total_rows = 0
            batch.inserted_rows = 0
            batch.skipped_rows = 0
            batch.exception_rows = 0
            batch.warnings_json = []
            batch.result_json = {
                "mode": getattr(payload, "mode", "2026"),
                "process_snapshots": bool(getattr(payload, "process_snapshots", True)),
            }

        db.commit()
        db.refresh(batch)
        return batch
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


@router.post(
    "/lines/{shipment_line_id}/resolve",
    response_model=ShipmentLineResolveResponse,
    summary="一键决策(Issue 29): 绑模型+设治理+出快照, 一次调用搞定",
)
def resolve_shipment_line(
    shipment_line_id: str,
    payload: ShipmentLineResolveRequest,
    db: Session = Depends(get_db_session),
):
    """Replaces frontend planner.ts::resolveShipmentLine orchestration.

    - action='adopt': bind SkuMaster→model, set governance=auto_bound,
      compute BOM snapshot (overwrite=True).
    - action='mark_long_tail' / 'defer_modeling': set governance only;
      snapshot is intentionally NOT forced (long-tail snapshot picks up
      the strategy rate on next worker pass; pending_model has no model
      to snapshot against).

    Returns a structured ``steps`` audit so UI can show "step X failed"
    without losing the partial successes.
    """
    try:
        return shipment_import_service.resolve_shipment_line(
            db,
            shipment_line_id=shipment_line_id,
            action=payload.action,
            model_id=payload.model_id,
            operator_id=payload.operator_id,
            note=payload.note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post(
    "/lines/bulk-resolve",
    response_model=ShipmentLineBulkResolveResponse,
    summary="一键批量决策(Issue 29 follow-up): 一次 POST 处理 N 条 shipment_line_id",
)
def bulk_resolve_shipment_lines(
    payload: ShipmentLineBulkResolveRequest,
    db: Session = Depends(get_db_session),
):
    """Server-side fanout for the PendingTab batch toolbar.

    Each row is processed via resolve_shipment_line (per-row commit/rollback),
    so a single bad row never tanks the rest. Default mode is "best effort"
    (``stop_on_first_error=false``) — set true if the caller wants to bail
    on first failure.

    Performance vs frontend ``Promise.all + concurrency 8``:
      - 100 rows × ~250ms each via the new path: ~25s ÷ N parallel workers
        on the server, with one network RTT instead of 100. UI gets a single
        progress message instead of mid-stream chatter.
    """
    return shipment_import_service.bulk_resolve_shipment_lines(
        db,
        items=[item.dict() for item in payload.items],
        operator_id=payload.operator_id,
        note=payload.note,
        stop_on_first_error=payload.stop_on_first_error,
    )


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


# ----------------------------------------------------------------------------
# Auto-resolve pending shipment lines
# (powers 「📦 业务管理 > 🚚 发货管理 > 🔴 待处理」 「⚡ 一键自动绑定」 banner)
#
# These endpoints port the legacy "/costing/sku-master > 自动识别" workflow
# (sku_master_service.auto_bind_*) into the new biz-friendly page, with two
# important enhancements:
#   1. Recognition is scoped to SKUs that actually appear in recent pending
#      shipment lines, not the full ~78k unbound SkuMaster pool.
#   2. After binding, BomSnapshot is generated immediately for the affected
#      lines and their SKU_NOT_BOUND exception rows are auto-resolved, so
#      operators see lines disappear from the queue without waiting for the
#      worker to come back around.
# ----------------------------------------------------------------------------


@router.post("/lines/auto-resolve/preview", response_model=ShipmentLinesAutoResolvePreviewResponse)
def auto_resolve_pending_shipment_lines_preview(
    payload: ShipmentLinesAutoResolveRequest,
    db: Session = Depends(get_db_session),
):
    return shipment_import_service.auto_resolve_pending_shipment_lines_preview(
        db,
        days=payload.days,
        limit=payload.limit,
        sku_codes=payload.sku_codes,
    )


@router.post("/lines/auto-resolve/execute", response_model=ShipmentLinesAutoResolveExecuteResponse)
def auto_resolve_pending_shipment_lines_execute(
    payload: ShipmentLinesAutoResolveRequest,
    db: Session = Depends(get_db_session),
):
    return shipment_import_service.auto_resolve_pending_shipment_lines_execute(
        db,
        days=payload.days,
        limit=payload.limit,
        sku_codes=payload.sku_codes,
        requested_by=payload.requested_by,
    )


# ----------------------------------------------------------------------------
# Recent stats (page header strip for 「📦 业务管理 → 🚚 发货管理 → 🔴 待处理」)
# Lightweight (~50ms) — safe to call on every page load.
# ----------------------------------------------------------------------------


@router.get("/lines/recent-stats", response_model=ShipmentLinesRecentStatsResponse)
def get_recent_shipment_line_stats(
    hours: int = Query(24, ge=1, le=24 * 30, description="时间窗(小时), 最近 hours 内新进的发货行"),
    latest_runs_limit: int = Query(5, ge=1, le=50, description="返回最近多少次同步 run"),
    db: Session = Depends(get_db_session),
):
    return shipment_import_service.get_recent_shipment_line_stats(
        db,
        hours=hours,
        latest_runs_limit=latest_runs_limit,
    )


# ----------------------------------------------------------------------------
# Manual catch-up for "已绑定但缺快照" rows (Issue 0.0i 配套手动按钮)
# - Background sweep covers the last 14 days automatically.
# - This endpoint lets operators sweep a wider window (default 90 days,
#   max 365) on demand from the 「待处理」 Tab "🔁 回写快照" button.
# - Reuses the same sweep logic, so 0 new code paths to test.
# ----------------------------------------------------------------------------


@router.post("/lines/regenerate-snapshots")
def regenerate_bound_pending_snapshots(
    lookback_days: int = Query(
        90, ge=1, le=365, description="回写时间窗(天)。默认 90, 月底盘点选 60-90"
    ),
    limit: int = Query(
        2000, ge=1, le=10000, description="单次最多处理多少行"
    ),
    db: Session = Depends(get_db_session),
):
    """Operator-initiated catch-up: scan all pending ShipmentLines whose
    SKU has an active binding but no BomSnapshot, within ``lookback_days``,
    and try to compute snapshots in batch.

    Returns the same shape as the background sweep so the UI can show a
    one-line summary toast.
    """
    return shipment_import_service.sweep_bound_lines_missing_snapshot(
        db,
        lookback_days=lookback_days,
        limit=limit,
    )
