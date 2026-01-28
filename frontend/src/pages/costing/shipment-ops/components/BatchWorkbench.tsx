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

  const [snapshotLimit, setSnapshotLimit] = useState(200)
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
      { title: '发货单号', dataIndex: 'shipment_no', width: 160, ellipsis: true },
      { title: '渠道', dataIndex: 'channel', width: 140, ellipsis: true },
      { title: 'SKU', dataIndex: 'sku_code', width: 160, ellipsis: true },
      {
        title: '原因',
        dataIndex: 'reason',
        width: 180,
        render: (v) => <Tag color="red">{formatExceptionReason(v)}</Tag>,
      },
      {
        title: '详情',
        dataIndex: 'message',
        ellipsis: true,
        render: (v) => {
          const s = safeString(v)
          return s ? <Text ellipsis={{ tooltip: s }}>{s}</Text> : '-'
        },
      },
    ],
    [],
  )

  const snapshotColumns: ColumnsType<BomSnapshot> = useMemo(
    () => [
      { title: '生成时间', dataIndex: 'created_at', width: 170, render: (v) => formatTime(v as any) },
      { title: '发货单号', dataIndex: 'shipment_no', width: 160, ellipsis: true },
      { title: 'SKU', dataIndex: 'sku_code', width: 160, ellipsis: true },
      { title: 'spec_hash', dataIndex: 'spec_hash', width: 220, ellipsis: true },
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
                      <Alert
                        type="info"
                        showIcon
                        message="建议操作顺序"
                        description={
                          <div>
                            <div>1) 先处理“待处理”里的未绑定/缺规格等问题（必要时去台账定位原始行）。</div>
                            <div>2) 再做“快照”里的回填/重算（用于历史对账与洞察回算）。</div>
                          </div>
                        }
                      />
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
                            <Button onClick={() => exceptionsQuery.refetch()} loading={exceptionsQuery.isFetching}>
                              刷新
                            </Button>
                          </Space>
                        }
                      >
                        <Table
                          rowKey="id"
                          size="small"
                          loading={exceptionsQuery.isFetching}
                          columns={exceptionColumns}
                          dataSource={(exceptionsQuery.data ?? []) as any}
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
                        <Table
                          rowKey="id"
                          size="small"
                          loading={snapshotsQuery.isFetching}
                          columns={snapshotColumns}
                          dataSource={(snapshotsQuery.data ?? []) as any}
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

