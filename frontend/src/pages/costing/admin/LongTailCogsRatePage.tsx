import {
  Alert,
  Button,
  Card,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Select,
  Space,
  Switch,
  Table,
  Tabs,
  Tag,
  Tooltip,
  Typography,
  message,
} from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'

import {
  createLongTailStrategy,
  deleteLongTailStrategy,
  fetchLongTailStrategies,
  patchLongTailStrategy,
  previewLongTailRateForSku,
} from '../../../services/longTailStrategy'
import AlgorithmLogTab from './AlgorithmLogTab'
import type {
  CostRateDataQuality,
  CostRateScopeType,
  LongTailCogsRateResolvePreviewResponse,
  LongTailCogsRateStrategy,
  LongTailCogsRateStrategyUpsertPayload,
} from '../../../types/planner'
import { formatBeijingTime } from '../../../utils/beijingTime'

const { Title, Text, Paragraph } = Typography

const COGS_QUERY_KEY = ['planner', 'longTailStrategies', 'cogs'] as const
const OVERHEAD_QUERY_KEY = ['planner', 'longTailStrategies', 'overhead_rate'] as const

const SOURCE_LABEL: Record<string, { color: string; text: string; tip: string }> = {
  manual: {
    color: 'gold',
    text: '人工指定',
    tip: 'SkuMaster.metadata.long_tail_category 命中此分类',
  },
  keyword: {
    color: 'blue',
    text: '关键字命中',
    tip: '按 spec_text + product_name 关键字匹配（高 priority 优先）',
  },
  default_strategy: {
    color: 'cyan',
    text: '兜底策略',
    tip: 'category=default 的策略',
  },
  global_setting: {
    color: 'default',
    text: '全局 settings',
    tip: '没有任何策略命中，回落到 settings.long_tail_cogs_rate（环境变量 LONG_TAIL_COGS_RATE）',
  },
  overhead_rate_hub: {
    color: 'purple',
    text: 'Hub 命中',
    tip: 'Cost Rate Hub 4 层 resolve 命中（model > category > cost_center > global）',
  },
  hard_fallback: {
    color: 'red',
    text: '硬兜底 0.30',
    tip: '4 层 Hub 链都没命中，回落到 0.30 默认值',
  },
}

const DATA_QUALITY_TAG: Record<CostRateDataQuality, { color: string; label: string }> = {
  green: { color: 'green', label: '🟢 高（实测/可验证）' },
  yellow: { color: 'gold', label: '🟡 中（估算/月度反推）' },
  red: { color: 'red', label: '🔴 低（默认/硬兜底）' },
}

/**
 * Path A §A5 — 数据源徽章。
 *
 * `cost_rate_master.source` 值映射到 4 种"出身"：
 *   manual                          → 🟢 manual    (人工录入)
 *   auto_aggregated_from_finance    → 🔵 auto      (A2 班组工资聚合产物)
 *   auto_allocated_from_finance     → 🟣 allocated (A4 班组分摊产物)
 *   <其他/null>                     → ⚫ legacy    (旧 long-tail 兜底 / 未知)
 */
const SOURCE_BADGE: Record<string, { color: string; emoji: string; label: string; group: 'manual' | 'auto' }> = {
  manual: { color: 'green', emoji: '🟢', label: 'manual', group: 'manual' },
  auto_aggregated_from_finance: {
    color: 'blue',
    emoji: '🔵',
    label: 'auto (A2 工资)',
    group: 'auto',
  },
  auto_allocated_from_finance: {
    color: 'purple',
    emoji: '🟣',
    label: 'allocated (A4 分摊)',
    group: 'auto',
  },
  finance_pushback: { color: 'default', emoji: '⚫', label: 'legacy', group: 'manual' },
  imported_excel: { color: 'default', emoji: '⚫', label: 'legacy', group: 'manual' },
  system_calculated: { color: 'default', emoji: '⚫', label: 'legacy', group: 'manual' },
}

function sourceGroup(s?: string | null): 'manual' | 'auto' {
  if (!s) return 'manual'
  return SOURCE_BADGE[s]?.group ?? 'manual'
}

const SCOPE_TYPE_OPTIONS: { value: CostRateScopeType; label: string; tip: string }[] = [
  { value: 'model', label: 'model（模型级，最高优先）', tip: 'scope_id 填 product_models.id（UUID）' },
  { value: 'category', label: 'category（品类级）', tip: 'scope_id 填 product_models.category（如 "布艺"）' },
  { value: 'cost_center', label: 'cost_center（成本中心，v1 留位）', tip: 'scope_id 填 cost_center.id（v1 数据可全为空）' },
  { value: 'global', label: 'global（全局兜底）', tip: 'scope_id 留空' },
]

