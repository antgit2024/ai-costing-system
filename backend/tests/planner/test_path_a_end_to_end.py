"""End-to-end tests for Path A — the full A1→A2→A3→A4 pipeline + Hub
resolve at the cost_center layer (验收标准 §4)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List
from unittest.mock import patch

import pytest

from src.planner import models
from src.planner.services import (
    bom_generation_service,
    cost_allocator_service as alloc,
    cost_center_aggregator_service as agg,
    cost_center_service as ccs,
    fixed_cost_amortizer_service as amort,
    long_tail_strategy_service as ltss,
)


def _fake_envelope(rows, source="mock"):
    class _Env:
        def __init__(self, data, src):
            self.data = data
            self.data_source = src

    return _Env(rows, source)


def test_kb8_overhead_resolves_at_cost_center_layer_when_no_model_or_category(db_session):
    """The brief's 验收 §4: After A4 wires cost_center overhead, BOM
    resolver hits the cost_center layer when there's no model-level row.
    """

    cc = ccs.create_cost_center(
        db_session,
        payload={
            "code": "CC_KB8",
            "name": "KB8 班组",
            "type": "production",
            "metadata": {"finance_department_mapping": ["KB8 班组"]},
        },
        actor="test",
    )
    proc = models.Process(
        process_code="P_KB8",
        process_name="KB8 工序",
        charging_mode="time",
        cost_center_id=cc.id,
    )
    db_session.add(proc)
    db_session.flush()
    model = models.ProductModel(
        model_code="M_KB8", model_name="KB8 model", calc_mode="ratio", category="布艺"
    )
    db_session.add(model)
    db_session.flush()
    ver = models.ProductModelVersion(
        model_id=model.id, version_kind="standard", version_status="published"
    )
    db_session.add(ver)
    db_session.flush()
    mvp = models.ModelVersionProcess(
        version_id=ver.id, process_id=proc.id, sequence_order=1, metadata_json={}
    )
    db_session.add(mvp)
    db_session.commit()

    # Manually upsert a cost_center-layer overhead_rate (simulating A4's output).
    ltss.create_strategy(
        db_session,
        payload={
            "rate_type": "overhead_rate",
            "scope_type": "cost_center",
            "scope_id": cc.id,
            "rate": 0.247,
            "rate_basis": "pct_of_cost",
            "source": "auto_allocated_from_finance",
            "data_quality": "yellow",
        },
        actor="test",
    )

    # Resolve via bom_generation_service: should hit cost_center layer.
    rate = bom_generation_service._resolve_overhead_rate(
        db_session, model_version_processes=[mvp]
    )
    assert rate == Decimal("0.247")


def test_kb8_model_layer_still_overrides_cost_center(db_session):
    """Backwards compatibility: when a model-level overhead row exists,
    it still wins over the cost_center layer."""

    cc = ccs.create_cost_center(
        db_session, payload={"code": "CC_M_OVR", "name": "M_OVR", "type": "production"}, actor="t"
    )
    proc = models.Process(
        process_code="P_M_OVR",
        process_name="P",
        charging_mode="time",
        cost_center_id=cc.id,
    )
    db_session.add(proc)
    db_session.flush()
    model = models.ProductModel(
        model_code="M_OVR", model_name="M", calc_mode="ratio", category="布艺"
    )
    db_session.add(model)
    db_session.flush()
    ver = models.ProductModelVersion(model_id=model.id, version_kind="standard")
    db_session.add(ver)
    db_session.flush()
    mvp = models.ModelVersionProcess(
        version_id=ver.id, process_id=proc.id, sequence_order=1, metadata_json={}
    )
    db_session.add(mvp)
    db_session.commit()

    # Both layers configured: model 0.25 and cost_center 0.40.
    ltss.create_strategy(
        db_session,
        payload={
            "rate_type": "overhead_rate",
            "scope_type": "model",
            "scope_id": model.id,
            "rate": 0.25,
        },
    )
    ltss.create_strategy(
        db_session,
        payload={
            "rate_type": "overhead_rate",
            "scope_type": "cost_center",
            "scope_id": cc.id,
            "rate": 0.40,
        },
    )
    rate = bom_generation_service._resolve_overhead_rate(
        db_session, model_version_processes=[mvp]
    )
    assert rate == Decimal("0.25")  # model layer wins


def test_kb8_falls_back_to_global_when_cc_id_unknown(db_session):
    """Process with NULL cost_center_id (legacy data) → resolver still
    returns global layer if one exists, NOT hard_fallback."""

    proc = models.Process(
        process_code="P_NO_CC",
        process_name="P",
        charging_mode="time",
        cost_center_id=None,
    )
    db_session.add(proc)
    db_session.flush()
    model = models.ProductModel(
        model_code="M_NO_CC", model_name="M", calc_mode="ratio", category="X"
    )
    db_session.add(model)
    db_session.flush()
    ver = models.ProductModelVersion(model_id=model.id, version_kind="standard")
    db_session.add(ver)
    db_session.flush()
    mvp = models.ModelVersionProcess(
        version_id=ver.id, process_id=proc.id, sequence_order=1, metadata_json={}
    )
    db_session.add(mvp)
    ltss.create_strategy(
        db_session,
        payload={
            "rate_type": "overhead_rate",
            "scope_type": "global",
            "rate": 0.30,
        },
    )
    db_session.commit()
    rate = bom_generation_service._resolve_overhead_rate(
        db_session, model_version_processes=[mvp]
    )
    assert rate == Decimal("0.30")


def test_full_pipeline_a2_a3_a4_writes_all_artifacts(db_session):
    """Full pipeline smoke: aggregator → amortizer → allocator → Hub
    overhead_rate row at cost_center scope. Uses mocks for finance.
    """

    cc1 = ccs.create_cost_center(
        db_session,
        payload={
            "code": "CC_E2E_1",
            "name": "缝纫一组",
            "type": "production",
            "metadata": {"finance_department_mapping": ["缝纫一组"]},
        },
    )
    cc2 = ccs.create_cost_center(
        db_session,
        payload={
            "code": "CC_E2E_2",
            "name": "缝纫二组",
            "type": "production",
            "metadata": {"finance_department_mapping": ["缝纫二组"]},
        },
    )

    period = "2026-04"
    payroll_rows = [
        {
            "employee_id": "e1",
            "name_masked": "X",
            "company_id": "co-1",
            "department_raw": "缝纫一组",
            "period_year": 2026,
            "period_month": 4,
            "gross_salary": 5500,
            "employer_insurance": 1100,
            "total_labor_cost": 6600,
            "metadata": {"actual_paid": 5000},
        },
        {
            "employee_id": "e2",
            "name_masked": "Y",
            "company_id": "co-1",
            "department_raw": "缝纫二组",
            "period_year": 2026,
            "period_month": 4,
            "gross_salary": 5500,
            "employer_insurance": 1100,
            "total_labor_cost": 6600,
            "metadata": {"actual_paid": 4500},
        },
    ]
    payment_rows = [
        {
            "id": "pr-rent",
            "payment_date": "2026-04-05",
            "belong_month": "202604",
            "amount": 9000.0,
            "company_name": "Demo",
            "company_id": "co-1",
            "pay_company": "co-1",
            "store_department": "厂部",
            "primary_subject": "管理费用",
            "secondary_subject": "房租",
            "expense_category": "admin",
            "is_monthly_amortized": False,
            "amort_months": None,
            "amort_start_period": None,
            "amort_end_period": None,
            "amort_monthly_amount": None,
            "match_status": "full",
            "matched_amount": 9000.0,
            "invoice_status": "已回票",
            "invoice_gap": 0.0,
            "metadata": {},
        }
    ]
    company_rows = [
        {
            "id": "co-1",
            "legal_name": "工厂 1",
            "tax_payer_type": "general",
            "entity_role": "factory",
            "is_active": True,
            "payroll_recognition": True,
            "fixed_cost_recognition": True,
            "material_purchase_recognition": True,
            "revenue_recognition": False,
            "floor_area_sqm": 1000.0,
        }
    ]

    with patch(
        "src.planner.services.cost_center_aggregator_service.get_finance_c1_client"
    ) as agg_client, patch(
        "src.planner.services.fixed_cost_amortizer_service.get_finance_c1_client"
    ) as am_client, patch(
        "src.planner.services.cost_allocator_service.get_finance_c1_client"
    ) as al_client, patch(
        "src.planner.services.cost_center_service.get_finance_c1_client"
    ) as cc_client:
        for m in (agg_client, am_client, al_client, cc_client):
            m.return_value.list_companies.return_value = _fake_envelope(company_rows)
            m.return_value.list_employees.return_value = _fake_envelope([])
            m.return_value.list_stores_revenue.return_value = _fake_envelope([])
        for m in (agg_client,):
            m.return_value.list_payroll.return_value = _fake_envelope(payroll_rows)
        for m in (am_client,):
            m.return_value.list_payment_requests.return_value = _fake_envelope(
                payment_rows
            )

        # A2: aggregate payroll for both cost_centers.
        batch = agg.aggregate_all_cost_centers(db_session, period=period)
        assert len(batch.snapshots) == 2

        # A3: amortize the rent line.
        amort_result = amort.amortize_fixed_costs_for_period(db_session, period=period)
        assert amort_result.lines_written == 1

        # A4: allocate to cost_centers + upsert overhead_rate.
        alloc_result = alloc.allocate_fixed_costs_to_cost_centers(
            db_session, period=period
        )
        # Both cost_centers should receive a slice of the 9000 admin cost
        # (floor_area total = 1000 split 500/500 → equal split here too).
        assert alloc_result.lines_written == 2

    # Hub now has labor_per_minute (skipped — no minutes in this test) and
    # overhead_rate rows for both cost_centers.
    overhead_rows = [
        r
        for r in ltss.list_strategies(db_session, rate_type="overhead_rate")
        if r.scope_type == "cost_center"
    ]
    assert {r.scope_id for r in overhead_rows} == {cc1.id, cc2.id}
    # Each cc got 4500 allocated. With total_paid 5000 / 4500 = 0.9
    # for cc1 (which got actual_paid=5000) and 4500/4500 = 1.0 for cc2.
    by_scope = {r.scope_id: float(r.rate) for r in overhead_rows}
    assert by_scope[cc1.id] == pytest.approx(0.9, abs=0.01)
    assert by_scope[cc2.id] == pytest.approx(1.0, abs=0.01)
