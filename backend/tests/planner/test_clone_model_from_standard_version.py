from __future__ import annotations


def test_clone_model_from_standard_version_creates_new_model_and_copies_lines_and_variants(client):
    # 1) Create a model
    r = client.post(
        "/api/planner/product-models",
        json={
            "model_name": "测试模型A",
            "model_code": "AAA",
            "description": "src",
            "category": "CAT",
            "calc_mode": "ratio",
            "status": "draft",
            "tags": [],
            "metadata_json": {},
            "modules": [],
        },
    )
    assert r.status_code == 201, r.text
    model_id = r.json()["id"]

    # 2) Create a standard version
    r = client.post(
        f"/api/planner/product-models/{model_id}/versions",
        json={"version_kind": "standard", "metadata_json": {}},
    )
    assert r.status_code == 201, r.text
    src_version_id = r.json()["id"]

    # 3) Save lines so base_line_id exists
    r = client.put(
        f"/api/planner/product-model-versions/{src_version_id}/lines",
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
            "processes": [
                {
                    "process_id": "PROC-1",
                    "pricing_method": "count",
                    "base_minutes": "1",
                    "unit_minutes": "2",
                    "sample_minutes": "3",
                    "standard_minutes": "3",
                    "metadata_json": {"pricing_method": "count", "base_minutes": "1", "unit_minutes": "2"},
                }
            ],
        },
    )
    assert r.status_code == 200, r.text
    src_lines = r.json()
    assert len(src_lines["materials"]) == 1
    src_base_line_id = src_lines["materials"][0]["id"]

    # 4) Add one line variant on that base line
    r = client.post(
        f"/api/planner/product-model-versions/{src_version_id}/line-variants",
        json={
            "version_id": src_version_id,
            "base_line_id": src_base_line_id,
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
                    "unit_of_measure": "平米",
                    "calculation_method": "area",
                    "base_quantity": 1,
                    "fixed_quantity": 0,
                    "coverage_ratio": 1,
                    "loss_rate": 0,
                    "metadata_json": {},
                }
            ],
            "operator_id": "tester",
        },
    )
    assert r.status_code == 201, r.text

    # 5) Clone model from standard version
    r = client.post(
        f"/api/planner/product-model-versions/{src_version_id}/clone-model",
        json={"include_line_variants": True, "operator_id": "tester"},
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["new_model_id"] != model_id
    assert data["new_standard_version_id"] != src_version_id
    assert data["new_model_code"] != "AAA"

    # 6) Verify lines copied
    new_vid = data["new_standard_version_id"]
    r = client.get(f"/api/planner/product-model-versions/{new_vid}/lines")
    assert r.status_code == 200, r.text
    new_lines = r.json()
    assert len(new_lines["materials"]) == 1
    assert len(new_lines["processes"]) == 1
    assert str(new_lines["materials"][0]["material_ref_id"]) == "MAT-1"

    # 7) Verify variants copied and base_line_id remapped
    r = client.get(f"/api/planner/product-model-versions/{new_vid}/line-variants")
    assert r.status_code == 200, r.text
    variants = r.json()
    assert len(variants) == 1
    assert variants[0]["base_line_id"] != src_base_line_id

