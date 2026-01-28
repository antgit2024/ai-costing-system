import {
  Alert,
  Button,
  Card,
  Checkbox,
  Col,
  Descriptions,
  Drawer,
  Image,
  Input,
  message,
  Modal,
  Tabs,
  Row,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  Upload,
} from 'antd'
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table'
import dayjs from 'dayjs'
import { useEffect, useMemo, useRef, useState } from 'react'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import {
  autoBindSkuMastersExecute,
  autoBindSkuMastersPreview,
  bindSkuMastersByBundleTemplate,
  bindSkuMastersByBundleTemplateBulk,
  bindSkuMastersByModel,
  bindSkuMastersByModelBulk,
  fetchPublishedStandardModels,
  fetchBundleTemplates,
  fetchSkuMaster,
  fetchSkuMasterDetail,
  importSkuMasterXlsx,
} from '@/services/planner'
import type { PublishedStandardModelCandidate, SkuMaster, SkuMasterAutoBindPreviewItem } from '@/types/planner'

const { Title, Text } = Typography

const DEFAULT_PAGE_SIZE = 100
const PAGE_SIZE_STORAGE_KEY = 'costing_sku_master_page_size_v1'

type ChipPalette = { bg: string; border: string; text: string }
const MODEL_CHIP_PALETTES: ChipPalette[] = [
  { bg: '#eff6ff', border: '#60a5fa', text: '#1d4ed8' }, // blue
  { bg: '#ecfeff', border: '#22d3ee', text: '#0e7490' }, // cyan
  { bg: '#ecfdf5', border: '#34d399', text: '#047857' }, // green
  { bg: '#fff7ed', border: '#fb923c', text: '#c2410c' }, // orange
  { bg: '#f5f3ff', border: '#a78bfa', text: '#6d28d9' }, // purple
  { bg: '#fdf2f8', border: '#f472b6', text: '#be185d' }, // pink
]

const hashCode = (s: string): number => {
  let h = 0
  for (let i = 0; i < s.length; i += 1) h = (h * 31 + s.charCodeAt(i)) | 0
  return Math.abs(h)
}

const renderModelChip = (modelCode?: string | null, modelName?: string | null) => {
  const code = safeString(modelCode).trim()
  const name = safeString(modelName).trim()
  if (!code && !name) return null
  const key = code || name
  const p = MODEL_CHIP_PALETTES[hashCode(key) % MODEL_CHIP_PALETTES.length]
  return (
    <Tag
      style={{
        marginInlineEnd: 0,
        borderRadius: 999,
        padding: '0 8px',
        lineHeight: '20px',
        fontSize: 12,
        background: p.bg,
        borderColor: p.border,
        color: p.text,
      }}
    >
      {[code, name].filter(Boolean).join(' ')}
    </Tag>
  )
}

const formatTime = (v?: string | null) => {
  if (!v) return '-'
  const d = dayjs(v)
  return d.isValid() ? d.format('YYYY-MM-DD HH:mm:ss') : String(v)
}

const safeString = (v: unknown): string => {
  if (v === null || v === undefined) return ''
  return String(v)
}

const isFilled = (v?: string | null) => !!(v && String(v).trim())

const jsonPretty = (obj: unknown) => {
  try {
    return JSON.stringify(obj ?? {}, null, 2)
  } catch {
    return String(obj ?? '')
  }
}