interface CogsEditFormValues {
  category: string
  rate: number
  priority: number
  enabled: boolean
  keywords: string
  note?: string
}

interface OverheadEditFormValues {
  scope_type: CostRateScopeType
  scope_id?: string
  rate: number
  data_quality?: CostRateDataQuality
  source?: string
  effective_from?: string
  note?: string
  enabled: boolean
}

const splitKeywords = (s: string | undefined | null): string[] => {
  if (!s) return []
  return s
    .split(/[,，;；\n]/)
    .map(x => x.trim())
    .filter(Boolean)
}

const joinKeywords = (arr: string[] | undefined | null): string => (arr || []).join(', ')

// ---------------------------------------------------------------------------
// Tab 1 — 长尾成本兜底（cogs，原 long-tail 行为不变）
// ---------------------------------------------------------------------------

function LongTailCogsTab() {
  const navigate = useNavigate()
  const qc = useQueryClient()

  const [editorOpen, setEditorOpen] = useState(false)
  const [editing, setEditing] = useState<LongTailCogsRateStrategy | null>(null)
  const [editorForm] = Form.useForm<CogsEditFormValues>()

  const [previewOpen, setPreviewOpen] = useState(false)
  const [previewForm] = Form.useForm<{
    sku_code?: string
    spec_text?: string
    product_name?: string
    long_tail_category?: string
  }>()
  const [previewResult, setPreviewResult] = useState<LongTailCogsRateResolvePreviewResponse | null>(
    null,
  )

  const listQuery = useQuery({
    queryKey: COGS_QUERY_KEY,
    queryFn: () => fetchLongTailStrategies({ rate_type: 'cogs' }),
  })

  const upsertMutation = useMutation({
    mutationFn: async (vars: { id?: string; payload: LongTailCogsRateStrategyUpsertPayload }) => {
      if (vars.id) return patchLongTailStrategy(vars.id, vars.payload)
      return createLongTailStrategy(vars.payload)
    },
    onSuccess: () => {
      message.success('保存成功')
      setEditorOpen(false)
      setEditing(null)
      editorForm.resetFields()
      qc.invalidateQueries({ queryKey: COGS_QUERY_KEY })
    },
    onError: (err: any) => {
      const detail = err?.response?.data?.detail
      message.error(typeof detail === 'string' ? detail : '保存失败')
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteLongTailStrategy(id, 'web-ui'),
    onSuccess: () => {
      message.success('已停用（软删除）')
      qc.invalidateQueries({ queryKey: COGS_QUERY_KEY })
    },
    onError: () => message.error('删除失败'),
  })

  const previewMutation = useMutation({
    mutationFn: (vars: { sku_code?: string; spec_text?: string; product_name?: string; long_tail_category?: string }) =>
      previewLongTailRateForSku(vars),
    onSuccess: (res) => setPreviewResult(res),
    onError: () => message.error('试算失败'),
  })

  const openCreate = () => {
    setEditing(null)
    editorForm.resetFields()
    editorForm.setFieldsValue({
      category: '',
      rate: 0.55,
      priority: 100,
      enabled: true,
      keywords: '',
      note: '',
    })
    setEditorOpen(true)
  }

  const openEdit = (row: LongTailCogsRateStrategy) => {
    setEditing(row)
    editorForm.setFieldsValue({
      category: row.category,
      rate: row.rate,
      priority: row.priority,
      enabled: row.enabled,
      keywords: joinKeywords(row.keywords),
      note: row.note ?? '',
    })
    setEditorOpen(true)
  }

  const onSubmitEditor = async () => {
    const values = await editorForm.validateFields()
    upsertMutation.mutate({
      id: editing?.id,
      payload: {
        category: values.category.trim(),
        rate: values.rate,
        priority: values.priority,
        enabled: values.enabled,
        keywords: splitKeywords(values.keywords),
        note: values.note?.trim() || null,
        actor: 'web-ui',
      },
    })
  }

  const onSubmitPreview = async () => {
    const values = await previewForm.validateFields()
    previewMutation.mutate({
      sku_code: values.sku_code?.trim() || undefined,
      spec_text: values.spec_text?.trim() || undefined,
      product_name: values.product_name?.trim() || undefined,
      long_tail_category: values.long_tail_category?.trim() || undefined,
    })
  }

  const items = listQuery.data?.items ?? []
  const globalRate = listQuery.data?.global_fallback_rate ?? 0.55

  const columns = useMemo(
    () => [
      {
        title: '品类',
        dataIndex: 'category',
        key: 'category',
        width: 160,
        render: (v: string) => (
          <Space>
            <Text strong>{v}</Text>
            {v.toLowerCase() === 'default' && <Tag color="cyan">兜底</Tag>}
          </Space>
        ),
      },
      {
        title: '比率 (cogs/revenue)',
        dataIndex: 'rate',
        key: 'rate',
        width: 160,
        render: (v: number) => (
          <Text strong style={{ fontFamily: 'monospace' }}>
            {(v * 100).toFixed(2)}%
          </Text>
        ),
      },
      {
        title: '优先级',
        dataIndex: 'priority',
        key: 'priority',
        width: 100,
        render: (v: number) => <Tag>{v}</Tag>,
      },
      {
        title: '关键字',
        dataIndex: 'keywords',
        key: 'keywords',
        render: (kws: string[]) => (
          <Space size={[4, 4]} wrap>
            {(kws || []).length === 0 && <Text type="secondary">—</Text>}
            {(kws || []).map(k => (
              <Tag key={k}>{k}</Tag>
            ))}
          </Space>
        ),
      },
      {
        title: '启用',
        dataIndex: 'enabled',
        key: 'enabled',
        width: 80,
        render: (v: boolean) => (v ? <Tag color="green">启用</Tag> : <Tag>停用</Tag>),
      },
      {
        title: '备注',
        dataIndex: 'note',
        key: 'note',
        ellipsis: true,
        render: (v?: string | null) => v || <Text type="secondary">—</Text>,
      },
      {
        title: '更新时间',
        dataIndex: 'updated_at',
        key: 'updated_at',
        width: 170,
        render: (v?: string | null) =>
          v ? <Text type="secondary">{formatBeijingTime(v)}</Text> : <Text type="secondary">—</Text>,
      },
      {
        title: '操作',
        key: 'actions',
        width: 160,
        fixed: 'right' as const,
        align: 'right' as const,
        render: (_: unknown, row: LongTailCogsRateStrategy) => (
          <Space>
            <Button size="small" onClick={() => openEdit(row)}>
              编辑
            </Button>
            <Popconfirm
              title="确认停用此策略？"
              description="软删除（保留 history 审计）。停用后该品类不再用于自动匹配。"
              okText="停用"
              cancelText="取消"
              onConfirm={() => deleteMutation.mutate(row.id)}
            >
              <Button size="small" danger>
                停用
              </Button>
            </Popconfirm>
          </Space>
        ),
      },
    ],
    [deleteMutation],
  )

  return (
    <>
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 12 }}
        message={
          <Space direction="vertical" size={2}>
            <Text>
              <b>匹配优先级</b>：① 人工标 long_tail_category → ② 关键字命中（高 priority 优先）→ ③ 兜底策略 default → ④ 全局 settings（{(globalRate * 100).toFixed(2)}%）
            </Text>
            <Text type="secondary" style={{ fontSize: 12 }}>
              注：rate 修改不会回写历史快照（trace_json 已记录当时值，报表保持稳定）；每次保存自动记 audit history。
            </Text>
          </Space>
        }
      />

      <Card>
        <Space style={{ marginBottom: 12 }}>
          <Button type="primary" onClick={openCreate}>
            ➕ 新建策略
          </Button>
          <Button
            onClick={() => {
              previewForm.resetFields()
              setPreviewResult(null)
              setPreviewOpen(true)
            }}
          >
            🧪 试算
          </Button>
          <Button onClick={() => listQuery.refetch()} loading={listQuery.isFetching}>
            刷新
          </Button>
          <Button onClick={() => navigate('/costing/biz/shipments?tab=long_tail')}>
            → 长尾池 SKU
          </Button>
        </Space>

        <Table
          rowKey="id"
          loading={listQuery.isLoading}
          dataSource={items}
          columns={columns as any}
          pagination={false}
          size="middle"
          scroll={{ x: 'max-content' }}
        />
      </Card>

      <Modal
        title={editing ? `编辑策略：${editing.category}` : '新建策略'}
        open={editorOpen}
        onCancel={() => setEditorOpen(false)}
        onOk={onSubmitEditor}
        confirmLoading={upsertMutation.isPending}
        okText="保存"
        cancelText="取消"
        destroyOnClose
      >
        <Form form={editorForm} layout="vertical" preserve={false}>
          <Form.Item
            name="category"
            label="品类"
            rules={[{ required: true, message: '请填写品类名（不可重复）' }]}
            extra="例：画框 / 抱枕 / 地毯 / default。'default' 表示兜底策略。"
          >
            <Input placeholder="画框" disabled={editing?.category?.toLowerCase() === 'default'} />
          </Form.Item>
          <Form.Item
            name="rate"
            label="比率（cogs/revenue, 0–1）"
            rules={[{ required: true, message: '必填' }]}
          >
            <InputNumber
              min={0}
              max={1}
              step={0.01}
              precision={4}
              style={{ width: 200 }}
              addonAfter="× revenue"
            />
          </Form.Item>
          <Form.Item
            name="priority"
            label="优先级"
            extra="数值越大越优先匹配；多个关键字策略命中同一 SKU 时高优先生效"
          >
            <InputNumber min={0} max={10000} step={10} style={{ width: 200 }} />
          </Form.Item>
          <Form.Item
            name="enabled"
            label="启用"
            valuePropName="checked"
            extra="停用后此品类不再参与匹配（停用 != 删除）"
          >
            <Switch />
          </Form.Item>
          <Form.Item
            name="keywords"
            label="关键字（逗号或换行分隔）"
            extra="匹配 SkuMaster.spec_text + product_name + product_code + barcode（小写子串）"
          >
            <Input.TextArea rows={3} placeholder="画框, frame, 实木框" />
          </Form.Item>
          <Form.Item name="note" label="备注（财务说明）">
            <Input.TextArea rows={2} placeholder="例：2026-Q2 财务校准结果" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="🧪 试算：这个 SKU 会被哪条策略命中？"
        open={previewOpen}
        onCancel={() => setPreviewOpen(false)}
        footer={[
          <Button key="close" onClick={() => setPreviewOpen(false)}>
            关闭
          </Button>,
          <Button
            key="run"
            type="primary"
            loading={previewMutation.isPending}
            onClick={onSubmitPreview}
          >
            试算
          </Button>,
        ]}
        destroyOnClose
      >
        <Paragraph type="secondary">
          填一项或多项均可。提供 sku_code 时优先用 SkuMaster 真实数据；其他字段会覆盖。
        </Paragraph>
        <Form form={previewForm} layout="vertical" preserve={false}>
          <Form.Item name="sku_code" label="SKU 条码">
            <Input placeholder="例：6973xxx" />
          </Form.Item>
          <Form.Item name="spec_text" label="规格文本（spec_text）">
            <Input placeholder="例：实木画框 60x80cm" />
          </Form.Item>
          <Form.Item name="product_name" label="商品名（product_name）">
            <Input placeholder="例：北欧风装饰画" />
          </Form.Item>
          <Form.Item
            name="long_tail_category"
            label="模拟人工标 long_tail_category"
            extra="留空则不模拟人工指定"
          >
            <Input placeholder="例：画框" />
          </Form.Item>
        </Form>
        {previewResult && (
          <Card size="small" style={{ marginTop: 12, background: 'rgba(255,255,255,0.04)' }}>
            <Space direction="vertical" size={6}>
              <Space>
                <Text strong>命中来源:</Text>
                <Tooltip title={SOURCE_LABEL[previewResult.source]?.tip}>
                  <Tag color={SOURCE_LABEL[previewResult.source]?.color}>
                    {SOURCE_LABEL[previewResult.source]?.text || previewResult.source}
                  </Tag>
                </Tooltip>
              </Space>
              <Space>
                <Text strong>使用比率:</Text>
                <Text style={{ fontFamily: 'monospace', fontSize: 16 }}>
                  {(previewResult.rate * 100).toFixed(2)}%
                </Text>
              </Space>
              {previewResult.category && (
                <Space>
                  <Text strong>命中品类:</Text>
                  <Tag>{previewResult.category}</Tag>
                </Space>
              )}
              {previewResult.matched_keyword && (
                <Space>
                  <Text strong>命中关键字:</Text>
                  <Tag color="blue">{previewResult.matched_keyword}</Tag>
                </Space>
              )}
              {previewResult.strategy_id && (
                <Text type="secondary" style={{ fontSize: 12 }}>
                  strategy_id: <code>{previewResult.strategy_id}</code>
                </Text>
              )}
            </Space>
          </Card>
        )}
      </Modal>
    </>
  )
}

