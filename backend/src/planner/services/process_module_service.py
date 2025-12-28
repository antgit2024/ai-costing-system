from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import asc, func, or_
from sqlalchemy.orm import Session

from .. import models
from ..utils.unit_normalizer import normalize_unit


class ProcessModuleFilters:
    def __init__(
        self,
        *,
        search: Optional[str] = None,
        status: Optional[str] = None,
        category: Optional[str] = None,
    ):
        self.search = search
        self.status = status
        self.category = category


def list_modules(
    db: Session,
    *,
    filters: ProcessModuleFilters,
    page: int,
    page_size: int,
) -> Tuple[int, Sequence[models.ProcessModule]]:
    query = db.query(models.ProcessModule).filter(models.ProcessModule.is_archived.is_(False))
    if filters.search:
        pattern = f"%{filters.search.strip()}%"
        query = query.filter(
            or_(
                models.ProcessModule.module_code.ilike(pattern),
                models.ProcessModule.module_name.ilike(pattern),
            )
        )
    if filters.status:
        query = query.filter(models.ProcessModule.status == filters.status)
    if filters.category:
        query = query.filter(func.trim(models.ProcessModule.category) == filters.category.strip())
    total = query.count()
    items = (
        query.order_by(models.ProcessModule.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return total, items


def get_module(db: Session, module_id: str) -> Optional[models.ProcessModule]:
    return (
        db.query(models.ProcessModule)
        .filter(models.ProcessModule.id == module_id, models.ProcessModule.is_archived.is_(False))
        .one_or_none()
    )


def create_module(
    db: Session,
    *,
    module_code: str,
    module_name: str,
    description: Optional[str],
    category: Optional[str],
    status: Optional[str],
    tags: Optional[List[str]],
    metadata: Optional[Dict[str, Any]],
    materials: Optional[List[Dict[str, Any]]] = None,
    steps: Optional[List[Dict[str, Any]]] = None,
) -> models.ProcessModule:
    module = models.ProcessModule(
        module_code=module_code,
        module_name=module_name,
        description=description,
        category=category,
        status=status or "draft",
        tags=tags or [],
        metadata_json=metadata or {},
    )
    db.add(module)
    db.flush()
    if materials is not None:
        _replace_materials(db, module, materials)
    if steps is not None:
        _replace_steps(db, module, steps)
    db.commit()
    db.refresh(module)
    return module


def update_module(
    db: Session,
    module: models.ProcessModule,
    *,
    module_name: Optional[str],
    description: Optional[str],
    category: Optional[str],
    status: Optional[str],
    tags: Optional[List[str]],
    metadata: Optional[Dict[str, Any]],
    materials: Optional[List[Dict[str, Any]]] = None,
    steps: Optional[List[Dict[str, Any]]] = None,
) -> models.ProcessModule:
    if module_name is not None:
        module.module_name = module_name
    if description is not None:
        module.description = description
    if category is not None:
        module.category = category
    if status is not None:
        module.status = status
    if tags is not None:
        module.tags = tags
    if metadata is not None:
        module.metadata_json = metadata
    if materials is not None:
        _replace_materials(db, module, materials)
    if steps is not None:
        _replace_steps(db, module, steps)
    db.commit()
    db.refresh(module)
    return module


def set_module_status(db: Session, module: models.ProcessModule, status: str) -> models.ProcessModule:
    # 启用口径：真正的“工艺模块”必须同时具备【至少 1 条物料】+【至少 1 条工序步骤】。
    # 草稿/停用允许不完整；但启用时必须完整，避免模型引用到空模块造成核算/生产链路异常。
    if status == "active":
        materials_count = (
            db.query(models.ProcessModuleMaterial)
            .filter(
                models.ProcessModuleMaterial.module_id == module.id,
                models.ProcessModuleMaterial.is_archived.is_(False),
            )
            .count()
        )
        steps_count = (
            db.query(models.ProcessModuleStep)
            .filter(
                models.ProcessModuleStep.module_id == module.id,
                models.ProcessModuleStep.is_archived.is_(False),
            )
            .count()
        )
        if materials_count <= 0 or steps_count <= 0:
            raise ValueError("启用失败：工艺模块必须同时包含至少1条物料和至少1条工序步骤")
    module.status = status
    db.commit()
    db.refresh(module)
    return module


def copy_module(
    db: Session,
    module: models.ProcessModule,
    *,
    module_code: str,
    module_name: str,
    status: Optional[str],
) -> models.ProcessModule:
    new_module = models.ProcessModule(
        module_code=module_code,
        module_name=module_name,
        description=module.description,
        category=module.category,
        status=status or module.status,
        version=module.version + 1,
        tags=list(module.tags or []),
        metadata_json=dict(module.metadata_json or {}),
    )
    db.add(new_module)
    db.flush()

    materials = [
        {
            "material_kind": material.material_kind,
            "material_ref_id": material.material_ref_id,
            "material_code": material.material_code,
            "material_name": material.material_name,
            "unit_of_measure": material.unit_of_measure,
            "calculation_method": material.calculation_method,
            "quantity": material.quantity,
            "loss_rate": material.loss_rate,
            "sequence_order": material.sequence_order,
            "material_category": material.material_category,
            "selection_notes": material.selection_notes,
            "loss_notes": material.loss_notes,
            "metadata_json": dict(material.metadata_json or {}),
        }
        for material in list_materials(db, module.id)
    ]
    steps = [
        {
            "sequence_order": step.sequence_order,
            "team_name": step.team_name,
            "pricing_method": step.pricing_method,
            "work_minutes": step.work_minutes,
            "unit_of_measure": step.unit_of_measure,
            "description": step.description,
            "notes": step.notes,
            "metadata_json": dict(step.metadata_json or {}),
        }
        for step in list_steps(db, module.id)
    ]
    _replace_materials(db, new_module, materials)
    _replace_steps(db, new_module, steps)
    db.commit()
    db.refresh(new_module)
    return new_module


def list_reference_modules(
    db: Session,
    *,
    module_ids: Optional[List[str]] = None,
    search: Optional[str] = None,
    status: Optional[str] = None,
) -> Sequence[models.ProcessModule]:
    query = db.query(models.ProcessModule).filter(models.ProcessModule.is_archived.is_(False))
    if module_ids:
        query = query.filter(models.ProcessModule.id.in_(module_ids))
    if search:
        pattern = f"%{search.strip()}%"
        query = query.filter(
            or_(
                models.ProcessModule.module_code.ilike(pattern),
                models.ProcessModule.module_name.ilike(pattern),
            )
        )
    if status:
        query = query.filter(models.ProcessModule.status == status)
    return query.order_by(asc(models.ProcessModule.module_name)).all()


def archive_module(db: Session, module: models.ProcessModule) -> None:
    """
    Archive (soft-delete) a process module.

    Safety rules:
    - Must be inactive (status != active)
    - Must not be referenced by:
      - model_process_modules.module_id (active bindings)
    """
    if module.status == "active":
        raise ValueError("请先停用该工艺模块后再删除")

    ref_cnt = (
        db.query(models.ModelProcessModule)
        .filter(
            models.ModelProcessModule.module_id == module.id,
            models.ModelProcessModule.is_archived.is_(False),
        )
        .count()
    )
    if ref_cnt:
        raise ValueError(f"该工艺模块仍被模型引用，无法删除：引用={ref_cnt}")

    module.is_archived = True

    # best-effort: archive child rows too (even though module is already hidden)
    db.query(models.ProcessModuleMaterial).filter(
        models.ProcessModuleMaterial.module_id == module.id,
        models.ProcessModuleMaterial.is_archived.is_(False),
    ).update({"is_archived": True})
    db.query(models.ProcessModuleStep).filter(
        models.ProcessModuleStep.module_id == module.id,
        models.ProcessModuleStep.is_archived.is_(False),
    ).update({"is_archived": True})


def serialize_module_payload(
    db: Session,
    module: models.ProcessModule,
) -> Dict[str, Any]:
    materials = [
        {
            "id": material.id,
            "material_kind": material.material_kind,
            "material_ref_id": material.material_ref_id,
            "material_code": material.material_code,
            "material_name": material.material_name,
            "unit_of_measure": material.unit_of_measure,
            "calculation_method": material.calculation_method,
            "quantity": Decimal(str(material.quantity)),
            "loss_rate": Decimal(str(material.loss_rate)),
            "sequence_order": material.sequence_order,
            "material_category": material.material_category,
            "selection_notes": material.selection_notes,
            "loss_notes": material.loss_notes,
            "metadata_json": material.metadata_json or {},
        }
        for material in list_materials(db, module.id)
    ]
    steps = [
        {
            "id": step.id,
            "sequence_order": step.sequence_order,
            "process_id": step.process_id,
            "team_name": step.team_name,
            "pricing_method": step.pricing_method,
            "work_minutes": Decimal(str(step.work_minutes)),
            "unit_of_measure": step.unit_of_measure,
            "description": step.description,
            "notes": step.notes,
            "metadata_json": step.metadata_json or {},
            "process": _serialize_process_reference(step.process),
        }
        for step in list_steps(db, module.id)
    ]
    return {
        "id": module.id,
        "module_code": module.module_code,
        "module_name": module.module_name,
        "description": module.description,
        "category": module.category,
        "status": module.status,
        "version": module.version,
        "tags": module.tags or [],
        "metadata_json": module.metadata_json or {},
        "created_at": module.created_at,
        "updated_at": module.updated_at,
        "materials": materials,
        "steps": steps,
    }


def _serialize_process_reference(process: Optional[models.Process]) -> Optional[Dict[str, Any]]:
    if not process:
        return None
    return {
        "id": process.id,
        "process_code": process.process_code,
        "process_name": process.process_name,
        "description": process.description,
        "charging_mode": process.charging_mode,
        "standard_rate": Decimal(str(process.standard_rate))
        if process.standard_rate is not None
        else None,
        "unit_of_measure": process.unit_of_measure,
        "team_name": process.team_name,
        "category": process.category,
    }


def list_materials(db: Session, module_id: str) -> Sequence[models.ProcessModuleMaterial]:
    return (
        db.query(models.ProcessModuleMaterial)
        .filter(
            models.ProcessModuleMaterial.module_id == module_id,
            models.ProcessModuleMaterial.is_archived.is_(False),
        )
        .order_by(
            asc(models.ProcessModuleMaterial.sequence_order),
            asc(models.ProcessModuleMaterial.created_at),
        )
        .all()
    )


def list_steps(db: Session, module_id: str) -> Sequence[models.ProcessModuleStep]:
    return (
        db.query(models.ProcessModuleStep)
        .filter(
            models.ProcessModuleStep.module_id == module_id,
            models.ProcessModuleStep.is_archived.is_(False),
        )
        .order_by(
            asc(models.ProcessModuleStep.sequence_order),
            asc(models.ProcessModuleStep.created_at),
        )
        .all()
    )


def _replace_materials(db: Session, module: models.ProcessModule, materials: List[Dict[str, Any]]) -> None:
    db.query(models.ProcessModuleMaterial).filter(
        models.ProcessModuleMaterial.module_id == module.id
    ).delete(synchronize_session=False)
    for index, payload in enumerate(materials):
        _create_material(db, module, payload, fallback_order=index)


def _replace_steps(db: Session, module: models.ProcessModule, steps: List[Dict[str, Any]]) -> None:
    db.query(models.ProcessModuleStep).filter(
        models.ProcessModuleStep.module_id == module.id
    ).delete(synchronize_session=False)
    for index, payload in enumerate(steps):
        _create_step(db, module, payload, fallback_order=index)


def _create_material(
    db: Session,
    module: models.ProcessModule,
    payload: Dict[str, Any],
    *,
    fallback_order: int,
) -> models.ProcessModuleMaterial:
    material_kind = (payload.get("material_kind") or "real").lower()
    material_ref_id = payload.get("material_ref_id")
    material_code = payload.get("material_code")
    material_name = payload.get("material_name")

    if material_kind not in {"real", "virtual", "bom"}:
        raise ValueError("material_kind must be real, virtual or bom")
    if material_kind in {"real", "bom", "virtual"} and not material_ref_id:
        raise ValueError("material_ref_id is required for referenced materials")

    if material_kind == "real" or material_kind == "bom":
        reference = (
            db.query(models.Material)
            .filter(models.Material.id == material_ref_id, models.Material.is_archived.is_(False))
            .one_or_none()
        )
        if not reference:
            raise ValueError("Referenced material not found")
        if not reference.is_active:
            raise ValueError("Referenced material is inactive")
        if material_kind == "bom" and not reference.is_bom_material:
            raise ValueError("Referenced material is not flagged as BOM-maintained")
        material_code = material_code or reference.material_code
        material_name = material_name or reference.material_name
    elif material_kind == "virtual":
        reference = (
            db.query(models.VirtualMaterial)
            .filter(models.VirtualMaterial.id == material_ref_id, models.VirtualMaterial.is_archived.is_(False))
            .one_or_none()
        )
        if not reference:
            raise ValueError("Referenced virtual material not found")
        material_code = material_code or reference.virtual_code
        material_name = material_name or reference.name

    quantity = Decimal(str(payload.get("quantity", "0")))
    if quantity <= 0:
        raise ValueError("quantity must be greater than zero")
    loss_rate = Decimal(str(payload.get("loss_rate", "0")))
    if loss_rate < 0 or loss_rate > 100:
        raise ValueError("loss_rate must be between 0 and 100")

    sequence_order = payload.get("sequence_order")
    if sequence_order is None:
        sequence_order = fallback_order

    model = models.ProcessModuleMaterial(
        module_id=module.id,
        material_kind=material_kind,
        material_ref_id=material_ref_id,
        material_code=material_code,
        material_name=material_name,
        unit_of_measure=normalize_unit(payload.get("unit_of_measure")),
        calculation_method=payload.get("calculation_method") or "count",
        quantity=quantity,
        loss_rate=loss_rate,
        sequence_order=sequence_order,
        material_category=payload.get("material_category"),
        selection_notes=payload.get("selection_notes"),
        loss_notes=payload.get("loss_notes"),
        metadata_json=payload.get("metadata_json") or {},
    )
    db.add(model)
    return model


def _create_step(
    db: Session,
    module: models.ProcessModule,
    payload: Dict[str, Any],
    *,
    fallback_order: int,
) -> models.ProcessModuleStep:
    process_id = payload.get("process_id")
    process_ref: Optional[models.Process] = None
    if process_id:
        process_ref = (
            db.query(models.Process)
            .filter(models.Process.id == process_id, models.Process.is_archived.is_(False))
            .one_or_none()
        )
        if not process_ref:
            raise ValueError("Referenced process not found")
        if not process_ref.is_active:
            raise ValueError("Referenced process is inactive")

    sequence_order = payload.get("sequence_order")
    if sequence_order is None:
        sequence_order = fallback_order

    provided_work = payload.get("work_minutes")
    work_minutes = Decimal(str(provided_work if provided_work is not None else "0"))
    if work_minutes < 0:
        raise ValueError("work_minutes must be greater than or equal to zero")

    default_unit = process_ref.unit_of_measure if process_ref else None
    default_team = process_ref.team_name if process_ref else None
    default_pricing = process_ref.charging_mode if process_ref else None
    default_minutes = (
        Decimal(str(process_ref.standard_rate)) if process_ref and process_ref.standard_rate is not None else None
    )

    metadata = payload.get("metadata_json") or {}
    if process_ref:
        metadata = dict(metadata)
        metadata["process_snapshot"] = {
            "process_id": process_ref.id,
            "process_code": process_ref.process_code,
            "process_name": process_ref.process_name,
            "description": process_ref.description,
            "charging_mode": process_ref.charging_mode,
            "standard_rate": float(process_ref.standard_rate) if process_ref.standard_rate is not None else None,
            "unit_of_measure": process_ref.unit_of_measure,
        }

    model = models.ProcessModuleStep(
        module_id=module.id,
        process_id=process_ref.id if process_ref else None,
        sequence_order=sequence_order,
        team_name=payload.get("team_name") or default_team,
        pricing_method=payload.get("pricing_method") or default_pricing or "count",
        work_minutes=work_minutes if provided_work is not None else (default_minutes or Decimal("0")),
        unit_of_measure=normalize_unit(payload.get("unit_of_measure") or default_unit),
        description=payload.get("description"),
        notes=payload.get("notes"),
        metadata_json=metadata,
    )
    db.add(model)
    return model

