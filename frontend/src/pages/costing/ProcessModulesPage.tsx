import {
  Alert,
  Button,
  Card,
  Col,
  Drawer,
  Empty,
  Form,
  Input,
  InputNumber,
  message,
  Modal,
  Popconfirm,
  Radio,
  Row,
  Select,
  Space,
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
  CheckCircleOutlined,
  CopyOutlined,
  DeleteOutlined,
  EditOutlined,
  ExclamationCircleOutlined,
  EyeOutlined,
  LinkOutlined,
  PlusOutlined,
  QuestionCircleOutlined,
  ReloadOutlined,
  RobotOutlined,
  StopOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import { useEffect, useMemo, useRef, useState } from 'react'
import type { Key } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useLocation, useNavigate } from 'react-router-dom'
import { normalizeUnit } from '@/utils/unit'
import {
  activateProcessModule,
  copyProcessModule,
  createProcessModule,
  deactivateProcessModule,
  deleteProcessModule,
  fetchStructureStandards,
  fetchMaterial,
  fetchProcess,
  fetchVirtualMaterial,
  fetchProcessModule,
  fetchProcessModuleReferences,
  fetchProcessModules,
  fetchProcessReferences,
  fetchTaxonomyItems,
  generateNextCode,
  generateProcessModuleDescription,
  updateProcessModule,
} from '@/services/planner'
import type {
  Material,
  ProcessReference,
  ProcessModuleCopyPayload,
  ProcessModuleCreatePayload,
  ProcessModuleListResponse,
  ProcessModuleMaterialInput,
  ProcessModuleQueryParams,
  ProcessModuleStepInput,
  ProcessModuleSummary,
  ProcessModuleUpdatePayload,
  StructureStandardRead,
  VirtualMaterial,
} from '@/types/planner'
import { CALCULATION_METHOD_OPTIONS } from '@/constants/calculationMethods'
import type { MaterialReferenceKind } from '@/types/planner'
import GuideDrawer from '@/components/common/GuideDrawer'
import processModulesGuide from '@/guides/process_modules_guide.md?raw'
import ProcessModuleAIDrawer from '@/components/costing/ProcessModuleAIDrawer'
import MaterialPickerDrawer from '@/components/costing/MaterialPickerDrawer'
import type { MaterialPickerResult, MaterialPickerTab } from '@/components/costing/MaterialPickerDrawer'

const { Title, Text } = Typography

type StepCostMode = 'time' | 'piece'
type StepMeasureType = 'area' | 'perimeter' | 'width' | 'height' | 'long_side' | 'short_side' | 'count' | 'length'

type StructureApplicabilityMode = 'slot_internal' | 'assembly' | 'global'

const normalizeStringArray = (raw: any): string[] => {
  const arr = Array.isArray(raw) ? raw : raw ? [raw] : []
  const cleaned = arr.map((x: any) => String(x ?? '').trim()).filter(Boolean)
  const seen = new Set<string>()
  return cleaned.filter((x) => (seen.has(x) ? false : (seen.add(x), true)))
}

const computeStructureTags = (args: {
  structureStandardCode?: string
  mode?: StructureApplicabilityMode
  slots?: string[]
}): string[] => {
  const code = String(args.structureStandardCode ?? '').trim()
  const mode = (args.mode ?? 'slot_internal') as StructureApplicabilityMode
  const slots = normalizeStringArray(args.slots ?? [])
  if (mode === 'global') return ['GLOBAL']
  if (!code) return []
  if (mode === 'slot_internal') {
    const slot = String(slots[0] ?? '').trim()
    if (!slot) return []
    return [`${code}:${slot}`]
  }
  // assembly: include CODE + CODE:slot...
  return normalizeStringArray([code, ...slots.map((s) => `${code}:${s}`)])
}

const STEP_MEASURE_TYPE_OPTIONS: Array<{ label: string; value: StepMeasureType; unitHint: string }> = [
  { label: '面积', value: 'area', unitHint: '㎡' },
  { label: '周长', value: 'perimeter', unitHint: 'm' },
  { label: '数量', value: 'count', unitHint: '个' },
  { label: '宽度', value: 'width', unitHint: 'm' },
  { label: '高度', value: 'height', unitHint: 'm' },
  { label: '长边', value: 'long_side', unitHint: 'm' },
  { label: '短边', value: 'short_side', unitHint: 'm' },
  // legacy: historical modules may have 'length' stored; keep compatible option (only shown when already selected)
  { label: '长度（legacy）', value: 'length', unitHint: 'm' },
]

// 统一口径：按 BOM 单位限制计量方式候选
const allowedCalcMethodsByUnit = (
  unit?: string | null,
): Array<'area' | 'perimeter' | 'count' | 'width' | 'height' | 'long_side' | 'short_side'> => {
  const u = normalizeUnit(unit) || unit || ''
  if (u === '平米') return ['area']
  if (u === '米') return ['perimeter', 'width', 'height', 'long_side', 'short_side']
  if (u === '个' || u === '套') return ['count']
  // unknown unit: don't hard block, keep full set to avoid breaking rare units
  return ['area', 'perimeter', 'width', 'height', 'long_side', 'short_side', 'count']
}

const deriveCalcMethodByUnit = (
  unit: string | null | undefined,
  preferred?: string | null,
): 'area' | 'perimeter' | 'count' | 'width' | 'height' | 'long_side' | 'short_side' => {
  const allowed = allowedCalcMethodsByUnit(unit)
  const pref = String(preferred ?? '').trim() as any
  if (pref && allowed.includes(pref)) return pref
  return (allowed[0] ?? 'count') as any
}

const deriveUnitByMeasureType = (measureType?: StepMeasureType | null): '平米' | '米' | '个' => {
  const mt = String(measureType ?? '').trim()
  if (mt === 'area') return '平米'
  if (mt === 'count') return '个'
  return '米'
}

const safeNum = (value: unknown, fallback = 0) => {
  const n = Number(value)
  return Number.isFinite(n) ? n : fallback
}

const truncateText = (value: unknown, maxLen = 600): string | undefined => {
  const s = String(value ?? '').trim()
  if (!s) return undefined
  if (s.length <= maxLen) return s
  return s.slice(0, maxLen) + '…'
}

// 只保留工序 ai_spec 的关键字段，避免 payload 过大导致 LLM 调用变慢
const pickProcessAiSpec = (raw: any): Record<string, any> | undefined => {
  if (!raw || typeof raw !== 'object') return undefined
  const src = raw as Record<string, any>
  const out: Record<string, any> = {}
  const keys = [
    'intent',
    'input',
    'output',
    'scenarios',
    'qc',
    'safety',
    'tools',
    'params_schema',
  ]
  for (const k of keys) {
    const v = src[k]
    if (v === undefined || v === null) continue
    if (typeof v === 'string') {
      const t = truncateText(v, 800)
      if (t) out[k] = t
      continue
    }
    // params_schema 可能是 JSON 对象/数组：控制大小
    if (k === 'params_schema') {
      try {
        const dumped = JSON.stringify(v)
        out[k] = dumped.length > 2000 ? dumped.slice(0, 2000) + '…' : v
      } catch {
        // ignore
      }
      continue
    }
    // 其他字段：尽量保留简单结构
    out[k] = v
  }
  return Object.keys(out).length ? out : undefined
}

const fallbackModuleCode = () => {
  const suffix = String(Date.now() % 10000).padStart(4, '0')
  return `MOD${suffix}`
}

const calcMeasureQty = (
  measureType: StepMeasureType,
  params: { width_mm: number; height_mm: number; length_m: number; count: number },
) => {
  const qty = Math.max(0, safeNum(params.count, 0))
  const w = Math.max(0, safeNum(params.width_mm, 0))
  const h = Math.max(0, safeNum(params.height_mm, 0))
  const len = Math.max(0, safeNum(params.length_m, 0))
  const long = Math.max(w, h)
  const short = Math.min(w, h)
  if (measureType === 'count') return qty
  if (measureType === 'perimeter') return (2 * (w + h)) / 1000 * qty
  if (measureType === 'width') return w / 1000 * qty
  if (measureType === 'height') return h / 1000 * qty
  if (measureType === 'long_side') return long / 1000 * qty
  if (measureType === 'short_side') return short / 1000 * qty
  // legacy: length in meters
  if (measureType === 'length') return len * qty
  // area
  return (w * h) / 1_000_000 * qty
}

type DrawerMode = 'view' | 'edit' | 'create'
type EditorMaterialValue = ProcessModuleMaterialInput & { id?: string }
type EditorStepValue = ProcessModuleStepInput & { id?: string; process?: ProcessReference | null }

const DEFAULT_OPERATOR = import.meta.env.VITE_PLANNER_USER_ID ?? 'planner_user'
const DEFAULT_PAGE_SIZE = 10

const STATUS_OPTIONS = [
  { label: '草稿', value: 'draft' },
  { label: '启用', value: 'active' },
  { label: '停用', value: 'inactive' },
]

// 班组从 taxonomy(team) 动态加载（不再硬编码）

const MATERIAL_KIND_COLOR: Record<string, string> = {
  real: 'blue',
  bom: 'orange',
  virtual: 'purple',
}

const renderCodePill = (code: string, opts?: { color?: string; solid?: boolean }) => {
  const color = opts?.color
  const solid = opts?.solid ?? true
  if (!code) {
    return <Text type="secondary">-</Text>
  }
  return (
    <span
      style={{
        display: 'inline-block',
        padding: '2px 8px',
        borderRadius: 10,
        border: `1px solid ${color ?? '#d9d9d9'}`,
        background: solid ? (color ? `${color}1A` : '#fafafa') : 'transparent',
        color: color ?? 'rgba(0,0,0,0.88)',
        fontFamily:
          'ui-monospace, SFMono-Regular, SF Mono, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace',
        fontSize: 12,
        lineHeight: '18px',
      }}
    >
      {code}
    </span>
  )
}

const parseNum = (value: unknown): number | undefined => {
  if (value === undefined || value === null) return undefined
  const n = Number(value)
  return Number.isFinite(n) ? n : undefined
}

const buildShortDescription = (text: unknown, maxLen = 90): string => {
  const s = String(text ?? '').trim()
  if (!s) return ''
  // 取第一句/前 maxLen
  const cutAt = Math.min(
    ...[s.indexOf('。'), s.indexOf('！'), s.indexOf('？'), s.indexOf('\n')]
      .filter((x) => x >= 0)
      .map((x) => x + 1),
    maxLen,
    s.length,
  )
  const out = s.slice(0, cutAt).trim()
  return out.length > maxLen ? out.slice(0, maxLen).trim() + '…' : out
}

const deriveBomUnitPrice = (material: Material): number | undefined => {
  const meta = (material.metadata_json ?? {}) as Record<string, unknown>
  const metaPrice = parseNum(meta['bom_unit_price'])
  if (metaPrice !== undefined) return metaPrice
  // fallback: unit_price / conversion_purchase_to_bom
  const unitPrice = parseNum(material.unit_price)
  const conversion = parseNum(material.conversion_purchase_to_bom)
  if (unitPrice === undefined || !conversion || conversion <= 0) return undefined
  return unitPrice / conversion
}

const PRICING_METHOD_OPTIONS = [
  { label: '固定工时', value: 'fixed' },
  { label: '按数量', value: 'count' },
  { label: '按面积', value: 'area' },
  { label: '按周长', value: 'perimeter' },
  { label: '按宽度', value: 'width' },
  { label: '按高度', value: 'height' },
]

const createEmptyMaterial = (): ProcessModuleMaterialInput => ({
  material_kind: 'real',
  material_ref_id: undefined,
  material_code: undefined,
  material_name: '',
  unit_of_measure: '',
  calculation_method: 'count',
  quantity: 1,
  loss_rate: 0,
  selection_notes: '',
  loss_notes: '',
})

const createEmptyStep = (order = 1): ProcessModuleStepInput => ({
  sequence_order: order,
  // pricing_method/work_minutes/unit_of_measure 属于历史字段；V1 以 metadata_json 中的计价参数为准
  pricing_method: 'count',
  work_minutes: 0,
  team_name: '',
  unit_of_measure: '',
  description: '',
  notes: '',
  process_id: null,
  // 工序库仅是字典；实际调参落在工艺模块步骤行
  metadata_json: {
    cost_type: 'piece', // 'time' | 'piece'
    base_minutes: 0,
    unit_minutes: 0,
    // 【单位口径】与 normalizeUnit() 一致：平米/米/个/套（避免 Select 回显掉值）
    measure_unit: '个',
    rate_per_minute: null,
    piece_rate: null,
  },
})

