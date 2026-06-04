"""Pydantic v1 schemas for finance → costing C1 contract (v1.3 终态).

每个 DTO 与契约 `DOC/costing/blueprints/finance_to_costing_c1_contract_v1.3_aligned.md`
§4 的 example response 字段 1:1 对齐 · 字段顺序、命名、可选性全部按契约。

v1.3 增量(本次升级):
    - `FinanceCompanyDTO` 加 4 个 recognition Boolean + `floor_area_sqm`
      (契约 §4.1 + §4.10)
    - 新增 `FinanceStoreRevenueDTO` (契约 §4.2)
    - 新增 `FinancePaymentRequestDTO` (契约 §4.6 — finance 主动提案的付款凭证)
    - `FinancePayrollByEmployeeDTO` (契约 §4.5 — 每员工每月 1 行)
    - envelope `_api_version` 升 `1.3`,加 `pagination.last_updated_at`

Note (2026-05-10):
    - 项目根仍用 Pydantic v1·所以这里禁止使用 v2-only 的 `field_validator` /
      `model_config` 等 API。
    - 不依赖 SQLAlchemy: 这些 DTO 只是「网络数据结构」·costing 侧不存表。
    - 老的 `FinancePayrollDTO`(by_department)保留 · 因为 client/router 里
      `aggregation=by_department` 仍然合法(契约 v1.3 §4.5 没撤回 by_department)。

文档位置: 与 client 放一起便于同源 import 路径短;不放进 monolithic
`backend/src/planner/schemas.py` 是为了避免与 cost_rate_master / models
schemas 混杂(C1 是「外部供数」语义,与本系统业务模型完全正交)。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

# --- Enum 类型别名 (契约 §3.1 / §4.1) ---
TaxPayerType = Literal["general", "small_scale"]
EntityRole = Literal["factory", "shop", "holding", "mixed"]

# --- §3.4.1 cost_category 标准枚举 (fixed-costs 用) ---
CostCategory = Literal[
    "rent",
    "utility",
    "salary_admin",
    "insurance_admin",
    "office_supplies",
    "depreciation",
    "logistics",
    "platform_fee",
    "after_sales",
    "others",
]

# 11 项标准 cost_category(下游汇总测试用) ·  C3 测试断言 ≥ 11 桶。
COST_CATEGORY_CHOICES: tuple[str, ...] = (
    "rent",
    "utility",
    "salary_admin",
    "insurance_admin",
    "office_supplies",
    "depreciation",
    "logistics",
    "platform_fee",
    "after_sales",
    "others",
)

# --- §4.6 expense_category 6 类管理会计分类(payment_requests 用) ---
ExpenseCategory = Literal[
    "cogs",
    "selling",
    "admin",
    "financial",
    "capital_recovery",
    "platform_recharge",
]

EXPENSE_CATEGORY_CHOICES: tuple[str, ...] = (
    "cogs",
    "selling",
    "admin",
    "financial",
    "capital_recovery",
    "platform_recharge",
)


# ---------------------------------------------------------------------------
# §4.1 + §4.10 GET /api/v1/c1/companies — 法人主体(v1.3 加 4 标签 + 1 面积)
# ---------------------------------------------------------------------------


class FinanceCompanyDTO(BaseModel):
    id: str = Field(..., description="canonical subject ID = master_companies.id (UUID)")
    legal_name: str
    tax_payer_type: TaxPayerType
    unified_social_credit_code: Optional[str] = None
    entity_role: EntityRole
    parent_company_id: Optional[str] = None
    is_active: bool = True
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None

    # --- v1.3 §4.1 4 个业务画像 Boolean(默认 false 兼容老数据)---
    revenue_recognition: bool = Field(
        False, description="真实营收归此主体(v1.3 §4.1)"
    )
    material_purchase_recognition: bool = Field(
        False, description="真实材料成本归此主体(v1.3 §4.1)"
    )
    payroll_recognition: bool = Field(
        False, description="真实人工成本归此主体(v1.3 §4.1)"
    )
    fixed_cost_recognition: bool = Field(
        False, description="真实固开归此主体(v1.3 §4.1)"
    )

    # --- v1.3 §4.10 floor_area_sqm 可空 ---
    floor_area_sqm: Optional[float] = Field(
        None,
        description=(
            "主体使用的厂房/办公面积(平米); NULL = ops 暂未测量, "
            "costing 侧 cost_allocator_service 自动 fallback 到 headcount/revenue"
        ),
    )

    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        # 允许 unknown 字段直接丢掉(向后兼容: finance 加新字段不破坏 costing 端)
        extra = "ignore"


# ---------------------------------------------------------------------------
# §3.2 GET /api/v1/c1/stores — 店铺
# ---------------------------------------------------------------------------


class FinanceStoreDTO(BaseModel):
    id: str
    store_name: str
    company_id: str = Field(..., description="引 master_companies.id (FK)")
    platform: Optional[str] = None
    platform_shop_id: Optional[str] = None
    manager_name: Optional[str] = None
    main_category: Optional[str] = None
    monthly_revenue_avg: Optional[float] = None
    is_active: bool = True
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        extra = "ignore"


# ---------------------------------------------------------------------------
# §4.2 GET /api/v1/c1/stores/revenue — 店铺月度真实营业额(v1.3 新增)
# ---------------------------------------------------------------------------


DataQuality = Literal["green", "yellow", "red"]


class FinanceStoreRevenueDTO(BaseModel):
    """店铺月度真实营业额(契约 v1.3 §4.2)。

    基于 finance 侧 LedgerMonthlySummary `profile_name='alipay_monthly_statement'`
    过滤后的权责制口径(优先 accrual_*,COALESCE 到收付制 sales_income_amount)。
    """

    store_id: str
    store_name: str
    company_id: str
    platform: Optional[str] = None
    period_year: int = Field(..., ge=2000, le=2100)
    period_month: int = Field(..., ge=1, le=12)
    gross_revenue: float = Field(..., description="毛收入(权责制优先,收付制兜底)")
    net_revenue: float = Field(
        ..., description="净收入 = gross - 退款(权责制优先,收付制兜底)"
    )
    platform_fee_paid: Optional[float] = Field(
        None, description="平台扣款(佣金 + 推广 + 技术服务费)"
    )
    withdraw_amount: Optional[float] = Field(None, description="Z01 提现到银行(参考用)")
    data_source: Optional[str] = Field(
        None, description="platform_api / manual / reconcile"
    )
    data_quality: Optional[DataQuality] = Field(
        None, description="green=完整 / yellow=部分缺失 / red=异常"
    )
    snapshot_at: Optional[datetime] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        extra = "ignore"


# ---------------------------------------------------------------------------
# §3.3 GET /api/v1/c1/employees — 员工花名册
# ---------------------------------------------------------------------------


class FinanceEmployeeDTO(BaseModel):
    id: str
    employee_no: str
    name: str
    contract_company_id: str = Field(..., description="工资发放主体(引 master_companies.id)")
    department: Optional[str] = None
    position: Optional[str] = None
    hire_date: Optional[date] = None
    leave_date: Optional[date] = None
    is_active: bool = True
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        extra = "ignore"


# ---------------------------------------------------------------------------
# §3.4 GET /api/v1/c1/fixed-costs — 固定开支台账(v1.3 不加 amortization 字段)
# ---------------------------------------------------------------------------


class FinanceFixedCostDTO(BaseModel):
    id: str
    company_id: str = Field(..., description="实际付款主体 (FK master_companies.id)")
    period_year: int
    period_month: int = Field(..., ge=1, le=12)
    cost_category: CostCategory
    cost_subcategory: Optional[str] = None
    amount: float
    tax_included: bool = True
    tax_rate: Optional[float] = None
    description: Optional[str] = None
    approver: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        extra = "ignore"


# ---------------------------------------------------------------------------
# §3.5 GET /api/v1/c1/payroll — 工资单(by_department,旧版 v1.0 形态保留)
# ---------------------------------------------------------------------------


class FinancePayrollDTO(BaseModel):
    """by_department 聚合 ·  v1.0 已实现 ·  v1.3 仍保留(契约 §4.5 仅强化 by_employee)。"""

    company_id: str
    department: str = Field(..., description="对应 costing cost_center 名称(如 '缝纫一组')")
    period_year: int
    period_month: int = Field(..., ge=1, le=12)
    headcount: int = Field(..., ge=0)
    total_gross_salary: float
    total_employer_insurance: float
    total_labor_cost: float
    avg_workdays: Optional[float] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        extra = "ignore"


# ---------------------------------------------------------------------------
# §4.5 GET /api/v1/c1/payroll?aggregation=by_employee — v1.3 真实落地(每员工每月 1 行)
# ---------------------------------------------------------------------------


class FinancePayrollByEmployeeDTO(BaseModel):
    """每员工每月 1 行(契约 v1.3 §4.5)。

    数据源策略(在 metadata.payment_source_types / fallback_reason 体现):
        - 2026+ 走 salary_reconciliation(实发,排除 payment_method='cash')
        - ≤2025 走 salary_declaration_details

    `gross_salary` 不再细拆 5 项(v1.1.1 撤回); finance 端用 total_labor_cost 统一口径。
    """

    employee_id: str
    employee_no: str
    name_masked: str = Field(
        ..., description="脱敏姓名(姓 + ** ·  与 employees 接口 metadata.name_masked 同源)"
    )
    company_id: str = Field(..., description="工资发放主体(引 master_companies.id)")
    department_raw: Optional[str] = Field(
        None, description="finance 端 raw 部门名(参考用; cost_center 归 costing 自建)"
    )
    period_year: int = Field(..., ge=2000, le=2100)
    period_month: int = Field(..., ge=1, le=12)
    workdays: Optional[float] = None
    gross_salary: float = Field(..., description="应发(税前总额; 不再拆细 v1.1.1 撤回)")
    employer_insurance: float = Field(..., description="公司部分五险一金")
    total_labor_cost: float = Field(..., description="gross_salary + employer_insurance")
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "含 actual_paid(实发) / payment_source_types(数据源 list) / "
            "fallback_reason(若用了 ≤2025 declaration 兜底说明)"
        ),
    )

    class Config:
        extra = "ignore"


# ---------------------------------------------------------------------------
# §4.6 GET /api/v1/c1/payment-requests — 付款凭证(v1.3 新增)
# ---------------------------------------------------------------------------


PaymentMatchStatus = Literal["full", "partial", "none", "unmatched"]


class FinancePaymentRequestDTO(BaseModel):
    """付款凭证(契约 v1.3 §4.6)。

    用途:
        - costing fixed_cost_amortizer_service 用 amort 5 字段平摊跨期费用
        - 解决「A 主体付钱、B 主体受益」场景(pay_company vs company_name)
        - 6 类 expense_category 管理会计分类(cogs/selling/admin/financial/capital_recovery/platform_recharge)
    """

    id: str
    payment_date: date
    belong_month: str = Field(..., description="YYYYMM 字符串", min_length=6, max_length=6)
    amount: float
    company_name: str = Field(..., description="费用承担主体(受益)")
    company_id: str = Field(..., description="受益主体 FK")
    pay_company: Optional[str] = Field(
        None, description="实际付款主体(可与 company_name 不同 — A 付 B 受益场景)"
    )
    store_department: Optional[str] = Field(None, description="店铺/部门归属")
    primary_subject: Optional[str] = Field(None, description="一级科目(管理费用 / 销售费用 / ...)")
    secondary_subject: Optional[str] = Field(None, description="二级科目(办公费 / 房租 / ...)")
    expense_category: ExpenseCategory

    # --- amort 5 字段(完整摊销引擎)---
    is_monthly_amortized: bool = False
    amort_months: Optional[int] = None
    amort_start_period: Optional[str] = Field(None, min_length=6, max_length=6)
    amort_end_period: Optional[str] = Field(None, min_length=6, max_length=6)
    amort_monthly_amount: Optional[float] = None

    reason: Optional[str] = None
    notes: Optional[str] = None

    # --- 银行流水匹配 + 发票回票(应付分析用)---
    match_status: Optional[PaymentMatchStatus] = None
    matched_amount: Optional[float] = None
    invoice_status: Optional[str] = None
    invoice_gap: Optional[float] = None

    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        extra = "ignore"


# ---------------------------------------------------------------------------
# 通用「数据来源」标记 — 客户端在每条 list 返回值里附带
# ---------------------------------------------------------------------------

DataSource = Literal["live", "cache", "mock"]


class FinanceC1ListEnvelope(BaseModel):
    """Client 返回给 Router 的统一信封 · 让前端 Badge 能区分 live/cache/mock。

    Fields:
        data: list of typed DTO dicts (不强制 Pydantic 实例 · 因为 client
              层内部用 dict 简化 cache 序列化 ·  Router 出参时由 FastAPI
              校验 schema)。
        data_source: live = finance 实时返回 · cache = finance 挂用上次结果
                     · mock = 开发环境 mock 数据。
        cache_age_seconds: data_source='cache' 时给(从 cache 写入到现在)
                           前端展示 "5m ago" 用。
        fetched_at: ISO 时间戳 (UTC) · 数据获取/读 cache 时间。
        api_version: finance 侧返回的 _api_version (没有则填 None) ·  v1.3 起为 "1.3"。
        pagination: 含 page/page_size/total ·  v1.3 起加 last_updated_at(用于
                    costing 增量同步的 ?since= 推进点)。
    """

    data: List[Dict[str, Any]]
    data_source: DataSource
    cache_age_seconds: Optional[float] = None
    fetched_at: datetime
    api_version: Optional[str] = None
    pagination: Optional[Dict[str, Any]] = None

    class Config:
        extra = "ignore"


__all__ = [
    "TaxPayerType",
    "EntityRole",
    "CostCategory",
    "COST_CATEGORY_CHOICES",
    "ExpenseCategory",
    "EXPENSE_CATEGORY_CHOICES",
    "DataQuality",
    "PaymentMatchStatus",
    "FinanceCompanyDTO",
    "FinanceStoreDTO",
    "FinanceStoreRevenueDTO",
    "FinanceEmployeeDTO",
    "FinanceFixedCostDTO",
    "FinancePayrollDTO",
    "FinancePayrollByEmployeeDTO",
    "FinancePaymentRequestDTO",
    "DataSource",
    "FinanceC1ListEnvelope",
]
