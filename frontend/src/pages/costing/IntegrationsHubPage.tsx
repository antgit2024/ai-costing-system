/**
 * 外部数据同步控制台.
 *
 * 用途: 集中管理所有「上游 API → 我们系统」的同步入口 (currently: 吉客云发货明细;
 * 未来: POD/PDD/天猫). 给运维 / 管理员看的「控制台」, 业务页面只放快捷按钮.
 *
 * Capabilities:
 * - 一键触发同步 (默认走水位线 + 后台异步; 可选高级参数 + 前台同步等待).
 * - 浏览最近 N 条 sync_runs, 状态/计数一目了然.
 * - 点击行展开 Drawer: 完整 run 详情 + request_params + result_json + 该次死信.
 * - 独立 Tab: 全局未处理死信列表, 一键标记已处理.
 *
 * UX 注意:
 * - 后台模式下 trigger 立即返回, sync_run_id 为空; 我们靠刷新列表 + 闪烁角标提示用户.
 * - "今天 00:00" 默认行为来自后端 _resolve_effective_start, 这里只显示 effective_start.
 */
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
  InputNumber,
  Input,
  message,
  Modal,
  Row,
  Select,
  Space,
  Table,
  Tabs,
  Tag,
  Tooltip,
  Typography,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useMemo, useState } from 'react'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import ReloadOutlined from '@ant-design/icons/lib/icons/ReloadOutlined'
import ThunderboltOutlined from '@ant-design/icons/lib/icons/ThunderboltOutlined'
import CheckCircleOutlined from '@ant-design/icons/lib/icons/CheckCircleOutlined'

import {
  type DeadLetterRead,
  type JackyunRefundSyncRequest,
  type JackyunShipmentSyncRequest,
  type SyncRunRead,
  getSyncRunDetail,
  listDeadLetters,
  listSyncRuns,
  resolveDeadLetter,
  triggerJackyunRefundSync,
  triggerJackyunShipmentSync,
} from '@/services/integrations'
import JackyunGoodsImportCard from '@/components/costing/JackyunGoodsImportCard'
import { beijingTime, formatBeijingTime, nowBeijing } from '@/utils/beijingTime'

const { Title, Text, Paragraph } = Typography

// ---------------------------------------------------------------------------
// helpers
// ---------------------------------------------------------------------------

const RUN_STATUS_COLOR: Record<string, string> = {
  succeeded: 'green',
  running: 'blue',
  failed: 'red',
  pending: 'default',
}

const formatDateTime = (value: string | null | undefined): string => {
  return formatBeijingTime(value, 'YYYY-MM-DD HH:mm:ss')
}

const formatDuration = (start?: string | null, end?: string | null): string => {
  if (!start) return '-'
  const s = beijingTime(start)
  const e = end ? beijingTime(end) : nowBeijing()
  if (!s || !e || !s.isValid() || !e.isValid()) return '-'
  const ms = Math.max(0, e.valueOf() - s.valueOf())
  const sec = Math.round(ms / 1000)
  if (sec < 60) return `${sec}s`
  const m = Math.floor(sec / 60)
  const r = sec % 60
  if (m < 60) return `${m}m${r}s`
  const h = Math.floor(m / 60)
  return `${h}h${m % 60}m`
}

const renderJsonBlock = (value: unknown) => {
  if (value === null || value === undefined) return <Text type="secondary">(空)</Text>
  let pretty = ''
  try {
    pretty = JSON.stringify(value, null, 2)
  } catch {
    pretty = String(value)
  }
  return (
    <pre
      style={{
        background: '#0f172a',
        color: '#e2e8f0',
        padding: 12,
        borderRadius: 6,
        maxHeight: 320,
        overflow: 'auto',
        fontSize: 12,
        margin: 0,
      }}
    >
      {pretty}
    </pre>
  )
}

// ---------------------------------------------------------------------------
// Trigger card (吉客云发货明细)
// ---------------------------------------------------------------------------

