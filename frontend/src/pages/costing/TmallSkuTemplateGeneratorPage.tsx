import { useEffect, useMemo, useState } from 'react'
import { Alert, Button, Card, Checkbox, Divider, Drawer, Input, message, Radio, Select, Space, Switch, Table, Tag, Typography, Upload } from 'antd'
import {
  CheckCircleFilled,
  CloseCircleFilled,
  DeleteOutlined,
  DownloadOutlined,
  EyeOutlined,
  PlusOutlined,
  ReloadOutlined,
  SettingOutlined,
  UploadOutlined,
} from '@ant-design/icons'
import * as XLSX from 'xlsx'

import {
  exportTmallSkuTemplateXlsx,
  fetchBundleTemplates,
  fetchBundleTemplateByCode,
  fetchPublishedStandardModels,
  previewTmallSkuTemplate,
  type TmallColorOption,
  type TmallSizeOption,
  type TmallSkuCell,
  type TmallSkuRow,
} from '@/services/planner'

const { Text } = Typography

const uid = () => Math.random().toString(36).slice(2, 10)

const downloadBlob = (blob: Blob, filename: string) => {
  const url = window.URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  window.URL.revokeObjectURL(url)
}

type ColorRow = TmallColorOption & {
  enabledSizes: Record<string, boolean>
  // 绑定“模型/套版”的来源编码（用于生成商家编码）；颜色分类层级优先级最高（覆盖尺寸绑定）
  // 例：PI5 / Z-3U3PAA / B-3U3PAA
  source_code?: string
}

type SizeRow = TmallSizeOption & {
  // 绑定“模型/套版”的来源编码（用于生成商家编码；对客展示仍使用 label）
  // 例：PI5 / YS2 / Z-3U3PAA / B-3U3PAA
  source_code?: string
}

type SourceOptionGroup = { label: string; options: Array<{ label: string; value: string }> }

type BundleTokenMeta = { mode: 'B' | 'Z'; phrase?: string; name?: string }

type BundleTokenInputParsed = {
  modeHint?: 'B' | 'Z'
  templateCode: string
  selector: string
}

const readFileAsArrayBuffer = (file: File): Promise<ArrayBuffer> =>
  new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result as ArrayBuffer)
    reader.onerror = () => reject(reader.error ?? new Error('读取文件失败'))
    reader.readAsArrayBuffer(file)
  })

const normalizeCellText = (v: unknown) => String(v ?? '').replace(/\s+/g, ' ').trim()

const safeUpper = (v: unknown) => String(v ?? '').trim().toUpperCase()

const buildMerchantSku = (args: {
  merchantSkuPrefix: string
  merchantSkuSuffix: string
  sourceCode?: string | null
}) => {
  const prefix = String(args.merchantSkuPrefix ?? '')
  const suffix = String(args.merchantSkuSuffix ?? '')
  const source = String(args.sourceCode ?? '').trim()

  // IMPORTANT: 商家编码里不要拼尺寸（例如 -4545 / 45x45 之类），只保留稳定的绑定锚点。
  if (source) {
    return `${source}${suffix}`.trim()
  }
  return `${prefix}${suffix}`.trim()
}

const parseBundleTokenInput = (raw: string): BundleTokenInputParsed | null => {
  const s0 = String(raw ?? '').trim()
  if (!s0) return null
  const s = s0
    .replace(/^BUNDLE:/i, '')
    .replace(/^B:/i, 'B-')
    .replace(/^Z:/i, 'Z-')
    .trim()

  // accept: B-3U3PAA / Z-3U3PAA / 3U3PAA
  const m = /^([BZ])?-?([0-9A-Z]+?)([A-Z]{2})$/i.exec(s.replace(/\s+/g, '').toUpperCase())
  if (!m) return null
  const modeHint = m[1] ? (m[1].toUpperCase() as 'B' | 'Z') : undefined
  const templateCode = String(m[2] ?? '').toUpperCase()
  const selector = String(m[3] ?? '').toUpperCase()
  if (!templateCode || !selector) return null
  return { modeHint, templateCode, selector }
}

const uniqueKeepOrder = (xs: string[]) => {
  const out: string[] = []
  const seen = new Set<string>()
  for (const x of xs) {
    const k = String(x ?? '')
    if (seen.has(k)) continue
    seen.add(k)
    out.push(k)
  }
  return out
}

const parseBundleAttributeFormula = (formulaRaw: string): { groups: string[][]; dims?: { w: number; h: number } } => {
  const formula = String(formulaRaw ?? '')
  const groups: string[][] = []

  // 1) extract option groups: each `[...]` contains `{a}{b}{}` etc
  for (let i = 0; i < formula.length; i++) {
    if (formula[i] !== '[') continue
    const j = formula.indexOf(']', i + 1)
    if (j < 0) break
    const seg = formula.slice(i + 1, j)
    const opts: string[] = []
    const re = /\{([^}]*)\}/g
    let mm: RegExpExecArray | null
    while ((mm = re.exec(seg))) {
      const t = String(mm[1] ?? '').trim()
      // keep empty option `{}` as '' (means “无/不选”)
      opts.push(t)
    }
    if (opts.length) groups.push(uniqueKeepOrder(opts))
    i = j
  }

  // 2) best-effort dims: find first `w*h*qty` / `w×h×qty`
  const dm = /(\d+(?:\.\d+)?)\s*[*xX×]\s*(\d+(?:\.\d+)?)\s*[*xX×]\s*(\d+(?:\.\d+)?)/.exec(formula)
  const w = dm ? Number(dm[1]) : NaN
  const h = dm ? Number(dm[2]) : NaN
  const dims = Number.isFinite(w) && Number.isFinite(h) ? { w, h } : undefined
  return { groups, dims }
}

const cartesianProduct = (groups: string[][], limit: number): Array<{ tokens: string[] }> => {
  const out: Array<{ tokens: string[] }> = []
  if (!groups.length) return out
  const step = (idx: number, acc: string[]) => {
    if (out.length >= limit) return
    if (idx >= groups.length) {
      out.push({ tokens: acc.slice() })
      return
    }
    const opts = groups[idx] ?? []
    for (const o of opts) {
      acc.push(String(o ?? ''))
      step(idx + 1, acc)
      acc.pop()
      if (out.length >= limit) return
    }
  }
  step(0, [])
  return out
}

const normalizeAttrValue = (v: unknown) => {
  // Normalize for stability when matching:
  // - collapse whitespace
  // - trim
  // - do NOT change punctuation/case (keep user intent)
  return String(v ?? '').replace(/\s+/g, ' ').trim()
}

const fmtNum = (v: unknown): string => {
  if (v === null || v === undefined) return ''
  const n = Number(v)
  if (!Number.isFinite(n)) return ''
  return n.toFixed(2).replace(/\.?0+$/, '')
}

const normalizeHeaderLabel = (v: unknown) => {
  // Make header matching robust across common template variants:
  // - collapse whitespace
  // - convert full-width parentheses
  // - strip any trailing "(必填)/(选填)/..." notes
  const s = String(v ?? '')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/（/g, '(')
    .replace(/）/g, ')')
  // Remove any parenthesized suffix notes, e.g. "颜色分类(必填)" -> "颜色分类"
  return s.replace(/\([^)]*\)\s*$/g, '').trim()
}

type HeaderIndex = {
  headerRowIndex: number
  colorCol: number
  sizeCol: number
  merchantSkuCol: number
  statusCol: number
}

const findHeaderIndex = (ws: XLSX.WorkSheet): HeaderIndex | null => {
  const ref = ws['!ref']
  if (!ref) return null
  const range = XLSX.utils.decode_range(ref)
  for (let r = range.s.r; r <= Math.min(range.e.r, range.s.r + 50); r++) {
    const rowValues: string[] = []
    for (let c = range.s.c; c <= range.e.c; c++) {
      const addr = XLSX.utils.encode_cell({ r, c })
      rowValues.push(normalizeHeaderLabel((ws as any)[addr]?.v))
    }
    const idxIncludesAny = (candidates: string[]) =>
      rowValues.findIndex((x) => candidates.some((k) => x === k || x.includes(k)))

    const colorCol = idxIncludesAny(['颜色分类'])
    const sizeCol = idxIncludesAny(['尺寸'])
    const merchantSkuCol = idxIncludesAny(['商家编码'])
    const statusCol = idxIncludesAny(['是否上架', '上架状态'])
    if ([colorCol, sizeCol, merchantSkuCol, statusCol].every((x) => x >= 0)) {
      return {
        headerRowIndex: r,
        colorCol: range.s.c + colorCol,
        sizeCol: range.s.c + sizeCol,
        merchantSkuCol: range.s.c + merchantSkuCol,
        statusCol: range.s.c + statusCol,
      }
    }
  }
  return null
}

type MainPatternOption = { key: string; label: string }

type PersistedConfigV1 = {
  merchantSkuPrefix: string
  merchantSkuSuffix: string
  sizes: SizeRow[]
  colors: Array<TmallColorOption & { enabledSizes?: Record<string, boolean>; source_code?: string }>
  mainPatternTypes: Array<MainPatternOption & { remark?: string }>
  ui?: {
    enableColorImages?: boolean
    enableSizeImages?: boolean
    enableColorRemarks?: boolean
    enableSizeRemarks?: boolean
    enablePatternRemarks?: boolean
    includeMainPatternType?: boolean
  }
}

