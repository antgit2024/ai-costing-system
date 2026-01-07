import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Alert,
  Button,
  Card,
  Col,
  Collapse,
  Drawer,
  Empty,
  Form,
  Input,
  Modal,
  Radio,
  Row,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
  message,
} from 'antd'

import {
  archiveBundleTemplate,
  cloneBundleTemplate,
  createBundleTemplate,
  fetchBundleTemplates,
  fetchProductModelVersionLines,
  fetchProductModelVersionsPaged,
  listLineVariants,
  updateBundleTemplate,
} from '@/services/planner'

const { Text } = Typography

type ComponentRow = {
  model_version_id: string | null
  width_cm: number
  height_cm: number
  quantity: number
  spec_text: string
}

const parseTags = (meta: any): string[] => {
  const raw = meta?.tags
  return Array.isArray(raw) ? raw.map((x) => String(x)).filter(Boolean) : []
}

const parseTokenText = (text: any): string[] => {
  const s = String(text ?? '').trim()
  if (!s) return []
  return s
    .split(/[\s,，;；/|、]+/g)
    .map((x) => x.trim())
    .filter(Boolean)
}

const formatBetween = (pair: any, unit: string) => {
  if (!Array.isArray(pair) || pair.length < 2) return null
  const [a, b] = pair
  const hasA = a != null && a !== ''
  const hasB = b != null && b !== ''
  if (!hasA && !hasB) return null
  if (hasA && hasB) return `${a}~${b}${unit}`
  if (hasA) return `>=${a}${unit}`
  return `<=${b}${unit}`
}

const formatTrigger = (condRaw: any): string => {
  const cond = (condRaw ?? {}) as any
  const any = Array.isArray(cond.spec_contains_any) ? cond.spec_contains_any.filter(Boolean) : []
  const all = Array.isArray(cond.spec_contains_all) ? cond.spec_contains_all.filter(Boolean) : []
  const parts: string[] = []
  if (any.length) parts.push(`TOKEN(any): ${any.join('、')}`)
  if (all.length) parts.push(`TOKEN(all): ${all.join('、')}`)
  const w = formatBetween(cond.width_between, 'cm')
  const h = formatBetween(cond.height_between, 'cm')
  const a = formatBetween(cond.area_between, 'm²')
  const p = formatBetween(cond.perimeter_between, 'm')
  if (w) parts.push(`宽: ${w}`)
  if (h) parts.push(`高: ${h}`)
  if (a) parts.push(`面积: ${a}`)
  if (p) parts.push(`周长: ${p}`)
  return parts.join('；') || '-'
}

