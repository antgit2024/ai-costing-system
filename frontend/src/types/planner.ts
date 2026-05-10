export interface Initiative {
  id: string
  code: string
  name: string
  description?: string | null
  owner_id: string
  sponsor?: string | null
  currency: string
  status: string
  target_launch_date?: string | null
  tags: string[]
  created_at: string
  updated_at: string
}

// ---------------------------------------------------------------------------
// Cost Rate Hub v1.3 — Insights cost-quality badge (U7-A)
// ---------------------------------------------------------------------------
// 给 4 个 Insights 看板（Profit / Shop / Sales / AfterSales）每行附带一枚
// 「成本可信度」徽章，由后端 `Hub.resolve_overhead_rate` 的 hit_layer 推导。
// 字段是 optional：旧前端忽略未知字段不会崩；新前端若拿到 undefined 就显示
// 占位 `-`。
export type CostQualityLevel = 'green' | 'yellow' | 'red'
export type CostQualityHitLayer =
  | 'model'
  | 'category'
  | 'cost_center'
  | 'global'
  | 'metadata_json'
  | 'hard_fallback'

export interface CostQualityBadge {
  level: CostQualityLevel
  hit_layer: CostQualityHitLayer
  source: string
  updated_at?: string | null
}

export interface PaginatedResponse<T> {
  total: number
  page: number
  page_size: number
  items: T[]
}

export interface PackageNode {
  id: string
  initiative_id: string
  name: string
  category?: string | null
  parent_package_id?: string | null
  owner_id?: string | null
  status: string
  notes?: string | null
  created_at: string
  updated_at: string
  children?: PackageNode[]
}

export interface SupplierQuote {
  id: string
  supplier_name: string
  contact?: string | null
  line_item_id: string
  quote_version: number
  currency: string
  unit_cost: string
  moq?: number | null
  lead_time_days?: number | null
  valid_through?: string | null
  attachments: string[]
  notes?: string | null
  created_at: string
  updated_at: string
}

export interface LineItem {
  id: string
  package_id: string
  type: string
  reference_code?: string | null
  description: string
  unit_of_measure: string
  quantity: string
  unit_cost_estimate: string
  currency: string
  supplier_id?: string | null
  preferred_quote_id?: string | null
  status: string
  metadata_json?: Record<string, unknown>
  supplier_quotes: SupplierQuote[]
  created_at: string
  updated_at: string
}

export interface NormalizedLineItem extends LineItem {
  metadata: Record<string, unknown>
}

export interface LineItemUpdatePayload {
  quantity?: number
  unit_cost_estimate?: number
  status?: string
  supplier_id?: string
  type?: string
}

export interface InitiativeQueryParams {
  [key: string]: string | number | undefined
  status?: string
  owner_id?: string
  tag?: string
  page?: number
  page_size?: number
}

export interface LineItemQueryParams {
  [key: string]: string | number | undefined
  initiative_id?: string
  package_id?: string
  status?: string
  type?: string
  supplier_id?: string
  search?: string
  page?: number
  page_size?: number
}

export interface ImportJob {
  id: string
  initiative_id: string
  file_name: string
  status: ImportJobStatus
  requested_by: string
  total_rows: number
  processed_rows: number
  error_rows: number
  errors: Array<{ row: number; error: string }>
  created_at: string
  updated_at: string
}

export type ImportJobStatus =
  | 'pending'
  | 'processing'
  | 'completed'
  | 'completed_with_errors'
  | 'failed'
  | string

export const terminalImportStatuses: ImportJobStatus[] = [
  'completed',
  'completed_with_errors',
  'failed',
]

export interface ScenarioSummary {
  id: string
  code: string
  name: string
  status: string
  baseline_flag: boolean
  initiative_id?: string
  initiative_name?: string
  owner_id?: string
  created_at?: string
  updated_at?: string
  total_cost?: string
  favorite?: boolean
  last_exported_at?: string | null
}

export interface ScenarioClonePayload {
  code: string
  name: string
  requested_by: string
  line_item_ids?: string[]
}

export interface ScenarioCloneResponse {
  job_id: string
  scenario_id: string
}

export interface ScenarioDiffParams {
  [key: string]: string | number | undefined
  against: string
  package_id?: string
  type?: string
  page?: number
  page_size?: number
}

export interface ScenarioDiffLine {
  line_item_id: string
  reference_code?: string | null
  description: string
  package_id: string
  package_name?: string | null
  item_type?: string | null
  quantity_diff: string | number
  unit_cost_diff: string | number
  total_cost_diff: string | number
  source_total: string | number
  target_total: string | number
}

export interface ScenarioDiffSummary {
  source_scenario_id: string
  target_scenario_id: string
  total_cost_source: string | number
  total_cost_target: string | number
  variance: string | number
  variance_percent: number
}

export interface ScenarioDiffResponse {
  job_id: string
  summary: ScenarioDiffSummary
  line_diffs: ScenarioDiffLine[]
  page: number
  page_size: number
  total: number
}

export type CalculationMethod =
  | 'area'
  | 'perimeter'
  | 'count'
  | 'width'
  | 'height'
  | 'long_side'
  | 'short_side'

export interface ScenarioListItem extends ScenarioSummary {
  owner_id: string
}

export interface ScenarioListResponse extends PaginatedResponse<ScenarioListItem> {}

export interface ScenarioListQueryParams extends Record<string, string | number | boolean | undefined> {
  page?: number
  page_size?: number
  status?: string
  initiative_id?: string
  owner_id?: string
  favorite?: boolean
  search?: string
  baseline_flag?: boolean
}

export interface ApprovalActionResponse {
  scenario_id: string
  scenario_status: string
  initiative_status: string
  baseline_flag: boolean
}

export interface ApprovalSubmitPayload {
  scenario_id: string
  actor_id: string
  actor_role: string
  comment?: string
}

export interface ApprovalApprovePayload extends ApprovalSubmitPayload {
  set_baseline?: boolean
}

export interface ApprovalRejectPayload extends ApprovalSubmitPayload {}

export type PlannerJobStatus = 'pending' | 'processing' | 'completed' | 'failed' | string

export interface PlannerJob {
  id: string
  initiative_id: string
  job_type: string
  file_name?: string | null
  requested_by: string
  status: PlannerJobStatus
  total_rows: number
  processed_rows: number
  error_rows: number
  errors: Array<{ row: number; error: string }>
  payload: Record<string, unknown>
  result: Record<string, unknown>
  created_at: string
  updated_at: string
  trace_id?: string
}

export type PlannerJobKind = 'planner' | 'import'

export const terminalPlannerJobStatuses: PlannerJobStatus[] = ['completed', 'failed']

export interface ScenarioExportPayload {
  requested_by: string
  format?: string
  comment?: string
}

export interface ScenarioExportResponse {
  job_id: string
  scenario_id: string
  executor_reference?: string
}

export interface BenchmarkSuggestPayload {
  scenario_id: string
  limit?: number
  owner_id?: string
}

export interface BenchmarkSuggestion {
  id: string
  title: string
  description?: string
  impact?: string
  score?: number
  recommendation?: string
  supplier_name?: string
  currency?: string
  freshness?: string
}

export interface BenchmarkFavorite {
  id: string
  suggestion_id: string
  scenario_id: string
  title?: string
  notes?: string
  created_at?: string
}

export interface AuditLogEntry {
  id: string
  target_type: string
  target_id: string
  action: string
  actor_id: string
  comment?: string | null
  created_at: string
  metadata?: Record<string, unknown>
  trace_id?: string
}

export interface AuditLogQueryParams extends Record<string, string | number | undefined> {
  target_type: string
  target_id: string
  page?: number
  page_size?: number
  action?: string
  trace_id?: string
  search?: string
}

export interface PaginatedAuditLogResponse {
  items: AuditLogEntry[]
  total: number
  page: number
  page_size: number
}

// Stage 2 (Migration 0039) — purchase entity 暂用枚举字符串，Phase 2 换 cost_center_master 真实 UUID。
export type PurchaseEntityCode = '一般纳税人' | '小规模A' | '小规模B'
export type MaterialPriceSource =
  | 'manual'
  | 'po_avg_30d'
  | 'last_po'
  | 'contract'
  | 'system_imported'
  | 'yida_sync'

export interface Material {
  id: string
  material_code: string
  material_name: string
  material_type: string
  category?: string | null
  model_category?: string | null
  calculation_method: CalculationMethod
  unit?: string | null
  purchase_unit?: string | null
  inventory_unit?: string | null
  unit_price?: number
  currency: string
  supplier_code?: string | null
  supplier_name?: string | null
  usage_scope?: string | null
  is_active: boolean
  status: string
  is_bom_material?: boolean
  conversion_purchase_to_bom?: string | number
  conversion_bom_to_inventory?: string | number
  images?: string[]
  bom_notes?: string | null
  source_created_at?: string | null
  source_updated_at?: string | null
  updated_at: string
  metadata_json?: Record<string, unknown>
  // Stage 2 (Migration 0039) — 税务/采购/效期
  purchase_entity_id?: PurchaseEntityCode | string | null
  tax_included_flag?: boolean
  tax_rate?: string | number | null
  price_source?: MaterialPriceSource | string | null
  effective_from?: string | null
  effective_to?: string | null
}

