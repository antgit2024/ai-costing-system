import { useMemo, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Alert, Button, Card, Col, Descriptions, Divider, Input, Row, Select, Space, Table, Tabs, Tag, Typography, message } from 'antd'

import {
  fetchProductModelVersionLines,
  fetchProductModels,
  fetchProductModelVersions,
  fetchBundleTemplates,
  generateBom,
  generateBomBySpec,
  listLineVariants,
  parseSpec,
} from '@/services/planner'
import type { BomGenerateResponse, LineVariantCondition, LineVariantDetailRead, ProductModel, ProductModelLinesResponse, ProductModelVersionRead, SpecParseResponse } from '@/types/planner'

const { Text } = Typography

const toNumberOrNull = (v: any): number | null => {
  if (v == null || v === '') return null
  const n = Number(v)
  return Number.isFinite(n) ? n : null
}

const formatMoney2 = (v: any): string => {
  const n = toNumberOrNull(v)
  if (n == null) return '-'
  return n.toFixed(2)
}

const computeMaterialCostFromLines = (lines: any[]): number => {
  return (lines ?? []).reduce((acc, r) => {
    const qty = toNumberOrNull((r as any)?.computed_quantity) ?? 0
    const unit = toNumberOrNull((r as any)?.bom_unit_price) ?? 0
    const lineCost = toNumberOrNull((r as any)?.line_cost)
    const v = lineCost != null ? lineCost : qty * unit
    return acc + (Number.isFinite(v) ? v : 0)
  }, 0)
}

type ProductListingDraft = {
  sku_code: string
  model_id: string | null
  model_version_id: string | null
  spec_text: string
}

type BundleTestDraft = {
  bundle_code: string | null
  spec_text: string
}

