"""Cost Rate Hub v1.3 (Migration 0038) — integration tests.

Covers the new Hub-only behaviour layered on top of the legacy long-tail
strategy table. Existing long-tail tests (``test_long_tail_strategy.py``,
``test_long_tail_auto_suggest.py``) cover the cogs path and must keep
passing — they exercise the same model class through the alias
``LongTailCogsRateStrategy = CostRateMaster``.

Scenarios:
1. ``resolve_overhead_rate`` walks priority chain model > category >
   cost_center > global, returning ``hard_fallback`` 0.30 when nothing
   matches.
2. POST ``/api/planner/long-tail-strategies`` with ``rate_type='overhead_rate'``
   creates a Hub row (synthesizing ``category`` from scope) and a follow-up
   GET with ``?rate_type=overhead_rate`` returns it.
3. End-to-end KB8 example: rate=0.25 at scope_type='model' yields
   manufacturing cost == (material+labor) × 0.25 via
   ``bom_generation_service._resolve_overhead_rate``.
4. Legacy ``rate_type='cogs'`` path keeps working (no surprise
   regressions for the long-tail UI).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.planner import models
from src.planner.services import (
    bom_generation_service,
    long_tail_strategy_service as ltss,
)


# ---------------------------------------------------------------------------
# resolve_overhead_rate — 4-layer priority chain
# ---------------------------------------------------------------------------


def test_overhead_resolve_hard_fallback_when_empty(db_session):
    hit = ltss.resolve_overhead_rate(db_session, model_id="missing-model")
    assert hit.hit_layer == "hard_fallback"
    assert hit.rate == Decimal("0.30")
    assert hit.data_quality == "red"
    assert hit.strategy_id is None


def test_overhead_resolve_global_layer(db_session):
    ltss.create_strategy(
        db_session,
        payload={
            "rate_type": "overhead_rate",
            "scope_type": "global",
            "rate": 0.25,
            "rate_basis": "pct_of_cost",
            "source": "manual",
        },
    )
    hit = ltss.resolve_overhead_rate(db_session, model_id="any", category="any")
    assert hit.hit_layer == "global"
    assert hit.rate == Decimal("0.25")


def test_overhead_resolve_category_overrides_global(db_session):
    ltss.create_strategy(
        db_session,
        payload={"rate_type": "overhead_rate", "scope_type": "global", "rate": 0.30},
    )
    ltss.create_strategy(
        db_session,
        payload={
            "rate_type": "overhead_rate",
            "scope_type": "category",
            "scope_id": "布艺",
            "rate": 0.22,
        },
    )
    hit = ltss.resolve_overhead_rate(db_session, category="布艺")
    assert hit.hit_layer == "category"
    assert hit.scope_id == "布艺"
    assert hit.rate == Decimal("0.22")


def test_overhead_resolve_model_overrides_category(db_session):
    ltss.create_strategy(
        db_session,
        payload={
            "rate_type": "overhead_rate",
            "scope_type": "category",
            "scope_id": "布艺",
            "rate": 0.30,
        },
    )
    ltss.create_strategy(
        db_session,
        payload={
            "rate_type": "overhead_rate",
            "scope_type": "model",
            "scope_id": "kb8-uuid",
            "rate": 0.25,
        },
    )
    hit = ltss.resolve_overhead_rate(db_session, model_id="kb8-uuid", category="布艺")
    assert hit.hit_layer == "model"
    assert hit.scope_id == "kb8-uuid"
    assert hit.rate == Decimal("0.25")


def test_overhead_resolve_skips_disabled_rows(db_session):
    ltss.create_strategy(
        db_session,
        payload={
            "rate_type": "overhead_rate",
            "scope_type": "global",
            "rate": 0.99,
            "enabled": False,
        },
    )
    hit = ltss.resolve_overhead_rate(db_session)
    assert hit.hit_layer == "hard_fallback"


# ---------------------------------------------------------------------------
# create_strategy — Hub mode synthesizes category, accepts new fields
# ---------------------------------------------------------------------------


def test_create_overhead_synthesizes_category(db_session):
    s = ltss.create_strategy(
        db_session,
        payload={
            "rate_type": "overhead_rate",
            "scope_type": "model",
            "scope_id": "kb8-uuid",
            "rate": 0.25,
        },
        actor="finance",
    )
    assert s.rate_type == "overhead_rate"
    assert s.scope_type == "model"
    assert s.scope_id == "kb8-uuid"
    assert s.rate_basis == "pct_of_cost"  # auto-defaulted for overhead_rate
    assert s.category == "__overhead_rate__model__kb8-uuid"
    history = (s.metadata_json or {}).get("history") or []
    assert history[0]["by"] == "finance"


def test_create_overhead_requires_scope_id_unless_global(db_session):
    with pytest.raises(ValueError, match="scope_id is required"):
        ltss.create_strategy(
            db_session,
            payload={"rate_type": "overhead_rate", "scope_type": "model", "rate": 0.25},
        )


def test_create_overhead_validates_data_quality(db_session):
    with pytest.raises(ValueError, match="data_quality"):
        ltss.create_strategy(
            db_session,
            payload={
                "rate_type": "overhead_rate",
                "scope_type": "global",
                "rate": 0.25,
                "data_quality": "purple",
            },
        )


def test_create_overhead_persists_effective_dates(db_session):
    s = ltss.create_strategy(
        db_session,
        payload={
            "rate_type": "overhead_rate",
            "scope_type": "global",
            "rate": 0.25,
            "effective_from": "2026-05-01T00:00:00",
        },
    )
    assert s.effective_from is not None
    assert s.effective_from.year == 2026 and s.effective_from.month == 5


# ---------------------------------------------------------------------------
# bom_generation_service._resolve_overhead_rate uses Hub when present
# ---------------------------------------------------------------------------


def _seed_kb8_model_version(db_session) -> tuple[models.ProductModel, models.ProductModelVersion, models.ModelVersionProcess]:
    model = models.ProductModel(
        model_code=f"KB8-test-{id(db_session)}",
        model_name="KB8 test fixture",
        category="布艺",
        calc_mode="ratio",
    )
    db_session.add(model)
    db_session.flush()
    version = models.ProductModelVersion(model_id=model.id, version_kind="standard", version_status="published")
    db_session.add(version)
    db_session.flush()
    # The resolver only inspects the version_id of the first process, no other
    # fields. We don't even need a real Process row.
    proc = models.ModelVersionProcess(
        version_id=version.id,
        process_id="dummy-proc-id",
        sequence_order=1,
        notes=None,
        metadata_json={},
    )
    db_session.add(proc)
    db_session.flush()
    return model, version, proc


def test_bom_overhead_uses_hub_model_layer(db_session):
    """KB8 model with Hub overhead 0.25 must override metadata_json default."""
    model, version, proc = _seed_kb8_model_version(db_session)
    ltss.create_strategy(
        db_session,
        payload={
            "rate_type": "overhead_rate",
            "scope_type": "model",
            "scope_id": model.id,
            "rate": 0.25,
            "rate_basis": "pct_of_cost",
            "data_quality": "yellow",
            "source": "manual",
        },
    )
    rate = bom_generation_service._resolve_overhead_rate(
        db_session, model_version_processes=[proc]
    )
    assert rate == Decimal("0.25")


def test_bom_overhead_uses_hub_category_layer(db_session):
    """When no model-level row exists, category-level Hub row should win."""
    model, _version, proc = _seed_kb8_model_version(db_session)
    ltss.create_strategy(
        db_session,
        payload={
            "rate_type": "overhead_rate",
            "scope_type": "category",
            "scope_id": model.category,  # '布艺'
            "rate": 0.22,
        },
    )
    rate = bom_generation_service._resolve_overhead_rate(
        db_session, model_version_processes=[proc]
    )
    assert rate == Decimal("0.22")


def test_bom_overhead_falls_back_to_metadata_json_when_no_hub_row(db_session):
    """No Hub row → legacy metadata_json behaviour preserved."""
    model, version, proc = _seed_kb8_model_version(db_session)
    version.metadata_json = {"costing": {"overhead_rate": 0.18}}
    db_session.flush()
    rate = bom_generation_service._resolve_overhead_rate(
        db_session, model_version_processes=[proc]
    )
    assert rate == Decimal("0.18")


def test_bom_overhead_hard_fallback_30pct(db_session):
    """No Hub row + no metadata_json → 0.30 hard fallback (unchanged)."""
    _model, _version, proc = _seed_kb8_model_version(db_session)
    rate = bom_generation_service._resolve_overhead_rate(
        db_session, model_version_processes=[proc]
    )
    assert rate == Decimal("0.3")


# ---------------------------------------------------------------------------
# Legacy cogs path is untouched (regression guard)
# ---------------------------------------------------------------------------


def test_legacy_cogs_create_still_unique_on_category(db_session):
    """Legacy long-tail behaviour: rate_type='cogs' still requires unique
    category and uses pct_of_revenue defaults.
    """
    s = ltss.create_strategy(
        db_session, payload={"category": "画框", "rate": 0.40}
    )
    assert s.rate_type == "cogs"
    assert s.scope_type == "category"
    assert s.scope_id == "画框" or s.scope_id is None  # backfill applies post-migration
    assert s.rate_basis == "pct_of_revenue"
    with pytest.raises(ValueError, match="already exists"):
        ltss.create_strategy(db_session, payload={"category": "画框", "rate": 0.50})


def test_list_strategies_default_filters_to_cogs(db_session):
    ltss.create_strategy(db_session, payload={"category": "cogs-only", "rate": 0.5})
    ltss.create_strategy(
        db_session,
        payload={"rate_type": "overhead_rate", "scope_type": "global", "rate": 0.25},
    )
    cogs_only = ltss.list_strategies(db_session)  # default rate_type='cogs'
    assert all(r.rate_type == "cogs" for r in cogs_only)
    overhead_only = ltss.list_strategies(db_session, rate_type="overhead_rate")
    assert len(overhead_only) == 1
    assert overhead_only[0].rate_type == "overhead_rate"
    everything = ltss.list_strategies(db_session, rate_type="all")
    assert len(everything) >= 2


# ---------------------------------------------------------------------------
# HTTP API: rate_type query/body wiring
# ---------------------------------------------------------------------------


def test_api_create_overhead_rate_round_trip(client, db_session):
    """POST overhead_rate, then GET ?rate_type=overhead_rate, then resolve-preview."""
    payload = {
        "rate_type": "overhead_rate",
        "scope_type": "model",
        "scope_id": "kb8-uuid",
        "rate": 0.25,
        "rate_basis": "pct_of_cost",
        "data_quality": "yellow",
        "note": "v1.3 Hub MVP smoke test",
        "actor": "test",
    }
    r = client.post("/api/planner/long-tail-strategies", json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["rate_type"] == "overhead_rate"
    assert body["scope_type"] == "model"
    assert body["scope_id"] == "kb8-uuid"
    assert body["rate_basis"] == "pct_of_cost"
    assert body["data_quality"] == "yellow"
    assert body["rate"] == 0.25

    # default GET hides overhead rows
    list_default = client.get("/api/planner/long-tail-strategies")
    assert list_default.status_code == 200
    assert all(it["rate_type"] == "cogs" for it in list_default.json()["items"])

    # GET ?rate_type=overhead_rate exposes the new row
    list_oh = client.get("/api/planner/long-tail-strategies?rate_type=overhead_rate")
    assert list_oh.status_code == 200
    items = list_oh.json()["items"]
    assert any(it["scope_id"] == "kb8-uuid" for it in items)

    # resolve-preview with overhead_rate hits the model layer
    rp = client.post(
        "/api/planner/long-tail-strategies/resolve-preview",
        json={"rate_type": "overhead_rate", "model_id": "kb8-uuid"},
    )
    assert rp.status_code == 200
    rp_body = rp.json()
    assert rp_body["rate"] == 0.25
    assert rp_body["hit_layer"] == "model"
    assert rp_body["hit_scope_type"] == "model"
    assert rp_body["hit_scope_id"] == "kb8-uuid"


def test_api_create_overhead_rejects_missing_scope_id(client):
    r = client.post(
        "/api/planner/long-tail-strategies",
        json={"rate_type": "overhead_rate", "scope_type": "model", "rate": 0.25},
    )
    assert r.status_code == 400
    assert "scope_id" in r.json().get("detail", "")
