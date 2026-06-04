"""Sprint 2-2 contract tests for governance gating in
``shipment_import_service._finalize_shipment_line``.

These pin the worker behaviour when the SkuMaster row is in one of the
governance states. If the gating ever regresses (e.g. a refactor removes
the do_not_model branch) the long-tail SKUs will silently flood the
exception queue again — exactly what Sprint 2 was built to stop.
"""

from __future__ import annotations

from decimal import Decimal

from src.planner import models
from src.planner.services import (
    shipment_import_service,
    sku_master_service as sms,
)


def _seed_sku_with_governance(db_session, *, barcode: str, status: str):
    sku = models.SkuMaster(
        erp_sku_barcode=barcode,
        spec_text="颜色:红;尺寸:大",
        channel="天猫",
        metadata_json={"governance_status": status},
    )
    db_session.add(sku)
    db_session.flush()
    return sku


def _seed_batch_with_line(db_session, *, sku_code: str, file_hash: str):
    batch = models.ShipmentImportBatch(
        file_name=f"test-{sku_code}.xlsx",
        file_hash=file_hash,
        export_date="2026-05-06",
        requested_by="test",
        status="processing",
        result_json={"processor": "jackyun_existing_lines"},
    )
    db_session.add(batch)
    db_session.flush()
    line = models.ShipmentLine(
        batch_id=batch.id,
        row_index=1,
        shipment_no=f"S-{sku_code}",
        sku_code=sku_code,
        spec_text="颜色:红;尺寸:大",
        qty=Decimal("1"),
        revenue_amount=Decimal("99.9"),
        external_line_key_hash=f"h-{sku_code}",
        is_active=True,
    )
    db_session.add(line)
    db_session.flush()
    return batch, line


def test_do_not_model_skips_exception_queue_and_writes_long_tail_fallback(db_session):
    """Long-tail (do_not_model) SKU must never appear in the exception
    queue (that's the whole reason the operator marked it). Sprint 3-2
    additionally requires we generate a placeholder BomSnapshot +
    ShipmentCostingResult tagged as 'long_tail_fallback' so profit
    reports get an estimated cogs (settings.long_tail_cogs_rate * revenue).
    """
    _seed_sku_with_governance(
        db_session, barcode="LT-1", status=sms.GOVERNANCE_DO_NOT_MODEL
    )
    batch, line = _seed_batch_with_line(
        db_session, sku_code="LT-1", file_hash="h-lt-1"
    )

    snap = shipment_import_service._finalize_shipment_line(
        db_session, batch=batch, line=line
    )
    assert snap is not None, (
        "Sprint 3-2: do_not_model SKU should still produce a "
        "long_tail_fallback BomSnapshot so cogs are estimated"
    )
    assert (snap.trace_json or {}).get("kind") == "long_tail_fallback"
    rate = (snap.trace_json or {}).get("long_tail_cogs_rate")
    assert rate is not None and 0 < float(rate) < 1

    excs = (
        db_session.query(models.ShipmentExceptionQueue)
        .filter(models.ShipmentExceptionQueue.batch_id == batch.id)
        .all()
    )
    assert excs == [], "do_not_model SKU must NOT enter the exception queue"

    # Costing row must also be present and tagged as fallback.
    costing = (
        db_session.query(models.ShipmentCostingResult)
        .filter(models.ShipmentCostingResult.shipment_line_id == line.id)
        .first()
    )
    assert costing is not None
    assert (costing.metadata_json or {}).get("kind") == "long_tail_fallback"
    # cost_total = revenue * rate; here revenue=99.9 and rate=0.55 (default).
    assert costing.cost_total is not None and float(costing.cost_total) > 0

    assert (line.metadata_json or {}).get("skipped_reason") == "governance:do_not_model"


def test_do_not_model_fallback_can_be_disabled_via_settings(db_session, monkeypatch):
    """When ops disables the fallback (e.g. preferring no number over a
    wrong number), do_not_model SKUs really get zero cogs."""
    from src.config import settings

    monkeypatch.setattr(settings, "long_tail_cogs_fallback_enabled", False)

    _seed_sku_with_governance(
        db_session, barcode="LT-DISABLED", status=sms.GOVERNANCE_DO_NOT_MODEL
    )
    batch, line = _seed_batch_with_line(
        db_session, sku_code="LT-DISABLED", file_hash="h-lt-d"
    )

    snap = shipment_import_service._finalize_shipment_line(
        db_session, batch=batch, line=line
    )
    assert snap is None

    snaps = (
        db_session.query(models.BomSnapshot)
        .filter(models.BomSnapshot.batch_id == batch.id)
        .all()
    )
    assert snaps == []
    costing = (
        db_session.query(models.ShipmentCostingResult)
        .filter(models.ShipmentCostingResult.shipment_line_id == line.id)
        .first()
    )
    assert costing is None


def test_pending_model_enqueues_with_model_pending_reason(db_session):
    """pending_model SKU must enqueue with the new reason='MODEL_PENDING'
    so the BatchWorkbench UI can show a different action set ("modeling
    in progress") instead of the default "bind manually" prompt.
    """
    _seed_sku_with_governance(
        db_session, barcode="PM-1", status=sms.GOVERNANCE_PENDING_MODEL
    )
    batch, line = _seed_batch_with_line(
        db_session, sku_code="PM-1", file_hash="h-pm-1"
    )

    snap = shipment_import_service._finalize_shipment_line(
        db_session, batch=batch, line=line
    )
    assert snap is None
    db_session.flush()

    excs = (
        db_session.query(models.ShipmentExceptionQueue)
        .filter(models.ShipmentExceptionQueue.batch_id == batch.id)
        .all()
    )
    assert len(excs) == 1
    assert excs[0].reason == "MODEL_PENDING"
    assert excs[0].shipment_line_id == line.id
    payload = excs[0].payload_json or {}
    assert payload.get("governance_status") == sms.GOVERNANCE_PENDING_MODEL
    assert payload.get("sku_code") == "PM-1"

    assert batch.exception_rows == 1


def test_unmanaged_falls_through_to_default_sku_not_bound(db_session):
    """unmanaged SKU (the default state) must hit the original code path
    and produce SKU_NOT_BOUND when there's no model binding. This
    guards against an over-eager governance gate accidentally stealing
    the default-path traffic.
    """
    _seed_sku_with_governance(
        db_session, barcode="UM-1", status=sms.GOVERNANCE_UNMANAGED
    )
    batch, line = _seed_batch_with_line(
        db_session, sku_code="UM-1", file_hash="h-um-1"
    )

    shipment_import_service._finalize_shipment_line(
        db_session, batch=batch, line=line
    )
    db_session.flush()

    excs = (
        db_session.query(models.ShipmentExceptionQueue)
        .filter(models.ShipmentExceptionQueue.batch_id == batch.id)
        .all()
    )
    assert len(excs) == 1
    assert excs[0].reason == "SKU_NOT_BOUND"
