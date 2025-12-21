from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from .. import models
from . import line_variant_service, product_model_service, spec_parser_service


def generate_bom(
    db: Session,
    *,
    spec_text: str,
    model_version_id: Optional[str],
    sku_code: Optional[str],
    quantity: Optional[Decimal],
) -> Dict[str, Any]:
    version = _resolve_version(db, model_version_id=model_version_id, sku_code=sku_code)
    model = db.get(models.ProductModel, version.model_id)
    if not model or model.is_archived:
        raise ValueError("产品模型不存在或已归档")

    spec_result = spec_parser_service.parse_spec(spec_text or "")
    measurement = _build_measurement(version, spec_result, quantity)
    metrics = _build_metrics(spec_result, measurement)

    base_lines = product_model_service.list_version_material_lines(db, version.id)
    variants = line_variant_service.list_variants(db, version_id=version.id)
    variants_by_line: Dict[str, List[models.ProductModelLineVariant]] = {}
    for variant in variants:
        variants_by_line.setdefault(variant.base_line_id, []).append(variant)

    final_lines: List[Dict[str, Any]] = []
    trace_hits: List[Dict[str, Any]] = []
    line_counter = 0

    def _push(line: Dict[str, Any]) -> None:
        nonlocal line_counter
        line_counter += 1
        line["line_index"] = line_counter
        final_lines.append(line)

    for row in base_lines:
        variant_rules = variants_by_line.get(row.id, [])
        keep_base = True
        replacement_lines: List[Dict[str, Any]] = []
        additions: List[Dict[str, Any]] = []

        for variant in variant_rules:
            if not variant.enabled:
                trace_hits.append(
                    {
                        "variant_id": variant.id,
                        "base_line_id": row.id,
                        "action": variant.action,
                        "matched": False,
                        "reason": "disabled",
                    }
                )
                continue

            matched = line_variant_service.evaluate_conditions(
                variant,
                tokens=spec_result["tokens"],
                metrics=metrics,
            )
            trace_entry = {
                "variant_id": variant.id,
                "base_line_id": row.id,
                "action": variant.action,
                "matched": matched,
            }
            if matched:
                produced = [
                    _materialize_variant_item(
                        item,
                        measurement=measurement,
                        variant_id=variant.id,
                        base_line_id=row.id,
                    )
                    for item in variant.items or []
                ]
                trace_entry["produced_item_ids"] = [line["variant_item_id"] for line in produced]
                if variant.action in ("replace_bundle", "replace_self"):
                    keep_base = False
                    replacement_lines = produced
                    trace_entry["effect"] = f"replace_with_{len(produced)}"
                elif variant.action == "remove_self":
                    keep_base = False
                    replacement_lines = []
                    trace_entry["effect"] = "removed"
                elif variant.action == "add_siblings":
                    additions.extend(produced)
                    trace_entry["effect"] = f"added_{len(produced)}"
                trace_hits.append(trace_entry)
                if variant.stop_on_hit:
                    break
            else:
                trace_entry["effect"] = "skipped"
                trace_hits.append(trace_entry)

        if keep_base:
            _push(_materialize_base_line(row, measurement=measurement))
            for add_line in additions:
                _push(add_line)
        else:
            for repl_line in replacement_lines:
                _push(repl_line)
            for add_line in additions:
                _push(add_line)

    return {
        "final_material_lines": final_lines,
        "trace": {
            "model_id": model.id,
            "model_version_id": version.id,
            "sku_code": sku_code,
            "parsed": spec_result,
            "measurement_mm": measurement,
            "matched_variants": trace_hits,
        },
    }


def _resolve_version(
    db: Session,
    *,
    model_version_id: Optional[str],
    sku_code: Optional[str],
) -> models.ProductModelVersion:
    version: Optional[models.ProductModelVersion] = None
    if model_version_id:
        version = product_model_service.get_model_version(db, model_version_id)
    elif sku_code:
        mapping = (
            db.query(models.SkuModelVersionMapping)
            .filter(
                models.SkuModelVersionMapping.sku_code == sku_code,
                models.SkuModelVersionMapping.is_archived.is_(False),
            )
            .order_by(
                models.SkuModelVersionMapping.is_active.desc(),
                models.SkuModelVersionMapping.updated_at.desc(),
            )
            .first()
        )
        if mapping:
            version = product_model_service.get_model_version(db, mapping.model_version_id)
    if not version or version.is_archived:
        raise ValueError("未找到可用的标准版本（model_version_id 或 sku_code）")
    return version


def _build_measurement(
    version: models.ProductModelVersion,
    spec_result: Dict[str, Any],
    quantity: Optional[Decimal],
) -> Dict[str, Decimal]:
    version_meta = version.metadata_json or {}
    std_meta = version_meta.get("standard") if isinstance(version_meta.get("standard"), dict) else {}
    default_width_mm = _to_decimal(std_meta.get("width_mm"), Decimal("1000"))
    default_height_mm = _to_decimal(std_meta.get("height_mm"), Decimal("1000"))

    width_cm = spec_result.get("width_cm")
    height_cm = spec_result.get("height_cm")
    width_mm = _to_decimal(width_cm, default_width_mm / Decimal("10")) * Decimal("10") if width_cm is not None else default_width_mm
    height_mm = (
        _to_decimal(height_cm, default_height_mm / Decimal("10")) * Decimal("10") if height_cm is not None else default_height_mm
    )
    qty = _to_decimal(quantity, Decimal("1"))
    return {
        "width_mm": width_mm,
        "height_mm": height_mm,
        "quantity": qty,
    }


