from typing import Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from .. import models, schemas
from ..dependencies import PaginationParams, get_db_session
from ..services import import_service, quote_service

router = APIRouter(tags=["Line Items"])


def _apply_line_item_filters(
    query,
    initiative_id: Optional[str],
    package_id: Optional[str],
    status_filter: Optional[str],
    item_type: Optional[str],
    supplier_id: Optional[str],
    search: Optional[str],
):
    if initiative_id:
        query = query.join(models.CostPackage).filter(models.CostPackage.initiative_id == initiative_id)
    if package_id:
        query = query.filter(models.CostLineItem.package_id == package_id)
    if status_filter:
        query = query.filter(models.CostLineItem.status == status_filter)
    if item_type:
        query = query.filter(models.CostLineItem.type == item_type)
    if supplier_id:
        query = query.filter(models.CostLineItem.supplier_id == supplier_id)
    if search:
        pattern = f"%{search.lower()}%"
        query = query.filter(
            or_(
                func.lower(models.CostLineItem.description).like(pattern),
                func.lower(func.coalesce(models.CostLineItem.reference_code, "")).like(pattern),
            )
        )
    return query


@router.get("/line-items", response_model=schemas.PaginatedLineItemResponse)
def list_line_items(
    initiative_id: Optional[str] = None,
    package_id: Optional[str] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    item_type: Optional[str] = Query(None, alias="type"),
    supplier_id: Optional[str] = None,
    search: Optional[str] = None,
    pagination: PaginationParams = Depends(),
    db: Session = Depends(get_db_session),
):
    query = db.query(models.CostLineItem).filter(models.CostLineItem.is_archived.is_(False))
    query = _apply_line_item_filters(
        query, initiative_id, package_id, status_filter, item_type, supplier_id, search
    )

    total = query.count()
    items = (
        query.order_by(models.CostLineItem.created_at.desc())
        .offset((pagination.page - 1) * pagination.page_size)
        .limit(pagination.page_size)
        .all()
    )

    return schemas.PaginatedLineItemResponse(
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
        items=items,
    )


@router.post(
    "/line-items",
    response_model=schemas.LineItemRead,
    status_code=status.HTTP_201_CREATED,
)
def create_line_item(payload: schemas.LineItemCreate, db: Session = Depends(get_db_session)):
    package = db.get(models.CostPackage, payload.package_id)
    if not package or package.is_archived:
        raise HTTPException(status_code=400, detail="Package does not exist")
    if payload.quantity < 0 or payload.unit_cost_estimate < 0:
        raise HTTPException(status_code=400, detail="Quantity and cost must be positive")

    data = payload.dict()
    metadata = data.pop("metadata", {})
    line_item = models.CostLineItem(**data, metadata_json=metadata)
    db.add(line_item)
    db.commit()
    db.refresh(line_item)
    return line_item


def _update_line_item_instance(
    db: Session,
    line_item: models.CostLineItem,
    payload: schemas.LineItemUpdate,
) -> models.CostLineItem:
    data = payload.dict(exclude_unset=True)
    metadata = data.pop("metadata", None)
    if metadata is not None:
        data["metadata_json"] = metadata
    if "preferred_quote_id" in data and data["preferred_quote_id"]:
        quote_service.validate_preferred_quote(db, line_item, data["preferred_quote_id"])
    for numeric_field in ("quantity", "unit_cost_estimate"):
        if numeric_field in data and data[numeric_field] is not None and data[numeric_field] < 0:
            raise HTTPException(status_code=400, detail=f"{numeric_field} must be positive")
    for key, value in data.items():
        setattr(line_item, key, value)
    db.commit()
    db.refresh(line_item)
    return line_item


@router.put("/line-items/{line_item_id}", response_model=schemas.LineItemRead)
def update_line_item(
    line_item_id: str,
    payload: schemas.LineItemUpdate,
    db: Session = Depends(get_db_session),
):
    line_item = db.get(models.CostLineItem, line_item_id)
    if not line_item or line_item.is_archived:
        raise HTTPException(status_code=404, detail="Line item not found")
    return _update_line_item_instance(db, line_item, payload)


@router.patch("/line-items/{line_item_id}", response_model=schemas.LineItemRead)
def inline_update_line_item(
    line_item_id: str,
    payload: schemas.LineItemUpdate,
    db: Session = Depends(get_db_session),
):
    line_item = db.get(models.CostLineItem, line_item_id)
    if not line_item or line_item.is_archived:
        raise HTTPException(status_code=404, detail="Line item not found")
    return _update_line_item_instance(db, line_item, payload)


@router.get("/line-items/{line_item_id}", response_model=schemas.LineItemRead)
def get_line_item(line_item_id: str, db: Session = Depends(get_db_session)):
    line_item = db.get(models.CostLineItem, line_item_id)
    if not line_item or line_item.is_archived:
        raise HTTPException(status_code=404, detail="Line item not found")
    return line_item


@router.delete("/line-items/{line_item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_line_item(line_item_id: str, db: Session = Depends(get_db_session)):
    line_item = db.get(models.CostLineItem, line_item_id)
    if not line_item or line_item.is_archived:
        raise HTTPException(status_code=404, detail="Line item not found")
    line_item.is_archived = True
    db.commit()
    return None


@router.post(
    "/line-items/{line_item_id}/supplier-quotes",
    response_model=schemas.SupplierQuoteRead,
    status_code=status.HTTP_201_CREATED,
)
def create_supplier_quote_for_line_item(
    line_item_id: str,
    payload: schemas.SupplierQuoteCreate,
    set_preferred: bool = Query(False, description="Mark as preferred quote"),
    db: Session = Depends(get_db_session),
):
    if payload.line_item_id != line_item_id:
        raise HTTPException(status_code=400, detail="Payload line_item_id mismatch")

    quote = quote_service.create_supplier_quote(db, payload, set_preferred)
    return quote


@router.post(
    "/line-items/import",
    response_model=schemas.PlannerJobRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def import_line_items(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    initiative_id: str = Form(...),
    requested_by: str = Form(...),
    db: Session = Depends(get_db_session),
):
    initiative = db.get(models.CostInitiative, initiative_id)
    if not initiative or initiative.is_archived:
        raise HTTPException(status_code=400, detail="Initiative not found")

    contents = await file.read()
    file_name = file.filename or "line_items.csv"
    job = models.PlannerJob(
        initiative_id=initiative_id,
        file_name=file_name,
        requested_by=requested_by,
        status="pending",
        job_type="line_item_import",
        payload={"file_name": file_name},
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    background_tasks.add_task(import_service.process_import_job, job.id, contents)
    return job


@router.get("/line-items/import-jobs/{job_id}", response_model=schemas.PlannerJobRead)
def get_import_job(job_id: str, db: Session = Depends(get_db_session)):
    job = db.get(models.PlannerJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Import job not found")
    return job
