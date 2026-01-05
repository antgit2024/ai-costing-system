from __future__ import annotations

from decimal import Decimal

from src.planner import models


def test_bom_fills_missing_unit_from_material_master_by_ref_id(client, db_session):
    """
    If a model version material line has missing unit_of_measure, BOM preview should fallback
    to material master unit (via material_ref_id) to avoid showing '-' in UI.
    """
    model = models.ProductModel(
        model_code="PI5",
        model_name="抱枕 PI5",
        status="active",
        unit_of_measure="套",
        metadata_json={},
    )
    db_session.add(model)
    db_session.flush()

    version = models.ProductModelVersion(
        model_id=model.id,
        version_kind="standard",
        version_status="published",
        version_label="PI5-STANDARD-UNIT-01",
        metadata_json={"standard": {"width_mm": 1000, "height_mm": 1000, "quantity": 1}},
    )
    db_session.add(version)
    db_session.flush()

    m = models.Material(
        material_code="WB02335",
        material_name="布料300-01白色黄金绒",
        material_type="raw",
        category="fabric",
        unit="平米",
        unit_price=Decimal("1.0"),
        currency="CNY",
        is_bom_material=True,
        is_active=True,
        status="active",
        metadata_json={},
    )
    db_session.add(m)
    db_session.flush()

    # Bad data: unit_of_measure missing on version line.
    line = models.ModelVersionMaterial(
        version_id=version.id,
        material_type="real",
        material_ref_id=m.id,
        material_code=m.material_code,
        material_name=m.material_name,
        unit_of_measure=None,
        calculation_method="area",
        base_quantity=Decimal("1"),
        loss_rate=Decimal("0"),
        sequence_order=1,
        metadata_json={"fixed_quantity": "0", "coverage_ratio": "1"},
    )
    db_session.add(line)
    db_session.commit()

    resp = client.post(
        "/api/planner/bom/generate",
        json={"model_version_id": version.id, "spec_text": "45X45", "quantity": "1"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["final_material_lines"][0]["material_code"] == "WB02335"
    assert body["final_material_lines"][0]["unit_of_measure"] == "平米"


