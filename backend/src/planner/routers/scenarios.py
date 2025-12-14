from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from .. import models, schemas
from ...config import settings
from ..dependencies import PaginationParams, get_db_session
from ..integrations import executor_client
from ..services import audit_service, notification_service, snapshot_service

router = APIRouter(tags=["Scenarios"])


@router.get("/scenarios", response_model=schemas.ScenarioListResponse)
def list_scenarios(
    initiative_id: Optional[str] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    baseline_flag: Optional[bool] = None,
    favorite_only: bool = Query(False, description="Only return favorites for provided user_id"),
    user_id: Optional[str] = Query(None, description="User id for favorites flag"),
    search: Optional[str] = None,
    pagination: PaginationParams = Depends(),
    db: Session = Depends(get_db_session),
):
    query = db.query(models.ScenarioVersion)

    if initiative_id:
        query = query.filter(models.ScenarioVersion.initiative_id == initiative_id)
    if status_filter:
        query = query.filter(models.ScenarioVersion.status == status_filter)
    if baseline_flag is not None:
        query = query.filter(models.ScenarioVersion.baseline_flag == baseline_flag)
    if search:
        pattern = f"%{search.lower()}%"
        query = query.filter(
            or_(
                func.lower(models.ScenarioVersion.code).like(pattern),
                func.lower(models.ScenarioVersion.name).like(pattern),
            )
        )

    favorite_ids: set[str] = set()
    if user_id:
        favorite_ids = {
            row[0]
            for row in db.query(models.ScenarioFavorite.scenario_id).filter(
                models.ScenarioFavorite.user_id == user_id
            )
        }
        if favorite_only:
            if not favorite_ids:
                return schemas.ScenarioListResponse(total=0, page=pagination.page, page_size=pagination.page_size, items=[])
            query = query.filter(models.ScenarioVersion.id.in_(favorite_ids))
    elif favorite_only:
        raise HTTPException(
            status_code=400, detail="favorite_only filter requires user_id parameter"
        )

    total = query.count()
    items = (
        query.order_by(models.ScenarioVersion.updated_at.desc())
        .offset((pagination.page - 1) * pagination.page_size)
        .limit(pagination.page_size)
        .all()
    )

    response_items = [
        schemas.ScenarioRead(
            id=scenario.id,
            code=scenario.code,
            name=scenario.name,
            status=scenario.status,
            baseline_flag=scenario.baseline_flag,
            total_cost=scenario.total_cost,
            updated_at=scenario.updated_at,
            is_favorite=scenario.id in favorite_ids,
        )
        for scenario in items
    ]

    return schemas.ScenarioListResponse(
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
        items=response_items,
    )


