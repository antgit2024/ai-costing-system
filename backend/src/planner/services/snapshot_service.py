from __future__ import annotations

from decimal import Decimal
from typing import Dict, Iterable, List, Optional, Tuple

from sqlalchemy.orm import Session

from .. import models


def _decimal(value: Decimal | float | int | None) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def clone_scenario_with_snapshots(
    db: Session,
    source_scenario_id: str,
    *,
    code: str,
    name: str,
    line_item_ids: Optional[List[str]] = None,
) -> Tuple[models.ScenarioVersion, int]:
    source = db.get(models.ScenarioVersion, source_scenario_id)
    if not source:
        raise ValueError("Source scenario not found")
    if not source.baseline_flag or source.status != "approved":
        raise ValueError("Only approved baseline scenarios can be cloned")

    new_scenario = models.ScenarioVersion(
        initiative_id=source.initiative_id,
        code=code,
        name=name,
        baseline_flag=False,
        status="draft",
        assumption_set_id=source.assumption_set_id,
        notes=source.notes,
    )
    db.add(new_scenario)
    db.flush()

    line_items_query = (
        db.query(models.CostLineItem)
        .join(models.CostPackage)
        .filter(
            models.CostPackage.initiative_id == source.initiative_id,
            models.CostLineItem.is_archived.is_(False),
        )
    )
    if line_item_ids:
        line_items_query = line_items_query.filter(models.CostLineItem.id.in_(line_item_ids))

    snapshots_created = 0
    total_cost = Decimal("0")
    for line_item in line_items_query:
        quantity = _decimal(line_item.quantity)
        unit_cost = _decimal(line_item.unit_cost_estimate)
        line_total = quantity * unit_cost
        snapshot = models.ScenarioLineSnapshot(
            scenario_id=new_scenario.id,
            line_item_id=line_item.id,
            quantity=quantity,
            unit_cost=unit_cost,
            currency=line_item.currency,
            fx_rate_used=Decimal("1"),
            markup_percent=None,
            total_cost=line_total,
            drivers={"assumption_set_id": source.assumption_set_id},
        )
        db.add(snapshot)
        snapshots_created += 1
        total_cost += line_total

    new_scenario.total_cost = total_cost
    db.flush()
    return new_scenario, snapshots_created


def _map_snapshots(snapshots: Iterable[models.ScenarioLineSnapshot]) -> Dict[str, models.ScenarioLineSnapshot]:
    return {snapshot.line_item_id: snapshot for snapshot in snapshots}


def calculate_scenario_diff(
    db: Session,
    *,
    source_scenario_id: str,
    target_scenario_id: str,
    package_id: Optional[str] = None,
    item_type: Optional[str] = None,
) -> Tuple[Dict[str, Decimal], List[Dict[str, object]]]:
    source_snaps = _map_snapshots(
        db.query(models.ScenarioLineSnapshot).filter(
            models.ScenarioLineSnapshot.scenario_id == source_scenario_id
        )
    )
    target_snaps = _map_snapshots(
        db.query(models.ScenarioLineSnapshot).filter(
            models.ScenarioLineSnapshot.scenario_id == target_scenario_id
        )
    )

    line_item_ids = set(source_snaps.keys()) | set(target_snaps.keys())
    if not line_item_ids:
        return (
            {
                "source_total": Decimal("0"),
                "target_total": Decimal("0"),
                "variance": Decimal("0"),
            },
            [],
        )

    line_meta = {
        li.id: li
        for li in db.query(models.CostLineItem).filter(models.CostLineItem.id.in_(line_item_ids))
    }
    package_ids = {li.package_id for li in line_meta.values()}
    package_map = {
        pkg.id: pkg.name
        for pkg in db.query(models.CostPackage).filter(models.CostPackage.id.in_(package_ids))
    }

    diffs: List[Dict[str, object]] = []
    source_total = Decimal("0")
    target_total = Decimal("0")

    for line_id in line_item_ids:
        metadata = line_meta.get(line_id)
        if not metadata:
            continue
        if package_id and metadata.package_id != package_id:
            continue
        if item_type and metadata.type != item_type:
            continue

        source_snapshot = source_snaps.get(line_id)
        target_snapshot = target_snaps.get(line_id)

        source_qty = _decimal(source_snapshot.quantity if source_snapshot else None)
        target_qty = _decimal(target_snapshot.quantity if target_snapshot else None)
        source_total_cost = _decimal(source_snapshot.total_cost if source_snapshot else None)
        target_total_cost = _decimal(target_snapshot.total_cost if target_snapshot else None)
        source_unit = _decimal(source_snapshot.unit_cost if source_snapshot else None)
        target_unit = _decimal(target_snapshot.unit_cost if target_snapshot else None)

        source_total += source_total_cost
        target_total += target_total_cost

        diffs.append(
            {
                "line_item_id": line_id,
                "reference_code": metadata.reference_code,
                "description": metadata.description,
                "package_id": metadata.package_id,
                "package_name": package_map.get(metadata.package_id),
                "item_type": metadata.type,
                "quantity_diff": source_qty - target_qty,
                "unit_cost_diff": source_unit - target_unit,
                "total_cost_diff": source_total_cost - target_total_cost,
                "source_total": source_total_cost,
                "target_total": target_total_cost,
            }
        )

    summary = {
        "source_total": source_total,
        "target_total": target_total,
        "variance": source_total - target_total,
    }
    return summary, diffs
