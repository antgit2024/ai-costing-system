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
  MaterialReferencesResponse,
  PaginatedAuditLogResponse,
  PaginatedResponse,
  PackageNode,
  PlannerJob,
  ProcessBatchStatusPayload,
  ProcessCopyPayload,
  ProcessCreatePayload,
  ProcessDetail,
  ProcessListResponse,
  ProcessModuleCopyPayload,
  ProcessModuleCreatePayload,
  ProcessModuleDetail,
  ProcessModuleListResponse,
  ProcessModuleQueryParams,
  ProcessModuleReferenceQuery,
  ProcessModuleReferenceResponse,
  ProcessModuleUpdatePayload,
  ProcessQueryParams,
  ProcessReference,
  ProcessUpdatePayload,
  ProductModel,
  ProductModelCreatePayload,
  ProductModelListResponse,
  ProductModelPlaceholder,
  ProductModelQueryParams,
  ProductModelLinesResponse,
  ProductModelLinesUpdateRequest,
  ProductModelPreviewRequest,
  ProductModelPreviewResponse,
  ProductModelSkuPreviewRequest,
  ProductModelSkuPreviewResponse,
  DeriveStandardRequest,
  DeriveStandardResponse,
  CloneModelFromVersionRequest,
  CloneModelFromVersionResponse,
  ProductModelSyncFromModulesRequest,
  ProductModelUpdatePayload,
  ProductModelVersionCreatePayload,
  ProductModelVersionPublishPayload,
  ProductModelVersionRead,
  ModelVersionImagesResponse,
  RandomCodeGenerateRequest,
  RandomCodeGenerateResponse,
  ModelVariantRuleRead,
  ModelVariantRuleCreatePayload,
  ModelVariantRuleUpdatePayload,
  ScenarioClonePayload,
  ScenarioCloneResponse,
  ScenarioDiffParams,
  ScenarioDiffResponse,
  ScenarioExportPayload,
  ScenarioExportResponse,
  ScenarioListQueryParams,
  ScenarioListResponse,
  VirtualMaterial,
  VirtualMaterialBindingRequest,
  VirtualMaterialCreatePayload,
  VirtualMaterialInventoryRequest,
  VirtualMaterialInventoryResponse,
  VirtualMaterialListResponse,
  VirtualMaterialQueryParams,
  VirtualMaterialReference,
  VirtualMaterialUpdatePayload,
  CodeGenerateRequest,
  CodeGenerateResponse,
  SkuModelVersionMappingCreatePayload,
  SkuModelVersionMappingRead,
  PaginatedProductModelVersionResponse,
  SkuMasterUnbindResponse,
  SkuMasterGeneratePreparseAndSnapshotsResponse,
  SpecParseRequest,
  SpecParseResponse,
  LineVariantCreateRequest,
  LineVariantDetailRead,
  LineVariantItemsReplaceRequest,
  LineVariantUpdateRequest,
  BomGenerateRequest,
  BomGenerateResponse,
  BomSnapshot,
  ShipmentCostingResult,
  ShipmentInventoryDeductionLine,
  ShipmentProcessCostLine,
  ShipmentException,
  ShipmentExceptionRetryRequest,
  ShipmentExceptionRetryResponse,
  ShipmentImportBatchListResponse,
  ShipmentImportBatch,
  ReturnsRateBySkuResponse,
  ReturnsRateByChannelResponse,
  ProfitBySkuResponse,
  ProfitByChannelResponse,
  ProfitByModelResponse,
  ModelInsightsSummaryResponse,
  ModelInsightsDetailResponse,
  ModelUsageMaterialSummaryResponse,
  ModelUsageProcessSummaryResponse,
  SalesLinesResponse,
  SalesProfitDashboardResponse,
  ShipmentProfitLinesResponse,
  ShipmentLineListResponse,
  ShipmentLineComputeSnapshotRequest,
  ShipmentLineComputeSnapshotResponse,
  ShipmentLineClearSnapshotsResponse,
  ShipmentLinesAutoResolveRequest,
  ShipmentLinesAutoResolvePreviewResponse,
  ShipmentLinesAutoResolveExecuteResponse,
  ShipmentLinesRecentStatsResponse,
  AfterSalesImportBatch,
  AfterSalesModelOptionsResponse,
  AfterSalesReasonOptionsResponse,
  AfterSalesDashboardResponse,
  PaginatedAfterSalesLinesResponse,
  ProductModelVersionPatchPayload,
  SkuMaster,
  SkuMasterScanResponse,
  SkuMasterImportResponse,
  SkuMasterListResponse,
  PublishedStandardModelCandidateListResponse,
  SkuMasterBindByModelResponse,
  SkuMasterBindPreviewResponse,
  SkuMasterBindPreviewBulkResponse,
  SkuMasterAutoBindPreviewResponse,
  SkuMasterAutoBindExecuteResponse,
  RecognitionKeywordsValidateResponse,
  TaxonomyScopeOptionsResponse,
  TaxonomyItemListResponse,
  TaxonomyItemRead,
  TaxonomyMappingListResponse,
  TaxonomyMappingRead,
  PaginatedStructureStandardResponse,
  StructureStandardQueryParams,
  StructureStandardRead,
  ShippingRule,
  ShippingRuleEvaluateRequest,
  ShippingRuleEvaluateResponse,
  ShippingRuleListResponse,
  ShippingRuleUpsertRequest,
} from '@/types/planner'

const resolvePlannerApiBase = (raw?: string): string => {
  if (!raw) return '/api/planner'
  // If someone sets API base to same host but a different port (e.g. :8800),
  // browsers will treat it as cross-origin and block unless CORS is configured.
  // In production we rely on nginx to proxy `/api/planner` on the same origin.
  if (typeof window === 'undefined') return raw
  try {
    const url = new URL(raw, window.location.origin)
    // On HTTPS pages, never allow an HTTP API base (will be blocked as Mixed Content).
    // Fall back to same-origin proxy instead.
    if (window.location.protocol === 'https:' && url.protocol === 'http:') {
      return '/api/planner'
    }
    const sameHostAndProto =
      url.hostname === window.location.hostname && url.protocol === window.location.protocol
    const differentPort = url.port !== window.location.port
    if (sameHostAndProto && differentPort) {
      return '/api/planner'
    }
    return raw
  } catch {
    return raw
  }
}

const API_BASE_URL = resolvePlannerApiBase(import.meta.env.VITE_PLANNER_API_BASE)
const DEFAULT_PLANNER_USER = import.meta.env.VITE_PLANNER_USER_ID ?? 'planner_user'
const PLANNER_ADMIN_KEY = import.meta.env.VITE_PLANNER_ADMIN_KEY as string | undefined

const mapBenchmarkFavorite = (favorite: any): BenchmarkFavorite => ({
  id: favorite.id,
  suggestion_id: favorite.benchmark_key ?? favorite.suggestion_id,
  scenario_id: favorite.payload?.scenario_id ?? favorite.scenario_id ?? '',
  title: favorite.payload?.title ?? favorite.title,
  notes: favorite.payload?.notes ?? favorite.notes,
  created_at: favorite.created_at,
})

import { installAuthInterceptors } from '@/utils/http'

export const plannerClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 20000,
})
installAuthInterceptors(plannerClient)

const adminHeaders = (): Record<string, string> => {
  if (!PLANNER_ADMIN_KEY) return {}
  return { 'X-PLANNER-ADMIN-KEY': PLANNER_ADMIN_KEY }
}

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

// -----------------------------
// Taxonomy (admin dictionaries)
// -----------------------------

export const fetchTaxonomyScopeOptions = async (): Promise<TaxonomyScopeOptionsResponse> => {
  const resp = await plannerClient.get('/taxonomy/scope-options')
  return resp.data
}

const normalizeTaxonomyItem = (raw: any): any => {
  // Backend responses currently use `scopes_json` / `metadata_json` (FastAPI by_alias).
  // Normalize to frontend-friendly `scopes` / `metadata` so UI forms work correctly.
  if (!raw || typeof raw !== 'object') return raw
  const scopes = Array.isArray(raw.scopes) ? raw.scopes : Array.isArray(raw.scopes_json) ? raw.scopes_json : []
  const metadata =
    raw.metadata && typeof raw.metadata === 'object'
      ? raw.metadata
      : raw.metadata_json && typeof raw.metadata_json === 'object'
        ? raw.metadata_json
        : {}
  return { ...raw, scopes, metadata }
}

export const fetchTaxonomyItems = async (
  domain: string,
  opts: { include_inactive?: boolean } = {},
): Promise<TaxonomyItemListResponse> => {
  const resp = await plannerClient.get('/taxonomy/items', {
    params: sanitizeParams({ domain, include_inactive: opts.include_inactive }),
  })
  return {
    items: (resp.data?.items ?? []).map(normalizeTaxonomyItem),
  }
}

export const createTaxonomyItem = async (payload: {
  domain: string
  name: string
  scopes: string[]
  is_active?: boolean
  sort_order?: number
  source?: string
  metadata?: Record<string, unknown>
}): Promise<TaxonomyItemRead> => {
  const resp = await plannerClient.post('/taxonomy/items', payload, { headers: adminHeaders() })
  return normalizeTaxonomyItem(resp.data)
}

export const updateTaxonomyItem = async (
  id: string,
  payload: { name?: string; scopes?: string[]; is_active?: boolean; sort_order?: number; metadata?: Record<string, unknown> },
): Promise<TaxonomyItemRead> => {
  const resp = await plannerClient.patch(`/taxonomy/items/${id}`, payload, { headers: adminHeaders() })
  return normalizeTaxonomyItem(resp.data)
}

export const archiveTaxonomyItem = async (id: string): Promise<void> => {
  await plannerClient.delete(`/taxonomy/items/${id}`, { headers: adminHeaders() })
}

export const fetchTaxonomyMappings = async (
  domain: string,
  external_system = 'yida',
): Promise<TaxonomyMappingListResponse> => {
  const resp = await plannerClient.get('/taxonomy/mappings', {
    params: sanitizeParams({ domain, external_system }),
  })
  return resp.data
}

export const createTaxonomyMapping = async (payload: {
  domain: string
  external_system?: string
  external_value: string
  taxonomy_item_id: string
}): Promise<TaxonomyMappingRead> => {
  const resp = await plannerClient.post('/taxonomy/mappings', payload, { headers: adminHeaders() })
  return resp.data
}

export const updateTaxonomyMapping = async (id: string, payload: { taxonomy_item_id: string }): Promise<TaxonomyMappingRead> => {
  const resp = await plannerClient.patch(`/taxonomy/mappings/${id}`, payload, { headers: adminHeaders() })
  return resp.data
}

export const deleteTaxonomyMapping = async (id: string): Promise<void> => {
  await plannerClient.delete(`/taxonomy/mappings/${id}`, { headers: adminHeaders() })
}

// -----------------------------
// Structure Standards (dictionary; backed by taxonomy domain=structure_standard)
// -----------------------------

const STRUCTURE_STANDARD_DOMAIN = 'structure_standard'

const normalizeStructureStandard = (item: any): StructureStandardRead => {
  const code = String(item?.name ?? '').trim()
  const meta = (item?.metadata ?? item?.metadata_json ?? {}) as any
  const displayName = String(meta?.display_name ?? meta?.name ?? '').trim()
  const defsRaw = meta?.slot_defs
  const slot_defs:
    | Array<{ code: string; name_cn?: string; enabled?: boolean; remark?: string; driver_quantity?: string }>
    | undefined = Array.isArray(defsRaw)
    ? defsRaw
        .map((r: any) => ({
          code: String(r?.code ?? '').trim(),
          name_cn: String(r?.name_cn ?? '').trim() || undefined,
          enabled: r?.enabled === false ? false : true,
          remark: String(r?.remark ?? '').trim() || undefined,
          driver_quantity: String(r?.driver_quantity ?? '').trim() || undefined,
        }))
        .filter((r: any) => r.code)
    : undefined

  // Active slots used for process-module slot dropdowns
  const slots =
    slot_defs && slot_defs.length
      ? slot_defs.filter((d) => d.enabled !== false).map((d) => d.code)
      : Array.isArray(meta?.slots)
        ? meta.slots.map((x: any) => String(x ?? '').trim()).filter(Boolean)
        : []

  // Display names (store for all slots, even disabled)
  let slot_display_names: Record<string, string> | undefined = undefined
  if (slot_defs && slot_defs.length) {
    const m: Record<string, string> = {}
    for (const d of slot_defs) {
      if (d.name_cn) m[d.code] = d.name_cn
    }
    slot_display_names = Object.keys(m).length ? m : undefined
  } else {
    const slotDisplayNamesRaw = meta?.slot_display_names
    const raw =
      slotDisplayNamesRaw && typeof slotDisplayNamesRaw === 'object' ? (slotDisplayNamesRaw as Record<string, any>) : undefined
    slot_display_names =
      raw && Object.keys(raw).length
        ? Object.fromEntries(Object.entries(raw).map(([k, v]) => [String(k ?? '').trim(), String(v ?? '').trim()]).filter(([k]) => k))
        : undefined
  }
  return {
    id: String(item?.id ?? ''),
    code,
    name: displayName || code,
    slots,
    slot_display_names,
    slot_defs,
    status: item?.is_active ? 'active' : 'inactive',
    updated_at: item?.updated_at,
  }
}

