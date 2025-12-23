from __future__ import annotations

import io

from openpyxl import Workbook

from src.planner import models


API_PREFIX = "/api/planner"


def _build_sku_master_xlsx_rows(rows: list[dict]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(
        [
            "规格图片（网店）",
            "销售渠道",
            "商品名称（网店）",
            "商品编码（网店）",
            "商品图片（网店）",
            "商品规格（网店）",
            "平台商品Id（网店）",
            "平台规格Id（网店）",
            "匹配状态",
            "货品条码（系统）",
            "最后更新时间",
        ]
    )
    for r in rows:
        ws.append(
            [
                r.get("spec_image"),
                r.get("channel"),
                r.get("product_name"),
                r.get("product_code"),
                r.get("product_image"),
                r.get("spec_text"),
                r.get("platform_product_id"),
                r.get("platform_sku_id"),
                r.get("match_status"),
                r.get("barcode"),
                r.get("source_updated_at"),
            ]
        )
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _build_shipment_xlsx_rows(rows: list[dict]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(["发货单号", "完成时间", "销售渠道", "货品条码", "交易规格", "数量", "金额"])
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
            ]
        )
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_sku_master_import_and_shipment_autobackfill_mvp(client, db_session):
    # 1) import 2 rows with same barcode -> 1 inserted + 1 updated
    file_bytes = _build_sku_master_xlsx_rows(
        [
            {
                "barcode": "BC-001",
                "channel": "九斗云旗舰店",
                "product_name": "商品A",
                "product_code": "CODE-A",
                "spec_text": "45X45;黑色包边",
                "platform_product_id": "PP-1",
                "platform_sku_id": "PS-1",
                "match_status": "未匹配",
                "source_updated_at": "2025-12-22 10:00:00",
            },
            {
                "barcode": "BC-001",
                "channel": "九斗云旗舰店",
                "product_name": "商品A-更新",
                "product_code": "CODE-A",
                "spec_text": "45X45;黑色包边;加厚",
                "platform_product_id": "PP-1",
                "platform_sku_id": "PS-1",
                "match_status": "已匹配",
                "source_updated_at": "2025-12-22 11:00:00",
            },
        ]
    )
    files = {
        "file": (
            "sku_master.xlsx",
            file_bytes,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    resp = client.post(f"{API_PREFIX}/sku-master/import", files=files, data={"requested_by": "tester"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 2
    assert body["inserted"] == 1
    assert body["updated"] == 1

    row = (
        db_session.query(models.SkuMaster)
        .filter(models.SkuMaster.erp_sku_barcode == "BC-001", models.SkuMaster.is_archived.is_(False))
        .one()
    )
    assert row.product_name == "商品A-更新"
    assert row.match_status == "已匹配"

    # 2) shipment import autobackfill: missing sku master -> create minimal record
    ship_bytes = _build_shipment_xlsx_rows(
        [
            {
                "shipment_no": "S-001",
                "completed_at": "2025-12-22 12:00:00",
                "channel": "绮妙旗舰店",
                "sku_code": "BC-NEW",
                "spec_text": "约50*140;024画框",
                "qty": 1,
                "revenue_amount": 10,
            }
        ]
    )
    ship_files = {
        "file": (
            "shipment.xlsx",
            ship_bytes,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    ship_resp = client.post(
        f"{API_PREFIX}/shipments/import",
        files=ship_files,
        data={"export_date": "2025-12-22", "requested_by": "tester"},
    )
    assert ship_resp.status_code == 200, ship_resp.text
    created = (
        db_session.query(models.SkuMaster)
        .filter(models.SkuMaster.erp_sku_barcode == "BC-NEW", models.SkuMaster.is_archived.is_(False))
        .one()
    )
    assert created.spec_text == "约50*140;024画框"
    assert created.channel == "绮妙旗舰店"
    assert created.metadata_json.get("source") == "shipment_autobackfill"
    assert created.metadata_json.get("last_shipment_spec_hash")

    # 3) shipment import should NOT overwrite existing sku master
    keep = models.SkuMaster(
        erp_sku_barcode="BC-KEEP",
        channel="九斗云旗舰店",
        spec_text="ORIGINAL",
        metadata_json={"source": "manual"},
    )
    db_session.add(keep)
    db_session.commit()

    ship_bytes2 = _build_shipment_xlsx_rows(
        [
            {
                "shipment_no": "S-002",
                "completed_at": "2025-12-22 13:00:00",
                "channel": "九斗云旗舰店",
                "sku_code": "BC-KEEP",
                "spec_text": "NEW_SPEC",
                "qty": 1,
                "revenue_amount": 10,
            }
        ]
    )
    ship_files2 = {
        "file": (
            "shipment2.xlsx",
            ship_bytes2,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    ship_resp2 = client.post(
        f"{API_PREFIX}/shipments/import",
        files=ship_files2,
        data={"export_date": "2025-12-22", "requested_by": "tester"},
    )
    assert ship_resp2.status_code == 200, ship_resp2.text
    kept = (
        db_session.query(models.SkuMaster)
        .filter(models.SkuMaster.erp_sku_barcode == "BC-KEEP", models.SkuMaster.is_archived.is_(False))
        .one()
    )
    assert kept.spec_text == "ORIGINAL"
    assert kept.metadata_json.get("source") == "manual"
    # should record last shipment spec without overwriting ERP spec_text or source
    assert kept.metadata_json.get("last_shipment_spec_text") == "NEW_SPEC"
    assert kept.metadata_json.get("spec_mismatch") is True


