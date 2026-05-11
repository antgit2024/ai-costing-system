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

// ----------------------------------------------------------------------------
// v1.4 制造费按模型设置 — GET resolve（4 层 hub） + POST upsert（一键覆盖）
//   配套后端：long_tail_strategies.py 末尾两个 endpoint
//   用户原话："制造费一定要指定模型，不能通用"
// ----------------------------------------------------------------------------

export interface OverheadResolveParams {
  model_id?: string | null
  category?: string | null
  cost_center_id?: string | null
}

/** GET 包装 — 让 useQuery 可按 model_id 缓存。返回 4 层 hub 命中详情。 */
export const resolveOverheadForModel = async (
  params: OverheadResolveParams,
): Promise<LongTailCogsRateResolvePreviewResponse> => {
  const response = await plannerClient.get(`${BASE}/resolve/overhead`, {
    params: {
      model_id: params.model_id || undefined,
      category: params.category || undefined,
      cost_center_id: params.cost_center_id || undefined,
    },
  })
  return response.data
}

export interface UpsertModelOverheadPayload {
  model_id: string
  rate: number
  note?: string
  actor?: string
}

/** POST upsert — 内部自动处理「新建 / 更新 / 复活 archived」三种情况。 */
export const upsertModelOverhead = async (
  payload: UpsertModelOverheadPayload,
): Promise<LongTailCogsRateStrategy> => {
  const response = await plannerClient.post(`${BASE}/upsert/model-overhead`, payload)
  return response.data
}
