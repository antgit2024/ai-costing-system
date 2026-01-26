from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Literal, Optional, Tuple

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from .. import models
from . import bom_generation_service, product_model_service


def _utc_date(dt: datetime) -> date:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).date()


def _group_time_expr(db: Session, column, group_by: Literal["day", "month"]):
    dialect = getattr(getattr(db.get_bind(), "dialect", None), "name", "")
    if dialect == "postgresql":
        if group_by == "month":
            return func.date_trunc("month", column)
        return func.date_trunc("day", column)
    # sqlite / mysql fallback
    if group_by == "month":
        return func.strftime("%Y-%m-01", column)
    return func.date(column)


def returns_rate_by_sku(
    db: Session,
    *,
    start: datetime,
    end: datetime,
    group_by: Literal["day", "month"] = "day",
    channel: Optional[str] = None,
    sku_code: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Return-rate analytics (2025 analysis mode):
    - Attribute returns to the shipment completion period by strong keys:
      order_no + product_link_id + sku_code.
    - Only matched after-sales lines contribute to returned_qty/refund_amount.
    """
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)

    period_expr = _group_time_expr(db, models.ShipmentLine.completed_at, group_by).label("period")

    ship_q = db.query(
        period_expr,
        models.ShipmentLine.channel.label("channel"),
        models.ShipmentLine.sku_code.label("sku_code"),
        func.coalesce(func.sum(models.ShipmentLine.qty), 0).label("shipped_qty"),
        func.coalesce(func.sum(models.ShipmentLine.revenue_amount), 0).label("shipped_amount"),
    ).filter(
        models.ShipmentLine.completed_at.isnot(None),
        models.ShipmentLine.completed_at >= start,
        models.ShipmentLine.completed_at < end,
        models.ShipmentLine.is_archived.is_(False),
    )
    if channel:
        ship_q = ship_q.filter(models.ShipmentLine.channel == channel)
    if sku_code:
        ship_q = ship_q.filter(models.ShipmentLine.sku_code == sku_code)

    ship_q = ship_q.group_by(period_expr, models.ShipmentLine.channel, models.ShipmentLine.sku_code)
    ship_rows = ship_q.all()

    # returns matched to shipments in the period
    ret_q = db.query(
        period_expr,
        models.ShipmentLine.channel.label("channel"),
        models.ShipmentLine.sku_code.label("sku_code"),
        func.coalesce(func.sum(models.AfterSalesLine.return_qty), 0).label("returned_qty"),
        func.coalesce(func.sum(models.AfterSalesLine.refund_amount), 0).label("refund_amount"),
    ).join(
        models.AfterSalesLine,
        and_(
            models.AfterSalesLine.order_no.isnot(None),
            models.AfterSalesLine.product_link_id.isnot(None),
            models.AfterSalesLine.sku_code.isnot(None),
            models.ShipmentLine.order_no == models.AfterSalesLine.order_no,
            models.ShipmentLine.product_link_id == models.AfterSalesLine.product_link_id,
            models.ShipmentLine.sku_code == models.AfterSalesLine.sku_code,
        ),
    ).filter(
        models.ShipmentLine.completed_at.isnot(None),
        models.ShipmentLine.completed_at >= start,
        models.ShipmentLine.completed_at < end,
        models.ShipmentLine.is_archived.is_(False),
        models.AfterSalesLine.is_archived.is_(False),
    )
    if channel:
        ret_q = ret_q.filter(models.ShipmentLine.channel == channel)
    if sku_code:
        ret_q = ret_q.filter(models.ShipmentLine.sku_code == sku_code)
    ret_q = ret_q.group_by(period_expr, models.ShipmentLine.channel, models.ShipmentLine.sku_code)
    ret_rows = ret_q.all()

    ret_map: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    for r in ret_rows:
        key = (str(r.period), str(r.channel or ""), str(r.sku_code or ""))
        ret_map[key] = {
            "returned_qty": r.returned_qty,
            "refund_amount": r.refund_amount,
        }

    items: List[Dict[str, Any]] = []
    for r in ship_rows:
        key = (str(r.period), str(r.channel or ""), str(r.sku_code or ""))
        ret = ret_map.get(key) or {"returned_qty": Decimal("0"), "refund_amount": Decimal("0")}
        shipped_qty = Decimal(str(r.shipped_qty or 0))
        shipped_amount = Decimal(str(r.shipped_amount or 0))
        returned_qty = Decimal(str(ret["returned_qty"] or 0))
        refund_amount = Decimal(str(ret["refund_amount"] or 0))
        return_rate = (returned_qty / shipped_qty) if shipped_qty > 0 else None
        refund_rate = (refund_amount / shipped_amount) if shipped_amount > 0 else None

        items.append(
            {
                "period": str(r.period),
                "channel": r.channel,
                "sku_code": r.sku_code,
                "shipped_qty": shipped_qty,
                "returned_qty": returned_qty,
                "return_rate": return_rate,
                "shipped_amount": shipped_amount,
                "refund_amount": refund_amount,
                "refund_rate": refund_rate,
            }
        )

    # unmatched returns within the same time window (for data quality)
    unmatched_q = db.query(func.count(models.AfterSalesLine.id)).filter(
        models.AfterSalesLine.is_archived.is_(False),
        models.AfterSalesLine.applied_at.isnot(None),
        models.AfterSalesLine.applied_at >= start,
        models.AfterSalesLine.applied_at < end,
        func.coalesce(models.AfterSalesLine.order_no, "") == "",
    )
    unmatched_returns = int(unmatched_q.scalar() or 0)

    return {
        "group_by": group_by,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "items": items,
        "unmatched_returns_missing_order_no": unmatched_returns,
    }


def returns_rate_by_channel(
    db: Session,
    *,
    start: datetime,
    end: datetime,
    group_by: Literal["day", "month"] = "day",
    channel: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Returns-rate aggregated by channel.
    - Shipment baseline uses shipment_lines within [start, end) by completed_at.
    - Returns are attributed to shipment period via strong keys:
      order_no + product_link_id + sku_code.
    """
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)

    period_expr = _group_time_expr(db, models.ShipmentLine.completed_at, group_by).label("period")

    ship_q = db.query(
        period_expr,
        models.ShipmentLine.channel.label("channel"),
        func.coalesce(func.sum(models.ShipmentLine.qty), 0).label("shipped_qty"),
        func.coalesce(func.sum(models.ShipmentLine.revenue_amount), 0).label("shipped_amount"),
        func.count(models.ShipmentLine.id).label("shipment_lines_total"),
    ).filter(
        models.ShipmentLine.completed_at.isnot(None),
        models.ShipmentLine.completed_at >= start,
        models.ShipmentLine.completed_at < end,
        models.ShipmentLine.is_archived.is_(False),
    )
    if channel:
        ship_q = ship_q.filter(models.ShipmentLine.channel == channel)
    ship_q = ship_q.group_by(period_expr, models.ShipmentLine.channel)
    ship_rows = ship_q.all()

    ret_q = db.query(
        period_expr,
        models.ShipmentLine.channel.label("channel"),
        func.coalesce(func.sum(models.AfterSalesLine.return_qty), 0).label("returned_qty"),
        func.coalesce(func.sum(models.AfterSalesLine.refund_amount), 0).label("refund_amount"),
    ).join(
        models.AfterSalesLine,
        and_(
            models.AfterSalesLine.order_no.isnot(None),
            models.AfterSalesLine.product_link_id.isnot(None),
            models.AfterSalesLine.sku_code.isnot(None),
            models.ShipmentLine.order_no == models.AfterSalesLine.order_no,
            models.ShipmentLine.product_link_id == models.AfterSalesLine.product_link_id,
            models.ShipmentLine.sku_code == models.AfterSalesLine.sku_code,
        ),
    ).filter(
        models.ShipmentLine.completed_at.isnot(None),
        models.ShipmentLine.completed_at >= start,
        models.ShipmentLine.completed_at < end,
        models.ShipmentLine.is_archived.is_(False),
        models.AfterSalesLine.is_archived.is_(False),
    )
    if channel:
        ret_q = ret_q.filter(models.ShipmentLine.channel == channel)
    ret_q = ret_q.group_by(period_expr, models.ShipmentLine.channel)
    ret_rows = ret_q.all()

    ret_map: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for r in ret_rows:
        ret_map[(str(r.period), str(r.channel or ""))] = {
            "returned_qty": r.returned_qty,
            "refund_amount": r.refund_amount,
        }

    items: List[Dict[str, Any]] = []
    for r in ship_rows:
        key = (str(r.period), str(r.channel or ""))
        ret = ret_map.get(key) or {"returned_qty": Decimal("0"), "refund_amount": Decimal("0")}
        shipped_qty = Decimal(str(r.shipped_qty or 0))
        shipped_amount = Decimal(str(r.shipped_amount or 0))
        returned_qty = Decimal(str(ret["returned_qty"] or 0))
        refund_amount = Decimal(str(ret["refund_amount"] or 0))
        return_rate = (returned_qty / shipped_qty) if shipped_qty > 0 else None
        refund_rate = (refund_amount / shipped_amount) if shipped_amount > 0 else None
        items.append(
            {
                "period": str(r.period),
                "channel": r.channel,
                "shipped_qty": shipped_qty,
                "returned_qty": returned_qty,
                "return_rate": return_rate,
                "shipped_amount": shipped_amount,
                "refund_amount": refund_amount,
                "refund_rate": refund_rate,
                "shipment_lines_total": int(r.shipment_lines_total or 0),
            }
        )

    unmatched_q = db.query(func.count(models.AfterSalesLine.id)).filter(
        models.AfterSalesLine.is_archived.is_(False),
        models.AfterSalesLine.applied_at.isnot(None),
        models.AfterSalesLine.applied_at >= start,
        models.AfterSalesLine.applied_at < end,
        func.coalesce(models.AfterSalesLine.order_no, "") == "",
    )
    unmatched_returns = int(unmatched_q.scalar() or 0)

    return {
        "group_by": group_by,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "items": items,
        "unmatched_returns_missing_order_no": unmatched_returns,
    }


