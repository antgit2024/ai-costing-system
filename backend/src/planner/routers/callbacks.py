from __future__ import annotations

import hashlib
import hmac
import json

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import desc
from sqlalchemy.orm import Session

from .. import models
from ...config import settings
from ..dependencies import get_db_session
from ..services import audit_service, notification_service

router = APIRouter(tags=["Executor"], prefix="/executor")


def _verify_signature(body: dict, signature: str) -> bool:
    secret = settings.executor_callback_secret.encode("utf-8")
    payload = json.dumps(body, sort_keys=True).encode("utf-8")
    expected = hmac.new(secret, payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.post("/callback", status_code=status.HTTP_202_ACCEPTED)
async def executor_callback(
    payload: dict,
    signature: str = Header(..., alias="X-Signature"),
    db: Session = Depends(get_db_session),
):
    if not _verify_signature(payload, signature):
        raise HTTPException(status_code=403, detail="Invalid signature")

    scenario_id = payload.get("scenario_id")
    if not scenario_id:
        raise HTTPException(status_code=400, detail="Missing scenario_id")

    scenario = db.get(models.ScenarioVersion, scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")

    trace_id = payload.get("trace_id", "")
    record_query = db.query(models.PlannerExecutorCallback).filter(
        models.PlannerExecutorCallback.scenario_id == scenario_id
    )
    if trace_id:
        record_query = record_query.filter(models.PlannerExecutorCallback.trace_id == trace_id)
    record = record_query.order_by(desc(models.PlannerExecutorCallback.created_at)).first()
    if record:
        record.signature = signature
        record.status = payload.get("status", "unknown")
        record.payload = payload
    else:
        record = models.PlannerExecutorCallback(
            scenario_id=scenario_id,
            callback_url=settings.executor_callback_url,
            signature=signature,
            status=payload.get("status", "unknown"),
            payload=payload,
            trace_id=trace_id or "",
        )
        db.add(record)

    audit_service.log_audit_event(
        db,
        target_type="scenario",
        target_id=scenario_id,
        action="executor_callback",
        actor_id="executor",
        payload={"payload": payload},
        trace_id=trace_id,
    )

    notification_service.dispatch_event(
        "SCENARIO_EXPORT_CALLBACK",
        {"scenario_id": scenario_id, "status": payload.get("status"), "payload": payload},
        trace_id=trace_id,
    )

    db.commit()
    return {"status": "accepted"}
