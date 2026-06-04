/**
 * Cost center master page (Path A §A1).
 *
 * - Lists 6 cost_centers with stats: process_count + employee_count
 *   (the latter pulled live via finance employees + finance_department_mapping)
 * - CRUD via drawer form
 * - "Refresh finance dept mapping" button — pulls finance employees
 *   distinct departments and appends them to each cost_center's mapping
 * - Per-row action: trigger A2 aggregator (POST /aggregate-payroll?period=…)
 *   then jump to Hub for review; per-period batch button at the top.
 *
 * Scope: 系统运维 → "💼 班组（cost_center）"
 * 路由: `/costing/admin/cost-centers` (App.tsx 注册 + AppLayout 菜单加项)
 */

import {
  Alert,
  Button,
  Card,
  DatePicker,
  Drawer,
  Empty,
  Form,
  Input,
  message,
  Modal,
  Popconfirm,
  Select,
  Space,
  Spin,
  Statistic,
  Table,
  Tag,
  Tooltip,
  Typography,
  Switch,
} from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import dayjs, { Dayjs } from 'dayjs'

import {
  aggregatePayrollBatch,
  createCostCenter,
  deleteCostCenter,
  fetchCostCenters,
  patchCostCenter,
  refreshFinanceDepartmentMapping,
  runCostAllocation,
  runFixedCostAmortization,
} from '../../../services/costCenter'
import type {
  CostCenter,
  CostCenterAllocationBasis,
  CostCenterType,
  CostCenterUpsertPayload,
} from '../../../types/planner'

const { Title, Text, Paragraph } = Typography

const COST_CENTER_QUERY = ['planner', 'costCenters'] as const

const TYPE_TAG: Record<CostCenterType, { color: string; label: string }> = {
  production: { color: 'blue', label: '生产' },
  auxiliary: { color: 'cyan', label: '辅助' },
  admin: { color: 'gold', label: '管理' },
}

const BASIS_LABEL: Record<CostCenterAllocationBasis | 'unset', string> = {
  headcount: '按人头',
  team_hours: '按工时',
  revenue: '按营业额',
  floor_area: '按面积',
  fixed_pct: '按固定比例',
  unset: '未设置',
}

const TYPE_OPTIONS: { value: CostCenterType; label: string }[] = [
  { value: 'production', label: '生产 production' },
  { value: 'auxiliary', label: '辅助 auxiliary' },
  { value: 'admin', label: '管理 admin' },
]

const BASIS_OPTIONS: { value: CostCenterAllocationBasis; label: string }[] = [
  { value: 'headcount', label: '按人头 headcount' },
  { value: 'team_hours', label: '按工时 team_hours' },
  { value: 'revenue', label: '按营业额 revenue' },
  { value: 'floor_area', label: '按面积 floor_area' },
  { value: 'fixed_pct', label: '按固定比例 fixed_pct' },
]

interface EditFormValues {
  code: string
  name: string
  type: CostCenterType
  description?: string
  default_allocation_basis?: CostCenterAllocationBasis
  legacy_team_names?: string
  finance_department_mapping?: string
  is_active: boolean
}

function splitCsv(s: string | undefined | null): string[] {
  if (!s) return []
  return s
    .split(/[,，;；\n]/)
    .map(x => x.trim())
    .filter(Boolean)
}

function joinCsv(arr: string[] | undefined | null): string {
  return (arr || []).join(', ')
}

// ---------------------------------------------------------------------------
// Edit drawer
// ---------------------------------------------------------------------------