def _d(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception:  # noqa: BLE001
        return Decimal("0")


def _extract_total_cost_from_trace(trace_json: Any) -> Tuple[Optional[Decimal], str]:
    """
    Extract total cost from a bom_snapshot-like trace JSON.
    Returns (cost, status): status in {"costed","missing_costing"}.
    """
    trace = (trace_json or {}) if isinstance(trace_json, dict) else {}
    costing = (trace.get("costing") or {}) if isinstance(trace.get("costing"), dict) else {}
    total_cost = costing.get("total_cost")
    if total_cost in (None, ""):
        total_cost = _d(costing.get("material_cost_total")) + _d(costing.get("process_cost_total")) + _d(costing.get("overhead_cost"))
    cost = _d(total_cost)
    if cost == 0 and total_cost in (None, "", 0):
        return None, "missing_costing"
    return cost, "costed"


def _extract_cost_breakdown_from_trace(trace_json: Any) -> Tuple[Optional[Decimal], Decimal, Decimal, Decimal, str]:
    """
    Extract (total, material, process, overhead, status) from a bom_snapshot-like trace JSON.
    status in {"costed","missing_costing"}.
    """
    trace = (trace_json or {}) if isinstance(trace_json, dict) else {}
    costing = (trace.get("costing") or {}) if isinstance(trace.get("costing"), dict) else {}

    material = costing.get("material_cost_total")
    process = costing.get("process_cost_total")
    overhead = costing.get("overhead_cost")
    total_cost = costing.get("total_cost")

    m = _d(material)
    p = _d(process)
    o = _d(overhead)

    if total_cost in (None, ""):
        total_cost = m + p + o
    total = _d(total_cost)

    if total == 0 and (costing.get("total_cost") in (None, "", 0)) and (material in (None, "")) and (process in (None, "")) and (overhead in (None, "")):
        return None, Decimal("0"), Decimal("0"), Decimal("0"), "missing_costing"
    return total, m, p, o, "costed"


def _period_key(dt: datetime, group_by: Literal["day", "month"]) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc)
    if group_by == "month":
        return f"{dt.year:04d}-{dt.month:02d}-01"
    return dt.date().isoformat()


