from __future__ import annotations

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ...config import settings
from ...database import get_db
from .. import models, schemas
from ..services import material_service
from ..services.yida_sync import (
    ProcessSyncService,
    YidaConfig,
    YidaFormClient,
    run_material_sync_job,
)
from openpyxl import Workbook

router = APIRouter(prefix="/base-config", tags=["base-config"])


class YidaMaterialSyncRequest(BaseModel):
    requested_by: str = Field("system", max_length=64)
    limit: Optional[int] = Field(None, gt=0, le=5000)
    dry_run: bool = False
    config_path: Optional[str] = None
    dump_path: Optional[str] = None


class YidaProcessSyncRequest(BaseModel):
    limit: Optional[int] = Field(None, gt=0, le=5000)
    dry_run: bool = False
    config_path: Optional[str] = None
    dump_path: Optional[str] = None


@router.post(
    "/materials/sync-yida",
    response_model=schemas.MaterialSyncJobRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def sync_yida_materials(
    payload: YidaMaterialSyncRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> schemas.MaterialSyncJobRead:
    config_path = Path(payload.config_path or settings.yida_materials_config_path)
    if not config_path.exists():
        raise HTTPException(status_code=400, detail=f"YiDa config not found: {config_path}")

    job = models.MaterialSyncJob(
        job_type="materials",
        config_path=str(config_path),
        requested_by=payload.requested_by,
        status="pending",
        limit=payload.limit,
        dry_run=payload.dry_run,
        dump_path=payload.dump_path,
        payload={"dump_path": payload.dump_path} if payload.dump_path else {},
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    background_tasks.add_task(run_material_sync_job, job.id)
    return schemas.MaterialSyncJobRead.from_orm(job)


@router.get(
    "/materials/sync-jobs/{job_id}",
    response_model=schemas.MaterialSyncJobRead,
)
def get_material_sync_job(job_id: str, db: Session = Depends(get_db)) -> schemas.MaterialSyncJobRead:
    job = db.get(models.MaterialSyncJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Material sync job not found")
    return schemas.MaterialSyncJobRead.from_orm(job)


@router.get(
    "/materials/sync-jobs",
    response_model=schemas.PaginatedMaterialSyncJobResponse,
)
def list_material_sync_jobs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
) -> schemas.PaginatedMaterialSyncJobResponse:
    query = db.query(models.MaterialSyncJob).order_by(models.MaterialSyncJob.created_at.desc())
    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return schemas.PaginatedMaterialSyncJobResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=[schemas.MaterialSyncJobRead.from_orm(job) for job in items],
    )


@router.post(
    "/processes/sync-yida",
    response_model=schemas.ProcessSyncResponse,
)
def sync_yida_processes(
    payload: YidaProcessSyncRequest,
    db: Session = Depends(get_db),
) -> schemas.ProcessSyncResponse:
    config_path = Path(payload.config_path or settings.yida_processes_config_path)
    if not config_path.exists():
        raise HTTPException(status_code=400, detail=f"YiDa config not found: {config_path}")

    config = YidaConfig.from_file(config_path)
    client = YidaFormClient(config)
    service = ProcessSyncService(db, client)
    dump_path = Path(payload.dump_path) if payload.dump_path else None
    result = service.sync_processes(limit=payload.limit, dry_run=payload.dry_run, dump_path=dump_path)
    return schemas.ProcessSyncResponse.from_result(result)


@router.get(
    "/materials",
    response_model=schemas.PaginatedMaterialResponse,
)
def list_materials(
    search: Optional[str] = Query(None, max_length=128),
    material_type: Optional[str] = None,
    category: Optional[str] = None,
    status: Optional[str] = None,
    is_active: Optional[bool] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
) -> schemas.PaginatedMaterialResponse:
    filters = material_service.MaterialFilters(
        search=search,
        material_type=material_type,
        category=category,
        status=status,
        is_active=is_active,
    )
    total, items = material_service.list_materials(db, filters=filters, page=page, page_size=page_size)
    return schemas.PaginatedMaterialResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=[schemas.MaterialRead.from_orm(item) for item in items],
    )


@router.patch(
    "/materials/{material_id}",
    response_model=schemas.MaterialRead,
)
def update_material(
    material_id: str,
    payload: schemas.MaterialUpdateRequest,
    db: Session = Depends(get_db),
) -> schemas.MaterialRead:
    material = db.get(models.Material, material_id)
    if not material or material.is_archived:
        raise HTTPException(status_code=404, detail="Material not found")
    if payload.is_active is not None:
        material.is_active = payload.is_active
    if payload.status is not None:
        material.status = payload.status
    db.commit()
    db.refresh(material)
    return schemas.MaterialRead.from_orm(material)


def _serialize_material_row(material: models.Material) -> list[str]:
    return [
        material.material_code,
        material.material_name,
        material.material_type,
        material.category or "",
        material.unit or "",
        str(material.unit_price),
        material.currency,
        "active" if material.is_active else "inactive",
        material.status,
        material.supplier_name or "",
    ]


def _build_csv_response(materials):
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        ["Code", "Name", "Type", "Category", "Unit", "Unit Price", "Currency", "Active", "Status", "Supplier"]
    )
    for material in materials:
        writer.writerow(_serialize_material_row(material))
    output = buffer.getvalue().encode("utf-8-sig")
    filename = f"materials_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}.csv"
    return StreamingResponse(
        io.BytesIO(output),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _build_xlsx_response(materials):
    wb = Workbook()
    ws = wb.active
    ws.append(["Code", "Name", "Type", "Category", "Unit", "Unit Price", "Currency", "Active", "Status", "Supplier"])
    for material in materials:
        ws.append(_serialize_material_row(material))
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    filename = f"materials_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post(
    "/materials/export",
    response_class=StreamingResponse,
)
def export_materials(
    payload: schemas.MaterialExportRequest,
    db: Session = Depends(get_db),
):
    filters = material_service.MaterialFilters(
        search=payload.search,
        material_type=payload.material_type,
        category=payload.category,
        status=payload.status,
        is_active=payload.is_active,
    )
    materials = material_service.fetch_materials_for_export(db, filters=filters)
    if payload.format == "xlsx":
        return _build_xlsx_response(materials)
    return _build_csv_response(materials)

