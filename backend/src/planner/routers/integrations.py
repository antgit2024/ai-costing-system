"""HTTP entrypoints for the generic integrations layer.

Currently exposes:
- POST   /integrations/jackyun/sync/shipments    (trigger a Jackyun shipment pull)
- GET    /integrations/sync-runs                 (list recent sync runs)
- GET    /integrations/sync-runs/{id}            (one run + its dead letters)
- GET    /integrations/dead-letters              (open / retrying queue)
- POST   /integrations/dead-letters/{id}/resolve (operator marks resolved)

Design notes:
- The ``sync_shipments`` job can take seconds-to-minutes per page. We use
  FastAPI's ``BackgroundTasks`` so the HTTP request returns immediately with
  the ``sync_run_id``, and clients poll ``GET /sync-runs/{id}`` for progress.
- Background tasks open their own DB session — request-scoped sessions get
  closed before the task runs.
- First-ever run (watermark empty) defaults to "today 00:00 Asia/Shanghai"
  unless the caller passes an explicit ``start_modify_time``. This matches the
  product decision to NOT backfill history on the first deploy.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ... import database as planner_db
from ...integrations.base import (
    get_watermark,
    list_open_dead_letters,
    resolve_dead_letter,
)
from ...integrations.jackyun import sync_jobs as jackyun_sync_jobs
from .. import models
from ..dependencies import get_db_session
from ..services import jackyun_goods_import_service

router = APIRouter(prefix="/integrations", tags=["Integrations"])


# Asia/Shanghai is UTC+8 year-round; we don't need full tzdata here.
_SHANGHAI_TZ = timezone(timedelta(hours=8))


def _today_start_shanghai_str() -> str:
    """Return today 00:00 in Shanghai as ``YYYY-MM-DD HH:MM:SS`` (Jackyun's format)."""

    today_local = datetime.now(_SHANGHAI_TZ).date()
    return datetime.combine(today_local, time.min).strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------------------
# request / response schemas
# ---------------------------------------------------------------------------


class JackyunShipmentSyncRequest(BaseModel):
    """Body for triggering a Jackyun shipment sync."""

    start_modify_time: Optional[str] = Field(
        None,
        description=(
            "Inclusive lower bound on Jackyun ``modifyTime`` "
            "(``YYYY-MM-DD HH:MM:SS``). Omit + ``use_watermark=true`` to resume "
            "from the last watermark (or today 00:00 Shanghai if none)."
        ),
    )
    end_modify_time: Optional[str] = Field(
        None, description="Inclusive upper bound; omit to pull up to 'now'."
    )
    page_size: int = Field(50, ge=1, le=200)
    order_status_list: Optional[List[int]] = Field(
        None,
        description="Optional Jackyun orderStatus filter (e.g. [7] = 已完成).",
    )
    use_watermark: bool = Field(
        True,
        description=(
            "When true, an empty start_modify_time resumes from the watermark; "
            "after the run completes the watermark advances to the latest modifyTime."
        ),
    )
    wait: bool = Field(
        False,
        description=(
            "When true, run the sync inline and return when finished "
            "(useful for small/manual backfills + tests). When false (default), "
            "the sync runs in a background task and the response returns immediately."
        ),
    )
    triggered_by: Optional[str] = Field(None, max_length=64)


class JackyunRefundSyncRequest(BaseModel):
    """Body for triggering a Jackyun after-sales refund sync.

    Mirrors ``JackyunShipmentSyncRequest`` but maps to
    ``omsapi-business.refund.listrefund``. Time window is the OMS
    ``gmtModified`` range (any header status change updates this column).
    """

    start_modify_time: Optional[str] = Field(
        None,
        description=(
            "Inclusive lower bound on Jackyun refund ``gmtModified`` "
            "(``YYYY-MM-DD HH:MM:SS``). Omit + ``use_watermark=true`` to resume "
            "from the last watermark (or last 7 days if none)."
        ),
    )
    end_modify_time: Optional[str] = Field(
        None, description="Inclusive upper bound; omit to pull up to 'now'."
    )
    page_size: int = Field(50, ge=1, le=100)
    use_watermark: bool = Field(
        True,
        description=(
            "When true, an empty start_modify_time resumes from the watermark; "
            "after the run completes the watermark advances to the latest gmtModified."
        ),
    )
    wait: bool = Field(
        False,
        description=(
            "When true, run the sync inline and return when finished. "
            "When false (default), runs in background and the response returns immediately."
        ),
    )
    triggered_by: Optional[str] = Field(None, max_length=64)


class JackyunGoodsSyncRequest(BaseModel):
    """Body for triggering a Jackyun ERP goods master sync.

    Maps to ``erp.storage.goodslist`` (see DOC/costing/blueprints/
    jackyun_erp_goods_master_sync_backlog.md §10.2 phase F). Time window
    is the ``skuGmtModified`` range (per-spec edits bump it; goods-level
    edits bump goodsGmtModified, but upstream usually sets BOTH on header
    changes so this is the safer cursor).
    """

    start_modify_time: Optional[str] = Field(
        None,
        description=(
            "Inclusive lower bound on Jackyun ``skuGmtModified`` "
            "(``YYYY-MM-DD HH:MM:SS``). Omit + ``use_watermark=true`` to resume "
            "from the last watermark (or last 7 days if none)."
        ),
    )
    end_modify_time: Optional[str] = Field(
        None, description="Inclusive upper bound; omit to pull up to 'now'."
    )
    page_size: int = Field(200, ge=1, le=200)
    use_watermark: bool = Field(
        True,
        description=(
            "When true, an empty start_modify_time resumes from the watermark; "
            "after the run completes the watermark advances to the latest skuGmtModified."
        ),
    )
    wait: bool = Field(
        False,
        description=(
            "When true, run the sync inline and return when finished. "
            "When false (default), runs in background and the response returns immediately."
        ),
    )
    triggered_by: Optional[str] = Field(None, max_length=64)


class SyncRunRead(BaseModel):
    id: str
    source_system: str
    sync_type: str
    api_method: str
    direction: str
    status: str
    total_rows: int
    inserted_rows: int
    updated_rows: int
    skipped_rows: int
    error_rows: int
    cursor_start: Optional[str]
    cursor_end: Optional[str]
    triggered_by: Optional[str]
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    error_message: Optional[str]
    request_params: Dict[str, Any] = Field(default_factory=dict)
    result: Dict[str, Any] = Field(default_factory=dict)


class TriggerSyncResponse(BaseModel):
    sync_run_id: str
    accepted: bool
    mode: str  # "background" | "inline"
    effective_start_modify_time: Optional[str]
    note: Optional[str] = None
    run: Optional[SyncRunRead] = None


class DeadLetterRead(BaseModel):
    id: str
    source_system: str
    api_method: Optional[str]
    record_type: Optional[str]
    stage: str
    sync_run_id: Optional[str]
    external_id: Optional[str]
    external_line_id: Optional[str]
    error_type: Optional[str]
    error_message: Optional[str]
    attempt: int
    status: str
    last_attempt_at: Optional[datetime]
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SyncRunDetailResponse(BaseModel):
    run: SyncRunRead
    dead_letters: List[DeadLetterRead]


class DeadLetterListResponse(BaseModel):
    items: List[DeadLetterRead]
    total: int


class ResolveDeadLetterRequest(BaseModel):
    resolved_by: Optional[str] = Field(None, max_length=64)
    note: Optional[str] = Field(None, max_length=500)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _serialize_run(run: models.IntegrationSyncRun) -> SyncRunRead:
    return SyncRunRead(
        id=run.id,
        source_system=run.source_system,
        sync_type=run.sync_type,
        api_method=run.api_method,
        direction=run.direction,
        status=run.status,
        total_rows=run.total_rows or 0,
        inserted_rows=run.inserted_rows or 0,
        updated_rows=run.updated_rows or 0,
        skipped_rows=run.skipped_rows or 0,
        error_rows=run.error_rows or 0,
        cursor_start=run.cursor_start,
        cursor_end=run.cursor_end,
        triggered_by=run.triggered_by,
        started_at=run.started_at,
        finished_at=run.finished_at,
        error_message=run.error_message,
        request_params=dict(run.request_params_json or {}),
        result=dict(run.result_json or {}),
    )


def _serialize_dead_letter(dl: models.IntegrationDeadLetter) -> DeadLetterRead:
    return DeadLetterRead(
        id=dl.id,
        source_system=dl.source_system,
        api_method=dl.api_method,
        record_type=dl.record_type,
        stage=dl.stage,
        sync_run_id=dl.sync_run_id,
        external_id=dl.external_id,
        external_line_id=dl.external_line_id,
        error_type=dl.error_type,
        error_message=dl.error_message,
        attempt=dl.attempt or 1,
        status=dl.status,
        last_attempt_at=dl.last_attempt_at,
        metadata=dict(dl.metadata_json or {}),
    )


def _resolve_effective_start(
    db: Session,
    *,
    requested_start: Optional[str],
    use_watermark: bool,
) -> tuple[Optional[str], Optional[str]]:
    """Decide which ``start_modify_time`` we'll actually pass to ``sync_shipments``.

    Precedence:
    1. Caller supplied an explicit value -> use it as-is.
    2. ``use_watermark=True`` AND a watermark row exists -> pass None so the job
       resumes from the watermark (we just record the watermark value in ``note``).
    3. Otherwise (first-ever run or watermark disabled) -> default to
       today 00:00 Shanghai so we never accidentally backfill the entire history.

    Returns ``(effective_start, note)`` where ``note`` is a short explanation
    surfaced in the response so operators understand what just happened.
    """

    if requested_start:
        return requested_start.strip(), "explicit start_modify_time provided by caller"

    if use_watermark:
        wm = get_watermark(
            db,
            source_system="jackyun",
            sync_type=jackyun_sync_jobs.SHIPMENT_SYNC_TYPE,
        )
        if wm and wm.watermark_value:
            return None, f"resuming from watermark={wm.watermark_value}"
        # First-ever run with use_watermark on: backfill from today only.
        return _today_start_shanghai_str(), (
            "no watermark yet; defaulting to today 00:00 Shanghai (no historical backfill)"
        )

    return _today_start_shanghai_str(), (
        "use_watermark=false and no start_modify_time; defaulting to today 00:00 Shanghai"
    )


def _run_sync_in_background(
    *,
    start_modify_time: Optional[str],
    end_modify_time: Optional[str],
    page_size: int,
    order_status_list: Optional[List[int]],
    use_watermark: bool,
    triggered_by: Optional[str],
) -> None:
    """Background task entrypoint.

    Opens its own DB session — the request-scoped session has already been
    closed by the time FastAPI runs background tasks.
    """

    if planner_db.SessionLocal is None:
        planner_db.configure_engine()

    db: Session = planner_db.SessionLocal()  # type: ignore[misc]
    try:
        try:
            jackyun_sync_jobs.sync_shipments(
                db,
                start_modify_time=start_modify_time,
                end_modify_time=end_modify_time,
                page_size=page_size,
                order_status_list=order_status_list,
                use_watermark=use_watermark,
                triggered_by=triggered_by or "background",
            )
            # ``sync_shipments`` already commits inside ``run_sync``; this is a
            # belt-and-suspenders flush in case mappers added trailing state.
            db.commit()
        except Exception:
            # ``run_sync`` already persisted the failure on the IntegrationSyncRun
            # row before re-raising, so we just need to make sure the session
            # doesn't leak partial state.
            db.rollback()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/jackyun/sync/shipments",
    response_model=TriggerSyncResponse,
    summary="触发吉客云发货明细同步",
)
def trigger_jackyun_shipment_sync(
    body: JackyunShipmentSyncRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db_session),
) -> TriggerSyncResponse:
    """Trigger one Jackyun shipment pull.

    Default mode (``wait=false``) returns immediately with ``sync_run_id`` and
    runs the sync in a background task; clients poll ``GET /sync-runs/{id}``.
    Pass ``wait=true`` to run inline and get the finished run back in one call.
    """

    effective_start, note = _resolve_effective_start(
        db,
        requested_start=body.start_modify_time,
        use_watermark=body.use_watermark,
    )

    if body.wait:
        sync_run_id = jackyun_sync_jobs.sync_shipments(
            db,
            start_modify_time=effective_start,
            end_modify_time=body.end_modify_time,
            page_size=body.page_size,
            order_status_list=body.order_status_list,
            use_watermark=body.use_watermark,
            triggered_by=body.triggered_by or "manual-inline",
        )
        db.commit()
        run = (
            db.query(models.IntegrationSyncRun)
            .filter(models.IntegrationSyncRun.id == sync_run_id)
            .one()
        )
        return TriggerSyncResponse(
            sync_run_id=sync_run_id,
            accepted=True,
            mode="inline",
            effective_start_modify_time=effective_start,
            note=note,
            run=_serialize_run(run),
        )

    # Background mode: pre-create a "queued" sync_run row so the caller can
    # poll immediately, then hand off the actual work to the background task.
    # This avoids the race where the caller polls before the worker has even
    # started. The background worker creates its OWN sync_run row inside
    # run_sync(), so we report that ID via /sync-runs?triggered_by=... — but
    # for a clean handshake we simply don't pre-create and instead return
    # accepted=true with no id, and clients can list runs by triggered_by.
    background_tasks.add_task(
        _run_sync_in_background,
        start_modify_time=effective_start,
        end_modify_time=body.end_modify_time,
        page_size=body.page_size,
        order_status_list=body.order_status_list,
        use_watermark=body.use_watermark,
        triggered_by=body.triggered_by or "manual-bg",
    )
    return TriggerSyncResponse(
        sync_run_id="",
        accepted=True,
        mode="background",
        effective_start_modify_time=effective_start,
        note=(
            (note or "")
            + " | background dispatched; poll GET /integrations/sync-runs?source_system=jackyun"
        ).strip(" |"),
    )


