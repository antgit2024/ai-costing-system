/**
 * 🔄 售后管理 — 上架员/客服日常工作台.
 *
 * v0.2 (2026-05-12):
 *   - 拉 /after-sales/lines/search 得到最近 30 天的售后行,按 status / status_name 客户端分组
 *   - 顶部 4 个 KPI 卡：总单 / 待审核 / 已退款 / 待补发
 *   - 4 个 Tab 显示真实表格,带常用列 (售后单号 / 平台订单 / 商品 / 状态 / 金额 / 时间)
 *   - 行尾标签: source_system='jackyun' / 'superseded_by_jackyun' (来源/升级标记)
 *   - "立即同步" 按钮直接跳 /costing/integrations 页面 (统一入口,不在这里重复实现)
 *
 * 后端 search_lines 当前不支持 status / source_system 过滤,所以全部一次拉到本地按
 * status_name 分组. 30 天窗口 + 默认 page_size=500 足够覆盖中小店铺日常体量;
 * 如果未来体量上去,加分页 + 服务端过滤.
 */
import { Card, Tabs, Typography, Space, Tag, Alert, DatePicker, Table, Statistic, Row, Col, Tooltip, Button } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import dayjs, { type Dayjs } from 'dayjs'
import ThunderboltOutlined from '@ant-design/icons/lib/icons/ThunderboltOutlined'
import ReloadOutlined from '@ant-design/icons/lib/icons/ReloadOutlined'

import { fetchAfterSalesLines } from '@/services/planner'
import type { AfterSalesLineItem } from '@/types/planner'

const { Title, Text } = Typography
const { RangePicker } = DatePicker

type AfterSalesBizTabKey = 'pending' | 'refunded' | 'reship' | 'all'

// Classify a single line into one of our four UI buckets.
// Refund lifecycle is messy and 12+ codes — collapse into the buckets the
// floor team actually distinguishes between.
const classifyLine = (line: AfterSalesLineItem): AfterSalesBizTabKey => {
  const has_goods_return = (line.metadata_json as Record<string, unknown> | undefined)?.has_goods_return
  if (has_goods_return === 3) return 'reship' // 补寄

  const s = (line.status || '').toLowerCase()
  if (s === 'success' || s === 'closed') return 'refunded'
  if (s === 'pending' || s === 'rejected') return 'pending'

  // Fallback on Chinese explain when status code is absent (legacy Excel rows).
  const name = line.status_name || ''
  if (name.includes('成功') || name.includes('完成')) return 'refunded'
  if (name.includes('待') || name.includes('同意') || name.includes('退货') || name.includes('退款中')) {
    return 'pending'
  }
  return 'all'
}

const STATUS_TAG_COLOR: Record<string, string> = {
  success: 'green',
  pending: 'orange',
  rejected: 'red',
  closed: 'default',
}

