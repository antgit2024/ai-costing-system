import { Alert, Button, Card, DatePicker, Form, Input, Segmented, Select, Space, Table, Typography } from 'antd'
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table'
import dayjs from 'dayjs'
import { useMemo, useState } from 'react'

import { fetchSalesLines } from '@/services/planner'
import type { SalesLineItem, SalesLinesResponse } from '@/types/planner'

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

const SalesInsightsPage = () => {
  const [form] = Form.useForm()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [data, setData] = useState<SalesLinesResponse | null>(null)
  const [includeMissing, setIncludeMissing] = useState(true)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(50)
  const [shopOptions, setShopOptions] = useState<string[]>([])
  const [lastQuery, setLastQuery] = useState<{
    start: string
    end: string
    include_missing: boolean
    channel?: string
    sku_code?: string
    order_no?: string
    product_link_id?: string
  } | null>(null)

  const columns = useMemo<ColumnsType<SalesLineItem>>(
    () => [
      { title: '付款时间', dataIndex: 'payment_at', width: 120, ellipsis: true, render: (v) => formatDateToDay(v) },
      { title: '发货时间', dataIndex: 'completed_at', width: 120, ellipsis: true, render: (v) => formatDateToDay(v) },
      { title: '店铺', dataIndex: 'channel', width: 160, ellipsis: true, render: (v) => String(v ?? '-') },
      { title: '货品名称', dataIndex: 'sku_name', width: 200, ellipsis: true, render: (v) => String(v ?? '-') },
      { title: '交易规格', dataIndex: 'spec_text', width: 260, ellipsis: true, render: (v) => String(v ?? '-') },
      { title: '货品条码', dataIndex: 'sku_code', width: 160, ellipsis: true, render: (v) => String(v ?? '-') },
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
    }
    setLastQuery(base)
    await runQuery({ ...base, page: 1, page_size: pageSize })
  }

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
    <div style={{ padding: 16 }}>
      <Typography.Title level={3} style={{ margin: '0 0 12px' }}>
        数据洞察 / 销售分析（明细）
      </Typography.Title>

      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 12 }}
        message="说明（明细口径）"
        description={
          <div>
            <div>本页展示“发货明细行”并回填你们关心的成本字段：成本金额=快照 trace.costing.total_cost；成本单价=成本金额/数量。</div>
            <div>缺快照的行会显示成本为“-”（可通过绑定/异常处理逐步补齐覆盖率）。</div>
          </div>
        }
      />

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
              <Button type="primary" onClick={() => onQuery()} loading={loading}>
                查询
              </Button>
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

      {data ? (
        <Alert
          type={data.lines_with_bom_snapshots > 0 ? 'success' : 'warning'}
          showIcon
          style={{ marginBottom: 12 }}
          message="成本覆盖率（本次范围内）"
          description={
            <div>
              <div>
                有 BOM 快照行：{data.lines_with_bom_snapshots}；缺成本字段行：{data.lines_missing_costing}
              </div>
              <div style={{ color: '#888' }}>{data.note || ''}</div>
            </div>
          }
        />
      ) : null}

      <Card size="small">
        <Table
          rowKey="shipment_line_id"
          size="small"
          loading={loading}
          columns={columns}
          dataSource={data?.items ?? []}
          pagination={pagination}
          scroll={{ x: 2100 }}
        />
      </Card>
    </div>
  )
}

export default SalesInsightsPage

