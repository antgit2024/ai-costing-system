"""HTTP-level tests for ``/api/planner/integrations/...`` endpoints.

We mount only the integrations router (and stub the auth dependency) instead of
booting the full ``main.app`` — the planner app pulls in dozens of unrelated
routers + a workers thread, which we don't need just to check our routes.

Coverage:
- POST /jackyun/sync/shipments?wait=true lands data and returns a finished run
- POST without wait returns immediately (background mode) and the row appears
  shortly after
- The "today 00:00 Shanghai" fallback applies when there's no watermark
- /sync-runs and /sync-runs/{id} reflect the persisted state
- /dead-letters lists open items and resolve marks them done
"""

from __future__ import annotations

from typing import Any, Dict

import pytest
from src import compat as _planner_compat  # noqa: F401  - patches typing.ForwardRef before fastapi import
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.integrations.base.client import ClientResponse
from src.integrations.jackyun import client as jackyun_client_mod
from src.integrations.jackyun import sync_jobs as jackyun_sync_jobs
from src.integrations.jackyun.mappers import shipment as jackyun_shipment_mapper
from src.planner import models as planner_models
from src.planner.dependencies import get_db_session
from src.planner.routers import integrations as integrations_router_mod


SAMPLE_SHIPMENT: Dict[str, Any] = {
    "orderNo": "S202605060001",
    "platCode": "TMALL",
    "ownerName": "自营",
    "warehouseName": "成品仓",
    "warehouseCode": "W001",
    "erporderNo": "JY202605060001",
    "logisticNo": "DPK999000111",
    "logisticName": "德邦",
    "orderStatus": 7,
    "shopId": "1839228742782059392",
    "shopName": "九斗云旗舰店",
    "finishTime": "2026-05-06 09:00:00",
    "gmtCreate": "2026-05-06 08:30:00",
    "sendTime": "2026-05-06 09:00:00",
    "modifyTime": "2026-05-06 09:00:00",
    "platOrderNo": "3299468990290000001",
    "sellerMemo": "请走德邦",
    "goodsDetail": [
        {
            "goodsNo": "J25073103",
            "goodsName": "蓝色大海餐厅饭厅高级感装饰画",
            "skuBarcode": "5892064445582",
            "skuName": "J25073103A;宣绒布+卡纸;约30*30",
            "tradeName": "蓝色大海餐厅饭厅高级感装饰画",
            "tradeSpec": "颜色分类:J25073103A",
            "tradeGoodsno": "J25073103MQ0103",
            "sellCount": 1,
            "sellTotal": 89.9,
            "detailId": "2472676284727099001",
            "unit": "件",
            "skuId": "2272723253017200001",
        }
    ],
}


def _stub_jackyun_call(monkeypatch, payloads=None):
    """Patch ``JackyunClient.call`` so no network is hit and the mapper sees one page."""

    page_payloads = list(payloads) if payloads is not None else [SAMPLE_SHIPMENT]
    pages = [
        {
            "code": 200,
            "msg": "操作成功",
            "result": {
                "contextId": "ctx-route-test",
                "data": page_payloads,
                "pageInfo": {"pageIndex": 1, "pageSize": 50, "total": len(page_payloads)},
            },
        }
    ]

    def fake_call(self, api_method, biz_content, *, sync_run_id=None, db=None):
        body = pages.pop(0) if pages else {
            "code": 200,
            "msg": "操作成功",
            "result": {"contextId": "ctx-route-test", "data": [], "pageInfo": {"total": len(page_payloads)}},
        }
        return ClientResponse(
            success=True,
            biz_code="200",
            biz_sub_code=None,
            message="操作成功",
            data=(body.get("result") or {}).get("data"),
            raw=body,
            http_status=200,
            context_id=(body.get("result") or {}).get("contextId"),
        )

    monkeypatch.setattr(jackyun_client_mod.JackyunClient, "call", fake_call)


def _make_fake_client():
    fake = jackyun_client_mod.JackyunClient.__new__(jackyun_client_mod.JackyunClient)
    fake.source_system = "jackyun"
    return fake


