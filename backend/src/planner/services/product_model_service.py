from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import asc, func, or_
from sqlalchemy.orm import Session

from .. import models
from . import variant_rule_service


def _json_safe(value: Any) -> Any:
    """
    Convert objects that are not JSON-serializable by default (e.g. Decimal) into safe values.
    Used before writing metadata_json into SQLAlchemy JSON columns.
    """
    if isinstance(value, Decimal):
        # Prefer string to preserve precision and match existing "Decimal-as-string" convention in metadata.
        return str(value)
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, tuple):
        return [_json_safe(v) for v in value]
    return value


class ProductModelFilters:
    def __init__(
        self,
        *,
        search: Optional[str] = None,
        status: Optional[str] = None,
        category: Optional[str] = None,
        include_archived: bool = False,
    ):
        self.search = search
        self.status = status
        self.category = category
        self.include_archived = include_archived


def list_models(
    db: Session, *, filters: ProductModelFilters, page: int, page_size: int
) -> Tuple[int, Sequence[models.ProductModel]]:
    query = db.query(models.ProductModel)
    if not getattr(filters, "include_archived", False):
        query = query.filter(models.ProductModel.is_archived.is_(False))
    if filters.search:
        pattern = f"%{filters.search.strip()}%"
        query = query.filter(
            or_(
                models.ProductModel.model_code.ilike(pattern),
                models.ProductModel.model_name.ilike(pattern),
            )
        )
    if filters.status:
        query = query.filter(models.ProductModel.status == filters.status)
    if filters.category:
        query = query.filter(func.trim(models.ProductModel.category) == filters.category.strip())
    total = query.count()
    items = (
        query.order_by(models.ProductModel.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return total, items


class ProductModelVersionFilters:
    def __init__(
        self,
        *,
        search: Optional[str] = None,
        version_kind: Optional[str] = None,
        version_status: Optional[str] = None,
        structure_standard_code: Optional[str] = None,
    ):
        self.search = search
        self.version_kind = version_kind
        self.version_status = version_status
        self.structure_standard_code = structure_standard_code


def list_versions(
    db: Session, *, filters: ProductModelVersionFilters, page: int, page_size: int
) -> Tuple[int, Sequence[Tuple[models.ProductModelVersion, models.ProductModel]]]:
    q = (
        db.query(models.ProductModelVersion, models.ProductModel)
        .join(models.ProductModel, models.ProductModel.id == models.ProductModelVersion.model_id)
        .filter(models.ProductModelVersion.is_archived.is_(False), models.ProductModel.is_archived.is_(False))
    )
    if filters.version_kind:
        q = q.filter(models.ProductModelVersion.version_kind == filters.version_kind)
    if filters.version_status:
        q = q.filter(models.ProductModelVersion.version_status == filters.version_status)
    if filters.search:
        pattern = f"%{filters.search.strip()}%"
        q = q.filter(
            or_(
                models.ProductModel.model_code.ilike(pattern),
                models.ProductModel.model_name.ilike(pattern),
                models.ProductModelVersion.version_label.ilike(pattern),
            )
        )
    structure_code = (filters.structure_standard_code or "").strip() or None
    dialect = str(getattr(getattr(db, "bind", None), "dialect", None).name or "")

    # SQLite fallback (tests): filter in Python, keep ordering/pagination consistent.
    if structure_code and dialect != "postgresql":
        all_rows = q.order_by(models.ProductModelVersion.updated_at.desc()).all()
        kept: List[Tuple[models.ProductModelVersion, models.ProductModel]] = []
        for v, m in all_rows:
            meta = getattr(v, "metadata_json", {}) or {}
            if str(meta.get("structure_standard_code") or "") == structure_code:
                kept.append((v, m))
        total = len(kept)
        start = (page - 1) * page_size
        end = start + page_size
        return total, kept[start:end]

    if structure_code:
        from sqlalchemy import cast
        from sqlalchemy.dialects.postgresql import JSONB

        meta = cast(models.ProductModelVersion.metadata_json, JSONB)
        q = q.filter(meta["structure_standard_code"].astext == structure_code)

    total = q.count()
    items = (
        q.order_by(models.ProductModelVersion.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return total, items


def get_model(db: Session, model_id: str, *, include_archived: bool = False) -> Optional[models.ProductModel]:
    q = db.query(models.ProductModel).filter(models.ProductModel.id == model_id)
    if not include_archived:
        q = q.filter(models.ProductModel.is_archived.is_(False))
    return q.one_or_none()


def list_model_modules(db: Session, model_id: str) -> Sequence[models.ModelProcessModule]:
    return (
        db.query(models.ModelProcessModule)
        .filter(
            models.ModelProcessModule.model_id == model_id,
            models.ModelProcessModule.is_archived.is_(False),
        )
        .order_by(asc(models.ModelProcessModule.sequence_order), asc(models.ModelProcessModule.created_at))
        .all()
    )


def list_model_material_lines(db: Session, model_id: str) -> Sequence[models.ModelMaterial]:
    return (
        db.query(models.ModelMaterial)
        .filter(models.ModelMaterial.model_id == model_id, models.ModelMaterial.is_archived.is_(False))
        .order_by(asc(models.ModelMaterial.sequence_order), asc(models.ModelMaterial.created_at))
        .all()
    )


def list_model_process_lines(db: Session, model_id: str) -> Sequence[models.ModelProcess]:
    return (
        db.query(models.ModelProcess)
        .filter(models.ModelProcess.model_id == model_id, models.ModelProcess.is_archived.is_(False))
        .order_by(asc(models.ModelProcess.sequence_order), asc(models.ModelProcess.created_at))
        .all()
    )


def list_model_versions(db: Session, model_id: str, *, include_archived: bool = False) -> Sequence[models.ProductModelVersion]:
    q = db.query(models.ProductModelVersion).filter(models.ProductModelVersion.model_id == model_id)
    if not include_archived:
        q = q.filter(models.ProductModelVersion.is_archived.is_(False))
    return q.order_by(
        asc(models.ProductModelVersion.created_at),
        asc(models.ProductModelVersion.id),
    ).all()


def get_model_version(
    db: Session, version_id: str, *, include_archived: bool = False
) -> Optional[models.ProductModelVersion]:
    q = db.query(models.ProductModelVersion).filter(models.ProductModelVersion.id == version_id)
    if not include_archived:
        q = q.filter(models.ProductModelVersion.is_archived.is_(False))
    return q.one_or_none()


def list_version_modules(db: Session, version_id: str) -> Sequence[models.ModelVersionModule]:
    return (
        db.query(models.ModelVersionModule)
        .filter(
            models.ModelVersionModule.version_id == version_id,
            models.ModelVersionModule.is_archived.is_(False),
        )
        .order_by(asc(models.ModelVersionModule.sequence_order), asc(models.ModelVersionModule.created_at))
        .all()
    )


def list_version_material_lines(db: Session, version_id: str) -> Sequence[models.ModelVersionMaterial]:
    return (
        db.query(models.ModelVersionMaterial)
        .filter(
            models.ModelVersionMaterial.version_id == version_id,
            models.ModelVersionMaterial.is_archived.is_(False),
        )
        .order_by(asc(models.ModelVersionMaterial.sequence_order), asc(models.ModelVersionMaterial.created_at))
        .all()
    )


def list_version_process_lines(db: Session, version_id: str) -> Sequence[models.ModelVersionProcess]:
    return (
        db.query(models.ModelVersionProcess)
        .filter(
            models.ModelVersionProcess.version_id == version_id,
            models.ModelVersionProcess.is_archived.is_(False),
        )
        .order_by(asc(models.ModelVersionProcess.sequence_order), asc(models.ModelVersionProcess.created_at))
        .all()
    )


def _extract_sample_and_standard(model: models.ProductModel) -> tuple[dict, dict]:
    meta = model.metadata_json or {}
    sample = (meta.get("sample") or {}) if isinstance(meta.get("sample"), dict) else {}
    standard = (meta.get("standard") or {}) if isinstance(meta.get("standard"), dict) else {}
    # defaults: standard=1000x1000 qty=1
    std = {
        "width_mm": _decimal(standard.get("width_mm"), Decimal("1000")),
        "height_mm": _decimal(standard.get("height_mm"), Decimal("1000")),
        "quantity": _decimal(standard.get("quantity"), Decimal("1")),
        "unit_label": str(standard.get("unit_label") or model.unit_of_measure or "幅"),
    }
    samp = {
        "width_mm": _decimal(sample.get("width_mm"), std["width_mm"]),
        "height_mm": _decimal(sample.get("height_mm"), std["height_mm"]),
        "quantity": _decimal(sample.get("quantity"), Decimal("1")),
        "unit_label": str(sample.get("unit_label") or model.unit_of_measure or "幅"),
    }
    return samp, std


def _measure_qty_for_method(method: str, *, spec: dict) -> Decimal:
    return _measure_qty(
        method,
        width_mm=_decimal(spec.get("width_mm")),
        height_mm=_decimal(spec.get("height_mm")),
        quantity=_decimal(spec.get("quantity"), Decimal("1")),
    )


def _build_placeholder_mapping_index(meta: dict) -> Dict[str, Dict[str, Any]]:
    mappings = meta.get("placeholder_mappings") or []
    mapping_by_placeholder: Dict[str, Dict[str, Any]] = {}
    if isinstance(mappings, list):
        for item in mappings:
            if not isinstance(item, dict):
                continue
            pid = str(item.get("placeholder_virtual_id") or "").strip()
            if pid:
                mapping_by_placeholder[pid] = item
    return mapping_by_placeholder


def _resolve_placeholder_to_fallback(
    db: Session,
    *,
    placeholder_virtual_id: str,
    mapping_by_placeholder: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Resolve a placeholder virtual material into its fallback material (real or non-placeholder virtual).
    Used before persisting any model/version ledger lines.
    """
    pid = str(placeholder_virtual_id or "").strip()
    if not pid:
        raise ValueError("占位型虚拟物料缺少 ref_id，无法替换兜底物料")

    ph = db.get(models.VirtualMaterial, pid)
    if not ph or ph.is_archived:
        raise ValueError("占位型虚拟物料不存在或已归档，无法替换兜底物料")
    if _get_virtual_kind(ph) != "placeholder":
        raise ValueError("仅占位型虚拟物料需要替换兜底物料")

    mapping = mapping_by_placeholder.get(pid) or {}
    rep_kind = str(mapping.get("replacement_kind") or "").strip()
    rep_id = str(mapping.get("replacement_ref_id") or "").strip()
    if not rep_kind or not rep_id:
        symbol = (ph.metadata_json or {}).get("placeholder_symbol") or ph.name or ph.virtual_code or pid
        raise ValueError(f"占位符 {symbol} 尚未配置兜底物料映射（replacement_kind/ref_id）")

    # Validate constraints: unit/category
    ph_unit = _normalize_unit(ph.unit)
    ph_cat = (getattr(ph, "category", None) or (ph.metadata_json or {}).get("constraint_category") or "").strip()

    if rep_kind == "real":
        mat = db.get(models.Material, rep_id)
        if not mat or mat.is_archived or not mat.is_active:
            raise ValueError("占位符兜底物料（实际物料）不存在/不可用")
        if ph_unit and _normalize_unit(mat.unit) and _normalize_unit(mat.unit) != ph_unit:
            raise ValueError(f"占位符单位={ph_unit}，但目标物料单位={_normalize_unit(mat.unit)}")
        if ph_cat and (mat.category or "").strip() and (mat.category or "").strip() != ph_cat:
            raise ValueError(f"占位符分类={ph_cat}，但目标物料分类={(mat.category or '').strip()}")
        return {
            "material_kind": "real",
            "material_ref_id": mat.id,
            "material_code": mat.material_code,
            "material_name": mat.material_name,
            "unit_of_measure": mat.unit,
            "origin_placeholder": {
                "virtual_id": ph.id,
                "virtual_code": ph.virtual_code,
                "name": ph.name,
                "placeholder_symbol": (ph.metadata_json or {}).get("placeholder_symbol"),
            },
        }

    if rep_kind == "virtual":
        vm = db.get(models.VirtualMaterial, rep_id)
        if not vm or vm.is_archived:
            raise ValueError("占位符兜底物料（虚拟物料）不存在/不可用")
        if _get_virtual_kind(vm) == "placeholder":
            raise ValueError("占位符兜底物料不允许指向占位型虚拟物料")
        if ph_unit and _normalize_unit(vm.unit) and _normalize_unit(vm.unit) != ph_unit:
            raise ValueError(f"占位符单位={ph_unit}，但目标物料单位={_normalize_unit(vm.unit)}")
        vm_cat = (getattr(vm, "category", None) or "").strip()
        if ph_cat and vm_cat and vm_cat != ph_cat:
            raise ValueError(f"占位符分类={ph_cat}，但目标物料分类={vm_cat}")
        return {
            "material_kind": "virtual",
            "material_ref_id": vm.id,
            "material_code": vm.virtual_code,
            "material_name": vm.name,
            "unit_of_measure": vm.unit,
            "origin_placeholder": {
                "virtual_id": ph.id,
                "virtual_code": ph.virtual_code,
                "name": ph.name,
                "placeholder_symbol": (ph.metadata_json or {}).get("placeholder_symbol"),
            },
        }

    raise ValueError("占位符兜底物料映射的 replacement_kind 仅支持 real / virtual")


def sync_lines_from_modules(db: Session, model: models.ProductModel, *, keep_overrides: bool = True) -> None:
    """
    Build model_materials/model_processes from current module bindings.
    Stores sample + standard trace fields in line.metadata_json.
    """
    sample, standard = _extract_sample_and_standard(model)
    mapping_by_placeholder = _build_placeholder_mapping_index(model.metadata_json or {})

    module_links = list_model_modules(db, model.id)
    module_ids = [link.module_id for link in module_links]
    modules = (
        db.query(models.ProcessModule)
        .filter(models.ProcessModule.id.in_(module_ids), models.ProcessModule.is_archived.is_(False))
        .all()
    )
    module_by_id = {m.id: m for m in modules}

    # index existing lines by source for keeping overrides
    existing_materials = list_model_material_lines(db, model.id)
    existing_by_source_mat: dict[str, models.ModelMaterial] = {}
    for row in existing_materials:
        meta = row.metadata_json or {}
        key = f"{meta.get('source_module_id')}::{meta.get('source_row_id')}"
        existing_by_source_mat[key] = row

    existing_processes = list_model_process_lines(db, model.id)
    existing_by_source_proc: dict[str, models.ModelProcess] = {}
    for row in existing_processes:
        meta = row.metadata_json or {}
        key = f"{meta.get('source_module_id')}::{meta.get('source_row_id')}"
        existing_by_source_proc[key] = row

    # wipe and rebuild
    db.query(models.ModelMaterial).filter(models.ModelMaterial.model_id == model.id).delete(synchronize_session=False)
    db.query(models.ModelProcess).filter(models.ModelProcess.model_id == model.id).delete(synchronize_session=False)

    seq_mat = 0
    seq_proc = 0
    for link in module_links:
        module = module_by_id.get(link.module_id)
        if not module:
            continue
        for m in module.materials or []:
            if m.is_archived:
                continue
            seq_mat += 1
            source_key = f"{module.id}::{m.id}"
            old = existing_by_source_mat.get(source_key) if keep_overrides else None
            old_meta = (old.metadata_json or {}) if old else {}
            meta: dict[str, Any] = {}
            meta["source_module_id"] = module.id
            meta["source_module_code"] = module.module_code
            meta["source_module_name"] = module.module_name
            meta["source_row_id"] = m.id
            # default trace values
            method = str(m.calculation_method or "count")
            sample_measure = _measure_qty_for_method(method, spec=sample)
            standard_measure = _measure_qty_for_method(method, spec=standard)
            base_qty = _decimal(m.quantity, Decimal("0"))
            meta["sample_used_quantity"] = str((sample_measure * base_qty).normalize())
            meta["standard_used_quantity"] = str((standard_measure * base_qty).normalize())
            meta["fixed_quantity"] = str(Decimal("0"))
            meta["coverage_ratio"] = str(Decimal("1"))
            # Carry pricing snapshot from module line if present; otherwise derive from master data.
            module_meta = m.metadata_json or {}
            if "bom_unit_price" in module_meta:
                meta["bom_unit_price"] = module_meta.get("bom_unit_price")
            if "bom_unit" in module_meta:
                meta["bom_unit"] = module_meta.get("bom_unit")
            if old_meta:
                # keep user edits at model layer
                for k in (
                    "sample_used_quantity",
                    "standard_used_quantity",
                    "fixed_quantity",
                    "coverage_ratio",
                    "remark",
                    "selection_notes",
                    "loss_notes",
                ):
                    if k in old_meta:
                        meta[k] = old_meta[k]

            # Placeholder virtual materials are template-only; resolve to fallback before persisting ledger.
            mat_kind = str(m.material_kind or "real")
            ref_id = str(m.material_ref_id or "")
            mat_code = m.material_code
            mat_name = m.material_name
            uom = m.unit_of_measure
            # Fallback: if module line doesn't contain BOM pricing snapshots, derive now so
            # model/version ledgers always have display-ready pricing info.
            if ("bom_unit_price" not in meta) or ("bom_unit" not in meta):
                try:
                    if mat_kind in ("real", "bom") and ref_id:
                        material = db.get(models.Material, ref_id)
                        if material and not material.is_archived:
                            if "bom_unit_price" not in meta:
                                price = _derive_bom_unit_price(material)
                                if price is not None:
                                    meta["bom_unit_price"] = float(price)
                            if "bom_unit" not in meta:
                                meta["bom_unit"] = material.unit
                    elif mat_kind == "virtual" and ref_id:
                        vm = db.get(models.VirtualMaterial, ref_id)
                        if vm and not vm.is_archived:
                            if "bom_unit" not in meta:
                                meta["bom_unit"] = vm.unit
                            if "bom_unit_price" not in meta:
                                raw = (vm.metadata_json or {}).get("bom_unit_price")
                                if raw not in (None, ""):
                                    try:
                                        meta["bom_unit_price"] = float(Decimal(str(raw)))
                                    except Exception:  # noqa: BLE001
                                        pass
                                # If virtual has no bom_unit_price snapshot, keep it absent; it can be computed
                                # by refresh_model_material_price_snapshots or by virtual bindings strategy.
                except Exception:
                    # best-effort only; never block sync
                    pass
            if mat_kind == "virtual" and ref_id:
                vm = db.get(models.VirtualMaterial, ref_id)
                if vm and not vm.is_archived and _get_virtual_kind(vm) == "placeholder":
                    try:
                        resolved = _resolve_placeholder_to_fallback(
                            db, placeholder_virtual_id=ref_id, mapping_by_placeholder=mapping_by_placeholder
                        )
                        mat_kind = resolved["material_kind"]
                        ref_id = resolved["material_ref_id"]
                        mat_code = resolved.get("material_code")
                        mat_name = resolved.get("material_name")
                        uom = resolved.get("unit_of_measure")
                        meta["origin_placeholder"] = resolved.get("origin_placeholder")
                    except ValueError:
                        # Soft mode: allow syncing modules that contain placeholder virtual materials
                        # without requiring placeholder_mappings. Keep the placeholder line and
                        # mark it for UI validation/replacement.
                        meta["is_placeholder"] = True
                        meta["origin_placeholder"] = {
                            "placeholder_virtual_id": vm.id,
                            "placeholder_symbol": (vm.metadata_json or {}).get("placeholder_symbol"),
                            "virtual_code": vm.virtual_code,
                            "name": vm.name,
                        }
            db.add(
                models.ModelMaterial(
                    model_id=model.id,
                    material_type=mat_kind,
                    material_ref_id=ref_id,
                    material_code=mat_code,
                    material_name=mat_name,
                    unit_of_measure=uom,
                    calculation_method=method,
                    base_quantity=base_qty,
                    loss_rate=_decimal(m.loss_rate, Decimal("0")),
                    sequence_order=seq_mat,
                    notes=m.selection_notes,
                    metadata_json=_json_safe(meta),
                )
            )

        for s in module.steps or []:
            if s.is_archived:
                continue
            if not s.process_id:
                continue
            seq_proc += 1
            source_key = f"{module.id}::{s.id}"
            old = existing_by_source_proc.get(source_key) if keep_overrides else None
            old_meta = (old.metadata_json or {}) if old else {}
            meta: dict[str, Any] = {}
            meta["source_module_id"] = module.id
            meta["source_module_code"] = module.module_code
            meta["source_module_name"] = module.module_name
            meta["source_row_id"] = s.id
            pricing_method = str(s.pricing_method or "count")
            meta["pricing_method"] = pricing_method
            # copy module step pricing params as defaults (these are expected to be edited in model)
            step_meta = s.metadata_json or {}
            for k in ("cost_type", "base_minutes", "unit_minutes", "measure_unit", "rate_per_minute", "piece_rate"):
                if k in step_meta:
                    meta[k] = step_meta[k]
            # Fallback: for legacy modules with empty step metadata, derive from process master.
            proc = db.get(models.Process, s.process_id) if s.process_id else None
            proc_meta = (proc.metadata_json or {}) if proc else {}
            for k in ("cost_type", "base_minutes", "unit_minutes", "measure_unit", "rate_per_minute", "piece_rate"):
                if k not in meta and k in proc_meta:
                    meta[k] = proc_meta.get(k)
            if "team_name" not in meta:
                meta["team_name"] = (s.team_name or None) or (proc.team_name if proc else None)
            if "rate_per_minute" not in meta and proc and proc.standard_rate is not None:
                meta["rate_per_minute"] = proc.standard_rate
            # derive sample/standard minutes (best effort)
            measure_method = pricing_method if pricing_method in ("fixed", "count", "area", "perimeter", "width", "height") else "count"
            sample_measure = _measure_qty_for_method(measure_method if measure_method != "fixed" else "count", spec=sample)
            standard_measure = _measure_qty_for_method(measure_method if measure_method != "fixed" else "count", spec=standard)
            base_minutes = _decimal(meta.get("base_minutes"), Decimal("0"))
            unit_minutes = _decimal(meta.get("unit_minutes"), Decimal("0"))
            meta["sample_minutes"] = str((base_minutes + unit_minutes * sample_measure).normalize())
            meta["standard_minutes"] = str((base_minutes + unit_minutes * standard_measure).normalize())
            if old_meta:
                for k in ("sample_minutes", "standard_minutes", "cost_type", "base_minutes", "unit_minutes", "rate_per_minute", "piece_rate", "team_name"):
                    if k in old_meta:
                        meta[k] = old_meta[k]
            db.add(
                models.ModelProcess(
                    model_id=model.id,
                    process_id=s.process_id,
                    sequence_order=seq_proc,
                    notes=s.notes,
                    metadata_json=meta,
                )
            )


def _extract_sample_and_standard_from_version(
    model: models.ProductModel, version: models.ProductModelVersion
) -> tuple[dict, dict]:
    meta = version.metadata_json or {}
    sample = (meta.get("sample") or {}) if isinstance(meta.get("sample"), dict) else {}
    standard = (meta.get("standard") or {}) if isinstance(meta.get("standard"), dict) else {}
    std = {
        "width_mm": _decimal(standard.get("width_mm"), Decimal("1000")),
        "height_mm": _decimal(standard.get("height_mm"), Decimal("1000")),
        "quantity": _decimal(standard.get("quantity"), Decimal("1")),
        "unit_label": str(standard.get("unit_label") or model.unit_of_measure or "幅"),
    }
    if (version.version_kind or "") == "standard":
        std["width_mm"] = Decimal("1000")
        std["height_mm"] = Decimal("1000")
        std["quantity"] = Decimal("1")
    samp = {
        "width_mm": _decimal(sample.get("width_mm"), std["width_mm"]),
        "height_mm": _decimal(sample.get("height_mm"), std["height_mm"]),
        "quantity": _decimal(sample.get("quantity"), Decimal("1")),
        "unit_label": str(sample.get("unit_label") or model.unit_of_measure or "幅"),
    }
    return samp, std


def sync_version_lines_from_modules(
    db: Session,
    *,
    version: models.ProductModelVersion,
    keep_overrides: bool = True,
    module_ids: List[str] | None = None,
) -> None:
    """
    Build model_version_materials/model_version_processes from version module bindings.
    """
    model = db.get(models.ProductModel, version.model_id)
    if not model or model.is_archived:
        raise ValueError("Product model not found")

    sample, standard = _extract_sample_and_standard_from_version(model, version)
    version_meta = version.metadata_json or {}
    mapping_by_placeholder = _build_placeholder_mapping_index(version_meta) or _build_placeholder_mapping_index(
        model.metadata_json or {}
    )

    # IMPORTANT:
    # - UI edits "modules" at model layer (model_process_modules)
    # - The version has its own snapshot table (model_version_modules)
    # To avoid "deleted modules come back after sync" on drafts, we treat
    # draft versions as "follow model's latest modules", and rebuild the
    # version snapshot accordingly.
    if (version.version_status or "") == "draft":
        model_links = list_model_modules(db, model.id)
        # rebuild version modules snapshot
        db.query(models.ModelVersionModule).filter(models.ModelVersionModule.version_id == version.id).delete(
            synchronize_session=False
        )
        for link in model_links:
            db.add(
                models.ModelVersionModule(
                    version_id=version.id,
                    module_id=link.module_id,
                    sequence_order=link.sequence_order,
                    notes=link.notes,
                    metadata_json=link.metadata_json or {},
                )
            )
        # SessionLocal uses autoflush=False; ensure inserts are flushed before querying.
        db.flush()
        module_links = list_version_modules(db, version.id)
    else:
        module_links = list_version_modules(db, version.id)

    all_module_ids = [link.module_id for link in module_links]
    modules = (
        db.query(models.ProcessModule)
        .filter(models.ProcessModule.id.in_(all_module_ids), models.ProcessModule.is_archived.is_(False))
        .all()
    )
    module_by_id = {m.id: m for m in modules}

    existing_materials = list_version_material_lines(db, version.id)
    existing_by_source_mat: dict[str, models.ModelVersionMaterial] = {}
    for row in existing_materials:
        meta = row.metadata_json or {}
        key = f"{meta.get('source_module_id')}::{meta.get('source_row_id')}"
        existing_by_source_mat[key] = row

    existing_processes = list_version_process_lines(db, version.id)
    existing_by_source_proc: dict[str, models.ModelVersionProcess] = {}
    for row in existing_processes:
        meta = row.metadata_json or {}
        key = f"{meta.get('source_module_id')}::{meta.get('source_row_id')}"
        existing_by_source_proc[key] = row

    selected = {str(x).strip() for x in (module_ids or []) if str(x).strip()}
    # Decide which existing rows should be removed for re-sync.
    # - selected empty: sync all modules
    #   - keep_overrides=True: keep user-added (non-module) rows; refresh module-derived rows
    #   - keep_overrides=False: wipe everything (original behavior)
    # - selected non-empty: only refresh selected modules; keep others (and keep user-added rows)
    to_delete_mat: list[models.ModelVersionMaterial] = []
    to_delete_proc: list[models.ModelVersionProcess] = []
    if not selected and not keep_overrides:
        db.query(models.ModelVersionMaterial).filter(models.ModelVersionMaterial.version_id == version.id).delete(
            synchronize_session=False
        )
        db.query(models.ModelVersionProcess).filter(models.ModelVersionProcess.version_id == version.id).delete(
            synchronize_session=False
        )
        kept_mat_max_seq = 0
        kept_proc_max_seq = 0
    else:
        # Row-by-row delete to preserve non-module rows (and/or unselected modules)
        kept_mat_max_seq = 0
        kept_proc_max_seq = 0
        if not selected:
            # sync all modules but keep non-module rows
            for row in existing_materials:
                meta = row.metadata_json or {}
                src = str(meta.get("source_module_id") or "").strip()
                if src:
                    to_delete_mat.append(row)
                else:
                    kept_mat_max_seq = max(kept_mat_max_seq, int(row.sequence_order or 0))
            for row in existing_processes:
                meta = row.metadata_json or {}
                src = str(meta.get("source_module_id") or "").strip()
                if src:
                    to_delete_proc.append(row)
                else:
                    kept_proc_max_seq = max(kept_proc_max_seq, int(row.sequence_order or 0))
        else:
            # selected sync: only delete rows belonging to selected modules
            for row in existing_materials:
                meta = row.metadata_json or {}
                src = str(meta.get("source_module_id") or "").strip()
                if src and src in selected:
                    to_delete_mat.append(row)
                else:
                    kept_mat_max_seq = max(kept_mat_max_seq, int(row.sequence_order or 0))
            for row in existing_processes:
                meta = row.metadata_json or {}
                src = str(meta.get("source_module_id") or "").strip()
                if src and src in selected:
                    to_delete_proc.append(row)
                else:
                    kept_proc_max_seq = max(kept_proc_max_seq, int(row.sequence_order or 0))

        for row in to_delete_mat:
            db.delete(row)
        for row in to_delete_proc:
            db.delete(row)
        db.flush()

    # Ensure new rows get non-conflicting sequence_order (append after kept rows)
    seq_mat = kept_mat_max_seq
    seq_proc = kept_proc_max_seq
    for link in module_links:
        module = module_by_id.get(link.module_id)
        if not module:
            continue
        if selected and str(module.id) not in selected:
            continue

        for m in module.materials or []:
            if m.is_archived:
                continue
            seq_mat += 1
            source_key = f"{module.id}::{m.id}"
            old = existing_by_source_mat.get(source_key) if keep_overrides else None
            old_meta = (old.metadata_json or {}) if old else {}
            meta: dict[str, Any] = {}
            meta["source_module_id"] = module.id
            meta["source_module_code"] = module.module_code
            meta["source_module_name"] = module.module_name
            meta["source_row_id"] = m.id

            method = str(m.calculation_method or "count")
            sample_measure = _measure_qty_for_method(method, spec=sample)
            standard_measure = _measure_qty_for_method(method, spec=standard)
            base_qty = _decimal(m.quantity, Decimal("0"))
            meta["sample_used_quantity"] = str((sample_measure * base_qty).normalize())
            meta["standard_used_quantity"] = str((standard_measure * base_qty).normalize())
            meta["fixed_quantity"] = str(Decimal("0"))
            meta["coverage_ratio"] = str(Decimal("1"))

            module_meta = m.metadata_json or {}
            if "bom_unit_price" in module_meta:
                meta["bom_unit_price"] = module_meta.get("bom_unit_price")
            if "bom_unit" in module_meta:
                meta["bom_unit"] = module_meta.get("bom_unit")

            if old_meta:
                for k in (
                    "sample_used_quantity",
                    "standard_used_quantity",
                    "fixed_quantity",
                    "coverage_ratio",
                    "remark",
                    "selection_notes",
                    "loss_notes",
                ):
                    if k in old_meta:
                        meta[k] = old_meta[k]

            mat_kind = str(m.material_kind or "real")
            ref_id = str(m.material_ref_id or "")
            mat_code = m.material_code
            mat_name = m.material_name
            uom = m.unit_of_measure
            # Fallback derive pricing snapshots for legacy module rows (same as model layer).
            if ("bom_unit_price" not in meta) or ("bom_unit" not in meta):
                try:
                    if mat_kind in ("real", "bom") and ref_id:
                        material = db.get(models.Material, ref_id)
                        if material and not material.is_archived:
                            if "bom_unit_price" not in meta:
                                price = _derive_bom_unit_price(material)
                                if price is not None:
                                    meta["bom_unit_price"] = float(price)
                            if "bom_unit" not in meta:
                                meta["bom_unit"] = material.unit
                    elif mat_kind == "virtual" and ref_id:
                        vm = db.get(models.VirtualMaterial, ref_id)
                        if vm and not vm.is_archived:
                            if "bom_unit" not in meta:
                                meta["bom_unit"] = vm.unit
                            if "bom_unit_price" not in meta:
                                raw = (vm.metadata_json or {}).get("bom_unit_price")
                                if raw not in (None, ""):
                                    try:
                                        meta["bom_unit_price"] = float(Decimal(str(raw)))
                                    except Exception:  # noqa: BLE001
                                        pass
                except Exception:
                    pass
            if mat_kind == "virtual" and ref_id:
                vm = db.get(models.VirtualMaterial, ref_id)
                if vm and not vm.is_archived and _get_virtual_kind(vm) == "placeholder":
                    try:
                        resolved = _resolve_placeholder_to_fallback(
                            db, placeholder_virtual_id=ref_id, mapping_by_placeholder=mapping_by_placeholder
                        )
                        mat_kind = resolved["material_kind"]
                        ref_id = resolved["material_ref_id"]
                        mat_code = resolved.get("material_code")
                        mat_name = resolved.get("material_name")
                        uom = resolved.get("unit_of_measure")
                        meta["origin_placeholder"] = resolved.get("origin_placeholder")
                    except ValueError:
                        # Soft mode: allow syncing modules with placeholder virtual materials without mapping.
                        # Keep placeholder in lines; UI should prompt replacement and block saving/publishing.
                        meta["is_placeholder"] = True
                        meta["origin_placeholder"] = {
                            "placeholder_virtual_id": vm.id,
                            "placeholder_symbol": (vm.metadata_json or {}).get("placeholder_symbol"),
                            "virtual_code": vm.virtual_code,
                            "name": vm.name,
                        }

            db.add(
                models.ModelVersionMaterial(
                    version_id=version.id,
                    material_type=mat_kind,
                    material_ref_id=ref_id,
                    material_code=mat_code,
                    material_name=mat_name,
                    unit_of_measure=uom,
                    calculation_method=method,
                    base_quantity=base_qty,
                    loss_rate=_decimal(m.loss_rate, Decimal("0")),
                    sequence_order=seq_mat,
                    notes=m.selection_notes,
                    metadata_json=_json_safe(meta),
                )
            )

        for s in module.steps or []:
            if s.is_archived:
                continue
            if not s.process_id:
                continue
            seq_proc += 1
            source_key = f"{module.id}::{s.id}"
            old = existing_by_source_proc.get(source_key) if keep_overrides else None
            old_meta = (old.metadata_json or {}) if old else {}
            meta: dict[str, Any] = {}
            meta["source_module_id"] = module.id
            meta["source_module_code"] = module.module_code
            meta["source_module_name"] = module.module_name
            meta["source_row_id"] = s.id
            pricing_method = str(s.pricing_method or "count")
            meta["pricing_method"] = pricing_method
            step_meta = s.metadata_json or {}
            for k in ("cost_type", "base_minutes", "unit_minutes", "measure_unit", "rate_per_minute", "piece_rate"):
                if k in step_meta:
                    meta[k] = step_meta[k]
            proc = db.get(models.Process, s.process_id) if s.process_id else None
            proc_meta = (proc.metadata_json or {}) if proc else {}
            for k in ("cost_type", "base_minutes", "unit_minutes", "measure_unit", "rate_per_minute", "piece_rate"):
                if k not in meta and k in proc_meta:
                    meta[k] = proc_meta.get(k)
            if "team_name" not in meta:
                meta["team_name"] = (s.team_name or None) or (proc.team_name if proc else None)
            if "rate_per_minute" not in meta and proc and proc.standard_rate is not None:
                meta["rate_per_minute"] = proc.standard_rate
            measure_method = (
                pricing_method
                if pricing_method in ("fixed", "count", "area", "perimeter", "width", "height")
                else "count"
            )
            sample_measure = _measure_qty_for_method(measure_method if measure_method != "fixed" else "count", spec=sample)
            standard_measure = _measure_qty_for_method(
                measure_method if measure_method != "fixed" else "count", spec=standard
            )
            base_minutes = _decimal(meta.get("base_minutes"), Decimal("0"))
            unit_minutes = _decimal(meta.get("unit_minutes"), Decimal("0"))
            meta["sample_minutes"] = str((base_minutes + unit_minutes * sample_measure).normalize())
            meta["standard_minutes"] = str((base_minutes + unit_minutes * standard_measure).normalize())
            if old_meta:
                for k in (
                    "sample_minutes",
                    "standard_minutes",
                    "cost_type",
                    "base_minutes",
                    "unit_minutes",
                    "rate_per_minute",
                    "piece_rate",
                    "team_name",
                ):
                    if k in old_meta:
                        meta[k] = old_meta[k]
            db.add(
                models.ModelVersionProcess(
                    version_id=version.id,
                    process_id=s.process_id,
                    sequence_order=seq_proc,
                    notes=s.notes,
                    metadata_json=_json_safe(meta),
                )
            )

    db.commit()


def refresh_model_material_price_snapshots(db: Session, model: models.ProductModel) -> None:
    """
    Refresh BOM unit price/unit snapshots for model material lines.

    - real/bom: read from material master metadata_json.bom_unit_price (via _derive_bom_unit_price) and material.unit
    - virtual (recipe/kit): derive from bindings' material BOM prices (+ binding loss) and virtual unit semantics
    - placeholder: fixed 0 + virtual unit

    This does NOT change quantities/measurements; only updates metadata_json.{bom_unit_price,bom_unit} for display and
    for cases where frontend wants a persisted snapshot without forcing preview refresh.
    """
    rows = list_model_material_lines(db, model.id)
    for row in rows:
        # NOTE: SQLAlchemy JSON columns won't reliably detect in-place dict mutations unless using mutable types.
        # Always assign a fresh dict to ensure updates are persisted.
        meta = dict(row.metadata_json or {})
        kind = str(row.material_type or "real")
        ref_id = str(row.material_ref_id or "").strip()

        if kind in ("real", "bom"):
            material = db.get(models.Material, ref_id) if ref_id else None
            if not material or material.is_archived:
                continue
            price = _derive_bom_unit_price(material)
            if price is not None:
                meta["bom_unit_price"] = float(price)
            meta["bom_unit"] = material.unit
            row.metadata_json = meta
            continue

        if kind != "virtual":
            continue

        virtual = db.get(models.VirtualMaterial, ref_id) if ref_id else None
        if not virtual or virtual.is_archived:
            continue

        v_kind = _get_virtual_kind(virtual)
        if v_kind == "placeholder":
            meta["bom_unit_price"] = 0.0
            meta["bom_unit"] = virtual.unit
            row.metadata_json = meta
            continue

        # unit semantics
        meta["bom_unit"] = "套" if v_kind == "kit" else (virtual.unit or meta.get("bom_unit"))

        binds = (
            db.query(models.VirtualMaterialBinding)
            .filter(models.VirtualMaterialBinding.virtual_material_id == virtual.id)
            .all()
        )
        if not binds:
            row.metadata_json = meta
            continue

        v_price: Decimal = Decimal("0")
        hit_any = False
        for bind in binds:
            material = db.get(models.Material, bind.material_id)
            if not material or material.is_archived:
                continue
            price = _derive_bom_unit_price(material)
            if price is None:
                continue

            qty = _decimal(bind.quantity_ratio, Decimal("0"))
            if v_kind == "recipe" and qty > Decimal("1.5"):
                qty = qty / Decimal("100")

            bind_loss = _decimal(bind.loss_rate, Decimal("0"))
            loss_factor = Decimal("1") + (bind_loss / Decimal("100"))
            v_price += price * qty * loss_factor
            hit_any = True

        if hit_any:
            meta["bom_unit_price"] = float(v_price)
        row.metadata_json = meta
    db.commit()


def refresh_version_material_price_snapshots(db: Session, version: models.ProductModelVersion) -> None:
    """
    Refresh BOM unit price/unit snapshots for *version* material lines.

    Background:
    - Version lines are often synced from modules and may carry stale metadata_json.{bom_unit_price,bom_unit}.
    - Virtual materials' BOM prices are derived from bindings and may change over time.

    This does NOT change quantities/measurements; it only updates metadata_json.{bom_unit_price,bom_unit} for display and
    for cases where frontend wants a persisted snapshot without forcing preview refresh.
    """
    rows = list_version_material_lines(db, version.id)
    for row in rows:
        # NOTE: SQLAlchemy JSON columns won't reliably detect in-place dict mutations unless using mutable types.
        # Always assign a fresh dict to ensure updates are persisted.
        meta = dict(row.metadata_json or {})
        kind = str(row.material_type or "real")
        ref_id = str(row.material_ref_id or "").strip()

        if kind in ("real", "bom"):
            material = db.get(models.Material, ref_id) if ref_id else None
            if not material or material.is_archived:
                continue
            price = _derive_bom_unit_price(material)
            if price is not None:
                meta["bom_unit_price"] = float(price)
            meta["bom_unit"] = material.unit
            row.metadata_json = meta
            continue

        if kind != "virtual":
            continue

        virtual = db.get(models.VirtualMaterial, ref_id) if ref_id else None
        if not virtual or virtual.is_archived:
            continue

        v_kind = _get_virtual_kind(virtual)
        if v_kind == "placeholder":
            meta["bom_unit_price"] = 0.0
            meta["bom_unit"] = virtual.unit
            row.metadata_json = meta
            continue

        # unit semantics
        meta["bom_unit"] = "套" if v_kind == "kit" else (virtual.unit or meta.get("bom_unit"))

        binds = (
            db.query(models.VirtualMaterialBinding)
            .filter(models.VirtualMaterialBinding.virtual_material_id == virtual.id)
            .all()
        )
        if not binds:
            row.metadata_json = meta
            continue

        v_price: Decimal = Decimal("0")
        hit_any = False
        for bind in binds:
            material = db.get(models.Material, bind.material_id)
            if not material or material.is_archived:
                continue
            price = _derive_bom_unit_price(material)
            if price is None:
                continue

            qty = _decimal(bind.quantity_ratio, Decimal("0"))
            if v_kind == "recipe" and qty > Decimal("1.5"):
                qty = qty / Decimal("100")

            bind_loss = _decimal(bind.loss_rate, Decimal("0"))
            loss_factor = Decimal("1") + (bind_loss / Decimal("100"))
            v_price += price * qty * loss_factor
            hit_any = True

        if hit_any:
            meta["bom_unit_price"] = float(v_price)
        row.metadata_json = meta
    db.commit()


def replace_model_lines(
    db: Session,
    model: models.ProductModel,
    *,
    sample: dict,
    standard: dict,
    materials: List[Dict[str, Any]],
    processes: List[Dict[str, Any]],
) -> None:
    """
    Overwrite model_materials/model_processes using payload from UI.
    Also persists sample/standard into model.metadata_json for traceability.
    """
    meta = model.metadata_json or {}
    meta["sample"] = sample
    meta["standard"] = standard
    model.metadata_json = _json_safe(meta)
    db.commit()

    # Replace materials
    db.query(models.ModelMaterial).filter(models.ModelMaterial.model_id == model.id).delete(synchronize_session=False)
    db.query(models.ModelProcess).filter(models.ModelProcess.model_id == model.id).delete(synchronize_session=False)

    sample_spec = {
        "width_mm": _decimal(sample.get("width_mm"), Decimal("1000")),
        "height_mm": _decimal(sample.get("height_mm"), Decimal("1000")),
        "quantity": _decimal(sample.get("quantity"), Decimal("1")),
    }
    standard_spec = {
        "width_mm": _decimal(standard.get("width_mm"), Decimal("1000")),
        "height_mm": _decimal(standard.get("height_mm"), Decimal("1000")),
        "quantity": _decimal(standard.get("quantity"), Decimal("1")),
    }

    seq = 0
    for item in materials:
        seq += 1
        kind = str(item.get("material_kind") or "real")
        ref_id = str(item.get("material_ref_id") or "").strip()
        # Disallow persisting placeholder virtual materials into model ledger.
        # Placeholders are template-only (modules). Model lines must be priceable fallbacks.
        if kind == "virtual" and ref_id:
            vm = db.get(models.VirtualMaterial, ref_id)
            if vm and not vm.is_archived and _get_virtual_kind(vm) == "placeholder":
                raise ValueError("模型清单不允许保存占位型虚拟物料：请先在“占位符映射”中选择兜底物料并替换后再保存")
        method = str(item.get("calculation_method") or "count")
        loss_rate = _decimal(item.get("loss_rate"), Decimal("0"))
        base_qty = item.get("base_quantity")
        sample_used = item.get("sample_used_quantity")
        fixed_qty = item.get("fixed_quantity")
        coverage_ratio = item.get("coverage_ratio")

        # derive base_quantity from sample_used if not provided (ratio mode)
        base = _decimal(base_qty, Decimal("0")) if base_qty is not None else None
        if base is None and model.calc_mode == "ratio" and sample_used is not None:
            sample_measure = _measure_qty(method, **sample_spec)
            if sample_measure > 0:
                base = _decimal(sample_used, Decimal("0")) / sample_measure
            else:
                base = Decimal("0")
        if base is None:
            base = _decimal(base_qty, Decimal("0"))

        standard_measure = _measure_qty(method, **standard_spec)
        # professional: standard_used (未计损耗) = fixed_qty + standard_measure * base_qty
        fixed = _decimal(fixed_qty, Decimal("0"))
        cov = _decimal(coverage_ratio, Decimal("1"))
        if model.calc_mode == "ratio":
            standard_used = fixed + (standard_measure * base * cov)
        else:
            standard_used = _decimal(item.get("standard_used_quantity"), Decimal("0"))
        meta_line: dict[str, Any] = dict(item.get("metadata_json") or {})
        for k in ("source_module_id", "source_module_code", "source_module_name"):
            if item.get(k) is not None:
                meta_line[k] = item.get(k)
        if sample_used is not None:
            meta_line["sample_used_quantity"] = str(_decimal(sample_used, Decimal("0")))
        meta_line["standard_used_quantity"] = str(_decimal(standard_used, Decimal("0")))
        meta_line["fixed_quantity"] = str(fixed)
        meta_line["coverage_ratio"] = str(cov)

        # IMPORTANT: Persist unit_of_measure on ledger lines (preview/BOM reads this field).
        # Otherwise UI may show unit from master, but BOM will always display '-' (None).
        uom: Optional[str] = None
        if ref_id:
            if kind in ("real", "material"):
                mat = db.get(models.Material, ref_id)
                if mat and not mat.is_archived:
                    uom = getattr(mat, "unit", None)
            elif kind == "virtual":
                vm2 = db.get(models.VirtualMaterial, ref_id)
                if vm2 and not vm2.is_archived:
                    uom = getattr(vm2, "unit", None)
        db.add(
            models.ModelMaterial(
                model_id=model.id,
                material_type=kind,
                material_ref_id=ref_id,
                material_code=item.get("material_code"),
                material_name=item.get("material_name"),
                unit_of_measure=uom,
                calculation_method=method,
                base_quantity=base,
                loss_rate=loss_rate,
                sequence_order=seq,
                notes=item.get("notes"),
                metadata_json=_json_safe(meta_line),
            )
        )

    # Replace processes
    seqp = 0
    for item in processes:
        seqp += 1
        process_id = str(item.get("process_id") or "").strip()
        meta_line: dict[str, Any] = dict(item.get("metadata_json") or {})
        for k in ("source_module_id", "source_module_code", "source_module_name"):
            if item.get(k) is not None:
                meta_line[k] = item.get(k)
        # persist pricing fields
        for k in (
            "team_name",
            "pricing_method",
            "cost_type",
            "base_minutes",
            "unit_minutes",
            "rate_per_minute",
            "piece_rate",
            "sample_minutes",
            "standard_minutes",
        ):
            if item.get(k) is not None:
                meta_line[k] = item.get(k)
        db.add(
            models.ModelProcess(
                model_id=model.id,
                process_id=process_id,
                sequence_order=seqp,
                notes=item.get("notes"),
                metadata_json=_json_safe(meta_line),
            )
        )

    db.commit()



def replace_version_lines(
    db: Session,
    *,
    version: models.ProductModelVersion,
    sample: dict,
    standard: dict,
    materials: List[Dict[str, Any]],
    processes: List[Dict[str, Any]],
) -> None:
    """
    Overwrite model_version_materials/model_version_processes using payload from UI.
    Persists sample/standard into version.metadata_json for reproducible preview/publish.
    """
    model = db.get(models.ProductModel, version.model_id)
    if not model or model.is_archived:
        raise ValueError("Product model not found")

    meta = version.metadata_json or {}
    meta["sample"] = sample
    meta["standard"] = standard
    if "placeholder_mappings" not in meta:
        m = (model.metadata_json or {}).get("placeholder_mappings")
        meta["placeholder_mappings"] = m if isinstance(m, list) else []
    meta.setdefault("calc_mode", model.calc_mode)
    meta.setdefault("fixed_price", model.fixed_price)
    version.metadata_json = _json_safe(meta)

    # IMPORTANT:
    # Do NOT hard-delete all version lines here.
    # These ledger line IDs are referenced by line variants (base_line_id) with FK ondelete=CASCADE.
    # If we delete+recreate every time, operators will "lose" variants after clicking "保存清单".
    existing_mats = (
        db.query(models.ModelVersionMaterial)
        .filter(models.ModelVersionMaterial.version_id == version.id)
        .all()
    )
    existing_procs = (
        db.query(models.ModelVersionProcess)
        .filter(models.ModelVersionProcess.version_id == version.id)
        .all()
    )
    mats_by_id = {str(x.id): x for x in existing_mats}
    procs_by_id = {str(x.id): x for x in existing_procs}

    sample_spec = {
        "width_mm": _decimal(sample.get("width_mm"), Decimal("1000")),
        "height_mm": _decimal(sample.get("height_mm"), Decimal("1000")),
        "quantity": _decimal(sample.get("quantity"), Decimal("1")),
    }
    standard_spec = {
        "width_mm": _decimal(standard.get("width_mm"), Decimal("1000")),
        "height_mm": _decimal(standard.get("height_mm"), Decimal("1000")),
        "quantity": _decimal(standard.get("quantity"), Decimal("1")),
    }

    calc_mode = (meta.get("calc_mode") or model.calc_mode or "ratio").strip()

    seq = 0
    keep_mat_ids: set[str] = set()
    for item in materials:
        seq += 1
        incoming_id = str(item.get("id") or "").strip() or None
        kind = str(item.get("material_kind") or "real")
        ref_id = str(item.get("material_ref_id") or "").strip()
        if kind == "virtual" and ref_id:
            vm = db.get(models.VirtualMaterial, ref_id)
            if vm and not vm.is_archived and _get_virtual_kind(vm) == "placeholder":
                # Allow placeholder virtual materials in sample versions for temporary saving / collaboration.
                # Guardrails are enforced at:
                # - derive standard (source sample must have placeholders replaced)
                # - publish standard (standard version must not contain placeholders)
                if str(getattr(version, "version_kind", "") or "").strip() == "standard":
                    raise ValueError(
                        "版本清单不允许保存占位型虚拟物料：请先在“占位符映射”中选择兜底物料并替换后再保存"
                    )
        method = str(item.get("calculation_method") or "count")
        base_qty = item.get("base_quantity")
        sample_used = item.get("sample_used_quantity")
        fixed_qty = item.get("fixed_quantity")
        coverage_ratio = item.get("coverage_ratio")

        base = _decimal(base_qty, Decimal("0")) if base_qty is not None else None
        if base is None and calc_mode == "ratio" and sample_used is not None:
            sample_measure = _measure_qty(method, **sample_spec)
            if sample_measure > 0:
                base = _decimal(sample_used, Decimal("0")) / sample_measure
            else:
                base = Decimal("0")
        if base is None:
            base = _decimal(base_qty, Decimal("0"))

        standard_measure = _measure_qty(method, **standard_spec)
        fixed = _decimal(fixed_qty, Decimal("0"))
        cov = _decimal(coverage_ratio, Decimal("1"))
        if calc_mode == "ratio":
            standard_used = fixed + (standard_measure * base * cov)
        else:
            standard_used = _decimal(item.get("standard_used_quantity"), Decimal("0"))

        meta_line: dict[str, Any] = dict(item.get("metadata_json") or {})
        for k in ("source_module_id", "source_module_code", "source_module_name"):
            if item.get(k) is not None:
                meta_line[k] = item.get(k)
        if sample_used is not None:
            meta_line["sample_used_quantity"] = str(_decimal(sample_used, Decimal("0")))
        meta_line["standard_used_quantity"] = str(_decimal(standard_used, Decimal("0")))
        meta_line["fixed_quantity"] = str(fixed)
        meta_line["coverage_ratio"] = str(cov)

        # IMPORTANT: Persist unit_of_measure on version ledger lines (bom/generate reads ModelVersionMaterial.unit_of_measure).
        # Otherwise preview BOM will always display '-' even if material master has unit (e.g. WH05009: 平米).
        uom: Optional[str] = None
        if ref_id:
            if kind in ("real", "material"):
                mat = db.get(models.Material, ref_id)
                if mat and not mat.is_archived:
                    uom = getattr(mat, "unit", None)
            elif kind == "virtual":
                vm2 = db.get(models.VirtualMaterial, ref_id)
                if vm2 and not vm2.is_archived:
                    uom = getattr(vm2, "unit", None)

        # Upsert: preserve id to avoid deleting line variants.
        row = mats_by_id.get(incoming_id) if incoming_id else None
        if row is None:
            row = models.ModelVersionMaterial(
                id=incoming_id,  # allow client-provided id
                version_id=version.id,
            )
            db.add(row)
        keep_mat_ids.add(str(row.id))
        row.version_id = version.id
        row.material_type = kind
        row.material_ref_id = ref_id
        row.material_code = item.get("material_code")
        row.material_name = item.get("material_name")
        row.unit_of_measure = uom
        row.calculation_method = method
        row.base_quantity = base
        row.loss_rate = _decimal(item.get("loss_rate"), Decimal("0"))
        row.sequence_order = seq
        row.notes = item.get("notes")
        # Merge existing metadata to avoid losing server-side fields not round-tripped by UI.
        base_meta = dict(getattr(row, "metadata_json", None) or {})
        base_meta.update(dict(item.get("metadata_json") or {}))
        base_meta.update(meta_line)
        row.metadata_json = _json_safe(base_meta)

    # Delete removed material rows (this will cascade delete variants for intentionally removed lines).
    if keep_mat_ids:
        db.query(models.ModelVersionMaterial).filter(
            models.ModelVersionMaterial.version_id == version.id,
            ~models.ModelVersionMaterial.id.in_(list(keep_mat_ids)),
        ).delete(synchronize_session=False)
    else:
        db.query(models.ModelVersionMaterial).filter(
            models.ModelVersionMaterial.version_id == version.id
        ).delete(synchronize_session=False)

    seqp = 0
    keep_proc_ids: set[str] = set()
    for item in processes:
        seqp += 1
        incoming_id = str(item.get("id") or "").strip() or None
        process_id = str(item.get("process_id") or "").strip()
        meta_line = dict(item.get("metadata_json") or {})
        for k in ("source_module_id", "source_module_code", "source_module_name"):
            if item.get(k) is not None:
                meta_line[k] = item.get(k)
        for k in (
            "team_name",
            "pricing_method",
            "cost_type",
            "base_minutes",
            "unit_minutes",
            "rate_per_minute",
            "piece_rate",
            "sample_minutes",
            "standard_minutes",
        ):
            if item.get(k) is not None:
                meta_line[k] = item.get(k)
        rowp = procs_by_id.get(incoming_id) if incoming_id else None
        if rowp is None:
            rowp = models.ModelVersionProcess(
                id=incoming_id,
                version_id=version.id,
            )
            db.add(rowp)
        keep_proc_ids.add(str(rowp.id))
        rowp.version_id = version.id
        rowp.process_id = process_id
        rowp.sequence_order = seqp
        rowp.notes = item.get("notes")
        base_meta_p = dict(getattr(rowp, "metadata_json", None) or {})
        base_meta_p.update(dict(item.get("metadata_json") or {}))
        base_meta_p.update(meta_line)
        rowp.metadata_json = _json_safe(base_meta_p)

    if keep_proc_ids:
        db.query(models.ModelVersionProcess).filter(
            models.ModelVersionProcess.version_id == version.id,
            ~models.ModelVersionProcess.id.in_(list(keep_proc_ids)),
        ).delete(synchronize_session=False)
    else:
        db.query(models.ModelVersionProcess).filter(
            models.ModelVersionProcess.version_id == version.id
        ).delete(synchronize_session=False)

    # Persist lightweight UI stats for version list (so refresh won't lose it).
    # This is a UI convenience cache, not an accounting ledger.
    try:
        material_cost = Decimal("0")
        labor_cost = Decimal("0")
        qty = _decimal(sample.get("quantity"), Decimal("1"))
        for item in materials:
            meta_line = dict(item.get("metadata_json") or {})
            unit_price = _decimal(meta_line.get("bom_unit_price"), None)
            if unit_price is None:
                continue
            used_qty = _decimal(item.get("sample_used_quantity"), Decimal("0"))
            loss = _decimal(item.get("loss_rate"), Decimal("0"))
            material_cost += used_qty * (Decimal("1") + loss / Decimal("100")) * unit_price

        for item in processes:
            meta_line = dict(item.get("metadata_json") or {})
            cost_type = str(item.get("cost_type") or meta_line.get("cost_type") or "time")
            if cost_type == "piece":
                piece_rate = _decimal(item.get("piece_rate") or meta_line.get("piece_rate"), None)
                if piece_rate is None:
                    continue
                labor_cost += piece_rate * (qty if qty > 0 else Decimal("1"))
                continue
            minutes = _decimal(item.get("sample_minutes") or meta_line.get("sample_minutes"), Decimal("0"))
            rate = _decimal(item.get("rate_per_minute") or meta_line.get("rate_per_minute"), None)
            if rate is None:
                continue
            labor_cost += minutes * rate

        manufacturing_fee = Decimal("0.3") * (material_cost + labor_cost)
        total_cost = material_cost + labor_cost + manufacturing_fee
        meta = version.metadata_json or {}
        ui = dict(meta.get("ui_stats") or {}) if isinstance(meta.get("ui_stats"), dict) else {}
        ui.update(
            {
                "material_count": len(materials),
                "process_count": len(processes),
                "material_cost": str(material_cost),
                "labor_cost": str(labor_cost),
                "manufacturing_fee": str(manufacturing_fee),
                "total_cost": str(total_cost),
            }
        )
        meta["ui_stats"] = ui
        version.metadata_json = _json_safe(meta)
    except Exception:
        # Never block saving lines due to UI stats calculation.
        pass

    db.commit()


def _replace_modules(db: Session, model: models.ProductModel, modules_payload: List[Dict[str, Any]]) -> None:
    db.query(models.ModelProcessModule).filter(models.ModelProcessModule.model_id == model.id).delete(
        synchronize_session=False
    )
    for idx, payload in enumerate(modules_payload):
        module_id = payload["module_id"]
        module = (
            db.query(models.ProcessModule)
            .filter(models.ProcessModule.id == module_id, models.ProcessModule.is_archived.is_(False))
            .one_or_none()
        )
        if not module:
            raise ValueError("Referenced process module not found")
        order = payload.get("sequence_order")
        if order is None:
            order = idx
        db.add(
            models.ModelProcessModule(
                model_id=model.id,
                module_id=module.id,
                sequence_order=order,
                notes=payload.get("notes"),
                metadata_json=payload.get("metadata_json") or {},
            )
        )


def create_model(
    db: Session,
    *,
    model_code: str | None,
    model_name: str,
    description: Optional[str],
    category: Optional[str],
    calc_mode: Optional[str],
    fixed_price: Optional[Decimal],
    status: Optional[str],
    tags: Optional[List[str]],
    standard_width_mm: Optional[Decimal],
    standard_height_mm: Optional[Decimal],
    unit_of_measure: Optional[str],
    metadata: Optional[Dict[str, Any]],
    modules: Optional[List[Dict[str, Any]]] = None,
) -> models.ProductModel:
    if not model_code:
        # auto-generate short code (A-Z + 1-9), length 3
        from . import code_generator_service  # local import to avoid cycles

        model_code = code_generator_service.generate_random_code(db, kind="product_model", length=3)
    model = models.ProductModel(
        model_code=model_code,
        model_name=model_name,
        description=description,
        category=category,
        calc_mode=calc_mode or "ratio",
        fixed_price=fixed_price,
        status=status or "draft",
        tags=tags or [],
        standard_width_mm=standard_width_mm,
        standard_height_mm=standard_height_mm,
        unit_of_measure=unit_of_measure,
        metadata_json=metadata or {},
    )
    db.add(model)
    db.flush()
    if modules is not None:
        _replace_modules(db, model, modules)
    # Create an initial draft version so UI can immediately work in version dimension.
    # Default is sample for backward compatibility, but if entry_context indicates standard,
    # create a standard draft as the initial version to avoid "standard model shows up in sample list".
    meta0 = model.metadata_json or {}
    entry_ctx = str(meta0.get("entry_context") or "").strip().lower()
    initial_kind = "standard" if entry_ctx == "standard" else "sample"
    v = create_model_version(db, model=model, version_kind=initial_kind, metadata=None, commit=False)
    meta = model.metadata_json or {}
    meta["current_draft_version_id"] = v.id
    model.metadata_json = meta
    db.commit()
    db.refresh(model)
    return model


def create_model_version(
    db: Session,
    *,
    model: models.ProductModel,
    version_kind: str,
    metadata: Optional[Dict[str, Any]],
    commit: bool = True,
) -> models.ProductModelVersion:
    kind = (version_kind or "sample").strip().lower()
    if kind not in ("sample", "standard"):
        raise ValueError("version_kind must be one of: sample, standard")

    model_meta = model.metadata_json or {}
    sample, standard = _extract_sample_and_standard(model)
    # Standard version spec is always 1m×1m as baseline.
    if kind == "standard":
        standard = {
            "width_mm": Decimal("1000"),
            "height_mm": Decimal("1000"),
            "quantity": Decimal("1"),
            "unit_label": str((standard.get("unit_label") if isinstance(standard, dict) else None) or model.unit_of_measure or "幅"),
        }

    version_meta: Dict[str, Any] = {}
    if isinstance(metadata, dict):
        version_meta.update(metadata)
    if "placeholder_mappings" not in version_meta:
        pm = model_meta.get("placeholder_mappings")
        version_meta["placeholder_mappings"] = pm if isinstance(pm, list) else []
    version_meta.setdefault("sample", sample)
    version_meta.setdefault("standard", standard)
    version_meta.setdefault("calc_mode", model.calc_mode)
    version_meta.setdefault("fixed_price", model.fixed_price)

    v = models.ProductModelVersion(
        model_id=model.id,
        version_kind=kind,
        version_status="draft",
        metadata_json=_json_safe(version_meta),
    )
    db.add(v)
    db.flush()

    # Assign a readable draft label immediately (temporary identifier shown in UI).
    # Example: K7Q-SAMPLE-20251219-01 / K7Q-STANDARD-20251219-01
    if not v.version_label:
        now = datetime.now(timezone.utc)
        seq = (
            db.query(models.ProductModelVersion)
            .filter(
                models.ProductModelVersion.model_id == model.id,
                models.ProductModelVersion.version_kind == kind,
            )
            .count()
        )
        v.version_label = f"{model.model_code}-{kind.upper()}-{now.strftime('%Y%m%d')}-{seq:02d}"

    # Copy module links from model to version (version may later diverge).
    for link in list_model_modules(db, model.id):
        db.add(
            models.ModelVersionModule(
                version_id=v.id,
                module_id=link.module_id,
                sequence_order=link.sequence_order,
                notes=link.notes,
                metadata_json=link.metadata_json or {},
            )
        )

    if commit:
        db.commit()
        db.refresh(v)
    return v


def _normalize_recognition_keyword(s: str) -> str:
    return "".join(str(s or "").strip().split()).upper()


def _extract_recognition_keywords(meta: Dict[str, Any]) -> List[str]:
    raw = meta.get("recognition_keywords")
    if not isinstance(raw, list):
        return []
    out: List[str] = []
    for x in raw:
        if x is None:
            continue
        k = _normalize_recognition_keyword(str(x))
        if not k:
            continue
        out.append(k)
    # de-dup while keeping order
    seen: set[str] = set()
    uniq: List[str] = []
    for k in out:
        if k in seen:
            continue
        seen.add(k)
        uniq.append(k)
    return uniq


def _validate_recognition_keywords_uniqueness(
    db: Session, *, current_model_id: str, keywords: List[str]
) -> Dict[str, str]:
    """
    Return conflicts mapping: keyword -> other model_code (or id).
    Only check against models that have published standard versions.
    """
    if not keywords:
        return {}
    rows = (
        db.query(models.ProductModel)
        .join(models.ProductModelVersion, models.ProductModelVersion.model_id == models.ProductModel.id)
        .filter(
            models.ProductModel.is_archived.is_(False),
            models.ProductModel.id != current_model_id,
            models.ProductModelVersion.version_kind == "standard",
            models.ProductModelVersion.version_status == "published",
            models.ProductModelVersion.is_archived.is_(False),
        )
        .all()
    )
    used: Dict[str, str] = {}
    for m in rows:
        meta0 = m.metadata_json or {}
        for k in _extract_recognition_keywords(meta0):
            used[k] = str(m.model_code or m.id)
    conflicts: Dict[str, str] = {}
    for k in keywords:
        if k in used:
            conflicts[k] = used[k]
    return conflicts


def update_model(
    db: Session,
    model: models.ProductModel,
    *,
    model_name: Optional[str],
    description: Optional[str],
    category: Optional[str],
    calc_mode: Optional[str],
    fixed_price: Optional[Decimal],
    status: Optional[str],
    tags: Optional[List[str]],
    standard_width_mm: Optional[Decimal],
    standard_height_mm: Optional[Decimal],
    unit_of_measure: Optional[str],
    metadata: Optional[Dict[str, Any]],
    modules: Optional[List[Dict[str, Any]]] = None,
) -> models.ProductModel:
    if model_name is not None:
        model.model_name = model_name
    if description is not None:
        model.description = description
    if category is not None:
        model.category = category
    if calc_mode is not None:
        model.calc_mode = calc_mode
    if fixed_price is not None or calc_mode is not None:
        # fixed_price is only meaningful for fixed mode; schemas already normalize it.
        model.fixed_price = fixed_price
    if status is not None:
        model.status = status
    if tags is not None:
        model.tags = tags
    if standard_width_mm is not None:
        model.standard_width_mm = standard_width_mm
    if standard_height_mm is not None:
        model.standard_height_mm = standard_height_mm
    if unit_of_measure is not None:
        model.unit_of_measure = unit_of_measure
    if metadata is not None:
        # Validate recognition keywords uniqueness among models that have published standard versions.
        # This is used by SKU auto-bind; ambiguous keywords must be rejected at save-time.
        new_keywords = _extract_recognition_keywords(metadata)
        if new_keywords:
            conflicts_map = _validate_recognition_keywords_uniqueness(db, current_model_id=model.id, keywords=new_keywords)
            if conflicts_map:
                conflicts = ", ".join(sorted(conflicts_map.keys()))
                raise ValueError(f"型号识别关键词冲突（需全局唯一）：{conflicts}")
        model.metadata_json = metadata
    if modules is not None:
        _replace_modules(db, model, modules)
    db.commit()
    db.refresh(model)
    return model


def _get_virtual_kind(virtual: models.VirtualMaterial) -> str:
    meta = virtual.metadata_json or {}
    kind = meta.get("virtual_kind")
    return kind if kind in ("recipe", "kit", "placeholder") else "kit"


def _collect_placeholders_for_modules(db: Session, module_ids: List[str]) -> List[models.VirtualMaterial]:
    if not module_ids:
        return []
    rows = (
        db.query(models.ProcessModuleMaterial.material_ref_id)
        .filter(
            models.ProcessModuleMaterial.is_archived.is_(False),
            models.ProcessModuleMaterial.module_id.in_(module_ids),
            models.ProcessModuleMaterial.material_kind == "virtual",
        )
        .all()
    )
    virtual_ids = sorted({row[0] for row in rows if row and row[0]})
    if not virtual_ids:
        return []
    virtuals = (
        db.query(models.VirtualMaterial)
        .filter(models.VirtualMaterial.id.in_(virtual_ids), models.VirtualMaterial.is_archived.is_(False))
        .all()
    )
    return [v for v in virtuals if _get_virtual_kind(v) == "placeholder"]


def _collect_base_material_ids_for_modules(
    db: Session,
    *,
    module_ids: List[str],
    placeholder_mapping_by_virtual_id: Dict[str, Dict[str, Any]] | None = None,
) -> List[str]:
    """
    Collect base material IDs that can be used as variant rule sources.
    Includes:
    - process_module_materials material_kind in (real, bom)
    - placeholder virtual materials mapped to (real, bom) targets
    """
    if not module_ids:
        return []
    mapping = placeholder_mapping_by_virtual_id or {}
    rows = (
        db.query(
            models.ProcessModuleMaterial.material_kind,
            models.ProcessModuleMaterial.material_ref_id,
        )
        .filter(
            models.ProcessModuleMaterial.is_archived.is_(False),
            models.ProcessModuleMaterial.module_id.in_(module_ids),
        )
        .all()
    )
    ids: List[str] = []
    for kind, ref_id in rows:
        if not ref_id:
            continue
        if kind in ("real", "bom"):
            ids.append(str(ref_id))
            continue
        if kind == "virtual":
            vm = db.get(models.VirtualMaterial, ref_id)
            if not vm or vm.is_archived:
                continue
            if _get_virtual_kind(vm) != "placeholder":
                continue
            m = mapping.get(vm.id)
            if not m:
                continue
            rk = str(m.get("replacement_kind") or "").strip()
            rid = str(m.get("replacement_ref_id") or "").strip()
            if rk in ("real", "bom") and rid:
                ids.append(rid)
    # stable unique
    return sorted(set(ids))


def validate_can_activate(db: Session, model: models.ProductModel) -> List[str]:
    errors: List[str] = []
    # If model ledger lines exist, activation should validate against the ledger,
    # not against module placeholders. This supports the workflow:
    # - modules may contain placeholder virtual materials for templating
    # - model lines must have placeholders replaced by fallback materials before activation
    model_materials = list_model_material_lines(db, model.id)
    model_processes = list_model_process_lines(db, model.id)
    if model_materials or model_processes:
        base_material_ids: List[str] = []
        for row in model_materials:
            kind = str(row.material_type or "").strip()
            if kind in ("real", "bom"):
                if row.material_ref_id:
                    base_material_ids.append(str(row.material_ref_id))
                continue
            if kind == "virtual":
                vm = db.get(models.VirtualMaterial, row.material_ref_id) if row.material_ref_id else None
                if vm and not vm.is_archived and _get_virtual_kind(vm) == "placeholder":
                    errors.append("模型清单仍包含占位型虚拟物料：请先完成占位符替换并保存清单后再启用")
        # Variant rule validation uses model ledger base materials as sources
        errors.extend(
            variant_rule_service.validate_rules_for_model_activation(
                db, model=model, base_material_ids=sorted(set(base_material_ids))
            )
        )
        return errors

    module_links = list_model_modules(db, model.id)
    module_ids = [link.module_id for link in module_links]
    placeholders = _collect_placeholders_for_modules(db, module_ids)
    if not placeholders:
        # Still validate variant rules against base materials (real/bom) even if no placeholders.
        base_material_ids = _collect_base_material_ids_for_modules(db, module_ids=module_ids)
        errors.extend(
            variant_rule_service.validate_rules_for_model_activation(
                db, model=model, base_material_ids=base_material_ids
            )
        )
        return errors

    meta = model.metadata_json or {}
    mappings = meta.get("placeholder_mappings") or []
    if not isinstance(mappings, list):
        mappings = []
    mapping_by_placeholder: Dict[str, Dict[str, Any]] = {}
    for item in mappings:
        if not isinstance(item, dict):
            continue
        pid = str(item.get("placeholder_virtual_id") or "").strip()
        if not pid:
            continue
        mapping_by_placeholder[pid] = item

    for placeholder in placeholders:
        ph_id = placeholder.id
        ph_meta = placeholder.metadata_json or {}
        ph_symbol = str(ph_meta.get("placeholder_symbol") or placeholder.name or placeholder.virtual_code)
        constraint_category = str(ph_meta.get("constraint_category") or "").strip()
        ph_unit = _normalize_unit(placeholder.unit)

        mapping = mapping_by_placeholder.get(ph_id)
        if not mapping:
            errors.append(f"缺少占位符映射：{ph_symbol}（virtual_id={ph_id}）")
            continue

        kind = str(mapping.get("replacement_kind") or "").strip()
        ref_id = str(mapping.get("replacement_ref_id") or "").strip()
        if kind not in ("real", "bom", "virtual") or not ref_id:
            errors.append(f"占位符映射不完整：{ph_symbol}（需要 replacement_kind + replacement_ref_id）")
            continue

        if kind in ("real", "bom"):
            material = (
                db.query(models.Material)
                .filter(models.Material.id == ref_id, models.Material.is_archived.is_(False))
                .one_or_none()
            )
            if not material or not material.is_active:
                errors.append(f"占位符 {ph_symbol} 映射的真实物料不存在或未启用")
                continue
            if kind == "bom" and not material.is_bom_material:
                errors.append(f"占位符 {ph_symbol} 映射为 BOM 物料，但目标物料未标记 BOM")
            if constraint_category and (material.category or "") != constraint_category:
                errors.append(
                    f"占位符 {ph_symbol} 约束分类={constraint_category}，但目标物料分类={material.category or '-'}"
                )
            target_unit = _normalize_unit(material.unit)
            if ph_unit and target_unit and ph_unit != target_unit:
                errors.append(f"占位符 {ph_symbol} 单位={ph_unit}，但目标物料单位={material.unit or '-'}")
        else:
            virtual = (
                db.query(models.VirtualMaterial)
                .filter(models.VirtualMaterial.id == ref_id, models.VirtualMaterial.is_archived.is_(False))
                .one_or_none()
            )
            if not virtual or virtual.status != "active":
                errors.append(f"占位符 {ph_symbol} 映射的虚拟物料不存在或未启用")
                continue
            if _get_virtual_kind(virtual) == "placeholder":
                errors.append(f"占位符 {ph_symbol} 不允许映射到另一个占位型虚拟物料")
            target_unit = _normalize_unit(virtual.unit)
            if ph_unit and target_unit and ph_unit != target_unit:
                errors.append(f"占位符 {ph_symbol} 单位={ph_unit}，但目标虚拟物料单位={virtual.unit or '-'}")

    # Variant rule validation (requires placeholder mappings resolved to base material set)
    base_material_ids = _collect_base_material_ids_for_modules(
        db, module_ids=module_ids, placeholder_mapping_by_virtual_id=mapping_by_placeholder
    )
    errors.extend(
        variant_rule_service.validate_rules_for_model_activation(
            db, model=model, base_material_ids=base_material_ids
        )
    )
    return errors


def set_model_status(db: Session, model: models.ProductModel, status: str) -> models.ProductModel:
    model.status = status
    db.commit()
    db.refresh(model)
    return model


def _decimal(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    if value is None:
        return default
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception:  # noqa: BLE001
        return default


def _normalize_unit(value: Any) -> str:
    """
    Normalize unit tokens for comparisons.
    Mirrors frontend `normalizeUnit` semantics to avoid false mismatches like 'm' vs '米'.
    """
    if value is None:
        return ""
    v = str(value).strip().replace(" ", "")
    if not v:
        return ""
    # Area
    if v in ("平米", "㎡", "平方", "平方米", "m²", "M2", "m2", "米²", "米2"):
        return "平米"
    # Length
    if v in ("米", "m", "M"):
        return "米"
    # Count
    if v in ("个", "pcs", "PCS", "piece", "Piece"):
        return "个"
    # Set
    if v in ("套", "set", "SET"):
        return "套"
    return v


def _infer_unit_to_mm(value: Decimal, unit: str | None) -> Decimal:
    u = (unit or "").strip().lower()
    if u in ("mm", "毫米"):
        return value
    if u in ("cm", "厘米"):
        return value * Decimal("10")
    if u in ("m", "米"):
        return value * Decimal("1000")
    # Heuristic when unit omitted:
    # - <= 20: treat as meters (e.g. 1.2x0.8)
    # - <= 200: treat as centimeters (e.g. 120x80)
    # - otherwise: treat as millimeters (e.g. 1200x800)
    if value <= Decimal("20"):
        return value * Decimal("1000")
    if value <= Decimal("200"):
        return value * Decimal("10")
    return value


def _round_by_step(value: Decimal, *, step: Decimal, mode: str) -> Decimal:
    if step <= 0:
        return value
    q = value / step
    if mode == "ceil":
        # avoid importing math for Decimal; use quantize tricks
        i = q.to_integral_value(rounding="ROUND_CEILING")
        return i * step
    if mode == "floor":
        i = q.to_integral_value(rounding="ROUND_FLOOR")
        return i * step
    i = q.to_integral_value(rounding="ROUND_HALF_UP")
    return i * step


def _derive_base_from_total(
    *,
    total: Decimal,
    fixed: Decimal,
    measure_qty: Decimal,
    coverage_ratio: Decimal,
) -> Decimal:
    mq = max(Decimal("0"), measure_qty)
    cov = max(Decimal("0"), coverage_ratio)
    if mq <= 0 or cov <= 0:
        return Decimal("0")
    num = total - fixed
    if num <= 0:
        return Decimal("0")
    return num / (mq * cov)


def derive_standard_version(
    db: Session,
    *,
    source_sample_version: models.ProductModelVersion,
    target_mode: str,
    target_standard_version_id: str | None,
    apply_to: str,
) -> tuple[models.ProductModelVersion, dict]:
    """
    Derive a standard (1000×1000×1) version from a sample version.

    Rules:
    - Source must be version_kind=sample
    - Target standard version is created or overwritten (draft only)
    - Output fields:
      - materials: base_quantity + metadata_json.fixed_quantity/coverage_ratio (+ trace fields)
      - processes: metadata_json.base_minutes/unit_minutes (+ trace fields)
    - Derive templates live in source sample version lines' metadata_json.derive_template
    """
    if (source_sample_version.version_kind or "") != "sample":
        raise ValueError("仅允许从打样版本（sample）推导标准版本（standard）")
    if source_sample_version.is_archived:
        raise ValueError("源打样版本已归档，无法推导")

    model = db.get(models.ProductModel, source_sample_version.model_id)
    if not model or model.is_archived:
        raise ValueError("Product model not found")

    mode = (target_mode or "create_new").strip()
    if mode not in ("create_new", "overwrite_draft"):
        raise ValueError("target_mode must be one of: create_new, overwrite_draft")
    which = (apply_to or "both").strip()
    if which not in ("materials", "processes", "both"):
        raise ValueError("apply_to must be one of: materials, processes, both")

    # Resolve/create target standard version
    created = False
    overwritten = False
    if mode == "create_new":
        target = create_model_version(db, model=model, version_kind="standard", metadata=None, commit=False)
        created = True
    else:
        if not target_standard_version_id:
            raise ValueError("overwrite_draft 需要 target_standard_version_id")
        target = get_model_version(db, target_standard_version_id)
        if not target or target.model_id != model.id:
            raise ValueError("目标标准版本不存在")
        if (target.version_kind or "") != "standard":
            raise ValueError("目标版本不是 standard")
        if (target.version_status or "") != "draft":
            raise ValueError("仅允许覆盖 draft 标准版本")
        overwritten = True

    # Force standard spec
    tmeta = target.metadata_json or {}
    smeta = source_sample_version.metadata_json or {}
    sample_spec = (smeta.get("sample") if isinstance(smeta.get("sample"), dict) else {}) or {}
    std_unit_label = None
    s_std = smeta.get("standard")
    if isinstance(s_std, dict):
        std_unit_label = s_std.get("unit_label")
    std_spec = {
        "width_mm": Decimal("1000"),
        "height_mm": Decimal("1000"),
        "quantity": Decimal("1"),
        "unit_label": str(std_unit_label or model.unit_of_measure or "幅"),
    }
    tmeta["standard"] = _json_safe(std_spec)
    tmeta["sample"] = _json_safe(sample_spec)
    tmeta["derived_from_version_id"] = source_sample_version.id
    tmeta["derived_at"] = datetime.now(timezone.utc).isoformat()
    target.metadata_json = _json_safe(tmeta)

    # Prepare measures
    sample_width = _decimal(sample_spec.get("width_mm"), Decimal("1000"))
    sample_height = _decimal(sample_spec.get("height_mm"), Decimal("1000"))
    sample_qty = _decimal(sample_spec.get("quantity"), Decimal("1"))
    standard_measure_spec = {"width_mm": Decimal("1000"), "height_mm": Decimal("1000"), "quantity": Decimal("1")}

    stats = {"materials": {"total": 0, "derived": 0, "warnings": 0}, "processes": {"total": 0, "derived": 0, "warnings": 0}}

    if which in ("materials", "both"):
        db.query(models.ModelVersionMaterial).filter(models.ModelVersionMaterial.version_id == target.id).delete(
            synchronize_session=False
        )
    if which in ("processes", "both"):
        db.query(models.ModelVersionProcess).filter(models.ModelVersionProcess.version_id == target.id).delete(
            synchronize_session=False
        )

    # Copy modules (ensure standard version inherits module bindings)
    if created:
        # create_model_version(commit=False) already copied model modules; overwrite_draft keeps existing.
        pass

    if which in ("materials", "both"):
        mats = list_version_material_lines(db, source_sample_version.id)
        for idx, row in enumerate(mats, 1):
            stats["materials"]["total"] += 1
            method = str(row.calculation_method or "count")
            meta = row.metadata_json or {}
            tmpl = meta.get("derive_template") if isinstance(meta.get("derive_template"), dict) else {}
            # inputs
            sample_measure = _measure_qty(method, width_mm=sample_width, height_mm=sample_height, quantity=sample_qty)
            std_measure = _measure_qty(method, **standard_measure_spec)
            try:
                sample_used = _decimal(meta.get("sample_used_quantity"), None)  # type: ignore[arg-type]
            except Exception:
                sample_used = None
            if sample_used is None:
                sample_used = sample_measure * _decimal(row.base_quantity, Decimal("0"))

            cov = _decimal(tmpl.get("coverage_ratio"), _decimal(meta.get("coverage_ratio"), Decimal("1")))
            fixed = _decimal(tmpl.get("fixed_quantity"), _decimal(meta.get("fixed_quantity"), Decimal("0")))
            coeff = tmpl.get("coefficient")
            coeff_d = _decimal(coeff, None) if coeff is not None else None  # type: ignore[arg-type]
            calibrate = bool(tmpl.get("calibrate_from_sample"))
            if coeff_d is None and calibrate:
                coeff_d = _derive_base_from_total(total=sample_used, fixed=fixed, measure_qty=sample_measure, coverage_ratio=cov)
            if coeff_d is None:
                # fallback: derive from sample_used regardless of template
                coeff_d = _derive_base_from_total(total=sample_used, fixed=fixed, measure_qty=sample_measure, coverage_ratio=cov)

            # compute standard total then apply min/max/round
            total_std = fixed + (std_measure * coeff_d * cov)
            min_total = tmpl.get("min_total")
            max_total = tmpl.get("max_total")
            if min_total is not None:
                total_std = max(total_std, _decimal(min_total, Decimal("0")))
            if max_total is not None:
                total_std = min(total_std, _decimal(max_total, total_std))
            rounding = tmpl.get("rounding")
            if isinstance(rounding, dict) and rounding.get("step") is not None:
                step = _decimal(rounding.get("step"), Decimal("1"))
                mode2 = str(rounding.get("mode") or "round")
                total_std = _round_by_step(total_std, step=step, mode=mode2)

            # recompute base from constrained total
            coeff_out = _derive_base_from_total(total=total_std, fixed=fixed, measure_qty=std_measure, coverage_ratio=cov)
            out_meta = dict(meta)
            out_meta["fixed_quantity"] = str(fixed)
            out_meta["coverage_ratio"] = str(cov)
            # For standard version UX: make computed totals explicit.
            # - `standard_used_quantity` should reflect the derived standard baseline (1000×1000×1).
            # - Many UI paths historically read/display `sample_used_quantity` as the primary "本品用量",
            #   so we also set it to the standard baseline here to avoid “推导后看起来没计算”.
            # - Keep the original sample total for traceability.
            out_meta["source_sample_used_quantity"] = str(sample_used)
            out_meta["standard_used_quantity"] = str(total_std)
            out_meta["sample_used_quantity"] = str(total_std)
            out_meta["derived_from_version_id"] = source_sample_version.id
            out_meta["derived_at"] = tmeta["derived_at"]
            out_meta["derive_template"] = tmpl
            stats["materials"]["derived"] += 1
            db.add(
                models.ModelVersionMaterial(
                    version_id=target.id,
                    material_type=row.material_type,
                    material_ref_id=row.material_ref_id,
                    material_code=row.material_code,
                    material_name=row.material_name,
                    unit_of_measure=row.unit_of_measure,
                    calculation_method=method,
                    base_quantity=coeff_out,
                    loss_rate=row.loss_rate,
                    sequence_order=idx,
                    notes=row.notes,
                    metadata_json=_json_safe(out_meta),
                )
            )

    if which in ("processes", "both"):
        procs = list_version_process_lines(db, source_sample_version.id)
        for idx, row in enumerate(procs, 1):
            stats["processes"]["total"] += 1
            meta = row.metadata_json or {}
            tmpl = meta.get("derive_template") if isinstance(meta.get("derive_template"), dict) else {}
            pricing_method = str(meta.get("pricing_method") or "count")
            measure_method = pricing_method if pricing_method in ("fixed", "count", "area", "perimeter", "width", "height") else "count"
            sample_measure = _measure_qty(
                measure_method if measure_method != "fixed" else "count",
                width_mm=sample_width,
                height_mm=sample_height,
                quantity=sample_qty,
            )
            std_measure = _measure_qty(measure_method if measure_method != "fixed" else "count", **standard_measure_spec)

            try:
                sample_minutes = _decimal(meta.get("sample_minutes"), None)  # type: ignore[arg-type]
            except Exception:
                sample_minutes = None
            base_min = _decimal(tmpl.get("base_minutes"), _decimal(meta.get("base_minutes"), Decimal("0")))
            coeff = tmpl.get("coefficient")
            unit_min = _decimal(coeff, None) if coeff is not None else None  # type: ignore[arg-type]
            calibrate = bool(tmpl.get("calibrate_from_sample"))
            if sample_minutes is None:
                # try to compute from existing base/unit and sample measure
                sample_minutes = base_min + _decimal(meta.get("unit_minutes"), Decimal("0")) * sample_measure
            if unit_min is None and calibrate:
                # sample_minutes = base + unit*sample_measure
                if sample_measure > 0:
                    unit_min = max(Decimal("0"), (sample_minutes - base_min) / sample_measure)
                else:
                    unit_min = Decimal("0")
            if unit_min is None:
                unit_min = _decimal(meta.get("unit_minutes"), Decimal("0"))

            total_std = base_min + unit_min * std_measure
            min_total = tmpl.get("min_total")
            max_total = tmpl.get("max_total")
            if min_total is not None:
                total_std = max(total_std, _decimal(min_total, Decimal("0")))
            if max_total is not None:
                total_std = min(total_std, _decimal(max_total, total_std))
            rounding = tmpl.get("rounding")
            if isinstance(rounding, dict) and rounding.get("step") is not None:
                step = _decimal(rounding.get("step"), Decimal("1"))
                mode2 = str(rounding.get("mode") or "round")
                total_std = _round_by_step(total_std, step=step, mode=mode2)

            # keep base_minutes, recompute unit_minutes from constrained total if possible
            if std_measure > 0:
                unit_out = max(Decimal("0"), (total_std - base_min) / std_measure)
            else:
                unit_out = Decimal("0")

            out_meta = dict(meta)
            out_meta["base_minutes"] = str(base_min)
            out_meta["unit_minutes"] = str(unit_out)
            # For standard version UX: expose derived totals explicitly.
            # Keep original sample total for traceability.
            out_meta["source_sample_minutes"] = str(sample_minutes)
            out_meta["standard_minutes"] = str(total_std)
            out_meta["sample_minutes"] = str(total_std)
            out_meta["derived_from_version_id"] = source_sample_version.id
            out_meta["derived_at"] = tmeta["derived_at"]
            out_meta["derive_template"] = tmpl
            stats["processes"]["derived"] += 1
            db.add(
                models.ModelVersionProcess(
                    version_id=target.id,
                    process_id=row.process_id,
                    sequence_order=idx,
                    notes=row.notes,
                    metadata_json=_json_safe(out_meta),
                )
            )

    db.add(target)
    db.commit()
    db.refresh(target)
    return target, stats

def parse_sku_code(sku_code: str) -> Dict[str, Any]:
    """
    Best-effort SKU parser:
    - model_code: leading [A-Z0-9]{3} (or first segment)
    - version_token: optional segment right after model_code
    - dimensions: token like 1000x800 / 1.2x0.8 / 120×80 (supports mm/cm/m)
    - variant_tokens: remaining segments after dimensions
    """
    raw = (sku_code or "").strip()
    s = re.sub(r"\s+", "", raw)
    s_norm = s.upper()
    parts = [p for p in re.split(r"[-_]", s_norm) if p]

    model_code = ""
    if parts:
        # Prefer strict 3-char model_code
        m = re.match(r"^[A-Z0-9]{3}$", parts[0])
        model_code = parts[0] if m else parts[0][:3]

    version_token: str | None = None
    width_mm: Decimal | None = None
    height_mm: Decimal | None = None
    dim_token_index: int | None = None

    # Find dimension token
    dim_re = re.compile(
        r"(?P<w>\d+(?:\.\d+)?)(?P<uw>MM|CM|M|毫米|厘米|米)?[X×*](?P<h>\d+(?:\.\d+)?)(?P<uh>MM|CM|M|毫米|厘米|米)?"
    )
    for idx, token in enumerate(parts):
        m = dim_re.search(token)
        if not m:
            continue
        w = Decimal(m.group("w"))
        h = Decimal(m.group("h"))
        uw = m.group("uw")
        uh = m.group("uh")
        width_mm = _infer_unit_to_mm(w, uw)
        height_mm = _infer_unit_to_mm(h, uh or uw)
        dim_token_index = idx
        break

    # Alternate: W1000H800 / 宽1000高800
    if width_mm is None or height_mm is None:
        m = re.search(r"W(?P<w>\d+(?:\.\d+)?)(MM|CM|M)?H(?P<h>\d+(?:\.\d+)?)(MM|CM|M)?", s_norm)
        if m:
            w = Decimal(m.group("w"))
            h = Decimal(m.group("h"))
            width_mm = _infer_unit_to_mm(w, None)
            height_mm = _infer_unit_to_mm(h, None)

    # Infer version token and variant tokens
    if parts:
        if len(parts) >= 2:
            # if second segment looks like version (V01/STD/20251219 etc), capture it
            cand = parts[1]
            if re.match(r"^(V\d+|STD|STANDARD|SAMPLE|\d{6,})$", cand):
                version_token = cand
        variant_tokens: List[str] = []
        if dim_token_index is not None:
            variant_tokens = parts[dim_token_index + 1 :]
        else:
            # If no dimension found, treat tail (after first segment and optional version) as variants
            start = 2 if version_token else 1
            variant_tokens = parts[start:]
    else:
        variant_tokens = []

    return {
        "raw": raw,
        "normalized": s_norm,
        "model_code": model_code,
        "version_token": version_token,
        "width_mm": str(width_mm) if width_mm is not None else None,
        "height_mm": str(height_mm) if height_mm is not None else None,
        "variant_tokens": variant_tokens,
    }


def get_active_sku_binding(db: Session, sku_code: str) -> Optional[models.SkuModelVersionMapping]:
    sku = (sku_code or "").strip()
    if not sku:
        return None
    return (
        db.query(models.SkuModelVersionMapping)
        .filter(
            models.SkuModelVersionMapping.sku_code == sku,
            models.SkuModelVersionMapping.is_active.is_(True),
            models.SkuModelVersionMapping.is_archived.is_(False),
        )
        .order_by(models.SkuModelVersionMapping.created_at.desc())
        .first()
    )


def get_latest_published_standard_version_for_model_code(
    db: Session, model_code: str
) -> Optional[models.ProductModelVersion]:
    code = (model_code or "").strip()
    if not code:
        return None
    model = (
        db.query(models.ProductModel)
        .filter(
            models.ProductModel.model_code == code,
            models.ProductModel.is_archived.is_(False),
        )
        .one_or_none()
    )
    if not model:
        return None
    return (
        db.query(models.ProductModelVersion)
        .filter(
            models.ProductModelVersion.model_id == model.id,
            models.ProductModelVersion.version_kind == "standard",
            models.ProductModelVersion.version_status == "published",
            models.ProductModelVersion.is_archived.is_(False),
        )
        # SQLite doesn't support "NULLS LAST"; use (published_at IS NULL) ordering for portability.
        .order_by(
            models.ProductModelVersion.published_at.is_(None).asc(),
            models.ProductModelVersion.published_at.desc(),
            models.ProductModelVersion.created_at.desc(),
        )
        .first()
    )


def _derive_bom_unit_price(material: models.Material) -> Optional[Decimal]:
    metadata = material.metadata_json or {}
    raw_price = metadata.get("bom_unit_price")
    if raw_price not in (None, ""):
        try:
            return Decimal(str(raw_price))
        except Exception:  # noqa: BLE001
            pass
    if material.unit_price is None or material.conversion_purchase_to_bom in (None, 0):
        return None
    try:
        unit_price = Decimal(str(material.unit_price))
        conversion = Decimal(str(material.conversion_purchase_to_bom))
        if conversion == 0:
            return None
        return unit_price / conversion
    except Exception:  # noqa: BLE001
        return None


def _measure_qty(method: str, *, width_mm: Decimal, height_mm: Decimal, quantity: Decimal) -> Decimal:
    q = max(Decimal("0"), _decimal(quantity, Decimal("0")))
    w = max(Decimal("0"), _decimal(width_mm, Decimal("0")))
    h = max(Decimal("0"), _decimal(height_mm, Decimal("0")))
    if method == "count":
        return q
    if method == "width":
        return (w / Decimal("1000")) * q
    if method == "height":
        return (h / Decimal("1000")) * q
    if method == "long_side":
        return (max(w, h) / Decimal("1000")) * q
    if method == "short_side":
        return (min(w, h) / Decimal("1000")) * q
    if method == "perimeter":
        return ((Decimal("2") * (w + h)) / Decimal("1000")) * q
    # area
    return ((w * h) / Decimal("1000000")) * q


def preview_model_cost(
    db: Session,
    model: models.ProductModel,
    *,
    width_mm: Decimal,
    height_mm: Decimal,
    quantity: Decimal,
    sku_hint: str | None = None,
) -> Dict[str, Any]:
    """
    Prefer model persisted lines (model_materials/model_processes) when present.
    Fallback to expanding modules when model lines are empty.
    Placeholder mappings are read from model.metadata_json.placeholder_mappings.
    """
    result: Dict[str, Any] = {
        "width_mm": width_mm,
        "height_mm": height_mm,
        "quantity": quantity,
        "material_lines": [],
        "labor_lines": [],
        "totals": {},
        "errors": [],
    }

    # fixed price mode: no module/material/process calculation required.
    if (model.calc_mode or "") == "fixed":
        fixed_price = _decimal(model.fixed_price, Decimal("0"))
        result["totals"] = {
            "material_cost": Decimal("0"),
            "labor_cost": Decimal("0"),
            "overhead_cost": Decimal("0"),
            "total_cost": fixed_price,
        }
        return result

    # If model lines exist, compute preview based on them (the model-layer "final ledger").
    # Important: placeholder virtual materials in the ledger must be resolved via placeholder_mappings
    # (otherwise pricing will be 0 and contradict the "must replace fallback material" rule).
    model_materials = list_model_material_lines(db, model.id)
    model_processes = list_model_process_lines(db, model.id)
    if model_materials or model_processes:
        material_cost_total = Decimal("0")
        labor_cost_total = Decimal("0")

        meta = model.metadata_json or {}
        mappings = meta.get("placeholder_mappings") or []
        mapping_by_placeholder: Dict[str, Dict[str, Any]] = {}
        if isinstance(mappings, list):
            for item in mappings:
                if not isinstance(item, dict):
                    continue
                pid = str(item.get("placeholder_virtual_id") or "").strip()
                if pid:
                    mapping_by_placeholder[pid] = item

        # Variant rules still apply on material_id (source_material_ref_id).
        rules = variant_rule_service.list_rules(db, model.id)
        active_rules = [r for r in rules if (r.status or "") == "active" and not r.is_archived]
        rules_by_source: Dict[str, List[models.ModelVariantRule]] = {}
        for r in active_rules:
            src = (r.source_material_ref_id or "").strip()
            if src:
                rules_by_source.setdefault(src, []).append(r)

        def _trigger_hit(rule: models.ModelVariantRule, *, area_m2: Decimal, perimeter_m: Decimal) -> bool:
            t = (rule.trigger_type or "").strip()
            v = (rule.trigger_value or "").strip() if rule.trigger_value is not None else ""
            if t == "sku_contains":
                return bool(sku_hint) and v != "" and v in str(sku_hint)
            if t == "area_gte":
                try:
                    return area_m2 >= Decimal(v)
                except Exception:  # noqa: BLE001
                    return False
            if t == "perimeter_gte":
                try:
                    return perimeter_m >= Decimal(v)
                except Exception:  # noqa: BLE001
                    return False
            return False

        def _apply_variant_to_line(line: Dict[str, Any], source_material_id: str, used_qty: Decimal, method: str) -> List[Dict[str, Any]]:
            nonlocal material_cost_total
            extra: List[Dict[str, Any]] = []
            candidates = rules_by_source.get(source_material_id) or []
            if not candidates:
                return extra
            area_m2 = _measure_qty("area", width_mm=width_mm, height_mm=height_mm, quantity=quantity)
            per_m = _measure_qty("perimeter", width_mm=width_mm, height_mm=height_mm, quantity=quantity)
            replace_rule: models.ModelVariantRule | None = None
            add_rules: List[models.ModelVariantRule] = []
            for rr in candidates:
                if not _trigger_hit(rr, area_m2=area_m2, perimeter_m=per_m):
                    continue
                if rr.action_type == "replace_material" and replace_rule is None:
                    replace_rule = rr
                elif rr.action_type == "add_material":
                    add_rules.append(rr)

            if replace_rule and replace_rule.target_material_ref_id:
                target = db.get(models.Material, replace_rule.target_material_ref_id)
                if target and not target.is_archived and target.is_active:
                    if line.get("total_cost") is not None:
                        material_cost_total -= _decimal(line["total_cost"], Decimal("0"))
                    price = _derive_bom_unit_price(target)
                    line["resolved_kind"] = "real"
                    line["resolved_ref_id"] = target.id
                    line["material_id"] = target.id
                    line["material_code"] = target.material_code
                    line["material_name"] = target.material_name
                    line["category"] = target.category
                    line["unit"] = target.unit
                    line["bom_unit_price"] = price
                    if price is None:
                        line["total_cost"] = None
                        line["warnings"].append(f"变体替换命中：{replace_rule.rule_name}（但目标无BOM单价）")
                    else:
                        line["total_cost"] = used_qty * price
                        material_cost_total += used_qty * price
                        line["warnings"].append(f"变体替换命中：{replace_rule.rule_name}")
                else:
                    line["warnings"].append(f"变体替换规则命中但目标物料不可用：{replace_rule.rule_name}")

            for ar in add_rules:
                if not ar.target_material_ref_id:
                    continue
                target = db.get(models.Material, ar.target_material_ref_id)
                if not target or target.is_archived or not target.is_active:
                    extra.append(
                        {
                            "module_id": "model",
                            "module_code": "MODEL",
                            "module_name": "模型清单",
                            "source_kind": "real",
                            "source_ref_id": source_material_id,
                            "resolved_kind": None,
                            "resolved_ref_id": None,
                            "material_id": None,
                            "material_code": None,
                            "material_name": None,
                            "category": None,
                            "calculation_method": method,
                            "base_quantity": Decimal("0"),
                            "loss_rate": Decimal("0"),
                            "used_quantity": Decimal("0"),
                            "unit": None,
                            "bom_unit_price": None,
                            "total_cost": None,
                            "warnings": [f"变体加料目标物料不可用：{ar.rule_name}"],
                        }
                    )
                    continue
                delta = _decimal(ar.quantity_delta, Decimal("0"))
                if delta <= 0:
                    continue
                measure_qty = _measure_qty(method, width_mm=width_mm, height_mm=height_mm, quantity=quantity)
                add_used = measure_qty * delta
                price = _derive_bom_unit_price(target)
                add_cost = (add_used * price) if price is not None else None
                if add_cost is not None:
                    material_cost_total += add_cost
                extra.append(
                    {
                        "module_id": "model",
                        "module_code": "MODEL",
                        "module_name": "模型清单",
                        "source_kind": "real",
                        "source_ref_id": source_material_id,
                        "resolved_kind": "real",
                        "resolved_ref_id": target.id,
                        "material_id": target.id,
                        "material_code": target.material_code,
                        "material_name": target.material_name,
                        "category": target.category,
                        "calculation_method": method,
                        "base_quantity": delta,
                        "loss_rate": Decimal("0"),
                        "used_quantity": add_used,
                        "unit": target.unit,
                        "bom_unit_price": price,
                        "total_cost": add_cost,
                        "warnings": [f"变体加料命中：{ar.rule_name}"],
                    }
                )
            return extra

        for row in model_materials:
            meta = row.metadata_json or {}
            method = str(row.calculation_method or "count")
            base_qty = _decimal(row.base_quantity, Decimal("0"))
            loss_rate = _decimal(row.loss_rate, Decimal("0"))
            fixed_qty = _decimal(meta.get("fixed_quantity"), Decimal("0"))
            cov = _decimal(meta.get("coverage_ratio"), Decimal("1"))
            measure = _measure_qty(method, width_mm=width_mm, height_mm=height_mm, quantity=quantity)
            used_qty = fixed_qty + (measure * base_qty * cov)
            used_qty = used_qty * (Decimal("1") + (loss_rate / Decimal("100")))

            line: Dict[str, Any] = {
                "module_id": meta.get("source_module_id") or "model",
                "module_code": meta.get("source_module_code") or "MODEL",
                "module_name": meta.get("source_module_name") or "模型清单",
                "source_kind": row.material_type or "real",
                "source_ref_id": row.material_ref_id,
                "resolved_kind": None,
                "resolved_ref_id": None,
                "material_id": None,
                "material_code": row.material_code,
                "material_name": row.material_name,
                "category": None,
                "calculation_method": method,
                "base_quantity": base_qty,
                "fixed_quantity": fixed_qty,
                "coverage_ratio": cov,
                "loss_rate": loss_rate,
                "used_quantity": used_qty,
                "unit": row.unit_of_measure,
                "bom_unit_price": None,
                "total_cost": None,
                "warnings": [],
            }

            if row.material_type in ("real", "bom"):
                material = db.get(models.Material, row.material_ref_id)
                if not material or material.is_archived:
                    line["warnings"].append("物料不存在或已归档")
                else:
                    line["material_id"] = material.id
                    line["material_code"] = material.material_code
                    line["material_name"] = material.material_name
                    line["category"] = material.category
                    line["unit"] = material.unit
                    price = _derive_bom_unit_price(material)
                    line["bom_unit_price"] = price
                    if price is None:
                        line["warnings"].append("未配置BOM单价")
                    else:
                        line["total_cost"] = used_qty * price
                        material_cost_total += used_qty * price
                    result["material_lines"].extend(_apply_variant_to_line(line, material.id, used_qty, method))
            else:
                # virtual material: compute BOM unit price from bindings (real material BOM unit prices)
                virtual_id = row.material_ref_id
                if not virtual_id:
                    line["warnings"].append("虚拟物料缺少 material_ref_id")
                    result["material_lines"].append(line)
                    continue

                virtual = db.get(models.VirtualMaterial, virtual_id)
                if not virtual or virtual.is_archived:
                    line["warnings"].append("虚拟物料不存在或已归档")
                    result["material_lines"].append(line)
                    continue

                v_kind = _get_virtual_kind(virtual)
                if v_kind == "placeholder":
                    # Resolve placeholder via model.placeholder_mappings to get a priceable fallback.
                    line["source_kind"] = "placeholder"
                    mapping = mapping_by_placeholder.get(virtual.id)
                    if not mapping:
                        line["warnings"].append("缺少占位符映射（placeholder_mappings）")
                        result["material_lines"].append(line)
                        continue
                    rk = str(mapping.get("replacement_kind") or "").strip()
                    rid = str(mapping.get("replacement_ref_id") or "").strip()
                    if rk not in ("real", "bom", "virtual") or not rid:
                        line["warnings"].append("占位符映射不完整（replacement_kind + replacement_ref_id）")
                        result["material_lines"].append(line)
                        continue

                    line["resolved_kind"] = rk
                    line["resolved_ref_id"] = rid
                    if rk in ("real", "bom"):
                        material = db.get(models.Material, rid)
                        if not material or material.is_archived:
                            line["warnings"].append("映射的真实物料不存在或已归档")
                            result["material_lines"].append(line)
                            continue
                        line["material_id"] = material.id
                        line["material_code"] = material.material_code
                        line["material_name"] = material.material_name
                        line["category"] = material.category
                        line["unit"] = material.unit
                        price = _derive_bom_unit_price(material)
                        line["bom_unit_price"] = price
                        if price is None:
                            line["warnings"].append("未配置BOM单价")
                        else:
                            line["total_cost"] = used_qty * price
                            material_cost_total += used_qty * price
                        result["material_lines"].extend(_apply_variant_to_line(line, material.id, used_qty, method))
                        result["material_lines"].append(line)
                        continue

                    # rk == virtual: treat as virtual recipe/kit pricing (not placeholder)
                    target_vm = db.get(models.VirtualMaterial, rid)
                    if not target_vm or target_vm.is_archived:
                        line["warnings"].append("映射的虚拟物料不存在或已归档")
                        result["material_lines"].append(line)
                        continue
                    if _get_virtual_kind(target_vm) == "placeholder":
                        line["warnings"].append("不允许映射到占位型虚拟物料")
                        result["material_lines"].append(line)
                        continue
                    binds = (
                        db.query(models.VirtualMaterialBinding)
                        .filter(models.VirtualMaterialBinding.virtual_material_id == target_vm.id)
                        .all()
                    )
                    if not binds:
                        line["warnings"].append("目标虚拟物料未配置绑定（无法计价）")
                        result["material_lines"].append(line)
                        continue
                    v_kind2 = _get_virtual_kind(target_vm)
                    line["unit"] = "套" if v_kind2 == "kit" else (target_vm.unit or line.get("unit") or "")
                    v_price2: Decimal = Decimal("0")
                    hit_any2 = False
                    for bind in binds:
                        child = db.get(models.Material, bind.material_id)
                        if not child or child.is_archived:
                            continue
                        price = _derive_bom_unit_price(child)
                        if price is None:
                            continue
                        qty = _decimal(bind.quantity_ratio, Decimal("0"))
                        if v_kind2 == "recipe" and qty > Decimal("1.5"):
                            qty = qty / Decimal("100")
                        bind_loss = _decimal(bind.loss_rate, Decimal("0"))
                        v_price2 += price * qty * (Decimal("1") + (bind_loss / Decimal("100")))
                        hit_any2 = True
                    if not hit_any2:
                        line["warnings"].append("目标虚拟物料绑定的真实物料未配置BOM单价（无法计价）")
                        result["material_lines"].append(line)
                        continue
                    line["bom_unit_price"] = v_price2
                    line["total_cost"] = used_qty * v_price2
                    material_cost_total += used_qty * v_price2
                    result["material_lines"].append(line)
                    continue

                # enforce unit semantics
                if v_kind == "kit":
                    line["unit"] = "套"
                else:
                    # recipe
                    line["unit"] = virtual.unit or line.get("unit") or ""

                binds = (
                    db.query(models.VirtualMaterialBinding)
                    .filter(
                        models.VirtualMaterialBinding.virtual_material_id == virtual.id,
                    )
                    .all()
                )
                if not binds:
                    line["warnings"].append("虚拟物料未配置绑定（无法计价）")
                    result["material_lines"].append(line)
                    continue

                v_price: Decimal = Decimal("0")
                hit_any = False
                for bind in binds:
                    material = db.get(models.Material, bind.material_id)
                    if not material or material.is_archived:
                        continue
                    price = _derive_bom_unit_price(material)
                    if price is None:
                        continue

                    qty = _decimal(bind.quantity_ratio, Decimal("0"))
                    # safety: if legacy data stored 0-100 for recipe, convert to 0-1 fraction
                    if v_kind == "recipe" and qty > Decimal("1.5"):
                        qty = qty / Decimal("100")

                    bind_loss = _decimal(bind.loss_rate, Decimal("0"))  # 0-100 (%)
                    loss_factor = Decimal("1") + (bind_loss / Decimal("100"))
                    v_price += price * qty * loss_factor
                    hit_any = True

                if not hit_any:
                    line["warnings"].append("虚拟物料绑定的真实物料未配置BOM单价（无法计价）")
                    result["material_lines"].append(line)
                    continue

                line["bom_unit_price"] = v_price
                line["total_cost"] = used_qty * v_price
                material_cost_total += used_qty * v_price

            result["material_lines"].append(line)

        for row in model_processes:
            meta = row.metadata_json or {}
            proc = db.get(models.Process, row.process_id)
            pricing_method = str(meta.get("pricing_method") or "count")
            measure_method = pricing_method if pricing_method in ("fixed", "count", "area", "perimeter", "width", "height") else "count"
            measure_qty = _measure_qty(
                measure_method if measure_method != "fixed" else "count",
                width_mm=width_mm,
                height_mm=height_mm,
                quantity=quantity,
            )
            cost_type = str(meta.get("cost_type") or "").strip() or None
            base_minutes = _decimal(meta.get("base_minutes"), Decimal("0"))
            unit_minutes = _decimal(meta.get("unit_minutes"), Decimal("0"))
            rate_per_minute = meta.get("rate_per_minute")
            piece_rate = meta.get("piece_rate")
            rate = _decimal(rate_per_minute, Decimal("0")) if rate_per_minute not in (None, "") else None
            piece = _decimal(piece_rate, Decimal("0")) if piece_rate not in (None, "") else None

            warnings: List[str] = []
            total_minutes: Optional[Decimal] = None
            total_cost: Optional[Decimal] = None
            if cost_type == "time":
                if rate is None or rate <= 0:
                    warnings.append("未配置分钟单价（rate_per_minute）")
                total_minutes = base_minutes + (unit_minutes * measure_qty)
                if rate is not None and rate > 0:
                    total_cost = total_minutes * rate
            elif cost_type == "piece":
                if piece is None or piece <= 0:
                    warnings.append("未配置计件单价（piece_rate）")
                if piece is not None and piece > 0:
                    total_cost = measure_qty * piece
            else:
                warnings.append("未配置工序计价类型（cost_type=time/piece）")

            if total_cost is not None:
                labor_cost_total += total_cost
            result["labor_lines"].append(
                {
                    "module_id": meta.get("source_module_id") or "model",
                    "module_code": meta.get("source_module_code") or "MODEL",
                    "module_name": meta.get("source_module_name") or "模型清单",
                    "process_id": row.process_id,
                    "process_code": proc.process_code if proc else None,
                    "process_name": proc.process_name if proc else None,
                    "team_name": meta.get("team_name") or (proc.team_name if proc else None),
                    "pricing_method": pricing_method,
                    "measure_quantity": measure_qty,
                    "cost_type": cost_type,
                    "base_minutes": base_minutes,
                    "unit_minutes": unit_minutes,
                    "rate_per_minute": rate,
                    "piece_rate": piece,
                    "total_minutes": total_minutes,
                    "total_cost": total_cost,
                    "warnings": warnings,
                }
            )

        overhead_cost = (material_cost_total + labor_cost_total) * Decimal("0.3")
        result["totals"] = {
            "material_cost": material_cost_total,
            "labor_cost": labor_cost_total,
            "overhead_cost": overhead_cost,
            "total_cost": material_cost_total + labor_cost_total + overhead_cost,
        }
        return result

    module_links = list_model_modules(db, model.id)
    module_ids = [link.module_id for link in module_links]
    if not module_ids:
        result["totals"] = {"material_cost": Decimal("0"), "labor_cost": Decimal("0"), "total_cost": Decimal("0")}
        return result

    meta = model.metadata_json or {}
    mappings = meta.get("placeholder_mappings") or []
    mapping_by_placeholder: Dict[str, Dict[str, Any]] = {}
    if isinstance(mappings, list):
        for item in mappings:
            if not isinstance(item, dict):
                continue
            pid = str(item.get("placeholder_virtual_id") or "").strip()
            if not pid:
                continue
            mapping_by_placeholder[pid] = item

    modules = (
        db.query(models.ProcessModule)
        .filter(models.ProcessModule.id.in_(module_ids), models.ProcessModule.is_archived.is_(False))
        .all()
    )
    module_by_id = {m.id: m for m in modules}

    material_cost_total = Decimal("0")
    labor_cost_total = Decimal("0")

    rules = variant_rule_service.list_rules(db, model.id)
    active_rules = [r for r in rules if (r.status or "") == "active" and not r.is_archived]
    rules_by_source: Dict[str, List[models.ModelVariantRule]] = {}
    for r in active_rules:
        src = (r.source_material_ref_id or "").strip()
        if not src:
            continue
        rules_by_source.setdefault(src, []).append(r)

    def _trigger_hit(rule: models.ModelVariantRule, *, area_m2: Decimal, perimeter_m: Decimal) -> bool:
        t = (rule.trigger_type or "").strip()
        v = (rule.trigger_value or "").strip() if rule.trigger_value is not None else ""
        if t == "sku_contains":
            if not sku_hint:
                return False
            return v != "" and v in str(sku_hint)
        if t == "area_gte":
            try:
                return area_m2 >= Decimal(v)
            except Exception:  # noqa: BLE001
                return False
        if t == "perimeter_gte":
            try:
                return perimeter_m >= Decimal(v)
            except Exception:  # noqa: BLE001
                return False
        return False

    def _apply_variant_rules_for_line(
        line: Dict[str, Any],
        *,
        source_material_id: str,
        module: models.ProcessModule,
        method: str,
        measure_qty: Decimal,
        used_qty: Decimal,
        source_kind_hint: str,
    ) -> List[Dict[str, Any]]:
        """
        Apply variant rules for a single base material (fallback = source_material_id).
        - replace_material: first match wins, mutates `line`
        - add_material: all matches generate extra lines (returned)
        """
        nonlocal material_cost_total
        extra_lines: List[Dict[str, Any]] = []
        candidates = rules_by_source.get(source_material_id) or []
        if not candidates:
            return extra_lines

        area_m2 = _measure_qty("area", width_mm=width_mm, height_mm=height_mm, quantity=quantity)
        per_m = _measure_qty("perimeter", width_mm=width_mm, height_mm=height_mm, quantity=quantity)

        replace_rule: models.ModelVariantRule | None = None
        add_rules: List[models.ModelVariantRule] = []
        for rr in candidates:
            if not _trigger_hit(rr, area_m2=area_m2, perimeter_m=per_m):
                continue
            if rr.action_type == "replace_material" and replace_rule is None:
                replace_rule = rr
            elif rr.action_type == "add_material":
                add_rules.append(rr)

        if replace_rule and replace_rule.target_material_ref_id:
            target = db.get(models.Material, replace_rule.target_material_ref_id)
            if target and not target.is_archived and target.is_active:
                # remove old cost from totals if it was added
                if line.get("total_cost") is not None:
                    material_cost_total -= _decimal(line["total_cost"], Decimal("0"))
                price = _derive_bom_unit_price(target)
                line["resolved_kind"] = "bom" if source_kind_hint == "bom" else "real"
                line["resolved_ref_id"] = target.id
                line["material_id"] = target.id
                line["material_code"] = target.material_code
                line["material_name"] = target.material_name
                line["category"] = target.category
                line["unit"] = target.unit
                line["bom_unit_price"] = price
                if price is None:
                    line["total_cost"] = None
                    line["warnings"].append(f"变体替换命中：{replace_rule.rule_name}（但目标无BOM单价）")
                else:
                    line["total_cost"] = used_qty * price
                    material_cost_total += used_qty * price
                    line["warnings"].append(f"变体替换命中：{replace_rule.rule_name}")
            else:
                line["warnings"].append(f"变体替换规则命中但目标物料不可用：{replace_rule.rule_name}")

        for ar in add_rules:
            if not ar.target_material_ref_id:
                continue
            target = db.get(models.Material, ar.target_material_ref_id)
            if not target or target.is_archived or not target.is_active:
                extra_lines.append(
                    {
                        "module_id": module.id,
                        "module_code": module.module_code,
                        "module_name": module.module_name,
                        "source_kind": "real",
                        "source_ref_id": source_material_id,
                        "resolved_kind": None,
                        "resolved_ref_id": None,
                        "material_id": None,
                        "material_code": None,
                        "material_name": None,
                        "category": None,
                        "calculation_method": method,
                        "base_quantity": Decimal("0"),
                        "loss_rate": Decimal("0"),
                        "used_quantity": Decimal("0"),
                        "unit": None,
                        "bom_unit_price": None,
                        "total_cost": None,
                        "warnings": [f"变体加料目标物料不可用：{ar.rule_name}"],
                    }
                )
                continue
            delta = _decimal(ar.quantity_delta, Decimal("0"))
            if delta <= 0:
                continue
            add_used = measure_qty * delta
            price = _derive_bom_unit_price(target)
            add_cost = (add_used * price) if price is not None else None
            if add_cost is not None:
                material_cost_total += add_cost
            extra_lines.append(
                {
                    "module_id": module.id,
                    "module_code": module.module_code,
                    "module_name": module.module_name,
                    "source_kind": "real",
                    "source_ref_id": source_material_id,
                    "resolved_kind": "real",
                    "resolved_ref_id": target.id,
                    "material_id": target.id,
                    "material_code": target.material_code,
                    "material_name": target.material_name,
                    "category": target.category,
                    "calculation_method": method,
                    "base_quantity": delta,
                    "loss_rate": Decimal("0"),
                    "used_quantity": add_used,
                    "unit": target.unit,
                    "bom_unit_price": price,
                    "total_cost": add_cost,
                    "warnings": [f"变体加料命中：{ar.rule_name}"],
                }
            )

        return extra_lines

    # Resolve and cost materials
    for link in module_links:
        module = module_by_id.get(link.module_id)
        if not module:
            continue
        for row in module.materials or []:
            if row.is_archived:
                continue
            method = str(row.calculation_method or "count")
            measure_qty = _measure_qty(method, width_mm=width_mm, height_mm=height_mm, quantity=quantity)
            base_qty = _decimal(row.quantity, Decimal("0"))
            loss_rate = _decimal(row.loss_rate, Decimal("0"))
            used_qty = measure_qty * base_qty * (Decimal("1") + (loss_rate / Decimal("100")))

            line: Dict[str, Any] = {
                "module_id": module.id,
                "module_code": module.module_code,
                "module_name": module.module_name,
                "source_kind": row.material_kind or "real",
                "source_ref_id": row.material_ref_id,
                "resolved_kind": None,
                "resolved_ref_id": None,
                "material_id": None,
                "material_code": row.material_code,
                "material_name": row.material_name,
                "category": row.material_category,
                "calculation_method": method,
                "base_quantity": base_qty,
                "loss_rate": loss_rate,
                "used_quantity": used_qty,
                "unit": row.unit_of_measure,
                "bom_unit_price": None,
                "total_cost": None,
                "warnings": [],
            }

            if row.material_kind in ("real", "bom"):
                ref_id = row.material_ref_id
                if not ref_id:
                    line["warnings"].append("未选择物料")
                else:
                    material = db.get(models.Material, ref_id)
                    if not material or material.is_archived:
                        line["warnings"].append("物料不存在或已归档")
                    else:
                        line["material_id"] = material.id
                        line["material_code"] = material.material_code
                        line["material_name"] = material.material_name
                        line["category"] = material.category
                        line["unit"] = material.unit
                        price = _derive_bom_unit_price(material)
                        line["bom_unit_price"] = price
                        if price is None:
                            line["warnings"].append("未配置BOM单价")
                        else:
                            line["total_cost"] = used_qty * price
                            material_cost_total += used_qty * price
                if line.get("material_id"):
                    src_id = str(line["material_id"])
                    result["material_lines"].extend(
                        _apply_variant_rules_for_line(
                            line,
                            source_material_id=src_id,
                            module=module,
                            method=method,
                            measure_qty=measure_qty,
                            used_qty=used_qty,
                            source_kind_hint=str(row.material_kind or "real"),
                        )
                    )
                result["material_lines"].append(line)
                continue

            if row.material_kind != "virtual":
                line["warnings"].append(f"未知 material_kind={row.material_kind}")
                result["material_lines"].append(line)
                continue

            virtual_id = row.material_ref_id
            if not virtual_id:
                line["warnings"].append("未选择虚拟物料")
                result["material_lines"].append(line)
                continue

            virtual = db.get(models.VirtualMaterial, virtual_id)
            if not virtual or virtual.is_archived:
                line["warnings"].append("虚拟物料不存在或已归档")
                result["material_lines"].append(line)
                continue

            v_kind = _get_virtual_kind(virtual)
            if v_kind == "placeholder":
                mapping = mapping_by_placeholder.get(virtual.id)
                if not mapping:
                    line["source_kind"] = "placeholder"
                    line["warnings"].append("缺少占位符映射（模型未配置 placeholder_mappings）")
                    result["material_lines"].append(line)
                    continue
                kind = str(mapping.get("replacement_kind") or "").strip()
                ref_id = str(mapping.get("replacement_ref_id") or "").strip()
                line["source_kind"] = "placeholder"
                line["resolved_kind"] = kind
                line["resolved_ref_id"] = ref_id
                if kind in ("real", "bom"):
                    material = db.get(models.Material, ref_id)
                    if not material or material.is_archived:
                        line["warnings"].append("映射的真实物料不存在或已归档")
                    else:
                        line["material_id"] = material.id
                        line["material_code"] = material.material_code
                        line["material_name"] = material.material_name
                        line["category"] = material.category
                        line["unit"] = material.unit
                        price = _derive_bom_unit_price(material)
                        line["bom_unit_price"] = price
                        if price is None:
                            line["warnings"].append("未配置BOM单价")
                        else:
                            line["total_cost"] = used_qty * price
                            material_cost_total += used_qty * price
                        # Apply variant rules on the mapped base material
                        src_id = str(material.id)
                        result["material_lines"].extend(
                            _apply_variant_rules_for_line(
                                line,
                                source_material_id=src_id,
                                module=module,
                                method=method,
                                measure_qty=measure_qty,
                                used_qty=used_qty,
                                source_kind_hint=kind,
                            )
                        )
                    result["material_lines"].append(line)
                    continue
                if kind == "virtual":
                    # Treat as virtual recipe/kit expansion
                    target_vm = db.get(models.VirtualMaterial, ref_id)
                    if not target_vm or target_vm.is_archived:
                        line["warnings"].append("映射的虚拟物料不存在或已归档")
                        result["material_lines"].append(line)
                        continue
                    if _get_virtual_kind(target_vm) == "placeholder":
                        line["warnings"].append("不允许映射到占位型虚拟物料")
                        result["material_lines"].append(line)
                        continue
                    # Expand via bindings into real materials (cost lines)
                    bindings = (
                        db.query(models.VirtualMaterialBinding)
                        .filter(models.VirtualMaterialBinding.virtual_material_id == target_vm.id)
                        .all()
                    )
                    if not bindings:
                        line["warnings"].append("目标虚拟物料无绑定，无法展开计价")
                        result["material_lines"].append(line)
                        continue
                    # Keep the placeholder line for traceability (cost is sum of children)
                    result["material_lines"].append(line)
                    for bind in bindings:
                        child = db.get(models.Material, bind.material_id)
                        if not child or child.is_archived:
                            result["material_lines"].append(
                                {
                                    **line,
                                    "source_kind": "virtual",
                                    "source_ref_id": target_vm.id,
                                    "material_id": None,
                                    "material_code": None,
                                    "material_name": None,
                                    "warnings": ["虚拟物料绑定的子物料不存在或已归档"],
                                    "total_cost": None,
                                }
                            )
                            continue
                        bind_meta = bind.metadata_json or {}
                        bind_type = str(bind_meta.get("binding_type") or "ratio")
                        ratio = _decimal(bind.quantity_ratio, Decimal("0"))
                        bind_loss = _decimal(bind.loss_rate, Decimal("0"))
                        child_used = used_qty * ratio
                        child_used = child_used * (Decimal("1") + (bind_loss / Decimal("100")))
                        price = _derive_bom_unit_price(child)
                        warnings: List[str] = []
                        if bind_type not in ("ratio", "quantity"):
                            warnings.append(f"未知 binding_type={bind_type}")
                        if price is None:
                            warnings.append("未配置BOM单价")
                        total_cost = (child_used * price) if price is not None else None
                        if total_cost is not None:
                            material_cost_total += total_cost
                        child_line: Dict[str, Any] = {
                            "module_id": module.id,
                            "module_code": module.module_code,
                            "module_name": module.module_name,
                            "source_kind": "virtual",
                            "source_ref_id": target_vm.id,
                            "resolved_kind": None,
                            "resolved_ref_id": None,
                            "material_id": child.id,
                            "material_code": child.material_code,
                            "material_name": child.material_name,
                            "category": child.category,
                            "calculation_method": method,
                            "base_quantity": base_qty,
                            "loss_rate": loss_rate,
                            "used_quantity": child_used,
                            "unit": child.unit,
                            "bom_unit_price": price,
                            "total_cost": total_cost,
                            "warnings": warnings,
                        }
                        # Apply variant rules on expanded child material too
                        result["material_lines"].extend(
                            _apply_variant_rules_for_line(
                                child_line,
                                source_material_id=str(child.id),
                                module=module,
                                method=method,
                                measure_qty=measure_qty,
                                used_qty=child_used,
                                source_kind_hint="real",
                            )
                        )
                        result["material_lines"].append(child_line)
                    continue

                line["warnings"].append("占位符映射 kind 不合法")
                result["material_lines"].append(line)
                continue

            # Non-placeholder virtual material: MVP does not auto-expand unless used as placeholder mapping target.
            line["source_kind"] = "virtual"
            line["warnings"].append(f"虚拟物料({v_kind})暂不在模型预览中自动展开计价")
            result["material_lines"].append(line)

    # Resolve and cost labor lines
    for link in module_links:
        module = module_by_id.get(link.module_id)
        if not module:
            continue
        for step in module.steps or []:
            if step.is_archived:
                continue
            pricing_method = str(step.pricing_method or "count")
            measure_qty = _measure_qty(
                pricing_method if pricing_method in ("count", "area", "perimeter", "width", "height") else "count",
                width_mm=width_mm,
                height_mm=height_mm,
                quantity=quantity if pricing_method != "fixed" else Decimal("1") * quantity,
            )
            meta_step = step.metadata_json or {}
            cost_type = str(meta_step.get("cost_type") or "").strip() or None
            base_minutes = _decimal(meta_step.get("base_minutes"), Decimal("0"))
            unit_minutes = _decimal(meta_step.get("unit_minutes"), Decimal("0"))
            rate_per_minute = meta_step.get("rate_per_minute")
            piece_rate = meta_step.get("piece_rate")
            rate = _decimal(rate_per_minute, Decimal("0")) if rate_per_minute not in (None, "") else None
            piece = _decimal(piece_rate, Decimal("0")) if piece_rate not in (None, "") else None
            warnings: List[str] = []

            total_minutes: Optional[Decimal] = None
            total_cost: Optional[Decimal] = None
            if cost_type == "time":
                if rate is None or rate <= 0:
                    warnings.append("未配置分钟单价（rate_per_minute）")
                total_minutes = base_minutes + (unit_minutes * measure_qty)
                if rate is not None and rate > 0:
                    total_cost = total_minutes * rate
            elif cost_type == "piece":
                if piece is None or piece <= 0:
                    warnings.append("未配置计件单价（piece_rate）")
                if piece is not None and piece > 0:
                    total_cost = measure_qty * piece
            else:
                warnings.append("未配置工序计价类型（cost_type=time/piece）")

            if total_cost is not None:
                labor_cost_total += total_cost

            proc = step.process
            result["labor_lines"].append(
                {
                    "module_id": module.id,
                    "module_code": module.module_code,
                    "module_name": module.module_name,
                    "process_id": step.process_id,
                    "process_code": proc.process_code if proc else None,
                    "process_name": proc.process_name if proc else None,
                    "team_name": step.team_name,
                    "pricing_method": pricing_method if pricing_method in ("fixed", "count", "area", "perimeter", "width", "height") else "count",
                    "measure_quantity": measure_qty,
                    "cost_type": cost_type,
                    "base_minutes": base_minutes,
                    "unit_minutes": unit_minutes,
                    "rate_per_minute": rate,
                    "piece_rate": piece,
                    "total_minutes": total_minutes,
                    "total_cost": total_cost,
                    "warnings": warnings,
                }
            )

    result["totals"] = {
        "material_cost": material_cost_total,
        "labor_cost": labor_cost_total,
        "total_cost": material_cost_total + labor_cost_total,
    }
    return result


def preview_version_cost(
    db: Session,
    *,
    version: models.ProductModelVersion,
    width_mm: Decimal,
    height_mm: Decimal,
    quantity: Decimal,
    sku_hint: str | None = None,
) -> Dict[str, Any]:
    """
    Preview cost based on version ledger lines (model_version_materials/model_version_processes).
    """
    model = db.get(models.ProductModel, version.model_id)
    if not model or model.is_archived:
        raise ValueError("Product model not found")

    meta = version.metadata_json or {}
    calc_mode = str(meta.get("calc_mode") or model.calc_mode or "ratio")
    fixed_price = _decimal(meta.get("fixed_price"), _decimal(model.fixed_price, Decimal("0")))

    result: Dict[str, Any] = {
        "width_mm": width_mm,
        "height_mm": height_mm,
        "quantity": quantity,
        "material_lines": [],
        "labor_lines": [],
        "totals": {},
        "errors": [],
    }

    if calc_mode == "fixed":
        result["totals"] = {
            "material_cost": Decimal("0"),
            "labor_cost": Decimal("0"),
            "overhead_cost": Decimal("0"),
            "total_cost": fixed_price,
        }
        return result

    materials = list_version_material_lines(db, version.id)
    processes = list_version_process_lines(db, version.id)
    if not materials and not processes:
        result["errors"].append("版本清单为空：请先从模块同步或保存版本清单后再预览")
        result["totals"] = {
            "material_cost": Decimal("0"),
            "labor_cost": Decimal("0"),
            "overhead_cost": Decimal("0"),
            "total_cost": Decimal("0"),
        }
        return result

    mapping_by_placeholder = _build_placeholder_mapping_index(meta)

    # Variant rules: include rules bound to this version or global (version_id is null)
    rules = variant_rule_service.list_rules(db, model.id)
    active_rules = [
        r
        for r in rules
        if (r.status or "") == "active"
        and not r.is_archived
        and (r.version_id is None or str(r.version_id) == str(version.id))
    ]
    rules_by_source: Dict[str, List[models.ModelVariantRule]] = {}
    for r in active_rules:
        src = (r.source_material_ref_id or "").strip()
        if src:
            rules_by_source.setdefault(src, []).append(r)

    def _trigger_hit(rule: models.ModelVariantRule, *, area_m2: Decimal, perimeter_m: Decimal) -> bool:
        t = (rule.trigger_type or "").strip()
        v = (rule.trigger_value or "").strip() if rule.trigger_value is not None else ""
        if t == "sku_contains":
            return bool(sku_hint) and v != "" and v in str(sku_hint)
        if t == "area_gte":
            try:
                return area_m2 >= Decimal(v)
            except Exception:  # noqa: BLE001
                return False
        if t == "perimeter_gte":
            try:
                return perimeter_m >= Decimal(v)
            except Exception:  # noqa: BLE001
                return False
        return False

    material_cost_total = Decimal("0")
    labor_cost_total = Decimal("0")

    def _apply_variant_to_line(
        line: Dict[str, Any], source_material_id: str, used_qty: Decimal, method: str
    ) -> List[Dict[str, Any]]:
        nonlocal material_cost_total
        extra: List[Dict[str, Any]] = []
        candidates = rules_by_source.get(source_material_id) or []
        if not candidates:
            return extra
        area_m2 = _measure_qty("area", width_mm=width_mm, height_mm=height_mm, quantity=quantity)
        per_m = _measure_qty("perimeter", width_mm=width_mm, height_mm=height_mm, quantity=quantity)
        replace_rule: models.ModelVariantRule | None = None
        add_rules: List[models.ModelVariantRule] = []
        for rr in candidates:
            if not _trigger_hit(rr, area_m2=area_m2, perimeter_m=per_m):
                continue
            if rr.action_type == "replace_material" and replace_rule is None:
                replace_rule = rr
            elif rr.action_type == "add_material":
                add_rules.append(rr)

        if replace_rule and replace_rule.target_material_ref_id:
            target = db.get(models.Material, replace_rule.target_material_ref_id)
            if target and not target.is_archived and target.is_active:
                if line.get("total_cost") is not None:
                    material_cost_total -= _decimal(line["total_cost"], Decimal("0"))
                price = _derive_bom_unit_price(target)
                line["resolved_kind"] = "real"
                line["resolved_ref_id"] = target.id
                line["material_id"] = target.id
                line["material_code"] = target.material_code
                line["material_name"] = target.material_name
                line["category"] = target.category
                line["unit"] = target.unit
                line["bom_unit_price"] = price
                if price is None:
                    line["warnings"].append("目标物料缺少 BOM 计价单价")
                line["total_cost"] = (used_qty * price) if price is not None else None
                if line["total_cost"] is not None:
                    material_cost_total += _decimal(line["total_cost"], Decimal("0"))

        for rr in add_rules:
            if not rr.target_material_ref_id:
                continue
            target = db.get(models.Material, rr.target_material_ref_id)
            if not target or target.is_archived or not target.is_active:
                continue
            price = _derive_bom_unit_price(target)
            qd = _decimal(rr.quantity_delta, Decimal("0"))
            total_cost = (qd * price) if price is not None else None
            if total_cost is not None:
                material_cost_total += total_cost
            extra.append(
                {
                    "resolved_kind": "real",
                    "resolved_ref_id": target.id,
                    "material_id": target.id,
                    "material_code": target.material_code,
                    "material_name": target.material_name,
                    "category": target.category,
                    "unit": target.unit,
                    "calculation_method": "count",
                    "measure_quantity": Decimal("1"),
                    "base_quantity": qd,
                    "loss_rate": Decimal("0"),
                    "used_quantity": qd,
                    "bom_unit_price": price,
                    "total_cost": total_cost,
                    "warnings": ["变体规则追加物料"],
                }
            )
        return extra

    # Materials
    for row in materials:
        kind = str(row.material_type or "real")
        ref_id = str(row.material_ref_id or "").strip()
        method = str(row.calculation_method or "count")
        base = _decimal(row.base_quantity, Decimal("0"))
        loss = _decimal(row.loss_rate, Decimal("0"))
        loss_factor = Decimal("1") + (loss / Decimal("100"))
        meta_line = row.metadata_json or {}
        fixed_qty = _decimal(meta_line.get("fixed_quantity"), Decimal("0"))
        cov = _decimal(meta_line.get("coverage_ratio"), Decimal("1"))
        measure_qty = _measure_qty(method, width_mm=width_mm, height_mm=height_mm, quantity=quantity)
        used_qty = fixed_qty + (measure_qty * base * cov) if calc_mode == "ratio" else _decimal(
            meta_line.get("standard_used_quantity"), Decimal("0")
        )
        used_with_loss = used_qty * loss_factor

        warnings: List[str] = []
        resolved_kind = kind
        resolved_ref_id = ref_id

        bom_unit_price: Optional[Decimal] = None
        unit = None
        category = None

        if kind in ("real", "bom"):
            mat = db.get(models.Material, ref_id) if ref_id else None
            if not mat or mat.is_archived:
                warnings.append("物料不存在/已归档")
            else:
                category = mat.category
                unit = mat.unit
                bom_unit_price = _derive_bom_unit_price(mat)
                if bom_unit_price is None:
                    warnings.append("缺少 BOM 计价单价")

        elif kind == "virtual":
            vm = db.get(models.VirtualMaterial, ref_id) if ref_id else None
            if not vm or vm.is_archived:
                warnings.append("虚拟物料不存在/已归档")
            else:
                v_kind = _get_virtual_kind(vm)
                unit = vm.unit
                category = getattr(vm, "category", None)
                if v_kind == "placeholder":
                    m = mapping_by_placeholder.get(vm.id) if vm.id else None
                    rk = str((m or {}).get("replacement_kind") or "").strip()
                    rid = str((m or {}).get("replacement_ref_id") or "").strip()
                    if not rk or not rid:
                        warnings.append("占位符未配置兜底物料映射")
                    else:
                        resolved_kind = rk
                        resolved_ref_id = rid
                        if rk in ("real", "bom"):
                            mat = db.get(models.Material, rid)
                            if mat and not mat.is_archived and mat.is_active:
                                category = mat.category
                                unit = mat.unit
                                bom_unit_price = _derive_bom_unit_price(mat)
                        elif rk == "virtual":
                            rvm = db.get(models.VirtualMaterial, rid)
                            if rvm and not rvm.is_archived and _get_virtual_kind(rvm) != "placeholder":
                                unit = rvm.unit
                                category = getattr(rvm, "category", None)
                                raw = (rvm.metadata_json or {}).get("bom_unit_price")
                                if raw not in (None, ""):
                                    try:
                                        bom_unit_price = Decimal(str(raw))
                                    except Exception:  # noqa: BLE001
                                        pass
                        else:
                            warnings.append("占位符兜底类型不支持")
                else:
                    raw = (vm.metadata_json or {}).get("bom_unit_price")
                    if raw not in (None, ""):
                        try:
                            bom_unit_price = Decimal(str(raw))
                        except Exception:  # noqa: BLE001
                            pass
                    if bom_unit_price is None:
                        warnings.append("虚拟物料缺少 BOM 计价单价")

        total_cost = (used_with_loss * bom_unit_price) if bom_unit_price is not None else None
        if total_cost is not None:
            material_cost_total += total_cost

        line: Dict[str, Any] = {
            "resolved_kind": resolved_kind,
            "resolved_ref_id": resolved_ref_id,
            "material_id": resolved_ref_id if resolved_kind in ("real", "bom") else None,
            "material_code": row.material_code,
            "material_name": row.material_name,
            "category": category,
            "unit": unit,
            "calculation_method": method,
            "measure_quantity": measure_qty,
            "base_quantity": base,
            "loss_rate": loss,
            "fixed_quantity": fixed_qty,
            "coverage_ratio": cov,
            "used_quantity": used_qty,
            "used_quantity_with_loss": used_with_loss,
            "bom_unit_price": bom_unit_price,
            "total_cost": total_cost,
            "warnings": warnings,
            "metadata_json": meta_line,
        }

        # Apply variant rules based on resolved material_id (for real/bom only)
        if line.get("material_id"):
            extra = _apply_variant_to_line(line, str(line["material_id"]), used_qty, method)
            result["material_lines"].append(line)
            result["material_lines"].extend(extra)
        else:
            result["material_lines"].append(line)

    # Processes (labor)
    for row in processes:
        meta_line = row.metadata_json or {}
        process_id = str(row.process_id or "").strip()
        proc = db.get(models.Process, process_id) if process_id else None
        pricing_method = str(meta_line.get("pricing_method") or "count")
        cost_type = str(meta_line.get("cost_type") or "time")
        base_minutes = _decimal(meta_line.get("base_minutes"), Decimal("0"))
        unit_minutes = _decimal(meta_line.get("unit_minutes"), Decimal("0"))
        rate = _decimal(meta_line.get("rate_per_minute"), Decimal("0"))
        piece = _decimal(meta_line.get("piece_rate"), Decimal("0"))

        warnings: List[str] = []
        measure_method = pricing_method if pricing_method in ("fixed", "count", "area", "perimeter", "width", "height") else "count"
        measure_qty = _measure_qty(measure_method if measure_method != "fixed" else "count", width_mm=width_mm, height_mm=height_mm, quantity=quantity)

        total_minutes: Optional[Decimal] = None
        total_cost: Optional[Decimal] = None
        if cost_type == "time":
            total_minutes = base_minutes + unit_minutes * measure_qty
            if rate is not None and rate > 0:
                total_cost = total_minutes * rate
        elif cost_type == "piece":
            if piece is not None and piece > 0:
                total_cost = measure_qty * piece
        else:
            warnings.append("未配置工序计价类型（cost_type=time/piece）")

        if total_cost is not None:
            labor_cost_total += total_cost

        result["labor_lines"].append(
            {
                "process_id": process_id,
                "process_code": proc.process_code if proc else None,
                "process_name": proc.process_name if proc else None,
                "team_name": meta_line.get("team_name") or (proc.team_name if proc else None),
                "pricing_method": measure_method,
                "measure_quantity": measure_qty,
                "cost_type": cost_type,
                "base_minutes": base_minutes,
                "unit_minutes": unit_minutes,
                "rate_per_minute": rate,
                "piece_rate": piece,
                "total_minutes": total_minutes,
                "total_cost": total_cost,
                "warnings": warnings,
                "metadata_json": meta_line,
            }
        )

    overhead = (material_cost_total + labor_cost_total) * Decimal("0.3")
    result["totals"] = {
        "material_cost": material_cost_total,
        "labor_cost": labor_cost_total,
        "overhead_cost": overhead,
        "total_cost": material_cost_total + labor_cost_total + overhead,
    }
    return result


def publish_standard_version(
    db: Session,
    *,
    version: models.ProductModelVersion,
    published_by: str | None = None,
    note: str | None = None,
) -> models.ProductModelVersion:
    if (version.version_kind or "") != "standard":
        raise ValueError("仅标准版本（standard）允许发布")
    if version.is_archived:
        raise ValueError("版本已归档，无法发布")

    model = db.get(models.ProductModel, version.model_id)
    if not model or model.is_archived:
        raise ValueError("Product model not found")

    meta = version.metadata_json or {}
    standard = meta.get("standard") if isinstance(meta.get("standard"), dict) else {}
    w = _decimal((standard or {}).get("width_mm"), Decimal("0"))
    h = _decimal((standard or {}).get("height_mm"), Decimal("0"))
    q = _decimal((standard or {}).get("quantity"), Decimal("0"))
    if w != Decimal("1000") or h != Decimal("1000") or q != Decimal("1"):
        raise ValueError("标准版本发布要求标准规格固定为 1000×1000×1")

    # Ensure ledger exists and contains no placeholder virtual materials
    mats = list_version_material_lines(db, version.id)
    procs = list_version_process_lines(db, version.id)
    if not mats and not procs:
        raise ValueError("标准版本清单为空：请先同步/保存清单后再发布")
    for row in mats:
        if str(row.material_type or "") == "virtual":
            vm = db.get(models.VirtualMaterial, row.material_ref_id) if row.material_ref_id else None
            if vm and not vm.is_archived and _get_virtual_kind(vm) == "placeholder":
                raise ValueError("标准版本清单仍包含占位型虚拟物料：请先完成兜底替换并保存清单后再发布")

    # Ensure fixed mode has fixed_price
    calc_mode = str(meta.get("calc_mode") or model.calc_mode or "ratio")
    if calc_mode == "fixed":
        fixed_price = _decimal(meta.get("fixed_price"), _decimal(model.fixed_price, Decimal("0")))
        if fixed_price <= 0:
            raise ValueError("calc_mode=fixed 时发布标准版本必须配置 fixed_price")

    now = datetime.now(timezone.utc)
    # Archive other published standard versions for the same model (keep history)
    db.query(models.ProductModelVersion).filter(
        models.ProductModelVersion.model_id == model.id,
        models.ProductModelVersion.id != version.id,
        models.ProductModelVersion.version_kind == "standard",
        models.ProductModelVersion.version_status == "published",
        models.ProductModelVersion.is_archived.is_(False),
    ).update({"version_status": "archived", "updated_at": now}, synchronize_session=False)

    # Generate a readable label
    published_count = (
        db.query(models.ProductModelVersion)
        .filter(
            models.ProductModelVersion.model_id == model.id,
            models.ProductModelVersion.version_kind == "standard",
            models.ProductModelVersion.version_status == "published",
        )
        .count()
    )
    version.version_status = "published"
    version.published_at = now
    version.published_by = published_by
    version.version_label = version.version_label or f"{model.model_code}-{now.strftime('%Y%m%d')}-{published_count + 1:02d}"
    if note:
        meta.setdefault("publish_note", note)
        version.metadata_json = _json_safe(meta)

    # Optional: mark master as active when first publish
    if (model.status or "") == "draft":
        model.status = "active"

    db.commit()
    db.refresh(version)
    return version


def bind_sku_to_version(
    db: Session,
    *,
    sku_code: str,
    version_id: str,
    source_system: str | None = None,
    metadata: dict | None = None,
) -> models.SkuModelVersionMapping:
    sku = (sku_code or "").strip()
    if not sku:
        raise ValueError("sku_code 不能为空")
    version = get_model_version(db, version_id)
    if not version:
        raise ValueError("版本不存在")
    if (version.version_kind or "") != "standard" or (version.version_status or "") != "published":
        raise ValueError("SKU 只能绑定到已发布的标准版本")

    model = db.get(models.ProductModel, version.model_id)
    if not model or model.is_archived:
        raise ValueError("Product model not found")

    parsed = parse_sku_code(sku)
    # Verify model_code prefix
    prefix = (model.model_code or "").strip().upper()
    norm = str(parsed.get("normalized") or "").upper()
    skip_prefix_check = False
    if source_system in ("sku_master_manual", "sku_master_auto", "shipment_autobind", "erp_barcode"):
        skip_prefix_check = True
    if isinstance(metadata, dict) and metadata.get("skip_prefix_check") is True:
        skip_prefix_check = True
    if not skip_prefix_check and prefix and not norm.startswith(prefix):
        raise ValueError(f"SKU 绑定失败：SKU={sku} 不匹配模型编码前缀 {prefix}")

    now = datetime.now(timezone.utc)
    # Deactivate existing active binding (history is preserved)
    actives = (
        db.query(models.SkuModelVersionMapping)
        .filter(
            models.SkuModelVersionMapping.sku_code == sku,
            models.SkuModelVersionMapping.is_active.is_(True),
            models.SkuModelVersionMapping.is_archived.is_(False),
        )
        .all()
    )
    for row in actives:
        row.is_active = False
        meta0 = row.metadata_json or {}
        meta0.setdefault("effective_through", now.isoformat())
        row.metadata_json = _json_safe(meta0)

    meta_new = dict(metadata or {})
    meta_new.setdefault("effective_from", now.isoformat())
    if source_system:
        meta_new.setdefault("source_system", source_system)
    # Persist parsed SKU semantics for downstream pricing & audit
    meta_new.setdefault("parsed_model_code", parsed.get("model_code"))
    meta_new.setdefault("parsed_version_token", parsed.get("version_token"))
    meta_new.setdefault("parsed_width_mm", parsed.get("width_mm"))
    meta_new.setdefault("parsed_height_mm", parsed.get("height_mm"))
    meta_new.setdefault("variant_tokens", parsed.get("variant_tokens") or [])
    meta_new.setdefault("sku_hint", sku)

    row = models.SkuModelVersionMapping(
        sku_code=sku,
        model_version_id=version.id,
        source_system=source_system,
        is_active=True,
        metadata_json=_json_safe(meta_new),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


