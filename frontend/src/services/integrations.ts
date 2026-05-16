/**
 * Service layer for ``/api/planner/integrations/*`` (generic external API hub).
 *
 * Currently powers the Jackyun shipment sync. Future vendors (POD, PDD, ...)
 * will plug into the same endpoints by passing a different ``source_system``.
 */
import { plannerClient, sanitizeParams } from './planner'

export interface SyncRunRead {
  id: string
  source_system: string
  sync_type: string
  api_method: string
  direction: string
  status: string
  total_rows: number
  inserted_rows: number
  updated_rows: number
  skipped_rows: number
  error_rows: number
  cursor_start: string | null
  cursor_end: string | null
  triggered_by: string | null
  started_at: string | null
  finished_at: string | null
  error_message: string | null
  request_params: Record<string, unknown>
  result: Record<string, unknown>
}

export interface DeadLetterRead {
  id: string
  source_system: string
  api_method: string | null
  record_type: string | null
  stage: string
  sync_run_id: string | null
  external_id: string | null
  external_line_id: string | null
  error_type: string | null
  error_message: string | null
  attempt: number
  status: string
  last_attempt_at: string | null
  metadata: Record<string, unknown>
}

export interface SyncRunDetailResponse {
  run: SyncRunRead
  dead_letters: DeadLetterRead[]
}

export interface DeadLetterListResponse {
  items: DeadLetterRead[]
  total: number
}

export interface TriggerSyncResponse {
  sync_run_id: string
  accepted: boolean
  mode: 'inline' | 'background'
  effective_start_modify_time: string | null
  note: string | null
  run: SyncRunRead | null
}

export interface JackyunShipmentSyncRequest {
  start_modify_time?: string | null
  end_modify_time?: string | null
  page_size?: number
  order_status_list?: number[] | null
  use_watermark?: boolean
  wait?: boolean
  triggered_by?: string | null
}

export const triggerJackyunShipmentSync = async (
  body: JackyunShipmentSyncRequest = {},
): Promise<TriggerSyncResponse> => {
  const { data } = await plannerClient.post<TriggerSyncResponse>(
    '/integrations/jackyun/sync/shipments',
    body,
  )
  return data
}

// 售后退款 (omsapi-business.refund.listrefund) — same shape as shipment except
// no order_status_list (refund namespace doesn't have an equivalent filter).
export interface JackyunRefundSyncRequest {
  start_modify_time?: string | null
  end_modify_time?: string | null
  page_size?: number
  use_watermark?: boolean
  wait?: boolean
  triggered_by?: string | null
}

export const triggerJackyunRefundSync = async (
  body: JackyunRefundSyncRequest = {},
): Promise<TriggerSyncResponse> => {
  const { data } = await plannerClient.post<TriggerSyncResponse>(
    '/integrations/jackyun/sync/refunds',
    body,
  )
  return data
}

export interface ListSyncRunsParams {
  source_system?: string
  sync_type?: string
  status?: string
  triggered_by?: string
  limit?: number
}

export const listSyncRuns = async (
  params: ListSyncRunsParams = {},
): Promise<SyncRunRead[]> => {
  const { data } = await plannerClient.get<SyncRunRead[]>('/integrations/sync-runs', {
    params: sanitizeParams(params as Record<string, unknown>),
  })
  return data
}

export const getSyncRunDetail = async (
  syncRunId: string,
): Promise<SyncRunDetailResponse> => {
  const { data } = await plannerClient.get<SyncRunDetailResponse>(
    `/integrations/sync-runs/${syncRunId}`,
  )
  return data
}

export interface ListDeadLettersParams {
  source_system?: string
  record_type?: string
  limit?: number
}

export const listDeadLetters = async (
  params: ListDeadLettersParams = {},
): Promise<DeadLetterListResponse> => {
  const { data } = await plannerClient.get<DeadLetterListResponse>('/integrations/dead-letters', {
    params: sanitizeParams(params as Record<string, unknown>),
  })
  return data
}

export interface ResolveDeadLetterPayload {
  resolved_by?: string | null
  note?: string | null
}

export const resolveDeadLetter = async (
  deadLetterId: string,
  body: ResolveDeadLetterPayload = {},
): Promise<{ resolved: boolean; dead_letter_id: string }> => {
  const { data } = await plannerClient.post<{ resolved: boolean; dead_letter_id: string }>(
    `/integrations/dead-letters/${deadLetterId}/resolve`,
    body,
  )
  return data
}

// ---------------------------------------------------------------------------
// Jackyun ERP goods master — Excel import (3-step wizard)
// See blueprint: DOC/costing/blueprints/jackyun_erp_goods_master_sync_backlog.md §10.2
// ---------------------------------------------------------------------------

export interface JackyunGoodsImportInspectResponse {
  sheet_name: string
  total_cols: number
  headers: string[]
  /** ``{col_idx_str: target_field}`` — auto-recognized mapping */
  auto_mapping: Record<string, string>
  unmatched_col_idx: number[]
  missing_required: string[]
  candidate_names: Record<string, string[]>
  physical_targets: string[]
  metadata_targets: string[]
  image_targets: string[]
  dimension_targets: string[]
  error: string | null
}

export interface JackyunGoodsImportTriggerResponse {
  sync_run_id: string
  status: string
  mode: 'dry_run' | 'commit'
  poll_url: string
}

export const inspectJackyunGoodsXlsx = async (
  file: File,
): Promise<JackyunGoodsImportInspectResponse> => {
  const form = new FormData()
  form.append('file', file)
  const { data } = await plannerClient.post<JackyunGoodsImportInspectResponse>(
    '/integrations/jackyun/goods/import-xlsx/inspect',
    form,
  )
  return data
}

export const dryRunJackyunGoodsXlsx = async (
  file: File,
  mapping: Record<string, string>,
  options: { requested_by?: string | null } = {},
): Promise<JackyunGoodsImportTriggerResponse> => {
  const form = new FormData()
  form.append('file', file)
  form.append('mapping', JSON.stringify(mapping))
  if (options.requested_by) form.append('requested_by', options.requested_by)
  const { data } = await plannerClient.post<JackyunGoodsImportTriggerResponse>(
    '/integrations/jackyun/goods/import-xlsx/dry-run',
    form,
  )
  return data
}

export const commitJackyunGoodsXlsx = async (
  file: File,
  mapping: Record<string, string>,
  options: { requested_by?: string | null; batch_size?: number } = {},
): Promise<JackyunGoodsImportTriggerResponse> => {
  const form = new FormData()
  form.append('file', file)
  form.append('mapping', JSON.stringify(mapping))
  if (options.requested_by) form.append('requested_by', options.requested_by)
  if (options.batch_size) form.append('batch_size', String(options.batch_size))
  const { data } = await plannerClient.post<JackyunGoodsImportTriggerResponse>(
    '/integrations/jackyun/goods/import-xlsx/commit',
    form,
  )
  return data
}
