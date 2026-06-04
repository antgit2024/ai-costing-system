from fastapi import APIRouter

router = APIRouter(tags=["Planner Health"])


@router.get("/health")
def planner_healthcheck():
    return {"status": "ok"}