const isBlankStepRow = (s: EditorStepValue): boolean => {
  // Treat a row as "blank placeholder" if it has no selected process AND no user-entered meaningful content.
  // This avoids blocking save when the UI keeps empty rows for convenience.
  const processId = String(s.process_id ?? '').trim()
  if (processId) return false

  const team = String(s.team_name ?? '').trim()
  const uom = String(s.unit_of_measure ?? '').trim()
  const desc = String(s.description ?? '').trim()
  const notes = String(s.notes ?? '').trim()

  // If user typed any visible text fields, it's not blank.
  if (team || uom || desc || notes) return false

  // Historical numeric fields: treat positive/meaningful values as non-blank.
  const pricingMethod = String(s.pricing_method ?? '').trim()
  const workMinutes = Number(s.work_minutes ?? 0)
  if (pricingMethod && pricingMethod !== 'count') return false
  if (Number.isFinite(workMinutes) && workMinutes > 0) return false

  const meta = ((s.metadata_json ?? {}) as any) || {}
  // If it contains a snapshot or any non-default pricing params, it's not blank.
  if (meta.process_snapshot) return false
  if (meta.measure_type) return false
  if (Number(meta.base_minutes ?? 0) > 0) return false
  if (Number(meta.unit_minutes ?? 0) > 0) return false
  if (meta.rate_per_minute !== null && meta.rate_per_minute !== undefined && Number(meta.rate_per_minute) > 0) return false
  if (meta.piece_rate !== null && meta.piece_rate !== undefined && Number(meta.piece_rate) > 0) return false

  // measure_unit/cost_type defaults shouldn't count as user input
  return true
}

const deriveStepProcessId = (s: EditorStepValue): string | null => {
  const direct = String(s.process_id ?? '').trim()
  if (direct) return direct
  const fromProcess = String((s.process as any)?.id ?? '').trim()
  if (fromProcess) return fromProcess
  const meta = ((s.metadata_json ?? {}) as any) || {}
  // backend historical: process_snapshot.process_id (not id)
  const fromSnapshotId = String(meta?.process_snapshot?.id ?? '').trim()
  if (fromSnapshotId) return fromSnapshotId
  const fromSnapshotProcessId = String(meta?.process_snapshot?.process_id ?? '').trim()
  return fromSnapshotProcessId || null
}

const deriveStepProcessCode = (s: EditorStepValue): string | null => {
  const fromProcess = String((s.process as any)?.process_code ?? '').trim()
  if (fromProcess) return fromProcess
  const meta = ((s.metadata_json ?? {}) as any) || {}
  const fromSnapshot = String(meta?.process_snapshot?.process_code ?? '').trim()
  return fromSnapshot || null
}

const isUuid = (value: unknown): boolean => {
  const s = String(value ?? '').trim()
  // UUID v4-ish format (we don't validate version bits strictly; just block obvious junk like "null")
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(s)
}

