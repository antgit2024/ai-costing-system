from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..dependencies import get_db_session

router = APIRouter(tags=["Planner Jobs"])


@router.get("/jobs/{job_id}", response_model=schemas.PlannerJobRead)
def get_job(job_id: str, db: Session = Depends(get_db_session)):
    job = db.get(models.PlannerJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job
