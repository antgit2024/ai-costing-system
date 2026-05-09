import {
  Alert,
  Button,
  Card,
  Col,
  Drawer,
  Row,
  Form,
  Input,
  InputNumber,
  message,
  Modal,
  Radio,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Tabs,
  Tooltip,
  Typography,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  ArrowDownOutlined,
  ArrowUpOutlined,
  CheckOutlined,
  DeleteOutlined,
  EditOutlined,
  FileTextOutlined,
  InfoCircleOutlined,
  LinkOutlined,
  PlusOutlined,
  ReloadOutlined,
  SettingOutlined,
  PercentageOutlined,
  SwapOutlined,
  StopOutlined,
} from '@ant-design/icons'
import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import './CostingModelsPage.css'
import GuideDrawer from '@/components/common/GuideDrawer'
import productModelGuide from '@doc/costing/manuals/guides/product_model_guide.md?raw'
import {
  activateProductModel,
  createProductModelVariantRule,
  createProductModel,
  deleteProductModelVariantRule,
  deactivateProductModel,
  fetchMaterials,
  fetchProductModel,
  fetchProductModelLines,
  fetchProductModelMaterials,
  fetchProductModelPlaceholders,
  fetchProductModels,
  fetchProductModelVariantRules,
  generateRandomCode,
  fetchProcesses,
  fetchProcessModules,
  fetchVirtualMaterials,
  previewProductModel,
  previewProductModelVersion,
  previewBySku,
  refreshProductModelMaterialPrices,
  syncProductModelFromModules,
  syncProductModelVersionFromModules,
  updateProductModelVariantRule,
  updateProductModelLines,
  updateProductModelVersionLines,
  updateProductModel,
  fetchProductModelVersions,
  createProductModelVersion,
  fetchProductModelVersionLines,
  publishProductModelVersion,
  bindSkuModelVersion,
  deriveStandardFromSampleVersion,
} from '@/services/planner'
import { normalizeUnit } from '@/utils/unit'
import { formatBeijingTime } from '@/utils/beijingTime'
import type {
  Material,
  MaterialQueryParams,
  ModelVariantRuleCreatePayload,
  ModelVariantRuleRead,
  ModelVariantRuleUpdatePayload,
  ProductModel,
  ProductModelCreatePayload,
  ProductModelListResponse,
  ProductModelPlaceholder,
  ProductModelPreviewResponse,
  ProductModelSkuPreviewResponse,
  ProductModelQueryParams,
  ProductModelUpdatePayload,
  ProductModelMaterialLineInput,
  ProductModelProcessLineInput,
  ProductModelSampleSpec,
  ProductModelVersionRead,
  ProcessDetail,
  ProcessModuleQueryParams,
  ProcessModuleSummary,
  VirtualMaterial,
  VirtualMaterialQueryParams,
  DeriveApplyTo,
  DeriveTargetMode,
} from '@/types/planner'
import { MATERIAL_CATEGORIES } from '@/constants/materialCategories'

const { Title, Text } = Typography

type DrawerMode = 'create' | 'edit'
type ReplacementKind = 'real' | 'bom' | 'virtual'
type MaterialKind = 'real' | 'bom' | 'virtual'

