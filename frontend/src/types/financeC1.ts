/**
 * Finance → costing C1 contract DTO TypeScript 类型(派单 §2.8)。
 *
 * 与 backend `src/planner/services/finance_c1_schemas.py` 1:1 对齐。
 * 字段命名/可选性/枚举值都按契约
 * `DOC/costing/blueprints/finance_to_costing_c1_contract_v1.md` §3。
 *
 * 「数据来源」语义(派单 §3.4):
 *   - live  : finance 实时拉成功(可能是 5min TTL cache 命中,本质是新鲜数据) → 🟢
 *   - cache : finance 挂了 fallback 用 _last_good   → 🟡 显示 "Xm ago"
 *   - mock  : 开发环境 use_mock=true               → 🔵
 */

export type FinanceC1TaxPayerType = 'general' | 'small_scale'
export type FinanceC1EntityRole = 'factory' | 'shop' | 'holding' | 'mixed'
export type FinanceC1DataSource = 'live' | 'cache' | 'mock'

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

/** §3.4.1 标准枚举(11 项) — 派单 brief §2.6 C3 测试也按此聚合。 */
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

/**
 * 客户端从 `/api/planner/finance/*` 收到的统一信封。
 * 直接对齐后端 `FinanceC1ListEnvelope`(Pydantic)。
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
    total_pages: number
  } | null
}
