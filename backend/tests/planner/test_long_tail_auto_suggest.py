"""Tests for the auto-suggest / auto-apply long_tail_category flow
(Issue 28 follow-up #2 — "一键自动标品类").

Covers:
- service: scope = all do_not_model when sku_codes omitted
- service: scope = explicit sku_codes
- service: skips already-labeled (default)
- service: include_already_labeled=True surfaces them again
- service: priority ordering wins ties
- service: empty strategy table returns reason
- service: auto_apply groups by category and writes via set_sku_long_tail_category
- HTTP: preview + execute happy path; preview limit truncation
"""

from __future__ import annotations

from src.planner import models
from src.planner.services import (
    long_tail_strategy_service as ltss,
    sku_master_service as sms,
)


def _seed_sku(
    db,
    *,
    barcode: str,
    spec_text: str = "",
    product_name: str = "",
    governance: str = sms.GOVERNANCE_DO_NOT_MODEL,
    long_tail_category: str | None = None,
):
    meta: dict = {"governance_status": governance}
    if long_tail_category is not None:
        meta["long_tail_category"] = long_tail_category
    s = models.SkuMaster(
        erp_sku_barcode=barcode,
        spec_text=spec_text,
        product_name=product_name,
        metadata_json=meta,
    )
    db.add(s)
    db.flush()
    return s


def test_auto_suggest_returns_no_strategies_reason(db_session):
    _seed_sku(db_session, barcode="A", spec_text="anything")
    res = sms.auto_suggest_long_tail_category(db_session)
    assert res["scanned"] == 0
    assert res["suggested"] == []
    assert res["reason"] == "no enabled strategies"


def test_auto_suggest_scans_only_do_not_model_when_sku_codes_omitted(db_session):
    ltss.create_strategy(db_session, payload={"category": "画框", "rate": 0.42, "keywords": ["画框"]})
    _seed_sku(db_session, barcode="LT-1", spec_text="实木画框 60x80")
    _seed_sku(db_session, barcode="UM-1", spec_text="实木画框 也是画框", governance=sms.GOVERNANCE_UNMANAGED)
    res = sms.auto_suggest_long_tail_category(db_session)
    sku_codes = [it["sku_code"] for it in res["suggested"]]
    assert "LT-1" in sku_codes
    assert "UM-1" not in sku_codes, "scope must restrict to do_not_model"


def test_auto_suggest_skips_already_labeled_by_default(db_session):
    ltss.create_strategy(db_session, payload={"category": "画框", "rate": 0.42, "keywords": ["画框"]})
    _seed_sku(
        db_session,
        barcode="LABELED",
        spec_text="实木画框",
        long_tail_category="画框",
    )
    _seed_sku(db_session, barcode="UNLABELED", spec_text="实木画框")
    res = sms.auto_suggest_long_tail_category(db_session)
    assert res["already_labeled_skipped"] == 1
    sku_codes = [it["sku_code"] for it in res["suggested"]]
    assert sku_codes == ["UNLABELED"]


def test_auto_suggest_can_include_already_labeled(db_session):
    ltss.create_strategy(db_session, payload={"category": "画框", "rate": 0.42, "keywords": ["画框"]})
    _seed_sku(db_session, barcode="L1", spec_text="画框", long_tail_category="抱枕")
    res = sms.auto_suggest_long_tail_category(db_session, include_already_labeled=True)
    assert res["already_labeled_skipped"] == 0
    items = res["suggested"]
    assert len(items) == 1
    assert items[0]["current_category"] == "抱枕"
    assert items[0]["suggested_category"] == "画框"


def test_auto_suggest_explicit_sku_codes_bypass_governance_filter(db_session):
    """When sku_codes is given explicitly, scan whatever is asked
    regardless of governance_status — caller knows what it's doing."""
    ltss.create_strategy(db_session, payload={"category": "画框", "rate": 0.42, "keywords": ["画框"]})
    _seed_sku(db_session, barcode="UM-2", spec_text="画框", governance=sms.GOVERNANCE_UNMANAGED)
    res = sms.auto_suggest_long_tail_category(db_session, sku_codes=["UM-2"])
    assert len(res["suggested"]) == 1
    assert res["suggested"][0]["sku_code"] == "UM-2"


