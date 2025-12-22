from __future__ import annotations

from __future__ import annotations

import csv
import io
import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ...config import settings
from ...database import get_db
from .. import models, schemas
from ..services import material_service
from ..services import material_image_storage
from ..services.dingtalk_client import get_dingtalk_client
from ..services.yida_sync import (
    ProcessSyncService,
    YidaConfig,
    YidaFormClient,
    run_material_sync_job,
)
from openpyxl import Workbook

router = APIRouter(prefix="/base-config", tags=["base-config"])
logger = logging.getLogger(__name__)


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
    is_bom_material: Optional[bool] = None,
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
        is_bom_material=is_bom_material,
        is_active=is_active,
    )
    total, items = material_service.list_materials(db, filters=filters, page=page, page_size=page_size)
    return schemas.PaginatedMaterialResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=[schemas.MaterialRead.from_orm(item) for item in items],
    )


@router.get(
    "/materials/{material_id}",
    response_model=schemas.MaterialRead,
)
def get_material(material_id: str, db: Session = Depends(get_db)) -> schemas.MaterialRead:
    material = db.get(models.Material, material_id)
    if not material or material.is_archived:
        raise HTTPException(status_code=404, detail="Material not found")
    return schemas.MaterialRead.from_orm(material)


@router.get(
    "/materials/{material_id}/images/{image_index}",
    response_class=StreamingResponse,
)
def download_material_image(
    material_id: str,
    image_index: int,
    size: Optional[int] = Query(None, ge=32, le=512),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """
    Image proxy for materials.

    Order:
    1) Serve from metadata_json.local_images if present and file exists
    2) Otherwise download from DingTalk using metadata_json.images (ossFileHandle) and persist locally (best-effort)
    """
    material = db.get(models.Material, material_id)
    if not material or material.is_archived:
        raise HTTPException(status_code=404, detail="Material not found")
    metadata = dict(material.metadata_json or {})
    image_sources = metadata.get("images") or []
    if not isinstance(image_sources, list):
        image_sources = []
    if image_index < 0 or image_index >= len(image_sources):
        raise HTTPException(status_code=404, detail="Image not found")

    # 1) local
    local_ref = material_image_storage.get_local_image_ref(metadata, image_index)
    if local_ref is not None:
        try:
            content = material_image_storage.read_local_bytes(local_ref)
            media_type = local_ref.content_type or "application/octet-stream"
            # NOTE: we currently ignore thumbnail resize (no Pillow dependency); return original.
            return StreamingResponse(io.BytesIO(content), media_type=media_type)
        except FileNotFoundError:
            # fallthrough to dingtalk download
            pass
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to read local material image (material=%s idx=%s): %s", material_id, image_index, exc)

    # 2) DingTalk download
    try:
        client = get_dingtalk_client()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    try:
        attachment = client.download_attachment(str(image_sources[image_index]))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"DingTalk download failed: {exc}") from exc

    content_type = attachment.headers.get("Content-Type")

    # Best-effort: persist locally so future loads don't depend on DingTalk.
    if settings.planner_persist_material_images:
        try:
            ref = material_image_storage.persist_bytes(
                material_id=material_id,
                image_index=image_index,
                source_url=str(image_sources[image_index]),
                content=attachment.content,
                content_type=content_type,
            )
            # Deep-copy to avoid SQLAlchemy JSON change-tracking pitfalls on nested mutables.
            metadata2 = json.loads(json.dumps(material.metadata_json or {}, ensure_ascii=False))
            material_image_storage.set_local_image_ref(metadata2, image_index, ref)
            material.metadata_json = metadata2
            db.commit()
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            logger.warning("Failed to persist material image locally (material=%s idx=%s): %s", material_id, image_index, exc)

    # Thumbnail resize not implemented; return original
    media_type = content_type or "application/octet-stream"
    return StreamingResponse(io.BytesIO(attachment.content), media_type=media_type)


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
    if payload.is_bom_material is not None:
        material.is_bom_material = payload.is_bom_material
    if payload.unit is not None:
        material.unit = payload.unit
    if payload.inventory_unit is not None:
        material.inventory_unit = payload.inventory_unit
    if payload.calculation_method is not None:
        material.calculation_method = str(payload.calculation_method)
    if payload.conversion_purchase_to_bom is not None:
        material.conversion_purchase_to_bom = payload.conversion_purchase_to_bom
    if payload.conversion_bom_to_inventory is not None:
        material.conversion_bom_to_inventory = payload.conversion_bom_to_inventory

    metadata = dict(material.metadata_json or {})
    metadata_updated = False
    if payload.metadata is not None:
        for key, value in (payload.metadata or {}).items():
            if value is None:
                if key in metadata:
                    metadata.pop(key, None)
                    metadata_updated = True
            else:
                metadata[key] = value
                metadata_updated = True
    if payload.bom_unit_price is not None:
        # store as float in metadata for backward compatibility
        metadata["bom_unit_price"] = float(payload.bom_unit_price)
        metadata_updated = True
    if metadata_updated:
        material.metadata_json = metadata
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
        is_bom_material=payload.is_bom_material,
        is_active=payload.is_active,
    )
    materials = material_service.fetch_materials_for_export(db, filters=filters)
    if payload.format == "xlsx":
        return _build_xlsx_response(materials)
    return _build_csv_response(materials)


