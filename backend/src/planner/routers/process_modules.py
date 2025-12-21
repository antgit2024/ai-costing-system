from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ...database import get_db
from .. import schemas
from ..services import audit_service, process_module_service

router = APIRouter(prefix="/process-modules", tags=["process-modules"])


def _serialize_module(db: Session, module) -> schemas.ProcessModuleDetailRead:
    payload = process_module_service.serialize_module_payload(db, module)
    payload["materials"] = [
        schemas.ProcessModuleMaterialRead(**material) for material in payload["materials"]
    ]
    payload["steps"] = [schemas.ProcessModuleStepRead(**step) for step in payload["steps"]]
    return schemas.ProcessModuleDetailRead(**payload)


def _material_payload(items: List[schemas.ProcessModuleMaterialInput]) -> List[dict]:
    return [item.dict(by_alias=True) for item in items]


def _step_payload(items: List[schemas.ProcessModuleStepInput]) -> List[dict]:
    return [item.dict(by_alias=True) for item in items]


def _get_module_or_404(module_id: str, db: Session):
    module = process_module_service.get_module(db, module_id)
    if not module:
        raise HTTPException(status_code=404, detail="Process module not found")
    return module


@router.get(
    "",
    response_model=schemas.PaginatedProcessModuleResponse,
)
def list_process_modules(
    search: Optional[str] = Query(None, max_length=128),
    status_filter: Optional[str] = Query(None, alias="status", max_length=32),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
):
    filters = process_module_service.ProcessModuleFilters(search=search, status=status_filter)
    total, items = process_module_service.list_modules(
        db,
        filters=filters,
        page=page,
        page_size=page_size,
    )
    return schemas.PaginatedProcessModuleResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=[schemas.ProcessModuleSummaryRead.from_orm(item) for item in items],
    )


@router.post(
    "",
    response_model=schemas.ProcessModuleDetailRead,
    status_code=status.HTTP_201_CREATED,
)
def create_process_module(payload: schemas.ProcessModuleCreateRequest, db: Session = Depends(get_db)):
    try:
        module = process_module_service.create_module(
            db,
            module_code=payload.module_code,
            module_name=payload.module_name,
            description=payload.description,
            category=payload.category,
            status=payload.status,
            tags=payload.tags,
            metadata=payload.metadata,
            materials=_material_payload(payload.materials),
            steps=_step_payload(payload.steps),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    audit_service.log_audit_event(
        db,
        target_type="process_module",
        target_id=module.id,
        action="create",
        actor_id=payload.operator_id or "system",
        payload={"module_code": module.module_code},
    )
    db.commit()
    return _serialize_module(db, module)


@router.get(
    "/references",
    response_model=schemas.ProcessModuleReferenceResponse,
)
def list_process_module_references(
    module_ids: Optional[List[str]] = Query(None),
    search: Optional[str] = Query(None, max_length=128),
    status_filter: Optional[str] = Query("active", alias="status"),
    db: Session = Depends(get_db),
):
    modules = process_module_service.list_reference_modules(
        db, module_ids=module_ids, search=search, status=status_filter
    )
    serialized = [_serialize_module(db, module) for module in modules]
    return schemas.ProcessModuleReferenceResponse(total=len(serialized), items=serialized)


@router.get(
    "/{module_id}",
    response_model=schemas.ProcessModuleDetailRead,
)
def get_process_module(module_id: str, db: Session = Depends(get_db)):
    module = _get_module_or_404(module_id, db)
    return _serialize_module(db, module)


@router.get(
    "/{module_id}/preview",
    response_model=schemas.ProcessModuleDetailRead,
)
def preview_process_module(module_id: str, db: Session = Depends(get_db)):
    module = _get_module_or_404(module_id, db)
    return _serialize_module(db, module)


@router.patch(
    "/{module_id}",
    response_model=schemas.ProcessModuleDetailRead,
)
def update_process_module(
    module_id: str,
    payload: schemas.ProcessModuleUpdateRequest,
    db: Session = Depends(get_db),
):
    module = _get_module_or_404(module_id, db)
    try:
        module = process_module_service.update_module(
            db,
            module,
            module_name=payload.module_name,
            description=payload.description,
            category=payload.category,
            status=payload.status,
            tags=payload.tags,
            metadata=payload.metadata,
            materials=_material_payload(payload.materials) if payload.materials is not None else None,
            steps=_step_payload(payload.steps) if payload.steps is not None else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    audit_service.log_audit_event(
        db,
        target_type="process_module",
        target_id=module.id,
        action="update",
        actor_id=payload.operator_id or "system",
        payload={"module_code": module.module_code},
    )
    db.commit()
    return _serialize_module(db, module)


@router.post(
    "/{module_id}/activate",
    response_model=schemas.ProcessModuleDetailRead,
)
def activate_process_module(module_id: str, db: Session = Depends(get_db)):
    module = _get_module_or_404(module_id, db)
    module = process_module_service.set_module_status(db, module, "active")
    audit_service.log_audit_event(
        db,
        target_type="process_module",
        target_id=module.id,
        action="activate",
        actor_id="system",
        payload={"module_code": module.module_code},
    )
    db.commit()
    return _serialize_module(db, module)


@router.post(
    "/{module_id}/deactivate",
    response_model=schemas.ProcessModuleDetailRead,
)
def deactivate_process_module(module_id: str, db: Session = Depends(get_db)):
    module = _get_module_or_404(module_id, db)
    module = process_module_service.set_module_status(db, module, "inactive")
    audit_service.log_audit_event(
        db,
        target_type="process_module",
        target_id=module.id,
        action="deactivate",
        actor_id="system",
        payload={"module_code": module.module_code},
    )
    db.commit()
    return _serialize_module(db, module)


@router.post(
    "/{module_id}/copy",
    response_model=schemas.ProcessModuleDetailRead,
)
def copy_process_module(
    module_id: str,
    payload: schemas.ProcessModuleCopyRequest,
    db: Session = Depends(get_db),
):
    module = _get_module_or_404(module_id, db)
    try:
        new_module = process_module_service.copy_module(
            db,
            module,
            module_code=payload.module_code,
            module_name=payload.module_name,
            status=payload.status or module.status,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    audit_service.log_audit_event(
        db,
        target_type="process_module",
        target_id=new_module.id,
        action="copy",
        actor_id=payload.operator_id or "system",
        payload={"source_module_id": module.id, "module_code": new_module.module_code},
    )
    db.commit()
    return _serialize_module(db, new_module)

