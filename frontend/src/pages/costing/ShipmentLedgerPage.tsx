import {
  Alert,
  Button,
  Card,
  DatePicker,
  Drawer,
  Form,
  Image,
  Input,
  Modal,
  Select,
  Space,
  Tabs as AntTabs,
  Table,
  Tabs,
  Tag,
  Tooltip,
  Typography,
  Descriptions,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import dayjs from 'dayjs'
import { useEffect, useMemo, useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'

import SalesInsightsPage from '@/pages/costing/SalesInsightsPage'
import {
  fetchBundleTemplates,
  fetchPublishedStandardModels,
  fetchProductModelVersions,
  fetchShipmentBomSnapshotDetail,
  fetchShipmentLineCosting,
  fetchShipmentLineDeductions,
  fetchShipmentLineProcesses,
  fetchShipmentLines,
  fetchSkuMasterByBarcode,
} from '@/services/planner'
import type { ShipmentLineListItem, ShipmentLineListResponse } from '@/types/planner'

const { Title, Text } = Typography

const safeString = (v: unknown): string => {
  if (v === null || v === undefined) return ''
  return String(v)
}

// Display-only normalization for transaction spec:
// - unify delimiters to Chinese semicolon "；"
// - strip attribute labels like "颜色分类:" / "地毯尺寸:" / "尺寸:" ... (generic `xxx:` prefix segments)
const normalizeTxSpecForDisplay = (raw: unknown): string => {
  let s = safeString(raw).trim()
  if (!s) return ''
  s = s.replace(/;/g, '；')
  // Remove label prefixes at start or after delimiter: "<label>:" => ""
  // e.g. "颜色分类:AAA；尺寸:BBB" -> "AAA；BBB"
  s = s.replace(/(^|；\s*)([^；]{1,32}?)\s*:\s*/g, '$1')
  s = s.replace(/；\s*；+/g, '；')
  s = s.replace(/\s+/g, ' ').trim()
  s = s.replace(/^；+/, '').replace(/；+$/, '')
  return s
}

type ParsedDims = {
  width_cm?: number
  height_cm?: number
  diameter_cm?: number
}

const parseDimsFromSpecText = (raw: unknown): ParsedDims => {
  const s0 = normalizeTxSpecForDisplay(raw)
  const s = s0.replace(/CM\b/gi, 'cm').replace(/厘米/g, 'cm')
  // Prefer explicit diameter markers
  const mDia = s.match(/(?:直径|Φ|φ)\s*([0-9]+(?:\.[0-9]+)?)\s*cm?/i)
  if (mDia?.[1]) {
    const d = Number(mDia[1])
    if (Number.isFinite(d) && d > 0 && d <= 1000) return { diameter_cm: d }
  }
  // width x height patterns: "60CM*60CM" / "45X45" / "约64.5*64.5"
  const mWH = s.match(/([0-9]+(?:\.[0-9]+)?)\s*(?:cm)?\s*[xX*×]\s*([0-9]+(?:\.[0-9]+)?)\s*(?:cm)?/i)
  if (mWH?.[1] && mWH?.[2]) {
    const w = Number(mWH[1])
    const h = Number(mWH[2])
    if (Number.isFinite(w) && Number.isFinite(h) && w > 0 && h > 0 && w <= 2000 && h <= 2000) {
      return { width_cm: w, height_cm: h }
    }
  }
  return {}
}

const formatDimsText = (d: ParsedDims): string => {
  const w = d.width_cm
  const h = d.height_cm
  const dia = d.diameter_cm
  if (Number.isFinite(dia as any) && (dia as any) > 0) return `直径≈${Number(dia).toFixed(1).replace(/\.0$/, '')}cm`
  if (Number.isFinite(w as any) && Number.isFinite(h as any) && (w as any) > 0 && (h as any) > 0) {
    const ww = Number(w).toFixed(1).replace(/\.0$/, '')
    const hh = Number(h).toFixed(1).replace(/\.0$/, '')
    return `宽≈${ww}cm；高≈${hh}cm`
  }
  return '-'
}

const inferAreaFromBomLines = (lines: any[]): number | null => {
  const items = Array.isArray(lines) ? lines : []
  const unitOk = (u: string) => {
    const x = (u || '').toLowerCase()
    return x.includes('㎡') || x.includes('平米') || x.includes('平方米') || x.includes('m2')
  }
  let best: number | null = null
  for (const r of items) {
    const u = safeString(r?.unit_of_measure).trim()
    if (!u || !unitOk(u)) continue
    const q = Number(safeString(r?.computed_quantity).trim())
    if (!Number.isFinite(q) || q <= 0) continue
    if (best === null || q > best) best = q
  }
  return best
}

const inferPrimaryAreaLine = (
  lines: any[],
): { qty_m2: number; uom: string; material_code?: string; material_name?: string; extra_width_mm?: number; extra_height_mm?: number } | null => {
  const items = Array.isArray(lines) ? lines : []
  const unitOk = (u: string) => {
    const x = (u || '').toLowerCase()
    return x.includes('㎡') || x.includes('平米') || x.includes('平方米') || x.includes('m2')
  }
  let best: any | null = null
  for (const r of items) {
    const u = safeString(r?.unit_of_measure).trim()
    if (!u || !unitOk(u)) continue
    const q = Number(safeString(r?.computed_quantity).trim())
    if (!Number.isFinite(q) || q <= 0) continue
    if (!best || q > Number(safeString(best?.computed_quantity).trim())) best = r
  }
  if (!best) return null
  const qty = Number(safeString(best?.computed_quantity).trim())
  if (!Number.isFinite(qty) || qty <= 0) return null
  const md = best?.metadata && typeof best.metadata === 'object' ? best.metadata : {}
  const ew = Number(safeString((md as any)?.extra_width_mm).trim())
  const eh = Number(safeString((md as any)?.extra_height_mm).trim())
  return {
    qty_m2: qty,
    uom: safeString(best?.unit_of_measure).trim(),
    material_code: safeString(best?.material_code).trim() || undefined,
    material_name: safeString(best?.material_name).trim() || undefined,
    extra_width_mm: Number.isFinite(ew) ? ew : undefined,
    extra_height_mm: Number.isFinite(eh) ? eh : undefined,
  }
}

const reasonLabel = (reason: string): string => {
  const r = String(reason || '').trim()
  if (!r) return ''
  if (r === 'SKU_NOT_BOUND') return '未绑定'
  if (r === 'SPEC_EMPTY') return '缺规格'
  if (r === 'BOM_GENERATION_FAILED') return 'BOM失败'
  return r
}

const ShipmentLedgerPage = () => {
  const navigate = useNavigate()
  const [ledgerForm] = Form.useForm()

  const initialUrl = useMemo(() => {
    try {
      if (typeof window === 'undefined') return {} as any
      const p = new URLSearchParams(window.location.search)
      return {
        tab: String(p.get('tab') ?? '').trim(),
        start: String(p.get('start') ?? '').trim(),
        end: String(p.get('end') ?? '').trim(),
        channel: String(p.get('channel') ?? '').trim(),
        sku_code: String(p.get('sku_code') ?? '').trim(),
        bound_target_kind: String(p.get('bound_target_kind') ?? '').trim(),
        bundle_template_code: String(p.get('bundle_template_code') ?? '').trim(),
        bundle_preset_selector: String(p.get('bundle_preset_selector') ?? '').trim(),
        sort: String(p.get('sort') ?? '').trim(),
        order: String(p.get('order') ?? '').trim(),
      }
    } catch {
      return {} as any
    }
  }, [])

  const [ledgerTab, setLedgerTab] = useState<'all' | 'processed' | 'pending' | 'sales' | 'issues'>(() => {
    const t = String((initialUrl as any)?.tab ?? '').trim()
    return t === 'processed' || t === 'pending' || t === 'sales' || t === 'issues' ? (t as any) : 'all'
  })
  const [ledgerPage, setLedgerPage] = useState(1)
  const [ledgerPageSize, setLedgerPageSize] = useState(50)
  const [ledgerRange, setLedgerRange] = useState<[any, any]>(() => [
    // 默认给足范围，避免“有数据但首屏看不到”造成误判（尤其是历史导入/回补数据）
    dayjs().subtract(89, 'day').startOf('day'),
    dayjs().add(1, 'day').startOf('day'),
  ])
  const [ledgerFilters, setLedgerFilters] = useState<{
    channel?: string
    sku_code?: string
    order_no?: string
    product_link_id?: string
    spec_text?: string
    unresolved_reason?: string
    bound_target_kind?: 'any' | 'model' | 'bundle'
    bound_model_code?: string
    bound_version_label?: string
    bundle_preset_selector?: string
  }>({})

  const [bulkModalOpen, setBulkModalOpen] = useState(false)
  const [bulkOverwrite, setBulkOverwrite] = useState(false)
  const [bulkLimit, setBulkLimit] = useState(200)

  const [tableSort, setTableSort] = useState<{ field?: string; order?: 'ascend' | 'descend' }>(() => {
    const f = String((initialUrl as any)?.sort ?? '').trim()
    const o = String((initialUrl as any)?.order ?? '').trim()
    const ord = o === 'ascend' || o === 'descend' ? (o as any) : undefined
    return f ? { field: f, order: ord } : {}
  })

  // Filter helpers (binding dropdowns)
  const [boundKind, setBoundKind] = useState<'any' | 'model' | 'bundle'>('any')
  const [modelSearch, setModelSearch] = useState('')
  const [bundleSearch, setBundleSearch] = useState('')
  const [selectedModelId, setSelectedModelId] = useState<string | undefined>(undefined)

  const publishedModelsQuery = useQuery({
    queryKey: ['shipments', 'ledger', 'published-models', modelSearch],
    queryFn: () => fetchPublishedStandardModels({ search: modelSearch || undefined, limit: 50 }),
    enabled: boundKind === 'model',
    placeholderData: keepPreviousData,
  })
  const modelOptions = useMemo(() => {
    const items = (publishedModelsQuery.data as any)?.items ?? []
    return (items as any[])
      .map((m: any) => ({
        label: `${String(m?.model_code ?? '').trim()} ${String(m?.model_name ?? '').trim()}`.trim(),
        value: String(m?.model_id ?? '').trim(),
        code: String(m?.model_code ?? '').trim(),
      }))
      .filter((x: any) => x.value && x.code)
  }, [publishedModelsQuery.data])

  const modelVersionsQuery = useQuery({
    queryKey: ['shipments', 'ledger', 'model-versions', selectedModelId],
    queryFn: () => fetchProductModelVersions(String(selectedModelId), {}),
    enabled: boundKind === 'model' && !!selectedModelId,
    placeholderData: keepPreviousData,
  })
  const versionOptions = useMemo(() => {
    const items = (modelVersionsQuery.data ?? []) as any[]
    return items
      .filter((v: any) => String(v?.version_status ?? '').trim() === 'published')
      .map((v: any) => ({
        label: String(v?.version_label ?? '').trim(),
        value: String(v?.version_label ?? '').trim(),
      }))
      .filter((x: any) => x.value)
  }, [modelVersionsQuery.data])

  const bundleTemplatesQuery = useQuery({
    queryKey: ['shipments', 'ledger', 'bundle-templates', bundleSearch],
    queryFn: () => fetchBundleTemplates({ search: bundleSearch || undefined, page: 1, page_size: 50 }),
    enabled: boundKind === 'bundle',
    placeholderData: keepPreviousData,
  })
  const bundleTemplateOptions = useMemo(() => {
    const items = (bundleTemplatesQuery.data as any)?.items ?? []
    return (items as any[])
      .map((t: any) => ({
        label: `${String(t?.template_code ?? '').trim()} ${String(t?.name ?? '').trim()}`.trim(),
        value: String(t?.template_code ?? '').trim(),
      }))
      .filter((x: any) => x.value)
  }, [bundleTemplatesQuery.data])

  // Drawer (details)
  const [detailOpen, setDetailOpen] = useState(false)
  const [detailRow, setDetailRow] = useState<ShipmentLineListItem | null>(null)

  const skuMasterQuery = useQuery({
    queryKey: ['shipments', 'ledger', 'sku-master-by-barcode', detailRow?.sku_code, detailRow?.channel],
    queryFn: () => fetchSkuMasterByBarcode(String(detailRow?.sku_code ?? ''), { channel: detailRow?.channel ?? undefined, limit: 10 }),
    enabled: detailOpen && !!safeString(detailRow?.sku_code).trim(),
    placeholderData: keepPreviousData,
  })
  const skuMasterId = safeString((skuMasterQuery.data as any)?.sku_master?.id).trim()
  const specImageUrl = skuMasterId ? `/api/planner/sku-master/${encodeURIComponent(skuMasterId)}/images/spec` : ''
  const productImageUrl = skuMasterId ? `/api/planner/sku-master/${encodeURIComponent(skuMasterId)}/images/product` : ''

  const snapshotId = safeString((detailRow as any)?.bom_snapshot_id).trim()
  const shipmentLineId = safeString((detailRow as any)?.id).trim()
  const bomSnapshotQuery = useQuery({
    queryKey: ['shipments', 'ledger', 'bom-snapshot', snapshotId],
    queryFn: () => fetchShipmentBomSnapshotDetail(snapshotId),
    enabled: detailOpen && !!snapshotId,
    placeholderData: keepPreviousData,
  })
  const costingQuery = useQuery({
    queryKey: ['shipments', 'ledger', 'costing', shipmentLineId],
    queryFn: () => fetchShipmentLineCosting(shipmentLineId),
    enabled: detailOpen && !!shipmentLineId,
    placeholderData: keepPreviousData,
  })
  const deductionsQuery = useQuery({
    queryKey: ['shipments', 'ledger', 'deductions', shipmentLineId],
    queryFn: () => fetchShipmentLineDeductions(shipmentLineId),
    enabled: detailOpen && !!shipmentLineId,
    placeholderData: keepPreviousData,
  })
  const processesQuery = useQuery({
    queryKey: ['shipments', 'ledger', 'processes', shipmentLineId],
    queryFn: () => fetchShipmentLineProcesses(shipmentLineId),
    enabled: detailOpen && !!shipmentLineId,
    placeholderData: keepPreviousData,
  })

  const parsedDims = useMemo(() => parseDimsFromSpecText((detailRow as any)?.spec_text), [detailRow])
  const parsedAreaM2 = useMemo(() => {
    if (parsedDims.width_cm && parsedDims.height_cm) return (parsedDims.width_cm / 100) * (parsedDims.height_cm / 100)
    if (parsedDims.diameter_cm) {
      const r = parsedDims.diameter_cm / 100 / 2
      return Math.PI * r * r
    }
    return null
  }, [parsedDims])
  const bomAreaM2 = useMemo(
    () => inferAreaFromBomLines(((bomSnapshotQuery.data as any)?.final_material_lines ?? []) as any[]),
    [bomSnapshotQuery.data],
  )
  const bomPrimaryAreaLine = useMemo(
    () => inferPrimaryAreaLine(((bomSnapshotQuery.data as any)?.final_material_lines ?? []) as any[]),
    [bomSnapshotQuery.data],
  )
  const snapshotMeasureMm = useMemo(() => {
    const t = (bomSnapshotQuery.data as any)?.trace
    const mm = t?.measurement_mm
    if (!mm || typeof mm !== 'object') return null
    const w = Number(safeString((mm as any)?.width_mm).trim())
    const h = Number(safeString((mm as any)?.height_mm).trim())
    if (!Number.isFinite(w) || !Number.isFinite(h) || w <= 0 || h <= 0) return null
    return { width_mm: w, height_mm: h }
  }, [bomSnapshotQuery.data])

  const shipmentLinesQuery = useQuery({
    queryKey: ['shipments', 'lines', ledgerTab, ledgerPage, ledgerPageSize, ledgerRange, ledgerFilters],
    queryFn: () =>
      fetchShipmentLines({
        page: ledgerTab === 'issues' ? 1 : ledgerPage,
        page_size: ledgerTab === 'issues' ? 200 : ledgerPageSize,
        start: ledgerRange?.[0]?.toISOString?.() ?? undefined,
        end: ledgerRange?.[1]?.toISOString?.() ?? undefined,
        status: ledgerTab === 'processed' || ledgerTab === 'pending' ? ledgerTab : ledgerTab === 'issues' ? 'processed' : undefined,
        include_issue_hints: ledgerTab === 'issues',
        ...ledgerFilters,
      }),
    placeholderData: keepPreviousData,
    enabled: ledgerTab !== 'sales',
  })

  const LOW_MARGIN_THRESHOLD = 0.1
  const calcProfit = (r: any): number | null => {
    const costRaw = safeString(r?.cost_total).trim()
    if (!costRaw || costRaw === '-') return null
    const rev = Number(safeString(r?.revenue_amount).trim())
    const cost = Number(costRaw)
    if (!Number.isFinite(rev) || !Number.isFinite(cost)) return null
    return rev - cost
  }
  const calcMargin = (r: any): number | null => {
    const profit = calcProfit(r)
    if (profit === null) return null
    const rev = Number(safeString(r?.revenue_amount).trim())
    if (!Number.isFinite(rev) || rev === 0) return null
    return profit / rev
  }
  const issueTags = (r: any): Array<{ key: string; label: string; color: string; tooltip?: string }> => {
    const tags: Array<{ key: string; label: string; color: string; tooltip?: string }> = []
    const profit = calcProfit(r)
    const margin = calcMargin(r)
    const suspected = Boolean((r as any)?.suspected_mismatch)
    const reasons = (((r as any)?.mismatch_warnings ?? []) as any[]).map((x) => safeString(x)).filter(Boolean)
    const sizeBad = Boolean((r as any)?.suspected_size_anomaly)
    const sizeDetail = safeString((r as any)?.size_anomaly_detail).trim()
    if (profit !== null && profit < 0) tags.push({ key: 'neg_profit', label: '毛利为负', color: 'volcano' })
    if (suspected) tags.push({ key: 'suspected_mismatch', label: '疑似绑错', color: 'red', tooltip: reasons.join('\n') || '疑似绑错（软提示）' })
    if (margin !== null && margin >= 0 && margin < LOW_MARGIN_THRESHOLD) {
      tags.push({ key: 'low_margin', label: `利润过低(<${Math.round(LOW_MARGIN_THRESHOLD * 100)}%)`, color: 'gold' })
    }
    if (sizeBad) tags.push({ key: 'size_anomaly', label: '尺寸疑似异常', color: 'orange', tooltip: sizeDetail || '解析尺寸与计价尺寸/面积差异过大（软提示）' })
    return tags
  }
  const isIssueRow = (r: any): boolean => issueTags(r).length > 0

  useEffect(() => {
    const kind0 = String((initialUrl as any)?.bound_target_kind ?? '').trim()
    const kind: 'any' | 'model' | 'bundle' = kind0 === 'model' || kind0 === 'bundle' ? (kind0 as any) : 'any'
    const tpl = String((initialUrl as any)?.bundle_template_code ?? '').trim().toUpperCase() || undefined
    const sel = String((initialUrl as any)?.bundle_preset_selector ?? '').trim().toUpperCase() || undefined
    const channel0 = String((initialUrl as any)?.channel ?? '').trim() || undefined
    const sku0 = String((initialUrl as any)?.sku_code ?? '').trim() || undefined
    const start0 = String((initialUrl as any)?.start ?? '').trim()
    const end0 = String((initialUrl as any)?.end ?? '').trim()
    if (start0 && end0) {
      const s = dayjs(start0)
      const e = dayjs(end0)
      if (s.isValid() && e.isValid()) setLedgerRange([s, e] as any)
    }
    if (channel0 || sku0) {
      ledgerForm.setFieldsValue({ channel: channel0, sku_code: sku0 })
      setLedgerFilters((prev) => ({ ...prev, channel: channel0, sku_code: sku0 }))
      setLedgerPage(1)
    }
    if (kind === 'bundle' && tpl) {
      setBoundKind('bundle')
      ledgerForm.setFieldsValue({
        bound_target_kind: 'bundle',
        bundle_template_code: tpl,
        bundle_selector: sel ? [sel] : undefined,
        channel: channel0,
        sku_code: sku0,
      })
      setLedgerFilters({
        bound_target_kind: 'bundle',
        bound_model_code: `B-${tpl}`,
        bundle_preset_selector: sel,
        channel: channel0,
        sku_code: sku0,
      })
      setLedgerPage(1)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const columns: ColumnsType<ShipmentLineListItem> = [
    {
      title: '发货日期',
      dataIndex: 'completed_at',
      width: 110,
      render: (v) => {
        const d = dayjs(safeString(v))
        return d.isValid() ? d.format('YYYY-MM-DD') : (safeString(v) || '-')
      },
    },
    { title: '店铺', dataIndex: 'channel', width: 140, ellipsis: true },
    { title: '货品条码', dataIndex: 'sku_code', width: 170, ellipsis: true },
    { title: '订单号', dataIndex: 'order_no', width: 215, ellipsis: true },
    {
      title: '问题标记',
      key: 'issue_tags',
      width: 210,
      render: (_v, r: any) => {
        const tags = issueTags(r)
        if (!tags.length) return '-'
        return (
          <Space size={4} wrap>
            {tags.map((t) => (
              <Tooltip key={t.key} title={t.tooltip}>
                <Tag color={t.color}>{t.label}</Tag>
              </Tooltip>
            ))}
          </Space>
        )
      },
    },
    {
      title: '模型/套装',
      key: 'bound_target',
      width: 295,
      render: (_v, r: any) => {
        const code = safeString(r?.bound_model_code).trim()
        const name = safeString(r?.bound_model_name).trim()
        if (!code) return '-'
        const isBundle = code.startsWith('B-') || code.startsWith('Z-')
        return (
          <span>
            <Tag color={isBundle ? 'purple' : 'blue'}>{code}</Tag>
            {name ? <span style={{ color: '#666' }}> {name}</span> : null}
          </span>
        )
      },
    },
    {
      title: '标准版本',
      dataIndex: 'bound_version_label',
      width: 215,
      ellipsis: true,
      render: (v) => {
        const s = safeString(v).trim()
        if (!s) return '-'
        return (
          <Tooltip title={s}>
            <span style={capsuleStyle}>{s}</span>
          </Tooltip>
        )
      },
    },
    {
      title: '交易规格',
      dataIndex: 'spec_text',
      ellipsis: true,
      render: (v) => {
        const s = normalizeTxSpecForDisplay(v)
        if (!s) return '-'
        return (
          <Text ellipsis={{ tooltip: s }} style={{ maxWidth: 660, display: 'inline-block', lineHeight: 1.2 }}>
            {s}
          </Text>
        )
      },
    },
    { title: '数量', dataIndex: 'qty', width: 60, render: (v) => safeString(v) || '-' },
    { title: '金额', dataIndex: 'revenue_amount', width: 88, render: (v) => formatMoney(v) },
    {
      title: '成本',
      dataIndex: 'cost_total',
      width: 88,
      render: (v) => formatMoney(v),
    },
    {
      title: '毛利',
      key: 'profit_amount',
      width: 88,
      sorter: (a: any, b: any) => {
        const va = calcProfit(a)
        const vb = calcProfit(b)
        if (va === null && vb === null) return 0
        if (va === null) return 1
        if (vb === null) return -1
        return va - vb
      },
      sortOrder: tableSort.field === 'profit_amount' ? tableSort.order : undefined,
      render: (_v, r: any) => {
        const costRaw = safeString(r?.cost_total).trim()
        if (!costRaw || costRaw === '-') return '-'
        const rev = Number(safeString(r?.revenue_amount).trim())
        const cost = Number(costRaw)
        if (!Number.isFinite(rev) || !Number.isFinite(cost)) return '-'
        return formatMoney(rev - cost)
      },
    },
    {
      title: '毛利率',
      key: 'profit_rate',
      width: 80,
      sorter: (a: any, b: any) => {
        const va = calcMargin(a)
        const vb = calcMargin(b)
        if (va === null && vb === null) return 0
        if (va === null) return 1
        if (vb === null) return -1
        return va - vb
      },
      sortOrder: tableSort.field === 'profit_rate' ? tableSort.order : undefined,
      render: (_v, r: any) => {
        const costRaw = safeString(r?.cost_total).trim()
        if (!costRaw || costRaw === '-') return '-'
        const rev = Number(safeString(r?.revenue_amount).trim())
        const cost = Number(costRaw)
        if (!Number.isFinite(rev) || !Number.isFinite(cost) || rev === 0) return '-'
        return formatPct((rev - cost) / rev)
      },
    },
    {
      title: '处理状态',
      key: 'status',
      width: 180,
      render: (_v, r: any) => {
        const status = safeString(r?.status)
        const src = safeString(r?.processed_source)
        const mode = safeString(r?.mode)
        const reason = safeString(r?.unresolved_reason)
        const msg = safeString(r?.unresolved_message)
        if (status === 'processed') {
          const text = src === 'bom_snapshot' || mode === '2026' ? '已落快照' : '已计价'
          const badge = mode ? `（${mode}）` : ''
          return <Text style={{ color: '#2e7d32' }}>{text}{badge}</Text>
        }
        if (reason) {
          const short = reasonLabel(reason) || '待处理'
          const full = `待处理（${reason}）${msg ? `：${msg}` : ''}`
          return (
            <Tooltip title={full}>
              <Tag color="red" style={{ cursor: 'help' }}>
                {short}
              </Tag>
            </Tooltip>
          )
        }
        return <Text style={{ color: '#b26a00' }}>待处理</Text>
      },
    },
  ]

  const data = shipmentLinesQuery.data as ShipmentLineListResponse | undefined
  const isEmpty = !shipmentLinesQuery.isFetching && (data?.total ?? 0) === 0

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between' }}>
        <div>
          <Title level={3} style={{ marginBottom: 4 }}>
            发货台账
          </Title>
          <Text type="secondary">面向运营查账：按时间范围查询发货行；异常与快照生成属于“作业中心”。</Text>
        </div>
        <Space>
          <Button type="primary" onClick={() => setBulkModalOpen(true)}>
            批量计价快照
          </Button>
          <Button onClick={() => navigate('/costing/shipments/ops')}>去发货作业中心</Button>
        </Space>
      </div>

      <Modal
        title="批量计价快照（按当前台账筛选范围）"
        open={bulkModalOpen}
        onCancel={() => setBulkModalOpen(false)}
        okText={bulkOverwrite ? '继续（覆盖重算）' : '继续（只补齐缺失）'}
        okButtonProps={bulkOverwrite ? { danger: true } : undefined}
        onOk={() => {
          const start = ledgerRange?.[0]?.toISOString?.()
          const end = ledgerRange?.[1]?.toISOString?.()
          const status = ledgerTab === 'all' ? undefined : ledgerTab

          const qp = new URLSearchParams()
          qp.set('tab', 'bulk')
          qp.set('from', 'ledger')
          if (start) qp.set('start', String(start))
          if (end) qp.set('end', String(end))
          if (status) qp.set('status', String(status))
          if (ledgerFilters.channel) qp.set('channel', String(ledgerFilters.channel))
          if (ledgerFilters.sku_code) qp.set('sku_code', String(ledgerFilters.sku_code))
          if (ledgerFilters.order_no) qp.set('order_no', String(ledgerFilters.order_no))
          if (ledgerFilters.product_link_id) qp.set('product_link_id', String(ledgerFilters.product_link_id))
          if (ledgerFilters.spec_text) qp.set('spec_text', String(ledgerFilters.spec_text))
          if (ledgerFilters.unresolved_reason) qp.set('unresolved_reason', String(ledgerFilters.unresolved_reason))
          qp.set('limit', String(Math.max(1, Math.min(2000, Math.floor(bulkLimit || 200)))))
          if (bulkOverwrite) qp.set('overwrite', '1')

          setBulkModalOpen(false)
          navigate(`/costing/shipments/ops?${qp.toString()}`)
        }}
      >
        <Space direction="vertical" style={{ width: '100%' }} size={8}>
          <Alert
            type="info"
            showIcon
            message="说明"
            description={
              <div>
                <div>
                  默认是<strong>只补齐缺失</strong>：已有快照/计价结果的行会跳过。
                </div>
                <div>
                  勾选“覆盖重算”后，会对已有快照执行覆盖重算（高风险，可能改写历史核算结果）。
                </div>
              </div>
            }
          />
          <Space wrap>
            <span>最多处理</span>
            <Input
              style={{ width: 120 }}
              value={String(bulkLimit)}
              onChange={(e) => setBulkLimit(Number(e.target.value) || 200)}
            />
            <span>条（建议先缩小时间范围/筛选条件）</span>
          </Space>
          <div>
            <label style={{ cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={bulkOverwrite}
                onChange={(e) => setBulkOverwrite(e.target.checked)}
                style={{ marginRight: 8 }}
              />
              覆盖重算（高风险）
            </label>
          </div>
        </Space>
      </Modal>

      <div style={{ marginTop: 16 }}>
        <Card title="发货记录（每日台账）" size="small">
          {shipmentLinesQuery.isError ? (
            <Alert
              type="error"
              showIcon
              style={{ marginBottom: 12 }}
              message="台账加载失败"
              description={String((shipmentLinesQuery.error as any)?.response?.data?.detail ?? (shipmentLinesQuery.error as any)?.message ?? 'unknown')}
            />
          ) : null}
          <Tabs
            activeKey={ledgerTab}
            onChange={(k) => {
              setLedgerTab(k as any)
              setLedgerPage(1)
            }}
            tabBarExtraContent={
              ledgerTab === 'sales' ? null : <Space wrap>
                <DatePicker.RangePicker
                  value={ledgerRange as any}
                  onChange={(v) => {
                    if (v && v[0] && v[1]) setLedgerRange(v as any)
                    setLedgerPage(1)
                  }}
                  allowClear={false}
                  format="YYYY-MM-DD"
                />
                <Form
                  form={ledgerForm}
                  layout="inline"
                  onValuesChange={(changed) => {
                    if ('bound_target_kind' in changed) {
                      const k = String((changed as any).bound_target_kind ?? 'any') as any
                      const kk: 'any' | 'model' | 'bundle' = k === 'model' || k === 'bundle' ? k : 'any'
                      setBoundKind(kk)
                      setSelectedModelId(undefined)
                      ledgerForm.setFieldsValue({ bound_model_id: undefined, bound_version_label: undefined, bundle_template_code: undefined, bundle_selector: undefined })
                    }
                  }}
                  onFinish={(values) => {
                    const k0 = String(values.bound_target_kind ?? '').trim()
                    const kind: 'any' | 'model' | 'bundle' = k0 === 'model' || k0 === 'bundle' ? k0 : 'any'
                    const bundleTpl = String(values.bundle_template_code ?? '').trim().toUpperCase() || undefined
                    const bundleSel = (() => {
                      const v = (values as any).bundle_selector
                      if (Array.isArray(v)) return String(v?.[0] ?? '').trim().toUpperCase() || undefined
                      return String(v ?? '').trim().toUpperCase() || undefined
                    })()
                    const modelId = String(values.bound_model_id ?? '').trim() || undefined
                    const modelHit = modelOptions.find((x: any) => x.value === modelId)
                    const modelCode = modelHit?.code || undefined
                    const versionLabel = String(values.bound_version_label ?? '').trim() || undefined

                    // Compose `bound_model_code`:
                    // - model: use 3-letter model code (e.g. OZU)
                    // - bundle: use B-<template_code> (e.g. B-DB9EAE). Selector is filtered separately.
                    let boundModelCode: string | undefined = undefined
                    if (kind === 'model') boundModelCode = modelCode
                    if (kind === 'bundle' && bundleTpl) boundModelCode = `B-${bundleTpl}`

                    const next = {
                      channel: values.channel ? String(values.channel).trim() : undefined,
                      sku_code: values.sku_code ? String(values.sku_code).trim() : undefined,
                      order_no: values.order_no ? String(values.order_no).trim() : undefined,
                      product_link_id: values.product_link_id ? String(values.product_link_id).trim() : undefined,
                      spec_text: values.spec_text ? String(values.spec_text).trim() : undefined,
                      unresolved_reason: values.unresolved_reason ? String(values.unresolved_reason).trim() : undefined,
                      bound_target_kind: kind === 'any' ? undefined : kind,
                      bound_model_code: boundModelCode || undefined,
                      bound_version_label: kind === 'model' ? versionLabel : undefined,
                      bundle_preset_selector: kind === 'bundle' ? bundleSel : undefined,
                    }
                    setLedgerFilters(next)
                    setLedgerPage(1)
                  }}
                >
                  <Form.Item name="sku_code">
                    <Input style={{ width: 160 }} placeholder="货品条码" allowClear />
                  </Form.Item>
                  <Form.Item name="spec_text">
                    <Input style={{ width: 220 }} placeholder="交易规格" allowClear />
                  </Form.Item>
                  <Form.Item name="bound_target_kind" initialValue="any">
                    <Select
                      style={{ width: 140 }}
                      options={[
                        { value: 'any', label: '模型/套装(全部)' },
                        { value: 'model', label: '标准模型' },
                        { value: 'bundle', label: '套装' },
                      ]}
                    />
                  </Form.Item>
                  {boundKind === 'model' ? (
                    <>
                      <Form.Item name="bound_model_id">
                        <Select
                          showSearch
                          allowClear
                          style={{ width: 180 }}
                          placeholder="一级：模型"
                          filterOption={false}
                          onSearch={(s) => setModelSearch(String(s || ''))}
                          options={modelOptions as any}
                          onChange={(v) => {
                            const id = String(v ?? '').trim() || undefined
                            setSelectedModelId(id)
                            ledgerForm.setFieldsValue({ bound_version_label: undefined })
                          }}
                        />
                      </Form.Item>
                      <Form.Item name="bound_version_label">
                        <Select
                          showSearch
                          allowClear
                          style={{ width: 220 }}
                          placeholder="二级：标准版本"
                          filterOption={(input, option) =>
                            String((option as any)?.value ?? '')
                              .toLowerCase()
                              .includes(String(input || '').toLowerCase())
                          }
                          options={versionOptions as any}
                        />
                      </Form.Item>
                    </>
                  ) : null}
                  {boundKind === 'bundle' ? (
                    <>
                      <Form.Item name="bundle_template_code">
                        <Select
                          showSearch
                          allowClear
                          style={{ width: 180 }}
                          placeholder="一级：套装模板"
                          filterOption={false}
                          onSearch={(s) => setBundleSearch(String(s || ''))}
                          options={bundleTemplateOptions as any}
                        />
                      </Form.Item>
                      <Form.Item name="bundle_selector">
                        <Select
                          mode="tags"
                          maxTagCount={1}
                          style={{ width: 160 }}
                          placeholder="二级：selector(可填AE)"
                        />
                      </Form.Item>
                    </>
                  ) : null}
                  <Form.Item name="unresolved_reason">
                    <Select
                      allowClear
                      placeholder="状态"
                      style={{ width: 150 }}
                      options={[
                        { value: 'SKU_NOT_BOUND', label: '未绑定' },
                        { value: 'SPEC_EMPTY', label: '缺规格' },
                        { value: 'BOM_GENERATION_FAILED', label: 'BOM失败' },
                      ]}
                    />
                  </Form.Item>
                  <Form.Item name="channel">
                    <Input style={{ width: 120 }} placeholder="店铺" allowClear />
                  </Form.Item>
                  <Button type="primary" onClick={() => ledgerForm.submit()} loading={shipmentLinesQuery.isFetching}>
                    查询
                  </Button>
                </Form>
              </Space>
            }
            items={[
              { key: 'all', label: '全部发货' },
              { key: 'processed', label: '已处理（已计价/已落快照）' },
              { key: 'pending', label: '待处理（未计价/异常）' },
              { key: 'issues', label: '问题订单（需核对）' },
              { key: 'sales', label: '销售分析（干净列表）' },
            ]}
          />

          <div style={{ marginBottom: 10 }}>
            <Text type="secondary">
              说明：2025 模式不落 BOM 大快照但会落“计价结果/扣库”；2026 模式会落 BOM 快照。列表“已处理”口径统一为：有快照或有计价结果。
            </Text>
          </div>

          {ledgerTab !== 'sales' && isEmpty ? (
            <Alert
              type="info"
              showIcon
              style={{ marginBottom: 12 }}
              message="当前筛选范围内无记录"
              description="已默认查询最近 90 天。若你确认库里有数据，请扩大日期范围（左上角）或清空筛选条件后再查。"
            />
          ) : null}

          {ledgerTab === 'sales' ? (
            <SalesInsightsPage embedded />
          ) : (
            <Table
              rowKey="id"
              size="small"
              loading={shipmentLinesQuery.isFetching}
              dataSource={ledgerTab === 'issues' ? (data?.items ?? []).filter((x: any) => isIssueRow(x)) : (data?.items ?? [])}
              pagination={
                ledgerTab === 'issues'
                  ? false
                  : {
                      current: ledgerPage,
                      pageSize: ledgerPageSize,
                      total: data?.total ?? 0,
                      showSizeChanger: true,
                      showTotal: (t) => `共 ${t} 条`,
                    }
              }
              onChange={(pagination, _filters, sorter) => {
                const p = pagination as any
                setLedgerPage(Number(p?.current) || 1)
                setLedgerPageSize(Number(p?.pageSize) || 50)
                const s: any = Array.isArray(sorter) ? sorter[0] : sorter
                const field = String(s?.columnKey ?? s?.field ?? '').trim()
                const order = s?.order === 'ascend' || s?.order === 'descend' ? s.order : undefined
                setTableSort(field ? { field, order } : {})
              }}
              columns={columns}
              onRow={(record) => ({
                onClick: () => {
                  setDetailRow(record)
                  setDetailOpen(true)
                },
              })}
            />
          )}
        </Card>
      </div>

      <Drawer
        width={880}
        open={detailOpen}
        onClose={() => setDetailOpen(false)}
        title={
          <Space size={8} wrap>
            <span>发货行详情</span>
            {safeString(detailRow?.sku_code).trim() ? <Tag>货品条码：{safeString(detailRow?.sku_code).trim()}</Tag> : null}
            {safeString(detailRow?.channel).trim() ? <Tag color="blue">店铺：{safeString(detailRow?.channel).trim()}</Tag> : null}
          </Space>
        }
      >
        {!detailRow ? (
          <Alert type="info" showIcon message="未选择记录" />
        ) : (
          <Space direction="vertical" style={{ width: '100%' }} size={12}>
            <Card size="small" title="关键信息">
              <Descriptions size="small" column={2}>
                <Descriptions.Item label="发货日期">
                  {detailRow.completed_at ? dayjs(detailRow.completed_at).format('YYYY-MM-DD') : '-'}
                </Descriptions.Item>
                <Descriptions.Item label="处理状态">
                  {safeString((detailRow as any)?.status) === 'processed' ? (
                    <Tag color="green">已处理</Tag>
                  ) : (
                    <Tag color="red">{safeString((detailRow as any)?.unresolved_reason) || '待处理'}</Tag>
                  )}
                </Descriptions.Item>
                <Descriptions.Item label="模型/套装">
                  {safeString((detailRow as any)?.bound_model_code) ? (
                    <span>
                      <Tag color={String((detailRow as any)?.bound_model_code).startsWith('B-') || String((detailRow as any)?.bound_model_code).startsWith('Z-') ? 'purple' : 'blue'}>
                        {safeString((detailRow as any)?.bound_model_code)}
                      </Tag>
                      {safeString((detailRow as any)?.bound_model_name) ? <span style={{ color: '#666' }}> {safeString((detailRow as any)?.bound_model_name)}</span> : null}
                    </span>
                  ) : (
                    '-'
                  )}
                </Descriptions.Item>
                <Descriptions.Item label="标准版本">{safeString((detailRow as any)?.bound_version_label) || '-'}</Descriptions.Item>
                <Descriptions.Item label="交易规格" span={2}>
                  {(() => {
                    const s = normalizeTxSpecForDisplay((detailRow as any)?.spec_text)
                    if (!s) return '-'
                    return (
                      <Text ellipsis={{ tooltip: s }} style={{ maxWidth: 900, display: 'inline-block' }}>
                        {s}
                      </Text>
                    )
                  })()}
                </Descriptions.Item>
                <Descriptions.Item label="解析尺寸（从交易规格）">
                  {formatDimsText(parsedDims)}
                </Descriptions.Item>
                <Descriptions.Item label="推导面积（解析/物料）">
                  <span>
                    <Text type="secondary">解析≈</Text>
                    {parsedAreaM2 ? `${parsedAreaM2.toFixed(2)}㎡` : '-'}
                    <Text type="secondary">；物料≈</Text>
                    {bomAreaM2 ? `${bomAreaM2.toFixed(2)}㎡` : '-'}
                    {(() => {
                      const ew = bomPrimaryAreaLine?.extra_width_mm
                      const eh = bomPrimaryAreaLine?.extra_height_mm
                      const mm = snapshotMeasureMm
                      if (!ew && !eh && !mm) return null
                      const parts: string[] = []
                      if (mm) parts.push(`计价尺寸：${Math.round(mm.width_mm)}×${Math.round(mm.height_mm)}mm`)
                      if (ew || eh) parts.push(`余量：+${ew ?? 0}mm×+${eh ?? 0}mm`)
                      return <Text type="secondary">（{parts.join('；')}）</Text>
                    })()}
                  </span>
                </Descriptions.Item>
              </Descriptions>
            </Card>

            <Card size="small" title="BOM / 扣库（非盲盒，可直接核对）">
              <AntTabs
                items={[
                  {
                    key: 'bom',
                    label: 'BOM物料',
                    children: (
                      <>
                        {!snapshotId ? (
                          <Alert type="info" showIcon message="该行暂无 BOM 快照（未计价/未落快照）" />
                        ) : bomSnapshotQuery.isError ? (
                          <Alert
                            type="error"
                            showIcon
                            message="BOM快照加载失败"
                            description={String((bomSnapshotQuery.error as any)?.response?.data?.detail ?? (bomSnapshotQuery.error as any)?.message ?? 'unknown')}
                          />
                        ) : (
                          <Table
                            size="small"
                            rowKey={(r: any, i) => String(r?.line_index ?? i)}
                            pagination={false}
                            loading={bomSnapshotQuery.isFetching}
                            dataSource={((bomSnapshotQuery.data as any)?.final_material_lines ?? []) as any[]}
                            columns={[
                              { title: '编码', dataIndex: 'material_code', width: 110, ellipsis: true },
                              { title: '名称', dataIndex: 'material_name', width: 180, ellipsis: true },
                              { title: '数量', dataIndex: 'computed_quantity', width: 110, render: (v) => safeString(v) || '-' },
                              { title: '单位', dataIndex: 'unit_of_measure', width: 70, render: (v) => safeString(v) || '-' },
                              { title: '单价', dataIndex: 'bom_unit_price', width: 90, render: (v) => formatMoney(v) },
                              { title: '行成本', dataIndex: 'line_cost', width: 90, render: (v) => formatMoney(v) },
                              {
                                title: '来源',
                                key: 'src',
                                width: 160,
                                render: (_v, r: any) => safeString(r?.metadata?.source_module_name || r?.metadata?.source_module_code || ''),
                              },
                            ]}
                          />
                        )}
                      </>
                    ),
                  },
                  {
                    key: 'costing',
                    label: '成本拆分',
                    children: (
                      <Table
                        size="small"
                        rowKey="k"
                        pagination={false}
                        loading={costingQuery.isFetching}
                        dataSource={[
                          { k: 'material', name: '材料成本', v: (costingQuery.data as any)?.cost_material_total },
                          { k: 'process', name: '工序成本', v: (costingQuery.data as any)?.cost_process_total },
                          { k: 'overhead', name: '管理费/间接费', v: (costingQuery.data as any)?.cost_overhead_total },
                          { k: 'total', name: '总成本', v: (costingQuery.data as any)?.cost_total },
                        ]}
                        columns={[
                          { title: '项', dataIndex: 'name', width: 180 },
                          { title: '金额', dataIndex: 'v', render: (v) => formatMoney(v) },
                        ]}
                      />
                    ),
                  },
                  {
                    key: 'process',
                    label: '工序明细',
                    children: (
                      <>
                        {processesQuery.isError ? (
                          <Alert
                            type="error"
                            showIcon
                            message="工序明细加载失败"
                            description={String((processesQuery.error as any)?.response?.data?.detail ?? (processesQuery.error as any)?.message ?? 'unknown')}
                          />
                        ) : (processesQuery.data ?? []).length === 0 ? (
                          <Alert type="info" showIcon message="该发货行未查到工序明细（可能版本未配置工序，或该行暂无BOM快照）" />
                        ) : (
                          <Table
                            size="small"
                            rowKey={(_r: any, i) => String(i)}
                            pagination={false}
                            loading={processesQuery.isFetching}
                            dataSource={(processesQuery.data ?? []) as any}
                            columns={[
                              { title: '工序编码', dataIndex: 'process_code', width: 120, ellipsis: true },
                              { title: '工序名称', dataIndex: 'process_name', width: 160, ellipsis: true },
                              { title: '班组', dataIndex: 'team_name', width: 120, ellipsis: true },
                              { title: '计价维度', dataIndex: 'pricing_method', width: 90, render: (v) => safeString(v) || '-' },
                              { title: '计价量', dataIndex: 'measure_quantity', width: 110, render: (v) => safeString(v) || '-' },
                              { title: '类型', dataIndex: 'cost_type', width: 70, render: (v) => safeString(v) || '-' },
                              { title: '分钟单价', dataIndex: 'rate_per_minute', width: 90, render: (v) => safeString(v) || '-' },
                              { title: '计件单价', dataIndex: 'piece_rate', width: 90, render: (v) => safeString(v) || '-' },
                              { title: '总分钟', dataIndex: 'total_minutes', width: 90, render: (v) => safeString(v) || '-' },
                              { title: '工序成本', dataIndex: 'total_cost', width: 90, render: (v) => formatMoney(v) },
                              {
                                title: '提示',
                                key: 'warnings',
                                render: (_v, r: any) => {
                                  const ws = Array.isArray(r?.warnings) ? (r.warnings as any[]).map((x) => String(x)) : []
                                  const s = ws.filter(Boolean).join('；')
                                  return s ? <Tooltip title={s}><Tag color="orange">注意</Tag></Tooltip> : '-'
                                },
                              },
                            ]}
                          />
                        )}
                      </>
                    ),
                  },
                  {
                    key: 'deduct',
                    label: '扣库行',
                    children: (
                      <Table
                        size="small"
                        rowKey="id"
                        pagination={false}
                        loading={deductionsQuery.isFetching}
                        dataSource={(deductionsQuery.data ?? []) as any}
                        columns={[
                          { title: '物料编码', dataIndex: 'material_code', width: 120, ellipsis: true },
                          { title: '物料名称', dataIndex: 'material_name', width: 220, ellipsis: true },
                          { title: '数量', dataIndex: 'quantity', width: 120, render: (v) => safeString(v) || '-' },
                          { title: '单位', dataIndex: 'unit_of_measure', width: 80, render: (v) => safeString(v) || '-' },
                          {
                            title: '来源',
                            key: 'sources',
                            render: (_v, r: any) => safeString(r?.metadata?.sources ? JSON.stringify(r.metadata.sources) : ''),
                          },
                        ]}
                      />
                    ),
                  },
                ]}
              />
            </Card>

            <Card size="small" title="更多字段（抽屉）">
              <Descriptions size="small" column={2}>
                <Descriptions.Item label="订单号">{safeString((detailRow as any)?.order_no) || '-'}</Descriptions.Item>
                <Descriptions.Item label="批次ID">{safeString((detailRow as any)?.batch_id) || '-'}</Descriptions.Item>
                <Descriptions.Item label="链接ID">
                  {safeString((detailRow as any)?.product_link_id) ? (
                    <a
                      href={`https://detail.tmall.com/item.htm?id=${encodeURIComponent(String((detailRow as any)?.product_link_id))}`}
                      target="_blank"
                      rel="noreferrer"
                    >
                      {safeString((detailRow as any)?.product_link_id)}
                    </a>
                  ) : (
                    '-'
                  )}
                </Descriptions.Item>
                <Descriptions.Item label="商家编码">{safeString((detailRow as any)?.shop_spec_code) || '-'}</Descriptions.Item>
                <Descriptions.Item label="平台规格Id">{safeString((detailRow as any)?.platform_sku_id) || '-'}</Descriptions.Item>
                <Descriptions.Item label="套装锚点">
                  {safeString((detailRow as any)?.bundle_template_code) ? (
                    <Space size={6}>
                      <Tag color="purple">{safeString((detailRow as any)?.bundle_template_code)}</Tag>
                      {safeString((detailRow as any)?.bundle_preset_selector) ? <Tag>{safeString((detailRow as any)?.bundle_preset_selector)}</Tag> : null}
                    </Space>
                  ) : (
                    '-'
                  )}
                </Descriptions.Item>
                <Descriptions.Item label="spec_hash">{safeString((detailRow as any)?.spec_hash) || '-'}</Descriptions.Item>
                <Descriptions.Item label="快照ID">{safeString((detailRow as any)?.bom_snapshot_id) || '-'}</Descriptions.Item>
              </Descriptions>
            </Card>

            <Card size="small" title="规格图（来自商品关联/SKU主档）">
              {!safeString(detailRow?.sku_code).trim() ? (
                <Alert type="info" showIcon message="缺货品条码，无法取图" />
              ) : (
                <Space size={12} wrap>
                  <div>
                    <div style={{ marginBottom: 6, color: '#666' }}>规格图</div>
                    {specImageUrl ? (
                      <Image width={240} src={specImageUrl} />
                    ) : (
                      <Text type="secondary">未找到SKU主档/规格图</Text>
                    )}
                  </div>
                  <div>
                    <div style={{ marginBottom: 6, color: '#666' }}>商品图</div>
                    {productImageUrl ? (
                      <Image width={240} src={productImageUrl} />
                    ) : (
                      <Text type="secondary">未找到SKU主档/商品图</Text>
                    )}
                  </div>
                </Space>
              )}
            </Card>
          </Space>
        )}
      </Drawer>
    </div>
  )
}

const formatMoney = (v: unknown): string => {
  const s = safeString(v).trim()
  if (!s) return '-'
  const n = Number(s)
  if (!Number.isFinite(n)) return s
  return n.toFixed(2)
}

const formatPct = (v: number | null): string => {
  if (v === null || v === undefined || !Number.isFinite(v)) return '-'
  return `${(v * 100).toFixed(2)}%`
}

const capsuleStyle: React.CSSProperties = {
  display: 'inline-block',
  padding: '0px 6px',
  borderRadius: 6,
  border: '1px solid color-mix(in srgb, var(--ant-color-success) 45%, var(--ant-color-border))',
  background: 'color-mix(in srgb, var(--ant-color-success) 18%, var(--ant-color-fill-tertiary))',
  fontSize: 11,
  lineHeight: '18px',
  color: 'var(--ant-color-success)',
  whiteSpace: 'nowrap',
}

export default ShipmentLedgerPage

