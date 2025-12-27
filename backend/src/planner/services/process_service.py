from __future__ import annotations

from decimal import Decimal
from typing import Dict, List, Optional, Sequence, Tuple

from sqlalchemy import or_
from sqlalchemy.orm import Session

from .. import models
from ..utils.unit_normalizer import normalize_unit


class ProcessFilters:
    def __init__(
        self,
        *,
        search: Optional[str] = None,
        status: Optional[str] = None,
        charging_mode: Optional[str] = None,
        category: Optional[str] = None,
    ):
        self.search = search
        self.status = status
        self.charging_mode = charging_mode
        self.category = category


def list_processes(
    db: Session,
    *,
    filters: ProcessFilters,
    page: int,
    page_size: int,
) -> Tuple[int, Sequence[models.Process]]:
    query = db.query(models.Process).filter(models.Process.is_archived.is_(False))
    if filters.search:
        pattern = f"%{filters.search.strip()}%"
        query = query.filter(
            or_(models.Process.process_code.ilike(pattern), models.Process.process_name.ilike(pattern))
        )
    if filters.status:
        query = query.filter(models.Process.status == filters.status)
    if filters.charging_mode:
        query = query.filter(models.Process.charging_mode == filters.charging_mode)
    if filters.category:
        query = query.filter(models.Process.category == filters.category)
    total = query.count()
    items = (
        query.order_by(models.Process.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return total, items


def get_process(db: Session, process_id: str) -> Optional[models.Process]:
    return (
        db.query(models.Process)
        .filter(models.Process.id == process_id, models.Process.is_archived.is_(False))
        .one_or_none()
    )


def create_process(
    db: Session,
    *,
    process_code: str,
    process_name: str,
    description: Optional[str],
    category: Optional[str],
    team_name: Optional[str],
    charging_mode: str,
    standard_rate: Optional[Decimal],
    unit_of_measure: Optional[str],
    status: Optional[str],
    metadata: Optional[Dict[str, any]],
) -> models.Process:
    existing = (
        db.query(models.Process)
        .filter(models.Process.process_code == process_code, models.Process.is_archived.is_(False))
        .one_or_none()
    )
    if existing:
        raise ValueError("process_code already exists")

    model = models.Process(
        process_code=process_code,
        process_name=process_name,
        description=description,
        category=category,
        team_name=team_name,
        charging_mode=charging_mode,
        standard_rate=_to_decimal_or_none(standard_rate),
        unit_of_measure=normalize_unit(unit_of_measure),
        status=status or "draft",
        is_active=(status or "draft") == "active",
        metadata_json=metadata or {},
    )
    db.add(model)
    db.commit()
    db.refresh(model)
    return model


def update_process(
    db: Session,
    process: models.Process,
    *,
    process_name: Optional[str],
    description: Optional[str],
    category: Optional[str],
    team_name: Optional[str],
    charging_mode: Optional[str],
    standard_rate: Optional[Decimal],
    unit_of_measure: Optional[str],
    status: Optional[str],
    metadata: Optional[Dict[str, any]],
) -> models.Process:
    if process_name is not None:
        process.process_name = process_name
    if description is not None:
        process.description = description
    if category is not None:
        process.category = category
    if team_name is not None:
        process.team_name = team_name
    if charging_mode is not None:
        process.charging_mode = charging_mode
    if standard_rate is not None:
        process.standard_rate = _to_decimal_or_none(standard_rate)
    if unit_of_measure is not None:
        process.unit_of_measure = normalize_unit(unit_of_measure)
    if status is not None:
        process.status = status
        process.is_active = status == "active"
    if metadata is not None:
        process.metadata_json = metadata
    db.commit()
    db.refresh(process)
    return process


def copy_process(
    db: Session,
    process: models.Process,
    *,
    process_code: str,
    process_name: str,
    status: Optional[str],
) -> models.Process:
    existing = (
        db.query(models.Process)
        .filter(models.Process.process_code == process_code, models.Process.is_archived.is_(False))
        .one_or_none()
    )
    if existing:
        raise ValueError("process_code already exists")
    new_process = models.Process(
        process_code=process_code,
        process_name=process_name,
        description=process.description,
        category=process.category,
        team_name=process.team_name,
        charging_mode=process.charging_mode,
        standard_rate=process.standard_rate,
        unit_of_measure=process.unit_of_measure,
        status=status or process.status,
        is_active=(status or process.status) == "active",
        metadata_json=dict(process.metadata_json or {}),
    )
    db.add(new_process)
    db.commit()
    db.refresh(new_process)
    return new_process


def set_process_status(
    db: Session,
    process: models.Process,
    *,
    status: str,
) -> models.Process:
    process.status = status
    process.is_active = status == "active"
    db.commit()
    db.refresh(process)
    return process


def set_process_status_bulk(
    db: Session,
    *,
    ids: List[str],
    status: str,
) -> int:
    if not ids:
        return 0
    update_q = (
        db.query(models.Process)
        .filter(models.Process.id.in_(ids), models.Process.is_archived.is_(False))
    )
    count = update_q.count()
    update_q.update({"status": status, "is_active": status == "active"}, synchronize_session=False)
    db.commit()
    return count


def _to_decimal_or_none(value: Optional[Decimal]) -> Optional[Decimal]:
    if value is None:
        return None
    return Decimal(str(value))


























