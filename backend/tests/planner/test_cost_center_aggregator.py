"""Tests for cost_center_aggregator_service (Path A §A2)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List
from unittest.mock import patch

import pytest

from src.planner import models
from src.planner.services import (
    cost_center_aggregator_service as agg,
    cost_center_service as ccs,
    long_tail_strategy_service as ltss,
)
from src.planner.services.finance_c1_client import FinanceC1Error


def _seed_cc(
    db, *, code: str, name: str, department_mapping: List[str] | None = None,
    type_: str = "production",
) -> models.CostCenter:
    return ccs.create_cost_center(
        db,
        payload={
            "code": code,
            "name": name,
            "type": type_,
            "metadata": {
                "finance_department_mapping": department_mapping or [],
            },
        },
        actor="test",
    )


def _fake_envelope(rows, source="mock"):
    class _Env:
        def __init__(self, data, src):
            self.data = data
            self.data_source = src

    return _Env(rows, source)


def _payroll_row(
    *,
    employee_id: str,
    company_id: str = "co-1",
    department: str = "缝纫一组",
    actual_paid: float = 6000,
    period_year: int = 2026,
    period_month: int = 4,
) -> Dict[str, Any]:
    return {
        "employee_id": employee_id,
        "name_masked": "X**",
        "company_id": company_id,
        "department_raw": department,
        "period_year": period_year,
        "period_month": period_month,
        "gross_salary": actual_paid + 500,
        "employer_insurance": 1000,
        "total_labor_cost": actual_paid + 1500,
        "metadata": {"actual_paid": actual_paid, "payment_source_types": ["recon"]},
    }


def _companies_envelope():
    return _fake_envelope(
        [
            {
                "id": "co-1",
                "legal_name": "工厂 1",
                "tax_payer_type": "general",
                "entity_role": "factory",
                "is_active": True,
                "payroll_recognition": True,
                "material_purchase_recognition": True,
                "fixed_cost_recognition": True,
                "revenue_recognition": False,
                "floor_area_sqm": 1000.0,
            },
        ]
    )


# ---------------------------------------------------------------------------
# Single cost_center aggregation
# ---------------------------------------------------------------------------


def test_aggregate_single_cc_happy_path(db_session):
    cc = _seed_cc(
        db_session,
        code="CC_FABRIC",
        name="布艺组",
        department_mapping=["缝纫一组", "缝纫二组"],
    )

    payroll_rows = [
        _payroll_row(employee_id="e1", department="缝纫一组", actual_paid=6000),
        _payroll_row(employee_id="e2", department="缝纫二组", actual_paid=5500),
        _payroll_row(employee_id="e3", department="包装组", actual_paid=4500),
    ]

    with patch(
        "src.planner.services.cost_center_aggregator_service.get_finance_c1_client"
    ) as mock_client:
        client = mock_client.return_value
        client.list_companies.return_value = _companies_envelope()
        client.list_payroll.return_value = _fake_envelope(payroll_rows)
        result = agg.aggregate_cost_center_payroll(
            db_session, cost_center_id=cc.id, period="2026-04"
        )
    snap = result.snapshot
    assert snap.cost_center_id == cc.id
    assert snap.period == "2026-04"
    assert snap.headcount == 2
    assert float(snap.total_paid) == 11500.0
    assert float(snap.avg_salary) == 5750.0
    assert snap.data_source == "finance_payroll"
    assert snap.data_quality == "yellow"


def test_aggregate_single_cc_finance_unavailable(db_session):
    cc = _seed_cc(db_session, code="CC_X", name="X", department_mapping=["缝纫"])
    with patch(
        "src.planner.services.cost_center_aggregator_service.get_finance_c1_client"
    ) as mock_client:
        client = mock_client.return_value
        client.list_companies.side_effect = FinanceC1Error("down")
        client.list_payroll.side_effect = FinanceC1Error("down")
        result = agg.aggregate_cost_center_payroll(
            db_session, cost_center_id=cc.id, period="2026-04"
        )
    snap = result.snapshot
    assert snap.headcount == 0
    assert snap.data_source == "finance_payroll_fallback"
    assert snap.data_quality == "red"
    assert any("unavailable" in w for w in (snap.warnings or []))


def test_aggregate_single_cc_no_finance_data_for_period(db_session):
    cc = _seed_cc(db_session, code="CC_Y", name="Y", department_mapping=["缝纫一组"])
    with patch(
        "src.planner.services.cost_center_aggregator_service.get_finance_c1_client"
    ) as mock_client:
        client = mock_client.return_value
        client.list_companies.return_value = _companies_envelope()
        client.list_payroll.return_value = _fake_envelope([])  # 0 rows
        result = agg.aggregate_cost_center_payroll(
            db_session, cost_center_id=cc.id, period="2026-04"
        )
    snap = result.snapshot
    assert snap.headcount == 0
    assert snap.data_source == "finance_payroll_fallback"
    assert any("no_finance_data_for_period" in w for w in (snap.warnings or []))


def test_aggregate_uses_legacy_keywords_when_mapping_empty(db_session):
    cc = ccs.create_cost_center(
        db_session,
        payload={
            "code": "CC_Z",
            "name": "Z",
            "type": "production",
            "metadata": {"legacy_team_keywords": ["缝纫"], "finance_department_mapping": []},
        },
        actor="test",
    )
    with patch(
        "src.planner.services.cost_center_aggregator_service.get_finance_c1_client"
    ) as mock_client:
        client = mock_client.return_value
        client.list_companies.return_value = _companies_envelope()
        client.list_payroll.return_value = _fake_envelope(
            [_payroll_row(employee_id="e1", department="缝纫一组", actual_paid=5000)]
        )
        result = agg.aggregate_cost_center_payroll(
            db_session, cost_center_id=cc.id, period="2026-04"
        )
    assert result.snapshot.headcount == 1
    assert any("legacy_team_keywords" in w for w in (result.snapshot.warnings or []))


def test_aggregate_idempotent_on_rerun(db_session):
    cc = _seed_cc(
        db_session, code="CC_IDEM", name="Idem", department_mapping=["缝纫一组"]
    )
    with patch(
        "src.planner.services.cost_center_aggregator_service.get_finance_c1_client"
    ) as mock_client:
        client = mock_client.return_value
        client.list_companies.return_value = _companies_envelope()
        client.list_payroll.return_value = _fake_envelope(
            [_payroll_row(employee_id="e1", department="缝纫一组", actual_paid=5000)]
        )
        agg.aggregate_cost_center_payroll(
            db_session, cost_center_id=cc.id, period="2026-04"
        )
        # second run → still one snapshot, not two
        agg.aggregate_cost_center_payroll(
            db_session, cost_center_id=cc.id, period="2026-04"
        )
    rows = (
        db_session.query(models.CostCenterPayrollSnapshot)
        .filter(models.CostCenterPayrollSnapshot.cost_center_id == cc.id)
        .all()
    )
    assert len(rows) == 1


# ---------------------------------------------------------------------------
# Hub upsert: labor_per_minute scope_type=cost_center row
# ---------------------------------------------------------------------------


def test_aggregate_upserts_labor_per_minute_when_minutes_present(db_session):
    cc = _seed_cc(
        db_session,
        code="CC_LM",
        name="LM",
        department_mapping=["缝纫一组"],
    )
    # Wire process minutes via ModelVersionProcess.metadata_json.process_minutes
    proc = models.Process(
        process_code="P_LM_1",
        process_name="LM proc",
        charging_mode="time",
        cost_center_id=cc.id,
    )
    db_session.add(proc)
    db_session.flush()
    model = models.ProductModel(model_code="M_LM_1", model_name="M", calc_mode="ratio")
    db_session.add(model)
    db_session.flush()
    ver = models.ProductModelVersion(model_id=model.id, version_kind="standard")
    db_session.add(ver)
    db_session.flush()
    mvp = models.ModelVersionProcess(
        version_id=ver.id,
        process_id=proc.id,
        sequence_order=1,
        metadata_json={"process_minutes": 1000.0},  # → 5000/1000 = 5 ¥/min
    )
    db_session.add(mvp)
    db_session.commit()

    with patch(
        "src.planner.services.cost_center_aggregator_service.get_finance_c1_client"
    ) as mock_client:
        client = mock_client.return_value
        client.list_companies.return_value = _companies_envelope()
        client.list_payroll.return_value = _fake_envelope(
            [_payroll_row(employee_id="e1", department="缝纫一组", actual_paid=5000)]
        )
        result = agg.aggregate_cost_center_payroll(
            db_session, cost_center_id=cc.id, period="2026-04"
        )
    assert result.upserted_rate_rows == 1
    assert result.snapshot.rate_per_minute is not None
    # cost_rate_master should now have a scope_type=cost_center labor_per_minute row
    rows = ltss.list_strategies(db_session, rate_type="labor_per_minute")
    matches = [r for r in rows if r.scope_type == "cost_center" and r.scope_id == cc.id]
    assert len(matches) == 1
    assert matches[0].source == "auto_aggregated_from_finance"
    assert matches[0].data_quality == "yellow"


def test_aggregate_skips_rate_upsert_when_no_minutes(db_session):
    cc = _seed_cc(
        db_session, code="CC_NOMIN", name="NoMin", department_mapping=["缝纫一组"]
    )
    with patch(
        "src.planner.services.cost_center_aggregator_service.get_finance_c1_client"
    ) as mock_client:
        client = mock_client.return_value
        client.list_companies.return_value = _companies_envelope()
        client.list_payroll.return_value = _fake_envelope(
            [_payroll_row(employee_id="e1", department="缝纫一组", actual_paid=5000)]
        )
        result = agg.aggregate_cost_center_payroll(
            db_session, cost_center_id=cc.id, period="2026-04"
        )
    assert result.upserted_rate_rows == 0
    rows = ltss.list_strategies(db_session, rate_type="labor_per_minute")
    matches = [r for r in rows if r.scope_id == cc.id]
    assert matches == []


# ---------------------------------------------------------------------------
# Batch
# ---------------------------------------------------------------------------


def test_aggregate_all_cost_centers_produces_one_snapshot_each(db_session):
    centers = [
        _seed_cc(db_session, code=f"CC_BATCH_{i}", name=f"B{i}", department_mapping=["缝纫一组"])
        for i in range(3)
    ]

    with patch(
        "src.planner.services.cost_center_aggregator_service.get_finance_c1_client"
    ) as mock_client:
        client = mock_client.return_value
        client.list_companies.return_value = _companies_envelope()
        client.list_payroll.return_value = _fake_envelope(
            [_payroll_row(employee_id="e1", department="缝纫一组", actual_paid=5000)]
        )
        result = agg.aggregate_all_cost_centers(db_session, period="2026-04")
    assert len(result.snapshots) == 3
    assert result.data_source == "finance_payroll"


def test_aggregate_period_validation():
    """period must be YYYY-MM format."""

    with pytest.raises(ValueError, match="must be YYYY-MM"):
        agg._parse_period("2026/04")
    with pytest.raises(ValueError, match="must be YYYY-MM"):
        agg._parse_period("202604")


def test_list_snapshots_filter_by_period_range(db_session):
    cc = _seed_cc(
        db_session, code="CC_LIST", name="L", department_mapping=["缝纫一组"]
    )
    for period in ("2026-02", "2026-03", "2026-04"):
        with patch(
            "src.planner.services.cost_center_aggregator_service.get_finance_c1_client"
        ) as mock_client:
            client = mock_client.return_value
            client.list_companies.return_value = _companies_envelope()
            client.list_payroll.return_value = _fake_envelope(
                [_payroll_row(employee_id="e", department="缝纫一组", actual_paid=5000)]
            )
            agg.aggregate_cost_center_payroll(
                db_session, cost_center_id=cc.id, period=period
            )
    rows = agg.list_snapshots(
        db_session, cost_center_id=cc.id, since="2026-03", until="2026-04"
    )
    assert {r.period for r in rows} == {"2026-03", "2026-04"}


def test_aggregate_unknown_cc_raises(db_session):
    with pytest.raises(ValueError, match="cost_center not found"):
        agg.aggregate_cost_center_payroll(
            db_session, cost_center_id="nonexistent", period="2026-04"
        )
