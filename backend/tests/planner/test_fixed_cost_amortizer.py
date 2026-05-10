"""Tests for fixed_cost_amortizer_service (Path A §A3)."""

from __future__ import annotations

from typing import Any, Dict, List
from unittest.mock import patch

import pytest

from src.planner import models
from src.planner.services import fixed_cost_amortizer_service as amort
from src.planner.services.finance_c1_client import FinanceC1Error


def _fake_envelope(rows, source="mock"):
    class _Env:
        def __init__(self, data, src):
            self.data = data
            self.data_source = src

    return _Env(rows, source)


def _pr(
    *,
    pid: str,
    category: str,
    amount: float,
    company_id: str = "co-bene",
    pay_company: str | None = "co-pay",
    is_amort: bool = False,
    months: int | None = None,
    start: str | None = None,
    end: str | None = None,
    monthly: float | None = None,
    belong: str = "202604",
) -> Dict[str, Any]:
    return {
        "id": pid,
        "payment_date": "2026-04-15",
        "belong_month": belong,
        "amount": amount,
        "company_name": "Demo Co",
        "company_id": company_id,
        "pay_company": pay_company,
        "store_department": "demo",
        "primary_subject": "管理费用",
        "secondary_subject": "X",
        "expense_category": category,
        "is_monthly_amortized": is_amort,
        "amort_months": months,
        "amort_start_period": start,
        "amort_end_period": end,
        "amort_monthly_amount": monthly,
        "reason": None,
        "notes": None,
        "match_status": "full",
        "matched_amount": amount,
        "invoice_status": "已回票",
        "invoice_gap": 0.0,
        "metadata": {},
    }


def _client_returns(rows):
    """Helper: patch get_finance_c1_client to return a mock with these rows."""

    return patch(
        "src.planner.services.fixed_cost_amortizer_service.get_finance_c1_client"
    )


# ---------------------------------------------------------------------------
# Happy path: 6 expense categories, 1 row each
# ---------------------------------------------------------------------------


def test_amortize_writes_one_line_per_one_shot_row(db_session):
    rows = [
        _pr(pid="p-cogs", category="cogs", amount=58000),
        _pr(pid="p-sell", category="selling", amount=26000),
        _pr(pid="p-admin", category="admin", amount=35000),
        _pr(pid="p-fin", category="financial", amount=1200),
        _pr(pid="p-cap", category="capital_recovery", amount=10000),
        _pr(pid="p-rech", category="platform_recharge", amount=8000),
    ]
    with _client_returns(rows) as mock_client:
        mock_client.return_value.list_payment_requests.return_value = _fake_envelope(rows)
        result = amort.amortize_fixed_costs_for_period(db_session, period="2026-04")
    assert result.lines_written == 6
    assert result.total_amount == 138200.0
    assert "cogs" in result.by_category
    assert "platform_recharge" in result.by_category
    cats_in_db = {
        r.expense_category
        for r in db_session.query(models.FixedCostAmortizationLine).all()
    }
    assert cats_in_db == {"cogs", "selling", "admin", "financial", "capital_recovery", "platform_recharge"}


def test_amortize_expands_amort_monthly_amount(db_session):
    rows = [
        _pr(
            pid="p-amort-1",
            category="admin",
            amount=12000,
            is_amort=True,
            months=12,
            start="202601",
            end="202612",
            monthly=1000.0,
            belong="202601",
        ),
    ]
    with _client_returns(rows) as mock_client:
        mock_client.return_value.list_payment_requests.return_value = _fake_envelope(rows)
        result = amort.amortize_fixed_costs_for_period(db_session, period="2026-04")
    assert result.lines_written == 1
    line = db_session.query(models.FixedCostAmortizationLine).first()
    assert float(line.amount_amortized) == 1000.0
    assert line.is_monthly_amortized is True


def test_amortize_falls_back_to_amount_div_months_when_monthly_missing(db_session):
    rows = [
        _pr(
            pid="p-fb",
            category="capital_recovery",
            amount=24000,
            is_amort=True,
            months=24,
            start="202603",
            end="202802",
            monthly=None,
            belong="202603",
        ),
    ]
    with _client_returns(rows) as mock_client:
        mock_client.return_value.list_payment_requests.return_value = _fake_envelope(rows)
        result = amort.amortize_fixed_costs_for_period(db_session, period="2026-04")
    line = db_session.query(models.FixedCostAmortizationLine).first()
    assert float(line.amount_amortized) == 1000.0
    assert any("amort_monthly_amount missing" in w for w in result.warnings)


def test_amortize_skips_one_shot_outside_period(db_session):
    rows = [
        _pr(pid="p-out", category="cogs", amount=5000, is_amort=False, belong="202603"),
        _pr(pid="p-in", category="cogs", amount=5000, is_amort=False, belong="202604"),
    ]
    with _client_returns(rows) as mock_client:
        mock_client.return_value.list_payment_requests.return_value = _fake_envelope(rows)
        result = amort.amortize_fixed_costs_for_period(db_session, period="2026-04")
    assert result.lines_written == 1
    line = db_session.query(models.FixedCostAmortizationLine).first()
    assert line.payment_request_id == "p-in"


