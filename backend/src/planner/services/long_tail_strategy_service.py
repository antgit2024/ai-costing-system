"""Long-tail COGS rate strategy service (Issue 28).

Maintains the per-category cogs rate used to estimate cogs for SKUs marked
``governance_status='do_not_model'`` (no real model/BOM, no spec parsing).

Resolution order at compute time (called from
``shipment_import_service._generate_long_tail_fallback_snapshot``):

1. ``SkuMaster.metadata_json.long_tail_category`` — explicit human override
2. keyword match against ``SkuMaster.spec_text + product_name + sku_code``
   (case-insensitive substring; highest ``priority`` wins, ties → smallest
   id for determinism)
3. strategy with ``category='default'`` if present
4. legacy ``settings.long_tail_cogs_rate`` (= 0.55 default)

Audit: every save bumps ``metadata.history`` (kept to last 20 entries) with
old/new rate + keywords + actor + timestamp. Historical BomSnapshots already
record the actual rate used in trace_json, so changing this table never
rewrites history (reports stay stable).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple  # noqa: F401  (Tuple used in match_keyword_strategy)

from sqlalchemy import func  # noqa: F401
from sqlalchemy.orm import Session

from .. import models
from ...config import settings


# How many history entries to keep per strategy (audit trail in metadata.history).
_MAX_HISTORY = 20


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _s(v: Any) -> str:
    return str(v if v is not None else "").strip()


def _norm_keywords(raw: Any) -> List[str]:
    """Normalize keywords payload into a deduplicated list of trimmed strings.

    Accepts list / tuple / comma-separated string. Empty strings are dropped.
    Casing is preserved (matching is case-insensitive at compare time).
    """
    out: List[str] = []
    if raw is None:
        return out
    items: List[Any]
    if isinstance(raw, (list, tuple)):
        items = list(raw)
    else:
        items = [piece for piece in str(raw).split(",")]
    seen: set[str] = set()
    for item in items:
        s = _s(item)
        if not s:
            continue
        key = s.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out


def _validate_rate(rate: Any) -> float:
    """Coerce a rate value to a float in [0, 1]. Raises ValueError otherwise."""
    if rate is None or rate == "":
        raise ValueError("rate is required")
    try:
        v = float(rate)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"rate must be a number, got: {rate!r}") from exc
    if not (0.0 <= v <= 1.0):
        raise ValueError(f"rate must be between 0 and 1 (got {v})")
    return v


def _strategy_to_dict(s: models.LongTailCogsRateStrategy) -> Dict[str, Any]:
    """Hand-rolled (so router can avoid pulling Pydantic schemas if needed)."""
    return {
        "id": s.id,
        "category": s.category,
        "rate": float(s.rate) if s.rate is not None else 0.0,
        "keywords": list(s.keywords_json or []),
        "priority": int(s.priority or 0),
        "enabled": bool(s.enabled),
        "note": s.note,
        "metadata": dict(s.metadata_json or {}),
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
        # v1.3 Cost Rate Hub fields (Migration 0038)
        "rate_type": getattr(s, "rate_type", None) or "cogs",
        "scope_type": getattr(s, "scope_type", None) or "category",
        "scope_id": getattr(s, "scope_id", None),
        "rate_basis": getattr(s, "rate_basis", None) or "pct_of_revenue",
        "source": getattr(s, "source", None) or "manual",
        "effective_from": s.effective_from.isoformat() if getattr(s, "effective_from", None) else None,
        "effective_to": s.effective_to.isoformat() if getattr(s, "effective_to", None) else None,
        "data_quality": getattr(s, "data_quality", None),
        "cost_center_id": getattr(s, "cost_center_id", None),
        "legal_entity_id": getattr(s, "legal_entity_id", None),
        "production_unit_id": getattr(s, "production_unit_id", None),
    }


def _push_history(
    strategy: models.LongTailCogsRateStrategy,
    *,
    actor: Optional[str],
    before: Optional[Dict[str, Any]],
    note: Optional[str] = None,
) -> None:
    meta = dict(strategy.metadata_json or {})
    history = list(meta.get("history") or [])
    history.append(
        {
            "at": _utcnow().isoformat(),
            "by": actor or "anonymous",
            "before": before,
            "after": {
                "rate": float(strategy.rate) if strategy.rate is not None else None,
                "keywords": list(strategy.keywords_json or []),
                "priority": int(strategy.priority or 0),
                "enabled": bool(strategy.enabled),
                "note": strategy.note,
            },
            "change_note": note,
        }
    )
    if len(history) > _MAX_HISTORY:
        history = history[-_MAX_HISTORY:]
    meta["history"] = history
    strategy.metadata_json = meta


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def list_strategies(
    db: Session,
    *,
    include_archived: bool = False,
    rate_type: Optional[str] = "cogs",
) -> List[models.LongTailCogsRateStrategy]:
    """List rate strategies.

    ``rate_type`` defaults to ``'cogs'`` for backwards compatibility with
    the legacy long-tail UI (it must keep seeing only its own rows). Pass
    ``rate_type=None`` (or ``'all'``) to bypass the filter and return rows
    of every type — useful for Hub admin pages.
    """
    q = db.query(models.LongTailCogsRateStrategy)
    if not include_archived:
        q = q.filter(models.LongTailCogsRateStrategy.is_archived.is_(False))
    if rate_type and rate_type != "all":
        q = q.filter(models.LongTailCogsRateStrategy.rate_type == rate_type)
    return (
        q.order_by(
            models.LongTailCogsRateStrategy.priority.desc(),
            models.LongTailCogsRateStrategy.category.asc(),
        ).all()
    )


def get_strategy(
    db: Session, *, strategy_id: str
) -> Optional[models.LongTailCogsRateStrategy]:
    return (
        db.query(models.LongTailCogsRateStrategy)
        .filter(models.LongTailCogsRateStrategy.id == strategy_id)
        .first()
    )


def get_by_category(
    db: Session, *, category: str
) -> Optional[models.LongTailCogsRateStrategy]:
    cat = _s(category)
    if not cat:
        return None
    return (
        db.query(models.LongTailCogsRateStrategy)
        .filter(models.LongTailCogsRateStrategy.category == cat)
        .first()
    )


_HUB_RATE_TYPES = {"labor_per_minute", "labor_per_piece", "labor_per_sqm", "overhead_rate"}


def _parse_dt(raw: Any) -> Optional[datetime]:
    """Best-effort ISO-8601 parser used by Hub fields. Returns naive UTC."""
    if raw in (None, ""):
        return None
    if isinstance(raw, datetime):
        return raw.replace(tzinfo=None) if raw.tzinfo is None else raw.astimezone(timezone.utc).replace(tzinfo=None)
    try:
        s = str(raw).strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            return dt
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid datetime: {raw!r}") from exc


def _synthesize_category_for_hub(rate_type: str, scope_type: str, scope_id: Optional[str]) -> str:
    """For non-cogs rate types we synthesize a unique 'category' string so
    the existing UNIQUE(category) constraint serves as a 1-row-per-scope
    guard. Users never see this synthesized name — the UI shows
    rate_type/scope_type/scope_id directly.
    """
    return f"__{rate_type}__{scope_type}__{(scope_id or 'global').lower()}"


def _apply_hub_fields(strategy: models.LongTailCogsRateStrategy, payload: Dict[str, Any]) -> None:
    """Copy v1.3 Hub-specific fields from payload onto the row, with
    sensible defaults that keep legacy long-tail rows backwards compatible.
    """
    if "rate_type" in payload and payload["rate_type"] is not None:
        strategy.rate_type = _s(payload["rate_type"]) or "cogs"
    if "scope_type" in payload and payload["scope_type"] is not None:
        strategy.scope_type = _s(payload["scope_type"]) or "category"
    if "scope_id" in payload:
        strategy.scope_id = _s(payload["scope_id"]) or None
    if "rate_basis" in payload and payload["rate_basis"] is not None:
        strategy.rate_basis = _s(payload["rate_basis"]) or "pct_of_revenue"
    if "source" in payload and payload["source"] is not None:
        strategy.source = _s(payload["source"]) or "manual"
    if "effective_from" in payload:
        strategy.effective_from = _parse_dt(payload["effective_from"])
    if "effective_to" in payload:
        strategy.effective_to = _parse_dt(payload["effective_to"])
    if "data_quality" in payload:
        dq = _s(payload["data_quality"]) or None
        if dq is not None and dq not in ("green", "yellow", "red"):
            raise ValueError(f"data_quality must be green|yellow|red (got {dq!r})")
        strategy.data_quality = dq
    if "cost_center_id" in payload:
        strategy.cost_center_id = _s(payload["cost_center_id"]) or None
    if "legal_entity_id" in payload:
        strategy.legal_entity_id = _s(payload["legal_entity_id"]) or None
    if "production_unit_id" in payload:
        strategy.production_unit_id = _s(payload["production_unit_id"]) or None


def create_strategy(
    db: Session,
    *,
    payload: Dict[str, Any],
    actor: Optional[str] = None,
) -> models.LongTailCogsRateStrategy:
    """Create a new strategy / rate row.

    Two flavours, switched by ``payload['rate_type']``:

    1. ``rate_type`` is None / ``'cogs'`` — legacy long-tail behaviour.
       Requires ``category`` (unique, human-meaningful name like '画框').
       If an archived row with the same category exists, it is revived
       instead of erroring (avoids unique-constraint deadlock).

    2. ``rate_type`` is one of the Hub types (``overhead_rate`` /
       ``labor_per_*``) — Hub MVP behaviour. Requires
       ``scope_type`` (and ``scope_id`` unless ``scope_type='global'``).
       The ``category`` field is synthesized from
       ``__<rate_type>__<scope_type>__<scope_id>`` so the existing
       UNIQUE(category) constraint becomes a "one row per scope" guard.

    Raises ``ValueError`` when required fields are missing or an active
    duplicate exists.
    """
    rate_type_raw = _s(payload.get("rate_type")) or "cogs"
    is_hub = rate_type_raw in _HUB_RATE_TYPES

    if is_hub:
        scope_type = _s(payload.get("scope_type")) or "global"
        scope_id = _s(payload.get("scope_id")) or None
        if scope_type != "global" and not scope_id:
            raise ValueError(f"scope_id is required when scope_type={scope_type!r}")
        category = _s(payload.get("category")) or _synthesize_category_for_hub(
            rate_type_raw, scope_type, scope_id
        )
    else:
        category = _s(payload.get("category"))
        if not category:
            raise ValueError("category is required")

    rate = _validate_rate(payload.get("rate"))
    keywords = _norm_keywords(payload.get("keywords"))
    priority = int(payload.get("priority") or 100)
    enabled = bool(payload.get("enabled", True))
    note = _s(payload.get("note")) or None

    existing = get_by_category(db, category=category)
    if existing is not None:
        if not existing.is_archived:
            raise ValueError(f"category already exists: {category}")
        before = {
            "rate": float(existing.rate) if existing.rate is not None else None,
            "keywords": list(existing.keywords_json or []),
            "priority": int(existing.priority or 0),
            "enabled": bool(existing.enabled),
            "note": existing.note,
            "is_archived": True,
        }
        existing.rate = Decimal(str(rate))
        existing.keywords_json = keywords
        existing.priority = priority
        existing.enabled = enabled
        existing.note = note
        existing.is_archived = False
        _apply_hub_fields(existing, payload)
        _push_history(existing, actor=actor, before=before, note="revived")
        db.commit()
        db.refresh(existing)
        return existing

    strategy = models.LongTailCogsRateStrategy(
        category=category,
        rate=Decimal(str(rate)),
        keywords_json=keywords,
        priority=priority,
        enabled=enabled,
        note=note,
        metadata_json={},
    )
    _apply_hub_fields(strategy, payload)
    if is_hub:
        # Hub rows have stricter defaults than legacy long-tail — make sure
        # the column values reflect the request even when the caller didn't
        # bother setting them explicitly.
        if not getattr(strategy, "rate_type", None):
            strategy.rate_type = rate_type_raw
        if not getattr(strategy, "scope_type", None):
            strategy.scope_type = _s(payload.get("scope_type")) or "global"
        if "scope_id" not in payload:
            strategy.scope_id = _s(payload.get("scope_id")) or None
        if not getattr(strategy, "rate_basis", None) or strategy.rate_basis == "pct_of_revenue":
            # overhead_rate defaults to pct_of_cost; labor types default to per_minute.
            if rate_type_raw == "overhead_rate":
                strategy.rate_basis = _s(payload.get("rate_basis")) or "pct_of_cost"
            elif rate_type_raw == "labor_per_minute":
                strategy.rate_basis = _s(payload.get("rate_basis")) or "per_minute"
            elif rate_type_raw == "labor_per_piece":
                strategy.rate_basis = _s(payload.get("rate_basis")) or "per_piece"
            elif rate_type_raw == "labor_per_sqm":
                strategy.rate_basis = _s(payload.get("rate_basis")) or "per_sqm"
    _push_history(strategy, actor=actor, before=None, note="created")
    db.add(strategy)
    db.commit()
    db.refresh(strategy)
    return strategy


def update_strategy(
    db: Session,
    *,
    strategy_id: str,
    patch: Dict[str, Any],
    actor: Optional[str] = None,
) -> models.LongTailCogsRateStrategy:
    strategy = get_strategy(db, strategy_id=strategy_id)
    if strategy is None:
        raise ValueError(f"strategy not found: {strategy_id}")
    before = {
        "rate": float(strategy.rate) if strategy.rate is not None else None,
        "keywords": list(strategy.keywords_json or []),
        "priority": int(strategy.priority or 0),
        "enabled": bool(strategy.enabled),
        "note": strategy.note,
    }
    if "category" in patch and patch["category"] is not None:
        new_cat = _s(patch["category"])
        if not new_cat:
            raise ValueError("category cannot be empty")
        if new_cat != strategy.category:
            existing = get_by_category(db, category=new_cat)
            if existing is not None and existing.id != strategy.id:
                raise ValueError(f"category already exists: {new_cat}")
            strategy.category = new_cat
    if "rate" in patch and patch["rate"] is not None:
        strategy.rate = Decimal(str(_validate_rate(patch["rate"])))
    if "keywords" in patch and patch["keywords"] is not None:
        strategy.keywords_json = _norm_keywords(patch["keywords"])
    if "priority" in patch and patch["priority"] is not None:
        strategy.priority = int(patch["priority"])
    if "enabled" in patch and patch["enabled"] is not None:
        strategy.enabled = bool(patch["enabled"])
    if "note" in patch:
        strategy.note = _s(patch["note"]) or None
    _apply_hub_fields(strategy, patch)
    _push_history(strategy, actor=actor, before=before, note="updated")
    db.commit()
    db.refresh(strategy)
    return strategy


def delete_strategy(
    db: Session,
    *,
    strategy_id: str,
    actor: Optional[str] = None,
    hard: bool = False,
) -> None:
    """Soft-delete by default (sets is_archived=True). Use ``hard=True`` to
    actually drop the row (admin-only; not exposed via UI).
    """
    strategy = get_strategy(db, strategy_id=strategy_id)
    if strategy is None:
        return
    if hard:
        db.delete(strategy)
        db.commit()
        return
    before = {
        "rate": float(strategy.rate) if strategy.rate is not None else None,
        "keywords": list(strategy.keywords_json or []),
        "priority": int(strategy.priority or 0),
        "enabled": bool(strategy.enabled),
        "note": strategy.note,
    }
    strategy.is_archived = True
    strategy.enabled = False
    _push_history(strategy, actor=actor, before=before, note="archived")
    db.commit()


# ---------------------------------------------------------------------------
# Resolution (called from shipment_import_service)
# ---------------------------------------------------------------------------


@dataclass
class ResolvedRate:
    """Outcome of resolving the long-tail cogs rate for one SKU.

    ``source`` describes which step in the chain produced the rate:
    - ``manual``        = SkuMaster.metadata_json.long_tail_category matched
    - ``keyword``       = a strategy's keyword matched spec_text/product_name
    - ``default_strategy`` = strategy with category='default' was used
    - ``global_setting``= no strategy hit; fell back to settings.long_tail_cogs_rate

    ``strategy_id`` / ``category`` are populated when source is one of the
    strategy-driven branches; both ``None`` when source='global_setting'.
    """

    rate: float
    source: str
    strategy_id: Optional[str]
    category: Optional[str]
    matched_keyword: Optional[str]


def _global_rate() -> float:
    try:
        return float(getattr(settings, "long_tail_cogs_rate", 0.55) or 0.55)
    except Exception:  # noqa: BLE001
        return 0.55


def _haystack_for(sku: Optional[models.SkuMaster]) -> str:
    if sku is None:
        return ""
    parts = [
        sku.spec_text or "",
        sku.product_name or "",
        sku.product_code or "",
        sku.erp_sku_barcode or "",
    ]
    return " ".join(parts).lower()


def match_keyword_strategy(
    enabled_strategies: List[models.LongTailCogsRateStrategy],
    haystack_lower: str,
) -> Optional[Tuple[models.LongTailCogsRateStrategy, str]]:
    """Pure keyword match: return ``(strategy, matched_keyword)`` or ``None``.

    Skips ``category='default'``. Iterates strategies in (priority desc, id
    asc) order and returns the first one whose any keyword appears in the
    haystack as a case-insensitive substring. ``haystack_lower`` MUST be
    pre-lowercased by the caller (we don't re-lower per call to avoid
    O(N×K) cost on the hot scan path).
    """
    if not haystack_lower:
        return None
    for s in sorted(enabled_strategies, key=lambda x: (-int(x.priority or 0), x.id)):
        if (s.category or "").strip().lower() == "default":
            continue
        for kw in s.keywords_json or []:
            kw_l = (kw or "").strip().lower()
            if kw_l and kw_l in haystack_lower:
                return s, kw
    return None


def _explicit_category(sku: Optional[models.SkuMaster]) -> Optional[str]:
    if sku is None:
        return None
    meta = sku.metadata_json or {}
    cat = meta.get("long_tail_category")
    if not cat:
        # Backward-compat: governance.long_tail_category
        gov = meta.get("governance") if isinstance(meta, dict) else None
        if isinstance(gov, dict):
            cat = gov.get("long_tail_category")
    return _s(cat) or None


def resolve_rate_for_sku(
    db: Session,
    *,
    sku: Optional[models.SkuMaster],
    sku_code: Optional[str] = None,
) -> ResolvedRate:
    """Pick the best rate for a long-tail SKU. See module docstring for order.

    Always returns a ResolvedRate; never raises. Callers should record
    ``rate`` + ``source`` + ``strategy_id`` + ``category`` in trace_json so
    historical snapshots stay auditable even if the strategy table changes.
    """
    strategies = list_strategies(db, include_archived=False)
    enabled = [s for s in strategies if s.enabled]

    # Step 1: explicit human override.
    explicit = _explicit_category(sku)
    if explicit:
        for s in enabled:
            if s.category.lower() == explicit.lower():
                return ResolvedRate(
                    rate=float(s.rate or 0.0),
                    source="manual",
                    strategy_id=s.id,
                    category=s.category,
                    matched_keyword=None,
                )
        # explicit category set but no enabled strategy -- still record it as a
        # manual hint so reports can show a warning, but use global rate.

    # Step 2: keyword match (excluding 'default' so it's a real fallback).
    haystack = _haystack_for(sku)
    if not haystack and sku_code:
        haystack = sku_code.lower()
    hit = match_keyword_strategy(enabled, haystack)
    if hit is not None:
        s, kw = hit
        return ResolvedRate(
            rate=float(s.rate or 0.0),
            source="keyword",
            strategy_id=s.id,
            category=s.category,
            matched_keyword=kw,
        )

    # Step 3: 'default' strategy.
    for s in enabled:
        if (s.category or "").strip().lower() == "default":
            return ResolvedRate(
                rate=float(s.rate or 0.0),
                source="default_strategy",
                strategy_id=s.id,
                category=s.category,
                matched_keyword=None,
            )

    # Step 4: legacy global setting.
    return ResolvedRate(
        rate=_global_rate(),
        source="global_setting",
        strategy_id=None,
        category=None,
        matched_keyword=None,
    )


# ---------------------------------------------------------------------------
# Cost Rate Hub v1.3 §5.1 — overhead_rate 4-layer resolver
# ---------------------------------------------------------------------------


@dataclass
class ResolvedOverheadRate:
    """Outcome of resolving an overhead_rate via the Cost Rate Hub.

    ``hit_layer`` is one of:
    - ``model``         — a row matched ``scope_type='model'``
    - ``category``      — a row matched ``scope_type='category'``
    - ``cost_center``   — a row matched ``scope_type='cost_center'``
    - ``global``        — a row matched ``scope_type='global'``
    - ``hard_fallback`` — no row matched; caller should treat as last-resort 0.30
    """

    rate: Decimal
    hit_layer: str
    scope_type: Optional[str]
    scope_id: Optional[str]
    source: Optional[str]
    data_quality: Optional[str]
    strategy_id: Optional[str]


_HARD_FALLBACK_OVERHEAD = Decimal("0.30")


def resolve_overhead_rate(
    db: Session,
    *,
    model_id: Optional[str] = None,
    category: Optional[str] = None,
    cost_center_id: Optional[str] = None,
    as_of: Optional[datetime] = None,
) -> ResolvedOverheadRate:
    """Cost Rate Hub v1.3 §5.1 4-layer resolve for overhead_rate.

    Walks priority chain ``model > category > cost_center > global``. Each
    layer queries ``cost_rate_master`` for an enabled, non-archived row of
    ``rate_type='overhead_rate'`` with the matching ``scope_type`` /
    ``scope_id``. ``effective_from`` (if set) must be on/before ``as_of``
    (defaults to now); ``effective_to`` (if set) must be after ``as_of``.

    Returns a ``ResolvedOverheadRate`` whose ``hit_layer`` is one of
    ``model | category | cost_center | global | hard_fallback``. Hard
    fallback returns 0.30 with ``data_quality='red'`` so callers (and the
    UI badge) know the value is the last-resort default.
    """
    now = (as_of or _utcnow()).replace(tzinfo=None) if as_of and getattr(as_of, "tzinfo", None) else (as_of or datetime.utcnow())

    chain: List[Tuple[str, Optional[str]]] = [
        ("model", _s(model_id) or None),
        ("category", _s(category) or None),
        ("cost_center", _s(cost_center_id) or None),
        ("global", None),
    ]

    for scope_type, scope_id in chain:
        if scope_type != "global" and not scope_id:
            continue
        q = db.query(models.LongTailCogsRateStrategy).filter(
            models.LongTailCogsRateStrategy.rate_type == "overhead_rate",
            models.LongTailCogsRateStrategy.scope_type == scope_type,
            models.LongTailCogsRateStrategy.enabled.is_(True),
            models.LongTailCogsRateStrategy.is_archived.is_(False),
        )
        if scope_type == "global":
            # Treat "any scope_id" as a match (some global rows may have
            # an explicit NULL/empty scope_id; some may have leftovers).
            q = q.filter(
                (models.LongTailCogsRateStrategy.scope_id.is_(None))
                | (models.LongTailCogsRateStrategy.scope_id == "")
            )
        else:
            q = q.filter(models.LongTailCogsRateStrategy.scope_id == scope_id)

        # Prefer the most recently effective row (NULL effective_from sorts
        # last so explicitly dated overrides win over "always-on" defaults).
        rows = (
            q.order_by(
                models.LongTailCogsRateStrategy.effective_from.desc(),
                models.LongTailCogsRateStrategy.priority.desc(),
                models.LongTailCogsRateStrategy.created_at.desc(),
            ).all()
        )
        for row in rows:
            ef_from = getattr(row, "effective_from", None)
            ef_to = getattr(row, "effective_to", None)
            if ef_from is not None and ef_from > now:
                continue
            if ef_to is not None and ef_to <= now:
                continue
            return ResolvedOverheadRate(
                rate=Decimal(str(row.rate)) if row.rate is not None else _HARD_FALLBACK_OVERHEAD,
                hit_layer=scope_type,
                scope_type=scope_type,
                scope_id=scope_id,
                source=getattr(row, "source", None),
                data_quality=getattr(row, "data_quality", None),
                strategy_id=row.id,
            )

    return ResolvedOverheadRate(
        rate=_HARD_FALLBACK_OVERHEAD,
        hit_layer="hard_fallback",
        scope_type=None,
        scope_id=None,
        source=None,
        data_quality="red",
        strategy_id=None,
    )
