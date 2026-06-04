import {
  Alert,
  Button,
  Card,
  Drawer,
  Form,
  Input,
  Modal,
  Popconfirm,
  Segmented,
  Select,
  Space,
  Statistic,
  Table,
  Tag,
  Tooltip,
  Typography,
  message,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useMemo, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'

import {
  autoSuggestLongTailCategoryExecute,
  autoSuggestLongTailCategoryPreview,
  listSkuGovernance,
  setSkuGovernance,
  setSkuLongTailCategory,
  type LongTailCategoryAutoSuggestItem,
  type LongTailCategoryAutoSuggestPreviewResponse,
  type SkuGovernanceListItem,
  type SkuGovernanceStatus,
} from '@/services/planner'
import { fetchLongTailStrategies } from '@/services/longTailStrategy'
import { formatBeijingTime } from '@/utils/beijingTime'

const { Text } = Typography

const safeString = (v: unknown): string => (v === null || v === undefined ? '' : String(v))

const formatTime = (v?: string | null) => {
  return formatBeijingTime(v, 'YYYY-MM-DD HH:mm')
}

const formatNumber = (n?: number | null) => {
  if (n === null || n === undefined) return '-'
  if (typeof n !== 'number') return String(n)
  if (Number.isFinite(n)) return n.toLocaleString(undefined, { maximumFractionDigits: 2 })
  return String(n)
}

/**
 * Sprint 3-1: governance backlog tabs (建模 Backlog / 长尾 SKU).
 *
 * Reuses the same /api/planner/sku-master/governance endpoint with a
 * different `status` filter. The "建模 Backlog" view sorts by
 * shipment_score (revenue, descending) so high-impact SKUs surface to
 * the top of the modeling queue. The "长尾 SKU" view is read-only
 * statistics + a "撤回" button to send a SKU back to `unmanaged` if
 * sales picked up.
 */
export default function GovernanceBacklogTab(props: {
  status: SkuGovernanceStatus
  // Used for the action-cell button label, since the same component is
  // mounted under two different tabs with different "primary actions".
  primaryActionLabel?: string
}) {
  const { status, primaryActionLabel } = props
  const navigate = useNavigate()

  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [orderBy, setOrderBy] = useState<'shipment_score' | 'updated_at' | 'last_shipment_at'>(
    'shipment_score',
  )
  const [salesWindowDays, setSalesWindowDays] = useState(30)
  const [searchKeyword, setSearchKeyword] = useState('')

  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([])
  const [categoryEditorOpen, setCategoryEditorOpen] = useState(false)
  const [categoryEditorTargets, setCategoryEditorTargets] = useState<string[]>([])
  const [categoryEditorForm] = Form.useForm<{ category: string; note?: string }>()

  // Auto-suggest drawer state
  const [autoDrawerOpen, setAutoDrawerOpen] = useState(false)
  const [autoPreview, setAutoPreview] = useState<
    LongTailCategoryAutoSuggestPreviewResponse | null
  >(null)
  const [autoSelectedKeys, setAutoSelectedKeys] = useState<React.Key[]>([])

  const query = useQuery({
    queryKey: ['governance', status, page, pageSize, orderBy, salesWindowDays],
    queryFn: () =>
      listSkuGovernance({
        status,
        page,
        page_size: pageSize,
        order_by: orderBy,
        sales_window_days: salesWindowDays,
      }),
    staleTime: 10_000,
  })

  const items = (query.data?.items ?? []).filter((it) => {
    const kw = searchKeyword.trim().toLowerCase()
    if (!kw) return true
    return (
      it.erp_sku_barcode.toLowerCase().includes(kw) ||
      safeString(it.spec_text).toLowerCase().includes(kw) ||
      safeString(it.channel).toLowerCase().includes(kw)
    )
  })

  // Issue 28 follow-up: load strategy categories for the do_not_model
  // "标品类" picker. Only fetched on the long-tail tab; cached 60s since the
  // strategy table changes rarely.
  const strategiesQuery = useQuery({
    queryKey: ['planner', 'longTailStrategies', 'forBacklog'],
    queryFn: () => fetchLongTailStrategies(),
    enabled: status === 'do_not_model',
    staleTime: 60_000,
  })
  const strategyOptions = useMemo(
    () =>
      (strategiesQuery.data?.items ?? [])
        .filter((s) => s.enabled)
        .map((s) => ({
          label: `${s.category}  ·  ${(s.rate * 100).toFixed(2)}%`,
          value: s.category,
        })),
    [strategiesQuery.data?.items],
  )

  const openCategoryEditor = (skuCodes: string[]) => {
    if (!skuCodes.length) {
      message.info('请先选择行')
      return
    }
    setCategoryEditorTargets(skuCodes)
    categoryEditorForm.resetFields()
    // Pre-fill if all selected SKUs already share the same category.
    const currentCategories = new Set(
      skuCodes
        .map((c) => items.find((it) => it.erp_sku_barcode === c)?.long_tail_category)
        .filter((v): v is string => Boolean(v)),
    )
    if (currentCategories.size === 1) {
      categoryEditorForm.setFieldsValue({ category: Array.from(currentCategories)[0] })
    }
    setCategoryEditorOpen(true)
  }

  const autoPreviewMutation = useMutation({
    mutationFn: () => autoSuggestLongTailCategoryPreview({ limit: 5000 }),
    onSuccess: (data) => {
      setAutoPreview(data)
      setAutoSelectedKeys(data.suggested.map((it) => it.sku_code))
      setAutoDrawerOpen(true)
    },
    onError: (err: any) => {
      const detail = err?.response?.data?.detail
      message.error(typeof detail === 'string' ? detail : '扫描失败')
    },
  })

  const autoExecuteMutation = useMutation({
    mutationFn: (sku_codes?: string[]) =>
      autoSuggestLongTailCategoryExecute({
        sku_codes,
        limit: 5000,
        actor: 'governance-tab-auto',
      }),
    onSuccess: (data) => {
      const errors = data.apply_results.filter((r) => r.error)
      if (errors.length) {
        message.warning(
          `已应用 ${data.applied} 条，但有 ${errors.length} 个品类失败：${errors
            .map((e) => `${e.category}:${e.error}`)
            .join('; ')}`,
        )
      } else {
        message.success(
          `✅ 自动标完成：applied=${data.applied}，scanned=${data.scanned}，no_match=${data.no_match_count}`,
        )
      }
      setAutoDrawerOpen(false)
      setAutoPreview(null)
      setAutoSelectedKeys([])
      query.refetch()
    },
    onError: (err: any) => {
      const detail = err?.response?.data?.detail
      message.error(typeof detail === 'string' ? detail : '执行失败')
    },
  })

  const handleSubmitCategory = async (clearOnly = false) => {
    const values = clearOnly
      ? { category: '', note: '清除人工品类标注' }
      : await categoryEditorForm.validateFields()
    try {
      const res = await setSkuLongTailCategory({
        sku_codes: categoryEditorTargets,
        category: clearOnly ? '' : (values.category || '').trim(),
        actor: 'governance-tab',
        note: values.note?.trim() || undefined,
      })
      const action = clearOnly ? '清除' : '标注'
      message.success(
        `${action}完成：updated=${res.updated}, cleared=${res.cleared}, unchanged=${res.unchanged}, missing=${res.missing}`,
      )
      setCategoryEditorOpen(false)
      setCategoryEditorTargets([])
      setSelectedRowKeys([])
      query.refetch()
    } catch (err: any) {
      const detail = err?.response?.data?.detail
      message.error(typeof detail === 'string' ? detail : '保存失败')
    }
  }

  const handlePromoteOrRevert = async (
    skuCodes: string[],
    target: SkuGovernanceStatus,
    label: string,
  ) => {
    if (!skuCodes.length) {
      message.info('请选择至少一行')
      return
    }
    try {
      const res = await setSkuGovernance({
        sku_codes: skuCodes,
        status: target,
        decided_by: 'governance-tab',
        note: `${label} from GovernanceBacklogTab`,
      })
      message.success(
        `${label}完成：updated=${res.updated}, unchanged=${res.unchanged}, missing=${res.missing}`,
      )
      query.refetch()
    } catch (err: any) {
      message.error(`${label}失败：${err?.response?.data?.detail ?? err?.message ?? 'unknown'}`)
    }
  }

  const columns: ColumnsType<SkuGovernanceListItem> = [
    { title: 'SKU 条码', dataIndex: 'erp_sku_barcode', width: 180, fixed: 'left' as const },
    {
      title: '规格',
      dataIndex: 'spec_text',
      ellipsis: true,
      render: (v) => (v ? <Text ellipsis={{ tooltip: safeString(v) }}>{safeString(v)}</Text> : '-'),
    },
    { title: '渠道', dataIndex: 'channel', width: 120 },
    {
      title: '治理状态',
      dataIndex: 'governance_status',
      width: 120,
      render: (v: SkuGovernanceStatus) => {
        const map: Record<SkuGovernanceStatus, { color: string; label: string }> = {
          unmanaged: { color: 'default', label: '未治理' },
          auto_bound: { color: 'green', label: '已绑定' },
          pending_model: { color: 'gold', label: '建模中' },
          do_not_model: { color: 'purple', label: '长尾' },
        }
        const m = map[v] ?? { color: 'default', label: safeString(v) }
        return <Tag color={m.color}>{m.label}</Tag>
      },
    },
    {
      title: `${salesWindowDays}天销售额`,
      dataIndex: 'revenue_window',
      width: 130,
      align: 'right' as const,
      sorter: (a, b) => (a.revenue_window ?? 0) - (b.revenue_window ?? 0),
      render: (v: number) => (
        <Tooltip title="按 ShipmentLine.revenue_amount 累加，作为建模优先级参考">
          <Text strong>{formatNumber(v)}</Text>
        </Tooltip>
      ),
    },
    {
      title: `${salesWindowDays}天件数`,
      dataIndex: 'qty_window',
      width: 110,
      align: 'right' as const,
      render: (v: number) => formatNumber(v),
    },
    {
      title: `${salesWindowDays}天发货行`,
      dataIndex: 'line_count_window',
      width: 110,
      align: 'right' as const,
      render: (v: number) => formatNumber(v),
    },
    {
      title: '最近发货',
      dataIndex: 'last_shipment_at',
      width: 160,
      render: (v) => formatTime(v),
    },
    {
      title: '决策人',
      dataIndex: 'governance_decided_by',
      width: 120,
      render: (v) => safeString(v) || '-',
    },
    {
      title: '决策时间',
      dataIndex: 'governance_decided_at',
      width: 160,
      render: (v) => formatTime(v),
    },
    {
      title: '操作',
      key: 'actions',
      width: status === 'do_not_model' ? 220 : 220,
      fixed: 'right' as const,
      align: 'right' as const,
      render: (_v, r) => {
        if (status === 'pending_model') {
          return (
            <Space wrap>
              <Button
                type="primary"
                size="small"
                onClick={() =>
                  navigate(
                    `/costing/product-models/new?from_sku=${encodeURIComponent(
                      r.erp_sku_barcode,
                    )}&prefill_spec=${encodeURIComponent(safeString(r.spec_text))}`,
                  )
                }
              >
                {primaryActionLabel ?? '立即建模'}
              </Button>
              <Button
                size="small"
                onClick={() => handlePromoteOrRevert([r.erp_sku_barcode], 'unmanaged', '撤回')}
              >
                撤回
              </Button>
            </Space>
          )
        }
        if (status === 'do_not_model') {
          return (
            <Space wrap>
              <Tooltip title="人工指定长尾品类，覆盖关键字匹配；优先级最高">
                <Button
                  size="small"
                  type={r.long_tail_category ? 'default' : 'primary'}
                  onClick={() => openCategoryEditor([r.erp_sku_barcode])}
                >
                  {r.long_tail_category ? '改品类' : '📂 标品类'}
                </Button>
              </Tooltip>
              <Button
                size="small"
                onClick={() => handlePromoteOrRevert([r.erp_sku_barcode], 'unmanaged', '撤回长尾标记')}
              >
                撤回长尾
              </Button>
            </Space>
          )
        }
        return null
      },
    },
  ]

  // Issue 28 follow-up: insert "当前品类" column right before 操作 (only on
  // the do_not_model tab so the modeling backlog stays uncluttered).
  if (status === 'do_not_model') {
    const insertAt = columns.findIndex((c) => (c as any).key === 'actions')
    columns.splice(insertAt >= 0 ? insertAt : columns.length, 0, {
      title: '当前品类',
      key: 'long_tail_category',
      dataIndex: 'long_tail_category',
      width: 140,
      render: (v: string | null | undefined, r: SkuGovernanceListItem) => {
        if (!v) return <Text type="secondary">— (走关键字/默认)</Text>
        return (
          <Tooltip
            title={
              r.long_tail_category_decided_by
                ? `${r.long_tail_category_decided_by} · ${formatTime(r.long_tail_category_decided_at)}`
                : formatTime(r.long_tail_category_decided_at)
            }
          >
            <Tag color="gold">{v}</Tag>
          </Tooltip>
        )
      },
    } as any)
  }

  return (
    <Card
      size="small"
      title={
        status === 'pending_model'
          ? '建模 Backlog（按销售额优先级）'
          : status === 'do_not_model'
            ? '长尾 SKU（不建模 · 可撤回）'
            : 'SKU 治理列表'
      }
      extra={
        <Space wrap>
          {status === 'do_not_model' && (
            <Tooltip title="按策略表关键字扫描整个长尾池, 给未标过的 SKU 推荐 long_tail_category。先看候选, 再决定是否一键应用。">
              <Button
                type="primary"
                onClick={() => autoPreviewMutation.mutate()}
                loading={autoPreviewMutation.isPending}
              >
                ⚡ 一键自动标品类
              </Button>
            </Tooltip>
          )}
          <Input
            style={{ width: 200 }}
            placeholder="搜索条码/规格/渠道"
            allowClear
            value={searchKeyword}
            onChange={(e) => setSearchKeyword(e.target.value)}
          />
          <Segmented
            value={orderBy}
            onChange={(v) => setOrderBy(v as any)}
            options={[
              { label: '按销售额', value: 'shipment_score' },
              { label: '按最近发货', value: 'last_shipment_at' },
              { label: '按更新', value: 'updated_at' },
            ]}
          />
          <Segmented
            value={String(salesWindowDays)}
            onChange={(v) => setSalesWindowDays(Number(v))}
            options={[
              { label: '7天', value: '7' },
              { label: '30天', value: '30' },
              { label: '90天', value: '90' },
            ]}
          />
          <Button onClick={() => query.refetch()} loading={query.isFetching}>
            刷新
          </Button>
        </Space>
      }
    >
      {status === 'do_not_model' && selectedRowKeys.length > 0 && (
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 8 }}
          message={
            <Space wrap>
              <Text strong>已选 {selectedRowKeys.length} 条</Text>
              <Button
                size="small"
                type="primary"
                onClick={() => openCategoryEditor(selectedRowKeys.map(String))}
              >
                📂 批量标品类
              </Button>
              <Button size="small" onClick={() => setSelectedRowKeys([])}>
                取消选择
              </Button>
            </Space>
          }
        />
      )}

      <Table
        rowKey="erp_sku_barcode"
        size="small"
        scroll={{ x: 1500 }}
        loading={query.isFetching}
        columns={columns}
        dataSource={items}
        rowSelection={
          status === 'do_not_model'
            ? {
                selectedRowKeys,
                onChange: (keys) => setSelectedRowKeys(keys),
                preserveSelectedRowKeys: true,
              }
            : undefined
        }
        pagination={{
          current: page,
          pageSize: pageSize,
          total: query.data?.total ?? 0,
          showSizeChanger: true,
          onChange: (p, ps) => {
            setPage(p)
            setPageSize(ps)
          },
        }}
      />

      <Modal
        open={categoryEditorOpen}
        title={
          categoryEditorTargets.length === 1
            ? `📂 标品类：${categoryEditorTargets[0]}`
            : `📂 批量标品类（${categoryEditorTargets.length} 条）`
        }
        onCancel={() => setCategoryEditorOpen(false)}
        footer={[
          <Button key="cancel" onClick={() => setCategoryEditorOpen(false)}>
            取消
          </Button>,
          <Button
            key="clear"
            danger
            onClick={() => handleSubmitCategory(true)}
            disabled={!categoryEditorTargets.length}
          >
            清除标注
          </Button>,
          <Button
            key="ok"
            type="primary"
            onClick={() => handleSubmitCategory(false)}
            disabled={!categoryEditorTargets.length}
          >
            保存
          </Button>,
        ]}
        destroyOnClose
      >
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 12 }}
          message={
            <span>
              人工指定后将覆盖关键字匹配，长尾兜底快照按此品类的 rate 计算。
              品类来自{' '}
              <a onClick={() => navigate('/costing/admin/long-tail-cogs-rate')}>
                💰 长尾成本策略
              </a>
              ，没有可选项时请先去那里建。
            </span>
          }
        />
        <Form form={categoryEditorForm} layout="vertical" preserve={false}>
          <Form.Item
            name="category"
            label="目标品类"
            rules={[{ required: true, message: '请选择品类（或点"清除标注"撤销）' }]}
          >
            <Select
              showSearch
              placeholder="选择品类（来自策略表 enabled 项）"
              options={strategyOptions}
              loading={strategiesQuery.isLoading}
              optionFilterProp="label"
              notFoundContent={
                strategyOptions.length === 0
                  ? '策略表为空，请先去 💰 长尾成本策略页新建'
                  : undefined
              }
            />
          </Form.Item>
          <Form.Item name="note" label="备注（可选）">
            <Input.TextArea rows={2} placeholder="例：北欧装饰画系列，整批走画框策略" />
          </Form.Item>
        </Form>
      </Modal>

      <Drawer
        open={autoDrawerOpen}
        onClose={() => setAutoDrawerOpen(false)}
        width={Math.min(960, typeof window !== 'undefined' ? window.innerWidth - 80 : 960)}
        title="⚡ 一键自动标品类 — 候选清单"
        extra={
          <Space>
            <Popconfirm
              title="确认应用所有勾选项？"
              description={`共 ${autoSelectedKeys.length} 条 → 写入 metadata.long_tail_category, 老快照不会受影响。`}
              okText="一键应用"
              cancelText="取消"
              disabled={autoSelectedKeys.length === 0 || autoExecuteMutation.isPending}
              onConfirm={() => {
                const allSelected =
                  autoSelectedKeys.length === (autoPreview?.suggested.length ?? 0)
                autoExecuteMutation.mutate(
                  allSelected ? undefined : autoSelectedKeys.map(String),
                )
              }}
            >
              <Button
                type="primary"
                disabled={autoSelectedKeys.length === 0}
                loading={autoExecuteMutation.isPending}
              >
                ✅ 应用 {autoSelectedKeys.length}/{autoPreview?.suggested.length ?? 0} 条
              </Button>
            </Popconfirm>
          </Space>
        }
      >
        {autoPreview?.reason === 'no enabled strategies' && (
          <Alert
            type="warning"
            showIcon
            message="策略表为空"
            description={
              <span>
                请先去{' '}
                <a onClick={() => navigate('/costing/admin/long-tail-cogs-rate')}>
                  💰 长尾成本策略
                </a>{' '}
                建几条带 keywords 的策略，再来扫。
              </span>
            }
          />
        )}
        {autoPreview && autoPreview.reason !== 'no enabled strategies' && (
          <>
            <Space size="large" style={{ marginBottom: 12 }} wrap>
              <Statistic title="本次扫描" value={autoPreview.scanned} suffix="条" />
              <Statistic
                title="可推荐"
                value={autoPreview.suggested.length}
                valueStyle={{ color: '#52c41a' }}
                suffix="条"
              />
              <Statistic
                title="跳过(已手动标过)"
                value={autoPreview.already_labeled_skipped}
                suffix="条"
              />
              <Statistic
                title="无关键字命中"
                value={autoPreview.no_match_count}
                valueStyle={{ color: autoPreview.no_match_count > 0 ? '#faad14' : undefined }}
                suffix="条"
              />
            </Space>
            {autoPreview.limited && (
              <Alert
                type="info"
                showIcon
                style={{ marginBottom: 12 }}
                message={`本次只扫描了 ${autoPreview.scanned} 条(达到 limit), 应用后再次扫描可继续处理剩余的`}
              />
            )}
            {autoPreview.suggested.length === 0 && (
              <Alert
                type="success"
                showIcon
                message="🎉 没有可推荐的项 — 所有长尾 SKU 要么已标, 要么策略关键字命中不到"
                description="如果想覆盖更多, 去 💰 长尾成本策略 给现有品类加更多 keywords; 或新建品类策略。"
              />
            )}
            <Table
              size="small"
              rowKey="sku_code"
              scroll={{ x: 1100, y: 480 }}
              dataSource={autoPreview.suggested}
              rowSelection={{
                selectedRowKeys: autoSelectedKeys,
                onChange: setAutoSelectedKeys,
                preserveSelectedRowKeys: true,
              }}
              pagination={{ pageSize: 50, showSizeChanger: true }}
              columns={[
                { title: 'SKU 条码', dataIndex: 'sku_code', width: 160, fixed: 'left' as const },
                {
                  title: '当前',
                  dataIndex: 'current_category',
                  width: 100,
                  render: (v: string | null) => (v ? <Tag>{v}</Tag> : <Text type="secondary">—</Text>),
                },
                {
                  title: '推荐品类',
                  dataIndex: 'suggested_category',
                  width: 130,
                  render: (v: string, r: LongTailCategoryAutoSuggestItem) => (
                    <Tooltip title={`rate ${(r.strategy_rate * 100).toFixed(2)}%`}>
                      <Tag color="gold">{v}</Tag>
                    </Tooltip>
                  ),
                },
                {
                  title: '命中关键字',
                  dataIndex: 'matched_keyword',
                  width: 130,
                  render: (v: string) => <Tag color="blue">{v}</Tag>,
                },
                {
                  title: 'rate',
                  dataIndex: 'strategy_rate',
                  width: 80,
                  align: 'right' as const,
                  render: (v: number) => (
                    <Text style={{ fontFamily: 'monospace' }}>{(v * 100).toFixed(2)}%</Text>
                  ),
                },
                {
                  title: '规格 / 商品名',
                  key: 'haystack',
                  ellipsis: true,
                  render: (_: unknown, r: LongTailCategoryAutoSuggestItem) => (
                    <Text ellipsis={{ tooltip: `${r.spec_text || ''} | ${r.product_name || ''}` }}>
                      {r.spec_text || r.product_name || '—'}
                    </Text>
                  ),
                },
              ]}
            />
          </>
        )}
      </Drawer>
    </Card>
  )
}
