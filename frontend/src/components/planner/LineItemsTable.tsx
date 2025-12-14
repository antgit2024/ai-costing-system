import { useMemo, useState } from 'react'
import type { RcFile } from 'antd/es/upload'
import { Alert, Button, Card, Empty, Form, Input, InputNumber, message, Select, Space, Table, Tag, Upload } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import CloudUploadOutlined from '@ant-design/icons/lib/icons/CloudUploadOutlined'
import EditOutlined from '@ant-design/icons/lib/icons/EditOutlined'
import SaveOutlined from '@ant-design/icons/lib/icons/SaveOutlined'
import StopOutlined from '@ant-design/icons/lib/icons/StopOutlined'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { NormalizedLineItem } from '@/types/planner'
import type { LineItemResponse } from '@/services/planner'
import { fetchLineItems, importLineItems, updateLineItem } from '@/services/planner'
import { LINE_ITEM_STATUS_OPTIONS, LINE_ITEM_TYPE_OPTIONS } from '@/constants/planner'
import PlannerJobDrawer from './PlannerJobDrawer'
import type { PlannerJobKind } from '@/types/planner'

interface LineItemsTableProps {
  initiativeId?: string
  packageId?: string
}

interface LineItemFilters {
  status?: string
  type?: string
  search?: string
}

const DEFAULT_PAGE_SIZE = 10

