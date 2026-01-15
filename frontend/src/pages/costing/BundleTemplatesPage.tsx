import { useEffect, useMemo, useState } from 'react'
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
  List,
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
  ArrowDownOutlined,
  ArrowUpOutlined,
  LeftOutlined,
  RightOutlined,
  CheckCircleFilled,
  CloseCircleFilled,
  CopyOutlined,
  DeleteOutlined,
  PauseCircleOutlined,
  PlayCircleOutlined,
} from '@ant-design/icons'

import {
  archiveBundleTemplate,
  cloneBundleTemplate,
  createBundleTemplate,
  fetchBundleTemplates,
  generateBomBySpecDebug,
  fetchProcessModule,
  fetchProductModelVersionLines,
  fetchProductModelVersions,
  fetchStructureStandards,
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
  // 指定模式：把所选变体规则依赖的 TOKEN 直接注入到组件行 tokens，不依赖交易规格解析
  tokens?: string[]
  // 指定(强制命中)：可选强制指定某个 base_line_id 使用某条 line-variant
  // shape: { "<base_line_id>": "<variant_id>" }
  force_variant_by_base_line?: Record<string, string>
}

type PhrasePresetRow = {
  selector: string // AA/AB/... stable id, NOT derived from array index
  phrase: string
  enabled?: boolean
  // parse: B-XXXXAA（解析型）；force: Z-XXXXAA（指定型，运营看到 Z 即无需查/写触发词）
  mode?: 'parse' | 'force'
  components: ComponentRow[]
}

const parseTags = (meta: any): string[] => {
  const raw = meta?.tags
  return Array.isArray(raw) ? raw.map((x) => String(x)).filter(Boolean) : []
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
  const d = formatBetween(cond.diameter_between, 'cm')
  const a = formatBetween(cond.area_between, 'm²')
  const p = formatBetween(cond.perimeter_between, 'm')
  if (w) parts.push(`宽: ${w}`)
  if (h) parts.push(`高: ${h}`)
  if (d) parts.push(`直径: ${d}`)
  if (a) parts.push(`面积: ${a}`)
  if (p) parts.push(`周长: ${p}`)
  return parts.join('；') || '-'
}

const extractTokensForVariant = (v: any): string[] => {
  const cond = (v?.conditions ?? {}) as any
  const anyTokens = Array.isArray(cond?.spec_contains_any) ? cond.spec_contains_any : []
  const allTokens = Array.isArray(cond?.spec_contains_all) ? cond.spec_contains_all : []
  const out: string[] = []
  for (const t of [...anyTokens, ...allTokens]) {
    const s = String(t ?? '').trim()
    if (!s) continue
    const up = s.toUpperCase()
    // runtime-only binding tokens (not customer-facing)
    if (up.startsWith('MODEL:') || up.startsWith('M:') || up.startsWith('BOUND_VERSION:') || up.startsWith('SKU:')) continue
    out.push(s)
  }
  const seen = new Set<string>()
  const uniq: string[] = []
  for (const x of out) {
    const k = String(x).trim()
    if (!k || seen.has(k)) continue
    seen.add(k)
    uniq.push(k)
  }
  return uniq
}

const normalizeBundleToken = (raw: any): string => {
  let s = String(raw ?? '').trim().toUpperCase()
  if (!s) return ''
  s = s.replace(/^BUNDLE:/, 'B:')
  if (!s.startsWith('B:')) s = `B:${s}`
  while (s.startsWith('B:B:')) s = s.replace(/^B:B:/, 'B:')
  return s
}

const toBundleTokenDash = (code: string, selector?: string | null): string => {
  const c = String(code ?? '').trim().toUpperCase().replace(/^B:/, '').replace(/^BUNDLE:/, '').replace(/^B-/, '')
  const sel = String(selector ?? '').trim().toUpperCase()
  // Format rules:
  // - New short form (only when CODE length==4 and selector length==2): B-XXXXAA
  // - Legacy/compat selector form (any CODE): B-CODE-AA
  if (sel) {
    if (c.length === 4 && sel.length === 2) return `B-${c}${sel}`
    return `B-${c}-${sel}`
  }
  return `B-${c}`
}

const toSelector2 = (idx: number): string => {
  if (idx < 0 || idx >= 26 * 26) return ''
  const a = Math.floor(idx / 26)
  const b = idx % 26
  return String.fromCharCode('A'.charCodeAt(0) + a) + String.fromCharCode('A'.charCodeAt(0) + b)
}

const allocateNextSelector2 = (used: Set<string>): string => {
  for (let i = 0; i < 26 * 26; i++) {
    const s = toSelector2(i)
    if (s && !used.has(s)) return s
  }
  return 'ZZ'
}

const normalizeSingleToken = (raw: string): string => {
  const s = String(raw ?? '').trim()
  if (!s) return ''
  // 运营口径：{} 内只允许 1 个 TOKEN。这里把空格/逗号/顿号/分号等作为分隔符，取第一个。
  const parts = s.split(/[\s,，、;；]+/).map((x) => String(x).trim()).filter(Boolean)
  return parts[0] ?? ''
}

const formatTokenBrace = (token: string): string => {
  const t = normalizeSingleToken(token)
  return t ? `{${t}}` : '{}'
}

type AttributeGroup = { key: string; options: string[]; isZeroCostGroup: boolean }
type AttributeComponentGroups = { componentIndex: number; groups: AttributeGroup[] }

const getDefaultSelectionForGroup = (g: AttributeGroup): string => {
  // zero-cost 互斥组默认空（不计入自动生成）
  if (g.isZeroCostGroup) return ''
  // 其它互斥组默认第一个非空项（兜底token优先）
  const uniq: string[] = []
  const seen = new Set<string>()
  for (const x of g.options ?? []) {
    const t = normalizeSingleToken(x)
    const k = t || '__EMPTY__'
    if (seen.has(k)) continue
    seen.add(k)
    uniq.push(t)
  }
  return uniq.find((x) => !!String(x).trim()) ?? ''
}

const getEffectiveSelection = (args: {
  presetIndex: number
  componentIndex: number
  group: AttributeGroup
  attributeGroupSelections: Record<string, string>
}): string => {
  const { presetIndex, componentIndex, group, attributeGroupSelections } = args
  const selKey = `${presetIndex}:${componentIndex}:${group.key}`
  if (Object.prototype.hasOwnProperty.call(attributeGroupSelections, selKey)) {
    return normalizeSingleToken(String(attributeGroupSelections[selKey] ?? ''))
  }
  return getDefaultSelectionForGroup(group)
}

const formatCm = (n: any): string => {
  const v = Number(n)
  if (!Number.isFinite(v)) return '0'
  const rounded = Math.round(v * 100) / 100
  const s = String(rounded)
  // avoid trailing .0/.00
  return s.includes('.') ? s.replace(/\.?0+$/, '') : s
}

const buildAttributeFormulaAndGroups = (args: {
  presetIndex: number
  componentOrder?: number[]
  componentRows: any[]
  presetSelectedByIdx: Record<string, Record<string, any>>
  fallbackTokenOverrides: Record<string, string>
  variantTokenOptionsByVersionBaseLine: Record<string, Record<string, string[]>>
  baseLineInfoByVersionBaseLine: Record<string, Record<string, { orderIndex: number; isZeroCost: boolean }>>
}): { formula: string; components: AttributeComponentGroups[] } => {
  const { presetIndex, componentOrder, componentRows, presetSelectedByIdx, fallbackTokenOverrides, variantTokenOptionsByVersionBaseLine, baseLineInfoByVersionBaseLine } = args
  if (!Array.isArray(componentRows) || componentRows.length <= 0) return { formula: '', components: [] }

  const parts: string[] = []
  const components: AttributeComponentGroups[] = []
  const defaultOrder = componentRows.map((_, i) => i)
  const order = Array.isArray(componentOrder) && componentOrder.length ? componentOrder : defaultOrder
  for (const cIdx of order) {
    if (cIdx < 0 || cIdx >= componentRows.length) continue
    const rr = componentRows[cIdx] as any
    const versionId = String(rr?.model_version_id ?? '').trim()
    const k = `${presetIndex}:${cIdx}`
    const sel = (presetSelectedByIdx?.[k] ?? {}) as Record<string, any>

    // 互斥组选项生成规则（确定性）：
    // - 以 base_line_id 为原子：默认选项来自兜底 TOKEN（fallback_token_overrides）
    // - 可选项来自该 base_line_id 关联的变体规则中出现过的 TOKEN（extractTokensForVariant）
    // - 多个 base_line_id 若“选项集”完全相同，则合并为同一个互斥组（用于表达“同一个TOKEN可替换多处”）
    const rawBaseLineIds: string[] = []
    // 关键口径：公式仅基于“已筛选/已强制”的基准行（base_line_id）。
    // 若用户未筛选（parent/forced 均为空），不应生成该互斥组（尤其是兜底-零成本的 {} 分支）。
    for (const [baseLineId, v] of Object.entries(sel ?? {})) {
      const id = String(baseLineId ?? '').trim()
      if (!id) continue
      const parent = String((v as any)?.parent_variant_id ?? '').trim()
      const forced = String((v as any)?.forced_child_variant_id ?? '').trim()
      if (!parent && !forced) continue
      rawBaseLineIds.push(id)
    }
    const fm = rr?.force_variant_by_base_line && typeof rr.force_variant_by_base_line === 'object' ? rr.force_variant_by_base_line : {}
    for (const baseLineId of Object.keys(fm ?? {})) {
      const id = String(baseLineId ?? '').trim()
      if (id) rawBaseLineIds.push(id)
    }
    const seenId = new Set<string>()
    const uniqBaseLineIds = rawBaseLineIds.filter((x) => (seenId.has(x) ? false : (seenId.add(x), true)))

    const infoByBase = (baseLineInfoByVersionBaseLine?.[versionId] ?? {}) as Record<string, { orderIndex: number; isZeroCost: boolean }>
    const baseLineIdsSorted = uniqBaseLineIds.slice().sort((a, b) => {
      const ia = infoByBase?.[a]
      const ib = infoByBase?.[b]
      const za = ia?.isZeroCost ? 1 : 0
      const zb = ib?.isZeroCost ? 1 : 0
      if (za !== zb) return zb - za // zero-cost first
      const oa = Number.isFinite(ia?.orderIndex) ? Number(ia.orderIndex) : 1e9
      const ob = Number.isFinite(ib?.orderIndex) ? Number(ib.orderIndex) : 1e9
      return oa - ob
    })

    const groupsInOrder: AttributeGroup[] = []
    const seenGroupKey = new Set<string>()

    for (const baseLineId of baseLineIdsSorted) {
      const isZeroCost = !!infoByBase?.[baseLineId]?.isZeroCost
      const overrideKey = `${versionId}:${baseLineId}`
      const defaultToken = String(fallbackTokenOverrides?.[overrideKey] ?? '').trim()
      const alt = (variantTokenOptionsByVersionBaseLine?.[versionId] ?? {})?.[baseLineId] ?? []
      const altTokens = Array.isArray(alt) ? alt.map((x) => String(x ?? '').trim()).filter(Boolean) : []

      const seenOpt = new Set<string>()
      const opts: string[] = []
      // 关键口径：
      // - 只有当基准物料为“兜底-零成本”时，才允许空选项 {}（表示“没有这个选项”）
      // - 非零成本基准物料不允许空选项（否则语义不成立）
      if (isZeroCost) {
        opts.push('') // force empty default
        seenOpt.add('__EMPTY__')
      } else if (defaultToken) {
        const d = normalizeSingleToken(defaultToken)
        if (d) {
          opts.push(d)
          seenOpt.add(d)
        }
      }
      // 其它选项按字面排序，保持稳定
      const rest = altTokens
        .map((x) => normalizeSingleToken(x))
        .filter((x) => x && !seenOpt.has(x))
        .sort((a, b) => a.localeCompare(b, 'zh-Hans-CN'))
      for (const t of rest) {
        seenOpt.add(t)
        opts.push(t)
      }

      // 若该 baseLine 无任何可选项，则不形成组
      // - zero-cost: 没有任何非空候选 => 不形成组（不存在“可选件”就不应该出现 [{}]）
      // - non-zero-cost: 没有默认且没有候选 => 不形成组
      if (isZeroCost) {
        const hasNonEmpty = opts.some((x) => !!String(x).trim())
        if (!hasNonEmpty) continue
      } else {
        if (!opts.length) continue
      }

      const key = opts.map((x) => (normalizeSingleToken(x) ? normalizeSingleToken(x) : '__EMPTY__')).join('|')
      if (seenGroupKey.has(key)) continue
      seenGroupKey.add(key)
      groupsInOrder.push({ key, options: opts, isZeroCostGroup: isZeroCost })
    }

    const componentFormula = groupsInOrder
      .map((g) => `[${g.options.map((t) => formatTokenBrace(t)).join('')}]`)
      .join('')

    const dims = `${formatCm(rr?.width_cm)}*${formatCm(rr?.height_cm)}*${formatCm(rr?.quantity ?? 1)}`
    if (componentFormula) parts.push(`${componentFormula}${dims}`)
    if (groupsInOrder.length) components.push({ componentIndex: cIdx, groups: groupsInOrder })
  }
  return { formula: parts.join(' + '), components }
}

const copyTextToClipboard = async (text: string) => {
  const s = String(text ?? '')
  if (!s) return false
  try {
    if (navigator?.clipboard?.writeText) {
      await navigator.clipboard.writeText(s)
      return true
    }
  } catch {
    // ignore and fallback
  }
  try {
    const ta = document.createElement('textarea')
    ta.value = s
    ta.style.position = 'fixed'
    ta.style.left = '-99999px'
    ta.style.top = '0'
    document.body.appendChild(ta)
    ta.focus()
    ta.select()
    const ok = document.execCommand('copy')
    document.body.removeChild(ta)
    return ok
  } catch {
    return false
  }
}

const buildAutoRuleFromSelections = (args: {
  presetIndex: number
  components: AttributeComponentGroups[]
  componentRows: any[]
  attributeGroupSelections: Record<string, string>
  componentOrder?: number[]
  groupOrderByPresetComponent?: Record<string, string[]>
}): string => {
  const { presetIndex, components, componentRows, attributeGroupSelections, componentOrder, groupOrderByPresetComponent } = args
  if (!Array.isArray(components) || !Array.isArray(componentRows)) return ''
  const byComp = new Map<number, AttributeGroup[]>()
  for (const c of components) byComp.set(c.componentIndex, c.groups)
  const defaultOrder = componentRows.map((_: any, i: number) => i)
  const order = Array.isArray(componentOrder) && componentOrder.length ? componentOrder : defaultOrder

  const parts: string[] = []
  for (const cIdx of order) {
    if (cIdx < 0 || cIdx >= componentRows.length) continue
    const rr = componentRows[cIdx] as any
    let groups = byComp.get(cIdx) ?? []
    if (!groups.length) continue
    const groupOrderKey = `${presetIndex}:${cIdx}`
    const groupOrder = groupOrderByPresetComponent?.[groupOrderKey] ?? []
    if (Array.isArray(groupOrder) && groupOrder.length) {
      const idxMap = new Map<string, number>()
      for (let i = 0; i < groupOrder.length; i++) idxMap.set(String(groupOrder[i]), i)
      groups = groups.slice().sort((a, b) => (idxMap.get(a.key) ?? 1e9) - (idxMap.get(b.key) ?? 1e9))
    }
    const tokens: string[] = []
    for (const g of groups) {
      const t = getEffectiveSelection({ presetIndex, componentIndex: cIdx, group: g, attributeGroupSelections })
      if (!t) continue
      tokens.push(t)
    }
    if (!tokens.length) continue
    const tokenText = tokens.join('')
    const dims = `${formatCm(rr?.width_cm)}*${formatCm(rr?.height_cm)}*${formatCm(rr?.quantity ?? 1)}`
    parts.push(`${tokenText}${dims}`)
  }
  return parts.join(' + ')
}

