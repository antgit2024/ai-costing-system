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
  SpecParseRequest,
  SpecParseResponse,
  LineVariantCreateRequest,
  LineVariantDetailRead,
  LineVariantItemsReplaceRequest,
  LineVariantUpdateRequest,
  BomGenerateRequest,
  BomGenerateResponse,
  BomSnapshot,
  ShipmentException,
  ShipmentExceptionRetryRequest,
  ShipmentExceptionRetryResponse,
  ShipmentImportBatchListResponse,
  ShipmentImportBatch,
  ProductModelVersionPatchPayload,
  SkuMaster,
  SkuMasterImportResponse,
  SkuMasterListResponse,
  PublishedStandardModelCandidateListResponse,
  SkuMasterBindByModelResponse,
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
} from '@/types/planner'

const resolvePlannerApiBase = (raw?: string): string => {
  if (!raw) return '/api/planner'
  // If someone sets API base to same host but a different port (e.g. :8800),
  // browsers will treat it as cross-origin and block unless CORS is configured.
  // In production we rely on nginx to proxy `/api/planner` on the same origin.
  if (typeof window === 'undefined') return raw
  try {
    const url = new URL(raw, window.location.origin)
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

export const plannerClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 20000,
})

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
  const slotsRaw = meta?.slots
  const slots = Array.isArray(slotsRaw) ? slotsRaw.map((x: any) => String(x ?? '').trim()).filter(Boolean) : []
  const slotDisplayNamesRaw = meta?.slot_display_names
  const slot_display_names =
    slotDisplayNamesRaw && typeof slotDisplayNamesRaw === 'object' ? (slotDisplayNamesRaw as Record<string, any>) : undefined
  return {
    id: String(item?.id ?? ''),
    code,
    name: displayName || code,
    slots,
    slot_display_names:
      slot_display_names && Object.keys(slot_display_names).length
        ? Object.fromEntries(
            Object.entries(slot_display_names).map(([k, v]) => [String(k ?? '').trim(), String(v ?? '').trim()]).filter(([k]) => k),
          )
        : undefined,
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
  status?: 'active' | 'inactive'
}): Promise<StructureStandardRead> => {
  const code = String(payload.code ?? '').trim()
  const name = String(payload.name ?? '').trim()
  const slots = Array.isArray(payload.slots) ? payload.slots.map((x) => String(x ?? '').trim()).filter(Boolean) : []
  const slotDisplayNames =
    payload.slot_display_names && typeof payload.slot_display_names === 'object' ? payload.slot_display_names : undefined
  const isActive = (payload.status ?? 'active') === 'active'

  const created = await createTaxonomyItem({
    domain: STRUCTURE_STANDARD_DOMAIN,
    name: code,
    scopes: ['*'],
    is_active: isActive,
    source: 'local',
    metadata: { display_name: name, slots, ...(slotDisplayNames ? { slot_display_names: slotDisplayNames } : {}) },
  })
  return normalizeStructureStandard(created)
}

