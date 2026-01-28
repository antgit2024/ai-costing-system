import { Alert, Button, Card, Col, Input, Row, Segmented, Space, Table, Tabs, Tag, Typography, message, Modal } from 'antd'
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table'
import dayjs from 'dayjs'
import { useEffect, useMemo, useRef, useState } from 'react'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'

import {
  fetchShipmentImportBatch,
  fetchShipmentImportBatches,
  fetchShipmentExceptions,
  fetchShipmentBomSnapshots,
  computeShipmentLineSnapshot,
  recomputeShipmentBomSnapshot,
  retryShipmentExceptions,
} from '@/services/planner'
import type { BomSnapshot, ShipmentException, ShipmentImportBatch } from '@/types/planner'

const { Text } = Typography

const safeString = (v: unknown): string => {
  if (v === null || v === undefined) return ''
  return String(v)
}

const formatTime = (v?: string | null) => {
  if (!v) return '-'
  const d = dayjs(v)
  return d.isValid() ? d.format('YYYY-MM-DD HH:mm:ss') : String(v)
}

const formatBatchStatus = (statusRaw: unknown): { label: string; color?: string } => {
  const s0 = safeString(statusRaw).trim()
  const s = s0.toLowerCase()
  if (!s) return { label: '未知', color: 'default' }
  if (s === 'success') return { label: '成功', color: 'green' }
  if (s === 'processing') return { label: '处理中', color: 'blue' }
  if (s === 'failed') return { label: '失败', color: 'red' }
  if (s === 'pending' || s === 'queued') return { label: '排队中', color: 'default' }
  return { label: s0, color: 'default' }
}

const formatExceptionReason = (reasonRaw: unknown): string => {
  const r0 = safeString(reasonRaw).trim()
  const r = r0.toUpperCase()
  if (!r) return '未知'
  const map: Record<string, string> = {
    SKU_NOT_BOUND: '未绑定',
    SPEC_EMPTY: '缺规格',
    SPEC_PARSE_FAILED: '规格解析失败',
    BOM_GENERATION_FAILED: 'BOM失败',
    MODEL_VERSION_NOT_FOUND: '模型版本不存在',
    MODEL_VERSION_NOT_PUBLISHED: '模型版本未发布',
    MISSING_SKU_CODE: '缺条码',
    MISSING_SKU: '缺条码',
  }
  return map[r] ? `${map[r]}（${r}）` : r0
}

