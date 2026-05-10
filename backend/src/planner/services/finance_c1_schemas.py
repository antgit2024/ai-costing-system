"""Pydantic v1 schemas for finance → costing C1 contract (v1.0).

每个 DTO 与契约 `DOC/costing/blueprints/finance_to_costing_c1_contract_v1.md`
§3.1 ~ §3.5 的 example response 字段 1:1 对齐 · 字段顺序、命名、可选性
全部按契约。

Note (2026-05-10):
- 这一版作 client 内部 typed view · 也作 `/api/planner/finance/*` 代理出参
  (FastAPI 自动序列化)·前端用对应 TS 类型对齐(详见
  `frontend/src/types/financeC1.ts`)。
- 项目根仍用 Pydantic v1·所以这里禁止使用 v2-only 的 `field_validator` /
  `model_config` 等 API。
- 不依赖 SQLAlchemy: 这些 DTO 只是「网络数据结构」·costing 侧不存表。

文档位置: 与 client 放一起便于同源 import 路径短;不放进 monolithic
`backend/src/planner/schemas.py` 是为了避免与 cost_rate_master / models
schemas 混杂(C1 是「外部供数」语义,与本系统业务模型完全正交)。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

# --- Enum 类型别名 (契约 §3.1) ---
TaxPayerType = Literal["general", "small_scale"]
EntityRole = Literal["factory", "shop", "holding", "mixed"]

# --- §3.4.1 cost_category 标准枚举 ---
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


# ---------------------------------------------------------------------------
# §3.1 GET /api/v1/c1/companies — 法人主体
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
# §3.4 GET /api/v1/c1/fixed-costs — 固定开支台账
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
# §3.5 GET /api/v1/c1/payroll — 工资单(高敏感)
# ---------------------------------------------------------------------------


class FinancePayrollDTO(BaseModel):
    """by_department 聚合 ·  by_employee 模式留给 v1.5 单独建。"""

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
        api_version: finance 侧返回的 _api_version (没有则填 None)。
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
    "FinanceCompanyDTO",
    "FinanceStoreDTO",
    "FinanceEmployeeDTO",
    "FinanceFixedCostDTO",
    "FinancePayrollDTO",
    "DataSource",
    "FinanceC1ListEnvelope",
]