interface TriggerJackyunCardProps {
  onTriggered: () => void
}

const TriggerJackyunCard = ({ onTriggered }: TriggerJackyunCardProps) => {
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const [form] = Form.useForm<JackyunShipmentSyncRequest>()

  const trigger = useMutation({
    mutationFn: (body: JackyunShipmentSyncRequest) => triggerJackyunShipmentSync(body),
    onSuccess: (resp) => {
      const note = resp.note ? `\n${resp.note}` : ''
      const tail = resp.effective_start_modify_time
        ? `（实际起始 modifyTime = ${resp.effective_start_modify_time}）`
        : ''
      if (resp.mode === 'inline' && resp.run) {
        message.success(
          `同步完成：新增 ${resp.run.inserted_rows} / 更新 ${resp.run.updated_rows} / 失败 ${resp.run.error_rows}${tail}`,
        )
      } else {
        message.success(`已派发后台同步任务，请在下方运行历史查看进度。${tail}${note}`)
      }
      onTriggered()
    },
    onError: (err: any) => {
      const detail = err?.response?.data?.detail ?? err?.message ?? '未知错误'
      message.error(`触发同步失败：${detail}`)
    },
  })

  const submitQuick = () => {
    trigger.mutate({
      use_watermark: true,
      wait: false,
      triggered_by: 'ui-quick',
    })
  }

  const submitAdvanced = async () => {
    const values = await form.validateFields()
    trigger.mutate({
      ...values,
      triggered_by: values.triggered_by || 'ui-advanced',
    })
  }

  return (
    <Card
      size="small"
      title={
        <Space>
          <ThunderboltOutlined style={{ color: '#1677ff' }} />
          <span>吉客云 · 发货明细同步</span>
          <Tag color="blue">jackyun.wms.order.query-info.page.v2</Tag>
        </Space>
      }
      extra={
        <Space>
          <Button onClick={() => setAdvancedOpen(true)}>高级参数…</Button>
          <Button
            type="primary"
            icon={<ThunderboltOutlined />}
            loading={trigger.isPending}
            onClick={submitQuick}
          >
            立即同步（增量）
          </Button>
        </Space>
      }
    >
      <Paragraph type="secondary" style={{ marginBottom: 0 }}>
        默认增量模式：第一次会自动从今天 00:00 (Asia/Shanghai) 起拉取，后续根据
        <Text code>水位线 (modifyTime)</Text> 自动续跑。点击「立即同步」即可，不需要填任何参数。
        如需回填指定区间或 disable 水位线，请使用「高级参数…」。
      </Paragraph>

      <Modal
        title="高级同步参数"
        open={advancedOpen}
        onCancel={() => setAdvancedOpen(false)}
        onOk={submitAdvanced}
        okText="立即触发"
        confirmLoading={trigger.isPending}
        width={620}
      >
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 12 }}
          message="回填历史时务必谨慎"
          description="把 use_watermark 关掉 + 给一个很早的 start_modify_time 会拉很多历史数据，可能耗时很长且占用 API 配额。建议先用小区间试一次。"
        />
        <Form
          form={form}
          layout="vertical"
          initialValues={{
            page_size: 50,
            use_watermark: true,
            wait: false,
          }}
        >
          <Row gutter={12}>
            <Col span={12}>
              <Form.Item name="start_modify_time" label="start_modify_time (起，含)">
                <Input placeholder="YYYY-MM-DD HH:mm:ss，留空走水位线" allowClear />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="end_modify_time" label="end_modify_time (止，含)">
                <Input placeholder="YYYY-MM-DD HH:mm:ss，留空到现在" allowClear />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="page_size" label="page_size">
                <InputNumber min={1} max={200} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="use_watermark" label="使用水位线">
                <Select
                  options={[
                    { value: true, label: '是（推荐）' },
                    { value: false, label: '否' },
                  ]}
                />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="wait" label="等待完成">
                <Select
                  options={[
                    { value: false, label: '否（后台跑）' },
                    { value: true, label: '是（前台等）' },
                  ]}
                />
              </Form.Item>
            </Col>
            <Col span={24}>
              <Form.Item name="triggered_by" label="备注/触发者">
                <Input placeholder="例如 manual-backfill-2026-04" allowClear maxLength={64} />
              </Form.Item>
            </Col>
          </Row>
        </Form>
      </Modal>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Trigger card (吉客云售后退款)
