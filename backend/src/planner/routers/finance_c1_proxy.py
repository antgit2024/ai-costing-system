"""Finance C1 代理 router — 让前端不直接调 finance API。

为什么要代理(派单 brief §2.5):
    - 前端拿不到也不该拿到 finance 的 X-Costing-Api-Key
    - 跨域 + 鉴权统一交给 ai-costing 后端处理
    - 缓存复用: 同一份 5 分钟 cache 给所有用户共享(不每个浏览器都拉一次)
    - Mock 切换: dev/staging/prod 切 use_mock 不需要前端改任何代码

挂载路径(派单 §2.5 + §B4):
    `/api/planner/finance/companies` 等

Auth: 沿用 router.py 里的 `require_staff_role` 守卫 (admin/operator/finance
/factory_admin 任一角色可访问)。Internal-only · 不暴露给匿名。

返回包: 我们把 `FinanceC1ListEnvelope` (含 data_source / cache_age_seconds /
fetched_at / api_version) 直接吐给前端 ·  前端的"数据来源"Badge 直接读
data_source 字段渲染。
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status

from ..services.finance_c1_client import (
    FinanceC1AuthError,
    FinanceC1ClientError,
    FinanceC1Error,
    get_finance_c1_client,
)
from ..services.finance_c1_schemas import FinanceC1ListEnvelope

router = APIRouter(prefix="/finance", tags=["Finance C1 Proxy"])

logger = logging.getLogger(__name__)


def _to_http_error(exc: BaseException) -> HTTPException:
    """统一把 client 异常翻成 HTTP 状态。

    - FinanceC1AuthError → 502 BAD_GATEWAY (上游鉴权配置错 ·  让运维感知 ·
      不用 401 因为 401 会被前端 AuthGuard 误读为「自己掉登录」)
    - FinanceC1ClientError → 400 (上游说我们参数错 ·  对前端而言确实是 400)
    - 其他 → 503 (finance 挂 + 没缓存 ·  让前端 Badge 显红色 + 自动重试)
    """

    if isinstance(exc, FinanceC1AuthError):
        return HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "error": "FINANCE_C1_AUTH_FAILED",
                "message": str(exc),
            },
        )
    if isinstance(exc, FinanceC1ClientError):
        return HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "FINANCE_C1_BAD_REQUEST",
                "message": str(exc),
            },
        )
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "error": "FINANCE_C1_UNAVAILABLE",
            "message": str(exc),
        },
    )


# ---------------------------------------------------------------------------
# §3.1 companies
# ---------------------------------------------------------------------------


@router.get(
    "/companies",
    response_model=FinanceC1ListEnvelope,
    summary="finance C1: 法人主体清单 (代理)",
)
def list_finance_companies(
    entity_role: Optional[str] = Query(
        None,
        description="过滤主体角色: factory / shop / holding / mixed",
    ),
    is_active: Optional[bool] = Query(True, description="默认只查启用; 传 false 看全量"),
) -> FinanceC1ListEnvelope:
    client = get_finance_c1_client()
    try:
        return client.list_companies(entity_role=entity_role, is_active=is_active)
    except FinanceC1Error as exc:
        raise _to_http_error(exc) from exc


# ---------------------------------------------------------------------------
# §3.2 stores
# ---------------------------------------------------------------------------


@router.get(
    "/stores",
    response_model=FinanceC1ListEnvelope,
    summary="finance C1: 店铺清单 (代理)",
)
def list_finance_stores(
    company_id: Optional[str] = Query(None),
    platform: Optional[str] = Query(None, description="tmall / taobao / jd / douyin / ..."),
    is_active: Optional[bool] = Query(True),
) -> FinanceC1ListEnvelope:
    client = get_finance_c1_client()
    try:
        return client.list_stores(
            company_id=company_id, platform=platform, is_active=is_active
        )
    except FinanceC1Error as exc:
        raise _to_http_error(exc) from exc


# ---------------------------------------------------------------------------
# §3.3 employees
# ---------------------------------------------------------------------------


@router.get(
    "/employees",
    response_model=FinanceC1ListEnvelope,
    summary="finance C1: 员工花名册 (代理)",
)
def list_finance_employees(
    contract_company_id: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(True),
) -> FinanceC1ListEnvelope:
    client = get_finance_c1_client()
    try:
        return client.list_employees(
            contract_company_id=contract_company_id, is_active=is_active
        )
    except FinanceC1Error as exc:
        raise _to_http_error(exc) from exc


# ---------------------------------------------------------------------------
# §3.4 fixed-costs
# ---------------------------------------------------------------------------


@router.get(
    "/fixed-costs",
    response_model=FinanceC1ListEnvelope,
    summary="finance C1: 固定开支台账 (代理)",
)
def list_finance_fixed_costs(
    period_year: int = Query(..., ge=2000, le=2100),
    period_month: int = Query(..., ge=1, le=12),
    cost_category: Optional[str] = Query(
        None,
        description="按 §3.4.1 标准枚举过滤 (rent/utility/salary_admin/...)",
    ),
    company_id: Optional[str] = Query(None),
) -> FinanceC1ListEnvelope:
    client = get_finance_c1_client()
    try:
        return client.list_fixed_costs(
            period_year=period_year,
            period_month=period_month,
            cost_category=cost_category,
            company_id=company_id,
        )
    except FinanceC1Error as exc:
        raise _to_http_error(exc) from exc


# ---------------------------------------------------------------------------
# §3.5 payroll (高敏感, 需要 settings.finance_c1_payroll_authorized=True)
# ---------------------------------------------------------------------------


@router.get(
    "/payroll",
    response_model=FinanceC1ListEnvelope,
    summary="finance C1: 工资单按月聚合 (代理 · 高敏感)",
)
def list_finance_payroll(
    company_id: str = Query(...),
    period_year: int = Query(..., ge=2000, le=2100),
    period_month: int = Query(..., ge=1, le=12),
    aggregation: str = Query("by_department"),
) -> FinanceC1ListEnvelope:
    client = get_finance_c1_client()
    try:
        return client.list_payroll(
            company_id=company_id,
            period_year=period_year,
            period_month=period_month,
            aggregation=aggregation,
        )
    except FinanceC1Error as exc:
        raise _to_http_error(exc) from exc
