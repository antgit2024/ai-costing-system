import axios from 'axios'
import type {
  ApprovalActionResponse,
  ApprovalApprovePayload,
  ApprovalRejectPayload,
  ApprovalSubmitPayload,
  AuditLogQueryParams,
  BenchmarkFavorite,
  BenchmarkSuggestion,
  BenchmarkSuggestPayload,
  ImportJob,
  Initiative,
  InitiativeQueryParams,
  LineItemQueryParams,
  LineItemUpdatePayload,
  NormalizedLineItem,
  Material,
  MaterialExportResponse,
  MaterialListResponse,
  MaterialQueryParams,
  MaterialStatusUpdatePayload,
  MaterialSyncLogResponse,
  PaginatedAuditLogResponse,
  PaginatedResponse,
  PackageNode,
  PlannerJob,
  ScenarioClonePayload,
  ScenarioCloneResponse,
  ScenarioDiffParams,
  ScenarioDiffResponse,
  ScenarioExportPayload,
  ScenarioExportResponse,
  ScenarioListQueryParams,
  ScenarioListResponse,
} from '@/types/planner'

const API_BASE_URL = import.meta.env.VITE_PLANNER_API_BASE ?? '/api/planner'
const DEFAULT_PLANNER_USER = import.meta.env.VITE_PLANNER_USER_ID ?? 'planner_user'

const mapBenchmarkFavorite = (favorite: any): BenchmarkFavorite => ({
  id: favorite.id,
  suggestion_id: favorite.benchmark_key ?? favorite.suggestion_id,
  scenario_id: favorite.payload?.scenario_id ?? favorite.scenario_id ?? '',
  title: favorite.payload?.title ?? favorite.title,
  notes: favorite.payload?.notes ?? favorite.notes,
  created_at: favorite.created_at,
})

export const plannerClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 20000,
})

export const sanitizeParams = <T extends Record<string, unknown>>(params: T) =>
  Object.entries(params).reduce<Record<string, unknown>>((acc, [key, value]) => {
    if (
      value !== undefined &&
      value !== null &&
      value !== '' &&
      !(typeof value === 'number' && Number.isNaN(value))
    ) {
      acc[key] = value
    }
    return acc
  }, {})

export const normalizeLineItems = (items: NormalizedLineItem[]): NormalizedLineItem[] =>
  items.map((item) => ({
    ...item,
    metadata: item.metadata_json ?? {},
  }))

export const fetchInitiatives = async (params: InitiativeQueryParams = {}): Promise<PaginatedResponse<Initiative>> => {
  const response = await plannerClient.get('/initiatives', {
    params: sanitizeParams(params as Record<string, unknown>),
  })
  return response.data
}

export const fetchInitiativeById = async (id: string): Promise<Initiative> => {
  const response = await plannerClient.get(`/initiatives/${id}`)
  return response.data
}

export const fetchScenarios = async (
  params: ScenarioListQueryParams = {},
): Promise<ScenarioListResponse> => {
  const response = await plannerClient.get('/scenarios', {
    params: sanitizeParams(params as Record<string, unknown>),
  })
  return response.data
}

export const fetchPackageTree = async (initiativeId: string): Promise<PackageNode[]> => {
  const response = await plannerClient.get('/packages/tree', {
    params: sanitizeParams({ initiative_id: initiativeId }),
  })
  return response.data
}

export interface LineItemResponse
  extends Omit<PaginatedResponse<NormalizedLineItem>, 'items'> {
  items: NormalizedLineItem[]
}

export const fetchLineItems = async (params: LineItemQueryParams = {}): Promise<LineItemResponse> => {
  const response = await plannerClient.get('/line-items', {
    params: sanitizeParams(params as Record<string, unknown>),
  })
  return {
    ...response.data,
    items: normalizeLineItems(response.data.items),
  }
}

export const updateLineItem = async (
  lineItemId: string,
  payload: LineItemUpdatePayload,
) => {
  const response = await plannerClient.patch(`/line-items/${lineItemId}`, payload)
  return response.data
}

export interface ImportPayload {
  file: File
  initiativeId: string
  requestedBy: string
}

export const importLineItems = async ({
  file,
  initiativeId,
  requestedBy,
}: ImportPayload): Promise<ImportJob> => {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('initiative_id', initiativeId)
  formData.append('requested_by', requestedBy)

  const response = await plannerClient.post('/line-items/import', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })

  return response.data
}

export const fetchImportJob = async (jobId: string): Promise<ImportJob> => {
  const response = await plannerClient.get(`/line-items/import-jobs/${jobId}`)
  return response.data
}

export const fetchPlannerJob = async (jobId: string): Promise<PlannerJob> => {
  const response = await plannerClient.get(`/jobs/${jobId}`)
  return response.data
}

export const setScenarioFavorite = async (
  scenarioId: string,
  favorite: boolean,
  userId = 'planner-ui',
) => {
  const payload = { user_id: userId }
  if (favorite) {
    const response = await plannerClient.post(`/scenarios/${scenarioId}/favorite`, payload)
    return response.data
  }
  const response = await plannerClient.delete(`/scenarios/${scenarioId}/favorite`, {
    data: payload,
  })
  return response.data
}

