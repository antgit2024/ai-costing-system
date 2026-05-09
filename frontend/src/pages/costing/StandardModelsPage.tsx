import { useEffect, useMemo, useState } from 'react'
import { Button, Card, Col, Input, Modal, Row, Select, Space, Switch, Table, Tag, Tooltip, Typography, message } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useQuery } from '@tanstack/react-query'
import { useLocation, useNavigate } from 'react-router-dom'
import { DeleteOutlined, EditOutlined, ThunderboltOutlined } from '@ant-design/icons'

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
import { formatBeijingTime } from '@/utils/beijingTime'

const { Title, Text } = Typography

// 使用 antd 主题色变量（避免硬编码亮色；暗色主题下也更柔和）
const KEYWORD_TONE_PALETTE = [
  'var(--ant-color-primary)',
  'var(--ant-color-success)',
  'var(--ant-color-warning)',
  'var(--ant-color-error)',
  'var(--ant-color-info)',
  'var(--ant-color-link)',
] as const

const hashToIndex = (s: string, mod: number) => {
  let h = 0
  for (let i = 0; i < s.length; i += 1) h = (h * 31 + s.charCodeAt(i)) >>> 0
  return mod === 0 ? 0 : h % mod
}

const getKeywordTone = (keyword?: string | null) => {
  const key = String(keyword ?? '').trim() || 'keyword'
  const idx = hashToIndex(key, KEYWORD_TONE_PALETTE.length)
  return KEYWORD_TONE_PALETTE[idx]
}

