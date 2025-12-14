from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from .. import models, schemas


def ensure_line_item(db: Session, line_item_id: str) -> models.CostLineItem:
    line_item = db.get(models.CostLineItem, line_item_id)
    if not line_item or line_item.is_archived:
        raise HTTPException(status_code=404, detail="Line item not found")
    return line_item


def validate_supplier_quote(
    db: Session, line_item: models.CostLineItem, payload: schemas.SupplierQuoteCreate
) -> None:
    if payload.currency != line_item.currency:
        raise HTTPException(status_code=400, detail="Quote currency must match line item")
    if payload.unit_cost <= 0:
        raise HTTPException(status_code=400, detail="Unit cost must be positive")

    existing = (
        db.query(models.SupplierQuote)
        .filter(
            models.SupplierQuote.line_item_id == line_item.id,
            models.SupplierQuote.quote_version == payload.quote_version,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="Quote version already exists")


def validate_preferred_quote(db: Session, line_item: models.CostLineItem, quote_id: str) -> None:
    quote = db.get(models.SupplierQuote, quote_id)
    if not quote or quote.line_item_id != line_item.id:
        raise HTTPException(status_code=400, detail="Preferred quote is invalid for line item")


def create_supplier_quote(
    db: Session,
    payload: schemas.SupplierQuoteCreate,
    set_preferred: bool = False,
) -> models.SupplierQuote:
    line_item = ensure_line_item(db, payload.line_item_id)
    validate_supplier_quote(db, line_item, payload)

    quote = models.SupplierQuote(**payload.dict())
    db.add(quote)
    db.flush()
    if set_preferred:
        line_item.preferred_quote_id = quote.id
    db.commit()
    db.refresh(quote)
    return quote
