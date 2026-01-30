from __future__ import annotations

import uuid
from datetime import datetime, timezone

from src.planner import models
from src.planner.services import sku_master_service


def _seed_shipment_sample(db_session, *, sku_code: str, spec_text: str) -> None:
    batch = models.ShipmentImportBatch(
        file_name="seed.xlsx",
        file_hash=uuid.uuid4().hex,
        export_date="2026-01-01",
        requested_by="tester",
        status="done",
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
        shipment_no="S-SEED",
        order_no="O-SEED",
        product_link_id="L-SEED",
        completed_at=datetime.now(timezone.utc),
        channel="seed",
        sku_code=sku_code,
        spec_text=spec_text,
        spec_hash=None,
        qty=1,
        revenue_amount=1,
        external_line_key_hash=uuid.uuid4().hex,
        revision_group_hash=uuid.uuid4().hex,
        revision_no=1,
        superseded_by_id=None,
        is_active=True,
        raw_row_json={},
        normalize_warnings_json=[],
        metadata_json={},
    )
    db_session.add(line)
    db_session.commit()


def test_manual_bind_by_model_and_auto_bind_preview_execute(client, db_session):
    # Prepare: one model + one published standard version
    model = models.ProductModel(model_code="A1B", model_name="标准模型A1B", status="active", metadata_json={})
    db_session.add(model)
    db_session.flush()

    v = models.ProductModelVersion(
        model_id=model.id,
        version_kind="standard",
        version_status="published",
        version_label="A1B-20251223-01",
        metadata_json={"standard": {"width_mm": 1000, "height_mm": 1000, "quantity": 1}},
    )
    db_session.add(v)
    db_session.flush()

    # Two sku masters: one manual bind, one for auto bind
    sm1 = models.SkuMaster(erp_sku_barcode="BC-100", spec_text="whatever", metadata_json={})
    sm2 = models.SkuMaster(
        erp_sku_barcode="BC-200",
        # model code is NOT in the first segment; should still be detected by scanner.
        spec_text="50*140;A1B;xxx",
        metadata_json={},
    )
    db_session.add_all([sm1, sm2])
    db_session.commit()

    # Seed latest shipment spec samples (binding now enforces validation)
    _seed_shipment_sample(db_session, sku_code="BC-100", spec_text="50*140;A1B;xxx")
    _seed_shipment_sample(db_session, sku_code="BC-200", spec_text="50*140;A1B;xxx")

    # Manual bind by model should bind sm1 barcode to published standard version
    resp = client.post(
        "/api/planner/sku-master/bind-by-model",
        json={"model_id": model.id, "sku_master_ids": [sm1.id], "requested_by": "tester"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["bound_count"] == 1
    mapping = (
        db_session.query(models.SkuModelVersionMapping)
        .filter(models.SkuModelVersionMapping.sku_code == "BC-100", models.SkuModelVersionMapping.is_active.is_(True))
        .one()
    )
    assert mapping.model_version_id == v.id

    # Auto bind preview should find sm2 (unbound) and match model_code_hint to published version
    prev = client.post("/api/planner/sku-master/auto-bind/preview", json={"limit": 50})
    assert prev.status_code == 200, prev.text
    prev_body = prev.json()
    assert prev_body["candidates"] >= 1
    assert any(it["erp_sku_barcode"] == "BC-200" and it["model_code"] == "A1B" for it in prev_body["items"])

    # Execute should bind BC-200
    exe = client.post(
        "/api/planner/sku-master/auto-bind/execute",
        json={"limit": 50, "requested_by": "tester", "sku_master_ids": [sm2.id]},
    )
    assert exe.status_code == 200, exe.text
    m2 = (
        db_session.query(models.SkuModelVersionMapping)
        .filter(models.SkuModelVersionMapping.sku_code == "BC-200", models.SkuModelVersionMapping.is_active.is_(True))
        .one()
    )
    assert m2.model_version_id == v.id

    # Ensure manual bind won't overwrite existing active binding
    resp2 = client.post(
        "/api/planner/sku-master/bind-by-model",
        json={"model_id": model.id, "sku_master_ids": [sm2.id], "requested_by": "tester"},
    )
    assert resp2.status_code == 200, resp2.text
    body2 = resp2.json()
    assert body2["skipped_already_bound"] == 1


def test_manual_bulk_bind_by_filters_with_exclusions(client, db_session):
    # Prepare: one model + one published standard version
    model = models.ProductModel(model_code="OZU", model_name="丝圈地垫", status="active", metadata_json={})
    db_session.add(model)
    db_session.flush()

    v = models.ProductModelVersion(
        model_id=model.id,
        version_kind="standard",
        version_status="published",
        version_label="OZU-STANDARD-20260111-01",
        metadata_json={"standard": {"width_mm": 1000, "height_mm": 1000, "quantity": 1}},
    )
    db_session.add(v)
    db_session.flush()

    # SKU masters (unbound) - two hit include_terms, one doesn't
    sm1 = models.SkuMaster(erp_sku_barcode="BC-OZU-1", spec_text="竖140CM*横200CM;丝圈地垫", metadata_json={})
    sm2 = models.SkuMaster(erp_sku_barcode="BC-OZU-2", spec_text="丝圈地垫 60*90", metadata_json={})
    sm3 = models.SkuMaster(erp_sku_barcode="BC-OTHER", spec_text="皮革地垫 60*90", metadata_json={})
    db_session.add_all([sm1, sm2, sm3])
    db_session.commit()

    _seed_shipment_sample(db_session, sku_code="BC-OZU-1", spec_text="60*90;丝圈地垫")
    _seed_shipment_sample(db_session, sku_code="BC-OZU-2", spec_text="60*90;丝圈地垫")

    # Exclude sm2 (simulate user unchecked)
    resp = client.post(
        "/api/planner/sku-master/bind-by-model/bulk",
        json={
            "model_id": model.id,
            "limit": 200,
            "include_terms": "丝圈地垫",
            "match_scope": "spec",
            "excluded_sku_master_ids": [sm2.id],
            "requested_by": "tester",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["batch_candidates"] >= 1
    assert body["bound_count"] == 1
    assert body["has_more"] is False

    # sm1 should be bound, sm2 excluded should remain unbound, sm3 doesn't match
    m1 = (
        db_session.query(models.SkuModelVersionMapping)
        .filter(models.SkuModelVersionMapping.sku_code == "BC-OZU-1", models.SkuModelVersionMapping.is_active.is_(True))
        .one()
    )
    assert m1.model_version_id == v.id

    assert (
        db_session.query(models.SkuModelVersionMapping)
        .filter(models.SkuModelVersionMapping.sku_code == "BC-OZU-2", models.SkuModelVersionMapping.is_active.is_(True))
        .count()
        == 0
    )
    assert (
        db_session.query(models.SkuModelVersionMapping)
        .filter(models.SkuModelVersionMapping.sku_code == "BC-OTHER", models.SkuModelVersionMapping.is_active.is_(True))
        .count()
        == 0
    )

