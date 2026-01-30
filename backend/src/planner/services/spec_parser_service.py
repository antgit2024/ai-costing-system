from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Tuple


DIMENSION_PATTERN = re.compile(
    # Support both:
    # - "60*60cm"  (unit at tail)
    # - "60CM*60CM" (unit after each side; common in channel exports)
    r"(?P<prefix>约|大约|约等)?"
    r"(?P<width>\d{1,4}(?:\.\d+)?)\s*(?P<unit_w>cm|厘米|mm|毫米|m|米)?\s*"
    r"(?:[xX×\*＊]\s*(?P<height>\d{1,4}(?:\.\d+)?))\s*(?P<unit_h>cm|厘米|mm|毫米|m|米)?",
    re.IGNORECASE,
)

# Dimension with optional quantity, e.g.:
# - 45*45*1
# - 45×45×2
# - 45X45X3
# NOTE:
# - unit (cm/mm/m) applies to width/height only; qty is treated as a plain count.
DIMENSION_WITH_QTY_PATTERN = re.compile(
    r"(?P<prefix>约|大约|约等)?"
    r"(?P<width>\d{1,4}(?:\.\d+)?)\s*(?P<unit_w>cm|厘米|mm|毫米|m|米)?\s*"
    r"(?:[xX×\*＊]\s*(?P<height>\d{1,4}(?:\.\d+)?))\s*(?P<unit_h>cm|厘米|mm|毫米|m|米)?"
    r"(?:\s*[xX×\*＊]\s*(?P<qty>\d{1,4}))?",
    re.IGNORECASE,
)
DIAMETER_PATTERN = re.compile(
    # Accept:
    # - 直径50 / φ50 / Φ50 / D50
    # - 圆50 / 圆形50
    # - 圆(50) / 圆形（50）
    # NOTE: "圆形" must appear before "圆" to avoid partial match.
    r"(直径|φ|Φ|D|圆形|圆)\s*[（(]?\s*(?P<value>\d{1,4}(?:\.\d+)?)\s*(?P<unit>cm|厘米|mm|毫米|m|米)?\s*[）)]?",
    re.IGNORECASE,
)
TOKEN_SPLIT_PATTERN = re.compile(r"[;\n\r,，/\\\+|、]+")

# In “发货规格/交易规格” some channels prepend attribute names like:
# - 颜色分类:xxx;尺寸:xxx;组合形式:xxx
# These labels are not customer-facing tokens and should not affect parsing/matching.
# We ONLY strip labels that contain Chinese characters to avoid breaking internal tokens like "BUNDLE:DB9EAE".
ATTR_LABEL_PREFIX_PATTERN = re.compile(
    r"(^|[;\n\r,，/\\\+|、])\s*(?P<label>[^;\n\r,，/\\\+|、:：]{1,40}[\u4e00-\u9fff][^;\n\r,，/\\\+|、:：]{0,40})\s*[：:]\s*"
)

# Common, business-meaningful phrases that should be emitted as standalone tokens
# when present in the ERP “交易规格（spec_text）”. Keep this list conservative to
# avoid token explosion and accidental over-matching.
PHRASE_TOKEN_WHITELIST = [
    "背面纯色",
    # Pillow variants (运营口径：只要交易规格出现这些词才允许命中对应变体物料)
    "毛球",
    "雪尼尔",
]

# e.g. "竖120CM*横150CM" / "横150*竖120" / "宽120×高150"
LABELED_DIMENSION_PATTERN = re.compile(
    r"(?P<label1>竖|横|宽|高|长)\s*(?P<v1>\d{1,4}(?:\.\d+)?)\s*(?P<u1>cm|厘米|mm|毫米|m|米)?\s*"
    r"(?:[xX×\*＊]\s*(?P<label2>竖|横|宽|高|长)\s*(?P<v2>\d{1,4}(?:\.\d+)?)\s*(?P<u2>cm|厘米|mm|毫米|m|米)?)",
    re.IGNORECASE,
)

# Model code (3 chars) heuristic for fallback:
# - exactly 3 alphanumeric chars (A-Z/0-9)
# - must include at least one letter and one digit
# Examples: "PI5", "A1B"
MODEL_CODE_3_PATTERN = re.compile(r"\b(?=[A-Z0-9]{3}\b)(?=.*[A-Z])(?=.*\d)[A-Z0-9]{3}\b", re.IGNORECASE)
# Avoid \b for the ":" forms because ERP/spec_text often glues Chinese text with codes.
# Support multiple bundle token spellings:
# - legacy: "BUNDLE:CODE" / "BUNDLE:CODE:A"
# - v1:     "B:CODE" / "B:CODE:A"
# - v2:     "B-CODE-A"        (legacy dash form with separator)
# - v3:     "B-XXXXAA" / "B-XXXX" (new short form, CODE length fixed to 4; selector is 2 letters)
# - v4:     "Z:CODE:AA" / "Z-XXXXAA" (force-mode entry; operators should not need to provide extra trigger words)
#
# NOTE: The v3 form MUST appear before the generic dash form, otherwise "B-XXXXA" would be parsed as code="XXXXA"
# and selector missing.
BUNDLE_CODE_PATTERN = re.compile(
    r"(?:(?P<prefix>BUNDLE:|B:|Z:)(?P<code_colon>[A-Z0-9]{4,16})(?::(?P<sel_colon>[A-Z]{1,2}))?)"
    r"|(?:\b(?P<prefix_short>[BZ])-(?P<code_short>[A-Z0-9]{4})(?P<sel_short>[A-Z]{2})\b)"
    r"|(?:\b(?P<prefix_dash>[BZ])-(?P<code_dash>[A-Z0-9]{4,16})(?:-(?P<sel_dash>[A-Z]{1,2}))?\b)",
    re.IGNORECASE,
)


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


