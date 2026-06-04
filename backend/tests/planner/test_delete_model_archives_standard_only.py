from __future__ import annotations


def test_delete_product_model_archives_standard_only_by_default(client):
    # create model
    r = client.post(
        "/api/planner/product-models",
        json={
            "model_name": "删除模型默认仅删标准版本测试",
            "model_code": "DEL-STD-ONLY-001",
            "status": "draft",
            "metadata_json": {},
            "modules": [],
        },
    )
    assert r.status_code == 201, r.text
    model_id = r.json()["id"]

    # create sample + standard versions
    r = client.post(f"/api/planner/product-models/{model_id}/versions", json={"version_kind": "sample", "metadata_json": {}})
    assert r.status_code == 201, r.text
    sample_vid = r.json()["id"]

    r = client.post(f"/api/planner/product-models/{model_id}/versions", json={"version_kind": "standard", "metadata_json": {}})
    assert r.status_code == 201, r.text
    standard_vid = r.json()["id"]

    # delete model (safety default): should only archive standard versions
    r = client.delete(f"/api/planner/product-models/{model_id}")
    assert r.status_code == 204, r.text

    # list versions -> sample should remain, standard should be gone (archived)
    r = client.get(f"/api/planner/product-models/{model_id}/versions")
    assert r.status_code == 200, r.text
    ids = {x["id"] for x in r.json()}
    assert sample_vid in ids
    assert standard_vid not in ids


