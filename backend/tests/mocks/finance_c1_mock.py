"""Mock finance C1 API responses(契约 §3 example response 1:1 复制)。

用途:
    1. `FINANCE_C1_USE_MOCK=true` 时 `FinanceC1Client` 直接返回这些数据 ·
       让 ai-costing-system 在 finance API 还没真起的阶段就能跑通端到端 ·
       UI 的 "数据来源" Badge 会显示 🔵 mock (dev)。
    2. 单测 `backend/tests/planner/test_finance_c1_client.py` 也用这份数据
       做 fixture (含 cache 命中 / 401 降级 / 5xx 降级三类断言)。

不变量(派单 §2.3 + 验收 B2):
    - companies >= 7 (3 factory + 4 shop)
    - stores    >= 4
    - employees >= 3
    - fixed-costs 覆盖契约 §3.4.1 全 11 个 cost_category 至少 1 条
    - payroll   >= 6 (6 班组)

注:本文件不依赖 ORM 也不依赖 Pydantic ·  纯 Python list[dict] ·  保持
"快速 import / 0 副作用 / 易增删字段" 的 mock fixture 风格。
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List

# ---------------------------------------------------------------------------
# §3.1 companies — 7 条 (3 factory + 4 shop)
# ---------------------------------------------------------------------------

# 注: id 用 "mock-company-uuid-N" 便于在测试断言里直接拼 string ·
# 真实环境 finance 返回 UUID v4 · costing 侧从来不验 UUID 格式(见契约 §3.1)。

MOCK_COMPANIES: List[Dict[str, Any]] = [
    {
        "id": "mock-company-uuid-factory-1",
        "legal_name": "杭州某某家居饰品有限公司",
        "tax_payer_type": "general",
        "unified_social_credit_code": "91330000XXXXXXXXX1",
        "entity_role": "factory",
        "parent_company_id": None,
        "is_active": True,
        "effective_from": "2024-01-01",
        "effective_to": None,
        "metadata": {
            "city": "杭州",
            "address": "杭州市余杭区某某路 1 号",
            "legal_representative": "张某某",
        },
    },
    {
        "id": "mock-company-uuid-factory-2",
        "legal_name": "杭州某某印染有限公司",
        "tax_payer_type": "general",
        "unified_social_credit_code": "91330000XXXXXXXXX2",
        "entity_role": "factory",
        "parent_company_id": None,
        "is_active": True,
        "effective_from": "2024-01-01",
        "effective_to": None,
        "metadata": {"city": "杭州", "address": "杭州市余杭区某某路 2 号"},
    },
    {
        "id": "mock-company-uuid-factory-3",
        "legal_name": "杭州某某家居拼版加工厂(小规模)",
        "tax_payer_type": "small_scale",
        "unified_social_credit_code": "91330000XXXXXXXXX3",
        "entity_role": "factory",
        "parent_company_id": None,
        "is_active": True,
        "effective_from": "2024-01-01",
        "effective_to": None,
        "metadata": {"city": "杭州"},
    },
    {
        "id": "mock-company-uuid-shop-1",
        "legal_name": "杭州饰家如画电子商务有限公司",
        "tax_payer_type": "general",
        "unified_social_credit_code": "91330000XXXXXXXXX4",
        "entity_role": "shop",
        "parent_company_id": None,
        "is_active": True,
        "effective_from": "2024-01-01",
        "effective_to": None,
        "metadata": {"city": "杭州"},
    },
    {
        "id": "mock-company-uuid-shop-2",
        "legal_name": "杭州饰家如画品牌管理有限公司(小规模)",
        "tax_payer_type": "small_scale",
        "unified_social_credit_code": "91330000XXXXXXXXX5",
        "entity_role": "shop",
        "parent_company_id": None,
        "is_active": True,
        "effective_from": "2024-01-01",
        "effective_to": None,
        "metadata": {"city": "杭州"},
    },
    {
        "id": "mock-company-uuid-shop-3",
        "legal_name": "杭州某某家居布艺有限公司",
        "tax_payer_type": "general",
        "unified_social_credit_code": "91330000XXXXXXXXX6",
        "entity_role": "shop",
        "parent_company_id": None,
        "is_active": True,
        "effective_from": "2024-06-01",
        "effective_to": None,
        "metadata": {"city": "杭州"},
    },
    {
        "id": "mock-company-uuid-shop-4",
        "legal_name": "杭州某某文化创意有限公司",
        "tax_payer_type": "general",
        "unified_social_credit_code": "91330000XXXXXXXXX7",
        "entity_role": "shop",
        "parent_company_id": None,
        "is_active": True,
        "effective_from": "2025-01-01",
        "effective_to": None,
        "metadata": {"city": "杭州"},
    },
]


# ---------------------------------------------------------------------------
# §3.2 stores — 4 条 (与 4 个 shop 主体 1:1 对齐)
# ---------------------------------------------------------------------------

MOCK_STORES: List[Dict[str, Any]] = [
    {
        "id": "mock-store-uuid-1",
        "store_name": "饰家如画旗舰店",
        "company_id": "mock-company-uuid-shop-1",
        "platform": "tmall",
        "platform_shop_id": "12345001",
        "manager_name": "李某某",
        "main_category": "家居饰品",
        "monthly_revenue_avg": 350000.0,
        "is_active": True,
        "metadata": {},
    },
    {
        "id": "mock-store-uuid-2",
        "store_name": "饰家如画旗舰店(京东)",
        "company_id": "mock-company-uuid-shop-2",
        "platform": "jd",
        "platform_shop_id": "12345002",
        "manager_name": "王某某",
        "main_category": "家居布艺",
        "monthly_revenue_avg": 180000.0,
        "is_active": True,
        "metadata": {},
    },
    {
        "id": "mock-store-uuid-3",
        "store_name": "饰家如画抖音小店",
        "company_id": "mock-company-uuid-shop-3",
        "platform": "douyin",
        "platform_shop_id": "12345003",
        "manager_name": "赵某某",
        "main_category": "家居布艺",
        "monthly_revenue_avg": 220000.0,
        "is_active": True,
        "metadata": {},
    },
    {
        "id": "mock-store-uuid-4",
        "store_name": "饰家如画淘宝店",
        "company_id": "mock-company-uuid-shop-4",
        "platform": "taobao",
        "platform_shop_id": "12345004",
        "manager_name": "孙某某",
        "main_category": "混合",
        "monthly_revenue_avg": 95000.0,
        "is_active": True,
        "metadata": {},
    },
]


# ---------------------------------------------------------------------------
# §3.3 employees — 3 条 (足够覆盖 by_department 聚合的 schema 验证)
# ---------------------------------------------------------------------------

MOCK_EMPLOYEES: List[Dict[str, Any]] = [
    {
        "id": "mock-emp-uuid-1",
        "employee_no": "E0001",
        "name": "张某某",
        "contract_company_id": "mock-company-uuid-factory-1",
        "department": "缝纫一组",
        "position": "缝纫工",
        "hire_date": "2023-03-15",
        "leave_date": None,
        "is_active": True,
        "metadata": {
            "id_card_masked": "330***********1234",
            "phone_masked": "138****5678",
        },
    },
    {
        "id": "mock-emp-uuid-2",
        "employee_no": "E0002",
        "name": "李某某",
        "contract_company_id": "mock-company-uuid-factory-1",
        "department": "缝纫二组",
        "position": "缝纫工",
        "hire_date": "2024-04-01",
        "leave_date": None,
        "is_active": True,
        "metadata": {
            "id_card_masked": "330***********5678",
            "phone_masked": "138****1234",
        },
    },
    {
        "id": "mock-emp-uuid-3",
        "employee_no": "E0003",
        "name": "王某某",
        "contract_company_id": "mock-company-uuid-factory-2",
        "department": "印染组",
        "position": "印染工",
        "hire_date": "2023-08-20",
        "leave_date": None,
        "is_active": True,
        "metadata": {
            "id_card_masked": "330***********9012",
            "phone_masked": "139****3456",
        },
    },
]


# ---------------------------------------------------------------------------
# §3.4 fixed-costs — 覆盖契约 §3.4.1 全 11 个 cost_category 各 ≥ 1 条
# ---------------------------------------------------------------------------

# 默认期间: 2026-04(派单 brief 选这个 month 是因为契约 §3.4 example 也用这个期)
_DEFAULT_PERIOD_YEAR = 2026
_DEFAULT_PERIOD_MONTH = 4

MOCK_FIXED_COSTS: List[Dict[str, Any]] = [
    {
        "id": "mock-fc-uuid-rent-1",
        "company_id": "mock-company-uuid-factory-1",
        "period_year": _DEFAULT_PERIOD_YEAR,
        "period_month": _DEFAULT_PERIOD_MONTH,
        "cost_category": "rent",
        "cost_subcategory": "factory_workshop",
        "amount": 35000.0,
        "tax_included": True,
        "tax_rate": 0.06,
        "description": "厂区 3 楼车间房租",
        "approver": "李某某",
        "metadata": {},
    },
    {
        "id": "mock-fc-uuid-utility-1",
        "company_id": "mock-company-uuid-factory-1",
        "period_year": _DEFAULT_PERIOD_YEAR,
        "period_month": _DEFAULT_PERIOD_MONTH,
        "cost_category": "utility",
        "cost_subcategory": "electricity",
        "amount": 18500.0,
        "tax_included": True,
        "tax_rate": 0.13,
        "description": "厂区 4 月电费",
        "approver": "李某某",
        "metadata": {},
    },
    {
        "id": "mock-fc-uuid-salary-admin-1",
        "company_id": "mock-company-uuid-factory-1",
        "period_year": _DEFAULT_PERIOD_YEAR,
        "period_month": _DEFAULT_PERIOD_MONTH,
        "cost_category": "salary_admin",
        "cost_subcategory": "factory_admin",
        "amount": 28000.0,
        "tax_included": False,
        "tax_rate": None,
        "description": "厂部管理人员工资(4 月)",
        "approver": "李某某",
        "metadata": {},
    },
    {
        "id": "mock-fc-uuid-insurance-admin-1",
        "company_id": "mock-company-uuid-factory-1",
        "period_year": _DEFAULT_PERIOD_YEAR,
        "period_month": _DEFAULT_PERIOD_MONTH,
        "cost_category": "insurance_admin",
        "cost_subcategory": "factory_admin",
        "amount": 5600.0,
        "tax_included": False,
        "tax_rate": None,
        "description": "厂部管理人员五险一金(公司部分)",
        "approver": "李某某",
        "metadata": {},
    },
    {
        "id": "mock-fc-uuid-office-supplies-1",
        "company_id": "mock-company-uuid-factory-1",
        "period_year": _DEFAULT_PERIOD_YEAR,
        "period_month": _DEFAULT_PERIOD_MONTH,
        "cost_category": "office_supplies",
        "cost_subcategory": "consumables",
        "amount": 1800.0,
        "tax_included": True,
        "tax_rate": 0.13,
        "description": "办公耗材(打印机墨盒/A4 纸/快递袋等)",
        "approver": "李某某",
        "metadata": {},
    },
    {
        "id": "mock-fc-uuid-depreciation-1",
        "company_id": "mock-company-uuid-factory-1",
        "period_year": _DEFAULT_PERIOD_YEAR,
        "period_month": _DEFAULT_PERIOD_MONTH,
        "cost_category": "depreciation",
        "cost_subcategory": "machinery",
        "amount": 12000.0,
        "tax_included": False,
        "tax_rate": None,
        "description": "缝纫/绣花/印染设备月折旧",
        "approver": "李某某",
        "metadata": {},
    },
    {
        "id": "mock-fc-uuid-logistics-1",
        "company_id": "mock-company-uuid-factory-1",
        "period_year": _DEFAULT_PERIOD_YEAR,
        "period_month": _DEFAULT_PERIOD_MONTH,
        "cost_category": "logistics",
        "cost_subcategory": "factory_outbound",
        "amount": 3200.0,
        "tax_included": True,
        "tax_rate": 0.09,
        "description": "厂出物流(成品出库 → 城市仓)",
        "approver": "李某某",
        "metadata": {},
    },
    {
        "id": "mock-fc-uuid-platform-fee-1",
        "company_id": "mock-company-uuid-shop-1",
        "period_year": _DEFAULT_PERIOD_YEAR,
        "period_month": _DEFAULT_PERIOD_MONTH,
        "cost_category": "platform_fee",
        "cost_subcategory": "tmall_commission",
        "amount": 26000.0,
        "tax_included": True,
        "tax_rate": 0.06,
        "description": "天猫旗舰店佣金 + 推广(直通车/万相台)",
        "approver": "王某某",
        "metadata": {},
    },
    {
        "id": "mock-fc-uuid-after-sales-1",
        "company_id": "mock-company-uuid-shop-1",
        "period_year": _DEFAULT_PERIOD_YEAR,
        "period_month": _DEFAULT_PERIOD_MONTH,
        "cost_category": "after_sales",
        "cost_subcategory": "return_freight",
        "amount": 4500.0,
        "tax_included": True,
        "tax_rate": 0.09,
        "description": "退换货运费(店铺承担部分)",
        "approver": "王某某",
        "metadata": {},
    },
    {
        "id": "mock-fc-uuid-others-1",
        "company_id": "mock-company-uuid-factory-1",
        "period_year": _DEFAULT_PERIOD_YEAR,
        "period_month": _DEFAULT_PERIOD_MONTH,
        "cost_category": "others",
        "cost_subcategory": "training",
        "amount": 1200.0,
        "tax_included": False,
        "tax_rate": None,
        "description": "员工培训费用",
        "approver": "李某某",
        "metadata": {},
    },
    # 第 11 条 — 第 2 个 utility 多记一笔覆盖 (水) · 让汇总测试更稳。
    {
        "id": "mock-fc-uuid-utility-2",
        "company_id": "mock-company-uuid-factory-1",
        "period_year": _DEFAULT_PERIOD_YEAR,
        "period_month": _DEFAULT_PERIOD_MONTH,
        "cost_category": "utility",
        "cost_subcategory": "water",
        "amount": 2200.0,
        "tax_included": True,
        "tax_rate": 0.06,
        "description": "厂区 4 月水费",
        "approver": "李某某",
        "metadata": {},
    },
]


# ---------------------------------------------------------------------------
# §3.5 payroll — 6 个班组(每个班组一行 by_department 聚合)
# ---------------------------------------------------------------------------

MOCK_PAYROLL: List[Dict[str, Any]] = [
    {
        "company_id": "mock-company-uuid-factory-1",
        "department": "缝纫一组",
        "period_year": _DEFAULT_PERIOD_YEAR,
        "period_month": _DEFAULT_PERIOD_MONTH,
        "headcount": 8,
        "total_gross_salary": 45000.0,
        "total_employer_insurance": 9000.0,
        "total_labor_cost": 54000.0,
        "avg_workdays": 21.5,
        "metadata": {},
    },
    {
        "company_id": "mock-company-uuid-factory-1",
        "department": "缝纫二组",
        "period_year": _DEFAULT_PERIOD_YEAR,
        "period_month": _DEFAULT_PERIOD_MONTH,
        "headcount": 6,
        "total_gross_salary": 33000.0,
        "total_employer_insurance": 6600.0,
        "total_labor_cost": 39600.0,
        "avg_workdays": 21.0,
        "metadata": {},
    },
    {
        "company_id": "mock-company-uuid-factory-1",
        "department": "拼版组",
        "period_year": _DEFAULT_PERIOD_YEAR,
        "period_month": _DEFAULT_PERIOD_MONTH,
        "headcount": 4,
        "total_gross_salary": 24000.0,
        "total_employer_insurance": 4800.0,
        "total_labor_cost": 28800.0,
        "avg_workdays": 22.0,
        "metadata": {},
    },
    {
        "company_id": "mock-company-uuid-factory-2",
        "department": "印染组",
        "period_year": _DEFAULT_PERIOD_YEAR,
        "period_month": _DEFAULT_PERIOD_MONTH,
        "headcount": 5,
        "total_gross_salary": 32000.0,
        "total_employer_insurance": 6400.0,
        "total_labor_cost": 38400.0,
        "avg_workdays": 21.5,
        "metadata": {},
    },
    {
        "company_id": "mock-company-uuid-factory-1",
        "department": "包装组",
        "period_year": _DEFAULT_PERIOD_YEAR,
        "period_month": _DEFAULT_PERIOD_MONTH,
        "headcount": 3,
        "total_gross_salary": 15000.0,
        "total_employer_insurance": 3000.0,
        "total_labor_cost": 18000.0,
        "avg_workdays": 22.0,
        "metadata": {},
    },
    {
        "company_id": "mock-company-uuid-factory-3",
        "department": "切割组",
        "period_year": _DEFAULT_PERIOD_YEAR,
        "period_month": _DEFAULT_PERIOD_MONTH,
        "headcount": 4,
        "total_gross_salary": 22000.0,
        "total_employer_insurance": 4400.0,
        "total_labor_cost": 26400.0,
        "avg_workdays": 21.0,
        "metadata": {},
    },
]


# ---------------------------------------------------------------------------
# Helpers — client / 测试 / 校验脚本共用
# ---------------------------------------------------------------------------


def get_companies(*, entity_role: str | None = None, is_active: bool | None = True) -> List[Dict[str, Any]]:
    """模拟 GET /api/v1/c1/companies 的过滤行为。

    deepcopy 是为了让上层 cache 写入不会被外部 mutate 污染原始 mock 数据。
    """

    rows = [deepcopy(r) for r in MOCK_COMPANIES]
    if entity_role:
        rows = [r for r in rows if r.get("entity_role") == entity_role]
    if is_active is not None:
        rows = [r for r in rows if bool(r.get("is_active")) == bool(is_active)]
    return rows


def get_stores(*, company_id: str | None = None, is_active: bool | None = True) -> List[Dict[str, Any]]:
    rows = [deepcopy(r) for r in MOCK_STORES]
    if company_id:
        rows = [r for r in rows if r.get("company_id") == company_id]
    if is_active is not None:
        rows = [r for r in rows if bool(r.get("is_active")) == bool(is_active)]
    return rows


def get_employees(
    *, contract_company_id: str | None = None, is_active: bool | None = True
) -> List[Dict[str, Any]]:
    rows = [deepcopy(r) for r in MOCK_EMPLOYEES]
    if contract_company_id:
        rows = [r for r in rows if r.get("contract_company_id") == contract_company_id]
    if is_active is not None:
        rows = [r for r in rows if bool(r.get("is_active")) == bool(is_active)]
    return rows


def get_fixed_costs(
    *,
    period_year: int | None = None,
    period_month: int | None = None,
    cost_category: str | None = None,
    company_id: str | None = None,
) -> List[Dict[str, Any]]:
    rows = [deepcopy(r) for r in MOCK_FIXED_COSTS]
    if period_year is not None:
        rows = [r for r in rows if r.get("period_year") == period_year]
    if period_month is not None:
        rows = [r for r in rows if r.get("period_month") == period_month]
    if cost_category:
        rows = [r for r in rows if r.get("cost_category") == cost_category]
    if company_id:
        rows = [r for r in rows if r.get("company_id") == company_id]
    return rows


def get_payroll(
    *,
    company_id: str,
    period_year: int,
    period_month: int,
) -> List[Dict[str, Any]]:
    rows = [deepcopy(r) for r in MOCK_PAYROLL]
    rows = [
        r
        for r in rows
        if r.get("company_id") == company_id
        and r.get("period_year") == period_year
        and r.get("period_month") == period_month
    ]
    return rows


__all__ = [
    "MOCK_COMPANIES",
    "MOCK_STORES",
    "MOCK_EMPLOYEES",
    "MOCK_FIXED_COSTS",
    "MOCK_PAYROLL",
    "get_companies",
    "get_stores",
    "get_employees",
    "get_fixed_costs",
    "get_payroll",
]
