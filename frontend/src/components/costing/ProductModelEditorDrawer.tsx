import { useEffect, useMemo, useState } from 'react'
import {
  Alert,
  Button,
  Card,
  Col,
  Row,
  Drawer,
  Form,
  Input,
  InputNumber,
  message,
  Modal,
  Select,
  Space,
  Switch,
  Table,
  Tabs,
  Tag,
  Tooltip,
  Typography,
} from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  DeleteOutlined,
  FileTextOutlined,
  InfoCircleOutlined,
  LockOutlined,
  ReloadOutlined,
  SwapOutlined,
  UnlockOutlined,
} from '@ant-design/icons'
import { normalizeUnit } from '@/utils/unit'
import GuideDrawer from '@/components/common/GuideDrawer'
import derivePerSqmGuide from '@/guides/derive_standard_per_sqm_tablecloth_example.md?raw'

import {
  bindSkuModelVersion,
  createProductModelVersion,
  deriveStandardFromSampleVersion,
  fetchMaterials,
  fetchProductModel,
  fetchProductModelPlaceholders,
  fetchProductModelVersionLines,
  fetchProductModelVersions,
  fetchProcessModules,
  fetchProcesses,
  publishProductModelVersion,
  refreshProductModelMaterialPrices,
  syncProductModelVersionFromModules,
  updateProductModel,
  updateProductModelVersionLines,
  fetchVirtualMaterials,
} from '@/services/planner'
import type {
  Material,
  MaterialQueryParams,
  ProductModel,
  ProductModelLinesResponse,
  ProductModelMaterialLineInput,
  ProductModelPlaceholder,
  ProductModelProcessLineInput,
  ProductModelSampleSpec,
  ProductModelVersionRead,
  ProcessDetail,
  ProcessModuleQueryParams,
  ProcessModuleSummary,
  ProductModelLinesResponse as ProductModelLinesResponseModel,
  VirtualMaterial,
  VirtualMaterialQueryParams,
} from '@/types/planner'

const { Text } = Typography

type EntryContext = 'sample' | 'standard'

type ReplacementKind = 'real' | 'bom' | 'virtual'
type MaterialKind = 'real' | 'bom' | 'virtual'

type CalcMethod = 'count' | 'area' | 'perimeter' | 'width' | 'height'

type PlaceholderMappingDraft = {
  placeholder_virtual_id: string
  replacement_kind: ReplacementKind
  replacement_ref_id: string
  metadata_json?: Record<string, unknown>
}

type ModuleLinkDraft = {
  module_id: string
  sequence_order: number
  notes?: string
  metadata_json?: Record<string, unknown>
  module?: Partial<ProcessModuleSummary> | null
}

export type ProductModelEditorDrawerProps = {
  open: boolean
  onClose: () => void
  entryContext: EntryContext
  modelId: string | null
  // Optional: when entering from “标准模型版本列表”，直接定位到该版本
  initialVersionId?: string | null
}

const lockStandardSpec = (): ProductModelSampleSpec => ({
  width_mm: 1000,
  height_mm: 1000,
  quantity: 1,
  unit_label: '幅',
})

const TABLE_FONT_SIZE = 12
const FIRST_COL_WIDTH = 280

const TEAM_OPTIONS = [
  '技术部',
  '仓库部',
  '采购部',
  '生产部',
  '品控部',
  '财务部',
  '行政部',
  '销售部',
  '运营部',
].map((item) => ({ label: item, value: item }))

const MODULE_COLOR_PALETTE = [
  '#1677ff', // blue
  '#52c41a', // green
  '#faad14', // gold
  '#722ed1', // purple
  '#eb2f96', // magenta
  '#13c2c2', // cyan
  '#fa541c', // volcano
  '#2f54eb', // geekblue
  '#a0d911', // lime
  '#f5222d', // red
] as const

const hashToIndex = (s: string, mod: number) => {
  let h = 0
  for (let i = 0; i < s.length; i += 1) h = (h * 31 + s.charCodeAt(i)) >>> 0
  return mod === 0 ? 0 : h % mod
}

const hexToRgba = (hex: string, alpha: number) => {
  const h = hex.replace('#', '').trim()
  if (h.length !== 6) return `rgba(0,0,0,${alpha})`
  const r = parseInt(h.slice(0, 2), 16)
  const g = parseInt(h.slice(2, 4), 16)
  const b = parseInt(h.slice(4, 6), 16)
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}

const getModuleColor = (moduleKey?: string | null) => {
  const key = String(moduleKey ?? 'model')
  const idx = hashToIndex(key, MODULE_COLOR_PALETTE.length)
  return MODULE_COLOR_PALETTE[idx]
}

const getMaterialKindColor = (k?: MaterialKind) => {
  if (k === 'bom') return '#fa8c16'
  if (k === 'virtual') return '#722ed1'
  return '#1677ff'
}

const ModuleCodePill = ({
  code,
  color,
  size = 'md',
}: {
  code: string
  color: string
  size?: 'sm' | 'md'
}) => {
  const fontSize = size === 'sm' ? 9 : 10
  const padding = size === 'sm' ? '0px 4px' : '1px 6px'
  return (
    <span
      style={{
        display: 'inline-block',
        padding,
        borderRadius: 999,
        border: `1px solid ${hexToRgba(color, 0.35)}`,
        background: hexToRgba(color, 0.12),
        color,
        fontVariantNumeric: 'tabular-nums',
        fontWeight: 600,
        fontSize,
      }}
    >
      {code}
    </span>
  )
}

const CodePill = ({
  code,
  color,
  size = 'md',
}: {
  code: string
  color: string
  size?: 'sm' | 'md'
}) => {
  const fontSize = size === 'sm' ? 9 : 10
  const padding = size === 'sm' ? '0px 4px' : '1px 6px'
  return (
    <span
      style={{
        display: 'inline-block',
        padding,
        borderRadius: 999,
        border: `1px solid ${hexToRgba(color, 0.35)}`,
        background: hexToRgba(color, 0.1),
        color,
        fontVariantNumeric: 'tabular-nums',
        fontSize,
      }}
    >
      {code}
    </span>
  )
}

/**
 * 核心编辑器（抽屉）
 *
 * 设计目标：
 * - 作为系统核心模块：打样管理/标准模型管理两个入口复用同一套编辑器
 * - 入口上下文隔离：entryContext='sample' 仅操作 sample 版本；'standard' 仅操作 standard 版本
 * - 标准入口支持 initialVersionId：从“标准模型版本列表”进入时优先锁定该版本，避免串台
 */
