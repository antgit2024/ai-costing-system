from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy import asc
from sqlalchemy.orm import Session

from .. import models


def list_rules(db: Session, model_id: str) -> Sequence[models.ModelVariantRule]:
    return (
        db.query(models.ModelVariantRule)
        .filter(
            models.ModelVariantRule.model_id == model_id,
            models.ModelVariantRule.is_archived.is_(False),
        )
        .order_by(asc(models.ModelVariantRule.created_at))
        .all()
    )


def get_rule(db: Session, rule_id: str) -> Optional[models.ModelVariantRule]:
    return (
        db.query(models.ModelVariantRule)
        .filter(models.ModelVariantRule.id == rule_id, models.ModelVariantRule.is_archived.is_(False))
        .one_or_none()
    )


def create_rule(
    db: Session,
    *,
    model_id: str,
    rule_name: str,
    source_material_ref_id: str,
    trigger_type: str,
    trigger_operator: str = "equals",
    trigger_value: Optional[str],
    action_type: str,
    target_material_ref_id: Optional[str],
    quantity_delta: Optional[Decimal],
    status: str,
    metadata_json: Dict[str, Any],
) -> models.ModelVariantRule:
    rule = models.ModelVariantRule(
        model_id=model_id,
        rule_name=rule_name,
        source_material_ref_id=source_material_ref_id,
        trigger_type=trigger_type,
        trigger_operator=trigger_operator,
        trigger_value=trigger_value,
        action_type=action_type,
        target_material_ref_id=target_material_ref_id,
        quantity_delta=quantity_delta,
        status=status,
        metadata_json=metadata_json or {},
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


def update_rule(
    db: Session,
    rule: models.ModelVariantRule,
    *,
    rule_name: Optional[str] = None,
    trigger_type: Optional[str] = None,
    trigger_operator: Optional[str] = None,
    trigger_value: Optional[str] = None,
    action_type: Optional[str] = None,
    target_material_ref_id: Optional[str] = None,
    quantity_delta: Optional[Decimal] = None,
    status: Optional[str] = None,
    metadata_json: Optional[Dict[str, Any]] = None,
) -> models.ModelVariantRule:
    if rule_name is not None:
        rule.rule_name = rule_name
    if trigger_type is not None:
        rule.trigger_type = trigger_type
    if trigger_operator is not None:
        rule.trigger_operator = trigger_operator
    if trigger_value is not None:
        rule.trigger_value = trigger_value
    if action_type is not None:
        rule.action_type = action_type
    if target_material_ref_id is not None:
        rule.target_material_ref_id = target_material_ref_id
    if quantity_delta is not None:
        rule.quantity_delta = quantity_delta
    if status is not None:
        rule.status = status
    if metadata_json is not None:
        rule.metadata_json = metadata_json
    db.commit()
    db.refresh(rule)
    return rule


def delete_rule(db: Session, rule: models.ModelVariantRule) -> None:
    rule.is_archived = True
    db.commit()


def validate_rules_for_model_activation(
    db: Session,
    *,
    model: models.ProductModel,
    base_material_ids: List[str],
) -> List[str]:
    """
    Activation validation:
    - Each rule must have source material present in model base materials (fallback guarantee).
    - Target material must exist and be active for replace/add.
    """
    errors: List[str] = []
    rules = list_rules(db, model.id)
    active_rules = [r for r in rules if (r.status or "") == "active"]
    base_set = set(base_material_ids)

    for rule in active_rules:
        src = (rule.source_material_ref_id or "").strip()
        if not src:
            errors.append(f"变体规则缺少 source_material_ref_id：{rule.rule_name}")
            continue
        if src not in base_set:
            errors.append(
                f"变体规则 {rule.rule_name} 的源物料不在模型展开物料中（缺少兜底基础）"
            )
        action = (rule.action_type or "").strip()
        tgt = (rule.target_material_ref_id or "").strip()
        if action in ("replace_material", "add_material"):
            if not tgt:
                errors.append(f"变体规则 {rule.rule_name} 缺少目标物料")
                continue
            material = (
                db.query(models.Material)
                .filter(models.Material.id == tgt, models.Material.is_archived.is_(False))
                .one_or_none()
            )
            if not material or not material.is_active:
                errors.append(f"变体规则 {rule.rule_name} 的目标物料不存在或未启用")
    return errors



































