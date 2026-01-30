import {
  Alert,
  Button,
  Card,
  Col,
  DatePicker,
  Form,
  Input,
  Progress,
  Row,
  Segmented,
  Select,
  Space,
  Statistic,
  Table,
  Tabs,
  Tooltip,
  Typography,
  message,
} from 'antd'
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table'
import dayjs from 'dayjs'
import isoWeek from 'dayjs/plugin/isoWeek'
import { useEffect, useMemo, useRef, useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { InfoCircleOutlined } from '@ant-design/icons'
import { LeftOutlined, RightOutlined } from '@ant-design/icons'

import {
  fetchSalesLines,
  fetchSalesProfitDashboard,
  fetchSalesProfitDashboardSnapshot,
  refreshSalesProfitDashboardSnapshot,
} from '@/services/planner'
import type { SalesLineItem, SalesLinesResponse, SalesProfitDashboardResponse, SalesProfitDashboardTopModelItem, SalesProfitDashboardTopSkuItem } from '@/types/planner'

const STORAGE_KEY = 'insights.sales.lastQuery.v1'

dayjs.extend(isoWeek)

const formatMoney = (raw?: string | null) => {
  if (raw == null || raw === '') return '-'
  const n = Number(raw)
  if (!Number.isFinite(n)) return String(raw)
  return n.toFixed(2)
}

const formatQty = (raw?: string | null) => {
  if (raw == null || raw === '') return '-'
  const n = Number(raw)
  if (!Number.isFinite(n)) return String(raw)
  return n.toFixed(2).replace(/\.00$/, '')
}

const formatDateToDay = (raw?: string | null) => {
  if (!raw) return '-'
  const s = String(raw)
  // fast path for ISO-like strings
  if (s.length >= 10 && s[4] === '-' && s[7] === '-') return s.slice(0, 10)
  const d = dayjs(s)
  if (!d.isValid()) return s
  return d.format('YYYY-MM-DD')
}

const formatDateTime = (raw?: string | null) => {
  if (!raw) return '-'
  const s = String(raw)
  const d = dayjs(s)
  if (!d.isValid()) return s
  return d.format('YYYY-MM-DD HH:mm:ss')
}

type SalesInsightsPageProps = {
  embedded?: boolean
}

type SalesPeriodMode = 'day' | 'week' | 'month' | 'custom'

const SalesInsightsPage = (props: SalesInsightsPageProps) => {
  const embedded = !!props.embedded
  const navigate = useNavigate()
  const [form] = Form.useForm()
  const [activeTab, setActiveTab] = useState<'dashboard' | 'lines'>('dashboard')
  const [linesView, setLinesView] = useState<'list' | 'rank_profit' | 'rank_loss'>('list')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [data, setData] = useState<SalesLinesResponse | null>(null)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(100)
  const [shopOptions, setShopOptions] = useState<string[]>([])
  const [useSnapshot] = useState(true)
  const [dashboardComputedAt, setDashboardComputedAt] = useState<string | null>(null)
  const [periodMode, setPeriodMode] = useState<SalesPeriodMode>('day')
  const [anchorDate, setAnchorDate] = useState(() => dayjs().subtract(1, 'day').startOf('day'))
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [lastQuery, setLastQuery] = useState<{
    start: string
    end: string
    include_missing: boolean
    channel?: string
    sku_code?: string
    order_no?: string
    product_link_id?: string
  } | null>(null)

  const didInitRef = useRef(false)

  const watchedRange = Form.useWatch('range', form) as [dayjs.Dayjs, dayjs.Dayjs] | undefined
  const watchedShop = Form.useWatch('shop', form) as string | undefined

  const computedRange = useMemo(() => {
    if (periodMode === 'custom') {
      const r = watchedRange
      if (r && r[0] && r[1]) return [r[0].startOf('day'), r[1].endOf('day')] as const
      return [dayjs().subtract(30, 'day').startOf('day'), dayjs().endOf('day')] as const
    }
    const a = anchorDate || dayjs().subtract(1, 'day').startOf('day')
    if (periodMode === 'day') return [a.startOf('day'), a.endOf('day')] as const
    if (periodMode === 'week') {
      // 上一完整周（按周一~周日）；以 anchorDate 所在周为“本周”，取本周开始日前一周
      const wkStart = a.startOf('isoWeek')
      const prevEnd = wkStart.subtract(1, 'day').endOf('day')
      const prevStart = wkStart.subtract(7, 'day').startOf('day')
      return [prevStart, prevEnd] as const
    }
    // month: 上一完整月
    const mStart = a.startOf('month')
    const prevEnd = mStart.subtract(1, 'day').endOf('day')
    const prevStart = mStart.subtract(1, 'month').startOf('month').startOf('day')
    return [prevStart, prevEnd] as const
  }, [anchorDate, periodMode, watchedRange])

  const shiftAnchorDate = (dir: -1 | 1) => {
    if (periodMode === 'custom') return
    if (periodMode === 'day') {
      setAnchorDate((d) => d.add(dir, 'day').startOf('day'))
      return
    }
    if (periodMode === 'week') {
      setAnchorDate((d) => d.add(dir, 'week').startOf('day'))
      return
    }
    setAnchorDate((d) => d.add(dir, 'month').startOf('day'))
  }

  const rangeStartIso = computedRange?.[0]?.toISOString?.()
  const rangeEndIso = computedRange?.[1]?.toISOString?.()

  const dashboardGroupBy: 'week' | 'month' = periodMode === 'month' ? 'month' : 'week'

  useEffect(() => {
    // Keep form range in sync for downstream list queries.
    if (periodMode !== 'custom') {
      form.setFieldsValue({ range: [computedRange[0], computedRange[1]] })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [periodMode, anchorDate])

  const dashboardQuery = useQuery({
    queryKey: ['sales', 'profit-dashboard', rangeStartIso, rangeEndIso, watchedShop, dashboardGroupBy],
    queryFn: async () => {
      const channel = watchedShop?.trim() || undefined
      if (useSnapshot) {
        try {
          const snap = await fetchSalesProfitDashboardSnapshot({
            start: String(rangeStartIso),
            end: String(rangeEndIso),
            group_by: dashboardGroupBy,
            top_n: 12,
            channel,
          })
          setDashboardComputedAt(String((snap as any)?.computed_at ?? '') || null)
          return snap.data as SalesProfitDashboardResponse
        } catch (e: any) {
          // If cache missing, fall back to live.
          if (Number(e?.response?.status) !== 404) {
            setDashboardComputedAt(null)
          }
        }
      }
      setDashboardComputedAt(null)
      return fetchSalesProfitDashboard(
        {
          start: String(rangeStartIso),
          end: String(rangeEndIso),
          group_by: dashboardGroupBy,
          channel,
          top_n: 12,
        },
        { timeoutMs: 60000 },
      )
    },
    enabled: !embedded && !!rangeStartIso && !!rangeEndIso,
    placeholderData: keepPreviousData,
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  })

  const refreshDashboardSnapshotNow = async () => {
    const channel = watchedShop?.trim() || undefined
    try {
      await refreshSalesProfitDashboardSnapshot({
        start: String(rangeStartIso),
        end: String(rangeEndIso),
        group_by: dashboardGroupBy,
        top_n: 12,
        channel,
        operator_id: 'planner-ui',
      })
      await dashboardQuery.refetch()
      message.success('已刷新（使用缓存）')
    } catch (e: any) {
      message.error(`刷新失败：${e?.response?.data?.detail ?? e?.message ?? 'unknown error'}`)
    }
  }

  const top100Query = useQuery({
    queryKey: ['sales', 'profit-dashboard', 'top100', rangeStartIso, rangeEndIso, watchedShop, dashboardGroupBy],
    enabled: !embedded && activeTab === 'lines' && linesView !== 'list' && !!rangeStartIso && !!rangeEndIso,
    queryFn: async () => {
      const channel = watchedShop?.trim() || undefined
      try {
        const snap = await fetchSalesProfitDashboardSnapshot({
          start: String(rangeStartIso),
          end: String(rangeEndIso),
          group_by: dashboardGroupBy,
          top_n: 100,
          channel,
        })
        return snap.data as SalesProfitDashboardResponse
      } catch (e: any) {
        const status = Number(e?.response?.status)
        if (status === 404) {
          await refreshSalesProfitDashboardSnapshot({
            start: String(rangeStartIso),
            end: String(rangeEndIso),
            group_by: dashboardGroupBy,
            top_n: 100,
            channel,
            operator_id: 'planner-ui',
          })
          const snap2 = await fetchSalesProfitDashboardSnapshot({
            start: String(rangeStartIso),
            end: String(rangeEndIso),
            group_by: dashboardGroupBy,
            top_n: 100,
            channel,
          })
          return snap2.data as SalesProfitDashboardResponse
        }
        throw e
      }
    },
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  })

  const openRankingInLinesTab = (kind: 'profit' | 'loss') => {
    setActiveTab('lines')
    setLinesView(kind === 'profit' ? 'rank_profit' : 'rank_loss')
    setError(null)
  }

  const openSkuInLinesList = async (sku_code: string) => {
    const sku = String(sku_code ?? '').trim()
    if (!sku) return
    setActiveTab('lines')
    setLinesView('list')
    setError(null)
    setPage(1)

    // Keep filters consistent with "analyze here" flow.
    form.setFieldsValue({
      sku_code: sku,
      order_no: undefined,
      product_link_id: undefined,
      bundle_template_code: undefined,
      bundle_preset_selector: undefined,
    })

    const range = computedRange as unknown as [dayjs.Dayjs, dayjs.Dayjs]
    const base = {
      start: range[0].startOf('day').toISOString(),
      end: range[1].endOf('day').toISOString(),
      include_missing: true,
      channel: watchedShop?.trim() || undefined,
      sku_code: sku,
      order_no: undefined,
      product_link_id: undefined,
      bundle_template_code: undefined,
      bundle_preset_selector: undefined,
    }
    await runQuery({ ...base, page: 1, page_size: pageSize })
  }

  const navigateToShipmentsProcessed = (params: { sku_code?: string; bundle_template_code?: string; bundle_preset_selector?: string }) => {
    const qp = new URLSearchParams()
    qp.set('tab', 'processed')
    if (rangeStartIso) qp.set('start', String(rangeStartIso))
    if (rangeEndIso) qp.set('end', String(rangeEndIso))
    const shop = String(watchedShop ?? '').trim()
    if (shop) qp.set('channel', shop)
    if (params.sku_code) qp.set('sku_code', String(params.sku_code))
    if (params.bundle_template_code) {
      qp.set('bound_target_kind', 'bundle')
      qp.set('bundle_template_code', String(params.bundle_template_code))
      if (params.bundle_preset_selector) qp.set('bundle_preset_selector', String(params.bundle_preset_selector))
    }
    qp.set('sort', 'profit_rate')
    qp.set('order', 'ascend')
    navigate(`/costing/shipments?${qp.toString()}`)
  }

  const columns = useMemo<ColumnsType<SalesLineItem>>(
    () => [
      { title: '付款时间', dataIndex: 'payment_at', width: 120, ellipsis: true, render: (v) => formatDateToDay(v) },
      { title: '发货时间', dataIndex: 'completed_at', width: 120, ellipsis: true, render: (v) => formatDateToDay(v) },
      { title: '店铺', dataIndex: 'channel', width: 160, ellipsis: true, render: (v) => String(v ?? '-') },
      { title: '货品名称', dataIndex: 'sku_name', width: 200, ellipsis: true, render: (v) => String(v ?? '-') },
      { title: '交易规格', dataIndex: 'spec_text', width: 260, ellipsis: true, render: (v) => String(v ?? '-') },
      { title: '货品条码', dataIndex: 'sku_code', width: 160, ellipsis: true, render: (v) => String(v ?? '-') },
      {
        title: '模型/套装（绑定）',
        key: 'bound_model',
        width: 260,
        render: (_v, r) => {
          const code = String((r as any)?.bound_model_code ?? '').trim()
          const name = String((r as any)?.bound_model_name ?? '').trim()
          const s = [code, name].filter(Boolean).join(' ')
          if (!s) return '-'
          return (
            <span style={{ display: 'inline-block', maxWidth: 250, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {s}
            </span>
          )
        },
      },
      {
        title: '套装',
        key: 'bundle',
        width: 260,
        render: (_v, r) => {
          const code = String((r as any)?.bundle_template_code ?? '').trim()
          const sel = String((r as any)?.bundle_preset_selector ?? '').trim().toUpperCase()
          const phrase = String((r as any)?.bundle_preset_phrase ?? '').trim()
          const s = [code, sel].filter(Boolean).join('-')
          if (!s && !phrase) return '-'
          const pillStyle = {
            display: 'inline-block',
            padding: '0px 6px',
            borderRadius: 6,
            border: '1px solid',
            borderColor: 'color-mix(in srgb, var(--ant-color-success) 45%, var(--ant-color-border))',
            background: 'color-mix(in srgb, var(--ant-color-success) 18%, var(--ant-color-fill-tertiary))',
            fontSize: 11,
            lineHeight: '18px',
            color: 'var(--ant-color-success)',
            whiteSpace: 'nowrap',
          } as const
          return (
            <span style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
              <span style={{ minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {s || '-'}
              </span>
              {phrase ? (
                <Tooltip title={phrase}>
                  <span style={pillStyle}>{phrase}</span>
                </Tooltip>
              ) : null}
            </span>
          )
        },
      },
      { title: '销售单价', dataIndex: 'sale_unit_price', width: 110, render: (v) => formatMoney(v) },
      { title: '数量', dataIndex: 'qty', width: 90, render: (v) => formatQty(v) },
      { title: '销售金额', dataIndex: 'revenue_amount', width: 110, render: (v) => formatMoney(v) },
      { title: '成本单价', dataIndex: 'cost_unit_price', width: 110, render: (v) => formatMoney(v) },
      { title: '成本金额', dataIndex: 'cost_amount', width: 110, render: (v) => formatMoney(v) },
      {
        title: '利润',
        key: 'gross_profit',
        width: 110,
        render: (_v, r) => {
          const revenue = Number(r.revenue_amount ?? '')
          const cost = Number(r.cost_amount ?? '')
          if (!Number.isFinite(revenue) || !Number.isFinite(cost)) return '-'
          return formatMoney(String(revenue - cost))
        },
      },
      {
        title: '利润率',
        key: 'gross_margin',
        width: 110,
        render: (_v, r) => {
          const revenue = Number(r.revenue_amount ?? '')
          const cost = Number(r.cost_amount ?? '')
          if (!Number.isFinite(revenue) || !Number.isFinite(cost) || revenue === 0) return '-'
          const margin = ((revenue - cost) / revenue) * 100
          if (!Number.isFinite(margin)) return '-'
          return `${margin.toFixed(2)}%`
        },
      },
      { title: '原始单号', dataIndex: 'order_no', width: 160, ellipsis: true, render: (v) => String(v ?? '-') },
      { title: '商品链接ID', dataIndex: 'product_link_id', width: 180, ellipsis: true, render: (v) => String(v ?? '-') },
      { title: '标记', dataIndex: 'mark', width: 120, ellipsis: true, render: (v) => String(v ?? '-') },
      { title: '备注', dataIndex: 'note', width: 220, ellipsis: true, render: (v) => String(v ?? '-') },
    ],
    [],
  )

  const runQuery = async (q: {
    start: string
    end: string
    include_missing: boolean
    channel?: string
    sku_code?: string
    order_no?: string
    product_link_id?: string
    bundle_template_code?: string
    bundle_preset_selector?: string
    page: number
    page_size: number
  }) => {
    setLoading(true)
    try {
      const resp = await fetchSalesLines(q)
      setData(resp)
      setShopOptions((prev) => {
        const next = new Set(prev)
        for (const it of resp.items ?? []) {
          if (it.channel) next.add(it.channel)
        }
        return Array.from(next).sort()
      })
      setPage(q.page)
      setPageSize(q.page_size)
    } catch (e: any) {
      setError(String(e?.response?.data?.detail ?? e?.message ?? e))
      setData(null)
    } finally {
      setLoading(false)
    }
  }

  const onQuery = async () => {
    setError(null)
    const v = await form.validateFields()
    const range = computedRange as unknown as [dayjs.Dayjs, dayjs.Dayjs]
    const base = {
      start: range[0].startOf('day').toISOString(),
      end: range[1].endOf('day').toISOString(),
      include_missing: true,
      channel: v.shop?.trim() || undefined,
      sku_code: v.sku_code?.trim() || undefined,
      order_no: v.order_no?.trim() || undefined,
      product_link_id: v.product_link_id?.trim() || undefined,
      bundle_template_code: v.bundle_template_code?.trim() || undefined,
      bundle_preset_selector: v.bundle_preset_selector?.trim() || undefined,
    }
    setLastQuery(base)
    try {
      if (typeof window !== 'undefined') {
        window.localStorage.setItem(
          STORAGE_KEY,
          JSON.stringify({
            // keep only minimal "tmall-like" memory; avoid sticky barcode etc.
            start: base.start,
            end: base.end,
            include_missing: true,
            channel: base.channel,
            page_size: pageSize,
          }),
        )
      }
    } catch {
      // ignore storage errors (private mode / quota)
    }
    if (embedded) {
      await runQuery({ ...base, page: 1, page_size: pageSize })
      return
    }
    if (activeTab === 'lines') {
      if (linesView !== 'list') {
        await top100Query.refetch()
        return
      }
      await runQuery({ ...base, page: 1, page_size: pageSize })
      return
    }
    dashboardQuery.refetch().then((res) => {
      const status = (res as any)?.error?.response?.status
      if (status === 404) message.warning('后端尚未部署销售利润看板接口（/api/planner/analytics/sales/profit-dashboard）。')
    })
  }

  const applyQuickRange = async (days: number) => {
    // legacy helper: keep for empty-state buttons; switch to custom range
    setPeriodMode('custom')
    const range: [dayjs.Dayjs, dayjs.Dayjs] = [dayjs().subtract(days, 'day'), dayjs()]
    form.setFieldsValue({ range })
    await onQuery()
  }

  useEffect(() => {
    if (didInitRef.current) return
    didInitRef.current = true

    const applyAndQuery = async () => {
      try {
        const raw = typeof window !== 'undefined' ? window.localStorage.getItem(STORAGE_KEY) : null
        if (!raw) {
          // default: show last 30 days on dashboard
          form.setFieldsValue({ range: [dayjs().subtract(30, 'day'), dayjs()] })
          return
        }
        const saved = JSON.parse(raw || '{}') as any
        const start = String(saved?.start ?? '').trim()
        const end = String(saved?.end ?? '').trim()
        const nextPageSize = Number(saved?.page_size)
        if (Number.isFinite(nextPageSize) && nextPageSize > 0) setPageSize(nextPageSize)
        // include_missing is fixed to true (no toggle)

        const range: [dayjs.Dayjs, dayjs.Dayjs] = [
          dayjs(start || dayjs().subtract(30, 'day').startOf('day').toISOString()),
          dayjs(end || dayjs().endOf('day').toISOString()),
        ]
        form.setFieldsValue({
          range,
          shop: saved?.channel ?? undefined,
          // do not auto-restore advanced filters (avoid "barcode stuck")
          sku_code: undefined,
          order_no: undefined,
          product_link_id: undefined,
        })

        const base = {
          start: range[0].startOf('day').toISOString(),
          end: range[1].endOf('day').toISOString(),
          include_missing: true,
          channel: String(saved?.channel ?? '').trim() || undefined,
          sku_code: undefined,
          order_no: undefined,
          product_link_id: undefined,
        }
        setLastQuery(base)
      } catch {
        form.setFieldsValue({ range: [dayjs().subtract(30, 'day'), dayjs()] })
      }
    }

    applyAndQuery()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const onPageChange = async (p: number, ps: number) => {
    setError(null)
    const base = lastQuery
    if (base) {
      await runQuery({ ...base, page: p, page_size: ps })
      return
    }
    // fallback: if user paginates before first query, read current form state
    const v = form.getFieldsValue(true) as any
    const fallback = {
      start: computedRange?.[0]?.startOf?.('day')?.toISOString?.() ?? dayjs().startOf('day').toISOString(),
      end: computedRange?.[1]?.endOf?.('day')?.toISOString?.() ?? dayjs().endOf('day').toISOString(),
      include_missing: true,
      channel: v.shop?.trim() || undefined,
      sku_code: v.sku_code?.trim() || undefined,
      order_no: v.order_no?.trim() || undefined,
      product_link_id: v.product_link_id?.trim() || undefined,
    }
    setLastQuery(fallback)
    await runQuery({ ...fallback, page: p, page_size: ps })
  }

  const pagination: TablePaginationConfig = {
    current: page,
    pageSize,
    total: data?.total ?? 0,
    showSizeChanger: true,
    onChange: (p, ps) => onPageChange(p, ps),
  }

  return (
    <div style={{ padding: embedded ? 0 : 16 }}>
      {!embedded ? (
        <>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, margin: '0 0 12px' }}>
            <Typography.Title level={3} style={{ margin: 0 }}>
              数据洞察 / 销售分析
            </Typography.Title>
            <Tooltip
              title={
                <div style={{ maxWidth: 520 }}>
                  <div>
                    本页默认展示“利润看板”，帮运营快速识别<strong>赚钱</strong>与<strong>亏钱</strong>的货品/模型（避免“卖一个亏一个”）。
                  </div>
                  <div style={{ marginTop: 6 }}>
                    为避免缺成本导致利润虚高：毛利/毛利率仅在“已计价行”上计算，并单独展示成本覆盖率。
                  </div>
                </div>
              }
            >
              <InfoCircleOutlined style={{ color: 'var(--ant-color-text-secondary)', cursor: 'help' }} />
            </Tooltip>
          </div>
        </>
      ) : null}

      <Card size="small" style={{ marginBottom: 12 }}>
        <Form
          form={form}
          layout="inline"
          initialValues={{
            range: [dayjs().subtract(30, 'day'), dayjs()],
            shop: undefined,
          }}
        >
          <Form.Item label="统计时间">
            <Space size={8} wrap>
              {periodMode === 'custom' ? (
                <Form.Item name="range" rules={[{ required: true, message: '请选择时间范围' }]} style={{ marginBottom: 0 }}>
                  <DatePicker.RangePicker allowClear={false} />
                </Form.Item>
              ) : (
                <DatePicker
                  picker={periodMode === 'week' ? 'week' : periodMode === 'month' ? 'month' : 'date'}
                  value={anchorDate as any}
                  onChange={(v) => {
                    if (v) setAnchorDate(v.startOf('day'))
                  }}
                  allowClear={false}
                  format={periodMode === 'month' ? 'YYYY-MM' : 'YYYY-MM-DD'}
                />
              )}
              <Segmented<SalesPeriodMode>
                value={periodMode}
                onChange={(v) => setPeriodMode(v as SalesPeriodMode)}
                options={[
                  { label: '日', value: 'day' },
                  { label: '周', value: 'week' },
                  { label: '月', value: 'month' },
                ]}
              />
              <Button size="small" onClick={() => shiftAnchorDate(-1)} disabled={periodMode === 'custom'}>
                <LeftOutlined />
              </Button>
              <Button size="small" onClick={() => shiftAnchorDate(1)} disabled={periodMode === 'custom'}>
                <RightOutlined />
              </Button>
              <Button
                size="small"
                type={periodMode === 'custom' ? 'primary' : 'default'}
                onClick={() => setPeriodMode('custom')}
              >
                自定义模块
              </Button>
              <Typography.Text type="secondary">
                {computedRange?.[0]?.format?.('YYYY-MM-DD')} ~ {computedRange?.[1]?.format?.('YYYY-MM-DD')}
              </Typography.Text>
            </Space>
          </Form.Item>
          <Form.Item label="店铺" name="shop">
            <Select
              allowClear
              showSearch
              placeholder="可选：选择店铺"
              style={{ width: 200 }}
              options={shopOptions.map((s) => ({ label: s, value: s }))}
              filterOption={(input, option) => String(option?.label ?? '').toLowerCase().includes(input.toLowerCase())}
            />
          </Form.Item>
          <Form.Item label="货品条码" name="sku_code">
            <Input placeholder="可选：barcode" style={{ width: 180 }} allowClear />
          </Form.Item>
          <Form.Item>
            <Button size="small" onClick={() => setShowAdvanced((v) => !v)}>
              {showAdvanced ? '收起筛选' : '更多筛选'}
            </Button>
          </Form.Item>
          {showAdvanced ? (
            <>
              <Form.Item label="套装模板" name="bundle_template_code">
                <Input placeholder="可选：bundle code" style={{ width: 160 }} allowClear />
              </Form.Item>
              <Form.Item label="套装二级" name="bundle_preset_selector">
                <Input placeholder="可选：AA/AB" style={{ width: 120 }} allowClear />
              </Form.Item>
              <Form.Item label="原始单号" name="order_no">
                <Input placeholder="可选：order_no" style={{ width: 180 }} allowClear />
              </Form.Item>
              <Form.Item label="商品链接ID" name="product_link_id">
                <Input placeholder="可选：product_link_id" style={{ width: 200 }} allowClear />
              </Form.Item>
            </>
          ) : null}
          <Form.Item>
            <Space>
              <Segmented
                options={[{ label: '含未计价（固定）', value: 'all' }]}
                value="all"
                disabled
              />
              <Button type="primary" onClick={() => onQuery()} loading={loading || dashboardQuery.isFetching}>
                {embedded ? '查询明细' : activeTab === 'lines' ? (linesView === 'list' ? '查询明细' : '刷新排名') : '刷新看板'}
              </Button>
              {!embedded ? (
                <>
                  <Button onClick={refreshDashboardSnapshotNow} disabled={!useSnapshot} loading={dashboardQuery.isFetching}>
                    刷新数据
                  </Button>
                </>
              ) : null}
              <Button
                onClick={() => {
                  form.resetFields()
                  setData(null)
                  setError(null)
                  setPage(1)
                }}
              >
                重置
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Card>

      {error ? <Alert type="error" showIcon message="查询失败" description={error} style={{ marginBottom: 12 }} /> : null}

      {data && (data.items ?? []).length === 0 ? (
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 12 }}
          message="当前范围暂无数据"
          description={
            <Space wrap>
              <span>建议点“近30天/近90天”确认数据范围，或检查是否已导入发货单。</span>
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

      <Card size="small">
        {embedded ? (
          <>
            {data ? (
              <Alert
                type={data.lines_with_bom_snapshots > 0 ? 'success' : 'warning'}
                showIcon
                style={{ marginBottom: 12 }}
                message="成本覆盖率（明细范围内）"
                description={
                  <div>
                    <div>
                      有 BOM/计价行：{data.lines_with_bom_snapshots}；缺成本字段行：{data.lines_missing_costing}
                    </div>
                    <div style={{ color: '#888' }}>{data.note || ''}</div>
                  </div>
                }
              />
            ) : null}
            <Table
              rowKey="shipment_line_id"
              size="small"
              loading={loading}
              columns={columns}
              dataSource={data?.items ?? []}
              pagination={pagination}
              scroll={{ x: 2100 }}
            />
          </>
        ) : (
          <Tabs
            activeKey={activeTab}
            onChange={(k) => {
              setActiveTab(k as any)
              if (k === 'lines') setLinesView('list')
            }}
            items={[
              {
                key: 'dashboard',
                label: '利润看板（赚钱/亏钱）',
                children: (
                  <>
                  <div style={{ marginBottom: 12 }}>
                    <Space wrap>
                      {useSnapshot && dashboardComputedAt ? (
                        <Typography.Text type="secondary">数据更新时间：{formatDateTime(dashboardComputedAt)}</Typography.Text>
                      ) : null}
                      <Typography.Text type="secondary">时间口径：按发货完成时间（成本口径一致）</Typography.Text>
                    </Space>
                  </div>

                  {dashboardQuery.isError ? (
                    <Alert
                      type={(dashboardQuery.error as any)?.response?.status === 404 ? 'warning' : 'error'}
                      showIcon
                      style={{ marginBottom: 12 }}
                      message="看板加载失败"
                      description={String((dashboardQuery.error as any)?.message ?? 'unknown error')}
                    />
                  ) : null}

                  <Row gutter={[12, 12]} style={{ marginBottom: 12 }}>
                    <Col xs={24} lg={6}>
                      <Card size="small">
                        <Statistic
                          title="销售额（全部）"
                          value={formatMoney((dashboardQuery.data as SalesProfitDashboardResponse | undefined)?.kpis?.revenue_amount)}
                        />
                      </Card>
                    </Col>
                    <Col xs={24} lg={6}>
                      <Card size="small">
                        <Statistic
                          title="已计价销售额"
                          value={formatMoney((dashboardQuery.data as SalesProfitDashboardResponse | undefined)?.kpis?.costed_revenue_amount)}
                        />
                      </Card>
                    </Col>
                    <Col xs={24} lg={6}>
                      <Card size="small">
                        <Statistic
                          title="毛利额（已计价）"
                          value={formatMoney((dashboardQuery.data as SalesProfitDashboardResponse | undefined)?.kpis?.gross_profit)}
                          valueStyle={{
                            color: Number((dashboardQuery.data as any)?.kpis?.gross_profit ?? 0) < 0 ? 'var(--ant-color-error)' : undefined,
                          }}
                        />
                      </Card>
                    </Col>
                    <Col xs={24} lg={6}>
                      <Card size="small">
                        <Space direction="vertical" style={{ width: '100%' }}>
                          <Typography.Text type="secondary">成本覆盖率（按销售额）</Typography.Text>
                          <Progress
                            percent={Number((Number((dashboardQuery.data as any)?.kpis?.costed_revenue_rate ?? 0) * 100).toFixed(1))}
                            strokeColor="var(--ant-color-primary, #1677ff)"
                            format={(p) => `${p ?? 0}%`}
                          />
                          <Typography.Text type="secondary">
                            缺成本行：{Number((dashboardQuery.data as any)?.kpis?.lines_missing_costing ?? 0)} /{' '}
                            {Number((dashboardQuery.data as any)?.kpis?.shipment_lines_total ?? 0)}
                          </Typography.Text>
                        </Space>
                      </Card>
                    </Col>
                  </Row>

                  <Row gutter={[12, 12]}>
                    <Col xs={24} lg={12}>
                      <Card
                        size="small"
                        title="Top 赚钱货品（毛利额最高，已计价）"
                        extra={
                          <Button
                            type="link"
                            size="small"
                            onClick={() => {
                              openRankingInLinesTab('profit')
                            }}
                          >
                            更多排名
                          </Button>
                        }
                      >
                        <Table
                          rowKey={(r: any) => String(r.sku_code)}
                          size="small"
                          loading={dashboardQuery.isFetching}
                          dataSource={(dashboardQuery.data as SalesProfitDashboardResponse | undefined)?.top_skus_profit ?? []}
                          pagination={false}
                          columns={[
                            { title: 'SKU', dataIndex: 'sku_code', width: 140, ellipsis: true },
                            { title: '规格（最常见）', dataIndex: 'spec_text', ellipsis: true },
                            { title: '销售额', dataIndex: 'revenue_amount', width: 110, render: (v: any) => formatMoney(v) },
                            { title: '成本', dataIndex: 'cost_amount', width: 110, render: (v: any) => formatMoney(v) },
                            {
                              title: '毛利',
                              dataIndex: 'gross_profit',
                              width: 110,
                              render: (v: any) => (
                                <Typography.Text type={Number(v ?? 0) < 0 ? 'danger' : undefined}>{formatMoney(v)}</Typography.Text>
                              ),
                            },
                            {
                              title: '毛利率',
                              dataIndex: 'gross_margin',
                              width: 110,
                              render: (v: any) => (v == null ? '-' : `${(Number(v) * 100).toFixed(2)}%`),
                            },
                          ]}
                          onRow={(r: SalesProfitDashboardTopSkuItem) => ({
                            onClick: () => {
                              const sku = String(r?.sku_code ?? '').trim()
                              if (!sku) return
                              openSkuInLinesList(sku)
                            },
                          })}
                        />
                      </Card>
                    </Col>
                    <Col xs={24} lg={12}>
                      <Card
                        size="small"
                        title="Top 亏损货品（毛利额最低，已计价）"
                        extra={
                          <Button
                            type="link"
                            size="small"
                            onClick={() => {
                              openRankingInLinesTab('loss')
                            }}
                          >
                            更多排名
                          </Button>
                        }
                      >
                        <Table
                          rowKey={(r: any) => String(r.sku_code)}
                          size="small"
                          loading={dashboardQuery.isFetching}
                          dataSource={(dashboardQuery.data as SalesProfitDashboardResponse | undefined)?.top_skus_loss ?? []}
                          pagination={false}
                          columns={[
                            { title: 'SKU', dataIndex: 'sku_code', width: 140, ellipsis: true },
                            { title: '规格（最常见）', dataIndex: 'spec_text', ellipsis: true },
                            { title: '销售额', dataIndex: 'revenue_amount', width: 110, render: (v: any) => formatMoney(v) },
                            { title: '成本', dataIndex: 'cost_amount', width: 110, render: (v: any) => formatMoney(v) },
                            {
                              title: '毛利',
                              dataIndex: 'gross_profit',
                              width: 110,
                              render: (v: any) => (
                                <Typography.Text type={Number(v ?? 0) < 0 ? 'danger' : undefined}>{formatMoney(v)}</Typography.Text>
                              ),
                            },
                            {
                              title: '毛利率',
                              dataIndex: 'gross_margin',
                              width: 110,
                              render: (v: any) => (v == null ? '-' : `${(Number(v) * 100).toFixed(2)}%`),
                            },
                          ]}
                          onRow={(r: SalesProfitDashboardTopSkuItem) => ({
                            onClick: () => {
                              const sku = String(r?.sku_code ?? '').trim()
                              if (!sku) return
                              openSkuInLinesList(sku)
                            },
                          })}
                        />
                      </Card>
                    </Col>
                  </Row>

                  <Row gutter={[12, 12]} style={{ marginTop: 12 }}>
                    <Col xs={24} lg={12}>
                      <Card size="small" title="Top 赚钱模型（毛利额最高，已计价）">
                        <Table
                          rowKey={(r: any) => String(r.model_code)}
                          size="small"
                          loading={dashboardQuery.isFetching}
                          dataSource={(dashboardQuery.data as SalesProfitDashboardResponse | undefined)?.top_models_profit ?? []}
                          pagination={false}
                          columns={[
                            {
                              title: '模型',
                              key: 'model',
                              ellipsis: true,
                              render: (_: any, r: SalesProfitDashboardTopModelItem) => {
                                const main = `${r.model_code}${r.model_name ? ` ${r.model_name}` : ''}`
                                const phrase = String((r as any)?.bundle_preset_phrase ?? '').trim()
                                if (!phrase) return main
                                const pillStyle = {
                                  display: 'inline-block',
                                  padding: '0px 6px',
                                  borderRadius: 6,
                                  border: '1px solid',
                                  borderColor: 'color-mix(in srgb, var(--ant-color-success) 45%, var(--ant-color-border))',
                                  background: 'color-mix(in srgb, var(--ant-color-success) 18%, var(--ant-color-fill-tertiary))',
                                  fontSize: 11,
                                  lineHeight: '18px',
                                  color: 'var(--ant-color-success)',
                                  whiteSpace: 'nowrap',
                                } as const
                                return (
                                  <span style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
                                    <span
                                      style={{ minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                                    >
                                      {main}
                                    </span>
                                    <Tooltip title={phrase}>
                                      <span style={pillStyle}>{phrase}</span>
                                    </Tooltip>
                                  </span>
                                )
                              },
                            },
                            { title: '销售额', dataIndex: 'revenue_amount', width: 110, render: (v: any) => formatMoney(v) },
                            {
                              title: '毛利',
                              dataIndex: 'gross_profit',
                              width: 110,
                              render: (v: any) => (
                                <Typography.Text type={Number(v ?? 0) < 0 ? 'danger' : undefined}>{formatMoney(v)}</Typography.Text>
                              ),
                            },
                            {
                              title: '毛利率',
                              dataIndex: 'gross_margin',
                              width: 110,
                              render: (v: any) => (v == null ? '-' : `${(Number(v) * 100).toFixed(2)}%`),
                            },
                          ]}
                          onRow={(r: SalesProfitDashboardTopModelItem) => ({
                            onClick: () => {
                              const mc = String((r as any)?.model_code ?? '').trim()
                              const isBundle = mc.startsWith('B-') || mc.startsWith('Z-')
                              if (!isBundle) return
                              const tpl = String((r as any)?.bundle_template_code ?? '').trim().toUpperCase()
                              const sel = String((r as any)?.bundle_preset_selector ?? '').trim().toUpperCase()
                              if (!tpl) return
                              navigateToShipmentsProcessed({ bundle_template_code: tpl, bundle_preset_selector: sel || undefined })
                            },
                          })}
                        />
                      </Card>
                    </Col>
                    <Col xs={24} lg={12}>
                      <Card size="small" title="Top 亏损模型（毛利额最低，已计价）">
                        <Table
                          rowKey={(r: any) => String(r.model_code)}
                          size="small"
                          loading={dashboardQuery.isFetching}
                          dataSource={(dashboardQuery.data as SalesProfitDashboardResponse | undefined)?.top_models_loss ?? []}
                          pagination={false}
                          columns={[
                            {
                              title: '模型',
                              key: 'model',
                              ellipsis: true,
                              render: (_: any, r: SalesProfitDashboardTopModelItem) => {
                                const main = `${r.model_code}${r.model_name ? ` ${r.model_name}` : ''}`
                                const phrase = String((r as any)?.bundle_preset_phrase ?? '').trim()
                                if (!phrase) return main
                                const pillStyle = {
                                  display: 'inline-block',
                                  padding: '0px 6px',
                                  borderRadius: 6,
                                  border: '1px solid',
                                  borderColor: 'color-mix(in srgb, var(--ant-color-success) 45%, var(--ant-color-border))',
                                  background: 'color-mix(in srgb, var(--ant-color-success) 18%, var(--ant-color-fill-tertiary))',
                                  fontSize: 11,
                                  lineHeight: '18px',
                                  color: 'var(--ant-color-success)',
                                  whiteSpace: 'nowrap',
                                } as const
                                return (
                                  <span style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
                                    <span
                                      style={{ minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                                    >
                                      {main}
                                    </span>
                                    <Tooltip title={phrase}>
                                      <span style={pillStyle}>{phrase}</span>
                                    </Tooltip>
                                  </span>
                                )
                              },
                            },
                            { title: '销售额', dataIndex: 'revenue_amount', width: 110, render: (v: any) => formatMoney(v) },
                            {
                              title: '毛利',
                              dataIndex: 'gross_profit',
                              width: 110,
                              render: (v: any) => (
                                <Typography.Text type={Number(v ?? 0) < 0 ? 'danger' : undefined}>{formatMoney(v)}</Typography.Text>
                              ),
                            },
                            {
                              title: '毛利率',
                              dataIndex: 'gross_margin',
                              width: 110,
                              render: (v: any) => (v == null ? '-' : `${(Number(v) * 100).toFixed(2)}%`),
                            },
                          ]}
                          onRow={(r: SalesProfitDashboardTopModelItem) => ({
                            onClick: () => {
                              const mc = String((r as any)?.model_code ?? '').trim()
                              const isBundle = mc.startsWith('B-') || mc.startsWith('Z-')
                              if (!isBundle) return
                              const tpl = String((r as any)?.bundle_template_code ?? '').trim().toUpperCase()
                              const sel = String((r as any)?.bundle_preset_selector ?? '').trim().toUpperCase()
                              if (!tpl) return
                              navigateToShipmentsProcessed({ bundle_template_code: tpl, bundle_preset_selector: sel || undefined })
                            },
                          })}
                        />
                      </Card>
                    </Col>
                  </Row>
                </>
              ),
            },
              {
                key: 'lines',
                label: '销售明细',
                children: (
                  <>
                    {linesView !== 'list' ? (
                      <>
                        <div style={{ marginBottom: 12 }}>
                          <Space wrap>
                            <Typography.Text strong>
                              {linesView === 'rank_profit' ? 'Top 赚钱货品（前100，按毛利额）' : 'Top 亏损货品（前100，按毛利额）'}
                            </Typography.Text>
                            <Button
                              size="small"
                              onClick={() => {
                                setLinesView('list')
                              }}
                            >
                              切回明细行列表
                            </Button>
                          </Space>
                        </div>
                        <Table<SalesProfitDashboardTopSkuItem>
                          rowKey={(r) => `${r.sku_code}-${String(r.spec_text ?? '')}`}
                          size="small"
                          loading={top100Query.isFetching}
                          pagination={{ pageSize: 100, showSizeChanger: false }}
                          dataSource={
                            linesView === 'rank_profit'
                              ? ((top100Query.data as SalesProfitDashboardResponse | undefined)?.top_skus_profit ?? [])
                              : ((top100Query.data as SalesProfitDashboardResponse | undefined)?.top_skus_loss ?? [])
                          }
                          columns={[
                            { title: '排名', width: 70, render: (_v, _r, idx) => idx + 1 },
                            { title: 'SKU', dataIndex: 'sku_code', width: 160, ellipsis: true },
                            { title: '规格（最常见）', dataIndex: 'spec_text', ellipsis: true },
                            { title: '发货件数', dataIndex: 'shipped_qty', width: 110, render: (v: any) => formatQty(v) },
                            { title: '销售额', dataIndex: 'revenue_amount', width: 120, render: (v: any) => formatMoney(v) },
                            { title: '成本', dataIndex: 'cost_amount', width: 120, render: (v: any) => formatMoney(v) },
                            {
                              title: '毛利',
                              dataIndex: 'gross_profit',
                              width: 120,
                              render: (v: any) => (
                                <Typography.Text type={Number(v ?? 0) < 0 ? 'danger' : undefined}>{formatMoney(v)}</Typography.Text>
                              ),
                            },
                            {
                              title: '毛利率',
                              dataIndex: 'gross_margin',
                              width: 110,
                              render: (v: any) => (v == null ? '-' : `${(Number(v) * 100).toFixed(2)}%`),
                            },
                            {
                              title: '操作',
                              key: 'ops',
                              width: 170,
                              render: (_v: any, r: SalesProfitDashboardTopSkuItem) => {
                                const sku = String(r?.sku_code ?? '').trim()
                                return (
                                  <Space>
                                    <Button
                                      size="small"
                                      onClick={(e) => {
                                        e?.stopPropagation?.()
                                        if (!sku) return
                                        openSkuInLinesList(sku)
                                      }}
                                    >
                                      查看明细
                                    </Button>
                                    <Button
                                      size="small"
                                      type="link"
                                      onClick={(e) => {
                                        e?.stopPropagation?.()
                                        if (!sku) return
                                        navigateToShipmentsProcessed({ sku_code: sku })
                                      }}
                                    >
                                      去台账
                                    </Button>
                                  </Space>
                                )
                              },
                            },
                          ]}
                          onRow={(r) => ({
                            onClick: () => {
                              const sku = String(r?.sku_code ?? '').trim()
                              if (!sku) return
                              openSkuInLinesList(sku)
                            },
                          })}
                        />
                      </>
                    ) : (
                      <>
                        {data ? (
                          <Alert
                            type={data.lines_with_bom_snapshots > 0 ? 'success' : 'warning'}
                            showIcon
                            style={{ marginBottom: 12 }}
                            message="成本覆盖率（明细范围内）"
                            description={
                              <div>
                                <div>
                                  有 BOM/计价行：{data.lines_with_bom_snapshots}；缺成本字段行：{data.lines_missing_costing}
                                </div>
                                <div style={{ color: '#888' }}>{data.note || ''}</div>
                              </div>
                            }
                          />
                        ) : null}
                        <Table
                          rowKey="shipment_line_id"
                          size="small"
                          loading={loading}
                          columns={columns}
                          dataSource={data?.items ?? []}
                          pagination={pagination}
                          scroll={{ x: 2350 }}
                        />
                      </>
                    )}
                  </>
                ),
              },
          ]}
          />
        )}
      </Card>
    </div>
  )
}

export default SalesInsightsPage

