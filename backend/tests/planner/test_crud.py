from datetime import date
import time

from fastapi.testclient import TestClient


API_PREFIX = "/api/planner"


def _create_initiative(client: TestClient) -> str:
    payload = {
        "code": "INIT-001",
        "name": "Launch Alpha",
        "description": "Initial test initiative",
        "owner_id": "owner-1",
        "sponsor": "exec-1",
        "currency": "CNY",
        "status": "draft",
        "target_launch_date": date.today().isoformat(),
        "tags": ["alpha", "test"],
    }
    response = client.post(f"{API_PREFIX}/initiatives", json=payload)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _create_package(client: TestClient, initiative_id: str, name: str, parent_id: str | None = None) -> str:
    payload = {
        "initiative_id": initiative_id,
        "name": name,
        "category": "materials",
        "parent_package_id": parent_id,
        "owner_id": "owner-1",
        "status": "in_progress",
        "notes": "pkg",
    }
    response = client.post(f"{API_PREFIX}/packages", json=payload)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_initiative_crud_flow(client: TestClient):
    initiative_id = _create_initiative(client)

    list_response = client.get(f"{API_PREFIX}/initiatives", params={"status": "draft"})
    assert list_response.status_code == 200
    body = list_response.json()
    assert body["total"] == 1

    update_payload = {"name": "Launch Alpha Updated", "status": "review"}
    update_resp = client.put(f"{API_PREFIX}/initiatives/{initiative_id}", json=update_payload)
    assert update_resp.status_code == 200
    assert update_resp.json()["status"] == "review"

    delete_resp = client.delete(f"{API_PREFIX}/initiatives/{initiative_id}")
    assert delete_resp.status_code == 204


def test_package_tree_and_line_items_with_quotes(client: TestClient):
    initiative_id = _create_initiative(client)
    parent_pkg = _create_package(client, initiative_id, "Materials")
    child_pkg = _create_package(client, initiative_id, "Sub Materials", parent_pkg)

    tree_resp = client.get(f"{API_PREFIX}/packages/tree", params={"initiative_id": initiative_id})
    assert tree_resp.status_code == 200
    tree = tree_resp.json()
    assert len(tree) == 1
    assert tree[0]["children"][0]["id"] == child_pkg

    line_payload = {
        "package_id": child_pkg,
        "type": "material",
        "reference_code": "SKU-1",
        "description": "Steel Part",
        "unit_of_measure": "pcs",
        "quantity": "10",
        "unit_cost_estimate": "2.5",
        "currency": "CNY",
        "supplier_id": "SUP-1",
        "status": "open",
        "metadata": {"color": "silver"},
    }
    line_resp = client.post(f"{API_PREFIX}/line-items", json=line_payload)
    assert line_resp.status_code == 201, line_resp.text
    line_item = line_resp.json()

    quote_payload = {
        "supplier_name": "Vendor A",
        "contact": "vendor@example.com",
        "line_item_id": line_item["id"],
        "quote_version": 1,
        "currency": "CNY",
        "unit_cost": "2.4",
        "moq": 100,
        "lead_time_days": 15,
        "attachments": [],
    }
    quote_resp = client.post(
        f"{API_PREFIX}/line-items/{line_item['id']}/supplier-quotes",
        params={"set_preferred": "true"},
        json=quote_payload,
    )
    assert quote_resp.status_code == 201, quote_resp.text
    quote_id = quote_resp.json()["id"]

    patch_payload = {"preferred_quote_id": quote_id}
    patch_resp = client.patch(f"{API_PREFIX}/line-items/{line_item['id']}", json=patch_payload)
    assert patch_resp.status_code == 200
    assert patch_resp.json()["preferred_quote_id"] == quote_id


def test_csv_import_job_and_status(client: TestClient):
    initiative_id = _create_initiative(client)
    package_id = _create_package(client, initiative_id, "Bulk Package")

    csv_content = (
        "package_id,type,description,unit_of_measure,quantity,unit_cost_estimate,currency\n"
        f"{package_id},material,Imported Item,pcs,5,1.2,CNY\n"
    )
    files = {"file": ("import.csv", csv_content, "text/csv")}
    data = {"initiative_id": initiative_id, "requested_by": "tester"}
    response = client.post(f"{API_PREFIX}/line-items/import", files=files, data=data)
    assert response.status_code == 202, response.text
    job_id = response.json()["id"]

    job_payload = {}
    for _ in range(5):
        status_response = client.get(f"{API_PREFIX}/line-items/import-jobs/{job_id}")
        assert status_response.status_code == 200
        job_payload = status_response.json()
        if job_payload["status"] != "pending":
            break
        time.sleep(0.05)

    assert job_payload["total_rows"] == 1
    assert job_payload["processed_rows"] == 1


def test_assumption_versioning(client: TestClient):
    initiative_id = _create_initiative(client)
    assumption_payload = {
        "initiative_id": initiative_id,
        "name": "FX Rate",
        "type": "fx",
        "value": "6.9",
        "unit": "CNY/USD",
        "effective_date": date.today().isoformat(),
        "source": "manual",
        "metadata": {},
    }
    resp = client.post(f"{API_PREFIX}/assumptions", json=assumption_payload)
    assert resp.status_code == 201, resp.text

    dup_resp = client.post(f"{API_PREFIX}/assumptions", json=assumption_payload)
    assert dup_resp.status_code == 400

    latest_resp = client.get(
        f"{API_PREFIX}/assumptions/latest",
        params={"initiative_id": initiative_id, "type": "fx"},
    )
    assert latest_resp.status_code == 200
    data = latest_resp.json()
    assert data[0]["latest"]["value"] == "6.9"
