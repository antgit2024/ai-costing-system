/**
 * Path A §A5 — Cost Rate Hub "🤖 自动算法日志" tab.
 *
 * Read-only audit surface for the auto pipeline:
 *   A2 班组工资聚合 → A3 固开摊销 → A4 班组分摊 → 上链 cost_rate_master
 *
 * For a chosen period (default = last full month), shows:
 *   1. A2 cost_center_payroll_snapshot rows (headcount / total_paid /
 *      rate_per_minute / data_source / warnings)
 *   2. A3 fixed_cost_amortization summary (by company, by category)
 *   3. A4 cost_allocation summary (by cost_center) + warnings
 *
 * Provides a "🔁 一键重算本月（A2+A3+A4）" button that calls the same
 * batch endpoints as the Cost Center master page — convenient when
 * the user is already on the Hub and wants to refresh rates after a
 * finance push.
 */

import {
  Alert,
  Button,
  Card,
  Col,
  DatePicker,
  Empty,
  message,
  Row,
  Space,
  Spin,
  Table,
  Tag,
  Tooltip,
  Typography,
} from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import dayjs, { Dayjs } from 'dayjs'
import { useState } from 'react'

import {
  aggregatePayrollBatch,
  fetchAllocationByCostCenter,
  fetchAllocationLines,
  fetchAmortizationByCategory,
  fetchAmortizationByCompany,
  fetchAmortizationLines,
  fetchCostCenters,
  fetchPayrollSnapshotsForPeriod,
  runCostAllocation,
  runFixedCostAmortization,
} from '../../../services/costCenter'
import type {
  CostAllocationLine,
  CostCenterPayrollSnapshot,
} from '../../../types/planner'

const { Text, Paragraph } = Typography

const FINANCE_TAG: Record<string, { color: string; label: string }> = {
  finance_payroll: { color: 'green', label: 'finance 真实数据' },
  finance_payroll_fallback: { color: 'gold', label: '⚠ 财务降级（无数据）' },
  finance_payment_requests: { color: 'green', label: 'finance 真实数据' },
  fallback: { color: 'gold', label: '⚠ 财务降级' },
  unavailable: { color: 'red', label: '🔴 finance 不可用' },
  empty: { color: 'default', label: '空（无源数据）' },
}

function financeTag(s?: string | null) {
  if (!s) return <Tag>—</Tag>
  const cfg = FINANCE_TAG[s] || { color: 'default', label: s }
  return <Tag color={cfg.color}>{cfg.label}</Tag>
}

function periodKey(p: Dayjs): string {
  return p.format('YYYY-MM')
}

// ---------------------------------------------------------------------------
// Sub-tables
// ---------------------------------------------------------------------------

