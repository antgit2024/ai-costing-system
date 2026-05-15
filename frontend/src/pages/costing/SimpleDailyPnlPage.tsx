/**
 * /costing/insights/daily-pnl —— 简易日盈亏页
 *
 * 设计要点（brief §3 / §5 红线）：
 *  - 复用 ProfitInsightsPage 的「模型聚合 API + 模型详情 API」与展示骨架，但 service / analytics_service.py 一字未改。
 *  - 顶部加 1 个方案下拉 + 6 个百分比输入；切换方案 → 前端 JS 重算"运营扣减 / 真税后贡献 / 税后率 / 颜色"。
 *  - 未建模兜底成本比 unmodeled_cost_pct：BOM 成本=0/null 或 cost_quality.level==='red' 时，cost = revenue * unmodeled_cost_pct。
 *  - 不动现有 4 个 Insights 页；不动 analytics_service；不新建表（方案存 taxonomy domain='ops_assumption_scheme'）。
 */

import {
  Alert,
  Button,
  Card,
  Col,
  DatePicker,
  Descriptions,
  Divider,
  Form,
  InputNumber,
  Modal,
  Popconfirm,
  Row,
  Select,
  Space,
  Table,
  Tabs,
  Tag,
  Tooltip,
  Typography,
  message,
} from 'antd'
import { DollarOutlined, DownloadOutlined, PlusOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import dayjs from 'dayjs'
import { useEffect, useMemo, useRef, useState } from 'react'
import * as XLSX from 'xlsx'

import {
  createOpsAssumptionScheme,
  deleteOpsAssumptionScheme,
  fetchModelInsightsDetail,
  fetchModelInsightsSummary,
  fetchOpsAssumptionSchemes,
  fetchSalesLines,
  fetchSalesProfitDashboard,
  seedOpsAssumptionSchemes,
  updateOpsAssumptionScheme,
} from '@/services/planner'
import type {
  ModelInsightsDetailResponse,
  ModelInsightsSummaryItem,
  ModelInsightsSummaryResponse,
  OpsAssumptionScheme,
  SalesLineItem,
  SalesProfitDashboardResponse,
  SalesProfitDashboardTopSkuItem,
} from '@/types/planner'
import { CostQualityBadge } from '@/components/costing/CostQualityBadge'

const STORAGE_KEY = 'insights.daily_pnl.lastState.v1'

// ---------------------------------------------------------------------------
// 工具函数
// ---------------------------------------------------------------------------

const toNum = (v: any): number => {
  if (v == null || v === '') return 0
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

const formatMoney = (v: number | string | null | undefined): string => {
  if (v == null || v === '') return '-'
  const n = Number(v)
  if (!Number.isFinite(n)) return String(v)
  return n.toFixed(2)
}

const formatQty = (v: number | string | null | undefined): string => {
  if (v == null || v === '') return '-'
  const n = Number(v)
  if (!Number.isFinite(n)) return String(v)
  return n.toFixed(2).replace(/\.00$/, '')
}

const formatPercent = (v: number | string | null | undefined): string => {
  if (v == null || v === '') return '-'
  const n = Number(v)
  if (!Number.isFinite(n)) return '-'
  return `${(n * 100).toFixed(2)}%`
}

const downloadBlob = (blob: Blob, filename: string) => {
  const url = window.URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  setTimeout(() => window.URL.revokeObjectURL(url), 200)
}

// ---------------------------------------------------------------------------
// 颜色档（建议值；F1 brief §3）
// 红≤0 / 黄 0~2% / 绿>2% / 兜底→警告（⚠️）
// ---------------------------------------------------------------------------
type ProfitColor = 'success' | 'info' | 'error' | 'warning'

const colorOf = (netMargin: number | null, isUnmodeled: boolean): ProfitColor => {
  if (isUnmodeled) return 'warning'
  if (netMargin == null) return 'info'
  if (netMargin >= 0.02) return 'success'
  if (netMargin >= 0) return 'info'
  return 'error'
}

const ProfitColorTag = ({ color, margin, unmodeled }: { color: ProfitColor; margin: number | null; unmodeled: boolean }) => {
  const map: Record<ProfitColor, { tag: 'success' | 'processing' | 'error' | 'warning'; text: string; emoji: string }> = {
    success: { tag: 'success', text: '盈利', emoji: '🟢' },
    info: { tag: 'processing', text: '勉强保本', emoji: '🟡' },
    error: { tag: 'error', text: '亏损', emoji: '🔴' },
    warning: { tag: 'warning', text: '兜底估算', emoji: '⚠️' },
  }
  const cfg = map[color]
  const tip = unmodeled
    ? '该模型 BOM 未建模 / cost_quality=red，成本走"未建模兜底成本比"估算，仅供参考'
    : margin == null
      ? '销售额为 0，无法计算税后率'
      : `税后率 = ${(margin * 100).toFixed(2)}%`
  return (
    <Tooltip title={tip}>
      <Tag color={cfg.tag} style={{ marginInlineEnd: 0 }}>
        {cfg.emoji} {cfg.text}
      </Tag>
    </Tooltip>
  )
}

// ---------------------------------------------------------------------------
// 前端 JS 重算口径（brief §3 F1 算法段，service / analytics_service 不动）
// ---------------------------------------------------------------------------

interface SchemeMath {
  promotion_pct: number
  platform_fee_pct: number
  tax_pct: number
  labor_pct: number
  venue_logistics_pct: number
  unmodeled_cost_pct: number
}

interface RecomputedRow {
  revenue: number
  refund: number
  bom_cost: number
  is_unmodeled: boolean
  cost: number
  ops_deduct: number
  net_profit: number
  net_margin: number | null
  color: ProfitColor
}

const recomputeRow = (
  row: { revenue_amount?: any; refund_amount?: any; cost_amount?: any; cost_quality?: any },
  scheme: SchemeMath,
): RecomputedRow => {
  const revenue = toNum(row.revenue_amount)
  const refund = toNum(row.refund_amount)
  const bomCost = toNum(row.cost_amount)
  const costQualityLevel = String(row?.cost_quality?.level ?? '').toLowerCase()
  const isUnmodeled = !bomCost || bomCost === 0 || costQualityLevel === 'red' || costQualityLevel === 'hard_fallback'
  const cost = isUnmodeled ? revenue * scheme.unmodeled_cost_pct : bomCost
  const opsDeduct =
    revenue *
    (scheme.promotion_pct +
      scheme.platform_fee_pct +
      scheme.tax_pct +
      scheme.labor_pct +
      scheme.venue_logistics_pct)
  const netProfit = revenue - refund - opsDeduct - cost
  const netMargin = revenue > 0 ? netProfit / revenue : null
  const color = colorOf(netMargin, isUnmodeled)
  return { revenue, refund, bom_cost: bomCost, is_unmodeled: isUnmodeled, cost, ops_deduct: opsDeduct, net_profit: netProfit, net_margin: netMargin, color }
}

// ---------------------------------------------------------------------------
// 主组件
// ---------------------------------------------------------------------------

interface SchemeFormValues {
  promotion_pct: number
  platform_fee_pct: number
  tax_pct: number
  labor_pct: number
  venue_logistics_pct: number
  unmodeled_cost_pct: number
}

const DEFAULT_FORM_VALUES: SchemeFormValues = {
  promotion_pct: 17,
  platform_fee_pct: 6.1,
  tax_pct: 8,
  labor_pct: 20,
  venue_logistics_pct: 10,
  unmodeled_cost_pct: 50,
}

const schemeToForm = (s: OpsAssumptionScheme | null): SchemeFormValues => {
  if (!s) return { ...DEFAULT_FORM_VALUES }
  return {
    promotion_pct: (s.promotion_pct ?? 0) * 100,
    platform_fee_pct: (s.platform_fee_pct ?? 0) * 100,
    tax_pct: (s.tax_pct ?? 0) * 100,
    labor_pct: (s.labor_pct ?? 0) * 100,
    venue_logistics_pct: (s.venue_logistics_pct ?? 0) * 100,
    unmodeled_cost_pct: (s.unmodeled_cost_pct ?? 0) * 100,
  }
}

const formToSchemeMath = (v: SchemeFormValues): SchemeMath => ({
  promotion_pct: (v.promotion_pct ?? 0) / 100,
  platform_fee_pct: (v.platform_fee_pct ?? 0) / 100,
  tax_pct: (v.tax_pct ?? 0) / 100,
  labor_pct: (v.labor_pct ?? 0) / 100,
  venue_logistics_pct: (v.venue_logistics_pct ?? 0) / 100,
  unmodeled_cost_pct: (v.unmodeled_cost_pct ?? 0) / 100,
})

const SimpleDailyPnlPage = () => {
  const [queryForm] = Form.useForm()
  const [paramForm] = Form.useForm<SchemeFormValues>()

  // 方案 + 查询状态
  const [schemes, setSchemes] = useState<OpsAssumptionScheme[]>([])
  const [currentSchemeId, setCurrentSchemeId] = useState<string | null>(null)
  const [paramValues, setParamValues] = useState<SchemeFormValues>(DEFAULT_FORM_VALUES)
  const [loadingSchemes, setLoadingSchemes] = useState(false)
  const [savingScheme, setSavingScheme] = useState(false)
  const [createModalOpen, setCreateModalOpen] = useState(false)
  const [createName, setCreateName] = useState('')

  // 模型 summary / detail
  const [loadingSummary, setLoadingSummary] = useState(false)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [summary, setSummary] = useState<ModelInsightsSummaryResponse | null>(null)
  const [detail, setDetail] = useState<ModelInsightsDetailResponse | null>(null)
  const [selectedModelCode, setSelectedModelCode] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const didInitRef = useRef(false)

  // 商品明细：Sales Profit Dashboard（Top 赚/亏 SKU）+ Sales Lines（全量行）
  const [salesDashboard, setSalesDashboard] = useState<SalesProfitDashboardResponse | null>(null)
  const [loadingSalesDashboard, setLoadingSalesDashboard] = useState(false)
  const [salesLines, setSalesLines] = useState<SalesLineItem[]>([])
  const [loadingSalesLines, setLoadingSalesLines] = useState(false)
  const [productTabKey, setProductTabKey] = useState<'top_profit' | 'top_loss' | 'lines'>('top_profit')

  const currentScheme = useMemo(
    () => schemes.find((s) => s.id === currentSchemeId) ?? null,
    [schemes, currentSchemeId],
  )
  const schemeMath = useMemo(() => formToSchemeMath(paramValues), [paramValues])

  // -----------------------------------------------------------------------
  // 初始化：拉方案列表（空则自动 seed）
  // -----------------------------------------------------------------------
  const loadSchemes = async (autoSeedIfEmpty: boolean = false): Promise<OpsAssumptionScheme[]> => {
    setLoadingSchemes(true)
    try {
      let resp = await fetchOpsAssumptionSchemes()
      if (autoSeedIfEmpty && (!resp.items || resp.items.length === 0)) {
        try {
          await seedOpsAssumptionSchemes()
          resp = await fetchOpsAssumptionSchemes()
        } catch {
          // seed 失败时 fallback：列表保持空，让用户感知
        }
      }
      const items = resp.items ?? []
      setSchemes(items)
      return items
    } catch (e: any) {
      message.error(String(e?.response?.data?.detail ?? e?.message ?? e))
      return []
    } finally {
      setLoadingSchemes(false)
    }
  }

  useEffect(() => {
    if (didInitRef.current) return
    didInitRef.current = true
    queryForm.setFieldsValue({ range: [dayjs().subtract(7, 'day'), dayjs()], channel: undefined })
    ;(async () => {
      const items = await loadSchemes(true)
      // 选默认方案
      const def = items.find((s) => s.is_default) ?? items[0] ?? null
      if (def) {
        setCurrentSchemeId(def.id)
        const fv = schemeToForm(def)
        setParamValues(fv)
        paramForm.setFieldsValue(fv)
      }
      // 自动查一次 summary（近 7 天）
      await onQuerySummary()
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // -----------------------------------------------------------------------
  // 方案下拉切换 → 立即填值 → 列表自动重算（useMemo 触发）
  // -----------------------------------------------------------------------
  const onChangeScheme = (id: string) => {
    setCurrentSchemeId(id)
    const target = schemes.find((s) => s.id === id) ?? null
    const fv = schemeToForm(target)
    setParamValues(fv)
    paramForm.setFieldsValue(fv)
  }

  // 参数手工调整时 → 仅更新 paramValues（重算自动触发；不写库）
  const onParamFormChange = () => {
    const v = paramForm.getFieldsValue() as SchemeFormValues
    setParamValues({
      promotion_pct: toNum(v.promotion_pct),
      platform_fee_pct: toNum(v.platform_fee_pct),
      tax_pct: toNum(v.tax_pct),
      labor_pct: toNum(v.labor_pct),
      venue_logistics_pct: toNum(v.venue_logistics_pct),
      unmodeled_cost_pct: toNum(v.unmodeled_cost_pct),
    })
  }

  // -----------------------------------------------------------------------
  // 方案 CRUD
  // -----------------------------------------------------------------------
  const onSaveCurrentScheme = async () => {
    if (!currentScheme) {
      message.warning('请先选择一个方案，或使用「另存为新方案」')
      return
    }
    setSavingScheme(true)
    try {
      const math = formToSchemeMath(paramValues)
      const updated = await updateOpsAssumptionScheme(currentScheme.id, {
        promotion_pct: math.promotion_pct,
        platform_fee_pct: math.platform_fee_pct,
        tax_pct: math.tax_pct,
        labor_pct: math.labor_pct,
        venue_logistics_pct: math.venue_logistics_pct,
        unmodeled_cost_pct: math.unmodeled_cost_pct,
      })
      message.success(`已保存方案「${updated.name}」`)
      await loadSchemes()
    } catch (e: any) {
      message.error(String(e?.response?.data?.detail ?? e?.message ?? e))
    } finally {
      setSavingScheme(false)
    }
  }

  const onCreateNewScheme = async () => {
    const name = createName.trim()
    if (!name) {
      message.warning('请填写方案名')
      return
    }
    setSavingScheme(true)
    try {
      const math = formToSchemeMath(paramValues)
      const created = await createOpsAssumptionScheme({
        name,
        promotion_pct: math.promotion_pct,
        platform_fee_pct: math.platform_fee_pct,
        tax_pct: math.tax_pct,
        labor_pct: math.labor_pct,
        venue_logistics_pct: math.venue_logistics_pct,
        unmodeled_cost_pct: math.unmodeled_cost_pct,
      })
      message.success(`已新建方案「${created.name}」`)
      await loadSchemes()
      setCurrentSchemeId(created.id)
      setCreateModalOpen(false)
      setCreateName('')
    } catch (e: any) {
      message.error(String(e?.response?.data?.detail ?? e?.message ?? e))
    } finally {
      setSavingScheme(false)
    }
  }

  const onDeleteCurrentScheme = async () => {
    if (!currentScheme) return
    if (currentScheme.is_default) {
      message.warning('默认方案不可删除')
      return
    }
    setSavingScheme(true)
    try {
      await deleteOpsAssumptionScheme(currentScheme.id)
      message.success(`已删除方案「${currentScheme.name}」`)
      const items = await loadSchemes()
      const def = items.find((s) => s.is_default) ?? items[0] ?? null
      if (def) {
        setCurrentSchemeId(def.id)
        const fv = schemeToForm(def)
        setParamValues(fv)
        paramForm.setFieldsValue(fv)
      } else {
        setCurrentSchemeId(null)
      }
    } catch (e: any) {
      message.error(String(e?.response?.data?.detail ?? e?.message ?? e))
    } finally {
      setSavingScheme(false)
    }
  }

  // -----------------------------------------------------------------------
  // 模型 summary 查询
  // -----------------------------------------------------------------------
  const onQuerySummary = async () => {
    setError(null)
    const v = await queryForm.validateFields()
    const range = v.range as [dayjs.Dayjs, dayjs.Dayjs]
    const start = range[0].startOf('day').toISOString()
    const end = range[1].endOf('day').toISOString()
    const channel = v.channel?.trim() || undefined
    setLoadingSummary(true)
    try {
      const resp = await fetchModelInsightsSummary({ start, end, channel })
      setSummary(resp)
      setSelectedModelCode(null)
      setDetail(null)
      setSalesDashboard(null)
      setSalesLines([])
      try {
        if (typeof window !== 'undefined') {
          window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ start, end, channel }))
        }
      } catch {
        // ignore
      }
    } catch (e: any) {
      setError(String(e?.response?.data?.detail ?? e?.message ?? e))
    } finally {
      setLoadingSummary(false)
    }
  }

  const applyQuickRange = async (days: number) => {
    queryForm.setFieldsValue({ range: [dayjs().subtract(days, 'day'), dayjs()] })
    await onQuerySummary()
  }

  // -----------------------------------------------------------------------
  // 模型聚合（按 model_id 去重 + 累加多 channel 行）
  // -----------------------------------------------------------------------
  type AggRow = ModelInsightsSummaryItem & {
    _row_key: string
    _channels_str: string
  }

  const aggregatedRows = useMemo<AggRow[]>(() => {
    const items = summary?.items ?? []
    const byModel = new Map<string, AggRow & { _channels: Set<string> }>()
    for (const row of items) {
      const key = String((row as any).model_id || row.model_code || '').trim()
      if (!key) continue
      const existing = byModel.get(key)
      if (!existing) {
        byModel.set(key, {
          ...(row as any),
          _row_key: key,
          _channels: new Set<string>([row.channel as string].filter(Boolean) as string[]),
          _channels_str: row.channel || '',
        })
        continue
      }
      existing.shipped_qty = String(toNum(existing.shipped_qty) + toNum(row.shipped_qty))
      existing.revenue_amount = String(toNum(existing.revenue_amount) + toNum(row.revenue_amount))
      existing.cost_amount = String(toNum(existing.cost_amount) + toNum(row.cost_amount))
      existing.refund_amount = String(toNum(existing.refund_amount) + toNum(row.refund_amount))
      existing.returned_qty = String(toNum(existing.returned_qty) + toNum(row.returned_qty))
      existing._channels.add((row.channel as string) || '')
    }
    return Array.from(byModel.values()).map((r) => ({
      ...r,
      _channels_str: Array.from(r._channels).filter(Boolean).join('、'),
    })) as AggRow[]
  }, [summary])

  // 按当前方案重算 + 倒序按"税后贡献"
  // ModelInsightsSummaryItem 自带 net_profit/net_margin（string），与 RecomputedRow（number）冲突 → Omit 后再合并。
  type DisplayRow = Omit<AggRow, 'net_profit' | 'net_margin'> & RecomputedRow
  const displaySummaryRows = useMemo<DisplayRow[]>(() => {
    const rows = aggregatedRows.map((row) => {
      const rec = recomputeRow(row, schemeMath)
      return { ...row, ...rec }
    })
    rows.sort((a, b) => b.net_profit - a.net_profit)
    return rows
  }, [aggregatedRows, schemeMath])

  // 总览汇总
  const summaryTotals = useMemo(() => {
    return displaySummaryRows.reduce(
      (acc, r) => {
        acc.revenue += r.revenue
        acc.refund += r.refund
        acc.cost += r.cost
        acc.ops_deduct += r.ops_deduct
        acc.net_profit += r.net_profit
        return acc
      },
      { revenue: 0, refund: 0, cost: 0, ops_deduct: 0, net_profit: 0 },
    )
  }, [displaySummaryRows])

  const totalsNetMargin = summaryTotals.revenue > 0 ? summaryTotals.net_profit / summaryTotals.revenue : null

  // 店铺选项（来自 summary）
  const shopOptions = useMemo(() => {
    const s = new Set<string>()
    for (const it of summary?.items ?? []) {
      const v = String((it as any)?.channel ?? '').trim()
      if (v) s.add(v)
    }
    return Array.from(s)
      .sort((a, b) => a.localeCompare(b))
      .map((v) => ({ value: v, label: v }))
  }, [summary])

  // -----------------------------------------------------------------------
  // 模型详情（点击左侧某行）
  // -----------------------------------------------------------------------
  const loadDetail = async (modelCode: string) => {
    const v = queryForm.getFieldsValue()
    const range = v.range as [dayjs.Dayjs, dayjs.Dayjs]
    if (!range) return
    const start = range[0].startOf('day').toISOString()
    const end = range[1].endOf('day').toISOString()
    setLoadingDetail(true)
    try {
      const resp = await fetchModelInsightsDetail({
        start,
        end,
        channel: v.channel?.trim() || undefined,
        model_code: modelCode,
      })
      setDetail(resp)
    } catch (e: any) {
      setError(String(e?.response?.data?.detail ?? e?.message ?? e))
    } finally {
      setLoadingDetail(false)
    }
  }

  const loadSalesDashboardAndLines = async (modelCode: string) => {
    const v = queryForm.getFieldsValue()
    const range = v.range as [dayjs.Dayjs, dayjs.Dayjs]
    if (!range) return
    const start = range[0].startOf('day').toISOString()
    const end = range[1].endOf('day').toISOString()
    const channel = v.channel?.trim() || undefined
    setLoadingSalesDashboard(true)
    setLoadingSalesLines(true)
    try {
      const [dashResp, linesResp] = await Promise.all([
        fetchSalesProfitDashboard({ start, end, channel, top_n: 100 }),
        fetchSalesLines({ start, end, channel, bound_model_code: modelCode, page: 1, page_size: 200 }),
      ])
      setSalesDashboard(dashResp)
      setSalesLines(linesResp?.items ?? [])
    } catch (e: any) {
      message.error(String(e?.response?.data?.detail ?? e?.message ?? e))
    } finally {
      setLoadingSalesDashboard(false)
      setLoadingSalesLines(false)
    }
  }

  // -----------------------------------------------------------------------
  // BOM 明细数据（保留 ProfitInsightsPage 原貌）
  // -----------------------------------------------------------------------
  const bom = detail?.bom as any
  const bomCosting = (bom?.trace?.costing ?? {}) as any
  const bomFinalLines = (bom?.final_material_lines ?? []) as any[]
  const bomProcessLines = (bomCosting?.process_lines ?? []) as any[]
  const traceInventory = (bom?.trace?.inventory ?? {}) as any
  const traceInventoryLines = (traceInventory?.inventory_lines ?? []) as any[]

  const selectedVersionId = String(detail?.selected_version_id ?? '').trim()
  const selectedVersionStat = useMemo(() => {
    const versions = detail?.versions ?? []
    if (!versions.length) return null
    const picked = versions.find((x: any) => String(x?.version_id ?? '') === selectedVersionId)
    return (picked ?? versions[0]) as any
  }, [detail, selectedVersionId])
  const rangeShippedQtyRaw = (selectedVersionStat as any)?.shipped_qty
  const rangeShippedQtyNum = useMemo(() => {
    const n = Number(rangeShippedQtyRaw)
    return Number.isFinite(n) ? n : 0
  }, [rangeShippedQtyRaw])
  const sampleQtyNum = useMemo(() => {
    const n = Number((detail as any)?.sample_qty ?? 1)
    return Number.isFinite(n) && n > 0 ? n : 1
  }, [detail])

  const bomCostingTotals = useMemo(() => {
    const perPieceUnit = (() => {
      const unit = Number(bomCosting?.unit_cost)
      if (Number.isFinite(unit)) return unit
      const total = Number(bomCosting?.total_cost)
      if (!Number.isFinite(total)) return NaN
      return total / sampleQtyNum
    })()
    const perPieceMaterial = (() => {
      const raw = Number(bomCosting?.material_cost_total)
      return Number.isFinite(raw) ? raw / sampleQtyNum : NaN
    })()
    const perPieceProcess = (() => {
      const raw = Number(bomCosting?.process_cost_total)
      return Number.isFinite(raw) ? raw / sampleQtyNum : NaN
    })()
    const perPieceOverhead = (() => {
      const raw = Number(bomCosting?.overhead_cost)
      return Number.isFinite(raw) ? raw / sampleQtyNum : NaN
    })()
    const perPieceTotal = (() => {
      const raw = Number(bomCosting?.total_cost)
      if (Number.isFinite(raw)) return raw / sampleQtyNum
      return perPieceUnit
    })()
    const scale = (pp: number) => (Number.isFinite(pp) ? pp * rangeShippedQtyNum : NaN)
    return {
      perPieceUnit,
      perPieceMaterial,
      perPieceProcess,
      perPieceOverhead,
      perPieceTotal,
      rangeTotal: scale(perPieceTotal),
      rangeMaterial: scale(perPieceMaterial),
      rangeProcess: scale(perPieceProcess),
      rangeOverhead: scale(perPieceOverhead),
      overheadRate: bomCosting?.overhead_rate,
    }
  }, [bomCosting, rangeShippedQtyNum, sampleQtyNum])

  // -----------------------------------------------------------------------
  // 商品明细：Top 赚/亏 SKU 重算
  // -----------------------------------------------------------------------
  type DisplaySkuRow = SalesProfitDashboardTopSkuItem & RecomputedRow & { _row_key: string }

  const displayTopProfitSkus = useMemo<DisplaySkuRow[]>(() => {
    const rows = (salesDashboard?.top_skus_profit ?? []).map((r, idx) => {
      const rec = recomputeRow(r as any, schemeMath)
      return { ...r, ...rec, _row_key: `${r.sku_code || ''}-${idx}` }
    })
    rows.sort((a, b) => b.net_profit - a.net_profit)
    return rows
  }, [salesDashboard, schemeMath])

  const displayTopLossSkus = useMemo<DisplaySkuRow[]>(() => {
    const rows = (salesDashboard?.top_skus_loss ?? []).map((r, idx) => {
      const rec = recomputeRow(r as any, schemeMath)
      return { ...r, ...rec, _row_key: `${r.sku_code || ''}-${idx}` }
    })
    rows.sort((a, b) => a.net_profit - b.net_profit)
    return rows
  }, [salesDashboard, schemeMath])

  type DisplayLineRow = SalesLineItem & RecomputedRow & { _row_key: string }
  const displaySalesLines = useMemo<DisplayLineRow[]>(() => {
    const rows = salesLines.map((r, idx) => {
      // 行级没有 refund_amount + cost_quality，但有 revenue_amount + cost_amount
      const rec = recomputeRow(r as any, schemeMath)
      return { ...r, ...rec, _row_key: `${r.shipment_line_id || idx}` }
    })
    rows.sort((a, b) => b.net_profit - a.net_profit)
    return rows
  }, [salesLines, schemeMath])

  // -----------------------------------------------------------------------
  // Excel 导出
  // -----------------------------------------------------------------------
  const buildSchemeMetadataSheet = (rangeLabel: string, channel?: string) => {
    return [
      ['项', '值'],
      ['方案名', currentScheme?.name ?? '未命名/手工输入'],
      ['推广 %', paramValues.promotion_pct.toFixed(3)],
      ['平台扣点 %', paramValues.platform_fee_pct.toFixed(3)],
      ['税 %', paramValues.tax_pct.toFixed(3)],
      ['人工 %', paramValues.labor_pct.toFixed(3)],
      ['场地+快递 %', paramValues.venue_logistics_pct.toFixed(3)],
      ['未建模兜底成本 %', paramValues.unmodeled_cost_pct.toFixed(3)],
      ['查询时间范围', rangeLabel],
      ['店铺', channel || '全部店铺'],
      ['导出时间', dayjs().format('YYYY-MM-DD HH:mm:ss')],
    ]
  }

  const getCurrentRangeLabelAndChannel = (): { label: string; channel?: string; start: string; end: string } => {
    const v = queryForm.getFieldsValue()
    const range = v.range as [dayjs.Dayjs, dayjs.Dayjs] | undefined
    const start = range?.[0]?.format('YYYY-MM-DD') ?? '?'
    const end = range?.[1]?.format('YYYY-MM-DD') ?? '?'
    return { label: `${start} ~ ${end}`, channel: v.channel?.trim() || undefined, start, end }
  }

  const buildFileName = (key: string): string => {
    const { start, end } = getCurrentRangeLabelAndChannel()
    const ts = dayjs().format('YYYYMMDD_HHmmss')
    const schemeName = (currentScheme?.name ?? '自定义').replace(/[\\/:*?"<>|]/g, '_')
    return `简易日盈亏_${schemeName}_${start}_${end}_${ts}_${key}.xlsx`
  }

  const exportModelDailyXlsx = () => {
    if (!displaySummaryRows.length) {
      message.info('暂无数据可导出')
      return
    }
    const { label, channel } = getCurrentRangeLabelAndChannel()
    const wb = XLSX.utils.book_new()

    const metaSheet = XLSX.utils.aoa_to_sheet(buildSchemeMetadataSheet(label, channel))
    XLSX.utils.book_append_sheet(wb, metaSheet, '方案与口径')

    const dataRows = displaySummaryRows.map((r) => ({
      模型编码: r.model_code,
      模型名称: r.model_name,
      店铺: r._channels_str || '-',
      发货数量: toNum(r.shipped_qty),
      销售额: Number(r.revenue.toFixed(2)),
      真退款: Number(r.refund.toFixed(2)),
      成本来源: r.is_unmodeled ? '兜底估算' : 'BOM 真实',
      成本: Number(r.cost.toFixed(2)),
      运营扣减: Number(r.ops_deduct.toFixed(2)),
      税后贡献: Number(r.net_profit.toFixed(2)),
      税后率: r.net_margin == null ? '' : Number((r.net_margin * 100).toFixed(2)),
      颜色: r.color === 'success' ? '🟢 盈利' : r.color === 'info' ? '🟡 勉强保本' : r.color === 'error' ? '🔴 亏损' : '⚠️ 兜底估算',
      成本可信度: r.cost_quality?.level ?? '-',
    }))
    const ws = XLSX.utils.json_to_sheet(dataRows)
    XLSX.utils.book_append_sheet(wb, ws, '模型日报')

    const out = XLSX.write(wb, { bookType: 'xlsx', type: 'array' })
    downloadBlob(
      new Blob([out], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }),
      buildFileName('模型日报'),
    )
    message.success('已导出 模型日报 Excel')
  }

  const exportProductTableXlsx = (key: 'top_profit' | 'top_loss' | 'lines') => {
    const { label, channel } = getCurrentRangeLabelAndChannel()
    const wb = XLSX.utils.book_new()
    const metaSheet = XLSX.utils.aoa_to_sheet(buildSchemeMetadataSheet(label, channel))
    XLSX.utils.book_append_sheet(wb, metaSheet, '方案与口径')

    if (key === 'lines') {
      if (!displaySalesLines.length) {
        message.info('暂无数据可导出')
        return
      }
      const data = displaySalesLines.map((r) => ({
        SKU编码: r.sku_code || r.sku_no || '-',
        模型编码: r.bound_model_code || '-',
        模型名称: r.bound_model_name || '-',
        规格: r.spec_text || '-',
        店铺: r.channel || '-',
        发货完成时间: r.completed_at || '-',
        销售单价: toNum(r.sale_unit_price),
        数量: toNum(r.qty),
        销售额: Number(r.revenue.toFixed(2)),
        真退款: Number(r.refund.toFixed(2)),
        成本来源: r.is_unmodeled ? '兜底估算' : 'BOM 真实',
        成本: Number(r.cost.toFixed(2)),
        运营扣减: Number(r.ops_deduct.toFixed(2)),
        税后贡献: Number(r.net_profit.toFixed(2)),
        税后率: r.net_margin == null ? '' : Number((r.net_margin * 100).toFixed(2)),
        颜色: r.color === 'success' ? '🟢 盈利' : r.color === 'info' ? '🟡 勉强保本' : r.color === 'error' ? '🔴 亏损' : '⚠️ 兜底估算',
      }))
      const ws = XLSX.utils.json_to_sheet(data)
      XLSX.utils.book_append_sheet(wb, ws, '行级明细')
    } else {
      const rows = key === 'top_profit' ? displayTopProfitSkus : displayTopLossSkus
      if (!rows.length) {
        message.info('暂无数据可导出')
        return
      }
      const data = rows.map((r) => ({
        SKU编码: r.sku_code,
        规格: r.spec_text || '-',
        模型编码: r.bound_model_code || '-',
        模型名称: r.bound_model_name || '-',
        发货数量: toNum(r.shipped_qty),
        销售额: Number(r.revenue.toFixed(2)),
        BOM成本: Number(r.bom_cost.toFixed(2)),
        成本来源: r.is_unmodeled ? '兜底估算' : 'BOM 真实',
        成本: Number(r.cost.toFixed(2)),
        运营扣减: Number(r.ops_deduct.toFixed(2)),
        税后贡献: Number(r.net_profit.toFixed(2)),
        税后率: r.net_margin == null ? '' : Number((r.net_margin * 100).toFixed(2)),
        颜色: r.color === 'success' ? '🟢 盈利' : r.color === 'info' ? '🟡 勉强保本' : r.color === 'error' ? '🔴 亏损' : '⚠️ 兜底估算',
      }))
      const ws = XLSX.utils.json_to_sheet(data)
      XLSX.utils.book_append_sheet(wb, ws, key === 'top_profit' ? 'Top赚钱SKU' : 'Top亏损SKU')
    }
    const out = XLSX.write(wb, { bookType: 'xlsx', type: 'array' })
    const fnKey = key === 'top_profit' ? 'Top赚钱SKU' : key === 'top_loss' ? 'Top亏损SKU' : '行级明细'
    downloadBlob(
      new Blob([out], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }),
      buildFileName(fnKey),
    )
    message.success(`已导出 ${fnKey} Excel`)
  }

  // -----------------------------------------------------------------------
  // 模型日报榜单列定义
  // -----------------------------------------------------------------------
  const modelListColumns = useMemo<ColumnsType<DisplayRow>>(
    () => [
      {
        title: '模型',
        key: 'model',
        width: 200,
        fixed: 'left',
        render: (_v, r) => (
          <Space direction="vertical" size={0}>
            <Typography.Text strong style={{ fontSize: 13 }}>
              {r.model_code}
            </Typography.Text>
            <Typography.Text type="secondary" style={{ fontSize: 11 }} ellipsis>
              {r.model_name || '-'}
            </Typography.Text>
          </Space>
        ),
      },
      { title: '发货量', dataIndex: 'shipped_qty', width: 75, align: 'right', render: (v) => formatQty(v as any) },
      {
        title: '销售额',
        key: 'revenue',
        width: 100,
        align: 'right',
        render: (_v, r) => formatMoney(r.revenue),
      },
      {
        title: '真退款',
        key: 'refund',
        width: 95,
        align: 'right',
        render: (_v, r) => formatMoney(r.refund),
      },
      {
        title: '成本',
        key: 'cost',
        width: 120,
        align: 'right',
        render: (_v, r) => (
          <Space direction="vertical" size={0}>
            <Typography.Text>{formatMoney(r.cost)}</Typography.Text>
            <Typography.Text type="secondary" style={{ fontSize: 10 }}>
              {r.is_unmodeled ? `兜底${(schemeMath.unmodeled_cost_pct * 100).toFixed(0)}%` : 'BOM真实'}
            </Typography.Text>
          </Space>
        ),
      },
      {
        title: '运营扣减',
        key: 'ops_deduct',
        width: 95,
        align: 'right',
        render: (_v, r) => formatMoney(r.ops_deduct),
      },
      {
        title: '税后贡献',
        key: 'net_profit',
        width: 100,
        align: 'right',
        render: (_v, r) => (
          <Typography.Text strong style={{ color: r.net_profit >= 0 ? 'var(--ant-color-success)' : 'var(--ant-color-error)' }}>
            {formatMoney(r.net_profit)}
          </Typography.Text>
        ),
        sorter: (a, b) => a.net_profit - b.net_profit,
        defaultSortOrder: 'descend',
      },
      {
        title: '税后率',
        key: 'net_margin',
        width: 85,
        align: 'right',
        render: (_v, r) => formatPercent(r.net_margin),
      },
      {
        title: '档位',
        key: 'color',
        width: 100,
        align: 'center',
        render: (_v, r) => <ProfitColorTag color={r.color} margin={r.net_margin} unmodeled={r.is_unmodeled} />,
      },
      {
        title: '成本可信度',
        key: 'cost_quality',
        width: 110,
        align: 'center',
        render: (_v, r) => <CostQualityBadge badge={(r as any).cost_quality} size="small" />,
      },
    ],
    [schemeMath],
  )

  // SKU Top 列定义（赚/亏共用）
  const skuTopColumns = useMemo<ColumnsType<DisplaySkuRow>>(
    () => [
      {
        title: 'SKU',
        key: 'sku',
        width: 180,
        render: (_v, r) => (
          <Space direction="vertical" size={0}>
            <Typography.Text style={{ fontFamily: 'monospace', fontSize: 12 }}>{r.sku_code}</Typography.Text>
            <Typography.Text type="secondary" style={{ fontSize: 11 }} ellipsis>
              {r.spec_text || '-'}
            </Typography.Text>
          </Space>
        ),
      },
      {
        title: '模型',
        key: 'model',
        width: 140,
        render: (_v, r) => (
          <Space direction="vertical" size={0}>
            <Typography.Text style={{ fontSize: 12 }}>{r.bound_model_code || '-'}</Typography.Text>
            <Typography.Text type="secondary" style={{ fontSize: 11 }} ellipsis>
              {r.bound_model_name || '-'}
            </Typography.Text>
          </Space>
        ),
      },
      { title: '发货量', dataIndex: 'shipped_qty', width: 70, align: 'right', render: (v) => formatQty(v as any) },
      { title: '销售额', key: 'revenue', width: 95, align: 'right', render: (_v, r) => formatMoney(r.revenue) },
      { title: '成本', key: 'cost', width: 95, align: 'right', render: (_v, r) => formatMoney(r.cost) },
      { title: '运营扣减', key: 'ops_deduct', width: 90, align: 'right', render: (_v, r) => formatMoney(r.ops_deduct) },
      {
        title: '税后贡献',
        key: 'net_profit',
        width: 95,
        align: 'right',
        render: (_v, r) => (
          <Typography.Text strong style={{ color: r.net_profit >= 0 ? 'var(--ant-color-success)' : 'var(--ant-color-error)' }}>
            {formatMoney(r.net_profit)}
          </Typography.Text>
        ),
      },
      { title: '税后率', key: 'net_margin', width: 75, align: 'right', render: (_v, r) => formatPercent(r.net_margin) },
      {
        title: '档位',
        key: 'color',
        width: 100,
        align: 'center',
        render: (_v, r) => <ProfitColorTag color={r.color} margin={r.net_margin} unmodeled={r.is_unmodeled} />,
      },
    ],
    [],
  )

  // 行级明细列
  const linesColumns = useMemo<ColumnsType<DisplayLineRow>>(
    () => [
      { title: '发货完成时间', dataIndex: 'completed_at', width: 130 },
      {
        title: 'SKU',
        key: 'sku',
        width: 180,
        render: (_v, r) => (
          <Space direction="vertical" size={0}>
            <Typography.Text style={{ fontFamily: 'monospace', fontSize: 12 }}>{r.sku_code || r.sku_no || '-'}</Typography.Text>
            <Typography.Text type="secondary" style={{ fontSize: 11 }} ellipsis>
              {r.spec_text || '-'}
            </Typography.Text>
          </Space>
        ),
      },
      { title: '店铺', dataIndex: 'channel', width: 100, ellipsis: true },
      { title: '数量', dataIndex: 'qty', width: 60, align: 'right', render: (v) => formatQty(v as any) },
      { title: '销售额', key: 'revenue', width: 95, align: 'right', render: (_v, r) => formatMoney(r.revenue) },
      { title: '成本', key: 'cost', width: 95, align: 'right', render: (_v, r) => formatMoney(r.cost) },
      { title: '运营扣减', key: 'ops_deduct', width: 90, align: 'right', render: (_v, r) => formatMoney(r.ops_deduct) },
      {
        title: '税后贡献',
        key: 'net_profit',
        width: 95,
        align: 'right',
        render: (_v, r) => (
          <Typography.Text strong style={{ color: r.net_profit >= 0 ? 'var(--ant-color-success)' : 'var(--ant-color-error)' }}>
            {formatMoney(r.net_profit)}
          </Typography.Text>
        ),
      },
      { title: '税后率', key: 'net_margin', width: 75, align: 'right', render: (_v, r) => formatPercent(r.net_margin) },
      {
        title: '档位',
        key: 'color',
        width: 100,
        align: 'center',
        render: (_v, r) => <ProfitColorTag color={r.color} margin={r.net_margin} unmodeled={r.is_unmodeled} />,
      },
    ],
    [],
  )

  // BOM 物料 / 工序 / 扣库列（与 ProfitInsightsPage 一字未改）
  const bomMaterialColumns = useMemo<ColumnsType<any>>(
    () => [
      { title: '编码', dataIndex: 'material_code', width: 120, render: (v) => v ?? '-' },
      { title: '名称', dataIndex: 'material_name', width: 200, ellipsis: true, render: (v) => v ?? '-' },
      { title: '数量', dataIndex: 'computed_quantity', width: 80, render: (v) => (v == null ? '-' : String(v)) },
      { title: '单位', dataIndex: 'unit_of_measure', width: 80, render: (v) => v ?? '-' },
      { title: '损耗%', dataIndex: 'loss_rate', width: 70, render: (v) => (v == null ? '-' : String(v)) },
      { title: 'BOM单价', dataIndex: 'bom_unit_price', width: 90, render: (v) => formatMoney(String(v ?? '')) },
      { title: '行成本', dataIndex: 'line_cost', width: 90, render: (v) => formatMoney(String(v ?? '')) },
    ],
    [],
  )
  const bomProcessColumns = useMemo<ColumnsType<any>>(
    () => [
      { title: '工序编码', dataIndex: 'process_code', width: 120, ellipsis: true },
      { title: '工序名称', dataIndex: 'process_name', width: 200, ellipsis: true },
      { title: '班组', dataIndex: 'team_name', width: 100, ellipsis: true },
      { title: '计量', dataIndex: 'pricing_method', width: 80 },
      { title: '分钟', dataIndex: 'total_minutes', width: 80 },
      { title: '分钟单价', dataIndex: 'rate_per_minute', width: 80 },
      { title: '行成本', dataIndex: 'total_cost', width: 90, render: (v) => formatMoney(String(v ?? '')) },
    ],
    [],
  )
  const deductionColumns = useMemo<ColumnsType<any>>(
    () => [
      { title: '物料编码', dataIndex: 'material_code', width: 120, ellipsis: true },
      { title: '物料名称', dataIndex: 'material_name', width: 200, ellipsis: true },
      { title: '单位', dataIndex: 'unit_of_measure', width: 80 },
      { title: '扣库数量', dataIndex: 'quantity', width: 90 },
    ],
    [],
  )

  // -----------------------------------------------------------------------
  // 渲染
  // -----------------------------------------------------------------------
  return (
    <div style={{ padding: 16 }}>
      <Typography.Title level={3} style={{ margin: '0 0 12px' }}>
        <DollarOutlined style={{ marginRight: 8 }} />
        数据洞察 / 简易日盈亏
      </Typography.Title>

      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 12 }}
        message="简易日盈亏 = 销售额 - 真退款 - 运营扣减（推广+扣点+税+人工+场地快递）- 物料/兜底成本"
        description={
          <div>
            <div>
              切换顶部「运营参数方案」即可实时重算左侧模型日报与右侧商品明细的"税后贡献 / 税后率 / 颜色档位"，零延迟（前端 JS 重算，service 不动）。
            </div>
            <div>
              成本来源：BOM 已建模 → 真物料/工序/制造费；BOM 缺失 / cost_quality=red → 走"未建模兜底成本比"估算（⚠️ 兜底估算徽章）。
            </div>
          </div>
        }
      />

      {error ? <Alert type="error" showIcon message="查询失败" description={error} style={{ marginBottom: 12 }} /> : null}

      {/* 顶部：方案 + 6 参数 + CRUD 按钮 */}
      <Card size="small" style={{ marginBottom: 12 }}>
        <Row gutter={[12, 12]} align="middle">
          <Col xs={24} md={6}>
            <Space direction="vertical" size={4} style={{ width: '100%' }}>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                运营参数方案
              </Typography.Text>
              <Select
                style={{ width: '100%' }}
                value={currentSchemeId ?? undefined}
                onChange={onChangeScheme}
                placeholder="请选择方案"
                loading={loadingSchemes}
                options={schemes.map((s) => ({
                  value: s.id,
                  label: (
                    <Space>
                      {s.is_default ? <Tag color="green">默认</Tag> : null}
                      <Typography.Text strong>{s.name}</Typography.Text>
                    </Space>
                  ),
                }))}
              />
            </Space>
          </Col>
          <Col xs={24} md={18}>
            <Form
              form={paramForm}
              layout="inline"
              initialValues={DEFAULT_FORM_VALUES}
              onValuesChange={onParamFormChange}
              size="small"
            >
              <Form.Item label="推广" name="promotion_pct">
                <InputNumber min={0} max={100} step={0.1} addonAfter="%" style={{ width: 110 }} />
              </Form.Item>
              <Form.Item label="扣点" name="platform_fee_pct">
                <InputNumber min={0} max={100} step={0.1} addonAfter="%" style={{ width: 110 }} />
              </Form.Item>
              <Form.Item label="税" name="tax_pct">
                <InputNumber min={0} max={100} step={0.1} addonAfter="%" style={{ width: 110 }} />
              </Form.Item>
              <Form.Item label="人工" name="labor_pct">
                <InputNumber min={0} max={100} step={0.1} addonAfter="%" style={{ width: 110 }} />
              </Form.Item>
              <Form.Item label="场地+快递" name="venue_logistics_pct">
                <InputNumber min={0} max={100} step={0.1} addonAfter="%" style={{ width: 110 }} />
              </Form.Item>
              <Tooltip title="BOM 未建模 / 红色可信度的模型，按此比例 × 销售额估算成本">
                <Form.Item label="未建模兜底" name="unmodeled_cost_pct">
                  <InputNumber min={0} max={100} step={0.5} addonAfter="%" style={{ width: 120 }} />
                </Form.Item>
              </Tooltip>
            </Form>
          </Col>
        </Row>
        <Divider style={{ margin: '12px 0' }} />
        <Space wrap>
          <Button onClick={onSaveCurrentScheme} loading={savingScheme} disabled={!currentScheme}>
            保存当前方案
          </Button>
          <Button icon={<PlusOutlined />} onClick={() => setCreateModalOpen(true)} loading={savingScheme}>
            另存为新方案
          </Button>
          <Popconfirm
            title={`确认删除方案「${currentScheme?.name || ''}」？`}
            onConfirm={onDeleteCurrentScheme}
            disabled={!currentScheme || currentScheme.is_default}
          >
            <Button danger disabled={!currentScheme || currentScheme.is_default} loading={savingScheme}>
              删除当前方案
            </Button>
          </Popconfirm>
          {currentScheme?.is_default ? <Tag color="green">默认方案不可删除</Tag> : null}
          <Typography.Text type="secondary" style={{ fontSize: 12, marginLeft: 8 }}>
            参数手工调整后会立即重算榜单。点「保存当前方案」写回数据库供下次使用。
          </Typography.Text>
        </Space>
      </Card>

      <Modal
        open={createModalOpen}
        title="新建方案"
        onOk={onCreateNewScheme}
        onCancel={() => setCreateModalOpen(false)}
        confirmLoading={savingScheme}
        okText="新建"
        cancelText="取消"
      >
        <Form layout="vertical">
          <Form.Item label="方案名" required>
            <input
              type="text"
              value={createName}
              onChange={(e) => setCreateName(e.target.value)}
              placeholder="例：双11降推广预演"
              style={{ width: '100%', padding: '4px 8px', border: '1px solid var(--ant-color-border)', borderRadius: 4 }}
            />
          </Form.Item>
          <Typography.Text type="secondary">
            将使用当前 6 个百分比值新建方案，is_default 默认为 false。
          </Typography.Text>
        </Form>
      </Modal>

      <Row gutter={[16, 16]}>
        {/* 左侧：模型日报榜单 */}
        <Col xs={24} lg={11}>
          <Card
            size="small"
            title={
              <Space>
                <Typography.Text strong>模型日报榜单</Typography.Text>
                <Tag>按"税后贡献"倒序</Tag>
              </Space>
            }
            extra={
              <Button size="small" icon={<DownloadOutlined />} onClick={exportModelDailyXlsx} disabled={!displaySummaryRows.length}>
                导出 Excel
              </Button>
            }
          >
            <Form form={queryForm} layout="inline" size="small">
              <Form.Item label="日期范围" name="range" rules={[{ required: true, message: '请选择日期范围' }]}>
                <DatePicker.RangePicker allowClear={false} />
              </Form.Item>
              <Form.Item name="channel" noStyle>
                <Select
                  placeholder="全部店铺"
                  allowClear
                  showSearch
                  options={shopOptions}
                  style={{ width: 180 }}
                  filterOption={(input, option) =>
                    String(option?.label ?? '').toLowerCase().includes(String(input ?? '').toLowerCase())
                  }
                />
              </Form.Item>
              <Space size={6}>
                <Button size="small" onClick={() => applyQuickRange(7)}>近7天</Button>
                <Button size="small" onClick={() => applyQuickRange(30)}>近30天</Button>
                <Button size="small" onClick={() => applyQuickRange(90)}>近90天</Button>
                <Button type="primary" size="small" onClick={onQuerySummary} loading={loadingSummary}>查询</Button>
              </Space>
            </Form>

            <Divider style={{ margin: '10px 0' }} />

            {summary ? (
              <Descriptions size="small" column={5} bordered style={{ marginBottom: 8 }} labelStyle={{ width: '12%' }}>
                <Descriptions.Item label="模型数">{displaySummaryRows.length}</Descriptions.Item>
                <Descriptions.Item label="销售额">{formatMoney(summaryTotals.revenue)}</Descriptions.Item>
                <Descriptions.Item label="运营扣减">{formatMoney(summaryTotals.ops_deduct)}</Descriptions.Item>
                <Descriptions.Item label="税后贡献合计">
                  <Typography.Text
                    strong
                    style={{ color: summaryTotals.net_profit >= 0 ? 'var(--ant-color-success)' : 'var(--ant-color-error)' }}
                  >
                    {formatMoney(summaryTotals.net_profit)}
                  </Typography.Text>
                </Descriptions.Item>
                <Descriptions.Item label="整体税后率">{formatPercent(totalsNetMargin)}</Descriptions.Item>
              </Descriptions>
            ) : null}

            <Table<DisplayRow>
              size="small"
              loading={loadingSummary}
              rowKey={(r) => r._row_key}
              dataSource={displaySummaryRows}
              columns={modelListColumns}
              pagination={{ pageSize: 15, showSizeChanger: true }}
              locale={{ emptyText: '暂无数据（请选择日期范围 → 查询）' }}
              scroll={{ x: 1180 }}
              onRow={(r) => ({
                style: {
                  cursor: 'pointer',
                  background: r.model_code === selectedModelCode ? 'color-mix(in srgb, var(--ant-color-primary) 8%, transparent)' : undefined,
                },
                onClick: async () => {
                  const code = String(r.model_code ?? '').trim()
                  if (!code) return
                  setSelectedModelCode(code)
                  await Promise.all([loadDetail(code), loadSalesDashboardAndLines(code)])
                },
              })}
            />
          </Card>
        </Col>

        {/* 右侧：父 Tabs */}
        <Col xs={24} lg={13}>
          <Card
            size="small"
            title={
              selectedModelCode ? (
                <Space>
                  <Typography.Text type="secondary">已选模型：</Typography.Text>
                  <Typography.Text strong>{selectedModelCode}</Typography.Text>
                  {loadingDetail || loadingSalesDashboard || loadingSalesLines ? <Tag>加载中…</Tag> : null}
                </Space>
              ) : (
                <Typography.Text type="secondary">从左侧点击一个模型查看明细</Typography.Text>
              )
            }
          >
            {!selectedModelCode ? (
              <Alert type="info" showIcon message="请从左侧点击一个模型" />
            ) : (
              <Tabs
                defaultActiveKey="model_detail"
                items={[
                  {
                    key: 'model_detail',
                    label: '模型明细（保留原貌）',
                    children: detail ? (
                      <Tabs
                        size="small"
                        defaultActiveKey="bom"
                        items={[
                          {
                            key: 'bom',
                            label: '最终 BOM',
                            children: (
                              <Space direction="vertical" style={{ width: '100%' }} size={12}>
                                <Descriptions bordered size="small" column={3}>
                                  <Descriptions.Item label="合计成本（CNY）">
                                    <b>{formatMoney(bomCostingTotals.rangeTotal)}</b>
                                  </Descriptions.Item>
                                  <Descriptions.Item label="物料成本">{formatMoney(bomCostingTotals.rangeMaterial)}</Descriptions.Item>
                                  <Descriptions.Item label="工序成本">{formatMoney(bomCostingTotals.rangeProcess)}</Descriptions.Item>
                                  <Descriptions.Item label="制造费用">{formatMoney(bomCostingTotals.rangeOverhead)}</Descriptions.Item>
                                  <Descriptions.Item label="制造费率">{formatPercent(bomCostingTotals.overheadRate)}</Descriptions.Item>
                                  <Descriptions.Item label="单位成本">{formatMoney(bomCostingTotals.perPieceUnit)}</Descriptions.Item>
                                </Descriptions>
                                <Typography.Text strong>物料（{bomFinalLines.length}）</Typography.Text>
                                <Table
                                  size="small"
                                  pagination={false}
                                  rowKey={(r: any, idx) => String(r?.id ?? `${r?.material_ref_id ?? ''}-${idx}`)}
                                  dataSource={bomFinalLines}
                                  columns={bomMaterialColumns}
                                  scroll={{ x: 740 }}
                                />
                                <Typography.Text strong>工序（{bomProcessLines.length}）</Typography.Text>
                                <Table
                                  size="small"
                                  pagination={false}
                                  rowKey={(r: any, idx) => String(r?.process_id ?? '') + '-' + String(idx ?? 0)}
                                  dataSource={bomProcessLines}
                                  columns={bomProcessColumns}
                                  locale={{ emptyText: '暂无工序明细' }}
                                  scroll={{ x: 760 }}
                                />
                              </Space>
                            ),
                          },
                          {
                            key: 'base',
                            label: '物料组 / 工序组',
                            children: (
                              <Space direction="vertical" style={{ width: '100%' }} size={12}>
                                <Typography.Text strong>物料组（基准）</Typography.Text>
                                <Table
                                  size="small"
                                  pagination={false}
                                  rowKey={(r: any, idx) => String(r?.material_ref_id ?? r?.material_code ?? idx)}
                                  dataSource={detail.base_material_lines ?? []}
                                  columns={[
                                    { title: '编码', dataIndex: 'material_code', width: 110 },
                                    { title: '名称', dataIndex: 'material_name', width: 200, ellipsis: true },
                                    { title: '基准数量', dataIndex: 'base_quantity', width: 80 },
                                    { title: '单位', dataIndex: 'unit_of_measure', width: 80 },
                                    { title: '损耗%', dataIndex: 'loss_rate', width: 70 },
                                    { title: '单价', dataIndex: 'unit_cost', width: 80, render: (v) => formatMoney(String(v ?? '')) },
                                  ]}
                                  scroll={{ x: 620 }}
                                />
                                <Typography.Text strong>工序组（基准）</Typography.Text>
                                <Table
                                  size="small"
                                  pagination={false}
                                  rowKey={(r: any, idx) => String(r?.process_id ?? '') + '-' + String(idx ?? 0)}
                                  dataSource={detail.base_process_lines ?? []}
                                  columns={[
                                    { title: '工序编码', dataIndex: 'process_code', width: 110 },
                                    { title: '工序名称', dataIndex: 'process_name', width: 200, ellipsis: true },
                                    { title: '班组', dataIndex: 'team_name', width: 100 },
                                    { title: '分钟单价', dataIndex: 'rate_per_minute', width: 80, render: (v) => formatMoney(String(v ?? '')) },
                                  ]}
                                  scroll={{ x: 600 }}
                                />
                              </Space>
                            ),
                          },
                          {
                            key: 'deduction',
                            label: '扣库单',
                            children: (
                              <Space direction="vertical" style={{ width: '100%' }} size={12}>
                                <Typography.Text strong>扣库单（落库）</Typography.Text>
                                <Table
                                  size="small"
                                  pagination={false}
                                  rowKey={(r: any, idx) => String(r?.material_code ?? idx)}
                                  dataSource={detail.persisted_deductions ?? []}
                                  columns={deductionColumns}
                                  locale={{ emptyText: '暂无落库扣库单' }}
                                  scroll={{ x: 500 }}
                                />
                                <Typography.Text strong>扣库单（trace）</Typography.Text>
                                <Table
                                  size="small"
                                  pagination={false}
                                  rowKey={(r: any, idx) => String(r?.material_code ?? idx)}
                                  dataSource={traceInventoryLines ?? []}
                                  columns={deductionColumns}
                                  locale={{ emptyText: '暂无 trace 扣库单' }}
                                  scroll={{ x: 500 }}
                                />
                              </Space>
                            ),
                          },
                        ]}
                      />
                    ) : (
                      <Alert type="info" showIcon message="加载模型明细中…" />
                    ),
                  },
                  {
                    key: 'product_detail',
                    label: '商品明细（按当前方案重算）',
                    children: (
                      <Tabs
                        size="small"
                        activeKey={productTabKey}
                        onChange={(k) => setProductTabKey(k as any)}
                        tabBarExtraContent={
                          <Button
                            size="small"
                            icon={<DownloadOutlined />}
                            onClick={() => exportProductTableXlsx(productTabKey)}
                          >
                            导出 Excel
                          </Button>
                        }
                        items={[
                          {
                            key: 'top_profit',
                            label: `Top 赚钱 SKU (${displayTopProfitSkus.length})`,
                            children: (
                              <Table<DisplaySkuRow>
                                size="small"
                                loading={loadingSalesDashboard}
                                rowKey={(r) => r._row_key}
                                dataSource={displayTopProfitSkus}
                                columns={skuTopColumns}
                                pagination={{ pageSize: 15 }}
                                locale={{ emptyText: '暂无数据' }}
                                scroll={{ x: 990 }}
                              />
                            ),
                          },
                          {
                            key: 'top_loss',
                            label: `Top 亏损 SKU (${displayTopLossSkus.length})`,
                            children: (
                              <Table<DisplaySkuRow>
                                size="small"
                                loading={loadingSalesDashboard}
                                rowKey={(r) => r._row_key}
                                dataSource={displayTopLossSkus}
                                columns={skuTopColumns}
                                pagination={{ pageSize: 15 }}
                                locale={{ emptyText: '暂无数据' }}
                                scroll={{ x: 990 }}
                              />
                            ),
                          },
                          {
                            key: 'lines',
                            label: `全量行级明细 (${displaySalesLines.length})`,
                            children: (
                              <Table<DisplayLineRow>
                                size="small"
                                loading={loadingSalesLines}
                                rowKey={(r) => r._row_key}
                                dataSource={displaySalesLines}
                                columns={linesColumns}
                                pagination={{ pageSize: 20 }}
                                locale={{ emptyText: '暂无数据（接口范围内当前模型可能无行）' }}
                                scroll={{ x: 1050 }}
                              />
                            ),
                          },
                        ]}
                      />
                    ),
                  },
                ]}
              />
            )}
          </Card>
        </Col>
      </Row>
    </div>
  )
}

export default SimpleDailyPnlPage
