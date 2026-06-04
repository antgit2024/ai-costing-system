"""Writeback queue helpers.

A writeback job is something we need to push to an upstream system, e.g.
"update Jackyun seller memo for orderNo X with body Y". Producers call
``enqueue_writeback(...)``; a worker (per-vendor or generic) calls
``claim_due_writebacks(...)`` then ``mark_writeback_result(...)``.

We keep the worker out of this file so each vendor can decide how to map
``payload`` to a real API call.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def enqueue_writeback(
    db: Session,
    *,
    source_system: str,
    api_method: str,
    target_type: str,
    target_id: str,
    payload: Dict[str, Any],
    requested_by: Optional[str] = None,
    max_attempts: int = 5,
    delay_seconds: int = 0,
    metadata: Optional[Dict[str, Any]] = None,
) -> str:
    from ...planner import models as planner_models  # type: ignore

    next_run_at = _utcnow() + timedelta(seconds=max(0, int(delay_seconds)))
    row = planner_models.IntegrationWritebackJob(
        id=str(uuid.uuid4()),
        source_system=source_system,
        api_method=api_method,
        target_type=target_type,
        target_id=target_id,
        payload_json=payload or {},
        status="pending",
        attempt=0,
        max_attempts=max_attempts,
        next_run_at=next_run_at,
        requested_by=requested_by,
        metadata_json=metadata or {},
    )
    db.add(row)
    db.flush()
    return row.id


def claim_due_writebacks(
    db: Session,
    *,
    source_system: Optional[str] = None,
    limit: int = 20,
    now: Optional[datetime] = None,
) -> List[Any]:
    """Claim a batch of due writeback jobs.

    NOTE: For multi-worker safety, callers should run this inside a transaction
    and use ``with_for_update(skip_locked=True)`` on PostgreSQL. Kept simple
    here so it works on SQLite for tests.
    """

    from ...planner import models as planner_models  # type: ignore

    cutoff = now or _utcnow()
    q = (
        db.query(planner_models.IntegrationWritebackJob)
        .filter(planner_models.IntegrationWritebackJob.status.in_(("pending", "retrying")))
        .filter(planner_models.IntegrationWritebackJob.next_run_at <= cutoff)
    )
    if source_system:
        q = q.filter(planner_models.IntegrationWritebackJob.source_system == source_system)
    q = q.order_by(planner_models.IntegrationWritebackJob.next_run_at.asc()).limit(limit)
    rows = q.all()
    for row in rows:
        row.status = "in_progress"
        row.attempt = (row.attempt or 0) + 1
        row.last_attempt_at = cutoff
    db.flush()
    return rows


def mark_writeback_result(
    db: Session,
    *,
    job_id: str,
    succeeded: bool,
    error: Optional[str] = None,
    retry_in_seconds: int = 60,
) -> None:
    from ...planner import models as planner_models  # type: ignore

    row = (
        db.query(planner_models.IntegrationWritebackJob)
        .filter(planner_models.IntegrationWritebackJob.id == job_id)
        .one_or_none()
    )
    if row is None:
        return
    if succeeded:
        row.status = "succeeded"
        row.last_error = None
        row.next_run_at = None
        return
    row.last_error = error
    if (row.attempt or 0) >= (row.max_attempts or 0):
        row.status = "failed"
        row.next_run_at = None
        return
    row.status = "retrying"
    row.next_run_at = _utcnow() + timedelta(seconds=max(1, int(retry_in_seconds)))
