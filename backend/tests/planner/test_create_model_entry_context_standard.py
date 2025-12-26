from __future__ import annotations


def test_create_model_with_entry_context_standard_creates_standard_draft_version(client):
    r = client.post(
        "/api/planner/product-models",
        json={
            "model_name": "标准入口模型",
            "model_code": "STD-ENTRY",
            "status": "draft",
            "metadata_json": {"entry_context": "standard"},
            "modules": [],
        },
    )
    assert r.status_code == 201, r.text
    model_id = r.json()["id"]
    meta = r.json().get("metadata_json") or {}
    assert meta.get("entry_context") == "standard"

    r = client.get(f"/api/planner/product-models/{model_id}/versions")
    assert r.status_code == 200, r.text
    kinds = [str(v.get("version_kind")) for v in r.json()]
    assert "standard" in kinds
    assert "sample" not in kinds