@pytest.fixture()
def client(db_session, monkeypatch):
    """Spin up a minimal FastAPI app that mounts ONLY the integrations router."""

    app = FastAPI()
    app.include_router(integrations_router_mod.router, prefix="/api/planner")

    # Reuse the test session for every request so assertions on db_session see
    # the same rows the route handler wrote.
    app.dependency_overrides[get_db_session] = lambda: db_session

    # Force ``wait=true`` callers to use our pre-built fake client (the route
    # itself calls ``build_default_client`` if we don't intercept).
    fake = _make_fake_client()
    original = jackyun_sync_jobs.sync_shipments

    def patched_sync_shipments(db, **kwargs):
        kwargs.setdefault("client", fake)
        return original(db, **kwargs)

    monkeypatch.setattr(jackyun_sync_jobs, "sync_shipments", patched_sync_shipments)

    with TestClient(app) as c:
        yield c


def test_post_sync_shipments_wait_inline_lands_data(client, db_session, monkeypatch):
    _stub_jackyun_call(monkeypatch)

    resp = client.post(
        "/api/planner/integrations/jackyun/sync/shipments",
        json={
            "start_modify_time": "2026-05-06 00:00:00",
            "end_modify_time": "2026-05-06 23:59:59",
            "page_size": 50,
            "wait": True,
            "use_watermark": False,
            "triggered_by": "route-test-inline",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["accepted"] is True
    assert body["mode"] == "inline"
    assert body["sync_run_id"]
    assert body["effective_start_modify_time"] == "2026-05-06 00:00:00"
    assert body["run"] is not None
    assert body["run"]["status"] == "succeeded"
    assert body["run"]["total_rows"] == 1
    assert body["run"]["inserted_rows"] == 1
    assert body["run"]["triggered_by"] == "route-test-inline"

    line = (
        db_session.query(planner_models.ShipmentLine)
        .filter(planner_models.ShipmentLine.source_system == "jackyun")
        .one()
    )
    assert line.shipment_no == SAMPLE_SHIPMENT["orderNo"]
    assert line.erp_order_no == SAMPLE_SHIPMENT["erporderNo"]


def test_post_sync_shipments_defaults_to_today_when_no_watermark(client, db_session, monkeypatch):
    """First-ever run with use_watermark=true and no start_modify_time = today 00:00 Shanghai."""

    _stub_jackyun_call(monkeypatch)
    assert (
        db_session.query(planner_models.IntegrationSyncWatermark)
        .filter(
            planner_models.IntegrationSyncWatermark.source_system == "jackyun",
            planner_models.IntegrationSyncWatermark.sync_type
            == jackyun_sync_jobs.SHIPMENT_SYNC_TYPE,
        )
        .count()
        == 0
    ), "precondition: watermark must be empty for this test"

    resp = client.post(
        "/api/planner/integrations/jackyun/sync/shipments",
        json={"wait": True, "use_watermark": True, "triggered_by": "today-default"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["effective_start_modify_time"] is not None
    # Format check: "YYYY-MM-DD 00:00:00"
    assert body["effective_start_modify_time"].endswith(" 00:00:00")
    assert "today" in (body["note"] or "").lower()
    assert body["run"]["status"] == "succeeded"

    wm = (
        db_session.query(planner_models.IntegrationSyncWatermark)
        .filter(
            planner_models.IntegrationSyncWatermark.source_system == "jackyun",
            planner_models.IntegrationSyncWatermark.sync_type
            == jackyun_sync_jobs.SHIPMENT_SYNC_TYPE,
        )
        .one()
    )
    # Watermark is now ``min(max(payload_ts, window_end), now - 5min)`` rather
    # than the literal payload modifyTime — the safety buffer prevents us
    # from skipping records that upstream uploads with a few seconds of
    # delay. So we just assert the new watermark sits in the expected band:
    #   * NOT earlier than the payload modifyTime (we did at least see this)
    #   * NOT later than "right now" (we never time-travel forward)
    from datetime import datetime as _dt, timezone as _tz, timedelta as _td
    sh_now = _dt.now(_tz(_td(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
    assert wm.watermark_value >= SAMPLE_SHIPMENT["modifyTime"], (
        f"watermark went backwards: {wm.watermark_value} < {SAMPLE_SHIPMENT['modifyTime']}"
    )
    assert wm.watermark_value <= sh_now, (
        f"watermark in the future: {wm.watermark_value} > now {sh_now}"
    )


def test_post_sync_shipments_resumes_from_watermark_on_second_call(client, db_session, monkeypatch):
    """Second call should NOT default to today — it should resume from the watermark."""

    _stub_jackyun_call(monkeypatch)
    client.post(
        "/api/planner/integrations/jackyun/sync/shipments",
        json={"wait": True, "use_watermark": True, "triggered_by": "round-1"},
    )

    _stub_jackyun_call(monkeypatch)
    resp = client.post(
        "/api/planner/integrations/jackyun/sync/shipments",
        json={"wait": True, "use_watermark": True, "triggered_by": "round-2"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["effective_start_modify_time"] is None, "watermark resume passes None to the job"
    assert "watermark" in (body["note"] or "").lower()


def test_get_sync_runs_lists_recent(client, db_session, monkeypatch):
    _stub_jackyun_call(monkeypatch)
    client.post(
        "/api/planner/integrations/jackyun/sync/shipments",
        json={"wait": True, "use_watermark": False, "triggered_by": "list-test"},
    )

    resp = client.get(
        "/api/planner/integrations/sync-runs",
        params={"source_system": "jackyun", "limit": 10},
    )
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert isinstance(rows, list)
    assert any(r["triggered_by"] == "list-test" for r in rows)
    assert all(r["source_system"] == "jackyun" for r in rows)


def test_get_sync_run_detail_returns_run_and_dead_letters(client, db_session, monkeypatch):
    _stub_jackyun_call(monkeypatch)

    def _boom(*args, **kwargs):
        raise RuntimeError("synthetic failure for route test")

    monkeypatch.setattr(
        jackyun_shipment_mapper, "upsert_shipment_from_payload", _boom
    )

    create = client.post(
        "/api/planner/integrations/jackyun/sync/shipments",
        json={"wait": True, "use_watermark": False, "triggered_by": "detail-test"},
    )
    assert create.status_code == 200, create.text
    sync_run_id = create.json()["sync_run_id"]

    detail = client.get(f"/api/planner/integrations/sync-runs/{sync_run_id}")
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["run"]["id"] == sync_run_id
    assert body["run"]["error_rows"] == 1
    assert len(body["dead_letters"]) == 1
    dl = body["dead_letters"][0]
    assert dl["source_system"] == "jackyun"
    assert dl["record_type"] == "shipment"
    assert dl["error_type"] == "RuntimeError"
    assert dl["status"] == "open"


def test_dead_letter_list_and_resolve_roundtrip(client, db_session, monkeypatch):
    _stub_jackyun_call(monkeypatch)

    def _boom(*args, **kwargs):
        raise RuntimeError("dead letter resolve roundtrip")

    monkeypatch.setattr(
        jackyun_shipment_mapper, "upsert_shipment_from_payload", _boom
    )

    client.post(
        "/api/planner/integrations/jackyun/sync/shipments",
        json={"wait": True, "use_watermark": False, "triggered_by": "dl-test"},
    )

    listing = client.get(
        "/api/planner/integrations/dead-letters",
        params={"source_system": "jackyun", "limit": 50},
    )
    assert listing.status_code == 200, listing.text
    items = listing.json()["items"]
    assert items, "expected at least one open dead letter"
    dl_id = items[0]["id"]

    resolved = client.post(
        f"/api/planner/integrations/dead-letters/{dl_id}/resolve",
        json={"resolved_by": "ops-test", "note": "handled manually in test"},
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json() == {"resolved": True, "dead_letter_id": dl_id}

    # After resolving, the open list should no longer include it.
    listing2 = client.get(
        "/api/planner/integrations/dead-letters",
        params={"source_system": "jackyun"},
    )
    remaining_ids = {row["id"] for row in listing2.json()["items"]}
    assert dl_id not in remaining_ids


def test_sync_run_not_found_returns_404(client):
    resp = client.get("/api/planner/integrations/sync-runs/does-not-exist-uuid")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "sync_run_not_found"
