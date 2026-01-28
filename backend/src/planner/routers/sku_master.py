from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session
import httpx

from ..dependencies import get_db_session
from .. import schemas
from ..schemas import PaginatedSkuMasterResponse, SkuMasterImportResponse, SkuMasterRead
from ..services import sku_master_service
from ..services import sku_master_image_storage
from ...config import settings
from .. import models


router = APIRouter(prefix="/sku-master", tags=["SKU Master"])


@router.post("/import", response_model=SkuMasterImportResponse)
async def import_sku_master_xlsx(
    file: UploadFile = File(...),
    requested_by: str | None = Form(None),
    db: Session = Depends(get_db_session),
):
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Empty file")
    result = sku_master_service.import_erp_sku_master_xlsx(db, file_bytes=contents, requested_by=requested_by)
    return result


@router.get("", response_model=PaginatedSkuMasterResponse)
def list_sku_master(
    search: str | None = None,
    channel: str | None = None,
    match_status: str | None = None,
    bound_state: str | None = None,
    bound_model_id: str | None = None,
    bound_model_code: str | None = None,
    bound_version_id: str | None = None,
    spec_mismatch: bool | None = None,
    preparse_state: str | None = None,
    include_terms: str | None = None,
    exclude_terms: str | None = None,
    match_scope: str | None = None,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db_session),
):
    total, items = sku_master_service.list_sku_master(
        db,
        search=search,
        channel=channel,
        match_status=match_status,
        bound_state=bound_state,
        bound_model_id=bound_model_id,
        bound_model_code=bound_model_code,
        bound_version_id=bound_version_id,
        spec_mismatch=spec_mismatch,
        preparse_state=preparse_state,
        include_terms=include_terms,
        exclude_terms=exclude_terms,
        match_scope=match_scope,
        page=page,
        page_size=page_size,
    )
    return {"total": total, "page": page, "page_size": page_size, "items": items}


@router.get("/published-standard-models", response_model=schemas.PublishedStandardModelCandidateListResponse)
def list_published_standard_models(
    search: str | None = None,
    limit: int = 50,
    db: Session = Depends(get_db_session),
):
    items = sku_master_service.list_published_standard_model_candidates(db, search=search, limit=limit)
    return {"items": items}


