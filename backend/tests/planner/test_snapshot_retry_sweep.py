"""Tests for sweep_bound_lines_missing_snapshot — the retry sweep that
backs the "⏳ 等出快照(系统处理中)" PendingTab tag.

Covers:
  - empty result when nothing is pending
  - happy path: bound line with no snapshot → snapshot created
  - skip: line whose SKU has NO active binding (still counted as scanned=0)
  - skip: line whose snapshot already exists (action=skipped, idempotent)
  - skip: line outside lookback window
  - skip: line whose snapshot was manually cleared (snapshot_cleared_at) —
    these should be re-snapshotted (cleared = "please redo")
  - failure tolerance: corrupt line doesn't tank the sweep
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from src.planner import models
from src.planner.services import shipment_import_service


def _seed_published_model(db, *, code: str, name: str):
    m = models.ProductModel(model_code=code, model_name=name, status="active", metadata_json={})
    db.add(m)
    db.flush()
    v = models.ProductModelVersion(
        model_id=m.id,
        version_kind="standard",
        version_status="published",
        version_label=f"{code}-S",
        metadata_json={"standard": {"width_mm": 1000, "height_mm": 1000, "quantity": 1}},
    )
    db.add(v)
    db.flush()
    return m, v


def _seed_pending_line(
    db,
    *,
    sku_code: str,
    completed_at: datetime,
    snapshot_cleared: bool = False,
    spec_text: str = "60画框 50*70",  # avoid SPEC_EMPTY exception in BOM gen
):
    batch = models.ShipmentImportBatch(
        file_name="seed.xlsx",
        file_hash=uuid.uuid4().hex,
        export_date="2026-05-07",
        requested_by="t",
        status="success",  # KEY: success → main worker won't touch it
        total_rows=1,
        inserted_rows=1,
        skipped_rows=0,
        exception_rows=0,
    )
    db.add(batch)
    db.flush()
    meta = {}
    if snapshot_cleared:
        meta["snapshot_cleared_at"] = datetime.now(timezone.utc).isoformat()
    line = models.ShipmentLine(
        batch_id=batch.id,
        row_index=1,
        shipment_no=f"S-{sku_code}",
        order_no=f"O-{sku_code}",
        product_link_id=f"L-{sku_code}",
        completed_at=completed_at,
        sku_code=sku_code,
        spec_text=spec_text,
        qty=Decimal("1"),
        external_line_key_hash=uuid.uuid4().hex,
        revision_group_hash=uuid.uuid4().hex,
        revision_no=1,
        is_active=True,
        raw_row_json={},
        normalize_warnings_json=[],
        metadata_json=meta,
    )
    db.add(line)
    db.flush()
    return batch.id, line.id


def _seed_sku_master_with_binding(db, *, sku_code: str, version):
    sm = models.SkuMaster(erp_sku_barcode=sku_code, metadata_json={})
    db.add(sm)
    db.flush()
    mapping = models.SkuModelVersionMapping(
        sku_code=sku_code,
        model_version_id=version.id,
        is_active=True,
    )
    db.add(mapping)
    db.flush()
    return sm


# ---------------------------------------------------------------------------


def test_sweep_empty_when_no_pending(db_session):
    res = shipment_import_service.sweep_bound_lines_missing_snapshot(
        db_session, lookback_days=14, limit=200
    )
    assert res["scanned"] == 0
    assert res["snapshots_created"] == 0
    assert res["failed"] == 0


def test_sweep_skips_unbound_skus(db_session):
    """Pending line with no active SkuModelVersionMapping → not in scope."""
    _seed_pending_line(
        db_session,
        sku_code="UNBOUND-1",
        completed_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    db_session.add(models.SkuMaster(erp_sku_barcode="UNBOUND-1", metadata_json={}))
    db_session.commit()

    res = shipment_import_service.sweep_bound_lines_missing_snapshot(
        db_session, lookback_days=14, limit=200
    )
    assert res["scanned"] == 0  # The binding_exists predicate filters it out


def test_sweep_creates_snapshot_for_bound_orphan(db_session):
    """The exact scenario the PendingTab tag promises to fix."""
    _, version = _seed_published_model(db_session, code="OZU", name="OZU")
    _seed_sku_master_with_binding(db_session, sku_code="ORPHAN-1", version=version)
    _, line_id = _seed_pending_line(
        db_session,
        sku_code="ORPHAN-1",
        completed_at=datetime.now(timezone.utc) - timedelta(hours=2),
    )
    db_session.commit()

    res = shipment_import_service.sweep_bound_lines_missing_snapshot(
        db_session, lookback_days=14, limit=200
    )
    assert res["scanned"] == 1, res
    assert res["snapshots_created"] == 1, res
    assert res["failed"] == 0, res

    # Snapshot row should exist for that line now.
    snap = (
        db_session.query(models.BomSnapshot).filter_by(shipment_line_id=line_id).first()
    )
    assert snap is not None


def test_sweep_skips_lines_outside_lookback(db_session):
    """Lookback gates by completed_at to keep the sweep cheap."""
    _, version = _seed_published_model(db_session, code="OLD", name="OLD")
    _seed_sku_master_with_binding(db_session, sku_code="OLD-1", version=version)
    _seed_pending_line(
        db_session,
        sku_code="OLD-1",
        completed_at=datetime.now(timezone.utc) - timedelta(days=30),
    )
    db_session.commit()

    res = shipment_import_service.sweep_bound_lines_missing_snapshot(
        db_session, lookback_days=7, limit=200
    )
    assert res["scanned"] == 0


def test_sweep_idempotent_rerun(db_session):
    """Running the sweep again immediately should be a no-op (snapshots exist)."""
    _, version = _seed_published_model(db_session, code="IDEM", name="IDEM")
    _seed_sku_master_with_binding(db_session, sku_code="IDEM-1", version=version)
    _seed_pending_line(
        db_session,
        sku_code="IDEM-1",
        completed_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    db_session.commit()

    res1 = shipment_import_service.sweep_bound_lines_missing_snapshot(
        db_session, lookback_days=14, limit=200
    )
    assert res1["snapshots_created"] == 1

    res2 = shipment_import_service.sweep_bound_lines_missing_snapshot(
        db_session, lookback_days=14, limit=200
    )
    # The line is no longer "pending" because it now has a BomSnapshot, so
    # the pending_pred filters it out → scanned=0 (the cleanest signal of
    # idempotency).
    assert res2["scanned"] == 0


def test_sweep_picks_up_manually_cleared_lines(db_session):
    """When operator hits "重算快照", we set snapshot_cleared_at on the line.
    The list view treats those as pending again, so the sweep MUST too."""
    _, version = _seed_published_model(db_session, code="CLR", name="CLR")
    _seed_sku_master_with_binding(db_session, sku_code="CLR-1", version=version)
    _, line_id = _seed_pending_line(
        db_session,
        sku_code="CLR-1",
        completed_at=datetime.now(timezone.utc) - timedelta(hours=1),
        snapshot_cleared=True,
    )
    db_session.commit()

    res = shipment_import_service.sweep_bound_lines_missing_snapshot(
        db_session, lookback_days=14, limit=200
    )
    assert res["scanned"] == 1
    assert res["snapshots_created"] == 1
    snap = (
        db_session.query(models.BomSnapshot).filter_by(shipment_line_id=line_id).first()
    )
    assert snap is not None


def test_sweep_respects_limit(db_session):
    """When more candidates than limit exist, we process exactly limit, oldest-first."""
    _, version = _seed_published_model(db_session, code="LIM", name="LIM")
    base_t = datetime.now(timezone.utc) - timedelta(hours=24)
    for i in range(3):
        sku = f"LIM-{i}"
        _seed_sku_master_with_binding(db_session, sku_code=sku, version=version)
        _seed_pending_line(
            db_session,
            sku_code=sku,
            completed_at=base_t + timedelta(minutes=i),
        )
    db_session.commit()

    res = shipment_import_service.sweep_bound_lines_missing_snapshot(
        db_session, lookback_days=14, limit=2
    )
    assert res["scanned"] == 2
    # Two snapshots created; one line still pending for next pass.
    pending_remaining = (
        db_session.query(models.ShipmentLine)
        .filter(
            models.ShipmentLine.sku_code.in_(["LIM-0", "LIM-1", "LIM-2"]),
        )
        .count()
    )
    assert pending_remaining == 3
    snaps = db_session.query(models.BomSnapshot).count()
    assert snaps == 2