export const fetchStructureStandards = async (
  params: StructureStandardQueryParams = {},
): Promise<PaginatedStructureStandardResponse> => {
  const page = Number(params.page ?? 1) || 1
  const pageSize = Number(params.page_size ?? 20) || 20
  const search = String(params.search ?? '').trim().toLowerCase()
  const status = String(params.status ?? 'all').trim()

  // Taxonomy list doesn't support search/pagination; do client-side filter (MVP)
  const resp = await fetchTaxonomyItems(STRUCTURE_STANDARD_DOMAIN, { include_inactive: true })
  let items = (resp.items ?? []).map(normalizeStructureStandard)

  if (status === 'active' || status === 'inactive') {
    items = items.filter((x) => x.status === status)
  }
  if (search) {
    items = items.filter((x) => x.code.toLowerCase().includes(search) || x.name.toLowerCase().includes(search))
  }

  // stable sort by code asc
  items = items.slice().sort((a, b) => a.code.localeCompare(b.code))

  const total = items.length
  const start = (page - 1) * pageSize
  const paged = items.slice(start, start + pageSize)
  return { total, page, page_size: pageSize, items: paged }
}

export const createStructureStandard = async (payload: {
  code: string
  name: string
  slots: string[]
  slot_display_names?: Record<string, string>
  slot_defs?: Array<{ code: string; name_cn?: string; enabled?: boolean; remark?: string; driver_quantity?: string }>
  status?: 'active' | 'inactive'
}): Promise<StructureStandardRead> => {
  const code = String(payload.code ?? '').trim()
  const name = String(payload.name ?? '').trim()
  const slots = Array.isArray(payload.slots) ? payload.slots.map((x) => String(x ?? '').trim()).filter(Boolean) : []
  const slotDisplayNames =
    payload.slot_display_names && typeof payload.slot_display_names === 'object' ? payload.slot_display_names : undefined
  const slotDefs = Array.isArray(payload.slot_defs) ? payload.slot_defs : undefined
  const isActive = (payload.status ?? 'active') === 'active'

  const created = await createTaxonomyItem({
    domain: STRUCTURE_STANDARD_DOMAIN,
    name: code,
    scopes: ['*'],
    is_active: isActive,
    source: 'local',
    metadata: {
      display_name: name,
      slots,
      ...(slotDisplayNames ? { slot_display_names: slotDisplayNames } : {}),
      ...(slotDefs ? { slot_defs: slotDefs } : {}),
    },
  })
  return normalizeStructureStandard(created)
}

export const updateStructureStandard = async (
  id: string,
  payload: {
    name?: string
    slots?: string[]
    slot_display_names?: Record<string, string>
    slot_defs?: Array<{ code: string; name_cn?: string; enabled?: boolean; remark?: string; driver_quantity?: string }>
    status?: 'active' | 'inactive'
  },
): Promise<StructureStandardRead> => {
  const next: any = {}
  if (payload.status) next.is_active = payload.status === 'active'
  if (
    payload.name !== undefined ||
    payload.slots !== undefined ||
    payload.slot_display_names !== undefined ||
    payload.slot_defs !== undefined
  ) {
    const name = payload.name !== undefined ? String(payload.name ?? '').trim() : undefined
    const slots = payload.slots !== undefined ? payload.slots.map((x) => String(x ?? '').trim()).filter(Boolean) : undefined
    const slotDisplayNames =
      payload.slot_display_names !== undefined && payload.slot_display_names
        ? (payload.slot_display_names as Record<string, string>)
        : undefined
    const slotDefs = payload.slot_defs !== undefined && Array.isArray(payload.slot_defs) ? payload.slot_defs : undefined
    next.metadata = {
      ...(name !== undefined ? { display_name: name } : {}),
      ...(slots !== undefined ? { slots } : {}),
      ...(slotDisplayNames !== undefined ? { slot_display_names: slotDisplayNames } : {}),
      ...(slotDefs !== undefined ? { slot_defs: slotDefs } : {}),
    }
  }
  const updated = await updateTaxonomyItem(id, next)
  return normalizeStructureStandard(updated)
}

export const activateStructureStandard = async (id: string): Promise<StructureStandardRead> => {
  const updated = await updateTaxonomyItem(id, { is_active: true })
  return normalizeStructureStandard(updated)
}

export const deactivateStructureStandard = async (id: string): Promise<StructureStandardRead> => {
  const updated = await updateTaxonomyItem(id, { is_active: false })
  return normalizeStructureStandard(updated)
}

export const deleteStructureStandard = async (id: string): Promise<void> => {
  // Taxonomy deletion is implemented as DELETE /taxonomy/items/{id}.
  // Treat as "archive/delete" for structure standards (dictionary entries).
  await archiveTaxonomyItem(id)
}

