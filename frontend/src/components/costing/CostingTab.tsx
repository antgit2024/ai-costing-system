/**
 * TDABC v1 H — 标准模型「成本核算」Tab.
 *
 * 行业方法论（POD / TDABC，详见 DOC/costing/blueprints/costing_methodology_industry_alignment.md）：
 * - 我们是按需印制（POD），不是 SAP MTO，**不**走标准成本表 + 月度差异分摊那一套。
 * - 单件成本 = 物料每单实际价 + 班组真工资时薪 × 工时 + Hub 4 层 resolve 制造费。
 * - 修改 Hub 任何一层（model > category > cost_center > global）→ 立即影响。
 *
 * 渲染分三块：
 * 1. ⚠️ 试算参数（宽/高/数量 + 刷新计算）
 * 2. 物料 / 人工 / 制造费 三层成本（每层带数据来源徽章 + 链路展开）
 * 3. 合计 + 「为本模型单独设固定时薪/费率」按钮（写 cost_rate_master scope=model）
 */

import { useCallback, useMemo, useState } from 'react'
import {
  Alert,
  Button,
  Card,
  Descriptions,
  Form,
  InputNumber,
  Modal,
  Skeleton,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
  message,
} from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { previewProductModel } from '@/services/planner'
import { createLongTailStrategy } from '@/services/longTailStrategy'
import type {
  ProductModelPreviewLaborLine,
  ProductModelPreviewMaterialLine,
  ProductModelPreviewResponse,
} from '@/types/planner'

const { Text, Title } = Typography

interface CostingTabProps {
  modelId: string | null | undefined
  /** Optional — currently unused; reserved for future per-version cost preview. */
  versionId?: string | null
  /** Read-only mode disables the "为本模型单独设" buttons. */
  readOnly?: boolean
}

const toNumber = (raw: string | number | null | undefined, fallback = 0): number => {
  if (raw === null || raw === undefined || raw === '') return fallback
  if (typeof raw === 'number') return Number.isFinite(raw) ? raw : fallback
  const n = Number(raw)
  return Number.isFinite(n) ? n : fallback
}

const formatCny = (raw: string | number | null | undefined, digits = 2): string => {
  const n = toNumber(raw, 0)
  return `¥${n.toFixed(digits)}`
}

const formatRate = (raw: string | number | null | undefined, digits = 4): string => {
  const n = toNumber(raw, 0)
  return n.toFixed(digits)
}

const formatPercent = (raw: string | number | null | undefined, digits = 2): string => {
  const n = toNumber(raw, 0)
  return `${(n * 100).toFixed(digits)}%`
}

// --- 数据来源徽章规范（统一 UI 语言）---------------------------------------
// 🟢 物料级精确（每物料独立配置）= material_master / inclusive 含税还原
// 🔵 Hub 命中 (model / category / cost_center) = 真实可信
// ⚪ Hub 全局兜底 = 通用近似
// ⚫ 硬编码兜底 / metadata 快照 = 历史数据，可能失真
// ⚠️ 未配置 → 用 0 = 数据缺失，需补
type BadgeLevel = 'green' | 'blue' | 'gray' | 'black' | 'warn'

interface BadgeMeta {
  level: BadgeLevel
  label: string
  desc: string
}

const labelForLaborSource = (line: ProductModelPreviewLaborLine): BadgeMeta => {
  const src = (line.rate_source ?? '').toLowerCase()
  const layer = (line.rate_hit_layer ?? '').toLowerCase()
  if (src === 'hub_model' || layer === 'model') {
    return { level: 'blue', label: '🔵 模型级覆盖', desc: 'cost_rate_master scope=model' }
  }
  if (src === 'hub_category' || layer === 'category') {
    return { level: 'blue', label: '🔵 类目级', desc: 'cost_rate_master scope=category' }
  }
  if (src === 'hub_cost_center' || layer === 'cost_center') {
    return {
      level: 'blue',
      label: '🔵 班组级真工资',
      desc: 'A2 finance 真工资 ÷ 班组工时容量自动算',
    }
  }
  if (src === 'hub_global' || layer === 'global') {
    return { level: 'gray', label: '⚪ Hub 全局兜底', desc: 'cost_rate_master scope=global' }
  }
  if (src === 'metadata') {
    return { level: 'black', label: '⚫ 历史 metadata', desc: '模型快照里的死数 (rate_per_minute)' }
  }
  if (src === 'missing') {
    return { level: 'warn', label: '⚠️ 未配置', desc: '走 0 — 必须补 metadata 或 Hub' }
  }
  return { level: 'gray', label: '— 未知', desc: src || '(无来源)' }
}