const SkuMasterWorkspacePage = () => {
  const queryClient = useQueryClient()

  const initialUrl = useMemo(() => {
    try {
      if (typeof window === 'undefined') return { search: '', tab: '' }
      const p = new URLSearchParams(window.location.search)
      return {
        search: String(p.get('search') ?? '').trim(),
        tab: String(p.get('tab') ?? '').trim(),
      }
    } catch {
      return { search: '', tab: '' }
    }
  }, [])

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
  const [search, setSearch] = useState<string>(initialUrl.search || '')
  const [includeTerms, setIncludeTerms] = useState<string>('')
  const [excludeTerms, setExcludeTerms] = useState<string>('')
  const [matchScope, setMatchScope] = useState<'spec' | 'name'>('spec')
  const [channel, setChannel] = useState<string | undefined>(undefined)
  const [matchStatus, setMatchStatus] = useState<string | undefined>(undefined)
  const [listTab, setListTab] = useState<'all' | 'unbound' | 'bound'>(
    initialUrl.tab === 'all' || initialUrl.tab === 'unbound' || initialUrl.tab === 'bound'
      ? (initialUrl.tab as any)
      : 'all',
  )
  const [selectedRowKeys, setSelectedRowKeys] = useState<string[]>([])

  const [uploading, setUploading] = useState(false)
  const [uploadFile, setUploadFile] = useState<File | null>(null)
  const [requestedBy, setRequestedBy] = useState<string>('') // 操作人/审核人（可选）
  const [importDrawerOpen, setImportDrawerOpen] = useState(false)

  const [drawerOpen, setDrawerOpen] = useState(false)
  const [activeId, setActiveId] = useState<string | null>(null)

  // left workbench（映射工作台）
  const [workbenchTab, setWorkbenchTab] = useState<'auto' | 'manual'>('manual')
  const [modelSearch, setModelSearch] = useState<string>('')
  const [selectedModelId, setSelectedModelId] = useState<string | undefined>(undefined)
  const [targetKind, setTargetKind] = useState<'model' | 'bundle'>('model')
  const [bundleSearch, setBundleSearch] = useState<string>('')
  const [selectedBundleTemplateId, setSelectedBundleTemplateId] = useState<string | undefined>(undefined)
  const [selectedBundlePresetSelector, setSelectedBundlePresetSelector] = useState<string | undefined>(undefined)
  const [autoPreviewText, setAutoPreviewText] = useState<string>('')
  const [autoPreviewCandidates, setAutoPreviewCandidates] = useState<SkuMasterAutoBindPreviewItem[]>([])
  const [autoCandidatesOnly, setAutoCandidatesOnly] = useState(false)
  const [allowRebind, setAllowRebind] = useState(false)
  const [autoRunAllRunning, setAutoRunAllRunning] = useState(false)
  const autoRunAllStopRef = useRef(false)
  const [autoRunAllStatus, setAutoRunAllStatus] = useState<{
    round: number
    last_bound: number
    total_bound: number
    remaining: number
    last_update: string
    note?: string
  } | null>(null)

  // manual run-all (人工审核：对勾选项分批循环绑定，避免一次性超时)
  const [manualRunAllRunning, setManualRunAllRunning] = useState(false)
  const manualRunAllStopRef = useRef(false)
  const [manualBulkMode, setManualBulkMode] = useState(false) // 默认：当页勾选模式；可切到“所有页勾选（跨页）”
  const [manualExcludedIds, setManualExcludedIds] = useState<string[]>([]) // 取消勾选=加入排除
  const [manualRunAllStatus, setManualRunAllStatus] = useState<{
    round: number
    last_bound: number
    total_bound: number
    processed: number
    total: number
    errors: number
    last_update: string
    note?: string
  } | null>(null)

  // NOTE: URL 预填（search/tab）已在 useState 初始化阶段完成，避免“先显示→几秒后清空”的闪烁体验。

  useEffect(() => {
    try {
      localStorage.setItem(PAGE_SIZE_STORAGE_KEY, String(pageSize))
    } catch {
      // ignore
    }
  }, [pageSize])

  // Tab 切换：重置分页，避免“第一页空白”的错觉
  useEffect(() => {
    setPage(1)
  }, [listTab])

  const listQuery = useQuery({
    queryKey: [
      'sku-master',
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
        // 口径：
        // - 已绑定：模型绑定 或 套装绑定 任一存在即可
        // - 未绑定：模型未绑 且 套装未绑
        target_kind: listTab === 'bound' ? 'any' : undefined,
        bound_state: listTab === 'bound' ? 'all' : listTab === 'unbound' ? 'unbound' : undefined,
        bundle_bound_state: listTab === 'unbound' ? 'unbound' : undefined,
      }),
    placeholderData: keepPreviousData,
    enabled: !autoCandidatesOnly, // 命中候选视图时不依赖服务端分页列表
    retry: 0,
  })

  const listQueryErrorText = useMemo(() => {
    const e: any = listQuery.error
    const detail = e?.response?.data?.detail
    const msg = e?.message
    return String(detail ?? msg ?? '').trim()
  }, [listQuery.error])

  // listEmptyHint 需要在 filteredItems/total 计算之后定义（避免 TDZ）

  const items = autoCandidatesOnly
    ? autoPreviewCandidates.map((x) => ({
        id: x.sku_master_id,
        erp_sku_barcode: x.erp_sku_barcode,
        channel: x.channel ?? null,
        spec_text: x.spec_text ?? null,
        // 预览候选本身就是未绑定
        active_model_version_id: null,
        // 用于表格展示“匹配模型（预览）”
      })) as any[]
    : listQuery.data?.items ?? []
  const _splitTerms = (s: string) =>
    (s || '')
      .split(/\s+/g)
      .map((x) => x.trim())
      .filter(Boolean)
  const _normText = (s: any) => String(s ?? '').replace(/\s+/g, '').toUpperCase()

  const filteredItems = useMemo(() => {
    let rows = items

    // 普通列表：全部交给后端（避免分页“空页”）
    if (!autoCandidatesOnly) return rows

    // 候选视图：做本地快速筛选（输入即生效）
    const qRaw = (search || '').trim()
    const q = _normText(qRaw)
    if (q) {
      rows = rows.filter((x) => {
        const barcode = _normText(x.erp_sku_barcode)
        const spec = _normText(x.spec_text)
        const ch = _normText(x.channel)
        return barcode.includes(q) || spec.includes(q) || ch.includes(q)
      })
    }

    const inc = _splitTerms(includeTerms)
    if (inc.length) {
      rows = rows.filter((x) => {
        const spec = _normText(x.spec_text)
        return inc.every((t) => spec.includes(_normText(t)))
      })
    }

    const exc = _splitTerms(excludeTerms)
    if (exc.length) {
      rows = rows.filter((x) => {
        const spec = _normText(x.spec_text)
        return exc.every((t) => !spec.includes(_normText(t)))
      })
    }

    return rows
  }, [autoCandidatesOnly, items, search, includeTerms, excludeTerms])

  const total = autoCandidatesOnly ? filteredItems.length : listQuery.data?.total ?? 0

  const listEmptyHint = useMemo(() => {
    if (autoCandidatesOnly) {
      return filteredItems.length === 0 ? '命中候选视图为空：请先点左侧“候选预览（命中）”，或退出候选视图查看完整列表。' : ''
    }
    if (listQuery.isFetching) return ''
    return filteredItems.length === 0
      ? '当前筛选结果为空：请清空“候选筛选/包含关键词/排除关键词”，并确认 Tab（全部/未绑定/已绑定）选择是否符合预期。'
      : ''
  }, [autoCandidatesOnly, filteredItems.length, listQuery.isFetching])

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

  const pageStats = useMemo(() => {
    const rows = filteredItems
    const totalRows = rows.length
    const erpMatched = rows.filter((x) => isFilled(x.match_status)).length
    const linked = rows.filter((x: any) => {
      const hasModel = isFilled(x.active_model_version_id as any)
      const hasBundle = isFilled((x as any)?.bundle_template_code ?? (x as any)?.metadata_json?.bundle_template_code)
      return hasModel || hasBundle
    }).length
    const complete = rows.filter((x) => {
      // MVP: “字段齐全” = 条码 + 渠道 + 名称 + 编码 + 规格 + 商家编码 + 平台商品Id + 平台规格Id
      return (
        isFilled(x.erp_sku_barcode) &&
        isFilled(x.channel) &&
        isFilled(x.product_name) &&
        isFilled(x.product_code) &&
        isFilled(x.spec_text) &&
        isFilled(x.shop_spec_code) &&
        isFilled(x.platform_product_id) &&
        isFilled(x.platform_sku_id)
      )
    }).length
    const rate = (n: number) => (totalRows ? `${Math.round((n / totalRows) * 1000) / 10}%` : '-')
    return {
      totalRows,
      erpMatched,
      linked,
      complete,
      erpMatchedRate: rate(erpMatched),
      linkedRate: rate(linked),
      completeRate: rate(complete),
    }
  }, [filteredItems])

  const detailQuery = useQuery({
    queryKey: ['sku-master', 'detail', activeId],
    queryFn: () => fetchSkuMasterDetail(activeId as string),
    enabled: !!activeId && drawerOpen,
  })

  const columns: ColumnsType<SkuMaster> = [
    {
      title: '货品条码（系统）',
      dataIndex: 'erp_sku_barcode',
      width: 140,
      ellipsis: true,
      render: (v) => safeString(v) || '-',
    },
    {
      title: '销售渠道',
      dataIndex: 'channel',
      width: 110,
      ellipsis: true,
      render: (v) => safeString(v) || '-',
    },
    {
      title: '商家编码',
      dataIndex: 'shop_spec_code',
      width: 160,
      ellipsis: true,
      render: (v, record) => safeString(v ?? (record.metadata_json as any)?.shop_spec_code) || '-',
    },
    {
      title: '商品规格（网店）',
      dataIndex: 'spec_text',
      width: 560,
      ellipsis: false,
      render: (v) => {
        const s = safeString(v) || '-'
        return <span style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{s}</span>
      },
    },
    // “模型提示”对业务侧噪声较大：已移到详情抽屉；列表仅展示“已绑定模型(名称)”或“预览匹配模型”
    ...(autoCandidatesOnly
      ? [
    {
            title: '匹配模型（预览）',
            dataIndex: 'id',
            width: 240,
            render: (_: any, record: any) => {
              const hit = autoPreviewCandidates.find((x) => x.sku_master_id === record.id)
              if (!hit) return '-'
              return (
                <Space size={6}>
                  {renderModelChip(hit.model_code, hit.model_name)}
                  {hit.match_method ? <Tag>{hit.match_method}</Tag> : null}
                  {hit.matched_keyword ? <Tag color="purple">{hit.matched_keyword}</Tag> : null}
                </Space>
              )
            },
          } as any,
        ]
      : []),
    {
      title: '对接状态（本系统）',
      dataIndex: 'active_model_version_id',
      width: 240,
      render: (v, record) => {
        const modelBound = isFilled(v as any)
        const source = safeString((record.metadata_json as any)?.source)
        const srcTag = source === 'shipment_autobackfill' ? <Tag color="gold">发货回写</Tag> : null
        const bundleCode = safeString((record as any)?.bundle_template_code ?? (record.metadata_json as any)?.bundle_template_code).trim()
        const preset = safeString(
          (record as any)?.bundle_preset_selector ?? (record.metadata_json as any)?.bundle_preset_selector,
        ).trim()
        const bundleDisplay = (() => {
          const code = bundleCode
          const sel = preset
          if (!code) return ''
          const tpl =
            (bundleTemplates as any[]).find(
              (t: any) =>
                String(t?.id ?? '') ===
                String((record as any)?.bundle_template_id ?? (record.metadata_json as any)?.bundle_template_id ?? ''),
            ) ?? (bundleTemplates as any[]).find((t: any) => String(t?.code ?? '').trim() === code)
          const meta = (tpl as any)?.metadata ?? (tpl as any)?.metadata_json ?? tpl ?? {}
          const presets = Array.isArray((meta as any)?.phrase_presets) ? ((meta as any).phrase_presets as any[]) : []
          const p = presets.find((x: any) => String(x?.selector ?? '').trim().toUpperCase() === String(sel || '').trim().toUpperCase())
          const mode = String((p as any)?.mode ?? '').trim()
          const prefix = mode === 'force' ? 'Z' : 'B'
          return sel ? `${prefix}-${code}${String(sel).trim().toUpperCase()}` : `${prefix}-${code}`
        })()
        const bundleTag = bundleCode ? (
          <Tag color="purple">
            套装 {bundleDisplay || bundleCode}
          </Tag>
        ) : null
        const anyBound = modelBound || !!bundleCode
        return (
          <Space size={6}>
            {anyBound ? <Tag color="green">已关联</Tag> : <Tag color="red">未关联</Tag>}
            {record.spec_mismatch ? <Tag color="orange">规格差异</Tag> : null}
            {renderModelChip(record.bound_model_code, record.bound_model_name)}
            {bundleTag}
            {srcTag}
          </Space>
        )
      },
    },
    {
      title: '最后更新时间',
      dataIndex: 'updated_at',
      width: 170,
      render: (v) => formatTime(v),
    },
    {
      title: '原始最后更新时间（ERP）',
      dataIndex: 'source_updated_at',
      width: 170,
      render: (v) => formatTime(v),
    },
    {
      title: '操作',
      key: 'actions',
      width: 90,
      render: (_, record) => (
        <Button
          size="small"
          onClick={() => {
            setActiveId(record.id)
            setDrawerOpen(true)
          }}
        >
          查看
        </Button>
      ),
    },
  ]

  const handlePaginationChange = (pagination: TablePaginationConfig) => {
    setPage(pagination.current ?? 1)
    setPageSize(pagination.pageSize ?? DEFAULT_PAGE_SIZE)
  }

  const handleImport = async () => {
    if (!uploadFile) {
      message.warning('请先选择要导入的 xlsx 文件')
      return
    }
    setUploading(true)
    try {
      const result = await importSkuMasterXlsx({ file: uploadFile, requested_by: requestedBy || undefined })
      message.success(
        `导入完成：total=${result.total} inserted=${result.inserted} updated=${result.updated} skipped=${result.skipped}`,
      )
      setUploadFile(null)
      await queryClient.invalidateQueries({ queryKey: ['sku-master', 'list'] })
    } catch (e: any) {
      message.error(e?.message || '导入失败')
    } finally {
      setUploading(false)
    }
  }

  const candidatesQuery = useQuery({
    queryKey: ['sku-master', 'published-standard-models', modelSearch],
    queryFn: () => fetchPublishedStandardModels({ search: modelSearch || undefined, limit: 50 }),
    placeholderData: keepPreviousData,
  })

  const bundleTemplatesQuery = useQuery({
    queryKey: ['bundle-templates', 'list', bundleSearch],
    queryFn: () => fetchBundleTemplates({ search: bundleSearch || undefined, page: 1, page_size: 50 }),
    placeholderData: keepPreviousData,
  })

  const bundleTemplates = useMemo(() => {
    const items = (bundleTemplatesQuery.data as any)?.items
    return Array.isArray(items) ? (items as any[]) : []
  }, [bundleTemplatesQuery.data])

  const modelOptions = useMemo(() => {
    const items = (candidatesQuery.data as any)?.items ?? []
    return (items as PublishedStandardModelCandidate[]).map((m) => ({
      // 绑定时总是落到“已发布标准版本”，这里不必展示版本号，降低噪声
      label: `${m.model_code} ${m.model_name}`,
      value: m.model_id,
    }))
  }, [candidatesQuery.data])

  const modelLabelById = useMemo(() => {
    const m = new Map<string, string>()
    for (const it of modelOptions) m.set(String(it.value), String(it.label))
    return m
  }, [modelOptions])

  const bundleTemplateOptions = useMemo(() => {
    return (bundleTemplates as any[]).map((t) => ({
      label: `${safeString(t.code)} ${safeString(t.name)}`.trim(),
      value: String(t.id),
    }))
  }, [bundleTemplates])

  const bundleTemplateLabelById = useMemo(() => {
    const m = new Map<string, string>()
    for (const it of bundleTemplateOptions) m.set(String(it.value), String(it.label))
    return m
  }, [bundleTemplateOptions])

  const bundlePresetsForSelectedTemplate = useMemo(() => {
    if (!selectedBundleTemplateId) return []
    const hit = (bundleTemplates as any[]).find((x) => String(x?.id) === String(selectedBundleTemplateId))
    const meta = (hit?.metadata ?? hit?.metadata_json ?? {}) as any
    const pp = Array.isArray(meta?.phrase_presets) ? meta.phrase_presets : []
    // BundleTemplatesPage has a migration: if top-level components exist but no preset components, map to preset A.
    if (!pp.length) {
      return [{ selector: 'AA', phrase: '默认', mode: 'parse', enabled: true }]
    }
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
    // When template changes, default to the first enabled preset.
    const first = (bundlePresetsForSelectedTemplate as any[]).find((x) => x?.enabled !== false) ?? bundlePresetsForSelectedTemplate?.[0]
    const sel = String((first as any)?.selector ?? '').trim().toUpperCase()
    setSelectedBundlePresetSelector(sel || undefined)
  }, [targetKind, selectedBundleTemplateId, bundlePresetsForSelectedTemplate])

  const bindMutation = useMutation({
    mutationFn: async () => {
      const chunk = <T,>(arr: T[], size: number) => {
        const out: T[][] = []
        for (let i = 0; i < arr.length; i += size) out.push(arr.slice(i, i + size))
        return out
      }

      if (targetKind === 'bundle') {
        if (!selectedBundleTemplateId) throw new Error('请选择套装模板')
        if (!selectedBundlePresetSelector) throw new Error('请选择套装二级（preset）')
        // 说明：plannerClient 默认 20s；勾选量大时容易前端超时。
        // 这里按 200/批自动分批，避免单次请求过大。
        const ids = [...selectedRowKeys]
        const batches = chunk(ids, 200)
        let totalSelected = 0
        let bound = 0
        let skipped = 0
        const errors: any[] = []
        for (const batch of batches) {
          const res = await bindSkuMastersByBundleTemplate(
            {
              template_id: selectedBundleTemplateId,
              preset_selector: selectedBundlePresetSelector,
              sku_master_ids: batch,
              requested_by: requestedBy || undefined,
              allow_rebind: allowRebind,
            },
            { timeoutMs: 60_000 },
          )
          totalSelected += Number(res?.total_selected || 0)
          bound += Number(res?.bound_count || 0)
          skipped += Number(res?.skipped_already_bound || 0)
          errors.push(...((res?.errors ?? []) as any[]))
        }
        return { total_selected: totalSelected, bound_count: bound, skipped_already_bound: skipped, errors }
      }
      if (!selectedModelId) throw new Error('请选择模型')
      {
        const ids = [...selectedRowKeys]
        const batches = chunk(ids, 200)
        let totalSelected = 0
        let bound = 0
        let skipped = 0
        const errors: any[] = []
        for (const batch of batches) {
          const res = await bindSkuMastersByModel(
            {
              model_id: selectedModelId,
              sku_master_ids: batch,
              requested_by: requestedBy || undefined,
              allow_rebind: allowRebind,
            },
            { timeoutMs: 60_000 },
          )
          totalSelected += Number(res?.total_selected || 0)
          bound += Number(res?.bound_count || 0)
          skipped += Number(res?.skipped_already_bound || 0)
          errors.push(...((res?.errors ?? []) as any[]))
        }
        return { total_selected: totalSelected, bound_count: bound, skipped_already_bound: skipped, errors }
      }
    },
    onSuccess: async (res: any) => {
      message.success(
        `绑定完成：bound=${res.bound_count} skipped(bound)=${res.skipped_already_bound} errors=${(res.errors ?? []).length}`,
      )
      setSelectedRowKeys([])
      await queryClient.invalidateQueries({ queryKey: ['sku-master', 'list'] })
    },
    onError: (e: any) => {
      const status = Number(e?.response?.status ?? 0)
      const msg = String(e?.message ?? '')
      const isTimeout = msg.toLowerCase().includes('timeout') || String(e?.code ?? '').toUpperCase() === 'ECONNABORTED'
      if (isTimeout) {
        message.error('绑定请求超时：后端可能仍在执行，请稍后点“刷新”确认是否已绑定（大批量建议用“一键跑完”）')
        return
      }
      if (status === 405) {
        message.error('绑定失败（405）：线上后端尚未部署“套装绑定”接口，请先发布后端再重试')
        return
      }
      message.error(e?.message || '绑定失败')
    },
  })

  // 人工审核：按筛选条件“隐式全选”（跨页）
  // - 默认勾选本页全部
  // - 用户在本页取消勾选 -> 加入排除列表（manualExcludedIds）
  useEffect(() => {
    if (workbenchTab !== 'manual') return
    if (!manualBulkMode) return
    if (autoCandidatesOnly) return
    if (listTab !== 'unbound') return
    const pageIds = (filteredItems as any[]).map((x) => String(x?.id)).filter(Boolean)
    if (!pageIds.length) return
    const excluded = new Set(manualExcludedIds.map((x) => String(x)))
    const nextSelected = pageIds.filter((id) => !excluded.has(id))
    setSelectedRowKeys(nextSelected)
  }, [workbenchTab, manualBulkMode, autoCandidatesOnly, listTab, filteredItems, manualExcludedIds])

  const handleRowSelectionChange = (keys: any[]) => {
    const nextSelected = (keys ?? []).map((x) => String(x))
    if (workbenchTab !== 'manual' || !manualBulkMode || autoCandidatesOnly || listTab !== 'unbound') {
      setSelectedRowKeys(nextSelected)
      return
    }
    const pageIds = (filteredItems as any[]).map((x) => String(x?.id)).filter(Boolean)
    const excluded = new Set(manualExcludedIds.map((x) => String(x)))
    for (const id of pageIds) {
      if (nextSelected.includes(id)) excluded.delete(id)
      else excluded.add(id)
    }
    setManualExcludedIds(Array.from(excluded))
    setSelectedRowKeys(nextSelected)
  }

  const handleManualRunAll = () => {
    if (manualRunAllRunning) return
    if (targetKind === 'bundle') {
      if (!selectedBundleTemplateId) {
        message.warning('请先选择套装模板')
        return
      }
      if (!selectedBundlePresetSelector) {
        message.warning('请先选择套装二级（preset）')
        return
      }
    } else if (!selectedModelId) {
      message.warning('请先选择目标模型（已发布）')
      return
    }
    if (autoCandidatesOnly) {
      message.warning('当前为“命中候选视图”，请先退出候选视图再使用人工审核的一键跑完')
      return
    }
    // 模式A：当页勾选模式（仅处理当前勾选）
    if (!manualBulkMode) {
      if (!selectedRowKeys.length) {
        message.warning('请先在右侧列表勾选要绑定的记录')
        return
      }
      const total = selectedRowKeys.length
      const targetLabel =
        targetKind === 'bundle'
          ? bundleTemplateLabelById.get(String(selectedBundleTemplateId)) || '（未选套装模板）'
          : modelLabelById.get(String(selectedModelId)) || '（未选模型）'
      Modal.confirm({
        title: '确认一键跑完（当页勾选）？',
        content: `将对当前勾选的 ${total} 条记录按 200 条/轮循环绑定到：${targetLabel}（${allowRebind ? '会覆盖已有绑定' : '不会覆盖已有绑定'}）。`,
        okText: '开始执行',
        cancelText: '取消',
        onOk: () => {
          // 关键：不要 await（否则 confirm 弹窗会一直“转圈”不关闭）
          // 点“开始执行”后立即关闭弹窗，后台继续跑；进度/停止在页面里看
          const modelId = selectedModelId
          const templateId = selectedBundleTemplateId
          const presetSelector = selectedBundlePresetSelector
          const idsAll = [...selectedRowKeys]
          const reqBy = requestedBy || undefined

          setManualRunAllRunning(true)
          manualRunAllStopRef.current = false
          setManualRunAllStatus(null)

          void (async () => {
            const BATCH_SIZE = 200
            let cursor = 0
            let totalBound = 0
            let totalErrors = 0

            try {
              for (let round = 1; round <= 999; round += 1) {
                if (manualRunAllStopRef.current) break
                const batch = idsAll.slice(cursor, cursor + BATCH_SIZE)
                if (!batch.length) break

                const ac = new AbortController()
                const timer = window.setTimeout(() => ac.abort(), 45_000)
                let res: any
                try {
                  if (targetKind === 'bundle') {
                    res = await bindSkuMastersByBundleTemplate(
                      {
                        template_id: templateId as string,
                        preset_selector: presetSelector as string,
                        sku_master_ids: batch,
                        requested_by: reqBy,
                        allow_rebind: allowRebind,
                      },
                      { timeoutMs: 45_000, signal: ac.signal },
                    )
                  } else {
                    res = await bindSkuMastersByModel(
                      {
                        model_id: modelId as string,
                        sku_master_ids: batch,
                        requested_by: reqBy,
                        allow_rebind: allowRebind,
                      },
                      { timeoutMs: 45_000, signal: ac.signal },
                    )
                  }
                } finally {
                  window.clearTimeout(timer)
                }

                const bound = Number(res?.bound_count || 0)
                const errors = (res?.errors ?? []).length
                totalBound += bound
                totalErrors += errors
                cursor += batch.length

                const now = new Date()
                const stamp = `${now.getHours().toString().padStart(2, '0')}:${now
                  .getMinutes()
                  .toString()
                  .padStart(2, '0')}:${now.getSeconds().toString().padStart(2, '0')}`
                setManualRunAllStatus({
                  round,
                  last_bound: bound,
                  total_bound: totalBound,
                  processed: cursor,
                  total,
                  errors: totalErrors,
                  last_update: stamp,
                  note: '当页勾选模式：每轮最多 200 条；如需暂停可点“停止”。',
                })

                if (bound === 0) {
                  message.warning('本轮未产生绑定进展（bound=0），已自动停止；可能都已绑定或存在异常')
                  break
                }
              }

              message.success(`人工审核自动绑定完成：累计bound=${totalBound} errors=${totalErrors}`)
              setSelectedRowKeys([])
              if (targetKind === 'model') {
                setListTab('bound')
              }
              setPage(1)
              setPageSize(DEFAULT_PAGE_SIZE)
              await queryClient.invalidateQueries({ queryKey: ['sku-master', 'list'] })
            } catch (e: any) {
              if (String(e?.name || '').toLowerCase().includes('abort')) {
                message.error('单次请求超时（45s）已中止：请稍后重试（或减少勾选量）')
              } else {
                message.error(e?.message || '人工审核自动执行失败')
              }
            } finally {
              setManualRunAllRunning(false)
              manualRunAllStopRef.current = false
            }
          })()
        },
      })
      return
    }

    // 模式B：所有页勾选模式（按筛选条件隐式全选，跨页）
    if (listTab !== 'unbound') {
      message.warning('请先切到“未绑定”列表再执行（避免误操作）')
      return
    }

    const _normConfirm = (s: string) => String(s || '').replace(/\s+/g, ' ').trim()
    const targetLabelRaw =
      targetKind === 'bundle'
        ? bundleTemplateLabelById.get(String(selectedBundleTemplateId)) || ''
        : modelLabelById.get(String(selectedModelId)) || ''
    const targetLabel = _normConfirm(targetLabelRaw)
    const targetNameOnly = _normConfirm(targetLabel.replace(/^\S+\s+/, ''))
    const expected = targetNameOnly || targetLabel || '确认'
    const excludedCount = new Set(manualExcludedIds.map((x) => String(x))).size
    const filterSummary = [
      `关键词：${search ? `“${search}”` : '（空）'}`,
      `包含词：${includeTerms ? `“${includeTerms}”` : '（空）'}`,
      `排除词：${excludeTerms ? `“${excludeTerms}”` : '（空）'}`,
      `范围：${matchScope}`,
      `渠道：${channel || '（全部）'}`,
      `ERP匹配：${matchStatus || '（全部）'}`,
      excludedCount ? `排除：${excludedCount} 条（取消勾选）` : null,
    ]
      .filter(Boolean)
      .join('；')

    let typed = ''
    Modal.confirm({
      title: '确认一键跑完（所有页勾选/跨页）？',
      content: (
        <div>
          <div style={{ marginBottom: 8 }}>
            你当前筛选条件将直接匹配绑定到：<b>{targetLabel || '（未选目标）'}</b>
          </div>
          <div style={{ marginBottom: 8, color: '#666' }}>{filterSummary}</div>
          <div style={{ marginBottom: 8 }}>
            为防误操作，请输入目标名称确认：<b>{expected}</b>
          </div>
          <Input placeholder="请输入上面的目标名称以确认" onChange={(e) => (typed = String(e.target.value || '').trim())} />
          <div style={{ marginTop: 8, color: '#999' }}>
            所有页勾选模式：视为“全选筛选结果（跨页）”，你在本页取消勾选的条目会加入“排除列表”，不会写入绑定。
          </div>
        </div>
      ),
      okText: '开始执行',
      cancelText: '取消',
      onOk: () => {
        const typed2 = _normConfirm(typed)
        const ok =
          typed2 === _normConfirm(expected) || typed2 === _normConfirm(targetLabel) || typed2 === _normConfirm(targetNameOnly)
        if (!ok) {
          message.error('确认输入不一致，已取消执行')
          return Promise.reject(new Error('confirm mismatch'))
        }

        // 关键：不要 await（否则 confirm 弹窗会一直“转圈”不关闭）
        // 点“开始执行”后立即关闭弹窗，后台继续跑；进度/停止在页面里看
        const modelId = selectedModelId
        const templateId = selectedBundleTemplateId
        const presetSelector = selectedBundlePresetSelector
        const reqBy = requestedBy || undefined
        const fSearch = search || undefined
        const fChannel = channel
        const fMatchStatus = matchStatus
        const fIncludeTerms = includeTerms || undefined
        const fExcludeTerms = excludeTerms || undefined
        const fMatchScope = matchScope
        const excluded = [...manualExcludedIds]

        setManualRunAllRunning(true)
        manualRunAllStopRef.current = false
        setManualRunAllStatus(null)

        void (async () => {
          let totalBound = 0
          let totalErrors = 0
          let totalProcessed = 0

          try {
            for (let round = 1; round <= 999; round += 1) {
              if (manualRunAllStopRef.current) break

              const ac = new AbortController()
              const timer = window.setTimeout(() => ac.abort(), 45_000)
              let res: any
              try {
                if (targetKind === 'bundle') {
                  res = await bindSkuMastersByBundleTemplateBulk(
                    {
                      template_id: templateId as string,
                      preset_selector: presetSelector as string,
                      requested_by: reqBy,
                      limit: 200,
                      allow_rebind: allowRebind,
                      search: fSearch,
                      channel: fChannel,
                      match_status: fMatchStatus,
                      include_terms: fIncludeTerms,
                      exclude_terms: fExcludeTerms,
                      match_scope: fMatchScope as any,
                      excluded_sku_master_ids: excluded,
                    },
                    { timeoutMs: 45_000, signal: ac.signal },
                  )
                } else {
                  res = await bindSkuMastersByModelBulk(
                    {
                      model_id: modelId as string,
                      requested_by: reqBy,
                      limit: 200,
                      allow_rebind: allowRebind,
                      search: fSearch,
                      channel: fChannel,
                      match_status: fMatchStatus,
                      include_terms: fIncludeTerms,
                      exclude_terms: fExcludeTerms,
                      match_scope: fMatchScope,
                      excluded_sku_master_ids: excluded,
                    },
                    { timeoutMs: 45_000, signal: ac.signal },
                  )
                }
              } finally {
                window.clearTimeout(timer)
              }

              const bound = Number(res?.bound_count || 0)
              const errors = (res?.errors ?? []).length
              const processedThisRound = Number(res?.batch_candidates || 0)
              const hasMore = Boolean(res?.has_more)
              totalBound += bound
              totalErrors += errors
              totalProcessed += processedThisRound

              const now = new Date()
              const stamp = `${now.getHours().toString().padStart(2, '0')}:${now
                .getMinutes()
                .toString()
                .padStart(2, '0')}:${now.getSeconds().toString().padStart(2, '0')}`
              setManualRunAllStatus({
                round,
                last_bound: bound,
                total_bound: totalBound,
                processed: totalProcessed,
                total: -1,
                errors: totalErrors,
                last_update: stamp,
                note: hasMore ? '仍有更多候选（跨页）' : '已无更多候选',
              })

              if (processedThisRound <= 0) break
              if (!hasMore) break
              if (bound === 0) {
                message.warning('本轮未产生绑定进展（bound=0），已自动停止；可能存在缺条码/条件过宽/排除过多')
                break
              }
            }

            message.success(`人工审核自动绑定完成：累计bound=${totalBound} errors=${totalErrors}`)
            setSelectedRowKeys([])
            setManualExcludedIds([])
            if (targetKind === 'model') {
              setListTab('bound')
            }
            setPage(1)
            setPageSize(DEFAULT_PAGE_SIZE)
            await queryClient.invalidateQueries({ queryKey: ['sku-master', 'list'] })
          } catch (e: any) {
            if (String(e?.name || '').toLowerCase().includes('abort')) {
              message.error('单次请求超时（45s）已中止：请稍后重试（或缩小筛选范围/分批执行）')
            } else {
              message.error(e?.message || '人工审核自动执行失败')
            }
          } finally {
            setManualRunAllRunning(false)
            manualRunAllStopRef.current = false
          }
        })()
      },
    })
  }

  const autoPreviewMutation = useMutation({
    mutationFn: () => autoBindSkuMastersPreview({ limit: 200, scan_limit: 50000 }),
    onSuccess: (res: any) => {
      setAutoPreviewText(`未绑定≈${res.total_unbound} 可自动=${res.candidates}（展示${(res.items ?? []).length}）`)
      const cand = (res.items ?? []) as SkuMasterAutoBindPreviewItem[]
      setAutoPreviewCandidates(cand)
      const idSet = new Set(cand.map((x) => x.sku_master_id))
      setAutoCandidatesOnly(true)
      setListTab('unbound')
      // 让右侧尽量展示“命中候选”（200条）
      setPage(1)
      setPageSize(100)
      setSelectedRowKeys(Array.from(idSet))
      message.success('已生成预览')
    },
    onError: (e: any) => message.error(e?.message || '预览失败'),
  })

  const autoExecuteMutation = useMutation({
    mutationFn: () => {
      if (!selectedRowKeys.length) throw new Error('请先在右侧列表勾选要绑定的记录（可先点预览自动全选）')
      // 仅绑定“预览命中候选”中被勾选的
      const allow = new Set(autoPreviewCandidates.map((x) => x.sku_master_id))
      const ids = selectedRowKeys.filter((id) => allow.has(id))
      if (!ids.length) throw new Error('当前勾选项不在“自动命中候选”中，不会执行绑定')
      return autoBindSkuMastersExecute({ limit: 200, requested_by: requestedBy || undefined, sku_master_ids: ids })
    },
    onSuccess: async (res: any) => {
      message.success(
        `自动绑定完成：bound=${res.bound_count} skipped(bound)=${res.skipped_already_bound} errors=${(res.errors ?? []).length}`,
      )
      setAutoPreviewText(
        `未绑定≈${res.preview?.total_unbound} 可自动=${res.preview?.candidates}（展示${(res.preview?.items ?? []).length}）`,
      )
      const cand = (res.preview?.items ?? []) as SkuMasterAutoBindPreviewItem[]
      setAutoPreviewCandidates(cand)
      // 执行完后：跳到“已绑定”列表（便于看到刚绑定的记录），并重置分页避免出现空白第一页
      setAutoCandidatesOnly(false)
      setSelectedRowKeys([])
      setListTab('bound')
      setPage(1)
      setPageSize(DEFAULT_PAGE_SIZE)
      await queryClient.invalidateQueries({ queryKey: ['sku-master', 'list'] })
    },
    onError: (e: any) => message.error(e?.message || '执行失败'),
  })

  const handleAutoExecuteAll = () => {
    if (!autoPreviewCandidates.length) {
      message.warning('请先点一次“候选预览（命中）”生成候选列表')
      return
    }
    const allow = new Set(autoPreviewCandidates.map((x) => x.sku_master_id))
    const ids = selectedRowKeys.filter((id) => allow.has(id))
    if (!ids.length) {
      message.warning('当前未选中候选（可先预览自动全选，或手动勾选右侧候选）')
      return
    }
    Modal.confirm({
      title: '确认执行自动绑定？',
      content: `将对“命中候选视图”中当前选中的 ${ids.length} 条记录执行绑定（不会覆盖已有绑定）。`,
      okText: '确认执行',
      cancelText: '取消',
      onOk: () => autoExecuteMutation.mutate(),
    })
  }

  const handleAutoRunAll = () => {
    if (autoRunAllRunning) return
    Modal.confirm({
      title: '一键跑完：自动绑定所有可命中候选？',
      content:
        '将自动循环执行：预览→绑定→再预览… 直到没有候选为止（不会覆盖已有绑定）。建议在无人操作时执行。',
      okText: '开始执行',
      cancelText: '取消',
      onOk: () => {
        // 关键：不要 await（否则 confirm 弹窗会一直“转圈”不关闭）
        // 点“开始执行”后立即关闭弹窗，后台继续跑；进度/停止在页面里看
        const reqBy = requestedBy || undefined
        setAutoRunAllRunning(true)
        autoRunAllStopRef.current = false
        void (async () => {
          let totalBound = 0
          let totalSkipped = 0
          let totalErrors = 0
          try {
            // 口径：后端 execute 默认 scan_limit=50000（路由层固定）；为避免单次绑定过大导致超时，
            // 这里每轮只执行小批量（200），循环多轮跑完。
            for (let round = 1; round <= 999; round += 1) {
              if (autoRunAllStopRef.current) break
              // 前端侧加一个“单次请求超时”保护，避免长时间无反馈造成“看起来死了”的错觉
              const ac = new AbortController()
              const timer = window.setTimeout(() => ac.abort(), 45_000)
              let res: any
              try {
                res = await autoBindSkuMastersExecute({
                  limit: 200,
                  requested_by: reqBy,
                  // 不传 sku_master_ids：由后端按 preview 的 items 批量绑定
                } as any)
              } finally {
                window.clearTimeout(timer)
              }
              const bound = Number(res?.bound_count || 0)
              const skipped = Number(res?.skipped_already_bound || 0)
              const errors = (res?.errors ?? []).length
              totalBound += bound
              totalSkipped += skipped
              totalErrors += errors

              const nextItems = (res?.preview?.items ?? []) as any[]
              const now = new Date()
              const stamp = `${now.getHours().toString().padStart(2, '0')}:${now
                .getMinutes()
                .toString()
                .padStart(2, '0')}:${now.getSeconds().toString().padStart(2, '0')}`
              setAutoRunAllStatus({
                round,
                last_bound: bound,
                total_bound: totalBound,
                remaining: nextItems.length,
                last_update: stamp,
                note: `每轮最多 200 条；如卡住可点“停止”后再点“一键跑完”继续。`,
              })
              setAutoPreviewText(
                `自动执行中：第${round}轮，本轮绑定=${bound}，累计=${totalBound}，剩余候选≈${nextItems.length}`,
              )

              // 没有候选了，或本轮没有任何绑定进展 -> 结束（避免死循环）
              if (!nextItems.length) break
              if (bound === 0) {
                message.warning('本轮未产生绑定进展（bound=0），已自动停止；可稍后再点“一键跑完”继续')
                break
              }
            }

            message.success(`自动执行完成：累计bound=${totalBound} skipped=${totalSkipped} errors=${totalErrors}`)
            // 执行完后：回到“已绑定”列表，并刷新
            setAutoCandidatesOnly(false)
            setSelectedRowKeys([])
            setListTab('bound')
            setPage(1)
            setPageSize(DEFAULT_PAGE_SIZE)
            await queryClient.invalidateQueries({ queryKey: ['sku-master', 'list'] })
          } catch (e: any) {
            if (String(e?.name || '').toLowerCase().includes('abort')) {
              message.error('单次请求超时（45s）已中止：请稍后再点“一键跑完”继续（或先降低并发/检查服务负载）')
            } else {
              message.error(e?.message || '自动执行失败')
            }
          } finally {
            setAutoRunAllRunning(false)
            autoRunAllStopRef.current = false
          }
        })()
      },
    })
  }

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between' }}>
        <div>
          <Title level={3} style={{ marginBottom: 4 }}>
            商品关联（SKU 主档）
          </Title>
          <Text type="secondary">
            左侧用于绑定与规则配置，右侧用于筛选与列表查看（统计以当前页为准）。
          </Text>
        </div>
        <Button onClick={() => listQuery.refetch()}>刷新</Button>
      </div>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        {/* 左侧：绑定工作台（1/4） */}
        <Col xs={24} lg={6}>
          <Space direction="vertical" size={12} style={{ width: '100%' }}>
            <Card size="small" title="映射工作台（SKU→标准模型/套装模块）">
              <Tabs
                activeKey={workbenchTab}
                onChange={(k) => setWorkbenchTab(k as any)}
                items={[
                  {
                    key: 'manual',
                    label: '人工审核',
                    children: (
                      <Space direction="vertical" style={{ width: '100%' }}>
                        <Text type="secondary">
                          先选“目标类型”，再选“目标对象”。标准模型会自动落到该模型唯一在线发布版本；套装模块会写入模板绑定（Phase0：存主档 metadata）。
                        </Text>
                        <div style={{ width: '100%' }}>
                          <div style={{ display: 'flex', gap: 8, width: '100%' }}>
                            <Select
                              value={targetKind}
                              options={[
                                { label: '标准模型', value: 'model' },
                                { label: '套装模块', value: 'bundle' },
                              ]}
                              onChange={(v) => {
                                setTargetKind(v as any)
                                setSelectedModelId(undefined)
                                setSelectedBundleTemplateId(undefined)
                                setSelectedBundlePresetSelector(undefined)
                              }}
                              style={{ width: 120 }}
                            />
                            {targetKind === 'bundle' ? (
                              <Select
                                showSearch
                                allowClear
                                placeholder="套装模板"
                                options={bundleTemplateOptions}
                                value={selectedBundleTemplateId}
                                onChange={(v) => setSelectedBundleTemplateId(v)}
                                onSearch={(v) => setBundleSearch(v)}
                                filterOption={false}
                                loading={bundleTemplatesQuery.isFetching}
                                style={{ flex: 1, minWidth: 260 }}
                              />
                            ) : (
                              <Select
                                showSearch
                                allowClear
                                placeholder="目标标准模型（已发布）"
                                options={modelOptions}
                                value={selectedModelId}
                                onChange={(v) => setSelectedModelId(v)}
                                onSearch={(v) => setModelSearch(v)}
                                filterOption={false}
                                loading={candidatesQuery.isFetching}
                                style={{ flex: 1, minWidth: 260 }}
                              />
                            )}
                          </div>
                          {targetKind === 'bundle' ? (
                            <div style={{ marginTop: 8 }}>
                              <Select
                                showSearch
                                allowClear={false}
                                placeholder="套装二级（preset）"
                                options={bundlePresetOptions}
                                value={selectedBundlePresetSelector}
                                onChange={(v) => setSelectedBundlePresetSelector(String(v || '').trim().toUpperCase() || undefined)}
                                filterOption={(input, opt) =>
                                  String(opt?.label ?? '').toUpperCase().includes(String(input ?? '').toUpperCase())
                                }
                                style={{ width: '100%' }}
                                popupMatchSelectWidth={false}
                                dropdownStyle={{ minWidth: 520 }}
                              />
                            </div>
                          ) : null}
                        </div>
                        <Input
                          value={requestedBy}
                          onChange={(e) => setRequestedBy(e.target.value)}
                          placeholder="操作人/审核人（可选）"
                        />
                        <Checkbox checked={allowRebind} onChange={(e) => setAllowRebind(e.target.checked)}>
                          覆盖关联（允许重新绑定）
                        </Checkbox>
                        <Space wrap align="center">
                          <Tag color={manualBulkMode ? 'green' : 'default'}>
                            {manualBulkMode ? '所有页勾选模式（跨页）' : '当页勾选模式'}
                          </Tag>
                          {manualBulkMode && manualExcludedIds.length ? (
                            <Tag color="orange">已排除 {manualExcludedIds.length}</Tag>
                          ) : null}
                          <Button
                            size="small"
                            onClick={() => {
                              setManualBulkMode((v) => !v)
                              setManualExcludedIds([])
                              message.info(manualBulkMode ? '已切换为：当页勾选模式（并清空排除）' : '已切换为：所有页勾选模式（跨页）')
                            }}
                          >
                            切换模式
                          </Button>
                          {manualBulkMode && manualExcludedIds.length ? (
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
                        </Space>
                        <Button
                          block
                          type="primary"
                          disabled={
                            (targetKind === 'bundle'
                              ? !selectedBundleTemplateId || !selectedBundlePresetSelector
                              : !selectedModelId) || selectedRowKeys.length === 0
                          }
                          loading={bindMutation.isPending}
                          onClick={() => bindMutation.mutate()}
                        >
                          执行绑定（仅勾选）{selectedRowKeys.length ? `（${selectedRowKeys.length}）` : ''}
                        </Button>
                        <Button
                          block
                          type="primary"
                          danger
                          disabled={
                            (targetKind === 'bundle'
                              ? !selectedBundleTemplateId || !selectedBundlePresetSelector
                              : !selectedModelId) ||
                            manualRunAllRunning ||
                            bindMutation.isPending
                          }
                          loading={manualRunAllRunning}
                          onClick={handleManualRunAll}
                        >
                          一键跑完（{manualBulkMode ? '所有页' : '当页'}）
                        </Button>
                        {manualRunAllRunning ? (
                          <Button
                            block
                            onClick={() => {
                              manualRunAllStopRef.current = true
                              message.info('已请求停止：将在本轮执行结束后停止')
                            }}
                          >
                            停止自动执行
                          </Button>
                        ) : null}
                        {manualRunAllStatus ? (
                          <Alert
                            type={manualRunAllRunning ? 'info' : 'success'}
                            showIcon
                            message={`进度：第${manualRunAllStatus.round}轮 / 本轮绑定${manualRunAllStatus.last_bound} / 累计绑定${manualRunAllStatus.total_bound} / 已处理≈${manualRunAllStatus.processed} / 错误累计${manualRunAllStatus.errors}`}
                            description={`最后更新：${manualRunAllStatus.last_update}${manualRunAllStatus.note ? `；${manualRunAllStatus.note}` : ''}`}
                          />
                        ) : null}
                        <Text type="secondary">
                          提示：当页模式=完全手动勾选；所有页模式=按筛选条件跨页全选，取消勾选会加入排除（执行前需模型名二次确认）。
                        </Text>
                      </Space>
                    ),
                  },
                  {
                    key: 'auto',
                    label: '自动识别',
                    children: (
                      <Space direction="vertical" style={{ width: '100%' }}>
                        <Text type="secondary">
                          默认规则：仅对可确定命中“已发布标准模型”的未绑定 SKU 自动写入映射。
                        </Text>
                        <Input
                          value={requestedBy}
                          onChange={(e) => setRequestedBy(e.target.value)}
                          placeholder="操作人/审核人（可选）"
                        />
                        <Button
                          block
                          loading={autoPreviewMutation.isPending}
                          onClick={() => autoPreviewMutation.mutate()}
                        >
                          候选预览（命中）
                        </Button>
                        <Button
                          block
                          type="primary"
                          loading={autoExecuteMutation.isPending}
                          onClick={handleAutoExecuteAll}
                        >
                          执行绑定（仅选中候选）
                        </Button>
                        <Button
                          block
                          type="primary"
                          danger
                          disabled={autoRunAllRunning || autoExecuteMutation.isPending || autoPreviewMutation.isPending}
                          loading={autoRunAllRunning}
                          onClick={handleAutoRunAll}
                        >
                          一键跑完（自动循环执行）
                        </Button>
                        {autoRunAllRunning ? (
                          <Button
                            block
                            onClick={() => {
                              autoRunAllStopRef.current = true
                              message.info('已请求停止：将在本轮执行结束后停止')
                            }}
                          >
                            停止自动执行
                          </Button>
                        ) : null}
                        {autoRunAllStatus ? (
                          <Alert
                            type={autoRunAllRunning ? 'info' : 'success'}
                            showIcon
                            message={`进度：第${autoRunAllStatus.round}轮 / 本轮绑定${autoRunAllStatus.last_bound} / 累计绑定${autoRunAllStatus.total_bound} / 剩余候选≈${autoRunAllStatus.remaining}`}
                            description={`最后更新：${autoRunAllStatus.last_update}${autoRunAllStatus.note ? `；${autoRunAllStatus.note}` : ''}`}
                          />
                        ) : null}
                        {autoPreviewText ? <Alert type="info" showIcon message={autoPreviewText} /> : null}
                        {autoCandidatesOnly ? (
                          <Button
                            block
                            onClick={() => {
                              setAutoCandidatesOnly(false)
                              setAutoPreviewCandidates([])
                              setSelectedRowKeys([])
                              // 恢复用户偏好分页（已持久化）
                              setPage(1)
                              message.info('已退出“命中候选”视图')
                            }}
                          >
                            退出命中候选视图
                          </Button>
                        ) : null}
                      </Space>
                    ),
                  },
                ]}
              />
            </Card>

            <Card size="small" title="规则/预设（占位）">
              <Space direction="vertical" style={{ width: '100%' }}>
                <Text type="secondary">后续这里放“规则保存/预设”，避免重复调试。</Text>
                <Button block disabled>
                  新建规则（待接）
                </Button>
                <Button block disabled>
                  管理预设（待接）
                </Button>
              </Space>
            </Card>

            <Card size="small" title="导入/同步（入口）">
              <Space direction="vertical" style={{ width: '100%' }}>
                <Text type="secondary">SKU 主档文件导入建议放到抽屉里，主页面更干净。</Text>
                <Button block onClick={() => setImportDrawerOpen(true)}>
                  上传/导入SKU主档（xlsx）
                </Button>
              </Space>
            </Card>
          </Space>
        </Col>

        {/* 右侧：筛选 + 列表（3/4） */}
        <Col xs={24} lg={18}>
            <Card
            title="候选列表"
            extra={
              <Space wrap>
                {autoCandidatesOnly ? (
                  <Tag color="purple">命中候选视图：{autoPreviewCandidates.length} 条</Tag>
                ) : null}
                <Text type="secondary">
                  状态：
                  {listQuery.isFetching ? '加载中' : listQuery.isError ? '失败' : '就绪'}｜结果 {filteredItems.length}/{total}
                </Text>
                <Input
                  style={{ width: 260 }}
                  placeholder={autoCandidatesOnly ? '候选筛选（本地）：条码/规格/渠道' : '候选筛选：条码/商品名/编码'}
                  value={search}
                  onChange={(e) => {
                    setSearch(e.target.value)
                    setPage(1)
                  }}
                />
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
                  disabled={autoCandidatesOnly}
                />
                <Select
                  allowClear
                  style={{ width: 160 }}
                  placeholder="渠道"
                  options={channelOptions}
                  value={channel}
                  onChange={(v) => {
                    setChannel(v)
                    setPage(1)
                  }}
                  disabled={autoCandidatesOnly}
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
                  disabled={autoCandidatesOnly}
                />
                <Tag color="blue">总数：{total}</Tag>
                <Tag>
                  本页：{pageStats.totalRows} ERP匹配填充率：{pageStats.erpMatchedRate} 对接就绪率：
                  {pageStats.linkedRate} 字段齐全率：{pageStats.completeRate}
                </Tag>
                {/* exit button moved to tabs (after 已绑定) */}
              </Space>
            }
          >
            {autoCandidatesOnly ? (
              <Alert
                type="info"
                showIcon
                style={{ marginBottom: 8 }}
                message="当前为“命中候选视图”：仅展示自动预览命中的候选记录；要看全部/未绑定/已绑定，请点击右上角“退出候选视图”。"
              />
            ) : null}
            {!autoCandidatesOnly && listQuery.isError ? (
              <Alert
                type="error"
                showIcon
                style={{ marginBottom: 8 }}
                message="列表加载失败"
                description={listQueryErrorText || '未知错误（请打开控制台查看网络请求）'}
              />
            ) : null}
            {listEmptyHint ? (
              <Alert type="info" showIcon style={{ marginBottom: 8 }} message="提示" description={listEmptyHint} />
            ) : null}
            <Tabs
              activeKey={listTab}
              onChange={(k) => setListTab(k as any)}
              items={[
                { key: 'all', label: '全部', children: null },
                { key: 'unbound', label: '未绑定', children: null },
                { key: 'bound', label: '已绑定', children: null },
              ]}
              tabBarExtraContent={
                autoCandidatesOnly ? (
                  <Button
                    size="small"
                    type="link"
                    onClick={() => {
                      setAutoCandidatesOnly(false)
                      setAutoPreviewCandidates([])
                      setSelectedRowKeys([])
                      setPage(1)
                      message.info('已退出“命中候选视图”')
                    }}
                  >
                    退出命中候选视图
                  </Button>
                ) : null
              }
            />
            <Table
              rowKey="id"
              size="small"
              loading={listQuery.isFetching}
              columns={columns}
              dataSource={filteredItems}
              rowSelection={{
                selectedRowKeys,
                onChange: (keys) => handleRowSelectionChange(keys as any[]),
              }}
              pagination={{
                current: page,
                pageSize,
                total,
                showSizeChanger: true,
              }}
              onChange={handlePaginationChange}
              scroll={{ x: 1350 }}
            />
          </Card>
        </Col>
      </Row>

      <Drawer
        title="SKU 主档详情（只读）"
        open={drawerOpen}
        width={980}
        onClose={() => {
          setDrawerOpen(false)
          setActiveId(null)
        }}
      >
        {detailQuery.data ? (
          <Row gutter={[16, 16]}>
            <Col span={14}>
              <Descriptions bordered size="small" column={2}>
                <Descriptions.Item label="erp_sku_barcode">
                  {detailQuery.data.erp_sku_barcode}
                </Descriptions.Item>
                <Descriptions.Item label="channel">{detailQuery.data.channel ?? '-'}</Descriptions.Item>
                <Descriptions.Item label="商品名称（网店）" span={2}>
                  {detailQuery.data.product_name ?? '-'}
                </Descriptions.Item>
                <Descriptions.Item label="商品编码（网店）">
                  {detailQuery.data.product_code ?? '-'}
                </Descriptions.Item>
                <Descriptions.Item label="平台商品Id（网店）">
                  {detailQuery.data.platform_product_id ?? '-'}
                </Descriptions.Item>
                <Descriptions.Item label="平台规格Id（网店）">
                  {detailQuery.data.platform_sku_id ?? '-'}
                </Descriptions.Item>
                <Descriptions.Item label="规格编码（网店）/商家编码">
                  {(detailQuery.data as any).shop_spec_code ?? (detailQuery.data.metadata_json as any)?.shop_spec_code ?? '-'}
                </Descriptions.Item>
                <Descriptions.Item label="套装模板绑定">
                  {(() => {
                    const code =
                      (detailQuery.data as any).bundle_template_code ??
                      (detailQuery.data.metadata_json as any)?.bundle_template_code ??
                      ''
                    const sel =
                      (detailQuery.data as any).bundle_preset_selector ??
                      (detailQuery.data.metadata_json as any)?.bundle_preset_selector ??
                      ''
                    const bundleCode = String(code || '').trim()
                    const preset = String(sel || '').trim().toUpperCase()
                    if (!bundleCode) return '-'
                    const tid = String(
                      (detailQuery.data as any).bundle_template_id ??
                        (detailQuery.data.metadata_json as any)?.bundle_template_id ??
                        '',
                    ).trim()
                    const tpl =
                      (bundleTemplates as any[]).find((t: any) => String(t?.id ?? '') === tid) ??
                      (bundleTemplates as any[]).find((t: any) => String(t?.code ?? '').trim() === bundleCode)
                    const meta = (tpl as any)?.metadata ?? (tpl as any)?.metadata_json ?? tpl ?? {}
                    const presets = Array.isArray((meta as any)?.phrase_presets) ? ((meta as any).phrase_presets as any[]) : []
                    const p = presets.find(
                      (x: any) => String(x?.selector ?? '').trim().toUpperCase() === String(preset || '').trim().toUpperCase(),
                    )
                    const mode = String((p as any)?.mode ?? '').trim()
                    const prefix = mode === 'force' ? 'Z' : 'B'
                    return preset ? `${prefix}-${bundleCode}${preset}` : `${prefix}-${bundleCode}`
                  })()}
                </Descriptions.Item>
                <Descriptions.Item label="ERP匹配状态（网店↔ERP）">
                  {detailQuery.data.match_status ?? '-'}
                </Descriptions.Item>
                <Descriptions.Item label="spec_text" span={2}>
                  {detailQuery.data.spec_text ?? '-'}
                </Descriptions.Item>
                <Descriptions.Item label="model_code_hint">
                  {detailQuery.data.model_code_hint ?? '-'}
                </Descriptions.Item>
                <Descriptions.Item label="erp_spec_hash">
                  {detailQuery.data.erp_spec_hash ?? '-'}
                </Descriptions.Item>
                <Descriptions.Item label="对接状态（本系统）">
                  {detailQuery.data.active_model_version_id ? (
                    <Tag color="green">已绑定</Tag>
                  ) : (
                    <Tag color="red">未绑定</Tag>
                  )}
                </Descriptions.Item>
                <Descriptions.Item label="active_model_version_id">
                  {detailQuery.data.active_model_version_id ?? '-'}
                </Descriptions.Item>
                <Descriptions.Item label="已绑定模型">
                  {detailQuery.data.bound_model_code ? (
                    <Space size={6}>
                      <Tag color="blue">{detailQuery.data.bound_model_code}</Tag>
                      <span>{detailQuery.data.bound_model_name || ''}</span>
                    </Space>
                  ) : (
                    '-'
                  )}
                </Descriptions.Item>
                <Descriptions.Item label="已绑定版本">
                  {detailQuery.data.bound_version_label || detailQuery.data.bound_version_kind ? (
                    <Space size={6}>
                      {detailQuery.data.bound_version_kind ? <Tag>{detailQuery.data.bound_version_kind}</Tag> : null}
                      {detailQuery.data.bound_version_status ? (
                        <Tag>{detailQuery.data.bound_version_status}</Tag>
                      ) : null}
                      <span>{detailQuery.data.bound_version_label || '-'}</span>
                    </Space>
                  ) : (
                    '-'
                  )}
                </Descriptions.Item>
                <Descriptions.Item label="规格差异（ERP vs 最近发货）">
                  {detailQuery.data.spec_mismatch ? <Tag color="orange">有差异</Tag> : <Tag>无</Tag>}
                </Descriptions.Item>
                <Descriptions.Item label="last_shipment_spec_hash">
                  {detailQuery.data.last_shipment_spec_hash ?? '-'}
                </Descriptions.Item>
                <Descriptions.Item label="source_updated_at">
                  {formatTime(detailQuery.data.source_updated_at ?? null)}
                </Descriptions.Item>
                <Descriptions.Item label="created_at">
                  {formatTime(detailQuery.data.created_at)}
                </Descriptions.Item>
                <Descriptions.Item label="updated_at">
                  {formatTime(detailQuery.data.updated_at)}
                </Descriptions.Item>
              </Descriptions>
            </Col>
            <Col span={10}>
              <Card size="small" title="图片预览（如有）">
                <Space direction="vertical" style={{ width: '100%' }}>
                  {safeString((detailQuery.data.images_json as any)?.product_image) ? (
                    <Image
                      width={260}
                      src={
                        detailQuery.data?.id
                          ? `/api/planner/sku-master/${encodeURIComponent(String(detailQuery.data.id))}/images/product`
                          : safeString((detailQuery.data.images_json as any)?.product_image)
                      }
                    />
                  ) : (
                    <Text type="secondary">无商品图片</Text>
                  )}
                  {safeString((detailQuery.data.images_json as any)?.spec_image) ? (
                    <Image
                      width={260}
                      src={
                        detailQuery.data?.id
                          ? `/api/planner/sku-master/${encodeURIComponent(String(detailQuery.data.id))}/images/spec`
                          : safeString((detailQuery.data.images_json as any)?.spec_image)
                      }
                    />
                  ) : (
                    <Text type="secondary">无规格图片</Text>
                  )}
                </Space>
              </Card>
              <Card size="small" title="解析摘要（MVP）" style={{ marginTop: 12 }}>
                <Descriptions bordered size="small" column={1}>
                  <Descriptions.Item label="ERP 解析版本">
                    {detailQuery.data.erp_parser_version ?? '-'}
                  </Descriptions.Item>
                  <Descriptions.Item label="ERP 尺寸">
                    {safeString((detailQuery.data.erp_dimensions as any)?.width_cm) ||
                    safeString((detailQuery.data.erp_dimensions as any)?.height_cm) ? (
                      <span>
                        {safeString((detailQuery.data.erp_dimensions as any)?.width_cm) || '?'} ×{' '}
                        {safeString((detailQuery.data.erp_dimensions as any)?.height_cm) || '?'} cm
                      </span>
                    ) : (
                      '-'
                    )}
                  </Descriptions.Item>
                  <Descriptions.Item label="ERP tokens（前10）">
                    {(detailQuery.data.erp_tokens ?? []).slice(0, 10).join('；') || '-'}
                  </Descriptions.Item>
                  <Descriptions.Item label="最近发货规格（如有）">
                    {detailQuery.data.last_shipment_spec_text ?? '-'}
                  </Descriptions.Item>
                  <Descriptions.Item label="规格差异时间">
                    {detailQuery.data.spec_mismatch_at ? formatTime(detailQuery.data.spec_mismatch_at) : '-'}
                  </Descriptions.Item>
                </Descriptions>
              </Card>
              <Card size="small" title="metadata_json" style={{ marginTop: 12 }}>
                <pre style={{ margin: 0, whiteSpace: 'pre-wrap' }}>
                  {jsonPretty(detailQuery.data.metadata_json)}
                </pre>
              </Card>
            </Col>
          </Row>
        ) : detailQuery.isFetching ? (
          <Text>加载中...</Text>
        ) : (
          <Alert type="info" showIcon message="未选择记录" />
        )}
      </Drawer>

      <Drawer
        title="上传/导入 SKU 主档（xlsx）"
        open={importDrawerOpen}
        width={760}
        onClose={() => setImportDrawerOpen(false)}
      >
        <Space direction="vertical" style={{ width: '100%' }} size={12}>
          <Alert
            type="info"
            showIcon
            message="提示"
            description="后续这些主档数据可能会走 API 同步；在此之前可先用 xlsx 做一次性/补量导入。"
          />
          <Space wrap>
            <Upload
              accept=".xlsx"
              beforeUpload={(file) => {
                setUploadFile(file as File)
                return false
              }}
              fileList={uploadFile ? ([{ uid: '1', name: uploadFile.name }] as any) : []}
              onRemove={() => setUploadFile(null)}
              maxCount={1}
            >
              <Button disabled={uploading}>选择xlsx</Button>
            </Upload>
            <Input
              style={{ width: 220 }}
              placeholder="requested_by（可空）"
              value={requestedBy}
              onChange={(e) => setRequestedBy(e.target.value)}
            />
            <Button type="primary" loading={uploading} onClick={handleImport}>
              导入
            </Button>
          </Space>
        </Space>
      </Drawer>
    </div>
  )
}

export default SkuMasterWorkspacePage