// ---------------------------------------------------------------------------

interface TriggerJackyunRefundCardProps {
  onTriggered: () => void
}

const TriggerJackyunRefundCard = ({ onTriggered }: TriggerJackyunRefundCardProps) => {
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const [form] = Form.useForm<JackyunRefundSyncRequest>()

  const trigger = useMutation({
    mutationFn: (body: JackyunRefundSyncRequest) => triggerJackyunRefundSync(body),
    onSuccess: (resp) => {
      const note = resp.note ? `\n${resp.note}` : ''
      const tail = resp.effective_start_modify_time
        ? `（实际起始 gmtModified = ${resp.effective_start_modify_time}）`
        : ''
      if (resp.mode === 'inline' && resp.run) {
        const sup = (resp.run.result as Record<string, unknown> | null)?.superseded_excel_rows
        const supTail = typeof sup === 'number' && sup > 0 ? ` / 标记原 Excel 行 ${sup}` : ''
        message.success(
          `售后同步完成：新增 ${resp.run.inserted_rows} / 更新 ${resp.run.updated_rows} / 失败 ${resp.run.error_rows}${supTail}${tail}`,
        )
      } else {
        message.success(`已派发后台售后同步任务，请在下方运行历史查看进度。${tail}${note}`)
      }
      onTriggered()
    },
    onError: (err: any) => {
      const detail = err?.response?.data?.detail ?? err?.message ?? '未知错误'
      message.error(`触发售后同步失败：${detail}`)
    },
  })

  const submitQuick = () => {
    trigger.mutate({
      use_watermark: true,
      wait: false,
      triggered_by: 'ui-quick-refund',
    })
  }

  const submitAdvanced = async () => {
    const values = await form.validateFields()
    trigger.mutate({
      ...values,
      triggered_by: values.triggered_by || 'ui-advanced-refund',
    })
  }

  return (
    <Card
      size="small"
      title={
        <Space>
          <ThunderboltOutlined style={{ color: '#722ed1' }} />
          <span>吉客云 · 售后退款同步</span>
          <Tag color="purple">jackyun.omsapi-business.refund.listrefund.v1</Tag>
        </Space>
      }
      extra={
        <Space>
          <Button onClick={() => setAdvancedOpen(true)}>高级参数…</Button>
          <Button
            type="primary"
            icon={<ThunderboltOutlined />}
            loading={trigger.isPending}
            onClick={submitQuick}
          >
            立即同步（增量）
          </Button>
        </Space>
      }
    >
      <Paragraph type="secondary" style={{ marginBottom: 0 }}>
        默认增量模式：第一次会自动从「最近 7 天」拉取，后续根据
        <Text code>水位线 (gmtModified)</Text> 自动续跑。售后同步会
        <Text strong>升级</Text>已存在的 Excel 行（标 <Tag color="default">superseded_by_jackyun</Tag>），
        不会删除原数据。
      </Paragraph>

      <Modal
        title="高级售后同步参数"
        open={advancedOpen}
        onCancel={() => setAdvancedOpen(false)}
        onOk={submitAdvanced}
        okText="立即触发"
        confirmLoading={trigger.isPending}
        width={620}
      >
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 12 }}
          message="售后单量较小，可放心回填"
          description="omsapi-business.refund.listrefund 单店每日通常 < 100 单，回填一个月也不会有 API 配额压力。建议把 use_watermark 关掉 + 给一个 30 天前的 start，把全部历史拉一次。"
        />
        <Form
          form={form}
          layout="vertical"
          initialValues={{
            page_size: 50,
            use_watermark: true,
            wait: false,
          }}
        >
          <Row gutter={12}>
            <Col span={12}>
              <Form.Item name="start_modify_time" label="start_modify_time (起，含)">
                <Input placeholder="YYYY-MM-DD HH:mm:ss，留空走水位线" allowClear />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="end_modify_time" label="end_modify_time (止，含)">
                <Input placeholder="YYYY-MM-DD HH:mm:ss，留空到现在" allowClear />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="page_size" label="page_size">
                <InputNumber min={1} max={100} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="use_watermark" label="使用水位线">
                <Select
                  options={[
                    { value: true, label: '是（推荐）' },
                    { value: false, label: '否' },
                  ]}
                />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="wait" label="等待完成">
                <Select
                  options={[
                    { value: false, label: '否（后台跑）' },
                    { value: true, label: '是（前台等）' },
                  ]}
                />
              </Form.Item>
            </Col>
            <Col span={24}>
              <Form.Item name="triggered_by" label="备注/触发者">
                <Input placeholder="例如 manual-refund-backfill-2026-04" allowClear maxLength={64} />
              </Form.Item>
            </Col>
          </Row>
        </Form>
      </Modal>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Sync runs table + detail drawer
