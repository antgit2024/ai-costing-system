from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import models, schemas
from ..dependencies import get_db_session
from ..integrations.executor_client import generate_trace_id
from ..services import audit_service, notification_service

router = APIRouter(tags=["Approvals"])

ROLE_MATRIX = {
    "submit": {"planner", "analyst"},
    "approve": {"approver", "exec"},
    "reject": {"approver", "exec"},
}


def _validate_role(action: str, role: str) -> None:
    allowed = ROLE_MATRIX.get(action, set())
    if role not in allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Role not permitted")


def _get_scenario(db: Session, scenario_id: str) -> models.ScenarioVersion:
    scenario = db.get(models.ScenarioVersion, scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")
    return scenario


def _get_initiative(db: Session, initiative_id: str) -> models.CostInitiative:
    initiative = db.get(models.CostInitiative, initiative_id)
    if not initiative:
        raise HTTPException(status_code=404, detail="Initiative not found")
    return initiative


def _record_approval(
    db: Session,
    *,
    target_type: str,
    target_id: str,
    action: str,
    actor_id: str,
    comment: str | None,
) -> None:
    record = models.ApprovalRecord(
        target_type=target_type,
        target_id=target_id,
        action=action,
        actor_id=actor_id,
        comment=comment,
    )
    db.add(record)


def _response(scenario: models.ScenarioVersion, initiative: models.CostInitiative) -> schemas.ApprovalActionResponse:
    return schemas.ApprovalActionResponse(
        scenario_id=scenario.id,
        scenario_status=scenario.status,
        initiative_status=initiative.status,
        baseline_flag=scenario.baseline_flag,
    )


@router.post(
    "/approvals/submit",
    response_model=schemas.ApprovalActionResponse,
)
def submit_scenario(
    payload: schemas.ApprovalSubmitRequest,
    db: Session = Depends(get_db_session),
):
    _validate_role("submit", payload.actor_role)
    scenario = _get_scenario(db, payload.scenario_id)
    if scenario.status not in {"draft", "rejected"}:
        raise HTTPException(status_code=400, detail="Scenario cannot be submitted")

    initiative = _get_initiative(db, scenario.initiative_id)
    scenario.status = "in_review"
    initiative.status = "review"
    trace_id = generate_trace_id()

    _record_approval(
        db,
        target_type="scenario",
        target_id=scenario.id,
        action="submit",
        actor_id=payload.actor_id,
        comment=payload.comment,
    )
    audit_service.log_audit_event(
        db,
        target_type="scenario",
        target_id=scenario.id,
        action="submit",
        actor_id=payload.actor_id,
        payload={"comment": payload.comment},
        trace_id=trace_id,
    )
    notification_service.dispatch_event(
        "SCENARIO_SUBMITTED",
        {"scenario_id": scenario.id, "actor_id": payload.actor_id},
        trace_id=trace_id,
    )
    db.commit()
    return _response(scenario, initiative)


@router.post(
    "/approvals/approve",
    response_model=schemas.ApprovalActionResponse,
)
def approve_scenario(
    payload: schemas.ApprovalApproveRequest,
    db: Session = Depends(get_db_session),
):
    _validate_role("approve", payload.actor_role)
    scenario = _get_scenario(db, payload.scenario_id)
    if scenario.status != "in_review":
        raise HTTPException(status_code=400, detail="Scenario must be in review")

    initiative = _get_initiative(db, scenario.initiative_id)
    scenario.status = "approved"
    initiative.status = "approved"

    if payload.set_baseline:
        db.query(models.ScenarioVersion).filter(
            models.ScenarioVersion.initiative_id == scenario.initiative_id,
            models.ScenarioVersion.id != scenario.id,
            models.ScenarioVersion.baseline_flag.is_(True),
        ).update({"baseline_flag": False}, synchronize_session=False)
        scenario.baseline_flag = True

    trace_id = generate_trace_id()

    _record_approval(
        db,
        target_type="scenario",
        target_id=scenario.id,
        action="approve",
        actor_id=payload.actor_id,
        comment=payload.comment,
    )
    audit_service.log_audit_event(
        db,
        target_type="scenario",
        target_id=scenario.id,
        action="approve",
        actor_id=payload.actor_id,
        payload={"baseline": scenario.baseline_flag, "comment": payload.comment},
        trace_id=trace_id,
    )
    notification_service.dispatch_event(
        "SCENARIO_APPROVED",
        {"scenario_id": scenario.id, "actor_id": payload.actor_id, "baseline": scenario.baseline_flag},
        trace_id=trace_id,
    )
    db.commit()
    return _response(scenario, initiative)


@router.post(
    "/approvals/reject",
    response_model=schemas.ApprovalActionResponse,
)
def reject_scenario(
    payload: schemas.ApprovalRejectRequest,
    db: Session = Depends(get_db_session),
):
    _validate_role("reject", payload.actor_role)
    scenario = _get_scenario(db, payload.scenario_id)
    if scenario.status != "in_review":
        raise HTTPException(status_code=400, detail="Scenario must be in review")

    initiative = _get_initiative(db, scenario.initiative_id)
    scenario.status = "rejected"
    scenario.baseline_flag = False
    initiative.status = "in_progress"

    trace_id = generate_trace_id()

    _record_approval(
        db,
        target_type="scenario",
        target_id=scenario.id,
        action="reject",
        actor_id=payload.actor_id,
        comment=payload.comment,
    )
    audit_service.log_audit_event(
        db,
        target_type="scenario",
        target_id=scenario.id,
        action="reject",
        actor_id=payload.actor_id,
        payload={"comment": payload.comment},
        trace_id=trace_id,
    )
    notification_service.dispatch_event(
        "SCENARIO_REJECTED",
        {"scenario_id": scenario.id, "actor_id": payload.actor_id},
        trace_id=trace_id,
    )
    db.commit()
    return _response(scenario, initiative)
