from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from .. import models


REPORT_SNAPSHOT_DOMAIN = "report_snapshot"
REPORT_SNAPSHOT_VERSION = "v1"


@dataclass(frozen=True)
class ReportSnapshot:
    key: str
    computed_at: datetime
    data: Dict[str, Any]
    params: Dict[str, Any]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def snapshot_key(kind: str, params: Dict[str, Any]) -> str:
    """
    Build a stable snapshot key for storage in taxonomy_items (domain=report_snapshot).

    Design goals:
    - No DB schema migration needed (reuse existing table)
    - Deterministic key string
    - Human-debuggable
    """
    k = str(kind or "").strip()
    if not k:
        raise ValueError("kind 不能为空")
    items = []
    for kk in sorted((params or {}).keys()):
        vv = params.get(kk)
        if vv in (None, ""):
            continue
        items.append(f"{kk}={vv}")
    suffix = "&".join(items) if items else ""
    return f"{k}?{suffix}" if suffix else k


def get_snapshot(db: Session, *, key: str) -> Optional[ReportSnapshot]:
    k = str(key or "").strip()
    if not k:
        return None
    row = (
        db.query(models.TaxonomyItem)
        .filter(
            models.TaxonomyItem.domain == REPORT_SNAPSHOT_DOMAIN,
            models.TaxonomyItem.name == k,
            models.TaxonomyItem.is_archived.is_(False),
        )
        .first()
    )
    if not row:
        return None
    meta = row.metadata_json if isinstance(row.metadata_json, dict) else {}
    computed_at_raw = meta.get("computed_at")
    computed_at = None
    if isinstance(computed_at_raw, str) and computed_at_raw.strip():
        try:
            s = computed_at_raw.strip()
            if s.endswith("Z"):
                s = s[:-1] + "+00:00"
            computed_at = datetime.fromisoformat(s)
            if computed_at.tzinfo is None:
                computed_at = computed_at.replace(tzinfo=timezone.utc)
        except Exception:
            computed_at = None
    data = meta.get("data") if isinstance(meta.get("data"), dict) else {}
    params = meta.get("params") if isinstance(meta.get("params"), dict) else {}
    return ReportSnapshot(
        key=k,
        computed_at=computed_at or (row.updated_at.replace(tzinfo=timezone.utc) if row.updated_at else _utcnow()),
        data=data,
        params=params,
    )


def upsert_snapshot(
    db: Session,
    *,
    key: str,
    data: Dict[str, Any],
    params: Dict[str, Any],
    operator_id: str | None = None,
    computed_at: datetime | None = None,
) -> ReportSnapshot:
    k = str(key or "").strip()
    if not k:
        raise ValueError("key 不能为空")
    op = str(operator_id or "").strip() or None
    ts = computed_at or _utcnow()
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    meta: Dict[str, Any] = {
        "version": REPORT_SNAPSHOT_VERSION,
        "computed_at": ts.isoformat(),
        "computed_by": op,
        "params": params or {},
        "data": data or {},
    }
    # Ensure JSON-serializable payload for DB JSON column:
    # - Decimal -> float
    # - datetime/date -> isoformat
    # - sets/tuples -> lists
    meta = jsonable_encoder(meta)

    row = (
        db.query(models.TaxonomyItem)
        .filter(
            models.TaxonomyItem.domain == REPORT_SNAPSHOT_DOMAIN,
            models.TaxonomyItem.name == k,
            models.TaxonomyItem.is_archived.is_(False),
        )
        .first()
    )
    if not row:
        row = models.TaxonomyItem(
            domain=REPORT_SNAPSHOT_DOMAIN,
            name=k,
            scopes_json=["*"],
            is_active=True,
            sort_order=0,
            source="local",
            metadata_json=meta,
        )
        db.add(row)
    else:
        row.metadata_json = meta
        row.is_active = True
    db.commit()
    return ReportSnapshot(key=k, computed_at=ts, data=data or {}, params=params or {})

