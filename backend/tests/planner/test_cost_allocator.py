"""Tests for cost_allocator_service (Path A §A4)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List
from unittest.mock import patch

import pytest

from src.planner import models
from src.planner.services import (
    cost_allocator_service as alloc,
    cost_center_service as ccs,
    long_tail_strategy_service as ltss,
)
from src.planner.services.finance_c1_client import FinanceC1Error


def _seed_cc(db, *, code: str, name: str, type_: str = "production") -> models.CostCenter:
    return ccs.create_cost_center(
        db,
        payload={
            "code": code,
            "name": name,
            "type": type_,
            "metadata": {
                "finance_department_mapping": [name],
            },
        },
        actor="test",
    )


def _seed_amort_line(
    db,
    *,
    period: str,
    company_id: str,
    expense_category: str,
    amount: float,
    payment_request_id: str | None = None,
) -> models.FixedCostAmortizationLine:
    line = models.FixedCostAmortizationLine(
        period=period,
        payment_request_id=payment_request_id or f"pr-{company_id}-{expense_category}",
        beneficiary_company_id=company_id,
        payer_company_id=company_id,
        expense_category=expense_category,
        amount_amortized=amount,
        is_monthly_amortized=False,
        metadata_json={},
    )
    db.add(line)
    db.commit()
    return line


def _seed_payroll_snapshot(
    db, *, cost_center_id: str, period: str, total_paid: float = 10000.0
) -> models.CostCenterPayrollSnapshot:
    snap = models.CostCenterPayrollSnapshot(
        cost_center_id=cost_center_id,
        period=period,
        headcount=2,
        total_paid=total_paid,
        avg_salary=total_paid / 2,
        data_source="finance_payroll",
        data_quality="yellow",
        warnings=[],
        metadata_json={},
    )
    db.add(snap)
    db.commit()
    return snap


def _fake_envelope(rows, source="mock"):
    class _Env:
        def __init__(self, data, src):
            self.data = data
            self.data_source = src

    return _Env(rows, source)


def _patch_drivers(*, floor_areas=None, revenues=None, employees=None):
    """Single context-manager helper that mocks finance_c1_client across both
    allocator and cost_center_service."""

    floor_rows = floor_areas if floor_areas is not None else []
    revenue_rows = revenues if revenues is not None else []
    emp_rows = employees if employees is not None else []

    class _Patches:
        def __enter__(self):
            self.alloc_patch = patch(
                "src.planner.services.cost_allocator_service.get_finance_c1_client"
            )
            self.cc_patch = patch(
                "src.planner.services.cost_center_service.get_finance_c1_client"
            )
            self.alloc_mock = self.alloc_patch.start()
            self.cc_mock = self.cc_patch.start()
            for m in (self.alloc_mock, self.cc_mock):
                m.return_value.list_companies.return_value = _fake_envelope(floor_rows)
                m.return_value.list_stores_revenue.return_value = _fake_envelope(revenue_rows)
                m.return_value.list_employees.return_value = _fake_envelope(emp_rows)
            return self

        def __exit__(self, *args):
            self.cc_patch.stop()
            self.alloc_patch.stop()

    return _Patches()


# ---------------------------------------------------------------------------
# Allocation chain — happy path
# ---------------------------------------------------------------------------


def test_allocate_admin_uses_floor_area_primary(db_session):
    cc1 = _seed_cc(db_session, code="CC_A1", name="A1", type_="production")
    cc2 = _seed_cc(db_session, code="CC_A2", name="A2", type_="production")
    _seed_amort_line(
        db_session, period="2026-04", company_id="co-1", expense_category="admin", amount=10000
    )
    floor_rows = [{"id": "co-1", "floor_area_sqm": 1000.0}]
    with _patch_drivers(floor_areas=floor_rows):
        result = alloc.allocate_fixed_costs_to_cost_centers(
            db_session, period="2026-04"
        )
    assert result.lines_written == 2
    lines = db_session.query(models.CostAllocationLine).all()
    assert all(l.allocation_basis == "floor_area" for l in lines)
    # Equal split (2 cost_centers, equal floor weights)
    amounts = sorted(float(l.amount_allocated) for l in lines)
    assert amounts == [5000.0, 5000.0]


def test_allocate_selling_uses_revenue_primary(db_session):
    prod1 = _seed_cc(db_session, code="CC_P1", name="P1", type_="production")
    prod2 = _seed_cc(db_session, code="CC_P2", name="P2", type_="production")
    aux = _seed_cc(db_session, code="CC_AUX", name="AUX", type_="auxiliary")
    _seed_amort_line(
        db_session, period="2026-04", company_id="co-shop-1", expense_category="selling", amount=30000
    )
    revenue_rows = [{"company_id": "co-shop-1", "net_revenue": 100000}]
    floor_rows = [{"id": "co-shop-1", "floor_area_sqm": 200.0}]
    with _patch_drivers(floor_areas=floor_rows, revenues=revenue_rows):
        result = alloc.allocate_fixed_costs_to_cost_centers(
            db_session, period="2026-04"
        )
    lines = db_session.query(models.CostAllocationLine).all()
    # selling chain: revenue first; auxiliary cost_centers get 0 weight
    assert all(l.allocation_basis == "revenue" for l in lines)
    aux_lines = [l for l in lines if l.target_cost_center_id == aux.id]
    assert aux_lines == []  # auxiliary excluded under revenue basis
    prod_lines = sorted([float(l.amount_allocated) for l in lines if l.target_cost_center_id != aux.id])
    assert prod_lines == [15000.0, 15000.0]


def test_allocate_falls_back_to_headcount_when_no_floor(db_session):
    cc1 = _seed_cc(db_session, code="CC_FB1", name="FB1", type_="production")
    cc2 = _seed_cc(db_session, code="CC_FB2", name="FB2", type_="production")
    _seed_amort_line(
        db_session, period="2026-04", company_id="co-1", expense_category="admin", amount=4000
    )
    # No floor_area for co-1 → should fall back to headcount.
    employees = [
        {"id": "e1", "name": "E1", "department": "FB1", "is_active": True},
        {"id": "e2", "name": "E2", "department": "FB1", "is_active": True},
        {"id": "e3", "name": "E3", "department": "FB1", "is_active": True},
        {"id": "e4", "name": "E4", "department": "FB2", "is_active": True},
    ]
    with _patch_drivers(floor_areas=[], employees=employees):
        result = alloc.allocate_fixed_costs_to_cost_centers(
            db_session, period="2026-04"
        )
    lines = db_session.query(models.CostAllocationLine).all()
    assert all(l.allocation_basis == "headcount" for l in lines)
    by_cc = {l.target_cost_center_id: float(l.amount_allocated) for l in lines}
    # FB1 has 3, FB2 has 1 → 75/25 split of 4000 = 3000 / 1000
    assert by_cc[cc1.id] == 3000.0
    assert by_cc[cc2.id] == 1000.0
    # fallback_chain audit: floor_area was tried first
    assert "floor_area" in lines[0].fallback_chain


def test_allocate_falls_back_to_equal_when_all_drivers_fail(db_session):
    cc1 = _seed_cc(db_session, code="CC_EQ1", name="EQ1", type_="production")
    cc2 = _seed_cc(db_session, code="CC_EQ2", name="EQ2", type_="production")
    _seed_amort_line(
        db_session, period="2026-04", company_id="co-x", expense_category="admin", amount=2000
    )
    # No floor, no employees, no revenue → must equal-split.
    with _patch_drivers():
        result = alloc.allocate_fixed_costs_to_cost_centers(
            db_session, period="2026-04"
        )
    lines = db_session.query(models.CostAllocationLine).all()
    assert all(l.allocation_basis == "equal" for l in lines)
    amounts = sorted(float(l.amount_allocated) for l in lines)
    assert amounts == [1000.0, 1000.0]


def test_allocate_strict_mode_raises_warning_on_missing_driver(db_session):
    _seed_cc(db_session, code="CC_S1", name="S1", type_="production")
    _seed_amort_line(
        db_session, period="2026-04", company_id="co-x", expense_category="admin", amount=100
    )
    with _patch_drivers():
        result = alloc.allocate_fixed_costs_to_cost_centers(
            db_session, period="2026-04", fallback_mode="strict"
        )
    # strict mode → first basis (floor_area) raises and we record warning
    assert result.lines_written == 0
    assert any("floor_area" in w for w in result.warnings)


def test_allocate_skips_platform_recharge_category(db_session):
    _seed_cc(db_session, code="CC_PR", name="PR", type_="production")
    _seed_amort_line(
        db_session, period="2026-04", company_id="co-x", expense_category="platform_recharge", amount=8000
    )
    with _patch_drivers():
        result = alloc.allocate_fixed_costs_to_cost_centers(
            db_session, period="2026-04"
        )
    assert result.lines_written == 0


# ---------------------------------------------------------------------------
# Hub upsert: overhead_rate scope_type=cost_center
# ---------------------------------------------------------------------------


def test_allocate_upserts_overhead_rate_when_payroll_snapshot_present(db_session):
    cc1 = _seed_cc(db_session, code="CC_OR1", name="OR1", type_="production")
    cc2 = _seed_cc(db_session, code="CC_OR2", name="OR2", type_="production")
    _seed_amort_line(
        db_session, period="2026-04", company_id="co-1", expense_category="admin", amount=5000
    )
    _seed_payroll_snapshot(db_session, cost_center_id=cc1.id, period="2026-04", total_paid=20000)
    _seed_payroll_snapshot(db_session, cost_center_id=cc2.id, period="2026-04", total_paid=10000)
    floor_rows = [{"id": "co-1", "floor_area_sqm": 1000.0}]
    with _patch_drivers(floor_areas=floor_rows):
        result = alloc.allocate_fixed_costs_to_cost_centers(
            db_session, period="2026-04"
        )
    assert result.upserted_rate_rows == 2
    rows = ltss.list_strategies(db_session, rate_type="overhead_rate")
    by_scope = {r.scope_id: r for r in rows if r.scope_type == "cost_center"}
    # cc1: 2500 / 20000 = 0.125
    # cc2: 2500 / 10000 = 0.25
    assert float(by_scope[cc1.id].rate) == 0.125
    assert float(by_scope[cc2.id].rate) == 0.25
    assert by_scope[cc1.id].source == "auto_allocated_from_finance"
    assert by_scope[cc1.id].data_quality == "yellow"


def test_allocate_skips_overhead_when_no_payroll(db_session):
    cc1 = _seed_cc(db_session, code="CC_NP1", name="NP1", type_="production")
    cc2 = _seed_cc(db_session, code="CC_NP2", name="NP2", type_="production")
    _seed_amort_line(
        db_session, period="2026-04", company_id="co-1", expense_category="admin", amount=5000
    )
    floor_rows = [{"id": "co-1", "floor_area_sqm": 1000.0}]
    with _patch_drivers(floor_areas=floor_rows):
        result = alloc.allocate_fixed_costs_to_cost_centers(
            db_session, period="2026-04"
        )
    # 2 lines but 0 rate upserts (no payroll snapshot to derive denominator)
    assert result.lines_written == 2
    assert result.upserted_rate_rows == 0


def test_allocate_idempotent_rerun_replaces_lines(db_session):
    _seed_cc(db_session, code="CC_ID1", name="ID1", type_="production")
    _seed_cc(db_session, code="CC_ID2", name="ID2", type_="production")
    _seed_amort_line(
        db_session, period="2026-04", company_id="co-1", expense_category="admin", amount=1000
    )
    with _patch_drivers():
        alloc.allocate_fixed_costs_to_cost_centers(db_session, period="2026-04")
        alloc.allocate_fixed_costs_to_cost_centers(db_session, period="2026-04")
    rows = db_session.query(models.CostAllocationLine).all()
    assert len(rows) == 2  # 1 group × 2 cost_centers, even after 2 runs


def test_allocate_no_amort_lines_returns_warning(db_session):
    _seed_cc(db_session, code="CC_NL", name="NL", type_="production")
    with _patch_drivers():
        result = alloc.allocate_fixed_costs_to_cost_centers(
            db_session, period="2026-04"
        )
    assert result.lines_written == 0
    assert any("no_amortization_lines" in w for w in result.warnings)


def test_allocate_no_active_cost_centers_returns_warning(db_session):
    _seed_amort_line(
        db_session, period="2026-04", company_id="co-x", expense_category="admin", amount=100
    )
    with _patch_drivers():
        result = alloc.allocate_fixed_costs_to_cost_centers(
            db_session, period="2026-04"
        )
    assert any("no_active_cost_centers" in w for w in result.warnings)


def test_aggregate_by_cost_center_returns_buckets(db_session):
    cc1 = _seed_cc(db_session, code="CC_B1", name="B1", type_="production")
    cc2 = _seed_cc(db_session, code="CC_B2", name="B2", type_="production")
    _seed_amort_line(
        db_session, period="2026-04", company_id="co-x", expense_category="admin", amount=2000
    )
    _seed_amort_line(
        db_session,
        period="2026-04",
        company_id="co-x",
        expense_category="cogs",
        amount=1000,
        payment_request_id="pr-cogs-1",
    )
    employees = [
        {"id": "e1", "name": "E1", "department": "B1", "is_active": True},
        {"id": "e2", "name": "E2", "department": "B2", "is_active": True},
    ]
    with _patch_drivers(employees=employees):
        alloc.allocate_fixed_costs_to_cost_centers(db_session, period="2026-04")
    out = alloc.aggregate_by_cost_center(db_session, period="2026-04")
    by_cc = {item["cost_center_id"]: item for item in out["items"]}
    assert by_cc[cc1.id]["total"] == 1500.0  # half of 2000+1000
    assert by_cc[cc2.id]["total"] == 1500.0


def test_allocate_invalid_fallback_mode_raises():
    with pytest.raises(ValueError, match="fallback_mode"):
        alloc.allocate_fixed_costs_to_cost_centers(
            None, period="2026-04", fallback_mode="bogus"  # type: ignore[arg-type]
        )
