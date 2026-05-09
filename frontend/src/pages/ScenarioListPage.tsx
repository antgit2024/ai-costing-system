import { useEffect, useMemo, useState } from 'react'
import {
  Alert,
  Button,
  Card,
  Input,
  message,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Tooltip,
  Typography,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import ReloadOutlined from '@ant-design/icons/lib/icons/ReloadOutlined'
import StarFilled from '@ant-design/icons/lib/icons/StarFilled'
import StarOutlined from '@ant-design/icons/lib/icons/StarOutlined'
import CloudDownloadOutlined from '@ant-design/icons/lib/icons/CloudDownloadOutlined'
import SendOutlined from '@ant-design/icons/lib/icons/SendOutlined'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { ScenarioListItem, ScenarioListResponse } from '@/types/planner'
import {
  exportScenario,
  fetchInitiatives,
  fetchScenarios,
  setScenarioFavorite,
  submitScenarioForApproval,
} from '@/services/planner'
import { usePlannerStore } from '@/store/plannerStore'
import { SCENARIO_STATUS_OPTIONS } from '@/constants/planner'
import PlannerJobDrawerLazy from '@/components/planner/PlannerJobDrawerLazy'
import { formatBeijingTime } from '@/utils/beijingTime'

const { Text } = Typography

const ScenarioListPage = () => {
  const queryClient = useQueryClient()
  const {
    scenarioFilters,
    setScenarioFilters,
    scenarioFavorites,
    toggleScenarioFavoriteLocal,
  } = usePlannerStore()
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([])
  const [jobViewer, setJobViewer] = useState<{ open: boolean; jobId?: string; title?: string }>({
    open: false,
    jobId: undefined,
    title: undefined,
  })

  const initiativeQuery = useQuery({
    queryKey: ['initiatives', 'filters'],
    queryFn: () => fetchInitiatives({ page_size: 50 }),
  })

  const scenarioQuery = useQuery<ScenarioListResponse>({
    queryKey: ['scenarios', scenarioFilters],
    queryFn: () =>
      fetchScenarios({
        ...scenarioFilters,
      }),
    placeholderData: keepPreviousData,
  })

  const scenarioQueryError = scenarioQuery.error as Error | null
  const initiativeQueryError = initiativeQuery.error as Error | null

  useEffect(() => {
    if (scenarioQueryError) {
      message.error(`场景列表加载失败：${scenarioQueryError.message}`)
    }
  }, [scenarioQueryError])

  useEffect(() => {
    if (initiativeQueryError) {
      message.warning(`Initiative 过滤项暂不可用：${initiativeQueryError.message}`)
    }
  }, [initiativeQueryError])

  const scenarios = scenarioQuery.data?.items ?? []
  const selectedScenarios = useMemo(
    () => scenarios.filter((scenario) => selectedRowKeys.includes(scenario.id)),
    [scenarios, selectedRowKeys],
  )

  useEffect(() => {
    setSelectedRowKeys([])
  }, [scenarioFilters, scenarioQuery.data?.items])

  const favoriteMutation = useMutation({
    mutationFn: ({ id, next }: { id: string; next: boolean }) => setScenarioFavorite(id, next),
    onMutate: ({ id, next }) => {
      toggleScenarioFavoriteLocal(id, next)
    },
    onError: (_err, { id }) => {
      toggleScenarioFavoriteLocal(id, false)
      message.error('更新收藏状态失败')
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['scenarios'] })
      queryClient.invalidateQueries({ queryKey: ['scenario-builder-scenarios'] })
    },
  })

  const handleFavorite = (record: ScenarioListItem) => {
    const next = !(record.favorite || scenarioFavorites[record.id])
    favoriteMutation.mutate({ id: record.id, next })
  }

  const handleBulkSubmit = async () => {
    if (!selectedRowKeys.length) {
      message.info('请选择场景')
      return
    }
    const invalid = selectedScenarios.filter(
      (scenario) => !['draft', 'rejected'].includes(scenario.status),
    )
    if (invalid.length) {
      message.warning('仅支持提交 Draft 或 Rejected 场景')
      return
    }
    const hide = message.loading('批量提交中...', 0)
    try {
      await Promise.all(
        selectedRowKeys.map((scenarioId) =>
          submitScenarioForApproval({
            scenario_id: String(scenarioId),
            actor_id: 'planner-ui',
            actor_role: 'planner',
          }),
        ),
      )
      message.success('批量提交成功')
      queryClient.invalidateQueries({ queryKey: ['scenarios'] })
      queryClient.invalidateQueries({ queryKey: ['scenario-builder-scenarios'] })
      setSelectedRowKeys([])
    } catch (error) {
      message.error((error as Error).message || '批量提交失败')
    } finally {
      hide()
    }
  }

  const handleBulkExport = async () => {
    if (!selectedRowKeys.length) {
      message.info('请选择场景')
      return
    }
    const invalid = selectedScenarios.filter((scenario) => scenario.status !== 'approved')
    if (invalid.length) {
      message.warning('仅已批准的场景可以导出')
      return
    }
    const hide = message.loading('批量导出任务创建中...', 0)
    try {
      const jobs = await Promise.all(
        selectedRowKeys.map((scenarioId) =>
          exportScenario(String(scenarioId), {
            requested_by: 'planner-ui',
            format: 'xlsx',
          }),
        ),
      )
      const lastJob = jobs[jobs.length - 1]
      if (lastJob?.job_id) {
        setJobViewer({ open: true, jobId: lastJob.job_id, title: '批量导出任务' })
      }
      message.success('批量导出已触发')
      queryClient.invalidateQueries({ queryKey: ['scenarios'] })
      queryClient.invalidateQueries({ queryKey: ['scenario-builder-scenarios'] })
      setSelectedRowKeys([])
    } catch (error) {
      message.error((error as Error).message || '批量导出失败')
    } finally {
      hide()
    }
  }

  const columns: ColumnsType<ScenarioListItem> = [
    {
      title: '',
      dataIndex: 'favorite',
      width: 60,
      render: (_value, record) => {
        const active = record.favorite || scenarioFavorites[record.id]
        return (
          <Button
            type="text"
            icon={active ? <StarFilled style={{ color: '#faad14' }} /> : <StarOutlined />}
            onClick={() => handleFavorite(record)}
          />
        )
      },
    },
    {
      title: '场景',
      dataIndex: 'code',
      render: (value, record) => (
        <Space direction="vertical" size={4}>
          <Space size={8}>
            <Text strong>{value}</Text>
            {record.baseline_flag ? <Tag color="green">Baseline</Tag> : null}
            <Tag>{record.status}</Tag>
          </Space>
          <Text type="secondary">{record.name}</Text>
        </Space>
      ),
    },
    {
      title: 'Initiative',
      dataIndex: 'initiative_name',
      render: (value: string, record) => value || record.initiative_id,
    },
    {
      title: 'Owner',
      dataIndex: 'owner_id',
    },
    {
      title: '更新时间',
      dataIndex: 'updated_at',
      render: (value: string) => (value ? formatBeijingTime(value) : '--'),
    },
    {
      title: '上次导出',
      dataIndex: 'last_exported_at',
      render: (value: string | null) => (value ? formatBeijingTime(value) : '尚未导出'),
    },
    {
      title: '操作',
      key: 'actions',
      width: 200,
      render: (_value, record) => (
        <Space>
          <Tooltip title="提交审批">
            <Button
              size="small"
              icon={<SendOutlined />}
              onClick={() =>
                submitScenarioForApproval({
                  scenario_id: record.id,
                  actor_id: 'planner-ui',
                  actor_role: 'planner',
                })
                  .then(() => {
                    message.success('已提交审核')
                    queryClient.invalidateQueries({ queryKey: ['scenarios'] })
                  })
                  .catch((error) => message.error((error as Error).message || '提交失败'))
              }
            />
          </Tooltip>
          <Tooltip title="导出场景">
            <Button
              size="small"
              icon={<CloudDownloadOutlined />}
              disabled={record.status !== 'approved'}
              onClick={() =>
                exportScenario(record.id, {
                  requested_by: 'planner-ui',
                  format: 'xlsx',
                })
                  .then((res) => {
                    setJobViewer({ open: true, jobId: res.job_id, title: `导出 ${record.code}` })
                    message.success('导出任务已创建')
                  })
                  .catch((error) => message.error((error as Error).message || '导出失败'))
              }
            />
          </Tooltip>
        </Space>
      ),
    },
  ]

  const rowSelection = {
    selectedRowKeys,
    onChange: (keys: React.Key[]) => setSelectedRowKeys(keys),
  }

  const initiativeOptions =
    initiativeQuery.data?.items.map((item) => ({ label: item.name, value: item.id })) ?? []

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Card
        title="场景列表"
        extra={
          <Space>
            <Button icon={<ReloadOutlined />} onClick={() => scenarioQuery.refetch()} />
          </Space>
        }
      >
        {scenarioQuery.isError ? (
          <Alert
            type="error"
            showIcon
            closable
            message="场景列表加载失败"
            description={scenarioQueryError?.message ?? '网络异常或超时，请稍后重试'}
            style={{ marginBottom: 16 }}
          />
        ) : null}
        {initiativeQuery.isError ? (
          <Alert
            type="warning"
            showIcon
            closable
            message="Initiative 过滤项暂不可用"
            description={initiativeQueryError?.message ?? '后台接口未返回数据'}
            style={{ marginBottom: 16 }}
          />
        ) : null}
        <Space wrap style={{ marginBottom: 16 }}>
          <Input.Search
            placeholder="搜索名称或编码"
            allowClear
            value={scenarioFilters.search as string | undefined}
            onChange={(e) => {
              setScenarioFilters({ search: e.target.value, page: 1 })
            }}
            style={{ width: 220 }}
          />
          <Select
            placeholder="状态"
            allowClear
            value={scenarioFilters.status as string | undefined}
            onChange={(value) => setScenarioFilters({ status: value, page: 1 })}
            options={SCENARIO_STATUS_OPTIONS}
            style={{ width: 160 }}
          />
          <Select
            placeholder="Initiative"
            allowClear
            showSearch
            optionFilterProp="label"
            value={scenarioFilters.initiative_id as string | undefined}
            onChange={(value) => setScenarioFilters({ initiative_id: value, page: 1 })}
            options={initiativeOptions}
            style={{ width: 220 }}
          />
          <Input
            placeholder="Owner"
            allowClear
            value={scenarioFilters.owner_id as string | undefined}
            onChange={(e) => setScenarioFilters({ owner_id: e.target.value || undefined, page: 1 })}
            style={{ width: 160 }}
          />
          <Space>
            <Text>仅收藏</Text>
            <Switch
              checked={Boolean(scenarioFilters.favorite)}
              onChange={(checked) => setScenarioFilters({ favorite: checked || undefined, page: 1 })}
            />
          </Space>
          <Space>
            <Text>Baseline</Text>
            <Switch
              checked={Boolean(scenarioFilters.baseline_flag)}
              onChange={(checked) => setScenarioFilters({ baseline_flag: checked || undefined, page: 1 })}
            />
          </Space>
        </Space>
        <Space style={{ marginBottom: 16 }}>
          <Button type="primary" icon={<SendOutlined />} disabled={!selectedRowKeys.length} onClick={handleBulkSubmit}>
            批量提交
          </Button>
          <Button
            icon={<CloudDownloadOutlined />}
            disabled={!selectedRowKeys.length}
            onClick={handleBulkExport}
          >
            批量导出
          </Button>
        </Space>
        <Table
          rowKey="id"
          loading={scenarioQuery.isLoading}
          columns={columns}
          dataSource={scenarios}
          rowSelection={rowSelection}
          pagination={{
            current: scenarioFilters.page ?? 1,
            pageSize: scenarioFilters.page_size ?? 20,
            total: scenarioQuery.data?.total ?? 0,
            onChange: (page, pageSize) => setScenarioFilters({ page, page_size: pageSize }),
          }}
        />
      </Card>
      <PlannerJobDrawerLazy
        jobId={jobViewer.jobId}
        open={jobViewer.open}
        title={jobViewer.title}
        onClose={() => setJobViewer({ open: false })}
      />
    </Space>
  )
}

export default ScenarioListPage

