import CloudSyncOutlined from '@ant-design/icons/lib/icons/CloudSyncOutlined'
import CopyOutlined from '@ant-design/icons/lib/icons/CopyOutlined'
import DownloadOutlined from '@ant-design/icons/lib/icons/DownloadOutlined'
import EditOutlined from '@ant-design/icons/lib/icons/EditOutlined'
import FileSearchOutlined from '@ant-design/icons/lib/icons/FileSearchOutlined'
import HistoryOutlined from '@ant-design/icons/lib/icons/HistoryOutlined'
import QuestionCircleOutlined from '@ant-design/icons/lib/icons/QuestionCircleOutlined'
import ReloadOutlined from '@ant-design/icons/lib/icons/ReloadOutlined'
import {
  Alert,
  Badge,
  Button,
  Card,
  Col,
  Descriptions,
  Drawer,
  Empty,
  Form,
  Input,
  InputNumber,
  Image,
  Modal,
  Row,
  Select,
  Space,
  Spin,
  Switch,
  Table,
  Tabs,
  Tag,
  Tooltip,
  Typography,
  message,
} from 'antd'
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table'
import dayjs from 'dayjs'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { MATERIAL_CATEGORIES } from '@/constants/materialCategories'
import {
  exportMaterials,
  fetchMaterialSyncJob,
  fetchMaterialSyncLogs,
  fetchMaterials,
  fetchMaterialVirtualLinks,
  triggerMaterialBomDerive,
  triggerMaterialSync,
  updateMaterial,
} from '@/services/planner'
import type {
  CalculationMethod,
  Material,
  MaterialListResponse,
  MaterialStatusUpdatePayload,
  MaterialSyncLog,
  MaterialSyncLogResponse,
  VirtualMaterialReference,
} from '@/types/planner'
import { MATERIAL_STATUS_OPTIONS } from '@/constants/planner'
import {
  CALCULATION_METHOD_OPTIONS,
  getCalculationMethodLabel,
  getDefaultUnitByCalculationMethod,
} from '@/constants/calculationMethods'
import { isAxiosError } from 'axios'
import GuideDrawer from '@/components/common/GuideDrawer'
import materialsGuide from '@/guides/materials_guide.md?raw'

const { Title, Text } = Typography
const { PreviewGroup } = Image

const BOM_TRUE_TOKENS = new Set(['1', 'true', 'yes', 'y', '启用', '激活', 'active', '是'])

const BOM_UNIT_OPTIONS = [
  { label: '平米', value: '平米' },
  { label: '米', value: '米' },
  { label: '个', value: '个' },
]

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
}

const normalizeBomUnit = (value?: string | null): string | undefined => {
  if (!value) {
    return undefined
  }
  const v = String(value).trim()
  if (['平米', '㎡', '平方', '平方米', 'm²', 'M2', 'm2'].includes(v)) return '平米'
  if (['米', 'm', 'M'].includes(v)) return '米'
  if (v === '个') return '个'
  if (v === '套') return '套'
  return v
}

const getBomUnitLabel = (value?: string | null): string | undefined => {
  const normalized = normalizeBomUnit(value)
  if (!normalized) {
    return undefined
  }
  return BOM_UNIT_LABEL_MAP[normalized] ?? normalized
}

const formatDecimalDisplay = (value?: string | number, fractionDigits = 2): string => {
  const num = Number(value)
  if (!Number.isFinite(num)) {
    return '-'
  }
  return Number(num.toFixed(fractionDigits)).toString()
}

const parseDecimal = (value?: string | number | null): number | undefined => {
  if (value === undefined || value === null) {
    return undefined
  }
  const num = Number(value)
  return Number.isFinite(num) ? num : undefined
}

const toFiniteNumber = (value: unknown): number | undefined => {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value
  }
  return undefined
}

const isBomMaterial = (record: Material): boolean => {
  const metadata = (record.metadata_json ?? {}) as {
    raw_form_data?: Record<string, unknown>
    [key: string]: unknown
  }
  const rawForm = metadata.raw_form_data ?? {}
  const rawValue = rawForm?.['radioField_lxo4jeon'] ?? metadata?.bom_material_flag

  if (typeof rawValue === 'boolean') {
    return rawValue
  }

  if (rawValue === undefined || rawValue === null) {
    return false
  }

  const normalized = String(rawValue).trim().toLowerCase()
  if (!normalized) {
    return false
  }

  if (BOM_TRUE_TOKENS.has(normalized)) {
    return true
  }

  // 中文“是”不会被 toLowerCase 影响，再额外判一次
  return rawValue === '是'
}

const defaultFilters = {
  search: undefined as string | undefined,
  category: undefined as string | undefined,
  status: undefined as string | undefined,
  is_active: true as boolean | undefined,
  is_bom_material: true as boolean | undefined,
}

const getBomUnitPrice = (record: Material): number | undefined => {
  const value = (record.metadata_json as Record<string, unknown> | undefined)?.['bom_unit_price']
  if (typeof value === 'number') {
    return value
  }
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value)
    return Number.isNaN(parsed) ? undefined : parsed
  }
  return undefined
}

const deriveBomUnitPrice = (record: Material): number | undefined => {
  // display 与“推导BOM价格”按钮保持同口径：缺关键输入则不推导
  if (!record.unit || !String(record.unit).trim()) {
    return undefined
  }
  if (!record.purchase_unit || !String(record.purchase_unit).trim()) {
    return undefined
  }
  const metadataPrice = getBomUnitPrice(record)
  if (metadataPrice !== undefined) {
    return metadataPrice
  }
  if (record.unit_price === undefined || record.unit_price === null) {
    return undefined
  }
  if (Number(record.unit_price) <= 0) {
    return undefined
  }
  const conversion = parseDecimal(record.conversion_purchase_to_bom)
  if (!conversion || conversion <= 0) {
    return undefined
  }
  return Number(record.unit_price) / conversion
}

const getBomDeriveIssue = (record: Material): string | null => {
  // 这里的“BOM 单价/单位”是后续算价/扣库的基础输入。若无法推导，必须明确暴露原因，避免静默失败。
  if (!record.unit || !String(record.unit).trim()) {
    return '未选择 BOM 单位（请在物料详情-成本参数里选择并保存）'
  }
  if (!record.purchase_unit || !String(record.purchase_unit).trim()) {
    return '入库单位缺失（请先同步/补齐入库单位；不要自动补齐）'
  }
  if (record.unit_price === undefined || record.unit_price === null) {
    return '入库单价缺失（请先同步/录入入库单价）'
  }
  if (Number(record.unit_price) <= 0) {
    return '入库单价为 0（可能未同步完成/数据缺失）'
  }
  const conversion = parseDecimal(record.conversion_purchase_to_bom)
  if (!conversion || conversion <= 0) {
    return '入库→BOM 换算缺失或不合法（必须 > 0）'
  }
  return null
}

