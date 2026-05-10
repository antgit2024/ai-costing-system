/**
 * Finance C1 fetchers(v1.3 终态)— 走后端 `/api/planner/finance/*` 代理。
 *
 * 不直接访问 finance-analyzer · 见契约 §6.1 鉴权统一在后端。所有 fetcher 共用
 * `plannerClient`(已含 baseURL + auth interceptors)。
 *
 * v1.3 增量(派单 §2.7):
 *   - 加 `fetchFinanceStoresRevenue`(§4.2 店铺月度真实营业额)
 *   - 加 `fetchFinancePaymentRequests`(§4.6 付款凭证)
 *   - 7 个 fetcher 统一支持 `?since/?until` 增量参数
 */

import { plannerClient, sanitizeParams } from './planner'
import type {
  FinanceC1ListEnvelope,
  FinanceCompanyDTO,
  FinanceEmployeeDTO,
  FinanceFixedCostDTO,
  FinancePayrollByEmployeeDTO,
  FinancePayrollDTO,
  FinancePaymentRequestDTO,
  FinanceStoreDTO,
  FinanceStoreRevenueDTO,
  FinanceExpenseCategory,
} from '../types/financeC1'

const BASE = '/finance'

/** v1.3 §4.4 增量参数 — 7 个 fetcher 共用 */
export interface SinceUntilParams {
  since?: string
  until?: string
}

export interface FetchCompaniesParams extends SinceUntilParams {
  entity_role?: 'factory' | 'shop' | 'holding' | 'mixed'
  is_active?: boolean
}

export interface FetchStoresParams extends SinceUntilParams {
  company_id?: string
  platform?: string
  is_active?: boolean
}

export interface FetchStoresRevenueParams extends SinceUntilParams {
  period_year: number
  period_month: number
  store_id?: string
}

export interface FetchEmployeesParams extends SinceUntilParams {
  contract_company_id?: string
  is_active?: boolean
}

export interface FetchFixedCostsParams extends SinceUntilParams {
  period_year: number
  period_month: number
  cost_category?: string
  company_id?: string
}

export interface FetchPayrollParams extends SinceUntilParams {
  company_id: string
  period_year: number
  period_month: number
  aggregation?: 'by_department' | 'by_employee'
}

export interface FetchPaymentRequestsParams extends SinceUntilParams {
  period?: string
  company_id?: string
  pay_company?: string
  expense_category?: FinanceExpenseCategory
  is_amortized?: boolean
  amort_covers_period?: string
}

export const fetchFinanceCompanies = async (
  params: FetchCompaniesParams = {},
): Promise<FinanceC1ListEnvelope<FinanceCompanyDTO>> => {
  const response = await plannerClient.get(`${BASE}/companies`, {
    params: sanitizeParams(params as Record<string, unknown>),
  })
  return response.data
}

export const fetchFinanceStores = async (
  params: FetchStoresParams = {},
): Promise<FinanceC1ListEnvelope<FinanceStoreDTO>> => {
  const response = await plannerClient.get(`${BASE}/stores`, {
    params: sanitizeParams(params as Record<string, unknown>),
  })
  return response.data
}

export const fetchFinanceStoresRevenue = async (
  params: FetchStoresRevenueParams,
): Promise<FinanceC1ListEnvelope<FinanceStoreRevenueDTO>> => {
  const response = await plannerClient.get(`${BASE}/stores/revenue`, {
    params: sanitizeParams(params as unknown as Record<string, unknown>),
  })
  return response.data
}

export const fetchFinanceEmployees = async (
  params: FetchEmployeesParams = {},
): Promise<FinanceC1ListEnvelope<FinanceEmployeeDTO>> => {
  const response = await plannerClient.get(`${BASE}/employees`, {
    params: sanitizeParams(params as Record<string, unknown>),
  })
  return response.data
}

export const fetchFinanceFixedCosts = async (
  params: FetchFixedCostsParams,
): Promise<FinanceC1ListEnvelope<FinanceFixedCostDTO>> => {
  const response = await plannerClient.get(`${BASE}/fixed-costs`, {
    params: sanitizeParams(params as unknown as Record<string, unknown>),
  })
  return response.data
}

/** v1.0 兼容: by_department 默认 */
export const fetchFinancePayroll = async (
  params: FetchPayrollParams,
): Promise<FinanceC1ListEnvelope<FinancePayrollDTO>> => {
  const response = await plannerClient.get(`${BASE}/payroll`, {
    params: sanitizeParams(params as unknown as Record<string, unknown>),
  })
  return response.data
}

/** v1.3 §4.5 真实落地: by_employee 每员工每月 1 行 */
export const fetchFinancePayrollByEmployee = async (
  params: Omit<FetchPayrollParams, 'aggregation'>,
): Promise<FinanceC1ListEnvelope<FinancePayrollByEmployeeDTO>> => {
  const response = await plannerClient.get(`${BASE}/payroll`, {
    params: sanitizeParams({
      ...(params as unknown as Record<string, unknown>),
      aggregation: 'by_employee',
    }),
  })
  return response.data
}

export const fetchFinancePaymentRequests = async (
  params: FetchPaymentRequestsParams = {},
): Promise<FinanceC1ListEnvelope<FinancePaymentRequestDTO>> => {
  const response = await plannerClient.get(`${BASE}/payment-requests`, {
    params: sanitizeParams(params as unknown as Record<string, unknown>),
  })
  return response.data
}
