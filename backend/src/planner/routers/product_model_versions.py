from __future__ import annotations

from decimal import Decimal
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ...database import get_db
from .. import models, schemas
from ..services import product_model_service

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
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
):
    filters = product_model_service.ProductModelVersionFilters(
        search=search, version_kind=version_kind, version_status=version_status
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
        product_model_service.sync_version_lines_from_modules(db, version=v, keep_overrides=payload.keep_overrides)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    # IMPORTANT: SessionLocal has autoflush=False; without an explicit commit, sync results
    # won't be persisted nor visible to subsequent reads in this request.
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












