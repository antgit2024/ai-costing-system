import CheckCircleOutlined from '@ant-design/icons/lib/icons/CheckCircleOutlined'
import CopyOutlined from '@ant-design/icons/lib/icons/CopyOutlined'
import EditOutlined from '@ant-design/icons/lib/icons/EditOutlined'
import PlusOutlined from '@ant-design/icons/lib/icons/PlusOutlined'
import QuestionCircleOutlined from '@ant-design/icons/lib/icons/QuestionCircleOutlined'
import ReloadOutlined from '@ant-design/icons/lib/icons/ReloadOutlined'
import StopOutlined from '@ant-design/icons/lib/icons/StopOutlined'
import {
  Alert,
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
  deactivateProcess,
  fetchProcesses,
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

const PROCESS_CATEGORY_OPTIONS = [
  { label: '布艺', value: '布艺' },
  { label: '画艺', value: '画艺' },
]

// 班组在工艺模块（工艺模板）的工序行维护；工序库不承载班组字段

const CHARGING_MODE_OPTIONS: Array<{ label: string; value: ProcessChargingMode }> = [
  { label: '固定', value: 'fixed' },
  { label: '按件', value: 'count' },
  { label: '按面积', value: 'area' },
  { label: '按周长', value: 'perimeter' },
  { label: '按宽度', value: 'width' },
  { label: '按高度', value: 'height' },
]

const MEASURE_UNIT_OPTIONS = [
  { label: '平米', value: '平米' },
  { label: '米', value: '米' },
  { label: '个', value: '个' },
  { label: '套', value: '套' },
]

const unitToChargingMode = (unit?: string | null): ProcessChargingMode => {
  const u = normalizeUnit(unit)
  if (u === '平米') return 'area'
  if (u === '米') return 'perimeter'
  return 'count'
}

const fallbackProcessCode = () => {
  const suffix = String(Date.now() % 100000).padStart(5, '0')
  return `PR${suffix}`
}

const getStatusTag = (status: string) => {
  if (status === 'active') return <Tag color="green">启用</Tag>
  if (status === 'inactive') return <Tag color="red">停用</Tag>
  return <Tag color="gold">草稿</Tag>
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

const renderPricingSummary = (record: ProcessSummary) => {
  const meta = (record.metadata_json ?? {}) as any
  const type = getProcessCostType(record)
  if (type === 'time') {
    const base = safeNumber(meta?.base_minutes) ?? 0
    const unit = safeNumber(meta?.unit_minutes) ?? 0
    const measureUnit = normalizeUnit(meta?.measure_unit ?? record.unit_of_measure) || '-'
    const rate = safeNumber(meta?.rate_per_minute)
    return (
      <Space direction="vertical" size={0}>
        <Text>
          基础{base}min + 单位{unit}min/{measureUnit}
        </Text>
        <Text type={rate === undefined ? 'danger' : undefined}>
          分钟单价：{rate === undefined ? '未配置（无法算成本）' : `${rate} 元/分钟`}
        </Text>
      </Space>
    )
  }
  const pieceRate = safeNumber(meta?.piece_rate) ?? safeNumber(record.standard_rate)
  return (
    <Space direction="vertical" size={0}>
      <Text>计件单价：{pieceRate === undefined ? '未配置（无法算成本）' : `${pieceRate} 元/件`}</Text>
      <Text type="secondary">成本 = 计件单价 × 订单数量</Text>
    </Space>
  )
}

const ProcessesPage = () => {
  const [filters, setFilters] = useState<ProcessQueryParams>({ page: 1, page_size: 20 })
  const [filtersForm] = AntForm.useForm()
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [drawerMode, setDrawerMode] = useState<'create' | 'edit' | 'view'>('create')
  const [selected, setSelected] = useState<ProcessSummary | null>(null)
  const [copyModalOpen, setCopyModalOpen] = useState(false)
  const [copySource, setCopySource] = useState<ProcessSummary | null>(null)
  const [guideOpen, setGuideOpen] = useState(false)

  const [form] = Form.useForm<
    ProcessCreatePayload & {
      id?: string
      cost_type?: ProcessCostType
      base_minutes?: number
      unit_minutes?: number
      measure_unit?: '平米' | '米' | '个' | '套'
      rate_per_minute?: number
      piece_rate?: number
      standard_time_minutes?: number
    }
  >()
  const [copyForm] = Form.useForm<ProcessCopyPayload>()

  const listQuery = useQuery<ProcessListResponse>({
    queryKey: ['processes', filters],
    queryFn: () => fetchProcesses(filters),
    placeholderData: keepPreviousData,
  })

  const categoryOptions = useMemo(() => {
    const base = new Map<string, string>()
    for (const opt of PROCESS_CATEGORY_OPTIONS) base.set(opt.value, opt.label)
    for (const it of listQuery.data?.items ?? []) {
      const c = String(it.category ?? '').trim()
      if (c) base.set(c, c)
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
    setDrawerMode('create')
    setSelected(null)
    form.resetFields()
    form.setFieldsValue({
      process_code: fallbackProcessCode(),
      cost_type: 'time',
      charging_mode: 'count',
      status: 'draft',
      unit_of_measure: '个',
      measure_unit: '个',
    })
    generateNextCode({ prefix: 'PR', width: 5 })
      .then((res) => {
        form.setFieldValue('process_code', res.code)
      })
      .catch(() => {
        // keep fallback
    })
    setDrawerOpen(true)
  }

  const openView = (record: ProcessSummary) => {
    setDrawerMode('view')
    setSelected(record)
    form.resetFields()
    const meta = (record.metadata_json ?? {}) as any
    const costType = getProcessCostType(record)
    form.setFieldsValue({
      id: record.id,
      process_code: record.process_code,
      process_name: record.process_name,
      description: record.description ?? undefined,
      category: record.category ?? undefined,
      cost_type: costType,
      base_minutes: safeNumber(meta?.base_minutes),
      unit_minutes: safeNumber(meta?.unit_minutes),
      measure_unit: (meta?.measure_unit as any) ?? (record.unit_of_measure as any) ?? '个',
      rate_per_minute: safeNumber(meta?.rate_per_minute),
      piece_rate: safeNumber(meta?.piece_rate) ?? safeNumber(record.standard_rate),
      charging_mode: record.charging_mode,
      standard_rate: safeNumber(record.standard_rate),
      unit_of_measure: record.unit_of_measure ?? undefined,
      status: record.status,
      standard_time_minutes: safeNumber((record.metadata_json as any)?.standard_time_minutes),
    })
    setDrawerOpen(true)
  }

  const openEdit = (record: ProcessSummary) => {
    setDrawerMode('edit')
    setSelected(record)
    form.resetFields()
    const meta = (record.metadata_json ?? {}) as any
    const costType = getProcessCostType(record)
    form.setFieldsValue({
      id: record.id,
      process_code: record.process_code,
      process_name: record.process_name,
      description: record.description ?? undefined,
      category: record.category ?? undefined,
      cost_type: costType,
      base_minutes: safeNumber(meta?.base_minutes),
      unit_minutes: safeNumber(meta?.unit_minutes),
      measure_unit: (meta?.measure_unit as any) ?? (record.unit_of_measure as any) ?? '个',
      rate_per_minute: safeNumber(meta?.rate_per_minute),
      piece_rate: safeNumber(meta?.piece_rate) ?? safeNumber(record.standard_rate),
      charging_mode: record.charging_mode,
      standard_rate: safeNumber(record.standard_rate),
      unit_of_measure: record.unit_of_measure ?? undefined,
      status: record.status,
      standard_time_minutes: safeNumber((record.metadata_json as any)?.standard_time_minutes),
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

    const costType = (values.cost_type ?? 'piece') as ProcessCostType
    const measureUnit = values.measure_unit ?? values.unit_of_measure ?? '个'
    const chargingMode = unitToChargingMode(measureUnit)
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
      if (values.status === 'active' && !standardRate) {
        message.error('启用状态下：计时工序必须配置“分钟单价”')
        return
      }
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
      width: 160,
      render: (value: string) => <Text code>{value}</Text>,
    },
    {
      title: '名称',
      dataIndex: 'process_name',
      width: 220,
      ellipsis: true,
    },
    {
      title: '分类',
      dataIndex: 'category',
      width: 120,
      ellipsis: true,
      render: (value?: string | null) => (
        <Text ellipsis={{ tooltip: value || '-' }}>{value || '-'}</Text>
      ),
    },
    {
      title: '工序类型 / 计价参数',
      key: 'pricing',
      width: 360,
      render: (_, record) => (
        <Space direction="vertical" size={0}>
          <Tag color={getProcessCostType(record) === 'time' ? 'blue' : 'purple'}>
            {getProcessCostType(record) === 'time' ? '计时' : '计件'}
          </Tag>
          {renderPricingSummary(record)}
        </Space>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (value: string) => getStatusTag(value),
    },
    {
      title: '更新时间',
      dataIndex: 'updated_at',
      width: 160,
      render: (value: string) => dayjs(value).format('YYYY-MM-DD HH:mm'),
    },
    {
      title: '操作',
      key: 'actions',
      width: 220,
      render: (_, record) => (
        <Space>
          <Button size="small" onClick={() => openView(record)}>
            查看
          </Button>
          <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(record)}>
            编辑
          </Button>
          <Button size="small" icon={<CopyOutlined />} onClick={() => openCopy(record)}>
            复制
          </Button>
          {record.status === 'active' ? (
            <Popconfirm
              title="确认停用该工序？"
              okText="停用"
              cancelText="取消"
              onConfirm={() => deactivateMutation.mutate(record.id)}
            >
              <Button size="small" danger icon={<StopOutlined />}>
                停用
              </Button>
            </Popconfirm>
          ) : (
            <Button
              size="small"
              type="primary"
              icon={<CheckCircleOutlined />}
              onClick={() => activateMutation.mutate(record.id)}
            >
              启用
            </Button>
          )}
        </Space>
      ),
    },
  ]

  const statusValue = Form.useWatch('status', form) as string | undefined
  const isActive = statusValue === 'active'
  const costTypeValue = (Form.useWatch('cost_type', form) as ProcessCostType | undefined) ?? 'piece'
  const measureUnitValue =
    (Form.useWatch('measure_unit', form) as '平米' | '米' | '个' | '套' | undefined) ?? '个'

  // keep unit hint stable (user can override by switching measure_unit)
  useEffect(() => {
    if (drawerMode === 'view') return
    if (costTypeValue === 'piece') {
      if (measureUnitValue !== '个') {
        form.setFieldValue('measure_unit', '个')
      }
    }
  }, [costTypeValue, drawerMode, form, measureUnitValue])

  return (
    <Space direction="vertical" style={{ width: '100%' }} size={24}>
      <div>
        <Title level={3} style={{ marginBottom: 0 }}>
          工序库
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
          }}
          onFinish={() => {
            const values = filtersForm.getFieldsValue()
            setFilters((prev) => ({
              ...prev,
              search: values.search?.trim() || undefined,
              status: values.status || undefined,
              charging_mode: values.charging_mode || undefined,
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
          <AntForm.Item name="charging_mode" label="计价量类型">
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
                  setFilters((prev) => ({ ...prev, search: undefined, status: undefined, charging_mode: undefined, page: 1 }))
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
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 12 }}
          message="计价说明（便于统一表达）"
          description={
            <Space direction="vertical" size={4}>
              <div>
                <Text strong>计时：</Text>
                <Text>成本 = (基础工时 + 单位工时×计价量) × 分钟单价</Text>
              </div>
              <div>
                <Text strong>计件：</Text>
                <Text>成本 = 计件单价 × 数量</Text>
              </div>
              <Text type="secondary">
                工序类型为单选（计时/计件），但两套字段都可同时维护；最终核算以当前选择的类型为准。
              </Text>
            </Space>
          }
        />
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
                { required: true, message: '请输入工序编码' },
                { max: 64, message: '最长 64 字符' },
              ]}
            >
              <Input placeholder="如: PR001" disabled={drawerMode !== 'create'} />
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

          <Text type="secondary" style={{ display: 'block', marginTop: -8, marginBottom: 12 }}>
            班组/工价/工时/计量等调参请在工艺模块（工艺模板）步骤行维护；工序库仅维护通用工序字典。
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
                <Form.Item
                  label="计量单位"
                  name="measure_unit"
                  style={{ width: 220 }}
                  tooltip="平米/米/个（建议与 BOM 单位配对；可在工艺模块按业务选择按周长/按长度）"
                >
                  <Select options={MEASURE_UNIT_OPTIONS} />
                </Form.Item>
              </Space>
          <Space style={{ width: '100%' }} size={16} align="start">
            <Form.Item
                  label={isActive ? '分钟单价（元/分钟）（必填）' : '分钟单价（元/分钟）'}
                  name="rate_per_minute"
                  style={{ width: 320 }}
                  rules={isActive ? [{ required: true, message: '启用状态下必须配置分钟单价' }] : undefined}
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