def _resolve_effective_refund_start(
    db: Session,
    *,
    requested_start: Optional[str],
    use_watermark: bool,
) -> tuple[Optional[str], Optional[str]]:
    """Refund-flavored counterpart of ``_resolve_effective_start``.

    Defaults to *7 days back* (not "today 00:00") on the first-ever run
    because refund volume is far lower than shipments and the upstream
    has a built-in 24h-window constraint that pages well even over a
    week. Skipping a week-of-history would force every operator to use
    --start manually for the very first sync.
    """
    if requested_start:
        return requested_start.strip(), "explicit start_modify_time provided by caller"

    if use_watermark:
        wm = get_watermark(
            db,
            source_system="jackyun",
            sync_type=jackyun_sync_jobs.REFUND_SYNC_TYPE,
        )
        if wm and wm.watermark_value:
            return None, f"resuming from watermark={wm.watermark_value}"

    # First-ever run / watermark disabled — backfill 7 days, mirroring
    # the cron CLI default in ``sync_refunds``.
    default_start = (datetime.now(_SHANGHAI_TZ) - timedelta(days=7)).strftime("%Y-%m-%d 00:00:00")
    return default_start, "no watermark yet; defaulting to last 7 days"


def _run_refund_sync_in_background(
    *,
    start_modify_time: Optional[str],
    end_modify_time: Optional[str],
    page_size: int,
    use_watermark: bool,
    triggered_by: Optional[str],
) -> None:
    if planner_db.SessionLocal is None:
        planner_db.configure_engine()
    db: Session = planner_db.SessionLocal()  # type: ignore[misc]
    try:
        try:
            jackyun_sync_jobs.sync_refunds(
                db,
                start_modify_time=start_modify_time,
                end_modify_time=end_modify_time,
                page_size=page_size,
                use_watermark=use_watermark,
                triggered_by=triggered_by or "background",
            )
            db.commit()
        except Exception:
            db.rollback()
    finally:
        db.close()


