from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..dependencies import get_db_session
from ..schemas import (
    PaginatedShippingRuleResponse,
    ShippingRuleEvaluateRequest,
    ShippingRuleEvaluateResponse,
    ShippingRuleRead,
    ShippingRuleUpsertRequest,
)
from ..services import shipping_rule_service


router = APIRouter(prefix="/shipping-rules", tags=["ShippingRules"])


@router.get("", response_model=PaginatedShippingRuleResponse)
def list_rules(
    search: Optional[str] = Query(None, max_length=128),
    is_active: Optional[bool] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db_session),
):
    total, items = shipping_rule_service.list_shipping_rules(
        db,
        search=search,
        is_active=is_active,
        page=page,
        page_size=page_size,
    )
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [ShippingRuleRead.from_orm(x) for x in items],
    }


@router.post("", response_model=ShippingRuleRead)
def create_rule(payload: ShippingRuleUpsertRequest, db: Session = Depends(get_db_session)):
    rule = shipping_rule_service.create_shipping_rule(
        db,
        payload={
            "rule_name": payload.rule_name,
            "priority": payload.priority,
            "is_active": payload.is_active if payload.is_active is not None else True,
            "conditions": payload.conditions or {},
            "outputs": payload.outputs or [],
            "notes": payload.notes,
            "metadata": payload.metadata or {},
        },
    )
    return ShippingRuleRead.from_orm(rule)


@router.patch("/{rule_id}", response_model=ShippingRuleRead)
def patch_rule(rule_id: str, payload: ShippingRuleUpsertRequest, db: Session = Depends(get_db_session)):
    try:
        rule = shipping_rule_service.update_shipping_rule(
            db,
            rule_id=rule_id,
            patch={
                "rule_name": payload.rule_name,
                "priority": payload.priority,
                "is_active": payload.is_active,
                "conditions": payload.conditions,
                "outputs": payload.outputs,
                "notes": payload.notes,
                "metadata": payload.metadata,
            },
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return ShippingRuleRead.from_orm(rule)


@router.post("/{rule_id}/archive")
def archive_rule(rule_id: str, db: Session = Depends(get_db_session)):
    shipping_rule_service.archive_shipping_rule(db, rule_id=rule_id)
    return {"ok": True}


@router.post("/evaluate", response_model=ShippingRuleEvaluateResponse)
def evaluate(payload: ShippingRuleEvaluateRequest, db: Session = Depends(get_db_session)):
    ctx = shipping_rule_service.EvaluateContext(
        shop_code=payload.shop_code or "",
        channel=payload.channel or "",
        shipping_method=payload.shipping_method or "",
        is_merge=payload.is_merge,
        province=payload.province or "",
        city=payload.city or "",
        weight_kg=payload.weight_kg,
        volume_m3=payload.volume_m3,
        package_count=payload.package_count,
        tokens=payload.tokens or [],
    )
    result = shipping_rule_service.evaluate_shipping_rules(
        db,
        ctx=ctx,
        include_disabled_rules=bool(payload.include_disabled_rules),
    )
    return ShippingRuleEvaluateResponse(**result)


