import { useEffect, useMemo, useState } from 'react'
import { Alert, Button, Card, Drawer, Input, InputNumber, Select, Space, Switch, Table, Tag, Tooltip, Typography, message } from 'antd'
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

type MetricOp = 'off' | 'gte' | 'lte' | 'eq' | 'between'

const FIXED_ACTION: LineVariantAction = 'replace_self'
const STABLE_SHAPE_LABEL = '最稳形态：replace_self + 同单位 1→1（启用前必须预演成功）'

const asStringArray = (v: unknown): string[] => (Array.isArray(v) ? v.map((x) => String(x)).filter(Boolean) : [])

const toNumber = (v: any, fallback = 0): number => {
  const n = Number(v)
  return Number.isFinite(n) ? n : fallback
}

const normalizeUnit = (u: unknown): string | null => {
  const s = String(u ?? '').trim()
  return s ? s : null
}

const asBetween = (v: any): [number | null, number | null] | null => {
  if (!Array.isArray(v) || v.length < 2) return null
  const a = v[0]
  const b = v[1]
  const min = a == null || a === '' ? null : Number(a)
  const max = b == null || b === '' ? null : Number(b)
  const minOk = min == null || Number.isFinite(min)
  const maxOk = max == null || Number.isFinite(max)
  if (!minOk || !maxOk) return null
  return [min, max]
}

const betweenToPayload = (pair: [number | null, number | null] | null): [number | null, number | null] | undefined => {
  if (!pair) return undefined
  const [min, max] = pair
  if (min == null && max == null) return undefined
  return [min ?? null, max ?? null]
}

const opFromBetween = (pair: [number | null, number | null] | null): MetricOp => {
  if (!pair) return 'off'
  const [min, max] = pair
  if (min == null && max == null) return 'off'
  if (min != null && max != null) return min === max ? 'eq' : 'between'
  if (min != null) return 'gte'
  return 'lte'
}

