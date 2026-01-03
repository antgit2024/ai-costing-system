from __future__ import annotations

import io
import json
from decimal import Decimal
from typing import List, Optional

from fastapi import File, UploadFile
from fastapi.responses import StreamingResponse

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ...database import get_db
from .. import models, schemas
from ..services import audit_service, line_variant_service, model_version_image_storage, product_model_service

router = APIRouter(tags=["product-model-versions"])


def _get_model_or_404(db: Session, model_id: str) -> models.ProductModel:
    model = product_model_service.get_model(db, model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Product model not found")
    return model


def _get_version_or_404(db: Session, version_id: str) -> models.ProductModelVersion:
    v = product_model_service.get_model_version(db, version_id)
    if not v:
        raise HTTPException(status_code=404, detail="Product model version not found")
    return v


def _serialize_version_images(version: models.ProductModelVersion) -> schemas.ModelVersionImagesResponse:
    meta = version.metadata_json or {}
    items = meta.get("version_images") or []
    if not isinstance(items, list):
        items = []
    out: List[schemas.ModelVersionImageRead] = []
    for idx, it in enumerate(items):
        if isinstance(it, dict) and it.get("path"):
            out.append(
                schemas.ModelVersionImageRead(
                    index=idx,
                    url=f"/api/planner/product-model-versions/{version.id}/images/{idx}",
                    filename=it.get("filename"),
                    content_type=it.get("content_type"),
                )
            )
        elif isinstance(it, str) and it:
            out.append(
                schemas.ModelVersionImageRead(
                    index=idx,
                    url=f"/api/planner/product-model-versions/{version.id}/images/{idx}",
                    filename=None,
                    content_type=None,
                )
            )
    return schemas.ModelVersionImagesResponse(version_id=version.id, images=out)


@router.get(
    "/product-model-versions/{version_id}/images/{image_index}",
    response_class=StreamingResponse,
)
def download_model_version_image(
    version_id: str,
    image_index: int,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    v = _get_version_or_404(db, version_id)
    meta = dict(v.metadata_json or {})
    ref = model_version_image_storage.get_local_image_ref(meta, image_index)
    if ref is None:
        raise HTTPException(status_code=404, detail="Image not found")
    try:
        content = model_version_image_storage.read_local_bytes(ref)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Image file missing")
    media_type = ref.content_type or "application/octet-stream"
    return StreamingResponse(io.BytesIO(content), media_type=media_type)


@router.post(
    "/product-model-versions/{version_id}/images",
    response_model=schemas.ModelVersionImagesResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_model_version_image(
    version_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> schemas.ModelVersionImagesResponse:
    """
    Upload an image for a specific model version.
    Images are persisted to PLANNER_MEDIA_DIR and referenced via version.metadata_json.version_images.
    Limit: 10MB.
    """
    v = _get_version_or_404(db, version_id)
    content = await file.read()
    if content is None:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="文件过大：请控制在 10MB 内")

    meta0 = v.metadata_json or {}
    items0 = meta0.get("version_images") or []
    if not isinstance(items0, list):
        items0 = []
    idx = len(items0)

    ref = model_version_image_storage.persist_bytes(
        version_id=str(v.id),
        image_index=idx,
        filename=str(file.filename or f"image_{idx}"),
        content=content,
        content_type=file.content_type,
    )

    # Deep-copy to avoid SQLAlchemy JSON change-tracking pitfalls on nested mutables.
    meta2 = json.loads(json.dumps(v.metadata_json or {}, ensure_ascii=False))
    model_version_image_storage.set_local_image_ref(meta2, idx, ref)
    v.metadata_json = meta2
    db.commit()
    db.refresh(v)
    return _serialize_version_images(v)


@router.get("/product-models/{model_id}/versions", response_model=List[schemas.ProductModelVersionRead])
def list_product_model_versions(model_id: str, db: Session = Depends(get_db)):
    _ = _get_model_or_404(db, model_id)
    items = product_model_service.list_model_versions(db, model_id)
    return [schemas.ProductModelVersionRead.from_orm(v) for v in items]


@router.get("/product-model-versions", response_model=schemas.PaginatedProductModelVersionResponse)
def list_versions(
    search: str | None = Query(None, max_length=128),
    version_kind: str | None = Query(None, max_length=32),
    version_status: str | None = Query(None, max_length=32),
    structure_standard_code: str | None = Query(None, max_length=128),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
):
    filters = product_model_service.ProductModelVersionFilters(
        search=search,
        version_kind=version_kind,
        version_status=version_status,
        structure_standard_code=structure_standard_code,
    )
    total, rows = product_model_service.list_versions(db, filters=filters, page=page, page_size=page_size)
    items: List[schemas.ProductModelVersionListItem] = []
    for v, m in rows:
        items.append(
            schemas.ProductModelVersionListItem(
                model_id=m.id,
                model_code=m.model_code,
                model_name=m.model_name,
                model_status=m.status,
                version_id=v.id,
                version_kind=v.version_kind,
                version_status=v.version_status,
                version_label=v.version_label,
                created_at=v.created_at,
                updated_at=v.updated_at,
                published_at=v.published_at,
            )
        )
    return schemas.PaginatedProductModelVersionResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=items,
    )


@router.post(
    "/product-models/{model_id}/versions",
    response_model=schemas.ProductModelVersionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_product_model_version(
    model_id: str, payload: schemas.ProductModelVersionCreateRequest, db: Session = Depends(get_db)
):
    model = _get_model_or_404(db, model_id)
    try:
        v = product_model_service.create_model_version(
            db, model=model, version_kind=payload.version_kind, metadata=payload.metadata
        )
        return schemas.ProductModelVersionRead.from_orm(v)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/product-model-versions/{version_id}/lines", response_model=schemas.ProductModelLinesResponse)
def get_version_lines(version_id: str, db: Session = Depends(get_db)):
    v = _get_version_or_404(db, version_id)
    model = db.get(models.ProductModel, v.model_id)
    if not model or model.is_archived:
        raise HTTPException(status_code=404, detail="Product model not found")

    sample, standard = product_model_service._extract_sample_and_standard_from_version(model, v)  # noqa: SLF001
    materials = product_model_service.list_version_material_lines(db, v.id)
    processes = product_model_service.list_version_process_lines(db, v.id)

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


@router.put("/product-model-versions/{version_id}/lines", response_model=schemas.ProductModelLinesResponse)
def update_version_lines(
    version_id: str, payload: schemas.ProductModelLinesUpdateRequest, db: Session = Depends(get_db)
):
    v = _get_version_or_404(db, version_id)
    try:
        product_model_service.replace_version_lines(
            db,
            version=v,
            sample=payload.sample.dict(),
            standard=payload.standard.dict(),
            materials=[m.dict(by_alias=True) for m in payload.materials],
            processes=[p.dict(by_alias=True) for p in payload.processes],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return get_version_lines(version_id, db)


@router.post("/product-model-versions/{version_id}/sync-from-modules", response_model=schemas.ProductModelLinesResponse)
def sync_version_from_modules(
    version_id: str,
    payload: schemas.ProductModelSyncFromModulesRequest,
    db: Session = Depends(get_db),
):
    v = _get_version_or_404(db, version_id)
    try:
        product_model_service.sync_version_lines_from_modules(
            db,
            version=v,
            keep_overrides=payload.keep_overrides,
            module_ids=payload.module_ids,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    # IMPORTANT: SessionLocal has autoflush=False; without an explicit commit, sync results
    # won't be persisted nor visible to subsequent reads in this request.
    db.commit()
    return get_version_lines(version_id, db)


@router.post("/product-model-versions/{version_id}/refresh-material-prices", response_model=schemas.ProductModelLinesResponse)
def refresh_version_material_prices(version_id: str, db: Session = Depends(get_db)):
    """
    Refresh *version* material lines' BOM unit price/unit snapshots from latest master data.
    This does NOT change quantities; it only updates metadata_json.{bom_unit_price,bom_unit}.
    """
    v = _get_version_or_404(db, version_id)
    product_model_service.refresh_version_material_price_snapshots(db, v)
    db.commit()
    return get_version_lines(version_id, db)


@router.post("/product-model-versions/{version_id}/preview", response_model=schemas.ProductModelPreviewResponse)
def preview_version_cost(
    version_id: str, payload: schemas.ProductModelPreviewRequest, db: Session = Depends(get_db)
):
    v = _get_version_or_404(db, version_id)
    try:
        data = product_model_service.preview_version_cost(
            db,
            version=v,
            width_mm=payload.width_mm,
            height_mm=payload.height_mm,
            quantity=payload.quantity,
            sku_hint=payload.sku_hint,
        )
        return schemas.ProductModelPreviewResponse(**data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/product-model-versions/{version_id}/publish",
    response_model=schemas.ProductModelVersionRead,
)
def publish_product_model_version(
    version_id: str, payload: schemas.ProductModelVersionPublishRequest, db: Session = Depends(get_db)
):
    v = _get_version_or_404(db, version_id)
    try:
        v = product_model_service.publish_standard_version(
            db, version=v, published_by=payload.published_by, note=payload.note
        )
        return schemas.ProductModelVersionRead.from_orm(v)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/product-model-versions/{version_id}/clone-model",
    response_model=schemas.CloneModelFromVersionResponse,
    status_code=status.HTTP_201_CREATED,
)
def clone_model_from_version(
    version_id: str,
    payload: schemas.CloneModelFromVersionRequest,
    db: Session = Depends(get_db),
):
    """
    Create a brand new ProductModel (with auto-generated model_code) from a source version.
    Intended for cloning an existing STANDARD version into a new "standard model" template.
    """
    src_version = _get_version_or_404(db, version_id)
    if str(src_version.version_kind or "").strip().lower() != "standard":
        raise HTTPException(status_code=400, detail="仅支持从标准版本（standard）克隆模型")

    src_model = db.get(models.ProductModel, src_version.model_id)
    if not src_model or src_model.is_archived:
        raise HTTPException(status_code=404, detail="Source product model not found")

    # Build new model meta (avoid carrying pointers of the old model).
    src_model_meta = dict(src_model.metadata_json or {})
    for k in (
        "current_draft_version_id",
        "current_published_standard_version_id",
        "current_published_standard_version_label",
    ):
        src_model_meta.pop(k, None)
    # Cloning must NOT carry recognition keywords because they are globally unique.
    # New model should start with empty keywords and let user configure explicitly.
    src_model_meta.pop("recognition_keywords", None)
    # Ensure this cloned model is treated as "standard entry" (affects initial version kind & list filters)
    src_model_meta["entry_context"] = "standard"

    new_name = (payload.model_name or "").strip() or f"{src_model.model_name}（克隆）"

    modules_payload = [
        {
            "module_id": link.module_id,
            "sequence_order": link.sequence_order,
            "notes": link.notes,
            "metadata_json": link.metadata_json or {},
        }
        for link in product_model_service.list_model_modules(db, src_model.id)
    ]

    # Create a new model (auto model_code). Initial draft version kind depends on entry_context.
    new_model = product_model_service.create_model(
        db,
        model_code=None,
        model_name=new_name,
        description=src_model.description,
        category=src_model.category,
        calc_mode=src_model.calc_mode,
        fixed_price=src_model.fixed_price,
        status="draft",
        tags=list(src_model.tags or []),
        standard_width_mm=src_model.standard_width_mm,
        standard_height_mm=src_model.standard_height_mm,
        unit_of_measure=src_model.unit_of_measure,
        metadata=src_model_meta,
        modules=modules_payload,
    )

    # Copy version metadata as a base (keeps placeholder_mappings/derive_template etc if stored there).
    src_vmeta = dict(src_version.metadata_json or {})
    # Prefer using the auto-created draft version (if it is already standard); otherwise create one.
    draft_vid = str((new_model.metadata_json or {}).get("current_draft_version_id") or "").strip()
    draft_v = db.get(models.ProductModelVersion, draft_vid) if draft_vid else None
    if draft_v and str(draft_v.version_kind or "").strip().lower() == "standard":
        # Merge source version metadata into draft version metadata (keep existing sample/standard spec keys)
        merged = dict(draft_v.metadata_json or {})
        merged.update(src_vmeta)
        draft_v.metadata_json = merged
        db.commit()
        db.refresh(draft_v)
        new_std_version = draft_v
    else:
        new_std_version = product_model_service.create_model_version(
            db,
            model=new_model,
            version_kind="standard",
            metadata=src_vmeta,
            commit=True,
        )

    # Copy lines
    sample, standard = product_model_service._extract_sample_and_standard_from_version(src_model, src_version)  # noqa: SLF001

    src_materials = product_model_service.list_version_material_lines(db, src_version.id)
    src_processes = product_model_service.list_version_process_lines(db, src_version.id)

    materials_payload = []
    for item in src_materials:
        meta = dict(item.metadata_json or {})
        materials_payload.append(
            {
                "material_kind": item.material_type,
                "material_ref_id": item.material_ref_id,
                "material_code": item.material_code,
                "material_name": item.material_name,
                "calculation_method": item.calculation_method,
                "sample_used_quantity": meta.get("sample_used_quantity"),
                "standard_used_quantity": meta.get("standard_used_quantity"),
                "fixed_quantity": meta.get("fixed_quantity"),
                "coverage_ratio": meta.get("coverage_ratio"),
                "base_quantity": item.base_quantity,
                "loss_rate": item.loss_rate,
                "notes": item.notes,
                "source_module_id": meta.get("source_module_id"),
                "source_module_code": meta.get("source_module_code"),
                "source_module_name": meta.get("source_module_name"),
                "metadata_json": meta,
            }
        )

    processes_payload = []
    for item in src_processes:
        meta = dict(item.metadata_json or {})
        processes_payload.append(
            {
                "process_id": item.process_id,
                "process_code": None,
                "process_name": None,
                "team_name": meta.get("team_name"),
                "pricing_method": meta.get("pricing_method") or "count",
                "sample_minutes": meta.get("sample_minutes"),
                "standard_minutes": meta.get("standard_minutes"),
                "base_minutes": meta.get("base_minutes") or 0,
                "unit_minutes": meta.get("unit_minutes") or 0,
                "rate_per_minute": meta.get("rate_per_minute"),
                "piece_rate": meta.get("piece_rate"),
                "cost_type": meta.get("cost_type"),
                "notes": item.notes,
                "source_module_id": meta.get("source_module_id"),
                "source_module_code": meta.get("source_module_code"),
                "source_module_name": meta.get("source_module_name"),
                "metadata_json": meta,
            }
        )

    product_model_service.replace_version_lines(
        db,
        version=new_std_version,
        sample=dict(sample),
        standard=dict(standard),
        materials=materials_payload,
        processes=processes_payload,
    )
    db.commit()

    # Optionally copy line variants (overlay) and remap base_line_id by sequence_order
    if payload.include_line_variants:
        old_lines = product_model_service.list_version_material_lines(db, src_version.id)
        new_lines = product_model_service.list_version_material_lines(db, new_std_version.id)
        old_by_seq = {int(l.sequence_order or 0): str(l.id) for l in old_lines}
        new_by_seq = {int(l.sequence_order or 0): str(l.id) for l in new_lines}
        old_id_to_new_id = {}
        for seq, old_id in old_by_seq.items():
            if seq in new_by_seq:
                old_id_to_new_id[old_id] = new_by_seq[seq]

        for v0 in line_variant_service.list_variants(db, version_id=src_version.id):
            base_old = str(v0.base_line_id)
            base_new = old_id_to_new_id.get(base_old)
            # If mapping fails (shouldn't), skip to avoid creating broken variants.
            if not base_new:
                continue
            items0 = line_variant_service.list_items(db, v0.id)
            items_payload = []
            for it in items0:
                items_payload.append(
                    {
                        "sequence_order": it.sequence_order,
                        "material_kind": it.material_kind,
                        "material_ref_id": it.material_ref_id,
                        "material_code": it.material_code,
                        "material_name": it.material_name,
                        "unit_of_measure": it.unit_of_measure,
                        "calculation_method": it.calculation_method,
                        "base_quantity": it.base_quantity,
                            "fixed_quantity": it.fixed_quantity,
                        "coverage_ratio": it.coverage_ratio,
                        "loss_rate": it.loss_rate,
                        "metadata_json": it.metadata_json or {},
                    }
                )
            line_variant_service.create_variant(
                db,
                version_id=new_std_version.id,
                base_line_id=base_new,
                priority=int(v0.priority or 0),
                enabled=bool(v0.enabled),
                action=str(v0.action),
                stop_on_hit=bool(v0.stop_on_hit),
                notes=v0.notes,
                conditions=dict(v0.conditions_json or {}),
                metadata=dict(v0.metadata_json or {}),
                items=items_payload,
            )

    audit_service.log_audit_event(
        db,
        target_type="product_model",
        target_id=new_model.id,
        action="clone_from_version",
        actor_id=payload.operator_id or "system",
        payload={"source_version_id": src_version.id, "source_model_id": src_model.id},
    )
    db.commit()

    return schemas.CloneModelFromVersionResponse(
        new_model_id=new_model.id,
        new_model_code=new_model.model_code,
        new_model_name=new_model.model_name,
        new_standard_version_id=new_std_version.id,
        new_standard_version_label=new_std_version.version_label,
    )


@router.post(
    "/sku-model-version-mapping",
    response_model=schemas.SkuModelVersionMappingRead,
    status_code=status.HTTP_201_CREATED,
)
def bind_sku(
    payload: schemas.SkuModelVersionMappingCreateRequest,
    db: Session = Depends(get_db),
):
    try:
        row = product_model_service.bind_sku_to_version(
            db,
            sku_code=payload.sku_code,
            version_id=payload.model_version_id,
            source_system=payload.source_system,
            metadata=payload.metadata,
        )
        return schemas.SkuModelVersionMappingRead.from_orm(row)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/sku-model-version-mapping", response_model=List[schemas.SkuModelVersionMappingRead])
def list_sku_bindings(
    sku_code: str = Query(..., max_length=64),
    include_inactive: bool = Query(False),
    db: Session = Depends(get_db),
):
    q = db.query(models.SkuModelVersionMapping).filter(
        models.SkuModelVersionMapping.sku_code == sku_code,
        models.SkuModelVersionMapping.is_archived.is_(False),
    )
    if not include_inactive:
        q = q.filter(models.SkuModelVersionMapping.is_active.is_(True))
    items = q.order_by(models.SkuModelVersionMapping.created_at.desc()).all()
    return [schemas.SkuModelVersionMappingRead.from_orm(x) for x in items]


@router.post("/sku-preview", response_model=schemas.ProductModelSkuPreviewResponse)
def preview_by_sku(payload: schemas.ProductModelSkuPreviewRequest, db: Session = Depends(get_db)):
    sku = payload.sku_code.strip()
    parsed = product_model_service.parse_sku_code(sku)
    width = payload.width_mm
    height = payload.height_mm
    qty = payload.quantity
    if width is None and parsed.get("width_mm") is not None:
        width = Decimal(str(parsed["width_mm"]))
    if height is None and parsed.get("height_mm") is not None:
        height = Decimal(str(parsed["height_mm"]))
    if qty is None:
        qty = Decimal("1")

    if width is None or height is None:
        raise HTTPException(status_code=400, detail="SKU 未能解析出尺寸（width_mm/height_mm），请补充 SKU 或手动传入 width_mm/height_mm")

    # Prefer active binding
    binding = product_model_service.get_active_sku_binding(db, sku)
    version = None
    if binding:
        version = product_model_service.get_model_version(db, binding.model_version_id)
    if version is None:
        model_code = str(parsed.get("model_code") or "").strip()
        version = product_model_service.get_latest_published_standard_version_for_model_code(db, model_code)
    if version is None:
        raise HTTPException(status_code=400, detail="未找到可用的已发布标准版本（请先发布标准版本或绑定 SKU）")

    model = db.get(models.ProductModel, version.model_id)
    if not model or model.is_archived:
        raise HTTPException(status_code=404, detail="Product model not found")

    data = product_model_service.preview_version_cost(
        db,
        version=version,
        width_mm=width,
        height_mm=height,
        quantity=qty,
        sku_hint=sku,
    )
    return schemas.ProductModelSkuPreviewResponse(
        **data,
        sku_code=sku,
        model_id=model.id,
        model_code=model.model_code,
        version_id=version.id,
        version_label=version.version_label,
        parsed=parsed,
    )


@router.post(
    "/product-model-versions/{source_version_id}/derive-standard",
    response_model=schemas.DeriveStandardResponse,
)
def derive_standard_from_sample(
    source_version_id: str,
    payload: schemas.DeriveStandardRequest,
    db: Session = Depends(get_db),
):
    source = _get_version_or_404(db, source_version_id)
    try:
        target, stats = product_model_service.derive_standard_version(
            db,
            source_sample_version=source,
            target_mode=payload.target_mode,
            target_standard_version_id=payload.target_standard_version_id,
            apply_to=payload.apply_to,
        )
        return schemas.DeriveStandardResponse(
            standard_version_id=target.id,
            created=payload.target_mode == "create_new",
            overwritten=payload.target_mode == "overwrite_draft",
            line_stats=stats,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/product-model-versions/{version_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product_model_version(version_id: str, db: Session = Depends(get_db)):
    """
    Soft delete a product model version.

    Rules:
    - Standard versions:
      - Only draft standard versions can be deleted.
      - Published/archived (or any non-draft) standard versions cannot be deleted.
    - Sample versions:
      - If any non-archived standard version was derived from this sample version,
        deletion is disallowed.
    """
    v = _get_version_or_404(db, version_id)
    if (v.version_kind or "") == "standard":
        if (v.version_status or "") != "draft":
            raise HTTPException(status_code=400, detail="已发布/已归档的标准版本不允许删除")
        v.is_archived = True
        db.commit()
        return None

    if (v.version_kind or "") != "sample":
        raise HTTPException(status_code=400, detail="仅允许删除打样版本（sample）或未发布的标准版本（standard draft）")

    # NOTE: SQLAlchemy JSON `.astext` is dialect-dependent; avoid it.
    # Use a lightweight Python-side check instead.
    std_versions = (
        db.query(models.ProductModelVersion)
        .filter(
            models.ProductModelVersion.model_id == v.model_id,
            models.ProductModelVersion.version_kind == "standard",
            models.ProductModelVersion.is_archived.is_(False),
        )
        .all()
    )
    derived_cnt = 0
    for sv in std_versions:
        meta = sv.metadata_json or {}
        if str(meta.get("derived_from_version_id") or "") == v.id:
            derived_cnt += 1
            break
    if derived_cnt > 0:
        raise HTTPException(status_code=400, detail="该打样版本已生成标准版本，不允许删除")

    v.is_archived = True
    db.commit()
    return None












