from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..dependencies import get_db_session
from ..schemas import (
    AfterSalesDashboardResponse,
    ModelInsightsDetailResponse,
    ModelInsightsSummaryResponse,
    ModelUsageMaterialSummaryResponse,
    ModelUsageProcessSummaryResponse,
    ProfitByChannelResponse,
    ProfitByModelResponse,
    ProfitBySkuResponse,
    ReturnsRateByChannelResponse,
    ReturnsRateBySkuResponse,
    SalesLinesResponse,
    SalesProfitDashboardResponse,
)
from ..services import analytics_service


router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/returns-rate/sku", response_model=ReturnsRateBySkuResponse)
def returns_rate_by_sku(
    start: str = Query(..., description="ISO datetime, e.g. 2025-01-01T00:00:00Z"),
    end: str = Query(..., description="ISO datetime, e.g. 2026-01-01T00:00:00Z"),
    group_by: Literal["day", "month"] = Query("month"),
    channel: Optional[str] = None,
    sku_code: Optional[str] = None,
    db: Session = Depends(get_db_session),
):
    def parse_dt(s: str) -> datetime:
        v = (s or "").strip()
        if v.endswith("Z"):
            v = v[:-1] + "+00:00"
        dt = datetime.fromisoformat(v)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    payload = analytics_service.returns_rate_by_sku(
        db,
        start=parse_dt(start),
        end=parse_dt(end),
        group_by=group_by,
        channel=channel,
        sku_code=sku_code,
    )
    return payload


@router.get("/returns-rate/channel", response_model=ReturnsRateByChannelResponse)
def returns_rate_by_channel(
    start: str = Query(..., description="ISO datetime, e.g. 2025-01-01T00:00:00Z"),
    end: str = Query(..., description="ISO datetime, e.g. 2026-01-01T00:00:00Z"),
    group_by: Literal["day", "month"] = Query("month"),
    channel: Optional[str] = None,
    db: Session = Depends(get_db_session),
):
    def parse_dt(s: str) -> datetime:
        v = (s or "").strip()
        if v.endswith("Z"):
            v = v[:-1] + "+00:00"
        dt = datetime.fromisoformat(v)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    return analytics_service.returns_rate_by_channel(
        db,
        start=parse_dt(start),
        end=parse_dt(end),
        group_by=group_by,
        channel=channel,
    )


@router.get("/after-sales/dashboard", response_model=AfterSalesDashboardResponse)
def after_sales_dashboard(
    start: str = Query(..., description="ISO datetime, e.g. 2025-01-01T00:00:00Z"),
    end: str = Query(..., description="ISO datetime, e.g. 2026-01-01T00:00:00Z"),
    group_by: Literal["week", "month"] = Query("week"),
    channel: Optional[str] = None,
    top_n: int = 12,
    view: Literal["factory", "ops"] = Query("factory", description="factory=发货归因口径; ops=申请口径全量"),
    db: Session = Depends(get_db_session),
):
    def parse_dt(s: str) -> datetime:
        v = (s or "").strip()
        if v.endswith("Z"):
            v = v[:-1] + "+00:00"
        dt = datetime.fromisoformat(v)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    return analytics_service.after_sales_dashboard(
        db,
        start=parse_dt(start),
        end=parse_dt(end),
        group_by=group_by,
        channel=channel,
        top_n=top_n,
        view=view,
    )


@router.get("/profit/sku", response_model=ProfitBySkuResponse)
def profit_by_sku(
    start: str = Query(..., description="ISO datetime, e.g. 2025-01-01T00:00:00Z"),
    end: str = Query(..., description="ISO datetime, e.g. 2026-01-01T00:00:00Z"),
    group_by: Literal["day", "month"] = Query("month"),
    channel: Optional[str] = None,
    sku_code: Optional[str] = None,
    db: Session = Depends(get_db_session),
):
    def parse_dt(s: str) -> datetime:
        v = (s or "").strip()
        if v.endswith("Z"):
            v = v[:-1] + "+00:00"
        dt = datetime.fromisoformat(v)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    return analytics_service.profit_by_sku(
        db,
        start=parse_dt(start),
        end=parse_dt(end),
        group_by=group_by,
        channel=channel,
        sku_code=sku_code,
    )


