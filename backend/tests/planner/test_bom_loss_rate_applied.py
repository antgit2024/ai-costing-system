from __future__ import annotations

from decimal import Decimal

from src.planner import models

API_PREFIX = "/api/planner"


def _create_material(db_session, *, code: str, name: str) -> models.Material:
    material = models.Material(
        material_code=code,
        material_name=name,
        material_type="raw",
        category="test",
        unit="pcs",
        unit_price=Decimal("1.0"),
        conversion_purchase_to_bom=Decimal("1.0"),
        currency="CNY",
        is_bom_material=True,
        is_active=True,
        status="active",
        metadata_json={"bom_unit_price": "1"},
    )
    db_session.add(material)
    db_session.commit()
    return material


def _create_standard_version_with_one_line(db_session) -> models.ProductModelVersion:
    model = models.ProductModel(
        model_code="PM-LOSS-001",
        model_name="损耗口径测试模型",
        status="active",
        unit_of_measure="件",
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

    m = _create_material(db_session, code="MAT-LOSS", name="损耗测试物料")
    line = models.ModelVersionMaterial(
        version_id=version.id,
        material_type="real",
        material_ref_id=m.id,
        material_code=m.material_code,
        material_name=m.material_name,
        unit_of_measure="pcs",
        calculation_method="count",
        base_quantity=Decimal("2"),
        loss_rate=Decimal("10"),
        sequence_order=1,
        metadata_json={"fixed_quantity": "0", "coverage_ratio": "1"},
    )
    db_session.add(line)
    db_session.commit()

    return version


def test_bom_generate_applies_line_loss_rate_to_inventory_and_costing(client, db_session):
    version = _create_standard_version_with_one_line(db_session)

    resp = client.post(
        f"{API_PREFIX}/bom/generate",
        json={
            "model_version_id": version.id,
            "spec_text": "约50*50",
            "quantity": "1",
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert len(data["final_material_lines"]) == 1
    line = data["final_material_lines"][0]

    computed_qty = Decimal(str(line["computed_quantity"]))  # 净用量
    assert computed_qty == Decimal("2")

    # 含损耗用量=净用量*(1+loss_rate/100)
    expected_gross = computed_qty * (Decimal("1") + (Decimal("10") / Decimal("100")))

    # costing.line_cost 口径应与扣库一致（含损耗）
    line_cost = Decimal(str(line["line_cost"]))
    assert line_cost == expected_gross

    inv = data["trace"]["inventory"]
    assert inv["inventory_line_count"] == 1
    inv_qty = Decimal(str(inv["inventory_lines"][0]["quantity"]))
    assert inv_qty == expected_gross


