"""Sprint 2-3 HTTP-level tests for /api/planner/sku-master/governance.

These guard the wire contract with the BatchWorkbench UI:
  POST /sku-master/governance                    -> {updated, unchanged, missing}
  GET  /sku-master/governance?status=...         -> {items, total, ...}
  POST /sku-master/governance/promote-from-model -> {promoted, skipped, missing}

Frontend pages (异常队列 4 个动作按钮 / 建模 Backlog Tab / 长尾 SKU Tab)
will speak this contract directly. Breaking it is a UX-visible
production regression.
"""

from __future__ import annotations

from src.planner import models
from src.planner.services import sku_master_service as sms


def _seed_sku(db_session, barcode: str, **meta_overrides):
    sku = models.SkuMaster(
        erp_sku_barcode=barcode,
        spec_text="颜色:红;尺寸:大",
        channel="天猫",
        metadata_json=meta_overrides or {},
    )
    db_session.add(sku)
    db_session.flush()
    return sku


def test_post_governance_sets_status_and_writes_audit(client, db_session):
    _seed_sku(db_session, "B-R1")
    db_session.commit()

    resp = client.post(
        "/api/planner/sku-master/governance",
        json={
            "sku_codes": ["B-R1"],
            "status": "do_not_model",
            "decided_by": "ops-jane",
            "note": "一年只卖一单",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body == {"updated": 1, "unchanged": 0, "missing": 0}

    sku = sms.get_by_barcode(db_session, "B-R1")
    assert sms.is_do_not_model(sku) is True
    assert sku.metadata_json["governance_decided_by"] == "ops-jane"
    assert sku.metadata_json["governance_history"][0]["from"] == "unmanaged"
    assert sku.metadata_json["governance_history"][0]["to"] == "do_not_model"


def test_post_governance_rejects_unknown_status(client, db_session):
    resp = client.post(
        "/api/planner/sku-master/governance",
        json={"sku_codes": ["B-R2"], "status": "garbage"},
    )
    assert resp.status_code == 400
    assert "Unknown governance status" in resp.json()["detail"]


def test_get_governance_lists_by_status_with_stats(client, db_session):
    _seed_sku(db_session, "B-R3", governance_status="pending_model")
    _seed_sku(db_session, "B-R4", governance_status="pending_model")
    _seed_sku(db_session, "B-R5", governance_status="do_not_model")
    db_session.commit()

    resp = client.get(
        "/api/planner/sku-master/governance",
        params={"status": "pending_model", "page_size": 10},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert body["page_size"] == 10
    barcodes = {it["erp_sku_barcode"] for it in body["items"]}
    assert barcodes == {"B-R3", "B-R4"}
    # Items must include the columns the UI needs to show priority.
    keys = set(body["items"][0].keys())
    must_have = {
        "erp_sku_barcode",
        "governance_status",
        "qty_window",
        "revenue_window",
        "line_count_window",
        "last_shipment_at",
    }
    assert must_have.issubset(keys), f"missing columns for UI: {must_have - keys}"


def test_get_governance_rejects_unknown_status(client, db_session):
    resp = client.get(
        "/api/planner/sku-master/governance", params={"status": "garbage"}
    )
    assert resp.status_code == 400


def test_post_governance_promote_from_model(client, db_session):
    _seed_sku(db_session, "B-R6", governance_status="pending_model")
    _seed_sku(db_session, "B-R7", governance_status="do_not_model")
    db_session.commit()

    resp = client.post(
        "/api/planner/sku-master/governance/promote-from-model",
        json={
            "sku_codes": ["B-R6", "B-R7", "MISSING"],
            "decided_by": "model-publish-job",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body == {"promoted": 1, "skipped": 1, "missing": 1}

    sku6 = sms.get_by_barcode(db_session, "B-R6")
    sku7 = sms.get_by_barcode(db_session, "B-R7")
    assert sms.get_sku_governance_status(sku6) == "auto_bound"
    # do_not_model decision must NOT be silently overwritten by model-publish.
    assert sms.get_sku_governance_status(sku7) == "do_not_model"