def _resolve_effective_goods_start(
    db: Session,
    *,
    requested_start: Optional[str],
    use_watermark: bool,
) -> tuple[Optional[str], Optional[str]]:
    """Goods-flavored counterpart of ``_resolve_effective_refund_start``.

    Defaults to *7 days back* on first run. Excel import (phase C) is
    expected to have already loaded the historical 40-万-row baseline,
    so the daily incremental cursor only needs to catch recent edits.
    """
    if requested_start:
        return requested_start.strip(), "explicit start_modify_time provided by caller"

    if use_watermark:
        wm = get_watermark(
            db,
            source_system="jackyun",
            sync_type=jackyun_sync_jobs.GOODS_SYNC_TYPE,
        )
        if wm and wm.watermark_value:
            return None, f"resuming from watermark={wm.watermark_value}"

    default_start = (datetime.now(_SHANGHAI_TZ) - timedelta(days=7)).strftime("%Y-%m-%d 00:00:00")
    return default_start, "no watermark yet; defaulting to last 7 days"


def _run_goods_sync_in_background(
    *,
    start_modify_time: Optional[str],
    end_modify_time: Optional[str],
    page_size: int,
    use_watermark: bool,
    triggered_by: Optional[str],
) -> None:
    if planner_db.SessionLocal is None:
        planner_db.configure_engine()
    db: Session = planner_db.SessionLocal()  # type: ignore[misc]
    try:
        try:
            jackyun_sync_jobs.sync_goods(
                db,
                start_modify_time=start_modify_time,
                end_modify_time=end_modify_time,
                page_size=page_size,
                use_watermark=use_watermark,
                triggered_by=triggered_by or "background",
            )
            db.commit()
        except Exception:
            db.rollback()
    finally:
        db.close()


