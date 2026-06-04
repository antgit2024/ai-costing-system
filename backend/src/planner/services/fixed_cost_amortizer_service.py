"""Fixed cost amortizer service (Path A §A3).

Purpose
-------
Pull finance C1 ``payment_requests`` for the given period
(``amort_covers_period`` filter on finance side), expand multi-month
amortizations to their monthly slice, and persist into
``fixed_cost_amortization_line``. Output feeds A4
``cost_allocator_service``.

Period semantics
----------------
- ``period`` is YYYY-MM (e.g. '2026-04').
- We pass ``amort_covers_period='YYYYMM'`` to finance so it returns
  ALL payment_requests whose ``amort_start_period <= P <=
  amort_end_period`` regardless of pay date — finance does the
  filtering.
- For one-shot (non-amortized) payment_requests, finance also returns
  rows whose ``belong_month=YYYYMM`` (one-shot rows have NULL
  amort_*_period; finance includes them when ``amort_covers_period``
  matches their ``belong_month``).
- For each row:
  - ``is_monthly_amortized=True``: write ``amort_monthly_amount``
  - ``is_monthly_amortized=False``: write ``amount`` (one-shot)

We persist *every* line including platform_recharge / capital_recovery
so the Hub日志 Tab can show the full picture; the A4 cost_allocator
later decides which categories actually get allocated to cost_centers.

Beneficiary vs payer
--------------------
- ``beneficiary_company_id`` = finance ``company_id`` (受益主体)
- ``payer_company_id``       = finance ``pay_company`` (实际付款主体,
  nullable; A 付 B 受益场景下 != company_id)

A4 always uses *beneficiary* for downstream allocation.

Robustness
----------
- finance unavailable → no lines written, return empty result with
  warning + ``data_source='unavailable'``
- finance returns 0 rows → 0 lines written + warning, but no error
- amort_monthly_amount missing on amortized row → fall back to
  ``amount / amort_months`` (computed locally) + warning
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from .. import models
from .finance_c1_client import FinanceC1Error, get_finance_c1_client


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _s(v: Any) -> str:
    return str(v if v is not None else "").strip()


def _parse_period(period: str) -> Tuple[int, int]:
    period_clean = _s(period)
    if len(period_clean) != 7 or period_clean[4] != "-":
        raise ValueError(f"period must be YYYY-MM (got {period!r})")
    year = int(period_clean[:4])
    month = int(period_clean[5:7])
    if not (2000 <= year <= 2100 and 1 <= month <= 12):
        raise ValueError(f"period out of range: {period!r}")
    return year, month


def _period_to_yyyymm(period: str) -> str:
    """Convert 'YYYY-MM' → 'YYYYMM' (finance API form)."""

    year, month = _parse_period(period)
    return f"{year:04d}{month:02d}"


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class FixedCostAmortizeResult:
    period: str
    lines_written: int = 0
    total_amount: float = 0.0
    by_category: Dict[str, float] = field(default_factory=dict)
    by_company: Dict[str, float] = field(default_factory=dict)
    data_source: str = "live"
    warnings: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Core amortization
# ---------------------------------------------------------------------------


def _decimal(v: Any, default: Decimal = Decimal("0")) -> Decimal:
    try:
        if v in (None, ""):
            return default
        return Decimal(str(v))
    except Exception:  # noqa: BLE001
        return default


def _line_amount_for_period(
    row: Dict[str, Any], yyyymm: str, warnings: List[str]
) -> Optional[Decimal]:
    """Compute the amount this payment_request contributes to ``yyyymm``.

    Returns None if the row doesn't apply to this period (finance might
    have given us extra rows in some edge case; we double-check
    locally).
    """

    is_amort = bool(row.get("is_monthly_amortized"))
    amount = _decimal(row.get("amount"))
    if amount <= 0:
        warnings.append(
            f"payment_request[{row.get('id')}]: amount<=0, skipped"
        )
        return None

    if not is_amort:
        belong = _s(row.get("belong_month"))
        if belong and belong != yyyymm:
            return None
        return amount

    start = _s(row.get("amort_start_period"))
    end = _s(row.get("amort_end_period"))
    if not start or not end:
        warnings.append(
            f"payment_request[{row.get('id')}]: amortized but missing amort_start/end_period; skipped"
        )
        return None
    if not (start <= yyyymm <= end):
        return None

    monthly = row.get("amort_monthly_amount")
    if monthly is not None:
        v = _decimal(monthly)
        if v > 0:
            return v
    months = row.get("amort_months") or 0
    try:
        months_int = int(months)
    except (TypeError, ValueError):
        months_int = 0
    if months_int > 0:
        warnings.append(
            f"payment_request[{row.get('id')}]: amort_monthly_amount missing; computed amount/amort_months={amount}/{months_int}"
        )
        return amount / Decimal(months_int)
    warnings.append(
        f"payment_request[{row.get('id')}]: amortized but no amort_monthly_amount nor amort_months; skipped"
    )
    return None


def amortize_fixed_costs_for_period(
    db: Session, *, period: str
) -> FixedCostAmortizeResult:
    """Pull finance payment_requests covering ``period``, write per-line
    amortization rows, return aggregate stats.

    Idempotent: re-running for the same period replaces existing lines
    (UNIQUE(period, payment_request_id)).
    """

    yyyymm = _period_to_yyyymm(period)
    warnings: List[str] = []
    rows: List[Dict[str, Any]] = []
    data_source = "live"

    client = get_finance_c1_client()
    try:
        env = client.list_payment_requests(amort_covers_period=yyyymm)
        rows = list(env.data or [])
        data_source = env.data_source or "live"
    except FinanceC1Error as exc:
        warnings.append(f"finance_payment_requests_unavailable: {exc}")
        data_source = "unavailable"
        rows = []

    # Wipe existing lines for this period (idempotent re-run). We don't
    # attempt to UPSERT because amortization is fully derivable from
    # finance — re-deriving is cheap and avoids stale rows.
    db.query(models.FixedCostAmortizationLine).filter(
        models.FixedCostAmortizationLine.period == period
    ).delete(synchronize_session=False)

    lines_written = 0
    total_amount = Decimal("0")
    by_category: Dict[str, Decimal] = {}
    by_company: Dict[str, Decimal] = {}

    for row in rows:
        amount = _line_amount_for_period(row, yyyymm, warnings)
        if amount is None or amount <= 0:
            continue
        category = _s(row.get("expense_category")) or "others"
        beneficiary_company_id = _s(row.get("company_id")) or None
        payer_company_id = _s(row.get("pay_company")) or None
        # Note: finance schema's `pay_company` is a string-id (UUID)
        # in our mock; in real finance it may be either name or id.
        # We store as opaque string and let A4 join on company_id.
        line = models.FixedCostAmortizationLine(
            period=period,
            payment_request_id=_s(row.get("id")) or "unknown",
            beneficiary_company_id=beneficiary_company_id,
            payer_company_id=payer_company_id,
            expense_category=category,
            amount_amortized=amount,
            is_monthly_amortized=bool(row.get("is_monthly_amortized")),
            amort_months=row.get("amort_months"),
            amort_start_period=_s(row.get("amort_start_period")) or None,
            metadata_json={
                "company_name": _s(row.get("company_name")),
                "primary_subject": _s(row.get("primary_subject")),
                "secondary_subject": _s(row.get("secondary_subject")),
                "match_status": _s(row.get("match_status")),
                "invoice_status": _s(row.get("invoice_status")),
                "invoice_gap": row.get("invoice_gap"),
                "reason": _s(row.get("reason")),
                "notes": _s(row.get("notes")),
                "store_department": _s(row.get("store_department")),
                "amort_end_period": _s(row.get("amort_end_period")),
                "finance_data_source": data_source,
                "amortized_at": _utcnow().isoformat(),
            },
        )
        db.add(line)
        lines_written += 1
        total_amount += amount
        by_category[category] = by_category.get(category, Decimal("0")) + amount
        if beneficiary_company_id:
            by_company[beneficiary_company_id] = (
                by_company.get(beneficiary_company_id, Decimal("0")) + amount
            )

    if lines_written == 0 and not warnings:
        warnings.append(
            f"no_payment_requests_covering_period_{yyyymm}: "
            "finance returned 0 rows or all filtered out"
        )

    db.commit()
    return FixedCostAmortizeResult(
        period=period,
        lines_written=lines_written,
        total_amount=float(total_amount),
        by_category={k: float(v) for k, v in by_category.items()},
        by_company={k: float(v) for k, v in by_company.items()},
        data_source=data_source,
        warnings=warnings,
    )


def list_lines(
    db: Session,
    *,
    period: str,
    expense_category: Optional[str] = None,
) -> List[models.FixedCostAmortizationLine]:
    q = db.query(models.FixedCostAmortizationLine).filter(
        models.FixedCostAmortizationLine.period == period
    )
    if expense_category:
        q = q.filter(
            models.FixedCostAmortizationLine.expense_category == expense_category
        )
    return q.order_by(
        models.FixedCostAmortizationLine.expense_category.asc(),
        models.FixedCostAmortizationLine.amount_amortized.desc(),
    ).all()


def aggregate_by_company(db: Session, *, period: str) -> Dict[str, Any]:
    rows = list_lines(db, period=period)
    by_company: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        cid = r.beneficiary_company_id or "__unknown__"
        bucket = by_company.setdefault(
            cid,
            {
                "company_id": cid,
                "total": 0.0,
                "by_category": {},
                "company_name": (r.metadata_json or {}).get("company_name") if isinstance(r.metadata_json, dict) else None,
            },
        )
        bucket["total"] += float(r.amount_amortized or 0)
        bucket["by_category"][r.expense_category] = (
            bucket["by_category"].get(r.expense_category, 0.0)
            + float(r.amount_amortized or 0)
        )
    return {
        "period": period,
        "items": list(by_company.values()),
        "total": sum(float(r.amount_amortized or 0) for r in rows),
    }


def aggregate_by_category(db: Session, *, period: str) -> Dict[str, Any]:
    rows = list_lines(db, period=period)
    by_category: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        cat = r.expense_category
        bucket = by_category.setdefault(
            cat,
            {"category": cat, "total": 0.0, "line_count": 0, "by_company": {}},
        )
        bucket["total"] += float(r.amount_amortized or 0)
        bucket["line_count"] += 1
        cid = r.beneficiary_company_id or "__unknown__"
        bucket["by_company"][cid] = (
            bucket["by_company"].get(cid, 0.0) + float(r.amount_amortized or 0)
        )
    return {
        "period": period,
        "items": list(by_category.values()),
        "total": sum(float(r.amount_amortized or 0) for r in rows),
    }


__all__ = [
    "FixedCostAmortizeResult",
    "amortize_fixed_costs_for_period",
    "list_lines",
    "aggregate_by_company",
    "aggregate_by_category",
]
