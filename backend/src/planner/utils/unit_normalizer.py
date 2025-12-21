from __future__ import annotations


def normalize_unit(value: str | None) -> str:
    """
    Canonical unit mapping for the whole costing system.

    Canonical values (display + storage):
    - 平米
    - 米
    - 个
    - 套

    Accepts common synonyms and returns canonical; unknown units are returned as-is.
    """
    u = (value or "").strip()
    if not u:
        return ""
    u = u.replace(" ", "")

    # Area
    if u in ("㎡", "m2", "M2", "m²", "M²", "米2", "米²", "平方", "平方米", "平米"):
        return "平米"

    # Length
    if u in ("m", "M", "米"):
        return "米"

    # Count
    if u in ("个", "pcs", "PCS", "piece", "Piece"):
        return "个"

    # Set
    if u in ("套", "set", "SET"):
        return "套"

    return u



