const getBomDisplayValue = (record: Material) =>
  typeof record.is_bom_material === 'boolean' ? record.is_bom_material : isBomMaterial(record)

const getErrorMessage = (error: unknown): string => {
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

const toFullUrl = (url?: string) => {
  if (!url) {
    return ''
  }
  if (/^https?:\/\//i.test(url)) {
    return url
  }
  return url
}

const getImageUrls = (record: Material): string[] => {
  if (Array.isArray(record.images)) {
    return record.images.filter((item) => typeof item === 'string' && item.trim())
  }
  return []
}

const getFormValue = (record: Material, key: string): string => {
  const metadata = (record.metadata_json ?? {}) as {
    raw_form_data?: Record<string, unknown>
    [k: string]: unknown
  }
  const raw = metadata.raw_form_data ?? {}
  const value = raw?.[key] ?? metadata?.[key]
  if (typeof value === 'string') {
    return value
  }
  if (typeof value === 'number') {
    return String(value)
  }
  return ''
}

const getMaterialTypeLabel = (record: Material): string => {
  const fromForm = getFormValue(record, 'radioField_lxmp8bgd')
  if (fromForm) {
    return fromForm
  }
  switch (record.material_type) {
    case 'virtual':
      return '虚拟物料'
    case 'component':
      return '部件/组件'
    case 'raw':
      return '主料'
    default:
      return record.material_type || '-'
  }
}

interface CostFormValues {
  is_bom_material?: boolean
  bom_unit?: string
  conversion_purchase_to_bom?: number
  inventory_unit?: string
  conversion_bom_to_inventory?: number
  calculation_method?: CalculationMethod
  local_description?: string
  fixed_quantity_alpha?: number
  coverage_ratio?: number
  default_loss_rate?: number
}

const positiveNumberRule = (message: string) => ({
  validator: (_: unknown, value: number | null | undefined) => {
    if (value && value > 0) {
      return Promise.resolve()
    }
    return Promise.reject(new Error(message))
  },
})

const MaterialMasterPage = () => {
  const queryClient = useQueryClient()
  const [filtersForm] = Form.useForm()
  const [costForm] = Form.useForm()
  const lastSubmittedCostValuesRef = useRef<CostFormValues | null>(null)
  const lastAutoBomToInventoryRef = useRef<number | null>(null)
  const [filters, setFilters] = useState(defaultFilters)
  const [pagination, setPagination] = useState({ current: 1, pageSize: 20 })
  const [syncDrawerOpen, setSyncDrawerOpen] = useState(false)
  const [syncPagination, setSyncPagination] = useState({ page: 1, pageSize: 10 })
  const [exporting, setExporting] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [detailDrawerOpen, setDetailDrawerOpen] = useState(false)
  const [guideOpen, setGuideOpen] = useState(false)
  const [editingMaterial, setEditingMaterial] = useState<Material | null>(null)
  const watchedBomUnit = Form.useWatch('bom_unit', costForm)
  const watchedInventoryUnit = Form.useWatch('inventory_unit', costForm)
  const watchedConversionPurchaseToBom = Form.useWatch('conversion_purchase_to_bom', costForm)
  const watchedConversionBomToInventory = Form.useWatch('conversion_bom_to_inventory', costForm)

  useEffect(() => {
    if (!detailDrawerOpen || !editingMaterial) {
      return
    }
    const inboundUnit = editingMaterial.purchase_unit || ''
    const inventoryUnit = (watchedInventoryUnit ?? editingMaterial.inventory_unit ?? inboundUnit) || ''
    const convPurchase =
      toFiniteNumber(watchedConversionPurchaseToBom) ?? parseDecimal(editingMaterial.conversion_purchase_to_bom)
    if (!inboundUnit || !inventoryUnit || inboundUnit !== inventoryUnit) {
      return
    }
    if (!convPurchase || convPurchase <= 0) {
      return
    }
    const derived = Number((1 / convPurchase).toFixed(6))
    if (!Number.isFinite(derived)) {
      return
    }
    const current = toFiniteNumber(watchedConversionBomToInventory)
    // 仅在“未填写”或仍是上一次自动值时才自动回填，避免覆盖用户手动输入
    if (current === undefined || current === null || current === lastAutoBomToInventoryRef.current) {
      lastAutoBomToInventoryRef.current = derived
      costForm.setFieldsValue({ conversion_bom_to_inventory: derived })
    }
  }, [
    detailDrawerOpen,
    editingMaterial,
    watchedInventoryUnit,
    watchedConversionPurchaseToBom,
    watchedConversionBomToInventory,
    costForm,
  ])

  const materialsQuery = useQuery<MaterialListResponse>({
    queryKey: ['materials', filters, pagination],
    queryFn: () =>
      fetchMaterials({
        ...filters,
        page: pagination.current,
        page_size: pagination.pageSize,
      }),
    placeholderData: keepPreviousData,
  })

  const materialVirtualLinksQuery = useQuery<VirtualMaterialReference[]>({
    queryKey: ['material-virtual-links', editingMaterial?.id],
    queryFn: () => fetchMaterialVirtualLinks(editingMaterial!.id),
    enabled: detailDrawerOpen && !!editingMaterial?.id,
  })

  const materials = materialsQuery.data?.items ?? []
  const totalCount = materialsQuery.data?.total ?? 0
  const backendCategories = materialsQuery.data?.categories
  const categoryOptions = useMemo(() => {
    const seen = new Set<string>()
    const options: { label: string; value: string }[] = []
    const append = (raw?: string | null) => {
      const value = raw?.trim()
      if (!value || seen.has(value)) {
        return
      }
      seen.add(value)
      options.push({ label: value, value })
    }
    MATERIAL_CATEGORIES.forEach((value) => append(value))
    ;(backendCategories ?? []).forEach((value) => append(value))
    materials.forEach((item) => {
      append(getFormValue(item, 'textField_jacd537') || item.category)
    })
    return options
  }, [backendCategories, materials])

  const syncLogsQuery = useQuery<MaterialSyncLogResponse>({
    queryKey: ['material-sync-logs', syncDrawerOpen, syncPagination],
    queryFn: () =>
      fetchMaterialSyncLogs({
        page: syncPagination.page,
        page_size: syncPagination.pageSize,
      }),
    enabled: syncDrawerOpen,
    placeholderData: keepPreviousData,
  })

  const statusMutation = useMutation<Material, Error, { id: string; active: boolean }>({
    mutationFn: ({ id, active }: { id: string; active: boolean }) =>
      updateMaterial(id, { is_active: active, status: active ? 'active' : 'inactive' }),
    onSuccess: (_, variables) => {
      message.success(`物料已${variables.active ? '启用' : '停用'}`)
      queryClient.invalidateQueries({ queryKey: ['materials'] })
    },
    onError: (error: unknown) => {
      message.error(getErrorMessage(error) || '更新状态失败')
    },
  })

  const bomMutation = useMutation<
    Material,
    Error,
    { id: string; bom: boolean; origin: 'list' | 'drawer' }
  >({
    mutationFn: ({ id, bom }) => updateMaterial(id, { is_bom_material: bom }),
    onSuccess: (updated, variables) => {
      message.success('BOM 标记已更新')
      queryClient.invalidateQueries({ queryKey: ['materials'] })
      setEditingMaterial((prev) => (prev?.id === updated.id ? updated : prev))
      if (variables.origin === 'drawer') {
        costForm.setFieldsValue({ is_bom_material: updated.is_bom_material })
      }
    },
    onError: (error, variables) => {
      message.error(getErrorMessage(error))
      if (variables.origin === 'drawer' && editingMaterial) {
        costForm.setFieldsValue({ is_bom_material: getBomDisplayValue(editingMaterial) })
      }
    },
  })

  const detailMutation = useMutation<
    Material,
    Error,
    { id: string; payload: MaterialStatusUpdatePayload }
  >({
    mutationFn: ({ id, payload }) => updateMaterial(id, payload),
    onSuccess: (updated) => {
      message.success('成本参数已保存')
      queryClient.invalidateQueries({ queryKey: ['materials'] })
      setEditingMaterial(updated)
      const fallback = lastSubmittedCostValuesRef.current
      const updatedMetadata = (updated.metadata_json as Record<string, any>) ?? {}
      costForm.setFieldsValue({
        is_bom_material: getBomDisplayValue(updated),
        bom_unit:
          normalizeBomUnit(updated.unit) ??
          fallback?.bom_unit ??
          BOM_UNIT_OPTIONS[0].value,
        conversion_purchase_to_bom:
          parseDecimal(updated.conversion_purchase_to_bom) ??
          fallback?.conversion_purchase_to_bom ??
          1,
        inventory_unit: updated.inventory_unit ?? fallback?.inventory_unit,
        conversion_bom_to_inventory:
          parseDecimal(updated.conversion_bom_to_inventory) ??
          fallback?.conversion_bom_to_inventory ??
          1,
        calculation_method: updated.calculation_method ?? fallback?.calculation_method,
        local_description:
          (updatedMetadata.local_description as string) ??
          fallback?.local_description ??
          '',
      })
      lastSubmittedCostValuesRef.current = null
    },
    onError: (error) => {
      message.error(getErrorMessage(error))
    },
  })

  const handleFilterSubmit = () => {
    const values = filtersForm.getFieldsValue()
    setFilters({
      search: values.search?.trim() || undefined,
      category: values.category || undefined,
      status: values.status || undefined,
      is_active: values.onlyActive ? true : undefined,
      is_bom_material: values.onlyBom ? true : undefined,
    })
    setPagination((prev) => ({ ...prev, current: 1 }))
  }

  const handleFilterReset = () => {
    filtersForm.resetFields()
    setFilters(defaultFilters)
    setPagination({ current: 1, pageSize: 20 })
  }

  const handleTableChange = (pager: TablePaginationConfig) => {
    setPagination({
      current: pager.current ?? 1,
      pageSize: pager.pageSize ?? 20,
    })
  }

  const formatCurrency = useCallback((value?: number, currency?: string) => {
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
  }, [])

  const openMaterialDrawer = (record: Material) => {
    setEditingMaterial(record)
    setDetailDrawerOpen(true)
    const metadata = (record.metadata_json as Record<string, any>) ?? {}
    const costingDefaults = (metadata.costing_defaults ?? {}) as Record<string, any>
    const convPurchase = parseDecimal(record.conversion_purchase_to_bom)
    const inboundUnit = record.purchase_unit || ''
    // 盘点（库存）单位：按业务口径固定使用“入库单位”
    const inventoryUnit = record.purchase_unit || ''
    const derivedBomToInventory =
      inboundUnit && inventoryUnit && inboundUnit === inventoryUnit && convPurchase && convPurchase > 0
        ? Number((1 / convPurchase).toFixed(6))
        : undefined
    costForm.setFieldsValue({
      is_bom_material: getBomDisplayValue(record),
      bom_unit: normalizeBomUnit(record.unit) ?? BOM_UNIT_OPTIONS[0].value,
      conversion_purchase_to_bom: parseDecimal(record.conversion_purchase_to_bom),
      inventory_unit: record.purchase_unit || undefined,
      conversion_bom_to_inventory:
        parseDecimal(record.conversion_bom_to_inventory) ?? derivedBomToInventory ?? undefined,
      calculation_method: record.calculation_method,
      local_description: (metadata.local_description as string) ?? '',
      fixed_quantity_alpha:
        typeof costingDefaults.fixed_quantity_alpha === 'number'
          ? costingDefaults.fixed_quantity_alpha
          : parseDecimal(costingDefaults.fixed_quantity_alpha),
      coverage_ratio:
        typeof costingDefaults.coverage_ratio === 'number'
          ? costingDefaults.coverage_ratio
          : parseDecimal(costingDefaults.coverage_ratio),
      default_loss_rate:
        typeof costingDefaults.loss_rate === 'number'
          ? costingDefaults.loss_rate
          : parseDecimal(costingDefaults.loss_rate),
    })
  }

  const closeMaterialDrawer = () => {
    setDetailDrawerOpen(false)
    setGuideOpen(false)
    setEditingMaterial(null)
    costForm.resetFields()
  }

  const handleCostFormSubmit = (values: CostFormValues) => {
    if (!editingMaterial) return
    lastSubmittedCostValuesRef.current = values
    const conversionPurchase = toFiniteNumber(values.conversion_purchase_to_bom)
    const conversionInventory = toFiniteNumber(values.conversion_bom_to_inventory)
    const purchaseUnitPrice = toFiniteNumber(editingMaterial.unit_price)
    const nextIsBom =
      typeof values.is_bom_material === 'boolean'
        ? values.is_bom_material
        : getBomDisplayValue(editingMaterial)
    const payload: MaterialStatusUpdatePayload = {
      is_bom_material: nextIsBom,
      conversion_purchase_to_bom: conversionPurchase,
      conversion_bom_to_inventory: conversionInventory,
      unit: values.bom_unit || normalizeBomUnit(editingMaterial.unit),
      metadata_json: {
        local_description: values.local_description?.trim()
          ? values.local_description.trim()
          : null,
        costing_defaults: {
          fixed_quantity_alpha: toFiniteNumber(values.fixed_quantity_alpha) ?? null,
          coverage_ratio: toFiniteNumber(values.coverage_ratio) ?? null,
          loss_rate: toFiniteNumber(values.default_loss_rate) ?? null,
        },
      },
    }
    if (values.calculation_method) {
      payload.calculation_method = values.calculation_method
    }
    let bomUnitPricePayload: number | undefined
    if (purchaseUnitPrice !== undefined && conversionPurchase && conversionPurchase > 0) {
      bomUnitPricePayload = Number(purchaseUnitPrice / conversionPurchase)
    } else {
      bomUnitPricePayload = getBomUnitPrice(editingMaterial)
    }
    if (bomUnitPricePayload !== undefined) {
      payload.bom_unit_price = Number(bomUnitPricePayload)
    }
    if (values.inventory_unit && values.inventory_unit !== editingMaterial.inventory_unit) {
      payload.inventory_unit = values.inventory_unit
    }
    detailMutation.mutate({
      id: editingMaterial.id,
      payload,
    })
  }

  const handleCopyLink = (url: string) => {
    let full = toFullUrl(url)
    if (!full) {
      return
    }
    if (!/^https?:\/\//i.test(full)) {
      if (typeof window !== 'undefined' && window.location) {
        full = `${window.location.origin}${full}`
      }
    }

    if (typeof navigator !== 'undefined' && navigator?.clipboard?.writeText) {
      navigator.clipboard
        .writeText(full)
        .then(() => message.success('链接已复制'))
        .catch(() => message.error('复制失败，请手动复制'))
      return
    }
    if (typeof document === 'undefined') {
      message.warning('当前环境不支持复制')
      return
    }
    const textarea = document.createElement('textarea')
    textarea.value = full
    textarea.style.position = 'fixed'
    textarea.style.top = '-9999px'
    document.body.appendChild(textarea)
    textarea.focus()
    textarea.select()
    try {
      document.execCommand('copy')
      message.success('链接已复制')
    } catch (error) {
      console.error(error)
      message.error('复制失败，请手动复制')
    } finally {
      document.body.removeChild(textarea)
    }
  }

  const handleExport = async () => {
    setExporting(true)
    try {
      const result = await exportMaterials(filters)
      if (result.download_url) {
        window.open(result.download_url, '_blank', 'noopener')
        message.success('物料导出已开始下载')
      } else if (result.job_id) {
        message.success(`已创建导出任务：${result.job_id}`)
      } else {
        message.success(result.message || '已触发物料导出')
      }
    } catch (error) {
      const err = error as Error
      message.error(err.message || '物料导出失败，请稍后重试')
    } finally {
      setExporting(false)
    }
  }

  type MaterialSyncMode = 'full' | 'new_only' | 'core_fields'

  const confirmSyncMaterials = (mode: MaterialSyncMode) => {
    const title =
      mode === 'new_only'
        ? '同步新物料（仅新增）'
        : mode === 'core_fields'
          ? '更新原价格（关键字段）'
          : '全量同步宜搭物料'
    const content =
      mode === 'new_only'
        ? '将扫描宜搭表单，仅把“本地不存在的物料”新增进来；已存在的物料不会被更新。确认继续？'
        : mode === 'core_fields'
          ? '将扫描宜搭表单，仅更新关键字段：入库单价/单位、采购单价/单位、采购→入库换算（公式）、采购规格；不会覆盖其它主数据字段。确认继续？'
          : '将立即触发 YiDa 全量同步任务（新增+更新多数字段，raw_form_data 会全量覆盖），可能需要几分钟完成。确认继续？'
    Modal.confirm({
      title,
      content,
      okText: '立即同步',
      cancelText: '取消',
      onOk: () => handleSyncMaterials(mode),
    })
  }

  const handleSyncMaterials = async (mode: MaterialSyncMode) => {
    setSyncing(true)
    try {
      const job = await triggerMaterialSync({ requested_by: 'material_master', mode })
      message.success(
        mode === 'new_only'
          ? '已触发“同步新物料”任务'
          : mode === 'core_fields'
            ? '已触发“更新原价格”任务'
            : '已触发“全量同步宜搭”任务',
      )
      setSyncDrawerOpen(true)
      queryClient.invalidateQueries({ queryKey: ['material-sync-logs'] })

      const jobId = job?.id
      if (jobId) {
        // 等宜搭同步完成后，自动推导一次 BOM 单价快照（用于算价/扣库）
        let done = false
        for (let i = 0; i < 120; i++) {
          await new Promise((r) => setTimeout(r, 1000))
          const current = await fetchMaterialSyncJob(jobId)
          if (current?.status === 'failed') {
            message.error(current?.error_message || '宜搭同步失败，未执行 BOM 价格推导')
            done = true
            break
          }
          if (current?.status === 'succeeded' || current?.status === 'completed') {
            done = true
            const deriveJob = await triggerMaterialBomDerive({
              requested_by: 'material_master_auto',
              limit: 5000,
              search: filters.search,
              category: filters.category,
              status: filters.status,
              is_active: filters.is_active,
              is_bom_material: filters.is_bom_material,
            })
            message.success('已自动触发 BOM 价格推导任务')
            queryClient.invalidateQueries({ queryKey: ['material-sync-logs'] })
            const deriveJobId = deriveJob?.id
            if (deriveJobId) {
              for (let j = 0; j < 120; j++) {
                await new Promise((r) => setTimeout(r, 1000))
                const d = await fetchMaterialSyncJob(deriveJobId)
                if (d?.status === 'failed') {
                  message.error(d?.error_message || 'BOM 价格推导失败')
                  break
                }
                if (d?.status === 'succeeded' || d?.status === 'completed') {
                  await materialsQuery.refetch()
                  break
                }
              }
            }
            break
          }
        }
        if (!done) {
          message.info('同步任务仍在执行，可稍后手动点击“推导BOM价格”')
        }
      }
    } catch (error) {
      const err = error as Error
      message.error(err.message || '同步失败，请稍后重试')
    } finally {
      setSyncing(false)
    }
  }

  const confirmDeriveBomPrices = () => {
    Modal.confirm({
      title: '推导 BOM 价格（入库→BOM）',
      content:
        '将按“BOM 单价 = 入库单价 ÷ 入库→BOM 换算”推导并写入本地（metadata_json.bom_unit_price）。该值用于算价/扣库；无法推导的物料会清理旧的 BOM 单价快照并在列表中以红字提示原因。确认继续？',
      okText: '立即推导',
      cancelText: '取消',
      onOk: async () => {
        try {
          setSyncing(true)
          const job = await triggerMaterialBomDerive({
            requested_by: 'material_master_manual',
            limit: 5000,
            search: filters.search,
            category: filters.category,
            status: filters.status,
            is_active: filters.is_active,
            is_bom_material: filters.is_bom_material,
          })
          message.success('已触发 BOM 价格推导任务')
          setSyncDrawerOpen(true)
          queryClient.invalidateQueries({ queryKey: ['material-sync-logs'] })
          const jobId = job?.id
          if (jobId) {
            for (let i = 0; i < 120; i++) {
              await new Promise((r) => setTimeout(r, 1000))
              const current = await fetchMaterialSyncJob(jobId)
              if (current?.status === 'failed') {
                message.error(current?.error_message || 'BOM 价格推导失败')
                break
              }
              if (current?.status === 'succeeded' || current?.status === 'completed') {
                await materialsQuery.refetch()
                break
              }
            }
          }
        } catch (err: any) {
          message.error(getErrorMessage(err))
        } finally {
          setSyncing(false)
        }
      },
    })
  }

  const materialColumns: ColumnsType<Material> = [
    {
      title: '图片',
      key: 'images',
      width: 120,
      render: (_, record) => {
        const imageUrls = getImageUrls(record)
        if (!imageUrls.length) {
          return <Text type="secondary">-</Text>
        }
        const first = toFullUrl(imageUrls[0])
        return (
          <Image
            width={64}
            height={64}
            src={first}
            style={{ objectFit: 'cover', borderRadius: 6 }}
            preview={{ mask: '预览' }}
          />
        )
      },
    },
    {
      title: '物料编码',
      dataIndex: 'material_code',
      key: 'material_code',
      width: 80,
      render: (code: string) => (
        <Space>
          <Text code>{code}</Text>
        </Space>
      ),
    },
    {
      title: '名称',
      dataIndex: 'material_name',
      key: 'material_name',
      render: (text: string, record) => {
        const typeLabel = getMaterialTypeLabel(record)
        return (
          <Space direction="vertical" size={0}>
            <Text strong>{text}</Text>
            <Text type="secondary">
              {typeLabel}
              {record.category ? ` · ${record.category}` : ''}
            </Text>
          </Space>
        )
      },
    },
    {
      title: '入库单价/单位',
      key: 'unit_price',
      width: 180,
      render: (_, record) => (
        <Space direction="vertical" size={0}>
          <Text>{formatCurrency(record.unit_price, record.currency)}</Text>
          <Text type="secondary">
            {record.purchase_unit || record.unit || '-'}
          </Text>
        </Space>
      ),
    },
    {
      title: 'BOM单价/单位',
      key: 'bom_unit_price',
      width: 180,
      render: (_, record) => {
        const bomPrice = deriveBomUnitPrice(record)
        const bomUnitText = getBomUnitLabel(record.unit) ?? record.unit ?? '-'
        const issue = getBomDeriveIssue(record)
        return (
          <Space direction="vertical" size={0}>
            <Text>{formatCurrency(bomPrice, record.currency)}</Text>
            {issue ? (
              <>
                <Tooltip title={issue}>
                  <Text style={{ color: '#cf1322' }}>{bomUnitText}</Text>
                </Tooltip>
                {/* 不依赖 hover：直接把原因显示出来（更符合运营场景） */}
                <Text style={{ color: '#cf1322', fontSize: 12 }} ellipsis={{ tooltip: issue }}>
                  {issue}
                </Text>
              </>
            ) : (
              <Text type="secondary">{bomUnitText}</Text>
            )}
          </Space>
        )
      },
    },
    {
      title: '计算方式',
      dataIndex: 'calculation_method',
      key: 'calculation_method',
      width: 140,
      render: (value: string) => <Tag>{getCalculationMethodLabel(value)}</Tag>,
    },
    {
      title: 'BOM',
      dataIndex: 'bom_material',
      key: 'bom_material',
      width: 160,
      render: (_, record) => {
        const hasLocalFlag = typeof record.is_bom_material === 'boolean'
        const value = getBomDisplayValue(record)
        const isUpdating = bomMutation.isPending && bomMutation.variables?.id === record.id
        const switchNode = (
          <Switch
            size="small"
            checked={value}
            disabled={!hasLocalFlag || isUpdating}
            loading={isUpdating}
            onChange={(checked) =>
              bomMutation.mutate({ id: record.id, bom: checked, origin: 'list' })
            }
          />
        )

        if (hasLocalFlag) {
          return (
            <Space>
              {switchNode}
              <Tag color={value ? 'blue' : undefined}>{value ? '是' : '否'}</Tag>
            </Space>
          )
        }

        return (
          <Space>
            <Tooltip title="标记来自宜搭，需在编辑抽屉中开启本地开关">
              <span>{switchNode}</span>
            </Tooltip>
            <Tag>仅来自宜搭</Tag>
          </Space>
        )
      },
    },
    {
      title: '启用',
      dataIndex: 'is_active',
      key: 'is_active',
      width: 140,
      render: (_, record) => {
        const isToggling =
          statusMutation.isPending && statusMutation.variables?.id === record.id
        return (
          <Switch
            size="small"
            checkedChildren="启用"
            unCheckedChildren="停用"
            checked={record.is_active}
            loading={isToggling}
            onChange={(checked) => statusMutation.mutate({ id: record.id, active: checked })}
          />
        )
      },
    },
    {
      title: '操作',
      key: 'actions',
      width: 200,
      render: (_, record) => (
        <Space size={4} wrap>
          <Button
            type="link"
            size="small"
            icon={<FileSearchOutlined />}
            onClick={() => {
              Modal.info({
                title: `物料详情 - ${record.material_name}`,
                width: 640,
                content: (
                  <pre
                    style={{
                      maxHeight: 360,
                      overflow: 'auto',
                      background: '#f7f7f7',
                      padding: 12,
                    }}
                  >
                    {JSON.stringify(record.metadata_json ?? {}, null, 2)}
                  </pre>
                ),
              })
            }}
          >
            查看来源
          </Button>
          <Button
            type="link"
            size="small"
            icon={<EditOutlined />}
            onClick={() => openMaterialDrawer(record)}
          >
            编辑
          </Button>
        </Space>
      ),
    },
  ]

  const syncColumns: ColumnsType<MaterialSyncLog> = [
    {
      title: '批次',
      dataIndex: 'id',
      key: 'id',
      width: 200,
      render: (value: string) => <Text code>{value}</Text>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 120,
      render: (status: string) => {
        const color = status === 'completed' ? 'green' : status === 'processing' ? 'blue' : 'red'
        return <Badge color={color} text={status} />
      },
    },
    {
      title: '处理结果',
      key: 'result',
      render: (_, record) => (
        <Space size={12}>
          <span>创建 {record.created}</span>
          <span>更新 {record.updated}</span>
          <span>停用 {record.disabled}</span>
          <span>跳过 {record.skipped}</span>
        </Space>
      ),
    },
    {
      title: '耗时',
      dataIndex: 'duration_ms',
      key: 'duration_ms',
      width: 120,
      render: (value?: number) => (value ? `${(value / 1000).toFixed(1)}s` : '-'),
    },
    {
      title: '开始时间',
      dataIndex: 'started_at',
      key: 'started_at',
      width: 200,
      render: (value: string) => dayjs(value).format('YYYY-MM-DD HH:mm'),
    },
    {
      title: '结束时间',
      dataIndex: 'finished_at',
      key: 'finished_at',
      width: 200,
      render: (value?: string | null) =>
        value ? dayjs(value).format('YYYY-MM-DD HH:mm') : '-',
    },
  ]

  const renderMaterialDrawerTabs = () => {
    if (!editingMaterial) {
      return null
    }
    const virtualLinks = materialVirtualLinksQuery.data ?? []
    const imageUrls = getImageUrls(editingMaterial)
    const purchaseUnitLabel = editingMaterial.purchase_unit || '-'
    const normalizedBomUnitValue =
      watchedBomUnit || normalizeBomUnit(editingMaterial.unit) || '㎡'
    const bomUnitLabel =
      getBomUnitLabel(normalizedBomUnitValue) ?? normalizedBomUnitValue ?? '平米'
    const inventoryUnitValue =
      watchedInventoryUnit ?? editingMaterial.inventory_unit ?? ''
    const inventoryUnitDisplay = inventoryUnitValue || '库存单位'
    const livePurchaseToBom =
      toFiniteNumber(watchedConversionPurchaseToBom) ??
      parseDecimal(editingMaterial.conversion_purchase_to_bom)
    const liveBomUnitPrice =
      editingMaterial.unit_price && livePurchaseToBom
        ? Number(editingMaterial.unit_price) / livePurchaseToBom
        : deriveBomUnitPrice(editingMaterial)
    const purchaseSpec = getFormValue(editingMaterial, 'textField_lxo1y6ab')
    const costFormula = getFormValue(editingMaterial, 'textField_m3pgyx4d')
    const yidaPurchaseUnit =
      ((editingMaterial.metadata_json ?? {}) as any)?.yida_purchase_unit ||
      getFormValue(editingMaterial, 'selectField_mjjgsdlp')
    const yidaPurchaseUnitPrice =
      toFiniteNumber(((editingMaterial.metadata_json ?? {}) as any)?.yida_purchase_unit_price) ??
      parseDecimal(getFormValue(editingMaterial, 'numberField_mjjgsdlr'))
    const purchaseToInboundFormula =
      ((editingMaterial.metadata_json ?? {}) as any)?.purchase_to_inbound_formula ||
      getFormValue(editingMaterial, 'numberField_mjjgsdlq')

    return (
      <Tabs
        defaultActiveKey="basic"
        items={[
          {
            key: 'basic',
            label: '基础信息',
            children: (
              <Descriptions column={1} bordered size="small">
                <Descriptions.Item label="物料编码">
                  <Text code>{editingMaterial.material_code}</Text>
                </Descriptions.Item>
                <Descriptions.Item label="物料名称">{editingMaterial.material_name}</Descriptions.Item>
                <Descriptions.Item label="物料类型">
                  {getMaterialTypeLabel(editingMaterial)}
                </Descriptions.Item>
                <Descriptions.Item label="计算方式">
                  {getCalculationMethodLabel(editingMaterial.calculation_method)}
                </Descriptions.Item>
                <Descriptions.Item label="采购单价/单位">
                  {yidaPurchaseUnitPrice != null
                    ? `${formatCurrency(yidaPurchaseUnitPrice, editingMaterial.currency)} / ${yidaPurchaseUnit || '-'}`
                    : '-'}
                </Descriptions.Item>
                <Descriptions.Item label="采购→入库 换算">
                  {(() => {
                    if (!purchaseToInboundFormula) return '-'
                    const num = Number(purchaseToInboundFormula)
                    const val = Number.isFinite(num) ? formatDecimalDisplay(num) : String(purchaseToInboundFormula)
                    const pu = yidaPurchaseUnit || '采购单位'
                    const iu = purchaseUnitLabel || '入库单位'
                    return (
                      <Text>
                        1{pu}={val}{iu}
                      </Text>
                    )
                  })()}
                </Descriptions.Item>
                <Descriptions.Item label="入库单价/单位">
                  {formatCurrency(editingMaterial.unit_price, editingMaterial.currency)} / {purchaseUnitLabel}
                </Descriptions.Item>
                <Descriptions.Item label="入库→BOM 换算">
                  {livePurchaseToBom != null && Number.isFinite(Number(livePurchaseToBom)) ? (
                    <Text>
                      1{purchaseUnitLabel}={formatDecimalDisplay(livePurchaseToBom)}{bomUnitLabel}
                    </Text>
                  ) : (
                    '-'
                  )}
                </Descriptions.Item>
                <Descriptions.Item label="BOM单价/单位">
                  {formatCurrency(deriveBomUnitPrice(editingMaterial), editingMaterial.currency)} /{' '}
                  {getBomUnitLabel(editingMaterial.unit) ?? editingMaterial.unit ?? '-'}
                </Descriptions.Item>
                <Descriptions.Item label="采购规格">
                  {purchaseSpec || '-'}
                </Descriptions.Item>
                {editingMaterial.bom_notes ? (
                  <Descriptions.Item label="备注（宜搭）">{editingMaterial.bom_notes}</Descriptions.Item>
                ) : null}
                <Descriptions.Item label="本地描述">
                  {((editingMaterial.metadata_json ?? {}) as any)?.local_description || '-'}
                </Descriptions.Item>
                <Descriptions.Item label="最近同步">
                  {dayjs(editingMaterial.updated_at).format('YYYY-MM-DD HH:mm')}
                </Descriptions.Item>
                <Descriptions.Item label="虚拟物料引用">
                  {materialVirtualLinksQuery.isLoading ? (
                    <Spin size="small" />
                  ) : virtualLinks.length ? (
                    <Space direction="vertical" size={4}>
                      {virtualLinks.map((link) => (
                        <Tag key={link.virtual_material_id}>
                          {link.virtual_code} · {link.virtual_name}{' '}
                          <Text type="secondary">
                            （配比 {formatDecimalDisplay(link.quantity_ratio)}，损耗{' '}
                            {formatDecimalDisplay(link.loss_rate)}%）
                          </Text>
                        </Tag>
                      ))}
                    </Space>
                  ) : (
                    <Text type="secondary">暂无引用</Text>
                  )}
                </Descriptions.Item>
              </Descriptions>
            ),
          },
          {
            key: 'cost',
            label: '成本参数',
            children: (
              <Form layout="vertical" form={costForm} onFinish={handleCostFormSubmit}>
                <Row gutter={16}>
                  <Col xs={24} md={12}>
                    <Form.Item label="BOM单价/单位">
                      <Input
                        disabled
                        value={`${formatCurrency(liveBomUnitPrice, editingMaterial.currency)} / ${
                          bomUnitLabel || '-'
                        }`}
                      />
                    </Form.Item>
                  </Col>
                  <Col xs={24} md={12}>
                    <Form.Item
                      label="计算方式"
                      name="calculation_method"
                      rules={[{ required: true, message: '请选择计算方式' }]}
                    >
                      <Select
                        placeholder="请选择计算方式"
                        options={CALCULATION_METHOD_OPTIONS.map((item) => ({
                          label: item.label,
                          value: item.value,
                        }))}
                        onChange={(value) => {
                          const defaultUnit = getDefaultUnitByCalculationMethod(value)
                          if (defaultUnit) {
                            costForm.setFieldsValue({ bom_unit: defaultUnit })
                          }
                        }}
                      />
                    </Form.Item>
                  </Col>
                </Row>
                {(purchaseSpec || costFormula) && (
                  <div style={{ marginBottom: 8 }}>
                    <Row gutter={16}>
                      <Col xs={24} md={12}>
                        {purchaseSpec ? (
                          <Form.Item label="采购规格" style={{ marginBottom: 8 }}>
                            <Input.TextArea value={purchaseSpec} autoSize disabled />
                          </Form.Item>
                        ) : null}
                      </Col>
                      <Col xs={24} md={12}>
                        <Form.Item label="入库单价/单位" style={{ marginBottom: 8 }}>
                          <Input
                            disabled
                            value={`${formatCurrency(editingMaterial.unit_price, editingMaterial.currency)} / ${
                              editingMaterial.purchase_unit || '-'
                            }`}
                          />
                        </Form.Item>
                      </Col>
                    </Row>
                    {costFormula && (
                      <Form.Item label="成本计算公式（只读）" style={{ marginBottom: 8 }}>
                        <Input.TextArea value={costFormula} autoSize disabled />
                      </Form.Item>
                    )}
                  </div>
                )}
                <Row gutter={16}>
                  <Col xs={24} md={12}>
                    <Form.Item
                      label={`入库→BOM 换算（1 ${purchaseUnitLabel} = ? ${bomUnitLabel}）`}
                      name="conversion_purchase_to_bom"
                      rules={[
                        { required: true, message: '请输入入库→BOM 换算系数' },
                        positiveNumberRule('换算系数必须大于 0'),
                      ]}
                    >
                      <InputNumber min={0.000001} step={0.0001} style={{ width: '100%' }} />
                    </Form.Item>
                  </Col>
                  <Col xs={24} md={12}>
                    <Form.Item
                      label="BOM 单位"
                      name="bom_unit"
                      rules={[{ required: true, message: '请选择 BOM 单位' }]}
                    >
                      <Select options={BOM_UNIT_OPTIONS} placeholder="请选择 BOM 单位" />
                    </Form.Item>
                  </Col>
                </Row>
                <Row gutter={16}>
                  <Col xs={24} md={12}>
                    <Form.Item
                      label={`BOM→库存换算（1 ${bomUnitLabel} = ? ${inventoryUnitDisplay}）`}
                      name="conversion_bom_to_inventory"
                      rules={[
                        { required: true, message: '请输入 BOM→库存 换算系数' },
                        positiveNumberRule('换算系数必须大于 0'),
                      ]}
                    >
                      <InputNumber disabled min={0.000001} step={0.0001} style={{ width: '100%' }} />
                    </Form.Item>
                  </Col>
                  <Col xs={24} md={12}>
                    <Form.Item
                      label="库存单位"
                      name="inventory_unit"
                    >
                      <Input disabled />
                    </Form.Item>
                  </Col>
                </Row>
                <Form.Item label="是否 BOM 物料" name="is_bom_material" valuePropName="checked">
                  <Switch />
                </Form.Item>
                <Form.Item
                  label="本地描述"
                  name="local_description"
                >
                  <Input.TextArea
                    rows={3}
                    placeholder="记录该物料的本地补充说明，如物性、注意事项等"
                  />
                </Form.Item>
                <Card
                  size="small"
                  title="成本默认参数（用于产品模型自动带入）"
                  style={{ marginBottom: 16 }}
                >
                  <Row gutter={16}>
                    <Col xs={24} md={8}>
                      <Form.Item
                        label="固定用量 α"
                        name="fixed_quantity_alpha"
                        extra="起步耗材/边料等（不随尺寸变化）。默认 0"
                      >
                        <InputNumber min={0} step={0.0001} style={{ width: '100%' }} />
                      </Form.Item>
                    </Col>
                    <Col xs={24} md={8}>
                      <Form.Item
                        label="覆盖率 r (0~1)"
                        name="coverage_ratio"
                        extra="局部材料占比/走线占比。默认 1"
                      >
                        <InputNumber min={0} max={1} step={0.01} style={{ width: '100%' }} />
                      </Form.Item>
                    </Col>
                    <Col xs={24} md={8}>
                      <Form.Item
                        label="默认损耗%"
                        name="default_loss_rate"
                        extra="模型引用该物料时建议的损耗%（可被模型覆盖）"
                      >
                        <InputNumber min={0} max={100} step={0.1} style={{ width: '100%' }} />
                      </Form.Item>
                    </Col>
                  </Row>
                  <Alert
                    type="info"
                    showIcon
                    message="说明"
                    description="这些参数会写入 metadata_json.costing_defaults。产品模型中选择/替换该物料时，会自动带入 α/覆盖率/损耗（若模型行仍处于默认值）。"
                  />
                </Card>
              </Form>
            ),
          },
          {
            key: 'images',
            label: '图片/附件',
            children: imageUrls.length ? (
              <PreviewGroup>
                <Space size={16} wrap>
                  {imageUrls.map((img) => {
                    const full = toFullUrl(img)
                    return (
                      <div key={img} style={{ textAlign: 'center' }}>
                        <Image
                          width={150}
                          height={150}
                          src={full}
                          style={{ objectFit: 'cover', borderRadius: 8 }}
                        />
                        <Button
                          size="small"
                          type="link"
                          icon={<CopyOutlined />}
                          onClick={() => handleCopyLink(img)}
                        >
                          复制链接
                        </Button>
                      </div>
                    )
                  })}
                </Space>
              </PreviewGroup>
            ) : (
              <Empty description="暂无图片" />
            ),
          },
        ]}
      />
    )
  }

  return (
    <Space direction="vertical" size={24} style={{ width: '100%' }}>
      <div>
        <Title level={3} style={{ marginBottom: 4 }}>
          物料主数据管理
        </Title>
        <Text type="secondary">
          管理物料主数据、同步 YiDa 原始表单，支持启用状态管控与导出，为工序和模型配置提供一致的数据底座。
        </Text>
      </div>

      <Row gutter={[24, 24]}>
        <Col xs={24} xl={7} style={{ display: 'flex' }}>
          <Card
            title="当前概览"
            bordered={false}
            style={{ flex: 1, minHeight: '100%' }}
            bodyStyle={{
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'center',
              gap: 12,
            }}
          >
            <Text strong style={{ fontSize: 16 }}>
              物料总数：{totalCount}
            </Text>
            <Text type="secondary">统计所有同步的物料数量</Text>
          </Card>
        </Col>
        <Col xs={24} xl={17} style={{ display: 'flex' }}>
          <Card
            title="筛选"
            bordered={false}
            style={{ flex: 1 }}
            extra={
              <Space>
                <Button icon={<ReloadOutlined />} onClick={() => materialsQuery.refetch()}>
                  刷新
                </Button>
                <Button loading={syncing} onClick={confirmDeriveBomPrices}>
                  推导BOM价格
                </Button>
                <Button
                  icon={<CloudSyncOutlined />}
                  loading={syncing}
                  onClick={() => confirmSyncMaterials('new_only')}
                >
                  同步新物料
                </Button>
                <Button
                  icon={<CloudSyncOutlined />}
                  loading={syncing}
                  onClick={() => confirmSyncMaterials('core_fields')}
                >
                  更新原价格
                </Button>
                <Button
                  icon={<CloudSyncOutlined />}
                  loading={syncing}
                  onClick={() => confirmSyncMaterials('full')}
                >
                  全量同步宜搭
                </Button>
                <Button icon={<HistoryOutlined />} onClick={() => setSyncDrawerOpen(true)}>
                  同步日志
                </Button>
                <Button
                  type="primary"
                  icon={<DownloadOutlined />}
                  loading={exporting}
                  onClick={handleExport}
                >
                  导出
                </Button>
              </Space>
            }
          >
            <Form
              form={filtersForm}
              layout="inline"
              initialValues={{ onlyActive: true, onlyBom: true }}
              onFinish={handleFilterSubmit}
            >
              <Form.Item name="search" label="关键词">
                <Input.Search
                  placeholder="物料编码 / 名称"
                  allowClear
                  onSearch={handleFilterSubmit}
                  style={{ width: 220 }}
                />
              </Form.Item>
              <Form.Item name="category" label="分类">
                <Select
                  allowClear
                  placeholder="全部"
                  options={categoryOptions}
                  style={{ width: 160 }}
                  showSearch
                  optionFilterProp="label"
                />
              </Form.Item>
              <Form.Item name="status" label="状态">
                <Select
                  allowClear
                  placeholder="全部"
                  options={MATERIAL_STATUS_OPTIONS}
                  style={{ width: 120 }}
                />
              </Form.Item>
              <Form.Item name="onlyActive" valuePropName="checked" label="仅启用">
                <Switch />
              </Form.Item>
              <Form.Item name="onlyBom" valuePropName="checked" label="仅 BOM 物料">
                <Switch />
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
        </Col>
      </Row>

      <Card>
        <Table<Material>
          rowKey="id"
          columns={materialColumns}
          dataSource={materials}
          loading={materialsQuery.isLoading}
          pagination={{
            current: pagination.current,
            pageSize: pagination.pageSize,
            total: totalCount,
            showSizeChanger: true,
            showTotal: (total) => `共 ${total} 条`,
          }}
          onChange={handleTableChange}
        />
      </Card>

      <Drawer
        title={editingMaterial ? `物料详情 - ${editingMaterial.material_name}` : '物料详情'}
        width={720}
        open={detailDrawerOpen}
        destroyOnClose
        onClose={closeMaterialDrawer}
        extra={
          editingMaterial ? (
            <Space>
              <Button type="primary" loading={detailMutation.isPending} onClick={() => costForm.submit()}>
                保存
              </Button>
              <Button icon={<QuestionCircleOutlined />} onClick={() => setGuideOpen(true)}>
                新建指南
              </Button>
              <Button onClick={closeMaterialDrawer}>取消</Button>
              <Button
                icon={<CloudSyncOutlined />}
                loading={syncing}
                onClick={async () => {
                  try {
                    const job = await triggerMaterialSync({
                      requested_by: 'material_drawer',
                      limit: 5000,
                      material_codes: [editingMaterial.material_code],
                    })
                    message.success('已触发同步任务，正在刷新…')
                    const jobId = job?.id
                    if (jobId) {
                      for (let i = 0; i < 20; i++) {
                        await new Promise((r) => setTimeout(r, 1000))
                        const current = await fetchMaterialSyncJob(jobId)
                        if (current?.status === 'succeeded' || current?.status === 'completed') {
                          break
                        }
                        if (current?.status === 'failed') {
                          message.error(current?.error_message || '同步失败')
                          break
                        }
                      }
                    }
                    await materialsQuery.refetch()
                    if (editingMaterial?.id) {
                      const refreshed = await fetchMaterials({
                        search: editingMaterial.material_code,
                        page: 1,
                        page_size: 1,
                      })
                      const hit = refreshed?.items?.[0]
                      if (hit) {
                        setEditingMaterial(hit)
                      }
                    }
                  } catch (err: any) {
                    message.error(getErrorMessage(err))
                  }
                }}
              >
                同步宜搭
              </Button>
            </Space>
          ) : null
        }
      >
        {editingMaterial && renderMaterialDrawerTabs()}
      </Drawer>

      <GuideDrawer
        open={guideOpen}
        onClose={() => setGuideOpen(false)}
        title="真实物料（物料主数据）新建指南"
        content={materialsGuide}
        tip="提示：这是“真实物料/物料主数据”面板的新建/维护指南（Markdown）。需要调整内容，直接修改对应指南文档并重新部署即可。"
      />

      <Drawer
        title="物料同步日志"
        width={860}
        open={syncDrawerOpen}
        onClose={() => setSyncDrawerOpen(false)}
        destroyOnClose
      >
        <Table<MaterialSyncLog>
          rowKey="id"
          columns={syncColumns}
          dataSource={syncLogsQuery.data?.items ?? []}
          loading={syncLogsQuery.isLoading}
          pagination={{
            current: syncPagination.page,
            pageSize: syncPagination.pageSize,
            total: syncLogsQuery.data?.total ?? 0,
            showSizeChanger: true,
            showTotal: (total) => `共 ${total} 条`,
          }}
          locale={{
            emptyText: syncLogsQuery.isLoading ? (
              <Empty description="加载中..." />
            ) : (
              <Empty description="暂无同步记录" />
            ),
          }}
          onChange={(pager) =>
            setSyncPagination({
              page: pager.current ?? 1,
              pageSize: pager.pageSize ?? 10,
            })
          }
        />
      </Drawer>
    </Space>
  )
}

export default MaterialMasterPage

