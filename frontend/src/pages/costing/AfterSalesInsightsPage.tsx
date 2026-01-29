import {
  Alert,
  Button,
  Card,
  Col,
  DatePicker,
  Drawer,
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
  Upload,
  message,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import dayjs from 'dayjs'
import { useEffect, useMemo, useRef, useState } from 'react'
import type { CSSProperties } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { InfoCircleOutlined, ReloadOutlined } from '@ant-design/icons'

import {
  fetchAfterSalesImportBatches,
  fetchAfterSalesLines,
  fetchAfterSalesDashboard,
  fetchAfterSalesDashboardSnapshot,
  refreshAfterSalesDashboardSnapshot,
  fetchReturnsRateBySku,
  importAfterSalesXlsx,
} from '@/services/planner'
import type { AfterSalesImportBatch, ReturnsRateBySkuItem, ReturnsRateBySkuResponse } from '@/types/planner'
import type {
  AfterSalesLineItem,
  AfterSalesDashboardResponse,
  PaginatedAfterSalesLinesResponse,
} from '@/types/planner'

type GroupBy = 'day' | 'month'

const STORAGE_KEY = 'insights.after_sales.lastSkuQuery.v1'

const formatPercent = (raw?: string | null) => {
  if (!raw) return '-'
  const n = Number(raw)
  if (!Number.isFinite(n)) return '-'
  return `${(n * 100).toFixed(2)}%`
}

const formatMoney = (raw?: string) => {
  if (raw == null) return '-'
  const n = Number(raw)
  if (!Number.isFinite(n)) return String(raw)
  return n.toFixed(2)
}

const formatQty = (raw?: string) => {
  if (raw == null) return '-'
  const n = Number(raw)
  if (!Number.isFinite(n)) return String(raw)
  return n.toFixed(2).replace(/\.00$/, '')
}

const AfterSalesInsightsPage = () => {
  const [form] = Form.useForm()
  const [activeTab, setActiveTab] = useState<'dashboard' | 'rate' | 'detail'>('dashboard')
  const [dashboardGroupBy, setDashboardGroupBy] = useState<'week' | 'month'>('week')
  const [dashboardView, setDashboardView] = useState<'ops' | 'factory'>('factory')
  const [dashboardAutoLoad, setDashboardAutoLoad] = useState(false)
  const [dashboardUseSnapshot, setDashboardUseSnapshot] = useState(true)
  const [dashboardQuickDays, setDashboardQuickDays] = useState<7 | 30 | 90>(30)
  const [dashboardComputedAt, setDashboardComputedAt] = useState<string | null>(null)
  const opsStroke = 'var(--ant-color-primary, #1677ff)'
  const factoryStroke = 'var(--ant-color-success, #52c41a)'

  const [loading, setLoading] = useState(false)
  const [data, setData] = useState<ReturnsRateBySkuResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)
  const [uploadFile, setUploadFile] = useState<File | null>(null)
  const [uploadExportDate, setUploadExportDate] = useState<string | undefined>(dayjs().format('YYYY-MM-DD'))
  const [uploadRequestedBy, setUploadRequestedBy] = useState<string>('planner_user')
  const [lastImportSummary, setLastImportSummary] = useState<string | null>(null)
  const [batchPage, setBatchPage] = useState(1)
  const [batchPageSize, setBatchPageSize] = useState(10)
  const didInitRef = useRef(false)
  const [uploadDrawerOpen, setUploadDrawerOpen] = useState(false)
  const [batchesDrawerOpen, setBatchesDrawerOpen] = useState(false)

  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState<string | null>(null)
  const [detailData, setDetailData] = useState<PaginatedAfterSalesLinesResponse | null>(null)
  const [detailPage, setDetailPage] = useState(1)
  const [detailPageSize, setDetailPageSize] = useState(50)

  const batchesQuery = useQuery({
    queryKey: ['after-sales', 'import-batches', batchPage, batchPageSize],
    queryFn: () => fetchAfterSalesImportBatches({ page: batchPage, page_size: batchPageSize }),
    placeholderData: keepPreviousData,
  })

  const watchedRange = Form.useWatch('range', form) as [dayjs.Dayjs, dayjs.Dayjs] | undefined
  const watchedChannel = Form.useWatch('channel', form) as string | undefined

  const rangeStartIso = watchedRange?.[0]?.startOf('day')?.toISOString?.()
  const rangeEndIso = watchedRange?.[1]?.endOf('day')?.toISOString?.()

  const dashboardQuery = useQuery({
    queryKey: ['after-sales', 'dashboard', rangeStartIso, rangeEndIso, watchedChannel, dashboardGroupBy, dashboardView],
    queryFn: async () => {
      const channel = watchedChannel?.trim() || undefined
      if (dashboardUseSnapshot) {
        try {
          const snap = await fetchAfterSalesDashboardSnapshot({
            range_days: dashboardQuickDays,
            group_by: dashboardGroupBy,
            view: dashboardView,
            channel,
          })
          setDashboardComputedAt(String((snap as any)?.computed_at ?? '') || null)
          return snap.data as any
        } catch (e: any) {
          if (Number(e?.response?.status) !== 404) setDashboardComputedAt(null)
        }
      }
      setDashboardComputedAt(null)
      return fetchAfterSalesDashboard(
        {
          start: String(rangeStartIso),
          end: String(rangeEndIso),
          group_by: dashboardGroupBy,
          channel,
          top_n: 12,
          view: dashboardView,
        },
        { timeoutMs: 60000 },
      )
    },
    enabled: activeTab === 'dashboard' && dashboardAutoLoad && !!rangeStartIso && !!rangeEndIso,
    placeholderData: keepPreviousData,
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  })

  const dashboardHttpStatus = (dashboardQuery.error as any)?.response?.status as number | undefined

  const columns = useMemo<ColumnsType<ReturnsRateBySkuItem>>(
    () => [
      { title: '发货日期', dataIndex: 'period', key: 'period', width: 160 },
      { title: '渠道', dataIndex: 'channel', key: 'channel', width: 160 },
      { title: '货品条码', dataIndex: 'sku_code', key: 'sku_code', width: 160 },
      { title: '发货数量', dataIndex: 'shipped_qty', key: 'shipped_qty', width: 120, render: formatQty },
      { title: '退货数量', dataIndex: 'returned_qty', key: 'returned_qty', width: 120, render: formatQty },
      { title: '退货率(件)', dataIndex: 'return_rate', key: 'return_rate', width: 120, render: formatPercent },
      { title: '发货金额', dataIndex: 'shipped_amount', key: 'shipped_amount', width: 120, render: formatMoney },
      { title: '退款金额', dataIndex: 'refund_amount', key: 'refund_amount', width: 120, render: formatMoney },
      { title: '退款率(额)', dataIndex: 'refund_rate', key: 'refund_rate', width: 120, render: formatPercent },
    ],
    [],
  )

  const formatDateToDay = (raw?: string | null) => {
    if (!raw) return '-'
    const s = String(raw)
    if (s.length >= 10 && s[4] === '-' && s[7] === '-') return s.slice(0, 10)
    const d = dayjs(s)
    if (!d.isValid()) return s
    return d.format('YYYY-MM-DD')
  }

  const detailColumns = useMemo<ColumnsType<AfterSalesLineItem>>(
    () => [
      { title: '申请日期', dataIndex: 'applied_at', width: 110, render: (v) => formatDateToDay(v as any) },
      { title: '渠道', dataIndex: 'channel', width: 140, ellipsis: true, render: (v) => String(v ?? '-') },
      { title: '货品条码', dataIndex: 'sku_code', width: 150, ellipsis: true, render: (v) => String(v ?? '-') },
      {
        title: '模型',
        key: 'model',
        width: 220,
        ellipsis: true,
        render: (_v, r) => {
          const code = String(r.bound_model_code ?? '').trim()
          const name = String(r.bound_model_name ?? '').trim()
          if (!code && !name) return '-'
          return [code, name].filter(Boolean).join(' ')
        },
      },
      { title: '版本', dataIndex: 'bound_version_label', width: 140, ellipsis: true, render: (v) => String(v ?? '-') },
      {
        title: '规格',
        dataIndex: 'spec_text',
        ellipsis: true,
        render: (v) => String(v ?? '-') || '-',
      },
      {
        title: '退换原因',
        dataIndex: 'reason',
        width: 180,
        ellipsis: true,
        render: (v) => String(v ?? '-') || '-',
      },
      { title: '退货数量', dataIndex: 'return_qty', width: 110, render: formatQty },
      { title: '退款金额', dataIndex: 'refund_amount', width: 110, render: formatMoney },
    ],
    [],
  )

  const onQuery = async () => {
    setError(null)
    setData(null)

    const v = await form.validateFields()
    const range = v.range as [dayjs.Dayjs, dayjs.Dayjs]
    const groupBy = v.group_by as GroupBy

    // 只按用户选择的范围查询；不做后台全量计算/全量重跑
    const start = range[0].startOf('day').toISOString()
    const end = range[1].endOf('day').toISOString()

    setLoading(true)
    try {
      const resp = await fetchReturnsRateBySku({
        start,
        end,
        group_by: groupBy,
        channel: v.channel?.trim() || undefined,
        sku_code: v.sku_code?.trim() || undefined,
      }, { timeoutMs: 120000 })
      setData(resp)
      try {
        if (typeof window !== 'undefined') {
          window.localStorage.setItem(
            STORAGE_KEY,
            JSON.stringify({
              start,
              end,
              group_by: groupBy,
              channel: v.channel?.trim() || undefined,
              sku_code: v.sku_code?.trim() || undefined,
            }),
          )
        }
      } catch {
        // ignore storage errors
      }
    } catch (e: any) {
      setError(String(e?.response?.data?.detail ?? e?.message ?? e))
    } finally {
      setLoading(false)
    }
  }

  const onQueryDetail = async (p?: number, ps?: number) => {
    setDetailError(null)
    const v = await form.validateFields()
    const range = v.range as [dayjs.Dayjs, dayjs.Dayjs]
    const start = range[0].startOf('day').toISOString()
    const end = range[1].endOf('day').toISOString()

    const page = p ?? detailPage
    const pageSize = ps ?? detailPageSize

    setDetailLoading(true)
    try {
      const resp = await fetchAfterSalesLines(
        {
          start,
          end,
          page,
          page_size: pageSize,
          channel: v.channel?.trim() || undefined,
          sku_code: v.sku_code?.trim() || undefined,
          product_link_id: v.product_link_id?.trim() || undefined,
          reason: v.reason || undefined,
          model_code: v.model_code || undefined,
        },
        { timeoutMs: 60000 },
      )
      setDetailData(resp)
      setDetailPage(page)
      setDetailPageSize(pageSize)
    } catch (e: any) {
      setDetailError(String(e?.response?.data?.detail ?? e?.message ?? e))
      setDetailData(null)
    } finally {
      setDetailLoading(false)
    }
  }

  useEffect(() => {
    if (didInitRef.current) return
    didInitRef.current = true

    try {
      const raw = typeof window !== 'undefined' ? window.localStorage.getItem(STORAGE_KEY) : null
      if (raw) {
        const saved = JSON.parse(raw || '{}') as any
        const start = String(saved?.start ?? '').trim()
        const end = String(saved?.end ?? '').trim()
        const groupBy = (String(saved?.group_by ?? 'month').trim() as GroupBy) || 'month'
        const range: [dayjs.Dayjs, dayjs.Dayjs] = [
          dayjs(start || dayjs().subtract(30, 'day').startOf('day').toISOString()),
          dayjs(end || dayjs().endOf('day').toISOString()),
        ]
        form.setFieldsValue({
          group_by: groupBy,
          range,
          channel: saved?.channel ?? undefined,
          sku_code: saved?.sku_code ?? undefined,
        })
      } else {
        // default: auto preview last 30 days (lightweight)
        form.setFieldsValue({
          group_by: 'month',
          range: [dayjs().subtract(30, 'day'), dayjs()],
        })
      }
    } catch {
      // ignore
    }
    // Always auto-run once so first screen is not empty.
    onQuery()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const applyQuickRange = async (days: number) => {
    const d = days === 7 || days === 30 || days === 90 ? (days as 7 | 30 | 90) : 30
    setDashboardQuickDays(d)
    const range: [dayjs.Dayjs, dayjs.Dayjs] = [dayjs().subtract(days, 'day'), dayjs()]
    form.setFieldsValue({ range })
    if (activeTab === 'detail') await onQueryDetail(1, detailPageSize)
    else if (activeTab === 'rate') await onQuery()
    else if (dashboardAutoLoad) await dashboardQuery.refetch()
  }

  const refreshDashboardSnapshotNow = async () => {
    const channel = watchedChannel?.trim() || undefined
    try {
      await refreshAfterSalesDashboardSnapshot({
        range_days: dashboardQuickDays,
        group_by: dashboardGroupBy,
        view: dashboardView,
        channel,
        operator_id: 'planner-ui',
      })
      await dashboardQuery.refetch()
      message.success('已刷新（使用缓存）')
    } catch (e: any) {
      message.error(`刷新失败：${e?.response?.data?.detail ?? e?.message ?? 'unknown error'}`)
    }
  }

  const activeTabColor = opsStroke

  return (
    <div style={{ padding: 16 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 12 }}>
        <Typography.Title level={3} style={{ margin: 0 }}>
          数据洞察 / 售后分析（退货率）
        </Typography.Title>
        <Tooltip
          title={
            <div style={{ maxWidth: 520 }}>
              <div>本页只在你选择的时间范围内查询汇总，不会全量重算。</div>
              <div style={{ marginTop: 6 }}>
                <b>工厂看板（归因口径）</b>：退货先按 <b>订单号 + 商品链接ID + 货品条码</b> 归因到发货行，再归因到“发货周/发货月”。
              </div>
              <div style={{ marginTop: 6 }}>
                <b>运营看板（全量口径）</b>：退货按“申请期全量”统计，不要求能匹配到发货行（更贴近售后工作量）。
              </div>
              <div style={{ marginTop: 6 }}>
                <b>为什么退</b>：到“售后明细”看申请日期/原因/规格/模型，并可从仪表盘点击 Top 项一键下钻。
              </div>
            </div>
          }
        >
          <InfoCircleOutlined style={{ color: 'var(--ant-color-text-secondary)', cursor: 'help' }} />
        </Tooltip>
      </div>

      <Card size="small" style={{ marginBottom: 12 }}>
        <Form
          form={form}
          layout="inline"
          initialValues={{
            group_by: 'month',
            range: [dayjs().subtract(30, 'day'), dayjs()],
          }}
        >
          <Form.Item label="时间范围" name="range" rules={[{ required: true, message: '请选择时间范围' }]}>
            <DatePicker.RangePicker allowClear={false} />
          </Form.Item>
          <Form.Item label="快捷">
            <Space size={6} wrap>
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
          <Form.Item label="粒度" name="group_by">
            <Select
              style={{ width: 100 }}
              options={[
                { value: 'month', label: '按月' },
                { value: 'day', label: '按日' },
              ]}
            />
          </Form.Item>
          <Form.Item label="渠道" name="channel">
            <Input placeholder="可选：店铺/渠道" style={{ width: 180 }} allowClear />
          </Form.Item>
          <Form.Item label="货品条码" name="sku_code">
            <Input placeholder="可选：barcode" style={{ width: 180 }} allowClear />
          </Form.Item>
          <Form.Item label="链接ID" name="product_link_id">
            <Input placeholder="可选：product_link_id（明细/钻取）" style={{ width: 220 }} allowClear />
          </Form.Item>
          {/* 隐藏高级筛选：原因/模型（仍支持图表点击下钻到明细） */}
          <Form.Item name="reason" hidden>
            <Input />
          </Form.Item>
          <Form.Item name="model_code" hidden>
            <Input />
          </Form.Item>
          <Form.Item label="操作">
            <Space size={8} wrap>
              {activeTab === 'dashboard' ? (
                <>
                  <Select
                    value={dashboardGroupBy}
                    style={{ width: 120 }}
                    onChange={(v) => setDashboardGroupBy(v)}
                    options={[
                      { value: 'week', label: '按周（默认）' },
                      { value: 'month', label: '按月' },
                    ]}
                  />
                  {!dashboardAutoLoad ? (
                    <Button
                      type="primary"
                      onClick={() => {
                        setDashboardAutoLoad(true)
                        dashboardQuery.refetch().then((res) => {
                          // if backend is not deployed, show a clearer hint
                          const status = (res as any)?.error?.response?.status
                          if (status === 404) {
                            message.warning('仪表盘接口未部署（404）。请先更新后端服务后再试。')
                          }
                        })
                      }}
                      loading={dashboardQuery.isFetching}
                    >
                      加载仪表盘
                    </Button>
                  ) : null}
                  <Button onClick={refreshDashboardSnapshotNow} disabled={!dashboardUseSnapshot || !dashboardAutoLoad} loading={dashboardQuery.isFetching}>
                    刷新数据
                  </Button>
                  <Button onClick={() => setDashboardUseSnapshot((v) => !v)} disabled={dashboardQuery.isFetching}>
                    {dashboardUseSnapshot ? '切到实时' : '切到缓存'}
                  </Button>
                </>
              ) : (
                <Button type="primary" onClick={onQuery} loading={loading}>
                  查询
                </Button>
              )}
              <Button onClick={() => onQueryDetail(1, detailPageSize)} loading={detailLoading} disabled={activeTab !== 'detail'}>
                查明细
              </Button>
              <Button
                onClick={() => {
                  form.resetFields()
                  setData(null)
                  setError(null)
                  setDetailData(null)
                  setDetailError(null)
                  if (activeTab === 'detail') onQueryDetail(1, detailPageSize)
                  else if (activeTab === 'rate') onQuery()
                  else dashboardQuery.refetch()
                }}
              >
                重置
              </Button>
              <Button onClick={() => setUploadDrawerOpen(true)}>上传/导入</Button>
              <Button onClick={() => setBatchesDrawerOpen(true)} loading={batchesQuery.isFetching}>
                导入记录
              </Button>
              {lastImportSummary ? (
                <Typography.Text type="secondary" ellipsis style={{ maxWidth: 520 }}>
                  最近导入：{lastImportSummary}
                </Typography.Text>
              ) : null}
            </Space>
          </Form.Item>
        </Form>
      </Card>

      <Card size="small">
        <Tabs
          activeKey={activeTab}
          onChange={(k) => {
            const next = k as 'dashboard' | 'rate' | 'detail'
            setActiveTab(next)
            if (next === 'detail' && !detailData && !detailLoading) {
              onQueryDetail(1, detailPageSize)
            }
            if (next === 'dashboard') {
              // do not auto-load on first render; user can click "加载仪表盘"
              // but if user already enabled it before, refresh normally
              if (dashboardAutoLoad) dashboardQuery.refetch()
            }
          }}
          items={[
            {
              key: 'dashboard',
              label: <span style={{ color: activeTab === 'dashboard' ? activeTabColor : undefined }}>仪表盘（周会）</span>,
              children: (
                <>
                  {!dashboardAutoLoad ? (
                    <Alert
                      type="info"
                      showIcon
                      style={{ marginBottom: 12 }}
                      message="仪表盘未自动加载"
                      description="为避免首次进入被长请求拖慢，仪表盘改为手动加载。点击上方“加载仪表盘”即可获取本范围内周会看板。"
                    />
                  ) : null}
                  {dashboardQuery.isError ? (
                    <Alert
                      type={dashboardHttpStatus === 404 ? 'warning' : 'error'}
                      showIcon
                      style={{ marginBottom: 12 }}
                      message="仪表盘加载失败"
                      description={
                        dashboardHttpStatus === 404
                          ? '后端尚未部署仪表盘接口（/api/planner/analytics/after-sales/dashboard）。请先更新后端并重启服务。'
                          : String((dashboardQuery.error as any)?.message ?? 'unknown error')
                      }
                    />
                  ) : null}

                  <div style={{ marginBottom: 12 }}>
                    <Space wrap>
                      <Segmented
                        value={dashboardView}
                        onChange={(v) => setDashboardView(v as any)}
                        options={[
                          { label: '运营看板', value: 'ops' },
                          { label: '工厂看板', value: 'factory' },
                        ]}
                      />
                      {dashboardView === 'factory' && dashboardAutoLoad ? (
                        <Button
                          type="text"
                          icon={<ReloadOutlined />}
                          title="刷新工厂看板"
                          onClick={() => dashboardQuery.refetch()}
                          loading={dashboardQuery.isFetching}
                        />
                      ) : null}
                      <Typography.Text type="secondary">
                        {dashboardView === 'ops'
                          ? '运营口径：退货按“申请期全量”统计；不要求能匹配到发货行。'
                          : '工厂口径：退货先按强关联键归因到发货行，再归因到发货周/月。'}
                      </Typography.Text>
                      {dashboardUseSnapshot && dashboardComputedAt ? (
                        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                          数据更新时间：{dashboardComputedAt}
                        </Typography.Text>
                      ) : null}
                    </Space>
                  </div>

                  <Row gutter={[12, 12]}>
                    <Col xs={24} lg={6}>
                      <Card size="small">
                        <Statistic title="发货数量" value={Number((dashboardQuery.data as AfterSalesDashboardResponse | undefined)?.kpis?.shipped_qty ?? 0)} />
                      </Card>
                    </Col>
                    <Col xs={24} lg={6}>
                      <Card size="small">
                        <Statistic
                          title={dashboardView === 'ops' ? '退货数量（申请期全量，实退优先）' : '退货数量（归因，实退优先）'}
                          value={Number((dashboardQuery.data as AfterSalesDashboardResponse | undefined)?.kpis?.returned_qty ?? 0)}
                        />
                      </Card>
                    </Col>
                    <Col xs={24} lg={6}>
                      <Card size="small">
                        <Statistic
                          title="退货率(件)"
                          value={Number((dashboardQuery.data as AfterSalesDashboardResponse | undefined)?.kpis?.return_rate ?? 0) * 100}
                          precision={2}
                          suffix="%"
                        />
                      </Card>
                    </Col>
                    <Col xs={24} lg={6}>
                      <Card size="small">
                        {dashboardView === 'factory' ? (
                          <Statistic
                            title="模型可归因覆盖率（发货）"
                            value={Number((dashboardQuery.data as AfterSalesDashboardResponse | undefined)?.kpis?.model_mapped_rate ?? 0) * 100}
                            precision={1}
                            suffix="%"
                          />
                        ) : (
                          <Statistic
                            title="退款率(额)"
                            value={Number((dashboardQuery.data as AfterSalesDashboardResponse | undefined)?.kpis?.refund_rate ?? 0) * 100}
                            precision={2}
                            suffix="%"
                          />
                        )}
                      </Card>
                    </Col>
                  </Row>

                  <Row gutter={[12, 12]} style={{ marginTop: 12 }}>
                    <Col xs={24} lg={12}>
                      <Card
                        size="small"
                        title={dashboardView === 'ops' ? '趋势（发货=发货完成；退货=申请期全量）' : '趋势（发货/退货，归因到发货周）'}
                      >
                        <Table
                          rowKey="period"
                          size="small"
                          loading={dashboardQuery.isFetching}
                          dataSource={(dashboardQuery.data as AfterSalesDashboardResponse | undefined)?.series ?? []}
                          pagination={{ pageSize: 8, showSizeChanger: true }}
                          columns={[
                            { title: '周期', dataIndex: 'period', width: 160, ellipsis: true },
                            { title: '发货', dataIndex: 'shipped_qty', width: 110 },
                            { title: '退货', dataIndex: 'returned_qty', width: 110 },
                            {
                              title: '退货率',
                              dataIndex: 'return_rate',
                              width: 120,
                              render: (v: any) => {
                                const n = Number(v ?? 0)
                                if (!Number.isFinite(n)) return '-'
                                return `${(n * 100).toFixed(2)}%`
                              },
                            },
                          ]}
                        />
                      </Card>
                    </Col>
                    <Col xs={24} lg={12}>
                      <Card size="small" title="Top 退换原因（点击可下钻明细）">
                        <Table
                          rowKey={(r: any) => String(r.reason)}
                          size="small"
                          loading={dashboardQuery.isFetching}
                          dataSource={(dashboardQuery.data as AfterSalesDashboardResponse | undefined)?.top_reasons ?? []}
                          pagination={{ pageSize: 8, showSizeChanger: true }}
                          columns={[
                            { title: '原因', dataIndex: 'reason', ellipsis: true },
                            { title: '退货', dataIndex: 'returned_qty', width: 110 },
                            {
                              title: '占比(退货)',
                              dataIndex: 'share_returned_qty',
                              width: 180,
                              render: (v: any) => {
                                const n = Number(v ?? 0) * 100
                                return (
                                  <Progress
                                    percent={Number.isFinite(n) ? Number(n.toFixed(1)) : 0}
                                    size="small"
                                    strokeColor={dashboardView === 'ops' ? opsStroke : factoryStroke}
                                  />
                                )
                              },
                            },
                          ]}
                          onRow={(r: any) => ({
                            onClick: async () => {
                              form.setFieldsValue({ reason: String(r.reason || '') })
                              setActiveTab('detail')
                              await onQueryDetail(1, detailPageSize)
                            },
                          })}
                        />
                      </Card>
                    </Col>
                  </Row>

                  <Row gutter={[12, 12]} style={{ marginTop: 12 }}>
                    <Col xs={24} lg={12}>
                      <Card size="small" title="Top 模型（点击可下钻明细）">
                        <Table
                          rowKey={(r: any) => String(r.model_code)}
                          size="small"
                          loading={dashboardQuery.isFetching}
                          dataSource={(dashboardQuery.data as AfterSalesDashboardResponse | undefined)?.top_models ?? []}
                          pagination={{ pageSize: 8, showSizeChanger: true }}
                          columns={[
                            {
                              title: '模型',
                              key: 'model',
                              ellipsis: true,
                              render: (_: any, r: any) => {
                                const main = `${r.model_code}${r.model_name ? ` ${r.model_name}` : ''}`
                                const phrase = String(r.bundle_preset_phrase ?? '').trim()
                                if (!phrase) return main
                                const pillStyle: CSSProperties = {
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
                                }
                                return (
                                  <span style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
                                    <span style={{ minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                      {main}
                                    </span>
                                    <Tooltip title={phrase}>
                                      <span style={pillStyle}>{phrase}</span>
                                    </Tooltip>
                                  </span>
                                )
                              },
                            },
                            { title: '发货', dataIndex: 'shipped_qty', width: 110 },
                            { title: '退货', dataIndex: 'returned_qty', width: 110 },
                            {
                              title: '退货率',
                              dataIndex: 'return_rate',
                              width: 160,
                              render: (v: any) => {
                                const n = Number(v ?? 0) * 100
                                return (
                                  <Progress
                                    percent={Number.isFinite(n) ? Number(n.toFixed(2)) : 0}
                                    size="small"
                                    strokeColor={dashboardView === 'ops' ? opsStroke : factoryStroke}
                                  />
                                )
                              },
                            },
                          ]}
                          onRow={(r: any) => ({
                            onClick: async () => {
                              form.setFieldsValue({ model_code: String(r.model_code || '') })
                              setActiveTab('detail')
                              await onQueryDetail(1, detailPageSize)
                            },
                          })}
                        />
                      </Card>
                    </Col>
                    <Col xs={24} lg={12}>
                      <Card size="small" title="Top 货品 / Top 链接（点击可下钻明细）">
                        <Tabs
                          items={[
                            {
                              key: 'sku',
                              label: '货品',
                              children: (
                                <Table
                                  rowKey={(r: any) => String(r.sku_code)}
                                  size="small"
                                  loading={dashboardQuery.isFetching}
                                  dataSource={(dashboardQuery.data as AfterSalesDashboardResponse | undefined)?.top_skus ?? []}
                                  pagination={{ pageSize: 8, showSizeChanger: true }}
                                  columns={[
                                    { title: 'SKU', dataIndex: 'sku_code', width: 150, ellipsis: true },
                                    { title: '规格（最常见）', dataIndex: 'spec_text', ellipsis: true },
                                    { title: '发货', dataIndex: 'shipped_qty', width: 110 },
                                    { title: '退货', dataIndex: 'returned_qty', width: 110 },
                                    {
                                      title: '退货率',
                                      dataIndex: 'return_rate',
                                      width: 160,
                                      render: (v: any) => {
                                        const n = Number(v ?? 0) * 100
                                        return (
                                          <Progress
                                            percent={Number.isFinite(n) ? Number(n.toFixed(2)) : 0}
                                            size="small"
                                            strokeColor={dashboardView === 'ops' ? opsStroke : factoryStroke}
                                          />
                                        )
                                      },
                                    },
                                  ]}
                                  onRow={(r: any) => ({
                                    onClick: async () => {
                                      form.setFieldsValue({ sku_code: String(r.sku_code || '') })
                                      setActiveTab('detail')
                                      await onQueryDetail(1, detailPageSize)
                                    },
                                  })}
                                />
                              ),
                            },
                            {
                              key: 'link',
                              label: '链接',
                              children: (
                                <Table
                                  rowKey={(r: any) => String(r.product_link_id)}
                                  size="small"
                                  loading={dashboardQuery.isFetching}
                                  dataSource={(dashboardQuery.data as AfterSalesDashboardResponse | undefined)?.top_links ?? []}
                                  pagination={{ pageSize: 8, showSizeChanger: true }}
                                  columns={[
                                    {
                                      title: '链接ID',
                                      dataIndex: 'product_link_id',
                                      width: 140,
                                      ellipsis: true,
                                      render: (v: any) => {
                                        const id = String(v ?? '').trim()
                                        if (!id) return '-'
                                        const href = `https://detail.tmall.com/item.htm?id=${encodeURIComponent(id)}`
                                        return (
                                          <a href={href} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>
                                            {id}
                                          </a>
                                        )
                                      },
                                    },
                                    { title: '规格（最常见）', dataIndex: 'spec_text', ellipsis: true },
                                    { title: '发货', dataIndex: 'shipped_qty', width: 110 },
                                    { title: '退货', dataIndex: 'returned_qty', width: 110 },
                                    {
                                      title: '退货率',
                                      dataIndex: 'return_rate',
                                      width: 160,
                                      render: (v: any) => {
                                        const n = Number(v ?? 0) * 100
                                        return (
                                          <Progress
                                            percent={Number.isFinite(n) ? Number(n.toFixed(2)) : 0}
                                            size="small"
                                            strokeColor={dashboardView === 'ops' ? opsStroke : factoryStroke}
                                          />
                                        )
                                      },
                                    },
                                  ]}
                                  onRow={(r: any) => ({
                                    onClick: async () => {
                                      form.setFieldsValue({ product_link_id: String(r.product_link_id || '') })
                                      setActiveTab('detail')
                                      await onQueryDetail(1, detailPageSize)
                                    },
                                  })}
                                />
                              ),
                            },
                          ]}
                        />
                      </Card>
                    </Col>
                  </Row>
                </>
              ),
            },
            {
              key: 'rate',
              label: <span style={{ color: activeTab === 'rate' ? activeTabColor : undefined }}>退货率（按SKU汇总）</span>,
              children: (
                <>
                  {error ? (
                    <Alert type="error" showIcon message="查询失败" description={error} style={{ marginBottom: 12 }} />
                  ) : null}
                  {data?.unmatched_returns_missing_order_no ? (
                    <Alert
                      type="warning"
                      showIcon
                      style={{ marginBottom: 12 }}
                      message="数据质量提示"
                      description={`存在 ${data.unmatched_returns_missing_order_no} 条售后记录缺少订单号，无法参与强关联归因（建议在 ERP 导出时开启网店订单号）。`}
                    />
                  ) : null}
                  <Table<ReturnsRateBySkuItem>
                    rowKey={(r) => `${r.period}-${r.channel ?? ''}-${r.sku_code ?? ''}`}
                    loading={loading}
                    columns={columns}
                    dataSource={data?.items ?? []}
                    pagination={{ pageSize: 50, showSizeChanger: true }}
                    scroll={{ x: 1100 }}
                  />
                </>
              ),
            },
            {
              key: 'detail',
              label: <span style={{ color: activeTab === 'detail' ? activeTabColor : undefined }}>售后明细（原因/规格/申请日期）</span>,
              children: (
                <>
                  {detailError ? (
                    <Alert type="error" showIcon message="明细查询失败" description={detailError} style={{ marginBottom: 12 }} />
                  ) : null}
                  <Table<AfterSalesLineItem>
                    rowKey="id"
                    size="small"
                    loading={detailLoading}
                    columns={detailColumns}
                    dataSource={detailData?.items ?? []}
                    pagination={{
                      current: detailPage,
                      pageSize: detailPageSize,
                      total: detailData?.total ?? 0,
                      showSizeChanger: true,
                      onChange: (p, ps) => onQueryDetail(p, ps),
                    }}
                    scroll={{ x: 1400 }}
                  />
                </>
              ),
            },
          ]}
        />
      </Card>

      <Drawer
        title="上传售后退货单（xlsx 导入）"
        open={uploadDrawerOpen}
        width={860}
        onClose={() => setUploadDrawerOpen(false)}
      >
        <Space direction="vertical" style={{ width: '100%' }} size={12}>
          <Alert
            type="info"
            showIcon
            message="说明"
            description="建议流程：先导入发货单（/costing/shipments），再导入售后退货单；导入后回到本页查询退货率。"
          />
          <Space wrap>
            <Upload
              accept=".xlsx"
              maxCount={1}
              beforeUpload={(file) => {
                setUploadFile(file as any)
                return false
              }}
              onRemove={() => setUploadFile(null)}
            >
              <Button disabled={uploading}>选择文件（.xlsx）</Button>
            </Upload>
            <Typography.Text type="secondary">{uploadFile ? uploadFile.name : '未选择文件'}</Typography.Text>
          </Space>
          <Space wrap>
            <Typography.Text>导出日期</Typography.Text>
            <DatePicker
              allowClear
              value={uploadExportDate ? dayjs(uploadExportDate) : null}
              format="YYYY-MM-DD"
              onChange={(d) => setUploadExportDate(d ? d.format('YYYY-MM-DD') : undefined)}
            />
            <Input
              placeholder="requested_by（可空）"
              style={{ width: 220 }}
              value={uploadRequestedBy}
              onChange={(e) => setUploadRequestedBy(e.target.value)}
            />
            <Button
              type="primary"
              loading={uploading}
              onClick={async () => {
                if (!uploadFile) {
                  message.warning('请先选择一个 .xlsx 文件')
                  return
                }
                setUploading(true)
                try {
                  const resp = await importAfterSalesXlsx({
                    file: uploadFile,
                    export_date: uploadExportDate,
                    requested_by: uploadRequestedBy?.trim() || undefined,
                  })
                  setLastImportSummary(
                    `batch=${resp.id} 插入${resp.inserted_rows} 跳过${resp.skipped_rows} 异常${resp.exception_rows}`,
                  )
                  message.success('售后退货单导入成功')
                  setUploadFile(null)
                  batchesQuery.refetch()
                } catch (e: any) {
                  message.error(String(e?.response?.data?.detail ?? e?.message ?? e))
                } finally {
                  setUploading(false)
                }
              }}
            >
              上传并导入
            </Button>
          </Space>
          {lastImportSummary ? <Alert type="success" showIcon message="最近一次导入" description={lastImportSummary} /> : null}
        </Space>
      </Drawer>

      <Drawer
        title="导入记录（最近）"
        open={batchesDrawerOpen}
        width={980}
        onClose={() => setBatchesDrawerOpen(false)}
        extra={
          <Button size="small" onClick={() => batchesQuery.refetch()} loading={batchesQuery.isFetching}>
            刷新
          </Button>
        }
      >
        <Table<AfterSalesImportBatch>
          rowKey="id"
          size="small"
          loading={batchesQuery.isFetching}
          dataSource={(batchesQuery.data?.items ?? []) as AfterSalesImportBatch[]}
          pagination={{
            current: batchPage,
            pageSize: batchPageSize,
            total: batchesQuery.data?.total ?? 0,
            showSizeChanger: true,
            onChange: (p, ps) => {
              setBatchPage(p)
              setBatchPageSize(ps)
            },
          }}
          columns={[
            { title: '导入批次', dataIndex: 'id', width: 220, ellipsis: true },
            { title: '文件名', dataIndex: 'file_name', width: 260, ellipsis: true },
            { title: '导出日期', dataIndex: 'export_date', width: 120, render: (v) => String(v ?? '-') },
            { title: '插入', dataIndex: 'inserted_rows', width: 90 },
            { title: '跳过', dataIndex: 'skipped_rows', width: 90 },
            { title: '异常', dataIndex: 'exception_rows', width: 90 },
            { title: '状态', dataIndex: 'status', width: 120 },
            { title: '导入时间', dataIndex: 'created_at', width: 180, ellipsis: true },
          ]}
          scroll={{ x: 1200 }}
        />
        <Typography.Text type="secondary">
          提示：若“查询为空/失败”，通常是 1）还没导入发货单（/costing/shipments），或 2）时间范围过大导致查询超时；可先缩小到 30~90 天再试。
        </Typography.Text>
      </Drawer>
    </div>
  )
}

export default AfterSalesInsightsPage