function PayrollSnapshotsCard({ period }: { period: string }) {
  const ccQ = useQuery({
    queryKey: ['planner', 'costCenters', 'forLog'],
    queryFn: () => fetchCostCenters({ include_inactive: false, with_stats: false }),
    staleTime: 60_000,
  })
  const snapsQ = useQuery({
    queryKey: ['planner', 'payrollSnapshots', period],
    queryFn: () => fetchPayrollSnapshotsForPeriod(period),
    enabled: Boolean(period),
  })
  const ccById = new Map(ccQ.data?.items.map(cc => [cc.id, cc]) ?? [])
  const rows = snapsQ.data ?? []

  const columns = [
    {
      title: '班组',
      dataIndex: 'cost_center_id',
      width: 200,
      render: (id: string) => {
        const cc = ccById.get(id)
        return cc ? (
          <Space size={4}>
            <Text code>{cc.code}</Text>
            <Text>{cc.name}</Text>
          </Space>
        ) : (
          <Text type="secondary">{id}</Text>
        )
      },
    },
    { title: '人头', dataIndex: 'headcount', width: 70 },
    {
      title: '工资合计 (¥)',
      dataIndex: 'total_paid',
      width: 130,
      render: (v: number) =>
        <Text style={{ fontFamily: 'monospace' }}>{v.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}</Text>,
    },
    {
      title: '人均月薪 (¥)',
      dataIndex: 'avg_salary',
      width: 130,
      render: (v: number) =>
        <Text style={{ fontFamily: 'monospace' }}>{v.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}</Text>,
    },
    {
      title: '总分钟',
      dataIndex: 'total_minutes',
      width: 100,
      render: (v?: number | null) =>
        v == null ? <Text type="secondary">—</Text> : v.toLocaleString('zh-CN'),
    },
    {
      title: 'rate/分钟 (¥)',
      dataIndex: 'rate_per_minute',
      width: 130,
      render: (v?: number | null) =>
        v == null ? (
          <Tooltip title="缺 total_minutes，无法上链 cost_rate_master.labor_per_minute">
            <Tag color="default">未上链</Tag>
          </Tooltip>
        ) : (
          <Tag color="purple">{v.toFixed(4)}</Tag>
        ),
    },
    {
      title: 'finance 数据',
      dataIndex: 'data_source',
      width: 170,
      render: financeTag,
    },
    {
      title: '可信度',
      dataIndex: 'data_quality',
      width: 100,
      render: (v: string) =>
        v === 'green' ? <Tag color="green">🟢 高</Tag>
          : v === 'yellow' ? <Tag color="gold">🟡 中</Tag>
            : <Tag color="red">🔴 低</Tag>,
    },
    {
      title: '警告',
      dataIndex: 'warnings',
      render: (ws: string[]) =>
        !ws?.length ? <Text type="secondary">—</Text> : (
          <Space wrap size={2}>
            {ws.map((w, i) => <Tag key={i} color="orange">{w}</Tag>)}
          </Space>
        ),
    },
  ]

  return (
    <Card
      size="small"
      title={
        <Space>
          <Text strong>A2 · 班组工资 snapshots</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {rows.length} 行 · period={period}
          </Text>
        </Space>
      }
    >
      <Spin spinning={snapsQ.isLoading || ccQ.isLoading}>
        {rows.length === 0 ? (
          <Empty description={`暂无 A2 snapshot — 请先点击页面顶部 "🔁 一键重算"，或前往 班组主页 跑 A2`} />
        ) : (
          <Table<CostCenterPayrollSnapshot>
            rowKey="id"
            dataSource={rows}
            columns={columns as any}
            pagination={false}
            size="small"
            scroll={{ x: 1200 }}
          />
        )}
      </Spin>
    </Card>
  )
}

function AmortizationCard({ period }: { period: string }) {
  const linesQ = useQuery({
    queryKey: ['planner', 'amortizationLines', period],
    queryFn: () => fetchAmortizationLines(period),
    enabled: Boolean(period),
  })
  const byCompanyQ = useQuery({
    queryKey: ['planner', 'amortByCompany', period],
    queryFn: () => fetchAmortizationByCompany(period),
    enabled: Boolean(period),
  })
  const byCategoryQ = useQuery({
    queryKey: ['planner', 'amortByCategory', period],
    queryFn: () => fetchAmortizationByCategory(period),
    enabled: Boolean(period),
  })
  const lines = linesQ.data ?? []

  return (
    <Card
      size="small"
      title={
        <Space>
          <Text strong>A3 · 固开月度摊销</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {lines.length} 行 · period={period}
          </Text>
        </Space>
      }
    >
      <Spin spinning={linesQ.isLoading || byCompanyQ.isLoading || byCategoryQ.isLoading}>
        {lines.length === 0 ? (
          <Empty description={`暂无 A3 amortization line — 请先跑 A3 (顶部"一键重算"或 班组主页)`} />
        ) : (
          <Row gutter={12}>
            <Col span={12}>
              <Card size="small" title="按法人主体" bordered={false}>
                <Table
                  rowKey="company_id"
                  dataSource={byCompanyQ.data?.items ?? []}
                  pagination={false}
                  size="small"
                  columns={[
                    {
                      title: '主体',
                      dataIndex: 'company_id',
                      render: (v, r: any) => (
                        <Space size={4}>
                          <Text code>{v}</Text>
                          {r.company_name && <Text>{r.company_name}</Text>}
                        </Space>
                      ),
                    },
                    {
                      title: '总额 (¥)',
                      dataIndex: 'total',
                      width: 140,
                      align: 'right' as const,
                      render: (v: number) =>
                        <Text strong style={{ fontFamily: 'monospace' }}>
                          {v.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}
                        </Text>,
                    },
                  ]}
                />
              </Card>
            </Col>
            <Col span={12}>
              <Card size="small" title="按费用类别" bordered={false}>
                <Table
                  rowKey="category"
                  dataSource={byCategoryQ.data?.items ?? []}
                  pagination={false}
                  size="small"
                  columns={[
                    {
                      title: '类别',
                      dataIndex: 'category',
                      render: (v: string) => <Tag>{v}</Tag>,
                    },
                    {
                      title: '行数',
                      dataIndex: 'line_count',
                      width: 60,
                      align: 'right' as const,
                    },
                    {
                      title: '总额 (¥)',
                      dataIndex: 'total',
                      width: 140,
                      align: 'right' as const,
                      render: (v: number) =>
                        <Text strong style={{ fontFamily: 'monospace' }}>
                          {v.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}
                        </Text>,
                    },
                  ]}
                />
              </Card>
            </Col>
          </Row>
        )}
      </Spin>
    </Card>
  )
}

