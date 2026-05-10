/**
 * Finance C1 主数据只读展示页(v1.3 终态)。
 *
 * - 6 Tabs:
 *   1) 公司主体(v1.3 加 4 recognition Boolean + floor_area_sqm)
 *   2) 店铺
 *   3) 店铺营收(v1.3 §4.2 新增 — 月度真实营业额)
 *   4) 员工
 *   5) 固定开支(v1.3 撤回 amortization 字段, 跨期摊销改走 §4.6 凭证)
 *   6) 付款凭证(v1.3 §4.6 新增 — amort + 6 类 + pay_company)
 *
 * - 顶部"数据来源"Badge: 🟢 finance-analyzer / 🟡 cache (Xm ago) / 🔵 mock (dev) / 🔴 error
 * - 数据从 `/api/planner/finance/*` 代理拉(后端 client 自带 5 分钟 TTL + 失败降级)
 *
 * scope 内只展示, 不写; 任何 finance 主数据修改都在 finance-analyzer 侧操作。
 *
 * 路由: `/costing/admin/finance-master`(由 App.tsx 注册)
 */

import {
  Alert,
  Card,
  Empty,
  Form,
  InputNumber,
  Space,
  Spin,
  Table,
  Tabs,
  Tag,
  Tooltip,
  Typography,
  Button,
} from 'antd'
import { useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'

import {
  fetchFinanceCompanies,
  fetchFinanceEmployees,
  fetchFinanceFixedCosts,
  fetchFinancePaymentRequests,
  fetchFinanceStores,
  fetchFinanceStoresRevenue,
} from '../../../services/financeC1'
import type {
  FinanceC1DataQuality,
  FinanceC1DataSource,
  FinanceC1ListEnvelope,
  FinanceC1MatchStatus,
  FinanceExpenseCategory,
} from '../../../types/financeC1'
import { formatBeijingTime } from '../../../utils/beijingTime'

const { Title, Text, Paragraph } = Typography

// ---------------------------------------------------------------------------
// Badge — 数据来源(派单 §3.4 + F2)
// ---------------------------------------------------------------------------

const DATA_SOURCE_TAG: Record<
  FinanceC1DataSource,
  { color: string; text: string; tip: string }
> = {
  live: {
    color: 'green',
    text: '🟢 finance-analyzer',
    tip: '实时拉取成功(或 5 分钟 TTL 内的命中,新鲜度可信)',
  },
  cache: {
    color: 'gold',
    text: '🟡 cache',
    tip: 'finance 暂时无法访问 · 自动降级到上次成功结果',
  },
  mock: {
    color: 'blue',
    text: '🔵 mock (dev)',
    tip: '开发环境 mock 数据(FINANCE_C1_USE_MOCK=true)·  非真实业务数据',
  },
}

const ERROR_TAG = {
  color: 'red',
  text: '🔴 error',
  tip: '连缓存都没有 · 检查 finance-analyzer 是否启动 + key 是否正确',
} as const

interface DataSourceBadgeProps {
  source: FinanceC1DataSource
  cacheAgeSeconds?: number | null
  fetchedAt?: string | null
  apiVersion?: string | null
  isError?: boolean
}

function DataSourceBadge({
  source,
  cacheAgeSeconds,
  fetchedAt,
  apiVersion,
  isError,
}: DataSourceBadgeProps) {
  if (isError) {
    return (
      <Tooltip title={ERROR_TAG.tip}>
        <Tag color={ERROR_TAG.color} style={{ fontSize: 13, padding: '2px 10px' }}>
          {ERROR_TAG.text}
        </Tag>
      </Tooltip>
    )
  }
  const cfg = DATA_SOURCE_TAG[source]
  const ageMin =
    cacheAgeSeconds && cacheAgeSeconds > 0 ? Math.round(cacheAgeSeconds / 60) : null

  // 1. cache 状态: 强制显示 "Xm ago"(派单要求 § F2)
  // 2. live 状态: 显示 fetched_at(刚拉了)
  // 3. mock 状态: 显示 "dev"
  const subtitle = (() => {
    if (source === 'cache' && ageMin !== null) {
      return `(${ageMin}m ago)`
    }
    if (source === 'live' && fetchedAt) {
      return ageMin && ageMin > 0 ? `(${ageMin}m ago)` : '(just now)'
    }
    return null
  })()

  const tip = (
    <Space direction="vertical" size={2}>
      <Text style={{ color: '#fff' }}>{cfg.tip}</Text>
      {fetchedAt && (
        <Text style={{ color: '#bfbfbf', fontSize: 12 }}>
          fetched_at: {formatBeijingTime(fetchedAt)}
        </Text>
      )}
      {apiVersion && (
        <Text style={{ color: '#bfbfbf', fontSize: 12 }}>api_version: {apiVersion}</Text>
      )}
    </Space>
  )

  return (
    <Tooltip title={tip}>
      <Tag color={cfg.color} style={{ fontSize: 13, padding: '2px 10px' }}>
        {cfg.text}
        {subtitle && <span style={{ marginLeft: 6, opacity: 0.8 }}>{subtitle}</span>}
      </Tag>
    </Tooltip>
  )
}

// ---------------------------------------------------------------------------
// 共享 helpers
// ---------------------------------------------------------------------------

const fmtMoney = (v: unknown): string => {
  const n = Number(v ?? 0)
  if (!Number.isFinite(n)) return '—'
  return `¥${n.toLocaleString(undefined, { maximumFractionDigits: 2 })}`
}

const RECOGNITION_LABEL: Record<string, string> = {
  revenue_recognition: '营收',
  material_purchase_recognition: '材料',
  payroll_recognition: '人工',
  fixed_cost_recognition: '固开',
}

// ---------------------------------------------------------------------------
// Tab 1 — 公司主体(v1.3 加 4 recognition + floor_area_sqm)
// ---------------------------------------------------------------------------

function CompaniesTab() {
  const query = useQuery({
    queryKey: ['planner', 'finance-c1', 'companies', 'v1.3'],
    queryFn: () => fetchFinanceCompanies({ is_active: true }),
    staleTime: 60_000,
  })

  const columns = useMemo(
    () => [
      {
        title: '主体名称',
        dataIndex: 'legal_name',
        key: 'legal_name',
        width: 280,
        render: (v: string) => <Text strong>{v}</Text>,
      },
      {
        title: '角色',
        dataIndex: 'entity_role',
        key: 'entity_role',
        width: 90,
        render: (v: string) => {
          const ROLE_TAG: Record<string, { color: string; text: string }> = {
            factory: { color: 'geekblue', text: '工厂' },
            shop: { color: 'green', text: '店铺' },
            holding: { color: 'purple', text: '控股' },
            mixed: { color: 'gold', text: '混合' },
          }
          const cfg = ROLE_TAG[v] ?? { color: 'default', text: v }
          return <Tag color={cfg.color}>{cfg.text}</Tag>
        },
      },
      {
        title: '业务画像 (v1.3)',
        key: 'recognition',
        width: 220,
        render: (_: unknown, row: Record<string, unknown>) => {
          const flags = Object.entries(RECOGNITION_LABEL).filter(
            ([k]) => row[k] === true,
          )
          if (flags.length === 0) {
            return <Text type="secondary">—</Text>
          }
          return (
            <Space size={4} wrap>
              {flags.map(([k, label]) => (
                <Tag key={k} color="cyan">
                  {label}
                </Tag>
              ))}
            </Space>
          )
        },
      },
      {
        title: '面积 (㎡)',
        dataIndex: 'floor_area_sqm',
        key: 'floor_area_sqm',
        width: 100,
        render: (v?: number | null) =>
          v != null ? (
            <Text style={{ fontFamily: 'monospace' }}>{Number(v).toFixed(2)}</Text>
          ) : (
            <Tooltip title="ops 暂未测量 · cost_allocator 自动 fallback 到 headcount/revenue 摊法">
              <Text type="secondary">—</Text>
            </Tooltip>
          ),
      },
      {
        title: '纳税类型',
        dataIndex: 'tax_payer_type',
        key: 'tax_payer_type',
        width: 100,
        render: (v: string) => <Tag>{v === 'general' ? '一般纳税人' : '小规模'}</Tag>,
      },
      {
        title: '统一社会信用代码',
        dataIndex: 'unified_social_credit_code',
        key: 'uscc',
        width: 200,
        render: (v?: string | null) =>
          v ? <Text style={{ fontFamily: 'monospace' }}>{v}</Text> : <Text type="secondary">—</Text>,
      },
      {
        title: '生效起',
        dataIndex: 'effective_from',
        key: 'effective_from',
        width: 120,
        render: (v?: string | null) => v ?? <Text type="secondary">—</Text>,
      },
      {
        title: '启用',
        dataIndex: 'is_active',
        key: 'is_active',
        width: 70,
        render: (v: boolean) => (v ? <Tag color="green">启用</Tag> : <Tag>停用</Tag>),
      },
      {
        title: 'subject_id',
        dataIndex: 'id',
        key: 'id',
        ellipsis: true,
        render: (v: string) => (
          <Text style={{ fontFamily: 'monospace', fontSize: 12, color: '#8c8c8c' }}>{v}</Text>
        ),
      },
    ],
    [],
  )

  return (
    <TabContent
      query={query}
      data={query.data?.data ?? []}
      columns={columns}
      rowKey="id"
      emptyText="finance 无公司主体数据"
    />
  )
}

// ---------------------------------------------------------------------------
// Tab 2 — 店铺
// ---------------------------------------------------------------------------

function StoresTab() {
  const query = useQuery({
    queryKey: ['planner', 'finance-c1', 'stores'],
    queryFn: () => fetchFinanceStores({ is_active: true }),
    staleTime: 60_000,
  })

  const columns = useMemo(
    () => [
      {
        title: '店铺名',
        dataIndex: 'store_name',
        key: 'store_name',
        width: 220,
        render: (v: string) => <Text strong>{v}</Text>,
      },
      {
        title: '平台',
        dataIndex: 'platform',
        key: 'platform',
        width: 110,
        render: (v?: string | null) => (v ? <Tag>{v}</Tag> : <Text type="secondary">—</Text>),
      },
      {
        title: '主营品类',
        dataIndex: 'main_category',
        key: 'main_category',
        width: 130,
        render: (v?: string | null) => v ?? <Text type="secondary">—</Text>,
      },
      {
        title: '店长',
        dataIndex: 'manager_name',
        key: 'manager_name',
        width: 100,
        render: (v?: string | null) => v ?? <Text type="secondary">—</Text>,
      },
      {
        title: '月均营业额 (v1.0 均值)',
        dataIndex: 'monthly_revenue_avg',
        key: 'monthly_revenue_avg',
        width: 160,
        render: (v?: number | null) =>
          v != null ? (
            <Text style={{ fontFamily: 'monospace' }}>{fmtMoney(v)}</Text>
          ) : (
            <Text type="secondary">—</Text>
          ),
      },
      {
        title: '所属主体',
        dataIndex: 'company_id',
        key: 'company_id',
        ellipsis: true,
        render: (v: string) => (
          <Text style={{ fontFamily: 'monospace', fontSize: 12, color: '#8c8c8c' }}>{v}</Text>
        ),
      },
    ],
    [],
  )

  return (
    <TabContent
      query={query}
      data={query.data?.data ?? []}
      columns={columns}
      rowKey="id"
      emptyText="finance 无店铺数据"
    />
  )
}

// ---------------------------------------------------------------------------
// Tab 3 — 店铺营收(v1.3 §4.2 新增)
// ---------------------------------------------------------------------------

const DATA_QUALITY_COLOR: Record<FinanceC1DataQuality, string> = {
  green: 'success',
  yellow: 'warning',
  red: 'error',
}

const DATA_QUALITY_LABEL: Record<FinanceC1DataQuality, string> = {
  green: '高',
  yellow: '中',
  red: '低',
}

function StoresRevenueTab() {
  const today = new Date()
  // 默认看上个月真实营收
  const lastMonth = new Date(today.getFullYear(), today.getMonth() - 1, 1)
  const [periodYear, setPeriodYear] = useState<number>(lastMonth.getFullYear())
  const [periodMonth, setPeriodMonth] = useState<number>(lastMonth.getMonth() + 1)

  const query = useQuery({
    queryKey: ['planner', 'finance-c1', 'stores-revenue', periodYear, periodMonth],
    queryFn: () =>
      fetchFinanceStoresRevenue({
        period_year: periodYear,
        period_month: periodMonth,
      }),
    staleTime: 60_000,
  })

  const data = query.data?.data ?? []
  const totalGross = data.reduce((acc, r) => acc + Number(r.gross_revenue || 0), 0)
  const totalNet = data.reduce((acc, r) => acc + Number(r.net_revenue || 0), 0)

  const columns = useMemo(
    () => [
      {
        title: '店铺',
        dataIndex: 'store_name',
        key: 'store_name',
        width: 200,
        render: (v: string) => <Text strong>{v}</Text>,
      },
      {
        title: '平台',
        dataIndex: 'platform',
        key: 'platform',
        width: 90,
        render: (v?: string | null) => (v ? <Tag>{v}</Tag> : <Text type="secondary">—</Text>),
      },
      {
        title: '毛收入',
        dataIndex: 'gross_revenue',
        key: 'gross_revenue',
        width: 130,
        render: (v?: number | null) => (
          <Text strong style={{ fontFamily: 'monospace' }}>{fmtMoney(v)}</Text>
        ),
      },
      {
        title: '净收入 (扣退款)',
        dataIndex: 'net_revenue',
        key: 'net_revenue',
        width: 140,
        render: (v?: number | null) => (
          <Text style={{ fontFamily: 'monospace' }}>{fmtMoney(v)}</Text>
        ),
      },
      {
        title: '平台扣款',
        dataIndex: 'platform_fee_paid',
        key: 'platform_fee_paid',
        width: 120,
        render: (v?: number | null) =>
          v != null ? (
            <Text style={{ fontFamily: 'monospace' }}>{fmtMoney(v)}</Text>
          ) : (
            <Text type="secondary">—</Text>
          ),
      },
      {
        title: '数据质量',
        dataIndex: 'data_quality',
        key: 'data_quality',
        width: 100,
        align: 'center' as const,
        render: (v?: FinanceC1DataQuality | null, row?: Record<string, unknown>) => {
          if (!v) return <Text type="secondary">—</Text>
          const tip = (
            <Space direction="vertical" size={2}>
              <Text style={{ color: '#fff' }}>来源: {String(row?.data_source ?? '—')}</Text>
              {row?.snapshot_at != null && (
                <Text style={{ color: '#bfbfbf', fontSize: 12 }}>
                  snapshot: {formatBeijingTime(String(row.snapshot_at))}
                </Text>
              )}
            </Space>
          )
          return (
            <Tooltip title={tip}>
              <Tag color={DATA_QUALITY_COLOR[v]}>{DATA_QUALITY_LABEL[v]}</Tag>
            </Tooltip>
          )
        },
      },
      {
        title: '所属主体',
        dataIndex: 'company_id',
        key: 'company_id',
        ellipsis: true,
        render: (v: string) => (
          <Text style={{ fontFamily: 'monospace', fontSize: 12, color: '#8c8c8c' }}>{v}</Text>
        ),
      },
    ],
    [],
  )

  return (
    <>
      <Card size="small" style={{ marginBottom: 12 }}>
        <Space size={16} wrap>
          <Form layout="inline">
            <Form.Item label="期间年">
              <InputNumber
                min={2020}
                max={2100}
                value={periodYear}
                onChange={(v) => v != null && setPeriodYear(Number(v))}
                style={{ width: 110 }}
              />
            </Form.Item>
            <Form.Item label="期间月">
              <InputNumber
                min={1}
                max={12}
                value={periodMonth}
                onChange={(v) => v != null && setPeriodMonth(Number(v))}
                style={{ width: 90 }}
              />
            </Form.Item>
            <Form.Item>
              <Button onClick={() => query.refetch()} loading={query.isFetching}>
                刷新
              </Button>
            </Form.Item>
          </Form>
          <Text type="secondary">
            毛收入合计: <Text strong>{fmtMoney(totalGross)}</Text> · 净收入合计:{' '}
            <Text strong>{fmtMoney(totalNet)}</Text> · 共 {data.length} 店铺
          </Text>
        </Space>
      </Card>

      <TabContent
        query={query}
        data={data}
        columns={columns}
        rowKey="store_id"
        emptyText={`${periodYear}-${String(periodMonth).padStart(2, '0')} 无店铺营收记录`}
      />
    </>
  )
}

// ---------------------------------------------------------------------------
// Tab 4 — 员工
// ---------------------------------------------------------------------------

function EmployeesTab() {
  const query = useQuery({
    queryKey: ['planner', 'finance-c1', 'employees'],
    queryFn: () => fetchFinanceEmployees({ is_active: true }),
    staleTime: 60_000,
  })

  const columns = useMemo(
    () => [
      { title: '工号', dataIndex: 'employee_no', key: 'employee_no', width: 110 },
      {
        title: '姓名',
        dataIndex: 'name',
        key: 'name',
        width: 110,
        render: (v: string) => <Text strong>{v}</Text>,
      },
      {
        title: '部门 (对应 cost_center)',
        dataIndex: 'department',
        key: 'department',
        width: 200,
        render: (v?: string | null) => (v ? <Tag color="cyan">{v}</Tag> : <Text type="secondary">—</Text>),
      },
      {
        title: '岗位',
        dataIndex: 'position',
        key: 'position',
        width: 120,
        render: (v?: string | null) => v ?? <Text type="secondary">—</Text>,
      },
      {
        title: '入职日期',
        dataIndex: 'hire_date',
        key: 'hire_date',
        width: 130,
        render: (v?: string | null) => v ?? <Text type="secondary">—</Text>,
      },
      {
        title: '在职',
        dataIndex: 'is_active',
        key: 'is_active',
        width: 80,
        render: (v: boolean) => (v ? <Tag color="green">在职</Tag> : <Tag>离职</Tag>),
      },
      {
        title: '工资发放主体',
        dataIndex: 'contract_company_id',
        key: 'contract_company_id',
        ellipsis: true,
        render: (v: string) => (
          <Text style={{ fontFamily: 'monospace', fontSize: 12, color: '#8c8c8c' }}>{v}</Text>
        ),
      },
    ],
    [],
  )

  return (
    <TabContent
      query={query}
      data={query.data?.data ?? []}
      columns={columns}
      rowKey="id"
      emptyText="finance 无员工数据"
    />
  )
}

// ---------------------------------------------------------------------------
// Tab 5 — 固定开支
// ---------------------------------------------------------------------------

const COST_CATEGORY_LABEL: Record<string, { color: string; label: string }> = {
  rent: { color: 'geekblue', label: '房租' },
  utility: { color: 'cyan', label: '水电' },
  salary_admin: { color: 'gold', label: '管理工资' },
  insurance_admin: { color: 'orange', label: '管理五险一金' },
  office_supplies: { color: 'lime', label: '办公耗材' },
  depreciation: { color: 'purple', label: '设备折旧' },
  logistics: { color: 'magenta', label: '厂出物流' },
  platform_fee: { color: 'red', label: '平台佣金' },
  after_sales: { color: 'volcano', label: '售后退换' },
  others: { color: 'default', label: '其他' },
}

function FixedCostsTab() {
  const today = new Date()
  // 默认看上个月数据(本月很少有完整入账)
  const lastMonth = new Date(today.getFullYear(), today.getMonth() - 1, 1)
  const [periodYear, setPeriodYear] = useState<number>(lastMonth.getFullYear())
  const [periodMonth, setPeriodMonth] = useState<number>(lastMonth.getMonth() + 1)

  const query = useQuery({
    queryKey: ['planner', 'finance-c1', 'fixed-costs', periodYear, periodMonth],
    queryFn: () =>
      fetchFinanceFixedCosts({
        period_year: periodYear,
        period_month: periodMonth,
      }),
    staleTime: 60_000,
  })

  const data = query.data?.data ?? []

  // 按 category 聚合 — 派单契约 §4.2 C3 测试这里也展示。
  const totalsByCategory = useMemo(() => {
    const acc: Record<string, number> = {}
    for (const row of data) {
      acc[row.cost_category] = (acc[row.cost_category] ?? 0) + Number(row.amount || 0)
    }
    return acc
  }, [data])

  const grandTotal = Object.values(totalsByCategory).reduce((a, b) => a + b, 0)

  const columns = useMemo(
    () => [
      {
        title: '费用类别',
        dataIndex: 'cost_category',
        key: 'cost_category',
        width: 140,
        render: (v: string) => {
          const cfg = COST_CATEGORY_LABEL[v] ?? { color: 'default', label: v }
          return <Tag color={cfg.color}>{cfg.label}</Tag>
        },
      },
      {
        title: '子类',
        dataIndex: 'cost_subcategory',
        key: 'cost_subcategory',
        width: 160,
        render: (v?: string | null) => v ?? <Text type="secondary">—</Text>,
      },
      {
        title: '金额',
        dataIndex: 'amount',
        key: 'amount',
        width: 140,
        render: (v: number) => (
          <Text strong style={{ fontFamily: 'monospace' }}>
            {fmtMoney(v)}
          </Text>
        ),
      },
      {
        title: '含税',
        dataIndex: 'tax_included',
        key: 'tax_included',
        width: 80,
        render: (v: boolean) => (v ? <Tag color="green">含税</Tag> : <Tag>不含税</Tag>),
      },
      {
        title: '税率',
        dataIndex: 'tax_rate',
        key: 'tax_rate',
        width: 80,
        render: (v?: number | null) =>
          v != null ? `${(v * 100).toFixed(1)}%` : <Text type="secondary">—</Text>,
      },
      {
        title: '说明',
        dataIndex: 'description',
        key: 'description',
        ellipsis: true,
        render: (v?: string | null) => v ?? <Text type="secondary">—</Text>,
      },
      {
        title: '审批人',
        dataIndex: 'approver',
        key: 'approver',
        width: 100,
        render: (v?: string | null) => v ?? <Text type="secondary">—</Text>,
      },
      {
        title: '付款主体',
        dataIndex: 'company_id',
        key: 'company_id',
        ellipsis: true,
        render: (v: string) => (
          <Text style={{ fontFamily: 'monospace', fontSize: 12, color: '#8c8c8c' }}>{v}</Text>
        ),
      },
    ],
    [],
  )

  return (
    <>
      <Card size="small" style={{ marginBottom: 12 }}>
        <Space size={16}>
          <Form layout="inline">
            <Form.Item label="期间年">
              <InputNumber
                min={2020}
                max={2100}
                value={periodYear}
                onChange={(v) => v != null && setPeriodYear(Number(v))}
                style={{ width: 110 }}
              />
            </Form.Item>
            <Form.Item label="期间月">
              <InputNumber
                min={1}
                max={12}
                value={periodMonth}
                onChange={(v) => v != null && setPeriodMonth(Number(v))}
                style={{ width: 90 }}
              />
            </Form.Item>
            <Form.Item>
              <Button onClick={() => query.refetch()} loading={query.isFetching}>
                刷新
              </Button>
            </Form.Item>
          </Form>
          <Text type="secondary">
            合计: <Text strong>{fmtMoney(grandTotal)}</Text> · 共{' '}
            {Object.keys(totalsByCategory).length} 种费用类别
          </Text>
        </Space>
      </Card>

      <TabContent
        query={query}
        data={data}
        columns={columns}
        rowKey="id"
        emptyText={`${periodYear}-${String(periodMonth).padStart(2, '0')} 无固定开支记录`}
      />
    </>
  )
}

// ---------------------------------------------------------------------------
// Tab 6 — 付款凭证(v1.3 §4.6 新增)
// ---------------------------------------------------------------------------

const EXPENSE_CATEGORY_LABEL: Record<FinanceExpenseCategory, { color: string; label: string }> = {
  cogs: { color: 'red', label: '主营成本' },
  selling: { color: 'orange', label: '销售费用' },
  admin: { color: 'geekblue', label: '管理费用' },
  financial: { color: 'purple', label: '财务费用' },
  capital_recovery: { color: 'magenta', label: '资本回收' },
  platform_recharge: { color: 'lime', label: '平台充值' },
}

const MATCH_STATUS_LABEL: Record<FinanceC1MatchStatus, { color: string; label: string }> = {
  full: { color: 'success', label: '全额匹配' },
  partial: { color: 'warning', label: '部分匹配' },
  none: { color: 'default', label: '未匹配' },
  unmatched: { color: 'error', label: '失配' },
}

function PaymentRequestsTab() {
  const today = new Date()
  const lastMonth = new Date(today.getFullYear(), today.getMonth() - 1, 1)
  // 默认按 belong_month 过滤上个月; 用户可清空看全量
  const defaultPeriod = `${lastMonth.getFullYear()}${String(lastMonth.getMonth() + 1).padStart(2, '0')}`
  const [period, setPeriod] = useState<string | undefined>(undefined)

  const query = useQuery({
    queryKey: ['planner', 'finance-c1', 'payment-requests', period ?? 'all'],
    queryFn: () =>
      fetchFinancePaymentRequests(period ? { period } : {}),
    staleTime: 60_000,
  })

  const data = query.data?.data ?? []
  const totalAmount = data.reduce((acc, r) => acc + Number(r.amount || 0), 0)
  const amortizedCount = data.filter((r) => r.is_monthly_amortized).length

  const columns = useMemo(
    () => [
      {
        title: '付款日期',
        dataIndex: 'payment_date',
        key: 'payment_date',
        width: 120,
      },
      {
        title: '归属月',
        dataIndex: 'belong_month',
        key: 'belong_month',
        width: 100,
        render: (v: string) => <Tag>{v}</Tag>,
      },
      {
        title: '金额',
        dataIndex: 'amount',
        key: 'amount',
        width: 130,
        render: (v: number) => (
          <Text strong style={{ fontFamily: 'monospace' }}>
            {fmtMoney(v)}
          </Text>
        ),
      },
      {
        title: '受益主体',
        dataIndex: 'company_name',
        key: 'company_name',
        width: 240,
        render: (v: string) => <Text>{v}</Text>,
      },
      {
        title: '付款主体 (pay_company)',
        dataIndex: 'pay_company',
        key: 'pay_company',
        width: 220,
        render: (v: string | null | undefined, row: { company_name: string }) => {
          if (!v) return <Text type="secondary">—</Text>
          if (v !== row.company_name) {
            return (
              <Tooltip title="A 主体付钱、B 主体受益场景">
                <Tag color="orange">{v}</Tag>
              </Tooltip>
            )
          }
          return <Text type="secondary">{v}</Text>
        },
      },
      {
        title: '管理会计分类',
        dataIndex: 'expense_category',
        key: 'expense_category',
        width: 130,
        render: (v: FinanceExpenseCategory) => {
          const cfg = EXPENSE_CATEGORY_LABEL[v] ?? { color: 'default', label: v }
          return <Tag color={cfg.color}>{cfg.label}</Tag>
        },
      },
      {
        title: '摊销月数',
        key: 'amort_months',
        width: 110,
        render: (_: unknown, row: Record<string, unknown>) => {
          if (!row.is_monthly_amortized) {
            return <Text type="secondary">—</Text>
          }
          const months = Number(row.amort_months ?? 0)
          const monthly = Number(row.amort_monthly_amount ?? 0)
          const tip = (
            <div style={{ lineHeight: 1.6 }}>
              <div>
                <b>区间</b>: {String(row.amort_start_period ?? '—')} ~{' '}
                {String(row.amort_end_period ?? '—')}
              </div>
              <div>
                <b>月摊</b>: {fmtMoney(monthly)}
              </div>
            </div>
          )
          return (
            <Tooltip title={tip}>
              <Tag color="purple">{months} 月</Tag>
            </Tooltip>
          )
        },
      },
      {
        title: '匹配状态',
        dataIndex: 'match_status',
        key: 'match_status',
        width: 110,
        align: 'center' as const,
        render: (v?: FinanceC1MatchStatus | null, row?: Record<string, unknown>) => {
          if (!v) return <Text type="secondary">—</Text>
          const cfg = MATCH_STATUS_LABEL[v] ?? { color: 'default', label: v }
          const tip = (
            <Space direction="vertical" size={2}>
              <Text style={{ color: '#fff' }}>已匹配: {fmtMoney(row?.matched_amount)}</Text>
              {row?.invoice_status != null && (
                <Text style={{ color: '#bfbfbf', fontSize: 12 }}>
                  发票: {String(row.invoice_status)}
                </Text>
              )}
              {row?.invoice_gap != null && Number(row.invoice_gap) > 0 && (
                <Text style={{ color: '#bfbfbf', fontSize: 12 }}>
                  发票差额: {fmtMoney(row.invoice_gap)}
                </Text>
              )}
            </Space>
          )
          return (
            <Tooltip title={tip}>
              <Tag color={cfg.color}>{cfg.label}</Tag>
            </Tooltip>
          )
        },
      },
      {
        title: '事由',
        dataIndex: 'reason',
        key: 'reason',
        ellipsis: true,
        render: (v?: string | null) => v ?? <Text type="secondary">—</Text>,
      },
    ],
    [],
  )

  return (
    <>
      <Card size="small" style={{ marginBottom: 12 }}>
        <Space size={16} wrap>
          <Form layout="inline">
            <Form.Item label="归属月 (YYYYMM)">
              <Space>
                <input
                  type="text"
                  placeholder="如 202604, 留空看全量"
                  value={period ?? ''}
                  onChange={(e) => {
                    const v = e.target.value.trim()
                    setPeriod(v === '' ? undefined : v)
                  }}
                  style={{
                    padding: '4px 11px',
                    border: '1px solid #d9d9d9',
                    borderRadius: 6,
                    width: 180,
                  }}
                />
                <Button size="small" onClick={() => setPeriod(defaultPeriod)}>
                  上月
                </Button>
                <Button size="small" onClick={() => setPeriod(undefined)}>
                  全量
                </Button>
              </Space>
            </Form.Item>
            <Form.Item>
              <Button onClick={() => query.refetch()} loading={query.isFetching}>
                刷新
              </Button>
            </Form.Item>
          </Form>
          <Text type="secondary">
            合计: <Text strong>{fmtMoney(totalAmount)}</Text> · 含{' '}
            <Text strong>{amortizedCount}</Text> 条跨期摊销 / 共 {data.length} 条
          </Text>
        </Space>
      </Card>

      <TabContent
        query={query}
        data={data}
        columns={columns}
        rowKey="id"
        emptyText={period ? `${period} 无付款凭证记录` : '暂无付款凭证'}
      />
    </>
  )
}

// ---------------------------------------------------------------------------
// 公共: TabContent — Loading / Error / Empty / 数据来源 Badge
// ---------------------------------------------------------------------------

interface TabContentProps<T> {
  query: {
    isLoading: boolean
    isError: boolean
    error: unknown
    data: FinanceC1ListEnvelope<T> | undefined
  }
  data: T[]
  columns: any[]
  rowKey: string
  emptyText?: string
}

function TabContent<T extends Record<string, any>>({
  query,
  data,
  columns,
  rowKey,
  emptyText,
}: TabContentProps<T>) {
  if (query.isLoading) {
    return (
      <Card>
        <div style={{ textAlign: 'center', padding: '48px 0' }}>
          <Spin tip="拉取 finance C1 数据 ..." />
        </div>
      </Card>
    )
  }
  if (query.isError) {
    const errMsg =
      (query.error as any)?.response?.data?.detail?.message ||
      (query.error as any)?.message ||
      '未知错误'
    return (
      <Alert
        type="error"
        showIcon
        message="finance-analyzer 不可达"
        description={
          <Space direction="vertical" size={4}>
            <Text>{errMsg}</Text>
            <Text type="secondary">
              请确认 finance-analyzer 已启动 + `FINANCE_C1_API_KEY` 配置正确;开发环境可设
              `FINANCE_C1_USE_MOCK=true` 用 mock 数据。
            </Text>
          </Space>
        }
      />
    )
  }

  return (
    <>
      <BadgeBar envelope={query.data} />
      <Table
        rowKey={rowKey}
        dataSource={data}
        columns={columns as any}
        pagination={{ pageSize: 50, showSizeChanger: true }}
        size="middle"
        scroll={{ x: 'max-content' }}
        locale={{
          emptyText: <Empty description={emptyText ?? '暂无数据'} />,
        }}
      />
    </>
  )
}

interface BadgeBarProps {
  envelope: FinanceC1ListEnvelope<any> | undefined
}

function BadgeBar({ envelope }: BadgeBarProps) {
  if (!envelope) return null
  const lastUpdatedAt = envelope.pagination?.last_updated_at
  return (
    <div style={{ marginBottom: 8, display: 'flex', alignItems: 'center', gap: 8 }}>
      <Text type="secondary" style={{ fontSize: 12 }}>
        数据来源:
      </Text>
      <DataSourceBadge
        source={envelope.data_source}
        cacheAgeSeconds={envelope.cache_age_seconds}
        fetchedAt={envelope.fetched_at}
        apiVersion={envelope.api_version}
      />
      {envelope.pagination && (
        <Text type="secondary" style={{ fontSize: 12 }}>
          · 共 {envelope.pagination.total} 条
          {envelope.pagination.total_pages != null && (
            <> (page {envelope.pagination.page}/{envelope.pagination.total_pages})</>
          )}
          {lastUpdatedAt && (
            <> · last_updated_at: {formatBeijingTime(lastUpdatedAt)}</>
          )}
        </Text>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page wrapper
// ---------------------------------------------------------------------------

export default function FinanceMasterDataPage() {
  return (
    <div style={{ padding: 16 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between' }}>
        <div>
          <Title level={3} style={{ marginBottom: 4 }}>
            🏢 Finance 主数据 (只读)
          </Title>
          <Paragraph type="secondary" style={{ marginBottom: 0 }}>
            来自 finance-analyzer 的 C1 契约 v1.3 终态(
            <Text code>finance_to_costing_c1_contract_v1.3_aligned.md</Text>)·
            6 类只读数据(含 v1.3 新增「店铺营收」+「付款凭证」)·  5 分钟 TTL 缓存 +
            finance 挂时降级 ·  数据维护在 finance-analyzer · 此页仅展示。
          </Paragraph>
        </div>
        <Space>
          <Tag color="green">C1 v1.3</Tag>
        </Space>
      </div>

      <Tabs
        defaultActiveKey="companies"
        style={{ marginTop: 12 }}
        items={[
          { key: 'companies', label: '公司主体', children: <CompaniesTab /> },
          { key: 'stores', label: '店铺', children: <StoresTab /> },
          {
            key: 'stores-revenue',
            label: '店铺营收 (v1.3)',
            children: <StoresRevenueTab />,
          },
          { key: 'employees', label: '员工', children: <EmployeesTab /> },
          { key: 'fixed-costs', label: '固定开支', children: <FixedCostsTab /> },
          {
            key: 'payment-requests',
            label: '付款凭证 (v1.3)',
            children: <PaymentRequestsTab />,
          },
        ]}
      />
    </div>
  )
}
