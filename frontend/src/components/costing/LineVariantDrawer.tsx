import { useEffect, useMemo, useState } from 'react'
import { Button, Card, Drawer, Input, InputNumber, Select, Space, Switch, Table, Tag, Tooltip, Typography, message } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { DeleteOutlined, EditOutlined, PlayCircleOutlined, SaveOutlined } from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { createLineVariant, deleteLineVariant, generateBom, listLineVariants, parseSpec, replaceLineVariantItems, updateLineVariant } from '@/services/planner'
import type {
  BomGenerateResponse,
  LineVariantAction,
  LineVariantCreateRequest,
  LineVariantDetailRead,
  LineVariantItemPayload,
  LineVariantUpdateRequest,
  SpecParseResponse,
} from '@/types/planner'

const { Text } = Typography

export type LineVariantDrawerProps = {
  open: boolean
  onClose: () => void
  versionId: string
  baseLineId: string
  baseLineLabel?: string
}

type EditableItemRow = LineVariantItemPayload & {
  _tmpId: string
}

const DEFAULT_ACTION: LineVariantAction = 'replace_bundle'

const asStringArray = (v: unknown): string[] => (Array.isArray(v) ? v.map((x) => String(x)).filter(Boolean) : [])

const toNumber = (v: any, fallback = 0): number => {
  const n = Number(v)
  return Number.isFinite(n) ? n : fallback
}

const buildEditableItems = (items: Array<any>): EditableItemRow[] =>
  (items ?? []).map((it, idx) => ({
    _tmpId: String(it?.id ?? `tmp-${idx}-${Math.random().toString(16).slice(2)}`),
    sequence_order: it?.sequence_order ?? idx,
    material_kind: (it?.material_kind ?? 'real') as any,
    material_ref_id: it?.material_ref_id ?? '',
    material_code: it?.material_code ?? null,
    material_name: it?.material_name ?? null,
    unit_of_measure: it?.unit_of_measure ?? null,
    calculation_method: (it?.calculation_method ?? 'count') as any,
    base_quantity: toNumber(it?.base_quantity, 0),
    fixed_quantity: toNumber(it?.fixed_quantity, 0),
    coverage_ratio: toNumber(it?.coverage_ratio, 1),
    loss_rate: toNumber(it?.loss_rate, 0),
    metadata_json: (it?.metadata_json ?? it?.metadata ?? {}) as any,
  }))