export default function ProductModelEditorDrawer(props: ProductModelEditorDrawerProps) {
  const { open, onClose, entryContext, modelId, initialVersionId } = props
  const queryClient = useQueryClient()
  const [form] = Form.useForm()

  const [activeTab, setActiveTab] = useState<'basic' | 'versions' | 'lines' | 'placeholders'>('lines')
  const [versions, setVersions] = useState<ProductModelVersionRead[]>([])
  const [selectedVersionId, setSelectedVersionId] = useState<string | null>(null)

  const [sampleSpec, setSampleSpec] = useState<ProductModelSampleSpec>(lockStandardSpec())
  const [standardSpec, setStandardSpec] = useState<ProductModelSampleSpec>(lockStandardSpec())
  const [materials, setMaterials] = useState<ProductModelMaterialLineInput[]>([])
  const [processes, setProcesses] = useState<ProductModelProcessLineInput[]>([])

  const [sampleSpecLocked, setSampleSpecLocked] = useState(false)

  const [modules, setModules] = useState<ModuleLinkDraft[]>([])
  // ERP 口径：默认“从模块同步”应拉取最新模板值；如需保留已调参，再开启保留开关
  const [syncKeepOverrides, setSyncKeepOverrides] = useState(false)
  const [syncingFromModules, setSyncingFromModules] = useState(false)
  const [savingLines, setSavingLines] = useState(false)
  const [refreshingMaterialPrices, setRefreshingMaterialPrices] = useState(false)
  const [summary, setSummary] = useState<{
    material_cost: number
    labor_cost: number
    overhead_cost: number
    total_cost: number
  }>({ material_cost: 0, labor_cost: 0, overhead_cost: 0, total_cost: 0 })

  const [modulePickerOpen, setModulePickerOpen] = useState(false)
  const [modulePickerSearch, setModulePickerSearch] = useState('')
  const [modulePickerSelected, setModulePickerSelected] = useState<string[]>([])

  const [materialPickerOpen, setMaterialPickerOpen] = useState(false)
  const [processPickerOpen, setProcessPickerOpen] = useState(false)
  const [pickerRowIndex, setPickerRowIndex] = useState<number | null>(null)
  const [pickerMaterialKind, setPickerMaterialKind] = useState<MaterialKind>('bom')
  const [pickerKeyword, setPickerKeyword] = useState<string>('')
  const [pickerProcessKeyword, setPickerProcessKeyword] = useState<string>('')

  const [notesModalOpen, setNotesModalOpen] = useState(false)
  const [notesModalKind, setNotesModalKind] = useState<'material' | 'process'>('material')
  const [notesModalIndex, setNotesModalIndex] = useState<number | null>(null)
  const [notesDraft, setNotesDraft] = useState<string>('')

  const [deriveGuideOpen, setDeriveGuideOpen] = useState(false)

  // 调参面板（合并：高级参数/耗损/高级公式；工序同理）
  const [tuningOpen, setTuningOpen] = useState(false)
  const [tuningKind, setTuningKind] = useState<'material' | 'process'>('material')
  const [tuningIndex, setTuningIndex] = useState<number | null>(null)
  const [tuningFixedQty, setTuningFixedQty] = useState<number>(0)
  const [tuningCoverageRatio, setTuningCoverageRatio] = useState<number>(1)
  const [tuningLossRatePercent, setTuningLossRatePercent] = useState<number>(0)
  const [tuningBaseMinutes, setTuningBaseMinutes] = useState<number>(0)
  const [tuningUnitMinutes, setTuningUnitMinutes] = useState<number>(0)
  const [tuningRatePerMinute, setTuningRatePerMinute] = useState<number>(0)
  const [tuningDeriveTemplateDraft, setTuningDeriveTemplateDraft] = useState<any>({
    template_kind: 'linear',
    calibrate_from_sample: true,
  })

  const [placeholderMappings, setPlaceholderMappings] = useState<PlaceholderMappingDraft[]>([])
  const [skuBindCode, setSkuBindCode] = useState('')

  const desiredKind = entryContext === 'sample' ? 'sample' : 'standard'
  const specLocked = entryContext === 'standard' || sampleSpecLocked

  const AlphaIcon = (
    <span style={{ fontWeight: 700, fontFamily: 'ui-serif, Georgia, Times, serif', lineHeight: 1 }}>α</span>
  )
  const addonLabel = (label: string) => (
    // 左侧标签列：适度加宽避免换行，但不要挤占输入区
    <span style={{ display: 'inline-block', width: 100, whiteSpace: 'nowrap' }}>{label}</span>
  )

  const ALL_CALC_METHOD_OPTIONS: Array<{ label: string; value: CalcMethod }> = [
    { label: '数量', value: 'count' },
    { label: '面积', value: 'area' },
    { label: '周长', value: 'perimeter' },
    { label: '宽度', value: 'width' },
    { label: '高度', value: 'height' },
  ]

  const modelQuery = useQuery({
    queryKey: ['productModel', modelId],
    queryFn: () => fetchProductModel(modelId as string),
    enabled: open && !!modelId,
  })

  const versionsQuery = useQuery({
    queryKey: ['productModelVersions', modelId],
    queryFn: () => fetchProductModelVersions(modelId as string),
    enabled: open && !!modelId,
  })

  const linesQuery = useQuery({
    queryKey: ['productModelVersionLines', selectedVersionId],
    queryFn: () => fetchProductModelVersionLines(selectedVersionId as string),
    enabled: open && !!selectedVersionId,
  })

  const placeholdersQuery = useQuery({
    queryKey: ['productModelPlaceholders', modelId],
    queryFn: () => fetchProductModelPlaceholders(modelId as string),
    enabled: open && !!modelId && entryContext === 'sample' && activeTab === 'placeholders',
  })

  const filteredVersions = useMemo(
    () => (versions ?? []).filter((v) => String(v.version_kind) === desiredKind),
    [desiredKind, versions],
  )

  const modulePickerParams: ProcessModuleQueryParams = useMemo(
    () => ({
      search: modulePickerSearch || undefined,
      page: 1,
      page_size: 50,
    }),
    [modulePickerSearch],
  )

  const modulePickerQuery = useQuery({
    queryKey: ['processModulesForModelPicker', modulePickerParams],
    queryFn: () => fetchProcessModules(modulePickerParams),
    enabled: open && modulePickerOpen,
  })

  const modelLineMaterialPickerParams: MaterialQueryParams = useMemo(
    () => ({
      search: pickerKeyword || undefined,
      status: 'active',
      is_active: true,
      page: 1,
      page_size: 50,
      is_bom_material: pickerMaterialKind === 'bom' ? true : undefined,
    }),
    [pickerKeyword, pickerMaterialKind],
  )

  const modelLineMaterialPickerQuery = useQuery({
    queryKey: ['materialsForModelLinePicker', modelLineMaterialPickerParams],
    queryFn: () => fetchMaterials(modelLineMaterialPickerParams),
    enabled: open && materialPickerOpen && (pickerMaterialKind === 'real' || pickerMaterialKind === 'bom'),
  })

  const modelLineVirtualPickerParams: VirtualMaterialQueryParams = useMemo(
    () => ({
      search: pickerKeyword || undefined,
      status: 'active',
      page: 1,
      page_size: 50,
    }),
    [pickerKeyword],
  )

  const modelLineVirtualPickerQuery = useQuery({
    queryKey: ['virtualMaterialsForModelLinePicker', modelLineVirtualPickerParams],
    queryFn: () => fetchVirtualMaterials(modelLineVirtualPickerParams),
    enabled: open && materialPickerOpen && pickerMaterialKind === 'virtual',
  })

  const modelLineProcessPickerQuery = useQuery({
    queryKey: ['processesForModelLinePicker', pickerProcessKeyword],
    queryFn: () =>
      fetchProcesses({
        search: pickerProcessKeyword || undefined,
        status: 'active',
        page: 1,
        page_size: 50,
      }),
    enabled: open && processPickerOpen,
  })

  useEffect(() => {
    if (!open) return
    // reset tab on open (avoid selecting non-existent tabs)
    setActiveTab(entryContext === 'sample' ? 'lines' : 'versions')
    // 默认锁定（打样入口）：避免尺寸被误改导致口径/用量/用时串台
    setSampleSpecLocked(entryContext === 'sample')
  }, [open, entryContext])

  useEffect(() => {
    if (!modelQuery.data) return
    const m = modelQuery.data as ProductModel
    form.setFieldsValue({
      model_code: m.model_code,
      model_name: m.model_name,
      status: m.status,
      calc_mode: m.calc_mode,
      fixed_price: m.fixed_price,
      unit_of_measure: m.unit_of_measure,
    })

    // modules（左侧工艺模块栏）
    setModules(
      (m.modules ?? [])
        .slice()
        .map((x: any, idx: number) => ({
          module_id: String(x.module_id),
          sequence_order: Number(x.sequence_order ?? idx + 1),
          notes: x.notes ?? '',
          metadata_json: x.metadata_json ?? {},
          module: x.module ?? null,
        }))
        .sort((a, b) => a.sequence_order - b.sequence_order)
        .map((x, i) => ({ ...x, sequence_order: i + 1 })),
    )

    const meta = (m.metadata_json ?? {}) as any
    const pm = Array.isArray(meta.placeholder_mappings) ? meta.placeholder_mappings : []
    setPlaceholderMappings(
      pm
        .filter((x: any) => x && typeof x === 'object')
        .map((x: any) => ({
          placeholder_virtual_id: String(x.placeholder_virtual_id ?? ''),
          replacement_kind: (x.replacement_kind ?? 'real') as any,
          replacement_ref_id: String(x.replacement_ref_id ?? ''),
          metadata_json: x.metadata_json ?? {},
        })),
    )
  }, [modelQuery.data, form])

  useEffect(() => {
    if (!versionsQuery.data) return
    const items = (versionsQuery.data ?? []) as ProductModelVersionRead[]
    setVersions(items)
    // choose version: initialVersionId > latest draft of desired kind > first of desired kind
    if (initialVersionId && items.some((v) => v.id === initialVersionId)) {
      setSelectedVersionId(initialVersionId)
      return
    }
    const preferred =
      items.find((v) => v.version_kind === desiredKind && v.version_status === 'draft') ??
      items.find((v) => v.version_kind === desiredKind) ??
      null
    setSelectedVersionId(preferred?.id ?? null)
  }, [versionsQuery.data, desiredKind, initialVersionId])

  const hydrateLinesFromApi = (data: any) => {
    if (!data) return
    setSampleSpec(data.sample)
    setStandardSpec(data.standard)

    // normalize numeric fields (API uses Decimal-as-string)
    const normalizedMaterials = (data.materials ?? []).map((r: any) => {
      const std = r.standard_used_quantity != null ? Number(r.standard_used_quantity) : 0
      const samp = r.sample_used_quantity != null ? Number(r.sample_used_quantity) : NaN
      return {
        ...r,
        base_quantity: r.base_quantity != null ? Number(r.base_quantity) : 0,
        loss_rate: r.loss_rate != null ? Number(r.loss_rate) : 0,
        fixed_quantity: r.fixed_quantity != null ? Number(r.fixed_quantity) : 0,
        coverage_ratio: r.coverage_ratio != null ? Number(r.coverage_ratio) : 1,
        // 若本品用量为空/不可用，默认用同步过来的“默认用量”（standard）做首填
        sample_used_quantity: Number.isFinite(samp) ? samp : std,
        standard_used_quantity: std,
      }
    })
    const normalizedProcesses = (data.processes ?? []).map((p: any) => ({
      ...p,
      base_minutes: p.base_minutes != null ? Number(p.base_minutes) : p.base_minutes,
      unit_minutes: p.unit_minutes != null ? Number(p.unit_minutes) : p.unit_minutes,
      rate_per_minute: p.rate_per_minute != null ? Number(p.rate_per_minute) : p.rate_per_minute,
      piece_rate: p.piece_rate != null ? Number(p.piece_rate) : p.piece_rate,
      sample_minutes: p.sample_minutes != null ? Number(p.sample_minutes) : p.sample_minutes,
      standard_minutes: p.standard_minutes != null ? Number(p.standard_minutes) : p.standard_minutes,
    }))
    setMaterials(normalizedMaterials)
    setProcesses(normalizedProcesses)

    // standard entry forces lock
    if (entryContext === 'standard') {
      setSampleSpec(lockStandardSpec())
      setStandardSpec(lockStandardSpec())
    }
  }

  useEffect(() => {
    if (!linesQuery.data) return
    const d = linesQuery.data as ProductModelLinesResponse
    hydrateLinesFromApi(d)
  }, [linesQuery.data, entryContext])

  const refreshSummary = async () => {
    // 本地汇总：基于“当前编辑态”的用量/工时立即算（无需先保存清单）
    try {
      let materialCost = 0
      let laborCost = 0

      for (const r of materials as any[]) {
        const meta = (r.metadata_json as any) ?? {}
        const rawPrice = meta.bom_unit_price
        const unitPrice = rawPrice != null ? Number(rawPrice) : NaN
        const qty = Number(r.sample_used_quantity ?? 0)
        const lossRatePct = Number(r.loss_rate ?? 0)
        if (!Number.isFinite(unitPrice) || unitPrice < 0) continue
        if (!Number.isFinite(qty) || qty < 0) continue
        if (!Number.isFinite(lossRatePct) || lossRatePct < 0) continue
        const used = qty * (1 + lossRatePct / 100)
        materialCost += used * unitPrice
      }

      for (const p of processes as any[]) {
        const meta = (p.metadata_json as any) ?? {}
        const costType = String(p.cost_type ?? meta.cost_type ?? 'time')
        const pricingMethod = String(p.pricing_method ?? meta.pricing_method ?? 'count')
        const methodForMeasure = pricingMethod === 'fixed' ? 'count' : pricingMethod
        const mq = Math.max(0, measureQty(methodForMeasure as any, sampleSpec))

        if (costType === 'piece') {
          const pieceRate = Number(p.piece_rate ?? meta.piece_rate)
          if (!Number.isFinite(pieceRate) || pieceRate <= 0) continue
          laborCost += pieceRate * Math.max(0, Number(sampleSpec.quantity ?? 1))
          continue
        }

        const baseMin = Number(p.base_minutes ?? meta.base_minutes ?? 0)
        const unitMin = Number(p.unit_minutes ?? meta.unit_minutes ?? 0)
        const rate = Number(p.rate_per_minute ?? meta.rate_per_minute)
        if (!Number.isFinite(rate) || rate <= 0) continue
        const minutes = Math.max(0, baseMin) + Math.max(0, unitMin) * mq
        laborCost += minutes * rate
      }

      const overheadCost = 0.3 * (materialCost + laborCost)
      const totalCost = materialCost + laborCost + overheadCost
      setSummary({
        material_cost: materialCost,
        labor_cost: laborCost,
        overhead_cost: overheadCost,
        total_cost: totalCost,
      })
    } finally {}
  }

  // lines 编辑态：尺寸/用量/工时/单价变化时自动刷新汇总（轻 debounce）
  useEffect(() => {
    if (!open) return
    if (activeTab !== 'lines') return
    const t = window.setTimeout(() => {
      refreshSummary().catch(() => {})
    }, 120)
    return () => window.clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, activeTab, sampleSpec.width_mm, sampleSpec.height_mm, sampleSpec.quantity, sampleSpec.unit_label, materials, processes])

  const handleRefreshMaterialPrices = async () => {
    if (!modelId) {
      message.warning('缺少 modelId')
      return
    }
    if (refreshingMaterialPrices) return
    setRefreshingMaterialPrices(true)
    try {
      // 后端当前只提供“模型层”刷新：更新 metadata_json.{bom_unit_price,bom_unit} 快照
      // 我们将其结果 merge 到当前“版本清单编辑态”，并提示用户保存以固化到该版本。
      const refreshed = (await refreshProductModelMaterialPrices(modelId)) as ProductModelLinesResponseModel
      const refreshedMaterials = (refreshed.materials ?? []) as any[]
      const priceByKey = new Map<string, { bom_unit_price?: any; bom_unit?: any }>()
      for (const r of refreshedMaterials) {
        const key = `${String(r.material_kind)}::${String(r.material_ref_id)}`
        const meta = (r.metadata_json as any) ?? {}
        priceByKey.set(key, { bom_unit_price: meta.bom_unit_price, bom_unit: meta.bom_unit })
      }

      setMaterials((prev: any[]) =>
        (prev ?? []).map((row) => {
          const key = `${String(row.material_kind)}::${String(row.material_ref_id)}`
          const snap = priceByKey.get(key)
          if (!snap) return row
          return {
            ...row,
            metadata_json: {
              ...(row.metadata_json ?? {}),
              bom_unit_price: snap.bom_unit_price ?? (row.metadata_json as any)?.bom_unit_price,
              bom_unit: snap.bom_unit ?? (row.metadata_json as any)?.bom_unit,
            },
          }
        }),
      )

      message.success('已同步物料BOM单价快照（请点击“保存清单”固化到该版本）')
    } catch (err: any) {
      message.error(err?.response?.data?.detail ?? '同步物料价格失败')
    } finally {
      setRefreshingMaterialPrices(false)
    }
  }

  const measureQty = (method: any, spec: ProductModelSampleSpec): number => {
    const w = Number(spec.width_mm || 0)
    const h = Number(spec.height_mm || 0)
    const q = Number(spec.quantity || 1)
    if (method === 'count') return q
    if (method === 'width') return (w / 1000) * q
    if (method === 'height') return (h / 1000) * q
    if (method === 'perimeter') return (2 * (w + h)) / 1000 * q
    // area
    return (w * h) / 1_000_000 * q
  }

  const allowedCalcMethodsByBomUnit = (unitRaw: unknown): CalcMethod[] => {
    const u = String(unitRaw ?? '').trim().toLowerCase()
    if (!u) return ['count', 'area', 'perimeter', 'width', 'height']
    // square units
    if (u.includes('㎡') || u.includes('m2') || u.includes('平方')) return ['area']
    // piece/count units
    if (u.includes('个') || u.includes('pcs') || u.includes('pc')) return ['count']
    // linear units
    if (u === 'm' || u.includes('米') || (u.endsWith('m') && !u.includes('m2'))) return ['perimeter', 'width', 'height']
    return ['count', 'area', 'perimeter', 'width', 'height']
  }

  const getBomUnitForRow = (row: any) => {
    const meta = (row?.metadata_json ?? {}) as any
    return normalizeUnit(meta.bom_unit ?? meta.display_unit) || ''
  }

  // 约束：计价口径需与 BOM 单位一致（个=数量；㎡=面积；m=周长/宽/高）
  useEffect(() => {
    if (!open) return
    if (activeTab !== 'lines') return
    setMaterials((prev: any[]) => {
      if (!Array.isArray(prev) || prev.length === 0) return prev
      let changed = false
      const next = prev.map((row) => {
        const bomUnit = getBomUnitForRow(row)
        const allowed = allowedCalcMethodsByBomUnit(bomUnit)
        const cur = (row.calculation_method as CalcMethod) ?? 'count'
        if (allowed.includes(cur)) return row
        // auto-fix to first allowed to avoid invalid pricing
        const v = allowed[0] ?? 'count'
        const baseQty = Number(row.base_quantity ?? 0)
        const fixedQty = Number(row.fixed_quantity ?? 0)
        const cov = Number(row.coverage_ratio ?? 1)
        const mqSample = Math.max(0, measureQty(v, sampleSpec))
        const mqStandard = Math.max(0, measureQty(v, standardSpec))
        const sampleUsed = fixedQty + mqSample * baseQty * cov
        const standardUsed = fixedQty + mqStandard * baseQty * cov
        changed = true
        return {
          ...row,
          calculation_method: v,
          sample_used_quantity: sampleUsed,
          standard_used_quantity: standardUsed,
        }
      })
      return changed ? next : prev
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, activeTab, sampleSpec.width_mm, sampleSpec.height_mm, sampleSpec.quantity, standardSpec.width_mm, standardSpec.height_mm, standardSpec.quantity])

  const getCalcHint = (method: any, spec: ProductModelSampleSpec) => {
    const w = Number(spec.width_mm || 0)
    const h = Number(spec.height_mm || 0)
    const q = Number(spec.quantity || 1)
    if (method === 'count') return `计价量=数量；当前数量=${q}`
    if (method === 'width') return `计价量=宽(m)×数量；宽=${(w / 1000).toFixed(4)}m，数量=${q}`
    if (method === 'height') return `计价量=高(m)×数量；高=${(h / 1000).toFixed(4)}m，数量=${q}`
    if (method === 'perimeter')
      return `计价量=周长(m)×数量；周长=${(2 * (w + h) / 1000).toFixed(4)}m，数量=${q}`
    return `计价量=面积(㎡)×数量；面积=${((w * h) / 1_000_000).toFixed(4)}㎡，数量=${q}`
  }

  // 当用户修改“打样尺寸（实际尺寸）”时：按计价方式自动重算“本品用量/本品用时”（基数不变）
  // 说明：该行为与旧抽屉一致，会覆盖依赖尺寸口径的 computed 字段（sample_used_quantity / sample_minutes）。
  useEffect(() => {
    if (!open) return
    if (activeTab !== 'lines') return

    setMaterials((prev: any[]) => {
      if (!Array.isArray(prev) || prev.length === 0) return prev
      let changed = false
      const next = prev.map((r) => {
        const method = (r.calculation_method as any) ?? 'count'
        const mq = Math.max(0, measureQty(method, sampleSpec))
        const baseQty = Number(r.base_quantity ?? 0)
        const fixedQty = Number(r.fixed_quantity ?? 0)
        const cov = Number(r.coverage_ratio ?? 1)
        const sampleUsed = fixedQty + mq * baseQty * cov
        const cur = Number(r.sample_used_quantity ?? 0)
        if (Math.abs(sampleUsed - cur) > 1e-6) changed = true
        return { ...r, sample_used_quantity: sampleUsed }
      })
      return changed ? next : prev
    })

    setProcesses((prev: any[]) => {
      if (!Array.isArray(prev) || prev.length === 0) return prev
      let changed = false
      const next = prev.map((p) => {
        const meta = (p.metadata_json as any) ?? {}
        const costType = String(p.cost_type ?? meta.cost_type ?? 'time')
        if (costType !== 'time') return p
        const pricingMethod = String(p.pricing_method ?? meta.pricing_method ?? 'count')
        const methodForMeasure = pricingMethod === 'fixed' ? 'count' : pricingMethod
        const mq = Math.max(0, measureQty(methodForMeasure as any, sampleSpec))
        const baseMin = Number(p.base_minutes ?? meta.base_minutes ?? 0)
        const unitMin = Number(p.unit_minutes ?? meta.unit_minutes ?? 0)
        const minutes = Math.max(0, baseMin) + Math.max(0, unitMin) * mq
        const cur = Number(p.sample_minutes ?? meta.sample_minutes ?? 0)
        if (Math.abs(minutes - cur) > 1e-6) changed = true
        return { ...p, sample_minutes: minutes, metadata_json: { ...meta, sample_minutes: minutes } }
      })
      return changed ? next : prev
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, activeTab, sampleSpec.width_mm, sampleSpec.height_mm, sampleSpec.quantity, sampleSpec.unit_label, specLocked])

  const openMaterialPickerForRow = (rowIndex: number) => {
    setPickerRowIndex(rowIndex)
    setPickerKeyword('')
    setPickerMaterialKind('bom')
    setMaterialPickerOpen(true)
  }

  const openTuningPanelForMaterial = (rowIndex: number) => {
    setTuningKind('material')
    setTuningIndex(rowIndex)
    const row = (materials as any[])[rowIndex] ?? {}
    setTuningFixedQty(Number(row.fixed_quantity ?? 0))
    setTuningCoverageRatio(Number(row.coverage_ratio ?? 1))
    setTuningLossRatePercent(Number(row.loss_rate ?? 0))
    const cur = (row.metadata_json as any)?.derive_template
    setTuningDeriveTemplateDraft(cur ?? { template_kind: 'linear', calibrate_from_sample: true })
    setTuningOpen(true)
  }

  const openTuningPanelForProcess = (rowIndex: number) => {
    setTuningKind('process')
    setTuningIndex(rowIndex)
    const row = (processes as any[])[rowIndex] ?? {}
    setTuningBaseMinutes(Number(row.base_minutes ?? 0))
    setTuningUnitMinutes(Number(row.unit_minutes ?? 0))
    setTuningRatePerMinute(Number(row.rate_per_minute ?? 0))
    const cur = (row.metadata_json as any)?.derive_template
    setTuningDeriveTemplateDraft(cur ?? { template_kind: 'linear', calibrate_from_sample: true })
    setTuningOpen(true)
  }

  const openNotesModal = (kind: 'material' | 'process', index: number) => {
    setNotesModalKind(kind)
    setNotesModalIndex(index)
    const row = kind === 'material' ? (materials[index] as any) : (processes[index] as any)
    setNotesDraft(String(row?.notes ?? ''))
    setNotesModalOpen(true)
  }

  const applyNotesModal = () => {
    if (notesModalIndex == null) return
    const idx = notesModalIndex
    const text = notesDraft
    if (notesModalKind === 'material') {
      const next = materials.slice()
      const row = next[idx]
      if (!row) return
      next[idx] = { ...(row as any), notes: text }
      setMaterials(next)
    } else {
      const next = processes.slice()
      const row = next[idx]
      if (!row) return
      next[idx] = { ...(row as any), notes: text }
      setProcesses(next)
    }
    setNotesModalOpen(false)
  }

  const openProcessPickerForRow = (rowIndex: number) => {
    setPickerRowIndex(rowIndex)
    setPickerProcessKeyword('')
    setProcessPickerOpen(true)
  }

  const applyTuningPanel = () => {
    if (tuningIndex == null) return
    if (tuningKind === 'material') {
      const idx = tuningIndex
      const next = (materials as any[]).slice()
      const row = next[idx]
      if (!row) return
      const fixedQty = Number(tuningFixedQty ?? 0)
      const cov = Number(tuningCoverageRatio ?? 1)
      const loss = Number(tuningLossRatePercent ?? 0)
      const method = (row.calculation_method as any) ?? 'count'
      const baseQty = Number(row.base_quantity ?? 0)
      const mqSample = Math.max(0, measureQty(method, sampleSpec))
      const mqStandard = Math.max(0, measureQty(method, standardSpec))
      const sampleUsed = fixedQty + mqSample * baseQty * cov
      const standardUsed = fixedQty + mqStandard * baseQty * cov

      // 推导模板（后端：仅从 sample 版本行读取 metadata_json.derive_template）
      const deriveTemplate =
        entryContext === 'sample'
          ? {
              ...(tuningDeriveTemplateDraft ?? {}),
              template_kind: (tuningDeriveTemplateDraft?.template_kind ?? 'linear') as any,
              // 面板上的 α/覆盖率 默认也写入模板，避免模板与行参数割裂
              fixed_quantity:
                tuningDeriveTemplateDraft?.fixed_quantity != null
                  ? tuningDeriveTemplateDraft.fixed_quantity
                  : fixedQty,
              coverage_ratio:
                tuningDeriveTemplateDraft?.coverage_ratio != null
                  ? tuningDeriveTemplateDraft.coverage_ratio
                  : cov,
            }
          : undefined

      next[idx] = {
        ...row,
        fixed_quantity: fixedQty,
        coverage_ratio: cov,
        loss_rate: entryContext === 'sample' ? loss : row.loss_rate,
        sample_used_quantity: sampleUsed,
        standard_used_quantity: standardUsed,
        metadata_json: {
          ...(row.metadata_json ?? {}),
          ...(entryContext === 'sample' ? { derive_template: deriveTemplate } : {}),
        },
      }
      setMaterials(next as any)
      setTuningOpen(false)
      return
    }

    // process
    const idx = tuningIndex
    const next = (processes as any[]).slice()
    const row = next[idx]
    if (!row) return
    const base = Number(tuningBaseMinutes ?? 0)
    const unit = Number(tuningUnitMinutes ?? 0)
    const rate = Number(tuningRatePerMinute ?? 0)
    const pm = row.pricing_method ?? 'count'
    const method = pm === 'fixed' ? 'count' : pm
    const mqSample = Math.max(0, measureQty(method, sampleSpec))
    const stdMq = Math.max(0, measureQty(method, standardSpec))
    const meta = (row.metadata_json as any) ?? {}

    const deriveTemplate =
      entryContext === 'sample'
        ? {
            ...(tuningDeriveTemplateDraft ?? {}),
            template_kind: (tuningDeriveTemplateDraft?.template_kind ?? 'linear') as any,
            // 面板上的基础/计量默认写入模板（可被模板内字段覆盖）
            base_minutes:
              tuningDeriveTemplateDraft?.base_minutes != null ? tuningDeriveTemplateDraft.base_minutes : base,
            coefficient:
              tuningDeriveTemplateDraft?.coefficient != null ? tuningDeriveTemplateDraft.coefficient : unit,
          }
        : undefined

    next[idx] = {
      ...row,
      base_minutes: base,
      unit_minutes: unit,
      rate_per_minute: rate,
      standard_minutes: base + unit * stdMq,
      sample_minutes: base + unit * mqSample,
      metadata_json: {
        ...meta,
        ...(entryContext === 'sample' ? { derive_template: deriveTemplate } : {}),
      },
    }
    setProcesses(next as any)
    setTuningOpen(false)
  }

  const applyPickedMaterialToRow = (payload: {
    kind: MaterialKind
    id: string
    code?: string | null
    name?: string | null
    unit?: string | null
    category?: string | null
    defaults?: { fixed_quantity?: number; coverage_ratio?: number; loss_rate?: number }
  }) => {
    if (pickerRowIndex === null) return
    const next = materials.slice()
    const row = next[pickerRowIndex] as any
    if (!row) return
    next[pickerRowIndex] = {
      ...row,
      material_kind: payload.kind,
      material_ref_id: payload.id,
      material_code: payload.code ?? undefined,
      material_name: payload.name ?? undefined,
      fixed_quantity:
        (row.fixed_quantity == null || Number(row.fixed_quantity) === 0) &&
        payload.defaults?.fixed_quantity != null &&
        Number(payload.defaults.fixed_quantity) !== 0
          ? payload.defaults.fixed_quantity
          : row.fixed_quantity,
      coverage_ratio:
        (row.coverage_ratio == null || Number(row.coverage_ratio) === 1) &&
        payload.defaults?.coverage_ratio != null &&
        Number(payload.defaults.coverage_ratio) !== 1
          ? payload.defaults.coverage_ratio
          : row.coverage_ratio,
      loss_rate:
        (row.loss_rate == null || Number(row.loss_rate) === 0) && payload.defaults?.loss_rate != null
          ? payload.defaults.loss_rate
          : row.loss_rate,
      metadata_json: {
        ...(row.metadata_json ?? {}),
        display_unit: payload.unit ?? undefined,
        display_category: payload.category ?? undefined,
      },
    }
    setMaterials(next as any)
    setMaterialPickerOpen(false)
  }

  const applyPickedProcessToRow = (proc: ProcessDetail) => {
    if (pickerRowIndex === null) return
    const next = processes.slice()
    const row = next[pickerRowIndex] as any
    if (!row) return
    next[pickerRowIndex] = {
      ...row,
      process_id: proc.id,
      process_code: proc.process_code,
      process_name: proc.process_name,
    }
    setProcesses(next as any)
    setProcessPickerOpen(false)
  }

  const addSelectedModules = async () => {
    const items = (modulePickerQuery.data as any)?.items ?? []
    const selected = new Set(modulePickerSelected)
    const picked = items.filter((m: any) => selected.has(m.id))
    const existing = new Set(modules.map((m) => m.module_id))
    const appended: ModuleLinkDraft[] = []
    const baseOrder = modules.length
    for (let idx = 0; idx < picked.length; idx += 1) {
      const pm = picked[idx]
      if (existing.has(pm.id)) continue
      appended.push({
        module_id: pm.id,
        sequence_order: baseOrder + appended.length + 1,
        notes: '',
        metadata_json: {},
        module: pm,
      })
    }
    const nextModules = [...modules, ...appended].map((m, i) => ({ ...m, sequence_order: i + 1 }))
    setModules(nextModules)
    setModulePickerSelected([])
    setModulePickerOpen(false)

    if (!modelId) {
      message.warning('缺少 modelId')
      return
    }
    if (!selectedVersionId) {
      message.warning('请先选择版本后再同步')
      return
    }
    try {
      setSyncingFromModules(true)
      await updateProductModel(modelId, {
        modules: nextModules
          .slice()
          .sort((a, b) => a.sequence_order - b.sequence_order)
          .map((m, idx2) => ({
            module_id: m.module_id,
            sequence_order: idx2 + 1,
            notes: m.notes,
            metadata_json: m.metadata_json ?? {},
          })),
      } as any)
      const res = await syncProductModelVersionFromModules(selectedVersionId, { keep_overrides: true })
      hydrateLinesFromApi(res)
      await queryClient.invalidateQueries({ queryKey: ['productModel', modelId] })
      await queryClient.invalidateQueries({ queryKey: ['productModelVersionLines', selectedVersionId] })
      message.success('已添加模块并生成版本清单')
    } catch (err: any) {
      message.error(err?.response?.data?.detail ?? '添加模块失败')
    } finally {
      setSyncingFromModules(false)
    }
  }

  const removeModuleAndLinkedLines = async (index: number) => {
    const target = modules[index]
    if (!target) return

    Modal.confirm({
      title: '删除模块',
      content: '删除后将移除该模块，并同时删除右侧由该模块拆分出来的物料行/工序行（不会影响其它模块）。确认删除？',
      okText: '删除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        const nextModules = modules.slice()
        nextModules.splice(index, 1)
        const normalizedModules = nextModules.map((m, i) => ({ ...m, sequence_order: i + 1 }))

        const moduleId = target.module_id
        setModules(normalizedModules)
        setMaterials((prev) => prev.filter((x: any) => String(x.source_module_id ?? '') !== String(moduleId)))
        setProcesses((prev) => prev.filter((x: any) => String(x.source_module_id ?? '') !== String(moduleId)))

        if (!modelId || !selectedVersionId) return

        try {
          setSyncingFromModules(true)
          await updateProductModel(modelId, {
            modules: normalizedModules
              .slice()
              .sort((a, b) => a.sequence_order - b.sequence_order)
              .map((m, idx2) => ({
                module_id: m.module_id,
                sequence_order: idx2 + 1,
                notes: m.notes,
                metadata_json: m.metadata_json ?? {},
              })),
          } as any)
          const res = await syncProductModelVersionFromModules(selectedVersionId, { keep_overrides: true })
          hydrateLinesFromApi(res)
          await queryClient.invalidateQueries({ queryKey: ['productModel', modelId] })
          await queryClient.invalidateQueries({ queryKey: ['productModelVersionLines', selectedVersionId] })
          message.success('已删除模块并同步版本清单')
        } catch (err: any) {
          message.error(err?.response?.data?.detail ?? '删除模块失败')
        } finally {
          setSyncingFromModules(false)
        }
      },
    })
  }

  const handleSyncFromModules = async () => {
    if (!modelId) {
      message.warning('缺少 modelId')
      return
    }
    if (!selectedVersionId) {
      message.warning('请先选择版本')
      return
    }
    const doSync = async () => {
      setSyncingFromModules(true)
      try {
        const res = await syncProductModelVersionFromModules(selectedVersionId, { keep_overrides: syncKeepOverrides })
        hydrateLinesFromApi(res)
        await queryClient.invalidateQueries({ queryKey: ['productModelVersionLines', selectedVersionId] })
        message.success(syncKeepOverrides ? '已同步到版本清单（保留版本层调参）' : '已同步到版本清单（覆盖版本层调参）')
      } catch (err: any) {
        message.warning(err?.response?.data?.detail ?? '同步失败（不影响继续编辑/保存）')
      } finally {
        setSyncingFromModules(false)
      }
    }

    if (!syncKeepOverrides) {
      Modal.confirm({
        title: '确认同步并覆盖版本层调参？',
        content: '关闭“保留调参”后，同步会以模块内容覆盖版本清单的用量/工时等字段。建议先保存或复制关键参数。',
        okText: '继续同步（覆盖）',
        cancelText: '取消',
        onOk: doSync,
      })
      return
    }
    await doSync()
  }

  const handleSaveLines = async () => {
    if (!modelId) {
      message.warning('缺少 modelId')
      return
    }
    if (!selectedVersionId) {
      message.warning('请先选择版本')
      return
    }

    const badMatIdx = materials.findIndex((m: any) => !String(m.material_ref_id || '').trim())
    if (badMatIdx >= 0) {
      message.error(`物料组存在未选择物料的行：第 ${badMatIdx + 1} 行，请先删除或重新选择`)
      return
    }
    const badProcIdx = processes.findIndex((p: any) => !String(p.process_id || '').trim())
    if (badProcIdx >= 0) {
      message.error(`工序组存在未选择工序的行：第 ${badProcIdx + 1} 行，请先删除或重新选择`)
      return
    }

    // 保存清单前做“占位符兜底替换”（保证清单可计价/可推导）
    const mappingByPlaceholderId = new Map(
      placeholderMappings.map((m) => [String(m.placeholder_virtual_id || '').trim(), m] as const),
    )
    const placeholderHits = materials
      .map((row: any, idx: number) => ({ row, idx }))
      .filter(({ row }) => mappingByPlaceholderId.has(String(row.material_ref_id || '').trim()))

    let replacedMaterials = materials.slice() as any[]
    if (placeholderHits.length) {
      const missing: Array<{ idx: number; label: string }> = []
      replacedMaterials = materials.map((row: any, index: number) => {
        const phId = String(row.material_ref_id || '').trim()
        const mapping = mappingByPlaceholderId.get(phId)
        if (!mapping) return row
        if (!mapping.replacement_kind || !mapping.replacement_ref_id) {
          const label = String(row.material_code || row.material_name || phId)
          missing.push({ idx: index, label })
          return row
        }
        const meta = (mapping.metadata_json ?? {}) as any
        if (mapping.replacement_kind === 'virtual' && String(meta.virtual_kind || '').trim() === 'placeholder') {
          const label = String(row.material_code || row.material_name || phId)
          missing.push({ idx: index, label })
          return row
        }
        return {
          ...row,
          material_kind: mapping.replacement_kind,
          material_ref_id: mapping.replacement_ref_id,
          material_code: meta.display_code ?? row.material_code,
          material_name: meta.display_name ?? row.material_name,
          metadata_json: {
            ...(row.metadata_json ?? {}),
            placeholder_replaced: true,
            placeholder_virtual_id: phId,
            display_unit: meta.display_unit ?? (row.metadata_json ?? {}).display_unit,
            display_category: meta.display_category ?? (row.metadata_json ?? {}).display_category,
          },
        }
      })
      if (missing.length) {
        message.error(`占位符映射缺失/不合法：${missing.slice(0, 3).map((x) => `第${x.idx + 1}行(${x.label})`).join('，')}${missing.length > 3 ? '…' : ''}`)
        return
      }
    }

    await updateProductModelVersionLines(selectedVersionId, {
      sample: entryContext === 'standard' ? lockStandardSpec() : sampleSpec,
      standard: lockStandardSpec(),
      materials: replacedMaterials,
      processes,
    } as any)
    await queryClient.invalidateQueries({ queryKey: ['productModelVersionLines', selectedVersionId] })
    message.success('已保存清单')
  }

  const saveBasicMutation = useMutation({
    mutationFn: async () => {
      if (!modelId) return
      const values = await form.validateFields()
      const meta = {
        placeholder_mappings: placeholderMappings,
      }
      await updateProductModel(modelId, {
        model_name: values.model_name,
        status: values.status,
        calc_mode: values.calc_mode,
        fixed_price: values.calc_mode === 'fixed' ? values.fixed_price : null,
        unit_of_measure: values.unit_of_measure,
        metadata_json: meta as any,
      } as any)
    },
    onSuccess: async () => {
      message.success('已保存基础信息')
      await queryClient.invalidateQueries({ queryKey: ['productModel', modelId] })
    },
    onError: (err: any) => message.error(err?.response?.data?.detail ?? '保存失败'),
  })

  const runSaveLines = async () => {
    if (savingLines) return
    setSavingLines(true)
    try {
      await handleSaveLines()
      if (entryContext === 'sample') setSampleSpecLocked(true)
    } catch (err: any) {
      message.error(err?.response?.data?.detail ?? err?.message ?? '保存清单失败')
    } finally {
      setSavingLines(false)
    }
  }

  const deriveMutation = useMutation({
    mutationFn: async () => {
      if (!selectedVersionId) throw new Error('请先选择打样版本')
      return await deriveStandardFromSampleVersion(selectedVersionId, {
        target_mode: 'create_new',
        apply_to: 'both',
      } as any)
    },
    onSuccess: async (res: any) => {
      message.success('已生成标准版本（草稿）')
      await versionsQuery.refetch()
      if (res?.standard_version_id) {
        setSelectedVersionId(res.standard_version_id)
      }
    },
    onError: (err: any) => message.error(err?.response?.data?.detail ?? '生成标准模型失败'),
  })

  const publishMutation = useMutation({
    mutationFn: async () => {
      if (!selectedVersionId) throw new Error('请先选择标准版本')
      return await publishProductModelVersion(selectedVersionId, {})
    },
    onSuccess: async () => {
      message.success('已发布标准版本')
      await versionsQuery.refetch()
    },
    onError: (err: any) => message.error(err?.response?.data?.detail ?? '发布失败'),
  })

  const bindSkuMutation = useMutation({
    mutationFn: async () => {
      const sku = skuBindCode.trim()
      if (!sku) throw new Error('请输入 SKU')
      if (!selectedVersionId) throw new Error('请先选择标准版本')
      await bindSkuModelVersion({ sku_code: sku, model_version_id: selectedVersionId, metadata_json: {} })
    },
    onSuccess: () => {
      message.success('SKU 已绑定')
      setSkuBindCode('')
    },
    onError: (err: any) => message.error(err?.response?.data?.detail ?? 'SKU 绑定失败'),
  })

  const createVersion = async () => {
    if (!modelId) return
    try {
      const created = await createProductModelVersion(modelId, { version_kind: desiredKind as any, metadata_json: {} })
      await versionsQuery.refetch()
      setSelectedVersionId(created.id)
      message.success('已创建版本')
    } catch (err: any) {
      message.error(err?.response?.data?.detail ?? '创建版本失败')
    }
  }

  const placeholderRows = useMemo(() => {
    const placeholders = (placeholdersQuery.data ?? []) as ProductModelPlaceholder[]
    const map = new Map(placeholderMappings.map((m) => [m.placeholder_virtual_id, m]))
    return placeholders.map((ph) => ({
      ph,
      mapping: map.get(ph.virtual_material_id),
    }))
  }, [placeholdersQuery.data, placeholderMappings])

  const updateMapping = (placeholderId: string, patch: Partial<PlaceholderMappingDraft>) => {
    setPlaceholderMappings((prev) => {
      const idx = prev.findIndex((x) => x.placeholder_virtual_id === placeholderId)
      if (idx < 0) {
        return [...prev, { placeholder_virtual_id: placeholderId, replacement_kind: 'real', replacement_ref_id: '', ...patch } as any]
      }
      const next = prev.slice()
      next[idx] = { ...next[idx], ...patch }
      return next
    })
  }

  return (
    <Drawer
      open={open}
      onClose={onClose}
      width={1320}
      destroyOnClose
      title={entryContext === 'sample' ? '打样管理' : '标准模型管理'}
      extra={
        <Space>
          <Button onClick={() => saveBasicMutation.mutate()} loading={saveBasicMutation.isPending} disabled={!modelId}>
            保存基础信息
          </Button>
          <Button type="primary" onClick={runSaveLines} loading={savingLines} disabled={!selectedVersionId}>
            保存清单
          </Button>
        </Space>
      }
    >
      {!modelId ? <Alert type="warning" showIcon message="缺少 modelId" /> : null}

      <Tabs
        activeKey={activeTab}
        onChange={(k) => setActiveTab(k as any)}
        items={[
          {
            key: 'basic',
            label: '基础信息',
            children: (
              <Card size="small" title="模型主档">
                <Form form={form} layout="vertical">
                  <Space wrap>
                    <Form.Item label="总编码" name="model_code">
                      <Input disabled style={{ width: 160 }} />
                    </Form.Item>
                    <Form.Item label="模型名称" name="model_name" rules={[{ required: true, message: '请输入模型名称' }]}>
                      <Input style={{ width: 260 }} />
                    </Form.Item>
                    <Form.Item label="状态" name="status">
                      <Select
                        style={{ width: 140 }}
                        options={[
                          { label: '草稿', value: 'draft' },
                          { label: '启用', value: 'active' },
                          { label: '停用', value: 'inactive' },
                        ]}
                      />
                    </Form.Item>
                    <Form.Item label="计算模式" name="calc_mode">
                      <Select
                        style={{ width: 180 }}
                        options={[
                          { label: '比例', value: 'ratio' },
                          { label: '一口价', value: 'fixed' },
                          { label: '独立', value: 'independent' },
                        ]}
                      />
                    </Form.Item>
                    <Form.Item label="一口价" name="fixed_price">
                      <InputNumber style={{ width: 160 }} min={0} precision={4} />
                    </Form.Item>
                    <Form.Item label="单位口径" name="unit_of_measure">
                      <Input style={{ width: 140 }} />
                    </Form.Item>
                  </Space>
                </Form>
              </Card>
            ),
          },
          {
            key: 'versions',
            label: entryContext === 'sample' ? '打样版本' : '标准版本',
            children: (
              <Space direction="vertical" size={12} style={{ width: '100%' }}>
                <Card size="small" title="版本选择">
                  <Space wrap>
                    <Select
                      style={{ width: 520 }}
                      placeholder={entryContext === 'sample' ? '选择打样版本（sample）' : '选择标准版本（standard）'}
                      value={selectedVersionId ?? undefined}
                      loading={versionsQuery.isLoading}
                      options={filteredVersions.map((v) => ({
                        value: v.id,
                        label: `${v.version_status}${v.version_label ? ` / ${v.version_label}` : ''}`,
                      }))}
                      onChange={(v) => setSelectedVersionId(v)}
                      allowClear
                    />
                    <Button onClick={createVersion} disabled={!modelId}>
                      新建{entryContext === 'sample' ? '打样' : '标准'}版本
                    </Button>
                    <Button onClick={() => versionsQuery.refetch()} disabled={!modelId}>
                      刷新
                    </Button>
                  </Space>
                  <div style={{ marginTop: 8 }}>
                    <Text type="secondary">仅显示 {desiredKind} 版本，避免两个栏目文案互串。</Text>
                  </div>
                </Card>
                {entryContext === 'sample' ? (
                  <Card size="small" title="一键生成标准版本（草稿）">
                    <Space wrap>
                      <Button type="primary" onClick={() => deriveMutation.mutate()} loading={deriveMutation.isPending} disabled={!selectedVersionId}>
                        生成标准模型
                      </Button>
                      <Text type="secondary">从当前打样版本推导生成 standard draft。</Text>
                    </Space>
                  </Card>
                ) : (
                  <Card size="small" title="发布 / SKU 绑定">
                    <Space wrap>
                      <Button type="primary" onClick={() => publishMutation.mutate()} loading={publishMutation.isPending} disabled={!selectedVersionId}>
                        发布该标准版本
                      </Button>
                      <Input
                        style={{ width: 260 }}
                        value={skuBindCode}
                        onChange={(e) => setSkuBindCode(e.target.value)}
                        placeholder="输入 SKU"
                        allowClear
                      />
                      <Button type="primary" onClick={() => bindSkuMutation.mutate()} loading={bindSkuMutation.isPending} disabled={!selectedVersionId || !skuBindCode.trim()}>
                        绑定SKU
                      </Button>
                    </Space>
                    <div style={{ marginTop: 8 }}>
                      <Tag color="blue">口径固定：1000×1000×1</Tag>
                    </div>
                  </Card>
                )}
              </Space>
            ),
          },
          ...(entryContext === 'sample'
            ? [
                {
                  key: 'placeholders',
                  label: '占位符映射',
                  children: (
                    <Space direction="vertical" size={12} style={{ width: '100%' }}>
                      <Alert
                        type="info"
                        showIcon
                        message="打样管理：占位符兜底物料"
                        description="占位符仅存在于模块模板层；保存/推导前会用映射替换为兜底物料。"
                      />
                      <Table
                        rowKey={(r: any) => r.ph.virtual_material_id}
                        loading={placeholdersQuery.isLoading}
                        dataSource={placeholderRows}
                        pagination={false}
                        size="small"
                        columns={[
                          {
                            title: '占位符',
                            width: 220,
                            render: (_: any, row: any) => row.ph.placeholder_symbol ?? row.ph.name ?? row.ph.virtual_code,
                          },
                          { title: '分类', width: 120, render: (_: any, row: any) => row.ph.constraint_category ?? '-' },
                          { title: '单位', width: 90, render: (_: any, row: any) => row.ph.unit ?? '-' },
                          {
                            title: '兜底类型',
                            width: 140,
                            render: (_: any, row: any) => (
                              <Select
                                style={{ width: 120 }}
                                value={row.mapping?.replacement_kind ?? 'real'}
                                options={[
                                  { label: '真实', value: 'real' },
                                  { label: 'BOM', value: 'bom' },
                                  { label: '虚拟', value: 'virtual' },
                                ]}
                                onChange={(v) => updateMapping(row.ph.virtual_material_id, { replacement_kind: v as any })}
                              />
                            ),
                          },
                          {
                            title: '兜底ID',
                            render: (_: any, row: any) => (
                              <Input
                                value={row.mapping?.replacement_ref_id ?? ''}
                                placeholder="material_id / virtual_material_id"
                                onChange={(e) => updateMapping(row.ph.virtual_material_id, { replacement_ref_id: e.target.value })}
                              />
                            ),
                          },
                        ]}
                      />
                      <Button onClick={() => saveBasicMutation.mutate()} loading={saveBasicMutation.isPending} disabled={!modelId}>
                        保存映射到主档
                      </Button>
                    </Space>
                  ),
                },
              ]
            : []),
          {
            key: 'lines',
            label: '清单编辑',
            children: (
              <Space direction="vertical" size={12} style={{ width: '100%' }}>
                <Card
                  size="small"
                  title="版本选择"
                  extra={
                    <Text type="secondary">
                      {selectedVersionId ? `当前版本：${selectedVersionId.slice(0, 8)}…` : '未选择版本'}
                    </Text>
                  }
                >
                  <Space wrap>
                    <Select
                      style={{ width: 520 }}
                      placeholder={entryContext === 'sample' ? '选择打样版本（sample）' : '选择标准版本（standard）'}
                      value={selectedVersionId ?? undefined}
                      loading={versionsQuery.isLoading}
                      options={filteredVersions.map((v) => ({
                        value: v.id,
                        label: `${v.version_status}${v.version_label ? ` / ${v.version_label}` : ''}`,
                      }))}
                      onChange={(v) => setSelectedVersionId(v)}
                      allowClear
                    />
                    <Button onClick={createVersion} disabled={!modelId}>
                      新建{entryContext === 'sample' ? '打样' : '标准'}版本
                    </Button>
                    <Button onClick={() => versionsQuery.refetch()} disabled={!modelId} icon={<ReloadOutlined />}>
                      刷新
                    </Button>
                  </Space>
                </Card>

                {entryContext === 'standard' ? (
                  <Alert
                    type="warning"
                    showIcon
                    message="标准模型编辑口径"
                    description="标准模型固定 1000×1000×1（1㎡）。编辑时请以该口径填写基数/分钟等参数。"
                  />
                ) : null}

                <Card
                  size="small"
                  title={entryContext === 'standard' ? '口径（锁定）' : '打样尺寸'}
                  extra={
                    <Space>
                      <Tag color="blue">sample: {String(sampleSpec.width_mm)}×{String(sampleSpec.height_mm)}×{String(sampleSpec.quantity)}</Tag>
                      <Tag color="purple">standard: 1000×1000×1</Tag>
                    </Space>
                  }
                >
                  <Space wrap>
                    <InputNumber
                      min={0}
                      precision={2}
                      value={Number(sampleSpec.width_mm ?? 0) / 10}
                      onChange={(v) => setSampleSpec({ ...sampleSpec, width_mm: Number(v ?? 0) * 10 })}
                      addonBefore="宽(cm)"
                      disabled={specLocked}
                    />
                    <InputNumber
                      min={0}
                      precision={2}
                      value={Number(sampleSpec.height_mm ?? 0) / 10}
                      onChange={(v) => setSampleSpec({ ...sampleSpec, height_mm: Number(v ?? 0) * 10 })}
                      addonBefore="高(cm)"
                      disabled={specLocked}
                    />
                    <InputNumber
                      min={1}
                      precision={0}
                      value={sampleSpec.quantity}
                      onChange={(v) => setSampleSpec({ ...sampleSpec, quantity: Number(v ?? 1) })}
                      addonBefore="数量"
                      disabled={specLocked}
                    />
                    <Space.Compact>
                      <Input
                        style={{ width: 140 }}
                        value={sampleSpec.unit_label}
                        onChange={(e) => setSampleSpec({ ...sampleSpec, unit_label: e.target.value || '幅' })}
                        addonBefore="单位"
                        disabled={specLocked}
                      />
                      <Button
                        title={specLocked ? '已锁定：尺寸不可修改' : '点击锁定：尺寸不再变化'}
                        disabled={entryContext === 'standard'}
                        icon={specLocked ? <LockOutlined /> : <UnlockOutlined />}
                        onClick={() => {
                          if (entryContext === 'standard') return
                          if (sampleSpecLocked) {
                            Modal.confirm({
                              title: '解锁并允许修改尺寸？',
                              content:
                                '解锁后修改打样尺寸会触发联动重算：系统将按新尺寸口径自动重算并覆盖“本品用量/本品用时”等默认计算值。若你之前手动改过这些值，请在修改尺寸后重新核对并必要时重新调整。',
                              okText: '解锁并继续',
                              cancelText: '取消',
                              onOk: () => {
                                message.info('已保存清单并锁定打样尺寸。如需修改尺寸，请先点击右侧“解锁”，系统会按新尺寸重算本品用量/用时。')
                                setSampleSpecLocked(false)
                                // 立即按当前尺寸口径重算，避免保留旧尺寸下的手工值
                                setMaterials((prev: any[]) =>
                                  (prev ?? []).map((r) => {
                                    const method = (r.calculation_method as any) ?? 'count'
                                    const mq = Math.max(0, measureQty(method, sampleSpec))
                                    const baseQty = Number(r.base_quantity ?? 0)
                                    const fixedQty = Number(r.fixed_quantity ?? 0)
                                    const cov = Number(r.coverage_ratio ?? 1)
                                    return { ...r, sample_used_quantity: fixedQty + mq * baseQty * cov }
                                  }),
                                )
                                setProcesses((prev: any[]) =>
                                  (prev ?? []).map((p) => {
                                    const meta = (p.metadata_json as any) ?? {}
                                    const costType = String(p.cost_type ?? meta.cost_type ?? 'time')
                                    if (costType !== 'time') return p
                                    const pricingMethod = String(p.pricing_method ?? meta.pricing_method ?? 'count')
                                    const methodForMeasure = pricingMethod === 'fixed' ? 'count' : pricingMethod
                                    const mq = Math.max(0, measureQty(methodForMeasure as any, sampleSpec))
                                    const baseMin = Number(p.base_minutes ?? meta.base_minutes ?? 0)
                                    const unitMin = Number(p.unit_minutes ?? meta.unit_minutes ?? 0)
                                    const minutes = Math.max(0, baseMin) + Math.max(0, unitMin) * mq
                                    return { ...p, sample_minutes: minutes, metadata_json: { ...meta, sample_minutes: minutes } }
                                  }),
                                )
                              },
                            })
                            return
                          }
                          setSampleSpecLocked(true)
                        }}
                      />
                    </Space.Compact>
                  </Space>
                </Card>

                <Card
                  size="small"
                  title="计算汇总"
                  extra={
                    <Space>
                      <Button loading={refreshingMaterialPrices} onClick={() => void handleRefreshMaterialPrices()} disabled={!modelId}>
                        同步物料价格
                      </Button>
                    </Space>
                  }
                >
                  <Space wrap>
                    <Tag color="blue">物料费：{summary.material_cost.toFixed(2)}</Tag>
                    <Tag color="purple">人工费：{summary.labor_cost.toFixed(2)}</Tag>
                    <Tag color="orange">管理费(30%)：{summary.overhead_cost.toFixed(2)}</Tag>
                    <Tag color="green">合计：{summary.total_cost.toFixed(2)}</Tag>
                  </Space>
                  <Text type="secondary" style={{ display: 'block', marginTop: 8 }}>
                    说明：汇总按当前编辑态即时计算；“同步物料价格”只刷新 BOM 单价快照，需点“保存清单”才会固化到该版本。
                  </Text>
                </Card>

                <Row gutter={12}>
                  <Col span={6}>
                    <Card
                      size="small"
                      title="工艺模块"
                      extra={
                        <Space direction="vertical" size={4}>
                          <Space wrap>
                            <Button onClick={() => setModulePickerOpen(true)} disabled={!modelId}>
                              添加
                            </Button>
                            <Button
                              loading={syncingFromModules}
                              onClick={() => void handleSyncFromModules()}
                              disabled={!selectedVersionId}
                              type="primary"
                            >
                              从模块同步
                            </Button>
                          </Space>
                          <Tooltip
                            getPopupContainer={() => document.body}
                            title={syncKeepOverrides ? '同步时保留版本清单已调参字段' : '同步时以模块内容覆盖版本清单调参'}
                          >
                            <Space size={6}>
                              <span style={{ fontSize: 12, color: '#8c8c8c' }}>保留调参</span>
                              <Switch
                                size="small"
                                checked={syncKeepOverrides}
                                onChange={(checked) => setSyncKeepOverrides(checked)}
                              />
                            </Space>
                          </Tooltip>
                        </Space>
                      }
                    >
                      <Table
                        rowKey="module_id"
                        dataSource={modules}
                        pagination={false}
                        size="small"
                        style={{ fontSize: TABLE_FONT_SIZE }}
                        columns={[
                          {
                            title: '编码',
                            width: 80,
                            render: (_: any, r: any) => {
                              const code = r.module?.module_code ?? '-'
                              const color = getModuleColor(r.module_id)
                              return <ModuleCodePill code={code} color={color} size="sm" />
                            },
                          },
                          { title: '名称', render: (_: any, r: any) => r.module?.module_name ?? '-' },
                          {
                            title: '',
                            width: 44,
                            render: (_: any, __: any, idx: number) => (
                              <Button
                                size="small"
                                type="text"
                                danger
                                icon={<DeleteOutlined />}
                                title="删除模块"
                                onClick={() => void removeModuleAndLinkedLines(idx)}
                              />
                            ),
                          },
                        ]}
                      />
                      <Text type="secondary" style={{ display: 'block', marginTop: 8 }}>
                        模块仅作为模板来源；所有调参最终落在右侧版本清单。
                      </Text>
                    </Card>
                  </Col>

                  <Col span={18}>
                    <Card size="small" title="物料组">
                      <Table
                        rowKey={(r: any, idx?: number) => r.id ?? `mat-${idx ?? 0}`}
                        dataSource={materials as any}
                        pagination={false}
                        size="small"
                        style={{ fontSize: TABLE_FONT_SIZE }}
                        onRow={(r: any) => {
                          const key = r.source_module_id ?? r.source_module_code ?? 'model'
                          const color = getModuleColor(String(key))
                          return { style: { background: hexToRgba(color, 0.06) } }
                        }}
                        columns={[
                          {
                            title: '物料',
                            width: FIRST_COL_WIDTH,
                            render: (_: any, r: any) => (
                              <Space>
                                {r.material_code ? (
                                  <CodePill code={r.material_code} color={getMaterialKindColor(r.material_kind as MaterialKind)} size="sm" />
                                ) : null}
                                <span style={{ whiteSpace: 'nowrap', fontSize: 12 }}>{r.material_name ?? r.material_ref_id}</span>
                              </Space>
                            ),
                          },
                          {
                            title: '操作',
                            width: 120,
                            render: (_: any, __: any, idx: number) => (
                              <Space size={2}>
                                <Button size="small" type="text" icon={<SwapOutlined />} title="替换" onClick={() => openMaterialPickerForRow(idx)} />
                                <Button
                                  size="small"
                                  type="text"
                                  icon={AlphaIcon}
                                  title="调参面板"
                                  onClick={() => openTuningPanelForMaterial(idx)}
                                />
                              </Space>
                            ),
                          },
                          {
                            title: '本品用量',
                            width: 160,
                            render: (_: any, r: any, idx: number) => (
                              <Space size={6} style={{ width: '100%' }} align="center">
                                <InputNumber
                                  min={0}
                                  precision={2}
                                  value={r.sample_used_quantity}
                                  onChange={(v) => {
                                    const next = (materials as any[]).slice()
                                    next[idx] = { ...next[idx], sample_used_quantity: Number(v ?? 0) }
                                    setMaterials(next as any)
                                  }}
                                  style={{ width: '100%' }}
                                />
                                <Tooltip
                                  getPopupContainer={() => document.body}
                                  title={
                                    <div>
                                      <div>
                                        默认用量：
                                        {Number.isFinite(Number(r.standard_used_quantity)) ? Number(r.standard_used_quantity).toFixed(2) : '-'}
                                      </div>
                                      <div style={{ color: '#8c8c8c' }}>{getCalcHint(r.calculation_method, sampleSpec)}</div>
                                    </div>
                                  }
                                >
                                  <InfoCircleOutlined style={{ color: '#8c8c8c', fontSize: 12 }} />
                                </Tooltip>
                              </Space>
                            ),
                          },
                          {
                            title: '计价',
                            width: 90,
                            render: (_: any, r: any, idx: number) => (
                              <Space style={{ width: '100%' }} align="center" size={6}>
                                <Select
                                  getPopupContainer={() => document.body}
                                  value={r.calculation_method}
                                  style={{ width: 78, fontSize: 12 }}
                                  dropdownStyle={{ fontSize: 12 }}
                                  options={(() => {
                                    const bomUnit = getBomUnitForRow(r)
                                    const allowed = new Set(allowedCalcMethodsByBomUnit(bomUnit))
                                    return ALL_CALC_METHOD_OPTIONS.map((o) => ({
                                      ...o,
                                      disabled: !allowed.has(o.value),
                                    }))
                                  })()}
                                  onChange={(v) => {
                                    const next = (materials as any[]).slice()
                                    const baseQty = Number(next[idx].base_quantity ?? 0)
                                    const fixedQty = Number(next[idx].fixed_quantity ?? 0)
                                    const cov = Number(next[idx].coverage_ratio ?? 1)
                                    const mqSample = Math.max(0, measureQty(v, sampleSpec))
                                    const mqStandard = Math.max(0, measureQty(v, standardSpec))
                                    const sampleUsed = fixedQty + mqSample * baseQty * cov
                                    const standardUsed = fixedQty + mqStandard * baseQty * cov
                                    next[idx] = {
                                      ...next[idx],
                                      calculation_method: v,
                                      base_quantity: baseQty,
                                      sample_used_quantity: sampleUsed,
                                      standard_used_quantity: standardUsed,
                                    }
                                    setMaterials(next as any)
                                  }}
                                />
                                <Tooltip getPopupContainer={() => document.body} title={getCalcHint(r.calculation_method, sampleSpec)}>
                                  <InfoCircleOutlined style={{ color: '#8c8c8c', fontSize: 12 }} />
                                </Tooltip>
                              </Space>
                            ),
                          },
                          {
                            title: 'BOM单价/单位',
                            width: 170,
                            render: (_: any, r: any, idx: number) => {
                              const meta = (r.metadata_json as any) ?? {}
                              const price = meta.bom_unit_price != null ? Number(meta.bom_unit_price) : undefined
                              const unit = normalizeUnit(meta.bom_unit ?? meta.display_unit) || ''
                              return (
                                <Space size={6} style={{ width: '100%' }} align="center">
                                  <InputNumber
                                    min={0}
                                    precision={4}
                                    value={Number.isFinite(price as any) ? price : undefined}
                                    onChange={(v) => {
                                      const next = (materials as any[]).slice()
                                      next[idx] = {
                                        ...next[idx],
                                        metadata_json: {
                                          ...(next[idx]?.metadata_json ?? {}),
                                          bom_unit_price: v == null ? null : Number(v),
                                        },
                                      }
                                      setMaterials(next as any)
                                    }}
                                    style={{ width: 110 }}
                                    placeholder="单价"
                                  />
                                  <Tag style={{ marginInlineStart: 0 }}>{unit || '-'}</Tag>
                                </Space>
                              )
                            },
                          },
                          {
                            title: '小计',
                            width: 110,
                            render: (_: any, r: any) => {
                              const meta = (r.metadata_json as any) ?? {}
                              const unitPrice = meta.bom_unit_price != null ? Number(meta.bom_unit_price) : NaN
                              const qty = Number(r.sample_used_quantity ?? 0)
                              const lossRatePct = Number(r.loss_rate ?? 0)
                              if (Number.isFinite(unitPrice) && Number.isFinite(qty) && Number.isFinite(lossRatePct)) {
                                const used = qty * (1 + Math.max(0, lossRatePct) / 100)
                                return (used * unitPrice).toFixed(2)
                              }
                              return '-'
                            },
                          },
                          {
                            title: '备注',
                            width: 60,
                            render: (_: any, r: any, idx: number) => {
                              const has = String(r.notes ?? '').trim().length > 0
                              return (
                                <Button
                                  size="small"
                                  type="text"
                                  icon={<FileTextOutlined style={{ color: has ? '#1677ff' : '#bfbfbf' }} />}
                                  title={has ? '查看/编辑备注' : '添加备注'}
                                  onClick={() => openNotesModal('material', idx)}
                                />
                              )
                            },
                          },
                        ]}
                      />
                    </Card>

                    <Card size="small" title="工序组" style={{ marginTop: 12 }}>
                      <Table
                        rowKey={(r: any, idx?: number) => r.id ?? `proc-${idx ?? 0}`}
                        dataSource={processes as any}
                        pagination={false}
                        size="small"
                        style={{ fontSize: TABLE_FONT_SIZE }}
                        onRow={(r: any) => {
                          const key = r.source_module_id ?? r.source_module_code ?? 'model'
                          const color = getModuleColor(String(key))
                          return { style: { background: hexToRgba(color, 0.06) } }
                        }}
                        columns={[
                          {
                            title: '工序',
                            width: FIRST_COL_WIDTH,
                            render: (_: any, r: any) => (
                              <Space>
                                {r.process_code ? <CodePill code={r.process_code} color="#595959" /> : null}
                                <span style={{ whiteSpace: 'nowrap' }}>{r.process_name ?? r.process_id}</span>
                              </Space>
                            ),
                          },
                          {
                            title: '替换',
                            width: 60,
                            render: (_: any, __: any, idx: number) => (
                              <Button size="small" type="text" icon={<SwapOutlined />} title="替换工序" onClick={() => openProcessPickerForRow(idx)} />
                            ),
                          },
                          {
                            title: '班组',
                            width: 120,
                            render: (_: any, r: any, idx: number) => (
                              <Select
                                getPopupContainer={() => document.body}
                                allowClear
                                showSearch
                                placeholder="选择班组"
                                optionFilterProp="label"
                                style={{ width: '100%', fontSize: 12 }}
                                dropdownStyle={{ fontSize: 12 }}
                                value={r.team_name}
                                options={TEAM_OPTIONS}
                                onChange={(v) => {
                                  const next = (processes as any[]).slice()
                                  next[idx] = { ...next[idx], team_name: v ?? undefined }
                                  setProcesses(next as any)
                                }}
                              />
                            ),
                          },
                          {
                            title: '计价',
                            width: 90,
                            render: (_: any, r: any, idx: number) => (
                              <Select
                                getPopupContainer={() => document.body}
                                style={{ width: '100%', fontSize: 12 }}
                                dropdownStyle={{ fontSize: 12 }}
                                value={r.pricing_method}
                                options={[
                                  { label: '数量', value: 'count' },
                                  { label: '面积', value: 'area' },
                                  { label: '周长', value: 'perimeter' },
                                  { label: '宽度', value: 'width' },
                                  { label: '高度', value: 'height' },
                                ]}
                                onChange={(v) => {
                                  const next = (processes as any[]).slice()
                                  const row = next[idx]
                                  if (!row) return
                                  const base = Number(row.base_minutes ?? 0)
                                  const unit = Number(row.unit_minutes ?? 0)
                                  const mqSample = Math.max(0, measureQty(v, sampleSpec))
                                  const stdMq = Math.max(0, measureQty(v, standardSpec))
                                  next[idx] = {
                                    ...row,
                                    pricing_method: v,
                                    sample_minutes: base + unit * mqSample,
                                    standard_minutes: base + unit * stdMq,
                                  }
                                  setProcesses(next as any)
                                }}
                              />
                            ),
                          },
                          {
                            title: '本品用时',
                            width: 110,
                            render: (_: any, r: any) => <span>{Number(r.sample_minutes ?? 0).toFixed(2)}</span>,
                          },
                          {
                            title: '参数',
                            width: 90,
                            render: (_: any, __: any, idx: number) => (
                              <Button
                                size="small"
                                type="text"
                                icon={AlphaIcon}
                                title="调参面板"
                                onClick={() => openTuningPanelForProcess(idx)}
                              />
                            ),
                          },
                          {
                            title: '小计',
                            width: 110,
                            render: (_: any, r: any) => {
                              const minutes = Number(r.sample_minutes ?? 0)
                              const rate = Number(r.rate_per_minute ?? 0)
                              if (Number.isFinite(minutes) && Number.isFinite(rate)) return (minutes * rate).toFixed(2)
                              return '-'
                            },
                          },
                          {
                            title: '备注',
                            width: 60,
                            render: (_: any, r: any, idx: number) => {
                              const has = String(r.notes ?? '').trim().length > 0
                              return (
                                <Button
                                  size="small"
                                  type="text"
                                  icon={<FileTextOutlined style={{ color: has ? '#1677ff' : '#bfbfbf' }} />}
                                  title={has ? '查看/编辑备注' : '添加备注'}
                                  onClick={() => openNotesModal('process', idx)}
                                />
                              )
                            },
                          },
                        ]}
                      />
                    </Card>
                  </Col>
                </Row>
              </Space>
            ),
          },
        ]}
      />

      {/* Model line material picker */}
      <Modal
        title="替换物料"
        open={materialPickerOpen}
        onCancel={() => setMaterialPickerOpen(false)}
        footer={null}
        width={900}
        destroyOnClose
      >
        <Space wrap style={{ marginBottom: 12 }}>
          <Select
            value={pickerMaterialKind}
            style={{ width: 140 }}
            options={[
              { label: 'BOM物料', value: 'bom' },
              { label: '真实物料', value: 'real' },
              { label: '虚拟物料', value: 'virtual' },
            ]}
            onChange={(v) => setPickerMaterialKind(v as any)}
          />
          <Input.Search
            allowClear
            placeholder="搜索编码/名称"
            style={{ width: 320 }}
            value={pickerKeyword}
            onChange={(e) => setPickerKeyword(e.target.value)}
          />
        </Space>

        {(pickerMaterialKind === 'real' || pickerMaterialKind === 'bom') && (
          <Table
            rowKey="id"
            loading={modelLineMaterialPickerQuery.isLoading}
            dataSource={(modelLineMaterialPickerQuery.data as any)?.items ?? []}
            pagination={false}
            size="small"
            columns={[
              { title: '编码', dataIndex: 'material_code', width: 140 },
              { title: '名称', dataIndex: 'material_name' },
              { title: '分类', dataIndex: 'category', width: 120 },
              { title: '单位', dataIndex: 'unit', width: 80 },
              {
                title: '操作',
                width: 100,
                render: (_: any, r: Material) => (
                  <Button
                    type="primary"
                    size="small"
                    onClick={() =>
                      applyPickedMaterialToRow({
                        kind: pickerMaterialKind,
                        id: r.id,
                        code: r.material_code,
                        name: r.material_name,
                        unit: r.unit,
                        category: r.category,
                        defaults: (() => {
                          const meta = (r.metadata_json ?? {}) as Record<string, any>
                          const d = (meta.costing_defaults ?? {}) as Record<string, any>
                          return {
                            fixed_quantity: d.fixed_quantity_alpha != null ? Number(d.fixed_quantity_alpha) : undefined,
                            coverage_ratio: d.coverage_ratio != null ? Number(d.coverage_ratio) : undefined,
                            loss_rate: d.loss_rate != null ? Number(d.loss_rate) : undefined,
                          }
                        })(),
                      })
                    }
                  >
                    选择
                  </Button>
                ),
              },
            ]}
          />
        )}

        {pickerMaterialKind === 'virtual' && (
          <Table
            rowKey="id"
            loading={modelLineVirtualPickerQuery.isLoading}
            dataSource={(modelLineVirtualPickerQuery.data as any)?.items ?? []}
            pagination={false}
            size="small"
            columns={[
              { title: '编码', dataIndex: 'virtual_code', width: 140 },
              { title: '名称', dataIndex: 'name' },
              { title: '类型', dataIndex: 'virtual_kind', width: 100 },
              { title: '单位', dataIndex: 'unit', width: 80 },
              {
                title: '操作',
                width: 100,
                render: (_: any, r: VirtualMaterial) => (
                  <Button
                    type="primary"
                    size="small"
                    onClick={() =>
                      applyPickedMaterialToRow({
                        kind: 'virtual',
                        id: r.id,
                        code: r.virtual_code,
                        name: r.name,
                        unit: (r as any).unit ?? null,
                        category: null,
                      })
                    }
                  >
                    选择
                  </Button>
                ),
              },
            ]}
          />
        )}
      </Modal>

      {/* Model line process picker */}
      <Modal
        title="替换工序"
        open={processPickerOpen}
        onCancel={() => setProcessPickerOpen(false)}
        footer={null}
        width={900}
        destroyOnClose
      >
        <Space wrap style={{ marginBottom: 12 }}>
          <Input.Search
            allowClear
            placeholder="搜索工序编码/名称"
            style={{ width: 360 }}
            value={pickerProcessKeyword}
            onChange={(e) => setPickerProcessKeyword(e.target.value)}
          />
        </Space>
        <Table
          rowKey="id"
          loading={modelLineProcessPickerQuery.isLoading}
          dataSource={(modelLineProcessPickerQuery.data as any)?.items ?? []}
          pagination={false}
          size="small"
          columns={[
            { title: '编码', dataIndex: 'process_code', width: 140 },
            { title: '名称', dataIndex: 'process_name' },
            { title: '计价方式', dataIndex: 'charging_mode', width: 120 },
            { title: '单位', dataIndex: 'unit_of_measure', width: 80 },
            {
              title: '操作',
              width: 100,
              render: (_: any, r: ProcessDetail) => (
                <Button type="primary" size="small" onClick={() => applyPickedProcessToRow(r)}>
                  选择
                </Button>
              ),
            },
          ]}
        />
      </Modal>

      {/* Tuning panel (material/process) */}
      <Modal
        title="调参面板"
        open={tuningOpen}
        onCancel={() => setTuningOpen(false)}
        onOk={applyTuningPanel}
        okText="应用"
        cancelText="取消"
        destroyOnClose
        width={860}
      >
        {tuningKind === 'material' ? (
          <Space direction="vertical" size={12} style={{ width: '100%' }}>
            <Alert
              type="info"
              showIcon
              message="说明"
              description="参数默认从“模块模板/物料库快照”带入；此处修改会覆盖并保存到“版本清单”。再次从模块同步时，如开启“保留调参”，这些值将被保留。"
            />

            <Card size="small" title="调参（α / 覆盖率 / 耗损）">
              <Row gutter={12}>
                <Col span={8}>
                  <InputNumber
                    min={0}
                    precision={2}
                    value={tuningFixedQty}
                    onChange={(v) => setTuningFixedQty(Number(v ?? 0))}
                    addonBefore={addonLabel('固定用量α')}
                    style={{ width: '100%' }}
                  />
                </Col>
                <Col span={8}>
                  <InputNumber
                    min={0}
                    max={1}
                    step={0.01}
                    precision={2}
                    value={tuningCoverageRatio}
                    onChange={(v) => setTuningCoverageRatio(Number(v ?? 1))}
                    addonBefore={addonLabel('覆盖率')}
                    style={{ width: '100%' }}
                  />
                </Col>
                <Col span={8}>
                  <Tooltip title={entryContext === 'sample' ? '用于上浮本品用量：×(1+耗损/100)' : '仅打样口径可编辑'}>
                    <InputNumber
                      min={0}
                      max={100}
                      precision={2}
                      disabled={entryContext !== 'sample'}
                      value={tuningLossRatePercent}
                      onChange={(v) => setTuningLossRatePercent(Number(v ?? 0))}
                      addonBefore={addonLabel('耗损%')}
                      style={{ width: '100%' }}
                    />
                  </Tooltip>
                </Col>
              </Row>
              <Text type="secondary" style={{ display: 'block', marginTop: 8 }}>
                用量计算（当前行）：<Text code>用量_total = α + β × M × 覆盖率</Text>；其中 <Text code>β</Text> 为清单里的“基数(base_quantity)”，
                <Text code>M</Text> 为计量值（按数量/面积/周长/宽/高计算）。
              </Text>
            </Card>

            {entryContext === 'sample' ? (
              <Card size="small" title="高级公式模板（用于推导标准每平米）">
                <Space direction="vertical" style={{ width: '100%' }} size={12}>
                  <Text type="secondary">
                    推导标准版本时（后端）：以打样“总用量(sample_used_quantity)”反推 β，并按标准口径(100CM×100CM×1)重算，写入标准版本的 base_quantity。
                  </Text>

                  <Row gutter={12}>
                    <Col span={8}>
                      <Select
                        value={tuningDeriveTemplateDraft?.template_kind ?? 'linear'}
                        style={{ width: '100%' }}
                        options={[{ value: 'linear', label: '线性（α + β×M×覆盖率）' }]}
                        onChange={(v) =>
                          setTuningDeriveTemplateDraft({ ...(tuningDeriveTemplateDraft ?? {}), template_kind: v })
                        }
                      />
                    </Col>
                    <Col span={8}>
                      <Space>
                        <Switch
                          checked={!!tuningDeriveTemplateDraft?.calibrate_from_sample}
                          onChange={(checked) =>
                            setTuningDeriveTemplateDraft({
                              ...(tuningDeriveTemplateDraft ?? {}),
                              calibrate_from_sample: checked,
                            })
                          }
                        />
                        <Text>用打样数据校准 β（推荐）</Text>
                      </Space>
                    </Col>
                    <Col span={8}>
                      <InputNumber
                        min={0}
                        precision={2}
                        value={
                          tuningDeriveTemplateDraft?.coefficient != null
                            ? Number(tuningDeriveTemplateDraft.coefficient)
                            : undefined
                        }
                        onChange={(v) =>
                          setTuningDeriveTemplateDraft({
                            ...(tuningDeriveTemplateDraft ?? {}),
                            coefficient: v ?? undefined,
                          })
                        }
                        addonBefore={addonLabel('β(可选)')}
                        style={{ width: '100%' }}
                      />
                    </Col>
                  </Row>

                  <Row gutter={12}>
                    <Col span={8}>
                      <InputNumber
                        min={0}
                        precision={2}
                        value={
                          tuningDeriveTemplateDraft?.min_total != null ? Number(tuningDeriveTemplateDraft.min_total) : undefined
                        }
                        onChange={(v) =>
                          setTuningDeriveTemplateDraft({ ...(tuningDeriveTemplateDraft ?? {}), min_total: v ?? undefined })
                        }
                        addonBefore={addonLabel('最小总用量')}
                        style={{ width: '100%' }}
                      />
                    </Col>
                    <Col span={8}>
                      <InputNumber
                        min={0}
                        precision={2}
                        value={
                          tuningDeriveTemplateDraft?.max_total != null ? Number(tuningDeriveTemplateDraft.max_total) : undefined
                        }
                        onChange={(v) =>
                          setTuningDeriveTemplateDraft({ ...(tuningDeriveTemplateDraft ?? {}), max_total: v ?? undefined })
                        }
                        addonBefore={addonLabel('最大总用量')}
                        style={{ width: '100%' }}
                      />
                    </Col>
                    <Col span={8}>
                      <InputNumber
                        min={0}
                        precision={2}
                        value={
                          tuningDeriveTemplateDraft?.rounding?.step != null
                            ? Number(tuningDeriveTemplateDraft.rounding.step)
                            : undefined
                        }
                        onChange={(v) =>
                          setTuningDeriveTemplateDraft({
                            ...(tuningDeriveTemplateDraft ?? {}),
                            rounding: { ...(tuningDeriveTemplateDraft?.rounding ?? {}), step: v ?? undefined },
                          })
                        }
                        addonBefore={addonLabel('取整步长')}
                        style={{ width: '100%' }}
                      />
                    </Col>
                  </Row>

                  <Row gutter={12}>
                    <Col span={8}>
                      <Select
                        value={tuningDeriveTemplateDraft?.rounding?.mode ?? 'round'}
                        style={{ width: '100%' }}
                        options={[
                          { value: 'round', label: '四舍五入' },
                          { value: 'ceil', label: '向上取整' },
                          { value: 'floor', label: '向下取整' },
                        ]}
                        onChange={(v) =>
                          setTuningDeriveTemplateDraft({
                            ...(tuningDeriveTemplateDraft ?? {}),
                            rounding: { ...(tuningDeriveTemplateDraft?.rounding ?? {}), mode: v },
                          })
                        }
                      />
                    </Col>
                  </Row>

                  <Alert
                    type="success"
                    showIcon
                    message="推导公式（专业口径）"
                    description={
                      <Space direction="vertical" size={6}>
                        <Text type="secondary">
                          怎么填（常用）：保持上面“α/覆盖率”为你期望的固定项；勾选“用打样数据校准 β”，并把 β 留空（系统会用打样总用量自动反推 β）。
                          只有在你明确知道系数时，才手动填 β 覆盖自动反推。
                        </Text>
                        <Text type="secondary">
                          最小/最大/取整：用于把推导出的“总用量”做约束（比如最小用量、按 0.01 取整、向上取整等），一般不需要就留空。
                        </Text>
                        <Text>
                          1）打样校准：<Text code>β = max(0, (U_s - α) / (M_s × 覆盖率))</Text>（当启用校准且 M_s&gt;0）
                        </Text>
                        <Text>
                          2）标准推导：<Text code>U_std = α + β × M_std × 覆盖率</Text>，再按最小/最大/取整规则约束
                        </Text>
                        <Text>
                          3）回写基数：<Text code>base_quantity_std = max(0, (U_std - α) / (M_std × 覆盖率))</Text>
                        </Text>
                        <Button type="link" size="small" style={{ padding: 0 }} onClick={() => setDeriveGuideOpen(true)}>
                          打开桌布示例文档（α/覆盖率/β/取整怎么填）
                        </Button>
                      </Space>
                    }
                  />
                </Space>
              </Card>
            ) : null}
          </Space>
        ) : (
          <Space direction="vertical" size={12} style={{ width: '100%' }}>
            <Alert
              type="info"
              showIcon
              message="说明"
              description="参数默认从“模块模板/工序库”带入；此处修改会覆盖并保存到“版本清单”。再次从模块同步时，如开启“保留调参”，这些值将被保留。"
            />

            <Card size="small" title="计价参数（基础 / 计量 / 单价）">
              <Row gutter={12}>
                <Col span={8}>
                  <InputNumber
                    min={0}
                    precision={2}
                    value={tuningBaseMinutes}
                    onChange={(v) => setTuningBaseMinutes(Number(v ?? 0))}
                    addonBefore={addonLabel('基础(分)')}
                    style={{ width: '100%' }}
                  />
                </Col>
                <Col span={8}>
                  <InputNumber
                    min={0}
                    precision={2}
                    value={tuningUnitMinutes}
                    onChange={(v) => setTuningUnitMinutes(Number(v ?? 0))}
                    addonBefore={addonLabel('计量(分)')}
                    style={{ width: '100%' }}
                  />
                </Col>
                <Col span={8}>
                  <InputNumber
                    min={0}
                    precision={2}
                    value={tuningRatePerMinute}
                    onChange={(v) => setTuningRatePerMinute(Number(v ?? 0))}
                    addonBefore={addonLabel('单价(元/分)')}
                    style={{ width: '100%' }}
                  />
                </Col>
              </Row>
              <Text type="secondary" style={{ display: 'block', marginTop: 8 }}>
                用时计算：<Text code>分钟 = base_minutes + unit_minutes × M</Text>；人工费：<Text code>人工费 = 分钟 × 单价(元/分)</Text>（计时口径）。
              </Text>
            </Card>

            {entryContext === 'sample' ? (
              <Card size="small" title="高级公式模板（用于推导标准每平米）">
                <Space direction="vertical" style={{ width: '100%' }} size={12}>
                  <Text type="secondary">
                    推导标准版本时（后端）：以打样“总用时(sample_minutes)”反推 unit 系数，并按标准口径(100CM×100CM×1)重算，写入标准版本的 unit_minutes。
                  </Text>

                  <Row gutter={12}>
                    <Col span={8}>
                      <Select
                        value={tuningDeriveTemplateDraft?.template_kind ?? 'linear'}
                        style={{ width: '100%' }}
                        options={[{ value: 'linear', label: '线性（base + unit×M）' }]}
                        onChange={(v) =>
                          setTuningDeriveTemplateDraft({ ...(tuningDeriveTemplateDraft ?? {}), template_kind: v })
                        }
                      />
                    </Col>
                    <Col span={8}>
                      <Space>
                        <Switch
                          checked={!!tuningDeriveTemplateDraft?.calibrate_from_sample}
                          onChange={(checked) =>
                            setTuningDeriveTemplateDraft({
                              ...(tuningDeriveTemplateDraft ?? {}),
                              calibrate_from_sample: checked,
                            })
                          }
                        />
                        <Text>用打样数据校准 unit（推荐）</Text>
                      </Space>
                    </Col>
                    <Col span={8}>
                      <InputNumber
                        min={0}
                        precision={2}
                        value={
                          tuningDeriveTemplateDraft?.base_minutes != null ? Number(tuningDeriveTemplateDraft.base_minutes) : undefined
                        }
                        onChange={(v) =>
                          setTuningDeriveTemplateDraft({ ...(tuningDeriveTemplateDraft ?? {}), base_minutes: v ?? undefined })
                        }
                        addonBefore={addonLabel('base(可选)')}
                        style={{ width: '100%' }}
                      />
                    </Col>
                  </Row>

                  <Row gutter={12}>
                    <Col span={8}>
                      <InputNumber
                        min={0}
                        precision={2}
                        value={
                          tuningDeriveTemplateDraft?.coefficient != null ? Number(tuningDeriveTemplateDraft.coefficient) : undefined
                        }
                        onChange={(v) =>
                          setTuningDeriveTemplateDraft({ ...(tuningDeriveTemplateDraft ?? {}), coefficient: v ?? undefined })
                        }
                        addonBefore={addonLabel('unit(可选)')}
                        style={{ width: '100%' }}
                      />
                    </Col>
                    <Col span={8}>
                      <InputNumber
                        min={0}
                        precision={2}
                        value={
                          tuningDeriveTemplateDraft?.min_total != null ? Number(tuningDeriveTemplateDraft.min_total) : undefined
                        }
                        onChange={(v) =>
                          setTuningDeriveTemplateDraft({ ...(tuningDeriveTemplateDraft ?? {}), min_total: v ?? undefined })
                        }
                        addonBefore={addonLabel('最小总用时')}
                        style={{ width: '100%' }}
                      />
                    </Col>
                    <Col span={8}>
                      <InputNumber
                        min={0}
                        precision={2}
                        value={
                          tuningDeriveTemplateDraft?.max_total != null ? Number(tuningDeriveTemplateDraft.max_total) : undefined
                        }
                        onChange={(v) =>
                          setTuningDeriveTemplateDraft({ ...(tuningDeriveTemplateDraft ?? {}), max_total: v ?? undefined })
                        }
                        addonBefore={addonLabel('最大总用时')}
                        style={{ width: '100%' }}
                      />
                    </Col>
                  </Row>

                  <Row gutter={12}>
                    <Col span={8}>
                      <InputNumber
                        min={0}
                        precision={2}
                        value={
                          tuningDeriveTemplateDraft?.rounding?.step != null
                            ? Number(tuningDeriveTemplateDraft.rounding.step)
                            : undefined
                        }
                        onChange={(v) =>
                          setTuningDeriveTemplateDraft({
                            ...(tuningDeriveTemplateDraft ?? {}),
                            rounding: { ...(tuningDeriveTemplateDraft?.rounding ?? {}), step: v ?? undefined },
                          })
                        }
                        addonBefore={addonLabel('取整步长')}
                        style={{ width: '100%' }}
                      />
                    </Col>
                    <Col span={8}>
                      <Select
                        value={tuningDeriveTemplateDraft?.rounding?.mode ?? 'round'}
                        style={{ width: '100%' }}
                        options={[
                          { value: 'round', label: '四舍五入' },
                          { value: 'ceil', label: '向上取整' },
                          { value: 'floor', label: '向下取整' },
                        ]}
                        onChange={(v) =>
                          setTuningDeriveTemplateDraft({
                            ...(tuningDeriveTemplateDraft ?? {}),
                            rounding: { ...(tuningDeriveTemplateDraft?.rounding ?? {}), mode: v },
                          })
                        }
                      />
                    </Col>
                  </Row>

                  <Alert
                    type="success"
                    showIcon
                    message="推导公式（专业口径）"
                    description={
                      <Space direction="vertical" size={6}>
                        <Text type="secondary">
                          怎么填（常用）：基础(base) 取你希望“每单固定时间”；勾选“用打样数据校准 unit”，并把 unit 留空（系统会用打样总用时自动反推 unit）。
                          只有在你明确知道计量分钟系数时，才手动填 unit 覆盖自动反推。
                        </Text>
                        <Text type="secondary">
                          最小/最大/取整：用于约束推导出的“总用时”，一般不需要就留空。
                        </Text>
                        <Text>
                          1）打样校准：<Text code>unit = max(0, (T_s - base) / M_s)</Text>（当启用校准且 M_s&gt;0）
                        </Text>
                        <Text>
                          2）标准推导：<Text code>T_std = base + unit × M_std</Text>，再按最小/最大/取整规则约束
                        </Text>
                        <Text>
                          3）回写：保持 base，重算 <Text code>unit_minutes_std = max(0, (T_std - base) / M_std)</Text>
                        </Text>
                      </Space>
                    }
                  />
                </Space>
              </Card>
            ) : null}
          </Space>
        )}
      </Modal>

      <GuideDrawer
        open={deriveGuideOpen}
        title="推导标准每平米：桌布示例（α/覆盖率/β/约束）"
        content={derivePerSqmGuide as string}
        tip="本指南用于培训新同事：从“打样版本”如何配置到“推导标准每平米”的口径与字段填写方式。"
        onClose={() => setDeriveGuideOpen(false)}
      />

      {/* Notes modal */}
      <Modal
        title={notesModalKind === 'material' ? '物料备注' : '工序备注'}
        open={notesModalOpen}
        onCancel={() => setNotesModalOpen(false)}
        onOk={applyNotesModal}
        okText="保存"
        cancelText="取消"
        destroyOnClose
      >
        <Input.TextArea
          rows={4}
          value={notesDraft}
          placeholder="可选：填写备注"
          onChange={(e) => setNotesDraft(e.target.value)}
        />
      </Modal>

      {/* Module picker */}
      <Modal
        open={modulePickerOpen}
        onCancel={() => setModulePickerOpen(false)}
        onOk={() => void addSelectedModules()}
        okText="添加所选模块"
        title="选择工艺模块"
        width={900}
      >
        <Space direction="vertical" style={{ width: '100%' }} size={12}>
          <Input.Search
            allowClear
            placeholder="搜索模块：编码/名称"
            onSearch={(v) => setModulePickerSearch(v.trim())}
          />
          <Table
            rowKey="id"
            loading={modulePickerQuery.isLoading}
            dataSource={(modulePickerQuery.data as any)?.items ?? []}
            pagination={false}
            rowSelection={{
              selectedRowKeys: modulePickerSelected,
              onChange: (keys) => setModulePickerSelected(keys as string[]),
            }}
            columns={[
              { title: '模块编码', dataIndex: 'module_code', width: 160 },
              { title: '模块名称', dataIndex: 'module_name' },
              { title: '状态', dataIndex: 'status', width: 110, render: (v: string) => <Tag>{v}</Tag> },
              { title: '版本', dataIndex: 'version', width: 80 },
            ]}
          />
        </Space>
      </Modal>

      {modelQuery.error ? (
        <Alert
          type="error"
          showIcon
          message="加载失败"
          description={(modelQuery.error as any)?.message ?? '未知错误'}
          style={{ marginTop: 12 }}
        />
      ) : null}

      {versionsQuery.error ? (
        <Alert
          type="error"
          showIcon
          message="版本加载失败"
          description={(versionsQuery.error as any)?.message ?? '未知错误'}
          style={{ marginTop: 12 }}
        />
      ) : null}
    </Drawer>
  )
}