const ProcessModulesPage = () => {
  const queryClient = useQueryClient()
  const location = useLocation() as any
  const navigate = useNavigate()
  const [filtersForm] = Form.useForm()
  const [editorForm] = Form.useForm()
  const [filters, setFilters] = useState<ProcessModuleQueryParams>({})
  const [pagination, setPagination] = useState({ current: 1, pageSize: DEFAULT_PAGE_SIZE })
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [drawerMode, setDrawerMode] = useState<DrawerMode>('view')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [guideOpen, setGuideOpen] = useState(false)
  const [aiDrawerOpen, setAiDrawerOpen] = useState(false)
  const [aiModuleId, setAiModuleId] = useState<string | null>(null)
  const [materialsLocal, setMaterialsLocal] = useState<EditorMaterialValue[]>([])
  const [stepsLocal, setStepsLocal] = useState<EditorStepValue[]>([])
  const [materialPickerContext, setMaterialPickerContext] = useState<{
    targetIndex?: number
    initialTab?: MaterialPickerTab
  } | null>(null)
  const [processSelectContext, setProcessSelectContext] = useState<{
    targetIndex?: number
  } | null>(null)
  const [referenceDrawerOpen, setReferenceDrawerOpen] = useState(false)
  const [generatingDescription, setGeneratingDescription] = useState(false)

  // Guard against late detailQuery hydration overwriting user edits (common when user starts selecting before detail loads).
  const hydratedRef = useRef(false)
  const lastHydratedIdRef = useRef<string | null>(null)
  const userTouchedRef = useRef(false)
  const suppressTouchRef = useRef(false)

  // 支持从其它页面（例如“关联引用”区块）跳转并直接打开当前工艺模块编辑抽屉
  useEffect(() => {
    const st = (location as any)?.state ?? {}
    const openId = String(st?.openProcessModuleId ?? '').trim()
    if (!openId) return
    if (!isUuid(openId)) {
      // Clear invalid state early; avoid accidental requests like /process-modules/null
      navigate(location.pathname, { replace: true, state: null })
      return
    }
    setDrawerMode('view')
    setSelectedId(openId)
    setDrawerOpen(true)
    // 清掉 state，避免刷新/返回时重复弹抽屉
    navigate(location.pathname, { replace: true, state: null })
  }, [location, navigate])

  useEffect(() => {
    if (!drawerOpen) return
    // switching selected record while drawer open should re-hydrate cleanly
    hydratedRef.current = false
    lastHydratedIdRef.current = null
    userTouchedRef.current = false
  }, [drawerOpen, selectedId])

  const listQuery = useQuery<ProcessModuleListResponse>({
    queryKey: ['process-modules', filters, pagination],
    queryFn: () =>
      fetchProcessModules({
        ...filters,
        page: pagination.current,
        page_size: pagination.pageSize,
      }),
    placeholderData: (previousData) => previousData,
  })

  const moduleCategoryQuery = useQuery({
    queryKey: ['taxonomy-items', 'process_module_category'],
    queryFn: () => fetchTaxonomyItems('process_module_category', { include_inactive: true }),
  })

  const teamQuery = useQuery({
    queryKey: ['taxonomy-items', 'team'],
    queryFn: () => fetchTaxonomyItems('team', { include_inactive: true }),
  })

  const structureStandardsQuery = useQuery({
    queryKey: ['structure-standards', 'dropdown'],
    enabled: drawerOpen,
    staleTime: 5 * 60 * 1000,
    queryFn: () => fetchStructureStandards({ status: 'all', page: 1, page_size: 500 }),
  })

  const teamRateByName = useMemo(() => {
    const m = new Map<string, number>()
    for (const it of teamQuery.data?.items ?? []) {
      const name = String((it as any)?.name ?? '').trim()
      const meta = (it as any)?.metadata ?? (it as any)?.metadata_json ?? {}
      const rate = Number(meta?.rate_per_minute)
      if (name && Number.isFinite(rate) && rate >= 0) m.set(name, rate)
    }
    return m
  }, [teamQuery.data?.items])

  const detailQuery = useQuery({
    queryKey: ['process-module', selectedId],
    queryFn: () => fetchProcessModule(selectedId as string),
    enabled: drawerOpen && isUuid(selectedId),
  })

  const referencesQuery = useQuery({
    queryKey: ['process-module-references', selectedId],
    queryFn: () =>
      fetchProcessModuleReferences({
        module_ids: selectedId ? [selectedId] : undefined,
        status: 'active',
      }),
    enabled: referenceDrawerOpen && isUuid(selectedId),
  })

  const createMutation = useMutation({
    mutationFn: (payload: ProcessModuleCreatePayload) => createProcessModule(payload),
    onSuccess: (data) => {
      message.success('工艺模块已创建')
      queryClient.invalidateQueries({ queryKey: ['process-modules'] })
      setSelectedId(data.id)
      setDrawerMode('view')
      detailQuery.refetch()
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: ProcessModuleUpdatePayload }) =>
      updateProcessModule(id, payload),
    onSuccess: () => {
      message.success('工艺模块已更新')
      queryClient.invalidateQueries({ queryKey: ['process-modules'] })
      if (selectedId) {
        detailQuery.refetch()
      }
      setDrawerMode('view')
    },
  })

  const activateMutation = useMutation({
    mutationFn: activateProcessModule,
    onSuccess: () => {
      message.success('模块已启用')
      queryClient.invalidateQueries({ queryKey: ['process-modules'] })
      detailQuery.refetch()
    },
  })

  const deactivateMutation = useMutation({
    mutationFn: deactivateProcessModule,
    onSuccess: () => {
      message.success('模块已停用')
      queryClient.invalidateQueries({ queryKey: ['process-modules'] })
      detailQuery.refetch()
    },
  })

  const confirmDeleteModule = (record: ProcessModuleSummary) => {
    const status = String(record.status ?? '').trim()
    if (status === 'active') {
      message.info('请先停用该工艺模块，再执行删除（归档）')
      return
    }
    let typed = ''
    Modal.confirm({
      title: '删除工艺模块（归档）',
      okText: '删除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      content: (
        <Space direction="vertical" style={{ width: '100%' }}>
          <Text>
            将删除（归档）：<Text code>{record.module_code}</Text> {record.module_name}
          </Text>
          <Text type="secondary">为避免误删，请输入模块编码确认删除：</Text>
          <Input placeholder={record.module_code} onChange={(e) => (typed = String(e.target.value ?? ''))} />
          <Text type="secondary">提示：若该模块仍被模型引用，后端会阻止删除。</Text>
        </Space>
      ),
      onOk: async () => {
        if (typed.trim() !== String(record.module_code ?? '').trim()) {
          message.error('输入不匹配，未执行删除')
          return Promise.reject(new Error('confirm_mismatch'))
        }
        try {
          await deleteProcessModule(record.id)
          message.success('已删除（归档）')
          queryClient.invalidateQueries({ queryKey: ['process-modules'] })
          if (selectedId) detailQuery.refetch()
        } catch (err: any) {
          message.error(err?.response?.data?.detail ?? err?.message ?? '删除失败')
          return Promise.reject(err)
        }
      },
    })
  }

  const copyMutation = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: ProcessModuleCopyPayload }) =>
      copyProcessModule(id, payload),
    onSuccess: (data) => {
      message.success('模块已复制')
      queryClient.invalidateQueries({ queryKey: ['process-modules'] })
      setSelectedId(data.id)
      setDrawerMode('view')
      detailQuery.refetch()
    },
  })

  useEffect(() => {
    if (!drawerOpen) {
      hydratedRef.current = false
      lastHydratedIdRef.current = null
      userTouchedRef.current = false
      suppressTouchRef.current = false
      editorForm.resetFields()
      setMaterialsLocal([])
      setStepsLocal([])
      setDrawerMode('view')
      return
    }
    if (drawerMode === 'create') {
      hydratedRef.current = true
      lastHydratedIdRef.current = 'create'
      userTouchedRef.current = false
      suppressTouchRef.current = true
      editorForm.setFieldsValue({
        module_code: '',
        module_name: '',
        description: '',
        category: '',
        status: 'draft',
        tags: [],
        structure_standard_code: '',
        structure_applicability_mode: 'slot_internal',
        structure_slots: [],
        structure_tags: [],
        materials: [],
        steps: [],
      })
      setMaterialsLocal([])
      setStepsLocal([])
      suppressTouchRef.current = false
    } else if (detailQuery.data) {
      const module = detailQuery.data
      // hydrate once per module id (don't overwrite user edits)
      if (
        !userTouchedRef.current &&
        (!hydratedRef.current || (module.id && lastHydratedIdRef.current !== module.id))
      ) {
        suppressTouchRef.current = true
        const meta = ((module.metadata_json ?? {}) as any) || {}
        const stdCode = String(meta?.structure_standard_code ?? '').trim()
        const modeRaw = String(meta?.structure_applicability_mode ?? '').trim()
        const mode: StructureApplicabilityMode =
          modeRaw === 'assembly' || modeRaw === 'global' || modeRaw === 'slot_internal'
            ? (modeRaw as any)
            : 'slot_internal'
        const slots = normalizeStringArray(meta?.structure_slots ?? [])
        const tags = normalizeStringArray(meta?.structure_tags ?? [])
        const nextMaterials = module.materials.length ? (module.materials as any) : []
        // IMPORTANT: backend copied modules may have step.process_id = null but embed process id in metadata_json.process_snapshot.process_id.
        // AntD Form may drop unregistered nested fields (like process_snapshot) in getFieldsValue(),
        // so we must normalize it into the canonical step.process_id at hydration time.
        const nextSteps = (module.steps.length ? (module.steps as any) : []).map((s: any) => {
          const direct = String(s?.process_id ?? '').trim()
          if (direct) return s
          const snap = (s?.metadata_json ?? {})?.process_snapshot ?? {}
          const snapPid = String((snap as any)?.process_id ?? (snap as any)?.id ?? '').trim()
          return snapPid ? { ...s, process_id: snapPid } : s
        })
        editorForm.setFieldsValue({
          module_code: module.module_code,
          module_name: module.module_name,
          description: module.description,
          category: module.category,
          status: module.status,
          tags: module.tags ?? [],
          structure_standard_code: stdCode,
          structure_applicability_mode: mode,
          structure_slots: slots,
          structure_tags: tags,
          materials: nextMaterials,
          steps: nextSteps,
        })
        setMaterialsLocal(nextMaterials)
        setStepsLocal(nextSteps)
        suppressTouchRef.current = false
        hydratedRef.current = true
        lastHydratedIdRef.current = module.id ?? null
        userTouchedRef.current = false
      }
    }
  }, [drawerOpen, drawerMode, detailQuery.data, editorForm])

  const materialsValue = Form.useWatch('materials', editorForm) as EditorMaterialValue[] | undefined
  const stepsValue = Form.useWatch('steps', editorForm) as EditorStepValue[] | undefined

  const structureStandardCodeValue = Form.useWatch('structure_standard_code', editorForm) as string | undefined
  const structureModeValue = Form.useWatch(
    'structure_applicability_mode',
    editorForm,
  ) as StructureApplicabilityMode | undefined
  const structureSlotsValue = Form.useWatch('structure_slots', editorForm) as string[] | undefined

  const computedStructureTags = useMemo(() => {
    return computeStructureTags({
      structureStandardCode: structureStandardCodeValue,
      mode: (structureModeValue ?? 'slot_internal') as any,
      slots: structureSlotsValue ?? [],
    })
  }, [structureStandardCodeValue, structureModeValue, structureSlotsValue])

  const structureStandardByCode = useMemo(() => {
    const m = new Map<string, StructureStandardRead>()
    for (const it of structureStandardsQuery.data?.items ?? []) {
      const code = String(it.code ?? '').trim()
      if (!code) continue
      m.set(code, it)
    }
    return m
  }, [structureStandardsQuery.data?.items])

  const selectedStructureStandard = useMemo(() => {
    const code = String(structureStandardCodeValue ?? '').trim()
    return code ? structureStandardByCode.get(code) ?? null : null
  }, [structureStandardByCode, structureStandardCodeValue])

  const selectedStructureSlotHints = useMemo(() => {
    const mode = String(structureModeValue ?? 'slot_internal') as StructureApplicabilityMode
    if (mode === 'global') return []
    if (!selectedStructureStandard) return []
    const slots = normalizeStringArray(structureSlotsValue ?? [])
    if (!slots.length) return []

    const labelByCode = selectedStructureStandard.slot_display_names ?? {}
    const defByCode = new Map<string, any>()
    for (const d of (selectedStructureStandard.slot_defs ?? []) as any[]) {
      const c = String(d?.code ?? '').trim()
      if (c) defByCode.set(c, d)
    }

    return slots.map((s) => {
      const d = defByCode.get(s) ?? {}
      const cn = String((labelByCode as any)?.[s] ?? '').trim()
      return {
        slot: s,
        label: cn ? `${cn}（${s}）` : s,
        driver_quantity: String(d?.driver_quantity ?? '').trim() || null,
        remark: String(d?.remark ?? '').trim() || null,
      }
    })
  }, [selectedStructureStandard, structureModeValue, structureSlotsValue])

  // Auto-maintain structure_tags based on structure standard + mode + slots
  useEffect(() => {
    if (!drawerOpen) return
    if (drawerMode !== 'edit' && drawerMode !== 'create') return
    suppressTouchRef.current = true
    try {
      editorForm.setFieldValue('structure_tags', computedStructureTags)
    } finally {
      suppressTouchRef.current = false
    }
  }, [drawerOpen, drawerMode, editorForm, computedStructureTags])

  const [previewInput, setPreviewInput] = useState({
    width_mm: 0,
    height_mm: 0,
    length_m: 0,
    count: 1,
  })

  const previewResult = useMemo(() => {
    // prefer local state (table source-of-truth), fallback to form watch
    const steps = (stepsLocal.length ? stepsLocal : stepsValue) ?? []
    const rows = steps.map((step, index) => {
      const meta = (step.metadata_json ?? {}) as Record<string, unknown>
      const costMode = (meta.cost_mode as StepCostMode) ?? (safeNum(meta.rate_per_minute, NaN) > 0 ? 'time' : 'piece')
      const measureType = (meta.measure_type as StepMeasureType) ?? 'count'
      const measureQty = calcMeasureQty(measureType, previewInput)

      const baseMinutes = safeNum(meta.base_minutes, 0)
      const unitMinutes = safeNum(meta.unit_minutes, 0)
      const ratePerMinute = safeNum(meta.rate_per_minute, 0)
      const pieceRate = safeNum(meta.piece_rate, 0)

      const minutes = baseMinutes + unitMinutes * measureQty
      const cost = costMode === 'time' ? minutes * ratePerMinute : pieceRate * measureQty

      const snapshot =
        step.process ??
        ((meta.process_snapshot as any) as ProcessReference | undefined)
      const name = snapshot ? `${snapshot.process_code} - ${snapshot.process_name}` : step.team_name || `Step ${index + 1}`

      const warnings: string[] = []
      if (measureQty <= 0) warnings.push('计价量=0')
      if (costMode === 'time' && ratePerMinute <= 0) warnings.push('分钟单价未配置')
      if (costMode === 'piece' && pieceRate <= 0) warnings.push('计件单价未配置')

      return {
        key: step.id ?? index,
        index,
        name,
        cost_mode: costMode,
        measure_type: measureType,
        measure_qty: measureQty,
        minutes,
        cost,
        warnings,
      }
    })
    const total = rows.reduce((acc, item) => acc + safeNum(item.cost, 0), 0)
    return { rows, total }
  }, [stepsValue, previewInput])

  const handleFilterSubmit = () => {
    const values = filtersForm.getFieldsValue()
    setFilters({
      search: values.search?.trim() || undefined,
      status: values.status || undefined,
      category: values.category || undefined,
      structure_code: values.structure_code?.trim() || undefined,
      structure_tag: values.structure_tag?.trim() || undefined,
    })
    setPagination((prev) => ({ ...prev, current: 1 }))
  }

  const handleFilterReset = () => {
    filtersForm.resetFields()
    setFilters({})
    setPagination({ current: 1, pageSize: DEFAULT_PAGE_SIZE })
  }

  const openCreateDrawer = () => {
    // hard reset to avoid any stale local rows showing up as "empty records"
    suppressTouchRef.current = true
    editorForm.resetFields()
    setMaterialsLocal([])
    setStepsLocal([])
    suppressTouchRef.current = false
    setDrawerMode('create')
    setSelectedId(null)
    setDrawerOpen(true)
  }

  const openViewDrawer = (record: ProcessModuleSummary) => {
    setDrawerMode('view')
    setSelectedId(record.id)
    setDrawerOpen(true)
  }

  const moduleListColumns: ColumnsType<ProcessModuleSummary> = [
    {
      title: '编码',
      dataIndex: 'module_code',
      key: 'module_code',
      width: 90,
      render: (value: string) => <Text code>{value}</Text>,
    },
    {
      title: '工艺模块',
      key: 'module_info',
      width: 320,
      render: (_: any, r: ProcessModuleSummary) => {
        const category = String(r.category ?? '').trim() || '-'
        const version = r.version ?? '-'
        const refCount = (r.metadata_json as any)?.reference_count ?? '-'
        const status = String(r.status ?? '').trim()
        const statusLabel = status === 'active' ? '启用' : status === 'inactive' ? '停用' : '草稿'
        const statusColor = status === 'active' ? 'green' : status === 'inactive' ? 'red' : 'gold'
        const tagsRaw = (r.tags ?? []) as any
        const tags = Array.isArray(tagsRaw)
          ? tagsRaw.map((x: any) => String(x ?? '').trim()).filter(Boolean)
          : []

        return (
          <div style={{ lineHeight: 1.25 }}>
            <div>
              <Space size={8} wrap>
                <Text strong ellipsis={{ tooltip: r.module_name }}>
                  {r.module_name}
                </Text>
                <Tag color={statusColor} style={{ marginInlineEnd: 0 }}>
                  {statusLabel}
                </Tag>
              </Space>
            </div>
            <div style={{ marginTop: 4 }}>
              <Space size={6} wrap>
                <Text type="secondary">
                  分类：{category}；版本：{version}；引用：{refCount}
                </Text>
                {tags.slice(0, 3).map((t: string) => (
                  <Tag
                    key={t}
                    style={{
                      marginInlineEnd: 0,
                      borderRadius: 999,
                      padding: '0 6px',
                      fontSize: 12,
                      lineHeight: '18px',
                    }}
                  >
                    {t}
                  </Tag>
                ))}
                {tags.length > 3 ? (
                  <Tag
                    style={{
                      marginInlineEnd: 0,
                      borderRadius: 999,
                      padding: '0 6px',
                      fontSize: 12,
                      lineHeight: '18px',
                    }}
                  >
                    +{tags.length - 3}
                  </Tag>
                ) : null}
              </Space>
            </div>
          </div>
        )
      },
    },
    {
      title: '结构标签',
      key: 'structure_tags',
      width: 220,
      render: (_: any, r: ProcessModuleSummary) => {
        const meta = ((r.metadata_json ?? {}) as any) || {}
        const raw = meta?.structure_tags
        const tags = Array.isArray(raw)
          ? raw.map((x: any) => String(x ?? '').trim()).filter(Boolean)
          : []
        if (!tags.length) return <Text type="secondary">-</Text>
        const show = tags.slice(0, 3)
        const rest = tags.length - show.length
        return (
          <Space size={6} wrap>
            {show.map((t) => (
              <Tag
                key={t}
                style={{
                  marginInlineEnd: 0,
                  borderRadius: 999,
                  padding: '0 6px',
                  fontSize: 12,
                  lineHeight: '18px',
                }}
              >
                {t}
              </Tag>
            ))}
            {rest > 0 ? (
              <Tag
                style={{
                  marginInlineEnd: 0,
                  borderRadius: 999,
                  padding: '0 6px',
                  fontSize: 12,
                  lineHeight: '18px',
                }}
              >
                …+{rest}
              </Tag>
            ) : null}
          </Space>
        )
      },
    },
    {
      title: '描述',
      dataIndex: 'description',
      key: 'description',
      width: 420,
      render: (value?: string | null) => (
        <Typography.Paragraph
          style={{ marginBottom: 0, lineHeight: 1.25 }}
          ellipsis={{ rows: 2, tooltip: value || '-' }}
        >
          {value || '-'}
        </Typography.Paragraph>
      ),
    },
    {
      title: '更新时间',
      dataIndex: 'updated_at',
      key: 'updated_at',
      width: 150,
      render: (value: string) => dayjs(value).format('YYYY-MM-DD HH:mm'),
    },
    {
      title: '操作',
      key: 'actions',
      width: 180,
      fixed: 'right',
      render: (_, record) => {
        const status = String(record.status ?? '').trim()
        return (
          <Space size={4} wrap>
            <Tooltip title="查看">
              <Button size="small" icon={<EyeOutlined />} onClick={() => openViewDrawer(record)} />
            </Tooltip>
            <Tooltip title="编辑">
              <Button
                size="small"
                icon={<EditOutlined />}
                onClick={() => {
                  setSelectedId(record.id)
                  setDrawerMode('edit')
                  setDrawerOpen(true)
                }}
              />
            </Tooltip>
            <Tooltip title="AI">
              <Button
                size="small"
                icon={<RobotOutlined />}
                onClick={() => {
                  setAiModuleId(record.id)
                  setAiDrawerOpen(true)
                }}
              />
            </Tooltip>
            <Tooltip title="复制">
              <Button
                size="small"
                icon={<CopyOutlined />}
                onClick={async () => {
                  let newCode = fallbackModuleCode()
                  try {
                    newCode = (await generateNextCode({ prefix: 'MOD', width: 4 })).code
                  } catch {
                    // keep fallback
                  }
                  const payload: ProcessModuleCopyPayload = {
                    module_code: newCode,
                    module_name: `${record.module_name}（复制）`,
                    status: 'draft',
                    operator_id: DEFAULT_OPERATOR,
                  }
                  copyMutation.mutate({ id: record.id, payload })
                }}
              />
            </Tooltip>
            {status === 'active' ? (
              <Popconfirm
                title="确认停用该工艺模块？"
                okText="停用"
                cancelText="取消"
                onConfirm={() => deactivateMutation.mutate(record.id)}
              >
                <Tooltip title="停用">
                  <Button size="small" danger icon={<StopOutlined />} />
                </Tooltip>
              </Popconfirm>
            ) : (
              <>
                <Popconfirm
                  title="确认启用该工艺模块？"
                  okText="启用"
                  cancelText="取消"
                  onConfirm={() => activateMutation.mutate(record.id)}
                >
                  <Tooltip title="启用">
                    <Button size="small" icon={<CheckCircleOutlined style={{ color: '#52c41a' }} />} />
                  </Tooltip>
                </Popconfirm>
              </>
            )}
            <Tooltip title={status === 'active' ? '请先停用，再删除（归档）' : '删除（归档）'}>
              <Button
                size="small"
                danger
                icon={<DeleteOutlined />}
                disabled={status === 'active'}
                onClick={() => confirmDeleteModule(record)}
              />
            </Tooltip>
          </Space>
        )
      },
    },
  ]

  const materialsDataSource =
    (materialsLocal.length ? materialsLocal : materialsValue)?.map((item, index) => ({
      key: item.id ?? index,
      index,
      record: item,
    })) ?? []

  const stepsDataSource =
    (stepsLocal.length ? stepsLocal : stepsValue)?.map((item, index) => ({
      key: item.id ?? index,
      index,
      record: item,
    })) ?? []

  const updateMaterials = (updater: (prev: EditorMaterialValue[]) => EditorMaterialValue[]) => {
    const prev = (editorForm.getFieldValue('materials') as EditorMaterialValue[]) ?? []
    const next = updater(prev)
    editorForm.setFieldValue('materials', next)
    setMaterialsLocal(next)
  }

  const updateSteps = (updater: (prev: EditorStepValue[]) => EditorStepValue[]) => {
    const prev = (editorForm.getFieldValue('steps') as EditorStepValue[]) ?? []
    const next = updater(prev)
    editorForm.setFieldValue('steps', next)
    setStepsLocal(next)
  }

  const handleRemoveMaterial = (index: number) => {
    updateMaterials((prev) => prev.filter((_, idx) => idx !== index))
  }

  const handleDuplicateMaterial = (index: number) => {
    updateMaterials((prev) => {
      const target = prev[index]
      if (!target) return prev
      const clone = { ...target }
      return [...prev.slice(0, index + 1), clone, ...prev.slice(index + 1)]
    })
  }

  const handleMoveMaterial = (index: number, direction: 'up' | 'down') => {
    updateMaterials((prev) => {
      const targetIndex = direction === 'up' ? index - 1 : index + 1
      if (targetIndex < 0 || targetIndex >= prev.length) return prev
      const next = [...prev]
      const temp = next[index]
      next[index] = next[targetIndex]
      next[targetIndex] = temp
      return next
    })
  }

  const handleRemoveStep = (index: number) => {
    updateSteps((prev) => prev.filter((_, idx) => idx !== index))
  }

  const handleDuplicateStep = (index: number) => {
    updateSteps((prev) => {
      const target = prev[index]
      if (!target) return prev
      const clone = { ...target }
      return [...prev.slice(0, index + 1), clone, ...prev.slice(index + 1)]
    })
  }

  const handleMoveStep = (index: number, direction: 'up' | 'down') => {
    updateSteps((prev) => {
      const targetIndex = direction === 'up' ? index - 1 : index + 1
      if (targetIndex < 0 || targetIndex >= prev.length) return prev
      const next = [...prev]
      const temp = next[index]
      next[index] = next[targetIndex]
      next[targetIndex] = temp
      return next
    })
  }

  const handleAddBlankMaterial = () => {
    updateMaterials((prev) => [...prev, createEmptyMaterial()])
  }

  const handleAddBlankStep = () => {
    updateSteps((prev) => [...prev, createEmptyStep(prev.length + 1)])
  }

  const buildPayload = (): {
    create: ProcessModuleCreatePayload
    update: ProcessModuleUpdatePayload
  } => {
    const values = editorForm.getFieldsValue()
    const structureStandardCode = String(values.structure_standard_code ?? '').trim() || null
    const structureMode = String(values.structure_applicability_mode ?? 'slot_internal').trim() as StructureApplicabilityMode
    const structureSlots = normalizeStringArray(values.structure_slots ?? [])
    const structureTags = computeStructureTags({
      structureStandardCode: structureStandardCode ?? undefined,
      mode: structureMode,
      slots: structureSlots,
    })
    const normalizeMaterials = (items: EditorMaterialValue[] = []) =>
      items
        .filter((item) => Boolean(item.material_ref_id))
        .map((item, index) => ({
        material_kind: item.material_kind ?? 'real',
        material_ref_id: item.material_ref_id ?? null,
        material_code: item.material_code,
        material_name: item.material_name,
        unit_of_measure: item.unit_of_measure,
        calculation_method: (() => {
          const unitOfMeasure = item.unit_of_measure
          const meta = (item.metadata_json ?? {}) as any
          const bomUnit = normalizeUnit(meta?.bom_unit ?? unitOfMeasure) || meta?.bom_unit || unitOfMeasure
          return deriveCalcMethodByUnit(bomUnit, String(item.calculation_method ?? '').trim() || null)
        })(),
        quantity: item.quantity ?? 0,
        loss_rate: item.loss_rate ?? 0,
        sequence_order: item.sequence_order ?? index,
        material_category: item.material_category,
        selection_notes: item.selection_notes,
        loss_notes: item.loss_notes,
        metadata_json: item.metadata_json ?? {},
      }))

    const normalizeSteps = (items: EditorStepValue[] = []) =>
      items
        .map((item) => ({ item, processId: deriveStepProcessId(item) }))
        .filter(({ processId }) => Boolean(processId))
        .map(({ item, processId }, index) => ({
        process_id: processId,
        sequence_order: item.sequence_order ?? index,
        team_name: item.team_name,
        pricing_method: item.pricing_method ?? 'count',
        work_minutes: item.work_minutes ?? 0,
        unit_of_measure: item.unit_of_measure,
        description: item.description,
        notes: item.notes,
        metadata_json: (() => {
          const meta = (item.metadata_json ?? {}) as any
          const mt = String(meta?.measure_type ?? '').trim() as StepMeasureType
          const unit = deriveUnitByMeasureType(mt || null)
          return { ...meta, measure_unit: unit }
        })(),
      }))

    return {
      create: {
        module_code: values.module_code,
        module_name: values.module_name,
        description: values.description,
        category: values.category,
        status: values.status,
        tags: values.tags ?? [],
        metadata_json: {
          structure_standard_code: structureStandardCode,
          structure_applicability_mode: structureMode,
          structure_slots: structureSlots,
          structure_tags: structureTags,
        },
        materials: normalizeMaterials(values.materials),
        steps: normalizeSteps(values.steps),
        operator_id: DEFAULT_OPERATOR,
      },
      update: {
        module_name: values.module_name,
        description: values.description,
        category: values.category,
        status: values.status,
        tags: values.tags ?? [],
        // 关键：更新时必须保留原 metadata_json（否则会把 AI/扩展字段覆盖成空对象）
        metadata_json: {
          ...(((detailQuery.data?.metadata_json ?? {}) as any) || {}),
          structure_standard_code: structureStandardCode,
          structure_applicability_mode: structureMode,
          structure_slots: structureSlots,
          structure_tags: structureTags,
        } as any,
        materials: normalizeMaterials(values.materials),
        steps: normalizeSteps(values.steps),
        operator_id: DEFAULT_OPERATOR,
      },
    }
  }

  const handleSave = async () => {
    // Create: allocate code only when user actually clicks "创建"
    if (drawerMode === 'create') {
      const currentCode = String(editorForm.getFieldValue('module_code') || '').trim()
      if (!currentCode) {
        try {
          const res = await generateNextCode({ prefix: 'MOD', width: 4 })
          editorForm.setFieldValue('module_code', res.code)
        } catch {
          editorForm.setFieldValue('module_code', fallbackModuleCode())
        }
      }
    }
    await editorForm.validateFields()
    // prevent saving with placeholder rows (user sees "empty records")
    let values = editorForm.getFieldsValue()

    // structure applicability validation (strong guardrail)
    {
      const mode = String(values.structure_applicability_mode ?? 'slot_internal') as any
      const code = String(values.structure_standard_code ?? '').trim()
      const slots = normalizeStringArray(values.structure_slots ?? [])
      if (mode === 'global') {
        if (slots.length) {
          message.error('适用类型为 global 时无需选择 slots，请先清空 slots')
          return
        }
      } else {
        if (!code) {
          message.error('请选择结构标准（非 global 时必填）')
          return
        }
        if (mode === 'slot_internal') {
          if (slots.length !== 1) {
            message.error('内用（slot）必须且只能选择 1 个 slot')
            return
          }
        } else if (mode === 'assembly') {
          if (slots.length < 2) {
            message.error('组合/装配（assembly）至少选择 2 个 slots')
            return
          }
        }
      }
    }

    const rawMaterials = (values.materials ?? []) as EditorMaterialValue[]
    let rawSteps = (values.steps ?? []) as EditorStepValue[]

    // Auto-repair for copied modules:
    // some steps may have process_snapshot.process_code but missing process_id (backend requires id).
    // Try resolving by unique exact match of process_code in /processes/references.
    {
      const targets = rawSteps
        .map((s, idx) => ({ s, rowNo: idx + 1 }))
        .filter(({ s }) => !deriveStepProcessId(s) && !isBlankStepRow(s) && Boolean(deriveStepProcessCode(s)))

      if (targets.length) {
        const codeToRows = new Map<string, number[]>()
        for (const t of targets) {
          const code = String(deriveStepProcessCode(t.s) ?? '').trim()
          if (!code) continue
          const rows = codeToRows.get(code) ?? []
          rows.push(t.rowNo)
          codeToRows.set(code, rows)
        }

        const unresolved: Array<{ code: string; rows: number[]; reason: 'not_found' | 'ambiguous' }> = []
        const resolvedByRow = new Map<number, ProcessReference>() // rowNo -> process ref

        const hide = message.loading('检测到工序ID缺失，正在按工序编码自动修复...', 0)
        try {
          for (const [code, rows] of codeToRows.entries()) {
            const list = await fetchProcessReferences({
              search: code,
              status: 'active',
              limit: 200,
            } as any)
            const exact = (list ?? []).filter((p) => String((p as any).process_code ?? '').trim() === code)
            if (exact.length === 1) {
              for (const rowNo of rows) resolvedByRow.set(rowNo, exact[0])
            } else if (exact.length === 0) {
              unresolved.push({ code, rows, reason: 'not_found' })
            } else {
              unresolved.push({ code, rows, reason: 'ambiguous' })
            }
          }
        } finally {
          hide()
        }

        if (resolvedByRow.size) {
          updateSteps((prev) => {
            const next = prev.slice()
            for (const [rowNo, ref] of resolvedByRow.entries()) {
              const idx = rowNo - 1
              const cur = next[idx]
              if (!cur) continue
              if (deriveStepProcessId(cur)) continue
              next[idx] = {
                ...cur,
                process_id: ref.id,
                process: ref,
                metadata_json: {
                  ...(cur.metadata_json ?? {}),
                  process_snapshot: {
                    ...(typeof (cur.metadata_json as any)?.process_snapshot === 'object'
                      ? (cur.metadata_json as any).process_snapshot
                      : {}),
                    ...ref,
                  },
                },
              }
            }
            return next
          })
          values = editorForm.getFieldsValue()
          rawSteps = (values.steps ?? []) as EditorStepValue[]
        }

        if (unresolved.length) {
          const parts = unresolved.map((u) => {
            const rows = u.rows.join('、')
            const suffix = u.reason === 'not_found' ? '未找到匹配工序' : '匹配到多个工序（不唯一）'
            return `第 ${rows} 行（${u.code}）：${suffix}`
          })
          message.error(`工序ID缺失，自动修复失败：${parts.join('；')}。请点“链条”按钮重新选择工序。`)
          return
        }
      }
    }
    const invalidMaterialRows = rawMaterials
      .map((m, idx) => ({ m, idx: idx + 1 }))
      .filter(({ m }) => !m.material_ref_id && (m.material_code || m.material_name))
      .map(({ idx }) => idx)
    const invalidStepRows = rawSteps
      .map((s, idx) => ({ s, idx: idx + 1 }))
      .filter(({ s }) => !deriveStepProcessId(s) && !isBlankStepRow(s))
      .map(({ idx }) => idx)
    if (invalidMaterialRows.length) {
      message.error(`物料组存在未选择物料的行：第 ${invalidMaterialRows.join('、')} 行，请先删除或重新选择`)
      return
    }
    if (invalidStepRows.length) {
      // steps can be empty; but if user added rows, require selecting process
      message.error(`工序组存在未选择工序的行：第 ${invalidStepRows.join('、')} 行，请先删除或选择工序`)
      return
    }
    // materials duplicate guard: same material + same calculation_method should be merged before saving
    const materials = (values.materials ?? []) as EditorMaterialValue[]
    const dupMap = new Map<string, { key: string; indices: number[] }>()
    materials.forEach((m, idx) => {
      const ref = String(m.material_ref_id || '').trim()
      const kind = String(m.material_kind || '').trim()
      const calc = String(m.calculation_method || '').trim()
      if (!ref) return
      const key = `${kind}:${ref}:${calc}`
      const entry = dupMap.get(key) ?? { key, indices: [] }
      entry.indices.push(idx + 1)
      dupMap.set(key, entry)
    })
    const dups = Array.from(dupMap.values()).filter((x) => x.indices.length > 1)
    if (dups.length) {
      Modal.warning({
        title: '物料组存在重复项，请先合并',
        content: (
          <Space direction="vertical">
            <Text>检测到同一物料在相同“计量”口径下重复出现，请在保存前合并为一行（数量/损耗/备注）。</Text>
            <Text type="secondary">
              重复行号：{dups.map((x) => x.indices.join('、')).join('；')}
            </Text>
          </Space>
        ),
      })
      return
    }
    if (drawerMode === 'create') {
      const payload = buildPayload().create
      if (!payload.module_code) {
        message.error('请输入模块编码')
        return
      }
      createMutation.mutate(payload)
    } else if (selectedId) {
      const payload = buildPayload().update
      updateMutation.mutate({ id: selectedId, payload })
    }
  }

  const handleCopy = async () => {
    if (!selectedId || !detailQuery.data) return
    const source = detailQuery.data
    let newCode = fallbackModuleCode()
    try {
      newCode = (await generateNextCode({ prefix: 'MOD', width: 4 })).code
    } catch {
      // keep fallback
    }
    const payload: ProcessModuleCopyPayload = {
      module_code: newCode,
      module_name: `${source.module_name} Copy`,
      status: 'draft',
      operator_id: DEFAULT_OPERATOR,
    }
    copyMutation.mutate({ id: selectedId, payload })
  }

  const openMaterialChooser = (targetIndex?: number) => {
    const currentKind =
      targetIndex !== undefined
        ? ((editorForm.getFieldValue(['materials', targetIndex, 'material_kind']) as MaterialReferenceKind) ??
          'real')
        : 'real'
    const initialTab: MaterialPickerTab = currentKind === 'virtual' ? 'virtual' : 'real'
    setMaterialPickerContext({ targetIndex, initialTab })
  }

  const materialsColumns: ColumnsType<{ index: number; record: EditorMaterialValue }> = [
    {
      title: '序号',
      dataIndex: 'index',
      width: 70,
      render: (value) => value + 1,
    },
    {
      title: '物料',
      dataIndex: 'material_code',
      width: 260,
      render: (_: unknown, row, index) => {
        const kind =
          (row.record.material_kind as any) ||
          (editorForm.getFieldValue(['materials', index, 'material_kind']) as any) ||
          'real'
        const color = MATERIAL_KIND_COLOR[String(kind)] || '#1677ff'
        const code = String(row.record.material_code || '')
        const name = String(row.record.material_name || '')
        return (
          <Space direction="vertical" size={4} style={{ width: '100%' }}>
            <Space size={8} align="center">
              {renderCodePill(code || '-', { color, solid: true })}
              <Text ellipsis={{ tooltip: name || '-' }} style={{ maxWidth: 220 }}>
                {name || '-'}
              </Text>
              <Button size="small" type="link" icon={<LinkOutlined />} onClick={() => openMaterialChooser(index)} />
            </Space>
            {/* keep values in form for submit */}
            <Form.Item name={['materials', index, 'material_kind']} hidden>
              <Input />
            </Form.Item>
            <Form.Item name={['materials', index, 'material_ref_id']} hidden>
              <Input />
            </Form.Item>
            <Form.Item name={['materials', index, 'material_code']} hidden>
              <Input />
            </Form.Item>
            <Form.Item name={['materials', index, 'material_name']} hidden>
              <Input />
            </Form.Item>
            <Form.Item name={['materials', index, 'unit_of_measure']} hidden>
              <Input />
            </Form.Item>
          </Space>
        )
      },
    },
    {
      title: '数量 / 损耗',
      dataIndex: 'quantity',
      width: 200,
      render: (_: unknown, _record, index) => (
        <Space align="start">
          <Form.Item
            name={['materials', index, 'quantity']}
            style={{ marginBottom: 0 }}
            rules={[{ required: true, message: '请输入数量' }]}
          >
            <InputNumber min={0} precision={2} placeholder="数量" />
          </Form.Item>
          <Form.Item
            name={['materials', index, 'loss_rate']}
            style={{ marginBottom: 0 }}
            rules={[
              { required: true, message: '请输入损耗' },
              {
                validator: (_rule, value) =>
                  value === undefined || (value >= 0 && value <= 100)
                    ? Promise.resolve()
                    : Promise.reject(new Error('0-100')),
              },
            ]}
          >
            <InputNumber min={0} max={100} precision={2} placeholder="损耗%" />
          </Form.Item>
        </Space>
      ),
    },
    {
      title: '计量',
      dataIndex: 'calculation_method',
      width: 80,
      render: (_: unknown, _record, index) => (
        <Form.Item noStyle shouldUpdate>
          {(form) => {
            const unitOfMeasure = form.getFieldValue(['materials', index, 'unit_of_measure'])
            const meta = (form.getFieldValue(['materials', index, 'metadata_json']) ?? {}) as any
            const bomUnit = normalizeUnit(meta?.bom_unit ?? unitOfMeasure) || meta?.bom_unit || unitOfMeasure
            const allowed = new Set(allowedCalcMethodsByUnit(bomUnit))
            // ⚠️ 性能/稳定性：不要在 render 内 setFieldValue（会引发渲染/微任务循环，严重时导致 Chrome RESULT_CODE_HUNG）
            // 口径：仅在保存时做规范化；UI 允许显示 legacy 值并提示用户手动调整。

            const options = CALCULATION_METHOD_OPTIONS.filter((opt) => allowed.has(opt.value as any))
            return (
              <Form.Item
                name={['materials', index, 'calculation_method']}
                style={{ marginBottom: 0 }}
                rules={[{ required: true, message: '必填' }]}
              >
                <Select options={options} placeholder="计量方式" optionLabelProp="label" />
              </Form.Item>
            )
          }}
        </Form.Item>
      ),
    },
    {
      title: 'BOM单价/单位',
      key: 'bom_price',
      width: 150,
      render: (_: unknown, row, index) => {
        const meta = ((row.record.metadata_json ?? {}) as any) || {}
        const price = parseNum(meta.bom_unit_price)
        const unit = normalizeUnit(meta.bom_unit || row.record.unit_of_measure) || ''
        return (
          <Space>
            <Text>{price === undefined ? '-' : `${price.toFixed(2)}/${unit || '-'}`}</Text>
            <Form.Item name={['materials', index, 'metadata_json']} hidden>
              <Input />
            </Form.Item>
          </Space>
        )
      },
    },
    {
      title: '备注',
      dataIndex: 'selection_notes',
      width: 260,
      render: (_: unknown, _record, index) => (
        <Form.Item name={['materials', index, 'selection_notes']} style={{ marginBottom: 0 }}>
          <Input.TextArea rows={1} placeholder="备注" />
        </Form.Item>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 180,
      render: (_: unknown, row) => (
        <Space>
          <Button
            size="small"
            icon={<ArrowUpOutlined />}
            onClick={() => handleMoveMaterial(row.index, 'up')}
          />
          <Button
            size="small"
            icon={<ArrowDownOutlined />}
            onClick={() => handleMoveMaterial(row.index, 'down')}
          />
          <Button
            size="small"
            icon={<CopyOutlined />}
            onClick={() => handleDuplicateMaterial(row.index)}
          />
          <Button
            danger
            size="small"
            icon={<DeleteOutlined />}
            onClick={() => handleRemoveMaterial(row.index)}
          />
        </Space>
      ),
    },
  ]

  const stepsColumns: ColumnsType<{ index: number; record: EditorStepValue }> = [
    {
      title: '序号',
      dataIndex: 'index',
      width: 70,
      render: (value) => value + 1,
    },
    {
      title: '工序',
      key: 'process',
      width: 260,
      render: (_: unknown, row, index) => {
        const processSnapshot = (row.record.metadata_json as any)?.process_snapshot as any
        const snapshot = row.record.process ?? (processSnapshot as ProcessReference | undefined)
        const canEdit = drawerMode === 'create' || drawerMode === 'edit'
        const code = snapshot?.process_code ?? '-'
        const name = snapshot?.process_name ?? '-'
        // NOTE: 后端返回的 step.process 可能不带 description；以 process_snapshot.description 兜底
        const desc = String((snapshot as any)?.description ?? processSnapshot?.description ?? '').trim()
        return (
          <Space direction="vertical" size={4} style={{ width: '100%' }}>
            <Space size={8}>
              {renderCodePill(code, { solid: false })}
              <Space size={6}>
                <Text ellipsis={{ tooltip: name }} style={{ maxWidth: 200 }}>
                  {name}
                </Text>
                {desc ? (
                  <Tooltip title={desc}>
                    <ExclamationCircleOutlined style={{ color: 'rgba(0,0,0,0.45)' }} />
                  </Tooltip>
                ) : null}
              </Space>
              {canEdit ? (
                <Button
                  size="small"
                  type="link"
                  icon={<LinkOutlined />}
                  onClick={() => setProcessSelectContext({ targetIndex: index })}
                />
              ) : null}
            </Space>
            <Form.Item name={['steps', index, 'process_id']} hidden>
              <Input />
            </Form.Item>
          </Space>
        )
      },
    },
    {
      title: '班组',
      key: 'team_name',
      width: 120,
      render: (_: unknown, _row, index) => (
        <Form.Item name={['steps', index, 'team_name']} style={{ marginBottom: 0 }} rules={[{ required: true, message: '必填' }]}>
          <Select
            allowClear
            showSearch
            placeholder="选择班组"
            options={(teamQuery.data?.items ?? []).map((it: any) => ({ label: it.name, value: it.name }))}
            optionFilterProp="label"
            onChange={(v) => {
              // 同步到本地 stepsLocal（用于行标题等）
              setStepsLocal((prev) => {
                const base = (prev.length ? prev : (editorForm.getFieldValue('steps') as EditorStepValue[]) ?? []).slice()
                if (base[index]) base[index] = { ...base[index], team_name: v ?? '' }
                return base
              })

              // 自动带出该班组的默认分钟单价（仅在当前步骤未填写时）
              const rate = v ? teamRateByName.get(String(v)) : undefined
              if (rate === undefined) return
              const cur = Number(editorForm.getFieldValue(['steps', index, 'metadata_json', 'rate_per_minute']))
              if (!Number.isFinite(cur) || cur <= 0) {
                editorForm.setFieldValue(['steps', index, 'metadata_json', 'rate_per_minute'], rate)
              }
            }}
          />
        </Form.Item>
      ),
    },
    {
      title: '基础(分)',
      key: 'base_minutes',
      width: 80,
      render: (_: unknown, _row, index) => (
        <Form.Item
          name={['steps', index, 'metadata_json', 'base_minutes']}
          style={{ marginBottom: 0 }}
          rules={[{ required: true, message: '必填' }]}
        >
          <InputNumber min={0} precision={2} style={{ width: '100%' }} />
        </Form.Item>
      ),
    },
    {
      title: '计量(分)',
      key: 'unit_minutes',
      width: 90,
      render: (_: unknown, _row, index) => (
        <Form.Item
          name={['steps', index, 'metadata_json', 'unit_minutes']}
          style={{ marginBottom: 0 }}
          rules={[{ required: true, message: '必填' }]}
        >
          <InputNumber min={0} precision={2} style={{ width: '100%' }} />
        </Form.Item>
      ),
    },
    {
      title: '单位',
      key: 'measure_unit',
      width: 80,
      render: (_: unknown, _row, index) => (
        <Form.Item noStyle shouldUpdate>
          {(form) => {
            const mt = form.getFieldValue(['steps', index, 'metadata_json', 'measure_type']) as StepMeasureType | undefined
            const unit = deriveUnitByMeasureType(mt)
            return <Text>{unit}</Text>
          }}
        </Form.Item>
      ),
    },
    {
      title: '计价量类型',
      key: 'measure_type',
      width: 110,
      render: (_: unknown, _row, index) => (
        <Form.Item noStyle shouldUpdate>
          {(form) => {
            const current = String(form.getFieldValue(['steps', index, 'metadata_json', 'measure_type']) ?? '').trim()

            // legacy: keep 'length' only if already selected in existing data
            const allowLegacyLength = current === 'length'

            const options = STEP_MEASURE_TYPE_OPTIONS.filter((opt) => {
              if (opt.value === 'length') return allowLegacyLength
              return true
            })

            return (
              <Form.Item
                name={['steps', index, 'metadata_json', 'measure_type']}
                style={{ marginBottom: 0 }}
                rules={[{ required: true, message: '必填' }]}
              >
                <Select
                  options={options}
                  placeholder="计价量"
                  optionFilterProp="label"
                  onChange={(v) => {
                    const unit = deriveUnitByMeasureType(v as any)
                    form.setFieldValue(['steps', index, 'metadata_json', 'measure_unit'], unit)
                  }}
                />
              </Form.Item>
            )
          }}
        </Form.Item>
      ),
    },
    {
      title: '单价(元/分)',
      key: 'rate_per_minute',
      width: 100,
      render: (_: unknown, _row, index) => (
        <Form.Item
          name={['steps', index, 'metadata_json', 'rate_per_minute']}
          style={{ marginBottom: 0 }}
          rules={[{ required: true, message: '必填' }]}
        >
          <InputNumber min={0} precision={2} style={{ width: '100%' }} />
        </Form.Item>
      ),
    },
    {
      title: '备注',
      key: 'notes',
      width: 220,
      render: (_: unknown, _row, index) => (
        <Form.Item name={['steps', index, 'notes']} style={{ marginBottom: 0 }}>
          <Input placeholder="备注" />
        </Form.Item>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 200,
      render: (_: unknown, row) => (
        <Space>
          <Button size="small" icon={<ArrowUpOutlined />} onClick={() => handleMoveStep(row.index, 'up')} />
          <Button size="small" icon={<ArrowDownOutlined />} onClick={() => handleMoveStep(row.index, 'down')} />
          <Button size="small" icon={<CopyOutlined />} onClick={() => handleDuplicateStep(row.index)} />
          <Button danger size="small" icon={<DeleteOutlined />} onClick={() => handleRemoveStep(row.index)} />
        </Space>
      ),
    },
  ]

  const currentModule = detailQuery.data

  const drawerTitle =
    drawerMode === 'create'
      ? '新建工艺模块'
      : currentModule
        ? `工艺模块：${currentModule.module_name}`
        : '工艺模块'

  const isEditing = drawerMode === 'create' || drawerMode === 'edit'

  const handleRealMaterialConfirm = (records: Material[], kind: MaterialReferenceKind, targetIndex?: number) => {
    if (!records.length) {
      message.warning('请选择物料')
      return
    }
    updateMaterials((prev) => {
      if (targetIndex !== undefined) {
        const next = [...prev]
        const bomUnitPrice = deriveBomUnitPrice(records[0])
        const bomUnit = normalizeUnit(records[0].unit || records[0].purchase_unit) || ''
        const calcMethod = deriveCalcMethodByUnit(bomUnit, (records[0].calculation_method as any) ?? null)
        next[targetIndex] = {
          ...(next[targetIndex] ?? createEmptyMaterial()),
          material_kind: kind as MaterialReferenceKind,
          material_ref_id: records[0].id,
          material_code: records[0].material_code,
          material_name: records[0].material_name,
          unit_of_measure: bomUnit,
          // 替换物料：以新物料主数据为准（否则会出现“计量方式与单位不配套/不更新”的回归问题）
          calculation_method: calcMethod,
          quantity: safeNum((next[targetIndex] as any)?.quantity, 1) || 1,
          loss_rate: safeNum((next[targetIndex] as any)?.loss_rate, 0) || 0,
          material_category: records[0].category || undefined,
          metadata_json: {
            ...(((next[targetIndex] ?? {}) as any).metadata_json ?? {}),
            bom_unit_price: bomUnitPrice,
            bom_unit: bomUnit,
            currency: records[0].currency,
          },
        }
        return next
      }
      const additions = records.map((record) => ({
        ...createEmptyMaterial(),
        material_kind: kind as MaterialReferenceKind,
        material_ref_id: record.id,
        material_code: record.material_code,
        material_name: record.material_name,
        unit_of_measure: normalizeUnit(record.unit || record.purchase_unit) || '',
        calculation_method: deriveCalcMethodByUnit(
          normalizeUnit(record.unit || record.purchase_unit) || '',
          (record.calculation_method as any) ?? null,
        ),
        material_category: record.category || undefined,
        metadata_json: {
          bom_unit_price: deriveBomUnitPrice(record),
          bom_unit: normalizeUnit(record.unit || record.purchase_unit) || '',
          currency: record.currency,
        },
      }))
      return [...prev, ...additions]
    })
  }

  const handleVirtualMaterialConfirm = (records: VirtualMaterial[], targetIndex?: number) => {
    if (!records.length) {
      message.warning('请选择虚拟物料')
      return
    }
    ;(async () => {
      const hide = message.loading('正在读取虚拟物料详情...', 0)
      try {
        // list API might not include bom_unit_price; use detail API for accurate snapshot
        const details = await Promise.all(records.map((r) => fetchVirtualMaterial(r.id)))

        // Also: virtual material bom_unit_price may be NULL; compute from bindings + underlying real material bom_unit_price
        const materialIds = Array.from(
          new Set(
            details
              .flatMap((vm) => (vm.bindings ?? []).map((b: any) => String(b.material_id ?? '').trim()))
              .filter(Boolean),
          ),
        )
        const materialDetails = await Promise.all(materialIds.map((id) => fetchMaterial(id)))
        const materialMap = new Map(materialDetails.map((m) => [m.id, m]))

        updateMaterials((prev) => {
          const toRow = (vm: VirtualMaterial, baseRow?: any) => {
            const unitOfMeasure =
              vm.virtual_kind === 'recipe' || vm.virtual_kind === 'placeholder' ? vm.unit || '' : '套'

            const computeVirtualBomUnitPrice = (): number | undefined => {
              if (vm.virtual_kind === 'placeholder') return 0
              const bindings = (vm.bindings ?? []) as any[]
              if (!bindings.length) return undefined
              let total = 0
              let hitAny = false
              for (const b of bindings) {
                const mid = String(b.material_id ?? '').trim()
                if (!mid) continue
                const mat = materialMap.get(mid)
                if (!mat) continue
                const price = deriveBomUnitPrice(mat)
                if (price === undefined) continue

                let qty = Number(b.quantity_ratio ?? 0)
                if (!Number.isFinite(qty)) qty = 0
                if (vm.virtual_kind === 'recipe' && qty > 1.5) {
                  // safety: if old data stored 0-100, convert to fraction
                  qty = qty / 100
                }

                // backend loss_rate is 0-100 (%)
                const lossRatePct = Number(b.loss_rate ?? 0)
                const lossFactor = 1 + Math.max(0, lossRatePct) / 100
                total += price * Math.max(0, qty) * lossFactor
                hitAny = true
              }
              return hitAny ? total : undefined
            }
            const computedBomPrice = computeVirtualBomUnitPrice()

            return {
              ...(baseRow ?? createEmptyMaterial()),
              material_kind: 'virtual' as MaterialReferenceKind,
              material_ref_id: vm.id,
              material_code: vm.virtual_code,
              material_name: vm.name,
              unit_of_measure: normalizeUnit(unitOfMeasure) || unitOfMeasure,
              material_category: vm.category || undefined,
              metadata_json: {
                ...(((baseRow ?? {}) as any).metadata_json ?? {}),
                bom_unit_price: computedBomPrice,
                bom_unit: normalizeUnit(unitOfMeasure) || unitOfMeasure,
                currency: (vm as any).currency,
              },
            }
          }

          if (targetIndex !== undefined) {
            const next = [...prev]
            next[targetIndex] = toRow(details[0], next[targetIndex])
            return next
          }
          return [...prev, ...details.map((vm) => toRow(vm))]
        })
      } catch (err: any) {
        message.error(err?.response?.data?.detail ?? '读取虚拟物料详情失败')
      } finally {
        hide()
      }
    })()
  }

  const handleProcessConfirm = (process: ProcessReference) => {
    const ctx = processSelectContext
    setProcessSelectContext(null)
    ;(async () => {
      const hide = message.loading('正在读取工序详情并回填默认参数...', 0)
      try {
        const detail = await fetchProcess(process.id)
        const meta = ((detail as any).metadata_json ?? {}) as any
        const aiSpec = meta?.ai_spec && typeof meta.ai_spec === 'object' ? meta.ai_spec : undefined
        const costType: StepCostMode =
          meta.cost_type === 'time' || meta.cost_type === 'piece'
            ? meta.cost_type
            : safeNum(meta.rate_per_minute, NaN) > 0
              ? 'time'
              : 'piece'
        const measureUnit = normalizeUnit(meta.measure_unit ?? detail.unit_of_measure) || '个'
        const measureType = (() => {
          const preferred = String(meta.measure_type ?? '').trim()
          // legacy: keep old value if present and compatible, else derive from unit
          if (preferred === 'length') return 'length' as StepMeasureType
          return deriveCalcMethodByUnit(measureUnit, preferred) as StepMeasureType
        })()
        const baseMinutes = safeNum(meta.base_minutes, 0)
        const unitMinutes = safeNum(meta.unit_minutes, 0)
        const ratePerMinute =
          costType === 'time' ? safeNum(meta.rate_per_minute, safeNum(detail.standard_rate, 0)) : safeNum(meta.rate_per_minute, 0)
        const pieceRate =
          costType === 'piece' ? safeNum(meta.piece_rate, safeNum(detail.standard_rate, 0)) : safeNum(meta.piece_rate, 0)

        updateSteps((prev) => {
          const targetIndex = ctx?.targetIndex
          if (targetIndex !== undefined) {
            const next = [...prev]
            const current = next[targetIndex] ?? (createEmptyStep(targetIndex + 1) as EditorStepValue)
            next[targetIndex] = {
              ...current,
              process_id: process.id,
              process,
              team_name: current.team_name || detail.team_name || '',
              metadata_json: {
                ...(current.metadata_json ?? {}),
                cost_type: costType,
                base_minutes: baseMinutes,
                unit_minutes: unitMinutes,
                measure_unit: measureUnit,
                measure_type: (current.metadata_json as any)?.measure_type ?? measureType,
                rate_per_minute: costType === 'time' ? ratePerMinute : null,
                piece_rate: costType === 'piece' ? pieceRate : null,
                process_snapshot: {
                  ...process,
                  process_id: process.id,
                  description: detail.description,
                  ai_spec: aiSpec,
                },
              },
            }
            message.success(`已选择工序：${process.process_code}（更新第 ${targetIndex + 1} 行）`)
            return next
          }
          message.success(`已选择工序：${process.process_code}（新增一行）`)
          const empty = createEmptyStep(prev.length + 1) as EditorStepValue
          return [
            ...prev,
            {
              ...empty,
              process_id: process.id,
              process,
              team_name: detail.team_name || '',
              metadata_json: {
                ...(empty.metadata_json ?? {}),
                cost_type: costType,
                base_minutes: baseMinutes,
                unit_minutes: unitMinutes,
                measure_unit: measureUnit,
                measure_type: measureType,
                rate_per_minute: costType === 'time' ? ratePerMinute : null,
                piece_rate: costType === 'piece' ? pieceRate : null,
                process_snapshot: {
                  ...process,
                  process_id: process.id,
                  description: detail.description,
                  ai_spec: aiSpec,
                },
              },
            },
          ]
        })
      } catch (err: any) {
        message.error(err?.response?.data?.detail ?? '读取工序详情失败')
      } finally {
        hide()
      }
    })()
  }

  return (
    <Space direction="vertical" size={24} style={{ width: '100%' }}>
      <div>
        <Title level={3} style={{ marginBottom: 0 }}>
          工艺模块
        </Title>
        <Text type="secondary">维护可复用的物料+工序组合，可在产品模型中直接引用。</Text>
      </div>

      <Card
        title="筛选"
        bordered={false}
        extra={
          <Space>
            <Button icon={<ReloadOutlined />} onClick={() => listQuery.refetch()}>
              刷新
            </Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreateDrawer}>
              新建工艺模块
            </Button>
          </Space>
        }
      >
        <Form form={filtersForm} layout="inline" onFinish={handleFilterSubmit}>
          <Form.Item name="search" label="关键词">
            <Input.Search
              placeholder="编码 / 名称"
              allowClear
              onSearch={handleFilterSubmit}
              style={{ width: 240 }}
            />
          </Form.Item>
          <Form.Item name="category" label="分类">
            <Select
              allowClear
              placeholder="全部"
              showSearch
              optionFilterProp="label"
              style={{ width: 200 }}
              options={(moduleCategoryQuery.data?.items ?? []).map((it: any) => ({
                label: it.name,
                value: it.name,
              }))}
            />
          </Form.Item>
          <Form.Item name="status" label="状态">
            <Select
              allowClear
              placeholder="全部"
              options={STATUS_OPTIONS}
              style={{ width: 160 }}
            />
          </Form.Item>
          <Form.Item name="structure_code" label="结构标准code">
            <Input
              allowClear
              placeholder='例如 pillowcase_v1 或 pillowcase_v1:zipper'
              style={{ width: 240 }}
            />
          </Form.Item>
          <Form.Item name="structure_tag" label="结构标签">
            <Input
              allowClear
              placeholder="例如 pillowcase_v1:zipper"
              style={{ width: 220 }}
            />
          </Form.Item>
          <Form.Item>
            <Space>
              <Button type="primary" htmlType="submit">
                查询
              </Button>
              <Button onClick={handleFilterReset}>重置</Button>
            </Space>
          </Form.Item>
        </Form>
      </Card>

      <Card>
        <Table<ProcessModuleSummary>
          rowKey="id"
          loading={listQuery.isLoading}
          columns={moduleListColumns}
          dataSource={listQuery.data?.items ?? []}
          pagination={{
            current: pagination.current,
            pageSize: pagination.pageSize,
            total: listQuery.data?.total ?? 0,
            showSizeChanger: true,
            onChange: (current, pageSize) => setPagination({ current, pageSize }),
          }}
          scroll={{ x: 1200 }}
        />
      </Card>

      <Drawer
        title={drawerTitle}
        width={1400}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        destroyOnClose
        extra={
          currentModule && drawerMode === 'view' ? (
            <Space>
              <Button onClick={() => setDrawerMode('edit')} icon={<EditOutlined />}>
                编辑
              </Button>
              <Button onClick={handleCopy} icon={<CopyOutlined />}>
                复制
              </Button>
              <Button onClick={() => setReferenceDrawerOpen(true)} icon={<LinkOutlined />}>
                引用
              </Button>
              {currentModule.status === 'active' ? (
                <Button
                  danger
                  onClick={() => selectedId && deactivateMutation.mutate(selectedId)}
                >
                  停用
                </Button>
              ) : (
                <Button type="primary" onClick={() => selectedId && activateMutation.mutate(selectedId)}>
                  启用
                </Button>
              )}
            </Space>
          ) : null
        }
        footer={
          isEditing ? (
            <Space style={{ float: 'right' }}>
              <Button icon={<QuestionCircleOutlined />} onClick={() => setGuideOpen(true)}>
                新建指南
              </Button>
              <Button onClick={() => setDrawerMode(selectedId ? 'view' : 'create')}>取消</Button>
              <Button
                type="primary"
                loading={createMutation.isPending || updateMutation.isPending}
                onClick={handleSave}
              >
                {drawerMode === 'create' ? '创建' : '保存'}
              </Button>
            </Space>
          ) : null
        }
      >
        <Tabs
          items={[
            {
              key: 'edit',
              label: '编辑',
              children: (
                <Form
                  layout="vertical"
                  form={editorForm}
                  disabled={!isEditing}
                  onValuesChange={() => {
                    if (suppressTouchRef.current) return
                    userTouchedRef.current = true
                    // keep table row records in sync for display-only cells (e.g. snapshot title)
                    setMaterialsLocal((editorForm.getFieldValue('materials') as EditorMaterialValue[]) ?? [])
                    setStepsLocal((editorForm.getFieldValue('steps') as EditorStepValue[]) ?? [])
                  }}
                >
                  <Card title="基础信息" size="small" bordered={false}>
            <Row gutter={16}>
              <Col span={12}>
                <Form.Item
                  label="模块编码"
                  name="module_code"
                  rules={[{ required: true, message: '创建时自动生成' }]}
                >
                  <Input placeholder="创建时自动生成" disabled />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item
                  label="模块名称"
                  name="module_name"
                  rules={[{ required: true, message: '请输入模块名称' }]}
                >
                  <Input placeholder="例如：UV 喷绘-灯片" />
                </Form.Item>
              </Col>
            </Row>
            <Row gutter={16}>
              <Col span={12}>
                <Form.Item label="类别" name="category">
                  <Select
                    allowClear
                    placeholder="请选择"
                    showSearch
                    options={(moduleCategoryQuery.data?.items ?? []).map((it: any) => ({
                      label: it.name,
                      value: it.name,
                    }))}
                  />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item label="状态" name="status" rules={[{ required: true }]}>
                  <Select options={STATUS_OPTIONS} />
                </Form.Item>
              </Col>
            </Row>
            <Row gutter={16}>
              <Col span={12}>
                <Form.Item label="标签" name="tags">
                  <Select mode="tags" placeholder="用于筛选/分组" />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item label="描述" name="description">
                  <Input.TextArea
                    rows={2}
                    placeholder="可同步宜搭表单备注"
                  />
                </Form.Item>
                <div style={{ marginTop: -8, marginBottom: 8 }}>
                  <Button
                    size="small"
                    loading={generatingDescription}
                    // Form has disabled={!isEditing}; explicitly override to allow using AI in view mode.
                    disabled={false}
                    onClick={async () => {
                      const values = editorForm.getFieldsValue()
                      const materials = (materialsLocal.length ? materialsLocal : (values.materials ?? [])) as any[]
                      const steps = (stepsLocal.length ? stepsLocal : (values.steps ?? [])) as any[]

                      const payload = {
                        module_name: String(values.module_name ?? '').trim(),
                        category: values.category ?? undefined,
                        structure: {
                          mode: String(values.structure_applicability_mode ?? 'slot_internal'),
                          standard_code: String(values.structure_standard_code ?? '').trim() || null,
                          slots: normalizeStringArray(values.structure_slots ?? []),
                        },
                        materials: materials
                          .filter((m) => m?.material_ref_id)
                          .map((m) => ({
                            material_kind: m.material_kind,
                            material_code: m.material_code,
                            material_name: m.material_name,
                            unit_of_measure: m.unit_of_measure,
                            calculation_method: m.calculation_method,
                          })),
                        steps: steps
                          .filter((s) => s?.process_id)
                          .map((s) => {
                            const meta = (s.metadata_json ?? {}) as any
                            const snap = (meta.process_snapshot ?? {}) as any
                            return {
                              process_code: snap.process_code,
                              process_name: snap.process_name,
                              process_description: truncateText(snap.description, 800),
                              process_ai_spec: pickProcessAiSpec(snap.ai_spec),
                              team_name: s.team_name,
                              measure_type: meta.measure_type,
                              notes: truncateText(s.notes, 300),
                            }
                          }),
                      }

                      setGeneratingDescription(true)
                      try {
                        const res = await generateProcessModuleDescription(payload as any)
                        const longText = String(res.description ?? '').trim()
                        const shortText = buildShortDescription(longText, 90)

                        // 1) 基础信息的“描述”保持短，便于列表/快速浏览
                        editorForm.setFieldValue('description', shortText || longText)

                        // 2) 长文写入模块 ai_spec，直接保存（避免再手工复制到 AI 抽屉）
                        if (selectedId && detailQuery.data) {
                          const baseMeta = ((detailQuery.data.metadata_json ?? {}) as any) || {}
                          const baseAi = (baseMeta.ai_spec && typeof baseMeta.ai_spec === 'object') ? baseMeta.ai_spec : {}
                          const nextMeta = {
                            ...baseMeta,
                            ai_spec: {
                              ...baseAi,
                              narrative_short: shortText || undefined,
                              narrative_long: longText || undefined,
                              narrative_provider: res.provider,
                              narrative_generated_at: new Date().toISOString(),
                            },
                          }
                          await updateProcessModule(selectedId, {
                            description: shortText || undefined,
                            metadata_json: nextMeta,
                          } as any)
                          queryClient.invalidateQueries({ queryKey: ['process-modules'] })
                          detailQuery.refetch()
                        }

                        message.success(res.provider === 'llm' ? 'AI生成完成（已写入AI语义长文）' : '生成完成（模板，已写入AI语义长文）')
                      } catch (e: any) {
                        // fallback: generate a short template locally (avoid blocking when AI service is unavailable)
                        const moduleName = String(values.module_name ?? '').trim() || '工艺模块'
                        const stepsText = ((payload as any)?.steps ?? [])
                          .map((s: any) => String(s?.process_name ?? s?.process_code ?? '').trim())
                          .filter(Boolean)
                        const matsText = ((payload as any)?.materials ?? [])
                          .map((m: any) => String(m?.material_name ?? m?.material_code ?? '').trim())
                          .filter(Boolean)
                        const mode = String(values.structure_applicability_mode ?? 'slot_internal')
                        const code = String(values.structure_standard_code ?? '').trim()
                        const slots = normalizeStringArray(values.structure_slots ?? [])
                        const scope =
                          mode === 'global' ? '通用（GLOBAL）' : code ? `${code}${slots.length ? ` / ${slots.join('、')}` : ''}（${mode}）` : ''
                        const local = [
                          `${moduleName}${values.category ? `（${values.category}）` : ''}`,
                          scope ? `适用范围：${scope}` : '',
                          stepsText.length ? `工序：${stepsText.join(' → ')}` : '',
                          matsText.length ? `物料：${matsText.slice(0, 8).join('、')}` : '',
                          '本描述不包含任何默认数值，仅描述流程/口径。',
                        ]
                          .filter(Boolean)
                          .join('\n')
                        editorForm.setFieldValue('description', buildShortDescription(local, 90) || local)
                        message.warning(e?.response?.data?.detail ?? 'AI生成失败，已用本地模板生成简述（可手工再润色）')
                      } finally {
                        setGeneratingDescription(false)
                      }
                    }}
                  >
                    AI生成
                  </Button>
                  <Text type="secondary" style={{ marginLeft: 8, fontSize: 12 }}>
                    将当前物料组+工序组汇总生成模块描述（通常 5-20 秒）
                  </Text>
                </div>
              </Col>
            </Row>
            <Row gutter={16}>
              <Col span={12}>
                <Card title="结构适用范围" size="small" bordered style={{ marginBottom: 0 }}>
                  <Row gutter={12}>
                    <Col span={12}>
                      <Form.Item label="适用类型" name="structure_applicability_mode">
                        <Radio.Group
                          optionType="button"
                          buttonStyle="solid"
                          options={[
                            { label: '内用（slot）', value: 'slot_internal' },
                            { label: '组合/装配', value: 'assembly' },
                            { label: 'global', value: 'global' },
                          ]}
                          onChange={(e) => {
                            const next = String(e?.target?.value ?? '')
                            if (next === 'global') {
                              // global: hide structure standard; clear related fields to avoid accidental selection
                              suppressTouchRef.current = true
                              try {
                                editorForm.setFieldValue('structure_standard_code', undefined)
                                editorForm.setFieldValue('structure_slots', [])
                              } finally {
                                suppressTouchRef.current = false
                              }
                            }
                          }}
                        />
                      </Form.Item>
                    </Col>
                    {String(structureModeValue ?? 'slot_internal') === 'global' ? null : (
                      <Col span={12}>
                        <Form.Item label="结构标准" name="structure_standard_code">
                          <Select
                            allowClear
                            showSearch
                            optionFilterProp="label"
                            placeholder="选择结构标准（来自结构标准字典）"
                            loading={structureStandardsQuery.isLoading}
                            options={(structureStandardsQuery.data?.items ?? []).map((it) => ({
                              value: it.code,
                              label: `${it.code}${it.name && it.name !== it.code ? ` / ${it.name}` : ''}${it.status === 'inactive' ? '（停用）' : ''}`,
                              disabled: it.status === 'inactive',
                            }))}
                            onChange={() => {
                              // 换结构标准后：slots 清空，避免错配
                              suppressTouchRef.current = true
                              try {
                                editorForm.setFieldValue('structure_slots', [])
                              } finally {
                                suppressTouchRef.current = false
                              }
                            }}
                          />
                        </Form.Item>
                      </Col>
                    )}
                  </Row>
                  {String(structureModeValue ?? 'slot_internal') === 'global' ? null : String(structureModeValue ?? 'slot_internal') === 'assembly' ? (
                    <Form.Item
                      label="slots（至少2个）"
                      name="structure_slots"
                      help={!selectedStructureStandard ? '请先选择结构标准' : undefined}
                      validateStatus={!selectedStructureStandard ? 'warning' : undefined}
                    >
                      <Select
                        mode="multiple"
                        allowClear
                        disabled={!selectedStructureStandard}
                        placeholder={selectedStructureStandard ? '选择 slots（来自结构标准 slots[]）' : '请先选择结构标准'}
                        options={(selectedStructureStandard?.slots ?? []).map((s) => {
                          const cn = selectedStructureStandard?.slot_display_names?.[s]
                          return { value: s, label: cn ? `${cn}（${s}）` : s }
                        })}
                        value={structureSlotsValue ?? []}
                        onChange={(vals) => {
                          suppressTouchRef.current = true
                          try {
                            editorForm.setFieldValue('structure_slots', normalizeStringArray(vals))
                          } finally {
                            suppressTouchRef.current = false
                          }
                        }}
                      />
                    </Form.Item>
                  ) : (
                    <Form.Item
                      label="slot（1个）"
                      name="structure_slots"
                      help={!selectedStructureStandard ? '请先选择结构标准' : undefined}
                      validateStatus={!selectedStructureStandard ? 'warning' : undefined}
                    >
                      <Select
                        allowClear
                        disabled={!selectedStructureStandard}
                        placeholder={selectedStructureStandard ? '选择 slot（来自结构标准 slots[]）' : '请先选择结构标准'}
                        options={(selectedStructureStandard?.slots ?? []).map((s) => {
                          const cn = selectedStructureStandard?.slot_display_names?.[s]
                          return { value: s, label: cn ? `${cn}（${s}）` : s }
                        })}
                        value={String((structureSlotsValue ?? [])[0] ?? '') || undefined}
                        onChange={(v) => {
                          suppressTouchRef.current = true
                          try {
                            editorForm.setFieldValue('structure_slots', v ? [String(v)] : [])
                          } finally {
                            suppressTouchRef.current = false
                          }
                        }}
                      />
                    </Form.Item>
                  )}
                  <Form.Item label="结构标签预览">
                    {computedStructureTags.length ? (
                      <Space size={6} wrap>
                        {computedStructureTags.map((t) => (
                          <Tag
                            key={t}
                            style={{
                              marginInlineEnd: 0,
                              borderRadius: 999,
                              padding: '0 6px',
                              fontSize: 12,
                              lineHeight: '18px',
                            }}
                          >
                            {t}
                          </Tag>
                        ))}
                      </Space>
                    ) : (
                      <Text type="secondary">（将写入 metadata_json.structure_tags[]，当前为空）</Text>
                    )}
                  </Form.Item>
                  {/* auto-maintained hidden field */}
                  <Form.Item name="structure_tags" hidden>
                    <Input />
                  </Form.Item>
                </Card>
              </Col>
              <Col span={12}>
                <Text type="secondary" style={{ fontSize: 12, lineHeight: '22px' }}>
                  说明：系统会根据“适用类型 + slot(s)”自动生成并维护 <Text code>metadata_json.structure_tags</Text>（MVP）。global 会写入固定标签 <Text code>GLOBAL</Text>。
                  <br />
                  规则（建议）：不依赖结构部位且跨品类通用的工艺 → 选 <Text code>global</Text>；只作用在单个部位/位置（拉链位/包边位/装饰位等） → 选 <Text code>slot_internal</Text> 并选 1 个 slot；需要把 ≥2 个部位拼接/装配在一起 → 选 <Text code>assembly</Text> 并选多个 slots。
                </Text>
                {selectedStructureSlotHints.length ? (
                  <div style={{ marginTop: 10 }}>
                    <Alert
                      type="info"
                      showIcon
                      message="当前 slot 提示（来自结构标准的配置）"
                      description={
                        <Space direction="vertical" size={6} style={{ width: '100%' }}>
                          {selectedStructureSlotHints.map((it) => (
                            <div key={it.slot}>
                              <Tag style={{ marginInlineEnd: 0 }}>{it.label}</Tag>
                              <div style={{ marginTop: 4 }}>
                                <Text type="secondary">
                                  驱动量：{it.driver_quantity ? <Text code>{it.driver_quantity}</Text> : '-'}
                                  {it.remark ? (
                                    <>
                                      <span style={{ margin: '0 6px' }}>；</span>
                                      备注：{it.remark}
                                    </>
                                  ) : null}
                                </Text>
                              </div>
                            </div>
                          ))}
                        </Space>
                      }
                    />
                  </div>
                ) : null}
              </Col>
            </Row>
          </Card>

          <Card
            title="物料组"
            size="small"
            bordered={false}
            extra={
              isEditing && (
                <Space>
                  <Button onClick={handleAddBlankMaterial}>添加空行</Button>
                  <Button type="primary" icon={<LinkOutlined />} onClick={() => openMaterialChooser(undefined)}>
                    选择物料
                  </Button>
                </Space>
              )
            }
            style={{ marginTop: 16 }}
          >
            {materialsDataSource.length ? (
              <Table
                dataSource={materialsDataSource}
                columns={materialsColumns}
                pagination={false}
                size="small"
                tableLayout="fixed"
              />
            ) : (
              <Empty description="尚未添加物料" />
            )}
          </Card>

          <Card
            title="工序组"
            size="small"
            bordered={false}
            style={{ marginTop: 16 }}
            extra={
              isEditing && (
                <Space>
                  <Button onClick={handleAddBlankStep}>添加空行</Button>
                  <Button type="primary" icon={<LinkOutlined />} onClick={() => setProcessSelectContext({})}>
                    选择工序
                  </Button>
                </Space>
              )
            }
          >
            {stepsDataSource.length ? (
              <Table
                dataSource={stepsDataSource}
                columns={stepsColumns}
                pagination={false}
                size="small"
                tableLayout="fixed"
              />
            ) : (
              <Empty description="尚未添加工序" />
            )}
          </Card>
                </Form>
              ),
            },
            {
              key: 'preview',
              label: '预览计算',
              children: (
                <Space direction="vertical" style={{ width: '100%' }} size={12}>
                  <Alert
                    type="info"
                    showIcon
                    message="预览计算（订单维度）"
                    description="输入宽/高/数量（可选长度），系统会按每步的 measure_type 计算计价量，并按 计时/计件 公式实时汇总成本。"
                  />

                  <Card size="small" title="订单输入">
                    <Space wrap>
                      <Form.Item label="宽(mm)" style={{ marginBottom: 0 }}>
                        <InputNumber
                          min={0}
                          value={previewInput.width_mm}
                          onChange={(v) => setPreviewInput((p) => ({ ...p, width_mm: safeNum(v, 0) }))}
                        />
                      </Form.Item>
                      <Form.Item label="高(mm)" style={{ marginBottom: 0 }}>
                        <InputNumber
                          min={0}
                          value={previewInput.height_mm}
                          onChange={(v) => setPreviewInput((p) => ({ ...p, height_mm: safeNum(v, 0) }))}
                        />
                      </Form.Item>
                      <Form.Item label="长度(m)" style={{ marginBottom: 0 }}>
                        <InputNumber
                          min={0}
                          value={previewInput.length_m}
                          onChange={(v) => setPreviewInput((p) => ({ ...p, length_m: safeNum(v, 0) }))}
                        />
                      </Form.Item>
                      <Form.Item label="数量(个)" style={{ marginBottom: 0 }}>
                        <InputNumber
                          min={0}
                          value={previewInput.count}
                          onChange={(v) => setPreviewInput((p) => ({ ...p, count: safeNum(v, 0) }))}
                        />
                      </Form.Item>
                    </Space>
                  </Card>

                  <Card
                    size="small"
                    title="成本预览"
                    extra={<Text strong>合计：{safeNum(previewResult.total, 0).toFixed(4)}</Text>}
                  >
                    <Table
                      size="small"
                      pagination={false}
                      dataSource={previewResult.rows}
                      columns={[
                        { title: '步骤', dataIndex: 'name', width: 260, ellipsis: true },
                        {
                          title: '模式',
                          dataIndex: 'cost_mode',
                          width: 80,
                          render: (v: StepCostMode) => (v === 'time' ? '计时' : '计件'),
                        },
                        {
                          title: '计价量类型',
                          dataIndex: 'measure_type',
                          width: 110,
                          render: (v: StepMeasureType) =>
                            STEP_MEASURE_TYPE_OPTIONS.find((x) => x.value === v)?.label ?? v,
                        },
                        {
                          title: '计价量',
                          dataIndex: 'measure_qty',
                          width: 120,
                          render: (v: number, r: any) => {
                            const unit = STEP_MEASURE_TYPE_OPTIONS.find((x) => x.value === r.measure_type)?.unitHint ?? ''
                            return `${safeNum(v, 0).toFixed(4)} ${unit}`
                          },
                        },
                        {
                          title: '成本',
                          dataIndex: 'cost',
                          width: 120,
                          render: (v: number, r: any) =>
                            r.warnings?.length ? (
                              <Space direction="vertical" size={0}>
                                <Text type="danger">{safeNum(v, 0).toFixed(4)}</Text>
                                <Text type="secondary">{r.warnings.join('，')}</Text>
                              </Space>
                            ) : (
                              safeNum(v, 0).toFixed(4)
                            ),
                        },
                      ]}
                    />
                  </Card>
                </Space>
              ),
            },
          ]}
        />
      </Drawer>

      <ProcessModuleAIDrawer
        open={aiDrawerOpen}
        moduleId={aiModuleId}
        onClose={() => {
          setAiDrawerOpen(false)
          setAiModuleId(null)
        }}
        onSaved={() => {
          listQuery.refetch()
          if (selectedId) detailQuery.refetch()
        }}
      />

      <GuideDrawer
        open={guideOpen}
        onClose={() => setGuideOpen(false)}
        title="新建工艺模块指南"
        content={processModulesGuide}
        tip="提示：这是“工艺模块”面板的新建/维护指南（Markdown）。需要调整内容，直接修改对应文档并重新部署即可。"
      />

      <ReferenceDrawer
        open={referenceDrawerOpen}
        onClose={() => setReferenceDrawerOpen(false)}
        data={referencesQuery.data}
        loading={referencesQuery.isLoading}
      />

      <ProcessSelectModal
        open={!!processSelectContext}
        onClose={() => setProcessSelectContext(null)}
        onConfirm={handleProcessConfirm}
      />

      <MaterialPickerDrawer
        open={!!materialPickerContext}
        onClose={() => setMaterialPickerContext(null)}
        title="选择物料"
        initialTab={materialPickerContext?.initialTab ?? 'real'}
        defaultOnlyBom
        onConfirm={(result: MaterialPickerResult) => {
          const targetIndex = materialPickerContext?.targetIndex
          setMaterialPickerContext(null)
          if (result.kind === 'virtual') {
            handleVirtualMaterialConfirm(result.materials, targetIndex)
            return
          }
          handleRealMaterialConfirm(result.materials, result.kind as any, targetIndex)
        }}
      />
    </Space>
  )
}

