from __future__ import annotations

import json
from datetime import datetime, timezone

from src.planner import models


def create_material(code: str, name: str, **kwargs):
    defaults = dict(
        material_type="raw",
        unit_price=1,
        currency="CNY",
        status="active",
        is_active=True,
    )
    defaults.update(kwargs)
    return models.Material(
        material_code=code,
        material_name=name,
        **defaults,
    )


def test_list_materials(client, db_session):
    mat1 = create_material("MAT-001", "Aluminum Frame", category="metal")
    mat2 = create_material("MAT-002", "Plastic Cover", category="plastic", status="inactive", is_active=False)
    db_session.add_all([mat1, mat2])
    db_session.commit()

    response = client.get("/api/planner/base-config/materials?page=1&page_size=10&search=MAT-00")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert len(payload["items"]) == 2
    assert payload["items"][0]["material_code"].startswith("MAT-00")

    response = client.get("/api/planner/base-config/materials?status=inactive")
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["material_code"] == "MAT-002"


def test_update_material_status(client, db_session):
    material = create_material("MAT-010", "Test Material")
    db_session.add(material)
    db_session.commit()

    response = client.patch(
        f"/api/planner/base-config/materials/{material.id}",
        json={"is_active": False, "status": "inactive"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["is_active"] is False
    assert payload["status"] == "inactive"

    db_session.refresh(material)
    assert material.is_active is False
    assert material.status == "inactive"


def test_export_materials_csv(client, db_session):
    db_session.add(create_material("MAT-EX-1", "Export 1"))
    db_session.commit()

    response = client.post(
        "/api/planner/base-config/materials/export",
        json={"format": "csv"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "MAT-EX-1" in response.content.decode("utf-8")


def test_list_material_sync_jobs(client, db_session):
    job1 = models.MaterialSyncJob(
        job_type="materials",
        config_path="config.json",
        requested_by="tester",
        status="succeeded",
        result_json={"created": 1},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    job2 = models.MaterialSyncJob(
        job_type="materials",
        config_path="config.json",
        requested_by="tester",
        status="failed",
        error_message="boom",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add_all([job1, job2])
    db_session.commit()

    response = client.get("/api/planner/base-config/materials/sync-jobs?page=1&page_size=10")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert len(payload["items"]) == 2