const STORAGE_KEY = 'tmall_sku_generator_config_v1'
const STORAGE_PROFILES_KEY = 'tmall_sku_generator_profiles_v1'

const downloadText = (text: string, filename: string) => {
  const blob = new Blob([text], { type: 'text/plain;charset=utf-8' })
  downloadBlob(blob, filename)
}

const copyText = async (text: string) => {
  try {
    await navigator.clipboard.writeText(text)
    message.success('已复制')
  } catch {
    // Fallback for environments without clipboard permission
    const el = document.createElement('textarea')
    el.value = text
    el.style.position = 'fixed'
    el.style.left = '-9999px'
    document.body.appendChild(el)
    el.focus()
    el.select()
    document.execCommand('copy')
    el.remove()
    message.success('已复制')
  }
}

type DisplayMode = 'table' | 'matrix'

type SpecRow = {
  row_key: string
  color_key: string
  size_key: string
  color_label: string
  size_label: string
  merchant_sku: string
  attribute_spec?: string
  token_formula?: string
  spec_text?: string
  sku_status: 0 | 1
  main_pattern_type?: string | null
  length_cm?: string
  thickness_cm?: string
  width_cm?: string
}

type SpecEdits = Record<
  string,
  {
    price?: string
    quantity?: string
    sku_category?: '单品' | '套装'
    barcode?: string
    reserved_qty?: string
    selling_point?: string
    spec_text?: string
  }
>

