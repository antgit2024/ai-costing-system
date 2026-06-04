"""Ops Assumption Scheme CRUD (复用 taxonomy 表, 不新建表).

简易日盈亏页面（/costing/insights/daily-pnl）顶部"运营参数方案"下拉源。
- 存储：`taxonomy_items` 表 + `domain='ops_assumption_scheme'`，每行 = 一个方案。
- metadata_json 存 6 个百分比 + description + is_default。
- `is_default=true` 在全表里有且仅有 1 个；POST/PUT 设置 true 时自动取消其他默认。
- DELETE 默认方案返回 400。

设计约束（brief §5 红线）：
- 不新建表（复用 taxonomy）
- 不动 `/costing/insights/{models,sales,shops,after-sales}` 任何一行代码
- 不改 `analytics_service.py` 任何函数
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import models, schemas
from ..dependencies import get_db_session, require_admin_key


router = APIRouter(prefix="/ops-assumption-schemes", tags=["OpsAssumptionScheme"])

DOMAIN = "ops_assumption_scheme"
DEFAULT_SCOPES = ["*"]


# Seed 4 个预置方案（首次部署运维调一次或前端首次进入页面自动调）
SEED_SCHEMES: List[Dict[str, Any]] = [
    {
        "name": "默认标准",
        "description": "运营当前算账口径（推广17 / 扣点6.1 / 税8 / 人工20 / 场地+快递10 / 兜底50）",
        "promotion_pct": 0.17,
        "platform_fee_pct": 0.061,
        "tax_pct": 0.08,
        "labor_pct": 0.20,
        "venue_logistics_pct": 0.10,
        "unmodeled_cost_pct": 0.50,
        "is_default": True,
        "sort_order": 10,
    },
    {
        "name": "大促降推广",
        "description": "大促前预演（推广降到12%）",
        "promotion_pct": 0.12,
        "platform_fee_pct": 0.061,
        "tax_pct": 0.08,
        "labor_pct": 0.20,
        "venue_logistics_pct": 0.10,
        "unmodeled_cost_pct": 0.50,
        "is_default": False,
        "sort_order": 20,
    },
    {
        "name": "试涨价",
        "description": "涨价 / 控人工（人工降到18%）",
        "promotion_pct": 0.17,
        "platform_fee_pct": 0.061,
        "tax_pct": 0.08,
        "labor_pct": 0.18,
        "venue_logistics_pct": 0.10,
        "unmodeled_cost_pct": 0.50,
        "is_default": False,
        "sort_order": 30,
    },
    {
        "name": "0 推广（最低边界）",
        "description": "看产品基本面（推广归零）",
        "promotion_pct": 0.0,
        "platform_fee_pct": 0.061,
        "tax_pct": 0.08,
        "labor_pct": 0.20,
        "venue_logistics_pct": 0.10,
        "unmodeled_cost_pct": 0.50,
        "is_default": False,
        "sort_order": 40,
    },
]


def _to_scheme(item: models.TaxonomyItem) -> schemas.OpsAssumptionScheme:
    """把 TaxonomyItem(domain='ops_assumption_scheme') 反序列化为 OpsAssumptionScheme。"""
    meta: Dict[str, Any] = item.metadata_json or {}
    return schemas.OpsAssumptionScheme(
        id=item.id,
        name=item.name,
        description=meta.get("description"),
        promotion_pct=float(meta.get("promotion_pct") or 0.0),
        platform_fee_pct=float(meta.get("platform_fee_pct") or 0.0),
        tax_pct=float(meta.get("tax_pct") or 0.0),
        labor_pct=float(meta.get("labor_pct") or 0.0),
        venue_logistics_pct=float(meta.get("venue_logistics_pct") or 0.0),
        unmodeled_cost_pct=float(meta.get("unmodeled_cost_pct") or 0.0),
        is_default=bool(meta.get("is_default") or False),
        sort_order=int(item.sort_order or 0),
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _build_metadata(
    *,
    description: Optional[str],
    promotion_pct: float,
    platform_fee_pct: float,
    tax_pct: float,
    labor_pct: float,
    venue_logistics_pct: float,
    unmodeled_cost_pct: float,
    is_default: bool,
) -> Dict[str, Any]:
    return {
        "description": description or "",
        "promotion_pct": float(promotion_pct),
        "platform_fee_pct": float(platform_fee_pct),
        "tax_pct": float(tax_pct),
        "labor_pct": float(labor_pct),
        "venue_logistics_pct": float(venue_logistics_pct),
        "unmodeled_cost_pct": float(unmodeled_cost_pct),
        "is_default": bool(is_default),
    }


def _list_all(db: Session) -> List[models.TaxonomyItem]:
    return (
        db.query(models.TaxonomyItem)
        .filter(
            models.TaxonomyItem.domain == DOMAIN,
            models.TaxonomyItem.is_archived.is_(False),
        )
        .order_by(models.TaxonomyItem.sort_order.asc(), models.TaxonomyItem.name.asc())
        .all()
    )


def _unset_other_defaults(db: Session, except_id: Optional[str] = None) -> None:
    """把除 except_id 外其他方案的 is_default 改为 false（保持全局只有 1 个默认）。"""
    rows = _list_all(db)
    for row in rows:
        if except_id and row.id == except_id:
            continue
        meta = dict(row.metadata_json or {})
        if meta.get("is_default"):
            meta["is_default"] = False
            row.metadata_json = meta


@router.get("", response_model=schemas.OpsAssumptionSchemeListResponse)
def list_ops_assumption_schemes(
    db: Session = Depends(get_db_session),
) -> schemas.OpsAssumptionSchemeListResponse:
    rows = _list_all(db)
    return schemas.OpsAssumptionSchemeListResponse(items=[_to_scheme(r) for r in rows])


@router.post(
    "",
    response_model=schemas.OpsAssumptionScheme,
    status_code=status.HTTP_201_CREATED,
)
def create_ops_assumption_scheme(
    payload: schemas.OpsAssumptionSchemeCreateRequest,
    db: Session = Depends(get_db_session),
    _: None = Depends(require_admin_key),
) -> schemas.OpsAssumptionScheme:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")

    # name 在 domain='ops_assumption_scheme' 内必须唯一（应用层校验，taxonomy 表模型无 DB 唯一约束）
    existing_same_name = (
        db.query(models.TaxonomyItem)
        .filter(
            models.TaxonomyItem.domain == DOMAIN,
            models.TaxonomyItem.is_archived.is_(False),
            models.TaxonomyItem.name == name,
        )
        .first()
    )
    if existing_same_name is not None:
        raise HTTPException(status_code=409, detail="scheme name already exists")

    if payload.is_default:
        _unset_other_defaults(db)

    metadata = _build_metadata(
        description=payload.description,
        promotion_pct=payload.promotion_pct,
        platform_fee_pct=payload.platform_fee_pct,
        tax_pct=payload.tax_pct,
        labor_pct=payload.labor_pct,
        venue_logistics_pct=payload.venue_logistics_pct,
        unmodeled_cost_pct=payload.unmodeled_cost_pct,
        is_default=bool(payload.is_default),
    )

    item = models.TaxonomyItem(
        domain=DOMAIN,
        name=name,
        scopes_json=list(DEFAULT_SCOPES),
        is_active=True,
        sort_order=int(payload.sort_order or 0),
        source="local",
        metadata_json=metadata,
        is_archived=False,
    )
    db.add(item)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="scheme name already exists")
    db.refresh(item)
    return _to_scheme(item)


@router.put("/{scheme_id}", response_model=schemas.OpsAssumptionScheme)
def update_ops_assumption_scheme(
    scheme_id: str,
    payload: schemas.OpsAssumptionSchemeUpdateRequest,
    db: Session = Depends(get_db_session),
    _: None = Depends(require_admin_key),
) -> schemas.OpsAssumptionScheme:
    item = db.get(models.TaxonomyItem, scheme_id)
    if not item or item.is_archived or item.domain != DOMAIN:
        raise HTTPException(status_code=404, detail="scheme not found")

    if payload.name is not None:
        item.name = payload.name.strip()

    if payload.sort_order is not None:
        item.sort_order = int(payload.sort_order)

    meta = dict(item.metadata_json or {})

    # 6 个百分比 + description
    for field in (
        "description",
        "promotion_pct",
        "platform_fee_pct",
        "tax_pct",
        "labor_pct",
        "venue_logistics_pct",
        "unmodeled_cost_pct",
    ):
        v = getattr(payload, field, None)
        if v is not None:
            meta[field] = v if field == "description" else float(v)

    # is_default 改 true 时需要把其他方案的 is_default 改回 false
    if payload.is_default is not None:
        if payload.is_default and not meta.get("is_default"):
            _unset_other_defaults(db, except_id=item.id)
        meta["is_default"] = bool(payload.is_default)

    item.metadata_json = meta

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="scheme name conflict")
    db.refresh(item)
    return _to_scheme(item)


@router.delete("/{scheme_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_ops_assumption_scheme(
    scheme_id: str,
    db: Session = Depends(get_db_session),
    _: None = Depends(require_admin_key),
):
    item = db.get(models.TaxonomyItem, scheme_id)
    if not item or item.is_archived or item.domain != DOMAIN:
        raise HTTPException(status_code=404, detail="scheme not found")

    meta = item.metadata_json or {}
    if meta.get("is_default"):
        raise HTTPException(
            status_code=400,
            detail="cannot delete the default scheme (is_default=true)",
        )

    item.is_archived = True
    db.commit()
    return None


@router.post("/seed", response_model=schemas.OpsAssumptionSchemeSeedResponse)
def seed_ops_assumption_schemes(
    db: Session = Depends(get_db_session),
    _: None = Depends(require_admin_key),
) -> schemas.OpsAssumptionSchemeSeedResponse:
    """幂等 seed 4 个预置方案。

    - 已存在的方案（按 name 匹配）不动；
    - 缺失的方案插入；
    - 最终保证：≥4 行（含原有）+ is_default=true 正好 1 个（如果原本没有任何 default，则把"默认标准"设为 default）。
    """
    existing_rows = _list_all(db)
    existing_by_name = {r.name: r for r in existing_rows}

    inserted = 0
    existed = 0
    for spec in SEED_SCHEMES:
        if spec["name"] in existing_by_name:
            existed += 1
            continue
        metadata = _build_metadata(
            description=spec["description"],
            promotion_pct=spec["promotion_pct"],
            platform_fee_pct=spec["platform_fee_pct"],
            tax_pct=spec["tax_pct"],
            labor_pct=spec["labor_pct"],
            venue_logistics_pct=spec["venue_logistics_pct"],
            unmodeled_cost_pct=spec["unmodeled_cost_pct"],
            is_default=bool(spec["is_default"]),
        )
        item = models.TaxonomyItem(
            domain=DOMAIN,
            name=spec["name"],
            scopes_json=list(DEFAULT_SCOPES),
            is_active=True,
            sort_order=int(spec.get("sort_order") or 0),
            source="seed",
            metadata_json=metadata,
            is_archived=False,
        )
        db.add(item)
        inserted += 1

    db.flush()

    # 校正 is_default：全表里有且仅有 1 个；如果当前 default 为 0 个，把"默认标准"设为默认。
    all_rows = _list_all(db)
    default_rows = [r for r in all_rows if (r.metadata_json or {}).get("is_default")]
    if len(default_rows) == 0:
        target = next((r for r in all_rows if r.name == "默认标准"), None)
        if target is None and all_rows:
            target = all_rows[0]
        if target is not None:
            meta = dict(target.metadata_json or {})
            meta["is_default"] = True
            target.metadata_json = meta
    elif len(default_rows) > 1:
        # 多于 1 个时保留第一个，其余取消。
        keep = default_rows[0]
        for r in default_rows[1:]:
            meta = dict(r.metadata_json or {})
            meta["is_default"] = False
            r.metadata_json = meta
        _ = keep  # explicit reference for readers

    db.commit()

    all_rows = _list_all(db)
    return schemas.OpsAssumptionSchemeSeedResponse(
        inserted=inserted,
        existed=existed,
        total=len(all_rows),
        items=[_to_scheme(r) for r in all_rows],
    )
