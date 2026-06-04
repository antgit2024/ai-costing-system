import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { Button, Drawer, Descriptions, Divider, Input, List, Progress, Skeleton, Space, Tag, Tooltip, Typography } from 'antd'
import CopyOutlined from '@ant-design/icons/lib/icons/CopyOutlined'
import SearchOutlined from '@ant-design/icons/lib/icons/SearchOutlined'
import type { ImportJob, PlannerJob, PlannerJobKind } from '@/types/planner'
import { usePlannerJob } from '@/hooks/usePlannerJob'
import { terminalImportStatuses, terminalPlannerJobStatuses } from '@/types/planner'

const { Text } = Typography

const jobStatusColor: Record<string, string> = {
  pending: 'default',
  processing: 'blue',
  completed: 'green',
  completed_with_errors: 'orange',
  failed: 'red',
}

export interface PlannerJobDrawerProps {
  jobId?: string
  kind?: PlannerJobKind
  open: boolean
  title?: string
  width?: number
  onClose: () => void
  onJobSettled?: () => void
  extraActions?: ReactNode
}

type JobResult = PlannerJob | ImportJob

const isPlannerJob = (job: JobResult | undefined): job is PlannerJob => Boolean(job && 'payload' in job)

const PlannerJobDrawer = ({
  jobId,
  kind = 'planner',
  open,
  title,
  width = 480,
  onClose,
  onJobSettled,
  extraActions,
}: PlannerJobDrawerProps) => {
  const jobQuery = usePlannerJob(jobId, kind, open)
  const job = jobQuery.data
  const plannerJob = isPlannerJob(job) ? job : undefined
  const [errorSearch, setErrorSearch] = useState('')

  useEffect(() => {
    if (!job) return
    const terminal =
      kind === 'import'
        ? terminalImportStatuses.includes(job.status)
        : terminalPlannerJobStatuses.includes(job.status)
    if (terminal) {
      onJobSettled?.()
    }
  }, [job, kind, onJobSettled])

  const totalRows = job && 'total_rows' in job ? job.total_rows : 0
  const processedRows = job && 'processed_rows' in job ? job.processed_rows : 0
  const percent = totalRows > 0 ? Math.round((processedRows / totalRows) * 100) : job?.status === 'completed' ? 100 : 0
  const traceId =
    (plannerJob?.trace_id as string) ||
    ((plannerJob?.payload as Record<string, unknown>)?.trace_id as string) ||
    ((plannerJob?.result as Record<string, unknown>)?.trace_id as string)
  const externalRef =
    (plannerJob?.result?.executor_reference as string) ||
    (plannerJob?.result?.reference_id as string)

  const filteredErrors = useMemo(() => {
    if (!job?.errors?.length) {
      return []
    }
    if (!errorSearch) {
      return job.errors
    }
    return job.errors.filter((err) =>
      `${err.row}:${err.error}`.toLowerCase().includes(errorSearch.toLowerCase()),
    )
  }, [job?.errors, errorSearch])

  const copyText = async (value?: string | number) => {
    if (!value) return
    try {
      await navigator.clipboard.writeText(String(value))
    } catch (error) {
      console.error('copy failed', error)
    }
  }

  return (
    <Drawer
      open={open}
      width={width}
      onClose={onClose}
      destroyOnClose
      title={title ?? '作业进度'}
      extra={extraActions}
    >
      {!job ? (
        <Skeleton active paragraph={{ rows: 6 }} />
      ) : (
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          <Descriptions column={1} colon={false} size="small">
            <Descriptions.Item label="任务 ID">
              <Space size={8}>
                <Text code>{job.id}</Text>
                <Tooltip title="复制任务 ID">
                  <Button size="small" icon={<CopyOutlined />} onClick={() => copyText(job.id)} />
                </Tooltip>
              </Space>
            </Descriptions.Item>
            {traceId ? (
              <Descriptions.Item label="Trace ID">
                <Space size={8}>
                  <Text code>{traceId}</Text>
                  <Tooltip title="复制 Trace ID">
                    <Button size="small" icon={<CopyOutlined />} onClick={() => copyText(traceId)} />
                  </Tooltip>
                </Space>
              </Descriptions.Item>
            ) : null}
            {plannerJob ? (
              <Descriptions.Item label="类型">{plannerJob.job_type}</Descriptions.Item>
            ) : (
              <Descriptions.Item label="类型">import_csv</Descriptions.Item>
            )}
            {externalRef ? (
              <Descriptions.Item label="外部引用">
                <Space size={8}>
                  <Text code>{externalRef}</Text>
                  <Tooltip title="复制引用号">
                    <Button size="small" icon={<CopyOutlined />} onClick={() => copyText(externalRef)} />
                  </Tooltip>
                </Space>
              </Descriptions.Item>
            ) : null}
            <Descriptions.Item label="状态">
              <Tag color={jobStatusColor[job.status] ?? 'default'}>{job.status}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="进度">
              <Progress percent={percent} status={job.status === 'failed' ? 'exception' : undefined} />
              <Text type="secondary">
                {processedRows}/{totalRows} rows
              </Text>
            </Descriptions.Item>
          </Descriptions>

          {job.errors?.length ? (
            <Space direction="vertical" style={{ width: '100%' }}>
              <Input
                allowClear
                size="small"
                prefix={<SearchOutlined />}
                placeholder="搜索错误"
                value={errorSearch}
                onChange={(e) => setErrorSearch(e.target.value)}
              />
              <List
                size="small"
                bordered
                dataSource={filteredErrors}
                header={<Text strong>错误详情</Text>}
                locale={{ emptyText: '无匹配错误' }}
                renderItem={(item) => (
                  <List.Item>
                    <Space direction="vertical" size={0}>
                      <Text strong>行 {item.row}</Text>
                      <Text type="secondary">{item.error}</Text>
                    </Space>
                  </List.Item>
                )}
              />
            </Space>
          ) : null}

          {plannerJob ? (
            <>
              <Divider />
              <Space direction="vertical" style={{ width: '100%' }}>
                <Space align="center">
                  <Text strong>Payload</Text>
                  <Button
                    size="small"
                    type="link"
                    icon={<CopyOutlined />}
                    onClick={() => copyText(JSON.stringify(plannerJob.payload, null, 2))}
                  >
                    复制
                  </Button>
                </Space>
                <pre style={{ maxHeight: 160, overflow: 'auto', background: '#f7f8fa', padding: 12 }}>
                  {JSON.stringify(plannerJob.payload, null, 2)}
                </pre>
                {plannerJob.result ? (
                  <>
                    <Space align="center">
                      <Text strong>Result</Text>
                      <Button
                        size="small"
                        type="link"
                        icon={<CopyOutlined />}
                        onClick={() => copyText(JSON.stringify(plannerJob.result, null, 2))}
                      >
                        复制
                      </Button>
                    </Space>
                    <pre style={{ maxHeight: 160, overflow: 'auto', background: '#f7f8fa', padding: 12 }}>
                      {JSON.stringify(plannerJob.result, null, 2)}
                    </pre>
                  </>
                ) : null}
              </Space>
            </>
          ) : null}
        </Space>
      )}
    </Drawer>
  )
}

export default PlannerJobDrawer