const applyOpToBetween = (
  op: MetricOp,
  current: [number | null, number | null] | null,
): [number | null, number | null] | null => {
  if (op === 'off') return null
  const [min, max] = current ?? [null, null]
  const seed = min ?? max ?? null
  if (op === 'gte') return [seed, null]
  if (op === 'lte') return [null, seed]
  if (op === 'eq') return [seed, seed]
  return [min, max]
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
  const [draftStopOnHit, setDraftStopOnHit] = useState(true)
  const [draftNotes, setDraftNotes] = useState('')
  const [draftContainsAny, setDraftContainsAny] = useState<string[]>([])
  const [draftContainsAll, setDraftContainsAll] = useState<string[]>([])
  const [draftWidthBetween, setDraftWidthBetween] = useState<[number | null, number | null] | null>(null)
  const [draftHeightBetween, setDraftHeightBetween] = useState<[number | null, number | null] | null>(null)
  const [draftAreaBetween, setDraftAreaBetween] = useState<[number | null, number | null] | null>(null)
  const [draftPerimeterBetween, setDraftPerimeterBetween] = useState<[number | null, number | null] | null>(null)
  const [draftWidthOp, setDraftWidthOp] = useState<MetricOp>('off')
  const [draftHeightOp, setDraftHeightOp] = useState<MetricOp>('off')
  const [draftAreaOp, setDraftAreaOp] = useState<MetricOp>('off')
  const [draftPerimeterOp, setDraftPerimeterOp] = useState<MetricOp>('off')
  const [draftItems, setDraftItems] = useState<EditableItemRow[]>([])

  const [specText, setSpecText] = useState('')
  const [specParsed, setSpecParsed] = useState<SpecParseResponse | null>(null)
  const [bomPreview, setBomPreview] = useState<BomGenerateResponse | null>(null)
  const [lastPreviewAt, setLastPreviewAt] = useState<number | null>(null)
  const [lastPreviewOk, setLastPreviewOk] = useState<boolean | null>(null)
  const [lastPreviewError, setLastPreviewError] = useState<string | null>(null)
  const [lastPreviewSummary, setLastPreviewSummary] = useState<{
    spec_text: string
    tokens_count: number
    final_lines_count: number
    trace_keys: number
    base_unit: string | null
    target_unit: string | null
    width_cm: string | number | null
    height_cm: string | number | null
    area_m2: string | number | null
    perimeter_m: string | number | null
  } | null>(null)
  const [lastPreviewFingerprint, setLastPreviewFingerprint] = useState<string | null>(null)

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
    setDraftStopOnHit(!!selectedVariant.stop_on_hit)
    setDraftNotes(String(selectedVariant.notes ?? ''))
    const cond = (selectedVariant.conditions ?? {}) as any
    setDraftContainsAny(asStringArray(cond.spec_contains_any))
    setDraftContainsAll(asStringArray(cond.spec_contains_all))
    const wb = asBetween(cond.width_between)
    const hb = asBetween(cond.height_between)
    const ab = asBetween(cond.area_between)
    const pb = asBetween(cond.perimeter_between)
    setDraftWidthBetween(wb)
    setDraftHeightBetween(hb)
    setDraftAreaBetween(ab)
    setDraftPerimeterBetween(pb)
    setDraftWidthOp(opFromBetween(wb))
    setDraftHeightOp(opFromBetween(hb))
    setDraftAreaOp(opFromBetween(ab))
    setDraftPerimeterOp(opFromBetween(pb))
    setDraftItems(buildEditableItems(selectedVariant.items as any))
  }, [open, selectedVariant])

  useEffect(() => {
    if (!open) return
    setSpecParsed(null)
    setBomPreview(null)
    setLastPreviewAt(null)
    setLastPreviewOk(null)
    setLastPreviewError(null)
    setLastPreviewSummary(null)
    setLastPreviewFingerprint(null)
  }, [open, versionId, baseLineId])

  const conditionRows = useMemo(() => {
    return [
      { key: 'token_any', field: 'token_any', label: 'token(any)', operator: '包含任一', unit: '', valueKind: 'tokens' },
      { key: 'token_all', field: 'token_all', label: 'token(all)', operator: '包含全部', unit: '', valueKind: 'tokens' },
      { key: 'width', field: 'width', label: '宽度', operator: draftWidthOp, unit: 'cm', valueKind: 'metric' },
      { key: 'height', field: 'height', label: '高度', operator: draftHeightOp, unit: 'cm', valueKind: 'metric' },
      { key: 'area', field: 'area', label: '面积', operator: draftAreaOp, unit: 'm²', valueKind: 'metric' },
      { key: 'perimeter', field: 'perimeter', label: '周长', operator: draftPerimeterOp, unit: 'm', valueKind: 'metric' },
    ]
  }, [draftWidthOp, draftHeightOp, draftAreaOp, draftPerimeterOp])

  const normalizedDraftItemsForFingerprint = useMemo(
    () =>
      draftItems.map((r) => ({
        material_kind: r.material_kind ?? 'real',
        material_ref_id: String(r.material_ref_id ?? '').trim() || null,
        base_quantity: toNumber(r.base_quantity, 0),
        fixed_quantity: toNumber(r.fixed_quantity, 0),
        coverage_ratio: toNumber(r.coverage_ratio, 1),
        loss_rate: toNumber(r.loss_rate, 0),
      })),
    [draftItems],
  )

  const currentPreviewFingerprint = useMemo(() => {
    const payload = {
      versionId,
      baseLineId,
      selectedVariantId,
      action: FIXED_ACTION,
      stop_on_hit: draftStopOnHit,
      conditions: {
        spec_contains_any: draftContainsAny,
        spec_contains_all: draftContainsAll,
        width_between: betweenToPayload(draftWidthBetween),
        height_between: betweenToPayload(draftHeightBetween),
        area_between: betweenToPayload(draftAreaBetween),
        perimeter_between: betweenToPayload(draftPerimeterBetween),
      },
      items: normalizedDraftItemsForFingerprint,
      spec_text: String(specText ?? '').trim(),
    }
    return JSON.stringify(payload)
  }, [
    versionId,
    baseLineId,
    selectedVariantId,
    draftStopOnHit,
    draftContainsAny,
    draftContainsAll,
    draftWidthBetween,
    draftHeightBetween,
    draftAreaBetween,
    draftPerimeterBetween,
    normalizedDraftItemsForFingerprint,
    specText,
  ])

  const previewStale = useMemo(() => {
    if (!lastPreviewOk) return false
    if (!lastPreviewFingerprint) return true
    return lastPreviewFingerprint !== currentPreviewFingerprint
  }, [lastPreviewOk, lastPreviewFingerprint, currentPreviewFingerprint])

  const baseUnitFromBom = useMemo(() => {
    const lines = (bomPreview?.final_material_lines ?? []) as any[]
    const baseLine = lines.find((r) => String(r?.source_type) === 'base_line' && String(r?.base_line_id ?? '') === String(baseLineId))
    return normalizeUnit(baseLine?.unit_of_measure)
  }, [bomPreview, baseLineId])

  const targetUnitFromItems = useMemo(() => normalizeUnit(draftItems?.[0]?.unit_of_measure), [draftItems])

  const unitMismatch = useMemo(() => {
    const baseU = baseUnitFromBom
    const targetU = targetUnitFromItems
    if (!baseU || !targetU) return null
    if (baseU !== targetU) return { base: baseU, target: targetU }
    return null
  }, [baseUnitFromBom, targetUnitFromItems])

  const enableBlockReason = useMemo((): string | null => {
    // 1) 必须 1→1
    if (draftItems.length !== 1) return '最稳形态只允许 1→1：请确保 items 仅 1 行目标物料'
    const targetRefId = String(draftItems?.[0]?.material_ref_id ?? '').trim()
    if (!targetRefId) return '请先填写目标物料 material_ref_id（并保存清单让后端回填单位）'

    // 2) 必须预演成功且不过期
    if (!lastPreviewOk) return '启用前必须先预演成功（spec/parse + bom/generate）'
    if (previewStale) return '规则/清单/spec_text 已变更：请重新预演后再启用'

    // 2.1) 若配置了尺寸/面积/周长条件，则预演样例必须解析出对应数值（避免“没测过就启用”）
    if (betweenToPayload(draftWidthBetween) && (lastPreviewSummary?.width_cm == null || lastPreviewSummary?.width_cm === '')) {
      return '你配置了“宽度区间”条件，但预演样例未解析出宽度（请用包含尺寸的 spec_text 重新预演）'
    }
    if (betweenToPayload(draftHeightBetween) && (lastPreviewSummary?.height_cm == null || lastPreviewSummary?.height_cm === '')) {
      return '你配置了“高度区间”条件，但预演样例未解析出高度（请用包含尺寸的 spec_text 重新预演）'
    }
    if (betweenToPayload(draftAreaBetween) && (lastPreviewSummary?.area_m2 == null || lastPreviewSummary?.area_m2 === '')) {
      return '你配置了“面积区间”条件，但预演样例未解析出面积（请用包含尺寸/直径的 spec_text 重新预演）'
    }
    if (betweenToPayload(draftPerimeterBetween) && (lastPreviewSummary?.perimeter_m == null || lastPreviewSummary?.perimeter_m === '')) {
      return '你配置了“周长区间”条件，但预演样例未解析出周长（请用包含尺寸/直径的 spec_text 重新预演）'
    }

    // 3) 同计量单位校验（拿不到单位也要阻止）
    if (!baseUnitFromBom || !targetUnitFromItems) {
      return '单位信息缺失：请先“保存清单”（让后端回填 unit_of_measure），并确保主数据单位已补齐；然后重新预演'
    }
    if (unitMismatch) {
      return `单位不一致：基准行单位=${unitMismatch.base}，目标物料单位=${unitMismatch.target}（最稳形态仅允许同单位平替）`
    }

    return null
  }, [draftItems, lastPreviewOk, previewStale, baseUnitFromBom, targetUnitFromItems, unitMismatch])

  const handleToggleEnabled = (nextEnabled: boolean) => {
    if (!nextEnabled) {
      setDraftEnabled(false)
      return
    }
    if (!selectedVariantId) {
      message.warning('请先选择一条变体规则')
      return
    }
    if (enableBlockReason) {
      message.error(enableBlockReason)
      setDraftEnabled(false)
      return
    }
    setDraftEnabled(true)
  }

  const createVariantMutation = useMutation({
    mutationFn: async () => {
      const payload: LineVariantCreateRequest = {
        version_id: versionId,
        base_line_id: baseLineId,
        // 收口：新建规则默认不启用，必须预演通过后才能启用
        enabled: false,
        priority: 100,
        action: FIXED_ACTION,
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
      if (draftEnabled && enableBlockReason) {
        throw new Error(enableBlockReason)
      }
      const payload: LineVariantUpdateRequest = {
        enabled: draftEnabled,
        priority: draftPriority,
        // 收口：UI 固定 replace_self（最稳第一步）
        action: FIXED_ACTION,
        stop_on_hit: draftStopOnHit,
        notes: draftNotes || undefined,
        conditions: {
          spec_contains_any: draftContainsAny,
          spec_contains_all: draftContainsAll,
          width_between: draftWidthOp === 'off' ? undefined : betweenToPayload(draftWidthBetween),
          height_between: draftHeightOp === 'off' ? undefined : betweenToPayload(draftHeightBetween),
          area_between: draftAreaOp === 'off' ? undefined : betweenToPayload(draftAreaBetween),
          perimeter_between: draftPerimeterOp === 'off' ? undefined : betweenToPayload(draftPerimeterBetween),
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
      if (draftItems.length > 1) throw new Error('最稳形态只允许 1→1：items 仅允许 1 行目标物料')
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
      const now = Date.now()
      const baseU = (() => {
        const lines = (bom?.final_material_lines ?? []) as any[]
        const baseLine = lines.find((r) => String(r?.source_type) === 'base_line' && String(r?.base_line_id ?? '') === String(baseLineId))
        return normalizeUnit(baseLine?.unit_of_measure)
      })()
      const targetU = normalizeUnit(draftItems?.[0]?.unit_of_measure)
      setLastPreviewAt(now)
      setLastPreviewOk(true)
      setLastPreviewError(null)
      setLastPreviewFingerprint(currentPreviewFingerprint)
      setLastPreviewSummary({
        spec_text: String(specText ?? '').trim(),
        tokens_count: parsed.tokens?.length ?? 0,
        final_lines_count: (bom.final_material_lines ?? []).length,
        trace_keys: Object.keys(bom.trace ?? {}).length,
        base_unit: baseU,
        target_unit: targetU,
        width_cm: (parsed as any)?.width_cm ?? null,
        height_cm: (parsed as any)?.height_cm ?? null,
        area_m2: (parsed as any)?.area_m2 ?? null,
        perimeter_m: (parsed as any)?.perimeter_m ?? null,
      })
      message.success('预演完成')
    },
    onError: (err: any) => {
      const detail = err?.response?.data?.detail ?? err?.message ?? '预演失败'
      setLastPreviewAt(Date.now())
      setLastPreviewOk(false)
      setLastPreviewError(String(detail))
      setLastPreviewFingerprint(currentPreviewFingerprint)
      setLastPreviewSummary(null)
      message.error(String(detail))
    },
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
        <Alert
          type="info"
          showIcon
          message="行级变体已收口为 ERP 最稳第一步"
          description={
            <div style={{ fontSize: 12 }}>
              <div>
                <b>{STABLE_SHAPE_LABEL}</b>
              </div>
              <div style={{ color: '#8c8c8c' }}>
                口径唯一真相：DOC/costing/manuals/standard_model_variants_ops_rules.md（7.1/7.2）
              </div>
            </div>
          }
        />

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
          title={
            <Space size={8} wrap>
              <span>规则设置</span>
              <Tag color="blue">action=replace_self</Tag>
              <Tooltip title={STABLE_SHAPE_LABEL}>
                <Tag>最稳形态</Tag>
              </Tooltip>
              {lastPreviewOk ? (
                <Tag color={previewStale ? 'orange' : 'green'}>{previewStale ? '预演已过期' : '预演已通过'}</Tag>
              ) : lastPreviewOk === false ? (
                <Tag color="red">预演失败</Tag>
              ) : (
                <Tag>未预演</Tag>
              )}
              {lastPreviewAt ? <Text type="secondary" style={{ fontSize: 12 }}>最近预演：{new Date(lastPreviewAt).toLocaleString()}</Text> : null}
            </Space>
          }
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
                <Switch checked={draftEnabled} onChange={(v) => handleToggleEnabled(v)} />
              </Space>
              <Space>
                <Text>优先级</Text>
                <InputNumber min={0} value={draftPriority} onChange={(v) => setDraftPriority(toNumber(v, 100))} />
              </Space>
              <Space>
                <Text>动作</Text>
                <Tag color="blue" style={{ marginInlineStart: 0 }}>
                  replace_self
                </Tag>
              </Space>
              <Space>
                <Text>命中后停止</Text>
                <Switch checked={draftStopOnHit} onChange={(v) => setDraftStopOnHit(v)} />
              </Space>
            </Space>

            {draftEnabled && enableBlockReason ? (
              <Alert type="error" showIcon message="当前不满足启用门槛" description={enableBlockReason} />
            ) : null}

            <Space direction="vertical" size={6} style={{ width: '100%' }}>
              <Text type="secondary">条件（列表式：字段 / 运算符 / 值）</Text>

              <Alert
                type="info"
                showIcon
                message="条件输入口径"
                description={
                  <div style={{ fontSize: 12 }}>
                    <div>宽/高=cm，面积=m²，周长=m（来自 spec/parse）。</div>
                    <div style={{ color: '#8c8c8c' }}>
                      运营规范建议：边界尽量用整数并做离散档位（避免灰区），详见 `standard_model_variants_ops_rules.md`。
                    </div>
                  </div>
                }
              />

              <Table
                rowKey="key"
                size="small"
                pagination={false}
                dataSource={conditionRows as any[]}
                columns={[
                  { title: '字段', width: 120, dataIndex: 'label' },
                  {
                    title: '运算符',
                    width: 160,
                    render: (_: any, row: any) => {
                      if (row.valueKind === 'tokens') return <Tag>{row.operator}</Tag>
                      const op = row.operator as MetricOp
                      const setOp = (next: MetricOp) => {
                        if (row.field === 'width') {
                          setDraftWidthOp(next)
                          setDraftWidthBetween(applyOpToBetween(next, draftWidthBetween))
                          if (next === 'off') setDraftWidthBetween(null)
                        }
                        if (row.field === 'height') {
                          setDraftHeightOp(next)
                          setDraftHeightBetween(applyOpToBetween(next, draftHeightBetween))
                          if (next === 'off') setDraftHeightBetween(null)
                        }
                        if (row.field === 'area') {
                          setDraftAreaOp(next)
                          setDraftAreaBetween(applyOpToBetween(next, draftAreaBetween))
                          if (next === 'off') setDraftAreaBetween(null)
                        }
                        if (row.field === 'perimeter') {
                          setDraftPerimeterOp(next)
                          setDraftPerimeterBetween(applyOpToBetween(next, draftPerimeterBetween))
                          if (next === 'off') setDraftPerimeterBetween(null)
                        }
                      }
                      return (
                        <Select
                          size="small"
                          value={op}
                          style={{ width: 140 }}
                          options={[
                            { label: '关闭', value: 'off' },
                            { label: '≥', value: 'gte' },
                            { label: '≤', value: 'lte' },
                            { label: '=', value: 'eq' },
                            { label: '区间', value: 'between' },
                          ]}
                          onChange={(v) => setOp(v as MetricOp)}
                        />
                      )
                    },
                  },
                  {
                    title: '值',
                    render: (_: any, row: any) => {
                      if (row.field === 'token_any') {
                        return (
                          <Select
                            mode="tags"
                            value={draftContainsAny}
                            style={{ width: '100%' }}
                            placeholder="命中任意 token（OR）"
                            onChange={(v) => setDraftContainsAny(v)}
                          />
                        )
                      }
                      if (row.field === 'token_all') {
                        return (
                          <Select
                            mode="tags"
                            value={draftContainsAll}
                            style={{ width: '100%' }}
                            placeholder="必须包含所有 token（AND）"
                            onChange={(v) => setDraftContainsAll(v)}
                          />
                        )
                      }

                      const op = row.operator as MetricOp
                      const unit = String(row.unit ?? '')
                      const pair =
                        row.field === 'width'
                          ? draftWidthBetween
                          : row.field === 'height'
                            ? draftHeightBetween
                            : row.field === 'area'
                              ? draftAreaBetween
                              : draftPerimeterBetween
                      const min = pair?.[0] ?? null
                      const max = pair?.[1] ?? null
                      const setPair = (nextMin: number | null, nextMax: number | null) => {
                        const next: [number | null, number | null] = [nextMin, nextMax]
                        if (row.field === 'width') setDraftWidthBetween(next)
                        if (row.field === 'height') setDraftHeightBetween(next)
                        if (row.field === 'area') setDraftAreaBetween(next)
                        if (row.field === 'perimeter') setDraftPerimeterBetween(next)
                      }

                      if (op === 'off') return <Text type="secondary">-</Text>
                      if (op === 'between') {
                        return (
                          <Space wrap>
                            <InputNumber
                              size="small"
                              placeholder="min"
                              value={min}
                              onChange={(v) => setPair(v == null ? null : Number(v), max)}
                            />
                            <Text type="secondary">到</Text>
                            <InputNumber
                              size="small"
                              placeholder="max"
                              value={max}
                              onChange={(v) => setPair(min, v == null ? null : Number(v))}
                            />
                            <Text type="secondary">{unit}</Text>
                          </Space>
                        )
                      }
                      // gte/lte/eq: use single value input (we store in min/max accordingly)
                      const single = op === 'lte' ? max : min
                      const setSingle = (v: number | null) => {
                        const num = v == null ? null : Number(v)
                        if (op === 'gte') setPair(num, null)
                        if (op === 'lte') setPair(null, num)
                        if (op === 'eq') setPair(num, num)
                      }
                      return (
                        <Space wrap>
                          <InputNumber size="small" placeholder="value" value={single} onChange={(v) => setSingle(v == null ? null : Number(v))} />
                          <Text type="secondary">{unit}</Text>
                        </Space>
                      )
                    },
                  },
                ]}
              />

              <Alert
                type="warning"
                showIcon
                message="个数/数量条件"
                description={<span style={{ fontSize: 12 }}>当前后端条件 schema 未提供数量区间字段（例如 quantity_between），因此 UI 暂无法写入规则条件。若你确认必须支持“个数”，需要下一轮补后端字段；临时可用 token 离散化（如 QTY_1/QTY_2/QTY_GT_2）。</span>}
              />

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
          title={
            <Space size={8} wrap>
              <span>变体物料清单（1→1 同单位平替）</span>
              <Tag>仅 1 行目标物料</Tag>
              {baseUnitFromBom ? <Tag color="geekblue">基准单位：{baseUnitFromBom}</Tag> : <Tag>基准单位：未知</Tag>}
              {targetUnitFromItems ? <Tag color="geekblue">目标单位：{targetUnitFromItems}</Tag> : <Tag>目标单位：未知</Tag>}
              {unitMismatch ? <Tag color="red">单位不一致</Tag> : null}
            </Space>
          }
          extra={
            <Space>
              <Button
                size="small"
                disabled={!selectedVariantId || draftItems.length >= 1}
                onClick={() => {
                  if (!selectedVariantId) {
                    message.warning('请先选择一条变体规则')
                    return
                  }
                  if (draftItems.length >= 1) {
                    message.warning('最稳形态只允许 1→1：不允许新增第 2 行')
                    return
                  }
                  setDraftItems([
                    {
                      _tmpId: `tmp-${Date.now()}`,
                      sequence_order: 0,
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
                }}
              >
                设置目标物料
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
              提示：最稳形态要求“同单位 1→1”。请先保存清单让后端回填单位，再进行预演；启用前必须预演成功（见上方门槛提示）。
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
            {lastPreviewAt ? (
              <Alert
                type={lastPreviewOk ? (previewStale ? 'warning' : 'success') : 'error'}
                showIcon
                message={
                  lastPreviewOk
                    ? previewStale
                      ? '最近一次预演已过期（配置已变更）'
                      : '最近一次预演通过'
                    : '最近一次预演失败'
                }
                description={
                  <div style={{ fontSize: 12 }}>
                    <div>时间：{new Date(lastPreviewAt).toLocaleString()}</div>
                    {lastPreviewOk && lastPreviewSummary ? (
                      <>
                        <div>spec_text：{lastPreviewSummary.spec_text}</div>
                        <div>
                          tokens={lastPreviewSummary.tokens_count} · final_lines={lastPreviewSummary.final_lines_count} · trace_keys={lastPreviewSummary.trace_keys}
                        </div>
                        <div>
                          基准单位={lastPreviewSummary.base_unit ?? '未知'} · 目标单位={lastPreviewSummary.target_unit ?? '未知'}
                        </div>
                      </>
                    ) : (
                      <div>{lastPreviewError ?? '预演失败'}</div>
                    )}
                  </div>
                }
              />
            ) : (
              <Alert
                type="info"
                showIcon
                message="启用门槛：必须先预演成功"
                description={<span style={{ fontSize: 12 }}>建议保存清单（回填单位）→ 输入 spec_text → 预演通过 → 再启用。</span>}
              />
            )}

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


