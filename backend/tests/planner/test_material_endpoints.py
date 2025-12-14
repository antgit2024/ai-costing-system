from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient

from src.planner import models

API_PREFIX = "/api/planner/base-config"


def _create_material(
    db,
    *,
    code: str,
    name: str,
    material_type: str = "raw",
    category: str | None = None,
    status: str = "active",
    is_active: bool = True,
):
    material = models.Material(
        material_code=code,
        material_name=name,
        material_type=material_type,
        category=category,
        unit="pcs",
        unit_price=Decimal("12.34"),
        currency="CNY",
        supplier_name="Vendor",
        status=status,
        is_active=is_active,
    )
    db.add(material)
    db.commit()
    db.refresh(material)
    return material


def test_material_listing_and_patch(client: TestClient, db_session):
    mat1 = _create_material(db_session, code="MAT-001", name="Frame A", category="frame")
    _create_material(
        db_session,
        code="MAT-002",
        name="Glass Panel",
        material_type="glass",
        category="panel",
        status="draft",
        is_active=False,
    )

    resp = client.get(
        f"{API_PREFIX}/materials",
        params={"search": "frame", "page": 1, "page_size": 10},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["material_code"] == "MAT-001"

    patch_resp = client.patch(
        f"{API_PREFIX}/materials/{mat1.id}",
        json={"is_active": False, "status": "inactive"},
    )
    assert patch_resp.status_code == 200
    payload = patch_resp.json()
    assert payload["is_active"] is False
    assert payload["status"] == "inactive"


def test_material_export_csv_and_xlsx(client: TestClient, db_session):
    _create_material(db_session, code="MAT-CSV", name="CSV Item")
    _create_material(db_session, code="MAT-XLSX", name="XLSX Item")

    csv_resp = client.post(f"{API_PREFIX}/materials/export", json={"format": "csv"})
    assert csv_resp.status_code == 200
    assert csv_resp.headers["content-type"].startswith("text/csv")
    assert "MAT-CSV" in csv_resp.content.decode("utf-8")

    xlsx_resp = client.post(f"{API_PREFIX}/materials/export", json={"format": "xlsx"})
    assert xlsx_resp.status_code == 200
    assert (
        xlsx_resp.headers["content-type"]
        == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    # Ensure binary payload is non-empty
    assert len(xlsx_resp.content) > 100


def test_material_sync_job_listing(client: TestClient, db_session):
    job1 = models.MaterialSyncJob(
        job_type="materials",
        config_path="/tmp/config.json",
        requested_by="tester",
        status="succeeded",
        limit=10,
        dry_run=False,
        payload={},
        result_json={"created": 10},
    )
    job2 = models.MaterialSyncJob(
        job_type="materials",
        config_path="/tmp/config.json",
        requested_by="tester",
        status="failed",
        limit=5,
        dry_run=True,
        payload={},
        result_json={},
        error_message="mock error",
    )
    db_session.add_all([job1, job2])
    db_session.commit()

    list_resp = client.get(f"{API_PREFIX}/materials/sync-jobs", params={"page": 1, "page_size": 5})
    assert list_resp.status_code == 200
    data = list_resp.json()
    assert data["total"] == 2

    detail_resp = client.get(f"{API_PREFIX}/materials/sync-jobs/{job1.id}")
    assert detail_resp.status_code == 200
    assert detail_resp.json()["status"] == "succeeded"

