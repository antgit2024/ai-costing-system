from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Tuple


DIMENSION_PATTERN = re.compile(
    r"(?P<prefix>约|大约|约等)?(?P<width>\d{1,4}(?:\.\d+)?)\s*"
    r"(?:[xX×\*＊]\s*(?P<height>\d{1,4}(?:\.\d+)?))"
    r"\s*(?P<unit>cm|厘米|mm|毫米|m|米)?",
    re.IGNORECASE,
)
DIAMETER_PATTERN = re.compile(
    r"(直径|φ|Φ|D)\s*(?P<value>\d{1,4}(?:\.\d+)?)\s*(?P<unit>cm|厘米|mm|毫米|m|米)?",
    re.IGNORECASE,
)
TOKEN_SPLIT_PATTERN = re.compile(r"[;\n\r,，/\\\+|、]+")


def _to_decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _normalize_to_cm(value: Decimal, unit: str | None) -> Decimal:
    unit_norm = (unit or "cm").strip().lower()
    if unit_norm in ("mm", "毫米"):
        return value / Decimal("10")
    if unit_norm in ("m", "米"):
        return value * Decimal("100")
    return value


def _derive_area_perimeter(
    width_cm: Decimal | None,
    height_cm: Decimal | None,
    diameter_cm: Decimal | None,
) -> Tuple[Decimal | None, Decimal | None]:
    pi = Decimal("3.141592653589793")
    if width_cm is not None and height_cm is not None:
        area = (width_cm * height_cm) / Decimal("10000")
        perimeter = Decimal("2") * (width_cm + height_cm) / Decimal("100")
        return area, perimeter
    if diameter_cm is not None:
        radius_m = (diameter_cm / Decimal("100")) / Decimal("2")
        area = pi * (radius_m**2)
        perimeter = Decimal("2") * pi * radius_m
        return area, perimeter
    return None, None


def parse_spec(spec_text: str) -> Dict[str, Any]:
    text = (spec_text or "").strip()
    tokens: List[str] = []
    explanations: List[Dict[str, str]] = []
    width_cm: Decimal | None = None
    height_cm: Decimal | None = None
    diameter_cm: Decimal | None = None

    dim_match = DIMENSION_PATTERN.search(text)
    if dim_match:
        width_val = _to_decimal(dim_match.group("width"))
        height_val = _to_decimal(dim_match.group("height"))
        unit = dim_match.group("unit")
        if width_val is not None:
            width_cm = _normalize_to_cm(width_val, unit)
            explanations.append(
                {"token": f"{width_cm}", "source": dim_match.group(0), "rule": "width_height"}
            )
        if height_val is not None:
            height_cm = _normalize_to_cm(height_val, unit)
            explanations.append(
                {"token": f"{height_cm}", "source": dim_match.group(0), "rule": "width_height"}
            )

    dia_match = DIAMETER_PATTERN.search(text)
    if dia_match:
        dia_val = _to_decimal(dia_match.group("value"))
        if dia_val is not None:
            diameter_cm = _normalize_to_cm(dia_val, dia_match.group("unit"))
            explanations.append(
                {"token": f"{diameter_cm}", "source": dia_match.group(0), "rule": "diameter"}
            )
            if width_cm is None and height_cm is None:
                width_cm = diameter_cm
                height_cm = diameter_cm

    for segment in TOKEN_SPLIT_PATTERN.split(text):
        token = segment.strip()
        if not token:
            continue
        tokens.append(token)
        explanations.append({"token": token, "source": token, "rule": "segment"})

    area_m2, perimeter_m = _derive_area_perimeter(width_cm, height_cm, diameter_cm)
    return {
        "tokens": tokens,
        "width_cm": width_cm,
        "height_cm": height_cm,
        "diameter_cm": diameter_cm,
        "area_m2": area_m2,
        "perimeter_m": perimeter_m,
        "explanations": explanations,
    }

