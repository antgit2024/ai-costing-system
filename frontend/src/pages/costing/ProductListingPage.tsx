import { useMemo, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Alert, Button, Card, Col, Descriptions, Divider, Input, Row, Select, Space, Table, Tabs, Tag, Typography, message } from 'antd'

import { fetchProductModels, fetchProductModelVersions, generateBom, parseSpec } from '@/services/planner'
import type { BomGenerateResponse, ProductModel, ProductModelVersionRead, SpecParseResponse } from '@/types/planner'

const { Text } = Typography

type ProductListingDraft = {
  sku_code: string
  model_id: string | null
  model_version_id: string | null
  spec_text: string
}

export default function ProductListingPage() {
  const [draft, setDraft] = useState<ProductListingDraft>({
    sku_code: '',
    model_id: null,
    model_version_id: null,
    spec_text: '',
  })

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

  const selectedModel = useMemo(() => models.find((m) => m.id === draft.model_id) ?? null, [models, draft.model_id])
  const selectedVersion = useMemo(
    () => selectableStandardVersions.find((v) => v.id === draft.model_version_id) ?? null,
    [selectableStandardVersions, draft.model_version_id],
  )

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
      const model_version_id = String(draft.model_version_id ?? '').trim()
      if (!model_version_id) throw new Error('请先选择“已发布标准版本”')
      if (!spec_text) throw new Error('请先输入交易规格（spec_text）')
      setLastError(null)

      const parsedRes = await parseSpec({ spec_text, sku_code: draft.sku_code || undefined })
      setParsed(parsedRes)

      const bomRes = await generateBom({
        spec_text,
        model_version_id,
        sku_code: draft.sku_code || undefined,
        quantity: 1,
      })
      setBom(bomRes)
      return bomRes
    },
    onSuccess: () => message.success('解析+预演完成'),
    onError: (e: any) => setLastError(String(e?.message ?? e)),
  })

  const matchedVariants = useMemo(() => {
    const traceAny = (bom?.trace ?? {}) as any
    const arr = traceAny?.matched_variants
    return Array.isArray(arr) ? arr : []
  }, [bom])

  const finalLines = useMemo(() => bom?.final_material_lines ?? [], [bom])

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
              <Input
                placeholder="货品编码（可选，仅用于标记/复制）"
                value={draft.sku_code}
                onChange={(e) => setDraft((d) => ({ ...d, sku_code: e.target.value }))}
              />

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
                  return (
                    String(raw.model_code ?? '').toLowerCase().includes(q) ||
                    String(raw.model_name ?? '').toLowerCase().includes(q)
                  )
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

              <Input.TextArea
                rows={4}
                placeholder="粘贴运营的交易规格（spec_text）"
                value={draft.spec_text}
                onChange={(e) => setDraft((d) => ({ ...d, spec_text: e.target.value }))}
              />

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
                <Button loading={parseMutation.isPending} onClick={() => parseMutation.mutate()}>
                  仅解析（spec/parse）
                </Button>
                <Button
                  type="primary"
                  loading={previewMutation.isPending}
                  onClick={() => previewMutation.mutate()}
                >
                  解析 + 预演 BOM（bom/generate）
                </Button>
              </Space>

              {lastError ? <Alert type="error" showIcon message="执行失败" description={lastError} /> : null}

              <Divider style={{ margin: '8px 0' }} />

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
                      <Tag color="green">published</Tag>
                    </Space>
                  ) : (
                    <Text type="secondary">未选择</Text>
                  )}
                </Descriptions.Item>
              </Descriptions>
            </Space>
          </Card>
        </Col>

        <Col xs={24} lg={14}>
          <Card title="诊断结果（只读）">
            <Tabs
              items={[
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
                      <pre style={{ whiteSpace: 'pre-wrap', margin: 0 }}>
                        {JSON.stringify(parsed, null, 2)}
                      </pre>
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
                      <Table
                        rowKey={(r: any, idx) => String(r?.variant_id ?? idx)}
                        size="small"
                        pagination={false}
                        dataSource={matchedVariants}
                        columns={[
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
                {
                  key: 'bom',
                  label: '最终 BOM（final_material_lines）',
                  children: bom ? (
                    <Table
                      rowKey={(r) => String((r as any)?.id ?? `${(r as any)?.material_ref_id ?? ''}-${(r as any)?.sequence_order ?? ''}`)}
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
                        { title: 'BOM单价', dataIndex: 'bom_unit_price', width: 110, render: (v) => (v == null ? '-' : String(v)) },
                        { title: '行成本', dataIndex: 'line_cost', width: 110, render: (v) => (v == null ? '-' : String(v)) },
                      ]}
                    />
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


