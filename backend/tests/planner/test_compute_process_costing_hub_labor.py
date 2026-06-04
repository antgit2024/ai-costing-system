"""TDABC v1 G — A2 接通：_compute_process_costing reads cost_rate_master.labor_per_minute.

Covers the new Hub-first labor rate resolution layered on top of the existing
metadata.rate_per_minute fallback, validating:

1. Hub hit on cost_center layer → uses Hub price, rate_source=hub_cost_center.
2. Hub miss because process.cost_center_id is NULL → falls back to metadata.rate_per_minute.
3. Hub miss because cost_rate_master has no row for this scope → falls back to metadata.
4. Hub row exists but rate is 0 → defensive fallback to metadata (we never want a 0 labor cost).
5. piece-type costing parity: Hub labor_per_piece hit overrides metadata.piece_rate.
6. Hub model layer beats cost_center layer (priority chain) — model-level override wins.

These tests pin the contract that "no Hub data → 100% behaviour-equivalent to pre-G".
"""

from __future__ import annotations

from decimal import Decimal
from typing import Tuple

import pytest

from src.planner import models
from src.planner.services import (
    bom_generation_service,
    long_tail_strategy_service as ltss,
)


# ---------------------------------------------------------------------------
# Fixture helpers — minimal model/version/process scaffolding for G tests.
# ---------------------------------------------------------------------------


def _seed_cost_center(db_session, code: str, name: str) -> models.CostCenter:
    cc = models.CostCenter(
        code=code,
        name=name,
        type="production",
        is_active=True,
    )
    db_session.add(cc)
    db_session.flush()
    return cc


def _seed_process(
    db_session,
    *,
    code: str,
    name: str = "印刷工序",
    cost_center_id: str | None = None,
) -> models.Process:
    proc = models.Process(
        process_code=code,
        process_name=name,
        team_name="生产",
        charging_mode="count",
        status="active",
        is_active=True,
        cost_center_id=cost_center_id,
        metadata_json={},
    )
    db_session.add(proc)
    db_session.flush()
    return proc


def _seed_model_version(
    db_session,
    *,
    model_code: str = "KB8-test",
    category: str = "布艺",
) -> Tuple[models.ProductModel, models.ProductModelVersion]:
    model = models.ProductModel(
        model_code=f"{model_code}-{id(db_session)}",
        model_name=f"{model_code} fixture",
        category=category,
        calc_mode="ratio",
    )
    db_session.add(model)
    db_session.flush()
    version = models.ProductModelVersion(
        model_id=model.id,
        version_kind="standard",
        version_status="published",
    )
    db_session.add(version)
    db_session.flush()
    return model, version


def _seed_version_process_line(
    db_session,
    *,
    version_id: str,
    process_id: str,
    cost_type: str = "time",
    base_minutes: float = 0,
    unit_minutes: float = 0,
    rate_per_minute: float | None = None,
    piece_rate: float | None = None,
    pricing_method: str = "count",
) -> models.ModelVersionProcess:
    meta = {
        "pricing_method": pricing_method,
        "cost_type": cost_type,
        "base_minutes": base_minutes,
        "unit_minutes": unit_minutes,
    }
    if rate_per_minute is not None:
        meta["rate_per_minute"] = rate_per_minute
    if piece_rate is not None:
        meta["piece_rate"] = piece_rate
    row = models.ModelVersionProcess(
        version_id=version_id,
        process_id=process_id,
        sequence_order=1,
        notes=None,
        metadata_json=meta,
    )
    db_session.add(row)
    db_session.flush()
    return row


# ---------------------------------------------------------------------------
# 1) Hub hit on cost_center layer overrides metadata
# ---------------------------------------------------------------------------


def test_hub_cost_center_overrides_metadata_rate(db_session):
    """When cost_rate_master has labor_per_minute scope=cost_center for the
    process's cost_center_id, that rate wins over metadata.rate_per_minute."""
    cc = _seed_cost_center(db_session, "CC_PRINT_TEST", "Test 印刷")
    proc = _seed_process(db_session, code="P_PRINT_TEST", cost_center_id=cc.id)
    model, version = _seed_model_version(db_session)
    line = _seed_version_process_line(
        db_session,
        version_id=version.id,
        process_id=proc.id,
        cost_type="time",
        base_minutes=0,
        unit_minutes=5,  # 5 minutes per unit
        rate_per_minute=0.50,  # legacy metadata snapshot says ¥0.50/min
    )

    # Seed Hub row at cost_center layer with ¥0.85/min — the "real" finance rate.
    ltss.create_strategy(
        db_session,
        payload={
            "rate_type": "labor_per_minute",
            "scope_type": "cost_center",
            "scope_id": cc.id,
            "rate": 0.85,
            "rate_basis": "per_minute",
            "source": "auto_aggregated_from_finance",
            "data_quality": "green",
        },
    )

    total, costing = bom_generation_service._compute_process_costing(
        db_session,
        process_lines=[line],
        width_mm=Decimal("100"),
        height_mm=Decimal("100"),
        quantity=Decimal("1"),
        model=model,
    )

    # 5 min × ¥0.85/min = ¥4.25
    assert total == Decimal("5") * Decimal("0.85")
    assert len(costing["process_lines"]) == 1
    pl = costing["process_lines"][0]
    assert pl["rate_source"] == "hub_cost_center"
    assert pl["rate_hit_layer"] == "cost_center"
    assert pl["cost_center_id"] == cc.id
    assert pl["rate_per_minute"] == Decimal("0.85")
    # legacy snapshot preserved for audit trail
    assert pl["rate_per_minute_legacy"] == Decimal("0.50")


