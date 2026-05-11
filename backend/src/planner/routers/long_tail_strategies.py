"""HTTP endpoints for long-tail COGS rate strategy (Issue 28).

All endpoints live under ``/api/planner/long-tail-strategies``.

Edit policy (per design choice 'all_logged_in'): no extra role check beyond
the existing ``require_staff_role`` already enforced on the parent router;
every mutation records ``actor`` in the strategy's ``metadata.history`` so
post-hoc audit is possible.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..dependencies import get_db_session
from ..schemas import (
    LongTailCogsRateResolvePreviewRequest,
    LongTailCogsRateResolvePreviewResponse,
    LongTailCogsRateStrategyListResponse,
    LongTailCogsRateStrategyRead,
    LongTailCogsRateStrategyUpsertRequest,
)
from .. import models
from ..services import long_tail_strategy_service
from ...config import settings


router = APIRouter(prefix="/long-tail-strategies", tags=["LongTailStrategies"])


_HUB_FIELDS: tuple[str, ...] = (
    "rate_type",
    "scope_type",
    "scope_id",
    "rate_basis",
    "source",
    "effective_from",
    "effective_to",
    "data_quality",
    "cost_center_id",
    "legal_entity_id",
    "production_unit_id",
)


def _to_read(row) -> LongTailCogsRateStrategyRead:
    return LongTailCogsRateStrategyRead(
        id=row.id,
        category=row.category,
        rate=float(row.rate or 0.0),
        keywords=list(row.keywords_json or []),
        priority=int(row.priority or 0),
        enabled=bool(row.enabled),
        note=row.note,
        metadata=dict(row.metadata_json or {}),
        created_at=row.created_at.isoformat() if row.created_at else None,
        updated_at=row.updated_at.isoformat() if row.updated_at else None,
        # v1.3 Cost Rate Hub fields
        rate_type=getattr(row, "rate_type", None) or "cogs",
        scope_type=getattr(row, "scope_type", None) or "category",
        scope_id=getattr(row, "scope_id", None),
        rate_basis=getattr(row, "rate_basis", None) or "pct_of_revenue",
        source=getattr(row, "source", None) or "manual",
        effective_from=row.effective_from.isoformat() if getattr(row, "effective_from", None) else None,
        effective_to=row.effective_to.isoformat() if getattr(row, "effective_to", None) else None,
        data_quality=getattr(row, "data_quality", None),
        cost_center_id=getattr(row, "cost_center_id", None),
        legal_entity_id=getattr(row, "legal_entity_id", None),
        production_unit_id=getattr(row, "production_unit_id", None),
    )


@router.get("", response_model=LongTailCogsRateStrategyListResponse)
def list_strategies(
    include_archived: bool = Query(False),
    rate_type: Optional[str] = Query(
        "cogs",
        description="cogs (default, 兼容老 long-tail) | overhead_rate | labor_per_minute | labor_per_piece | labor_per_sqm | all",
    ),
    db: Session = Depends(get_db_session),
):
    rows = long_tail_strategy_service.list_strategies(
        db,
        include_archived=include_archived,
        rate_type=rate_type or "cogs",
    )
    return LongTailCogsRateStrategyListResponse(
        items=[_to_read(r) for r in rows],
        global_fallback_rate=float(getattr(settings, "long_tail_cogs_rate", 0.55) or 0.55),
    )


@router.post("", response_model=LongTailCogsRateStrategyRead)
def create_strategy(
    payload: LongTailCogsRateStrategyUpsertRequest,
    db: Session = Depends(get_db_session),
):
    rate_type_raw = (payload.rate_type or "cogs").strip()
    is_hub = rate_type_raw != "cogs"

    if is_hub:
        # Hub mode: rate + scope_type required; category is synthesized when missing.
        if payload.rate is None:
            raise HTTPException(status_code=400, detail="rate 必填")
        if not payload.scope_type:
            raise HTTPException(status_code=400, detail="scope_type 必填 (model | category | cost_center | global)")
        if payload.scope_type != "global" and not payload.scope_id:
            raise HTTPException(status_code=400, detail="非 global scope 必须提供 scope_id")
    else:
        if payload.category is None or payload.rate is None:
            raise HTTPException(status_code=400, detail="category 和 rate 必填")

    body: dict = {
        "category": payload.category,
        "rate": payload.rate,
        "keywords": payload.keywords or [],
        "priority": payload.priority if payload.priority is not None else 100,
        "enabled": payload.enabled if payload.enabled is not None else True,
        "note": payload.note,
    }
    for f in _HUB_FIELDS:
        v = getattr(payload, f, None)
        if v is not None:
            body[f] = v
    try:
        row = long_tail_strategy_service.create_strategy(
            db,
            payload=body,
            actor=payload.actor,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _to_read(row)


@router.patch("/{strategy_id}", response_model=LongTailCogsRateStrategyRead)
def patch_strategy(
    strategy_id: str,
    payload: LongTailCogsRateStrategyUpsertRequest,
    db: Session = Depends(get_db_session),
):
    patch: dict = {
        "category": payload.category,
        "rate": payload.rate,
        "keywords": payload.keywords,
        "priority": payload.priority,
        "enabled": payload.enabled,
        "note": payload.note,
    }
    for f in _HUB_FIELDS:
        if getattr(payload, f, None) is not None:
            patch[f] = getattr(payload, f)
    try:
        row = long_tail_strategy_service.update_strategy(
            db,
            strategy_id=strategy_id,
            patch=patch,
            actor=payload.actor,
        )
    except ValueError as exc:
        # Treat 'not found' specially so frontend can distinguish.
        message = str(exc)
        status_code = 404 if "not found" in message else 400
        raise HTTPException(status_code=status_code, detail=message)
    return _to_read(row)


@router.delete("/{strategy_id}")
def delete_strategy(
    strategy_id: str,
    actor: Optional[str] = Query(None),
    db: Session = Depends(get_db_session),
):
    long_tail_strategy_service.delete_strategy(
        db, strategy_id=strategy_id, actor=actor, hard=False
    )
    return {"ok": True}


@router.post(
    "/resolve-preview",
    response_model=LongTailCogsRateResolvePreviewResponse,
)
def resolve_preview(
    payload: LongTailCogsRateResolvePreviewRequest,
    db: Session = Depends(get_db_session),
):
    """Try-it: simulate which strategy would apply.

    Two modes (auto-selected by ``rate_type``):

    1. ``rate_type='cogs'`` (default) — long-tail behaviour. If
       ``sku_code`` is provided we look up the actual SkuMaster (so the
       user's ``metadata.long_tail_category`` is respected). Other fields,
       when provided, override the looked-up SkuMaster (handy for
       dry-running before the SKU exists).

    2. ``rate_type='overhead_rate'`` — Cost Rate Hub v1.3 4-layer chain.
       Uses ``model_id`` / ``category`` / ``cost_center_id`` to walk
       model > category > cost_center > global.
    """
    rate_type = (payload.rate_type or "cogs").strip()

    if rate_type == "overhead_rate":
        hit = long_tail_strategy_service.resolve_overhead_rate(
            db,
            model_id=payload.model_id,
            category=payload.category,
            cost_center_id=payload.cost_center_id,
        )
        return LongTailCogsRateResolvePreviewResponse(
            rate=float(hit.rate),
            source=hit.source or ("hard_fallback" if hit.hit_layer == "hard_fallback" else "overhead_rate_hub"),
            strategy_id=hit.strategy_id,
            category=payload.category,
            matched_keyword=None,
            hit_layer=hit.hit_layer,
            hit_scope_type=hit.scope_type,
            hit_scope_id=hit.scope_id,
            data_quality=hit.data_quality,
        )

    sku = None
    code = (payload.sku_code or "").strip()
    if code:
        sku = (
            db.query(models.SkuMaster)
            .filter(models.SkuMaster.erp_sku_barcode == code)
            .first()
        )
    if (
        payload.spec_text is not None
        or payload.product_name is not None
        or payload.long_tail_category is not None
    ):
        # Build a synthetic SkuMaster on the fly so we don't mutate the DB row.
        synthetic = models.SkuMaster(
            erp_sku_barcode=code or "__preview__",
            spec_text=payload.spec_text if payload.spec_text is not None else (sku.spec_text if sku else None),
            product_name=payload.product_name if payload.product_name is not None else (sku.product_name if sku else None),
            metadata_json=(
                {**(sku.metadata_json or {}), "long_tail_category": payload.long_tail_category}
                if payload.long_tail_category is not None
                else (sku.metadata_json if sku else {})
            ),
        )
        sku = synthetic

    resolved = long_tail_strategy_service.resolve_rate_for_sku(
        db, sku=sku, sku_code=code or None
    )
    return LongTailCogsRateResolvePreviewResponse(
        rate=resolved.rate,
        source=resolved.source,
        strategy_id=resolved.strategy_id,
        category=resolved.category,
        matched_keyword=resolved.matched_keyword,
    )


# ============================================================================
# v1.4 制造费按模型设置 — GET resolve + POST upsert 便捷封装
#
# 用户原话（2026-05-11）："制造费一定要指定模型，不能通用"。
# 这两个 endpoint 让 ProductModelEditorDrawer 的「计算汇总」能够：
#   1) 实时拿当前 model 的 hub 命中费率（取代写死的 0.30），不用走 POST + body
#   2) 一键写入/更新「scope=model + scope_id=<model_id>」那一行 overhead_rate
#      （内部自动处理「新建 vs 更新已存在 vs 复活 archived」三种情况）
# ============================================================================


@router.get(
    "/resolve/overhead",
    response_model=LongTailCogsRateResolvePreviewResponse,
)
def resolve_overhead_for_model(
    model_id: Optional[str] = Query(None, description="product_models.id；空则只走 category > global"),
    category: Optional[str] = Query(None, description="模型品类（model 层未命中后兜 category 层）"),
    cost_center_id: Optional[str] = Query(None, description="班组 ID（兜 cost_center 层）"),
    db: Session = Depends(get_db_session),
):
    """4 层 resolve 包装为 GET，方便 React useQuery 按 model_id 缓存。"""
    hit = long_tail_strategy_service.resolve_overhead_rate(
        db,
        model_id=model_id,
        category=category,
        cost_center_id=cost_center_id,
    )
    return LongTailCogsRateResolvePreviewResponse(
        rate=float(hit.rate),
        source=hit.source or ("hard_fallback" if hit.hit_layer == "hard_fallback" else "overhead_rate_hub"),
        strategy_id=hit.strategy_id,
        category=category,
        matched_keyword=None,
        hit_layer=hit.hit_layer,
        hit_scope_type=hit.scope_type,
        hit_scope_id=hit.scope_id,
        data_quality=hit.data_quality,
    )


class _UpsertModelOverheadRequest(BaseModel):
    """POST /upsert/model-overhead 的简化入参（不暴露 long_tail 全套字段）。"""

    model_id: str = Field(..., min_length=1, description="product_models.id")
    rate: float = Field(..., gt=0, lt=10, description="制造费率（0~10 之间，常见 0.20~0.40）")
    note: Optional[str] = Field(None, description="备注（写到 metadata.history）")
    actor: Optional[str] = Field(None, description="操作人（审计）")


@router.post(
    "/upsert/model-overhead",
    response_model=LongTailCogsRateStrategyRead,
)
def upsert_model_overhead(
    payload: _UpsertModelOverheadRequest,
    db: Session = Depends(get_db_session),
):
    """Upsert 一行 scope_type=model + scope_id=<model_id> 的 overhead_rate。

    内部自动处理 3 种情况：
      - 已有非 archived 行：PATCH（rate / note / source）
      - 已有 archived 行：复活（unarchive）+ 更新值
      - 不存在：新建

    category 由后端 `_synthesize_category_for_hub` 自动合成
    （`__overhead_rate__model__<model_id_lower>`），前端不需要感知。
    """
    rate_type = "overhead_rate"
    scope_type = "model"
    scope_id = payload.model_id.strip()
    if not scope_id:
        raise HTTPException(status_code=400, detail="model_id 必填")

    synthesized_category = long_tail_strategy_service._synthesize_category_for_hub(
        rate_type, scope_type, scope_id
    )
    existing = long_tail_strategy_service.get_by_category(
        db, category=synthesized_category
    )

    body = {
        "category": synthesized_category,
        "rate": payload.rate,
        "rate_type": rate_type,
        "scope_type": scope_type,
        "scope_id": scope_id,
        "source": "manual_model_override",
        "data_quality": "green",  # 用户手动设的算 green（明确意图）
        "enabled": True,
        "note": payload.note,
    }

    try:
        if existing is None or existing.is_archived:
            # 新建（或复活 archived）走 create_strategy 内部自动判断
            row = long_tail_strategy_service.create_strategy(
                db, payload=body, actor=payload.actor
            )
        else:
            # 已存在且 active：走 update_strategy（PATCH 语义）
            row = long_tail_strategy_service.update_strategy(
                db,
                strategy_id=existing.id,
                patch={
                    "rate": payload.rate,
                    "source": "manual_model_override",
                    "data_quality": "green",
                    "note": payload.note,
                },
                actor=payload.actor,
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return _to_read(row)
