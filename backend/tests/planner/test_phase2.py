from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.planner import models
from src.planner.services import notification_service

API_PREFIX = "/api/planner"


def _create_initiative(client: TestClient) -> str:
    code = f"INIT-{uuid.uuid4().hex[:6]}"
    payload = {
        "code": code,
        "name": f"Initiative {code}",
        "description": "Phase2",
        "owner_id": "owner",
        "currency": "CNY",
        "status": "draft",
        "tags": [],
    }
    resp = client.post(f"{API_PREFIX}/initiatives", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _create_package(client: TestClient, initiative_id: str) -> str:
    payload = {
        "initiative_id": initiative_id,
        "name": "Pkg",
        "category": "materials",
        "owner_id": "owner",
        "status": "draft",
    }
    resp = client.post(f"{API_PREFIX}/packages", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _create_line_item(client: TestClient, package_id: str) -> str:
    payload = {
        "package_id": package_id,
        "type": "material",
        "reference_code": "SKU",
        "description": "Widget",
        "unit_of_measure": "pcs",
        "quantity": "10",
        "unit_cost_estimate": "5",
        "currency": "CNY",
    }
    resp = client.post(f"{API_PREFIX}/line-items", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _baseline_scenario(db: Session, initiative_id: str, code: str = "SC-BASE") -> models.ScenarioVersion:
    scenario = models.ScenarioVersion(
        id=str(uuid.uuid4()),
        initiative_id=initiative_id,
        code=code,
        name="Baseline",
        baseline_flag=True,
        status="approved",
    )
    db.add(scenario)
    db.commit()
    return scenario


def _scenario_with_snapshot(db: Session, initiative_id: str, line_item_id: str, code: str, total: Decimal) -> models.ScenarioVersion:
    scenario = models.ScenarioVersion(
        id=str(uuid.uuid4()),
        initiative_id=initiative_id,
        code=code,
        name=code,
        baseline_flag=False,
        status="draft",
    )
    snapshot = models.ScenarioLineSnapshot(
        scenario_id=scenario.id,
        line_item_id=line_item_id,
        quantity=Decimal("10"),
        unit_cost=total,
        currency="CNY",
        fx_rate_used=Decimal("1"),
        markup_percent=None,
        total_cost=total * Decimal("10"),
        drivers={},
    )
    db.add(scenario)
    db.add(snapshot)
    db.commit()
    return scenario


def test_scenario_clone_creates_snapshots_and_job(client: TestClient, db_session: Session):
    initiative_id = _create_initiative(client)
    package_id = _create_package(client, initiative_id)
    _create_line_item(client, package_id)
    baseline = _baseline_scenario(db_session, initiative_id)

    payload = {
        "code": "SC-CLONE",
        "name": "Cloned Scenario",
        "requested_by": "tester",
    }
    resp = client.post(f"{API_PREFIX}/scenarios/{baseline.id}/clone", json=payload)
    assert resp.status_code == 202, resp.text
    body = resp.json()
    job_resp = client.get(f"{API_PREFIX}/jobs/{body['job_id']}")
    assert job_resp.status_code == 200
    job_data = job_resp.json()
    assert job_data["status"] == "completed"
    assert job_data["job_type"] == "scenario_snapshot"

    new_scenario_id = body["scenario_id"]
    snapshots = db_session.query(models.ScenarioLineSnapshot).filter_by(scenario_id=new_scenario_id).all()
    assert len(snapshots) == 1
    assert snapshots[0].total_cost == Decimal("50")


def test_scenario_diff_endpoint_returns_diffs(client: TestClient, db_session: Session):
    initiative_id = _create_initiative(client)
    package_id = _create_package(client, initiative_id)
    line_item_id = _create_line_item(client, package_id)
    scenario_a = _scenario_with_snapshot(db_session, initiative_id, line_item_id, "SC-A", Decimal("5"))
    scenario_b = _scenario_with_snapshot(db_session, initiative_id, line_item_id, "SC-B", Decimal("3"))

    resp = client.get(
        f"{API_PREFIX}/scenarios/{scenario_a.id}/diff",
        params={"against": scenario_b.id},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert Decimal(str(data["summary"]["variance"])) == Decimal("20")
    assert data["total"] == 1
    assert Decimal(str(data["line_diffs"][0]["unit_cost_diff"])) == Decimal("2")
    job_resp = client.get(f"{API_PREFIX}/jobs/{data['job_id']}")
    assert job_resp.status_code == 200
    assert job_resp.json()["job_type"] == "scenario_diff"


def test_approval_workflow_and_notifications(client: TestClient, db_session: Session):
    notification_service.clear_events()
    initiative_id = _create_initiative(client)
    package_id = _create_package(client, initiative_id)
    line_item_id = _create_line_item(client, package_id)
    scenario = _scenario_with_snapshot(db_session, initiative_id, line_item_id, "SC-APP", Decimal("4"))
    other_baseline = _baseline_scenario(db_session, initiative_id, code="SC-OLD")
    other_baseline.baseline_flag = True
    db_session.commit()

    submit_payload = {
        "scenario_id": scenario.id,
        "actor_id": "planner-1",
        "actor_role": "planner",
    }
    resp = client.post(f"{API_PREFIX}/approvals/submit", json=submit_payload)
    assert resp.status_code == 200, resp.text
    assert resp.json()["scenario_status"] == "in_review"

    approve_payload = {
        "scenario_id": scenario.id,
        "actor_id": "approver-1",
        "actor_role": "approver",
        "set_baseline": True,
    }
    resp = client.post(f"{API_PREFIX}/approvals/approve", json=approve_payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["scenario_status"] == "approved"
    assert data["baseline_flag"] is True

    # ensure other baseline cleared
    db_session.refresh(other_baseline)
    assert other_baseline.baseline_flag is False

    events = notification_service.get_events()
    assert any(event["event_type"] == "SCENARIO_APPROVED" for event in events)

    logs = (
        db_session.query(models.AuditLog)
        .filter(models.AuditLog.target_id == scenario.id)
        .all()
    )
    actions = {log.action for log in logs}
    assert {"submit", "approve"} & actions
