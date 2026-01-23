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
import { useParams } from 'react-router-dom'

import {
  exportTmallSkuTemplateXlsx,
  fetchBundleTemplates,
  fetchPublishedStandardModels,
  previewTmallSkuTemplate,
  type TmallColorOption,
  type TmallSizeOption,
  type TmallSkuCell,
  type TmallSkuRow,
} from '@/services/planner'

import {
  computeMatrixCountFromConfig,
  loadTemplateConfig,
  loadTemplateIndex,
  saveTemplateConfig,
  upsertTemplateMeta,
  type SpecModuleType,
} from './tmallSkuGeneratorTemplates'

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

type BundleTokenMeta = {
  mode: 'B' | 'Z'
  phrase?: string
  name?: string
  // phrase_preset.components 优先；否则回退模板顶层 components（best-effort）
  components?: Array<{
    model_version_id?: string
    width_mm?: number
    height_mm?: number
    quantity?: number
    spec_text?: string
    label?: string
  }>
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

const mmToCmText = (mm: unknown): string => {
  const n = Number(mm)
  if (!Number.isFinite(n) || n <= 0) return ''
  return fmtNum(n / 10)
}

// 说明（前置校验台）：
// - 本页用于在“同步 ERP/发货扣库”之前，把“商品规格（网店）spec_text + 商家编码 + 尺寸(B/Z口径)”提前跑通并暴露问题
// - 解析口径尽量与后端一致，避免“前端看着对、后端扣库失败”
// - 相关后端口径：
//   - spec 解析：backend/src/planner/services/spec_parser_service.py::parse_spec
//   - B/Z 尺寸策略：backend/src/planner/services/bom_generation_service.py（generate-by-spec 的 B / Z dimension strategy）
//
// 与后端 spec_parser_service.parse_spec 尽量一致：用于“商品规格（网店）”解析宽高（B 解析型命中/扣库口径）
const parseDimsFromSpecText = (specTextRaw: string): { width_cm?: string; height_cm?: string; diameter_cm?: string } => {
  const text = String(specTextRaw ?? '').trim()
  if (!text) return {}

  const normalizeToCm = (value: number, unitRaw?: string | null) => {
    const u = String(unitRaw ?? 'cm').trim().toLowerCase()
    if (u === 'mm' || u === '毫米') return value / 10
    if (u === 'm' || u === '米') return value * 100
    return value
  }

  let widthCm: number | null = null
  let heightCm: number | null = null
  let diameterCm: number | null = null

  const isHeightLabel = (lbl: string) => ['竖', '高'].includes(String(lbl || '').trim())
  const isWidthLabel = (lbl: string) => ['横', '宽', '长'].includes(String(lbl || '').trim())

  // e.g. "竖120CM*横150CM" / "横150*竖120" / "宽120×高150"
  const labeledRe =
    /(竖|横|宽|高|长)\s*(\d{1,4}(?:\.\d+)?)\s*(cm|厘米|mm|毫米|m|米)?\s*(?:[xX×\*＊]\s*(竖|横|宽|高|长)\s*(\d{1,4}(?:\.\d+)?)\s*(cm|厘米|mm|毫米|m|米)?)/i
  const labeled = labeledRe.exec(text)
  if (labeled) {
    const l1 = String(labeled[1] ?? '').trim()
    const v1 = Number(labeled[2])
    const u1 = labeled[3]
    const l2 = String(labeled[4] ?? '').trim()
    const v2 = Number(labeled[5])
    const u2 = labeled[6]
    const v1cm = Number.isFinite(v1) ? normalizeToCm(v1, u1) : null
    const v2cm = Number.isFinite(v2) ? normalizeToCm(v2, u2) : null

    if (v1cm !== null && isHeightLabel(l1)) heightCm = v1cm
    if (v1cm !== null && isWidthLabel(l1)) widthCm = v1cm
    if (v2cm !== null && isHeightLabel(l2)) heightCm = v2cm
    if (v2cm !== null && isWidthLabel(l2)) widthCm = v2cm

    if (widthCm === null && v1cm !== null) widthCm = v1cm
    if (heightCm === null && v2cm !== null) heightCm = v2cm
  }

  // e.g. "45*45" / "45×45" / "45X45"
  const dimRe =
    /(约|大约|约等)?(\d{1,4}(?:\.\d+)?)\s*(?:[xX×\*＊]\s*(\d{1,4}(?:\.\d+)?))\s*(cm|厘米|mm|毫米|m|米)?/i
  const dim = dimRe.exec(text)
  if (dim) {
    const w = Number(dim[2])
    const h = Number(dim[3])
    const unit = dim[4]
    if (widthCm === null && Number.isFinite(w)) widthCm = normalizeToCm(w, unit)
    if (heightCm === null && Number.isFinite(h)) heightCm = normalizeToCm(h, unit)
  }

  // e.g. "直径50" / "φ50" / "圆形(50)"
  const diaRe = /(直径|φ|Φ|D|圆形|圆)\s*[（(]?\s*(\d{1,4}(?:\.\d+)?)\s*(cm|厘米|mm|毫米|m|米)?\s*[）)]?/i
  const dia = diaRe.exec(text)
  if (dia) {
    const v = Number(dia[2])
    const unit = dia[3]
    if (Number.isFinite(v)) {
      diameterCm = normalizeToCm(v, unit)
      if (widthCm === null && heightCm === null) {
        widthCm = diameterCm
        heightCm = diameterCm
      }
    }
  }

  const out: { width_cm?: string; height_cm?: string; diameter_cm?: string } = {}
  if (widthCm !== null && widthCm > 0) out.width_cm = fmtNum(widthCm)
  if (heightCm !== null && heightCm > 0) out.height_cm = fmtNum(heightCm)
  if (diameterCm !== null && diameterCm > 0) out.diameter_cm = fmtNum(diameterCm)
  return out
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
  merchant_source?: string
  display_source?: string
  is_z_source?: boolean
  attribute_spec?: string
  token_formula?: string
  spec_text?: string
  sku_status: 0 | 1
  main_pattern_type?: string | null
  length_cm?: string
  thickness_cm?: string
  width_cm?: string
  height_cm?: string
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
    model_source_code?: string
    token_formula?: string
  }
>

export default function TmallSkuTemplateGeneratorPage() {
  const params = useParams()
  const templateId = String((params as any)?.templateId ?? 'mvp').trim() || 'mvp'
  const [templateName, setTemplateName] = useState<string>('')
  const [templateType, setTemplateType] = useState<SpecModuleType>('家居布艺')

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
  type RowValidationDetail = {
    ok: boolean
    issues: string[]
    okTokens: string[]
    multiTokens: string[]
    missingGroupIndexes: number[]
  }
  const [rowValidation, setRowValidation] = useState<Record<string, RowValidationDetail>>({})
  // Model dropdown sources (for colors & sizes)
  const [sourceGroups, setSourceGroups] = useState<SourceOptionGroup[]>([])
  const [loadingSourceGroups, setLoadingSourceGroups] = useState(false)
  const [sourceRefreshKey, setSourceRefreshKey] = useState(0)
  const [bundleTokenMetaByValue, setBundleTokenMetaByValue] = useState<Record<string, BundleTokenMeta>>({})

  // Explicit save/load profiles (in addition to auto localStorage)
  const [profileName, setProfileName] = useState('')
  const [profileNames, setProfileNames] = useState<string[]>([])
  const [selectedProfileName, setSelectedProfileName] = useState<string>('')

  // Load per-template meta (name/type) from index
  useEffect(() => {
    const rows = loadTemplateIndex()
    const hit = rows.find((r) => String((r as any)?.id ?? '').trim() === templateId)
    if (hit) {
      setTemplateName(String((hit as any)?.name ?? '').trim() || '未命名模板')
      setTemplateType(((hit as any)?.type as any) || '家居布艺')
      return
    }
    const now = new Date().toISOString()
    const seedName = templateId === 'mvp' ? '天猫布艺 SKU规格生成器（MVP）' : '未命名模板'
    const seedType: SpecModuleType = '家居布艺'
    setTemplateName(seedName)
    setTemplateType(seedType)
    upsertTemplateMeta({
      id: templateId,
      name: seedName,
      type: seedType,
      published_at: now,
      matrix_count: null,
    })
  }, [templateId])

  // Load per-template config (fallback: migrate legacy single-config)
  useEffect(() => {
    try {
      const parsed = loadTemplateConfig(templateId) as any as PersistedConfigV1 | null
      if (!parsed) {
        // migrate legacy single-config storage if exists (best-effort)
        const legacyRaw = localStorage.getItem('tmall_sku_generator_config_v1')
        if (!legacyRaw) return
        const legacyParsed = JSON.parse(legacyRaw) as PersistedConfigV1
        if (!legacyParsed) return
        saveTemplateConfig(templateId, legacyParsed as any)
        if (legacyParsed?.merchantSkuPrefix) setMerchantSkuPrefix(legacyParsed.merchantSkuPrefix)
        if (legacyParsed?.merchantSkuSuffix !== undefined) setMerchantSkuSuffix(legacyParsed.merchantSkuSuffix)
        if (Array.isArray(legacyParsed?.sizes) && legacyParsed.sizes.length) setSizes(legacyParsed.sizes)
        if (Array.isArray(legacyParsed?.colors) && legacyParsed.colors.length) {
          setColors(
            legacyParsed.colors.map((c) => ({
              key: c.key,
              label: c.label,
              width_cm: c.width_cm,
              height_cm: c.height_cm,
              thickness_cm: (c as any).thickness_cm,
              length_cm: (c as any).length_cm,
              main_pattern_type: (c as any).main_pattern_type,
              source_code: (c as any)?.source_code ?? '',
              enabledSizes: (c as any).enabledSizes ?? {},
            })),
          )
        }
        if (Array.isArray(legacyParsed?.mainPatternTypes) && legacyParsed.mainPatternTypes.length) setMainPatternTypes(legacyParsed.mainPatternTypes)
        if (legacyParsed?.ui) {
          if (typeof legacyParsed.ui.enableColorImages === 'boolean') setEnableColorImages(legacyParsed.ui.enableColorImages)
          if (typeof legacyParsed.ui.enableSizeImages === 'boolean') setEnableSizeImages(legacyParsed.ui.enableSizeImages)
          if (typeof legacyParsed.ui.enableColorRemarks === 'boolean') setEnableColorRemarks(legacyParsed.ui.enableColorRemarks)
          if (typeof legacyParsed.ui.enableSizeRemarks === 'boolean') setEnableSizeRemarks(legacyParsed.ui.enableSizeRemarks)
          if (typeof legacyParsed.ui.enablePatternRemarks === 'boolean') setEnablePatternRemarks(legacyParsed.ui.enablePatternRemarks)
          if (typeof legacyParsed.ui.includeMainPatternType === 'boolean') setIncludeMainPatternType(legacyParsed.ui.includeMainPatternType)
        }
        return
      }
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
  }, [templateId])

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
            // phrase_preset.components 优先：selector 模式下更稳定；否则回退模板顶层 components（best-effort）
            const presetComps = Array.isArray((p as any)?.components) ? ((p as any).components as any[]) : []
            const tplComps = Array.isArray((t as any)?.components) ? ((t as any).components as any[]) : []
            const compsRaw = presetComps.length ? presetComps : tplComps
            const comps =
              compsRaw
                .map((c: any) => ({
                  model_version_id: String(c?.model_version_id ?? '').trim() || undefined,
                  width_mm: typeof c?.width_mm === 'number' ? c.width_mm : Number(c?.width_mm ?? 0),
                  height_mm: typeof c?.height_mm === 'number' ? c.height_mm : Number(c?.height_mm ?? 0),
                  quantity: typeof c?.quantity === 'number' ? c.quantity : Number(c?.quantity ?? 0),
                  spec_text: String(c?.spec_text ?? '').trim() || undefined,
                  label: String(c?.label ?? '').trim() || undefined,
                }))
                .filter((c: any) => Number.isFinite(c.width_mm) || Number.isFinite(c.height_mm) || Number.isFinite(c.quantity))
            bundleOptions.push({
              value: token,
              label: `${token}${name ? `（${name}）` : ''}${phrase ? `：${phrase}` : ''}`,
            })
            bundleMeta[token] = { mode: mode as any, phrase: phrase || undefined, name: name || undefined, components: comps }
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
      saveTemplateConfig(templateId, data as any)

      const now = new Date().toISOString()
      const name = String(templateName ?? '').trim() || (templateId === 'mvp' ? '天猫布艺 SKU规格生成器（MVP）' : '未命名模板')
      upsertTemplateMeta({
        id: templateId,
        name,
        type: templateType,
        published_at: now,
        matrix_count: computeMatrixCountFromConfig(data as any),
      })
    } catch {
      // ignore quota/disabled storage
    }
  }, [
    templateId,
    templateName,
    templateType,
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
        const row_key = `${c.key}||${s.key}`
        const enabled = c.enabledSizes?.[s.key] !== false
        const sku_status: 0 | 1 = enabled ? 1 : 0

        const rowOverride = String(specEdits?.[row_key]?.model_source_code ?? '').trim()
        const colorSource = String((c as any)?.source_code ?? '').trim()
        const sizeSource = String((s as any)?.source_code ?? '').trim()

        // Priority:
        // - row override (table) > color binding (drawer) > size binding (drawer) > prefix/suffix
        const merchantSource = rowOverride || colorSource || sizeSource
        const displaySource = rowOverride || sizeSource
        const isZSource = !!displaySource && displaySource.toUpperCase().startsWith('Z-')

        const merchant_sku = buildMerchantSku({
          merchantSkuPrefix,
          merchantSkuSuffix,
          sourceCode: merchantSource || undefined,
        })

        const attribute_spec = displaySource ? sourceLabelByValue.get(displaySource) || displaySource : ''
        const bm = displaySource ? bundleTokenMetaByValue[displaySource] : undefined
        const token_formula =
          String(specEdits?.[row_key]?.token_formula ?? '').trim() ||
          (bm && bm.mode === 'B' ? String(bm.phrase ?? '').trim() : '')
        const spec_text = `${String(c.label ?? '').trim()} ${String(s.label ?? '').trim()}`.trim()
        rows.push({
          row_key,
          color_key: c.key,
          size_key: s.key,
          color_label: c.label,
          size_label: s.label,
          merchant_sku,
          merchant_source: merchantSource || undefined,
          display_source: displaySource || undefined,
          is_z_source: isZSource || undefined,
          attribute_spec,
          token_formula,
          spec_text,
          sku_status,
          main_pattern_type: includeMainPatternType ? (c.main_pattern_type ?? null) : null,
          length_cm: fmtNum(c.length_cm),
          thickness_cm: fmtNum(c.thickness_cm),
          width_cm: fmtNum(c.width_cm),
          height_cm: fmtNum((c as any).height_cm),
        })
      }
    }
    return rows
  }, [colors, sizes, merchantSkuPrefix, merchantSkuSuffix, includeMainPatternType, sourceLabelByValue, bundleTokenMetaByValue, specEdits])

  const getSpecTextForRow = (r: SpecRow): string => String(r.spec_text ?? '').trim()

  const parsedDimsByRowKey = useMemo(() => {
    const out: Record<string, { width_cm?: string; height_cm?: string; diameter_cm?: string }> = {}
    for (const r of specRows) {
      out[r.row_key] = parseDimsFromSpecText(getSpecTextForRow(r))
    }
    return out
  }, [specRows])

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

  const highlightTextByTokens = (
    textRaw: string,
    rules: { red: string[]; green?: string[]; orange?: string[] } = { red: [] },
  ) => {
    const text = String(textRaw ?? '')
    const red = Array.from(new Set((rules.red ?? []).map((x) => String(x ?? '').trim()).filter(Boolean)))
    const orange = Array.from(new Set((rules.orange ?? []).map((x) => String(x ?? '').trim()).filter(Boolean)))

    // Prefer longer tokens to avoid partial overlaps.
    const all = Array.from(new Set([...red, ...orange])).sort((a, b) => b.length - a.length)
    if (!text || !all.length) return <>{text}</>

    const pickStyle = (tk: string) => {
      if (orange.includes(tk)) return { color: '#d46b08', fontWeight: 700 } // orange (ambiguous)
      if (red.includes(tk)) return { color: '#cf1322', fontWeight: 700 } // red (matched)
      return undefined
    }

    const out: React.ReactNode[] = []
    let i = 0
    while (i < text.length) {
      let matched: string | null = null
      for (const tk of all) {
        if (!tk) continue
        if (text.startsWith(tk, i)) {
          matched = tk
          break
        }
      }
      if (!matched) {
        out.push(text[i])
        i += 1
        continue
      }
      out.push(
        <span key={`hl-${i}-${matched}`} style={pickStyle(matched)}>
          {matched}
        </span>,
      )
      i += matched.length
    }
    return <>{out}</>
  }

  const renderFormulaWithValidation = (formulaRaw: string, v?: RowValidationDetail | null) => {
    const formula = String(formulaRaw ?? '')
    if (!formula.trim()) return <Text type="secondary">-</Text>

    const okSet = new Set((v?.okTokens ?? []).map((x) => String(x)))
    const multiSet = new Set((v?.multiTokens ?? []).map((x) => String(x)))
    const missingGroups = new Set(v?.missingGroupIndexes ?? [])

    // Render by scanning groups: `[ ... {token} ... ]`
    const nodes: React.ReactNode[] = []
    let groupIdx = 0
    for (let i = 0; i < formula.length; i++) {
      const ch = formula[i]
      if (ch !== '[') {
        nodes.push(ch)
        continue
      }
      const j = formula.indexOf(']', i + 1)
      if (j < 0) {
        nodes.push(formula.slice(i))
        break
      }
      const inner = formula.slice(i + 1, j)
      const parts: React.ReactNode[] = ['[']
      const re = /\{([^}]*)\}/g
      let last = 0
      let mm: RegExpExecArray | null
      while ((mm = re.exec(inner))) {
        const start = mm.index
        const end = re.lastIndex
        if (start > last) parts.push(inner.slice(last, start))
        const token = String(mm[1] ?? '').trim()
        const isMissingGroup = missingGroups.has(groupIdx)
        const style =
          token && okSet.has(token)
            ? { color: '#389e0d', fontWeight: 700 } // green
            : token && multiSet.has(token)
              ? { color: '#d46b08', fontWeight: 700 } // orange
              : token && isMissingGroup
                ? { color: '#cf1322', fontWeight: 700 } // red (missing)
                : undefined
        parts.push(
          <span key={`f-${groupIdx}-${start}`} style={style}>
            {'{'}
            {token || ''}
            {'}'}
          </span>,
        )
        last = end
      }
      if (last < inner.length) parts.push(inner.slice(last))
      parts.push(']')
      nodes.push(<span key={`g-${groupIdx}-${i}`}>{parts}</span>)
      groupIdx += 1
      i = j
    }
    return <div style={{ whiteSpace: 'normal', lineHeight: 1.2 }}>{nodes}</div>
  }

  const validateAllSpecRows = () => {
    const out: Record<string, RowValidationDetail> = {}
    let okCount = 0
    let badCount = 0
    for (const r of specRows) {
      const specText = getSpecTextForRow(r)
      const formula = String(r.token_formula ?? '').trim()
      const issues: string[] = []

      // 商家编码：用于“系统命中”的稳定锚点；这里做基础校验，提示运营是否需要补绑定/修正
      const merchantSku = String(r.merchant_sku ?? '').trim()
      const merchantSource = String((r as any)?.merchant_source ?? '').trim()
      if (!merchantSku) {
        issues.push('商家编码为空')
      }
      if (!merchantSource) {
        issues.push('商家编码未绑定模型/套版（请在颜色/尺寸/行级覆盖里选择来源编码）')
      } else if (merchantSku && !merchantSku.startsWith(merchantSource)) {
        issues.push(`商家编码未命中来源编码：期望以 ${merchantSource} 开头`)
      }

      // 尺寸策略（与后端 generate-by-spec 的 B/Z 口径对齐）
      const displaySource = String((r as any)?.display_source ?? '').trim()
      const bm = displaySource ? bundleTokenMetaByValue?.[displaySource] : undefined
      const dims = parsedDimsByRowKey?.[r.row_key] || {}
      const hasParsedWH = !!(dims.width_cm && dims.height_cm)
      if (displaySource.toUpperCase().startsWith('Z-')) {
        const comps = Array.isArray(bm?.components) ? (bm?.components as any[]) : []
        if (!comps.length) {
          issues.push('指定型(Z-)：未获取到套版组件尺寸（请刷新“模型/套版”下拉）')
        } else {
          for (let i = 0; i < comps.length; i += 1) {
            const c = comps[i] ?? {}
            const w = Number((c as any)?.width_mm ?? 0)
            const h = Number((c as any)?.height_mm ?? 0)
            const q = Number((c as any)?.quantity ?? 0)
            if (!(Number.isFinite(w) && w > 0 && Number.isFinite(h) && h > 0)) {
              issues.push(`指定型(Z-)：组件${i + 1} 缺少尺寸（width_mm/height_mm 必须 >0）`)
              break
            }
            if (!(Number.isFinite(q) && q > 0)) {
              issues.push(`指定型(Z-)：组件${i + 1} 缺少数量（quantity 必须 >0）`)
              break
            }
          }
        }
      }
      if (displaySource.toUpperCase().startsWith('B-')) {
        const comps = Array.isArray(bm?.components) ? (bm?.components as any[]) : []
        const anyMissing = comps.some((c) => Number((c as any)?.width_mm ?? 0) <= 0 || Number((c as any)?.height_mm ?? 0) <= 0)
        if (anyMissing && !hasParsedWH) {
          issues.push('解析型(B-)：套版组件未填尺寸，且“商品规格（网店）”未解析到宽高（后端将直接失败进异常队列）')
        } else if (!hasParsedWH) {
          issues.push('解析型(B-)：商品规格（网店）未解析到宽高（建议包含如 45X45 / 45*45 / 45×45）')
        }
      }

      // 标准模型/未绑定：若 spec_text 明显包含“尺寸段”，但解析失败，提示运营修正（避免后端尺寸条件/扣库口径走不通）
      if (!displaySource.toUpperCase().startsWith('B-') && !displaySource.toUpperCase().startsWith('Z-')) {
        const looksLikeHasDims =
          /(\d{1,4}(?:\.\d+)?)\s*[xX×\*＊]\s*(\d{1,4}(?:\.\d+)?)/.test(specText) ||
          /(直径|φ|Φ|圆形|圆)\s*[（(]?\s*\d{1,4}/.test(specText)
        if (looksLikeHasDims && !(dims.width_cm && dims.height_cm)) {
          issues.push('尺寸：商品规格（网店）包含尺寸段但未解析到宽高（建议写成 45X45 / 45*45 / 45×45 或 宽120×高150）')
        }
      }

      // Z-：不依赖公式解析；且避免任何红/绿高亮（不生成 tokens/missing）
      if (r.is_z_source) {
        const ok = issues.length === 0
        out[r.row_key] = { ok, issues, okTokens: [], multiTokens: [], missingGroupIndexes: [] }
        if (ok) okCount++
        else badCount++
        continue
      }
      if (!formula) {
        const ok = issues.length === 0
        out[r.row_key] = { ok, issues, okTokens: [], multiTokens: [], missingGroupIndexes: [] }
        if (ok) okCount++
        else badCount++
        continue
      }
      const groups = parseFormulaTokenGroups(formula)
      const okTokens: string[] = []
      const multiTokens: string[] = []
      const missingGroupIndexes: number[] = []
      for (let gi = 0; gi < groups.length; gi++) {
        const g = groups[gi]
        if (!g.tokens.length) continue
        const hits = g.tokens.filter((tk) => tk && specText.includes(tk))
        if (hits.length === 0) {
          if (!g.allowEmpty) {
            issues.push(`缺失互斥组：${g.tokens.join(' / ')}`)
            missingGroupIndexes.push(gi)
          }
          continue
        }
        if (hits.length === 1) {
          okTokens.push(hits[0])
          continue
        }
        multiTokens.push(...hits)
        issues.push(`互斥组多命中：${hits.join(' / ')}`)
      }
      const ok = issues.length === 0
      out[r.row_key] = {
        ok,
        issues,
        okTokens: Array.from(new Set(okTokens)),
        multiTokens: Array.from(new Set(multiTokens)),
        missingGroupIndexes: Array.from(new Set(missingGroupIndexes)),
      }
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

  return (
    <div style={{ padding: 16 }}>
      <Space direction="vertical" style={{ width: '100%' }} size={12}>
        <Card
          title={
            <Space wrap size={10} style={{ width: '100%', justifyContent: 'space-between' }}>
              <Space wrap size={8}>
                <Text type="secondary">模板名称</Text>
                <Input
                  style={{ width: 360 }}
                  value={templateName}
                  onChange={(e) => setTemplateName(e.target.value)}
                  placeholder="未命名模板"
                />
                <Select
                  style={{ width: 140 }}
                  value={templateType}
                  onChange={(v) => setTemplateType(v as SpecModuleType)}
                  options={[
                    { label: '家居布艺', value: '家居布艺' },
                    { label: '家居饰品', value: '家居饰品' },
                  ]}
                />
              </Space>
              <Tag color="gold">颜色分类=图案/工艺款式；尺寸可按款式禁用</Tag>
            </Space>
          }
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
                  render: (_: any, r: SpecRow) => {
                    const v = rowValidation?.[r.row_key]
                    const specText = String(r.spec_text ?? '').trim()
                    return (
                      <div style={{ whiteSpace: 'normal', lineHeight: 1.2 }}>
                        {v && !r.is_z_source
                          ? highlightTextByTokens(specText, { red: v.okTokens ?? [], orange: v.multiTokens ?? [] })
                          : specText || '-'}
                      </div>
                    )
                  },
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
                  title: '模型属性',
                  width: 210,
                  render: (_: any, r: SpecRow) => (
                    <Select
                      allowClear
                      showSearch
                      placeholder="行级覆盖：选择模型/套版"
                      loading={loadingSourceGroups}
                      popupMatchSelectWidth={false}
                      listHeight={520}
                      value={String(specEdits[r.row_key]?.model_source_code ?? '').trim() || undefined}
                      options={[
                        { label: '不覆盖（走颜色/尺寸绑定）', value: '' },
                        ...sourceGroups.map((g) => ({
                          label: g.label,
                          options: g.options,
                        })),
                      ]}
                      onChange={(v) =>
                        setSpecEdits((prev) => ({
                          ...prev,
                          [r.row_key]: { ...(prev[r.row_key] ?? {}), model_source_code: String(v ?? '') },
                        }))
                      }
                      filterOption={(input, opt) => {
                        const t = String((opt as any)?.label ?? '')
                        const vv = String((opt as any)?.value ?? '')
                        const q = String(input ?? '').trim().toLowerCase()
                        return t.toLowerCase().includes(q) || vv.toLowerCase().includes(q)
                      }}
                    />
                  ),
                },
                {
                  title: '尺寸',
                  width: 280,
                  render: (_: any, r: SpecRow) => {
                    const pill = (textRaw: string) => (
                      <span
                        style={{
                          display: 'inline-block',
                          padding: '1px 8px',
                          borderRadius: 999,
                          background: 'var(--ant-color-fill-tertiary)',
                          color: 'var(--ant-color-text-secondary)',
                          fontSize: 12,
                          lineHeight: '18px',
                          whiteSpace: 'nowrap',
                        }}
                      >
                        {textRaw}
                      </span>
                    )

                    const displaySource = String((r as any)?.display_source ?? '').trim()
                    const bm = displaySource ? bundleTokenMetaByValue?.[displaySource] : undefined

                    const dims = parsedDimsByRowKey?.[r.row_key] || {}
                    const pw = String(dims.width_cm ?? '').trim()
                    const ph = String(dims.height_cm ?? '').trim()

                    const pills: React.ReactNode[] = []

                    const pushParsed = () => {
                      if (pw && ph) pills.push(pill(`解析:${pw}×${ph}cm`))
                      else if (pw) pills.push(pill(`解析:宽${pw}cm`))
                    }

                    const pushBundleComponents = (prefix: string) => {
                      const comps = Array.isArray(bm?.components) ? (bm?.components as any[]) : []
                      if (!comps.length) {
                        pills.push(pill(`${prefix}无组件`))
                        return
                      }
                      for (let i = 0; i < comps.length; i += 1) {
                        const c = comps[i] ?? {}
                        const w = mmToCmText((c as any)?.width_mm)
                        const h = mmToCmText((c as any)?.height_mm)
                        const qn = Number((c as any)?.quantity ?? 0)
                        const q = Number.isFinite(qn) && qn > 0 ? String(Math.floor(qn) === qn ? qn : fmtNum(qn)) : ''
                        if (!w || !h) continue
                        pills.push(pill(`${prefix}${i + 1}:${w}×${h}cm${q ? `×${q}` : ''}`))
                      }
                    }

                    // Z：指定型，尺寸来自套版组件（不依赖网店规格解析）
                    if (String(r.is_z_source ?? '').trim()) {
                      pushBundleComponents('指定')
                      return pills.length ? <Space wrap size={6}>{pills}</Space> : <Text type="secondary">-</Text>
                    }

                    // B：解析型，同时展示“解析尺寸 + 模板组件尺寸”（便于对照后端命中/扣库口径）
                    if (displaySource.toUpperCase().startsWith('B-')) {
                      pushParsed()
                      pushBundleComponents('模板')
                      return pills.length ? <Space wrap size={6}>{pills}</Space> : <Text type="secondary">-</Text>
                    }

                    // 模型码/未绑定：仅展示解析尺寸（与后端 spec parser 同口径）
                    pushParsed()
                    return pills.length ? <Space wrap size={6}>{pills}</Space> : <Text type="secondary">-</Text>
                  },
                },
                {
                  title: '商家编码',
                  dataIndex: 'merchant_sku',
                  width: 150,
                  render: (v: any) => <Text code>{String(v ?? '').trim() || '-'}</Text>,
                },
                {
                  title: 'TOKEN/公式',
                  dataIndex: 'token_formula',
                  width: 360,
                  render: (_: any, r: SpecRow) => {
                    const formula = String(r.token_formula ?? '').trim()
                    if (formula && !r.is_z_source) {
                      return renderFormulaWithValidation(formula, rowValidation?.[r.row_key])
                    }
                    const spec = String(r.attribute_spec ?? '').trim()
                    if (!spec) return <Text type="secondary">-</Text>
                    return (
                      <span
                        style={{
                          display: 'inline-block',
                          padding: '1px 8px',
                          borderRadius: 999,
                          background: 'var(--ant-color-fill-tertiary)',
                          // 与“TOKEN/公式”列整体风格一致（不做红绿高亮，且适配黑底主题）
                          color: 'var(--ant-color-text-secondary)',
                          fontSize: 12,
                          lineHeight: '18px',
                          whiteSpace: 'nowrap',
                        }}
                      >
                        {spec}
                      </span>
                    )
                  },
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
                            border: '1px solid var(--app-border)',
                            borderRadius: 6,
                            overflow: 'hidden',
                            background: 'var(--app-surface)',
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
                            border: '1px solid var(--app-border)',
                            borderRadius: 6,
                            overflow: 'hidden',
                            background: 'var(--app-surface)',
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

