import { useEffect, useMemo, useState } from 'react'
import dayjs from 'dayjs'
import { Button, Card, Col, Input, Modal, Row, Select, Space, Switch, Table, Tag, Tooltip, Typography, message } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useQuery } from '@tanstack/react-query'
import { useLocation, useNavigate } from 'react-router-dom'

import {
  createProductModel,
  fetchProductModelVersions,
  fetchProductModels,
  previewProductModel,
  fetchTaxonomyItems,
  archiveStandardVersionsOnly,
} from '@/services/planner'
import type { ProductModel } from '@/types/planner'
import ProductModelEditorDrawer from '@/components/costing/ProductModelEditorDrawer'

const { Title, Text } = Typography

const KEYWORD_COLOR_PALETTE = [
  '#1677ff', // blue
  '#52c41a', // green
  '#faad14', // gold
  '#722ed1', // purple
  '#eb2f96', // magenta
  '#13c2c2', // cyan
  '#fa541c', // volcano
  '#2f54eb', // geekblue
  '#a0d911', // lime
  '#f5222d', // red
] as const

const hashToIndex = (s: string, mod: number) => {
  let h = 0
  for (let i = 0; i < s.length; i += 1) h = (h * 31 + s.charCodeAt(i)) >>> 0
  return mod === 0 ? 0 : h % mod
}

const getKeywordColor = (keyword?: string | null) => {
  const key = String(keyword ?? '').trim() || 'keyword'
  const idx = hashToIndex(key, KEYWORD_COLOR_PALETTE.length)
  return KEYWORD_COLOR_PALETTE[idx]
}

const KeywordPill = ({ keyword }: { keyword: string }) => {
  const k = String(keyword ?? '').trim()
  const color = getKeywordColor(k)
  return (
    <span
      style={{
        display: 'inline-block',
        padding: '1px 8px',
        borderRadius: 999,
        border: `1px solid ${color}55`,
        background: `${color}22`,
        color,
        fontSize: 12,
        lineHeight: '18px',
        whiteSpace: 'nowrap',
      }}
    >
      {k}
    </span>
  )
}

