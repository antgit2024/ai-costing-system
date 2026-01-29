from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..dependencies import get_db_session
from ..services import analytics_service
from ..services import report_snapshot_service

router = APIRouter(prefix="/reports", tags=["Reports"])


def _bj_day_range(days: int) -> tuple[datetime, datetime]:
    """
    Compute [start,end) range using Beijing day boundaries, then convert to UTC.

    Frontend uses dayjs().subtract(days,'day').startOf('day') ~ today.endOf('day').
    We mirror that for stable “每日更新”的口径。
    """
    n = int(days or 0)
    if n <= 0 or n > 365:
        raise ValueError("days 需在 1~365")
    bj = timezone(timedelta(hours=8))
    now_bj = datetime.now(bj)
    start_bj = (now_bj - timedelta(days=n)).replace(hour=0, minute=0, second=0, microsecond=0)
    end_bj = now_bj.replace(hour=23, minute=59, second=59, microsecond=999000)
    return start_bj.astimezone(timezone.utc), end_bj.astimezone(timezone.utc)


@router.get("/insights/models-summary")
def get_models_summary_snapshot(
    range_days: int = Query(30, ge=1, le=365, description="近N天（按北京时间日界）"),
    channel: Optional[str] = Query(None),
    db: Session = Depends(get_db_session),
):
    params = {"range_days": int(range_days), "channel": (channel or "").strip() or None}
    key = report_snapshot_service.snapshot_key("insights.models_summary", params)
    snap = report_snapshot_service.get_snapshot(db, key=key)
    if not snap:
        raise HTTPException(status_code=404, detail="缓存不存在")
    return {"key": snap.key, "computed_at": snap.computed_at.isoformat(), "params": snap.params, "data": snap.data}


@router.post("/insights/models-summary/refresh")
def refresh_models_summary_snapshot(
    range_days: int = Query(30, ge=1, le=365),
    channel: Optional[str] = Query(None),
    operator_id: Optional[str] = Query(None, description="操作者（用于审计展示）"),
    db: Session = Depends(get_db_session),
):
    try:
        start, end = _bj_day_range(range_days)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    params = {"range_days": int(range_days), "channel": (channel or "").strip() or None}
    payload = analytics_service.model_insights_summary(
        db,
        start=start,
        end=end,
        channel=params["channel"],
        bundle_template_code=None,
        bundle_preset_selector=None,
    )
    key = report_snapshot_service.snapshot_key("insights.models_summary", params)
    snap = report_snapshot_service.upsert_snapshot(db, key=key, data=payload, params=params, operator_id=operator_id)
    return {"key": snap.key, "computed_at": snap.computed_at.isoformat(), "params": snap.params}


@router.get("/insights/sales-profit-dashboard")
def get_sales_profit_dashboard_snapshot(
    range_days: int = Query(30, ge=1, le=365),
    group_by: Literal["week", "month"] = Query("week"),
    channel: Optional[str] = Query(None),
    db: Session = Depends(get_db_session),
):
    params = {"range_days": int(range_days), "group_by": group_by, "channel": (channel or "").strip() or None}
    key = report_snapshot_service.snapshot_key("insights.sales_profit_dashboard", params)
    snap = report_snapshot_service.get_snapshot(db, key=key)
    if not snap:
        raise HTTPException(status_code=404, detail="缓存不存在")
    return {"key": snap.key, "computed_at": snap.computed_at.isoformat(), "params": snap.params, "data": snap.data}


@router.post("/insights/sales-profit-dashboard/refresh")
def refresh_sales_profit_dashboard_snapshot(
    range_days: int = Query(30, ge=1, le=365),
    group_by: Literal["week", "month"] = Query("week"),
    channel: Optional[str] = Query(None),
    operator_id: Optional[str] = Query(None),
    db: Session = Depends(get_db_session),
):
    try:
        start, end = _bj_day_range(range_days)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    params = {"range_days": int(range_days), "group_by": group_by, "channel": (channel or "").strip() or None}
    payload = analytics_service.sales_profit_dashboard(
        db,
        start=start,
        end=end,
        group_by=group_by,
        channel=params["channel"],
        top_n=12,
    )
    key = report_snapshot_service.snapshot_key("insights.sales_profit_dashboard", params)
    snap = report_snapshot_service.upsert_snapshot(db, key=key, data=payload, params=params, operator_id=operator_id)
    return {"key": snap.key, "computed_at": snap.computed_at.isoformat(), "params": snap.params}


@router.get("/insights/after-sales-dashboard")
def get_after_sales_dashboard_snapshot(
    range_days: int = Query(30, ge=1, le=365),
    group_by: Literal["week", "month"] = Query("week"),
    view: Literal["factory", "ops"] = Query("factory"),
    channel: Optional[str] = Query(None),
    db: Session = Depends(get_db_session),
):
    params: Dict[str, Any] = {
        "range_days": int(range_days),
        "group_by": group_by,
        "view": view,
        "channel": (channel or "").strip() or None,
    }
    key = report_snapshot_service.snapshot_key("insights.after_sales_dashboard", params)
    snap = report_snapshot_service.get_snapshot(db, key=key)
    if not snap:
        raise HTTPException(status_code=404, detail="缓存不存在")
    return {"key": snap.key, "computed_at": snap.computed_at.isoformat(), "params": snap.params, "data": snap.data}


