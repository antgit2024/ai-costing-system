import {
  Alert,
  Button,
  Card,
  Col,
  DatePicker,
  Descriptions,
  Drawer,
  Form,
  Input,
  message,
  Modal,
  Row,
  Segmented,
  Space,
  Table,
  Tabs,
  Tag,
  Typography,
  Upload,
} from 'antd'
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table'
import dayjs from 'dayjs'
import { useEffect, useMemo, useRef, useState } from 'react'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'

import {
  executeShipmentsFromPreview,
  fetchShipmentImportBatch,
  fetchShipmentBomSnapshots,
  fetchShipmentExceptions,
  fetchShipmentImportBatches,
  generateBom,
  parseSpec,
  fetchSkuMasterByBarcode,
  previewShipmentsXlsx,
  recomputeShipmentBomSnapshot,
  retryShipmentExceptions,
} from '@/services/planner'
import type {
  BomGenerateResponse,
  BomSnapshot,
  ShipmentException,
  ShipmentImportBatch,
  SkuMasterScanResponse,
} from '@/types/planner'

const { Title, Text } = Typography

const DEFAULT_PAGE_SIZE = 10
const MB = 1024 * 1024

const formatBytes = (bytes: number): string => {
  const b = Number(bytes || 0)
  if (!Number.isFinite(b) || b <= 0) return '0B'
  if (b < 1024) return `${b}B`
  if (b < MB) return `${(b / 1024).toFixed(1)}KB`
  return `${(b / MB).toFixed(2)}MB`
}

const tryGetHttpStatus = (err: any): number | null => {
  const n = Number(err?.response?.status)
  return Number.isFinite(n) ? n : null
}

const sleepMs = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms))

const isTimeoutError = (err: any): boolean => {
  const code = String(err?.code ?? '').toUpperCase()
  if (code === 'ECONNABORTED') return true
  const msg = String(err?.message ?? '').toLowerCase()
  return msg.includes('timeout') && msg.includes('exceeded')
}

const formatTime = (v?: string | null) => {
  if (!v) return '-'
  const d = dayjs(v)
  return d.isValid() ? d.format('YYYY-MM-DD HH:mm:ss') : String(v)
}

const safeString = (v: unknown): string => {
  if (v === null || v === undefined) return ''
  return String(v)
}

const formatShipmentBatchStatus = (statusRaw: unknown): { label: string; color?: string } => {
  const s0 = safeString(statusRaw).trim()
  const s = s0.toLowerCase()
  if (!s) return { label: '未知', color: 'default' }
  if (s === 'success') return { label: '成功', color: 'green' }
  if (s === 'processing') return { label: '处理中', color: 'blue' }
  if (s === 'failed') return { label: '失败', color: 'red' }
  if (s === 'pending' || s === 'queued') return { label: '排队中', color: 'default' }
  return { label: s0, color: 'default' }
}

const formatExceptionReason = (reasonRaw: unknown): { label: string; tooltip?: string } => {
  const r0 = safeString(reasonRaw).trim()
  const r = r0.toUpperCase()
  if (!r) return { label: '未知' }
  const map: Record<string, string> = {
    SKU_NOT_BOUND: 'SKU 未绑定标准版本',
    SPEC_EMPTY: '缺规格',
    SPEC_PARSE_FAILED: '规格解析失败',
    BOM_GENERATION_FAILED: 'BOM 生成失败',
    MODEL_VERSION_NOT_FOUND: '模型版本不存在',
    MODEL_VERSION_NOT_PUBLISHED: '模型版本未发布',
    MISSING_SKU_CODE: '缺条码',
    MISSING_SKU: '缺条码',
    UNKNOWN: '未知异常',
  }
  const label = map[r] ?? r0
  return { label: map[r] ? `${label}（${r}）` : label, tooltip: r0 }
}

const reasonStepHint = (reasonRaw: unknown): { stepLabel: string; step: 1 | 2 | 3 } | null => {
  const r = safeString(reasonRaw).trim().toUpperCase()
  if (!r) return null
  // 业务流程：1) 绑定 2) 规格解析 3) BOM生成
  if (r === 'SKU_NOT_BOUND' || r === 'MODEL_VERSION_NOT_FOUND' || r === 'MODEL_VERSION_NOT_PUBLISHED') {
    return { stepLabel: '绑定', step: 1 }
  }
  if (r === 'SPEC_EMPTY' || r === 'SPEC_PARSE_FAILED') {
    return { stepLabel: '规格解析', step: 2 }
  }
  if (r === 'BOM_GENERATION_FAILED') {
    return { stepLabel: 'BOM生成', step: 3 }
  }
  return null
}

const formatVersionStatus = (statusRaw: unknown): string => {
  const s0 = safeString(statusRaw).trim()
  const s = s0.toLowerCase()
  if (!s) return ''
  if (s === 'published') return '已发布'
  if (s === 'draft') return '草稿'
  if (s === 'deprecated') return '已废弃'
  return s0
}

const toNumberOrNull = (v: unknown): number | null => {
  if (v === null || v === undefined) return null
  if (typeof v === 'number' && Number.isFinite(v)) return v
  if (typeof v === 'string') {
    const s = v.trim()
    if (!s) return null
    const n = Number(s)
    return Number.isFinite(n) ? n : null
  }
  return null
}

const formatMoney = (v: unknown): string => {
  const n = toNumberOrNull(v)
  if (n === null) return '-'
  return n.toFixed(4)
}

const computeLineCost = (line: any): number | null => {
  const direct = toNumberOrNull(line?.line_cost)
  if (direct !== null) return direct
  const qty = toNumberOrNull(line?.computed_quantity ?? line?.quantity ?? line?.qty)
  const price = toNumberOrNull(line?.bom_unit_price ?? line?.metadata?.bom_unit_price)
  if (qty === null || price === null) return null
  return qty * price
}

const computeTotalCostFromLines = (lines: any[]): number | null => {
  if (!Array.isArray(lines) || lines.length === 0) return null
  let sum = 0
  let hasAny = false
  for (const l of lines) {
    const c = computeLineCost(l)
    if (c !== null) {
      sum += c
      hasAny = true
    }
  }
  return hasAny ? sum : null
}

const jsonPretty = (obj: unknown) => {
  try {
    return JSON.stringify(obj ?? {}, null, 2)
  } catch {
    return String(obj ?? '')
  }
}

const guessLineCode = (line: Record<string, unknown>) =>
  safeString(line.code ?? line.material_code ?? line.materialCode ?? line.reference_code)

const guessLineName = (line: Record<string, unknown>) =>
  safeString(line.name ?? line.material_name ?? line.materialName ?? line.description)

const guessLineQty = (line: Record<string, unknown>) =>
  safeString(line.quantity ?? line.computed_quantity ?? line.qty ?? line.base_quantity)

const guessLineUnit = (line: Record<string, unknown>) =>
  safeString(line.unit ?? line.unit_of_measure ?? line.unitOfMeasure ?? line.bom_unit)

