"""Generic dead-letter queue helpers.

Use ``record_dead_letter(...)`` from any mapper / writeback worker when a
single record fails to process so the surrounding batch can keep going.

Operators replay items via ``list_open_dead_letters(...)`` and acknowledge
fixes via ``resolve_dead_letter(...)``.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def record_dead_letter(  # type: ignore[no-untyped-def]
    db,
    *,
    source_system: str,
    api_method: Optional[str] = None,
    record_type: Optional[str] = None,
    stage: str = "mapper",
    sync_run_id: Optional[str] = None,
    source_payload_id: Optional[str] = None,
    external_id: Optional[str] = None,
    external_line_id: Optional[str] = None,
    error: BaseException | str | None = None,
    payload_snapshot: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
):
    """Insert (or bump attempt counter for) a dead-letter row.

    If a row already exists with the same identity (same source_system +
    api_method + external_id + external_line_id + stage), we bump ``attempt``
    instead of inserting a duplicate; otherwise the queue would explode on
    repeated retries.
    """

    from ...planner import models as planner_models  # type: ignore

    if isinstance(error, BaseException):
        error_type = type(error).__name__
        error_message = str(error)
    elif isinstance(error, str):
        error_type = "Error"
        error_message = error
    else:
        error_type = None
        error_message = None

    existing = (
        db.query(planner_models.IntegrationDeadLetter)
        .filter(
            planner_models.IntegrationDeadLetter.source_system == source_system,
            planner_models.IntegrationDeadLetter.api_method == api_method,
            planner_models.IntegrationDeadLetter.stage == stage,
            planner_models.IntegrationDeadLetter.external_id == external_id,
            planner_models.IntegrationDeadLetter.external_line_id == external_line_id,
            planner_models.IntegrationDeadLetter.status.in_(("open", "retrying")),
        )
        .one_or_none()
    )
    now = _utcnow()
    if existing is not None:
        existing.attempt = (existing.attempt or 0) + 1
        existing.last_attempt_at = now
        existing.error_type = error_type or existing.error_type
        existing.error_message = error_message or existing.error_message
        if payload_snapshot is not None:
            existing.payload_snapshot_json = payload_snapshot
        if metadata is not None:
            md = dict(existing.metadata_json or {})
            md.update(metadata)
            existing.metadata_json = md
        if source_payload_id and not existing.source_payload_id:
            existing.source_payload_id = source_payload_id
        if sync_run_id:
            existing.sync_run_id = sync_run_id
        return existing

    row = planner_models.IntegrationDeadLetter(
        id=str(uuid.uuid4()),
        source_system=source_system,
        api_method=api_method,
        record_type=record_type,
        stage=stage,
        sync_run_id=sync_run_id,
        source_payload_id=source_payload_id,
        external_id=external_id,
        external_line_id=external_line_id,
        error_type=error_type,
        error_message=error_message,
        payload_snapshot_json=payload_snapshot or {},
        attempt=1,
        status="open",
        last_attempt_at=now,
        metadata_json=metadata or {},
    )
    db.add(row)
    db.flush()
    return row


def list_open_dead_letters(  # type: ignore[no-untyped-def]
    db,
    *,
    source_system: Optional[str] = None,
    record_type: Optional[str] = None,
    limit: int = 100,
) -> List[Any]:
    from ...planner import models as planner_models  # type: ignore

    q = db.query(planner_models.IntegrationDeadLetter).filter(
        planner_models.IntegrationDeadLetter.status.in_(("open", "retrying"))
    )
    if source_system:
        q = q.filter(planner_models.IntegrationDeadLetter.source_system == source_system)
    if record_type:
        q = q.filter(planner_models.IntegrationDeadLetter.record_type == record_type)
    q = q.order_by(planner_models.IntegrationDeadLetter.last_attempt_at.asc()).limit(limit)
    return q.all()


def resolve_dead_letter(  # type: ignore[no-untyped-def]
    db,
    *,
    dead_letter_id: str,
    resolved_by: Optional[str] = None,
    note: Optional[str] = None,
) -> bool:
    from ...planner import models as planner_models  # type: ignore

    row = (
        db.query(planner_models.IntegrationDeadLetter)
        .filter(planner_models.IntegrationDeadLetter.id == dead_letter_id)
        .one_or_none()
    )
    if row is None:
        return False
    row.status = "resolved"
    row.resolved_at = _utcnow()
    row.resolved_by = resolved_by
    if note:
        md = dict(row.metadata_json or {})
        md["resolve_note"] = note
        row.metadata_json = md
    return True
