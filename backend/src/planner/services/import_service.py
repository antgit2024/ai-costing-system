from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session, sessionmaker

from .. import models
from ...config import settings
from ...database import SessionLocal

SESSION_FACTORY: Optional[sessionmaker] = None


def set_session_factory(factory: sessionmaker) -> None:
    global SESSION_FACTORY
    SESSION_FACTORY = factory


def _get_factory() -> sessionmaker:
    return SESSION_FACTORY or SessionLocal


def _parse_decimal(value: str, field_name: str) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError) as exc:
        raise ValueError(f"Invalid decimal for {field_name}") from exc


def _parse_metadata(value: Optional[str]) -> Dict[str, Any]:
    if not value:
        return {}
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError("metadata must be valid JSON") from exc


def _persist_row(session: Session, row: Dict[str, Any], initiative_id: str) -> None:
    required_fields = [
        "package_id",
        "type",
        "description",
        "unit_of_measure",
        "quantity",
        "unit_cost_estimate",
        "currency",
    ]
    missing = [field for field in required_fields if not row.get(field)]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")

    package = session.get(models.CostPackage, row["package_id"])
    if not package or package.initiative_id != initiative_id:
        raise ValueError("Package does not exist for initiative")

    quantity = _parse_decimal(row["quantity"], "quantity")
    unit_cost = _parse_decimal(row["unit_cost_estimate"], "unit_cost_estimate")

    metadata = _parse_metadata(row.get("metadata"))

    line_item = models.CostLineItem(
        package_id=package.id,
        type=row["type"],
        reference_code=row.get("reference_code"),
        description=row["description"],
        unit_of_measure=row["unit_of_measure"],
        quantity=quantity,
        unit_cost_estimate=unit_cost,
        currency=row.get("currency", "CNY"),
        supplier_id=row.get("supplier_id"),
        status=row.get("status", "draft"),
        metadata_json=metadata,
    )
    session.add(line_item)


def process_import_job(job_id: str, file_bytes: bytes, chunk_size: Optional[int] = None) -> None:
    factory = _get_factory()
    session: Session = factory()
    chunk = chunk_size or settings.csv_import_chunk_size

    try:
        job = session.get(models.PlannerJob, job_id)
        if not job:
            return

        job.status = "processing"
        job.updated_at = datetime.now(timezone.utc)
        if not job.errors:
            job.errors = []
        session.commit()

        csv_buffer = io.StringIO(file_bytes.decode("utf-8"))
        reader = csv.DictReader(csv_buffer)
        row_number = 1
        for row in reader:
            row_number += 1
            job.total_rows += 1
            try:
                _persist_row(session, row, job.initiative_id)
                job.processed_rows += 1
            except Exception as exc:
                job.error_rows += 1
                errors = list(job.errors or [])
                errors.append({"row": row_number, "error": str(exc)})
                job.errors = errors
            if job.total_rows % chunk == 0:
                job.updated_at = datetime.now(timezone.utc)
                session.commit()

        job.status = "completed" if job.error_rows == 0 else "completed_with_errors"
        job.updated_at = datetime.now(timezone.utc)
        session.commit()
    except Exception as exc:  # pragma: no cover - defensive
        job = session.get(models.PlannerJob, job_id)
        if job:
            job.status = "failed"
            errors = list(job.errors or [])
            errors.append({"row": 0, "error": str(exc)})
            job.errors = errors
            job.updated_at = datetime.now(timezone.utc)
            session.commit()
    finally:
        session.close()