export interface MaterialListResponse extends PaginatedResponse<Material> {
  categories: string[]
}

export interface MaterialQueryParams extends Record<string, string | number | boolean | undefined> {
  page?: number
  page_size?: number
  search?: string
  category?: string
  material_type?: string
  status?: string
  is_active?: boolean
  is_bom_material?: boolean
  usage_class?: 'direct' | 'conditional' | 'indirect'
}

export interface MaterialStatusUpdatePayload {
  is_active?: boolean
  status?: string
  is_bom_material?: boolean
  unit?: string
  inventory_unit?: string
  conversion_purchase_to_bom?: number
  conversion_bom_to_inventory?: number
  bom_unit_price?: number
  calculation_method?: CalculationMethod
  metadata_json?: Record<string, unknown>
  // Stage 2 (Migration 0039) — 税务/采购/效期。null = 显式清空，undefined = 不动。
  purchase_entity_id?: PurchaseEntityCode | string | null
  tax_included_flag?: boolean
  tax_rate?: number | null
  price_source?: MaterialPriceSource | string | null
  effective_from?: string | null
  effective_to?: string | null
}

export interface MaterialExportResponse {
  job_id?: string
  download_url?: string
  message?: string
}

export interface ShippingRule {
  id: string
  rule_name: string
  priority: number
  is_active: boolean
  conditions: Record<string, any>
  outputs: Record<string, any>[]
  notes?: string | null
  metadata?: Record<string, any>
  created_at: string
  updated_at: string
}

export interface ShippingRuleListResponse {
  total: number
  page: number
  page_size: number
  items: ShippingRule[]
}

export interface ShippingRuleUpsertRequest {
  rule_name?: string
  priority?: number
  is_active?: boolean
  conditions?: Record<string, any>
  outputs?: Record<string, any>[]
  notes?: string | null
  metadata?: Record<string, any>
}

export interface ShippingRuleEvaluateRequest {
  shop_code?: string
  channel?: string
  shipping_method?: string
  is_merge?: boolean
  province?: string
  city?: string
  weight_kg?: number
  volume_m3?: number
  package_count?: number
  tokens?: string[]
  include_disabled_rules?: boolean
}

export interface ShippingRuleEvaluateResponse {
  matched_rules: { rule_id: string; rule_name: string; priority: number }[]
  lines: {
    material_id: string
    material_code: string
    material_name: string
    unit_of_measure?: string | null
    quantity: number
  }[]
  warnings: string[]
}

export interface MaterialSyncLog {
  id: string
  status: string
  operator?: string
  total_fetched: number
  processed: number
  created: number
  updated: number
  disabled: number
  skipped: number
  errors: string[]
  started_at: string
  finished_at?: string | null
  duration_ms?: number
  dump_path?: string | null
}

export interface MaterialSyncLogResponse extends PaginatedResponse<MaterialSyncLog> {}

export interface MaterialSyncJobRead {
  id: string
  job_type: string
  config_path: string
  requested_by: string
  status: string
  limit?: number | null
  dry_run: boolean
  dump_path?: string | null
  payload: Record<string, unknown>
  result_json: Record<string, unknown>
  error_message?: string | null
  started_at?: string | null
  finished_at?: string | null
  created_at: string
  updated_at: string
}

export interface VirtualMaterialBinding {
  material_id: string
  material_code: string
  material_name: string
  unit?: string | null
  purchase_unit_price?: string | number
  purchase_unit?: string | null
  bom_unit_price?: string | number
  bom_unit?: string | null
  currency?: string
  quantity_ratio: string | number
  loss_rate: string | number
  binding_type?: 'ratio' | 'quantity'
  image_url?: string | null
  status?: string | null
  is_active?: boolean
}

export interface VirtualMaterial {
  id: string
  virtual_code: string
  name: string
  virtual_kind?: 'recipe' | 'kit' | 'placeholder'
  description?: string | null
  category?: string | null
  unit?: string | null
  bom_unit_price?: string | number
  currency?: string
  status: string
  version: number
  notes?: string | null
  metadata_json?: Record<string, unknown>
  created_at: string
  updated_at: string
  bindings: VirtualMaterialBinding[]
}

export interface VirtualMaterialListResponse extends PaginatedResponse<VirtualMaterial> {}

export interface VirtualMaterialQueryParams extends Record<string, string | number | undefined> {
  search?: string
  status?: string
  category?: string
  virtual_kind?: 'recipe' | 'kit' | 'placeholder' | string
  binding_search?: string
  page?: number
  page_size?: number
}

export interface VirtualMaterialCreatePayload {
  virtual_code: string
  name: string
  virtual_kind?: 'recipe' | 'kit' | 'placeholder'
  description?: string
  category?: string
  unit?: string
  status?: string
  metadata_json?: Record<string, unknown>
}

export interface VirtualMaterialUpdatePayload {
  name?: string
  virtual_kind?: 'recipe' | 'kit' | 'placeholder'
  description?: string
  category?: string
  unit?: string
  status?: string
  metadata_json?: Record<string, unknown>
}

export interface VirtualMaterialBindingInput {
  material_id: string
  quantity_ratio: number
  loss_rate?: number
  binding_type?: 'ratio' | 'quantity'
}

export interface VirtualMaterialBindingRequest {
  bindings: VirtualMaterialBindingInput[]
}

export interface VirtualMaterialReference {
  virtual_material_id: string
  virtual_code: string
  virtual_name: string
  status: string
  quantity_ratio: string | number
  loss_rate: string | number
}

export interface VirtualMaterialInventoryRequest {
  quantity: number
  calculation_method?: CalculationMethod
  usage_context?: string
}

export interface VirtualMaterialInventoryItem {
  material_id: string
  material_code: string
  material_name: string
  unit?: string | null
  quantity_ratio: string | number
  loss_rate: string | number
  required_quantity: string | number
}

export interface VirtualMaterialInventoryResponse {
  virtual_material_id: string
  virtual_code: string
  virtual_name: string
  requested_quantity: string | number
  calculation_method?: CalculationMethod
  usage_context?: string
  items: VirtualMaterialInventoryItem[]
}

// -----------------------------
// BaseConfig / Material References
// -----------------------------

export interface MaterialReferencesVirtualMaterialItem {
  id: string
  virtual_code: string
  name: string
  virtual_kind?: 'recipe' | 'kit' | 'placeholder' | string
  status?: string | null
}

export interface MaterialReferencesProcessModuleItem {
  id: string
  name: string
}

export interface MaterialReferencesProductModelVersionItem {
  version_id: string
  model_id: string
  model_name: string
  version_label?: string | null
  version_kind: string
  version_status: string
}

export interface MaterialReferencesBlock<TItem> {
  count: number
  items: TItem[]
}

export type MaterialReferencesError =
  | string
  | {
      source?: string
      message: string
      detail?: unknown
    }

export interface MaterialReferencesResponse {
  material_id: string
  virtual_materials: MaterialReferencesBlock<MaterialReferencesVirtualMaterialItem>
  process_modules: MaterialReferencesBlock<MaterialReferencesProcessModuleItem>
  product_model_versions: MaterialReferencesBlock<MaterialReferencesProductModelVersionItem>
  errors: MaterialReferencesError[]
}

export type MaterialReferenceKind = 'real' | 'bom' | 'virtual'

export type LaborPricingMethod = 'fixed' | 'count' | 'area' | 'perimeter' | 'width' | 'height'

export interface ProcessModuleMaterialInput {
  material_kind?: MaterialReferenceKind
  material_ref_id?: string | null
  material_code?: string | null
  material_name?: string | null
  unit_of_measure?: string | null
  calculation_method?: CalculationMethod
  quantity: number
  loss_rate?: number
  sequence_order?: number
  material_category?: string | null
  selection_notes?: string | null
  loss_notes?: string | null
  metadata_json?: Record<string, unknown>
}

export interface ProcessModuleStepInput {
  sequence_order?: number
  team_name?: string | null
  pricing_method?: LaborPricingMethod
  work_minutes?: number
  unit_of_measure?: string | null
  description?: string | null
  notes?: string | null
  process_id?: string | null
  metadata_json?: Record<string, unknown>
}

export interface ProcessModuleMaterial extends ProcessModuleMaterialInput {
  id: string
}

export interface ProcessModuleStep extends ProcessModuleStepInput {
  id: string
  process?: ProcessReference | null
}