def profit_by_sku(
    db: Session,
    *,
    start: datetime,
    end: datetime,
    group_by: Literal["day", "month"] = "month",
    channel: Optional[str] = None,
    sku_code: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Profit analytics by SKU:
    - Revenue/qty baseline uses ALL shipment_lines within [start, end) by completed_at.
    - Cost uses shipment_costing_results when present (2025/2026 unified). For legacy data, falls back to latest bom_snapshot trace.
    - Refunds (returns) are attributed to shipment period via strong join (order_no+product_link_id+sku_code).
    """
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)

    # Revenue baseline: all shipments (even those without BOM snapshots)
    ship_q = db.query(models.ShipmentLine).filter(
        models.ShipmentLine.completed_at.isnot(None),
        models.ShipmentLine.completed_at >= start,
        models.ShipmentLine.completed_at < end,
        models.ShipmentLine.is_archived.is_(False),
    )
    if channel:
        ship_q = ship_q.filter(models.ShipmentLine.channel == channel)
    if sku_code:
        ship_q = ship_q.filter(models.ShipmentLine.sku_code == sku_code)

    total_ship_lines = ship_q.count()

    # Latest snapshot per shipment_line_id (legacy fallback)
    snap_sq = (
        db.query(
            models.BomSnapshot.id.label("bom_snapshot_id"),
            models.BomSnapshot.shipment_line_id.label("shipment_line_id"),
            models.BomSnapshot.model_version_id.label("model_version_id"),
            models.BomSnapshot.trace_json.label("trace_json"),
            models.BomSnapshot.created_at.label("created_at"),
        )
        .filter(models.BomSnapshot.shipment_line_id.isnot(None))
        .order_by(models.BomSnapshot.shipment_line_id.asc(), models.BomSnapshot.created_at.desc())
        .distinct(models.BomSnapshot.shipment_line_id)
        .subquery()
    )

    cost_q = (
        db.query(
            models.ShipmentLine,
            models.ShipmentCostingResult,
            snap_sq.c.bom_snapshot_id,
            snap_sq.c.model_version_id,
            snap_sq.c.trace_json,
        )
        .outerjoin(models.ShipmentCostingResult, models.ShipmentLine.id == models.ShipmentCostingResult.shipment_line_id)
        .outerjoin(snap_sq, models.ShipmentLine.id == snap_sq.c.shipment_line_id)
        .filter(
            models.ShipmentLine.completed_at.isnot(None),
            models.ShipmentLine.completed_at >= start,
            models.ShipmentLine.completed_at < end,
            models.ShipmentLine.is_archived.is_(False),
            or_(models.ShipmentCostingResult.shipment_line_id.isnot(None), snap_sq.c.bom_snapshot_id.isnot(None)),
        )
    )
    if channel:
        cost_q = cost_q.filter(models.ShipmentLine.channel == channel)
    if sku_code:
        cost_q = cost_q.filter(models.ShipmentLine.sku_code == sku_code)
    cost_rows = cost_q.all()

    # Refund aggregation (same keying as returns-rate)
    refund_q = db.query(
        models.ShipmentLine,
        func.coalesce(func.sum(models.AfterSalesLine.refund_amount), 0).label("refund_amount"),
        func.coalesce(func.sum(models.AfterSalesLine.return_qty), 0).label("returned_qty"),
    ).join(
        models.AfterSalesLine,
        and_(
            models.AfterSalesLine.order_no.isnot(None),
            models.AfterSalesLine.product_link_id.isnot(None),
            models.AfterSalesLine.sku_code.isnot(None),
            models.ShipmentLine.order_no == models.AfterSalesLine.order_no,
            models.ShipmentLine.product_link_id == models.AfterSalesLine.product_link_id,
            models.ShipmentLine.sku_code == models.AfterSalesLine.sku_code,
        ),
    ).filter(
        models.ShipmentLine.completed_at.isnot(None),
        models.ShipmentLine.completed_at >= start,
        models.ShipmentLine.completed_at < end,
        models.ShipmentLine.is_archived.is_(False),
        models.AfterSalesLine.is_archived.is_(False),
    )
    if channel:
        refund_q = refund_q.filter(models.ShipmentLine.channel == channel)
    if sku_code:
        refund_q = refund_q.filter(models.ShipmentLine.sku_code == sku_code)
    refund_q = refund_q.group_by(models.ShipmentLine.id)
    refund_rows = refund_q.all()

    refund_by_line: Dict[str, Dict[str, Decimal]] = {}
    for sl, ra, rq in refund_rows:
        refund_by_line[str(sl.id)] = {"refund_amount": _d(ra), "returned_qty": _d(rq)}

    agg: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    missing_cost = 0

    for line, res, _snap_id, _snap_model_version_id, snap_trace_json in cost_rows:
        if not line.completed_at:
            continue
        period = _period_key(line.completed_at, group_by)
        key = (period, str(line.channel or ""), str(line.sku_code or ""))
        bucket = agg.setdefault(
            key,
            {
                "period": period,
                "channel": line.channel,
                "sku_code": line.sku_code,
                "shipped_qty": Decimal("0"),
                "revenue_amount": Decimal("0"),
                "cost_amount": Decimal("0"),
                "refund_amount": Decimal("0"),
                "returned_qty": Decimal("0"),
                "lines_with_bom": 0,
            },
        )

        bucket["lines_with_bom"] += 1
        bucket["shipped_qty"] += _d(line.qty)
        bucket["revenue_amount"] += _d(line.revenue_amount)

        if res is not None:
            total_cost = getattr(res, "cost_total", None)
            if total_cost in (None, ""):
                total_cost = (
                    _d(getattr(res, "cost_material_total", None))
                    + _d(getattr(res, "cost_process_total", None))
                    + _d(getattr(res, "cost_overhead_total", None))
                )
            cost = _d(total_cost)
            if cost == 0 and total_cost in (None, "", 0):
                # If the lightweight result is missing cost (edge/legacy), try to fall back to snapshot trace if present.
                snap_cost, status = _extract_total_cost_from_trace(snap_trace_json)
                if status == "costed":
                    cost = _d(snap_cost)
                else:
                    missing_cost += 1
            bucket["cost_amount"] += cost
        else:
            cost, status = _extract_total_cost_from_trace(snap_trace_json)
            if status == "missing_costing":
                missing_cost += 1
            bucket["cost_amount"] += _d(cost)

        ref = refund_by_line.get(str(line.id))
        if ref:
            bucket["refund_amount"] += ref["refund_amount"]
            bucket["returned_qty"] += ref["returned_qty"]

    items: List[Dict[str, Any]] = []
    for _, b in sorted(agg.items(), key=lambda kv: kv[0]):
        revenue = b["revenue_amount"]
        cost = b["cost_amount"]
        refund = b["refund_amount"]
        gross_profit = revenue - cost
        gross_margin = (gross_profit / revenue) if revenue > 0 else None
        net_revenue = revenue - refund
        net_profit = net_revenue - cost
        net_margin = (net_profit / net_revenue) if net_revenue > 0 else None

        items.append(
            {
                **{k: v for k, v in b.items() if k not in ("lines_with_bom",)},
                "gross_profit": gross_profit,
                "gross_margin": gross_margin,
                "net_revenue": net_revenue,
                "net_profit": net_profit,
                "net_margin": net_margin,
            }
        )

    return {
        "group_by": group_by,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "total_shipment_lines": total_ship_lines,
        "lines_with_bom_snapshots": len(cost_rows),
        "lines_missing_costing": missing_cost,
        "items": items,
        "note": "Profit by SKU uses shipment_lines revenue baseline; cost from shipment_costing_results (coverage tracked). net_profit=(revenue-refund)-cost.",
    }


def profit_by_channel(
    db: Session,
    *,
    start: datetime,
    end: datetime,
    group_by: Literal["day", "month"] = "month",
    channel: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Profit analytics aggregated by channel.
    - Revenue/qty baseline uses ALL shipment_lines within [start, end) by completed_at.
    - Cost uses shipment_costing_results when present; falls back to latest bom_snapshot trace for legacy data.
    - Refunds are attributed to shipment period via strong keys (order_no+product_link_id+sku_code).
    - Coverage is explicit (total shipment lines vs costed lines).
    """
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)

    ship_q = db.query(models.ShipmentLine).filter(
        models.ShipmentLine.completed_at.isnot(None),
        models.ShipmentLine.completed_at >= start,
        models.ShipmentLine.completed_at < end,
        models.ShipmentLine.is_archived.is_(False),
    )
    if channel:
        ship_q = ship_q.filter(models.ShipmentLine.channel == channel)
    total_ship_lines = ship_q.count()
    ship_rows = ship_q.all()

    snap_sq = (
        db.query(
            models.BomSnapshot.id.label("bom_snapshot_id"),
            models.BomSnapshot.shipment_line_id.label("shipment_line_id"),
            models.BomSnapshot.trace_json.label("trace_json"),
            models.BomSnapshot.created_at.label("created_at"),
        )
        .filter(models.BomSnapshot.shipment_line_id.isnot(None))
        .order_by(models.BomSnapshot.shipment_line_id.asc(), models.BomSnapshot.created_at.desc())
        .distinct(models.BomSnapshot.shipment_line_id)
        .subquery()
    )

    cost_q = (
        db.query(
            models.ShipmentLine,
            models.ShipmentCostingResult,
            snap_sq.c.bom_snapshot_id,
            snap_sq.c.trace_json,
        )
        .outerjoin(models.ShipmentCostingResult, models.ShipmentLine.id == models.ShipmentCostingResult.shipment_line_id)
        .outerjoin(snap_sq, models.ShipmentLine.id == snap_sq.c.shipment_line_id)
        .filter(
            models.ShipmentLine.completed_at.isnot(None),
            models.ShipmentLine.completed_at >= start,
            models.ShipmentLine.completed_at < end,
            models.ShipmentLine.is_archived.is_(False),
            or_(models.ShipmentCostingResult.shipment_line_id.isnot(None), snap_sq.c.bom_snapshot_id.isnot(None)),
        )
    )
    if channel:
        cost_q = cost_q.filter(models.ShipmentLine.channel == channel)
    cost_rows = cost_q.all()

    refund_q = db.query(
        models.ShipmentLine.id.label("shipment_line_id"),
        func.coalesce(func.sum(models.AfterSalesLine.refund_amount), 0).label("refund_amount"),
        func.coalesce(func.sum(models.AfterSalesLine.return_qty), 0).label("returned_qty"),
    ).join(
        models.AfterSalesLine,
        and_(
            models.AfterSalesLine.order_no.isnot(None),
            models.AfterSalesLine.product_link_id.isnot(None),
            models.AfterSalesLine.sku_code.isnot(None),
            models.ShipmentLine.order_no == models.AfterSalesLine.order_no,
            models.ShipmentLine.product_link_id == models.AfterSalesLine.product_link_id,
            models.ShipmentLine.sku_code == models.AfterSalesLine.sku_code,
        ),
    ).filter(
        models.ShipmentLine.completed_at.isnot(None),
        models.ShipmentLine.completed_at >= start,
        models.ShipmentLine.completed_at < end,
        models.ShipmentLine.is_archived.is_(False),
        models.AfterSalesLine.is_archived.is_(False),
    )
    if channel:
        refund_q = refund_q.filter(models.ShipmentLine.channel == channel)
    refund_q = refund_q.group_by(models.ShipmentLine.id)
    refund_by_line = {str(r.shipment_line_id): {"refund_amount": _d(r.refund_amount), "returned_qty": _d(r.returned_qty)} for r in refund_q.all()}

    # Baseline aggregation by period+channel (ALL shipment lines)
    base: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for line in ship_rows:
        if not line.completed_at:
            continue
        period = _period_key(line.completed_at, group_by)
        key = (period, str(line.channel or ""))
        bucket = base.setdefault(
            key,
            {
                "period": period,
                "channel": line.channel,
                "shipped_qty": Decimal("0"),
                "revenue_amount": Decimal("0"),
                "refund_amount": Decimal("0"),
                "returned_qty": Decimal("0"),
                "shipment_lines_total": 0,
                "lines_with_bom_snapshots": 0,
                "lines_missing_costing": 0,
                "cost_amount": Decimal("0"),
            },
        )
        bucket["shipment_lines_total"] += 1
        bucket["shipped_qty"] += _d(line.qty)
        bucket["revenue_amount"] += _d(line.revenue_amount)
        ref = refund_by_line.get(str(line.id))
        if ref:
            bucket["refund_amount"] += ref["refund_amount"]
            bucket["returned_qty"] += ref["returned_qty"]

    # Add costs (prefer costing results; fallback to snapshot trace)
    total_missing_costing = 0
    for line, res, _snap_id, snap_trace_json in cost_rows:
        if not line.completed_at:
            continue
        period = _period_key(line.completed_at, group_by)
        key = (period, str(line.channel or ""))
        bucket = base.get(key)
        if not bucket:
            # safety: should not happen, but keep consistent
            bucket = base.setdefault(
                key,
                {
                    "period": period,
                    "channel": line.channel,
                    "shipped_qty": Decimal("0"),
                    "revenue_amount": Decimal("0"),
                    "refund_amount": Decimal("0"),
                    "returned_qty": Decimal("0"),
                    "shipment_lines_total": 0,
                    "lines_with_bom_snapshots": 0,
                    "lines_missing_costing": 0,
                    "cost_amount": Decimal("0"),
                },
            )
        bucket["lines_with_bom_snapshots"] += 1
        if res is not None:
            total_cost = getattr(res, "cost_total", None)
            if total_cost in (None, ""):
                total_cost = (
                    _d(getattr(res, "cost_material_total", None))
                    + _d(getattr(res, "cost_process_total", None))
                    + _d(getattr(res, "cost_overhead_total", None))
                )
            cost = _d(total_cost)
            if cost == 0 and total_cost in (None, "", 0):
                # lightweight result missing cost -> fallback to snapshot trace if possible
                snap_cost, status = _extract_total_cost_from_trace(snap_trace_json)
                if status == "costed":
                    cost = _d(snap_cost)
                else:
                    bucket["lines_missing_costing"] += 1
                    total_missing_costing += 1
            bucket["cost_amount"] += cost
        else:
            cost, status = _extract_total_cost_from_trace(snap_trace_json)
            if status == "missing_costing":
                bucket["lines_missing_costing"] += 1
                total_missing_costing += 1
            bucket["cost_amount"] += _d(cost)

    items: List[Dict[str, Any]] = []
    for _, b in sorted(base.items(), key=lambda kv: kv[0]):
        revenue = b["revenue_amount"]
        cost = b["cost_amount"]
        refund = b["refund_amount"]
        gross_profit = revenue - cost
        gross_margin = (gross_profit / revenue) if revenue > 0 else None
        net_revenue = revenue - refund
        net_profit = net_revenue - cost
        net_margin = (net_profit / net_revenue) if net_revenue > 0 else None
        items.append(
            {
                "period": b["period"],
                "channel": b["channel"],
                "shipped_qty": b["shipped_qty"],
                "revenue_amount": revenue,
                "cost_amount": cost,
                "gross_profit": gross_profit,
                "gross_margin": gross_margin,
                "refund_amount": refund,
                "returned_qty": b["returned_qty"],
                "net_revenue": net_revenue,
                "net_profit": net_profit,
                "net_margin": net_margin,
                "shipment_lines_total": int(b["shipment_lines_total"]),
                "lines_with_bom_snapshots": int(b["lines_with_bom_snapshots"]),
                "lines_missing_costing": int(b["lines_missing_costing"]),
            }
        )

    return {
        "group_by": group_by,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "total_shipment_lines": total_ship_lines,
        "lines_with_bom_snapshots": len(cost_rows),
        "lines_missing_costing": total_missing_costing,
        "items": items,
        "note": "Channel profit uses shipment_lines revenue baseline; cost from shipment_costing_results (coverage tracked). net_profit=(revenue-refund)-cost.",
    }