function CostCenterEditDrawer(props: {
  open: boolean
  onClose: () => void
  initial?: CostCenter | null
}) {
  const { open, onClose, initial } = props
  const [form] = Form.useForm<EditFormValues>()
  const queryClient = useQueryClient()

  const isEdit = Boolean(initial?.id)

  const initialValues: EditFormValues = useMemo(() => {
    const meta = (initial?.metadata as Record<string, unknown> | undefined) || {}
    return {
      code: initial?.code ?? '',
      name: initial?.name ?? '',
      type: (initial?.type as CostCenterType) ?? 'production',
      description: initial?.description ?? '',
      default_allocation_basis:
        (initial?.default_allocation_basis as CostCenterAllocationBasis) ?? 'team_hours',
      legacy_team_names: joinCsv(initial?.legacy_team_names ?? []),
      finance_department_mapping: joinCsv(
        (meta.finance_department_mapping as string[] | undefined) ?? [],
      ),
      is_active: initial?.is_active ?? true,
    }
  }, [initial])

  const submit = useMutation({
    mutationFn: async (values: EditFormValues) => {
      const meta = (initial?.metadata as Record<string, unknown> | undefined) || {}
      const payload: CostCenterUpsertPayload = {
        name: values.name.trim(),
        type: values.type,
        description: values.description?.trim() || null,
        default_allocation_basis: values.default_allocation_basis,
        legacy_team_names: splitCsv(values.legacy_team_names),
        is_active: values.is_active,
        metadata: {
          ...meta,
          finance_department_mapping: splitCsv(values.finance_department_mapping),
        },
      }
      if (isEdit && initial) {
        return patchCostCenter(initial.id, payload)
      }
      return createCostCenter({ ...payload, code: values.code.trim().toUpperCase() })
    },
    onSuccess: () => {
      message.success(isEdit ? '已保存' : '已创建')
      void queryClient.invalidateQueries({ queryKey: COST_CENTER_QUERY })
      onClose()
    },
    onError: (err: any) => {
      message.error(`保存失败：${err?.response?.data?.detail || err?.message || err}`)
    },
  })

  return (
    <Drawer
      title={isEdit ? `编辑 班组：${initial?.name}` : '新建 班组'}
      width={520}
      open={open}
      onClose={onClose}
      destroyOnClose
      extra={
        <Space>
          <Button onClick={onClose}>取消</Button>
          <Button
            type="primary"
            onClick={async () => {
              const values = await form.validateFields()
              submit.mutate(values)
            }}
            loading={submit.isPending}
          >
            保存
          </Button>
        </Space>
      }
    >
      <Form
        form={form}
        layout="vertical"
        initialValues={initialValues}
        preserve={false}
      >
        <Form.Item
          name="code"
          label="代码（不可改）"
          rules={[{ required: !isEdit, message: '请输入代码' }]}
          tooltip="如 CC_DECOR_PROD；建议大写下划线分隔；创建后不可修改"
        >
          <Input
            placeholder="CC_..."
            maxLength={64}
            disabled={isEdit}
            style={{ textTransform: 'uppercase' }}
          />
        </Form.Item>
        <Form.Item
          name="name"
          label="名称"
          rules={[{ required: true, message: '请输入名称' }]}
        >
          <Input placeholder="例如：家居饰品生产组" maxLength={128} />
        </Form.Item>
        <Form.Item name="type" label="类型" rules={[{ required: true }]}>
          <Select options={TYPE_OPTIONS} />
        </Form.Item>
        <Form.Item name="default_allocation_basis" label="默认分摊基础">
          <Select options={BASIS_OPTIONS} allowClear />
        </Form.Item>
        <Form.Item
          name="legacy_team_names"
          label="老 team_name 列表"
          tooltip="逗号分隔；记录这个班组吸收过哪些老 team_name 字符串（审计用）"
        >
          <Input.TextArea rows={2} placeholder="缝纫一组, 缝纫二组, 缝纫三组" />
        </Form.Item>
        <Form.Item
          name="finance_department_mapping"
          label="finance 部门映射"
          tooltip="逗号分隔；A2 aggregator 用此匹配 finance employees.department"
        >
          <Input.TextArea
            rows={2}
            placeholder={`缝纫一组, 缝纫二组（点击页面顶部"刷新 finance 映射"可自动追加）`}
          />
        </Form.Item>
        <Form.Item name="description" label="描述">
          <Input.TextArea rows={2} maxLength={500} />
        </Form.Item>
        <Form.Item name="is_active" label="启用" valuePropName="checked">
          <Switch />
        </Form.Item>
      </Form>
    </Drawer>
  )
}