export default function BatchWorkbench(props: { onOpenImport: () => void }) {
  const queryClient = useQueryClient()
  const [sp, setSp] = useSearchParams()

  const [batchPage, setBatchPage] = useState(1)
  const [batchPageSize, setBatchPageSize] = useState(20)
  const [selectedBatchId, setSelectedBatchId] = useState<string>('')

  const [exceptionResolved, setExceptionResolved] = useState<'unresolved' | 'resolved' | 'all'>('unresolved')
  const [exceptionLimit, setExceptionLimit] = useState(200)
  const [operatorId, setOperatorId] = useState('planner_user')
  const [excFilterSkuCode, setExcFilterSkuCode] = useState<string>('')
  const [excFilterChannel, setExcFilterChannel] = useState<string>('')
  const [excFilterSpecText, setExcFilterSpecText] = useState<string>('')
  const [excSelectedRowKeys, setExcSelectedRowKeys] = useState<React.Key[]>([])

  const [snapshotLimit, setSnapshotLimit] = useState(200)
  const [snapTargetKind, setSnapTargetKind] = useState<'any' | 'model' | 'bundle'>('any')
  const [snapFilterSkuCode, setSnapFilterSkuCode] = useState<string>('')
  const [snapFilterChannel, setSnapFilterChannel] = useState<string>('')
  const [snapFilterSpecText, setSnapFilterSpecText] = useState<string>('')
  const [snapSelectedRowKeys, setSnapSelectedRowKeys] = useState<React.Key[]>([])
  const bulkStopRef = useRef(false)
  const [bulkRunning, setBulkRunning] = useState(false)

  const batchesQuery = useQuery({
    queryKey: ['shipments', 'import-batches', batchPage, batchPageSize],
    queryFn: () => fetchShipmentImportBatches({ page: batchPage, page_size: batchPageSize }),
    placeholderData: keepPreviousData,
  })

  const batches = (batchesQuery.data?.items ?? []) as ShipmentImportBatch[]
  const totalBatches = batchesQuery.data?.total ?? 0

  // init selection: from URL batch_id first, else latest batch
  useEffect(() => {
    const fromUrl = String(sp.get('batch_id') ?? '').trim()
    if (fromUrl && fromUrl !== selectedBatchId) {
      setSelectedBatchId(fromUrl)
      return
    }
    if (selectedBatchId) return
    const firstId = String((batches?.[0] as any)?.id ?? '').trim()
    if (firstId) setSelectedBatchId(firstId)
  }, [batches, selectedBatchId, sp])

  useEffect(() => {
    if (!selectedBatchId) return
    // keep batch_id in URL for shareable link
    setSp((prev) => {
      const next = new URLSearchParams(prev)
      next.set('batch_id', selectedBatchId)
      return next
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedBatchId])

  const selectedBatchQuery = useQuery({
    queryKey: ['shipments', 'import-batch', selectedBatchId],
    queryFn: () => fetchShipmentImportBatch(String(selectedBatchId)),
    enabled: !!selectedBatchId,
  })
  const selectedBatch = selectedBatchQuery.data

  const exceptionsQuery = useQuery({
    queryKey: ['shipments', 'exceptions', selectedBatchId, exceptionResolved, exceptionLimit],
    queryFn: () =>
      fetchShipmentExceptions({
        batch_id: selectedBatchId || undefined,
        resolved:
          exceptionResolved === 'all' ? undefined : exceptionResolved === 'resolved' ? true : false,
        limit: exceptionLimit,
      }),
    enabled: !!selectedBatchId,
  })

  const snapshotsQuery = useQuery({
    queryKey: ['shipments', 'bom-snapshots', selectedBatchId, snapshotLimit],
    queryFn: () =>
      fetchShipmentBomSnapshots({
        batch_id: selectedBatchId || undefined,
        limit: snapshotLimit,
      }),
    enabled: !!selectedBatchId,
  })

  const retryMutation = useMutation({
    mutationFn: async () => {
      if (!selectedBatchId) throw new Error('请先选择导入单据')
      return retryShipmentExceptions({
        batch_id: selectedBatchId,
        only_unresolved: true,
        limit: exceptionLimit || undefined,
        operator_id: operatorId.trim() || 'planner_user',
        reason: 'ui_retry_unresolved',
      })
    },
    onSuccess: (res) => {
      message.success(`已触发重试：processed=${res.processed}, resolved=${res.resolved}, unresolved=${res.unresolved}`)
      exceptionsQuery.refetch()
      queryClient.invalidateQueries({ queryKey: ['shipments', 'bom-snapshots'] })
    },
    onError: (err: any) => {
      message.error(`重试失败：${err?.response?.data?.detail ?? err?.message ?? 'unknown error'}`)
    },
  })

  const bulkHandleSelectedExceptions = async () => {
    const keys = excSelectedRowKeys as any[]
    if (!keys.length) {
      message.info('请先勾选要处理的异常行')
      return
    }
    const rows = filteredExceptions.filter((r: any) => keys.includes(String(r.id)))
    const ok = await new Promise<boolean>((resolve) => {
      Modal.confirm({
        title: `对所选异常生成快照/计价？（${rows.length}条）`,
        content: '将按当前绑定与当前规则，对所选异常对应的发货行执行“只补齐缺失”。成功后异常会自动标记为已解决。',
        okText: '确认执行',
        cancelText: '取消',
        onOk: () => resolve(true),
        onCancel: () => resolve(false),
      })
    })
    if (!ok) return

    const key = 'bulk-handle-exc'
    message.loading({ content: `处理中... 0/${rows.length}`, key, duration: 0 })
    let okCount = 0
    let failCount = 0
    for (let i = 0; i < rows.length; i += 1) {
      const r: any = rows[i]
      const lid = safeString(r?.shipment_line_id).trim()
      if (!lid) {
        failCount += 1
        continue
      }
      try {
        const res = await computeShipmentLineSnapshot(lid, { overwrite: false, operator_id: operatorId.trim() || undefined })
        if (res.action === 'failed') failCount += 1
        else okCount += 1
      } catch {
        failCount += 1
      }
      message.loading({
        content: `处理中... ${Math.min(i + 1, rows.length)}/${rows.length}（成功${okCount} 失败${failCount}）`,
        key,
        duration: 0,
      })
    }
    message.destroy(key)
    message.success(`处理完成：成功${okCount} 失败${failCount}`)
    setExcSelectedRowKeys([])
    exceptionsQuery.refetch()
    queryClient.invalidateQueries({ queryKey: ['shipments', 'bom-snapshots'] })
  }

  const runBulkRecomputeSnapshots = async () => {
    const rows = (snapshotsQuery.data ?? []) as BomSnapshot[]
    if (!rows.length) {
      message.info('当前快照列表为空，无需回填')
      return
    }
    if (bulkRunning) return

    const ok = await new Promise<boolean>((resolve) => {
      Modal.confirm({
        title: `覆盖重算这些快照？（${rows.length}条，高风险）`,
        content:
          '将逐条调用“回填/重算快照”接口，用当前 SKU 绑定重新计算并覆盖写回快照。建议先在台账缩小范围再操作。',
        okText: '确认覆盖重算',
        okButtonProps: { danger: true },
        cancelText: '取消',
        onOk: () => resolve(true),
        onCancel: () => resolve(false),
      })
    })
    if (!ok) return

    bulkStopRef.current = false
    setBulkRunning(true)

    const key = 'bulk-recompute'
    message.loading({ content: `批量回填中... 0/${rows.length}`, key, duration: 0 })
    let okCount = 0
    let failCount = 0
    for (let i = 0; i < rows.length; i += 1) {
      if (bulkStopRef.current) break
      const id = String((rows[i] as any)?.id ?? '').trim()
      if (!id) continue
      try {
        await recomputeShipmentBomSnapshot(id, { operator_id: operatorId.trim() || undefined })
        okCount += 1
      } catch {
        failCount += 1
      }
      message.loading({
        content: `批量回填中... ${Math.min(i + 1, rows.length)}/${rows.length}（成功${okCount} 失败${failCount}）`,
        key,
        duration: 0,
      })
    }
    await snapshotsQuery.refetch()
    message.destroy(key)
    setBulkRunning(false)
    if (bulkStopRef.current) message.warning(`已停止：成功${okCount} 失败${failCount}（已完成部分已生效）`)
    else message.success(`批量回填完成：成功${okCount} 失败${failCount}`)
  }

  const filteredExceptions = useMemo(() => {
    const rows = (exceptionsQuery.data ?? []) as ShipmentException[]
    const qSku = excFilterSkuCode.trim()
    const qChannel = excFilterChannel.trim()
    const qSpec = excFilterSpecText.trim()
    if (!qSku && !qChannel && !qSpec) return rows
    const inc = (src: unknown, q: string) => safeString(src).toLowerCase().includes(q.toLowerCase())
    return rows.filter((r: any) => {
      if (qSku && !inc(r?.sku_code, qSku)) return false
      if (qChannel && !inc(r?.channel, qChannel)) return false
      if (qSpec && !inc(r?.spec_text, qSpec)) return false
      return true
    })
  }, [exceptionsQuery.data, excFilterSkuCode, excFilterChannel, excFilterSpecText])

  const filteredSnapshots = useMemo(() => {
    const rows = (snapshotsQuery.data ?? []) as BomSnapshot[]
    const qSku = snapFilterSkuCode.trim()
    const qChannel = snapFilterChannel.trim()
    const qSpec = snapFilterSpecText.trim()
    const inc = (src: unknown, q: string) => safeString(src).toLowerCase().includes(q.toLowerCase())
    return rows.filter((r: any) => {
      if (snapTargetKind !== 'any') {
        const trace = (r as any)?.trace ?? {}
        const isBundle = !!(trace?.sold_as_bundle || trace?.bundle)
        if (snapTargetKind === 'bundle' && !isBundle) return false
        if (snapTargetKind === 'model' && isBundle) return false
      }
      if (qSku && !inc(r?.sku_code, qSku)) return false
      if (qChannel && !inc(r?.channel, qChannel)) return false
      if (qSpec && !inc(r?.spec_text, qSpec)) return false
      return true
    })
  }, [snapshotsQuery.data, snapTargetKind, snapFilterSkuCode, snapFilterChannel, snapFilterSpecText])

  const batchSummary = useMemo(() => {
    const b: any = selectedBatch ?? {}
    const total = Number(b?.total_rows ?? 0) || 0
    const inserted = Number(b?.inserted_rows ?? 0) || 0
    const exc = Number(b?.exception_rows ?? 0) || 0
    const snaps = (snapshotsQuery.data ?? []).length
    const unresolved = (exceptionsQuery.data ?? []).filter((x: any) => !(x as any)?.resolved_at).length
    return { total, inserted, exc, snaps, unresolved }
  }, [selectedBatch, exceptionsQuery.data, snapshotsQuery.data])

  const batchColumns: ColumnsType<ShipmentImportBatch> = useMemo(
    () => [
      { title: '导入时间', dataIndex: 'created_at', width: 170, render: (v) => formatTime(v) },
      { title: '文件名', dataIndex: 'file_name', ellipsis: true },
      {
        title: '状态',
        dataIndex: 'status',
        width: 110,
        render: (v) => {
          const x = formatBatchStatus(v)
          return <Tag color={x.color}>{x.label}</Tag>
        },
      },
      { title: '总行', dataIndex: 'total_rows', width: 90 },
      { title: '写入', dataIndex: 'inserted_rows', width: 90 },
      { title: '异常', dataIndex: 'exception_rows', width: 90 },
    ],
    [],
  )

  const exceptionColumns: ColumnsType<ShipmentException> = useMemo(
    () => [
      { title: '行号', dataIndex: 'row_index', width: 80 },
      { title: '货品条码', dataIndex: 'sku_code', width: 170, ellipsis: true },
      { title: '渠道', dataIndex: 'channel', width: 140, ellipsis: true },
      {
        title: '交易规格',
        dataIndex: 'spec_text',
        ellipsis: true,
        render: (v) => {
          const s = safeString(v)
          return s ? <Text ellipsis={{ tooltip: s }}>{s}</Text> : '-'
        },
      },
      {
        title: '模型/套装',
        key: 'bound_target',
        width: 220,
        render: (_v, r: any) => {
          const code = safeString(r?.bound_model_code).trim()
          const name = safeString(r?.bound_model_name).trim()
          if (!code) return <Tag>未绑定</Tag>
          const isBundle = code.startsWith('B-') || code.startsWith('Z-')
          return (
            <span>
              <Tag color={isBundle ? 'purple' : 'blue'}>{code}</Tag>
              {name ? <span style={{ color: '#666' }}> {name}</span> : null}
            </span>
          )
        },
      },
      {
        title: '规格解析',
        key: 'spec_parse',
        width: 180,
        render: (_v, r: any) => {
          const ok = r?.spec_parsed === true || !!safeString(r?.spec_hash).trim()
          if (!ok) return <Tag>未解析</Tag>
          const w = safeString(r?.spec_width_cm).trim()
          const h = safeString(r?.spec_height_cm).trim()
          if (w && h) return <Tag color="green">宽{w}×高{h}cm</Tag>
          return <Tag color="green">已解析</Tag>
        },
      },
      {
        title: '原因',
        dataIndex: 'reason',
        width: 180,
        render: (v, r: any) => (
          <Tag color="red" title={safeString(r?.message) ? `详情：${safeString(r?.message)}` : undefined}>
            {formatExceptionReason(v)}
          </Tag>
        ),
      },
    ],
    [],
  )

  const bindingTextFromSnapshot = (r: any): { code: string; name?: string } | null => {
    const trace = r?.trace ?? {}
    const code =
      safeString(trace?.sold_model_code).trim() ||
      safeString(trace?.model_code).trim() ||
      safeString(trace?.model?.model_code).trim() ||
      ''
    const name =
      safeString(trace?.sold_model_name).trim() ||
      safeString(trace?.model_name).trim() ||
      safeString(trace?.model?.model_name).trim() ||
      ''
    if (!code) return null
    return { code, name: name || undefined }
  }

  const snapshotColumns: ColumnsType<BomSnapshot> = useMemo(
    () => [
      { title: '生成时间', dataIndex: 'created_at', width: 170, render: (v) => formatTime(v as any) },
      { title: '货品条码', dataIndex: 'sku_code', width: 170, ellipsis: true },
      {
        title: '交易规格',
        dataIndex: 'spec_text',
        ellipsis: true,
        render: (v) => {
          const s = safeString(v)
          return s ? <Text ellipsis={{ tooltip: s }}>{s}</Text> : '-'
        },
      },
      {
        title: '绑定',
        key: 'binding',
        width: 240,
        render: (_v, r: any) => {
          const hit = bindingTextFromSnapshot(r)
          if (!hit) return '-'
          const isBundle = hit.code.startsWith('B-') || hit.code.startsWith('Z-') || !!(r?.trace?.sold_as_bundle || r?.trace?.bundle)
          return (
            <span>
              <Tag color={isBundle ? 'purple' : 'blue'}>{hit.code}</Tag>
              {hit.name ? <span style={{ color: '#666' }}> {hit.name}</span> : null}
            </span>
          )
        },
      },
      {
        title: 'spec_hash',
        dataIndex: 'spec_hash',
        width: 220,
        ellipsis: true,
        render: (v) => {
          const s = safeString(v)
          return s ? <Text ellipsis={{ tooltip: '规格Hash：由交易规格文本计算的sha1，用于缓存/追溯' }}>{s}</Text> : '-'
        },
      },
      {
        title: '操作',
        key: 'ops',
        width: 140,
        render: (_v, r: any) => (
          <Button
            size="small"
            onClick={async () => {
              try {
                const updated = await recomputeShipmentBomSnapshot(String(r.id), { operator_id: operatorId.trim() || undefined })
                message.success(`回填完成：${String(updated.id).slice(0, 8)}...`)
                snapshotsQuery.refetch()
              } catch (err: any) {
                message.error(`回填失败：${err?.response?.data?.detail ?? err?.message ?? 'unknown error'}`)
              }
            }}
          >
            回填
          </Button>
        ),
      },
    ],
    [operatorId, snapshotsQuery],
  )

  const handleBatchPaginationChange = (p: TablePaginationConfig) => {
    setBatchPage(p.current ?? 1)
    setBatchPageSize(p.pageSize ?? 20)
  }

  return (
    <Row gutter={[12, 12]}>
      <Col xs={24} lg={9}>
        <Card
          size="small"
          title="导入单据（批次）"
          extra={
            <Space>
              <Button onClick={props.onOpenImport} type="primary">
                导入
              </Button>
              <Button onClick={() => batchesQuery.refetch()} loading={batchesQuery.isFetching}>
                刷新
              </Button>
            </Space>
          }
        >
          <Table
            rowKey="id"
            size="small"
            loading={batchesQuery.isFetching}
            columns={batchColumns}
            dataSource={batches}
            pagination={{ current: batchPage, pageSize: batchPageSize, total: totalBatches, showSizeChanger: true }}
            onChange={handleBatchPaginationChange}
            rowClassName={(record) => (String(record.id) === String(selectedBatchId) ? 'ant-table-row-selected' : '')}
            onRow={(record) => ({
              onClick: () => setSelectedBatchId(String(record.id)),
            })}
          />
        </Card>
      </Col>

      <Col xs={24} lg={15}>
        <Card
          size="small"
          title={
            <Space size={8} wrap>
              <span>单据详情</span>
              {selectedBatchId ? <Tag color="blue">batch_id: {selectedBatchId}</Tag> : <Tag>未选择</Tag>}
              {selectedBatch?.file_name ? <Text type="secondary">({String(selectedBatch.file_name)})</Text> : null}
            </Space>
          }
          extra={
            <Space>
              <Input
                style={{ width: 180 }}
                placeholder="operator_id（可空）"
                value={operatorId}
                onChange={(e) => setOperatorId(e.target.value)}
              />
            </Space>
          }
        >
          {!selectedBatchId ? (
            <Alert type="info" showIcon message="请先选择一个导入单据（批次）" />
          ) : (
            <>
              <DescriptionsBlock batch={selectedBatch} />

              <Tabs
                items={[
                  {
                    key: 'reconcile',
                    label: '对账（概览）',
                    children: (
                      <Space direction="vertical" size={8} style={{ width: '100%' }}>
                        <Alert
                          type="info"
                          showIcon
                          message="这页是做什么的？"
                          description="对账（概览）用于快速判断：本批次是否还有“待处理”（未绑定/缺规格/BOM失败等），以及快照是否已生成。下一步该点“异常处理”还是“成本快照/回填”。"
                        />
                        <Card size="small" title="关键统计（本批次）">
                          <Space size={8} wrap>
                            <Tag>总行 {batchSummary.total}</Tag>
                            <Tag color="green">写入 {batchSummary.inserted}</Tag>
                            <Tag color={batchSummary.exc > 0 ? 'red' : 'default'}>异常 {batchSummary.exc}</Tag>
                            <Tag color={batchSummary.snaps > 0 ? 'green' : 'default'}>快照 {batchSummary.snaps}</Tag>
                            <Tag color={batchSummary.unresolved > 0 ? 'red' : 'default'}>待处理 {batchSummary.unresolved}</Tag>
                          </Space>
                        </Card>
                        <Alert
                          type="warning"
                          showIcon
                          message="推荐操作顺序（ERP任务流）"
                          description={
                            <div>
                              <div>
                                1) 先到 <b>待处理（异常）</b>：把“未绑定/缺规格/BOM失败”等处理掉，再点“批量重试（未解决）”。
                              </div>
                              <div style={{ marginTop: 6 }}>
                                2) 再到 <b>已完成（成本快照）</b>：需要历史对账时用“回填/覆盖重算”（高风险）更新快照。
                              </div>
                            </div>
                          }
                        />
                      </Space>
                    ),
                  },
                  {
                    key: 'exceptions',
                    label: '待处理（异常）',
                    children: (
                      <Card
                        size="small"
                        title="异常队列（本批次）"
                        extra={
                          <Space wrap>
                            <Segmented
                              value={exceptionResolved}
                              onChange={(v) => setExceptionResolved(v as any)}
                              options={[
                                { label: '未解决', value: 'unresolved' },
                                { label: '已解决', value: 'resolved' },
                                { label: '全部', value: 'all' },
                              ]}
                            />
                            <Input
                              style={{ width: 120 }}
                              placeholder="limit"
                              value={String(exceptionLimit)}
                              onChange={(e) => setExceptionLimit(Number(e.target.value) || 200)}
                            />
                            <Button
                              type="primary"
                              onClick={() => retryMutation.mutate()}
                              loading={retryMutation.isPending}
                              disabled={!selectedBatchId}
                            >
                              批量重试（未解决）
                            </Button>
                            <Button type="primary" onClick={bulkHandleSelectedExceptions} disabled={!excSelectedRowKeys.length}>
                              处理所选（生成快照）
                            </Button>
                            <Button onClick={() => exceptionsQuery.refetch()} loading={exceptionsQuery.isFetching}>
                              刷新
                            </Button>
                          </Space>
                        }
                      >
                        <div style={{ marginBottom: 8 }}>
                          <Space wrap>
                            <Input
                              style={{ width: 180 }}
                              placeholder="货品条码"
                              allowClear
                              value={excFilterSkuCode}
                              onChange={(e) => setExcFilterSkuCode(e.target.value)}
                            />
                            <Input
                              style={{ width: 140 }}
                              placeholder="渠道"
                              allowClear
                              value={excFilterChannel}
                              onChange={(e) => setExcFilterChannel(e.target.value)}
                            />
                            <Input
                              style={{ width: 260 }}
                              placeholder="交易规格"
                              allowClear
                              value={excFilterSpecText}
                              onChange={(e) => setExcFilterSpecText(e.target.value)}
                            />
                            <Text type="secondary">当前：{filteredExceptions.length} 条</Text>
                          </Space>
                        </div>
                        <Table
                          rowKey="id"
                          size="small"
                          loading={exceptionsQuery.isFetching}
                          columns={exceptionColumns}
                          dataSource={filteredExceptions as any}
                          rowSelection={{
                            selectedRowKeys: excSelectedRowKeys,
                            onChange: (keys) => setExcSelectedRowKeys(keys),
                          }}
                          pagination={false}
                        />
                      </Card>
                    ),
                  },
                  {
                    key: 'snapshots',
                    label: '已完成（成本快照）',
                    children: (
                      <Card
                        size="small"
                        title="成本快照（本批次）"
                        extra={
                          <Space wrap>
                            <Input
                              style={{ width: 120 }}
                              placeholder="limit"
                              value={String(snapshotLimit)}
                              onChange={(e) => setSnapshotLimit(Number(e.target.value) || 200)}
                            />
                            <Button
                              danger={bulkRunning}
                              onClick={() => {
                                if (bulkRunning) {
                                  bulkStopRef.current = true
                                  return
                                }
                                runBulkRecomputeSnapshots()
                              }}
                              disabled={snapshotsQuery.isFetching || !(snapshotsQuery.data ?? []).length}
                              loading={bulkRunning}
                            >
                              {bulkRunning ? '停止覆盖重算' : '批量覆盖重算（当前列表）'}
                            </Button>
                            <Button onClick={() => snapshotsQuery.refetch()} loading={snapshotsQuery.isFetching}>
                              刷新
                            </Button>
                          </Space>
                        }
                      >
                        <div style={{ marginBottom: 8 }}>
                          <Space wrap>
                            <Segmented
                              value={snapTargetKind}
                              onChange={(v) => setSnapTargetKind(v as any)}
                              options={[
                                { label: '全部', value: 'any' },
                                { label: '标准模型', value: 'model' },
                                { label: '套装', value: 'bundle' },
                              ]}
                            />
                            <Input
                              style={{ width: 180 }}
                              placeholder="货品条码"
                              allowClear
                              value={snapFilterSkuCode}
                              onChange={(e) => setSnapFilterSkuCode(e.target.value)}
                            />
                            <Input
                              style={{ width: 140 }}
                              placeholder="渠道"
                              allowClear
                              value={snapFilterChannel}
                              onChange={(e) => setSnapFilterChannel(e.target.value)}
                            />
                            <Input
                              style={{ width: 260 }}
                              placeholder="交易规格"
                              allowClear
                              value={snapFilterSpecText}
                              onChange={(e) => setSnapFilterSpecText(e.target.value)}
                            />
                            <Text type="secondary">当前：{filteredSnapshots.length} 条</Text>
                          </Space>
                        </div>
                        <Table
                          rowKey="id"
                          size="small"
                          loading={snapshotsQuery.isFetching}
                          columns={snapshotColumns}
                          dataSource={filteredSnapshots as any}
                          rowSelection={{
                            selectedRowKeys: snapSelectedRowKeys,
                            onChange: (keys) => setSnapSelectedRowKeys(keys),
                          }}
                          pagination={false}
                        />
                      </Card>
                    ),
                  },
                ]}
              />
            </>
          )}
        </Card>
      </Col>
    </Row>
  )
}

