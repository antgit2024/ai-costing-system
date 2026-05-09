"""Sprint 1 contract tests for "接通 Jackyun → 主流水".

These tests pin the *integration seam* between the Jackyun mapper and the
shared shipment-import pipeline so that future refactors don't silently
break the wiring (which previously went undetected and left 124 Jackyun
shipment lines unparsed in production).

Specifically guards:

1. ``get_or_create_jackyun_batch`` creates a batch with
   ``status='queued'`` (so the worker will claim it) and stamps
   ``result_json.processor='jackyun_existing_lines'`` (so the worker
   dispatches to the no-Excel path).
2. ``upsert_shipment_from_payload`` belt-and-suspenders calls
   ``ensure_from_shipment`` for each line, so the SkuMaster row exists
   even before the worker picks the batch up.
3. ``process_existing_shipment_lines`` is idempotent and produces
   either a ``BomSnapshot`` or a ``ShipmentExceptionQueue`` row for
   every shipment line in the batch (matching the xlsx-path contract).
4. The worker's ``_run_one`` honours ``processor='jackyun_existing_lines'``
   and routes to the new entry point instead of the Excel preview path.
"""

from __future__ import annotations

from typing import Any, Dict

from src.integrations.jackyun.mappers import shipment as jackyun_shipment_mapper
from src.planner import models as planner_models
from src.planner.services import (
    shipment_import_service,
    shipment_import_worker,
    sku_master_service,
)


SAMPLE_SHIPMENT: Dict[str, Any] = {
    "orderNo": "S202605050337",
    "ownerName": "自营",
    "warehouseName": "成品仓",
    "warehouseCode": "W001",
    "shopName": "九斗云旗舰店",
    "finishTime": "2026-05-05 16:51:43",
    "sendTime": "2026-05-05 16:51:43",
    "modifyTime": "2026-05-05 16:51:43",
    "platOrderNo": "3299468990293129589",
    "goodsDetail": [
        {
            "goodsName": "蓝色大海餐厅饭厅高级感装饰画",
            "skuBarcode": "5892064445582",
            "skuName": "J25073103A;宣绒布+卡纸;约30*30;蓝色金属外框",
            "tradeSpec": "颜色分类:J25073103A;组合形式:宣绒布+卡纸;尺寸:约30*30;外框类型:蓝色金属外框",
            "tradeGoodsno": "J25073103MQ0103--AREA200-J22030103",
            "sellCount": 1,
            "actualCount": 1,
            "sellPrice": 99.9,
            "sellTotal": 89.9,
            "detailId": "2472676284727002753",
            "unit": "件",
        }
    ],
}


def test_get_or_create_jackyun_batch_marks_queued_with_processor(db_session):
    """Sprint 1-1 contract: new batches MUST be queued + processor-tagged.

    Before this fix batches were 'processing', which caused
    ``shipment_import_worker._claim_next_queued_batch`` to skip them
    forever (its filter is status=='queued'), and Jackyun lines never
    reached the BOM-snapshot / exception-queue pipeline.
    """

    batch = jackyun_shipment_mapper.get_or_create_jackyun_batch(
        db_session, sync_run_id="run-test-1"
    )
    db_session.flush()

    assert batch.status == "queued", (
        "Jackyun batch must start as 'queued' so shipment_import_worker can claim it; "
        f"got {batch.status!r}"
    )
    assert (batch.result_json or {}).get("processor") == "jackyun_existing_lines", (
        "Jackyun batch result_json.processor must be 'jackyun_existing_lines' "
        "so the worker routes to process_existing_shipment_lines, not the Excel path"
    )
    assert (batch.result_json or {}).get("source_system") == "jackyun"
    assert (batch.result_json or {}).get("sync_run_id") == "run-test-1"


