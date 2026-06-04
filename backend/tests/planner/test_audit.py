from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.planner import models

API_PREFIX = "/api/planner"


def _seed_audit_logs(db: Session) -> List[models.AuditLog]:
    now = datetime.now(timezone.utc)
    logs = [
        models.AuditLog(
            target_type="scenario",
            target_id="SC-1",
            action="scenario_export",
            actor_id="user-1",
            payload={"job_id": "job-1"},
            trace_id="trace-1",
            created_at=now - timedelta(minutes=5),
        ),
        models.AuditLog(
            target_type="scenario",
            target_id="SC-1",
            action="scenario_approve",
            actor_id="user-2",
            payload={},
            trace_id="trace-2",
            created_at=now - timedelta(minutes=2),
        ),
        models.AuditLog(
            target_type="scenario",
            target_id="SC-2",
            action="scenario_export",
            actor_id="user-3",
            payload={},
            trace_id="trace-3",
            created_at=now - timedelta(minutes=1),
        ),
    ]
    db.add_all(logs)
    db.commit()
    return logs


def test_audit_list_filters_and_pagination(client: TestClient, db_session: Session):
    logs = _seed_audit_logs(db_session)

    resp = client.get(
        f"{API_PREFIX}/audit",
        params={"target_type": "scenario", "target_id": "SC-1", "page": 1, "page_size": 1},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert data["page"] == 1
    assert len(data["items"]) == 1
    # should be most recent SC-1 record (trace-2)
    assert data["items"][0]["trace_id"] == "trace-2"

    resp_page2 = client.get(
        f"{API_PREFIX}/audit",
        params={"target_type": "scenario", "target_id": "SC-1", "page": 2, "page_size": 1},
    )
    assert resp_page2.status_code == 200
    data_page2 = resp_page2.json()
    assert len(data_page2["items"]) == 1
    assert data_page2["items"][0]["trace_id"] == "trace-1"


def test_audit_filter_by_action_and_trace(client: TestClient, db_session: Session):
    _seed_audit_logs(db_session)

    resp = client.get(
        f"{API_PREFIX}/audit",
        params={"action": "scenario_export", "trace_id": "trace-3"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    item = data["items"][0]
    assert item["trace_id"] == "trace-3"
    assert item["action"] == "scenario_export"