const labelForOverhead = (hit: string | null | undefined): BadgeMeta => {
  switch ((hit ?? '').toLowerCase()) {
    case 'model':
      return { level: 'blue', label: '🔵 模型级覆盖', desc: 'cost_rate_master scope=model' }
    case 'category':
      return { level: 'blue', label: '🔵 类目级', desc: 'cost_rate_master scope=category' }
    case 'cost_center':
      return { level: 'blue', label: '🔵 班组级', desc: 'A4 固定费按面积/人头/营收摊到班组 (auto)' }
    case 'global':
      return { level: 'gray', label: '⚪ Hub 全局兜底', desc: 'cost_rate_master scope=global' }
    case 'hard_fallback':
      return { level: 'black', label: '⚫ 硬编码兜底 0.30', desc: 'Hub 没数据 → 默认 0.30' }
    default:
      return { level: 'gray', label: '— 未知', desc: hit || '(无层级)' }
  }
}

const labelForMaterial = (line: ProductModelPreviewMaterialLine): BadgeMeta => {
  const q = (line.price_metadata?._data_quality ?? '').toLowerCase()
  if (q === 'green') {
    return { level: 'green', label: '🟢 物料级精确', desc: '含税还原 + 生效期 + 价格来源齐全' }
  }
  if (q === 'yellow') {
    return { level: 'gray', label: '🟡 物料级近似', desc: '老数据缺生效期或 price_source' }
  }
  if (q === 'red') {
    return { level: 'warn', label: '⚠️ 物料级缺失', desc: '未配置 BOM 单价' }
  }
  if (line.bom_unit_price !== null && line.bom_unit_price !== undefined) {
    return { level: 'green', label: '🟢 物料级', desc: 'BOM 单价已配置' }
  }
  return { level: 'warn', label: '⚠️ 未配置 BOM 单价', desc: '物料未配置 BOM 单价 → 走 0' }
}

const TAG_COLOR: Record<BadgeLevel, string> = {
  green: 'success',
  blue: 'processing',
  gray: 'default',
  black: 'default',
  warn: 'warning',
}

const Badge = ({ meta }: { meta: BadgeMeta }) => (
  <Tooltip title={meta.desc} placement="top">
    <Tag color={TAG_COLOR[meta.level]} style={{ marginInlineEnd: 0 }}>
      {meta.label}
    </Tag>
  </Tooltip>
)

const aggregateLaborSource = (lines: ProductModelPreviewLaborLine[]): BadgeMeta => {
  if (!lines.length) {
    return { level: 'gray', label: '—', desc: '无工序行' }
  }
  // Worst-of mode: any 'missing' wins → ⚠️; any 'metadata' wins → ⚫;
  // any 'hub_global' wins → ⚪; any 'hub_*' on cost_center/category/model wins → 🔵
  const layers = lines.map((l) => labelForLaborSource(l).level)
  if (layers.includes('warn')) return labelForLaborSource(lines.find((l) => labelForLaborSource(l).level === 'warn')!)
  if (layers.includes('black')) return labelForLaborSource(lines.find((l) => labelForLaborSource(l).level === 'black')!)
  if (layers.includes('gray')) return labelForLaborSource(lines.find((l) => labelForLaborSource(l).level === 'gray')!)
  if (layers.includes('blue')) {
    // pick the highest priority hit (model > category > cost_center)
    const order = ['hub_model', 'hub_category', 'hub_cost_center']
    for (const key of order) {
      const found = lines.find((l) => (l.rate_source ?? '').toLowerCase() === key)
      if (found) return labelForLaborSource(found)
    }
    return labelForLaborSource(lines.find((l) => labelForLaborSource(l).level === 'blue')!)
  }
  return labelForLaborSource(lines[0])
}

const aggregateMaterialSource = (lines: ProductModelPreviewMaterialLine[]): BadgeMeta => {
  if (!lines.length) {
    return { level: 'gray', label: '—', desc: '无物料行' }
  }
  const levels = lines.map((l) => labelForMaterial(l).level)
  if (levels.includes('warn')) return labelForMaterial(lines.find((l) => labelForMaterial(l).level === 'warn')!)
  if (levels.includes('gray')) return labelForMaterial(lines.find((l) => labelForMaterial(l).level === 'gray')!)
  return labelForMaterial(lines[0])
}

