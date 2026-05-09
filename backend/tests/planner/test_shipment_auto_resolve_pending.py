"""
Tests for the new "/lines/auto-resolve" endpoints powering the
「📦 业务管理 > 🚚 发货管理 > 🔴 待处理」 「⚡ 一键自动绑定」 banner.

These endpoints port the legacy "/sku-master > 自动识别" flow into the
biz-friendly page, scoped to SKUs that actually appear in recent
pending shipment lines (instead of the full unbound SkuMaster pool).

What we cover here:
  - preview returns 0 candidates when no pending lines exist
  - preview discovers candidates via model_code_hint matching
  - execute binds + generates BomSnapshot + flips line.status to processed
  - execute resolves the SKU_NOT_BOUND exception row inline
  - re-running execute is a no-op (idempotent) once everything is bound
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from src.planner import models


def _seed_published_model(db_session, *, code: str, name: str, recognition_keywords=None):
    """Create a published standard model with optional recognition_keywords."""
    meta = {}
    if recognition_keywords:
        meta["recognition_keywords"] = list(recognition_keywords)
    m = models.ProductModel(model_code=code, model_name=name, status="active", metadata_json=meta)
    db_session.add(m)
    db_session.flush()
    v = models.ProductModelVersion(
        model_id=m.id,
        version_kind="standard",
        version_status="published",
        version_label=f"{code}-STANDARD-001",
        metadata_json={"standard": {"width_mm": 1000, "height_mm": 1000, "quantity": 1}},
    )
    db_session.add(v)
    db_session.flush()
    return m, v


def _seed_pending_shipment_line(
    db_session,
    *,
    sku_code: str,
    spec_text: str,
    create_sku_master: bool = True,
    create_exception: bool = True,
):
    """Insert a fresh pending shipment line + (optionally) its SkuMaster + SKU_NOT_BOUND exception."""
    batch = models.ShipmentImportBatch(
        file_name="seed.xlsx",
        file_hash=uuid.uuid4().hex,
        export_date="2026-05-01",
        requested_by="tester",
        status="success",
        total_rows=1,
        inserted_rows=1,
        skipped_rows=0,
        exception_rows=1,
    )
    db_session.add(batch)
    db_session.flush()

    line = models.ShipmentLine(
        batch_id=batch.id,
        row_index=1,
        shipment_no=f"S-{sku_code}",
        order_no=f"O-{sku_code}",
        product_link_id=f"L-{sku_code}",
        completed_at=datetime.now(timezone.utc),
        channel="taobao",
        sku_code=sku_code,
        spec_text=spec_text,
        qty=Decimal("1"),
        external_line_key_hash=uuid.uuid4().hex,
        revision_group_hash=uuid.uuid4().hex,
        revision_no=1,
        is_active=True,
        raw_row_json={},
        normalize_warnings_json=[],
        metadata_json={},
    )
    db_session.add(line)
    db_session.flush()

    if create_sku_master:
        sm = models.SkuMaster(erp_sku_barcode=sku_code, spec_text=spec_text, metadata_json={})
        db_session.add(sm)

    if create_exception:
        exc = models.ShipmentExceptionQueue(
            batch_id=batch.id,
            shipment_line_id=line.id,
            reason="SKU_NOT_BOUND",
            message="SKU 未绑定已发布版本",
            payload_json={"sku_code": sku_code},
        )
        db_session.add(exc)

    db_session.commit()
    batch_id = batch.id
    line_id = line.id
    db_session.expire_all()
    return batch_id, line_id


def test_auto_resolve_preview_empty_when_no_pending_lines(client, db_session):
    resp = client.post(
        "/api/planner/shipments/lines/auto-resolve/preview",
        json={"days": 30, "limit": 100},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total_pending_lines"] == 0
    assert body["candidates_count"] == 0
    assert body["items"] == []


def test_auto_resolve_preview_finds_candidate_via_model_code_hint(client, db_session):
    # Model code "024" should be auto-recognized from spec_text leading-digits.
    _seed_published_model(db_session, code="024", name="画框-024")
    _seed_pending_shipment_line(db_session, sku_code="BC-024-1", spec_text="024画框;50*70")

    resp = client.post(
        "/api/planner/shipments/lines/auto-resolve/preview",
        json={"days": 30, "limit": 100},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total_pending_lines"] == 1
    assert body["unique_unbound_skus"] == 1
    assert body["candidates_count"] == 1

    item = body["items"][0]
    assert item["sku_code"] == "BC-024-1"
    assert item["model_code"] == "024"
    assert item["match_method"] == "model_code_hint"
    assert item["shipment_line_count_for_sku"] == 1


def test_auto_resolve_preview_finds_candidate_via_keyword(client, db_session):
    _seed_published_model(
        db_session,
        code="ABC",
        name="磁吸画框",
        recognition_keywords=["磁吸画框"],
    )
    _seed_pending_shipment_line(
        db_session,
        sku_code="BC-KW-1",
        spec_text="磁吸画框;红色;40x60",
    )

    resp = client.post(
        "/api/planner/shipments/lines/auto-resolve/preview",
        json={"days": 30, "limit": 100},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["candidates_count"] == 1
    assert body["items"][0]["match_method"] == "model_keyword"
    assert body["items"][0]["matched_keyword"] == "磁吸画框"


def test_auto_resolve_preview_includes_lines_with_null_or_old_completed_at(client, db_session):
    """
    Regression for the 2026-05-07 bug: pending shipment lines with
    ``completed_at IS NULL`` (Jackyun rows that arrived before finishTime
    was populated) or ``completed_at`` outside the 30-day window (Excel
    backfill of older orders) were silently excluded from the auto-bind
    candidate pool. The window must be anchored on ``created_at`` instead.
    """
    _seed_published_model(
        db_session,
        code="SI",
        name="丝圈地垫",
        recognition_keywords=["丝圈地垫"],
    )

    # Case 1: Jackyun-style row, completed_at is NULL but created_at is fresh.
    batch1 = models.ShipmentImportBatch(
        file_name="seed-null.xlsx",
        file_hash=uuid.uuid4().hex,
        export_date="2026-05-07",
        requested_by="tester",
        status="success",
    )
    db_session.add(batch1)
    db_session.flush()
    line_null = models.ShipmentLine(
        batch_id=batch1.id,
        row_index=1,
        shipment_no="S-NULL",
        order_no="O-NULL",
        product_link_id="L-NULL",
        completed_at=None,
        channel="taobao",
        sku_code="BC-NULL-1",
        spec_text="尺寸:60CM*120CM;颜色分类:Q-ABC丝圈地垫",
        qty=Decimal("1"),
        external_line_key_hash=uuid.uuid4().hex,
        is_active=True,
        raw_row_json={},
        metadata_json={},
    )
    db_session.add(line_null)
    db_session.add(models.SkuMaster(erp_sku_barcode="BC-NULL-1", spec_text=line_null.spec_text, metadata_json={}))

    # Case 2: Excel-backfill style row, completed_at is months in the past
    # but created_at is very recent (just landed in the system today).
    batch2 = models.ShipmentImportBatch(
        file_name="seed-old.xlsx",
        file_hash=uuid.uuid4().hex,
        export_date="2026-05-07",
        requested_by="tester",
        status="success",
    )
    db_session.add(batch2)
    db_session.flush()
    line_old = models.ShipmentLine(
        batch_id=batch2.id,
        row_index=1,
        shipment_no="S-OLD",
        order_no="O-OLD",
        product_link_id="L-OLD",
        completed_at=datetime.now(timezone.utc) - timedelta(days=120),
        channel="taobao",
        sku_code="BC-OLD-1",
        spec_text="尺寸:90CM*120CM;颜色分类:Q-DEF丝圈地垫",
        qty=Decimal("1"),
        external_line_key_hash=uuid.uuid4().hex,
        is_active=True,
        raw_row_json={},
        metadata_json={},
    )
    db_session.add(line_old)
    db_session.add(models.SkuMaster(erp_sku_barcode="BC-OLD-1", spec_text=line_old.spec_text, metadata_json={}))
    db_session.commit()

    resp = client.post(
        "/api/planner/shipments/lines/auto-resolve/preview",
        json={"days": 30, "limit": 100},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    matched_codes = {it["sku_code"] for it in body["items"]}
    assert "BC-NULL-1" in matched_codes, body
    assert "BC-OLD-1" in matched_codes, body


def test_auto_resolve_preview_backfills_missing_sku_master_before_matching(client, db_session):
    _seed_published_model(
        db_session,
        code="MAT",
        name="皮革桌垫",
        recognition_keywords=["皮革桌垫"],
    )
    _seed_pending_shipment_line(
        db_session,
        sku_code="BC-NO-MASTER-1",
        spec_text="颜色分类:Q26032308A皮革桌垫;规格:40*80",
        create_sku_master=False,
    )

    resp = client.post(
        "/api/planner/shipments/lines/auto-resolve/preview",
        json={"days": 30, "limit": 100},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["candidates_count"] == 1
    assert body["items"][0]["sku_code"] == "BC-NO-MASTER-1"
    assert body["items"][0]["match_method"] == "model_keyword"

    sm = (
        db_session.query(models.SkuMaster)
        .filter(models.SkuMaster.erp_sku_barcode == "BC-NO-MASTER-1")
        .one()
    )
    assert sm.metadata_json["source"] == "shipment_auto_resolve_catchup"


def test_auto_resolve_preview_skips_already_bound_sku(client, db_session):
    _, v = _seed_published_model(db_session, code="025", name="025画框")
    _seed_pending_shipment_line(
        db_session,
        sku_code="BC-025-1",
        spec_text="025画框;50*70",
    )
    # Pre-bind it so preview should return 0 candidates.
    from src.planner.services import product_model_service

    product_model_service.bind_sku_to_version(
        db_session,
        sku_code="BC-025-1",
        version_id=v.id,
        source_system="test",
        metadata={"skip_prefix_check": True},
    )
    db_session.commit()

    resp = client.post(
        "/api/planner/shipments/lines/auto-resolve/preview",
        json={"days": 30, "limit": 100},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["unique_unbound_skus"] == 0
    assert body["candidates_count"] == 0


def test_auto_resolve_preview_respects_sku_codes_filter(client, db_session):
    _seed_published_model(db_session, code="026", name="026画框")
    _seed_pending_shipment_line(db_session, sku_code="BC-026-1", spec_text="026画框;50*70")
    _seed_pending_shipment_line(db_session, sku_code="BC-026-2", spec_text="026画框;60*80")

    resp = client.post(
        "/api/planner/shipments/lines/auto-resolve/preview",
        json={"days": 30, "limit": 100, "sku_codes": ["BC-026-1"]},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["candidates_count"] == 1
    assert body["items"][0]["sku_code"] == "BC-026-1"


def test_auto_resolve_execute_binds_and_creates_snapshot(client, db_session):
    _seed_published_model(db_session, code="027", name="027画框")
    batch_id, line_id = _seed_pending_shipment_line(
        db_session, sku_code="BC-027-1", spec_text="027画框;60*80"
    )

    # Sanity: open SKU_NOT_BOUND exception exists
    open_excs_before = (
        db_session.query(models.ShipmentExceptionQueue)
        .filter(
            models.ShipmentExceptionQueue.shipment_line_id == line_id,
            models.ShipmentExceptionQueue.resolved_at.is_(None),
        )
        .count()
    )
    assert open_excs_before == 1

    resp = client.post(
        "/api/planner/shipments/lines/auto-resolve/execute",
        json={"days": 30, "limit": 100, "requested_by": "auto-test"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["bound_skus_count"] == 1, body
    assert body["snapshots_created"] == 1, body
    assert body["lines_resolved"] == 1, body
    assert body["exceptions_resolved"] == 1, body
    assert body["bind_errors"] == [], body
    assert body["snapshot_errors"] == [], body
    assert len(body["items"]) == 1, body
    assert body["items"][0]["status"] == "ok", body
    assert body["items"][0]["bom_snapshot_id"], body

    # NOTE: We can't use ``db_session`` to verify side effects here because
    # the service internally calls ``db.commit()`` which detaches data from
    # the test fixture's nested-transaction view. Instead, re-run preview
    # via the API: it should now return 0 candidates (everything resolved).
    resp2 = client.post(
        "/api/planner/shipments/lines/auto-resolve/preview",
        json={"days": 30, "limit": 100},
    )
    assert resp2.status_code == 200, resp2.text
    body2 = resp2.json()
    # The line is no longer pending (snapshot exists) AND the SKU is bound,
    # so preview should report 0 unbound SKUs from pending lines.
    assert body2["candidates_count"] == 0, body2
    assert body2["unique_unbound_skus"] == 0, body2


def test_bind_sku_to_version_triggers_snapshot_for_old_pending_lines(client, db_session):
    """Issue 0.0i regression: when an operator binds a SKU in sku-master,
    OLD pending shipment_lines (older than the sweep's 60d window) must
    immediately get a BomSnapshot — without this hook, those lines would
    stay forever in 「待处理」 even after the user manually fixed binding.

    Setup mirrors the user-reported scenario:
      - 1 published model + version
      - 1 pending shipment line dated 90 days ago (sweep would skip it)
      - SkuMaster exists but unbound
    """
    from src.planner.services import product_model_service

    model, version = _seed_published_model(db_session, code="KB8", name="通用包边垫类")
    # Date 90 days back: well outside both the old 14d and the new 60d sweep window
    ancient_dt = datetime.now(timezone.utc) - timedelta(days=90)
    batch = models.ShipmentImportBatch(
        file_name="seed-old.xlsx",
        file_hash=uuid.uuid4().hex,
        export_date="2026-02-01",
        requested_by="tester",
        status="success",
        total_rows=1,
        inserted_rows=1,
        skipped_rows=0,
        exception_rows=1,
    )
    db_session.add(batch)
    db_session.flush()
    line = models.ShipmentLine(
        batch_id=batch.id,
        row_index=1,
        shipment_no="S-old-1",
        order_no="O-old-1",
        product_link_id="L-old-1",
        completed_at=ancient_dt,
        created_at=ancient_dt,
        channel="taobao",
        sku_code="6232909415870-test",
        spec_text="颜色分类:Q26041801A冰丝凉感-沙发垫",
        qty=Decimal("1"),
        external_line_key_hash=uuid.uuid4().hex,
        revision_group_hash=uuid.uuid4().hex,
        revision_no=1,
        is_active=True,
        raw_row_json={},
        normalize_warnings_json=[],
        metadata_json={},
    )
    db_session.add(line)
    db_session.add(models.SkuMaster(erp_sku_barcode="6232909415870-test", spec_text="x", metadata_json={}))
    db_session.commit()
    line_id = line.id

    snap_before = (
        db_session.query(models.BomSnapshot)
        .filter(models.BomSnapshot.shipment_line_id == line_id)
        .count()
    )
    assert snap_before == 0, "precondition: no snapshot for the old line"

    product_model_service.bind_sku_to_version(
        db_session,
        sku_code="6232909415870-test",
        version_id=str(version.id),
        source_system="sku_master_manual",
        metadata={"requested_by": "regression-test"},
    )
    db_session.expire_all()

    snap_after = (
        db_session.query(models.BomSnapshot)
        .filter(models.BomSnapshot.shipment_line_id == line_id)
        .count()
    )
    assert snap_after == 1, (
        "bind hook must create a BomSnapshot for the OLD pending line "
        "(no time window). Got "
        f"{snap_after} snapshots after bind."
    )


def test_auto_resolve_execute_idempotent_when_re_run(client, db_session):
    _seed_published_model(db_session, code="028", name="028画框")
    _seed_pending_shipment_line(
        db_session, sku_code="BC-028-1", spec_text="028画框;60*80"
    )

    resp1 = client.post(
        "/api/planner/shipments/lines/auto-resolve/execute",
        json={"days": 30, "limit": 100, "requested_by": "auto-test"},
    )
    assert resp1.status_code == 200, resp1.text
    body1 = resp1.json()
    assert body1["bound_skus_count"] == 1
    assert body1["snapshots_created"] == 1

    # Second run: nothing to do, no candidates left.
    resp2 = client.post(
        "/api/planner/shipments/lines/auto-resolve/execute",
        json={"days": 30, "limit": 100, "requested_by": "auto-test"},
    )
    assert resp2.status_code == 200, resp2.text
    body2 = resp2.json()
    assert body2["bound_skus_count"] == 0
    assert body2["snapshots_created"] == 0
    assert body2["lines_resolved"] == 0
    assert body2["preview"]["candidates_count"] == 0