def profit_by_model(
    db: Session,
    *,
    start: datetime,
    end: datetime,
    group_by: Literal["day", "month"] = "month",
    channel: Optional[str] = None,
    model_code: Optional[str] = None,
) -> Dict[str, Any]:
    """
    模型分析（按模型聚合）：
    - 收入/数量基线：时间范围内全部发货行（completed_at）
    - 模型归因：优先 shipment_costing_results.model_version_id，缺失时回退到最新 bom_snapshot.model_version_id
    - 成本：优先 shipment_costing_results（三段成本齐全），回退到 bom_snapshot.trace.costing
    - 版本：同一个模型可能涉及多个版本；返回“主版本”（按销售额最大的版本）+ version_count
    """
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)

    # Revenue baseline: all shipments (even those without model attribution)
    ship_q = db.query(models.ShipmentLine).filter(
        models.ShipmentLine.completed_at.isnot(None),
        models.ShipmentLine.completed_at >= start,
        models.ShipmentLine.completed_at < end,
        models.ShipmentLine.is_archived.is_(False),
    )
    if channel:
        ship_q = ship_q.filter(models.ShipmentLine.channel == channel)
    total_ship_lines = int(ship_q.count() or 0)

    # Costing result per shipment_line_id (supports 2025 no-snapshot mode)
    res_sq = (
        db.query(
            models.ShipmentCostingResult.shipment_line_id.label("shipment_line_id"),
            models.ShipmentCostingResult.cost_total.label("cost_total"),
            models.ShipmentCostingResult.cost_material_total.label("cost_material_total"),
            models.ShipmentCostingResult.cost_process_total.label("cost_process_total"),
            models.ShipmentCostingResult.cost_overhead_total.label("cost_overhead_total"),
            models.ShipmentCostingResult.model_version_id.label("model_version_id"),
        )
        .subquery()
    )

    # Legacy fallback: latest bom_snapshot per shipment_line_id
    snap_sq = (
        db.query(
            models.BomSnapshot.id.label("bom_snapshot_id"),
            models.BomSnapshot.shipment_line_id.label("shipment_line_id"),
            models.BomSnapshot.model_version_id.label("model_version_id"),
            models.BomSnapshot.trace_json.label("trace_json"),
            models.BomSnapshot.created_at.label("created_at"),
        )
        .filter(models.BomSnapshot.shipment_line_id.isnot(None))
        .order_by(models.BomSnapshot.shipment_line_id.asc(), models.BomSnapshot.created_at.desc())
        .distinct(models.BomSnapshot.shipment_line_id)
        .subquery()
    )

    mv_id_expr = func.coalesce(res_sq.c.model_version_id, snap_sq.c.model_version_id)

    base_q = (
        db.query(
            models.ShipmentLine,
            res_sq.c.shipment_line_id.label("res_ship_line_id"),
            res_sq.c.cost_total,
            res_sq.c.cost_material_total,
            res_sq.c.cost_process_total,
            res_sq.c.cost_overhead_total,
            snap_sq.c.bom_snapshot_id,
            snap_sq.c.trace_json,
            mv_id_expr.label("model_version_id"),
            models.ProductModelVersion.version_kind,
            models.ProductModelVersion.version_status,
            models.ProductModelVersion.version_label,
            models.ProductModel.id.label("model_id"),
            models.ProductModel.model_code.label("model_code"),
            models.ProductModel.model_name.label("model_name"),
        )
        .outerjoin(res_sq, models.ShipmentLine.id == res_sq.c.shipment_line_id)
        .outerjoin(snap_sq, models.ShipmentLine.id == snap_sq.c.shipment_line_id)
        .outerjoin(
            models.ProductModelVersion,
            and_(models.ProductModelVersion.id == mv_id_expr, models.ProductModelVersion.is_archived.is_(False)),
        )
        .outerjoin(models.ProductModel, and_(models.ProductModel.id == models.ProductModelVersion.model_id, models.ProductModel.is_archived.is_(False)))
        .filter(
            models.ShipmentLine.completed_at.isnot(None),
            models.ShipmentLine.completed_at >= start,
            models.ShipmentLine.completed_at < end,
            models.ShipmentLine.is_archived.is_(False),
        )
    )
    if channel:
        base_q = base_q.filter(models.ShipmentLine.channel == channel)
    if model_code:
        base_q = base_q.filter(models.ProductModel.model_code == model_code)
    rows = base_q.all()

    # Refund by shipment line (same as profit_by_sku)
    refund_q = db.query(
        models.ShipmentLine.id.label("shipment_line_id"),
        func.coalesce(func.sum(models.AfterSalesLine.refund_amount), 0).label("refund_amount"),
    ).join(
        models.AfterSalesLine,
        and_(
            models.AfterSalesLine.order_no.isnot(None),
            models.AfterSalesLine.product_link_id.isnot(None),
            models.AfterSalesLine.sku_code.isnot(None),
            models.ShipmentLine.order_no == models.AfterSalesLine.order_no,
            models.ShipmentLine.product_link_id == models.AfterSalesLine.product_link_id,
            models.ShipmentLine.sku_code == models.AfterSalesLine.sku_code,
        ),
    ).filter(
        models.ShipmentLine.completed_at.isnot(None),
        models.ShipmentLine.completed_at >= start,
        models.ShipmentLine.completed_at < end,
        models.ShipmentLine.is_archived.is_(False),
        models.AfterSalesLine.is_archived.is_(False),
    )
    if channel:
        refund_q = refund_q.filter(models.ShipmentLine.channel == channel)
    refund_q = refund_q.group_by(models.ShipmentLine.id)
    refund_by_line = {str(r.shipment_line_id): _d(r.refund_amount) for r in refund_q.all()}

    mapped_lines = 0
    costed_lines = 0
    missing_costing_lines = 0

    agg: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    for (
        line,
        res_ship_line_id,
        cost_total,
        cost_material_total,
        cost_process_total,
        cost_overhead_total,
        _bom_snapshot_id,
        snap_trace_json,
        mv_id,
        ver_kind,
        ver_status,
        ver_label,
        mdl_id,
        mdl_code,
        mdl_name,
    ) in rows:
        if not line.completed_at:
            continue
        if not mdl_id or not mdl_code or not mdl_name:
            continue

        period = _period_key(line.completed_at, group_by)
        store = str(line.channel or "").strip()
        key = (period, store, str(mdl_id))

        bucket = agg.setdefault(
            key,
            {
                "period": period,
                "channel": store or None,
                "model_id": str(mdl_id),
                "model_code": str(mdl_code),
                "model_name": str(mdl_name),
                # top version (filled at the end)
                "version_id": "",
                "version_kind": "",
                "version_status": "",
                "version_label": None,
                "version_count": 0,
                "shipped_qty": Decimal("0"),
                "revenue_amount": Decimal("0"),
                "cost_material_amount": Decimal("0"),
                "cost_process_amount": Decimal("0"),
                "cost_overhead_amount": Decimal("0"),
                "cost_amount": Decimal("0"),
                "refund_amount": Decimal("0"),
                "line_count": 0,
                "costed_line_count": 0,
                "missing_costing_line_count": 0,
                # internal
                "_ver_rev": {},  # version_id -> revenue
                "_ver_info": {},  # version_id -> (kind,status,label)
            },
        )

        mapped_lines += 1
        bucket["line_count"] += 1

        qty = _d(line.qty)
        revenue = _d(line.revenue_amount)
        bucket["shipped_qty"] += qty
        bucket["revenue_amount"] += revenue
        bucket["refund_amount"] += refund_by_line.get(str(line.id), Decimal("0"))

        # Version tracking (for top-version selection)
        mv_id_str = str(mv_id or "").strip()
        if mv_id_str:
            bucket["_ver_rev"][mv_id_str] = _d(bucket["_ver_rev"].get(mv_id_str, 0)) + revenue
            bucket["_ver_info"][mv_id_str] = (str(ver_kind or ""), str(ver_status or ""), str(ver_label or "") or None)

        # Cost breakdown
        if res_ship_line_id is not None:
            m = _d(cost_material_total)
            p = _d(cost_process_total)
            o = _d(cost_overhead_total)
            total_src = cost_total
            if total_src in (None, ""):
                total_src = m + p + o
            total = _d(total_src)
            if total == 0 and (cost_total in (None, "", 0)) and (cost_material_total in (None, "")) and (cost_process_total in (None, "")) and (cost_overhead_total in (None, "")):
                # lightweight result missing cost -> fallback to snapshot trace if possible
                snap_total, sm, sp, so, s = _extract_cost_breakdown_from_trace(snap_trace_json)
                if s == "costed":
                    bucket["costed_line_count"] += 1
                    costed_lines += 1
                    bucket["cost_material_amount"] += _d(sm)
                    bucket["cost_process_amount"] += _d(sp)
                    bucket["cost_overhead_amount"] += _d(so)
                    bucket["cost_amount"] += _d(snap_total)
                else:
                    bucket["missing_costing_line_count"] += 1
                    missing_costing_lines += 1
            else:
                bucket["costed_line_count"] += 1
                costed_lines += 1
                bucket["cost_material_amount"] += m
                bucket["cost_process_amount"] += p
                bucket["cost_overhead_amount"] += o
                bucket["cost_amount"] += total
        else:
            total, m, p, o, status = _extract_cost_breakdown_from_trace(snap_trace_json)
            if status == "missing_costing":
                bucket["missing_costing_line_count"] += 1
                missing_costing_lines += 1
            else:
                bucket["costed_line_count"] += 1
                costed_lines += 1
                bucket["cost_material_amount"] += _d(m)
                bucket["cost_process_amount"] += _d(p)
                bucket["cost_overhead_amount"] += _d(o)
                bucket["cost_amount"] += _d(total)

    items: List[Dict[str, Any]] = []
    for _, b in sorted(agg.items(), key=lambda kv: kv[0]):
        # resolve top version (by revenue)
        ver_rev = b.pop("_ver_rev", {}) or {}
        ver_info = b.pop("_ver_info", {}) or {}
        if ver_rev:
            top_ver_id = max(ver_rev.items(), key=lambda kv: kv[1])[0]
            kind, status, label = ver_info.get(top_ver_id, ("", "", None))
            b["version_id"] = top_ver_id
            b["version_kind"] = kind
            b["version_status"] = status
            b["version_label"] = label
            b["version_count"] = len(ver_rev)
        else:
            b["version_id"] = ""
            b["version_kind"] = ""
            b["version_status"] = ""
            b["version_label"] = None
            b["version_count"] = 0

        revenue = b["revenue_amount"]
        cost = b["cost_amount"]
        refund = b["refund_amount"]
        gross_profit = revenue - cost
        gross_margin = (gross_profit / revenue) if revenue > 0 else None
        net_revenue = revenue - refund
        net_profit = net_revenue - cost
        net_margin = (net_profit / net_revenue) if net_revenue > 0 else None
        items.append(
            {
                **b,
                "gross_profit": gross_profit,
                "gross_margin": gross_margin,
                "net_revenue": net_revenue,
                "net_profit": net_profit,
                "net_margin": net_margin,
            }
        )

    return {
        "group_by": group_by,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "total_shipment_lines": total_ship_lines,
        "mapped_model_lines": int(mapped_lines),
        "costed_lines": int(costed_lines),
        "lines_missing_costing": int(missing_costing_lines),
        "items": items,
        "note": "模型分析：成本优先 shipment_costing_results（三段成本），回退 bom_snapshot.trace；版本为主版本（按销售额最大）。净利润=(销售额-退款)-成本。",
    }