export default function ProductListingPage() {
  const [mode, setMode] = useState<'single' | 'multi'>('single')
  const [draft, setDraft] = useState<ProductListingDraft>({
    sku_code: '',
    model_id: null,
    model_version_id: null,
    spec_text: '',
  })
  const [bundleDraft, setBundleDraft] = useState<BundleTestDraft>({ bundle_code: null, spec_text: '' })

  const [parsed, setParsed] = useState<SpecParseResponse | null>(null)
  const [bom, setBom] = useState<BomGenerateResponse | null>(null)
  const [lastError, setLastError] = useState<string | null>(null)

  const modelsQuery = useQuery({
    queryKey: ['product-models', 'listing', 'search', draft.sku_code ? '' : ''],
    // 这里不做自动 search（避免每次输入就请求）；先给 50 条兜底，用户用下拉搜索即可。
    queryFn: () => fetchProductModels({ page: 1, page_size: 50 }),
  })
  const models = (modelsQuery.data?.items ?? []) as ProductModel[]

  const versionsQuery = useQuery({
    queryKey: ['product-model-versions', draft.model_id],
    queryFn: () => fetchProductModelVersions(String(draft.model_id)),
    enabled: !!draft.model_id,
  })
  const versions = (versionsQuery.data ?? []) as ProductModelVersionRead[]

  const [showAllStandardVersions, setShowAllStandardVersions] = useState(false)

  const standardVersions = useMemo(() => {
    return versions.filter((v) => String(v.version_kind) === 'standard')
  }, [versions])

  const selectableStandardVersions = useMemo(() => {
    if (showAllStandardVersions) return standardVersions
    return standardVersions.filter((v) => String(v.version_status) === 'published')
  }, [showAllStandardVersions, standardVersions])

  const bundleTemplatesQuery = useQuery({
    queryKey: ['product-listing', 'bundle-templates', 'for-test'],
    queryFn: () =>
      fetchBundleTemplates({
        include_archived: true,
        page: 1,
        page_size: 200,
      }),
  })
  const bundleTemplateOptions = useMemo(() => {
    const items = (bundleTemplatesQuery.data?.items ?? []) as any[]
    return items.map((x) => ({
      value: String(x?.code ?? '').trim(),
      label: `B:${String(x?.code ?? '').trim()} / ${String(x?.name ?? '').trim() || '-'}${x?.is_archived ? ' (archived)' : ''}`,
    }))
  }, [bundleTemplatesQuery.data])

  const selectedModel = useMemo(() => models.find((m) => m.id === draft.model_id) ?? null, [models, draft.model_id])
  const selectedVersion = useMemo(
    () => selectableStandardVersions.find((v) => v.id === draft.model_version_id) ?? null,
    [selectableStandardVersions, draft.model_version_id],
  )

  const bundleTokenInSpec = useMemo(() => {
    const t = String(draft.spec_text || '')
    const m = t.match(/(?:BUNDLE:|B:)([A-Z0-9]{4,16})/i)
    if (!m) return null
    return `B:${String(m[1]).toUpperCase()}`
  }, [draft.spec_text])

  const parseMutation = useMutation({
    mutationFn: async () => {
      const spec_text = String(draft.spec_text ?? '').trim()
      if (!spec_text) throw new Error('请先输入交易规格（spec_text）')
      setLastError(null)
      const res = await parseSpec({ spec_text, sku_code: draft.sku_code || undefined })
      setParsed(res)
      return res
    },
    onError: (e: any) => setLastError(String(e?.message ?? e)),
  })

  const previewMutation = useMutation({
    mutationFn: async () => {
      const spec_text = String(draft.spec_text ?? '').trim()
      if (!spec_text) throw new Error('请先输入交易规格（spec_text）')
      setLastError(null)

      // 优先：交易规格中的套装编码（运营口径，避免依赖SKU/ERP同步）
      if (bundleTokenInSpec) {
        const bomRes = await generateBomBySpec({
          spec_text,
          sku_code: draft.sku_code || undefined,
        })
        setBom(bomRes)
        setParsed(((bomRes as any)?.trace ?? {})?.parsed ?? null)
        return bomRes
      }

      const model_version_id = String(draft.model_version_id ?? '').trim()
      if (!model_version_id) throw new Error('请先选择“已发布标准版本”（或在交易规格中提供 BUNDLE:XXXX）')

      const parsedRes = await parseSpec({ spec_text, sku_code: draft.sku_code || undefined })
      setParsed(parsedRes)
      const bomRes = await generateBom({ spec_text, model_version_id, sku_code: draft.sku_code || undefined, quantity: 1 })
      setBom(bomRes)
      return bomRes
    },
    onSuccess: () => message.success('解析+预演完成'),
    onError: (e: any) => setLastError(String(e?.message ?? e)),
  })

  const bundlePreviewMutation = useMutation({
    mutationFn: async () => {
      setLastError(null)
      const code = String(bundleDraft.bundle_code ?? '').trim()
      if (!code) throw new Error('请先选择套装（B:XXXXXX）')
      const extra = String(bundleDraft.spec_text ?? '').trim()
      const spec_text = extra ? `B:${code} ${extra}` : `B:${code}`
      const bomRes = await generateBomBySpec({
        spec_text,
        sku_code: draft.sku_code || undefined,
      })
      setBom(bomRes)
      setParsed(((bomRes as any)?.trace ?? {})?.parsed ?? null)
      return bomRes
    },
    onSuccess: () => message.success('套装预演完成'),
    onError: (e: any) => setLastError(String(e?.message ?? e)),
  })

  const matchedVariants = useMemo(() => {
    const traceAny = (bom?.trace ?? {}) as any
    const arr = traceAny?.matched_variants
    return Array.isArray(arr) ? arr : []
  }, [bom])

  const matchedBaseLineIds = useMemo(() => {
    const ids = new Set<string>()
    for (const r of matchedVariants as any[]) {
      const id = String((r as any)?.base_line_id ?? '').trim()
      if (id) ids.add(id)
    }
    return Array.from(ids)
  }, [matchedVariants])

  const versionLinesQuery = useQuery({
    queryKey: ['product-listing', 'version-lines', draft.model_version_id],
    queryFn: () => fetchProductModelVersionLines(String(draft.model_version_id)),
    enabled: mode === 'single' && !!draft.model_version_id && !!bom,
  })

  const variantsByBaseLineQuery = useQuery({
    queryKey: ['product-listing', 'line-variants-by-base-line', draft.model_version_id, matchedBaseLineIds.join(',')],
    queryFn: async () => {
      const version_id = String(draft.model_version_id)
      const res = await Promise.all(
        matchedBaseLineIds.map(async (base_line_id) => {
          const items = await listLineVariants({ version_id, base_line_id })
          return { base_line_id, items }
        }),
      )
      return res
    },
    enabled: mode === 'single' && !!draft.model_version_id && !!bom && matchedBaseLineIds.length > 0,
  })

  const baseLineMaterialMap = useMemo(() => {
    const data = versionLinesQuery.data as ProductModelLinesResponse | undefined
    const mats = (data?.materials ?? []) as any[]
    const m = new Map<string, any>()
    for (const r of mats) {
      const id = String(r?.id ?? '').trim()
      if (!id) continue
      m.set(id, r)
    }
    return m
  }, [versionLinesQuery.data])

  const variantMap = useMemo(() => {
    const m = new Map<string, LineVariantDetailRead>()
    const groups = (variantsByBaseLineQuery.data ?? []) as Array<{ base_line_id: string; items: LineVariantDetailRead[] }>
    for (const g of groups) {
      for (const v of g.items ?? []) {
        if (!v?.id) continue
        m.set(String(v.id), v)
      }
    }
    return m
  }, [variantsByBaseLineQuery.data])

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
    const cond = (condRaw ?? {}) as LineVariantCondition
    const any = Array.isArray(cond.spec_contains_any) ? cond.spec_contains_any.filter(Boolean) : []
    const all = Array.isArray(cond.spec_contains_all) ? cond.spec_contains_all.filter(Boolean) : []
    const parts: string[] = []
    if (any.length) parts.push(`TOKEN(any): ${any.join('、')}`)
    if (all.length) parts.push(`TOKEN(all): ${all.join('、')}`)
    const w = formatBetween((cond as any).width_between, 'cm')
    const h = formatBetween((cond as any).height_between, 'cm')
    const a = formatBetween((cond as any).area_between, 'm²')
    const p = formatBetween((cond as any).perimeter_between, 'm')
    if (w) parts.push(`宽: ${w}`)
    if (h) parts.push(`高: ${h}`)
    if (a) parts.push(`面积: ${a}`)
    if (p) parts.push(`周长: ${p}`)
    return parts.join('；') || '-'
  }

  const processLines = useMemo(() => {
    const traceAny = (bom?.trace ?? {}) as any
    const arr = traceAny?.costing?.process_lines
    return Array.isArray(arr) ? arr : []
  }, [bom])

  const inventoryLines = useMemo(() => {
    const traceAny = (bom?.trace ?? {}) as any
    const arr = traceAny?.inventory?.inventory_lines
    return Array.isArray(arr) ? arr : []
  }, [bom])

  const finalLines = useMemo(() => bom?.final_material_lines ?? [], [bom])

  const costingSummary = useMemo(() => {
    if (!bom) return null
    const traceAny = (bom.trace ?? {}) as any
    const costing = (traceAny?.costing ?? {}) as any

    const material_cost_total =
      toNumberOrNull(costing?.material_cost_total) ??
      computeMaterialCostFromLines((bom.final_material_lines ?? []) as any[])
    const process_cost_total =
      toNumberOrNull(costing?.process_cost_total) ??
      (processLines ?? []).reduce((acc: number, r: any) => acc + (toNumberOrNull(r?.total_cost) ?? 0), 0)

    const overhead_rate = 0.3
    const overhead_cost =
      toNumberOrNull(costing?.overhead_cost) ?? (material_cost_total + process_cost_total) * overhead_rate
    const total_cost =
      toNumberOrNull(costing?.total_cost) ?? material_cost_total + process_cost_total + overhead_cost
    const unit_cost = toNumberOrNull(costing?.unit_cost) ?? total_cost

    return {
      material_cost_total,
      process_cost_total,
      overhead_rate,
      overhead_cost,
      total_cost,
      unit_cost,
      priced_material_lines: costing?.priced_material_lines ?? costing?.priced_lines ?? null,
      missing_price_material_lines: costing?.missing_price_material_lines ?? costing?.missing_price_lines ?? null,
      missing_price_process_lines: costing?.missing_price_process_lines ?? null,
    }
  }, [bom, processLines])

  const modelOptions = useMemo(
    () =>
      models.map((m) => ({
        value: m.id,
        label: (
          <Space size={8}>
            <Text strong>{m.model_code}</Text>
            <Text>{m.model_name}</Text>
            {m.status && m.status !== 'active' ? <Tag color="orange">{m.status}</Tag> : null}
          </Space>
        ),
        raw: m,
      })),
    [models],
  )

  const versionOptions = useMemo(
    () =>
      selectableStandardVersions.map((v) => ({
        value: v.id,
        label: (
          <Space size={8}>
            <Text strong>{v.version_label || v.id.slice(0, 8)}</Text>
            {String(v.version_status) === 'published' ? (
              <Tag color="green">published</Tag>
            ) : (
              <Tag color="orange">{String(v.version_status || 'draft')}</Tag>
            )}
          </Space>
        ),
      })),
    [selectableStandardVersions],
  )

  return (
    <div style={{ padding: 16 }}>
      <Row gutter={[16, 16]}>
        <Col xs={24} lg={10}>
          <Card
            title="产品上架（测试台）"
            extra={<Text type="secondary">输入交易规格 → 解析 → 预演最终 BOM（用于运营自测命中与口径）</Text>}
          >
            <Space direction="vertical" style={{ width: '100%' }} size={12}>
              <Tabs
                activeKey={mode}
                onChange={(k) => {
                  setMode(k as any)
                  setLastError(null)
                  setParsed(null)
                  setBom(null)
                }}
                items={[
                  { key: 'single', label: '模型测试' },
                  { key: 'multi', label: '套装测试' },
                ]}
              />

              <Input
                placeholder="货品编码（可选，仅用于标记/复制）"
                value={draft.sku_code}
                onChange={(e) => setDraft((d) => ({ ...d, sku_code: e.target.value }))}
              />

              {mode === 'single' ? (
                <>
                  <Select
                    showSearch
                    allowClear
                    placeholder="选择标准模型（按编码/名称搜索）"
                    options={modelOptions as any}
                    value={draft.model_id ?? undefined}
                    loading={modelsQuery.isLoading}
                    filterOption={(input, option: any) => {
                      const raw = option?.raw as ProductModel | undefined
                      const q = String(input ?? '').trim().toLowerCase()
                      if (!raw) return false
                      return String(raw.model_code ?? '').toLowerCase().includes(q) || String(raw.model_name ?? '').toLowerCase().includes(q)
                    }}
                    onChange={(v) => {
                      setDraft((d) => ({ ...d, model_id: (v as string) ?? null, model_version_id: null }))
                      setBom(null)
                    }}
                  />

                  <Select
                    showSearch
                    allowClear
                    placeholder="选择已发布标准版本（published standard）"
                    options={versionOptions as any}
                    value={draft.model_version_id ?? undefined}
                    loading={versionsQuery.isLoading}
                    disabled={!draft.model_id}
                    onChange={(v) => {
                      setDraft((d) => ({ ...d, model_version_id: (v as string) ?? null }))
                      setBom(null)
                    }}
                  />
                </>
              ) : (
                <>
                  <Select
                    showSearch
                    allowClear
                    placeholder="选择套装（B:XXXXXX）"
                    options={bundleTemplateOptions as any}
                    value={bundleDraft.bundle_code ?? undefined}
                    loading={bundleTemplatesQuery.isLoading}
                    onChange={(v) => setBundleDraft((d) => ({ ...d, bundle_code: (v as string) ?? null }))}
                    style={{ width: '100%' }}
                  />
                  <Input.TextArea
                    rows={4}
                    placeholder="交易规格（可选）：用于触发词/特征串（不会解析尺寸）"
                    value={bundleDraft.spec_text}
                    onChange={(e) => setBundleDraft((d) => ({ ...d, spec_text: e.target.value }))}
                  />
                </>
              )}

              {mode === 'single' && bundleTokenInSpec ? (
                <Alert
                  type="success"
                  showIcon
                  message={`检测到套装编码：${bundleTokenInSpec}`}
                  description="将优先按交易规格中的 BUNDLE 编码生成合并BOM（无需选择模型/版本，也不解析尺寸）。"
                />
              ) : null}

              {mode === 'single' ? (
                <>
                  {!draft.model_id ? (
                    <Alert type="info" showIcon message="提示：先选择一个标准模型，再选择“已发布标准版本”用于预演。" />
                  ) : !showAllStandardVersions && selectableStandardVersions.length === 0 ? (
                    <Alert
                      type="warning"
                      showIcon
                      message="该模型暂无已发布标准版本（published）。请先发布标准版本，否则无法用于生产级预演。"
                    />
                  ) : null}

                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      版本候选：
                      {showAllStandardVersions ? '全部标准版本（含 draft/archived）' : '仅 published 标准版本'}
                    </Text>
                    <Button
                      size="small"
                      onClick={() => {
                        setShowAllStandardVersions((v) => !v)
                        setDraft((d) => ({ ...d, model_version_id: null }))
                        setBom(null)
                      }}
                    >
                      {showAllStandardVersions ? '切回仅 published' : '显示全部标准版本'}
                    </Button>
                  </div>
                  {showAllStandardVersions ? (
                    <Alert
                      type="info"
                      showIcon
                      message="你正在使用“全部标准版本”模式：允许选择 draft/archived 用于测试预演（不代表可用于生产）。"
                    />
                  ) : null}
                </>
              ) : null}

              {mode === 'single' ? (
                <Input.TextArea
                  rows={4}
                  placeholder="粘贴运营的交易规格（spec_text）"
                  value={draft.spec_text}
                  onChange={(e) => setDraft((d) => ({ ...d, spec_text: e.target.value }))}
                />
              ) : null}

              <Space>
                <Button
                  onClick={() => {
                    setParsed(null)
                    setBom(null)
                    setLastError(null)
                  }}
                >
                  清空结果
                </Button>
                {mode === 'single' ? (
                  <>
                    <Button loading={parseMutation.isPending} onClick={() => parseMutation.mutate()}>
                      仅解析（spec/parse）
                    </Button>
                    <Button type="primary" loading={previewMutation.isPending} onClick={() => previewMutation.mutate()}>
                      解析 + 预演 BOM（bom/generate）
                    </Button>
                  </>
                ) : (
                  <Button type="primary" loading={bundlePreviewMutation.isPending} onClick={() => bundlePreviewMutation.mutate()}>
                    套装：预演 BOM（B:编码）
                  </Button>
                )}
              </Space>

              {lastError ? <Alert type="error" showIcon message="执行失败" description={lastError} /> : null}

              <Divider style={{ margin: '8px 0' }} />

              {mode === 'single' ? (
                <Descriptions size="small" column={1} bordered>
                  <Descriptions.Item label="模型">
                    {selectedModel ? (
                      <Space size={8}>
                        <Text strong>{selectedModel.model_code}</Text>
                        <Text>{selectedModel.model_name}</Text>
                      </Space>
                    ) : (
                      <Text type="secondary">未选择</Text>
                    )}
                  </Descriptions.Item>
                  <Descriptions.Item label="版本">
                    {selectedVersion ? (
                      <Space size={8}>
                        <Text strong>{selectedVersion.version_label || selectedVersion.id}</Text>
                        {String(selectedVersion.version_status) === 'published' ? (
                          <Tag color="green">published</Tag>
                        ) : (
                          <Tag color="orange">{String(selectedVersion.version_status || 'draft')}</Tag>
                        )}
                      </Space>
                    ) : (
                      <Text type="secondary">未选择</Text>
                    )}
                  </Descriptions.Item>
                </Descriptions>
              ) : (
                <Descriptions size="small" column={1} bordered>
                  <Descriptions.Item label="套装">
                    {bundleDraft.bundle_code ? <Text code>{`B:${bundleDraft.bundle_code}`}</Text> : <Text type="secondary">未选择</Text>}
                  </Descriptions.Item>
                </Descriptions>
              )}
            </Space>
          </Card>
        </Col>

        <Col xs={24} lg={14}>
          <Card title="诊断结果（只读）">
            <Tabs
              items={[
                ...(mode === 'single'
                  ? ([
                      {
                        key: 'parse',
                        label: '解析结果',
                        children: parsed ? (
                          <>
                            <Space wrap style={{ marginBottom: 8 }}>
                              <Tag color="blue">tokens: {(parsed.tokens ?? []).length}</Tag>
                              {parsed.width_cm != null ? <Tag>宽(cm)：{String(parsed.width_cm)}</Tag> : null}
                              {parsed.height_cm != null ? <Tag>高(cm)：{String(parsed.height_cm)}</Tag> : null}
                              {parsed.area_m2 != null ? <Tag>面积(m²)：{String(parsed.area_m2)}</Tag> : null}
                              {parsed.perimeter_m != null ? <Tag>周长(m)：{String(parsed.perimeter_m)}</Tag> : null}
                            </Space>
                            <pre style={{ whiteSpace: 'pre-wrap', margin: 0 }}>{JSON.stringify(parsed, null, 2)}</pre>
                          </>
                        ) : (
                          <Text type="secondary">暂无（先点“仅解析”或“解析+预演”）</Text>
                        ),
                      },
                      {
                        key: 'matched',
                        label: '命中情况',
                        children: bom ? (
                    <>
                      <Space wrap style={{ marginBottom: 8 }}>
                        {variantsByBaseLineQuery.isLoading ? <Tag>加载规则详情中…</Tag> : null}
                        {versionLinesQuery.isLoading ? <Tag>加载基准清单中…</Tag> : null}
                      </Space>
                      <Table
                        rowKey={(r: any, idx) => String(r?.variant_id ?? idx)}
                        size="small"
                        pagination={false}
                        dataSource={matchedVariants}
                        columns={[
                          {
                            title: '触发条件',
                            key: 'trigger',
                            width: 320,
                            render: (_: any, r: any) => {
                              const v = variantMap.get(String(r?.variant_id ?? ''))
                              return <Text>{formatTrigger((v as any)?.conditions)}</Text>
                            },
                          },
                          {
                            title: '基准物料',
                            key: 'base_material',
                            width: 220,
                            render: (_: any, r: any) => {
                              const base = baseLineMaterialMap.get(String(r?.base_line_id ?? ''))
                              if (!base) return <Text type="secondary">-</Text>
                              return (
                                <Space size={6}>
                                  <Text code>{String(base.material_code ?? base.material_ref_id ?? '-')}</Text>
                                  <Text>{String(base.material_name ?? '')}</Text>
                                </Space>
                              )
                            },
                          },
                          {
                            title: '替换物料',
                            key: 'target_material',
                            width: 240,
                            render: (_: any, r: any) => {
                              const v = variantMap.get(String(r?.variant_id ?? ''))
                              const it = (v?.items ?? [])[0]
                              if (!it) return <Text type="secondary">-</Text>
                              return (
                                <Space size={6}>
                                  <Text code>{String(it.material_code ?? it.material_ref_id ?? '-')}</Text>
                                  <Text>{String(it.material_name ?? '')}</Text>
                                  {it.unit_of_measure ? <Tag>{String(it.unit_of_measure)}</Tag> : null}
                                </Space>
                              )
                            },
                          },
                          { title: 'variant_id', dataIndex: 'variant_id', width: 240, render: (v) => <Text code>{String(v)}</Text> },
                          { title: 'base_line_id', dataIndex: 'base_line_id', width: 240, render: (v) => <Text code>{String(v)}</Text> },
                          { title: 'action', dataIndex: 'action', width: 120 },
                          {
                            title: 'matched',
                            dataIndex: 'matched',
                            width: 90,
                            render: (v) => (v ? <Tag color="green">true</Tag> : <Tag>false</Tag>),
                          },
                          { title: 'effect', dataIndex: 'effect', width: 120, render: (v) => String(v ?? '') },
                        ]}
                      />
                      <Divider style={{ margin: '12px 0' }} />
                      <Text type="secondary">trace（完整）</Text>
                      <pre style={{ whiteSpace: 'pre-wrap', margin: '6px 0 0' }}>
                        {JSON.stringify(bom.trace ?? {}, null, 2)}
                      </pre>
                    </>
                  ) : (
                    <Text type="secondary">暂无（先点“解析+预演”）</Text>
                  ),
                      },
                    ] as any[])
                  : []),
                {
                  key: 'bom',
                  label: '最终 BOM（final_material_lines）',
                  children: bom ? (
                    <Space direction="vertical" style={{ width: '100%' }} size={12}>
                      <Descriptions bordered size="small" column={3}>
                        <Descriptions.Item label="合计成本（CNY）">
                          <b>{formatMoney2(costingSummary?.total_cost)}</b>
                        </Descriptions.Item>
                        <Descriptions.Item label="物料成本（CNY）">{formatMoney2(costingSummary?.material_cost_total)}</Descriptions.Item>
                        <Descriptions.Item label="工序成本（CNY）">{formatMoney2(costingSummary?.process_cost_total)}</Descriptions.Item>
                        <Descriptions.Item label="制造费用（CNY，30%）">{formatMoney2(costingSummary?.overhead_cost)}</Descriptions.Item>
                        <Descriptions.Item label="制造费率">{costingSummary ? '30%' : '-'}</Descriptions.Item>
                        <Descriptions.Item label="单位成本（CNY/件）">{formatMoney2(costingSummary?.unit_cost)}</Descriptions.Item>
                        <Descriptions.Item label="已计价物料行">{String(costingSummary?.priced_material_lines ?? '-')}</Descriptions.Item>
                        <Descriptions.Item label="缺物料单价行">{String(costingSummary?.missing_price_material_lines ?? '-')}</Descriptions.Item>
                        <Descriptions.Item label="缺工序单价行">{String(costingSummary?.missing_price_process_lines ?? '-')}</Descriptions.Item>
                      </Descriptions>

                      <Divider style={{ margin: '4px 0' }} />
                      <Text strong>物料（{finalLines.length}）</Text>
                      <Table
                        rowKey={(r) =>
                          String((r as any)?.id ?? `${(r as any)?.material_ref_id ?? ''}-${(r as any)?.sequence_order ?? ''}`)
                        }
                        size="small"
                        pagination={false}
                        dataSource={finalLines}
                        columns={[
                          { title: '编码', dataIndex: 'material_code', width: 140, render: (v) => v ?? '-' },
                          { title: '名称', dataIndex: 'material_name', render: (v) => v ?? '-' },
                          { title: '数量', dataIndex: 'computed_quantity', width: 120, render: (v) => (v == null ? '-' : String(v)) },
                          { title: '单位', dataIndex: 'unit_of_measure', width: 90, render: (v) => v ?? '-' },
                          { title: '计量方式', dataIndex: 'calculation_method', width: 110, render: (v) => String(v ?? '-') },
                          { title: '损耗%', dataIndex: 'loss_rate', width: 90, render: (v) => (v == null ? '-' : String(v)) },
                          { title: 'BOM单价', dataIndex: 'bom_unit_price', width: 110, render: (v) => formatMoney2(v) },
                          { title: '行成本', dataIndex: 'line_cost', width: 110, render: (v) => formatMoney2(v) },
                        ]}
                      />

                      <Divider style={{ margin: '4px 0' }} />
                      <Text strong>工序（{processLines.length}）</Text>
                      {processLines.length ? (
                        <Table
                          size="small"
                          pagination={false}
                          rowKey={(r) => String((r as any).process_id ?? '') + '-' + String((r as any).process_code ?? '')}
                          columns={[
                            { title: '工序编码', dataIndex: 'process_code', width: 120, ellipsis: true },
                            { title: '工序名称', dataIndex: 'process_name', ellipsis: true },
                            { title: '班组', dataIndex: 'team_name', width: 110, ellipsis: true },
                            { title: '计量', dataIndex: 'pricing_method', width: 90 },
                            { title: '计量值', dataIndex: 'measure_quantity', width: 90 },
                            { title: '计价', dataIndex: 'cost_type', width: 90 },
                            { title: '分钟', dataIndex: 'total_minutes', width: 90 },
                            { title: '分钟单价', dataIndex: 'rate_per_minute', width: 90 },
                            { title: '计件单价', dataIndex: 'piece_rate', width: 90 },
                            { title: '行成本', dataIndex: 'total_cost', width: 110, render: (v) => formatMoney2(v) },
                            {
                              title: '警告',
                              dataIndex: 'warnings',
                              width: 220,
                              render: (v) =>
                                Array.isArray(v) && v.length ? <Text type="warning">{String(v.join('；'))}</Text> : '-',
                            },
                          ]}
                          dataSource={processLines}
                        />
                      ) : (
                        <Alert type="info" showIcon message="该版本未返回工序明细（可能未配置工序行或后端未回传）。" />
                      )}

                      <Divider style={{ margin: '4px 0' }} />
                      <Text strong>扣库清单（真实物料展开）</Text>
                      {Array.isArray((bom?.trace as any)?.inventory?.warnings) && ((bom?.trace as any)?.inventory?.warnings ?? []).length ? (
                        <Alert
                          style={{ marginTop: 8 }}
                          type="warning"
                          showIcon
                          message="扣库展开存在提示（可能导致部分物料未展开）"
                          description={String(((bom?.trace as any)?.inventory?.warnings ?? []).slice(0, 5).join('；'))}
                        />
                      ) : null}
                      {inventoryLines.length ? (
                        <Table
                          size="small"
                          pagination={false}
                          rowKey={(r) => String((r as any)?.material_code ?? '')}
                          columns={[
                            { title: '物料编码', dataIndex: 'material_code', width: 140, ellipsis: true },
                            { title: '物料名称', dataIndex: 'material_name', ellipsis: true },
                            { title: '单位', dataIndex: 'unit_of_measure', width: 90 },
                            { title: '扣库数量', dataIndex: 'quantity', width: 140 },
                            {
                              title: '来源(展开)',
                              dataIndex: 'sources',
                              width: 110,
                              render: (v) => (Array.isArray(v) ? v.length : 0),
                            },
                          ]}
                          dataSource={inventoryLines}
                        />
                      ) : (
                        <Alert
                          type="info"
                          showIcon
                          message="暂未生成扣库清单（真实物料展开）。"
                          description="当前“物料”表可能包含虚拟物料（VM）。若需要对账/扣库，请以“扣库清单（真实物料展开）”为准。"
                        />
                      )}
                    </Space>
                  ) : (
                    <Text type="secondary">暂无（先点“解析+预演”）</Text>
                  ),
                },
              ]}
            />
          </Card>
        </Col>
      </Row>
    </div>
  )
}


