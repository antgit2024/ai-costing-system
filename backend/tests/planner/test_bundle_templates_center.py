from __future__ import annotations


def test_bundle_templates_crud_flow(client):
    # create
    payload = {
        "name": "三件套",
        "components": [
            {
                "model_version_id": "11111111-1111-1111-1111-111111111111",
                "width_mm": "400",
                "height_mm": "500",
                "quantity": "1",
                "spec_text": "背面纯色",
            }
        ],
        "metadata": {"category": "gift", "tags": ["活动款", "渠道A"]},
    }
    r = client.post("/api/planner/bundle-templates", json=payload)
    assert r.status_code == 201, r.text
    data = r.json()
    tid = data["id"]
    code = data["code"]
    assert code

    # list (filter by tag)
    r = client.get("/api/planner/bundle-templates", params={"tag": "渠道A", "page": 1, "page_size": 20})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] >= 1
    assert any(it["id"] == tid for it in body["items"])

    # get by code
    r = client.get(f"/api/planner/bundle-templates/by-code/{code}")
    assert r.status_code == 200, r.text
    assert r.json()["id"] == tid

    # update name
    r = client.patch(f"/api/planner/bundle-templates/{tid}", json={"name": "三件套-改名"})
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "三件套-改名"

    # clone
    r = client.post(f"/api/planner/bundle-templates/{tid}/clone", json={})
    assert r.status_code == 201, r.text
    assert r.json()["id"] != tid
    assert r.json()["code"] != code

    # archive
    r = client.delete(f"/api/planner/bundle-templates/{tid}")
    assert r.status_code == 204, r.text

    # list default should exclude archived
    r = client.get("/api/planner/bundle-templates", params={"page": 1, "page_size": 50})
    assert r.status_code == 200, r.text
    ids = [it["id"] for it in r.json().get("items") or []]
    assert tid not in ids

    # list include_archived should include it
    r = client.get("/api/planner/bundle-templates", params={"include_archived": True, "page": 1, "page_size": 50})
    assert r.status_code == 200, r.text
    ids = [it["id"] for it in r.json().get("items") or []]
    assert tid in ids