@router.post(
    "/jackyun/sync/refunds",
    response_model=TriggerSyncResponse,
    summary="触发吉客云售后退款同步",
)
def trigger_jackyun_refund_sync(
    body: JackyunRefundSyncRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db_session),
) -> TriggerSyncResponse:
    """Trigger one Jackyun refund pull (omsapi-business.refund.listrefund).

    Same shape as the shipment endpoint — see ``trigger_jackyun_shipment_sync``
    for the wait/background semantics. Status updates land in
    ``after_sales_lines`` (source_system='jackyun'); pre-existing Excel rows
    for the same after_sales_no are tagged ``superseded_by_jackyun``
    (never deleted).
    """

    effective_start, note = _resolve_effective_refund_start(
        db,
        requested_start=body.start_modify_time,
        use_watermark=body.use_watermark,
    )

    if body.wait:
        sync_run_id = jackyun_sync_jobs.sync_refunds(
            db,
            start_modify_time=effective_start,
            end_modify_time=body.end_modify_time,
            page_size=body.page_size,
            use_watermark=body.use_watermark,
            triggered_by=body.triggered_by or "manual-inline",
        )
        db.commit()
        run = (
            db.query(models.IntegrationSyncRun)
            .filter(models.IntegrationSyncRun.id == sync_run_id)
            .one()
        )
        return TriggerSyncResponse(
            sync_run_id=sync_run_id,
            accepted=True,
            mode="inline",
            effective_start_modify_time=effective_start,
            note=note,
            run=_serialize_run(run),
        )

    background_tasks.add_task(
        _run_refund_sync_in_background,
        start_modify_time=effective_start,
        end_modify_time=body.end_modify_time,
        page_size=body.page_size,
        use_watermark=body.use_watermark,
        triggered_by=body.triggered_by or "manual-bg",
    )
    return TriggerSyncResponse(
        sync_run_id="",
        accepted=True,
        mode="background",
        effective_start_modify_time=effective_start,
        note=(
            (note or "")
            + " | background dispatched; poll GET /integrations/sync-runs?source_system=jackyun&sync_type=refund_pull"
        ).strip(" |"),
    )


