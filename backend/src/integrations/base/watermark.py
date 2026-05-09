"""Incremental sync watermarks.

Why a dedicated table (vs. scanning ``integration_sync_runs``):
- single, indexed lookup per (source_system, sync_type)
- decoupled from history retention (we may purge old runs)
- supports atomic monotonic advance (we never go backwards)

Typical use:

    cursor = get_watermark_value(db, source_system="jackyun", sync_type="shipment_pull")
    # ... pull from upstream starting at `cursor` ...
    advance_watermark_if_newer(
        db,
        source_system="jackyun",
        sync_type="shipment_pull",
        watermark_field="modifyTime",
        new_value="2026-05-06 09:30:00",
        sync_run_id=run_id,
    )
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def get_watermark(db, *, source_system: str, sync_type: str):  # type: ignore[no-untyped-def]
    from ...planner import models as planner_models  # type: ignore

    return (
        db.query(planner_models.IntegrationSyncWatermark)
        .filter(
            planner_models.IntegrationSyncWatermark.source_system == source_system,
            planner_models.IntegrationSyncWatermark.sync_type == sync_type,
        )
        .one_or_none()
    )


def get_watermark_value(db, *, source_system: str, sync_type: str) -> Optional[str]:  # type: ignore[no-untyped-def]
    row = get_watermark(db, source_system=source_system, sync_type=sync_type)
    return row.watermark_value if row else None


def set_watermark(  # type: ignore[no-untyped-def]
    db,
    *,
    source_system: str,
    sync_type: str,
    watermark_field: str,
    watermark_value: Optional[str],
    sync_run_id: Optional[str] = None,
    cursor_extra: Optional[Dict[str, Any]] = None,
    notes: Optional[str] = None,
):
    """Upsert the watermark row unconditionally (use ``advance_watermark_if_newer`` for guarded writes)."""

    import uuid

    from ...planner import models as planner_models  # type: ignore

    row = get_watermark(db, source_system=source_system, sync_type=sync_type)
    now = _utcnow()
    if row is None:
        row = planner_models.IntegrationSyncWatermark(
            id=str(uuid.uuid4()),
            source_system=source_system,
            sync_type=sync_type,
            watermark_field=watermark_field,
            watermark_value=watermark_value,
            cursor_extra_json=cursor_extra or {},
            last_sync_run_id=sync_run_id,
            last_advanced_at=now,
            notes=notes,
        )
        db.add(row)
        db.flush()
        return row
    row.watermark_field = watermark_field
    row.watermark_value = watermark_value
    if cursor_extra is not None:
        row.cursor_extra_json = cursor_extra
    row.last_sync_run_id = sync_run_id or row.last_sync_run_id
    row.last_advanced_at = now
    if notes is not None:
        row.notes = notes
    return row


def advance_watermark_if_newer(  # type: ignore[no-untyped-def]
    db,
    *,
    source_system: str,
    sync_type: str,
    watermark_field: str,
    new_value: Optional[str],
    sync_run_id: Optional[str] = None,
    cursor_extra: Optional[Dict[str, Any]] = None,
    notes: Optional[str] = None,
):
    """Advance only if ``new_value`` is strictly greater (lexicographically) than current value.

    Watermark values are stored as strings; for ISO/timestamp formats lexicographic
    ordering matches chronological ordering, which is what we want.
    """

    if new_value is None:
        return get_watermark(db, source_system=source_system, sync_type=sync_type)

    current = get_watermark(db, source_system=source_system, sync_type=sync_type)
    if current is None:
        return set_watermark(
            db,
            source_system=source_system,
            sync_type=sync_type,
            watermark_field=watermark_field,
            watermark_value=new_value,
            sync_run_id=sync_run_id,
            cursor_extra=cursor_extra,
            notes=notes,
        )
    if (current.watermark_value or "") < (new_value or ""):
        return set_watermark(
            db,
            source_system=source_system,
            sync_type=sync_type,
            watermark_field=watermark_field,
            watermark_value=new_value,
            sync_run_id=sync_run_id,
            cursor_extra=cursor_extra,
            notes=notes,
        )
    return current
