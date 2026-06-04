import { useMemo, useState } from 'react'
import { Badge, Button, Drawer, List, Progress, Space, Tag, Tooltip, Typography } from 'antd'
import ReloadOutlined from '@ant-design/icons/lib/icons/ReloadOutlined'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'

import { fetchTaskCenter, type TaskCenterItem } from '@/services/planner'
import PlannerJobDrawerLazy from '@/components/planner/PlannerJobDrawerLazy'
import MaterialSyncJobDrawer from '@/components/common/MaterialSyncJobDrawer'

const { Text } = Typography

const runningStatuses = new Set(['pending', 'running', 'processing'])

const statusColor = (status: string) => {
  if (status === 'failed') return 'red'
  if (status === 'succeeded' || status === 'completed') return 'green'
  if (status === 'completed_with_errors') return 'orange'
  if (status === 'running' || status === 'processing') return 'blue'
  return 'default'
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

export interface TaskCenterDrawerProps {
  open: boolean
  onClose: () => void
}

const TaskCenterDrawer = ({ open, onClose }: TaskCenterDrawerProps) => {
  const navigate = useNavigate()
  const [limit, setLimit] = useState(50)
  const [selected, setSelected] = useState<TaskCenterItem | null>(null)
  const [plannerDetailOpen, setPlannerDetailOpen] = useState(false)
  const [materialDetailOpen, setMaterialDetailOpen] = useState(false)
  const tasksQuery = useQuery({
    queryKey: ['task-center', { limit }],
    queryFn: () => fetchTaskCenter({ limit }),
    enabled: open,
    refetchInterval: (q) => {
      const items = q.state.data?.items ?? []
      const hasRunning = items.some((t) => runningStatuses.has(String(t.status)))
      return hasRunning ? 2000 : 8000
    },
  })

  const items = tasksQuery.data?.items ?? []

  const runningCount = useMemo(
    () => items.filter((t) => runningStatuses.has(String(t.status))).length,
    [items],
  )

  const openDetail = (item: TaskCenterItem) => {
    setSelected(item)
    if (item.source === 'material') {
      setMaterialDetailOpen(true)
      return
    }
    setPlannerDetailOpen(true)
  }

  const plannerJumpTarget = (item: TaskCenterItem | null) => {
    if (!item) return '/planner'
    const payload = (item.payload ?? {}) as Record<string, unknown>
    if (payload.scenario_id) return '/planner/scenarios'
    return '/planner'
  }

  return (
    <Drawer
      open={open}
      width={560}
      onClose={onClose}
      destroyOnClose
      title={
        <Space>
          <span>任务列表</span>
          <Badge count={runningCount} size="small" />
        </Space>
      }
      extra={
        <Space>
          <Button
            icon={<ReloadOutlined />}
            onClick={() => tasksQuery.refetch()}
            loading={tasksQuery.isFetching}
          >
            刷新
          </Button>
          <Button onClick={() => setLimit((v) => (v >= 100 ? 50 : 100))}>
            {limit >= 100 ? '仅看 50 条' : '看 100 条'}
          </Button>
        </Space>
      }
    >
      <List<TaskCenterItem>
        loading={tasksQuery.isLoading}
        dataSource={items}
        locale={{ emptyText: '暂无任务' }}
        renderItem={(item) => {
          const total = item.progress_total ?? undefined
          const current = item.progress_current ?? undefined
          const percent =
            typeof total === 'number' && total > 0 && typeof current === 'number'
              ? Math.min(100, Math.round((current / total) * 100))
              : runningStatuses.has(String(item.status))
                ? 10
                : item.status === 'completed' || item.status === 'succeeded'
                  ? 100
                  : 0
          const duration = fmtDuration(item.started_at ?? item.created_at, item.finished_at ?? null)
          return (
            <List.Item
              style={{ cursor: 'pointer' }}
              onClick={() => openDetail(item)}
            >
              <Space direction="vertical" size={4} style={{ width: '100%' }}>
                <Space wrap style={{ width: '100%', justifyContent: 'space-between' }}>
                  <Space wrap>
                    <Tag color={item.source === 'material' ? 'geekblue' : 'purple'}>
                      {item.source === 'material' ? '物料' : 'Planner'}
                    </Tag>
                    <Text strong>{item.title || item.job_type}</Text>
                    <Tag color={statusColor(String(item.status))}>{item.status}</Tag>
                    <Text type="secondary">耗时 {duration}</Text>
                  </Space>
                  <Tooltip title={`任务ID：${item.id}`}>
                    <Text code>{String(item.id).slice(0, 8)}…</Text>
                  </Tooltip>
                </Space>

                {typeof total === 'number' && typeof current === 'number' ? (
                  <Text type="secondary">
                    进度：{current}/{total}
                  </Text>
                ) : null}
                <Progress percent={percent} size="small" showInfo={false} />

                {item.error_message ? (
                  <Text style={{ color: '#cf1322' }} ellipsis={{ tooltip: item.error_message }}>
                    {item.error_message}
                  </Text>
                ) : null}
              </Space>
            </List.Item>
          )
        }}
      />

      <PlannerJobDrawerLazy
        open={plannerDetailOpen}
        jobId={selected?.source === 'planner' ? selected.id : undefined}
        kind="planner"
        onClose={() => setPlannerDetailOpen(false)}
        title="任务详情（Planner）"
        extraActions={
          <Button onClick={() => navigate(plannerJumpTarget(selected))}>
            跳转
          </Button>
        }
      />

      <MaterialSyncJobDrawer
        open={materialDetailOpen}
        jobId={selected?.source === 'material' ? selected.id : undefined}
        onClose={() => setMaterialDetailOpen(false)}
      />
    </Drawer>
  )
}

export default TaskCenterDrawer


