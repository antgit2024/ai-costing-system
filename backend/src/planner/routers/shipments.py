from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..dependencies import get_db_session
from ..schemas import BomSnapshotRead, ShipmentExceptionRead, ShipmentImportBatchRead
from ..services import shipment_import_service


router = APIRouter(prefix="/shipments", tags=["Shipments"])


@router.post("/import", response_model=ShipmentImportBatchRead)
async def import_shipments_xlsx(
    file: UploadFile = File(...),
    export_date: str | None = Form(None),
    requested_by: str | None = Form(None),
    db: Session = Depends(get_db_session),
):
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Empty file")
    batch = shipment_import_service.import_shipment_xlsx(
        db,
        file_name=file.filename or "shipment.xlsx",
        file_bytes=contents,
        export_date=export_date,
        requested_by=requested_by,
    )
    return batch


@router.get("/import-batches/{batch_id}", response_model=ShipmentImportBatchRead)
def get_import_batch(batch_id: str, db: Session = Depends(get_db_session)):
    batch = shipment_import_service.get_batch(db, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    return batch


@router.get("/exceptions", response_model=list[ShipmentExceptionRead])
def list_exceptions(batch_id: str, db: Session = Depends(get_db_session)):
    return shipment_import_service.list_exceptions(db, batch_id=batch_id)


@router.get("/bom-snapshots", response_model=list[BomSnapshotRead])
def list_bom_snapshots(batch_id: str, db: Session = Depends(get_db_session)):
    return shipment_import_service.list_bom_snapshots(db, batch_id=batch_id)


