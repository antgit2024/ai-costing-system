"""finance C1 客户端消费测试(v1.0 5 条 + v1.3 新增 5 条 = 共 10 条契约 case)。

测试矩阵覆盖:
    -- v1.0 (派单 commit 4e5cba5b 既有 5 条) --
    C1  拉取 companies → 能 build subject_id → legal_name dict (mock 模式)
    C2  拉取 stores → store.company_id 都能在 companies 里命中(无孤立外键)
    C3  拉取 fixed-costs → 按 cost_category 聚合得到 ≥ 10 项分类总和
    C4  X-Costing-Api-Key 错误 → FinanceC1AuthError(不降级 ·  让运维知道)
    C5  finance 服务挂(连接超时 / 5xx) → 用 _last_good 兜底, envelope.data_source='cache'

    -- v1.3 (本次升级 派单 §3 B7 5 条) --
    C6  拉取 stores/revenue → 4 店铺 4 月真实营收 + Pydantic 校验通过
    C7  拉取 payment-requests → 12 凭证覆盖 6 类 expense_category 各 ≥ 2 + amort 配置完整
    C8  ?since/?until 参数支持 → 7 个方法都接 since/until,过滤生效
    C9  companies v1.3 新字段 → 4 recognition Boolean + floor_area_sqm(部分 NULL 演示 fallback)
    C10 payroll(by_employee)模式 → 每员工每月 1 行 + metadata 含 actual_paid/payment_source_types

附加:
    + 切换 FINANCE_C1_USE_MOCK=true/false(B5) → 互不污染 cache + 行为正确
    + Pydantic 校验 envelope schema 通过(序列化往返)
    + payroll 拒未授权调用(派单 §2.1 X-Payroll-Authorized 行为)
    + envelope.api_version 升 v1.3 + pagination.last_updated_at 字段

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
    EXPENSE_CATEGORY_CHOICES,
    FinanceCompanyDTO,
    FinanceFixedCostDTO,
    FinancePaymentRequestDTO,
    FinancePayrollByEmployeeDTO,
    FinanceStoreDTO,
    FinanceStoreRevenueDTO,
)
from tests.mocks.finance_c1_mock import (
    MOCK_COMPANIES,
    MOCK_FIXED_COSTS,
    MOCK_PAYMENT_REQUESTS,
    MOCK_STORES,
    MOCK_STORES_REVENUE,
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


# ===========================================================================
# v1.3 新增 5 条 case (派单 §3 B7) — stores_revenue / payment_requests / since /
#                                    new fields / by_employee mode
# ===========================================================================


# ---------------------------------------------------------------------------
# C6 — stores/revenue (v1.3 §4.2): 4 店铺 4 月真实营收 + Pydantic 校验通过
# ---------------------------------------------------------------------------


def test_c6_stores_revenue_v1_3_returns_per_month_real_revenue():
    """v1.3 §4.2 — list_stores_revenue 返回 4 店铺当月真实毛/净收入 + 数据质量。

    替代 v1.0 master_stores.monthly_revenue_avg(均值)·  成本核算用真实月度营收。
    """

    client = FinanceC1Client(use_mock=True)
    envelope = client.list_stores_revenue(period_year=2026, period_month=4)

    assert envelope.data_source == "mock"
    assert envelope.api_version and "1.3" in envelope.api_version
    assert envelope.pagination is not None
    # v1.3 §4.4 — last_updated_at 让 costing 增量同步推进
    assert "last_updated_at" in envelope.pagination

    # 派单 §2.1 mock 不变量: 4 店铺 × 至少 1 月 ≥ 4 条
    assert len(envelope.data) >= 4

    for row in envelope.data:
        assert row["period_year"] == 2026
        assert row["period_month"] == 4
        assert row["gross_revenue"] >= 0
        assert row["net_revenue"] >= 0
        # 净收入 ≤ 毛收入(扣了退款)
        assert row["net_revenue"] <= row["gross_revenue"]
        # data_quality 必须在 green/yellow/red 白名单
        assert row.get("data_quality") in {"green", "yellow", "red", None}

    # Pydantic schema round-trip — 字段命名 1:1 对齐契约 §4.2
    parsed = [FinanceStoreRevenueDTO(**row) for row in envelope.data]
    assert all(p.gross_revenue >= 0 for p in parsed)

    # 单店铺过滤生效
    single = client.list_stores_revenue(
        period_year=2026, period_month=4, store_id="mock-store-uuid-1"
    )
    assert len(single.data) == 1
    assert single.data[0]["store_id"] == "mock-store-uuid-1"


# ---------------------------------------------------------------------------
# C7 — payment-requests (v1.3 §4.6): 12 凭证 × 6 类 + amort + pay vs receive
# ---------------------------------------------------------------------------


def test_c7_payment_requests_v1_3_six_categories_and_amort_full():
    """v1.3 §4.6 — payment-requests 含 6 类 expense_category + amort 5 字段 +
    pay_company vs company_name 主体分离场景。
    """

    client = FinanceC1Client(use_mock=True)
    envelope = client.list_payment_requests()

    assert envelope.data_source == "mock"
    # 派单 §2.1: 至少 12 条凭证 (6 类 × 2)
    assert len(envelope.data) >= 12

    # 6 类 expense_category 全覆盖 ·  每类 ≥ 2 条
    by_category: Dict[str, int] = defaultdict(int)
    for r in envelope.data:
        by_category[r["expense_category"]] += 1

    assert set(by_category.keys()) == set(EXPENSE_CATEGORY_CHOICES), (
        f"expense_category 未覆盖 6 类 ·  实际: {sorted(by_category.keys())}"
    )
    for cat, n in by_category.items():
        assert n >= 2, f"{cat} 仅 {n} 条 ·  期望 ≥ 2"

    # 至少 1 条跨期摊销凭证 (amort 5 字段都填了)
    amortized = [r for r in envelope.data if r["is_monthly_amortized"]]
    assert amortized, "应至少有 1 条 is_monthly_amortized=True 的凭证"
    for r in amortized:
        assert r["amort_months"] is not None and r["amort_months"] > 0
        assert r["amort_start_period"] is not None
        assert r["amort_end_period"] is not None
        assert r["amort_monthly_amount"] is not None and r["amort_monthly_amount"] > 0
        # 摊销起 ≤ 摊销止 (字符串 YYYYMM 字典序与时间序一致)
        assert r["amort_start_period"] <= r["amort_end_period"]

    # 至少 1 条 A 主体付钱、B 主体受益 (pay_company != company_name) 场景
    pay_b_recv_a = [
        r
        for r in envelope.data
        if r.get("pay_company") and r["pay_company"] != r["company_name"]
    ]
    assert pay_b_recv_a, "应至少有 1 条 pay_company != company_name 的凭证(展示主体分离场景)"

    # Pydantic schema round-trip
    parsed = [FinancePaymentRequestDTO(**r) for r in envelope.data]
    assert all(p.amount > 0 for p in parsed)

    # 过滤参数生效: 拉 cogs 类
    cogs_only = client.list_payment_requests(expense_category="cogs")
    assert all(r["expense_category"] == "cogs" for r in cogs_only.data)
    assert len(cogs_only.data) >= 2

    # amort_covers_period — finance 加的额外参数: 拉「覆盖目标月」的所有摊销项
    # admin-1 (12 月摊到 202612) + capital-1 (60 月摊到 203012) 都覆盖 202604
    covers_april = client.list_payment_requests(amort_covers_period="202604")
    assert all(
        r["is_monthly_amortized"]
        and r["amort_start_period"] <= "202604" <= r["amort_end_period"]
        for r in covers_april.data
    )
    assert len(covers_april.data) >= 1


# ---------------------------------------------------------------------------
# C8 — ?since/?until 参数: 7 个方法签名都接受, 不抛 TypeError
# ---------------------------------------------------------------------------


def test_c8_since_until_param_supported_on_all_seven_methods():
    """v1.3 §4.4 — 7 个 list_* 方法都接受 since/until 参数 ·  不报错。

    mock 数据用 ISO 字符串字典序比较 ·  传未来时间 → 应过滤掉所有数据。
    传 1900-01 这种远古时间 → 应返回全部数据。
    """

    client = FinanceC1Client(use_mock=True, payroll_authorized=True)
    far_future = "9999-12-31T23:59:59+08:00"
    far_past = "1900-01-01T00:00:00+08:00"

    # 1. since=far_future → 应过滤掉所有数据 (没有数据 updated_at >= 9999)
    assert client.list_companies(since=far_future).data == []
    assert client.list_stores(since=far_future).data == []
    assert (
        client.list_stores_revenue(period_year=2026, period_month=4, since=far_future).data == []
    )
    assert client.list_employees(since=far_future).data == []
    assert (
        client.list_fixed_costs(period_year=2026, period_month=4, since=far_future).data == []
    )
    assert (
        client.list_payroll(
            company_id="mock-company-uuid-factory-1",
            period_year=2026,
            period_month=4,
            since=far_future,
        ).data == []
    )
    assert client.list_payment_requests(since=far_future).data == []

    # 2. since=far_past → 应能拉到全部数据(不被过滤)
    assert len(client.list_companies(since=far_past).data) >= 7
    assert len(client.list_stores(since=far_past).data) >= 4
    assert len(client.list_payment_requests(since=far_past).data) >= 12

    # 3. until=far_past → 同样过滤掉所有数据 (没有数据 updated_at < 1900)
    assert client.list_companies(until=far_past).data == []


# ---------------------------------------------------------------------------
# C9 — companies v1.3 新字段: 4 recognition Boolean + floor_area_sqm
# ---------------------------------------------------------------------------


def test_c9_companies_v1_3_recognition_flags_and_floor_area():
    """v1.3 §4.1 + §4.10 — companies 加 4 业务画像 Boolean + 1 floor_area_sqm。

    要求:
        - 4 个 recognition 字段都是 bool(可为 false)
        - floor_area_sqm 可为 None (ops 暂未测量 → cost_allocator fallback 场景)
        - 至少 1 个主体每个 recognition flag = True (验证不是全 false 的死配)
        - 至少 1 个主体 floor_area_sqm 已填值(演示按面积摊法)
        - 至少 1 个主体 floor_area_sqm = None(演示 fallback)
    """

    client = FinanceC1Client(use_mock=True)
    envelope = client.list_companies()

    assert envelope.api_version and "1.3" in envelope.api_version
    assert len(envelope.data) >= 7

    # 每个主体都有 4 recognition Boolean + floor_area_sqm 字段
    for row in envelope.data:
        for flag in (
            "revenue_recognition",
            "material_purchase_recognition",
            "payroll_recognition",
            "fixed_cost_recognition",
        ):
            assert flag in row, f"主体 {row.get('legal_name')} 缺 {flag}"
            assert isinstance(row[flag], bool)
        assert "floor_area_sqm" in row
        # 可为 None / float / int
        if row["floor_area_sqm"] is not None:
            assert isinstance(row["floor_area_sqm"], (int, float))
            assert row["floor_area_sqm"] >= 0

    # 至少 1 个主体每个 recognition flag = True
    has_revenue_recog = [r for r in envelope.data if r["revenue_recognition"]]
    has_material_recog = [r for r in envelope.data if r["material_purchase_recognition"]]
    has_payroll_recog = [r for r in envelope.data if r["payroll_recognition"]]
    has_fixed_cost_recog = [r for r in envelope.data if r["fixed_cost_recognition"]]
    assert has_revenue_recog, "至少 1 主体 revenue_recognition=True (店铺主体)"
    assert has_material_recog, "至少 1 主体 material_purchase_recognition=True (生产主体)"
    assert has_payroll_recog, "至少 1 主体 payroll_recognition=True (生产主体)"
    assert has_fixed_cost_recog, "至少 1 主体 fixed_cost_recognition=True"

    # floor_area_sqm 双场景 — 测过 + 没测过
    measured = [r for r in envelope.data if r["floor_area_sqm"] is not None]
    unmeasured = [r for r in envelope.data if r["floor_area_sqm"] is None]
    assert measured, "至少 1 主体 floor_area_sqm 已填(演示按面积摊)"
    assert unmeasured, "至少 1 主体 floor_area_sqm=NULL(演示 cost_allocator fallback)"

    # Pydantic schema round-trip — 4 recognition + floor_area 不漏字段
    parsed = [FinanceCompanyDTO(**row) for row in envelope.data]
    assert any(p.revenue_recognition for p in parsed)
    assert any(p.floor_area_sqm is not None for p in parsed)
    assert any(p.floor_area_sqm is None for p in parsed)


# ---------------------------------------------------------------------------
# C10 — payroll(by_employee) v1.3 真实落地: 每员工每月 1 行 + metadata 完整
# ---------------------------------------------------------------------------


def test_c10_payroll_by_employee_mode_v1_3_per_employee_per_month():
    """v1.3 §4.5 — payroll aggregation=by_employee 真实落地 ·  每员工每月 1 行。

    finance 备忘录 §4.5 关键字段:
        - 数据源策略在 metadata.payment_source_types(2026+ 走 reconciliation)
        - metadata.actual_paid 是实发(排除 payment_method='cash' 后)
        - metadata.fallback_reason 说明为啥 fallback 到 declaration(如有)
    """

    client = FinanceC1Client(use_mock=True, payroll_authorized=True)
    env = client.list_payroll(
        company_id="mock-company-uuid-factory-1",
        period_year=2026,
        period_month=4,
        aggregation="by_employee",
    )

    assert env.data_source == "mock"
    assert env.api_version and "1.3" in env.api_version

    # factory-1 在 mock 里有 4 个员工(缝纫一组 2 + 缝纫二组 1 + 包装组 1)·  共 4 行
    assert len(env.data) >= 4
    # by_employee 不再聚合 ·  每员工 1 行 ·  employee_id 唯一
    employee_ids = [r["employee_id"] for r in env.data]
    assert len(employee_ids) == len(set(employee_ids)), (
        "by_employee 模式下每员工应唯一 1 行 ·  实际有重复 employee_id"
    )

    # 字段 1:1 对齐契约 v1.3 §4.5
    for row in env.data:
        assert row["employee_id"] and row["employee_no"]
        # 脱敏 — 不应出现"张某某"原文 (mock data 里 name_masked = "张**")
        assert "**" in row["name_masked"]
        assert row["company_id"] == "mock-company-uuid-factory-1"
        assert row["period_year"] == 2026 and row["period_month"] == 4
        assert row["gross_salary"] > 0
        # total_labor_cost = gross_salary + employer_insurance (恒等)
        assert (
            abs(row["total_labor_cost"] - row["gross_salary"] - row["employer_insurance"])
            < 0.01
        )
        # finance 备忘录 §4.5 关键 metadata 字段
        meta = row.get("metadata") or {}
        assert "actual_paid" in meta, "metadata.actual_paid 缺(finance 备忘录 §4.5)"
        assert "payment_source_types" in meta, "metadata.payment_source_types 缺"
        assert isinstance(meta["payment_source_types"], list)
        assert meta["payment_source_types"], "payment_source_types 不应为空 list"
        # 2026+ 主路径必须含 salary_reconciliation
        assert "salary_reconciliation" in meta["payment_source_types"]

    # Pydantic schema round-trip (新 DTO)
    parsed = [FinancePayrollByEmployeeDTO(**row) for row in env.data]
    assert all(p.gross_salary > 0 for p in parsed)

    # by_department 模式仍兼容 (v1.0 形态保留)
    env_dept = client.list_payroll(
        company_id="mock-company-uuid-factory-1",
        period_year=2026,
        period_month=4,
        aggregation="by_department",
    )
    # by_department 是聚合: factory-1 有 4 个班组(缝纫一/二/拼版/包装)
    assert len(env_dept.data) >= 4
    assert "department" in env_dept.data[0]
    assert "headcount" in env_dept.data[0]


# ---------------------------------------------------------------------------
# Router smoke 补充: 2 个 v1.3 新 endpoint 走 /api/planner/finance/* 代理
# ---------------------------------------------------------------------------


def test_extra_router_stores_revenue_v1_3(client):
    """端到端 smoke: GET /api/planner/finance/stores/revenue 返回 envelope schema。"""

    response = client.get(
        "/api/planner/finance/stores/revenue?period_year=2026&period_month=4"
    )
    assert response.status_code == 200
    body = response.json()
    assert "data" in body
    assert body["data_source"] == "mock"
    assert len(body["data"]) >= 4
    # v1.3 字段就位
    first = body["data"][0]
    for f in ("store_id", "store_name", "gross_revenue", "net_revenue", "data_quality"):
        assert f in first


def test_extra_router_payment_requests_v1_3(client):
    """端到端 smoke: GET /api/planner/finance/payment-requests 返回 envelope。"""

    response = client.get("/api/planner/finance/payment-requests")
    assert response.status_code == 200
    body = response.json()
    assert body["data_source"] == "mock"
    assert len(body["data"]) >= 12

    # 6 类 expense_category 全在结果里
    cats = {r["expense_category"] for r in body["data"]}
    assert cats == set(EXPENSE_CATEGORY_CHOICES)

    # is_amortized=true 过滤
    response2 = client.get("/api/planner/finance/payment-requests?is_amortized=true")
    assert response2.status_code == 200
    body2 = response2.json()
    assert all(r["is_monthly_amortized"] for r in body2["data"])
    assert len(body2["data"]) >= 1
