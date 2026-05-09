"""U7-A — Insights cost-quality badge service tests.

Covers the in-memory ``cost_quality_service`` helper that the 5 analytics
endpoints (returns-rate/sku, returns-rate/channel, profit/sku,
profit/channel, profit/model) and ``models/summary`` use to attach a
``cost_quality`` field to every row without N+1 queries.

Three core scenarios (per task brief §4):

1. Model-level config (KB8 example): a row with ``rate_type=overhead_rate``
   and ``scope_type=model`` yields a ``green`` badge whose ``hit_layer`` is
   ``model``.
2. No model config + no global: falls all the way through to
   ``hard_fallback`` red (signals "no Hub row at all → 0.30 hardcoded").
3. Aggregation: when an analytics row rolls up multiple SKU/model badges
   the worst level wins (``red`` > ``yellow`` > ``green``).
"""

from __future__ import annotations

from src.planner.services import (
    cost_quality_service,
    long_tail_strategy_service as ltss,
)


# ---------------------------------------------------------------------------
# 1. Model-level Hub row → green/model
# ---------------------------------------------------------------------------


def test_model_level_overhead_yields_green_badge(db_session):
    """KB8 example: model-scoped overhead_rate row → 🟢 hit_layer=model."""
    ltss.create_strategy(
        db_session,
        payload={
            "rate_type": "overhead_rate",
            "scope_type": "model",
            "scope_id": "kb8-model-id",
            "rate": 0.25,
            "rate_basis": "pct_of_cost",
            "source": "manual",
        },
    )

    lookup = cost_quality_service.build_overhead_quality_lookup(db_session)
    badge = cost_quality_service.derive_badge_for_model(
        lookup, model_id="kb8-model-id"
    )
    assert badge["level"] == "green"
    assert badge["hit_layer"] == "model"
    assert badge["source"] == "manual"
    assert badge["updated_at"] is not None


def test_category_level_yields_yellow_badge(db_session):
    ltss.create_strategy(
        db_session,
        payload={
            "rate_type": "overhead_rate",
            "scope_type": "category",
            "scope_id": "布艺",
            "rate": 0.22,
        },
    )
    lookup = cost_quality_service.build_overhead_quality_lookup(db_session)
    badge = cost_quality_service.derive_badge_for_model(
        lookup, model_id="missing-model", category="布艺"
    )
    assert badge["level"] == "yellow"
    assert badge["hit_layer"] == "category"


# ---------------------------------------------------------------------------
# 2. Hard-fallback when nothing matches
# ---------------------------------------------------------------------------


def test_hard_fallback_when_no_rows(db_session):
    """No cost_rate_master rows at all → 🔴 hard_fallback / hardcoded_0.30."""
    lookup = cost_quality_service.build_overhead_quality_lookup(db_session)
    badge = cost_quality_service.derive_badge_for_model(
        lookup, model_id="any-model"
    )
    assert badge["level"] == "red"
    assert badge["hit_layer"] == "hard_fallback"
    assert badge["source"] == "hardcoded_0.30"


def test_global_layer_yields_red_badge(db_session):
    """Only global row exists → 🔴 hit_layer=global (still red per §3.2)."""
    ltss.create_strategy(
        db_session,
        payload={"rate_type": "overhead_rate", "scope_type": "global", "rate": 0.30},
    )
    lookup = cost_quality_service.build_overhead_quality_lookup(db_session)
    badge = cost_quality_service.derive_badge_for_model(
        lookup, model_id="unknown-model"
    )
    assert badge["level"] == "red"
    assert badge["hit_layer"] == "global"


# ---------------------------------------------------------------------------
# 3. Aggregation — worst level wins
# ---------------------------------------------------------------------------


def test_aggregate_quality_picks_worst_level(db_session):
    """Roll-up over green + yellow + red → red (保守显示)."""
    ltss.create_strategy(
        db_session,
        payload={
            "rate_type": "overhead_rate",
            "scope_type": "model",
            "scope_id": "model-a",
            "rate": 0.20,
        },
    )
    ltss.create_strategy(
        db_session,
        payload={
            "rate_type": "overhead_rate",
            "scope_type": "category",
            "scope_id": "cat-b",
            "rate": 0.22,
        },
    )

    lookup = cost_quality_service.build_overhead_quality_lookup(db_session)
    # green for model-a, yellow for category cat-b, red hard_fallback for unknown
    badges = [
        cost_quality_service.derive_badge_for_model(lookup, model_id="model-a"),
        cost_quality_service.derive_badge_for_model(
            lookup, model_id="missing-x", category="cat-b"
        ),
        cost_quality_service.derive_badge_for_model(lookup, model_id="totally-unknown"),
    ]
    levels = [b["level"] for b in badges]
    assert "green" in levels
    assert "yellow" in levels
    assert "red" in levels

    rolled = cost_quality_service.aggregate_quality(badges)
    assert rolled is not None
    assert rolled["level"] == "red"


def test_aggregate_quality_all_green_returns_green(db_session):
    ltss.create_strategy(
        db_session,
        payload={
            "rate_type": "overhead_rate",
            "scope_type": "model",
            "scope_id": "m1",
            "rate": 0.20,
        },
    )
    ltss.create_strategy(
        db_session,
        payload={
            "rate_type": "overhead_rate",
            "scope_type": "model",
            "scope_id": "m2",
            "rate": 0.25,
        },
    )
    lookup = cost_quality_service.build_overhead_quality_lookup(db_session)
    rolled = cost_quality_service.aggregate_quality(
        [
            cost_quality_service.derive_badge_for_model(lookup, model_id="m1"),
            cost_quality_service.derive_badge_for_model(lookup, model_id="m2"),
        ]
    )
    assert rolled is not None
    assert rolled["level"] == "green"
    assert rolled["hit_layer"] == "model"


def test_aggregate_quality_empty_returns_none():
    assert cost_quality_service.aggregate_quality([]) is None
    assert cost_quality_service.aggregate_quality([None, None]) is None


# ---------------------------------------------------------------------------
# 4. Pydantic schema parses the dict cleanly (response payload contract)
# ---------------------------------------------------------------------------


def test_badge_dict_serializes_into_pydantic_schema():
    from src.planner.schemas import CostQualityBadge

    raw = {
        "level": "green",
        "hit_layer": "model",
        "source": "cost_rate_hub",
        "updated_at": "2026-05-09T18:00:00",
    }
    badge = CostQualityBadge(**raw)
    assert badge.level == "green"
    assert badge.hit_layer == "model"
    assert badge.dict() == raw