export default function StandardModelsPage() {
  const location = useLocation() as any
  const navigate = useNavigate()
  const [search, setSearch] = useState('')
  const [category, setCategory] = useState<string | undefined>(undefined)
  const [includeArchived, setIncludeArchived] = useState(false)
  const [page] = useState(1)
  const [pageSize] = useState(50)

  const [editorOpen, setEditorOpen] = useState(false)
  const [editingModelId, setEditingModelId] = useState<string | null>(null)
  const [editingVersionId, setEditingVersionId] = useState<string | null>(null)
  const [createModalOpen, setCreateModalOpen] = useState(false)
  const [createName, setCreateName] = useState<string>('未命名标准模型')
  const [creating, setCreating] = useState(false)

  const [auditingModelIds, setAuditingModelIds] = useState<Record<string, boolean>>({})
  const [auditResultByModelId, setAuditResultByModelId] = useState<
    Record<
      string,
      {
        baseline_total?: number
        realtime_total?: number
        diff_percent?: number
        checked_at?: string
        error?: string
      }
    >
  >({})

  useEffect(() => {
    const st = (location as any)?.state ?? {}
    const openModelId = String(st?.openModelId ?? '').trim()
    const openVersionId = String(st?.openVersionId ?? '').trim()
    if (!openModelId || !openVersionId) return

    setEditingModelId(openModelId)
    setEditingVersionId(openVersionId)
    setEditorOpen(true)
    // 清掉 state，避免刷新/返回时重复弹抽屉
    navigate(location.pathname, { replace: true, state: null })
  }, [location, navigate])

  const params = useMemo(
    () => ({
      search: search || undefined,
      category: category || undefined,
      include_archived: includeArchived || undefined,
      page,
      page_size: pageSize,
    }),
    [category, includeArchived, page, pageSize, search],
  )

  const listQuery = useQuery({
    queryKey: ['standardModels', params],
    queryFn: () => fetchProductModels(params as any),
  })

  const taxonomyCategoryQuery = useQuery({
    queryKey: ['taxonomy-items', 'product_model_category', 'standard-models'],
    queryFn: () => fetchTaxonomyItems('product_model_category', { include_inactive: true }),
  })

  const listItems = useMemo(() => {
    // 标准列表：为了“可见即可删/可见可查”，不再做 entry_context/版本数过滤（需要时可打开“显示已归档”）。
    return ((((listQuery.data as any)?.items ?? []) as any[]) || []).slice()
  }, [listQuery.data])

  const getBaselineTotalFromPublished = async (modelId: string, publishedVersionId: string) => {
    const versions = await fetchProductModelVersions(modelId)
    const v = versions.find((x) => x.id === publishedVersionId)
    const meta: any = (v as any)?.metadata_json ?? (v as any)?.metadata ?? {}
    const ui = meta?.ui_stats ?? {}
    const total = Number(ui.total_cost ?? ui.total ?? NaN)
    if (Number.isFinite(total) && total > 0) {
      return total
    }
    const material = Number(ui.material_cost ?? 0)
    const labor = Number(ui.labor_cost ?? 0)
    const mf = Number(ui.manufacturing_fee ?? ui.overhead_cost ?? 0)
    const sum = material + labor + mf
    return Number.isFinite(sum) && sum > 0 ? sum : undefined
  }

  const handleRealtimeAudit = async (model: ProductModel) => {
    const modelId = model.id
    if (auditingModelIds[modelId]) return
    const publishedVersionId = (model as any).current_published_standard_version_id
    if (!publishedVersionId) {
      message.warning('该模型暂无“已发布”标准版本，无法核价')
      return
    }

    setAuditingModelIds((prev) => ({ ...prev, [modelId]: true }))
    try {
      const baselineTotal = await getBaselineTotalFromPublished(modelId, String(publishedVersionId))
      if (!baselineTotal) {
        throw new Error('未找到发布版本的基准价（version.metadata_json.ui_stats.total_cost）')
      }

      // 标准核价口径：默认使用 100×100cm×1（= 1000mm×1000mm×1）
      const widthMm = Number((model as any).standard_width_mm ?? 1000)
      const heightMm = Number((model as any).standard_height_mm ?? 1000)
      const preview = await previewProductModel(modelId, {
        width_mm: widthMm,
        height_mm: heightMm,
        quantity: 1,
      } as any)

      const realtimeTotal = Number((preview as any)?.totals?.total_cost ?? NaN)
      if (!Number.isFinite(realtimeTotal)) {
        throw new Error('实时核价失败：preview 返回 totals.total_cost 缺失')
      }
      const diffPercent = ((realtimeTotal - baselineTotal) / baselineTotal) * 100
      setAuditResultByModelId((prev) => ({
        ...prev,
        [modelId]: {
          baseline_total: baselineTotal,
          realtime_total: realtimeTotal,
          diff_percent: diffPercent,
          checked_at: new Date().toISOString(),
        },
      }))
      message.success('实时核价完成')
    } catch (err: any) {
      setAuditResultByModelId((prev) => ({
        ...prev,
        [modelId]: {
          ...prev[modelId],
          error: err?.message || String(err),
          checked_at: new Date().toISOString(),
        },
      }))
      message.error(err?.message || '实时核价失败')
    } finally {
      setAuditingModelIds((prev) => ({ ...prev, [modelId]: false }))
    }
  }

  const handleDeleteModel = async (model: ProductModel) => {
    Modal.confirm({
      title: '删除模型',
      content: `确认删除（归档）标准版本：${model.model_code} - ${model.model_name}？（不会影响打样版本）`,
      okText: '删除标准',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        try {
          // 标准入口的“删除”口径：仅归档 standard 版本；若模型没有任何剩余版本，再归档模型本身
          // 目的：确保“删除标准模型”不会误伤同一 model 下的打样版本（sample）。
          await archiveStandardVersionsOnly(model.id)
          message.success('已删除标准（归档标准版本）')
          await listQuery.refetch()
        } catch (err: any) {
          message.error(err?.response?.data?.detail ?? err?.message ?? '删除失败')
        }
      },
    })
  }

  const columns: ColumnsType<ProductModel> = [
    { title: '总编码', dataIndex: 'model_code', width: 120 },
    { title: '品类', dataIndex: 'category', width: 70, render: (v: any) => String(v ?? '').trim() || '-' },
    { title: '模型名称', dataIndex: 'model_name', width: 160 },
    {
      title: '货品映射',
      width: 420,
      render: (_: any, r: any) => {
        const meta: any = (r as any)?.metadata_json ?? {}
        const raw = Array.isArray(meta?.recognition_keywords) ? meta.recognition_keywords : []
        const keywords = raw
          .map((x: any) => String(x ?? '').trim())
          .filter((x: string) => x)
        // de-dup preserve order
        const seen = new Set<string>()
        const uniq: string[] = []
        for (const k of keywords) {
          if (seen.has(k)) continue
          seen.add(k)
          uniq.push(k)
        }
        if (!uniq.length) return <Text type="secondary">-</Text>

        const show = uniq.slice(0, 3)
        const rest = uniq.length - show.length
        const content = (
          <Space size={6} wrap>
            {show.map((k) => (
              <KeywordPill key={k} keyword={k} />
            ))}
            {rest > 0 ? <Tag style={{ borderRadius: 999 }}>+{rest}</Tag> : null}
          </Space>
        )

        if (rest <= 0) return content
        return (
          <Tooltip
            getPopupContainer={() => document.body}
            title={
              <Space size={6} wrap>
                {uniq.map((k) => (
                  <KeywordPill key={k} keyword={k} />
                ))}
              </Space>
            }
          >
            {content}
          </Tooltip>
        )
      },
    },
    { title: '打样版本数', width: 110, render: (_: any, r: any) => (r.sample_version_count ?? '-') },
    { title: '标准版本数', width: 110, render: (_, r) => (r.standard_version_count ?? '-') },
    {
      title: '当前发布标准',
      width: 140,
      render: (_: any, r: any) => {
        const v = String(r.current_published_standard_version_label ?? '').trim()
        if (!v) return <Text type="secondary">-</Text>
        return (
          <span
            style={{
              display: 'inline-block',
              padding: '0px 6px',
              borderRadius: 6,
              border: '1px solid #d9d9d9',
              background: '#fafafa',
              fontSize: 11,
              lineHeight: '18px',
              color: '#595959',
              whiteSpace: 'nowrap',
            }}
          >
            {v}
          </span>
        )
      },
    },
    {
      title: '核价偏差',
      width: 140,
      render: (_, r) => {
        const audit = auditResultByModelId[r.id]
        if (!audit) return <Tag>-</Tag>
        if (audit.error) {
          return (
            <Tooltip title={audit.error}>
              <Tag color="red">失败</Tag>
            </Tooltip>
          )
        }
        const diff = audit.diff_percent
        if (diff === undefined || diff === null || !Number.isFinite(diff)) return <Tag>-</Tag>
        const abs = Math.abs(diff)
        const warn = abs >= 5
        const text = `${diff >= 0 ? '+' : ''}${diff.toFixed(1)}%`
        return <Tag color={warn ? 'red' : 'green'}>{warn ? `预警 ${text}` : text}</Tag>
      },
    },
    {
      title: '更新时间',
      dataIndex: 'updated_at',
      width: 170,
      render: (v: any) => {
        const s = String(v ?? '').trim()
        if (!s) return '-'
        const d = dayjs(s)
        return d.isValid() ? d.format('YYYY-MM-DD HH:mm') : s
      },
    },
    {
      title: '操作',
      width: 260,
      render: (_, r) => (
        <Space>
          <Button
            type="primary"
            onClick={() => {
              setEditingModelId(r.id)
              setEditingVersionId(null)
              setEditorOpen(true)
            }}
          >
            编辑
          </Button>
          <Button loading={Boolean(auditingModelIds[r.id])} onClick={() => handleRealtimeAudit(r)}>
            实时核价
          </Button>
          <Tooltip title="删除为“归档删除标准版本（不影响打样版本）”。规则：存在已发布标准版本或存在SKU绑定则不允许删除；否则允许删除标准版本。">
            <Button
              danger
              disabled={Boolean((r as any).current_published_standard_version_id)}
              onClick={() => handleDeleteModel(r)}
            >
              删除
            </Button>
          </Tooltip>
        </Space>
      ),
    },
  ]

  const handleGuideToDerive = () => {
    Modal.info({
      title: '推荐做法：从打样推导标准模型',
      content: (
        <div>
          <div style={{ marginBottom: 8 }}>
            标准模型建议由打样版本推导生成，避免直接新建造成口径不一致。
          </div>
          <div style={{ marginBottom: 8 }}>
            操作路径：进入“打样模型” → 进入打样管理 → 选择打样版本 → 点击“推导标准模型”。
          </div>
        </div>
      ),
      okText: '前往打样模型',
      onOk: () => navigate('/costing/sample-models'),
    })
  }

  const handleCreateStandardDirect = async () => {
    if (creating) return
    const name = String(createName || '').trim()
    if (!name) {
      message.warning('请输入模型名称')
      return
    }
    setCreating(true)
    try {
      const model = await createProductModel({
        model_name: name,
        metadata_json: { created_from: 'ui', entry_context: 'standard', note: 'direct_create_standard' },
      })
      // 兼容：后端可能返回 metadata_json 或 metadata（不同 Pydantic by_alias 行为/历史兼容）
      let draftId = String(
        (model as any)?.metadata_json?.current_draft_version_id ??
          (model as any)?.metadata?.current_draft_version_id ??
          '',
      ).trim()
      if (!draftId) {
        // 兜底：若未回传 current_draft_version_id，则主动拉取版本列表并选择 standard draft
        try {
          const versions = await fetchProductModelVersions(model.id)
          const standardDraft =
            versions.find((v: any) => v?.version_kind === 'standard' && v?.version_status === 'draft') ??
            versions.find((v: any) => v?.version_kind === 'standard')
          draftId = String(standardDraft?.id ?? '').trim()
        } catch {
          // ignore: keep draftId empty, will still open drawer with modelId only
        }
      }
      message.success(`已创建标准模型：${model.model_code}`)
      setCreateModalOpen(false)
      setEditingModelId(model.id)
      setEditingVersionId(draftId || null)
      setEditorOpen(true)
      // 列表刷新失败不应覆盖“创建成功”的反馈（避免出现“已创建但提示失败”的误报）
      try {
        await listQuery.refetch()
      } catch {
        // ignore
      }
    } catch (err: any) {
      message.error(err?.response?.data?.detail ?? err?.message ?? '新建标准模型失败')
    } finally {
      setCreating(false)
    }
  }

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between' }}>
        <div>
          <Title level={3} style={{ marginBottom: 4 }}>
            标准模型
          </Title>
          <Text type="secondary">标准模型以“标准版本（100×100cm×1）”为核算单元，支持发布与SKU绑定。</Text>
        </div>
      </div>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} lg={12}>
          <Card size="small" title="筛选">
            <Space wrap>
              <Input.Search
                allowClear
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                onSearch={() => listQuery.refetch()}
                placeholder="搜索三位编码 / 模型名 / 版本号"
                style={{ width: 420 }}
              />
              <Select
                allowClear
                showSearch
                optionFilterProp="label"
                placeholder="品类"
                style={{ width: 200 }}
                value={category}
                onChange={(v) => setCategory(v ?? undefined)}
                options={(taxonomyCategoryQuery.data?.items ?? []).map((it: any) => ({ label: it.name, value: it.name }))}
              />
              <Space size={6}>
                <Switch checked={includeArchived} onChange={setIncludeArchived} />
                <Text type="secondary">显示已归档</Text>
              </Space>
            </Space>
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card size="small" title="操作">
            <Space wrap>
              <Button type="primary" onClick={handleGuideToDerive}>
                从打样推导（推荐）
              </Button>
              <Button onClick={() => setCreateModalOpen(true)}>直接新建标准（高级）</Button>
              <Button onClick={() => listQuery.refetch()}>刷新</Button>
            </Space>
          </Card>
        </Col>

        <Col span={24}>
          <Card>
            <Table
              rowKey={(r) => r.id}
              loading={listQuery.isLoading}
              dataSource={listItems as ProductModel[]}
              columns={columns}
              pagination={false}
              scroll={{ x: 980 }}
            />
          </Card>
        </Col>
      </Row>

      <Modal
        title="直接新建标准模型（高级）"
        open={createModalOpen}
        okText="创建并进入"
        cancelText="取消"
        confirmLoading={creating}
        onOk={handleCreateStandardDirect}
        onCancel={() => {
          if (creating) return
          setCreateModalOpen(false)
        }}
      >
        <Space direction="vertical" style={{ width: '100%' }}>
          <Input value={createName} onChange={(e) => setCreateName(e.target.value)} placeholder="模型名称（必填）" />
          <Text type="secondary">
            注意：专业建议走“从打样推导”。仅在明确无需打样口径/模板推导时，才使用直接新建。
          </Text>
        </Space>
      </Modal>

      <ProductModelEditorDrawer
        open={editorOpen}
        onClose={() => setEditorOpen(false)}
        entryContext="standard"
        modelId={editingModelId}
        initialVersionId={editingVersionId}
        includeArchived={includeArchived}
      />
    </div>
  )
}













