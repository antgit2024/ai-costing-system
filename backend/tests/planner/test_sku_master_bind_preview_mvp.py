from __future__ import annotations

import uuid
from datetime import datetime, timezone

from src.planner import models


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
    db_session.add(
        models.ShipmentLine(
            batch_id=batch.id,
            row_index=1,
            shipment_no="S-SEED",
            order_no="O-SEED",
            product_link_id="L-SEED",
            completed_at=datetime.now(timezone.utc),
            channel="seed",
            sku_code=sku_code,
            spec_text=spec_text,
            external_line_key_hash=uuid.uuid4().hex,
            revision_group_hash=uuid.uuid4().hex,
            revision_no=1,
            is_active=True,
            raw_row_json={},
            normalize_warnings_json=[],
            metadata_json={},
        )
    )
    db_session.commit()


def test_bind_preview_blocks_when_no_shipment_sample(client, db_session):
    model = models.ProductModel(model_code="PV1", model_name="预检模型", status="active", metadata_json={})
    db_session.add(model)
    db_session.flush()
    v = models.ProductModelVersion(
        model_id=model.id,
        version_kind="standard",
        version_status="published",
        version_label="PV1-STANDARD-001",
        metadata_json={"standard": {"width_mm": 1000, "height_mm": 1000, "quantity": 1}},
    )
    db_session.add(v)
    db_session.flush()
    sm = models.SkuMaster(erp_sku_barcode="BC-PV-001", spec_text="x", metadata_json={})
    db_session.add(sm)
    db_session.commit()

    prev = client.post(
        "/api/planner/sku-master/bind-by-model/preview",
        json={"model_id": model.id, "sku_master_ids": [sm.id], "requested_by": "tester"},
    )
    assert prev.status_code == 200, prev.text
    body = prev.json()
    assert body["total_selected"] == 1
    assert body["hard_errors"] == 0
    assert body["can_bind"] == 1
    assert body["items"][0]["status"] == "can_bind"

    # enforce: actual bind should also fail (blocked)
    resp = client.post(
        "/api/planner/sku-master/bind-by-model",
        json={"model_id": model.id, "sku_master_ids": [sm.id], "requested_by": "tester"},
    )
    assert resp.status_code == 200, resp.text
    body2 = resp.json()
    assert body2["bound_count"] == 1
    assert len(body2["errors"]) == 0


def test_bind_preview_allows_and_auto_preparse_on_success(client, db_session):
    model = models.ProductModel(model_code="PV2", model_name="预检模型2", status="active", metadata_json={})
    db_session.add(model)
    db_session.flush()
    v = models.ProductModelVersion(
        model_id=model.id,
        version_kind="standard",
        version_status="published",
        version_label="PV2-STANDARD-001",
        metadata_json={"standard": {"width_mm": 1000, "height_mm": 1000, "quantity": 1}},
    )
    db_session.add(v)
    db_session.flush()
    sm = models.SkuMaster(erp_sku_barcode="BC-PV-002", spec_text="x", metadata_json={})
    db_session.add(sm)
    db_session.commit()

    _seed_shipment_sample(db_session, sku_code="BC-PV-002", spec_text="60*90;PV2")

    prev = client.post(
        "/api/planner/sku-master/bind-by-model/preview",
        json={"model_id": model.id, "sku_master_ids": [sm.id], "requested_by": "tester"},
    )
    assert prev.status_code == 200, prev.text
    body = prev.json()
    assert body["can_bind"] == 1
    assert body["hard_errors"] == 0
    assert body["items"][0]["status"] == "can_bind"

    resp = client.post(
        "/api/planner/sku-master/bind-by-model",
        json={"model_id": model.id, "sku_master_ids": [sm.id], "requested_by": "tester"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["bound_count"] == 1

    # auto preparse should be written on sku_master
    sm2 = db_session.get(models.SkuMaster, sm.id)
    meta = sm2.metadata_json or {}
    assert str(meta.get("preparse_spec_hash") or "").strip() != ""
    assert str(meta.get("preparse_spec_text") or "").strip() != ""


def test_bind_preview_warns_when_sample_keywords_mismatch_target(client, db_session):
    # Model name indicates pillow, but sample indicates mat -> should warn (not block)
    model = models.ProductModel(model_code="BZ1", model_name="抱枕", status="active", metadata_json={})
    db_session.add(model)
    db_session.flush()
    v = models.ProductModelVersion(
        model_id=model.id,
        version_kind="standard",
        version_status="published",
        version_label="BZ1-STANDARD-001",
        metadata_json={"standard": {"width_mm": 1000, "height_mm": 1000, "quantity": 1}},
    )
    db_session.add(v)
    db_session.flush()
    sm = models.SkuMaster(erp_sku_barcode="BC-MIS-001", spec_text="丝圈地垫 60*90", product_name="丝圈地垫", metadata_json={})
    db_session.add(sm)
    db_session.commit()

    _seed_shipment_sample(db_session, sku_code="BC-MIS-001", spec_text="丝圈地垫 60*90")

    prev = client.post(
        "/api/planner/sku-master/bind-by-model/preview",
        json={"model_id": model.id, "sku_master_ids": [sm.id], "requested_by": "tester"},
    )
    assert prev.status_code == 200, prev.text
    body = prev.json()
    assert body["can_bind"] == 1
    ws = body["items"][0]["warnings"]
    assert ws and any("疑似选错目标" in str(x) or "请确认目标是否选对" in str(x) for x in ws)


def test_bundle_bind_preview_blocks_when_bom_cannot_fill_dims(client, db_session):
    # base model/version for bundle component
    m = models.ProductModel(model_code="BM1", model_name="组件模型", status="active", metadata_json={})
    db_session.add(m)
    db_session.flush()
    v = models.ProductModelVersion(
        model_id=m.id,
        version_kind="standard",
        version_status="published",
        version_label="BM1-STANDARD-001",
        metadata_json={"standard": {"width_mm": 1000, "height_mm": 1000, "quantity": 1}},
    )
    db_session.add(v)
    db_session.commit()

    # create bundle template with missing dims (0) so generation must fill from tx spec dims
    r = client.post(
        "/api/planner/bundle-templates",
        json={
            "name": "缺尺寸套装",
            "components": [
                {"model_version_id": v.id, "width_mm": "0", "height_mm": "0", "quantity": "1", "spec_text": "x"}
            ],
            "metadata": {},
        },
    )
    assert r.status_code == 201, r.text
    tid = r.json()["id"]

    pub = client.post(f"/api/planner/bundle-templates/{tid}/publish", json={"operator_id": "tester"})
    assert pub.status_code == 200, pub.text

    # sku master + shipment sample WITHOUT any size
    sm = models.SkuMaster(erp_sku_barcode="BC-BUNDLE-001", spec_text="x", metadata_json={})
    db_session.add(sm)
    db_session.commit()
    _seed_shipment_sample(db_session, sku_code="BC-BUNDLE-001", spec_text="颜色分类:纯色")

    prev = client.post(
        "/api/planner/sku-master/bind-by-bundle/preview",
        json={
            "template_id": tid,
            "preset_selector": "A",
            "sku_master_ids": [sm.id],
            "requested_by": "tester",
        },
    )
    assert prev.status_code == 200, prev.text
    body = prev.json()
    assert body["hard_errors"] == 1
    assert body["items"][0]["status"] == "hard_error"

