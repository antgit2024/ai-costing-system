from __future__ import annotations

import io
import datetime

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
            "货品规格（系统）",
            "规格编码（网店）",
            "平台商品Id（网店）",
            "平台规格Id（网店）",
            "匹配状态",
            "货品条码（系统）",
            "最后更新时间",
            "匹配方式",
            "生产工艺",
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
                r.get("system_spec_text"),
                r.get("shop_spec_code"),
                r.get("platform_product_id"),
                r.get("platform_sku_id"),
                r.get("match_status"),
                r.get("barcode"),
                r.get("source_updated_at"),
                r.get("match_method"),
                r.get("production_process"),
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
                "system_spec_text": "45X45;黑色包边",
                "shop_spec_code": "",
                "platform_product_id": "PP-1",
                "platform_sku_id": "PS-1",
                "match_status": "未匹配",
                "match_method": "ERP同步",
                "production_process": "",
                "source_updated_at": "2025-12-22 10:00:00",
            },
            {
                "barcode": "BC-001",
                "channel": "九斗云旗舰店",
                "product_name": "商品A-更新",
                "product_code": "CODE-A",
                # 覆盖回退逻辑：网店规格为空时，使用“货品规格（系统）”作为解析来源
                "spec_text": "",
                "system_spec_text": "45X45;黑色包边;加厚",
                "shop_spec_code": "OUR-SPEC-CODE-001",
                "platform_product_id": "PP-1",
                "platform_sku_id": "PS-1",
                "match_status": "已匹配",
                "match_method": "ERP同步",
                "production_process": "工艺：热转印；注意包边",
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
    # extra fields should be preserved for reverse-sync use cases
    assert row.metadata_json.get("shop_spec_code") == "OUR-SPEC-CODE-001"
    assert row.metadata_json.get("match_method") == "ERP同步"
    assert row.metadata_json.get("production_process") == "工艺：热转印；注意包边"
    assert row.metadata_json.get("production_note") == "工艺：热转印；注意包边"
    assert row.spec_text == "45X45;黑色包边;加厚"

    # mapping table should preserve platform_sku_id dimension even when barcode repeats
    mappings = (
        db_session.query(models.ShopSkuMapping)
        .filter(models.ShopSkuMapping.channel == "九斗云旗舰店", models.ShopSkuMapping.is_archived.is_(False))
        .all()
    )
    # our test file uses only one platform_sku_id (PS-1), so 1 mapping row
    assert len(mappings) == 1
    assert mappings[0].platform_sku_id == "PS-1"
    assert mappings[0].erp_sku_barcode == "BC-001"

    # scan endpoint: by barcode (factory/production use case)
    scan = client.get(f"{API_PREFIX}/sku-master/by-barcode/BC-001")
    assert scan.status_code == 200, scan.text
    body2 = scan.json()
    assert body2["sku_master"]["erp_sku_barcode"] == "BC-001"
    assert len(body2.get("shop_skus") or []) >= 1
    assert body2["shop_skus"][0]["platform_sku_id"] == "PS-1"

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
    assert created.metadata_json.get("needs_erp_sync") is True
    assert created.metadata_json.get("erp_sync_status") == "pending"
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


def test_sku_master_list_default_order_by_source_updated_at_desc(client, db_session):
    # Three rows: newest source_updated_at should appear first; NULL should be last.
    a = models.SkuMaster(
        erp_sku_barcode="BC-A",
        spec_text="A",
        source_updated_at=datetime.datetime(2026, 1, 10, 10, 0, 0),
        metadata_json={},
    )
    b = models.SkuMaster(
        erp_sku_barcode="BC-B",
        spec_text="B",
        source_updated_at=datetime.datetime(2026, 1, 11, 10, 0, 0),
        metadata_json={},
    )
    c = models.SkuMaster(erp_sku_barcode="BC-C", spec_text="C", source_updated_at=None, metadata_json={})
    db_session.add_all([a, b, c])
    db_session.commit()

    resp = client.get(f"{API_PREFIX}/sku-master", params={"page": 1, "page_size": 10})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    items = body["items"]
    # order should be: b (newest), a, c (NULL last)
    barcodes = [it["erp_sku_barcode"] for it in items if it["erp_sku_barcode"] in ("BC-A", "BC-B", "BC-C")]
    assert barcodes[:3] == ["BC-B", "BC-A", "BC-C"]

