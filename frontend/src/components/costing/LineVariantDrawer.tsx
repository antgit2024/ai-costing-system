import { useEffect, useMemo, useState } from 'react'
import { Alert, Button, Card, Drawer, Input, InputNumber, Modal, Select, Space, Switch, Table, Tag, Typography, message } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { DeleteOutlined, EditOutlined, PlayCircleOutlined } from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { createLineVariant, deleteLineVariant, generateBom, listLineVariants, parseSpec, replaceLineVariantItems, updateLineVariant } from '@/services/planner'
import MaterialSelectModal from './MaterialSelectModal'
import { normalizeUnit as normalizeUnitText } from '@/utils/unit'
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
type TriggerType = 'token' | 'width' | 'height' | 'area' | 'perimeter'

type ModalRuleRow = {
  key: string
  id?: string
  enabled: boolean
  // condition
  op: Exclude<MetricOp, 'off'>
  min: number | null
  max: number | null
  token_any: string[]
  token_all: string[]
  // item (1->1)
  item: EditableItemRow
}

const FIXED_ACTION: LineVariantAction = 'replace_self'
const STABLE_SHAPE_LABEL = '最稳形态：replace_self + 同单位 1→1（启用前必须预演成功）'

const asStringArray = (v: unknown): string[] => (Array.isArray(v) ? v.map((x) => String(x)).filter(Boolean) : [])

const toNumber = (v: any, fallback = 0): number => {
  const n = Number(v)
  return Number.isFinite(n) ? n : fallback
}