interface OverrideModalProps {
  open: boolean
  modelId: string
  rateType: 'labor_per_minute' | 'overhead_rate'
  initialRate: number
  onClose: () => void
  onSuccess: () => void
}

const RATE_TYPE_LABEL: Record<OverrideModalProps['rateType'], string> = {
  labor_per_minute: '人工时薪 (¥/分钟)',
  overhead_rate: '制造费费率 (0~1，例如 0.25 = 25%)',
}

const OverrideRateModal = ({
  open,
  modelId,
  rateType,
  initialRate,
  onClose,
  onSuccess,
}: OverrideModalProps) => {
  const [form] = Form.useForm()
  const queryClient = useQueryClient()

  const mutation = useMutation({
    mutationFn: async (rate: number) => {
      return await createLongTailStrategy({
        rate_type: rateType,
        scope_type: 'model',
        scope_id: modelId,
        rate_basis: rateType === 'labor_per_minute' ? 'per_minute' : 'pct_of_cost',
        source: 'manual_model_override',
        rate,
        enabled: true,
      })
    },
    onSuccess: () => {
      message.success('已保存模型级覆盖，正在刷新预览...')
      queryClient.invalidateQueries({ queryKey: ['cost-preview'] })
      onSuccess()
      onClose()
    },
    onError: (err: any) => {
      const detail = err?.response?.data?.detail || err?.message || '未知错误'
      message.error(`保存失败：${detail}`)
    },
  })

  const handleSubmit = useCallback(async () => {
    try {
      const values = await form.validateFields()
      const rate = Number(values.rate)
      if (!Number.isFinite(rate) || rate < 0) {
        message.error('rate 必须 ≥ 0')
        return
      }
      await mutation.mutateAsync(rate)
    } catch {
      // antd validation error will surface inline
    }
  }, [form, mutation])

  return (
    <Modal
      open={open}
      title={`为本模型单独设 — ${RATE_TYPE_LABEL[rateType]}`}
      okText="保存覆盖"
      cancelText="取消"
      confirmLoading={mutation.isPending}
      onOk={handleSubmit}
      onCancel={onClose}
      destroyOnClose
    >
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 12 }}
        message="模型级覆盖说明"
        description={
          <div style={{ lineHeight: 1.7 }}>
            写入 <code>cost_rate_master</code>，
            <code>scope_type=model</code>，
            <code>scope_id={modelId.slice(0, 8)}…</code>
            ，<code>source=manual_model_override</code>。<br />
            模型层级会覆盖类目 / 班组 / 全局，立即影响预览与 BOM 快照。
            如要还原回班组真工资，请到「Cost Rate Hub 管理」页删除本行。
          </div>
        }
      />
      <Form form={form} layout="vertical" initialValues={{ rate: initialRate }}>
        <Form.Item
          name="rate"
          label={RATE_TYPE_LABEL[rateType]}
          rules={[{ required: true, message: '请输入 rate' }]}
        >
          <InputNumber
            style={{ width: '100%' }}
            min={0}
            max={rateType === 'overhead_rate' ? 1 : 100}
            step={rateType === 'overhead_rate' ? 0.01 : 0.05}
            precision={4}
            placeholder={rateType === 'overhead_rate' ? '0.25' : '0.85'}
          />
        </Form.Item>
      </Form>
    </Modal>
  )
}

