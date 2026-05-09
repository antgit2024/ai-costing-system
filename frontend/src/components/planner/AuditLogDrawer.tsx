import { useCallback, useEffect, useMemo, useState } from 'react'
import { Button, Drawer, Empty, Input, List, Pagination, Skeleton, Space, Tag, Tooltip, Typography } from 'antd'
import CopyOutlined from '@ant-design/icons/lib/icons/CopyOutlined'
import ReloadOutlined from '@ant-design/icons/lib/icons/ReloadOutlined'
import SearchOutlined from '@ant-design/icons/lib/icons/SearchOutlined'
import type { AxiosError } from 'axios'
import type { AuditLogEntry } from '@/types/planner'
import { fetchAuditLogs } from '@/services/planner'
import { formatBeijingTime } from '@/utils/beijingTime'

const { Text } = Typography

export interface AuditLogDrawerProps {
  scenarioId?: string
  open: boolean
  onClose: () => void
}

const isAxiosNotFoundError = (error: unknown): error is AxiosError => {
  return Boolean((error as AxiosError)?.response?.status === 404)
}

const AuditLogDrawer = ({ scenarioId, open, onClose }: AuditLogDrawerProps) => {
  const [logs, setLogs] = useState<AuditLogEntry[]>([])
  const [loading, setLoading] = useState(false)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(10)
  const [total, setTotal] = useState(0)
  const [search, setSearch] = useState('')
  const [traceId, setTraceId] = useState('')
  const [auditUnavailable, setAuditUnavailable] = useState(false)
  const [auditError, setAuditError] = useState<Error | null>(null)

  const loadLogs = useCallback(async () => {
    if (!open || !scenarioId) {
      return
    }
    setLoading(true)
    setAuditError(null)
    try {
      const response = await fetchAuditLogs({
        target_type: 'scenario',
        target_id: scenarioId,
        page,
        page_size: pageSize,
        search: search || undefined,
        trace_id: traceId || undefined,
      })
      setLogs(response.items)
      setTotal(response.total)
      setAuditUnavailable(false)
    } catch (error) {
      if (isAxiosNotFoundError(error)) {
        setAuditUnavailable(true)
        setLogs([])
        setTotal(0)
      } else {
        setAuditError(error as Error)
      }
    } finally {
      setLoading(false)
    }
  }, [open, scenarioId, page, pageSize, search, traceId])

  useEffect(() => {
    if (!open || !scenarioId) {
      return
    }
    setAuditUnavailable(false)
    loadLogs()
  }, [open, scenarioId, loadLogs])

  const handleReload = () => {
    setAuditUnavailable(false)
    loadLogs()
  }

  const handleCopy = async (value?: string | Record<string, unknown>) => {
    if (!value) return
    const text = typeof value === 'string' ? value : JSON.stringify(value, null, 2)
    try {
      await navigator.clipboard.writeText(text)
    } catch (error) {
      console.error('copy failed', error)
    }
  }

  const content = useMemo(() => {
    if (auditUnavailable) {
      return (
        <Empty
          description={
            <Space direction="vertical" size={4}>
              <Text>后端尚未提供审计接口，暂无法展示日志</Text>
              <Button type="link" onClick={handleReload}>
                重新检查
              </Button>
            </Space>
          }
        />
      )
    }

    if (loading) {
      return <Skeleton active paragraph={{ rows: 8 }} />
    }

    if (auditError) {
      return (
        <Empty
          description={
            <Space direction="vertical" size={4}>
              <Text>审计日志加载失败：{auditError.message}</Text>
              <Button type="link" onClick={handleReload}>
                重试
              </Button>
            </Space>
          }
        />
      )
    }

    if (!logs.length) {
      return <Empty description="暂无审计记录" />
    }
    return (
      <>
        <List
          dataSource={logs}
          renderItem={(log) => (
            <List.Item key={log.id}>
              <Space direction="vertical" size={4} style={{ width: '100%' }}>
                <Space size={8} wrap>
                  <Tag color="blue">{log.action}</Tag>
                  <Text strong>{log.actor_id}</Text>
                  <Text type="secondary">{formatBeijingTime(log.created_at)}</Text>
                  {log.trace_id ? (
                    <Tooltip title="复制 Trace ID">
                      <Button size="small" icon={<CopyOutlined />} onClick={() => handleCopy(log.trace_id)}>
                        {log.trace_id}
                      </Button>
                    </Tooltip>
                  ) : null}
                </Space>
                {log.comment ? <Text>{log.comment}</Text> : null}
                {log.metadata ? (
                  <Space direction="vertical" size={4} style={{ width: '100%' }}>
                    <Space size={8}>
                      <Text type="secondary">Metadata</Text>
                      <Button size="small" type="link" icon={<CopyOutlined />} onClick={() => handleCopy(log.metadata)}>
                        复制
                      </Button>
                    </Space>
                    <pre style={{ margin: 0, background: '#f5f5f5', padding: 8, borderRadius: 6 }}>
                      {JSON.stringify(log.metadata, null, 2)}
                    </pre>
                  </Space>
                ) : null}
              </Space>
            </List.Item>
          )}
        />
        <Pagination
          style={{ marginTop: 16, textAlign: 'right' }}
          current={page}
          pageSize={pageSize}
          total={total}
          onChange={(nextPage, nextSize) => {
            setPage(nextPage)
            setPageSize(nextSize ?? pageSize)
          }}
        />
      </>
    )
  }, [logs, loading, page, pageSize, total])

  return (
    <Drawer
      width={520}
      open={open}
      onClose={() => {
        setPage(1)
        setSearch('')
        setTraceId('')
        setAuditUnavailable(false)
        setAuditError(null)
        onClose()
      }}
      title="审计日志"
      destroyOnClose
    >
      <Space direction="vertical" size={12} style={{ width: '100%', marginBottom: 16 }}>
        <Input
          allowClear
          prefix={<SearchOutlined />}
          placeholder="搜索动作或备注"
          value={search}
          onChange={(e) => {
            setAuditUnavailable(false)
            setAuditError(null)
            setPage(1)
            setSearch(e.target.value)
          }}
        />
        <Input
          allowClear
          placeholder="Trace ID 过滤"
          value={traceId}
          onChange={(e) => {
            setAuditUnavailable(false)
            setAuditError(null)
            setPage(1)
            setTraceId(e.target.value)
          }}
        />
        <Button icon={<ReloadOutlined />} onClick={handleReload}>
          刷新
        </Button>
      </Space>
      {content}
    </Drawer>
  )
}

export default AuditLogDrawer

