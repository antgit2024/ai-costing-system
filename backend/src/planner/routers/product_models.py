from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ...database import get_db
from .. import models, schemas
from ..services import audit_service
from ..services import product_model_service
from ..services import variant_rule_service

router = APIRouter(prefix="/product-models", tags=["product-models"])


def _serialize_model(db: Session, model: models.ProductModel) -> schemas.ProductModelRead:
    result = schemas.ProductModelRead.from_orm(model)
    links = product_model_service.list_model_modules(db, model.id)
    enriched: List[schemas.ModelProcessModuleRead] = []
    for link in links:
        module = db.get(models.ProcessModule, link.module_id)
        enriched.append(
            schemas.ModelProcessModuleRead(
                id=link.id,
                module_id=link.module_id,
                sequence_order=link.sequence_order,
                notes=link.notes,
                metadata_json=link.metadata_json or {},
                module=schemas.ProcessModuleSummaryRead.from_orm(module) if module else None,
            )
        )
    result.modules = enriched
    # Include persisted model lines (editable at model layer)
    materials = product_model_service.list_model_material_lines(db, model.id)
    processes = product_model_service.list_model_process_lines(db, model.id)
    result.materials = []
    for item in materials:
        meta = item.metadata_json or {}
        result.materials.append(
            schemas.ProductModelMaterialLineRead(
                id=item.id,
                source_module_id=meta.get("source_module_id"),
                source_module_code=meta.get("source_module_code"),
                source_module_name=meta.get("source_module_name"),
                material_kind=item.material_type,
                material_ref_id=item.material_ref_id,
                material_code=item.material_code,
                material_name=item.material_name,
                calculation_method=item.calculation_method,
                base_quantity=item.base_quantity,
                loss_rate=item.loss_rate,
                notes=item.notes,
                sample_used_quantity=meta.get("sample_used_quantity"),
                standard_used_quantity=meta.get("standard_used_quantity"),
                fixed_quantity=meta.get("fixed_quantity"),
                coverage_ratio=meta.get("coverage_ratio"),
                metadata_json=meta,
            )
        )
    result.processes = []
    for item in processes:
        meta = item.metadata_json or {}
        proc = db.get(models.Process, item.process_id)
        result.processes.append(
            schemas.ProductModelProcessLineRead(
                id=item.id,
                source_module_id=meta.get("source_module_id"),
                source_module_code=meta.get("source_module_code"),
                source_module_name=meta.get("source_module_name"),
                process_id=item.process_id,
                process_code=proc.process_code if proc else None,
                process_name=proc.process_name if proc else None,
                team_name=meta.get("team_name") or (proc.team_name if proc else None),
                pricing_method=meta.get("pricing_method") or "count",
                sample_minutes=meta.get("sample_minutes"),
                standard_minutes=meta.get("standard_minutes"),
                base_minutes=meta.get("base_minutes") or 0,
                unit_minutes=meta.get("unit_minutes") or 0,
                rate_per_minute=meta.get("rate_per_minute"),
                piece_rate=meta.get("piece_rate"),
                cost_type=meta.get("cost_type"),
                notes=item.notes,
                metadata_json=meta,
            )
        )
    # Version stats (for list pages)
    q = db.query(models.ProductModelVersion).filter(
        models.ProductModelVersion.model_id == model.id,
        models.ProductModelVersion.is_archived.is_(False),
    )
    result.sample_version_count = q.filter(models.ProductModelVersion.version_kind == "sample").count()
    result.standard_version_count = q.filter(models.ProductModelVersion.version_kind == "standard").count()
    published_std = (
        q.filter(
            models.ProductModelVersion.version_kind == "standard",
            models.ProductModelVersion.version_status == "published",
        )
        # SQLite used in tests doesn't support "NULLS LAST"; keep it portable.
        .order_by(models.ProductModelVersion.published_at.desc(), models.ProductModelVersion.updated_at.desc())
        .first()
    )
    if published_std:
        result.current_published_standard_version_id = published_std.id
        result.current_published_standard_version_label = published_std.version_label
        # 抽取该已发布版本下所有变体的"货品映射"摘要（变体编码 + 替换物料名）。
        # 用于"标准模型列表 - 货品映射"列，例如：仿羊绒(KB8-001) / 多尼尔(KB8-002)
        variant_rows = (
            db.query(models.ProductModelLineVariant)
            .filter(
                models.ProductModelLineVariant.version_id == published_std.id,
                models.ProductModelLineVariant.is_archived.is_(False),
            )
            .all()
        )
        seen: set[str] = set()
        briefs: list[schemas.VariantCodeBrief] = []
        for vr in variant_rows:
            meta = vr.metadata_json or {}
            code = str(meta.get("variant_code") or "").strip().upper()
            if not code or code in seen:
                continue
            seen.add(code)
            # 展示名优先级：
            #   1. metadata_json.display_name（用户显式填的"对客显示名"，如"麻感冰丝"）
            #   2. items[0].material_name（兜底：实际替换物料的内部库存名，如"布料隔針蜂窝本白"）
            # 这样运营可以在变体编辑里把内部物料名（"布料隔針蜂窝本白"）换成卖家秀对客名（"麻感冰丝"），
            # 而不影响 BOM / 成本计算（material_code / material_ref_id 仍指向真实物料）。
            display_name = str(meta.get("display_name") or "").strip() or None
            material_name: Optional[str] = display_name
            if not material_name:
                for it in vr.items or []:
                    name = str(getattr(it, "material_name", "") or "").strip()
                    if name:
                        material_name = name
                        break
            briefs.append(schemas.VariantCodeBrief(variant_code=code, material_name=material_name))
        briefs.sort(key=lambda b: b.variant_code)
        result.current_published_variant_codes = briefs

    # Latest sample version (for list thumbnails) - prefer versions with images to reduce 404s
    # Note: image URLs are served by `/api/planner/product-model-versions/{version_id}/images/{idx}`.
    sample_versions = (
        q.filter(
            models.ProductModelVersion.version_kind == "sample",
            models.ProductModelVersion.version_status != "archived",
        )
        .order_by(models.ProductModelVersion.updated_at.desc(), models.ProductModelVersion.created_at.desc())
        .all()
    )
    for v in sample_versions:
        meta = v.metadata_json or {}
        imgs = meta.get("version_images")
        if isinstance(imgs, list) and len(imgs) > 0:
            result.latest_sample_version_id = v.id
            break
    return result


