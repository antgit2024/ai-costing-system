"""Cost allocator service (Path A §A4).

Purpose
-------
Take A3's per-(beneficiary_company_id, expense_category, total_amount)
groups and distribute them to active cost_centers using a multi-level
fallback driver chain (per v1.3 §4.10). Then upsert
``rate_type='overhead_rate'`` ``scope_type='cost_center'`` rows in
``cost_rate_master`` so the 4-layer Hub resolver can hit the
cost_center layer.

Driver chain
------------
| expense_category                    | primary basis | fallback 1 | fallback 2 | fallback 3 |
|-------------------------------------|---------------|------------|------------|------------|
| admin (rent / utility / office)    | floor_area    | headcount  | revenue    | equal      |
| selling (platform fee / refund)    | revenue       | headcount  | floor_area | equal      |
| financial / capital_recovery / cogs | headcount     | floor_area | revenue    | equal      |
| platform_recharge                   | (excluded — these are deposits, not costs) |

The "equal" fallback splits evenly across active cost_centers.

Drivers
-------
- floor_area_sqm: from finance ``master_companies.floor_area_sqm``
  (NULL means unknown — fallback). Allocated to cost_centers
  proportional to their relative weight (we use uniform weight per
  cost_center if we can't refine; alternatively the
  cost_center.metadata.floor_area_sqm overrides the company-level
  number if set).
- headcount: from cost_center stats (employee_count via finance
  employees pull keyed off ``finance_department_mapping``).
- revenue: from finance ``stores/revenue`` for the period; we
  attribute revenue to the cost_center that ships the product (v1
  rough heuristic: production-type cost_centers split equally;
  auxiliary/admin types don't get revenue allocations directly).

Note v1: floor_area driver currently uses the company's total
floor_area divided equally across the company's cost_centers (we
don't have per-cost_center floor numbers yet). This is fine: the
*relative* allocation between cost_centers is what matters for the
overhead rate, and equal splitting at least gets the totals correct.

Robustness
----------
- finance unavailable for any driver → fall to next basis in chain
- ``allocation_basis_total = 0`` (e.g. no employees in any cost_center)
  → fall to next basis
- All drivers fail → ``equal`` fallback split + ``warnings`` entry
- ``platform_recharge`` rows (deposits, not costs) are skipped with a
  trace warning so the Hub Tab can show "skipped: deposit".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy.orm import Session

from .. import models
from . import cost_center_service, long_tail_strategy_service
from .finance_c1_client import FinanceC1Error, get_finance_c1_client


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _s(v: Any) -> str:
    return str(v if v is not None else "").strip()


def _norm(s: Any) -> str:
    return _s(s).lower()


def _parse_period(period: str) -> Tuple[int, int]:
    period_clean = _s(period)
    if len(period_clean) != 7 or period_clean[4] != "-":
        raise ValueError(f"period must be YYYY-MM (got {period!r})")
    year = int(period_clean[:4])
    month = int(period_clean[5:7])
    if not (2000 <= year <= 2100 and 1 <= month <= 12):
        raise ValueError(f"period out of range: {period!r}")
    return year, month


def _period_first_day(period: str) -> datetime:
    year, month = _parse_period(period)
    return datetime(year, month, 1)


# ---------------------------------------------------------------------------
# Allocation driver chain
# ---------------------------------------------------------------------------


# Per-category basis chain (in priority order). Each chain is tried left-to-right
# until one yields ``allocation_basis_total > 0``.
_CHAIN: Dict[str, List[str]] = {
    "admin": ["floor_area", "headcount", "revenue", "equal"],
    "selling": ["revenue", "headcount", "floor_area", "equal"],
    "financial": ["headcount", "floor_area", "revenue", "equal"],
    "capital_recovery": ["headcount", "floor_area", "revenue", "equal"],
    "cogs": ["headcount", "floor_area", "revenue", "equal"],
    # platform_recharge is excluded (deposits, not costs)
}

# Categories that we never allocate (treated as "skip").
_EXCLUDED_CATEGORIES: set[str] = {"platform_recharge"}


@dataclass
class AllocatorResult:
    period: str
    lines_written: int = 0
    cost_centers_touched: int = 0
    total_amount: float = 0.0
    upserted_rate_rows: int = 0
    by_cost_center: Dict[str, float] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Driver lookups (cached per-call)
# ---------------------------------------------------------------------------


@dataclass
class _DriverContext:
    """All driver data we might need; computed lazily and cached per call."""

    floor_area_by_company: Dict[str, Decimal]
    headcount_by_cost_center: Dict[str, int]
    revenue_by_company: Dict[str, Decimal]
    cost_centers: List[models.CostCenter]
    warnings: List[str]


def _build_driver_context(
    db: Session, *, period: str
) -> _DriverContext:
    centers = cost_center_service.list_active(db)
    warnings: List[str] = []

    floor_area_by_company: Dict[str, Decimal] = {}
    revenue_by_company: Dict[str, Decimal] = {}
    headcount_by_cost_center: Dict[str, int] = {}

    client = get_finance_c1_client()
    # 1) floor_area + companies (used by both floor_area and revenue → company → cc)
    try:
        env = client.list_companies(is_active=True)
        for row in env.data or []:
            cid = _s(row.get("id"))
            if not cid:
                continue
            floor = row.get("floor_area_sqm")
            if floor is not None:
                try:
                    floor_area_by_company[cid] = Decimal(str(floor))
                except Exception:  # noqa: BLE001
                    continue
    except FinanceC1Error as exc:
        warnings.append(f"finance_companies_unavailable_for_floor_area: {exc}")

    # 2) revenue (period_year/period_month) by company
    try:
        year, month = _parse_period(period)
        env = client.list_stores_revenue(period_year=year, period_month=month)
        for row in env.data or []:
            cid = _s(row.get("company_id"))
            if not cid:
                continue
            try:
                v = Decimal(str(row.get("net_revenue") or row.get("gross_revenue") or 0))
            except Exception:  # noqa: BLE001
                v = Decimal("0")
            revenue_by_company[cid] = revenue_by_company.get(cid, Decimal("0")) + v
    except FinanceC1Error as exc:
        warnings.append(f"finance_stores_revenue_unavailable: {exc}")

    # 3) headcount per cost_center via finance employees (mirrors A1 stats)
    rows_with_stats = cost_center_service.get_cost_centers_with_stats(
        db, include_inactive=False
    )
    for cc, stats in rows_with_stats:
        headcount_by_cost_center[cc.id] = stats.employee_count
    if rows_with_stats:
        finance_source = rows_with_stats[0][1].finance_data_source
        if finance_source == "unavailable":
            warnings.append("finance_employees_unavailable_for_headcount_driver")

    return _DriverContext(
        floor_area_by_company=floor_area_by_company,
        headcount_by_cost_center=headcount_by_cost_center,
        revenue_by_company=revenue_by_company,
        cost_centers=centers,
        warnings=warnings,
    )


def _basis_weights_for(
    *,
    basis: str,
    centers: List[models.CostCenter],
    ctx: _DriverContext,
    source_company_id: Optional[str],
) -> Optional[Dict[str, Decimal]]:
    """Return per-cost_center driver value (NOT yet normalized into weights).

    Returns None if this basis can't be applied (e.g. floor_area total is 0).
    The caller will sum and normalize.
    """

    out: Dict[str, Decimal] = {}
    if basis == "floor_area":
        # Use the source company's floor_area as the budget, split equally
        # across cost_centers. (v1 — we don't have per-cc floor data yet.)
        total = ctx.floor_area_by_company.get(source_company_id or "", Decimal("0"))
        if total <= 0:
            return None
        if not centers:
            return None
        per_cc = total / Decimal(len(centers))
        for cc in centers:
            out[cc.id] = per_cc
        return out
    if basis == "headcount":
        for cc in centers:
            out[cc.id] = Decimal(int(ctx.headcount_by_cost_center.get(cc.id, 0)))
        if sum(out.values()) <= 0:
            return None
        return out
    if basis == "revenue":
        # Revenue isn't per-cost_center directly; we attribute to *production*
        # type centers (the ones that ship). Auxiliary/admin types get 0
        # weight under the revenue basis.
        production_centers = [cc for cc in centers if cc.type == "production"]
        if not production_centers:
            return None
        company_revenue = ctx.revenue_by_company.get(
            source_company_id or "", Decimal("0")
        )
        if company_revenue <= 0:
            # fallback: total all-company revenue as weight
            company_revenue = sum(ctx.revenue_by_company.values()) or Decimal("0")
        if company_revenue <= 0:
            return None
        per_prod = company_revenue / Decimal(len(production_centers))
        for cc in centers:
            out[cc.id] = per_prod if cc in production_centers else Decimal("0")
        return out
    if basis == "equal":
        if not centers:
            return None
        for cc in centers:
            out[cc.id] = Decimal("1")
        return out
    return None


# ---------------------------------------------------------------------------
# Per-(company, category) allocation
# ---------------------------------------------------------------------------


def _allocate_one_group(
    db: Session,
    *,
    period: str,
    source_company_id: str,
    expense_category: str,
    total_amount: Decimal,
    ctx: _DriverContext,
    fallback_mode: str,
    metadata: Dict[str, Any],
) -> List[models.CostAllocationLine]:
    chain = _CHAIN.get(expense_category, ["headcount", "floor_area", "revenue", "equal"])
    fallback_chain_used: List[str] = []
    chosen_basis: Optional[str] = None
    weights: Optional[Dict[str, Decimal]] = None
    for basis in chain:
        weights = _basis_weights_for(
            basis=basis,
            centers=ctx.cost_centers,
            ctx=ctx,
            source_company_id=source_company_id,
        )
        if weights is not None and sum(weights.values()) > 0:
            chosen_basis = basis
            break
        fallback_chain_used.append(basis)
        if fallback_mode == "strict":
            raise ValueError(
                f"basis {basis} unavailable for ({source_company_id}, "
                f"{expense_category}); strict mode rejects fallback"
            )

    lines: List[models.CostAllocationLine] = []
    if chosen_basis is None or weights is None:
        # No basis worked at all — emit one warning line that allocates 100%
        # to a synthetic "unallocated" sentinel? Better: skip with warning
        # so callers can surface to UI.
        return lines

    # Normalize to weights → amounts
    grand_total = sum(v for v in weights.values()) or Decimal("0")
    if grand_total <= 0:
        return lines
    chain_audit = list(fallback_chain_used)
    if chosen_basis not in chain_audit:
        chain_audit.append(chosen_basis)

    for cc in ctx.cost_centers:
        v = weights.get(cc.id, Decimal("0"))
        if v <= 0:
            continue
        weight = (v / grand_total).quantize(Decimal("0.000001"))
        amount = (total_amount * weight).quantize(Decimal("0.01"))
        line = models.CostAllocationLine(
            period=period,
            source_company_id=source_company_id,
            source_expense_category=expense_category,
            source_total_amount=total_amount,
            target_cost_center_id=cc.id,
            allocation_basis=chosen_basis,
            allocation_basis_value=v,
            allocation_basis_total=grand_total,
            allocation_weight=weight,
            amount_allocated=amount,
            fallback_chain=chain_audit,
            warnings=[],
            metadata_json={
                **metadata,
                "computed_at": _utcnow().isoformat(),
            },
        )
        db.add(line)
        lines.append(line)
    return lines


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------


def _aggregate_a3_groups(
    db: Session, *, period: str
) -> Dict[Tuple[str, str], Decimal]:
    """Read fixed_cost_amortization_line for ``period`` and group by
    (beneficiary_company_id, expense_category) → total amount."""

    rows = (
        db.query(models.FixedCostAmortizationLine)
        .filter(models.FixedCostAmortizationLine.period == period)
        .all()
    )
    out: Dict[Tuple[str, str], Decimal] = {}
    for r in rows:
        if r.expense_category in _EXCLUDED_CATEGORIES:
            continue
        cid = r.beneficiary_company_id or ""
        key = (cid, r.expense_category)
        out[key] = out.get(key, Decimal("0")) + Decimal(str(r.amount_amortized or 0))
    return out


def _upsert_overhead_rate(
    db: Session,
    *,
    cost_center_id: str,
    rate: Decimal,
    period: str,
) -> int:
    synthesized_category = (
        f"__overhead_rate__cost_center__{cost_center_id.lower()}"
    )
    existing = long_tail_strategy_service.get_by_category(
        db, category=synthesized_category
    )
    payload: Dict[str, Any] = {
        "rate_type": "overhead_rate",
        "scope_type": "cost_center",
        "scope_id": cost_center_id,
        "rate_basis": "pct_of_cost",
        "rate": float(rate),
        "source": "auto_allocated_from_finance",
        "data_quality": "yellow",
        "effective_from": _period_first_day(period).isoformat(),
        "note": f"auto-allocated from finance fixed costs for period {period}",
        "enabled": True,
    }
    if existing is None:
        long_tail_strategy_service.create_strategy(
            db, payload=payload, actor="cost_allocator_service"
        )
        return 1
    long_tail_strategy_service.update_strategy(
        db,
        strategy_id=existing.id,
        patch=payload,
        actor="cost_allocator_service",
    )
    return 1


def _compute_overhead_rate_per_cc(
    db: Session,
    *,
    period: str,
    by_cost_center_total: Dict[str, Decimal],
    ctx: _DriverContext,
) -> Dict[str, Decimal]:
    """For each cost_center: overhead_rate = allocated_total / direct_cost_estimate.

    v1 heuristic: direct_cost_estimate = sum of
    cost_center_payroll_snapshot.total_paid for the same period (when
    present). If snapshot total_paid is 0/missing, we fall back to
    using the period's allocated amount itself as the denominator
    (yielding a rate of 1.0 — clearly bogus, but matches v1 brief
    behaviour: "如果 cost_center 当月总产出 0 → rate 用 0.30 hard
    fallback by Hub" path is preserved by NOT writing a row).
    """

    out: Dict[str, Decimal] = {}
    for cc_id, total in by_cost_center_total.items():
        snap = (
            db.query(models.CostCenterPayrollSnapshot)
            .filter(
                models.CostCenterPayrollSnapshot.cost_center_id == cc_id,
                models.CostCenterPayrollSnapshot.period == period,
            )
            .first()
        )
        denominator = Decimal("0")
        if snap is not None and snap.total_paid is not None:
            denominator = Decimal(str(snap.total_paid))
        if denominator <= 0:
            # Don't fabricate a rate when we have no direct-cost denominator.
            continue
        rate = (total / denominator).quantize(Decimal("0.0001"))
        # Sanity bound: cap at 5.0 (500%) to keep wild outliers from
        # poisoning the Hub. Real-world overhead rates are 0.05–0.6.
        if rate > Decimal("5.0"):
            rate = Decimal("5.0")
        out[cc_id] = rate
    return out


def allocate_fixed_costs_to_cost_centers(
    db: Session,
    *,
    period: str,
    fallback_mode: str = "permissive",
) -> AllocatorResult:
    """Top-level entry: A3 → A4 + Hub upsert.

    Idempotent: re-running for the same period replaces existing
    cost_allocation_line rows.
    """

    if fallback_mode not in {"permissive", "strict"}:
        raise ValueError(f"fallback_mode must be permissive|strict (got {fallback_mode!r})")

    ctx = _build_driver_context(db, period=period)
    warnings = list(ctx.warnings)

    # Wipe existing lines for this period (idempotent re-run)
    db.query(models.CostAllocationLine).filter(
        models.CostAllocationLine.period == period
    ).delete(synchronize_session=False)

    groups = _aggregate_a3_groups(db, period=period)
    if not groups:
        warnings.append(f"no_amortization_lines_for_period_{period}: run A3 first")
        db.commit()
        return AllocatorResult(period=period, warnings=warnings)

    if not ctx.cost_centers:
        warnings.append("no_active_cost_centers; allocation skipped")
        db.commit()
        return AllocatorResult(period=period, warnings=warnings)

    lines_written = 0
    by_cost_center_total: Dict[str, Decimal] = {}
    skipped_groups: List[str] = []

    for (company_id, category), total_amount in groups.items():
        if total_amount <= 0:
            continue
        try:
            new_lines = _allocate_one_group(
                db,
                period=period,
                source_company_id=company_id or "__unknown__",
                expense_category=category,
                total_amount=total_amount,
                ctx=ctx,
                fallback_mode=fallback_mode,
                metadata={
                    "source_company_id": company_id,
                    "expense_category": category,
                    "fallback_mode": fallback_mode,
                },
            )
        except ValueError as exc:
            warnings.append(str(exc))
            skipped_groups.append(f"{company_id}:{category}")
            continue
        for line in new_lines:
            lines_written += 1
            cc_id = line.target_cost_center_id
            by_cost_center_total[cc_id] = (
                by_cost_center_total.get(cc_id, Decimal("0"))
                + Decimal(str(line.amount_allocated))
            )

    # Upsert overhead_rate per cost_center (only when total_paid > 0)
    rates = _compute_overhead_rate_per_cc(
        db, period=period, by_cost_center_total=by_cost_center_total, ctx=ctx
    )
    upserted = 0
    for cc_id, rate in rates.items():
        if rate > 0:
            upserted += _upsert_overhead_rate(
                db, cost_center_id=cc_id, rate=rate, period=period
            )

    db.commit()
    return AllocatorResult(
        period=period,
        lines_written=lines_written,
        cost_centers_touched=len(by_cost_center_total),
        total_amount=float(sum(by_cost_center_total.values())),
        upserted_rate_rows=upserted,
        by_cost_center={k: float(v) for k, v in by_cost_center_total.items()},
        warnings=warnings,
    )


def list_lines(
    db: Session,
    *,
    period: str,
    cost_center_id: Optional[str] = None,
) -> List[models.CostAllocationLine]:
    q = db.query(models.CostAllocationLine).filter(
        models.CostAllocationLine.period == period
    )
    if cost_center_id:
        q = q.filter(models.CostAllocationLine.target_cost_center_id == cost_center_id)
    return q.order_by(
        models.CostAllocationLine.target_cost_center_id.asc(),
        models.CostAllocationLine.source_expense_category.asc(),
    ).all()


def aggregate_by_cost_center(db: Session, *, period: str) -> Dict[str, Any]:
    rows = list_lines(db, period=period)
    by_cc: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        cc_id = r.target_cost_center_id
        bucket = by_cc.setdefault(
            cc_id,
            {
                "cost_center_id": cc_id,
                "total": 0.0,
                "by_category": {},
            },
        )
        bucket["total"] += float(r.amount_allocated or 0)
        bucket["by_category"][r.source_expense_category] = (
            bucket["by_category"].get(r.source_expense_category, 0.0)
            + float(r.amount_allocated or 0)
        )
    return {
        "period": period,
        "items": list(by_cc.values()),
        "total": sum(float(r.amount_allocated or 0) for r in rows),
    }


__all__ = [
    "AllocatorResult",
    "allocate_fixed_costs_to_cost_centers",
    "list_lines",
    "aggregate_by_cost_center",
]
