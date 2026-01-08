from __future__ import annotations

from decimal import Decimal

from src.planner import models

API_PREFIX = "/api/planner"


def _create_material(db_session, *, code: str, name: str) -> models.Material:
    m = models.Material(
        material_code=code,
        material_name=name,
        material_type="raw",
        category="fabric",
        unit="m",
        unit_price=Decimal("1.0"),
        currency="CNY",
        is_bom_material=True,
        is_active=True,
        status="active",
        metadata_json={},
    )
    db_session.add(m)
    db_session.commit()
    return m


def _create_version_with_one_line(db_session, *, model_code: str) -> tuple[models.ProductModelVersion, models.ModelVersionMaterial]:
    model = models.ProductModel(
        model_code=model_code,
        model_name=f"模型{model_code}",
        status="active",
        unit_of_measure="套",
        metadata_json={},
    )
    db_session.add(model)
    db_session.commit()

    v = models.ProductModelVersion(
        model_id=model.id,
        version_kind="standard",
        version_status="published",
        metadata_json={"standard": {"width_mm": "500", "height_mm": "500"}},
    )
    db_session.add(v)
    db_session.commit()

    base_material = _create_material(db_session, code=f"{model_code}-BASE", name=f"{model_code}底材")
    line = models.ModelVersionMaterial(
        version_id=v.id,
        material_type="real",
        material_ref_id=base_material.id,
        material_code=base_material.material_code,
        material_name=base_material.material_name,
        unit_of_measure="m",
        calculation_method="count",
        base_quantity=Decimal("1"),
        loss_rate=Decimal("0"),
        sequence_order=1,
        metadata_json={},
    )
    db_session.add(line)
    db_session.commit()
    return v, line


def test_generate_by_spec_bundle_selector_A_forces_first_phrase_preset(client, db_session):
    # Arrange: 2 components (2 versions). Only component-1 has a variant that requires token "雪尼尔".
    v1, base_line_v1 = _create_version_with_one_line(db_session, model_code="PI5")
    v2, _base_line_v2 = _create_version_with_one_line(db_session, model_code="OZU")

    repl = _create_material(db_session, code="PI5-CHENILLE", name="雪尼尔替换料")

    # Create a line variant on v1 that triggers when token "雪尼尔" is present.
    create_resp = client.post(
        f"{API_PREFIX}/product-model-versions/{v1.id}/line-variants",
        json={
            "version_id": v1.id,
            "base_line_id": base_line_v1.id,
            "priority": 200,
            "enabled": True,
            "action": "replace_self",
            "stop_on_hit": True,
            "conditions": {"spec_contains_any": ["雪尼尔"]},
            "metadata_json": {},
            "items": [
                {
                    "material_kind": "real",
                    "material_ref_id": repl.id,
                    "material_code": repl.material_code,
                    "material_name": repl.material_name,
                    "unit_of_measure": "m",
                    "calculation_method": "count",
                    "base_quantity": "1",
                }
            ],
        },
    )
    assert create_resp.status_code == 201, create_resp.text

    # Create bundle template with phrase_presets (A is the first preset row)
    tpl_payload = {
        "name": "两件套",
        "components": [
            {"model_version_id": v1.id, "width_mm": "500", "height_mm": "500", "quantity": "1"},
            {"model_version_id": v2.id, "width_mm": "1200", "height_mm": "800", "quantity": "1"},
        ],
        "metadata": {
            "phrase_presets": [
                {
                    "phrase": "A组(不需要命中)",
                    "mappings": [{"match_key": None, "match_value": "雪尼尔", "target_component_index": 0}],
                },
                {
                    "phrase": "B组",
                    "mappings": [{"match_key": None, "match_value": "背面纯色", "target_component_index": 0}],
                },
            ]
        },
    }
    r_tpl = client.post(f"{API_PREFIX}/bundle-templates", json=tpl_payload)
    assert r_tpl.status_code == 201, r_tpl.text
    code = r_tpl.json()["code"]
    assert code

    # Act: spec_text does NOT contain "雪尼尔", but contains (B:CODE:A) selector.
    spec_text = f"运营随便写(50*50)2个+丝圈地垫(120*80)1张；(B:{code}:A)"
    r = client.post(f"{API_PREFIX}/bom/generate-by-spec", json={"spec_text": spec_text, "sku_code": None})
    assert r.status_code == 200, r.text
    body = r.json()

    # Assert: variant should be triggered because selector forces preset-A mappings injecting token "雪尼尔".
    final_lines = body.get("final_material_lines") or []
    codes = [str(x.get("material_code") or "") for x in final_lines]
    assert "PI5-CHENILLE" in codes
    trace = body.get("trace") or {}
    assert str(trace.get("bundle_code") or "").startswith("B:")
    # phrase_presets should include forced marker
    presets = trace.get("phrase_presets") or []
    assert any((p.get("forced") is True) for p in presets if isinstance(p, dict))