def _get_model_or_404(model_id: str, db: Session, *, include_archived: bool = False) -> models.ProductModel:
    model = product_model_service.get_model(db, model_id, include_archived=include_archived)
    if not model:
        raise HTTPException(status_code=404, detail="Product model not found")
    return model


@router.get("", response_model=schemas.PaginatedProductModelResponse)
def list_product_models(
    search: Optional[str] = Query(None, max_length=128),
    category: Optional[str] = Query(None, max_length=128),
    status_filter: Optional[str] = Query(None, alias="status", max_length=32),
    include_archived: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
):
    filters = product_model_service.ProductModelFilters(
        search=search, status=status_filter, category=category, include_archived=include_archived
    )
    total, items = product_model_service.list_models(db, filters=filters, page=page, page_size=page_size)
    return schemas.PaginatedProductModelResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=[_serialize_model(db, item) for item in items],
    )


@router.post("", response_model=schemas.ProductModelRead, status_code=status.HTTP_201_CREATED)
def create_product_model(payload: schemas.ProductModelCreateRequest, db: Session = Depends(get_db)):
    try:
        model = product_model_service.create_model(
            db,
            model_code=payload.model_code,
            model_name=payload.model_name,
            description=payload.description,
            category=payload.category,
            calc_mode=payload.calc_mode,
            fixed_price=payload.fixed_price,
            status=payload.status,
            tags=payload.tags,
            standard_width_mm=payload.standard_width_mm,
            standard_height_mm=payload.standard_height_mm,
            unit_of_measure=payload.unit_of_measure,
            metadata=payload.metadata,
            modules=[m.dict(by_alias=True) for m in payload.modules],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    audit_service.log_audit_event(
        db,
        target_type="product_model",
        target_id=model.id,
        action="create",
        actor_id="system",
        payload={"model_code": model.model_code},
    )
    db.commit()
    return _serialize_model(db, model)


@router.get("/{model_id}", response_model=schemas.ProductModelRead)
def get_product_model(
    model_id: str,
    include_archived: bool = Query(False),
    db: Session = Depends(get_db),
):
    model = _get_model_or_404(model_id, db, include_archived=include_archived)
    return _serialize_model(db, model)


@router.post("/{model_id}/sync-from-modules", response_model=schemas.ProductModelRead)
def sync_model_lines_from_modules(
    model_id: str,
    payload: schemas.ProductModelSyncFromModulesRequest,
    db: Session = Depends(get_db),
):
    model = _get_model_or_404(model_id, db)
    product_model_service.sync_lines_from_modules(db, model, keep_overrides=payload.keep_overrides)
    audit_service.log_audit_event(
        db,
        target_type="product_model",
        target_id=model.id,
        action="sync_from_modules",
        actor_id="system",
        payload={"keep_overrides": payload.keep_overrides},
    )
    db.commit()
    return _serialize_model(db, model)


@router.post("/{model_id}/refresh-material-prices", response_model=schemas.ProductModelLinesResponse)
def refresh_model_material_prices(model_id: str, db: Session = Depends(get_db)):
    """
    Refresh model material lines' BOM unit price/unit snapshots from latest master data.
    This does NOT change quantities; it only updates metadata_json.{bom_unit_price,bom_unit}.
    """
    model = _get_model_or_404(model_id, db)
    product_model_service.refresh_model_material_price_snapshots(db, model)
    db.commit()
    # return latest lines for immediate UI refresh
    # NOTE: get_model_lines signature includes include_archived; use keyword args to avoid positional mismatch.
    return get_model_lines(model_id=model_id, db=db)


@router.get("/{model_id}/lines", response_model=schemas.ProductModelLinesResponse)
def get_model_lines(
    model_id: str,
    include_archived: bool = Query(False),
    db: Session = Depends(get_db),
):
    model = _get_model_or_404(model_id, db, include_archived=include_archived)
    sample, standard = product_model_service._extract_sample_and_standard(model)  # noqa: SLF001
    materials = product_model_service.list_model_material_lines(db, model.id)
    processes = product_model_service.list_model_process_lines(db, model.id)
    mat_reads: List[schemas.ProductModelMaterialLineRead] = []
    for item in materials:
        meta = item.metadata_json or {}
        mat_reads.append(
            schemas.ProductModelMaterialLineRead(
                id=item.id,
                source_module_id=meta.get("source_module_id"),
                source_module_code=meta.get("source_module_code"),
                source_module_name=meta.get("source_module_name"),
                material_kind=item.material_type,
                material_ref_id=item.material_ref_id,
                material_code=item.material_code,
                material_name=item.material_name,
                calculation_method=item.calculation_method,
                base_quantity=item.base_quantity,
                loss_rate=item.loss_rate,
                notes=item.notes,
                sample_used_quantity=meta.get("sample_used_quantity"),
                standard_used_quantity=meta.get("standard_used_quantity"),
                fixed_quantity=meta.get("fixed_quantity"),
                coverage_ratio=meta.get("coverage_ratio"),
                metadata_json=meta,
            )
        )
    proc_reads: List[schemas.ProductModelProcessLineRead] = []
    for item in processes:
        meta = item.metadata_json or {}
        proc = db.get(models.Process, item.process_id)
        proc_reads.append(
            schemas.ProductModelProcessLineRead(
                id=item.id,
                source_module_id=meta.get("source_module_id"),
                source_module_code=meta.get("source_module_code"),
                source_module_name=meta.get("source_module_name"),
                process_id=item.process_id,
                process_code=proc.process_code if proc else None,
                process_name=proc.process_name if proc else None,
                team_name=meta.get("team_name") or (proc.team_name if proc else None),
                pricing_method=meta.get("pricing_method") or "count",
                sample_minutes=meta.get("sample_minutes"),
                standard_minutes=meta.get("standard_minutes"),
                base_minutes=meta.get("base_minutes") or 0,
                unit_minutes=meta.get("unit_minutes") or 0,
                rate_per_minute=meta.get("rate_per_minute"),
                piece_rate=meta.get("piece_rate"),
                cost_type=meta.get("cost_type"),
                notes=item.notes,
                metadata_json=meta,
            )
        )
    return schemas.ProductModelLinesResponse(
        sample=schemas.ProductModelSampleSpec(**sample),
        standard=schemas.ProductModelSampleSpec(**standard),
        materials=mat_reads,
        processes=proc_reads,
    )


@router.put("/{model_id}/lines", response_model=schemas.ProductModelRead)
def update_model_lines(
    model_id: str,
    payload: schemas.ProductModelLinesUpdateRequest,
    db: Session = Depends(get_db),
):
    model = _get_model_or_404(model_id, db)
    product_model_service.replace_model_lines(
        db,
        model,
        sample=payload.sample.dict(),
        standard=payload.standard.dict(),
        materials=[m.dict(by_alias=True) for m in payload.materials],
        processes=[p.dict(by_alias=True) for p in payload.processes],
    )
    audit_service.log_audit_event(
        db,
        target_type="product_model",
        target_id=model.id,
        action="update_lines",
        actor_id="system",
        payload={"materials": len(payload.materials), "processes": len(payload.processes)},
    )
    db.commit()
    return _serialize_model(db, model)


@router.patch("/{model_id}", response_model=schemas.ProductModelRead)
def update_product_model(model_id: str, payload: schemas.ProductModelUpdateRequest, db: Session = Depends(get_db)):
    model = _get_model_or_404(model_id, db)
    try:
        model = product_model_service.update_model(
            db,
            model,
            model_name=payload.model_name,
            description=payload.description,
            category=payload.category,
            calc_mode=payload.calc_mode,
            fixed_price=payload.fixed_price,
            status=payload.status,
            tags=payload.tags,
            standard_width_mm=payload.standard_width_mm,
            standard_height_mm=payload.standard_height_mm,
            unit_of_measure=payload.unit_of_measure,
            metadata=payload.metadata,
            modules=[m.dict(by_alias=True) for m in payload.modules] if payload.modules is not None else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    audit_service.log_audit_event(
        db,
        target_type="product_model",
        target_id=model.id,
        action="update",
        actor_id="system",
        payload={"model_code": model.model_code},
    )
    db.commit()
    return _serialize_model(db, model)


@router.post("/{model_id}/recognition/validate", response_model=schemas.RecognitionKeywordsValidateResponse)
def validate_model_recognition_keywords(
    model_id: str,
    payload: schemas.RecognitionKeywordsValidateRequest,
    db: Session = Depends(get_db),
):
    model = _get_model_or_404(model_id, db)
    meta = model.metadata_json or {}
    # merge draft keywords into current metadata for normalization rules
    meta2 = dict(meta)
    meta2["recognition_keywords"] = list(payload.keywords or [])
    normalized = product_model_service._extract_recognition_keywords(meta2)  # noqa: SLF001
    conflicts = product_model_service._validate_recognition_keywords_uniqueness(  # noqa: SLF001
        db, current_model_id=model.id, keywords=normalized
    )
    return {"ok": not bool(conflicts), "normalized_keywords": normalized, "conflicts": conflicts}


@router.post("/{model_id}/activate", response_model=schemas.ProductModelRead)
def activate_product_model(model_id: str, db: Session = Depends(get_db)):
    model = _get_model_or_404(model_id, db)
    errors = product_model_service.validate_can_activate(db, model)
    if errors:
        raise HTTPException(status_code=400, detail="；".join(errors))
    model = product_model_service.set_model_status(db, model, "active")
    audit_service.log_audit_event(
        db,
        target_type="product_model",
        target_id=model.id,
        action="activate",
        actor_id="system",
        payload={"model_code": model.model_code},
    )
    db.commit()
    return _serialize_model(db, model)


@router.post("/{model_id}/deactivate", response_model=schemas.ProductModelRead)
def deactivate_product_model(model_id: str, db: Session = Depends(get_db)):
    model = _get_model_or_404(model_id, db)
    model = product_model_service.set_model_status(db, model, "inactive")
    audit_service.log_audit_event(
        db,
        target_type="product_model",
        target_id=model.id,
        action="deactivate",
        actor_id="system",
        payload={"model_code": model.model_code},
    )
    db.commit()
    return _serialize_model(db, model)


@router.get("/{model_id}/placeholders", response_model=List[Dict[str, Any]])
def list_model_placeholders(model_id: str, db: Session = Depends(get_db)):
    model = _get_model_or_404(model_id, db)
    links = product_model_service.list_model_modules(db, model.id)
    module_ids = [link.module_id for link in links]
    placeholders = product_model_service._collect_placeholders_for_modules(db, module_ids)  # noqa: SLF001
    items: List[Dict[str, Any]] = []
    for vm in placeholders:
        meta = vm.metadata_json or {}
        items.append(
            {
                "virtual_material_id": vm.id,
                "virtual_code": vm.virtual_code,
                "name": vm.name,
                "unit": vm.unit,
                "placeholder_symbol": meta.get("placeholder_symbol"),
                "constraint_category": meta.get("constraint_category"),
            }
        )
    return items


@router.get("/{model_id}/materials", response_model=List[Dict[str, Any]])
def list_model_base_materials(model_id: str, db: Session = Depends(get_db)):
    """
    Return a de-duplicated list of base materials that appear in model-expanded modules
    (after placeholder mappings), used for variant rule source selection.
    """
    model = _get_model_or_404(model_id, db)

    # If model-layer lines exist, treat them as the single source of truth for variant "fallback materials".
    # This matches the UX: placeholders are template-only (modules), and model ledger must contain real/bom materials.
    model_lines = product_model_service.list_model_material_lines(db, model.id)
    if model_lines:
        ids: List[str] = []
        for row in model_lines:
            if (row.material_type or "") not in ("real", "bom"):
                continue
            if row.material_ref_id:
                ids.append(str(row.material_ref_id))
        items: List[Dict[str, Any]] = []
        for mid in sorted(set(ids)):
            material = db.get(models.Material, mid)
            if not material or material.is_archived:
                continue
            items.append(
                {
                    "material_id": material.id,
                    "material_code": material.material_code,
                    "material_name": material.material_name,
                    "category": material.category,
                    "unit": material.unit,
                    "is_active": material.is_active,
                }
            )
        return items

    # Build placeholder mapping index (same semantics as activation)
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

    links = product_model_service.list_model_modules(db, model.id)
    module_ids = [link.module_id for link in links]
    material_ids = product_model_service._collect_base_material_ids_for_modules(  # noqa: SLF001
        db,
        module_ids=module_ids,
        placeholder_mapping_by_virtual_id=mapping_by_placeholder,
    )
    items: List[Dict[str, Any]] = []
    for mid in material_ids:
        material = db.get(models.Material, mid)
        if not material or material.is_archived:
            continue
        items.append(
            {
                "material_id": material.id,
                "material_code": material.material_code,
                "material_name": material.material_name,
                "category": material.category,
                "unit": material.unit,
                "is_active": material.is_active,
            }
        )
    return items


@router.post("/{model_id}/preview", response_model=schemas.ProductModelPreviewResponse)
def preview_product_model_cost(
    model_id: str,
    payload: schemas.ProductModelPreviewRequest,
    db: Session = Depends(get_db),
):
    model = _get_model_or_404(model_id, db)
    data = product_model_service.preview_model_cost(
        db,
        model,
        width_mm=payload.width_mm,
        height_mm=payload.height_mm,
        quantity=payload.quantity,
        sku_hint=payload.sku_hint,
    )
    return schemas.ProductModelPreviewResponse(**data)


def _get_rule_or_404(db: Session, model_id: str, rule_id: str) -> models.ModelVariantRule:
    rule = variant_rule_service.get_rule(db, rule_id)
    if not rule or rule.model_id != model_id:
        raise HTTPException(status_code=404, detail="Variant rule not found")
    return rule


@router.get("/{model_id}/variant-rules", response_model=List[schemas.ModelVariantRuleRead])
def list_variant_rules(model_id: str, db: Session = Depends(get_db)):
    _ = _get_model_or_404(model_id, db)
    return [schemas.ModelVariantRuleRead.from_orm(r) for r in variant_rule_service.list_rules(db, model_id)]


@router.post("/{model_id}/variant-rules", response_model=schemas.ModelVariantRuleRead, status_code=status.HTTP_201_CREATED)
def create_variant_rule(
    model_id: str,
    payload: schemas.ModelVariantRuleCreateRequest,
    db: Session = Depends(get_db),
):
    model = _get_model_or_404(model_id, db)
    rule = variant_rule_service.create_rule(
        db,
        model_id=model.id,
        rule_name=payload.rule_name,
        source_material_ref_id=payload.source_material_ref_id or "",
        trigger_type=payload.trigger_type,
        trigger_operator="equals",
        trigger_value=payload.trigger_value,
        action_type=payload.action_type,
        target_material_ref_id=payload.target_material_ref_id,
        quantity_delta=payload.quantity_delta,
        status=payload.status,
        metadata_json=payload.metadata,
    )
    audit_service.log_audit_event(
        db,
        target_type="product_model",
        target_id=model.id,
        action="variant_rule_create",
        actor_id="system",
        payload={"rule_id": rule.id, "rule_name": rule.rule_name},
    )
    db.commit()
    return schemas.ModelVariantRuleRead.from_orm(rule)


@router.patch("/{model_id}/variant-rules/{rule_id}", response_model=schemas.ModelVariantRuleRead)
def update_variant_rule(
    model_id: str,
    rule_id: str,
    payload: schemas.ModelVariantRuleUpdateRequest,
    db: Session = Depends(get_db),
):
    model = _get_model_or_404(model_id, db)
    rule = _get_rule_or_404(db, model.id, rule_id)
    rule = variant_rule_service.update_rule(
        db,
        rule,
        rule_name=payload.rule_name,
        trigger_type=payload.trigger_type,
        trigger_value=payload.trigger_value,
        action_type=payload.action_type,
        target_material_ref_id=payload.target_material_ref_id,
        quantity_delta=payload.quantity_delta,
        status=payload.status,
        metadata_json=payload.metadata,
    )
    audit_service.log_audit_event(
        db,
        target_type="product_model",
        target_id=model.id,
        action="variant_rule_update",
        actor_id="system",
        payload={"rule_id": rule.id, "rule_name": rule.rule_name},
    )
    db.commit()
    return schemas.ModelVariantRuleRead.from_orm(rule)


@router.delete("/{model_id}/variant-rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_variant_rule(model_id: str, rule_id: str, db: Session = Depends(get_db)):
    model = _get_model_or_404(model_id, db)
    rule = _get_rule_or_404(db, model.id, rule_id)
    variant_rule_service.delete_rule(db, rule)
    audit_service.log_audit_event(
        db,
        target_type="product_model",
        target_id=model.id,
        action="variant_rule_delete",
        actor_id="system",
        payload={"rule_id": rule.id, "rule_name": rule.rule_name},
    )
    db.commit()
    return None


@router.delete("/{model_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product_model(model_id: str, db: Session = Depends(get_db)):
    """
    Soft delete (archive) a product model.

    Rule:
    - If the model has any published standard versions, deletion is disallowed.
    - If any SKU is actively bound to any standard version of this model, deletion is disallowed.
    - Otherwise, archive **standard versions only** by default to avoid accidentally removing sample versions.

    Rationale:
    - The UI has separate entrances: 打样模型 / 标准模型.
    - Some older clients may still call `DELETE /product-models/{id}` from the 标准入口.
      If we cascade-archive all versions, it will look like “删除标准把打样也删了”.
    - For safety, default behavior is aligned with 标准入口：only archive `standard` versions.
    """
    model = _get_model_or_404(model_id, db)

    published_std_cnt = (
        db.query(models.ProductModelVersion)
        .filter(
            models.ProductModelVersion.model_id == model.id,
            models.ProductModelVersion.version_kind == "standard",
            models.ProductModelVersion.version_status == "published",
            models.ProductModelVersion.is_archived.is_(False),
        )
        .count()
    )
    if published_std_cnt > 0:
        raise HTTPException(status_code=400, detail="该模型存在已发布标准版本（published），不允许删除")

    # Block if any active SKU binding exists for this model's standard versions.
    std_version_ids = [
        x[0]
        for x in db.query(models.ProductModelVersion.id)
        .filter(
            models.ProductModelVersion.model_id == model.id,
            models.ProductModelVersion.version_kind == "standard",
            models.ProductModelVersion.is_archived.is_(False),
        )
        .all()
        if x and x[0]
    ]
    if std_version_ids:
        bound_cnt = (
            db.query(models.SkuModelVersionMapping)
            .filter(
                models.SkuModelVersionMapping.model_version_id.in_(std_version_ids),
                models.SkuModelVersionMapping.is_archived.is_(False),
                models.SkuModelVersionMapping.is_active.is_(True),
            )
            .count()
        )
        if bound_cnt > 0:
            raise HTTPException(status_code=400, detail="该模型存在SKU绑定关系（active），不允许删除")

    # Safety default: archive standard versions only (do NOT archive sample versions).
    (
        db.query(models.ProductModelVersion)
        .filter(
            models.ProductModelVersion.model_id == model.id,
            models.ProductModelVersion.version_kind == "standard",
            models.ProductModelVersion.is_archived.is_(False),
        )
        .update({"is_archived": True}, synchronize_session=False)
    )

    # If model has no remaining non-archived versions, archive model as well.
    remain_cnt = (
        db.query(models.ProductModelVersion)
        .filter(models.ProductModelVersion.model_id == model.id, models.ProductModelVersion.is_archived.is_(False))
        .count()
    )
    if remain_cnt == 0:
        model.is_archived = True
    audit_service.log_audit_event(
        db,
        target_type="product_model",
        target_id=model.id,
        action="delete",
        actor_id="system",
        payload={"model_code": model.model_code},
    )
    db.commit()
    return None


@router.post("/{model_id}/archive-sample", status_code=status.HTTP_204_NO_CONTENT)
def archive_sample_versions_only(model_id: str, db: Session = Depends(get_db)):
    """
    Archive sample versions of a model only (do NOT archive standard versions).

    Rationale:
    - The UI has separate entrances: 打样模型 / 标准模型.
    - Users may want to "删除打样" without affecting derived 标准版本.
    """
    model = _get_model_or_404(model_id, db)

    # Archive sample versions
    (
        db.query(models.ProductModelVersion)
        .filter(
            models.ProductModelVersion.model_id == model.id,
            models.ProductModelVersion.version_kind == "sample",
            models.ProductModelVersion.is_archived.is_(False),
        )
        .update({"is_archived": True}, synchronize_session=False)
    )

    # If model has no remaining non-archived versions, archive model as well.
    remain_cnt = (
        db.query(models.ProductModelVersion)
        .filter(models.ProductModelVersion.model_id == model.id, models.ProductModelVersion.is_archived.is_(False))
        .count()
    )
    if remain_cnt == 0:
        model.is_archived = True

    audit_service.log_audit_event(
        db,
        target_type="product_model",
        target_id=model.id,
        action="archive_sample_versions",
        actor_id="system",
        payload={"model_code": model.model_code},
    )
    db.commit()
    return None


@router.post("/{model_id}/archive-standard", status_code=status.HTTP_204_NO_CONTENT)
def archive_standard_versions_only(model_id: str, db: Session = Depends(get_db)):
    """
    Archive standard versions of a model only (do NOT archive sample versions).

    Rationale:
    - The UI has separate entrances: 打样模型 / 标准模型.
    - Users may want to "删除标准" without affecting existing 打样版本。
    """
    model = _get_model_or_404(model_id, db)

    # Same guardrails as deleting a whole model (standard side is subject to publish/bind constraints).
    published_std_cnt = (
        db.query(models.ProductModelVersion)
        .filter(
            models.ProductModelVersion.model_id == model.id,
            models.ProductModelVersion.version_kind == "standard",
            models.ProductModelVersion.version_status == "published",
            models.ProductModelVersion.is_archived.is_(False),
        )
        .count()
    )
    if published_std_cnt > 0:
        raise HTTPException(status_code=400, detail="该模型存在已发布标准版本（published），不允许删除标准版本")

    std_version_ids = [
        x[0]
        for x in db.query(models.ProductModelVersion.id)
        .filter(
            models.ProductModelVersion.model_id == model.id,
            models.ProductModelVersion.version_kind == "standard",
            models.ProductModelVersion.is_archived.is_(False),
        )
        .all()
        if x and x[0]
    ]
    if std_version_ids:
        bound_cnt = (
            db.query(models.SkuModelVersionMapping)
            .filter(
                models.SkuModelVersionMapping.model_version_id.in_(std_version_ids),
                models.SkuModelVersionMapping.is_archived.is_(False),
                models.SkuModelVersionMapping.is_active.is_(True),
            )
            .count()
        )
        if bound_cnt > 0:
            raise HTTPException(status_code=400, detail="该模型存在SKU绑定关系（active），不允许删除标准版本")

    # Archive standard versions
    (
        db.query(models.ProductModelVersion)
        .filter(
            models.ProductModelVersion.model_id == model.id,
            models.ProductModelVersion.version_kind == "standard",
            models.ProductModelVersion.is_archived.is_(False),
        )
        .update({"is_archived": True}, synchronize_session=False)
    )

    # If model has no remaining non-archived versions, archive model as well.
    remain_cnt = (
        db.query(models.ProductModelVersion)
        .filter(models.ProductModelVersion.model_id == model.id, models.ProductModelVersion.is_archived.is_(False))
        .count()
    )
    if remain_cnt == 0:
        model.is_archived = True

    audit_service.log_audit_event(
        db,
        target_type="product_model",
        target_id=model.id,
        action="archive_standard_versions",
        actor_id="system",
        payload={"model_code": model.model_code},
    )
    db.commit()
    return None