// ---------------------------------------------------------------------------
// Run-batch toolbar
// ---------------------------------------------------------------------------

function RunBatchToolbar() {
  const [period, setPeriod] = useState<Dayjs>(() => dayjs().subtract(1, 'month'))
  const queryClient = useQueryClient()

  const aggregator = useMutation({
    mutationFn: async () => aggregatePayrollBatch(period.format('YYYY-MM')),
    onSuccess: result => {
      message.success(
        `A2 跑完：${result.cost_center_count} 个班组 / ${result.snapshots.length} 个 snapshot / 写入 ${result.upserted_rate_rows} 条 cost_rate_master`,
      )
      void queryClient.invalidateQueries({ queryKey: COST_CENTER_QUERY })
    },
    onError: (err: any) =>
      message.error(`A2 失败：${err?.response?.data?.detail || err?.message}`),
  })

  const amortizer = useMutation({
    mutationFn: async () => runFixedCostAmortization(period.format('YYYY-MM')),
    onSuccess: result => {
      message.success(
        `A3 跑完：写入 ${result.lines_written} 行摊销 / 总额 ¥${result.total_amount.toFixed(2)}`,
      )
    },
    onError: (err: any) =>
      message.error(`A3 失败：${err?.response?.data?.detail || err?.message}`),
  })

  const allocator = useMutation({
    mutationFn: async () => runCostAllocation(period.format('YYYY-MM'), 'permissive'),
    onSuccess: result => {
      message.success(
        `A4 跑完：写入 ${result.lines_written} 行分摊 / ${result.cost_centers_touched} 个班组受影响 / 上链 ${result.upserted_rate_rows} 条 cost_rate_master`,
      )
      void queryClient.invalidateQueries({ queryKey: COST_CENTER_QUERY })
    },
    onError: (err: any) =>
      message.error(`A4 失败：${err?.response?.data?.detail || err?.message}`),
  })

  const runAll = async () => {
    await aggregator.mutateAsync()
    await amortizer.mutateAsync()
    await allocator.mutateAsync()
  }

  const isRunning =
    aggregator.isPending || amortizer.isPending || allocator.isPending

  return (
    <Space wrap>
      <Text strong>批量重算月份：</Text>
      <DatePicker
        picker="month"
        value={period}
        onChange={d => d && setPeriod(d)}
        format="YYYY-MM"
        allowClear={false}
      />
      <Tooltip title="A2 班组工资聚合：拉 finance payroll → cost_center_payroll_snapshot → 上链 labor_per_minute">
        <Button
          onClick={() => aggregator.mutate()}
          loading={aggregator.isPending}
          disabled={isRunning && !aggregator.isPending}
        >
          A2 班组工资
        </Button>
      </Tooltip>
      <Tooltip title="A3 固开摊销：拉 finance payment_requests → fixed_cost_amortization_line">
        <Button
          onClick={() => amortizer.mutate()}
          loading={amortizer.isPending}
          disabled={isRunning && !amortizer.isPending}
        >
          A3 固开摊销
        </Button>
      </Tooltip>
      <Tooltip title="A4 班组分摊：A3 数据 + finance 真 driver → cost_allocation_line → 上链 overhead_rate">
        <Button
          onClick={() => allocator.mutate()}
          loading={allocator.isPending}
          disabled={isRunning && !allocator.isPending}
        >
          A4 班组分摊
        </Button>
      </Tooltip>
      <Tooltip title="顺序执行 A2 → A3 → A4">
        <Button type="primary" onClick={runAll} loading={isRunning}>
          🔁 一键重算本月（A2+A3+A4）
        </Button>
      </Tooltip>
    </Space>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function CostCenterMasterPage() {
  const queryClient = useQueryClient()
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [editing, setEditing] = useState<CostCenter | null>(null)
  const [showInactive, setShowInactive] = useState(false)

  const list = useQuery({
    queryKey: [...COST_CENTER_QUERY, { showInactive }],
    queryFn: () => fetchCostCenters({ include_inactive: showInactive, with_stats: true }),
  })

  const refreshMapping = useMutation({
    mutationFn: async () => refreshFinanceDepartmentMapping(),
    onSuccess: result => {
      Modal.info({
        title: '刷新 finance department 映射',
        width: 600,
        content: (
          <div>
            <Paragraph>
              共看到 <Text strong>{result.departments_seen.length}</Text> 个 finance
              部门字符串；更新了 <Text strong>{result.cost_centers_updated}</Text> 个
              cost_center；finance 数据来源：<Tag>{result.finance_data_source}</Tag>
            </Paragraph>
            {result.unmatched_departments.length > 0 ? (
              <>
                <Paragraph type="warning" style={{ marginBottom: 4 }}>
                  以下 {result.unmatched_departments.length} 个部门没匹配到任何
                  cost_center（请编辑对应班组的"finance 部门映射"字段添加）：
                </Paragraph>
                <Paragraph code>{result.unmatched_departments.join('，')}</Paragraph>
              </>
            ) : (
              <Paragraph type="success">所有 finance 部门都成功匹配到 cost_center。</Paragraph>
            )}
            {result.warnings.length > 0 && (
              <Alert
                type="warning"
                showIcon
                message="警告"
                description={
                  <ul style={{ marginBottom: 0 }}>
                    {result.warnings.map((w, i) => (
                      <li key={i}>{w}</li>
                    ))}
                  </ul>
                }
              />
            )}
          </div>
        ),
      })
      void queryClient.invalidateQueries({ queryKey: COST_CENTER_QUERY })
    },
    onError: (err: any) =>
      message.error(`刷新失败：${err?.response?.data?.detail || err?.message}`),
  })

  const remove = useMutation({
    mutationFn: async (id: string) => deleteCostCenter(id, 'ui'),
    onSuccess: () => {
      message.success('已停用')
      void queryClient.invalidateQueries({ queryKey: COST_CENTER_QUERY })
    },
  })

  const items = list.data?.items ?? []

  const columns = [
    {
      title: '代码',
      dataIndex: 'code',
      width: 160,
      render: (code: string) => <Text code>{code}</Text>,
    },
    {
      title: '名称',
      dataIndex: 'name',
      width: 160,
    },
    {
      title: '类型',
      dataIndex: 'type',
      width: 90,
      render: (t: CostCenterType) => {
        const cfg = TYPE_TAG[t] || { color: 'default', label: t }
        return <Tag color={cfg.color}>{cfg.label}</Tag>
      },
    },
    {
      title: '员工数',
      dataIndex: ['stats', 'employee_count'],
      width: 90,
      render: (n: number, row: CostCenter) => (
        <Tooltip
          title={`finance 数据：${row.stats.finance_data_source}${
            row.stats.finance_warnings.length
              ? '；警告：' + row.stats.finance_warnings.join('；')
              : ''
          }`}
        >
          <Tag color={n > 0 ? 'blue' : 'default'}>{n}</Tag>
        </Tooltip>
      ),
    },
    {
      title: '工序数',
      dataIndex: ['stats', 'process_count'],
      width: 90,
      render: (n: number) => <Tag color={n > 0 ? 'green' : 'default'}>{n}</Tag>,
    },
    {
      title: '默认分摊基础',
      dataIndex: 'default_allocation_basis',
      width: 130,
      render: (b: CostCenterAllocationBasis | null) => (
        <Text type="secondary">{BASIS_LABEL[(b as CostCenterAllocationBasis) || 'unset']}</Text>
      ),
    },
    {
      title: '启用',
      dataIndex: 'is_active',
      width: 70,
      render: (v: boolean) => (v ? <Tag color="green">启用</Tag> : <Tag>停用</Tag>),
    },
    {
      title: 'finance 部门映射',
      width: 220,
      render: (_: unknown, row: CostCenter) => {
        const meta = (row.metadata as Record<string, unknown>) || {}
        const mapping = (meta.finance_department_mapping as string[] | undefined) || []
        if (!mapping.length)
          return <Text type="secondary">未配置（点"刷新映射"自动填）</Text>
        return (
          <Space wrap size={4}>
            {mapping.map((m, i) => (
              <Tag key={`${row.id}-${i}`}>{m}</Tag>
            ))}
          </Space>
        )
      },
    },
    {
      title: '操作',
      width: 220,
      fixed: 'right' as const,
      render: (_: unknown, row: CostCenter) => (
        <Space>
          <Button
            size="small"
            onClick={() => {
              setEditing(row)
              setDrawerOpen(true)
            }}
          >
            编辑
          </Button>
          <Popconfirm
            title="确认停用此 班组？"
            description="软删除：is_active=false + deleted_at 落地；下游 service 不再用它"
            okText="停用"
            cancelText="取消"
            onConfirm={() => remove.mutate(row.id)}
          >
            <Button size="small" danger>
              停用
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  const totalEmployees = items.reduce((s, r) => s + (r.stats.employee_count || 0), 0)
  const totalProcesses = items.reduce((s, r) => s + (r.stats.process_count || 0), 0)

  return (
    <div style={{ padding: 16 }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'baseline',
          justifyContent: 'space-between',
          marginBottom: 12,
        }}
      >
        <div>
          <Title level={3} style={{ marginBottom: 4 }}>
            💼 班组（cost_center）
          </Title>
          <Paragraph type="secondary" style={{ marginBottom: 0 }}>
            真数据通电 · Path A §A1 — 把 <Text code>processes.team_name</Text>{' '}
            字符串升级为可被 Hub 4 层 resolve 链命中的 cost_center 实体。修改后
            A2/A3/A4 batch 立即可用。
          </Paragraph>
        </div>
        <Space>
          <Tag color="purple">Path A §A1</Tag>
        </Space>
      </div>

      <Card style={{ marginBottom: 12 }}>
        <Space size="large" wrap>
          <Statistic title="启用班组数" value={items.filter(r => r.is_active).length} />
          <Statistic title="员工合计 (finance)" value={totalEmployees} />
          <Statistic title="工序合计" value={totalProcesses} />
          <Tooltip
            title={
              list.data?.finance_warnings?.length
                ? list.data.finance_warnings.join('；')
                : 'finance employees 拉取来源'
            }
          >
            <Tag color={list.data?.finance_data_source === 'unavailable' ? 'red' : 'blue'}>
              finance: {list.data?.finance_data_source ?? '-'}
            </Tag>
          </Tooltip>
        </Space>
      </Card>

      <Space style={{ marginBottom: 12 }} wrap>
        <Button type="primary" onClick={() => { setEditing(null); setDrawerOpen(true) }}>
          + 新建班组
        </Button>
        <Button
          onClick={() => refreshMapping.mutate()}
          loading={refreshMapping.isPending}
        >
          🔄 刷新 finance 部门映射
        </Button>
        <Switch
          checked={showInactive}
          onChange={setShowInactive}
          checkedChildren="含停用"
          unCheckedChildren="只看启用"
        />
      </Space>

      <Card style={{ marginBottom: 12 }} size="small" title="🚀 一键算月（自动跑 A2+A3+A4）">
        <RunBatchToolbar />
      </Card>

      <Spin spinning={list.isLoading}>
        {items.length === 0 && !list.isLoading ? (
          <Empty description="暂无 cost_center；点新建或先跑 Migration 0040 落 6 班组初稿" />
        ) : (
          <Table
            rowKey="id"
            columns={columns}
            dataSource={items}
            pagination={false}
            scroll={{ x: 1300 }}
            size="middle"
          />
        )}
      </Spin>

      <CostCenterEditDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        initial={editing}
      />
    </div>
  )
}
