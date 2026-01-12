from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models


def _s(v: Any) -> str:
    return str(v or "").strip()


def _lower(v: Any) -> str:
    return _s(v).lower()


def _as_list(v: Any) -> list[str]:
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    s = str(v).strip()
    if not s:
        return []
    return [s]


def _num(v: Any) -> Optional[float]:
    if v in (None, ""):
        return None
    try:
        return float(v)
    except Exception:  # noqa: BLE001
        return None


def list_shipping_rules(
    db: Session,
    *,
    search: Optional[str],
    is_active: Optional[bool],
    page: int,
    page_size: int,
) -> Tuple[int, Sequence[models.ShippingRule]]:
    q = db.query(models.ShippingRule).filter(models.ShippingRule.is_archived.is_(False))
    if search:
        pattern = f"%{search.strip()}%"
        q = q.filter(models.ShippingRule.rule_name.ilike(pattern))
    if is_active is not None:
        q = q.filter(models.ShippingRule.is_active.is_(bool(is_active)))
    total = q.count()
    items = (
        q.order_by(models.ShippingRule.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return total, items


def create_shipping_rule(db: Session, *, payload: Dict[str, Any]) -> models.ShippingRule:
    rule = models.ShippingRule(
        rule_name=_s(payload.get("rule_name") or "未命名规则"),
        priority=int(payload.get("priority") or 100),
        is_active=bool(payload.get("is_active", True)),
        conditions_json=dict(payload.get("conditions") or {}),
        outputs_json=list(payload.get("outputs") or []),
        notes=_s(payload.get("notes")) or None,
        metadata_json=dict(payload.get("metadata") or {}),
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


def update_shipping_rule(db: Session, *, rule_id: str, patch: Dict[str, Any]) -> models.ShippingRule:
    rule = db.get(models.ShippingRule, rule_id)
    if not rule or rule.is_archived:
        raise ValueError("Shipping rule not found")
    if "rule_name" in patch and patch.get("rule_name") is not None:
        rule.rule_name = _s(patch.get("rule_name") or rule.rule_name)
    if "priority" in patch and patch.get("priority") is not None:
        rule.priority = int(patch.get("priority") or rule.priority)
    if "is_active" in patch and patch.get("is_active") is not None:
        rule.is_active = bool(patch.get("is_active"))
    if "conditions" in patch and patch.get("conditions") is not None:
        rule.conditions_json = dict(patch.get("conditions") or {})
    if "outputs" in patch and patch.get("outputs") is not None:
        rule.outputs_json = list(patch.get("outputs") or [])
    if "notes" in patch:
        rule.notes = _s(patch.get("notes")) or None
    if "metadata" in patch and patch.get("metadata") is not None:
        rule.metadata_json = dict(patch.get("metadata") or {})
    db.commit()
    db.refresh(rule)
    return rule


def archive_shipping_rule(db: Session, *, rule_id: str) -> None:
    rule = db.get(models.ShippingRule, rule_id)
    if not rule or rule.is_archived:
        return
    rule.is_archived = True
    db.commit()


@dataclass
class EvaluateContext:
    """
    MVP context for shipping rules evaluation.
    You can extend this without DB changes because rules store JSON.
    """

    shop_code: str = ""
    channel: str = ""
    shipping_method: str = ""
    is_merge: Optional[bool] = None
    province: str = ""
    city: str = ""
    weight_kg: Optional[float] = None
    volume_m3: Optional[float] = None
    package_count: Optional[int] = None
    tokens: list[str] = None  # type: ignore[assignment]


def _match_range(v: Optional[float], mn: Any, mx: Any) -> bool:
    if v is None:
        return True
    lo = _num(mn)
    hi = _num(mx)
    if lo is not None and v < lo:
        return False
    if hi is not None and v > hi:
        return False
    return True


def _match_tokens(ctx_tokens: list[str], cond: dict) -> bool:
    ts = [t for t in (ctx_tokens or []) if str(t).strip()]
    tset = {str(t).strip() for t in ts}
    all_need = _as_list(cond.get("has_tokens_all"))
    any_need = _as_list(cond.get("has_tokens_any"))
    if all_need and not all(str(x).strip() in tset for x in all_need):
        return False
    if any_need and not any(str(x).strip() in tset for x in any_need):
        return False
    return True


def evaluate_shipping_rules(
    db: Session,
    *,
    ctx: EvaluateContext,
    include_disabled_rules: bool = False,
) -> Dict[str, Any]:
    q = db.query(models.ShippingRule).filter(models.ShippingRule.is_archived.is_(False))
    if not include_disabled_rules:
        q = q.filter(models.ShippingRule.is_active.is_(True))
    rules = q.order_by(models.ShippingRule.priority.desc(), models.ShippingRule.created_at.asc()).all()

    matched_rules: list[dict] = []
    out_lines: list[dict] = []

    for r in rules:
        cond = dict(r.conditions_json or {})

        # Exact/IN matches (if condition absent => pass)
        shop_ok = True
        shops = _as_list(cond.get("shop_codes"))
        if shops:
            shop_ok = _s(ctx.shop_code) in {str(x).strip() for x in shops}

        ship_ok = True
        methods = _as_list(cond.get("shipping_methods"))
        if methods:
            ship_ok = _s(ctx.shipping_method) in {str(x).strip() for x in methods}

        merge_ok = True
        if cond.get("is_merge") in (True, False):
            if ctx.is_merge is None:
                merge_ok = False
            else:
                merge_ok = bool(ctx.is_merge) is bool(cond.get("is_merge"))

        region_ok = True
        provinces = _as_list(cond.get("province_in"))
        if provinces:
            region_ok = _s(ctx.province) in {str(x).strip() for x in provinces}

        if not (shop_ok and ship_ok and merge_ok and region_ok):
            continue

        if not _match_range(ctx.weight_kg, cond.get("min_weight_kg"), cond.get("max_weight_kg")):
            continue
        if not _match_range(ctx.volume_m3, cond.get("min_volume_m3"), cond.get("max_volume_m3")):
            continue
        if not _match_tokens(ctx.tokens or [], cond):
            continue

        matched_rules.append(
            {
                "rule_id": r.id,
                "rule_name": r.rule_name,
                "priority": r.priority,
            }
        )

        for item in (r.outputs_json or []):
            out_lines.append(dict(item or {}))

        # Optional stop_on_hit (default false)
        if bool(cond.get("stop_on_hit")):
            break

    # Expand/validate output materials (guardrail: only allow conditional materials)
    enriched: list[dict] = []
    warnings: list[str] = []
    if out_lines:
        mat_ids = list({str(x.get("material_id")) for x in out_lines if x.get("material_id")})
        mats = {}
        if mat_ids:
            ms = db.query(models.Material).filter(models.Material.id.in_(mat_ids)).all()
            mats = {m.id: m for m in ms}
        for line in out_lines:
            mid = str(line.get("material_id") or "").strip()
            qty = _num(line.get("quantity")) or 0.0
            multiplier = _s(line.get("multiplier") or "per_order") or "per_order"
            if not mid:
                continue
            m = mats.get(mid)
            if not m or m.is_archived:
                warnings.append(f"发货规则产出物料不存在或已归档：{mid}")
                continue
            usage = _lower((m.metadata_json or {}).get("usage_class"))
            if usage != "conditional":
                warnings.append(f"发货规则仅允许条件物料（usage_class=conditional）：{m.material_code}")
                continue
            mul = 1.0
            if multiplier == "per_package":
                mul = float(ctx.package_count or 1)
            enriched.append(
                {
                    "material_id": m.id,
                    "material_code": m.material_code,
                    "material_name": m.material_name,
                    "unit_of_measure": m.unit or m.purchase_unit,
                    "quantity": qty * mul,
                    "multiplier": multiplier,
                }
            )

    # Aggregate by material_code for readability
    agg: Dict[str, dict] = {}
    for x in enriched:
        key = _s(x.get("material_code")) or _s(x.get("material_id"))
        if not key:
            continue
        agg.setdefault(
            key,
            {
                "material_id": x.get("material_id"),
                "material_code": x.get("material_code"),
                "material_name": x.get("material_name"),
                "unit_of_measure": x.get("unit_of_measure"),
                "quantity": 0.0,
            },
        )
        agg[key]["quantity"] = float(agg[key]["quantity"]) + float(x.get("quantity") or 0)

    return {
        "matched_rules": matched_rules,
        "lines": list(agg.values()),
        "warnings": warnings[:50],
    }


