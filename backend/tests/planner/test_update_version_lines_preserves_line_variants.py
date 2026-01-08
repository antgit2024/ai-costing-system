from __future__ import annotations


def test_update_version_lines_preserves_line_variants(client):
    # 1) Create a model + standard version
    r = client.post(
        "/api/planner/product-models",
        json={
            "model_name": "测试模型-变体不丢",
            "model_code": "VTP",
            "description": "x",
            "category": "CAT",
            "calc_mode": "ratio",
            "status": "draft",
            "tags": [],
            "metadata_json": {"recognition_keywords": ["测试"]},
            "modules": [],
        },
    )
    assert r.status_code == 201, r.text
    model_id = r.json()["id"]

    r = client.post(
        f"/api/planner/product-models/{model_id}/versions",
        json={"version_kind": "standard", "metadata_json": {}},
    )
    assert r.status_code == 201, r.text
    vid = r.json()["id"]

    # 2) Save lines once to get base_line_id
    r = client.put(
        f"/api/planner/product-model-versions/{vid}/lines",
        json={
            "sample": {"width_mm": "1000", "height_mm": "1000", "quantity": "1", "unit_label": "CM"},
            "standard": {"width_mm": "1000", "height_mm": "1000", "quantity": "1", "unit_label": "CM"},
            "materials": [
                {
                    "material_kind": "bom",
                    "material_ref_id": "MAT-1",
                    "material_code": "M001",
                    "material_name": "物料1",
                    "calculation_method": "area",
                    "base_quantity": "1.2",
                    "loss_rate": "2",
                    "sample_used_quantity": "1.23",
                    "standard_used_quantity": "1.23",
                    "fixed_quantity": "0",
                    "coverage_ratio": "1",
                    "metadata_json": {"sample_used_quantity": "1.23", "standard_used_quantity": "1.23"},
                }
            ],
            "processes": [],
        },
    )
    assert r.status_code == 200, r.text
    base_line_id = r.json()["materials"][0]["id"]

    # 3) Create a line variant on that base line
    r = client.post(
        f"/api/planner/product-model-versions/{vid}/line-variants",
        json={
            "version_id": vid,
            "base_line_id": base_line_id,
            "priority": 100,
            "enabled": True,
            "action": "replace_self",
            "stop_on_hit": True,
            "notes": "v0",
            "conditions": {"spec_contains_any": ["A"]},
            "metadata": {},
            "items": [
                {
                    "sequence_order": 1,
                    "material_kind": "bom",
                    "material_ref_id": "MAT-2",
                    "material_code": "M002",
                    "material_name": "物料2",
                    "calculation_method": "area",
                    "base_quantity": "1",
                    "fixed_quantity": "0",
                    "coverage_ratio": "1",
                    "loss_rate": "0",
                    "metadata_json": {},
                }
            ],
            "operator_id": "test",
        },
    )
    assert r.status_code == 201, r.text

    # 4) Save lines again (MUST preserve base_line_id, otherwise the FK cascade would delete variants)
    r = client.put(
        f"/api/planner/product-model-versions/{vid}/lines",
        json={
            "sample": {"width_mm": "1000", "height_mm": "1000", "quantity": "1", "unit_label": "CM"},
            "standard": {"width_mm": "1000", "height_mm": "1000", "quantity": "1", "unit_label": "CM"},
            "materials": [
                {
                    "id": base_line_id,
                    "material_kind": "bom",
                    "material_ref_id": "MAT-1",
                    "material_code": "M001",
                    "material_name": "物料1",
                    "calculation_method": "area",
                    "base_quantity": "1.2",
                    "loss_rate": "2",
                    "sample_used_quantity": "1.23",
                    "standard_used_quantity": "1.23",
                    "fixed_quantity": "0",
                    "coverage_ratio": "1",
                    "metadata_json": {"sample_used_quantity": "1.23", "standard_used_quantity": "1.23"},
                }
            ],
            "processes": [],
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["materials"][0]["id"] == base_line_id

    # 5) Variants should still exist after saving lines
    r = client.get(
        f"/api/planner/product-model-versions/{vid}/line-variants",
        params={"base_line_id": base_line_id},
    )
    assert r.status_code == 200, r.text
    items = r.json()
    assert len(items) == 1


