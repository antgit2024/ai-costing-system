import { useMemo } from 'react'
import { Button, Drawer, Descriptions, Divider, Skeleton, Space, Tag, Tooltip, Typography } from 'antd'
import CopyOutlined from '@ant-design/icons/lib/icons/CopyOutlined'
import ExportOutlined from '@ant-design/icons/lib/icons/ExportOutlined'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'

import { fetchMaterialSyncJob } from '@/services/planner'
import type { MaterialSyncJobRead } from '@/types/planner'

const { Text } = Typography

const jobStatusColor: Record<string, string> = {
  pending: 'default',
  running: 'blue',
  succeeded: 'green',
  completed: 'green',
  failed: 'red',
}

const fmtDuration = (start?: string | null, end?: string | null) => {
  if (!start) return '-'
  const s = Date.parse(start)
  const e = end ? Date.parse(end) : Date.now()
  if (!Number.isFinite(s) || !Number.isFinite(e)) return '-'
  const ms = Math.max(0, e - s)
  const sec = Math.round(ms / 1000)
  if (sec < 60) return `${sec}s`
  const min = Math.floor(sec / 60)
  const rem = sec % 60
  if (min < 60) return `${min}m${rem}s`
  const h = Math.floor(min / 60)
  const m = min % 60
  return `${h}h${m}m`
}

export interface MaterialSyncJobDrawerProps {
  jobId?: string
  open: boolean
  onClose: () => void
}

const MaterialSyncJobDrawer = ({ jobId, open, onClose }: MaterialSyncJobDrawerProps) => {
  const navigate = useNavigate()
  const jobQuery = useQuery<MaterialSyncJobRead>({
    queryKey: ['material-sync-job', jobId],
    queryFn: () => fetchMaterialSyncJob(jobId!),
    enabled: Boolean(jobId) && open,
    refetchInterval: (q) => {
      const status = q.state.data?.status
      if (!status) return 2000
      return ['succeeded', 'completed', 'failed'].includes(String(status)) ? false : 2000
    },
  })

  const job = jobQuery.data

  const duration = useMemo(
    () => fmtDuration(job?.started_at ?? job?.created_at, job?.finished_at ?? null),
    [job?.created_at, job?.finished_at, job?.started_at],
  )

  const copyText = async (value?: string) => {
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
      width={520}
      onClose={onClose}
      destroyOnClose
      title="任务详情（物料）"
      extra={
        <Space>
          <Button icon={<ExportOutlined />} onClick={() => navigate('/costing/materials')}>
            跳转到物料管理
          </Button>
        </Space>
      }
    >
      {!job ? (
        <Skeleton active paragraph={{ rows: 8 }} />
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
            <Descriptions.Item label="类型">{job.job_type}</Descriptions.Item>
            <Descriptions.Item label="状态">
              <Tag color={jobStatusColor[job.status] ?? 'default'}>{job.status}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="耗时">{duration}</Descriptions.Item>
            <Descriptions.Item label="创建时间">{job.created_at}</Descriptions.Item>
            {job.started_at ? <Descriptions.Item label="开始时间">{job.started_at}</Descriptions.Item> : null}
            {job.finished_at ? <Descriptions.Item label="完成时间">{job.finished_at}</Descriptions.Item> : null}
            {job.error_message ? (
              <Descriptions.Item label="错误">
                <Text style={{ color: '#cf1322' }}>{job.error_message}</Text>
              </Descriptions.Item>
            ) : null}
          </Descriptions>

          <Divider />

          <Space direction="vertical" style={{ width: '100%' }}>
            <Space align="center">
              <Text strong>Payload</Text>
              <Button
                size="small"
                type="link"
                icon={<CopyOutlined />}
                onClick={() => copyText(JSON.stringify(job.payload ?? {}, null, 2))}
              >
                复制
              </Button>
            </Space>
            <pre style={{ maxHeight: 200, overflow: 'auto', background: '#f7f8fa', padding: 12 }}>
              {JSON.stringify(job.payload ?? {}, null, 2)}
            </pre>

            <Space align="center">
              <Text strong>Result</Text>
              <Button
                size="small"
                type="link"
                icon={<CopyOutlined />}
                onClick={() => copyText(JSON.stringify(job.result_json ?? {}, null, 2))}
              >
                复制
              </Button>
            </Space>
            <pre style={{ maxHeight: 200, overflow: 'auto', background: '#f7f8fa', padding: 12 }}>
              {JSON.stringify(job.result_json ?? {}, null, 2)}
            </pre>
          </Space>
        </Space>
      )}
    </Drawer>
  )
}

export default MaterialSyncJobDrawer


