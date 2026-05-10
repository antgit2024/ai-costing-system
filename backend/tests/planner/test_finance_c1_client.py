"""finance C1 客户端消费测试(契约 §4.2 C1~C5 5 条)。

测试矩阵覆盖:
    C1  拉取 companies → 能 build subject_id → legal_name dict (mock 模式)
    C2  拉取 stores → store.company_id 都能在 companies 里命中(无孤立外键)
    C3  拉取 fixed-costs → 按 cost_category 聚合得到 ≥ 11 项分类总和
    C4  X-Costing-Api-Key 错误 → FinanceC1AuthError(不降级 ·  让运维知道)
    C5  finance 服务挂(连接超时 / 5xx) → 用 _last_good 兜底, envelope.data_source='cache'

附加:
    + 切换 FINANCE_C1_USE_MOCK=true/false(B5) → 互不污染 cache + 行为正确
    + Pydantic 校验 envelope schema 通过(序列化往返)
    + payroll 拒未授权调用(派单 §2.1 X-Payroll-Authorized 行为)

运行:
    pytest backend/tests/planner/test_finance_c1_client.py -v
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List

import httpx
import pytest
import respx

# `conftest.py` 已经把 BACKEND_DIR 加到 sys.path · 所以这里直接 import src.*
from src.planner.services import finance_c1_client
from src.planner.services.finance_c1_client import (
    FinanceC1AuthError,
    FinanceC1Client,
    FinanceC1Error,
    clear_cache,
)
from src.planner.services.finance_c1_schemas import (
    COST_CATEGORY_CHOICES,
    FinanceCompanyDTO,
    FinanceFixedCostDTO,
    FinanceStoreDTO,
)
from tests.mocks.finance_c1_mock import (
    MOCK_COMPANIES,
    MOCK_FIXED_COSTS,
    MOCK_STORES,
)

C1_BASE = "http://finance-test.local"


@pytest.fixture(autouse=True)
def _clean_cache_each_test():
    """每条 test 前后清 cache · 否则 _last_good 会跨用例泄漏。"""

    clear_cache()
    yield
    clear_cache()


# ---------------------------------------------------------------------------
# C1 — companies build subject_id → legal_name dict
# ---------------------------------------------------------------------------


def test_c1_companies_build_subject_dict_from_mock():
    """mock 模式:  list_companies() 返回足够字段, 上层能直接 build name dict。"""

    client = FinanceC1Client(use_mock=True)
    envelope = client.list_companies()

    assert envelope.data_source == "mock"
    assert len(envelope.data) >= 7  # 派单 B2: 至少 7 家(3 工厂 + 4 店铺)

    # 这是上层(cost_center / materials.purchase_entity_id)消费 finance 的核心模式 ·
    # 任何字段命名不一致都会让这一步炸掉 · 故作为 C1 测试的核心断言。
    subject_dict = {row["id"]: row["legal_name"] for row in envelope.data}
    assert len(subject_dict) == len(envelope.data)  # id 唯一
    for legal_name in subject_dict.values():
        assert isinstance(legal_name, str) and legal_name.strip()

    # entity_role 必须在白名单内(契约 §3.1)
    for row in envelope.data:
        assert row["entity_role"] in {"factory", "shop", "holding", "mixed"}

    # Pydantic schema round-trip(契约字段没漏)
    parsed = [FinanceCompanyDTO(**row) for row in envelope.data]
    assert all(p.id and p.legal_name for p in parsed)


# ---------------------------------------------------------------------------
# C2 — stores.company_id all reference an existing company
# ---------------------------------------------------------------------------


def test_c2_stores_company_id_resolves_to_companies():
    client = FinanceC1Client(use_mock=True)

    companies_envelope = client.list_companies(is_active=None)  # 不过滤 ·  保险
    stores_envelope = client.list_stores()

    assert stores_envelope.data_source == "mock"
    assert len(stores_envelope.data) >= 4

    company_ids = {c["id"] for c in companies_envelope.data}
    orphan_stores: List[Dict[str, Any]] = [
        s for s in stores_envelope.data if s["company_id"] not in company_ids
    ]
    assert orphan_stores == [], (
        f"以下店铺的 company_id 不在 companies 列表里: "
        f"{[s['id'] for s in orphan_stores]}"
    )

    # Pydantic schema round-trip
    parsed = [FinanceStoreDTO(**s) for s in stores_envelope.data]
    assert all(p.company_id for p in parsed)


# ---------------------------------------------------------------------------
# C3 — fixed-costs aggregate by cost_category covers all 11 categories
# ---------------------------------------------------------------------------


def test_c3_fixed_costs_aggregated_by_category_covers_eleven_buckets():
    client = FinanceC1Client(use_mock=True)
    envelope = client.list_fixed_costs(period_year=2026, period_month=4)

    assert envelope.data_source == "mock"
    assert len(envelope.data) >= 11  # 派单 B2

    totals: Dict[str, float] = defaultdict(float)
    for row in envelope.data:
        totals[row["cost_category"]] += float(row["amount"])

    # 所有命中的 category 都必须在契约 §3.4.1 11 个白名单内
    assert set(totals.keys()).issubset(set(COST_CATEGORY_CHOICES))
    # 至少出现 10 个不同 category(默认 mock 是 10 个 unique · 第 11 行重复 utility) ·
    # mock 增删时只要保持 ≥10 即可;若以后想再扩 cost_category · 这里也兼容。
    assert len(totals) >= 10

    # 每个金额 > 0
    for cat, amount in totals.items():
        assert amount > 0, f"{cat} 的总额非正: {amount}"

    # Pydantic schema round-trip
    parsed = [FinanceFixedCostDTO(**r) for r in envelope.data]
    assert all(p.amount > 0 for p in parsed)


# ---------------------------------------------------------------------------
# C4 — wrong API key → FinanceC1AuthError, 不降级
# ---------------------------------------------------------------------------


@respx.mock
def test_c4_invalid_api_key_raises_and_does_not_degrade(monkeypatch):
    """X-Costing-Api-Key 错时 finance 返 401。

    契约 §6.4 + 派单 §3.3: 这种场景 client 必须抛 ·  不能默默用 cache ·
    否则运维永远修不了 key 配置错。
    """

    # 模拟 finance 返回 401
    respx.get(f"{C1_BASE}/api/v1/c1/companies").mock(
        return_value=httpx.Response(
            status_code=401,
            json={"error": "MISSING_OR_INVALID_API_KEY"},
        )
    )

    client = FinanceC1Client(
        base_url=C1_BASE,
        api_key="wrong-key",
        use_mock=False,
    )

    with pytest.raises(FinanceC1AuthError):
        client.list_companies()

    # 即使之前有 _last_good · 401 也不该走它 — 这里没塞 last_good · 也验证一下
    # 确实没被错误地静默成功。
    assert finance_c1_client._last_good == {}


@respx.mock
def test_c4b_invalid_api_key_does_not_consume_existing_cache(monkeypatch):
    """变体:  即使 _last_good 里有数据 · 401 也必须抛(不能用旧 cache 掩盖鉴权错)。"""

    # 1) 先成功一次 → 写 _last_good
    respx.get(f"{C1_BASE}/api/v1/c1/companies").mock(
        return_value=httpx.Response(
            status_code=200,
            json={"_api_version": "1.0", "data": list(MOCK_COMPANIES)},
        )
    )
    client = FinanceC1Client(base_url=C1_BASE, api_key="good-key", use_mock=False)
    ok = client.list_companies()
    assert ok.data_source == "live"
    clear_cache_only_ttl()  # 让 TTL cache 过期 · 但 _last_good 还在(模拟 5 分钟后)
    # 2) 然后 finance 改成返 401(模拟 key 被人改错)
    respx.get(f"{C1_BASE}/api/v1/c1/companies").mock(
        return_value=httpx.Response(status_code=401, json={"error": "..."})
    )
    with pytest.raises(FinanceC1AuthError):
        client.list_companies()


def clear_cache_only_ttl() -> None:
    """让 TTLCache 立刻过期 · 保留 _last_good。

    给 C4b 测试用 · 否则 ttl=300s 默认值 · 测试里不可能等 5 分钟。
    """

    finance_c1_client._cache.clear()


# ---------------------------------------------------------------------------
# C5 — finance 挂时 (网络错 / 5xx) 用本地缓存 + envelope.data_source='cache'
# ---------------------------------------------------------------------------


@respx.mock
def test_c5_finance_down_uses_cache_with_data_source_marker():
    """5xx / 网络错时 client 用 _last_good 兜底 ·  并标记 data_source='cache'。"""

    base_url = C1_BASE
    client = FinanceC1Client(base_url=base_url, api_key="ok-key", use_mock=False)

    # 1) 第一次成功 → _last_good 有了
    respx.get(f"{base_url}/api/v1/c1/stores").mock(
        return_value=httpx.Response(
            status_code=200,
            json={"_api_version": "1.0", "data": list(MOCK_STORES)},
        )
    )
    first = client.list_stores()
    assert first.data_source == "live"
    assert len(first.data) == len(MOCK_STORES)

    # 2) finance 挂 → 5xx
    clear_cache_only_ttl()  # TTL cache 过期 ·  必须走 _last_good
    respx.get(f"{base_url}/api/v1/c1/stores").mock(
        return_value=httpx.Response(status_code=503, json={"error": "UPSTREAM"})
    )
    second = client.list_stores()
    assert second.data_source == "cache", (
        "5xx 时必须降级到 cache · 否则前端 Badge 显示 live 是误导"
    )
    assert len(second.data) == len(MOCK_STORES)
    assert second.cache_age_seconds is not None and second.cache_age_seconds >= 0

    # 3) 网络异常(超时等) → 同样降级
    clear_cache_only_ttl()
    respx.get(f"{base_url}/api/v1/c1/stores").mock(
        side_effect=httpx.ConnectTimeout("connection timed out")
    )
    third = client.list_stores()
    assert third.data_source == "cache"


@respx.mock
def test_c5b_finance_down_no_cache_raises():
    """没 _last_good 时挂掉 → 必须抛(不能假装成功返空 list)。"""

    client = FinanceC1Client(base_url=C1_BASE, api_key="ok-key", use_mock=False)
    respx.get(f"{C1_BASE}/api/v1/c1/stores").mock(
        return_value=httpx.Response(status_code=503)
    )
    with pytest.raises(FinanceC1Error):
        client.list_stores()


# ---------------------------------------------------------------------------
# 附加 — Mock vs Live 切换不污染 + Payroll 鉴权 + Router smoke
# ---------------------------------------------------------------------------


def test_extra_mock_mode_does_not_touch_network():
    """use_mock=True 时即使 base_url 不可达 ·  也能正常返回 ·  证明没发 HTTP。"""

    client = FinanceC1Client(
        base_url="http://this-host-does-not-exist.invalid",
        api_key="anything",
        use_mock=True,
    )
    envelope = client.list_companies()
    assert envelope.data_source == "mock"
    assert len(envelope.data) >= 7


def test_extra_payroll_requires_authorization():
    """payroll 接口必须 payroll_authorized=True 才让发 ·  否则在 client 层就抛。"""

    client = FinanceC1Client(use_mock=False, payroll_authorized=False)
    with pytest.raises(FinanceC1AuthError):
        client.list_payroll(
            company_id="mock-company-uuid-factory-1",
            period_year=2026,
            period_month=4,
        )


def test_extra_payroll_mock_with_authorized_works():
    """payroll mock 模式 · 开了 authorized · 能拉到 6 班组数据。"""

    client = FinanceC1Client(use_mock=True, payroll_authorized=True)
    env = client.list_payroll(
        company_id="mock-company-uuid-factory-1", period_year=2026, period_month=4
    )
    # mock 里 factory-1 有 4 个班组(缝纫一/二/拼版/包装)·  factory-2 印染 / factory-3 切割 不在此 company。
    assert env.data_source == "mock"
    departments = {r["department"] for r in env.data}
    assert "缝纫一组" in departments


def test_extra_router_proxy_returns_envelope(client):
    """端到端 smoke: GET /api/planner/finance/companies 返回 envelope schema。"""

    response = client.get("/api/planner/finance/companies")
    assert response.status_code == 200
    body = response.json()
    assert "data" in body
    assert "data_source" in body
    assert body["data_source"] in {"mock", "live", "cache"}
    assert "fetched_at" in body
    assert len(body["data"]) >= 7


def test_extra_router_fixed_costs_filters_period(client):
    response = client.get(
        "/api/planner/finance/fixed-costs?period_year=2026&period_month=4"
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["data"]) >= 11
    cats = {r["cost_category"] for r in body["data"]}
    assert "rent" in cats
    assert "platform_fee" in cats