def test_generate_by_spec_bundle_selector_prefers_preset_components_list(client, db_session):
    # Arrange: 2 versions. v1 has a variant requiring token "雪尼尔".
    v1, base_line_v1 = _create_version_with_one_line(db_session, model_code="PI5X")
    v2, _base_line_v2 = _create_version_with_one_line(db_session, model_code="OZUX")

    repl = _create_material(db_session, code="PI5X-CHENILLE", name="雪尼尔替换料")
    create_resp = client.post(
        f"{API_PREFIX}/product-model-versions/{v1.id}/line-variants",
        json={
            "version_id": v1.id,
            "base_line_id": base_line_v1.id,
            "priority": 200,
            "enabled": True,
            "action": "replace_self",
            "stop_on_hit": True,
            "conditions": {"spec_contains_any": ["雪尼尔"]},
            "metadata_json": {},
            "items": [
                {
                    "material_kind": "real",
                    "material_ref_id": repl.id,
                    "material_code": repl.material_code,
                    "material_name": repl.material_name,
                    "unit_of_measure": "m",
                    "calculation_method": "count",
                    "base_quantity": "1",
                }
            ],
        },
    )
    assert create_resp.status_code == 201, create_resp.text

    # Template top-level components can be empty in new workflow; selector should use preset.components.
    tpl_payload = {
        "name": "照片墙",
        "components": [],
        "metadata": {
            "phrase_presets": [
                {
                    "phrase": "A组",
                    "components": [
                        {"model_version_id": v1.id, "width_mm": "500", "height_mm": "500", "quantity": "2", "spec_text": "雪尼尔"},
                        {"model_version_id": v2.id, "width_mm": "1200", "height_mm": "800", "quantity": "1"},
                    ],
                }
            ]
        },
    }
    r_tpl = client.post(f"{API_PREFIX}/bundle-templates", json=tpl_payload)
    assert r_tpl.status_code == 201, r_tpl.text
    code = r_tpl.json()["code"]
    assert code

    # Act: spec_text does not contain "雪尼尔", selector should still trigger via preset component spec_text.
    spec_text = f"运营随便写；(B:{code}:A)"
    r = client.post(f"{API_PREFIX}/bom/generate-by-spec", json={"spec_text": spec_text, "sku_code": None})
    assert r.status_code == 200, r.text
    body = r.json()

    # Assert: variant should be triggered.
    final_lines = body.get("final_material_lines") or []
    codes = [str(x.get("material_code") or "") for x in final_lines]
    assert "PI5X-CHENILLE" in codes


def test_generate_by_spec_accepts_inline_selector_token(client, db_session):
    """
    Regression: allow spec_text to be directly "B:CODE:A" (no parentheses/extra chars).
    Backend should load template by CODE and apply selector A.
    """
    v1, _base_line_v1 = _create_version_with_one_line(db_session, model_code="PI5X")
    v2, _base_line_v2 = _create_version_with_one_line(db_session, model_code="OZUX")

    tpl_payload = {
        "name": "照片墙-inline",
        "components": [],
        "metadata": {
            "phrase_presets": [
                {
                    "phrase": "A组",
                    "components": [
                        {"model_version_id": v1.id, "width_mm": "500", "height_mm": "500", "quantity": "2"},
                        {"model_version_id": v2.id, "width_mm": "1200", "height_mm": "800", "quantity": "1"},
                    ],
                }
            ]
        },
    }
    r_tpl = client.post(f"{API_PREFIX}/bundle-templates", json=tpl_payload)
    assert r_tpl.status_code == 201, r_tpl.text
    code = r_tpl.json()["code"]

    # New platform-friendly format: B-CODE-A
    r = client.post(f"{API_PREFIX}/bom/generate-by-spec", json={"spec_text": f"B-{code}-A", "sku_code": None})
    assert r.status_code == 200, r.text