// ---------------------------------------------------------------------------

interface RunDetailDrawerProps {
  runId: string | null
  onClose: () => void
}

const RunDetailDrawer = ({ runId, onClose }: RunDetailDrawerProps) => {
  const detailQuery = useQuery({
    queryKey: ['integrations', 'sync-run', runId],
    queryFn: () => getSyncRunDetail(runId as string),
    enabled: !!runId,
    refetchInterval: (q) => {
      const status = q.state.data?.run?.status
      return status === 'running' || status === 'pending' ? 2000 : false
    },
  })

  const queryClient = useQueryClient()
  const resolveMutation = useMutation({
    mutationFn: (dlId: string) => resolveDeadLetter(dlId, { resolved_by: 'ui' }),
    onSuccess: () => {
      message.success('已标记为已处理')
      detailQuery.refetch()
      queryClient.invalidateQueries({ queryKey: ['integrations', 'dead-letters'] })
    },
    onError: (err: any) => {
      message.error(`处理失败：${err?.response?.data?.detail ?? err?.message ?? '未知错误'}`)
    },
  })

  const run = detailQuery.data?.run
  const deadLetters = detailQuery.data?.dead_letters ?? []

  return (
    <Drawer
      open={!!runId}
      onClose={onClose}
      title={run ? `同步详情 · ${run.api_method}` : '同步详情'}
      width={Math.min(960, typeof window !== 'undefined' ? window.innerWidth - 80 : 960)}
      destroyOnClose
    >
      {detailQuery.isLoading ? (
        <Text type="secondary">加载中…</Text>
      ) : !run ? (
        <Empty description="未找到该运行记录" />
      ) : (
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          <Card size="small" title="运行状态">
            <Descriptions size="small" column={2} bordered>
              <Descriptions.Item label="run id">{run.id}</Descriptions.Item>
              <Descriptions.Item label="状态">
                <Tag color={RUN_STATUS_COLOR[run.status] ?? 'default'}>{run.status}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="source / sync_type">
                {run.source_system} / {run.sync_type}
              </Descriptions.Item>
              <Descriptions.Item label="api_method">{run.api_method}</Descriptions.Item>
              <Descriptions.Item label="触发人">{run.triggered_by ?? '-'}</Descriptions.Item>
              <Descriptions.Item label="耗时">
                {formatDuration(run.started_at, run.finished_at)}
              </Descriptions.Item>
              <Descriptions.Item label="started_at">
                {formatDateTime(run.started_at)}
              </Descriptions.Item>
              <Descriptions.Item label="finished_at">
                {formatDateTime(run.finished_at)}
              </Descriptions.Item>
              <Descriptions.Item label="cursor 起 → 止" span={2}>
                {(run.cursor_start ?? '-') + '  →  ' + (run.cursor_end ?? '-')}
              </Descriptions.Item>
              <Descriptions.Item label="计数" span={2}>
                <Space size={12} wrap>
                  <Tag>总数 {run.total_rows}</Tag>
                  <Tag color="green">新增 {run.inserted_rows}</Tag>
                  <Tag color="blue">更新 {run.updated_rows}</Tag>
                  <Tag>跳过 {run.skipped_rows}</Tag>
                  <Tag color={run.error_rows > 0 ? 'red' : 'default'}>失败 {run.error_rows}</Tag>
                </Space>
              </Descriptions.Item>
              {run.error_message ? (
                <Descriptions.Item label="错误信息" span={2}>
                  <Text type="danger">{run.error_message}</Text>
                </Descriptions.Item>
              ) : null}
            </Descriptions>
          </Card>

          <Card size="small" title="request_params">{renderJsonBlock(run.request_params)}</Card>
          <Card size="small" title="result_json">{renderJsonBlock(run.result)}</Card>

          <Card
            size="small"
            title={
              <Space>
                <span>该次同步的死信</span>
                <Badge count={deadLetters.length} style={{ backgroundColor: '#ff4d4f' }} />
              </Space>
            }
          >
            {deadLetters.length === 0 ? (
              <Empty description="此次同步无死信记录" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            ) : (
              <Table<DeadLetterRead>
                rowKey="id"
                size="small"
                pagination={false}
                dataSource={deadLetters}
                columns={[
                  { title: 'external_id', dataIndex: 'external_id', width: 180 },
                  { title: 'stage', dataIndex: 'stage', width: 80 },
                  { title: 'attempt', dataIndex: 'attempt', width: 70 },
                  { title: 'error_type', dataIndex: 'error_type', width: 140 },
                  {
                    title: 'error_message',
                    dataIndex: 'error_message',
                    ellipsis: true,
                    render: (v: string | null) => (
                      <Tooltip title={v ?? ''}>
                        <Text type="danger" ellipsis>
                          {v ?? '-'}
                        </Text>
                      </Tooltip>
                    ),
                  },
                  {
                    title: '操作',
                    width: 110,
                    render: (_: unknown, row) =>
                      row.status === 'open' || row.status === 'retrying' ? (
                        <Button
                          size="small"
                          type="link"
                          icon={<CheckCircleOutlined />}
                          loading={resolveMutation.isPending}
                          onClick={() => resolveMutation.mutate(row.id)}
                        >
                          已处理
                        </Button>
                      ) : (
                        <Tag color="green">{row.status}</Tag>
                      ),
                  },
                ]}
              />
            )}
          </Card>
        </Space>
      )}
    </Drawer>
  )
}

