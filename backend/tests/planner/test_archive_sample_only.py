from __future__ import annotations


def test_archive_sample_only_does_not_archive_standard_versions(client):
    # create model
    r = client.post(
        "/api/planner/product-models",
        json={
            "model_name": "打样/标准拆分删除测试",
            "model_code": "SM-STD-001",
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

    # archive sample only
    r = client.post(f"/api/planner/product-models/{model_id}/archive-sample")
    assert r.status_code == 204, r.text

    # list versions -> standard should remain, sample should be gone (archived)
    r = client.get(f"/api/planner/product-models/{model_id}/versions")
    assert r.status_code == 200, r.text
    ids = {x["id"] for x in r.json()}
    assert standard_vid in ids
    assert sample_vid not in ids