// ---------------------------------------------------------------------------
// Tab 2 — 制造费率治理（overhead_rate，v1.3 Cost Rate Hub）
// ---------------------------------------------------------------------------

function OverheadRateTab() {
  const qc = useQueryClient()

  const [editorOpen, setEditorOpen] = useState(false)
  const [editing, setEditing] = useState<LongTailCogsRateStrategy | null>(null)
  const [editorForm] = Form.useForm<OverheadEditFormValues>()
  // Path A §A5 — auto/manual 切换：默认 all，可只看 auto 或只看 manual。
  const [sourceFilter, setSourceFilter] = useState<'all' | 'auto' | 'manual'>('all')

  const [previewOpen, setPreviewOpen] = useState(false)
  const [previewForm] = Form.useForm<{
    rate_type: 'overhead_rate'
    model_id?: string
    category?: string
    cost_center_id?: string
  }>()
  const [previewResult, setPreviewResult] = useState<LongTailCogsRateResolvePreviewResponse | null>(
    null,
  )

  const listQuery = useQuery({
    queryKey: OVERHEAD_QUERY_KEY,
    queryFn: () => fetchLongTailStrategies({ rate_type: 'overhead_rate' }),
  })

  const upsertMutation = useMutation({
    mutationFn: async (vars: { id?: string; payload: LongTailCogsRateStrategyUpsertPayload }) => {
      if (vars.id) return patchLongTailStrategy(vars.id, vars.payload)
      return createLongTailStrategy(vars.payload)
    },
    onSuccess: () => {
      message.success('保存成功')
      setEditorOpen(false)
      setEditing(null)
      editorForm.resetFields()
      qc.invalidateQueries({ queryKey: OVERHEAD_QUERY_KEY })
    },
    onError: (err: any) => {
      const detail = err?.response?.data?.detail
      message.error(typeof detail === 'string' ? detail : '保存失败')
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteLongTailStrategy(id, 'web-ui'),
    onSuccess: () => {
      message.success('已归档（软删除）')
      qc.invalidateQueries({ queryKey: OVERHEAD_QUERY_KEY })
    },
    onError: () => message.error('归档失败'),
  })

  const previewMutation = useMutation({
    mutationFn: (vars: { rate_type: 'overhead_rate'; model_id?: string; category?: string; cost_center_id?: string }) =>
      previewLongTailRateForSku(vars),
    onSuccess: (res) => setPreviewResult(res),
    onError: () => message.error('试算失败'),
  })

  const openCreate = () => {
    setEditing(null)
    editorForm.resetFields()
    editorForm.setFieldsValue({
      scope_type: 'model',
      rate: 0.25,
      data_quality: 'yellow',
      source: 'manual',
      enabled: true,
    })
    setEditorOpen(true)
  }

  const openEdit = (row: LongTailCogsRateStrategy) => {
    setEditing(row)
    editorForm.setFieldsValue({
      scope_type: (row.scope_type as CostRateScopeType) || 'model',
      scope_id: row.scope_id ?? undefined,
      rate: row.rate,
      data_quality: (row.data_quality as CostRateDataQuality | null) ?? undefined,
      source: row.source,
      effective_from: row.effective_from ?? undefined,
      note: row.note ?? '',
      enabled: row.enabled,
    })
    setEditorOpen(true)
  }

  const onSubmitEditor = async () => {
    const values = await editorForm.validateFields()
    if (values.scope_type !== 'global' && !values.scope_id?.trim()) {
      message.error('非 global scope 必须填 scope_id')
      return
    }
    upsertMutation.mutate({
      id: editing?.id,
      payload: {
        rate_type: 'overhead_rate',
        scope_type: values.scope_type,
        scope_id: values.scope_type === 'global' ? null : values.scope_id?.trim(),
        rate: values.rate,
        data_quality: values.data_quality ?? null,
        source: values.source || 'manual',
        effective_from: values.effective_from || null,
        note: values.note?.trim() || null,
        enabled: values.enabled,
        actor: 'web-ui',
      },
    })
  }

  const onSubmitPreview = async () => {
    const values = await previewForm.validateFields()
    previewMutation.mutate({
      rate_type: 'overhead_rate',
      model_id: values.model_id?.trim() || undefined,
      category: values.category?.trim() || undefined,
      cost_center_id: values.cost_center_id?.trim() || undefined,
    })
  }

  const items = listQuery.data?.items ?? []

  const columns = useMemo(
    () => [
      {
        title: 'scope_type',
        dataIndex: 'scope_type',
        key: 'scope_type',
        width: 130,
        render: (v?: string | null) => <Tag color="purple">{v || 'category'}</Tag>,
      },
      {
        title: 'scope_id',
        dataIndex: 'scope_id',
        key: 'scope_id',
        width: 240,
        ellipsis: true,
        render: (v?: string | null) =>
          v ? <Text style={{ fontFamily: 'monospace' }}>{v}</Text> : <Text type="secondary">global</Text>,
      },
      {
        title: 'rate',
        dataIndex: 'rate',
        key: 'rate',
        width: 120,
        render: (v: number) => (
          <Text strong style={{ fontFamily: 'monospace' }}>
            {(v * 100).toFixed(2)}%
          </Text>
        ),
      },
      {
        title: 'rate_basis',
        dataIndex: 'rate_basis',
        key: 'rate_basis',
        width: 140,
        render: (v?: string | null) => <Tag>{v || 'pct_of_cost'}</Tag>,
      },
      {
        title: 'data_quality',
        dataIndex: 'data_quality',
        key: 'data_quality',
        width: 170,
        render: (v?: string | null) => {
          if (!v) return <Text type="secondary">—</Text>
          const cfg = DATA_QUALITY_TAG[v as CostRateDataQuality]
          return cfg ? <Tag color={cfg.color}>{cfg.label}</Tag> : <Tag>{v}</Tag>
        },
      },
      {
        title: 'source',
        dataIndex: 'source',
        key: 'source',
        width: 200,
        render: (v?: string | null) => {
          const cfg = SOURCE_BADGE[v || 'manual'] ?? {
            color: 'default',
            emoji: '⚫',
            label: v || 'unknown',
            group: 'manual' as const,
          }
          return (
            <Tooltip
              title={
                cfg.group === 'auto'
                  ? '由 Path A 自动算法回写（A2/A4 batch），无需人工维护'
                  : '人工录入或旧 long-tail 数据 — 优先级高于自动'
              }
            >
              <Tag color={cfg.color}>
                {cfg.emoji} {cfg.label}
              </Tag>
            </Tooltip>
          )
        },
      },
      {
        title: 'effective_from',
        dataIndex: 'effective_from',
        key: 'effective_from',
        width: 170,
        render: (v?: string | null) =>
          v ? <Text type="secondary">{formatBeijingTime(v)}</Text> : <Text type="secondary">立即生效</Text>,
      },
      {
        title: '启用',
        dataIndex: 'enabled',
        key: 'enabled',
        width: 80,
        render: (v: boolean) => (v ? <Tag color="green">启用</Tag> : <Tag>停用</Tag>),
      },
      {
        title: '备注',
        dataIndex: 'note',
        key: 'note',
        ellipsis: true,
        render: (v?: string | null) => v || <Text type="secondary">—</Text>,
      },
      {
        title: '操作',
        key: 'actions',
        width: 160,
        fixed: 'right' as const,
        align: 'right' as const,
        render: (_: unknown, row: LongTailCogsRateStrategy) => (
          <Space>
            <Button size="small" onClick={() => openEdit(row)}>
              编辑
            </Button>
            <Popconfirm
              title="确认归档此费率？"
              description="软删除（保留 history 审计）。归档后该 scope 不再参与 4 层 resolve；要恢复请重新创建同一 scope_type+scope_id。"
              okText="归档"
              cancelText="取消"
              onConfirm={() => deleteMutation.mutate(row.id)}
            >
              <Button size="small" danger>
                归档
              </Button>
            </Popconfirm>
          </Space>
        ),
      },
    ],
    [deleteMutation],
  )

  return (
    <>
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 12 }}
        message={
          <Space direction="vertical" size={2}>
            <Text>
              <b>4 层 resolve 优先级</b>：① model（scope_id=product_models.id）→ ② category（scope_id=布艺/家居饰品...）→ ③ cost_center（v1 留位）→ ④ global → ⑤ 硬兜底 0.30
            </Text>
            <Text type="secondary" style={{ fontSize: 12 }}>
              v1.3 Cost Rate Hub：制造费率治理。<code>rate_basis=pct_of_cost</code> 表示制造费 =（物料费 + 人工费）× rate。<br />
              示例：KB8 配 model 级 rate=0.25 后，KB8 实时核价从 23% 折算占比降为 20%。
            </Text>
          </Space>
        }
      />

      <Card>
        <Space style={{ marginBottom: 12 }} wrap>
          <Button type="primary" onClick={openCreate}>
            ➕ 新建费率
          </Button>
          <Button
            onClick={() => {
              previewForm.resetFields()
              setPreviewResult(null)
              setPreviewOpen(true)
            }}
          >
            🧪 试算 4 层 resolve
          </Button>
          <Button onClick={() => listQuery.refetch()} loading={listQuery.isFetching}>
            刷新
          </Button>
          <Tooltip title="按 source 出身过滤：auto = A2/A4 自动产物；manual = 人工录入或 legacy">
            <Select
              value={sourceFilter}
              onChange={setSourceFilter}
              style={{ width: 200 }}
              options={[
                { value: 'all', label: `全部（${items.length}）` },
                {
                  value: 'manual',
                  label: `🟢 人工 / legacy（${items.filter(r => sourceGroup(r.source) === 'manual').length}）`,
                },
                {
                  value: 'auto',
                  label: `🔵🟣 自动算法（${items.filter(r => sourceGroup(r.source) === 'auto').length}）`,
                },
              ]}
            />
          </Tooltip>
          <Text type="secondary" style={{ fontSize: 12 }}>
            徽章说明：🟢 manual · 🔵 auto (A2 工资) · 🟣 allocated (A4 分摊) · ⚫ legacy
          </Text>
        </Space>

        <Table
          rowKey="id"
          loading={listQuery.isLoading}
          dataSource={
            sourceFilter === 'all'
              ? items
              : items.filter(r => sourceGroup(r.source) === sourceFilter)
          }
          columns={columns as any}
          pagination={false}
          size="middle"
          scroll={{ x: 'max-content' }}
          locale={{ emptyText: '暂无 overhead_rate 配置 — 算法仍走 metadata_json + 0.30 兜底' }}
        />
      </Card>

      <Modal
        title={editing ? `编辑制造费率：${editing.scope_type}/${editing.scope_id || 'global'}` : '新建制造费率'}
        open={editorOpen}
        onCancel={() => setEditorOpen(false)}
        onOk={onSubmitEditor}
        confirmLoading={upsertMutation.isPending}
        okText="保存"
        cancelText="取消"
        destroyOnClose
        width={620}
      >
        <Form form={editorForm} layout="vertical" preserve={false}>
          <Form.Item
            name="scope_type"
            label="范围 (scope_type)"
            rules={[{ required: true, message: '必填' }]}
            extra="model > category > cost_center > global，命中即返回"
          >
            <Select
              options={SCOPE_TYPE_OPTIONS.map(opt => ({
                value: opt.value,
                label: opt.label,
              }))}
              disabled={!!editing}  /* 修改 scope_type 等于改键，禁止；新建即可 */
            />
          </Form.Item>
          <Form.Item
            noStyle
            shouldUpdate={(p, n) => p.scope_type !== n.scope_type}
          >
            {({ getFieldValue }) => {
              const scope = getFieldValue('scope_type') as CostRateScopeType
              if (scope === 'global') {
                return (
                  <Form.Item label="scope_id">
                    <Tag color="default">global 不需要 scope_id</Tag>
                  </Form.Item>
                )
              }
              const tip = SCOPE_TYPE_OPTIONS.find(o => o.value === scope)?.tip
              return (
                <Form.Item
                  name="scope_id"
                  label="scope_id"
                  rules={[{ required: true, message: '必填' }]}
                  extra={tip}
                >
                  <Input
                    placeholder={
                      scope === 'model'
                        ? '例：464ca78d-81d6-40e5-8370-66d94ce49312（KB8）'
                        : scope === 'category'
                          ? '例：布艺 / 家居饰品'
                          : 'cost_center.id'
                    }
                    disabled={!!editing}
                  />
                </Form.Item>
              )
            }}
          </Form.Item>
          <Form.Item
            name="rate"
            label="rate（小数 0–1，例 0.25 表示 25%）"
            rules={[{ required: true, message: '必填' }]}
          >
            <InputNumber min={0} max={1} step={0.01} precision={4} style={{ width: 200 }} addonAfter="× (mat+lab)" />
          </Form.Item>
          <Form.Item name="data_quality" label="data_quality（可信度徽章）">
            <Select
              allowClear
              options={(['green', 'yellow', 'red'] as CostRateDataQuality[]).map(v => ({
                value: v,
                label: DATA_QUALITY_TAG[v].label,
              }))}
            />
          </Form.Item>
          <Form.Item name="source" label="source（数据来源）">
            <Select
              allowClear
              options={[
                { value: 'manual', label: 'manual（人工录入）' },
                { value: 'finance_pushback', label: 'finance_pushback（财务月度反推）' },
                { value: 'imported_excel', label: 'imported_excel（Excel 导入）' },
                { value: 'system_calculated', label: 'system_calculated（系统计算）' },
              ]}
            />
          </Form.Item>
          <Form.Item
            name="effective_from"
            label="生效日期（effective_from，可选）"
            extra="ISO 格式，例 2026-05-01T00:00:00；留空表示立即生效"
          >
            <Input placeholder="2026-05-01T00:00:00" />
          </Form.Item>
          <Form.Item name="enabled" label="启用" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item name="note" label="备注（财务说明 / 凭证链接）">
            <Input.TextArea rows={2} placeholder="例：2026-Q2 财务月度反推；凭证 https://..." />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="🧪 试算：当前参数会命中哪一层 Hub resolve？"
        open={previewOpen}
        onCancel={() => setPreviewOpen(false)}
        footer={[
          <Button key="close" onClick={() => setPreviewOpen(false)}>
            关闭
          </Button>,
          <Button
            key="run"
            type="primary"
            loading={previewMutation.isPending}
            onClick={onSubmitPreview}
          >
            试算
          </Button>,
        ]}
        destroyOnClose
      >
        <Paragraph type="secondary">
          按 4 层链 <code>model &gt; category &gt; cost_center &gt; global</code> 解析 overhead_rate。任一层命中则返回该层 rate；都没命中则返回硬兜底 0.30。
        </Paragraph>
        <Form form={previewForm} layout="vertical" preserve={false} initialValues={{ rate_type: 'overhead_rate' }}>
          <Form.Item name="model_id" label="model_id（product_models.id UUID）">
            <Input placeholder="例：464ca78d-81d6-40e5-8370-66d94ce49312" />
          </Form.Item>
          <Form.Item name="category" label="category（备份品类）">
            <Input placeholder="例：布艺" />
          </Form.Item>
          <Form.Item name="cost_center_id" label="cost_center_id（v1 留位）">
            <Input placeholder="cost_center.id（可空）" />
          </Form.Item>
        </Form>
        {previewResult && (
          <Card size="small" style={{ marginTop: 12, background: 'rgba(255,255,255,0.04)' }}>
            <Space direction="vertical" size={6}>
              <Space>
                <Text strong>命中层级:</Text>
                {previewResult.hit_layer && (
                  <Tooltip title={SOURCE_LABEL[previewResult.source]?.tip}>
                    <Tag color={previewResult.hit_layer === 'hard_fallback' ? 'red' : 'purple'}>
                      {previewResult.hit_layer}
                    </Tag>
                  </Tooltip>
                )}
              </Space>
              <Space>
                <Text strong>使用比率:</Text>
                <Text style={{ fontFamily: 'monospace', fontSize: 16 }}>
                  {(previewResult.rate * 100).toFixed(2)}%
                </Text>
              </Space>
              {previewResult.hit_scope_type && (
                <Space>
                  <Text strong>命中 scope:</Text>
                  <Tag color="purple">
                    {previewResult.hit_scope_type}
                    {previewResult.hit_scope_id ? ` / ${previewResult.hit_scope_id}` : ''}
                  </Tag>
                </Space>
              )}
              {previewResult.data_quality && (
                <Space>
                  <Text strong>data_quality:</Text>
                  <Tag color={DATA_QUALITY_TAG[previewResult.data_quality].color}>
                    {DATA_QUALITY_TAG[previewResult.data_quality].label}
                  </Tag>
                </Space>
              )}
              {previewResult.strategy_id && (
                <Text type="secondary" style={{ fontSize: 12 }}>
                  strategy_id: <code>{previewResult.strategy_id}</code>
                </Text>
              )}
            </Space>
          </Card>
        )}
      </Modal>
    </>
  )
}