export interface ProcessModuleSummary {
  id: string
  module_code: string
  module_name: string
  description?: string | null
  category?: string | null
  status: string
  version: number
  tags: string[]
  metadata_json?: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface ProcessModuleDetail extends ProcessModuleSummary {
  materials: ProcessModuleMaterial[]
  steps: ProcessModuleStep[]
}

export interface ProcessModuleQueryParams extends Record<string, string | number | undefined> {
  search?: string
  category?: string
  status?: string
  // structure filters (MVP)
  // - structure_code: match "<code>" or "<code>:<slot>" prefix
  // - structure_tag: exact match any tag in metadata_json.structure_tags[]
  structure_code?: string
  structure_tag?: string
  page?: number
  page_size?: number
}

export interface ProcessModuleCreatePayload {
  module_code: string
  module_name: string
  description?: string
  category?: string
  status?: string
  tags?: string[]
  metadata_json?: Record<string, unknown>
  materials?: ProcessModuleMaterialInput[]
  steps?: ProcessModuleStepInput[]
  operator_id?: string
}

export interface ProcessModuleUpdatePayload {
  module_name?: string
  description?: string
  category?: string
  status?: string
  tags?: string[]
  metadata_json?: Record<string, unknown>
  materials?: ProcessModuleMaterialInput[]
  steps?: ProcessModuleStepInput[]
  operator_id?: string
}

export interface ProcessModuleCopyPayload {
  module_code: string
  module_name: string
  status?: string
  operator_id?: string
}

export interface ProcessModuleListResponse extends PaginatedResponse<ProcessModuleSummary> {}

export interface ProcessModuleReferenceResponse {
  total: number
  items: ProcessModuleDetail[]
}

export interface ProductModelModuleLink {
  id: string
  module_id: string
  sequence_order?: number
  notes?: string | null
  metadata_json?: Record<string, unknown>
  module?: Partial<ProcessModuleSummary> | null
}

export interface ProductModel {
  id: string
  model_code: string
  model_name: string
  description?: string | null
  category?: string | null
  calc_mode?: string
  fixed_price?: string | number | null
  standard_width_mm?: string | number | null
  standard_height_mm?: string | number | null
  unit_of_measure?: string | null
  status: string
  tags: string[]
  metadata_json?: Record<string, unknown>
  created_at: string
  updated_at: string
  modules: ProductModelModuleLink[]
  materials?: any[]
  processes?: any[]
  // version stats (optional; backend may include for list pages)
  sample_version_count?: number
  standard_version_count?: number
  current_published_standard_version_id?: string | null
  current_published_standard_version_label?: string | null
  current_published_variant_codes?: Array<{ variant_code: string; material_name?: string | null }>
  // list perf: avoid N+1 version fetch just to render thumbnail
  latest_sample_version_id?: string | null
}

export interface ProductModelQueryParams extends Record<string, string | number | boolean | undefined> {
  search?: string
  category?: string
  status?: string
  include_archived?: boolean
  page?: number
  page_size?: number
}

export interface ProductModelListResponse extends PaginatedResponse<ProductModel> {}

export interface ProductModelCreatePayload {
  model_code?: string
  model_name: string
  description?: string
  category?: string
  calc_mode?: 'ratio' | 'fixed' | 'independent'
  fixed_price?: number
  status?: string
  tags?: string[]
  standard_width_mm?: number
  standard_height_mm?: number
  unit_of_measure?: string
  metadata_json?: Record<string, unknown>
  modules?: Array<{
    module_id: string
    sequence_order?: number
    notes?: string
    metadata_json?: Record<string, unknown>
  }>
}

export interface ProductModelUpdatePayload {
  model_name?: string
  description?: string
  category?: string
  calc_mode?: 'ratio' | 'fixed' | 'independent'
  fixed_price?: number
  status?: string
  tags?: string[]
  standard_width_mm?: number
  standard_height_mm?: number
  unit_of_measure?: string
  metadata_json?: Record<string, unknown>
  modules?: Array<{
    module_id: string
    sequence_order?: number
    notes?: string
    metadata_json?: Record<string, unknown>
  }>
}

export interface ProductModelPlaceholder {
  virtual_material_id: string
  virtual_code: string
  name: string
  unit?: string | null
  placeholder_symbol?: string | null
  constraint_category?: string | null
}

export interface ProductModelPreviewRequest {
  width_mm: number
  height_mm: number
  quantity: number
  sku_hint?: string
}

export interface RandomCodeGenerateRequest {
  kind: 'product_model'
  length?: number
}

export interface RandomCodeGenerateResponse {
  code: string
}

export interface ProductModelSampleSpec {
  width_mm: number
  height_mm: number
  quantity: number
  unit_label: string
}

export interface ProductModelMaterialLineInput {
  id?: string
  source_module_id?: string
  source_module_code?: string
  source_module_name?: string
  material_kind: MaterialReferenceKind
  material_ref_id: string
  material_code?: string
  material_name?: string
  calculation_method: CalculationMethod
  sample_used_quantity?: number
  standard_used_quantity?: number
  fixed_quantity?: number
  coverage_ratio?: number
  base_quantity?: number
  loss_rate: number
  notes?: string
  metadata_json?: Record<string, unknown>
}

export interface ProductModelProcessLineInput {
  id?: string
  source_module_id?: string
  source_module_code?: string
  source_module_name?: string
  process_id: string
  process_code?: string
  process_name?: string
  team_name?: string
  pricing_method: LaborPricingMethod
  sample_minutes?: number
  standard_minutes?: number
  base_minutes: number
  unit_minutes: number
  rate_per_minute?: number
  piece_rate?: number
  cost_type?: 'time' | 'piece'
  notes?: string
  metadata_json?: Record<string, unknown>
}

export interface ProductModelLinesResponse {
  sample: ProductModelSampleSpec
  standard: ProductModelSampleSpec
  materials: ProductModelMaterialLineInput[]
  processes: ProductModelProcessLineInput[]
}

export interface ProductModelSyncFromModulesRequest {
  keep_overrides?: boolean
  module_ids?: string[]
}

export interface ProductModelLinesUpdateRequest extends ProductModelLinesResponse {}

export interface ProductModelPreviewMaterialLine {
  module_id?: string | null
  module_code?: string | null
  module_name?: string | null
  source_kind: 'real' | 'bom' | 'virtual' | 'placeholder'
  source_ref_id?: string | null
  resolved_kind?: 'real' | 'bom' | 'virtual' | null
  resolved_ref_id?: string | null
  material_id?: string | null
  material_code?: string | null
  material_name?: string | null
  category?: string | null
  calculation_method: CalculationMethod
  base_quantity: string | number
  loss_rate: string | number
  used_quantity: string | number
  unit?: string | null
  bom_unit_price?: string | number | null
  total_cost?: string | number | null
  warnings: string[]
  /** Stage 2: 物料取价元数据（含税还原 / 生效期 / 价格来源 / 数据质量）。 */
  price_metadata?: {
    price_inclusive?: number | null
    price_exclusive?: number | null
    bom_unit_price_exclusive?: number | null
    tax_rate?: number | null
    tax_included_flag?: boolean | null
    purchase_entity_id?: string | null
    price_source?: string | null
    effective_from?: string | null
    effective_to?: string | null
    _data_quality?: 'green' | 'yellow' | 'red' | string | null
    _warnings?: string[] | null
  } | null
}

export interface ProductModelPreviewLaborLine {
  module_id?: string | null
  module_code?: string | null
  module_name?: string | null
  process_id?: string | null
  process_code?: string | null
  process_name?: string | null
  team_name?: string | null
  pricing_method: LaborPricingMethod
  measure_quantity: string | number
  cost_type?: 'time' | 'piece' | null
  base_minutes: string | number
  unit_minutes: string | number
  rate_per_minute?: string | number | null
  piece_rate?: string | number | null
  total_minutes?: string | number | null
  total_cost?: string | number | null
  warnings: string[]
}

export interface ProductModelPreviewResponse {
  width_mm: string | number
  height_mm: string | number
  quantity: string | number
  material_lines: ProductModelPreviewMaterialLine[]
  labor_lines: ProductModelPreviewLaborLine[]
  totals: Record<string, string | number>
  errors: string[]
}

export type ProductModelVersionKind = 'sample' | 'standard'
export type ProductModelVersionStatus = 'draft' | 'published' | 'archived'

export interface ProductModelVersionCreatePayload {
  version_kind: ProductModelVersionKind
  metadata_json?: Record<string, unknown>
}

export interface ProductModelVersionRead {
  id: string
  model_id: string
  version_kind: ProductModelVersionKind | string
  version_status: ProductModelVersionStatus | string
  version_label?: string | null
  published_at?: string | null
  published_by?: string | null
  metadata_json?: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface ProductModelVersionListItem {
  model_id: string
  model_code: string
  model_name: string
  model_status: string
  version_id: string
  version_kind: ProductModelVersionKind | string
  version_status: ProductModelVersionStatus | string
  version_label?: string | null
  created_at: string
  updated_at: string
  published_at?: string | null
}

export interface PaginatedProductModelVersionResponse extends PaginatedResponse<ProductModelVersionListItem> {}

export interface ProductModelVersionPublishPayload {
  published_by?: string
  note?: string
}

export interface ProductModelVersionPatchPayload {
  metadata_json: Record<string, unknown>
  operator_id?: string
}

export interface ModelVersionImageRead {
  index: number
  url: string
  filename?: string | null
  content_type?: string | null
}

export interface ModelVersionImagesResponse {
  version_id: string
  images: ModelVersionImageRead[]
}

export interface SkuModelVersionMappingCreatePayload {
  sku_code: string
  model_version_id: string
  source_system?: string
  is_active?: boolean
  metadata_json?: Record<string, unknown>
}

export interface SkuModelVersionMappingRead extends SkuModelVersionMappingCreatePayload {
  id: string
  created_at: string
  updated_at: string
}

export interface ProductModelSkuPreviewRequest {
  sku_code: string
  width_mm?: number
  height_mm?: number
  quantity?: number
}

export interface ProductModelSkuPreviewResponse extends ProductModelPreviewResponse {
  sku_code: string
  model_id: string
  model_code: string
  version_id: string
  version_label?: string | null
  parsed: Record<string, unknown>
}

export type DeriveTargetMode = 'create_new' | 'overwrite_draft'
export type DeriveApplyTo = 'materials' | 'processes' | 'both'

export interface DeriveRoundRule {
  step: string | number
  mode: 'round' | 'floor' | 'ceil'
}

export interface DeriveTemplateBase {
  template_kind: 'linear'
  calibrate_from_sample?: boolean
  fixed_quantity?: string | number
  coverage_ratio?: string | number
  min_total?: string | number
  max_total?: string | number
  rounding?: DeriveRoundRule
}

export interface DeriveTemplateMaterial extends DeriveTemplateBase {
  coefficient?: string | number
}

export interface DeriveTemplateProcess extends DeriveTemplateBase {
  coefficient?: string | number
  base_minutes?: string | number
}

export interface DeriveStandardRequest {
  target_mode: DeriveTargetMode
  target_standard_version_id?: string
  apply_to: DeriveApplyTo
}

export interface DeriveStandardResponse {
  standard_version_id: string
  created: boolean
  overwritten: boolean
  line_stats: Record<string, unknown>
}

export interface CloneModelFromVersionRequest {
  model_name?: string
  include_line_variants?: boolean
  operator_id?: string
}

export interface CloneModelFromVersionResponse {
  new_model_id: string
  new_model_code: string
  new_model_name: string
  new_standard_version_id: string
  new_standard_version_label?: string | null
}

// --- Line variants (version-scoped) + spec parser + dynamic BOM (MVP) ---

export interface SpecTokenExplanation {
  token: string
  source: string
  rule: string
}

export interface SpecParseRequest {
  spec_text: string
  sku_code?: string
}

export interface SpecParseResponse {
  tokens: string[]
  width_cm?: string | number | null
  height_cm?: string | number | null
  diameter_cm?: string | number | null
  area_m2?: string | number | null
  perimeter_m?: string | number | null
  explanations: SpecTokenExplanation[]
}

export type LineVariantAction = 'replace_bundle' | 'replace_self' | 'remove_self' | 'add_siblings'

export interface LineVariantCondition {
  spec_contains_any?: string[]
  spec_contains_all?: string[]
  width_between?: [string | number | null, string | number | null]
  height_between?: [string | number | null, string | number | null]
  area_between?: [string | number | null, string | number | null]
  perimeter_between?: [string | number | null, string | number | null]
}

export interface LineVariantItemPayload {
  sequence_order?: number
  material_kind: MaterialReferenceKind
  material_ref_id?: string | null
  material_code?: string | null
  material_name?: string | null
  unit_of_measure?: string | null
  calculation_method: CalculationMethod
  base_quantity: number
  fixed_quantity: number
  coverage_ratio: number
  loss_rate: number
  metadata_json?: Record<string, unknown>
}

export interface LineVariantItemRead extends LineVariantItemPayload {
  id: string
  sequence_order: number
  created_at: string
  updated_at: string
}

export interface LineVariantCreateRequest {
  version_id: string
  base_line_id: string
  priority?: number
  enabled?: boolean
  action?: LineVariantAction
  stop_on_hit?: boolean
  notes?: string
  conditions?: LineVariantCondition
  metadata_json?: Record<string, unknown>
  items?: LineVariantItemPayload[]
  operator_id?: string
}

export interface LineVariantUpdateRequest {
  base_line_id?: string
  priority?: number
  enabled?: boolean
  action?: LineVariantAction
  stop_on_hit?: boolean
  notes?: string
  conditions?: LineVariantCondition
  metadata_json?: Record<string, unknown>
  operator_id?: string
}

export interface LineVariantItemsReplaceRequest {
  items: LineVariantItemPayload[]
}

export interface LineVariantDetailRead {
  id: string
  version_id: string
  base_line_id: string
  priority: number
  enabled: boolean
  action: LineVariantAction
  stop_on_hit: boolean
  notes?: string | null
  conditions: Record<string, unknown>
  metadata: Record<string, unknown>
  items: LineVariantItemRead[]
  created_at: string
  updated_at: string
}

export interface BomLineRead {
  line_index: number
  source_type: 'base_line' | 'variant_item'
  base_line_id?: string | null
  variant_id?: string | null
  variant_item_id?: string | null
  material_kind: string
  material_ref_id?: string | null
  material_code?: string | null
  material_name?: string | null
  unit_of_measure?: string | null
  calculation_method: CalculationMethod
  base_quantity: string | number
  fixed_quantity: string | number
  coverage_ratio: string | number
  loss_rate: string | number
  computed_quantity: string | number
  bom_unit_price?: string | number | null
  line_cost?: string | number | null
  metadata: Record<string, unknown>
  /** Stage 2: 物料取价元数据（含税还原 / 生效期 / 价格来源 / 数据质量）。
   * 仅 ``material_kind in ('real','bom')`` 的行有；virtual 行通常为空。 */
  price_metadata?: {
    price_inclusive?: number | null
    price_exclusive?: number | null
    bom_unit_price_exclusive?: number | null
    tax_rate?: number | null
    tax_included_flag?: boolean | null
    purchase_entity_id?: string | null
    price_source?: string | null
    effective_from?: string | null
    effective_to?: string | null
    _data_quality?: 'green' | 'yellow' | 'red' | string | null
    _warnings?: string[] | null
  } | null
}

export interface BomGenerateRequest {
  spec_text: string
  model_version_id?: string
  sku_code?: string
  quantity?: number
  operator_id?: string
  include_disabled_variants?: boolean
}

export interface BomGenerateResponse {
  final_material_lines: BomLineRead[]
  trace: Record<string, unknown>
}

export type VariantTriggerType = 'sku_contains' | 'area_gte' | 'perimeter_gte'
export type VariantActionType = 'replace_material' | 'add_material'

export interface ModelVariantRuleRead {
  id: string
  model_id: string
  rule_name: string
  source_material_ref_id?: string | null
  trigger_type: VariantTriggerType
  trigger_value?: string | null
  action_type: VariantActionType
  target_material_ref_id?: string | null
  quantity_delta?: string | number | null
  status: string
  metadata_json?: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface ModelVariantRuleCreatePayload {
  rule_name: string
  source_material_ref_id: string
  trigger_type: VariantTriggerType
  trigger_value?: string
  action_type: VariantActionType
  target_material_ref_id: string
  quantity_delta?: number
  status?: string
  metadata_json?: Record<string, unknown>
}

export interface ModelVariantRuleUpdatePayload {
  rule_name?: string
  trigger_type?: VariantTriggerType
  trigger_value?: string
  action_type?: VariantActionType
  target_material_ref_id?: string
  quantity_delta?: number
  status?: string
  metadata_json?: Record<string, unknown>
}

export type ProcessChargingMode =
  | 'fixed'
  | 'count'
  | 'area'
  | 'perimeter'
  | 'width'
  | 'height'
  | 'long_side'
  | 'short_side'

export interface ProcessSummary {
  id: string
  process_code: string
  process_name: string
  description?: string | null
  category?: string | null
  team_name?: string | null
  charging_mode: ProcessChargingMode
  standard_rate?: string | number | null
  unit_of_measure?: string | null
  status: string
  is_active: boolean
  metadata_json?: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface ProcessDetail extends ProcessSummary {}

export interface ProcessQueryParams
  extends Record<string, string | number | boolean | undefined> {
  search?: string
  status?: string
  charging_mode?: string
  category?: string
  page?: number
  page_size?: number
}

export interface ProcessListResponse extends PaginatedResponse<ProcessSummary> {}

export interface ProcessCreatePayload {
  process_code: string
  process_name: string
  description?: string
  category?: string
  team_name?: string
  charging_mode?: ProcessChargingMode
  standard_rate?: number
  unit_of_measure?: string
  status?: string
  metadata_json?: Record<string, unknown>
  operator_id?: string
}

export interface ProcessUpdatePayload {
  process_name?: string
  description?: string
  category?: string
  team_name?: string
  charging_mode?: ProcessChargingMode
  standard_rate?: number
  unit_of_measure?: string
  status?: string
  metadata_json?: Record<string, unknown>
  operator_id?: string
}

export interface ProcessCopyPayload {
  process_code: string
  process_name: string
  status?: string
  operator_id?: string
}

export interface ProcessBatchStatusPayload {
  ids: string[]
  status: string
  operator_id?: string
}

export interface ProcessReference {
  id: string
  process_code: string
  process_name: string
  charging_mode: ProcessChargingMode
  standard_rate?: string | number | null
  unit_of_measure?: string | null
  team_name?: string | null
  category?: string | null
}

export interface ProcessModuleReferenceQuery {
  module_ids?: string[]
  search?: string
  status?: string
}

export interface CodeGenerateRequest {
  prefix: string
  width?: number
}

export interface CodeGenerateResponse {
  code: string
}

export interface ShipmentImportBatch {
  id: string
  file_name?: string | null
  file_hash: string
  export_date?: string | null
  requested_by?: string | null
  status: string
  total_rows: number
  inserted_rows: number
  skipped_rows: number
  exception_rows: number
  warnings_json?: Array<Record<string, unknown>>
  result_json?: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface ShipmentImportBatchListResponse extends PaginatedResponse<ShipmentImportBatch> {}

export type ShipmentLineStatus = 'processed' | 'pending'
export type ShipmentLineProcessedSource = 'bom_snapshot' | 'costing_result'
export type ShipmentLineMode = '2025' | '2026'

export interface ShipmentLineListItem {
  id: string
  batch_id: string
  row_index?: number | null
  shipment_no?: string | null
  order_no?: string | null
  product_link_id?: string | null
  completed_at?: string | null
  channel?: string | null
  sku_code?: string | null
  shop_spec_code?: string | null
  platform_sku_id?: string | null
  bundle_template_code?: string | null
  bundle_preset_selector?: string | null
  bound_model_code?: string | null
  bound_model_name?: string | null
  // 与 SkuMaster.bound_variant_label 同源：列表后端从 sku_master.metadata_json.bound_variant_code
  // 反查 ProductModelLineVariant.metadata_json.display_name 拼出 "麻感冰丝(KB8-001)"。
  // 仅"已绑定具体变体"的发货行有值；按"模型基础线"绑的（兜底）为 null，前端回退到 model 名展示。
  bound_variant_code?: string | null
  bound_variant_label?: string | null
  bound_version_label?: string | null
  spec_text?: string | null
  spec_hash?: string | null
  qty?: string | null
  revenue_amount?: string | null
  cost_total?: string | null
  bound_model_version_id?: string | null
  snapshot_model_version_id?: string | null
  needs_rebuild_snapshot?: boolean
  bom_snapshot_id?: string | null
  status: ShipmentLineStatus
  processed_source?: ShipmentLineProcessedSource | null
  mode?: ShipmentLineMode | null
  unresolved_reason?: string | null
  unresolved_message?: string | null
  suspected_mismatch?: boolean
  mismatch_warnings?: string[]
  suspected_size_anomaly?: boolean
  size_anomaly_detail?: string | null
  /**
   * SKU 主档「数据质量」状态。来自 SkuMaster.metadata.data_quality_status，
   * 目前只有 "spu_attribute_conflict"——即同一条码历史发货跨多个不相关品类。
   * 仅用于 UI 灰色 Tag 提示运营这是数据脏 SKU、自动绑定不可信。
   * mark_only：不影响成本计算流程。
   */
  sku_data_quality_status?: string | null

