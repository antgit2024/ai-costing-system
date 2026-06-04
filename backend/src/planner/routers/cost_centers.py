"""HTTP endpoints for cost_center master + Path A §A2/A3/A4 batch services.

All endpoints live under ``/api/planner/cost-centers`` (master CRUD +
A2 aggregator) and ``/api/planner/fixed-costs`` / ``/cost-allocation``
(A3 + A4 — separate prefixes for clarity, all wired in this module so
front-end code only needs one import).

Auth: inherits the parent ``require_staff_role`` guard — admin /
operator / finance / factory_admin all permitted.
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..dependencies import get_db_session
from ..schemas import (
    CostAllocationLineRead,
    CostAllocationRunResponse,
    CostCenterAggregatePayrollResponse,
    CostCenterAssignProcessesRequest,
    CostCenterAssignProcessesResponse,
    CostCenterListResponse,
    CostCenterPayrollSnapshotRead,
    CostCenterRefreshMappingResponse,
    CostCenterStatsRead,
    CostCenterUpsertRequest,
    CostCenterWithStatsRead,
    FixedCostAmortizationLineRead,
    FixedCostAmortizeResponse,
)
from ..services import (
    cost_allocator_service,
    cost_center_aggregator_service,
    cost_center_service,
    fixed_cost_amortizer_service,
)
from .. import models


router = APIRouter(prefix="/cost-centers", tags=["CostCenters"])
fixed_costs_router = APIRouter(prefix="/fixed-costs", tags=["FixedCostAmortization"])
allocation_router = APIRouter(prefix="/cost-allocation", tags=["CostAllocation"])


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def _cost_center_to_read(
    cc: models.CostCenter,
    *,
    stats: Optional[cost_center_service.CostCenterStats] = None,
) -> CostCenterWithStatsRead:
    return CostCenterWithStatsRead(
        id=cc.id,
        code=cc.code,
        name=cc.name,
        type=cc.type,
        description=cc.description,
        default_allocation_basis=cc.default_allocation_basis,
        legacy_team_names=list(cc.legacy_team_names or []),
        is_active=bool(cc.is_active),
        metadata=dict(cc.metadata_json or {}),
        created_at=cc.created_at.isoformat() if cc.created_at else None,
        updated_at=cc.updated_at.isoformat() if cc.updated_at else None,
        deleted_at=cc.deleted_at.isoformat() if cc.deleted_at else None,
        stats=(
            CostCenterStatsRead(
                process_count=stats.process_count if stats else 0,
                employee_count=stats.employee_count if stats else 0,
                finance_data_source=stats.finance_data_source if stats else "live",
                finance_warnings=list(stats.finance_warnings) if stats else [],
            )
            if stats is not None
            else CostCenterStatsRead()
        ),
    )


def _payroll_snapshot_to_read(s: models.CostCenterPayrollSnapshot) -> CostCenterPayrollSnapshotRead:
    return CostCenterPayrollSnapshotRead(
        id=s.id,
        cost_center_id=s.cost_center_id,
        period=s.period,
        headcount=int(s.headcount or 0),
        total_paid=float(s.total_paid or 0),
        avg_salary=float(s.avg_salary or 0),
        total_minutes=float(s.total_minutes) if s.total_minutes is not None else None,
        rate_per_minute=float(s.rate_per_minute) if s.rate_per_minute is not None else None,
        data_source=s.data_source,
        data_quality=s.data_quality,
        warnings=list(s.warnings or []),
        metadata=dict(s.metadata_json or {}),
        created_at=s.created_at.isoformat() if s.created_at else None,
        updated_at=s.updated_at.isoformat() if s.updated_at else None,
    )


def _amortization_line_to_read(
    line: models.FixedCostAmortizationLine,
) -> FixedCostAmortizationLineRead:
    return FixedCostAmortizationLineRead(
        id=line.id,
        period=line.period,
        payment_request_id=line.payment_request_id,
        beneficiary_company_id=line.beneficiary_company_id,
        payer_company_id=line.payer_company_id,
        expense_category=line.expense_category,
        amount_amortized=float(line.amount_amortized or 0),
        is_monthly_amortized=bool(line.is_monthly_amortized),
        amort_months=line.amort_months,
        amort_start_period=line.amort_start_period,
        metadata=dict(line.metadata_json or {}),
        created_at=line.created_at.isoformat() if line.created_at else None,
    )


def _allocation_line_to_read(line: models.CostAllocationLine) -> CostAllocationLineRead:
    return CostAllocationLineRead(
        id=line.id,
        period=line.period,
        source_company_id=line.source_company_id,
        source_expense_category=line.source_expense_category,
        source_total_amount=float(line.source_total_amount or 0),
        target_cost_center_id=line.target_cost_center_id,
        allocation_basis=line.allocation_basis,
        allocation_basis_value=float(line.allocation_basis_value or 0),
        allocation_basis_total=float(line.allocation_basis_total or 0),
        allocation_weight=float(line.allocation_weight or 0),
        amount_allocated=float(line.amount_allocated or 0),
        fallback_chain=list(line.fallback_chain or []),
        warnings=list(line.warnings or []),
        metadata=dict(line.metadata_json or {}),
        created_at=line.created_at.isoformat() if line.created_at else None,
    )


# ---------------------------------------------------------------------------
# Master CRUD
# ---------------------------------------------------------------------------


@router.get("", response_model=CostCenterListResponse)
def list_cost_centers(
    include_inactive: bool = Query(False),
    with_stats: bool = Query(True, description="是否拉 finance employees 计算 employee_count(默认 true)"),
    db: Session = Depends(get_db_session),
):
    """List cost centers; default returns active rows + stats.

    ``with_stats=false`` skips finance employees pull entirely (fast
    path for downstream services that just need the master list).
    """

    if with_stats:
        rows = cost_center_service.get_cost_centers_with_stats(
            db, include_inactive=include_inactive
        )
        items = [_cost_center_to_read(cc, stats=stats) for cc, stats in rows]
        # Pull data_source from first stats (homogeneous for all rows since
        # we make one finance call per request).
        data_source = rows[0][1].finance_data_source if rows else "live"
        warnings = list(rows[0][1].finance_warnings) if rows else []
    else:
        ccs = cost_center_service.list_cost_centers(
            db, include_inactive=include_inactive
        )
        items = [_cost_center_to_read(cc) for cc in ccs]
        data_source = "skipped"
        warnings = []
    return CostCenterListResponse(
        items=items,
        finance_data_source=data_source,
        finance_warnings=warnings,
    )


@router.get("/{cost_center_id}", response_model=CostCenterWithStatsRead)
def get_cost_center(
    cost_center_id: str,
    db: Session = Depends(get_db_session),
):
    cc = cost_center_service.get_cost_center(db, cost_center_id=cost_center_id)
    if cc is None:
        raise HTTPException(status_code=404, detail="cost_center not found")
    return _cost_center_to_read(cc)


@router.post("", response_model=CostCenterWithStatsRead)
def create_cost_center(
    payload: CostCenterUpsertRequest,
    db: Session = Depends(get_db_session),
):
    body = payload.dict(exclude_unset=True)
    body.pop("actor", None)
    try:
        cc = cost_center_service.create_cost_center(
            db, payload=body, actor=payload.actor
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _cost_center_to_read(cc)


@router.patch("/{cost_center_id}", response_model=CostCenterWithStatsRead)
def update_cost_center(
    cost_center_id: str,
    payload: CostCenterUpsertRequest,
    db: Session = Depends(get_db_session),
):
    body = payload.dict(exclude_unset=True)
    body.pop("actor", None)
    body.pop("code", None)  # code is immutable
    try:
        cc = cost_center_service.update_cost_center(
            db, cost_center_id=cost_center_id, patch=body, actor=payload.actor
        )
    except ValueError as exc:
        message = str(exc)
        status_code = 404 if "not found" in message else 400
        raise HTTPException(status_code=status_code, detail=message)
    return _cost_center_to_read(cc)


@router.delete("/{cost_center_id}")
def delete_cost_center(
    cost_center_id: str,
    actor: Optional[str] = Query(None),
    db: Session = Depends(get_db_session),
):
    cost_center_service.soft_delete_cost_center(
        db, cost_center_id=cost_center_id, actor=actor
    )
    return {"ok": True}


@router.post(
    "/{cost_center_id}/assign-processes",
    response_model=CostCenterAssignProcessesResponse,
)
def assign_processes(
    cost_center_id: str,
    payload: CostCenterAssignProcessesRequest,
    db: Session = Depends(get_db_session),
):
    try:
        bound = cost_center_service.assign_processes(
            db,
            cost_center_id=cost_center_id,
            process_ids=payload.process_ids,
            actor=payload.actor,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return CostCenterAssignProcessesResponse(
        cost_center_id=cost_center_id, bound_count=bound
    )


@router.post(
    "/refresh-finance-mapping",
    response_model=CostCenterRefreshMappingResponse,
)
def refresh_finance_mapping(
    actor: Optional[str] = Query(None),
    db: Session = Depends(get_db_session),
):
    """Pull finance employees → distinct departments → update each
    cost_center.metadata.finance_department_mapping (path A §11)."""

    result = cost_center_service.refresh_finance_department_mapping(db, actor=actor)
    return CostCenterRefreshMappingResponse(
        departments_seen=result.departments_seen,
        cost_centers_updated=result.cost_centers_updated,
        unmatched_departments=result.unmatched_departments,
        finance_data_source=result.data_source,
        warnings=result.warnings,
    )


# ---------------------------------------------------------------------------
# A2 — payroll aggregator
# ---------------------------------------------------------------------------


@router.post(
    "/{cost_center_id}/aggregate-payroll",
    response_model=CostCenterAggregatePayrollResponse,
)
def aggregate_payroll(
    cost_center_id: str,
    period: str = Query(..., description="YYYY-MM, e.g. 2026-04", min_length=7, max_length=7),
    db: Session = Depends(get_db_session),
):
    cc = cost_center_service.get_cost_center(db, cost_center_id=cost_center_id)
    if cc is None:
        raise HTTPException(status_code=404, detail="cost_center not found")
    result = cost_center_aggregator_service.aggregate_cost_center_payroll(
        db, cost_center_id=cost_center_id, period=period
    )
    return CostCenterAggregatePayrollResponse(
        period=period,
        cost_center_count=1,
        snapshots=[_payroll_snapshot_to_read(result.snapshot)],
        upserted_rate_rows=result.upserted_rate_rows,
        finance_data_source=result.data_source,
        warnings=result.warnings,
    )


@router.post(
    "/aggregate-payroll-batch",
    response_model=CostCenterAggregatePayrollResponse,
)
def aggregate_payroll_batch(
    period: str = Query(..., description="YYYY-MM", min_length=7, max_length=7),
    db: Session = Depends(get_db_session),
):
    """Batch-aggregate all active cost_centers for the given period.

    Always returns one snapshot per active cost_center, even if finance
    has zero data — those get ``data_source='finance_payroll_fallback'``
    and the warning surface in ``warnings``.
    """

    batch = cost_center_aggregator_service.aggregate_all_cost_centers(
        db, period=period
    )
    return CostCenterAggregatePayrollResponse(
        period=period,
        cost_center_count=len(batch.snapshots),
        snapshots=[_payroll_snapshot_to_read(s) for s in batch.snapshots],
        upserted_rate_rows=batch.upserted_rate_rows,
        finance_data_source=batch.data_source,
        warnings=batch.warnings,
    )


@router.get(
    "/{cost_center_id}/payroll-snapshots",
    response_model=List[CostCenterPayrollSnapshotRead],
)
def list_payroll_snapshots(
    cost_center_id: str,
    since: Optional[str] = Query(None, description="YYYY-MM (inclusive)"),
    until: Optional[str] = Query(None, description="YYYY-MM (inclusive)"),
    db: Session = Depends(get_db_session),
):
    rows = cost_center_aggregator_service.list_snapshots(
        db, cost_center_id=cost_center_id, since=since, until=until
    )
    return [_payroll_snapshot_to_read(r) for r in rows]


@router.get(
    "/payroll-snapshots",
    response_model=List[CostCenterPayrollSnapshotRead],
)
def list_payroll_snapshots_for_period(
    period: str = Query(..., min_length=7, max_length=7, description="YYYY-MM"),
    db: Session = Depends(get_db_session),
):
    """Read-only batch fetch for the "Algorithm Log" tab.

    Returns all snapshots for one period, ordered by cost_center.code.
    Empty list if A2 hasn't been run yet for that period — no recompute.
    """

    rows = cost_center_aggregator_service.list_snapshots_for_period(db, period=period)
    return [_payroll_snapshot_to_read(r) for r in rows]


# ---------------------------------------------------------------------------
# A3 — fixed cost amortizer (mounted on /api/planner/fixed-costs)
# ---------------------------------------------------------------------------


@fixed_costs_router.post("/amortize", response_model=FixedCostAmortizeResponse)
def amortize_fixed_costs(
    period: str = Query(..., description="YYYY-MM", min_length=7, max_length=7),
    db: Session = Depends(get_db_session),
):
    result = fixed_cost_amortizer_service.amortize_fixed_costs_for_period(
        db, period=period
    )
    return FixedCostAmortizeResponse(
        period=period,
        lines_written=result.lines_written,
        total_amount=result.total_amount,
        by_category=result.by_category,
        by_company=result.by_company,
        finance_data_source=result.data_source,
        warnings=result.warnings,
    )


@fixed_costs_router.get(
    "/amortization", response_model=List[FixedCostAmortizationLineRead]
)
def list_amortization_lines(
    period: str = Query(..., min_length=7, max_length=7),
    expense_category: Optional[str] = Query(None),
    db: Session = Depends(get_db_session),
):
    rows = fixed_cost_amortizer_service.list_lines(
        db, period=period, expense_category=expense_category
    )
    return [_amortization_line_to_read(r) for r in rows]


@fixed_costs_router.get("/amortization/by-company")
def amortization_by_company(
    period: str = Query(..., min_length=7, max_length=7),
    db: Session = Depends(get_db_session),
):
    return fixed_cost_amortizer_service.aggregate_by_company(db, period=period)


@fixed_costs_router.get("/amortization/by-category")
def amortization_by_category(
    period: str = Query(..., min_length=7, max_length=7),
    db: Session = Depends(get_db_session),
):
    return fixed_cost_amortizer_service.aggregate_by_category(db, period=period)


# ---------------------------------------------------------------------------
# A4 — cost allocator (mounted on /api/planner/cost-allocation)
# ---------------------------------------------------------------------------


@allocation_router.post("/run", response_model=CostAllocationRunResponse)
def run_allocation(
    period: str = Query(..., min_length=7, max_length=7),
    fallback_mode: str = Query(
        "permissive",
        description="strict (无 driver 抛错) | permissive (默认; 走 fallback chain)",
    ),
    db: Session = Depends(get_db_session),
):
    result = cost_allocator_service.allocate_fixed_costs_to_cost_centers(
        db, period=period, fallback_mode=fallback_mode
    )
    return CostAllocationRunResponse(
        period=period,
        lines_written=result.lines_written,
        cost_centers_touched=result.cost_centers_touched,
        total_amount=result.total_amount,
        upserted_rate_rows=result.upserted_rate_rows,
        by_cost_center=result.by_cost_center,
        warnings=result.warnings,
    )


@allocation_router.get(
    "/lines", response_model=List[CostAllocationLineRead]
)
def list_allocation_lines(
    period: str = Query(..., min_length=7, max_length=7),
    cost_center_id: Optional[str] = Query(None),
    db: Session = Depends(get_db_session),
):
    rows = cost_allocator_service.list_lines(
        db, period=period, cost_center_id=cost_center_id
    )
    return [_allocation_line_to_read(r) for r in rows]


@allocation_router.get("/by-cost-center")
def allocation_by_cost_center(
    period: str = Query(..., min_length=7, max_length=7),
    db: Session = Depends(get_db_session),
):
    return cost_allocator_service.aggregate_by_cost_center(db, period=period)