const SLOT_CN_FALLBACK: Record<string, string> = {
  front: '前片位',
  back: '背片位',
  left: '左侧位',
  right: '右侧位',
  top: '顶部位',
  bottom: '底部位',
  center: '中心位',
  edge: '边位',
  border: '包边位',
  zipper: '拉链位',
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
  const [phrasePresets, setPhrasePresets] = useState<PhrasePresetRow[]>([])
  const [activePresetIndex, setActivePresetIndex] = useState<number>(0)
  const [attributeGroupSelections, setAttributeGroupSelections] = useState<Record<string, string>>({})
  const [componentOrderByPreset, setComponentOrderByPreset] = useState<Record<string, number[]>>({})
  const [groupOrderByPresetComponent, setGroupOrderByPresetComponent] = useState<Record<string, string[]>>({})
  // 默认兜底“对客 TOKEN”（仅用于对客展示/规范化用词；不影响真实物料/扣库/算价）
  // key: `${versionId}:${baseLineId}` -> tokenAlias (例如：黄金绒)
  const [fallbackTokenOverrides, setFallbackTokenOverrides] = useState<Record<string, string>>({})

  // 模型池（缩小范围）：多选版本
  const [modelPoolVersionIds, setModelPoolVersionIds] = useState<string[]>([])

  // 预设变体筛选：每个短语行内组件 key(pIdx:cIdx) -> { base_line_id -> selection }
  // selection:
  // - parent_variant_id: 选中的一级（token门槛）
  // - child_variant_ids: 解析命中模式下默认全选（用于说明/落库；真实命中由后端按尺寸/指标决定）
  // - forced_child_variant_id: 强制命中模式下只允许选一个子条件（精确指定）
  type VariantPresetSelection = {
    parent_variant_id: string | null
    child_variant_ids?: string[]
    forced_child_variant_id?: string | null
  }
  const [presetSelectedByIdx, setPresetSelectedByIdx] = useState<Record<string, Record<string, VariantPresetSelection>>>({})
  const [presetModalOpen, setPresetModalOpen] = useState(false)
  const [presetModalKey, setPresetModalKey] = useState<{ pIdx: number; cIdx: number } | null>(null)
  const [presetApplyMode, setPresetApplyMode] = useState<'variant' | 'force'>('variant')
  const [presetValidation, setPresetValidation] = useState<{
    presetIndex: number
    checkedAt: number
    ok: boolean
    issues: { level: 'error' | 'warn'; message: string }[]
    // component_key = `${presetIndex}:${componentIndex}`
    componentOk: Record<string, boolean>
    // base_line_key = `${presetIndex}:${componentIndex}:${baseLineId}`
    baseLineOk: Record<string, boolean>
  } | null>(null)

  // 预演（后端 debug）：直接用“短码”作为最小 spec_text 触发 /bom/generate-by-spec-debug
  const [bundlePreviewOpen, setBundlePreviewOpen] = useState(false)
  const [bundlePreviewSpecText, setBundlePreviewSpecText] = useState<string>('')
  const [bundlePreviewData, setBundlePreviewData] = useState<any | null>(null)

  const bundlePreviewMutation = useMutation({
    mutationFn: async (args: { selector: string; spec_text: string }) => {
      const res = await generateBomBySpecDebug({ spec_text: args.spec_text })
      return res
    },
    onSuccess: (res: any) => {
      setBundlePreviewData(res)
      setBundlePreviewOpen(true)
    },
    onError: (e: any) => message.error(String(e?.message ?? e)),
  })

  const selectedVersionIds = useMemo(() => {
    const ids = new Set<string>()
    for (const vid of modelPoolVersionIds ?? []) {
      const s = String(vid ?? '').trim()
      if (s) ids.add(s)
    }
    for (const p of phrasePresets ?? []) {
      const rows = Array.isArray(p?.components) ? p.components : []
      for (const r of rows) {
        const vid = String(r?.model_version_id ?? '').trim()
        if (vid) ids.add(vid)
      }
    }
    return Array.from(ids)
  }, [modelPoolVersionIds, phrasePresets])

  const currentBundleToken = useMemo(() => {
    const code = String(editing?.code ?? '').trim()
    if (code) return normalizeBundleToken(code)
    const hint = String(createdTokenHint ?? '').trim()
    if (hint) return normalizeBundleToken(hint)
    return ''
  }, [editing?.code, createdTokenHint])


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

  const versionOptionsCompact = useMemo(() => {
    const items = (versionPickerQuery.data?.items ?? []) as any[]
    return items.map((x) => {
      const mc = String(x?.model_code ?? '').trim()
      const mn = String(x?.model_name ?? '').trim()
      const label = mc && mn ? `${mc}:${mn}` : mc || mn || String(x?.version_id ?? '').slice(0, 8)
      return { value: x.version_id, label }
    })
  }, [versionPickerQuery.data])

  const versionIdToModelLabel = useMemo(() => {
    const m = new Map<string, string>()
    const items = (versionPickerQuery.data?.items ?? []) as any[]
    for (const it of items) {
      const vid = String(it?.version_id ?? '').trim()
      const mc = String(it?.model_code ?? '').trim()
      const mn = String(it?.model_name ?? '').trim()
      if (!vid) continue
      const label = mc && mn ? `${mc}:${mn}` : mc || mn || vid.slice(0, 8)
      m.set(vid, label)
    }
    return m
  }, [versionPickerQuery.data])

  const versionIdToModelId = useMemo(() => {
    const m = new Map<string, string>()
    const items = (versionPickerQuery.data?.items ?? []) as any[]
    for (const it of items) {
      const vid = String(it?.version_id ?? '').trim()
      const mid = String(it?.model_id ?? '').trim()
      if (vid && mid) m.set(vid, mid)
    }
    return m
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

  const variantTokenOptionsByVersionBaseLine = useMemo(() => {
    // version_id -> base_line_id -> token options
    const out: Record<string, Record<string, string[]>> = {}
    for (const x of (variantsSummaryQuery.data ?? []) as any[]) {
      const versionId = String((x as any)?.version_id ?? '').trim()
      if (!versionId) continue
      const items = Array.isArray((x as any)?.items) ? (x as any).items : []
      const byBase: Record<string, Set<string>> = {}
      for (const v of items) {
        const baseLineId = String((v as any)?.base_line_id ?? '').trim()
        if (!baseLineId) continue
        const tokens = extractTokensForVariant(v)
        if (!tokens.length) continue
        if (!byBase[baseLineId]) byBase[baseLineId] = new Set<string>()
        for (const t of tokens) byBase[baseLineId].add(String(t))
      }
      const inner: Record<string, string[]> = {}
      for (const [baseLineId, set] of Object.entries(byBase)) {
        inner[baseLineId] = Array.from(set).sort((a, b) => a.localeCompare(b, 'zh-Hans-CN'))
      }
      out[versionId] = inner
    }
    return out
  }, [variantsSummaryQuery.data])

  // NOTE: 旧“映射组(目标模型+变体映射)”已废弃，不再需要按版本提取候选词。

  const structureStandardsQuery = useQuery({
    queryKey: ['bundle-template-center', 'structure-standards'],
    queryFn: () => fetchStructureStandards({ status: 'all', page: 1, page_size: 2000 } as any),
  })

  const structureStandardByCode = useMemo(() => {
    const m = new Map<string, any>()
    const items = (structureStandardsQuery.data?.items ?? []) as any[]
    for (const it of items) {
      const code = String(it?.code ?? it?.name ?? '').trim()
      const k = code.toLowerCase()
      if (k) m.set(k, it)
    }
    return m
  }, [structureStandardsQuery.data])

  const versionStructureCodeQuery = useQuery({
    queryKey: ['bundle-template-center', 'version-structure-code', selectedVersionIds.join(',')],
    queryFn: async () => {
      const modelIds = Array.from(
        new Set(selectedVersionIds.map((vid) => String(versionIdToModelId.get(vid) ?? '').trim()).filter(Boolean)),
      )
      const rows = await Promise.all(
        modelIds.map(async (model_id) => {
          const versions = await fetchProductModelVersions(model_id, { include_archived: true })
          return { model_id, versions }
        }),
      )
      const m: Record<string, string> = {}
      for (const r of rows) {
        const versions = (r.versions ?? []) as any[]
        for (const v of versions) {
          const vid = String(v?.id ?? '').trim()
          if (!vid) continue
          const meta = (v?.metadata_json ?? {}) as any
          const code = String(meta?.structure_standard_code ?? '').trim()
          if (code) m[vid] = code
        }
      }
      return m
    },
    enabled: selectedVersionIds.length > 0 && versionIdToModelId.size > 0,
  })

  const slotDisplayNameByVersionId = useMemo(() => {
    const m = new Map<string, Record<string, string>>()
    const mapping = (versionStructureCodeQuery.data ?? {}) as Record<string, string>
    for (const [vid, code] of Object.entries(mapping)) {
      const std = structureStandardByCode.get(String(code ?? '').trim().toLowerCase())
      const names = (std?.slot_display_names ?? {}) as Record<string, any>
      const out: Record<string, string> = {}
      for (const [k, v] of Object.entries(names ?? {})) {
        const kk = String(k ?? '').trim()
        const vv = String(v ?? '').trim()
        if (kk && vv) out[kk.toLowerCase()] = vv
      }
      if (Object.keys(out).length) m.set(String(vid), out)
    }
    return m
  }, [versionStructureCodeQuery.data, structureStandardByCode])

  const toSlotCn = (slot: string, versionId: string | null): string => {
    const s = String(slot ?? '').trim()
    if (!s) return ''
    // already CN (or user-entered), keep as-is
    if (/[\u4e00-\u9fff]/.test(s)) return s
    const names = versionId ? slotDisplayNameByVersionId.get(String(versionId)) : undefined
    const hit = names ? String(names[s.toLowerCase()] ?? '').trim() : ''
    if (hit) return hit
    const fb = SLOT_CN_FALLBACK[s.toLowerCase()]
    return fb || s
  }

  const versionLinesSummaryQuery = useQuery({
    queryKey: ['bundle-template-center', 'version-lines-summary', selectedVersionIds.join(',')],
    queryFn: async () => {
      const rows = await Promise.all(
        selectedVersionIds.map(async (version_id) => {
          const data = await fetchProductModelVersionLines(version_id)
          return { version_id, data }
        }),
      )
      return rows
    },
    enabled: selectedVersionIds.length > 0,
  })

  const moduleIdsInSelectedVersions = useMemo(() => {
    const rows = (versionLinesSummaryQuery.data ?? []) as Array<{ version_id: string; data: any }>
    const ids = new Set<string>()
    for (const r of rows) {
      const mats = (r?.data?.materials ?? []) as any[]
      for (const it of mats) {
        const meta = (it?.metadata_json ?? it?.metadata ?? {}) as any
        const mid = String(meta?.source_module_id ?? it?.source_module_id ?? '').trim()
        if (mid) ids.add(mid)
      }
    }
    return Array.from(ids)
  }, [versionLinesSummaryQuery.data])

  const moduleMetaByIdQuery = useQuery({
    queryKey: ['bundle-template-center', 'module-meta-by-id', moduleIdsInSelectedVersions.join(',')],
    queryFn: async () => {
      const res = await Promise.all(
        moduleIdsInSelectedVersions.map(async (id) => {
          try {
            const m = await fetchProcessModule(id)
            return [id, m] as const
          } catch {
            return [id, null] as const
          }
        }),
      )
      return new Map<string, any>(res)
    },
    enabled: moduleIdsInSelectedVersions.length > 0,
  })

  const baseLineMapByVersion = useMemo(() => {
    const m = new Map<string, Map<string, any>>()
    const rows = (versionLinesSummaryQuery.data ?? []) as Array<{ version_id: string; data: any }>
    for (const r of rows) {
      const mats = (r?.data?.materials ?? []) as any[]
      const inner = new Map<string, any>()
      for (const it of mats) {
        const id = String(it?.id ?? '').trim()
        if (!id) continue
        inner.set(id, it)
      }
      m.set(String(r.version_id), inner)
    }
    return m
  }, [versionLinesSummaryQuery.data])

  const baseLineInfoByVersionBaseLine = useMemo(() => {
    // version_id -> base_line_id -> { orderIndex, isZeroCost }
    const out: Record<string, Record<string, { orderIndex: number; isZeroCost: boolean }>> = {}
    for (const r of (versionLinesSummaryQuery.data ?? []) as Array<{ version_id: string; data: any }>) {
      const versionId = String((r as any)?.version_id ?? '').trim()
      if (!versionId) continue
      const mats = ((r as any)?.data?.materials ?? []) as any[]
      const inner: Record<string, { orderIndex: number; isZeroCost: boolean }> = {}
      for (let i = 0; i < mats.length; i++) {
        const it = mats[i]
        const id = String(it?.id ?? '').trim()
        if (!id) continue
        const name = String(it?.material_name ?? '').trim()
        const code = String(it?.material_code ?? '').trim()
        const isZeroCost = name.includes('兜底-零成本') || code.includes('兜底-零成本')
        inner[id] = { orderIndex: i, isZeroCost }
      }
      out[versionId] = inner
    }
    return out
  }, [versionLinesSummaryQuery.data])

  const moduleStructureByVersion = useMemo(() => {
    const mapByVersion = new Map<string, Map<string, { whole: boolean; slots: string[] }>>()
    const versionToStd = (versionStructureCodeQuery.data ?? {}) as Record<string, string>
    const moduleMetaById = (moduleMetaByIdQuery.data ?? new Map<string, any>()) as Map<string, any>
    for (const vid of selectedVersionIds) {
      const stdCode = String(versionToStd[String(vid)] ?? '').trim()
      const inner = new Map<string, { whole: boolean; slots: string[] }>()
      if (!stdCode) {
        mapByVersion.set(String(vid), inner)
        continue
      }
      for (const mid of moduleIdsInSelectedVersions) {
        const moduleDetail = moduleMetaById.get(mid)
        const meta: any = (moduleDetail?.metadata_json ?? moduleDetail?.metadata ?? {}) as any
        const tags = Array.isArray(meta?.structure_tags) ? meta.structure_tags.map((x: any) => String(x)) : []
        const whole = tags.includes(stdCode)
        const slots =
          tags.length && stdCode
            ? tags
                .filter((t: string) => t.startsWith(`${stdCode}:`))
                .map((t: string) => String(t.split(':')[1] ?? '').trim())
                .filter(Boolean)
            : []
        inner.set(String(mid), { whole, slots })
      }
      mapByVersion.set(String(vid), inner)
    }
    return mapByVersion
  }, [selectedVersionIds, versionStructureCodeQuery.data, moduleMetaByIdQuery.data, moduleIdsInSelectedVersions])

  const getLineStructureLabel = (line: any, versionId: string | null): string => {
    const meta = (line?.metadata_json ?? line?.metadata ?? {}) as any
    const curSlot = String(meta?.structure_slot ?? '').trim()
    if (curSlot) return toSlotCn(curSlot, versionId)
    const moduleId = String(meta?.source_module_id ?? line?.source_module_id ?? '').trim()
    if (!moduleId || !versionId) return ''
    const info = moduleStructureByVersion.get(String(versionId))?.get(moduleId)
    if (!info) return ''
    if (info.whole) return '整结构'
    if (Array.isArray(info.slots) && info.slots.length === 1) return toSlotCn(info.slots[0], versionId)
    if (Array.isArray(info.slots) && info.slots.length > 1) return toSlotCn(info.slots[0], versionId)
    return ''
  }

  const presetVersionId = useMemo(() => {
    if (!presetModalOpen) return null
    if (!presetModalKey) return null
    const p = phrasePresets[presetModalKey.pIdx]
    const r = (p?.components ?? [])[presetModalKey.cIdx]
    const vid = String(r?.model_version_id ?? '').trim()
    return vid || null
  }, [presetModalOpen, presetModalKey, phrasePresets])

  const lockedPresetApplyMode = useMemo((): 'variant' | 'force' => {
    if (!presetModalOpen || !presetModalKey) return 'variant'
    const p = phrasePresets?.[presetModalKey.pIdx] as any
    const mode = String(p?.mode ?? 'parse').trim()
    // selector 锁模式：
    // - parse(B) => 只能“变体（解析命中）”
    // - force(Z) => 只能“指定（强制命中，不走解析）”
    return mode === 'force' ? 'force' : 'variant'
  }, [presetModalOpen, presetModalKey, phrasePresets])

  useEffect(() => {
    if (!presetModalOpen || !presetModalKey) return
    // 弹窗模式必须由 selector 的 B/Z 模式锁死，避免“弹窗里误切模式”导致失控
    setPresetApplyMode(lockedPresetApplyMode)
  }, [presetModalOpen, presetModalKey, lockedPresetApplyMode])

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
    if (hit && Array.isArray(hit.items)) return hit.items
    return []
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

  const openPresetModal = (pIdx: number, cIdx: number) => {
    const r = (phrasePresets[pIdx]?.components ?? [])[cIdx]
    const vid = String(r?.model_version_id ?? '').trim()
    if (!vid) {
      message.warning('请先选择该组件的模型版本')
      return
    }
    setPresetModalKey({ pIdx, cIdx })
    setPresetModalOpen(true)
  }

  const copyPhrasePreset = (pIdx: number) => {
    const src = phrasePresets[pIdx]
    if (!src) return

    // 口径：复制出来应是“新编码（新 selector）”，但其它内容保持一致，并继承原记录的 B/Z 模式。
    const used = new Set((phrasePresets ?? []).map((x) => String(x?.selector ?? '').trim().toUpperCase()).filter(Boolean))
    const nextSelector = allocateNextSelector2(used)
    const srcMode = String((src as any)?.mode ?? 'parse').trim() === 'force' ? 'force' : 'parse'

    const newIdx = phrasePresets.length
    const copied: PhrasePresetRow = {
      selector: nextSelector,
      mode: srcMode as any,
      phrase: String(src.phrase ?? '').trim() ? `${String(src.phrase ?? '').trim()}（复制）` : '',
      enabled: src.enabled !== false,
      components: Array.isArray(src.components) ? src.components.map((c) => ({ ...c })) : [],
    }
    setPhrasePresets((prev) => [...(prev ?? []), copied])
    // copy selected variants (by component index)
    setPresetSelectedByIdx((prev) => {
      const out: Record<string, Record<string, VariantPresetSelection>> = { ...(prev ?? {}) }
      for (const [k, v] of Object.entries(prev ?? {})) {
        if (!k.startsWith(`${pIdx}:`)) continue
        const cIdxStr = k.split(':')[1]
        const cIdx = Number(cIdxStr)
        if (!Number.isFinite(cIdx)) continue
        out[`${newIdx}:${cIdx}`] = { ...(v ?? {}) }
      }
      return out
    })
    setActivePresetIndex(newIdx)
    message.success(`已复制属性（新编码 ${nextSelector}）`)
  }

  const deletePhrasePreset = (pIdx: number) => {
    const p = phrasePresets?.[pIdx]
    if (!p) return
    const selector = String(p?.selector ?? '').trim().toUpperCase() || toSelector2(pIdx)
    const codeOnly = String(currentBundleToken || '').toUpperCase().replace(/^B:/, '').replace(/^BUNDLE:/, '')
    const tokenDash = codeOnly ? toBundleTokenDash(codeOnly, selector) : selector

    Modal.confirm({
      title: `删除属性 ${selector}？`,
      content: (
        <div>
          <div>删除后不可恢复。</div>
          <div>
            如果线上/订单已经有人在用这个编码（例如 <Text code>{tokenDash}</Text>），删除会导致无法命中；这种情况更建议“停用”该属性。
          </div>
        </div>
      ),
      okText: '删除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: () => {
        setPhrasePresets((prev) => (prev ?? []).filter((_, i) => i !== pIdx))
        // Remap presetSelectedByIdx keys because they are index-based `${pIdx}:${cIdx}`
        setPresetSelectedByIdx((prev) => {
          const out: Record<string, Record<string, VariantPresetSelection>> = {}
          for (const [k, v] of Object.entries(prev ?? {})) {
            const parts = String(k).split(':')
            const pStr = parts[0]
            const cStr = parts[1]
            const pi = Number(pStr)
            const ci = Number(cStr)
            if (!Number.isFinite(pi) || !Number.isFinite(ci)) {
              out[k] = v
              continue
            }
            if (pi === pIdx) continue // drop deleted preset mappings
            const npi = pi > pIdx ? pi - 1 : pi
            out[`${npi}:${ci}`] = v
          }
          return out
        })
        setActivePresetIndex((cur) => {
          if (cur === pIdx) return Math.max(0, cur - 1)
          if (cur > pIdx) return cur - 1
          return cur
        })
      },
    })
  }

  const movePhrasePreset = (fromIdx: number, toIdx: number) => {
    if (fromIdx === toIdx) return
    setPhrasePresets((prev) => {
      const arr = [...(prev ?? [])]
      if (fromIdx < 0 || fromIdx >= arr.length) return arr
      if (toIdx < 0 || toIdx >= arr.length) return arr
      const [it] = arr.splice(fromIdx, 1)
      arr.splice(toIdx, 0, it)
      return arr
    })
    // Remap presetSelectedByIdx keys because they are index-based `${pIdx}:${cIdx}`
    setPresetSelectedByIdx((prev) => {
      const out: Record<string, Record<string, VariantPresetSelection>> = {}
      if (!prev || typeof prev !== 'object') return out
      const keys = Object.entries(prev)
      const mapIdx = (i: number): number => {
        if (i === fromIdx) return toIdx
        if (fromIdx < toIdx) {
          // move down: [from+1..to] shift up by 1
          if (i > fromIdx && i <= toIdx) return i - 1
          return i
        }
        // move up: [to..from-1] shift down by 1
        if (i >= toIdx && i < fromIdx) return i + 1
        return i
      }
      for (const [k, v] of keys) {
        const parts = String(k).split(':')
        const pStr = parts[0]
        const cStr = parts[1]
        const p = Number(pStr)
        const c = Number(cStr)
        if (!Number.isFinite(p) || !Number.isFinite(c)) {
          out[k] = v
          continue
        }
        const np = mapIdx(p)
        out[`${np}:${c}`] = v
      }
      return out
    })
    setActivePresetIndex((cur) => {
      if (cur === fromIdx) return toIdx
      if (fromIdx < toIdx) {
        if (cur > fromIdx && cur <= toIdx) return cur - 1
        return cur
      }
      if (cur >= toIdx && cur < fromIdx) return cur + 1
      return cur
    })
  }

  const validateActivePreset = (): { ok: boolean; reason?: string } => {
    const p = phrasePresets?.[activePresetIndex]
    if (!p) return { ok: false, reason: '请先新建一条属性' }
    if (p?.enabled === false) return { ok: false, reason: '该属性已停用，请先启用再保存' }
    const rows = Array.isArray(p?.components) ? p.components : []
    const valid = rows.filter((c: any) => String(c?.model_version_id ?? '').trim() && Number(c?.width_cm) > 0 && Number(c?.height_cm) > 0 && Number(c?.quantity) > 0)
    if (!valid.length) return { ok: false, reason: '请至少填写 1 条完整组件行（模型/宽/高/数量）' }
    return { ok: true }
  }

  const validateCurrentPreset = () => {
    const pIdx = activePresetIndex
    const p = phrasePresets?.[pIdx]
    if (!p) {
      message.warning('请先选择一个属性')
      return
    }
    const issues: { level: 'error' | 'warn'; message: string }[] = []
    const componentOk: Record<string, boolean> = {}
    const baseLineOk: Record<string, boolean> = {}

    const rows = Array.isArray(p?.components) ? p.components : []
    const presetMode = (String((p as any)?.mode ?? 'parse').trim() === 'force' ? 'force' : 'parse') as 'parse' | 'force'
    for (let cIdx = 0; cIdx < rows.length; cIdx++) {
      const rr = rows[cIdx] as any
      const compKey = `${pIdx}:${cIdx}`
      const versionId = String(rr?.model_version_id ?? '').trim()
      const w = Number(rr?.width_cm ?? 0)
      const h = Number(rr?.height_cm ?? 0)
      const forceMap = (rr?.force_variant_by_base_line ?? {}) as any
      let okThisComp = true

      if (!versionId) {
        okThisComp = false
        issues.push({ level: 'error', message: `组件${cIdx + 1}：未选择模型版本` })
      }
      if (!(w > 0 && h > 0)) {
        okThisComp = false
        issues.push({ level: 'error', message: `组件${cIdx + 1}：尺寸非法（宽/高必须 >0）` })
      }

      const baseMap = baseLineMapByVersion.get(versionId) ?? new Map<string, any>()
      // 兜底“零成本”行：不允许填 TOKEN（避免和真实变体 token 冲突）
      for (const [baseLineId, base] of baseMap.entries()) {
        const rawName = String(base?.material_name ?? base?.material_code ?? '').trim()
        const isZeroCostFallback = rawName.includes('兜底-零成本')
        const overrideKey = `${versionId}:${String(baseLineId)}`
        const alias = String(fallbackTokenOverrides?.[overrideKey] ?? '').trim()
        const key = `${pIdx}:${cIdx}:${baseLineId}`
        if (isZeroCostFallback && alias) {
          okThisComp = false
          baseLineOk[key] = false
          issues.push({
            level: 'error',
            message: `组件${cIdx + 1}：兜底物料「${rawName}」不应配置 TOKEN（当前=${alias}），否则易与真实变体冲突`,
          })
        } else {
          baseLineOk[key] = true
        }
      }

      // 已选变体规则是否仍存在（防止你说的“改完变体，这里不更新导致失效”）
      const sel = (presetSelectedByIdx?.[compKey] ?? {}) as Record<string, VariantPresetSelection>
      const variantsForVersion = ((variantsSummaryQuery.data ?? []) as any[]).find((x: any) => String(x?.version_id ?? '') === versionId)
        ?.items as any[]
      const variants = Array.isArray(variantsForVersion) ? variantsForVersion : []
      const variantsById = new Map<string, any>()
      for (const v of variants) if (v?.id) variantsById.set(String(v.id), v)

      const injectedFromSpec = String(rr?.spec_text ?? '')
        .split(/[，,、\n\r\t ]+/g)
        .map((x) => String(x).trim())
        .filter(Boolean)
      const injectedFromTokens = Array.isArray(rr?.tokens) ? (rr.tokens as any[]).map((x) => String(x).trim()).filter(Boolean) : []
      // “触发词（参与匹配）”：来自组件行 spec_text/tokens（会被后端解析并注入 component.tokens）
      const injectedAll = new Set<string>([...injectedFromSpec, ...injectedFromTokens])
      const forceMapForComp =
        rr?.force_variant_by_base_line && typeof rr.force_variant_by_base_line === 'object' ? (rr.force_variant_by_base_line as any) : {}
      const hasForce = Object.keys(forceMapForComp ?? {}).length > 0

      // --- 制度化约束：一个 selector 只能一种模式 ---
      // parse(B)：禁止出现强制映射
      if (presetMode === 'parse' && hasForce) {
        okThisComp = false
        issues.push({ level: 'error', message: `组件${cIdx + 1}：当前短语为解析型（B），不允许配置“指定(强制)”映射（请切换为 Z 模式或清理强制映射）` })
      }

      for (const [baseLineId, s] of Object.entries(sel)) {
        const parentId = String(s?.parent_variant_id ?? '').trim()
        if (!parentId) continue
        const parent = variantsById.get(parentId)
        const base = baseMap.get(String(baseLineId))
        const baseName = String(base?.material_name ?? base?.material_code ?? baseLineId).trim()
        const baseKey = `${pIdx}:${cIdx}:${baseLineId}`

        if (!parent) {
          okThisComp = false
          baseLineOk[baseKey] = false
          issues.push({ level: 'error', message: `组件${cIdx + 1}：物料行「${baseName}」所选一级规则已不存在/已变更（请重新筛选）` })
          continue
        }

        // 强制模式：若一级含二级，必须能定位到 1 条子条件
        const children = variants.filter((x: any) => String(x?.metadata?.parent_variant_id ?? '').trim() === parentId)
        const hasChild = children.length > 0
        const forcedChildId = String(s?.forced_child_variant_id ?? '').trim()
        if (hasForce && hasChild && !forcedChildId) {
          okThisComp = false
          baseLineOk[baseKey] = false
          issues.push({ level: 'error', message: `组件${cIdx + 1}：物料行「${baseName}」强制模式下必须选择 1 条子条件` })
          continue
        }

        // 强制映射存在性（前端已写入 rr.force_variant_by_base_line；这里再确认）
        if (hasForce) {
          const forcedVariantId = String(forceMap?.[String(baseLineId)] ?? '').trim()
          if (!forcedVariantId) {
            okThisComp = false
            baseLineOk[baseKey] = false
            issues.push({ level: 'error', message: `组件${cIdx + 1}：物料行「${baseName}」缺少强制映射（请重新筛选/保存）` })
            continue
          }
          if (!variantsById.get(forcedVariantId)) {
            okThisComp = false
            baseLineOk[baseKey] = false
            issues.push({ level: 'error', message: `组件${cIdx + 1}：物料行「${baseName}」强制规则已不存在/已变更（请重新筛选）` })
            continue
          }
        }
      }

      // Z 模式：必须强制覆盖所有“依赖触发词”的行（无需“关键行”概念/手动维护）
      if (presetMode === 'force' && versionId) {
        // 该版本中所有“依赖触发词”的 base_line_id 集合
        const tokenDepBaseLineIds = new Set<string>()
        for (const v of variants) {
          const baseId = String(v?.base_line_id ?? '').trim()
          if (!baseId) continue
          const cond = (v?.conditions ?? {}) as any
          const anyTokens = Array.isArray(cond?.spec_contains_any) ? cond.spec_contains_any : []
          const allTokens = Array.isArray(cond?.spec_contains_all) ? cond.spec_contains_all : []
          const hasTokenCond = [...anyTokens, ...allTokens].some((x) => {
            const s = String(x ?? '').trim()
            if (!s) return false
            const up = s.toUpperCase()
            if (up.startsWith('MODEL:') || up.startsWith('M:') || up.startsWith('BOUND_VERSION:') || up.startsWith('SKU:')) return false
            return true
          })
          if (hasTokenCond) tokenDepBaseLineIds.add(baseId)
        }

        for (const baseLineId of tokenDepBaseLineIds) {
          const base = baseMap.get(String(baseLineId))
          const baseName = String(base?.material_name ?? base?.material_code ?? baseLineId).trim()
          const forcedVariantId = String(forceMapForComp?.[String(baseLineId)] ?? '').trim()
          if (!forcedVariantId) {
            okThisComp = false
            issues.push({ level: 'error', message: `组件${cIdx + 1}：Z 模式下「${baseName}」依赖触发词但未强制指定（请在“筛选”里选中对应规则并保存）` })
            continue
          }
          const vv = variantsById.get(forcedVariantId)
          if (!vv) {
            okThisComp = false
            issues.push({ level: 'error', message: `组件${cIdx + 1}：Z 模式下「${baseName}」强制规则已不存在/已变更（请重新筛选）` })
            continue
          }
          if (vv?.enabled === false) {
            okThisComp = false
            issues.push({ level: 'error', message: `组件${cIdx + 1}：Z 模式下「${baseName}」强制规则已禁用（不允许）` })
            continue
          }
        }
      }

      // 风险提示：若该版本存在依赖 TOKEN 的变体规则，但当前组件未写入触发词且也未强制指定，则可能仍需要运营在规格里写词
      if (!hasForce && injectedAll.size === 0) {
        const tokenVariants = variants.filter((v: any) => {
          const cond = (v?.conditions ?? {}) as any
          const anyTokens = Array.isArray(cond?.spec_contains_any) ? cond.spec_contains_any : []
          const allTokens = Array.isArray(cond?.spec_contains_all) ? cond.spec_contains_all : []
          return [...anyTokens, ...allTokens].some((x) => {
            const s = String(x ?? '').trim()
            if (!s) return false
            const up = s.toUpperCase()
            if (up.startsWith('MODEL:') || up.startsWith('M:') || up.startsWith('BOUND_VERSION:') || up.startsWith('SKU:')) return false
            return true
          })
        })
        if (tokenVariants.length) {
          const sampleTokens = new Set<string>()
          for (const v of tokenVariants.slice(0, 6)) {
            for (const t of extractTokensForVariant(v)) {
              const s = String(t).trim()
              if (!s) continue
              sampleTokens.add(s.includes(':') ? String(s.split(':', 2)[1] ?? s).trim() || s : s)
            }
          }
          issues.push({
            level: 'warn',
            message: `组件${cIdx + 1}：该版本存在需要触发词的变体规则（例如：${Array.from(sampleTokens).slice(0, 4).join('、') || '材质类词'}）。当前未写入触发词且未强制指定，可能仍依赖运营在规格里写词（不推荐）。`,
          })
        }
      }

      componentOk[compKey] = okThisComp
    }

    const hasError = issues.some((x) => x.level === 'error')
    setPresetValidation({
      presetIndex: pIdx,
      checkedAt: Date.now(),
      ok: !hasError,
      issues,
      componentOk,
      baseLineOk,
    })
    message.success(hasError ? '检验完成：存在问题（红色）' : '检验通过（绿色）')
  }

  const cleanupInvalidSelectionsForPreset = (pIdx: number) => {
    const p = phrasePresets?.[pIdx]
    if (!p) return
    const rows = Array.isArray((p as any)?.components) ? ((p as any).components as any[]) : []

    // Build variantsById per version from current query cache (best-effort, no extra request)
    const variantsByVersionId = new Map<string, Map<string, any>>()
    for (const x of (variantsSummaryQuery.data ?? []) as any[]) {
      const vid = String((x as any)?.version_id ?? '').trim()
      if (!vid) continue
      const items = Array.isArray((x as any)?.items) ? (x as any).items : []
      const m = new Map<string, any>()
      for (const v of items) if (v?.id) m.set(String(v.id), v)
      variantsByVersionId.set(vid, m)
    }

    // 1) 清理 presetSelectedByIdx 中失效的 parent/forced 规则
    setPresetSelectedByIdx((prev) => {
      const out = { ...(prev ?? {}) } as Record<string, Record<string, VariantPresetSelection>>
      for (let cIdx = 0; cIdx < rows.length; cIdx++) {
        const compKey = `${pIdx}:${cIdx}`
        const rr = rows[cIdx]
        const versionId = String(rr?.model_version_id ?? '').trim()
        const vb = variantsByVersionId.get(versionId) ?? new Map<string, any>()
        const sel = (out[compKey] ?? {}) as Record<string, VariantPresetSelection>
        const nextSel: Record<string, VariantPresetSelection> = {}
        let changed = false
        for (const [baseLineId, s] of Object.entries(sel)) {
          const parentId = String(s?.parent_variant_id ?? '').trim()
          if (parentId && !vb.get(parentId)) {
            changed = true
            continue
          }
          const forcedChildId = String(s?.forced_child_variant_id ?? '').trim()
          if (forcedChildId && !vb.get(forcedChildId)) {
            changed = true
            nextSel[baseLineId] = { ...(s as any), forced_child_variant_id: null }
            continue
          }
          nextSel[baseLineId] = s
        }
        if (changed) out[compKey] = nextSel
      }
      return out
    })

    // 2) 清理组件行 force_variant_by_base_line 中失效的 variant_id
    setPhrasePresets((prev) =>
      (prev ?? []).map((pp, pi) => {
        if (pi !== pIdx) return pp
        const nextComponents = (rows ?? []).map((rr) => {
          const versionId = String(rr?.model_version_id ?? '').trim()
          const vb = variantsByVersionId.get(versionId) ?? new Map<string, any>()
          const fm = rr?.force_variant_by_base_line && typeof rr.force_variant_by_base_line === 'object' ? rr.force_variant_by_base_line : {}
          if (!fm || typeof fm !== 'object') return rr
          let changed = false
          const nextFm: Record<string, string> = {}
          for (const [baseLineId, variantId] of Object.entries(fm as any)) {
            const vid = String(variantId ?? '').trim()
            if (!vid) continue
            if (!vb.get(vid)) {
              changed = true
              continue
            }
            nextFm[String(baseLineId)] = vid
          }
          return changed ? { ...rr, force_variant_by_base_line: Object.keys(nextFm).length ? nextFm : undefined } : rr
        })
        return { ...pp, components: nextComponents }
      }),
    )

    message.success('已清理失效规则（请重新点“检验结果”确认）')
  }

  // NOTE: auto phrase builder removed (it was too visually noisy); keep UI structured with locked tokens + editable fallback names.

  const copyComponentRow = (pIdx: number, cIdx: number) => {
    const src = (phrasePresets[pIdx]?.components ?? [])[cIdx]
    if (!src) return
    setPhrasePresets((prev) =>
      (prev ?? []).map((pp, pi) => {
        if (pi !== pIdx) return pp
        const rows = Array.isArray(pp.components) ? pp.components : []
        const nextRows = rows.slice()
        nextRows.splice(cIdx + 1, 0, { ...src })
        return { ...pp, components: nextRows }
      }),
    )
    // shift selections for this preset (index-based keys), and clone selections for the copied row
    setPresetSelectedByIdx((prev) => {
      const out: Record<string, Record<string, VariantPresetSelection>> = {}
      const prefix = `${pIdx}:`
      for (const [k, v] of Object.entries(prev ?? {})) {
        if (!k.startsWith(prefix)) {
          out[k] = v
          continue
        }
        const cIdxStr = k.slice(prefix.length)
        const oldC = Number(cIdxStr)
        if (!Number.isFinite(oldC)) {
          out[k] = v
          continue
        }
        if (oldC <= cIdx) {
          out[`${pIdx}:${oldC}`] = v
          continue
        }
        out[`${pIdx}:${oldC + 1}`] = v
      }
      const srcKey = `${pIdx}:${cIdx}`
      if ((prev ?? {})[srcKey]) {
        out[`${pIdx}:${cIdx + 1}`] = { ...((prev ?? {})[srcKey] ?? {}) }
      }
      return out
    })
  }

  const deleteComponentRow = (pIdx: number, cIdx: number) => {
    setPhrasePresets((prev) =>
      (prev ?? []).map((pp, pi) => (pi !== pIdx ? pp : { ...pp, components: (pp.components ?? []).filter((_, j) => j !== cIdx) })),
    )
    // shift selections down to avoid "selected variants" misalignment
    setPresetSelectedByIdx((prev) => {
      const out: Record<string, Record<string, VariantPresetSelection>> = {}
      const prefix = `${pIdx}:`
      for (const [k, v] of Object.entries(prev ?? {})) {
        if (!k.startsWith(prefix)) {
          out[k] = v
          continue
        }
        const cIdxStr = k.slice(prefix.length)
        const oldC = Number(cIdxStr)
        if (!Number.isFinite(oldC)) continue
        if (oldC < cIdx) out[`${pIdx}:${oldC}`] = v
        else if (oldC > cIdx) out[`${pIdx}:${oldC - 1}`] = v
        // oldC === cIdx => drop
      }
      return out
    })
  }

  const applyPresetToComponent = () => {
    if (!presetModalKey) return
    const k = `${presetModalKey.pIdx}:${presetModalKey.cIdx}`
    const selectedMap = presetSelectedByIdx[k] ?? {}
    const tokenSet = new Set<string>()
    if (presetApplyMode === 'force') {
      // 强制模式：如果某个一级含二级，则必须明确选中 1 条子条件（否则无法“强制到某个条件”）
      for (const [baseLineId, sel] of Object.entries(selectedMap)) {
        const parentId = String(sel?.parent_variant_id ?? '').trim()
        if (!parentId) continue
        const variants = presetVariantsByBaseLine.get(baseLineId) ?? []
        const children = variants.filter((x: any) => String(x?.metadata?.parent_variant_id ?? '').trim() === parentId)
        const hasChild = children.length > 0
        const forcedChildId = String(sel?.forced_child_variant_id ?? '').trim()
        if (hasChild && !forcedChildId) {
          message.error('强制模式：一级含二级时必须选择 1 条子条件（请在弹窗里选择子条件）')
          return
        }
      }
    }
    for (const [baseLineId, sel] of Object.entries(selectedMap)) {
      const parentId = String(sel?.parent_variant_id ?? '').trim()
      if (!parentId) continue
      const variants = presetVariantsByBaseLine.get(baseLineId) ?? []
      // “变体（解析命中）”：选一级即可（tokens 从一级拿，二级由尺寸/指标决定）
      // “指定（强制命中）”：若一级有二级，必须选一个子条件；否则就用一级本身
      const forcedChildId = String(sel?.forced_child_variant_id ?? '').trim()
      let pickId = parentId
      if (presetApplyMode === 'force') {
        if (forcedChildId) {
          pickId = forcedChildId
        } else {
          const children = variants.filter((x: any) => String(x?.metadata?.parent_variant_id ?? '').trim() === parentId)
          const firstChildId = String(children?.[0]?.id ?? '').trim()
          pickId = firstChildId || parentId
        }
      }
      const v = variants.find((x: any) => String(x?.id) === String(pickId))
      if (!v) continue
      // Normalize tokens:
      // - keep original token (e.g. 材质:雪尼尔)
      // - also add value-only token (e.g. 雪尼尔) to reduce coupling to tokenizer/legacy rules
      for (const t of extractTokensForVariant(v)) {
        const s = String(t ?? '').trim()
        if (!s) continue
        tokenSet.add(s)
        if (s.includes(':')) {
          const vOnly = String(s.split(':', 2)[1] ?? '').trim()
          if (vOnly) tokenSet.add(vOnly)
        }
      }
    }
    const tokens = Array.from(tokenSet)
    const nextText = tokens.join('，')
    const forceVariantByBaseLine: Record<string, string> = {}
    if (presetApplyMode === 'force') {
      for (const [baseLineId, sel] of Object.entries(selectedMap)) {
        const parentId = String(sel?.parent_variant_id ?? '').trim()
        if (!parentId) continue
        const forcedChildId = String(sel?.forced_child_variant_id ?? '').trim()
        forceVariantByBaseLine[String(baseLineId)] = forcedChildId || parentId
      }
    }
    setPhrasePresets((prev) =>
      prev.map((pp, pi) =>
        pi !== presetModalKey.pIdx
          ? pp
          : {
              ...pp,
              components: (pp.components ?? []).map((cc, ci) => {
                if (ci !== presetModalKey.cIdx) return cc
                // 变体：填充 spec_text（需要交易规格解析命中）
                // 指定：注入 tokens（不依赖交易规格解析，直接强制命中）
                if (presetApplyMode === 'force') {
                  return { ...cc, spec_text: '', tokens, force_variant_by_base_line: forceVariantByBaseLine }
                }
                return { ...cc, spec_text: nextText, tokens: [], force_variant_by_base_line: undefined }
              }),
            },
      ),
    )
    if (presetApplyMode === 'force') {
      message.success(
        tokens.length
          ? `已指定（强制命中）：${tokens.join('、')}（写入模板组件，运营无需在规格中输入）`
          : '所选规则不包含 TOKEN，无法通过“指定(强制)”实现（请改为变体解析或补 TOKEN 条件）',
      )
    } else {
      message.success(
        tokens.length
          ? `已填充触发词：${tokens.join('、')}（写入模板组件，运营无需在规格中输入）`
          : '所选变体不依赖 TOKEN 触发词（仅尺寸/面积/周长条件等）',
      )
    }
    setPresetModalOpen(false)
  }

  // NOTE: “字段映射”的“词”已收口为严格候选选择，不再提供“命中/预演”按钮。

  const openCreate = () => {
    setEditing(null)
    setCreatedTokenHint(null)
    form.setFieldsValue({ name: '', category: '', tags: [], shared_trigger_text: '' })
    setModelPoolVersionIds([])
    setPresetSelectedByIdx({})
    setPhrasePresets([])
    setFallbackTokenOverrides({})
    setAttributeGroupSelections({})
    setComponentOrderByPreset({})
    setGroupOrderByPresetComponent({})
    setActivePresetIndex(0)
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
      shared_trigger_text: String(meta?.shared_trigger_text ?? row?.shared_trigger_text ?? '') || '',
    })
    const pool = (meta?.model_pool_version_ids ?? meta?.model_pool ?? meta?.model_versions) as any
    setModelPoolVersionIds(Array.isArray(pool) ? pool.map((x) => String(x)).filter(Boolean) : [])
    const vp = (row?.metadata ?? {})?.phrase_variant_presets
    if (vp && typeof vp === 'object') {
      // Backward compatibility:
      // - legacy: { [k]: { [base_line_id]: variant_id|null } }
      // - new:    { [k]: { [base_line_id]: { parent_variant_id, child_variant_ids?, forced_child_variant_id? } } }
      const out: Record<string, Record<string, VariantPresetSelection>> = {}
      for (const [k, m] of Object.entries(vp as any)) {
        if (!m || typeof m !== 'object') continue
        const inner: Record<string, VariantPresetSelection> = {}
        for (const [baseLineId, rawSel] of Object.entries(m as any)) {
          if (!baseLineId) continue
          if (rawSel && typeof rawSel === 'object' && 'parent_variant_id' in (rawSel as any)) {
            inner[String(baseLineId)] = rawSel as any
            continue
          }
          // legacy string/null
          const vid = String(rawSel ?? '').trim()
          inner[String(baseLineId)] = { parent_variant_id: vid || null }
        }
        out[String(k)] = inner
      }
      setPresetSelectedByIdx(out)
    } else {
      setPresetSelectedByIdx({})
    }

    const fo = (row?.metadata ?? {})?.fallback_token_overrides ?? (row?.metadata ?? {})?.fallback_display_overrides
    if (fo && typeof fo === 'object') setFallbackTokenOverrides(fo as any)
    else setFallbackTokenOverrides({})
    setAttributeGroupSelections({})
    setComponentOrderByPreset({})
    setGroupOrderByPresetComponent({})
    // NOTE: legacy metadata.lexicon_rules is preserved on save, but UI is intentionally hidden to avoid confusion.

    const pp = (row?.metadata ?? {})?.phrase_presets
    if (Array.isArray(pp)) {
      setPhrasePresets(
        pp
          .map((x: any) => ({
            selector: String(x?.selector ?? '').trim().toUpperCase() || undefined,
            enabled: x?.enabled === false ? false : true,
            phrase: String(x?.phrase ?? '').trim(),
            mode: String(x?.mode ?? '').trim() === 'force' ? 'force' : 'parse',
            components: Array.isArray(x?.components)
              ? (x.components as any[])
                  .map((c: any) => ({
                    model_version_id: String(c?.model_version_id ?? '').trim() || null,
                    width_cm: Number(c?.width_mm ?? 0) / 10,
                    height_cm: Number(c?.height_mm ?? 0) / 10,
                    quantity: Number(c?.quantity ?? 1),
                    spec_text: String(c?.spec_text ?? ''),
                    tokens: Array.isArray(c?.tokens) ? c.tokens.map((x: any) => String(x)).filter(Boolean) : [],
                    force_variant_by_base_line:
                      c?.force_variant_by_base_line && typeof c.force_variant_by_base_line === 'object' ? c.force_variant_by_base_line : undefined,
                  }))
                  .filter((c: any) => !!c.model_version_id)
              : [],
          }))
          .map((x: any, idx: number) => ({
            ...x,
            selector: String(x?.selector ?? '').trim().toUpperCase() || toSelector2(idx),
          }))
          // keep disabled rows; enabled rows can be empty when user is still editing
          .filter((x: any) => !!String(x?.selector ?? '').trim()),
      )
    } else {
      setPhrasePresets([])
    }
    setActivePresetIndex(0)

    // Migration: if old template has top-level components but no preset components, map them to preset A.
    const topRows = (row?.components ?? []) as any[]
    if ((!Array.isArray(pp) || !pp.length) && Array.isArray(topRows) && topRows.length) {
      const converted = topRows
        .map((c: any) => ({
          model_version_id: String(c.model_version_id ?? '').trim() || null,
          width_cm: Number(c.width_mm ?? 0) / 10,
          height_cm: Number(c.height_mm ?? 0) / 10,
          quantity: Number(c.quantity ?? 1),
          spec_text: String(c.spec_text ?? ''),
        }))
        .filter((c: any) => !!c.model_version_id)
      if (converted.length) {
        setPhrasePresets([{ selector: 'AA', phrase: 'A组', components: converted, enabled: true }])
        // seed pool with those versions if pool empty
        if (!Array.isArray(pool) || !pool.length) {
          setModelPoolVersionIds(Array.from(new Set(converted.map((x: any) => String(x.model_version_id)))))
        }
      }
    }
    setDrawerOpen(true)
  }

  useEffect(() => {
    const len = (phrasePresets ?? []).length
    if (len <= 0) {
      if (activePresetIndex !== 0) setActivePresetIndex(0)
      return
    }
    if (activePresetIndex < 0) setActivePresetIndex(0)
    else if (activePresetIndex >= len) setActivePresetIndex(len - 1)
  }, [activePresetIndex, phrasePresets])

  const activePresetAttributeBuilt = useMemo(() => {
    const p = phrasePresets?.[activePresetIndex] as any
    if (!p) return null
    if (String(p?.mode ?? 'parse') === 'force') return null
    const rows = Array.isArray(p?.components) ? (p.components as any[]) : []
    const orderKey = String(activePresetIndex)
    const componentOrder = componentOrderByPreset?.[orderKey]
    return buildAttributeFormulaAndGroups({
      presetIndex: activePresetIndex,
      componentOrder,
      componentRows: rows,
      presetSelectedByIdx,
      fallbackTokenOverrides,
      variantTokenOptionsByVersionBaseLine,
      baseLineInfoByVersionBaseLine,
    })
  }, [
    activePresetIndex,
    phrasePresets,
    presetSelectedByIdx,
    fallbackTokenOverrides,
    variantTokenOptionsByVersionBaseLine,
    baseLineInfoByVersionBaseLine,
    componentOrderByPreset,
  ])

  useEffect(() => {
    // 解析型：若属性名称/公式为空，则自动写入生成的属性公式（可手改，不会覆盖已有内容）
    const built = activePresetAttributeBuilt
    if (!built?.formula) return
    const p = phrasePresets?.[activePresetIndex] as any
    if (!p) return
    if (String(p?.mode ?? 'parse') === 'force') return
    if (String(p?.phrase ?? '').trim()) return
    setPhrasePresets((prev) => (prev ?? []).map((x, i) => (i === activePresetIndex ? { ...x, phrase: built.formula } : x)))
  }, [activePresetAttributeBuilt, activePresetIndex, phrasePresets])

  const addPhrasePreset = () => {
    setPhrasePresets((prev) => {
      const used = new Set((prev ?? []).map((x: any) => String(x?.selector ?? '').trim().toUpperCase()).filter(Boolean))
      const next = [
        ...(prev ?? []),
        {
          selector: allocateNextSelector2(used),
          phrase: '',
          // 新建默认停用，避免“未填完就阻塞保存/误上线上线”
          enabled: false,
          // 默认：指定型（Z），符合运营心智：默认“不走解析”
          mode: 'force',
          components: [{ model_version_id: null, width_cm: 40, height_cm: 50, quantity: 1, spec_text: '', tokens: [] }],
        } as PhrasePresetRow,
      ]
      setActivePresetIndex(next.length - 1)
      return next
    })
  }

  const saveMutation = useMutation({
    mutationFn: async () => {
      const values = await form.validateFields()
      const comps: any[] = []

      const meta = {
        ...(editing?.metadata ?? {}),
        category: String(values.category ?? '').trim() || undefined,
        tags: Array.isArray(values.tags) ? values.tags.map((x: any) => String(x)).filter(Boolean) : [],
        shared_trigger_text: String(values.shared_trigger_text ?? '').trim() || undefined,
        model_pool_version_ids: modelPoolVersionIds,
        phrase_variant_presets: presetSelectedByIdx,
        fallback_token_overrides: fallbackTokenOverrides,
        // keep legacy field for older clients
        fallback_display_overrides: fallbackTokenOverrides,
        // Preserve legacy lexicon_rules (global fallback mapping) if exists, but do not expose to operators.
        lexicon_rules: Array.isArray((editing?.metadata ?? {})?.lexicon_rules) ? (editing?.metadata ?? {})?.lexicon_rules : [],
        phrase_presets: phrasePresets
          .map((p) => ({
            selector: String((p as any).selector ?? '').trim().toUpperCase() || undefined,
            enabled: (p as any).enabled === false ? false : undefined,
            phrase: String((p as any).phrase ?? '').trim(),
            mode: String((p as any).mode ?? '').trim() === 'force' ? 'force' : 'parse',
            components: Array.isArray(p.components)
              ? p.components
                  .map((c) => ({
                    model_version_id: String(c.model_version_id ?? '').trim(),
                    width_mm: Number(c.width_cm) * 10,
                    height_mm: Number(c.height_cm) * 10,
                    quantity: Number(c.quantity),
                    spec_text: String(c.spec_text || '').trim() || undefined,
                    tokens: Array.isArray((c as any).tokens)
                      ? ((c as any).tokens as any[]).map((x) => String(x)).filter(Boolean)
                      : undefined,
                    force_variant_by_base_line:
                      c.force_variant_by_base_line && typeof c.force_variant_by_base_line === 'object'
                        ? c.force_variant_by_base_line
                        : undefined,
                  }))
                  .filter((c) => c.model_version_id && c.width_mm > 0 && c.height_mm > 0 && c.quantity > 0)
              : [],
          }))
          // Keep disabled rows (by selector) even if they are empty, to avoid selector reuse/shift.
          // Enabled rows must have phrase + component rows.
          .filter((p: any) => {
            const sel = String(p?.selector ?? '').trim()
            const enabled = p?.enabled !== false
            if (!enabled) return !!sel
            return Array.isArray(p.components) && p.components.length > 0
          }),
      }
      if (editing?.id) {
        return await updateBundleTemplate(editing.id, {
          name: String(values.name ?? '').trim() || undefined,
          components: comps as any,
          metadata: meta,
        })
      }
      return await createBundleTemplate({
        name: String(values.name ?? '').trim() || undefined,
        components: comps as any,
        metadata: meta,
      })
    },
    onSuccess: (res: any) => {
      qc.invalidateQueries({ queryKey: ['bundle-templates'] })
      const code = String(res?.code ?? '').toUpperCase()
      // Default hint uses new short external token, preset AA: B-XXXXAA
      if (code) setCreatedTokenHint(toBundleTokenDash(code, 'AA'))
      message.success(editing?.id ? '已保存' : '已创建')
      setEditing(res)
    },
    onError: (e: any) => message.error(String(e?.message ?? e)),
  })

  const validateAllEnabledPresetsBeforeSave = (): { ok: boolean; issues: { level: 'error' | 'warn'; message: string }[] } => {
    const issues: { level: 'error' | 'warn'; message: string }[] = []
    const presets = phrasePresets ?? []
    const enabledSelectorCounts = new Map<string, number>()
    for (let pIdx = 0; pIdx < presets.length; pIdx++) {
      const p = presets[pIdx] as any
      const selector = String(p?.selector ?? '').trim().toUpperCase() || `#${pIdx + 1}`
      if (p?.enabled === false) continue
      enabledSelectorCounts.set(selector, (enabledSelectorCounts.get(selector) ?? 0) + 1)
      const rows = Array.isArray(p?.components) ? p.components : []
      const valid = rows.filter((c: any) => String(c?.model_version_id ?? '').trim() && Number(c?.width_cm) > 0 && Number(c?.height_cm) > 0 && Number(c?.quantity) > 0)
      if (!String(p?.phrase ?? '').trim()) {
        issues.push({ level: 'error', message: `属性 ${selector}：属性备注不能为空（用于识别/管理；若暂不使用请在左侧停用该属性）` })
      }
      if (!valid.length) {
        issues.push({
          level: 'error',
          message: `属性 ${selector}：已启用但未配置完整组件行（模型/宽/高/数量）；请补齐至少1行或在左侧停用该属性`,
        })
      }
    }
    for (const [sel, cnt] of enabledSelectorCounts.entries()) {
      if (cnt <= 1) continue
      issues.push({ level: 'error', message: `属性 ${sel}：存在 ${cnt} 条“启用”的同编码属性（会导致命中歧义）；请确保同一编码仅启用 1 条` })
    }
    const hasError = issues.some((x) => x.level === 'error')
    return { ok: !hasError, issues }
  }

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

  const filteredItems = useMemo(() => {
    const q = String(search ?? '').trim().toLowerCase()
    if (!q) return items
    return items.filter((r: any) => {
      const code = String(r?.code ?? '').trim().toLowerCase()
      const name = String(r?.name ?? '').trim().toLowerCase()
      if (code.includes(q) || name.includes(q)) return true
      const meta = r?.metadata ?? {}
      const pp = Array.isArray(meta?.phrase_presets) ? meta.phrase_presets : []
      for (const p of pp) {
        const phrase = String(p?.phrase ?? '').trim().toLowerCase()
        if (phrase && phrase.includes(q)) return true
      }
      return false
    })
  }, [items, search])

  return (
    <div style={{ padding: 16 }}>
      <Drawer
        open={bundlePreviewOpen}
        onClose={() => setBundlePreviewOpen(false)}
        width={980}
        destroyOnClose
        title="套装预演结果（debug）"
      >
        <Space direction="vertical" style={{ width: '100%' }} size={10}>
          <Alert
            type="info"
            showIcon
            message="说明：该预演直接调用后端 /bom/generate-by-spec-debug，可用于验证“短码/selector/强制命中”是否稳定。"
            description="建议：对关键套装模板，在修改变体规则或短语预设后先预演；若出现 forced_by_bundle 相关报错，说明强制规则已失效，需要重新筛选/保存。"
          />
          <Card size="small" title="本次预演输入（spec_text）">
            <pre style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{bundlePreviewSpecText || '-'}</pre>
          </Card>
          <Card size="small" title="预演输出（JSON）">
            <pre style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{JSON.stringify(bundlePreviewData ?? {}, null, 2)}</pre>
          </Card>
        </Space>
      </Drawer>
      <Modal
        open={presetModalOpen}
        title="预设变体筛选（按物料行选择变体规则 → 一键填充触发词）"
        width={980}
        onCancel={() => setPresetModalOpen(false)}
        onOk={applyPresetToComponent}
        okText={lockedPresetApplyMode === 'force' ? '按勾选强制指定' : '按勾选填充触发词'}
        destroyOnClose
      >
        {!presetVersionId ? (
          <Empty description="请先选择组件的模型版本" />
        ) : presetVariantsForVersion.length === 0 ? (
          <Empty description="该版本没有行级变体规则" />
        ) : (
          <Space direction="vertical" style={{ width: '100%' }} size={12}>
            <Space wrap size={10} style={{ width: '100%', justifyContent: 'space-between' }}>
              <Space wrap size={8}>
                <Text type="secondary">模式：</Text>
                <Radio.Group
                  value={lockedPresetApplyMode}
                  disabled
                  optionType="button"
                  buttonStyle="solid"
                >
                  <Radio.Button value="variant">变体（解析命中）</Radio.Button>
                  <Radio.Button value="force">指定（强制命中，不走解析）</Radio.Button>
                </Radio.Group>
                <Text type="secondary">
                  （已锁定：{lockedPresetApplyMode === 'force' ? 'Z 指定型' : 'B 解析型'}，弹窗内不可切换）
                </Text>
              </Space>
              <Text type="secondary">提示：最终命中仍受 priority + stop_on_hit 影响，建议用测试台预演确认</Text>
            </Space>

            <Collapse
              items={Array.from(presetVariantsByBaseLine.entries()).map(([baseLineId, arr]) => {
                const base = presetBaseLineMap.get(baseLineId)
                const selKey = presetModalKey ? `${presetModalKey.pIdx}:${presetModalKey.cIdx}` : ''
                const selected = (selKey ? (presetSelectedByIdx[selKey] ?? {}) : {})[baseLineId] ?? null
                const slot = getLineStructureLabel(base, presetVersionId)
                const baseLabelRaw = String(base?.material_name ?? base?.material_code ?? baseLineId).trim()
                const baseLabel = slot ? `${slot}：${baseLabelRaw}` : baseLabelRaw

                const selectedParentId = String(selected?.parent_variant_id ?? '').trim()
                const selectedVariant = selectedParentId ? (arr ?? []).find((x: any) => String(x?.id) === selectedParentId) : null
                const childRows = selectedParentId
                  ? (arr ?? []).filter((x: any) => String(x?.metadata?.parent_variant_id ?? '').trim() === selectedParentId)
                  : []
                const selectedProduced = Array.isArray(selectedVariant?.items) ? selectedVariant.items : []
                const selectedProducedLabels: string[] = selectedProduced
                  .map((it: any) => String(it?.material_name ?? it?.material_code ?? '').trim())
                  .filter(Boolean)
                  .slice(0, 2)
                const selectedEffect =
                  selectedVariant?.action === 'remove_self'
                    ? '移除'
                    : selectedVariant?.action === 'add_siblings'
                      ? '新增物料'
                      : '替换物料'

                return {
                  key: baseLineId,
                  label: (
                    <Space size={8}>
                      <Text strong>{baseLabel}</Text>
                      <Text type="secondary">{arr.length}条规则</Text>
                      {selectedParentId ? (
                        <Space size={6}>
                          <Text type="secondary">{selectedEffect}</Text>
                          {selectedProducedLabels.length && childRows.length === 0 ? (
                            <Tag color="green">{selectedProducedLabels.join('、')}</Tag>
                          ) : (
                            <Tag color="green">-</Tag>
                          )}
                          {childRows.length ? <Tag color="orange">含二级×{childRows.length}</Tag> : null}
                          {presetApplyMode === 'force' && childRows.length ? (
                            <Tag color="volcano">强制：选1条子条件</Tag>
                          ) : presetApplyMode === 'variant' && childRows.length ? (
                            <Tag color="blue">解析：子条件默认全选</Tag>
                          ) : (
                            <Tag color="green">已选</Tag>
                          )}
                        </Space>
                      ) : (
                        <Tag>未选</Tag>
                      )}
                    </Space>
                  ),
                  children: (
                    <Radio.Group
                      value={selectedParentId || ''}
                      onChange={(e) => {
                        const parentId = String(e?.target?.value ?? '')
                        const k = presetModalKey ? `${presetModalKey.pIdx}:${presetModalKey.cIdx}` : ''
                        if (!k) return
                        const compRow =
                          presetModalKey ? (phrasePresets?.[presetModalKey.pIdx]?.components ?? [])?.[presetModalKey.cIdx] : null
                        const wcm = Number(compRow?.width_cm ?? 0)
                        const hcm = Number(compRow?.height_cm ?? 0)
                        const children = parentId
                          ? (arr ?? []).filter((x: any) => String(x?.metadata?.parent_variant_id ?? '').trim() === parentId)
                          : []
                        const childIds = children.map((x: any) => String(x?.id)).filter(Boolean)
                        const pickBestChildId = (): string | null => {
                          if (!children.length) return null
                          const toNum = (x: any): number | null => {
                            if (x == null || x === '') return null
                            const n = Number(x)
                            return Number.isFinite(n) ? n : null
                          }
                          const between = (val: number | null, pair: any): boolean => {
                            if (val == null) return false
                            if (!Array.isArray(pair) || pair.length < 2) return false
                            const min = toNum(pair[0])
                            const max = toNum(pair[1])
                            if (min != null && val < min) return false
                            if (max != null && val > max) return false
                            return true
                          }
                          const areaM2 = wcm > 0 && hcm > 0 ? (wcm / 100) * (hcm / 100) : null
                          const perimM = wcm > 0 && hcm > 0 ? (2 * (wcm + hcm)) / 100 : null
                          const diameterCm = wcm > 0 && hcm > 0 && Math.abs(wcm - hcm) < 1e-6 ? wcm : null
                          const scored = children
                            .map((c: any) => {
                              const cond = (c?.conditions ?? {}) as any
                              const okW = cond.width_between ? between(wcm || null, cond.width_between) : true
                              const okH = cond.height_between ? between(hcm || null, cond.height_between) : true
                              const okA = cond.area_between ? between(areaM2, cond.area_between) : true
                              const okP = cond.perimeter_between ? between(perimM, cond.perimeter_between) : true
                              const okD = cond.diameter_between ? between(diameterCm, cond.diameter_between) : true
                              const matched = okW && okH && okA && okP && okD
                              return {
                                id: String(c?.id ?? ''),
                                matched,
                                priority: Number(c?.priority ?? 0) || 0,
                              }
                            })
                            .filter((x) => x.id)
                          const hits = scored.filter((x) => x.matched)
                          if (hits.length) {
                            hits.sort((a, b) => b.priority - a.priority)
                            return hits[0].id
                          }
                          return null
                        }
                        const best = pickBestChildId()
                        setPresetSelectedByIdx((prev) => ({
                          ...prev,
                          [k]: {
                            ...(prev[k] ?? {}),
                            [baseLineId]: {
                              parent_variant_id: parentId ? parentId : null,
                              child_variant_ids: childIds,
                              forced_child_variant_id: best || (childIds.length ? childIds[0] : null),
                            },
                          },
                        }))
                      }}
                    >
                      <Space direction="vertical" style={{ width: '100%' }} size={10}>
                        <Radio value="">不选择（该物料行用默认/其它规则）</Radio>
                        {(() => {
                          // 变体筛选（套装模板）按“一级”展示：
                          // - 新变体体系：二级（尺寸/面积/周长/直径）会写 metadata.parent_variant_id 归属某个一级 token 父规则
                          // - 套装里不需要逐条挑选二级表达式；只需选一级（用于填充触发词 / 强制命中）
                          const parents = arr.filter((v: any) => !String(v?.metadata?.parent_variant_id ?? '').trim())
                          const options = parents.length ? parents : arr
                          return options.map((v: any) => {
                            const id = String(v?.id ?? '')
                            const childRows = arr.filter((x: any) => String(x?.metadata?.parent_variant_id ?? '').trim() === id)
                            const hasChild = childRows.length > 0
                            const trigger = formatTrigger(v?.conditions)
                            const tokens = extractTokensForVariant(v)
                            const produced = Array.isArray(v?.items) ? v.items : []
                            const producedLabels: string[] = produced
                              .map((it: any) => String(it?.material_name ?? it?.material_code ?? '').trim())
                              .filter(Boolean)
                              .slice(0, 8)
                            const isSelectedParent = String(selectedParentId) === id
                            const forcedChildId = String(selected?.forced_child_variant_id ?? '').trim()
                            return (
                              <Radio key={String(v?.id)} value={String(v?.id)}>
                                <Space direction="vertical" size={4} style={{ width: '100%' }}>
                                  <Space size={8} wrap>
                                    {hasChild ? (
                                      <Tag color="orange">一级（含二级×{childRows.length}）</Tag>
                                    ) : (
                                      <Tag color={v?.enabled ? 'green' : 'default'}>{v?.enabled ? 'enabled' : 'disabled'}</Tag>
                                    )}
                                    <Tag>priority: {String(v?.priority ?? '-')}</Tag>
                                    <Tag>stop_on_hit: {String(!!v?.stop_on_hit)}</Tag>
                                    <Tag>action: {String(v?.action ?? '-')}</Tag>
                                  </Space>
                                  {/* 只读展示：优先展示 TOKEN 分词；无 TOKEN 时回退展示完整条件 */}
                                  {tokens.length ? (
                                    <Space wrap size={6}>
                                      <Text type="secondary">TOKEN：</Text>
                                      {tokens.map((t) => (
                                        <Tag
                                          key={`${String(v?.id)}:${t}`}
                                          style={{
                                            background: 'rgba(255,77,79,0.15)',
                                            color: '#cf1322',
                                            border: '1px solid #ffccc7',
                                          }}
                                        >
                                          {t}
                                        </Tag>
                                      ))}
                                      {hasChild ? <Text type="secondary">（二级按尺寸/指标继续判断）</Text> : null}
                                    </Space>
                                  ) : (
                                    <Text type="secondary">{trigger}</Text>
                                  )}
                                  {hasChild && isSelectedParent ? (
                                    presetApplyMode === 'variant' ? (
                                      <Text type="secondary" style={{ fontSize: 12 }}>
                                        子条件默认全选：{childRows.length}条（套装里不在此处逐条选择）
                                      </Text>
                                    ) : (
                                      <Space wrap size={8}>
                                        <Text type="secondary">指定子条件：</Text>
                                        <Select
                                          size="small"
                                          style={{ width: 520, maxWidth: '100%' }}
                                          placeholder="请选择一条子条件（强制命中）"
                                          value={forcedChildId || String(childRows?.[0]?.id ?? '') || undefined}
                                          options={childRows.map((c: any) => ({
                                            value: String(c?.id),
                                            label: formatTrigger(c?.conditions),
                                          }))}
                                          onChange={(cid) => {
                                            const k = presetModalKey ? `${presetModalKey.pIdx}:${presetModalKey.cIdx}` : ''
                                            if (!k) return
                                            setPresetSelectedByIdx((prev) => ({
                                              ...(prev ?? {}),
                                              [k]: {
                                                ...(prev?.[k] ?? {}),
                                                [baseLineId]: {
                                                  ...(prev?.[k]?.[baseLineId] ?? { parent_variant_id: id }),
                                                  parent_variant_id: id,
                                                  forced_child_variant_id: String(cid ?? '').trim() || null,
                                                },
                                              },
                                            }))
                                          }}
                                        />
                                      </Space>
                                    )
                                  ) : null}
                                  {/* 一级含二级时，最终替换由二级决定；不在此处展示“替换物料”以免误导 */}
                                  {!hasChild && producedLabels.length ? (
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
                          })
                        })()}
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
              <Input.Search
                style={{ width: 280 }}
                allowClear
                placeholder="搜索：短码/名称/运营短语"
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
              dataSource={filteredItems}
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
                // 列宽缩小（原 110）：编码列更紧凑
                { title: '编码', dataIndex: 'code', width: 70, render: (v) => <Text code>{String(v)}</Text> },
                // 名称缩小 1/3（180 -> 120）
                { title: '名称', dataIndex: 'name', width: 120, render: (v) => String(v ?? '').trim() || '-' },
                {
                  title: '分类',
                  width: 90,
                  render: (_: any, r: any) => String(r?.metadata?.category ?? '').trim() || '-',
                },
                {
                  // 短码 + 运营短语合并列：把空间都给“属性名称”
                  title: '属性名称',
                  width: 520,
                  render: (_: any, r: any) => {
                    const codeRaw = String(r?.code ?? '').trim()
                    const pp = Array.isArray(r?.metadata?.phrase_presets) ? r.metadata.phrase_presets : []
                    if (!codeRaw || !pp.length) return <Text type="secondary">-</Text>
                    return (
                      <Space direction="vertical" size={2}>
                        {pp.slice(0, 8).map((p: any, idx: number) => {
                          const sel = String(p?.selector ?? '').trim().toUpperCase() || toSelector2(idx)
                          const prefix = String(p?.mode ?? '').trim() === 'force' ? 'Z' : 'B'
                          const t =
                            sel && prefix === 'Z'
                              ? `Z-${String(codeRaw).toUpperCase()}${String(sel).toUpperCase()}`
                              : toBundleTokenDash(codeRaw, sel)
                          const phrase = String(p?.phrase ?? '').trim()
                          // 运营短语不需要展示 selector 前缀（例如 “AC:”）
                          const label = phrase || '-'
                          return (
                            <div key={`${t}-${label}`} style={{ display: 'flex', gap: 8, alignItems: 'flex-start', flexWrap: 'wrap' }}>
                              {/* 短码胶囊：有底色和外框色 */}
                              <Tag
                                color={prefix === 'Z' ? 'volcano' : 'blue'}
                                style={{
                                  marginInlineEnd: 0,
                                  borderRadius: 999,
                                  borderWidth: 1,
                                  borderStyle: 'solid',
                                  borderColor: prefix === 'Z' ? '#ffccc7' : '#91caff',
                                  minWidth: 120,
                                  textAlign: 'center',
                                  fontWeight: 700,
                                }}
                              >
                                {t}
                              </Tag>
                              {/* 运营短语：不截断，不显示复制图标 */}
                              <Text style={{ whiteSpace: 'normal' }}>{label}</Text>
                            </div>
                          )
                        })}
                        {pp.length > 8 ? <Text type="secondary">+{pp.length - 8}</Text> : null}
                      </Space>
                    )
                  },
                },
                {
                  title: '标签',
                  width: 200,
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
                  title: '模型',
                  // 模型列缩小一半（260 -> 130）
                  width: 130,
                  render: (_: any, r: any) => {
                    const meta = r?.metadata ?? {}
                    const pool = Array.isArray(meta?.model_pool_version_ids) ? meta.model_pool_version_ids : []
                    const pp = Array.isArray(meta?.phrase_presets) ? meta.phrase_presets : []
                    const ids = new Set<string>()
                    for (const x of pool) {
                      const s = String(x ?? '').trim()
                      if (s) ids.add(s)
                    }
                    for (const p of pp) {
                      const rows = Array.isArray(p?.components) ? p.components : []
                      for (const c of rows) {
                        const s = String(c?.model_version_id ?? '').trim()
                        if (s) ids.add(s)
                      }
                    }
                    const list = Array.from(ids).map((vid) => versionIdToModelLabel.get(vid) || vid.slice(0, 8))
                    if (!list.length) return <Text type="secondary">-</Text>
                    return (
                      <Space wrap>
                        {list.slice(0, 6).map((x) => (
                          <Tag key={x}>{x}</Tag>
                        ))}
                        {list.length > 6 ? <Tag>+{list.length - 6}</Tag> : null}
                      </Space>
                    )
                  },
                },
                {
                  title: '更新时间',
                  // 只要日期 + 列宽缩小 1/3（170 -> 110）
                  width: 110,
                  dataIndex: 'updated_at',
                  render: (v) => {
                    const s = String(v ?? '').trim()
                    if (!s) return '-'
                    // ISO / datetime -> YYYY-MM-DD
                    const d = s.includes('T') ? s.split('T')[0] : s.split(' ')[0]
                    return d || s
                  },
                },
                {
                  title: '状态',
                  width: 90,
                  render: (_: any, r: any) => (r?.is_archived ? <Tag color="orange">archived</Tag> : <Tag color="green">active</Tag>),
                },
                {
                  title: '操作',
                  width: 220,
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
        width={1280}
        destroyOnClose={false}
        title={
          editing?.id
            ? `编辑套装模板（${toBundleTokenDash(String(editing?.code ?? ''), 'AA')}）`
            : '新建套装模板'
        }
        extra={
          <Space>
            <Button onClick={() => setDrawerOpen(false)}>关闭</Button>
            <Button type="primary" loading={saveMutation.isPending} onClick={() => saveMutation.mutate()}>
              保存模板
            </Button>
          </Space>
        }
      >
        <Space direction="vertical" style={{ width: '100%' }} size={12}>
          {/* 降噪：不在编辑页重复提示“把短码放进交易规格” */}

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

            <Form.Item label="模型选择（缩小范围，多选）">
              <Select
                className="bt-model-pool-select"
                mode="multiple"
                showSearch
                allowClear
                placeholder="先选本模板可能用到的模型版本（用于缩小下方下拉范围）"
                loading={versionPickerQuery.isLoading}
                options={versionOptions as any}
                value={modelPoolVersionIds}
                onChange={(v) => setModelPoolVersionIds(Array.isArray(v) ? (v as any[]).map((x) => String(x)).filter(Boolean) : [])}
              />
            </Form.Item>
          </Form>

          {/* 已按运营心智收口：不再展示“全局字段映射/可变词列表”，避免误会与绕圈。 */}

          <div style={{ display: 'flex', gap: 12, width: '100%', alignItems: 'stretch' }}>
            {/* 左侧：属性列表 + 新建/复制/停用 */}
            <Card
              size="small"
              style={{ flex: '0 0 380px', minWidth: 340 }}
              title={
                <Space size={8}>
                  <Text strong>属性列表</Text>
                  <Tag>{phrasePresets.length}</Tag>
                </Space>
              }
              extra={
                <Space size={8}>
                  <Button size="small" type="dashed" onClick={addPhrasePreset}>
                    新建
            </Button>
                </Space>
              }
              bodyStyle={{ padding: 8 }}
            >
              <style>{`
                /* BundleTemplatesPage: phrase card list micro-UX */
                .bt-phrase-card-icon-btn.ant-btn {
                  color: rgba(0,0,0,0.45);
                  padding: 0 4px;
                  height: 24px;
                }
                .bt-phrase-card-icon-btn.ant-btn:not([disabled]):hover {
                  color: #1677ff;
                  background: rgba(22,119,255,0.08);
                }
                .bt-phrase-card-icon-btn.ant-btn[disabled] {
                  color: rgba(0,0,0,0.25);
                }
                /* Model pool select: allow wrapping tags onto multiple lines */
                .bt-model-pool-select .ant-select-selector {
                  height: auto !important;
                  padding-top: 4px !important;
                  padding-bottom: 4px !important;
                  flex-wrap: wrap !important;
                }
                .bt-model-pool-select .ant-select-selection-overflow {
                  flex-wrap: wrap !important;
                }
              `}</style>
              <List
                locale={{ emptyText: '暂无属性：点击右上角“新建”添加第一条' }}
                dataSource={phrasePresets}
                renderItem={(p: any, idx: number) => {
                  const sel = String(p?.selector ?? '').trim().toUpperCase() || toSelector2(idx)
                  const codeOnly = String(currentBundleToken || '').toUpperCase().replace(/^B:/, '').replace(/^BUNDLE:/, '')
                  const prefix = String(p?.mode ?? '').trim() === 'force' ? 'Z' : 'B'
                  const tokenDash = codeOnly
                    ? prefix === 'Z'
                      ? `Z-${codeOnly}${sel}`
                      : toBundleTokenDash(codeOnly, sel)
                    : `${prefix}-????${sel}`
                  const active = idx === activePresetIndex
                  const enabled = p?.enabled !== false
                  const phraseText = String(p?.phrase ?? '').trim() || '-'
                  return (
                    <div
                      style={{
                        border: active ? '1px solid #1677ff' : '1px solid rgba(0,0,0,0.08)',
                        borderRadius: 8,
                        padding: 10,
                        marginBottom: 8,
                        background: active ? 'rgba(22,119,255,0.06)' : '#fff',
                        cursor: 'pointer',
                      }}
                      onClick={() => setActivePresetIndex(idx)}
                    >
                      <Space direction="vertical" size={6} style={{ width: '100%' }}>
                        {/* 第一行：编码（左）+ 操作按钮（右） */}
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                          <div style={{ minWidth: 0, display: 'flex', alignItems: 'center' }}>
                            <Tag
                              color={!enabled ? 'default' : prefix === 'Z' ? 'volcano' : 'blue'}
                              style={{ fontWeight: 600, marginInlineEnd: 0 }}
                            >
                              {tokenDash}
                            </Tag>
          </div>
                          <Space size={0}>
                            <Button
            size="small"
                              type="text"
                              className="bt-phrase-card-icon-btn"
                              icon={<CopyOutlined />}
                              title="复制"
                              onClick={(e) => {
                                e.stopPropagation()
                                copyPhrasePreset(idx)
                              }}
                            />
                            <Button
                              size="small"
                              type="text"
                              className="bt-phrase-card-icon-btn"
                              icon={<DeleteOutlined />}
                              title="删除"
                              onClick={(e) => {
                                e.stopPropagation()
                                deletePhrasePreset(idx)
                              }}
                            />
                            <Button
                              size="small"
                              type="text"
                              className="bt-phrase-card-icon-btn"
                              icon={<ArrowUpOutlined />}
                              title="上移"
                              disabled={idx <= 0}
                              onClick={(e) => {
                                e.stopPropagation()
                                movePhrasePreset(idx, idx - 1)
                              }}
                            />
                            <Button
                              size="small"
                              type="text"
                              className="bt-phrase-card-icon-btn"
                              icon={<ArrowDownOutlined />}
                              title="下移"
                              disabled={idx >= (phrasePresets?.length ?? 0) - 1}
                              onClick={(e) => {
                                e.stopPropagation()
                                movePhrasePreset(idx, idx + 1)
                              }}
                            />
                            <Button
                              size="small"
                              type="text"
                              className="bt-phrase-card-icon-btn"
                              icon={enabled ? <PauseCircleOutlined /> : <PlayCircleOutlined />}
                              title={enabled ? '停用' : '启用'}
                              onClick={(e) => {
                                e.stopPropagation()
                                // 防呆：同一 selector 编码只允许启用 1 条（避免命中歧义）
                                const cur = phrasePresets?.[idx] as any
                                const sel = String(cur?.selector ?? '').trim().toUpperCase() || toSelector2(idx)
                                const willEnable = !(cur?.enabled !== false)
                                if (willEnable) {
                                  const conflict = (phrasePresets ?? []).some((x: any, i2: number) => {
                                    if (i2 === idx) return false
                                    if (x?.enabled === false) return false
                                    const s2 = String(x?.selector ?? '').trim().toUpperCase() || toSelector2(i2)
                                    return s2 === sel
                                  })
                                  if (conflict) {
                                    message.warning(`属性 ${sel} 已有启用项，请先停用其它同编码属性`)
                                    return
                                  }
                                }
                                setPhrasePresets((prev) =>
                                  (prev ?? []).map((x, i) => (i !== idx ? x : { ...x, enabled: x.enabled === false ? true : false })),
                                )
                              }}
                            />
                          </Space>
                        </div>

                        {/* 第二行：纯短语（运营短语不截短，全显示） */}
                        <Text style={{ color: 'rgba(0,0,0,0.88)', whiteSpace: 'normal' }}>
                          {phraseText}
                        </Text>
                      </Space>
                    </div>
                  )
                }}
              />
            </Card>

            {/* 右侧：当前选中属性的组件行编辑 */}
            <Card
              size="small"
              style={{ flex: 1, minWidth: 0 }}
              title={<Text strong>属性编辑</Text>}
              bodyStyle={{ padding: 8 }}
            >
              {(phrasePresets ?? []).length <= 0 ? (
                <Empty
                  description={
                    <span>
                      先在左侧新建一条属性，再在右侧为该属性添加组件行（模型/尺寸/数量/筛选/复制）。
                    </span>
                  }
                />
              ) : (
                (() => {
                  const r = phrasePresets[activePresetIndex]
                  const idx = activePresetIndex
                const rows = Array.isArray(r?.components) ? (r.components as any[]) : []
                  const disabled = r?.enabled === false
                const allowed = modelPoolVersionIds.length ? new Set(modelPoolVersionIds.map((x) => String(x))) : null
                const options = allowed
                    ? (versionOptionsCompact as any[]).filter((o: any) => allowed.has(String(o?.value)))
                    : (versionOptionsCompact as any[])
                  const selector = String(r?.selector ?? '').trim().toUpperCase() || toSelector2(idx)
                return (
                  <Space direction="vertical" style={{ width: '100%' }} size={8}>
                      <Space wrap size={10} style={{ width: '100%', justifyContent: 'space-between' }}>
                        <Space wrap size={8}>
                          <Text type="secondary">当前：</Text>
                          <Text code>{selector}</Text>
                          {disabled ? <Tag color="red">已停用</Tag> : <Tag color="green">启用</Tag>}
                        </Space>
                        <Space wrap size={8}>
                          <Button
                            onClick={() => validateCurrentPreset()}
                            icon={
                              presetValidation && presetValidation.presetIndex === idx ? (
                                presetValidation.ok ? (
                                  <CheckCircleFilled style={{ color: '#52c41a' }} />
                                ) : (
                                  <CloseCircleFilled style={{ color: '#ff4d4f' }} />
                                )
                              ) : undefined
                            }
                          >
                            检验结果
                          </Button>
                          <Button
                            danger
                            disabled={disabled}
                            onClick={() => cleanupInvalidSelectionsForPreset(idx)}
                          >
                            清理失效规则
                          </Button>
                          <Button
                            type="primary"
                            loading={saveMutation.isPending}
                            onClick={() => {
                              // 强校验：避免“保存了但不敢用/容易出问题”
                              const v = validateActivePreset()
                              if (!v.ok) {
                                message.warning(v.reason || '请完善当前属性')
                                return
                              }
                              // 额外：全局校验（启用的短语必须有备注与至少1条组件行）
                              const vv = validateAllEnabledPresetsBeforeSave()
                              if (!vv.ok) {
                                Modal.error({
                                  title: '保存前校验未通过',
                                  content: (
                                    <div>
                                      <Text type="danger">存在必填项缺失，建议先补齐再保存：</Text>
                                      <div style={{ marginTop: 8 }}>
                                        {vv.issues.slice(0, 8).map((it, i2) => (
                                          <div key={`v-iss-${i2}`}>
                                            <Text type={it.level === 'error' ? 'danger' : 'secondary'}>{it.message}</Text>
                                          </div>
                                        ))}
                                        {vv.issues.length > 8 ? <Text type="secondary">…还有 {vv.issues.length - 8} 条</Text> : null}
                                      </div>
                                    </div>
                                  ),
                                })
                                return
                              }
                              saveMutation.mutate()
                            }}
                          >
                            保存当前属性
                          </Button>
                        </Space>
                      </Space>
                      {presetValidation && presetValidation.presetIndex === idx && presetValidation.issues.length ? (
                        <Alert
                          type={presetValidation.ok ? 'success' : 'error'}
                          showIcon
                          message={presetValidation.ok ? '检验通过' : '检验未通过'}
                          description={
                            <div>
                              {presetValidation.issues.slice(0, 6).map((it, i2) => (
                                <div key={`${idx}-iss-${i2}`}>
                                  <Text type={it.level === 'error' ? 'danger' : 'secondary'}>{it.message}</Text>
                                </div>
                              ))}
                              {presetValidation.issues.length > 6 ? (
                                <Text type="secondary">…还有 {presetValidation.issues.length - 6} 条</Text>
                              ) : null}
                            </div>
                          }
                        />
                      ) : null}
                      <Input
                        placeholder={
                          String((r as any)?.mode ?? 'parse') === 'force'
                            ? '属性备注（可选）：例如 黄金绒双面30X50+PP棉枕芯'
                            : '属性名称/公式（解析型，默认自动生成，可编辑）：例如 [{黄金绒}{雪尼尔}]30*50*1 + [{PP}{羽丝绒}]45*45*1'
                        }
                        disabled={disabled}
                        value={String(r?.phrase ?? '')}
                        onChange={(e) =>
                          setPhrasePresets((prev) => (prev ?? []).map((x, i) => (i === idx ? { ...x, phrase: e.target.value } : x)))
                        }
                      />
                      <Space wrap align="center" size={10}>
                        <Text type="secondary">模式：</Text>
                        {(() => {
                          const hasAnyFilterSelection = Object.entries(presetSelectedByIdx ?? {}).some(([kk, mm]) => {
                            if (!String(kk).startsWith(`${idx}:`)) return false
                            const entries = Object.values((mm ?? {}) as any)
                            return entries.some((s: any) => !!String(s?.parent_variant_id ?? '').trim())
                          })
                          const hasAnyForceMap = Array.isArray((r as any)?.components)
                            ? ((r as any).components as any[]).some((cc: any) => {
                                const fm = cc?.force_variant_by_base_line && typeof cc.force_variant_by_base_line === 'object' ? cc.force_variant_by_base_line : {}
                                return Object.keys(fm ?? {}).length > 0
                              })
                            : false
                          const isModeLocked = hasAnyFilterSelection || hasAnyForceMap
                          return (
                            <>
                              <Radio.Group
                                value={String((r as any)?.mode ?? 'parse') === 'force' ? 'force' : 'parse'}
                                disabled={disabled || isModeLocked}
                                optionType="button"
                                buttonStyle="solid"
                                onChange={(e) => {
                                  const v = (e?.target?.value as any) ?? 'parse'
                                  setPhrasePresets((prev) =>
                                    (prev ?? []).map((x, i) => (i === idx ? { ...x, mode: v === 'force' ? 'force' : 'parse' } : x)),
                                  )
                                }}
                                options={[
                                  // 调整顺序：指定型在前；默认新建短语也为指定型
                                  { label: 'Z（指定型）', value: 'force' },
                                  { label: 'B（解析型）', value: 'parse' },
                                ]}
                              />
                              {isModeLocked ? <Tag color="orange">已锁定（已筛选/已强制）</Tag> : null}
                            </>
                          )
                        })()}
                        <Text type="secondary">
                          运营短码：
                          <Text code style={{ marginLeft: 6 }}>
                            {(String((r as any)?.mode ?? 'parse') === 'force' ? 'Z' : 'B') + '-' + String(currentBundleToken || '').replace(/^B:/, '').replace(/^BUNDLE:/, '').replace(/^Z:/, '') + String(selector)}
                          </Text>
                        </Text>
                        {String((r as any)?.mode ?? 'parse') === 'force'
                          ? null
                          : (() => {
                              const built = buildAttributeFormulaAndGroups({
                                presetIndex: idx,
                                componentRows: rows,
                                presetSelectedByIdx,
                                fallbackTokenOverrides,
                                variantTokenOptionsByVersionBaseLine,
                                baseLineInfoByVersionBaseLine,
                              })
                              const formula = built.formula
                              const components = built.components
                              return (
                                <Space direction="vertical" size={6}>
                                  <Space wrap size={6}>
                                    <Text type="secondary">属性公式：</Text>
                                    <Text type="secondary">已写入上方“属性名称/公式”输入框（可编辑）</Text>
                                    <Button
                                      size="small"
                                      icon={<CopyOutlined />}
                                      disabled={!String(r?.phrase ?? '').trim()}
                                      onClick={async () => {
                                        const ok = await copyTextToClipboard(String(r?.phrase ?? '').trim())
                                        if (ok) message.success('已复制属性公式')
                                        else message.error('复制失败：请手动复制')
                                      }}
                                    >
                                      复制公式
                                    </Button>
                                    <Button
                                      size="small"
                                      onClick={() => {
                                        if (!formula) {
                                          message.warning('暂无可生成的属性公式（请先筛选/强制）')
                                          return
                                        }
                                        setPhrasePresets((prev) => (prev ?? []).map((x, i) => (i === idx ? { ...x, phrase: formula } : x)))
                                        message.success('已写入属性公式到输入框')
                                      }}
                                    >
                                      重新生成
                                    </Button>
                                  </Space>

                                  {/* 互斥组下拉（解析型专用）：每组一个单选 Select；按组件显示 */}
                                  {components.length ? (
                                    <Space direction="vertical" size={6} style={{ width: '100%' }}>
                                      <style>{`
                                        .bt-model-pill {
                                          display: inline-flex;
                                          align-items: center;
                                          padding: 1px 6px;
                                          border-radius: 999px;
                                          font-weight: 700;
                                          background: rgba(22,119,255,0.12);
                                          border: 1px solid rgba(22,119,255,0.35);
                                          color: #0958d9;
                                          line-height: 16px;
                                          font-size: 12px;
                                        }
                                        .bt-model-reorder-btn.ant-btn {
                                          padding: 0 4px;
                                          height: 18px;
                                          line-height: 18px;
                                          color: rgba(0,0,0,0.45);
                                        }
                                        .bt-model-reorder-btn.ant-btn:not([disabled]):hover {
                                          color: #1677ff;
                                          background: rgba(22,119,255,0.08);
                                        }
                                      `}</style>
                                      {(() => {
                                        const orderKey = String(idx)
                                        const rawOrder = componentOrderByPreset?.[orderKey]
                                        const defaultOrder = components.map((c) => c.componentIndex)
                                        const order = Array.isArray(rawOrder) && rawOrder.length ? rawOrder : defaultOrder
                                        const seen = new Set<number>()
                                        const ordered = order
                                          .map((i) => Number(i))
                                          .filter((i) => Number.isFinite(i))
                                          .filter((i) => (seen.has(i) ? false : (seen.add(i), true)))
                                          .map((i) => components.find((c) => c.componentIndex === i))
                                          .filter(Boolean) as AttributeComponentGroups[]
                                        const rest = components.filter((c) => !seen.has(c.componentIndex))
                                        return [...ordered, ...rest]
                                      })().map((c) => {
                                        const versionId = String((rows?.[c.componentIndex] as any)?.model_version_id ?? '').trim()
                                        const label = versionId ? String(versionIdToModelLabel.get(versionId) ?? '') : ''
                                        const modelCode = label.includes(':') ? label.split(':')[0] : label
                                        const orderKey = String(idx)
                                        const currentOrder = componentOrderByPreset?.[orderKey] ?? []
                                        const ordered = currentOrder.length
                                          ? currentOrder.slice()
                                          : components.map((cc) => cc.componentIndex)
                                        const pos = ordered.indexOf(c.componentIndex)
                                        const canUp = pos > 0
                                        const canDown = pos >= 0 && pos < ordered.length - 1
                                        return (
                                          <Space key={`attr-comp-${idx}-${c.componentIndex}`} wrap size={8}>
                                            <Space size={4} align="center">
                                              <span className="bt-model-pill">{modelCode || '组件'}</span>
                                              <Button
                                                size="small"
                                                type="text"
                                                className="bt-model-reorder-btn"
                                                icon={<ArrowUpOutlined />}
                                                disabled={!canUp}
                                                onClick={() => {
                                                  const next = ordered.slice()
                                                  if (pos <= 0) return
                                                  const tmp = next[pos - 1]
                                                  next[pos - 1] = next[pos]
                                                  next[pos] = tmp
                                                  setComponentOrderByPreset((prev) => ({ ...(prev ?? {}), [orderKey]: next }))
                                                }}
                                              />
                                              <Button
                                                size="small"
                                                type="text"
                                                className="bt-model-reorder-btn"
                                                icon={<ArrowDownOutlined />}
                                                disabled={!canDown}
                                                onClick={() => {
                                                  const next = ordered.slice()
                                                  if (pos < 0 || pos >= next.length - 1) return
                                                  const tmp = next[pos + 1]
                                                  next[pos + 1] = next[pos]
                                                  next[pos] = tmp
                                                  setComponentOrderByPreset((prev) => ({ ...(prev ?? {}), [orderKey]: next }))
                                                }}
                                              />
                                            </Space>
                                            {(() => {
                                              const groupOrderKey = `${idx}:${c.componentIndex}`
                                              const order = groupOrderByPresetComponent?.[groupOrderKey] ?? []
                                              if (!Array.isArray(order) || !order.length) return c.groups
                                              const idxMap = new Map<string, number>()
                                              for (let i = 0; i < order.length; i++) idxMap.set(String(order[i]), i)
                                              return c.groups.slice().sort((a, b) => (idxMap.get(a.key) ?? 1e9) - (idxMap.get(b.key) ?? 1e9))
                                            })().map((g) => {
                                              const selKey = `${idx}:${c.componentIndex}:${g.key}`
                                              const options = (g.options ?? []).map((x) => normalizeSingleToken(x))
                                              const uniq: string[] = []
                                              const seen = new Set<string>()
                                              for (const t of options) {
                                                const k = t || '__EMPTY__'
                                                if (seen.has(k)) continue
                                                seen.add(k)
                                                uniq.push(t)
                                              }
                                              const value = getEffectiveSelection({
                                                presetIndex: idx,
                                                componentIndex: c.componentIndex,
                                                group: g,
                                                attributeGroupSelections,
                                              })
                                              const groupOrderKey = `${idx}:${c.componentIndex}`
                                              const currentOrder = groupOrderByPresetComponent?.[groupOrderKey] ?? []
                                              const baseOrder = currentOrder.length ? currentOrder.slice() : c.groups.map((x) => x.key)
                                              const pos = baseOrder.indexOf(g.key)
                                              const canLeft = pos > 0
                                              const canRight = pos >= 0 && pos < baseOrder.length - 1
                                              return (
                                                <Space key={`attr-sel-${selKey}`} size={2} align="center">
                                                  <Button
                                                    size="small"
                                                    type="text"
                                                    className="bt-model-reorder-btn"
                                                    icon={<LeftOutlined />}
                                                    disabled={!canLeft}
                                                    onClick={() => {
                                                      const next = baseOrder.slice()
                                                      if (pos <= 0) return
                                                      const tmp = next[pos - 1]
                                                      next[pos - 1] = next[pos]
                                                      next[pos] = tmp
                                                      setGroupOrderByPresetComponent((prev) => ({ ...(prev ?? {}), [groupOrderKey]: next }))
                                                    }}
                                                  />
                                                  <Select
                                                    size="small"
                                                    style={{ width: 150 }}
                                                    value={value}
                                                    onChange={(v) =>
                                                      setAttributeGroupSelections((prev) => ({
                                                        ...(prev ?? {}),
                                                        [selKey]: String(v ?? ''),
                                                      }))
                                                    }
                                                    options={uniq
                                                      .filter((x) => (g.isZeroCostGroup ? true : !!String(x).trim()))
                                                      .map((t) => ({ value: t, label: t ? t : '（无）' }))}
                                                  />
                                                  <Button
                                                    size="small"
                                                    type="text"
                                                    className="bt-model-reorder-btn"
                                                    icon={<RightOutlined />}
                                                    disabled={!canRight}
                                                    onClick={() => {
                                                      const next = baseOrder.slice()
                                                      if (pos < 0 || pos >= next.length - 1) return
                                                      const tmp = next[pos + 1]
                                                      next[pos + 1] = next[pos]
                                                      next[pos] = tmp
                                                      setGroupOrderByPresetComponent((prev) => ({ ...(prev ?? {}), [groupOrderKey]: next }))
                                                    }}
                                                  />
                                                </Space>
                                              )
                                            })}
                                          </Space>
                                        )
                                      })}

                                      {(() => {
                                        const orderKey = String(idx)
                                        const componentOrder = componentOrderByPreset?.[orderKey]
                                        const autoRule = buildAutoRuleFromSelections({
                                          presetIndex: idx,
                                          components,
                                          componentRows: rows,
                                          attributeGroupSelections,
                                          componentOrder,
                                          groupOrderByPresetComponent,
                                        })
                                        return (
                                          <Space wrap size={8}>
                                            <Text type="secondary">自动生成：</Text>
                                            <Text code>{autoRule || '-'}</Text>
                                            <Button
                                              size="small"
                                              disabled={!autoRule}
                                              onClick={() => {
                                                if (!autoRule) return
                                                setPhrasePresets((prev) => (prev ?? []).map((x, i) => (i === idx ? { ...x, phrase: autoRule } : x)))
                                                message.success('已写入自动生成内容到输入框')
                                              }}
                                            >
                                              写入输入框
                                            </Button>
                                          </Space>
                                        )
                                      })()}
                                    </Space>
                                  ) : (
                                    <Text type="secondary">提示：请先对需要的物料位做一次“筛选”或“强制”，才会生成互斥组下拉。</Text>
                                  )}
                                </Space>
                              )
                            })()}
                        <Button
                          size="small"
                          disabled={!String(currentBundleToken || '').trim()}
                          icon={<PlayCircleOutlined />}
                          onClick={() => {
                            const codeOnly = String(currentBundleToken || '').replace(/^B:/, '').replace(/^BUNDLE:/, '').replace(/^Z:/, '')
                            const prefix = String((r as any)?.mode ?? 'parse') === 'force' ? 'Z' : 'B'
                            const specText = `${prefix}-${String(codeOnly).toUpperCase()}${String(selector).toUpperCase()}`
                            setBundlePreviewSpecText(specText)
                            bundlePreviewMutation.mutate({ selector: String(selector), spec_text: specText })
                          }}
                        >
                          预演(debug)
                        </Button>
                      </Space>
                      {/* 降噪：筛选弹窗模式已由 selector(B/Z) 锁死 */}
                      {disabled ? (
                        <Alert
                          type="warning"
                          showIcon
                          message="该属性已停用"
                          description="停用状态下不会参与命中解析；如需编辑请先在左侧启用。"
                        />
                      ) : null}
                    <Table
                      size="small"
                      pagination={false}
                      rowKey={(_, mi) => `ppc-${idx}-${mi}`}
                      dataSource={rows}
                        locale={{ emptyText: '暂无组件行：点击右侧“+行”添加第一条' }}
                      expandable={{
                        expandedRowKeys: (rows ?? []).map((_: any, mi: number) => `ppc-${idx}-${mi}`),
                        showExpandColumn: false,
                        expandedRowRender: (rr: any, mi: number) => {
                          const versionId = String(rr?.model_version_id ?? '').trim()
                          const k = `${idx}:${mi}`
                          const sel = (presetSelectedByIdx[k] ?? {}) as Record<string, VariantPresetSelection>
                          const selectedEntries = Object.entries(sel).filter(([, v]) => !!String(v?.parent_variant_id ?? '').trim())
                          if (!versionId) return null

                          const forceMap = rr?.force_variant_by_base_line && typeof rr.force_variant_by_base_line === 'object' ? rr.force_variant_by_base_line : {}
                          const isForce = Object.keys(forceMap ?? {}).length > 0

                          const variantsForVersion = ((variantsSummaryQuery.data ?? []) as any[]).find(
                            (x: any) => String(x?.version_id ?? '') === versionId,
                          )?.items as any[]
                          const variants = Array.isArray(variantsForVersion) ? variantsForVersion : []
                          const variantsById = new Map<string, any>()
                          for (const v of variants) {
                            if (v?.id) variantsById.set(String(v.id), v)
                          }

                          const baseMap = baseLineMapByVersion.get(versionId) ?? new Map<string, any>()

                            const extractTokensForVariant = (v: any): string[] => {
                              const cond = (v?.conditions ?? {}) as any
                              const anyTokens = Array.isArray(cond?.spec_contains_any) ? cond.spec_contains_any : []
                              const allTokens = Array.isArray(cond?.spec_contains_all) ? cond.spec_contains_all : []
                              const out: string[] = []
                              for (const t of [...anyTokens, ...allTokens]) {
                                const s = String(t ?? '').trim()
                                if (!s) continue
                                const up = s.toUpperCase()
                                if (up.startsWith('MODEL:') || up.startsWith('M:') || up.startsWith('BOUND_VERSION:') || up.startsWith('SKU:')) continue
                                out.push(s)
                              }
                              // de-dup while preserving order
                              const seen = new Set<string>()
                              const uniq: string[] = []
                              for (const x of out) {
                                const k = String(x).trim()
                                if (!k || seen.has(k)) continue
                                seen.add(k)
                                uniq.push(k)
                              }
                              return uniq
                            }

                          return (
                            <Space direction="vertical" size={4} style={{ width: '100%' }}>
                              {/* 降噪：不展示“Z模式关键行”区块；Z 模式的强制覆盖由校验自动约束 */}
                              {/* 降噪：不在此处展示“已注入触发词”与教学文案；由 Z/B 模式与预演承担验证 */}
                              {/* 默认兜底：第一条与其它行同格式（TOKEN 可输入，兜底物料原名只读） */}
                              {!isForce ? (() => {
                                const seen = new Set<string>()
                                const uniqIds: string[] = []
                                for (const [baseLineId] of selectedEntries) {
                                  const id = String(baseLineId)
                                  if (!id || seen.has(id)) continue
                                  seen.add(id)
                                  uniqIds.push(id)
                                }
                                if (!uniqIds.length) return null
                                return (
                                  <Space direction="vertical" size={6} style={{ width: '100%' }}>
                                    {uniqIds.map((baseLineId) => {
                                      const base = baseMap.get(String(baseLineId))
                                      const slot = getLineStructureLabel(base, versionId)
                                      const rawName = String(base?.material_name ?? base?.material_code ?? baseLineId).trim()
                                      const overrideKey = `${versionId}:${String(baseLineId)}`
                                      const tokenAlias = String(fallbackTokenOverrides?.[overrideKey] ?? '').trim()
                                      return (
                                        <Space key={`fb-token-${overrideKey}`} wrap size={10}>
                                          <Text type="secondary">TOKEN：</Text>
                                          <Input
                                            size="small"
                                            style={{ width: 180 }}
                                            placeholder="例如：黄金绒（可选；仅允许1个TOKEN）"
                                            disabled={disabled || rawName.includes('兜底-零成本')}
                                            value={tokenAlias}
                                            onChange={(e) => {
                                              const next = normalizeSingleToken(e.target.value)
                                              setFallbackTokenOverrides((prev) => ({
                                                ...(prev ?? {}),
                                                [overrideKey]: next,
                                              }))
                                            }}
                                          />
                                          <Text type="secondary">兜底物料：</Text>
                                          <Text title={rawName}>
                                            {slot ? `${slot}：` : ''}
                                            {rawName}
                                          </Text>
                                        </Space>
                                      )
                                    })}
                                  </Space>
                                )
                              })() : null}

                              {selectedEntries.map(([baseLineId, s]) => {
                                const parentId = String(s?.parent_variant_id ?? '').trim()
                                const forcedChildId = String(s?.forced_child_variant_id ?? '').trim()
                                const pickId = isForce && forcedChildId ? forcedChildId : parentId
                                const v = variantsById.get(String(pickId))
                                const base = baseMap.get(String(baseLineId))
                                const slot = getLineStructureLabel(base, versionId)
                                const rawName = String(base?.material_name ?? base?.material_code ?? baseLineId).trim()
                                const tokens = extractTokensForVariant(v)
                                const produced = Array.isArray(v?.items) ? v.items : []
                                const producedOne = produced[0]
                                const producedLabel = String(
                                  producedOne?.material_name ?? producedOne?.material_code ?? producedOne?.material_ref_id ?? '',
                                ).trim()

                                return (
                                  <div key={`${k}:${baseLineId}:${pickId}`}>
                                    <Space wrap size={8}>
                                      {isForce ? (
                                        <>
                                          <Tag
                                            style={{
                                              background: 'rgba(255, 77, 79, 0.14)',
                                              color: '#cf1322',
                                              border: '1px solid #ffccc7',
                                              fontWeight: 700,
                                            }}
                                          >
                                            FORCE
                                          </Tag>
                                          <Tag
                                            style={{
                                              background: 'rgba(250,173,20,0.18)',
                                              color: '#d46b08',
                                              border: '1px solid #ffe7ba',
                                              fontWeight: 700,
                                            }}
                                          >
                                            强制替换
                                          </Tag>
                                          <Tag color="default">
                                            {slot ? `${slot}：` : ''}
                                            {rawName}
                                          </Tag>
                                          <Text type="secondary">→</Text>
                                          <Tag color="red">{producedLabel || '-'}</Tag>
                                        </>
                                      ) : (
                                        <>
                                          <Tag
                                            style={{
                                              background: 'rgba(22, 119, 255, 0.14)',
                                              color: '#0958d9',
                                              border: '1px solid #91caff',
                                              fontWeight: 700,
                                            }}
                                          >
                                            TOKEN
                                          </Tag>
                                          {tokens.length ? (
                                            tokens.map((t) => (
                                              <Tag
                                                key={`${k}:${baseLineId}:${pickId}:${t}`}
                                                style={{
                                                  background: 'rgba(255,77,79,0.15)',
                                                  color: '#cf1322',
                                                  border: '1px solid #ffccc7',
                                                }}
                                              >
                                                {t}
                                              </Tag>
                                            ))
                                          ) : (
                                            <Text type="secondary">（无 TOKEN）</Text>
                                          )}
                                          <Tag color="default">
                                            {slot ? `${slot}：` : ''}
                                            {rawName}
                                          </Tag>
                                          <Text type="secondary">→</Text>
                                          <Tag color="red">{producedLabel || '-'}</Tag>
                                        </>
                                      )}
                                      {/* 降噪：一级/子规则 id 仅用于排障，不对运营展示 */}
                                    </Space>
                                  </div>
                                )
                              })}
                            </Space>
                          )
                        },
                      }}
                      columns={[
                        {
                            title: '模型版本',
                            width: 520,
                          render: (_: any, rr: any, mi: number) => (
                            <Select
                              showSearch
                              allowClear
                                disabled={disabled}
                              placeholder="选择模型版本"
                              style={{ width: '100%' }}
                              loading={versionPickerQuery.isLoading}
                              options={options as any}
                              value={rr.model_version_id ?? undefined}
                              onChange={(v) =>
                                setPhrasePresets((prev) =>
                                    (prev ?? []).map((pp, pi) =>
                                    pi !== idx
                                      ? pp
                                      : {
                                          ...pp,
                                          components: (pp.components ?? []).map((c, ci) =>
                                            ci === mi ? { ...c, model_version_id: (v as any) ?? null } : c,
                                          ),
                                        },
                                  ),
                                )
                              }
                            />
                          ),
                        },
                        {
                            title: '宽(cm)',
                            width: 110,
                          render: (_: any, rr: any, mi: number) => (
                            <Input
                                disabled={disabled}
                              value={String(rr.width_cm ?? '')}
                              onChange={(e) => {
                                const v = Number(e.target.value)
                                setPhrasePresets((prev) =>
                                    (prev ?? []).map((pp, pi) =>
                                    pi !== idx
                                      ? pp
                                      : {
                                          ...pp,
                                          components: (pp.components ?? []).map((c, ci) =>
                                            ci === mi ? { ...c, width_cm: Number.isFinite(v) ? v : 0 } : c,
                                          ),
                                        },
                                  ),
                                )
                              }}
                            />
                          ),
                        },
                        {
                            title: '高(cm)',
                            width: 110,
                          render: (_: any, rr: any, mi: number) => (
                            <Input
                                disabled={disabled}
                              value={String(rr.height_cm ?? '')}
                              onChange={(e) => {
                                const v = Number(e.target.value)
                                setPhrasePresets((prev) =>
                                    (prev ?? []).map((pp, pi) =>
                                    pi !== idx
                                      ? pp
                                      : {
                                          ...pp,
                                          components: (pp.components ?? []).map((c, ci) =>
                                            ci === mi ? { ...c, height_cm: Number.isFinite(v) ? v : 0 } : c,
                                          ),
                                        },
                                  ),
                                )
                              }}
                            />
                          ),
                        },
                        {
                            title: '数量',
                            width: 90,
                          render: (_: any, rr: any, mi: number) => (
                            <Input
                                disabled={disabled}
                              value={String(rr.quantity ?? '')}
                              onChange={(e) => {
                                const v = Number(e.target.value)
                                setPhrasePresets((prev) =>
                                    (prev ?? []).map((pp, pi) =>
                                    pi !== idx
                                      ? pp
                                      : {
                                          ...pp,
                                          components: (pp.components ?? []).map((c, ci) =>
                                            ci === mi ? { ...c, quantity: Number.isFinite(v) ? v : 1 } : c,
                                          ),
                                        },
                                  ),
                                )
                              }}
                            />
                          ),
                        },
                        {
                            title: '操作',
                            width: 260,
                          render: (_: any, rr: any, mi: number) => (
                            <Space>
                              <Button
                                size="small"
                                  disabled={disabled}
                                onClick={() =>
                                  setPhrasePresets((prev) =>
                                      (prev ?? []).map((pp, pi) =>
                                      pi !== idx
                                        ? pp
                                        : {
                                            ...pp,
                                            components: [
                                              ...(pp.components ?? []),
                                              { model_version_id: null, width_cm: 40, height_cm: 50, quantity: 1, spec_text: '', tokens: [] },
                                            ],
                                          },
                                    ),
                                  )
                                }
                              >
                                +行
                              </Button>
                                <Button size="small" disabled={disabled} onClick={() => copyComponentRow(idx, mi)}>
                                复制
                              </Button>
                              <Button
                                size="small"
                                  disabled={disabled || !String(rr?.model_version_id ?? '').trim()}
                                onClick={() => openPresetModal(idx, mi)}
                              >
                                筛选
                              </Button>
                                <Button size="small" disabled={disabled} danger onClick={() => deleteComponentRow(idx, mi)}>
                                删除
                              </Button>
                            </Space>
                          ),
                        },
                      ]}
                    />
                  </Space>
                )
                })()
              )}
            </Card>
          </div>

          {/* 旧的“组件清单（结构化）”已废弃：统一在短语预设内维护组件行清单（支持同模型多尺寸/多数量/筛选变体）。 */}

          <Form layout="vertical" form={form}>
            <Form.Item name="shared_trigger_text" label="描述备注">
              <Input.TextArea rows={2} placeholder="例如：雪尼尔印花，背面纯色（仅备注，不参与解析）" />
            </Form.Item>
          </Form>
        </Space>
      </Drawer>
    </div>
  )
}