def test_amortize_skips_amortized_outside_window(db_session):
    rows = [
        _pr(
            pid="p-window-mismatch",
            category="capital_recovery",
            amount=24000,
            is_amort=True,
            months=24,
            start="202501",
            end="202512",  # ends 2025-12, our period is 2026-04
            monthly=1000.0,
        ),
    ]
    with _client_returns(rows) as mock_client:
        mock_client.return_value.list_payment_requests.return_value = _fake_envelope(rows)
        result = amort.amortize_fixed_costs_for_period(db_session, period="2026-04")
    assert result.lines_written == 0


def test_amortize_pay_company_neq_company_name_records_both(db_session):
    """A 主体付钱、B 主体受益 — 我们按 B(beneficiary)归集 + 把 payer 也存下来便于审计。"""

    rows = [
        _pr(
            pid="p-cross",
            category="cogs",
            amount=12000,
            company_id="co-B-beneficiary",
            pay_company="co-A-payer",
        ),
    ]
    with _client_returns(rows) as mock_client:
        mock_client.return_value.list_payment_requests.return_value = _fake_envelope(rows)
        result = amort.amortize_fixed_costs_for_period(db_session, period="2026-04")
    line = db_session.query(models.FixedCostAmortizationLine).first()
    assert line.beneficiary_company_id == "co-B-beneficiary"
    assert line.payer_company_id == "co-A-payer"
    # by_company aggregation uses beneficiary
    assert "co-B-beneficiary" in result.by_company
    assert "co-A-payer" not in result.by_company


def test_amortize_idempotent_rerun_replaces_lines(db_session):
    rows1 = [_pr(pid="p1", category="cogs", amount=5000)]
    rows2 = [_pr(pid="p2", category="cogs", amount=8000)]  # different rows

    with _client_returns(rows1) as mock_client:
        mock_client.return_value.list_payment_requests.return_value = _fake_envelope(rows1)
        amort.amortize_fixed_costs_for_period(db_session, period="2026-04")
    with _client_returns(rows2) as mock_client:
        mock_client.return_value.list_payment_requests.return_value = _fake_envelope(rows2)
        amort.amortize_fixed_costs_for_period(db_session, period="2026-04")
    rows = db_session.query(models.FixedCostAmortizationLine).all()
    assert len(rows) == 1
    assert rows[0].payment_request_id == "p2"


def test_amortize_finance_unavailable_writes_no_lines(db_session):
    with _client_returns([]) as mock_client:
        mock_client.return_value.list_payment_requests.side_effect = FinanceC1Error("down")
        result = amort.amortize_fixed_costs_for_period(db_session, period="2026-04")
    assert result.lines_written == 0
    assert result.data_source == "unavailable"
    assert any("unavailable" in w for w in result.warnings)


def test_amortize_period_validation():
    with pytest.raises(ValueError, match="must be YYYY-MM"):
        amort.amortize_fixed_costs_for_period(None, period="2026/04")  # type: ignore[arg-type]


def test_aggregate_by_category_returns_buckets(db_session):
    rows = [
        _pr(pid="p1", category="cogs", amount=5000, company_id="co-A"),
        _pr(pid="p2", category="cogs", amount=3000, company_id="co-B"),
        _pr(pid="p3", category="admin", amount=8000, company_id="co-A"),
    ]
    with _client_returns(rows) as mock_client:
        mock_client.return_value.list_payment_requests.return_value = _fake_envelope(rows)
        amort.amortize_fixed_costs_for_period(db_session, period="2026-04")
    out = amort.aggregate_by_category(db_session, period="2026-04")
    cats = {item["category"]: item for item in out["items"]}
    assert cats["cogs"]["total"] == 8000.0
    assert cats["admin"]["total"] == 8000.0
    assert out["total"] == 16000.0


def test_aggregate_by_company_returns_buckets(db_session):
    rows = [
        _pr(pid="p1", category="cogs", amount=5000, company_id="co-A"),
        _pr(pid="p2", category="admin", amount=3000, company_id="co-A"),
        _pr(pid="p3", category="cogs", amount=2000, company_id="co-B"),
    ]
    with _client_returns(rows) as mock_client:
        mock_client.return_value.list_payment_requests.return_value = _fake_envelope(rows)
        amort.amortize_fixed_costs_for_period(db_session, period="2026-04")
    out = amort.aggregate_by_company(db_session, period="2026-04")
    by_id = {item["company_id"]: item for item in out["items"]}
    assert by_id["co-A"]["total"] == 8000.0
    assert by_id["co-B"]["total"] == 2000.0


def test_amortize_no_data_writes_warning(db_session):
    with _client_returns([]) as mock_client:
        mock_client.return_value.list_payment_requests.return_value = _fake_envelope([])
        result = amort.amortize_fixed_costs_for_period(db_session, period="2026-04")
    assert result.lines_written == 0
    assert any("no_payment_requests_covering_period" in w for w in result.warnings)
