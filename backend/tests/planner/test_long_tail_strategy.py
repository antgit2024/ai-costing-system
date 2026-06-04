"""Tests for long-tail COGS rate strategy (Issue 28).

Covers:
- service: CRUD + audit history
- service: resolve_rate_for_sku 4-step priority chain (manual / keyword /
  default_strategy / global_setting)
- integration: shipment_import_service.long_tail_fallback_snapshot picks
  the right per-category rate and records it in trace_json + costing
- HTTP: list / create / patch / delete + resolve-preview
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.planner import models
from src.planner.services import (
    long_tail_strategy_service as ltss,
    shipment_import_service,
    sku_master_service as sms,
)


# ---------------------------------------------------------------------------
# helpers (mirrors test_shipment_import_governance_gating.py)
# ---------------------------------------------------------------------------


def _seed_sku(db, *, barcode: str, spec_text: str = "", product_name: str = "", metadata: dict | None = None):
    sku = models.SkuMaster(
        erp_sku_barcode=barcode,
        spec_text=spec_text,
        product_name=product_name,
        metadata_json={"governance_status": sms.GOVERNANCE_DO_NOT_MODEL, **(metadata or {})},
    )
    db.add(sku)
    db.flush()
    return sku


def _seed_batch_with_line(db, *, sku_code: str, file_hash: str, revenue: float = 100.0):
    batch = models.ShipmentImportBatch(
        file_name=f"test-{sku_code}.xlsx",
        file_hash=file_hash,
        export_date="2026-05-07",
        requested_by="test",
        status="processing",
        result_json={"processor": "test"},
    )
    db.add(batch)
    db.flush()
    line = models.ShipmentLine(
        batch_id=batch.id,
        row_index=1,
        shipment_no=f"S-{sku_code}",
        sku_code=sku_code,
        spec_text="规格不重要",
        qty=Decimal("1"),
        revenue_amount=Decimal(str(revenue)),
        external_line_key_hash=f"h-{sku_code}",
        is_active=True,
    )
    db.add(line)
    db.flush()
    return batch, line


# ---------------------------------------------------------------------------
# Service: CRUD + audit
# ---------------------------------------------------------------------------


def test_create_strategy_sets_history(db_session):
    s = ltss.create_strategy(
        db_session,
        payload={
            "category": "画框",
            "rate": 0.40,
            "keywords": ["画框", "frame"],
            "priority": 200,
            "note": "财务 2026-Q2 校准",
        },
        actor="alice",
    )
    assert s.id and s.category == "画框"
    assert float(s.rate) == 0.40
    assert s.keywords_json == ["画框", "frame"]
    history = (s.metadata_json or {}).get("history") or []
    assert len(history) == 1
    assert history[0]["by"] == "alice"
    assert history[0]["before"] is None
    assert history[0]["after"]["rate"] == 0.40


def test_create_strategy_rejects_duplicate_category(db_session):
    ltss.create_strategy(db_session, payload={"category": "抱枕", "rate": 0.5})
    with pytest.raises(ValueError, match="already exists"):
        ltss.create_strategy(db_session, payload={"category": "抱枕", "rate": 0.6})


def test_create_strategy_validates_rate_range(db_session):
    with pytest.raises(ValueError, match="between 0 and 1"):
        ltss.create_strategy(db_session, payload={"category": "bad", "rate": 1.5})
    with pytest.raises(ValueError, match="between 0 and 1"):
        ltss.create_strategy(db_session, payload={"category": "bad", "rate": -0.1})


def test_update_strategy_appends_history(db_session):
    s = ltss.create_strategy(
        db_session, payload={"category": "地毯", "rate": 0.50}, actor="alice"
    )
    s2 = ltss.update_strategy(
        db_session,
        strategy_id=s.id,
        patch={"rate": 0.62, "note": "上调"},
        actor="bob",
    )
    assert float(s2.rate) == 0.62
    history = (s2.metadata_json or {}).get("history") or []
    assert len(history) == 2
    assert history[-1]["by"] == "bob"
    assert history[-1]["before"]["rate"] == 0.50
    assert history[-1]["after"]["rate"] == 0.62


def test_delete_strategy_soft_deletes(db_session):
    s = ltss.create_strategy(
        db_session, payload={"category": "to-delete", "rate": 0.3}
    )
    ltss.delete_strategy(db_session, strategy_id=s.id, actor="bob")
    refreshed = ltss.get_strategy(db_session, strategy_id=s.id)
    assert refreshed is not None
    assert refreshed.is_archived is True
    assert refreshed.enabled is False
    listed = ltss.list_strategies(db_session)
    assert all(x.id != s.id for x in listed)


def test_create_revives_archived_same_category(db_session):
    """Re-creating a soft-deleted category must revive the row, not 400.

    Background: unique constraint is on `category` alone, so a second
    INSERT would violate uq_long_tail_cogs_rate_category. The service
    detects the archived row and overwrites it instead.
    """
    s1 = ltss.create_strategy(
        db_session, payload={"category": "revive-me", "rate": 0.30}, actor="alice"
    )
    sid = s1.id
    ltss.delete_strategy(db_session, strategy_id=sid, actor="bob")

    s2 = ltss.create_strategy(
        db_session,
        payload={"category": "revive-me", "rate": 0.55, "keywords": ["x"]},
        actor="charlie",
    )
    # Same row (id preserved), revived, with new values.
    assert s2.id == sid
    assert s2.is_archived is False
    assert s2.enabled is True
    assert float(s2.rate) == 0.55
    assert s2.keywords_json == ["x"]
    history = (s2.metadata_json or {}).get("history") or []
    assert any(h.get("change_note") == "revived" for h in history)


def test_create_active_duplicate_still_400(db_session):
    """Active (non-archived) duplicate still rejected — only archived ones revive."""
    ltss.create_strategy(db_session, payload={"category": "active-dup", "rate": 0.5})
    with pytest.raises(ValueError, match="already exists"):
        ltss.create_strategy(db_session, payload={"category": "active-dup", "rate": 0.6})


# ---------------------------------------------------------------------------
# Service: resolve_rate_for_sku priority chain
# ---------------------------------------------------------------------------


def test_resolve_falls_back_to_global_when_no_strategy(db_session, monkeypatch):
    from src.config import settings

    monkeypatch.setattr(settings, "long_tail_cogs_rate", 0.55)
    sku = _seed_sku(db_session, barcode="X-NOMATCH", spec_text="random")
    r = ltss.resolve_rate_for_sku(db_session, sku=sku)
    assert r.source == "global_setting"
    assert r.rate == 0.55
    assert r.strategy_id is None


def test_resolve_uses_keyword_match(db_session):
    ltss.create_strategy(
        db_session,
        payload={"category": "画框", "rate": 0.40, "keywords": ["画框", "frame"], "priority": 100},
    )
    sku = _seed_sku(
        db_session,
        barcode="P-1",
        spec_text="实木画框 60x80cm",
        product_name="北欧风装饰画",
    )
    r = ltss.resolve_rate_for_sku(db_session, sku=sku)
    assert r.source == "keyword"
    assert r.category == "画框"
    assert r.rate == 0.40
    assert r.matched_keyword == "画框"


def test_resolve_priority_breaks_ties(db_session):
    """When multiple keyword strategies match, highest priority wins."""
    ltss.create_strategy(
        db_session,
        payload={"category": "low-prio", "rate": 0.30, "keywords": ["pillow"], "priority": 10},
    )
    ltss.create_strategy(
        db_session,
        payload={"category": "high-prio", "rate": 0.70, "keywords": ["pillow"], "priority": 999},
    )
    sku = _seed_sku(db_session, barcode="P-2", spec_text="cotton pillow")
    r = ltss.resolve_rate_for_sku(db_session, sku=sku)
    assert r.category == "high-prio"
    assert r.rate == 0.70


def test_resolve_disabled_strategy_is_skipped(db_session):
    ltss.create_strategy(
        db_session,
        payload={
            "category": "disabled-cat",
            "rate": 0.99,
            "keywords": ["match-me"],
            "enabled": False,
        },
    )
    sku = _seed_sku(db_session, barcode="P-3", spec_text="match-me everywhere")
    r = ltss.resolve_rate_for_sku(db_session, sku=sku)
    assert r.source == "global_setting"


def test_resolve_uses_default_strategy_when_no_keyword_hit(db_session):
    ltss.create_strategy(
        db_session,
        payload={"category": "画框", "rate": 0.40, "keywords": ["frame"]},
    )
    ltss.create_strategy(
        db_session,
        payload={"category": "default", "rate": 0.50, "keywords": []},
    )
    sku = _seed_sku(db_session, barcode="P-4", spec_text="random nothing matches")
    r = ltss.resolve_rate_for_sku(db_session, sku=sku)
    assert r.source == "default_strategy"
    assert r.category == "default"
    assert r.rate == 0.50


def test_resolve_manual_category_overrides_keywords(db_session):
    """Even when a keyword would match, an explicit human category wins."""
    ltss.create_strategy(
        db_session,
        payload={"category": "画框", "rate": 0.40, "keywords": ["画框"], "priority": 999},
    )
    ltss.create_strategy(
        db_session,
        payload={"category": "抱枕", "rate": 0.60, "keywords": []},
    )
    sku = _seed_sku(
        db_session,
        barcode="P-5",
        spec_text="画框风格抱枕",
        metadata={"long_tail_category": "抱枕"},
    )
    r = ltss.resolve_rate_for_sku(db_session, sku=sku)
    assert r.source == "manual"
    assert r.category == "抱枕"
    assert r.rate == 0.60


# ---------------------------------------------------------------------------
# Integration: shipment_import_service uses the resolver
# ---------------------------------------------------------------------------


def test_long_tail_fallback_snapshot_uses_strategy_rate(db_session):
    """End-to-end: when shipment_import_service generates a long-tail
    snapshot for a SKU whose spec matches a strategy keyword, the rate
    used must come from the strategy table (not the global setting), and
    trace_json must record the strategy id + source for audit.
    """
    ltss.create_strategy(
        db_session,
        payload={
            "category": "画框",
            "rate": 0.30,
            "keywords": ["画框"],
            "priority": 200,
        },
    )
    sku = _seed_sku(
        db_session,
        barcode="LT-FRAME",
        spec_text="实木画框 50x70",
        product_name="装饰画 画框 北欧",
    )
    batch, line = _seed_batch_with_line(
        db_session, sku_code="LT-FRAME", file_hash="h-frame", revenue=200.0
    )

    snap = shipment_import_service._finalize_shipment_line(
        db_session, batch=batch, line=line
    )
    assert snap is not None
    trace = snap.trace_json or {}
    assert trace.get("kind") == "long_tail_fallback"
    assert trace.get("rate_source") == "keyword"
    assert trace.get("strategy_category") == "画框"
    assert trace.get("matched_keyword") == "画框"
    # Rate must be 0.30 from the strategy, NOT the global 0.55.
    assert float(trace.get("long_tail_cogs_rate")) == 0.30

    costing = (
        db_session.query(models.ShipmentCostingResult)
        .filter(models.ShipmentCostingResult.shipment_line_id == line.id)
        .first()
    )
    assert costing is not None
    # cogs = revenue * 0.30 = 60.00
    assert float(costing.cost_total) == 60.00
    md = costing.metadata_json or {}
    assert md.get("rate_source") == "keyword"
    assert md.get("strategy_category") == "画框"


def test_long_tail_fallback_falls_back_to_global_when_no_strategy(db_session, monkeypatch):
    """Backward-compat: existing behaviour preserved when strategy table is empty."""
    from src.config import settings

    monkeypatch.setattr(settings, "long_tail_cogs_rate", 0.55)
    sku = _seed_sku(db_session, barcode="LT-NOMATCH", spec_text="无匹配")
    batch, line = _seed_batch_with_line(
        db_session, sku_code="LT-NOMATCH", file_hash="h-nomatch", revenue=100.0
    )
    snap = shipment_import_service._finalize_shipment_line(
        db_session, batch=batch, line=line
    )
    assert snap is not None
    trace = snap.trace_json or {}
    assert trace.get("rate_source") == "global_setting"
    assert float(trace.get("long_tail_cogs_rate")) == 0.55


# ---------------------------------------------------------------------------
# HTTP routes
# ---------------------------------------------------------------------------


def test_http_list_create_patch_delete_strategy(client):
    resp = client.get("/api/planner/long-tail-strategies")
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert "global_fallback_rate" in data

    create = client.post(
        "/api/planner/long-tail-strategies",
        json={"category": "画框", "rate": 0.42, "keywords": ["画框"], "actor": "alice"},
    )
    assert create.status_code == 200, create.text
    sid = create.json()["id"]

    listed = client.get("/api/planner/long-tail-strategies")
    assert listed.status_code == 200
    items = listed.json()["items"]
    assert len(items) == 1
    assert items[0]["category"] == "画框"
    assert items[0]["rate"] == 0.42

    patched = client.patch(
        f"/api/planner/long-tail-strategies/{sid}",
        json={"rate": 0.55, "note": "上调", "actor": "bob"},
    )
    assert patched.status_code == 200
    assert patched.json()["rate"] == 0.55
    history = patched.json()["metadata"].get("history") or []
    assert len(history) == 2

    deleted = client.delete(f"/api/planner/long-tail-strategies/{sid}?actor=bob")
    assert deleted.status_code == 200
    listed2 = client.get("/api/planner/long-tail-strategies")
    assert listed2.json()["items"] == []


def test_http_create_validation_errors(client):
    bad = client.post(
        "/api/planner/long-tail-strategies",
        json={"category": "x", "rate": 1.5},
    )
    assert bad.status_code == 422  # pydantic validator catches le=1.0

    missing = client.post(
        "/api/planner/long-tail-strategies",
        json={"category": "x"},
    )
    assert missing.status_code == 400

    client.post(
        "/api/planner/long-tail-strategies",
        json={"category": "dup", "rate": 0.5},
    )
    dup = client.post(
        "/api/planner/long-tail-strategies",
        json={"category": "dup", "rate": 0.6},
    )
    assert dup.status_code == 400
    assert "already exists" in dup.json()["detail"]


def test_http_resolve_preview(client):
    client.post(
        "/api/planner/long-tail-strategies",
        json={"category": "画框", "rate": 0.40, "keywords": ["画框"]},
    )
    preview = client.post(
        "/api/planner/long-tail-strategies/resolve-preview",
        json={"spec_text": "实木画框 60x80"},
    )
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["source"] == "keyword"
    assert body["category"] == "画框"
    assert body["rate"] == 0.40
    assert body["matched_keyword"] == "画框"

    nomatch = client.post(
        "/api/planner/long-tail-strategies/resolve-preview",
        json={"spec_text": "完全不匹配"},
    )
    assert nomatch.status_code == 200
    assert nomatch.json()["source"] == "global_setting"
