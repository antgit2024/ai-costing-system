/**
 * Finance → costing C1 contract DTO TypeScript 类型(v1.3 终态)。
 *
 * 与 backend `src/planner/services/finance_c1_schemas.py` 1:1 对齐。
 * 字段命名/可选性/枚举值都按契约
 * `DOC/costing/blueprints/finance_to_costing_c1_contract_v1.3_aligned.md` §4。
 *
 * v1.3 增量(2026-05-10):
 *   - `FinanceCompanyDTO` 加 4 recognition Boolean + `floor_area_sqm`
 *   - 新增 `FinanceStoreRevenueDTO`(§4.2 — 店铺月度真实营收)
 *   - 新增 `FinancePaymentRequestDTO`(§4.6 — 付款凭证 amort + 6 类 + pay_company)
 *   - `FinancePayrollByEmployeeDTO`(§4.5 — 每员工每月 1 行)
 *   - envelope `_api_version` 升 `1.3`,加 `pagination.last_updated_at`
 *
 * 「数据来源」语义(派单 §3.4):
 *   - live  : finance 实时拉成功(可能是 5min TTL cache 命中,本质是新鲜数据) → 🟢
 *   - cache : finance 挂了 fallback 用 _last_good   → 🟡 显示 "Xm ago"
 *   - mock  : 开发环境 use_mock=true               → 🔵
 */

export type FinanceC1TaxPayerType = 'general' | 'small_scale'
export type FinanceC1EntityRole = 'factory' | 'shop' | 'holding' | 'mixed'
export type FinanceC1DataSource = 'live' | 'cache' | 'mock'
export type FinanceC1DataQuality = 'green' | 'yellow' | 'red'
export type FinanceC1MatchStatus = 'full' | 'partial' | 'none' | 'unmatched'

/** v1.3 §4.6 6 类管理会计分类(payment_requests 用) */
export type FinanceExpenseCategory =
  | 'cogs'
  | 'selling'
  | 'admin'
  | 'financial'
  | 'capital_recovery'
  | 'platform_recharge'

export interface FinanceCompanyDTO {
  id: string
  legal_name: string
  tax_payer_type: FinanceC1TaxPayerType
  unified_social_credit_code?: string | null
  entity_role: FinanceC1EntityRole
  parent_company_id?: string | null
  is_active: boolean
  effective_from?: string | null
  effective_to?: string | null
  /** v1.3 §4.1: 4 业务画像 Boolean(默认 false 兼容老数据) */
  revenue_recognition?: boolean
  material_purchase_recognition?: boolean
  payroll_recognition?: boolean
  fixed_cost_recognition?: boolean
  /** v1.3 §4.10: 主体厂房/办公面积(平米); NULL = ops 暂未测量 */
  floor_area_sqm?: number | null
  metadata?: Record<string, unknown>
}

export interface FinanceStoreDTO {
  id: string
  store_name: string
  company_id: string
  platform?: string | null
  platform_shop_id?: string | null
  manager_name?: string | null
  main_category?: string | null
  monthly_revenue_avg?: number | null
  is_active: boolean
  metadata?: Record<string, unknown>
}

/** v1.3 §4.2 店铺月度真实营业额 */
export interface FinanceStoreRevenueDTO {
  store_id: string
  store_name: string
  company_id: string
  platform?: string | null
  period_year: number
  period_month: number
  gross_revenue: number
  net_revenue: number
  platform_fee_paid?: number | null
  withdraw_amount?: number | null
  data_source?: string | null
  data_quality?: FinanceC1DataQuality | null
  snapshot_at?: string | null
  metadata?: Record<string, unknown>
}

export interface FinanceEmployeeDTO {
  id: string
  employee_no: string
  name: string
  contract_company_id: string
  department?: string | null
  position?: string | null
  hire_date?: string | null
  leave_date?: string | null
  is_active: boolean
  metadata?: Record<string, unknown>
}

/** §3.4.1 标准枚举(10 项) — 派单 brief §2.6 C3 测试也按此聚合。 */
export type FinanceFixedCostCategory =
  | 'rent'
  | 'utility'
  | 'salary_admin'
  | 'insurance_admin'
  | 'office_supplies'
  | 'depreciation'
  | 'logistics'
  | 'platform_fee'
  | 'after_sales'
  | 'others'

export interface FinanceFixedCostDTO {
  id: string
  company_id: string
  period_year: number
  period_month: number
  cost_category: FinanceFixedCostCategory
  cost_subcategory?: string | null
  amount: number
  tax_included: boolean
  tax_rate?: number | null
  description?: string | null
  approver?: string | null
  metadata?: Record<string, unknown>
}

/** v1.0 by_department 聚合 ·  v1.3 仍保留兼容 */
export interface FinancePayrollDTO {
  company_id: string
  department: string
  period_year: number
  period_month: number
  headcount: number
  total_gross_salary: number
  total_employer_insurance: number
  total_labor_cost: number
  avg_workdays?: number | null
  metadata?: Record<string, unknown>
}

/** v1.3 §4.5 真实落地 by_employee — 每员工每月 1 行 */
export interface FinancePayrollByEmployeeDTO {
  employee_id: string
  employee_no: string
  name_masked: string
  company_id: string
  department_raw?: string | null
  period_year: number
  period_month: number
  workdays?: number | null
  gross_salary: number
  employer_insurance: number
  total_labor_cost: number
  metadata?: Record<string, unknown> & {
    actual_paid?: number
    payment_source_types?: string[]
    fallback_reason?: string | null
  }
}

/** v1.3 §4.6 付款凭证(含 amort + 6 类 + pay_company vs company_name) */
export interface FinancePaymentRequestDTO {
  id: string
  payment_date: string
  belong_month: string
  amount: number
  company_name: string
  company_id: string
  pay_company?: string | null
  store_department?: string | null
  primary_subject?: string | null
  secondary_subject?: string | null
  expense_category: FinanceExpenseCategory
  is_monthly_amortized: boolean
  amort_months?: number | null
  amort_start_period?: string | null
  amort_end_period?: string | null
  amort_monthly_amount?: number | null
  reason?: string | null
  notes?: string | null
  match_status?: FinanceC1MatchStatus | null
  matched_amount?: number | null
  invoice_status?: string | null
  invoice_gap?: number | null
  metadata?: Record<string, unknown>
}

/**
 * 客户端从 `/api/planner/finance/*` 收到的统一信封。
 * 直接对齐后端 `FinanceC1ListEnvelope`(Pydantic)。
 *
 * v1.3 加 `pagination.last_updated_at`(增量同步推进点)。
 */
export interface FinanceC1ListEnvelope<T> {
  data: T[]
  data_source: FinanceC1DataSource
  cache_age_seconds?: number | null
  fetched_at: string
  api_version?: string | null
  pagination?: {
    page: number
    page_size: number
    total: number
    total_pages?: number
    /** v1.3 §4.4: ISO 时间 ·  下次增量拉取的推进点 */
    last_updated_at?: string
  } | null
}
