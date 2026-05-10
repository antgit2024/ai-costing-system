/**
 * Cost center / Path A §A1~A4 fetchers — calls `/api/planner/cost-centers/*`,
 * `/api/planner/fixed-costs/*`, `/api/planner/cost-allocation/*`.
 *
 * Auth: shares `plannerClient` interceptors (staff JWT or admin key).
 */

import type {
  CostAllocationLine,
  CostAllocationRunResponse,
  CostCenter,
  CostCenterAggregatePayrollResponse,
  CostCenterAssignProcessesResponse,
  CostCenterListResponse,
  CostCenterPayrollSnapshot,
  CostCenterRefreshMappingResponse,
  CostCenterUpsertPayload,
  FixedCostAmortizationLine,
  FixedCostAmortizeResponse,
} from '../types/planner'
import { plannerClient } from './planner'

const CC_BASE = '/cost-centers'
const FC_BASE = '/fixed-costs'
const CA_BASE = '/cost-allocation'

export const fetchCostCenters = async (
  params: { include_inactive?: boolean; with_stats?: boolean } = {},
): Promise<CostCenterListResponse> => {
  const response = await plannerClient.get(CC_BASE, { params })
  return response.data
}

export const fetchCostCenter = async (id: string): Promise<CostCenter> => {
  const response = await plannerClient.get(`${CC_BASE}/${id}`)
  return response.data
}

export const createCostCenter = async (
  payload: CostCenterUpsertPayload,
): Promise<CostCenter> => {
  const response = await plannerClient.post(CC_BASE, payload)
  return response.data
}

export const patchCostCenter = async (
  id: string,
  payload: CostCenterUpsertPayload,
): Promise<CostCenter> => {
  const response = await plannerClient.patch(`${CC_BASE}/${id}`, payload)
  return response.data
}

export const deleteCostCenter = async (id: string, actor?: string): Promise<void> => {
  await plannerClient.delete(`${CC_BASE}/${id}`, {
    params: actor ? { actor } : undefined,
  })
}

export const assignProcessesToCostCenter = async (
  id: string,
  process_ids: string[],
  actor?: string,
): Promise<CostCenterAssignProcessesResponse> => {
  const response = await plannerClient.post(`${CC_BASE}/${id}/assign-processes`, {
    process_ids,
    actor,
  })
  return response.data
}

export const refreshFinanceDepartmentMapping = async (
  actor?: string,
): Promise<CostCenterRefreshMappingResponse> => {
  const response = await plannerClient.post(`${CC_BASE}/refresh-finance-mapping`, null, {
    params: actor ? { actor } : undefined,
  })
  return response.data
}

// ---------------------------------------------------------------------------
// A2 payroll aggregator
// ---------------------------------------------------------------------------

export const aggregatePayrollForCostCenter = async (
  id: string,
  period: string,
): Promise<CostCenterAggregatePayrollResponse> => {
  const response = await plannerClient.post(
    `${CC_BASE}/${id}/aggregate-payroll`,
    null,
    { params: { period } },
  )
  return response.data
}

export const aggregatePayrollBatch = async (
  period: string,
): Promise<CostCenterAggregatePayrollResponse> => {
  const response = await plannerClient.post(
    `${CC_BASE}/aggregate-payroll-batch`,
    null,
    { params: { period } },
  )
  return response.data
}

export const fetchPayrollSnapshots = async (
  cost_center_id: string,
  params: { since?: string; until?: string } = {},
): Promise<CostCenterPayrollSnapshot[]> => {
  const response = await plannerClient.get(
    `${CC_BASE}/${cost_center_id}/payroll-snapshots`,
    { params },
  )
  return response.data
}

export const fetchPayrollSnapshotsForPeriod = async (
  period: string,
): Promise<CostCenterPayrollSnapshot[]> => {
  const response = await plannerClient.get(`${CC_BASE}/payroll-snapshots`, {
    params: { period },
  })
  return response.data
}

// ---------------------------------------------------------------------------
// A3 fixed cost amortizer
// ---------------------------------------------------------------------------

export const runFixedCostAmortization = async (
  period: string,
): Promise<FixedCostAmortizeResponse> => {
  const response = await plannerClient.post(`${FC_BASE}/amortize`, null, {
    params: { period },
  })
  return response.data
}

export const fetchAmortizationLines = async (
  period: string,
  expense_category?: string,
): Promise<FixedCostAmortizationLine[]> => {
  const response = await plannerClient.get(`${FC_BASE}/amortization`, {
    params: { period, ...(expense_category ? { expense_category } : {}) },
  })
  return response.data
}

export const fetchAmortizationByCompany = async (period: string) => {
  const response = await plannerClient.get(`${FC_BASE}/amortization/by-company`, {
    params: { period },
  })
  return response.data as {
    period: string
    items: Array<{
      company_id: string
      total: number
      by_category: Record<string, number>
      company_name?: string | null
    }>
    total: number
  }
}

export const fetchAmortizationByCategory = async (period: string) => {
  const response = await plannerClient.get(`${FC_BASE}/amortization/by-category`, {
    params: { period },
  })
  return response.data as {
    period: string
    items: Array<{
      category: string
      total: number
      line_count: number
      by_company: Record<string, number>
    }>
    total: number
  }
}

// ---------------------------------------------------------------------------
// A4 cost allocator
// ---------------------------------------------------------------------------

export const runCostAllocation = async (
  period: string,
  fallback_mode: 'permissive' | 'strict' = 'permissive',
): Promise<CostAllocationRunResponse> => {
  const response = await plannerClient.post(`${CA_BASE}/run`, null, {
    params: { period, fallback_mode },
  })
  return response.data
}

export const fetchAllocationLines = async (
  period: string,
  cost_center_id?: string,
): Promise<CostAllocationLine[]> => {
  const response = await plannerClient.get(`${CA_BASE}/lines`, {
    params: { period, ...(cost_center_id ? { cost_center_id } : {}) },
  })
  return response.data
}

export const fetchAllocationByCostCenter = async (period: string) => {
  const response = await plannerClient.get(`${CA_BASE}/by-cost-center`, {
    params: { period },
  })
  return response.data as {
    period: string
    items: Array<{
      cost_center_id: string
      total: number
      by_category: Record<string, number>
    }>
    total: number
  }
}