@router.post(
    "/jackyun/sync/goods",
    response_model=TriggerSyncResponse,
    summary="触发吉客云 ERP 货品档案同步",
)
def trigger_jackyun_goods_sync(
    body: JackyunGoodsSyncRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db_session),
) -> TriggerSyncResponse:
    """Trigger one Jackyun ERP goods master pull (``erp.storage.goodslist``).

    Same shape as the shipment / refund endpoints — see
    ``trigger_jackyun_shipment_sync`` for the wait/background semantics.
    Updates land in ``sku_master`` with ``metadata.source='jackyun_erp_goods_api'``;
    pre-existing rows from Excel import keep their physical columns intact
    except for those API explicitly overwrites (narrow overwrite).

    Watermark cursor: ``skuGmtModified`` per spec. First-ever run defaults
    to last 7 days (Excel import phase C is expected to have loaded the
    historical baseline already).
    """

    effective_start, note = _resolve_effective_goods_start(
        db,
        requested_start=body.start_modify_time,
        use_watermark=body.use_watermark,
    )

    if body.wait:
        sync_run_id = jackyun_sync_jobs.sync_goods(
            db,
            start_modify_time=effective_start,
            end_modify_time=body.end_modify_time,
            page_size=body.page_size,
            use_watermark=body.use_watermark,
            triggered_by=body.triggered_by or "manual-inline",
        )
        db.commit()
        run = (
            db.query(models.IntegrationSyncRun)
            .filter(models.IntegrationSyncRun.id == sync_run_id)
            .one()
        )
        return TriggerSyncResponse(
            sync_run_id=sync_run_id,
            accepted=True,
            mode="inline",
            effective_start_modify_time=effective_start,
            note=note,
            run=_serialize_run(run),
        )

    background_tasks.add_task(
        _run_goods_sync_in_background,
        start_modify_time=effective_start,
        end_modify_time=body.end_modify_time,
        page_size=body.page_size,
        use_watermark=body.use_watermark,
        triggered_by=body.triggered_by or "manual-bg",
    )
    return TriggerSyncResponse(
        sync_run_id="",
        accepted=True,
        mode="background",
        effective_start_modify_time=effective_start,
        note=(
            (note or "")
            + " | background dispatched; poll GET /integrations/sync-runs?source_system=jackyun&sync_type=goods_pull"
        ).strip(" |"),
    )


