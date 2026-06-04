import { Alert, Button, Card, Checkbox, Input, Space, Table, Tag, Typography, message, Modal } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import dayjs from 'dayjs'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import { computeShipmentLineSnapshot, fetchShipmentLines } from '@/services/planner'
import type { ShipmentLineComputeSnapshotResponse, ShipmentLineListItem } from '@/types/planner'

const { Text } = Typography

const safeString = (v: unknown): string => {
  if (v === null || v === undefined) return ''
  return String(v)
}

const formatDate = (v?: string | null) => {
  if (!v) return '-'
  const d = dayjs(v)
  return d.isValid() ? d.format('YYYY-MM-DD') : String(v)
}

const pick = (sp: URLSearchParams, k: string): string | undefined => {
  const v = String(sp.get(k) ?? '').trim()
  return v || undefined
}

export default function BulkCostingTab() {
  const [sp] = useSearchParams()

  const [operatorId, setOperatorId] = useState('planner_user')
  const [limit, setLimit] = useState(() => {
    const n = Number(sp.get('limit') ?? 200)
    return Number.isFinite(n) && n > 0 ? Math.min(Math.max(Math.floor(n), 1), 2000) : 200
  })
  const [overwrite, setOverwrite] = useState(() => String(sp.get('overwrite') ?? '').trim() === '1')
  const [loading, setLoading] = useState(false)
  const [running, setRunning] = useState(false)
  const stopRef = useRef(false)
  const [items, setItems] = useState<ShipmentLineListItem[]>([])
  const previewAbortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    return () => {
      try {
        previewAbortRef.current?.abort()
      } catch {
        // ignore
      } finally {
        previewAbortRef.current = null
      }
    }
  }, [])

  const filters = useMemo(() => {
    const start = pick(sp, 'start')
    const end = pick(sp, 'end')
    const statusRaw = pick(sp, 'status')
    const status: 'processed' | 'pending' | undefined =
      statusRaw === 'processed' || statusRaw === 'pending' ? statusRaw : undefined
    return {
      from: pick(sp, 'from'),
      start,
      end,
      status,
      channel: pick(sp, 'channel'),
      sku_code: pick(sp, 'sku_code'),
      order_no: pick(sp, 'order_no'),
      product_link_id: pick(sp, 'product_link_id'),
      spec_text: pick(sp, 'spec_text'),
      unresolved_reason: pick(sp, 'unresolved_reason'),
    }
  }, [sp])

  const preview = async () => {
    setLoading(true)
    try {
      // Cancel any in-flight preview request (avoid piling up)
      try {
        previewAbortRef.current?.abort()
      } catch {
        // ignore
      }
      previewAbortRef.current = new AbortController()

      const pageSize = Math.min(Math.max(Math.floor(limit || 200), 1), 500)
      const resp = await fetchShipmentLines({
        page: 1,
        page_size: pageSize,
        start: filters.start,
        end: filters.end,
        status: filters.status,
        channel: filters.channel,
        sku_code: filters.sku_code,
        order_no: filters.order_no,
        product_link_id: filters.product_link_id,
        spec_text: filters.spec_text,
        unresolved_reason: filters.unresolved_reason,
      }, { signal: previewAbortRef.current.signal })
      setItems((resp.items ?? []) as any)
      message.success(`已加载 ${Math.min(resp.items?.length ?? 0, pageSize)} 条（上限 ${pageSize}）`)
    } catch (err: any) {
      // If request was canceled due to new preview/unmount, do nothing.
      const code = String(err?.code ?? '')
      if (code === 'ERR_CANCELED' || code === 'ECONNABORTED') return
      message.error(`加载失败：${err?.response?.data?.detail ?? err?.message ?? 'unknown error'}`)
    } finally {
      setLoading(false)
    }
  }

  const run = async () => {
    if (!items.length) {
      message.info('请先点击“预览范围”加载要处理的发货行')
      return
    }
    if (running) return

    const ok = await new Promise<boolean>((resolve) => {
      Modal.confirm({
        title: overwrite ? '确认覆盖重算？（高风险）' : '确认批量计价快照？',
        content: overwrite
          ? '将对列表内每条记录执行“覆盖重算”（若已有快照会覆盖写回）。建议先缩小范围。'
          : '将对列表内每条记录执行“只补齐缺失”（已有快照/计价结果会跳过）。',
        okText: overwrite ? '确认覆盖重算' : '确认执行',
        okButtonProps: overwrite ? { danger: true } : undefined,
        cancelText: '取消',
        onOk: () => resolve(true),
        onCancel: () => resolve(false),
      })
    })
    if (!ok) return

    stopRef.current = false
    setRunning(true)

    const key = 'bulk-costing'
    message.loading({ content: `批量处理中... 0/${items.length}`, key, duration: 0 })
    let okCount = 0
    let failCount = 0
    let skipCount = 0

    for (let i = 0; i < items.length; i += 1) {
      if (stopRef.current) break
      const line = items[i] as any
      const id = safeString(line?.id).trim()
      if (!id) continue

      // client-side skip for missing-only mode
      if (!overwrite && safeString(line?.status).trim() === 'processed') {
        skipCount += 1
        message.loading({
          content: `批量处理中... ${Math.min(i + 1, items.length)}/${items.length}（成功${okCount} 跳过${skipCount} 失败${failCount}）`,
          key,
          duration: 0,
        })
        continue
      }

      try {
        const res: ShipmentLineComputeSnapshotResponse = await computeShipmentLineSnapshot(id, {
          operator_id: operatorId?.trim() || undefined,
          overwrite: !!overwrite,
        })
        if (res.action === 'skipped') skipCount += 1
        else if (res.action === 'failed') failCount += 1
        else okCount += 1
      } catch {
        failCount += 1
      }

      message.loading({
        content: `批量处理中... ${Math.min(i + 1, items.length)}/${items.length}（成功${okCount} 跳过${skipCount} 失败${failCount}）`,
        key,
        duration: 0,
      })
    }

    message.destroy(key)
    setRunning(false)
    if (stopRef.current) message.warning(`已停止：成功${okCount} 跳过${skipCount} 失败${failCount}`)
    else message.success(`完成：成功${okCount} 跳过${skipCount} 失败${failCount}`)
  }

  const columns = useMemo<ColumnsType<ShipmentLineListItem>>(
    () => [
      { title: '发货日期', dataIndex: 'completed_at', width: 110, render: (v) => formatDate(v as any) },
      { title: '店铺', dataIndex: 'channel', width: 120, ellipsis: true },
      { title: 'SKU', dataIndex: 'sku_code', width: 160, ellipsis: true },
      {
        title: '状态',
        key: 'status',
        width: 120,
        render: (_v, r: any) =>
          safeString(r?.status).trim() === 'processed' ? <Tag color="green">已处理</Tag> : <Tag color="red">待处理</Tag>,
      },
      { title: '快照ID', dataIndex: 'bom_snapshot_id', width: 160, ellipsis: true, render: (v) => safeString(v) || '-' },
      { title: '待处理原因', dataIndex: 'unresolved_reason', width: 160, ellipsis: true, render: (v) => safeString(v) || '-' },
      { title: '交易规格', dataIndex: 'spec_text', ellipsis: true, render: (v) => safeString(v) || '-' },
    ],
    [],
  )

  const summary = useMemo(() => {
    const parts: string[] = []
    const s = (k: string, label: string) => {
      const v = (filters as any)[k]
      if (v) parts.push(`${label}=${v}`)
    }
    s('start', 'start')
    s('end', 'end')
    s('status', 'status')
    s('channel', '店铺')
    s('sku_code', 'SKU')
    s('spec_text', '交易规格')
    s('unresolved_reason', '状态')
    return parts.join('；') || '（未携带筛选条件：请从发货台账点击“批量计价快照”进入）'
  }, [filters])

  return (
    <Space direction="vertical" style={{ width: '100%' }} size={12}>
      <Alert type="info" showIcon message="本页按“发货台账的当前筛选范围”批量执行" description={<Text>{summary}</Text>} />

      <Card size="small" title="执行参数">
        <Space wrap>
          <Input
            style={{ width: 180 }}
            placeholder="operator_id（可空）"
            value={operatorId}
            onChange={(e) => setOperatorId(e.target.value)}
          />
          <Input
            style={{ width: 120 }}
            placeholder="最多处理N条"
            value={String(limit)}
            onChange={(e) => setLimit(Number(e.target.value) || 200)}
          />
          <Checkbox checked={overwrite} onChange={(e) => setOverwrite(e.target.checked)}>
            覆盖重算（高风险）
          </Checkbox>
          <Button onClick={preview} loading={loading}>
            预览范围
          </Button>
          <Button type="primary" danger={overwrite} onClick={run} loading={running} disabled={!items.length}>
            {overwrite ? '开始覆盖重算' : '开始计价快照（只补齐缺失）'}
          </Button>
          <Button
            disabled={!running}
            onClick={() => {
              stopRef.current = true
            }}
          >
            停止
          </Button>
        </Space>
      </Card>

      <Card size="small" title={`待处理列表（当前加载：${items.length}条）`}>
        <Table
          rowKey={(r) => String((r as any)?.id ?? '')}
          size="small"
          bordered
          scroll={{ x: 1200 }}
          loading={loading}
          columns={columns}
          dataSource={items as any}
          pagination={{ pageSize: 50, showSizeChanger: true }}
        />
      </Card>
    </Space>
  )
}