@router.post("/insights/after-sales-dashboard/refresh")
def refresh_after_sales_dashboard_snapshot(
    range_days: int = Query(30, ge=1, le=365),
    group_by: Literal["week", "month"] = Query("week"),
    view: Literal["factory", "ops"] = Query("factory"),
    channel: Optional[str] = Query(None),
    operator_id: Optional[str] = Query(None),
    db: Session = Depends(get_db_session),
):
    try:
        start, end = _bj_day_range(range_days)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    params: Dict[str, Any] = {
        "range_days": int(range_days),
        "group_by": group_by,
        "view": view,
        "channel": (channel or "").strip() or None,
    }
    payload = analytics_service.after_sales_dashboard(
        db,
        start=start,
        end=end,
        group_by=group_by,
        channel=params["channel"],
        top_n=12,
        view=view,
    )
    key = report_snapshot_service.snapshot_key("insights.after_sales_dashboard", params)
    snap = report_snapshot_service.upsert_snapshot(db, key=key, data=payload, params=params, operator_id=operator_id)
    return {"key": snap.key, "computed_at": snap.computed_at.isoformat(), "params": snap.params}


@router.get("/insights/shops/profit-by-channel")
def get_profit_by_channel_snapshot(
    range_days: int = Query(30, ge=1, le=365),
    group_by: Literal["day", "month"] = Query("month"),
    channel: Optional[str] = Query(None),
    db: Session = Depends(get_db_session),
):
    params = {"range_days": int(range_days), "group_by": group_by, "channel": (channel or "").strip() or None}
    key = report_snapshot_service.snapshot_key("insights.shops.profit_by_channel", params)
    snap = report_snapshot_service.get_snapshot(db, key=key)
    if not snap:
        raise HTTPException(status_code=404, detail="缓存不存在")
    return {"key": snap.key, "computed_at": snap.computed_at.isoformat(), "params": snap.params, "data": snap.data}


@router.post("/insights/shops/profit-by-channel/refresh")
def refresh_profit_by_channel_snapshot(
    range_days: int = Query(30, ge=1, le=365),
    group_by: Literal["day", "month"] = Query("month"),
    channel: Optional[str] = Query(None),
    operator_id: Optional[str] = Query(None),
    db: Session = Depends(get_db_session),
):
    try:
        start, end = _bj_day_range(range_days)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    params = {"range_days": int(range_days), "group_by": group_by, "channel": (channel or "").strip() or None}
    payload = analytics_service.profit_by_channel(db, start=start, end=end, group_by=group_by, channel=params["channel"])
    key = report_snapshot_service.snapshot_key("insights.shops.profit_by_channel", params)
    snap = report_snapshot_service.upsert_snapshot(db, key=key, data=payload, params=params, operator_id=operator_id)
    return {"key": snap.key, "computed_at": snap.computed_at.isoformat(), "params": snap.params}


@router.get("/insights/shops/returns-rate-by-channel")
def get_returns_rate_by_channel_snapshot(
    range_days: int = Query(30, ge=1, le=365),
    group_by: Literal["day", "month"] = Query("month"),
    channel: Optional[str] = Query(None),
    db: Session = Depends(get_db_session),
):
    params = {"range_days": int(range_days), "group_by": group_by, "channel": (channel or "").strip() or None}
    key = report_snapshot_service.snapshot_key("insights.shops.returns_rate_by_channel", params)
    snap = report_snapshot_service.get_snapshot(db, key=key)
    if not snap:
        raise HTTPException(status_code=404, detail="缓存不存在")
    return {"key": snap.key, "computed_at": snap.computed_at.isoformat(), "params": snap.params, "data": snap.data}


@router.post("/insights/shops/returns-rate-by-channel/refresh")
def refresh_returns_rate_by_channel_snapshot(
    range_days: int = Query(30, ge=1, le=365),
    group_by: Literal["day", "month"] = Query("month"),
    channel: Optional[str] = Query(None),
    operator_id: Optional[str] = Query(None),
    db: Session = Depends(get_db_session),
):
    try:
        start, end = _bj_day_range(range_days)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    params = {"range_days": int(range_days), "group_by": group_by, "channel": (channel or "").strip() or None}
    payload = analytics_service.returns_rate_by_channel(db, start=start, end=end, group_by=group_by, channel=params["channel"])
    key = report_snapshot_service.snapshot_key("insights.shops.returns_rate_by_channel", params)
    snap = report_snapshot_service.upsert_snapshot(db, key=key, data=payload, params=params, operator_id=operator_id)
    return {"key": snap.key, "computed_at": snap.computed_at.isoformat(), "params": snap.params}

