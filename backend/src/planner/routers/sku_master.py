from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..dependencies import get_db_session
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
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db_session),
):
    total, items = sku_master_service.list_sku_master(
        db,
        search=search,
        channel=channel,
        match_status=match_status,
        page=page,
        page_size=page_size,
    )
    return {"total": total, "page": page, "page_size": page_size, "items": items}


@router.get("/{sku_id}", response_model=SkuMasterRead)
def get_sku_master(sku_id: str, db: Session = Depends(get_db_session)):
    row = sku_master_service.get_sku_master(db, sku_id)
    if not row:
        raise HTTPException(status_code=404, detail="SKU master not found")
    return row


