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

export type CalculationMethod = 'area' | 'perimeter' | 'count' | 'width' | 'height'

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
}

export interface MaterialExportResponse {
  job_id?: string
  download_url?: string
  message?: string
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
  status?: string
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
}

export interface ProductModelQueryParams extends Record<string, string | number | undefined> {
  search?: string
  status?: string
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
  metadata: Record<string, unknown>
}

export interface BomGenerateRequest {
  spec_text: string
  model_version_id?: string
  sku_code?: string
  quantity?: number
  operator_id?: string
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

export type ProcessChargingMode = 'fixed' | 'count' | 'area' | 'perimeter' | 'width' | 'height'

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
  qty?: string | null
  revenue_amount?: string | null
  reason: string
  message?: string | null
  payload_json?: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface BomSnapshot {
  id: string
  batch_id: string
  shipment_line_id: string
  shipment_no?: string | null
  sku_code?: string | null
  model_version_id?: string | null
  spec_hash?: string | null
  qty?: string | null
  final_material_lines: Array<Record<string, unknown>>
  trace: Record<string, unknown>
  generated_at?: string | null
  created_at: string
  updated_at: string
}

export interface SkuMaster {
  id: string
  erp_sku_barcode: string
  platform_product_id?: string | null
  platform_sku_id?: string | null
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
  preparse_saved_at?: string | null
  preparse_saved_by?: string | null
  spec_mismatch?: boolean
  spec_mismatch_at?: string | null
  source_updated_at?: string | null
  metadata_json?: Record<string, unknown>
  created_at: string
  updated_at: string
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

export interface SkuMasterAutoBindPreviewItem {
  sku_master_id: string
  erp_sku_barcode: string
  channel?: string | null
  spec_text?: string | null
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

