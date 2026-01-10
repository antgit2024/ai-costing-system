import { useEffect, useMemo, useState } from 'react'
import { Alert, Button, Card, Col, Input, InputNumber, Modal, Row, Select, Space, Switch, Table, Tag, Typography, message } from 'antd'
// ColumnsType used by legacy rule list UI (removed)
import { DeleteOutlined, EditOutlined, PlayCircleOutlined } from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import {
  createLineVariant,
  deleteLineVariant,
  fetchProductModelVersionLines,
  generateBom,
  listLineVariants,
  parseSpec,
  replaceLineVariantItems,
  updateLineVariant,
} from '@/services/planner'
import MaterialPickerDrawer from '@/components/costing/MaterialPickerDrawer'
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
  // Optional: allow UI to show/anchor by model code (e.g. PI5). If omitted, UI still works.
  modelCode?: string | null
}

type EditableItemRow = LineVariantItemPayload & {
  _tmpId: string
}

type MetricOp = 'off' | 'gte' | 'lte' | 'eq' | 'between'
type TriggerType = 'token' | 'width' | 'height' | 'area' | 'perimeter' | 'size'
type TokenMode = 'any' | 'all'

type ModalRuleRow = {
  key: string
  id?: string
  enabled: boolean
  // per-row trigger (for token mode: 一级=token, 二级=size)
  trigger_type: TriggerType
  // 二级规则归属（用于把 size 规则挂到某条 token 一级下）
  parent_variant_id?: string | null
  // variant-level metadata (persisted on LineVariant itself)
  metadata_json?: Record<string, unknown>
  // UI-only: local edits not persisted to backend yet.
  dirty?: boolean
  token_mode?: TokenMode
  // condition
  op: Exclude<MetricOp, 'off'>
  min: number | null
  max: number | null
  // size mode (height)
  h_op?: Exclude<MetricOp, 'off'>
  h_min?: number | null
  h_max?: number | null
  token_any: string[]
  token_all: string[]
  // item (1->1)
  item: EditableItemRow
}

const FIXED_ACTION: LineVariantAction = 'replace_self'
// STABLE_SHAPE_LABEL: legacy banner text (rule list layer removed)

const asStringArray = (v: unknown): string[] => (Array.isArray(v) ? v.map((x) => String(x)).filter(Boolean) : [])

const toNumber = (v: any, fallback = 0): number => {
  const n = Number(v)
  return Number.isFinite(n) ? n : fallback
}

const formatQty2 = (v: any): string => {
  if (v == null || v === '') return '-'
  const n = Number(v)
  if (!Number.isFinite(n)) return String(v)
  return n.toFixed(2)
}