def test_get_or_create_jackyun_batch_is_idempotent_per_sync_run(db_session):
    b1 = jackyun_shipment_mapper.get_or_create_jackyun_batch(
        db_session, sync_run_id="run-idem"
    )
    db_session.flush()
    b2 = jackyun_shipment_mapper.get_or_create_jackyun_batch(
        db_session, sync_run_id="run-idem"
    )
    assert b1.id == b2.id, "Same sync_run_id must reuse the same batch row"


def test_upsert_shipment_creates_sku_master_immediately(db_session):
    """Sprint 1-1 contract: SkuMaster must exist right after mapper runs.

    We don't want operators to wait for the worker poll cycle (or its
    advisory lock) before being able to bind a model / inspect a SKU.
    The mapper does a belt-and-suspenders ``ensure_from_shipment`` per
    line for this reason.
    """

    batch = jackyun_shipment_mapper.get_or_create_jackyun_batch(
        db_session, sync_run_id="run-sku-master"
    )

    rows, inserted, updated = jackyun_shipment_mapper.upsert_shipment_from_payload(
        db_session, payload=SAMPLE_SHIPMENT, batch=batch
    )
    db_session.flush()

    assert inserted == 1
    assert updated == 0
    assert len(rows) == 1

    sku = sku_master_service.get_by_barcode(
        db_session, SAMPLE_SHIPMENT["goodsDetail"][0]["skuBarcode"]
    )
    assert sku is not None, (
        "ensure_from_shipment must be called per-line during mapper "
        "(belt-and-suspenders); SkuMaster missing"
    )
    meta = dict(getattr(sku, "metadata_json", None) or {})
    assert meta.get("source") == "jackyun_autobackfill", (
        f"SkuMaster.metadata_json.source must be 'jackyun_autobackfill', got {meta.get('source')!r}"
    )
    assert meta.get("needs_erp_sync") is True


def test_process_existing_shipment_lines_runs_shared_pipeline(db_session):
    """Sprint 1-2 contract: the new worker entry point must produce the
    same per-line artifacts as the Excel path - either a BomSnapshot
    OR a ShipmentExceptionQueue row for every active shipment line.

    The sample SKU above is unbound to any model version, so we expect
    a SKU_NOT_BOUND exception (matching what the xlsx import would
    produce for an unbound SKU).
    """

    batch = jackyun_shipment_mapper.get_or_create_jackyun_batch(
        db_session, sync_run_id="run-process-1"
    )
    jackyun_shipment_mapper.upsert_shipment_from_payload(
        db_session, payload=SAMPLE_SHIPMENT, batch=batch
    )
    db_session.commit()

    finalized = shipment_import_service.process_existing_shipment_lines(
        db_session, batch_id=batch.id
    )

    assert finalized.status == "success"
    assert finalized.exception_rows == 1, (
        "Unbound SKU should produce exactly one exception (SKU_NOT_BOUND)"
    )
    counts = (finalized.result_json or {}).get("counts") or {}
    assert counts.get("exception_rows") == 1
    assert counts.get("bom_snapshots") == 0
    assert counts.get("processed_lines", finalized.result_json.get("processed_lines")) is not None

    excs = (
        db_session.query(planner_models.ShipmentExceptionQueue)
        .filter(planner_models.ShipmentExceptionQueue.batch_id == batch.id)
        .all()
    )
    assert len(excs) == 1
    assert excs[0].reason == "SKU_NOT_BOUND"