// ---------------------------------------------------------------------------
// Sync runs Tab
// ---------------------------------------------------------------------------

const SyncRunsTab = ({ refreshKey }: { refreshKey: number }) => {
  const [filterSource, setFilterSource] = useState<string | undefined>('jackyun')
  const [filterStatus, setFilterStatus] = useState<string | undefined>(undefined)
  const [filterSyncType, setFilterSyncType] = useState<string | undefined>(undefined)
  const [openRunId, setOpenRunId] = useState<string | null>(null)

  const runsQuery = useQuery({
    queryKey: ['integrations', 'sync-runs', { filterSource, filterStatus, filterSyncType, refreshKey }],
    queryFn: () =>
      listSyncRuns({
        source_system: filterSource,
        sync_type: filterSyncType,
        status: filterStatus,
        limit: 100,
      }),
    refetchInterval: (q) => {
      const items = (q.state.data ?? []) as SyncRunRead[]
      const hasRunning = items.some((r) => r.status === 'running' || r.status === 'pending')
      return hasRunning ? 3000 : 15000
    },
    placeholderData: keepPreviousData,
  })

  const columns: ColumnsType<SyncRunRead> = [
    {
      title: '触发时间',
      dataIndex: 'started_at',
      width: 170,
      render: (v: string | null) => formatDateTime(v),
    },
    { title: 'source', dataIndex: 'source_system', width: 90 },
    { title: 'sync_type', dataIndex: 'sync_type', width: 130 },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (s: string) => <Tag color={RUN_STATUS_COLOR[s] ?? 'default'}>{s}</Tag>,
    },
    {
      title: '总',
      dataIndex: 'total_rows',
      width: 60,
      align: 'right',
    },
    {
      title: '新增',
      dataIndex: 'inserted_rows',
      width: 70,
      align: 'right',
      render: (n: number) => (n > 0 ? <Text type="success">{n}</Text> : n),
    },
    {
      title: '更新',
      dataIndex: 'updated_rows',
      width: 70,
      align: 'right',
    },
    {
      title: '失败',
      dataIndex: 'error_rows',
      width: 70,
      align: 'right',
      render: (n: number) => (n > 0 ? <Text type="danger">{n}</Text> : n),
    },
    {
      title: '耗时',
      width: 90,
      render: (_: unknown, r) => formatDuration(r.started_at, r.finished_at),
    },
    { title: '触发人', dataIndex: 'triggered_by', width: 130 },
    {
      title: '操作',
      width: 90,
      render: (_: unknown, r) => (
        <Button size="small" type="link" onClick={() => setOpenRunId(r.id)}>
          详情
        </Button>
      ),
    },
  ]

  return (
    <>
      <Space style={{ marginBottom: 12 }} wrap>
        <Select
          allowClear
          placeholder="source_system"
          style={{ width: 160 }}
          value={filterSource}
          onChange={setFilterSource}
          options={[{ value: 'jackyun', label: 'jackyun (吉客云)' }]}
        />
        <Select
          allowClear
          placeholder="同步类型"
          style={{ width: 180 }}
          value={filterSyncType}
          onChange={setFilterSyncType}
          options={[
            { value: 'shipment_pull', label: 'shipment_pull (发货)' },
            { value: 'refund_pull', label: 'refund_pull (售后)' },
          ]}
        />
        <Select
          allowClear
          placeholder="状态"
          style={{ width: 160 }}
          value={filterStatus}
          onChange={setFilterStatus}
          options={[
            { value: 'succeeded', label: 'succeeded' },
            { value: 'running', label: 'running' },
            { value: 'failed', label: 'failed' },
            { value: 'pending', label: 'pending' },
          ]}
        />
        <Button icon={<ReloadOutlined />} onClick={() => runsQuery.refetch()}>
          刷新
        </Button>
      </Space>

      <Table<SyncRunRead>
        rowKey="id"
        size="small"
        loading={runsQuery.isLoading || runsQuery.isFetching}
        columns={columns}
        dataSource={runsQuery.data ?? []}
        pagination={{ pageSize: 20, showSizeChanger: false }}
        onRow={(r) => ({
          style: { cursor: 'pointer' },
          onClick: () => setOpenRunId(r.id),
        })}
      />

      <RunDetailDrawer runId={openRunId} onClose={() => setOpenRunId(null)} />
    </>
  )
}

