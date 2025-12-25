from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..dependencies import get_db_session
from .. import schemas
from ..schemas import PaginatedSkuMasterResponse, SkuMasterImportResponse, SkuMasterRead
from ..services import sku_master_service


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