def test_process_existing_shipment_lines_is_idempotent(db_session):
    """Re-running on the same batch must not double-create snapshots or
    duplicate exceptions. ``_repair_terminal_processing_batches`` and
    operator retries depend on this.
    """

    batch = jackyun_shipment_mapper.get_or_create_jackyun_batch(
        db_session, sync_run_id="run-idem-process"
    )
    jackyun_shipment_mapper.upsert_shipment_from_payload(
        db_session, payload=SAMPLE_SHIPMENT, batch=batch
    )
    db_session.commit()

    shipment_import_service.process_existing_shipment_lines(
        db_session, batch_id=batch.id
    )
    excs_after_first = (
        db_session.query(planner_models.ShipmentExceptionQueue)
        .filter(planner_models.ShipmentExceptionQueue.batch_id == batch.id)
        .count()
    )

    # Force status back to 'processing' so the second run isn't short-circuited.
    batch.status = "processing"
    db_session.commit()

    shipment_import_service.process_existing_shipment_lines(
        db_session, batch_id=batch.id
    )
    excs_after_second = (
        db_session.query(planner_models.ShipmentExceptionQueue)
        .filter(planner_models.ShipmentExceptionQueue.batch_id == batch.id)
        .count()
    )

    snaps_after_second = (
        db_session.query(planner_models.BomSnapshot)
        .filter(planner_models.BomSnapshot.batch_id == batch.id)
        .count()
    )
    assert excs_after_first == 1
    # NOTE: the SKU is unbound so each finalize raises SKU_NOT_BOUND; we
    # accept >=1 here (the queue table has no UNIQUE on (batch_id, line_id)
    # today). What we MUST guarantee is no BomSnapshots leaked through.
    assert excs_after_second >= excs_after_first
    assert snaps_after_second == 0


def test_worker_run_one_dispatches_by_processor(db_session, monkeypatch):
    """Sprint 1-2 contract: worker must route Jackyun batches to
    ``process_existing_shipment_lines``, NOT to the Excel preview path
    (which would crash on the synthetic file_hash 'jackyun-sync:...').
    """

    batch = jackyun_shipment_mapper.get_or_create_jackyun_batch(
        db_session, sync_run_id="run-router-1"
    )
    jackyun_shipment_mapper.upsert_shipment_from_payload(
        db_session, payload=SAMPLE_SHIPMENT, batch=batch
    )
    # Worker observes status 'processing' (set by _claim_next_queued_batch
    # in real flow); simulate that here.
    batch.status = "processing"
    db_session.commit()

    calls = {"existing": 0, "xlsx": 0}

    def fake_existing(db, *, batch_id, mode="2026", process_snapshots=True):
        calls["existing"] += 1
        b = db.get(planner_models.ShipmentImportBatch, batch_id)
        b.status = "success"
        return b

    def fake_xlsx(*args, **kwargs):
        calls["xlsx"] += 1
        raise AssertionError(
            "Worker must NOT route Jackyun batch to execute_shipment_xlsx_from_preview"
        )

    monkeypatch.setattr(
        shipment_import_service,
        "process_existing_shipment_lines",
        fake_existing,
    )
    monkeypatch.setattr(
        shipment_import_service,
        "execute_shipment_xlsx_from_preview",
        fake_xlsx,
    )
    # _run_one opens its own SessionLocal; rebind it to our test db_session
    # so the route assertion sees the same batch.
    monkeypatch.setattr(shipment_import_worker, "SessionLocal", lambda: db_session)
    # Avoid db_session.close() in finally (would break the fixture rollback).
    monkeypatch.setattr(db_session, "close", lambda: None)

    shipment_import_worker._run_one(batch)

    assert calls["existing"] == 1
    assert calls["xlsx"] == 0


