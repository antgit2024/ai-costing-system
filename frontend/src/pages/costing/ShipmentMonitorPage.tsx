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
import { keepPreviousData, useQuery, useQueryClient } from '@tanstack/react-query'

import { fetchShipmentBomSnapshots, fetchShipmentExceptions, fetchShipmentImportBatches, importShipmentsXlsx } from '@/services/planner'
import type { BomSnapshot, ShipmentException, ShipmentImportBatch } from '@/types/planner'

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
  const [batchPage, setBatchPage] = useState(1)
  const [batchPageSize, setBatchPageSize] = useState(DEFAULT_PAGE_SIZE)
  const [selectedBatchId, setSelectedBatchId] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<'batches' | 'exceptions' | 'snapshots'>('batches')

  const [uploading, setUploading] = useState(false)
  const [uploadFile, setUploadFile] = useState<File | null>(null)
  const [uploadExportDate, setUploadExportDate] = useState<string | undefined>(
    dayjs().format('YYYY-MM-DD'),
  )
  const [uploadRequestedBy, setUploadRequestedBy] = useState<string>('planner_user')

  const [exceptionResolved, setExceptionResolved] = useState<'unresolved' | 'resolved' | 'all'>(
    'unresolved',
  )
  const [exceptionLimit, setExceptionLimit] = useState(200)

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

  const snapshotsQuery = useQuery({
    queryKey: ['shipments', 'bom-snapshots', snapshotQuery],
    queryFn: () => fetchShipmentBomSnapshots(snapshotQuery),
    enabled: activeTab === 'snapshots',
  })

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
      width: 110,
      render: (_, record) => (
        <Button
          size="small"
          onClick={() => {
            setActiveSnapshot(record)
            setSnapshotDrawerOpen(true)
          }}
        >
          查看
        </Button>
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
        raw: obj,
      }
    })
  }, [activeSnapshot])

  const snapshotLineCols: ColumnsType<any> = [
    { title: '来源', dataIndex: 'source', width: 110 },
    { title: '编码', dataIndex: 'code', width: 140, ellipsis: true },
    { title: '名称', dataIndex: 'name', ellipsis: true },
    { title: '数量', dataIndex: 'quantity', width: 120 },
    { title: '单位', dataIndex: 'unit', width: 90 },
  ]

  const handleBatchPaginationChange = (pagination: TablePaginationConfig) => {
    const nextPage = pagination.current ?? 1
    const nextSize = pagination.pageSize ?? DEFAULT_PAGE_SIZE
    setBatchPage(nextPage)
    setBatchPageSize(nextSize)
  }

  const handleUploadImport = async () => {
    if (!uploadFile) {
      message.warning('请先选择一个 .xlsx 文件')
      return
    }
    try {
      setUploading(true)
      const batch = await importShipmentsXlsx({
        file: uploadFile,
        export_date: uploadExportDate,
        requested_by: uploadRequestedBy?.trim() || undefined,
      })
      message.success(`导入完成：batch=${batch.id}（inserted=${batch.inserted_rows}, skipped=${batch.skipped_rows}, exceptions=${batch.exception_rows}）`)
      setSelectedBatchId(batch.id)
      setActiveTab('batches')
      setBatchPage(1)
      queryClient.invalidateQueries({ queryKey: ['shipments'] })
    } catch (err: any) {
      message.error(`导入失败：${err?.response?.data?.detail ?? err?.message ?? 'unknown error'}`)
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
        <Card title="上传发货单（xlsx 导入）" size="small">
          <Row gutter={[16, 16]} align="middle">
            <Col xs={24} lg={10}>
              <Upload
                accept=".xlsx"
                maxCount={1}
                beforeUpload={(file) => {
                  setUploadFile(file as any)
                  return false
                }}
                onRemove={() => {
                  setUploadFile(null)
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
              <Button type="primary" loading={uploading} onClick={handleUploadImport} block>
                上传并导入
              </Button>
            </Col>
          </Row>
          <div style={{ marginTop: 8 }}>
            <Text type="secondary">
              说明：后端按 file_hash 做文件级幂等；重复上传同文件会直接返回已成功的 batch。
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

            <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
              <Col span={14}>
                <Card title="final_material_lines（概要）" size="small">
                  <Table
                    size="small"
                    columns={snapshotLineCols}
                    dataSource={snapshotLines}
                    pagination={false}
                    scroll={{ x: 720 }}
                  />
                </Card>
              </Col>
              <Col span={10}>
                <Card title="trace（JSON）" size="small">
                  <pre style={{ margin: 0, whiteSpace: 'pre-wrap' }}>
                    {jsonPretty(activeSnapshot.trace)}
                  </pre>
                </Card>
              </Col>
            </Row>
          </div>
        ) : (
          <Alert type="info" showIcon message="未选择快照" />
        )}
      </Drawer>
    </div>
  )
}

export default ShipmentMonitorPage