def _virtual_kind_of(vm: models.VirtualMaterial) -> str:
    meta = vm.metadata_json or {}
    kind = meta.get("virtual_kind")
    return str(kind or "kit")


def _virtual_read(db: Session, vm: models.VirtualMaterial) -> schemas.VirtualMaterialRead:
    # Build bindings
    binds = (
        db.query(models.VirtualMaterialBinding)
        .filter(models.VirtualMaterialBinding.virtual_material_id == vm.id)
        .order_by(models.VirtualMaterialBinding.created_at.asc())
        .all()
    )
    binding_reads: List[schemas.VirtualMaterialBindingRead] = []
    for b in binds:
        material = db.get(models.Material, b.material_id)
        if not material or material.is_archived:
            continue
        meta = b.metadata_json or {}
        binding_type = meta.get("binding_type") or "ratio"
        binding_reads.append(
            schemas.VirtualMaterialBindingRead(
                material_id=material.id,
                material_code=material.material_code,
                material_name=material.material_name,
                unit=material.unit,
                quantity_ratio=Decimal(str(b.quantity_ratio)),
                loss_rate=Decimal(str(b.loss_rate)),
                currency=material.currency,
                purchase_unit_price=None,
                purchase_unit=material.purchase_unit,
                bom_unit_price=None,
                bom_unit=material.unit,
                image_url=None,
                status=material.status,
                is_active=material.is_active,
                binding_type=str(binding_type),
            )
        )

    data: Dict[str, Any] = {
        "id": vm.id,
        "virtual_code": vm.virtual_code,
        "name": vm.name,
        "description": vm.description,
        "category": vm.category,
        "virtual_kind": _virtual_kind_of(vm),
        "unit": vm.unit,
        "status": vm.status,
        "version": vm.version,
        "notes": None,
        "metadata_json": vm.metadata_json or {},
        "created_at": vm.created_at,
        "updated_at": vm.updated_at,
        "bindings": binding_reads,
    }
    return schemas.VirtualMaterialRead.parse_obj(data)


