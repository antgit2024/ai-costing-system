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
  unit?: string | null
  unit_price?: number
  currency: string
  supplier_code?: string | null
  supplier_name?: string | null
  usage_scope?: string | null
  is_active: boolean
  status: string
  bom_notes?: string | null
  source_created_at?: string | null
  source_updated_at?: string | null
  updated_at: string
  metadata_json?: Record<string, unknown>
}

export interface MaterialListResponse extends PaginatedResponse<Material> {}

export interface MaterialQueryParams extends Record<string, string | number | boolean | undefined> {
  page?: number
  page_size?: number
  search?: string
  category?: string
  material_type?: string
  status?: string
  is_active?: boolean
}

export interface MaterialStatusUpdatePayload {
  is_active?: boolean
  status?: string
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

