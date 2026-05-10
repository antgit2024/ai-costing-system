"""Finance → costing C1 client service。

按契约 `DOC/costing/blueprints/finance_to_costing_c1_contract_v1.md` v1.0
§3 实现 5 个 GET endpoint 的拉取 + 5 分钟 TTL 缓存 + finance 挂时降级。

设计要点(派单 brief §2.1 + §3):
    - sync httpx (现有 `executor_client` / `benchmark_client` 也是 sync · 风格一致)
    - 缓存 keyed by 完整 query params · `cachetools.TTLCache` · TTL 来自
      settings.finance_c1_cache_ttl_seconds (默认 300s)
    - 失败降级:
        * `httpx.RequestError` (网络错/超时) → 用 cache (有则给) ·  并把
          envelope.data_source = 'cache' 让前端 Badge 显示 🟡
        * 5xx (含 503 UPSTREAM_DEPENDENCY_DOWN) → 用 cache + log warning
        * 401 / 403 → raise FinanceC1AuthError (不降级 ·  让运维知道 key 错)
        * 400 → raise FinanceC1ClientError (程序 bug · 必须让上层炸出来)
        * 429 → 直接抛 (限流不该被吃掉 · 让上层重试逻辑/告警感知)
    - X-Costing-Api-Key 自动注入 ·  payroll 自动加 X-Payroll-Authorized: true
      (前提 `settings.finance_c1_payroll_authorized=True`)
    - Mock 模式: `settings.finance_c1_use_mock=True` 时直接返回
      `tests/mocks/finance_c1_mock` 数据 ·  不发 HTTP ·  envelope.data_source='mock'

注: client 不是 singleton; Router 每个请求 new 一个 (内存极小开销) · 但
缓存是 module-level TTLCache · 跨请求共享(不然 5 分钟 TTL 等于失效)。
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx
from cachetools import TTLCache

from ...config import settings
from .finance_c1_schemas import FinanceC1ListEnvelope

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Module-level cache + last-good store
# ---------------------------------------------------------------------------

# `_cache` 存命中(TTL 内)·`_last_good` 永远存最近一次成功结果(用于 finance
# 挂掉时降级 — 即使 TTL 已过期 ·  也优于「直接抛 503」)。
_cache: TTLCache = TTLCache(maxsize=128, ttl=settings.finance_c1_cache_ttl_seconds)
_last_good: Dict[Tuple[str, ...], Tuple[float, List[Dict[str, Any]], Optional[str]]] = {}


def clear_cache() -> None:
    """清空 module-level 缓存(测试用)。"""

    _cache.clear()
    _last_good.clear()


def _rebuild_cache_with_current_ttl() -> None:
    """让 `settings.finance_c1_cache_ttl_seconds` 改了后能在测试里立刻生效。

    生产从不调用; 仅 test fixture 调。
    """

    global _cache
    _cache = TTLCache(maxsize=128, ttl=settings.finance_c1_cache_ttl_seconds)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class FinanceC1Error(RuntimeError):
    """C1 client 通用异常基类。"""


class FinanceC1AuthError(FinanceC1Error):
    """401 / 403 / PAYROLL_NOT_AUTHORIZED — 配置错误必须修 ·  不降级。"""


class FinanceC1ClientError(FinanceC1Error):
    """400 INVALID_QUERY 等程序 bug — 必须暴露给调用方。"""


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class FinanceC1Client:
    """对接 finance-analyzer C1 API 的轻量 sync client。

    单实例可复用; 不持有连接池(每次请求 new httpx.Client 短连接 ·  finance C1
    QPS 不高 · 不需要连接复用)。
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        payroll_authorized: Optional[bool] = None,
        use_mock: Optional[bool] = None,
        timeout: Optional[float] = None,
    ) -> None:
        self.base_url = (base_url or settings.finance_c1_base_url).rstrip("/")
        self.api_key = api_key or settings.finance_c1_api_key
        self.payroll_authorized = (
            settings.finance_c1_payroll_authorized
            if payroll_authorized is None
            else payroll_authorized
        )
        self.use_mock = (
            settings.finance_c1_use_mock if use_mock is None else use_mock
        )
        self.timeout = timeout or settings.finance_c1_timeout_seconds

    # ------------------------------------------------------------------
    # 内部: header / cache key / 实际拉取
    # ------------------------------------------------------------------

    def _headers(self, *, payroll: bool = False) -> Dict[str, str]:
        headers: Dict[str, str] = {
            "Accept": "application/json",
            "X-Costing-Api-Key": self.api_key or "",
        }
        if payroll:
            # 契约 §3.5: 没开 payroll_authorized 又调 list_payroll → 直接抛 ·
            # 避免「明知道会 403 还硬发」浪费一次 RTT + 在 finance log 上留无意义的拒绝。
            if not self.payroll_authorized:
                raise FinanceC1AuthError(
                    "payroll endpoint requires payroll_authorized=True "
                    "(set FINANCE_C1_PAYROLL_AUTHORIZED=true to enable)"
                )
            headers["X-Payroll-Authorized"] = "true"
        return headers

    @staticmethod
    def _build_cache_key(path: str, params: Dict[str, Any]) -> Tuple[str, ...]:
        """缓存 key = (path, sorted-frozen tuple of (k,v))。

        Tuple-of-tuples 而非 dict 是因为 TTLCache 的 key 必须 hashable。
        """

        items = tuple(sorted((str(k), str(v)) for k, v in params.items() if v is not None))
        return (path,) + items

    def _record_last_good(
        self,
        cache_key: Tuple[str, ...],
        data: List[Dict[str, Any]],
        api_version: Optional[str],
    ) -> None:
        """成功命中后写入 _cache + _last_good。

        _last_good 与 TTLCache 不同 ·  不会过期; 用于 finance 长时间挂掉时
        最后兜底(契约 §6.3 cache 5 分钟 TTL 是「正常运转期 SLA」 ·  挂了
        我们不忍心给用户 503 ·  故有 _last_good)。
        """

        envelope_payload = (time.time(), data, api_version)
        _cache[cache_key] = envelope_payload
        _last_good[cache_key] = envelope_payload

    # ------------------------------------------------------------------
    # Mock 分支
    # ------------------------------------------------------------------

    def _mock_envelope(self, kind: str, **filters: Any) -> FinanceC1ListEnvelope:
        # Lazy-import: 让生产 deploy 不打包 tests 目录时也能跑 (use_mock=False)
        try:
            from tests.mocks import finance_c1_mock as mock_data  # type: ignore
        except ImportError:  # pragma: no cover — dev-only path
            from backend.tests.mocks import finance_c1_mock as mock_data  # type: ignore

        if kind == "companies":
            data = mock_data.get_companies(
                entity_role=filters.get("entity_role"),
                is_active=filters.get("is_active"),
            )
        elif kind == "stores":
            data = mock_data.get_stores(
                company_id=filters.get("company_id"),
                is_active=filters.get("is_active"),
            )
        elif kind == "employees":
            data = mock_data.get_employees(
                contract_company_id=filters.get("contract_company_id"),
                is_active=filters.get("is_active"),
            )
        elif kind == "fixed_costs":
            data = mock_data.get_fixed_costs(
                period_year=filters.get("period_year"),
                period_month=filters.get("period_month"),
                cost_category=filters.get("cost_category"),
                company_id=filters.get("company_id"),
            )
        elif kind == "payroll":
            data = mock_data.get_payroll(
                company_id=filters["company_id"],
                period_year=filters["period_year"],
                period_month=filters["period_month"],
            )
        else:  # pragma: no cover — guarded at call site
            raise ValueError(f"unknown mock kind: {kind}")

        return FinanceC1ListEnvelope(
            data=data,
            data_source="mock",
            cache_age_seconds=None,
            fetched_at=datetime.now(timezone.utc),
            api_version="1.0-mock",
            pagination={
                "page": 1,
                "page_size": len(data),
                "total": len(data),
                "total_pages": 1,
            },
        )

    # ------------------------------------------------------------------
    # 真 HTTP 分支
    # ------------------------------------------------------------------

    def _fetch_list(
        self,
        path: str,
        params: Dict[str, Any],
        *,
        payroll: bool = False,
    ) -> FinanceC1ListEnvelope:
        """实际发 HTTP + 命中缓存 / 失败降级。

        path 形如 ``/api/v1/c1/companies``  ·  params 是 query string 字典。
        """

        cache_key = self._build_cache_key(path, params)
        # 1. TTL 内命中 → 直接返回(envelope.data_source='live' 因为是「真 finance
        #    返回过的」 · 只是被 cache 复用; 前端如果需要区分「这次走了 cache」可看
        #    age=0 vs >0;为了让 5 min TTL 的稳定期 Badge 显示绿色 · 我们这里仍标 live)。
        cached = _cache.get(cache_key)
        if cached is not None:
            ts, data, api_version = cached
            return FinanceC1ListEnvelope(
                data=data,
                data_source="live",
                cache_age_seconds=max(0.0, time.time() - ts),
                fetched_at=datetime.fromtimestamp(ts, tz=timezone.utc),
                api_version=api_version,
            )

        url = f"{self.base_url}{path}"
        headers = self._headers(payroll=payroll)

        # 2. 没命中 → 发 HTTP
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(url, params=params, headers=headers)
        except httpx.RequestError as exc:
            # 网络错 / 超时: finance 挂了 ·  尝试用 _last_good 兜底 ·  否则抛。
            return self._fallback_or_raise(cache_key, exc)

        # 3. 解析 status
        if response.status_code in (401, 403):
            # 鉴权错: 不降级。前端会看到 50x ·  运维必须修 finance api key 配置。
            raise FinanceC1AuthError(
                f"finance C1 auth failed: {response.status_code} {response.text[:200]}"
            )
        if response.status_code == 400:
            raise FinanceC1ClientError(
                f"finance C1 400 INVALID_QUERY: {response.text[:200]}"
            )
        if response.status_code == 429:
            # 契约 §6.2 限流 ·  让上层处理 retry-after。
            raise FinanceC1Error(
                f"finance C1 429 RATE_LIMIT: retry-after="
                f"{response.headers.get('Retry-After')}"
            )
        if response.status_code >= 500:
            # 5xx: finance 内部错 · 用 _last_good 降级。
            return self._fallback_or_raise(
                cache_key, RuntimeError(f"finance C1 {response.status_code}")
            )

        try:
            payload = response.json()
        except ValueError as exc:
            return self._fallback_or_raise(cache_key, exc)

        data = payload.get("data") or []
        if not isinstance(data, list):
            return self._fallback_or_raise(
                cache_key, RuntimeError("finance C1 'data' field is not a list")
            )

        api_version = (
            payload.get("_api_version")
            or response.headers.get("X-Api-Version")
        )
        pagination = payload.get("pagination")

        # 4. 成功 → 写 cache + last_good
        self._record_last_good(cache_key, data, api_version)
        return FinanceC1ListEnvelope(
            data=data,
            data_source="live",
            cache_age_seconds=0.0,
            fetched_at=datetime.now(timezone.utc),
            api_version=api_version,
            pagination=pagination if isinstance(pagination, dict) else None,
        )

    def _fallback_or_raise(
        self, cache_key: Tuple[str, ...], exc: BaseException
    ) -> FinanceC1ListEnvelope:
        """finance 挂或返回非 200 时的统一降级。

        有 _last_good ·  返回 envelope.data_source='cache' ·  前端 Badge 黄色;
        没有 ·  抛 FinanceC1Error 让上层 (router) 翻成 503。
        """

        last = _last_good.get(cache_key)
        if last is None:
            logger.warning(
                "finance_c1_unavailable_no_cache cache_key=%s exc=%s",
                cache_key,
                exc,
            )
            raise FinanceC1Error(f"finance C1 unavailable and no cached data: {exc}") from exc

        ts, data, api_version = last
        age = max(0.0, time.time() - ts)
        logger.warning(
            "finance_c1_degraded_to_cache cache_key=%s age=%.1fs exc=%s",
            cache_key,
            age,
            exc,
        )
        return FinanceC1ListEnvelope(
            data=data,
            data_source="cache",
            cache_age_seconds=age,
            fetched_at=datetime.fromtimestamp(ts, tz=timezone.utc),
            api_version=api_version,
        )

    # ------------------------------------------------------------------
    # 5 个公开方法 (派单 §2.1)
    # ------------------------------------------------------------------

    def list_companies(
        self,
        *,
        entity_role: Optional[str] = None,
        is_active: Optional[bool] = True,
    ) -> FinanceC1ListEnvelope:
        params: Dict[str, Any] = {}
        if entity_role:
            params["entity_role"] = entity_role
        if is_active is not None:
            params["is_active"] = "true" if is_active else "false"
        if self.use_mock:
            return self._mock_envelope("companies", entity_role=entity_role, is_active=is_active)
        return self._fetch_list("/api/v1/c1/companies", params)

    def list_stores(
        self,
        *,
        company_id: Optional[str] = None,
        platform: Optional[str] = None,
        is_active: Optional[bool] = True,
    ) -> FinanceC1ListEnvelope:
        params: Dict[str, Any] = {}
        if company_id:
            params["company_id"] = company_id
        if platform:
            params["platform"] = platform
        if is_active is not None:
            params["is_active"] = "true" if is_active else "false"
        if self.use_mock:
            return self._mock_envelope("stores", company_id=company_id, is_active=is_active)
        return self._fetch_list("/api/v1/c1/stores", params)

    def list_employees(
        self,
        *,
        contract_company_id: Optional[str] = None,
        is_active: Optional[bool] = True,
    ) -> FinanceC1ListEnvelope:
        params: Dict[str, Any] = {}
        if contract_company_id:
            params["contract_company_id"] = contract_company_id
        if is_active is not None:
            params["is_active"] = "true" if is_active else "false"
        if self.use_mock:
            return self._mock_envelope(
                "employees", contract_company_id=contract_company_id, is_active=is_active
            )
        return self._fetch_list("/api/v1/c1/employees", params)

    def list_fixed_costs(
        self,
        *,
        period_year: int,
        period_month: int,
        cost_category: Optional[str] = None,
        company_id: Optional[str] = None,
    ) -> FinanceC1ListEnvelope:
        params: Dict[str, Any] = {
            "period_year": period_year,
            "period_month": period_month,
        }
        if cost_category:
            params["cost_category"] = cost_category
        if company_id:
            params["company_id"] = company_id
        if self.use_mock:
            return self._mock_envelope(
                "fixed_costs",
                period_year=period_year,
                period_month=period_month,
                cost_category=cost_category,
                company_id=company_id,
            )
        return self._fetch_list("/api/v1/c1/fixed-costs", params)

    def list_payroll(
        self,
        *,
        company_id: str,
        period_year: int,
        period_month: int,
        aggregation: str = "by_department",
    ) -> FinanceC1ListEnvelope:
        params: Dict[str, Any] = {
            "company_id": company_id,
            "period_year": period_year,
            "period_month": period_month,
            "aggregation": aggregation,
        }
        if self.use_mock:
            return self._mock_envelope(
                "payroll",
                company_id=company_id,
                period_year=period_year,
                period_month=period_month,
            )
        return self._fetch_list("/api/v1/c1/payroll", params, payroll=True)


# ---------------------------------------------------------------------------
# Factory — Router 用
# ---------------------------------------------------------------------------


def get_finance_c1_client() -> FinanceC1Client:
    """Default factory · 用 settings 默认值构造。Router 每请求一个 client。

    cache 是 module-level ·  跨实例共享 ·  所以 new 客户端不丢命中。
    """

    return FinanceC1Client()


__all__ = [
    "FinanceC1Client",
    "FinanceC1Error",
    "FinanceC1AuthError",
    "FinanceC1ClientError",
    "get_finance_c1_client",
    "clear_cache",
]