# ---------------------------------------------------------------------------
# 2) Hub miss because process has no cost_center_id → metadata fallback
# ---------------------------------------------------------------------------


def test_hub_miss_when_process_has_no_cost_center(db_session):
    """Legacy processes (cost_center_id IS NULL) must fall back unchanged."""
    proc = _seed_process(db_session, code="P_LEGACY", cost_center_id=None)
    model, version = _seed_model_version(db_session)
    line = _seed_version_process_line(
        db_session,
        version_id=version.id,
        process_id=proc.id,
        cost_type="time",
        unit_minutes=3,
        rate_per_minute=0.40,
    )

    # No Hub row seeded.
    total, costing = bom_generation_service._compute_process_costing(
        db_session,
        process_lines=[line],
        width_mm=Decimal("100"),
        height_mm=Decimal("100"),
        quantity=Decimal("1"),
        model=model,
    )

    # 3 × ¥0.40 = ¥1.20  (legacy metadata)
    assert total == Decimal("3") * Decimal("0.40")
    pl = costing["process_lines"][0]
    assert pl["rate_source"] == "metadata"
    assert pl["rate_hit_layer"] is None
    assert pl["cost_center_id"] is None
    assert pl["rate_per_minute"] == Decimal("0.40")
    assert pl["rate_per_minute_legacy"] == Decimal("0.40")


# ---------------------------------------------------------------------------
# 3) Hub miss because no cost_rate_master row for this scope
# ---------------------------------------------------------------------------


def test_hub_miss_when_no_strategy_row(db_session):
    """Process has cost_center_id, but cost_rate_master has no labor row → fallback."""
    cc = _seed_cost_center(db_session, "CC_DECOR_TEST", "Test 包边")
    proc = _seed_process(db_session, code="P_DECOR_TEST", cost_center_id=cc.id)
    model, version = _seed_model_version(db_session)
    line = _seed_version_process_line(
        db_session,
        version_id=version.id,
        process_id=proc.id,
        cost_type="time",
        unit_minutes=2,
        rate_per_minute=0.30,
    )
    # NOTE: NO Hub row seeded — only a different cost_center has Hub data.
    other_cc = _seed_cost_center(db_session, "CC_OTHER_TEST", "Test 其他")
    ltss.create_strategy(
        db_session,
        payload={
            "rate_type": "labor_per_minute",
            "scope_type": "cost_center",
            "scope_id": other_cc.id,
            "rate": 0.99,
            "rate_basis": "per_minute",
        },
    )

    total, costing = bom_generation_service._compute_process_costing(
        db_session,
        process_lines=[line],
        width_mm=Decimal("100"),
        height_mm=Decimal("100"),
        quantity=Decimal("1"),
        model=model,
    )

    assert total == Decimal("2") * Decimal("0.30")
    pl = costing["process_lines"][0]
    assert pl["rate_source"] == "metadata"
    assert pl["rate_hit_layer"] is None
    assert pl["cost_center_id"] == cc.id
    assert pl["rate_per_minute"] == Decimal("0.30")


# ---------------------------------------------------------------------------
# 4) Hub row exists but rate is 0 → defensive fallback (never zero-cost labor)
# ---------------------------------------------------------------------------


def test_hub_zero_rate_falls_back_to_metadata(db_session):
    """A 0-valued Hub rate must not silently zero out labor cost."""
    cc = _seed_cost_center(db_session, "CC_ZERO_TEST", "Test 零费率")
    proc = _seed_process(db_session, code="P_ZERO_TEST", cost_center_id=cc.id)
    model, version = _seed_model_version(db_session)
    line = _seed_version_process_line(
        db_session,
        version_id=version.id,
        process_id=proc.id,
        cost_type="time",
        unit_minutes=4,
        rate_per_minute=0.45,
    )
    ltss.create_strategy(
        db_session,
        payload={
            "rate_type": "labor_per_minute",
            "scope_type": "cost_center",
            "scope_id": cc.id,
            "rate": 0,  # explicit zero — should NOT be applied
            "rate_basis": "per_minute",
        },
    )

    total, costing = bom_generation_service._compute_process_costing(
        db_session,
        process_lines=[line],
        width_mm=Decimal("100"),
        height_mm=Decimal("100"),
        quantity=Decimal("1"),
        model=model,
    )

    # Falls back to ¥0.45 metadata.
    assert total == Decimal("4") * Decimal("0.45")
    pl = costing["process_lines"][0]
    assert pl["rate_source"] == "metadata"
    assert pl["rate_per_minute"] == Decimal("0.45")


