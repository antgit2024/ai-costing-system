"""Sync run orchestration shared by all vendors.

Usage from a vendor sync_jobs.py:

    with run_sync(
        db=db,
        source_system="jackyun",
        sync_type="shipment_pull",
        api_method="wms.order.query-info",
        request_params={"start": "...", "end": "..."},
        triggered_by="cron",
    ) as ctx:
        for page in iter_pages(...):
            ctx.archive_record(record_type="shipment", external_id=..., payload=...)
            ctx.inc_inserted()
            ...

The context manager is responsible for:
- creating the ``integration_sync_runs`` row
- letting the body call ``ctx.archive_record(...)`` to upsert into
  ``integration_api_records``
- finalizing status + counters on exit (succeeded / failed)
"""

from __future__ import annotations

import hashlib
import json
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, Optional

from sqlalchemy.orm import Session

from .errors import IntegrationError


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _payload_hash(payload: Any) -> str:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class SyncRunContext:
    """Mutable context passed to the body of ``run_sync(...)``."""

    sync_run_id: str
    source_system: str
    sync_type: str
    api_method: str
    db: Session

    total: int = 0
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    errored: int = 0
    cursor_start: Optional[str] = None
    cursor_end: Optional[str] = None
    context_id: Optional[str] = None
    extra_result: Dict[str, Any] = field(default_factory=dict)

    def archive_record(
        self,
        *,
        record_type: str,
        external_id: str,
        payload: Dict[str, Any],
        external_line_id: Optional[str] = None,
        fetched_at: Optional[datetime] = None,
        schema_version: Optional[str] = None,
    ) -> "ArchivedRecord":
        """Upsert one external record into ``integration_api_records``.

        Returns an ``ArchivedRecord`` that mappers can attach to business rows.
        ``schema_version`` should identify the upstream payload contract
        (e.g. ``jackyun.shipment.v1``) so future mapper changes can replay
        records by version.
        """

        from ...planner import models as planner_models  # type: ignore

        if not external_id:
            raise ValueError("external_id is required for archive_record")

        record_hash = _payload_hash(payload)
        try:
            payload_bytes = len(json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8"))
        except Exception:
            payload_bytes = None
        # Identity is (source_system, api_method, record_type, external_id,
        # external_line_id, schema_version). Different schema_versions of the
        # same external record are kept side-by-side so old payloads can be
        # replayed against old mappers when upstream contracts evolve.
        existing = (
            self.db.query(planner_models.IntegrationApiRecord)
            .filter(
                planner_models.IntegrationApiRecord.source_system == self.source_system,
                planner_models.IntegrationApiRecord.api_method == self.api_method,
                planner_models.IntegrationApiRecord.record_type == record_type,
                planner_models.IntegrationApiRecord.external_id == external_id,
                planner_models.IntegrationApiRecord.external_line_id == external_line_id,
                planner_models.IntegrationApiRecord.schema_version == schema_version,
            )
            .one_or_none()
        )
        now = _utcnow()
        if existing is None:
            row = planner_models.IntegrationApiRecord(
                id=str(uuid.uuid4()),
                sync_run_id=self.sync_run_id,
                source_system=self.source_system,
                api_method=self.api_method,
                record_type=record_type,
                external_id=external_id,
                external_line_id=external_line_id,
                payload_hash=record_hash,
                payload_bytes=payload_bytes,
                schema_version=schema_version,
                payload_json=payload,
                fetched_at=fetched_at or now,
                status="pending",
            )
            self.db.add(row)
            self.db.flush()
            return ArchivedRecord(id=row.id, was_new=True, payload_changed=True)
        payload_changed = existing.payload_hash != record_hash
        if payload_changed:
            existing.payload_hash = record_hash
            existing.payload_bytes = payload_bytes
            existing.payload_json = payload
            existing.fetched_at = fetched_at or now
            existing.sync_run_id = self.sync_run_id
            existing.status = "pending"
            existing.error_message = None
        return ArchivedRecord(id=existing.id, was_new=False, payload_changed=payload_changed)

    def inc_total(self, n: int = 1) -> None:
        self.total += n

    def inc_inserted(self, n: int = 1) -> None:
        self.inserted += n

    def inc_updated(self, n: int = 1) -> None:
        self.updated += n

    def inc_skipped(self, n: int = 1) -> None:
        self.skipped += n

    def inc_errored(self, n: int = 1) -> None:
        self.errored += n


@dataclass
class ArchivedRecord:
    id: str
    was_new: bool
    payload_changed: bool


@contextmanager
def run_sync(
    *,
    db: Session,
    source_system: str,
    sync_type: str,
    api_method: str,
    request_params: Optional[Dict[str, Any]] = None,
    direction: str = "pull",
    triggered_by: Optional[str] = None,
    cursor_start: Optional[str] = None,
) -> Iterator[SyncRunContext]:
    """Create a ``integration_sync_runs`` row and yield a context for the body."""

    from ...planner import models as planner_models  # type: ignore

    run = planner_models.IntegrationSyncRun(
        id=str(uuid.uuid4()),
        source_system=source_system,
        sync_type=sync_type,
        api_method=api_method,
        direction=direction,
        status="running",
        request_params_json=request_params or {},
        cursor_start=cursor_start,
        triggered_by=triggered_by,
        started_at=_utcnow(),
    )
    db.add(run)
    db.flush()

    ctx = SyncRunContext(
        sync_run_id=run.id,
        source_system=source_system,
        sync_type=sync_type,
        api_method=api_method,
        db=db,
        cursor_start=cursor_start,
    )

    try:
        yield ctx
    except IntegrationError as exc:
        run.status = "failed"
        run.finished_at = _utcnow()
        run.total_rows = ctx.total
        run.inserted_rows = ctx.inserted
        run.updated_rows = ctx.updated
        run.skipped_rows = ctx.skipped
        run.error_rows = max(ctx.errored, 1)
        run.cursor_end = ctx.cursor_end
        run.context_id = ctx.context_id
        run.error_message = exc.message
        run.result_json = {**ctx.extra_result, "error": exc.to_dict()}
        db.commit()
        raise
    except Exception as exc:  # noqa: BLE001
        run.status = "failed"
        run.finished_at = _utcnow()
        run.total_rows = ctx.total
        run.inserted_rows = ctx.inserted
        run.updated_rows = ctx.updated
        run.skipped_rows = ctx.skipped
        run.error_rows = max(ctx.errored, 1)
        run.cursor_end = ctx.cursor_end
        run.context_id = ctx.context_id
        run.error_message = str(exc)
        run.result_json = {**ctx.extra_result, "error": {"type": type(exc).__name__, "message": str(exc)}}
        db.commit()
        raise
    else:
        run.status = "succeeded"
        run.finished_at = _utcnow()
        run.total_rows = ctx.total
        run.inserted_rows = ctx.inserted
        run.updated_rows = ctx.updated
        run.skipped_rows = ctx.skipped
        run.error_rows = ctx.errored
        run.cursor_end = ctx.cursor_end
        run.context_id = ctx.context_id
        run.result_json = ctx.extra_result
        db.commit()