def _build_metrics(spec_result: Dict[str, Any], measurement: Dict[str, Decimal]) -> Dict[str, Decimal | None]:
    width_cm = spec_result.get("width_cm")
    height_cm = spec_result.get("height_cm")
    area_m2 = spec_result.get("area_m2")
    perimeter_m = spec_result.get("perimeter_m")
    if width_cm is None:
        width_cm = measurement["width_mm"] / Decimal("10")
    if height_cm is None:
        height_cm = measurement["height_mm"] / Decimal("10")
    if area_m2 is None:
        area_m2 = (measurement["width_mm"] * measurement["height_mm"]) / Decimal("1000000")
    if perimeter_m is None:
        perimeter_m = (
            Decimal("2") * (measurement["width_mm"] + measurement["height_mm"]) / Decimal("1000")
        )
    return {
        "width_cm": width_cm,
        "height_cm": height_cm,
        "area_m2": area_m2,
        "perimeter_m": perimeter_m,
    }


def _materialize_base_line(
    row: models.ModelVersionMaterial,
    *,
    measurement: Dict[str, Decimal],
) -> Dict[str, Any]:
    meta = row.metadata_json or {}
    fixed_quantity = _to_decimal(meta.get("fixed_quantity"))
    coverage_ratio = _to_decimal(meta.get("coverage_ratio"), Decimal("1"))
    return _build_line_payload(
        measurement=measurement,
        source_type="base_line",
        base_line_id=row.id,
        variant_id=None,
        variant_item_id=None,
        material_kind=row.material_type,
        material_ref_id=row.material_ref_id,
        material_code=row.material_code,
        material_name=row.material_name,
        unit_of_measure=row.unit_of_measure,
        calculation_method=row.calculation_method or "count",
        base_quantity=_to_decimal(row.base_quantity),
        fixed_quantity=fixed_quantity,
        coverage_ratio=coverage_ratio,
        loss_rate=_to_decimal(row.loss_rate),
        metadata=dict(meta),
    )


def _materialize_variant_item(
    item: models.ProductModelLineVariantItem,
    *,
    measurement: Dict[str, Decimal],
    variant_id: str,
    base_line_id: str,
) -> Dict[str, Any]:
    return _build_line_payload(
        measurement=measurement,
        source_type="variant_item",
        base_line_id=base_line_id,
        variant_id=variant_id,
        variant_item_id=item.id,
        material_kind=item.material_kind,
        material_ref_id=item.material_ref_id,
        material_code=item.material_code,
        material_name=item.material_name,
        unit_of_measure=item.unit_of_measure,
        calculation_method=item.calculation_method or "count",
        base_quantity=_to_decimal(item.base_quantity),
        fixed_quantity=_to_decimal(item.fixed_quantity),
        coverage_ratio=_to_decimal(item.coverage_ratio, Decimal("1")),
        loss_rate=_to_decimal(item.loss_rate),
        metadata=dict(item.metadata_json or {}),
    )


def _build_line_payload(
    *,
    measurement: Dict[str, Decimal],
    source_type: str,
    base_line_id: Optional[str],
    variant_id: Optional[str],
    variant_item_id: Optional[str],
    material_kind: str | None,
    material_ref_id: Optional[str],
    material_code: Optional[str],
    material_name: Optional[str],
    unit_of_measure: Optional[str],
    calculation_method: str,
    base_quantity: Decimal,
    fixed_quantity: Decimal,
    coverage_ratio: Decimal,
    loss_rate: Decimal,
    metadata: Dict[str, Any],
) -> Dict[str, Any]:
    method = calculation_method or "count"
    measure_qty = product_model_service._measure_qty(
        method,
        width_mm=measurement["width_mm"],
        height_mm=measurement["height_mm"],
        quantity=measurement["quantity"],
    )
    total = fixed_quantity + (base_quantity * coverage_ratio * measure_qty)
    return {
        "source_type": source_type,
        "base_line_id": base_line_id,
        "variant_id": variant_id,
        "variant_item_id": variant_item_id,
        "material_kind": material_kind or "real",
        "material_ref_id": material_ref_id,
        "material_code": material_code,
        "material_name": material_name,
        "unit_of_measure": unit_of_measure,
        "calculation_method": method,
        "base_quantity": base_quantity,
        "fixed_quantity": fixed_quantity,
        "coverage_ratio": coverage_ratio,
        "loss_rate": loss_rate,
        "computed_quantity": total,
        "metadata": metadata,
    }


def _to_decimal(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value in (None, ""):
        return default
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return default

