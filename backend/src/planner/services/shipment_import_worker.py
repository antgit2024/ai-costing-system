from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from ...config import settings
from ...database import SessionLocal
from .. import models
from . import shipment_import_service


_worker_thread: Optional[threading.Thread] = None
_stop_event = threading.Event()

# Track when the snapshot retry sweep last ran so we can throttle it
# without coupling to wall-clock cron expressions. Module-level: lives as
# long as the in-process worker thread.
_last_snapshot_sweep_at: Optional[datetime] = None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def request_stop() -> None:
    _stop_event.set()


def _try_acquire_lock(db: Session) -> bool:
    # Postgres advisory lock - ensures only one worker runs across uvicorn workers/processes.
    try:
        ok = db.execute(text("select pg_try_advisory_lock(:k)"), {"k": int(settings.planner_shipment_import_worker_lock_key)}).scalar()
        return bool(ok)
    except Exception:
        return False


def _release_lock(db: Session) -> None:
    try:
        db.execute(text("select pg_advisory_unlock(:k)"), {"k": int(settings.planner_shipment_import_worker_lock_key)})
    except Exception:
        return None


def _claim_next_queued_batch(db: Session) -> Optional[models.ShipmentImportBatch]:
    """
    Claim a queued shipment import batch using row locks.
    """
    batch = (
        db.query(models.ShipmentImportBatch)
        .filter(models.ShipmentImportBatch.status == "queued")
        .order_by(models.ShipmentImportBatch.created_at.asc())
        .with_for_update(skip_locked=True)
        .first()
    )
    if not batch:
        return None
    batch.status = "processing"
    batch.updated_at = _utcnow()
    db.commit()
    db.refresh(batch)
    return batch


def _repair_terminal_processing_batches(db: Session) -> int:
    """
    A service restart can interrupt the import after all line-level work is persisted
    but before the final batch.status='success' commit. Repair those terminal batches
    so the UI does not stay forever in "processing".
    """
    repaired = 0
    batches = (
        db.query(models.ShipmentImportBatch)
        .filter(models.ShipmentImportBatch.status == "processing")
        .order_by(models.ShipmentImportBatch.updated_at.asc())
        .limit(20)
        .all()
    )
    for batch in batches:
        if not batch.total_rows or batch.total_rows <= 0:
            continue
        line_count = (
            db.query(func.count(models.ShipmentLine.id))
            .filter(models.ShipmentLine.batch_id == batch.id)
            .scalar()
            or 0
        )
        if int(line_count) != int(batch.total_rows):
            continue
        snapshot_count = (
            db.query(func.count(models.BomSnapshot.id))
            .filter(models.BomSnapshot.batch_id == batch.id)
            .scalar()
            or 0
        )
        exception_count = (
            db.query(func.count(models.ShipmentExceptionQueue.id))
            .filter(models.ShipmentExceptionQueue.batch_id == batch.id)
            .scalar()
            or 0
        )
        if int(snapshot_count) + int(exception_count) != int(batch.total_rows):
            continue
        costing_count = (
            db.query(func.count(models.ShipmentCostingResult.id))
            .filter(models.ShipmentCostingResult.batch_id == batch.id)
            .scalar()
            or 0
        )
        batch.status = "success"
        batch.exception_rows = int(exception_count)
        batch.result_json = {
            **(batch.result_json or {}),
            "batch_id": batch.id,
            "file_hash": batch.file_hash,
            "counts": {
                "total_rows": batch.total_rows,
                "inserted_rows": batch.inserted_rows,
                "skipped_rows": batch.skipped_rows,
                "exception_rows": int(exception_count),
                "bom_snapshots": int(snapshot_count),
                "costing_results": int(costing_count),
            },
            "status_repaired_at": _utcnow().isoformat(),
            "status_repair_reason": "terminal_counts_match_after_worker_interruption",
        }
        batch.updated_at = _utcnow()
        repaired += 1
    if repaired:
        db.commit()
    return repaired