const HandoffRowExpanded = (props: {
  skuCode: string
  channel?: string | null
  erpSpecText?: string | null
  preparseSpecText?: string | null
  shipmentSpecText?: string | null
  shipmentLineId?: string | null
  snapshotId?: string | null
  boundModelCode?: string | null
  boundModelName?: string | null
  boundVersionLabel?: string | null
  boundVersionStatus?: string | null
}) => {
  const [parseShipmentSpec, setParseShipmentSpec] = useState(false)
  const [parsePreparseSpec, setParsePreparseSpec] = useState(false)

  const skuQuery = useQuery({
    queryKey: ['sku-master', 'by-barcode', props.skuCode, props.channel],
    queryFn: () => fetchSkuMasterByBarcode(props.skuCode, { channel: props.channel ?? undefined, limit: 1 }),
    enabled: !!props.skuCode,
  })

  const skuMaster = (skuQuery.data as SkuMasterScanResponse | undefined)?.sku_master

  const preparseText =
    props.preparseSpecText ?? skuMaster?.preparse_spec_text ?? skuMaster?.spec_text ?? skuMaster?.last_shipment_spec_text ?? null
  const shipmentText = props.shipmentSpecText ?? null

  const preparseParseQuery = useQuery({
    queryKey: ['spec-parse', 'preparse', props.skuCode, preparseText],
    queryFn: () => parseSpec({ spec_text: String(preparseText ?? '') }),
    enabled: !!preparseText && parsePreparseSpec,
  })

  const shipmentParseQuery = useQuery({
    queryKey: ['spec-parse', 'shipment', props.skuCode, shipmentText],
    queryFn: () => parseSpec({ spec_text: String(shipmentText ?? '') }),
    enabled: !!shipmentText && parseShipmentSpec,
  })

  const renderDims = (dims: any) => {
    if (!dims || typeof dims !== 'object') return '-'
    const w = dims.width_cm ?? dims.width ?? null
    const h = dims.height_cm ?? dims.height ?? null
    const d = dims.diameter_cm ?? dims.diameter ?? null
    const a = dims.area_m2 ?? dims.area ?? null
    const p = dims.perimeter_m ?? dims.perimeter ?? null
    const parts = []
    if (w !== null || h !== null) parts.push(`宽=${w ?? '-'}cm 高=${h ?? '-'}cm`)
    if (d !== null) parts.push(`直径=${d}cm`)
    if (a !== null) parts.push(`面积=${a}㎡`)
    if (p !== null) parts.push(`周长=${p}m`)
    return parts.length ? parts.join('；') : '-'
  }

  return (
    <Row gutter={[16, 16]}>
      <Col xs={24} lg={12}>
        <Card size="small" title="前置（SKU 主档：绑定 + 预解析缓存）">
          {skuQuery.isFetching ? <Text type="secondary">加载中…</Text> : null}
          {skuQuery.isError ? (
            <Text type="danger">SKU 主档加载失败：{String((skuQuery.error as any)?.message ?? 'unknown')}</Text>
          ) : null}
          <Descriptions bordered size="small" column={1}>
            <Descriptions.Item label="SKU（条码）">{props.skuCode}</Descriptions.Item>
            <Descriptions.Item label="绑定模型">
              {props.boundModelCode || skuMaster?.bound_model_code ? (
                <Space size={6}>
                  <Tag color="blue">{props.boundModelCode ?? skuMaster?.bound_model_code}</Tag>
                  <span style={{ color: '#666' }}>{props.boundModelName ?? skuMaster?.bound_model_name}</span>
                </Space>
              ) : (
                <Text type="warning">未绑定</Text>
              )}
            </Descriptions.Item>
            <Descriptions.Item label="版本">
              {props.boundVersionLabel ?? skuMaster?.bound_version_label ?? '-'}{' '}
              <span style={{ color: '#999' }}>
                {formatVersionStatus(props.boundVersionStatus ?? skuMaster?.bound_version_status ?? '')}
              </span>
            </Descriptions.Item>
            <Descriptions.Item label="预解析 spec_text">{preparseText ? <Text code>{preparseText}</Text> : '-'}</Descriptions.Item>
            <Descriptions.Item label="预解析 dimensions（已落库）">
              {renderDims(skuMaster?.preparse_dimensions)}
            </Descriptions.Item>
            <Descriptions.Item label="预解析 tokens（已落库）">
              {Array.isArray(skuMaster?.preparse_tokens) && skuMaster!.preparse_tokens!.length ? (
                <Text code>{skuMaster!.preparse_tokens!.slice(0, 24).join(' ')}</Text>
              ) : (
                '-'
              )}
            </Descriptions.Item>
            <Descriptions.Item label="解析（按 spec/parse 现场计算）">
              <Space>
                <Button size="small" onClick={() => setParsePreparseSpec(true)} disabled={!preparseText}>
                  解析预解析 spec_text
                </Button>
                <Text type="secondary">
                  {preparseParseQuery.isFetching
                    ? '解析中…'
                    : preparseParseQuery.data
                      ? `dims=${renderDims((preparseParseQuery.data as any)?.dimensions)}`
                      : ''}
                </Text>
              </Space>
            </Descriptions.Item>
          </Descriptions>
        </Card>
      </Col>

      <Col xs={24} lg={12}>
        <Card size="small" title="后置（发货导入：交易规格解析 + 快照/异常）">
          <Descriptions bordered size="small" column={1}>
            <Descriptions.Item label="数据来源">
              <Space size={6} wrap>
                {props.shipmentLineId ? <Tag color="blue">shipment_line_id 已关联</Tag> : <Tag>shipment_line_id 缺失</Tag>}
                {props.snapshotId ? <Tag color="green">已落库快照</Tag> : <Tag>未落库快照</Tag>}
                {props.snapshotId ? (
                  <Text type="secondary">snapshot_id={String(props.snapshotId)}</Text>
                ) : null}
              </Space>
            </Descriptions.Item>
            <Descriptions.Item label="交易规格（本批次）">
              {shipmentText ? (
                <Text code>{shipmentText}</Text>
              ) : (
                <Text type="warning">
                  （无：无法与“前置”对比。常见原因：旧快照缺 shipment_line_id，后端无法回填本批次交易规格；或该行原始数据缺规格应进入异常队列）
                </Text>
              )}
            </Descriptions.Item>
            <Descriptions.Item label="解析（按 spec/parse 现场计算）">
              <Space>
                <Button size="small" onClick={() => setParseShipmentSpec(true)} disabled={!shipmentText}>
                  解析交易规格
                </Button>
                <Text type="secondary">
                  {shipmentParseQuery.isFetching
                    ? '解析中…'
                    : shipmentParseQuery.data
                      ? `dims=${renderDims((shipmentParseQuery.data as any)?.dimensions)}`
                      : ''}
                </Text>
              </Space>
            </Descriptions.Item>
          </Descriptions>
          <div style={{ marginTop: 10 }}>
            <Text type="secondary">
              说明：左侧是“前置主档缓存/绑定（参考）”，右侧是“本批次交易规格（用于计价/扣库）”。系统以本批次交易规格为准：若为空会进入异常；若不为空则会按它解析并生成快照（可在“快照结果/快照详情”查看计价与扣库清单）。
            </Text>
          </div>
        </Card>
      </Col>
    </Row>
  )
}

