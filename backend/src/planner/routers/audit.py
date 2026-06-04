from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from .. import models, schemas
from ..dependencies import PaginationParams, get_db_session

router = APIRouter(tags=["Audit"])


@router.get("/audit", response_model=schemas.PaginatedAuditLogResponse)
def list_audit_logs(
    target_type: Optional[str] = Query(None),
    target_id: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    actor_id: Optional[str] = Query(None),
    trace_id: Optional[str] = Query(None),
    pagination: PaginationParams = Depends(),
    db: Session = Depends(get_db_session),
):
    query = db.query(models.AuditLog)

    if target_type:
        query = query.filter(models.AuditLog.target_type == target_type)
    if target_id:
        query = query.filter(models.AuditLog.target_id == target_id)
    if action:
        query = query.filter(models.AuditLog.action == action)
    if actor_id:
        query = query.filter(models.AuditLog.actor_id == actor_id)
    if trace_id:
        query = query.filter(models.AuditLog.trace_id == trace_id)

    total = query.count()
    items = (
        query.order_by(models.AuditLog.created_at.desc())
        .offset((pagination.page - 1) * pagination.page_size)
        .limit(pagination.page_size)
        .all()
    )

    return schemas.PaginatedAuditLogResponse(
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
        items=items,
    )