const KeywordPill = ({ keyword }: { keyword: string }) => {
  const k = String(keyword ?? '').trim()
  const tone = getKeywordTone(k)
  return (
    <span
      style={{
        display: 'inline-block',
        padding: '1px 8px',
        borderRadius: 999,
        border: '1px solid var(--ant-color-border)',
        // fallback (no color-mix support)
        backgroundColor: 'var(--ant-color-fill-tertiary)',
        // tinted when supported
        background: `color-mix(in srgb, ${tone} 18%, var(--ant-color-fill-tertiary))`,
        borderColor: `color-mix(in srgb, ${tone} 45%, var(--ant-color-border))`,
        color: 'var(--ant-color-text-secondary)',
        fontSize: 11, // 字体缩小一号
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
  const [mappingSearch, setMappingSearch] = useState('')
  const [category, setCategory] = useState<string | undefined>(undefined)
  const [includeArchived, setIncludeArchived] = useState(false)
  const [page] = useState(1)
  // NOTE: 标准模型页会先拉取“全部主模型”再按“标准入口/存在标准版本/有发布标准”做前端过滤。
  // page_size 过小会导致满足条件的模型在分页阶段被截掉（曾经 50 时只显示 1 条 YS2）。
  // 这里直接使用后端上限 200；若未来主模型总数超过 200，需要改为后端按 version_kind/entry_context 过滤。
  const [pageSize] = useState(200)

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
    // 标准列表：只展示“标准入口”或“存在标准版本”的模型。
    // 目的：确保打样模型不会“自动出现在标准模型列表”，只有推导/创建过标准版本才会出现。
    const raw = ((((listQuery.data as any)?.items ?? []) as any[]) || []).slice()
    return raw.filter((r: any) => {
      const meta: any = r?.metadata_json ?? {}
      const entry = String(meta?.entry_context ?? '').trim().toLowerCase()
      const stdCnt = Number((r as any)?.standard_version_count ?? 0)
      const hasPublishedStd = Boolean((r as any)?.current_published_standard_version_id)
      return entry === 'standard' || (Number.isFinite(stdCnt) && stdCnt > 0) || hasPublishedStd
    })
  }, [listQuery.data])

  const filteredItems = useMemo(() => {
    const q = String(mappingSearch || '').trim()
    if (!q) return listItems
    const terms = q
      .split(/[\s,，;；/|]+/g)
      .map((x) => x.trim())
      .filter(Boolean)
    if (!terms.length) return listItems

    return (listItems as any[]).filter((r: any) => {
      const meta: any = r?.metadata_json ?? {}
      const raw = Array.isArray(meta?.recognition_keywords) ? meta.recognition_keywords : []
      const kws = raw
        .map((x: any) => String(x ?? '').trim())
        .filter((x: string) => x)
      const hay = kws.join(' ').toLowerCase()
      return terms.some((t) => hay.includes(String(t).toLowerCase()))
    })
  }, [listItems, mappingSearch])

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
      // 原"货品映射"在这里展示的是 model.metadata_json.recognition_keywords，
      // 用途是 sku-master 自动绑定时的关键词兜底（详见型号识别规则页签）。
      // 它本质是"识别用关键词标签"，不是真正映射到天猫商家编码的"货品"，因此正名为"关键词标签"。
      // 真正的"货品映射"由下面新增的列承载，展示该模型已发布标准版本下的所有变体编码（KB8-001 / KB8-002 ...）。
      title: '关键词标签',
      width: 280,
      render: (_: any, r: any) => {
        const meta: any = (r as any)?.metadata_json ?? {}
        const raw = Array.isArray(meta?.recognition_keywords) ? meta.recognition_keywords : []
        const seen = new Set<string>()
        const uniq: string[] = []
        for (const x of raw) {
          const s = String(x ?? '').trim()
          if (!s || seen.has(s)) continue
          seen.add(s)
          uniq.push(s)
        }
        if (!uniq.length) return <Text type="secondary">-</Text>
        const show = uniq.slice(0, 4)
        const rest = uniq.length - show.length
        const tags = (
          <Space size={4} wrap>
            {show.map((k) => (
              <Tag key={k} style={{ marginInlineEnd: 0 }}>
                {k}
              </Tag>
            ))}
            {rest > 0 ? <Tag color="default">+{rest}</Tag> : null}
          </Space>
        )
        if (rest <= 0) return tags
        return (
          <Tooltip
            getPopupContainer={() => document.body}
            title={
              <Space size={4} wrap>
                {uniq.map((k) => (
                  <Tag key={k} style={{ marginInlineEnd: 0 }}>
                    {k}
                  </Tag>
                ))}
              </Space>
            }
          >
            {tags}
          </Tooltip>
        )
      },
    },
    {
      // 真正的"货品映射"：模型已发布标准版本下所有变体的"物料名(变体编码)"摘要，
      // 例如 仿羊绒(KB8-001) / 多尼尔(KB8-002)。
      // 每个变体 = 一种可对外的"货品"，运营把变体编码填到天猫商家编码即可锚定。
      title: '货品映射',
      width: 420,
      render: (_: any, r: any) => {
        const briefs: Array<{ variant_code: string; material_name?: string | null }> = Array.isArray(
          (r as any)?.current_published_variant_codes,
        )
          ? (r as any).current_published_variant_codes
          : []
        if (!briefs.length) return <Text type="secondary">-</Text>
        const formatLabel = (b: { variant_code: string; material_name?: string | null }) => {
          const name = String(b.material_name ?? '').trim()
          const code = String(b.variant_code ?? '').trim()
          return name ? `${name}(${code})` : code
        }
        const show = briefs.slice(0, 4)
        const rest = briefs.length - show.length
        const pills = (
          <Space size={6} wrap>
            {show.map((b) => (
              <KeywordPill key={b.variant_code} keyword={formatLabel(b)} />
            ))}
            {rest > 0 ? (
              <span
                style={{
                  display: 'inline-block',
                  padding: '1px 8px',
                  borderRadius: 999,
                  border: '1px solid var(--ant-color-border)',
                  background: 'var(--ant-color-fill-tertiary)',
                  color: 'var(--ant-color-text-secondary)',
                  fontSize: 11,
                  lineHeight: '18px',
                  whiteSpace: 'nowrap',
                }}
              >
                +{rest}
              </span>
            ) : null}
          </Space>
        )
        if (rest <= 0) return pills
        return (
          <Tooltip
            getPopupContainer={() => document.body}
            title={
              <Space size={6} wrap>
                {briefs.map((b) => (
                  <KeywordPill key={b.variant_code} keyword={formatLabel(b)} />
                ))}
              </Space>
            }
          >
            {pills}
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
              border: '1px solid var(--ant-color-border)',
              backgroundColor: 'var(--ant-color-fill-tertiary)',
              background: 'color-mix(in srgb, var(--ant-color-success) 18%, var(--ant-color-fill-tertiary))',
              borderColor: 'color-mix(in srgb, var(--ant-color-success) 45%, var(--ant-color-border))',
              fontSize: 11,
              lineHeight: '18px',
              color: 'var(--ant-color-success)',
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
              <Tag
                style={{
                  border: '1px solid var(--ant-color-border)',
                  backgroundColor: 'var(--ant-color-fill-tertiary)',
                  background: 'color-mix(in srgb, var(--ant-color-error) 18%, var(--ant-color-fill-tertiary))',
                  borderColor: 'color-mix(in srgb, var(--ant-color-error) 45%, var(--ant-color-border))',
                  color: 'var(--ant-color-error)',
                }}
              >
                失败
              </Tag>
            </Tooltip>
          )
        }
        const diff = audit.diff_percent
        if (diff === undefined || diff === null || !Number.isFinite(diff)) return <Tag>-</Tag>
        const abs = Math.abs(diff)
        const warn = abs >= 5
        const text = `${diff >= 0 ? '+' : ''}${diff.toFixed(1)}%`
        return (
          <Tag
            style={{
              border: '1px solid var(--ant-color-border)',
              backgroundColor: 'var(--ant-color-fill-tertiary)',
              background: warn
                ? 'color-mix(in srgb, var(--ant-color-warning) 18%, var(--ant-color-fill-tertiary))'
                : 'color-mix(in srgb, var(--ant-color-success) 18%, var(--ant-color-fill-tertiary))',
              borderColor: warn
                ? 'color-mix(in srgb, var(--ant-color-warning) 45%, var(--ant-color-border))'
                : 'color-mix(in srgb, var(--ant-color-success) 45%, var(--ant-color-border))',
              color: warn ? 'var(--ant-color-warning)' : 'var(--ant-color-success)',
            }}
          >
            {warn ? `预警 ${text}` : text}
          </Tag>
        )
      },
    },
    {
      title: '更新时间',
      dataIndex: 'updated_at',
      width: 170,
      render: (v: any) => {
        const s = String(v ?? '').trim()
        if (!s) return '-'
        return formatBeijingTime(s, 'YYYY-MM-DD HH:mm')
      },
    },
    {
      title: '操作',
      width: 140,
      render: (_, r) => (
        <Space size={6}>
          <Tooltip title="编辑">
            <Button
              size="small"
              type="text"
              icon={<EditOutlined />}
              aria-label="编辑"
              onClick={() => {
                setEditingModelId(r.id)
                setEditingVersionId(null)
                setEditorOpen(true)
              }}
            />
          </Tooltip>

          <Tooltip title="实时核价">
            <Button
              size="small"
              type="text"
              icon={<ThunderboltOutlined />}
              aria-label="实时核价"
              loading={Boolean(auditingModelIds[r.id])}
              onClick={() => handleRealtimeAudit(r)}
            />
          </Tooltip>

          <Tooltip title="删除为“归档删除标准版本（不影响打样版本）”。规则：存在已发布标准版本或存在SKU绑定则不允许删除；否则允许删除标准版本。">
            <Button
              size="small"
              type="text"
              danger
              icon={<DeleteOutlined />}
              aria-label="删除"
              disabled={Boolean((r as any).current_published_standard_version_id)}
              onClick={() => handleDeleteModel(r)}
            />
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
          <Space direction="vertical" size={2}>
            <Text type="secondary">1、按“结构 + 工艺 + 计价公式”建产品模型，不按销售品名建，也不单纯按材质建。</Text>
            <Text type="secondary">2、标准模型负责“一个物品怎么算成本”，套装模板负责“多个物品怎么组合销售 / 组合出 BOM”。</Text>
          </Space>
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
              <Input
                allowClear
                value={mappingSearch}
                onChange={(e) => setMappingSearch(e.target.value)}
                placeholder="搜索关键词标签（识别关键词）"
                style={{ width: 260 }}
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
              dataSource={filteredItems as ProductModel[]}
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













