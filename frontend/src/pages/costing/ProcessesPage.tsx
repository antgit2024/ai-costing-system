import CheckCircleOutlined from '@ant-design/icons/lib/icons/CheckCircleOutlined'
import CopyOutlined from '@ant-design/icons/lib/icons/CopyOutlined'
import EditOutlined from '@ant-design/icons/lib/icons/EditOutlined'
import PlusOutlined from '@ant-design/icons/lib/icons/PlusOutlined'
import QuestionCircleOutlined from '@ant-design/icons/lib/icons/QuestionCircleOutlined'
import ReloadOutlined from '@ant-design/icons/lib/icons/ReloadOutlined'
import StopOutlined from '@ant-design/icons/lib/icons/StopOutlined'
import DeleteOutlined from '@ant-design/icons/lib/icons/DeleteOutlined'
import EyeOutlined from '@ant-design/icons/lib/icons/EyeOutlined'
import RobotOutlined from '@ant-design/icons/lib/icons/RobotOutlined'
import {
  Button,
  Card,
  Form as AntForm,
  Drawer,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Radio,
  Select,
  Space,
  Table,
  Tag,
  Tooltip,
  Divider,
  Collapse,
  Typography,
  message,
} from 'antd'
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table'
import dayjs from 'dayjs'
import { useEffect, useMemo, useState } from 'react'
import { keepPreviousData, useMutation, useQuery } from '@tanstack/react-query'
import { isAxiosError } from 'axios'
import { normalizeUnit } from '@/utils/unit'
import GuideDrawer from '@/components/common/GuideDrawer'

import {
  activateProcess,
  copyProcess,
  createProcess,
  deleteProcess,
  deactivateProcess,
  fetchProcesses,
  fetchTaxonomyItems,
  generateNextCode,
  updateProcess,
} from '@/services/planner'
import type {
  ProcessChargingMode,
  ProcessCopyPayload,
  ProcessCreatePayload,
  ProcessListResponse,
  ProcessQueryParams,
  ProcessSummary,
  ProcessUpdatePayload,
} from '@/types/planner'
import processCreateGuide from '@/guides/process_create_guide.md?raw'

const { Text, Title } = Typography

type ProcessCostType = 'time' | 'piece'

const PROCESS_STATUS_OPTIONS = [
  { label: '草稿', value: 'draft' },
  { label: '启用', value: 'active' },
  { label: '停用', value: 'inactive' },
]

// 班组在工艺模块（工艺模板）的工序行维护；工序管理不承载班组字段

const CHARGING_MODE_OPTIONS: Array<{ label: string; value: ProcessChargingMode }> = [
  { label: '面积', value: 'area' },
  { label: '周长', value: 'perimeter' },
  { label: '数量', value: 'count' },
  { label: '宽度', value: 'width' },
  { label: '高度', value: 'height' },
  { label: '长边', value: 'long_side' },
  { label: '短边', value: 'short_side' },
]

const chargingModeToUnit = (mode?: ProcessChargingMode | null): '平米' | '米' | '个' => {
  if (mode === 'area') return '平米'
  if (mode === 'perimeter' || mode === 'width' || mode === 'height' || mode === 'long_side' || mode === 'short_side') return '米'
  // fixed/count fallback
  return '个'
}

const chargingModeLabel = (mode?: string | null): string => {
  const v = String(mode ?? '').trim()
  const hit = CHARGING_MODE_OPTIONS.find((x) => x.value === (v as any))
  return hit?.label ?? (v || '-')
}

/**
 * 【单位口径-禁止随意改动】
 * 本项目统一单位口径以 `frontend/src/utils/unit.ts` 的 `normalizeUnit()` 为准：
 * - 面积：平米
 * - 长度：米
 * - 数量：个
 * - 套装：套
 *
 * 这里的 Select 选项必须与 normalizeUnit 的返回值一致，否则会出现“编辑时回显为空/掉值”的历史问题。
 * ❌ 不要改回 `㎡/m` 作为 value（显示可以写“平米（㎡）/米（m）”，但 value 必须是“平米/米/个/套”）。
 */
// NOTE: 计量单位由“计量类型(charging_mode)”自动推导，不再由用户在工序库维护。

const fallbackProcessCode = () => {
  const suffix = String(Date.now() % 100000).padStart(5, '0')
  return `PR${suffix}`
}

const safeNumber = (value: unknown): number | undefined => {
  const num = Number(value)
  return Number.isFinite(num) ? num : undefined
}

const getProcessCostType = (record: ProcessSummary): ProcessCostType => {
  const meta = (record.metadata_json ?? {}) as any
  const explicit = meta?.cost_type as ProcessCostType | undefined
  if (explicit === 'time' || explicit === 'piece') return explicit
  // best-effort fallback for legacy records
  if (record.charging_mode === 'fixed') return 'time'
  return 'piece'
}