@router.post(
    "/scenarios/{scenario_id}/favorite",
    response_model=schemas.ScenarioFavoriteStatus,
    status_code=status.HTTP_201_CREATED,
)
def favorite_scenario(
    scenario_id: str,
    payload: schemas.ScenarioFavoriteRequest,
    db: Session = Depends(get_db_session),
):
    scenario = db.get(models.ScenarioVersion, scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")

    favorite = (
        db.query(models.ScenarioFavorite)
        .filter(
            models.ScenarioFavorite.scenario_id == scenario_id,
            models.ScenarioFavorite.user_id == payload.user_id,
        )
        .first()
    )
    if not favorite:
        favorite = models.ScenarioFavorite(
            scenario_id=scenario_id,
            user_id=payload.user_id,
        )
        db.add(favorite)
        db.commit()
    return schemas.ScenarioFavoriteStatus(scenario_id=scenario_id, favorite=True)


@router.delete(
    "/scenarios/{scenario_id}/favorite",
    response_model=schemas.ScenarioFavoriteStatus,
    status_code=status.HTTP_200_OK,
)
def unfavorite_scenario(
    scenario_id: str,
    user_id: str = Query(...),
    db: Session = Depends(get_db_session),
):
    favorite = (
        db.query(models.ScenarioFavorite)
        .filter(
            models.ScenarioFavorite.scenario_id == scenario_id,
            models.ScenarioFavorite.user_id == user_id,
        )
        .first()
    )
    if not favorite:
        raise HTTPException(status_code=404, detail="Favorite not found")
    db.delete(favorite)
    db.commit()
    return schemas.ScenarioFavoriteStatus(scenario_id=scenario_id, favorite=False)


def _create_job(
    db: Session,
    initiative_id: str,
    requested_by: str,
    job_type: str,
    payload: dict,
    file_name: Optional[str] = None,
) -> models.PlannerJob:
    job = models.PlannerJob(
        initiative_id=initiative_id,
        file_name=file_name,
        requested_by=requested_by,
        status="processing",
        job_type=job_type,
        payload=payload,
    )
    db.add(job)
    db.flush()
    return job


@router.post(
    "/scenarios/{scenario_id}/clone",
    response_model=schemas.ScenarioCloneResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def clone_scenario(
    scenario_id: str,
    payload: schemas.ScenarioCloneRequest,
    db: Session = Depends(get_db_session),
):
    scenario = db.get(models.ScenarioVersion, scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")

    file_name = payload.name or payload.code
    job = _create_job(
        db,
        initiative_id=scenario.initiative_id,
        requested_by=payload.requested_by,
        job_type="scenario_snapshot",
        payload={
            "source_scenario_id": scenario_id,
            "line_item_ids": payload.line_item_ids or [],
        },
        file_name=file_name,
    )

    trace_id = executor_client.generate_trace_id()

    try:
        new_scenario, snapshot_count = snapshot_service.clone_scenario_with_snapshots(
            db,
            scenario_id,
            code=payload.code,
            name=payload.name,
            line_item_ids=payload.line_item_ids,
        )
        job.status = "completed"
        job.total_rows = snapshot_count
        job.processed_rows = snapshot_count
        job.result = {"scenario_id": new_scenario.id}
    except ValueError as exc:
        job.status = "failed"
        job.errors = [{"row": 0, "error": str(exc)}]
        db.commit()
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:  # pragma: no cover - defensive
        job.status = "failed"
        job.errors = [{"row": 0, "error": str(exc)}]
        db.commit()
        raise

    audit_service.log_audit_event(
        db,
        target_type="scenario",
        target_id=scenario_id,
        action="scenario_clone",
        actor_id=payload.requested_by,
        payload={"job_id": job.id, "new_scenario_id": job.result["scenario_id"]},
        trace_id=trace_id,
    )
    notification_service.dispatch_event(
        "SCENARIO_CLONED",
        {"scenario_id": scenario_id, "new_scenario_id": job.result["scenario_id"]},
        trace_id=trace_id,
    )
    db.commit()
    return schemas.ScenarioCloneResponse(job_id=job.id, scenario_id=job.result["scenario_id"])


@router.get(
    "/scenarios/{scenario_id}/diff",
    response_model=schemas.ScenarioDiffResponse,
)
def scenario_diff(
    scenario_id: str,
    against: str = Query(..., description="Scenario id to compare against"),
    package_id: Optional[str] = None,
    item_type: Optional[str] = Query(None, alias="type"),
    pagination: PaginationParams = Depends(),
    db: Session = Depends(get_db_session),
):
    source = db.get(models.ScenarioVersion, scenario_id)
    target = db.get(models.ScenarioVersion, against)
    if not source or not target:
        raise HTTPException(status_code=404, detail="Scenario not found")

    trace_id = executor_client.generate_trace_id()

    job = _create_job(
        db,
        initiative_id=source.initiative_id,
        requested_by="system",
        job_type="scenario_diff",
        payload={
            "source": scenario_id,
            "against": against,
            "package_id": package_id,
            "item_type": item_type,
        },
        file_name=f"diff-{source.code}-{target.code}",
    )

    summary_raw, diffs = snapshot_service.calculate_scenario_diff(
        db,
        source_scenario_id=scenario_id,
        target_scenario_id=against,
        package_id=package_id,
        item_type=item_type,
    )

    diffs.sort(key=lambda item: (item.get("reference_code") or "", item.get("description") or ""))
    total = len(diffs)
    start = (pagination.page - 1) * pagination.page_size
    end = start + pagination.page_size
    page_items = diffs[start:end]

    source_total = summary_raw["source_total"]
    target_total = summary_raw["target_total"]
    variance = summary_raw["variance"]
    variance_percent = 0.0
    if target_total != Decimal("0"):
        variance_percent = float((variance / target_total) * Decimal("100"))

    job.status = "completed"
    job.total_rows = total
    job.processed_rows = total
    job.result = {
        "total": total,
        "source_total": str(source_total),
        "target_total": str(target_total),
    }
    audit_service.log_audit_event(
        db,
        target_type="scenario",
        target_id=scenario_id,
        action="scenario_diff",
        actor_id="system",
        payload={"job_id": job.id, "target_scenario_id": against},
        trace_id=trace_id,
    )
    notification_service.dispatch_event(
        "SCENARIO_DIFF_READY",
        {"scenario_id": scenario_id, "against": against, "job_id": job.id},
        trace_id=trace_id,
    )
    db.commit()

    summary = schemas.ScenarioDiffSummary(
        source_scenario_id=scenario_id,
        target_scenario_id=against,
        total_cost_source=source_total,
        total_cost_target=target_total,
        variance=variance,
        variance_percent=variance_percent,
    )

    return schemas.ScenarioDiffResponse(
        job_id=job.id,
        summary=summary,
        line_diffs=page_items,
        page=pagination.page,
        page_size=pagination.page_size,
        total=total,
    )


@router.post(
    "/scenarios/{scenario_id}/export",
    response_model=schemas.ScenarioExportResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def export_scenario(
    scenario_id: str,
    payload: schemas.ScenarioExportRequest,
    db: Session = Depends(get_db_session),
):
    scenario = db.get(models.ScenarioVersion, scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")
    if scenario.status != "approved":
        raise HTTPException(status_code=400, detail="Scenario must be approved before export")

    trace_id = executor_client.generate_trace_id()

    job = _create_job(
        db,
        initiative_id=scenario.initiative_id,
        requested_by=payload.requested_by,
        job_type="scenario_export",
        payload={"scenario_id": scenario.id},
        file_name=f"export-{scenario.code}",
    )

    client = executor_client.get_executor_client()
    export_payload = {
        "scenario_id": scenario.id,
        "initiative_id": scenario.initiative_id,
        "total_cost": str(scenario.total_cost or 0),
        "requested_by": payload.requested_by,
        "comment": payload.comment,
        "trace_id": trace_id,
        "callback_url": settings.executor_callback_url,
    }
    result = client.export_scenario(export_payload, trace_id)

    job.status = "completed"
    job.total_rows = 1
    job.processed_rows = 1
    job.result = result

    callback_record = models.PlannerExecutorCallback(
        scenario_id=scenario.id,
        callback_url=settings.executor_callback_url,
        signature="pending",
        status="pending",
        payload={},
        trace_id=trace_id,
    )
    db.add(callback_record)

    audit_service.log_audit_event(
        db,
        target_type="scenario",
        target_id=scenario_id,
        action="scenario_export",
        actor_id=payload.requested_by,
        payload={"job_id": job.id, "executor_reference": result["reference_id"]},
        trace_id=trace_id,
    )

    notification_service.dispatch_event(
        "SCENARIO_EXPORTED",
        {
            "scenario_id": scenario_id,
            "initiative_id": scenario.initiative_id,
            "executor_reference": result["reference_id"],
        },
        trace_id=trace_id,
    )

    db.commit()
    return schemas.ScenarioExportResponse(
        job_id=job.id,
        scenario_id=scenario_id,
        executor_reference=result["reference_id"],
    )
