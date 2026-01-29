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
import { useEffect, useMemo, useRef, useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'

import {
  fetchSalesLines,
  fetchSalesProfitDashboard,
  fetchSalesProfitDashboardSnapshot,
  refreshSalesProfitDashboardSnapshot,
} from '@/services/planner'
import type { SalesLineItem, SalesLinesResponse, SalesProfitDashboardResponse, SalesProfitDashboardTopModelItem, SalesProfitDashboardTopSkuItem } from '@/types/planner'

const STORAGE_KEY = 'insights.sales.lastQuery.v1'

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

type SalesInsightsPageProps = {
  embedded?: boolean
}

const SalesInsightsPage = (props: SalesInsightsPageProps) => {
  const embedded = !!props.embedded
  const navigate = useNavigate()
  const [form] = Form.useForm()
  const [dashboardGroupBy, setDashboardGroupBy] = useState<'week' | 'month'>('week')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [data, setData] = useState<SalesLinesResponse | null>(null)
  const [includeMissing, setIncludeMissing] = useState(true)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [shopOptions, setShopOptions] = useState<string[]>([])
  const [useSnapshot, setUseSnapshot] = useState(true)
  const [quickDays, setQuickDays] = useState<7 | 30 | 90>(30)
  const [dashboardComputedAt, setDashboardComputedAt] = useState<string | null>(null)
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
  const rangeStartIso = watchedRange?.[0]?.startOf('day')?.toISOString?.()
  const rangeEndIso = watchedRange?.[1]?.endOf('day')?.toISOString?.()

  const dashboardQuery = useQuery({
    queryKey: ['sales', 'profit-dashboard', rangeStartIso, rangeEndIso, watchedShop, dashboardGroupBy],
    queryFn: async () => {
      const channel = watchedShop?.trim() || undefined
      if (useSnapshot) {
        try {
          const snap = await fetchSalesProfitDashboardSnapshot({ range_days: quickDays, group_by: dashboardGroupBy, channel })
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
        range_days: quickDays,
        group_by: dashboardGroupBy,
        channel,
        operator_id: 'planner-ui',
      })
      await dashboardQuery.refetch()
      message.success('已刷新（使用缓存）')
    } catch (e: any) {
      message.error(`刷新失败：${e?.response?.data?.detail ?? e?.message ?? 'unknown error'}`)
    }
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
    const range = v.range as [dayjs.Dayjs, dayjs.Dayjs]
    const base = {
      start: range[0].startOf('day').toISOString(),
      end: range[1].endOf('day').toISOString(),
      include_missing: includeMissing,
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
            ...base,
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
    dashboardQuery.refetch().then((res) => {
      const status = (res as any)?.error?.response?.status
      if (status === 404) message.warning('后端尚未部署销售利润看板接口（/api/planner/analytics/sales/profit-dashboard）。')
    })
  }

  const applyQuickRange = async (days: number) => {
    const d = days === 7 || days === 30 || days === 90 ? (days as 7 | 30 | 90) : 30
    setQuickDays(d)
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
        const nextIncludeMissing = saved?.include_missing !== false

        if (Number.isFinite(nextPageSize) && nextPageSize > 0) setPageSize(nextPageSize)
        setIncludeMissing(nextIncludeMissing)

        const range: [dayjs.Dayjs, dayjs.Dayjs] = [
          dayjs(start || dayjs().subtract(30, 'day').startOf('day').toISOString()),
          dayjs(end || dayjs().endOf('day').toISOString()),
        ]
        form.setFieldsValue({
          range,
          shop: saved?.channel ?? undefined,
          sku_code: saved?.sku_code ?? undefined,
          order_no: saved?.order_no ?? undefined,
          product_link_id: saved?.product_link_id ?? undefined,
        })

        const base = {
          start: range[0].startOf('day').toISOString(),
          end: range[1].endOf('day').toISOString(),
          include_missing: nextIncludeMissing,
          channel: String(saved?.channel ?? '').trim() || undefined,
          sku_code: String(saved?.sku_code ?? '').trim() || undefined,
          order_no: String(saved?.order_no ?? '').trim() || undefined,
          product_link_id: String(saved?.product_link_id ?? '').trim() || undefined,
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
    const range = v.range as [dayjs.Dayjs, dayjs.Dayjs]
    const fallback = {
      start: range?.[0]?.startOf('day')?.toISOString?.() ?? dayjs().startOf('day').toISOString(),
      end: range?.[1]?.endOf('day')?.toISOString?.() ?? dayjs().endOf('day').toISOString(),
      include_missing: includeMissing,
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
          <Typography.Title level={3} style={{ margin: '0 0 12px' }}>
            数据洞察 / 销售分析
          </Typography.Title>

          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 12 }}
            message="说明（利润看板）"
            description={
              <div>
                <div>
                  本页默认展示“利润看板”，帮运营快速识别<strong>赚钱</strong>与<strong>亏钱</strong>的货品/模型（避免“卖一个亏一个”）。
                </div>
                <div>为避免缺成本导致利润虚高：毛利/毛利率仅在“已计价行”上计算，并单独展示成本覆盖率。</div>
              </div>
            }
          />
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
          <Form.Item label="时间范围" name="range" rules={[{ required: true, message: '请选择时间范围' }]}>
            <DatePicker.RangePicker allowClear={false} />
          </Form.Item>
          <Form.Item label="快捷">
            <Space size={6}>
              <Button size="small" onClick={() => applyQuickRange(7)}>
                近7天
              </Button>
              <Button size="small" onClick={() => applyQuickRange(30)}>
                近30天
              </Button>
              <Button size="small" onClick={() => applyQuickRange(90)}>
                近90天
              </Button>
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
          <Form.Item>
            <Space>
              <Segmented
                value={includeMissing ? 'all' : 'costed'}
                onChange={(v) => setIncludeMissing(v === 'all')}
                options={[
                  { label: '含未计价', value: 'all' },
                  { label: '仅已计价', value: 'costed' },
                ]}
              />
              <Button type="primary" onClick={() => onQuery()} loading={loading || dashboardQuery.isFetching}>
                {embedded ? '查询明细' : '刷新看板'}
              </Button>
              {!embedded ? (
                <>
                  <Button onClick={refreshDashboardSnapshotNow} disabled={!useSnapshot} loading={dashboardQuery.isFetching}>
                    刷新数据
                  </Button>
                  <Button onClick={() => setUseSnapshot((v) => !v)} disabled={dashboardQuery.isFetching || loading}>
                    {useSnapshot ? '切到实时' : '切到缓存'}
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

      {!embedded && useSnapshot && dashboardComputedAt ? (
        <Alert
          type="success"
          showIcon
          style={{ marginBottom: 12 }}
          message="利润看板（缓存）"
          description={<span>数据更新时间：{dashboardComputedAt}</span>}
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
            activeKey="dashboard"
            items={[
              {
                key: 'dashboard',
                label: '利润看板（赚钱/亏钱）',
                children: (
                  <>
                  <div style={{ marginBottom: 12 }}>
                    <Space wrap>
                      <Select
                        value={dashboardGroupBy}
                        style={{ width: 120 }}
                        onChange={(v) => setDashboardGroupBy(v)}
                        options={[
                          { value: 'week', label: '按周（默认）' },
                          { value: 'month', label: '按月' },
                        ]}
                      />
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
                      <Card size="small" title="Top 赚钱货品（毛利额最高，已计价）">
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
                              navigateToShipmentsProcessed({ sku_code: sku })
                            },
                          })}
                        />
                      </Card>
                    </Col>
                    <Col xs={24} lg={12}>
                      <Card size="small" title="Top 亏损货品（毛利额最低，已计价）">
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
                              navigateToShipmentsProcessed({ sku_code: sku })
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
          ]}
          />
        )}
      </Card>
    </div>
  )
}

export default SalesInsightsPage