  // Jackyun v2 wms.order.query-info.page.v2 extensions (backend migration 0036).
  // All optional; older rows (pre-0036 backfill or Excel imports) may be null.
  erp_order_no?: string | null
  platform_order_no?: string | null
  sent_at?: string | null
  paid_at?: string | null
  ordered_at?: string | null
  check_started_at?: string | null
  order_status_name?: string | null
  trade_type?: number | null
  trade_type_msg?: string | null
  customer_name?: string | null
  logistic_no?: string | null
  logistic_name?: string | null
  logistic_type_name?: string | null
  logistic_code?: string | null
  warehouse_code?: string | null
  warehouse_name?: string | null
  wave_no?: string | null
  picker?: string | null
  packer?: string | null
  checker?: string | null
  seller_memo?: string | null
  buyer_memo?: string | null
  unit_price?: string | null
  unit_of_measure?: string | null
  category_name?: string | null
  goods_name?: string | null
  goods_no?: string | null
  is_gift?: boolean | null
  actual_qty?: string | null
}

export interface ShipmentLineListResponse extends PaginatedResponse<ShipmentLineListItem> {}

export interface ShipmentLineComputeSnapshotRequest {
  operator_id?: string | null
  overwrite: boolean
}

export type ShipmentLineComputeSnapshotAction = 'skipped' | 'created' | 'recomputed' | 'failed'

export interface ShipmentLineComputeSnapshotResponse {
  action: ShipmentLineComputeSnapshotAction
  shipment_line_id: string
  bom_snapshot_id?: string | null
  detail?: string | null
}

export interface ShipmentLineClearSnapshotsResponse {
  total_selected: number
  cleared_count: number
  skipped_not_found: number
  skipped_already_cleared: number
  skipped_missing_barcode: number
  errors: Array<Record<string, unknown>>
}

// Auto-resolve pending shipment lines (powers 「📦 业务管理 > 🚚 发货管理 > 🔴 待处理」 「⚡ 一键自动绑定」 banner)
// Backed by /api/planner/shipments/lines/auto-resolve/{preview,execute}
export interface ShipmentLinesAutoResolveRequest {
  days?: number
  limit?: number
  sku_codes?: string[]
  requested_by?: string
}

export interface ShipmentLinesAutoResolveCandidate {
  shipment_line_id: string
  shipment_line_count_for_sku: number
  sku_code: string
  channel?: string | null
  spec_text?: string | null
  model_id?: string | null
  model_code?: string | null
  model_name?: string | null
  version_id?: string | null
  version_label?: string | null
  match_method?: string | null
  matched_keyword?: string | null
}

export interface ShipmentLinesAutoResolvePreviewResponse {
  scanned_days: number
  total_pending_lines: number
  unique_unbound_skus: number
  candidates_count: number
  items: ShipmentLinesAutoResolveCandidate[]
}

export interface ShipmentLinesAutoResolveExecuteItem {
  shipment_line_id: string
  sku_code: string
  status: 'ok' | 'skipped_no_batch' | 'snapshot_failed' | 'error'
  bom_snapshot_id?: string | null
  error?: string | null
}

export interface ShipmentLinesAutoResolveExecuteResponse {
  scanned_days: number
  preview: ShipmentLinesAutoResolvePreviewResponse
  bound_skus_count: number
  skipped_already_bound: number
  snapshots_created: number
  lines_resolved: number
  exceptions_resolved: number
  bind_errors: Array<Record<string, unknown>>
  snapshot_errors: Array<Record<string, unknown>>
  items: ShipmentLinesAutoResolveExecuteItem[]
}

// Backed by GET /api/planner/shipments/lines/recent-stats
export interface ShipmentRecentBySourceItem {
  source_system: string | null
  count: number
}

export interface ShipmentRecentSyncRunItem {
  id: string
  source_system: string
  sync_type: string
  status: string
  inserted_rows: number
  updated_rows: number
  error_rows: number
  started_at?: string | null
  finished_at?: string | null
  triggered_by?: string | null
  error_message?: string | null
}

export interface ShipmentLinesRecentStatsResponse {
  window_hours: number
  as_of: string
  total_new_lines: number
  by_source_system: ShipmentRecentBySourceItem[]
  latest_runs: ShipmentRecentSyncRunItem[]
  recent_failed_runs_count?: number
  latest_failed_run?: ShipmentRecentSyncRunItem | null
}

export interface ShipmentCostingResult {
  id: string
  shipment_line_id: string
  mode: string
  qty?: string | null
  cost_total?: string | null
  cost_material_total?: string | null
  cost_process_total?: string | null
  cost_overhead_total?: string | null
  metadata?: Record<string, unknown>
}

export interface ShipmentInventoryDeductionLine {
  id: string
  shipment_line_id: string
  material_code?: string | null
  material_name?: string | null
  unit_of_measure?: string | null
  quantity?: string | null
  metadata?: Record<string, unknown>
}

export interface ShipmentProcessCostLine {
  process_code?: string | null
  process_name?: string | null
  team_name?: string | null
  pricing_method?: string | null
  measure_quantity?: string | null
  cost_type?: string | null
  base_minutes?: string | null
  unit_minutes?: string | null
  rate_per_minute?: string | null
  piece_rate?: string | null
  total_minutes?: string | null
  total_cost?: string | null
  warnings?: string[]
}

export interface ShipmentException {
  id: string
  batch_id: string
  shipment_line_id?: string | null
  row_index?: number | null
  shipment_no?: string | null
  completed_at?: string | null
  channel?: string | null
  sku_code?: string | null
  spec_text?: string | null
  spec_hash?: string | null
  bound_model_code?: string | null
  bound_model_name?: string | null
  spec_parsed?: boolean | null
  spec_width_cm?: string | null
  spec_height_cm?: string | null
  qty?: string | null
  revenue_amount?: string | null
  reason: string
  message?: string | null
  payload_json?: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface ShipmentExceptionRetryRequest {
  batch_id: string
  only_unresolved: boolean
  limit?: number | null
  operator_id: string
  reason: string
}

export interface ShipmentExceptionRetryResultItem {
  exception_id: string
  shipment_line_id?: string | null
  status: 'resolved' | 'unresolved'
  new_bom_snapshot_id?: string | null
  error?: string | null
}

export interface ShipmentExceptionRetryResponse {
  batch_id: string
  only_unresolved: boolean
  limit?: number | null
  processed: number
  resolved: number
  unresolved: number
  items: ShipmentExceptionRetryResultItem[]
}

export interface BomSnapshot {
  id: string
  batch_id: string
  shipment_line_id: string
  row_index?: number | null
  shipment_no?: string | null
  completed_at?: string | null
  channel?: string | null
  sku_code?: string | null
  spec_text?: string | null
  model_version_id?: string | null
  spec_hash?: string | null
  qty?: string | null
  revenue_amount?: string | null
  final_material_lines: Array<Record<string, unknown>>
  trace: Record<string, unknown>
  generated_at?: string | null
  created_at: string
  updated_at: string
}

export interface ShipmentProfitLineItem {
  shipment_line_id: string
  row_index?: number | null
  shipment_no?: string | null
  completed_at?: string | null
  channel?: string | null
  sku_code?: string | null
  spec_text?: string | null
  qty?: string | null
  revenue_amount?: string | null
  bom_snapshot_id?: string | null
  model_version_id?: string | null
  spec_hash?: string | null
  generated_at?: string | null
  cost_amount?: string | null
  gross_profit?: string | null
  gross_margin?: string | null
  status: 'costed' | 'missing_snapshot' | 'missing_costing' | 'unknown'
  note?: string | null
}

export interface ShipmentProfitLinesResponse {
  batch_id: string
  total_shipment_lines: number
  lines_with_bom_snapshots: number
  lines_missing_costing: number
  items: ShipmentProfitLineItem[]
  note?: string | null
}

export interface ReturnsRateBySkuItem {
  period: string
  channel?: string | null
  sku_code?: string | null
  shipped_qty: string
  returned_qty: string
  return_rate?: string | null
  shipped_amount: string
  refund_amount: string
  refund_rate?: string | null
  cost_quality?: CostQualityBadge | null
}

export interface ReturnsRateBySkuResponse {
  group_by: 'day' | 'month'
  start: string
  end: string
  items: ReturnsRateBySkuItem[]
  unmatched_returns_missing_order_no: number
}

export interface ProfitBySkuItem {
  period: string
  channel?: string | null
  sku_code?: string | null
  shipped_qty: string
  revenue_amount: string
  cost_amount: string
  gross_profit: string
  gross_margin?: string | null
  refund_amount: string
  returned_qty: string
  net_revenue: string
  net_profit: string
  net_margin?: string | null
  cost_quality?: CostQualityBadge | null
}

export interface ProfitBySkuResponse {
  group_by: 'day' | 'month'
  start: string
  end: string
  total_shipment_lines: number
  lines_with_bom_snapshots: number
  lines_missing_costing: number
  items: ProfitBySkuItem[]
  note?: string | null
}

export interface ProfitByModelItem {
  period: string
  channel?: string | null
  model_id: string
  model_code: string
  model_name: string
  version_id: string
  version_kind: string
  version_status: string
  version_label?: string | null
  version_count?: number
  shipped_qty: string
  revenue_amount: string
  cost_material_amount?: string
  cost_process_amount?: string
  cost_overhead_amount?: string
  cost_amount: string
  gross_profit: string
  gross_margin?: string | null
  refund_amount: string
  net_revenue: string
  net_profit: string
  net_margin?: string | null
  line_count?: number
  costed_line_count?: number
  missing_costing_line_count?: number
  cost_quality?: CostQualityBadge | null
}

export interface ProfitByModelResponse {
  group_by: 'day' | 'month'
  start: string
  end: string
  total_shipment_lines?: number
  mapped_model_lines?: number
  costed_lines?: number
  lines_missing_costing?: number
  items: ProfitByModelItem[]
  note?: string | null
}

export interface ModelInsightsSummaryItem {
  channel?: string | null
  model_id: string
  model_code: string
  model_name: string

