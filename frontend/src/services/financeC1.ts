/**
 * Finance C1 fetchers(派单 §2.8)— 走后端 `/api/planner/finance/*` 代理。
 *
 * 不直接访问 finance-analyzer · 见契约 §6.1 鉴权统一在后端。所有 fetcher 共用
 * `plannerClient`(已含 baseURL + auth interceptors)。
 */

import { plannerClient, sanitizeParams } from './planner'
import type {
  FinanceC1ListEnvelope,
  FinanceCompanyDTO,
  FinanceEmployeeDTO,
  FinanceFixedCostDTO,
  FinancePayrollDTO,
  FinanceStoreDTO,
} from '../types/financeC1'

const BASE = '/finance'

export interface FetchCompaniesParams {
  entity_role?: 'factory' | 'shop' | 'holding' | 'mixed'
  is_active?: boolean
}

export interface FetchStoresParams {
  company_id?: string
  platform?: string
  is_active?: boolean
}

export interface FetchEmployeesParams {
  contract_company_id?: string
  is_active?: boolean
}

export interface FetchFixedCostsParams {
  period_year: number
  period_month: number
  cost_category?: string
  company_id?: string
}

export interface FetchPayrollParams {
  company_id: string
  period_year: number
  period_month: number
  aggregation?: 'by_department' | 'by_employee'
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

export const fetchFinancePayroll = async (
  params: FetchPayrollParams,
): Promise<FinanceC1ListEnvelope<FinancePayrollDTO>> => {
  const response = await plannerClient.get(`${BASE}/payroll`, {
    params: sanitizeParams(params as unknown as Record<string, unknown>),
  })
  return response.data
}
