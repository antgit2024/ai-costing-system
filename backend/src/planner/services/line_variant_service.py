from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy import asc
from sqlalchemy.orm import Session

from .. import models

VALID_ACTIONS = {"replace_bundle", "replace_self", "remove_self", "add_siblings"}


def _to_decimal(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    if value in (None, ""):
        return default
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return default


def _json_safe(value: Any) -> Any:
    """
    Ensure JSON-serializable payloads for JSON columns (e.g. conditions_json/metadata_json).
    SQLAlchemy's default JSON serializer cannot handle Decimal/tuple.
    """
    if value is None:
        return None
    if isinstance(value, Decimal):
        # keep precision and avoid float rounding
        return str(value)
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    return value


def list_variants(
    db: Session,
    *,
    version_id: str,
    base_line_id: Optional[str] = None,
) -> Sequence[models.ProductModelLineVariant]:
    query = (
        db.query(models.ProductModelLineVariant)
        .filter(
            models.ProductModelLineVariant.version_id == version_id,
            models.ProductModelLineVariant.is_archived.is_(False),
        )
        .order_by(
            models.ProductModelLineVariant.priority.desc(),
            asc(models.ProductModelLineVariant.created_at),
        )
    )
    if base_line_id:
        query = query.filter(models.ProductModelLineVariant.base_line_id == base_line_id)
    return query.all()


def get_variant(db: Session, variant_id: str) -> Optional[models.ProductModelLineVariant]:
    return (
        db.query(models.ProductModelLineVariant)
        .filter(
            models.ProductModelLineVariant.id == variant_id,
            models.ProductModelLineVariant.is_archived.is_(False),
        )
        .one_or_none()
    )


def create_variant(
    db: Session,
    *,
    version_id: str,
    base_line_id: str,
    priority: int,
    enabled: bool,
    action: str,
    stop_on_hit: bool,
    notes: Optional[str],
    conditions: Dict[str, Any],
    metadata: Dict[str, Any],
    items: Optional[List[Dict[str, Any]]],
) -> models.ProductModelLineVariant:
    _ensure_version_and_line(db, version_id=version_id, base_line_id=base_line_id)
    _validate_action(action)

    variant = models.ProductModelLineVariant(
        version_id=version_id,
        base_line_id=base_line_id,
        priority=priority,
        enabled=enabled,
        action=action,
        stop_on_hit=stop_on_hit,
        notes=notes,
        conditions_json=_json_safe(conditions or {}),
        metadata_json=_json_safe(metadata or {}),
    )
    db.add(variant)
    db.flush()
    _replace_items(db, variant, items or [])
    db.commit()
    db.refresh(variant)
    return variant


def update_variant(
    db: Session,
    variant: models.ProductModelLineVariant,
    *,
    base_line_id: Optional[str],
    priority: Optional[int],
    enabled: Optional[bool],
    action: Optional[str],
    stop_on_hit: Optional[bool],
    notes: Optional[str],
    conditions: Optional[Dict[str, Any]],
    metadata: Optional[Dict[str, Any]],
) -> models.ProductModelLineVariant:
    if base_line_id is not None and base_line_id != variant.base_line_id:
        _ensure_version_and_line(db, version_id=variant.version_id, base_line_id=base_line_id)
        variant.base_line_id = base_line_id
    if priority is not None:
        variant.priority = priority
    if enabled is not None:
        variant.enabled = enabled
    if action is not None:
        _validate_action(action)
        variant.action = action
    if stop_on_hit is not None:
        variant.stop_on_hit = stop_on_hit
    if notes is not None:
        variant.notes = notes
    if conditions is not None:
        variant.conditions_json = _json_safe(conditions)
    if metadata is not None:
        variant.metadata_json = _json_safe(metadata)
    db.commit()
    db.refresh(variant)
    return variant


def delete_variant(db: Session, variant: models.ProductModelLineVariant) -> None:
    variant.is_archived = True
    db.commit()


def list_items(db: Session, variant_id: str) -> Sequence[models.ProductModelLineVariantItem]:
    return (
        db.query(models.ProductModelLineVariantItem)
        .filter(
            models.ProductModelLineVariantItem.variant_id == variant_id,
            models.ProductModelLineVariantItem.is_archived.is_(False),
        )
        .order_by(
            asc(models.ProductModelLineVariantItem.sequence_order),
            asc(models.ProductModelLineVariantItem.created_at),
        )
        .all()
    )


def replace_items(
    db: Session,
    variant: models.ProductModelLineVariant,
    *,
    items: List[Dict[str, Any]],
) -> models.ProductModelLineVariant:
    _replace_items(db, variant, items)
    db.commit()
    db.refresh(variant)
    return variant


def evaluate_conditions(
    variant: models.ProductModelLineVariant,
    *,
    tokens: List[str],
    metrics: Dict[str, Decimal | None],
) -> bool:
    cond = variant.conditions_json or {}
    lowered_tokens = [token.lower() for token in tokens]

    def _split_token_values(values: Any) -> List[str]:
        """
        Compatibility: historical data sometimes stores multiple tokens in one string,
        e.g. "雪尼尔，WB02339". We split by common delimiters.
        """
        out: List[str] = []
        raw_list = values if isinstance(values, list) else []
        for v in raw_list:
            s = str(v).strip()
            if not s:
                continue
            for part in s.replace("、", ",").replace("，", ",").split(","):
                p = part.strip()
                if p:
                    out.append(p.lower())
        return out

    if cond.get("spec_contains_any"):
        any_values = _split_token_values(cond.get("spec_contains_any") or [])
        if any_values and not any(value for value in any_values if value and value in lowered_tokens):
            return False

    if cond.get("spec_contains_all"):
        all_values = _split_token_values(cond.get("spec_contains_all") or [])
        if any(value and value not in lowered_tokens for value in all_values):
            return False

    checks = {
        "width_between": metrics.get("width_cm"),
        "height_between": metrics.get("height_cm"),
        "diameter_between": metrics.get("diameter_cm"),
        "area_between": metrics.get("area_m2"),
        "perimeter_between": metrics.get("perimeter_m"),
    }
    for key, metric_value in checks.items():
        if key not in cond:
            continue
        bounds = cond.get(key) or []
        if not _is_between(metric_value, bounds):
            return False

    return True


def _replace_items(
    db: Session,
    variant: models.ProductModelLineVariant,
    items: List[Dict[str, Any]],
) -> None:
    db.query(models.ProductModelLineVariantItem).filter(
        models.ProductModelLineVariantItem.variant_id == variant.id
    ).delete(synchronize_session=False)
    for idx, item in enumerate(items or [], 1):
        normalized = _normalize_item_payload(db, item)
        db.add(
            models.ProductModelLineVariantItem(
                variant_id=variant.id,
                sequence_order=normalized.get("sequence_order") or idx,
                material_kind=normalized.get("material_kind") or "real",
                material_ref_id=normalized.get("material_ref_id"),
                material_code=normalized.get("material_code"),
                material_name=normalized.get("material_name"),
                unit_of_measure=normalized.get("unit_of_measure"),
                calculation_method=normalized.get("calculation_method") or "count",
                base_quantity=_to_decimal(normalized.get("base_quantity")),
                fixed_quantity=_to_decimal(normalized.get("fixed_quantity")),
                coverage_ratio=_to_decimal(normalized.get("coverage_ratio"), Decimal("1")),
                loss_rate=_to_decimal(normalized.get("loss_rate")),
                metadata_json=normalized.get("metadata_json") or {},
            )
        )


def _ensure_version_and_line(db: Session, *, version_id: str, base_line_id: str) -> None:
    version = (
        db.query(models.ProductModelVersion)
        .filter(
            models.ProductModelVersion.id == version_id,
            models.ProductModelVersion.is_archived.is_(False),
        )
        .one_or_none()
    )
    if not version:
        raise ValueError("标准版本不存在或已归档")
    line = (
        db.query(models.ModelVersionMaterial)
        .filter(
            models.ModelVersionMaterial.id == base_line_id,
            models.ModelVersionMaterial.is_archived.is_(False),
        )
        .one_or_none()
    )
    if not line or line.version_id != version.id:
        raise ValueError("基准物料行不存在或不属于该版本")


def _validate_action(action: str) -> None:
    if action not in VALID_ACTIONS:
        raise ValueError("action 仅支持 replace_bundle/remove_self/add_siblings/replace_self")


def _is_between(value: Decimal | None, bounds: List[Any]) -> bool:
    if value is None:
        return False
    if not bounds:
        return True
    lower = _to_decimal(bounds[0], Decimal("-inf")) if len(bounds) >= 1 else Decimal("-inf")
    upper = _to_decimal(bounds[1], Decimal("inf")) if len(bounds) >= 2 else Decimal("inf")
    if lower != Decimal("-inf") and value < lower:
        return False
    if upper != Decimal("inf") and value > upper:
        return False
    return True


def _normalize_item_payload(db: Session, item: Dict[str, Any]) -> Dict[str, Any]:
    data = dict(item or {})
    material_kind = (data.get("material_kind") or "real").lower()
    data["material_kind"] = material_kind
    ref_id = data.get("material_ref_id")
    if ref_id:
        if material_kind == "real":
            material = db.get(models.Material, ref_id)
            if not material or material.is_archived:
                raise ValueError("material_ref_id 所指真实物料不存在或已归档")
            data.setdefault("material_code", material.material_code)
            data.setdefault("material_name", material.material_name)
            data.setdefault("unit_of_measure", material.unit)
            data.setdefault("calculation_method", material.calculation_method or "count")
        elif material_kind == "virtual":
            virtual = db.get(models.VirtualMaterial, ref_id)
            if not virtual or virtual.is_archived:
                raise ValueError("material_ref_id 所指虚拟物料不存在或已归档")
            data.setdefault("material_code", virtual.virtual_code)
            data.setdefault("material_name", virtual.name)
            data.setdefault("unit_of_measure", virtual.unit)
            data.setdefault("calculation_method", data.get("calculation_method") or "count")
        else:
            if material_kind not in {"bom"}:
                raise ValueError("material_kind 不受支持")
    return data

