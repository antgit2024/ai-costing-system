from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Literal, Optional, Tuple

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from .. import models


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
    Profit analytics (2025 analysis mode):
    - Revenue/qty from shipment_lines within [start, end) by completed_at.
    - Cost from bom_snapshots.trace.costing.total_cost (generated at import-time, using current price strategy).
    - Refunds (returns) are attributed to shipment period via strong join (order_no+product_link_id+sku_code).
    - Never runs full rebuild; only aggregates within the requested time range.
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

    # Cost only for lines with BOM snapshots
    snap_q = (
        db.query(models.BomSnapshot, models.ShipmentLine)
        .join(models.ShipmentLine, models.ShipmentLine.id == models.BomSnapshot.shipment_line_id)
        .filter(
            models.ShipmentLine.completed_at.isnot(None),
            models.ShipmentLine.completed_at >= start,
            models.ShipmentLine.completed_at < end,
            models.ShipmentLine.is_archived.is_(False),
        )
    )
    if channel:
        snap_q = snap_q.filter(models.ShipmentLine.channel == channel)
    if sku_code:
        snap_q = snap_q.filter(models.ShipmentLine.sku_code == sku_code)

    rows = snap_q.all()

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

    for snap, line in rows:
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

        trace = (snap.trace_json or {}) if isinstance(snap.trace_json, dict) else {}
        costing = (trace.get("costing") or {}) if isinstance(trace.get("costing"), dict) else {}
        total_cost = costing.get("total_cost")
        if total_cost in (None, ""):
            # fallback
            total_cost = _d(costing.get("material_cost_total")) + _d(costing.get("process_cost_total")) + _d(costing.get("overhead_cost"))
        cost = _d(total_cost)
        if cost == 0 and total_cost in (None, "", 0):
            missing_cost += 1
        bucket["cost_amount"] += cost

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
        "lines_with_bom_snapshots": len(rows),
        "lines_missing_costing": missing_cost,
        "items": items,
        "note": "2025 analysis mode: costs from bom_snapshots.trace.costing.total_cost (current price strategy); net_profit=(revenue-refund)-cost (no inventory reversal).",
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
    - Cost uses bom_snapshots.trace.costing.total_cost for lines that have BOM snapshots.
    - Refunds are attributed to shipment period via strong keys (order_no+product_link_id+sku_code).
    - Coverage is explicit (total shipment lines vs lines with BOM snapshots).
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

    snap_q = (
        db.query(models.BomSnapshot, models.ShipmentLine)
        .join(models.ShipmentLine, models.ShipmentLine.id == models.BomSnapshot.shipment_line_id)
        .filter(
            models.ShipmentLine.completed_at.isnot(None),
            models.ShipmentLine.completed_at >= start,
            models.ShipmentLine.completed_at < end,
            models.ShipmentLine.is_archived.is_(False),
        )
    )
    if channel:
        snap_q = snap_q.filter(models.ShipmentLine.channel == channel)
    snap_rows = snap_q.all()

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

    # Add costs from snapshots
    total_missing_costing = 0
    for snap, line in snap_rows:
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
        trace = (snap.trace_json or {}) if isinstance(snap.trace_json, dict) else {}
        costing = (trace.get("costing") or {}) if isinstance(trace.get("costing"), dict) else {}
        total_cost = costing.get("total_cost")
        if total_cost in (None, ""):
            total_cost = _d(costing.get("material_cost_total")) + _d(costing.get("process_cost_total")) + _d(costing.get("overhead_cost"))
        cost = _d(total_cost)
        if cost == 0 and total_cost in (None, "", 0):
            bucket["lines_missing_costing"] += 1
            total_missing_costing += 1
        bucket["cost_amount"] += cost

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
        "lines_with_bom_snapshots": len(snap_rows),
        "lines_missing_costing": total_missing_costing,
        "items": items,
        "note": "Channel profit uses shipment_lines revenue baseline; cost from bom_snapshots only (coverage tracked). net_profit=(revenue-refund)-cost.",
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
    Profit grouped by model (product_models) using bom_snapshots.model_version_id -> product_model_versions -> product_models.
    Only includes shipment lines that have bom_snapshots (i.e., SKU already bound & parsed).
    """
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)

    q = (
        db.query(
            models.BomSnapshot,
            models.ShipmentLine,
            models.ProductModelVersion,
            models.ProductModel,
        )
        .join(models.ShipmentLine, models.ShipmentLine.id == models.BomSnapshot.shipment_line_id)
        .join(models.ProductModelVersion, models.ProductModelVersion.id == models.BomSnapshot.model_version_id)
        .join(models.ProductModel, models.ProductModel.id == models.ProductModelVersion.model_id)
        .filter(
            models.ShipmentLine.completed_at.isnot(None),
            models.ShipmentLine.completed_at >= start,
            models.ShipmentLine.completed_at < end,
            models.ShipmentLine.is_archived.is_(False),
        )
    )
    if channel:
        q = q.filter(models.ShipmentLine.channel == channel)
    if model_code:
        q = q.filter(models.ProductModel.model_code == model_code)

    rows = q.all()

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

    agg: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for snap, line, ver, model in rows:
        if not line.completed_at:
            continue
        period = _period_key(line.completed_at, group_by)
        key = (period, str(model.id))
        bucket = agg.setdefault(
            key,
            {
                "period": period,
                "channel": line.channel,
                "model_id": model.id,
                "model_code": model.model_code,
                "model_name": model.model_name,
                "version_id": ver.id,
                "version_kind": ver.version_kind,
                "version_status": ver.version_status,
                "shipped_qty": Decimal("0"),
                "revenue_amount": Decimal("0"),
                "cost_amount": Decimal("0"),
                "refund_amount": Decimal("0"),
            },
        )
        bucket["shipped_qty"] += _d(line.qty)
        bucket["revenue_amount"] += _d(line.revenue_amount)

        trace = (snap.trace_json or {}) if isinstance(snap.trace_json, dict) else {}
        costing = (trace.get("costing") or {}) if isinstance(trace.get("costing"), dict) else {}
        total_cost = costing.get("total_cost")
        if total_cost in (None, ""):
            total_cost = _d(costing.get("material_cost_total")) + _d(costing.get("process_cost_total")) + _d(costing.get("overhead_cost"))
        bucket["cost_amount"] += _d(total_cost)
        bucket["refund_amount"] += refund_by_line.get(str(line.id), Decimal("0"))

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
        "items": items,
        "note": "Model profit uses bom_snapshots only (bound SKUs). net_profit=(revenue-refund)-cost.",
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

    def _extract_total_cost(trace_json: Any) -> Tuple[Optional[Decimal], str]:
        trace = (trace_json or {}) if isinstance(trace_json, dict) else {}
        costing = (trace.get("costing") or {}) if isinstance(trace.get("costing"), dict) else {}
        total_cost = costing.get("total_cost")
        if total_cost in (None, ""):
            total_cost = _d(costing.get("material_cost_total")) + _d(costing.get("process_cost_total")) + _d(costing.get("overhead_cost"))
        cost = _d(total_cost)
        if cost == 0 and total_cost in (None, "", 0):
            return None, "missing_costing"
        return cost, "costed"

    # Latest snapshot per shipment_line_id (DISTINCT ON)
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
            snap_sq.c.bom_snapshot_id,
            snap_sq.c.trace_json,
        )
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

    for line, bom_snapshot_id, trace_json in rows:
        raw = getattr(line, "raw_row_json", None) or getattr(line, "raw_row", None) or {}
        payment_at = _guess(raw, ["付款时间", "支付时间", "pay_time", "paid_at", "付款日期", "payment_at", "payment_time"])
        sku_no = _guess(raw, ["货品编号", "商品编号", "货品编码", "goods_code", "sku_no", "product_code"])
        sku_name = _guess(raw, ["货品名称", "商品名称", "商品标题", "title", "goods_name", "product_name"])
        logistics_company = _guess(raw, ["物流公司", "快递公司", "carrier", "logistics_company"])
        logistics_no = _guess(raw, ["物流单号", "快递单号", "tracking_no", "logistics_no", "waybill_no"])

        qty = _d(getattr(line, "qty", None))
        revenue = _d(getattr(line, "revenue_amount", None))
        sale_unit = (revenue / qty) if qty > 0 else None

        has_snap = bool(bom_snapshot_id)
        cost_amount: Optional[Decimal] = None
        cost_unit: Optional[Decimal] = None
        status = "missing_snapshot"
        note = None
        if has_snap:
            with_bom += 1
            cost_amount, status = _extract_total_cost(trace_json)
            if status == "missing_costing":
                missing_costing += 1
                note = "快照缺成本字段（trace.costing.total_cost 为空）"
            if cost_amount is not None and qty > 0:
                cost_unit = cost_amount / qty
        else:
            if include_missing:
                note = "缺 BOM 快照（未计价）"
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
        "note": "明细口径：cost 来自最新 BOM 快照 trace.costing.total_cost；缺快照的行成本显示为空。",
    }