export default function TmallSkuTemplateGeneratorPage() {
  const [merchantSkuPrefix, setMerchantSkuPrefix] = useState('BZPB008XXXXX-')
  const [merchantSkuSuffix, setMerchantSkuSuffix] = useState('')

  const [sizes, setSizes] = useState<SizeRow[]>([
    { key: 'size_1', label: '枕芯+枕套', size_code: 'C1', source_code: '' },
    { key: 'size_2', label: '枕套', size_code: 'C2', source_code: '' },
  ])

  const [colors, setColors] = useState<ColorRow[]>([
    {
      key: 'c1',
      label: 'Q25122501A黄金绒背面纯色（红色毛球） 45X45',
      width_cm: 45,
      height_cm: 45,
      enabledSizes: { size_1: true, size_2: true },
      source_code: '',
    },
  ])

  const [previewRows, setPreviewRows] = useState<TmallSkuRow[]>([])
  const [previewTotal, setPreviewTotal] = useState(0)
  const [loadingPreview, setLoadingPreview] = useState(false)
  const [loadingExport, setLoadingExport] = useState(false)
  const [templateFile, setTemplateFile] = useState<File | null>(null)
  const [templateSheetNames, setTemplateSheetNames] = useState<string[]>([])
  const [templateSheetName, setTemplateSheetName] = useState<string>('')
  const [loadingFill, setLoadingFill] = useState(false)
  const [overwriteExisting, setOverwriteExisting] = useState(true)
  const [mainPatternTypes, setMainPatternTypes] = useState<MainPatternOption[]>([
    { key: 'p1', label: '无' },
  ])
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [includeMainPatternType, setIncludeMainPatternType] = useState(true)
  const [enableColorImages, setEnableColorImages] = useState(true)
  const [enableSizeImages, setEnableSizeImages] = useState(false)
  const [enableColorRemarks, setEnableColorRemarks] = useState(true)
  const [enableSizeRemarks, setEnableSizeRemarks] = useState(true)
  const [enablePatternRemarks, setEnablePatternRemarks] = useState(false)
  const [displayMode, setDisplayMode] = useState<DisplayMode>('table')
  const [specEdits, setSpecEdits] = useState<SpecEdits>({})
  const [rowValidation, setRowValidation] = useState<Record<string, { ok: boolean; issues: string[] }>>({})

  // Bundle-template assisted generation (B/Z) for token-driven Tmall attributes
  const [bundleTokenInput, setBundleTokenInput] = useState<string>('B-3U3PAA')
  const [bundleLoading, setBundleLoading] = useState(false)
  const [bundlePresetMode, setBundlePresetMode] = useState<'B' | 'Z' | null>(null)
  const [bundlePresetPhrase, setBundlePresetPhrase] = useState<string>('')
  const [bundleGroups, setBundleGroups] = useState<string[][]>([])
  const [bundleDims, setBundleDims] = useState<{ w: number; h: number } | null>(null)
  const [bundleMaxCombos, setBundleMaxCombos] = useState<number>(120)
  const [bundleIncludeDimsInColorLabel, setBundleIncludeDimsInColorLabel] = useState(true)
  const [bundleGeneratedColorLabels, setBundleGeneratedColorLabels] = useState<string>('')

  // Model/bundle dropdown sources (for colors & sizes)
  const [sourceGroups, setSourceGroups] = useState<SourceOptionGroup[]>([])
  const [loadingSourceGroups, setLoadingSourceGroups] = useState(false)
  const [sourceRefreshKey, setSourceRefreshKey] = useState(0)
  const [bundleTokenMetaByValue, setBundleTokenMetaByValue] = useState<Record<string, BundleTokenMeta>>({})

  // Explicit save/load profiles (in addition to auto localStorage)
  const [profileName, setProfileName] = useState('')
  const [profileNames, setProfileNames] = useState<string[]>([])
  const [selectedProfileName, setSelectedProfileName] = useState<string>('')

  // Persist config in browser storage (MVP; makes it usable as "系统主体" without backend yet)
  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY)
      if (!raw) return
      const parsed = JSON.parse(raw) as PersistedConfigV1
      if (parsed?.merchantSkuPrefix) setMerchantSkuPrefix(parsed.merchantSkuPrefix)
      if (parsed?.merchantSkuSuffix !== undefined) setMerchantSkuSuffix(parsed.merchantSkuSuffix)
      if (Array.isArray(parsed?.sizes) && parsed.sizes.length) setSizes(parsed.sizes)
      if (Array.isArray(parsed?.colors) && parsed.colors.length) {
        setColors(
          parsed.colors.map((c) => ({
            key: c.key,
            label: c.label,
            width_cm: c.width_cm,
            height_cm: c.height_cm,
            thickness_cm: c.thickness_cm,
            length_cm: c.length_cm,
            main_pattern_type: c.main_pattern_type,
            source_code: (c as any)?.source_code ?? '',
            enabledSizes: c.enabledSizes ?? {},
          })),
        )
      }
      if (Array.isArray(parsed?.mainPatternTypes) && parsed.mainPatternTypes.length) setMainPatternTypes(parsed.mainPatternTypes)
      if (parsed?.ui) {
        if (typeof parsed.ui.enableColorImages === 'boolean') setEnableColorImages(parsed.ui.enableColorImages)
        if (typeof parsed.ui.enableSizeImages === 'boolean') setEnableSizeImages(parsed.ui.enableSizeImages)
        if (typeof parsed.ui.enableColorRemarks === 'boolean') setEnableColorRemarks(parsed.ui.enableColorRemarks)
        if (typeof parsed.ui.enableSizeRemarks === 'boolean') setEnableSizeRemarks(parsed.ui.enableSizeRemarks)
        if (typeof parsed.ui.enablePatternRemarks === 'boolean') setEnablePatternRemarks(parsed.ui.enablePatternRemarks)
        if (typeof parsed.ui.includeMainPatternType === 'boolean') setIncludeMainPatternType(parsed.ui.includeMainPatternType)
      }
    } catch {
      // ignore storage corruption
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_PROFILES_KEY)
      if (!raw) return
      const parsed = JSON.parse(raw) as Record<string, PersistedConfigV1>
      const names = Object.keys(parsed ?? {}).filter(Boolean).sort((a, b) => a.localeCompare(b))
      setProfileNames(names)
    } catch {
      // ignore
    }
  }, [])

  useEffect(() => {
    // fetch options (refreshable)
    let cancelled = false
    void (async () => {
      setLoadingSourceGroups(true)
      try {
        // cache-bust: new models/bundles might not show up immediately if upstream caches GET
        const ts = Date.now()

        // 1) Published standard models (increase limit to avoid pagination hiding new items)
        const modelsResp = await fetchPublishedStandardModels({ limit: 1000, _ts: ts } as any)

        const modelItems = Array.isArray((modelsResp as any)?.items) ? ((modelsResp as any).items as any[]) : Array.isArray(modelsResp as any) ? (modelsResp as any) : []
        const modelOptions = modelItems
          .map((it: any) => {
            const code = safeUpper((it as any)?.code ?? (it as any)?.model_code ?? (it as any)?.model ?? '')
            const name = String((it as any)?.name ?? (it as any)?.model_name ?? '').trim()
            if (!code) return null
            return { value: code, label: name ? `${code}（${name}）` : code }
          })
          .filter(Boolean) as Array<{ value: string; label: string }>

        // 2) Bundle templates: page through to avoid new items being outside first page
        const bundleItems: any[] = []
        const pageSize = 200
        const maxPages = 20 // hard cap: 4000 templates max (should be enough for now)
        for (let page = 1; page <= maxPages; page++) {
          const resp = await fetchBundleTemplates({ page, page_size: pageSize, include_archived: true, _ts: ts } as any)
          const items = Array.isArray((resp as any)?.items) ? ((resp as any).items as any[]) : []
          bundleItems.push(...items)
          if (items.length < pageSize) break
        }
        const bundleOptions: Array<{ value: string; label: string }> = []
        const bundleMeta: Record<string, BundleTokenMeta> = {}
        for (const t of bundleItems) {
          const code = safeUpper((t as any)?.code)
          if (!code) continue
          const name = String((t as any)?.name ?? '').trim()
          const pp = Array.isArray((t as any)?.metadata?.phrase_presets) ? ((t as any).metadata.phrase_presets as any[]) : []
          for (const p of pp) {
            const sel = safeUpper((p as any)?.selector)
            if (!sel) continue
            const mode = String((p as any)?.mode ?? '').trim() === 'force' ? 'Z' : 'B'
            const token = `${mode}-${code}${sel}`
            const phrase = String((p as any)?.phrase ?? '').trim()
            bundleOptions.push({
              value: token,
              label: `${token}${name ? `（${name}）` : ''}${phrase ? `：${phrase}` : ''}`,
            })
            bundleMeta[token] = { mode: mode as any, phrase: phrase || undefined, name: name || undefined }
          }
        }
        // stable sort
        modelOptions.sort((a, b) => a.value.localeCompare(b.value))
        bundleOptions.sort((a, b) => a.value.localeCompare(b.value))

        const groups: SourceOptionGroup[] = [
          { label: '标准模型（已发布）', options: modelOptions },
          { label: '套装模板（B/Z + AA/AB...）', options: bundleOptions },
        ].filter((g) => g.options.length)

        if (!cancelled) setSourceGroups(groups)
        if (!cancelled) setBundleTokenMetaByValue(bundleMeta)
      } catch (e: any) {
        if (!cancelled) message.warning(`加载“模型/套版”下拉失败：${String(e?.message ?? e)}`)
      } finally {
        if (!cancelled) setLoadingSourceGroups(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [sourceRefreshKey])

  useEffect(() => {
    try {
      const data: PersistedConfigV1 = {
        merchantSkuPrefix,
        merchantSkuSuffix,
        sizes,
        colors,
        mainPatternTypes,
        ui: {
          enableColorImages,
          enableSizeImages,
          enableColorRemarks,
          enableSizeRemarks,
          enablePatternRemarks,
          includeMainPatternType,
        },
      }
      localStorage.setItem(STORAGE_KEY, JSON.stringify(data))
    } catch {
      // ignore quota/disabled storage
    }
  }, [
    merchantSkuPrefix,
    merchantSkuSuffix,
    sizes,
    colors,
    mainPatternTypes,
    enableColorImages,
    enableSizeImages,
    enableColorRemarks,
    enableSizeRemarks,
    enablePatternRemarks,
    includeMainPatternType,
  ])

  const cells: TmallSkuCell[] = useMemo(() => {
    const out: TmallSkuCell[] = []
    for (const c of colors) {
      for (const s of sizes) {
        out.push({
          color_key: c.key,
          size_key: s.key,
          enabled: c.enabledSizes?.[s.key] !== false,
        })
      }
    }
    return out
  }, [colors, sizes])

  const payload = useMemo(
    () => ({
      sizes,
      colors: colors.map(({ enabledSizes, ...rest }) => rest),
      cells,
      merchant_sku_prefix: merchantSkuPrefix,
      merchant_sku_suffix: merchantSkuSuffix,
    }),
    [sizes, colors, cells, merchantSkuPrefix, merchantSkuSuffix],
  )

  const sourceLabelByValue = useMemo(() => {
    const m = new Map<string, string>()
    for (const g of sourceGroups ?? []) {
      for (const opt of g.options ?? []) {
        const v = String((opt as any)?.value ?? '').trim()
        const label = String((opt as any)?.label ?? '').trim()
        if (!v) continue
        if (!m.has(v)) m.set(v, label || v)
      }
    }
    return m
  }, [sourceGroups])

  const specRows: SpecRow[] = useMemo(() => {
    const rows: SpecRow[] = []
    for (const c of colors) {
      for (const s of sizes) {
        const enabled = c.enabledSizes?.[s.key] !== false
        const sku_status: 0 | 1 = enabled ? 1 : 0
        const merchant_sku = buildMerchantSku({
          merchantSkuPrefix,
          merchantSkuSuffix,
          // 颜色分类绑定优先级最高：更具体（同一尺寸下不同工艺/套版可不同）
          sourceCode: (c as any)?.source_code || (s as any)?.source_code,
        })
        const sizeSource = String((s as any)?.source_code ?? '').trim()
        const attribute_spec = sizeSource ? sourceLabelByValue.get(sizeSource) || sizeSource : ''
        const bm = sizeSource ? bundleTokenMetaByValue[sizeSource] : undefined
        const token_formula = bm && bm.mode === 'B' ? String(bm.phrase ?? '').trim() : ''
        const spec_text = `${String(c.label ?? '').trim()} ${String(s.label ?? '').trim()}`.trim()
        rows.push({
          row_key: `${c.key}||${s.key}`,
          color_key: c.key,
          size_key: s.key,
          color_label: c.label,
          size_label: s.label,
          merchant_sku,
          attribute_spec,
          token_formula,
          spec_text,
          sku_status,
          main_pattern_type: includeMainPatternType ? (c.main_pattern_type ?? null) : null,
          length_cm: fmtNum(c.length_cm),
          thickness_cm: fmtNum(c.thickness_cm),
          width_cm: fmtNum(c.width_cm),
        })
      }
    }
    return rows
  }, [colors, sizes, merchantSkuPrefix, merchantSkuSuffix, includeMainPatternType, sourceLabelByValue, bundleTokenMetaByValue])

  const getSpecTextForRow = (r: SpecRow): string => {
    const edited = String(specEdits?.[r.row_key]?.spec_text ?? '').trim()
    if (edited) return edited
    return String(r.spec_text ?? '').trim()
  }

  const parseFormulaTokenGroups = (formulaRaw: string): Array<{ tokens: string[]; allowEmpty: boolean }> => {
    const formula = String(formulaRaw ?? '')
    const groups: Array<{ tokens: string[]; allowEmpty: boolean }> = []
    const bracketRe = /\[([^\]]+)\]/g
    let m: RegExpExecArray | null
    while ((m = bracketRe.exec(formula))) {
      const seg = String(m[1] ?? '')
      const tokenRe = /\{([^}]*)\}/g
      let mm: RegExpExecArray | null
      const tokens: string[] = []
      let allowEmpty = false
      while ((mm = tokenRe.exec(seg))) {
        const t = String(mm[1] ?? '').trim()
        if (!t) {
          allowEmpty = true
          continue
        }
        tokens.push(t)
      }
      const uniq = Array.from(new Set(tokens))
      if (uniq.length || allowEmpty) groups.push({ tokens: uniq, allowEmpty })
    }
    return groups
  }

  const validateAllSpecRows = () => {
    const out: Record<string, { ok: boolean; issues: string[] }> = {}
    let okCount = 0
    let badCount = 0
    for (const r of specRows) {
      const specText = getSpecTextForRow(r)
      const formula = String(r.token_formula ?? '').trim()
      if (!formula) {
        // 指定型(Z) / 模型码：暂不要求规格触发 token
        out[r.row_key] = { ok: true, issues: [] }
        okCount++
        continue
      }
      const groups = parseFormulaTokenGroups(formula)
      const issues: string[] = []
      for (const g of groups) {
        if (!g.tokens.length) continue
        const hit = g.tokens.some((tk) => specText.includes(tk))
        if (!hit && !g.allowEmpty) {
          issues.push(`未命中互斥组：${g.tokens.join(' / ')}`)
        }
      }
      const ok = issues.length === 0
      out[r.row_key] = { ok, issues }
      if (ok) okCount++
      else badCount++
    }
    setRowValidation(out)
    if (badCount) message.warning(`检验完成：通过 ${okCount} 条；未通过 ${badCount} 条（请检查“商品规格（网店）”是否包含需要的 TOKEN）`)
    else message.success(`检验完成：全部通过（${okCount} 条）`)
  }

  const setSkuEnabled = (colorKey: string, sizeKey: string, enabled: boolean) => {
    setColors((prev) =>
      prev.map((c) => (c.key === colorKey ? { ...c, enabledSizes: { ...(c.enabledSizes ?? {}), [sizeKey]: enabled } } : c)),
    )
  }

  const updateColorField = (colorKey: string, patch: Partial<ColorRow>) => {
    setColors((prev) => prev.map((c) => (c.key === colorKey ? { ...c, ...patch } : c)))
  }

  const doPreview = async () => {
    setLoadingPreview(true)
    try {
      const resp = await previewTmallSkuTemplate(payload)
      setPreviewRows(resp.rows ?? [])
      setPreviewTotal(resp.total_rows ?? 0)
      message.success(`已生成预览：${resp.total_rows ?? 0} 行`)
    } catch (e: any) {
      message.error(String(e?.message ?? e))
    } finally {
      setLoadingPreview(false)
    }
  }

  const doExport = async () => {
    setLoadingExport(true)
    try {
      const blob = await exportTmallSkuTemplateXlsx(payload)
      downloadBlob(blob, 'tmall_buyi_sku_template.xlsx')
      message.success('已导出 xlsx')
    } catch (e: any) {
      message.error(String(e?.message ?? e))
    } finally {
      setLoadingExport(false)
    }
  }

  const doFillTemplateAndDownload = async () => {
    if (!templateFile) {
      message.warning('请先上传天猫官方模板（xls/xlsx）')
      return
    }
    setLoadingFill(true)
    try {
      const [buf, resp] = await Promise.all([readFileAsArrayBuffer(templateFile), previewTmallSkuTemplate(payload)])

      // Build lookup: (color_label, size_label) -> row
      const lookup = new Map<string, TmallSkuRow>()
      for (const r of resp.rows ?? []) {
        const k = `${normalizeCellText(r.color_label)}||${normalizeCellText(r.size_label)}`
        lookup.set(k, r)
      }

      const wb = XLSX.read(buf, { type: 'array', cellStyles: true })
      const sheetName = templateSheetName && wb.SheetNames.includes(templateSheetName) ? templateSheetName : wb.SheetNames?.[0]
      if (!sheetName) throw new Error('模板无工作表（Sheet）')
      const ws = wb.Sheets[sheetName]
      if (!ws) throw new Error('模板工作表读取失败')

      const header = findHeaderIndex(ws)
      if (!header) {
        throw new Error('未在模板中找到表头列：颜色分类/尺寸/商家编码/是否上架（请确认上传的是天猫官方SKU模板）')
      }

      const range = XLSX.utils.decode_range(ws['!ref'] as string)
      let filled = 0
      let skipped = 0
      let unmatched = 0

      for (let r = header.headerRowIndex + 1; r <= range.e.r; r++) {
        const colorAddr = XLSX.utils.encode_cell({ r, c: header.colorCol })
        const sizeAddr = XLSX.utils.encode_cell({ r, c: header.sizeCol })
        const colorVal = normalizeCellText((ws as any)[colorAddr]?.v)
        const sizeVal = normalizeCellText((ws as any)[sizeAddr]?.v)

        // stop early on trailing empty rows
        if (!colorVal && !sizeVal) continue

        const k = `${colorVal}||${sizeVal}`
        const target = lookup.get(k)
        if (!target) {
          unmatched++
          continue
        }

        const merchantAddr = XLSX.utils.encode_cell({ r, c: header.merchantSkuCol })
        const statusAddr = XLSX.utils.encode_cell({ r, c: header.statusCol })

        const existingMerchant = normalizeCellText((ws as any)[merchantAddr]?.v)
        const existingStatus = normalizeCellText((ws as any)[statusAddr]?.v)
        if (!overwriteExisting && (existingMerchant || existingStatus)) {
          skipped++
          continue
        }

        const merchantSku = String(target.merchant_sku ?? '').trim()
        const skuStatus = Number(target.sku_status ?? 0)

        if (merchantSku) {
          const cell: any = (ws as any)[merchantAddr] ?? {}
          cell.t = 's'
          cell.v = merchantSku
          ;(ws as any)[merchantAddr] = cell
        }
        {
          const cell: any = (ws as any)[statusAddr] ?? {}
          cell.t = 'n'
          cell.v = skuStatus
          ;(ws as any)[statusAddr] = cell
        }
        filled++
      }

      const out = XLSX.write(wb, { bookType: 'xlsx', type: 'array' })
      const blob = new Blob([out], {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      })
      const base = templateFile.name.replace(/\.(xlsx|xls)$/i, '')
      downloadBlob(blob, `${base}_filled.xlsx`)
      message.success(`已填充并导出：填充 ${filled} 行；未匹配 ${unmatched} 行；跳过 ${skipped} 行`)
    } catch (e: any) {
      message.error(String(e?.message ?? e))
    } finally {
      setLoadingFill(false)
    }
  }

  const exportAttributeBuildListXlsx = () => {
    const wb = XLSX.utils.book_new()
    const rows: Array<{ attribute: string; value: string }> = []
    for (const c of colors) rows.push({ attribute: '颜色分类', value: normalizeAttrValue(c.label) })
    for (const s of sizes) rows.push({ attribute: '尺寸', value: normalizeAttrValue(s.label) })
    for (const p of mainPatternTypes) rows.push({ attribute: '主图案类型', value: normalizeAttrValue(p.label) })

    const ws = XLSX.utils.json_to_sheet(rows, { header: ['attribute', 'value'] })
    // Friendly headers
    XLSX.utils.sheet_add_aoa(ws, [['属性名', '属性值']], { origin: 'A1' })
    XLSX.utils.book_append_sheet(wb, ws, 'build_attributes')

    const out = XLSX.write(wb, { bookType: 'xlsx', type: 'array' })
    downloadBlob(new Blob([out], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }), 'tmall_build_attributes.xlsx')
  }

  const exportConfigJson = () => {
    const data: PersistedConfigV1 = {
      merchantSkuPrefix,
      merchantSkuSuffix,
      sizes,
      colors,
      mainPatternTypes,
      ui: {
        enableColorImages,
        enableSizeImages,
        enableColorRemarks,
        enableSizeRemarks,
        enablePatternRemarks,
        includeMainPatternType,
      },
    }
    downloadText(JSON.stringify(data, null, 2), 'tmall_sku_generator_config.json')
  }

  const importConfigJson = async (file: File) => {
    try {
      const buf = await file.text()
      const parsed = JSON.parse(buf) as Partial<PersistedConfigV1>
      if (parsed.merchantSkuPrefix !== undefined) setMerchantSkuPrefix(String(parsed.merchantSkuPrefix))
      if (parsed.merchantSkuSuffix !== undefined) setMerchantSkuSuffix(String(parsed.merchantSkuSuffix))
      if (Array.isArray(parsed.sizes)) setSizes(parsed.sizes as any)
      if (Array.isArray(parsed.colors)) {
        setColors(
          (parsed.colors as any[]).map((c) => ({
            key: String(c.key ?? `c_${uid()}`),
            label: String(c.label ?? '').trim(),
            width_cm: c.width_cm ?? null,
            height_cm: c.height_cm ?? null,
            thickness_cm: c.thickness_cm ?? null,
            length_cm: c.length_cm ?? null,
            main_pattern_type: c.main_pattern_type ?? null,
            source_code: String((c as any)?.source_code ?? '').trim(),
            enabledSizes: (c.enabledSizes && typeof c.enabledSizes === 'object' ? c.enabledSizes : {}) as Record<string, boolean>,
          })),
        )
      }
      if (Array.isArray(parsed.mainPatternTypes)) {
        setMainPatternTypes(
          (parsed.mainPatternTypes as any[]).map((p) => ({
            key: String(p.key ?? `p_${uid()}`),
            label: String(p.label ?? '').trim(),
          })),
        )
      }
      if (parsed.ui) {
        if (typeof parsed.ui.enableColorImages === 'boolean') setEnableColorImages(parsed.ui.enableColorImages)
        if (typeof parsed.ui.enableSizeImages === 'boolean') setEnableSizeImages(parsed.ui.enableSizeImages)
        if (typeof parsed.ui.enableColorRemarks === 'boolean') setEnableColorRemarks(parsed.ui.enableColorRemarks)
        if (typeof parsed.ui.enableSizeRemarks === 'boolean') setEnableSizeRemarks(parsed.ui.enableSizeRemarks)
        if (typeof parsed.ui.enablePatternRemarks === 'boolean') setEnablePatternRemarks(parsed.ui.enablePatternRemarks)
        if (typeof parsed.ui.includeMainPatternType === 'boolean') setIncludeMainPatternType(parsed.ui.includeMainPatternType)
      }
      message.success('已导入配置')
    } catch (e: any) {
      message.error(String(e?.message ?? e ?? '导入失败'))
    }
  }

  const readFileAsDataUrl = (file: File): Promise<string> =>
    new Promise((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = () => resolve(String(reader.result ?? ''))
      reader.onerror = () => reject(reader.error ?? new Error('读取图片失败'))
      reader.readAsDataURL(file)
    })

  const attributeText = useMemo(() => {
    const lines: string[] = []
    lines.push('【颜色分类】')
    for (const c of colors) lines.push(`- ${normalizeAttrValue(c.label)}`)
    lines.push('')
    lines.push('【尺寸】')
    for (const s of sizes) lines.push(`- ${normalizeAttrValue(s.label)}`)
    lines.push('')
    lines.push('【主图案类型】')
    for (const p of mainPatternTypes) lines.push(`- ${normalizeAttrValue(p.label)}`)
    lines.push('')
    return lines.join('\n')
  }, [colors, sizes, mainPatternTypes])

  const loadBundlePreset = async () => {
    const parsed = parseBundleTokenInput(bundleTokenInput)
    if (!parsed) {
      message.warning('请输入套装短码，例如：B-3U3PAA 或 Z-3U3PAA')
      return
    }
    setBundleLoading(true)
    try {
      const tpl = await fetchBundleTemplateByCode(parsed.templateCode)
      const pp = Array.isArray((tpl as any)?.metadata?.phrase_presets) ? ((tpl as any).metadata.phrase_presets as any[]) : []
      const preset =
        pp.find((x) => String(x?.selector ?? '').trim().toUpperCase() === parsed.selector.toUpperCase()) ??
        pp.find((x) => String(x?.selector ?? '').trim()) ??
        null
      if (!preset) {
        throw new Error(`模板 ${parsed.templateCode} 未找到 selector=${parsed.selector} 的属性组`)
      }
      const mode = String(preset?.mode ?? '').trim() === 'force' ? 'Z' : 'B'
      setBundlePresetMode(mode)
      const phrase = String(preset?.phrase ?? '').trim()
      setBundlePresetPhrase(phrase)
      if (mode === 'Z') {
        // 指定型不依赖解析；这里只展示备注/短语（如有）
        setBundleGroups([])
        setBundleDims(null)
        setBundleGeneratedColorLabels('')
        return
      }
      if (!phrase) {
        throw new Error('解析型(B) 的“属性名称/公式”为空；请先在套装模板里点击“重新生成/保存当前属性”')
      }
      const built = parseBundleAttributeFormula(phrase)
      setBundleGroups(built.groups)
      setBundleDims(built.dims ?? null)
      setBundleGeneratedColorLabels('')
    } catch (e: any) {
      message.error(String(e?.message ?? e))
    } finally {
      setBundleLoading(false)
    }
  }

  const generateColorsFromBundleGroups = (opts: { append: boolean }) => {
    if (bundlePresetMode === 'Z') {
      message.warning('Z（指定型）不需要解析 TOKEN；这里只建议把商家编码回填为 Z-XXXXAA')
      return
    }
    if (!bundleGroups.length) {
      message.warning('未解析到互斥组选项（请先加载套装短码，并确保公式包含 [{A}{B}] 结构）')
      return
    }

    const limit = Math.max(1, Math.min(500, Number(bundleMaxCombos || 0) || 120))
    const combos = cartesianProduct(bundleGroups, limit)
    if (!combos.length) {
      message.warning('暂无可生成组合')
      return
    }
    const labelLines: string[] = []
    const newRows: ColorRow[] = []
    for (const x of combos) {
      const tokens = (x.tokens ?? []).map((t) => String(t ?? '').trim()).filter(Boolean)
      const tokenText = tokens.length ? tokens.join(' ') : '无'
      const dimText =
        bundleIncludeDimsInColorLabel && bundleDims && Number.isFinite(bundleDims.w) && Number.isFinite(bundleDims.h)
          ? ` ${fmtNum(bundleDims.w)}X${fmtNum(bundleDims.h)}`
          : ''
      const label = `${tokenText}${dimText}`.trim()
      labelLines.push(label)
      newRows.push({
        key: `c_${uid()}`,
        label,
        width_cm: bundleDims?.w ?? null,
        height_cm: bundleDims?.h ?? null,
        enabledSizes: Object.fromEntries(sizes.map((s) => [s.key, true])),
      })
    }
    setBundleGeneratedColorLabels(labelLines.join('\n'))
    setColors((prev) => (opts.append ? [...prev, ...newRows] : newRows))
    message.success(`已生成颜色分类：${newRows.length} 条${combos.length >= limit ? '（已按上限截断）' : ''}`)
  }

  return (
    <div style={{ padding: 16 }}>
      <Space direction="vertical" style={{ width: '100%' }} size={12}>
        <Card
          title="天猫布艺 SKU规格生成器（MVP）"
          extra={<Tag color="gold">颜色分类=图案/工艺款式；尺寸可按款式禁用</Tag>}
        >
          <Space direction="vertical" style={{ width: '100%' }} size={10}>
            <Space wrap size={8}>
              <Text type="secondary">商家编码前缀</Text>
              <Input style={{ width: 260 }} value={merchantSkuPrefix} onChange={(e) => setMerchantSkuPrefix(e.target.value)} />
              <Text type="secondary">后缀</Text>
              <Input style={{ width: 160 }} value={merchantSkuSuffix} onChange={(e) => setMerchantSkuSuffix(e.target.value)} />
              <Divider type="vertical" />
              <Button icon={<SettingOutlined />} onClick={() => setSettingsOpen(true)}>
                设置
              </Button>
              <Divider type="vertical" />
              <Text type="secondary">SKU规格展示</Text>
              <Radio.Group
                value={displayMode}
                onChange={(e) => setDisplayMode(e.target.value as DisplayMode)}
                optionType="button"
                buttonStyle="solid"
                options={[
                  { label: '表格', value: 'table' },
                  { label: '矩阵', value: 'matrix' },
                ]}
              />
            </Space>

            <Divider style={{ margin: '8px 0' }} />

            <Space wrap size={8} style={{ width: '100%', justifyContent: 'space-between' }}>
              <Space wrap size={8}>
                <Button icon={<EyeOutlined />} loading={loadingPreview} onClick={doPreview}>
                  生成预览
                </Button>
                <Button icon={<DownloadOutlined />} type="primary" loading={loadingExport} onClick={doExport}>
                  导出 xlsx
                </Button>
                <Text type="secondary">（导出包含 sheet1 数据 + sheet2 字段映射）</Text>
              </Space>
              <Text type="secondary">预览行数：{previewTotal}</Text>
            </Space>

            <Divider style={{ margin: '8px 0' }} />

            <Alert
              type="info"
              showIcon
              message="天猫模板填充（推荐流程）"
              description={
                <div>
                  <div>销售属性（颜色分类/尺寸）需要先在天猫后台建立，模板里不可编辑。</div>
                  <div>本工具用于把你配置好的“商家编码 / 是否上架(0/1)”批量回填到天猫官方模板，再下载回传。</div>
                </div>
              }
            />

            <Space wrap size={8} style={{ marginTop: 8 }}>
              <Upload
                accept=".xlsx,.xls"
                maxCount={1}
                showUploadList={false}
                beforeUpload={(file) => {
                  setTemplateFile(file)
                  setTemplateSheetNames([])
                  setTemplateSheetName('')
                  void (async () => {
                    try {
                      const buf = await readFileAsArrayBuffer(file)
                      const wb = XLSX.read(buf, { type: 'array' })
                      const names = (wb.SheetNames ?? []).filter(Boolean)
                      setTemplateSheetNames(names)
                      if (names[0]) setTemplateSheetName(names[0])
                    } catch (e: any) {
                      message.warning(`读取模板工作表失败：${String(e?.message ?? e)}`)
                    }
                  })()
                  message.success(`已选择模板：${file.name}`)
                  return false
                }}
              >
                <Button icon={<UploadOutlined />}>上传天猫官方模板</Button>
              </Upload>
              <Text type="secondary">{templateFile ? templateFile.name : '未选择文件'}</Text>
              <Divider type="vertical" />
              <Text type="secondary">工作表</Text>
              <Select
                style={{ width: 220 }}
                disabled={!templateFile || templateSheetNames.length <= 1}
                placeholder="自动识别"
                value={templateSheetName || undefined}
                options={templateSheetNames.map((n) => ({ label: n, value: n }))}
                onChange={(v) => setTemplateSheetName(v)}
              />
              <Divider type="vertical" />
              <Text type="secondary">覆盖已有值</Text>
              <Switch checked={overwriteExisting} onChange={setOverwriteExisting} />
              <Button type="primary" loading={loadingFill} disabled={!templateFile} onClick={doFillTemplateAndDownload}>
                一键填充并下载
              </Button>
            </Space>
          </Space>
        </Card>

        <Card
          title="套装模板（B/Z）→ 天猫属性词（占主动权）"
          extra={<Tag color="blue">B：解析型（用互斥组生成属性值域）；Z：指定型（不依赖解析）</Tag>}
        >
          <Space direction="vertical" style={{ width: '100%' }} size={10}>
            <Alert
              type="info"
              showIcon
              message="用法"
              description={
                <div>
                  <div>输入套装短码（例如 B-3U3PAA / Z-3U3PAA），加载套装抽屉里保存的“属性名称/公式”。</div>
                  <div>
                    B（解析型）会把公式中的互斥组（例如 <Text code>{'[{}{毛球}][{黄金绒}{雪尼尔}]...'}</Text>）拆成天猫可建属性的值域，并按组合生成“颜色分类”。
                  </div>
                  <div>
                    Z（指定型）不需要解析 TOKEN；建议仅用于模板回填商家编码为 <Text code>{'Z-XXXXAA'}</Text>（颜色分类可按对客展示自由定义）。
                  </div>
                </div>
              }
            />

            <Space wrap size={8}>
              <Text type="secondary">套装短码</Text>
              <Input
                style={{ width: 220 }}
                value={bundleTokenInput}
                onChange={(e) => setBundleTokenInput(e.target.value)}
                placeholder="B-3U3PAA"
              />
              <Button loading={bundleLoading} onClick={() => void loadBundlePreset()}>
                加载套版规则
              </Button>
              <Divider type="vertical" />
              <Text type="secondary">最大组合数</Text>
              <Input style={{ width: 90 }} value={String(bundleMaxCombos)} onChange={(e) => setBundleMaxCombos(Number(e.target.value || 0))} />
              <Text type="secondary">颜色分类包含尺寸</Text>
              <Switch checked={bundleIncludeDimsInColorLabel} onChange={setBundleIncludeDimsInColorLabel} />
            </Space>

            {bundlePresetMode ? (
              <Space direction="vertical" style={{ width: '100%' }} size={8}>
                <Text type="secondary">
                  已加载模式：<Text strong>{bundlePresetMode}</Text>
                  {bundleDims ? (
                    <Text type="secondary">
                      {' '}
                      （识别尺寸：{fmtNum(bundleDims.w)}X{fmtNum(bundleDims.h)}）
                    </Text>
                  ) : null}
                </Text>
                {bundlePresetPhrase ? (
                  <Input.TextArea value={bundlePresetPhrase} autoSize={{ minRows: 2, maxRows: 4 }} readOnly />
                ) : (
                  <Text type="secondary">（无公式/备注）</Text>
                )}
                {bundlePresetMode === 'B' ? (
                  <div>
                    <Text type="secondary">互斥组：</Text>
                    <div style={{ marginTop: 6 }}>
                      {bundleGroups.length ? (
                        <Space wrap size={6}>
                          {bundleGroups.map((g, i) => (
                            <Tag key={`bg-${i}`} color="geekblue">
                              G{i + 1}: {g.map((x) => (String(x).trim() ? String(x).trim() : '（无）')).join(' / ')}
                            </Tag>
                          ))}
                        </Space>
                      ) : (
                        <Text type="secondary">未识别到互斥组（请确认公式包含 [...] 且内部使用 {'{'}...{'}'}）</Text>
                      )}
                    </div>
                  </div>
                ) : null}

                <Space wrap size={8}>
                  <Button type="primary" disabled={bundlePresetMode !== 'B' || !bundleGroups.length} onClick={() => generateColorsFromBundleGroups({ append: false })}>
                    生成颜色分类（覆盖）
                  </Button>
                  <Button disabled={bundlePresetMode !== 'B' || !bundleGroups.length} onClick={() => generateColorsFromBundleGroups({ append: true })}>
                    生成颜色分类（追加）
                  </Button>
                  <Button disabled={!bundleGeneratedColorLabels.trim()} onClick={() => void copyText(bundleGeneratedColorLabels)}>
                    复制颜色分类清单
                  </Button>
                </Space>

                {bundleGeneratedColorLabels.trim() ? (
                  <Input.TextArea value={bundleGeneratedColorLabels} autoSize={{ minRows: 4, maxRows: 8 }} readOnly />
                ) : null}
              </Space>
            ) : (
              <Text type="secondary">尚未加载套版规则</Text>
            )}
          </Space>
        </Card>

        {displayMode === 'table' ? (
          <Card
            title="SKU规格（表格样式）"
            extra={
              <Space wrap size={10}>
                <Text type="secondary">行数：{specRows.length}</Text>
                <Button size="small" onClick={validateAllSpecRows}>
                  检验
                </Button>
              </Space>
            }
          >
            <Table
              size="small"
              pagination={false}
              rowKey="row_key"
              dataSource={specRows}
              scroll={{ x: 1600 }}
              onRow={(r) => ({
                style: r.sku_status === 0 ? { opacity: 0.45 } : undefined,
              })}
              columns={[
                {
                  title: '商品规格（网店）',
                  fixed: 'left',
                  width: 420,
                  render: (_: any, r: SpecRow) => (
                    <Input
                      value={specEdits[r.row_key]?.spec_text ?? r.spec_text ?? ''}
                      onChange={(e) =>
                        setSpecEdits((prev) => ({
                          ...prev,
                          [r.row_key]: { ...(prev[r.row_key] ?? {}), spec_text: e.target.value },
                        }))
                      }
                    />
                  ),
                },
                {
                  title: 'SKU分类',
                  width: 120,
                  render: (_: any, r: SpecRow) => (
                    <Select
                      value={specEdits[r.row_key]?.sku_category ?? '单品'}
                      style={{ width: '100%' }}
                      options={[
                        { label: '单品', value: '单品' },
                        { label: '套装', value: '套装' },
                      ]}
                      onChange={(v) =>
                        setSpecEdits((prev) => ({
                          ...prev,
                          [r.row_key]: { ...(prev[r.row_key] ?? {}), sku_category: v },
                        }))
                      }
                    />
                  ),
                },
                {
                  title: '长度',
                  width: 100,
                  render: (_: any, r: SpecRow) => (
                    <Input
                      placeholder="规格"
                      value={r.length_cm ?? ''}
                      onChange={(e) => updateColorField(r.color_key, { length_cm: Number(e.target.value || 0) })}
                    />
                  ),
                },
                {
                  title: '厚度(cm)',
                  width: 120,
                  render: (_: any, r: SpecRow) => (
                    <Input
                      placeholder="规格"
                      value={r.thickness_cm ?? ''}
                      onChange={(e) => updateColorField(r.color_key, { thickness_cm: Number(e.target.value || 0) })}
                    />
                  ),
                },
                {
                  title: '宽度',
                  width: 100,
                  render: (_: any, r: SpecRow) => (
                    <Input
                      placeholder="规格"
                      value={r.width_cm ?? ''}
                      onChange={(e) => updateColorField(r.color_key, { width_cm: Number(e.target.value || 0) })}
                    />
                  ),
                },
                {
                  title: '商家编码',
                  dataIndex: 'merchant_sku',
                  width: 220,
                  render: (v: any) => <Input value={String(v ?? '')} readOnly />,
                },
                {
                  title: '属性规格',
                  dataIndex: 'attribute_spec',
                  width: 320,
                  render: (v: any) => <div style={{ whiteSpace: 'normal', lineHeight: 1.2 }}>{String(v ?? '').trim() || '-'}</div>,
                },
                {
                  title: 'TOKEN/公式',
                  dataIndex: 'token_formula',
                  width: 360,
                  render: (v: any) => (
                    <div style={{ whiteSpace: 'normal', lineHeight: 1.2, color: '#595959' }}>
                      {String(v ?? '').trim() || '-'}
                    </div>
                  ),
                },
                {
                  title: '是否上架',
                  width: 110,
                  fixed: 'right',
                  render: (_: any, r: SpecRow) => {
                    const v = rowValidation?.[r.row_key]
                    return (
                      <Space size={6}>
                        {v ? (v.ok ? <CheckCircleFilled style={{ color: '#52c41a' }} /> : <CloseCircleFilled style={{ color: '#ff4d4f' }} />) : null}
                        <Switch checked={r.sku_status === 1} onChange={(x) => setSkuEnabled(r.color_key, r.size_key, x)} />
                      </Space>
                    )
                  },
                },
                {
                  title: '操作',
                  width: 110,
                  fixed: 'right',
                  render: (_: any, r: SpecRow) =>
                    r.sku_status === 1 ? (
                      <Button type="link" danger onClick={() => setSkuEnabled(r.color_key, r.size_key, false)}>
                        删除
                      </Button>
                    ) : (
                      <Button type="link" onClick={() => setSkuEnabled(r.color_key, r.size_key, true)}>
                        重新启用
                      </Button>
                    ),
                },
              ]}
            />
          </Card>
        ) : null}

        {displayMode === 'matrix' ? (
        <Card
          title="颜色分类（图案/工艺款式）+ 是否上架矩阵"
          extra={
            <Button
              icon={<PlusOutlined />}
              onClick={() =>
                setColors((prev) => [
                  ...prev,
                  {
                    key: `c_${uid()}`,
                    label: '新款式',
                    width_cm: 45,
                    height_cm: 45,
                    enabledSizes: Object.fromEntries(sizes.map((s) => [s.key, true])),
                  },
                ])
              }
            >
              添加款式
            </Button>
          }
        >
          <Table
            size="small"
            pagination={false}
            rowKey="key"
            dataSource={colors}
            columns={[
              {
                title: '颜色分类（图案/工艺）',
                dataIndex: 'label',
                render: (_: any, r: ColorRow, idx: number) => (
                  <Input
                    value={r.label}
                    onChange={(e) =>
                      setColors((prev) => prev.map((x, i) => (i === idx ? { ...x, label: e.target.value } : x)))
                    }
                  />
                ),
              },
              {
                title: '主图案类型（可选）',
                width: 200,
                render: (_: any, r: ColorRow, idx: number) => (
                  <Select
                    allowClear
                    disabled={!includeMainPatternType}
                    placeholder="可选"
                    style={{ width: '100%' }}
                    value={r.main_pattern_type ?? undefined}
                    options={mainPatternTypes.map((p) => ({ label: p.label, value: p.label }))}
                    onChange={(v) =>
                      setColors((prev) =>
                        prev.map((x, i) => (i === idx ? { ...x, main_pattern_type: v ?? null } : x)),
                      )
                    }
                  />
                ),
              },
              {
                title: '宽*高(cm)',
                width: 140,
                render: (_: any, r: ColorRow, idx: number) => (
                  <Space size={6}>
                    <Input
                      style={{ width: 54 }}
                      value={String(r.width_cm ?? '')}
                      onChange={(e) =>
                        setColors((prev) =>
                          prev.map((x, i) => (i === idx ? { ...x, width_cm: Number(e.target.value || 0) } : x)),
                        )
                      }
                    />
                    <Text type="secondary">*</Text>
                    <Input
                      style={{ width: 54 }}
                      value={String(r.height_cm ?? '')}
                      onChange={(e) =>
                        setColors((prev) =>
                          prev.map((x, i) => (i === idx ? { ...x, height_cm: Number(e.target.value || 0) } : x)),
                        )
                      }
                    />
                  </Space>
                ),
              },
              ...sizes.map((s) => ({
                title: s.label,
                width: 110,
                align: 'center' as const,
                render: (_: any, r: ColorRow, idx: number) => (
                  <Switch
                    checked={r.enabledSizes?.[s.key] !== false}
                    onChange={(v) =>
                      setColors((prev) =>
                        prev.map((x, i) =>
                          i === idx ? { ...x, enabledSizes: { ...(x.enabledSizes ?? {}), [s.key]: v } } : x,
                        ),
                      )
                    }
                  />
                ),
              })),
            ]}
          />
          <div style={{ marginTop: 8 }}>
            <Text type="secondary">说明：每个开关对应导出表格里的“是否上架”（开=1，关=0，平台显示为灰色不可选但可重新启用）。</Text>
          </div>
        </Card>
        ) : null}

        <Card title="预览（前 50 行）" extra={<Text type="secondary">共 {previewTotal} 行</Text>}>
          <Table
            size="small"
            pagination={false}
            rowKey={(_, i) => `r-${i}`}
            dataSource={(previewRows ?? []).slice(0, 50)}
            columns={[
              { title: '颜色分类', dataIndex: 'color_label' },
              { title: '尺寸', dataIndex: 'size_label', width: 160 },
              { title: '商家编码', dataIndex: 'merchant_sku', width: 220 },
              { title: '是否上架', dataIndex: 'sku_status', width: 90 },
            ]}
          />
        </Card>

        <Drawer
          title="设置（SKU 模式 / 销售属性）"
          open={settingsOpen}
          onClose={() => setSettingsOpen(false)}
          width={860}
        >
          <Space direction="vertical" style={{ width: '100%' }} size={12}>
            <Alert
              type="info"
              showIcon
              message="说明"
              description={
                <div>
                  <div>这里用于模拟天猫“建立销售属性”的第一步：维护属性值域并输出可复制清单。</div>
                  <div>天猫模板中的“颜色分类/尺寸”不可编辑；建好属性后下载模板，再用主页面的“模板回填”批量填编码/上架。</div>
                </div>
              }
            />

            <Card
              size="small"
              title="属性选择"
              extra={
                <Space wrap size={8}>
                  <Text type="secondary">颜色分类/尺寸为必选；主图案类型可选</Text>
                  <Button
                    size="small"
                    icon={<ReloadOutlined />}
                    loading={loadingSourceGroups}
                    onClick={() => setSourceRefreshKey((x) => x + 1)}
                  >
                    刷新模型/套版
                  </Button>
                </Space>
              }
            >
              <Space wrap size={16}>
                <Checkbox checked disabled>
                  颜色分类
                </Checkbox>
                <Checkbox checked disabled>
                  尺寸
                </Checkbox>
                <Checkbox checked={includeMainPatternType} onChange={(e) => setIncludeMainPatternType(e.target.checked)}>
                  主图案类型
                </Checkbox>
              </Space>
            </Card>

            <Card
              size="small"
              title={`颜色分类（${colors.length}）`}
              extra={
                <Space wrap size={8}>
                  <Checkbox checked={enableColorImages} onChange={(e) => setEnableColorImages(e.target.checked)}>
                    添加图片
                  </Checkbox>
                  <Checkbox checked={enableColorRemarks} onChange={(e) => setEnableColorRemarks(e.target.checked)}>
                    备注
                  </Checkbox>
                  <Button
                    icon={<PlusOutlined />}
                    onClick={() =>
                      setColors((prev) => [
                        ...prev,
                        {
                          key: `c_${uid()}`,
                          label: '',
                          width_cm: 45,
                          height_cm: 45,
                          enabledSizes: Object.fromEntries(sizes.map((s) => [s.key, true])),
                          source_code: '',
                        },
                      ])
                    }
                  >
                    添加
                  </Button>
                </Space>
              }
            >
              <Space direction="vertical" style={{ width: '100%' }} size={10}>
                {colors.map((c, idx) => (
                  <Space key={c.key} wrap size={8} style={{ width: '100%', alignItems: 'flex-start' }}>
                    {enableColorImages ? (
                      <Upload
                        accept="image/*"
                        showUploadList={false}
                        beforeUpload={async (file) => {
                          try {
                            const dataUrl = await readFileAsDataUrl(file)
                            setColors((prev) => prev.map((x, i) => (i === idx ? { ...x, metadata_json: { ...(x as any).metadata_json, image_data_url: dataUrl } as any } : x)))
                          } catch (e: any) {
                            message.error(String(e?.message ?? e))
                          }
                          return false
                        }}
                      >
                        <div
                          style={{
                            width: 40,
                            height: 40,
                            border: '1px solid #ddd',
                            borderRadius: 6,
                            overflow: 'hidden',
                            background: '#fafafa',
                            cursor: 'pointer',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            marginTop: 2,
                          }}
                        >
                          {(c as any)?.metadata_json?.image_data_url ? (
                            // eslint-disable-next-line @typescript-eslint/no-unsafe-member-access
                            <img src={(c as any).metadata_json.image_data_url as string} alt="img" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                          ) : (
                            <Text type="secondary" style={{ fontSize: 12 }}>
                              图
                            </Text>
                          )}
                        </div>
                      </Upload>
                    ) : null}

                    <Input
                      style={{ flex: 1, minWidth: 520 }}
                      placeholder="颜色分类（天猫展示值）"
                      value={c.label}
                      onChange={(e) => setColors((prev) => prev.map((x, i) => (i === idx ? { ...x, label: e.target.value } : x)))}
                    />

                    <Select
                      allowClear
                      showSearch
                      style={{ width: 520 }}
                      placeholder="绑定来源(模型/套版)（可选，优先级最高）"
                      loading={loadingSourceGroups}
                      popupMatchSelectWidth={false}
                      listHeight={520}
                      value={String((c as any)?.source_code ?? '') || undefined}
                      options={[
                        { label: '不绑定（使用尺寸绑定/前后缀规则）', value: '' },
                        ...sourceGroups.map((g) => ({
                          label: g.label,
                          options: g.options,
                        })),
                      ]}
                      onChange={(v) =>
                        setColors((prev) => prev.map((x, i) => (i === idx ? ({ ...x, source_code: String(v ?? '') } as any) : x)))
                      }
                      filterOption={(input, opt) => {
                        const t = String((opt as any)?.label ?? '')
                        const vv = String((opt as any)?.value ?? '')
                        const q = String(input ?? '').trim().toLowerCase()
                        return t.toLowerCase().includes(q) || vv.toLowerCase().includes(q)
                      }}
                    />

                    {enableColorRemarks ? (
                      <Input
                        style={{ width: 220 }}
                        placeholder="备注(可选)"
                        value={String((c as any)?.metadata_json?.remark ?? '')}
                        onChange={(e) =>
                          setColors((prev) =>
                            prev.map((x, i) =>
                              i === idx ? { ...x, metadata_json: { ...(x as any).metadata_json, remark: e.target.value } as any } : x,
                            ),
                          )
                        }
                      />
                    ) : null}

                    <Button
                      icon={<DeleteOutlined />}
                      danger
                      onClick={() => setColors((prev) => prev.filter((_, i) => i !== idx))}
                    />
                  </Space>
                ))}
              </Space>
            </Card>

            <Card
              size="small"
              title={`尺寸（${sizes.length}）`}
              extra={
                <Space wrap size={8}>
                  <Checkbox checked={enableSizeImages} onChange={(e) => setEnableSizeImages(e.target.checked)}>
                    添加图片
                  </Checkbox>
                  <Checkbox checked={enableSizeRemarks} onChange={(e) => setEnableSizeRemarks(e.target.checked)}>
                    备注
                  </Checkbox>
                  <Button
                    icon={<PlusOutlined />}
                    onClick={() => setSizes((prev) => [...prev, { key: `size_${uid()}`, label: '', size_code: '', source_code: '' }])}
                  >
                    添加
                  </Button>
                </Space>
              }
            >
              <Space direction="vertical" style={{ width: '100%' }} size={10}>
                {sizes.map((s, idx) => (
                  <Space key={s.key} wrap size={8} style={{ width: '100%', alignItems: 'flex-start' }}>
                    {enableSizeImages ? (
                      <Upload
                        accept="image/*"
                        showUploadList={false}
                        beforeUpload={async (file) => {
                          try {
                            const dataUrl = await readFileAsDataUrl(file)
                            setSizes((prev) => prev.map((x, i) => (i === idx ? ({ ...x, metadata_json: { ...(x as any).metadata_json, image_data_url: dataUrl } } as any) : x)))
                          } catch (e: any) {
                            message.error(String(e?.message ?? e))
                          }
                          return false
                        }}
                      >
                        <div
                          style={{
                            width: 40,
                            height: 40,
                            border: '1px solid #ddd',
                            borderRadius: 6,
                            overflow: 'hidden',
                            background: '#fafafa',
                            cursor: 'pointer',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            marginTop: 2,
                          }}
                        >
                          {(s as any)?.metadata_json?.image_data_url ? (
                            <img src={(s as any).metadata_json.image_data_url as string} alt="img" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                          ) : (
                            <Text type="secondary" style={{ fontSize: 12 }}>
                              图
                            </Text>
                          )}
                        </div>
                      </Upload>
                    ) : null}

                    <Input
                      style={{ width: 420 }}
                      placeholder="尺寸（天猫展示值）"
                      value={s.label}
                      onChange={(e) => setSizes((prev) => prev.map((x, i) => (i === idx ? { ...x, label: e.target.value } : x)))}
                    />
                    <Select
                      allowClear
                      showSearch
                      style={{ width: 520 }}
                      placeholder="绑定来源(模型/套版)（可选，优先级低于颜色绑定）"
                      loading={loadingSourceGroups}
                      popupMatchSelectWidth={false}
                      listHeight={520}
                      value={String((s as any)?.source_code ?? '') || undefined}
                      options={[
                        { label: '不绑定（使用前后缀规则）', value: '' },
                        ...sourceGroups.map((g) => ({
                          label: g.label,
                          options: g.options,
                        })),
                      ]}
                      onChange={(v) =>
                        setSizes((prev) => prev.map((x, i) => (i === idx ? ({ ...x, source_code: String(v ?? '') } as any) : x)))
                      }
                      filterOption={(input, opt) => {
                        const t = String((opt as any)?.label ?? '')
                        const vv = String((opt as any)?.value ?? '')
                        const q = String(input ?? '').trim().toLowerCase()
                        return t.toLowerCase().includes(q) || vv.toLowerCase().includes(q)
                      }}
                    />

                    {enableSizeRemarks ? (
                      <Input
                        style={{ width: 220 }}
                        placeholder="备注(可选)"
                        value={String((s as any)?.metadata_json?.remark ?? '')}
                        onChange={(e) =>
                          setSizes((prev) =>
                            prev.map((x, i) =>
                              i === idx ? ({ ...x, metadata_json: { ...(x as any).metadata_json, remark: e.target.value } } as any) : x,
                            ),
                          )
                        }
                      />
                    ) : null}

                    <Button icon={<DeleteOutlined />} danger onClick={() => setSizes((prev) => prev.filter((_, i) => i !== idx))} />
                  </Space>
                ))}
              </Space>
            </Card>

            {includeMainPatternType ? (
              <Card
                size="small"
                title={`主图案类型（${mainPatternTypes.length}）`}
                extra={
                  <Space wrap size={8}>
                    <Checkbox checked={enablePatternRemarks} onChange={(e) => setEnablePatternRemarks(e.target.checked)}>
                      备注
                    </Checkbox>
                    <Button onClick={() => setMainPatternTypes((prev) => [...prev, { key: `p_${uid()}`, label: '' }])} icon={<PlusOutlined />}>
                      添加
                    </Button>
                  </Space>
                }
              >
                <Space direction="vertical" style={{ width: '100%' }} size={10}>
                  {mainPatternTypes.map((p, idx) => (
                    <Space key={p.key} wrap size={8} style={{ width: '100%', alignItems: 'flex-start' }}>
                      <Input
                        style={{ width: 360 }}
                        placeholder="主图案类型（天猫展示值）"
                        value={p.label}
                        onChange={(e) =>
                          setMainPatternTypes((prev) => prev.map((x, i) => (i === idx ? { ...x, label: e.target.value } : x)))
                        }
                      />
                      {enablePatternRemarks ? (
                        <Input
                          style={{ width: 220 }}
                          placeholder="备注(可选)"
                          value={String((p as any)?.remark ?? '')}
                          onChange={(e) =>
                            setMainPatternTypes((prev) =>
                              prev.map((x, i) => (i === idx ? ({ ...x, remark: e.target.value } as any) : x)),
                            )
                          }
                        />
                      ) : null}
                      <Button icon={<DeleteOutlined />} danger onClick={() => setMainPatternTypes((prev) => prev.filter((_, i) => i !== idx))} />
                    </Space>
                  ))}
                </Space>
              </Card>
            ) : null}

            <Card
              size="small"
              title="输出（复制/导出）"
              extra={
                <Space wrap size={8}>
                  <Upload
                    accept=".json"
                    maxCount={1}
                    showUploadList={false}
                    beforeUpload={(file) => {
                      void importConfigJson(file)
                      return false
                    }}
                  >
                    <Button>导入配置(JSON)</Button>
                  </Upload>
                  <Button onClick={exportConfigJson}>导出配置(JSON)</Button>
                  <Button onClick={() => void copyText(attributeText)}>一键复制建属性清单</Button>
                  <Button icon={<DownloadOutlined />} onClick={exportAttributeBuildListXlsx}>
                    导出建属性清单(xlsx)
                  </Button>
                </Space>
              }
            >
              <div style={{ marginBottom: 12 }}>
                <Text type="secondary">保存方案（显式）</Text>
                <div style={{ marginTop: 8 }}>
                  <Space wrap size={8}>
                    <Input
                      style={{ width: 240 }}
                      placeholder="方案名（例如：抱枕-枕套/枕芯套装）"
                      value={profileName}
                      onChange={(e) => setProfileName(e.target.value)}
                    />
                    <Button
                      onClick={() => {
                        const name = String(profileName ?? '').trim()
                        if (!name) {
                          message.warning('请输入方案名')
                          return
                        }
                        try {
                          const raw = localStorage.getItem(STORAGE_PROFILES_KEY)
                          const all = raw ? (JSON.parse(raw) as Record<string, PersistedConfigV1>) : {}
                          all[name] = {
                            merchantSkuPrefix,
                            merchantSkuSuffix,
                            sizes,
                            colors,
                            mainPatternTypes,
                            ui: {
                              enableColorImages,
                              enableSizeImages,
                              enableColorRemarks,
                              enableSizeRemarks,
                              enablePatternRemarks,
                              includeMainPatternType,
                            },
                          }
                          localStorage.setItem(STORAGE_PROFILES_KEY, JSON.stringify(all))
                          const names = Object.keys(all).filter(Boolean).sort((a, b) => a.localeCompare(b))
                          setProfileNames(names)
                          setSelectedProfileName(name)
                          message.success('已保存方案')
                        } catch (e: any) {
                          message.error(`保存失败：${String(e?.message ?? e)}`)
                        }
                      }}
                    >
                      保存
                    </Button>
                    <Select
                      style={{ width: 260 }}
                      placeholder="选择已保存方案"
                      value={selectedProfileName || undefined}
                      options={profileNames.map((n) => ({ label: n, value: n }))}
                      onChange={(v) => setSelectedProfileName(String(v ?? ''))}
                    />
                    <Button
                      disabled={!selectedProfileName}
                      onClick={() => {
                        const name = String(selectedProfileName ?? '').trim()
                        if (!name) return
                        try {
                          const raw = localStorage.getItem(STORAGE_PROFILES_KEY)
                          const all = raw ? (JSON.parse(raw) as Record<string, PersistedConfigV1>) : {}
                          const cfg = all[name]
                          if (!cfg) {
                            message.warning('未找到该方案')
                            return
                          }
                          setMerchantSkuPrefix(String(cfg.merchantSkuPrefix ?? ''))
                          setMerchantSkuSuffix(String(cfg.merchantSkuSuffix ?? ''))
                          setSizes(Array.isArray(cfg.sizes) ? (cfg.sizes as any) : [])
                          if (Array.isArray(cfg.colors)) {
                            setColors(
                              (cfg.colors as any[]).map((c) => ({
                                key: String(c.key ?? `c_${uid()}`),
                                label: String(c.label ?? '').trim(),
                                width_cm: c.width_cm ?? null,
                                height_cm: c.height_cm ?? null,
                                thickness_cm: c.thickness_cm ?? null,
                                length_cm: c.length_cm ?? null,
                                main_pattern_type: c.main_pattern_type ?? null,
                                source_code: String((c as any)?.source_code ?? '').trim(),
                                enabledSizes: (c.enabledSizes && typeof c.enabledSizes === 'object' ? c.enabledSizes : {}) as Record<string, boolean>,
                              })),
                            )
                          } else {
                            setColors([])
                          }
                          if (Array.isArray(cfg.mainPatternTypes)) {
                            setMainPatternTypes(
                              (cfg.mainPatternTypes as any[]).map((p) => ({
                                key: String(p.key ?? `p_${uid()}`),
                                label: String(p.label ?? '').trim(),
                              })),
                            )
                          }
                          const ui = (cfg as any)?.ui ?? {}
                          if (typeof ui.enableColorImages === 'boolean') setEnableColorImages(ui.enableColorImages)
                          if (typeof ui.enableSizeImages === 'boolean') setEnableSizeImages(ui.enableSizeImages)
                          if (typeof ui.enableColorRemarks === 'boolean') setEnableColorRemarks(ui.enableColorRemarks)
                          if (typeof ui.enableSizeRemarks === 'boolean') setEnableSizeRemarks(ui.enableSizeRemarks)
                          if (typeof ui.enablePatternRemarks === 'boolean') setEnablePatternRemarks(ui.enablePatternRemarks)
                          if (typeof ui.includeMainPatternType === 'boolean') setIncludeMainPatternType(ui.includeMainPatternType)
                          message.success('已加载方案')
                        } catch (e: any) {
                          message.error(`加载失败：${String(e?.message ?? e)}`)
                        }
                      }}
                    >
                      加载
                    </Button>
                    <Button
                      danger
                      disabled={!selectedProfileName}
                      onClick={() => {
                        const name = String(selectedProfileName ?? '').trim()
                        if (!name) return
                        try {
                          const raw = localStorage.getItem(STORAGE_PROFILES_KEY)
                          const all = raw ? (JSON.parse(raw) as Record<string, PersistedConfigV1>) : {}
                          if (!all[name]) {
                            message.warning('未找到该方案')
                            return
                          }
                          delete all[name]
                          localStorage.setItem(STORAGE_PROFILES_KEY, JSON.stringify(all))
                          const names = Object.keys(all).filter(Boolean).sort((a, b) => a.localeCompare(b))
                          setProfileNames(names)
                          setSelectedProfileName('')
                          message.success('已删除方案')
                        } catch (e: any) {
                          message.error(`删除失败：${String(e?.message ?? e)}`)
                        }
                      }}
                    >
                      删除
                    </Button>
                  </Space>
                </div>
              </div>
              <pre style={{ margin: 0, whiteSpace: 'pre-wrap', fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace' }}>
                {attributeText}
              </pre>
            </Card>
          </Space>
        </Drawer>
      </Space>
    </div>
  )
}

