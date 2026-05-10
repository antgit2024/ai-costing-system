"""Mock finance C1 API responses(契约 v1.3 §4 example response 1:1 复制)。

用途:
    1. `FINANCE_C1_USE_MOCK=true` 时 `FinanceC1Client` 直接返回这些数据 ·
       让 ai-costing-system 在 finance staging URL/key 拿到之前就能跑通端到端 ·
       UI 的 "数据来源" Badge 会显示 🔵 mock (dev)。
    2. 单测 `backend/tests/planner/test_finance_c1_client.py` 也用这份数据
       做 fixture (含 v1.0 老 5 条 + v1.3 新 5 条 case)。
    3. `backend/scripts/finance_c1_e2e_smoke.py --mock` 7 endpoint 端到端 smoke。

不变量(v1.3 升级 §2.3 + 验收 B3/B4):
    - companies          >= 7 (3 factory + 4 shop)·  每条含 4 recognition Boolean + floor_area_sqm
    - stores             >= 4
    - stores_revenue     >= 4 (4 店铺 × ≥1 月 = 4 条)
    - employees          >= 3
    - fixed-costs        覆盖契约 §3.4.1 全 10 unique cost_category 各 ≥ 1 条
    - payroll(by_dept)   >= 6 (6 班组 ·  v1.0 兼容)
    - payroll(by_emp)    每员工每月 1 行(v1.3 §4.5 真实落地形态)
    - payment_requests   >= 12 (覆盖 6 类 expense_category 各 ≥ 2 条)

注:本文件不依赖 ORM 也不依赖 Pydantic ·  纯 Python list[dict] ·  保持
"快速 import / 0 副作用 / 易增删字段" 的 mock fixture 风格。
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# §4.1 + §4.10 companies — 7 条 (3 factory + 4 shop)
# v1.3 增量: 每条加 4 recognition Boolean + floor_area_sqm(部分 NULL 演示 fallback)
# ---------------------------------------------------------------------------

# 注: id 用 "mock-company-uuid-N" 便于在测试断言里直接拼 string ·
# 真实环境 finance 返回 UUID v4 · costing 侧从来不验 UUID 格式(见契约 §4.1)。

MOCK_COMPANIES: List[Dict[str, Any]] = [
    {
        # factory-1: 真实生产主体(material/payroll/fixed_cost recognition=True)
        # ·  4 月份房租/水电/折旧主要归这里·  floor_area_sqm 已测量
        "id": "mock-company-uuid-factory-1",
        "legal_name": "杭州某某家居饰品有限公司",
        "tax_payer_type": "general",
        "unified_social_credit_code": "91330000XXXXXXXXX1",
        "entity_role": "factory",
        "parent_company_id": None,
        "is_active": True,
        "effective_from": "2024-01-01",
        "effective_to": None,
        "revenue_recognition": False,
        "material_purchase_recognition": True,
        "payroll_recognition": True,
        "fixed_cost_recognition": True,
        "floor_area_sqm": 850.50,
        "metadata": {
            "city": "杭州",
            "address": "杭州市余杭区某某路 1 号",
            "legal_representative": "张某某",
        },
    },
    {
        # factory-2: 印染主体 ·  payroll_recognition=True ·  floor_area 已测量
        "id": "mock-company-uuid-factory-2",
        "legal_name": "杭州某某印染有限公司",
        "tax_payer_type": "general",
        "unified_social_credit_code": "91330000XXXXXXXXX2",
        "entity_role": "factory",
        "parent_company_id": None,
        "is_active": True,
        "effective_from": "2024-01-01",
        "effective_to": None,
        "revenue_recognition": False,
        "material_purchase_recognition": False,
        "payroll_recognition": True,
        "fixed_cost_recognition": False,
        "floor_area_sqm": 320.00,
        "metadata": {"city": "杭州", "address": "杭州市余杭区某某路 2 号"},
    },
    {
        # factory-3: 小规模拼版加工厂 ·  floor_area 暂未测量(NULL = 演示
        # cost_allocator_service 多级 fallback 到 headcount 摊法的场景)
        "id": "mock-company-uuid-factory-3",
        "legal_name": "杭州某某家居拼版加工厂(小规模)",
        "tax_payer_type": "small_scale",
        "unified_social_credit_code": "91330000XXXXXXXXX3",
        "entity_role": "factory",
        "parent_company_id": None,
        "is_active": True,
        "effective_from": "2024-01-01",
        "effective_to": None,
        "revenue_recognition": False,
        "material_purchase_recognition": False,
        "payroll_recognition": True,
        "fixed_cost_recognition": False,
        "floor_area_sqm": None,
        "metadata": {"city": "杭州"},
    },
    {
        # shop-1: 天猫旗舰店主体 ·  revenue + fixed_cost(平台佣金/售后)recognition
        # ·  floor_area 通常无(店铺不占厂房)
        "id": "mock-company-uuid-shop-1",
        "legal_name": "杭州饰家如画电子商务有限公司",
        "tax_payer_type": "general",
        "unified_social_credit_code": "91330000XXXXXXXXX4",
        "entity_role": "shop",
        "parent_company_id": None,
        "is_active": True,
        "effective_from": "2024-01-01",
        "effective_to": None,
        "revenue_recognition": True,
        "material_purchase_recognition": False,
        "payroll_recognition": False,
        "fixed_cost_recognition": True,
        "floor_area_sqm": None,
        "metadata": {"city": "杭州"},
    },
    {
        # shop-2: 京东店主体(小规模)·  revenue_recognition=True
        "id": "mock-company-uuid-shop-2",
        "legal_name": "杭州饰家如画品牌管理有限公司(小规模)",
        "tax_payer_type": "small_scale",
        "unified_social_credit_code": "91330000XXXXXXXXX5",
        "entity_role": "shop",
        "parent_company_id": None,
        "is_active": True,
        "effective_from": "2024-01-01",
        "effective_to": None,
        "revenue_recognition": True,
        "material_purchase_recognition": False,
        "payroll_recognition": False,
        "fixed_cost_recognition": True,
        "floor_area_sqm": None,
        "metadata": {"city": "杭州"},
    },
    {
        # shop-3: 抖音店主体
        "id": "mock-company-uuid-shop-3",
        "legal_name": "杭州某某家居布艺有限公司",
        "tax_payer_type": "general",
        "unified_social_credit_code": "91330000XXXXXXXXX6",
        "entity_role": "shop",
        "parent_company_id": None,
        "is_active": True,
        "effective_from": "2024-06-01",
        "effective_to": None,
        "revenue_recognition": True,
        "material_purchase_recognition": False,
        "payroll_recognition": False,
        "fixed_cost_recognition": False,
        "floor_area_sqm": None,
        "metadata": {"city": "杭州"},
    },
    {
        # shop-4: 淘宝店主体(2025 启用)
        "id": "mock-company-uuid-shop-4",
        "legal_name": "杭州某某文化创意有限公司",
        "tax_payer_type": "general",
        "unified_social_credit_code": "91330000XXXXXXXXX7",
        "entity_role": "shop",
        "parent_company_id": None,
        "is_active": True,
        "effective_from": "2025-01-01",
        "effective_to": None,
        "revenue_recognition": True,
        "material_purchase_recognition": False,
        "payroll_recognition": False,
        "fixed_cost_recognition": False,
        "floor_area_sqm": None,
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
# §4.2 stores/revenue — v1.3 新增 (4 店铺 × 2026-04 真实月度营收)
# 来自 finance LedgerMonthlySummary `profile_name='alipay_monthly_statement'`
# 优先权责制(accrual_*) ·  COALESCE 到收付制(sales_income_amount)兜底
# ---------------------------------------------------------------------------

_DEFAULT_PERIOD_YEAR = 2026
_DEFAULT_PERIOD_MONTH = 4

MOCK_STORES_REVENUE: List[Dict[str, Any]] = [
    {
        "store_id": "mock-store-uuid-1",
        "store_name": "饰家如画旗舰店",
        "company_id": "mock-company-uuid-shop-1",
        "platform": "tmall",
        "period_year": _DEFAULT_PERIOD_YEAR,
        "period_month": _DEFAULT_PERIOD_MONTH,
        "gross_revenue": 385000.00,
        "net_revenue": 342500.00,
        "platform_fee_paid": 28500.00,
        "withdraw_amount": 320000.00,
        "data_source": "platform_api",
        "data_quality": "green",
        "snapshot_at": "2026-05-08T10:00:00+08:00",
        "metadata": {
            "accrual_used": True,
            "refund_amount": 42500.00,
        },
    },
    {
        "store_id": "mock-store-uuid-2",
        "store_name": "饰家如画旗舰店(京东)",
        "company_id": "mock-company-uuid-shop-2",
        "platform": "jd",
        "period_year": _DEFAULT_PERIOD_YEAR,
        "period_month": _DEFAULT_PERIOD_MONTH,
        "gross_revenue": 195000.00,
        "net_revenue": 175200.00,
        "platform_fee_paid": 12500.00,
        "withdraw_amount": 168000.00,
        "data_source": "platform_api",
        "data_quality": "green",
        "snapshot_at": "2026-05-08T10:00:00+08:00",
        "metadata": {
            "accrual_used": True,
            "refund_amount": 19800.00,
        },
    },
    {
        "store_id": "mock-store-uuid-3",
        "store_name": "饰家如画抖音小店",
        "company_id": "mock-company-uuid-shop-3",
        "platform": "douyin",
        "period_year": _DEFAULT_PERIOD_YEAR,
        "period_month": _DEFAULT_PERIOD_MONTH,
        "gross_revenue": 245000.00,
        "net_revenue": 218400.00,
        "platform_fee_paid": 18900.00,
        "withdraw_amount": 215000.00,
        "data_source": "platform_api",
        "data_quality": "yellow",
        "snapshot_at": "2026-05-08T10:00:00+08:00",
        "metadata": {
            "accrual_used": False,
            "refund_amount": 26600.00,
            "warnings": ["accrual_sales_income_amount missing — fallback to sales_income_amount"],
        },
    },
    {
        "store_id": "mock-store-uuid-4",
        "store_name": "饰家如画淘宝店",
        "company_id": "mock-company-uuid-shop-4",
        "platform": "taobao",
        "period_year": _DEFAULT_PERIOD_YEAR,
        "period_month": _DEFAULT_PERIOD_MONTH,
        "gross_revenue": 102000.00,
        "net_revenue": 91300.00,
        "platform_fee_paid": 7100.00,
        "withdraw_amount": 88500.00,
        "data_source": "manual",
        "data_quality": "yellow",
        "snapshot_at": "2026-05-08T10:00:00+08:00",
        "metadata": {
            "accrual_used": True,
            "refund_amount": 10700.00,
        },
    },
]


# ---------------------------------------------------------------------------
# §3.3 employees — 6 条 (覆盖 4 班组 × 多主体 ·  v1.3 by_employee 模式需要逐人数据)
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
            "name_masked": "张**",
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
            "name_masked": "李**",
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
            "name_masked": "王**",
        },
    },
    {
        "id": "mock-emp-uuid-4",
        "employee_no": "E0004",
        "name": "刘某某",
        "contract_company_id": "mock-company-uuid-factory-1",
        "department": "缝纫一组",
        "position": "缝纫工",
        "hire_date": "2024-09-10",
        "leave_date": None,
        "is_active": True,
        "metadata": {
            "id_card_masked": "330***********4567",
            "phone_masked": "137****8901",
            "name_masked": "刘**",
        },
    },
    {
        "id": "mock-emp-uuid-5",
        "employee_no": "E0005",
        "name": "陈某某",
        "contract_company_id": "mock-company-uuid-factory-1",
        "department": "包装组",
        "position": "包装工",
        "hire_date": "2024-02-15",
        "leave_date": None,
        "is_active": True,
        "metadata": {
            "id_card_masked": "330***********2345",
            "phone_masked": "136****5432",
            "name_masked": "陈**",
        },
    },
    {
        "id": "mock-emp-uuid-6",
        "employee_no": "E0006",
        "name": "孙某某",
        "contract_company_id": "mock-company-uuid-factory-3",
        "department": "切割组",
        "position": "切割工",
        "hire_date": "2024-01-08",
        "leave_date": None,
        "is_active": True,
        "metadata": {
            "id_card_masked": "330***********6789",
            "phone_masked": "135****1098",
            "name_masked": "孙**",
        },
    },
]


# ---------------------------------------------------------------------------
# §3.4 fixed-costs — 覆盖契约 §3.4.1 全 10 个 cost_category 至少 1 条
# v1.3 不加 amortization 字段(撤回·  跨期摊销改走 §4.6 payment_requests)
# ---------------------------------------------------------------------------

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
# §3.5 payroll(by_department) — 6 个班组(v1.0 形态保留 ·  by_dept aggregation 兼容)
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
# §4.5 payroll(by_employee) — v1.3 真实落地 (每员工每月 1 行)
# 数据源策略(metadata 体现):
#     - 2026+ 走 salary_reconciliation(实发,排除 payment_method='cash' 现金避重)
#     - ≤2025 走 salary_declaration_details(无 reconciliation 历史数据)
# 字段 1:1 对齐契约 v1.3 §4.5 + finance 备忘录 v0.4 §4.5
# ---------------------------------------------------------------------------

MOCK_PAYROLL_BY_EMPLOYEE: List[Dict[str, Any]] = [
    {
        "employee_id": "mock-emp-uuid-1",
        "employee_no": "E0001",
        "name_masked": "张**",
        "company_id": "mock-company-uuid-factory-1",
        "department_raw": "缝纫一组",
        "period_year": _DEFAULT_PERIOD_YEAR,
        "period_month": _DEFAULT_PERIOD_MONTH,
        "workdays": 21.5,
        "gross_salary": 6800.00,
        "employer_insurance": 1360.00,
        "total_labor_cost": 8160.00,
        "metadata": {
            "actual_paid": 6125.50,
            "payment_source_types": ["salary_reconciliation"],
            "fallback_reason": None,
        },
    },
    {
        "employee_id": "mock-emp-uuid-4",
        "employee_no": "E0004",
        "name_masked": "刘**",
        "company_id": "mock-company-uuid-factory-1",
        "department_raw": "缝纫一组",
        "period_year": _DEFAULT_PERIOD_YEAR,
        "period_month": _DEFAULT_PERIOD_MONTH,
        "workdays": 21.0,
        "gross_salary": 5500.00,
        "employer_insurance": 1100.00,
        "total_labor_cost": 6600.00,
        "metadata": {
            "actual_paid": 4980.00,
            "payment_source_types": ["salary_reconciliation"],
            "fallback_reason": None,
        },
    },
    {
        "employee_id": "mock-emp-uuid-2",
        "employee_no": "E0002",
        "name_masked": "李**",
        "company_id": "mock-company-uuid-factory-1",
        "department_raw": "缝纫二组",
        "period_year": _DEFAULT_PERIOD_YEAR,
        "period_month": _DEFAULT_PERIOD_MONTH,
        "workdays": 21.0,
        "gross_salary": 5800.00,
        "employer_insurance": 1160.00,
        "total_labor_cost": 6960.00,
        "metadata": {
            "actual_paid": 5230.00,
            # 演示混合源场景: 2026 主走 reconciliation · 但 payment_method=cash
            # 那笔被排除时部分员工会 fallback 到 declaration 兜底
            "payment_source_types": ["salary_reconciliation", "salary_declaration_details"],
            "fallback_reason": "partial_cash_excluded — fallback to declaration for cash portion",
        },
    },
    {
        "employee_id": "mock-emp-uuid-5",
        "employee_no": "E0005",
        "name_masked": "陈**",
        "company_id": "mock-company-uuid-factory-1",
        "department_raw": "包装组",
        "period_year": _DEFAULT_PERIOD_YEAR,
        "period_month": _DEFAULT_PERIOD_MONTH,
        "workdays": 22.0,
        "gross_salary": 5000.00,
        "employer_insurance": 1000.00,
        "total_labor_cost": 6000.00,
        "metadata": {
            "actual_paid": 4500.00,
            "payment_source_types": ["salary_reconciliation"],
            "fallback_reason": None,
        },
    },
    {
        "employee_id": "mock-emp-uuid-3",
        "employee_no": "E0003",
        "name_masked": "王**",
        "company_id": "mock-company-uuid-factory-2",
        "department_raw": "印染组",
        "period_year": _DEFAULT_PERIOD_YEAR,
        "period_month": _DEFAULT_PERIOD_MONTH,
        "workdays": 21.5,
        "gross_salary": 6400.00,
        "employer_insurance": 1280.00,
        "total_labor_cost": 7680.00,
        "metadata": {
            "actual_paid": 5760.00,
            "payment_source_types": ["salary_reconciliation"],
            "fallback_reason": None,
        },
    },
    {
        "employee_id": "mock-emp-uuid-6",
        "employee_no": "E0006",
        "name_masked": "孙**",
        "company_id": "mock-company-uuid-factory-3",
        "department_raw": "切割组",
        "period_year": _DEFAULT_PERIOD_YEAR,
        "period_month": _DEFAULT_PERIOD_MONTH,
        "workdays": 21.0,
        "gross_salary": 5500.00,
        "employer_insurance": 1100.00,
        "total_labor_cost": 6600.00,
        "metadata": {
            "actual_paid": 4950.00,
            "payment_source_types": ["salary_reconciliation"],
            "fallback_reason": None,
        },
    },
]


# ---------------------------------------------------------------------------
# §4.6 payment_requests — v1.3 新增 (12 条 ·  6 类 expense_category 各 ≥ 2 条)
# ·  含 amort 5 字段完整摊销配置
# ·  含 pay_company vs company_name 不同的 A 付 B 受益场景
# ·  含 invoice_status / match_status 应付分析字段
# ---------------------------------------------------------------------------

MOCK_PAYMENT_REQUESTS: List[Dict[str, Any]] = [
    # === cogs (2 条) === 主营成本类
    {
        "id": "mock-pr-uuid-cogs-1",
        "payment_date": "2026-04-08",
        "belong_month": "202604",
        "amount": 58000.00,
        "company_name": "杭州某某家居饰品有限公司",
        "company_id": "mock-company-uuid-factory-1",
        "pay_company": "杭州某某家居饰品有限公司",
        "store_department": "缝纫车间",
        "primary_subject": "主营业务成本",
        "secondary_subject": "面料采购",
        "expense_category": "cogs",
        "is_monthly_amortized": False,
        "amort_months": None,
        "amort_start_period": None,
        "amort_end_period": None,
        "amort_monthly_amount": None,
        "reason": "4 月份面料采购(春夏新品)",
        "notes": None,
        "match_status": "full",
        "matched_amount": 58000.00,
        "invoice_status": "已回票",
        "invoice_gap": 0.00,
        "metadata": {},
    },
    {
        "id": "mock-pr-uuid-cogs-2",
        "payment_date": "2026-04-15",
        "belong_month": "202604",
        "amount": 12000.00,
        "company_name": "杭州某某印染有限公司",
        "company_id": "mock-company-uuid-factory-2",
        "pay_company": "杭州某某家居饰品有限公司",
        "store_department": "印染车间",
        "primary_subject": "主营业务成本",
        "secondary_subject": "印染加工费",
        "expense_category": "cogs",
        "is_monthly_amortized": False,
        "amort_months": None,
        "amort_start_period": None,
        "amort_end_period": None,
        "amort_monthly_amount": None,
        "reason": "4 月外协印染加工费(A 主体付钱、B 主体受益场景)",
        "notes": "factory-1 代付印染厂(factory-2)·  受益主体是 factory-2",
        "match_status": "full",
        "matched_amount": 12000.00,
        "invoice_status": "已回票",
        "invoice_gap": 0.00,
        "metadata": {},
    },
    # === selling (2 条) === 销售费用类
    {
        "id": "mock-pr-uuid-selling-1",
        "payment_date": "2026-04-12",
        "belong_month": "202604",
        "amount": 26000.00,
        "company_name": "杭州饰家如画电子商务有限公司",
        "company_id": "mock-company-uuid-shop-1",
        "pay_company": "杭州饰家如画电子商务有限公司",
        "store_department": "天猫旗舰店",
        "primary_subject": "销售费用",
        "secondary_subject": "平台佣金",
        "expense_category": "selling",
        "is_monthly_amortized": False,
        "amort_months": None,
        "amort_start_period": None,
        "amort_end_period": None,
        "amort_monthly_amount": None,
        "reason": "天猫 4 月佣金(直通车 + 万相台)",
        "notes": None,
        "match_status": "full",
        "matched_amount": 26000.00,
        "invoice_status": "已回票",
        "invoice_gap": 0.00,
        "metadata": {},
    },
    {
        "id": "mock-pr-uuid-selling-2",
        "payment_date": "2026-04-20",
        "belong_month": "202604",
        "amount": 4500.00,
        "company_name": "杭州饰家如画电子商务有限公司",
        "company_id": "mock-company-uuid-shop-1",
        "pay_company": "杭州饰家如画电子商务有限公司",
        "store_department": "天猫旗舰店",
        "primary_subject": "销售费用",
        "secondary_subject": "退换货运费",
        "expense_category": "selling",
        "is_monthly_amortized": False,
        "amort_months": None,
        "amort_start_period": None,
        "amort_end_period": None,
        "amort_monthly_amount": None,
        "reason": "4 月售后退换货运费(店铺承担)",
        "notes": None,
        "match_status": "partial",
        "matched_amount": 3800.00,
        "invoice_status": "未开票",
        "invoice_gap": 700.00,
        "metadata": {},
    },
    # === admin (2 条 ·  含 12 月跨期摊销) === 管理费用类
    {
        "id": "mock-pr-uuid-admin-1",
        "payment_date": "2026-01-10",
        "belong_month": "202601",
        "amount": 12000.00,
        "company_name": "杭州某某家居饰品有限公司",
        "company_id": "mock-company-uuid-factory-1",
        "pay_company": "杭州某某家居饰品有限公司",
        "store_department": "厂部办公室",
        "primary_subject": "管理费用",
        "secondary_subject": "办公费",
        "expense_category": "admin",
        "is_monthly_amortized": True,
        "amort_months": 12,
        "amort_start_period": "202601",
        "amort_end_period": "202612",
        "amort_monthly_amount": 1000.00,
        "reason": "全年办公耗材采购(跨期 12 月平摊)",
        "notes": None,
        "match_status": "full",
        "matched_amount": 12000.00,
        "invoice_status": "已回票",
        "invoice_gap": 0.00,
        "metadata": {},
    },
    {
        "id": "mock-pr-uuid-admin-2",
        "payment_date": "2026-04-05",
        "belong_month": "202604",
        "amount": 35000.00,
        "company_name": "杭州某某家居饰品有限公司",
        "company_id": "mock-company-uuid-factory-1",
        "pay_company": "杭州某某家居饰品有限公司",
        "store_department": "厂部",
        "primary_subject": "管理费用",
        "secondary_subject": "房租",
        "expense_category": "admin",
        "is_monthly_amortized": False,
        "amort_months": None,
        "amort_start_period": None,
        "amort_end_period": None,
        "amort_monthly_amount": None,
        "reason": "4 月厂区房租",
        "notes": None,
        "match_status": "full",
        "matched_amount": 35000.00,
        "invoice_status": "已回票",
        "invoice_gap": 0.00,
        "metadata": {},
    },
    # === financial (2 条) === 财务费用类
    {
        "id": "mock-pr-uuid-financial-1",
        "payment_date": "2026-04-01",
        "belong_month": "202604",
        "amount": 1200.00,
        "company_name": "杭州某某家居饰品有限公司",
        "company_id": "mock-company-uuid-factory-1",
        "pay_company": "杭州某某家居饰品有限公司",
        "store_department": "财务",
        "primary_subject": "财务费用",
        "secondary_subject": "银行手续费",
        "expense_category": "financial",
        "is_monthly_amortized": False,
        "amort_months": None,
        "amort_start_period": None,
        "amort_end_period": None,
        "amort_monthly_amount": None,
        "reason": "4 月银行账户管理费 + 跨行手续费",
        "notes": None,
        "match_status": "full",
        "matched_amount": 1200.00,
        "invoice_status": "已回票",
        "invoice_gap": 0.00,
        "metadata": {},
    },
    {
        "id": "mock-pr-uuid-financial-2",
        "payment_date": "2026-04-25",
        "belong_month": "202604",
        "amount": 3500.00,
        "company_name": "杭州某某家居饰品有限公司",
        "company_id": "mock-company-uuid-factory-1",
        "pay_company": "杭州某某家居饰品有限公司",
        "store_department": "财务",
        "primary_subject": "财务费用",
        "secondary_subject": "贷款利息",
        "expense_category": "financial",
        "is_monthly_amortized": False,
        "amort_months": None,
        "amort_start_period": None,
        "amort_end_period": None,
        "amort_monthly_amount": None,
        "reason": "工厂经营贷款 4 月利息",
        "notes": None,
        "match_status": "full",
        "matched_amount": 3500.00,
        "invoice_status": "已回票",
        "invoice_gap": 0.00,
        "metadata": {},
    },
    # === capital_recovery (2 条 ·  含设备采购跨期摊销) === 资本性支出回收类
    {
        "id": "mock-pr-uuid-capital-1",
        "payment_date": "2026-01-15",
        "belong_month": "202601",
        "amount": 60000.00,
        "company_name": "杭州某某家居饰品有限公司",
        "company_id": "mock-company-uuid-factory-1",
        "pay_company": "杭州某某家居饰品有限公司",
        "store_department": "缝纫车间",
        "primary_subject": "固定资产",
        "secondary_subject": "缝纫设备",
        "expense_category": "capital_recovery",
        "is_monthly_amortized": True,
        "amort_months": 60,
        "amort_start_period": "202601",
        "amort_end_period": "203012",
        "amort_monthly_amount": 1000.00,
        "reason": "新增 5 台工业缝纫机(5 年摊销)",
        "notes": None,
        "match_status": "full",
        "matched_amount": 60000.00,
        "invoice_status": "已回票",
        "invoice_gap": 0.00,
        "metadata": {},
    },
    {
        "id": "mock-pr-uuid-capital-2",
        "payment_date": "2026-03-20",
        "belong_month": "202603",
        "amount": 24000.00,
        "company_name": "杭州某某印染有限公司",
        "company_id": "mock-company-uuid-factory-2",
        "pay_company": "杭州某某家居饰品有限公司",
        "store_department": "印染车间",
        "primary_subject": "固定资产",
        "secondary_subject": "印染设备",
        "expense_category": "capital_recovery",
        "is_monthly_amortized": True,
        "amort_months": 24,
        "amort_start_period": "202603",
        "amort_end_period": "202802",
        "amort_monthly_amount": 1000.00,
        "reason": "印染机维修升级(2 年摊销 ·  factory-1 代付)",
        "notes": "A 付 B 受益: factory-1 代付 ·  factory-2 受益",
        "match_status": "full",
        "matched_amount": 24000.00,
        "invoice_status": "已回票",
        "invoice_gap": 0.00,
        "metadata": {},
    },
    # === platform_recharge (2 条) === 平台充值类
    {
        "id": "mock-pr-uuid-recharge-1",
        "payment_date": "2026-04-02",
        "belong_month": "202604",
        "amount": 8000.00,
        "company_name": "杭州饰家如画电子商务有限公司",
        "company_id": "mock-company-uuid-shop-1",
        "pay_company": "杭州饰家如画电子商务有限公司",
        "store_department": "天猫旗舰店",
        "primary_subject": "其他应收款",
        "secondary_subject": "平台保证金",
        "expense_category": "platform_recharge",
        "is_monthly_amortized": False,
        "amort_months": None,
        "amort_start_period": None,
        "amort_end_period": None,
        "amort_monthly_amount": None,
        "reason": "天猫保证金充值",
        "notes": "性质: 押金 / 不计入当期成本",
        "match_status": "full",
        "matched_amount": 8000.00,
        "invoice_status": "无需开票",
        "invoice_gap": 0.00,
        "metadata": {},
    },
    {
        "id": "mock-pr-uuid-recharge-2",
        "payment_date": "2026-04-18",
        "belong_month": "202604",
        "amount": 5000.00,
        "company_name": "杭州饰家如画品牌管理有限公司(小规模)",
        "company_id": "mock-company-uuid-shop-2",
        "pay_company": "杭州饰家如画品牌管理有限公司(小规模)",
        "store_department": "京东店",
        "primary_subject": "其他应收款",
        "secondary_subject": "平台广告金",
        "expense_category": "platform_recharge",
        "is_monthly_amortized": False,
        "amort_months": None,
        "amort_start_period": None,
        "amort_end_period": None,
        "amort_monthly_amount": None,
        "reason": "京东快车充值",
        "notes": None,
        "match_status": "full",
        "matched_amount": 5000.00,
        "invoice_status": "已回票",
        "invoice_gap": 0.00,
        "metadata": {},
    },
]


# ---------------------------------------------------------------------------
# Helpers — client / 测试 / 校验脚本共用
# ---------------------------------------------------------------------------

# v1.3 §4.4 ?since/?until 增量参数 — mock 模式下用 ISO 字符串简单做字符串比较
# (生产 finance 端是 SQLAlchemy WHERE updated_at >= since · 这里 mock 简化)
_DEFAULT_UPDATED_AT = "2026-05-08T10:00:00+08:00"


def _passes_since_until(
    updated_at: Optional[str],
    since: Optional[str],
    until: Optional[str],
) -> bool:
    """ISO 字符串字典序比较 ·  ISO 8601 词典序与时间序一致 ·  无需 datetime 解析。

    mock 数据没有真的 updated_at 字段时统一用 _DEFAULT_UPDATED_AT 兜底; 这样
    --since=2026-04-01 / --until=2026-06-01 这种粗粒度过滤也能跑通 smoke 脚本。
    """

    actual = updated_at or _DEFAULT_UPDATED_AT
    if since is not None and actual < since:
        return False
    if until is not None and actual >= until:
        return False
    return True


def get_companies(
    *,
    entity_role: str | None = None,
    is_active: bool | None = True,
    since: str | None = None,
    until: str | None = None,
) -> List[Dict[str, Any]]:
    """模拟 GET /api/v1/c1/companies 的过滤行为。

    deepcopy 是为了让上层 cache 写入不会被外部 mutate 污染原始 mock 数据。
    """

    rows = [deepcopy(r) for r in MOCK_COMPANIES]
    if entity_role:
        rows = [r for r in rows if r.get("entity_role") == entity_role]
    if is_active is not None:
        rows = [r for r in rows if bool(r.get("is_active")) == bool(is_active)]
    rows = [r for r in rows if _passes_since_until(r.get("updated_at"), since, until)]
    return rows


def get_stores(
    *,
    company_id: str | None = None,
    is_active: bool | None = True,
    since: str | None = None,
    until: str | None = None,
) -> List[Dict[str, Any]]:
    rows = [deepcopy(r) for r in MOCK_STORES]
    if company_id:
        rows = [r for r in rows if r.get("company_id") == company_id]
    if is_active is not None:
        rows = [r for r in rows if bool(r.get("is_active")) == bool(is_active)]
    rows = [r for r in rows if _passes_since_until(r.get("updated_at"), since, until)]
    return rows


def get_stores_revenue(
    *,
    period_year: int,
    period_month: int,
    store_id: str | None = None,
    since: str | None = None,
    until: str | None = None,
) -> List[Dict[str, Any]]:
    """模拟 GET /api/v1/c1/stores/revenue (v1.3 §4.2)。"""

    rows = [deepcopy(r) for r in MOCK_STORES_REVENUE]
    rows = [
        r
        for r in rows
        if r.get("period_year") == period_year and r.get("period_month") == period_month
    ]
    if store_id:
        rows = [r for r in rows if r.get("store_id") == store_id]
    rows = [
        r
        for r in rows
        if _passes_since_until(r.get("snapshot_at") or r.get("updated_at"), since, until)
    ]
    return rows


def get_employees(
    *,
    contract_company_id: str | None = None,
    is_active: bool | None = True,
    since: str | None = None,
    until: str | None = None,
) -> List[Dict[str, Any]]:
    rows = [deepcopy(r) for r in MOCK_EMPLOYEES]
    if contract_company_id:
        rows = [r for r in rows if r.get("contract_company_id") == contract_company_id]
    if is_active is not None:
        rows = [r for r in rows if bool(r.get("is_active")) == bool(is_active)]
    rows = [r for r in rows if _passes_since_until(r.get("updated_at"), since, until)]
    return rows


def get_fixed_costs(
    *,
    period_year: int | None = None,
    period_month: int | None = None,
    cost_category: str | None = None,
    company_id: str | None = None,
    since: str | None = None,
    until: str | None = None,
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
    rows = [r for r in rows if _passes_since_until(r.get("updated_at"), since, until)]
    return rows


def get_payroll(
    *,
    company_id: str,
    period_year: int,
    period_month: int,
    aggregation: str = "by_department",
    since: str | None = None,
    until: str | None = None,
) -> List[Dict[str, Any]]:
    """支持 by_department(v1.0 兼容) + by_employee(v1.3 真实落地)。"""

    if aggregation == "by_employee":
        source = MOCK_PAYROLL_BY_EMPLOYEE
    else:
        source = MOCK_PAYROLL

    rows = [deepcopy(r) for r in source]
    rows = [
        r
        for r in rows
        if r.get("company_id") == company_id
        and r.get("period_year") == period_year
        and r.get("period_month") == period_month
    ]
    rows = [r for r in rows if _passes_since_until(r.get("updated_at"), since, until)]
    return rows


def get_payment_requests(
    *,
    period: str | None = None,
    company_id: str | None = None,
    pay_company: str | None = None,
    expense_category: str | None = None,
    is_amortized: bool | None = None,
    amort_covers_period: str | None = None,
    since: str | None = None,
    until: str | None = None,
) -> List[Dict[str, Any]]:
    """模拟 GET /api/v1/c1/payment-requests (v1.3 §4.6)。

    `amort_covers_period` 是 finance 主动加的额外参数: 拉所有
    `amort_start_period <= period <= amort_end_period` 的凭证 ·  让
    costing fixed_cost_amortizer_service 一次性拿到所有"覆盖目标月"的摊销项。
    """

    rows = [deepcopy(r) for r in MOCK_PAYMENT_REQUESTS]
    if period:
        rows = [r for r in rows if r.get("belong_month") == period]
    if company_id:
        rows = [r for r in rows if r.get("company_id") == company_id]
    if pay_company:
        rows = [r for r in rows if r.get("pay_company") == pay_company]
    if expense_category:
        rows = [r for r in rows if r.get("expense_category") == expense_category]
    if is_amortized is not None:
        rows = [
            r for r in rows if bool(r.get("is_monthly_amortized")) == bool(is_amortized)
        ]
    if amort_covers_period:
        rows = [
            r
            for r in rows
            if r.get("is_monthly_amortized")
            and r.get("amort_start_period") is not None
            and r.get("amort_end_period") is not None
            and r["amort_start_period"] <= amort_covers_period <= r["amort_end_period"]
        ]
    rows = [r for r in rows if _passes_since_until(r.get("payment_date"), since, until)]
    return rows


def now_iso() -> str:
    """v1.3 envelope.pagination.last_updated_at 用 ·  避免每条 mock 写死时间。"""

    return datetime.now(timezone.utc).isoformat()


__all__ = [
    "MOCK_COMPANIES",
    "MOCK_STORES",
    "MOCK_STORES_REVENUE",
    "MOCK_EMPLOYEES",
    "MOCK_FIXED_COSTS",
    "MOCK_PAYROLL",
    "MOCK_PAYROLL_BY_EMPLOYEE",
    "MOCK_PAYMENT_REQUESTS",
    "get_companies",
    "get_stores",
    "get_stores_revenue",
    "get_employees",
    "get_fixed_costs",
    "get_payroll",
    "get_payment_requests",
    "now_iso",
]