@router.get(
    "/virtual-materials",
    response_model=schemas.PaginatedVirtualMaterialResponse,
)
def list_virtual_materials(
    search: Optional[str] = Query(None, max_length=128),
    status: Optional[str] = Query(None, max_length=32),
    category: Optional[str] = Query(None, max_length=128),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
) -> schemas.PaginatedVirtualMaterialResponse:
    query = db.query(models.VirtualMaterial).filter(models.VirtualMaterial.is_archived.is_(False))
    if search:
        like = f"%{search.strip()}%"
        query = query.filter(
            (models.VirtualMaterial.virtual_code.ilike(like)) | (models.VirtualMaterial.name.ilike(like))
        )
    if status:
        query = query.filter(models.VirtualMaterial.status == status)
    if category:
        query = query.filter(models.VirtualMaterial.category == category)
    total = query.count()
    items = (
        query.order_by(models.VirtualMaterial.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return schemas.PaginatedVirtualMaterialResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=[_virtual_read(db, vm) for vm in items],
    )


@router.get(
    "/virtual-materials/{virtual_material_id}",
    response_model=schemas.VirtualMaterialRead,
)
def get_virtual_material(
    virtual_material_id: str,
    db: Session = Depends(get_db),
) -> schemas.VirtualMaterialRead:
    vm = db.get(models.VirtualMaterial, virtual_material_id)
    if not vm or vm.is_archived:
        raise HTTPException(status_code=404, detail="Virtual material not found")
    return _virtual_read(db, vm)


@router.post(
    "/virtual-materials",
    response_model=schemas.VirtualMaterialRead,
    status_code=status.HTTP_201_CREATED,
)
def create_virtual_material(
    payload: schemas.VirtualMaterialCreateRequest,
    db: Session = Depends(get_db),
) -> schemas.VirtualMaterialRead:
    meta = dict(payload.metadata_json or {})
    meta["virtual_kind"] = payload.virtual_kind
    unit = payload.unit or ("套" if payload.virtual_kind == "kit" else None)
    vm = models.VirtualMaterial(
        virtual_code=payload.virtual_code,
        name=payload.name,
        description=payload.description,
        category=payload.category,
        unit=unit or "套",
        status=payload.status,
        version=1,
        metadata_json=meta,
    )
    db.add(vm)
    db.commit()
    db.refresh(vm)
    return _virtual_read(db, vm)


@router.patch(
    "/virtual-materials/{virtual_material_id}",
    response_model=schemas.VirtualMaterialRead,
)
def update_virtual_material(
    virtual_material_id: str,
    payload: schemas.VirtualMaterialUpdateRequest,
    db: Session = Depends(get_db),
) -> schemas.VirtualMaterialRead:
    vm = db.get(models.VirtualMaterial, virtual_material_id)
    if not vm or vm.is_archived:
        raise HTTPException(status_code=404, detail="Virtual material not found")
    if payload.name is not None:
        vm.name = payload.name
    if payload.description is not None:
        vm.description = payload.description
    if payload.category is not None:
        vm.category = payload.category
    if payload.status is not None:
        vm.status = payload.status
    meta = vm.metadata_json or {}
    if payload.metadata_json is not None:
        meta.update(payload.metadata_json or {})
    if payload.virtual_kind is not None:
        meta["virtual_kind"] = payload.virtual_kind
    if payload.unit is not None:
        vm.unit = payload.unit
    vm.metadata_json = meta
    db.commit()
    db.refresh(vm)
    return _virtual_read(db, vm)


@router.put(
    "/virtual-materials/{virtual_material_id}/bindings",
    response_model=schemas.VirtualMaterialRead,
)
def save_virtual_material_bindings(
    virtual_material_id: str,
    payload: schemas.VirtualMaterialBindingBatchRequest,
    db: Session = Depends(get_db),
) -> schemas.VirtualMaterialRead:
    vm = db.get(models.VirtualMaterial, virtual_material_id)
    if not vm or vm.is_archived:
        raise HTTPException(status_code=404, detail="Virtual material not found")
    kind = _virtual_kind_of(vm)
    if kind == "placeholder" and payload.bindings:
        raise HTTPException(status_code=400, detail="placeholder 虚拟物料不允许绑定子物料")

    # Replace-all: delete then insert
    db.query(models.VirtualMaterialBinding).filter(
        models.VirtualMaterialBinding.virtual_material_id == virtual_material_id
    ).delete()
    for b in payload.bindings:
        material = db.get(models.Material, b.material_id)
        if not material or material.is_archived:
            raise HTTPException(status_code=400, detail=f"Referenced material not found: {b.material_id}")
        db.add(
            models.VirtualMaterialBinding(
                virtual_material_id=virtual_material_id,
                material_id=material.id,
                material_type="real",
                material_ref_id=material.id,
                quantity_ratio=b.quantity_ratio,
                loss_rate=b.loss_rate,
                metadata_json={"binding_type": b.binding_type or "ratio"},
            )
        )
    db.commit()
    db.refresh(vm)
    return _virtual_read(db, vm)


@router.post(
    "/virtual-materials/{virtual_material_id}/deactivate",
    response_model=schemas.VirtualMaterialRead,
)
def deactivate_virtual_material(
    virtual_material_id: str,
    db: Session = Depends(get_db),
) -> schemas.VirtualMaterialRead:
    vm = db.get(models.VirtualMaterial, virtual_material_id)
    if not vm or vm.is_archived:
        raise HTTPException(status_code=404, detail="Virtual material not found")
    vm.is_archived = True
    db.commit()
    db.refresh(vm)
    return _virtual_read(db, vm)


@router.get(
    "/materials/{material_id}/virtual-links",
    response_model=List[schemas.VirtualMaterialReferenceRead],
)
def list_material_virtual_links(
    material_id: str,
    db: Session = Depends(get_db),
) -> List[schemas.VirtualMaterialReferenceRead]:
    rows = (
        db.query(models.VirtualMaterialBinding, models.VirtualMaterial)
        .join(models.VirtualMaterial, models.VirtualMaterial.id == models.VirtualMaterialBinding.virtual_material_id)
        .filter(models.VirtualMaterialBinding.material_id == material_id)
        .filter(models.VirtualMaterial.is_archived.is_(False))
        .order_by(models.VirtualMaterial.updated_at.desc())
        .all()
    )
    out: List[schemas.VirtualMaterialReferenceRead] = []
    for b, vm in rows:
        out.append(
            schemas.VirtualMaterialReferenceRead(
                virtual_material_id=vm.id,
                virtual_code=vm.virtual_code,
                virtual_name=vm.name,
                status=vm.status,
                quantity_ratio=Decimal(str(b.quantity_ratio)),
                loss_rate=Decimal(str(b.loss_rate)),
            )
        )
    return out


@router.post(
    "/virtual-materials/{virtual_material_id}/inventory-breakdown",
    response_model=schemas.VirtualMaterialInventoryResponse,
)
def inventory_breakdown_virtual_material(
    virtual_material_id: str,
    payload: schemas.VirtualMaterialInventoryRequest,
    db: Session = Depends(get_db),
) -> schemas.VirtualMaterialInventoryResponse:
    vm = db.get(models.VirtualMaterial, virtual_material_id)
    if not vm or vm.is_archived:
        raise HTTPException(status_code=404, detail="Virtual material not found")
    binds = (
        db.query(models.VirtualMaterialBinding)
        .filter(models.VirtualMaterialBinding.virtual_material_id == virtual_material_id)
        .order_by(models.VirtualMaterialBinding.created_at.asc())
        .all()
    )
    items: List[schemas.VirtualMaterialInventoryItem] = []
    req_qty = Decimal(str(payload.quantity))
    for b in binds:
        material = db.get(models.Material, b.material_id)
        if not material or material.is_archived:
            continue
        ratio = Decimal(str(b.quantity_ratio))
        loss = Decimal(str(b.loss_rate))
        required = req_qty * ratio * (Decimal("1") + (loss / Decimal("100")))
        items.append(
            schemas.VirtualMaterialInventoryItem(
                material_id=material.id,
                material_code=material.material_code,
                material_name=material.material_name,
                unit=material.unit,
                quantity_ratio=ratio,
                loss_rate=loss,
                required_quantity=required,
            )
        )
    return schemas.VirtualMaterialInventoryResponse(
        virtual_material_id=vm.id,
        virtual_code=vm.virtual_code,
        virtual_name=vm.name,
        requested_quantity=req_qty,
        calculation_method=payload.calculation_method,
        usage_context=payload.usage_context,
        items=items,
    )

