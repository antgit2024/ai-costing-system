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


def test_retry_exceptions_resolves_sku_not_bound_and_generates_new_snapshot(client, db_session):
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
    resp = client.post(
        f"{API_PREFIX}/shipments/import",
        files=bad_files,
        data={"export_date": "2025-12-22", "requested_by": "tester"},
    )
    assert resp.status_code == 200, resp.text
    batch_id = resp.json()["id"]

    excs = client.get(f"{API_PREFIX}/shipments/exceptions", params={"batch_id": batch_id})
    assert excs.status_code == 200, excs.text
    assert any(x["reason"] == "SKU_NOT_BOUND" for x in excs.json())
    assert (
        db_session.query(models.ShipmentExceptionQueue)
        .filter(models.ShipmentExceptionQueue.batch_id == batch_id)
        .filter(models.ShipmentExceptionQueue.resolved_at.is_(None))
        .count()
        >= 1
    )

    _create_version_with_binding(db_session, sku_code="SKU-NOT-BOUND")

    retry = client.post(
        f"{API_PREFIX}/shipments/exceptions/retry",
        json={
            "batch_id": batch_id,
            "only_unresolved": True,
            "limit": 50,
            "operator_id": "tester",
            "reason": "binding_completed",
        },
    )
    assert retry.status_code == 200, retry.text
    assert retry.json()["resolved"] >= 1

    # exception resolved, and new bom snapshot exists
    assert (
        db_session.query(models.ShipmentExceptionQueue)
        .filter(models.ShipmentExceptionQueue.batch_id == batch_id)
        .filter(models.ShipmentExceptionQueue.resolved_at.isnot(None))
        .count()
        >= 1
    )
    snaps = client.get(f"{API_PREFIX}/shipments/bom-snapshots", params={"batch_id": batch_id})
    assert snaps.status_code == 200, snaps.text
    assert len(snaps.json()) == 1
    assert snaps.json()[0]["trace"].get("retry_exception_id")
    assert snaps.json()[0]["trace"].get("retried_by") == "tester"


def test_retry_does_not_overwrite_historical_snapshot_creates_new_row(client, db_session):
    _create_version_with_binding(db_session, sku_code="SKU-001")
    ok_bytes = _build_xlsx_bytes(
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
            ok_bytes,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    resp = client.post(
        f"{API_PREFIX}/shipments/import",
        files=files,
        data={"export_date": "2025-12-21", "requested_by": "tester"},
    )
    assert resp.status_code == 200, resp.text
    batch_id = resp.json()["id"]

    line = (
        db_session.query(models.ShipmentLine)
        .filter(models.ShipmentLine.batch_id == batch_id)
        .order_by(models.ShipmentLine.created_at.desc())
        .first()
    )
    assert line

    before_snaps = (
        db_session.query(models.BomSnapshot).filter(models.BomSnapshot.batch_id == batch_id).all()
    )
    assert len(before_snaps) == 1
    old_snap_id = before_snaps[0].id
    old_final_lines = list(before_snaps[0].final_lines_json or [])
    old_trace = dict(before_snaps[0].trace_json or {})

    # create an unresolved exception record for this line (simulate "needs retry")
    exc = models.ShipmentExceptionQueue(
        batch_id=batch_id,
        shipment_line_id=line.id,
        reason="MANUAL_RETRY",
        message="force_retry",
        payload_json={},
    )
    db_session.add(exc)
    db_session.commit()

    retry = client.post(
        f"{API_PREFIX}/shipments/exceptions/retry",
        json={
            "batch_id": batch_id,
            "only_unresolved": True,
            "operator_id": "tester",
            "reason": "manual_retry",
        },
    )
    assert retry.status_code == 200, retry.text
    assert retry.json()["resolved"] >= 1

    after_snaps = (
        db_session.query(models.BomSnapshot).filter(models.BomSnapshot.batch_id == batch_id).all()
    )
    assert len(after_snaps) == 2
    # old snapshot remains untouched (no overwrite)
    old_after = db_session.get(models.BomSnapshot, old_snap_id)
    assert old_after
    assert list(old_after.final_lines_json or []) == old_final_lines
    assert dict(old_after.trace_json or {}) == old_trace