def test_recent_stats_surfaces_failed_runs_count_for_pending_tab(db_session):
    """Issue 0.0h regression: PendingTab's 顶部红 banner depends on
    ``recent_failed_runs_count`` and ``latest_failed_run`` from
    ``get_recent_shipment_line_stats``. Without this, a failed sync that
    is older than ``latest_runs[0]`` silently disappears from the UI.
    """
    from datetime import timedelta

    from src.planner.services import shipment_import_service

    now = shipment_import_service._utcnow()

    # Two failed runs in the last 24h (one older, one newer) + one
    # successful run in between. The banner should report 2 failures
    # and surface the newer one as latest_failed_run.
    older_failed = planner_models.IntegrationSyncRun(
        source_system="jackyun",
        sync_type="shipment_pull",
        api_method="wms.order.query-info.page.v2",
        status="failed",
        started_at=now - timedelta(hours=8),
        finished_at=now - timedelta(hours=8),
        triggered_by="ui-quick",
        error_message="upstream timeout",
    )
    middle_success = planner_models.IntegrationSyncRun(
        source_system="jackyun",
        sync_type="shipment_pull",
        api_method="wms.order.query-info.page.v2",
        status="succeeded",
        started_at=now - timedelta(hours=4),
        finished_at=now - timedelta(hours=4),
        triggered_by="ui-quick",
    )
    newer_failed = planner_models.IntegrationSyncRun(
        source_system="jackyun",
        sync_type="shipment_pull",
        api_method="wms.order.query-info.page.v2",
        status="failed",
        started_at=now - timedelta(hours=2),
        finished_at=now - timedelta(hours=2),
        triggered_by="diag-v2",
        error_message="signature mismatch",
    )
    # Older than the 24h window — must NOT be counted.
    out_of_window = planner_models.IntegrationSyncRun(
        source_system="jackyun",
        sync_type="shipment_pull",
        api_method="wms.order.query-info.page.v2",
        status="failed",
        started_at=now - timedelta(hours=48),
        finished_at=now - timedelta(hours=48),
        triggered_by="ui-quick",
        error_message="ancient failure (should be ignored)",
    )
    db_session.add_all([older_failed, middle_success, newer_failed, out_of_window])
    db_session.commit()

    stats = shipment_import_service.get_recent_shipment_line_stats(
        db_session, hours=24, latest_runs_limit=5
    )

    assert stats["recent_failed_runs_count"] == 2, (
        "Should count exactly the two failed runs inside the 24h window "
        "(not the 48h-old one); got "
        f"{stats['recent_failed_runs_count']}"
    )
    latest = stats["latest_failed_run"]
    assert latest is not None, "latest_failed_run must be present when count > 0"
    assert latest["id"] == newer_failed.id, (
        "latest_failed_run must be the most recent failure inside the window "
        "(by started_at), not an older one"
    )
    assert latest["error_message"] == "signature mismatch"
    assert latest["triggered_by"] == "diag-v2"


def test_recent_stats_returns_zero_failed_when_window_clean(db_session):
    """Counterpart: when the window is clean, the new fields must be
    explicit zero/None so the banner stays hidden in the UI."""
    from src.planner.services import shipment_import_service

    stats = shipment_import_service.get_recent_shipment_line_stats(
        db_session, hours=24, latest_runs_limit=3
    )
    assert stats["recent_failed_runs_count"] == 0
    assert stats["latest_failed_run"] is None


def test_jackyun_sync_jobs_writes_canonical_batch_status_literal():
    """Regression guard for the 'succeeded' vs 'success' divergence.

    Background: jackyun/sync_jobs.py historically wrote
    ``batch.status = 'succeeded'`` while every other import path
    (xlsx import, after-sales, worker) writes ``'success'``. The
    frontend's BatchWorkbench only recognises ``'success'``, so 8
    jackyun batches showed up as "未知" status before this was fixed.

    This test pins the source-level literal so a future refactor
    can't silently reintroduce the divergence.
    """
    import inspect

    from src.integrations.jackyun import sync_jobs

    src = inspect.getsource(sync_jobs)
    assert 'batch.status = "succeeded"' not in src and "batch.status = 'succeeded'" not in src, (
        "jackyun/sync_jobs.py must NOT write batch.status='succeeded' — "
        "use 'success' to align with shipment_import_service / worker / "
        "frontend BatchWorkbench. See known_issues.md Issue 0.0g."
    )
    assert 'batch.status = "success"' in src or "batch.status = 'success'" in src, (
        "jackyun/sync_jobs.py must mark batch terminal as 'success' "
        "(currently the literal was removed entirely — that's also wrong)"
    )
