from __future__ import annotations

import uuid
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
        payload=payload or {},
        trace_id=trace_id or str(uuid.uuid4()),
    )
    db.add(record)
    return record
