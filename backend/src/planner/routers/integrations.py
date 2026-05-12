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

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
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
