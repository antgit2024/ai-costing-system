import { useEffect, useMemo, useState } from 'react'
import {
  Alert,
  Button,
  Card,
  Col,
  Divider,
  Empty,
  Form,
  Input,
  List,
  Pagination,
  Row,
  Select,
  Space,
  Spin,
  Statistic,
  Steps,
  Table,
  Tag,
  Timeline,
  Tooltip,
  Typography,
  message,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import BulbOutlined from '@ant-design/icons/lib/icons/BulbOutlined'
import DownloadOutlined from '@ant-design/icons/lib/icons/DownloadOutlined'
import FileSearchOutlined from '@ant-design/icons/lib/icons/FileSearchOutlined'
import RocketOutlined from '@ant-design/icons/lib/icons/RocketOutlined'
import StarFilled from '@ant-design/icons/lib/icons/StarFilled'
import StarOutlined from '@ant-design/icons/lib/icons/StarOutlined'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import type { AxiosError } from 'axios'
import type {
  ApprovalActionResponse,
  BenchmarkFavorite,
  BenchmarkSuggestion,
  ScenarioDiffLine,
  ScenarioDiffResponse,
} from '@/types/planner'
import {
  approveScenario,
  rejectScenario,
  cloneScenario,
  exportScenario,
  fetchScenarioDiff,
  fetchBenchmarkFavorites,
  fetchBenchmarkSuggestions,
  fetchScenarios,
  fetchAuditLogs,
  removeBenchmarkFavorite,
  saveBenchmarkFavorite,
  submitScenarioForApproval,
} from '@/services/planner'
import PlannerJobDrawerLazy from '@/components/planner/PlannerJobDrawerLazy'
import AuditLogDrawerLazy from '@/components/planner/AuditLogDrawerLazy'
import { LINE_ITEM_TYPE_OPTIONS } from '@/constants/planner'
import type { PlannerJobKind } from '@/types/planner'

const { Title, Paragraph, Text } = Typography

const isAxiosNotFoundError = (error: unknown): error is AxiosError & { response: { status: 404 } } => {
  if (!error || typeof error !== 'object') {
    return false
  }
  return (error as AxiosError).response?.status === 404
}

const ScenarioBuilderPage = () => {
  const queryClient = useQueryClient()
  const [selectedScenarioId, setSelectedScenarioId] = useState<string>()
  const [jobViewer, setJobViewer] = useState<{ open: boolean; jobId?: string; title?: string; kind: PlannerJobKind }>({
    open: false,
    jobId: undefined,
    title: undefined,
    kind: 'planner',
  })
  const [auditViewer, setAuditViewer] = useState<{ open: boolean; scenarioId?: string }>({ open: false })
  const [cloneForm] = Form.useForm()
  const [diffForm] = Form.useForm()
  const [approvalForm] = Form.useForm()
  const [exportForm] = Form.useForm()
  const [benchmarkForm] = Form.useForm()
  const [diffResult, setDiffResult] = useState<ScenarioDiffResponse | null>(null)
  const [diffLoading, setDiffLoading] = useState(false)
  const [diffState, setDiffState] = useState({
    scenarioId: '',
    against: '',
    type: undefined as string | undefined,
    page: 1,
    pageSize: 10,
  })
  const [benchmarkState, setBenchmarkState] = useState<{
    loading: boolean
    suggestions: BenchmarkSuggestion[]
  }>({
    loading: false,
    suggestions: [],
  })
  const [exportHistorySearch, setExportHistorySearch] = useState('')
  const [exportHistoryPage, setExportHistoryPage] = useState(1)
  const [exportHistoryPageSize, setExportHistoryPageSize] = useState(5)
  const [auditUnavailable, setAuditUnavailable] = useState(false)

  const scenarioListQuery = useQuery({
    queryKey: ['scenario-builder-scenarios'],
    queryFn: () => fetchScenarios({ page: 1, page_size: 100 }),
  })
  const scenarios = scenarioListQuery.data?.items ?? []
  const scenarioListError = scenarioListQuery.error as Error | null

  const benchmarkFavoritesQuery = useQuery({
    queryKey: ['benchmark-favorites'],
    queryFn: fetchBenchmarkFavorites,
  })
  const benchmarkFavoritesError = benchmarkFavoritesQuery.error as Error | null

  const benchmarkFavoriteMap = useMemo(() => {
    const map: Record<string, string> = {}
    benchmarkFavoritesQuery.data?.forEach((fav: BenchmarkFavorite) => {
      map[fav.suggestion_id] = fav.id
    })
    return map
  }, [benchmarkFavoritesQuery.data])

  useEffect(() => {
    if (!selectedScenarioId && scenarios.length) {
      setSelectedScenarioId(scenarios[0].id)
    }
  }, [scenarios, selectedScenarioId])

  useEffect(() => {
    if (selectedScenarioId) {
      cloneForm.setFieldsValue({ baseline_scenario_id: selectedScenarioId })
      diffForm.setFieldsValue({ scenarioId: selectedScenarioId })
      approvalForm.setFieldsValue({ scenario_id: selectedScenarioId })
      exportForm.setFieldsValue({ scenario_id: selectedScenarioId })
      benchmarkForm.setFieldsValue({ scenario_id: selectedScenarioId })
    }
  }, [selectedScenarioId, cloneForm, diffForm, approvalForm, exportForm, benchmarkForm])

  useEffect(() => {
    setAuditUnavailable(false)
  }, [selectedScenarioId])

  const exportHistoryQuery = useQuery({
    enabled: Boolean(selectedScenarioId) && !auditUnavailable,
    queryKey: ['scenario-export-history', selectedScenarioId, exportHistoryPage, exportHistoryPageSize, exportHistorySearch],
    queryFn: () =>
      fetchAuditLogs({
        target_type: 'scenario',
        target_id: selectedScenarioId!,
        action: 'scenario_export',
        page: exportHistoryPage,
        page_size: exportHistoryPageSize,
        search: exportHistorySearch || undefined,
      }),
    retry: (failureCount, error) => {
      if (isAxiosNotFoundError(error)) {
        return false
      }
      return failureCount < 2
    },
  })
  const exportHistoryError = exportHistoryQuery.error as AxiosError | null

  const exportHistoryItems = exportHistoryQuery.data?.items ?? []
  const activeScenario = scenarios.find((scenario) => scenario.id === selectedScenarioId)

  const scenarioOptions = useMemo(
    () =>
      scenarios.map((scenario) => ({
        label: `${scenario.code} · ${scenario.name}`,
        value: scenario.id,
      })),
    [scenarios],
  )

  const isFormValidationError = (error: unknown): error is { errorFields: unknown[] } =>
    Boolean(error && typeof error === 'object' && 'errorFields' in error)

  useEffect(() => {
    if (scenarioListError) {
      message.error(`场景列表加载失败：${scenarioListError.message}`)
    }
  }, [scenarioListError])

  useEffect(() => {
    if (!exportHistoryError) {
      return
    }
    if (isAxiosNotFoundError(exportHistoryError)) {
      if (!auditUnavailable) {
        setAuditUnavailable(true)
        queryClient.removeQueries({ queryKey: ['scenario-export-history'] })
        message.info('后端尚未提供审计接口，暂无法展示导出历史')
      }
      return
    }
    message.warning(`导出历史暂不可用：${exportHistoryError?.message ?? '未知错误'}`)
  }, [exportHistoryError, auditUnavailable, queryClient])

  useEffect(() => {
    if (benchmarkFavoritesError) {
      message.warning(`AI 收藏状态无法加载：${benchmarkFavoritesError.message}`)
    }
  }, [benchmarkFavoritesError])

  const copyText = async (value?: string) => {
    if (!value) return
    try {
      await navigator.clipboard.writeText(value)
      message.success('已复制')
    } catch {
      message.warning('复制失败')
    }
  }

  const startScenarioExport = async (scenarioId: string, format?: string, requestedBy = 'planner-ui') => {
    const hide = message.loading('正在创建导出任务...', 0)
    try {
      const response = await exportScenario(scenarioId, {
        requested_by: requestedBy,
        format,
      })
      message.success('导出任务已触发')
      setJobViewer({ open: true, jobId: response.job_id, title: '场景导出', kind: 'planner' })
      if (selectedScenarioId === scenarioId) {
        exportHistoryQuery.refetch()
      }
    } finally {
      hide()
    }
  }

  const handleExportScenario = async () => {
    try {
      const values = await exportForm.validateFields()
      await startScenarioExport(values.scenario_id, values.format, values.requested_by)
    } catch (error) {
      if (isFormValidationError(error)) {
        return
      }
      message.error((error as Error).message || '导出失败')
    }
  }

  const quickExportScenario = async (scenarioId: string) => {
    try {
      await startScenarioExport(scenarioId)
    } catch (error) {
      message.error((error as Error).message || '导出失败')
    }
  }

  const handleFetchBenchmarks = async () => {
    let hide: (() => void) | undefined
    try {
      const values = await benchmarkForm.validateFields()
      setBenchmarkState((prev) => ({ ...prev, loading: true }))
      hide = message.loading('AI 建议获取中...', 0)
      const suggestions = await fetchBenchmarkSuggestions({
        scenario_id: values.scenario_id,
        limit: values.limit,
        owner_id: activeScenario?.owner_id,
      })
      setBenchmarkState((prev) => ({
        ...prev,
        loading: false,
        suggestions,
      }))
      message.success('AI 建议已更新')
    } catch (error) {
      setBenchmarkState((prev) => ({ ...prev, loading: false }))
      if (isFormValidationError(error)) {
        return
      }
      message.error((error as Error).message || '获取建议失败')
    } finally {
      hide?.()
    }
  }

  const handleBenchmarkFavoriteToggle = async (suggestion: BenchmarkSuggestion) => {
    if (!selectedScenarioId) {
      message.info('请选择场景')
      return
    }
    const favoriteId = benchmarkFavoriteMap[suggestion.id]
    let hide: (() => void) | undefined
    try {
      hide = message.loading('更新收藏状态...', 0)
      if (favoriteId) {
        await removeBenchmarkFavorite(favoriteId)
        message.success('已取消收藏')
      } else {
        await saveBenchmarkFavorite({
          suggestion_id: suggestion.id,
          scenario_id: selectedScenarioId,
          notes: suggestion.recommendation,
        })
        message.success('已收藏')
      }
      queryClient.invalidateQueries({ queryKey: ['benchmark-favorites'] })
    } catch (error) {
      message.error((error as Error).message || '收藏操作失败')
    } finally {
      hide?.()
    }
  }

  const openAuditDrawer = (scenarioId: string) => {
    setAuditViewer({ open: true, scenarioId })
  }

  const retryExportHistory = () => {
    setAuditUnavailable(false)
    exportHistoryQuery.refetch()
  }

  const handleClone = async () => {
    let hide: (() => void) | undefined
    try {
      const values = await cloneForm.validateFields()
      const lineItemIds: string[] | undefined = values.line_item_ids
        ? String(values.line_item_ids)
            .split(',')
            .map((id: string) => id.trim())
            .filter(Boolean)
        : undefined
      hide = message.loading('正在克隆基线...', 0)
      const response = await cloneScenario(values.baseline_scenario_id, {
        code: values.code,
        name: values.name,
        requested_by: values.requested_by,
        line_item_ids: lineItemIds,
      })
      message.success('克隆任务已提交并完成')
      setSelectedScenarioId(response.scenario_id)
      queryClient.invalidateQueries({ queryKey: ['scenario-builder-scenarios'] })
      setJobViewer({ open: true, jobId: response.job_id, title: '场景克隆任务', kind: 'planner' })
      cloneForm.resetFields(['code', 'name', 'line_item_ids'])
    } catch (error) {
      if (isFormValidationError(error)) {
        return
      }
      message.error((error as Error).message || '克隆失败')
    } finally {
      hide?.()
    }
  }

  const runDiff = async (overrides?: Partial<typeof diffState>) => {
    const formValues = diffForm.getFieldsValue()
    const scenarioId = formValues.scenarioId ?? diffState.scenarioId
    const against = formValues.against ?? diffState.against
    const type = formValues.type ?? diffState.type
    const next = { ...diffState, ...overrides, scenarioId, against, type }
    if (!next.scenarioId || !next.against) {
      message.warning('请选择来源和对比场景')
      return
    }
    setDiffState(next)
    setDiffLoading(true)
    let hide: (() => void) | undefined
    try {
      hide = message.loading('差异分析进行中...', 0)
      const response = await fetchScenarioDiff(next.scenarioId, {
        against: next.against,
        page: next.page,
        page_size: next.pageSize,
        type: next.type,
      })
      setDiffResult(response)
      setJobViewer({ open: true, jobId: response.job_id, title: '差异分析', kind: 'planner' })
      message.success('差异分析已完成')
    } catch (error) {
      message.error((error as Error).message || '差异分析失败')
    } finally {
      setDiffLoading(false)
      hide?.()
    }
  }

  const handleApprovalAction = async (action: 'submit' | 'approve' | 'reject') => {
    let hide: (() => void) | undefined
    try {
      const values = await approvalForm.validateFields()
      hide = message.loading('审批操作进行中...', 0)
      const response: ApprovalActionResponse =
        action === 'submit'
          ? await submitScenarioForApproval(values)
          : action === 'approve'
            ? await approveScenario(values)
            : await rejectScenario(values)
      message.success(`场景${action === 'submit' ? '提交' : action === 'approve' ? '批准' : '驳回'}成功`)
      queryClient.invalidateQueries({ queryKey: ['scenario-builder-scenarios'] })
      setSelectedScenarioId(response.scenario_id)
    } catch (error) {
      if (isFormValidationError(error)) {
        return
      }
      message.error((error as Error).message || '操作失败')
    } finally {
      hide?.()
    }
  }

  const diffColumns: ColumnsType<ScenarioDiffLine> = [
    {
      title: '行项目',
      dataIndex: 'description',
      width: 220,
    },
    {
      title: '参考码',
      dataIndex: 'reference_code',
      width: 120,
    },
    {
      title: '包/分类',
      dataIndex: 'package_name',
      width: 160,
      render: (value: string, record) => value || record.package_id,
    },
    {
      title: '类型',
      dataIndex: 'item_type',
      width: 120,
      render: (value: string) => value || '未定义',
    },
    {
      title: '数量差异',
      dataIndex: 'quantity_diff',
      width: 140,
    },
    {
      title: '单价差异',
      dataIndex: 'unit_cost_diff',
      width: 140,
    },
    {
      title: '合计差异',
      dataIndex: 'total_cost_diff',
      width: 160,
    },
  ]

  const diffSummary = diffResult?.summary

  return (
    <Space direction="vertical" size={24} style={{ width: '100%' }}>
      <Card>
        <Row justify="space-between" align="middle">
          <Col>
            <Title level={3} style={{ margin: 0 }}>
              场景建模工作区
            </Title>
            <Paragraph type="secondary" style={{ marginBottom: 0 }}>
              克隆基线、执行差异分析，完成审批闭环。
            </Paragraph>
          </Col>
          <Col>
            <Button type="primary" icon={<RocketOutlined />} onClick={() => runDiff()}>
              运行差异分析
            </Button>
          </Col>
        </Row>
      </Card>

      <Row gutter={24}>
        <Col xs={24} lg={10}>
          <Card title="场景列表">
            {scenarioListQuery.isError ? (
              <Alert
                showIcon
                type="error"
                closable
                message="场景列表加载失败"
                description={scenarioListError?.message ?? '网络异常或权限受限'}
                style={{ marginBottom: 16 }}
              />
            ) : null}
            {scenarioListQuery.isLoading ? (
              <Spin />
            ) : scenarios.length === 0 ? (
              <Empty description="暂无场景" />
            ) : (
              <Space direction="vertical" style={{ width: '100%' }}>
                {scenarios.map((scenario) => {
                  const isActive = scenario.id === selectedScenarioId
                  return (
                    <Card
                      key={scenario.id}
                      size="small"
                      hoverable
                      onClick={() => setSelectedScenarioId(scenario.id)}
                      style={{
                        borderColor: isActive
                          ? '#3057e1'
                          : scenario.baseline_flag
                            ? '#52c41a'
                            : 'var(--app-border)',
                        background: isActive ? 'rgba(48,87,225,0.10)' : 'var(--app-bg-elevated)',
                        cursor: 'pointer',
                      }}
                    >
                      <Space direction="vertical" size={4} style={{ width: '100%' }}>
                        <Space size={8} wrap>
                          <Text strong>{scenario.code}</Text>
                          <Tag color={scenario.baseline_flag ? 'green' : 'blue'}>
                            {scenario.baseline_flag ? 'Baseline' : scenario.status}
                          </Tag>
                        </Space>
                        <Text type="secondary">{scenario.name}</Text>
                        <Space size={12} wrap>
                          <Text type="secondary">Owner: {scenario.owner_id || '未指定'}</Text>
                          <Text type="secondary">
                            更新: {scenario.updated_at ? new Date(scenario.updated_at).toLocaleString() : '—'}
                          </Text>
                        </Space>
                        <Space size={8} wrap>
                          <Button
                            size="small"
                            type="link"
                            icon={<DownloadOutlined />}
                            onClick={(event) => {
                              event.stopPropagation()
                              quickExportScenario(scenario.id)
                            }}
                          >
                            导出
                          </Button>
                          <Button
                            size="small"
                            type="link"
                            icon={<FileSearchOutlined />}
                            onClick={(event) => {
                              event.stopPropagation()
                              openAuditDrawer(scenario.id)
                            }}
                          >
                            审计
                          </Button>
                        </Space>
                      </Space>
                    </Card>
                  )
                })}
              </Space>
            )}
            <Form
              layout="inline"
              form={exportForm}
              style={{ marginTop: 16 }}
              onFinish={handleExportScenario}
              initialValues={{ format: 'xlsx', requested_by: 'planner-ui' }}
            >
              <Form.Item
                name="scenario_id"
                rules={[{ required: true, message: '请选择要导出的场景' }]}
              >
                <Select
                  placeholder="选择场景导出"
                  showSearch
                  options={scenarioOptions}
                  optionFilterProp="label"
                  style={{ minWidth: 200 }}
                />
              </Form.Item>
              <Form.Item name="format">
                <Select
                  style={{ width: 120 }}
                  options={[
                    { value: 'xlsx', label: 'Excel' },
                    { value: 'csv', label: 'CSV' },
                  ]}
                />
              </Form.Item>
              <Form.Item name="requested_by">
                <Input placeholder="请求人" style={{ width: 160 }} />
              </Form.Item>
              <Button type="primary" htmlType="submit" icon={<DownloadOutlined />}>
                导出场景
              </Button>
            </Form>
          </Card>
          <Card style={{ marginTop: 24 }} title="导出历史">
            {!selectedScenarioId ? (
              <Empty description="请选择场景" />
            ) : (
              <Space direction="vertical" style={{ width: '100%' }}>
                {auditUnavailable ? (
                  <Alert
                    type="info"
                    showIcon
                    message="后端尚未提供审计接口，暂无法展示导出历史"
                    description="接口上线后可点击“重新检查”刷新结果。"
                    action={
                      <Button size="small" type="link" onClick={retryExportHistory}>
                        重新检查
                      </Button>
                    }
                  />
                ) : (
                  <>
                    <Input.Search
                      allowClear
                      placeholder="搜索 Trace / 备注"
                      value={exportHistorySearch}
                      onChange={(e) => {
                        setExportHistorySearch(e.target.value)
                        setExportHistoryPage(1)
                      }}
                    />
                    {exportHistoryQuery.isError ? (
                      <Alert
                        type="warning"
                        showIcon
                        closable
                        message="导出历史暂不可用"
                        description={exportHistoryError?.message ?? '请检查网络或稍后重试'}
                        style={{ marginBottom: 16 }}
                      />
                    ) : null}
                    {exportHistoryQuery.isLoading ? (
                      <Spin />
                    ) : exportHistoryItems.length === 0 ? (
                      <Empty description="暂无导出记录" />
                    ) : (
                      <>
                        <Timeline
                          items={exportHistoryItems.map((log) => ({
                            color: 'blue',
                            children: (
                              <Space direction="vertical" size={4} style={{ width: '100%' }}>
                                <Space size={8} wrap>
                                  <Text strong>{log.actor_id}</Text>
                                  <Text type="secondary">{new Date(log.created_at).toLocaleString()}</Text>
                                  {log.trace_id ? (
                                    <Tooltip title="复制 Trace ID">
                                      <Button size="small" type="link" onClick={() => copyText(log.trace_id!)}>
                                        {log.trace_id}
                                      </Button>
                                    </Tooltip>
                                  ) : null}
                                </Space>
                                <Text>{log.comment || '无备注'}</Text>
                              </Space>
                            ),
                          }))}
                        />
                        <Pagination
                          style={{ textAlign: 'right' }}
                          current={exportHistoryPage}
                          pageSize={exportHistoryPageSize}
                          total={exportHistoryQuery.data?.total ?? 0}
                          onChange={(page, pageSize) => {
                            setExportHistoryPage(page)
                            setExportHistoryPageSize(pageSize ?? exportHistoryPageSize)
                          }}
                        />
                      </>
                    )}
                  </>
                )}
              </Space>
            )}
          </Card>
          <Card style={{ marginTop: 24 }} title="建模步骤">
            <Steps
              direction="vertical"
              current={2}
              items={[
                { title: '克隆基线', description: '选择 approved baseline 执行快照' },
                { title: '差异分析', description: '与目标场景对比，定位成本差异' },
                { title: '审批', description: '提交领导审批并可设为 baseline' },
              ]}
            />
          </Card>
        </Col>
        <Col xs={24} lg={14}>
          <Card title="克隆基线">
            <Form layout="vertical" form={cloneForm} initialValues={{ requested_by: 'planner-ui' }}>
              <Form.Item
                name="baseline_scenario_id"
                label="基线场景 ID"
                rules={[{ required: true, message: '请输入基线场景 ID' }]}
              >
                <Input placeholder="例如：SCENARIO-UUID" />
              </Form.Item>
              <Form.Item name="code" label="新场景编码" rules={[{ required: true }]}>
                <Input />
              </Form.Item>
              <Form.Item name="name" label="场景名称" rules={[{ required: true }]}>
                <Input />
              </Form.Item>
              <Form.Item name="requested_by" label="请求人" rules={[{ required: true }]}>
                <Input />
              </Form.Item>
              <Form.Item name="line_item_ids" label="限定行项目（可选，逗号分隔）">
                <Input.TextArea rows={2} placeholder="留空表示克隆全部" />
              </Form.Item>
              <Button type="primary" onClick={handleClone}>
                克隆基线
              </Button>
            </Form>
          </Card>

          <Divider />

          <Card title="审批流">
            <Form layout="vertical" form={approvalForm}>
              <Form.Item
                name="scenario_id"
                label="场景"
                rules={[{ required: true, message: '请选择场景' }]}
              >
                <Select
                  options={scenarioOptions}
                  showSearch
                  placeholder="选择或输入场景 ID"
                  optionFilterProp="label"
                />
              </Form.Item>
              <Form.Item name="actor_id" label="操作者 ID" rules={[{ required: true }]}>
                <Input />
              </Form.Item>
              <Form.Item name="actor_role" label="角色" rules={[{ required: true }]}>
                <Select
                  options={[
                    { label: 'Planner', value: 'planner' },
                    { label: 'Analyst', value: 'analyst' },
                    { label: 'Approver', value: 'approver' },
                    { label: 'Exec', value: 'exec' },
                  ]}
                />
              </Form.Item>
              <Form.Item name="comment" label="备注">
                <Input.TextArea rows={2} />
              </Form.Item>
              <Form.Item name="set_baseline" label="批准时设为 Baseline" initialValue={true}>
                <Select
                  options={[
                    { label: '是', value: true },
                    { label: '否', value: false },
                  ]}
                />
              </Form.Item>
              <Space>
                <Button onClick={() => handleApprovalAction('submit')}>提交审核</Button>
                <Button type="primary" onClick={() => handleApprovalAction('approve')}>
                  批准
                </Button>
                <Button danger onClick={() => handleApprovalAction('reject')}>
                  驳回
                </Button>
              </Space>
            </Form>
          </Card>
          <Card title="AI Benchmark 建议" style={{ marginTop: 24 }}>
            {benchmarkFavoritesQuery.isFetching ? null : benchmarkFavoritesError ? (
              <Alert
                type="warning"
                showIcon
                closable
                message="AI 收藏状态暂不可用"
                description={benchmarkFavoritesError?.message ?? '收藏接口未返回数据'}
                style={{ marginBottom: 12 }}
              />
            ) : null}
            <Form
              layout="inline"
              form={benchmarkForm}
              onFinish={handleFetchBenchmarks}
              style={{ marginBottom: 16 }}
            >
              <Form.Item
                name="scenario_id"
                rules={[{ required: true, message: '请选择需要分析的场景' }]}
              >
                <Select
                  placeholder="选择场景"
                  showSearch
                  options={scenarioOptions}
                  optionFilterProp="label"
                  style={{ minWidth: 200 }}
                />
              </Form.Item>
              <Form.Item name="limit" initialValue={5}>
                <Select
                  style={{ width: 120 }}
                  options={[
                    { label: 'Top 3', value: 3 },
                    { label: 'Top 5', value: 5 },
                    { label: 'Top 10', value: 10 },
                  ]}
                />
              </Form.Item>
              <Button type="primary" htmlType="submit" icon={<BulbOutlined />}>
                获取建议
              </Button>
            </Form>
            <List
              loading={benchmarkState.loading}
              dataSource={benchmarkState.suggestions}
              locale={{ emptyText: benchmarkState.loading ? '加载中...' : '暂无建议' }}
              renderItem={(item) => {
                const favoriteId = benchmarkFavoriteMap[item.id]
                const isFavorite = Boolean(favoriteId)
                return (
                  <List.Item
                    key={item.id}
                    actions={[
                      <Button
                        type="link"
                        icon={isFavorite ? <StarFilled /> : <StarOutlined />}
                        onClick={() => handleBenchmarkFavoriteToggle(item)}
                      >
                        {isFavorite ? '已收藏' : '收藏'}
                      </Button>,
                    ]}
                  >
                    <List.Item.Meta
                      title={
                        <Space size={8} wrap>
                          <Text strong>{item.title}</Text>
                          {item.impact ? <Tag color="purple">{item.impact}</Tag> : null}
                          {item.supplier_name ? <Tag>{item.supplier_name}</Tag> : null}
                          {item.currency ? <Tag>{item.currency}</Tag> : null}
                        </Space>
                      }
                      description={item.description || 'AI 建议描述待补充'}
                    />
                    {item.recommendation ? (
                      <Text type="secondary">{item.recommendation}</Text>
                    ) : null}
                    {item.freshness ? (
                      <Text type="secondary" style={{ display: 'block' }}>
                        数据时间：{item.freshness}
                      </Text>
                    ) : null}
                  </List.Item>
                )
              }}
            />
          </Card>
        </Col>
      </Row>

      <Card title="差异分析">
        <Form
          layout="inline"
          form={diffForm}
          style={{ marginBottom: 16 }}
          onFinish={() => runDiff({ page: 1 })}
        >
          <Form.Item
            name="scenarioId"
            label="来源场景"
            rules={[{ required: true, message: '请选择来源场景' }]}
          >
            <Select options={scenarioOptions} showSearch placeholder="选择来源" optionFilterProp="label" />
          </Form.Item>
          <Form.Item name="against" label="对比场景" rules={[{ required: true }]}>
            <Select options={scenarioOptions} showSearch placeholder="选择对比目标" optionFilterProp="label" />
          </Form.Item>
          <Form.Item name="type" label="物料类型">
            <Select allowClear placeholder="全部类型" options={LINE_ITEM_TYPE_OPTIONS} />
          </Form.Item>
          <Button type="primary" htmlType="submit">
            获取差异
          </Button>
        </Form>

        {diffSummary ? (
          <Space size={24}>
            <Statistic
              title="来源成本"
              prefix="¥"
              value={Number(diffSummary.total_cost_source)}
              precision={2}
            />
            <Statistic
              title="目标成本"
              prefix="¥"
              value={Number(diffSummary.total_cost_target)}
              precision={2}
            />
            <Statistic
              title="差异"
              prefix="¥"
              value={Number(diffSummary.variance)}
              precision={2}
            />
            <Statistic title="差异%" suffix="%" value={diffSummary.variance_percent.toFixed(2)} />
          </Space>
        ) : (
          <Paragraph type="secondary">尚未生成差异报告。</Paragraph>
        )}

        <Table
          style={{ marginTop: 16 }}
          rowKey="line_item_id"
          loading={diffLoading}
          columns={diffColumns}
          dataSource={diffResult?.line_diffs ?? []}
          pagination={{
            current: diffResult?.page ?? diffState.page,
            pageSize: diffResult?.page_size ?? diffState.pageSize,
            total: diffResult?.total ?? 0,
            onChange: (page, pageSize) => runDiff({ page, pageSize: pageSize ?? diffState.pageSize }),
          }}
        />
      </Card>

      <PlannerJobDrawerLazy
        jobId={jobViewer.jobId}
        open={jobViewer.open}
        title={jobViewer.title}
        kind={jobViewer.kind}
        onClose={() => setJobViewer((prev) => ({ ...prev, open: false }))}
      />
      <AuditLogDrawerLazy
        scenarioId={auditViewer.scenarioId}
        open={auditViewer.open}
        onClose={() => setAuditViewer({ open: false, scenarioId: undefined })}
      />
    </Space>
  )
}

export default ScenarioBuilderPage