const splitTokens = (raw: string): string[] => {
  return String(raw ?? '')
    .split(/[,\uFF0C|\u003B\uFF1B]+/g) // "," / "，" / "|" / ";" / "；"
    .map((x) => x.trim())
    .filter(Boolean)
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
  const { open, onClose, versionId, baseLineId, baseLineLabel, modelCode } = props
  const queryClient = useQueryClient()

  // legacy single-rule item editor removed; modal uses per-row item
  const [draftTriggerType, setDraftTriggerType] = useState<TriggerType>('token')

  const [materialPickerOpen, setMaterialPickerOpen] = useState(false)
  const [materialPickerRowKey, setMaterialPickerRowKey] = useState<string | null>(null)
  const [modalRows, setModalRows] = useState<ModalRuleRow[]>([])
  const [selectedTokenParentKey, setSelectedTokenParentKey] = useState<string | null>(null)
  const [autoAnchorModelToken] = useState(true)

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

  // IMPORTANT: keep a stable reference when query data is undefined, otherwise effects depending on `variants`
  // may loop (data ?? [] creates a new array each render) and can trigger React nested update error #185 in prod.
  const variants = useMemo(() => ((variantsQuery.data ?? []) as LineVariantDetailRead[]), [variantsQuery.data])

  const modelAnchorToken = useMemo(() => {
    const raw = String(modelCode ?? '').trim()
    if (!raw) return null
    return `MODEL:${raw.toUpperCase()}`
  }, [modelCode])

  // Base line defaults (β/α/覆盖率/损耗% / 计量方式) for better UX when creating replacement items.
  const baseLineQuery = useQuery({
    queryKey: ['variantBaseLine', versionId, baseLineId],
    queryFn: () => fetchProductModelVersionLines(versionId),
    enabled: open && !!versionId,
  })
  const baseLineDefaults = useMemo(() => {
    const mats = (baseLineQuery.data as any)?.materials ?? []
    const base = (mats as any[]).find((x) => String(x?.id ?? '') === String(baseLineId))
    return {
      calculation_method: (base?.calculation_method ?? null) as any,
      base_quantity: base?.base_quantity != null ? Number(base.base_quantity) : null,
      fixed_quantity: base?.fixed_quantity != null ? Number(base.fixed_quantity) : null,
      coverage_ratio: base?.coverage_ratio != null ? Number(base.coverage_ratio) : null,
      loss_rate: base?.loss_rate != null ? Number(base.loss_rate) : null,
    }
  }, [baseLineQuery.data, baseLineId])

  const inferTriggerType = (cond: any): TriggerType => {
    // Prefer size trigger when both width/height constraints exist (even if token exists).
    if (cond?.width_between && cond?.height_between) return 'size'
    const anyCnt = asStringArray(cond?.spec_contains_any).length
    const allCnt = asStringArray(cond?.spec_contains_all).length
    if (cond?.perimeter_between) return 'perimeter'
    if (cond?.area_between) return 'area'
    if (cond?.width_between) return 'width'
    if (cond?.height_between) return 'height'
    if (anyCnt || allCnt) return 'token'
    return 'token'
  }

  const triggerLabel = (t: TriggerType): string => {
    if (t === 'token') return 'token（包含）'
    if (t === 'size') return '尺寸（宽+高，cm）'
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
    calculation_method: (baseLineDefaults.calculation_method ?? 'count') as any,
    // 默认继承基准行参数：避免新增规则时要重复手填，且减少“替换后数量=0”的误导。
    base_quantity:
      baseLineDefaults.base_quantity != null && Number.isFinite(baseLineDefaults.base_quantity) && baseLineDefaults.base_quantity > 0
        ? baseLineDefaults.base_quantity
        : 1,
    fixed_quantity:
      baseLineDefaults.fixed_quantity != null && Number.isFinite(baseLineDefaults.fixed_quantity) ? baseLineDefaults.fixed_quantity : 0,
    coverage_ratio:
      baseLineDefaults.coverage_ratio != null && Number.isFinite(baseLineDefaults.coverage_ratio) ? baseLineDefaults.coverage_ratio : 1,
    loss_rate: baseLineDefaults.loss_rate != null && Number.isFinite(baseLineDefaults.loss_rate) ? baseLineDefaults.loss_rate : 0,
    metadata_json: {},
  })

  const rowFromVariant = (v: LineVariantDetailRead): ModalRuleRow => {
    const cond = (v.conditions ?? {}) as any
    const meta = (v.metadata ?? {}) as any
    const anyArr = asStringArray(cond.spec_contains_any)
    let allArr = asStringArray(cond.spec_contains_all)
    // If backend stored auto anchor token, hide it from user input (show separately in UI).
    if (modelAnchorToken && autoAnchorModelToken) {
      allArr = allArr.filter((t) => String(t).toLowerCase() !== String(modelAnchorToken).toLowerCase())
    }
    const key = v.id
    let op: Exclude<MetricOp, 'off'> = 'gte'
    let min: number | null = null
    let max: number | null = null
    let h_op: Exclude<MetricOp, 'off'> = 'gte'
    let h_min: number | null = null
    let h_max: number | null = null
    const t = inferTriggerType(cond)
    if (t === 'size') {
      const wPair = asBetween(cond.width_between)
      const hPair = asBetween(cond.height_between)
      const wOp = opFromBetween(wPair)
      const hOp = opFromBetween(hPair)
      op = (wOp === 'off' ? 'gte' : wOp) as any
      min = wPair?.[0] ?? null
      max = wPair?.[1] ?? null
      h_op = (hOp === 'off' ? 'gte' : hOp) as any
      h_min = hPair?.[0] ?? null
      h_max = hPair?.[1] ?? null
    } else if (t !== 'token') {
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
      trigger_type: t,
      parent_variant_id: String(meta?.parent_variant_id ?? '').trim() || null,
      metadata_json: (meta ?? {}) as any,
      dirty: false,
      token_mode: anyArr.length > 0 ? 'any' : 'all',
      op,
      min,
      max,
      h_op,
      h_min,
      h_max,
      token_any: anyArr,
      token_all: allArr,
      item: item0,
    }
  }

  const rowToConditions = (trigger: TriggerType, row: ModalRuleRow): any => {
    const withToken = (base: any) => {
      // 业务 token 只允许二选一（any vs all），避免两套表达式并存造成误解；
      // 系统锚定 token（MODEL:xxx）仍由 spec_contains_all 注入，用户无需感知。
      const mode = inferTokenMode(row)
      const anyArr = mode === 'any' ? row.token_any ?? [] : []
      const allArr0 = mode === 'all' ? row.token_all ?? [] : []
      const allArr = (() => {
        if (!autoAnchorModelToken) return allArr0
        if (!modelAnchorToken) return allArr0
        const lower = new Set(allArr0.map((x) => String(x).toLowerCase()))
        if (lower.has(modelAnchorToken.toLowerCase())) return allArr0
        return [...allArr0, modelAnchorToken]
      })()
      return { ...base, spec_contains_any: anyArr, spec_contains_all: allArr }
    }
    if (trigger === 'token') return withToken({})
    const toPair = (): [number | null, number | null] | null => {
      const a = row.min
      const b = row.max
      if (row.op === 'between') return [a, b]
      if (row.op === 'gte') return [a, null]
      if (row.op === 'lte') return [null, b]
      return [a, a]
    }
    const toPairH = (): [number | null, number | null] | null => {
      const a = row.h_min ?? null
      const b = row.h_max ?? null
      const op = row.h_op ?? 'gte'
      if (op === 'between') return [a, b]
      if (op === 'gte') return [a, null]
      if (op === 'lte') return [null, b]
      return [a, a]
    }
    const pair = betweenToPayload(toPair())
    if (trigger === 'width') return withToken({ width_between: pair })
    if (trigger === 'height') return withToken({ height_between: pair })
    if (trigger === 'area') return withToken({ area_between: pair })
    if (trigger === 'perimeter') return withToken({ perimeter_between: pair })
    // size: token + width + height
    const hPair = betweenToPayload(toPairH())
    return withToken({ width_between: pair, height_between: hPair })
  }

  const inferTokenMode = (r: ModalRuleRow): TokenMode => {
    if (r.token_mode) return r.token_mode
    const allCnt = (r.token_all ?? []).length
    const anyCnt = (r.token_any ?? []).length
    if (anyCnt) return 'any'
    if (allCnt) return 'all'
    return 'all'
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

  const anyDirty = useMemo(() => modalRows.some((r) => !!r.dirty), [modalRows])

  // 变体编辑器默认进入 token 模式（你们当前主要用 token→二级指标）；其他触发类型仍可在非 token 模式下使用

  useEffect(() => {
    if (!open) return
    // keep rows in sync with current trigger selection (simple filter view)
    const filtered =
      draftTriggerType === 'token'
        ? variants.filter((v) => {
            const t = inferTriggerType((v.conditions ?? {}) as any)
            if (t === 'token') return true
            if (t === 'size' || t === 'area' || t === 'perimeter') {
              const pid = String(((v as any)?.metadata as any)?.parent_variant_id ?? '').trim()
              return !!pid
            }
            return false
          })
        : variants.filter((v) => inferTriggerType((v.conditions ?? {}) as any) === draftTriggerType)
    const nextRows = filtered.map((v) => rowFromVariant(v))
    if (draftTriggerType === 'token') {
      const parentIds = new Set(
        nextRows
          .filter((r) => r.trigger_type === 'size' || r.trigger_type === 'area' || r.trigger_type === 'perimeter')
          .map((r) => String(r.parent_variant_id ?? '').trim())
          .filter(Boolean),
      )
      const normalized = nextRows.map((r) => {
        if (r.trigger_type !== 'token') return r
        if (!r.id) return r
        if (!parentIds.has(String(r.id))) return r
        if (!r.enabled) return r
        // 若后端历史上误启用了 token 一级（但存在二级），这里强制关闭并要求保存落库
        return { ...r, enabled: false, dirty: true }
      })
      setModalRows(normalized)
      if (nextRows.some((r) => r.trigger_type === 'token' && r.enabled && r.id && parentIds.has(String(r.id)))) {
        message.warning('检测到 token 一级存在二级尺寸分段：已自动关闭一级“启动”。请保存以落库。')
      }
      return
    }
    setModalRows(nextRows)
  }, [open, variants, draftTriggerType])

  useEffect(() => {
    if (!open) return
    if (draftTriggerType !== 'token') return
    setSelectedTokenParentKey((prev) => {
      const list = modalRows.filter((r) => r.trigger_type === 'token')
      if (!list.length) return null
      if (prev && list.some((p) => p.key === prev)) return prev
      return list[0].key
    })
  }, [open, draftTriggerType, modalRows])

  useEffect(() => {
    if (!open) return
    invalidatePreview()
  }, [open, versionId, baseLineId])

  // legacy buildConditionsPayload removed: modal uses rowToConditions per row

  const normalizedModalRowsForFingerprint = useMemo(
    () =>
      modalRows.map((r) => ({
        id: r.id ?? null,
        trigger_type: r.trigger_type ?? null,
        parent_variant_id: r.parent_variant_id ?? null,
        // 注意：fingerprint 不包含 enabled，否则“预演通过 → 打开启动”会被判定为预演过期（逻辑冲突）
        op: r.op,
        min: r.min ?? null,
        max: r.max ?? null,
        h_op: r.h_op ?? null,
        h_min: r.h_min ?? null,
        h_max: r.h_max ?? null,
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
      action: FIXED_ACTION,
      trigger_type: draftTriggerType,
      // 以弹窗多行规则为准（用于“预演是否过期”的判定）
      rules: normalizedModalRowsForFingerprint,
      spec_text: String(specText ?? '').trim(),
    }
    return JSON.stringify(payload)
  }, [
    versionId,
    baseLineId,
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

  const baseUnitFromLines = useMemo(() => {
    // When replace_self matches, the base_line row disappears from final_material_lines,
    // so baseUnitFromBom may be null even though base line has a valid unit.
    const mats = ((baseLineQuery.data as any)?.materials ?? []) as any[]
    const base = mats.find((x) => String(x?.id ?? '') === String(baseLineId))
    const u =
      (base?.unit_of_measure ?? null) ||
      (base?.metadata_json?.display_unit ?? null) ||
      (base?.metadata_json?.bom_unit ?? null)
    return normalizeUnit(u)
  }, [baseLineQuery.data, baseLineId])

  const baseUnit = useMemo(() => baseUnitFromBom || baseUnitFromLines, [baseUnitFromBom, baseUnitFromLines])

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

      const needDimForRow = (row: ModalRuleRow): string | null => {
        if (row.trigger_type === 'size') return 'size_wh'
        if (row.trigger_type === 'width') return 'width_cm'
        if (row.trigger_type === 'height') return 'height_cm'
        if (row.trigger_type === 'area') return 'area_m2'
        if (row.trigger_type === 'perimeter') return 'perimeter_m'
        return null
      }

      const enableGate = (row: ModalRuleRow, hasChildRows: boolean): string | null => {
        if (!row.enabled) return null
        // token 父：只要有二级且被启用，就必须拦截（避免一级抢命中）
        if (row.trigger_type === 'token' && hasChildRows) return '该 token 一级存在二级规则：一级不可启用（请启用二级）'
        // IMPORTANT:
        // 新增/编辑其他行时会 invalidatePreview()，此时 lastPreviewOk 会被清空。
        // 但“已入库且未改动”的已启用规则并没有发生变化，不应该阻塞保存（否则会出现：预演被 dirty 拦住、保存又要求预演 的死循环）。
        if (row.id && !row.dirty) return null
        if (!lastPreviewOk) return '启用前必须先预演成功（spec/parse + bom/generate）'
        const need = needDimForRow(row)
        if (need === 'size_wh') {
          if ((lastPreviewSummary as any)?.width_cm == null || (lastPreviewSummary as any)?.height_cm == null) {
            return `你选择了“${triggerLabel(row.trigger_type)}”，但预演样例未解析出宽/高，请换 spec_text 重新预演`
          }
        } else if (need && (lastPreviewSummary as any)?.[need] == null) {
          return `你选择了“${triggerLabel(row.trigger_type)}”，但预演样例未解析出对应数值，请换 spec_text 重新预演`
        }
        const ref = String(row.item.material_ref_id ?? '').trim()
        if (!ref) return '请先选择替换物料并保存（让后端回填单位）'
        if (!baseUnit || !normalizeUnit(row.item.unit_of_measure)) {
          return '单位信息缺失：请先保存（让后端回填 unit_of_measure）并预演；主数据单位未补齐也会导致缺失'
        }
        const baseU = baseUnit
        const targetU = normalizeUnit(row.item.unit_of_measure)
        if (baseU && targetU && baseU !== targetU) return `单位不一致：基准=${baseU}，替换物料=${targetU}（只允许同单位平替）`
        return null
      }

      // Avoid deadlock:
      // - Preview reads only persisted rules, so we block preview when there are dirty local edits.
      // - Enabling requires a successful preview.
      // If a rule is currently enabled and user edited it (dirty), saving must be allowed by auto-disabling it first.
      const normalizedRows = modalRows.map((r) => (r.enabled && r.dirty ? { ...r, enabled: false } : r))
      if (normalizedRows.some((r, idx) => r.enabled !== modalRows[idx]?.enabled)) {
        setModalRows(normalizedRows)
        message.warning('检测到已启用规则存在未保存改动：已自动关闭“启动”。请保存后预演成功再启用。')
      }

      // validate rows first
      for (const r of normalizedRows) {
        // token 可为空（允许“无条件”规则）；若开启 autoAnchorModelToken，仍会自动追加 MODEL:<code> 作为跨模型护栏
        if (r.trigger_type === 'size') {
          // width
          if (r.op === 'between') {
            if (r.min == null || r.max == null) throw new Error('尺寸规则：宽度区间必须同时填写 min/max（单位 cm）')
          } else if (r.op === 'gte' || r.op === 'eq') {
            if (r.min == null) throw new Error('尺寸规则：宽度条件值不能为空（单位 cm）')
          } else if (r.op === 'lte') {
            if (r.max == null) throw new Error('尺寸规则：宽度条件值不能为空（单位 cm）')
          }
          // height
          const hop = r.h_op ?? 'gte'
          if (hop === 'between') {
            if (r.h_min == null || r.h_max == null) throw new Error('尺寸规则：高度区间必须同时填写 min/max（单位 cm）')
          } else if (hop === 'gte' || hop === 'eq') {
            if (r.h_min == null) throw new Error('尺寸规则：高度条件值不能为空（单位 cm）')
          } else if (hop === 'lte') {
            if (r.h_max == null) throw new Error('尺寸规则：高度条件值不能为空（单位 cm）')
          }
        } else if (r.trigger_type !== 'token') {
          // metric-only rows (width/height/area/perimeter)
          const unit = r.trigger_type === 'area' ? 'm²' : r.trigger_type === 'perimeter' ? 'm' : 'cm'
          if (r.op === 'between') {
            if (r.min == null || r.max == null) throw new Error(`区间条件必须同时填写 min/max（单位 ${unit}）`)
          } else if (r.op === 'gte' || r.op === 'eq') {
            if (r.min == null) throw new Error(`条件值不能为空（单位 ${unit}）`)
          } else if (r.op === 'lte') {
            if (r.max == null) throw new Error(`条件值不能为空（单位 ${unit}）`)
          }
        }
        const hasChildRows =
          r.trigger_type === 'token'
            ? normalizedRows.some(
                (x) =>
                  (x.trigger_type === 'size' || x.trigger_type === 'area' || x.trigger_type === 'perimeter') &&
                  String(x.parent_variant_id ?? '') === String(r.id ?? ''),
              )
            : false
        const gate = enableGate(r, hasChildRows)
        if (gate) throw new Error(gate)
      }

      // persist rows sequentially
      for (let i = 0; i < normalizedRows.length; i++) {
        const r = normalizedRows[i]
        const conditions = rowToConditions(r.trigger_type, r)
        const items = [itemPayloadFromRow(r.item)]
        const hasChildRows =
          r.trigger_type === 'token'
            ? normalizedRows.some(
                (x) =>
                  (x.trigger_type === 'size' || x.trigger_type === 'area' || x.trigger_type === 'perimeter') &&
                  String(x.parent_variant_id ?? '') === String(r.id ?? ''),
              )
            : false
        const enabled = r.trigger_type === 'token' && hasChildRows ? false : !!r.enabled
        const metadataJson =
          r.trigger_type === 'size' || r.trigger_type === 'area' || r.trigger_type === 'perimeter'
            ? ({
                ...(r.metadata_json ?? {}),
                parent_variant_id: String(r.parent_variant_id ?? '').trim() || null,
                parent_child_type: r.trigger_type,
              } as any)
            : (r.metadata_json ?? undefined)
        if (!r.id) {
          const payload: LineVariantCreateRequest = {
            version_id: versionId,
            base_line_id: baseLineId,
            enabled,
            priority: 100,
            action: FIXED_ACTION,
            stop_on_hit: true,
            notes: '',
            conditions,
            metadata_json: metadataJson ?? {},
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
            enabled,
            priority: 100,
            action: FIXED_ACTION,
            stop_on_hit: true,
            notes: undefined,
            conditions,
            metadata_json: metadataJson,
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
      // Saving clears local dirty state; users must re-preview to enable again (preview gating handles it).
      setModalRows((prev) => prev.map((r) => ({ ...r, dirty: false })))
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
        generateBom({ spec_text: text, model_version_id: versionId, include_disabled_variants: true }),
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

  // 规则列表层已移除：点击“物料变体”直接进入编辑工作台（避免多一层无意义的抽屉/列表）

  const updateModalRow = (key: string, patch: Partial<ModalRuleRow>) => {
    setModalRows((prev) =>
      prev.map((r) => {
        if (r.key !== key) return r
        const keys = Object.keys(patch ?? {})
        const onlyEnabledToggle = keys.length === 1 && keys[0] === 'enabled'
        const merged: ModalRuleRow = { ...r, ...patch }
        if (!onlyEnabledToggle) {
          merged.dirty = true
          // 修改规则内容后，必须“保存→预演→再启动”。避免出现“本地改了但后端还按旧启用规则预演”的错觉。
          if (merged.enabled) {
            merged.enabled = false
            message.warning('你修改了规则内容：已自动关闭“启动”。请先保存→预演→再启动。')
          }
        }
        return merged
      }),
    )
    // token 模式：二级尺寸继承一级 token；当一级 token 变化时同步给它的二级
    const patchKeys = Object.keys(patch ?? {})
    const touchedToken = patchKeys.includes('token_any') || patchKeys.includes('token_all') || patchKeys.includes('token_mode')
    if (touchedToken && draftTriggerType === 'token') {
      setModalRows((prev) => {
        const parent = prev.find((x) => x.key === key)
        if (!parent?.id) return prev
        return prev.map((r) => {
          if (r.trigger_type !== 'size' && r.trigger_type !== 'area' && r.trigger_type !== 'perimeter') return r
          if (String(r.parent_variant_id ?? '') !== String(parent.id)) return r
          const next: ModalRuleRow = { ...r, ...(patch as any), dirty: true }
          if (next.enabled) next.enabled = false
          return next
        })
      })
    }
    // 仅切换“启动(enabled)”不应使预演失效，否则会出现：预演通过→打开启动→保存时又提示必须预演 的冲突
    const onlyEnabledToggle = patchKeys.length === 1 && patchKeys[0] === 'enabled'
    if (!onlyEnabledToggle) invalidatePreview()
  }

  const removeModalRow = async (row: ModalRuleRow) => {
    if (draftTriggerType === 'token' && row.trigger_type === 'token' && row.id) {
      const children = modalRows.filter(
        (r) =>
          (r.trigger_type === 'size' || r.trigger_type === 'area' || r.trigger_type === 'perimeter') &&
          String(r.parent_variant_id ?? '') === String(row.id),
      )
      if (children.length > 0) {
        const ok = await new Promise<boolean>((resolve) => {
          Modal.confirm({
            title: '删除一级规则？',
            content: `该 token 一级下有 ${children.length} 条二级规则，将一并删除。是否继续？`,
            okText: '继续删除',
            okButtonProps: { danger: true },
            cancelText: '取消',
            onOk: () => resolve(true),
            onCancel: () => resolve(false),
          })
        })
        if (!ok) return
        for (const c of children) {
          if (c.id) await deleteVariantMutation.mutateAsync(c.id)
        }
      }
    }
    if (row.id) {
      await deleteVariantMutation.mutateAsync(row.id)
    } else {
      setModalRows((prev) => prev.filter((r) => r.key !== row.key))
    }
    // token 模式删除父行：同时清理本地子行（未入库的）
    if (draftTriggerType === 'token' && row.trigger_type === 'token' && row.id) {
      setModalRows((prev) =>
        prev.filter(
          (r) =>
            !(
              (r.trigger_type === 'size' || r.trigger_type === 'area' || r.trigger_type === 'perimeter') &&
              String(r.parent_variant_id ?? '') === String(row.id)
            ),
        ),
      )
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
        trigger_type: draftTriggerType,
        parent_variant_id: null,
        metadata_json: {},
        dirty: true,
        token_mode: 'all',
        op: 'gte',
        min: null,
        max: null,
        h_op: 'gte',
        h_min: null,
        h_max: null,
        token_any: [],
        token_all: [],
        item: blankItemRow(),
      },
    ])
    if (draftTriggerType === 'token') setSelectedTokenParentKey(key)
    invalidatePreview()
  }

  const tokenParents = useMemo(() => modalRows.filter((r) => r.trigger_type === 'token'), [modalRows])
  const childrenByParentId = useMemo(() => {
    const map: Record<string, ModalRuleRow[]> = {}
    for (const r of modalRows) {
      if (r.trigger_type !== 'size' && r.trigger_type !== 'area' && r.trigger_type !== 'perimeter') continue
      const pid = String(r.parent_variant_id ?? '').trim()
      if (!pid) continue
      if (!map[pid]) map[pid] = []
      map[pid].push(r)
    }
    return map
  }, [modalRows])
  const childrenOf = (parentId: string | undefined): ModalRuleRow[] => (parentId ? childrenByParentId[String(parentId)] ?? [] : [])
  const parentHasChildren = (parentId: string | undefined): boolean => childrenOf(parentId).length > 0

  const getParentChildType = (parent: ModalRuleRow): 'size' | 'area' | 'perimeter' | null => {
    const ch = childrenOf(parent.id)
    if (ch.length > 0) {
      const types = Array.from(
        new Set(
          ch
            .map((r) => r.trigger_type)
            .filter((t) => t === 'size' || t === 'area' || t === 'perimeter') as Array<'size' | 'area' | 'perimeter'>,
        ),
      )
      return types.length === 1 ? types[0] : null
    }
    const raw = String((parent.metadata_json as any)?.child_trigger_type ?? '').trim()
    if (raw === 'size' || raw === 'area' || raw === 'perimeter') return raw
    return null
  }

  const addChildMetricRow = (parent: ModalRuleRow, childType: 'size' | 'area' | 'perimeter') => {
    if (!parent?.id) {
      message.warning('请先保存一级规则（拿到ID）后再新增二级')
      return
    }
    const key = `tmp-${Date.now()}-${Math.random().toString(16).slice(2)}`
    const mode = inferTokenMode(parent)
    const inheritedAll = mode === 'all' ? parent.token_all ?? [] : []
    const inheritedAny = mode === 'any' ? parent.token_any ?? [] : []
    setModalRows((prev) => [
      ...(prev ?? []),
      {
        key,
        enabled: false,
        trigger_type: childType,
        parent_variant_id: parent.id,
        metadata_json: { parent_variant_id: parent.id, parent_child_type: childType },
        dirty: true,
        token_mode: mode,
        op: 'gte',
        min: null,
        max: null,
        h_op: 'gte',
        h_min: null,
        h_max: null,
        token_any: inheritedAny,
        token_all: inheritedAll,
        item: blankItemRow(),
      },
    ])
    // 有二级：一级不可启用
    updateModalRow(parent.key, { enabled: false } as any)
    invalidatePreview()
  }

  return (
    <Modal
      title={
        <Space direction="vertical" size={0}>
          <div>物料行变体</div>
          <Text type="secondary" style={{ fontSize: 12 }}>
            version={versionId.slice(0, 8)}… · base_line_id={baseLineId.slice(0, 8)}… {baseLineLabel ? `· ${baseLineLabel}` : ''}
          </Text>
        </Space>
      }
      open={open}
      onCancel={onClose}
      width={1300}
      footer={null}
      destroyOnClose
      bodyStyle={{ maxHeight: '80vh', overflowY: 'auto' }}
    >
      <Space direction="vertical" size={12} style={{ width: '100%' }}>
            <Card
              size="small"
              title={
                <Space wrap>
                  {draftTriggerType === 'token' ? (
                    <>
                      <Tag color="blue">当前物料</Tag>
                      <Text>
                        {String((baseLineQuery.data as any)?.materials?.find((x: any) => String(x?.id ?? '') === String(baseLineId))?.material_code ?? '') ||
                          baseLineLabel ||
                          baseLineId.slice(0, 8)}
                      </Text>
                      <Text type="secondary" ellipsis={{ tooltip: baseLineLabel }} style={{ maxWidth: 360 }}>
                        {String((baseLineQuery.data as any)?.materials?.find((x: any) => String(x?.id ?? '') === String(baseLineId))?.material_name ?? '') ||
                          baseLineLabel ||
                          ''}
                      </Text>
                      {(() => {
                        const base = (baseLineQuery.data as any)?.materials?.find((x: any) => String(x?.id ?? '') === String(baseLineId))
                        const unit = normalizeUnitText(String(base?.unit_of_measure ?? '')) || String(base?.unit_of_measure ?? '')
                        const price = base?.bom_unit_price ?? null
                        if (!unit && price == null) return null
                        return (
                          <Tag>
                            {price != null ? `BOM单价=${price}` : 'BOM单价=-'}/{unit || '单位-'}
                          </Tag>
                        )
                      })()}
                      <Tag>β={baseLineDefaults.base_quantity ?? 1}</Tag>
                      <Tag>α={baseLineDefaults.fixed_quantity ?? 0}</Tag>
                      <Tag>覆盖率={baseLineDefaults.coverage_ratio ?? 1}</Tag>
                      <Tag>损耗%={baseLineDefaults.loss_rate ?? 0}</Tag>
                    </>
                  ) : (
                    <>
                      <span>触发类型</span>
                      <Select
                        value={draftTriggerType}
                        style={{ width: 220 }}
                        options={[
                          { label: '尺寸（宽+高，cm）', value: 'size' },
                          { label: '宽度（cm）', value: 'width' },
                          { label: '高度（cm）', value: 'height' },
                          { label: '面积（m²）', value: 'area' },
                          { label: '周长（m）', value: 'perimeter' },
                        ]}
                        onChange={(v) => handleTriggerTypeChange(v as any)}
                      />
                      <Tag color="blue">action=replace_self</Tag>
                    </>
                  )}
                </Space>
              }
              extra={
                draftTriggerType === 'token' ? null : (
                  <Button size="small" type="primary" onClick={addModalRow}>
                    新增
                  </Button>
                )
              }
            >
              {draftTriggerType === 'token' ? (
                <Row gutter={12}>
                  <Col xs={24} lg={8}>
                    <Card
                      size="small"
                      title="一级 TOKEN（只读列表）"
                      extra={
                        <Button size="small" type="primary" onClick={addModalRow}>
                          新增一级
                        </Button>
                      }
                    >
                      <Table
                        rowKey="key"
                        size="small"
                        pagination={false}
                        dataSource={tokenParents}
                        rowClassName={(r) => (r.key === selectedTokenParentKey ? 'pm-selected-row' : '')}
                        onRow={(r) => ({
                          onClick: () => setSelectedTokenParentKey(r.key),
                          style: { cursor: 'pointer' },
                        })}
                        columns={[
                          {
                            title: 'TOKEN表达式',
                            render: (_: any, r: ModalRuleRow) => {
                              const mode = inferTokenMode(r)
                              const tokenStr = (mode === 'all' ? r.token_all : r.token_any).join(',')
                              const hasChild = !!r.id && parentHasChildren(r.id)
                              const childType = getParentChildType(r)
                              const childLabel = childType === 'size' ? '尺寸' : childType === 'area' ? '面积' : childType === 'perimeter' ? '周长' : '-'
                              return (
                                <Space direction="vertical" size={2} style={{ width: '100%' }}>
                                  <Space wrap size={6}>
                                    <Tag color="blue">{mode === 'all' ? 'token(all)' : 'token(any)'}</Tag>
                                    {hasChild ? <Tag color="orange">二级:{childLabel}</Tag> : <Tag>无二级</Tag>}
                                  </Space>
                                  <Text type="secondary" style={{ fontSize: 12 }}>
                                    {tokenStr || '（空=无条件）'}
                                  </Text>
                                </Space>
                              )
                            },
                          },
                          {
                            title: '启用',
                            width: 70,
                            render: (_: any, r: ModalRuleRow) => (
                              <Switch
                                checked={!!r.enabled}
                                disabled={!!r.id && parentHasChildren(r.id)}
                                onChange={(v) => {
                                  if (r.id && parentHasChildren(r.id)) {
                                    message.error('存在二级：一级不可启用')
                                    return
                                  }
                                  updateModalRow(r.key, { enabled: v })
                                }}
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
                      />
                    </Card>
                  </Col>
                  <Col xs={24} lg={16}>
                    {(() => {
                      const parent = tokenParents.find((p) => p.key === selectedTokenParentKey) ?? null
                      if (!parent) {
                        return <Alert type="info" showIcon message="请先在左侧选择或新增一个一级 token 规则" />
                      }
                      const hasChild = !!parent.id && parentHasChildren(parent.id)
                      const childType = getParentChildType(parent)
                      const childTypeLabel = childType === 'size' ? '尺寸（宽+高）' : childType === 'area' ? '面积' : childType === 'perimeter' ? '周长' : null
                      const disableParentReplace = hasChild

                      const parentMode = inferTokenMode(parent)
                      const parentTokenStr = (parentMode === 'all' ? parent.token_all : parent.token_any).join(',')

                      return (
                        <Space direction="vertical" size={12} style={{ width: '100%' }}>
                          <Card
                            size="small"
                            title="一级详情（编辑）"
                            extra={
                              <Button
                                size="small"
                                type="primary"
                                loading={modalSaveMutation.isPending}
                                onClick={() => modalSaveMutation.mutate()}
                              >
                                保存
                              </Button>
                            }
                          >
                            <Row gutter={[12, 12]}>
                              <Col span={24}>
                                <Row gutter={8} align="middle" wrap={false}>
                                  <Col flex="auto">
                                    <Space wrap size={8}>
                                      <Tag color="blue">TOKEN 条件表达式</Tag>
                                      <Select
                                        size="small"
                                        value={parentMode}
                                        style={{ width: 120 }}
                                        options={[
                                          { label: 'token(all)', value: 'all' },
                                          { label: 'token(any)', value: 'any' },
                                        ]}
                                        onChange={(v) => {
                                          const next = (v as any) ?? 'all'
                                          if (next === 'all') {
                                            updateModalRow(parent.key, {
                                              token_mode: 'all',
                                              token_all: parent.token_all?.length ? parent.token_all : parent.token_any,
                                              token_any: [],
                                            })
                                          }
                                          if (next === 'any') {
                                            updateModalRow(parent.key, {
                                              token_mode: 'any',
                                              token_any: parent.token_any?.length ? parent.token_any : parent.token_all,
                                              token_all: [],
                                            })
                                          }
                                        }}
                                      />
                                      <Input
                                        size="small"
                                        style={{ width: 220 }}
                                        value={parentTokenStr}
                                        placeholder="token 可空，逗号分隔"
                                        onChange={(e) => {
                                          const arr = splitTokens(e.target.value)
                                          updateModalRow(parent.key, parentMode === 'all' ? { token_all: arr } : { token_any: arr })
                                        }}
                                      />
                                      {hasChild ? <Tag color="orange">存在二级：一级仅作 token 门槛（可空）</Tag> : <Tag color="green">无二级：本级替换生效</Tag>}
                                    </Space>
                                  </Col>
                                </Row>
                              </Col>

                              {!hasChild ? (
                              <Col span={24}>
                                <Row gutter={8} align="middle">
                                  <Col flex="260px">
                                    <Space direction="vertical" size={2} style={{ width: '100%' }}>
                                      <Text strong>替换物料</Text>
                                      <Space size={6} wrap>
                                        <Text code>{parent.item.material_code ?? (parent.item.material_ref_id ? String(parent.item.material_ref_id).slice(0, 8) + '…' : '无')}</Text>
                                        <Text type="secondary" ellipsis={{ tooltip: parent.item.material_name ?? '' }} style={{ maxWidth: 160 }}>
                                          {parent.item.material_name ?? (parent.item.material_code ? '' : '无')}
                                        </Text>
                                        <Button
                                          size="small"
                                          type="text"
                                          icon={<EditOutlined />}
                                          disabled={disableParentReplace}
                                          onClick={() => {
                                            setMaterialPickerRowKey(parent.key)
                                            setMaterialPickerOpen(true)
                                          }}
                                        />
                                      </Space>
                                    </Space>
                                  </Col>
                                  <Col flex="70px">
                                    <Text strong>用量(β)</Text>
                                    <InputNumber
                                      size="small"
                                      min={0}
                                      disabled={disableParentReplace}
                                      value={toNumber(parent.item.base_quantity, 0)}
                                      onChange={(v) =>
                                        updateModalRow(parent.key, { item: { ...parent.item, base_quantity: toNumber(v, 0) } })
                                      }
                                      style={{ width: 70 }}
                                    />
                                  </Col>
                                  <Col flex="70px">
                                    <Text strong>固定(α)</Text>
                                    <InputNumber
                                      size="small"
                                      min={0}
                                      disabled={disableParentReplace}
                                      value={toNumber(parent.item.fixed_quantity, 0)}
                                      onChange={(v) =>
                                        updateModalRow(parent.key, { item: { ...parent.item, fixed_quantity: toNumber(v, 0) } })
                                      }
                                      style={{ width: 70 }}
                                    />
                                  </Col>
                                  <Col flex="70px">
                                    <Text strong>覆盖率</Text>
                                    <InputNumber
                                      size="small"
                                      min={0}
                                      max={1}
                                      step={0.1}
                                      disabled={disableParentReplace}
                                      value={toNumber(parent.item.coverage_ratio, 1)}
                                      onChange={(v) =>
                                        updateModalRow(parent.key, { item: { ...parent.item, coverage_ratio: toNumber(v, 1) } })
                                      }
                                      style={{ width: 70 }}
                                    />
                                  </Col>
                                  <Col flex="70px">
                                    <Text strong>损耗%</Text>
                                    <InputNumber
                                      size="small"
                                      min={0}
                                      max={100}
                                      disabled={disableParentReplace}
                                      value={toNumber(parent.item.loss_rate, 0)}
                                      onChange={(v) => updateModalRow(parent.key, { item: { ...parent.item, loss_rate: toNumber(v, 0) } })}
                                      style={{ width: 70 }}
                                    />
                                  </Col>
                                </Row>
                              </Col>
                              ) : null}
                            </Row>
                          </Card>

                          <Card
                            size="small"
                            title="二级规则（多行=OR）"
                            extra={
                              <Space size={8}>
                                <Select
                                  size="small"
                                  style={{ width: 220 }}
                                  placeholder="新建二级：选择类型"
                                  value={childType ?? undefined}
                                  disabled={hasChild}
                                  options={[
                                    { label: '尺寸（宽+高，cm）', value: 'size' },
                                    { label: '面积（m²）', value: 'area' },
                                    { label: '周长（m）', value: 'perimeter' },
                                  ]}
                                  onChange={(v) => {
                                    updateModalRow(parent.key, { metadata_json: { ...(parent.metadata_json ?? {}), child_trigger_type: v as any } } as any)
                                  }}
                                />
                                <Button
                                  size="small"
                                  type="primary"
                                  onClick={() => {
                                    const t = getParentChildType(parent)
                                    if (!t) {
                                      message.error('请先选择二级类型（尺寸/面积/周长）')
                                      return
                                    }
                                    addChildMetricRow(parent, t)
                                  }}
                                  disabled={!parent.id}
                                >
                                  +行
                                </Button>
                              </Space>
                            }
                          >
                            {hasChild && childTypeLabel ? (
                              <div style={{ marginBottom: 8 }}>
                                <Text type="secondary" style={{ fontSize: 12 }}>
                                  当前二级类型：{childTypeLabel}（类型锁定；需要变更请先删除全部二级再选）
                                </Text>
                              </div>
                            ) : null}

                            <Table
                              rowKey="key"
                              size="small"
                              pagination={false}
                              dataSource={childrenOf(parent.id)}
                              columns={[
                                {
                                  title: '启用',
                                  width: 70,
                                  render: (_: any, r: ModalRuleRow) => (
                                    <Switch checked={!!r.enabled} onChange={(v) => updateModalRow(r.key, { enabled: v })} />
                                  ),
                                },
                                {
                                  title: '表达式/替换物料',
                                  render: (_: any, r: ModalRuleRow) => {
                                    const unit = r.trigger_type === 'area' ? 'm²' : r.trigger_type === 'perimeter' ? 'm' : 'cm'
                                    const materialCode = r.item.material_code ?? null
                                    const materialName = r.item.material_name ?? null
                                    const materialDisplay =
                                      materialCode || materialName
                                        ? `${materialCode ?? '无'} ${materialName ?? ''}`.trim()
                                        : r.item.material_ref_id
                                          ? `${String(r.item.material_ref_id).slice(0, 8)}…`
                                          : '无'
                                    return (
                                      <Space direction="vertical" size={6} style={{ width: '100%' }}>
                                        {/* 第一行：条件表达式 */}
                                        <div>
                                          {r.trigger_type === 'size' ? (
                                            <Space wrap size={8}>
                                              <Tag>宽(cm)</Tag>
                                              <Select
                                                size="small"
                                                value={r.op}
                                                style={{ width: 92 }}
                                                options={[
                                                  { label: '≥', value: 'gte' },
                                                  { label: '≤', value: 'lte' },
                                                  { label: '=', value: 'eq' },
                                                  { label: '区间', value: 'between' },
                                                ]}
                                                onChange={(v) => updateModalRow(r.key, { op: v as any })}
                                              />
                                              {r.op === 'between' ? (
                                                <Space wrap size={6}>
                                                  <InputNumber
                                                    size="small"
                                                    placeholder="min"
                                                    value={r.min}
                                                    onChange={(v) => updateModalRow(r.key, { min: v == null ? null : Number(v) })}
                                                  />
                                                  <Text type="secondary">到</Text>
                                                  <InputNumber
                                                    size="small"
                                                    placeholder="max"
                                                    value={r.max}
                                                    onChange={(v) => updateModalRow(r.key, { max: v == null ? null : Number(v) })}
                                                  />
                                                </Space>
                                              ) : (
                                                <InputNumber
                                                  size="small"
                                                  placeholder="value"
                                                  value={r.op === 'lte' ? r.max : r.min}
                                                  onChange={(v) => {
                                                    const n = v == null ? null : Number(v)
                                                    if (r.op === 'lte') updateModalRow(r.key, { max: n })
                                                    else updateModalRow(r.key, { min: n })
                                                  }}
                                                />
                                              )}
                                              <Tag>高(cm)</Tag>
                                              <Select
                                                size="small"
                                                value={r.h_op ?? 'gte'}
                                                style={{ width: 92 }}
                                                options={[
                                                  { label: '≥', value: 'gte' },
                                                  { label: '≤', value: 'lte' },
                                                  { label: '=', value: 'eq' },
                                                  { label: '区间', value: 'between' },
                                                ]}
                                                onChange={(v) => updateModalRow(r.key, { h_op: v as any })}
                                              />
                                              {(r.h_op ?? 'gte') === 'between' ? (
                                                <Space wrap size={6}>
                                                  <InputNumber
                                                    size="small"
                                                    placeholder="min"
                                                    value={r.h_min ?? null}
                                                    onChange={(v) => updateModalRow(r.key, { h_min: v == null ? null : Number(v) })}
                                                  />
                                                  <Text type="secondary">到</Text>
                                                  <InputNumber
                                                    size="small"
                                                    placeholder="max"
                                                    value={r.h_max ?? null}
                                                    onChange={(v) => updateModalRow(r.key, { h_max: v == null ? null : Number(v) })}
                                                  />
                                                </Space>
                                              ) : (
                                                <InputNumber
                                                  size="small"
                                                  placeholder="value"
                                                  value={(r.h_op ?? 'gte') === 'lte' ? (r.h_max ?? null) : (r.h_min ?? null)}
                                                  onChange={(v) => {
                                                    const n = v == null ? null : Number(v)
                                                    if ((r.h_op ?? 'gte') === 'lte') updateModalRow(r.key, { h_max: n })
                                                    else updateModalRow(r.key, { h_min: n })
                                                  }}
                                                />
                                              )}
                                            </Space>
                                          ) : (
                                            <Space wrap size={8}>
                                              <Select
                                                size="small"
                                                value={r.op}
                                                style={{ width: 92 }}
                                                options={[
                                                  { label: '≥', value: 'gte' },
                                                  { label: '≤', value: 'lte' },
                                                  { label: '=', value: 'eq' },
                                                  { label: '区间', value: 'between' },
                                                ]}
                                                onChange={(v) => updateModalRow(r.key, { op: v as any })}
                                              />
                                              {r.op === 'between' ? (
                                                <Space wrap size={6}>
                                                  <InputNumber
                                                    size="small"
                                                    placeholder="min"
                                                    value={r.min}
                                                    onChange={(v) => updateModalRow(r.key, { min: v == null ? null : Number(v) })}
                                                  />
                                                  <Text type="secondary">到</Text>
                                                  <InputNumber
                                                    size="small"
                                                    placeholder="max"
                                                    value={r.max}
                                                    onChange={(v) => updateModalRow(r.key, { max: v == null ? null : Number(v) })}
                                                  />
                                                  <Text type="secondary">{unit}</Text>
                                                </Space>
                                              ) : (
                                                <Space wrap size={6}>
                                                  <InputNumber
                                                    size="small"
                                                    placeholder="value"
                                                    value={r.op === 'lte' ? r.max : r.min}
                                                    onChange={(v) => {
                                                      const n = v == null ? null : Number(v)
                                                      if (r.op === 'lte') updateModalRow(r.key, { max: n })
                                                      else updateModalRow(r.key, { min: n })
                                                    }}
                                                  />
                                                  <Text type="secondary">{unit}</Text>
                                                </Space>
                                              )}
                                            </Space>
                                          )}
                                        </div>

                                        {/* 第二行：替换物料（按钮在前、无图标） */}
                                        <div>
                                          <Space size={8} wrap>
                                            <Button
                                              size="small"
                                              type="default"
                                              onClick={() => {
                                                setMaterialPickerRowKey(r.key)
                                                setMaterialPickerOpen(true)
                                              }}
                                            >
                                              替换物料
                                            </Button>
                                            <Text code>{materialDisplay}</Text>
                                          </Space>
                                        </div>

                                        {/* 第三行：参数 */}
                                        <div>
                                          <Space size={8} wrap>
                                            <Text type="secondary">用量(β)：</Text>
                                            <InputNumber
                                              size="small"
                                              min={0}
                                              value={toNumber(r.item.base_quantity, 0)}
                                              onChange={(v) =>
                                                updateModalRow(r.key, { item: { ...r.item, base_quantity: toNumber(v, 0) } })
                                              }
                                              style={{ width: 58 }}
                                            />
                                            <Text type="secondary">固定(α)：</Text>
                                            <InputNumber
                                              size="small"
                                              min={0}
                                              value={toNumber(r.item.fixed_quantity, 0)}
                                              onChange={(v) =>
                                                updateModalRow(r.key, { item: { ...r.item, fixed_quantity: toNumber(v, 0) } })
                                              }
                                              style={{ width: 58 }}
                                            />
                                            <Text type="secondary">覆盖率：</Text>
                                            <InputNumber
                                              size="small"
                                              min={0}
                                              max={1}
                                              step={0.1}
                                              value={toNumber(r.item.coverage_ratio, 1)}
                                              onChange={(v) =>
                                                updateModalRow(r.key, { item: { ...r.item, coverage_ratio: toNumber(v, 1) } })
                                              }
                                              style={{ width: 58 }}
                                            />
                                            <Text type="secondary">损耗%：</Text>
                                            <InputNumber
                                              size="small"
                                              min={0}
                                              max={100}
                                              value={toNumber(r.item.loss_rate, 0)}
                                              onChange={(v) => updateModalRow(r.key, { item: { ...r.item, loss_rate: toNumber(v, 0) } })}
                                              style={{ width: 58 }}
                                            />
                                          </Space>
                                        </div>
                                      </Space>
                                    )
                                  },
                                },
                                {
                                  title: '',
                                  width: 44,
                                  render: (_: any, r: ModalRuleRow) => (
                                    <Button size="small" danger type="text" icon={<DeleteOutlined />} onClick={() => void removeModalRow(r)} />
                                  ),
                                },
                              ]}
                              scroll={{ x: 900 }}
                            />
                          </Card>
                        </Space>
                      )
                    })()}
                  </Col>
                </Row>
              ) : (
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
                          // 非 token 模式下不允许出现 token 行；这里不再做 token 父子拦截
                          if (v && r.dirty) {
                            message.error('规则有未保存改动：请先保存→预演→再启动。')
                            return
                          }
                          if (v && (!lastPreviewOk || previewStale)) {
                            message.error(previewStale ? '预演已过期：请先重新预演' : '启用前必须先预演成功')
                            return
                          }
                          if (v) {
                            const t = r.trigger_type
                            const needDim =
                              t === 'size'
                                ? 'size_wh'
                                : t === 'width'
                                  ? 'width_cm'
                                  : t === 'height'
                                    ? 'height_cm'
                                    : t === 'area'
                                      ? 'area_m2'
                                      : t === 'perimeter'
                                        ? 'perimeter_m'
                                        : null
                            if (needDim === 'size_wh') {
                              if ((lastPreviewSummary as any)?.width_cm == null || (lastPreviewSummary as any)?.height_cm == null) {
                                message.error(`你选择了“${triggerLabel(t)}”，但预演样例未解析出宽/高，请换 spec_text 重新预演`)
                                return
                              }
                            } else if (needDim && (lastPreviewSummary as any)?.[needDim] == null) {
                              message.error(`你选择了“${triggerLabel(t)}”，但预演样例未解析出对应数值，请换 spec_text 重新预演`)
                              return
                            }
                            const ref = String(r.item.material_ref_id ?? '').trim()
                            if (!ref) {
                              message.error('请先选择替换物料并保存（让后端回填单位）')
                              return
                            }
                            if (!baseUnit) {
                              message.error('基准行单位缺失：请先补齐主数据单位并“保存清单”，再回来启用规则')
                              return
                            }
                            const targetU = normalizeUnit(r.item.unit_of_measure)
                            if (!targetU) {
                              message.error('替换物料单位缺失：请先保存（让后端回填 unit_of_measure）')
                              return
                            }
                            if (targetU !== baseUnit) {
                              message.error(`单位不一致：基准=${baseUnit}，替换物料=${targetU}（只允许同单位平替）`)
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
                      // 一级：TOKEN（可空）。二级：选一个指标类型（token/尺寸/宽/高/面积/周长）
                      const mode = inferTokenMode(r)
                      const tokenStr = (mode === 'all' ? r.token_all : r.token_any).join(',')
                      const tokenEditor = (
                        <Space wrap size={6}>
                          <Select
                            size="small"
                            value={mode}
                            style={{ width: 120 }}
                            options={[
                              { label: 'token(all)', value: 'all' },
                              { label: 'token(any)', value: 'any' },
                            ]}
                            onChange={(v) => {
                              const next = (v as TokenMode) ?? 'all'
                              if (next === 'all') {
                                updateModalRow(r.key, {
                                  token_mode: 'all',
                                  token_all: r.token_all?.length ? r.token_all : r.token_any,
                                  token_any: [],
                                })
                              }
                              if (next === 'any') {
                                updateModalRow(r.key, {
                                  token_mode: 'any',
                                  token_any: r.token_any?.length ? r.token_any : r.token_all,
                                  token_all: [],
                                })
                              }
                            }}
                          />
                          <Input
                            placeholder={mode === 'all' ? 'TOKEN(all) 可空，逗号分隔' : 'TOKEN(any) 可空，逗号分隔'}
                            value={tokenStr}
                            onChange={(e) => {
                              const arr = splitTokens(e.target.value)
                              updateModalRow(r.key, mode === 'all' ? { token_all: arr } : { token_any: arr })
                            }}
                            style={{ width: 260 }}
                            size="small"
                          />
                          {modelAnchorToken ? (
                            <Tag color={autoAnchorModelToken ? 'blue' : 'default'}>
                              自动锚定：{modelAnchorToken} {autoAnchorModelToken ? '' : '（已关闭）'}
                            </Tag>
                          ) : null}
                        </Space>
                      )

                      if (draftTriggerType === 'size') {
                        return (
                          <Space wrap size={8}>
                            {tokenEditor}
                            <Tag style={{ marginInlineStart: 4 }}>宽(cm)</Tag>
                            <Select
                              size="small"
                              value={r.op}
                              style={{ width: 92 }}
                              options={[
                                { label: '≥', value: 'gte' },
                                { label: '≤', value: 'lte' },
                                { label: '=', value: 'eq' },
                                { label: '区间', value: 'between' },
                              ]}
                              onChange={(v) => updateModalRow(r.key, { op: v as any })}
                            />
                            {r.op === 'between' ? (
                              <Space wrap size={6}>
                                <InputNumber
                                  size="small"
                                  placeholder="min"
                                  value={r.min}
                                  onChange={(v) => updateModalRow(r.key, { min: v == null ? null : Number(v) })}
                                />
                                <Text type="secondary">到</Text>
                                <InputNumber
                                  size="small"
                                  placeholder="max"
                                  value={r.max}
                                  onChange={(v) => updateModalRow(r.key, { max: v == null ? null : Number(v) })}
                                />
                              </Space>
                            ) : (
                              <InputNumber
                                size="small"
                                placeholder="value"
                                value={r.op === 'lte' ? r.max : r.min}
                                onChange={(v) => {
                                  const n = v == null ? null : Number(v)
                                  if (r.op === 'lte') updateModalRow(r.key, { max: n })
                                  else updateModalRow(r.key, { min: n })
                                }}
                              />
                            )}

                            <Tag style={{ marginInlineStart: 4 }}>高(cm)</Tag>
                            <Select
                              size="small"
                              value={r.h_op ?? 'gte'}
                              style={{ width: 92 }}
                              options={[
                                { label: '≥', value: 'gte' },
                                { label: '≤', value: 'lte' },
                                { label: '=', value: 'eq' },
                                { label: '区间', value: 'between' },
                              ]}
                              onChange={(v) => updateModalRow(r.key, { h_op: v as any })}
                            />
                            {(r.h_op ?? 'gte') === 'between' ? (
                              <Space wrap size={6}>
                                <InputNumber
                                  size="small"
                                  placeholder="min"
                                  value={r.h_min ?? null}
                                  onChange={(v) => updateModalRow(r.key, { h_min: v == null ? null : Number(v) })}
                                />
                                <Text type="secondary">到</Text>
                                <InputNumber
                                  size="small"
                                  placeholder="max"
                                  value={r.h_max ?? null}
                                  onChange={(v) => updateModalRow(r.key, { h_max: v == null ? null : Number(v) })}
                                />
                              </Space>
                            ) : (
                              <InputNumber
                                size="small"
                                placeholder="value"
                                value={(r.h_op ?? 'gte') === 'lte' ? (r.h_max ?? null) : (r.h_min ?? null)}
                                onChange={(v) => {
                                  const n = v == null ? null : Number(v)
                                  if ((r.h_op ?? 'gte') === 'lte') updateModalRow(r.key, { h_max: n })
                                  else updateModalRow(r.key, { h_min: n })
                                }}
                              />
                            )}
                          </Space>
                        )
                      }

                      const unit = draftTriggerType === 'area' ? 'm²' : draftTriggerType === 'perimeter' ? 'm' : 'cm'
                      return (
                        <Space wrap size={8}>
                          {tokenEditor}
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
                          <Text type="secondary">{unit}</Text>
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
                        </Space.Compact>
                        <Text type="secondary" style={{ fontSize: 12 }}>
                          {r.item.material_code ?? '-'} {r.item.material_name ?? ''}
                        </Text>
                        <Text type="secondary" style={{ fontSize: 12 }}>
                          单位：{r.item.unit_of_measure ?? '-'}
                        </Text>
                        {(() => {
                          const baseU = baseUnit
                          const targetU = normalizeUnit(r.item.unit_of_measure)
                          if (!r.enabled) return null
                          if (!lastPreviewOk || previewStale) return null
                          if (!baseU) return <Text type="danger">基准单位缺失：请先补齐主数据单位并保存清单</Text>
                          if (!targetU) return <Text type="danger">替换物料单位缺失：请先保存规则（让后端回填）</Text>
                          if (baseU !== targetU) return <Text type="danger">单位不一致：基准={baseU}，替换={targetU}</Text>
                          return null
                        })()}
                      </Space>
                    ),
                  },
                  {
                    title: '用量(β)',
                    width: 70,
                    render: (_: any, r: ModalRuleRow) => (
                      <InputNumber
                        size="small"
                        min={0}
                        value={toNumber(r.item.base_quantity, 0)}
                        onChange={(v) => updateModalRow(r.key, { item: { ...r.item, base_quantity: toNumber(v, 0) } })}
                        style={{ width: 70 }}
                      />
                    ),
                  },
                  {
                    title: '固定(α)',
                    width: 70,
                    render: (_: any, r: ModalRuleRow) => (
                      <InputNumber
                        size="small"
                        min={0}
                        value={toNumber(r.item.fixed_quantity, 0)}
                        onChange={(v) => updateModalRow(r.key, { item: { ...r.item, fixed_quantity: toNumber(v, 0) } })}
                        style={{ width: 70 }}
                      />
                    ),
                  },
                  {
                    title: '覆盖率',
                    width: 70,
                    render: (_: any, r: ModalRuleRow) => (
                      <InputNumber
                        size="small"
                        min={0}
                        max={1}
                        step={0.1}
                        value={toNumber(r.item.coverage_ratio, 1)}
                        onChange={(v) => updateModalRow(r.key, { item: { ...r.item, coverage_ratio: toNumber(v, 1) } })}
                        style={{ width: 70 }}
                      />
                    ),
                  },
                  {
                    title: '损耗%',
                    width: 70,
                    render: (_: any, r: ModalRuleRow) => (
                      <InputNumber
                        size="small"
                        min={0}
                        max={100}
                        value={toNumber(r.item.loss_rate, 0)}
                        onChange={(v) => updateModalRow(r.key, { item: { ...r.item, loss_rate: toNumber(v, 0) } })}
                        style={{ width: 70 }}
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
              )}
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
                    onClick={() => {
                      if (anyDirty) {
                        message.error('你有未保存的改动：预演只读取“已保存入库”的规则。请先点“保存/创建并保存”。')
                        return
                      }
                      previewMutation.mutate()
                    }}
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
                          render: (v) => formatQty2(v),
                        },
                        {
                          title: '单位',
                          width: 80,
                          dataIndex: 'unit_of_measure',
                          // normalizeUnit returns '' when empty; use || to show '-' instead of blank cell.
                          render: (v) => normalizeUnit(v) || '-',
                        },
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
        <MaterialPickerDrawer
          open={materialPickerOpen}
          onClose={() => {
            setMaterialPickerOpen(false)
            setMaterialPickerRowKey(null)
          }}
          title="选择替换物料（同单位平替）"
          initialTab="real"
          defaultOnlyBom
          baseUnit={baseUnit}
          maxSelection={1}
          confirmText="选择"
          defaultPageSize={50}
          onConfirm={async (result) => {
            const key = materialPickerRowKey
            if (!key) return
            const inheritedMethod = baseLineParamsFromBom.calculation_method
            const inheritedBaseQty = baseLineParamsFromBom.base_quantity

            if (result.kind === 'virtual') {
              const vm = (result.materials ?? [])[0] as any
              if (!vm) return
              updateModalRow(key, {
                item: {
                  ...(modalRows.find((x) => x.key === key)?.item ?? ({} as any)),
                  material_kind: 'virtual',
                  material_ref_id: vm.id,
                  material_code: vm.virtual_code ?? null,
                  material_name: vm.name ?? null,
                  unit_of_measure: vm.unit ?? null,
                  calculation_method:
                    inheritedMethod ??
                    ((modalRows.find((x) => x.key === key)?.item as any)?.calculation_method ?? 'count'),
                  base_quantity:
                    inheritedBaseQty != null && Number.isFinite(inheritedBaseQty)
                      ? inheritedBaseQty
                      : ((modalRows.find((x) => x.key === key)?.item as any)?.base_quantity ?? 1),
                } as any,
              })
              return
            }

            const m = (result.materials ?? [])[0] as any
            if (!m) return
            updateModalRow(key, {
              item: {
                ...(modalRows.find((x) => x.key === key)?.item ?? ({} as any)),
                material_kind: result.kind === 'bom' ? 'real' : 'real',
                material_ref_id: m.id,
                material_code: m.material_code,
                material_name: m.material_name,
                unit_of_measure: m.unit ?? null,
                // 关键：替换物料默认继承基准行的计量方式与 β，避免出现替换后 computed_quantity=0 的误导
                calculation_method:
                  inheritedMethod ??
                  ((modalRows.find((x) => x.key === key)?.item as any)?.calculation_method ?? 'count'),
                base_quantity:
                  inheritedBaseQty != null && Number.isFinite(inheritedBaseQty)
                    ? inheritedBaseQty
                    : ((modalRows.find((x) => x.key === key)?.item as any)?.base_quantity ?? 1),
              } as any,
            })
          }}
        />
      </Space>
    </Modal>
  )
}


