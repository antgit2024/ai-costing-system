from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .. import models, schemas
from ..dependencies import get_db_session

router = APIRouter(tags=["Planner Jobs"])

@router.get("/task-center/recent", response_model=schemas.TaskCenterListResponse)
def list_recent_jobs(
    limit: int = Query(30, ge=1, le=200),
    include_material: bool = True,
    include_planner: bool = True,
    db: Session = Depends(get_db_session),
):
    """
    A unified task list for the whole app.

    We intentionally aggregate multiple job tables (PlannerJob + MaterialSyncJob) so the UI
    can show "what's running" globally and avoid repeated clicks / duplicate executions.
    """
    items: List[schemas.TaskCenterItemRead] = []

    if include_planner:
        try:
            planner_jobs = (
                db.query(models.PlannerJob)
                .order_by(models.PlannerJob.created_at.desc())
                .limit(limit)
                .all()
            )
            for job in planner_jobs:
                items.append(
                    schemas.TaskCenterItemRead(
                        id=job.id,
                        source="planner",
                        job_type=job.job_type,
                        status=job.status,
                        requested_by=job.requested_by,
                        title=job.file_name or job.job_type,
                        created_at=job.created_at,
                        started_at=job.created_at,
                        finished_at=None if job.status not in ("completed", "failed") else job.updated_at,
                        updated_at=job.updated_at,
                        progress_current=job.processed_rows,
                        progress_total=job.total_rows,
                        payload=job.payload or {},
                        result=job.result or {},
                        error_message=None,
                    )
                )
        except SQLAlchemyError:
            # Never break global task probe because of a single table.
            # The UI uses this endpoint for a lightweight badge poll.
            include_planner = False

    if include_material:
        try:
            material_jobs = (
                db.query(models.MaterialSyncJob)
                .order_by(models.MaterialSyncJob.created_at.desc())
                .limit(limit)
                .all()
            )
            for job in material_jobs:
                items.append(
                    schemas.TaskCenterItemRead(
                        id=job.id,
                        source="material",
                        job_type=job.job_type,
                        status=job.status,
                        requested_by=job.requested_by,
                        title=job.job_type,
                        created_at=job.created_at,
                        started_at=job.started_at,
                        finished_at=job.finished_at,
                        updated_at=job.updated_at,
                        progress_current=None,
                        progress_total=None,
                        payload=job.payload or {},
                        result=job.result_json or {},
                        error_message=job.error_message,
                    )
                )
        except SQLAlchemyError:
            include_material = False

    # merge-sort by created_at desc
    items.sort(key=lambda x: x.created_at or datetime.min, reverse=True)
    return schemas.TaskCenterListResponse(items=items[:limit])


@router.get("/jobs/{job_id}", response_model=schemas.PlannerJobRead)
def get_job(job_id: str, db: Session = Depends(get_db_session)):
    job = db.get(models.PlannerJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job