  shipped_qty: string
  revenue_amount: string
  cost_material_amount: string
  cost_process_amount: string
  cost_overhead_amount: string
  cost_amount: string
  gross_profit: string
  gross_margin?: string | null
  returned_qty?: string | null
  refund_amount: string
  net_revenue: string
  net_profit: string
  net_margin?: string | null

  line_count?: number
  costed_line_count?: number
  missing_costing_line_count?: number

  top_version_id?: string | null
  top_version_kind?: string | null
  top_version_status?: string | null
  top_version_label?: string | null
  version_count?: number
  cost_quality?: CostQualityBadge | null
}

export interface ModelInsightsSummaryResponse {
  start: string
  end: string
  channel?: string | null
  total_shipment_lines: number
  mapped_model_lines: number
  costed_lines: number
  lines_missing_costing: number
  items: ModelInsightsSummaryItem[]
  note?: string | null
}

export interface ModelInsightsVersionStat {
  version_id: string
  version_kind?: string | null
  version_status?: string | null
  version_label?: string | null
  shipped_qty: string
  revenue_amount: string
  cost_material_amount: string
  cost_process_amount: string
  cost_overhead_amount: string
  cost_amount: string
  gross_profit: string
  gross_margin?: string | null
  line_count?: number
  costed_line_count?: number
  missing_costing_line_count?: number
}

export interface ModelInsightsDeductionLine {
  material_code?: string | null
  material_name?: string | null
  unit_of_measure?: string | null
  quantity?: string | null
  sources?: number | null
}

export interface ModelBaseMaterialLine {
  material_type?: string | null
  material_ref_id?: string | null
  material_code?: string | null
  material_name?: string | null
  unit_of_measure?: string | null
  calculation_method?: string | null
  base_quantity?: string | null
  loss_rate?: string | null
  unit_cost?: string | null
  sequence_order?: number | null
  notes?: string | null
}

export interface ModelBaseProcessLine {
  process_id?: string | null
  process_code?: string | null
  process_name?: string | null
  team_name?: string | null
  pricing_method?: string | null
  piece_rate?: string | null
  rate_per_minute?: string | null
  notes?: string | null
}

export interface ModelInsightsDetailResponse {
  start: string
  end: string
  channel?: string | null
  model_id: string
  model_code: string
  model_name: string
  selected_version_id?: string | null
  versions: ModelInsightsVersionStat[]