function DescriptionsBlock(props: { batch?: ShipmentImportBatch | null }) {
  const b = props.batch
  if (!b) return null
  return (
    <div style={{ marginBottom: 12 }}>
      <Row gutter={[12, 12]}>
        <Col xs={24} lg={12}>
          <Card size="small" title="基本信息">
            <div>
              <Text type="secondary">文件：</Text>
              <Text>{String(b.file_name ?? '-') || '-'}</Text>
            </div>
            <div>
              <Text type="secondary">导出日期：</Text>
              <Text>{String(b.export_date ?? '-') || '-'}</Text>
            </div>
            <div>
              <Text type="secondary">导入时间：</Text>
              <Text>{formatTime(b.created_at ?? null)}</Text>
            </div>
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card size="small" title="统计">
            <Space size={10} wrap>
              <Tag>总行 {Number((b as any)?.total_rows ?? 0) || 0}</Tag>
              <Tag color="green">写入 {Number((b as any)?.inserted_rows ?? 0) || 0}</Tag>
              <Tag color="red">异常 {Number((b as any)?.exception_rows ?? 0) || 0}</Tag>
              <Tag>{formatBatchStatus((b as any)?.status).label}</Tag>
            </Space>
          </Card>
        </Col>
      </Row>
    </div>
  )
}

