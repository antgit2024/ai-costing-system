"""End-to-end Jackyun sync entrypoints.

Each function:
- creates a ``IntegrationSyncRun`` via ``run_sync(...)``
- reads & advances the matching ``integration_sync_watermarks`` row
- pages through the upstream API
- archives raw payloads via ``ctx.archive_record(...)`` (with schema_version)
- maps payloads into business tables; mapper failures land in
  ``integration_dead_letters`` instead of aborting the whole batch

These are intended to be called from CLI scripts, an APScheduler job, or
ad-hoc maintenance routes.

Upstream constraint we honor here: Jackyun's ``wms.order.query-info.page``
caps the ``startModifyTime ~ endModifyTime`` window at **24 hours** per
call (otherwise it returns sub-code ``0050030002``). When the caller asks
for a wider range — explicitly or implicitly via watermark — we transparently
split the request into per-day windows so the caller never has to think
about it.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Iterable, Iterator, List, Optional, Tuple

from sqlalchemy.orm import Session

from ..base import (
    advance_watermark_if_newer,
    get_watermark_value,
    record_dead_letter,
    run_sync,
)
from ..base.errors import IntegrationError
from .api import shipment as shipment_api
from .client import JackyunClient, build_default_client
from .mappers import shipment as shipment_mapper

SHIPMENT_SCHEMA_VERSION = "jackyun.shipment.v1"
SHIPMENT_SYNC_TYPE = "shipment_pull"
SHIPMENT_WATERMARK_FIELD = "modifyTime"

_SHANGHAI_TZ = timezone(timedelta(hours=8))
_TS_FORMAT = "%Y-%m-%d %H:%M:%S"
# Upstream rejects windows wider than this. Keep one second of safety margin
# (so we don't tickle off-by-one edge cases inside Jackyun's own validator).
_MAX_WINDOW_SECONDS = 24 * 3600 - 1
# When advancing the watermark, never push it past ``now - this`` so that
# records uploaded with even a few seconds of upstream delay are not
# permanently skipped on the next incremental run.
_WATERMARK_SAFETY_BUFFER_SECONDS = 300


def _payload_max_timestamp(payload: dict) -> Optional[str]:
    """Pick the most recent business-time string out of a Jackyun shipment payload.

    The ``query-info.page`` payload does NOT contain a top-level
    ``modifyTime``, so we walk a fallback list. None of these are perfect
    proxies for "last modified", but they are monotonic enough for
    watermark advancement when combined with the safety buffer below.
    """
    for key in ("modifyTime", "gmtModified", "sendTime", "finishTime", "gmtCreate"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _compute_watermark_target(
    *,
    max_payload_time: Optional[str],
    last_window_end: Optional[str],
    now_dt: Optional[datetime] = None,
) -> Optional[str]:
    """Decide the next watermark value for an incremental shipment_pull run.

    Rules (in order of precedence):
    1. Prefer the highest payload-side timestamp we observed in the run —
       that's the strongest signal that "everything modified up to time T
       has been seen".
    2. Otherwise (e.g. payload had no usable timestamps, or the run was
       empty) fall back to the upper bound of the last window we scanned;
       that still moves the cursor forward so we don't re-scan the same
       window forever.
    3. Cap whichever we picked at ``now - safety_buffer`` (Shanghai time).
       Without this cap the cursor can jump to ``23:59:59`` of the
       requested end-of-day and silently skip records uploaded in the
       intervening minutes.
    """
    candidates = [t for t in (max_payload_time, last_window_end) if t]
    if not candidates:
        return None
    raw_target = max(candidates)

    now = now_dt or datetime.now(_SHANGHAI_TZ)
    safe_now = (now - timedelta(seconds=_WATERMARK_SAFETY_BUFFER_SECONDS))
    safe_now_str = safe_now.astimezone(_SHANGHAI_TZ).strftime(_TS_FORMAT)
    return min(raw_target, safe_now_str)


def _parse_ts(value: str) -> datetime:
    """Parse a Jackyun-style ``YYYY-MM-DD HH:MM:SS`` string as Shanghai time."""
    return datetime.strptime(value.strip(), _TS_FORMAT).replace(tzinfo=_SHANGHAI_TZ)


def _format_ts(dt: datetime) -> str:
    return dt.astimezone(_SHANGHAI_TZ).strftime(_TS_FORMAT)


def _today_end_shanghai() -> datetime:
    today = datetime.now(_SHANGHAI_TZ).date()
    return datetime.combine(today, time(23, 59, 59)).replace(tzinfo=_SHANGHAI_TZ)


def _iter_24h_windows(
    start_str: Optional[str], end_str: Optional[str]
) -> Iterator[Tuple[str, str]]:
    """Yield ``(window_start, window_end)`` pairs no wider than 24h.

    Behavior:
    - If both bounds are missing, yield exactly one (None, None) tuple so the
      caller can fall back to upstream defaults.
    - If only ``start`` is given, the window extends to ``min(start+24h, now)``,
      then keeps stepping forward until we reach the current moment.
    - If only ``end`` is given, the window starts at ``end - 24h``.
    - If both are given, we slice ``[start, end]`` into ``<=24h`` chunks.

    Each window is half-open in spirit: the next window starts at
    ``previous_end + 1 second`` to avoid double-counting boundary records.
    """

    if not start_str and not end_str:
        yield None, None  # type: ignore[misc]
        return

    if start_str:
        start = _parse_ts(start_str)
    else:
        # Treat a lone end as "give me the 24h ending at ``end``".
        end_dt = _parse_ts(end_str)  # type: ignore[arg-type]
        start = end_dt - timedelta(seconds=_MAX_WINDOW_SECONDS)

    if end_str:
        hard_end = _parse_ts(end_str)
    else:
        hard_end = _today_end_shanghai()

    if hard_end < start:
        return

    cursor = start
    while cursor <= hard_end:
        win_end = min(cursor + timedelta(seconds=_MAX_WINDOW_SECONDS), hard_end)
        yield _format_ts(cursor), _format_ts(win_end)
        if win_end >= hard_end:
            return
        cursor = win_end + timedelta(seconds=1)


def sync_shipments(
    db: Session,
    *,
    start_modify_time: Optional[str] = None,
    end_modify_time: Optional[str] = None,
    page_size: int = 50,
    order_status_list: Optional[Iterable[int]] = None,
    triggered_by: Optional[str] = "manual",
    use_watermark: bool = True,
    client: Optional[JackyunClient] = None,
) -> str:
    """Pull Jackyun shipments and upsert them into ``shipment_lines``.

    Behavior:
    - If ``start_modify_time`` is omitted and ``use_watermark=True``, we read
      the last successful watermark and resume from there.
    - On success the watermark is advanced to the latest modifyTime seen.
    - Per-record mapper exceptions are recorded in ``integration_dead_letters``
      and do not abort the run.

    Returns the ``IntegrationSyncRun.id`` for caller diagnostics.
    """

    use_client = client or build_default_client()

    effective_start = start_modify_time
    start_resolution: str
    if effective_start is None and use_watermark:
        effective_start = get_watermark_value(
            db, source_system="jackyun", sync_type=SHIPMENT_SYNC_TYPE
        )
        start_resolution = (
            "watermark-resume" if effective_start else "watermark-empty"
        )
    else:
        start_resolution = "explicit" if effective_start else "no-watermark-disabled"

    # Defense in depth: this endpoint REJECTS calls without at least one
    # of (startModifyTime / startGmtCreate / startFinishTime), returning
    # sub-code ``0050030002 创建时间/完成时间/修改时间必传其一``. The HTTP route
    # already defaults to "today 00:00 Shanghai", but cron jobs / CLI / unit
    # tests can land here with None — fall back to the same default so a
    # missing watermark NEVER hits the upstream as a bare request.
    if effective_start is None:
        effective_start = datetime.now(_SHANGHAI_TZ).strftime("%Y-%m-%d 00:00:00")
        if start_resolution in ("watermark-empty", "no-watermark-disabled"):
            start_resolution = f"default-today ({start_resolution})"

    effective_end = end_modify_time

    request_params = {
        "start_modify_time": effective_start,
        "end_modify_time": effective_end,
        "page_size": page_size,
        "order_status_list": list(order_status_list) if order_status_list else None,
        "use_watermark": bool(use_watermark),
        "start_resolution": start_resolution,
    }

    windows: List[Tuple[Optional[str], Optional[str]]] = list(
        _iter_24h_windows(effective_start, effective_end)
    )
    request_params["effective_windows"] = [
        {"start": w[0], "end": w[1]} for w in windows
    ]

    with run_sync(
        db=db,
        source_system="jackyun",
        sync_type=SHIPMENT_SYNC_TYPE,
        api_method=shipment_api.DEFAULT_LIST_API,
        request_params=request_params,
        direction="pull",
        triggered_by=triggered_by,
        cursor_start=effective_start,
    ) as ctx:
        batch = shipment_mapper.get_or_create_jackyun_batch(db, sync_run_id=ctx.sync_run_id)
        # Track the highest *payload-side* timestamp we've seen across the
        # whole run. Initialized to None (NOT effective_start) so that
        # payloads with stale business-time values can't accidentally hold
        # the watermark back to the window's lower bound.
        max_payload_time: Optional[str] = None
        last_window_end: Optional[str] = None
        try:
            for win_start, win_end in windows:
                last_window_end = win_end or last_window_end
                for page_rows in shipment_api.iter_shipments(
                    use_client,
                    page_size=page_size,
                    start_modify_time=win_start,
                    end_modify_time=win_end,
                    order_status_list=order_status_list,
                    sync_run_id=ctx.sync_run_id,
                    db=db,
                ):
                    for payload in page_rows:
                        order_no = (payload.get("orderNo") or "").strip()
                        if not order_no:
                            ctx.inc_skipped()
                            continue
                        try:
                            archived = ctx.archive_record(
                                record_type="shipment",
                                external_id=order_no,
                                payload=payload,
                                schema_version=SHIPMENT_SCHEMA_VERSION,
                            )
                            rows, inserted, updated = shipment_mapper.upsert_shipment_from_payload(
                                db,
                                payload=payload,
                                batch=batch,
                                source_payload_id=archived.id,
                            )
                            ctx.inc_total(len(rows))
                            ctx.inc_inserted(inserted)
                            ctx.inc_updated(updated)
                            ctx.cursor_end = order_no
                            payload_ts = _payload_max_timestamp(payload)
                            if payload_ts and (max_payload_time is None or payload_ts > max_payload_time):
                                max_payload_time = payload_ts
                        except Exception as exc:  # noqa: BLE001 - mapper isolation
                            ctx.inc_errored()
                            record_dead_letter(
                                db,
                                source_system="jackyun",
                                api_method=shipment_api.DEFAULT_LIST_API,
                                record_type="shipment",
                                stage="mapper",
                                sync_run_id=ctx.sync_run_id,
                                external_id=order_no,
                                error=exc,
                                payload_snapshot={"shipment": payload},
                                metadata={"schema_version": SHIPMENT_SCHEMA_VERSION},
                            )
        except IntegrationError:
            raise
        finally:
            # NOTE: 必须用 'success' (不是 'succeeded')，与 shipment_import_service /
            # shipment_import_worker / after_sales_import_service / 前端 BatchWorkbench
            # 的契约对齐。改动前请同时修改这些地方。
            batch.status = "success"
            batch.export_date = batch.export_date or ctx.cursor_end or ""

        watermark_target = _compute_watermark_target(
            max_payload_time=max_payload_time,
            last_window_end=last_window_end,
        )
        if use_watermark and watermark_target:
            advance_watermark_if_newer(
                db,
                source_system="jackyun",
                sync_type=SHIPMENT_SYNC_TYPE,
                watermark_field=SHIPMENT_WATERMARK_FIELD,
                new_value=watermark_target,
                sync_run_id=ctx.sync_run_id,
                cursor_extra={
                    "page_size": int(page_size),
                    "window_count": len(windows),
                },
            )
            ctx.cursor_end = watermark_target
        elif effective_end:
            ctx.cursor_end = ctx.cursor_end or effective_end
        ctx.extra_result["watermark_value"] = watermark_target
        ctx.extra_result["watermark_field"] = SHIPMENT_WATERMARK_FIELD
        ctx.extra_result["schema_version"] = SHIPMENT_SCHEMA_VERSION
        ctx.extra_result["window_count"] = len(windows)
        ctx.extra_result["max_payload_time"] = max_payload_time
        ctx.extra_result["last_window_end"] = last_window_end
        return ctx.sync_run_id


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
