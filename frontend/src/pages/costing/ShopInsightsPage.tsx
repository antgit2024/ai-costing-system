import { Alert, Button, Card, Checkbox, DatePicker, Form, Input, Select, Space, Table, Tabs, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import dayjs from 'dayjs'
import { useEffect, useMemo, useRef, useState } from 'react'

import {
  fetchProfitByChannel,
  fetchReturnsRateByChannel,
  fetchProfitByChannelSnapshot,
  fetchReturnsRateByChannelSnapshot,
  refreshProfitByChannelSnapshot,
  refreshReturnsRateByChannelSnapshot,
} from '@/services/planner'
import type {
  ProfitByChannelItem,
  ProfitByChannelResponse,
  ReturnsRateByChannelItem,
  ReturnsRateByChannelResponse,
} from '@/types/planner'
import { CostQualityBadge } from '@/components/costing/CostQualityBadge'

type GroupBy = 'day' | 'month'

const STORAGE_KEY = 'insights.shops.lastQuery.v1'

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

const formatCoverage = (withBom: number, total: number) => {
  if (!total) return '-'
  const pct = (withBom / total) * 100
  return `${withBom}/${total}（${pct.toFixed(1)}%）`
}

const ShopInsightsPage = () => {
  const [form] = Form.useForm()
  const [activeTab, setActiveTab] = useState<'profit' | 'returns'>('profit')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [dataProfit, setDataProfit] = useState<ProfitByChannelResponse | null>(null)
  const [dataReturns, setDataReturns] = useState<ReturnsRateByChannelResponse | null>(null)
  const [onlyFullCoverage, setOnlyFullCoverage] = useState(false)
  const didInitRef = useRef(false)
  const [useSnapshot, setUseSnapshot] = useState(true)
  const [quickDays, setQuickDays] = useState<7 | 30 | 90>(30)
  const [computedAt, setComputedAt] = useState<string | null>(null)

  const profitColumns = useMemo<ColumnsType<ProfitByChannelItem>>(
    () => [
      { title: '周期', dataIndex: 'period', key: 'period', width: 140 },
      { title: '渠道', dataIndex: 'channel', key: 'channel', width: 160 },
      { title: '覆盖率(成本)', key: 'coverage', width: 140, render: (_, r) => formatCoverage(r.lines_with_bom_snapshots, r.shipment_lines_total) },
      { title: '发货数量', dataIndex: 'shipped_qty', key: 'shipped_qty', width: 100, render: formatQty },
      { title: '销售额', dataIndex: 'revenue_amount', key: 'revenue_amount', width: 110, render: formatMoney },
      { title: '成本', dataIndex: 'cost_amount', key: 'cost_amount', width: 110, render: formatMoney },
      { title: '毛利', dataIndex: 'gross_profit', key: 'gross_profit', width: 110, render: formatMoney },
      { title: '毛利率', dataIndex: 'gross_margin', key: 'gross_margin', width: 100, render: formatPercent },
      { title: '退款金额', dataIndex: 'refund_amount', key: 'refund_amount', width: 110, render: formatMoney },
      { title: '净利润', dataIndex: 'net_profit', key: 'net_profit', width: 110, render: formatMoney },
      { title: '净利率', dataIndex: 'net_margin', key: 'net_margin', width: 100, render: formatPercent },
      {
        title: '成本可信度',
        key: 'cost_quality',
        width: 110,
        align: 'center',
        render: (_, r) => <CostQualityBadge badge={r.cost_quality} size="small" />,
      },
    ],
    [],
  )

  const returnsColumns = useMemo<ColumnsType<ReturnsRateByChannelItem>>(
    () => [
      { title: '周期', dataIndex: 'period', key: 'period', width: 140 },
      { title: '渠道', dataIndex: 'channel', key: 'channel', width: 160 },
      { title: '发货行数', dataIndex: 'shipment_lines_total', key: 'shipment_lines_total', width: 110 },
      { title: '发货数量', dataIndex: 'shipped_qty', key: 'shipped_qty', width: 100, render: formatQty },
      { title: '退货数量', dataIndex: 'returned_qty', key: 'returned_qty', width: 100, render: formatQty },
      { title: '退货率(件)', dataIndex: 'return_rate', key: 'return_rate', width: 120, render: formatPercent },
      { title: '发货金额', dataIndex: 'shipped_amount', key: 'shipped_amount', width: 120, render: formatMoney },
      { title: '退款金额', dataIndex: 'refund_amount', key: 'refund_amount', width: 120, render: formatMoney },
      { title: '退款率(额)', dataIndex: 'refund_rate', key: 'refund_rate', width: 120, render: formatPercent },
      {
        title: '成本可信度',
        key: 'cost_quality',
        width: 110,
        align: 'center',
        render: (_, r) => <CostQualityBadge badge={r.cost_quality} size="small" />,
      },
    ],
    [],
  )

  const onQuery = async () => {
    setError(null)
    const v = await form.validateFields()
    const range = v.range as [dayjs.Dayjs, dayjs.Dayjs]
    const groupBy = v.group_by as GroupBy
    const start = range[0].startOf('day').toISOString()
    const end = range[1].endOf('day').toISOString()

    setLoading(true)
    try {
      try {
        if (typeof window !== 'undefined') {
          window.localStorage.setItem(
            STORAGE_KEY,
            JSON.stringify({
              active_tab: activeTab,
              start,
              end,
              group_by: groupBy,
              channel: v.channel?.trim() || undefined,
              only_full_coverage: onlyFullCoverage,
            }),
          )
        }
      } catch {
        // ignore storage errors
      }
      const channel = v.channel?.trim() || undefined
      if (useSnapshot) {
        try {
          if (activeTab === 'profit') {
            const snap = await fetchProfitByChannelSnapshot({ range_days: quickDays, group_by: groupBy, channel })
            setComputedAt(String((snap as any)?.computed_at ?? '') || null)
            setDataProfit(snap.data as any)
            setDataReturns(null)
          } else {
            const snap = await fetchReturnsRateByChannelSnapshot({ range_days: quickDays, group_by: groupBy, channel })
            setComputedAt(String((snap as any)?.computed_at ?? '') || null)
            setDataReturns(snap.data as any)
            setDataProfit(null)
          }
          setLoading(false)
          return
        } catch (e: any) {
          // Cache miss -> fall back to live query
          setComputedAt(null)
        }
      }
      if (activeTab === 'profit') {
        const resp = await fetchProfitByChannel({ start, end, group_by: groupBy, channel })
        setDataProfit(resp)
        setDataReturns(null)
      } else {
        const resp = await fetchReturnsRateByChannel({ start, end, group_by: groupBy, channel })
        setDataReturns(resp)
        setDataProfit(null)
      }
    } catch (e: any) {
      setError(String(e?.response?.data?.detail ?? e?.message ?? e))
    } finally {
      setLoading(false)
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
        })
        setActiveTab(saved?.active_tab === 'returns' ? 'returns' : 'profit')
        setOnlyFullCoverage(Boolean(saved?.only_full_coverage))
      } else {
        form.setFieldsValue({
          group_by: 'month',
          range: [dayjs().subtract(30, 'day'), dayjs()],
        })
      }
    } catch {
      // ignore
    }

    // 首屏自动查询一次，避免“进来空白”
    onQuery()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const applyQuickRange = async (days: number) => {
    const d = days === 7 || days === 30 || days === 90 ? (days as 7 | 30 | 90) : 30
    setQuickDays(d)
    const range: [dayjs.Dayjs, dayjs.Dayjs] = [dayjs().subtract(days, 'day'), dayjs()]
    form.setFieldsValue({ range })
    await onQuery()
  }

  const refreshSnapshotNow = async () => {
    const v = await form.validateFields()
    const groupBy = v.group_by as GroupBy
    const channel = v.channel?.trim() || undefined
    setLoading(true)
    try {
      if (activeTab === 'profit') {
        await refreshProfitByChannelSnapshot({ range_days: quickDays, group_by: groupBy, channel, operator_id: 'planner-ui' })
      } else {
        await refreshReturnsRateByChannelSnapshot({ range_days: quickDays, group_by: groupBy, channel, operator_id: 'planner-ui' })
      }
      await onQuery()
    } catch (e: any) {
      setError(String(e?.response?.data?.detail ?? e?.message ?? e))
    } finally {
      setLoading(false)
    }
  }

  const filteredProfitItems = useMemo(() => {
    const items = dataProfit?.items ?? []
    if (!onlyFullCoverage) return items
    return items.filter((it) => (it.shipment_lines_total || 0) > 0 && it.lines_with_bom_snapshots === it.shipment_lines_total)
  }, [dataProfit, onlyFullCoverage])

  return (
    <div style={{ padding: 16 }}>
      <Typography.Title level={3} style={{ margin: '0 0 12px' }}>
        数据洞察 / 店铺数据（按渠道汇总）
      </Typography.Title>

      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 12 }}
        message="说明（2025 分析期：边搭建边算）"
        description={
          <div>
            <div>本页只在你选择的时间范围内查询汇总，不会全量重算。</div>
            <div>利润口径（当前版）：净利润=(销售额-退款)-成本（不考虑返库/冲销）。</div>
            <div>成本覆盖率=有 BOM 快照的发货行 / 总发货行。未覆盖的行不会阻塞，只会让成本偏低。</div>
          </div>
        }
      />

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
          <Form.Item label="粒度" name="group_by">
            <Select style={{ width: 100 }} options={[{ value: 'month', label: '按月' }, { value: 'day', label: '按日' }]} />
          </Form.Item>
          <Form.Item label="渠道" name="channel">
            <Input placeholder="可选：店铺/渠道（留空=全部）" style={{ width: 200 }} allowClear />
          </Form.Item>
          <Form.Item>
            <Space>
              <Button type="primary" onClick={onQuery} loading={loading}>
                查询
              </Button>
              <Button onClick={refreshSnapshotNow} disabled={!useSnapshot} loading={loading}>
                刷新数据
              </Button>
              <Button onClick={() => setUseSnapshot((v) => !v)} disabled={loading}>
                {useSnapshot ? '切到实时' : '切到缓存'}
              </Button>
              <Button
                onClick={() => {
                  form.resetFields()
                  setDataProfit(null)
                  setDataReturns(null)
                  setError(null)
                }}
              >
                重置
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Card>

      {error ? <Alert type="error" showIcon message="查询失败" description={error} style={{ marginBottom: 12 }} /> : null}

      {useSnapshot && computedAt ? (
        <Alert
          type="success"
          showIcon
          style={{ marginBottom: 12 }}
          message="当前数据来自夜间缓存"
          description={<span>数据更新时间：{computedAt}</span>}
        />
      ) : null}

      <Card size="small">
        <Tabs
          activeKey={activeTab}
          onChange={(k) => setActiveTab(k as any)}
          items={[
            {
              key: 'profit',
              label: '渠道利润',
              children: (
                <>
                  {dataProfit && (dataProfit.items ?? []).length === 0 ? (
                    <Alert
                      type="info"
                      showIcon
                      style={{ marginBottom: 12 }}
                      message="当前范围暂无数据"
                      description={
                        <Space wrap>
                          <span>建议先点右上“近30天/近90天”查看是否有数据。</span>
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
                  {dataProfit ? (
                    <Alert
                      type={dataProfit.total_shipment_lines === dataProfit.lines_with_bom_snapshots ? 'success' : 'warning'}
                      showIcon
                      style={{ marginBottom: 12 }}
                      message="成本覆盖率（本次范围内）"
                      description={
                        <div>
                          <div>
                            总发货行：{dataProfit.total_shipment_lines}；有 BOM 快照行：{dataProfit.lines_with_bom_snapshots}；缺成本字段行：
                            {dataProfit.lines_missing_costing}
                          </div>
                          <div style={{ marginTop: 8 }}>
                            <Checkbox checked={onlyFullCoverage} onChange={(e) => setOnlyFullCoverage(e.target.checked)}>
                              仅显示覆盖率=100% 的渠道分组
                            </Checkbox>
                          </div>
                        </div>
                      }
                    />
                  ) : null}
                  <Table<ProfitByChannelItem>
                    rowKey={(r) => `${r.period}-${r.channel ?? ''}`}
                    loading={loading}
                    columns={profitColumns}
                    dataSource={filteredProfitItems}
                    pagination={{ pageSize: 50, showSizeChanger: true }}
                    scroll={{ x: 1360 }}
                  />
                </>
              ),
            },
            {
              key: 'returns',
              label: '渠道退货率',
              children: (
                <>
                  {dataReturns && (dataReturns.items ?? []).length === 0 ? (
                    <Alert
                      type="info"
                      showIcon
                      style={{ marginBottom: 12 }}
                      message="当前范围暂无数据"
                      description={
                        <Space wrap>
                          <span>建议先点右上“近30天/近90天”查看是否有数据。</span>
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
                  {dataReturns?.unmatched_returns_missing_order_no ? (
                    <Alert
                      type="warning"
                      showIcon
                      style={{ marginBottom: 12 }}
                      message="数据质量提示"
                      description={`存在 ${dataReturns.unmatched_returns_missing_order_no} 条售后记录缺少订单号，无法参与强关联归因（建议在 ERP 导出时开启网店订单号）。`}
                    />
                  ) : null}
                  <Table<ReturnsRateByChannelItem>
                    rowKey={(r) => `${r.period}-${r.channel ?? ''}`}
                    loading={loading}
                    columns={returnsColumns}
                    dataSource={dataReturns?.items ?? []}
                    pagination={{ pageSize: 50, showSizeChanger: true }}
                    scroll={{ x: 1260 }}
                  />
                </>
              ),
            },
          ]}
        />
      </Card>
    </div>
  )
}

export default ShopInsightsPage