@router.get("/profit/channel", response_model=ProfitByChannelResponse)
def profit_by_channel(
    start: str = Query(..., description="ISO datetime, e.g. 2025-01-01T00:00:00Z"),
    end: str = Query(..., description="ISO datetime, e.g. 2026-01-01T00:00:00Z"),
    group_by: Literal["day", "month"] = Query("month"),
    channel: Optional[str] = None,
    db: Session = Depends(get_db_session),
):
    def parse_dt(s: str) -> datetime:
        v = (s or "").strip()
        if v.endswith("Z"):
            v = v[:-1] + "+00:00"
        dt = datetime.fromisoformat(v)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    return analytics_service.profit_by_channel(
        db,
        start=parse_dt(start),
        end=parse_dt(end),
        group_by=group_by,
        channel=channel,
    )


@router.get("/profit/model", response_model=ProfitByModelResponse)
def profit_by_model(
    start: str = Query(..., description="ISO datetime, e.g. 2025-01-01T00:00:00Z"),
    end: str = Query(..., description="ISO datetime, e.g. 2026-01-01T00:00:00Z"),
    group_by: Literal["day", "month"] = Query("month"),
    channel: Optional[str] = None,
    model_code: Optional[str] = None,
    db: Session = Depends(get_db_session),
):
    def parse_dt(s: str) -> datetime:
        v = (s or "").strip()
        if v.endswith("Z"):
            v = v[:-1] + "+00:00"
        dt = datetime.fromisoformat(v)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    return analytics_service.profit_by_model(
        db,
        start=parse_dt(start),
        end=parse_dt(end),
        group_by=group_by,
        channel=channel,
        model_code=model_code,
    )


@router.get("/models/summary", response_model=ModelInsightsSummaryResponse)
def models_summary(
    start: str = Query(..., description="ISO datetime, e.g. 2025-01-01T00:00:00Z"),
    end: str = Query(..., description="ISO datetime, e.g. 2026-01-01T00:00:00Z"),
    channel: Optional[str] = None,
    bundle_template_code: Optional[str] = None,
    bundle_preset_selector: Optional[str] = None,
    db: Session = Depends(get_db_session),
):
    def parse_dt(s: str) -> datetime:
        v = (s or "").strip()
        if v.endswith("Z"):
            v = v[:-1] + "+00:00"
        dt = datetime.fromisoformat(v)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    return analytics_service.model_insights_summary(
        db,
        start=parse_dt(start),
        end=parse_dt(end),
        channel=channel,
        bundle_template_code=bundle_template_code,
        bundle_preset_selector=bundle_preset_selector,
    )


@router.get("/models/detail", response_model=ModelInsightsDetailResponse)
def models_detail(
    start: str = Query(..., description="ISO datetime, e.g. 2025-01-01T00:00:00Z"),
    end: str = Query(..., description="ISO datetime, e.g. 2026-01-01T00:00:00Z"),
    model_code: str = Query(..., description="model_code"),
    channel: Optional[str] = None,
    version_id: Optional[str] = None,
    bundle_template_code: Optional[str] = None,
    bundle_preset_selector: Optional[str] = None,
    db: Session = Depends(get_db_session),
):
    def parse_dt(s: str) -> datetime:
        v = (s or "").strip()
        if v.endswith("Z"):
            v = v[:-1] + "+00:00"
        dt = datetime.fromisoformat(v)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    return analytics_service.model_insights_detail(
        db,
        start=parse_dt(start),
        end=parse_dt(end),
        channel=channel,
        model_code=model_code,
        version_id=version_id,
        bundle_template_code=bundle_template_code,
        bundle_preset_selector=bundle_preset_selector,
    )