export const updateStructureStandard = async (
  id: string,
  payload: { name?: string; slots?: string[]; slot_display_names?: Record<string, string>; status?: 'active' | 'inactive' },
): Promise<StructureStandardRead> => {
  const next: any = {}
  if (payload.status) next.is_active = payload.status === 'active'
  if (payload.name !== undefined || payload.slots !== undefined || payload.slot_display_names !== undefined) {
    const name = payload.name !== undefined ? String(payload.name ?? '').trim() : undefined
    const slots = payload.slots !== undefined ? payload.slots.map((x) => String(x ?? '').trim()).filter(Boolean) : undefined
    const slotDisplayNames =
      payload.slot_display_names !== undefined && payload.slot_display_names
        ? (payload.slot_display_names as Record<string, string>)
        : undefined
    next.metadata = {
      ...(name !== undefined ? { display_name: name } : {}),
      ...(slots !== undefined ? { slots } : {}),
      ...(slotDisplayNames !== undefined ? { slot_display_names: slotDisplayNames } : {}),
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
): Promise<MaterialListResponse> => {
  const response = await plannerClient.get('/base-config/materials', {
    params: sanitizeParams(params as Record<string, unknown>),
  })
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

export const fetchProductModel = async (modelId: string): Promise<ProductModel> => {
  const response = await plannerClient.get(`/product-models/${modelId}`)
  return response.data
}

export const deleteProductModel = async (modelId: string): Promise<void> => {
  await plannerClient.delete(`/product-models/${modelId}`)
}

export const archiveSampleVersionsOnly = async (modelId: string): Promise<void> => {
  await plannerClient.post(`/product-models/${modelId}/archive-sample`)
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

export const fetchProductModelVersions = async (modelId: string): Promise<ProductModelVersionRead[]> => {
  const response = await plannerClient.get(`/product-models/${modelId}/versions`)
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

export const fetchProductModelVersionLines = async (versionId: string): Promise<ProductModelLinesResponse> => {
  const response = await plannerClient.get(`/product-model-versions/${versionId}/lines`)
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
  })
  return response.data
}

export const executeShipmentsFromPreview = async (payload: {
  preview_id: string
  file_name?: string
  export_date?: string
  requested_by?: string
}): Promise<ShipmentImportBatch> => {
  const response = await plannerClient.post('/shipments/import/execute', payload)
  return response.data
}

export const fetchShipmentExceptions = async (
  params: { batch_id?: string; resolved?: boolean; limit?: number } = {},
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

export const recomputeShipmentBomSnapshot = async (snapshot_id: string, payload?: { operator_id?: string }): Promise<BomSnapshot> => {
  const response = await plannerClient.post(`/shipments/bom-snapshots/${snapshot_id}/recompute`, payload ?? {})
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

export const fetchSkuMaster = async (
  params: {
    page?: number
    page_size?: number
    search?: string
    channel?: string
    match_status?: string
    bound_state?: 'bound' | 'unbound'
    preparse_state?: 'parsed' | 'unparsed'
    spec_mismatch?: boolean
    include_terms?: string
    exclude_terms?: string
    match_scope?: 'spec' | 'name'
  } = {},
): Promise<SkuMasterListResponse> => {
  const response = await plannerClient.get('/sku-master', { params: sanitizeParams(params) })
  return response.data
}

export const fetchSkuMasterDetail = async (skuId: string): Promise<SkuMaster> => {
  const response = await plannerClient.get(`/sku-master/${skuId}`)
  return response.data
}

export const fetchPublishedStandardModels = async (params: {
  search?: string
  limit?: number
} = {}): Promise<PublishedStandardModelCandidateListResponse> => {
  const response = await plannerClient.get('/sku-master/published-standard-models', { params: sanitizeParams(params) })
  return response.data
}

export const bindSkuMastersByModel = async (payload: {
  model_id: string
  sku_master_ids: string[]
  requested_by?: string
}): Promise<SkuMasterBindByModelResponse> => {
  const response = await plannerClient.post('/sku-master/bind-by-model', payload)
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
  include_terms?: string
  exclude_terms?: string
  match_scope?: string
  skip_if_same_hash?: boolean
  requested_by?: string
} = {}): Promise<{
  scanned: number
  saved: number
  skipped_same_hash: number
  errors: Array<Record<string, unknown>>
}> => {
  const response = await plannerClient.post('/sku-master/spec-preparse/bulk', payload)
  return response.data
}

export const previewSkuMasterSpecPreparse = async (payload: {
  limit?: number
  search?: string
  channel?: string
  match_status?: string
  include_terms?: string
  exclude_terms?: string
  match_scope?: string
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
}): Promise<{
  scanned: number
  saved: number
  skipped_same_hash: number
  errors: Array<Record<string, unknown>>
}> => {
  const response = await plannerClient.post('/sku-master/spec-preparse/execute', payload)
  return response.data
}

export const validateProductModelRecognitionKeywords = async (
  modelId: string,
  payload: { keywords: string[] },
): Promise<RecognitionKeywordsValidateResponse> => {
  const response = await plannerClient.post(`/product-models/${modelId}/recognition/validate`, payload)
  return response.data
}