export default function AfterSalesManagementPage() {
  const navigate = useNavigate()
  const [sp, setSp] = useSearchParams()

  const initialTab: AfterSalesBizTabKey = useMemo(() => {
    const t = String(sp.get('tab') ?? '').trim() as AfterSalesBizTabKey
    if (t === 'refunded' || t === 'reship' || t === 'all') return t
    return 'pending'
  }, [sp])
  const [activeTab, setActiveTab] = useState<AfterSalesBizTabKey>(initialTab)

  const [range, setRange] = useState<[Dayjs, Dayjs]>(() => [dayjs().subtract(30, 'day').startOf('day'), dayjs().endOf('day')])

  const start = range[0].format('YYYY-MM-DD HH:mm:ss')
  const end = range[1].format('YYYY-MM-DD HH:mm:ss')

  const linesQuery = useQuery({
    queryKey: ['after-sales-mgmt', start, end],
    queryFn: () =>
      fetchAfterSalesLines({
        start,
        end,
        time_basis: 'applied',
        page: 1,
        page_size: 500,
      }),
  })

  const items = linesQuery.data?.items ?? []

  // KPIs + per-tab buckets in one pass — one O(n) scan.
  const buckets = useMemo(() => {
    const acc: Record<AfterSalesBizTabKey, AfterSalesLineItem[]> = {
      pending: [],
      refunded: [],
      reship: [],
      all: items,
    }
    for (const line of items) {
      const k = classifyLine(line)
      if (k !== 'all') acc[k].push(line)
    }
    return acc
  }, [items])

  const refundedAmountSum = useMemo(() => {
    return buckets.refunded.reduce((sum, line) => sum + Number(line.refund_amount || 0), 0)
  }, [buckets.refunded])

  const handleTabChange = (k: string) => {
    setActiveTab(k as AfterSalesBizTabKey)
    const next = new URLSearchParams(sp)
    next.set('tab', k)
    setSp(next, { replace: true })
  }

  const columns: ColumnsType<AfterSalesLineItem> = [
    {
      title: '售后单号',
      dataIndex: 'after_sales_no',
      width: 180,
      ellipsis: true,
      render: (v: string | null) => v || <Text type="secondary">-</Text>,
    },
    {
      title: '平台订单 / ERP',
      width: 230,
      render: (_: unknown, line) => (
        <Space direction="vertical" size={0}>
          <Text style={{ fontSize: 12 }}>{line.platform_order_no || line.order_no || <Text type="secondary">-</Text>}</Text>
          {line.erp_order_no ? (
            <Text type="secondary" style={{ fontSize: 11 }}>
              ERP: {line.erp_order_no}
            </Text>
          ) : null}
        </Space>
      ),
    },
    { title: '渠道', dataIndex: 'channel', width: 120, ellipsis: true },
    {
      title: '商品',
      width: 280,
      ellipsis: true,
      render: (_: unknown, line) => (
        <Space direction="vertical" size={0}>
          <Tooltip title={line.product_name}>
            <Text style={{ fontSize: 12 }}>{line.product_name || <Text type="secondary">-</Text>}</Text>
          </Tooltip>
          <Space size={6}>
            {line.product_code ? <Tag color="cyan" style={{ marginInlineEnd: 0 }}>商家:{line.product_code}</Tag> : null}
            {line.sku_code ? <Tag style={{ marginInlineEnd: 0 }}>{line.sku_code}</Tag> : null}
          </Space>
        </Space>
      ),
    },
    { title: '规格', dataIndex: 'spec_text', width: 140, ellipsis: true, render: (v: string | null) => v || '-' },
    {
      title: '数量',
      dataIndex: 'return_qty',
      width: 70,
      align: 'right',
      render: (v: string | null) => (v ? Number(v).toFixed(0) : '-'),
    },
    {
      title: '退款 ¥',
      dataIndex: 'refund_amount',
      width: 100,
      align: 'right',
      render: (v: string | null) => (v ? Number(v).toFixed(2) : '-'),
    },
    {
      title: '状态',
      width: 140,
      render: (_: unknown, line) => (
        <Space direction="vertical" size={0}>
          {line.status ? (
            <Tag color={STATUS_TAG_COLOR[line.status] || 'default'} style={{ marginInlineEnd: 0 }}>
              {line.status}
            </Tag>
          ) : null}
          {line.status_name ? <Text style={{ fontSize: 11 }}>{line.status_name}</Text> : null}
        </Space>
      ),
    },
    { title: '原因', dataIndex: 'reason', width: 130, ellipsis: true, render: (v: string | null) => v || '-' },
    {
      title: '申请时间',
      dataIndex: 'applied_at',
      width: 140,
      render: (v: string | null) => (v ? dayjs(v).format('MM-DD HH:mm') : '-'),
    },
    {
      title: '来源',
      width: 130,
      render: (_: unknown, line) => (
        <Space size={4} wrap>
          {line.source_system === 'jackyun' ? (
            <Tag color="purple" style={{ marginInlineEnd: 0 }}>
              吉客云
            </Tag>
          ) : (
            <Tag style={{ marginInlineEnd: 0 }}>Excel</Tag>
          )}
          {line.tag && line.tag.includes('superseded_by_jackyun') ? (
            <Tooltip title="已被吉客云 API 拉取的更新版本覆盖">
              <Tag color="default" style={{ marginInlineEnd: 0 }}>
                已升级
              </Tag>
            </Tooltip>
          ) : null}
        </Space>
      ),
    },
  ]

  const renderTable = (rows: AfterSalesLineItem[], emptyText: string) => (
    <Table<AfterSalesLineItem>
      rowKey="id"
      size="small"
      loading={linesQuery.isLoading || linesQuery.isFetching}
      dataSource={rows}
      columns={columns}
      scroll={{ x: 1500 }}
      pagination={{ pageSize: 30, showSizeChanger: true, showTotal: (t) => `共 ${t} 条` }}
      locale={{ emptyText }}
    />
  )

  return (
    <div style={{ padding: 16 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between' }}>
        <div>
          <Title level={3} style={{ marginBottom: 4 }}>
            售后管理
          </Title>
          <Text type="secondary">
            统一处理来自吉客云 API + Excel 上传的退款 / 补发 / 换货售后单。
          </Text>
        </div>
        <Space>
          <RangePicker value={range} onChange={(v) => v && v[0] && v[1] && setRange([v[0], v[1]])} allowClear={false} />
          <Button icon={<ReloadOutlined />} onClick={() => linesQuery.refetch()}>
            刷新
          </Button>
          <Button type="primary" icon={<ThunderboltOutlined />} onClick={() => navigate('/costing/integrations')}>
            去同步控制台
          </Button>
        </Space>
      </div>

      <Alert
        type="info"
        showIcon
        style={{ marginTop: 12 }}
        message="数据由吉客云 API 增量同步 + Excel 历史导入合并而成。"
        description="同一售后单号若同时存在 Excel 与吉客云数据,以吉客云为准 (Excel 行打 superseded_by_jackyun 标签保留)。如需手动触发同步,点右上角「去同步控制台」。"
      />

      <Row gutter={12} style={{ marginTop: 12 }}>
        <Col span={6}>
          <Card size="small">
            <Statistic title="时间窗口内售后单 (行)" value={items.length} />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic title="待审核 / 处理中" value={buckets.pending.length} valueStyle={{ color: '#fa8c16' }} />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic title="已退款" value={buckets.refunded.length} valueStyle={{ color: '#52c41a' }} />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic
              title="退款总金额 ¥"
              value={refundedAmountSum.toFixed(2)}
              valueStyle={{ color: '#52c41a' }}
            />
          </Card>
        </Col>
      </Row>

      <div style={{ marginTop: 12 }}>
        <Tabs
          activeKey={activeTab}
          onChange={handleTabChange}
          items={[
            {
              key: 'pending',
              label: `待审核 / 处理中 (${buckets.pending.length})`,
              children: renderTable(buckets.pending, '暂无待审核售后单'),
            },
            {
              key: 'refunded',
              label: `已退款 (${buckets.refunded.length})`,
              children: renderTable(buckets.refunded, '暂无已退款记录'),
            },
            {
              key: 'reship',
              label: `待补发 (${buckets.reship.length})`,
              children: renderTable(buckets.reship, '暂无补发任务'),
            },
            {
              key: 'all',
              label: `全部 (${items.length})`,
              children: renderTable(items, '该时间窗口暂无售后数据'),
            },
          ]}
        />
      </div>
    </div>
  )
}