type PlaceholderMapping = {
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

const DEFAULT_PAGE_SIZE = 10
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

const MODEL_STATUS_COLORS: Record<string, string> = {
  draft: 'default',
  active: 'green',
  inactive: 'red',
}

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
  // compact: shrink ~1/3 vs previous
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
  // compact: shrink ~1/3 vs previous
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

const getModelStatusLabel = (status: string) => {
  if (status === 'draft') return '草稿'
  if (status === 'active') return '启用'
  if (status === 'inactive') return '停用'
  return status
}

const getCalcModeLabelShort = (mode?: string) => {
  if (mode === 'ratio') return '比例'
  if (mode === 'fixed') return '一口价'
  if (mode === 'independent') return '独立'
  return mode ?? '-'
}

const getCalcModeTagColor = (mode?: string) => {
  if (mode === 'fixed') return 'gold'
  if (mode === 'ratio') return 'blue'
  if (mode === 'independent') return 'purple'
  return 'default'
}

const CALC_MODE_OPTIONS: Array<{ label: string; value: 'ratio' | 'fixed' | 'independent' }> = [
  { label: '比例（按尺寸/口径计算）', value: 'ratio' },
  { label: '一口价（固定价）', value: 'fixed' },
  { label: '独立（按明细累计）', value: 'independent' },
]

const getPlaceholderMappingsFromMeta = (meta: unknown): PlaceholderMapping[] => {
  if (!meta || typeof meta !== 'object') return []
  const mappings = (meta as any).placeholder_mappings
  if (!Array.isArray(mappings)) return []
  return mappings
    .filter((x) => x && typeof x === 'object')
    .map((x) => ({
      placeholder_virtual_id: String((x as any).placeholder_virtual_id ?? '').trim(),
      replacement_kind: String((x as any).replacement_kind ?? '').trim() as ReplacementKind,
      replacement_ref_id: String((x as any).replacement_ref_id ?? '').trim(),
      metadata_json: (x as any).metadata_json ?? undefined,
    }))
    .filter((x) => x.placeholder_virtual_id && x.replacement_kind && x.replacement_ref_id)
}

const upsertPlaceholderMapping = (
  mappings: PlaceholderMapping[],
  next: PlaceholderMapping,
): PlaceholderMapping[] => {
  const normalized = mappings.filter((m) => m.placeholder_virtual_id !== next.placeholder_virtual_id)
  return [...normalized, next]
}

const removePlaceholderMapping = (mappings: PlaceholderMapping[], placeholderId: string): PlaceholderMapping[] =>
  mappings.filter((m) => m.placeholder_virtual_id !== placeholderId)

const CostingModelsPage = () => {
  const queryClient = useQueryClient()
  const [form] = Form.useForm()
  const [listFiltersForm] = Form.useForm()

  const [search, setSearch] = useState<string>('')
  const [status, setStatus] = useState<string | undefined>(undefined)
  const [page, setPage] = useState<number>(1)
  const [pageSize, setPageSize] = useState<number>(DEFAULT_PAGE_SIZE)

  const [drawerOpen, setDrawerOpen] = useState(false)
  const [drawerMode, setDrawerMode] = useState<DrawerMode>('create')
  const [activeTab, setActiveTab] = useState<string>('basic')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [guideOpen, setGuideOpen] = useState(false)

  const [generatingModelCode, setGeneratingModelCode] = useState(false)

  const [modules, setModules] = useState<ModuleLinkDraft[]>([])
  const [placeholderMappings, setPlaceholderMappings] = useState<PlaceholderMapping[]>([])
  const [modelMetadata, setModelMetadata] = useState<Record<string, unknown>>({})

  // Versioning (draft sample/standard + published standard for SKU)
  const [routingTab, setRoutingTab] = useState<'modules' | 'placeholders'>('modules')
  const [modelVersions, setModelVersions] = useState<ProductModelVersionRead[]>([])
  const [selectedVersionId, setSelectedVersionId] = useState<string | null>(null)

  const [skuBindCode, setSkuBindCode] = useState<string>('')
  const [skuPreviewCode, setSkuPreviewCode] = useState<string>('')
  const [skuPreviewResult, setSkuPreviewResult] = useState<ProductModelSkuPreviewResponse | null>(null)

  const [deriveSourceSampleVersionId, setDeriveSourceSampleVersionId] = useState<string | null>(null)
  const [deriveTargetMode, setDeriveTargetMode] = useState<DeriveTargetMode>('create_new')
  const [deriveTargetStandardVersionId, setDeriveTargetStandardVersionId] = useState<string | null>(null)
  const [deriveApplyTo, setDeriveApplyTo] = useState<DeriveApplyTo>('both')
  const [derivingStandard, setDerivingStandard] = useState(false)

  const [deriveTemplateOpen, setDeriveTemplateOpen] = useState(false)
  const [deriveTemplateKind, setDeriveTemplateKind] = useState<'material' | 'process'>('material')
  const [deriveTemplateRowIndex, setDeriveTemplateRowIndex] = useState<number | null>(null)
  const [deriveTemplateDraft, setDeriveTemplateDraft] = useState<any>({ template_kind: 'linear', calibrate_from_sample: true })

  const [modulePickerOpen, setModulePickerOpen] = useState(false)
  const [modulePickerSearch, setModulePickerSearch] = useState('')
  const [modulePickerSelected, setModulePickerSelected] = useState<string[]>([])

  const [targetPickerOpen, setTargetPickerOpen] = useState(false)
  const [targetPickerKind, setTargetPickerKind] = useState<ReplacementKind>('real')
  const [targetPickerPlaceholder, setTargetPickerPlaceholder] = useState<ProductModelPlaceholder | null>(null)
  const [targetPickerSearch, setTargetPickerSearch] = useState('')
  const [targetPickerCategory, setTargetPickerCategory] = useState<string | undefined>(undefined)

  const [previewParams, setPreviewParams] = useState<{ width_mm: number; height_mm: number; quantity: number }>({
    width_mm: 1000,
    height_mm: 1000,
    quantity: 1,
  })
  const [previewSkuHint, setPreviewSkuHint] = useState<string>('')
  const [previewResult, setPreviewResult] = useState<ProductModelPreviewResponse | null>(null)

  const [sampleSpec, setSampleSpec] = useState<ProductModelSampleSpec>({
    width_mm: 1000,
    height_mm: 1000,
    quantity: 1,
    unit_label: '幅',
  })
  const [standardSpec, setStandardSpec] = useState<ProductModelSampleSpec>({
    width_mm: 1000,
    height_mm: 1000,
    quantity: 1,
    unit_label: '幅',
  })
  const [materialLines, setMaterialLines] = useState<ProductModelMaterialLineInput[]>([])
  const [processLines, setProcessLines] = useState<ProductModelProcessLineInput[]>([])

  const [syncingFromModules, setSyncingFromModules] = useState(false)
  const [syncKeepOverrides, setSyncKeepOverrides] = useState(true)
  const [refreshingSummary, setRefreshingSummary] = useState(false)
  const [summary, setSummary] = useState<{
    material_cost: number
    labor_cost: number
    overhead_cost: number
    total_cost: number
  }>({ material_cost: 0, labor_cost: 0, overhead_cost: 0, total_cost: 0 })

  const [materialPickerOpen, setMaterialPickerOpen] = useState(false)
  const [processPickerOpen, setProcessPickerOpen] = useState(false)
  const [pickerRowIndex, setPickerRowIndex] = useState<number | null>(null)
  const [pickerMaterialKind, setPickerMaterialKind] = useState<'real' | 'bom' | 'virtual'>('bom')
  const [pickerKeyword, setPickerKeyword] = useState<string>('')
  const [pickerProcessKeyword, setPickerProcessKeyword] = useState<string>('')
  const [materialAdvancedOpen, setMaterialAdvancedOpen] = useState(false)
  const [materialAdvancedIndex, setMaterialAdvancedIndex] = useState<number | null>(null)
  const [materialAdvancedFixedQty, setMaterialAdvancedFixedQty] = useState<number>(0)
  const [materialAdvancedCoverageRatio, setMaterialAdvancedCoverageRatio] = useState<number>(1)

  const [materialLossOpen, setMaterialLossOpen] = useState(false)
  const [materialLossIndex, setMaterialLossIndex] = useState<number | null>(null)
  const [materialLossRatePercent, setMaterialLossRatePercent] = useState<number>(0)

  const [processParamsOpen, setProcessParamsOpen] = useState(false)
  const [processParamsIndex, setProcessParamsIndex] = useState<number | null>(null)
  const [processParamsBaseMinutes, setProcessParamsBaseMinutes] = useState<number>(0)
  const [processParamsUnitMinutes, setProcessParamsUnitMinutes] = useState<number>(0)
  const [processParamsRatePerMinute, setProcessParamsRatePerMinute] = useState<number>(0)

  const [notesModalOpen, setNotesModalOpen] = useState(false)
  const [notesModalKind, setNotesModalKind] = useState<'material' | 'process'>('material')
  const [notesModalIndex, setNotesModalIndex] = useState<number | null>(null)
  const [notesDraft, setNotesDraft] = useState<string>('')

  const [variantRules, setVariantRules] = useState<ModelVariantRuleRead[]>([])
  const [variantEditorOpen, setVariantEditorOpen] = useState(false)
  const [variantEditing, setVariantEditing] = useState<ModelVariantRuleRead | null>(null)
  const [variantForm] = Form.useForm()
  const [modelMaterials, setModelMaterials] = useState<Array<Record<string, any>>>([])

  const listParams: ProductModelQueryParams = useMemo(
    () => ({
      search: search || undefined,
      status,
      page,
      page_size: pageSize,
    }),
    [page, pageSize, search, status],
  )

  const overviewAllQuery = useQuery<ProductModelListResponse>({
    queryKey: ['productModelsOverview', 'all'],
    queryFn: () => fetchProductModels({ page: 1, page_size: 1 }),
  })
  const overviewDraftQuery = useQuery<ProductModelListResponse>({
    queryKey: ['productModelsOverview', 'draft'],
    queryFn: () => fetchProductModels({ page: 1, page_size: 1, status: 'draft' }),
  })
  const overviewActiveQuery = useQuery<ProductModelListResponse>({
    queryKey: ['productModelsOverview', 'active'],
    queryFn: () => fetchProductModels({ page: 1, page_size: 1, status: 'active' }),
  })
  const overviewInactiveQuery = useQuery<ProductModelListResponse>({
    queryKey: ['productModelsOverview', 'inactive'],
    queryFn: () => fetchProductModels({ page: 1, page_size: 1, status: 'inactive' }),
  })

  const listQuery = useQuery<ProductModelListResponse>({
    queryKey: ['productModels', listParams],
    queryFn: () => fetchProductModels(listParams),
  })

  const modelQuery = useQuery({
    queryKey: ['productModel', editingId],
    queryFn: () => fetchProductModel(editingId as string),
    enabled: !!editingId && drawerOpen,
  })

  const versionsQuery = useQuery<ProductModelVersionRead[]>({
    queryKey: ['productModelVersions', editingId],
    queryFn: () => fetchProductModelVersions(editingId as string),
    enabled: !!editingId && drawerOpen,
  })

  const versionLinesQuery = useQuery({
    queryKey: ['productModelVersionLines', selectedVersionId],
    queryFn: () => fetchProductModelVersionLines(selectedVersionId as string),
    enabled: !!selectedVersionId && drawerOpen && !!editingId && (activeTab === 'workspace' || activeTab === 'preview'),
  })

  const placeholdersQuery = useQuery({
    queryKey: ['productModelPlaceholders', editingId],
    queryFn: () => fetchProductModelPlaceholders(editingId as string),
    enabled: !!editingId && drawerOpen && activeTab === 'routing' && routingTab === 'placeholders',
  })

  const variantRulesQuery = useQuery({
    queryKey: ['productModelVariantRules', editingId],
    queryFn: () => fetchProductModelVariantRules(editingId as string),
    enabled: !!editingId && drawerOpen && activeTab === 'versions',
  })

  const modelMaterialsQuery = useQuery({
    queryKey: ['productModelMaterials', editingId],
    queryFn: () => fetchProductModelMaterials(editingId as string),
    enabled: !!editingId && drawerOpen && activeTab === 'versions',
  })

  const createMutation = useMutation({
    mutationFn: (payload: ProductModelCreatePayload) => createProductModel(payload),
    onSuccess: async (created) => {
      message.success('已创建产品模型')
      setEditingId(created.id)
      setDrawerMode('edit')
      await queryClient.invalidateQueries({ queryKey: ['productModels'] })
      await queryClient.invalidateQueries({ queryKey: ['productModel', created.id] })
    },
    onError: (err: any) => {
      message.error(err?.response?.data?.detail ?? '创建失败')
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: ProductModelUpdatePayload }) =>
      updateProductModel(id, payload),
    onSuccess: async (updated) => {
      message.success('已保存')
      await queryClient.invalidateQueries({ queryKey: ['productModels'] })
      await queryClient.invalidateQueries({ queryKey: ['productModel', updated.id] })
    },
    onError: (err: any) => {
      message.error(err?.response?.data?.detail ?? '保存失败')
    },
  })

  const activateMutation = useMutation({
    mutationFn: (id: string) => activateProductModel(id),
    onSuccess: async () => {
      message.success('已启用')
      await queryClient.invalidateQueries({ queryKey: ['productModels'] })
      if (editingId) await queryClient.invalidateQueries({ queryKey: ['productModel', editingId] })
    },
    onError: (err: any) => {
      // 可能是“占位符映射缺失/不匹配”等启用校验失败：默认不阻塞用户继续编辑
      message.warning(err?.response?.data?.detail ?? '启用失败（不影响继续编辑/保存）')
    },
  })

  const deactivateMutation = useMutation({
    mutationFn: (id: string) => deactivateProductModel(id),
    onSuccess: async () => {
      message.success('已停用')
      await queryClient.invalidateQueries({ queryKey: ['productModels'] })
      if (editingId) await queryClient.invalidateQueries({ queryKey: ['productModel', editingId] })
    },
    onError: (err: any) => {
      message.error(err?.response?.data?.detail ?? '停用失败')
    },
  })

  const openCreate = () => {
    setDrawerMode('create')
    setEditingId(null)
    setActiveTab('basic')
    setModules([])
    setPlaceholderMappings([])
    setModelMetadata({})
    form.resetFields()
    form.setFieldsValue({
      model_code: '',
      model_name: '',
      status: 'draft',
      calc_mode: 'ratio',
      fixed_price: null,
      tags: [],
      unit_of_measure: 'mm',
    })
    // pre-generate short code for usability (silent; if it fails user can click "生成" to retry)
    handleGenerateModelCode({ silentSuccess: true }).catch(() => {})
    setDrawerOpen(true)
  }

  const openEdit = async (row: ProductModel) => {
    setDrawerMode('edit')
    setEditingId(row.id)
    setActiveTab('workspace')
    setDrawerOpen(true)
  }

  const closeDrawer = () => {
    setDrawerOpen(false)
    setEditingId(null)
    setActiveTab('basic')
    setRoutingTab('modules')
    setModules([])
    setPlaceholderMappings([])
    setModelMetadata({})
    setModelVersions([])
    setSelectedVersionId(null)
    setSkuBindCode('')
    setSkuPreviewCode('')
    setSkuPreviewResult(null)
    setPreviewResult(null)
    setMaterialLines([])
    setProcessLines([])
    form.resetFields()
  }

  const syncFromModel = (model: ProductModel) => {
    form.setFieldsValue({
      model_code: model.model_code,
      model_name: model.model_name,
      description: model.description ?? undefined,
      category: model.category ?? undefined,
      status: model.status,
      calc_mode: (model.calc_mode as any) ?? 'ratio',
      fixed_price: model.fixed_price ?? null,
      standard_width_mm: model.standard_width_mm ? Number(model.standard_width_mm) : undefined,
      standard_height_mm: model.standard_height_mm ? Number(model.standard_height_mm) : undefined,
      unit_of_measure: model.unit_of_measure ?? undefined,
      tags: model.tags ?? [],
    })
    const nextModules: ModuleLinkDraft[] = (model.modules ?? []).map((m, idx) => ({
      module_id: m.module_id,
      sequence_order: typeof m.sequence_order === 'number' ? m.sequence_order : idx,
      notes: m.notes ?? undefined,
      metadata_json: m.metadata_json ?? {},
      module: (m.module as any) ?? null,
    }))
    setModules(nextModules.sort((a, b) => a.sequence_order - b.sequence_order))
    setModelMetadata((model.metadata_json ?? {}) as Record<string, unknown>)
    setPlaceholderMappings(getPlaceholderMappingsFromMeta(model.metadata_json))
    // Default preview params from standard size if present
    const w = model.standard_width_mm ? Number(model.standard_width_mm) : 1000
    const h = model.standard_height_mm ? Number(model.standard_height_mm) : 1000
    setPreviewParams({ width_mm: w || 1000, height_mm: h || 1000, quantity: 1 })
    setPreviewResult(null)
    setPreviewSkuHint('')
  }

  const linesQuery = useQuery({
    queryKey: ['productModelLines', editingId],
    queryFn: () => fetchProductModelLines(editingId as string),
    enabled:
      !!editingId &&
      drawerOpen &&
      (activeTab === 'workspace' || activeTab === 'preview') &&
      !selectedVersionId,
  })

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
        // 若本品用量为空/不可用，默认用同步过来的“默认用量”（standard）做首填，避免同步后输入框为空
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
    setMaterialLines(normalizedMaterials)
    setProcessLines(normalizedProcesses)
    // best-effort refresh summary when opening workspace
    refreshSummary().catch(() => {})
  }

  // When model detail arrives, hydrate form/state
  useEffect(() => {
    if (!drawerOpen || drawerMode !== 'edit') return
    if (!modelQuery.data) return
    syncFromModel(modelQuery.data)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [drawerOpen, drawerMode, modelQuery.data?.id])

  // When versions arrive, pick a default selected version (prefer published standard, then draft).
  useEffect(() => {
    if (!versionsQuery.data) return
    setModelVersions(versionsQuery.data ?? [])
    if (selectedVersionId) return
    const items = versionsQuery.data ?? []
    const preferred =
      items.find((v) => v.version_kind === 'standard' && v.version_status === 'published') ??
      items.find((v) => v.version_status === 'draft') ??
      items[0]
    if (preferred?.id) setSelectedVersionId(preferred.id)
  }, [versionsQuery.data, selectedVersionId])

  useEffect(() => {
    if (!linesQuery.data) return
    hydrateLinesFromApi(linesQuery.data)
  }, [linesQuery.data])

  useEffect(() => {
    if (!versionLinesQuery.data) return
    hydrateLinesFromApi(versionLinesQuery.data)
  }, [versionLinesQuery.data])

  // 当用户修改“打样尺寸（实际尺寸）”时：按计价方式自动重算“本品用量/本品用时”（基数不变）
  useEffect(() => {
    setMaterialLines((prev) => {
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

    setProcessLines((prev) => {
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
  }, [sampleSpec.width_mm, sampleSpec.height_mm, sampleSpec.quantity, sampleSpec.unit_label])

  useEffect(() => {
    if (activeTab !== 'versions') return
    if (variantRulesQuery.data) setVariantRules(variantRulesQuery.data)
    if (modelMaterialsQuery.data) setModelMaterials(modelMaterialsQuery.data)
  }, [activeTab, variantRulesQuery.data, modelMaterialsQuery.data])

  const buildPayload = async (): Promise<ProductModelCreatePayload | ProductModelUpdatePayload> => {
    const values = await form.validateFields()
    const mergedMeta = {
      ...(modelMetadata as Record<string, unknown>),
      placeholder_mappings: placeholderMappings,
    }

    const normalizedModules = modules
      .slice()
      .sort((a, b) => a.sequence_order - b.sequence_order)
      .map((m, idx) => ({
        module_id: m.module_id,
        sequence_order: idx + 1,
        notes: m.notes,
        metadata_json: m.metadata_json ?? {},
      }))

    return {
      model_code: values.model_code,
      model_name: values.model_name,
      description: values.description,
      category: values.category,
      calc_mode: values.calc_mode,
      // 非 fixed 模式：显式置空，避免“切换模式后后端仍保留旧 fixed_price”导致启用/校验口径不一致
      fixed_price: values.calc_mode === 'fixed' ? values.fixed_price : null,
      status: values.status,
      tags: values.tags ?? [],
      standard_width_mm: values.standard_width_mm,
      standard_height_mm: values.standard_height_mm,
      unit_of_measure: values.unit_of_measure,
      metadata_json: mergedMeta,
      modules: normalizedModules,
    }
  }

  const handleSave = async () => {
    // 统一“保存”：基础信息 + 当前清单（避免“保存/保存清单”双按钮造成误解）
    const payload = await buildPayload()
    if (drawerMode === 'create') {
      const created = await createMutation.mutateAsync(payload as ProductModelCreatePayload)
      // create 成功后如已进入工作台并已有清单编辑态，则补一次保存 lines（created.id 来自返回的 ProductModel）
      const createdId = (created as any)?.id
      if (createdId) {
        try {
          await updateProductModelLines(createdId, {
            sample: sampleSpec,
            standard: standardSpec,
            materials: materialLines,
            processes: processLines,
          })
        } catch {
          // ignore: 用户可在编辑态再次点击“保存”
        }
      }
      return
    }
    if (!editingId) return
    const { model_code: _ignore, ...patch } = payload as any
    await updateMutation.mutateAsync({ id: editingId, payload: patch })

    // 同步保存“清单调参结果”
    // （如果有缺物料/缺工序，会在 handleSaveLines 的前置校验里给出更明确提示）
    await handleSaveLines()
  }

  const handleGenerateModelCode = async (opts?: { silentSuccess?: boolean }) => {
    if (generatingModelCode) return
    setGeneratingModelCode(true)
    try {
      const res = await generateRandomCode({ kind: 'product_model', length: 3 })
      form.setFieldsValue({ model_code: res.code })
      if (!opts?.silentSuccess) message.success(`已生成编码：${res.code}`)
    } catch (err: any) {
      const detail = err?.response?.data?.detail ?? '生成编码失败'
      message.open({
        type: 'error',
        content: (
          <Space>
            <span>{detail}</span>
            <Button size="small" onClick={() => handleGenerateModelCode()}>
              重试
            </Button>
          </Space>
        ),
        duration: 4,
      })
    } finally {
      setGeneratingModelCode(false)
    }
  }

  const handleSyncFromModules = async () => {
    if (!editingId) {
      message.warning('请先保存模型')
      return
    }
    const doSync = async () => {
      setSyncingFromModules(true)
      try {
        if (selectedVersionId) {
          await syncProductModelVersionFromModules(selectedVersionId, { keep_overrides: syncKeepOverrides })
          await queryClient.invalidateQueries({ queryKey: ['productModelVersionLines', selectedVersionId] })
          message.success(syncKeepOverrides ? '已同步到版本清单（保留版本层调参）' : '已同步到版本清单（覆盖版本层调参）')
        } else {
          await syncProductModelFromModules(editingId, { keep_overrides: syncKeepOverrides })
          await queryClient.invalidateQueries({ queryKey: ['productModel', editingId] })
          await queryClient.invalidateQueries({ queryKey: ['productModelLines', editingId] })
          message.success(syncKeepOverrides ? '已同步（保留模型层调参）' : '已同步（覆盖模型层调参）')
        }
      } catch (err: any) {
        message.warning(err?.response?.data?.detail ?? '同步失败（不影响继续编辑/保存）')
      } finally {
        setSyncingFromModules(false)
      }
    }

    if (!syncKeepOverrides) {
      Modal.confirm({
        title: '确认同步并覆盖模型层调参？',
        content: '关闭“保留模型层调参”后，同步会以模块内容覆盖模型清单的用量/工时等字段。建议先保存或复制关键参数。',
        okText: '继续同步（覆盖）',
        cancelText: '取消',
        onOk: doSync,
      })
      return
    }
    await doSync()
  }

  const handleSaveLines = async () => {
    if (!editingId) {
      message.warning('请先保存模型')
      return
    }
    try {
      // 前置校验：避免后端 422（缺工序/缺物料）导致用户只看到“保存失败”
      const badMatIdx = materialLines.findIndex((m) => !String(m.material_ref_id || '').trim())
      if (badMatIdx >= 0) {
        message.error(`物料组存在未选择物料的行：第 ${badMatIdx + 1} 行，请先删除或重新选择`)
        return
      }
      const badProcIdx = processLines.findIndex((p) => !String(p.process_id || '').trim())
      if (badProcIdx >= 0) {
        message.error(`工序组存在未选择工序的行：第 ${badProcIdx + 1} 行，请先删除或重新选择`)
        return
      }

      // 占位符兜底替换（保存清单前完成替换，保证清单可计价/可做后续变体兜底）
      // - 占位符只存在于“工艺模块模板层”
      // - 落库到模型清单时必须替换为真实物料 / 非占位型虚拟物料
      const mappingByPlaceholderId = new Map(
        placeholderMappings.map((m) => [String(m.placeholder_virtual_id || '').trim(), m] as const),
      )
      const placeholderHits = materialLines
        .map((row, idx) => ({ row, idx }))
        .filter(({ row }) => mappingByPlaceholderId.has(String(row.material_ref_id || '').trim()))
      if (placeholderHits.length) {
        const missing: Array<{ idx: number; label: string }> = []
        const replacedMaterials = materialLines.map((row, index) => {
          const phId = String(row.material_ref_id || '').trim()
          const mapping = mappingByPlaceholderId.get(phId)
          if (!mapping) return row
          if (!mapping.replacement_kind || !mapping.replacement_ref_id) {
            const label =
              String((row.metadata_json as any)?.placeholder_symbol || row.material_code || row.material_name || phId)
            missing.push({ idx: index, label })
            return row
          }
          const meta = (mapping.metadata_json ?? {}) as any
          if (mapping.replacement_kind === 'virtual' && String(meta.virtual_kind || '').trim() === 'placeholder') {
            const label =
              String((row.metadata_json as any)?.placeholder_symbol || row.material_code || row.material_name || phId)
            missing.push({ idx: index, label })
            return row
          }
          return {
            ...row,
            material_kind: mapping.replacement_kind as any,
            material_ref_id: mapping.replacement_ref_id,
            material_code: meta.display_code ?? row.material_code,
            material_name: meta.display_name ?? row.material_name,
            metadata_json: {
              ...(row.metadata_json ?? {}),
              display_unit: meta.display_unit ?? (row.metadata_json as any)?.display_unit,
              display_category: meta.display_category ?? (row.metadata_json as any)?.display_category,
              origin_placeholder: {
                placeholder_virtual_id: phId,
                placeholder_symbol: meta.placeholder_symbol ?? (row.metadata_json as any)?.placeholder_symbol,
                replacement_kind: mapping.replacement_kind,
                replacement_ref_id: mapping.replacement_ref_id,
              },
            },
          }
        })

        if (missing.length) {
          setActiveTab('routing')
          setRoutingTab('placeholders')
          Modal.warning({
            title: '占位符未配置兜底物料，无法保存清单',
            content: (
              <Space direction="vertical" size={6}>
                <Text>以下行仍是占位符，但缺少替换目标（兜底物料）：</Text>
                <div>
                  {missing.slice(0, 20).map((m) => (
                    <div key={`${m.idx}-${m.label}`}>
                      <Text strong>第 {m.idx + 1} 行</Text>：<Text type="secondary">{m.label}</Text>
                    </div>
                  ))}
                  {missing.length > 20 ? <Text type="secondary">…共 {missing.length} 行</Text> : null}
                </div>
                <Text type="secondary">请到“占位符映射”Tab 配置兜底物料后再保存。</Text>
              </Space>
            ),
            okText: '去占位符映射',
            onOk: () => {
              setActiveTab('routing')
              setRoutingTab('placeholders')
            },
          })
          return
        }

        // 用替换后的物料行提交（同时更新本地 state，保证 UI 立刻不再显示占位符）
        setMaterialLines(replacedMaterials)
        if (selectedVersionId) {
          await updateProductModelVersionLines(selectedVersionId, {
            sample: sampleSpec,
            standard: standardSpec,
            materials: replacedMaterials,
            processes: processLines,
          })
          await queryClient.invalidateQueries({ queryKey: ['productModelVersionLines', selectedVersionId] })
          message.success('已保存版本清单（占位符已替换为兜底物料）')
        } else {
          await updateProductModelLines(editingId, {
            sample: sampleSpec,
            standard: standardSpec,
            materials: replacedMaterials,
            processes: processLines,
          })
          await queryClient.invalidateQueries({ queryKey: ['productModel', editingId] })
          await queryClient.invalidateQueries({ queryKey: ['productModelLines', editingId] })
          message.success('已保存模型清单（占位符已替换为兜底物料）')
        }
        return
      }

      if (selectedVersionId) {
        await updateProductModelVersionLines(selectedVersionId, {
          sample: sampleSpec,
          standard: standardSpec,
          materials: materialLines,
          processes: processLines,
        })
        await queryClient.invalidateQueries({ queryKey: ['productModelVersionLines', selectedVersionId] })
        message.success('已保存版本清单')
      } else {
        await updateProductModelLines(editingId, {
          sample: sampleSpec,
          standard: standardSpec,
          materials: materialLines,
          processes: processLines,
        })
        await queryClient.invalidateQueries({ queryKey: ['productModel', editingId] })
        await queryClient.invalidateQueries({ queryKey: ['productModelLines', editingId] })
        message.success('已保存模型清单')
      }
    } catch (err: any) {
      const detail = err?.response?.data?.detail
      if (typeof detail === 'string' && detail.trim()) {
        message.error(detail)
      } else if (Array.isArray(detail)) {
        // FastAPI 422: [{loc, msg, type}, ...]
        const first = detail[0]
        const loc = Array.isArray(first?.loc) ? first.loc.join('.') : ''
        const msg = String(first?.msg || '参数校验失败')
        message.error(loc ? `${loc}：${msg}` : msg)
      } else {
        message.error('保存清单失败')
      }
    }
  }

  const handleRefreshMaterialPrices = async () => {
    if (!editingId) {
      message.warning('请先保存模型')
      return
    }
    try {
      await refreshProductModelMaterialPrices(editingId)
      await queryClient.invalidateQueries({ queryKey: ['productModel', editingId] })
      await queryClient.invalidateQueries({ queryKey: ['productModelLines', editingId] })
      message.success('已同步物料价格')
    } catch (err: any) {
      message.error(err?.response?.data?.detail ?? '同步物料价格失败')
    }
  }

  const refreshSummary = async () => {
    if (!editingId) return
    // 本地汇总：基于“当前编辑态”的用量/工时立即算（无需先保存清单）
    // 后端 preview 仍可用于校验/返回 warnings，但它基于 DB 已保存清单，和编辑态可能不同，因此这里不强依赖。
    setRefreshingSummary(true)
    try {
      let materialCost = 0
      let laborCost = 0

      for (const r of materialLines) {
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

      for (const p of processLines) {
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

        // time
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
    } finally {
      setRefreshingSummary(false)
    }
  }

  // Workspace 顶部“打样尺寸”变更时，自动刷新右侧汇总（不阻塞编辑/保存）
  useEffect(() => {
    if (!drawerOpen) return
    if (!editingId) return
    if (activeTab !== 'workspace') return
    const t = window.setTimeout(() => {
      refreshSummary().catch(() => {
        message.warning('汇总刷新失败（不影响继续编辑/保存）')
      })
    }, 120)
    return () => window.clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    drawerOpen,
    editingId,
    activeTab,
    sampleSpec.width_mm,
    sampleSpec.height_mm,
    sampleSpec.quantity,
    sampleSpec.unit_label,
    materialLines,
    processLines,
  ])

  type PlaceholderValidationIssue = {
    placeholder_id: string
    placeholder_label: string
    message: string
  }

  const getErrorDetailText = (err: any): string => {
    const detail = err?.response?.data?.detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) {
      const first = detail[0]
      const msg = String(first?.msg || '')
      return msg || '参数校验失败'
    }
    return '操作失败'
  }

  const validatePlaceholderMappings = (
    placeholders: ProductModelPlaceholder[],
    mappings: PlaceholderMapping[],
  ): PlaceholderValidationIssue[] => {
    const issues: PlaceholderValidationIssue[] = []
    const byId = new Map(mappings.map((m) => [m.placeholder_virtual_id, m]))
    for (const ph of placeholders) {
      const phId = ph.virtual_material_id
      const phLabel = ph.placeholder_symbol ?? ph.name ?? ph.virtual_code ?? phId
      const mapping = byId.get(phId)
      if (!mapping || !mapping.replacement_kind || !mapping.replacement_ref_id) {
        issues.push({
          placeholder_id: phId,
          placeholder_label: phLabel,
          message: '未配置替换目标',
        })
        continue
      }

      const meta = (mapping.metadata_json ?? {}) as any
      // 不允许映射到另一个占位型虚拟物料
      if (mapping.replacement_kind === 'virtual' && String(meta.virtual_kind || '').trim() === 'placeholder') {
        issues.push({
          placeholder_id: phId,
          placeholder_label: phLabel,
          message: '替换目标不能是“占位型虚拟物料”',
        })
      }

      // 约束分类校验（若占位符存在 constraint_category）
      const constraintCategory = String(ph.constraint_category || '').trim()
      if (constraintCategory) {
        const targetCategory = String(meta.display_category || '').trim()
        if (!targetCategory) {
          issues.push({
            placeholder_id: phId,
            placeholder_label: phLabel,
            message: `缺少目标分类信息（需匹配：${constraintCategory}）`,
          })
        } else if (targetCategory !== constraintCategory) {
          issues.push({
            placeholder_id: phId,
            placeholder_label: phLabel,
            message: `分类不匹配：占位符=${constraintCategory}，目标=${targetCategory}`,
          })
        }
      }

      // 单位校验（若占位符存在 unit）
      const constraintUnit = normalizeUnit(ph.unit || undefined)
      if (constraintUnit) {
        const targetUnit = normalizeUnit(meta.display_unit || undefined)
        if (!targetUnit) {
          issues.push({
            placeholder_id: phId,
            placeholder_label: phLabel,
            message: `缺少目标单位信息（需匹配：${constraintUnit}）`,
          })
        } else if (targetUnit !== constraintUnit) {
          issues.push({
            placeholder_id: phId,
            placeholder_label: phLabel,
            message: `单位不匹配：占位符=${constraintUnit}，目标=${targetUnit}`,
          })
        }
      }
    }
    return issues
  }

  const openEditAtTab = async (row: ProductModel, tab: string) => {
    setDrawerMode('edit')
    setEditingId(row.id)
    setActiveTab(tab)
    setDrawerOpen(true)
  }

  const showPlaceholderIssuesModal = (issues: PlaceholderValidationIssue[]) => {
    Modal.warning({
      title: '占位符映射未完成，无法启用',
      content: (
        <Space direction="vertical" size={6}>
          <Text>请先在“工艺路线 → 占位符映射”完成以下配置：</Text>
          <div>
            {issues.map((it) => (
              <div key={`${it.placeholder_id}-${it.message}`}>
                <Text strong>{it.placeholder_label}</Text>：<Text type="secondary">{it.message}</Text>
              </div>
            ))}
          </div>
        </Space>
      ),
      okText: '去配置占位符映射',
      onOk: () => {
        setActiveTab('routing')
        setRoutingTab('placeholders')
      },
    })
  }

  const persistMappingsForActivate = async (modelId: string) => {
    const mode = form.getFieldValue('calc_mode')
    const fixedPrice = mode === 'fixed' ? form.getFieldValue('fixed_price') : null
    const mergedMeta = {
      ...(modelMetadata as Record<string, unknown>),
      placeholder_mappings: placeholderMappings,
    }
    // 只补齐“启用强校验”相关字段，避免强制用户先点“保存”
    await updateProductModel(modelId, {
      calc_mode: mode,
      fixed_price: fixedPrice,
      metadata_json: mergedMeta,
    } as any)
    await queryClient.invalidateQueries({ queryKey: ['productModel', modelId] })
  }

  const handleActivate = async (row: ProductModel | { id: string }) => {
    const id = (row as any).id as string

    // 若在抽屉编辑态：启用前做前端可解释校验（避免用户只看到后端一句话）
    if (drawerOpen && editingId && editingId === id) {
      try {
        const placeholders = await fetchProductModelPlaceholders(id)
        const issues = validatePlaceholderMappings(placeholders ?? [], placeholderMappings)
        if (issues.length) {
          setActiveTab('routing')
          setRoutingTab('placeholders')
          showPlaceholderIssuesModal(issues)
          return
        }
      } catch {
        // 占位符拉取失败时不阻塞启用；让后端兜底校验并返回 detail
      }
      try {
        await persistMappingsForActivate(id)
      } catch {
        // ignore: 若落库失败，后端启用校验仍会拦截并返回 detail
      }
    }

    try {
      await activateMutation.mutateAsync(id)
    } catch (err: any) {
      // 列表直接启用失败时，给用户一个“可操作”的入口
      const detail = getErrorDetailText(err)
      const isPlaceholderLike =
        /placeholder|占位|映射|replacement|constraint|单位|分类/i.test(detail)
      if (isPlaceholderLike && drawerOpen && editingId === id) {
        Modal.error({
          title: '启用失败：请完善占位符映射',
          content: (
            <Space direction="vertical" size={6}>
              <Text type="secondary">{detail}</Text>
              <Text>请到“工艺路线 → 占位符映射”完成配置后再启用。</Text>
            </Space>
          ),
          okText: '去占位符映射',
          onOk: () => {
            setActiveTab('routing')
            setRoutingTab('placeholders')
          },
        })
        return
      }
      if (isPlaceholderLike && 'model_code' in (row as any)) {
        Modal.error({
          title: '启用失败：请完善占位符映射',
          content: (
            <Space direction="vertical" size={6}>
              <Text type="secondary">{detail}</Text>
              <Text>你可以打开该模型的“工艺路线 → 占位符映射”完成配置后再启用。</Text>
            </Space>
          ),
          okText: '打开模型并配置',
          onOk: () => {
            setRoutingTab('placeholders')
            openEditAtTab(row as ProductModel, 'routing')
          },
        })
      }
    }
  }

  const handleDeactivate = async (id: string) => {
    await deactivateMutation.mutateAsync(id)
  }

  const previewMutation = useMutation({
    mutationFn: async (payload: { id: string; width_mm: number; height_mm: number; quantity: number; sku_hint?: string }) => {
      if (selectedVersionId) {
        return await previewProductModelVersion(selectedVersionId, {
          width_mm: payload.width_mm,
          height_mm: payload.height_mm,
          quantity: payload.quantity,
          sku_hint: payload.sku_hint,
        })
      }
      return await previewProductModel(payload.id, {
        width_mm: payload.width_mm,
        height_mm: payload.height_mm,
        quantity: payload.quantity,
        sku_hint: payload.sku_hint,
      })
    },
    onSuccess: (data) => {
      setPreviewResult(data)
      setSkuPreviewResult(null)
    },
    onError: (err: any) => {
      message.warning(err?.response?.data?.detail ?? '预览计算失败（不影响继续编辑/保存）')
    },
  })

  const skuPreviewMutation = useMutation({
    mutationFn: async (payload: { sku_code: string; width_mm?: number; height_mm?: number; quantity?: number }) =>
      previewBySku(payload),
    onSuccess: (data) => {
      setSkuPreviewResult(data)
      setPreviewResult(data)
      // Sync params from parsed dimensions (best effort)
      const parsed = (data.parsed ?? {}) as any
      const w = parsed.width_mm != null ? Number(parsed.width_mm) : undefined
      const h = parsed.height_mm != null ? Number(parsed.height_mm) : undefined
      if (w && h) setPreviewParams({ width_mm: w, height_mm: h, quantity: Number(data.quantity ?? 1) })
    },
    onError: (err: any) => {
      message.warning(err?.response?.data?.detail ?? 'SKU 预览失败（不影响继续编辑/保存）')
    },
  })

  const handlePreview = async () => {
    if (!editingId) {
      message.warning('请先保存模型')
      return
    }
    const sku = skuPreviewCode.trim()
    if (sku) {
      await skuPreviewMutation.mutateAsync({
        sku_code: sku,
      })
      return
    }
    await previewMutation.mutateAsync({
      id: editingId,
      ...previewParams,
      sku_hint: previewSkuHint.trim() || undefined,
    })
  }

  const createVariantMutation = useMutation({
    mutationFn: async (payload: { modelId: string; body: ModelVariantRuleCreatePayload }) =>
      createProductModelVariantRule(payload.modelId, payload.body),
    onSuccess: async () => {
      message.success('已创建规则')
      if (editingId) await queryClient.invalidateQueries({ queryKey: ['productModelVariantRules', editingId] })
      setVariantEditorOpen(false)
    },
    onError: (err: any) => message.error(err?.response?.data?.detail ?? '创建失败'),
  })

  const updateVariantMutation = useMutation({
    mutationFn: async (payload: { modelId: string; ruleId: string; body: ModelVariantRuleUpdatePayload }) =>
      updateProductModelVariantRule(payload.modelId, payload.ruleId, payload.body),
    onSuccess: async () => {
      message.success('已更新规则')
      if (editingId) await queryClient.invalidateQueries({ queryKey: ['productModelVariantRules', editingId] })
      setVariantEditorOpen(false)
    },
    onError: (err: any) => message.error(err?.response?.data?.detail ?? '更新失败'),
  })

  const deleteVariantMutation = useMutation({
    mutationFn: async (payload: { modelId: string; ruleId: string }) =>
      deleteProductModelVariantRule(payload.modelId, payload.ruleId),
    onSuccess: async () => {
      message.success('已删除规则')
      if (editingId) await queryClient.invalidateQueries({ queryKey: ['productModelVariantRules', editingId] })
    },
    onError: (err: any) => message.error(err?.response?.data?.detail ?? '删除失败'),
  })

  const openVariantEditor = (rule?: ModelVariantRuleRead) => {
    setVariantEditing(rule ?? null)
    setVariantEditorOpen(true)
    variantForm.resetFields()
    if (rule) {
      variantForm.setFieldsValue({
        rule_name: rule.rule_name,
        source_material_ref_id: rule.source_material_ref_id,
        trigger_type: rule.trigger_type,
        trigger_value: rule.trigger_value,
        action_type: rule.action_type,
        target_material_ref_id: rule.target_material_ref_id,
        quantity_delta: rule.quantity_delta ? Number(rule.quantity_delta) : undefined,
        status: rule.status,
      })
    } else {
      variantForm.setFieldsValue({
        status: 'active',
        action_type: 'replace_material',
        trigger_type: 'area_gte',
      })
    }
  }

  const saveVariantRule = async () => {
    if (!editingId) return
    const values = await variantForm.validateFields()
    const body: any = {
      rule_name: values.rule_name,
      source_material_ref_id: values.source_material_ref_id,
      trigger_type: values.trigger_type,
      trigger_value: values.trigger_value,
      action_type: values.action_type,
      target_material_ref_id: values.target_material_ref_id,
      quantity_delta: values.action_type === 'add_material' ? values.quantity_delta : undefined,
      status: values.status,
      metadata_json: {},
    }
    if (variantEditing) {
      await updateVariantMutation.mutateAsync({ modelId: editingId, ruleId: variantEditing.id, body })
    } else {
      await createVariantMutation.mutateAsync({ modelId: editingId, body })
    }
  }

  const columns: ColumnsType<ProductModel> = [
    { title: '模型编码', dataIndex: 'model_code', width: 140, fixed: 'left' },
    { title: '模型名称', dataIndex: 'model_name', width: 220, ellipsis: true },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (v: string) => <Tag color={MODEL_STATUS_COLORS[v] ?? 'default'}>{getModelStatusLabel(v)}</Tag>,
    },
    {
      title: '计算模式',
      dataIndex: 'calc_mode',
      width: 110,
      render: (v: string) => {
        const label = getCalcModeLabelShort(v)
        return <Tag color={getCalcModeTagColor(v)}>{label}</Tag>
      },
    },
    {
      title: '工艺模块数',
      width: 110,
      render: (_, row) => <span>{row.modules?.length ?? 0}</span>,
    },
    {
      title: '标准尺寸',
      width: 170,
      render: (_, row) => {
        const w = row.standard_width_mm ? Number(row.standard_width_mm) : null
        const h = row.standard_height_mm ? Number(row.standard_height_mm) : null
        if (!w && !h) return <Text type="secondary">-</Text>
        return (
          <span>
            {w ?? '-'} × {h ?? '-'} mm
          </span>
        )
      },
    },
    {
      title: '更新时间',
      dataIndex: 'updated_at',
      width: 170,
      render: (v: string) => formatBeijingTime(v, 'YYYY-MM-DD HH:mm'),
    },
    {
      title: '操作',
      width: 220,
      render: (_, row) => (
        <Space>
          <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(row)}>
            编辑
          </Button>
          {row.status === 'active' ? (
            <Button size="small" danger icon={<StopOutlined />} onClick={() => handleDeactivate(row.id)}>
              停用
            </Button>
          ) : (
            <Button size="small" type="primary" icon={<CheckOutlined />} onClick={() => handleActivate(row)}>
              启用
            </Button>
          )}
        </Space>
      ),
    },
  ]

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
    enabled: modulePickerOpen,
  })

  const addSelectedModules = async () => {
    const items = modulePickerQuery.data?.items ?? []
    const selected = new Set(modulePickerSelected)
    const picked = items.filter((m) => selected.has(m.id))
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

    // Key UX fix: once modules are selected, persist to backend and immediately sync model lines,
    // so the right-side material/process groups show up without extra clicks.
    if (!editingId) {
      message.warning('请先保存模型（创建后再添加模块）')
      return
    }
    try {
      setSyncingFromModules(true)
      await updateMutation.mutateAsync({
        id: editingId,
        payload: {
          modules: nextModules
            .slice()
            .sort((a, b) => a.sequence_order - b.sequence_order)
            .map((m, idx) => ({
              module_id: m.module_id,
              sequence_order: idx + 1,
              notes: m.notes,
              metadata_json: m.metadata_json ?? {},
            })),
        },
      })
      await syncProductModelFromModules(editingId, { keep_overrides: true })
      await queryClient.invalidateQueries({ queryKey: ['productModel', editingId] })
      await queryClient.invalidateQueries({ queryKey: ['productModelLines', editingId] })
      message.success('已添加模块并生成模型清单')
    } catch (err: any) {
      message.error(err?.response?.data?.detail ?? '添加模块失败')
    } finally {
      setSyncingFromModules(false)
    }
  }

  const moveModule = (index: number, dir: 'up' | 'down') => {
    const next = modules.slice()
    const targetIndex = dir === 'up' ? index - 1 : index + 1
    if (targetIndex < 0 || targetIndex >= next.length) return
    const tmp = next[index]
    next[index] = next[targetIndex]
    next[targetIndex] = tmp
    setModules(next.map((m, i) => ({ ...m, sequence_order: i + 1 })))
  }

  const removeModule = (index: number) => {
    const next = modules.slice()
    next.splice(index, 1)
    setModules(next.map((m, i) => ({ ...m, sequence_order: i + 1 })))
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

        // optimistic UI: drop linked lines
        const moduleId = target.module_id
        setModules(normalizedModules)
        setMaterialLines((prev) => prev.filter((x) => String(x.source_module_id ?? '') !== String(moduleId)))
        setProcessLines((prev) => prev.filter((x) => String(x.source_module_id ?? '') !== String(moduleId)))

        if (!editingId) return

        // keep the closed loop: PATCH modules -> sync-from-modules
        try {
          setSyncingFromModules(true)
          await updateMutation.mutateAsync({
            id: editingId,
            payload: {
              modules: normalizedModules
                .slice()
                .sort((a, b) => a.sequence_order - b.sequence_order)
                .map((m, idx2) => ({
                  module_id: m.module_id,
                  sequence_order: idx2 + 1,
                  notes: m.notes,
                  metadata_json: m.metadata_json ?? {},
                })),
            },
          })
          await syncProductModelFromModules(editingId, { keep_overrides: true })
          await queryClient.invalidateQueries({ queryKey: ['productModel', editingId] })
          await queryClient.invalidateQueries({ queryKey: ['productModelLines', editingId] })
          message.success('已删除模块并同步清单')
        } catch (err: any) {
          message.error(err?.response?.data?.detail ?? '删除模块失败')
        } finally {
          setSyncingFromModules(false)
        }
      },
    })
  }

  const placeholders = placeholdersQuery.data ?? []

  const openTargetPicker = (placeholder: ProductModelPlaceholder, kind: ReplacementKind) => {
    setTargetPickerPlaceholder(placeholder)
    setTargetPickerKind(kind)
    setTargetPickerSearch('')
    setTargetPickerCategory(placeholder.constraint_category ?? undefined)
    setTargetPickerOpen(true)
  }

  const materialPickerParams: MaterialQueryParams = useMemo(
    () => ({
      search: targetPickerSearch || undefined,
      category: targetPickerCategory || undefined,
      status: 'active',
      is_active: true,
      page: 1,
      page_size: 50,
      is_bom_material: targetPickerKind === 'bom' ? true : undefined,
    }),
    [targetPickerCategory, targetPickerKind, targetPickerSearch],
  )

  const materialPickerQuery = useQuery({
    queryKey: ['materialsForPlaceholderPicker', materialPickerParams],
    queryFn: () => fetchMaterials(materialPickerParams),
    enabled: targetPickerOpen && (targetPickerKind === 'real' || targetPickerKind === 'bom'),
  })

  const virtualPickerParams: VirtualMaterialQueryParams = useMemo(
    () => ({
      search: targetPickerSearch || undefined,
      status: 'active',
      page: 1,
      page_size: 50,
    }),
    [targetPickerSearch],
  )

  const virtualPickerQuery = useQuery({
    queryKey: ['virtualMaterialsForPlaceholderPicker', virtualPickerParams],
    queryFn: () => fetchVirtualMaterials(virtualPickerParams),
    enabled: targetPickerOpen && targetPickerKind === 'virtual',
  })

  // Model line pickers (material / process) reuse the same datasets, but with independent search/kind state.
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
    enabled: materialPickerOpen && (pickerMaterialKind === 'real' || pickerMaterialKind === 'bom'),
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
    enabled: materialPickerOpen && pickerMaterialKind === 'virtual',
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
    enabled: processPickerOpen,
  })

  const openMaterialPickerForRow = (rowIndex: number) => {
    setPickerRowIndex(rowIndex)
    setPickerKeyword('')
    setPickerMaterialKind('bom')
    setMaterialPickerOpen(true)
  }

  const openMaterialAdvancedForRow = (rowIndex: number) => {
    setMaterialAdvancedIndex(rowIndex)
    const row = materialLines[rowIndex]
    setMaterialAdvancedFixedQty(Number(row?.fixed_quantity ?? 0))
    setMaterialAdvancedCoverageRatio(Number(row?.coverage_ratio ?? 1))
    setMaterialAdvancedOpen(true)
  }

  const openMaterialLossForRow = (rowIndex: number) => {
    setMaterialLossIndex(rowIndex)
    const row = materialLines[rowIndex]
    setMaterialLossRatePercent(Number(row?.loss_rate ?? 0))
    setMaterialLossOpen(true)
  }

  const applyMaterialAdvanced = () => {
    if (materialAdvancedIndex == null) return
    const next = materialLines.slice()
    const row = next[materialAdvancedIndex]
    if (!row) return
    const fixedQty = Number(materialAdvancedFixedQty ?? 0)
    const cov = Number(materialAdvancedCoverageRatio ?? 1)
    const method = row.calculation_method
    const stdMq = Math.max(0, measureQty(method, standardSpec))
    const baseQty = Number(row.base_quantity ?? 0)
    const stdUsed = fixedQty + stdMq * baseQty * cov
    next[materialAdvancedIndex] = {
      ...row,
      fixed_quantity: fixedQty,
      coverage_ratio: cov,
      standard_used_quantity: stdUsed,
    }
    setMaterialLines(next)
    setMaterialAdvancedOpen(false)
  }

  const applyMaterialLoss = () => {
    if (materialLossIndex == null) return
    const next = materialLines.slice()
    const row = next[materialLossIndex]
    if (!row) return
    next[materialLossIndex] = { ...row, loss_rate: Number(materialLossRatePercent ?? 0) }
    setMaterialLines(next)
    setMaterialLossOpen(false)
  }

  const openNotesModal = (kind: 'material' | 'process', index: number) => {
    setNotesModalKind(kind)
    setNotesModalIndex(index)
    const row = kind === 'material' ? materialLines[index] : processLines[index]
    setNotesDraft(String((row as any)?.notes ?? ''))
    setNotesModalOpen(true)
  }

  const applyNotesModal = () => {
    if (notesModalIndex == null) return
    const idx = notesModalIndex
    const text = notesDraft
    if (notesModalKind === 'material') {
      const next = materialLines.slice()
      const row = next[idx]
      if (!row) return
      next[idx] = { ...row, notes: text }
      setMaterialLines(next)
    } else {
      const next = processLines.slice()
      const row = next[idx]
      if (!row) return
      next[idx] = { ...row, notes: text }
      setProcessLines(next)
    }
    setNotesModalOpen(false)
  }

  const openProcessPickerForRow = (rowIndex: number) => {
    setPickerRowIndex(rowIndex)
    setPickerProcessKeyword('')
    setProcessPickerOpen(true)
  }

  const openProcessParamsForRow = (rowIndex: number) => {
    setProcessParamsIndex(rowIndex)
    const row = processLines[rowIndex]
    setProcessParamsBaseMinutes(Number(row?.base_minutes ?? 0))
    setProcessParamsUnitMinutes(Number(row?.unit_minutes ?? 0))
    setProcessParamsRatePerMinute(Number(row?.rate_per_minute ?? 0))
    setProcessParamsOpen(true)
  }

  const applyProcessParams = () => {
    if (processParamsIndex == null) return
    const idx = processParamsIndex
    const next = processLines.slice()
    const row = next[idx]
    if (!row) return
    const base = Number(processParamsBaseMinutes ?? 0)
    const unit = Number(processParamsUnitMinutes ?? 0)
    const rate = Number(processParamsRatePerMinute ?? 0)
    const pm = (row.pricing_method as any) ?? 'count'
    const method = pm === 'fixed' ? 'count' : pm
    const mqSample = Math.max(0, measureQty(method, sampleSpec))
    const stdMq = Math.max(0, measureQty(method, standardSpec))
    next[idx] = {
      ...row,
      base_minutes: base,
      unit_minutes: unit,
      rate_per_minute: rate,
      standard_minutes: base + unit * stdMq,
      sample_minutes: base + unit * mqSample,
    }
    setProcessLines(next)
    setProcessParamsOpen(false)
  }

  const applyPickedMaterialToRow = (payload: {
    kind: 'real' | 'bom' | 'virtual'
    id: string
    code?: string | null
    name?: string | null
    unit?: string | null
    category?: string | null
    defaults?: {
      fixed_quantity?: number
      coverage_ratio?: number
      loss_rate?: number
    }
  }) => {
    if (pickerRowIndex === null) return
    const next = materialLines.slice()
    const row = next[pickerRowIndex]
    if (!row) return
    next[pickerRowIndex] = {
      ...row,
      material_kind: payload.kind,
      material_ref_id: payload.id,
      material_code: payload.code ?? undefined,
      material_name: payload.name ?? undefined,
      // Apply material defaults if the model line is still at its neutral defaults (0 / 1),
      // so early-stage projects can benefit from more professional parameters immediately.
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
    setMaterialLines(next)
    setMaterialPickerOpen(false)
  }

  const applyPickedProcessToRow = (proc: ProcessDetail) => {
    if (pickerRowIndex === null) return
    const next = processLines.slice()
    const row = next[pickerRowIndex]
    if (!row) return
    next[pickerRowIndex] = {
      ...row,
      process_id: proc.id,
      process_code: proc.process_code,
      process_name: proc.process_name,
    }
    setProcessLines(next)
    setProcessPickerOpen(false)
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

  const findPreviewMaterialLine = (row: ProductModelMaterialLineInput) => {
    const targetModuleId = row.source_module_id ?? 'model'
    return (previewResult?.material_lines ?? []).find(
      (l: any) => String(l.source_ref_id ?? '') === String(row.material_ref_id ?? '') && String(l.module_id ?? '') === String(targetModuleId),
    )
  }

  const findPreviewLaborLine = (row: ProductModelProcessLineInput) => {
    const targetModuleId = row.source_module_id ?? 'model'
    return (previewResult?.labor_lines ?? []).find(
      (l: any) => String(l.process_id ?? '') === String(row.process_id ?? '') && String(l.module_id ?? '') === String(targetModuleId),
    )
  }

  const selectMaterialAsTarget = (material: Material) => {
    if (!targetPickerPlaceholder) return
    const placeholderId = targetPickerPlaceholder.virtual_material_id
    const next: PlaceholderMapping = {
      placeholder_virtual_id: placeholderId,
      replacement_kind: targetPickerKind,
      replacement_ref_id: material.id,
      metadata_json: {
        display_code: material.material_code,
        display_name: material.material_name,
        display_unit: material.unit,
        display_category: material.category,
      },
    }
    setPlaceholderMappings(upsertPlaceholderMapping(placeholderMappings, next))
    setTargetPickerOpen(false)
  }

  const selectVirtualAsTarget = (vm: VirtualMaterial) => {
    if (!targetPickerPlaceholder) return
    const placeholderId = targetPickerPlaceholder.virtual_material_id
    const next: PlaceholderMapping = {
      placeholder_virtual_id: placeholderId,
      replacement_kind: 'virtual',
      replacement_ref_id: vm.id,
      metadata_json: {
        display_code: vm.virtual_code,
        display_name: vm.name,
        display_unit: vm.unit,
        display_category: (vm as any).category,
        virtual_kind: vm.virtual_kind,
      },
    }
    setPlaceholderMappings(upsertPlaceholderMapping(placeholderMappings, next))
    setTargetPickerOpen(false)
  }

  const findMapping = (placeholderId: string): PlaceholderMapping | undefined =>
    placeholderMappings.find((m) => m.placeholder_virtual_id === placeholderId)

  const placeholderRows = placeholders.map((ph) => {
    const mapping = findMapping(ph.virtual_material_id)
    return { ph, mapping }
  })

  return (
    <Space direction="vertical" size={24} style={{ width: '100%' }}>
      <div>
        <Title level={3} style={{ marginBottom: 4 }}>
          产品模型
        </Title>
        <Text type="secondary">
          配置产品模型的计算模式、工艺模块编排与占位符映射，为后续 SKU/订单算价提供统一的可复用配置底座。
        </Text>
      </div>

      <Row gutter={[24, 24]}>
        <Col xs={24} xl={7} style={{ display: 'flex' }}>
          <Card
            title="当前概览"
            bordered={false}
            style={{ flex: 1, minHeight: '100%' }}
            bodyStyle={{ display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: 10 }}
          >
            <Text strong style={{ fontSize: 16 }}>
              模型总数：{overviewAllQuery.data?.total ?? '-'}
            </Text>
            <Space wrap>
              <Tag>草稿 {overviewDraftQuery.data?.total ?? '-'}</Tag>
              <Tag color="green">启用 {overviewActiveQuery.data?.total ?? '-'}</Tag>
              <Tag color="red">停用 {overviewInactiveQuery.data?.total ?? '-'}</Tag>
            </Space>
            <Text type="secondary">统计全量产品模型（不受当前筛选影响）</Text>
          </Card>
        </Col>
        <Col xs={24} xl={17} style={{ display: 'flex' }}>
          <Card
            title="筛选"
            bordered={false}
            style={{ flex: 1 }}
            extra={
              <Space>
                <Button icon={<ReloadOutlined />} onClick={() => listQuery.refetch()}>
                  刷新
                </Button>
                <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
                  新建模型
                </Button>
              </Space>
            }
          >
            <Form
              form={listFiltersForm}
              layout="inline"
              initialValues={{ search: search || undefined, status }}
              onFinish={(values) => {
                setSearch(String(values.search ?? '').trim())
                setStatus(values.status ?? undefined)
                setPage(1)
              }}
            >
              <Form.Item name="search" label="关键词">
                <Input.Search
                  allowClear
                  placeholder="模型编码 / 名称"
                  style={{ width: 240 }}
                  onSearch={() => listFiltersForm.submit()}
                />
              </Form.Item>
              <Form.Item name="status" label="状态">
                <Select
                  getPopupContainer={() => document.body}
                  allowClear
                  placeholder="全部"
                  style={{ width: 140 }}
                  options={[
                    { label: '草稿', value: 'draft' },
                    { label: '启用', value: 'active' },
                    { label: '停用', value: 'inactive' },
                  ]}
                />
              </Form.Item>
              <Form.Item>
                <Space>
                  <Button type="primary" htmlType="submit">
                    查询
                  </Button>
                  <Button
                    onClick={() => {
                      listFiltersForm.resetFields()
                      setSearch('')
                      setStatus(undefined)
                      setPage(1)
                    }}
                  >
                    重置
                  </Button>
                </Space>
              </Form.Item>
            </Form>
          </Card>
        </Col>
      </Row>

      <Card>
        <Table
          rowKey="id"
          loading={listQuery.isLoading}
          columns={columns}
          dataSource={listQuery.data?.items ?? []}
          pagination={{
            current: page,
            pageSize,
            total: listQuery.data?.total ?? 0,
            showSizeChanger: true,
            showTotal: (total) => `共 ${total} 条`,
            onChange: (p, ps) => {
              setPage(p)
              setPageSize(ps)
            },
          }}
        />
      </Card>

      <Drawer
        className="costing-models-drawer"
        open={drawerOpen}
        onClose={closeDrawer}
        width={1320}
        title={
          <Space>
            <span>{drawerMode === 'create' ? '新建产品模型' : '编辑产品模型'}</span>
            {drawerMode === 'edit' && modelQuery.data?.status ? (
              <Tag color={MODEL_STATUS_COLORS[modelQuery.data.status] ?? 'default'}>
                {getModelStatusLabel(modelQuery.data.status)}
              </Tag>
            ) : null}
          </Space>
        }
        extra={
          <Space>
            {drawerMode === 'edit' && editingId ? (
              modelQuery.data?.status === 'active' ? (
                <Button danger onClick={() => handleDeactivate(editingId)} loading={deactivateMutation.isPending}>
                  停用
                </Button>
              ) : (
                <Button type="primary" onClick={() => handleActivate({ id: editingId })} loading={activateMutation.isPending}>
                  启用
                </Button>
              )
            ) : null}
            <Button icon={<FileTextOutlined />} onClick={() => setGuideOpen(true)}>
              新建指南
            </Button>
            <Button type="primary" onClick={handleSave} loading={createMutation.isPending || updateMutation.isPending}>
              保存
            </Button>
          </Space>
        }
      >
        {drawerMode === 'edit' && modelQuery.isLoading ? <Text>加载中...</Text> : null}
        {drawerMode === 'edit' && modelQuery.error ? (
          <Alert type="error" showIcon message="加载失败" description={(modelQuery.error as any)?.message} />
        ) : null}

        <Form form={form} layout="vertical">
          <Tabs
            activeKey={activeTab}
            onChange={(key) => setActiveTab(key)}
            items={[
              {
                key: 'basic',
                label: '基础信息',
                children: (
                  <Space direction="vertical" style={{ width: '100%' }} size={16}>
                    <Space wrap style={{ width: '100%' }}>
                      <Form.Item
                        label="模型编码"
                        name="model_code"
                        rules={[{ required: true, message: '请输入模型编码' }]}
                        style={{ width: 220 }}
                      >
                        <Input
                          disabled
                          placeholder="自动生成，例如 K7Q"
                          addonAfter={
                            <Button
                              size="small"
                              loading={generatingModelCode}
                              onClick={() => handleGenerateModelCode()}
                            >
                              生成
                            </Button>
                          }
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
            dataSource={modelLineMaterialPickerQuery.data?.items ?? []}
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
            dataSource={modelLineVirtualPickerQuery.data?.items ?? []}
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
                          unit: r.unit ?? null,
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
          dataSource={modelLineProcessPickerQuery.data?.items ?? []}
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

      {/* Material advanced (α fixed quantity) */}
      <Modal
        title="物料高级参数（专业算法）"
        open={materialAdvancedOpen}
        onCancel={() => setMaterialAdvancedOpen(false)}
        onOk={applyMaterialAdvanced}
        okText="应用"
        cancelText="取消"
        destroyOnClose
      >
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <Text type="secondary">
            专业用量模型：用量 = 固定用量α + 单位系数β × 计量值 × 覆盖率。用于“局部亚克力面积/局部贴膜/走线长度”等更精准场景。
          </Text>
          <InputNumber
            min={0}
            precision={6}
            value={materialAdvancedFixedQty}
            onChange={(v) => setMaterialAdvancedFixedQty(Number(v ?? 0))}
            addonBefore="固定用量α"
            style={{ width: '100%' }}
          />
          <InputNumber
            min={0}
            max={1}
            step={0.01}
            precision={4}
            value={materialAdvancedCoverageRatio}
            onChange={(v) => setMaterialAdvancedCoverageRatio(Number(v ?? 1))}
            addonBefore="覆盖率(0~1)"
            style={{ width: '100%' }}
          />
        </Space>
      </Modal>

      {/* Material loss rate */}
      <Modal
        title="耗损（%）"
        open={materialLossOpen}
        onCancel={() => setMaterialLossOpen(false)}
        onOk={applyMaterialLoss}
        okText="应用"
        cancelText="取消"
        destroyOnClose
      >
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <Text type="secondary">用于把“本品用量”按耗损率上浮。示例：耗损 3% 表示实际用量会乘以 1.03。</Text>
          <InputNumber
            min={0}
            max={100}
            precision={2}
            value={materialLossRatePercent}
            onChange={(v) => setMaterialLossRatePercent(Number(v ?? 0))}
            addonBefore="耗损%"
            style={{ width: '100%' }}
          />
        </Space>
      </Modal>

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

      {/* Process pricing params (collapsed for readability) */}
      <Modal
        title="工序计价参数"
        open={processParamsOpen}
        onCancel={() => setProcessParamsOpen(false)}
        onOk={applyProcessParams}
        okText="应用"
        cancelText="取消"
        destroyOnClose
      >
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <Alert
            type="info"
            showIcon
            message="说明"
            description="基础/计量分钟会影响“本品用时”，并参与右侧汇总与预览计算。建议先确认“计价口径”（数量/面积/周长/宽/高）。"
          />
          <InputNumber
            min={0}
            precision={2}
            value={processParamsBaseMinutes}
            onChange={(v) => setProcessParamsBaseMinutes(Number(v ?? 0))}
            addonBefore="基础(分)"
            style={{ width: '100%' }}
          />
          <InputNumber
            min={0}
            precision={2}
            value={processParamsUnitMinutes}
            onChange={(v) => setProcessParamsUnitMinutes(Number(v ?? 0))}
            addonBefore="计量(分)"
            style={{ width: '100%' }}
          />
          <InputNumber
            min={0}
            precision={2}
            value={processParamsRatePerMinute}
            onChange={(v) => setProcessParamsRatePerMinute(Number(v ?? 0))}
            addonBefore="单价(元/分)"
            style={{ width: '100%' }}
          />
        </Space>
      </Modal>
                      </Form.Item>
                      <Form.Item
                        label="模型名称"
                        name="model_name"
                        rules={[{ required: true, message: '请输入模型名称' }]}
                        style={{ width: 320 }}
                      >
                        <Input placeholder="例如 画框模型-通用" />
                      </Form.Item>
                      <Form.Item label="状态" name="status" style={{ width: 160 }}>
                        <Select
                          getPopupContainer={() => document.body}
                          options={[
                            { label: '草稿', value: 'draft' },
                            { label: '启用', value: 'active' },
                            { label: '停用', value: 'inactive' },
                          ]}
                        />
                      </Form.Item>
                    </Space>

                    <Space wrap style={{ width: '100%' }}>
                      <Form.Item label="计算模式" name="calc_mode" style={{ width: 320 }}>
                        <Select
                          getPopupContainer={() => document.body}
                          options={CALC_MODE_OPTIONS}
                          onChange={(v) => {
                            // when switching away from fixed, clear value to avoid confusion & backend strict validation
                            if (v !== 'fixed') form.setFieldsValue({ fixed_price: null })
                          }}
                        />
                      </Form.Item>

                      <Form.Item
                        noStyle
                        shouldUpdate={(prev, cur) => prev.calc_mode !== cur.calc_mode}
                      >
                        {({ getFieldValue }) => {
                          const mode = getFieldValue('calc_mode')
                          if (mode !== 'fixed') return null
                          return (
                            <Form.Item
                              label="一口价（元）"
                              name="fixed_price"
                              style={{ width: 220 }}
                              rules={[{ required: true, message: '一口价模式必须填写 fixed_price' }]}
                            >
                              <InputNumber min={0} precision={4} style={{ width: '100%' }} placeholder="请输入固定价" />
                            </Form.Item>
                          )
                        }}
                      </Form.Item>
                      <Form.Item label="单位口径" name="unit_of_measure" style={{ width: 200 }}>
                        <Input placeholder="例如 mm / ㎡ / m / 个" />
                      </Form.Item>
                    </Space>

                    <Space wrap style={{ width: '100%' }}>
                      <Form.Item label="标准宽度（mm）" name="standard_width_mm" style={{ width: 220 }}>
                        <InputNumber min={0} precision={0} style={{ width: '100%' }} />
                      </Form.Item>
                      <Form.Item label="标准高度（mm）" name="standard_height_mm" style={{ width: 220 }}>
                        <InputNumber min={0} precision={0} style={{ width: '100%' }} />
                      </Form.Item>
                      <Form.Item label="分类" name="category" style={{ width: 220 }}>
                        <Select
                          getPopupContainer={() => document.body}
                          allowClear
                          options={MATERIAL_CATEGORIES.map((c) => ({ label: c, value: c }))}
                        />
                      </Form.Item>
                      <Form.Item label="标签" name="tags" style={{ minWidth: 260 }}>
                        <Select getPopupContainer={() => document.body} mode="tags" placeholder="输入回车添加标签" />
                      </Form.Item>
                    </Space>

                    <Form.Item label="描述" name="description">
                      <Input.TextArea rows={3} placeholder="建议描述该模型的适用 SKU/尺寸范围/关键规则" />
                    </Form.Item>
                    <Alert
                      type="info"
                      showIcon
                      message="说明"
                      description="占位符映射将自动写入 metadata_json.placeholder_mappings；启用时后端会校验占位符是否全部映射且分类/单位匹配。"
                    />
                  </Space>
                ),
              },
              {
                key: 'workspace',
                label: '标准模型',
                children: (
                  <Space direction="vertical" size={12} style={{ width: '100%' }}>
                    <Card
                      size="small"
                      title="版本选择"
                      extra={
                        <Text type="secondary">
                          {selectedVersionId
                            ? `当前版本：${selectedVersionId.slice(0, 8)}…`
                            : '未选择版本（将回落到旧的“模型清单”口径）'}
                        </Text>
                      }
                    >
                      <Space wrap>
                        <Select
                          style={{ width: 420 }}
                          placeholder="选择要编辑/预览的版本"
                          value={selectedVersionId ?? undefined}
                          loading={versionsQuery.isLoading}
                          options={(modelVersions ?? []).map((v) => ({
                            value: v.id,
                            label: `${v.version_kind === 'standard' ? '标准' : '打样'} / ${v.version_status}${
                              v.version_label ? ` / ${v.version_label}` : ''
                            }`,
                          }))}
                          onChange={(v) => {
                            setSelectedVersionId(v)
                            setSkuPreviewResult(null)
                            setPreviewResult(null)
                          }}
                          allowClear
                        />
                        <Button
                          onClick={() => versionsQuery.refetch()}
                          disabled={!editingId}
                          icon={<ReloadOutlined />}
                        >
                          刷新版本
                        </Button>
                      </Space>
                    </Card>
                    <Card
                      size="small"
                      title="打样尺寸"
                      extra={
                        <Space>
                          <Button
                            loading={refreshingSummary}
                            onClick={() => {
                              refreshSummary().catch(() => {
                                message.warning('汇总刷新失败（不影响继续编辑/保存）')
                              })
                            }}
                            disabled={!editingId}
                          >
                            计算模型价格
                          </Button>
                          <Button onClick={handleRefreshMaterialPrices} disabled={!editingId}>
                            同步物料价格
                          </Button>
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
                        />
                        <InputNumber
                          min={0}
                          precision={2}
                          value={Number(sampleSpec.height_mm ?? 0) / 10}
                          onChange={(v) => setSampleSpec({ ...sampleSpec, height_mm: Number(v ?? 0) * 10 })}
                          addonBefore="高(cm)"
                        />
                        <InputNumber
                          min={1}
                          precision={0}
                          value={sampleSpec.quantity}
                          onChange={(v) => setSampleSpec({ ...sampleSpec, quantity: Number(v ?? 1) })}
                          addonBefore="数量"
                        />
                        <Input
                          style={{ width: 140 }}
                          value={sampleSpec.unit_label}
                          onChange={(e) => setSampleSpec({ ...sampleSpec, unit_label: e.target.value || '幅' })}
                          addonBefore="单位"
                        />
                        <InputNumber
                          disabled
                          precision={4}
                          value={(Number(sampleSpec.width_mm) * Number(sampleSpec.height_mm)) / 1_000_000 * Math.max(0, Number(sampleSpec.quantity ?? 1))}
                          addonBefore="面积(㎡)"
                        />
                        <InputNumber
                          disabled
                          precision={4}
                          value={(2 * (Number(sampleSpec.width_mm) + Number(sampleSpec.height_mm))) / 1000 * Math.max(0, Number(sampleSpec.quantity ?? 1))}
                          addonBefore="周长(m)"
                        />
                        {/* 汇总按钮已移动到卡片右上角（“计算模型价格”） */}
                      </Space>
                      <Space wrap style={{ marginTop: 8 }}>
                        <Tag color="blue">物料费：{summary.material_cost.toFixed(2)}</Tag>
                        <Tag color="purple">人工费：{summary.labor_cost.toFixed(2)}</Tag>
                        <Tag color="orange">管理费(23%)：{summary.overhead_cost.toFixed(2)}</Tag>
                        <Tag color="green">合计：{summary.total_cost.toFixed(2)}</Tag>
                      </Space>
                      <Text type="secondary" style={{ display: 'block', marginTop: 8 }}>
                        说明：右侧“实际用量/实际用时”可直接按打样测量输入；保存后系统会自动换算并保存标准尺寸 1000×1000 的单位用量/用时，用于后续 SKU 自动算价。
                      </Text>
                    </Card>

                    <Row gutter={12}>
                      <Col span={6}>
                        <Card
                          size="small"
                          title="工艺模块"
                          extra={
                            <Space>
                              <Button onClick={() => setModulePickerOpen(true)}>添加</Button>
                              <Tooltip
                                getPopupContainer={() => document.body}
                                title={syncKeepOverrides ? '同步时保留模型清单已调参字段' : '同步时以模块内容覆盖模型清单调参'}
                              >
                                <Space size={6}>
                                  <span style={{ fontSize: 12, color: '#8c8c8c' }}>保留调参</span>
                                  <Switch
                                    size="small"
                                    checked={syncKeepOverrides}
                                    onChange={(checked: boolean) => setSyncKeepOverrides(checked)}
                                  />
                                </Space>
                              </Tooltip>
                              <Button
                                loading={syncingFromModules}
                                onClick={handleSyncFromModules}
                                disabled={!editingId}
                                type="primary"
                              >
                                从模块同步
                              </Button>
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
                                render: (_, r) => {
                                  const code = r.module?.module_code ?? '-'
                                  const color = getModuleColor(r.module_id)
                                  return <ModuleCodePill code={code} color={color} size="sm" />
                                },
                              },
                              { title: '名称', render: (_, r) => r.module?.module_name ?? '-' },
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
                                    onClick={() => removeModuleAndLinkedLines(idx)}
                                  />
                                ),
                              },
                            ]}
                          />
                          <Text type="secondary" style={{ display: 'block', marginTop: 8 }}>
                            模块仅作为模板来源；所有调参最终落在右侧模型清单。
                          </Text>
                        </Card>
                      </Col>

                      <Col span={18}>
                        <Card
                          size="small"
                          title="物料组"
                        >
                          <Table
                            rowKey={(r, idx) => r.id ?? `mat-${idx}`}
                            dataSource={materialLines}
                            pagination={false}
                            size="small"
                            style={{ fontSize: TABLE_FONT_SIZE }}
                            onRow={(r) => {
                              const key = r.source_module_id ?? r.source_module_code ?? 'model'
                              const color = getModuleColor(String(key))
                              return { style: { background: hexToRgba(color, 0.06) } }
                            }}
                            columns={[
                              {
                                title: '物料',
                                width: FIRST_COL_WIDTH,
                                render: (_, r) => (
                                  <Space>
                                    {r.material_code ? (
                                      <CodePill
                                        code={r.material_code}
                                        color={getMaterialKindColor(r.material_kind as MaterialKind)}
                                        size="sm"
                                      />
                                    ) : null}
                                    <span style={{ whiteSpace: 'nowrap', fontSize: 12 }}>
                                      {r.material_name ?? r.material_ref_id}
                                    </span>
                                  </Space>
                                ),
                              },
                              {
                                title: '操作',
                                width: 120,
                                render: (_, __, idx) => (
                                  <Space size={2}>
                                    <Button
                                      size="small"
                                      type="text"
                                      icon={<SwapOutlined />}
                                      title="替换"
                                      onClick={() => openMaterialPickerForRow(idx)}
                                    />
                                    <Button
                                      size="small"
                                      type="text"
                                      icon={<SettingOutlined />}
                                      title="高级"
                                      onClick={() => openMaterialAdvancedForRow(idx)}
                                    />
                                    <Button
                                      size="small"
                                      type="text"
                                      icon={<PercentageOutlined />}
                                      title="耗损"
                                      onClick={() => openMaterialLossForRow(idx)}
                                    />
                                    <Button
                                      size="small"
                                      type="text"
                                      icon={<FileTextOutlined />}
                                      title="高级公式"
                                      onClick={() => {
                                        setDeriveTemplateKind('material')
                                        setDeriveTemplateRowIndex(idx)
                                        const cur = (materialLines[idx]?.metadata_json as any)?.derive_template
                                        setDeriveTemplateDraft(
                                          cur ?? { template_kind: 'linear', calibrate_from_sample: true },
                                        )
                                        setDeriveTemplateOpen(true)
                                      }}
                                    />
                                  </Space>
                                ),
                              },
                              {
                                title: '本品用量',
                                width: 160,
                                render: (_, r, idx) => {
                                  return (
                                    <Space size={6} style={{ width: '100%' }} align="center">
                                      <InputNumber
                                        min={0}
                                        precision={2}
                                        value={r.sample_used_quantity}
                                        onChange={(v) => {
                                          const next = materialLines.slice()
                                          const sampleUsed = Number(v ?? 0)
                                          next[idx] = {
                                            ...next[idx],
                                            sample_used_quantity: sampleUsed,
                                          }
                                          setMaterialLines(next)
                                        }}
                                        style={{ width: '100%' }}
                                      />
                                      <Tooltip
                                        getPopupContainer={() => document.body}
                                        title={
                                          <div>
                                            <div>
                                              默认用量：
                                              {Number.isFinite(Number(r.standard_used_quantity))
                                                ? Number(r.standard_used_quantity).toFixed(2)
                                                : '-'}
                                            </div>
                                            <div style={{ color: '#8c8c8c' }}>{getCalcHint(r.calculation_method, sampleSpec)}</div>
                                          </div>
                                        }
                                      >
                                        <InfoCircleOutlined style={{ color: '#8c8c8c', fontSize: 12 }} />
                                      </Tooltip>
                                    </Space>
                                  )
                                },
                              },
                              {
                                title: '计价',
                                width: 90,
                                render: (_, r, idx) => (
                                  <Space style={{ width: '100%' }} align="center" size={6}>
                                    <Select
                                      getPopupContainer={() => document.body}
                                      value={r.calculation_method}
                                      style={{ width: 78, fontSize: 12 }}
                                      dropdownStyle={{ fontSize: 12 }}
                                      options={[
                                        { label: '数量', value: 'count' },
                                        { label: '面积', value: 'area' },
                                        { label: '周长', value: 'perimeter' },
                                        { label: '宽度', value: 'width' },
                                        { label: '高度', value: 'height' },
                                      ]}
                                      onChange={(v) => {
                                        const next = materialLines.slice()
                                        const baseQty = Number(next[idx].base_quantity ?? 0)
                                        const fixedQty = Number(next[idx].fixed_quantity ?? 0)
                                        const cov = Number(next[idx].coverage_ratio ?? 1)
                                        const mqSample = Math.max(0, measureQty(v, sampleSpec))
                                        const mqStandard = Math.max(0, measureQty(v, standardSpec))
                                        const sampleUsed = fixedQty + mqSample * baseQty * cov
                                        const standardUsed = fixedQty + mqStandard * baseQty * cov
                                        next[idx] = {
                                          ...next[idx],
                                          calculation_method: v as any,
                                          base_quantity: baseQty,
                                          sample_used_quantity: sampleUsed,
                                          standard_used_quantity: standardUsed,
                                        }
                                        setMaterialLines(next)
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
                                width: 140,
                                render: (_, r) => {
                                  const pl = findPreviewMaterialLine(r)
                                  const meta = (r.metadata_json as any) ?? {}
                                  const rawPrice = pl?.bom_unit_price ?? meta.bom_unit_price
                                  if (rawPrice == null) return '-'
                                  const p = Number(rawPrice ?? 0)
                                  const u = normalizeUnit(pl?.unit ?? meta.bom_unit ?? meta.display_unit) || '-'
                                  return `${p.toFixed(2)}/${u}`
                                },
                              },
                              {
                                title: '小计',
                                width: 110,
                                render: (_, r) => {
                                  const pl = findPreviewMaterialLine(r)
                                  const t = pl?.total_cost
                                  if (t != null) return Number(t).toFixed(2)

                                  // Fallback: if preview not refreshed, compute using local qty + loss% and BOM unit price (if available).
                                  const meta = (r.metadata_json as any) ?? {}
                                  const rawPrice = pl?.bom_unit_price ?? meta.bom_unit_price
                                  const unitPrice = rawPrice != null ? Number(rawPrice) : NaN
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
                                render: (_, r, idx) => {
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
                            rowKey={(r, idx) => r.id ?? `proc-${idx}`}
                            dataSource={processLines}
                            pagination={false}
                            size="small"
                            style={{ fontSize: TABLE_FONT_SIZE }}
                            onRow={(r) => {
                              const key = r.source_module_id ?? r.source_module_code ?? 'model'
                              const color = getModuleColor(String(key))
                              return { style: { background: hexToRgba(color, 0.06) } }
                            }}
                            columns={[
                              {
                                title: '工序',
                                width: FIRST_COL_WIDTH,
                                render: (_, r) => (
                                  <Space>
                                    {r.process_code ? <CodePill code={r.process_code} color="#595959" /> : null}
                                    <span style={{ whiteSpace: 'nowrap' }}>
                                      {r.process_name ?? r.process_id}
                                    </span>
                                  </Space>
                                ),
                              },
                              {
                                title: '替换',
                                width: 60,
                                render: (_, __, idx) => (
                                  <Button
                                    size="small"
                                    type="text"
                                    icon={<SwapOutlined />}
                                    title="替换工序"
                                    onClick={() => openProcessPickerForRow(idx)}
                                  />
                                ),
                              },
                              {
                                title: '班组',
                                width: 120,
                                render: (_, r, idx) => (
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
                                      const next = processLines.slice()
                                      next[idx] = { ...next[idx], team_name: v ?? undefined }
                                      setProcessLines(next)
                                    }}
                                  />
                                ),
                              },
                              {
                                title: '计价',
                                width: 90,
                                render: (_, r, idx) => (
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
                                      const next = processLines.slice()
                                      const row = next[idx]
                                      if (!row) return
                                      const base = Number(row.base_minutes ?? 0)
                                      const unit = Number(row.unit_minutes ?? 0)
                                      const mqSample = Math.max(0, measureQty(v, sampleSpec))
                                      const stdMq = Math.max(0, measureQty(v, standardSpec))
                                      next[idx] = {
                                        ...row,
                                        pricing_method: v as any,
                                        sample_minutes: base + unit * mqSample,
                                        standard_minutes: base + unit * stdMq,
                                      }
                                      setProcessLines(next)
                                    }}
                                  />
                                ),
                              },
                              {
                                title: '本品用时',
                                width: 110,
                                render: (_, r) => <span>{Number(r.sample_minutes ?? 0).toFixed(2)}</span>,
                              },
                              {
                                title: '参数',
                                width: 90,
                                render: (_, r, idx) => (
                                  <Space size={6}>
                                    <Button
                                      size="small"
                                      type="text"
                                      icon={<SettingOutlined />}
                                      title="编辑计价参数"
                                      onClick={() => openProcessParamsForRow(idx)}
                                    />
                                    <Button
                                      size="small"
                                      type="text"
                                      icon={<FileTextOutlined />}
                                      title="高级公式"
                                      onClick={() => {
                                        setDeriveTemplateKind('process')
                                        setDeriveTemplateRowIndex(idx)
                                        const cur = (processLines[idx]?.metadata_json as any)?.derive_template
                                        setDeriveTemplateDraft(
                                          cur ?? { template_kind: 'linear', calibrate_from_sample: true },
                                        )
                                        setDeriveTemplateOpen(true)
                                      }}
                                    />
                                    <Tooltip
                                      getPopupContainer={() => document.body}
                                      title={
                                        <div>
                                          <div>基础(分)：{Number(r.base_minutes ?? 0).toFixed(2)}</div>
                                          <div>计量(分)：{Number(r.unit_minutes ?? 0).toFixed(2)}</div>
                                          <div>单价(元/分)：{Number(r.rate_per_minute ?? 0).toFixed(2)}</div>
                                        </div>
                                      }
                                    >
                                      <InfoCircleOutlined style={{ color: '#8c8c8c', fontSize: 12 }} />
                                    </Tooltip>
                                  </Space>
                                ),
                              },
                              {
                                title: '小计',
                                width: 110,
                                render: (_, r) => {
                                  const pl = findPreviewLaborLine(r)
                                  const t = pl?.total_cost
                                  if (t != null) return Number(t).toFixed(2)

                                  // Fallback: local compute from current row inputs.
                                  const minutes = Number(r.sample_minutes ?? 0)
                                  const rate = Number(r.rate_per_minute ?? 0)
                                  if (Number.isFinite(minutes) && Number.isFinite(rate)) {
                                    return (minutes * rate).toFixed(2)
                                  }
                                  return '-'
                                },
                              },
                              {
                                title: '备注',
                                width: 60,
                                render: (_, r, idx) => {
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
              {
                key: 'routing',
                label: '工艺路线',
                children: (
                  <Tabs
                    activeKey={routingTab}
                    onChange={(k) => setRoutingTab(k as any)}
                    items={[
                      {
                        key: 'modules',
                        label: '工艺模块编排',
                        children: (
                          <Space direction="vertical" size={12} style={{ width: '100%' }}>
                            <Space wrap>
                              <Button icon={<LinkOutlined />} onClick={() => setModulePickerOpen(true)}>
                                选择工艺模块
                              </Button>
                              <Text type="secondary">已选 {modules.length} 个模块（可调整顺序）。</Text>
                            </Space>
                            <Table
                              rowKey="module_id"
                              dataSource={modules}
                              pagination={false}
                              columns={[
                                { title: '顺序', dataIndex: 'sequence_order', width: 70 },
                                {
                                  title: '模块编码',
                                  width: 140,
                                  render: (_, row) => row.module?.module_code ?? row.module_id,
                                },
                                {
                                  title: '模块名称',
                                  render: (_, row) => row.module?.module_name ?? '-',
                                },
                                {
                                  title: '状态',
                                  width: 100,
                                  render: (_, row) => <Tag>{row.module?.status ?? '-'}</Tag>,
                                },
                                {
                                  title: '备注',
                                  render: (_, row, idx) => (
                                    <Input
                                      value={row.notes}
                                      placeholder="可选"
                                      onChange={(e) => {
                                        const next = modules.slice()
                                        next[idx] = { ...next[idx], notes: e.target.value }
                                        setModules(next)
                                      }}
                                    />
                                  ),
                                },
                                {
                                  title: '操作',
                                  width: 160,
                                  render: (_, __, idx) => (
                                    <Space>
                                      <Button
                                        size="small"
                                        icon={<ArrowUpOutlined />}
                                        disabled={idx === 0}
                                        onClick={() => moveModule(idx, 'up')}
                                      />
                                      <Button
                                        size="small"
                                        icon={<ArrowDownOutlined />}
                                        disabled={idx === modules.length - 1}
                                        onClick={() => moveModule(idx, 'down')}
                                      />
                                      <Button size="small" danger icon={<DeleteOutlined />} onClick={() => removeModule(idx)} />
                                    </Space>
                                  ),
                                },
                              ]}
                            />
                          </Space>
                        ),
                      },
                      {
                        key: 'placeholders',
                        label: '占位符映射',
                        children: (
                          <Space direction="vertical" size={12} style={{ width: '100%' }}>
                            {drawerMode === 'create' || !editingId ? (
                              <Alert
                                type="warning"
                                showIcon
                                message="请先保存模型"
                                description="占位符列表来自“模型引用的工艺模块”。新建模型需先保存并关联模块后，才能拉取占位符并配置映射。"
                              />
                            ) : null}
                            {editingId ? (
                              <Button onClick={() => placeholdersQuery.refetch()} icon={<ReloadOutlined />}>
                                刷新占位符列表
                              </Button>
                            ) : null}
                            <Table
                              rowKey={(r) => r.ph.virtual_material_id}
                              loading={placeholdersQuery.isLoading}
                              dataSource={placeholderRows}
                              pagination={false}
                              columns={[
                                {
                                  title: '占位符',
                                  width: 220,
                                  render: (_, row) => row.ph.placeholder_symbol ?? row.ph.name ?? row.ph.virtual_code,
                                },
                                { title: '约束分类', width: 140, render: (_, row) => row.ph.constraint_category ?? '-' },
                                { title: '单位', width: 90, render: (_, row) => row.ph.unit ?? '-' },
                                {
                                  title: '替换类型',
                                  width: 220,
                                  render: (_, row) => {
                                    const phId = row.ph.virtual_material_id
                                    const current = row.mapping?.replacement_kind ?? 'real'
                                    return (
                                      <Radio.Group
                                        value={current}
                                        onChange={(e) => {
                                          const kind = e.target.value as ReplacementKind
                                          const next = removePlaceholderMapping(placeholderMappings, phId)
                                          setPlaceholderMappings(next)
                                          openTargetPicker(row.ph, kind)
                                        }}
                                      >
                                        <Radio.Button value="real">真实</Radio.Button>
                                        <Radio.Button value="bom">BOM</Radio.Button>
                                        <Radio.Button value="virtual">虚拟</Radio.Button>
                                      </Radio.Group>
                                    )
                                  },
                                },
                                {
                                  title: '替换目标',
                                  render: (_, row) => {
                                    const phId = row.ph.virtual_material_id
                                    const mapping = row.mapping
                                    if (!mapping) {
                                      return (
                                        <Button
                                          size="small"
                                          onClick={() => openTargetPicker(row.ph, 'real')}
                                          icon={<LinkOutlined />}
                                        >
                                          选择替换目标
                                        </Button>
                                      )
                                    }
                                    const meta = (mapping.metadata_json ?? {}) as any
                                    const title =
                                      `${meta.display_code ?? ''} ${meta.display_name ?? ''}`.trim() || mapping.replacement_ref_id
                                    const unit = meta.display_unit ? ` / ${meta.display_unit}` : ''
                                    return (
                                      <Space>
                                        <span>
                                          <Tag color="blue">{mapping.replacement_kind}</Tag>
                                          {title}
                                          {unit}
                                        </span>
                                        <Button size="small" onClick={() => openTargetPicker(row.ph, mapping.replacement_kind)}>
                                          重选
                                        </Button>
                                        <Button
                                          size="small"
                                          danger
                                          onClick={() => setPlaceholderMappings(removePlaceholderMapping(placeholderMappings, phId))}
                                        >
                                          清除
                                        </Button>
                                      </Space>
                                    )
                                  },
                                },
                              ]}
                            />
                            <Alert
                              type="info"
                              showIcon
                              message="启用校验规则"
                              description="启用/发布时：若工艺模块中引用了占位型虚拟物料，则必须配置映射（replacement_kind + replacement_ref_id），并校验分类/单位匹配。"
                            />
                          </Space>
                        ),
                      },
                    ]}
                  />
                ),
              },
              {
                key: 'versions',
                label: '版本管理',
                children: (
                  <Space direction="vertical" size={12} style={{ width: '100%' }}>
                    <Card size="small" title="版本列表 / 发布">
                      <Space direction="vertical" style={{ width: '100%' }} size={8}>
                        <Space wrap>
                          <Button
                            type="primary"
                            disabled={!editingId}
                            onClick={async () => {
                              if (!editingId) return
                              try {
                                const created = await createProductModelVersion(editingId, {
                                  version_kind: 'sample',
                                  metadata_json: {},
                                })
                                message.success('已创建打样版本')
                                await versionsQuery.refetch()
                                setSelectedVersionId(created.id)
                                setActiveTab('workspace')
                              } catch (err: any) {
                                message.error(err?.response?.data?.detail ?? '创建打样版本失败')
                              }
                            }}
                          >
                            新建打样版本
                          </Button>
                          <Button
                            disabled={!editingId}
                            onClick={async () => {
                              if (!editingId) return
                              try {
                                const created = await createProductModelVersion(editingId, {
                                  version_kind: 'standard',
                                  metadata_json: {},
                                })
                                message.success('已创建标准版本草稿')
                                await versionsQuery.refetch()
                                setSelectedVersionId(created.id)
                                setActiveTab('workspace')
                              } catch (err: any) {
                                message.error(err?.response?.data?.detail ?? '创建标准版本失败')
                              }
                            }}
                          >
                            新建标准版本（草稿）
                          </Button>
                          <Button
                            type="primary"
                            disabled={!selectedVersionId}
                            onClick={async () => {
                              if (!selectedVersionId) return
                              try {
                                await publishProductModelVersion(selectedVersionId, {})
                                message.success('已发布标准版本')
                                await versionsQuery.refetch()
                              } catch (err: any) {
                                message.error(err?.response?.data?.detail ?? '发布失败')
                              }
                            }}
                          >
                            发布当前选择版本
                          </Button>
                          <Button
                            onClick={() => versionsQuery.refetch()}
                            disabled={!editingId}
                            icon={<ReloadOutlined />}
                          >
                            刷新
                          </Button>
                        </Space>

                        <Table
                          rowKey="id"
                          size="small"
                          pagination={false}
                          loading={versionsQuery.isLoading}
                          dataSource={modelVersions}
                          columns={[
                            {
                              title: '类型',
                              width: 90,
                              render: (_: any, r: ProductModelVersionRead) =>
                                r.version_kind === 'standard' ? <Tag color="blue">标准</Tag> : <Tag>打样</Tag>,
                            },
                            { title: '状态', width: 110, dataIndex: 'version_status' },
                            {
                              title: '标识',
                              render: (_: any, r: ProductModelVersionRead) =>
                                r.version_label ? r.version_label : <Text type="secondary">{r.id}</Text>,
                            },
                            {
                              title: '操作',
                              width: 140,
                              render: (_: any, r: ProductModelVersionRead) => (
                                <Button
                                  size="small"
                                  type={selectedVersionId === r.id ? 'primary' : 'default'}
                                  onClick={() => {
                                    setSelectedVersionId(r.id)
                                    setActiveTab('workspace')
                                  }}
                                >
                                  {selectedVersionId === r.id ? '已选中' : '选择'}
                                </Button>
                              ),
                            },
                          ]}
                        />
                      </Space>
                    </Card>

                    <Card size="small" title="一键推导标准版本（从打样版本）">
                      <Space direction="vertical" style={{ width: '100%' }} size={8}>
                        <Space wrap>
                          <Select
                            style={{ width: 420 }}
                            placeholder="选择源打样版本（sample）"
                            value={deriveSourceSampleVersionId ?? undefined}
                            options={(modelVersions ?? [])
                              .filter((v) => v.version_kind === 'sample')
                              .map((v) => ({
                                value: v.id,
                                label: `${v.version_label ?? v.id} / ${v.version_status}`,
                              }))}
                            onChange={(v) => setDeriveSourceSampleVersionId(v)}
                            allowClear
                          />
                          <Select
                            style={{ width: 200 }}
                            value={deriveTargetMode}
                            options={[
                              { value: 'create_new', label: '新建标准版本' },
                              { value: 'overwrite_draft', label: '覆盖草稿标准版本' },
                            ]}
                            onChange={(v) => setDeriveTargetMode(v as DeriveTargetMode)}
                          />
                          {deriveTargetMode === 'overwrite_draft' ? (
                            <Select
                              style={{ width: 420 }}
                              placeholder="选择要覆盖的 standard draft"
                              value={deriveTargetStandardVersionId ?? undefined}
                              options={(modelVersions ?? [])
                                .filter((v) => v.version_kind === 'standard' && v.version_status === 'draft')
                                .map((v) => ({
                                  value: v.id,
                                  label: `${v.version_label ?? v.id}`,
                                }))}
                              onChange={(v) => setDeriveTargetStandardVersionId(v)}
                              allowClear
                            />
                          ) : null}
                        </Space>
                        <Space wrap>
                          <Select
                            style={{ width: 200 }}
                            value={deriveApplyTo}
                            options={[
                              { value: 'both', label: '物料+工序' },
                              { value: 'materials', label: '仅物料' },
                              { value: 'processes', label: '仅工序' },
                            ]}
                            onChange={(v) => setDeriveApplyTo(v as DeriveApplyTo)}
                          />
                          <Button
                            type="primary"
                            loading={derivingStandard}
                            disabled={
                              !deriveSourceSampleVersionId ||
                              (deriveTargetMode === 'overwrite_draft' && !deriveTargetStandardVersionId)
                            }
                            onClick={async () => {
                              if (!deriveSourceSampleVersionId) return
                              setDerivingStandard(true)
                              try {
                                const res = await deriveStandardFromSampleVersion(deriveSourceSampleVersionId, {
                                  target_mode: deriveTargetMode,
                                  target_standard_version_id:
                                    deriveTargetMode === 'overwrite_draft'
                                      ? deriveTargetStandardVersionId ?? undefined
                                      : undefined,
                                  apply_to: deriveApplyTo,
                                })
                                message.success('已推导生成标准版本')
                                await versionsQuery.refetch()
                                setSelectedVersionId(res.standard_version_id)
                                setActiveTab('workspace')
                              } catch (err: any) {
                                message.error(err?.response?.data?.detail ?? '推导失败')
                              } finally {
                                setDerivingStandard(false)
                              }
                            }}
                          >
                            开始推导
                          </Button>
                          <Text type="secondary">
                            公式模板存放于打样版本行 `metadata_json.derive_template`；推导会强制标准规格=1000×1000×1。
                          </Text>
                        </Space>
                      </Space>
                    </Card>

                    <Card size="small" title="SKU 绑定（绑定到已发布标准版本）">
                      <Space wrap>
                        <Input
                          style={{ width: 320 }}
                          value={skuBindCode}
                          onChange={(e) => setSkuBindCode(e.target.value)}
                          placeholder="输入 SKU，例如 K7Q-1000x1000-THICK"
                          allowClear
                        />
                        <Button
                          type="primary"
                          disabled={!skuBindCode.trim() || !selectedVersionId}
                          onClick={async () => {
                            const sku = skuBindCode.trim()
                            if (!sku || !selectedVersionId) return
                            try {
                              await bindSkuModelVersion({
                                sku_code: sku,
                                model_version_id: selectedVersionId,
                                metadata_json: {},
                              })
                              message.success('SKU 已绑定到版本（历史保留）')
                              setSkuBindCode('')
                            } catch (err: any) {
                              message.error(err?.response?.data?.detail ?? 'SKU 绑定失败')
                            }
                          }}
                        >
                          绑定到当前版本
                        </Button>
                        <Text type="secondary">
                          规则：先识别模型编码前缀 →（可选）版本号 → 解析 SKU 尺寸 → 变体映射（sku_contains 等）。
                        </Text>
                      </Space>
                    </Card>

                    {drawerMode === 'create' || !editingId ? (
                      <Alert
                        type="warning"
                        showIcon
                        message="请先保存模型"
                        description="变体规则必须绑定到“模型展开后的基础物料（兜底）”。新建模型需先保存并配置工艺模块/占位符映射。"
                      />
                    ) : null}
                    <Space wrap>
                      <Button type="primary" onClick={() => openVariantEditor()} disabled={!editingId}>
                        新增规则
                      </Button>
                      <Button icon={<ReloadOutlined />} onClick={() => variantRulesQuery.refetch()} disabled={!editingId}>
                        刷新
                      </Button>
                      <Text type="secondary">
                        规则以 source_material_ref_id 为兜底基础：未命中任何规则时回落源物料；启用校验会验证兜底存在。
                      </Text>
                    </Space>
                    <Table
                      rowKey="id"
                      loading={variantRulesQuery.isLoading}
                      dataSource={variantRules}
                      pagination={false}
                      size="small"
                      columns={[
                        { title: '规则名', dataIndex: 'rule_name', width: 200 },
                        { title: '触发', width: 160, render: (_, r) => `${r.trigger_type} ${r.trigger_value ?? ''}`.trim() },
                        { title: '动作', width: 160, render: (_, r) => `${r.action_type}${r.quantity_delta ? ` (+${r.quantity_delta})` : ''}` },
                        { title: '状态', dataIndex: 'status', width: 90, render: (v: string) => <Tag>{v}</Tag> },
                        {
                          title: '操作',
                          width: 180,
                          render: (_, r) => (
                            <Space>
                              <Button size="small" onClick={() => openVariantEditor(r)}>编辑</Button>
                              <Button
                                size="small"
                                danger
                                onClick={() => editingId && deleteVariantMutation.mutate({ modelId: editingId, ruleId: r.id })}
                                loading={deleteVariantMutation.isPending}
                              >
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
                      message="工序是否能变体？"
                      description="本阶段规则仅作用于物料行（替换/加料），工序保持不变；若未来允许工序变体，也必须绑定 source_process_id 作为兜底并做启用校验，避免命中失败导致工艺路线缺失。"
                    />

                    <Modal
                      open={variantEditorOpen}
                      onCancel={() => setVariantEditorOpen(false)}
                      onOk={saveVariantRule}
                      okText="保存规则"
                      title={variantEditing ? '编辑变体规则' : '新增变体规则'}
                      confirmLoading={createVariantMutation.isPending || updateVariantMutation.isPending}
                      width={860}
                    >
                      <Form form={variantForm} layout="vertical">
                        <Space wrap style={{ width: '100%' }}>
                          <Form.Item
                            label="规则名"
                            name="rule_name"
                            rules={[{ required: true, message: '请输入规则名' }]}
                            style={{ width: 260 }}
                          >
                            <Input placeholder="例如 大面积用厚板" />
                          </Form.Item>
                          <Form.Item label="状态" name="status" style={{ width: 160 }}>
                            <Select options={[{ label: '启用', value: 'active' }, { label: '停用', value: 'inactive' }]} />
                          </Form.Item>
                        </Space>

                        <Space wrap style={{ width: '100%' }}>
                          <Form.Item
                            label="兜底源物料（source）"
                            name="source_material_ref_id"
                            rules={[{ required: true, message: '请选择源物料（兜底）' }]}
                            style={{ width: 380 }}
                          >
                            <Select
                              showSearch
                              optionFilterProp="label"
                              placeholder="必须是模型展开物料（否则启用校验不通过）"
                              options={modelMaterials.map((m) => ({
                                label: `${m.material_code ?? ''} ${m.material_name ?? ''}`.trim(),
                                value: m.material_id,
                              }))}
                            />
                          </Form.Item>
                          <Form.Item
                            label="目标物料（target）"
                            name="target_material_ref_id"
                            rules={[{ required: true, message: '请选择目标物料' }]}
                            style={{ width: 380 }}
                          >
                            <Select
                              showSearch
                              optionFilterProp="label"
                              options={modelMaterials.map((m) => ({
                                label: `${m.material_code ?? ''} ${m.material_name ?? ''}`.trim(),
                                value: m.material_id,
                              }))}
                            />
                          </Form.Item>
                        </Space>

                        <Space wrap style={{ width: '100%' }}>
                          <Form.Item label="触发类型" name="trigger_type" style={{ width: 220 }}>
                            <Select
                              options={[
                                { label: 'SKU包含', value: 'sku_contains' },
                                { label: '面积≥', value: 'area_gte' },
                                { label: '周长≥', value: 'perimeter_gte' },
                              ]}
                            />
                          </Form.Item>
                          <Form.Item
                            label="触发值"
                            name="trigger_value"
                            rules={[{ required: true, message: '请输入触发值' }]}
                            style={{ width: 220 }}
                          >
                            <Input placeholder="sku_contains=关键词；面积/周长=阈值" />
                          </Form.Item>
                          <Form.Item label="动作" name="action_type" style={{ width: 220 }}>
                            <Select
                              options={[
                                { label: '替换物料', value: 'replace_material' },
                                { label: '加料', value: 'add_material' },
                              ]}
                            />
                          </Form.Item>
                          <Form.Item
                            label="加料用量（quantity_delta）"
                            name="quantity_delta"
                            dependencies={['action_type']}
                            rules={[
                              ({ getFieldValue }) => ({
                                validator: async (_, value) => {
                                  if (getFieldValue('action_type') !== 'add_material') return
                                  if (!value || Number(value) <= 0) throw new Error('加料必须填写 quantity_delta > 0')
                                },
                              }),
                            ]}
                            style={{ width: 220 }}
                          >
                            <InputNumber min={0} precision={6} style={{ width: '100%' }} />
                          </Form.Item>
                        </Space>
                        <Alert
                          type="info"
                          showIcon
                          message="兜底机制"
                          description="规则必须绑定 source（兜底）。命中时替换/加料；未命中时继续使用 source 物料不变。"
                        />
                      </Form>
                    </Modal>
                  </Space>
                ),
              },
              {
                key: 'preview',
                label: '预览计算',
                children: (
                  <Space direction="vertical" style={{ width: '100%' }} size={12}>
                    <Space wrap>
                      <InputNumber
                        min={0}
                        precision={0}
                        value={previewParams.width_mm}
                        onChange={(v) => setPreviewParams({ ...previewParams, width_mm: Number(v ?? 0) })}
                        addonBefore="宽(mm)"
                      />
                      <InputNumber
                        min={0}
                        precision={0}
                        value={previewParams.height_mm}
                        onChange={(v) => setPreviewParams({ ...previewParams, height_mm: Number(v ?? 0) })}
                        addonBefore="高(mm)"
                      />
                      <InputNumber
                        min={1}
                        precision={0}
                        value={previewParams.quantity}
                        onChange={(v) => setPreviewParams({ ...previewParams, quantity: Number(v ?? 1) })}
                        addonBefore="数量"
                      />
                      <Input
                        style={{ width: 260 }}
                        value={skuPreviewCode}
                        onChange={(e) => setSkuPreviewCode(e.target.value)}
                        placeholder="SKU（优先，自动解析尺寸/版本/变体；可选）"
                        allowClear
                      />
                      <Input
                        style={{ width: 260 }}
                        value={previewSkuHint}
                        onChange={(e) => setPreviewSkuHint(e.target.value)}
                        placeholder="SKU/特征串（用于 sku_contains，可选）"
                      />
                      <Button
                        type="primary"
                        onClick={handlePreview}
                        loading={previewMutation.isPending || skuPreviewMutation.isPending}
                      >
                        预览计算
                      </Button>
                      {skuPreviewResult ? (
                        <Tag color="geekblue">
                          SKU→版本：{skuPreviewResult.model_code}-{skuPreviewResult.version_label ?? skuPreviewResult.version_id}
                        </Tag>
                      ) : null}
                      {previewResult?.totals ? (
                        <Space>
                          <Tag color="blue">物料 {String(previewResult.totals.material_cost ?? '-')}</Tag>
                          <Tag color="purple">人工 {String(previewResult.totals.labor_cost ?? '-')}</Tag>
                          <Tag color="green">合计 {String(previewResult.totals.total_cost ?? '-')}</Tag>
                        </Space>
                      ) : null}
                    </Space>

                    {previewResult?.errors?.length ? (
                      <Alert
                        type="error"
                        showIcon
                        message="预览错误"
                        description={previewResult.errors.join('；')}
                      />
                    ) : null}

                    <Tabs
                      items={[
                        {
                          key: 'materials',
                          label: `物料明细 (${previewResult?.material_lines?.length ?? 0})`,
                          children: (
                            <Table
                              rowKey={(_, idx) => `mat-${idx}`}
                              dataSource={previewResult?.material_lines ?? []}
                              pagination={false}
                              size="small"
                              columns={[
                                { title: '模块', width: 180, render: (_, r) => `${r.module_code ?? ''} ${r.module_name ?? ''}`.trim() || r.module_id },
                                { title: '来源', width: 110, dataIndex: 'source_kind' },
                                { title: '物料', render: (_, r) => `${r.material_code ?? ''} ${r.material_name ?? ''}`.trim() || '-' },
                                { title: '计量', width: 90, dataIndex: 'calculation_method' },
                                { title: '用量', width: 110, dataIndex: 'used_quantity' },
                                { title: '单价', width: 110, dataIndex: 'bom_unit_price' },
                                { title: '成本', width: 110, dataIndex: 'total_cost' },
                                {
                                  title: '提示',
                                  render: (_, r) => (r.warnings?.length ? <Text type="warning">{r.warnings.join('；')}</Text> : <Text type="secondary">-</Text>),
                                },
                              ]}
                            />
                          ),
                        },
                        {
                          key: 'labor',
                          label: `工序明细 (${previewResult?.labor_lines?.length ?? 0})`,
                          children: (
                            <Table
                              rowKey={(_, idx) => `lab-${idx}`}
                              dataSource={previewResult?.labor_lines ?? []}
                              pagination={false}
                              size="small"
                              columns={[
                                { title: '模块', width: 180, render: (_, r) => `${r.module_code ?? ''} ${r.module_name ?? ''}`.trim() || r.module_id },
                                { title: '工序', render: (_, r) => `${r.process_code ?? ''} ${r.process_name ?? ''}`.trim() || '-' },
                                { title: '班组', width: 120, dataIndex: 'team_name' },
                                { title: '口径', width: 90, dataIndex: 'pricing_method' },
                                { title: '计量值', width: 100, dataIndex: 'measure_quantity' },
                                { title: '计价', width: 90, dataIndex: 'cost_type' },
                                { title: '分钟单价', width: 110, dataIndex: 'rate_per_minute' },
                                { title: '计件单价', width: 110, dataIndex: 'piece_rate' },
                                { title: '成本', width: 110, dataIndex: 'total_cost' },
                                {
                                  title: '提示',
                                  render: (_, r) => (r.warnings?.length ? <Text type="warning">{r.warnings.join('；')}</Text> : <Text type="secondary">-</Text>),
                                },
                              ]}
                            />
                          ),
                        },
                      ]}
                    />
                    <Alert
                      type="info"
                      showIcon
                      message="说明"
                      description="预览计算基于：工艺模块内物料行（calculation_method/quantity/loss_rate）与步骤行（metadata_json 计价参数）。占位符会按模型 placeholder_mappings 映射后再计价。"
                    />
                  </Space>
                ),
              },
            ]}
          />
        </Form>
      </Drawer>

      <GuideDrawer
        open={guideOpen}
        onClose={() => setGuideOpen(false)}
        title="新建产品模型指南"
        content={productModelGuide}
        tip="提示：这是“产品模型”面板的新建/维护指南（Markdown）。需要调整内容，直接修改对应文档并重新部署即可。"
      />

      <Modal
        title="高级公式模板（推导标准版本用）"
        open={deriveTemplateOpen}
        onCancel={() => setDeriveTemplateOpen(false)}
        onOk={() => {
          if (deriveTemplateRowIndex == null) return
          if (deriveTemplateKind === 'material') {
            const next = materialLines.slice()
            const row = next[deriveTemplateRowIndex]
            if (!row) return
            next[deriveTemplateRowIndex] = {
              ...row,
              metadata_json: {
                ...(row.metadata_json ?? {}),
                derive_template: deriveTemplateDraft,
              },
            }
            setMaterialLines(next)
          } else {
            const next = processLines.slice()
            const row = next[deriveTemplateRowIndex]
            if (!row) return
            next[deriveTemplateRowIndex] = {
              ...row,
              metadata_json: {
                ...(row.metadata_json ?? {}),
                derive_template: deriveTemplateDraft,
              },
            }
            setProcessLines(next)
          }
          message.success('已更新公式模板（请保存版本清单后再推导）')
          setDeriveTemplateOpen(false)
        }}
        okText="应用到当前行"
        width={860}
        destroyOnClose
      >
        <Space direction="vertical" style={{ width: '100%' }} size={12}>
          <Alert
            type="info"
            showIcon
            message="说明"
            description="模板会随打样版本行一起保存（metadata_json.derive_template）。点击“推导标准版本”时，后端按模板计算标准版本(1×1)的 base/fixed/coverage（或 base/unit minutes）。"
          />
          <Space wrap>
            <Select
              value={deriveTemplateDraft?.template_kind ?? 'linear'}
              style={{ width: 200 }}
              options={[{ value: 'linear', label: '线性（base×计量 + fixed）' }]}
              onChange={(v) => setDeriveTemplateDraft({ ...(deriveTemplateDraft ?? {}), template_kind: v })}
            />
            <Switch
              checked={!!deriveTemplateDraft?.calibrate_from_sample}
              onChange={(checked) =>
                setDeriveTemplateDraft({ ...(deriveTemplateDraft ?? {}), calibrate_from_sample: checked })
              }
            />
            <Text type="secondary">用打样数据校准系数（推荐）</Text>
          </Space>

          <Space wrap>
            <InputNumber
              min={0}
              precision={6}
              value={deriveTemplateDraft?.fixed_quantity != null ? Number(deriveTemplateDraft.fixed_quantity) : undefined}
              onChange={(v) => setDeriveTemplateDraft({ ...(deriveTemplateDraft ?? {}), fixed_quantity: v ?? 0 })}
              addonBefore="fixed(α)"
            />
            <InputNumber
              min={0}
              max={1}
              step={0.01}
              precision={4}
              value={deriveTemplateDraft?.coverage_ratio != null ? Number(deriveTemplateDraft.coverage_ratio) : 1}
              onChange={(v) => setDeriveTemplateDraft({ ...(deriveTemplateDraft ?? {}), coverage_ratio: v ?? 1 })}
              addonBefore="覆盖率"
            />
            <InputNumber
              min={0}
              precision={6}
              value={deriveTemplateDraft?.min_total != null ? Number(deriveTemplateDraft.min_total) : undefined}
              onChange={(v) => setDeriveTemplateDraft({ ...(deriveTemplateDraft ?? {}), min_total: v ?? undefined })}
              addonBefore="最小"
            />
            <InputNumber
              min={0}
              precision={6}
              value={deriveTemplateDraft?.max_total != null ? Number(deriveTemplateDraft.max_total) : undefined}
              onChange={(v) => setDeriveTemplateDraft({ ...(deriveTemplateDraft ?? {}), max_total: v ?? undefined })}
              addonBefore="封顶"
            />
          </Space>

          <Card size="small" title="圆整">
            <Space wrap>
              <Select
                style={{ width: 180 }}
                value={deriveTemplateDraft?.rounding?.mode ?? 'round'}
                options={[
                  { value: 'round', label: '四舍五入' },
                  { value: 'floor', label: '向下取整' },
                  { value: 'ceil', label: '向上取整' },
                ]}
                onChange={(v) =>
                  setDeriveTemplateDraft({
                    ...(deriveTemplateDraft ?? {}),
                    rounding: { ...(deriveTemplateDraft?.rounding ?? {}), mode: v },
                  })
                }
              />
              <InputNumber
                min={0.000001}
                precision={6}
                value={deriveTemplateDraft?.rounding?.step != null ? Number(deriveTemplateDraft.rounding.step) : 1}
                onChange={(v) =>
                  setDeriveTemplateDraft({
                    ...(deriveTemplateDraft ?? {}),
                    rounding: { ...(deriveTemplateDraft?.rounding ?? {}), step: v ?? 1 },
                  })
                }
                addonBefore="step"
              />
            </Space>
          </Card>
        </Space>
      </Modal>

      <Modal
        open={modulePickerOpen}
        onCancel={() => setModulePickerOpen(false)}
        onOk={addSelectedModules}
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
            dataSource={modulePickerQuery.data?.items ?? []}
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

      <Modal
        open={targetPickerOpen}
        onCancel={() => setTargetPickerOpen(false)}
        footer={null}
        title={`选择替换目标（${targetPickerKind}）`}
        width={980}
      >
        <Space direction="vertical" style={{ width: '100%' }} size={12}>
          <Space wrap>
            <Input.Search
              allowClear
              placeholder="搜索：编码/名称"
              style={{ width: 320 }}
              onSearch={(v) => setTargetPickerSearch(v.trim())}
            />
            {(targetPickerKind === 'real' || targetPickerKind === 'bom') ? (
              <Select
                allowClear
                placeholder="分类（建议与占位符一致）"
                style={{ width: 220 }}
                value={targetPickerCategory}
                onChange={(v) => setTargetPickerCategory(v)}
                options={MATERIAL_CATEGORIES.map((c) => ({ label: c, value: c }))}
              />
            ) : null}
          </Space>

          {(targetPickerKind === 'real' || targetPickerKind === 'bom') ? (
            <Table
              rowKey="id"
              loading={materialPickerQuery.isLoading}
              dataSource={materialPickerQuery.data?.items ?? []}
              pagination={false}
              columns={[
                { title: '物料编码', dataIndex: 'material_code', width: 160 },
                { title: '物料名称', dataIndex: 'material_name' },
                { title: '分类', dataIndex: 'category', width: 140 },
                { title: '单位', dataIndex: 'unit', width: 90 },
                {
                  title: '操作',
                  width: 100,
                  render: (_, row) => (
                    <Button type="link" onClick={() => selectMaterialAsTarget(row as Material)}>
                      选择
                    </Button>
                  ),
                },
              ]}
            />
          ) : (
            <Table
              rowKey="id"
              loading={virtualPickerQuery.isLoading}
              dataSource={(virtualPickerQuery.data?.items ?? []).filter((vm) => vm.virtual_kind !== 'placeholder')}
              pagination={false}
              columns={[
                { title: '虚拟编码', dataIndex: 'virtual_code', width: 160 },
                { title: '名称', dataIndex: 'name' },
                { title: '类型', dataIndex: 'virtual_kind', width: 120, render: (v: string) => <Tag>{v}</Tag> },
                { title: '单位', dataIndex: 'unit', width: 90 },
                {
                  title: '操作',
                  width: 100,
                  render: (_, row) => (
                    <Button type="link" onClick={() => selectVirtualAsTarget(row as VirtualMaterial)}>
                      选择
                    </Button>
                  ),
                },
              ]}
            />
          )}
        </Space>
      </Modal>
    </Space>
  )
}

export default CostingModelsPage
















