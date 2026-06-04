from __future__ import annotations


def _create_model(client, *, name: str, code: str, version_status: str | None = None) -> dict:
    r = client.post(
        "/api/planner/product-models",
        json={
            "model_name": name,
            "model_code": code,
            "status": "draft",
            "metadata_json": {},
            "modules": [],
        },
    )
    assert r.status_code == 201, r.text
    model = r.json()
    if version_status:
        r2 = client.post(
            f"/api/planner/product-models/{model['id']}/versions",
            json={"version_kind": "standard", "metadata_json": {}, "version_status": version_status},
        )
        # version_status may be ignored by schema; published needs explicit publish endpoint in other tests.
        assert r2.status_code in (201, 400), r2.text
    return model


def test_delete_model_allowed_when_no_published_and_no_sku_binding(client):
    model = _create_model(client, name="可删模型", code="DEL-OK")
    # create a draft standard version
    r = client.post(
        f"/api/planner/product-models/{model['id']}/versions",
        json={"version_kind": "standard", "metadata_json": {}},
    )
    assert r.status_code == 201, r.text

    r = client.delete(f"/api/planner/product-models/{model['id']}")
    assert r.status_code == 204, r.text


def test_delete_model_blocked_when_published_standard_exists(client):
    model = _create_model(client, name="不可删模型-已发布", code="DEL-BLOCK-PUB")
    # create a standard version and mark it published via publish endpoint
    r = client.post(
        f"/api/planner/product-models/{model['id']}/versions",
        json={"version_kind": "standard", "metadata_json": {}},
    )
    assert r.status_code == 201, r.text
    vid = r.json()["id"]

    # publish requires non-empty lines
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
                    "base_quantity": "1",
                    "loss_rate": "0",
                    "sample_used_quantity": "1",
                    "standard_used_quantity": "1",
                    "fixed_quantity": "0",
                    "coverage_ratio": "1",
                    "metadata_json": {"sample_used_quantity": "1", "standard_used_quantity": "1"},
                }
            ],
            "processes": [],
        },
    )
    assert r.status_code == 200, r.text

    r = client.post(f"/api/planner/product-model-versions/{vid}/publish", json={"published_by": "tester", "note": "publish"})
    assert r.status_code == 200, r.text

    r = client.delete(f"/api/planner/product-models/{model['id']}")
    assert r.status_code == 400
    assert "published" in (r.json().get("detail") or "")