@router.get("/models/materials-summary", response_model=ModelUsageMaterialSummaryResponse)
def model_usage_materials_summary(
    start: str = Query(..., description="ISO datetime, e.g. 2025-01-01T00:00:00Z"),
    end: str = Query(..., description="ISO datetime, e.g. 2026-01-01T00:00:00Z"),
    model_code: str = Query(..., description="model_code"),
    channel: Optional[str] = None,
    version_id: Optional[str] = None,
    db: Session = Depends(get_db_session),
):
    def parse_dt(s: str) -> datetime:
        v = (s or "").strip()
        if v.endswith("Z"):
            v = v[:-1] + "+00:00"
        dt = datetime.fromisoformat(v)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    return analytics_service.model_usage_materials_summary(
        db,
        start=parse_dt(start),
        end=parse_dt(end),
        model_code=model_code,
        channel=channel,
        version_id=version_id,
    )


@router.get("/models/processes-summary", response_model=ModelUsageProcessSummaryResponse)
def model_usage_processes_summary(
    start: str = Query(..., description="ISO datetime, e.g. 2025-01-01T00:00:00Z"),
    end: str = Query(..., description="ISO datetime, e.g. 2026-01-01T00:00:00Z"),
    model_code: str = Query(..., description="model_code"),
    channel: Optional[str] = None,
    version_id: Optional[str] = None,
    db: Session = Depends(get_db_session),
):
    def parse_dt(s: str) -> datetime:
        v = (s or "").strip()
        if v.endswith("Z"):
            v = v[:-1] + "+00:00"
        dt = datetime.fromisoformat(v)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    return analytics_service.model_usage_processes_summary(
        db,
        start=parse_dt(start),
        end=parse_dt(end),
        model_code=model_code,
        channel=channel,
        version_id=version_id,
    )


@router.get("/sales/lines", response_model=SalesLinesResponse)
def sales_lines(
    start: str = Query(..., description="ISO datetime, e.g. 2025-01-01T00:00:00Z"),
    end: str = Query(..., description="ISO datetime, e.g. 2026-01-01T00:00:00Z"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    channel: Optional[str] = None,
    sku_code: Optional[str] = None,
    shipment_no: Optional[str] = None,
    order_no: Optional[str] = None,
    product_link_id: Optional[str] = None,
    bound_model_code: Optional[str] = None,
    bundle_template_code: Optional[str] = None,
    bundle_preset_selector: Optional[str] = None,
    include_missing: bool = True,
    db: Session = Depends(get_db_session),
):
    def parse_dt(s: str) -> datetime:
        v = (s or "").strip()
        if v.endswith("Z"):
            v = v[:-1] + "+00:00"
        dt = datetime.fromisoformat(v)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    return analytics_service.sales_lines(
        db,
        start=parse_dt(start),
        end=parse_dt(end),
        page=page,
        page_size=page_size,
        channel=channel,
        sku_code=sku_code,
        shipment_no=shipment_no,
        order_no=order_no,
        product_link_id=product_link_id,
        bound_model_code=bound_model_code,
        bundle_template_code=bundle_template_code,
        bundle_preset_selector=bundle_preset_selector,
        include_missing=include_missing,
    )


@router.get("/sales/profit-dashboard", response_model=SalesProfitDashboardResponse)
def sales_profit_dashboard(
    start: str = Query(..., description="ISO datetime, e.g. 2025-01-01T00:00:00Z"),
    end: str = Query(..., description="ISO datetime, e.g. 2026-01-01T00:00:00Z"),
    group_by: Literal["week", "month"] = Query("week"),
    channel: Optional[str] = None,
    top_n: int = 12,
    db: Session = Depends(get_db_session),
):
    def parse_dt(s: str) -> datetime:
        v = (s or "").strip()
        if v.endswith("Z"):
            v = v[:-1] + "+00:00"
        dt = datetime.fromisoformat(v)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    return analytics_service.sales_profit_dashboard(
        db,
        start=parse_dt(start),
        end=parse_dt(end),
        group_by=group_by,
        channel=channel,
        top_n=top_n,
    )