def sales_lines(
    db: Session,
    *,
    start: datetime,
    end: datetime,
    page: int = 1,
    page_size: int = 50,
    channel: Optional[str] = None,
    sku_code: Optional[str] = None,
    shipment_no: Optional[str] = None,
    order_no: Optional[str] = None,
    product_link_id: Optional[str] = None,
    include_missing: bool = True,
) -> Dict[str, Any]:
    """
    Sales analysis (line-level) for shipped orders within [start, end).
    - Revenue baseline: shipment_lines.revenue_amount
    - Cost baseline: latest bom_snapshot.trace.costing.total_cost (per shipment_line_id)
    - Rows without snapshots are kept (cost shows null) when include_missing is True.
    """
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    start = start.astimezone(timezone.utc)
    end = end.astimezone(timezone.utc)

    p = max(int(page or 1), 1)
    ps = max(min(int(page_size or 50), 200), 1)

    def _to_str(v: Any) -> Optional[str]:
        if v in (None, ""):
            return None
        if isinstance(v, datetime):
            return v.isoformat()
        return str(v)

    def _guess(raw: Dict[str, Any], keys: List[str]) -> Optional[str]:
        if not isinstance(raw, dict) or not raw:
            return None
        for k in keys:
            if k in raw and raw.get(k) not in (None, ""):
                return _to_str(raw.get(k))
        lower = {str(k).lower(): k for k in raw.keys()}
        for k in keys:
            src = lower.get(str(k).lower())
            if src and raw.get(src) not in (None, ""):
                return _to_str(raw.get(src))
        return None

    # Costing result per shipment_line_id (lightweight; supports 2025 no-snapshot mode)
    res_sq = (
        db.query(
            models.ShipmentCostingResult.shipment_line_id.label("shipment_line_id"),
            models.ShipmentCostingResult.cost_total.label("cost_total"),
            models.ShipmentCostingResult.cost_material_total.label("cost_material_total"),
            models.ShipmentCostingResult.cost_process_total.label("cost_process_total"),
            models.ShipmentCostingResult.cost_overhead_total.label("cost_overhead_total"),
            models.ShipmentCostingResult.model_version_id.label("model_version_id"),
            models.ShipmentCostingResult.spec_hash.label("spec_hash"),
            models.ShipmentCostingResult.computed_at.label("computed_at"),
        )
        .subquery()
    )

    # Legacy fallback: latest bom_snapshot per shipment_line_id
    snap_sq = (
        db.query(
            models.BomSnapshot.id.label("bom_snapshot_id"),
            models.BomSnapshot.shipment_line_id.label("shipment_line_id"),
            models.BomSnapshot.trace_json.label("trace_json"),
            models.BomSnapshot.created_at.label("created_at"),
        )
        .filter(models.BomSnapshot.shipment_line_id.isnot(None))
        .order_by(models.BomSnapshot.shipment_line_id.asc(), models.BomSnapshot.created_at.desc())
        .distinct(models.BomSnapshot.shipment_line_id)
        .subquery()
    )

    base_q = (
        db.query(
            models.ShipmentLine,
            res_sq.c.shipment_line_id,
            snap_sq.c.bom_snapshot_id,
            snap_sq.c.trace_json,
            res_sq.c.cost_total,
            res_sq.c.cost_material_total,
            res_sq.c.cost_process_total,
            res_sq.c.cost_overhead_total,
            res_sq.c.model_version_id,
            res_sq.c.spec_hash,
        )
        .outerjoin(res_sq, models.ShipmentLine.id == res_sq.c.shipment_line_id)
        .outerjoin(snap_sq, models.ShipmentLine.id == snap_sq.c.shipment_line_id)
        .filter(
            models.ShipmentLine.is_archived.is_(False),
            models.ShipmentLine.completed_at.isnot(None),
            models.ShipmentLine.completed_at >= start,
            models.ShipmentLine.completed_at < end,
        )
    )
    if channel:
        base_q = base_q.filter(models.ShipmentLine.channel == channel)
    if sku_code:
        base_q = base_q.filter(models.ShipmentLine.sku_code == sku_code)
    if shipment_no:
        base_q = base_q.filter(models.ShipmentLine.shipment_no == shipment_no)
    if order_no:
        base_q = base_q.filter(models.ShipmentLine.order_no == order_no)
    if product_link_id:
        base_q = base_q.filter(models.ShipmentLine.product_link_id == product_link_id)

    # When user requests "only costed", pagination total must match the rows we will return.
    # We define "costed" as having a costing result OR a legacy BOM snapshot.
    if not include_missing:
        base_q = base_q.filter(or_(res_sq.c.shipment_line_id.isnot(None), snap_sq.c.bom_snapshot_id.isnot(None)))

    total = base_q.count()
    rows = (
        base_q.order_by(models.ShipmentLine.completed_at.desc(), models.ShipmentLine.created_at.desc())
        .offset((p - 1) * ps)
        .limit(ps)
        .all()
    )

    items: List[Dict[str, Any]] = []
    with_bom = 0
    missing_costing = 0

    for (
        line,
        result_line_id,
        bom_snapshot_id,
        snap_trace_json,
        cost_total,
        cost_material_total,
        cost_process_total,
        cost_overhead_total,
        model_version_id,
        spec_hash,
    ) in rows:
        raw = getattr(line, "raw_row_json", None) or getattr(line, "raw_row", None) or {}
        payment_at = _guess(raw, ["付款时间", "支付时间", "pay_time", "paid_at", "付款日期", "payment_at", "payment_time"])
        sku_no = _guess(raw, ["货品编号", "商品编号", "货品编码", "goods_code", "sku_no", "product_code"])
        sku_name = _guess(raw, ["货品名称", "商品名称", "商品标题", "title", "goods_name", "product_name"])
        logistics_company = _guess(raw, ["物流公司", "快递公司", "carrier", "logistics_company"])
        logistics_no = _guess(raw, ["物流单号", "快递单号", "tracking_no", "logistics_no", "waybill_no"])

        qty = _d(getattr(line, "qty", None))
        revenue = _d(getattr(line, "revenue_amount", None))
        sale_unit = (revenue / qty) if qty > 0 else None

        has_result = bool(result_line_id)
        has_snap = bool(bom_snapshot_id)
        cost_amount: Optional[Decimal] = None
        cost_unit: Optional[Decimal] = None
        status = "missing_snapshot"
        note = None
        if has_result:
            with_bom += 1
            # Prefer stored total cost; fall back to components sum.
            cost_amount = _d(cost_total)
            if cost_amount == 0 and cost_total in (None, "", 0):
                parts = _d(cost_material_total) + _d(cost_process_total) + _d(cost_overhead_total)
                cost_amount = parts if parts != 0 else None
            if cost_amount is None:
                status = "missing_costing"
                missing_costing += 1
                note = "计价结果缺成本字段（cost_total 为空）"
            else:
                status = "costed"
                if qty > 0:
                    cost_unit = cost_amount / qty
        elif has_snap:
            with_bom += 1
            cost_amount, status = _extract_total_cost_from_trace(snap_trace_json)
            if status == "missing_costing":
                missing_costing += 1
                note = "BOM 快照缺成本字段（trace.costing.total_cost 为空）"
            if cost_amount is not None and qty > 0:
                cost_unit = cost_amount / qty
        else:
            if include_missing:
                note = "缺计价结果（未计价）"
            else:
                continue

        mark = None
        if status == "missing_snapshot":
            mark = "未计价"
        elif status == "missing_costing":
            mark = "缺成本"

        items.append(
            {
                "shipment_line_id": str(line.id),
                "batch_id": str(getattr(line, "batch_id", "")) if getattr(line, "batch_id", None) else None,
                "row_index": getattr(line, "row_index", None),
                "payment_at": payment_at,
                "completed_at": getattr(line, "completed_at", None),
                "channel": getattr(line, "channel", None),
                "sku_no": sku_no,
                "sku_name": sku_name,
                "spec_text": getattr(line, "spec_text", None),
                "sku_code": getattr(line, "sku_code", None),
                "sale_unit_price": sale_unit,
                "qty": qty if qty != 0 else None,
                "revenue_amount": revenue if revenue != 0 else None,
                "cost_unit_price": cost_unit,
                "cost_amount": cost_amount,
                "order_no": getattr(line, "order_no", None),
                "product_link_id": getattr(line, "product_link_id", None),
                "logistics_company": logistics_company,
                "logistics_no": logistics_no,
                "mark": mark,
                "bom_snapshot_id": str(bom_snapshot_id) if has_snap else None,
                "status": status,
                "note": note,
            }
        )

    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "total": int(total),
        "page": p,
        "page_size": ps,
        "lines_with_bom_snapshots": int(with_bom),
        "lines_missing_costing": int(missing_costing),
        "items": items,
        "note": "明细口径：cost 优先来自计价结果（shipment_costing_results.cost_total），缺失时回退到最新 BOM 快照 trace.costing.total_cost。缺计价结果/快照的行成本显示为空。",
    }