const normalizeUnit = (u: unknown): string | null => {
  const s = normalizeUnitText(String(u ?? ''))
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
  const [draftStopOnHit, setDraftStopOnHit] = useState(true)
  // legacy single-rule item editor removed; modal uses per-row item
  const [draftTriggerType, setDraftTriggerType] = useState<TriggerType>('token')

  const [editModalOpen, setEditModalOpen] = useState(false)
  const [materialPickerOpen, setMaterialPickerOpen] = useState(false)
  const [materialPickerRowKey, setMaterialPickerRowKey] = useState<string | null>(null)
  const [editMode, setEditMode] = useState<'create' | 'edit'>('edit')
  const [modalRows, setModalRows] = useState<ModalRuleRow[]>([])

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

  const inferTriggerType = (cond: any): TriggerType => {
    const anyCnt = asStringArray(cond?.spec_contains_any).length
    const allCnt = asStringArray(cond?.spec_contains_all).length
    if (anyCnt || allCnt) return 'token'
    if (cond?.perimeter_between) return 'perimeter'
    if (cond?.area_between) return 'area'
    if (cond?.width_between) return 'width'
    if (cond?.height_between) return 'height'
    return 'token'
  }

  const triggerLabel = (t: TriggerType): string => {
    if (t === 'token') return 'token（包含）'
    if (t === 'width') return '宽度（cm）'
    if (t === 'height') return '高度（cm）'
    if (t === 'area') return '面积（m²）'
    return '周长（m）'
  }

  const blankItemRow = (): EditableItemRow => ({
    _tmpId: `tmp-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    sequence_order: 0,
    material_kind: 'real' as any,
    material_ref_id: '',
    material_code: null,
    material_name: null,
    unit_of_measure: null,
    calculation_method: 'count' as any,
    // 避免默认=0 导致 preview 出现 “替换物料用量=0”的误导；用户仍可手工改回 0，但主路径不应是 0。
    base_quantity: 1,
    fixed_quantity: 0,
    coverage_ratio: 1,
    loss_rate: 0,
    metadata_json: {},
  })

  const rowFromVariant = (v: LineVariantDetailRead): ModalRuleRow => {
    const cond = (v.conditions ?? {}) as any
    const anyArr = asStringArray(cond.spec_contains_any)
    const allArr = asStringArray(cond.spec_contains_all)
    const key = v.id
    let op: Exclude<MetricOp, 'off'> = 'gte'
    let min: number | null = null
    let max: number | null = null
    const t = inferTriggerType(cond)
    if (t !== 'token') {
      const pair =
        t === 'width'
          ? asBetween(cond.width_between)
          : t === 'height'
            ? asBetween(cond.height_between)
            : t === 'area'
              ? asBetween(cond.area_between)
              : asBetween(cond.perimeter_between)
      const o = opFromBetween(pair)
      op = (o === 'off' ? 'gte' : o) as any
      min = pair?.[0] ?? null
      max = pair?.[1] ?? null
    }
    const item0 = buildEditableItems(((v.items ?? []) as any[]).slice(0, 1))[0] ?? blankItemRow()
    return {
      key,
      id: v.id,
      enabled: !!v.enabled,
      op,
      min,
      max,
      token_any: anyArr,
      token_all: allArr,
      item: item0,
    }
  }

  const rowToConditions = (trigger: TriggerType, row: ModalRuleRow): any => {
    if (trigger === 'token') {
      return { spec_contains_any: row.token_any, spec_contains_all: row.token_all }
    }
    const toPair = (): [number | null, number | null] | null => {
      const a = row.min
      const b = row.max
      if (row.op === 'between') return [a, b]
      if (row.op === 'gte') return [a, null]
      if (row.op === 'lte') return [null, b]
      return [a, a]
    }
    const pair = betweenToPayload(toPair())
    if (trigger === 'width') return { spec_contains_any: [], spec_contains_all: [], width_between: pair }
    if (trigger === 'height') return { spec_contains_any: [], spec_contains_all: [], height_between: pair }
    if (trigger === 'area') return { spec_contains_any: [], spec_contains_all: [], area_between: pair }
    return { spec_contains_any: [], spec_contains_all: [], perimeter_between: pair }
  }

  const invalidatePreview = () => {
    setSpecParsed(null)
    setBomPreview(null)
    setLastPreviewAt(null)
    setLastPreviewOk(null)
    setLastPreviewError(null)
    setLastPreviewSummary(null)
    setLastPreviewFingerprint(null)
  }

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
    setDraftStopOnHit(!!selectedVariant.stop_on_hit)
    const cond = (selectedVariant.conditions ?? {}) as any
    const inferred = inferTriggerType(cond)
    setDraftTriggerType(inferred)
  }, [open, selectedVariant])

  useEffect(() => {
    if (!editModalOpen) return
    // keep rows in sync with current trigger selection (simple filter view)
    const filtered = variants.filter((v) => inferTriggerType((v.conditions ?? {}) as any) === draftTriggerType)
    setModalRows(filtered.map((v) => rowFromVariant(v)))
  }, [editModalOpen, variants, draftTriggerType])

  useEffect(() => {
    if (!open) return
    invalidatePreview()
  }, [open, versionId, baseLineId])


  const openCreateModal = () => {
    setEditMode('create')
    setSelectedVariantId(null)
    // reset draft
    setDraftStopOnHit(true)
    setDraftTriggerType('token')
    setSpecText('')
    setSpecParsed(null)
    setBomPreview(null)
    setLastPreviewAt(null)
    setLastPreviewOk(null)
    setLastPreviewError(null)
    setLastPreviewSummary(null)
    setLastPreviewFingerprint(null)
    setEditModalOpen(true)
  }

  const openEditModal = (variantId: string) => {
    setEditMode('edit')
    setSelectedVariantId(variantId)
    const v = variants.find((x) => x.id === variantId)
    if (v) {
      const inferred = inferTriggerType((v.conditions ?? {}) as any)
      setDraftTriggerType(inferred)
    }
    setEditModalOpen(true)
  }

  // legacy buildConditionsPayload removed: modal uses rowToConditions per row

  const normalizedModalRowsForFingerprint = useMemo(
    () =>
      modalRows.map((r) => ({
        id: r.id ?? null,
        // 注意：fingerprint 不包含 enabled，否则“预演通过 → 打开启动”会被判定为预演过期（逻辑冲突）
        op: r.op,
        min: r.min ?? null,
        max: r.max ?? null,
        token_any: r.token_any ?? [],
        token_all: r.token_all ?? [],
        item: {
          material_kind: r.item?.material_kind ?? 'real',
          material_ref_id: String(r.item?.material_ref_id ?? '').trim() || null,
          base_quantity: toNumber(r.item?.base_quantity, 0),
          fixed_quantity: toNumber(r.item?.fixed_quantity, 0),
          coverage_ratio: toNumber(r.item?.coverage_ratio, 1),
          loss_rate: toNumber(r.item?.loss_rate, 0),
        },
      })),
    [modalRows],
  )

  const currentPreviewFingerprint = useMemo(() => {
    const payload = {
      versionId,
      baseLineId,
      selectedVariantId,
      action: FIXED_ACTION,
      stop_on_hit: draftStopOnHit,
      trigger_type: draftTriggerType,
      // 以弹窗多行规则为准（用于“预演是否过期”的判定）
      rules: normalizedModalRowsForFingerprint,
      spec_text: String(specText ?? '').trim(),
    }
    return JSON.stringify(payload)
  }, [
    versionId,
    baseLineId,
    selectedVariantId,
    draftStopOnHit,
    draftTriggerType,
    normalizedModalRowsForFingerprint,
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

  const baseLineParamsFromBom = useMemo(() => {
    const lines = (bomPreview?.final_material_lines ?? []) as any[]
    const baseLine = lines.find(
      (r) => String(r?.source_type) === 'base_line' && String(r?.base_line_id ?? '') === String(baseLineId),
    )
    return {
      calculation_method: (baseLine?.calculation_method ?? null) as any,
      base_quantity: baseLine?.base_quantity != null ? Number(baseLine.base_quantity) : null,
    }
  }, [bomPreview, baseLineId])

  // legacy enableBlockReason removed; enable gate is now per-row in modalSaveMutation/onChange

  const handleTriggerTypeChange = (next: TriggerType) => {
    setDraftTriggerType(next)
    // 预演结果会失效
    setLastPreviewOk(null)
    setLastPreviewAt(null)
    setLastPreviewError(null)
    setLastPreviewSummary(null)
    setLastPreviewFingerprint(null)
  }

  const modalSaveMutation = useMutation({
    mutationFn: async () => {
      const unitOfTrigger = draftTriggerType === 'area' ? 'm²' : draftTriggerType === 'perimeter' ? 'm' : 'cm'
      const needDim =
        draftTriggerType === 'width'
          ? 'width_cm'
          : draftTriggerType === 'height'
            ? 'height_cm'
            : draftTriggerType === 'area'
              ? 'area_m2'
              : draftTriggerType === 'perimeter'
                ? 'perimeter_m'
                : null

      const itemPayloadFromRow = (it: EditableItemRow): LineVariantItemPayload => ({
        sequence_order: 0,
        material_kind: (it.material_kind ?? 'real') as any,
        material_ref_id: String(it.material_ref_id ?? '').trim() || null,
        calculation_method: ((it.calculation_method ?? 'count') as any) ?? 'count',
        // 主路径：替换物料的 β 不应为 0（否则会导致 computed_quantity=0）；若用户没填/还是 0，则继承基准行 β
        base_quantity:
          toNumber(it.base_quantity, 0) > 0
            ? toNumber(it.base_quantity, 0)
            : baseLineParamsFromBom.base_quantity != null
              ? Number(baseLineParamsFromBom.base_quantity)
              : 1,
        fixed_quantity: toNumber(it.fixed_quantity, 0),
        coverage_ratio: toNumber(it.coverage_ratio, 1),
        loss_rate: toNumber(it.loss_rate, 0),
        metadata_json: (it.metadata_json ?? {}) as any,
      })

      const enableGate = (row: ModalRuleRow): string | null => {
        if (!row.enabled) return null
        if (!lastPreviewOk) return '启用前必须先预演成功（spec/parse + bom/generate）'
        if (needDim && (lastPreviewSummary as any)?.[needDim] == null) return `你选择了“${triggerLabel(draftTriggerType)}”，但预演样例未解析出对应数值，请换 spec_text 重新预演`
        const ref = String(row.item.material_ref_id ?? '').trim()
        if (!ref) return '请先选择替换物料并保存（让后端回填单位）'
        if (!baseUnitFromBom || !normalizeUnit(row.item.unit_of_measure)) {
          return '单位信息缺失：请先保存（让后端回填 unit_of_measure）并预演；主数据单位未补齐也会导致缺失'
        }
        const baseU = baseUnitFromBom
        const targetU = normalizeUnit(row.item.unit_of_measure)
        if (baseU && targetU && baseU !== targetU) return `单位不一致：基准=${baseU}，替换物料=${targetU}（只允许同单位平替）`
        return null
      }

      // validate rows first
      for (const r of modalRows) {
        if (draftTriggerType === 'token') {
          if (r.token_any.length === 0 && r.token_all.length === 0) throw new Error('token 规则至少填写 1 个 token（any 或 all）')
        } else {
          if (r.op === 'between') {
            if (r.min == null || r.max == null) throw new Error(`区间条件必须同时填写 min/max（单位 ${unitOfTrigger}）`)
          } else if (r.op === 'gte' || r.op === 'eq') {
            if (r.min == null) throw new Error(`条件值不能为空（单位 ${unitOfTrigger}）`)
          } else if (r.op === 'lte') {
            if (r.max == null) throw new Error(`条件值不能为空（单位 ${unitOfTrigger}）`)
          }
        }
        const gate = enableGate(r)
        if (gate) throw new Error(gate)
      }

      // persist rows sequentially
      for (let i = 0; i < modalRows.length; i++) {
        const r = modalRows[i]
        const conditions = rowToConditions(draftTriggerType, r)
        const items = [itemPayloadFromRow(r.item)]
        if (!r.id) {
          const payload: LineVariantCreateRequest = {
            version_id: versionId,
            base_line_id: baseLineId,
            enabled: !!r.enabled,
            priority: 100,
            action: FIXED_ACTION,
            stop_on_hit: true,
            notes: '',
            conditions,
            metadata_json: {},
            items,
            operator_id: 'planner-ui',
          }
          const created = await createLineVariant(versionId, payload)
          const createdId = created.id
          // refresh items with server filled fields
          if (String(r.item.material_ref_id ?? '').trim()) {
            const updated = await replaceLineVariantItems(createdId, { items })
            const it0 = buildEditableItems((updated.items ?? []) as any[])[0]
            setModalRows((prev) => prev.map((x) => (x.key === r.key ? { ...x, id: createdId, key: createdId, item: it0 ?? x.item } : x)))
          } else {
            setModalRows((prev) => prev.map((x) => (x.key === r.key ? { ...x, id: createdId, key: createdId } : x)))
          }
        } else {
          const updatePayload: LineVariantUpdateRequest = {
            enabled: !!r.enabled,
            priority: 100,
            action: FIXED_ACTION,
            stop_on_hit: true,
            notes: undefined,
            conditions,
            operator_id: 'planner-ui',
          }
          await updateLineVariant(r.id, updatePayload)
          if (String(r.item.material_ref_id ?? '').trim()) {
            const updated = await replaceLineVariantItems(r.id, { items })
            const it0 = buildEditableItems((updated.items ?? []) as any[])[0]
            if (it0) setModalRows((prev) => prev.map((x) => (x.key === r.key ? { ...x, item: it0 } : x)))
          }
        }
      }
      return true
    },
    onSuccess: async () => {
      message.success('已保存')
      await queryClient.invalidateQueries({ queryKey: ['lineVariants', versionId, baseLineId] })
    },
    onError: (err: any) => message.error(err?.response?.data?.detail ?? err?.message ?? '保存失败'),
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
      const enabledRows = modalRows.filter((r) => r.enabled)
      const targetU = normalizeUnit((enabledRows.length === 1 ? enabledRows[0].item?.unit_of_measure : modalRows[0]?.item?.unit_of_measure) ?? null)
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

  // (legacy) itemColumns removed: modal now edits per-row item inline

  const formatBetween = (pair: any, unit: string): string | null => {
    const b = asBetween(pair)
    if (!b) return null
    const [min, max] = b
    if (min == null && max == null) return null
    if (min != null && max != null) return min === max ? `=${min}${unit}` : `${min}~${max}${unit}`
    if (min != null) return `≥${min}${unit}`
    return `≤${max}${unit}`
  }

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
        const w = formatBetween(cond.width_between, 'cm')
        const h = formatBetween(cond.height_between, 'cm')
        const a = formatBetween(cond.area_between, 'm²')
        const p = formatBetween(cond.perimeter_between, 'm')
        const hasMetric = !!(w || h || a || p)

        if (!anyCnt && !allCnt && !hasMetric) return <span style={{ color: '#bfbfbf' }}>-</span>
        if (anyCnt || allCnt) {
          return (
            <Space size={6}>
              <Tag>token</Tag>
              {anyCnt ? <Tag>any:{anyCnt}</Tag> : null}
              {allCnt ? <Tag>all:{allCnt}</Tag> : null}
            </Space>
          )
        }
        // 单触发类型：优先展示一个 metric（如果历史数据存在多种，这里只展示第一个）
        const metricTag = p ? `周长${p}` : a ? `面积${a}` : w ? `宽度${w}` : h ? `高度${h}` : null
        return metricTag ? <Tag>{metricTag}</Tag> : <span style={{ color: '#bfbfbf' }}>-</span>
      },
    },
    { title: 'items', width: 70, render: (_: any, r: any) => (r.items?.length ?? 0) },
    {
      title: '操作',
      width: 110,
      render: (_: any, r: any) => (
        <Space size={6}>
          <Button size="small" icon={<EditOutlined />} onClick={() => openEditModal(r.id)}>
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

  const updateModalRow = (key: string, patch: Partial<ModalRuleRow>) => {
    setModalRows((prev) => prev.map((r) => (r.key === key ? { ...r, ...patch } : r)))
    // 仅切换“启动(enabled)”不应使预演失效，否则会出现：预演通过→打开启动→保存时又提示必须预演 的冲突
    const keys = Object.keys(patch ?? {})
    const onlyEnabledToggle = keys.length === 1 && keys[0] === 'enabled'
    if (!onlyEnabledToggle) invalidatePreview()
  }

  const removeModalRow = async (row: ModalRuleRow) => {
    if (row.id) {
      await deleteVariantMutation.mutateAsync(row.id)
    } else {
      setModalRows((prev) => prev.filter((r) => r.key !== row.key))
    }
    invalidatePreview()
  }

  const addModalRow = () => {
    const key = `tmp-${Date.now()}-${Math.random().toString(16).slice(2)}`
    setModalRows((prev) => [
      ...prev,
      {
        key,
        enabled: false,
        op: 'gte',
        min: null,
        max: null,
        token_any: [],
        token_all: [],
        item: blankItemRow(),
      },
    ])
    invalidatePreview()
  }

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
          title="规则列表（只展示/选择）"
          extra={
            <Space>
              <Button size="small" type="primary" onClick={openCreateModal}>
                新建规则
              </Button>
              <Button size="small" onClick={() => variantsQuery.refetch()} disabled={variantsQuery.isLoading}>
                刷新
              </Button>
            </Space>
          }
        >
          {variants.length === 0 ? (
            <Alert
              type="warning"
              showIcon
              style={{ marginBottom: 12 }}
              message="该行暂无规则"
              description={
                <span style={{ fontSize: 12 }}>
                  如果你之前建过规则但这里为空，通常是 <b>base_line_id 变化</b>（例如未“保存清单/同步清单”导致行ID不稳定）。
                  建议：先在主抽屉里保存清单，再回来创建/查看行级变体。
                </span>
              }
            />
          ) : null}
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
        <div style={{ fontSize: 12, color: '#8c8c8c' }}>
          选择一条规则后点击“编辑”在弹窗内配置（触发类型/条件/替换物料/预演）。
        </div>
        <Modal
          title={
            editMode === 'create'
              ? `新建规则（${baseLineLabel ?? baseLineId.slice(0, 8)}…）`
              : `编辑规则（${selectedVariantId?.slice(0, 8) ?? '-'}）`
          }
          open={editModalOpen}
          onCancel={() => setEditModalOpen(false)}
          width={980}
          footer={null}
          bodyStyle={{ maxHeight: '72vh', overflowY: 'auto' }}
          destroyOnClose
        >
          <Space direction="vertical" size={12} style={{ width: '100%' }}>
            <Alert
              type="info"
              showIcon
              message="最稳形态（固定动作）"
              description={
                <div style={{ fontSize: 12 }}>
                  <div>
                    <b>{STABLE_SHAPE_LABEL}</b>
                  </div>
                  <div style={{ color: '#8c8c8c' }}>弹窗内按“同一触发类型”批量维护多条规则，每行=一条规则。</div>
                  <div style={{ color: '#8c8c8c' }}>重要：预演只会读取“已保存入库”的规则；因此请先点“创建并保存/保存”，再点右侧“预演”。</div>
                </div>
              }
            />
            <Card
              size="small"
              title={
                <Space wrap>
                  <span>触发类型</span>
                  <Select
                    value={draftTriggerType}
                    style={{ width: 220 }}
                    options={[
                      { label: 'token（包含）', value: 'token' },
                      { label: '宽度（cm）', value: 'width' },
                      { label: '高度（cm）', value: 'height' },
                      { label: '面积（m²）', value: 'area' },
                      { label: '周长（m）', value: 'perimeter' },
                    ]}
                    onChange={(v) => handleTriggerTypeChange(v as any)}
                  />
                  <Tag color="blue">action=replace_self</Tag>
                </Space>
              }
              extra={
                <Space size={8}>
                  <Button size="small" type="primary" onClick={addModalRow}>
                    新增
                  </Button>
                  <Button
                    size="small"
                    type="primary"
                    loading={modalSaveMutation.isPending}
                    onClick={() => modalSaveMutation.mutate()}
                  >
                    {editMode === 'create' ? '创建并保存' : '保存'}
                  </Button>
                </Space>
              }
            >
              <Table
                rowKey="key"
                size="small"
                pagination={false}
                dataSource={modalRows}
                columns={[
                  {
                    title: '启动',
                    width: 70,
                    render: (_: any, r: ModalRuleRow) => (
                      <Switch
                        checked={!!r.enabled}
                        onChange={(v) => {
                          if (v && (!lastPreviewOk || previewStale)) {
                            message.error(previewStale ? '预演已过期：请先重新预演' : '启用前必须先预演成功')
                            return
                          }
                          if (v) {
                            const needDim =
                              draftTriggerType === 'width'
                                ? 'width_cm'
                                : draftTriggerType === 'height'
                                  ? 'height_cm'
                                  : draftTriggerType === 'area'
                                    ? 'area_m2'
                                    : draftTriggerType === 'perimeter'
                                      ? 'perimeter_m'
                                      : null
                            if (needDim && (lastPreviewSummary as any)?.[needDim] == null) {
                              message.error(`你选择了“${triggerLabel(draftTriggerType)}”，但预演样例未解析出对应数值，请换 spec_text 重新预演`)
                              return
                            }
                            const ref = String(r.item.material_ref_id ?? '').trim()
                            if (!ref) {
                              message.error('请先选择替换物料并保存（让后端回填单位）')
                              return
                            }
                            if (!baseUnitFromBom) {
                              message.error('基准行单位缺失：请先补齐主数据单位并“保存清单”，再回来启用规则')
                              return
                            }
                            const targetU = normalizeUnit(r.item.unit_of_measure)
                            if (!targetU) {
                              message.error('替换物料单位缺失：请先保存（让后端回填 unit_of_measure）')
                              return
                            }
                            if (targetU !== baseUnitFromBom) {
                              message.error(`单位不一致：基准=${baseUnitFromBom}，替换物料=${targetU}（只允许同单位平替）`)
                              return
                            }
                          }
                          updateModalRow(r.key, { enabled: v })
                        }}
                      />
                    ),
                  },
                  {
                    title: '条件表达式',
                    render: (_: any, r: ModalRuleRow) => {
                      if (draftTriggerType === 'token') {
                        const anyStr = (r.token_any ?? []).join(',')
                        const allStr = (r.token_all ?? []).join(',')
                        return (
                          <Space wrap>
                            <Input
                              placeholder="token(any) 逗号分隔"
                              value={anyStr}
                              onChange={(e) => updateModalRow(r.key, { token_any: e.target.value.split(',').map((x) => x.trim()).filter(Boolean) })}
                              style={{ width: 220 }}
                            />
                            <Input
                              placeholder="token(all) 逗号分隔"
                              value={allStr}
                              onChange={(e) => updateModalRow(r.key, { token_all: e.target.value.split(',').map((x) => x.trim()).filter(Boolean) })}
                              style={{ width: 220 }}
                            />
                          </Space>
                        )
                      }
                      return (
                        <Space wrap>
                          <Select
                            value={r.op}
                            style={{ width: 120 }}
                            options={[
                              { label: '≥', value: 'gte' },
                              { label: '≤', value: 'lte' },
                              { label: '=', value: 'eq' },
                              { label: '区间', value: 'between' },
                            ]}
                            onChange={(v) => updateModalRow(r.key, { op: v as any })}
                          />
                          {r.op === 'between' ? (
                            <Space wrap>
                              <InputNumber placeholder="min" value={r.min} onChange={(v) => updateModalRow(r.key, { min: v == null ? null : Number(v) })} />
                              <Text type="secondary">到</Text>
                              <InputNumber placeholder="max" value={r.max} onChange={(v) => updateModalRow(r.key, { max: v == null ? null : Number(v) })} />
                            </Space>
                          ) : (
                            <InputNumber
                              placeholder="value"
                              value={r.op === 'lte' ? r.max : r.min}
                              onChange={(v) => {
                                const n = v == null ? null : Number(v)
                                if (r.op === 'gte') updateModalRow(r.key, { min: n, max: null })
                                if (r.op === 'lte') updateModalRow(r.key, { min: null, max: n })
                                if (r.op === 'eq') updateModalRow(r.key, { min: n, max: n })
                              }}
                            />
                          )}
                        </Space>
                      )
                    },
                  },
                  {
                    title: '替换物料',
                    width: 260,
                    render: (_: any, r: ModalRuleRow) => (
                      <Space direction="vertical" size={0} style={{ width: '100%' }}>
                        <Space.Compact style={{ width: '100%' }}>
                          <Input
                            readOnly
                            placeholder="点击右侧“选择”"
                            value={String(r.item.material_code ?? '') || String(r.item.material_ref_id ?? '') || ''}
                          />
                          <Button
                            size="small"
                            onClick={() => {
                              setMaterialPickerRowKey(r.key)
                              setMaterialPickerOpen(true)
                            }}
                          >
                            选择
                          </Button>
                          <Button
                            size="small"
                            danger
                            onClick={() =>
                              updateModalRow(r.key, {
                                item: {
                                  ...r.item,
                                  material_ref_id: '',
                                  material_code: null,
                                  material_name: null,
                                  unit_of_measure: null,
                                },
                              })
                            }
                          >
                            清空
                          </Button>
                        </Space.Compact>
                        <Text type="secondary" style={{ fontSize: 12 }}>
                          {r.item.material_code ?? '-'} {r.item.material_name ?? ''}
                        </Text>
                        <Text type="secondary" style={{ fontSize: 12 }}>
                          单位：{r.item.unit_of_measure ?? '-'}
                        </Text>
                      </Space>
                    ),
                  },
                  {
                    title: '用量(β)',
                    width: 110,
                    render: (_: any, r: ModalRuleRow) => (
                      <InputNumber
                        size="small"
                        min={0}
                        value={toNumber(r.item.base_quantity, 0)}
                        onChange={(v) => updateModalRow(r.key, { item: { ...r.item, base_quantity: toNumber(v, 0) } })}
                      />
                    ),
                  },
                  {
                    title: '固定(α)',
                    width: 110,
                    render: (_: any, r: ModalRuleRow) => (
                      <InputNumber
                        size="small"
                        min={0}
                        value={toNumber(r.item.fixed_quantity, 0)}
                        onChange={(v) => updateModalRow(r.key, { item: { ...r.item, fixed_quantity: toNumber(v, 0) } })}
                      />
                    ),
                  },
                  {
                    title: '覆盖率',
                    width: 110,
                    render: (_: any, r: ModalRuleRow) => (
                      <InputNumber
                        size="small"
                        min={0}
                        max={1}
                        step={0.1}
                        value={toNumber(r.item.coverage_ratio, 1)}
                        onChange={(v) => updateModalRow(r.key, { item: { ...r.item, coverage_ratio: toNumber(v, 1) } })}
                      />
                    ),
                  },
                  {
                    title: '损耗%',
                    width: 100,
                    render: (_: any, r: ModalRuleRow) => (
                      <InputNumber
                        size="small"
                        min={0}
                        max={100}
                        value={toNumber(r.item.loss_rate, 0)}
                        onChange={(v) => updateModalRow(r.key, { item: { ...r.item, loss_rate: toNumber(v, 0) } })}
                      />
                    ),
                  },
                  {
                    title: '',
                    width: 44,
                    render: (_: any, r: ModalRuleRow) => (
                      <Button size="small" danger type="text" icon={<DeleteOutlined />} onClick={() => void removeModalRow(r)} />
                    ),
                  },
                ]}
                scroll={{ x: 1200 }}
              />
              <div style={{ marginTop: 8 }}>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  启用门槛：每行“启动”前必须先预演成功；保存会回填物料编码/名称/单位，并做同单位校验。
                </Text>
              </div>
            </Card>

            <Card
              size="small"
              title="预演（spec/parse + bom/generate，启用前必须成功）"
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
                    description={<span style={{ fontSize: 12 }}>建议：先保存（回填单位）→ 输入 spec_text → 预演通过 → 再启用。</span>}
                  />
                )}

                <Input.TextArea
                  value={specText}
                  onChange={(e) => setSpecText(e.target.value)}
                  placeholder="输入 spec_text（例如：120*80 黑色 无框）"
                  autoSize={{ minRows: 2, maxRows: 6 }}
                />

                <Card size="small" title="解析结果（tokens/尺寸）">
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
        </Modal>

        <MaterialSelectModal
          open={materialPickerOpen}
          onClose={() => {
            setMaterialPickerOpen(false)
            setMaterialPickerRowKey(null)
          }}
          title="选择替换物料（同单位平替）"
          onlyBom
          onSelect={(m) => {
            const key = materialPickerRowKey
            if (!key) return
          const inheritedMethod = baseLineParamsFromBom.calculation_method
          const inheritedBaseQty = baseLineParamsFromBom.base_quantity
            updateModalRow(key, {
              item: {
                ...(modalRows.find((x) => x.key === key)?.item ?? ({} as any)),
                material_ref_id: m.id,
                material_code: m.material_code,
                material_name: m.material_name,
                unit_of_measure: m.unit ?? null,
              // 关键：替换物料默认继承基准行的计量方式与 β，避免出现替换后 computed_quantity=0 的误导
              calculation_method: inheritedMethod ?? ((modalRows.find((x) => x.key === key)?.item as any)?.calculation_method ?? 'count'),
              base_quantity:
                inheritedBaseQty != null && Number.isFinite(inheritedBaseQty)
                  ? inheritedBaseQty
                  : ((modalRows.find((x) => x.key === key)?.item as any)?.base_quantity ?? 1),
              } as any,
            })
          }}
        />
      </Space>
    </Drawer>
  )
}