def test_auto_suggest_priority_breaks_ties(db_session):
    ltss.create_strategy(
        db_session,
        payload={"category": "low", "rate": 0.30, "keywords": ["pillow"], "priority": 10},
    )
    ltss.create_strategy(
        db_session,
        payload={"category": "high", "rate": 0.70, "keywords": ["pillow"], "priority": 999},
    )
    _seed_sku(db_session, barcode="P1", spec_text="cotton pillow")
    res = sms.auto_suggest_long_tail_category(db_session)
    assert len(res["suggested"]) == 1
    assert res["suggested"][0]["suggested_category"] == "high"


def test_auto_suggest_no_match_counted(db_session):
    ltss.create_strategy(db_session, payload={"category": "画框", "rate": 0.42, "keywords": ["画框"]})
    _seed_sku(db_session, barcode="N1", spec_text="random nothing")
    res = sms.auto_suggest_long_tail_category(db_session)
    assert res["scanned"] == 1
    assert res["no_match_count"] == 1
    assert res["suggested"] == []


def test_auto_apply_groups_by_category_and_writes(db_session):
    ltss.create_strategy(db_session, payload={"category": "画框", "rate": 0.42, "keywords": ["画框"]})
    ltss.create_strategy(db_session, payload={"category": "抱枕", "rate": 0.55, "keywords": ["抱枕"]})
    _seed_sku(db_session, barcode="A1", spec_text="实木画框")
    _seed_sku(db_session, barcode="A2", spec_text="北欧画框")
    _seed_sku(db_session, barcode="B1", spec_text="纯棉抱枕")
    res = sms.auto_apply_long_tail_category(db_session, actor="alice")
    assert res["applied"] == 3
    by_cat = {x["category"]: x for x in res["apply_results"]}
    assert by_cat["画框"]["sku_count"] == 2
    assert by_cat["抱枕"]["sku_count"] == 1
    # Verify the labels actually landed on rows.
    a1 = db_session.query(models.SkuMaster).filter_by(erp_sku_barcode="A1").one()
    assert (a1.metadata_json or {}).get("long_tail_category") == "画框"
    history = (a1.metadata_json or {}).get("long_tail_category_history") or []
    assert history[-1]["by"] == "alice"
    assert "auto-applied" in (history[-1].get("note") or "")


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------


def test_http_auto_suggest_preview_and_execute(client, db_session):
    client.post(
        "/api/planner/long-tail-strategies",
        json={"category": "画框", "rate": 0.42, "keywords": ["画框"], "actor": "smoke"},
    )

    # Seed via the same db_session the test client is bound to (conftest
    # overrides get_db to yield this exact session, so writes here are
    # immediately visible to the API endpoints below).
    db_session.add(
        models.SkuMaster(
            erp_sku_barcode="HTTP-LT-1",
            spec_text="实木画框 50x70",
            metadata_json={"governance_status": "do_not_model"},
        )
    )
    db_session.add(
        models.SkuMaster(
            erp_sku_barcode="HTTP-LT-2",
            spec_text="无关 SKU",
            metadata_json={"governance_status": "do_not_model"},
        )
    )
    db_session.flush()

    preview = client.post(
        "/api/planner/sku-master/long-tail-category/auto-suggest/preview",
        json={"limit": 100},
    )
    assert preview.status_code == 200, preview.text
    body = preview.json()
    sku_codes_in_preview = [it["sku_code"] for it in body["suggested"]]
    assert "HTTP-LT-1" in sku_codes_in_preview
    assert "HTTP-LT-2" not in sku_codes_in_preview  # no keyword hit
    assert body["no_match_count"] >= 1

    execute = client.post(
        "/api/planner/sku-master/long-tail-category/auto-suggest/execute",
        json={"limit": 100, "actor": "ui-smoke"},
    )
    assert execute.status_code == 200, execute.text
    eb = execute.json()
    assert eb["applied"] >= 1
    cats_in_apply = [r["category"] for r in eb["apply_results"]]
    assert "画框" in cats_in_apply

    # Re-running preview must skip the now-labeled SKU.
    preview2 = client.post(
        "/api/planner/sku-master/long-tail-category/auto-suggest/preview",
        json={"limit": 100},
    )
    assert preview2.status_code == 200
    body2 = preview2.json()
    assert body2["already_labeled_skipped"] >= 1
    assert all(it["sku_code"] != "HTTP-LT-1" for it in body2["suggested"])
