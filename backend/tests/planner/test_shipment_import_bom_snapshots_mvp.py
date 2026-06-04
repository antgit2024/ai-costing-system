from __future__ import annotations

import io
from decimal import Decimal

from openpyxl import Workbook

from src.planner import models


API_PREFIX = "/api/planner"


def _create_material(db_session, *, code: str, name: str) -> models.Material:
    material = models.Material(
        material_code=code,
        material_name=name,
        material_type="raw",
        category="frame",
        unit="m",
        unit_price=Decimal("1.0"),
        currency="CNY",
        is_bom_material=True,
        is_active=True,
        status="active",
        metadata_json={},
    )
    db_session.add(material)
    db_session.commit()
    return material


def _create_version_with_binding(db_session, *, sku_code: str) -> models.ProductModelVersion:
    model = models.ProductModel(
        model_code=f"PM-SHIP-{sku_code}",
        model_name="发货导入基准",
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

    base_material = _create_material(db_session, code=f"MAT-{sku_code}", name="基准物料")
    line = models.ModelVersionMaterial(
        version_id=version.id,
        material_type="real",
        material_ref_id=base_material.id,
        material_code=base_material.material_code,
        material_name=base_material.material_name,
        unit_of_measure="m",
        calculation_method="area",
        base_quantity=Decimal("0.5"),
        loss_rate=Decimal("5"),
        sequence_order=1,
        metadata_json={"fixed_quantity": "0", "coverage_ratio": "1"},
    )
    db_session.add(line)
    db_session.commit()

    binding = models.SkuModelVersionMapping(
        sku_code=sku_code,
        model_version_id=version.id,
        is_active=True,
        metadata_json={},
    )
    db_session.add(binding)
    db_session.commit()
    return version


def _build_xlsx_bytes(*, rows: list[dict]) -> bytes:
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


def test_shipment_import_bom_snapshots_mvp(client, db_session):
    _create_version_with_binding(db_session, sku_code="SKU-001")

    file_bytes = _build_xlsx_bytes(
        rows=[
            {
                "shipment_no": "S202512210857",
                "completed_at": "2025-12-21 16:30:00",
                "channel": "九斗云旗舰店",
                "sku_code": "SKU-001",
                "spec_text": "约50*140;024画框",
                "qty": 2,
                "revenue_amount": 100,
            }
        ]
    )

    files = {
        "file": (
            "shipment.xlsx",
            file_bytes,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    data = {"export_date": "2025-12-21", "requested_by": "tester"}
    resp = client.post(f"{API_PREFIX}/shipments/import", files=files, data=data)
    assert resp.status_code == 200, resp.text
    batch_id = resp.json()["id"]
    assert resp.json()["status"] == "success"
    assert resp.json()["inserted_rows"] == 1
    assert resp.json()["skipped_rows"] == 0

    # file-level idempotency: same xlsx bytes -> same batch
    resp2 = client.post(f"{API_PREFIX}/shipments/import", files=files, data=data)
    assert resp2.status_code == 200
    assert resp2.json()["id"] == batch_id

    # bom snapshot generated
    snaps = client.get(f"{API_PREFIX}/shipments/bom-snapshots", params={"batch_id": batch_id})
    assert snaps.status_code == 200, snaps.text
    items = snaps.json()
    assert len(items) == 1
    assert len(items[0]["final_material_lines"]) >= 1
    assert items[0]["trace"].get("bound_version_id")
    assert items[0]["trace"].get("spec_hash")

    # line-level idempotency across batches: different file hash, same line -> no duplicate lines/snapshots
    file_bytes2 = _build_xlsx_bytes(
        rows=[
            {
                "shipment_no": "S202512210857",
                "completed_at": "2025-12-21 16:30:00",
                "channel": "九斗云旗舰店",
                "sku_code": "SKU-001",
                "spec_text": "约50*140;024画框",
                "qty": 2,
                "revenue_amount": 100,
            },
            {"shipment_no": None, "completed_at": None, "channel": None, "sku_code": None, "spec_text": None, "qty": None, "revenue_amount": None},
        ]
    )
    files2 = {
        "file": (
            "shipment_v2.xlsx",
            file_bytes2,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    resp3 = client.post(f"{API_PREFIX}/shipments/import", files=files2, data={"export_date": "2025-12-22", "requested_by": "tester"})
    assert resp3.status_code == 200, resp3.text
    assert resp3.json()["id"] != batch_id
    assert resp3.json()["inserted_rows"] == 0
    assert resp3.json()["skipped_rows"] == 1
    assert db_session.query(models.ShipmentLine).count() == 1

    # unbound sku -> exception queue
    bad_bytes = _build_xlsx_bytes(
        rows=[
            {
                "shipment_no": "S202512210999",
                "completed_at": "2025-12-21 10:00:00",
                "channel": "测试店铺",
                "sku_code": "SKU-NOT-BOUND",
                "spec_text": "45X45;黑色包边",
                "qty": 1,
                "revenue_amount": 10,
            }
        ]
    )
    bad_files = {
        "file": (
            "shipment_bad.xlsx",
            bad_bytes,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    resp4 = client.post(
        f"{API_PREFIX}/shipments/import",
        files=bad_files,
        data={"export_date": "2025-12-22", "requested_by": "tester"},
    )
    assert resp4.status_code == 200, resp4.text
    bad_batch_id = resp4.json()["id"]
    excs = client.get(f"{API_PREFIX}/shipments/exceptions", params={"batch_id": bad_batch_id})
    assert excs.status_code == 200, excs.text
    reasons = [x["reason"] for x in excs.json()]
    assert "SKU_NOT_BOUND" in reasons
    snaps_bad = client.get(f"{API_PREFIX}/shipments/bom-snapshots", params={"batch_id": bad_batch_id})
    assert snaps_bad.status_code == 200
    assert snaps_bad.json() == []


