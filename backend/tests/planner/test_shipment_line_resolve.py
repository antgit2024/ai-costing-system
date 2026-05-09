"""Tests for Issue 29 — POST /shipments/lines/{id}/resolve.

The endpoint replaces the legacy 4-call frontend orchestration
(planner.ts::resolveShipmentLine). What we cover here:

- mark_long_tail / defer_modeling: governance-only paths
- adopt: end-to-end bind+governance+snapshot, idempotent re-run
- adopt with missing model_id → 200 ok=False (validation surfaces)
- missing sku_code on the line → 200 ok=False (precheck)
- nonexistent line id → 400 ValueError
- adopt with nonexistent SkuMaster → 200 ok=False (lookup_sku_master step in audit)
- governance + snapshot are skipped (snapshot_action=None) for non-adopt
- HTTP smoke test for the router wiring
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from src.planner import models
from src.planner.services import shipment_import_service, sku_master_service


def _seed_published_model(db, *, code: str, name: str):
    m = models.ProductModel(model_code=code, model_name=name, status="active", metadata_json={})
    db.add(m)
    db.flush()
    v = models.ProductModelVersion(
        model_id=m.id,
        version_kind="standard",
        version_status="published",
        version_label=f"{code}-STANDARD-001",
        metadata_json={"standard": {"width_mm": 1000, "height_mm": 1000, "quantity": 1}},
    )
    db.add(v)
    db.flush()
    return m, v


def _seed_pending_line(db, *, sku_code: str, spec_text: str = "", with_sku_master: bool = True):
    batch = models.ShipmentImportBatch(
        file_name="seed.xlsx",
        file_hash=uuid.uuid4().hex,
        export_date="2026-05-07",
        requested_by="tester",
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
    db.add(line)
    db.flush()

    if with_sku_master:
        sm = models.SkuMaster(erp_sku_barcode=sku_code, spec_text=spec_text, metadata_json={})
        db.add(sm)
        db.flush()

    db.commit()
    return batch.id, line.id


# ---------------------------------------------------------------------------
# Service-level
# ---------------------------------------------------------------------------


def test_resolve_unknown_action_raises(db_session):
    _, line_id = _seed_pending_line(db_session, sku_code="X-1")
    try:
        shipment_import_service.resolve_shipment_line(
            db_session, shipment_line_id=line_id, action="bogus"
        )
        assert False, "should raise"
    except ValueError as e:
        assert "unknown action" in str(e)


def test_resolve_missing_line_raises(db_session):
    try:
        shipment_import_service.resolve_shipment_line(
            db_session, shipment_line_id=str(uuid.uuid4()), action="mark_long_tail"
        )
        assert False, "should raise"
    except ValueError as e:
        assert "发货行不存在" in str(e)


def test_resolve_missing_sku_code_returns_soft_failure(db_session):
    """Line without sku_code → ok=False but no exception."""
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
    db_session.add(batch)
    db_session.flush()
    line = models.ShipmentLine(
        batch_id=batch.id,
        row_index=1,
        shipment_no="X",
        order_no="X",
        product_link_id="X",
        completed_at=datetime.now(timezone.utc),
        sku_code=None,  # KEY: no sku_code
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
    db_session.commit()

    res = shipment_import_service.resolve_shipment_line(
        db_session, shipment_line_id=line.id, action="mark_long_tail"
    )
    assert res["ok"] is False
    assert "sku_code" in (res["error"] or "").lower()
    assert res["steps"][0]["step"] == "precheck"


def test_resolve_mark_long_tail_writes_governance(db_session):
    _, line_id = _seed_pending_line(db_session, sku_code="LT-A")
    res = shipment_import_service.resolve_shipment_line(
        db_session,
        shipment_line_id=line_id,
        action="mark_long_tail",
        operator_id="alice",
    )
    assert res["ok"] is True
    assert res["snapshot_id"] is None  # governance-only
    assert res["snapshot_action"] is None
    sm = (
        db_session.query(models.SkuMaster)
        .filter_by(erp_sku_barcode="LT-A")
        .one()
    )
    assert (sm.metadata_json or {}).get("governance_status") == "do_not_model"
    assert (sm.metadata_json or {}).get("governance_decided_by") == "alice"


def test_resolve_defer_modeling_writes_pending_model(db_session):
    _, line_id = _seed_pending_line(db_session, sku_code="DEF-1")
    res = shipment_import_service.resolve_shipment_line(
        db_session, shipment_line_id=line_id, action="defer_modeling"
    )
    assert res["ok"] is True
    sm = (
        db_session.query(models.SkuMaster)
        .filter_by(erp_sku_barcode="DEF-1")
        .one()
    )
    assert (sm.metadata_json or {}).get("governance_status") == "pending_model"


def test_resolve_adopt_without_model_id_returns_soft_failure(db_session):
    _, line_id = _seed_pending_line(db_session, sku_code="A-1")
    res = shipment_import_service.resolve_shipment_line(
        db_session, shipment_line_id=line_id, action="adopt"
    )
    assert res["ok"] is False
    assert "model_id" in (res["error"] or "")


def test_resolve_adopt_missing_sku_master_returns_soft_failure(db_session):
    model, _ = _seed_published_model(db_session, code="042", name="画框-042")
    _, line_id = _seed_pending_line(
        db_session, sku_code="NO-MASTER-1", with_sku_master=False
    )
    res = shipment_import_service.resolve_shipment_line(
        db_session,
        shipment_line_id=line_id,
        action="adopt",
        model_id=str(model.id),
    )
    assert res["ok"] is False
    assert "未找到 SKU 主档" in (res["error"] or "")
    # Step audit should record the lookup attempt.
    step_names = [s["step"] for s in res["steps"]]
    assert "lookup_sku_master" in step_names


def test_resolve_adopt_full_path_binds_and_creates_snapshot(db_session):
    """End-to-end: bind + auto_bound + snapshot in one call."""
    model, version = _seed_published_model(db_session, code="060", name="画框-060")
    batch_id, line_id = _seed_pending_line(
        db_session, sku_code="ADOPT-1", spec_text="60画框 50*70"
    )

    res = shipment_import_service.resolve_shipment_line(
        db_session,
        shipment_line_id=line_id,
        action="adopt",
        model_id=str(model.id),
        operator_id="bob",
    )

    assert res["ok"] is True, res
    assert res["snapshot_action"] in ("created", "recomputed", "generated"), res
    assert res["snapshot_id"], res

    # Governance should be auto_bound now.
    sm = (
        db_session.query(models.SkuMaster)
        .filter_by(erp_sku_barcode="ADOPT-1")
        .one()
    )
    assert (sm.metadata_json or {}).get("governance_status") == "auto_bound"

    # Snapshot row exists for the line.
    snap = (
        db_session.query(models.BomSnapshot)
        .filter_by(shipment_line_id=line_id)
        .one()
    )
    assert snap is not None

    # Step audit covers all 4 stages.
    step_names = [s["step"] for s in res["steps"]]
    for expected in (
        "lookup_sku_master",
        "bind_sku_to_model",
        "set_governance_auto_bound",
        "compute_snapshot",
    ):
        assert expected in step_names, step_names


def test_resolve_adopt_idempotent_rerun(db_session):
    """Re-running adopt on the same line is safe (allow_rebind=True;
    compute_snapshot uses overwrite=True)."""
    model, _ = _seed_published_model(db_session, code="061", name="画框-061")
    _, line_id = _seed_pending_line(
        db_session, sku_code="REBIND-1", spec_text="61画框 50*70"
    )

    res1 = shipment_import_service.resolve_shipment_line(
        db_session, shipment_line_id=line_id, action="adopt", model_id=str(model.id)
    )
    assert res1["ok"] is True

    res2 = shipment_import_service.resolve_shipment_line(
        db_session, shipment_line_id=line_id, action="adopt", model_id=str(model.id)
    )
    assert res2["ok"] is True
    # Second run: snapshot should still exist (recomputed), not duplicated.
    snaps = (
        db_session.query(models.BomSnapshot)
        .filter_by(shipment_line_id=line_id)
        .count()
    )
    assert snaps == 1


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------


def test_http_resolve_mark_long_tail(client, db_session):
    _, line_id = _seed_pending_line(db_session, sku_code="HTTP-LT-1")
    resp = client.post(
        f"/api/planner/shipments/lines/{line_id}/resolve",
        json={"action": "mark_long_tail", "operator_id": "ui"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["action"] == "mark_long_tail"
    assert body["snapshot_id"] is None


def test_http_resolve_unknown_action_400(client, db_session):
    _, line_id = _seed_pending_line(db_session, sku_code="HTTP-X-1")
    resp = client.post(
        f"/api/planner/shipments/lines/{line_id}/resolve",
        json={"action": "noop"},
    )
    # FastAPI validates the Literal at the schema layer → 422.
    assert resp.status_code in (400, 422), resp.text


def test_http_resolve_unknown_line_400(client, db_session):
    resp = client.post(
        f"/api/planner/shipments/lines/{uuid.uuid4()}/resolve",
        json={"action": "mark_long_tail"},
    )
    assert resp.status_code == 400
    assert "发货行" in resp.json()["detail"]