// 列表里不展示“计价参数”明细（避免造成误解；工价由班组在工艺模块步骤行维护）

const ProcessesPage = () => {
  const [filters, setFilters] = useState<ProcessQueryParams>({ page: 1, page_size: 20 })
  const [filtersForm] = AntForm.useForm()
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [drawerMode, setDrawerMode] = useState<'create' | 'edit' | 'view'>('create')
  const [selected, setSelected] = useState<ProcessSummary | null>(null)
  const [pendingFormValues, setPendingFormValues] = useState<Record<string, unknown> | null>(null)
  // 工序编码改为“保存时后端生成”，避免打开抽屉就消耗编码
  const [copyModalOpen, setCopyModalOpen] = useState(false)
  const [copySource, setCopySource] = useState<ProcessSummary | null>(null)
  const [guideOpen, setGuideOpen] = useState(false)
  const [aiPanelOpen, setAiPanelOpen] = useState(false)

  const [form] = Form.useForm<
    ProcessCreatePayload & {
      id?: string
      cost_type?: ProcessCostType
      base_minutes?: number
      unit_minutes?: number
      rate_per_minute?: number
      piece_rate?: number
      standard_time_minutes?: number
      ai_intent?: string
      ai_inputs?: string
      ai_outputs?: string
      ai_quality_points?: string
      ai_constraints?: string
      ai_tools?: string
      ai_parameter_schema_json?: string
    }
  >()
  const [copyForm] = Form.useForm<ProcessCopyPayload>()

  const listQuery = useQuery<ProcessListResponse>({
    queryKey: ['processes', filters],
    queryFn: () => fetchProcesses(filters),
    placeholderData: keepPreviousData,
  })

  const taxonomyCategoriesQuery = useQuery({
    queryKey: ['taxonomy-items', 'process_category'],
    queryFn: () => fetchTaxonomyItems('process_category', { include_inactive: false }),
  })

  const categoryOptions = useMemo(() => {
    const base = new Map<string, string>()
    const active = new Set<string>()
    for (const it of taxonomyCategoriesQuery.data?.items ?? []) {
      const name = String((it as any)?.name ?? '').trim()
      if (!name) continue
      const isActive = (it as any)?.is_active !== false
      if (!isActive) continue
      active.add(name)
      base.set(name, name)
    }
    // 仅兜底：如果历史数据里有分类，但 taxonomy 里已启用同名分类，则允许显示；停用/不存在的不显示（按用户口径）。
    for (const it of listQuery.data?.items ?? []) {
      const c = String(it.category ?? '').trim()
      if (c && active.has(c)) base.set(c, c)
    }
    return Array.from(base.entries()).map(([value, label]) => ({ value, label }))
  }, [listQuery.data?.items, taxonomyCategoriesQuery.data?.items])

  const processTagOptions = useMemo(() => {
    const base = new Map<string, string>()
    // 默认快捷：画艺/布艺（仍可扩展）
    for (const s of ['画艺', '布艺']) base.set(s, s)
    for (const it of listQuery.data?.items ?? []) {
      const tags = ((it.metadata_json as any)?.process_tags ?? []) as any
      if (!Array.isArray(tags)) continue
      for (const t of tags) {
        const name = String(t ?? '').trim()
        if (name) base.set(name, name)
      }
    }
    return Array.from(base.entries()).map(([value, label]) => ({ value, label }))
  }, [listQuery.data?.items])

  const createMutation = useMutation({
    mutationFn: (payload: ProcessCreatePayload) => createProcess(payload),
    onSuccess: () => {
      message.success('已创建')
      setDrawerOpen(false)
      listQuery.refetch()
    },
    onError: (error) => {
      if (isAxiosError(error)) {
        message.error(error.response?.data?.detail ?? error.message)
        return
      }
      message.error('创建失败')
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: ProcessUpdatePayload }) =>
      updateProcess(id, payload),
    onSuccess: () => {
      message.success('已保存')
      setDrawerOpen(false)
      listQuery.refetch()
    },
    onError: (error) => {
      if (isAxiosError(error)) {
        message.error(error.response?.data?.detail ?? error.message)
        return
      }
      message.error('保存失败')
    },
  })

  const activateMutation = useMutation({
    mutationFn: (id: string) => activateProcess(id),
    onSuccess: () => {
      message.success('已启用')
      listQuery.refetch()
    },
    onError: () => message.error('启用失败'),
  })

  const deactivateMutation = useMutation({
    mutationFn: (id: string) => deactivateProcess(id),
    onSuccess: () => {
      message.success('已停用')
      listQuery.refetch()
    },
    onError: () => message.error('停用失败'),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteProcess(id),
    onSuccess: () => {
      message.success('已删除（归档）')
      listQuery.refetch()
    },
    onError: (error) => {
      if (isAxiosError(error)) {
        message.error(error.response?.data?.detail ?? error.message)
        return
      }
      message.error('删除失败')
    },
  })

  const copyMutation = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: ProcessCopyPayload }) =>
      copyProcess(id, payload),
    onSuccess: () => {
      message.success('已复制')
      setCopyModalOpen(false)
      listQuery.refetch()
    },
    onError: (error) => {
      if (isAxiosError(error)) {
        message.error(error.response?.data?.detail ?? error.message)
        return
      }
      message.error('复制失败')
    },
  })

  const pagination = useMemo<TablePaginationConfig>(
    () => ({
      current: filters.page ?? 1,
      pageSize: filters.page_size ?? 20,
      total: listQuery.data?.total ?? 0,
      showSizeChanger: true,
      pageSizeOptions: [10, 20, 50, 100],
      onChange: (page, pageSize) =>
        setFilters((prev) => ({
          ...prev,
          page,
          page_size: pageSize,
        })),
    }),
    [filters.page, filters.page_size, listQuery.data?.total],
  )

  const openCreate = () => {
    setAiPanelOpen(false)
    setDrawerMode('create')
    setSelected(null)
    // Drawer 使用 destroyOnClose，Form 也设置了 preserve={false}：
    // 必须在 Drawer 打开且 Form 挂载后再回填，否则会出现“编辑/新建掉值”。
    form.resetFields()
    setPendingFormValues({
      process_code: '',
      cost_type: 'time',
      charging_mode: 'count',
      status: 'draft',
      unit_of_measure: '个',
    })
    setDrawerOpen(true)
  }

  const openView = (record: ProcessSummary) => {
    setAiPanelOpen(false)
    setDrawerMode('view')
    setSelected(record)
    form.resetFields()
    const meta = (record.metadata_json ?? {}) as any
    const ai = (meta?.ai_spec ?? {}) as any
    const costType = getProcessCostType(record)
    setPendingFormValues({
      id: record.id,
      process_code: record.process_code,
      process_name: record.process_name,
      description: record.description ?? undefined,
      category: record.category ?? undefined,
      cost_type: costType,
      base_minutes: safeNumber(meta?.base_minutes),
      unit_minutes: safeNumber(meta?.unit_minutes),
      rate_per_minute: safeNumber(meta?.rate_per_minute),
      piece_rate: safeNumber(meta?.piece_rate) ?? safeNumber(record.standard_rate),
      charging_mode: record.charging_mode,
      standard_rate: safeNumber(record.standard_rate),
      unit_of_measure: normalizeUnit(record.unit_of_measure) || undefined,
      status: record.status,
      standard_time_minutes: safeNumber((record.metadata_json as any)?.standard_time_minutes),
      process_tags: Array.isArray((record.metadata_json as any)?.process_tags) ? (record.metadata_json as any).process_tags : [],
      ai_intent: String(ai?.intent ?? record.description ?? ''),
      ai_inputs: String(ai?.inputs ?? ''),
      ai_outputs: String(ai?.outputs ?? ''),
      ai_quality_points: String(ai?.quality_points ?? ''),
      ai_constraints: String(ai?.constraints ?? ''),
      ai_tools: String(ai?.tools ?? ''),
      ai_parameter_schema_json: ai?.parameter_schema ? JSON.stringify(ai?.parameter_schema, null, 2) : '',
    })
    setDrawerOpen(true)
  }

  const openEdit = (record: ProcessSummary) => {
    setAiPanelOpen(false)
    setDrawerMode('edit')
    setSelected(record)
    form.resetFields()
    const meta = (record.metadata_json ?? {}) as any
    const ai = (meta?.ai_spec ?? {}) as any
    const costType = getProcessCostType(record)
    setPendingFormValues({
      id: record.id,
      process_code: record.process_code,
      process_name: record.process_name,
      description: record.description ?? undefined,
      category: record.category ?? undefined,
      cost_type: costType,
      base_minutes: safeNumber(meta?.base_minutes),
      unit_minutes: safeNumber(meta?.unit_minutes),
      rate_per_minute: safeNumber(meta?.rate_per_minute),
      piece_rate: safeNumber(meta?.piece_rate) ?? safeNumber(record.standard_rate),
      charging_mode: record.charging_mode,
      standard_rate: safeNumber(record.standard_rate),
      unit_of_measure: normalizeUnit(record.unit_of_measure) || undefined,
      status: record.status,
      standard_time_minutes: safeNumber((record.metadata_json as any)?.standard_time_minutes),
      process_tags: Array.isArray((record.metadata_json as any)?.process_tags) ? (record.metadata_json as any).process_tags : [],
      ai_intent: String(ai?.intent ?? record.description ?? ''),
      ai_inputs: String(ai?.inputs ?? ''),
      ai_outputs: String(ai?.outputs ?? ''),
      ai_quality_points: String(ai?.quality_points ?? ''),
      ai_constraints: String(ai?.constraints ?? ''),
      ai_tools: String(ai?.tools ?? ''),
      ai_parameter_schema_json: ai?.parameter_schema ? JSON.stringify(ai?.parameter_schema, null, 2) : '',
    })
    setDrawerOpen(true)
  }

  const openAiEdit = (record: ProcessSummary) => {
    setAiPanelOpen(true)
    setDrawerMode('edit')
    setSelected(record)
    form.resetFields()
    const meta = (record.metadata_json ?? {}) as any
    const ai = (meta?.ai_spec ?? {}) as any
    const costType = getProcessCostType(record)
    setPendingFormValues({
      id: record.id,
      process_code: record.process_code,
      process_name: record.process_name,
      description: record.description ?? undefined,
      category: record.category ?? undefined,
      cost_type: costType,
      base_minutes: safeNumber(meta?.base_minutes),
      unit_minutes: safeNumber(meta?.unit_minutes),
      rate_per_minute: safeNumber(meta?.rate_per_minute),
      piece_rate: safeNumber(meta?.piece_rate) ?? safeNumber(record.standard_rate),
      charging_mode: record.charging_mode,
      standard_rate: safeNumber(record.standard_rate),
      unit_of_measure: normalizeUnit(record.unit_of_measure) || undefined,
      status: record.status,
      standard_time_minutes: safeNumber((record.metadata_json as any)?.standard_time_minutes),
      process_tags: Array.isArray((record.metadata_json as any)?.process_tags) ? (record.metadata_json as any).process_tags : [],
      ai_intent: String(ai?.intent ?? record.description ?? ''),
      ai_inputs: String(ai?.inputs ?? ''),
      ai_outputs: String(ai?.outputs ?? ''),
      ai_quality_points: String(ai?.quality_points ?? ''),
      ai_constraints: String(ai?.constraints ?? ''),
      ai_tools: String(ai?.tools ?? ''),
      ai_parameter_schema_json: ai?.parameter_schema ? JSON.stringify(ai?.parameter_schema, null, 2) : '',
    })
    setDrawerOpen(true)
  }

  const openCopy = (record: ProcessSummary) => {
    setCopySource(record)
    copyForm.resetFields()
    copyForm.setFieldsValue({
      process_code: fallbackProcessCode(),
      process_name: `${record.process_name}（复制）`,
      status: record.status,
    })
    generateNextCode({ prefix: 'PR', width: 5 })
      .then((res) => {
        copyForm.setFieldValue('process_code', res.code)
      })
      .catch(() => {
        // keep fallback
    })
    setCopyModalOpen(true)
  }

  const handleSubmit = async () => {
    const values = await form.validateFields()
    const baseMetadata =
      drawerMode === 'create'
        ? {}
        : ((selected?.metadata_json ?? {}) as Record<string, unknown>)
    const metadata = { ...baseMetadata }
    if (values.standard_time_minutes === undefined || values.standard_time_minutes === null) {
      delete metadata.standard_time_minutes
    } else {
      metadata.standard_time_minutes = values.standard_time_minutes
    }

    // 工序标签（非必填）：写入 metadata_json.process_tags
    const rawTags = (values as any).process_tags
    const tags = Array.isArray(rawTags)
      ? Array.from(new Set(rawTags.map((x: any) => String(x ?? '').trim()).filter(Boolean)))
      : []
    if (tags.length) {
      ;(metadata as any).process_tags = tags
    } else {
      delete (metadata as any).process_tags
    }

    // AI 语义字段（可选）：写入 metadata_json.ai_spec
    const ai_spec: any = {}
    const s = (v: any) => String(v ?? '').trim()
    // 自动兜底：如果未填写 AI 意图，则用“描述”作为默认意图（用户保存后固化）
    const intentValue = s(values.ai_intent) || s(values.description)
    if (intentValue) ai_spec.intent = intentValue
    if (s(values.ai_inputs)) ai_spec.inputs = s(values.ai_inputs)
    if (s(values.ai_outputs)) ai_spec.outputs = s(values.ai_outputs)
    if (s(values.ai_quality_points)) ai_spec.quality_points = s(values.ai_quality_points)
    if (s(values.ai_constraints)) ai_spec.constraints = s(values.ai_constraints)
    if (s(values.ai_tools)) ai_spec.tools = s(values.ai_tools)
    const rawSchema = s(values.ai_parameter_schema_json)
    if (rawSchema) {
      try {
        ai_spec.parameter_schema = JSON.parse(rawSchema)
      } catch {
        message.error('AI参数模板必须是合法 JSON')
        return
      }
    }
    if (Object.keys(ai_spec).length) {
      ;(metadata as any).ai_spec = ai_spec
    } else {
      delete (metadata as any).ai_spec
    }

    const costType = (values.cost_type ?? 'piece') as ProcessCostType
    const chargingMode = (values.charging_mode ?? 'count') as ProcessChargingMode
    const measureUnit = chargingModeToUnit(chargingMode)
    const unitOfMeasure = measureUnit

    // keep both sets of fields in metadata; only validate the active one
    metadata.cost_type = costType
    metadata.base_minutes = values.base_minutes ?? safeNumber((metadata as any).base_minutes) ?? 0
    metadata.unit_minutes = values.unit_minutes ?? safeNumber((metadata as any).unit_minutes) ?? 0
    metadata.measure_unit = measureUnit
    metadata.rate_per_minute = values.rate_per_minute ?? safeNumber((metadata as any).rate_per_minute) ?? 0
    metadata.piece_rate = values.piece_rate ?? safeNumber((metadata as any).piece_rate) ?? 0

    let standardRate: number | undefined
    if (costType === 'time') {
      standardRate = values.rate_per_minute ?? undefined
    } else {
      standardRate = values.piece_rate ?? undefined
      if (values.status === 'active' && !standardRate) {
        message.error('启用状态下：计件工序必须配置“计件单价”')
        return
      }
    }

    if (drawerMode === 'create') {
      const payload: ProcessCreatePayload = {
        process_code: values.process_code,
        process_name: values.process_name,
        description: values.description,
        category: values.category,
        charging_mode: chargingMode,
        standard_rate: standardRate,
        unit_of_measure: unitOfMeasure,
        status: values.status,
        metadata_json: metadata,
      }
      createMutation.mutate(payload)
      return
    }

    if (!selected?.id) {
      message.error('缺少工序 ID')
      return
    }
    const payload: ProcessUpdatePayload = {
      process_name: values.process_name,
      description: values.description,
      category: values.category,
      charging_mode: chargingMode,
      standard_rate: standardRate,
      unit_of_measure: unitOfMeasure,
      status: values.status,
      metadata_json: metadata,
    }
    updateMutation.mutate({ id: selected.id, payload })
  }

  const columns: ColumnsType<ProcessSummary> = [
    {
      title: '编码',
      dataIndex: 'process_code',
      width: 80,
      render: (value: string) => <Text code>{value}</Text>,
    },
    {
      title: '工序',
      key: 'process_info',
      width: 260,
      render: (_: any, r: ProcessSummary) => {
        const tagsRaw = ((r.metadata_json as any)?.process_tags ?? []) as any
        const tags = Array.isArray(tagsRaw)
          ? tagsRaw.map((x: any) => String(x ?? '').trim()).filter(Boolean)
          : []
        const category = (r.category ?? '').trim() || '-'
        const chargingMode = chargingModeLabel(r.charging_mode)
        const unit = chargingModeToUnit(r.charging_mode as any)

        return (
          <div style={{ lineHeight: 1.25 }}>
            <div>
              <Text strong ellipsis={{ tooltip: r.process_name }}>
                {r.process_name}
              </Text>
            </div>
            <div style={{ marginTop: 4 }}>
              <Space size={6} wrap>
                <Text type="secondary">
                  分类：{category}；计量类型：{chargingMode}；单位：{unit}
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
      title: '类型/工时',
      key: 'costing_and_hours',
      width: 170,
      render: (_: any, r: ProcessSummary) => {
        const meta = (r.metadata_json ?? {}) as any
        const base = safeNumber(meta?.base_minutes) ?? 0
        const unit = safeNumber(meta?.unit_minutes) ?? 0
        const pieceRate = safeNumber(meta?.piece_rate) ?? safeNumber(r.standard_rate) ?? 0

        const primary = getProcessCostType(r) // 'time' | 'piece'
        const primaryLabel = primary === 'time' ? '计时' : '计件'
        const secondLine =
          primary === 'time' ? `${base}分钟+${unit}分钟` : pieceRate ? `${pieceRate}元/件` : '-'

        return (
          <div style={{ lineHeight: 1.25 }}>
            <div>
              <Text>{primaryLabel}</Text>
            </div>
            <div style={{ marginTop: 4 }}>
              <Text type="secondary">{secondLine}</Text>
            </div>
          </div>
        )
      },
    },
    {
      title: '描述',
      dataIndex: 'description',
      width: 390,
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
      width: 150,
      render: (value: string) => dayjs(value).format('YYYY-MM-DD HH:mm'),
    },
    {
      title: '操作',
      key: 'actions',
      width: 160,
      render: (_, record) => (
        <Space size={4} wrap>
          <Tooltip title="查看">
            <Button size="small" icon={<EyeOutlined />} onClick={() => openView(record)} />
          </Tooltip>
          <Tooltip title="编辑">
            <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(record)} />
          </Tooltip>
          <Tooltip title="AI">
            <Button size="small" icon={<RobotOutlined />} onClick={() => openAiEdit(record)} />
          </Tooltip>
          <Tooltip title="复制">
            <Button size="small" icon={<CopyOutlined />} onClick={() => openCopy(record)} />
          </Tooltip>
          {record.status === 'active' ? (
            <Popconfirm
              title="确认停用该工序？"
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
              <Tooltip title="启用">
                <Button size="small" type="primary" icon={<CheckCircleOutlined />} onClick={() => activateMutation.mutate(record.id)} />
              </Tooltip>
              <Popconfirm
                title="确认删除该工序？"
                description="删除为归档删除：工序将从列表隐藏。若该工序仍被工艺模块/模型引用，会阻止删除。"
                okText="删除"
                okButtonProps={{ danger: true }}
                cancelText="取消"
                onConfirm={() => deleteMutation.mutate(record.id)}
              >
                <Tooltip title="删除">
                  <Button size="small" danger icon={<DeleteOutlined />} />
                </Tooltip>
              </Popconfirm>
            </>
          )}
        </Space>
      ),
    },
  ]

  const statusValue = Form.useWatch('status', form) as string | undefined
  const isActive = statusValue === 'active'
  const costTypeValue = (Form.useWatch('cost_type', form) as ProcessCostType | undefined) ?? 'piece'
  const chargingModeValue = (Form.useWatch('charging_mode', form) as ProcessChargingMode | undefined) ?? 'count'
  const derivedMeasureUnit = chargingModeToUnit(chargingModeValue)

  // Drawer destroyOnClose + Form preserve={false} 会导致“先 setFieldsValue 再打开抽屉”失效；
  // 统一在抽屉打开后回填，避免编辑时掉值。
  useEffect(() => {
    if (!drawerOpen) return
    if (!pendingFormValues) return
    form.setFieldsValue(pendingFormValues)
    setPendingFormValues(null)
  }, [drawerOpen, form, pendingFormValues])

  // process_code is backend-allocated on save; no need to watch

  return (
    <Space direction="vertical" style={{ width: '100%' }} size={24}>
      <div>
        <Title level={3} style={{ marginBottom: 0 }}>
          工序管理
        </Title>
        <Text type="secondary">维护工序主数据（计时/计件），供工艺模块引用与订单维度预览计算。</Text>
      </div>

      <Card
        title="筛选"
        bordered={false}
        extra={
          <Space>
            <Button icon={<ReloadOutlined />} onClick={() => listQuery.refetch()}>
              刷新
            </Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
              新建工序
            </Button>
          </Space>
        }
      >
        <AntForm
          form={filtersForm}
          layout="inline"
          initialValues={{
            search: filters.search,
            status: filters.status,
            charging_mode: filters.charging_mode,
            category: (filters as any).category,
          }}
          onFinish={() => {
            const values = filtersForm.getFieldsValue()
            setFilters((prev) => ({
              ...prev,
              search: values.search?.trim() || undefined,
              status: values.status || undefined,
              charging_mode: values.charging_mode || undefined,
              category: values.category || undefined,
              page: 1,
            }))
          }}
        >
          <AntForm.Item name="search" label="关键词">
            <Input.Search placeholder="编码 / 名称" allowClear style={{ width: 240 }} />
          </AntForm.Item>
          <AntForm.Item name="status" label="状态">
            <Select allowClear placeholder="全部" options={PROCESS_STATUS_OPTIONS} style={{ width: 160 }} />
          </AntForm.Item>
          <AntForm.Item name="category" label="分类">
            <Select allowClear placeholder="全部" options={categoryOptions} style={{ width: 180 }} showSearch optionFilterProp="label" />
          </AntForm.Item>
          <AntForm.Item name="charging_mode" label="计量类型">
            <Select allowClear placeholder="全部" options={CHARGING_MODE_OPTIONS} style={{ width: 180 }} />
          </AntForm.Item>
          <AntForm.Item>
            <Space>
              <Button type="primary" htmlType="submit">
                查询
              </Button>
              <Button
                onClick={() => {
                  filtersForm.resetFields()
                  setFilters((prev) => ({
                    ...prev,
                    search: undefined,
                    status: undefined,
                    charging_mode: undefined,
                    category: undefined,
                    page: 1,
                  }))
                }}
              >
                重置
              </Button>
        </Space>
          </AntForm.Item>
        </AntForm>
      </Card>

      <Card>
        <Table<ProcessSummary>
          className="hide-x-scrollbar"
          rowKey="id"
          loading={listQuery.isLoading}
          dataSource={listQuery.data?.items ?? []}
          columns={columns}
          pagination={{
            ...pagination,
            showTotal: (total) => `共 ${total} 条`,
          }}
          tableLayout="fixed"
          scroll={{ x: 1600 }}
        />
      </Card>

      <Drawer
        title={drawerMode === 'create' ? '新建工序' : drawerMode === 'edit' ? '编辑工序' : '工序详情'}
        open={drawerOpen}
        onClose={() => {
          setDrawerOpen(false)
          setGuideOpen(false)
        }}
        width={720}
        destroyOnClose
        extra={
          drawerMode === 'view' ? (
            <Space>
              <Button onClick={() => setDrawerOpen(false)}>关闭</Button>
              {selected ? (
                <Button type="primary" icon={<EditOutlined />} onClick={() => openEdit(selected)}>
                  编辑
                </Button>
              ) : null}
            </Space>
          ) : (
            <Space>
              <Button icon={<QuestionCircleOutlined />} onClick={() => setGuideOpen(true)}>
                新建指南
              </Button>
              <Button onClick={() => setDrawerOpen(false)}>取消</Button>
              <Button
                type="primary"
                onClick={handleSubmit}
                loading={createMutation.isPending || updateMutation.isPending}
              >
                保存
              </Button>
            </Space>
          )
        }
      >
        <Form
          form={form}
          layout="vertical"
          disabled={drawerMode === 'view'}
          preserve={false}
        >
          <Form.Item name="id" hidden>
            <Input />
          </Form.Item>

          <Space style={{ width: '100%' }} size={16} align="start">
            <Form.Item
              label="工序编码"
              name="process_code"
              style={{ flex: 1 }}
              rules={[
                { max: 64, message: '最长 64 字符' },
              ]}
            >
              <Input
                placeholder={drawerMode === 'create' ? '保存时自动生成' : '如: PR001'}
                disabled
              />
            </Form.Item>
            <Form.Item
              label="状态"
              name="status"
              style={{ width: 200 }}
              rules={[{ required: true, message: '请选择状态' }]}
            >
              <Select options={PROCESS_STATUS_OPTIONS} />
            </Form.Item>
          </Space>

          <Form.Item
            label="工序类型"
            name="cost_type"
            rules={[{ required: true, message: '请选择工序类型' }]}
            tooltip="单选：计时/计件。两套字段都可同时维护，但最终核算只使用当前选择的类型。"
          >
            <Radio.Group
              options={[
                { label: '计时', value: 'time' },
                { label: '计件', value: 'piece' },
              ]}
              optionType="button"
              buttonStyle="solid"
            />
          </Form.Item>

          <Form.Item
            label="工序名称"
            name="process_name"
            rules={[{ required: true, message: '请输入工序名称' }, { max: 255, message: '最长 255 字符' }]}
          >
            <Input placeholder="如: 覆膜" />
          </Form.Item>

          <Form.Item
            label="分类"
            name="category"
            rules={[{ required: true, message: '请选择分类' }]}
          >
            <Select placeholder="请选择" options={categoryOptions} showSearch optionFilterProp="label" />
          </Form.Item>

          <Form.Item label="标签（非必填）" name="process_tags" tooltip="回车可新增标签；也可选择已存在标签。">
            <Select
              mode="tags"
              placeholder="例如：画艺 / 布艺 / 通用..."
              options={processTagOptions}
            />
          </Form.Item>

          <Space style={{ width: '100%' }} size={16} align="start">
            <Form.Item
              label="计量类型"
              name="charging_mode"
              style={{ width: 220 }}
              rules={[{ required: true, message: '请选择计量类型' }]}
              tooltip="按周长/面积/宽度/高度等，用于后续在工艺模块/模型中自动推导计量单位。"
            >
              <Select options={CHARGING_MODE_OPTIONS} />
            </Form.Item>
            <Form.Item label="计量单位（自动）" style={{ width: 220 }}>
              <Text>{derivedMeasureUnit}</Text>
            </Form.Item>
          </Space>

          <Text type="secondary" style={{ display: 'block', marginTop: -8, marginBottom: 12 }}>
            班组/工价/工时/计量等调参请在工艺模块（工艺模板）步骤行维护；工序管理仅维护通用工序字典。
          </Text>

          {costTypeValue === 'time' ? (
            <>
              <Space style={{ width: '100%' }} size={16} align="start">
                <Form.Item label="基础工时（分钟）" name="base_minutes" style={{ width: 220 }}>
                  <InputNumber min={0} precision={2} style={{ width: '100%' }} placeholder="固定值" />
                </Form.Item>
                <Form.Item label="单位工时（分钟）" name="unit_minutes" style={{ width: 220 }}>
                  <InputNumber min={0} precision={4} style={{ width: '100%' }} placeholder="每单位耗时" />
                </Form.Item>
              </Space>
          <Space style={{ width: '100%' }} size={16} align="start">
            <Form.Item
                  label="分钟单价（元/分钟）"
                  name="rate_per_minute"
                  style={{ width: 320 }}
                >
                  <InputNumber min={0} precision={6} style={{ width: '100%' }} placeholder="未配置（无法算成本）" />
                </Form.Item>
                <Form.Item label="计时公式" style={{ flex: 1 }}>
                  <Text type="secondary">
                    成本 = (基础工时 + 单位工时 × 计价量) × 分钟单价
                  </Text>
            </Form.Item>
              </Space>
            </>
          ) : (
            <Space style={{ width: '100%' }} size={16} align="start">
            <Form.Item
                label={isActive ? '计件单价（元/件）（必填）' : '计件单价（元/件）'}
                name="piece_rate"
                style={{ width: 320 }}
                rules={isActive ? [{ required: true, message: '启用状态下必须配置计件单价' }] : undefined}
            >
                <InputNumber min={0} precision={6} style={{ width: '100%' }} placeholder="未配置（无法算成本）" />
            </Form.Item>
              <Form.Item label="计件公式" style={{ flex: 1 }}>
                <Text type="secondary">成本 = 计件单价 × 订单数量</Text>
            </Form.Item>
          </Space>
          )}

          <Space style={{ width: '100%' }} size={16} align="start">
            <Form.Item
              label="标准工时（分钟）"
              name="standard_time_minutes"
              style={{ width: 220 }}
              tooltip="当前作为扩展字段存入 metadata_json.standard_time_minutes（不影响后端校验）"
            >
              <InputNumber style={{ width: '100%' }} min={0} precision={0} placeholder="可选" />
            </Form.Item>
          </Space>

          <Form.Item label="描述" name="description">
            <Input.TextArea rows={3} placeholder="可选" />
          </Form.Item>

          <Divider />

          <Collapse
            defaultActiveKey={aiPanelOpen ? ['ai'] : []}
            items={[
              {
                key: 'ai',
                label: 'AI 语义（可选，建议逐步完善）',
                children: (
                  <Space direction="vertical" size={12} style={{ width: '100%' }}>
                    <Form.Item label="工序意图/目的" name="ai_intent">
                      <Input.TextArea
                        rows={3}
                        placeholder="可直接写业务口径/规则说明（例如：用于地垫地毯，按最短边卷起+两头各留15cm扎带…）"
                      />
                    </Form.Item>
                    <Form.Item label="输入" name="ai_inputs">
                      <Input.TextArea rows={2} placeholder="输入材料/半成品/前置条件" />
                    </Form.Item>
                    <Form.Item label="输出" name="ai_outputs">
                      <Input.TextArea rows={2} placeholder="输出产物/状态/交付物" />
                    </Form.Item>
                    <Form.Item label="质量要点/QC" name="ai_quality_points">
                      <Input.TextArea rows={2} placeholder="验收点、常见缺陷、容差/注意事项" />
                    </Form.Item>
                    <Form.Item label="禁忌/边界条件" name="ai_constraints">
                      <Input.TextArea rows={2} placeholder="什么时候不能用/风险点" />
                    </Form.Item>
                    <Form.Item label="设备/工具" name="ai_tools">
                      <Input.TextArea rows={2} placeholder="设备、刀具、工装夹具等" />
                    </Form.Item>
                    <Form.Item
                      label="参数模板（JSON）"
                      name="ai_parameter_schema_json"
                      tooltip="用于后续 AI 自动生成工艺步骤参数；留空即可。"
                    >
                      <Input.TextArea rows={6} placeholder='例如：{"speed": {"type":"number","unit":"mm/s","default":10}}' />
                    </Form.Item>
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
        title="新建工序指南（三步法）"
        content={processCreateGuide}
        tip="提示：本指南内容来自项目内的 Markdown 文档。后续也会在“真实物料/虚拟物料/工艺模块/产品模型”等面板复用同一套展示方式。"
      />

      <Modal
        title="复制工序"
        open={copyModalOpen}
        onCancel={() => setCopyModalOpen(false)}
        okText="复制"
        cancelText="取消"
        confirmLoading={copyMutation.isPending}
        onOk={async () => {
          if (!copySource) {
            message.error('缺少源工序')
            return
          }
          const values = await copyForm.validateFields()
          copyMutation.mutate({ id: copySource.id, payload: values })
        }}
        destroyOnClose
      >
        <Form form={copyForm} layout="vertical" preserve={false}>
          <Form.Item
            label="新工序编码"
            name="process_code"
            rules={[
              { required: true, message: '请输入新工序编码' },
              { max: 64, message: '最长 64 字符' },
            ]}
          >
            <Input placeholder="如: PR001_COPY" />
          </Form.Item>
          <Form.Item
            label="新工序名称"
            name="process_name"
            rules={[
              { required: true, message: '请输入新工序名称' },
              { max: 255, message: '最长 255 字符' },
            ]}
          >
            <Input placeholder="如: 覆膜（复制）" />
          </Form.Item>
          <Form.Item label="状态" name="status">
            <Select allowClear placeholder="默认继承源工序状态" options={PROCESS_STATUS_OPTIONS} />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  )
}

export default ProcessesPage


