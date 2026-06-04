"""Cost center master service (Path A §A1).

Manages the ``cost_center`` table and its 6 initial seeds, plus the
runtime sync that aligns finance ``employees.department`` strings into
``cost_center.metadata.finance_department_mapping`` so downstream A2
aggregator can find which finance employees feed which cost_center.

Resolution policy:
- ``code`` is human-readable & immutable (CC_DECOR_PROD etc.); ``name``
  may be edited (e.g. when finance department naming changes).
- Soft-delete via ``deleted_at`` timestamp; ``is_active=False`` keeps
  the row visible but excludes from active resolves.
- Every mapping refresh appends a step to ``metadata.assignment_log``
  (capped at 50 entries, oldest dropped) so finance ops can audit.

This service does NOT touch ``cost_rate_master`` directly — that's
done by A2 ``cost_center_aggregator_service`` and A4 ``cost_allocator
_service`` via ``long_tail_strategy_service`` so audit history is
preserved through the existing ``_push_history`` pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from .. import models
from .finance_c1_client import FinanceC1Error, get_finance_c1_client


_MAX_ASSIGNMENT_LOG = 50


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _s(v: Any) -> str:
    return str(v if v is not None else "").strip()


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def list_cost_centers(
    db: Session,
    *,
    include_inactive: bool = False,
    include_deleted: bool = False,
) -> List[models.CostCenter]:
    q = db.query(models.CostCenter)
    if not include_deleted:
        q = q.filter(models.CostCenter.deleted_at.is_(None))
    if not include_inactive:
        q = q.filter(models.CostCenter.is_active.is_(True))
    return q.order_by(models.CostCenter.code.asc()).all()


def list_active(db: Session) -> List[models.CostCenter]:
    """Convenience for downstream services (A2/A3/A4) — active + not deleted."""

    return list_cost_centers(db, include_inactive=False, include_deleted=False)


def get_cost_center(db: Session, *, cost_center_id: str) -> Optional[models.CostCenter]:
    return (
        db.query(models.CostCenter)
        .filter(models.CostCenter.id == cost_center_id)
        .first()
    )


def get_by_code(db: Session, *, code: str) -> Optional[models.CostCenter]:
    code_clean = _s(code)
    if not code_clean:
        return None
    return (
        db.query(models.CostCenter)
        .filter(models.CostCenter.code == code_clean)
        .first()
    )


_VALID_TYPES = {"production", "auxiliary", "admin"}
_VALID_BASES = {"headcount", "team_hours", "revenue", "floor_area", "fixed_pct"}


def _validate_type(t: Any) -> str:
    s = _s(t).lower()
    if s not in _VALID_TYPES:
        raise ValueError(
            f"invalid type {t!r} (must be one of {sorted(_VALID_TYPES)})"
        )
    return s


def _validate_basis(b: Any) -> Optional[str]:
    if b in (None, ""):
        return None
    s = _s(b).lower()
    if s not in _VALID_BASES:
        raise ValueError(
            f"invalid default_allocation_basis {b!r} "
            f"(must be one of {sorted(_VALID_BASES)})"
        )
    return s


def _push_assignment_log(cc: models.CostCenter, *, by: str, action: str, note: Optional[str] = None, payload: Optional[Dict[str, Any]] = None) -> None:
    meta = dict(cc.metadata_json or {})
    log = list(meta.get("assignment_log") or [])
    entry: Dict[str, Any] = {
        "at": _utcnow_iso(),
        "by": by,
        "action": action,
    }
    if note:
        entry["note"] = note
    if payload:
        entry["payload"] = payload
    log.append(entry)
    if len(log) > _MAX_ASSIGNMENT_LOG:
        log = log[-_MAX_ASSIGNMENT_LOG:]
    meta["assignment_log"] = log
    cc.metadata_json = meta


def create_cost_center(
    db: Session,
    *,
    payload: Dict[str, Any],
    actor: Optional[str] = None,
) -> models.CostCenter:
    code = _s(payload.get("code")).upper()
    name = _s(payload.get("name"))
    type_ = _validate_type(payload.get("type"))
    basis = _validate_basis(payload.get("default_allocation_basis"))
    description = _s(payload.get("description")) or None
    if not code or not name:
        raise ValueError("code and name are required")
    if get_by_code(db, code=code) is not None:
        raise ValueError(f"cost_center code already exists: {code}")
    metadata = dict(payload.get("metadata") or {})
    legacy = payload.get("legacy_team_names") or []
    if not isinstance(legacy, list):
        legacy = []
    cc = models.CostCenter(
        code=code,
        name=name,
        type=type_,
        description=description,
        default_allocation_basis=basis,
        legacy_team_names=list(legacy),
        is_active=bool(payload.get("is_active", True)),
        metadata_json=metadata,
    )
    _push_assignment_log(cc, by=actor or "anonymous", action="create")
    db.add(cc)
    db.commit()
    db.refresh(cc)
    return cc


def update_cost_center(
    db: Session,
    *,
    cost_center_id: str,
    patch: Dict[str, Any],
    actor: Optional[str] = None,
) -> models.CostCenter:
    cc = get_cost_center(db, cost_center_id=cost_center_id)
    if cc is None:
        raise ValueError(f"cost_center not found: {cost_center_id}")
    if "name" in patch and patch["name"] is not None:
        cc.name = _s(patch["name"]) or cc.name
    if "type" in patch and patch["type"] is not None:
        cc.type = _validate_type(patch["type"])
    if "description" in patch:
        cc.description = _s(patch["description"]) or None
    if "default_allocation_basis" in patch:
        cc.default_allocation_basis = _validate_basis(patch["default_allocation_basis"])
    if "is_active" in patch and patch["is_active"] is not None:
        cc.is_active = bool(patch["is_active"])
    if "legacy_team_names" in patch and isinstance(patch["legacy_team_names"], list):
        cc.legacy_team_names = list(patch["legacy_team_names"])
    if "metadata" in patch and isinstance(patch["metadata"], dict):
        merged = dict(cc.metadata_json or {})
        merged.update(patch["metadata"])
        cc.metadata_json = merged
    _push_assignment_log(cc, by=actor or "anonymous", action="update")
    db.commit()
    db.refresh(cc)
    return cc


def soft_delete_cost_center(
    db: Session,
    *,
    cost_center_id: str,
    actor: Optional[str] = None,
) -> None:
    cc = get_cost_center(db, cost_center_id=cost_center_id)
    if cc is None:
        return
    cc.deleted_at = datetime.now(timezone.utc).replace(tzinfo=None)
    cc.is_active = False
    _push_assignment_log(cc, by=actor or "anonymous", action="soft_delete")
    db.commit()


def assign_processes(
    db: Session,
    *,
    cost_center_id: str,
    process_ids: List[str],
    actor: Optional[str] = None,
) -> int:
    """Bulk assign processes to a cost_center. Returns row count updated.

    Empty ``process_ids`` is allowed and is a no-op (returns 0).
    """

    cc = get_cost_center(db, cost_center_id=cost_center_id)
    if cc is None:
        raise ValueError(f"cost_center not found: {cost_center_id}")
    ids = [pid for pid in (process_ids or []) if pid]
    if not ids:
        return 0
    rows = (
        db.query(models.Process)
        .filter(models.Process.id.in_(ids))
        .update({models.Process.cost_center_id: cost_center_id}, synchronize_session=False)
    )
    _push_assignment_log(
        cc,
        by=actor or "anonymous",
        action="assign_processes",
        note=f"bound {rows} process rows",
        payload={"process_ids": ids[:20], "count": rows},
    )
    db.commit()
    db.refresh(cc)
    return int(rows)


# ---------------------------------------------------------------------------
# Stats — process_count / employee_count via finance pull
# ---------------------------------------------------------------------------


@dataclass
class CostCenterStats:
    """Per-cost_center stats used by the master page table."""

    cost_center_id: str
    code: str
    process_count: int = 0
    employee_count: int = 0
    finance_data_source: str = "live"  # live | cache | mock | unavailable
    finance_warnings: List[str] = field(default_factory=list)


def _process_count_map(db: Session) -> Dict[str, int]:
    rows = (
        db.query(
            models.Process.cost_center_id,
            # SQLAlchemy needs a func.count; we keep dependency-light.
        )
        .filter(models.Process.cost_center_id.isnot(None))
        .all()
    )
    out: Dict[str, int] = {}
    for (cc_id,) in rows:
        if cc_id:
            out[cc_id] = out.get(cc_id, 0) + 1
    return out


def _normalize_dept(s: Any) -> str:
    return _s(s).strip().lower()


def _pull_finance_employees(use_mock_only: bool = False) -> Tuple[List[Dict[str, Any]], str, List[str]]:
    """Pull finance employees envelope; degrade gracefully on errors.

    Returns (rows, data_source, warnings). ``data_source`` is one of
    live|cache|mock|unavailable; warnings list captures any soft errors.
    """

    warnings: List[str] = []
    try:
        client = get_finance_c1_client()
        env = client.list_employees(is_active=True)
        return list(env.data or []), env.data_source or "live", warnings
    except FinanceC1Error as exc:
        warnings.append(f"finance_employees_unavailable: {exc}")
        return [], "unavailable", warnings


def get_cost_centers_with_stats(
    db: Session,
    *,
    include_inactive: bool = False,
) -> List[Tuple[models.CostCenter, CostCenterStats]]:
    """List cost_centers with process_count + employee_count stats.

    ``employee_count`` is computed by mapping ``finance employees.department``
    against ``cc.metadata.finance_department_mapping`` (case-insensitive
    substring + exact match). Robust to finance unavailability — returns
    employee_count=0 with a warning.
    """

    centers = list_cost_centers(db, include_inactive=include_inactive)
    proc_count_map = _process_count_map(db)
    employees, data_source, warnings = _pull_finance_employees()

    # Build (department lower) → list of cost_center.id by using each cc's
    # finance_department_mapping; fall back to legacy_team_keywords if
    # mapping is empty (so initial pre-refresh state still produces sane
    # employee counts).
    cc_dept_map: Dict[str, List[str]] = {}
    for cc in centers:
        meta = cc.metadata_json or {}
        depts: List[str] = []
        depts.extend(meta.get("finance_department_mapping") or [])
        if not depts:
            depts.extend(meta.get("legacy_team_keywords") or [])
        depts.append(cc.name)
        cc_dept_map[cc.id] = [_normalize_dept(d) for d in depts if d]

    counts: Dict[str, int] = {cc.id: 0 for cc in centers}
    for emp in employees:
        dept_raw = _normalize_dept(emp.get("department"))
        if not dept_raw:
            continue
        for cc_id, depts in cc_dept_map.items():
            if any(d and (d == dept_raw or d in dept_raw or dept_raw in d) for d in depts):
                counts[cc_id] += 1
                break  # one employee → one cost_center

    out: List[Tuple[models.CostCenter, CostCenterStats]] = []
    for cc in centers:
        out.append(
            (
                cc,
                CostCenterStats(
                    cost_center_id=cc.id,
                    code=cc.code,
                    process_count=int(proc_count_map.get(cc.id, 0)),
                    employee_count=int(counts.get(cc.id, 0)),
                    finance_data_source=data_source,
                    finance_warnings=list(warnings),
                ),
            )
        )
    return out


# ---------------------------------------------------------------------------
# Finance department mapping refresh (path A §11)
# ---------------------------------------------------------------------------


@dataclass
class RefreshMappingResult:
    departments_seen: List[str]
    cost_centers_updated: int
    unmatched_departments: List[str]
    data_source: str
    warnings: List[str]


def _match_department_to_cost_center(
    department: str, centers: List[models.CostCenter]
) -> Optional[models.CostCenter]:
    """Heuristic: match by existing mapping → name → legacy keywords.

    The match rules are intentionally conservative — they prefer "no
    match" (returning None and bubbling to the unmatched_departments
    list) over an incorrect auto-bind, because A2 aggregator's payroll
    sums depend on this mapping being accurate.
    """

    dept = _normalize_dept(department)
    if not dept:
        return None
    # Round 1: existing finance_department_mapping (already curated)
    for cc in centers:
        meta = cc.metadata_json or {}
        for d in meta.get("finance_department_mapping") or []:
            if _normalize_dept(d) == dept:
                return cc
    # Round 2: cost_center name
    for cc in centers:
        if _normalize_dept(cc.name) == dept:
            return cc
    # Round 3: legacy keywords
    for cc in centers:
        meta = cc.metadata_json or {}
        for kw in meta.get("legacy_team_keywords") or []:
            kw_n = _normalize_dept(kw)
            if kw_n and (kw_n == dept or kw_n in dept):
                return cc
    return None


def refresh_finance_department_mapping(
    db: Session,
    *,
    actor: Optional[str] = None,
) -> RefreshMappingResult:
    """Pull finance employees' distinct departments and update each
    cost_center's metadata.finance_department_mapping.

    Behaviour:
    - For each *new* department string seen, append it to whichever
      cost_center matches by ``_match_department_to_cost_center``.
    - Departments that don't match any cost_center are returned in
      ``unmatched_departments`` (warning surface for ops).
    - finance unavailability is a non-fatal warning (returns empty
      result + ``data_source='unavailable'`` so the caller can still
      render a UI without 500-ing).
    """

    employees, data_source, warnings = _pull_finance_employees()
    centers = list_active(db)

    seen_depts = sorted({(_s(e.get("department")) or "") for e in employees if e.get("department")})
    seen_depts = [d for d in seen_depts if d]

    cost_centers_updated = 0
    unmatched: List[str] = []
    by_cc: Dict[str, List[str]] = {cc.id: [] for cc in centers}

    for dept in seen_depts:
        cc = _match_department_to_cost_center(dept, centers)
        if cc is None:
            unmatched.append(dept)
            continue
        by_cc[cc.id].append(dept)

    for cc in centers:
        meta = dict(cc.metadata_json or {})
        existing = list(meta.get("finance_department_mapping") or [])
        new_seen = by_cc.get(cc.id, [])
        merged = list(existing)
        added = 0
        for d in new_seen:
            if d not in merged:
                merged.append(d)
                added += 1
        if added > 0:
            meta["finance_department_mapping"] = merged
            cc.metadata_json = meta
            _push_assignment_log(
                cc,
                by=actor or "finance_dept_refresh",
                action="finance_dept_mapping_refresh",
                note=f"appended {added} dept(s) from finance",
                payload={"added": new_seen[:10], "data_source": data_source},
            )
            cost_centers_updated += 1

    if cost_centers_updated:
        db.commit()

    return RefreshMappingResult(
        departments_seen=seen_depts,
        cost_centers_updated=cost_centers_updated,
        unmatched_departments=unmatched,
        data_source=data_source,
        warnings=warnings,
    )


__all__ = [
    "CostCenterStats",
    "RefreshMappingResult",
    "list_cost_centers",
    "list_active",
    "get_cost_center",
    "get_by_code",
    "create_cost_center",
    "update_cost_center",
    "soft_delete_cost_center",
    "assign_processes",
    "get_cost_centers_with_stats",
    "refresh_finance_department_mapping",
]
