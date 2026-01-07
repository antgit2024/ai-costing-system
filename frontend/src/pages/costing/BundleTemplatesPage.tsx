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
}

type LexiconRuleRow = {
  match_value: string
  target_component_index: number | null
}

type PhrasePresetRow = {
  phrase: string
  mappings: LexiconRuleRow[]
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
  const a = formatBetween(cond.area_between, 'm²')
  const p = formatBetween(cond.perimeter_between, 'm')
  if (w) parts.push(`宽: ${w}`)
  if (h) parts.push(`高: ${h}`)
  if (a) parts.push(`面积: ${a}`)
  if (p) parts.push(`周长: ${p}`)
  return parts.join('；') || '-'
}

const isRuntimeToken = (t: string): boolean => {
  const up = String(t ?? '').trim().toUpperCase()
  return up.startsWith('MODEL:') || up.startsWith('M:') || up.startsWith('BOUND_VERSION:') || up.startsWith('SKU:')
}

const splitTokenCandidates = (raw: string): string[] => {
  const s = String(raw ?? '').trim()
  if (!s) return []
  // support historical "雪尼尔，WB02339" style
  return s
    .replace(/、/g, ',')
    .replace(/，/g, ',')
    .split(',')
    .map((x) => x.trim())
    .filter(Boolean)
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
  const [components, setComponents] = useState<ComponentRow[]>([
    { model_version_id: null, width_cm: 40, height_cm: 50, quantity: 1, spec_text: '' },
  ])
  const [phrasePresets, setPhrasePresets] = useState<PhrasePresetRow[]>([])

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

  const getComponentDisplay = (idx: number, comp?: any): string => {
    const c = comp ?? (components ?? [])[idx]
    const vid = String(c?.model_version_id ?? '').trim()
    const base = vid ? versionIdToModelLabel.get(vid) || vid.slice(0, 8) : '未选模型'
    return `组件${idx + 1}：${base}`
  }

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

  const variableTokenCandidates = useMemo(() => {
    // 从所选版本的“启用变体规则”里提取 TOKEN(any/all) 关键词，供运营复制拼接交易规格。
    const rows = (variantsSummaryQuery.data ?? []) as any[]
    const tokenSet = new Set<string>()
    for (const row of rows) {
      const items = Array.isArray(row?.items) ? row.items : []
      for (const v of items) {
        if (!v?.enabled) continue
        const cond = (v?.conditions ?? {}) as any
        const anyTokens = Array.isArray(cond?.spec_contains_any) ? cond.spec_contains_any : []
        const allTokens = Array.isArray(cond?.spec_contains_all) ? cond.spec_contains_all : []
        for (const raw of [...anyTokens, ...allTokens]) {
          const s0 = String(raw ?? '').trim()
          if (!s0) continue
          if (isRuntimeToken(s0)) continue
          for (const s of splitTokenCandidates(s0)) {
            if (s && !isRuntimeToken(s)) tokenSet.add(s)
          }
        }
      }
    }
    return Array.from(tokenSet).sort((a, b) => a.localeCompare(b, 'zh-Hans-CN'))
  }, [variantsSummaryQuery.data])

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

  // NOTE: “字段映射”的“词”已收口为严格候选选择，不再提供“命中/预演”按钮。

  const openCreate = () => {
    setEditing(null)
    setCreatedTokenHint(null)
    form.setFieldsValue({ name: '', category: '', tags: [], shared_trigger_text: '' })
    setComponents([{ model_version_id: null, width_cm: 40, height_cm: 50, quantity: 1, spec_text: '' }])
    setPresetSelectedByIdx({})
    setPhrasePresets([])
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
    const legacyLabelToIndex = new Map<string, number>()
    rows.forEach((c: any, idx: number) => {
      const lab = String(c?.label ?? '').trim()
      if (lab && !legacyLabelToIndex.has(lab)) legacyLabelToIndex.set(lab, idx)
    })
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
    const vp = (row?.metadata ?? {})?.variant_presets
    if (vp && typeof vp === 'object') {
      setPresetSelectedByIdx(vp as any)
    } else {
      setPresetSelectedByIdx({})
    }
    // NOTE: legacy metadata.lexicon_rules is preserved on save, but UI is intentionally hidden to avoid confusion.

    const pp = (row?.metadata ?? {})?.phrase_presets
    if (Array.isArray(pp)) {
      setPhrasePresets(
        pp
          .map((x: any) => ({
            phrase: String(x?.phrase ?? '').trim(),
            mappings: Array.isArray(x?.mappings)
              ? x.mappings
                  .map((m: any) => ({
                    match_value: String(m?.match_value ?? m?.value ?? '').trim(),
                    target_component_index:
                      typeof m?.target_component_index === 'number'
                        ? m.target_component_index
                        : typeof x?.target_component_index === 'number'
                          ? x.target_component_index
                          : null,
                  }))
                  .filter((m: any) => m.match_value && typeof m.target_component_index === 'number')
              : // backward compatibility: old format {target_component_index,tokens[]}
                Array.isArray(x?.tokens)
                ? (x.tokens as any[])
                    .map((t: any) => {
                      const s = String(t ?? '').trim()
                      if (!s) return null
                      const parts = s.split(':')
                      const mv = parts.length >= 2 ? String(parts.slice(1).join(':')).trim() : s
                      return {
                        match_value: mv,
                        target_component_index: typeof x?.target_component_index === 'number' ? x.target_component_index : null,
                      }
                    })
                    .filter((m: any) => m && m.match_value && typeof m.target_component_index === 'number')
                : [],
          }))
          .filter((x: any) => x.phrase && Array.isArray(x.mappings) && x.mappings.length > 0),
      )
    } else {
      setPhrasePresets([])
    }
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
        variant_presets: presetSelectedByIdx,
        // Preserve legacy lexicon_rules (global fallback mapping) if exists, but do not expose to operators.
        lexicon_rules: Array.isArray((editing?.metadata ?? {})?.lexicon_rules) ? (editing?.metadata ?? {})?.lexicon_rules : [],
        phrase_presets: phrasePresets
          .map((p) => ({
            phrase: String(p.phrase ?? '').trim(),
            mappings: Array.isArray(p.mappings)
              ? p.mappings
                  .map((m) => ({
                    match_value: String(m.match_value ?? '').trim(),
                    target_component_index:
                      typeof m.target_component_index === 'number' && Number.isFinite(m.target_component_index) ? m.target_component_index : undefined,
                  }))
                  .filter((m) => m.match_value && typeof (m as any).target_component_index === 'number')
              : [],
          }))
          .filter((p) => p.phrase && Array.isArray((p as any).mappings) && (p as any).mappings.length > 0),
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
                const selected = (presetSelectedByIdx[presetModalIdx ?? -1] ?? {})[baseLineId] ?? null
                const slot = getLineStructureLabel(base, presetVersionId)
                const baseLabelRaw = String(base?.material_name ?? base?.material_code ?? baseLineId).trim()
                const baseLabel = slot ? `${slot}：${baseLabelRaw}` : baseLabelRaw

                const selectedVariant = selected ? (arr ?? []).find((x: any) => String(x?.id) === String(selected)) : null
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
                      {selected ? (
                        <Space size={6}>
                          <Text type="secondary">{selectedEffect}</Text>
                          {selectedProducedLabels.length ? (
                            <Tag color="green">{selectedProducedLabels.join('、')}</Tag>
                          ) : (
                            <Tag color="green">-</Tag>
                          )}
                          <Tag color="green">已选1条</Tag>
                        </Space>
                      ) : (
                        <Tag>未选</Tag>
                      )}
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

          {/* 已按运营心智收口：不再展示“全局字段映射/可变词列表”，避免误会与绕圈。 */}

          <Alert
            type="info"
            showIcon
            message="短语预设（推荐：把常见交易规格片段定死）"
            description="匹配规则：对客交易规格“包含命中”，并按“更长短语优先”。命中后会执行该短语下的“映射组”（字段/词/目标组件）。"
          />
          <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
            <Button
              type="dashed"
              onClick={() =>
                setPhrasePresets((prev) => [
                  ...prev,
                  { phrase: '', mappings: [{ match_value: '', target_component_index: null }] },
                ])
              }
            >
              新增短语
            </Button>
          </div>
          <Table
            size="small"
            pagination={false}
            rowKey={(_, idx) => `pp-${idx}`}
            dataSource={phrasePresets}
            locale={{ emptyText: '暂无短语：点击上方“新增短语”添加第一条' }}
            expandable={{
              expandedRowKeys: phrasePresets.map((_, idx) => `pp-${idx}`),
              showExpandColumn: false,
              expandedRowRender: (r: any, idx: number) => {
                const mappings = Array.isArray(r?.mappings) ? (r.mappings as any[]) : []
                return (
                  <Space direction="vertical" style={{ width: '100%' }} size={8}>
                    <Table
                      size="small"
                      pagination={false}
                      showHeader={false}
                      rowKey={(_, mi) => `ppm-${idx}-${mi}`}
                      dataSource={mappings}
                      locale={{ emptyText: '暂无映射：点击右侧“+行”添加第一条' }}
                      columns={[
                        {
                          width: 200,
                          render: (_: any, rr: any, mi: number) => (
                            <Select
                              showSearch
                              allowClear
                              placeholder="选择组件（按模型）"
                              style={{ width: '100%' }}
                              value={typeof rr.target_component_index === 'number' ? rr.target_component_index : undefined}
                              options={(components ?? []).map((c, i) => ({
                                value: i,
                                label: getComponentDisplay(i, c),
                              }))}
                              onChange={(v) =>
                                setPhrasePresets((prev) =>
                                  prev.map((x, i) =>
                                    i === idx
                                      ? {
                                          ...x,
                                          mappings: (x.mappings ?? []).map((m, j) =>
                                            j === mi ? { ...m, target_component_index: v == null ? null : Number(v) } : m,
                                          ),
                                        }
                                      : x,
                                  ),
                                )
                              }
                            />
                          ),
                        },
                        {
                          width: 420,
                          render: (_: any, rr: any, mi: number) => (
                            <Select
                              showSearch
                              allowClear
                              placeholder={variableTokenCandidates.length ? '选择变体映射（不可手输）' : '先选目标模型'}
                              style={{ width: '100%' }}
                              value={String(rr.match_value ?? '').trim() || undefined}
                              options={variableTokenCandidates.map((t) => ({ value: t, label: t }))}
                              onChange={(v) =>
                                setPhrasePresets((prev) =>
                                  prev.map((x, i) =>
                                    i === idx
                                      ? {
                                          ...x,
                                          mappings: (x.mappings ?? []).map((m, j) => (j === mi ? { ...m, match_value: String(v ?? '') } : m)),
                                        }
                                      : x,
                                  ),
                                )
                              }
                              disabled={!variableTokenCandidates.length}
                            />
                          ),
                        },
                        {
                          title: '操作',
                          width: 140,
                          render: (_: any, __: any, mi: number) => (
                            <Space>
                              <Button
                                size="small"
                                onClick={() =>
                                  setPhrasePresets((prev) =>
                                    prev.map((x, i) =>
                                      i === idx
                                        ? { ...x, mappings: [...(x.mappings ?? []), { match_value: '', target_component_index: null }] }
                                        : x,
                                    ),
                                  )
                                }
                              >
                                +行
                              </Button>
                              <Button
                                size="small"
                                danger
                                onClick={() =>
                                  setPhrasePresets((prev) =>
                                    prev.map((x, i) =>
                                      i === idx ? { ...x, mappings: (x.mappings ?? []).filter((_, j) => j !== mi) } : x,
                                    ),
                                  )
                                }
                              >
                                删除
                              </Button>
                            </Space>
                          ),
                        },
                      ]}
                    />
                  </Space>
                )
              },
            }}
            columns={[
              {
                title: '短语（运营用，包含命中）',
                render: (_: any, r: any, idx: number) => (
                  <Input
                    placeholder="例如：雪尼尔2个，背面纯色"
                    value={String(r.phrase ?? '')}
                    onChange={(e) => setPhrasePresets((prev) => prev.map((x, i) => (i === idx ? { ...x, phrase: e.target.value } : x)))}
                  />
                ),
              },
              {
                title: '操作',
                width: 140,
                render: (_: any, __: any, idx: number) => (
                  <Space>
                    <Button size="small" danger onClick={() => setPhrasePresets((prev) => prev.filter((_, i) => i !== idx))}>
                      删除
                    </Button>
                  </Space>
                ),
              },
            ]}
          />

          <Alert
            type="info"
            showIcon
            message="组件清单（结构化）"
            description="每行：标准版本 + 宽(cm) + 高(cm) + 数量 + 预设变体筛选/触发词（可选，仅用于命中变体；不会解析尺寸/不会改变模板尺寸）。"
          />

          <Table
            size="small"
            pagination={false}
            rowKey={(_, idx) => `c-${idx}`}
            dataSource={components}
            expandable={{
              expandedRowKeys: (components ?? []).map((_, idx) => `c-${idx}`),
              showExpandColumn: false,
              expandedRowRender: (r: any, idx: number) => {
                const versionId = String(r?.model_version_id ?? '').trim()
                return (
                  <Space direction="vertical" size={6} style={{ width: '100%' }}>
                    <div>
                      <Button size="small" onClick={() => openPresetModal(idx)} disabled={!versionId}>
                        预设变体筛选…
                      </Button>
                      <Text type="secondary" style={{ marginLeft: 8 }}>
                        {versionId ? '（按物料行挑变体 → 只看结果 → 一键填充触发词）' : '（请先选择模型版本）'}
                      </Text>
                    </div>

                    {(() => {
                      const sel = (presetSelectedByIdx[idx] ?? {}) as Record<string, string | null>
                      const selectedEntries = Object.entries(sel).filter(([, v]) => !!v)
                      if (!versionId || !selectedEntries.length) return null

                      const variantsForVersion = ((variantsSummaryQuery.data ?? []) as any[]).find(
                        (x: any) => String(x?.version_id ?? '') === versionId,
                      )?.items as any[]
                      const variants = Array.isArray(variantsForVersion) ? variantsForVersion : []
                      const variantsById = new Map<string, any>()
                      for (const v of variants) {
                        if (v?.id) variantsById.set(String(v.id), v)
                      }

                      const baseMap = baseLineMapByVersion.get(versionId) ?? new Map<string, any>()

                      return (
                        <Space direction="vertical" size={4} style={{ width: '100%' }}>
                          {selectedEntries.map(([baseLineId, variantId]) => {
                            const v = variantsById.get(String(variantId))
                            const base = baseMap.get(String(baseLineId))
                            const slot = getLineStructureLabel(base, versionId)
                            const baseName = String(base?.material_name ?? base?.material_code ?? baseLineId).trim()
                            const baseLabel = slot ? `${slot}：${baseName}` : baseName

                            const effect =
                              v?.action === 'remove_self' ? '移除' : v?.action === 'add_siblings' ? '新增物料' : '替换物料'
                            const produced = Array.isArray(v?.items) ? v.items : []
                            const producedLabels = produced
                              .map((it: any) => String(it?.material_name ?? it?.material_code ?? '').trim())
                              .filter(Boolean)
                              .slice(0, 6)
                            const trigger = formatTrigger(v?.conditions)

                            return (
                              <div key={`${baseLineId}:${variantId}`}>
                                <Space wrap size={6}>
                                  <Text strong>{baseLabel}</Text>
                                  <Text type="secondary">变体表达式：</Text>
                                  <Text type="secondary">{trigger}</Text>
                                  <Text type="secondary">{effect}：</Text>
                                  {producedLabels.length ? (
                                    <Tag color="green">{producedLabels.join('、')}</Tag>
                                  ) : (
                                    <Tag color="green">-</Tag>
                                  )}
                                </Space>
                              </div>
                            )
                          })}
                        </Space>
                      )
                    })()}
                  </Space>
                )
              },
            }}
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
                    <Button
                      size="small"
                      danger
                      disabled={components.length <= 1}
                      onClick={() => {
                        setComponents((prev) => prev.filter((_, i) => i !== idx))
                        setPresetSelectedByIdx((prev) => {
                          const next: Record<number, Record<string, string | null>> = {}
                          for (const [k, v] of Object.entries(prev ?? {})) {
                            const i = Number(k)
                            if (!Number.isFinite(i)) continue
                            if (i === idx) continue
                            next[i > idx ? i - 1 : i] = v as any
                          }
                          return next
                        })
                      }}
                    >
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