def model_insights_summary(
    db: Session,
    *,
    start: datetime,
    end: datetime,
    channel: Optional[str] = None,
) -> Dict[str, Any]:
    """
    模型分析（统计榜单）：
    - 聚合维度：模型（可选按店铺过滤；若不传则为全店铺汇总）
    - 指标：发货数量/销售额/三段成本/毛利/退款/净利润 + 覆盖率（按行数）
    """
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    start = start.astimezone(timezone.utc)
    end = end.astimezone(timezone.utc)

    ship_q = db.query(models.ShipmentLine).filter(
        models.ShipmentLine.completed_at.isnot(None),
        models.ShipmentLine.completed_at >= start,
        models.ShipmentLine.completed_at < end,
        models.ShipmentLine.is_archived.is_(False),
    )
    if channel:
        ship_q = ship_q.filter(models.ShipmentLine.channel == channel)
    total_ship_lines = int(ship_q.count() or 0)

    res_sq = (
        db.query(
            models.ShipmentCostingResult.shipment_line_id.label("shipment_line_id"),
            models.ShipmentCostingResult.cost_total.label("cost_total"),
            models.ShipmentCostingResult.cost_material_total.label("cost_material_total"),
            models.ShipmentCostingResult.cost_process_total.label("cost_process_total"),
            models.ShipmentCostingResult.cost_overhead_total.label("cost_overhead_total"),
            models.ShipmentCostingResult.model_version_id.label("model_version_id"),
        )
        .subquery()
    )

    snap_sq = (
        db.query(
            models.BomSnapshot.shipment_line_id.label("shipment_line_id"),
            models.BomSnapshot.model_version_id.label("model_version_id"),
            models.BomSnapshot.trace_json.label("trace_json"),
            models.BomSnapshot.created_at.label("created_at"),
        )
        .filter(models.BomSnapshot.shipment_line_id.isnot(None))
        .order_by(models.BomSnapshot.shipment_line_id.asc(), models.BomSnapshot.created_at.desc())
        .distinct(models.BomSnapshot.shipment_line_id)
        .subquery()
    )

    mv_id_expr = func.coalesce(res_sq.c.model_version_id, snap_sq.c.model_version_id)
    q = (
        db.query(
            models.ShipmentLine,
            res_sq.c.shipment_line_id.label("res_ship_line_id"),
            res_sq.c.cost_total,
            res_sq.c.cost_material_total,
            res_sq.c.cost_process_total,
            res_sq.c.cost_overhead_total,
            snap_sq.c.trace_json,
            mv_id_expr.label("model_version_id"),
            models.ProductModelVersion.version_kind,
            models.ProductModelVersion.version_status,
            models.ProductModelVersion.version_label,
            models.ProductModel.id.label("model_id"),
            models.ProductModel.model_code.label("model_code"),
            models.ProductModel.model_name.label("model_name"),
        )
        .outerjoin(res_sq, models.ShipmentLine.id == res_sq.c.shipment_line_id)
        .outerjoin(snap_sq, models.ShipmentLine.id == snap_sq.c.shipment_line_id)
        .outerjoin(
            models.ProductModelVersion,
            and_(models.ProductModelVersion.id == mv_id_expr, models.ProductModelVersion.is_archived.is_(False)),
        )
        .outerjoin(models.ProductModel, and_(models.ProductModel.id == models.ProductModelVersion.model_id, models.ProductModel.is_archived.is_(False)))
        .filter(
            models.ShipmentLine.completed_at.isnot(None),
            models.ShipmentLine.completed_at >= start,
            models.ShipmentLine.completed_at < end,
            models.ShipmentLine.is_archived.is_(False),
        )
    )
    if channel:
        q = q.filter(models.ShipmentLine.channel == channel)
    rows = q.all()

    refund_q = db.query(
        models.ShipmentLine.id.label("shipment_line_id"),
        func.coalesce(func.sum(models.AfterSalesLine.refund_amount), 0).label("refund_amount"),
        func.coalesce(func.sum(models.AfterSalesLine.return_qty), 0).label("returned_qty"),
    ).join(
        models.AfterSalesLine,
        and_(
            models.AfterSalesLine.order_no.isnot(None),
            models.AfterSalesLine.product_link_id.isnot(None),
            models.AfterSalesLine.sku_code.isnot(None),
            models.ShipmentLine.order_no == models.AfterSalesLine.order_no,
            models.ShipmentLine.product_link_id == models.AfterSalesLine.product_link_id,
            models.ShipmentLine.sku_code == models.AfterSalesLine.sku_code,
        ),
    ).filter(
        models.ShipmentLine.completed_at.isnot(None),
        models.ShipmentLine.completed_at >= start,
        models.ShipmentLine.completed_at < end,
        models.ShipmentLine.is_archived.is_(False),
        models.AfterSalesLine.is_archived.is_(False),
    )
    if channel:
        refund_q = refund_q.filter(models.ShipmentLine.channel == channel)
    refund_q = refund_q.group_by(models.ShipmentLine.id)
    refund_by_line = {
        str(r.shipment_line_id): {"refund_amount": _d(r.refund_amount), "returned_qty": _d(r.returned_qty)}
        for r in refund_q.all()
    }

    mapped_lines = 0
    costed_lines = 0
    missing_costing_lines = 0

    agg: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for (
        line,
        res_ship_line_id,
        cost_total,
        cost_material_total,
        cost_process_total,
        cost_overhead_total,
        snap_trace_json,
        mv_id,
        ver_kind,
        ver_status,
        ver_label,
        mdl_id,
        mdl_code,
        mdl_name,
    ) in rows:
        if not line.completed_at:
            continue
        if not mdl_id or not mdl_code or not mdl_name:
            continue

        mapped_lines += 1
        key = (str(line.channel or "").strip(), str(mdl_id))
        bucket = agg.setdefault(
            key,
            {
                "channel": str(line.channel or "").strip() or None,
                "model_id": str(mdl_id),
                "model_code": str(mdl_code),
                "model_name": str(mdl_name),
                "shipped_qty": Decimal("0"),
                "revenue_amount": Decimal("0"),
                "cost_material_amount": Decimal("0"),
                "cost_process_amount": Decimal("0"),
                "cost_overhead_amount": Decimal("0"),
                "cost_amount": Decimal("0"),
                "refund_amount": Decimal("0"),
                "returned_qty": Decimal("0"),
                "line_count": 0,
                "costed_line_count": 0,
                "missing_costing_line_count": 0,
                "_ver_rev": {},
                "_ver_info": {},
            },
        )

        bucket["line_count"] += 1
        qty = _d(line.qty)
        revenue = _d(line.revenue_amount)
        bucket["shipped_qty"] += qty
        bucket["revenue_amount"] += revenue
        ref = refund_by_line.get(str(line.id)) or {"refund_amount": Decimal("0"), "returned_qty": Decimal("0")}
        bucket["refund_amount"] += _d(ref.get("refund_amount"))
        bucket["returned_qty"] += _d(ref.get("returned_qty"))

        mv_id_str = str(mv_id or "").strip()
        if mv_id_str:
            bucket["_ver_rev"][mv_id_str] = _d(bucket["_ver_rev"].get(mv_id_str, 0)) + revenue
            bucket["_ver_info"][mv_id_str] = (str(ver_kind or ""), str(ver_status or ""), str(ver_label or "") or None)

        if res_ship_line_id is not None:
            m = _d(cost_material_total)
            p = _d(cost_process_total)
            o = _d(cost_overhead_total)
            total_src = cost_total
            if total_src in (None, ""):
                total_src = m + p + o
            total = _d(total_src)
            if total == 0 and (cost_total in (None, "", 0)) and (cost_material_total in (None, "")) and (cost_process_total in (None, "")) and (cost_overhead_total in (None, "")):
                snap_total, sm, sp, so, s = _extract_cost_breakdown_from_trace(snap_trace_json)
                if s == "costed":
                    bucket["costed_line_count"] += 1
                    costed_lines += 1
                    bucket["cost_material_amount"] += _d(sm)
                    bucket["cost_process_amount"] += _d(sp)
                    bucket["cost_overhead_amount"] += _d(so)
                    bucket["cost_amount"] += _d(snap_total)
                else:
                    bucket["missing_costing_line_count"] += 1
                    missing_costing_lines += 1
            else:
                bucket["costed_line_count"] += 1
                costed_lines += 1
                bucket["cost_material_amount"] += m
                bucket["cost_process_amount"] += p
                bucket["cost_overhead_amount"] += o
                bucket["cost_amount"] += total
        else:
            total, m, p, o, status = _extract_cost_breakdown_from_trace(snap_trace_json)
            if status == "missing_costing":
                bucket["missing_costing_line_count"] += 1
                missing_costing_lines += 1
            else:
                bucket["costed_line_count"] += 1
                costed_lines += 1
                bucket["cost_material_amount"] += _d(m)
                bucket["cost_process_amount"] += _d(p)
                bucket["cost_overhead_amount"] += _d(o)
                bucket["cost_amount"] += _d(total)

    items: List[Dict[str, Any]] = []
    for _, b in agg.items():
        ver_rev = b.pop("_ver_rev", {}) or {}
        ver_info = b.pop("_ver_info", {}) or {}
        if ver_rev:
            top_ver_id = max(ver_rev.items(), key=lambda kv: kv[1])[0]
            kind, status, label = ver_info.get(top_ver_id, ("", "", None))
            b["top_version_id"] = top_ver_id
            b["top_version_kind"] = kind or None
            b["top_version_status"] = status or None
            b["top_version_label"] = label
            b["version_count"] = len(ver_rev)
        else:
            b["top_version_id"] = None
            b["top_version_kind"] = None
            b["top_version_status"] = None
            b["top_version_label"] = None
            b["version_count"] = 0

        revenue = b["revenue_amount"]
        cost = b["cost_amount"]
        refund = b["refund_amount"]
        gross_profit = revenue - cost
        gross_margin = (gross_profit / revenue) if revenue > 0 else None
        net_revenue = revenue - refund
        net_profit = net_revenue - cost
        net_margin = (net_profit / net_revenue) if net_revenue > 0 else None
        items.append(
            {
                **b,
                "gross_profit": gross_profit,
                "gross_margin": gross_margin,
                "net_revenue": net_revenue,
                "net_profit": net_profit,
                "net_margin": net_margin,
            }
        )

    items.sort(key=lambda r: _d(r.get("revenue_amount")), reverse=True)
    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "channel": channel,
        "total_shipment_lines": total_ship_lines,
        "mapped_model_lines": int(mapped_lines),
        "costed_lines": int(costed_lines),
        "lines_missing_costing": int(missing_costing_lines),
        "items": items,
        "note": "模型统计榜单：按模型聚合；成本优先 shipment_costing_results（三段），回退 bom_snapshot.trace；覆盖率按行数。",
    }


