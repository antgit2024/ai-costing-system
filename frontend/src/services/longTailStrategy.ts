import type {
  CostRateType,
  LongTailCogsRateResolvePreviewPayload,
  LongTailCogsRateResolvePreviewResponse,
  LongTailCogsRateStrategy,
  LongTailCogsRateStrategyListResponse,
  LongTailCogsRateStrategyUpsertPayload,
} from '../types/planner'
import { plannerClient } from './planner'

const BASE = '/long-tail-strategies'

export const fetchLongTailStrategies = async (
  params: { include_archived?: boolean; rate_type?: CostRateType | 'all' } = {},
): Promise<LongTailCogsRateStrategyListResponse> => {
  const response = await plannerClient.get(BASE, { params })
  return response.data
}

export const createLongTailStrategy = async (
  payload: LongTailCogsRateStrategyUpsertPayload,
): Promise<LongTailCogsRateStrategy> => {
  const response = await plannerClient.post(BASE, payload)
  return response.data
}

export const patchLongTailStrategy = async (
  strategyId: string,
  payload: LongTailCogsRateStrategyUpsertPayload,
): Promise<LongTailCogsRateStrategy> => {
  const response = await plannerClient.patch(`${BASE}/${strategyId}`, payload)
  return response.data
}

export const deleteLongTailStrategy = async (
  strategyId: string,
  actor?: string,
): Promise<void> => {
  await plannerClient.delete(`${BASE}/${strategyId}`, {
    params: actor ? { actor } : undefined,
  })
}

export const previewLongTailRateForSku = async (
  payload: LongTailCogsRateResolvePreviewPayload,
): Promise<LongTailCogsRateResolvePreviewResponse> => {
  const response = await plannerClient.post(`${BASE}/resolve-preview`, payload)
  return response.data
}