// ---------------------------------------------------------------------------
// Dead letters Tab (global)
// ---------------------------------------------------------------------------

const DeadLettersTab = () => {
  const [filterSource, setFilterSource] = useState<string | undefined>(undefined)

  const queryClient = useQueryClient()
  const dlQuery = useQuery({
    queryKey: ['integrations', 'dead-letters', { filterSource }],
    queryFn: () => listDeadLetters({ source_system: filterSource, limit: 200 }),
    refetchInterval: 30000,
  })

  const resolveMutation = useMutation({
    mutationFn: (dlId: string) => resolveDeadLetter(dlId, { resolved_by: 'ui' }),
    onSuccess: () => {
      message.success('已标记为已处理')
      dlQuery.refetch()
      queryClient.invalidateQueries({ queryKey: ['integrations', 'sync-run'] })
    },
    onError: (err: any) => {
      message.error(`处理失败：${err?.response?.data?.detail ?? err?.message ?? '未知错误'}`)
    },
  })

  const items = dlQuery.data?.items ?? []

  const columns: ColumnsType<DeadLetterRead> = [
    { title: 'source', dataIndex: 'source_system', width: 90 },
    { title: 'record_type', dataIndex: 'record_type', width: 110 },
    { title: 'stage', dataIndex: 'stage', width: 90 },
    { title: 'external_id', dataIndex: 'external_id', width: 180 },
    { title: 'attempt', dataIndex: 'attempt', width: 70, align: 'right' },
    { title: 'error_type', dataIndex: 'error_type', width: 150 },
    {
      title: 'error_message',
      dataIndex: 'error_message',
      ellipsis: true,
      render: (v: string | null) => (
        <Tooltip title={v ?? ''}>
          <Text type="danger" ellipsis>
            {v ?? '-'}
          </Text>
        </Tooltip>
      ),
    },
    {
      title: '最近尝试',
      dataIndex: 'last_attempt_at',
      width: 170,
      render: (v: string | null) => formatDateTime(v),
    },
    {
      title: '操作',
      width: 110,
      render: (_: unknown, row) => (
        <Button
          size="small"
          type="link"
          icon={<CheckCircleOutlined />}
          loading={resolveMutation.isPending}
          onClick={() => resolveMutation.mutate(row.id)}
        >
          标记已处理
        </Button>
      ),
    },
  ]

  return (
    <>
      <Space style={{ marginBottom: 12 }} wrap>
        <Select
          allowClear
          placeholder="source_system"
          style={{ width: 160 }}
          value={filterSource}
          onChange={setFilterSource}
          options={[{ value: 'jackyun', label: 'jackyun (吉客云)' }]}
        />
        <Button icon={<ReloadOutlined />} onClick={() => dlQuery.refetch()}>
          刷新
        </Button>
        <Badge count={items.length} style={{ backgroundColor: items.length ? '#ff4d4f' : '#999' }}>
          <Tag>未处理 / 重试中</Tag>
        </Badge>
      </Space>

      <Table<DeadLetterRead>
        rowKey="id"
        size="small"
        loading={dlQuery.isLoading || dlQuery.isFetching}
        columns={columns}
        dataSource={items}
        pagination={{ pageSize: 20, showSizeChanger: false }}
        locale={{ emptyText: <Empty description="暂无待处理死信" image={Empty.PRESENTED_IMAGE_SIMPLE} /> }}
      />
    </>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

const IntegrationsHubPage = () => {
  const [refreshKey, setRefreshKey] = useState(0)
  const bumpRefresh = () => setRefreshKey((x) => x + 1)

  const tabItems = useMemo(
    () => [
      {
        key: 'runs',
        label: '运行历史',
        children: <SyncRunsTab refreshKey={refreshKey} />,
      },
      {
        key: 'dead-letters',
        label: '死信队列',
        children: <DeadLettersTab />,
      },
    ],
    [refreshKey],
  )

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <div>
        <Title level={4} style={{ marginBottom: 4 }}>
          外部数据同步
        </Title>
        <Text type="secondary">
          统一管理所有上游 API 同步：吉客云（已接入）、POD/PDD（规划中）。底层走通用整合层（带原始 payload 留底、增量水位线、死信队列）。
        </Text>
      </div>

      <TriggerJackyunCard onTriggered={bumpRefresh} />
      <TriggerJackyunRefundCard onTriggered={bumpRefresh} />
      <JackyunGoodsImportCard onCommitted={bumpRefresh} />

      <Card size="small">
        <Tabs items={tabItems} />
      </Card>
    </Space>
  )
}

export default IntegrationsHubPage
