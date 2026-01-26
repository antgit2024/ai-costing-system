from __future__ import annotations

import io
from datetime import datetime, timezone
from openpyxl import Workbook

from src.planner import models


API_PREFIX = "/api/planner"


def _create_shipment_line(
    db_session,
    *,
    order_no: str,
    product_link_id: str,
    channel: str,
    sku_code: str,
    completed_at: str,
    qty: int,
    revenue_amount: int,
) -> models.ShipmentLine:
    batch = models.ShipmentImportBatch(
        file_name="seed.xlsx",
        file_hash="seed",
        export_date="2025-01-01",
        requested_by="seed",
        status="success",
    )
    db_session.add(batch)
    db_session.commit()

    line = models.ShipmentLine(
        batch_id=batch.id,
        row_index=2,
        shipment_no="S-SEED",
        order_no=order_no,
        product_link_id=product_link_id,
        completed_at=datetime.fromisoformat(completed_at).replace(tzinfo=timezone.utc),
        channel=channel,
        sku_code=sku_code,
        spec_text="交易规格:45*45",
        qty=qty,
        revenue_amount=revenue_amount,
        external_line_key_hash=f"seed-{order_no}-{sku_code}",
        revision_group_hash="seed",
        revision_no=1,
        is_active=True,
        raw_row_json={},
        normalize_warnings_json=[],
        metadata_json={},
    )
    db_session.add(line)
    db_session.commit()
    return line


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


def test_after_sales_import_and_returns_rate_by_sku(client, db_session):
    _create_shipment_line(
        db_session,
        order_no="TM-ORDER-001",
        product_link_id="LINK-001",
        channel="绮妙旗舰店",
        sku_code="BARCODE-001",
        completed_at="2025-01-02 10:00:00",
        qty=2,
        revenue_amount=100,
    )

    file_bytes = _build_after_sales_xlsx_bytes(
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
            }
        ]
    )

    files = {
        "file": ("after_sales.xlsx", file_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    }
    resp = client.post(f"{API_PREFIX}/after-sales/import", files=files, data={"requested_by": "tester"})
    assert resp.status_code == 200, resp.text
    batch = resp.json()
    assert batch["status"] == "success"
    assert batch["inserted_rows"] == 1

    # returns-rate: attribute returns to shipment completion period (month)
    r2 = client.get(
        f"{API_PREFIX}/analytics/returns-rate/sku",
        params={
            "start": "2025-01-01T00:00:00+00:00",
            "end": "2025-02-01T00:00:00+00:00",
            "group_by": "month",
            "channel": "绮妙旗舰店",
            "sku_code": "BARCODE-001",
        },
    )
    assert r2.status_code == 200, r2.text
    data = r2.json()
    assert data["items"], data
    item = data["items"][0]
    assert item["sku_code"] == "BARCODE-001"
    assert str(item["shipped_qty"]) in ("2", "2.0")
    assert str(item["returned_qty"]) in ("1", "1.0")

