"""Guardrails for the strict shop_spec_code → model_code extractor.

These tests pin down the **anti-misbinding** behavior added when 吉客云
historical tradeGoodsno values turned out to be 12-digit platform IDs
that would otherwise be incorrectly matched by the loose
``_extract_model_code_hint`` (which takes leading 3 digits from any
token).
"""
from src.planner.services.sku_master_service import (
    _extract_model_code_from_shop_spec,
    _extract_model_code_hint,
)


def test_strict_extractor_accepts_3char_alnum_models():
    assert _extract_model_code_from_shop_spec("KB8") == "KB8"
    assert _extract_model_code_from_shop_spec("ozu") == "OZU"
    assert _extract_model_code_from_shop_spec("A1B") == "A1B"


def test_strict_extractor_accepts_structured_variants():
    assert _extract_model_code_from_shop_spec("KB8-001") == "KB8"
    assert _extract_model_code_from_shop_spec("OZU-MG") == "OZU"
    assert _extract_model_code_from_shop_spec("KB8-001-TMALL") == "KB8"


def test_strict_extractor_rejects_pure_digit_platform_ids():
    """Critical: 24442 historical jackyun tradeGoodsno values are pure
    digits like '986153092837'. Loose extractor would return '986'.
    """
    assert _extract_model_code_hint("986153092837") == "986"  # loose: leaks!
    assert _extract_model_code_from_shop_spec("986153092837") is None  # strict: blocks


def test_strict_extractor_rejects_3digit_only():
    """Even '024' alone is rejected by strict path — could collide with
    platform IDs 024xxxxxxx. Operators must use 'KB8'-style codes."""
    assert _extract_model_code_from_shop_spec("024") is None
    assert _extract_model_code_from_shop_spec("999") is None


def test_strict_extractor_rejects_non_dash_suffix():
    """'F26040205' / 'Q26010601C丝圈地垫' / 'Q25090802' shouldn't auto-bind."""
    assert _extract_model_code_from_shop_spec("F26040205") is None
    assert _extract_model_code_from_shop_spec("Q26010601C") is None
    assert _extract_model_code_from_shop_spec("Q25090802") is None
    assert _extract_model_code_from_shop_spec("Q25102204DDXNEF001X-4060") is None


def test_strict_extractor_keeps_pm_legacy_format():
    assert _extract_model_code_from_shop_spec("PM001") == "PM001"
    assert _extract_model_code_from_shop_spec("PM_OLD-A") == "PM_OLD-A"


def test_strict_extractor_handles_blank_input():
    assert _extract_model_code_from_shop_spec(None) is None
    assert _extract_model_code_from_shop_spec("") is None
    assert _extract_model_code_from_shop_spec("   ") is None
