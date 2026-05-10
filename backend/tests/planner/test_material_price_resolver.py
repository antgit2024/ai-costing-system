"""Stage 2 物料取价器单元测试

覆盖 brief §4 完成标准 B1 / B5：
- 4 种取价场景（绿/黄/红 + 老数据兼容）
- 3 种含税还原口径（含税带税率 / 含税无税率走兜底 / 不含税）
- 数据质量分级 + warning 文案
- ``derive_bom_unit_price_exclusive`` 与老 ``_derive_bom_unit_price`` 数值一致性
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from src.planner import models
from src.planner.services.material_price_resolver import (
    DEFAULT_TAX_RATE_FALLBACK,
    derive_bom_unit_price_exclusive,
    price_source_label_cn,
    resolve_material_price,
)


def _make_material(db_session, **overrides) -> models.Material:
    base: dict = dict(
        material_code="MAT-RES-001",
        material_name="物料取价测试",
        material_type="raw",
        calculation_method="count",
        unit="米",
        purchase_unit="米",
        unit_price=Decimal("100"),
        conversion_purchase_to_bom=Decimal("1"),
        currency="CNY",
        is_active=True,
    )
    base.update(overrides)
    if base["material_code"] == "MAT-RES-001" and "material_code" not in overrides:
        suffix_idx = (
            db_session.query(models.Material).filter(models.Material.material_code.like("MAT-RES-%")).count()
        )
        base["material_code"] = f"MAT-RES-{suffix_idx + 1:03d}"
    m = models.Material(**base)
    db_session.add(m)
    db_session.commit()
    db_session.refresh(m)
    return m


# ---------------------------------------------------------------------------
# T1: 含税带税率 — green case（含税还原核心）
# ---------------------------------------------------------------------------


def test_resolve_inclusive_with_tax_rate_returns_exclusive(db_session) -> None:
    m = _make_material(
        db_session,
        unit_price=Decimal("113"),
        tax_included_flag=True,
        tax_rate=Decimal("0.13"),
        price_source="contract",
        effective_from=date(2026, 1, 1),
    )

    q = resolve_material_price(m, as_of_date=date(2026, 5, 10))

    assert q.price_inclusive == Decimal("113")
    assert q.price_exclusive == Decimal("100")
    assert q.bom_unit_price_exclusive == Decimal("100")
    assert q.tax_rate == Decimal("0.13")
    assert q.tax_included_flag is True
    assert q.data_quality == "green"
    assert q.price_source == "contract"
    assert q.warnings == []


# ---------------------------------------------------------------------------
# T2: 含税但 tax_rate NULL — yellow + 13% 兜底
# ---------------------------------------------------------------------------


def test_resolve_inclusive_without_tax_rate_falls_back_to_default(db_session) -> None:
    m = _make_material(
        db_session,
        unit_price=Decimal("113"),
        tax_included_flag=True,
        tax_rate=None,
        price_source="contract",
        effective_from=date(2026, 1, 1),
    )

    q = resolve_material_price(m, as_of_date=date(2026, 5, 10))

    assert q.tax_rate == DEFAULT_TAX_RATE_FALLBACK
    assert q.price_inclusive == Decimal("113")
    expected_exclusive = Decimal("113") / (Decimal("1") + DEFAULT_TAX_RATE_FALLBACK)
    assert q.price_exclusive == expected_exclusive
    assert q.data_quality == "yellow"
    assert any("默认" in w and "兜底" in w for w in q.warnings)


# ---------------------------------------------------------------------------
# T3: 不含税 — price_exclusive == unit_price
# ---------------------------------------------------------------------------


def test_resolve_exclusive_unit_price_no_tax_round_trip(db_session) -> None:
    m = _make_material(
        db_session,
        unit_price=Decimal("100"),
        tax_included_flag=False,
        tax_rate=Decimal("0.13"),
        price_source="invoice",
        effective_from=date(2026, 1, 1),
    )

    q = resolve_material_price(m, as_of_date=date(2026, 5, 10))

    assert q.price_exclusive == Decimal("100")
    assert q.price_inclusive == Decimal("113")
    assert q.tax_rate == Decimal("0.13")
    assert q.tax_included_flag is False
    assert q.data_quality == "green"


# ---------------------------------------------------------------------------
# T4: 老数据 effective_from = NULL → yellow + 不报错（向后兼容硬约束）
# ---------------------------------------------------------------------------


def test_resolve_legacy_data_without_effective_from_yields_yellow(db_session) -> None:
    m = _make_material(
        db_session,
        unit_price=Decimal("50"),
        tax_included_flag=False,
        tax_rate=None,
        price_source=None,
        effective_from=None,
        effective_to=None,
    )

    q = resolve_material_price(m, as_of_date=date(2026, 5, 10))

    assert q.price_exclusive == Decimal("50")
    assert q.bom_unit_price_exclusive == Decimal("50")
    assert q.data_quality == "yellow"
    assert any("effective_from 缺失" in w for w in q.warnings)
    assert any("price_source 缺失" in w for w in q.warnings)


# ---------------------------------------------------------------------------
# T5: 生效期不匹配 → yellow + warning（不抛错，给兜底）
# ---------------------------------------------------------------------------


def test_resolve_as_of_date_outside_effective_period_warns(db_session) -> None:
    m = _make_material(
        db_session,
        unit_price=Decimal("100"),
        tax_included_flag=False,
        price_source="contract",
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 3, 31),
    )

    q = resolve_material_price(m, as_of_date=date(2026, 5, 10))

    assert q.data_quality == "yellow"
    assert q.price_exclusive == Decimal("100")
    assert any("不在生效期" in w for w in q.warnings)


# ---------------------------------------------------------------------------
# T6: unit_price=0 / None → red, price_exclusive=None（不允许 0 价 silently）
# ---------------------------------------------------------------------------


def test_resolve_missing_unit_price_yields_red(db_session) -> None:
    m = _make_material(
        db_session,
        unit_price=Decimal("0"),
        tax_included_flag=False,
    )

    q = resolve_material_price(m, as_of_date=date(2026, 5, 10))

    assert q.data_quality == "red"
    assert q.price_exclusive is None
    assert q.bom_unit_price_exclusive is None
    assert any("unit_price" in w for w in q.warnings)


# ---------------------------------------------------------------------------
# T7: BOM 单位换算 — bom_unit_price_exclusive 体现 conversion
# ---------------------------------------------------------------------------


def test_resolve_bom_unit_price_applies_conversion(db_session) -> None:
    m = _make_material(
        db_session,
        unit_price=Decimal("113"),
        tax_included_flag=True,
        tax_rate=Decimal("0.13"),
        price_source="contract",
        effective_from=date(2026, 1, 1),
        unit="米",
        purchase_unit="卷",
        conversion_purchase_to_bom=Decimal("10"),
    )

    q = resolve_material_price(m, as_of_date=date(2026, 5, 10))

    assert q.price_exclusive == Decimal("100")
    assert q.bom_unit_price_exclusive == Decimal("10")
    assert q.data_quality == "green"


# ---------------------------------------------------------------------------
# T8: derive_bom_unit_price_exclusive — 老 ``_derive_bom_unit_price`` 兼容入口
# ---------------------------------------------------------------------------


def test_derive_bom_unit_price_exclusive_compat_signature(db_session) -> None:
    m = _make_material(
        db_session,
        unit_price=Decimal("113"),
        tax_included_flag=True,
        tax_rate=Decimal("0.13"),
        price_source="contract",
        effective_from=date(2026, 1, 1),
        unit="米",
        purchase_unit="米",
        conversion_purchase_to_bom=Decimal("1"),
    )
    legacy = _make_material(
        db_session,
        unit_price=Decimal("100"),
        tax_included_flag=False,
        tax_rate=None,
        effective_from=None,
        unit="个",
        purchase_unit="个",
        conversion_purchase_to_bom=Decimal("1"),
    )

    p1 = derive_bom_unit_price_exclusive(m, as_of_date=date(2026, 5, 10))
    p2 = derive_bom_unit_price_exclusive(legacy, as_of_date=date(2026, 5, 10))

    assert p1 == Decimal("100")
    assert p2 == Decimal("100")


# ---------------------------------------------------------------------------
# T9: 价格来源中文化（前端 tooltip 用）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "code,expected",
    [
        ("contract", "合同"),
        ("invoice", "发票"),
        ("purchase_order", "采购单"),
        ("manual", "手填"),
        ("estimate", "估算"),
        (None, "未填"),
        ("", "未填"),
        ("unknown_xx", "unknown_xx"),
    ],
)
def test_price_source_label_cn(code, expected) -> None:
    assert price_source_label_cn(code) == expected


# ---------------------------------------------------------------------------
# T10: to_jsonable() 给 cost_breakdown 用（JSON 友好 + 含警告 / quality）
# ---------------------------------------------------------------------------


def test_quote_to_jsonable_serializes_for_cost_breakdown(db_session) -> None:
    m = _make_material(
        db_session,
        unit_price=Decimal("113"),
        tax_included_flag=True,
        tax_rate=Decimal("0.13"),
        price_source="contract",
        effective_from=date(2026, 1, 1),
    )

    q = resolve_material_price(m, as_of_date=date(2026, 5, 10))
    body = q.to_jsonable()

    assert body["price_inclusive"] == 113.0
    assert body["price_exclusive"] == 100.0
    assert body["tax_rate"] == 0.13
    assert body["tax_included_flag"] is True
    assert body["price_source"] == "contract"
    assert body["effective_from"] == "2026-01-01"
    assert body["effective_to"] is None
    assert body["_data_quality"] == "green"
    assert body["_warnings"] == []
