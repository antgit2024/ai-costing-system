import { Alert, Badge, Button, Card, DatePicker, Descriptions, Divider, Form, Row, Col, Select, Space, Table, Tabs, Tag, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import dayjs from 'dayjs'
import { useEffect, useMemo, useRef, useState } from 'react'

import {
  fetchModelInsightsDetail,
  fetchModelInsightsSummary,
  fetchModelsSummarySnapshot,
  refreshModelsSummarySnapshot,
} from '@/services/planner'
import type {
  ModelInsightsDetailResponse,
  ModelInsightsSummaryResponse,
} from '@/types/planner'
import { CostQualityBadge } from '@/components/costing/CostQualityBadge'

const STORAGE_KEY = 'insights.models.lastQuery.v1'

const formatPercent = (raw?: string | number | null) => {
  if (raw == null || raw === '') return '-'
  const n = Number(raw)
  if (!Number.isFinite(n)) return '-'
  return `${(n * 100).toFixed(2)}%`
}

const formatMoney = (raw?: string | number | null) => {
  if (raw == null || raw === '') return '-'
  const n = Number(raw)
  if (!Number.isFinite(n)) return String(raw)
  return n.toFixed(2)
}

const formatQty = (raw?: string | number | null) => {
  if (raw == null || raw === '') return '-'
  const n = Number(raw)
  if (!Number.isFinite(n)) return String(raw)
  return n.toFixed(2).replace(/\.00$/, '')
}

const formatCoveragePercent = (num: number, den: number) => {
  if (!den) return '-'
  const pct = (num / den) * 100
  return `${pct.toFixed(1)}%`
}

const ProfitInsightsPage = () => {
  const [form] = Form.useForm()
  const [loadingSummary, setLoadingSummary] = useState(false)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [summary, setSummary] = useState<ModelInsightsSummaryResponse | null>(null)
  const [detail, setDetail] = useState<ModelInsightsDetailResponse | null>(null)
  const [selectedModelCode, setSelectedModelCode] = useState<string | null>(null)
  const [selectedVariantCode, setSelectedVariantCode] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const didInitRef = useRef(false)
  // 默认走实时：当前用于固定历史月份校验（快照仅支持近N天）
  const [useSnapshot, setUseSnapshot] = useState(false)
  const [quickDays, setQuickDays] = useState<7 | 30 | 90>(7)
  const [computedAt, setComputedAt] = useState<string | null>(null)
  // 合并同 model_code 多渠道行；同时把 variant_breakdown 转成 children（树形二级）。
  // 数字字段累加；gross_margin 用 (gross_profit / revenue) 重算（避免直接对率求平均）。
  const unifiedRows = useMemo(() => {
    type Num = number
    type Variant = {
      variant_code?: string | null
      variant_label?: string | null
      shipped_qty: Num
      revenue_amount: Num
      cost_amount: Num
      gross_profit: Num
      gross_margin?: Num | null
      returned_qty?: Num | null
      refund_amount: Num
      line_count: Num
    }
    type Row = {
      row_kind: 'model' | 'variant'
      model_code?: string | null
      model_id?: string | null
      model_name?: string | null
      variant_code?: string | null
      variant_label?: string | null
      shipped_qty: Num
      revenue_amount: Num
      cost_amount: Num
      gross_profit: Num
      gross_margin?: Num | null
      returned_qty?: Num | null
      refund_amount: Num
      line_count?: Num
      cost_quality?: any
      children?: Row[]
      // 透传，用于 onRow 点击 / 后端 detail 查询
      _channels?: string[]
    }
    const items = summary?.items ?? []
    const groups = new Map<string, Row & { _variantMap: Map<string, Variant> }>()
    const num = (v: any): number => {
      if (v == null || v === '') return 0
      const n = Number(v)
      return Number.isFinite(n) ? n : 0
    }
    for (const it of items) {
      const code = String((it as any).model_code ?? '').trim() || `__noid__${(it as any).model_id ?? ''}`
      let g = groups.get(code)
      if (!g) {
        g = {
          row_kind: 'model',
          model_code: (it as any).model_code,
          model_id: (it as any).model_id,
          model_name: (it as any).model_name,
          shipped_qty: 0,
          revenue_amount: 0,
          cost_amount: 0,
          gross_profit: 0,
          returned_qty: 0,
          refund_amount: 0,
          cost_quality: (it as any).cost_quality ?? null,
          _channels: [],
          _variantMap: new Map(),
        }
        groups.set(code, g)
      }
      g.shipped_qty += num((it as any).shipped_qty)
      g.revenue_amount += num((it as any).revenue_amount)
      g.cost_amount += num((it as any).cost_amount)
      g.gross_profit += num((it as any).gross_profit)
      g.refund_amount += num((it as any).refund_amount)
      g.returned_qty = (g.returned_qty ?? 0) + num((it as any).returned_qty)
      const ch = String((it as any).channel ?? '').trim()
      if (ch && !g._channels!.includes(ch)) g._channels!.push(ch)
      // cost_quality 多渠道相同（来自 model 4 层链解析），保留首次
      if (!g.cost_quality && (it as any).cost_quality) g.cost_quality = (it as any).cost_quality
      const vbs: any[] = Array.isArray((it as any).variant_breakdown) ? (it as any).variant_breakdown : []
      for (const vb of vbs) {
        const vc = String(vb?.variant_code ?? '').trim() || '__unassigned__'
        let vAgg = g._variantMap.get(vc)
        if (!vAgg) {
          vAgg = {
            variant_code: vb?.variant_code ?? null,
            variant_label: vb?.variant_label ?? null,
            shipped_qty: 0,
            revenue_amount: 0,
            cost_amount: 0,
            gross_profit: 0,
            returned_qty: 0,
            refund_amount: 0,
            line_count: 0,
          }
          g._variantMap.set(vc, vAgg)
        }
        vAgg.shipped_qty += num(vb.shipped_qty)
        vAgg.revenue_amount += num(vb.revenue_amount)
        vAgg.cost_amount += num(vb.cost_amount)
        vAgg.gross_profit += num(vb.gross_profit)
        vAgg.refund_amount += num(vb.refund_amount)
        vAgg.returned_qty = (vAgg.returned_qty ?? 0) + num(vb.returned_qty)
        vAgg.line_count += num(vb.line_count)
      }
    }
    const out: Row[] = []
    for (const g of groups.values()) {
      g.gross_margin = g.revenue_amount > 0 ? g.gross_profit / g.revenue_amount : null
      const variantChildren: Row[] = Array.from(g._variantMap.values())
        .map((v) => ({
          row_kind: 'variant' as const,
          model_code: g.model_code,
          model_id: g.model_id,
          model_name: g.model_name,
          variant_code: v.variant_code ?? null,
          variant_label: v.variant_label ?? null,
          shipped_qty: v.shipped_qty,
          revenue_amount: v.revenue_amount,
          cost_amount: v.cost_amount,
          gross_profit: v.gross_profit,
          gross_margin: v.revenue_amount > 0 ? v.gross_profit / v.revenue_amount : null,
          returned_qty: v.returned_qty ?? 0,
          refund_amount: v.refund_amount,
          line_count: v.line_count,
        }))
        .sort((a, b) => b.revenue_amount - a.revenue_amount)
      // 删 _variantMap，避免污染 dataSource
      const { _variantMap, ...gNoMap } = g
      void _variantMap
      out.push({
        ...gNoMap,
        children: variantChildren.length > 0 ? variantChildren : undefined,
      })
    }
    out.sort((a, b) => b.revenue_amount - a.revenue_amount)
    return out
  }, [summary])

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

  const onQuerySummary = async () => {
    setError(null)
    const v = await form.validateFields()
    const range = v.range as [dayjs.Dayjs, dayjs.Dayjs]
    const start = range[0].startOf('day').toISOString()
    const end = range[1].endOf('day').toISOString()

    setLoadingSummary(true)
    try {
      const channel = v.channel?.trim() || undefined
      if (useSnapshot) {
        try {
          const snap = await fetchModelsSummarySnapshot({ range_days: quickDays, channel })
          setSummary(snap.data as any)
          setComputedAt(String((snap as any)?.computed_at ?? '') || null)
        } catch (e: any) {
          const status = Number(e?.response?.status)
          if (status === 404) {
            await refreshModelsSummarySnapshot({ range_days: quickDays, channel, operator_id: 'planner-ui' })
            const snap2 = await fetchModelsSummarySnapshot({ range_days: quickDays, channel })
            setSummary(snap2.data as any)
            setComputedAt(String((snap2 as any)?.computed_at ?? '') || null)
          } else {
            // fallback to live query if cache path fails
            const resp = await fetchModelInsightsSummary({ start, end, channel })
            setSummary(resp)
            setComputedAt(null)
          }
        }
      } else {
        const resp = await fetchModelInsightsSummary({ start, end, channel })
        setSummary(resp)
        setComputedAt(null)
      }
      // reset selection when query changes
      setSelectedModelCode(null)
      setDetail(null)
      try {
        if (typeof window !== 'undefined') {
          window.localStorage.setItem(
            STORAGE_KEY,
            JSON.stringify({
              start,
              end,
              channel: v.channel?.trim() || undefined,
            }),
          )
        }
      } catch {
        // ignore storage errors
      }
    } catch (e: any) {
      setError(String(e?.response?.data?.detail ?? e?.message ?? e))
    } finally {
      setLoadingSummary(false)
    }
  }

  const applyQuickRange = async (days: number) => {
    const d = days === 7 || days === 30 || days === 90 ? (days as 7 | 30 | 90) : 30
    setQuickDays(d)
    const range: [dayjs.Dayjs, dayjs.Dayjs] = [dayjs().subtract(days, 'day'), dayjs()]
    form.setFieldsValue({ range })
    await onQuerySummary()
  }

  const refreshSnapshotNow = async () => {
    setError(null)
    const v = await form.validateFields()
    const channel = v.channel?.trim() || undefined
    setLoadingSummary(true)
    try {
      await refreshModelsSummarySnapshot({ range_days: quickDays, channel, operator_id: 'planner-ui' })
      const snap = await fetchModelsSummarySnapshot({ range_days: quickDays, channel })
      setSummary(snap.data as any)
      setComputedAt(String((snap as any)?.computed_at ?? '') || null)
    } catch (e: any) {
      setError(String(e?.response?.data?.detail ?? e?.message ?? e))
    } finally {
      setLoadingSummary(false)
    }
  }

  useEffect(() => {
    if (didInitRef.current) return
    didInitRef.current = true

    // 默认展示近 7 天；不要再用历史验数月份覆盖表单默认值。
    // localStorage 仍只在用户主动查询后写入，当前页面刷新应回到业务默认口径。
    form.setFieldsValue({
      range: [dayjs().subtract(7, 'day'), dayjs()],
      channel: undefined,
    })

    // auto preview: show recent real data by default
    onQuerySummary()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const loadDetail = async (modelCode: string, versionId?: string, variantCode?: string) => {
    const v = await form.validateFields()
    const range = v.range as [dayjs.Dayjs, dayjs.Dayjs]
    const start = range[0].startOf('day').toISOString()
    const end = range[1].endOf('day').toISOString()
    setLoadingDetail(true)
    try {
      const resp = await fetchModelInsightsDetail({
        start,
        end,
        channel: v.channel?.trim() || undefined,
        model_code: modelCode,
        version_id: versionId || undefined,
        variant_code: variantCode || undefined,
      })
      setDetail(resp)
    } catch (e: any) {
      setError(String(e?.response?.data?.detail ?? e?.message ?? e))
    } finally {
      setLoadingDetail(false)
    }
  }

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
    const toNum = (v: any) => {
      const n = Number(v)
      return Number.isFinite(n) ? n : NaN
    }
    const perPieceUnit = (() => {
      const unit = toNum(bomCosting?.unit_cost)
      if (Number.isFinite(unit)) return unit
      const total = toNum(bomCosting?.total_cost)
      if (!Number.isFinite(total)) return NaN
      return total / sampleQtyNum
    })()

    const perPieceMaterial = (() => {
      const raw = toNum(bomCosting?.material_cost_total)
      return Number.isFinite(raw) ? raw / sampleQtyNum : NaN
    })()
    const perPieceProcess = (() => {
      const raw = toNum(bomCosting?.process_cost_total)
      return Number.isFinite(raw) ? raw / sampleQtyNum : NaN
    })()
    const perPieceOverhead = (() => {
      const raw = toNum(bomCosting?.overhead_cost)
      return Number.isFinite(raw) ? raw / sampleQtyNum : NaN
    })()
    const perPieceTotal = (() => {
      const raw = toNum(bomCosting?.total_cost)
      if (Number.isFinite(raw)) return raw / sampleQtyNum
      return perPieceUnit
    })()

    const scale = (perPiece: number) => (Number.isFinite(perPiece) ? perPiece * rangeShippedQtyNum : NaN)

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

  // 右侧表格列宽：完全对齐 ProductListingPage（测试台）
  const bomMaterialColumns = useMemo<ColumnsType<any>>(
    () => [
      { title: '编码', dataIndex: 'material_code', width: 120, render: (v) => v ?? '-' },
      { title: '名称', dataIndex: 'material_name', width: 220, ellipsis: true, render: (v) => v ?? '-' },
      {
        title: '来源',
        dataIndex: 'source_type',
        width: 80,
        render: (v, r: any) => {
          const t = String((r as any)?.source_type ?? v ?? '').trim()
          if (t === 'variant_item') return <Tag color="gold">变体</Tag>
          if (t === 'base_line') return <Tag>基准</Tag>
          return <Typography.Text type="secondary">-</Typography.Text>
        },
      },
      { title: '数量', dataIndex: 'computed_quantity', width: 90, render: (v) => (v == null ? '-' : String(v)) },
      { title: '单位', dataIndex: 'unit_of_measure', width: 90, render: (v) => v ?? '-' },
      { title: '计量方式', dataIndex: 'calculation_method', width: 90, render: (v) => String(v ?? '-') },
      { title: '损耗%', dataIndex: 'loss_rate', width: 90, render: (v) => (v == null ? '-' : String(v)) },
      {
        title: 'BOM单价',
        dataIndex: 'bom_unit_price',
        width: 90,
        render: (v) => {
          const miss = v == null || v === ''
          return (
            <Space size={6}>
              <Typography.Text>{formatMoney(String(v ?? ''))}</Typography.Text>
              {miss ? <Tag color="red">缺单价</Tag> : null}
            </Space>
          )
        },
      },
      {
        title: '行成本',
        dataIndex: 'line_cost',
        render: (v, r: any) => {
          const miss = (r as any)?.bom_unit_price == null || (r as any)?.bom_unit_price === ''
          return (
            <Space size={6}>
              <Typography.Text>{formatMoney(String(v ?? ''))}</Typography.Text>
              {miss ? <Tag color="red">缺单价</Tag> : null}
            </Space>
          )
        },
      },
      {
        title: '发货数量',
        key: 'range_shipped_qty',
        width: 90,
        align: 'right',
        render: () => formatQty(rangeShippedQtyRaw as any),
      },
      {
        title: '合计',
        key: 'range_total_cost',
        width: 110,
        align: 'right',
        render: (_: any, r: any) => {
          const lineCost = Number((r as any)?.line_cost)
          const perPiece = Number.isFinite(lineCost) ? lineCost / sampleQtyNum : NaN
          const total = Number.isFinite(perPiece) ? perPiece * rangeShippedQtyNum : NaN
          return formatMoney(total)
        },
      },
    ],
    [rangeShippedQtyRaw, rangeShippedQtyNum, sampleQtyNum],
  )

  const bomProcessColumns = useMemo<ColumnsType<any>>(
    () => [
      { title: '工序编码', dataIndex: 'process_code', width: 120, ellipsis: true },
      { title: '工序名称', dataIndex: 'process_name', width: 220, ellipsis: true },
      { title: '班组', dataIndex: 'team_name', width: 110, ellipsis: true },
      { title: '计量', dataIndex: 'pricing_method', width: 90 },
      { title: '计量值', dataIndex: 'measure_quantity', width: 90 },
      { title: '计价', dataIndex: 'cost_type', width: 90 },
      { title: '分钟', dataIndex: 'total_minutes', width: 90 },
      { title: '分钟单价', dataIndex: 'rate_per_minute', width: 90 },
      { title: '计件单价', dataIndex: 'piece_rate', width: 90 },
      { title: '行成本', dataIndex: 'total_cost', width: 110, render: (v) => formatMoney(String(v ?? '')) },
      {
        title: '警告',
        dataIndex: 'warnings',
        render: (v) => (Array.isArray(v) && v.length ? <Typography.Text type="warning">{String(v.join('；'))}</Typography.Text> : '-'),
      },
      {
        title: '发货数量',
        key: 'range_shipped_qty',
        width: 90,
        align: 'right',
        render: () => formatQty(rangeShippedQtyRaw as any),
      },
      {
        title: '合计',
        key: 'range_total_cost',
        width: 110,
        align: 'right',
        render: (_: any, r: any) => {
          const cost = Number((r as any)?.total_cost)
          const perPiece = Number.isFinite(cost) ? cost / sampleQtyNum : NaN
          const total = Number.isFinite(perPiece) ? perPiece * rangeShippedQtyNum : NaN
          return formatMoney(total)
        },
      },
    ],
    [rangeShippedQtyRaw, rangeShippedQtyNum, sampleQtyNum],
  )

  const deductionColumns = useMemo<ColumnsType<any>>(
    () => [
      { title: '物料编码', dataIndex: 'material_code', width: 120, ellipsis: true },
      { title: '物料名称', dataIndex: 'material_name', width: 220, ellipsis: true },
      { title: '单位', dataIndex: 'unit_of_measure', width: 90 },
      { title: '扣库数量', dataIndex: 'quantity', width: 90 },
      { title: '来源(展开)', dataIndex: 'sources', render: (v) => (v == null ? '-' : String(v)) },
    ],
    [],
  )

  const renderVersionLabelPill = (label: string) => {
    const text = String(label ?? '').trim()
    if (!text) return <Typography.Text type="secondary">-</Typography.Text>
    return (
      <span
        style={{
          display: 'inline-block',
          padding: '0px 6px',
          borderRadius: 6,
          border: '1px solid color-mix(in srgb, var(--ant-color-success) 45%, var(--ant-color-border))',
          background: 'color-mix(in srgb, var(--ant-color-success) 18%, var(--ant-color-fill-tertiary))',
          fontSize: 11,
          lineHeight: '18px',
          color: 'var(--ant-color-success)',
          whiteSpace: 'nowrap',
        }}
      >
        {text}
      </span>
    )
  }

  const modelListColumns = useMemo<ColumnsType<any>>(
    () => [
      {
        title: '编码',
        key: 'code_pill',
        width: 220,
        render: (_: any, r: any) => {
          if (r?.row_kind === 'variant') {
            const vc = String(r?.variant_code ?? '').trim()
            const label = String(r?.variant_label ?? '').trim()
            if (!vc) {
              return (
                <Space size={6}>
                  <Tag color="warning" style={{ marginInlineEnd: 0 }}>⚠ 兜底</Tag>
                  <Typography.Text type="warning" style={{ fontSize: 12 }}>未指定变体</Typography.Text>
                </Space>
              )
            }
            // 紫色 monospace Tag（与 target-picker 模式 0 完全同款），后接物料名/展示串
            const display = label.replace(new RegExp(`\\(${vc}\\)$`), '').trim() || vc
            return (
              <Space size={6}>
                <Tag color="purple" style={{ marginInlineEnd: 0, fontFamily: 'monospace' }}>{vc}</Tag>
                {display && display !== vc ? <Typography.Text style={{ fontSize: 13 }}>{display}</Typography.Text> : null}
              </Space>
            )
          }
          // 一级 model 行：[模型蓝Tag] OZU 模型名 [变体数Badge]
          const code = String(r?.model_code ?? '')
          const name = String(r?.model_name ?? '').trim()
          const vCount = Array.isArray(r?.children) ? r.children.length : 0
          return (
            <Space size={6}>
              <Tag color="blue" style={{ marginInlineEnd: 0 }}>模型</Tag>
              <Typography.Text strong>{code}</Typography.Text>
              {name ? (
                <Typography.Text type="secondary" ellipsis style={{ fontSize: 12, maxWidth: 90 }}>{name}</Typography.Text>
              ) : null}
              {vCount > 0 ? (
                <Badge count={vCount} style={{ backgroundColor: '#52c41a' }} />
              ) : null}
            </Space>
          )
        },
      },
      { title: '发货数量', dataIndex: 'shipped_qty', width: 90, align: 'right', render: (v) => formatQty(v as any) },
      { title: '销售金额', dataIndex: 'revenue_amount', width: 110, align: 'right', render: (v) => formatMoney(v as any) },
      { title: '成本', dataIndex: 'cost_amount', width: 110, align: 'right', render: (v) => formatMoney(v as any) },
      { title: '毛利', dataIndex: 'gross_profit', width: 110, align: 'right', render: (v) => formatMoney(v as any) },
      { title: '毛利率', dataIndex: 'gross_margin', width: 90, align: 'right', render: (v) => formatPercent(v as any) },
      {
        title: '退货数量',
        dataIndex: 'returned_qty',
        width: 90,
        align: 'right',
        render: (_v: any, r) => formatQty(((r as any)?.returned_qty ?? '-') as any),
      },
      { title: '退货金额', dataIndex: 'refund_amount', width: 110, align: 'right', render: (v) => formatMoney(v as any) },
      {
        title: '成本可信度',
        key: 'cost_quality',
        width: 110,
        align: 'center',
        render: (_v, r: any) => (r?.row_kind === 'model' ? <CostQualityBadge badge={r.cost_quality} size="small" /> : null),
      },
    ],
    [],
  )

  return (
    <div style={{ padding: 16 }}>
      <Typography.Title level={3} style={{ margin: '0 0 12px' }}>
        数据洞察 / 模型分析
      </Typography.Title>

      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 12 }}
        message="说明（模型分析 = 统计 + 可解释明细）"
        description={
          <div>
            <div>左侧：按店铺+日期筛选后，列出“模型统计榜单”（不展示发货明细）。</div>
            <div>右侧：点选某个模型后，展示版本、最终BOM、工序、扣库单，用于解释与核对口径。</div>
          </div>
        }
      />

      {error ? <Alert type="error" showIcon message="查询失败" description={error} style={{ marginBottom: 12 }} /> : null}

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={10}>
          <Card
            size="small"
            title="模型统计榜单"
            extra={<Typography.Text type="secondary">选店铺+日期 → 查询 → 点击模型看右侧明细</Typography.Text>}
          >
            <Form
              form={form}
              layout="vertical"
              initialValues={{
                range: [dayjs().subtract(7, 'day'), dayjs()],
              }}
            >
              <Row gutter={12}>
                <Col span={24}>
                  <Form.Item label="店铺" name="channel">
                    <Select
                      placeholder="可选：选择店铺（不选=全部店铺）"
                      allowClear
                      showSearch
                      options={shopOptions}
                      filterOption={(input, option) =>
                        String(option?.label ?? '').toLowerCase().includes(String(input ?? '').toLowerCase())
                      }
                    />
                  </Form.Item>
                </Col>
                <Col span={24}>
                  <Form.Item label="日期范围" name="range" rules={[{ required: true, message: '请选择日期范围' }]}>
                    <DatePicker.RangePicker allowClear={false} style={{ width: '100%' }} />
                  </Form.Item>
                </Col>
                <Col span={24}>
                  <Space wrap>
                    <Typography.Text type="secondary">快捷：</Typography.Text>
                    <Button size="small" onClick={() => applyQuickRange(7)}>
                      近7天
                    </Button>
                    <Button size="small" onClick={() => applyQuickRange(30)}>
                      近30天
                    </Button>
                    <Button size="small" onClick={() => applyQuickRange(90)}>
                      近90天
                    </Button>
                    <Tag color={useSnapshot ? 'green' : 'default'}>{useSnapshot ? '夜间缓存' : '实时计算'}</Tag>
                  </Space>
                </Col>
                <Col span={24}>
                  <Space>
                    <Button type="primary" onClick={onQuerySummary} loading={loadingSummary}>
                      查询
                    </Button>
                    <Button onClick={refreshSnapshotNow} disabled={!useSnapshot} loading={loadingSummary}>
                      刷新数据
                    </Button>
                    <Button onClick={() => setUseSnapshot((v) => !v)} disabled={loadingSummary}>
                      {useSnapshot ? '切到实时' : '切到缓存'}
                    </Button>
                    <Button
                      onClick={() => {
                        form.resetFields()
                        setSummary(null)
                        setSelectedModelCode(null)
                        setSelectedVariantCode(null)
                        setDetail(null)
                        setError(null)
                      }}
                    >
                      重置
                    </Button>
                  </Space>
                </Col>
              </Row>
            </Form>

            <Divider style={{ margin: '12px 0' }} />

            {summary && (summary.items ?? []).length === 0 ? (
              <Alert
                type="info"
                showIcon
                style={{ marginBottom: 12 }}
                message="当前范围暂无数据"
                description={
                  <Space wrap>
                    <span>建议点“近30天/近90天”确认数据范围；若仍为空，通常是发货数据未导入或完成时间不在该范围内。</span>
                    <Button size="small" onClick={() => applyQuickRange(30)}>
                      近30天
                    </Button>
                    <Button size="small" onClick={() => applyQuickRange(90)}>
                      近90天
                    </Button>
                  </Space>
                }
              />
            ) : null}

            {computedAt ? (
              <Typography.Text type="secondary" style={{ display: 'block', marginBottom: 8, fontSize: 12 }}>
                数据更新时间：{computedAt}
              </Typography.Text>
            ) : null}

            {summary ? (
              <Typography.Text
                type="secondary"
                style={{
                  display: 'block',
                  marginBottom: 10,
                  fontSize: 12,
                  lineHeight: '18px',
                }}
              >
                总发货行：{summary.total_shipment_lines ?? 0}；已归因到模型：{summary.mapped_model_lines ?? 0}（覆盖率{' '}
                {formatCoveragePercent(summary.mapped_model_lines ?? 0, summary.total_shipment_lines ?? 0)}）&nbsp;&nbsp;已计价行：
                {summary.costed_lines ?? 0}；缺成本字段行：{summary.lines_missing_costing ?? 0}
              </Typography.Text>
            ) : null}

            <Table<any>
              size="small"
              loading={loadingSummary}
              rowKey={(r: any) => (
                r?.row_kind === 'variant'
                  ? `v::${r?.model_code ?? ''}::${r?.variant_code ?? '__unassigned__'}`
                  : `m::${r?.model_code ?? r?.model_id ?? ''}`
              )}
              dataSource={unifiedRows}
              columns={modelListColumns}
              pagination={{ pageSize: 12, showSizeChanger: true }}
              locale={{ emptyText: '暂无数据（请先选择范围并查询）' }}
              indentSize={24}
              expandable={{
                rowExpandable: (r: any) => Array.isArray(r?.children) && r.children.length > 0,
                defaultExpandAllRows: false,
              }}
              onRow={(r: any) => ({
                onClick: async () => {
                  const code = String(r?.model_code ?? '').trim()
                  if (!code) return
                  if (r?.row_kind === 'variant') {
                    const vc = String(r?.variant_code ?? '').trim()
                    setSelectedModelCode(code)
                    setSelectedVariantCode(vc || null)
                    await loadDetail(code, undefined, vc || undefined)
                  } else {
                    setSelectedModelCode(code)
                    setSelectedVariantCode(null)
                    await loadDetail(code)
                  }
                },
              })}
              rowClassName={(r: any) => {
                if (r?.row_kind === 'variant') {
                  return (
                    String(r?.model_code ?? '') === String(selectedModelCode ?? '') &&
                      String(r?.variant_code ?? '') === String(selectedVariantCode ?? '')
                      ? 'ant-table-row-selected'
                      : ''
                  )
                }
                // 一级行高亮：选中模型且当前没选 variant
                return (
                  String(r?.model_code ?? '') === String(selectedModelCode ?? '') && !selectedVariantCode
                    ? 'ant-table-row-selected'
                    : ''
                )
              }}
              scroll={{ x: 1090 }}
            />
          </Card>
        </Col>

        <Col xs={24} lg={14}>
          <Card
            size="small"
            title="模型明细"
            extra={
              selectedModelCode ? (
                <Space size={8}>
                  <Typography.Text type="secondary">已选：</Typography.Text>
                  <Tag color="blue" style={{ marginInlineEnd: 0 }}>模型</Tag>
                  <Typography.Text strong>{selectedModelCode}</Typography.Text>
                  {selectedVariantCode ? (
                    <Tag color="purple" style={{ marginInlineEnd: 0, fontFamily: 'monospace' }}>{selectedVariantCode}</Tag>
                  ) : null}
                </Space>
              ) : (
                <Typography.Text type="secondary">点击一级看模型整体；点二级（紫色 Tag）看该变体明细</Typography.Text>
              )
            }
          >
            {detail ? (
              <>
                <Space wrap style={{ marginBottom: 12 }}>
                  <Typography.Text strong>{detail.model_name}</Typography.Text>
                  <Tag>{detail.model_code}</Tag>
                  {loadingDetail ? <Tag>加载中…</Tag> : null}
                </Space>

                <Card size="small" title="版本（本次范围内出现过的版本）" style={{ marginBottom: 12 }}>
                  <Table
                    size="small"
                    pagination={false}
                    rowKey={(r: any) => String(r.version_id)}
                    dataSource={detail.versions ?? []}
                    columns={[
                      {
                        title: '版本',
                        key: 'ver',
                        width: 260,
                        render: (_: any, r: any) => renderVersionLabelPill(String(r.version_label ?? String(r.version_id).slice(0, 8))),
                      },
                      { title: '发货数量', dataIndex: 'shipped_qty', width: 100, render: formatQty },
                      { title: '销售额', dataIndex: 'revenue_amount', width: 110, render: formatMoney },
                      { title: '物料成本', dataIndex: 'cost_material_amount', width: 110, render: formatMoney },
                      { title: '人工成本', dataIndex: 'cost_process_amount', width: 110, render: formatMoney },
                      { title: '制造费用', dataIndex: 'cost_overhead_amount', width: 110, render: formatMoney },
                      { title: '成本', dataIndex: 'cost_amount', width: 110, render: formatMoney },
                      { title: '毛利率', dataIndex: 'gross_margin', width: 100, render: formatPercent },
                      { title: '行数', dataIndex: 'line_count', width: 80, render: (v) => String(v ?? '-') },
                    ]}
                    onRow={(r: any) => ({
                      onClick: async () => {
                        if (!selectedModelCode) return
                        await loadDetail(selectedModelCode, String(r.version_id))
                      },
                    })}
                    rowClassName={(r: any) =>
                      String(r.version_id || '') === String(detail.selected_version_id || '') ? 'ant-table-row-selected' : ''
                    }
                    scroll={{ x: 1250 }}
                  />
                </Card>

                <Tabs
                  defaultActiveKey="bom"
                  items={[
                    {
                      key: 'bom',
                      label: `最终 BOM（final_material_lines）`,
                      children: (
                        <Space direction="vertical" style={{ width: '100%' }} size={12}>
                          <Descriptions bordered size="small" column={3}>
                            <Descriptions.Item label="合计成本（CNY）">
                              <b>{formatMoney(bomCostingTotals.rangeTotal)}</b>
                            </Descriptions.Item>
                            <Descriptions.Item label="物料成本（CNY）">{formatMoney(bomCostingTotals.rangeMaterial)}</Descriptions.Item>
                            <Descriptions.Item label="工序成本（CNY）">{formatMoney(bomCostingTotals.rangeProcess)}</Descriptions.Item>
                            <Descriptions.Item label="制造费用（CNY）">{formatMoney(bomCostingTotals.rangeOverhead)}</Descriptions.Item>
                            <Descriptions.Item label="制造费率">{formatPercent(bomCostingTotals.overheadRate)}</Descriptions.Item>
                            <Descriptions.Item label="单位成本（CNY/件）">{formatMoney(bomCostingTotals.perPieceUnit)}</Descriptions.Item>
                          </Descriptions>

                          <Divider style={{ margin: '4px 0' }} />
                          <Typography.Text strong>物料（{bomFinalLines.length}）</Typography.Text>
                          <Table
                            size="small"
                            pagination={false}
                            rowKey={(r: any, idx) => String(r?.id ?? `${r?.material_ref_id ?? ''}-${r?.sequence_order ?? ''}-${idx}`)}
                            dataSource={bomFinalLines}
                            columns={bomMaterialColumns}
                            scroll={{ x: 950 }}
                            summary={(pageData) => {
                              const total = pageData.reduce((acc, r: any) => {
                                const lineCost = Number((r as any)?.line_cost)
                                const perPiece = Number.isFinite(lineCost) ? lineCost / sampleQtyNum : NaN
                                const t = Number.isFinite(perPiece) ? perPiece * rangeShippedQtyNum : NaN
                                return acc + (Number.isFinite(t) ? t : 0)
                              }, 0)
                              return (
                                <Table.Summary fixed>
                                  <Table.Summary.Row>
                                    <Table.Summary.Cell index={0} colSpan={9}>
                                      <Typography.Text strong>总计</Typography.Text>
                                    </Table.Summary.Cell>
                                    <Table.Summary.Cell index={9} align="right">
                                      <Typography.Text strong>{formatQty(rangeShippedQtyRaw as any)}</Typography.Text>
                                    </Table.Summary.Cell>
                                    <Table.Summary.Cell index={10} align="right">
                                      <Typography.Text strong>{formatMoney(total)}</Typography.Text>
                                    </Table.Summary.Cell>
                                  </Table.Summary.Row>
                                </Table.Summary>
                              )
                            }}
                          />

                          <Divider style={{ margin: '4px 0' }} />
                          <Typography.Text strong>工序（{bomProcessLines.length}）</Typography.Text>
                          <Table
                            size="small"
                            pagination={false}
                            rowKey={(r: any, idx) => String(r?.process_id ?? '') + '-' + String(idx ?? 0)}
                            dataSource={bomProcessLines}
                            columns={bomProcessColumns}
                            locale={{ emptyText: '暂无工序明细（样本BOM未返回 process_lines）' }}
                            scroll={{ x: 1100 }}
                            summary={(pageData) => {
                              const total = pageData.reduce((acc, r: any) => {
                                const cost = Number((r as any)?.total_cost)
                                const perPiece = Number.isFinite(cost) ? cost / sampleQtyNum : NaN
                                const t = Number.isFinite(perPiece) ? perPiece * rangeShippedQtyNum : NaN
                                return acc + (Number.isFinite(t) ? t : 0)
                              }, 0)
                              return (
                                <Table.Summary fixed>
                                  <Table.Summary.Row>
                                    <Table.Summary.Cell index={0} colSpan={11}>
                                      <Typography.Text strong>总计</Typography.Text>
                                    </Table.Summary.Cell>
                                    <Table.Summary.Cell index={11} align="right">
                                      <Typography.Text strong>{formatQty(rangeShippedQtyRaw as any)}</Typography.Text>
                                    </Table.Summary.Cell>
                                    <Table.Summary.Cell index={12} align="right">
                                      <Typography.Text strong>{formatMoney(total)}</Typography.Text>
                                    </Table.Summary.Cell>
                                  </Table.Summary.Row>
                                </Table.Summary>
                              )
                            }}
                          />
                        </Space>
                      ),
                    },
                    {
                      key: 'base',
                      label: '物料组 / 工序组（基准清单）',
                      children: (
                        <Space direction="vertical" style={{ width: '100%' }} size={12}>
                          <Typography.Text strong>物料组（基准）</Typography.Text>
                          <Table
                            size="small"
                            pagination={false}
                            rowKey={(r: any, idx) => String(r?.material_ref_id ?? r?.material_code ?? idx)}
                            dataSource={detail.base_material_lines ?? []}
                            columns={[
                              { title: '编码', dataIndex: 'material_code', width: 120, render: (v) => v ?? '-' },
                              { title: '名称', dataIndex: 'material_name', width: 220, ellipsis: true, render: (v) => v ?? '-' },
                              { title: '基准数量', dataIndex: 'base_quantity', width: 90, render: (v) => (v == null ? '-' : String(v)) },
                              { title: '单位', dataIndex: 'unit_of_measure', width: 90, render: (v) => v ?? '-' },
                              { title: '计量方式', dataIndex: 'calculation_method', width: 90, render: (v) => String(v ?? '-') },
                              { title: '损耗%', dataIndex: 'loss_rate', width: 90, render: (v) => (v == null ? '-' : String(v)) },
                              { title: '单价', dataIndex: 'unit_cost', width: 90, render: (v) => formatMoney(String(v ?? '')) },
                              { title: '备注', dataIndex: 'notes', render: (v) => String(v ?? '-') },
                            ]}
                            scroll={{ x: 950 }}
                          />

                          <Typography.Text strong>工序组（基准）</Typography.Text>
                          <Table
                            size="small"
                            pagination={false}
                            rowKey={(r: any, idx) => String(r?.process_id ?? '') + '-' + String(idx ?? 0)}
                            dataSource={detail.base_process_lines ?? []}
                            columns={[
                              { title: '工序编码', dataIndex: 'process_code', width: 120, ellipsis: true },
                              { title: '工序名称', dataIndex: 'process_name', width: 220, ellipsis: true },
                              { title: '班组', dataIndex: 'team_name', width: 110, ellipsis: true },
                              { title: '计量', dataIndex: 'pricing_method', width: 90 },
                              { title: '分钟单价', dataIndex: 'rate_per_minute', width: 90, render: (v) => formatMoney(String(v ?? '')) },
                              { title: '计件单价', dataIndex: 'piece_rate', width: 90, render: (v) => formatMoney(String(v ?? '')) },
                              { title: '备注', dataIndex: 'notes', render: (v) => String(v ?? '-') },
                            ]}
                            scroll={{ x: 950 }}
                          />
                        </Space>
                      ),
                    },
                    {
                      key: 'deduction',
                      label: '扣库单',
                      children: (
                        <Space direction="vertical" style={{ width: '100%' }} size={12}>
                          <Alert
                            type="info"
                            showIcon
                            message="扣库单口径"
                            description="优先展示该样本发货行“落库扣库单”（更适合对账）；若没有落库数据，也可参考样本BOM trace.inventory。"
                          />
                          <Typography.Text strong>扣库单（落库）</Typography.Text>
                          <Table
                            size="small"
                            pagination={false}
                            rowKey={(r: any, idx) => String(r?.material_code ?? idx)}
                            dataSource={detail.persisted_deductions ?? []}
                            columns={deductionColumns}
                            locale={{ emptyText: '暂无落库扣库单（可能是历史批次/未执行扣库）' }}
                            scroll={{ x: 650 }}
                          />

                          <Typography.Text strong>扣库单（trace）</Typography.Text>
                          <Table
                            size="small"
                            pagination={false}
                            rowKey={(r: any, idx) => String(r?.material_code ?? idx)}
                            dataSource={(traceInventoryLines ?? []).map((r: any) => ({
                              ...r,
                              sources: Array.isArray(r?.sources) ? r.sources.length : r?.sources,
                            }))}
                            columns={deductionColumns}
                            locale={{ emptyText: '暂无 trace 扣库单（请先确保样本BOM生成成功）' }}
                            scroll={{ x: 650 }}
                          />
                        </Space>
                      ),
                    },
                  ]}
                />
              </>
            ) : (
              <Alert type="info" showIcon message="请从左侧点击一个模型" />
            )}
          </Card>
        </Col>
      </Row>
    </div>
  )
}

export default ProfitInsightsPage