export default function CostingTab({ modelId, readOnly = false }: CostingTabProps) {
  const [widthMm, setWidthMm] = useState<number>(180)
  const [heightMm, setHeightMm] = useState<number>(90)
  const [quantity, setQuantity] = useState<number>(1)
  const [overrideOpen, setOverrideOpen] = useState<{ rateType: 'labor_per_minute' | 'overhead_rate' } | null>(null)

  const previewQuery = useQuery({
    queryKey: ['cost-preview', modelId, widthMm, heightMm, quantity],
    enabled: !!modelId,
    queryFn: () =>
      previewProductModel(modelId!, {
        width_mm: widthMm,
        height_mm: heightMm,
        quantity: quantity,
      }),
  })

  const data: ProductModelPreviewResponse | undefined = previewQuery.data

  const totals = data?.totals ?? {}
  const materialTotal = toNumber(totals['material_cost'])
  const laborTotal = toNumber(totals['labor_cost'])
  const overheadTotal = toNumber(totals['overhead_cost'])
  const grandTotal = toNumber(totals['total_cost'])

  const materialBadge = useMemo(
    () => (data ? aggregateMaterialSource(data.material_lines || []) : null),
    [data],
  )
  const laborBadge = useMemo(
    () => (data ? aggregateLaborSource(data.labor_lines || []) : null),
    [data],
  )
  const overheadBadge = useMemo(
    () => labelForOverhead(data?.costing?.overhead_hit_layer),
    [data?.costing?.overhead_hit_layer],
  )

  const overheadRateNum = toNumber(data?.costing?.overhead_rate, 0)

  // Pick a reasonable default rate for the override modal: use the
  // currently-effective hub rate if any, otherwise a placeholder.
  const defaultLaborOverrideRate = useMemo(() => {
    const lines = data?.labor_lines || []
    for (const l of lines) {
      const r = toNumber(l.rate_per_minute, 0)
      if (r > 0) return Number(r.toFixed(4))
    }
    return 0.85
  }, [data?.labor_lines])
  const defaultOverheadOverrideRate = overheadRateNum > 0 ? Number(overheadRateNum.toFixed(4)) : 0.3

  const refresh = useCallback(() => {
    void previewQuery.refetch()
  }, [previewQuery])

  if (!modelId) {
    return (
      <Alert
        type="info"
        showIcon
        message="请先选择一个模型 / 版本以查看成本核算。"
      />
    )
  }

  return (
    <div className="costing-tab-scope" style={{ paddingBottom: 24 }}>
      {/* 试算参数 */}
      <Card size="small" title="⚙️ 试算参数" style={{ marginBottom: 12 }}>
        <Space wrap align="center">
          <Form layout="inline">
            <Form.Item label="宽 (mm)">
              <InputNumber
                value={widthMm}
                onChange={(v) => setWidthMm(toNumber(v, 0))}
                min={0}
                step={10}
                style={{ width: 120 }}
              />
            </Form.Item>
            <Form.Item label="高 (mm)">
              <InputNumber
                value={heightMm}
                onChange={(v) => setHeightMm(toNumber(v, 0))}
                min={0}
                step={10}
                style={{ width: 120 }}
              />
            </Form.Item>
            <Form.Item label="数量">
              <InputNumber
                value={quantity}
                onChange={(v) => setQuantity(toNumber(v, 1))}
                min={1}
                step={1}
                style={{ width: 100 }}
              />
            </Form.Item>
          </Form>
          <Button type="primary" onClick={refresh} loading={previewQuery.isFetching}>
            刷新计算
          </Button>
        </Space>
        <div style={{ marginTop: 8 }}>
          <Text type="secondary">
            ⓘ 单件成本 = 物料每单实际价 + 班组真工资时薪 × 工时 + Hub 4 层 resolve 制造费。修改 Hub 任何一层 → 立即影响。
          </Text>
        </div>
      </Card>

      {previewQuery.isError ? (
        <Alert
          type="error"
          message="加载失败"
          description={String((previewQuery.error as any)?.message || previewQuery.error || '未知错误')}
          showIcon
          style={{ marginBottom: 12 }}
        />
      ) : null}

      {previewQuery.isLoading ? (
        <Skeleton active />
      ) : (
        <>
          {/* 物料 */}
          <Card
            size="small"
            style={{ marginBottom: 12 }}
            title={
              <Space>
                <span>物料</span>
                <span style={{ fontWeight: 600 }}>{formatCny(materialTotal)}</span>
                {materialBadge ? <Badge meta={materialBadge} /> : null}
              </Space>
            }
          >
            <Table
              size="small"
              rowKey={(_, i) => `mat-${i}`}
              pagination={false}
              dataSource={data?.material_lines ?? []}
              scroll={{ x: 'max-content' }}
              columns={[
                {
                  title: '物料',
                  key: 'material',
                  render: (_, r) => (
                    <Tooltip title={r.material_code ?? ''}>
                      <Text>{r.material_name ?? r.material_code ?? '—'}</Text>
                    </Tooltip>
                  ),
                  width: 180,
                  ellipsis: true,
                },
                { title: '单位', dataIndex: 'unit', key: 'unit', width: 64 },
                {
                  title: '用量',
                  key: 'used_quantity',
                  render: (_, r) => formatRate(r.used_quantity, 4),
                  width: 96,
                  align: 'right' as const,
                },
                {
                  title: '单价 (¥)',
                  key: 'bom_unit_price',
                  render: (_, r) => formatRate(r.bom_unit_price, 4),
                  width: 96,
                  align: 'right' as const,
                },
                {
                  title: '小计 (¥)',
                  key: 'total_cost',
                  render: (_, r) => (r.total_cost == null ? '—' : formatCny(r.total_cost)),
                  width: 96,
                  align: 'right' as const,
                },
                {
                  title: '数据来源',
                  key: 'badge',
                  render: (_, r) => <Badge meta={labelForMaterial(r as ProductModelPreviewMaterialLine)} />,
                  width: 180,
                },
              ]}
              locale={{ emptyText: '暂无物料行（请到「清单编辑」补全）' }}
            />
          </Card>

          {/* 人工 */}
          <Card
            size="small"
            style={{ marginBottom: 12 }}
            title={
              <Space>
                <span>人工</span>
                <span style={{ fontWeight: 600 }}>{formatCny(laborTotal)}</span>
                {laborBadge ? <Badge meta={laborBadge} /> : null}
              </Space>
            }
            extra={
              !readOnly ? (
                <Button
                  size="small"
                  onClick={() => setOverrideOpen({ rateType: 'labor_per_minute' })}
                >
                  ⚙ 为本模型单独设固定时薪
                </Button>
              ) : null
            }
          >
            <Table
              size="small"
              rowKey={(_, i) => `lab-${i}`}
              pagination={false}
              dataSource={data?.labor_lines ?? []}
              scroll={{ x: 'max-content' }}
              columns={[
                {
                  title: '工序',
                  key: 'process',
                  render: (_, r) => (
                    <Tooltip title={r.process_code ?? ''}>
                      <Text>{r.process_name ?? r.process_code ?? '—'}</Text>
                    </Tooltip>
                  ),
                  width: 160,
                  ellipsis: true,
                },
                { title: '班组', dataIndex: 'team_name', key: 'team_name', width: 100, ellipsis: true },
                {
                  title: '类型',
                  key: 'cost_type',
                  render: (_, r) => (r.cost_type === 'piece' ? '计件' : '计时'),
                  width: 64,
                },
                {
                  title: '工时 / 件量',
                  key: 'minutes',
                  render: (_, r) =>
                    r.cost_type === 'piece'
                      ? formatRate(r.measure_quantity, 2)
                      : formatRate(r.total_minutes ?? 0, 2),
                  width: 100,
                  align: 'right' as const,
                },
                {
                  title: '时薪 / 件单价 (¥)',
                  key: 'rate',
                  render: (_, r) =>
                    r.cost_type === 'piece'
                      ? formatRate(r.piece_rate, 4)
                      : formatRate(r.rate_per_minute, 4),
                  width: 132,
                  align: 'right' as const,
                },
                {
                  title: '小计 (¥)',
                  key: 'total_cost',
                  render: (_, r) => (r.total_cost == null ? '—' : formatCny(r.total_cost)),
                  width: 96,
                  align: 'right' as const,
                },
                {
                  title: '数据来源 (4 层链路)',
                  key: 'badge',
                  render: (_, r) => {
                    const meta = labelForLaborSource(r as ProductModelPreviewLaborLine)
                    const legacy = toNumber((r as ProductModelPreviewLaborLine).rate_per_minute_legacy, 0)
                    const cur = toNumber(r.rate_per_minute, 0)
                    return (
                      <Space size={4} wrap>
                        <Badge meta={meta} />
                        {legacy > 0 && legacy !== cur ? (
                          <Tooltip title={`metadata 快照价：¥${legacy.toFixed(4)}/分钟（已被 Hub 覆盖）`}>
                            <Tag>原 metadata: ¥{legacy.toFixed(2)}</Tag>
                          </Tooltip>
                        ) : null}
                      </Space>
                    )
                  },
                  width: 240,
                },
              ]}
              locale={{ emptyText: '暂无工序行' }}
            />
            <Descriptions column={1} size="small" style={{ marginTop: 8 }}>
              <Descriptions.Item label="时薪来源">
                {laborBadge ? <Badge meta={laborBadge} /> : '—'}
              </Descriptions.Item>
              <Descriptions.Item label="班组（众数）">
                <Text code>{data?.costing?.dominant_cost_center_id ?? '— (老数据未配 cost_center_id)'}</Text>
              </Descriptions.Item>
            </Descriptions>
          </Card>

          {/* 制造费 */}
          <Card
            size="small"
            style={{ marginBottom: 12 }}
            title={
              <Space>
                <span>制造费</span>
                <span style={{ fontWeight: 600 }}>{formatCny(overheadTotal)}</span>
                <Tag>费率 {formatPercent(overheadRateNum)}</Tag>
                <Badge meta={overheadBadge} />
              </Space>
            }
            extra={
              !readOnly ? (
                <Button
                  size="small"
                  onClick={() => setOverrideOpen({ rateType: 'overhead_rate' })}
                >
                  ⚙ 为本模型单独设费率
                </Button>
              ) : null
            }
          >
            <Descriptions column={1} size="small">
              <Descriptions.Item label="命中链路 (model > category > cost_center > global)">
                <Space wrap size={4}>
                  <Tag color={overheadBadge.level === 'blue' && data?.costing?.overhead_hit_layer === 'model' ? 'blue' : 'default'}>
                    model {data?.costing?.overhead_hit_layer === 'model' ? `✓ ${formatRate(overheadRateNum)}` : '(空)'}
                  </Tag>
                  <Tag color={data?.costing?.overhead_hit_layer === 'category' ? 'blue' : 'default'}>
                    category {data?.costing?.overhead_hit_layer === 'category' ? `✓ ${formatRate(overheadRateNum)}` : '(空)'}
                  </Tag>
                  <Tag color={data?.costing?.overhead_hit_layer === 'cost_center' ? 'blue' : 'default'}>
                    cost_center {data?.costing?.overhead_hit_layer === 'cost_center' ? `✓ ${formatRate(overheadRateNum)}` : '(空)'}
                  </Tag>
                  <Tag color={data?.costing?.overhead_hit_layer === 'global' ? 'default' : 'default'}>
                    global {data?.costing?.overhead_hit_layer === 'global' ? `✓ ${formatRate(overheadRateNum)}` : '(空)'}
                  </Tag>
                  <Tag color={data?.costing?.overhead_hit_layer === 'hard_fallback' ? 'red' : 'default'}>
                    hard_fallback {data?.costing?.overhead_hit_layer === 'hard_fallback' ? `✓ 0.30` : ''}
                  </Tag>
                </Space>
              </Descriptions.Item>
              <Descriptions.Item label="数据源">
                <Space wrap>
                  <Tag>scope_type={data?.costing?.overhead_scope_type ?? '—'}</Tag>
                  <Tag>scope_id={data?.costing?.overhead_scope_id ?? '—'}</Tag>
                  <Tag>source={data?.costing?.overhead_source ?? '—'}</Tag>
                  {data?.costing?.overhead_data_quality ? (
                    <Tag color={
                      data.costing.overhead_data_quality === 'green' ? 'success' :
                      data.costing.overhead_data_quality === 'yellow' ? 'warning' : 'error'
                    }>
                      data_quality={data.costing.overhead_data_quality}
                    </Tag>
                  ) : null}
                </Space>
              </Descriptions.Item>
              <Descriptions.Item label="计算口径">
                制造费 = (物料 + 人工) × 费率 = (¥{materialTotal.toFixed(2)} + ¥{laborTotal.toFixed(2)}) × {formatPercent(overheadRateNum)}
              </Descriptions.Item>
            </Descriptions>
          </Card>

          {/* 合计 */}
          <Card size="small" title="合计">
            <Title level={3} style={{ margin: 0 }}>
              {formatCny(grandTotal)}
            </Title>
            <Text type="secondary" style={{ display: 'block', marginTop: 8 }}>
              ⓘ 这是该模型在【当前 Hub 配置】下，按 TDABC 算法得到的唯一真实标准成本。
              <br />
              （行业方法论：POD / TDABC，不走 SAP 标准成本表 + 月度差异分摊那一套。）
            </Text>
            {data?.errors?.length ? (
              <Alert
                type="warning"
                style={{ marginTop: 8 }}
                showIcon
                message="试算告警"
                description={
                  <ul style={{ margin: 0, paddingLeft: 20 }}>
                    {data.errors.map((e, i) => (
                      <li key={i}>{e}</li>
                    ))}
                  </ul>
                }
              />
            ) : null}
          </Card>
        </>
      )}

      {overrideOpen ? (
        <OverrideRateModal
          open={!!overrideOpen}
          modelId={modelId}
          rateType={overrideOpen.rateType}
          initialRate={
            overrideOpen.rateType === 'labor_per_minute'
              ? defaultLaborOverrideRate
              : defaultOverheadOverrideRate
          }
          onClose={() => setOverrideOpen(null)}
          onSuccess={() => previewQuery.refetch()}
        />
      ) : null}
    </div>
  )
}