# ---------------------------------------------------------------------------
# 5) piece-type costing — Hub labor_per_piece overrides metadata
# ---------------------------------------------------------------------------


def test_hub_labor_per_piece_overrides_metadata(db_session):
    cc = _seed_cost_center(db_session, "CC_PACK_TEST", "Test 包装")
    proc = _seed_process(db_session, code="P_PACK_TEST", cost_center_id=cc.id)
    model, version = _seed_model_version(db_session)
    line = _seed_version_process_line(
        db_session,
        version_id=version.id,
        process_id=proc.id,
        cost_type="piece",
        pricing_method="count",
        piece_rate=1.20,
    )
    ltss.create_strategy(
        db_session,
        payload={
            "rate_type": "labor_per_piece",
            "scope_type": "cost_center",
            "scope_id": cc.id,
            "rate": 1.50,
            "rate_basis": "per_piece",
            "source": "manual",
        },
    )

    total, costing = bom_generation_service._compute_process_costing(
        db_session,
        process_lines=[line],
        width_mm=Decimal("100"),
        height_mm=Decimal("100"),
        quantity=Decimal("3"),  # 3 pieces
        model=model,
    )

    # quantity 3 × ¥1.50 = ¥4.50
    assert total == Decimal("3") * Decimal("1.50")
    pl = costing["process_lines"][0]
    assert pl["rate_source"] == "hub_cost_center"
    assert pl["piece_rate"] == Decimal("1.50")
    assert pl["piece_rate_legacy"] == Decimal("1.20")


# ---------------------------------------------------------------------------
# 6) Hub priority chain — model > cost_center
# ---------------------------------------------------------------------------


def test_hub_model_layer_beats_cost_center(db_session):
    """A model-scoped Hub row must override a cost_center-scoped one."""
    cc = _seed_cost_center(db_session, "CC_HIER_TEST", "Test 层级")
    proc = _seed_process(db_session, code="P_HIER_TEST", cost_center_id=cc.id)
    model, version = _seed_model_version(db_session)
    line = _seed_version_process_line(
        db_session,
        version_id=version.id,
        process_id=proc.id,
        cost_type="time",
        unit_minutes=2,
        rate_per_minute=0.50,
    )
    # cost_center layer: ¥0.80
    ltss.create_strategy(
        db_session,
        payload={
            "rate_type": "labor_per_minute",
            "scope_type": "cost_center",
            "scope_id": cc.id,
            "rate": 0.80,
            "rate_basis": "per_minute",
        },
    )
    # model layer: ¥0.99 — should win
    ltss.create_strategy(
        db_session,
        payload={
            "rate_type": "labor_per_minute",
            "scope_type": "model",
            "scope_id": model.id,
            "rate": 0.99,
            "rate_basis": "per_minute",
            "source": "manual_model_override",
        },
    )

    total, costing = bom_generation_service._compute_process_costing(
        db_session,
        process_lines=[line],
        width_mm=Decimal("100"),
        height_mm=Decimal("100"),
        quantity=Decimal("1"),
        model=model,
    )

    assert total == Decimal("2") * Decimal("0.99")
    pl = costing["process_lines"][0]
    assert pl["rate_source"] == "hub_model"
    assert pl["rate_hit_layer"] == "model"


# ---------------------------------------------------------------------------
# 7) resolve_labor_rate stand-alone — hard_fallback when nothing matches
# ---------------------------------------------------------------------------


def test_resolve_labor_rate_hard_fallback_returns_none(db_session):
    hit = ltss.resolve_labor_rate(db_session, model_id="missing-model")
    assert hit.hit_layer == "hard_fallback"
    assert hit.rate_per_minute is None  # explicitly None — no hardcoded number
    assert hit.strategy_id is None


def test_resolve_labor_rate_chain_global_fallback(db_session):
    """When only a global row exists, it should win over hard_fallback."""
    ltss.create_strategy(
        db_session,
        payload={
            "rate_type": "labor_per_minute",
            "scope_type": "global",
            "rate": 0.55,
            "rate_basis": "per_minute",
        },
    )
    hit = ltss.resolve_labor_rate(db_session, cost_center_id="missing-cc")
    assert hit.hit_layer == "global"
    assert hit.rate_per_minute == Decimal("0.5500")
