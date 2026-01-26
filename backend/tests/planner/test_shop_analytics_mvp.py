from __future__ import annotations

import io

from openpyxl import Workbook

from src.planner import models


API_PREFIX = "/api/planner"


def _build_shipments_xlsx_bytes(*, rows: list[dict]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(["发货单号", "完成时间", "销售渠道", "货品条码", "交易规格", "数量", "金额", "原始单号", "商品链接ID"])
    for r in rows:
        ws.append(
            [
                r.get("shipment_no"),
                r.get("completed_at"),
                r.get("channel"),
                r.get("sku_code"),
                r.get("spec_text"),
                r.get("qty"),
                r.get("revenue_amount"),
                r.get("order_no"),
                r.get("product_link_id"),
            ]
        )
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _build_after_sales_xlsx_bytes(*, rows: list[dict]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(["退换补发单号", "销售渠道", "货品条码", "商品链接Id", "网店订单号", "申请时间", "退货数量", "退货金额", "退换原因"])
    for r in rows:
        ws.append(
            [
                r.get("after_sales_no"),
                r.get("channel"),
                r.get("sku_code"),
                r.get("product_link_id"),
                r.get("order_no"),
                r.get("applied_at"),
                r.get("return_qty"),
                r.get("refund_amount"),
                r.get("reason"),
            ]
        )
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _seed_min_model(db_session, *, sku_code: str) -> None:
    model = models.ProductModel(
        model_code="PM-SHOPS-ANALYTICS-001",
        model_name="店铺数据测试模型",
        status="active",
        unit_of_measure="套",
        metadata_json={},
    )
    db_session.add(model)
    db_session.commit()

    version = models.ProductModelVersion(
        model_id=model.id,
        version_kind="standard",
        version_status="published",
        metadata_json={"standard": {"width_mm": "1000", "height_mm": "1000"}},
    )
    db_session.add(version)
    db_session.commit()

    binding = models.SkuModelVersionMapping(
        sku_code=sku_code,
        model_version_id=version.id,
        is_active=True,
        metadata_json={},
    )
    db_session.add(binding)
    db_session.commit()


def test_shop_analytics_profit_and_returns_by_channel_has_coverage(client, db_session):
    # Only BARCODE-001 is bound (will produce BOM snapshot). BARCODE-002 is unbound (no snapshot).
    _seed_min_model(db_session, sku_code="BARCODE-001")

    ship_bytes = _build_shipments_xlsx_bytes(
        rows=[
            {
                "shipment_no": "S-001",
                "completed_at": "2025-01-02 10:00:00",
                "channel": "绮妙旗舰店",
                "sku_code": "BARCODE-001",
                "spec_text": "约50*140;024画框",
                "qty": 1,
                "revenue_amount": 100,
                "order_no": "TM-ORDER-001",
                "product_link_id": "LINK-001",
            },
            {
                "shipment_no": "S-002",
                "completed_at": "2025-01-02 11:00:00",
                "channel": "绮妙旗舰店",
                "sku_code": "BARCODE-002",
                "spec_text": "约50*140;024画框",
                "qty": 1,
                "revenue_amount": 80,
                "order_no": "TM-ORDER-002",
                "product_link_id": "LINK-002",
            },
        ]
    )
    resp = client.post(
        f"{API_PREFIX}/shipments/import",
        files={"file": ("ship.xlsx", ship_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={"requested_by": "tester"},
    )
    assert resp.status_code == 200, resp.text
    batch_id = resp.json()["id"]

    # Force deterministic cost for the generated snapshot(s).
    snap = (
        db_session.query(models.BomSnapshot)
        .filter(models.BomSnapshot.batch_id == batch_id)
        .order_by(models.BomSnapshot.created_at.desc())
        .first()
    )
    assert snap is not None
    trace = dict(snap.trace_json or {})
    trace["costing"] = {"total_cost": "20"}
    snap.trace_json = trace
    db_session.commit()

    # Import after-sales for both lines (strong keys). Refund should still be attributed even if no BOM snapshot.
    ret_bytes = _build_after_sales_xlsx_bytes(
        rows=[
            {
                "after_sales_no": "SH202501030001",
                "channel": "绮妙旗舰店",
                "sku_code": "BARCODE-001",
                "product_link_id": "LINK-001",
                "order_no": "TM-ORDER-001",
                "applied_at": "2025-01-03 12:00:00",
                "return_qty": 1,
                "refund_amount": 50,
                "reason": "不想要了",
            },
            {
                "after_sales_no": "SH202501030002",
                "channel": "绮妙旗舰店",
                "sku_code": "BARCODE-002",
                "product_link_id": "LINK-002",
                "order_no": "TM-ORDER-002",
                "applied_at": "2025-01-03 12:30:00",
                "return_qty": 1,
                "refund_amount": 50,
                "reason": "不想要了",
            },
        ]
    )
    r2 = client.post(
        f"{API_PREFIX}/after-sales/import",
        files={"file": ("ret.xlsx", ret_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={"requested_by": "tester"},
    )
    assert r2.status_code == 200, r2.text

    p = client.get(
        f"{API_PREFIX}/analytics/profit/channel",
        params={
            "start": "2025-01-01T00:00:00+00:00",
            "end": "2025-02-01T00:00:00+00:00",
            "group_by": "month",
            "channel": "绮妙旗舰店",
        },
    )
    assert p.status_code == 200, p.text
    pdata = p.json()
    assert pdata["total_shipment_lines"] == 2
    assert pdata["lines_with_bom_snapshots"] == 1
    assert pdata["items"], pdata
    item = pdata["items"][0]
    # revenue=180, refund=100, cost=20 => net_profit=(180-100)-20=60
    assert str(item["revenue_amount"]) in ("180", "180.0")
    assert str(item["refund_amount"]) in ("100", "100.0")
    assert str(item["cost_amount"]) in ("20", "20.0")
    assert str(item["net_profit"]) in ("60", "60.0")
    assert item["shipment_lines_total"] == 2
    assert item["lines_with_bom_snapshots"] == 1

    rr = client.get(
        f"{API_PREFIX}/analytics/returns-rate/channel",
        params={
            "start": "2025-01-01T00:00:00+00:00",
            "end": "2025-02-01T00:00:00+00:00",
            "group_by": "month",
            "channel": "绮妙旗舰店",
        },
    )
    assert rr.status_code == 200, rr.text
    rdata = rr.json()
    assert rdata["items"], rdata
    ritem = rdata["items"][0]
    assert ritem["shipment_lines_total"] == 2
    assert str(ritem["shipped_qty"]) in ("2", "2.0")
    assert str(ritem["returned_qty"]) in ("2", "2.0")