export const cloneScenario = async (
  scenarioId: string,
  payload: ScenarioClonePayload,
): Promise<ScenarioCloneResponse> => {
  const response = await plannerClient.post(`/scenarios/${scenarioId}/clone`, payload)
  return response.data
}

export const fetchScenarioDiff = async (
  scenarioId: string,
  params: ScenarioDiffParams,
): Promise<ScenarioDiffResponse> => {
  const response = await plannerClient.get(`/scenarios/${scenarioId}/diff`, {
    params: sanitizeParams(params as Record<string, unknown>),
  })
  return response.data
}

export const exportScenario = async (
  scenarioId: string,
  payload: ScenarioExportPayload,
): Promise<ScenarioExportResponse> => {
  const response = await plannerClient.post(`/scenarios/${scenarioId}/export`, payload)
  return response.data
}

export const fetchBenchmarkSuggestions = async (
  payload: BenchmarkSuggestPayload,
): Promise<BenchmarkSuggestion[]> => {
  const response = await plannerClient.post('/benchmarks/suggest', payload)
  const data = response.data
  if (Array.isArray(data)) {
    return data
  }
  if (Array.isArray(data?.items)) {
    return data.items
  }
  if (Array.isArray(data?.suggestions)) {
    return data.suggestions
  }
  return []
}

export const fetchBenchmarkFavorites = async (): Promise<BenchmarkFavorite[]> => {
  const response = await plannerClient.get('/benchmarks/favorites', {
    params: { user_id: DEFAULT_PLANNER_USER },
  })
  const data = response.data
  if (Array.isArray(data)) {
    return data.map(mapBenchmarkFavorite)
  }
  if (Array.isArray(data?.items)) {
    return data.items.map(mapBenchmarkFavorite)
  }
  return []
}

export const saveBenchmarkFavorite = async (payload: {
  suggestion_id: string
  scenario_id: string
  notes?: string
}) => {
  const response = await plannerClient.post('/benchmarks/favorites', {
    benchmark_key: payload.suggestion_id,
    user_id: DEFAULT_PLANNER_USER,
    payload: {
      scenario_id: payload.scenario_id,
      notes: payload.notes,
    },
  })
  return mapBenchmarkFavorite(response.data)
}

export const removeBenchmarkFavorite = async (favoriteId: string) => {
  await plannerClient.delete(`/benchmarks/favorites/${favoriteId}`, {
    params: { user_id: DEFAULT_PLANNER_USER },
  })
}

export const fetchAuditLogs = async (
  params: AuditLogQueryParams,
): Promise<PaginatedAuditLogResponse> => {
  const response = await plannerClient.get('/audit', {
    params: sanitizeParams(params as Record<string, unknown>),
  })
  const data = response.data
  if (Array.isArray(data)) {
    return {
      items: data,
      total: data.length,
      page: 1,
      page_size: data.length,
    }
  }
  if (data?.items) {
    return {
      items: data.items,
      total: data.total ?? data.items.length,
      page: data.page ?? params.page ?? 1,
      page_size: data.page_size ?? params.page_size ?? data.items.length,
    }
  }
  return {
    items: [],
    total: 0,
    page: params.page ?? 1,
    page_size: params.page_size ?? 20,
  }
}

export const fetchMaterials = async (
  params: MaterialQueryParams = {},
): Promise<MaterialListResponse> => {
  const response = await plannerClient.get('/base-config/materials', {
    params: sanitizeParams(params as Record<string, unknown>),
  })
  return response.data
}

export const updateMaterialStatus = async (
  materialId: string,
  payload: MaterialStatusUpdatePayload,
): Promise<Material> => {
  const response = await plannerClient.patch(`/base-config/materials/${materialId}`, payload)
  return response.data
}

export const exportMaterials = async (
  params: MaterialQueryParams = {},
): Promise<MaterialExportResponse> => {
  const response = await plannerClient.post('/base-config/materials/export', params)
  return response.data
}

export interface MaterialSyncRequest {
  limit?: number
  dry_run?: boolean
  config_path?: string
  dump_path?: string
}

export const triggerMaterialSync = async (payload: MaterialSyncRequest = {}) => {
  const response = await plannerClient.post('/base-config/materials/sync-yida', payload)
  return response.data
}

export const fetchMaterialSyncLogs = async (
  params: MaterialQueryParams = {},
): Promise<MaterialSyncLogResponse> => {
  const response = await plannerClient.get('/base-config/materials/sync-jobs', {
    params: sanitizeParams(params as Record<string, unknown>),
  })
  return response.data
}

const postApproval = async <T extends ApprovalSubmitPayload>(
  path: string,
  payload: T,
): Promise<ApprovalActionResponse> => {
  const response = await plannerClient.post(path, payload)
  return response.data
}

export const submitScenarioForApproval = (payload: ApprovalSubmitPayload) =>
  postApproval('/approvals/submit', payload)

export const approveScenario = (payload: ApprovalApprovePayload) =>
  postApproval('/approvals/approve', payload)

export const rejectScenario = (payload: ApprovalRejectPayload) =>
  postApproval('/approvals/reject', payload)