const LineItemsTable = ({ initiativeId, packageId }: LineItemsTableProps) => {
  const [filters, setFilters] = useState<LineItemFilters>({})
  const [pagination, setPagination] = useState({ current: 1, pageSize: DEFAULT_PAGE_SIZE })
  const updateFilters = (next: LineItemFilters) => {
    setFilters(next)
    setPagination((prev) => ({ ...prev, current: 1 }))
  }
  const [editingRowId, setEditingRowId] = useState<string>()
  const [form] = Form.useForm()
  const [jobViewer, setJobViewer] = useState<{ jobId?: string; open: boolean; kind: PlannerJobKind }>({
    jobId: undefined,
    open: false,
    kind: 'import',
  })
  const queryClient = useQueryClient()

  const lineItemsQueryKey = useMemo(
    () => ['lineItems', initiativeId, packageId, filters, pagination],
    [initiativeId, packageId, filters, pagination],
  )

  const { data, isPending, refetch } = useQuery<LineItemResponse>({
    queryKey: lineItemsQueryKey,
    enabled: !!initiativeId,
    queryFn: () =>
      fetchLineItems({
        ...filters,
        initiative_id: initiativeId,
        package_id: packageId,
        page: pagination.current,
        page_size: pagination.pageSize,
      }),
    placeholderData: keepPreviousData,
  })

  const updateMutation = useMutation({
    mutationFn: (payload: { id: string; values: Record<string, unknown> }) =>
      updateLineItem(payload.id, payload.values),
    onSuccess: () => {
      message.success('行项目已更新')
      setEditingRowId(undefined)
      queryClient.invalidateQueries({ queryKey: lineItemsQueryKey })
    },
    onError: (err: Error) => {
      message.error(err.message || '更新失败')
    },
  })

  const handleEdit = (record: NormalizedLineItem) => {
    setEditingRowId(record.id)
    form.setFieldsValue({
      quantity: Number(record.quantity),
      unit_cost_estimate: Number(record.unit_cost_estimate),
      status: record.status,
    })
  }

  const handleCancel = () => {
    setEditingRowId(undefined)
    form.resetFields()
  }

  const handleSave = async (recordId: string) => {
    const values = await form.validateFields()
    await updateMutation.mutateAsync({ id: recordId, values })
  }

  const handleTableChange = (page: number, pageSize?: number) => {
    setPagination((prev) => ({ ...prev, current: page, pageSize: pageSize ?? prev.pageSize }))
  }

  const handleImport = async (file: RcFile) => {
    if (!initiativeId) {
      message.warning('请先选择一个 initiative')
      return false
    }
    try {
      const job = await importLineItems({
        file,
        initiativeId,
        requestedBy: 'planner-frontend',
      })
      setJobViewer({ jobId: job.id, open: true, kind: 'import' })
      message.success('导入任务已提交')
    } catch (error) {
      message.error((error as Error).message || '导入失败')
    }
    return false
  }

  const columns: ColumnsType<NormalizedLineItem> = [
    {
      title: '描述',
      dataIndex: 'description',
      width: 220,
      render: (text: string) => <span>{text}</span>,
    },
    {
      title: '类型',
      dataIndex: 'type',
      width: 120,
      render: (value: string) => <Tag color="purple">{value}</Tag>,
    },
    {
      title: '数量',
      dataIndex: 'quantity',
      width: 120,
      render: (_value, record) =>
        editingRowId === record.id ? (
          <Form.Item name="quantity" noStyle>
            <InputNumber min={0} style={{ width: '100%' }} />
          </Form.Item>
        ) : (
          Number(record.quantity).toLocaleString()
        ),
    },
    {
      title: '单价',
      dataIndex: 'unit_cost_estimate',
      width: 140,
      render: (_value, record) =>
        editingRowId === record.id ? (
          <Form.Item name="unit_cost_estimate" noStyle>
            <InputNumber min={0} style={{ width: '100%' }} />
          </Form.Item>
        ) : (
          `${record.currency} ${Number(record.unit_cost_estimate).toLocaleString()}`
        ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 140,
      render: (_value, record) =>
        editingRowId === record.id ? (
          <Form.Item name="status" noStyle>
            <Select
              options={LINE_ITEM_STATUS_OPTIONS.filter((option) => option.value)}
              placeholder="状态"
              style={{ width: '100%' }}
            />
          </Form.Item>
        ) : (
          <Tag className="status-tag-bold" color="geekblue">
            {record.status}
          </Tag>
        ),
    },
    {
      title: '供应商',
      dataIndex: 'supplier_id',
      width: 160,
      render: (value: string | undefined) => value || '未指定',
    },
    {
      title: '操作',
      key: 'actions',
      width: 160,
      render: (_value, record) =>
        editingRowId === record.id ? (
          <Space>
            <Button size="small" type="primary" icon={<SaveOutlined />} loading={updateMutation.isPending} onClick={() => handleSave(record.id)}>
              保存
            </Button>
            <Button size="small" icon={<StopOutlined />} onClick={handleCancel}>
              取消
            </Button>
          </Space>
        ) : (
          <Button
            size="small"
            icon={<EditOutlined />}
            type="link"
            onClick={() => handleEdit(record)}
            disabled={!initiativeId}
          >
            编辑
          </Button>
        ),
    },
  ]

  if (!initiativeId) {
    return (
      <Card title="行项目" className="line-items-card planner-section">
        <Empty description="请选择 initiative 以查看行项目" />
      </Card>
    )
  }

  return (
    <>
      <Card
        title="行项目"
        className="line-items-card planner-section"
        extra={
          <Space size={8}>
            <Select
              placeholder="状态"
              allowClear
              size="small"
              value={filters.status}
              style={{ width: 140 }}
              options={LINE_ITEM_STATUS_OPTIONS}
              onChange={(value) => updateFilters({ ...filters, status: value })}
            />
            <Select
              placeholder="类型"
              allowClear
              size="small"
              value={filters.type}
              style={{ width: 140 }}
              options={LINE_ITEM_TYPE_OPTIONS}
              onChange={(value) => updateFilters({ ...filters, type: value })}
            />
            <Input.Search
              placeholder="搜索描述/编号"
              allowClear
              size="small"
              style={{ width: 200 }}
              value={filters.search}
              onChange={(e) => updateFilters({ ...filters, search: e.target.value || undefined })}
              onSearch={(value) => updateFilters({ ...filters, search: value || undefined })}
            />
            <Upload beforeUpload={handleImport} showUploadList={false} accept=".csv" disabled={!initiativeId}>
              <Button icon={<CloudUploadOutlined />} disabled={!initiativeId}>
                导入 CSV
              </Button>
            </Upload>
            <Button onClick={() => refetch()} disabled={!initiativeId}>
              刷新
            </Button>
          </Space>
        }
      >
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 12 }}
          message="支持 inline edit，保存后实时调用 API。导入 CSV 将触发后台异步任务，可在右侧面板查看进度。"
        />
        <Form form={form} component={false}>
          <Table
            rowKey="id"
            size="small"
            loading={isPending}
            columns={columns}
            dataSource={data?.items ?? []}
            pagination={{
              current: pagination.current,
              pageSize: pagination.pageSize,
              total: data?.total ?? 0,
              showSizeChanger: true,
              onChange: handleTableChange,
            }}
            bordered
          />
        </Form>
      </Card>

      <PlannerJobDrawer
        jobId={jobViewer.jobId}
        kind={jobViewer.kind}
        open={jobViewer.open}
        title="CSV 导入任务"
        onClose={() => setJobViewer((prev) => ({ ...prev, open: false }))}
        onJobSettled={() => {
          queryClient.invalidateQueries({ queryKey: lineItemsQueryKey })
        }}
      />
    </>
  )
}

export default LineItemsTable

