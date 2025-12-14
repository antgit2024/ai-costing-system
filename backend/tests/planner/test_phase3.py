from __future__ import annotations

import hashlib
import hmac
import json
import uuid

import respx
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy.orm import Session

from src.config import settings
from src.planner import models
from src.planner.integrations import benchmark_client, executor_client, message_bus
from src.planner.services import notification_service

API_PREFIX = "/api/planner"


def _create_initiative(client: TestClient) -> str:
    code = f"INIT-{uuid.uuid4().hex[:5]}"
    payload = {
        "code": code,
        "name": code,
        "description": "phase3",
        "owner_id": "owner",
        "currency": "CNY",
        "status": "draft",
        "tags": [],
    }
    resp = client.post(f"{API_PREFIX}/initiatives", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _approved_scenario(db: Session, initiative_id: str, code: str = "SC-EXP") -> models.ScenarioVersion:
    scenario = models.ScenarioVersion(
        id=str(uuid.uuid4()),
        initiative_id=initiative_id,
        code=code,
        name=code,
        status="approved",
        baseline_flag=True,
        total_cost=10,
    )
    db.add(scenario)
    db.commit()
    return scenario


def _sign_callback(payload: dict) -> str:
    secret = settings.executor_callback_secret.encode("utf-8")
    body = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hmac.new(secret, body, hashlib.sha256).hexdigest()


@respx.mock
def test_scenario_export_executor_flow(client: TestClient, db_session: Session):
    message_bus.clear_events()
    notification_service.clear_events()
    prev_flag = settings.feature_flag_mock_integrations
    settings.feature_flag_mock_integrations = False
    executor_client.reset_client()

    route = respx.post(f"{settings.executor_base_url.rstrip('/')}/exports").mock(
        return_value=Response(200, json={"status": "accepted", "reference_id": "EXEC-123"})
    )

    try:
        initiative_id = _create_initiative(client)
        scenario = _approved_scenario(db_session, initiative_id)
        payload = {"requested_by": "integrator", "comment": "sync"}
        resp = client.post(f"{API_PREFIX}/scenarios/{scenario.id}/export", json=payload)
        assert resp.status_code == 202, resp.text
        assert route.called

        callback_record = (
            db_session.query(models.PlannerExecutorCallback)
            .filter(models.PlannerExecutorCallback.scenario_id == scenario.id)
            .one()
        )
        trace_id = callback_record.trace_id

        callback_payload = {"scenario_id": scenario.id, "status": "done", "trace_id": trace_id}
        signature = _sign_callback(callback_payload)
        callback_resp = client.post(
            f"{API_PREFIX}/executor/callback",
            json=callback_payload,
            headers={"X-Signature": signature},
        )
        assert callback_resp.status_code == 202
        db_session.refresh(callback_record)
        assert callback_record.status == "done"
        assert callback_record.signature == signature

        events = notification_service.get_events()
        assert any(event["event_type"] == "SCENARIO_EXPORTED" for event in events)
        assert any(event["event_type"] == "SCENARIO_EXPORT_CALLBACK" for event in events)
        bus_events = message_bus.get_published_events()
        assert any(event["event_type"] == "SCENARIO_EXPORTED" for event in bus_events)
    finally:
        settings.feature_flag_mock_integrations = prev_flag
        executor_client.reset_client()
        message_bus.clear_events()
        notification_service.clear_events()


def test_scenario_list_and_favorites(client: TestClient, db_session: Session):
    initiative_id = _create_initiative(client)
    scenario_a = _approved_scenario(db_session, initiative_id, code="SC-A")
    scenario_b = _approved_scenario(db_session, initiative_id, code="SC-B")

    resp = client.get(f"{API_PREFIX}/scenarios", params={"initiative_id": initiative_id})
    assert resp.status_code == 200
    assert resp.json()["total"] == 2

    fav_payload = {"user_id": "user-1"}
    fav_resp = client.post(f"{API_PREFIX}/scenarios/{scenario_a.id}/favorite", json=fav_payload)
    assert fav_resp.status_code == 201
    assert fav_resp.json()["favorite"] is True

    favorite_list = client.get(
        f"{API_PREFIX}/scenarios",
        params={"initiative_id": initiative_id, "favorite_only": "true", "user_id": "user-1"},
    ).json()
    assert favorite_list["total"] == 1
    assert favorite_list["items"][0]["id"] == scenario_a.id

    unfav_resp = client.delete(
        f"{API_PREFIX}/scenarios/{scenario_a.id}/favorite",
        params={"user_id": "user-1"},
    )
    assert unfav_resp.status_code == 200
    assert unfav_resp.json()["favorite"] is False

    bad_resp = client.get(
        f"{API_PREFIX}/scenarios",
        params={"favorite_only": "true"},
    )
    assert bad_resp.status_code == 400


@respx.mock
def test_benchmark_suggest_and_favorites(client: TestClient):
    prev_flag = settings.feature_flag_mock_integrations
    settings.feature_flag_mock_integrations = False
    benchmark_client.clear_cache()
    route = respx.get(f"{settings.benchmark_api_base_url.rstrip('/')}/benchmarks").mock(
        return_value=Response(
            200,
            json={
                "category": "materials",
                "metric": "unit_cost",
                "items": [{"value": 4.2, "confidence": 0.7}],
                "source": "remote",
            },
        )
    )

    try:
        resp = client.get(
            f"{API_PREFIX}/benchmarks/suggest",
            params={"category": "materials", "metric": "unit_cost"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["source"] == "remote"
        assert route.called

        fav_payload = {
            "benchmark_key": "materials:unit_cost",
            "user_id": "user-1",
            "payload": {"value": 4.2},
        }
        fav_resp = client.post(f"{API_PREFIX}/benchmarks/favorites", json=fav_payload)
        assert fav_resp.status_code == 201
        list_resp = client.get(f"{API_PREFIX}/benchmarks/favorites", params={"user_id": "user-1"})
        assert len(list_resp.json()) == 1

        favorite_id = list_resp.json()[0]["id"]
        delete_resp = client.delete(
            f"{API_PREFIX}/benchmarks/favorites/{favorite_id}",
            params={"user_id": "user-1"},
        )
        assert delete_resp.status_code == 204
    finally:
        settings.feature_flag_mock_integrations = prev_flag


@respx.mock
def test_benchmark_fallback_on_failure(client: TestClient):
    prev_mock = settings.feature_flag_mock_integrations
    prev_fail_open = settings.benchmark_fail_open
    settings.feature_flag_mock_integrations = False
    settings.benchmark_fail_open = True
    benchmark_client.clear_cache()
    route = respx.get(f"{settings.benchmark_api_base_url.rstrip('/')}/benchmarks").mock(
        return_value=Response(500)
    )
    try:
        resp = client.get(
            f"{API_PREFIX}/benchmarks/suggest",
            params={"category": "materials", "metric": "unit_cost"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["source"] in {"fallback", "mock"}
        assert route.called
    finally:
        settings.feature_flag_mock_integrations = prev_mock
        settings.benchmark_fail_open = prev_fail_open
