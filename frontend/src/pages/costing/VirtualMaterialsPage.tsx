const BOM_UNIT_LABEL_MAP: Record<string, string> = {
  平米: '平米',
  '㎡': '平米',
  平方: '平米',
  平方米: '平米',
  'm²': '平米',
  M2: '平米',
  m2: '平米',
  米: '米',
  m: '米',
  M: '米',
  个: '个',
  套: '套',
}

const normalizeBomUnit = (value?: string | null): string | undefined => {
  if (!value) return undefined
  const v = String(value).trim()
  if (['平米', '㎡', '平方', '平方米', 'm²', 'M2', 'm2'].includes(v)) return '平米'
  if (['米', 'm', 'M'].includes(v)) return '米'
  if (v === '个') return '个'
  if (v === '套') return '套'
  return v
}

const getBomUnitLabel = (value?: string | null): string | undefined => {
  const normalized = normalizeBomUnit(value)
  if (!normalized) return undefined
  return BOM_UNIT_LABEL_MAP[normalized] ?? normalized
}

const parseDecimal = (value?: string | number | null): number | undefined => {
  if (value === undefined || value === null) return undefined
  const num = Number(value)
  return Number.isFinite(num) ? num : undefined
}

const getBomUnitPriceFromMetadata = (record: Material): number | undefined => {
  const value = (record.metadata_json as Record<string, unknown> | undefined)?.['bom_unit_price']
  if (typeof value === 'number') return value
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value)
    return Number.isNaN(parsed) ? undefined : parsed
  }
  return undefined
}

const deriveBomUnitPrice = (record: Material): number | undefined => {
  const metadataPrice = getBomUnitPriceFromMetadata(record)
  if (metadataPrice !== undefined) {
    return metadataPrice
  }
  if (record.unit_price === undefined || record.unit_price === null) {
    return undefined
  }
  const conversion = parseDecimal(record.conversion_purchase_to_bom)
  if (!conversion || conversion <= 0) {
    return undefined
  }
  return Number(record.unit_price) / conversion
}

const buildSizedImageUrl = (url?: string, size = 160): string | undefined => {
  if (!url) return undefined
  if (url.includes('size=')) {
    return url
  }
  const separator = url.includes('?') ? '&' : '?'
  return `${url}${separator}size=${size}`
}

const getPrimaryImage = (record: Material, size = 160): string | undefined => {
  if (Array.isArray(record.images) && record.images.length > 0) {
    return buildSizedImageUrl(record.images[0], size)
  }
  return undefined
}

const formatCurrency = (value?: number, currency?: string) => {
  if (value === undefined || value === null) {
    return '-'
  }
  try {
    return new Intl.NumberFormat('zh-CN', {
      style: 'currency',
      currency: currency || 'CNY',
      minimumFractionDigits: 2,
    }).format(Number(value))
  } catch {
    return `${value}`
  }
}

const distributeRatiosEvenly = (list: BindingFormValue[]) => {
  // recipe V1: bindings are always ratios; distribute across all rows
  const len = list.length
  if (!len) {
    return list
  }
  let remaining = 1
  const shares = list.map((_item, idx) => {
    const share =
      idx === len - 1 ? Number(remaining.toFixed(4)) : Number((1 / len).toFixed(4))
    remaining -= share
    return { index: idx, share }
  })
  return list.map((item, index) => {
    const target = shares.find((entry) => entry.index === index)
    if (!target) {
      return item
    }
    return { ...item, quantity_ratio: target.share }
  })
}

const getErrorMessage = (error: unknown) => {
  if (isAxiosError(error)) {
    const detail = error.response?.data?.detail
    if (typeof detail === 'string') {
      return detail
    }
    if (Array.isArray(detail)) {
      return detail
        .map((item) => (typeof item?.msg === 'string' ? item.msg : JSON.stringify(item)))
        .join('; ')
    }
  }
  return (error as Error)?.message || '操作失败'
}
import {
  Alert,
  Button,
  Card,
  Col,
  Descriptions,
  Drawer,
  Empty,
  Form,
  Image,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Radio,
  Row,
  Select,
  Space,
  Spin,
  Switch,
  Table,
  Tag,
  Tooltip,
  Typography,
  message,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  DeleteOutlined,
  LinkOutlined,
  PlusOutlined,
  QuestionCircleOutlined,
  ReloadOutlined,
  SettingOutlined,
  CheckCircleOutlined,
  StopOutlined,
  EyeOutlined,
  EditOutlined,
} from '@ant-design/icons'
import { useEffect, useMemo, useRef, useState } from 'react'
import type { Key } from 'react'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { isAxiosError } from 'axios'
import { useLocation, useNavigate } from 'react-router-dom'

import GuideDrawer from '@/components/common/GuideDrawer'
import type {
  CalculationMethod,
  Material,
  VirtualMaterial,
  VirtualMaterialBinding,
  VirtualMaterialInventoryResponse,
  VirtualMaterialUpdatePayload,
} from '@/types/planner'
import virtualMaterialsGuide from '@doc/costing/manuals/guides/virtual_materials_guide.md?raw'
import {
  calculateVirtualMaterialInventory,
  createVirtualMaterial,
  deactivateVirtualMaterial,
  generateNextCode,
  fetchMaterial,
  fetchMaterials,
  fetchTaxonomyItems,
  fetchVirtualMaterial,
  fetchVirtualMaterials,
  saveVirtualMaterialBindings,
  updateVirtualMaterial,
} from '@/services/planner'
import { CALCULATION_METHOD_OPTIONS, getCalculationMethodLabel } from '@/constants/calculationMethods'
import { formatBeijingTime } from '@/utils/beijingTime'
import MaterialDrawer from '@/components/costing/MaterialDrawer'

const { Title, Text } = Typography

type BindingMode = 'ratio' | 'quantity'
type VirtualKind = 'recipe' | 'kit' | 'placeholder'
const DEFAULT_VIRTUAL_UNIT = '套'
const DEFAULT_VIRTUAL_CATEGORY = '未分类'

const PLACEHOLDER_UNIT_OPTIONS = [
  { label: '平米', value: '平米' },
  { label: '米', value: '米' },
  { label: '个', value: '个' },
]

const VM_UNIT_OPTIONS = [
  { label: '平米', value: '平米' },
  { label: '米', value: '米' },
  { label: '个', value: '个' },
  { label: '套', value: '套' },
]

const fallbackRandomCode = (prefix: string, width: number) => {
  const digits = String(Math.floor(Math.random() * 10 ** width)).padStart(width, '0')
  return `${prefix}${digits}`
}

type BindingFormValue = {
  material_id?: string
  material_code?: string
  material_name?: string
  image_url?: string
  unit?: string | null
  currency?: string
  purchase_unit_price?: number
  purchase_unit?: string | null
  bom_unit_price?: number
  bom_unit?: string | null
  quantity_ratio?: number
  loss_rate?: number
  binding_type?: BindingMode
  status?: string | null
  is_active?: boolean
}

const getVirtualKindLabel = (value?: string) =>
  value === 'recipe' ? '配方型' : value === 'placeholder' ? '占位型' : '套件型'

const inferVirtualKind = (record: Partial<VirtualMaterial>): VirtualKind => {
  const metaKind = (record.metadata_json as any)?.virtual_kind
  const direct = record.virtual_kind ?? metaKind
  if (direct === 'recipe' || direct === 'kit' || direct === 'placeholder') return direct

  // Placeholder compatibility: if backend doesn't expose/retain virtual_kind yet,
  // infer from placeholder metadata (prefer this over unit-based inference).
  const meta = (record.metadata_json ?? {}) as Record<string, unknown>
  const placeholderSymbol = String((meta as any).placeholder_symbol || '').trim()
  if (placeholderSymbol) return 'placeholder'

  // Backward compatibility for deployed backends that don't expose/retain virtual_kind yet:
  // - kit: unit fixed "套"
  // - recipe: unit is derived from children and usually not "套"
  if (record.unit && record.unit !== DEFAULT_VIRTUAL_UNIT) return 'recipe'

  const bindings = (record.bindings ?? []) as Array<{ binding_type?: 'ratio' | 'quantity' }>
  if (bindings.some((b) => b.binding_type === 'quantity')) return 'kit'
  if (bindings.some((b) => b.binding_type === 'ratio')) return 'recipe'
  return 'kit'
}

const normalizePlaceholderSymbol = (name: string) => {
  const trimmed = String(name || '').trim()
  if (!trimmed) return ''
  if (trimmed.startsWith('#{') && trimmed.endsWith('}')) return trimmed
  return `#{${trimmed}}`
}

const stripPlaceholderSymbol = (value: string) => {
  const trimmed = String(value || '').trim()
  if (trimmed.startsWith('#{') && trimmed.endsWith('}')) {
    return trimmed.slice(2, -1).trim()
  }
  return trimmed
}

const statusOptions = [
  { label: '草稿', value: 'draft' },
  { label: '启用', value: 'active' },
  { label: '停用', value: 'inactive' },
]