// ---------------------------------------------------------------------------
// Page wrapper — Tabs (cogs / overhead_rate)
// ---------------------------------------------------------------------------

export default function LongTailCogsRatePage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const tabParam = searchParams.get('tab')
  const activeTab: 'cogs' | 'overhead_rate' | 'algorithm_log' =
    tabParam === 'overhead_rate'
      ? 'overhead_rate'
      : tabParam === 'algorithm_log'
        ? 'algorithm_log'
        : 'cogs'

  return (
    <div style={{ padding: 16 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between' }}>
        <div>
          <Title level={3} style={{ marginBottom: 4 }}>
            💰 成本费率治理中枢
          </Title>
          <Text type="secondary">
            v1.3 Cost Rate Hub：长尾成本兜底（cogs，原长尾池）+ 制造费率治理（overhead_rate，4 层 resolve）。
          </Text>
        </div>
        <Space>
          <Tag color="green">v1.3</Tag>
          <Tag>Migration 0038</Tag>
        </Space>
      </div>

      <Tabs
        activeKey={activeTab}
        onChange={key => {
          const next = new URLSearchParams(searchParams)
          next.set('tab', key)
          setSearchParams(next, { replace: true })
        }}
        style={{ marginTop: 12 }}
        items={[
          {
            key: 'cogs',
            label: '长尾成本兜底（cogs）',
            children: <LongTailCogsTab />,
          },
          {
            key: 'overhead_rate',
            label: '制造费率治理（overhead_rate）',
            children: <OverheadRateTab />,
          },
          {
            key: 'algorithm_log',
            label: '🤖 自动算法日志',
            children: <AlgorithmLogTab />,
          },
        ]}
      />
    </div>
  )
}