@router.get(
    "/sync-runs",
    response_model=List[SyncRunRead],
    summary="列出最近的同步运行记录",
)
def list_sync_runs(
    source_system: Optional[str] = Query(None, max_length=32),
    sync_type: Optional[str] = Query(None, max_length=64),
    status: Optional[str] = Query(None, max_length=32),
    triggered_by: Optional[str] = Query(None, max_length=64),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db_session),
) -> List[SyncRunRead]:
    q = db.query(models.IntegrationSyncRun)
    if source_system:
        q = q.filter(models.IntegrationSyncRun.source_system == source_system)
    if sync_type:
        q = q.filter(models.IntegrationSyncRun.sync_type == sync_type)
    if status:
        q = q.filter(models.IntegrationSyncRun.status == status)
    if triggered_by:
        q = q.filter(models.IntegrationSyncRun.triggered_by == triggered_by)
    # ``created_at`` is non-null (TimestampMixin) so we use it as the primary
    # sort key for cross-DB portability — SQLite doesn't support NULLS LAST.
    q = q.order_by(models.IntegrationSyncRun.created_at.desc()).limit(limit)
    return [_serialize_run(r) for r in q.all()]


@router.get(
    "/sync-runs/{sync_run_id}",
    response_model=SyncRunDetailResponse,
    summary="查看单次同步运行详情（含死信摘要）",
)
def get_sync_run(
    sync_run_id: str,
    db: Session = Depends(get_db_session),
) -> SyncRunDetailResponse:
    run = (
        db.query(models.IntegrationSyncRun)
        .filter(models.IntegrationSyncRun.id == sync_run_id)
        .one_or_none()
    )
    if run is None:
        raise HTTPException(status_code=404, detail="sync_run_not_found")

    dl_rows = (
        db.query(models.IntegrationDeadLetter)
        .filter(models.IntegrationDeadLetter.sync_run_id == sync_run_id)
        .order_by(models.IntegrationDeadLetter.created_at.desc())
        .all()
    )
    return SyncRunDetailResponse(
        run=_serialize_run(run),
        dead_letters=[_serialize_dead_letter(dl) for dl in dl_rows],
    )


