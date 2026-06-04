from __future__ import annotations


def test_list_models_include_archived_param(client):
    # create model
    r = client.post(
        "/api/planner/product-models",
        json={
            "model_name": "列表包含归档模型测试",
            "model_code": "INCLUDE-ARCHIVED-001",
            "status": "draft",
            # Ensure initial version is standard so DELETE archives it and then archives model itself.
            "metadata_json": {"entry_context": "standard"},
            "modules": [],
        },
    )
    assert r.status_code == 201, r.text
    model_id = r.json()["id"]

    # archive via delete endpoint (safety default may only archive standard versions; but if no versions, model gets archived)
    r = client.delete(f"/api/planner/product-models/{model_id}")
    assert r.status_code == 204, r.text

    # default list should NOT include archived
    r = client.get("/api/planner/product-models?page=1&page_size=200")
    assert r.status_code == 200, r.text
    ids = {x["id"] for x in r.json()["items"]}
    assert model_id not in ids

    # include_archived=true should include it
    r = client.get("/api/planner/product-models?page=1&page_size=200&include_archived=true")
    assert r.status_code == 200, r.text
    ids = {x["id"] for x in r.json()["items"]}
    assert model_id in ids


