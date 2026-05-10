"""Cost center payroll aggregator service (Path A §A2).

Purpose
-------
Take finance C1 ``aggregation=by_employee`` payroll data and aggregate
into per-(cost_center, period) snapshots. Then upsert a Hub
``rate_type='labor_per_minute'`` row into ``cost_rate_master`` so the
4-layer resolver can hit it on the cost_center layer.

Pipeline (per cost_center):

1. Read ``cost_center.metadata.finance_department_mapping`` →
   list of finance department strings to match.
2. For each ``master_companies.id`` we know about (pulled lazily via
   ``finance_c1_client.list_companies``), call
   ``finance_c1_client.list_payroll(company_id, year, month,
   aggregation='by_employee')``. Concatenate results.
3. Filter to employees whose ``department_raw`` matches the cost
   center's mapping (case-insensitive substring).
4. Sum: headcount, total_paid (preferring metadata.actual_paid →
   gross_salary fallback), avg_salary.
5. Compute ``total_minutes`` from
   ``shipment_costing_results.metadata.process_minutes`` joined to
   the cost_center's processes (best-effort; v1 may have this empty
   and we just skip ``rate_per_minute``).
6. Persist ``cost_center_payroll_snapshot`` (UNIQUE on
   (cost_center_id, period) → re-runnable, idempotent).
7. If ``total_minutes > 0``, upsert a ``rate_type='labor_per_minute'``
   ``scope_type='cost_center'`` ``scope_id=cost_center_id`` row in
   ``cost_rate_master`` with ``source='auto_aggregated_from_finance'``,
   ``data_quality='yellow'``.

Robustness
----------
- finance unavailable → snapshot still written with
  ``data_source='finance_payroll_fallback'`` + ``data_quality='red'``
  + a warning explaining why; ``rate_per_minute=NULL``.
- finance returns 0 rows → snapshot has headcount=0,
  data_quality='yellow', warning 'no_finance_data_for_period'; no
  rate row upserted.
- Department mapping empty → snapshot still written but with warning
  'finance_department_mapping_empty' so ops knows to populate it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from .. import models
from . import cost_center_service, long_tail_strategy_service
from .finance_c1_client import (
    FinanceC1Error,
    get_finance_c1_client,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _s(v: Any) -> str:
    return str(v if v is not None else "").strip()


def _norm(s: Any) -> str:
    return _s(s).lower()


def _parse_period(period: str) -> Tuple[int, int]:
    """Parse 'YYYY-MM' → (year, month). Raises ValueError on malformed input."""

    period_clean = _s(period)
    if len(period_clean) != 7 or period_clean[4] != "-":
        raise ValueError(f"period must be YYYY-MM (got {period!r})")
    try:
        year = int(period_clean[:4])
        month = int(period_clean[5:7])
    except ValueError as exc:
        raise ValueError(f"period must be YYYY-MM (got {period!r})") from exc
    if not (2000 <= year <= 2100 and 1 <= month <= 12):
        raise ValueError(f"period out of range: {period!r}")
    return year, month


def _period_first_day(period: str) -> datetime:
    year, month = _parse_period(period)
    return datetime(year, month, 1)


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class CostCenterPayrollAggregateResult:
    """Outcome of aggregating one cost_center for one period."""

    snapshot: models.CostCenterPayrollSnapshot
    upserted_rate_rows: int = 0
    data_source: str = "finance_payroll"  # finance_payroll|finance_payroll_fallback|manual
    warnings: List[str] = field(default_factory=list)


@dataclass
class CostCenterPayrollBatchResult:
    snapshots: List[models.CostCenterPayrollSnapshot] = field(default_factory=list)
    upserted_rate_rows: int = 0
    data_source: str = "finance_payroll"
    warnings: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Per-cost-center aggregation
# ---------------------------------------------------------------------------


def _pull_payroll_for_companies(
    *,
    company_ids: List[str],
    period_year: int,
    period_month: int,
    use_existing_warnings: List[str],
) -> Tuple[List[Dict[str, Any]], str]:
    """Pull by_employee payroll across multiple companies; aggregate.

    Returns (rows, data_source). data_source is the WORST status seen:
    if any company returns from cache → 'cache'; if all live → 'live';
    if any errors → warnings appended and we continue with what we got.
    """

    rows: List[Dict[str, Any]] = []
    sources: List[str] = []
    client = get_finance_c1_client()
    for cid in company_ids:
        if not cid:
            continue
        try:
            env = client.list_payroll(
                company_id=cid,
                period_year=period_year,
                period_month=period_month,
                aggregation="by_employee",
            )
            rows.extend(env.data or [])
            sources.append(env.data_source or "live")
        except FinanceC1Error as exc:
            use_existing_warnings.append(
                f"finance_payroll_unavailable[{cid}]: {exc}"
            )
            sources.append("unavailable")
    if not sources:
        return rows, "unavailable"
    if "unavailable" in sources:
        return rows, "cache" if rows else "unavailable"
    if "cache" in sources:
        return rows, "cache"
    if "mock" in sources:
        return rows, "mock"
    return rows, "live"


def _company_ids_payroll_recognition(warnings: List[str]) -> List[str]:
    """Return master_companies.id where ``payroll_recognition=True``.

    These are the only companies whose payroll feeds cost_center
    aggregation (per v1.3 §4.1 — only the entities that actually pay
    the workers count, not the legal/billing entities).
    """

    client = get_finance_c1_client()
    try:
        env = client.list_companies(is_active=True)
    except FinanceC1Error as exc:
        warnings.append(f"finance_companies_unavailable: {exc}")
        return []
    out: List[str] = []
    for row in env.data or []:
        if bool(row.get("payroll_recognition")):
            cid = row.get("id")
            if cid:
                out.append(str(cid))
    # If finance hasn't tagged anyone as payroll_recognition=True
    # (early staging), fall back to the full company list — better
    # than silently returning empty.
    if not out:
        for row in env.data or []:
            cid = row.get("id")
            if cid:
                out.append(str(cid))
    return out


def _compute_total_minutes_for_cost_center(
    db: Session,
    *,
    cost_center_id: str,
    period: str,
) -> Optional[Decimal]:
    """Best-effort total_minutes from shipment_costing_results metadata.

    Schema isn't fixed (model_version_processes.metadata might or might
    not have ``process_minutes`` — depends on what spec parsing wrote).
    We sum any numeric value found under
    ``ModelVersionProcess.metadata_json.process_minutes`` for processes
    bound to this cost_center, weighted by the active shipments in the
    period. v1 returns None when no data — that's fine, the
    rate_per_minute field also goes None and Hub falls back to global.
    """

    procs: List[models.ModelVersionProcess] = (
        db.query(models.ModelVersionProcess)
        .join(models.Process, models.Process.id == models.ModelVersionProcess.process_id)
        .filter(models.Process.cost_center_id == cost_center_id)
        .all()
    )
    if not procs:
        return None
    total = Decimal("0")
    found_any = False
    for p in procs:
        meta = p.metadata_json if isinstance(p.metadata_json, dict) else {}
        raw = meta.get("process_minutes") or meta.get("standard_minutes") or 0
        try:
            v = Decimal(str(raw))
            if v > 0:
                total += v
                found_any = True
        except Exception:  # noqa: BLE001
            continue
    return total if found_any else None


def _upsert_labor_per_minute_rate(
    db: Session,
    *,
    cost_center_id: str,
    rate_per_minute: Decimal,
    period: str,
    data_quality: str = "yellow",
) -> int:
    """Upsert a cost_rate_master row for this cost_center's labor rate.

    Uses ``long_tail_strategy_service.create_strategy`` (which doubles
    as upsert via the synthesized category UNIQUE constraint) — that
    keeps the audit history pipeline intact.
    """

    synthesized_category = (
        f"__labor_per_minute__cost_center__{cost_center_id.lower()}"
    )
    existing = long_tail_strategy_service.get_by_category(
        db, category=synthesized_category
    )
    payload: Dict[str, Any] = {
        "rate_type": "labor_per_minute",
        "scope_type": "cost_center",
        "scope_id": cost_center_id,
        "rate_basis": "per_minute",
        "rate": float(rate_per_minute),
        "source": "auto_aggregated_from_finance",
        "data_quality": data_quality,
        "effective_from": _period_first_day(period).isoformat(),
        "note": f"auto-aggregated from finance payroll for period {period}",
        "enabled": True,
    }
    if existing is None:
        long_tail_strategy_service.create_strategy(
            db, payload=payload, actor="cost_center_aggregator_service"
        )
        return 1
    long_tail_strategy_service.update_strategy(
        db,
        strategy_id=existing.id,
        patch=payload,
        actor="cost_center_aggregator_service",
    )
    return 1


def aggregate_cost_center_payroll(
    db: Session,
    *,
    cost_center_id: str,
    period: str,
) -> CostCenterPayrollAggregateResult:
    """Aggregate one cost_center for one period.

    Always returns a result — even when finance has no data, a fallback
    snapshot is written with warnings and ``data_quality='red'``.
    """

    cc = cost_center_service.get_cost_center(db, cost_center_id=cost_center_id)
    if cc is None:
        raise ValueError(f"cost_center not found: {cost_center_id}")
    year, month = _parse_period(period)

    warnings: List[str] = []
    company_ids = _company_ids_payroll_recognition(warnings)
    if not company_ids and not any("finance_companies_unavailable" in w for w in warnings):
        warnings.append("no_payroll_recognition_companies (finance staging?)")
    rows, data_source = _pull_payroll_for_companies(
        company_ids=company_ids,
        period_year=year,
        period_month=month,
        use_existing_warnings=warnings,
    )

    mapping_set = {
        _norm(d) for d in (cc.metadata_json or {}).get("finance_department_mapping") or []
    }
    if not mapping_set:
        # Use legacy_team_keywords as a soft fallback — works for fresh
        # installs before refresh_finance_department_mapping has run.
        mapping_set = {
            _norm(d) for d in (cc.metadata_json or {}).get("legacy_team_keywords") or []
        }
        if mapping_set:
            warnings.append("finance_department_mapping_empty: used legacy_team_keywords as fallback")
        else:
            warnings.append("finance_department_mapping_empty: aggregation may miss employees")

    matched: List[Dict[str, Any]] = []
    for row in rows:
        dept = _norm(row.get("department_raw"))
        if not dept:
            continue
        if not mapping_set:
            continue
        if any(d == dept or d in dept or dept in d for d in mapping_set if d):
            matched.append(row)

    headcount = len(matched)
    total_paid = Decimal("0")
    for r in matched:
        meta = r.get("metadata") or {}
        actual_paid = meta.get("actual_paid")
        if actual_paid is None:
            actual_paid = r.get("gross_salary") or 0
        try:
            total_paid += Decimal(str(actual_paid))
        except Exception:  # noqa: BLE001
            pass
    avg_salary = (total_paid / Decimal(headcount)) if headcount > 0 else Decimal("0")

    total_minutes = _compute_total_minutes_for_cost_center(
        db, cost_center_id=cost_center_id, period=period
    )
    rate_per_minute: Optional[Decimal] = None
    if total_minutes is not None and total_minutes > 0 and total_paid > 0:
        rate_per_minute = (total_paid / total_minutes).quantize(Decimal("0.0001"))

    if data_source == "unavailable":
        snapshot_data_source = "finance_payroll_fallback"
        data_quality = "red"
    elif headcount == 0:
        snapshot_data_source = "finance_payroll_fallback"
        data_quality = "yellow"
        warnings.append(
            f"no_finance_data_for_period: 0 employees matched for period {period}"
        )
    else:
        snapshot_data_source = "finance_payroll"
        data_quality = "yellow"  # auto-aggregated; ops can promote to green

    # Idempotent upsert per (cost_center_id, period).
    snapshot = (
        db.query(models.CostCenterPayrollSnapshot)
        .filter(
            models.CostCenterPayrollSnapshot.cost_center_id == cost_center_id,
            models.CostCenterPayrollSnapshot.period == period,
        )
        .first()
    )
    if snapshot is None:
        snapshot = models.CostCenterPayrollSnapshot(
            cost_center_id=cost_center_id,
            period=period,
            warnings=[],
            metadata_json={},
        )
        db.add(snapshot)

    snapshot.headcount = headcount
    snapshot.total_paid = total_paid
    snapshot.avg_salary = avg_salary
    snapshot.total_minutes = total_minutes
    snapshot.rate_per_minute = rate_per_minute
    snapshot.data_source = snapshot_data_source
    snapshot.data_quality = data_quality
    snapshot.warnings = list(warnings)
    snapshot.metadata_json = {
        "finance_data_source": data_source,
        "matched_employee_ids": [r.get("employee_id") for r in matched][:50],
        "company_ids_pulled": company_ids[:20],
        "aggregated_at": _utcnow().isoformat(),
    }

    upserted = 0
    if rate_per_minute is not None and rate_per_minute > 0:
        upserted = _upsert_labor_per_minute_rate(
            db,
            cost_center_id=cost_center_id,
            rate_per_minute=rate_per_minute,
            period=period,
            data_quality=data_quality,
        )

    db.commit()
    db.refresh(snapshot)
    return CostCenterPayrollAggregateResult(
        snapshot=snapshot,
        upserted_rate_rows=upserted,
        data_source=snapshot_data_source,
        warnings=warnings,
    )


def aggregate_all_cost_centers(
    db: Session, *, period: str
) -> CostCenterPayrollBatchResult:
    """Aggregate every active cost_center for the given period.

    Even when finance has 0 data for some/all centers, this still
    returns one snapshot row per active cost_center (using fallback +
    warnings). That guarantees the A5 Hub UI always has rows to render.
    """

    centers = cost_center_service.list_active(db)
    snapshots: List[models.CostCenterPayrollSnapshot] = []
    upserted_total = 0
    warnings: List[str] = []
    data_sources: List[str] = []
    for cc in centers:
        try:
            r = aggregate_cost_center_payroll(
                db, cost_center_id=cc.id, period=period
            )
        except Exception as exc:  # noqa: BLE001 — must not break the batch
            warnings.append(f"cost_center[{cc.code}] aggregate failed: {exc}")
            continue
        snapshots.append(r.snapshot)
        upserted_total += r.upserted_rate_rows
        data_sources.append(r.data_source)
        warnings.extend(r.warnings)

    if not data_sources:
        worst = "unavailable"
    elif "finance_payroll_fallback" in data_sources:
        worst = "finance_payroll_fallback"
    else:
        worst = "finance_payroll"

    return CostCenterPayrollBatchResult(
        snapshots=snapshots,
        upserted_rate_rows=upserted_total,
        data_source=worst,
        warnings=warnings,
    )


def list_snapshots(
    db: Session,
    *,
    cost_center_id: str,
    since: Optional[str] = None,
    until: Optional[str] = None,
) -> List[models.CostCenterPayrollSnapshot]:
    q = db.query(models.CostCenterPayrollSnapshot).filter(
        models.CostCenterPayrollSnapshot.cost_center_id == cost_center_id
    )
    if since:
        q = q.filter(models.CostCenterPayrollSnapshot.period >= since)
    if until:
        q = q.filter(models.CostCenterPayrollSnapshot.period <= until)
    return q.order_by(models.CostCenterPayrollSnapshot.period.desc()).all()


def list_snapshots_for_period(
    db: Session,
    *,
    period: str,
) -> List[models.CostCenterPayrollSnapshot]:
    """Read-only sibling of ``aggregate_all_cost_centers``: return all
    snapshots already written for ``period``, ordered by cost_center.code.

    Used by the Hub "Algorithm Log" tab and by ad-hoc audits — explicitly
    NOT calling the aggregator here keeps reads idempotent and fast.
    """

    return (
        db.query(models.CostCenterPayrollSnapshot)
        .join(
            models.CostCenter,
            models.CostCenter.id == models.CostCenterPayrollSnapshot.cost_center_id,
        )
        .filter(models.CostCenterPayrollSnapshot.period == period)
        .order_by(models.CostCenter.code.asc())
        .all()
    )


__all__ = [
    "CostCenterPayrollAggregateResult",
    "CostCenterPayrollBatchResult",
    "aggregate_cost_center_payroll",
    "aggregate_all_cost_centers",
    "list_snapshots",
    "list_snapshots_for_period",
]
