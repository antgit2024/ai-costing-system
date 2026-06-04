"""Cost-quality badge service (U7-A).

Companion to the Cost Rate Hub v1.3 4-layer overhead_rate resolver.

Where Hub.resolve_overhead_rate is called per-shipment-line in the
**costing path** (one DB query each is fine because we batch by line),
this module is for the **analytics path** (5 InsightsPage endpoints) where
we may aggregate hundreds-thousands of shipment lines per request and
must NOT trigger N+1 queries.

Strategy (per task brief §3.5):

1. Up-front, prefetch ALL enabled overhead_rate rows in cost_rate_master
   in **one** query and bucketize them by scope_type+scope_id in memory.
2. Provide an in-memory ``derive_badge_for_model(...)`` that walks the
   chain ``model > category > cost_center > global > hard_fallback``
   purely from the prefetched dicts (zero DB calls per row).
3. Provide ``aggregate_quality(badges)`` that takes the worst level
   when multiple model badges roll up into one analytics row
   (e.g. profit_by_channel aggregates over many models).

The badge structure mirrors ``schemas.CostQualityBadge`` but is exposed
here as a plain dict to keep this layer independent of pydantic so it can
be returned straight from analytics_service into the response payload
(pydantic auto-coerces dicts on serialization).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy.orm import Session

from .. import models


# ---------------------------------------------------------------------------
# Constants — keep aligned with task brief §3.2
# ---------------------------------------------------------------------------

HIT_LAYER_TO_LEVEL: Dict[str, str] = {
    "model": "green",
    "category": "yellow",
    "cost_center": "yellow",
    "global": "red",
    "metadata_json": "yellow",
    "hard_fallback": "red",
}

# Severity ranks for aggregation (higher rank = worse, picked first).
_LEVEL_RANK: Dict[str, int] = {"green": 0, "yellow": 1, "red": 2}


def _level_for(hit_layer: str) -> str:
    return HIT_LAYER_TO_LEVEL.get(hit_layer, "red")


def _utcnow_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _row_iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    try:
        # SQLAlchemy returns naive datetimes; just ISO-stringify.
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return str(value)
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# Lookup builder — one query, bucketized in memory
# ---------------------------------------------------------------------------


@dataclass
class _OverheadRow:
    strategy_id: str
    rate: Decimal
    source: Optional[str]
    data_quality: Optional[str]
    updated_at: Optional[str]
    effective_from: Optional[datetime]
    effective_to: Optional[datetime]
    priority: int


@dataclass
class OverheadQualityLookup:
    """Pre-bucketed cost_rate_master rows for fast in-memory lookup."""

    by_model: Dict[str, _OverheadRow]
    by_category: Dict[str, _OverheadRow]
    by_cost_center: Dict[str, _OverheadRow]
    global_row: Optional[_OverheadRow]


def _is_active(row: _OverheadRow, now: datetime) -> bool:
    if row.effective_from is not None and row.effective_from > now:
        return False
    if row.effective_to is not None and row.effective_to <= now:
        return False
    return True


def _pick_best(rows: Iterable[_OverheadRow], now: datetime) -> Optional[_OverheadRow]:
    """Pick the most-recently-effective active row from a candidate list.

    Mirrors `long_tail_strategy_service.resolve_overhead_rate`'s ordering:
    effective_from desc, then priority desc, then created_at desc. We don't
    have created_at on the dataclass — strategy_id ASC is a stable enough
    tiebreaker for analytics (production rows rarely tie on (effective_from,
    priority)).
    """
    best: Optional[_OverheadRow] = None
    best_key: Any = None
    for row in rows:
        if not _is_active(row, now):
            continue
        key = (
            row.effective_from or datetime.min,
            row.priority,
            row.strategy_id,
        )
        if best is None or key > best_key:
            best = row
            best_key = key
    return best


def build_overhead_quality_lookup(
    db: Session, *, as_of: Optional[datetime] = None
) -> OverheadQualityLookup:
    """Prefetch + bucketize all enabled overhead_rate rows in one query.

    Skips rows whose effective window doesn't include ``as_of`` (defaults
    to now in naive UTC, matching the store/effective_from semantics).
    """
    now = (as_of or datetime.utcnow()).replace(tzinfo=None) if as_of and getattr(as_of, "tzinfo", None) else (as_of or datetime.utcnow())

    rows = (
        db.query(models.LongTailCogsRateStrategy)
        .filter(
            models.LongTailCogsRateStrategy.rate_type == "overhead_rate",
            models.LongTailCogsRateStrategy.enabled.is_(True),
            models.LongTailCogsRateStrategy.is_archived.is_(False),
        )
        .all()
    )

    by_model_buckets: Dict[str, List[_OverheadRow]] = {}
    by_category_buckets: Dict[str, List[_OverheadRow]] = {}
    by_cost_center_buckets: Dict[str, List[_OverheadRow]] = {}
    global_buckets: List[_OverheadRow] = []

    for r in rows:
        ovr = _OverheadRow(
            strategy_id=str(r.id),
            rate=Decimal(str(r.rate)) if r.rate is not None else Decimal("0"),
            source=getattr(r, "source", None),
            data_quality=getattr(r, "data_quality", None),
            updated_at=_row_iso(getattr(r, "updated_at", None)),
            effective_from=getattr(r, "effective_from", None),
            effective_to=getattr(r, "effective_to", None),
            priority=int(getattr(r, "priority", 0) or 0),
        )
        scope_type = (getattr(r, "scope_type", None) or "").strip().lower()
        scope_id = (getattr(r, "scope_id", None) or "").strip()

        if scope_type == "model" and scope_id:
            by_model_buckets.setdefault(scope_id, []).append(ovr)
        elif scope_type == "category" and scope_id:
            by_category_buckets.setdefault(scope_id, []).append(ovr)
        elif scope_type == "cost_center" and scope_id:
            by_cost_center_buckets.setdefault(scope_id, []).append(ovr)
        elif scope_type == "global":
            global_buckets.append(ovr)
        # ignore stray rows with unexpected scope_type for safety

    by_model: Dict[str, _OverheadRow] = {}
    for k, v in by_model_buckets.items():
        best = _pick_best(v, now)
        if best is not None:
            by_model[k] = best

    by_category: Dict[str, _OverheadRow] = {}
    for k, v in by_category_buckets.items():
        best = _pick_best(v, now)
        if best is not None:
            by_category[k] = best

    by_cost_center: Dict[str, _OverheadRow] = {}
    for k, v in by_cost_center_buckets.items():
        best = _pick_best(v, now)
        if best is not None:
            by_cost_center[k] = best

    global_row = _pick_best(global_buckets, now)

    return OverheadQualityLookup(
        by_model=by_model,
        by_category=by_category,
        by_cost_center=by_cost_center,
        global_row=global_row,
    )


# ---------------------------------------------------------------------------
# Per-row badge derivation — pure in-memory
# ---------------------------------------------------------------------------


def _row_to_badge(row: _OverheadRow, hit_layer: str) -> Dict[str, Any]:
    return {
        "level": _level_for(hit_layer),
        "hit_layer": hit_layer,
        "source": (row.source or "cost_rate_hub"),
        "updated_at": row.updated_at,
    }


def _hard_fallback_badge() -> Dict[str, Any]:
    return {
        "level": "red",
        "hit_layer": "hard_fallback",
        "source": "hardcoded_0.30",
        "updated_at": None,
    }


def derive_badge_for_model(
    lookup: OverheadQualityLookup,
    *,
    model_id: Optional[str] = None,
    category: Optional[str] = None,
    cost_center_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Walk model > category > cost_center > global > hard_fallback in-memory.

    Always returns a badge dict (never None). Use ``hard_fallback`` red when
    nothing matches — that's the same semantic as Hub's resolver returning
    0.30 with data_quality='red'.
    """
    if model_id:
        mid = str(model_id).strip()
        if mid and mid in lookup.by_model:
            return _row_to_badge(lookup.by_model[mid], "model")

    if category:
        cat = str(category).strip()
        if cat and cat in lookup.by_category:
            return _row_to_badge(lookup.by_category[cat], "category")

    if cost_center_id:
        cc = str(cost_center_id).strip()
        if cc and cc in lookup.by_cost_center:
            return _row_to_badge(lookup.by_cost_center[cc], "cost_center")

    if lookup.global_row is not None:
        return _row_to_badge(lookup.global_row, "global")

    return _hard_fallback_badge()


# ---------------------------------------------------------------------------
# Aggregation — multiple SKU/model badges roll up to one analytics row
# ---------------------------------------------------------------------------


def aggregate_quality(badges: Iterable[Optional[Dict[str, Any]]]) -> Optional[Dict[str, Any]]:
    """Combine N per-row badges into one row badge by taking the worst level.

    Per task brief §3.3:
    - any red present  → return red representative
    - else any yellow  → return yellow representative
    - all green        → return green representative
    - empty / all None → return None (don't display anything)

    The "representative" badge is the **first** badge encountered at the
    chosen level — preserves a usable hit_layer/source/updated_at so the
    tooltip remains informative without inventing a fake aggregated layer.
    """
    chosen_rank = -1
    chosen: Optional[Dict[str, Any]] = None
    for b in badges:
        if not b:
            continue
        level = b.get("level") or "red"
        rank = _LEVEL_RANK.get(level, 2)
        if rank > chosen_rank:
            chosen_rank = rank
            chosen = b
    return chosen