function AllocationCard({ period }: { period: string }) {
  const linesQ = useQuery({
    queryKey: ['planner', 'allocationLines', period],
    queryFn: () => fetchAllocationLines(period),
    enabled: Boolean(period),
  })
  const byCcQ = useQuery({
    queryKey: ['planner', 'allocByCc', period],
    queryFn: () => fetchAllocationByCostCenter(period),
    enabled: Boolean(period),
  })
  const ccQ = useQuery({
    queryKey: ['planner', 'costCenters', 'forAlloc'],
    queryFn: () => fetchCostCenters({ include_inactive: false, with_stats: false }),
    staleTime: 60_000,
  })
  const ccById = new Map(ccQ.data?.items.map(cc => [cc.id, cc]) ?? [])
  const lines = linesQ.data ?? []

  return (
    <Card
      size="small"
      title={
        <Space>
          <Text strong>A4 · 固开 → 班组分摊</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {lines.length} 行 · period={period}
          </Text>
        </Space>
      }
    >
      <Spin spinning={linesQ.isLoading || byCcQ.isLoading || ccQ.isLoading}>
        {lines.length === 0 ? (
          <Empty description="暂无 A4 cost_allocation_line — 请先跑 A4" />
        ) : (
          <>
            <Card size="small" title="按班组汇总" bordered={false} style={{ marginBottom: 12 }}>
              <Table
                rowKey="cost_center_id"
                dataSource={byCcQ.data?.items ?? []}
                pagination={false}
                size="small"
                columns={[
                  {
                    title: '班组',
                    dataIndex: 'cost_center_id',
                    render: (id: string) => {
                      const cc = ccById.get(id)
                      return cc ? (
                        <Space size={4}>
                          <Text code>{cc.code}</Text>
                          <Text>{cc.name}</Text>
                        </Space>
                      ) : (
                        <Text type="secondary">{id}</Text>
                      )
                    },
                  },
                  {
                    title: '分摊总额 (¥)',
                    dataIndex: 'total',
                    width: 160,
                    align: 'right' as const,
                    render: (v: number) =>
                      <Text strong style={{ fontFamily: 'monospace' }}>
                        {v.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}
                      </Text>,
                  },
                  {
                    title: '按类别拆分',
                    dataIndex: 'by_category',
                    render: (m: Record<string, number>) => (
                      <Space wrap size={4}>
                        {Object.entries(m).map(([k, v]) => (
                          <Tooltip key={k} title={`${k}: ¥${v.toFixed(2)}`}>
                            <Tag>{k}: ¥{v.toFixed(0)}</Tag>
                          </Tooltip>
                        ))}
                      </Space>
                    ),
                  },
                ]}
              />
            </Card>
            <Card size="small" title="按行明细 (含分摊基础 / fallback chain)" bordered={false}>
              <Table<CostAllocationLine>
                rowKey="id"
                dataSource={lines}
                pagination={{ pageSize: 20 }}
                size="small"
                scroll={{ x: 1200 }}
                columns={[
                  { title: '主体', dataIndex: 'source_company_id', width: 100 },
                  {
                    title: '类别',
                    dataIndex: 'source_expense_category',
                    width: 110,
                    render: (v: string) => <Tag>{v}</Tag>,
                  },
                  {
                    title: '源总额',
                    dataIndex: 'source_total_amount',
                    width: 100,
                    align: 'right' as const,
                    render: (v: number) => v.toFixed(2),
                  },
                  {
                    title: '目标班组',
                    dataIndex: 'target_cost_center_id',
                    width: 160,
                    render: (id: string) => {
                      const cc = ccById.get(id)
                      return cc ? <Text code>{cc.code}</Text> : <Text type="secondary">{id}</Text>
                    },
                  },
                  {
                    title: '分摊基础',
                    dataIndex: 'allocation_basis',
                    width: 110,
                    render: (v: string) => <Tag color="cyan">{v}</Tag>,
                  },
                  {
                    title: '权重',
                    dataIndex: 'allocation_weight',
                    width: 90,
                    align: 'right' as const,
                    render: (v: number) => `${(v * 100).toFixed(2)}%`,
                  },
                  {
                    title: '分摊金额',
                    dataIndex: 'amount_allocated',
                    width: 100,
                    align: 'right' as const,
                    render: (v: number) =>
                      <Text strong style={{ fontFamily: 'monospace' }}>
                        {v.toFixed(2)}
                      </Text>,
                  },
                  {
                    title: 'fallback 链',
                    dataIndex: 'fallback_chain',
                    width: 220,
                    render: (chain: string[]) =>
                      !chain?.length ? <Text type="secondary">—</Text> : (
                        <Space size={2} wrap>
                          {chain.map((c, i) => (
                            <Tag key={i} color={c.startsWith('used:') ? 'green' : 'default'}>
                              {c}
                            </Tag>
                          ))}
                        </Space>
                      ),
                  },
                  {
                    title: '警告',
                    dataIndex: 'warnings',
                    render: (ws: string[]) =>
                      !ws?.length ? <Text type="secondary">—</Text> : (
                        <Space wrap size={2}>
                          {ws.map((w, i) => <Tag key={i} color="orange">{w}</Tag>)}
                        </Space>
                      ),
                  },
                ]}
              />
            </Card>
          </>
        )}
      </Spin>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function AlgorithmLogTab() {
  const [period, setPeriod] = useState<Dayjs>(() => dayjs().subtract(1, 'month'))
  const periodStr = periodKey(period)
  const queryClient = useQueryClient()

  const aggregator = useMutation({
    mutationFn: () => aggregatePayrollBatch(periodStr),
  })
  const amortizer = useMutation({
    mutationFn: () => runFixedCostAmortization(periodStr),
  })
  const allocator = useMutation({
    mutationFn: () => runCostAllocation(periodStr, 'permissive'),
  })

  const runAll = async () => {
    try {
      const a2 = await aggregator.mutateAsync()
      const a3 = await amortizer.mutateAsync()
      const a4 = await allocator.mutateAsync()
      message.success(
        `算月完成 (${periodStr})：A2 ${a2.cost_center_count} 班组 · A3 ${a3.lines_written} 摊销行 · A4 ${a4.lines_written} 分摊行`,
      )
      void queryClient.invalidateQueries({
        predicate: q => {
          const k = q.queryKey[0]
          return k === 'planner'
        },
      })
    } catch (err: any) {
      message.error(`算月失败：${err?.response?.data?.detail || err?.message}`)
    }
  }

  const isRunning =
    aggregator.isPending || amortizer.isPending || allocator.isPending

  return (
    <div>
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 12 }}
        message="🤖 自动算法日志"
        description={
          <Paragraph style={{ marginBottom: 0 }}>
            Path A 真数据通电流水线的只读审计页：每月跑一次{' '}
            <Text code>A2 班组工资聚合</Text> →{' '}
            <Text code>A3 固开摊销</Text> →{' '}
            <Text code>A4 班组分摊 + 上链 cost_rate_master.overhead_rate</Text>。
            修改 finance 数据后回到此页{'"一键重算"'}刷新；下游 Hub 4 层 resolve 链立即生效。
          </Paragraph>
        }
      />

      <Card size="small" style={{ marginBottom: 12 }}>
        <Space wrap>
          <Text strong>月份：</Text>
          <DatePicker
            picker="month"
            value={period}
            onChange={d => d && setPeriod(d)}
            format="YYYY-MM"
            allowClear={false}
          />
          <Button type="primary" onClick={runAll} loading={isRunning}>
            🔁 一键重算本月（A2+A3+A4）
          </Button>
          <Tooltip title="拉 finance payroll → 写 snapshot → 上链 labor_per_minute">
            <Button onClick={() => aggregator.mutate()} loading={aggregator.isPending} disabled={isRunning && !aggregator.isPending}>
              单跑 A2
            </Button>
          </Tooltip>
          <Tooltip title="拉 finance payment_requests → 写 amortization_line">
            <Button onClick={() => amortizer.mutate()} loading={amortizer.isPending} disabled={isRunning && !amortizer.isPending}>
              单跑 A3
            </Button>
          </Tooltip>
          <Tooltip title="A3 数据 + finance driver → 写 allocation_line → 上链 overhead_rate">
            <Button onClick={() => allocator.mutate()} loading={allocator.isPending} disabled={isRunning && !allocator.isPending}>
              单跑 A4
            </Button>
          </Tooltip>
        </Space>
      </Card>

      <Space direction="vertical" size={12} style={{ width: '100%' }}>
        <PayrollSnapshotsCard period={periodStr} />
        <AmortizationCard period={periodStr} />
        <AllocationCard period={periodStr} />
      </Space>
    </div>
  )
}