export default function BundleTemplatesPage() {
  const qc = useQueryClient()
  const [search, setSearch] = useState<string>('')
  const [category, setCategory] = useState<string>('')
  const [tag, setTag] = useState<string>('')
  const [includeArchived, setIncludeArchived] = useState(false)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)

  const [drawerOpen, setDrawerOpen] = useState(false)
  const [editing, setEditing] = useState<any | null>(null)
  const [createdTokenHint, setCreatedTokenHint] = useState<string | null>(null)

  const [form] = Form.useForm()
  const [components, setComponents] = useState<ComponentRow[]>([
    { model_version_id: null, width_cm: 40, height_cm: 50, quantity: 1, spec_text: '' },
  ])

  // 预设变体筛选：每个组件 idx -> { base_line_id -> selected_variant_id }
  const [presetSelectedByIdx, setPresetSelectedByIdx] = useState<Record<number, Record<string, string | null>>>({})
  const [presetModalOpen, setPresetModalOpen] = useState(false)
  const [presetModalIdx, setPresetModalIdx] = useState<number | null>(null)

  const selectedVersionIds = useMemo(() => {
    const ids = new Set<string>()
    for (const r of components ?? []) {
      const vid = String(r.model_version_id ?? '').trim()
      if (vid) ids.add(vid)
    }
    return Array.from(ids)
  }, [components])

  const listQuery = useQuery({
    queryKey: ['bundle-templates', { search, category, tag, includeArchived, page, pageSize }],
    queryFn: () =>
      fetchBundleTemplates({
        search: search || undefined,
        category: category || undefined,
        tag: tag || undefined,
        include_archived: includeArchived || undefined,
        page,
        page_size: pageSize,
      }),
  })

  const versionPickerQuery = useQuery({
    queryKey: ['product-model-versions-paged', 'bundle-template-center', 'standard'],
    queryFn: () => fetchProductModelVersionsPaged({ version_kind: 'standard', page: 1, page_size: 200 }),
  })
  const versionOptions = useMemo(() => {
    const items = (versionPickerQuery.data?.items ?? []) as any[]
    return items.map((x) => ({
      value: x.version_id,
      label: `${x.model_code}:${x.model_name} / ${x.version_label || x.version_id.slice(0, 8)} (${x.version_status})`,
    }))
  }, [versionPickerQuery.data])

  const variantsSummaryQuery = useQuery({
    queryKey: ['bundle-template-center', 'variants-summary', selectedVersionIds.join(',')],
    queryFn: async () => {
      const rows = await Promise.all(
        selectedVersionIds.map(async (version_id) => {
          const items = await listLineVariants({ version_id })
          return { version_id, items }
        }),
      )
      return rows
    },
    enabled: selectedVersionIds.length > 0,
  })

  const variantsHintByVersion = useMemo(() => {
    const m = new Map<string, { has_enabled: boolean; token_hints: string[]; total: number }>()
    const rows = (variantsSummaryQuery.data ?? []) as Array<{ version_id: string; items: any[] }>
    for (const r of rows) {
      const items = Array.isArray(r.items) ? r.items : []
      const enabledItems = items.filter((x) => !!x?.enabled)
      const tokenSet = new Set<string>()
      for (const v of enabledItems) {
        const cond = (v?.conditions ?? {}) as any
        const anyTokens = Array.isArray(cond?.spec_contains_any) ? cond.spec_contains_any : []
        const allTokens = Array.isArray(cond?.spec_contains_all) ? cond.spec_contains_all : []
        for (const t of [...anyTokens, ...allTokens]) {
          const s = String(t ?? '').trim()
          if (!s) continue
          // hide system guardrail tokens from operator hints
          const up = s.toUpperCase()
          if (up.startsWith('MODEL:') || up.startsWith('M:') || up.startsWith('BOUND_VERSION:') || up.startsWith('SKU:')) continue
          tokenSet.add(s)
        }
      }
      const token_hints = Array.from(tokenSet).slice(0, 12)
      m.set(String(r.version_id), { has_enabled: enabledItems.length > 0, token_hints, total: items.length })
    }
    return m
  }, [variantsSummaryQuery.data])

  const presetVersionId = useMemo(() => {
    if (!presetModalOpen) return null
    if (presetModalIdx == null) return null
    const r = (components ?? [])[presetModalIdx]
    const vid = String(r?.model_version_id ?? '').trim()
    return vid || null
  }, [presetModalOpen, presetModalIdx, components])

  const presetVersionLinesQuery = useQuery({
    queryKey: ['bundle-template-center', 'preset-version-lines', presetVersionId],
    queryFn: () => fetchProductModelVersionLines(String(presetVersionId)),
    enabled: !!presetVersionId,
  })

  const presetBaseLineMap = useMemo(() => {
    const data = presetVersionLinesQuery.data as any
    const mats = (data?.materials ?? []) as any[]
    const m = new Map<string, any>()
    for (const r of mats) {
      const id = String(r?.id ?? '').trim()
      if (!id) continue
      m.set(id, r)
    }
    return m
  }, [presetVersionLinesQuery.data])

  const presetVariantsForVersion = useMemo(() => {
    if (!presetVersionId) return []
    const rows = (variantsSummaryQuery.data ?? []) as Array<{ version_id: string; items: any[] }>
    const hit = rows.find((x) => String(x?.version_id) === String(presetVersionId))
    return Array.isArray(hit?.items) ? hit.items : []
  }, [presetVersionId, variantsSummaryQuery.data])

  const presetVariantsByBaseLine = useMemo(() => {
    const m = new Map<string, any[]>()
    for (const v of presetVariantsForVersion) {
      const baseId = String(v?.base_line_id ?? '').trim()
      if (!baseId) continue
      m.set(baseId, [...(m.get(baseId) ?? []), v])
    }
    for (const [k, arr] of m.entries()) {
      arr.sort((a: any, b: any) => Number(b?.priority ?? 0) - Number(a?.priority ?? 0))
      m.set(k, arr)
    }
    return m
  }, [presetVariantsForVersion])

  const openPresetModal = (idx: number) => {
    const r = (components ?? [])[idx]
    const vid = String(r?.model_version_id ?? '').trim()
    if (!vid) {
      message.warning('请先选择该组件的模型版本')
      return
    }
    setPresetModalIdx(idx)
    setPresetModalOpen(true)
  }

  const applyPresetToComponent = () => {
    if (presetModalIdx == null) return
    const selectedMap = presetSelectedByIdx[presetModalIdx] ?? {}
    const tokenSet = new Set<string>()
    for (const [baseLineId, variantId] of Object.entries(selectedMap)) {
      if (!variantId) continue
      const variants = presetVariantsByBaseLine.get(baseLineId) ?? []
      const v = variants.find((x: any) => String(x?.id) === String(variantId))
      if (!v) continue
      const cond = (v?.conditions ?? {}) as any
      const anyTokens = Array.isArray(cond?.spec_contains_any) ? cond.spec_contains_any : []
      const allTokens = Array.isArray(cond?.spec_contains_all) ? cond.spec_contains_all : []
      for (const t of [...anyTokens, ...allTokens]) {
        const s = String(t ?? '').trim()
        if (!s) continue
        const up = s.toUpperCase()
        if (up.startsWith('MODEL:') || up.startsWith('M:') || up.startsWith('BOUND_VERSION:') || up.startsWith('SKU:')) continue
        tokenSet.add(s)
      }
    }
    const tokens = Array.from(tokenSet)
    const nextText = tokens.join('，')
    setComponents((prev) => prev.map((x, i) => (i === presetModalIdx ? { ...x, spec_text: nextText } : x)))
    message.success(tokens.length ? `已填充触发词：${tokens.join('、')}` : '所选变体不依赖 TOKEN 触发词（仅尺寸/面积/周长条件等）')
    setPresetModalOpen(false)
  }

  const hasTokenVariantRisk = useMemo(() => {
    for (const vid of selectedVersionIds) {
      const info = variantsHintByVersion.get(vid)
      if (info?.has_enabled && (info.token_hints ?? []).length > 0) return true
    }
    return false
  }, [selectedVersionIds, variantsHintByVersion])

  const openCreate = () => {
    setEditing(null)
    setCreatedTokenHint(null)
    form.setFieldsValue({ name: '', category: '', tags: [], shared_trigger_text: '' })
    setComponents([{ model_version_id: null, width_cm: 40, height_cm: 50, quantity: 1, spec_text: '' }])
    setDrawerOpen(true)
  }

  const openEdit = (row: any) => {
    setEditing(row)
    setCreatedTokenHint(null)
    const meta = row?.metadata ?? {}
    form.setFieldsValue({
      name: row?.name ?? '',
      category: String(meta?.category ?? '') || '',
      tags: parseTags(meta),
      shared_trigger_text: String(row?.shared_trigger_text ?? meta?.shared_trigger_text ?? '') || '',
    })
    const rows = (row?.components ?? []) as any[]
    setComponents(
      rows.length
        ? rows.map((c: any) => ({
            model_version_id: String(c.model_version_id ?? '') || null,
            width_cm: Number(c.width_mm ?? 0) / 10,
            height_cm: Number(c.height_mm ?? 0) / 10,
            quantity: Number(c.quantity ?? 1),
            spec_text: String(c.spec_text ?? ''),
          }))
        : [{ model_version_id: null, width_cm: 40, height_cm: 50, quantity: 1, spec_text: '' }],
    )
    setDrawerOpen(true)
  }

  const saveMutation = useMutation({
    mutationFn: async () => {
      const values = await form.validateFields()
      const comps = (components ?? [])
        .map((c) => ({
          model_version_id: String(c.model_version_id ?? '').trim(),
          width_mm: Number(c.width_cm) * 10,
          height_mm: Number(c.height_cm) * 10,
          quantity: Number(c.quantity),
          spec_text: String(c.spec_text || '').trim() || undefined,
        }))
        .filter((c) => c.model_version_id && c.width_mm > 0 && c.height_mm > 0 && c.quantity > 0)
      if (!comps.length) throw new Error('请先填写至少 1 行组件（版本/宽/高/数量）')

      const meta = {
        ...(editing?.metadata ?? {}),
        category: String(values.category ?? '').trim() || undefined,
        tags: Array.isArray(values.tags) ? values.tags.map((x: any) => String(x)).filter(Boolean) : [],
      }
      const sharedText = String(values.shared_trigger_text ?? '').trim() || undefined

      if (editing?.id) {
        return await updateBundleTemplate(editing.id, {
          name: String(values.name ?? '').trim() || undefined,
          components: comps as any,
          metadata: meta,
          shared_trigger_text: sharedText,
        })
      }
      return await createBundleTemplate({
        name: String(values.name ?? '').trim() || undefined,
        components: comps as any,
        metadata: meta,
        shared_trigger_text: sharedText,
      })
    },
    onSuccess: (res: any) => {
      qc.invalidateQueries({ queryKey: ['bundle-templates'] })
      const code = String(res?.code ?? '').toUpperCase()
      if (code) setCreatedTokenHint(`B:${code}`)
      message.success(editing?.id ? '已保存' : '已创建')
      setEditing(res)
    },
    onError: (e: any) => message.error(String(e?.message ?? e)),
  })

  const cloneMutation = useMutation({
    mutationFn: async (row: any) => cloneBundleTemplate(String(row?.id), {}),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['bundle-templates'] })
      message.success('已复制')
    },
    onError: (e: any) => message.error(String(e?.message ?? e)),
  })

  const archiveMutation = useMutation({
    mutationFn: async (row: any) => archiveBundleTemplate(String(row?.id)),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['bundle-templates'] })
      message.success('已归档')
    },
    onError: (e: any) => message.error(String(e?.message ?? e)),
  })

  const items = (listQuery.data?.items ?? []) as any[]

  return (
    <div style={{ padding: 16 }}>
      <Modal
        open={presetModalOpen}
        title="预设变体筛选（按物料行选择变体规则 → 一键填充触发词）"
        width={980}
        onCancel={() => setPresetModalOpen(false)}
        onOk={applyPresetToComponent}
        okText="按勾选填充触发词"
        destroyOnClose
      >
        {!presetVersionId ? (
          <Empty description="请先选择组件的模型版本" />
        ) : presetVariantsForVersion.length === 0 ? (
          <Empty description="该版本没有行级变体规则" />
        ) : (
          <Space direction="vertical" style={{ width: '100%' }} size={12}>
            <Alert
              type="info"
              showIcon
              message="说明"
              description={
                <div>
                  <div>这里按 base_line（物料行）分组列出该版本所有变体规则，你可以为每条物料行选择 0/1 条“希望触发的规则”。</div>
                  <div>
                    点击“按勾选填充触发词”会把所选规则的 TOKEN(any/all) 关键词自动填充到该组件的触发词里（便于运营写对词）。
                  </div>
                  <div>注意：最终命中仍受 priority + stop_on_hit 影响，建议用测试台预演确认。</div>
                </div>
              }
            />

            <Collapse
              items={Array.from(presetVariantsByBaseLine.entries()).map(([baseLineId, arr]) => {
                const base = presetBaseLineMap.get(baseLineId)
                const baseLabel = String(base?.material_name ?? base?.material_code ?? baseLineId).trim()
                const selected = (presetSelectedByIdx[presetModalIdx ?? -1] ?? {})[baseLineId] ?? null

                return {
                  key: baseLineId,
                  label: (
                    <Space size={8}>
                      <Text strong>{baseLabel}</Text>
                      <Tag color="blue">{arr.length} 条规则</Tag>
                      {selected ? <Tag color="green">已选 1 条</Tag> : <Tag>未选</Tag>}
                    </Space>
                  ),
                  children: (
                    <Radio.Group
                      value={selected ?? ''}
                      onChange={(e) => {
                        const vid = String(e?.target?.value ?? '')
                        setPresetSelectedByIdx((prev) => ({
                          ...prev,
                          [presetModalIdx ?? 0]: {
                            ...(prev[presetModalIdx ?? 0] ?? {}),
                            [baseLineId]: vid ? vid : null,
                          },
                        }))
                      }}
                    >
                      <Space direction="vertical" style={{ width: '100%' }} size={10}>
                        <Radio value="">不选择（该物料行用默认/其它规则）</Radio>
                        {arr.map((v: any) => {
                          const trigger = formatTrigger(v?.conditions)
                          const produced = Array.isArray(v?.items) ? v.items : []
                          const producedLabels: string[] = produced
                            .map((it: any) => String(it?.material_name ?? it?.material_code ?? '').trim())
                            .filter(Boolean)
                            .slice(0, 8)
                          return (
                            <Radio key={String(v?.id)} value={String(v?.id)}>
                              <Space direction="vertical" size={4} style={{ width: '100%' }}>
                                <Space size={8} wrap>
                                  <Tag color={v?.enabled ? 'green' : 'default'}>{v?.enabled ? 'enabled' : 'disabled'}</Tag>
                                  <Tag>priority: {String(v?.priority ?? '-')}</Tag>
                                  <Tag>stop_on_hit: {String(!!v?.stop_on_hit)}</Tag>
                                  <Tag>action: {String(v?.action ?? '-')}</Tag>
                                </Space>
                                <Text type="secondary">{trigger}</Text>
                                {producedLabels.length ? (
                                  <Space size={6} wrap>
                                    <Text type="secondary">替换/新增物料：</Text>
                                    {producedLabels.map((x: string) => (
                                      <Tag key={x}>{x}</Tag>
                                    ))}
                                  </Space>
                                ) : null}
                              </Space>
                            </Radio>
                          )
                        })}
                      </Space>
                    </Radio.Group>
                  ),
                }
              })}
            />
          </Space>
        )}
      </Modal>

      <Row gutter={[16, 16]}>
        <Col span={24}>
          <Card
            title="套装模板（长期资产）"
            extra={
              <Space>
                <Button type="primary" onClick={openCreate}>
                  新建模板
                </Button>
              </Space>
            }
          >
            <Space wrap style={{ marginBottom: 12 }}>
              <Input
                style={{ width: 220 }}
                placeholder="搜索：编码/名称"
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value)
                  setPage(1)
                }}
              />
              <Input
                style={{ width: 160 }}
                placeholder="分类（metadata.category）"
                value={category}
                onChange={(e) => {
                  setCategory(e.target.value)
                  setPage(1)
                }}
              />
              <Input
                style={{ width: 160 }}
                placeholder="标签（metadata.tags）"
                value={tag}
                onChange={(e) => {
                  setTag(e.target.value)
                  setPage(1)
                }}
              />
              <Space>
                <Text type="secondary">含归档</Text>
                <Switch checked={includeArchived} onChange={(v) => setIncludeArchived(v)} />
              </Space>
            </Space>

            <Table
              rowKey={(r) => String((r as any).id)}
              loading={listQuery.isLoading}
              dataSource={items}
              pagination={{
                current: page,
                pageSize,
                total: Number(listQuery.data?.total ?? 0),
                showSizeChanger: true,
                onChange: (p, ps) => {
                  setPage(p)
                  setPageSize(ps)
                },
              }}
              columns={[
                { title: '编码', dataIndex: 'code', width: 120, render: (v) => <Text code>{String(v)}</Text> },
                { title: '名称', dataIndex: 'name', width: 220, render: (v) => String(v ?? '').trim() || '-' },
                {
                  title: '分类',
                  width: 120,
                  render: (_: any, r: any) => String(r?.metadata?.category ?? '').trim() || '-',
                },
                {
                  title: '标签',
                  width: 240,
                  render: (_: any, r: any) => {
                    const tags = parseTags(r?.metadata)
                    if (!tags.length) return <Text type="secondary">-</Text>
                    return (
                      <Space wrap>
                        {tags.slice(0, 6).map((t) => (
                          <Tag key={t}>{t}</Tag>
                        ))}
                        {tags.length > 6 ? <Tag>+{tags.length - 6}</Tag> : null}
                      </Space>
                    )
                  },
                },
                {
                  title: '组件数',
                  width: 90,
                  render: (_: any, r: any) => ((r?.components ?? []) as any[]).length,
                },
                {
                  title: '更新时间',
                  width: 170,
                  dataIndex: 'updated_at',
                  render: (v) => String(v ?? '') || '-',
                },
                {
                  title: '状态',
                  width: 90,
                  render: (_: any, r: any) => (r?.is_archived ? <Tag color="orange">archived</Tag> : <Tag color="green">active</Tag>),
                },
                {
                  title: '操作',
                  width: 240,
                  render: (_: any, r: any) => (
                    <Space>
                      <Button size="small" onClick={() => openEdit(r)}>
                        编辑
                      </Button>
                      <Button size="small" loading={cloneMutation.isPending} onClick={() => cloneMutation.mutate(r)}>
                        复制
                      </Button>
                      <Button
                        size="small"
                        danger
                        disabled={!!r?.is_archived}
                        loading={archiveMutation.isPending}
                        onClick={() => {
                          Modal.confirm({
                            title: '归档模板？',
                            content: `归档后将不再出现在默认列表中（仍可在“含归档”中查看）。编码：${String(r?.code ?? '')}`,
                            okText: '归档',
                            okButtonProps: { danger: true },
                            onOk: async () => archiveMutation.mutateAsync(r),
                          })
                        }}
                      >
                        归档
                      </Button>
                    </Space>
                  ),
                },
              ]}
            />
          </Card>
        </Col>
      </Row>

      <Drawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        width={960}
        destroyOnClose={false}
        title={editing?.id ? `编辑套装模板（B:${String(editing?.code ?? '')}）` : '新建套装模板'}
        extra={
          <Space>
            <Button onClick={() => setDrawerOpen(false)}>关闭</Button>
            <Button type="primary" loading={saveMutation.isPending} onClick={() => saveMutation.mutate()}>
              保存
            </Button>
          </Space>
        }
      >
        <Space direction="vertical" style={{ width: '100%' }} size={12}>
          {createdTokenHint ? (
            <Alert type="success" showIcon message={`编码已生成：${createdTokenHint}`} description="把 B: 编码放进交易规格即可走合并器预演。" />
          ) : null}

          <Form layout="vertical" form={form}>
            <Row gutter={12}>
              <Col span={10}>
                <Form.Item name="name" label="模板名称（可选）">
                  <Input placeholder="例如：三件套（活动款）" />
                </Form.Item>
              </Col>
              <Col span={7}>
                <Form.Item name="category" label="分类（metadata.category）">
                  <Input placeholder="例如：gift / packaging" />
                </Form.Item>
              </Col>
              <Col span={7}>
                <Form.Item name="tags" label="标签（metadata.tags）">
                  <Select mode="tags" placeholder="例如：gift, 渠道A, 活动款" />
                </Form.Item>
              </Col>
            </Row>
            <Form.Item
              name="shared_trigger_text"
              label="公共触发词（作用于所有组件，可选）"
              extra="建议填对客交易规格里一定会出现/需要的关键词。运营写尺寸也没问题，但这里不会用于解析尺寸/不会改变模板尺寸（仅用于触发变体）。"
            >
              <Input.TextArea rows={2} placeholder="例如：背面纯色，雪尼尔（写尺寸也不会影响模板尺寸）" />
            </Form.Item>
          </Form>

          <Alert
            type="info"
            showIcon
            message="组件清单（结构化）"
            description="每行：标准版本 + 宽(cm) + 高(cm) + 数量 + 预设变体筛选/触发词（可选，仅用于命中变体；不会解析尺寸/不会改变模板尺寸）。"
          />

          {hasTokenVariantRisk ? (
            <Alert
              type="warning"
              showIcon
              message="提示：当前模板所选版本包含“依赖触发词(Token)”的变体规则"
              description="如果对客交易规格没有写到这些关键词，则可能命不中变体而落到兜底物料/默认逻辑。你也可以在某个组件行用“附加触发词”补充特定关键词。"
            />
          ) : null}

          <Table
            size="small"
            pagination={false}
            rowKey={(_, idx) => `c-${idx}`}
            dataSource={components}
            columns={[
              {
                title: '模型版本',
                width: 320,
                render: (_: any, r: any, idx: number) => (
                  <Space direction="vertical" style={{ width: '100%' }} size={4}>
                    <Select
                      showSearch
                      allowClear
                      placeholder="选择标准版本"
                      style={{ width: '100%' }}
                      loading={versionPickerQuery.isLoading}
                      options={versionOptions as any}
                      value={r.model_version_id ?? undefined}
                      onChange={(v) =>
                        setComponents((prev) => prev.map((x, i) => (i === idx ? { ...x, model_version_id: (v as any) ?? null } : x)))
                      }
                    />
                    {r.model_version_id ? (
                      (() => {
                        const info = variantsHintByVersion.get(String(r.model_version_id))
                        if (!info) return <Text type="secondary">变体：加载中…</Text>
                        if (!info.has_enabled) return <Text type="secondary">变体：无</Text>
                        if ((info.token_hints ?? []).length) {
                          return (
                            <Space size={6} wrap>
                              <Tag color="orange">变体：可能需要触发词</Tag>
                              <Text type="secondary" style={{ fontSize: 12 }}>
                                示例：{info.token_hints.slice(0, 6).join('、')}
                                {info.token_hints.length > 6 ? '…' : ''}
                              </Text>
                            </Space>
                          )
                        }
                        return <Tag color="blue">变体：不依赖触发词</Tag>
                      })()
                    ) : (
                      <Text type="secondary">变体：-</Text>
                    )}
                  </Space>
                ),
              },
              {
                title: '宽(cm)',
                width: 90,
                render: (_: any, r: any, idx: number) => (
                  <Input
                    value={String(r.width_cm)}
                    onChange={(e) => {
                      const v = Number(e.target.value)
                      setComponents((prev) => prev.map((x, i) => (i === idx ? { ...x, width_cm: Number.isFinite(v) ? v : 0 } : x)))
                    }}
                  />
                ),
              },
              {
                title: '高(cm)',
                width: 90,
                render: (_: any, r: any, idx: number) => (
                  <Input
                    value={String(r.height_cm)}
                    onChange={(e) => {
                      const v = Number(e.target.value)
                      setComponents((prev) => prev.map((x, i) => (i === idx ? { ...x, height_cm: Number.isFinite(v) ? v : 0 } : x)))
                    }}
                  />
                ),
              },
              {
                title: '数量',
                width: 80,
                render: (_: any, r: any, idx: number) => (
                  <Input
                    value={String(r.quantity)}
                    onChange={(e) => {
                      const v = Number(e.target.value)
                      setComponents((prev) => prev.map((x, i) => (i === idx ? { ...x, quantity: Number.isFinite(v) ? v : 1 } : x)))
                    }}
                  />
                ),
              },
              {
                title: '预设变体筛选 / 触发词（可选）',
                render: (_: any, r: any, idx: number) => (
                  <Space direction="vertical" style={{ width: '100%' }} size={8}>
                    <Space>
                      <Button size="small" onClick={() => openPresetModal(idx)} disabled={!r.model_version_id}>
                        预设变体筛选…
                      </Button>
                      <Text type="secondary">（按物料行挑变体 → 一键填充触发词）</Text>
                    </Space>
                    <Select
                      mode="multiple"
                      placeholder="也可直接从候选触发词中多选（不支持自由输入）"
                      style={{ width: '100%' }}
                      value={parseTokenText(r.spec_text)}
                      options={
                        r.model_version_id
                          ? (variantsHintByVersion.get(String(r.model_version_id))?.token_hints ?? []).map((t) => ({ value: t, label: t }))
                          : []
                      }
                      onChange={(vals) => {
                        const merged = Array.isArray(vals) ? vals.map((x) => String(x)).filter(Boolean) : []
                        const nextText = merged.join('，')
                        setComponents((prev) => prev.map((x, i) => (i === idx ? { ...x, spec_text: nextText } : x)))
                      }}
                    />
                  </Space>
                ),
              },
              {
                title: '操作',
                width: 160,
                render: (_: any, __: any, idx: number) => (
                  <Space>
                    <Button
                      size="small"
                      onClick={() =>
                        setComponents((prev) => [...prev, { model_version_id: null, width_cm: 40, height_cm: 50, quantity: 1, spec_text: '' }])
                      }
                    >
                      +行
                    </Button>
                    <Button size="small" danger disabled={components.length <= 1} onClick={() => setComponents((prev) => prev.filter((_, i) => i !== idx))}>
                      删除
                    </Button>
                  </Space>
                ),
              },
            ]}
          />
        </Space>
      </Drawer>
    </div>
  )
}