def model_insights_detail(
    db: Session,
    *,
    start: datetime,
    end: datetime,
    model_code: str,
    channel: Optional[str] = None,
    version_id: Optional[str] = None,
) -> Dict[str, Any]:
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    start = start.astimezone(timezone.utc)
    end = end.astimezone(timezone.utc)

    mdl = (
        db.query(models.ProductModel)
        .filter(models.ProductModel.model_code == model_code, models.ProductModel.is_archived.is_(False))
        .first()
    )
    if not mdl:
        raise ValueError("模型不存在或已归档")

    res_sq = (
        db.query(
            models.ShipmentCostingResult.shipment_line_id.label("shipment_line_id"),
            models.ShipmentCostingResult.cost_total.label("cost_total"),
            models.ShipmentCostingResult.cost_material_total.label("cost_material_total"),
            models.ShipmentCostingResult.cost_process_total.label("cost_process_total"),
            models.ShipmentCostingResult.cost_overhead_total.label("cost_overhead_total"),
            models.ShipmentCostingResult.model_version_id.label("model_version_id"),
        )
        .subquery()
    )
    snap_sq = (
        db.query(
            models.BomSnapshot.shipment_line_id.label("shipment_line_id"),
            models.BomSnapshot.model_version_id.label("model_version_id"),
            models.BomSnapshot.trace_json.label("trace_json"),
            models.BomSnapshot.created_at.label("created_at"),
        )
        .filter(models.BomSnapshot.shipment_line_id.isnot(None))
        .order_by(models.BomSnapshot.shipment_line_id.asc(), models.BomSnapshot.created_at.desc())
        .distinct(models.BomSnapshot.shipment_line_id)
        .subquery()
    )

    mv_id_expr = func.coalesce(res_sq.c.model_version_id, snap_sq.c.model_version_id)
    base_q = (
        db.query(
            models.ShipmentLine,
            res_sq.c.shipment_line_id.label("res_ship_line_id"),
            res_sq.c.cost_total,
            res_sq.c.cost_material_total,
            res_sq.c.cost_process_total,
            res_sq.c.cost_overhead_total,
            snap_sq.c.trace_json,
            mv_id_expr.label("model_version_id"),
            models.ProductModelVersion.version_kind,
            models.ProductModelVersion.version_status,
            models.ProductModelVersion.version_label,
        )
        .outerjoin(res_sq, models.ShipmentLine.id == res_sq.c.shipment_line_id)
        .outerjoin(snap_sq, models.ShipmentLine.id == snap_sq.c.shipment_line_id)
        .join(
            models.ProductModelVersion,
            and_(
                models.ProductModelVersion.id == mv_id_expr,
                models.ProductModelVersion.is_archived.is_(False),
                models.ProductModelVersion.model_id == mdl.id,
            ),
        )
        .filter(
            models.ShipmentLine.completed_at.isnot(None),
            models.ShipmentLine.completed_at >= start,
            models.ShipmentLine.completed_at < end,
            models.ShipmentLine.is_archived.is_(False),
        )
    )
    if channel:
        base_q = base_q.filter(models.ShipmentLine.channel == channel)
    rows = base_q.all()

    ver_agg: Dict[str, Dict[str, Any]] = {}
    for (
        line,
        res_ship_line_id,
        cost_total,
        cost_material_total,
        cost_process_total,
        cost_overhead_total,
        snap_trace_json,
        mv_id,
        ver_kind,
        ver_status,
        ver_label,
    ) in rows:
        vid = str(mv_id or "").strip()
        if not vid:
            continue
        b = ver_agg.setdefault(
            vid,
            {
                "version_id": vid,
                "version_kind": str(ver_kind or "") or None,
                "version_status": str(ver_status or "") or None,
                "version_label": str(ver_label or "") or None,
                "shipped_qty": Decimal("0"),
                "revenue_amount": Decimal("0"),
                "cost_material_amount": Decimal("0"),
                "cost_process_amount": Decimal("0"),
                "cost_overhead_amount": Decimal("0"),
                "cost_amount": Decimal("0"),
                "line_count": 0,
                "costed_line_count": 0,
                "missing_costing_line_count": 0,
            },
        )
        b["line_count"] += 1
        b["shipped_qty"] += _d(line.qty)
        revenue = _d(line.revenue_amount)
        b["revenue_amount"] += revenue

        if res_ship_line_id is not None:
            m = _d(cost_material_total)
            p = _d(cost_process_total)
            o = _d(cost_overhead_total)
            total_src = cost_total
            if total_src in (None, ""):
                total_src = m + p + o
            total = _d(total_src)
            if total == 0 and (cost_total in (None, "", 0)) and (cost_material_total in (None, "")) and (cost_process_total in (None, "")) and (cost_overhead_total in (None, "")):
                snap_total, sm, sp, so, s = _extract_cost_breakdown_from_trace(snap_trace_json)
                if s == "costed":
                    b["costed_line_count"] += 1
                    b["cost_material_amount"] += _d(sm)
                    b["cost_process_amount"] += _d(sp)
                    b["cost_overhead_amount"] += _d(so)
                    b["cost_amount"] += _d(snap_total)
                else:
                    b["missing_costing_line_count"] += 1
            else:
                b["costed_line_count"] += 1
                b["cost_material_amount"] += m
                b["cost_process_amount"] += p
                b["cost_overhead_amount"] += o
                b["cost_amount"] += total
        else:
            total, m, p, o, status = _extract_cost_breakdown_from_trace(snap_trace_json)
            if status == "missing_costing":
                b["missing_costing_line_count"] += 1
            else:
                b["costed_line_count"] += 1
                b["cost_material_amount"] += _d(m)
                b["cost_process_amount"] += _d(p)
                b["cost_overhead_amount"] += _d(o)
                b["cost_amount"] += _d(total)

    versions: List[Dict[str, Any]] = []
    for b in ver_agg.values():
        revenue = b["revenue_amount"]
        cost = b["cost_amount"]
        gross_profit = revenue - cost
        gross_margin = (gross_profit / revenue) if revenue > 0 else None
        versions.append({**b, "gross_profit": gross_profit, "gross_margin": gross_margin})
    versions.sort(key=lambda r: _d(r.get("revenue_amount")), reverse=True)

    selected_version_id = str(version_id or (versions[0]["version_id"] if versions else "")).strip() or None

    sample_row = None
    if selected_version_id:
        sample_row = (
            base_q.filter(mv_id_expr == selected_version_id)
            .order_by(models.ShipmentLine.completed_at.desc(), models.ShipmentLine.created_at.desc())
            .first()
        )
    sample_line = sample_row[0] if sample_row else None

    bom: Optional[Dict[str, Any]] = None
    note: Optional[str] = None
    if sample_line and selected_version_id:
        try:
            qty = _d(sample_line.qty) if sample_line.qty not in (None, "") else Decimal("1")
            bom = bom_generation_service.generate_bom(
                db,
                spec_text=str(sample_line.spec_text or ""),
                model_version_id=str(selected_version_id),
                sku_code=str(sample_line.sku_code or ""),
                quantity=qty,
                include_disabled_variants=False,
            )
            note = "右侧 BOM 为样本发货行“现场生成”（与测试台 bom/generate 同口径）。"
        except Exception as e:  # noqa: BLE001
            bom = {"final_material_lines": [], "trace": {"costing": {}, "inventory": {}}}
            note = f"生成样本 BOM 失败：{e}"

    persisted = []
    if sample_line:
        persisted_rows = (
            db.query(models.ShipmentInventoryDeductionLine)
            .filter(models.ShipmentInventoryDeductionLine.shipment_line_id == sample_line.id)
            .order_by(models.ShipmentInventoryDeductionLine.material_code.asc())
            .all()
        )
        for r in persisted_rows:
            meta = getattr(r, "metadata_json", None) or {}
            sources = meta.get("sources")
            persisted.append(
                {
                    "material_code": getattr(r, "material_code", None),
                    "material_name": getattr(r, "material_name", None),
                    "unit_of_measure": getattr(r, "unit_of_measure", None),
                    "quantity": getattr(r, "quantity", None),
                    "sources": (len(sources) if isinstance(sources, list) else None),
                }
            )

    base_material_lines = []
    base_process_lines = []
    if selected_version_id:
        try:
            mats = product_model_service.list_version_material_lines(db, str(selected_version_id))
            for r in mats or []:
                base_material_lines.append(
                    {
                        "material_type": getattr(r, "material_type", None),
                        "material_ref_id": getattr(r, "material_ref_id", None),
                        "material_code": getattr(r, "material_code", None),
                        "material_name": getattr(r, "material_name", None),
                        "unit_of_measure": getattr(r, "unit_of_measure", None),
                        "calculation_method": getattr(r, "calculation_method", None),
                        "base_quantity": getattr(r, "base_quantity", None),
                        "loss_rate": getattr(r, "loss_rate", None),
                        "unit_cost": getattr(r, "unit_cost", None),
                        "sequence_order": getattr(r, "sequence_order", None),
                        "notes": getattr(r, "notes", None),
                    }
                )
            procs = product_model_service.list_version_process_lines(db, str(selected_version_id))
            for r in procs or []:
                p = getattr(r, "process", None)
                base_process_lines.append(
                    {
                        "process_id": getattr(r, "process_id", None),
                        "process_code": getattr(p, "process_code", None) if p is not None else None,
                        "process_name": getattr(p, "process_name", None) if p is not None else None,
                        "team_name": getattr(p, "team_name", None) if p is not None else None,
                        "pricing_method": getattr(p, "pricing_method", None) if p is not None else None,
                        "piece_rate": getattr(p, "piece_rate", None) if p is not None else None,
                        "rate_per_minute": getattr(p, "rate_per_minute", None) if p is not None else None,
                        "notes": getattr(r, "notes", None),
                    }
                )
        except Exception:
            pass

    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "channel": channel,
        "model_id": str(mdl.id),
        "model_code": str(mdl.model_code),
        "model_name": str(mdl.model_name),
        "selected_version_id": selected_version_id,
        "versions": versions,
        "sample_shipment_line_id": str(sample_line.id) if sample_line else None,
        "sample_completed_at": sample_line.completed_at if sample_line else None,
        "sample_sku_code": str(sample_line.sku_code) if sample_line and sample_line.sku_code else None,
        "sample_spec_text": str(sample_line.spec_text) if sample_line and sample_line.spec_text else None,
        "sample_qty": sample_line.qty if sample_line else None,
        "bom": bom,
        "persisted_deductions": persisted,
        "base_material_lines": base_material_lines,
        "base_process_lines": base_process_lines,
        "note": note,
    }