def normalize_tx_spec_text(spec_text: str) -> str:
    """
    Normalize transaction spec_text for parsing & hashing:
    - unify punctuation (fullwidth → ascii)
    - strip Chinese attribute label prefixes like "颜色分类:" / "尺寸:" / "组合形式:"
    - normalize delimiters to ';' and collapse whitespace
    """
    t = str(spec_text or "").strip()
    if not t:
        return ""
    t = t.replace("；", ";").replace("：", ":").replace("，", ",").replace("（", "(").replace("）", ")")
    # strip Chinese attribute labels, keep separators
    t = ATTR_LABEL_PREFIX_PATTERN.sub(r"\1", t)
    # normalize delimiters to ';' for stable hashing
    t = TOKEN_SPLIT_PATTERN.sub(";", t)
    t = re.sub(r";{2,}", ";", t)
    t = re.sub(r"\s+", " ", t).strip()
    # trim leading/trailing separators
    t = t.strip(" ;")
    return t


def parse_spec(spec_text: str) -> Dict[str, Any]:
    text = normalize_tx_spec_text(spec_text)
    tokens: List[str] = []
    explanations: List[Dict[str, str]] = []
    width_cm: Decimal | None = None
    height_cm: Decimal | None = None
    diameter_cm: Decimal | None = None
    dimension_qty: int | None = None
    extra_tokens: List[str] = []

    def _is_height_label(lbl: str) -> bool:
        return (lbl or "").strip() in ("竖", "高")

    def _is_width_label(lbl: str) -> bool:
        return (lbl or "").strip() in ("横", "宽", "长")

    labeled = LABELED_DIMENSION_PATTERN.search(text)
    if labeled:
        l1 = (labeled.group("label1") or "").strip()
        l2 = (labeled.group("label2") or "").strip()
        v1 = _to_decimal(labeled.group("v1"))
        v2 = _to_decimal(labeled.group("v2"))
        u1 = labeled.group("u1")
        u2 = labeled.group("u2")
        v1_cm = _normalize_to_cm(v1, u1) if v1 is not None else None
        v2_cm = _normalize_to_cm(v2, u2) if v2 is not None else None

        if v1_cm is not None and _is_height_label(l1):
            height_cm = v1_cm
        if v1_cm is not None and _is_width_label(l1):
            width_cm = v1_cm
        if v2_cm is not None and _is_height_label(l2):
            height_cm = v2_cm
        if v2_cm is not None and _is_width_label(l2):
            width_cm = v2_cm

        # Fallback if labels are ambiguous/missing mapping
        if width_cm is None and v1_cm is not None:
            width_cm = v1_cm
        if height_cm is None and v2_cm is not None:
            height_cm = v2_cm

        explanations.append({"token": f"{width_cm}", "source": labeled.group(0), "rule": "labeled_width_height"})
        explanations.append({"token": f"{height_cm}", "source": labeled.group(0), "rule": "labeled_width_height"})

    dim_match = DIMENSION_PATTERN.search(text)
    if dim_match:
        width_val = _to_decimal(dim_match.group("width"))
        height_val = _to_decimal(dim_match.group("height"))
        unit_w = dim_match.group("unit_w")
        unit_h = dim_match.group("unit_h")
        # Backward compat: if only one side has unit, apply it to both.
        unit_fallback = unit_h or unit_w
        if width_cm is None and width_val is not None:
            width_cm = _normalize_to_cm(width_val, unit_w or unit_fallback)
            explanations.append(
                {"token": f"{width_cm}", "source": dim_match.group(0), "rule": "width_height"}
            )
        if height_cm is None and height_val is not None:
            height_cm = _normalize_to_cm(height_val, unit_h or unit_fallback)
            explanations.append(
                {"token": f"{height_cm}", "source": dim_match.group(0), "rule": "width_height"}
            )

    # Optional quantity parsing:
    # - If spec uses the 3-part form (W*H*Q), take Q as the "dimension_qty"
    # - If spec has dimensions but no qty, default to 1
    dim_qty_match = DIMENSION_WITH_QTY_PATTERN.search(text)
    if dim_qty_match:
        try:
            raw = str(dim_qty_match.group("qty") or "").strip()
            if raw:
                q = int(raw)
                if q > 0:
                    dimension_qty = q
                    explanations.append({"token": str(q), "source": dim_qty_match.group(0), "rule": "dimension_qty"})
        except Exception:
            dimension_qty = None
    if dimension_qty is None and width_cm is not None and height_cm is not None:
        dimension_qty = 1

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

        # Extract stable “code tokens” from within a segment so rules can target them directly,
        # even when they are glued to other text (e.g. "Q25121102A黄金绒…" / "WB01176棉麻…").
        #
        # This is intentionally conservative: only extract high-signal identifiers.
        # - Material codes: WBxxxxx / VMxxxxx
        # - Style/color codes: Qxxxxxxxx + optional letters
        # - Barcodes: 12~14 digit sequences (common EAN/UPC variants used in ERP exports)
        for m in re.findall(r"(WB\d{5})", token, flags=re.IGNORECASE):
            extra_tokens.append(m.upper())
            explanations.append({"token": m.upper(), "source": token, "rule": "extract_material_code"})
        for m in re.findall(r"(VM\d{5})", token, flags=re.IGNORECASE):
            extra_tokens.append(m.upper())
            explanations.append({"token": m.upper(), "source": token, "rule": "extract_virtual_code"})
        for m in re.findall(r"(Q\d{6,}[A-Z]*)", token, flags=re.IGNORECASE):
            extra_tokens.append(m.upper())
            explanations.append({"token": m.upper(), "source": token, "rule": "extract_style_code"})
        for m in re.findall(r"(\d{12,14})", token):
            extra_tokens.append(m)
            explanations.append({"token": m, "source": token, "rule": "extract_barcode"})
        # Fallback: extract 3-char model codes when present (for binding/triage scenarios).
        # Output as a namespaced token to reduce collision with normal words.
        for m in MODEL_CODE_3_PATTERN.findall(token):
            code = m.upper()
            extra_tokens.append(f"MODEL:{code}")
            explanations.append({"token": f"MODEL:{code}", "source": token, "rule": "extract_model_code_3"})
            # Short alias for customer-facing spec token convention
            extra_tokens.append(f"M:{code}")
            explanations.append({"token": f"M:{code}", "source": token, "rule": "extract_model_code_3_alias"})

        # Extract bundle template codes so BOM can be generated without parsing sizes.
        # Emit canonical tokens for downstream logic.
        for m in BUNDLE_CODE_PATTERN.finditer(token):
            gd = m.groupdict() if m else {}
            code = (
                str(gd.get("code_colon") or "").strip().upper()
                or str(gd.get("code_short") or "").strip().upper()
                or str(gd.get("code_dash") or "").strip().upper()
            )
            selector = (
                str(gd.get("sel_colon") or "").strip().upper()
                or str(gd.get("sel_short") or "").strip().upper()
                or str(gd.get("sel_dash") or "").strip().upper()
            )
            prefix_raw = str(gd.get("prefix") or "").strip().upper() or None
            prefix_short = str(gd.get("prefix_short") or "").strip().upper() or None
            prefix_dash = str(gd.get("prefix_dash") or "").strip().upper() or None
            prefix_letter = "Z" if (prefix_raw == "Z:" or prefix_short == "Z" or prefix_dash == "Z") else "B"
            if not code:
                continue
            if prefix_letter == "Z":
                extra_tokens.append(f"Z:{code}")
                explanations.append({"token": f"Z:{code}", "source": token, "rule": "extract_bundle_code_z"})
                if selector:
                    extra_tokens.append(f"Z:{code}:{selector}")
                    explanations.append({"token": f"Z:{code}:{selector}", "source": token, "rule": "extract_bundle_selector_z"})
            else:
                extra_tokens.append(f"B:{code}")
                explanations.append({"token": f"B:{code}", "source": token, "rule": "extract_bundle_code"})
                extra_tokens.append(f"BUNDLE:{code}")
                explanations.append({"token": f"BUNDLE:{code}", "source": token, "rule": "extract_bundle_code_legacy"})
                if selector:
                    # Internal selector token is also 2-letter (AA/AB/...), keep legacy 1-letter if provided.
                    extra_tokens.append(f"B:{code}:{selector}")
                    explanations.append({"token": f"B:{code}:{selector}", "source": token, "rule": "extract_bundle_selector"})

        # Extract whitelist phrase tokens from within a segment
        for phrase in PHRASE_TOKEN_WHITELIST:
            if phrase and phrase in token:
                extra_tokens.append(phrase)
                explanations.append({"token": phrase, "source": token, "rule": "extract_phrase"})

    # De-duplicate but keep stable order (original segments first, then extracted codes).
    if extra_tokens:
        seen = set(t.lower() for t in tokens)
        for t in extra_tokens:
            k = t.lower()
            if k in seen:
                continue
            tokens.append(t)
            seen.add(k)

    area_m2, perimeter_m = _derive_area_perimeter(width_cm, height_cm, diameter_cm)
    return {
        "tokens": tokens,
        "width_cm": width_cm,
        "height_cm": height_cm,
        "diameter_cm": diameter_cm,
        "dimension_qty": dimension_qty,
        "area_m2": area_m2,
        "perimeter_m": perimeter_m,
        "explanations": explanations,
    }