@router.get(
    "/dead-letters",
    response_model=DeadLetterListResponse,
    summary="列出待处理的死信记录",
)
def list_dead_letters(
    source_system: Optional[str] = Query(None, max_length=32),
    record_type: Optional[str] = Query(None, max_length=64),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db_session),
) -> DeadLetterListResponse:
    rows = list_open_dead_letters(
        db,
        source_system=source_system,
        record_type=record_type,
        limit=limit,
    )
    return DeadLetterListResponse(
        items=[_serialize_dead_letter(r) for r in rows],
        total=len(rows),
    )


@router.post(
    "/dead-letters/{dead_letter_id}/resolve",
    summary="标记死信为已处理",
)
def resolve_dead_letter_endpoint(
    dead_letter_id: str,
    body: ResolveDeadLetterRequest,
    db: Session = Depends(get_db_session),
) -> Dict[str, Any]:
    ok = resolve_dead_letter(
        db,
        dead_letter_id=dead_letter_id,
        resolved_by=body.resolved_by,
        note=body.note,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="dead_letter_not_found")
    db.commit()
    return {"resolved": True, "dead_letter_id": dead_letter_id}


# ---------------------------------------------------------------------------
# Jackyun ERP goods master — Excel import (3-step wizard)
#
# Blueprint:  DOC/costing/blueprints/jackyun_erp_goods_master_sync_backlog.md §10.2 (C)
# Service:    src/planner/services/jackyun_goods_import_service.py
#
# Flow:
#   1. POST .../goods/import-xlsx/inspect    [sync, ~100ms]     → column mapping preview
#   2. POST .../goods/import-xlsx/dry-run    [BG, ~60-120s]     → diff report (no DB write)
#   3. POST .../goods/import-xlsx/commit     [BG, ~5-30min]     → real upsert in 5000-row batches
#
# Long-running 2/3 use BackgroundTasks + IntegrationSyncRun for progress polling
# via the existing GET /integrations/sync-runs/{id} endpoint.
# ---------------------------------------------------------------------------


def _parse_mapping_form_field(raw: Optional[str]) -> Dict[int, str]:
    """Parse the ``mapping`` form field (JSON-encoded ``{col_idx_str: target_field}``)."""
    if not raw:
        return {}
    import json

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"invalid mapping JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="mapping must be a JSON object")
    out: Dict[int, str] = {}
    for k, v in data.items():
        try:
            ki = int(k)
        except (TypeError, ValueError):
            continue
        if isinstance(v, str) and v:
            out[ki] = v
    return out


@router.post(
    "/jackyun/goods/import-xlsx/inspect",
    summary="吉客云货品档案导入 - Step 1: 读表头返回列识别",
)
async def jackyun_goods_import_inspect(
    file: UploadFile = File(...),
) -> Dict[str, Any]:
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="empty_file")
    result = jackyun_goods_import_service.inspect_xlsx(contents)
    if result.error:
        raise HTTPException(status_code=400, detail=result.error)
    return result.to_dict()


def _run_goods_import_job(
    *,
    sync_run_id: str,
    file_bytes: bytes,
    mapping: Dict[int, str],
    requested_by: Optional[str],
    commit: bool,
    batch_size: int = 5000,
) -> None:
    """Background job: open a fresh DB session, run dry_run / commit, update IntegrationSyncRun."""
    if planner_db.SessionLocal is None:
        raise RuntimeError("SessionLocal not initialized")
    db: Session = planner_db.SessionLocal()  # type: ignore[misc]
    try:
        run = db.query(models.IntegrationSyncRun).filter(models.IntegrationSyncRun.id == sync_run_id).one()
        run.status = "running"
        run.started_at = datetime.now(timezone.utc)
        db.commit()

        report = jackyun_goods_import_service._execute(
            db,
            file_bytes=file_bytes,
            mapping=mapping,
            requested_by=requested_by,
            commit=commit,
            batch_size=batch_size,
        )

        run.status = "success"
        run.finished_at = datetime.now(timezone.utc)
        run.total_rows = report.total_rows
        run.inserted_rows = report.new_rows
        run.updated_rows = report.updated_rows
        run.skipped_rows = report.skipped_no_barcode + report.duplicate_in_file
        run.error_rows = len(report.errors)
        run.result_json = report.to_dict()
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        run = db.query(models.IntegrationSyncRun).filter(models.IntegrationSyncRun.id == sync_run_id).one_or_none()
        if run is not None:
            run.status = "failed"
            run.finished_at = datetime.now(timezone.utc)
            run.error_message = f"{type(exc).__name__}: {exc}"
            db.commit()
    finally:
        db.close()


