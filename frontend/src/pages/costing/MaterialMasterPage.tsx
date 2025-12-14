import CloudSyncOutlined from '@ant-design/icons/lib/icons/CloudSyncOutlined'
import DownloadOutlined from '@ant-design/icons/lib/icons/DownloadOutlined'
import FileSearchOutlined from '@ant-design/icons/lib/icons/FileSearchOutlined'
import HistoryOutlined from '@ant-design/icons/lib/icons/HistoryOutlined'
import ReloadOutlined from '@ant-design/icons/lib/icons/ReloadOutlined'
import {
  Badge,
  Button,
  Card,
  Col,
  Drawer,
  Empty,
  Form,
  Input,
  Modal,
  Row,
  Select,
  Space,
  Statistic,
  Switch,
  Table,
  Tag,
  Tooltip,
  Typography,
  message,
} from 'antd'
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table'
import dayjs from 'dayjs'
import { useCallback, useMemo, useState } from 'react'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import {
  exportMaterials,
  fetchMaterialSyncLogs,
  fetchMaterials,
  triggerMaterialSync,
  updateMaterialStatus,
} from '@/services/planner'
import type {
  Material,
  MaterialListResponse,
  MaterialSyncLog,
  MaterialSyncLogResponse,
} from '@/types/planner'
import {
  MATERIAL_STATUS_OPTIONS,
  MATERIAL_TYPE_OPTIONS,
} from '@/constants/planner'

const { Title, Text } = Typography

const defaultFilters = {
  search: undefined as string | undefined,
  material_type: undefined as string | undefined,
  status: undefined as string | undefined,
  is_active: undefined as boolean | undefined,
}

const MaterialMasterPage = () => {
  const queryClient = useQueryClient()
  const [filtersForm] = Form.useForm()
  const [filters, setFilters] = useState(defaultFilters)
  const [pagination, setPagination] = useState({ current: 1, pageSize: 20 })
  const [syncDrawerOpen, setSyncDrawerOpen] = useState(false)
  const [syncPagination, setSyncPagination] = useState({ page: 1, pageSize: 10 })
  const [exporting, setExporting] = useState(false)
  const [syncing, setSyncing] = useState(false)

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

  const materials = materialsQuery.data?.items ?? []
  const totalCount = materialsQuery.data?.total ?? 0
  const activeOnPage = useMemo(() => materials.filter((item) => item.is_active).length, [materials])

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
      updateMaterialStatus(id, { is_active: active, status: active ? 'active' : 'inactive' }),
    onSuccess: (_, variables) => {
      message.success(`物料已${variables.active ? '启用' : '停用'}`)
      queryClient.invalidateQueries({ queryKey: ['materials'] })
    },
    onError: (error: unknown) => {
      const err = error as Error
      message.error(err.message || '更新状态失败')
    },
  })

  const handleFilterSubmit = () => {
    const values = filtersForm.getFieldsValue()
    setFilters({
      search: values.search?.trim() || undefined,
      material_type: values.material_type || undefined,
      status: values.status || undefined,
      is_active: values.onlyActive ? true : undefined,
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

  const confirmSyncMaterials = () => {
    Modal.confirm({
      title: '手动同步宜搭物料',
      content: '将立即触发 YiDa 同步任务，该操作可能需要几分钟完成，确认继续？',
      okText: '立即同步',
      cancelText: '取消',
      onOk: handleSyncMaterials,
    })
  }

  const handleSyncMaterials = async () => {
    setSyncing(true)
    try {
      await triggerMaterialSync()
      message.success('已触发宜搭物料同步')
      setSyncDrawerOpen(true)
      queryClient.invalidateQueries({ queryKey: ['material-sync-logs'] })
    } catch (error) {
      const err = error as Error
      message.error(err.message || '同步失败，请稍后重试')
    } finally {
      setSyncing(false)
    }
  }

  const materialColumns: ColumnsType<Material> = [
    {
      title: '物料编码',
      dataIndex: 'material_code',
      key: 'material_code',
      width: 160,
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
      render: (text: string, record) => (
        <Space direction="vertical" size={0}>
          <Text strong>{text}</Text>
          <Text type="secondary">
            {record.material_type === 'virtual' ? '虚拟物料' : '原材料'}
            {record.category ? ` · ${record.category}` : ''}
          </Text>
        </Space>
      ),
    },
    {
      title: '单位 / 单价',
      key: 'unit_price',
      width: 160,
      render: (_, record) => (
        <Space direction="vertical" size={0}>
          <Text>{record.unit || '-'}</Text>
          <Text type="secondary">{formatCurrency(record.unit_price, record.currency)}</Text>
        </Space>
      ),
    },
    {
      title: '供应商',
      key: 'supplier',
      width: 200,
      render: (_, record) => (
        <Space direction="vertical" size={0}>
          <Text>{record.supplier_name || '-'}</Text>
          <Text type="secondary">{record.supplier_code || ''}</Text>
        </Space>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 120,
      render: (_, record) => (
        <Tag color={record.is_active ? 'green' : 'red'}>
          {record.is_active ? '启用' : '停用'}
        </Tag>
      ),
    },
    {
      title: '最后更新',
      dataIndex: 'updated_at',
      key: 'updated_at',
      width: 180,
      render: (value: string) => dayjs(value).format('YYYY-MM-DD HH:mm'),
    },
    {
      title: '操作',
      key: 'actions',
      width: 140,
      render: (_, record) => (
        <Space>
          <Switch
            size="small"
            checkedChildren="启用"
            unCheckedChildren="停用"
            checked={record.is_active}
            loading={statusMutation.isPending && statusMutation.variables?.id === record.id}
            onChange={(checked) => statusMutation.mutate({ id: record.id, active: checked })}
          />
          <Tooltip title="查看源数据">
            <Button
              type="link"
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
            />
          </Tooltip>
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
        <Col xs={24} xl={7}>
          <Card title="当前概览" bordered={false}>
            <Row gutter={16}>
              <Col span={12}>
                <Statistic title="物料总数" value={totalCount} />
              </Col>
              <Col span={12}>
                <Statistic title="本页启用" value={activeOnPage} />
              </Col>
            </Row>
            <Button
              icon={<HistoryOutlined />}
              block
              style={{ marginTop: 16 }}
              onClick={() => setSyncDrawerOpen(true)}
            >
              查看同步日志
            </Button>
          </Card>
        </Col>
        <Col xs={24} xl={17}>
          <Card
            title="筛选"
            bordered={false}
            extra={
              <Space>
                <Button icon={<ReloadOutlined />} onClick={() => materialsQuery.refetch()}>
                  刷新
                </Button>
                <Button
                  icon={<CloudSyncOutlined />}
                  loading={syncing}
                  onClick={confirmSyncMaterials}
                >
                  同步宜搭
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
              initialValues={{ onlyActive: false }}
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
              <Form.Item name="material_type" label="物料类型">
                <Select
                  allowClear
                  placeholder="全部"
                  options={MATERIAL_TYPE_OPTIONS}
                  style={{ width: 160 }}
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

