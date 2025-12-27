from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ...database import get_db
from .. import models, schemas
from ..services import audit_service, process_service

router = APIRouter(prefix="/processes", tags=["processes"])


def _get_process_or_404(process_id: str, db: Session):
    process = process_service.get_process(db, process_id)
    if not process:
        raise HTTPException(status_code=404, detail="Process not found")
    return process


def _serialize(process) -> schemas.ProcessDetailRead:
    return schemas.ProcessDetailRead.from_orm(process)


@router.get("", response_model=schemas.PaginatedProcessResponse)
def list_processes(
    search: Optional[str] = Query(None, max_length=128),
    status_filter: Optional[str] = Query(None, alias="status", max_length=32),
    charging_mode: Optional[str] = Query(None, max_length=32),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
):
    filters = process_service.ProcessFilters(
        search=search,
        status=status_filter,
        charging_mode=charging_mode,
    )
    total, items = process_service.list_processes(db, filters=filters, page=page, page_size=page_size)
    return schemas.PaginatedProcessResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=[schemas.ProcessSummaryRead.from_orm(item) for item in items],
    )


@router.post(
    "",
    response_model=schemas.ProcessDetailRead,
    status_code=status.HTTP_201_CREATED,
)
def create_process(payload: schemas.ProcessCreateRequest, db: Session = Depends(get_db)):
    try:
        process = process_service.create_process(
            db,
            process_code=payload.process_code,
            process_name=payload.process_name,
            description=payload.description,
            category=payload.category,
            team_name=payload.team_name,
            charging_mode=payload.charging_mode,
            standard_rate=payload.standard_rate,
            unit_of_measure=payload.unit_of_measure,
            status=payload.status,
            metadata=payload.metadata,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    audit_service.log_audit_event(
        db,
        target_type="process",
        target_id=process.id,
        action="create",
        actor_id=payload.operator_id or "system",
        payload={"process_code": process.process_code},
    )
    db.commit()
    return _serialize(process)


@router.get(
    "/references",
    response_model=List[schemas.ProcessReferenceRead],
)
def list_process_references(
    search: Optional[str] = Query(None, max_length=128),
    status_filter: Optional[str] = Query("active", alias="status"),
    charging_mode: Optional[str] = Query(None, max_length=32),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    filters = process_service.ProcessFilters(
        search=search,
        status=status_filter,
        charging_mode=charging_mode,
    )
    total, items = process_service.list_processes(db, filters=filters, page=1, page_size=limit)
    references = [
        schemas.ProcessReferenceRead(
            id=item.id,
            process_code=item.process_code,
            process_name=item.process_name,
            charging_mode=item.charging_mode,
            standard_rate=item.standard_rate,
            unit_of_measure=item.unit_of_measure,
            team_name=item.team_name,
            category=item.category,
        )
        for item in items
    ]
    return references


@router.get(
    "/{process_id}",
    response_model=schemas.ProcessDetailRead,
)
def get_process(process_id: str, db: Session = Depends(get_db)):
    process = _get_process_or_404(process_id, db)
    return _serialize(process)


@router.patch(
    "/{process_id}",
    response_model=schemas.ProcessDetailRead,
)
def update_process(
    process_id: str,
    payload: schemas.ProcessUpdateRequest,
    db: Session = Depends(get_db),
):
    process = _get_process_or_404(process_id, db)
    try:
        process = process_service.update_process(
            db,
            process,
            process_name=payload.process_name,
            description=payload.description,
            category=payload.category,
            team_name=payload.team_name,
            charging_mode=payload.charging_mode,
            standard_rate=payload.standard_rate,
            unit_of_measure=payload.unit_of_measure,
            status=payload.status,
            metadata=payload.metadata,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    audit_service.log_audit_event(
        db,
        target_type="process",
        target_id=process.id,
        action="update",
        actor_id=payload.operator_id or "system",
        payload={"process_code": process.process_code},
    )
    db.commit()
    return _serialize(process)


@router.post(
    "/{process_id}/activate",
    response_model=schemas.ProcessDetailRead,
)
def activate_process(process_id: str, db: Session = Depends(get_db)):
    process = _get_process_or_404(process_id, db)
    process = process_service.set_process_status(db, process, status="active")
    audit_service.log_audit_event(
        db,
        target_type="process",
        target_id=process.id,
        action="activate",
        actor_id="system",
        payload={"process_code": process.process_code},
    )
    db.commit()
    return _serialize(process)


@router.post(
    "/{process_id}/deactivate",
    response_model=schemas.ProcessDetailRead,
)
def deactivate_process(process_id: str, db: Session = Depends(get_db)):
    process = _get_process_or_404(process_id, db)
    process = process_service.set_process_status(db, process, status="inactive")
    audit_service.log_audit_event(
        db,
        target_type="process",
        target_id=process.id,
        action="deactivate",
        actor_id="system",
        payload={"process_code": process.process_code},
    )
    db.commit()
    return _serialize(process)


@router.post(
    "/{process_id}/copy",
    response_model=schemas.ProcessDetailRead,
)
def copy_process(
    process_id: str,
    payload: schemas.ProcessCopyRequest,
    db: Session = Depends(get_db),
):
    process = _get_process_or_404(process_id, db)
    try:
        new_process = process_service.copy_process(
            db,
            process,
            process_code=payload.process_code,
            process_name=payload.process_name,
            status=payload.status or process.status,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    audit_service.log_audit_event(
        db,
        target_type="process",
        target_id=new_process.id,
        action="copy",
        actor_id=payload.operator_id or "system",
        payload={"source_process_id": process.id, "process_code": new_process.process_code},
    )
    db.commit()
    return _serialize(new_process)


@router.post(
    "/batch/status",
    response_model=schemas.ProcessBatchStatusResponse,
)
def batch_update_status(payload: schemas.ProcessBatchStatusRequest, db: Session = Depends(get_db)):
    updated = process_service.set_process_status_bulk(db, ids=payload.ids, status=payload.status)
    if updated:
        audit_service.log_audit_event(
            db,
            target_type="process_batch",
            target_id="batch",
            action="batch_status",
            actor_id=payload.operator_id or "system",
            payload={"ids": payload.ids, "status": payload.status},
        )
    db.commit()
    return schemas.ProcessBatchStatusResponse(updated=updated)


@router.delete(
    "/{process_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def archive_process(process_id: str, db: Session = Depends(get_db)):
    """
    Archive (soft-delete) a process.

    Safety rules:
    - Must be inactive (status != active)
    - Must not be referenced by:
      - process_module_steps.process_id (active steps)
      - model_processes.process_id
      - model_version_processes.process_id
    """
    process = _get_process_or_404(process_id, db)
    if process.status == "active":
        raise HTTPException(status_code=400, detail="请先停用该工序后再删除")

    step_ref_cnt = (
        db.query(models.ProcessModuleStep)
        .filter(
            models.ProcessModuleStep.process_id == process.id,
            models.ProcessModuleStep.is_archived.is_(False),
        )
        .count()
    )
    model_ref_cnt = (
        db.query(models.ModelProcess)
        .filter(models.ModelProcess.process_id == process.id, models.ModelProcess.is_archived.is_(False))
        .count()
    )
    version_ref_cnt = (
        db.query(models.ModelVersionProcess)
        .filter(
            models.ModelVersionProcess.process_id == process.id,
            models.ModelVersionProcess.is_archived.is_(False),
        )
        .count()
    )
    if step_ref_cnt or model_ref_cnt or version_ref_cnt:
        raise HTTPException(
            status_code=400,
            detail=f"该工序仍被引用，无法删除：工艺模块步骤引用={step_ref_cnt}，模型引用={model_ref_cnt}，版本引用={version_ref_cnt}",
        )

    process.is_archived = True
    audit_service.log_audit_event(
        db,
        target_type="process",
        target_id=process.id,
        action="archive",
        actor_id="system",
        payload={"process_code": process.process_code},
    )
    db.commit()
    return None