export default function LineVariantDrawer(props: LineVariantDrawerProps) {
  const { open, onClose, versionId, baseLineId, baseLineLabel } = props
  const queryClient = useQueryClient()

  const [selectedVariantId, setSelectedVariantId] = useState<string | null>(null)
  const [draftEnabled, setDraftEnabled] = useState(true)
  const [draftPriority, setDraftPriority] = useState(100)
  const [draftAction, setDraftAction] = useState<LineVariantAction>(DEFAULT_ACTION)
  const [draftStopOnHit, setDraftStopOnHit] = useState(true)
  const [draftNotes, setDraftNotes] = useState('')
  const [draftContainsAny, setDraftContainsAny] = useState<string[]>([])
  const [draftContainsAll, setDraftContainsAll] = useState<string[]>([])
  const [draftItems, setDraftItems] = useState<EditableItemRow[]>([])

  const [specText, setSpecText] = useState('')
  const [specParsed, setSpecParsed] = useState<SpecParseResponse | null>(null)
  const [bomPreview, setBomPreview] = useState<BomGenerateResponse | null>(null)

  const variantsQuery = useQuery({
    queryKey: ['lineVariants', versionId, baseLineId],
    queryFn: () => listLineVariants({ version_id: versionId, base_line_id: baseLineId }),
    enabled: open && !!versionId && !!baseLineId,
  })

  const variants = (variantsQuery.data ?? []) as LineVariantDetailRead[]

  const selectedVariant = useMemo(
    () => variants.find((v) => v.id === selectedVariantId) ?? null,
    [selectedVariantId, variants],
  )

  useEffect(() => {
    if (!open) return
    // default select: first variant if any
    if (!selectedVariantId && variants.length > 0) {
      setSelectedVariantId(variants[0].id)
    }
  }, [open, variants, selectedVariantId])

  useEffect(() => {
    if (!open) return
    if (!selectedVariant) return
    setDraftEnabled(!!selectedVariant.enabled)
    setDraftPriority(toNumber(selectedVariant.priority, 100))
    setDraftAction((selectedVariant.action ?? DEFAULT_ACTION) as LineVariantAction)
    setDraftStopOnHit(!!selectedVariant.stop_on_hit)
    setDraftNotes(String(selectedVariant.notes ?? ''))
    const cond = (selectedVariant.conditions ?? {}) as any
    setDraftContainsAny(asStringArray(cond.spec_contains_any))
    setDraftContainsAll(asStringArray(cond.spec_contains_all))
    setDraftItems(buildEditableItems(selectedVariant.items as any))
  }, [open, selectedVariant])

  useEffect(() => {
    if (!open) return
    setSpecParsed(null)
    setBomPreview(null)
  }, [open, versionId, baseLineId])

  const createVariantMutation = useMutation({
    mutationFn: async () => {
      const payload: LineVariantCreateRequest = {
        version_id: versionId,
        base_line_id: baseLineId,
        enabled: true,
        priority: 100,
        action: DEFAULT_ACTION,
        stop_on_hit: true,
        notes: '',
        conditions: { spec_contains_any: [], spec_contains_all: [] },
        metadata_json: {},
        items: [],
        operator_id: 'planner-ui',
      }
      return await createLineVariant(versionId, payload)
    },
    onSuccess: async (created) => {
      message.success('已创建变体规则')
      await queryClient.invalidateQueries({ queryKey: ['lineVariants', versionId, baseLineId] })
      setSelectedVariantId(created.id)
    },
    onError: (err: any) => message.error(err?.response?.data?.detail ?? '创建失败'),
  })

  const saveVariantMutation = useMutation({
    mutationFn: async () => {
      if (!selectedVariantId) throw new Error('请先选择一条变体规则')
      const payload: LineVariantUpdateRequest = {
        enabled: draftEnabled,
        priority: draftPriority,
        action: draftAction,
        stop_on_hit: draftStopOnHit,
        notes: draftNotes || undefined,
        conditions: {
          spec_contains_any: draftContainsAny,
          spec_contains_all: draftContainsAll,
        },
        operator_id: 'planner-ui',
      }
      return await updateLineVariant(selectedVariantId, payload)
    },
    onSuccess: async () => {
      message.success('已保存规则设置')
      await queryClient.invalidateQueries({ queryKey: ['lineVariants', versionId, baseLineId] })
    },
    onError: (err: any) => message.error(err?.response?.data?.detail ?? '保存失败'),
  })

  const saveItemsMutation = useMutation({
    mutationFn: async () => {
      if (!selectedVariantId) throw new Error('请先选择一条变体规则')
      // normalize sequence order
      const items: LineVariantItemPayload[] = draftItems.map((r, idx) => ({
        sequence_order: idx,
        material_kind: (r.material_kind ?? 'real') as any,
        material_ref_id: String(r.material_ref_id ?? '').trim() || null,
        calculation_method: (r.calculation_method ?? 'count') as any,
        base_quantity: toNumber(r.base_quantity, 0),
        fixed_quantity: toNumber(r.fixed_quantity, 0),
        coverage_ratio: toNumber(r.coverage_ratio, 1),
        loss_rate: toNumber(r.loss_rate, 0),
        metadata_json: (r.metadata_json ?? {}) as any,
      }))
      return await replaceLineVariantItems(selectedVariantId, { items })
    },
    onSuccess: async (updated) => {
      message.success('已保存变体物料清单')
      await queryClient.invalidateQueries({ queryKey: ['lineVariants', versionId, baseLineId] })
      // keep edit state aligned with server (material_code/name filled by backend)
      setDraftItems(buildEditableItems(updated.items as any))
    },
    onError: (err: any) => message.error(err?.response?.data?.detail ?? '保存清单失败'),
  })

  const deleteVariantMutation = useMutation({
    mutationFn: async (variantId: string) => {
      await deleteLineVariant(variantId)
    },
    onSuccess: async () => {
      message.success('已删除')
      setSelectedVariantId(null)
      await queryClient.invalidateQueries({ queryKey: ['lineVariants', versionId, baseLineId] })
    },
    onError: (err: any) => message.error(err?.response?.data?.detail ?? '删除失败'),
  })

  const previewMutation = useMutation({
    mutationFn: async () => {
      const text = String(specText ?? '').trim()
      if (!text) throw new Error('请先输入 spec_text')
      const [parsed, bom] = await Promise.all([
        parseSpec({ spec_text: text }),
        generateBom({ spec_text: text, model_version_id: versionId }),
      ])
      return { parsed, bom }
    },
    onSuccess: ({ parsed, bom }) => {
      setSpecParsed(parsed)
      setBomPreview(bom)
      message.success('预演完成')
    },
    onError: (err: any) => message.error(err?.response?.data?.detail ?? err?.message ?? '预演失败'),
  })

  const itemColumns: ColumnsType<EditableItemRow> = [
    {
      title: '类型',
      width: 90,
      render: (_: any, r: any, idx) => (
        <Select
          size="small"
          value={r.material_kind}
          style={{ width: 84 }}
          options={[
            { label: 'real', value: 'real' },
            { label: 'bom', value: 'bom' },
            { label: 'virtual', value: 'virtual' },
          ]}
          onChange={(v) => {
            const next = draftItems.slice()
            next[idx] = { ...next[idx], material_kind: v as any }
            setDraftItems(next)
          }}
        />
      ),
    },
    {
      title: '物料ID',
      width: 220,
      render: (_: any, r: any, idx) => (
        <Input
          size="small"
          value={String(r.material_ref_id ?? '')}
          placeholder="material_ref_id（后端会回填编码/名称）"
          onChange={(e) => {
            const next = draftItems.slice()
            next[idx] = { ...next[idx], material_ref_id: e.target.value }
            setDraftItems(next)
          }}
        />
      ),
    },
    {
      title: '编码/名称',
      render: (_: any, r: any) => (
        <Space size={6}>
          {r.material_code ? <Tag>{String(r.material_code)}</Tag> : null}
          <span>{String(r.material_name ?? '-')}</span>
        </Space>
      ),
    },
    {
      title: '用量(β)',
      width: 110,
      render: (_: any, r: any, idx) => (
        <InputNumber
          size="small"
          min={0}
          value={toNumber(r.base_quantity, 0)}
          onChange={(v) => {
            const next = draftItems.slice()
            next[idx] = { ...next[idx], base_quantity: toNumber(v, 0) }
            setDraftItems(next)
          }}
          style={{ width: '100%' }}
        />
      ),
    },
    {
      title: '固定(α)',
      width: 110,
      render: (_: any, r: any, idx) => (
        <InputNumber
          size="small"
          min={0}
          value={toNumber(r.fixed_quantity, 0)}
          onChange={(v) => {
            const next = draftItems.slice()
            next[idx] = { ...next[idx], fixed_quantity: toNumber(v, 0) }
            setDraftItems(next)
          }}
          style={{ width: '100%' }}
        />
      ),
    },
    {
      title: '覆盖率',
      width: 100,
      render: (_: any, r: any, idx) => (
        <InputNumber
          size="small"
          min={0}
          max={1}
          step={0.1}
          value={toNumber(r.coverage_ratio, 1)}
          onChange={(v) => {
            const next = draftItems.slice()
            next[idx] = { ...next[idx], coverage_ratio: toNumber(v, 1) }
            setDraftItems(next)
          }}
          style={{ width: '100%' }}
        />
      ),
    },
    {
      title: '损耗%',
      width: 100,
      render: (_: any, r: any, idx) => (
        <InputNumber
          size="small"
          min={0}
          max={100}
          value={toNumber(r.loss_rate, 0)}
          onChange={(v) => {
            const next = draftItems.slice()
            next[idx] = { ...next[idx], loss_rate: toNumber(v, 0) }
            setDraftItems(next)
          }}
          style={{ width: '100%' }}
        />
      ),
    },
    {
      title: '',
      width: 44,
      render: (_: any, __: any, idx) => (
        <Button
          size="small"
          type="text"
          danger
          icon={<DeleteOutlined />}
          title="删除行"
          onClick={() => setDraftItems(draftItems.filter((_, i) => i !== idx))}
        />
      ),
    },
  ]

  const variantColumns: ColumnsType<LineVariantDetailRead> = [
    { title: '启用', width: 70, render: (_: any, r: any) => (r.enabled ? <Tag color="green">ON</Tag> : <Tag>OFF</Tag>) },
    { title: '优先级', width: 90, dataIndex: 'priority' },
    { title: '动作', width: 140, dataIndex: 'action', render: (v) => <Tag>{String(v)}</Tag> },
    {
      title: '条件',
      render: (_: any, r: any) => {
        const cond = (r.conditions ?? {}) as any
        const anyCnt = asStringArray(cond.spec_contains_any).length
        const allCnt = asStringArray(cond.spec_contains_all).length
        if (!anyCnt && !allCnt) return <span style={{ color: '#bfbfbf' }}>-</span>
        return (
          <Space size={6}>
            {anyCnt ? <Tag>any:{anyCnt}</Tag> : null}
            {allCnt ? <Tag>all:{allCnt}</Tag> : null}
          </Space>
        )
      },
    },
    { title: 'items', width: 70, render: (_: any, r: any) => (r.items?.length ?? 0) },
    {
      title: '操作',
      width: 110,
      render: (_: any, r: any) => (
        <Space size={6}>
          <Button size="small" icon={<EditOutlined />} onClick={() => setSelectedVariantId(r.id)}>
            编辑
          </Button>
          <Button
            size="small"
            danger
            type="text"
            icon={<DeleteOutlined />}
            onClick={() => deleteVariantMutation.mutate(r.id)}
          />
        </Space>
      ),
    },
  ]

  return (
    <Drawer
      title={
        <Space direction="vertical" size={0}>
          <div>物料行变体（Overlay）</div>
          <Text type="secondary" style={{ fontSize: 12 }}>
            version={versionId.slice(0, 8)}… · base_line_id={baseLineId.slice(0, 8)}… {baseLineLabel ? `· ${baseLineLabel}` : ''}
          </Text>
        </Space>
      }
      width={980}
      open={open}
      onClose={onClose}
      destroyOnClose
    >
      <Space direction="vertical" size={12} style={{ width: '100%' }}>
        <Card
          size="small"
          title="规则列表"
          extra={
            <Space>
              <Button size="small" type="primary" onClick={() => createVariantMutation.mutate()} loading={createVariantMutation.isPending}>
                新建规则
              </Button>
              <Button size="small" onClick={() => variantsQuery.refetch()} disabled={variantsQuery.isLoading}>
                刷新
              </Button>
            </Space>
          }
        >
          <Table
            rowKey="id"
            size="small"
            pagination={false}
            loading={variantsQuery.isLoading}
            dataSource={variants}
            columns={variantColumns}
            rowClassName={(r) => (r.id === selectedVariantId ? 'pm-selected-row' : '')}
            onRow={(r) => ({
              onClick: () => setSelectedVariantId(r.id),
              style: { cursor: 'pointer' },
            })}
          />
        </Card>

        <Card
          size="small"
          title="规则设置（最小字段）"
          extra={
            <Button
              size="small"
              type="primary"
              icon={<SaveOutlined />}
              disabled={!selectedVariantId}
              loading={saveVariantMutation.isPending}
              onClick={() => saveVariantMutation.mutate()}
            >
              保存设置
            </Button>
          }
        >
          <Space direction="vertical" size={10} style={{ width: '100%' }}>
            <Space wrap>
              <Space>
                <Text>启用</Text>
                <Switch checked={draftEnabled} onChange={(v) => setDraftEnabled(v)} />
              </Space>
              <Space>
                <Text>优先级</Text>
                <InputNumber min={0} value={draftPriority} onChange={(v) => setDraftPriority(toNumber(v, 100))} />
              </Space>
              <Space>
                <Text>动作</Text>
                <Select
                  value={draftAction}
                  style={{ width: 160 }}
                  options={[
                    { label: 'replace_bundle', value: 'replace_bundle' },
                    { label: 'replace_self', value: 'replace_self' },
                    { label: 'remove_self', value: 'remove_self' },
                    { label: 'add_siblings', value: 'add_siblings' },
                  ]}
                  onChange={(v) => setDraftAction(v as any)}
                />
              </Space>
              <Space>
                <Text>命中后停止</Text>
                <Switch checked={draftStopOnHit} onChange={(v) => setDraftStopOnHit(v)} />
              </Space>
            </Space>

            <Space direction="vertical" size={6} style={{ width: '100%' }}>
              <Text type="secondary">条件（MVP：仅 spec_contains_any / spec_contains_all）</Text>
              <Space wrap style={{ width: '100%' }}>
                <Tooltip title="命中任意 token 即触发（OR）">
                  <div style={{ width: 420 }}>
                    <Select
                      mode="tags"
                      value={draftContainsAny}
                      style={{ width: '100%' }}
                      placeholder="spec_contains_any（例如：黑色,无框）"
                      onChange={(v) => setDraftContainsAny(v)}
                    />
                  </div>
                </Tooltip>
                <Tooltip title="必须包含所有 token 才触发（AND）">
                  <div style={{ width: 420 }}>
                    <Select
                      mode="tags"
                      value={draftContainsAll}
                      style={{ width: '100%' }}
                      placeholder="spec_contains_all（例如：加厚,防水）"
                      onChange={(v) => setDraftContainsAll(v)}
                    />
                  </div>
                </Tooltip>
              </Space>

              <Input.TextArea
                value={draftNotes}
                onChange={(e) => setDraftNotes(e.target.value)}
                placeholder="备注（可选）"
                autoSize={{ minRows: 2, maxRows: 4 }}
              />
            </Space>
          </Space>
        </Card>

        <Card
          size="small"
          title="变体物料清单（整单替换 items）"
          extra={
            <Space>
              <Button
                size="small"
                onClick={() =>
                  setDraftItems([
                    ...draftItems,
                    {
                      _tmpId: `tmp-${Date.now()}`,
                      sequence_order: draftItems.length,
                      material_kind: 'real' as any,
                      material_ref_id: '',
                      calculation_method: 'count' as any,
                      base_quantity: 0,
                      fixed_quantity: 0,
                      coverage_ratio: 1,
                      loss_rate: 0,
                      metadata_json: {},
                    },
                  ])
                }
              >
                新增行
              </Button>
              <Button
                size="small"
                type="primary"
                icon={<SaveOutlined />}
                disabled={!selectedVariantId}
                loading={saveItemsMutation.isPending}
                onClick={() => saveItemsMutation.mutate()}
              >
                保存清单
              </Button>
            </Space>
          }
        >
          <Table
            rowKey={(r) => r._tmpId}
            size="small"
            pagination={false}
            dataSource={draftItems}
            columns={itemColumns}
          />
          <div style={{ marginTop: 8 }}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              提示：本轮 MVP 直接输入 material_ref_id；保存后后端会回填编码/名称/单位/计量方式并用于 BOM 预演。
            </Text>
          </div>
        </Card>

        <Card
          size="small"
          title="spec_text 预演（tokens + 最终 BOM）"
          extra={
            <Button
              size="small"
              type="primary"
              icon={<PlayCircleOutlined />}
              loading={previewMutation.isPending}
              onClick={() => previewMutation.mutate()}
            >
              预演
            </Button>
          }
        >
          <Space direction="vertical" size={10} style={{ width: '100%' }}>
            <Input.TextArea
              value={specText}
              onChange={(e) => setSpecText(e.target.value)}
              placeholder="输入 spec_text（例如：120*80 黑色 无框）"
              autoSize={{ minRows: 2, maxRows: 6 }}
            />

            <Card size="small" title="解析结果（tokens）">
              {specParsed ? (
                <Space direction="vertical" style={{ width: '100%' }} size={6}>
                  <Space wrap>
                    <Tag>tokens: {specParsed.tokens?.length ?? 0}</Tag>
                    {specParsed.width_cm != null ? <Tag>W(cm): {String(specParsed.width_cm)}</Tag> : null}
                    {specParsed.height_cm != null ? <Tag>H(cm): {String(specParsed.height_cm)}</Tag> : null}
                    {specParsed.area_m2 != null ? <Tag>area(m²): {String(specParsed.area_m2)}</Tag> : null}
                    {specParsed.perimeter_m != null ? <Tag>perimeter(m): {String(specParsed.perimeter_m)}</Tag> : null}
                  </Space>
                  <div>
                    {(specParsed.tokens ?? []).map((t) => (
                      <Tag key={t}>{t}</Tag>
                    ))}
                  </div>
                </Space>
              ) : (
                <Text type="secondary">暂无（点击“预演”后生成）</Text>
              )}
            </Card>

            <Card size="small" title="最终 BOM（final_material_lines）">
              {bomPreview ? (
                <Table
                  rowKey={(r: any) => `${r.line_index}-${r.variant_item_id ?? r.base_line_id ?? ''}`}
                  size="small"
                  pagination={false}
                  dataSource={(bomPreview.final_material_lines ?? []) as any[]}
                  columns={[
                    { title: '#', width: 48, dataIndex: 'line_index' },
                    { title: '来源', width: 100, dataIndex: 'source_type', render: (v) => <Tag>{String(v)}</Tag> },
                    { title: '编码', width: 130, dataIndex: 'material_code', render: (v) => v ?? '-' },
                    { title: '名称', dataIndex: 'material_name', render: (v) => v ?? '-' },
                    {
                      title: '数量',
                      width: 120,
                      dataIndex: 'computed_quantity',
                      render: (v) => (v != null ? String(v) : '-'),
                    },
                    { title: '单位', width: 80, dataIndex: 'unit_of_measure', render: (v) => v ?? '-' },
                  ]}
                />
              ) : (
                <Text type="secondary">暂无（点击“预演”后生成）</Text>
              )}
              {bomPreview?.trace ? (
                <div style={{ marginTop: 8 }}>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    trace（摘要）：{Object.keys(bomPreview.trace ?? {}).length} keys
                  </Text>
                  <pre style={{ whiteSpace: 'pre-wrap', margin: '6px 0 0', fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace' }}>
                    {JSON.stringify(bomPreview.trace ?? {}, null, 2)}
                  </pre>
                </div>
              ) : null}
            </Card>
          </Space>
        </Card>
      </Space>
    </Drawer>
  )
}