  sample_shipment_line_id?: string | null
  sample_completed_at?: string | null
  sample_sku_code?: string | null
  sample_spec_text?: string | null
  sample_qty?: string | null

  bom?: any | null
  persisted_deductions: ModelInsightsDeductionLine[]
  base_material_lines: ModelBaseMaterialLine[]
  base_process_lines: ModelBaseProcessLine[]
  note?: string | null
}

// -----------------------------
// Model usage aggregates (real shipped lines)
// -----------------------------

export interface ModelUsageMaterialItem {
  material_id?: string | null
  material_code?: string | null
  material_name?: string | null
  unit_of_measure?: string | null
  total_quantity: string
  line_count: number
}

export interface ModelUsageMaterialSummaryResponse {
  start: string
  end: string
  channel?: string | null
  model_code: string
  version_id?: string | null

  total_shipment_lines: number
  mapped_model_lines: number
  shipped_qty_total: string

  lines_with_deductions: number
  shipped_qty_covered: string

  items: ModelUsageMaterialItem[]
  note?: string | null
}

export interface ModelUsageProcessItem {
  process_code?: string | null
  process_name?: string | null
  team_name?: string | null
  total_minutes: string
  total_cost: string
  line_count: number
}

export interface ModelUsageProcessSummaryResponse {
  start: string
  end: string
  channel?: string | null
  model_code: string
  version_id?: string | null

  total_shipment_lines: number
  mapped_model_lines: number
  shipped_qty_total: string

  lines_with_process_details: number
  shipped_qty_covered: string