// Danger: rename code (taxonomy.name). This may break references that store structure_standard_code as a plain string.
// Only use when you are sure downstream references have been migrated/are unused.
export const renameStructureStandardCode = async (id: string, nextCode: string): Promise<StructureStandardRead> => {
  const name = String(nextCode ?? '').trim()
  if (!name) throw new Error('code 不能为空')
  const updated = await updateTaxonomyItem(id, { name })
  return normalizeStructureStandard(updated)
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

export interface TaskCenterItem {
  id: string
  source: 'planner' | 'material' | string
  job_type: string
  status: string
  requested_by: string
  title: string
  created_at: string
  updated_at: string
  started_at?: string | null
  finished_at?: string | null
  progress_current?: number | null
  progress_total?: number | null
  payload?: Record<string, unknown>
  result?: Record<string, unknown>
  error_message?: string | null
}

export interface TaskCenterListResponse {
  items: TaskCenterItem[]
}

export const fetchTaskCenter = async (params: { limit?: number } = {}): Promise<TaskCenterListResponse> => {
  const response = await plannerClient.get('/task-center/recent', { params: sanitizeParams(params as any) })
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
  opts?: { signal?: AbortSignal },
): Promise<MaterialListResponse> => {
  const response = await plannerClient.get('/base-config/materials', {
    params: sanitizeParams(params as Record<string, unknown>),
    signal: opts?.signal,
  })
  return response.data
}

export const fetchShippingRules = async (params: {
  search?: string
  is_active?: boolean
  page?: number
  page_size?: number
}): Promise<ShippingRuleListResponse> => {
  const response = await plannerClient.get('/shipping-rules', { params: sanitizeParams(params as any) })
  return response.data
}

export const createShippingRule = async (payload: ShippingRuleUpsertRequest): Promise<ShippingRule> => {
  const response = await plannerClient.post('/shipping-rules', payload)
  return response.data
}

export const updateShippingRule = async (ruleId: string, payload: ShippingRuleUpsertRequest): Promise<ShippingRule> => {
  const response = await plannerClient.patch(`/shipping-rules/${ruleId}`, payload)
  return response.data
}

export const archiveShippingRule = async (ruleId: string): Promise<{ ok: boolean }> => {
  const response = await plannerClient.post(`/shipping-rules/${ruleId}/archive`)
  return response.data
}

export const evaluateShippingRules = async (
  payload: ShippingRuleEvaluateRequest,
): Promise<ShippingRuleEvaluateResponse> => {
  const response = await plannerClient.post('/shipping-rules/evaluate', payload)
  return response.data
}

export const fetchMaterial = async (materialId: string): Promise<Material> => {
  const response = await plannerClient.get(`/base-config/materials/${materialId}`)
  return response.data
}

export const updateMaterial = async (
  materialId: string,
  payload: MaterialStatusUpdatePayload,
): Promise<Material> => {
  const response = await plannerClient.patch(`/base-config/materials/${materialId}`, payload)
  return response.data
}

export const updateMaterialStatus = updateMaterial

export const exportMaterials = async (
  params: MaterialQueryParams = {},
): Promise<MaterialExportResponse> => {
  const response = await plannerClient.post('/base-config/materials/export', params)
  return response.data
}

export interface MaterialSyncRequest {
  requested_by?: string
  limit?: number
  dry_run?: boolean
  config_path?: string
  dump_path?: string
  material_codes?: string[]
  mode?: 'full' | 'new_only' | 'core_fields'
}

export const triggerMaterialSync = async (payload: MaterialSyncRequest = {}) => {
  const response = await plannerClient.post('/base-config/materials/sync-yida', payload)
  return response.data
}

export interface MaterialBomDeriveRequest {
  requested_by?: string
  limit?: number
  dry_run?: boolean
  material_codes?: string[]
  search?: string
  material_type?: string
  category?: string
  status?: string
  is_bom_material?: boolean
  is_active?: boolean
}

export const triggerMaterialBomDerive = async (payload: MaterialBomDeriveRequest = {}) => {
  const response = await plannerClient.post('/base-config/materials/derive-bom-prices', payload)
  return response.data
}

export const fetchMaterialSyncJob = async (jobId: string): Promise<import('@/types/planner').MaterialSyncJobRead> => {
  const response = await plannerClient.get(`/base-config/materials/sync-jobs/${jobId}`)
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

export const fetchVirtualMaterials = async (
  params: VirtualMaterialQueryParams = {},
): Promise<VirtualMaterialListResponse> => {
  const response = await plannerClient.get('/base-config/virtual-materials', {
    params: sanitizeParams(params as Record<string, unknown>),
  })
  return response.data
}

export const fetchVirtualMaterial = async (virtualMaterialId: string): Promise<VirtualMaterial> => {
  const response = await plannerClient.get(`/base-config/virtual-materials/${virtualMaterialId}`)
  return response.data
}

export const createVirtualMaterial = async (
  payload: VirtualMaterialCreatePayload,
): Promise<VirtualMaterial> => {
  const response = await plannerClient.post('/base-config/virtual-materials', payload)
  return response.data
}

export const updateVirtualMaterial = async (
  virtualMaterialId: string,
  payload: VirtualMaterialUpdatePayload,
): Promise<VirtualMaterial> => {
  const response = await plannerClient.patch(
    `/base-config/virtual-materials/${virtualMaterialId}`,
    payload,
  )
  return response.data
}

export const saveVirtualMaterialBindings = async (
  virtualMaterialId: string,
  payload: VirtualMaterialBindingRequest,
): Promise<VirtualMaterial> => {
  const response = await plannerClient.put(
    `/base-config/virtual-materials/${virtualMaterialId}/bindings`,
    payload,
  )
  return response.data
}

export const deactivateVirtualMaterial = async (virtualMaterialId: string): Promise<VirtualMaterial> => {
  const response = await plannerClient.post(
    `/base-config/virtual-materials/${virtualMaterialId}/deactivate`,
  )
  return response.data
}

export const fetchMaterialVirtualLinks = async (
  materialId: string,
): Promise<VirtualMaterialReference[]> => {
  const response = await plannerClient.get(`/base-config/materials/${materialId}/virtual-links`)
  return response.data
}

export const fetchMaterialReferences = async (materialId: string): Promise<MaterialReferencesResponse> => {
  const response = await plannerClient.get(`/base-config/materials/${materialId}/references`)
  return response.data
}

export const calculateVirtualMaterialInventory = async (
  virtualMaterialId: string,
  payload: VirtualMaterialInventoryRequest,
): Promise<VirtualMaterialInventoryResponse> => {
  const response = await plannerClient.post(
    `/base-config/virtual-materials/${virtualMaterialId}/inventory-breakdown`,
    payload,
  )
  return response.data
}

export const fetchProcessModules = async (
  params: ProcessModuleQueryParams = {},
): Promise<ProcessModuleListResponse> => {
  const response = await plannerClient.get('/process-modules', {
    params: sanitizeParams(params as Record<string, unknown>),
  })
  return response.data
}

export const fetchProcessModule = async (moduleId: string): Promise<ProcessModuleDetail> => {
  const response = await plannerClient.get(`/process-modules/${moduleId}`)
  return response.data
}

export const createProcessModule = async (
  payload: ProcessModuleCreatePayload,
): Promise<ProcessModuleDetail> => {
  const response = await plannerClient.post('/process-modules', payload)
  return response.data
}

export const updateProcessModule = async (
  moduleId: string,
  payload: ProcessModuleUpdatePayload,
): Promise<ProcessModuleDetail> => {
  const response = await plannerClient.patch(`/process-modules/${moduleId}`, payload)
  return response.data
}

export const activateProcessModule = async (moduleId: string): Promise<ProcessModuleDetail> => {
  const response = await plannerClient.post(`/process-modules/${moduleId}/activate`)
  return response.data
}

export const deactivateProcessModule = async (moduleId: string): Promise<ProcessModuleDetail> => {
  const response = await plannerClient.post(`/process-modules/${moduleId}/deactivate`)
  return response.data
}

export const copyProcessModule = async (
  moduleId: string,
  payload: ProcessModuleCopyPayload,
): Promise<ProcessModuleDetail> => {
  const response = await plannerClient.post(`/process-modules/${moduleId}/copy`, payload)
  return response.data
}

export const deleteProcessModule = async (moduleId: string): Promise<void> => {
  await plannerClient.delete(`/process-modules/${moduleId}`)
}

export const fetchProcessModuleReferences = async (
  params: ProcessModuleReferenceQuery = {},
): Promise<ProcessModuleReferenceResponse> => {
  const response = await plannerClient.get('/process-modules/references', {
    params: sanitizeParams(params as Record<string, unknown>),
  })
  return response.data
}

export const fetchProcesses = async (
  params: ProcessQueryParams = {},
): Promise<ProcessListResponse> => {
  const response = await plannerClient.get('/processes', {
    params: sanitizeParams(params as Record<string, unknown>),
  })
  return response.data
}

export const fetchProcess = async (processId: string): Promise<ProcessDetail> => {
  const response = await plannerClient.get(`/processes/${processId}`)
  return response.data
}

export const createProcess = async (payload: ProcessCreatePayload): Promise<ProcessDetail> => {
  const response = await plannerClient.post('/processes', payload)
  return response.data
}

export const updateProcess = async (
  processId: string,
  payload: ProcessUpdatePayload,
): Promise<ProcessDetail> => {
  const response = await plannerClient.patch(`/processes/${processId}`, payload)
  return response.data
}

export const copyProcess = async (
  processId: string,
  payload: ProcessCopyPayload,
): Promise<ProcessDetail> => {
  const response = await plannerClient.post(`/processes/${processId}/copy`, payload)
  return response.data
}

export const activateProcess = async (processId: string): Promise<ProcessDetail> => {
  const response = await plannerClient.post(`/processes/${processId}/activate`)
  return response.data
}

export const deactivateProcess = async (processId: string): Promise<ProcessDetail> => {
  const response = await plannerClient.post(`/processes/${processId}/deactivate`)
  return response.data
}

export const deleteProcess = async (processId: string): Promise<void> => {
  await plannerClient.delete(`/processes/${processId}`)
}

export const batchUpdateProcessStatus = async (
  payload: ProcessBatchStatusPayload,
): Promise<{ updated: number }> => {
  const response = await plannerClient.post('/processes/batch/status', payload)
  return response.data
}

export const fetchProcessReferences = async (
  params: ProcessQueryParams = {},
): Promise<ProcessReference[]> => {
  const response = await plannerClient.get('/processes/references', {
    params: sanitizeParams(params as Record<string, unknown>),
  })
  return response.data
}

export type GenerateProcessModuleDescriptionPayload = {
  module_name: string
  category?: string | null
  structure?: Record<string, any> | null
  materials: Array<Record<string, any>>
  steps: Array<Record<string, any>>
}

export type GenerateProcessModuleDescriptionResponse = {
  description: string
  provider: string
}

export const generateProcessModuleDescription = async (
  payload: GenerateProcessModuleDescriptionPayload,
): Promise<GenerateProcessModuleDescriptionResponse> => {
  const response = await plannerClient.post('/ai/process-modules/describe', payload)
  return response.data
}

export const fetchProductModels = async (
  params: ProductModelQueryParams = {},
): Promise<ProductModelListResponse> => {
  const response = await plannerClient.get('/product-models', {
    params: sanitizeParams(params as Record<string, unknown>),
  })
  return response.data
}

export const fetchProductModel = async (
  modelId: string,
  params: { include_archived?: boolean } = {},
): Promise<ProductModel> => {
  const response = await plannerClient.get(`/product-models/${modelId}`, {
    params: sanitizeParams(params),
  })
  return response.data
}

export const deleteProductModel = async (modelId: string): Promise<void> => {
  await plannerClient.delete(`/product-models/${modelId}`)
}

export const archiveSampleVersionsOnly = async (modelId: string): Promise<void> => {
  await plannerClient.post(`/product-models/${modelId}/archive-sample`)
}

export const archiveStandardVersionsOnly = async (modelId: string): Promise<void> => {
  await plannerClient.post(`/product-models/${modelId}/archive-standard`)
}

export const createProductModel = async (
  payload: ProductModelCreatePayload,
): Promise<ProductModel> => {
  const response = await plannerClient.post('/product-models', payload)
  return response.data
}

export const updateProductModel = async (
  modelId: string,
  payload: ProductModelUpdatePayload,
): Promise<ProductModel> => {
  const response = await plannerClient.patch(`/product-models/${modelId}`, payload)
  return response.data
}

export const activateProductModel = async (modelId: string): Promise<ProductModel> => {
  const response = await plannerClient.post(`/product-models/${modelId}/activate`)
  return response.data
}

export const deactivateProductModel = async (modelId: string): Promise<ProductModel> => {
  const response = await plannerClient.post(`/product-models/${modelId}/deactivate`)
  return response.data
}

export const fetchProductModelPlaceholders = async (
  modelId: string,
): Promise<ProductModelPlaceholder[]> => {
  const response = await plannerClient.get(`/product-models/${modelId}/placeholders`)
  return response.data
}

export const previewProductModel = async (
  modelId: string,
  payload: ProductModelPreviewRequest,
): Promise<ProductModelPreviewResponse> => {
  const response = await plannerClient.post(`/product-models/${modelId}/preview`, payload)
  return response.data
}

export const fetchProductModelVersions = async (
  modelId: string,
  params: { include_archived?: boolean } = {},
): Promise<ProductModelVersionRead[]> => {
  const response = await plannerClient.get(`/product-models/${modelId}/versions`, {
    params: sanitizeParams(params),
  })
  return response.data
}

export const fetchProductModelVersionsPaged = async (
  params: {
    search?: string
    version_kind?: string
    version_status?: string
    structure_standard_code?: string
    page?: number
    page_size?: number
  } = {},
): Promise<PaginatedProductModelVersionResponse> => {
  const response = await plannerClient.get(`/product-model-versions`, {
    params: sanitizeParams(params),
  })
  return response.data
}

export const createProductModelVersion = async (
  modelId: string,
  payload: ProductModelVersionCreatePayload,
): Promise<ProductModelVersionRead> => {
  const response = await plannerClient.post(`/product-models/${modelId}/versions`, payload)
  return response.data
}

export const fetchProductModelVersionLines = async (
  versionId: string,
  params: { include_archived?: boolean } = {},
): Promise<ProductModelLinesResponse> => {
  const response = await plannerClient.get(`/product-model-versions/${versionId}/lines`, {
    params: sanitizeParams(params),
  })
  return response.data
}

export const uploadProductModelVersionImage = async (versionId: string, file: File): Promise<ModelVersionImagesResponse> => {
  const fd = new FormData()
  fd.append('file', file)
  const response = await plannerClient.post(`/product-model-versions/${versionId}/images`, fd, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return response.data
}

export const deleteProductModelVersionImage = async (versionId: string, imageIndex: number): Promise<ModelVersionImagesResponse> => {
  const response = await plannerClient.delete(`/product-model-versions/${versionId}/images/${imageIndex}`)
  return response.data
}

export const updateProductModelVersionLines = async (
  versionId: string,
  payload: ProductModelLinesUpdateRequest,
): Promise<ProductModelLinesResponse> => {
  const response = await plannerClient.put(`/product-model-versions/${versionId}/lines`, payload)
  return response.data
}

export const deleteProductModelVersion = async (versionId: string): Promise<void> => {
  await plannerClient.delete(`/product-model-versions/${versionId}`)
}

export const cloneProductModelFromStandardVersion = async (
  sourceVersionId: string,
  payload: CloneModelFromVersionRequest = {},
): Promise<CloneModelFromVersionResponse> => {
  const response = await plannerClient.post(`/product-model-versions/${sourceVersionId}/clone-model`, payload)
  return response.data
}

export const syncProductModelVersionFromModules = async (
  versionId: string,
  payload: ProductModelSyncFromModulesRequest = {},
): Promise<ProductModelLinesResponse> => {
  const response = await plannerClient.post(`/product-model-versions/${versionId}/sync-from-modules`, payload)
  return response.data
}

export const previewProductModelVersion = async (
  versionId: string,
  payload: ProductModelPreviewRequest,
): Promise<ProductModelPreviewResponse> => {
  const response = await plannerClient.post(`/product-model-versions/${versionId}/preview`, payload)
  return response.data
}

export const publishProductModelVersion = async (
  versionId: string,
  payload: ProductModelVersionPublishPayload = {},
): Promise<ProductModelVersionRead> => {
  const response = await plannerClient.post(`/product-model-versions/${versionId}/publish`, payload)
  return response.data
}

export const patchProductModelVersion = async (
  versionId: string,
  payload: ProductModelVersionPatchPayload,
): Promise<ProductModelVersionRead> => {
  const response = await plannerClient.patch(`/product-model-versions/${versionId}`, payload)
  return response.data
}

export const bindSkuModelVersion = async (
  payload: SkuModelVersionMappingCreatePayload,
): Promise<SkuModelVersionMappingRead> => {
  const response = await plannerClient.post(`/sku-model-version-mapping`, payload)
  return response.data
}

export const fetchSkuModelVersionMappings = async (params: {
  sku_code: string
  include_inactive?: boolean
}): Promise<SkuModelVersionMappingRead[]> => {
  const response = await plannerClient.get(`/sku-model-version-mapping`, {
    params: sanitizeParams(params),
  })
  return response.data
}

export const previewBySku = async (
  payload: ProductModelSkuPreviewRequest,
): Promise<ProductModelSkuPreviewResponse> => {
  const response = await plannerClient.post(`/sku-preview`, payload)
  return response.data
}

export const deriveStandardFromSampleVersion = async (
  sourceVersionId: string,
  payload: DeriveStandardRequest,
): Promise<DeriveStandardResponse> => {
  const response = await plannerClient.post(
    `/product-model-versions/${sourceVersionId}/derive-standard`,
    payload,
  )
  return response.data
}

// --- Line variants (version-scoped) + spec parser + dynamic BOM (MVP) ---

export const parseSpec = async (payload: SpecParseRequest): Promise<SpecParseResponse> => {
  const response = await plannerClient.post(`/spec/parse`, payload)
  return response.data
}

export const listLineVariants = async (params: {
  version_id: string
  base_line_id?: string
}): Promise<LineVariantDetailRead[]> => {
  const response = await plannerClient.get(`/product-model-versions/${params.version_id}/line-variants`, {
    params: sanitizeParams({ base_line_id: params.base_line_id }),
  })
  return response.data
}

export const createLineVariant = async (
  versionId: string,
  payload: LineVariantCreateRequest,
): Promise<LineVariantDetailRead> => {
  const response = await plannerClient.post(`/product-model-versions/${versionId}/line-variants`, payload)
  return response.data
}

export const updateLineVariant = async (
  variantId: string,
  payload: LineVariantUpdateRequest,
): Promise<LineVariantDetailRead> => {
  const response = await plannerClient.patch(`/line-variants/${variantId}`, payload)
  return response.data
}

export const deleteLineVariant = async (variantId: string): Promise<void> => {
  await plannerClient.delete(`/line-variants/${variantId}`)
}

export const replaceLineVariantItems = async (
  variantId: string,
  payload: LineVariantItemsReplaceRequest,
): Promise<LineVariantDetailRead> => {
  const response = await plannerClient.put(`/line-variants/${variantId}/items`, payload)
  return response.data
}

export const generateBom = async (payload: BomGenerateRequest): Promise<BomGenerateResponse> => {
  const response = await plannerClient.post(`/bom/generate`, payload)
  return response.data
}

export type BomBundleComponent = {
  width_mm: number
  height_mm: number
  quantity: number
  spec_text?: string
  tokens?: string[]
  notes?: string
}

export type BomGenerateBundleRequest = {
  model_version_id: string
  sku_code?: string
  components: BomBundleComponent[]
  include_disabled_variants?: boolean
}

export type BomGenerateBundleResponse = {
  merged: BomGenerateResponse
  components: any[]
}

export const generateBomBundle = async (payload: BomGenerateBundleRequest): Promise<BomGenerateBundleResponse> => {
  const response = await plannerClient.post(`/bom/generate-bundle`, payload)
  return response.data
}

export type BomMultiBundleComponent = {
  model_version_id: string
  width_mm: number
  height_mm: number
  quantity: number
  spec_text?: string
  tokens?: string[]
  notes?: string
}

export type BomGenerateMultiBundleRequest = {
  sku_code?: string
  components: BomMultiBundleComponent[]
  include_disabled_variants?: boolean
}

export type BomGenerateMultiBundleResponse = {
  merged: BomGenerateResponse
  components: any[]
}

export const generateBomMultiBundle = async (
  payload: BomGenerateMultiBundleRequest,
): Promise<BomGenerateMultiBundleResponse> => {
  const response = await plannerClient.post(`/bom/generate-multi-bundle`, payload)
  return response.data
}

export type BundleTemplateComponent = {
  model_version_id: string
  width_mm: number
  height_mm: number
  quantity: number
  spec_text?: string
  label?: string
}

export type BundleTemplateCreateRequest = {
  name?: string
  components: BundleTemplateComponent[]
  metadata?: Record<string, any>
  shared_trigger_text?: string
}

export type BundleTemplateRead = {
  id: string
  code: string
  name?: string | null
  components: BundleTemplateComponent[]
  metadata: Record<string, any>
  shared_trigger_text?: string | null
  published_version_id?: string | null
  published_version_label?: string | null
  published_at?: string | null
  is_archived: boolean
  created_at?: string
  updated_at?: string
}

export const createBundleTemplate = async (payload: BundleTemplateCreateRequest): Promise<BundleTemplateRead> => {
  const response = await plannerClient.post(`/bundle-templates`, payload)
  return response.data
}

export const fetchBundleTemplateByCode = async (code: string): Promise<BundleTemplateRead> => {
  const response = await plannerClient.get(`/bundle-templates/by-code/${encodeURIComponent(code)}`)
  return response.data
}

export type PaginatedBundleTemplateResponse = {
  total: number
  page: number
  page_size: number
  items: BundleTemplateRead[]
}

export const fetchBundleTemplates = async (
  params: { search?: string; category?: string; tag?: string; include_archived?: boolean; page?: number; page_size?: number } = {},
): Promise<PaginatedBundleTemplateResponse> => {
  const response = await plannerClient.get(`/bundle-templates`, { params: sanitizeParams(params) })
  return response.data
}

export const fetchBundleTemplate = async (templateId: string): Promise<BundleTemplateRead> => {
  const response = await plannerClient.get(`/bundle-templates/${templateId}`)
  return response.data
}

export const updateBundleTemplate = async (
  templateId: string,
  payload: { name?: string; components?: BundleTemplateComponent[]; metadata?: Record<string, any>; shared_trigger_text?: string },
): Promise<BundleTemplateRead> => {
  const response = await plannerClient.patch(`/bundle-templates/${templateId}`, payload)
  return response.data
}

export const cloneBundleTemplate = async (
  templateId: string,
  payload: { name?: string } = {},
): Promise<BundleTemplateRead> => {
  const response = await plannerClient.post(`/bundle-templates/${templateId}/clone`, payload)
  return response.data
}

export const archiveBundleTemplate = async (templateId: string): Promise<void> => {
  await plannerClient.delete(`/bundle-templates/${templateId}`)
}

export type BundleTemplateVersionRead = {
  id: string
  template_id: string
  template_code: string
  template_name?: string | null
  version_status: string
  version_label?: string | null
  published_at?: string | null
  published_by?: string | null
  components: BundleTemplateComponent[]
  metadata: Record<string, any>
  is_archived: boolean
  created_at?: string
}

export type BundleTemplateVersionsResponse = {
  total: number
  items: BundleTemplateVersionRead[]
}

export const fetchBundleTemplateVersions = async (templateId: string): Promise<BundleTemplateVersionsResponse> => {
  const response = await plannerClient.get(`/bundle-templates/${templateId}/versions`)
  return response.data
}

export const publishBundleTemplate = async (
  templateId: string,
  payload: { operator_id?: string; note?: string } = {},
): Promise<{ version: BundleTemplateVersionRead }> => {
  const response = await plannerClient.post(`/bundle-templates/${templateId}/publish`, payload)
  return response.data
}

export type BomGenerateBySpecRequest = {
  spec_text: string
  sku_code?: string
  include_disabled_variants?: boolean
}

export const generateBomBySpec = async (payload: BomGenerateBySpecRequest): Promise<BomGenerateResponse> => {
  const response = await plannerClient.post(`/bom/generate-by-spec`, payload)
  return response.data
}

// Debug: return per-component details for bundle (components[])
export const generateBomBySpecDebug = async (payload: BomGenerateBySpecRequest): Promise<any> => {
  const response = await plannerClient.post(`/bom/generate-by-spec-debug`, payload)
  return response.data
}

// -----------------------------
// TMALL SKU Template (布艺类) - MVP
// -----------------------------

export type TmallSizeOption = { key: string; label: string; size_code?: string }
export type TmallColorOption = {
  key: string
  label: string
  width_cm?: number | null
  height_cm?: number | null
  thickness_cm?: number | null
  length_cm?: number | null
  main_pattern_type?: string | null
}
export type TmallSkuCell = { color_key: string; size_key: string; enabled: boolean; merchant_sku?: string | null }
export type TmallSkuTemplateRequest = {
  sizes: TmallSizeOption[]
  colors: TmallColorOption[]
  cells: TmallSkuCell[]
  merchant_sku_prefix?: string
  merchant_sku_sep?: string
  merchant_sku_suffix?: string
}
export type TmallSkuRow = {
  color_label: string
  size_label: string
  merchant_sku: string
  sku_status: number
  main_pattern_type?: string | null
  length_cm?: string | null
  thickness_cm?: string | null
  width_cm?: string | null
}
export type TmallSkuTemplatePreviewResponse = {
  total_rows: number
  rows: TmallSkuRow[]
  header_mapping: Record<string, string>
}

export type TmallSkuGeneratorPersistedConfig = {
  merchantSkuPrefix: string
  merchantSkuSuffix: string
  listingChannel?: 'tmall' | 'jd' | 'xhs' | 'douyin'
  sizes: any[]
  colors: any[]
  mainPatternTypes: any[]
  customSalesAttributes?: any[]
  ui?: {
    enableColorImages?: boolean
    enableSizeImages?: boolean
    enableColorRemarks?: boolean
    enableSizeRemarks?: boolean
    enablePatternRemarks?: boolean
    includeMainPatternType?: boolean
  }
}

export type TmallSkuGeneratorTemplate = {
  id: string
  name: string
  type: '家居布艺' | '家居饰品'
  published_at: string | null
  matrix_count: number | null
  archived: boolean
  config: TmallSkuGeneratorPersistedConfig
  created_at: string
  updated_at: string
}

export type TmallSkuGeneratorTemplateListResponse = {
  total: number
  items: TmallSkuGeneratorTemplate[]
}

export const previewTmallSkuTemplate = async (payload: TmallSkuTemplateRequest): Promise<TmallSkuTemplatePreviewResponse> => {
  const resp = await plannerClient.post('/tmall/sku-template/preview', payload)
  return resp.data
}

export const exportTmallSkuTemplateXlsx = async (payload: TmallSkuTemplateRequest): Promise<Blob> => {
  const resp = await plannerClient.post('/tmall/sku-template/export', payload, { responseType: 'blob' })
  return resp.data as Blob
}

export const fetchTmallSkuGeneratorTemplates = async (params: {
  search?: string
  type?: string
  include_archived?: boolean
} = {}): Promise<TmallSkuGeneratorTemplateListResponse> => {
  const resp = await plannerClient.get('/tmall/sku-template/generator-templates', {
    params: sanitizeParams(params as Record<string, unknown>),
  })
  return resp.data
}

export const fetchTmallSkuGeneratorTemplate = async (templateId: string): Promise<TmallSkuGeneratorTemplate> => {
  const resp = await plannerClient.get(`/tmall/sku-template/generator-templates/${encodeURIComponent(templateId)}`)
  return resp.data
}

export const createTmallSkuGeneratorTemplate = async (payload: {
  id: string
  name: string
  type: '家居布艺' | '家居饰品'
  published_at?: string | null
  matrix_count?: number | null
  archived?: boolean
  config: TmallSkuGeneratorPersistedConfig
}): Promise<TmallSkuGeneratorTemplate> => {
  const resp = await plannerClient.post('/tmall/sku-template/generator-templates', payload)
  return resp.data
}

export const upsertTmallSkuGeneratorTemplate = async (
  templateId: string,
  payload: {
    id: string
    name: string
    type: '家居布艺' | '家居饰品'
    published_at?: string | null
    matrix_count?: number | null
    archived?: boolean
    config: TmallSkuGeneratorPersistedConfig
  },
): Promise<TmallSkuGeneratorTemplate> => {
  const resp = await plannerClient.put(`/tmall/sku-template/generator-templates/${encodeURIComponent(templateId)}`, payload)
  return resp.data
}

// -----------------------------
// Report snapshots (nightly precompute + manual refresh)
// -----------------------------

export type ReportSnapshotEnvelope<TData = any> = {
  key: string
  computed_at: string
  params: Record<string, any>
  data: TData
}

export const fetchModelsSummarySnapshot = async (params: { range_days?: number; channel?: string } = {}): Promise<ReportSnapshotEnvelope<any>> => {
  const resp = await plannerClient.get('/reports/insights/models-summary', { params: sanitizeParams(params as any) })
  return resp.data
}

export const refreshModelsSummarySnapshot = async (params: {
  range_days?: number
  channel?: string
  operator_id?: string
} = {}): Promise<{ key: string; computed_at: string; params: Record<string, any> }> => {
  const resp = await plannerClient.post('/reports/insights/models-summary/refresh', null, { params: sanitizeParams(params as any) })
  return resp.data
}

export const fetchSalesProfitDashboardSnapshot = async (params: {
  range_days?: number
  start?: string
  end?: string
  group_by?: 'day' | 'week' | 'month'
  top_n?: number
  channel?: string
} = {}): Promise<ReportSnapshotEnvelope<any>> => {
  const resp = await plannerClient.get('/reports/insights/sales-profit-dashboard', { params: sanitizeParams(params as any) })
  return resp.data
}

export const refreshSalesProfitDashboardSnapshot = async (params: {
  range_days?: number
  start?: string
  end?: string
  group_by?: 'day' | 'week' | 'month'
  top_n?: number
  channel?: string
  operator_id?: string
} = {}): Promise<{ key: string; computed_at: string; params: Record<string, any> }> => {
  const resp = await plannerClient.post('/reports/insights/sales-profit-dashboard/refresh', null, { params: sanitizeParams(params as any) })
  return resp.data
}

export const fetchAfterSalesDashboardSnapshot = async (params: {
  range_days?: number
  start?: string
  end?: string
  group_by?: 'day' | 'week' | 'month'
  view?: 'factory' | 'ops'
  channel?: string
} = {}): Promise<ReportSnapshotEnvelope<any>> => {
  const resp = await plannerClient.get('/reports/insights/after-sales-dashboard', { params: sanitizeParams(params as any) })
  return resp.data
}

export const refreshAfterSalesDashboardSnapshot = async (params: {
  range_days?: number
  start?: string
  end?: string
  group_by?: 'day' | 'week' | 'month'
  view?: 'factory' | 'ops'
  channel?: string
  operator_id?: string
} = {}): Promise<{ key: string; computed_at: string; params: Record<string, any> }> => {
  const resp = await plannerClient.post('/reports/insights/after-sales-dashboard/refresh', null, { params: sanitizeParams(params as any) })
  return resp.data
}

export const fetchProfitByChannelSnapshot = async (params: {
  range_days?: number
  group_by?: 'day' | 'month'
  channel?: string
} = {}): Promise<ReportSnapshotEnvelope<any>> => {
  const resp = await plannerClient.get('/reports/insights/shops/profit-by-channel', { params: sanitizeParams(params as any) })
  return resp.data
}

export const refreshProfitByChannelSnapshot = async (params: {
  range_days?: number
  group_by?: 'day' | 'month'
  channel?: string
  operator_id?: string
} = {}): Promise<{ key: string; computed_at: string; params: Record<string, any> }> => {
  const resp = await plannerClient.post('/reports/insights/shops/profit-by-channel/refresh', null, { params: sanitizeParams(params as any) })
  return resp.data
}

export const fetchReturnsRateByChannelSnapshot = async (params: {
  range_days?: number
  group_by?: 'day' | 'month'
  channel?: string
} = {}): Promise<ReportSnapshotEnvelope<any>> => {
  const resp = await plannerClient.get('/reports/insights/shops/returns-rate-by-channel', { params: sanitizeParams(params as any) })
  return resp.data
}

export const refreshReturnsRateByChannelSnapshot = async (params: {
  range_days?: number
  group_by?: 'day' | 'month'
  channel?: string
  operator_id?: string
} = {}): Promise<{ key: string; computed_at: string; params: Record<string, any> }> => {
  const resp = await plannerClient.post('/reports/insights/shops/returns-rate-by-channel/refresh', null, { params: sanitizeParams(params as any) })
  return resp.data
}

export const fetchShipmentsIssuesSnapshot = async (
  params: { range_days?: number; channel?: string; limit?: number } = {},
  opts: PlannerRequestOptions = {},
): Promise<ReportSnapshotEnvelope<{ total: number; items: any[] }>> => {
  const resp = await plannerClient.get('/reports/shipments/issues', {
    params: sanitizeParams(params as any),
    signal: opts.signal,
    timeout: opts.timeoutMs,
  })
  return resp.data
}

export const refreshShipmentsIssuesSnapshot = async (params: {
  range_days?: number
  channel?: string
  limit?: number
  operator_id?: string
} = {}): Promise<{ key: string; computed_at: string; params: Record<string, any> }> => {
  const resp = await plannerClient.post('/reports/shipments/issues/refresh', null, { params: sanitizeParams(params as any) })
  return resp.data
}

export const fetchProductModelMaterials = async (
  modelId: string,
): Promise<Array<Record<string, any>>> => {
  const response = await plannerClient.get(`/product-models/${modelId}/materials`)
  return response.data
}

export const fetchProductModelVariantRules = async (modelId: string): Promise<ModelVariantRuleRead[]> => {
  const response = await plannerClient.get(`/product-models/${modelId}/variant-rules`)
  return response.data
}

export const createProductModelVariantRule = async (
  modelId: string,
  payload: ModelVariantRuleCreatePayload,
): Promise<ModelVariantRuleRead> => {
  const response = await plannerClient.post(`/product-models/${modelId}/variant-rules`, payload)
  return response.data
}

export const updateProductModelVariantRule = async (
  modelId: string,
  ruleId: string,
  payload: ModelVariantRuleUpdatePayload,
): Promise<ModelVariantRuleRead> => {
  const response = await plannerClient.patch(
    `/product-models/${modelId}/variant-rules/${ruleId}`,
    payload,
  )
  return response.data
}

export const deleteProductModelVariantRule = async (modelId: string, ruleId: string) => {
  await plannerClient.delete(`/product-models/${modelId}/variant-rules/${ruleId}`)
}

export const generateNextCode = async (
  payload: CodeGenerateRequest,
): Promise<CodeGenerateResponse> => {
  const response = await plannerClient.post('/codes/next', payload)
  return response.data
}

export const generateRandomCode = async (
  payload: RandomCodeGenerateRequest,
): Promise<RandomCodeGenerateResponse> => {
  const response = await plannerClient.post('/codes/random', payload)
  return response.data
}

export const syncProductModelFromModules = async (
  modelId: string,
  payload: ProductModelSyncFromModulesRequest = {},
): Promise<ProductModel> => {
  const response = await plannerClient.post(`/product-models/${modelId}/sync-from-modules`, payload)
  return response.data
}

export const refreshProductModelMaterialPrices = async (
  modelId: string,
): Promise<ProductModelLinesResponse> => {
  const response = await plannerClient.post(`/product-models/${modelId}/refresh-material-prices`, {})
  return response.data
}

export const refreshProductModelVersionMaterialPrices = async (
  versionId: string,
): Promise<ProductModelLinesResponse> => {
  const response = await plannerClient.post(`/product-model-versions/${versionId}/refresh-material-prices`, {})
  return response.data
}

export const fetchProductModelLines = async (modelId: string): Promise<ProductModelLinesResponse> => {
  const response = await plannerClient.get(`/product-models/${modelId}/lines`)
  return response.data
}

export const updateProductModelLines = async (
  modelId: string,
  payload: ProductModelLinesUpdateRequest,
): Promise<ProductModel> => {
  const response = await plannerClient.put(`/product-models/${modelId}/lines`, payload)
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

export const fetchShipmentImportBatches = async (
  params: { page?: number; page_size?: number } = {},
): Promise<ShipmentImportBatchListResponse> => {
  const response = await plannerClient.get('/shipments/import-batches', { params: sanitizeParams(params) })
  return response.data
}

// Large XLSX uploads/imports can easily exceed the default axios timeout (20s).
// Give shipments import endpoints a longer timeout to avoid false-negative UI errors.
// Note: execute may take much longer than preview (it writes lines + generates BOM snapshots).
const SHIPMENTS_PREVIEW_TIMEOUT_MS = 5 * 60 * 1000
const SHIPMENTS_EXECUTE_TIMEOUT_MS = 30 * 60 * 1000
const SHIPMENTS_LINES_TIMEOUT_MS = 60 * 1000
const SHIPMENTS_DETAIL_TIMEOUT_MS = 30 * 1000
const AFTER_SALES_IMPORT_TIMEOUT_MS = 10 * 60 * 1000
const ANALYTICS_QUERY_TIMEOUT_MS = 60 * 1000

export const fetchShipmentImportBatch = async (batchId: string): Promise<ShipmentImportBatch> => {
  const resp = await plannerClient.get(`/shipments/import-batches/${batchId}`)
  return resp.data
}

export const fetchShipmentLines = async (
  params: {
    page?: number
    page_size?: number
    start?: string
    end?: string
    batch_id?: string
    status?: 'processed' | 'pending'
    channel?: string
    sku_code?: string
    shipment_no?: string
    order_no?: string
    product_link_id?: string
    spec_text?: string
    bound_target_kind?: 'any' | 'model' | 'bundle'
    bound_model_code?: string
    bound_version_label?: string
    bundle_preset_selector?: string
    unresolved_reason?: string
    suspected_mismatch?: boolean
    include_issue_hints?: boolean
    ready_to_generate?: boolean
    need_rebuild_snapshot?: boolean
  } = {},
  opts: PlannerRequestOptions = {},
): Promise<ShipmentLineListResponse> => {
  try {
    const response = await plannerClient.get('/shipments/lines', {
      params: sanitizeParams(params as any),
      timeout: opts.timeoutMs ?? SHIPMENTS_LINES_TIMEOUT_MS,
      signal: opts.signal,
    })
    return response.data
  } catch (err: any) {
    // Backward-compat: some deployments may not have /shipments/lines yet.
    // Fall back to /analytics/sales/lines which provides similar line-level fields.
    const status = Number(err?.response?.status)
    const detail = String(err?.response?.data?.detail ?? '')
    if (status !== 404 || detail.toLowerCase() !== 'not found') throw err

    const includeMissing = params.status === 'processed' ? false : true
    const resp = await plannerClient.get('/analytics/sales/lines', {
      params: sanitizeParams({
        start: params.start,
        end: params.end,
        page: params.page,
        page_size: params.page_size,
        channel: params.channel,
        sku_code: params.sku_code,
        shipment_no: params.shipment_no,
        order_no: params.order_no,
        product_link_id: params.product_link_id,
        include_missing: includeMissing,
      } as any),
      timeout: opts.timeoutMs ?? SHIPMENTS_LINES_TIMEOUT_MS,
      signal: opts.signal,
    })
    const data = resp.data as any
    const items = (data?.items ?? []).map((r: any) => {
      const hasSnapshot = !!r?.bom_snapshot_id
      const hasCost = r?.cost_amount !== null && r?.cost_amount !== undefined && r?.cost_amount !== ''
      return {
        id: String(r?.shipment_line_id ?? ''),
        batch_id: r?.batch_id ?? null,
        row_index: r?.row_index ?? null,
        shipment_no: r?.shipment_no ?? null,
        order_no: r?.order_no ?? null,
        product_link_id: r?.product_link_id ?? null,
        completed_at: r?.completed_at ?? null,
        channel: r?.channel ?? null,
        sku_code: r?.sku_code ?? null,
        spec_text: r?.spec_text ?? null,
        spec_hash: r?.spec_hash ?? null,
        qty: r?.qty ?? null,
        revenue_amount: r?.revenue_amount ?? null,
        status: hasSnapshot || hasCost ? 'processed' : 'pending',
        processed_source: hasSnapshot ? 'bom_snapshot' : hasCost ? 'costing_result' : null,
        mode: hasSnapshot ? '2026' : null,
        unresolved_reason: null,
        unresolved_message: null,
      }
    })
    return {
      start: data?.start,
      end: data?.end,
      total: Number(data?.total ?? items.length) || 0,
      page: Number(data?.page ?? params.page ?? 1) || 1,
      page_size: Number(data?.page_size ?? params.page_size ?? items.length) || (params.page_size ?? 50),
      items,
      lines_with_bom_snapshots: Number(data?.lines_with_bom_snapshots ?? 0) || 0,
      lines_missing_costing: Number(data?.lines_missing_costing ?? 0) || 0,
      note: 'fallback_to_analytics_sales_lines',
    } as any
  }
}

export const importShipmentsXlsx = async (params: {
  file: File
  export_date?: string
  requested_by?: string
}): Promise<ShipmentImportBatch> => {
  const formData = new FormData()
  formData.append('file', params.file)
  if (params.export_date) formData.append('export_date', params.export_date)
  if (params.requested_by) formData.append('requested_by', params.requested_by)
  const response = await plannerClient.post('/shipments/import', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: SHIPMENTS_EXECUTE_TIMEOUT_MS,
  })
  return response.data
}

export const previewShipmentsXlsx = async (params: {
  file: File
  export_date?: string
  requested_by?: string
}): Promise<{
  preview_id: string
  file_name: string
  export_date?: string | null
  total_rows: number
  ready_rows: number
  missing_sku_rows: number
  missing_spec_rows: number
  unbound_sku_rows: number
  warnings: Array<Record<string, unknown>>
  issues: Array<Record<string, unknown>>
  ready_items: Array<Record<string, unknown>>
}> => {
  const formData = new FormData()
  formData.append('file', params.file)
  if (params.export_date) formData.append('export_date', params.export_date)
  if (params.requested_by) formData.append('requested_by', params.requested_by)
  const response = await plannerClient.post('/shipments/import/preview', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: SHIPMENTS_PREVIEW_TIMEOUT_MS,
  })
  return response.data
}

export const executeShipmentsFromPreview = async (
  payload: {
  preview_id: string
  file_name?: string
  export_date?: string
  requested_by?: string
  mode?: '2025' | '2026'
  process_snapshots?: boolean
  },
  opts: { signal?: AbortSignal; timeoutMs?: number } = {},
): Promise<ShipmentImportBatch> => {
  const response = await plannerClient.post('/shipments/import/execute', payload, {
    timeout: opts.timeoutMs ?? SHIPMENTS_EXECUTE_TIMEOUT_MS,
    signal: opts.signal,
  })
  return response.data
}

export const fetchShipmentExceptions = async (
  params: {
    batch_id?: string
    resolved?: boolean
    limit?: number
    sku_code?: string
    channel?: string
    spec_text?: string
  } = {},
): Promise<ShipmentException[]> => {
  const response = await plannerClient.get('/shipments/exceptions', { params: sanitizeParams(params) })
  return response.data
}

export const retryShipmentExceptions = async (
  payload: ShipmentExceptionRetryRequest,
): Promise<ShipmentExceptionRetryResponse> => {
  const response = await plannerClient.post('/shipments/exceptions/retry', payload)
  return response.data
}

// ---------------------------------------------------------------------------
// SKU Governance (Sprint 2-3 of "SKU 治理与按需建模")
// 4 states: unmanaged | auto_bound | pending_model | do_not_model
// Stored in SkuMaster.metadata_json.governance_status (no Alembic migration).
// ---------------------------------------------------------------------------

export type SkuGovernanceStatus = 'unmanaged' | 'auto_bound' | 'pending_model' | 'do_not_model'

export interface SkuGovernanceSetRequest {
  sku_codes: string[]
  status: SkuGovernanceStatus
  decided_by?: string
  note?: string
}

export interface SkuGovernanceSetResponse {
  updated: number
  unchanged: number
  missing: number
}

export interface SkuGovernanceListItem {
  erp_sku_barcode: string
  spec_text?: string | null
  channel?: string | null
  governance_status: SkuGovernanceStatus
  governance_decided_at?: string | null
  governance_decided_by?: string | null
  governance_note?: string | null
  last_shipment_at?: string | null
  qty_window: number
  revenue_window: number
  line_count_window: number
  updated_at?: string | null
  long_tail_category?: string | null
  long_tail_category_decided_at?: string | null
  long_tail_category_decided_by?: string | null
}

export interface SkuLongTailCategorySetRequest {
  sku_codes: string[]
  category: string | null
  actor?: string
  note?: string
}

export interface SkuLongTailCategorySetResponse {
  updated: number
  unchanged: number
  missing: number
  cleared: number
}

export interface SkuGovernanceListResponse {
  items: SkuGovernanceListItem[]
  total: number
  page: number
  page_size: number
  order_by: string
  sales_window_days: number
}

export interface SkuGovernancePromoteResponse {
  promoted: number
  skipped: number
  missing: number
}

export const setSkuGovernance = async (
  payload: SkuGovernanceSetRequest,
): Promise<SkuGovernanceSetResponse> => {
  const response = await plannerClient.post('/sku-master/governance', payload)
  return response.data
}

export const listSkuGovernance = async (
  params: {
    status: SkuGovernanceStatus
    page?: number
    page_size?: number
    order_by?: 'shipment_score' | 'updated_at' | 'last_shipment_at'
    sales_window_days?: number
  },
): Promise<SkuGovernanceListResponse> => {
  const response = await plannerClient.get('/sku-master/governance', {
    params: sanitizeParams(params),
  })
  return response.data
}

export const promoteSkuGovernanceFromModel = async (
  payload: { sku_codes: string[]; decided_by?: string },
): Promise<SkuGovernancePromoteResponse> => {
  const response = await plannerClient.post('/sku-master/governance/promote-from-model', payload)
  return response.data
}

/** Issue 28 follow-up: bulk write SkuMaster.metadata.long_tail_category.
 * Pass `category: ''` (or null) to clear the override. Backend validates
 * the category exists in the long-tail strategy table. */
export const setSkuLongTailCategory = async (
  payload: SkuLongTailCategorySetRequest,
): Promise<SkuLongTailCategorySetResponse> => {
  const response = await plannerClient.post('/sku-master/long-tail-category', payload)
  return response.data
}

// ===== Auto-suggest long_tail_category (Issue 28 follow-up #2) =====

export interface LongTailCategoryAutoSuggestItem {
  sku_code: string
  current_category?: string | null
  suggested_category: string
  matched_keyword: string
  strategy_id: string
  strategy_rate: number
  spec_text?: string | null
  product_name?: string | null
}

export interface LongTailCategoryAutoSuggestPreviewResponse {
  scanned: number
  already_labeled_skipped: number
  no_match_count: number
  limited: boolean
  suggested: LongTailCategoryAutoSuggestItem[]
  reason?: string | null
}

export interface LongTailCategoryAutoSuggestApplyResultItem {
  category: string
  sku_count: number
  updated?: number
  unchanged?: number
  missing?: number
  cleared?: number
  error?: string | null
}

export interface LongTailCategoryAutoSuggestExecuteResponse
  extends LongTailCategoryAutoSuggestPreviewResponse {
  applied: number
  apply_results: LongTailCategoryAutoSuggestApplyResultItem[]
}

export interface LongTailCategoryAutoSuggestRequest {
  sku_codes?: string[]
  include_already_labeled?: boolean
  limit?: number
  actor?: string
}

export const autoSuggestLongTailCategoryPreview = async (
  payload: LongTailCategoryAutoSuggestRequest = {},
): Promise<LongTailCategoryAutoSuggestPreviewResponse> => {
  const response = await plannerClient.post(
    '/sku-master/long-tail-category/auto-suggest/preview',
    payload,
    { timeout: 60_000 },
  )
  return response.data
}

export const autoSuggestLongTailCategoryExecute = async (
  payload: LongTailCategoryAutoSuggestRequest = {},
): Promise<LongTailCategoryAutoSuggestExecuteResponse> => {
  const response = await plannerClient.post(
    '/sku-master/long-tail-category/auto-suggest/execute',
    payload,
    { timeout: 120_000 },
  )
  return response.data
}

export const fetchShipmentBomSnapshots = async (
  params: {
    batch_id?: string
    sku_code?: string
    shipment_no?: string
    spec_hash?: string
    limit?: number
  } = {},
): Promise<BomSnapshot[]> => {
  const response = await plannerClient.get('/shipments/bom-snapshots', { params: sanitizeParams(params) })
  return response.data
}

export const fetchShipmentBomSnapshotDetail = async (
  snapshot_id: string,
  opts: PlannerRequestOptions = {},
): Promise<BomSnapshot> => {
  const id = String(snapshot_id || '').trim()
  const response = await plannerClient.get(`/shipments/bom-snapshots/${encodeURIComponent(id)}`, {
    timeout: opts.timeoutMs ?? SHIPMENTS_DETAIL_TIMEOUT_MS,
    signal: opts.signal,
  })
  return response.data
}

export const fetchShipmentLineCosting = async (
  shipment_line_id: string,
  opts: PlannerRequestOptions = {},
): Promise<ShipmentCostingResult> => {
  const id = String(shipment_line_id || '').trim()
  const response = await plannerClient.get(`/shipments/lines/${encodeURIComponent(id)}/costing`, {
    timeout: opts.timeoutMs ?? SHIPMENTS_DETAIL_TIMEOUT_MS,
    signal: opts.signal,
  })
  return response.data
}

export const fetchShipmentLineDeductions = async (
  shipment_line_id: string,
  opts: PlannerRequestOptions = {},
): Promise<ShipmentInventoryDeductionLine[]> => {
  const id = String(shipment_line_id || '').trim()
  const response = await plannerClient.get(`/shipments/lines/${encodeURIComponent(id)}/deductions`, {
    timeout: opts.timeoutMs ?? SHIPMENTS_DETAIL_TIMEOUT_MS,
    signal: opts.signal,
  })
  return response.data
}

export const fetchShipmentLineProcesses = async (
  shipment_line_id: string,
  opts: PlannerRequestOptions = {},
): Promise<ShipmentProcessCostLine[]> => {
  const id = String(shipment_line_id || '').trim()
  const response = await plannerClient.get(`/shipments/lines/${encodeURIComponent(id)}/processes`, {
    timeout: opts.timeoutMs ?? SHIPMENTS_DETAIL_TIMEOUT_MS,
    signal: opts.signal,
  })
  return response.data
}

export const fetchShipmentProfitLines = async (params: {
  batch_id: string
  limit?: number
  include_missing?: boolean
}): Promise<ShipmentProfitLinesResponse> => {
  const resp = await plannerClient.get('/shipments/profit-lines', { params: sanitizeParams(params as any) })
  return resp.data
}

export const recomputeShipmentBomSnapshot = async (snapshot_id: string, payload?: { operator_id?: string }): Promise<BomSnapshot> => {
  const response = await plannerClient.post(`/shipments/bom-snapshots/${snapshot_id}/recompute`, payload ?? {})
  return response.data
}

// ============================================================================
// Shipment Line Resolve - 上架员一键决策
// ============================================================================
//
// 业务诉求: 上架员在「📦 业务管理 > 🚚 发货管理」对每条未处理的发货行
// 做"一键决策",系统应该一步把所有事情做完(绑模型 + 设治理 + 出快照),
// 不要让员工跨页面操作。
//
// Issue 29 (2026-05-07): 后端 POST /shipments/lines/{id}/resolve 上线后,
// 这个函数内部从"前端串 4 个 API"改成"单次 POST"。所有调用方 0 改动 ——
// 函数签名 / ShipmentLineResolveAction / ShipmentLineResolveResult 都不变。
//
// 收益:
//   - adopt 从 4 次串行 RTT (~1.5-2s) 降到 1 次 (~250ms)
//   - 后端单事务执行, 不再有"绑了但快照没出"的中间态
//   - 失败时返回的 steps 还在原位置, 不影响错误展示
// ============================================================================

export type ShipmentLineResolveAction =
  | { type: 'adopt'; modelId: string } // 用某个模型(从弹窗选完后)
  | { type: 'mark_long_tail' } // 标长尾不建模
  | { type: 'defer_modeling' } // 加入建模 backlog(等模型建好)

export type ShipmentLineResolveResult = {
  ok: boolean
  snapshot?: BomSnapshot
  error?: string
  /** 为审计 / debug 保留的执行细节 */
  steps: Array<{ step: string; ok: boolean; durationMs?: number; detail?: string }>
}

interface ShipmentLineResolveBackendStep {
  step: string
  ok: boolean
  duration_ms?: number
  detail?: string | null
}

interface ShipmentLineResolveBackendResponse {
  ok: boolean
  action: string
  shipment_line_id: string
  snapshot_id?: string | null
  snapshot_action?: string | null
  error?: string | null
  steps: ShipmentLineResolveBackendStep[]
}

/**
 * 一键决策: 单次 POST /shipments/lines/{id}/resolve, 后端单事务完成。
 *
 * 失败处理:
 *   - 后端返回 ok=false 时, error / steps 都会带上下文。
 *   - 网络层失败 (超时 / 4xx / 5xx) 由 catch 兜底, steps 用一条
 *     'http_request' 占位, 保持原 UI 兼容。
 *
 * 性能预算 (2026-05-07 上线后):
 *   - adopt: ~250ms (单次 POST, 含 bind + governance + snapshot)
 *   - mark_long_tail / defer_modeling: ~80ms
 */
export const resolveShipmentLine = async (
  line: { id: string; sku_code?: string | null },
  action: ShipmentLineResolveAction,
  opts: { operatorId?: string } = {},
): Promise<ShipmentLineResolveResult> => {
  const skuCode = String(line?.sku_code ?? '').trim()
  const operatorId = (opts.operatorId ?? '').trim() || undefined

  if (!skuCode) {
    return {
      ok: false,
      error: '该发货行没有 SKU 编码,无法做治理决策',
      steps: [{ step: 'precheck', ok: false, detail: 'missing sku_code' }],
    }
  }

  const body: Record<string, unknown> = {
    action: action.type,
    operator_id: operatorId,
  }
  if (action.type === 'adopt') {
    body.model_id = action.modelId
  }

  const t0 = Date.now()
  try {
    const response = await plannerClient.post<ShipmentLineResolveBackendResponse>(
      `/shipments/lines/${encodeURIComponent(line.id)}/resolve`,
      body,
      { timeout: 60_000 },
    )
    const data = response.data
    const steps: ShipmentLineResolveResult['steps'] = (data.steps ?? []).map((s) => ({
      step: s.step,
      ok: s.ok,
      durationMs: s.duration_ms,
      detail: s.detail ?? undefined,
    }))

    // BomSnapshot 完整对象不在响应里 (后端只返 snapshot_id),
    // 调用方目前只用 result.snapshot 是否存在做"刷新台账"的判断,
    // 用一个最小占位对象保持类型契约。需要完整字段的调用方应单独
    // 调 GET /shipments/bom-snapshots/{id}。
    const snapshot = data.snapshot_id
      ? ({ id: data.snapshot_id } as unknown as BomSnapshot)
      : undefined

    return {
      ok: data.ok,
      snapshot,
      error: data.error ?? undefined,
      steps,
    }
  } catch (e: any) {
    const detail = String(e?.response?.data?.detail || e?.message || e || 'unknown')
    const durationMs = Date.now() - t0
    return {
      ok: false,
      error: detail,
      steps: [{ step: 'http_request', ok: false, durationMs, detail }],
    }
  }
}

export const computeShipmentLineSnapshot = async (
  shipment_line_id: string,
  payload: ShipmentLineComputeSnapshotRequest,
): Promise<ShipmentLineComputeSnapshotResponse> => {
  const id = String(shipment_line_id || '').trim()
  const response = await plannerClient.post(`/shipments/lines/${id}/compute-snapshot`, payload)
  return response.data
}

// ============================================================================
// Bulk resolve (Issue 29 follow-up p1-new-4)
//
// Folds PendingTab's `Promise.all + concurrency 8` fanout into one server
// call. See backend shipment_import_service.bulk_resolve_shipment_lines.
// Use this for batch-toolbar operations; for single-row "one-off" decisions
// keep using resolveShipmentLine (it returns richer step audit).
// ============================================================================

export interface ShipmentLineBulkResolveItem {
  shipment_line_id: string
  action: 'adopt' | 'mark_long_tail' | 'defer_modeling'
  /** required when action='adopt' */
  model_id?: string
}

export interface ShipmentLineBulkResolveRequest {
  items: ShipmentLineBulkResolveItem[]
  operator_id?: string
  note?: string
  /** default false = best-effort (process all rows); true = bail on first failure */
  stop_on_first_error?: boolean
}

export interface ShipmentLineBulkResolveResultItem {
  shipment_line_id: string
  ok: boolean
  action: string
  snapshot_id?: string | null
  snapshot_action?: string | null
  error?: string | null
  duration_ms: number
}

export interface ShipmentLineBulkResolveResponse {
  total: number
  succeeded: number
  failed: number
  skipped_after_error: number
  total_duration_ms: number
  results: ShipmentLineBulkResolveResultItem[]
}

export const bulkResolveShipmentLines = async (
  payload: ShipmentLineBulkResolveRequest,
): Promise<ShipmentLineBulkResolveResponse> => {
  const response = await plannerClient.post('/shipments/lines/bulk-resolve', payload, {
    timeout: 600_000,
  })
  return response.data
}

export const clearShipmentLineSnapshots = async (payload: {
  shipment_line_ids: string[]
  operator_id?: string
  reason?: string
}): Promise<ShipmentLineClearSnapshotsResponse> => {
  const response = await plannerClient.post('/shipments/lines/clear-snapshots', payload)
  return response.data
}

// "⚡ 一键自动绑定" — recognize unbound SKUs in recent pending shipment lines
// using the same keyword/code-hint algorithm as the legacy
// /costing/sku-master "自动识别" tab, but scoped to actively-shipping SKUs
// and following through with bind + immediate snapshot generation.
export const autoResolvePendingShipmentLinesPreview = async (
  payload: ShipmentLinesAutoResolveRequest = {},
  opts: PlannerRequestOptions = {},
): Promise<ShipmentLinesAutoResolvePreviewResponse> => {
  const response = await plannerClient.post('/shipments/lines/auto-resolve/preview', payload, {
    timeout: opts.timeoutMs ?? 30_000,
    signal: opts.signal,
  })
  return response.data
}

export const autoResolvePendingShipmentLinesExecute = async (
  payload: ShipmentLinesAutoResolveRequest = {},
  opts: PlannerRequestOptions = {},
): Promise<ShipmentLinesAutoResolveExecuteResponse> => {
  const response = await plannerClient.post('/shipments/lines/auto-resolve/execute', payload, {
    timeout: opts.timeoutMs ?? 60_000,
    signal: opts.signal,
  })
  return response.data
}

// Page-header lightweight summary (~50ms): "上次同步 + 24h 新进 + 拆源"
export const fetchShipmentLinesRecentStats = async (
  params: { hours?: number; latest_runs_limit?: number } = {},
  opts: PlannerRequestOptions = {},
): Promise<ShipmentLinesRecentStatsResponse> => {
  const response = await plannerClient.get('/shipments/lines/recent-stats', {
    params: sanitizeParams(params as Record<string, unknown>),
    timeout: opts.timeoutMs ?? 10_000,
    signal: opts.signal,
  })
  return response.data
}

// Manual "🔁 回写快照" — operator-initiated catch-up for "已绑定但缺快照"
// rows beyond the 14-day background sweep window.
export interface RegenerateBoundSnapshotsResponse {
  scanned: number
  snapshots_created: number
  snapshots_recomputed: number
  skipped_already_done: number
  failed: number
  duration_ms: number
  lookback_days: number
  limit: number
  failure_samples?: string[]
}

export const regenerateBoundPendingSnapshots = async (
  params: { lookback_days?: number; limit?: number } = {},
  opts: PlannerRequestOptions = {},
): Promise<RegenerateBoundSnapshotsResponse> => {
  const response = await plannerClient.post(
    '/shipments/lines/regenerate-snapshots',
    null,
    {
      params: sanitizeParams(params as Record<string, unknown>),
      timeout: opts.timeoutMs ?? 60_000,
      signal: opts.signal,
    },
  )
  return response.data
}

export const fetchReturnsRateBySku = async (params: {
  start: string
  end: string
  group_by?: 'day' | 'month'
  channel?: string
  sku_code?: string
}, opts: PlannerRequestOptions = {}): Promise<ReturnsRateBySkuResponse> => {
  const response = await plannerClient.get('/analytics/returns-rate/sku', {
    params: sanitizeParams(params as Record<string, unknown>),
    timeout: opts.timeoutMs ?? ANALYTICS_QUERY_TIMEOUT_MS,
    signal: opts.signal,
  })
  return response.data
}

export const fetchProfitBySku = async (params: {
  start: string
  end: string
  group_by?: 'day' | 'month'
  channel?: string
  sku_code?: string
}): Promise<ProfitBySkuResponse> => {
  const response = await plannerClient.get('/analytics/profit/sku', {
    params: sanitizeParams(params as Record<string, unknown>),
  })
  return response.data
}

export const fetchProfitByModel = async (params: {
  start: string
  end: string
  group_by?: 'day' | 'month'
  channel?: string
  model_code?: string
}): Promise<ProfitByModelResponse> => {
  const response = await plannerClient.get('/analytics/profit/model', {
    params: sanitizeParams(params as Record<string, unknown>),
  })
  return response.data
}

export const fetchModelInsightsSummary = async (params: {
  start: string
  end: string
  channel?: string
  bundle_template_code?: string
  bundle_preset_selector?: string
}): Promise<ModelInsightsSummaryResponse> => {
  const response = await plannerClient.get('/analytics/models/summary', {
    params: sanitizeParams(params as Record<string, unknown>),
  })
  return response.data
}

export const fetchModelInsightsDetail = async (params: {
  start: string
  end: string
  model_code: string
  channel?: string
  version_id?: string
  bundle_template_code?: string
  bundle_preset_selector?: string
}): Promise<ModelInsightsDetailResponse> => {
  const response = await plannerClient.get('/analytics/models/detail', {
    params: sanitizeParams(params as Record<string, unknown>),
  })
  return response.data
}

export const fetchModelUsageMaterialsSummary = async (params: {
  start: string
  end: string
  model_code: string
  channel?: string
  version_id?: string
}): Promise<ModelUsageMaterialSummaryResponse> => {
  const response = await plannerClient.get('/analytics/models/materials-summary', {
    params: sanitizeParams(params as Record<string, unknown>),
  })
  return response.data
}

export const fetchModelUsageProcessesSummary = async (params: {
  start: string
  end: string
  model_code: string
  channel?: string
  version_id?: string
}): Promise<ModelUsageProcessSummaryResponse> => {
  const response = await plannerClient.get('/analytics/models/processes-summary', {
    params: sanitizeParams(params as Record<string, unknown>),
  })
  return response.data
}

export const fetchReturnsRateByChannel = async (params: {
  start: string
  end: string
  group_by?: 'day' | 'month'
  channel?: string
}, opts: PlannerRequestOptions = {}): Promise<ReturnsRateByChannelResponse> => {
  const response = await plannerClient.get('/analytics/returns-rate/channel', {
    params: sanitizeParams(params as Record<string, unknown>),
    timeout: opts.timeoutMs ?? ANALYTICS_QUERY_TIMEOUT_MS,
    signal: opts.signal,
  })
  return response.data
}

export const fetchProfitByChannel = async (params: {
  start: string
  end: string
  group_by?: 'day' | 'month'
  channel?: string
}): Promise<ProfitByChannelResponse> => {
  const response = await plannerClient.get('/analytics/profit/channel', {
    params: sanitizeParams(params as Record<string, unknown>),
  })
  return response.data
}

export const fetchSalesLines = async (params: {
  start: string
  end: string
  page?: number
  page_size?: number
  channel?: string
  sku_code?: string
  shipment_no?: string
  order_no?: string
  product_link_id?: string
  bound_model_code?: string
  bundle_template_code?: string
  bundle_preset_selector?: string
  include_missing?: boolean
}): Promise<SalesLinesResponse> => {
  const response = await plannerClient.get('/analytics/sales/lines', {
    params: sanitizeParams(params as Record<string, unknown>),
  })
  return response.data
}

export const fetchSalesProfitDashboard = async (
  params: {
    start: string
    end: string
    group_by?: 'day' | 'week' | 'month'
    channel?: string
    top_n?: number
  },
  opts: PlannerRequestOptions = {},
): Promise<SalesProfitDashboardResponse> => {
  const response = await plannerClient.get('/analytics/sales/profit-dashboard', {
    params: sanitizeParams(params as Record<string, unknown>),
    timeout: opts.timeoutMs ?? ANALYTICS_QUERY_TIMEOUT_MS,
    signal: opts.signal,
  })
  return response.data
}

export const importSkuMasterXlsx = async (params: {
  file: File
  requested_by?: string
}): Promise<SkuMasterImportResponse> => {
  const formData = new FormData()
  formData.append('file', params.file)
  if (params.requested_by) formData.append('requested_by', params.requested_by)
  const response = await plannerClient.post('/sku-master/import', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return response.data
}

export const importAfterSalesXlsx = async (params: {
  file: File
  export_date?: string
  requested_by?: string
}, opts: PlannerRequestOptions = {}): Promise<AfterSalesImportBatch> => {
  const formData = new FormData()
  formData.append('file', params.file)
  if (params.export_date) formData.append('export_date', params.export_date)
  if (params.requested_by) formData.append('requested_by', params.requested_by)
  const response = await plannerClient.post('/after-sales/import', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: opts.timeoutMs ?? AFTER_SALES_IMPORT_TIMEOUT_MS,
    signal: opts.signal,
  })
  return response.data
}

export const fetchAfterSalesImportBatches = async (
  params: { page?: number; page_size?: number } = {},
  opts: PlannerRequestOptions = {},
): Promise<PaginatedResponse<AfterSalesImportBatch>> => {
  const response = await plannerClient.get('/after-sales/import-batches', {
    params: sanitizeParams(params as Record<string, unknown>),
    timeout: opts.timeoutMs ?? ANALYTICS_QUERY_TIMEOUT_MS,
    signal: opts.signal,
  })
  return response.data
}

export const fetchAfterSalesLines = async (
  params: {
    start?: string
    end?: string
    channel?: string
    sku_code?: string
    product_link_id?: string
    reason?: string
    model_code?: string
    time_basis?: 'applied' | 'shipment_completed'
    page?: number
    page_size?: number
  } = {},
  opts: PlannerRequestOptions = {},
): Promise<PaginatedAfterSalesLinesResponse> => {
  const response = await plannerClient.get('/after-sales/lines/search', {
    params: sanitizeParams(params as Record<string, unknown>),
    timeout: opts.timeoutMs ?? ANALYTICS_QUERY_TIMEOUT_MS,
    signal: opts.signal,
  })
  return response.data
}

export const fetchAfterSalesDashboard = async (
  params: {
    start: string
    end: string
    group_by?: 'day' | 'week' | 'month'
    channel?: string
    top_n?: number
    view?: 'factory' | 'ops'
  },
  opts: PlannerRequestOptions = {},
): Promise<AfterSalesDashboardResponse> => {
  const response = await plannerClient.get('/analytics/after-sales/dashboard', {
    params: sanitizeParams(params as Record<string, unknown>),
    timeout: opts.timeoutMs ?? ANALYTICS_QUERY_TIMEOUT_MS,
    signal: opts.signal,
  })
  return response.data
}

export const fetchAfterSalesReasonOptions = async (
  params: { start?: string; end?: string; channel?: string; sku_code?: string; model_code?: string; limit?: number } = {},
  opts: PlannerRequestOptions = {},
): Promise<AfterSalesReasonOptionsResponse> => {
  const response = await plannerClient.get('/after-sales/reason-options', {
    params: sanitizeParams(params as Record<string, unknown>),
    timeout: opts.timeoutMs ?? ANALYTICS_QUERY_TIMEOUT_MS,
    signal: opts.signal,
  })
  return response.data
}

export const fetchAfterSalesModelOptions = async (
  params: { start?: string; end?: string; channel?: string; sku_code?: string; reason?: string; limit?: number } = {},
  opts: PlannerRequestOptions = {},
): Promise<AfterSalesModelOptionsResponse> => {
  const response = await plannerClient.get('/after-sales/model-options', {
    params: sanitizeParams(params as Record<string, unknown>),
    timeout: opts.timeoutMs ?? ANALYTICS_QUERY_TIMEOUT_MS,
    signal: opts.signal,
  })
  return response.data
}

export const fetchSkuMaster = async (
  params: {
    page?: number
    page_size?: number
    search?: string
    channel?: string
    match_status?: string
    target_kind?: 'model' | 'bundle' | 'any'
    bound_state?: 'bound' | 'unbound' | 'all'
    bound_model_id?: string
    bound_model_code?: string
    bound_version_id?: string
    bundle_bound_state?: 'bound' | 'unbound'
    bundle_template_id?: string
    bundle_template_code?: string
    bundle_preset_selector?: string
    preparse_state?: 'parsed' | 'unparsed'
    spec_mismatch?: boolean
    /** SKU 数据质量状态筛选：'spu_attribute_conflict' | 'ok' | 不传 = 不限 */
    data_quality_status?: 'spu_attribute_conflict' | 'ok'
    include_terms?: string
    exclude_terms?: string
    match_scope?: 'spec' | 'name'
    excluded_sku_master_ids?: string[]
    shop_spec_code_kind?: 'structured' | 'platform' | 'malformed' | 'nonstructured' | 'empty' | 'all'
    compute_total?: boolean
    include_bindings?: boolean
    include_parsed_fields?: boolean
  } = {},
  opts: PlannerRequestOptions = {},
): Promise<SkuMasterListResponse> => {
  const response = await plannerClient.get('/sku-master', {
    params: sanitizeParams(params),
    timeout: opts.timeoutMs,
    signal: opts.signal,
  })
  return response.data
}

/** 单条 SKU 重新评估"数据质量"标签（SPU 属性冲突）。 */
export const recomputeSkuDataQuality = async (
  skuMasterId: string,
  payload: { lookback_days?: number } = {},
): Promise<{
  sku_master_id: string
  data_quality_status: string | null
  data_quality_evidence: import('@/types/planner').SkuDataQualityEvidence | null
}> => {
  const resp = await plannerClient.post(
    `/sku-master/${skuMasterId}/data-quality/recompute`,
    payload,
  )
  return resp.data
}

export interface ShopSpecCodeSummary {
  total: number
  structured: number
  platform: number
  malformed: number
  empty: number
}

export const fetchShopSpecCodeSummary = async (
  params: { channel?: string; bound_state?: 'bound' | 'unbound' | 'all' } = {},
): Promise<ShopSpecCodeSummary> => {
  const response = await plannerClient.get('/sku-master/shop-spec-code-summary', {
    params: sanitizeParams(params),
  })
  return response.data
}

export const fetchSkuMasterDetail = async (skuId: string): Promise<SkuMaster> => {
  const response = await plannerClient.get(`/sku-master/${skuId}`)
  return response.data
}

export const resolveSkuMasterSuspectMisbind = async (
  skuId: string,
  payload: { requested_by?: string; note?: string } = {},
): Promise<{
  sku_master_id: string
  erp_sku_barcode: string | null
  suspect_misbind_resolved: boolean
}> => {
  const response = await plannerClient.post(
    `/sku-master/${encodeURIComponent(String(skuId))}/suspect-misbind/resolve`,
    payload,
  )
  return response.data
}

export const resolveSkuMasterSuspectMisbindByBarcode = async (
  barcode: string,
  payload: { requested_by?: string; note?: string } = {},
): Promise<{
  sku_master_id: string
  erp_sku_barcode: string | null
  suspect_misbind_resolved: boolean
}> => {
  const code = String(barcode || '').trim()
  if (!code) throw new Error('barcode required')
  const found = await fetchSkuMasterByBarcode(code, { limit: 1 })
  const sm = found?.sku_master
  if (!sm?.id) throw new Error(`未找到 SKU 主档：${code}`)
  return resolveSkuMasterSuspectMisbind(String(sm.id), payload)
}

export const resolveSkuMasterSpecMismatch = async (
  skuId: string,
  payload: { requested_by?: string; note?: string } = {},
): Promise<{
  sku_master_id: string
  erp_sku_barcode: string | null
  spec_mismatch: boolean
  spec_mismatch_resolved: boolean
}> => {
  const response = await plannerClient.post(
    `/sku-master/${encodeURIComponent(String(skuId))}/spec-mismatch/resolve`,
    payload,
  )
  return response.data
}

export const fetchSkuMasterByBarcode = async (
  barcode: string,
  params: { channel?: string; limit?: number } = {},
): Promise<SkuMasterScanResponse> => {
  const code = String(barcode || '').trim()
  const response = await plannerClient.get(`/sku-master/by-barcode/${encodeURIComponent(code)}`, {
    params: sanitizeParams(params as Record<string, unknown>),
  })
  return response.data
}

export const fetchPublishedStandardModels = async (params: {
  search?: string
  limit?: number
} = {}): Promise<PublishedStandardModelCandidateListResponse> => {
  const response = await plannerClient.get('/sku-master/published-standard-models', { params: sanitizeParams(params) })
  return response.data
}

// ============================================================
// 通用 "绑定目标" 选择器（标准模型 + 套装模板二合一）
// 配套后端：GET /api/planner/binding-targets
// 业务背景：详见 components/common/TargetPicker.tsx 顶部 docstring 与
// services/binding_target_service.py 顶部 docstring。
// ============================================================
export type BindingTargetVariant = {
  variant_code: string
  material_name: string | null
  label: string
}

export type BindingTargetPreset = {
  selector: string
  label: string
  // 'force' / 'parse'：决定天猫 SKU 模板生成的 token 前缀（Z-/B-）。
  // 来自 BundleTemplate.metadata_json.phrase_presets[i].mode；缺省 'parse'。
  mode: 'force' | 'parse'
}

export type BindingTargetItem = {
  kind: 'model' | 'bundle'
  id: string
  code: string
  name: string | null
  // model-only
  published_version_id?: string | null
  version_label?: string | null
  variants?: BindingTargetVariant[]
  // bundle-only
  presets?: BindingTargetPreset[]
}

export type BindingTargetSearchResponse = {
  items: BindingTargetItem[]
  truncated: boolean
}

export const fetchBindingTargets = async (
  params: { search?: string; kind?: 'model' | 'bundle'; limit?: number } = {},
): Promise<BindingTargetSearchResponse> => {
  const response = await plannerClient.get('/binding-targets', { params: sanitizeParams(params) })
  return response.data
}

type PlannerRequestOptions = {
  timeoutMs?: number
  signal?: AbortSignal
}

export const bindSkuMastersByModel = async (
  payload: {
  model_id: string
  sku_master_ids: string[]
  requested_by?: string
  allow_rebind?: boolean
  /**
   * 可选：用户在 TargetPickerBrowserButton 显式选定的"最终绑定变体编码"（如 KB8-001）。
   * 后端会规范化为大写写入 sku_master.metadata_json.bound_variant_code，列表/详情
   * 接口直接读这个字段拼出 "麻感冰丝(KB8-001)" 类显示串。传 undefined / null = 不指定变体。
   */
  variant_code?: string | null
  },
  opts: PlannerRequestOptions = {},
): Promise<SkuMasterBindByModelResponse> => {
  const response = await plannerClient.post('/sku-master/bind-by-model', payload, {
    timeout: opts.timeoutMs,
    signal: opts.signal,
  })
  return response.data
}

export const unbindSkuMasters = async (
  payload: {
    sku_master_ids: string[]
    requested_by?: string
  },
  opts: PlannerRequestOptions = {},
): Promise<SkuMasterUnbindResponse> => {
  const response = await plannerClient.post('/sku-master/unbind', payload, {
    timeout: opts.timeoutMs,
    signal: opts.signal,
  })
  return response.data
}

export const generateSkuMasterPreparseAndSnapshots = async (
  payload: {
    sku_master_ids: string[]
    operator_id?: string
    limit_per_sku?: number
    overwrite?: boolean
  },
  opts: PlannerRequestOptions = {},
): Promise<SkuMasterGeneratePreparseAndSnapshotsResponse> => {
  const response = await plannerClient.post('/sku-master/generate-preparse-and-snapshots', payload, {
    timeout: opts.timeoutMs,
    signal: opts.signal,
  })
  return response.data
}

export const previewBindSkuMastersByModel = async (
  payload: {
    model_id: string
    sku_master_ids: string[]
    requested_by?: string
    allow_rebind?: boolean
  },
  opts: PlannerRequestOptions = {},
): Promise<SkuMasterBindPreviewResponse> => {
  const response = await plannerClient.post('/sku-master/bind-by-model/preview', payload, {
    timeout: opts.timeoutMs,
    signal: opts.signal,
  })
  return response.data
}

export const bindSkuMastersByModelBulk = async (
  payload: {
    model_id: string
    requested_by?: string
    limit?: number
    allow_rebind?: boolean
    search?: string
    channel?: string
    match_status?: string
    spec_mismatch?: boolean
    preparse_state?: string
    include_terms?: string
    exclude_terms?: string
    match_scope?: 'spec' | 'name' | 'auto' | 'spec_or_name'
    excluded_sku_master_ids?: string[]
    variant_code?: string | null
  },
  opts: PlannerRequestOptions = {},
): Promise<{
  batch_candidates: number
  bound_count: number
  skipped_already_bound: number
  skipped_missing_barcode: number
  skipped_excluded: number
  errors: Array<Record<string, unknown>>
  has_more: boolean
}> => {
  const response = await plannerClient.post('/sku-master/bind-by-model/bulk', payload, {
    timeout: opts.timeoutMs,
    signal: opts.signal,
  })
  return response.data
}

export const previewBindSkuMastersByModelBulk = async (
  payload: {
    model_id: string
    requested_by?: string
    limit?: number
    bound_state?: 'unbound' | 'bound' | 'all'
    allow_rebind?: boolean
    search?: string
    channel?: string
    match_status?: string
    spec_mismatch?: boolean
    preparse_state?: string
    include_terms?: string
    exclude_terms?: string
    match_scope?: 'spec' | 'name' | 'auto' | 'spec_or_name'
    bound_model_id?: string
    bound_model_code?: string
    bound_version_id?: string
    excluded_sku_master_ids?: string[]
  },
  opts: PlannerRequestOptions = {},
): Promise<SkuMasterBindPreviewBulkResponse> => {
  const response = await plannerClient.post('/sku-master/bind-by-model/preview/bulk', payload, {
    timeout: opts.timeoutMs,
    signal: opts.signal,
  })
  return response.data
}

export const bindSkuMastersByBundleTemplate = async (
  payload: {
    template_id: string
    preset_selector?: string
    sku_master_ids: string[]
    requested_by?: string
    allow_rebind?: boolean
  },
  opts: PlannerRequestOptions = {},
): Promise<{
  total_selected: number
  bound_count: number
  skipped_already_bound: number
  errors: Array<Record<string, unknown>>
}> => {
  const response = await plannerClient.post('/sku-master/bind-by-bundle', payload, {
    timeout: opts.timeoutMs,
    signal: opts.signal,
  })
  return response.data
}

export const previewBindSkuMastersByBundleTemplate = async (
  payload: {
    template_id: string
    preset_selector?: string
    sku_master_ids: string[]
    requested_by?: string
    allow_rebind?: boolean
  },
  opts: PlannerRequestOptions = {},
): Promise<SkuMasterBindPreviewResponse> => {
  const response = await plannerClient.post('/sku-master/bind-by-bundle/preview', payload, {
    timeout: opts.timeoutMs,
    signal: opts.signal,
  })
  return response.data
}

export const bindSkuMastersByBundleTemplateBulk = async (
  payload: {
    template_id: string
    preset_selector?: string
    requested_by?: string
    limit?: number
    bound_state?: 'unbound' | 'bound' | 'all'
    allow_rebind?: boolean
    search?: string
    channel?: string
    match_status?: string
    spec_mismatch?: boolean
    preparse_state?: string
    include_terms?: string
    exclude_terms?: string
    match_scope?: 'spec' | 'name' | 'auto' | 'spec_or_name'
    bound_model_id?: string
    bound_model_code?: string
    bound_version_id?: string
    excluded_sku_master_ids?: string[]
  },
  opts: PlannerRequestOptions = {},
): Promise<{
  batch_candidates: number
  bound_count: number
  skipped_already_bound: number
  skipped_excluded: number
  errors: Array<Record<string, unknown>>
  has_more: boolean
}> => {
  const response = await plannerClient.post('/sku-master/bind-by-bundle/bulk', payload, {
    timeout: opts.timeoutMs,
    signal: opts.signal,
  })
  return response.data
}

export const previewBindSkuMastersByBundleTemplateBulk = async (
  payload: {
    template_id: string
    preset_selector?: string
    requested_by?: string
    limit?: number
    bound_state?: 'unbound' | 'bound' | 'all'
    allow_rebind?: boolean
    search?: string
    channel?: string
    match_status?: string
    spec_mismatch?: boolean
    preparse_state?: string
    include_terms?: string
    exclude_terms?: string
    match_scope?: 'spec' | 'name' | 'auto' | 'spec_or_name'
    bound_model_id?: string
    bound_model_code?: string
    bound_version_id?: string
    excluded_sku_master_ids?: string[]
  },
  opts: PlannerRequestOptions = {},
): Promise<SkuMasterBindPreviewBulkResponse> => {
  const response = await plannerClient.post('/sku-master/bind-by-bundle/preview/bulk', payload, {
    timeout: opts.timeoutMs,
    signal: opts.signal,
  })
  return response.data
}

export const autoBindSkuMastersPreview = async (payload: {
  limit?: number
  scan_limit?: number
} = {}): Promise<SkuMasterAutoBindPreviewResponse> => {
  const response = await plannerClient.post('/sku-master/auto-bind/preview', payload)
  return response.data
}

export const autoBindSkuMastersExecute = async (payload: {
  limit?: number
  requested_by?: string
  sku_master_ids?: string[]
} = {}): Promise<SkuMasterAutoBindExecuteResponse> => {
  const response = await plannerClient.post('/sku-master/auto-bind/execute', payload)
  return response.data
}

export const saveSkuMasterSpecPreparse = async (
  skuId: string,
  payload: {
    spec_text: string
    width_cm?: string | number | null
    height_cm?: string | number | null
    diameter_cm?: string | number | null
    requested_by?: string | null
  },
): Promise<{
  sku_id: string
  preparse_spec_hash: string
  preparse_dimensions: Record<string, unknown>
  preparse_tokens: string[]
  preparse_saved_at?: string | null
  preparse_saved_by?: string | null
}> => {
  const response = await plannerClient.post(`/sku-master/${skuId}/spec-preparse`, payload)
  return response.data
}

export const bulkSaveSkuMasterSpecPreparse = async (payload: {
  limit?: number
  search?: string
  channel?: string
  match_status?: string
  target_kind?: 'model' | 'bundle' | 'any'
  bundle_bound_state?: 'bound' | 'unbound'
  bundle_template_id?: string
  bundle_template_code?: string
  bundle_preset_selector?: string
  include_terms?: string
  exclude_terms?: string
  match_scope?: string
  bound_model_id?: string
  bound_model_code?: string
  bound_version_id?: string
  preparse_state?: 'parsed' | 'unparsed'
  cursor_id?: string
  excluded_sku_ids?: string[]
  skip_if_same_hash?: boolean
  requested_by?: string
} = {}, opts: PlannerRequestOptions = {}): Promise<{
  scanned: number
  saved: number
  skipped_same_hash: number
  skipped_empty_spec?: number
  errors: Array<Record<string, unknown>>
  batch_candidates?: number
  has_more?: boolean
  next_cursor_id?: string | null
  mode?: string | null
}> => {
  const response = await plannerClient.post('/sku-master/spec-preparse/bulk', payload, {
    timeout: opts.timeoutMs,
    signal: opts.signal,
  })
  return response.data
}

export const previewSkuMasterSpecPreparse = async (payload: {
  limit?: number
  search?: string
  channel?: string
  match_status?: string
  target_kind?: 'model' | 'bundle' | 'any'
  bundle_bound_state?: 'bound' | 'unbound'
  bundle_template_id?: string
  bundle_template_code?: string
  bundle_preset_selector?: string
  include_terms?: string
  exclude_terms?: string
  match_scope?: string
  bound_model_id?: string
  bound_model_code?: string
  bound_version_id?: string
  preparse_state?: 'parsed' | 'unparsed'
} = {}): Promise<{
  scanned: number
  skipped_empty_spec?: number
  errors?: Array<Record<string, unknown>>
  items: Array<{
    sku_id: string
    erp_sku_barcode: string
    channel?: string | null
    spec_text_used: string
    spec_hash: string
    width_cm?: string | number | null
    height_cm?: string | number | null
    diameter_cm?: string | number | null
    area_m2?: string | number | null
    perimeter_m?: string | number | null
  }>
}> => {
  const response = await plannerClient.post('/sku-master/spec-preparse/preview', payload)
  return response.data
}

export const executeSkuMasterSpecPreparse = async (payload: {
  sku_ids: string[]
  skip_if_same_hash?: boolean
  requested_by?: string
}, opts: PlannerRequestOptions = {}): Promise<{
  scanned: number
  saved: number
  skipped_same_hash: number
  skipped_empty_spec?: number
  errors: Array<Record<string, unknown>>
}> => {
  const response = await plannerClient.post('/sku-master/spec-preparse/execute', payload, {
    timeout: opts.timeoutMs,
    signal: opts.signal,
  })
  return response.data
}

export const validateProductModelRecognitionKeywords = async (
  modelId: string,
  payload: { keywords: string[] },
): Promise<RecognitionKeywordsValidateResponse> => {
  const response = await plannerClient.post(`/product-models/${modelId}/recognition/validate`, payload)
  return response.data
}