interface ProcessSelectModalProps {
  open: boolean
  onClose: () => void
  onConfirm: (process: ProcessReference) => void
}

const ProcessSelectModal = ({ open, onClose, onConfirm }: ProcessSelectModalProps) => {
  const [search, setSearch] = useState('')
  const [chargingMode, setChargingMode] = useState<string | undefined>(undefined)
  const [category, setCategory] = useState<string | undefined>(undefined)
  const [selectedRowKeys, setSelectedRowKeys] = useState<Key[]>([])
  const [selectedRows, setSelectedRows] = useState<ProcessReference[]>([])

  const taxonomyCategoriesQuery = useQuery({
    queryKey: ['taxonomy-items', 'process_category', 'process-picker'],
    queryFn: () => fetchTaxonomyItems('process_category', { include_inactive: false }),
    enabled: open,
  })

  useEffect(() => {
    if (!open) {
      setSearch('')
      setChargingMode(undefined)
      setCategory(undefined)
      setSelectedRowKeys([])
      setSelectedRows([])
    }
  }, [open])

  const query = useQuery<ProcessReference[]>({
    queryKey: ['process-picker', search, chargingMode, category],
    queryFn: () =>
      fetchProcessReferences({
        search: search || undefined,
        charging_mode: chargingMode || undefined,
        category: category || undefined,
        status: 'active',
        limit: 200,
      } as any),
    enabled: open,
  })

  const handleConfirm = () => {
    if (!selectedRows.length) {
      message.warning('请选择一个工序')
      return
    }
    onConfirm(selectedRows[0])
    onClose()
  }

  return (
    <Drawer
      title="选择工序（全局工序库）"
      open={open}
      onClose={onClose}
      width={860}
      destroyOnClose
      extra={
        <Space>
          <Button onClick={onClose}>取消</Button>
          <Button type="primary" onClick={handleConfirm}>
            选择
          </Button>
        </Space>
      }
    >
      <Space direction="vertical" style={{ width: '100%' }}>
        <Space align="start">
          <Input.Search
            placeholder="搜索编码/名称"
            allowClear
            style={{ width: 260 }}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
            <Select
              allowClear
              placeholder="分类"
              style={{ width: 220 }}
              value={category}
              onChange={(value) => setCategory(value)}
              options={(taxonomyCategoriesQuery.data?.items ?? []).map((it: any) => ({
                label: it.name,
                value: it.name,
              }))}
            />
          <Select
            allowClear
            placeholder="计价方式"
            style={{ width: 200 }}
            value={chargingMode}
            onChange={(value) => setChargingMode(value)}
            options={PRICING_METHOD_OPTIONS}
          />
        </Space>

        <Table<ProcessReference>
          rowKey="id"
          loading={query.isLoading}
          dataSource={query.data ?? []}
          pagination={{ pageSize: 10 }}
          rowSelection={{
            type: 'radio',
            selectedRowKeys,
            onChange: (_keys, rows) => {
              setSelectedRowKeys(_keys)
              setSelectedRows(rows)
            },
          }}
          columns={[
            {
              title: '编码',
              dataIndex: 'process_code',
              width: 160,
              render: (code: string) => <Text code>{code}</Text>,
            },
            {
              title: '名称',
              dataIndex: 'process_name',
              width: 220,
              ellipsis: true,
            },
            {
              title: '计价方式',
              dataIndex: 'charging_mode',
              width: 120,
              render: (value: string) => value || '-',
            },
            {
              title: '标准单价',
              dataIndex: 'standard_rate',
              width: 140,
              render: (value: string | number | null, record) => {
                if (value === null || value === undefined) return '-'
                return `${value} / ${normalizeUnit(record.unit_of_measure) || '-'}`
              },
            },
          ]}
        />
      </Space>
    </Drawer>
  )
}

interface ReferenceDrawerProps {
  open: boolean
  onClose: () => void
  data?: Awaited<ReturnType<typeof fetchProcessModuleReferences>>
  loading: boolean
}

const ReferenceDrawer = ({ open, onClose, data, loading }: ReferenceDrawerProps) => {
  const references = data?.items ?? []
  return (
    <Drawer title="引用详情" open={open} onClose={onClose} width={720} destroyOnClose>
      {loading ? (
        <Empty description="加载中..." />
      ) : references.length ? (
        <Space direction="vertical" style={{ width: '100%' }}>
          {references.map((item) => (
            <Card
              key={item.id}
              size="small"
              title={`${item.module_code} · ${item.module_name}`}
              extra={
                <Tag color={item.status === 'active' ? 'green' : 'gold'}>
                  {item.status === 'active' ? '启用' : '草稿'}
                </Tag>
              }
            >
              <Text type="secondary">
                物料 {item.materials.length} 条 · 工序 {item.steps.length} 条
              </Text>
            </Card>
          ))}
        </Space>
      ) : (
        <Empty description="暂无引用信息" />
      )}
    </Drawer>
  )
}

export default ProcessModulesPage