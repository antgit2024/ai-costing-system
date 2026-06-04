from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from .. import models


def log_audit_event(
    db: Session,
    *,
    target_type: str,
    target_id: str,
    action: str,
    actor_id: str,
    payload: Dict[str, Any] | None = None,
    trace_id: Optional[str] = None,
) -> models.AuditLog:
    record = models.AuditLog(
        target_type=target_type,
        target_id=target_id,
        action=action,
        actor_id=actor_id,
        payload=_json_safe(payload or {}),
        trace_id=trace_id or str(uuid.uuid4()),
    )
    db.add(record)
    return record


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_safe(val) for key, val in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    return value
