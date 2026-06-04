"""Tests for POST /shipments/lines/bulk-resolve (Issue 29 follow-up).

Validates that the bulk endpoint:
  - is a no-op for empty input
  - reports per-row results matching the single-row endpoint
  - keeps going on per-row failure (default best-effort)
  - honors stop_on_first_error=true (skips the rest with explicit reason)
  - never lets one bad row tank the whole batch (governance writes from
    earlier successful rows are still committed)
  - HTTP smoke test for router wiring + summary counts
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from src.planner import models
from src.planner.services import shipment_import_service


def _seed_pending_line(db, *, sku_code: str, with_sku_master: bool = True):
    batch = models.ShipmentImportBatch(
        file_name="seed.xlsx",
        file_hash=uuid.uuid4().hex,
        export_date="2026-05-07",
        requested_by="t",
        status="success",
        total_rows=1,
        inserted_rows=1,
        skipped_rows=0,
        exception_rows=0,
    )
    db.add(batch)
    db.flush()
    line = models.ShipmentLine(
        batch_id=batch.id,
        row_index=1,
        shipment_no=f"S-{sku_code}",
        order_no=f"O-{sku_code}",
        product_link_id=f"L-{sku_code}",
        completed_at=datetime.now(timezone.utc),
        sku_code=sku_code,
        spec_text="",
        qty=Decimal("1"),
        external_line_key_hash=uuid.uuid4().hex,
        revision_group_hash=uuid.uuid4().hex,
        revision_no=1,
        is_active=True,
        raw_row_json={},
        normalize_warnings_json=[],
        metadata_json={},
    )
    db.add(line)
    db.flush()
    if with_sku_master:
        db.add(models.SkuMaster(erp_sku_barcode=sku_code, metadata_json={}))
        db.flush()
    db.commit()
    return line.id


# ---------------------------------------------------------------------------
# Service-level
# ---------------------------------------------------------------------------


def test_bulk_resolve_empty_returns_zero(db_session):
    res = shipment_import_service.bulk_resolve_shipment_lines(db_session, items=[])
    assert res["total"] == 0
    assert res["succeeded"] == 0
    assert res["failed"] == 0
    assert res["results"] == []


def test_bulk_resolve_rejects_non_list(db_session):
    try:
        shipment_import_service.bulk_resolve_shipment_lines(db_session, items="oops")  # type: ignore[arg-type]
        assert False, "should raise"
    except ValueError as e:
        assert "items must be a list" in str(e)


def test_bulk_resolve_all_defer_modeling_succeeds(db_session):
    line_a = _seed_pending_line(db_session, sku_code="BULK-A")
    line_b = _seed_pending_line(db_session, sku_code="BULK-B")
    line_c = _seed_pending_line(db_session, sku_code="BULK-C")

    res = shipment_import_service.bulk_resolve_shipment_lines(
        db_session,
        items=[
            {"shipment_line_id": line_a, "action": "defer_modeling"},
            {"shipment_line_id": line_b, "action": "defer_modeling"},
            {"shipment_line_id": line_c, "action": "defer_modeling"},
        ],
        operator_id="bulker",
    )
    assert res["total"] == 3
    assert res["succeeded"] == 3
    assert res["failed"] == 0

    # All three SKUs should be in pending_model now.
    for code in ("BULK-A", "BULK-B", "BULK-C"):
        sm = db_session.query(models.SkuMaster).filter_by(erp_sku_barcode=code).one()
        assert (sm.metadata_json or {}).get("governance_status") == "pending_model"


def test_bulk_resolve_best_effort_continues_after_failure(db_session):
    """Default (stop_on_first_error=False): one bad row, others still apply."""
    good_id = _seed_pending_line(db_session, sku_code="GOOD-1")
    bogus_id = str(uuid.uuid4())
    other_good_id = _seed_pending_line(db_session, sku_code="GOOD-2")

    res = shipment_import_service.bulk_resolve_shipment_lines(
        db_session,
        items=[
            {"shipment_line_id": good_id, "action": "mark_long_tail"},
            {"shipment_line_id": bogus_id, "action": "mark_long_tail"},
            {"shipment_line_id": other_good_id, "action": "mark_long_tail"},
        ],
    )
    assert res["total"] == 3
    assert res["succeeded"] == 2
    assert res["failed"] == 1
    assert res["skipped_after_error"] == 0

    # Verify the failure row carries the underlying ValueError detail.
    bad_row = next(r for r in res["results"] if r["shipment_line_id"] == bogus_id)
    assert bad_row["ok"] is False
    assert "发货行" in (bad_row["error"] or "")

    # Both GOOD-1 and GOOD-2 should be do_not_model.
    for code in ("GOOD-1", "GOOD-2"):
        sm = db_session.query(models.SkuMaster).filter_by(erp_sku_barcode=code).one()
        assert (sm.metadata_json or {}).get("governance_status") == "do_not_model"


def test_bulk_resolve_stop_on_first_error_skips_rest(db_session):
    line_a = _seed_pending_line(db_session, sku_code="STOP-A")
    bogus = str(uuid.uuid4())
    line_c = _seed_pending_line(db_session, sku_code="STOP-C")

    res = shipment_import_service.bulk_resolve_shipment_lines(
        db_session,
        items=[
            {"shipment_line_id": bogus, "action": "mark_long_tail"},
            {"shipment_line_id": line_a, "action": "mark_long_tail"},
            {"shipment_line_id": line_c, "action": "mark_long_tail"},
        ],
        stop_on_first_error=True,
    )
    assert res["total"] == 3
    assert res["succeeded"] == 0
    assert res["failed"] == 1
    assert res["skipped_after_error"] == 2

    # The two skipped entries carry the standardized reason.
    skipped = [r for r in res["results"] if "skipped after earlier failure" in (r["error"] or "")]
    assert len(skipped) == 2

    # STOP-A and STOP-C must NOT have been touched.
    for code in ("STOP-A", "STOP-C"):
        sm = db_session.query(models.SkuMaster).filter_by(erp_sku_barcode=code).one()
        meta = sm.metadata_json or {}
        assert meta.get("governance_status") in (None, "unmanaged")


def test_bulk_resolve_handles_garbage_item_entry(db_session):
    """A non-dict element in items[] should turn into a per-row failure,
    not crash the whole batch."""
    good_id = _seed_pending_line(db_session, sku_code="MIX-1")
    res = shipment_import_service.bulk_resolve_shipment_lines(
        db_session,
        items=[
            "not a dict",  # type: ignore[list-item]
            {"shipment_line_id": good_id, "action": "mark_long_tail"},
        ],
    )
    assert res["total"] == 2
    assert res["succeeded"] == 1
    assert res["failed"] == 1
    bad_row = res["results"][0]
    assert bad_row["ok"] is False
    assert "must be an object" in (bad_row["error"] or "")


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------


def test_http_bulk_resolve_summary_counts(client, db_session):
    line_a = _seed_pending_line(db_session, sku_code="HTTP-BULK-A")
    line_b = _seed_pending_line(db_session, sku_code="HTTP-BULK-B")

    resp = client.post(
        "/api/planner/shipments/lines/bulk-resolve",
        json={
            "items": [
                {"shipment_line_id": line_a, "action": "defer_modeling"},
                {"shipment_line_id": line_b, "action": "defer_modeling"},
            ],
            "operator_id": "ui-bulk",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 2
    assert body["succeeded"] == 2
    assert body["failed"] == 0
    assert len(body["results"]) == 2
    assert all(r["ok"] for r in body["results"])
    assert body["total_duration_ms"] >= 0


def test_http_bulk_resolve_validates_action_literal(client):
    """FastAPI validates Literal at the schema layer → 422 before any DB hit."""
    resp = client.post(
        "/api/planner/shipments/lines/bulk-resolve",
        json={"items": [{"shipment_line_id": str(uuid.uuid4()), "action": "noop"}]},
    )
    assert resp.status_code == 422
