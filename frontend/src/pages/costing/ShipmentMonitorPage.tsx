import {
  Alert,
  Button,
  Card,
  Col,
  DatePicker,
  Descriptions,
  Drawer,
  Form,
  Input,
  message,
  Modal,
  Row,
  Segmented,
  Space,
  Table,
  Tabs,
  Tag,
  Typography,
  Upload,
} from 'antd'
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table'
import dayjs from 'dayjs'
import { useMemo, useState } from 'react'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'

import {
  executeShipmentsFromPreview,
  fetchShipmentBomSnapshots,
  fetchShipmentExceptions,
  fetchShipmentImportBatches,
  generateBom,
  previewShipmentsXlsx,
  recomputeShipmentBomSnapshot,
  retryShipmentExceptions,
} from '@/services/planner'
import type { BomGenerateResponse, BomSnapshot, ShipmentException, ShipmentImportBatch } from '@/types/planner'

const { Title, Text } = Typography

const DEFAULT_PAGE_SIZE = 10

const formatTime = (v?: string | null) => {
  if (!v) return '-'
  const d = dayjs(v)
  return d.isValid() ? d.format('YYYY-MM-DD HH:mm:ss') : String(v)
}

const safeString = (v: unknown): string => {
  if (v === null || v === undefined) return ''
  return String(v)
}

const toNumberOrNull = (v: unknown): number | null => {
  if (v === null || v === undefined) return null
  if (typeof v === 'number' && Number.isFinite(v)) return v
  if (typeof v === 'string') {
    const s = v.trim()
    if (!s) return null
    const n = Number(s)
    return Number.isFinite(n) ? n : null
  }
  return null
}

const formatMoney = (v: unknown): string => {
  const n = toNumberOrNull(v)
  if (n === null) return '-'
  return n.toFixed(4)
}

const computeLineCost = (line: any): number | null => {
  const direct = toNumberOrNull(line?.line_cost)
  if (direct !== null) return direct
  const qty = toNumberOrNull(line?.computed_quantity ?? line?.quantity ?? line?.qty)
  const price = toNumberOrNull(line?.bom_unit_price ?? line?.metadata?.bom_unit_price)
  if (qty === null || price === null) return null
  return qty * price
}

const computeTotalCostFromLines = (lines: any[]): number | null => {
  if (!Array.isArray(lines) || lines.length === 0) return null
  let sum = 0
  let hasAny = false
  for (const l of lines) {
    const c = computeLineCost(l)
    if (c !== null) {
      sum += c
      hasAny = true
    }
  }
  return hasAny ? sum : null
}

const jsonPretty = (obj: unknown) => {
  try {
    return JSON.stringify(obj ?? {}, null, 2)
  } catch {
    return String(obj ?? '')
  }
}

const guessLineCode = (line: Record<string, unknown>) =>
  safeString(line.code ?? line.material_code ?? line.materialCode ?? line.reference_code)

const guessLineName = (line: Record<string, unknown>) =>
  safeString(line.name ?? line.material_name ?? line.materialName ?? line.description)

const guessLineQty = (line: Record<string, unknown>) =>
  safeString(line.quantity ?? line.computed_quantity ?? line.qty ?? line.base_quantity)

const guessLineUnit = (line: Record<string, unknown>) =>
  safeString(line.unit ?? line.unit_of_measure ?? line.unitOfMeasure ?? line.bom_unit)

