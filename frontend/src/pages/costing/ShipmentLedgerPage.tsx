import { Alert, Button, Card, DatePicker, Form, Input, Select, Space, Table, Tabs, Tag, Tooltip, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import dayjs from 'dayjs'
import { useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'

import { fetchShipmentLines } from '@/services/planner'
import type { ShipmentLineListItem, ShipmentLineListResponse } from '@/types/planner'

const { Title, Text } = Typography

const safeString = (v: unknown): string => {
  if (v === null || v === undefined) return ''
  return String(v)
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

  const [ledgerTab, setLedgerTab] = useState<'all' | 'processed' | 'pending'>('all')
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
    shipment_no?: string
    order_no?: string
    product_link_id?: string
    spec_text?: string
    unresolved_reason?: string
  }>({})

  const shipmentLinesQuery = useQuery({
    queryKey: ['shipments', 'lines', ledgerTab, ledgerPage, ledgerPageSize, ledgerRange, ledgerFilters],
    queryFn: () =>
      fetchShipmentLines({
        page: ledgerPage,
        page_size: ledgerPageSize,
        start: ledgerRange?.[0]?.toISOString?.() ?? undefined,
        end: ledgerRange?.[1]?.toISOString?.() ?? undefined,
        status: ledgerTab === 'all' ? undefined : (ledgerTab as any),
        ...ledgerFilters,
      }),
    placeholderData: keepPreviousData,
  })

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
    { title: '发货单号', dataIndex: 'shipment_no', width: 160, ellipsis: true },
    { title: '订单号', dataIndex: 'order_no', width: 160, ellipsis: true },
    {
      title: '链接ID',
      dataIndex: 'product_link_id',
      width: 140,
      render: (v) => {
        const id = safeString(v).trim()
        if (!id) return '-'
        const href = `https://detail.tmall.com/item.htm?id=${encodeURIComponent(id)}`
        return (
          <a href={href} target="_blank" rel="noreferrer">
            {id}
          </a>
        )
      },
    },
    { title: '渠道', dataIndex: 'channel', width: 140, ellipsis: true },
    { title: 'SKU', dataIndex: 'sku_code', width: 160, ellipsis: true },
    { title: '商家编码', dataIndex: 'shop_spec_code', width: 160, ellipsis: true },
    {
      title: '绑定目标',
      key: 'bound_target',
      width: 220,
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
      title: '交易规格',
      dataIndex: 'spec_text',
      ellipsis: true,
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
    { title: '数量', dataIndex: 'qty', width: 90, render: (v) => safeString(v) || '-' },
    { title: '金额', dataIndex: 'revenue_amount', width: 110, render: (v) => safeString(v) || '-' },
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
    { title: '批次', dataIndex: 'batch_id', width: 220, ellipsis: true },
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
          <Button onClick={() => navigate('/costing/shipments/ops')}>去发货作业中心</Button>
        </Space>
      </div>

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
              <Space wrap>
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
                  onFinish={(values) => {
                    const next = {
                      channel: values.channel ? String(values.channel).trim() : undefined,
                      sku_code: values.sku_code ? String(values.sku_code).trim() : undefined,
                      shipment_no: values.shipment_no ? String(values.shipment_no).trim() : undefined,
                      order_no: values.order_no ? String(values.order_no).trim() : undefined,
                      product_link_id: values.product_link_id ? String(values.product_link_id).trim() : undefined,
                      spec_text: values.spec_text ? String(values.spec_text).trim() : undefined,
                      unresolved_reason: values.unresolved_reason ? String(values.unresolved_reason).trim() : undefined,
                    }
                    setLedgerFilters(next)
                    setLedgerPage(1)
                  }}
                >
                  <Form.Item name="sku_code">
                    <Input style={{ width: 140 }} placeholder="SKU" allowClear />
                  </Form.Item>
                  <Form.Item name="shipment_no">
                    <Input style={{ width: 150 }} placeholder="发货单号" allowClear />
                  </Form.Item>
                  <Form.Item name="order_no">
                    <Input style={{ width: 150 }} placeholder="订单号" allowClear />
                  </Form.Item>
                  <Form.Item name="product_link_id">
                    <Input style={{ width: 150 }} placeholder="链接ID" allowClear />
                  </Form.Item>
                  <Form.Item name="spec_text">
                    <Input style={{ width: 220 }} placeholder="交易规格" allowClear />
                  </Form.Item>
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
                    <Input style={{ width: 120 }} placeholder="渠道" allowClear />
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
            ]}
          />

          <div style={{ marginBottom: 10 }}>
            <Text type="secondary">
              说明：2025 模式不落 BOM 大快照但会落“计价结果/扣库”；2026 模式会落 BOM 快照。列表“已处理”口径统一为：有快照或有计价结果。
            </Text>
          </div>

          {isEmpty ? (
            <Alert
              type="info"
              showIcon
              style={{ marginBottom: 12 }}
              message="当前筛选范围内无记录"
              description="已默认查询最近 90 天。若你确认库里有数据，请扩大日期范围（左上角）或清空筛选条件后再查。"
            />
          ) : null}

          <Table
            rowKey="id"
            size="small"
            loading={shipmentLinesQuery.isFetching}
            dataSource={data?.items ?? []}
            pagination={{
              current: ledgerPage,
              pageSize: ledgerPageSize,
              total: data?.total ?? 0,
              showSizeChanger: true,
              showTotal: (t) => `共 ${t} 条`,
            }}
            onChange={(pagination) => {
              const p = pagination as any
              setLedgerPage(Number(p?.current) || 1)
              setLedgerPageSize(Number(p?.pageSize) || 50)
            }}
            columns={columns}
          />
        </Card>
      </div>
    </div>
  )
}

export default ShipmentLedgerPage

