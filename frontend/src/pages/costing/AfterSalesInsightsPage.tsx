import { Alert, Button, Card, DatePicker, Form, Input, Select, Space, Table, Typography, Upload, message } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import dayjs from 'dayjs'
import { useMemo, useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'

import { fetchAfterSalesImportBatches, fetchReturnsRateBySku, importAfterSalesXlsx } from '@/services/planner'
import type { AfterSalesImportBatch, ReturnsRateBySkuItem, ReturnsRateBySkuResponse } from '@/types/planner'

type GroupBy = 'day' | 'month'

const formatPercent = (raw?: string | null) => {
  if (!raw) return '-'
  const n = Number(raw)
  if (!Number.isFinite(n)) return '-'
  return `${(n * 100).toFixed(2)}%`
}

const formatMoney = (raw?: string) => {
  if (raw == null) return '-'
  const n = Number(raw)
  if (!Number.isFinite(n)) return String(raw)
  return n.toFixed(2)
}

const formatQty = (raw?: string) => {
  if (raw == null) return '-'
  const n = Number(raw)
  if (!Number.isFinite(n)) return String(raw)
  return n.toFixed(2).replace(/\.00$/, '')
}

const AfterSalesInsightsPage = () => {
  const [form] = Form.useForm()
  const [loading, setLoading] = useState(false)
  const [data, setData] = useState<ReturnsRateBySkuResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)
  const [uploadFile, setUploadFile] = useState<File | null>(null)
  const [uploadExportDate, setUploadExportDate] = useState<string | undefined>(dayjs().format('YYYY-MM-DD'))
  const [uploadRequestedBy, setUploadRequestedBy] = useState<string>('planner_user')
  const [lastImportSummary, setLastImportSummary] = useState<string | null>(null)
  const [batchPage, setBatchPage] = useState(1)
  const [batchPageSize, setBatchPageSize] = useState(10)

  const batchesQuery = useQuery({
    queryKey: ['after-sales', 'import-batches', batchPage, batchPageSize],
    queryFn: () => fetchAfterSalesImportBatches({ page: batchPage, page_size: batchPageSize }),
    placeholderData: keepPreviousData,
  })

  const columns = useMemo<ColumnsType<ReturnsRateBySkuItem>>(
    () => [
      { title: '周期', dataIndex: 'period', key: 'period', width: 160 },
      { title: '渠道', dataIndex: 'channel', key: 'channel', width: 160 },
      { title: '货品条码', dataIndex: 'sku_code', key: 'sku_code', width: 160 },
      { title: '发货数量', dataIndex: 'shipped_qty', key: 'shipped_qty', width: 120, render: formatQty },
      { title: '退货数量', dataIndex: 'returned_qty', key: 'returned_qty', width: 120, render: formatQty },
      { title: '退货率(件)', dataIndex: 'return_rate', key: 'return_rate', width: 120, render: formatPercent },
      { title: '发货金额', dataIndex: 'shipped_amount', key: 'shipped_amount', width: 120, render: formatMoney },
      { title: '退款金额', dataIndex: 'refund_amount', key: 'refund_amount', width: 120, render: formatMoney },
      { title: '退款率(额)', dataIndex: 'refund_rate', key: 'refund_rate', width: 120, render: formatPercent },
    ],
    [],
  )

  const onQuery = async () => {
    setError(null)
    setData(null)

    const v = await form.validateFields()
    const range = v.range as [dayjs.Dayjs, dayjs.Dayjs]
    const groupBy = v.group_by as GroupBy

    // 只按用户选择的范围查询；不做后台全量计算/全量重跑
    const start = range[0].startOf('day').toISOString()
    const end = range[1].endOf('day').toISOString()

    setLoading(true)
    try {
      const resp = await fetchReturnsRateBySku({
        start,
        end,
        group_by: groupBy,
        channel: v.channel?.trim() || undefined,
        sku_code: v.sku_code?.trim() || undefined,
      }, { timeoutMs: 120000 })
      setData(resp)
    } catch (e: any) {
      setError(String(e?.response?.data?.detail ?? e?.message ?? e))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ padding: 16 }}>
      <Typography.Title level={3} style={{ margin: '0 0 12px' }}>
        数据洞察 / 售后分析（退货率）
      </Typography.Title>

      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 12 }}
        message="说明（2025 分析期：边搭建边算）"
        description={
          <div>
            <div>本页只在你选择的时间范围内查询汇总，不会全量重算。</div>
            <div>
              退货归因采用强关联键：<b>订单号 + 商品链接ID + 货品条码</b>。若某些货品尚未绑定模型，也不影响货品维度的退货率统计。
            </div>
          </div>
        }
      />

      <Card title="上传售后退货单（xlsx 导入）" size="small" style={{ marginBottom: 12 }}>
        <Space wrap style={{ width: '100%', justifyContent: 'space-between' }}>
          <Space wrap>
            <Upload
              accept=".xlsx"
              maxCount={1}
              beforeUpload={(file) => {
                setUploadFile(file as any)
                return false
              }}
              onRemove={() => setUploadFile(null)}
            >
              <Button disabled={uploading}>选择文件（.xlsx）</Button>
            </Upload>
            <Typography.Text type="secondary">{uploadFile ? uploadFile.name : '未选择文件'}</Typography.Text>
          </Space>
          <Space wrap>
            <Typography.Text>导出日期</Typography.Text>
            <DatePicker
              allowClear
              value={uploadExportDate ? dayjs(uploadExportDate) : null}
              format="YYYY-MM-DD"
              onChange={(d) => setUploadExportDate(d ? d.format('YYYY-MM-DD') : undefined)}
            />
            <Input
              placeholder="requested_by（可空）"
              style={{ width: 180 }}
              value={uploadRequestedBy}
              onChange={(e) => setUploadRequestedBy(e.target.value)}
            />
            <Button
              type="primary"
              loading={uploading}
              onClick={async () => {
                if (!uploadFile) {
                  message.warning('请先选择一个 .xlsx 文件')
                  return
                }
                setUploading(true)
                try {
                  const resp = await importAfterSalesXlsx({
                    file: uploadFile,
                    export_date: uploadExportDate,
                    requested_by: uploadRequestedBy?.trim() || undefined,
                  })
                  setLastImportSummary(
                    `导入成功：batch=${resp.id}，插入${resp.inserted_rows}，跳过${resp.skipped_rows}，异常${resp.exception_rows}`,
                  )
                  message.success('售后退货单导入成功')
                  setUploadFile(null)
                  batchesQuery.refetch()
                } catch (e: any) {
                  message.error(String(e?.response?.data?.detail ?? e?.message ?? e))
                } finally {
                  setUploading(false)
                }
              }}
            >
              上传并导入
            </Button>
          </Space>
        </Space>
        {lastImportSummary ? (
          <Alert style={{ marginTop: 12 }} type="success" showIcon message="最近一次导入" description={lastImportSummary} />
        ) : (
          <Typography.Text type="secondary" style={{ display: 'block', marginTop: 8 }}>
            说明：先导入发货单（`/costing/shipments`），再导入售后退货单；然后到本页选择时间范围点击“查询”。
          </Typography.Text>
        )}
      </Card>

      <Card
        title="导入记录（最近）"
        size="small"
        style={{ marginBottom: 12 }}
        extra={
          <Button size="small" onClick={() => batchesQuery.refetch()} loading={batchesQuery.isFetching}>
            刷新
          </Button>
        }
      >
        <Table<AfterSalesImportBatch>
          rowKey="id"
          size="small"
          loading={batchesQuery.isFetching}
          dataSource={(batchesQuery.data?.items ?? []) as AfterSalesImportBatch[]}
          pagination={{
            current: batchPage,
            pageSize: batchPageSize,
            total: batchesQuery.data?.total ?? 0,
            showSizeChanger: true,
            onChange: (p, ps) => {
              setBatchPage(p)
              setBatchPageSize(ps)
            },
          }}
          columns={[
            { title: '导入批次', dataIndex: 'id', width: 220, ellipsis: true },
            { title: '文件名', dataIndex: 'file_name', width: 220, ellipsis: true },
            { title: '导出日期', dataIndex: 'export_date', width: 120, render: (v) => String(v ?? '-') },
            { title: '插入', dataIndex: 'inserted_rows', width: 90 },
            { title: '跳过', dataIndex: 'skipped_rows', width: 90 },
            { title: '异常', dataIndex: 'exception_rows', width: 90 },
            { title: '状态', dataIndex: 'status', width: 120 },
            { title: '导入时间', dataIndex: 'created_at', width: 180, ellipsis: true },
          ]}
          scroll={{ x: 1100 }}
        />
        <Typography.Text type="secondary">
          提示：若“查询为空/失败”，通常是 1）还没导入发货单（`/costing/shipments`），或 2）时间范围过大导致查询超时；可先缩小到 7~30 天再试。
        </Typography.Text>
      </Card>

      <Card size="small" style={{ marginBottom: 12 }}>
        <Form
          form={form}
          layout="inline"
          initialValues={{
            group_by: 'month',
            range: [dayjs().subtract(30, 'day'), dayjs()],
          }}
        >
          <Form.Item
            label="时间范围"
            name="range"
            rules={[{ required: true, message: '请选择时间范围' }]}
          >
            <DatePicker.RangePicker allowClear={false} />
          </Form.Item>
          <Form.Item label="粒度" name="group_by">
            <Select style={{ width: 100 }} options={[{ value: 'month', label: '按月' }, { value: 'day', label: '按日' }]} />
          </Form.Item>
          <Form.Item label="渠道" name="channel">
            <Input placeholder="可选：店铺/渠道" style={{ width: 160 }} allowClear />
          </Form.Item>
          <Form.Item label="货品条码" name="sku_code">
            <Input placeholder="可选：barcode" style={{ width: 180 }} allowClear />
          </Form.Item>
          <Form.Item>
            <Space>
              <Button type="primary" onClick={onQuery} loading={loading}>
                查询
              </Button>
              <Button
                onClick={() => {
                  form.resetFields()
                  setData(null)
                  setError(null)
                }}
              >
                重置
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Card>

      {error ? (
        <Alert type="error" showIcon message="查询失败" description={error} style={{ marginBottom: 12 }} />
      ) : null}

      {data?.unmatched_returns_missing_order_no ? (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 12 }}
          message="数据质量提示"
          description={`存在 ${data.unmatched_returns_missing_order_no} 条售后记录缺少订单号，无法参与强关联归因（建议在 ERP 导出时开启网店订单号）。`}
        />
      ) : null}

      <Card size="small">
        <Table<ReturnsRateBySkuItem>
          rowKey={(r) => `${r.period}-${r.channel ?? ''}-${r.sku_code ?? ''}`}
          loading={loading}
          columns={columns}
          dataSource={data?.items ?? []}
          pagination={{ pageSize: 50, showSizeChanger: true }}
          scroll={{ x: 1100 }}
        />
      </Card>
    </div>
  )
}

export default AfterSalesInsightsPage