const ShipmentMonitorPage = () => {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [batchPage, setBatchPage] = useState(1)
  const [batchPageSize, setBatchPageSize] = useState(DEFAULT_PAGE_SIZE)
  const [selectedBatchId, setSelectedBatchId] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<'batches' | 'exceptions' | 'snapshots' | 'parse-queue'>('batches')

  const [uploading, setUploading] = useState(false)
  const [uploadFile, setUploadFile] = useState<File | null>(null)
  const [uploadExportDate, setUploadExportDate] = useState<string | undefined>(
    dayjs().format('YYYY-MM-DD'),
  )
  const [uploadRequestedBy, setUploadRequestedBy] = useState<string>('planner_user')
  const [previewData, setPreviewData] = useState<any>(null)
  const [queueDrawerOpen, setQueueDrawerOpen] = useState(false)
  const [activeQueueRow, setActiveQueueRow] = useState<any>(null)
  const [queueBomPreview, setQueueBomPreview] = useState<BomGenerateResponse | null>(null)

  const [exceptionResolved, setExceptionResolved] = useState<'unresolved' | 'resolved' | 'all'>(
    'unresolved',
  )
  const [exceptionLimit, setExceptionLimit] = useState(200)
  const [retryingExceptions, setRetryingExceptions] = useState(false)

  const [snapshotForm] = Form.useForm()
  const [snapshotQuery, setSnapshotQuery] = useState<{
    batch_id?: string
    sku_code?: string
    shipment_no?: string
    spec_hash?: string
    limit?: number
  }>({ limit: 200 })

  const [snapshotDrawerOpen, setSnapshotDrawerOpen] = useState(false)
  const [activeSnapshot, setActiveSnapshot] = useState<BomSnapshot | null>(null)
  const [recomputingSnapshotId, setRecomputingSnapshotId] = useState<string | null>(null)

  const batchesQuery = useQuery({
    queryKey: ['shipments', 'import-batches', batchPage, batchPageSize],
    queryFn: () => fetchShipmentImportBatches({ page: batchPage, page_size: batchPageSize }),
    placeholderData: keepPreviousData,
  })

  const batches = batchesQuery.data?.items ?? []
  const totalBatches = batchesQuery.data?.total ?? 0

  const exceptionsQuery = useQuery({
    queryKey: ['shipments', 'exceptions', selectedBatchId, exceptionResolved, exceptionLimit],
    queryFn: () =>
      fetchShipmentExceptions({
        batch_id: selectedBatchId || undefined,
        resolved:
          exceptionResolved === 'all'
            ? undefined
            : exceptionResolved === 'resolved'
              ? true
              : false,
        limit: exceptionLimit,
      }),
    enabled: activeTab === 'exceptions',
  })

  const retryExceptionsMutation = useMutation({
    mutationFn: async () => {
      const batchId = (selectedBatchId || '').trim()
      if (!batchId) throw new Error('请先填写/选择 batch_id')
      const operatorId = (uploadRequestedBy || '').trim() || 'planner_user'
      // MVP: 使用固定 reason，避免额外弹窗/输入；后端要求非空且 <=128
      const reason = 'ui_retry_unresolved'
      return await retryShipmentExceptions({
        batch_id: batchId,
        only_unresolved: true,
        limit: exceptionLimit || undefined,
        operator_id: operatorId,
        reason,
      })
    },
    onSuccess: (res) => {
      message.success(`已触发重试：processed=${res.processed}, resolved=${res.resolved}, unresolved=${res.unresolved}`)
      exceptionsQuery.refetch()
      // retry 会新建 bom_snapshot，顺带刷新快照 tab 的数据缓存
      queryClient.invalidateQueries({ queryKey: ['shipments', 'bom-snapshots'] })
    },
    onError: (err: any) => {
      message.error(`重试失败：${err?.response?.data?.detail ?? err?.message ?? 'unknown error'}`)
    },
    onSettled: () => {
      setRetryingExceptions(false)
    },
  })

  const snapshotsQuery = useQuery({
    queryKey: ['shipments', 'bom-snapshots', snapshotQuery],
    queryFn: () => fetchShipmentBomSnapshots(snapshotQuery),
    enabled: activeTab === 'snapshots',
  })

  const handleQueuePreviewBom = async (row: any) => {
    try {
      setActiveQueueRow(row)
      setQueueDrawerOpen(true)
      setQueueBomPreview(null)
      const specText = safeString(row?.spec_text)
      const skuCode = safeString(row?.sku_code)
      const qty0 = Number(row?.qty ?? 1)
      const qty = Number.isFinite(qty0) && qty0 > 0 ? qty0 : 1
      const res = await generateBom({ spec_text: specText, sku_code: skuCode, quantity: qty })
      setQueueBomPreview(res)
    } catch (err: any) {
      message.error(`BOM预览失败：${err?.response?.data?.detail ?? err?.message ?? 'unknown error'}`)
    }
  }

  const batchColumns: ColumnsType<ShipmentImportBatch> = [
    {
      title: '导入时间',
      dataIndex: 'created_at',
      width: 170,
      render: (v) => formatTime(v),
    },
    {
      title: '导出日期',
      dataIndex: 'export_date',
      width: 120,
      render: (v) => safeString(v) || '-',
    },
    {
      title: '文件名',
      dataIndex: 'file_name',
      ellipsis: true,
      render: (v) => safeString(v) || '-',
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 120,
      render: (v) => {
        const s = safeString(v) || 'unknown'
        const color = s === 'success' ? 'green' : s === 'processing' ? 'blue' : 'default'
        return <Tag color={color}>{s}</Tag>
      },
    },
    {
      title: '总行',
      dataIndex: 'total_rows',
      width: 80,
    },
    {
      title: '写入',
      dataIndex: 'inserted_rows',
      width: 80,
    },
    {
      title: '跳过',
      dataIndex: 'skipped_rows',
      width: 80,
    },
    {
      title: '异常',
      dataIndex: 'exception_rows',
      width: 80,
    },
  ]

  const exceptionColumns: ColumnsType<ShipmentException> = [
    {
      title: '时间',
      dataIndex: 'created_at',
      width: 170,
      render: (v) => formatTime(v),
    },
    {
      title: '发货单号',
      dataIndex: 'shipment_no',
      width: 160,
      ellipsis: true,
      render: (v) => safeString(v) || '-',
    },
    {
      title: '货品条码(SKU)',
      dataIndex: 'sku_code',
      width: 160,
      ellipsis: true,
      render: (v) => safeString(v) || '-',
    },
    {
      title: '交易规格',
      dataIndex: 'spec_text',
      ellipsis: true,
      render: (v) => safeString(v) || '-',
    },
    {
      title: '数量',
      dataIndex: 'qty',
      width: 90,
      render: (v) => safeString(v) || '-',
    },
    {
      title: '金额',
      dataIndex: 'revenue_amount',
      width: 110,
      render: (v) => safeString(v) || '-',
    },
    {
      title: '原因',
      dataIndex: 'reason',
      width: 180,
      render: (v) => safeString(v) || '-',
    },
    {
      title: '消息',
      dataIndex: 'message',
      ellipsis: true,
      render: (v) => safeString(v) || '-',
    },
    {
      title: '操作',
      key: 'actions',
      width: 120,
      render: (_, record) => {
        const reason = safeString(record?.reason)
        const sku = safeString(record?.sku_code).trim()
        if (reason === 'SKU_NOT_BOUND' && sku) {
          return (
            <Button
              size="small"
              type="link"
              onClick={() => navigate(`/costing/sku-master?search=${encodeURIComponent(sku)}`)}
            >
              去绑定
            </Button>
          )
        }
        return null
      },
    },
  ]

  const snapshotColumns: ColumnsType<BomSnapshot> = [
    {
      title: '生成时间',
      dataIndex: 'generated_at',
      width: 170,
      render: (v) => formatTime(v),
    },
    {
      title: '发货单号',
      dataIndex: 'shipment_no',
      width: 160,
      ellipsis: true,
      render: (v) => safeString(v) || '-',
    },
    {
      title: 'SKU',
      dataIndex: 'sku_code',
      width: 140,
      ellipsis: true,
      render: (v) => safeString(v) || '-',
    },
    {
      title: 'qty',
      dataIndex: 'qty',
      width: 90,
      render: (v) => safeString(v) || '-',
    },
    {
      title: 'model_version_id',
      dataIndex: 'model_version_id',
      width: 220,
      ellipsis: true,
      render: (v) => safeString(v) || '-',
    },
    {
      title: '明细行数',
      dataIndex: 'final_material_lines',
      width: 90,
      render: (v) => (Array.isArray(v) ? v.length : 0),
    },
    {
      title: '操作',
      key: 'actions',
      width: 180,
      render: (_, record) => (
        <Space size={8}>
          <Button
            size="small"
            onClick={() => {
              setActiveSnapshot(record)
              setSnapshotDrawerOpen(true)
            }}
          >
            查看
          </Button>
          <Button
            size="small"
            loading={recomputingSnapshotId === record.id}
            onClick={async () => {
              try {
                setRecomputingSnapshotId(record.id)
                const updated = await recomputeShipmentBomSnapshot(record.id, {
                  operator_id: uploadRequestedBy?.trim() || undefined,
                })
                message.success('回填完成：已重算工序+成本并更新快照')
                // refresh list + open updated snapshot
                snapshotsQuery.refetch()
                setActiveSnapshot(updated)
                setSnapshotDrawerOpen(true)
              } catch (err: any) {
                message.error(`回填失败：${err?.response?.data?.detail ?? err?.message ?? 'unknown error'}`)
              } finally {
                setRecomputingSnapshotId(null)
              }
            }}
          >
            回填
          </Button>
        </Space>
      ),
    },
  ]

  const snapshotLines = useMemo(() => {
    if (!activeSnapshot?.final_material_lines) return []
    const rows = activeSnapshot.final_material_lines
    return rows.map((line, idx) => {
      const obj = (line ?? {}) as Record<string, unknown>
      return {
        key: `${activeSnapshot.id}-${idx}`,
        source: safeString(obj.source) || safeString(obj.line_source) || '-',
        code: guessLineCode(obj) || '-',
        name: guessLineName(obj) || '-',
        quantity: guessLineQty(obj) || '-',
        unit: guessLineUnit(obj) || '-',
        bom_unit_price: (obj as any).bom_unit_price ?? ((obj as any).metadata ?? {})?.bom_unit_price ?? null,
        line_cost: (obj as any).line_cost ?? null,
        raw: obj,
      }
    })
  }, [activeSnapshot])

  const snapshotTotalCost = useMemo(() => {
    if (!activeSnapshot) return null
    const traceCost = (activeSnapshot as any)?.trace?.costing?.total_cost
    const n = toNumberOrNull(traceCost)
    if (n !== null) return n
    return computeTotalCostFromLines((activeSnapshot as any)?.final_material_lines ?? [])
  }, [activeSnapshot])

  const snapshotLineCols: ColumnsType<any> = [
    { title: '来源', dataIndex: 'source', width: 110 },
    { title: '编码', dataIndex: 'code', width: 140, ellipsis: true },
    { title: '名称', dataIndex: 'name', ellipsis: true },
    { title: '数量', dataIndex: 'quantity', width: 120 },
    { title: '单位', dataIndex: 'unit', width: 90 },
    { title: 'BOM单价', dataIndex: 'bom_unit_price', width: 120, render: (v) => formatMoney(v) },
    { title: '行成本', dataIndex: 'line_cost', width: 120, render: (_, r) => formatMoney(computeLineCost(r?.raw)) },
  ]

  const handleBatchPaginationChange = (pagination: TablePaginationConfig) => {
    const nextPage = pagination.current ?? 1
    const nextSize = pagination.pageSize ?? DEFAULT_PAGE_SIZE
    setBatchPage(nextPage)
    setBatchPageSize(nextSize)
  }

  const handleUploadPreview = async () => {
    if (!uploadFile) {
      message.warning('请先选择一个 .xlsx 文件')
      return
    }
    try {
      setUploading(true)
      const res = await previewShipmentsXlsx({
        file: uploadFile,
        export_date: uploadExportDate,
        requested_by: uploadRequestedBy?.trim() || undefined,
      })
      setPreviewData(res)
      message.success(`预览完成：可执行 ${res.ready_rows}/${res.total_rows}`)
    } catch (err: any) {
      setPreviewData(null)
      message.error(`预览失败：${err?.response?.data?.detail ?? err?.message ?? 'unknown error'}`)
    } finally {
      setUploading(false)
    }
  }

  const handleUploadExecute = async () => {
    if (!previewData?.preview_id) {
      message.warning('请先完成“预览”')
      return
    }
    if (uploadFile?.name && previewData?.file_name && String(previewData.file_name) !== String(uploadFile.name)) {
      message.error(`当前选择文件与预览不一致：已选"${uploadFile.name}"，预览的是"${previewData.file_name}"。请重新点击“预览”。`)
      return
    }
    try {
      setUploading(true)
      const batch = await executeShipmentsFromPreview({
        preview_id: previewData.preview_id,
        file_name: previewData.file_name,
        export_date: uploadExportDate,
        requested_by: uploadRequestedBy?.trim() || undefined,
      })
      message.success(`执行完成：batch=${batch.id}（inserted=${batch.inserted_rows}, skipped=${batch.skipped_rows}, exceptions=${batch.exception_rows}）`)
      setSelectedBatchId(batch.id)
      setActiveTab('batches')
      setBatchPage(1)
      setUploadFile(null)
      setPreviewData(null)
      queryClient.invalidateQueries({ queryKey: ['shipments'] })
    } catch (err: any) {
      message.error(`执行失败：${err?.response?.data?.detail ?? err?.message ?? 'unknown error'}`)
    } finally {
      setUploading(false)
    }
  }

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between' }}>
        <div>
          <Title level={3} style={{ marginBottom: 4 }}>
            发货批次 / 异常队列 / BOM 快照（只读）
          </Title>
          <Text type="secondary">
            入口用于对账与排查：先选批次，再看异常与快照；也可在快照 Tab 按 SKU/单号/SpecHash 查询。
          </Text>
        </div>
        <Space>
          <Tag color={selectedBatchId ? 'blue' : 'default'}>
            当前批次：{selectedBatchId ? selectedBatchId : '未选择'}
          </Tag>
          <Button
            onClick={() => {
              batchesQuery.refetch()
              if (activeTab === 'exceptions') exceptionsQuery.refetch()
              if (activeTab === 'snapshots') snapshotsQuery.refetch()
            }}
          >
            刷新
          </Button>
        </Space>
      </div>

      <div style={{ marginTop: 16 }}>
        <Card title="上传发货单（预览→执行）" size="small">
          <Row gutter={[16, 16]} align="middle">
            <Col xs={24} lg={10}>
              <Upload
                accept=".xlsx"
                maxCount={1}
                beforeUpload={(file) => {
                  setUploadFile(file as any)
                  setPreviewData(null)
                  return false
                }}
                onRemove={() => {
                  setUploadFile(null)
                  setPreviewData(null)
                }}
              >
                <Button disabled={uploading}>选择文件（.xlsx）</Button>
                <Text type="secondary" style={{ marginLeft: 12 }}>
                  {uploadFile ? uploadFile.name : '未选择'}
                </Text>
              </Upload>
            </Col>
            <Col xs={24} lg={6}>
              <Space>
                <Text>导出日期</Text>
                <DatePicker
                  allowClear
                  value={uploadExportDate ? dayjs(uploadExportDate) : null}
                  format="YYYY-MM-DD"
                  onChange={(d) => setUploadExportDate(d ? d.format('YYYY-MM-DD') : undefined)}
                />
              </Space>
            </Col>
            <Col xs={24} lg={5}>
              <Input
                placeholder="requested_by（可空）"
                value={uploadRequestedBy}
                onChange={(e) => setUploadRequestedBy(e.target.value)}
              />
            </Col>
            <Col xs={24} lg={3}>
              <Space direction="vertical" style={{ width: '100%' }}>
                <Button type="primary" loading={uploading} onClick={handleUploadPreview} block>
                  预览
                </Button>
                <Button
                  type="primary"
                  danger
                  loading={uploading}
                  onClick={handleUploadExecute}
                  disabled={!previewData?.preview_id}
                  block
                >
                  执行
                </Button>
              </Space>
            </Col>
          </Row>
          {previewData ? (
            <Alert
              style={{ marginTop: 12 }}
              type="info"
              showIcon
              message={`预览结果：总行${previewData.total_rows}，可执行${previewData.ready_rows}，未绑定${previewData.unbound_sku_rows}，缺条码${previewData.missing_sku_rows}，缺规格${previewData.missing_spec_rows}`}
              description={
                (previewData.issues ?? []).length ? (
                  <div style={{ maxHeight: 180, overflow: 'auto', marginTop: 8 }}>
                    <pre style={{ margin: 0 }}>{jsonPretty((previewData.issues ?? []).slice(0, 50))}</pre>
                  </div>
                ) : (
                  <Text type="secondary">无问题明细（或问题数为0）。</Text>
                )
              }
            />
          ) : null}
          <div style={{ marginTop: 8 }}>
            <Text type="secondary">
              说明：先预览再执行。后端按 file_hash（preview_id）做文件级幂等；执行会使用预览阶段缓存的文件。
            </Text>
          </div>
        </Card>
      </div>

      <div style={{ marginTop: 16 }}>
        <Tabs
          activeKey={activeTab}
          onChange={(k) => setActiveTab(k as any)}
          items={[
            {
              key: 'batches',
              label: '发货批次列表',
              children: (
                <Row gutter={[16, 16]}>
                  <Col span={24}>
                    <Card>
                      <Alert
                        type="info"
                        showIcon
                        message="提示"
                        description="点击任意批次行即可设置为“当前批次”。异常队列 / BOM快照 默认会用当前批次作为筛选条件。"
                        style={{ marginBottom: 12 }}
                      />
                      <Table
                        rowKey="id"
                        size="small"
                        loading={batchesQuery.isFetching}
                        columns={batchColumns}
                        dataSource={batches}
                        pagination={{
                          current: batchPage,
                          pageSize: batchPageSize,
                          total: totalBatches,
                          showSizeChanger: true,
                        }}
                        onChange={handleBatchPaginationChange}
                        rowClassName={(record) =>
                          record.id === selectedBatchId ? 'ant-table-row-selected' : ''
                        }
                        onRow={(record) => ({
                          onClick: () => {
                            setSelectedBatchId(record.id)
                          },
                        })}
                      />
                    </Card>
                  </Col>
                </Row>
              ),
            },
            {
              key: 'exceptions',
              label: '异常队列',
              children: (
                <Row gutter={[16, 16]}>
                  <Col span={24}>
                    <Card
                      title="异常队列（只读）"
                      extra={
                        <Space>
                          <Segmented
                            value={exceptionResolved}
                            onChange={(v) => setExceptionResolved(v as any)}
                            options={[
                              { label: '未解决', value: 'unresolved' },
                              { label: '已解决', value: 'resolved' },
                              { label: '全部', value: 'all' },
                            ]}
                          />
                          <Button
                            type="primary"
                            disabled={!selectedBatchId || exceptionResolved !== 'unresolved'}
                            loading={retryingExceptions || retryExceptionsMutation.isPending}
                            onClick={() => {
                              if (!selectedBatchId || !(selectedBatchId || '').trim()) {
                                message.warning('请先填写/选择 batch_id')
                                return
                              }
                              if (exceptionResolved !== 'unresolved') {
                                message.warning('请先切换到“未解决”视图再重试')
                                return
                              }
                              // 轻量确认，避免误触造成大量重算
                              ;(async () => {
                                setRetryingExceptions(true)
                                const ok = await new Promise<boolean>((resolve) => {
                                  Modal.confirm({
                                    title: '重试本批未解决异常？',
                                    content:
                                      '将对当前 batch_id 的未解决异常逐条重新执行“绑定→解析→BOM生成”，成功会生成新的 BOM 快照并标记异常已解决。',
                                    okText: '确认重试',
                                    cancelText: '取消',
                                    onOk: () => resolve(true),
                                    onCancel: () => resolve(false),
                                  })
                                })
                                if (!ok) {
                                  setRetryingExceptions(false)
                                  return
                                }
                                retryExceptionsMutation.mutate()
                              })()
                            }}
                          >
                            重试本批未解决异常
                          </Button>
                          <Input
                            style={{ width: 240 }}
                            placeholder="batch_id（可空=全局）"
                            value={selectedBatchId ?? ''}
                            onChange={(e) => setSelectedBatchId(e.target.value.trim() || null)}
                          />
                          <Input
                            style={{ width: 120 }}
                            placeholder="limit"
                            value={String(exceptionLimit)}
                            onChange={(e) => setExceptionLimit(Number(e.target.value) || 200)}
                          />
                        </Space>
                      }
                    >
                      <Table
                        rowKey="id"
                        size="small"
                        loading={exceptionsQuery.isFetching}
                        columns={exceptionColumns}
                        dataSource={exceptionsQuery.data ?? []}
                        pagination={false}
                      />
                    </Card>
                  </Col>
                </Row>
              ),
            },
            {
              key: 'parse-queue',
              label: '解析队列（预览可执行）',
              children: (
                <Row gutter={[16, 16]}>
                  <Col span={24}>
                    <Card title="解析队列（来自“预览”结果）" size="small">
                      {!previewData ? (
                        <Alert type="info" showIcon message="请先在上方上传区点击“预览”，这里会展示可执行的记录列表。" />
                      ) : (
                        <>
                          <Alert
                            type="info"
                            showIcon
                            style={{ marginBottom: 12 }}
                            message={`可执行记录：${previewData.ready_rows}/${previewData.total_rows}（点击行可预览BOM）`}
                          />
                          <Table
                            rowKey={(r) => safeString((r as any).row_index) + '-' + safeString((r as any).sku_code)}
                            size="small"
                            dataSource={(previewData.ready_items ?? []) as any[]}
                            pagination={{ pageSize: 20 }}
                            columns={[
                              { title: '行号', dataIndex: 'row_index', width: 80 },
                              { title: '发货单号', dataIndex: 'shipment_no', width: 160, ellipsis: true },
                              { title: 'SKU', dataIndex: 'sku_code', width: 160, ellipsis: true },
                              {
                                title: '交易规格',
                                dataIndex: 'spec_text',
                                render: (v) => (
                                  <div style={{ whiteSpace: 'normal', wordBreak: 'break-word', lineHeight: 1.2 }}>
                                    {safeString(v) || '-'}
                                  </div>
                                ),
                              },
                              { title: 'qty', dataIndex: 'qty', width: 90 },
                              {
                                title: '模型',
                                dataIndex: 'bound_model_code',
                                width: 220,
                                render: (_v, r) =>
                                  safeString((r as any).bound_model_code) ? (
                                    <Space size={6}>
                                      <Tag color="blue">{safeString((r as any).bound_model_code)}</Tag>
                                      <span style={{ color: '#666' }}>{safeString((r as any).bound_model_name)}</span>
                                    </Space>
                                  ) : (
                                    '-'
                                  ),
                              },
                              { title: '标准版本', dataIndex: 'bound_version_label', width: 180, ellipsis: true },
                            ]}
                            onRow={(record) => ({
                              onClick: () => handleQueuePreviewBom(record),
                            })}
                          />
                        </>
                      )}
                    </Card>
                  </Col>
                </Row>
              ),
            },
            {
              key: 'snapshots',
              label: 'BOM 快照查询',
              children: (
                <Row gutter={[16, 16]}>
                  <Col span={24}>
                    <Card
                      title="BOM 快照查询（只读）"
                      extra={
                        <Space>
                          <Button
                            type="primary"
                            onClick={() => {
                              snapshotForm.submit()
                            }}
                          >
                            查询
                          </Button>
                          <Button
                            onClick={() => {
                              snapshotForm.resetFields()
                              setSnapshotQuery({ limit: 200 })
                            }}
                          >
                            重置
                          </Button>
                        </Space>
                      }
                    >
                      <Form
                        form={snapshotForm}
                        layout="inline"
                        initialValues={{
                          batch_id: selectedBatchId ?? undefined,
                          sku_code: undefined,
                          shipment_no: undefined,
                          spec_hash: undefined,
                          limit: 200,
                        }}
                        onFinish={(values) => {
                          const next = {
                            batch_id: (values.batch_id ?? selectedBatchId ?? undefined) as
                              | string
                              | undefined,
                            sku_code: values.sku_code ? String(values.sku_code).trim() : undefined,
                            shipment_no: values.shipment_no
                              ? String(values.shipment_no).trim()
                              : undefined,
                            spec_hash: values.spec_hash ? String(values.spec_hash).trim() : undefined,
                            limit: values.limit ? Number(values.limit) : 200,
                          }
                          setSnapshotQuery(next)
                        }}
                      >
                        <Form.Item name="batch_id" label="batch_id">
                          <Input style={{ width: 260 }} placeholder="可空=全局" />
                        </Form.Item>
                        <Form.Item name="sku_code" label="SKU">
                          <Input style={{ width: 160 }} placeholder="SKU-001" />
                        </Form.Item>
                        <Form.Item name="shipment_no" label="发货单号">
                          <Input style={{ width: 160 }} placeholder="S2025..." />
                        </Form.Item>
                        <Form.Item name="spec_hash" label="spec_hash">
                          <Input style={{ width: 220 }} placeholder="sha1..." />
                        </Form.Item>
                        <Form.Item name="limit" label="limit">
                          <Input style={{ width: 100 }} />
                        </Form.Item>
                      </Form>

                      <div style={{ marginTop: 12 }}>
                        <Table
                          rowKey="id"
                          size="small"
                          loading={snapshotsQuery.isFetching}
                          columns={snapshotColumns}
                          dataSource={snapshotsQuery.data ?? []}
                          pagination={false}
                        />
                      </div>
                    </Card>
                  </Col>
                </Row>
              ),
            },
          ]}
        />
      </div>

      <Drawer
        title="解析队列：BOM预览（扣库存清单）"
        open={queueDrawerOpen}
        onClose={() => {
          setQueueDrawerOpen(false)
          setActiveQueueRow(null)
          setQueueBomPreview(null)
        }}
        width={980}
      >
        {activeQueueRow ? (
          <Space direction="vertical" style={{ width: '100%' }}>
            <Descriptions bordered size="small" column={2}>
              <Descriptions.Item label="shipment_no">{safeString(activeQueueRow.shipment_no) || '-'}</Descriptions.Item>
              <Descriptions.Item label="sku_code">{safeString(activeQueueRow.sku_code) || '-'}</Descriptions.Item>
              <Descriptions.Item label="qty">{safeString(activeQueueRow.qty) || '-'}</Descriptions.Item>
              <Descriptions.Item label="模型">
                {safeString(activeQueueRow.bound_model_code) ? (
                  <Space size={6}>
                    <Tag color="blue">{safeString(activeQueueRow.bound_model_code)}</Tag>
                    <span>{safeString(activeQueueRow.bound_model_name)}</span>
                  </Space>
                ) : (
                  '-'
                )}
              </Descriptions.Item>
              <Descriptions.Item label="交易规格" span={2}>
                {safeString(activeQueueRow.spec_text) || '-'}
              </Descriptions.Item>
            </Descriptions>
            {queueBomPreview ? (
              <Tabs
                items={[
                  {
                    key: 'summary',
                    label: '汇总',
                    children: (
                      <Descriptions bordered size="small" column={3}>
                        <Descriptions.Item label="合计成本（CNY）">
                          <b>
                            {formatMoney(
                              toNumberOrNull((queueBomPreview as any)?.trace?.costing?.total_cost) ??
                                computeTotalCostFromLines((queueBomPreview.final_material_lines ?? []) as any[]),
                            )}
                          </b>
                        </Descriptions.Item>
                        <Descriptions.Item label="物料成本（CNY）">
                          {formatMoney(toNumberOrNull((queueBomPreview as any)?.trace?.costing?.material_cost_total))}
                        </Descriptions.Item>
                        <Descriptions.Item label="工序成本（CNY）">
                          {formatMoney(toNumberOrNull((queueBomPreview as any)?.trace?.costing?.process_cost_total))}
                        </Descriptions.Item>
                        <Descriptions.Item label="制造费用（CNY）">
                          {formatMoney(toNumberOrNull((queueBomPreview as any)?.trace?.costing?.overhead_cost))}
                        </Descriptions.Item>
                        <Descriptions.Item label="制造费率（展示23%）">
                          {safeString((queueBomPreview as any)?.trace?.costing?.overhead_rate) || '0.3'}
                        </Descriptions.Item>
                        <Descriptions.Item label="单位成本（CNY/件）">
                          {formatMoney(toNumberOrNull((queueBomPreview as any)?.trace?.costing?.unit_cost))}
                        </Descriptions.Item>
                        <Descriptions.Item label="已计价物料行">
                          {safeString((queueBomPreview as any)?.trace?.costing?.priced_material_lines) ||
                            safeString((queueBomPreview as any)?.trace?.costing?.priced_lines) ||
                            '-'}
                        </Descriptions.Item>
                        <Descriptions.Item label="缺物料单价行">
                          {safeString((queueBomPreview as any)?.trace?.costing?.missing_price_material_lines) ||
                            safeString((queueBomPreview as any)?.trace?.costing?.missing_price_lines) ||
                            '-'}
                        </Descriptions.Item>
                        <Descriptions.Item label="缺工序单价行">
                          {safeString((queueBomPreview as any)?.trace?.costing?.missing_price_process_lines) || '-'}
                        </Descriptions.Item>
                      </Descriptions>
                    ),
                  },
                  {
                    key: 'materials',
                    label: `物料（${(queueBomPreview.final_material_lines ?? []).length}）`,
                    children: (
                      <Table
                        rowKey={(r) =>
                          safeString((r as any).line_index) + '-' + safeString((r as any).material_code)
                        }
                        size="small"
                        pagination={false}
                        columns={[
                          { title: '#', dataIndex: 'line_index', width: 60 },
                          { title: '编码', dataIndex: 'material_code', width: 140, ellipsis: true },
                          { title: '名称', dataIndex: 'material_name', ellipsis: true },
                          { title: '数量', dataIndex: 'computed_quantity', width: 110 },
                          { title: '单位', dataIndex: 'unit_of_measure', width: 80 },
                          { title: '计量', dataIndex: 'calculation_method', width: 100 },
                          { title: 'BOM单价', dataIndex: 'bom_unit_price', width: 120, render: (v) => formatMoney(v) },
                          {
                            title: '行成本',
                            key: 'line_cost',
                            width: 120,
                            render: (_, r) => formatMoney(computeLineCost(r)),
                          },
                        ]}
                        dataSource={(queueBomPreview.final_material_lines ?? []) as any[]}
                      />
                    ),
                  },
                  {
                    key: 'inventory',
                    label: `扣库清单（真实物料）`,
                    children: Array.isArray((queueBomPreview as any)?.trace?.inventory?.inventory_lines) ? (
                      <Table
                        size="small"
                        pagination={false}
                        rowKey={(r) => safeString((r as any).material_code)}
                        columns={[
                          { title: '物料编码', dataIndex: 'material_code', width: 140, ellipsis: true },
                          { title: '物料名称', dataIndex: 'material_name', ellipsis: true },
                          { title: '单位', dataIndex: 'unit_of_measure', width: 90 },
                          { title: '扣库数量', dataIndex: 'quantity', width: 140 },
                          {
                            title: '来源(展开)',
                            dataIndex: 'sources',
                            render: (v) => (Array.isArray(v) ? v.length : 0),
                            width: 110,
                          },
                        ]}
                        dataSource={((queueBomPreview as any)?.trace?.inventory?.inventory_lines ?? []) as any[]}
                      />
                    ) : (
                      <Alert
                        type="info"
                        showIcon
                        message="暂未生成扣库清单（真实物料展开）。"
                        description="当前页面物料表显示的是模型BOM行（可能含虚拟物料）。扣库存应以“扣库清单（真实物料）”为准。"
                      />
                    ),
                  },
                  {
                    key: 'processes',
                    label: `工序（${(((queueBomPreview as any)?.trace?.costing?.process_lines ?? []) as any[]).length}）`,
                    children: Array.isArray((queueBomPreview as any)?.trace?.costing?.process_lines) ? (
                      <Table
                        size="small"
                        pagination={false}
                        rowKey={(r) => safeString((r as any).process_id) + '-' + safeString((r as any).process_code)}
                        columns={[
                          { title: '工序编码', dataIndex: 'process_code', width: 120, ellipsis: true },
                          { title: '工序名称', dataIndex: 'process_name', ellipsis: true },
                          { title: '班组', dataIndex: 'team_name', width: 110, ellipsis: true },
                          { title: '计量', dataIndex: 'pricing_method', width: 90 },
                          { title: '计量值', dataIndex: 'measure_quantity', width: 90 },
                          { title: '计价', dataIndex: 'cost_type', width: 90 },
                          { title: '分钟', dataIndex: 'total_minutes', width: 90 },
                          { title: '分钟单价', dataIndex: 'rate_per_minute', width: 90 },
                          { title: '计件单价', dataIndex: 'piece_rate', width: 90 },
                          { title: '行成本', dataIndex: 'total_cost', width: 110, render: (v) => formatMoney(v) },
                          {
                            title: '警告',
                            dataIndex: 'warnings',
                            width: 220,
                            render: (v) =>
                              Array.isArray(v) && v.length ? <Text type="warning">{String(v.join('；'))}</Text> : '-',
                          },
                        ]}
                        dataSource={((queueBomPreview as any)?.trace?.costing?.process_lines ?? []) as any[]}
                      />
                    ) : (
                      <Alert type="info" showIcon message="该模型版本未配置工序行，或未返回工序明细。" />
                    ),
                  },
                  {
                    key: 'trace',
                    label: 'Trace',
                    children: (
                      <pre style={{ margin: 0, maxHeight: 420, overflow: 'auto' }}>
                        {jsonPretty(queueBomPreview.trace)}
                      </pre>
                    ),
                  },
                ]}
              />
            ) : (
              <Alert type="info" showIcon message="加载中…（若失败会在顶部提示）" />
            )}
          </Space>
        ) : (
          <Alert type="info" showIcon message="请选择一条解析队列记录" />
        )}
      </Drawer>

      <Drawer
        title="BOM 快照详情（只读）"
        open={snapshotDrawerOpen}
        onClose={() => {
          setSnapshotDrawerOpen(false)
          setActiveSnapshot(null)
        }}
        width={980}
      >
        {activeSnapshot ? (
          <div>
            <Descriptions bordered size="small" column={2}>
              <Descriptions.Item label="snapshot_id">{activeSnapshot.id}</Descriptions.Item>
              <Descriptions.Item label="batch_id">{activeSnapshot.batch_id}</Descriptions.Item>
              <Descriptions.Item label="shipment_no">
                {activeSnapshot.shipment_no ?? '-'}
              </Descriptions.Item>
              <Descriptions.Item label="sku_code">{activeSnapshot.sku_code ?? '-'}</Descriptions.Item>
              <Descriptions.Item label="qty">{activeSnapshot.qty ?? '-'}</Descriptions.Item>
              <Descriptions.Item label="model_version_id">
                {activeSnapshot.model_version_id ?? '-'}
              </Descriptions.Item>
              <Descriptions.Item label="spec_hash">{activeSnapshot.spec_hash ?? '-'}</Descriptions.Item>
              <Descriptions.Item label="generated_at">
                {formatTime(activeSnapshot.generated_at)}
              </Descriptions.Item>
            </Descriptions>

            <div style={{ marginTop: 16 }}>
              <Tabs
                items={[
                  {
                    key: 'summary',
                    label: '汇总',
                    children: (
                      <Descriptions bordered size="small" column={3}>
                        <Descriptions.Item label="合计成本（CNY）">
                          <b>{formatMoney(snapshotTotalCost)}</b>
                        </Descriptions.Item>
                        <Descriptions.Item label="物料成本（CNY）">
                          {formatMoney(toNumberOrNull((activeSnapshot as any)?.trace?.costing?.material_cost_total))}
                        </Descriptions.Item>
                        <Descriptions.Item label="工序成本（CNY）">
                          {formatMoney(toNumberOrNull((activeSnapshot as any)?.trace?.costing?.process_cost_total))}
                        </Descriptions.Item>
                        <Descriptions.Item label="制造费用（CNY）">
                          {formatMoney(toNumberOrNull((activeSnapshot as any)?.trace?.costing?.overhead_cost))}
                        </Descriptions.Item>
                        <Descriptions.Item label="制造费率（展示23%）">
                          {safeString((activeSnapshot as any)?.trace?.costing?.overhead_rate) || '0.3'}
                        </Descriptions.Item>
                        <Descriptions.Item label="单位成本（CNY/件）">
                          {formatMoney(toNumberOrNull((activeSnapshot as any)?.trace?.costing?.unit_cost))}
                        </Descriptions.Item>
                      </Descriptions>
                    ),
                  },
                  {
                    key: 'materials',
                    label: `物料（${snapshotLines.length}）`,
                    children: (
                      <Table
                        size="small"
                        columns={snapshotLineCols}
                        dataSource={snapshotLines}
                        pagination={false}
                        scroll={{ x: 960 }}
                      />
                    ),
                  },
                  {
                    key: 'inventory',
                    label: '扣库清单（真实物料）',
                    children: Array.isArray((activeSnapshot as any)?.trace?.inventory?.inventory_lines) ? (
                      <Table
                        size="small"
                        pagination={false}
                        rowKey={(r) => safeString((r as any).material_code)}
                        columns={[
                          { title: '物料编码', dataIndex: 'material_code', width: 140, ellipsis: true },
                          { title: '物料名称', dataIndex: 'material_name', ellipsis: true },
                          { title: '单位', dataIndex: 'unit_of_measure', width: 90 },
                          { title: '扣库数量', dataIndex: 'quantity', width: 140 },
                          {
                            title: '来源(展开)',
                            dataIndex: 'sources',
                            render: (v) => (Array.isArray(v) ? v.length : 0),
                            width: 110,
                          },
                        ]}
                        dataSource={((activeSnapshot as any)?.trace?.inventory?.inventory_lines ?? []) as any[]}
                      />
                    ) : (
                      <Alert
                        type="info"
                        showIcon
                        message="该快照未包含扣库清单（真实物料展开）。"
                        description="可点快照列表的“回填”，重新生成后即可获得真实物料扣库清单。"
                      />
                    ),
                  },
                  {
                    key: 'processes',
                    label: `工序（${(((activeSnapshot as any)?.trace?.costing?.process_lines ?? []) as any[]).length}）`,
                    children: Array.isArray((activeSnapshot as any)?.trace?.costing?.process_lines) ? (
                      <Table
                        size="small"
                        pagination={false}
                        rowKey={(r) => safeString((r as any).process_id) + '-' + safeString((r as any).process_code)}
                        columns={[
                          { title: '工序编码', dataIndex: 'process_code', width: 120, ellipsis: true },
                          { title: '工序名称', dataIndex: 'process_name', ellipsis: true },
                          { title: '班组', dataIndex: 'team_name', width: 110, ellipsis: true },
                          { title: '计量', dataIndex: 'pricing_method', width: 90 },
                          { title: '计量值', dataIndex: 'measure_quantity', width: 90 },
                          { title: '计价', dataIndex: 'cost_type', width: 90 },
                          { title: '分钟', dataIndex: 'total_minutes', width: 90 },
                          { title: '分钟单价', dataIndex: 'rate_per_minute', width: 90 },
                          { title: '计件单价', dataIndex: 'piece_rate', width: 90 },
                          { title: '行成本', dataIndex: 'total_cost', width: 110, render: (v) => formatMoney(v) },
                          {
                            title: '警告',
                            dataIndex: 'warnings',
                            width: 220,
                            render: (v) =>
                              Array.isArray(v) && v.length ? <Text type="warning">{String(v.join('；'))}</Text> : '-',
                          },
                        ]}
                        dataSource={(((activeSnapshot as any)?.trace?.costing?.process_lines ?? []) as any[]).slice(0, 500)}
                      />
                    ) : (
                      <Alert type="info" showIcon message="该快照未包含工序明细（可能当时未开启/未配置）。" />
                    ),
                  },
                  {
                    key: 'trace',
                    label: 'Trace',
                    children: (
                      <pre style={{ margin: 0, maxHeight: 520, overflow: 'auto' }}>
                        {jsonPretty(activeSnapshot.trace)}
                      </pre>
                    ),
                  },
                ]}
              />
            </div>
          </div>
        ) : (
          <Alert type="info" showIcon message="未选择快照" />
        )}
      </Drawer>
    </div>
  )
}

export default ShipmentMonitorPage


