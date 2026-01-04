from __future__ import annotations

from decimal import Decimal

from src.planner import models

API_PREFIX = "/api/planner"


def _create_material(db_session, *, code: str, name: str) -> models.Material:
    material = models.Material(
        material_code=code,
        material_name=name,
        material_type="raw",
        category="fabric",
        unit="m2",
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


def test_bom_generate_injects_model_token_for_variant_matching(client, db_session):
    """
    Guardrail: variant rules can be anchored to the bound model code even if spec_text doesn't contain it.

    This prevents cross-model false hits when materials are reused across categories.
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
        version_label="PI5-STANDARD-TEST-01",
        metadata_json={"standard": {"width_mm": 1000, "height_mm": 1000, "quantity": 1}},
    )
    db_session.add(version)
    db_session.flush()

    base_material = _create_material(db_session, code="FAB-BASE", name="基础面料")
    replacement_material = _create_material(db_session, code="WB01176", name="棉麻布300本白防水")

    base_line = models.ModelVersionMaterial(
        version_id=version.id,
        material_type="real",
        material_ref_id=base_material.id,
        material_code=base_material.material_code,
        material_name=base_material.material_name,
        unit_of_measure="m2",
        calculation_method="area",
        base_quantity=Decimal("1"),
        loss_rate=Decimal("0"),
        sequence_order=1,
        metadata_json={"fixed_quantity": "0", "coverage_ratio": "1"},
    )
    db_session.add(base_line)
    db_session.flush()

    # Bind SKU barcode to this published standard version
    sku = "1003433256386"
    db_session.add(
        models.SkuModelVersionMapping(
            sku_code=sku,
            model_version_id=version.id,
            is_active=True,
            metadata_json={},
        )
    )
    db_session.flush()

    # Create a variant anchored to MODEL:PI5 (not present in spec_text)
    create_variant = client.post(
        f"{API_PREFIX}/product-model-versions/{version.id}/line-variants",
        json={
            "version_id": version.id,
            "base_line_id": base_line.id,
            "priority": 100,
            "enabled": True,
            "action": "replace_self",
            "stop_on_hit": True,
            "conditions": {"spec_contains_all": ["MODEL:PI5"]},
            "items": [
                {
                    "material_kind": "real",
                    "material_ref_id": replacement_material.id,
                    "material_code": replacement_material.material_code,
                    "material_name": replacement_material.material_name,
                    "unit_of_measure": "m2",
                    "calculation_method": "area",
                    "base_quantity": "1",
                }
            ],
        },
    )
    assert create_variant.status_code == 201, create_variant.text
    variant_id = create_variant.json()["id"]

    # Spec text doesn't contain "PI5" at all; match should still happen via runtime token injection.
    bom_resp = client.post(
        f"{API_PREFIX}/bom/generate",
        json={
            "sku_code": sku,
            "spec_text": "枕套 / 黄金绒双面印花（棕色毛球） 45X45",
            "quantity": "1",
        },
    )
    assert bom_resp.status_code == 200, bom_resp.text
    body = bom_resp.json()
    assert body["final_material_lines"][0]["variant_id"] == variant_id
    assert body["final_material_lines"][0]["material_code"] == replacement_material.material_code

    trace = body.get("trace") or {}
    runtime_tokens = trace.get("runtime_tokens") or []
    assert "MODEL:PI5" in runtime_tokens
    assert any(t.startswith("BOUND_VERSION:") for t in runtime_tokens)
    assert f"SKU:{sku}" in runtime_tokens