const ShipmentMonitorPage = () => {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [batchPage, setBatchPage] = useState(1)
  const [batchPageSize, setBatchPageSize] = useState(DEFAULT_PAGE_SIZE)
  const [selectedBatchId, setSelectedBatchId] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<'batches' | 'handoff' | 'exceptions' | 'snapshots'>('batches')

  const [uploadDrawerOpen, setUploadDrawerOpen] = useState(false)
  const [batchesDrawerOpen, setBatchesDrawerOpen] = useState(false)

  const [uploading, setUploading] = useState(false)
  const [uploadFile, setUploadFile] = useState<File | null>(null)
  const [uploadExportDate, setUploadExportDate] = useState<string | undefined>(
    dayjs().format('YYYY-MM-DD'),
  )
  const [uploadRequestedBy, setUploadRequestedBy] = useState<string>('planner_user')
  const [uploadExecuteMode, setUploadExecuteMode] = useState<'2025' | '2026'>('2026')
  const [previewData, setPreviewData] = useState<any>(null)
  const [precheckDrawerOpen, setPrecheckDrawerOpen] = useState(false)
  const [queueDrawerOpen, setQueueDrawerOpen] = useState(false)
  const [activeQueueRow, setActiveQueueRow] = useState<any>(null)
  const [queueBomPreview, setQueueBomPreview] = useState<BomGenerateResponse | null>(null)

  const [exceptionResolved, setExceptionResolved] = useState<'unresolved' | 'resolved' | 'all'>(
    'unresolved',
  )
  const [exceptionLimit, setExceptionLimit] = useState(200)
  const [retryingExceptions, setRetryingExceptions] = useState(false)

  const [snapshotForm] = Form.useForm()
  const [snapshotsUseCurrentBatch, setSnapshotsUseCurrentBatch] = useState(true)
  const [snapshotQuery, setSnapshotQuery] = useState<{
    batch_id?: string
    sku_code?: string
    shipment_no?: string
    spec_hash?: string
    limit?: number
  }>({ limit: 200 })

  const [snapshotDrawerOpen, setSnapshotDrawerOpen] = useState(false)
  const [activeSnapshot, setActiveSnapshot] = useState<BomSnapshot | null>(null)
  const [recomputingSnapshotId, setRecomputingSnapshotId] = useState<string | null>(null)

  // Handoff view (SKU master preparse/binding ↔ shipment rows in current batch)
  const [handoffMode, setHandoffMode] = useState<'exceptions' | 'snapshots' | 'both'>('exceptions')
  const [handoffLimit, setHandoffLimit] = useState(200)
  const [handoffExceptionResolved, setHandoffExceptionResolved] = useState<'unresolved' | 'resolved' | 'all'>('unresolved')
  const [handoffExpandedRowKeys, setHandoffExpandedRowKeys] = useState<Array<string>>([])

  const batchesQuery = useQuery({
    queryKey: ['shipments', 'import-batches', batchPage, batchPageSize],
    queryFn: () => fetchShipmentImportBatches({ page: batchPage, page_size: batchPageSize }),
    placeholderData: keepPreviousData,
  })

  const batches = batchesQuery.data?.items ?? []
  const totalBatches = batchesQuery.data?.total ?? 0

  // ERP-like default: pick latest batch automatically
  useEffect(() => {
    if (selectedBatchId) return
    const firstId = (batches?.[0] as any)?.id
    if (firstId) setSelectedBatchId(String(firstId))
  }, [batches, selectedBatchId])

  const selectedBatchQuery = useQuery({
    queryKey: ['shipments', 'import-batch', selectedBatchId],
    queryFn: () => fetchShipmentImportBatch(String(selectedBatchId)),
    enabled: !!selectedBatchId,
  })
  const selectedBatch = selectedBatchQuery.data

  const exceptionsQuery = useQuery({
    queryKey: ['shipments', 'exceptions', selectedBatchId, exceptionResolved, exceptionLimit],
    queryFn: () =>
      fetchShipmentExceptions({
        batch_id: selectedBatchId || undefined,
        resolved:
          exceptionResolved === 'all'
            ? undefined
            : exceptionResolved === 'resolved'
              ? true
              : false,
        limit: exceptionLimit,
      }),
    enabled: batchesDrawerOpen && activeTab === 'exceptions',
  })

  const retryExceptionsMutation = useMutation({
    mutationFn: async () => {
      const batchId = (selectedBatchId || '').trim()
      if (!batchId) throw new Error('请先填写/选择 batch_id')
      const operatorId = (uploadRequestedBy || '').trim() || 'planner_user'
      // MVP: 使用固定 reason，避免额外弹窗/输入；后端要求非空且 <=128
      const reason = 'ui_retry_unresolved'
      return await retryShipmentExceptions({
        batch_id: batchId,
        only_unresolved: true,
        limit: exceptionLimit || undefined,
        operator_id: operatorId,
        reason,
      })
    },
    onSuccess: (res) => {
      message.success(`已触发重试：processed=${res.processed}, resolved=${res.resolved}, unresolved=${res.unresolved}`)
      exceptionsQuery.refetch()
      // retry 会新建 bom_snapshot，顺带刷新快照 tab 的数据缓存
      queryClient.invalidateQueries({ queryKey: ['shipments', 'bom-snapshots'] })
    },
    onError: (err: any) => {
      message.error(`重试失败：${err?.response?.data?.detail ?? err?.message ?? 'unknown error'}`)
    },
    onSettled: () => {
      setRetryingExceptions(false)
    },
  })

  const snapshotsQuery = useQuery({
    queryKey: ['shipments', 'bom-snapshots', snapshotQuery],
    queryFn: () =>
      fetchShipmentBomSnapshots({
        ...snapshotQuery,
        ...(snapshotsUseCurrentBatch && selectedBatchId ? { batch_id: selectedBatchId } : {}),
      }),
    enabled: batchesDrawerOpen && activeTab === 'snapshots',
  })

  const handoffExceptionsQuery = useQuery({
    queryKey: ['shipments', 'handoff', 'exceptions', selectedBatchId, handoffExceptionResolved, handoffLimit],
    queryFn: () =>
      fetchShipmentExceptions({
        batch_id: selectedBatchId || undefined,
        resolved:
          handoffExceptionResolved === 'all'
            ? undefined
            : handoffExceptionResolved === 'resolved'
              ? true
              : false,
        limit: Math.max(Math.min(handoffLimit, 1000), 1),
      }),
    enabled:
      batchesDrawerOpen &&
      activeTab === 'handoff' &&
      !!selectedBatchId &&
      (handoffMode === 'exceptions' || handoffMode === 'both'),
  })

  const handoffSnapshotsQuery = useQuery({
    queryKey: ['shipments', 'handoff', 'bom-snapshots', selectedBatchId, handoffLimit],
    queryFn: () =>
      fetchShipmentBomSnapshots({
        batch_id: selectedBatchId || undefined,
        limit: Math.max(Math.min(handoffLimit, 1000), 1),
      }),
    enabled:
      batchesDrawerOpen &&
      activeTab === 'handoff' &&
      !!selectedBatchId &&
      (handoffMode === 'snapshots' || handoffMode === 'both'),
  })

  type HandoffRow = {
    key: string
    shipment_line_id?: string | null
    row_index?: number | null
    shipment_no?: string | null
    channel?: string | null
    completed_at?: string | null
    sku_code?: string | null
    spec_text?: string | null
    spec_hash?: string | null
    qty?: string | number | null
    revenue_amount?: string | number | null
    snapshot?: BomSnapshot
    exception?: ShipmentException
  }

  const handoffRows = useMemo<HandoffRow[]>(() => {
    const snaps = handoffMode === 'snapshots' || handoffMode === 'both' ? handoffSnapshotsQuery.data ?? [] : []
    const excs = handoffMode === 'exceptions' || handoffMode === 'both' ? handoffExceptionsQuery.data ?? [] : []
    const byLineId = new Map<string, HandoffRow>()

    for (const s of snaps) {
      const lineId = safeString((s as any).shipment_line_id).trim()
      const key = lineId || `snap:${safeString(s.id)}`
      const row: HandoffRow = {
        key,
        shipment_line_id: lineId || null,
        row_index: (s as any).row_index ?? null,
        shipment_no: (s as any).shipment_no ?? null,
        channel: (s as any).channel ?? null,
        completed_at: (s as any).completed_at ?? null,
        sku_code: (s as any).sku_code ?? null,
        spec_text: (s as any).spec_text ?? null,
        spec_hash: (s as any).spec_hash ?? null,
        qty: (s as any).qty ?? null,
        revenue_amount: (s as any).revenue_amount ?? null,
        snapshot: s,
      }
      if (lineId) byLineId.set(lineId, row)
      else byLineId.set(key, row)
    }

    for (const e of excs) {
      const lineId = safeString((e as any).shipment_line_id).trim()
      const existing = lineId ? byLineId.get(lineId) : undefined
      if (existing) {
        existing.exception = e
        continue
      }
      const key = lineId || `exc:${safeString(e.id)}`
      byLineId.set(key, {
        key,
        shipment_line_id: lineId || null,
        row_index: (e as any).row_index ?? null,
        shipment_no: (e as any).shipment_no ?? null,
        channel: (e as any).channel ?? null,
        completed_at: (e as any).completed_at ?? null,
        sku_code: (e as any).sku_code ?? null,
        spec_text: (e as any).spec_text ?? null,
        spec_hash: (e as any).spec_hash ?? null,
        qty: (e as any).qty ?? null,
        revenue_amount: (e as any).revenue_amount ?? null,
        exception: e,
      })
    }

    const rows = Array.from(byLineId.values())
    // Prefer stable sort by row_index asc; fallback to key
    rows.sort((a, b) => {
      const ai = a.row_index ?? null
      const bi = b.row_index ?? null
      if (ai !== null && bi !== null) return ai - bi
      if (ai !== null && bi === null) return -1
      if (ai === null && bi !== null) return 1
      return a.key.localeCompare(b.key)
    })
    return rows
  }, [handoffExceptionsQuery.data, handoffMode, handoffSnapshotsQuery.data])

  // When user changes current batch, keep snapshots form in sync (default: filter by current batch).
  const prevSelectedBatchIdRef = useRef<string | null>(null)
  useEffect(() => {
    const prev = prevSelectedBatchIdRef.current
    if (prev !== selectedBatchId) {
      prevSelectedBatchIdRef.current = selectedBatchId
      if (snapshotsUseCurrentBatch) {
        snapshotForm.setFieldsValue({ batch_id: selectedBatchId ?? undefined })
      }
    }
  }, [selectedBatchId, snapshotForm, snapshotsUseCurrentBatch])

  const handleQueuePreviewBom = async (row: any) => {
    try {
      setActiveQueueRow(row)
      setQueueDrawerOpen(true)
      setQueueBomPreview(null)
      const specText = safeString(row?.spec_text)
      const skuCode = safeString(row?.sku_code)
      const qty0 = Number(row?.qty ?? 1)
      const qty = Number.isFinite(qty0) && qty0 > 0 ? qty0 : 1
      const res = await generateBom({ spec_text: specText, sku_code: skuCode, quantity: qty })
      setQueueBomPreview(res)
    } catch (err: any) {
      message.error(`BOM预览失败：${err?.response?.data?.detail ?? err?.message ?? 'unknown error'}`)
    }
  }

  const batchColumns: ColumnsType<ShipmentImportBatch> = [
    {
      title: '导入时间',
      dataIndex: 'created_at',
      width: 170,
      render: (v) => formatTime(v),
    },
    {
      title: '导出日期',
      dataIndex: 'export_date',
      width: 120,
      render: (v) => safeString(v) || '-',
    },
    {
      title: '文件名',
      dataIndex: 'file_name',
      ellipsis: true,
      render: (v) => safeString(v) || '-',
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 120,
      render: (v) => {
        const x = formatShipmentBatchStatus(v)
        return <Tag color={x.color}>{x.label}</Tag>
      },
    },
    {
      title: '总行',
      dataIndex: 'total_rows',
      width: 80,
    },
    {
      title: '写入',
      dataIndex: 'inserted_rows',
      width: 80,
    },
    {
      title: '跳过',
      dataIndex: 'skipped_rows',
      width: 80,
    },
    {
      title: '异常',
      dataIndex: 'exception_rows',
      width: 80,
    },
  ]

  const exceptionColumns: ColumnsType<ShipmentException> = [
    {
      title: '时间',
      dataIndex: 'created_at',
      width: 170,
      render: (v) => formatTime(v),
    },
    {
      title: '发货单号',
      dataIndex: 'shipment_no',
      width: 160,
      ellipsis: true,
      render: (v) => safeString(v) || '-',
    },
    {
      title: '货品条码',
      dataIndex: 'sku_code',
      width: 160,
      ellipsis: true,
      render: (v) => safeString(v) || '-',
    },
    {
      title: '交易规格',
      dataIndex: 'spec_text',
      ellipsis: true,
      render: (v) => safeString(v) || '-',
    },
    {
      title: '数量',
      dataIndex: 'qty',
      width: 90,
      render: (v) => safeString(v) || '-',
    },
    {
      title: '金额',
      dataIndex: 'revenue_amount',
      width: 110,
      render: (v) => safeString(v) || '-',
    },
    {
      title: '原因',
      dataIndex: 'reason',
      width: 180,
      render: (v) => {
        const x = formatExceptionReason(v)
        return <span title={x.tooltip}>{x.label || '-'}</span>
      },
    },
    {
      title: '消息',
      dataIndex: 'message',
      ellipsis: true,
      render: (v) => safeString(v) || '-',
    },
    {
      title: '操作',
      key: 'actions',
      width: 120,
      render: (_, record) => {
        const reason = safeString(record?.reason)
        const sku = safeString(record?.sku_code).trim()
        if (reason === 'SKU_NOT_BOUND' && sku) {
          return (
            <Button
              size="small"
              type="link"
              onClick={() => navigate(`/costing/sku-master?search=${encodeURIComponent(sku)}`)}
            >
              去绑定
            </Button>
          )
        }
        return null
      },
    },
  ]

  const snapshotColumns: ColumnsType<BomSnapshot> = [
    {
      title: '生成时间',
      dataIndex: 'generated_at',
      width: 170,
      render: (v) => formatTime(v),
    },
    {
      title: '发货单号',
      dataIndex: 'shipment_no',
      width: 160,
      ellipsis: true,
      render: (v) => safeString(v) || '-',
    },
    {
      title: '货品条码',
      dataIndex: 'sku_code',
      width: 140,
      ellipsis: true,
      render: (v) => safeString(v) || '-',
    },
    {
      title: 'qty',
      dataIndex: 'qty',
      width: 90,
      render: (v) => safeString(v) || '-',
    },
    {
      title: 'model_version_id',
      dataIndex: 'model_version_id',
      width: 220,
      ellipsis: true,
      render: (v) => safeString(v) || '-',
    },
    {
      title: '明细行数',
      dataIndex: 'final_material_lines',
      width: 90,
      render: (v) => (Array.isArray(v) ? v.length : 0),
    },
    {
      title: '操作',
      key: 'actions',
      width: 180,
      render: (_, record) => (
        <Space size={8}>
          <Button
            size="small"
            onClick={() => {
              setActiveSnapshot(record)
              setSnapshotDrawerOpen(true)
            }}
          >
            查看
          </Button>
          <Button
            size="small"
            loading={recomputingSnapshotId === record.id}
            onClick={async () => {
              try {
                setRecomputingSnapshotId(record.id)
                const updated = await recomputeShipmentBomSnapshot(record.id, {
                  operator_id: uploadRequestedBy?.trim() || undefined,
                })
                message.success('回填完成：已重算工序+成本并更新快照')
                // refresh list + open updated snapshot
                snapshotsQuery.refetch()
                setActiveSnapshot(updated)
                setSnapshotDrawerOpen(true)
              } catch (err: any) {
                message.error(`回填失败：${err?.response?.data?.detail ?? err?.message ?? 'unknown error'}`)
              } finally {
                setRecomputingSnapshotId(null)
              }
            }}
          >
            回填
          </Button>
        </Space>
      ),
    },
  ]

  const snapshotLines = useMemo(() => {
    if (!activeSnapshot?.final_material_lines) return []
    const rows = activeSnapshot.final_material_lines
    return rows.map((line, idx) => {
      const obj = (line ?? {}) as Record<string, unknown>
      return {
        key: `${activeSnapshot.id}-${idx}`,
        source: safeString(obj.source) || safeString(obj.line_source) || '-',
        code: guessLineCode(obj) || '-',
        name: guessLineName(obj) || '-',
        quantity: guessLineQty(obj) || '-',
        unit: guessLineUnit(obj) || '-',
        bom_unit_price: (obj as any).bom_unit_price ?? ((obj as any).metadata ?? {})?.bom_unit_price ?? null,
        line_cost: (obj as any).line_cost ?? null,
        raw: obj,
      }
    })
  }, [activeSnapshot])

  const snapshotTotalCost = useMemo(() => {
    if (!activeSnapshot) return null
    const traceCost = (activeSnapshot as any)?.trace?.costing?.total_cost
    const n = toNumberOrNull(traceCost)
    if (n !== null) return n
    return computeTotalCostFromLines((activeSnapshot as any)?.final_material_lines ?? [])
  }, [activeSnapshot])

  const snapshotLineCols: ColumnsType<any> = [
    { title: '来源', dataIndex: 'source', width: 110 },
    { title: '编码', dataIndex: 'code', width: 140, ellipsis: true },
    { title: '名称', dataIndex: 'name', ellipsis: true },
    { title: '数量', dataIndex: 'quantity', width: 120 },
    { title: '单位', dataIndex: 'unit', width: 90 },
    { title: 'BOM单价', dataIndex: 'bom_unit_price', width: 120, render: (v) => formatMoney(v) },
    { title: '行成本', dataIndex: 'line_cost', width: 120, render: (_, r) => formatMoney(computeLineCost(r?.raw)) },
  ]

  const handleBatchPaginationChange = (pagination: TablePaginationConfig) => {
    const nextPage = pagination.current ?? 1
    const nextSize = pagination.pageSize ?? DEFAULT_PAGE_SIZE
    setBatchPage(nextPage)
    setBatchPageSize(nextSize)
  }

  const handleUploadPreview = async () => {
    if (!uploadFile) {
      message.warning('请先选择一个 .xlsx 文件')
      return
    }
    try {
      setUploading(true)
      if (uploadFile.size >= 2 * MB) {
        message.info(
          `当前文件大小约 ${formatBytes(uploadFile.size)}。若预览/上传报 413（请求体过大），通常需要拆分文件或让运维调大网关/Nginx 上传限制（client_max_body_size）。`,
        )
      }
      const res = await previewShipmentsXlsx({
        file: uploadFile,
        export_date: uploadExportDate,
        requested_by: uploadRequestedBy?.trim() || undefined,
      })
      setPreviewData(res)
      message.success(`预览完成：可执行 ${res.ready_rows}/${res.total_rows}`)
    } catch (err: any) {
      setPreviewData(null)
      const status = tryGetHttpStatus(err)
      if (status === 413) {
        Modal.error({
          title: '预览失败：413（上传体积超限）',
          content: (
            <div>
              <div style={{ marginBottom: 8 }}>
                当前文件：<Text code>{uploadFile?.name ?? '-'}</Text>（约{' '}
                <Text code>{formatBytes(uploadFile?.size ?? 0)}</Text>）
              </div>
              <div style={{ marginBottom: 8 }}>
                这通常是反向代理/Nginx 的请求体大小限制触发（常见默认 1MB）。前端无法绕过限制。
              </div>
              <div style={{ marginBottom: 8 }}>
                处理建议：
                <ul style={{ margin: '6px 0 0 18px' }}>
                  <li>拆分发货单文件（按日期/店铺/导出批次拆分）后再上传</li>
                  <li>
                    或让运维在网关/Nginx 放开上传限制（例如：
                    <Text code>client_max_body_size 20m;</Text>），并确保{' '}
                    <Text code>/api/planner/shipments/import/preview</Text> 与{' '}
                    <Text code>/api/planner/shipments/import</Text> 生效
                  </li>
                </ul>
              </div>
              <div>
                原始错误：<Text type="secondary">{err?.message ?? 'unknown error'}</Text>
              </div>
            </div>
          ),
        })
      } else {
        message.error(`预览失败：${err?.response?.data?.detail ?? err?.message ?? 'unknown error'}`)
      }
    } finally {
      setUploading(false)
    }
  }

  const handleUploadExecute = async () => {
    if (!previewData?.preview_id) {
      message.warning('请先完成“预览”')
      return
    }
    if (uploadFile?.name && previewData?.file_name && String(previewData.file_name) !== String(uploadFile.name)) {
      message.error(`当前选择文件与预览不一致：已选"${uploadFile.name}"，预览的是"${previewData.file_name}"。请重新点击“预览”。`)
      return
    }
    const previewId = String(previewData.preview_id || '').trim()
    const fileName = String(previewData.file_name || uploadFile?.name || '').trim()

    const tryLocateBatch = async (opts: { timeoutMs: number; intervalMs: number; signal?: AbortSignal }) => {
      const deadline = Date.now() + Math.max(1, opts.timeoutMs)
      while (Date.now() < deadline) {
        if (opts.signal?.aborted) throw new Error('aborted')
        try {
          const res = await fetchShipmentImportBatches({ page: 1, page_size: 50 })
          const hit = (res.items ?? []).find((b) => String((b as any).file_hash || '').trim() === previewId)
          if (hit?.id) return hit as any
        } catch {
          // ignore transient errors; keep polling
        }
        await sleepMs(Math.max(500, opts.intervalMs))
      }
      return null
    }

    try {
      setUploading(true)
      const abortController = new AbortController()
      const startedAt = Date.now()
      let modalDestroyed = false
      let cancelled = false

      const modal = Modal.confirm({
        title: '正在执行导入…',
        content: (
          <div>
            <div style={{ marginBottom: 8 }}>
              文件：<Text code>{fileName || '-'}</Text>
            </div>
            <div style={{ marginBottom: 8 }}>
              模式：<Text code>{uploadExecuteMode}</Text>
              <Text type="secondary" style={{ marginLeft: 8 }}>
                {uploadExecuteMode === '2025'
                  ? '不落 BOM 快照（trace），只落计价结果与扣库明细'
                  : '落 BOM 快照（含 trace），并同步落计价结果与扣库明细'}
              </Text>
            </div>
            <div style={{ marginBottom: 8 }}>
              提示：大文件执行期间你可以关闭窗口继续等待；完成后可在“批次列表（上传文件）”看到新批次并自动定位。
            </div>
            <div>
              已等待：<Text code>0s</Text>
            </div>
          </div>
        ),
        okText: '关闭窗口（后台继续）',
        cancelText: '取消执行',
        onOk: () => {
          // close modal but keep polling in background
          if (!modalDestroyed) {
            modalDestroyed = true
            modal.destroy()
          }
        },
        onCancel: () => {
          cancelled = true
          abortController.abort()
          if (!modalDestroyed) {
            modalDestroyed = true
            modal.destroy()
          }
        },
      })

      const ticker = setInterval(() => {
        if (modalDestroyed) return
        const waited = Math.max(0, Math.floor((Date.now() - startedAt) / 1000))
        modal.update({
          content: (
            <div>
              <div style={{ marginBottom: 8 }}>
                文件：<Text code>{fileName || '-'}</Text>
              </div>
              <div style={{ marginBottom: 8 }}>
                模式：<Text code>{uploadExecuteMode}</Text>
                <Text type="secondary" style={{ marginLeft: 8 }}>
                  {uploadExecuteMode === '2025'
                    ? '不落 BOM 快照（trace），只落计价结果与扣库明细'
                    : '落 BOM 快照（含 trace），并同步落计价结果与扣库明细'}
                </Text>
              </div>
              <div style={{ marginBottom: 8 }}>
                提示：大文件执行期间你可以关闭窗口继续等待；完成后可在“批次列表（上传文件）”看到新批次并自动定位。
              </div>
              <div>
                已等待：<Text code>{waited}s</Text>
              </div>
            </div>
          ),
        })
      }, 1000)

      // Background: keep polling until a batch with this file_hash appears (commit happens at end of import).
      ;(async () => {
        if (!previewId) return
        const hit = await tryLocateBatch({
          timeoutMs: 30 * 60 * 1000,
          intervalMs: 5000,
          signal: abortController.signal,
        })
        if (!hit?.id || cancelled) return
        clearInterval(ticker)
        if (!modalDestroyed) {
          modalDestroyed = true
          modal.destroy()
        }
        message.success(`后台执行完成：已定位到批次 ${hit.id}`)
        setSelectedBatchId(hit.id)
        setActiveTab('batches')
        setBatchPage(1)
        queryClient.invalidateQueries({ queryKey: ['shipments'] })
      })()

      const batch = await executeShipmentsFromPreview(
        {
          preview_id: previewData.preview_id,
          file_name: previewData.file_name,
          export_date: uploadExportDate,
          requested_by: uploadRequestedBy?.trim() || undefined,
          mode: uploadExecuteMode,
        },
        { signal: abortController.signal },
      )

      clearInterval(ticker)
      if (!modalDestroyed) {
        modalDestroyed = true
        modal.destroy()
      }

      message.success(`执行完成：batch=${batch.id}（inserted=${batch.inserted_rows}, skipped=${batch.skipped_rows}, exceptions=${batch.exception_rows}）`)
      setSelectedBatchId(batch.id)
      setActiveTab('batches')
      setBatchPage(1)
      setUploadFile(null)
      setPreviewData(null)
      queryClient.invalidateQueries({ queryKey: ['shipments'] })
    } catch (err: any) {
      // If user cancels, keep UI calm.
      if (String(err?.message ?? '').toLowerCase().includes('aborted')) {
        message.info('已取消执行请求')
        return
      }
      if (isTimeoutError(err)) {
        Modal.info({
          title: '执行超时（前端等待超时）',
          content: (
            <div>
              <div style={{ marginBottom: 8 }}>
                大文件执行可能需要较长时间。前端等待超时并不一定代表后端失败。
              </div>
              <div style={{ marginBottom: 8 }}>
                建议：先点右上角“导入记录/排查”→“刷新批次”；若出现新批次，选中后即可查看异常与快照。若未出现，稍等 30–60 秒再刷新。
              </div>
              <div>
                原始错误：<Text type="secondary">{err?.message ?? 'timeout'}</Text>
              </div>
            </div>
          ),
        })
      } else {
        message.error(`执行失败：${err?.response?.data?.detail ?? err?.message ?? 'unknown error'}`)
      }
    } finally {
      setUploading(false)
    }
  }

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between' }}>
        <div>
          <Title level={3} style={{ marginBottom: 4 }}>
            发货作业中心
          </Title>
          <Text type="secondary">
            面向自动化/排查：上传导入、批次、异常队列、BOM快照与回填。运营查账请到“发货台账”。
          </Text>
        </div>
        <Space>
          <Tag color={selectedBatchId ? 'blue' : 'default'} style={{ maxWidth: 520 }}>
            当前批次：{selectedBatchId ? selectedBatchId : '未选择'}
            {selectedBatch?.file_name ? (
              <span style={{ marginLeft: 8, color: '#666' }}>（{String(selectedBatch.file_name)}）</span>
            ) : null}
          </Tag>
          <Button type="primary" onClick={() => setUploadDrawerOpen(true)}>
            上传/导入发货单（xlsx）
          </Button>
          <Button onClick={() => navigate('/costing/shipments')}>去发货台账</Button>
          <Button
            onClick={() => {
              setBatchesDrawerOpen(true)
              batchesQuery.refetch()
            }}
          >
            导入记录/排查
          </Button>
        </Space>
      </div>

      {selectedBatchId ? (
        <div style={{ marginTop: 12 }}>
          <Card size="small" title="当前批次摘要（作业视角）">
            <Descriptions bordered size="small" column={3}>
              <Descriptions.Item label="文件名">{selectedBatch?.file_name ?? '-'}</Descriptions.Item>
              <Descriptions.Item label="导出日期">{selectedBatch?.export_date ?? '-'}</Descriptions.Item>
              <Descriptions.Item label="导入时间">{formatTime(selectedBatch?.created_at ?? null)}</Descriptions.Item>
              <Descriptions.Item label="总行">{safeString(selectedBatch?.total_rows) || '-'}</Descriptions.Item>
              <Descriptions.Item label="写入">{safeString(selectedBatch?.inserted_rows) || '-'}</Descriptions.Item>
              <Descriptions.Item label="异常">{safeString(selectedBatch?.exception_rows) || '-'}</Descriptions.Item>
            </Descriptions>
            <div style={{ marginTop: 10 }}>
              <Space>
                <Button
                  onClick={() => {
                    setBatchesDrawerOpen(true)
                    setActiveTab('exceptions')
                  }}
                >
                  去异常处理
                </Button>
                <Button
                  onClick={() => {
                    setBatchesDrawerOpen(true)
                    setActiveTab('snapshots')
                  }}
                >
                  去快照结果
                </Button>
              </Space>
            </div>
          </Card>
        </div>
      ) : null}

      <Drawer
        title="上传发货单（预览→执行）"
        open={uploadDrawerOpen}
        onClose={() => setUploadDrawerOpen(false)}
        width={880}
      >
        <Card size="small">
          <Row gutter={[16, 16]} align="middle">
            <Col xs={24} lg={10}>
              <Upload
                accept=".xlsx"
                maxCount={1}
                beforeUpload={(file) => {
                  setUploadFile(file as any)
                  setPreviewData(null)
                  return false
                }}
                onRemove={() => {
                  setUploadFile(null)
                  setPreviewData(null)
                }}
              >
                <Button disabled={uploading}>选择文件（.xlsx）</Button>
                <Text type="secondary" style={{ marginLeft: 12 }}>
                  {uploadFile ? uploadFile.name : '未选择'}
                </Text>
              </Upload>
            </Col>
            <Col xs={24} lg={6}>
              <Space>
                <Text>导出日期</Text>
                <DatePicker
                  allowClear
                  value={uploadExportDate ? dayjs(uploadExportDate) : null}
                  format="YYYY-MM-DD"
                  onChange={(d) => setUploadExportDate(d ? d.format('YYYY-MM-DD') : undefined)}
                />
              </Space>
            </Col>
            <Col xs={24} lg={5}>
              <Input
                placeholder="requested_by（可空）"
                value={uploadRequestedBy}
                onChange={(e) => setUploadRequestedBy(e.target.value)}
              />
            </Col>
            <Col xs={24} lg={3}>
              <Space direction="vertical" style={{ width: '100%' }}>
                <Button type="primary" loading={uploading} onClick={handleUploadPreview} block>
                  预览
                </Button>
                <Segmented
                  value={uploadExecuteMode}
                  onChange={(v) => setUploadExecuteMode(v as any)}
                  options={[
                    { label: '2026（落快照）', value: '2026' },
                    { label: '2025（不落快照）', value: '2025' },
                  ]}
                />
                <Button
                  type="primary"
                  danger
                  loading={uploading}
                  onClick={handleUploadExecute}
                  disabled={!previewData?.preview_id}
                  block
                >
                  执行
                </Button>
                <Button onClick={() => setPrecheckDrawerOpen(true)} disabled={!previewData} block>
                  执行前抽查（预览样本）
                </Button>
              </Space>
            </Col>
          </Row>
          {previewData ? (
            <Alert
              style={{ marginTop: 12 }}
              type="info"
              showIcon
              message={`预览结果：总行${previewData.total_rows}，可执行${previewData.ready_rows}，未绑定${previewData.unbound_sku_rows}，缺条码${previewData.missing_sku_rows}，缺规格${previewData.missing_spec_rows}`}
              description={
                (previewData.issues ?? []).length ? (
                  <div style={{ maxHeight: 180, overflow: 'auto', marginTop: 8 }}>
                    <pre style={{ margin: 0 }}>{jsonPretty((previewData.issues ?? []).slice(0, 50))}</pre>
                  </div>
                ) : (
                  <Text type="secondary">无问题明细（或问题数为0）。</Text>
                )
              }
            />
          ) : null}
          <div style={{ marginTop: 8 }}>
            <Text type="secondary">
              说明：先预览再执行。后端按 file_hash（preview_id）做文件级幂等；执行会使用预览阶段缓存的文件。
            </Text>
          </div>
        </Card>
      </Drawer>

      <Drawer
        title="导入记录/排查"
        open={batchesDrawerOpen}
        onClose={() => setBatchesDrawerOpen(false)}
        width={1100}
      >
        <div style={{ marginBottom: 12 }}>
          <Space wrap>
            <Button onClick={() => batchesQuery.refetch()} loading={batchesQuery.isFetching}>
              刷新批次
            </Button>
            <Text type="secondary">提示：点击批次行可切换“当前批次”。</Text>
          </Space>
        </div>
        <Tabs
          activeKey={activeTab}
          onChange={(k) => setActiveTab(k as any)}
          items={[
            {
              key: 'batches',
              label: '批次列表（上传文件）',
              children: (
                <Row gutter={[16, 16]}>
                  <Col span={24}>
                    <Card>
                      <Alert
                        type="info"
                        showIcon
                        message="提示"
                        description="点击任意批次行即可设置为“当前批次”。交接对账 / 异常处理 / 快照结果 默认会围绕当前批次展示。"
                        style={{ marginBottom: 12 }}
                      />
                      <Table
                        rowKey="id"
                        size="small"
                        loading={batchesQuery.isFetching}
                        columns={batchColumns}
                        dataSource={batches}
                        pagination={{
                          current: batchPage,
                          pageSize: batchPageSize,
                          total: totalBatches,
                          showSizeChanger: true,
                        }}
                        onChange={handleBatchPaginationChange}
                        rowClassName={(record) =>
                          record.id === selectedBatchId ? 'ant-table-row-selected' : ''
                        }
                        onRow={(record) => ({
                          onClick: () => {
                            setSelectedBatchId(record.id)
                          },
                        })}
                      />
                    </Card>
                  </Col>
                </Row>
              ),
            },
            {
              key: 'handoff',
              label: '交接对账（本批次）',
              children: (
                <Row gutter={[16, 16]}>
                  <Col span={24}>
                    <Card
                      title="交接对账（前置主档绑定/预解析 ↔ 本批次交易规格/成功快照/异常）"
                      extra={
                        <Space>
                          <Segmented
                            value={handoffMode}
                            onChange={(v) => setHandoffMode(v as any)}
                            options={[
                              { label: '仅异常（交接）', value: 'exceptions' },
                              { label: '仅成功（快照）', value: 'snapshots' },
                              { label: '合并', value: 'both' },
                            ]}
                          />
                          <Segmented
                            value={handoffExceptionResolved}
                            onChange={(v) => setHandoffExceptionResolved(v as any)}
                            disabled={handoffMode === 'snapshots'}
                            options={[
                              { label: '未解决异常', value: 'unresolved' },
                              { label: '已解决异常', value: 'resolved' },
                              { label: '全部异常', value: 'all' },
                            ]}
                          />
                          <Input
                            style={{ width: 120 }}
                            placeholder="limit"
                            value={String(handoffLimit)}
                            onChange={(e) => setHandoffLimit(Number(e.target.value) || 200)}
                          />
                          <Button
                            onClick={() => {
                              if (handoffMode === 'exceptions' || handoffMode === 'both') handoffExceptionsQuery.refetch()
                              if (handoffMode === 'snapshots' || handoffMode === 'both') handoffSnapshotsQuery.refetch()
                            }}
                            disabled={!selectedBatchId}
                          >
                            刷新
                          </Button>
                        </Space>
                      }
                    >
                      {!selectedBatchId ? (
                        <Alert
                          type="info"
                          showIcon
                          message="请先在“批次列表（上传文件）”选择一个批次"
                          description="交接对账默认围绕当前 batch_id，把“成功快照”与“异常（未绑定/缺规格/失败等）”合并展示，便于对账与推动下一步动作。"
                        />
                      ) : (
                        <>
                          <Alert
                            type="info"
                            showIcon
                            style={{ marginBottom: 12 }}
                            message={`当前批次：${selectedBatchId}${selectedBatch?.file_name ? `（${String(selectedBatch.file_name)}）` : ''}`}
                            description={
                              <Text type="secondary">
                                说明：本 Tab 是“本批次交接点”的对账视图，支持仅看异常/仅看成功/合并。点击“展开”可看到两列对账——左侧为 SKU
                                主档预解析/绑定，右侧为本批次交易规格解析。常见异常如“SKU 未绑定标准版本（SKU_NOT_BOUND）”，可先去绑定再重试生成快照。
                              </Text>
                            }
                          />
                          <Table
                            rowKey="key"
                            size="small"
                            loading={
                              ((handoffMode === 'exceptions' || handoffMode === 'both')
                                ? handoffExceptionsQuery.isFetching
                                : false) ||
                              ((handoffMode === 'snapshots' || handoffMode === 'both')
                                ? handoffSnapshotsQuery.isFetching
                                : false)
                            }
                            dataSource={handoffRows}
                            expandable={{
                              expandedRowKeys: handoffExpandedRowKeys,
                              onExpandedRowsChange: (keys) => setHandoffExpandedRowKeys(keys as string[]),
                              expandedRowRender: (r: any) => (
                                <HandoffRowExpanded
                                  skuCode={safeString(r?.sku_code)}
                                  channel={r?.channel ?? null}
                                  erpSpecText={null}
                                  preparseSpecText={null}
                                  shipmentSpecText={r?.spec_text ?? null}
                                  shipmentLineId={r?.shipment_line_id ?? null}
                                  snapshotId={r?.snapshot?.id ?? null}
                                  boundModelCode={null}
                                  boundModelName={null}
                                  boundVersionLabel={null}
                                  boundVersionStatus={null}
                                />
                              ),
                              rowExpandable: (r: any) => !!safeString(r?.sku_code).trim(),
                            }}
                            pagination={{ pageSize: 20 }}
                            columns={[
                              { title: '行号', dataIndex: 'row_index', width: 80 },
                              { title: '发货单号', dataIndex: 'shipment_no', width: 160, ellipsis: true },
                              { title: '渠道', dataIndex: 'channel', width: 140, ellipsis: true },
                              {
                                title: 'SKU',
                                dataIndex: 'sku_code',
                                width: 160,
                                ellipsis: true,
                                render: (v) => safeString(v) || '-',
                              },
                              {
                                title: '交易规格',
                                dataIndex: 'spec_text',
                                width: 360,
                                render: (v) => {
                                  const s = safeString(v)
                                  if (!s) return '-'
                                  return (
                                    <Text ellipsis={{ tooltip: s }} style={{ maxWidth: 520, display: 'inline-block' }}>
                                      {s}
                                    </Text>
                                  )
                                },
                              },
                              {
                                title: '状态',
                                key: 'status',
                                width: 320,
                                render: (_v, r: any) => {
                                  const tags: any[] = []
                                  const hasSnapshot = !!r?.snapshot
                                  const snapLineId = safeString(r?.snapshot?.shipment_line_id).trim()
                                  if (hasSnapshot) {
                                    tags.push(<Tag key="snap" color="green">成功：已落库快照</Tag>)
                                    // 旧快照可能没有 shipment_line_id，导致无法回填 channel/spec_text
                                    if (!snapLineId && !safeString(r?.channel).trim() && !safeString(r?.spec_text).trim()) {
                                      tags.push(
                                        <Text key="snap-hint" type="secondary">
                                          （旧快照缺关联行，渠道/规格可能为空）
                                        </Text>,
                                      )
                                    }
                                  }
                                  const rawReason = safeString(r?.exception?.reason || r?.reason).trim()
                                  if (rawReason) {
                                    const x = formatExceptionReason(rawReason)
                                    const step = reasonStepHint(rawReason)
                                    tags.push(
                                      <Tag key="exc" color="orange">
                                        <span title={x.tooltip}>
                                          {`异常：${x.label}${step ? `（${step.step}/3 ${step.stepLabel}）` : ''}`}
                                        </span>
                                      </Tag>,
                                    )
                                  }
                                  return tags.length ? <Space size={6}>{tags}</Space> : <Tag>未知</Tag>
                                },
                              },
                              {
                                title: '操作',
                                key: 'actions',
                                width: 180,
                                render: (_v, r: any) => {
                                  const reason = safeString(r?.exception?.reason || r?.reason).trim()
                                  const sku = safeString(r?.sku_code).trim()
                                  return (
                                    <Space size={8}>
                                      {r?.snapshot ? (
                                        <Button
                                          size="small"
                                          onClick={() => {
                                            setActiveSnapshot(r.snapshot)
                                            setSnapshotDrawerOpen(true)
                                          }}
                                        >
                                          看快照
                                        </Button>
                                      ) : null}
                                      {reason === 'SKU_NOT_BOUND' && sku ? (
                                        <Button
                                          size="small"
                                          type="link"
                                          onClick={() => navigate(`/costing/sku-master?search=${encodeURIComponent(sku)}`)}
                                        >
                                          去绑定
                                        </Button>
                                      ) : null}
                                    </Space>
                                  )
                                },
                              },
                            ]}
                          />
                        </>
                      )}
                    </Card>
                  </Col>
                </Row>
              ),
            },
            {
              key: 'exceptions',
              label: '异常处理（本批次）',
              children: (
                <Row gutter={[16, 16]}>
                  <Col span={24}>
                    <Card
                      title="异常处理（可重试推进）"
                      extra={
                        <Space>
                          <Segmented
                            value={exceptionResolved}
                            onChange={(v) => setExceptionResolved(v as any)}
                            options={[
                              { label: '未解决', value: 'unresolved' },
                              { label: '已解决', value: 'resolved' },
                              { label: '全部', value: 'all' },
                            ]}
                          />
                          <Button
                            type="primary"
                            disabled={!selectedBatchId || exceptionResolved !== 'unresolved'}
                            loading={retryingExceptions || retryExceptionsMutation.isPending}
                            onClick={() => {
                              if (!selectedBatchId || !(selectedBatchId || '').trim()) {
                                message.warning('请先填写/选择 batch_id')
                                return
                              }
                              if (exceptionResolved !== 'unresolved') {
                                message.warning('请先切换到“未解决”视图再重试')
                                return
                              }
                              // 轻量确认，避免误触造成大量重算
                              ;(async () => {
                                setRetryingExceptions(true)
                                const ok = await new Promise<boolean>((resolve) => {
                                  Modal.confirm({
                                    title: '重试本批未解决异常？',
                                    content:
                                      '将对当前 batch_id 的未解决异常逐条重新执行“绑定→解析→BOM生成”，成功会生成新的 BOM 快照并标记异常已解决。',
                                    okText: '确认重试',
                                    cancelText: '取消',
                                    onOk: () => resolve(true),
                                    onCancel: () => resolve(false),
                                  })
                                })
                                if (!ok) {
                                  setRetryingExceptions(false)
                                  return
                                }
                                retryExceptionsMutation.mutate()
                              })()
                            }}
                          >
                            重试本批未解决异常
                          </Button>
                          <Input
                            style={{ width: 240 }}
                            placeholder="batch_id（可空=全局）"
                            value={selectedBatchId ?? ''}
                            onChange={(e) => setSelectedBatchId(e.target.value.trim() || null)}
                          />
                          <Input
                            style={{ width: 120 }}
                            placeholder="limit"
                            value={String(exceptionLimit)}
                            onChange={(e) => setExceptionLimit(Number(e.target.value) || 200)}
                          />
                        </Space>
                      }
                    >
                      <Table
                        rowKey="id"
                        size="small"
                        loading={exceptionsQuery.isFetching}
                        columns={exceptionColumns}
                        dataSource={exceptionsQuery.data ?? []}
                        pagination={false}
                      />
                    </Card>
                  </Col>
                </Row>
              ),
            },
            {
              key: 'snapshots',
              label: '快照结果',
              children: (
                <Row gutter={[16, 16]}>
                  <Col span={24}>
                    <Card
                      title="快照结果（默认本批次，可切全局检索）"
                      extra={
                        <Space>
                          <Segmented
                            value={snapshotsUseCurrentBatch ? 'current' : 'all'}
                            onChange={(v) => setSnapshotsUseCurrentBatch(v === 'current')}
                            options={[
                              { label: '仅当前批次', value: 'current' },
                              { label: '全局', value: 'all' },
                            ]}
                          />
                          <Button
                            type="primary"
                            onClick={() => {
                              snapshotForm.submit()
                            }}
                          >
                            查询
                          </Button>
                          <Button
                            onClick={() => {
                              snapshotForm.resetFields()
                              setSnapshotQuery({ limit: 200 })
                              if (snapshotsUseCurrentBatch) {
                                snapshotForm.setFieldsValue({ batch_id: selectedBatchId ?? undefined })
                              }
                            }}
                          >
                            重置
                          </Button>
                        </Space>
                      }
                    >
                      <>
                        <Form
                          form={snapshotForm}
                          layout="inline"
                          initialValues={{
                            batch_id: selectedBatchId ?? undefined,
                            sku_code: undefined,
                            shipment_no: undefined,
                            spec_hash: undefined,
                            limit: 200,
                          }}
                          onFinish={(values) => {
                            const next = {
                              batch_id:
                                snapshotsUseCurrentBatch
                                  ? (selectedBatchId ?? undefined)
                                  : ((values.batch_id ?? selectedBatchId ?? undefined) as string | undefined),
                              sku_code: values.sku_code ? String(values.sku_code).trim() : undefined,
                              shipment_no: values.shipment_no ? String(values.shipment_no).trim() : undefined,
                              spec_hash: values.spec_hash ? String(values.spec_hash).trim() : undefined,
                              limit: values.limit ? Number(values.limit) : 200,
                            }
                            setSnapshotQuery(next)
                          }}
                        >
                          <Form.Item name="batch_id" label="batch_id">
                            <Input
                              style={{ width: 260 }}
                              placeholder={snapshotsUseCurrentBatch ? '当前批次（自动）' : '可空=全局'}
                              disabled={snapshotsUseCurrentBatch}
                            />
                          </Form.Item>
                          <Form.Item name="sku_code" label="SKU">
                            <Input style={{ width: 160 }} placeholder="SKU-001" />
                          </Form.Item>
                          <Form.Item name="shipment_no" label="发货单号">
                            <Input style={{ width: 160 }} placeholder="S2025..." />
                          </Form.Item>
                          <Form.Item name="spec_hash" label="spec_hash">
                            <Input style={{ width: 220 }} placeholder="sha1..." />
                          </Form.Item>
                          <Form.Item name="limit" label="limit">
                            <Input style={{ width: 100 }} />
                          </Form.Item>
                        </Form>

                        <div style={{ marginTop: 12 }}>
                          <Table
                            rowKey="id"
                            size="small"
                            loading={snapshotsQuery.isFetching}
                            columns={snapshotColumns}
                            dataSource={snapshotsQuery.data ?? []}
                            pagination={false}
                          />
                        </div>
                      </>
                    </Card>
                  </Col>
                </Row>
              ),
            },
          ]}
        />
      </Drawer>

      <Drawer
        title="执行前抽查（预览样本）"
        open={precheckDrawerOpen}
        onClose={() => setPrecheckDrawerOpen(false)}
        width={1100}
      >
        {!previewData ? (
          <Alert
            type="info"
            showIcon
            message="请先在上方上传区点击“预览”"
            description="这里展示的是“本次上传文件的预览临时结果（ready_items）”，用于执行前抽查几行并预演 BOM；执行后的结果请用“交接对账/异常处理/快照结果”。"
          />
        ) : (
          <>
            <Alert
              type="info"
              showIcon
              style={{ marginBottom: 12 }}
              message={`可执行记录：${previewData.ready_rows}/${previewData.total_rows}（点击行可预览BOM）`}
            />
            <Table
              rowKey={(r) => safeString((r as any).row_index) + '-' + safeString((r as any).sku_code)}
              size="small"
              dataSource={(previewData.ready_items ?? []) as any[]}
              pagination={{ pageSize: 20 }}
              columns={[
                { title: '行号', dataIndex: 'row_index', width: 80 },
                { title: '发货单号', dataIndex: 'shipment_no', width: 160, ellipsis: true },
                { title: 'SKU', dataIndex: 'sku_code', width: 160, ellipsis: true },
                {
                  title: '交易规格',
                  dataIndex: 'spec_text',
                  render: (v) => {
                    const s = safeString(v)
                    if (!s) return '-'
                    return (
                      <Text ellipsis={{ tooltip: s }} style={{ maxWidth: 520, display: 'inline-block' }}>
                        {s}
                      </Text>
                    )
                  },
                },
                { title: 'qty', dataIndex: 'qty', width: 90 },
                {
                  title: '模型',
                  dataIndex: 'bound_model_code',
                  width: 220,
                  render: (_v, r) =>
                    safeString((r as any).bound_model_code) ? (
                      <Space size={6}>
                        <Tag color="blue">{safeString((r as any).bound_model_code)}</Tag>
                        <span style={{ color: '#666' }}>{safeString((r as any).bound_model_name)}</span>
                      </Space>
                    ) : (
                      '-'
                    ),
                },
                { title: '标准版本', dataIndex: 'bound_version_label', width: 180, ellipsis: true },
              ]}
              onRow={(record) => ({
                onClick: () => handleQueuePreviewBom(record),
              })}
            />
          </>
        )}
      </Drawer>

      <Drawer
        title="抽查：BOM预览（扣库存清单）"
        open={queueDrawerOpen}
        onClose={() => {
          setQueueDrawerOpen(false)
          setActiveQueueRow(null)
          setQueueBomPreview(null)
        }}
        width={980}
      >
        {activeQueueRow ? (
          <Space direction="vertical" style={{ width: '100%' }}>
            <Descriptions bordered size="small" column={2}>
              <Descriptions.Item label="shipment_no">{safeString(activeQueueRow.shipment_no) || '-'}</Descriptions.Item>
              <Descriptions.Item label="sku_code">{safeString(activeQueueRow.sku_code) || '-'}</Descriptions.Item>
              <Descriptions.Item label="qty">{safeString(activeQueueRow.qty) || '-'}</Descriptions.Item>
              <Descriptions.Item label="模型">
                {safeString(activeQueueRow.bound_model_code) ? (
                  <Space size={6}>
                    <Tag color="blue">{safeString(activeQueueRow.bound_model_code)}</Tag>
                    <span>{safeString(activeQueueRow.bound_model_name)}</span>
                  </Space>
                ) : (
                  '-'
                )}
              </Descriptions.Item>
              <Descriptions.Item label="交易规格" span={2}>
                {safeString(activeQueueRow.spec_text) || '-'}
              </Descriptions.Item>
            </Descriptions>
            {queueBomPreview ? (
              <Tabs
                items={[
                  {
                    key: 'summary',
                    label: '汇总',
                    children: (
                      <Descriptions bordered size="small" column={3}>
                        <Descriptions.Item label="合计成本（CNY）">
                          <b>
                            {formatMoney(
                              toNumberOrNull((queueBomPreview as any)?.trace?.costing?.total_cost) ??
                                computeTotalCostFromLines((queueBomPreview.final_material_lines ?? []) as any[]),
                            )}
                          </b>
                        </Descriptions.Item>
                        <Descriptions.Item label="物料成本（CNY）">
                          {formatMoney(toNumberOrNull((queueBomPreview as any)?.trace?.costing?.material_cost_total))}
                        </Descriptions.Item>
                        <Descriptions.Item label="工序成本（CNY）">
                          {formatMoney(toNumberOrNull((queueBomPreview as any)?.trace?.costing?.process_cost_total))}
                        </Descriptions.Item>
                        <Descriptions.Item label="制造费用（CNY）">
                          {formatMoney(toNumberOrNull((queueBomPreview as any)?.trace?.costing?.overhead_cost))}
                        </Descriptions.Item>
                        <Descriptions.Item label="制造费率（展示23%）">
                          {safeString((queueBomPreview as any)?.trace?.costing?.overhead_rate) || '0.3'}
                        </Descriptions.Item>
                        <Descriptions.Item label="单位成本（CNY/件）">
                          {formatMoney(toNumberOrNull((queueBomPreview as any)?.trace?.costing?.unit_cost))}
                        </Descriptions.Item>
                        <Descriptions.Item label="已计价物料行">
                          {safeString((queueBomPreview as any)?.trace?.costing?.priced_material_lines) ||
                            safeString((queueBomPreview as any)?.trace?.costing?.priced_lines) ||
                            '-'}
                        </Descriptions.Item>
                        <Descriptions.Item label="缺物料单价行">
                          {safeString((queueBomPreview as any)?.trace?.costing?.missing_price_material_lines) ||
                            safeString((queueBomPreview as any)?.trace?.costing?.missing_price_lines) ||
                            '-'}
                        </Descriptions.Item>
                        <Descriptions.Item label="缺工序单价行">
                          {safeString((queueBomPreview as any)?.trace?.costing?.missing_price_process_lines) || '-'}
                        </Descriptions.Item>
                      </Descriptions>
                    ),
                  },
                  {
                    key: 'materials',
                    label: `物料（${(queueBomPreview.final_material_lines ?? []).length}）`,
                    children: (
                      <Table
                        rowKey={(r) =>
                          safeString((r as any).line_index) + '-' + safeString((r as any).material_code)
                        }
                        size="small"
                        pagination={false}
                        columns={[
                          { title: '#', dataIndex: 'line_index', width: 60 },
                          { title: '编码', dataIndex: 'material_code', width: 140, ellipsis: true },
                          { title: '名称', dataIndex: 'material_name', ellipsis: true },
                          { title: '数量', dataIndex: 'computed_quantity', width: 110 },
                          { title: '单位', dataIndex: 'unit_of_measure', width: 80 },
                          { title: '计量', dataIndex: 'calculation_method', width: 100 },
                          { title: 'BOM单价', dataIndex: 'bom_unit_price', width: 120, render: (v) => formatMoney(v) },
                          {
                            title: '行成本',
                            key: 'line_cost',
                            width: 120,
                            render: (_, r) => formatMoney(computeLineCost(r)),
                          },
                        ]}
                        dataSource={(queueBomPreview.final_material_lines ?? []) as any[]}
                      />
                    ),
                  },
                  {
                    key: 'inventory',
                    label: `扣库清单（真实物料）`,
                    children: Array.isArray((queueBomPreview as any)?.trace?.inventory?.inventory_lines) ? (
                      <Table
                        size="small"
                        pagination={false}
                        rowKey={(r) => safeString((r as any).material_code)}
                        columns={[
                          { title: '物料编码', dataIndex: 'material_code', width: 140, ellipsis: true },
                          { title: '物料名称', dataIndex: 'material_name', ellipsis: true },
                          { title: '单位', dataIndex: 'unit_of_measure', width: 90 },
                          { title: '扣库数量', dataIndex: 'quantity', width: 140 },
                          {
                            title: '来源(展开)',
                            dataIndex: 'sources',
                            render: (v) => (Array.isArray(v) ? v.length : 0),
                            width: 110,
                          },
                        ]}
                        dataSource={((queueBomPreview as any)?.trace?.inventory?.inventory_lines ?? []) as any[]}
                      />
                    ) : (
                      <Alert
                        type="info"
                        showIcon
                        message="暂未生成扣库清单（真实物料展开）。"
                        description="当前页面物料表显示的是模型BOM行（可能含虚拟物料）。扣库存应以“扣库清单（真实物料）”为准。"
                      />
                    ),
                  },
                  {
                    key: 'processes',
                    label: `工序（${(((queueBomPreview as any)?.trace?.costing?.process_lines ?? []) as any[]).length}）`,
                    children: Array.isArray((queueBomPreview as any)?.trace?.costing?.process_lines) ? (
                      <Table
                        size="small"
                        pagination={false}
                        rowKey={(r) => safeString((r as any).process_id) + '-' + safeString((r as any).process_code)}
                        columns={[
                          { title: '工序编码', dataIndex: 'process_code', width: 120, ellipsis: true },
                          { title: '工序名称', dataIndex: 'process_name', ellipsis: true },
                          { title: '班组', dataIndex: 'team_name', width: 110, ellipsis: true },
                          { title: '计量', dataIndex: 'pricing_method', width: 90 },
                          { title: '计量值', dataIndex: 'measure_quantity', width: 90 },
                          { title: '计价', dataIndex: 'cost_type', width: 90 },
                          { title: '分钟', dataIndex: 'total_minutes', width: 90 },
                          { title: '分钟单价', dataIndex: 'rate_per_minute', width: 90 },
                          { title: '计件单价', dataIndex: 'piece_rate', width: 90 },
                          { title: '行成本', dataIndex: 'total_cost', width: 110, render: (v) => formatMoney(v) },
                          {
                            title: '警告',
                            dataIndex: 'warnings',
                            width: 220,
                            render: (v) =>
                              Array.isArray(v) && v.length ? <Text type="warning">{String(v.join('；'))}</Text> : '-',
                          },
                        ]}
                        dataSource={((queueBomPreview as any)?.trace?.costing?.process_lines ?? []) as any[]}
                      />
                    ) : (
                      <Alert type="info" showIcon message="该模型版本未配置工序行，或未返回工序明细。" />
                    ),
                  },
                  {
                    key: 'trace',
                    label: 'Trace',
                    children: (
                      <pre style={{ margin: 0, maxHeight: 420, overflow: 'auto' }}>
                        {jsonPretty(queueBomPreview.trace)}
                      </pre>
                    ),
                  },
                ]}
              />
            ) : (
              <Alert type="info" showIcon message="加载中…（若失败会在顶部提示）" />
            )}
          </Space>
        ) : (
          <Alert type="info" showIcon message="请选择一条抽查记录" />
        )}
      </Drawer>

      <Drawer
        title="快照详情（只读）"
        open={snapshotDrawerOpen}
        onClose={() => {
          setSnapshotDrawerOpen(false)
          setActiveSnapshot(null)
        }}
        width={980}
      >
        {activeSnapshot ? (
          <div>
            <Descriptions bordered size="small" column={2}>
              <Descriptions.Item label="snapshot_id">{activeSnapshot.id}</Descriptions.Item>
              <Descriptions.Item label="batch_id">{activeSnapshot.batch_id}</Descriptions.Item>
              <Descriptions.Item label="shipment_no">
                {activeSnapshot.shipment_no ?? '-'}
              </Descriptions.Item>
              <Descriptions.Item label="sku_code">{activeSnapshot.sku_code ?? '-'}</Descriptions.Item>
              <Descriptions.Item label="qty">{activeSnapshot.qty ?? '-'}</Descriptions.Item>
              <Descriptions.Item label="model_version_id">
                {activeSnapshot.model_version_id ?? '-'}
              </Descriptions.Item>
              <Descriptions.Item label="spec_hash">{activeSnapshot.spec_hash ?? '-'}</Descriptions.Item>
              <Descriptions.Item label="generated_at">
                {formatTime(activeSnapshot.generated_at)}
              </Descriptions.Item>
            </Descriptions>

            <div style={{ marginTop: 16 }}>
              <Tabs
                items={[
                  {
                    key: 'summary',
                    label: '汇总',
                    children: (
                      <Descriptions bordered size="small" column={3}>
                        <Descriptions.Item label="合计成本（CNY）">
                          <b>{formatMoney(snapshotTotalCost)}</b>
                        </Descriptions.Item>
                        <Descriptions.Item label="物料成本（CNY）">
                          {formatMoney(toNumberOrNull((activeSnapshot as any)?.trace?.costing?.material_cost_total))}
                        </Descriptions.Item>
                        <Descriptions.Item label="工序成本（CNY）">
                          {formatMoney(toNumberOrNull((activeSnapshot as any)?.trace?.costing?.process_cost_total))}
                        </Descriptions.Item>
                        <Descriptions.Item label="制造费用（CNY）">
                          {formatMoney(toNumberOrNull((activeSnapshot as any)?.trace?.costing?.overhead_cost))}
                        </Descriptions.Item>
                        <Descriptions.Item label="制造费率（展示23%）">
                          {safeString((activeSnapshot as any)?.trace?.costing?.overhead_rate) || '0.3'}
                        </Descriptions.Item>
                        <Descriptions.Item label="单位成本（CNY/件）">
                          {formatMoney(toNumberOrNull((activeSnapshot as any)?.trace?.costing?.unit_cost))}
                        </Descriptions.Item>
                      </Descriptions>
                    ),
                  },
                  {
                    key: 'materials',
                    label: `物料（${snapshotLines.length}）`,
                    children: (
                      <Table
                        size="small"
                        columns={snapshotLineCols}
                        dataSource={snapshotLines}
                        pagination={false}
                        scroll={{ x: 960 }}
                      />
                    ),
                  },
                  {
                    key: 'inventory',
                    label: '扣库清单（真实物料）',
                    children: Array.isArray((activeSnapshot as any)?.trace?.inventory?.inventory_lines) ? (
                      <Table
                        size="small"
                        pagination={false}
                        rowKey={(r) => safeString((r as any).material_code)}
                        columns={[
                          { title: '物料编码', dataIndex: 'material_code', width: 140, ellipsis: true },
                          { title: '物料名称', dataIndex: 'material_name', ellipsis: true },
                          { title: '单位', dataIndex: 'unit_of_measure', width: 90 },
                          { title: '扣库数量', dataIndex: 'quantity', width: 140 },
                          {
                            title: '来源(展开)',
                            dataIndex: 'sources',
                            render: (v) => (Array.isArray(v) ? v.length : 0),
                            width: 110,
                          },
                        ]}
                        dataSource={((activeSnapshot as any)?.trace?.inventory?.inventory_lines ?? []) as any[]}
                      />
                    ) : (
                      <Alert
                        type="info"
                        showIcon
                        message="该快照未包含扣库清单（真实物料展开）。"
                        description="可点快照列表的“回填”，重新生成后即可获得真实物料扣库清单。"
                      />
                    ),
                  },
                  {
                    key: 'processes',
                    label: `工序（${(((activeSnapshot as any)?.trace?.costing?.process_lines ?? []) as any[]).length}）`,
                    children: Array.isArray((activeSnapshot as any)?.trace?.costing?.process_lines) ? (
                      <Table
                        size="small"
                        pagination={false}
                        rowKey={(r) => safeString((r as any).process_id) + '-' + safeString((r as any).process_code)}
                        columns={[
                          { title: '工序编码', dataIndex: 'process_code', width: 120, ellipsis: true },
                          { title: '工序名称', dataIndex: 'process_name', ellipsis: true },
                          { title: '班组', dataIndex: 'team_name', width: 110, ellipsis: true },
                          { title: '计量', dataIndex: 'pricing_method', width: 90 },
                          { title: '计量值', dataIndex: 'measure_quantity', width: 90 },
                          { title: '计价', dataIndex: 'cost_type', width: 90 },
                          { title: '分钟', dataIndex: 'total_minutes', width: 90 },
                          { title: '分钟单价', dataIndex: 'rate_per_minute', width: 90 },
                          { title: '计件单价', dataIndex: 'piece_rate', width: 90 },
                          { title: '行成本', dataIndex: 'total_cost', width: 110, render: (v) => formatMoney(v) },
                          {
                            title: '警告',
                            dataIndex: 'warnings',
                            width: 220,
                            render: (v) =>
                              Array.isArray(v) && v.length ? <Text type="warning">{String(v.join('；'))}</Text> : '-',
                          },
                        ]}
                        dataSource={(((activeSnapshot as any)?.trace?.costing?.process_lines ?? []) as any[]).slice(0, 500)}
                      />
                    ) : (
                      <Alert type="info" showIcon message="该快照未包含工序明细（可能当时未开启/未配置）。" />
                    ),
                  },
                  {
                    key: 'trace',
                    label: 'Trace',
                    children: (
                      <pre style={{ margin: 0, maxHeight: 520, overflow: 'auto' }}>
                        {jsonPretty(activeSnapshot.trace)}
                      </pre>
                    ),
                  },
                ]}
              />
            </div>
          </div>
        ) : (
          <Alert type="info" showIcon message="未选择快照" />
        )}
      </Drawer>
    </div>
  )
}

export default ShipmentMonitorPage


