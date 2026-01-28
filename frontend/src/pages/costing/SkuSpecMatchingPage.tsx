import { Alert, Button, Card, Checkbox, Col, Descriptions, Input, InputNumber, Modal, Row, Select, Space, Table, Tabs, Tag, Typography, message } from 'antd'
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table'
import dayjs from 'dayjs'
import { useEffect, useMemo, useRef, useState } from 'react'
import { keepPreviousData, useMutation, useQuery } from '@tanstack/react-query'

import {
  bulkSaveSkuMasterSpecPreparse,
  executeSkuMasterSpecPreparse,
  fetchBundleTemplates,
  fetchPublishedStandardModels,
  fetchSkuMaster,
  parseSpec,
  previewSkuMasterSpecPreparse,
  saveSkuMasterSpecPreparse,
} from '@/services/planner'
import type { SkuMaster, SpecParseResponse } from '@/types/planner'

const { Title, Text } = Typography

const DEFAULT_PAGE_SIZE = 100
const PAGE_SIZE_STORAGE_KEY = 'costing_sku_spec_matching_page_size_v1'

const formatTime = (v?: string | null) => {
  if (!v) return '-'
  const d = dayjs(v)
  return d.isValid() ? d.format('YYYY-MM-DD HH:mm:ss') : String(v)
}

const safeString = (v: unknown): string => {
  if (v === null || v === undefined) return ''
  return String(v)
}

const isFilled = (v: unknown): boolean => !!safeString(v).trim()

const dimGet = (dims: any, key: string): string => {
  const v = dims?.[key]
  if (v === null || v === undefined || v === '') return '-'
  return String(v)
}

const tokensPreview = (tokens: any): string => {
  if (!Array.isArray(tokens) || tokens.length === 0) return '-'
  const parts = tokens.slice(0, 3).map((t) => String(t ?? '').trim()).filter(Boolean)
  const more = tokens.length > 3 ? '…' : ''
  return parts.length ? `${parts.join(' / ')}${more}` : '-'
}