def _run_one(batch: models.ShipmentImportBatch) -> None:
    db: Session = SessionLocal()
    try:
        # Ensure we're still processing the same batch in this session.
        b = db.get(models.ShipmentImportBatch, batch.id)
        if not b:
            return
        if b.status != "processing":
            return
        cfg = dict(b.result_json or {})
        mode = str(cfg.get("mode") or "2026")
        process_snapshots = bool(cfg.get("process_snapshots", True))
        processor = str(cfg.get("processor") or "").strip()

        # Dispatch by processor type. The default (unset / empty) is the
        # legacy Excel path that needs a preview-cache file. Integration
        # paths (e.g. Jackyun mapper) set processor='jackyun_existing_lines'
        # to indicate the lines are already in DB and only need the shared
        # finalize / BOM-snapshot pipeline.
        if processor == "jackyun_existing_lines":
            shipment_import_service.process_existing_shipment_lines(
                db,
                batch_id=b.id,
                mode=mode,
                process_snapshots=process_snapshots,
            )
        else:
            shipment_import_service.execute_shipment_xlsx_from_preview(
                db,
                preview_id=b.file_hash,
                file_name=b.file_name,
                export_date=b.export_date,
                requested_by=b.requested_by,
                mode=mode,
                process_snapshots=process_snapshots,
            )
    except Exception as exc:  # noqa: BLE001
        try:
            db.rollback()
        except Exception:
            pass
        try:
            b = db.get(models.ShipmentImportBatch, batch.id)
            if b:
                b.status = "failed"
                b.result_json = {
                    **(b.result_json or {}),
                    "error": str(exc)[:800],
                    "stage": "shipment_import_worker",
                }
                b.updated_at = _utcnow()
                db.commit()
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass
    finally:
        db.close()


def _maybe_run_snapshot_sweep(db: Session) -> None:
    """Throttled call to ``sweep_bound_lines_missing_snapshot`` — keeps
    the "⏳ 等出快照(系统处理中)" promise true.

    Runs at most once every ``planner_shipment_snapshot_retry_interval_seconds``
    while the worker holds the advisory lock; failures are logged but
    never crash the worker loop (we want batch processing to keep going
    even if the sweep blows up on a corrupt line).
    """
    global _last_snapshot_sweep_at
    if not getattr(settings, "planner_shipment_snapshot_retry_enabled", True):
        return
    interval = max(float(getattr(settings, "planner_shipment_snapshot_retry_interval_seconds", 300.0) or 300.0), 30.0)
    now = _utcnow()
    if _last_snapshot_sweep_at is not None and (now - _last_snapshot_sweep_at).total_seconds() < interval:
        return

    lookback = int(getattr(settings, "planner_shipment_snapshot_retry_lookback_days", 14) or 14)
    limit = int(getattr(settings, "planner_shipment_snapshot_retry_max_lines_per_pass", 200) or 200)

    try:
        result = shipment_import_service.sweep_bound_lines_missing_snapshot(
            db,
            lookback_days=lookback,
            limit=limit,
        )
        _last_snapshot_sweep_at = now
        # Brief stdout log so operators can grep journalctl for sweep
        # progress; intentionally one-line to keep journal noise low.
        scanned = result.get("scanned") or 0
        if scanned:
            print(  # noqa: T201
                f"[snapshot-retry-sweep] scanned={scanned} created={result.get('snapshots_created')}"
                f" recomputed={result.get('snapshots_recomputed')} skipped={result.get('skipped_already_done')}"
                f" failed={result.get('failed')} duration_ms={result.get('duration_ms')}",
                flush=True,
            )
    except Exception as exc:  # noqa: BLE001
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        # Don't update _last_snapshot_sweep_at on failure → next loop tick
        # will retry; but if it keeps failing, throttle once 30s have passed
        # so we don't spin.
        _last_snapshot_sweep_at = now - timedelta(seconds=interval - 30.0)
        print(f"[snapshot-retry-sweep] FAILED: {exc!r}", flush=True)  # noqa: T201


def _loop() -> None:
    while not _stop_event.is_set():
        db: Session = SessionLocal()
        acquired = False
        try:
            acquired = _try_acquire_lock(db)
            if not acquired:
                time.sleep(max(float(settings.planner_shipment_import_worker_idle_sleep_seconds or 2.0), 0.5))
                continue

            _repair_terminal_processing_batches(db)
            _maybe_run_snapshot_sweep(db)
            batch = _claim_next_queued_batch(db)
            if not batch:
                time.sleep(max(float(settings.planner_shipment_import_worker_idle_sleep_seconds or 2.0), 0.5))
                continue
        finally:
            try:
                if acquired:
                    _release_lock(db)
            finally:
                db.close()

        # Run outside the lock to allow other processes to keep polling.
        _run_one(batch)


def start_worker() -> None:
    global _worker_thread
    if not settings.planner_shipment_import_worker_enabled:
        return
    if _worker_thread and _worker_thread.is_alive():
        return
    _stop_event.clear()
    t = threading.Thread(target=_loop, name="shipment-import-worker", daemon=True)
    _worker_thread = t
    t.start()