  items: ModelUsageProcessItem[]
  note?: string | null
}

export interface ReturnsRateByChannelItem {
  period: string
  channel?: string | null
  shipped_qty: string
  returned_qty: string
  return_rate?: string | null
  shipped_amount: string
  refund_amount: string
  refund_rate?: string | null
  shipment_lines_total: number
  cost_quality?: CostQualityBadge | null
}

export interface ReturnsRateByChannelResponse {
  group_by: 'day' | 'month'
  start: string
  end: string
  items: ReturnsRateByChannelItem[]
  unmatched_returns_missing_order_no: number
}

export interface ProfitByChannelItem {
  period: string
  channel?: string | null
  shipped_qty: string
  revenue_amount: string
  cost_amount: string
  gross_profit: string
  gross_margin?: string | null
  refund_amount: string
  returned_qty: string
  net_revenue: string
  net_profit: string
  net_margin?: string | null
  shipment_lines_total: number
  lines_with_bom_snapshots: number
  lines_missing_costing: number
  cost_quality?: CostQualityBadge | null
}

export interface ProfitByChannelResponse {
  group_by: 'day' | 'month'
  start: string
  end: string
  total_shipment_lines: number
  lines_with_bom_snapshots: number
  lines_missing_costing: number
  items: ProfitByChannelItem[]
  note?: string | null
}

export interface SalesLineItem {
  shipment_line_id: string
  batch_id?: string | null
  row_index?: number | null
  payment_at?: string | null
  completed_at?: string | null
  channel?: string | null
  sku_no?: string | null
  sku_name?: string | null
  spec_text?: string | null
  sku_code?: string | null
  sale_unit_price?: string | null
  qty?: string | null
  revenue_amount?: string | null
  cost_unit_price?: string | null
  cost_amount?: string | null
  order_no?: string | null
  product_link_id?: string | null
  logistics_company?: string | null
  logistics_no?: string | null
  mark?: string | null
  bundle_template_code?: string | null
  bundle_preset_selector?: string | null
  bundle_preset_phrase?: string | null
  bound_model_code?: string | null
  bound_model_name?: string | null
  // 与发货管理 / 台账 / SKU Master 同源：来自 sku_master.metadata_json.bound_variant_code。
  bound_variant_code?: string | null
  bound_variant_label?: string | null
  bom_snapshot_id?: string | null
  status: 'costed' | 'missing_snapshot' | 'missing_costing' | 'unknown'
  note?: string | null
  cost_quality?: CostQualityBadge | null
}

export interface SalesLinesResponse {
  start: string
  end: string
  total: number
  page: number
  page_size: number
  lines_with_bom_snapshots: number
  lines_missing_costing: number
  items: SalesLineItem[]
  note?: string | null
}

export interface SalesProfitDashboardKpis {
  shipped_qty: string
  revenue_amount: string
  shipment_lines_total: number
  costed_revenue_amount: string
  costed_lines: number
  lines_missing_costing: number
  costed_revenue_rate?: string | null
  cost_amount: string
  gross_profit: string
  gross_margin?: string | null
}

export interface SalesProfitDashboardSeriesItem {
  period: string
  shipped_qty: string
  revenue_amount: string
  costed_revenue_amount: string
  cost_amount: string
  gross_profit: string
  gross_margin?: string | null
  shipment_lines_total: number
  costed_lines: number
  lines_missing_costing: number
}

export interface SalesProfitDashboardTopSkuItem {
  sku_code: string
  spec_text?: string | null
  bound_model_code?: string | null
  bound_model_name?: string | null
  bundle_template_code?: string | null
  bundle_preset_selector?: string | null
  bundle_preset_phrase?: string | null
  shipped_qty: string
  revenue_amount: string
  cost_amount: string
  gross_profit: string
  gross_margin?: string | null
  shipment_lines_total: number
  costed_lines: number
}

export interface SalesProfitDashboardTopModelItem {
  model_code: string
  model_name?: string | null
  bundle_template_code?: string | null
  bundle_preset_selector?: string | null
  bundle_preset_phrase?: string | null
  shipped_qty: string
  revenue_amount: string
  cost_amount: string
  gross_profit: string
  gross_margin?: string | null
  shipment_lines_total: number
  costed_lines: number
}

export interface SalesProfitDashboardResponse {
  group_by: 'day' | 'week' | 'month'
  start: string
  end: string
  channel?: string | null
  top_n: number
  kpis: SalesProfitDashboardKpis
  series: SalesProfitDashboardSeriesItem[]
  top_skus_profit: SalesProfitDashboardTopSkuItem[]
  top_skus_loss: SalesProfitDashboardTopSkuItem[]
  top_models_profit: SalesProfitDashboardTopModelItem[]
  top_models_loss: SalesProfitDashboardTopModelItem[]
  note?: string | null
}

export interface AfterSalesImportBatch {
  id: string
  file_name?: string | null
  file_hash: string
  export_date?: string | null
  requested_by?: string | null
  status: string
  total_rows: number
  inserted_rows: number
  skipped_rows: number
  exception_rows: number
  warnings_json: Array<Record<string, unknown>>
  result_json: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface AfterSalesLineItem {
  id: string
  batch_id: string
  row_index: number
  after_sales_no?: string | null
  occurred_at?: string | null
  applied_at?: string | null
  shipment_completed_at?: string | null
  channel?: string | null
  reason?: string | null
  bound_model_code?: string | null
  bound_model_name?: string | null
  bound_version_label?: string | null
  order_no?: string | null
  product_link_id?: string | null
  product_code?: string | null
  product_name?: string | null
  spec_text?: string | null
  unit?: string | null
  sale_unit_price?: string | null
  return_qty?: string | null
  actual_return_qty?: string | null
  refund_amount?: string | null
  allocated_refund_amount?: string | null
  sku_code?: string | null
  normalize_warnings_json?: Array<Record<string, unknown>>
  metadata_json?: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface PaginatedAfterSalesLinesResponse {
  total: number
  page: number
  page_size: number
  items: AfterSalesLineItem[]
}

export interface AfterSalesDashboardKpis {
  shipped_qty: string
  shipped_amount: string
  returned_qty: string
  refund_amount: string
  return_rate?: string | null
  refund_rate?: string | null
  model_mapped_shipped_qty: string
  model_mapped_rate?: string | null
  model_unmapped_shipped_qty: string
  model_mapped_returned_qty: string
  model_unmapped_returned_qty: string
  model_mapped_returned_rate?: string | null
  matched_return_lines: number
  matched_return_lines_with_applied_at: number
  after_sales_lines_total: number
  after_sales_lines_matched_any_shipment: number
  after_sales_lines_unmatched: number
  after_sales_lines_unmatched_rate?: string | null
  after_sales_lines_missing_order_no: number
  after_sales_lines_missing_product_link_id: number
  after_sales_lines_missing_sku_code: number
}

export interface AfterSalesDashboardLagBucketItem {
  bucket: string
  returned_qty: string
  share?: string | null
}

export interface AfterSalesDashboardSeriesItem {
  period: string
  shipped_qty: string
  shipped_amount: string
  returned_qty: string
  refund_amount: string
  return_rate?: string | null
  refund_rate?: string | null
  model_mapped_shipped_qty?: string | null
  model_mapped_rate?: string | null
}

export interface AfterSalesDashboardTopReasonItem {
  reason: string
  returned_qty: string
  refund_amount: string
  share_returned_qty?: string | null
  share_refund_amount?: string | null
}

export interface AfterSalesDashboardTopModelItem {
  model_code: string
  model_name?: string | null
  bundle_template_code?: string | null
  bundle_preset_selector?: string | null
  bundle_preset_phrase?: string | null
  shipped_qty: string
  returned_qty: string
  return_rate?: string | null
}

export interface AfterSalesDashboardTopSkuItem {
  sku_code: string
  spec_text?: string | null
  shipped_qty: string
  returned_qty: string
  return_rate?: string | null
}

export interface AfterSalesDashboardTopLinkItem {
  product_link_id: string
  spec_text?: string | null
  shipped_qty: string
  returned_qty: string
  return_rate?: string | null
}

export interface AfterSalesDashboardResponse {
  group_by: 'day' | 'week' | 'month'
  start: string
  end: string
  kpis: AfterSalesDashboardKpis
  series: AfterSalesDashboardSeriesItem[]
  top_reasons: AfterSalesDashboardTopReasonItem[]
  top_models: AfterSalesDashboardTopModelItem[]
  top_skus: AfterSalesDashboardTopSkuItem[]
  top_links: AfterSalesDashboardTopLinkItem[]
  lag_buckets: AfterSalesDashboardLagBucketItem[]
}

export interface AfterSalesReasonOptionItem {
  reason: string
  count: number
}

export interface AfterSalesReasonOptionsResponse {
  items: AfterSalesReasonOptionItem[]
}

export interface AfterSalesModelOptionItem {
  model_code: string
  model_name?: string | null
  count: number
}

export interface AfterSalesModelOptionsResponse {
  items: AfterSalesModelOptionItem[]
}

export interface SkuMaster {
  id: string
  erp_sku_barcode: string
  platform_product_id?: string | null
  platform_sku_id?: string | null
  shop_spec_code?: string | null
  bundle_template_id?: string | null
  bundle_template_code?: string | null
  bundle_preset_selector?: string | null
  channel?: string | null
  product_name?: string | null
  product_code?: string | null
  spec_text?: string | null
  images_json?: Record<string, unknown>
  match_status?: string | null
  active_version_binding_id?: string | null
  active_model_version_id?: string | null
  bound_model_code?: string | null
  bound_model_name?: string | null
  bound_version_label?: string | null
  bound_version_kind?: string | null
  bound_version_status?: string | null
  // 显式落库的"最终绑定变体编码"（如 KB8-001）。绑定时（人工 / 自动）一并写入，
  // 列表/详情读路径直接用，不再靠 spec_text 反推。空表示"不指定变体"。
  bound_variant_code?: string | null
  // 形如 "麻感冰丝(KB8-001)" 或 "KB8-001"（无 display_name 时）。
  bound_variant_label?: string | null
  model_code_hint?: string | null
  erp_spec_hash?: string | null
  erp_parser_version?: string | null
  erp_dimensions?: Record<string, unknown>
  erp_tokens?: string[]
  last_shipment_spec_text?: string | null
  last_shipment_spec_hash?: string | null
  preparse_spec_text?: string | null
  preparse_spec_hash?: string | null
  preparse_parser_version?: string | null
  preparse_dimensions?: Record<string, unknown>
  preparse_tokens?: string[]
  preparse_has_dims?: boolean | null
  preparse_saved_at?: string | null
  preparse_saved_by?: string | null
  spec_mismatch?: boolean
  spec_mismatch_at?: string | null
  /** "spu_attribute_conflict" 或 null/undefined。由 data_quality_service nightly 重算。 */
  data_quality_status?: string | null
  data_quality_evidence?: SkuDataQualityEvidence | null
  data_quality_evaluated_at?: string | null
  source_updated_at?: string | null
  metadata_json?: Record<string, unknown>
  created_at: string
  updated_at: string
}

/** SKU "数据质量"评估 evidence —— 来自 backend data_quality_service。 */
export interface SkuDataQualityEvidence {
  version: number
  /** 命中的规则代号：'R1'（关键词冲突）/ 'R2'（高变异规格） */
  rules_hit: string[]
  total_lines: number
  distinct_specs: number
  unmatched_specs: number
  /** 已识别 model_code 列表（如 ['YS2','PI5']） */
  keyword_matched_models: string[]
  /** R1 的模型占比明细 [{model_code, lines, ratio}, ...] */
  model_share?: Array<{ model_code: string; lines: number; ratio: number }>
  /** 该 SKU TOP 6 个 variant，UI 展示用 */
  top_variants?: Array<{ spec: string; qty: number; top_model_code: string | null }>
  r2_exempt_due_to_single_model?: boolean
}

export interface ShopSkuMappingRead {
  id: string
  channel?: string | null
  platform_product_id?: string | null
  platform_sku_id: string
  erp_sku_barcode?: string | null
  shop_spec_code?: string | null
  production_process?: string | null
  match_status?: string | null
  match_method?: string | null
  source_updated_at?: string | null
  metadata_json?: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface SkuMasterScanResponse {
  sku_master: SkuMaster
  shop_skus: ShopSkuMappingRead[]
}

export interface SkuMasterListResponse extends PaginatedResponse<SkuMaster> {}

export interface SkuMasterImportResponse {
  total: number
  inserted: number
  updated: number
  skipped: number
  errors: Array<Record<string, unknown>>
}

export interface PublishedStandardModelCandidate {
  model_id: string
  model_code: string
  model_name: string
  published_version_id: string
  version_label?: string | null
}

export interface PublishedStandardModelCandidateListResponse {
  items: PublishedStandardModelCandidate[]
}

export interface SkuMasterBindByModelResponse {
  total_selected: number
  bound_count: number
  skipped_already_bound: number
  skipped_missing_barcode: number
  errors: Array<Record<string, unknown>>
}

export interface SkuMasterUnbindResponse {
  total_selected: number
  unbound_count: number
  skipped_missing_barcode: number
  errors: Array<Record<string, unknown>>
}

export interface SkuMasterGeneratePreparseAndSnapshotsResponse {
  total_selected: number
  parsed_count: number
  created_snapshots: number
  recomputed_snapshots: number
  skipped_snapshots: number
  failed_snapshots: number
  skipped_missing_barcode: number
  errors: Array<Record<string, unknown>>
}

export type SkuMasterBindPreviewItemStatus = 'can_bind' | 'skip_already_bound' | 'skip_missing_barcode' | 'hard_error'

export interface SkuMasterBindPreviewItem {
  sku_master_id: string
  sku_code?: string | null
  channel?: string | null
  sample_shipment_line_id?: string | null
  sample_completed_at?: string | null
  sample_spec_text?: string | null
  sample_spec_text_norm?: string | null
  status: SkuMasterBindPreviewItemStatus
  hard_errors: string[]
  warnings: string[]
  model_version_id?: string | null
  cost_total?: string | null
  inventory_line_count?: number | null
}

export interface SkuMasterBindPreviewResponse {
  total_selected: number
  can_bind: number
  skip_already_bound: number
  skip_missing_barcode: number
  hard_errors: number
  items: SkuMasterBindPreviewItem[]
}

export interface SkuMasterBindPreviewBulkResponse {
  batch_candidates: number
  can_bind: number
  skip_already_bound: number
  skip_missing_barcode: number
  hard_errors: number
  skipped_excluded: number
  has_more: boolean
  items: SkuMasterBindPreviewItem[]
}

export interface SkuMasterAutoBindPreviewItem {
  sku_master_id: string
  erp_sku_barcode: string
  channel?: string | null
  spec_text?: string | null
  shop_spec_code?: string | null
  variant_code_hint?: string | null
  model_code_hint: string
  model_id: string
  model_code: string
  model_name: string
  published_version_id: string
  version_label?: string | null
  match_method?: string | null
  matched_keyword?: string | null
}

export interface SkuMasterAutoBindPreviewResponse {
  total_unbound: number
  candidates: number
  items: SkuMasterAutoBindPreviewItem[]
}

export interface SkuMasterAutoBindExecuteResponse {
  preview: SkuMasterAutoBindPreviewResponse
  bound_count: number
  skipped_already_bound: number
  errors: Array<Record<string, unknown>>
}

export interface RecognitionKeywordsValidateResponse {
  ok: boolean
  normalized_keywords: string[]
  conflicts: Record<string, string>
}

// -----------------------------
// Taxonomy (admin dictionaries)
// -----------------------------

export interface TaxonomyScopeOptionsResponse {
  universal_scope: string
  default_scopes: string[]
}

export interface TaxonomyItemRead {
  id: string
  domain: string
  name: string
  scopes: string[]
  is_active: boolean
  sort_order: number
  source: string
  metadata: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface TaxonomyItemListResponse {
  items: TaxonomyItemRead[]
}

export interface TaxonomyMappingRead {
  id: string
  domain: string
  external_system: string
  external_value: string
  taxonomy_item_id: string
  taxonomy_item_name?: string | null
  created_at: string
  updated_at: string
}

export interface TaxonomyMappingListResponse {
  items: TaxonomyMappingRead[]
}

// -----------------------------
// Structure Standards (dictionary; backed by taxonomy domain=structure_standard)
// -----------------------------

export type StructureStandardStatus = 'active' | 'inactive'

export interface StructureStandardRead {
  id: string
  code: string
  name: string
  slots: string[]
  slot_display_names?: Record<string, string>
  slot_defs?: Array<{
    code: string
    name_cn?: string
    enabled?: boolean
    remark?: string
    driver_quantity?: string
  }>
  status: StructureStandardStatus
  updated_at?: string
}

export interface StructureStandardQueryParams extends Record<string, string | number | undefined> {
  search?: string
  status?: StructureStandardStatus | 'all'
  page?: number
  page_size?: number
}

export interface PaginatedStructureStandardResponse extends PaginatedResponse<StructureStandardRead> {}

// ===== Long-tail COGS rate strategy (Issue 28) =====

// v1.3 Cost Rate Hub (Migration 0038): rate_type / scope_type / scope_id /
// rate_basis / source / data_quality / effective_from / effective_to are all
// optional with safe defaults so legacy long-tail clients keep working.
export type CostRateType =
  | 'cogs'
  | 'labor_per_minute'
  | 'labor_per_piece'
  | 'labor_per_sqm'
  | 'overhead_rate'

export type CostRateScopeType = 'global' | 'category' | 'cost_center' | 'model'

export type CostRateRateBasis =
  | 'pct_of_revenue'
  | 'pct_of_cost'
  | 'per_minute'
  | 'per_piece'
  | 'per_sqm'

export type CostRateDataQuality = 'green' | 'yellow' | 'red'

export interface LongTailCogsRateStrategy {
  id: string
  category: string
  rate: number
  keywords: string[]
  priority: number
  enabled: boolean
  note?: string | null
  metadata?: Record<string, unknown>
  created_at?: string | null
  updated_at?: string | null
  // v1.3 Cost Rate Hub fields
  rate_type?: CostRateType
  scope_type?: CostRateScopeType
  scope_id?: string | null
  rate_basis?: CostRateRateBasis
  source?: string
  effective_from?: string | null
  effective_to?: string | null
  data_quality?: CostRateDataQuality | null
  cost_center_id?: string | null
  legal_entity_id?: string | null
  production_unit_id?: string | null
}

export interface LongTailCogsRateStrategyListResponse {
  items: LongTailCogsRateStrategy[]
  global_fallback_rate: number
}

export interface LongTailCogsRateStrategyUpsertPayload {
  category?: string
  rate?: number
  keywords?: string[]
  priority?: number
  enabled?: boolean
  note?: string | null
  actor?: string
  // v1.3 Cost Rate Hub upsert fields
  rate_type?: CostRateType
  scope_type?: CostRateScopeType
  scope_id?: string | null
  rate_basis?: CostRateRateBasis
  source?: string
  effective_from?: string | null
  effective_to?: string | null
  data_quality?: CostRateDataQuality | null
  cost_center_id?: string | null
  legal_entity_id?: string | null
  production_unit_id?: string | null
}

export interface LongTailCogsRateResolvePreviewPayload {
  sku_code?: string
  spec_text?: string
  product_name?: string
  long_tail_category?: string
  // v1.3 Cost Rate Hub overhead_rate preview
  rate_type?: CostRateType
  model_id?: string
  category?: string
  cost_center_id?: string
}

export type LongTailCogsRateResolveSource =
  | 'manual'
  | 'keyword'
  | 'default_strategy'
  | 'global_setting'
  | 'overhead_rate_hub'
  | 'hard_fallback'

export interface LongTailCogsRateResolvePreviewResponse {
  rate: number
  source: LongTailCogsRateResolveSource
  strategy_id?: string | null
  category?: string | null
  matched_keyword?: string | null
  // v1.3 Cost Rate Hub diagnostics
  hit_layer?: 'model' | 'category' | 'cost_center' | 'global' | 'hard_fallback' | null
  hit_scope_type?: CostRateScopeType | null
  hit_scope_id?: string | null
  data_quality?: CostRateDataQuality | null
}