export default function SkuSpecMatchingPage() {
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(() => {
    try {
      const raw = localStorage.getItem(PAGE_SIZE_STORAGE_KEY)
      const n = raw ? Number(raw) : NaN
      if (!Number.isFinite(n) || n <= 0) return DEFAULT_PAGE_SIZE
      return Math.min(Math.max(Math.floor(n), 10), 500)
    } catch {
      return DEFAULT_PAGE_SIZE
    }
  })

  const [search, setSearch] = useState<string>('')
  const [includeTerms, setIncludeTerms] = useState<string>('')
  const [excludeTerms, setExcludeTerms] = useState<string>('')
  const [matchScope, setMatchScope] = useState<'spec' | 'name'>('spec')
  const [channel, setChannel] = useState<string | undefined>(undefined)
  const [matchStatus, setMatchStatus] = useState<string | undefined>(undefined)
  const [modelSearch, setModelSearch] = useState<string>('')
  const [boundModelId, setBoundModelId] = useState<string | undefined>(undefined)
  const [onlyPublishedVersion, setOnlyPublishedVersion] = useState<boolean>(false)
  const [targetKind, setTargetKind] = useState<'any' | 'model' | 'bundle'>('any')
  const [bundleSearch, setBundleSearch] = useState<string>('')
  const [selectedBundleTemplateId, setSelectedBundleTemplateId] = useState<string | undefined>(undefined)
  const [selectedBundlePresetSelector, setSelectedBundlePresetSelector] = useState<string | undefined>(undefined)
  const [forceOverride, setForceOverride] = useState<boolean>(false)

  const [activeSku, setActiveSku] = useState<SkuMaster | null>(null)
  const [specTextDraft, setSpecTextDraft] = useState<string>('')
  const [specParsed, setSpecParsed] = useState<SpecParseResponse | null>(null)
  const [manualWidthCm, setManualWidthCm] = useState<number | null>(null)
  const [manualHeightCm, setManualHeightCm] = useState<number | null>(null)
  const [manualDiameterCm, setManualDiameterCm] = useState<number | null>(null)
  const [bulkLimit, setBulkLimit] = useState<number>(200)
  const [isPreviewMode, setIsPreviewMode] = useState<boolean>(false)
  const [previewItems, setPreviewItems] = useState<any[]>([])
  const [previewSelectedKeys, setPreviewSelectedKeys] = useState<string[]>([])
  const [previewSaved, setPreviewSaved] = useState<boolean>(false)
  const [listTab, setListTab] = useState<'all' | 'parsed' | 'unparsed'>('all')

  // 对齐 /costing/sku-master：“所有页勾选（跨页）”单一模式
  const [manualExcludedIds, setManualExcludedIds] = useState<string[]>([]) // 取消勾选=加入排除
  const [selectedRowKeys, setSelectedRowKeys] = useState<string[]>([]) // 当前页“隐式全选”的可视回显

  // 一键跑完：自循环执行 + 可停止 + 心跳状态
  const [runAllRunning, setRunAllRunning] = useState(false)
  const runAllStopRef = useRef(false)
  const [runAllStatus, setRunAllStatus] = useState<{
    round: number
    last_scanned: number
    last_saved: number
    last_skipped: number
    total_saved: number
    has_more: boolean
    last_update: string
    note?: string
  } | null>(null)

  useEffect(() => {
    try {
      localStorage.setItem(PAGE_SIZE_STORAGE_KEY, String(pageSize))
    } catch {
      // ignore
    }
  }, [pageSize])

  const publishedModelsQuery = useQuery({
    queryKey: ['sku-spec-matching', 'published-standard-models', modelSearch],
    queryFn: () => fetchPublishedStandardModels({ search: modelSearch || undefined, limit: 50 }),
    placeholderData: keepPreviousData,
  })

  const bundleTemplatesQuery = useQuery({
    queryKey: ['sku-spec-matching', 'bundle-templates', 'list', bundleSearch],
    queryFn: () => fetchBundleTemplates({ search: bundleSearch || undefined, page: 1, page_size: 50 }),
    placeholderData: keepPreviousData,
  })

  const bundleTemplates = useMemo(() => {
    const items = (bundleTemplatesQuery.data as any)?.items
    return Array.isArray(items) ? (items as any[]) : []
  }, [bundleTemplatesQuery.data])

  const publishedModelById = useMemo(() => {
    const items = (publishedModelsQuery.data as any)?.items ?? []
    const m = new Map<string, any>()
    for (const it of items) {
      const id = String(it?.model_id ?? '').trim()
      if (!id) continue
      m.set(id, it)
    }
    return m
  }, [publishedModelsQuery.data])

  const bundleTemplateOptions = useMemo(() => {
    return (bundleTemplates as any[])
      .map((t) => ({
        label: `${safeString((t as any)?.code)} ${safeString((t as any)?.name)}`.trim(),
        value: String((t as any)?.id ?? '').trim(),
      }))
      .filter((x) => x.value)
  }, [bundleTemplates])

  const bundlePresetsForSelectedTemplate = useMemo(() => {
    if (!selectedBundleTemplateId) return []
    const hit = (bundleTemplates as any[]).find((x) => String((x as any)?.id ?? '') === String(selectedBundleTemplateId))
    const meta = (hit as any)?.metadata ?? (hit as any)?.metadata_json ?? hit ?? {}
    const pp = Array.isArray((meta as any)?.phrase_presets) ? (meta as any).phrase_presets : []
    if (!pp.length) return [{ selector: 'AA', phrase: '默认', mode: 'parse', enabled: true }]
    return pp
      .map((p: any) => ({
        selector: String(p?.selector ?? '').trim().toUpperCase(),
        phrase: String(p?.phrase ?? '').trim(),
        mode: String(p?.mode ?? 'parse').trim(),
        enabled: p?.enabled !== false,
      }))
      .filter((p: any) => !!p.selector)
  }, [bundleTemplates, selectedBundleTemplateId])

  const bundlePresetOptions = useMemo(() => {
    return (bundlePresetsForSelectedTemplate as any[]).map((p) => {
      const mode = String(p.mode || 'parse').trim() === 'force' ? '指定' : '解析'
      const label = `${p.selector}（${mode}）${p.phrase ? ` ${p.phrase}` : ''}`.trim()
      return { label, value: p.selector }
    })
  }, [bundlePresetsForSelectedTemplate])

  useEffect(() => {
    if (targetKind !== 'bundle') return
    if (!selectedBundleTemplateId) {
      setSelectedBundlePresetSelector(undefined)
      return
    }
    const first =
      (bundlePresetsForSelectedTemplate as any[]).find((x: any) => x?.enabled !== false) ??
      (bundlePresetsForSelectedTemplate as any[])?.[0]
    const sel = String((first as any)?.selector ?? '').trim().toUpperCase()
    setSelectedBundlePresetSelector(sel || undefined)
  }, [targetKind, selectedBundleTemplateId, bundlePresetsForSelectedTemplate])

  useEffect(() => {
    // 目标类型切换时，清理无效筛选，避免“看不见数据”的误解
    if (targetKind === 'model') {
      setSelectedBundleTemplateId(undefined)
      setSelectedBundlePresetSelector(undefined)
    } else if (targetKind === 'bundle') {
      setBoundModelId(undefined)
      setOnlyPublishedVersion(false)
    }
    setPage(1)
  }, [targetKind])

  const boundVersionId = useMemo(() => {
    if (!onlyPublishedVersion || !boundModelId) return undefined
    const hit = publishedModelById.get(String(boundModelId))
    const vid = String(hit?.published_version_id ?? '').trim()
    return vid || undefined
  }, [onlyPublishedVersion, boundModelId, publishedModelById])

  const modelOptions = useMemo(() => {
    const items = (publishedModelsQuery.data as any)?.items ?? []
    return (items as any[])
      .map((m: any) => ({
        label: `${String(m?.model_code ?? '').trim()} ${String(m?.model_name ?? '').trim()}`.trim(),
        value: String(m?.model_id ?? '').trim(),
      }))
      .filter((x: any) => x.value)
  }, [publishedModelsQuery.data])

  const listTargetKind = useMemo(() => {
    if (targetKind === 'bundle') return 'bundle' as const
    if (targetKind === 'model') return 'model' as const
    return 'any' as const
  }, [targetKind])

  const listBundleBoundState = useMemo(() => {
    if (listTargetKind === 'bundle') return 'bound' as const
    return undefined
  }, [listTargetKind])

  const effectivePreparseState = useMemo(() => {
    if (forceOverride) return undefined
    return listTab === 'parsed' ? 'parsed' : listTab === 'unparsed' ? 'unparsed' : undefined
  }, [forceOverride, listTab])

  const listQuery = useQuery({
    queryKey: [
      'sku-spec-matching',
      'list',
      listTab,
      page,
      pageSize,
      search,
      channel,
      matchStatus,
      includeTerms,
      excludeTerms,
      matchScope,
      boundModelId,
      boundVersionId,
      targetKind,
      selectedBundleTemplateId,
      selectedBundlePresetSelector,
      forceOverride,
    ],
    queryFn: () =>
      fetchSkuMaster({
        page,
        page_size: pageSize,
        search: search || undefined,
        channel,
        match_status: matchStatus,
        include_terms: includeTerms || undefined,
        exclude_terms: excludeTerms || undefined,
        match_scope: matchScope,
        target_kind: listTargetKind,
        bound_state: listTargetKind === 'model' ? 'bound' : 'all',
        bound_model_id: boundModelId,
        bound_version_id: boundVersionId,
        bundle_bound_state: listBundleBoundState,
        bundle_template_id: selectedBundleTemplateId,
        bundle_preset_selector: selectedBundlePresetSelector,
        preparse_state: effectivePreparseState,
        // spec-matching 列表不依赖 total；COUNT 代价很高，会导致首屏卡顿
        compute_total: false,
      }),
    placeholderData: keepPreviousData,
  })

  const items = (listQuery.data?.items ?? []) as SkuMaster[]
  const total = listQuery.data?.total ?? 0

  const hasModelAnchor = (row: any) =>
    isFilled(row?.active_model_version_id) || isFilled(row?.bound_model_code) || isFilled(row?.bound_model_name)

  const hasBundleAnchor = (row: any) => {
    const meta = row?.metadata_json ?? {}
    return (
      isFilled(row?.bundle_template_id) ||
      isFilled(row?.bundle_template_code) ||
      isFilled(row?.bundle_preset_selector) ||
      isFilled(meta?.bundle_template_id) ||
      isFilled(meta?.bundle_template_code) ||
      isFilled(meta?.bundle_preset_selector)
    )
  }

  // 关键口径：规格解析工作台只展示“已绑定模型 或 已绑定套装”的 SKU。
  // 说明：后端部署未覆盖/筛选条件过宽时，列表可能返回未绑定项；这里做前端兜底过滤，避免误操作与误解。
  const anchoredItems = useMemo(() => {
    return (items ?? []).filter((r: any) => {
      const m = hasModelAnchor(r)
      const b = hasBundleAnchor(r)
      if (targetKind === 'model') return m
      if (targetKind === 'bundle') return b
      return m || b
    })
  }, [items, targetKind])

  const droppedUnanchoredCount = useMemo(() => {
    if (!items?.length) return 0
    return Math.max(items.length - anchoredItems.length, 0)
  }, [anchoredItems.length, items.length])

  // 锚点变更识别：
  // - 若预解析早于绑定时间（model_bound_at / bundle_bound_at），提示“需重算”
  // - Z/force 套装：预解析缓存使用 "__BUNDLE_FORCE__:template_id:preset" 作为 spec_text_key；
  //   若绑定发生变更，旧 key 会不匹配，需重算以标记最新锚点。
  const isAnchorStale = useMemo(() => {
    const parseIso = (v: any) => {
      const s = safeString(v).trim()
      const t = s ? Date.parse(s) : NaN
      return Number.isFinite(t) ? t : NaN
    }
    const getMeta = (r: any) => (r?.metadata_json ?? {}) as any
    const staleSet = new Set<string>()
    for (const r of anchoredItems as any[]) {
      const id = String(r?.id ?? '')
      if (!id) continue
      const meta = getMeta(r)
      const preAt = parseIso(r?.preparse_saved_at ?? meta?.preparse_saved_at)
      const modelAt = parseIso(meta?.model_bound_at)
      const bundleAt = parseIso(meta?.bundle_bound_at)
      const anchorAt = Math.max(Number.isFinite(modelAt) ? modelAt : 0, Number.isFinite(bundleAt) ? bundleAt : 0)
      let stale = false
      if (Number.isFinite(preAt) && anchorAt > 0 && preAt < anchorAt) stale = true

      const preText = safeString(meta?.preparse_spec_text ?? r?.preparse_spec_text).trim()
      if (preText.startsWith('__BUNDLE_FORCE__:')) {
        const parts = preText.split(':')
        const preTid = parts?.[1] || ''
        const preSel = (parts?.[2] || '').toUpperCase()
        const curTid = safeString(meta?.bundle_template_id ?? r?.bundle_template_id).trim()
        const curSel = safeString(meta?.bundle_preset_selector ?? r?.bundle_preset_selector).trim().toUpperCase()
        if (curTid && curSel && (preTid !== curTid || preSel !== curSel)) stale = true
      }
      if (stale) staleSet.add(id)
    }
    return staleSet
  }, [anchoredItems])

  const staleCount = useMemo(() => isAnchorStale.size, [isAnchorStale.size])

  const tableRows = isPreviewMode ? previewItems : anchoredItems
  const tableTotal = isPreviewMode ? previewItems.length : anchoredItems.length

  // 所有页勾选模式：默认“隐式全选本页（跨页）”，取消勾选=加入排除
  useEffect(() => {
    if (isPreviewMode) return
    if (listTab !== 'unparsed') return
    const pageIds = (items ?? []).map((x) => String((x as any)?.id ?? '')).filter(Boolean)
    if (!pageIds.length) return
    const excluded = new Set(manualExcludedIds.map((x) => String(x)))
    const nextSelected = pageIds.filter((id) => !excluded.has(id))
    setSelectedRowKeys(nextSelected)
  }, [isPreviewMode, listTab, items, manualExcludedIds])

  const handleRowSelectionChange = (keys: any[]) => {
    const nextSelected = (keys ?? []).map((x) => String(x))
    if (isPreviewMode || listTab !== 'unparsed') {
      setSelectedRowKeys(nextSelected)
      return
    }
    const pageIds = (items ?? []).map((x) => String((x as any)?.id ?? '')).filter(Boolean)
    const excluded = new Set(manualExcludedIds.map((x) => String(x)))
    for (const id of pageIds) {
      if (nextSelected.includes(id)) excluded.delete(id)
      else excluded.add(id)
    }
    setManualExcludedIds(Array.from(excluded))
    setSelectedRowKeys(nextSelected)
  }

  const channelOptions = useMemo(() => {
    const set = new Set<string>()
    for (const it of items) {
      const c = safeString(it.channel).trim()
      if (c) set.add(c)
    }
    return Array.from(set)
      .sort()
      .map((c) => ({ label: c, value: c }))
  }, [items])

  const matchStatusOptions = useMemo(() => {
    const set = new Set<string>()
    for (const it of items) {
      const s = safeString(it.match_status).trim()
      if (s) set.add(s)
    }
    return Array.from(set)
      .sort()
      .map((s) => ({ label: s, value: s }))
  }, [items])

  const parseMutation = useMutation({
    mutationFn: (spec_text: string) => parseSpec({ spec_text }),
    onSuccess: (res) => setSpecParsed(res),
    onError: () => setSpecParsed(null),
  })

  const activeAnchors = useMemo(() => {
    const shopSpecCode = safeString((activeSku as any)?.shop_spec_code ?? (activeSku as any)?.metadata_json?.shop_spec_code).trim()
    const bundleTemplateCode = safeString(
      (activeSku as any)?.bundle_template_code ?? (activeSku as any)?.metadata_json?.bundle_template_code,
    ).trim()
    const bundlePresetSelector = safeString(
      (activeSku as any)?.bundle_preset_selector ?? (activeSku as any)?.metadata_json?.bundle_preset_selector,
    )
      .trim()
      .toUpperCase()

    const erpSkuBarcode = safeString((activeSku as any)?.erp_sku_barcode).trim()
    const mode =
      shopSpecCode.toUpperCase().startsWith('Z-') ? 'Z' : shopSpecCode.toUpperCase().startsWith('B-') ? 'B' : undefined

    return { shopSpecCode, bundleTemplateCode, bundlePresetSelector, erpSkuBarcode, mode }
  }, [activeSku])

  const skuMasterJumpUrl = useMemo(() => {
    if (!activeSku) return ''
    const q = activeAnchors.shopSpecCode || activeAnchors.erpSkuBarcode
    if (!q) return '/costing/sku-master'
    // 优先把用户带到“未绑定”视图，便于做绑定/复核；若已绑定也可手动切 TAB。
    return `/costing/sku-master?tab=unbound&search=${encodeURIComponent(q)}`
  }, [activeAnchors.erpSkuBarcode, activeAnchors.shopSpecCode, activeSku])

  const effectiveSpecText = useMemo(() => {
    const s = (specTextDraft || '').trim()
    if (s) return s
    // In preview mode, rows carry `spec_text_used` (computed by backend preview endpoint).
    // Do NOT confuse it with real "last_shipment_spec_text" (shipment snapshot).
    const src = (activeSku as any)?.spec_text_used || activeSku?.last_shipment_spec_text || activeSku?.spec_text || ''
    return String(src || '').trim()
  }, [activeSku, specTextDraft])

  useEffect(() => {
    // 切换行时：默认用“发货规格”优先，其次用 ERP 规格，并清空手工覆写
    setSpecTextDraft('')
    setSpecParsed(null)
    setManualWidthCm(null)
    setManualHeightCm(null)
    setManualDiameterCm(null)
  }, [activeSku?.id])

  useEffect(() => {
    if (!effectiveSpecText) return
    parseMutation.mutate(effectiveSpecText)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [effectiveSpecText])

  const savePreparseMutation = useMutation({
    mutationFn: async () => {
      if (!activeSku?.id) throw new Error('请先选择一条SKU')
      const baseDims = specParsed || ({} as any)
      const width = manualWidthCm != null ? manualWidthCm : baseDims?.width_cm ?? null
      const height = manualHeightCm != null ? manualHeightCm : baseDims?.height_cm ?? null
      const dia = manualDiameterCm != null ? manualDiameterCm : baseDims?.diameter_cm ?? null
      return saveSkuMasterSpecPreparse(activeSku.id, {
        spec_text: effectiveSpecText,
        width_cm: width as any,
        height_cm: height as any,
        diameter_cm: dia as any,
        requested_by: null,
      })
    },
    onSuccess: (res) => {
      message.success('已保存为预解析缓存（用于加速/预填，不影响发货快照口径）')
      // 本地刷新选中行的展示（避免必须手动刷新列表）
      setActiveSku((prev) =>
        prev
          ? ({
              ...prev,
              preparse_spec_hash: res.preparse_spec_hash,
              preparse_dimensions: res.preparse_dimensions,
              preparse_tokens: res.preparse_tokens,
              preparse_saved_at: res.preparse_saved_at ?? null,
              preparse_saved_by: res.preparse_saved_by ?? null,
            } as any)
          : prev,
      )
      listQuery.refetch()
    },
    onError: (err: any) => {
      message.error(err?.response?.data?.detail ?? err?.message ?? '保存失败')
    },
  })

  const previewMutation = useMutation({
    mutationFn: async () => {
      return previewSkuMasterSpecPreparse({
        limit: bulkLimit,
        search: search || undefined,
        channel: channel || undefined,
        match_status: matchStatus || undefined,
        target_kind: listTargetKind,
        bundle_bound_state: listBundleBoundState,
        bundle_template_id: selectedBundleTemplateId,
        bundle_preset_selector: selectedBundlePresetSelector,
        include_terms: includeTerms || undefined,
        exclude_terms: excludeTerms || undefined,
        match_scope: matchScope,
        bound_model_id: boundModelId,
        bound_version_id: boundVersionId,
        // 默认：对齐当前 TAB；若开启“强制覆盖”，允许预览全部（含已解析）
        preparse_state: effectivePreparseState,
      })
    },
    onSuccess: (res) => {
      // 预览模式的行数据需要保留“已落库”的 preparse_* 字段（否则右侧会出现：预览命中→已解析列变未解析 的错觉）
      const baseById = new Map<string, any>()
      for (const r of anchoredItems as any[]) {
        const id = String((r as any)?.id ?? '')
        if (id) baseById.set(id, r)
      }
      const rows = (res.items ?? []).map((x) => {
        const id = String((x as any)?.sku_id ?? '')
        const base = (id && baseById.get(id)) || {}
        const bundleTid = (x as any).bundle_template_id ?? null
        const bundleCode = (x as any).bundle_template_code ?? null
        const bundleSel = (x as any).bundle_preset_selector ?? null
        const baseMeta = ((base as any)?.metadata_json ?? {}) as any
        return {
          ...base,
          id,
          erp_sku_barcode: (x as any).erp_sku_barcode ?? (base as any)?.erp_sku_barcode ?? null,
          channel: (x as any).channel ?? (base as any)?.channel ?? null,
          product_name: (x as any).product_name ?? (base as any)?.product_name ?? null,
          product_code: (x as any).product_code ?? (base as any)?.product_code ?? null,
          spec_text: (x as any).spec_text ?? (base as any)?.spec_text ?? null,
          // keep bundle anchor in preview rows, otherwise it may "flash bound then unbound"
          bundle_template_id: bundleTid ?? (base as any)?.bundle_template_id ?? null,
          bundle_template_code: bundleCode ?? (base as any)?.bundle_template_code ?? null,
          bundle_preset_selector: bundleSel ?? (base as any)?.bundle_preset_selector ?? null,
          bound_model_code: (x as any).bound_model_code ?? (base as any)?.bound_model_code ?? null,
          bound_model_name: (x as any).bound_model_name ?? (base as any)?.bound_model_name ?? null,
          bound_version_label: (x as any).bound_version_label ?? (base as any)?.bound_version_label ?? null,
          // Preview-only: spec text actually used for parsing (shipment-first fallback to shop spec).
          // DO NOT map it into `last_shipment_spec_text` (that field means real shipment snapshot in DB).
          spec_text_used: (x as any).spec_text_used,
          _preview_spec_hash: (x as any).spec_hash,
          _preview_dims: {
            width_cm: (x as any).width_cm ?? null,
            height_cm: (x as any).height_cm ?? null,
            diameter_cm: (x as any).diameter_cm ?? null,
            area_m2: (x as any).area_m2 ?? null,
            perimeter_m: (x as any).perimeter_m ?? null,
          },
          metadata_json: {
            ...baseMeta,
            bundle_template_id: bundleTid ?? baseMeta?.bundle_template_id ?? null,
            bundle_template_code: bundleCode ?? baseMeta?.bundle_template_code ?? null,
            bundle_preset_selector: bundleSel ?? baseMeta?.bundle_preset_selector ?? null,
          },
        }
      })
      setIsPreviewMode(true)
      setPreviewSaved(false)
      setPreviewItems(rows as any[])
      setPreviewSelectedKeys(rows.map((r) => String(r.id)))
      const skippedEmpty = Number((res as any)?.skipped_empty_spec ?? 0)
      const errs = ((res as any)?.errors ?? []) as any[]
      if (skippedEmpty || (errs?.length ?? 0)) {
        message.warning(`预览解析完成：${rows.length} 条（默认全选），跳过空规格${skippedEmpty}，错误${errs?.length ?? 0}`)
      } else {
        message.success(`预览解析完成：${rows.length} 条（默认全选）`)
      }
    },
    onError: (err: any) => {
      message.error(err?.response?.data?.detail ?? err?.message ?? '预览解析失败')
    },
  })

  const executeCandidatesMutation = useMutation({
    mutationFn: async () => {
      const ids = (previewSelectedKeys ?? []).map((x) => String(x)).filter(Boolean)
      if (!ids.length) throw new Error('请先勾选候选')
      // 单次可能较慢：提高超时，避免默认 20s 误判为“跑不动”
      return executeSkuMasterSpecPreparse({ sku_ids: ids, skip_if_same_hash: !forceOverride }, { timeoutMs: 120000 })
    },
    onSuccess: (res: any) => {
      const errs = (res as any)?.errors ?? []
      if (Array.isArray(errs) && errs.length) {
        const first = errs[0] ?? {}
        message.error(`保存失败：${first?.error ?? '未知错误'}`)
        return
      }

      // 预览表格的数据源是 `previewItems`（来自 /preview），它不包含后端落库后的 preparse_* 字段。
      // 为避免“保存成功但表格仍显示未解析”的错觉：在前端用预览结果回填一份 preparse_*，作为回执展示。
      const selected = new Set((previewSelectedKeys ?? []).map((x) => String(x)).filter(Boolean))
      const nowIso = new Date().toISOString()
      setPreviewItems((prev) =>
        (prev ?? []).map((r: any) => {
          const id = String(r?.id ?? '')
          if (!id || !selected.has(id)) return r
          return {
            ...r,
            preparse_spec_hash: r?._preview_spec_hash ?? r?.preparse_spec_hash ?? null,
            preparse_dimensions: r?._preview_dims ?? r?.preparse_dimensions ?? null,
            preparse_tokens: Array.isArray(r?.preparse_tokens) ? r.preparse_tokens : [],
            preparse_saved_at: r?.preparse_saved_at ?? nowIso,
          }
        }),
      )

      const scanned = Number(res?.scanned ?? 0)
      const saved = Number(res?.saved ?? 0)
      const skipped = Number(res?.skipped_same_hash ?? 0)
      const skippedEmpty = Number(res?.skipped_empty_spec ?? 0)
      if (saved > 0) {
        message.success(`保存完成：扫描${scanned}，新增保存${saved}，已存在跳过${skipped}，空规格跳过${skippedEmpty}`)
      } else if (skipped > 0) {
        message.success(`无新增写入：扫描${scanned}，已存在相同规格（跳过${skipped}），空规格跳过${skippedEmpty}`)
      } else {
        message.success(`执行完成：扫描${scanned}（无可保存项；空规格跳过${skippedEmpty}）`)
      }
      setPreviewSaved(true)
      listQuery.refetch()
    },
    onError: (err: any) => {
      message.error(err?.response?.data?.detail ?? err?.message ?? '保存失败')
    },
  })

  const handleRunAllLoop = () => {
    if (runAllRunning) return
    if (listTab !== 'unparsed' && !forceOverride) {
      message.warning('请先切到“未解析”TAB 再执行（避免误操作）；如需重算已解析项，请勾选“强制覆盖”。')
      return
    }

    // 若在候选预览中：把“取消勾选”作为排除，并自动退出预览后再跑全量
    const selected = new Set<string>((previewSelectedKeys ?? []).map((x) => String(x)))
    const excludedFromPreview: string[] = []
    if (isPreviewMode) {
      for (const r of previewItems ?? []) {
        const id = String((r as any)?.id ?? '')
        if (!id) continue
        if (!selected.has(id)) excludedFromPreview.push(id)
      }
    }
    const excludedMerged = Array.from(new Set([...manualExcludedIds, ...excludedFromPreview].map((x) => String(x)).filter(Boolean)))

    const excludedCount = new Set(manualExcludedIds.map((x) => String(x))).size
    const modelLabel = boundModelId
      ? String(
          (publishedModelById.get(String(boundModelId))?.model_code ?? '').toString() +
            ' ' +
            (publishedModelById.get(String(boundModelId))?.model_name ?? '').toString(),
        ).trim()
      : ''
    const filterSummary = [
      `关键词：${search ? `“${search}”` : '（空）'}`,
      `包含词：${includeTerms ? `“${includeTerms}”` : '（空）'}`,
      `排除词：${excludeTerms ? `“${excludeTerms}”` : '（空）'}`,
      `范围：${matchScope}`,
      `渠道：${channel || '（全部）'}`,
      `ERP匹配：${matchStatus || '（全部）'}`,
      `目标：${targetKind === 'bundle' ? '套装模块' : targetKind === 'model' ? '标准模型' : '自动'}`,
      boundModelId ? `模型：${modelLabel || boundModelId}${onlyPublishedVersion ? '（仅当前发布标准版本）' : ''}` : null,
      selectedBundleTemplateId
        ? `套装模板：${selectedBundleTemplateId}${selectedBundlePresetSelector ? `-${selectedBundlePresetSelector}` : ''}`
        : null,
      forceOverride ? '强制覆盖：是（忽略相同Hash）' : null,
      excludedCount ? `排除：${excludedCount} 条（取消勾选）` : null,
    ]
      .filter(Boolean)
      .join('；')

    const expected = '预解析'
    let typed = ''
    Modal.confirm({
      title: '确认一键跑完（自循环执行）？',
      content: (
        <div>
          <div style={{ marginBottom: 8, color: '#666' }}>{filterSummary}</div>
          <div style={{ marginBottom: 8 }}>
            为防误操作，请输入确认词：<b>{expected}</b>
          </div>
          <Input placeholder="请输入上面的确认词以确认" onChange={(e) => (typed = String(e.target.value || '').trim())} />
          <div style={{ marginTop: 8, color: '#999' }}>
            将按筛选条件跨页循环执行；本页取消勾选的条目会加入“排除列表”。若出现“无进展（保存=0且跳过=0）”将自动停止，避免死循环。
          </div>
        </div>
      ),
      okText: '开始执行',
      cancelText: '取消',
      onOk: () => {
        if (String(typed || '').trim() !== expected) {
          message.error('确认输入不一致，已取消执行')
          return Promise.reject(new Error('confirm mismatch'))
        }

        // 开始跑之前：如果来自预览，把排除合并落回 state 并退出预览
        if (excludedMerged.length) setManualExcludedIds(excludedMerged)
        if (isPreviewMode) {
          setIsPreviewMode(false)
          setPreviewItems([])
          setPreviewSelectedKeys([])
          setPreviewSaved(false)
        }

        setRunAllRunning(true)
        runAllStopRef.current = false
        setRunAllStatus(null)

        void (async () => {
          const MESSAGE_KEY = 'spec-preparse-run-all'
          let totalSaved = 0
          let totalSkipped = 0
          let totalSkippedEmpty = 0
          let cursorId: string | undefined = undefined
          let hadError = false
          try {
            for (let round = 1; round <= 999; round += 1) {
              if (runAllStopRef.current) break

              const res = await bulkSaveSkuMasterSpecPreparse({
                limit: bulkLimit,
                search: search || undefined,
                channel: channel || undefined,
                match_status: matchStatus || undefined,
                target_kind: listTargetKind,
                bundle_bound_state: listBundleBoundState,
                bundle_template_id: selectedBundleTemplateId,
                bundle_preset_selector: selectedBundlePresetSelector,
                include_terms: includeTerms || undefined,
                exclude_terms: excludeTerms || undefined,
                match_scope: matchScope,
                bound_model_id: boundModelId,
                bound_version_id: boundVersionId,
                preparse_state: forceOverride ? undefined : 'unparsed',
                cursor_id: cursorId,
                excluded_sku_ids: excludedMerged,
                skip_if_same_hash: !forceOverride,
              }, { timeoutMs: 180000 })

              const scanned = Number((res as any)?.scanned ?? 0)
              const saved = Number((res as any)?.saved ?? 0)
              const skipped = Number((res as any)?.skipped_same_hash ?? 0)
              const skippedEmpty = Number((res as any)?.skipped_empty_spec ?? 0)
              const hasMore = Boolean((res as any)?.has_more)
              const nextCursor = String((res as any)?.next_cursor_id ?? '').trim()
              const errs = ((res as any)?.errors ?? []) as any[]
              totalSaved += saved
              totalSkipped += skipped
              totalSkippedEmpty += skippedEmpty
              if (nextCursor) cursorId = nextCursor

              const now = new Date()
              const stamp = `${now.getHours().toString().padStart(2, '0')}:${now
                .getMinutes()
                .toString()
                .padStart(2, '0')}:${now.getSeconds().toString().padStart(2, '0')}`

              setRunAllStatus({
                round,
                last_scanned: scanned,
                last_saved: saved,
                last_skipped: skipped,
                total_saved: totalSaved,
                has_more: hasMore,
                last_update: stamp,
                note: runAllStopRef.current ? '已请求停止' : hasMore ? '循环中…' : '已无更多',
              })

              message.loading({
                content: `保存中… 第${round}轮：本轮扫描${scanned} / 保存${saved} / 跳过${skipped} / 空规格${skippedEmpty}；累计保存${totalSaved}${hasMore ? '（还有待处理）' : '（已无更多）'}`,
                key: MESSAGE_KEY,
                duration: 0,
              })

              if (Array.isArray(errs) && errs.length) {
                const first = errs[0] ?? {}
                hadError = true
                message.error({ content: `保存失败（已中止）：${first?.error ?? '未知错误'}`, key: MESSAGE_KEY, duration: 5 })
                break
              }
              if (!hasMore) break
              if (saved <= 0 && skipped <= 0 && skippedEmpty <= 0) {
                message.warning({ content: '批量已停止（无进展）：本轮保存=0且跳过=0且空规格=0', key: MESSAGE_KEY, duration: 5 })
                break
              }
            }
          } finally {
            setRunAllRunning(false)
            listQuery.refetch()
            const tail = `批量结束：累计新增保存${totalSaved}，累计相同Hash跳过${totalSkipped}，累计空规格跳过${totalSkippedEmpty}`
            if (hadError) {
              message.error({ content: tail, key: MESSAGE_KEY, duration: 6 })
            } else if (totalSaved > 0) {
              message.success({ content: tail, key: MESSAGE_KEY, duration: 4 })
            } else if (totalSkipped > 0 || totalSkippedEmpty > 0) {
              message.warning({ content: tail, key: MESSAGE_KEY, duration: 5 })
            } else {
              message.info({ content: tail, key: MESSAGE_KEY, duration: 5 })
            }
          }
        })()
      },
    })
  }

  const columns: ColumnsType<any> = useMemo(
    () => [
      {
        title: '货品条码（系统）',
        dataIndex: 'erp_sku_barcode',
        width: 170,
        fixed: 'left',
        render: (v) => {
          const barcode = safeString(v).trim()
          return <Text style={{ fontFamily: 'monospace' }}>{barcode || '-'}</Text>
        },
      },
      { title: '销售渠道', dataIndex: 'channel', width: 120, render: (v) => safeString(v) || '-' },
      {
        title: '已绑定目标',
        key: 'bound_target',
        width: 320,
        render: (_v, row) => {
          const modelCode = safeString((row as any)?.bound_model_code).trim()
          const modelName = safeString((row as any)?.bound_model_name).trim()
          const hasModel = !!modelCode

          const meta = (row as any)?.metadata_json ?? {}
          const codeRaw = safeString((row as any)?.bundle_template_code ?? meta?.bundle_template_code).trim()
          const tid = safeString((row as any)?.bundle_template_id ?? meta?.bundle_template_id).trim()
          const selRaw = safeString((row as any)?.bundle_preset_selector ?? meta?.bundle_preset_selector)
            .trim()
            .toUpperCase()
          const hasBundle = !!codeRaw

          const normalize = (s: string) =>
            String(s || '')
              .trim()
              .toUpperCase()
              .replace(/^([BZ])-/, '')
              .replace(/[^A-Z0-9]/g, '')

          const bundleTag = (() => {
            if (!hasBundle) return null
            const base = normalize(codeRaw)
            const sel = normalize(selRaw)
            const tpl =
              (bundleTemplates as any[]).find((t: any) => String(t?.id ?? '').trim() === tid) ??
              (bundleTemplates as any[]).find((t: any) => normalize(String(t?.code ?? '')) === base) ??
              (bundleTemplates as any[]).find((t: any) => normalize(String(t?.code ?? '')).endsWith(base))
            const tplCode = String((tpl as any)?.code ?? '').trim()
            const tplName = String((tpl as any)?.name ?? '').trim()
            const tplMeta = (tpl as any)?.metadata ?? (tpl as any)?.metadata_json ?? tpl ?? {}
            const presets = Array.isArray((tplMeta as any)?.phrase_presets) ? ((tplMeta as any).phrase_presets as any[]) : []
            const presetHit = presets.find((p: any) => normalize(String(p?.selector ?? '')) === sel)
            const mode = String((presetHit as any)?.mode ?? '').trim()
            const prefix = mode === 'force' || tplCode.toUpperCase().startsWith('Z-') ? 'Z' : 'B'

            let displayBase = base
            if (sel && !displayBase.endsWith(sel)) displayBase = `${displayBase}${sel}`

            const label = `${prefix}-${displayBase}`
            const text = tplName ? `${label} ${tplName}` : label
            return <Tag color="purple">{text}</Tag>
          })()

          if (!hasModel && !bundleTag) return <Tag>未绑定</Tag>

          // 若两者同时存在：同一格里分两行展示，避免混淆口径
          return (
            <Space direction="vertical" size={2}>
              {isAnchorStale.has(String((row as any)?.id ?? '')) ? <Tag color="orange">锚点已变更（需重算）</Tag> : null}
              {hasModel ? (
                <span>
                  <Tag color="blue">{modelCode}</Tag>
                  {modelName ? <span style={{ color: '#666' }}> {modelName}</span> : null}
                </span>
              ) : null}
              {bundleTag}
            </Space>
          )
        },
      },
      { title: '标准版本', dataIndex: 'bound_version_label', width: 120, render: (v) => safeString(v) || '-' },
      {
        title: '商品规格（网店）',
        dataIndex: 'spec_text',
        width: 520,
        render: (v) => (
          <div style={{ whiteSpace: 'normal', wordBreak: 'break-word', lineHeight: 1.2 }}>{safeString(v) || '-'}</div>
        ),
      },
      {
        title: isPreviewMode ? '用于解析的规格（预览）' : '发货规格（优先用于解析）',
        dataIndex: 'last_shipment_spec_text',
        width: 360,
        render: (v, row) => {
          const ship = safeString(v).trim()
          const shop = safeString((row as any)?.spec_text).trim()
          const text = isPreviewMode ? safeString((row as any)?.spec_text_used) : ship || shop
          const shown = text || '-'
          const dims = (row as any)?._preview_dims
          if (!dims) {
            return (
              <div style={{ whiteSpace: 'normal', wordBreak: 'break-word', lineHeight: 1.2 }}>
                <div>{shown}</div>
                {!isPreviewMode && !ship && shop ? <Tag color="orange">回退：网店规格</Tag> : null}
              </div>
            )
          }
          const w = dims?.width_cm ?? '-'
          const h = dims?.height_cm ?? '-'
          return (
            <div style={{ whiteSpace: 'normal', wordBreak: 'break-word', lineHeight: 1.2 }}>
              <div>{shown}</div>
              {!isPreviewMode && !ship && shop ? <Tag color="orange">回退：网店规格</Tag> : null}
              <Tag color="purple" style={{ marginTop: 4 }}>
                解析尺寸：宽{w}cm × 高{h}cm
              </Tag>
            </div>
          )
        },
      },
      {
        title: '预解析尺寸（已落库）',
        dataIndex: 'preparse_dimensions',
        width: 220,
        render: (_v, row) => {
          const dims = (row as any)?.preparse_dimensions
          const hash = (row as any)?.preparse_spec_hash
          if (!hash) return <Tag>未解析</Tag>
          const w = dimGet(dims, 'width_cm')
          const h = dimGet(dims, 'height_cm')
          const hasDims = (row as any)?.preparse_has_dims
          return (
            <Space size={6} wrap>
              <Tag color="geekblue">已解析</Tag>
              {hasDims === false ? <Tag color="orange">无尺寸/定制</Tag> : null}
              <Tag color="purple">
                宽{w}×高{h}cm
              </Tag>
            </Space>
          )
        },
      },
      {
        title: '预解析TOKEN（已落库）',
        dataIndex: 'preparse_tokens',
        width: 220,
        render: (_v, row) => {
          const hash = (row as any)?.preparse_spec_hash
          if (!hash) return <Tag>未解析</Tag>
          const tokens = (row as any)?.preparse_tokens
          const n = Array.isArray(tokens) ? tokens.length : 0
          return (
            <Space size={6} wrap>
              <Tag color="geekblue">tokens:{n}</Tag>
              <span style={{ color: '#666' }}>{tokensPreview(tokens)}</span>
            </Space>
          )
        },
      },
      { title: '宽(cm)(ERP缓存)', dataIndex: 'erp_dimensions', width: 120, render: (dims) => dimGet(dims, 'width_cm') },
      { title: '高(cm)(ERP缓存)', dataIndex: 'erp_dimensions', width: 120, render: (dims) => dimGet(dims, 'height_cm') },
      { title: 'ERP规格Hash', dataIndex: 'erp_spec_hash', width: 160, render: (v) => safeString(v) || '-' },
      { title: '更新时间', dataIndex: 'updated_at', width: 170, render: (v) => formatTime(v as any) },
    ],
    [isPreviewMode],
  )

  const handlePaginationChange = (pagination: TablePaginationConfig) => {
    const nextPage = Number(pagination.current || 1)
    const nextSize = Number(pagination.pageSize || pageSize)
    setPage(nextPage)
    setPageSize(nextSize)
  }

  return (
    <div>
      <Title level={3} style={{ marginTop: 0 }}>
        规格匹配工作台（第一步：尺寸/规格解析）
      </Title>
      <Text type="secondary">
        本页面用于把<strong>交易规格文本</strong>解析成<strong>尺寸(dims)/TOKEN(tokens)</strong>并落库为“预解析缓存”（用于加速/预填，不改变发货快照口径）。
        支持按<strong>模型</strong>或<strong>套装模板+preset</strong>筛选：Z-（指定型）可仅绑定套装后解析；B-（解析型）建议先绑定套装锚点再依赖 TOKEN 做分支。
      </Text>
      <div style={{ marginTop: 8 }}>
        <Button
          type="link"
          style={{ padding: 0 }}
          onClick={() => window.open('/costing/tmall-sku-generator/mvp', '_blank')}
        >
          去“天猫SKU规格生成器（MVP）”做运营前置预检/预演
        </Button>
      </div>

      <Row gutter={[16, 16]} style={{ marginTop: 12 }}>
        {/* 左侧 1/4：解析工作台 */}
        <Col xs={24} lg={6}>
          <Space direction="vertical" style={{ width: '100%' }}>
            <Card
              size="small"
              title="工作台（与商品匹配同款：预览解析 → 保存落库）"
              extra={isPreviewMode ? <Tag color="purple">预览中</Tag> : <Tag>未预览</Tag>}
            >
              <Space wrap>
                <Tag color="purple">模式：自动识别</Tag>
                <Tag color="green">所有页勾选模式（跨页）</Tag>
                {manualExcludedIds.length ? <Tag color="orange">已排除 {manualExcludedIds.length}</Tag> : null}
                {manualExcludedIds.length ? (
                  <Button
                    size="small"
                    onClick={() => {
                      setManualExcludedIds([])
                      message.success('已清空排除列表（本页将重新默认全选）')
                    }}
                  >
                    清空排除
                  </Button>
                ) : null}
                <InputNumber
                  addonBefore="预览数"
                  min={1}
                  max={5000}
                  value={bulkLimit}
                  onChange={(v) => setBulkLimit(typeof v === 'number' ? v : 200)}
                />
                <Button type="primary" loading={previewMutation.isPending} onClick={() => previewMutation.mutate()}>
                  候选预览（命中）
                </Button>
                <Button
                  type="primary"
                  disabled={!isPreviewMode || previewSelectedKeys.length === 0}
                  loading={executeCandidatesMutation.isPending}
                  onClick={() => executeCandidatesMutation.mutate()}
                >
                  执行保存（仅选中候选）
                </Button>
                <Button type="primary" danger loading={runAllRunning} onClick={handleRunAllLoop}>
                  一键跑完（自循环执行）
                </Button>
                {runAllRunning ? (
                  <Button
                    onClick={() => {
                      runAllStopRef.current = true
                      message.info('已请求停止：将在本轮执行结束后停止')
                    }}
                  >
                    停止自动执行
                  </Button>
                ) : null}
                {isPreviewMode ? (
                  <Button
                    onClick={() => {
                      // 退出预览：回到“已解析”视图查看落库结果
                      setIsPreviewMode(false)
                      setPreviewItems([])
                      setPreviewSelectedKeys([])
                      setPreviewSaved(false)
                      setListTab('parsed')
                      setPage(1)
                      listQuery.refetch()
                    }}
                  >
                    退出预览
                  </Button>
                ) : null}
              </Space>
              {isPreviewMode ? (
                <Alert
                  style={{ marginTop: 8 }}
                  type="info"
                  showIcon
                  message={`当前为预览模式：这里只展示上限${bulkLimit}条“候选预览”（默认全选${previewItems.length}条）。你可以：1）点“执行保存（仅选中候选）”仅保存这${previewSelectedKeys.length}条；2）点“一键跑完（自循环执行）”跑完全部筛选结果（跨页全选），你在预览里取消勾选的条目会加入排除。`}
                />
              ) : null}
              {!isPreviewMode && runAllStatus ? (
                <Alert
                  style={{ marginTop: 8 }}
                  type={runAllRunning ? 'info' : 'success'}
                  showIcon
                  message={`心跳：第${runAllStatus.round}轮 / 本轮扫描${runAllStatus.last_scanned} / 保存${runAllStatus.last_saved} / 跳过${runAllStatus.last_skipped} / 累计保存${runAllStatus.total_saved} ${
                    runAllStatus.has_more ? '（还有待处理）' : '（已无更多）'
                  }`}
                  description={`最后更新：${runAllStatus.last_update}${runAllStatus.note ? `；${runAllStatus.note}` : ''}`}
                />
              ) : null}
              {isPreviewMode && previewSaved ? (
                <Alert
                  style={{ marginTop: 8 }}
                  type="success"
                  showIcon
                  message="已落库成功：右侧仍展示本次保存的记录作为回执；点击“退出预览”将自动切到“已解析”TAB。"
                />
              ) : null}
            </Card>

            <Card size="small" title="单条人工审核（可选）">
              {!activeSku ? (
                <Alert type="info" showIcon message="请在右侧列表选择一条已绑定SKU，系统会自动解析尺寸。" />
              ) : (
                <Space direction="vertical" style={{ width: '100%' }}>
                  <Card size="small" title="锚点信息（只读）" style={{ marginBottom: 8 }}>
                    <Space direction="vertical" style={{ width: '100%' }} size={8}>
                      <Space wrap>
                        <Tag color="purple">模式：{activeAnchors.mode ? `${activeAnchors.mode}-` : '未识别'}</Tag>
                        {activeAnchors.shopSpecCode ? (
                          <Tag color="geekblue">商家编码：{activeAnchors.shopSpecCode}</Tag>
                        ) : (
                          <Tag>商家编码：-</Tag>
                        )}
                      </Space>
                      <Space wrap>
                        {activeAnchors.bundleTemplateCode ? (
                          <Tag color="purple">
                            套装：{activeAnchors.bundleTemplateCode}
                            {activeAnchors.bundlePresetSelector ? `-${activeAnchors.bundlePresetSelector}` : ''}
                          </Tag>
                        ) : (
                          <Tag>套装：-</Tag>
                        )}
                        <Button
                          size="small"
                          type="link"
                          disabled={!skuMasterJumpUrl}
                          onClick={() => window.open(skuMasterJumpUrl, '_blank')}
                        >
                          去商品关联（sku-master）绑定/复核
                        </Button>
                      </Space>
                      {activeAnchors.mode === 'Z' ? (
                        <Alert
                          type="success"
                          showIcon
                          message="Z-（指定型）：只需完成套装绑定即可；本页解析主要用于尺寸校验/排查，不依赖 TOKEN 做组件分支。"
                        />
                      ) : activeAnchors.mode === 'B' ? (
                        <Alert
                          type="info"
                          showIcon
                          message="B-（解析型）：先在 sku-master 绑定套装模板+二级 preset（锚点），再用本页解析 TOKEN/尺寸供后续 BOM 分支与对账。"
                        />
                      ) : (
                        <Alert
                          type="warning"
                          showIcon
                          message="未识别 Z/B：建议先在 sku-master 用“商家编码”完成模型/套装绑定；本页仍可解析尺寸/TOKEN 作为排查依据。"
                        />
                      )}
                    </Space>
                  </Card>
                  <Space wrap>
                    <Tag color="green">已绑定</Tag>
                    {activeSku.bound_model_code ? <Tag color="blue">{activeSku.bound_model_code}</Tag> : null}
                    {activeSku.bound_model_name ? <span>{activeSku.bound_model_name}</span> : null}
                  </Space>
                  <Space wrap>
                    <Tag color="purple">模式：人工审核</Tag>
                    {activeSku.preparse_spec_hash ? <Tag color="geekblue">已保存预解析</Tag> : <Tag>未保存</Tag>}
                  </Space>
                  <Text type="secondary">用于解析的规格文本（可手工覆写调试）：</Text>
                  <Input.TextArea
                    rows={4}
                    value={effectiveSpecText}
                    onChange={(e) => setSpecTextDraft(e.target.value)}
                    placeholder="优先发货规格，其次网店规格；你也可以在这里粘贴一段规格文本进行解析"
                  />
                  <Space wrap>
                    <span style={{ color: '#666' }}>人工校对：</span>
                    <InputNumber
                      addonBefore="宽cm"
                      value={manualWidthCm}
                      onChange={(v) => setManualWidthCm(typeof v === 'number' ? v : null)}
                      placeholder={specParsed?.width_cm != null ? String(specParsed.width_cm) : '—'}
                    />
                    <InputNumber
                      addonBefore="高cm"
                      value={manualHeightCm}
                      onChange={(v) => setManualHeightCm(typeof v === 'number' ? v : null)}
                      placeholder={specParsed?.height_cm != null ? String(specParsed.height_cm) : '—'}
                    />
                    <InputNumber
                      addonBefore="直径cm"
                      value={manualDiameterCm}
                      onChange={(v) => setManualDiameterCm(typeof v === 'number' ? v : null)}
                      placeholder={specParsed?.diameter_cm != null ? String(specParsed.diameter_cm) : '—'}
                    />
                    <Button
                      type="primary"
                      loading={savePreparseMutation.isPending}
                      onClick={() => savePreparseMutation.mutate()}
                      disabled={!effectiveSpecText || !activeSku?.id}
                    >
                      保存本条（当前行）
                    </Button>
                  </Space>
                  <Alert
                    type="info"
                    showIcon
                    message="提示：系统会识别“竖/横/宽/高/长”这类带方向的尺寸写法，例如：竖120CM*横150CM → 高=120cm，宽=150cm。"
                    style={{ marginTop: 8 }}
                  />
                  <Descriptions bordered size="small" column={2} style={{ marginTop: 8 }}>
                    <Descriptions.Item label="宽(cm)">{specParsed?.width_cm ?? '-'}</Descriptions.Item>
                    <Descriptions.Item label="高(cm)">{specParsed?.height_cm ?? '-'}</Descriptions.Item>
                    <Descriptions.Item label="直径(cm)">{specParsed?.diameter_cm ?? '-'}</Descriptions.Item>
                    <Descriptions.Item label="面积(m²)">{specParsed?.area_m2 ?? '-'}</Descriptions.Item>
                    <Descriptions.Item label="周长(m)">{specParsed?.perimeter_m ?? '-'}</Descriptions.Item>
                    <Descriptions.Item label="tokens数">{(specParsed?.tokens ?? []).length}</Descriptions.Item>
                  </Descriptions>
                  {activeSku.preparse_saved_at ? (
                    <Text type="secondary">预解析保存时间：{formatTime(activeSku.preparse_saved_at)}</Text>
                  ) : null}
                  <Card size="small" title="解析 tokens（原始分段）" style={{ marginTop: 8 }}>
                    <div style={{ whiteSpace: 'normal', wordBreak: 'break-word', lineHeight: 1.2 }}>
                      {(specParsed?.tokens ?? []).slice(0, 50).map((t, idx) => (
                        <Tag key={`${t}-${idx}`}>{t}</Tag>
                      ))}
                      {(specParsed?.tokens ?? []).length > 50 ? <Tag>…</Tag> : null}
                    </div>
                  </Card>
                  {parseMutation.isPending ? <Text type="secondary">解析中…</Text> : null}
                </Space>
              )}
            </Card>

            <Card size="small" title="后续：变体规则（暂不启用）">
              <Alert
                type="warning"
                showIcon
                message="先完成“尺寸解析”与70%主流程；等进入变体实操阶段，再引入 token 词典与行级变体规则（Overlay）。"
              />
            </Card>
          </Space>
        </Col>

        {/* 右侧 3/4：筛选 + 列表 */}
        <Col xs={24} lg={18}>
          <Card
            title="已绑定SKU列表"
            extra={
              <Space wrap>
                <Input
                  style={{ width: 240 }}
                  placeholder="搜索：条码/商品名/编码"
                  value={search}
                  onChange={(e) => {
                    setSearch(e.target.value)
                    setPage(1)
                  }}
                />
                <Select
                  style={{ width: 150 }}
                  value={targetKind}
                  onChange={(v) => setTargetKind(v as any)}
                  options={[
                    { label: '目标：自动', value: 'any' },
                    { label: '目标：标准模型', value: 'model' },
                    { label: '目标：套装模块', value: 'bundle' },
                  ]}
                />
                {targetKind === 'model' ? (
                  <>
                    <Select
                      showSearch
                      allowClear
                      style={{ width: 240 }}
                      placeholder="按模型过滤（已发布标准）"
                      options={modelOptions}
                      value={boundModelId}
                      onChange={(v) => {
                        setBoundModelId(v)
                        setOnlyPublishedVersion(false)
                        setPage(1)
                      }}
                      onSearch={(v) => setModelSearch(v)}
                      filterOption={false}
                      loading={publishedModelsQuery.isFetching}
                    />
                    <Checkbox
                      checked={onlyPublishedVersion}
                      disabled={!boundModelId}
                      onChange={(e) => {
                        setOnlyPublishedVersion(e.target.checked)
                        setPage(1)
                      }}
                    >
                      仅当前发布标准版本
                    </Checkbox>
                  </>
                ) : null}
                {targetKind === 'bundle' ? (
                  <>
                    <Select
                      showSearch
                      allowClear
                      style={{ width: 240 }}
                      placeholder="按套装模板过滤"
                      options={bundleTemplateOptions}
                      value={selectedBundleTemplateId}
                      onChange={(v) => {
                        setSelectedBundleTemplateId(v)
                        setPage(1)
                      }}
                      onSearch={(v) => setBundleSearch(v)}
                      filterOption={false}
                      loading={bundleTemplatesQuery.isFetching}
                    />
                    <Select
                      allowClear
                      style={{ width: 200 }}
                      placeholder="套装二级(preset)"
                      options={bundlePresetOptions}
                      value={selectedBundlePresetSelector}
                      onChange={(v) => {
                        setSelectedBundlePresetSelector(v)
                        setPage(1)
                      }}
                      disabled={!selectedBundleTemplateId}
                    />
                  </>
                ) : null}
                <Checkbox
                  checked={forceOverride}
                  onChange={(e) => {
                    setForceOverride(e.target.checked)
                    setPage(1)
                  }}
                >
                  强制覆盖
                </Checkbox>
                <Input
                  style={{ width: 220 }}
                  placeholder="包含关键词（AND，多词空格分隔）"
                  value={includeTerms}
                  onChange={(e) => {
                    setIncludeTerms(e.target.value)
                    setPage(1)
                  }}
                />
                <Input
                  style={{ width: 200 }}
                  placeholder="排除关键词（AND NOT）"
                  value={excludeTerms}
                  onChange={(e) => {
                    setExcludeTerms(e.target.value)
                    setPage(1)
                  }}
                />
                <Select
                  style={{ width: 170 }}
                  value={matchScope}
                  onChange={(v) => setMatchScope(v)}
                  options={[
                    { label: '商品规格', value: 'spec' },
                    { label: '商品名称', value: 'name' },
                  ]}
                />
                <Select
                  allowClear
                  style={{ width: 150 }}
                  placeholder="渠道"
                  options={channelOptions}
                  value={channel}
                  onChange={(v) => {
                    setChannel(v)
                    setPage(1)
                  }}
                />
                <Select
                  allowClear
                  style={{ width: 190 }}
                  placeholder="ERP匹配状态（网店↔ERP）"
                  options={matchStatusOptions}
                  value={matchStatus}
                  onChange={(v) => {
                    setMatchStatus(v)
                    setPage(1)
                  }}
                />
                <Tag color="blue">总数：{total}</Tag>
              </Space>
            }
          >
            {!isPreviewMode && droppedUnanchoredCount > 0 ? (
              <Alert
                style={{ marginBottom: 8 }}
                type="warning"
                showIcon
                message={`已隐藏未绑定记录 ${droppedUnanchoredCount} 条（仅展示“已绑定模型或已绑定套装”的 SKU）`}
                description="如需处理这些记录，请先去“商品关联（sku-master）”完成模型/套装锚点绑定后再回到本页解析。"
              />
            ) : null}
            {!isPreviewMode && staleCount > 0 ? (
              <Alert
                style={{ marginBottom: 8 }}
                type="info"
                showIcon
                message={`检测到 ${staleCount} 条记录：预解析早于绑定更新时间 / 或套装锚点已变更`}
                description="建议勾选“强制覆盖”后重新执行“执行保存/一键跑完”，确保预解析缓存与最新锚点一致。"
              />
            ) : null}
            {!isPreviewMode ? (
              <Tabs
                activeKey={listTab}
                onChange={(k) => {
                  setListTab(k as any)
                  setPage(1)
                }}
                items={[
                  { key: 'all', label: '全部' },
                  { key: 'parsed', label: '已解析' },
                  { key: 'unparsed', label: '未解析' },
                ]}
              />
            ) : null}
            <Table
              rowKey="id"
              size="small"
              tableLayout="fixed"
              loading={listQuery.isFetching}
              columns={columns}
              dataSource={tableRows}
              rowSelection={
                isPreviewMode
                  ? {
                      selectedRowKeys: previewSelectedKeys,
                      onChange: (keys) => setPreviewSelectedKeys((keys ?? []) as string[]),
                    }
                  : listTab === 'unparsed'
                    ? {
                        selectedRowKeys,
                        onChange: (keys) => handleRowSelectionChange((keys ?? []) as any[]),
                      }
                    : undefined
              }
              pagination={
                isPreviewMode
                  ? {
                      current: 1,
                      pageSize: tableTotal,
                      total: tableTotal,
                      showSizeChanger: false,
                    }
                  : {
                      current: page,
                      pageSize,
                      total: tableTotal,
                      showSizeChanger: true,
                    }
              }
              onChange={handlePaginationChange}
              onRow={(record) => ({
                onClick: () => setActiveSku(record),
              })}
              rowClassName={(record) => (record.id === activeSku?.id ? 'row-selected' : '')}
              scroll={{ x: 2200 }}
            />
          </Card>
        </Col>
      </Row>
    </div>
  )
}


