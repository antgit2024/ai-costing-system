from __future__ import annotations

from decimal import Decimal

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


def _create_model_version(db_session) -> tuple[models.ProductModelVersion, models.ModelVersionMaterial]:
    model = models.ProductModel(
        model_code="PM-LINE-V1",
        model_name="画框基准",
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

    base_material = _create_material(db_session, code="MAT-BASE", name="画框149")
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
    return version, line


def test_line_variant_crud_and_bom_generation(client, db_session):
    version, base_line = _create_model_version(db_session)
    replacement_material = _create_material(db_session, code="MAT-024", name="画框024")
    addon_material = _create_material(db_session, code="MAT-HOOK", name="配套挂扣")

    create_resp = client.post(
        f"{API_PREFIX}/product-model-versions/{version.id}/line-variants",
        json={
            "version_id": version.id,
            "base_line_id": base_line.id,
            "priority": 200,
            "enabled": True,
            "action": "replace_bundle",
            "stop_on_hit": True,
            "conditions": {"spec_contains_any": ["024画框"]},
            "metadata_json": {"slot": "frame"},
            "items": [
                {
                    "material_kind": "real",
                    "material_ref_id": replacement_material.id,
                    "material_code": replacement_material.material_code,
                    "material_name": replacement_material.material_name,
                    "unit_of_measure": "m",
                    "calculation_method": "area",
                    "base_quantity": "0.6",
                },
                {
                    "material_kind": "real",
                    "material_ref_id": addon_material.id,
                    "material_code": addon_material.material_code,
                    "material_name": addon_material.material_name,
                    "calculation_method": "count",
                    "base_quantity": "2",
                },
            ],
        },
    )
    assert create_resp.status_code == 201, create_resp.text
    variant_id = create_resp.json()["id"]
    assert len(create_resp.json()["items"]) == 2

    list_resp = client.get(f"{API_PREFIX}/product-model-versions/{version.id}/line-variants")
    assert list_resp.status_code == 200
    assert list_resp.json()[0]["id"] == variant_id

    patch_resp = client.patch(
        f"{API_PREFIX}/line-variants/{variant_id}",
        json={"priority": 180, "notes": "updated"},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["priority"] == 180
    assert patch_resp.json()["notes"] == "updated"

    replace_items_resp = client.put(
        f"{API_PREFIX}/line-variants/{variant_id}/items",
        json={
            "items": [
                {
                    "material_kind": "real",
                    "material_ref_id": replacement_material.id,
                    "calculation_method": "area",
                    "base_quantity": "0.7",
                }
            ]
        },
    )
    assert replace_items_resp.status_code == 200
    assert len(replace_items_resp.json()["items"]) == 1

    spec_resp = client.post(
        f"{API_PREFIX}/spec/parse",
        json={"spec_text": "约50*140;024画框+推拉"},
    )
    assert spec_resp.status_code == 200
    body = spec_resp.json()
    assert body["width_cm"] == "50"
    assert "024画框" in body["tokens"]

    bom_resp = client.post(
        f"{API_PREFIX}/bom/generate",
        json={
            "model_version_id": version.id,
            "spec_text": "约50*140;024画框",
            "quantity": "1",
        },
    )
    assert bom_resp.status_code == 200, bom_resp.text
    bom_data = bom_resp.json()
    assert len(bom_data["final_material_lines"]) == 1
    final_line = bom_data["final_material_lines"][0]
    assert final_line["variant_id"] == variant_id
    assert final_line["material_code"] == replacement_material.material_code