const VirtualMaterialsPage = () => {
  const queryClient = useQueryClient()
  const location = useLocation() as any
  const navigate = useNavigate()
  const [filtersForm] = Form.useForm()
  const [basicForm] = Form.useForm()
  const [bindingForm] = Form.useForm()
  const [inventoryForm] = Form.useForm()

  const [filters, setFilters] = useState<{
    search?: string
    status?: string
    category?: string
    virtual_kind?: string
    binding_search?: string
  }>({})
  const [pagination, setPagination] = useState({ current: 1, pageSize: 10 })
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [drawerMode, setDrawerMode] = useState<'create' | 'view'>('view')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [materialPickerOpen, setMaterialPickerOpen] = useState(false)
  const [syncingBindingData, setSyncingBindingData] = useState(false)
  const [guideOpen, setGuideOpen] = useState(false)
  const [inventoryResult, setInventoryResult] = useState<VirtualMaterialInventoryResponse | null>(
    null,
  )
  const [manualRatioEdited, setManualRatioEdited] = useState(false)
  const [showBindingsInList, setShowBindingsInList] = useState(true)
  const bindingUpdateRef = useRef(false)
  const materialCacheRef = useRef<Record<string, Material>>({})

  // 支持从其它页面（例如“关联引用”区块）跳转并直接打开当前虚拟物料抽屉
  useEffect(() => {
    const st = (location as any)?.state ?? {}
    const openId = String(st?.openVirtualMaterialId ?? '').trim()
    if (!openId) return
    setDrawerMode('view')
    setSelectedId(openId)
    setDrawerOpen(true)
    // 清掉 state，避免刷新/返回时重复弹抽屉
    navigate(location.pathname, { replace: true, state: null })
  }, [location, navigate])

  const taxonomyVirtualCategoryQuery = useQuery({
    queryKey: ['taxonomy-items', 'virtual_material_category'],
    queryFn: () => fetchTaxonomyItems('virtual_material_category', { include_inactive: false }),
  })

  const listQuery = useQuery({
    queryKey: ['virtual-materials', filters, pagination],
    queryFn: () =>
      fetchVirtualMaterials({
        ...filters,
        page: pagination.current,
        page_size: pagination.pageSize,
      }),
    placeholderData: keepPreviousData,
  })

  const detailQuery = useQuery({
    queryKey: ['virtual-material', selectedId],
    queryFn: () => fetchVirtualMaterial(selectedId as string),
    enabled: drawerOpen && !!selectedId,
  })

  useEffect(() => {
    if (!drawerOpen) {
      setSelectedId(null)
      setInventoryResult(null)
      basicForm.resetFields()
      bindingForm.resetFields()
      inventoryForm.resetFields()
      setDrawerMode('view')
      setManualRatioEdited(false)
      materialCacheRef.current = {}
      return
    }
    if (drawerMode === 'create') {
      basicForm.setFieldsValue({
        virtual_code: '',
        name: '',
        status: 'draft',
        category: DEFAULT_VIRTUAL_CATEGORY,
        virtual_kind: 'kit',
        unit: DEFAULT_VIRTUAL_UNIT,
      })
      bindingForm.setFieldsValue({ bindings: [] })
      inventoryForm.setFieldsValue({ quantity: 1 })
    }
  }, [drawerOpen, drawerMode, basicForm, bindingForm, inventoryForm])

  useEffect(() => {
    if (!detailQuery.data) {
      return
    }
    const vm = detailQuery.data
    const kind = inferVirtualKind(vm)
    const meta = (vm.metadata_json ?? {}) as Record<string, unknown>
    const metaPlaceholderName = String((meta as any).placeholder_name || '').trim()
    const displayName =
      kind === 'placeholder'
        ? stripPlaceholderSymbol(metaPlaceholderName || vm.name)
        : vm.name
    bindingUpdateRef.current = true
    basicForm.setFieldsValue({
      virtual_code: vm.virtual_code,
      name: displayName,
      description: vm.description,
      category: vm.category || DEFAULT_VIRTUAL_CATEGORY,
      status: vm.status,
      virtual_kind: kind,
      unit: kind === 'kit' ? DEFAULT_VIRTUAL_UNIT : vm.unit || '',
      metadata_json: (vm.metadata_json ?? {}) as any,
    })
    bindingForm.setFieldsValue({
      bindings: vm.bindings.map((binding: VirtualMaterialBinding) => ({
        material_id: binding.material_id,
        material_code: binding.material_code,
        material_name: binding.material_name,
        image_url: buildSizedImageUrl(binding.image_url ?? undefined, 96),
        unit: binding.unit,
        quantity_ratio: Number(binding.quantity_ratio),
        loss_rate: Number(binding.loss_rate),
        currency: binding.currency,
        purchase_unit_price: binding.purchase_unit_price
          ? Number(binding.purchase_unit_price)
          : undefined,
        purchase_unit: binding.purchase_unit || binding.unit || null,
        bom_unit_price: binding.bom_unit_price ? Number(binding.bom_unit_price) : undefined,
        bom_unit: binding.bom_unit || binding.unit || null,
        binding_type: kind === 'recipe' ? 'ratio' : 'quantity',
        status: binding.status,
        is_active: binding.is_active,
      })),
    })
    bindingUpdateRef.current = false
    inventoryForm.setFieldsValue({ quantity: 1, calculation_method: undefined, usage_context: undefined })
    setInventoryResult(null)
    setManualRatioEdited(false)
  }, [detailQuery.data, basicForm, bindingForm, inventoryForm])

  const bindingsValue = Form.useWatch('bindings', bindingForm) as BindingFormValue[] | undefined
  const activeBindings = useMemo(() => bindingsValue ?? [], [bindingsValue])
  const virtualKind = (Form.useWatch('virtual_kind', basicForm) as VirtualKind | undefined) ?? 'kit'
  const placeholderUnit = String(Form.useWatch('unit', basicForm) || '').trim()
  const manualBomUnitPrice = Form.useWatch(['metadata_json', 'bom_unit_price'], basicForm)
  const selectedUnit = String(Form.useWatch('unit', basicForm) || '').trim()
  const selectedVirtualCode = String(Form.useWatch('virtual_code', basicForm) || '').trim()
  const selectedVirtualName = String(Form.useWatch('name', basicForm) || '').trim()

  const [bomOverrideModalOpen, setBomOverrideModalOpen] = useState(false)
  const [bomOverrideDraftPrice, setBomOverrideDraftPrice] = useState<number | null>(null)
  const [bomOverrideDraftUnit, setBomOverrideDraftUnit] = useState<string | null>(null)

  const isZeroCostFallback = useMemo(() => {
    const name = selectedVirtualName
    const code = selectedVirtualCode
    return name.startsWith('兜底-零成本-') || code === 'VM00052' || code === 'VM00053' || code === 'VM00054'
  }, [selectedVirtualCode, selectedVirtualName])

  const bindingSummary = useMemo(() => {
    if (!activeBindings.length) {
      return {
        totalRatio: 0,
        allUnits: true,
        baseUnit: undefined as string | undefined,
        unitLabel: undefined as string | undefined,
        totalPrice: undefined as number | undefined,
        currency: undefined as string | undefined,
        hasPrice: false,
        hasQuantityMode: false,
      }
    }
    let baseUnit: string | undefined
    let unitLabel: string | undefined
    let allUnits = true
    let totalRatio = 0
    let totalPrice = 0
    let currency: string | undefined
    let hasPrice = true
    let hasQuantityMode = false
    let hasRatioMode = false

    activeBindings.forEach((binding) => {
      const ratio = Number(binding.quantity_ratio) || 0
      const loss = Number(binding.loss_rate) || 0
      if (virtualKind === 'recipe') {
        hasRatioMode = true
        totalRatio += ratio
      } else {
        hasQuantityMode = true
      }
      if (virtualKind === 'recipe') {
        // recipe: enforce unit consistency (use BOM unit normalization only for label friendliness)
        const normalized = normalizeBomUnit(binding.bom_unit || binding.unit || undefined)
        if (!baseUnit && normalized) {
          baseUnit = normalized
          unitLabel = getBomUnitLabel(normalized)
        }
        if (normalized && baseUnit && normalized !== baseUnit) {
          allUnits = false
        }
      }
      const price = Number(binding.bom_unit_price)
      if (!Number.isFinite(price)) {
        hasPrice = false
      } else {
        const effectiveQuantity = ratio
        const required = effectiveQuantity * (1 + loss / 100)
        totalPrice += price * required
      }
      if (!currency && binding.currency) {
        currency = binding.currency
      }
    })

    return {
      totalRatio,
      allUnits,
      baseUnit,
      unitLabel,
      totalPrice: hasPrice ? totalPrice : undefined,
      currency,
      hasPrice,
      hasQuantityMode,
      hasRatioMode,
    }
  }, [activeBindings, virtualKind])

  useEffect(() => {
    if (!drawerOpen || !activeBindings.length) {
      return
    }
    const ac = new AbortController()
    let cancelled = false

    ;(async () => {
      for (const binding of activeBindings) {
        if (cancelled) return
        if (!binding.material_id || (binding.purchase_unit_price && binding.bom_unit_price)) {
          continue
        }
        if (materialCacheRef.current[binding.material_id]) {
          continue
        }
        try {
          const response = await fetchMaterials(
            {
              search: binding.material_code,
              page: 1,
              page_size: 5,
            },
            { signal: ac.signal },
          )
          if (cancelled) return
          const match = response.items.find(
            (item) => item.id === binding.material_id || item.material_code === binding.material_code,
          )
          if (match) {
            materialCacheRef.current[binding.material_id] = match
            bindingUpdateRef.current = true
            const current = (bindingForm.getFieldValue('bindings') as BindingFormValue[]) ?? []
            bindingForm.setFieldsValue({
              bindings: current.map((item) =>
                item.material_id === binding.material_id
                  ? {
                      ...item,
                      currency: match.currency,
                      purchase_unit_price: match.unit_price ? Number(match.unit_price) : undefined,
                      purchase_unit: match.purchase_unit || match.unit || item.unit || null,
                      bom_unit_price: deriveBomUnitPrice(match),
                      bom_unit: match.unit || item.unit || null,
                      image_url: item.image_url || getPrimaryImage(match),
                    }
                  : item,
              ),
            })
            bindingUpdateRef.current = false
          }
        } catch (error) {
          // close/cancel should not be treated as an error
          if ((error as any)?.name === 'CanceledError') return
          console.error('Failed to fetch material info', error)
        }
      }
    })()

    return () => {
      cancelled = true
      ac.abort()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [drawerOpen, activeBindings.length])

  const ratioIsValid = useMemo(() => {
    if (virtualKind !== 'recipe') {
      return true
    }
    if (!activeBindings.length) return true
    return Math.abs(bindingSummary.totalRatio - 1) <= 0.001
  }, [activeBindings.length, bindingSummary.totalRatio, virtualKind])

  const virtualBomPriceLabel = useMemo(() => {
    if (virtualKind === 'placeholder') {
      const unit = placeholderUnit || '-'
      return `${formatCurrency(0, bindingSummary.currency || 'CNY')} / ${unit}`
    }
    if (manualBomUnitPrice !== undefined && manualBomUnitPrice !== null && String(manualBomUnitPrice) !== '') {
      const currency = bindingSummary.currency || 'CNY'
      const unitLabel =
        virtualKind === 'kit'
          ? DEFAULT_VIRTUAL_UNIT
          : bindingSummary.unitLabel || bindingSummary.baseUnit || selectedUnit || '件'
      return `${formatCurrency(Number(manualBomUnitPrice), currency)} / ${unitLabel}`
    }
    if (virtualKind === 'recipe' && !bindingSummary.allUnits) {
      return '配方型要求子物料单位一致，请先统一单位后再参考虚拟单价'
    }
    if (bindingSummary.totalPrice === undefined) {
      return '- / -（需所有真实物料维护 BOM 单价）'
    }
    const currency = bindingSummary.currency || 'CNY'
    const unitLabel =
      virtualKind === 'kit'
        ? DEFAULT_VIRTUAL_UNIT
        : bindingSummary.unitLabel || bindingSummary.baseUnit || selectedUnit || '件'
    return `${formatCurrency(bindingSummary.totalPrice, currency)} / ${unitLabel}`
  }, [bindingSummary, manualBomUnitPrice, placeholderUnit, selectedUnit, virtualKind])

  const virtualBomPriceMeta = useMemo(() => {
    if (virtualKind === 'placeholder') {
      return { source: 'fixed' as const, tag: '占位固定0' }
    }
    if (isZeroCostFallback) {
      return { source: 'fixed' as const, tag: '兜底固定0' }
    }
    if (manualBomUnitPrice !== undefined && manualBomUnitPrice !== null && String(manualBomUnitPrice) !== '') {
      return { source: 'manual' as const, tag: '手动覆盖' }
    }
    if (bindingSummary.totalPrice !== undefined) {
      return { source: 'derived' as const, tag: '自动推导' }
    }
    return { source: 'unknown' as const, tag: '未推导' }
  }, [bindingSummary.totalPrice, isZeroCostFallback, manualBomUnitPrice, virtualKind])
  const totalRatioPercent = useMemo(() => {
    if (virtualKind !== 'recipe') {
      return null
    }
    if (!activeBindings.length) return null
    return Number((bindingSummary.totalRatio * 100).toFixed(2))
  }, [activeBindings.length, bindingSummary.totalRatio, virtualKind])

  const handleFilterSubmit = () => {
    const values = filtersForm.getFieldsValue()
    setFilters({
      search: values.search?.trim() || undefined,
      status: values.status || undefined,
      category: values.category || undefined,
      virtual_kind: values.virtual_kind || undefined,
      binding_search: values.binding_search?.trim() || undefined,
    })
    setPagination((prev) => ({ ...prev, current: 1 }))
  }

  const handleFilterReset = () => {
    filtersForm.resetFields()
    setFilters({})
    setPagination({ current: 1, pageSize: 10 })
  }

  const handleTableChange = (pager: { current?: number; pageSize?: number }) => {
    setPagination({
      current: pager.current ?? 1,
      pageSize: pager.pageSize ?? 10,
    })
  }

  const openCreateDrawer = () => {
    setDrawerMode('create')
    setDrawerOpen(true)
  }

  const openDetailDrawer = (virtualMaterial: VirtualMaterial) => {
    setDrawerMode('view')
    setSelectedId(virtualMaterial.id)
    setDrawerOpen(true)
  }

  const [materialDrawerOpen, setMaterialDrawerOpen] = useState(false)
  const [currentMaterialId, setCurrentMaterialId] = useState<string | null>(null)

  useEffect(() => {
    if (!materialDrawerOpen) {
      setCurrentMaterialId(null)
    }
  }, [materialDrawerOpen])

  const openMaterialDrawerById = (materialId: string) => {
    setCurrentMaterialId(materialId)
    setMaterialDrawerOpen(true)
  }

  const closeDrawer = () => {
    setDrawerOpen(false)
  }

  const listData = listQuery.data?.items ?? []
  const mergedCategoryOptions = useMemo(() => {
    const seen = new Set<string>()
    const options: Array<{ label: string; value: string }> = []
    const append = (raw?: string | null) => {
      const value = String(raw ?? '').trim()
      if (!value || seen.has(value)) return
      seen.add(value)
      options.push({ label: value, value })
    }
    append(DEFAULT_VIRTUAL_CATEGORY)
    ;(taxonomyVirtualCategoryQuery.data?.items ?? []).forEach((it: any) => append(it?.name))
    // 兜底：历史数据里可能存在 taxonomy 外的分类，允许展示但不强制
    listData.forEach((item) => append(item.category))
    append(detailQuery.data?.category ?? undefined)
    return options
  }, [detailQuery.data?.category, listData, taxonomyVirtualCategoryQuery.data?.items])
  const totalCount = listQuery.data?.total ?? 0

  const createMutation = useMutation({
    mutationFn: createVirtualMaterial,
    onSuccess: (data) => {
      message.success('虚拟物料已创建')
      queryClient.invalidateQueries({ queryKey: ['virtual-materials'] })
      setDrawerMode('view')
      setSelectedId(data.id)
    },
    onError: (error) => {
      message.error(getErrorMessage(error))
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: VirtualMaterialUpdatePayload }) =>
      updateVirtualMaterial(id, payload),
    onSuccess: () => {
      message.success('虚拟物料已更新')
      queryClient.invalidateQueries({ queryKey: ['virtual-materials'] })
      if (selectedId) {
        queryClient.invalidateQueries({ queryKey: ['virtual-material', selectedId] })
      }
    },
    onError: (error) => {
      message.error(getErrorMessage(error))
    },
  })

  // Guard: prevent duplicate submissions while async code generation / validation is running.
  const [savingBasic, setSavingBasic] = useState(false)

  const bindingsMutation = useMutation({
    mutationFn: ({
      id,
      bindings,
    }: {
      id: string
      bindings: BindingFormValue[]
    }) => {
      return (async () => {
        const nextKind = virtualKind
        const nextUnit =
          nextKind === 'kit'
            ? DEFAULT_VIRTUAL_UNIT
            : nextKind === 'placeholder'
              ? String(basicForm.getFieldValue('unit') || '').trim() || undefined
              : (bindingSummary.baseUnit ?? undefined)
        const nextMeta = ((basicForm.getFieldValue('metadata_json') as any) ?? {}) as Record<string, unknown>
        if (nextKind === 'placeholder') {
          const name = stripPlaceholderSymbol(String(basicForm.getFieldValue('name') || ''))
          if (name) {
            nextMeta.virtual_kind = 'placeholder'
            nextMeta.placeholder_name = name
            nextMeta.placeholder_symbol = normalizePlaceholderSymbol(name)
          }
        }
        // “保存绑定”同时落库类型/单位，避免类型切换后无法保存或不落库
        await updateVirtualMaterial(id, {
          virtual_kind: nextKind,
          unit: nextUnit,
          // placeholder 相关字段落在 metadata_json
          metadata_json: nextMeta,
        })
        return await saveVirtualMaterialBindings(id, {
          bindings:
            nextKind === 'placeholder'
              ? []
              : bindings.map((item) => ({
                  material_id: item.material_id as string,
                  quantity_ratio: Number(item.quantity_ratio) || 0,
                  loss_rate: Number(item.loss_rate) || 0,
                  binding_type: virtualKind === 'recipe' ? 'ratio' : 'quantity',
                })),
        })
      })()
    },
    onSuccess: () => {
      message.success('绑定关系已保存')
      if (selectedId) {
        queryClient.invalidateQueries({ queryKey: ['virtual-material', selectedId] })
      }
    },
    onError: (error) => {
      message.error(getErrorMessage(error) || '保存绑定关系失败')
    },
  })

  const deactivateMutation = useMutation({
    mutationFn: deactivateVirtualMaterial,
    onSuccess: () => {
      message.success('已删除（归档）')
      queryClient.invalidateQueries({ queryKey: ['virtual-materials'] })
      if (selectedId) {
        queryClient.invalidateQueries({ queryKey: ['virtual-material', selectedId] })
      }
    },
  })

  const statusMutation = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) =>
      updateVirtualMaterial(id, { status }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['virtual-materials'] })
      if (selectedId) {
        queryClient.invalidateQueries({ queryKey: ['virtual-material', selectedId] })
      }
    },
    onError: (error) => message.error(getErrorMessage(error)),
  })

  const inventoryMutation = useMutation({
    mutationFn: ({
      id,
      quantity,
      calculation_method,
      usage_context,
    }: {
      id: string
      quantity: number
      calculation_method?: CalculationMethod
      usage_context?: string
    }) =>
      calculateVirtualMaterialInventory(id, {
        quantity,
        calculation_method,
        usage_context,
      }),
    onSuccess: (data) => {
      setInventoryResult(data)
    },
  })

  const handleSaveBasic = async () => {
    if (savingBasic || createMutation.isPending || updateMutation.isPending) return
    setSavingBasic(true)
    try {
      const values = await basicForm.validateFields()
      const kind = (values.virtual_kind as VirtualKind) ?? 'kit'
      const meta = (values.metadata_json ?? {}) as Record<string, unknown>
      const constraintCategory = String(meta.constraint_category || '').trim()
      // 单位策略：
      // - kit：固定“套”
      // - recipe：自动从子物料单位推导（展示在 BOM 单价里）
      // - placeholder：必须显式选择 unit（后续模型替换映射依赖）
      const unitFromForm = String(values.unit ?? '').trim() || undefined
      const unit =
        kind === 'kit'
          ? DEFAULT_VIRTUAL_UNIT
          : kind === 'placeholder'
            ? String(values.unit || '').trim()
            : (bindingSummary.baseUnit || unitFromForm)
      if (kind === 'placeholder') {
        if (!unit) {
          message.error('占位型必须选择单位')
          return
        }
      }
      if (kind === 'recipe' && !bindingSummary.baseUnit) {
        if (!unit) {
          message.error('配方型在未绑定物料时，请先选择单位（用于兜底/对账）')
          return
        }
      }
      const nextMetadata: Record<string, unknown> = { ...(values.metadata_json ?? {}) }
      if (kind === 'placeholder') {
        const name = stripPlaceholderSymbol(String(values.name || ''))
        if (!name) {
          message.error('占位型必须填写名称')
          return
        }
        nextMetadata.virtual_kind = 'placeholder'
        nextMetadata.placeholder_name = name
        nextMetadata.placeholder_symbol = normalizePlaceholderSymbol(name)
        if (constraintCategory) {
          nextMetadata.constraint_category = constraintCategory
        } else {
          delete (nextMetadata as any).constraint_category
        }
      }
      if (drawerMode === 'create') {
        // VM 编码只在“实际创建/保存”时申请，避免打开抽屉就消耗递增号
        let nextCode = String(values.virtual_code || '').trim()
        if (!nextCode) {
          try {
            const res = await generateNextCode({ prefix: 'VM', width: 5 })
            nextCode = res.code
            basicForm.setFieldValue('virtual_code', nextCode)
          } catch {
            // fallback: keep it usable even if code service is temporarily unavailable
            nextCode = fallbackRandomCode('VM', 5)
            basicForm.setFieldValue('virtual_code', nextCode)
          }
        }
        await createMutation.mutateAsync({
          virtual_code: nextCode,
          name: kind === 'placeholder' ? normalizePlaceholderSymbol(String(values.name || '')) : values.name,
          virtual_kind: kind,
          description: values.description,
          category: values.category,
          unit,
          status: values.status,
          metadata_json: nextMetadata,
        })
        return
      }
      if (!selectedId) {
        return
      }
      await updateMutation.mutateAsync({
        id: selectedId,
        payload: {
          name: kind === 'placeholder' ? normalizePlaceholderSymbol(String(values.name || '')) : values.name,
          virtual_kind: kind,
          description: values.description,
          category: values.category,
          unit,
          status: values.status,
          metadata_json: nextMetadata,
        },
      })
    } finally {
      setSavingBasic(false)
    }
  }

  const handleSaveBindings = async () => {
    if (!selectedId) {
      message.warning('请先创建虚拟物料后再维护绑定关系')
      return
    }
    if (virtualKind === 'placeholder') {
      // placeholder: no bindings, allow saving empty; ensure kind/unit/metadata are persisted via updateVirtualMaterial
      const unit = String(basicForm.getFieldValue('unit') || '').trim()
      const meta = (basicForm.getFieldValue('metadata_json') ?? {}) as Record<string, unknown>
      const placeholderName = String(meta.placeholder_name || '').trim()
      const placeholderSymbol = String(meta.placeholder_symbol || '').trim()
      if (!placeholderName || !placeholderSymbol || !unit) {
        message.error('占位型需要填写：占位名称/占位符号/单位')
        return
      }
      bindingsMutation.mutate({ id: selectedId, bindings: [] })
      return
    }
    if (!activeBindings.length) {
      message.warning('请至少添加一个真实物料')
      return
    }
    const inactiveBindings = activeBindings.filter((binding) => binding.is_active === false)
    if (inactiveBindings.length) {
      message.error(
        `以下物料已停用，请先启用后再绑定：${inactiveBindings
          .map((binding) => binding.material_code || binding.material_name || binding.material_id)
          .join('、')}`,
      )
      return
    }
    if (virtualKind === 'recipe' && !ratioIsValid) {
      message.error('配比合计需为 100%')
      return
    }
    if (virtualKind === 'recipe') {
      if (!bindingSummary.baseUnit) {
        message.error('配方型需要子物料维护单位，才能自动推导“虚拟 BOM 单价”的单位。')
        return
      }
      if (!bindingSummary.allUnits) {
        message.error('配方型要求子物料单位一致：请先统一单位后再保存。')
        return
      }
    }
    await bindingForm.validateFields()
    bindingsMutation.mutate({ id: selectedId, bindings: activeBindings })
  }

  const handleSyncBindingData = async () => {
    if (!selectedId) {
      message.warning('请先选择一个虚拟物料')
      return
    }
    if (virtualKind === 'placeholder') {
      message.info('占位型不绑定子物料，无需同步')
      return
    }
    const current = (bindingForm.getFieldValue('bindings') as BindingFormValue[]) ?? []
    const ids = current.map((b) => String(b.material_id || '').trim()).filter(Boolean)
    if (!ids.length) {
      message.info('当前没有绑定真实物料')
      return
    }
    try {
      setSyncingBindingData(true)
      const results = await Promise.allSettled(ids.map((id) => fetchMaterial(id)))
      const byId = new Map<string, Material>()
      const failed: string[] = []
      const missingBomPrice: string[] = []
      const zeroBomPrice: string[] = []
      results.forEach((r, idx) => {
        const id = ids[idx]!
        if (r.status === 'fulfilled') {
          byId.set(id, r.value)
          materialCacheRef.current[id] = r.value
          const code = String(r.value.material_code || id).trim()
          const bomPrice = deriveBomUnitPrice(r.value)
          if (bomPrice === undefined) {
            missingBomPrice.push(code)
          } else if (Number(bomPrice) === 0) {
            zeroBomPrice.push(code)
          }
        } else {
          failed.push(id)
        }
      })
      if (!byId.size) {
        message.error('同步失败：未获取到任何物料数据')
        return
      }
      bindingUpdateRef.current = true
      bindingForm.setFieldsValue({
        bindings: current.map((item) => {
          const id = String(item.material_id || '').trim()
          const m = id ? byId.get(id) : undefined
          if (!m) return item
          return {
            ...item,
            currency: m.currency,
            purchase_unit_price: m.unit_price != null ? Number(m.unit_price) : undefined,
            purchase_unit: m.purchase_unit || m.unit || item.unit || null,
            bom_unit_price: deriveBomUnitPrice(m),
            bom_unit: m.unit || item.unit || null,
            unit: m.unit || item.unit || null,
            image_url: item.image_url || getPrimaryImage(m, 96),
          }
        }),
      })
      bindingUpdateRef.current = false
      const baseMsg = `已同步 ${byId.size} 条：BOM单价/单位已刷新（虚拟BOM单价会自动重算）`
      if (failed.length) {
        message.warning(`${baseMsg}；${failed.length} 条失败（可重试）`)
      } else {
        message.success(baseMsg)
      }
      // 重要提示：若物料主数据未维护单价/换算，BOM 单价可能为 undefined/0，虚拟单价会偏低或显示缺失。
      const uniq = (list: string[]) => Array.from(new Set(list)).slice(0, 12)
      const missing = uniq(missingBomPrice)
      const zeros = uniq(zeroBomPrice)
      if (missing.length) {
        message.warning(`以下物料缺少BOM单价（请检查物料主数据单价/换算）：${missing.join('、')}${missingBomPrice.length > missing.length ? '…' : ''}`)
      }
      if (zeros.length) {
        message.warning(`以下物料BOM单价=0（通常表示未维护或单价为0）：${zeros.join('、')}${zeroBomPrice.length > zeros.length ? '…' : ''}`)
      }
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setSyncingBindingData(false)
      bindingUpdateRef.current = false
    }
  }

  const handleInventoryCalculate = async () => {
    if (!selectedId) {
      message.warning('请先选择虚拟物料')
      return
    }
    const values = await inventoryForm.validateFields()
    const calcMethod = values.calculation_method as CalculationMethod | undefined
    const usageContext = values.usage_context?.trim()
    if (!calcMethod && !usageContext) {
      message.error('请至少选择计算方式或填写使用场景')
      return
    }
    inventoryMutation.mutate({
      id: selectedId,
      quantity: Number(values.quantity),
      calculation_method: calcMethod,
      usage_context: usageContext,
    })
  }

  const handleMaterialSelect = (materialsToAdd: Material[]) => {
    if (!materialsToAdd.length) {
      message.warning('请选择至少一个物料')
      return
    }
    const current = (bindingForm.getFieldValue('bindings') as BindingFormValue[]) ?? []
    const existingIds = new Set(current.map((item) => item.material_id))
    let next = [...current]
    const duplicates: string[] = []
    let unitMismatchDetected = false
    let recipeBaseUnit = virtualKind === 'recipe' ? (bindingSummary.baseUnit ?? undefined) : undefined
    materialsToAdd.forEach((material) => {
      if (existingIds.has(material.id)) {
        duplicates.push(material.material_code)
        return
      }
      if (virtualKind === 'recipe') {
        const materialUnitRaw = (material.unit || material.purchase_unit || '').trim()
        const materialUnit = normalizeBomUnit(materialUnitRaw) || materialUnitRaw
        if (!recipeBaseUnit && materialUnit) {
          recipeBaseUnit = materialUnit
        }
        if (recipeBaseUnit && materialUnit && materialUnit !== recipeBaseUnit) {
          unitMismatchDetected = true
          return
        }
      }
      next.push({
        material_id: material.id,
        material_code: material.material_code,
        material_name: material.material_name,
        image_url: getPrimaryImage(material, 96),
        unit: material.unit || material.purchase_unit || material.inventory_unit || '件',
        currency: material.currency,
        purchase_unit_price: material.unit_price ? Number(material.unit_price) : undefined,
        purchase_unit: material.purchase_unit || material.unit || null,
        bom_unit_price: deriveBomUnitPrice(material),
        bom_unit: material.unit || null,
        quantity_ratio: virtualKind === 'recipe' ? 1 : 1,
        loss_rate: 0,
        binding_type: virtualKind === 'recipe' ? 'ratio' : 'quantity',
        status: material.status,
        is_active: material.is_active,
      })
      existingIds.add(material.id)
    })
    if (virtualKind === 'recipe' && !manualRatioEdited && next.length > 0) {
      next = distributeRatiosEvenly(next)
    }
    bindingUpdateRef.current = true
    bindingForm.setFieldsValue({ bindings: next })
    bindingUpdateRef.current = false
    if (duplicates.length) {
      message.warning(`以下物料已存在：${duplicates.join('、')}`)
    } else {
      message.success('已添加所选物料')
    }
    if (unitMismatchDetected) {
      message.error('配方型要求子物料单位一致：已跳过单位不一致的物料。')
    }
  }

  const currentVirtualMaterial = detailQuery.data

  const listColumns = [
    {
      title: '类型',
      dataIndex: 'virtual_kind',
      key: 'virtual_kind',
      width: 140,
      render: (_value: unknown, record: VirtualMaterial) => getVirtualKindLabel(inferVirtualKind(record)),
    },
    {
      title: '虚拟编码',
      dataIndex: 'virtual_code',
      key: 'virtual_code',
      width: 160,
      render: (code: string) => <Text code>{code}</Text>,
    },
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
      render: (text: string, record: VirtualMaterial) => {
        const kind = inferVirtualKind(record)
        const meta = (record.metadata_json ?? {}) as Record<string, unknown>
        const placeholderSymbol = String((meta as any).placeholder_symbol || '').trim()
        if (kind === 'placeholder') {
          return <Text strong>{placeholderSymbol || normalizePlaceholderSymbol(text)}</Text>
        }
        return (
          <Space direction="vertical" size={0}>
            <Text strong>{text}</Text>
          </Space>
        )
      },
    },
    ...(showBindingsInList
      ? [
          {
            title: '绑定物料',
            key: 'bindings',
            width: 520,
            render: (_: unknown, record: VirtualMaterial) => {
              const kind = inferVirtualKind(record)
              const binds = Array.isArray(record.bindings) ? record.bindings : []
              if (!binds.length) return <Text type="secondary">-</Text>
              return (
                <div style={{ fontSize: 12, lineHeight: 1.35, maxHeight: 180, overflowY: 'auto' }}>
                  <div
                    style={{
                      display: 'flex',
                      gap: 8,
                      fontWeight: 600,
                      color: 'var(--app-text-muted)',
                      paddingBottom: 6,
                      borderBottom: '1px solid var(--app-border)',
                      marginBottom: 6,
                    }}
                  >
                    <div style={{ width: 90 }}>编码</div>
                    <div style={{ flex: 1 }}>名称</div>
                    <div style={{ width: 140, textAlign: 'right' }}>
                      {kind === 'recipe' ? '配比（%）' : '每套数量'}
                    </div>
                    <div style={{ width: 110, textAlign: 'right' }}>损耗率（%）</div>
                  </div>
                  {binds.map((b: any, idx: number) => {
                    const code = String(b.material_code || '').trim() || '-'
                    const name = String(b.material_name || '').trim() || '-'
                    const ratio = Number(b.quantity_ratio || 0)
                    const loss = Number(b.loss_rate || 0)
                    const ratioLabel =
                      kind === 'recipe' ? Number((ratio * 100).toFixed(2)) : Number(ratio.toFixed(4))
                    return (
                      <div
                        key={`${String(b.material_id || idx)}`}
                        style={{ display: 'flex', gap: 8, padding: '2px 0' }}
                      >
                        <div style={{ width: 90 }}>
                          <Text code>{code}</Text>
                        </div>
                        <div style={{ flex: 1 }}>
                          <Text ellipsis={{ tooltip: name }}>{name}</Text>
                        </div>
                        <div style={{ width: 140, textAlign: 'right' }}>
                          <Text>{Number.isFinite(ratioLabel) ? ratioLabel : '-'}</Text>
                        </div>
                        <div style={{ width: 110, textAlign: 'right' }}>
                          <Text>{Number.isFinite(loss) ? loss : '-'}</Text>
                        </div>
                      </div>
                    )
                  })}
                </div>
              )
            },
          } as any,
        ]
      : []),
    {
      title: '分类',
      dataIndex: 'category',
      key: 'category',
      width: 160,
      render: (value?: string) => value || '-',
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (value: string) => (
        <Tag color={value === 'active' ? 'green' : value === 'inactive' ? 'red' : 'gold'}>
          {value === 'active' ? '启用' : value === 'inactive' ? '停用' : '草稿'}
        </Tag>
      ),
    },
    {
      title: '更新时间',
      dataIndex: 'updated_at',
      key: 'updated_at',
      width: 200,
      render: (value: string) => formatBeijingTime(value, 'YYYY-MM-DD HH:mm'),
    },
    {
      title: '操作',
      key: 'actions',
      width: 180,
      render: (_: unknown, record: VirtualMaterial) => (
        <Space size={4} wrap>
          <Tooltip title="查看/编辑">
            <Button size="small" icon={<EyeOutlined />} onClick={() => openDetailDrawer(record)} />
          </Tooltip>
          <Tooltip title="配置（打开抽屉）">
            <Button size="small" icon={<EditOutlined />} onClick={() => openDetailDrawer(record)} />
          </Tooltip>
          {record.status === 'active' ? (
            <Popconfirm
              title="确认停用该虚拟物料？"
              description="仅修改状态为“停用”，不会删除（归档）。"
              okText="停用"
              cancelText="取消"
              onConfirm={() => statusMutation.mutate({ id: record.id, status: 'inactive' })}
            >
              <Tooltip title="停用">
                <Button size="small" danger icon={<StopOutlined />} loading={statusMutation.isPending} />
              </Tooltip>
            </Popconfirm>
          ) : (
            <Tooltip title="启用">
              <Button
                size="small"
                type="primary"
                icon={<CheckCircleOutlined />}
                onClick={() => statusMutation.mutate({ id: record.id, status: 'active' })}
                loading={statusMutation.isPending}
              />
            </Tooltip>
          )}
          {record.status === 'active' ? (
            <Tooltip title="删除（需先停用）">
              <Button size="small" danger icon={<DeleteOutlined />} disabled />
            </Tooltip>
          ) : (
            <Popconfirm
              title="确认删除该虚拟物料？"
              description="删除为归档删除：该虚拟物料将从列表隐藏。"
              okText="删除"
              okButtonProps={{ danger: true }}
              cancelText="取消"
              onConfirm={() => deactivateMutation.mutate(record.id)}
            >
              <Tooltip title="删除（归档）">
                <Button size="small" danger icon={<DeleteOutlined />} loading={deactivateMutation.isPending} />
              </Tooltip>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ]

  const drawerTitle =
    drawerMode === 'create'
      ? '新建虚拟物料'
      : currentVirtualMaterial
        ? `虚拟物料：${currentVirtualMaterial.name}`
        : '虚拟物料详情'

  return (
    <Space direction="vertical" size={24} style={{ width: '100%' }}>
      <div>
        <Title level={3} style={{ marginBottom: 0 }}>
          虚拟物料
        </Title>
        <Text type="secondary">
          维护虚拟套件与真实物料的绑定关系，可在这里配置配比、损耗与盘点换算。
        </Text>
      </div>

      <Card
        title="筛选"
        size="small"
        className="costing-filter-card"
        extra={
          <Space>
            <Button icon={<ReloadOutlined />} onClick={() => listQuery.refetch()}>
              刷新
            </Button>
            <Space>
              <span>显示子物料</span>
              <Switch checked={showBindingsInList} onChange={setShowBindingsInList} />
            </Space>
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreateDrawer}>
              新建虚拟物料
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
              style={{ width: 220 }}
            />
          </Form.Item>
          <Form.Item name="virtual_kind" label="类型">
            <Select
              allowClear
              placeholder="全部"
              options={[
                { label: '配方型', value: 'recipe' },
                { label: '套件型', value: 'kit' },
                { label: '占位型', value: 'placeholder' },
              ]}
              style={{ width: 160 }}
            />
          </Form.Item>
          <Form.Item name="binding_search" label="绑定物料">
            <Input
              placeholder="子物料编码/名称"
              allowClear
              style={{ width: 220 }}
              onPressEnter={handleFilterSubmit}
            />
          </Form.Item>
          <Form.Item name="status" label="状态">
            <Select
              allowClear
              placeholder="全部"
              options={statusOptions}
              style={{ width: 160 }}
            />
          </Form.Item>
          <Form.Item name="category" label="分类">
            <Select
              allowClear
              placeholder="全部分类"
              options={mergedCategoryOptions}
              showSearch
              optionFilterProp="label"
              style={{ width: 200 }}
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
        <Table<VirtualMaterial>
          rowKey="id"
          loading={listQuery.isLoading}
          columns={listColumns}
          dataSource={listData}
          pagination={{
            current: pagination.current,
            pageSize: pagination.pageSize,
            total: totalCount,
            showSizeChanger: true,
            showTotal: (total) => `共 ${total} 条`,
          }}
          onChange={handleTableChange}
        />
        <Text type="secondary" style={{ display: 'block', marginTop: 8 }}>
          说明：仅允许绑定启用中的真实物料；配比表示 1 个虚拟物料需要消耗的真实物料数量；损耗率以百分比计。
        </Text>
      </Card>

      <Drawer
        title={drawerTitle}
        width={1100}
        open={drawerOpen}
        onClose={closeDrawer}
        destroyOnClose
        extra={
          <Space>
            {drawerMode === 'view' && currentVirtualMaterial ? (
              <>
                <Tag color={currentVirtualMaterial.status === 'active' ? 'green' : 'gold'}>
                  {currentVirtualMaterial.status === 'active' ? '启用' : '草稿'}
                </Tag>
                <Text type="secondary">
                  更新于 {formatBeijingTime(currentVirtualMaterial.updated_at, 'YYYY-MM-DD HH:mm')}
                </Text>
              </>
            ) : null}

            <Button icon={<QuestionCircleOutlined />} onClick={() => setGuideOpen(true)}>
              新建指南
            </Button>

            <Button
              type="primary"
              onClick={handleSaveBasic}
              loading={savingBasic || createMutation.isPending || updateMutation.isPending}
              disabled={savingBasic || createMutation.isPending || updateMutation.isPending}
            >
              保存基础信息
            </Button>

            {drawerMode === 'view' && selectedId ? (
              <Button
                icon={<LinkOutlined />}
                onClick={() => {
                  queryClient.invalidateQueries({
                    queryKey: ['virtual-material', selectedId],
                  })
                }}
              >
                刷新详情
              </Button>
            ) : null}

            <Button onClick={closeDrawer}>关闭</Button>
          </Space>
        }
      >
        {drawerMode === 'view' && detailQuery.isLoading ? (
          <div style={{ textAlign: 'center', padding: 48 }}>
            <Spin />
          </div>
        ) : (
          <Space direction="vertical" size={24} style={{ width: '100%' }}>
            <Card title="基础信息" bordered={false}>
              <Form layout="vertical" form={basicForm}>
                <Form.Item name="unit" hidden>
                  <Input />
                </Form.Item>
                <Form.Item name="metadata_json" hidden>
                  <Input />
                </Form.Item>
                <Form.Item label="类型" name="virtual_kind" initialValue="kit">
                  <Radio.Group
                    optionType="button"
                    buttonStyle="solid"
                    onChange={(e) => {
                      const value = e.target.value as VirtualKind
                      basicForm.setFieldValue('virtual_kind', value)
                      basicForm.setFieldValue('unit', value === 'kit' ? DEFAULT_VIRTUAL_UNIT : '')
                      const bindings = (bindingForm.getFieldValue('bindings') as BindingFormValue[]) ?? []
                      if (value === 'placeholder') {
                        bindingForm.setFieldsValue({ bindings: [] })
                        setManualRatioEdited(false)
                        return
                      }
                      if (bindings.length) {
                        bindingUpdateRef.current = true
                        const next = bindings.map((item) => ({
                          ...item,
                          binding_type: (value === 'recipe' ? 'ratio' : 'quantity') as BindingMode,
                        }))
                        bindingForm.setFieldsValue({
                          bindings: value === 'recipe' && !manualRatioEdited ? distributeRatiosEvenly(next) : next,
                        })
                        bindingUpdateRef.current = false
                      }
                    }}
                    options={[
                      { label: '配方型', value: 'recipe' },
                      { label: '套件型', value: 'kit' },
                      { label: '占位型', value: 'placeholder' },
                    ]}
                  />
                </Form.Item>
                <Row gutter={16}>
                  <Col xs={24} md={12}>
                    <Form.Item
                      label="虚拟编码"
                      name="virtual_code"
                      rules={drawerMode === 'create' ? [] : [{ required: true, message: '请输入虚拟编码' }]}
                    >
                      <Input placeholder="创建时自动生成 VM+5位数字" disabled />
                    </Form.Item>
                  </Col>
                  <Col xs={24} md={12}>
                    <Form.Item
                      label="名称"
                      name="name"
                      rules={[{ required: true, message: '请输入名称' }]}
                    >
                      <Input placeholder="请输入虚拟物料名称" />
                    </Form.Item>
                  </Col>
                  <Form.Item noStyle shouldUpdate={(prev, curr) => prev.virtual_kind !== curr.virtual_kind}>
                    {() => {
                      const kind = (basicForm.getFieldValue('virtual_kind') as VirtualKind) ?? 'kit'
                      if (kind === 'kit') return null
                      return null
                    }}
                  </Form.Item>
                  <Form.Item noStyle shouldUpdate={(prev, curr) => prev.virtual_kind !== curr.virtual_kind}>
                    {() => {
                      const kind = (basicForm.getFieldValue('virtual_kind') as VirtualKind) ?? 'kit'
                      if (kind === 'placeholder') return null
                      return null
                    }}
                  </Form.Item>
                  <Col xs={24} md={12}>
                    <Form.Item
                      label="分类"
                      name="category"
                      rules={[{ required: true, message: '请选择分类' }]}
                    >
                      <Select
                        placeholder="请选择分类"
                        options={mergedCategoryOptions}
                        showSearch
                        optionFilterProp="label"
                      />
                    </Form.Item>
                  </Col>
                  <Col xs={24} md={12}>
                    <Form.Item label="状态" name="status" rules={[{ required: true }]}>
                      <Select options={statusOptions} />
                    </Form.Item>
                  </Col>
                  <Form.Item noStyle shouldUpdate={(prev, curr) => prev.virtual_kind !== curr.virtual_kind}>
                    {() => {
                      const kind = (basicForm.getFieldValue('virtual_kind') as VirtualKind) ?? 'kit'
                      if (kind !== 'placeholder') return <Col xs={24} md={12} />
                      return (
                        <>
                          <Col xs={24} md={12}>
                            <Form.Item label="单位" name="unit" rules={[{ required: true, message: '请选择单位' }]}>
                              <Select options={PLACEHOLDER_UNIT_OPTIONS} />
                            </Form.Item>
                          </Col>
                          <Col xs={24} md={12}>
                            <Form.Item
                              label="约束分类"
                              name={['metadata_json', 'constraint_category']}
                            >
                              <Select
                                placeholder="用于产品模型映射过滤"
                                options={mergedCategoryOptions}
                                showSearch
                                optionFilterProp="label"
                              />
                            </Form.Item>
                          </Col>
                        </>
                      )
                    }}
                  </Form.Item>
                  <Col span={24}>
                    <Form.Item
                      label="描述"
                      name="description"
                      extra="用于记录虚拟物料用途、组成说明等信息"
                    >
                      <Input.TextArea
                        placeholder="填写虚拟物料用途或备注"
                        autoSize={{ minRows: 4, maxRows: 8 }}
                      />
                    </Form.Item>
                  </Col>
                </Row>
                <Form.Item noStyle shouldUpdate={(prev, curr) => prev.virtual_kind !== curr.virtual_kind}>
                  {() => {
                    const kind = (basicForm.getFieldValue('virtual_kind') as VirtualKind) ?? 'kit'
                    if (kind !== 'placeholder') return null
                    return (
                      <Alert
                        type="warning"
                        showIcon
                        style={{ marginTop: 12 }}
                        message="占位型仅用于模板化"
                        description="占位型会在保存时自动生成占位符号：#{名称}。必须在产品模型里配置替换映射，否则模型不能启用（草稿可保存）。"
                      />
                    )
                  }}
                </Form.Item>
                <Text type="secondary" style={{ display: 'block', marginTop: 12 }}>
                  说明：配方型会自动校验子物料单位一致并推导单位；套件型单位固定为“套”；占位型不绑定子物料，BOM 单价固定为 0。
                </Text>
              </Form>
            </Card>

            <Card
              title="绑定真实物料"
              bordered={false}
              extra={
                <Space>
                  {virtualKind !== 'placeholder' ? (
                    <Button icon={<ReloadOutlined />} loading={syncingBindingData} onClick={handleSyncBindingData}>
                      同步数据
                    </Button>
                  ) : null}
                  {virtualKind !== 'placeholder' ? (
                    <Button icon={<PlusOutlined />} onClick={() => setMaterialPickerOpen(true)}>
                      添加物料
                    </Button>
                  ) : null}
                  <Button
                    icon={<SettingOutlined />}
                    type="primary"
                    onClick={handleSaveBindings}
                    loading={bindingsMutation.isPending}
                  >
                    保存绑定
                  </Button>
                </Space>
              }
            >
              <Descriptions
                size="small"
                column={1}
                layout="horizontal"
                style={{ marginBottom: 12, background: '#fafafa', padding: '12px 16px', borderRadius: 8 }}
              >
                <Descriptions.Item label="BOM 单价（用于成本）">
                  <Space size={8} wrap>
                    <Text>{virtualBomPriceLabel}</Text>
                    <Tag
                      color={
                        virtualBomPriceMeta.source === 'manual'
                          ? 'orange'
                          : virtualBomPriceMeta.source === 'derived'
                            ? 'green'
                            : 'default'
                      }
                    >
                      {virtualBomPriceMeta.tag}
                    </Tag>
                    {virtualKind !== 'placeholder' && !isZeroCostFallback ? (
                      virtualBomPriceMeta.source === 'manual' ? (
                        <Button
                          size="small"
                          type="link"
                          onClick={() => {
                            const meta = (basicForm.getFieldValue('metadata_json') || {}) as Record<string, unknown>
                            basicForm.setFieldsValue({ metadata_json: { ...meta, bom_unit_price: undefined } })
                            message.success('已清除手动覆盖：保存基础信息后将使用自动推导单价')
                          }}
                        >
                          清除覆盖
                        </Button>
                      ) : (
                        <Button
                          size="small"
                          type="link"
                          onClick={() => {
                            setBomOverrideDraftPrice(
                              manualBomUnitPrice !== undefined && manualBomUnitPrice !== null && String(manualBomUnitPrice) !== ''
                                ? Number(manualBomUnitPrice)
                                : null,
                            )
                            setBomOverrideDraftUnit(selectedUnit || null)
                            setBomOverrideModalOpen(true)
                          }}
                        >
                          设置覆盖
                        </Button>
                      )
                    ) : null}
                  </Space>
                </Descriptions.Item>
              </Descriptions>
              <Modal
                title="设置 BOM 单价覆盖"
                open={bomOverrideModalOpen}
                onCancel={() => setBomOverrideModalOpen(false)}
                okText="确定（写入覆盖）"
                cancelText="取消"
                destroyOnClose
                okButtonProps={{ disabled: isZeroCostFallback || virtualKind === 'placeholder' }}
                onOk={() => {
                  const nextPrice =
                    bomOverrideDraftPrice === null ||
                    bomOverrideDraftPrice === undefined ||
                    String(bomOverrideDraftPrice) === ''
                      ? undefined
                      : Number(bomOverrideDraftPrice)
                  const meta = (basicForm.getFieldValue('metadata_json') || {}) as Record<string, unknown>
                  basicForm.setFieldsValue({
                    metadata_json: { ...meta, bom_unit_price: nextPrice },
                    ...(virtualKind === 'recipe' && bomOverrideDraftUnit ? { unit: bomOverrideDraftUnit } : {}),
                  })
                  setBomOverrideModalOpen(false)
                  message.success('已写入覆盖值：请点“保存基础信息”入库后生效（成本将优先使用覆盖值）')
                }}
              >
                <Space direction="vertical" style={{ width: '100%' }} size={12}>
                  {isZeroCostFallback ? (
                    <Alert
                      type="warning"
                      showIcon
                      message="兜底-零成本 虚拟物料：BOM 单价与单位已锁定，不允许覆盖"
                      description="如需调整，请新建非兜底虚拟物料并绑定真实物料推导单价。"
                    />
                  ) : null}
                  <Alert
                    type="info"
                    showIcon
                    message="默认口径：自动推导"
                    description="自动推导=按绑定真实物料的 BOM 单价 × 配比 × 损耗 汇总。仅在兜底/临时需要时使用覆盖。"
                  />
                  <Row gutter={12}>
                    <Col span={12}>
                      <div style={{ marginBottom: 6 }}>
                        <Text type="secondary">覆盖单价（可留空=不覆盖）</Text>
                      </div>
                      <InputNumber
                        min={0}
                        precision={6}
                        style={{ width: '100%' }}
                        value={bomOverrideDraftPrice ?? undefined}
                        onChange={(v) => setBomOverrideDraftPrice(v == null ? null : Number(v))}
                        placeholder="例如：0"
                        disabled={isZeroCostFallback || virtualKind === 'placeholder'}
                      />
                    </Col>
                    <Col span={12}>
                      <div style={{ marginBottom: 6 }}>
                        <Text type="secondary">单位（配方型可选）</Text>
                      </div>
                      <Select
                        allowClear
                        disabled={isZeroCostFallback || virtualKind !== 'recipe'}
                        options={VM_UNIT_OPTIONS}
                        value={bomOverrideDraftUnit ?? undefined}
                        onChange={(v) => setBomOverrideDraftUnit(v ?? null)}
                        placeholder={virtualKind === 'recipe' ? '不填则沿用当前单位/自动推导' : '仅配方型可选'}
                      />
                    </Col>
                  </Row>
                </Space>
              </Modal>
              <Alert
                type="warning"
                showIcon
                message={
                  virtualKind === 'recipe'
                    ? '配方型要求子物料单位一致；虚拟单价按“每单位配方”的真实物料成本汇总。'
                    : virtualKind === 'placeholder'
                      ? '占位型不绑定子物料：BOM 单价固定为 0，仅用于模板化占位。'
                      : '套件型允许子物料单位不同；虚拟单价按“每套”汇总。'
                }
                style={{ marginBottom: 16 }}
              />
              <Form
                form={bindingForm}
                layout="vertical"
                onValuesChange={(changedValues) => {
                  if (bindingUpdateRef.current) return
                  if (changedValues.bindings) {
                    setManualRatioEdited(true)
                  }
                }}
              >
                <Form.List name="bindings">
                  {(fields, { remove }) => {
                    if (virtualKind === 'placeholder') {
                      return (
                        <Alert
                          type="info"
                          showIcon
                          message="占位型不绑定子物料"
                          description="占位型仅用于工艺模块模板化；请在产品模型中配置替换映射后再启用模型。"
                        />
                      )
                    }
                    const dataSource = fields.map((field) => ({
                      key: field.key,
                      field,
                      binding: activeBindings[field.name] || {},
                    }))
                    const columns: ColumnsType<{
                      key: number
                      field: { name: number; key: number }
                      binding: BindingFormValue
                    }> = [
                      {
                        title: '物料',
                        dataIndex: 'binding',
                        width: 280,
                        render: (_: unknown, record) => (
                          <Space align="start" size={12}>
                            <Image
                              src={record.binding.image_url}
                              width={36}
                              height={36}
                              style={{ objectFit: 'cover', borderRadius: 4 }}
                              placeholder
                              loading="lazy"
                              fallback="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' width='36' height='36'/>"
                              preview={false}
                            />
                            <Space direction="vertical" size={2}>
                              <Button
                                type="link"
                                size="small"
                                style={{ padding: 0 }}
                                onClick={() => {
                                  if (!record.binding.material_id) return
                                  openMaterialDrawerById(record.binding.material_id)
                                }}
                              >
                                {record.binding.material_name || '-'}
                              </Button>
                              <Space size={8}>
                                <Text code>{record.binding.material_code || '-'}</Text>
                                <Tag>{record.binding.unit || '-'}</Tag>
                              </Space>
                              <Form.Item name={[record.field.name, 'material_id']} hidden>
                                <Input />
                              </Form.Item>
                              <Form.Item name={[record.field.name, 'material_code']} hidden>
                                <Input />
                              </Form.Item>
                              <Form.Item name={[record.field.name, 'material_name']} hidden>
                                <Input />
                              </Form.Item>
                              <Form.Item name={[record.field.name, 'unit']} hidden>
                                <Input />
                              </Form.Item>
                              <Form.Item name={[record.field.name, 'currency']} hidden>
                                <Input />
                              </Form.Item>
                              <Form.Item name={[record.field.name, 'purchase_unit_price']} hidden>
                                <Input />
                              </Form.Item>
                              <Form.Item name={[record.field.name, 'purchase_unit']} hidden>
                                <Input />
                              </Form.Item>
                              <Form.Item name={[record.field.name, 'bom_unit_price']} hidden>
                                <Input />
                              </Form.Item>
                              <Form.Item name={[record.field.name, 'bom_unit']} hidden>
                                <Input />
                              </Form.Item>
                              <Form.Item name={[record.field.name, 'image_url']} hidden>
                                <Input />
                              </Form.Item>
                            </Space>
                          </Space>
                        ),
                      },
                      {
                        title: virtualKind === 'recipe' ? '配比（%）' : '每套数量',
                        dataIndex: 'quantity_ratio',
                        width: 130,
                        render: (_: unknown, record) => (
                          <Form.Item
                            name={[record.field.name, 'quantity_ratio']}
                            style={{ marginBottom: 0 }}
                            rules={[
                              { required: true, message: '请输入数值' },
                              {
                                validator: (_rule, value) =>
                                  value && value > 0
                                    ? Promise.resolve()
                                    : Promise.reject(new Error('需大于 0')),
                              },
                            ]}
                          >
                            {virtualKind === 'recipe' ? (
                              <InputNumber
                                min={0.0001}
                                max={1}
                                step={0.01}
                                style={{ width: '100%' }}
                                formatter={(value) =>
                                  value !== undefined && value !== null ? `${Number(value) * 100}%` : ''
                                }
                                parser={(value?: string) =>
                                  value ? Number(value.replace('%', '')) / 100 : 0
                                }
                              />
                            ) : (
                              <InputNumber min={0.0001} step={0.1} style={{ width: '100%' }} />
                            )}
                          </Form.Item>
                        ),
                      },
                      {
                        title: '损耗率 (%)',
                        dataIndex: 'loss_rate',
                        width: 100,
                        render: (_: unknown, record) => (
                          <Form.Item
                            name={[record.field.name, 'loss_rate']}
                            style={{ marginBottom: 0 }}
                            rules={[
                              {
                                validator: (_rule, value) =>
                                  value === undefined || (value >= 0 && value <= 100)
                                    ? Promise.resolve()
                                    : Promise.reject(new Error('损耗率需在 0-100% 之间')),
                              },
                            ]}
                          >
                            <InputNumber min={0} max={100} step={0.5} style={{ width: '100%' }} />
                          </Form.Item>
                        ),
                      },
                      {
                        title: 'BOM 单价/单位',
                        dataIndex: 'bom',
                        width: 130,
                        render: (_: unknown, record) => (
                          <Space direction="vertical" size={0}>
                            <Text>
                              {formatCurrency(record.binding.bom_unit_price, record.binding.currency)}
                            </Text>
                            <Text type="secondary">
                              {getBomUnitLabel(record.binding.bom_unit) ??
                                record.binding.bom_unit ??
                                record.binding.unit ??
                                '-'}
                            </Text>
                          </Space>
                        ),
                      },
                      {
                        title: '操作',
                        dataIndex: 'actions',
                        width: 120,
                        fixed: 'right',
                        render: (_: unknown, record) => (
                          <Button
                            type="link"
                            size="small"
                            danger
                            icon={<DeleteOutlined />}
                            onClick={() => {
                              remove(record.field.name)
                              if (virtualKind === 'recipe' && !manualRatioEdited) {
                                const nextBindings =
                                  (bindingForm.getFieldValue('bindings') as BindingFormValue[]) ?? []
                                if (nextBindings.length) {
                                  bindingUpdateRef.current = true
                                  bindingForm.setFieldsValue({
                                    bindings: distributeRatiosEvenly(nextBindings),
                                  })
                                  bindingUpdateRef.current = false
                                }
                              }
                            }}
                          >
                            移除
                          </Button>
                        ),
                      },
                    ]
                    return dataSource.length ? (
                      <Table
                        size="middle"
                        dataSource={dataSource}
                        columns={columns}
                        pagination={false}
                        rowKey="key"
                        scroll={{ x: 900 }}
                      />
                    ) : (
                      <Empty description="尚未添加真实物料" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                    )
                  }}
                </Form.List>
              </Form>
              <Alert
                style={{ marginTop: 16 }}
                type={ratioIsValid ? 'success' : 'warning'}
                showIcon
                message={
                  virtualKind === 'recipe'
                    ? `配比合计：${totalRatioPercent ?? 0}%`
                    : '套件清单：数量为“每套用量”'
                }
                description={
                  virtualKind === 'recipe' && bindingSummary.hasRatioMode && !ratioIsValid
                    ? '请将按比例项的配比调整为合计 100%。'
                    : '校验通过，可直接保存。'
                }
              />
              <Alert
                type="info"
                showIcon
                style={{ marginTop: 12 }}
                message="使用说明"
                description={
                  virtualKind === 'recipe'
                    ? '配方型：仅允许按比例绑定，且子物料单位必须与虚拟单位一致；配比合计需为 100%。'
                    : '套件型：仅允许按数量绑定，数量表示“每套用量”，子物料单位可不同。'
                }
              />
            </Card>

            <Card title="盘点计算器" bordered={false}>
              {drawerMode === 'create' ? (
                <Alert
                  type="info"
                  showIcon
                  message="请先创建虚拟物料后再使用盘点功能"
                />
              ) : (
                <>
                  <Form
                    form={inventoryForm}
                    layout="inline"
                    onFinish={handleInventoryCalculate}
                    initialValues={{ quantity: 1 }}
                  >
                    <Form.Item
                      label="虚拟物料数量"
                      name="quantity"
                      rules={[{ required: true, message: '请输入数量' }]}
                    >
                      <InputNumber min={0.0001} step={0.5} style={{ width: 180 }} />
                    </Form.Item>
                    <Form.Item label="计算方式" name="calculation_method">
                      <Select
                        allowClear
                        placeholder="请选择计算方式"
                        style={{ width: 200 }}
                        options={CALCULATION_METHOD_OPTIONS.map((item) => ({
                          label: item.label,
                          value: item.value,
                        }))}
                      />
                    </Form.Item>
                    <Form.Item label="使用场景" name="usage_context">
                      <Input placeholder="如：门头-户外" style={{ width: 200 }} />
                    </Form.Item>
                    <Form.Item>
                      <Button
                        type="primary"
                        htmlType="submit"
                        loading={inventoryMutation.isPending}
                        disabled={!selectedId}
                      >
                        计算所需真实物料
                      </Button>
                    </Form.Item>
                  </Form>
                  <Text type="secondary" style={{ display: 'block', marginTop: 8 }}>
                    计算方式与使用场景至少填写一项，用于记录本次折算依据。
                  </Text>
                </>
              )}
              {inventoryResult && (
                <>
                  <Descriptions
                    size="small"
                    column={1}
                    layout="horizontal"
                    style={{
                      marginTop: 16,
                      background: '#fafafa',
                      padding: '12px 16px',
                      borderRadius: 8,
                    }}
                  >
                    {inventoryResult.calculation_method && (
                      <Descriptions.Item label="计算方式">
                        {getCalculationMethodLabel(inventoryResult.calculation_method)}
                      </Descriptions.Item>
                    )}
                    {inventoryResult.usage_context && (
                      <Descriptions.Item label="使用场景">
                        {inventoryResult.usage_context}
                      </Descriptions.Item>
                    )}
                  </Descriptions>
                  <Table
                    style={{ marginTop: 16 }}
                    rowKey="material_id"
                    dataSource={inventoryResult.items.map((item) => ({
                      ...item,
                      quantity_ratio: Number(item.quantity_ratio),
                      loss_rate: Number(item.loss_rate),
                      required_quantity: Number(item.required_quantity),
                    }))}
                    pagination={false}
                    columns={[
                      {
                        title: '物料编码',
                        dataIndex: 'material_code',
                        key: 'material_code',
                        render: (code: string) => <Text code>{code}</Text>,
                      },
                      {
                        title: '名称',
                        dataIndex: 'material_name',
                        key: 'material_name',
                      },
                      {
                        title: '单位',
                        dataIndex: 'unit',
                        key: 'unit',
                      },
                      {
                        title: '配比',
                        dataIndex: 'quantity_ratio',
                        key: 'quantity_ratio',
                      },
                      {
                        title: '损耗率 (%)',
                        dataIndex: 'loss_rate',
                        key: 'loss_rate',
                      },
                      {
                        title: `所需数量（${inventoryResult.virtual_name} × ${inventoryResult.requested_quantity}）`,
                        dataIndex: 'required_quantity',
                        key: 'required_quantity',
                      },
                    ]}
                  />
                </>
              )}
            </Card>
          </Space>
        )}
      </Drawer>

      <GuideDrawer
        open={guideOpen}
        onClose={() => setGuideOpen(false)}
        title="新建虚拟物料指南"
        content={virtualMaterialsGuide}
        tip="提示：这是“虚拟物料”面板的新建/维护指南（Markdown）。需要改文案时，直接在仓库里改对应文档并重新部署即可。"
      />

      <MaterialSelectModal
        open={materialPickerOpen}
        onClose={() => setMaterialPickerOpen(false)}
        onConfirm={(materials) => {
          handleMaterialSelect(materials)
          setMaterialPickerOpen(false)
        }}
      />
      <MaterialDrawer
        materialId={currentMaterialId}
        open={materialDrawerOpen}
        onClose={() => setMaterialDrawerOpen(false)}
        onUpdated={() => {
          if (selectedId) {
            detailQuery.refetch()
          }
        }}
      />
    </Space>
  )
}

interface MaterialSelectModalProps {
  open: boolean
  onClose: () => void
  onConfirm: (materials: Material[]) => void
}

const MaterialSelectModal = ({ open, onClose, onConfirm }: MaterialSelectModalProps) => {
  const [search, setSearch] = useState('')
  const [category, setCategory] = useState<string | undefined>(undefined)
  const [onlyBom, setOnlyBom] = useState(false)
  const [pagination, setPagination] = useState({ current: 1, pageSize: 8 })
  const [selectedRowKeys, setSelectedRowKeys] = useState<Key[]>([])
  const [selectedRows, setSelectedRows] = useState<Material[]>([])

  const taxonomyCategoryQuery = useQuery({
    queryKey: ['taxonomy-items', 'material_category', 'picker'],
    queryFn: () => fetchTaxonomyItems('material_category', { include_inactive: false }),
    enabled: open,
  })

  useEffect(() => {
    if (!open) {
      setSearch('')
      setPagination({ current: 1, pageSize: 8 })
      setSelectedRowKeys([])
      setSelectedRows([])
    }
  }, [open])

  const pickerQuery = useQuery({
    queryKey: ['material-picker', search, category, onlyBom, pagination],
    queryFn: ({ signal }) =>
      fetchMaterials(
        {
          search: search || undefined,
          category,
          page: pagination.current,
          page_size: pagination.pageSize,
          is_active: true,
          is_bom_material: onlyBom || undefined,
        },
        { signal },
      ),
    enabled: open,
    placeholderData: keepPreviousData,
    staleTime: 0,
  })

  const materialsRaw = (pickerQuery.data?.items ?? []) as Material[]
  // Phase0：真实物料选择器不展示“间接耗材”（周期领用核算），但允许“条件物料”
  const materials = materialsRaw.filter((m) => {
    const meta = ((m as any)?.metadata_json ?? {}) as Record<string, any>
    const usage = String(meta?.usage_class ?? '').trim().toLowerCase()
    return usage !== 'indirect'
  })

  const handleConfirm = () => {
    if (!selectedRows.length) {
      message.warning('请选择至少一个物料')
      return
    }
    onConfirm(selectedRows)
    onClose()
  }

  return (
    <Modal
      title="选择真实物料"
      open={open}
      onCancel={onClose}
      width={780}
      destroyOnClose
      footer={
        <Space>
          <Button onClick={onClose}>取消</Button>
          <Button type="primary" disabled={!selectedRows.length} onClick={handleConfirm}>
            添加所选（{selectedRows.length}）
          </Button>
        </Space>
      }
    >
      <Space style={{ marginBottom: 16 }} wrap>
        <Select
          allowClear
          placeholder="分类"
          showSearch
          optionFilterProp="label"
          style={{ width: 180 }}
          value={category}
          onChange={(value) => {
            setCategory(value)
            setPagination((prev) => ({ ...prev, current: 1 }))
          }}
          filterOption={(input, opt) => {
            const label = String((opt as any)?.label ?? '')
            return label.toLowerCase().includes(String(input ?? '').toLowerCase())
          }}
          options={(taxonomyCategoryQuery.data?.items ?? []).map((it: any) => ({
            label: it.name,
            value: it.name,
          }))}
        />
        <Input.Search
          placeholder="按编码 / 名称搜索"
          allowClear
          value={search}
          onChange={(event) => {
            setSearch(event.target.value)
            setPagination((prev) => ({ ...prev, current: 1 }))
          }}
          onSearch={() => setPagination((prev) => ({ ...prev, current: 1 }))}
          style={{ width: 240 }}
        />
        <Space>
          <span>仅 BOM 物料</span>
          <Switch
            checked={onlyBom}
            onChange={(checked) => {
              setOnlyBom(checked)
              setPagination((prev) => ({ ...prev, current: 1 }))
            }}
          />
        </Space>
      </Space>
      <Table<Material>
        rowKey="id"
        dataSource={materials}
        loading={pickerQuery.isFetching}
        pagination={{
          current: pagination.current,
          pageSize: pagination.pageSize,
          total: pickerQuery.data?.total ?? 0,
          showSizeChanger: false,
          onChange: (page) => setPagination((prev) => ({ ...prev, current: page })),
        }}
        rowSelection={{
          selectedRowKeys,
          onChange: (keys, rows) => {
            setSelectedRowKeys(keys)
            setSelectedRows(rows as Material[])
          },
        }}
        columns={[
          {
            title: '图片',
            dataIndex: 'images',
            key: 'images',
            width: 80,
            render: (_: unknown, record) => {
              const cover = getPrimaryImage(record, 160)
              if (!cover) {
                return <Text type="secondary">-</Text>
              }
              return (
                <Image
                  src={cover}
                  width={48}
                  height={48}
                  style={{ objectFit: 'cover', borderRadius: 4 }}
                  loading="lazy"
                  preview={false}
                  fallback="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' width='48' height='48' />"
                />
              )
            },
          },
          {
            title: '物料编码',
            dataIndex: 'material_code',
            key: 'material_code',
            width: 160,
            render: (code: string) => <Text code>{code}</Text>,
          },
          {
            title: '名称',
            dataIndex: 'material_name',
            key: 'material_name',
            render: (text: string, record) => (
              <Space direction="vertical" size={0}>
                <Text strong>{text}</Text>
                <Text type="secondary">{record.category || '-'}</Text>
              </Space>
            ),
          },
          {
            title: 'BOM单价/单位',
            key: 'bom_price',
            width: 200,
            render: (_: unknown, record) => (
              <Space direction="vertical" size={0}>
                <Text>{formatCurrency(deriveBomUnitPrice(record), record.currency)}</Text>
                <Text type="secondary">
                  {getBomUnitLabel(record.unit) ?? record.unit ?? record.purchase_unit ?? '-'}
                </Text>
              </Space>
            ),
          },
        ]}
      />
    </Modal>
  )
}

export default VirtualMaterialsPage