@router.post("/bind-by-model", response_model=schemas.SkuMasterBindByModelResponse)
def bind_by_model(payload: schemas.SkuMasterBindByModelRequest, db: Session = Depends(get_db_session)):
    try:
        return sku_master_service.bind_sku_master_by_model(
            db,
            model_id=payload.model_id,
            sku_master_ids=payload.sku_master_ids,
            requested_by=payload.requested_by,
            allow_rebind=payload.allow_rebind,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/bind-by-model/bulk", response_model=schemas.SkuMasterBindByModelBulkResponse)
def bind_by_model_bulk(payload: schemas.SkuMasterBindByModelBulkRequest, db: Session = Depends(get_db_session)):
    """
    Bind all unbound sku masters matched by current filters (server-side).
    This enables UI "implicit select all" across pages, with an exclusion list for unchecked rows.
    """
    try:
        return sku_master_service.bind_sku_master_by_model_bulk(
            db,
            model_id=payload.model_id,
            requested_by=payload.requested_by,
            limit=payload.limit,
            bound_state=payload.bound_state,
            allow_rebind=payload.allow_rebind,
            search=payload.search,
            channel=payload.channel,
            match_status=payload.match_status,
            spec_mismatch=payload.spec_mismatch,
            preparse_state=payload.preparse_state,
            include_terms=payload.include_terms,
            exclude_terms=payload.exclude_terms,
            match_scope=payload.match_scope,
            bound_model_id=payload.bound_model_id,
            bound_model_code=payload.bound_model_code,
            bound_version_id=payload.bound_version_id,
            excluded_sku_master_ids=payload.excluded_sku_master_ids,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/bind-by-bundle", response_model=schemas.SkuMasterBindByBundleTemplateResponse)
def bind_by_bundle(payload: schemas.SkuMasterBindByBundleTemplateRequest, db: Session = Depends(get_db_session)):
    try:
        return sku_master_service.bind_sku_master_by_bundle_template(
            db,
            template_id=payload.template_id,
            sku_master_ids=payload.sku_master_ids,
            requested_by=payload.requested_by,
            allow_rebind=payload.allow_rebind,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/bind-by-bundle/bulk", response_model=schemas.SkuMasterBindByBundleTemplateBulkResponse)
def bind_by_bundle_bulk(payload: schemas.SkuMasterBindByBundleTemplateBulkRequest, db: Session = Depends(get_db_session)):
    try:
        return sku_master_service.bind_sku_master_by_bundle_template_bulk(
            db,
            template_id=payload.template_id,
            requested_by=payload.requested_by,
            limit=payload.limit,
            bound_state=payload.bound_state,
            allow_rebind=payload.allow_rebind,
            search=payload.search,
            channel=payload.channel,
            match_status=payload.match_status,
            spec_mismatch=payload.spec_mismatch,
            preparse_state=payload.preparse_state,
            include_terms=payload.include_terms,
            exclude_terms=payload.exclude_terms,
            match_scope=payload.match_scope,
            bound_model_id=payload.bound_model_id,
            bound_model_code=payload.bound_model_code,
            bound_version_id=payload.bound_version_id,
            excluded_sku_master_ids=payload.excluded_sku_master_ids,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/auto-bind/preview", response_model=schemas.SkuMasterAutoBindPreviewResponse)
def auto_bind_preview(payload: schemas.SkuMasterAutoBindPreviewRequest, db: Session = Depends(get_db_session)):
    return sku_master_service.auto_bind_preview(db, limit=payload.limit, scan_limit=payload.scan_limit)


@router.post("/auto-bind/execute", response_model=schemas.SkuMasterAutoBindExecuteResponse)
def auto_bind_execute(payload: schemas.SkuMasterAutoBindExecuteRequest, db: Session = Depends(get_db_session)):
    return sku_master_service.auto_bind_execute(
        db,
        limit=payload.limit,
        requested_by=payload.requested_by,
        sku_master_ids=payload.sku_master_ids,
        scan_limit=50000,
    )


@router.get("/{sku_id}", response_model=SkuMasterRead)
def get_sku_master(sku_id: str, db: Session = Depends(get_db_session)):
    row = sku_master_service.get_sku_master(db, sku_id)
    if not row:
        raise HTTPException(status_code=404, detail="SKU master not found")
    return row


def _download_image(url: str) -> tuple[bytes, str | None]:
    """
    Isolated for tests (can be monkeypatched).
    """
    with httpx.Client(timeout=20.0, follow_redirects=True) as client:
        resp = client.get(url)
    resp.raise_for_status()
    return resp.content, resp.headers.get("content-type")


@router.get("/{sku_id}/images/{kind}")
def get_sku_master_image(
    sku_id: str,
    kind: str,
    force_refresh: int | None = None,
    db: Session = Depends(get_db_session),
):
    """
    Proxy + on-demand local caching for SKU master images (spec/product).
    Use this instead of directly loading 3rd-party (e.g. alicdn) URLs on factory scan pages.
    """
    kind2 = (kind or "").strip().lower()
    if kind2 not in ("spec", "product"):
        raise HTTPException(status_code=400, detail="kind must be spec|product")

    row = db.get(models.SkuMaster, sku_id)
    if not row or getattr(row, "is_archived", False):
        raise HTTPException(status_code=404, detail="SKU master not found")

    images = getattr(row, "images_json", {}) or {}
    if not isinstance(images, dict):
        images = {}
    key = "spec_image" if kind2 == "spec" else "product_image"
    source_url = (images.get(key) or "").strip()
    if not source_url:
        raise HTTPException(status_code=404, detail="Image not found")

    meta = getattr(row, "metadata_json", {}) or {}
    if not isinstance(meta, dict):
        meta = {}

    if settings.planner_persist_sku_images and not force_refresh:
        ref = sku_master_image_storage.get_local_image_ref(meta, kind2)
        if ref and ref.path:
            try:
                data = sku_master_image_storage.read_local_bytes(ref)
                return Response(content=data, media_type=ref.content_type or "application/octet-stream")
            except Exception:
                # fall back to remote fetch
                pass

    # Remote fetch (and optionally persist)
    try:
        data, ct = _download_image(source_url)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Failed to fetch image: {exc}") from exc

    if settings.planner_persist_sku_images:
        ref2 = sku_master_image_storage.persist_bytes(
            sku_master_id=row.id,
            kind=kind2,
            source_url=source_url,
            content=data,
            content_type=ct,
        )
        sku_master_image_storage.set_local_image_ref(meta, kind2, ref2)
        row.metadata_json = meta
        db.add(row)
        db.commit()
        # best-effort cleanup
        sku_master_image_storage.maybe_cleanup()

    return Response(content=data, media_type=ct or "application/octet-stream")

@router.get("/by-barcode/{barcode}", response_model=schemas.SkuMasterScanResponse)
def get_sku_master_by_barcode(
    barcode: str,
    channel: str | None = None,
    limit: int = 20,
    db: Session = Depends(get_db_session),
):
    """
    Scan/production use case: query sku master by ERP barcode (SSOT).
    Also returns shop-level SKUs (platform_sku_id dimension) when table/migration exists.
    """
    row = sku_master_service.get_by_barcode(db, barcode)
    if not row:
        raise HTTPException(status_code=404, detail="SKU master not found")
    shop_skus = []
    try:
        shop_skus = sku_master_service.list_shop_skus_by_barcode(
            db, erp_sku_barcode=barcode, channel=channel, limit=limit
        )
    except Exception:
        shop_skus = []
    return {"sku_master": row, "shop_skus": shop_skus}


@router.post("/{sku_id}/spec-preparse", response_model=schemas.SkuMasterSpecPreparseSaveResponse)
def save_spec_preparse(
    sku_id: str,
    payload: schemas.SkuMasterSpecPreparseSaveRequest,
    db: Session = Depends(get_db_session),
):
    try:
        return sku_master_service.save_spec_preparse(
            db,
            sku_id=sku_id,
            spec_text=payload.spec_text,
            width_cm=payload.width_cm,
            height_cm=payload.height_cm,
            diameter_cm=payload.diameter_cm,
            requested_by=payload.requested_by,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/spec-preparse/bulk", response_model=schemas.SkuMasterSpecPreparseBulkResponse)
def bulk_save_spec_preparse(
    payload: schemas.SkuMasterSpecPreparseBulkRequest,
    db: Session = Depends(get_db_session),
):
    try:
        return sku_master_service.bulk_save_spec_preparse(
            db,
            limit=payload.limit,
            search=payload.search,
            channel=payload.channel,
            match_status=payload.match_status,
            include_terms=payload.include_terms,
            exclude_terms=payload.exclude_terms,
            match_scope=payload.match_scope,
            bound_model_id=payload.bound_model_id,
            bound_model_code=payload.bound_model_code,
            bound_version_id=payload.bound_version_id,
            preparse_state=payload.preparse_state,
            cursor_id=payload.cursor_id,
            excluded_sku_ids=payload.excluded_sku_ids,
            skip_if_same_hash=payload.skip_if_same_hash,
            requested_by=payload.requested_by,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/spec-preparse/preview", response_model=schemas.SkuMasterSpecPreparsePreviewResponse)
def preview_spec_preparse(
    payload: schemas.SkuMasterSpecPreparsePreviewRequest,
    db: Session = Depends(get_db_session),
):
    return sku_master_service.preview_spec_preparse(
        db,
        limit=payload.limit,
        search=payload.search,
        channel=payload.channel,
        match_status=payload.match_status,
        include_terms=payload.include_terms,
        exclude_terms=payload.exclude_terms,
        match_scope=payload.match_scope,
        bound_model_id=payload.bound_model_id,
        bound_model_code=payload.bound_model_code,
        bound_version_id=payload.bound_version_id,
        preparse_state=payload.preparse_state,
    )


@router.post("/spec-preparse/execute", response_model=schemas.SkuMasterSpecPreparseExecuteResponse)
def execute_spec_preparse(
    payload: schemas.SkuMasterSpecPreparseExecuteRequest,
    db: Session = Depends(get_db_session),
):
    return sku_master_service.execute_spec_preparse(
        db,
        sku_ids=payload.sku_ids,
        skip_if_same_hash=payload.skip_if_same_hash,
        requested_by=payload.requested_by,
    )