def _create_goods_import_run(
    db: Session,
    *,
    sync_type: str,
    request_params: Dict[str, Any],
    triggered_by: Optional[str],
) -> models.IntegrationSyncRun:
    run = models.IntegrationSyncRun(
        source_system="jackyun",
        sync_type=sync_type,
        api_method="xlsx.import.goods_master",
        direction="pull",
        status="pending",
        request_params_json=request_params,
        triggered_by=triggered_by,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


@router.post(
    "/jackyun/goods/import-xlsx/dry-run",
    summary="吉客云货品档案导入 - Step 2: Dry-run 预演（不写库）",
)
async def jackyun_goods_import_dry_run(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    mapping: Optional[str] = Form(None, description="JSON {col_idx: target_field}; 空则用 auto_mapping"),
    requested_by: Optional[str] = Form(None),
    db: Session = Depends(get_db_session),
) -> Dict[str, Any]:
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="empty_file")
    mapping_dict = _parse_mapping_form_field(mapping)
    if not mapping_dict:
        inspect = jackyun_goods_import_service.inspect_xlsx(contents)
        if inspect.error:
            raise HTTPException(status_code=400, detail=inspect.error)
        if inspect.missing_required:
            raise HTTPException(
                status_code=400,
                detail=f"missing_required_fields: {inspect.missing_required}",
            )
        mapping_dict = inspect.auto_mapping

    run = _create_goods_import_run(
        db,
        sync_type="goods_import_xlsx_dry_run",
        request_params={
            "filename": file.filename,
            "size_bytes": len(contents),
            "mapping_size": len(mapping_dict),
            "mode": "dry_run",
        },
        triggered_by=requested_by,
    )
    background_tasks.add_task(
        _run_goods_import_job,
        sync_run_id=run.id,
        file_bytes=contents,
        mapping=mapping_dict,
        requested_by=requested_by,
        commit=False,
    )
    return {
        "sync_run_id": run.id,
        "status": run.status,
        "mode": "dry_run",
        "poll_url": f"/integrations/sync-runs/{run.id}",
    }


@router.post(
    "/jackyun/goods/import-xlsx/commit",
    summary="吉客云货品档案导入 - Step 3: 正式导入（5000 行/批）",
)
async def jackyun_goods_import_commit(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    mapping: Optional[str] = Form(None),
    requested_by: Optional[str] = Form(None),
    batch_size: int = Form(5000, ge=100, le=20000),
    db: Session = Depends(get_db_session),
) -> Dict[str, Any]:
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="empty_file")
    mapping_dict = _parse_mapping_form_field(mapping)
    if not mapping_dict:
        inspect = jackyun_goods_import_service.inspect_xlsx(contents)
        if inspect.error:
            raise HTTPException(status_code=400, detail=inspect.error)
        if inspect.missing_required:
            raise HTTPException(
                status_code=400,
                detail=f"missing_required_fields: {inspect.missing_required}",
            )
        mapping_dict = inspect.auto_mapping

    run = _create_goods_import_run(
        db,
        sync_type="goods_import_xlsx_commit",
        request_params={
            "filename": file.filename,
            "size_bytes": len(contents),
            "mapping_size": len(mapping_dict),
            "batch_size": batch_size,
            "mode": "commit",
        },
        triggered_by=requested_by,
    )
    background_tasks.add_task(
        _run_goods_import_job,
        sync_run_id=run.id,
        file_bytes=contents,
        mapping=mapping_dict,
        requested_by=requested_by,
        commit=True,
        batch_size=batch_size,
    )
    return {
        "sync_run_id": run.id,
        "status": run.status,
        "mode": "commit",
        "poll_url": f"/integrations/sync-runs/{run.id}",
    }
