"""Sprint 2-1 unit tests for SKU governance state machine.

Covers ``sku_master_service.set_sku_governance``,
``is_do_not_model``, ``list_governance_backlog``,
``auto_promote_pending_model`` — the 4 functions the worker /
exception-queue UI / model-publish flow rely on.

Why each test exists:
  * State transitions must be validated (the worker behaviour
    branches on these states; a typo silently hides SKUs).
  * Audit history must persist (compliance + debugging).
  * The backlog list must include shipment stats so the UI can
    sort by sales potential (the whole point of "建模 Backlog").
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from src.planner import models
from src.planner.services import sku_master_service as sms


def _make_sku(db_session, barcode: str, **meta_overrides):
    sku = models.SkuMaster(
        erp_sku_barcode=barcode,
        spec_text="颜色:红;尺寸:大",
        channel="天猫",
        metadata_json=meta_overrides or {},
    )
    db_session.add(sku)
    db_session.flush()
    return sku


def _make_shipment_line(
    db_session,
    sku_code: str,
    *,
    qty: float = 1.0,
    revenue: float = 100.0,
    completed_days_ago: int = 1,
):
    """Helper to seed a ShipmentLine for backlog stats tests."""
    completed = datetime.now(timezone.utc) - timedelta(days=completed_days_ago)
    # Need a ShipmentImportBatch FK
    batch = models.ShipmentImportBatch(
        file_name="test.xlsx",
        file_hash=f"h-{sku_code}-{completed_days_ago}",
        export_date="2026-05-06",
        requested_by="test",
        status="success",
    )
    db_session.add(batch)
    db_session.flush()
    line = models.ShipmentLine(
        batch_id=batch.id,
        row_index=1,
        shipment_no=f"S-{sku_code}-{completed_days_ago}",
        sku_code=sku_code,
        spec_text="颜色:红;尺寸:大",
        qty=Decimal(str(qty)),
        revenue_amount=Decimal(str(revenue)),
        external_line_key_hash=f"h-line-{sku_code}-{completed_days_ago}",
        completed_at=completed,
        is_active=True,
    )
    db_session.add(line)
    db_session.flush()
    return line


# -----------------------------------------------------------------
# get_sku_governance_status / is_do_not_model
# -----------------------------------------------------------------


def test_get_sku_governance_status_defaults_to_unmanaged_for_none(db_session):
    """Defensive: callers (worker) hand us None when SKU not built yet."""
    assert sms.get_sku_governance_status(None) == sms.GOVERNANCE_UNMANAGED


def test_get_sku_governance_status_returns_unmanaged_when_meta_missing(db_session):
    sku = _make_sku(db_session, "B-A1")
    assert sms.get_sku_governance_status(sku) == sms.GOVERNANCE_UNMANAGED
    assert not sms.is_do_not_model(sku)


def test_is_do_not_model_true_when_marked(db_session):
    sku = _make_sku(db_session, "B-A2", governance_status=sms.GOVERNANCE_DO_NOT_MODEL)
    assert sms.is_do_not_model(sku) is True
    assert sms.is_pending_model(sku) is False


# -----------------------------------------------------------------
# set_sku_governance
# -----------------------------------------------------------------


def test_set_sku_governance_rejects_unknown_status(db_session):
    with pytest.raises(ValueError, match="Unknown governance status"):
        sms.set_sku_governance(db_session, sku_codes=["X"], status="bogus")


def test_set_sku_governance_updates_and_writes_audit(db_session):
    sku = _make_sku(db_session, "B-T1")

    counters = sms.set_sku_governance(
        db_session,
        sku_codes=["B-T1"],
        status=sms.GOVERNANCE_DO_NOT_MODEL,
        decided_by="ops-jane",
        note="一年只卖一单",
    )
    assert counters == {"updated": 1, "unchanged": 0, "missing": 0}

    db_session.refresh(sku)
    meta = sku.metadata_json
    assert meta["governance_status"] == sms.GOVERNANCE_DO_NOT_MODEL
    assert meta["governance_decided_by"] == "ops-jane"
    assert meta["governance_note"] == "一年只卖一单"
    assert meta.get("governance_decided_at"), "must record decision timestamp"
    history = meta.get("governance_history") or []
    assert len(history) == 1
    h0 = history[0]
    assert h0["from"] == sms.GOVERNANCE_UNMANAGED
    assert h0["to"] == sms.GOVERNANCE_DO_NOT_MODEL
    assert h0["by"] == "ops-jane"
    assert h0["note"] == "一年只卖一单"


def test_set_sku_governance_is_idempotent(db_session):
    """Re-applying the same status must not duplicate audit entries."""
    sku = _make_sku(db_session, "B-T2")

    sms.set_sku_governance(
        db_session, sku_codes=["B-T2"], status=sms.GOVERNANCE_PENDING_MODEL
    )
    counters_2 = sms.set_sku_governance(
        db_session, sku_codes=["B-T2"], status=sms.GOVERNANCE_PENDING_MODEL
    )

    assert counters_2 == {"updated": 0, "unchanged": 1, "missing": 0}
    db_session.refresh(sku)
    history = sku.metadata_json.get("governance_history") or []
    assert len(history) == 1, "no-op transitions must not append to history"


def test_set_sku_governance_counts_missing_barcodes(db_session):
    _make_sku(db_session, "B-T3")
    counters = sms.set_sku_governance(
        db_session,
        sku_codes=["B-T3", "DOES-NOT-EXIST", "ALSO-MISSING"],
        status=sms.GOVERNANCE_PENDING_MODEL,
    )
    assert counters["updated"] == 1
    assert counters["missing"] == 2
    assert counters["unchanged"] == 0


def test_set_sku_governance_caps_history_at_20_entries(db_session):
    sku = _make_sku(db_session, "B-T4")
    statuses = [
        sms.GOVERNANCE_PENDING_MODEL,
        sms.GOVERNANCE_DO_NOT_MODEL,
        sms.GOVERNANCE_UNMANAGED,
    ]
    for i in range(25):
        sms.set_sku_governance(
            db_session,
            sku_codes=["B-T4"],
            status=statuses[i % len(statuses)],
            decided_by=f"u{i}",
        )
    db_session.refresh(sku)
    history = sku.metadata_json.get("governance_history") or []
    assert len(history) == 20, "history must be capped at last 20 entries"


# -----------------------------------------------------------------
# list_governance_backlog
# -----------------------------------------------------------------


def test_list_governance_backlog_filters_by_status(db_session):
    _make_sku(db_session, "B-L1", governance_status=sms.GOVERNANCE_PENDING_MODEL)
    _make_sku(db_session, "B-L2", governance_status=sms.GOVERNANCE_PENDING_MODEL)
    _make_sku(db_session, "B-L3", governance_status=sms.GOVERNANCE_DO_NOT_MODEL)
    _make_sku(db_session, "B-L4")  # unmanaged

    out = sms.list_governance_backlog(
        db_session, status=sms.GOVERNANCE_PENDING_MODEL
    )
    assert out["total"] == 2
    barcodes = {it["erp_sku_barcode"] for it in out["items"]}
    assert barcodes == {"B-L1", "B-L2"}


def test_list_governance_backlog_attaches_shipment_stats(db_session):
    _make_sku(db_session, "B-L5", governance_status=sms.GOVERNANCE_PENDING_MODEL)
    _make_shipment_line(
        db_session, "B-L5", qty=3, revenue=999.0, completed_days_ago=2
    )
    _make_shipment_line(
        db_session, "B-L5", qty=1, revenue=99.0, completed_days_ago=5
    )

    out = sms.list_governance_backlog(
        db_session,
        status=sms.GOVERNANCE_PENDING_MODEL,
        sales_window_days=30,
    )
    assert out["total"] == 1
    item = out["items"][0]
    assert item["erp_sku_barcode"] == "B-L5"
    assert float(item["qty_window"]) == 4.0
    assert float(item["revenue_window"]) == 1098.0
    assert item["line_count_window"] == 2
    assert item["last_shipment_at"] is not None


def test_list_governance_backlog_orders_by_revenue_desc(db_session):
    """Sorting by 'shipment_score' (default) must put highest-revenue first
    so the modeling backlog UI surfaces high-impact SKUs at the top."""
    _make_sku(db_session, "B-L6", governance_status=sms.GOVERNANCE_PENDING_MODEL)
    _make_sku(db_session, "B-L7", governance_status=sms.GOVERNANCE_PENDING_MODEL)
    _make_sku(db_session, "B-L8", governance_status=sms.GOVERNANCE_PENDING_MODEL)
    _make_shipment_line(db_session, "B-L6", revenue=10.0)
    _make_shipment_line(db_session, "B-L7", revenue=5000.0)
    _make_shipment_line(db_session, "B-L8", revenue=200.0)

    out = sms.list_governance_backlog(
        db_session, status=sms.GOVERNANCE_PENDING_MODEL
    )
    ordered = [it["erp_sku_barcode"] for it in out["items"]]
    assert ordered == ["B-L7", "B-L8", "B-L6"]


def test_list_governance_backlog_paginates(db_session):
    for i in range(7):
        _make_sku(
            db_session,
            f"B-P{i}",
            governance_status=sms.GOVERNANCE_DO_NOT_MODEL,
        )
    page1 = sms.list_governance_backlog(
        db_session, status=sms.GOVERNANCE_DO_NOT_MODEL, page=1, page_size=3
    )
    page3 = sms.list_governance_backlog(
        db_session, status=sms.GOVERNANCE_DO_NOT_MODEL, page=3, page_size=3
    )
    assert page1["total"] == 7
    assert len(page1["items"]) == 3
    assert len(page3["items"]) == 1


# -----------------------------------------------------------------
# auto_promote_pending_model
# -----------------------------------------------------------------


def test_auto_promote_pending_model_promotes_only_pending(db_session):
    """Only ``pending_model`` SKUs may be auto-promoted; others are skipped.

    This guarantees that publishing a model never overwrites a deliberate
    ``do_not_model`` decision (ops protection).
    """
    _make_sku(db_session, "B-AP1", governance_status=sms.GOVERNANCE_PENDING_MODEL)
    _make_sku(db_session, "B-AP2", governance_status=sms.GOVERNANCE_DO_NOT_MODEL)
    _make_sku(db_session, "B-AP3")  # unmanaged

    counters = sms.auto_promote_pending_model(
        db_session,
        sku_codes=["B-AP1", "B-AP2", "B-AP3", "B-MISSING"],
        decided_by="model-publish-job",
    )
    assert counters == {"promoted": 1, "skipped": 2, "missing": 1}

    sku1 = sms.get_by_barcode(db_session, "B-AP1")
    sku2 = sms.get_by_barcode(db_session, "B-AP2")
    sku3 = sms.get_by_barcode(db_session, "B-AP3")
    assert sms.get_sku_governance_status(sku1) == sms.GOVERNANCE_AUTO_BOUND
    assert sms.get_sku_governance_status(sku2) == sms.GOVERNANCE_DO_NOT_MODEL
    assert sms.get_sku_governance_status(sku3) == sms.GOVERNANCE_UNMANAGED

    history = sku1.metadata_json.get("governance_history") or []
    assert history[-1]["to"] == sms.GOVERNANCE_AUTO_BOUND
    assert history[-1]["by"] == "model-publish-job"


def test_auto_promote_pending_model_is_idempotent(db_session):
    _make_sku(db_session, "B-AP4", governance_status=sms.GOVERNANCE_PENDING_MODEL)
    sms.auto_promote_pending_model(db_session, sku_codes=["B-AP4"])
    counters_2 = sms.auto_promote_pending_model(
        db_session, sku_codes=["B-AP4"]
    )
    assert counters_2 == {"promoted": 0, "skipped": 1, "missing": 0}
