import { Alert, Button, Card, DatePicker, Descriptions, Divider, Form, Row, Col, Select, Space, Table, Tabs, Tag, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import dayjs from 'dayjs'
import { useMemo, useState } from 'react'

import { fetchModelInsightsDetail, fetchModelInsightsSummary, fetchModelUsageMaterialsSummary, fetchModelUsageProcessesSummary } from '@/services/planner'
import type {
  ModelInsightsDetailResponse,
  ModelInsightsSummaryItem,
  ModelInsightsSummaryResponse,
  ModelUsageMaterialSummaryResponse,
  ModelUsageProcessSummaryResponse,
} from '@/types/planner'

const hashString = (s: string) => {
  let h = 0
  for (let i = 0; i < s.length; i += 1) {
    h = (h * 31 + s.charCodeAt(i)) | 0
  }
  return Math.abs(h)
}

const formatPercent = (raw?: string | number | null) => {
  if (raw == null || raw === '') return '-'
  const n = Number(raw)
  if (!Number.isFinite(n)) return '-'
  return `${(n * 100).toFixed(2)}%`
}

const formatMoney = (raw?: string | number | null) => {
  if (raw == null || raw === '') return '-'
  const n = Number(raw)
  if (!Number.isFinite(n)) return String(raw)
  return n.toFixed(2)
}

const formatQty = (raw?: string | number | null) => {
  if (raw == null || raw === '') return '-'
  const n = Number(raw)
  if (!Number.isFinite(n)) return String(raw)
  return n.toFixed(2).replace(/\.00$/, '')
}

const formatCoveragePercent = (num: number, den: number) => {
  if (!den) return '-'
  const pct = (num / den) * 100
  return `${pct.toFixed(1)}%`
}

const ProfitInsightsPage = () => {
  const [form] = Form.useForm()
  const [loadingSummary, setLoadingSummary] = useState(false)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [summary, setSummary] = useState<ModelInsightsSummaryResponse | null>(null)
  const [detail, setDetail] = useState<ModelInsightsDetailResponse | null>(null)
  const [usageMaterials, setUsageMaterials] = useState<ModelUsageMaterialSummaryResponse | null>(null)
  const [usageProcesses, setUsageProcesses] = useState<ModelUsageProcessSummaryResponse | null>(null)
  const [loadingUsage, setLoadingUsage] = useState(false)
  const [selectedModelCode, setSelectedModelCode] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const shopOptions = useMemo(() => {
    const s = new Set<string>()
    for (const it of summary?.items ?? []) {
      const v = String((it as any)?.channel ?? '').trim()
      if (v) s.add(v)
    }
    return Array.from(s)
      .sort((a, b) => a.localeCompare(b))
      .map((v) => ({ value: v, label: v }))
  }, [summary])

  const onQuerySummary = async () => {
    setError(null)
    const v = await form.validateFields()
    const range = v.range as [dayjs.Dayjs, dayjs.Dayjs]
    const start = range[0].startOf('day').toISOString()
    const end = range[1].endOf('day').toISOString()

    setLoadingSummary(true)
    try {
      const resp = await fetchModelInsightsSummary({
        start,
        end,
        channel: v.channel?.trim() || undefined,
      })
      setSummary(resp)
      // reset selection when query changes
      setSelectedModelCode(null)
      setDetail(null)
    } catch (e: any) {
      setError(String(e?.response?.data?.detail ?? e?.message ?? e))
    } finally {
      setLoadingSummary(false)
    }
  }

  const loadDetail = async (modelCode: string, versionId?: string) => {
    const v = await form.validateFields()
    const range = v.range as [dayjs.Dayjs, dayjs.Dayjs]
    const start = range[0].startOf('day').toISOString()
    const end = range[1].endOf('day').toISOString()
    setLoadingDetail(true)
    try {
      const resp = await fetchModelInsightsDetail({
        start,
        end,
        channel: v.channel?.trim() || undefined,
        model_code: modelCode,
        version_id: versionId || undefined,
      })
      setDetail(resp)
      setLoadingUsage(true)
      try {
        const [mats, procs] = await Promise.all([
          fetchModelUsageMaterialsSummary({
            start,
            end,
            channel: v.channel?.trim() || undefined,
            model_code: modelCode,
            version_id: versionId || undefined,
          }),
          fetchModelUsageProcessesSummary({
            start,
            end,
            channel: v.channel?.trim() || undefined,
            model_code: modelCode,
            version_id: versionId || undefined,
          }),
        ])
        setUsageMaterials(mats)
        setUsageProcesses(procs)
      } finally {
        setLoadingUsage(false)
      }
    } catch (e: any) {
      setError(String(e?.response?.data?.detail ?? e?.message ?? e))
    } finally {
      setLoadingDetail(false)
    }
  }

  const bom = detail?.bom as any
  const bomCosting = (bom?.trace?.costing ?? {}) as any
  const bomFinalLines = (bom?.final_material_lines ?? []) as any[]
  const bomProcessLines = (bomCosting?.process_lines ?? []) as any[]
  const traceInventory = (bom?.trace?.inventory ?? {}) as any
  const traceInventoryLines = (traceInventory?.inventory_lines ?? []) as any[]

  // 右侧表格列宽：完全对齐 ProductListingPage（测试台）
  const bomMaterialColumns = useMemo<ColumnsType<any>>(
    () => [
      { title: '编码', dataIndex: 'material_code', width: 120, render: (v) => v ?? '-' },
      { title: '名称', dataIndex: 'material_name', width: 220, ellipsis: true, render: (v) => v ?? '-' },
      { title: '数量', dataIndex: 'computed_quantity', width: 90, render: (v) => (v == null ? '-' : String(v)) },
      { title: '单位', dataIndex: 'unit_of_measure', width: 90, render: (v) => v ?? '-' },
      { title: '计量方式', dataIndex: 'calculation_method', width: 90, render: (v) => String(v ?? '-') },
      { title: '损耗%', dataIndex: 'loss_rate', width: 90, render: (v) => (v == null ? '-' : String(v)) },
      {
        title: 'BOM单价',
        dataIndex: 'bom_unit_price',
        width: 90,
        render: (v) => {
          const miss = v == null || v === ''
          return (
            <Space size={6}>
              <Typography.Text>{formatMoney(String(v ?? ''))}</Typography.Text>
              {miss ? <Tag color="red">缺单价</Tag> : null}
            </Space>
          )
        },
      },
      {
        title: '行成本',
        dataIndex: 'line_cost',
        render: (v, r: any) => {
          const miss = (r as any)?.bom_unit_price == null || (r as any)?.bom_unit_price === ''
          return (
            <Space size={6}>
              <Typography.Text>{formatMoney(String(v ?? ''))}</Typography.Text>
              {miss ? <Tag color="red">缺单价</Tag> : null}
            </Space>
          )
        },
      },
    ],
    [],
  )

  const bomProcessColumns = useMemo<ColumnsType<any>>(
    () => [
      { title: '工序编码', dataIndex: 'process_code', width: 120, ellipsis: true },
      { title: '工序名称', dataIndex: 'process_name', width: 220, ellipsis: true },
      { title: '班组', dataIndex: 'team_name', width: 110, ellipsis: true },
      { title: '计量', dataIndex: 'pricing_method', width: 90 },
      { title: '计量值', dataIndex: 'measure_quantity', width: 90 },
      { title: '计价', dataIndex: 'cost_type', width: 90 },
      { title: '分钟', dataIndex: 'total_minutes', width: 90 },
      { title: '分钟单价', dataIndex: 'rate_per_minute', width: 90 },
      { title: '计件单价', dataIndex: 'piece_rate', width: 90 },
      { title: '行成本', dataIndex: 'total_cost', width: 110, render: (v) => formatMoney(String(v ?? '')) },
      {
        title: '警告',
        dataIndex: 'warnings',
        render: (v) => (Array.isArray(v) && v.length ? <Typography.Text type="warning">{String(v.join('；'))}</Typography.Text> : '-'),
      },
    ],
    [],
  )

  const deductionColumns = useMemo<ColumnsType<any>>(
    () => [
      { title: '物料编码', dataIndex: 'material_code', width: 120, ellipsis: true },
      { title: '物料名称', dataIndex: 'material_name', width: 220, ellipsis: true },
      { title: '单位', dataIndex: 'unit_of_measure', width: 90 },
      { title: '扣库数量', dataIndex: 'quantity', width: 90 },
      { title: '来源(展开)', dataIndex: 'sources', render: (v) => (v == null ? '-' : String(v)) },
    ],
    [],
  )

  const usageMaterialColumns = useMemo<ColumnsType<any>>(
    () => [
      { title: '物料编码', dataIndex: 'material_code', width: 140, ellipsis: true, render: (v) => v ?? '-' },
      { title: '物料名称', dataIndex: 'material_name', width: 240, ellipsis: true, render: (v) => v ?? '-' },
      { title: '单位', dataIndex: 'unit_of_measure', width: 80, render: (v) => v ?? '-' },
      { title: '合计用量', dataIndex: 'total_quantity', width: 120, align: 'right', render: (v) => formatQty(v as any) },
      { title: '覆盖行数', dataIndex: 'line_count', width: 90, align: 'right', render: (v) => String(v ?? 0) },
    ],
    [],
  )

  const usageProcessColumns = useMemo<ColumnsType<any>>(
    () => [
      { title: '工序编码', dataIndex: 'process_code', width: 140, ellipsis: true, render: (v) => v ?? '-' },
      { title: '工序名称', dataIndex: 'process_name', width: 240, ellipsis: true, render: (v) => v ?? '-' },
      { title: '班组', dataIndex: 'team_name', width: 120, ellipsis: true, render: (v) => v ?? '-' },
      { title: '合计分钟', dataIndex: 'total_minutes', width: 110, align: 'right', render: (v) => formatQty(v as any) },
      { title: '合计成本', dataIndex: 'total_cost', width: 120, align: 'right', render: (v) => formatMoney(v as any) },
      { title: '覆盖行数', dataIndex: 'line_count', width: 90, align: 'right', render: (v) => String(v ?? 0) },
    ],
    [],
  )

  const renderModelCodePill = (code: string) => {
    const text = String(code ?? '').trim()
    if (!text) return <Typography.Text type="secondary">-</Typography.Text>

    // Use Ant Design theme colors (deterministic per code)
    const palette = [
      'var(--ant-color-blue)',
      'var(--ant-color-purple)',
      'var(--ant-color-cyan)',
      'var(--ant-color-green)',
      'var(--ant-color-magenta)',
      'var(--ant-color-volcano)',
      'var(--ant-color-gold)',
      'var(--ant-color-geekblue)',
    ]
    const c = palette[hashString(text) % palette.length] ?? 'var(--ant-color-primary)'
    return (
      <span
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          height: 22,
          padding: '0 8px',
          borderRadius: 999,
          border: `1px solid color-mix(in srgb, ${c} 45%, var(--ant-color-border))`,
          background: `color-mix(in srgb, ${c} 18%, var(--ant-color-fill-tertiary))`,
          color: c,
          fontWeight: 600,
          fontSize: 12,
          lineHeight: '22px',
          whiteSpace: 'nowrap',
        }}
      >
        {text}
      </span>
    )
  }

  const renderVersionLabelPill = (label: string) => {
    const text = String(label ?? '').trim()
    if (!text) return <Typography.Text type="secondary">-</Typography.Text>
    return (
      <span
        style={{
          display: 'inline-block',
          padding: '0px 6px',
          borderRadius: 6,
          border: '1px solid color-mix(in srgb, var(--ant-color-success) 45%, var(--ant-color-border))',
          background: 'color-mix(in srgb, var(--ant-color-success) 18%, var(--ant-color-fill-tertiary))',
          fontSize: 11,
          lineHeight: '18px',
          color: 'var(--ant-color-success)',
          whiteSpace: 'nowrap',
        }}
      >
        {text}
      </span>
    )
  }

  const modelListColumns = useMemo<ColumnsType<ModelInsightsSummaryItem>>(
    () => [
      {
        title: '编码',
        key: 'model_code',
        width: 90,
        fixed: 'left',
        render: (_: any, r) => renderModelCodePill(String(r.model_code ?? '')),
      },
      {
        title: '模型名称',
        dataIndex: 'model_name',
        width: 180,
        ellipsis: true,
        render: (v) => (
          <Typography.Text style={{ fontSize: 13 }} ellipsis>
            {String(v ?? '-') || '-'}
          </Typography.Text>
        ),
      },
      { title: '发货数量', dataIndex: 'shipped_qty', width: 90, align: 'right', render: (v) => formatQty(v as any) },
      { title: '销售金额', dataIndex: 'revenue_amount', width: 110, align: 'right', render: (v) => formatMoney(v as any) },
      { title: '成本', dataIndex: 'cost_amount', width: 110, align: 'right', render: (v) => formatMoney(v as any) },
      { title: '毛利', dataIndex: 'gross_profit', width: 110, align: 'right', render: (v) => formatMoney(v as any) },
      { title: '毛利率', dataIndex: 'gross_margin', width: 90, align: 'right', render: (v) => formatPercent(v as any) },
      {
        title: '退货数量',
        dataIndex: 'returned_qty',
        width: 90,
        align: 'right',
        render: (_v: any, r) => formatQty(((r as any)?.returned_qty ?? '-') as any),
      },
      { title: '退货金额', dataIndex: 'refund_amount', width: 110, align: 'right', render: (v) => formatMoney(v as any) },
    ],
    [],
  )

  return (
    <div style={{ padding: 16 }}>
      <Typography.Title level={3} style={{ margin: '0 0 12px' }}>
        数据洞察 / 模型分析
      </Typography.Title>

      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 12 }}
        message="说明（模型分析 = 统计 + 可解释明细）"
        description={
          <div>
            <div>左侧：按店铺+日期筛选后，列出“模型统计榜单”（不展示发货明细）。</div>
            <div>右侧：点选某个模型后，展示版本、最终BOM、工序、扣库单，用于解释与核对口径。</div>
          </div>
        }
      />

      {error ? <Alert type="error" showIcon message="查询失败" description={error} style={{ marginBottom: 12 }} /> : null}

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={10}>
          <Card
            size="small"
            title="模型统计榜单"
            extra={<Typography.Text type="secondary">选店铺+日期 → 查询 → 点击模型看右侧明细</Typography.Text>}
          >
            <Form
              form={form}
              layout="vertical"
              initialValues={{
                range: [dayjs().subtract(30, 'day'), dayjs()],
              }}
            >
              <Row gutter={12}>
                <Col span={24}>
                  <Form.Item label="店铺" name="channel">
                    <Select
                      placeholder="可选：选择店铺（不选=全部店铺）"
                      allowClear
                      showSearch
                      options={shopOptions}
                      filterOption={(input, option) =>
                        String(option?.label ?? '').toLowerCase().includes(String(input ?? '').toLowerCase())
                      }
                    />
                  </Form.Item>
                </Col>
                <Col span={24}>
                  <Form.Item label="日期范围" name="range" rules={[{ required: true, message: '请选择日期范围' }]}>
                    <DatePicker.RangePicker allowClear={false} style={{ width: '100%' }} />
                  </Form.Item>
                </Col>
                <Col span={24}>
                  <Space>
                    <Button type="primary" onClick={onQuerySummary} loading={loadingSummary}>
                      查询
                    </Button>
                    <Button
                      onClick={() => {
                        form.resetFields()
                        setSummary(null)
                        setSelectedModelCode(null)
                        setDetail(null)
                        setError(null)
                      }}
                    >
                      重置
                    </Button>
                  </Space>
                </Col>
              </Row>
            </Form>

            <Divider style={{ margin: '12px 0' }} />

            {summary ? (
              <Alert
                type={(summary.mapped_model_lines ?? 0) === (summary.total_shipment_lines ?? 0) ? 'success' : 'warning'}
                showIcon
                style={{ marginBottom: 12 }}
                message="覆盖率（按行数｜本次范围内）"
                description={
                  <div>
                    <div>
                      总发货行：{summary.total_shipment_lines ?? 0}；已归因到模型：{summary.mapped_model_lines ?? 0}（覆盖率{' '}
                      {formatCoveragePercent(summary.mapped_model_lines ?? 0, summary.total_shipment_lines ?? 0)}）
                    </div>
                    <div>
                      已计价行：{summary.costed_lines ?? 0}；缺成本字段行：{summary.lines_missing_costing ?? 0}
                    </div>
                  </div>
                }
              />
            ) : null}

            <Table<ModelInsightsSummaryItem>
              size="small"
              loading={loadingSummary}
              rowKey={(r) => String(r.model_code ?? '') || String((r as any)?.model_id ?? '')}
              dataSource={(summary?.items ?? []).slice()}
              columns={modelListColumns}
              pagination={{ pageSize: 12, showSizeChanger: true }}
              locale={{ emptyText: '暂无数据（请先选择范围并查询）' }}
              onRow={(r) => ({
                onClick: async () => {
                  const code = String(r.model_code ?? '').trim()
                  if (!code) return
                  setSelectedModelCode(code)
                  await loadDetail(code)
                },
              })}
              rowClassName={(r) => (String(r.model_code ?? '') === String(selectedModelCode ?? '') ? 'ant-table-row-selected' : '')}
              scroll={{ x: 980 }}
            />
          </Card>
        </Col>

        <Col xs={24} lg={14}>
          <Card
            size="small"
            title="模型明细"
            extra={
              selectedModelCode ? (
                <Space size={8}>
                  <Typography.Text type="secondary">已选：</Typography.Text>
                  <Typography.Text strong>{selectedModelCode}</Typography.Text>
                </Space>
              ) : (
                <Typography.Text type="secondary">从左侧点击一个模型</Typography.Text>
              )
            }
          >
            {detail ? (
              <>
                <Space wrap style={{ marginBottom: 12 }}>
                  <Typography.Text strong>{detail.model_name}</Typography.Text>
                  <Tag>{detail.model_code}</Tag>
                  {loadingDetail ? <Tag>加载中…</Tag> : null}
                </Space>

                <Card size="small" title="版本（本次范围内出现过的版本）" style={{ marginBottom: 12 }}>
                  <Table
                    size="small"
                    pagination={false}
                    rowKey={(r: any) => String(r.version_id)}
                    dataSource={detail.versions ?? []}
                    columns={[
                      {
                        title: '版本',
                        key: 'ver',
                        width: 260,
                        render: (_: any, r: any) => renderVersionLabelPill(String(r.version_label ?? String(r.version_id).slice(0, 8))),
                      },
                      { title: '发货数量', dataIndex: 'shipped_qty', width: 100, render: formatQty },
                      { title: '销售额', dataIndex: 'revenue_amount', width: 110, render: formatMoney },
                      { title: '物料成本', dataIndex: 'cost_material_amount', width: 110, render: formatMoney },
                      { title: '人工成本', dataIndex: 'cost_process_amount', width: 110, render: formatMoney },
                      { title: '制造费用', dataIndex: 'cost_overhead_amount', width: 110, render: formatMoney },
                      { title: '成本', dataIndex: 'cost_amount', width: 110, render: formatMoney },
                      { title: '毛利率', dataIndex: 'gross_margin', width: 100, render: formatPercent },
                      { title: '行数', dataIndex: 'line_count', width: 80, render: (v) => String(v ?? '-') },
                    ]}
                    onRow={(r: any) => ({
                      onClick: async () => {
                        if (!selectedModelCode) return
                        await loadDetail(selectedModelCode, String(r.version_id))
                      },
                    })}
                    rowClassName={(r: any) =>
                      String(r.version_id || '') === String(detail.selected_version_id || '') ? 'ant-table-row-selected' : ''
                    }
                    scroll={{ x: 1250 }}
                  />
                </Card>

                <Card size="small" title="发货合计（真实明细汇总）" style={{ marginBottom: 12 }}>
                  <Alert
                    type="info"
                    showIcon
                    style={{ marginBottom: 10 }}
                    message="口径"
                    description={
                      <div>
                        <div>物料合计：按发货行的“扣库明细（落库）”汇总（更贴近对账/损耗口径）。</div>
                        <div>工序合计：按发货行最新 BOM 快照 trace.costing.process_lines 汇总（2025 轻量结果可能缺工序明细）。</div>
                      </div>
                    }
                  />

                  <Tabs
                    defaultActiveKey="materials"
                    items={[
                      {
                        key: 'materials',
                        label: '物料合计',
                        children: (
                          <Space direction="vertical" size={10} style={{ width: '100%' }}>
                            <Alert
                              type="warning"
                              showIcon
                              message="覆盖率（物料明细）"
                              description={
                                <div>
                                  <div>
                                    归因发货行：{usageMaterials?.mapped_model_lines ?? '-'}；其中有扣库明细：{usageMaterials?.lines_with_deductions ?? '-'}
                                  </div>
                                  <div>
                                    归因发货数量：{formatQty(usageMaterials?.shipped_qty_total ?? null)}；有扣库明细的发货数量：
                                    {formatQty(usageMaterials?.shipped_qty_covered ?? null)}
                                  </div>
                                </div>
                              }
                            />
                            <Table
                              size="small"
                              loading={loadingUsage}
                              pagination={{ pageSize: 20, showSizeChanger: true }}
                              rowKey={(r: any) => String(r.material_code ?? r.material_id ?? '')}
                              dataSource={usageMaterials?.items ?? []}
                              columns={usageMaterialColumns}
                              scroll={{ x: 760 }}
                              locale={{ emptyText: '暂无物料扣库明细（可能覆盖率较低或未落库扣库明细）' }}
                            />
                          </Space>
                        ),
                      },
                      {
                        key: 'processes',
                        label: '工序合计',
                        children: (
                          <Space direction="vertical" size={10} style={{ width: '100%' }}>
                            <Alert
                              type="warning"
                              showIcon
                              message="覆盖率（工序明细）"
                              description={
                                <div>
                                  <div>
                                    归因发货行：{usageProcesses?.mapped_model_lines ?? '-'}；其中有工序明细：{usageProcesses?.lines_with_process_details ?? '-'}
                                  </div>
                                  <div>
                                    归因发货数量：{formatQty(usageProcesses?.shipped_qty_total ?? null)}；有工序明细的发货数量：
                                    {formatQty(usageProcesses?.shipped_qty_covered ?? null)}
                                  </div>
                                </div>
                              }
                            />
                            <Table
                              size="small"
                              loading={loadingUsage}
                              pagination={{ pageSize: 20, showSizeChanger: true }}
                              rowKey={(r: any, idx) => String(r.process_code ?? '') + '-' + String(r.team_name ?? '') + '-' + String(idx)}
                              dataSource={usageProcesses?.items ?? []}
                              columns={usageProcessColumns}
                              scroll={{ x: 860 }}
                              locale={{ emptyText: '暂无工序明细（可能尚未落 BOM 快照/或 2025 轻量结果缺工序明细）' }}
                            />
                          </Space>
                        ),
                      },
                    ]}
                  />
                </Card>

                <Tabs
                  defaultActiveKey="bom"
                  items={[
                    {
                      key: 'bom',
                      label: `最终 BOM（final_material_lines）`,
                      children: (
                        <Space direction="vertical" style={{ width: '100%' }} size={12}>
                          <Descriptions bordered size="small" column={3}>
                            <Descriptions.Item label="合计成本（CNY）">
                              <b>{formatMoney(String(bomCosting?.total_cost ?? ''))}</b>
                            </Descriptions.Item>
                            <Descriptions.Item label="物料成本（CNY）">{formatMoney(String(bomCosting?.material_cost_total ?? ''))}</Descriptions.Item>
                            <Descriptions.Item label="工序成本（CNY）">{formatMoney(String(bomCosting?.process_cost_total ?? ''))}</Descriptions.Item>
                            <Descriptions.Item label="制造费用（CNY）">{formatMoney(String(bomCosting?.overhead_cost ?? ''))}</Descriptions.Item>
                            <Descriptions.Item label="制造费率">{bomCosting?.overhead_rate == null ? '-' : String(bomCosting?.overhead_rate)}</Descriptions.Item>
                            <Descriptions.Item label="单位成本（CNY/件）">{formatMoney(String(bomCosting?.unit_cost ?? ''))}</Descriptions.Item>
                          </Descriptions>

                          <Divider style={{ margin: '4px 0' }} />
                          <Typography.Text strong>物料（{bomFinalLines.length}）</Typography.Text>
                          <Table
                            size="small"
                            pagination={false}
                            rowKey={(r: any, idx) => String(r?.id ?? `${r?.material_ref_id ?? ''}-${r?.sequence_order ?? ''}-${idx}`)}
                            dataSource={bomFinalLines}
                            columns={bomMaterialColumns}
                            scroll={{ x: 950 }}
                          />

                          <Divider style={{ margin: '4px 0' }} />
                          <Typography.Text strong>工序（{bomProcessLines.length}）</Typography.Text>
                          <Table
                            size="small"
                            pagination={false}
                            rowKey={(r: any, idx) => String(r?.process_id ?? '') + '-' + String(idx ?? 0)}
                            dataSource={bomProcessLines}
                            columns={bomProcessColumns}
                            locale={{ emptyText: '暂无工序明细（样本BOM未返回 process_lines）' }}
                            scroll={{ x: 1100 }}
                          />
                        </Space>
                      ),
                    },
                    {
                      key: 'base',
                      label: '物料组 / 工序组（基准清单）',
                      children: (
                        <Space direction="vertical" style={{ width: '100%' }} size={12}>
                          <Typography.Text strong>物料组（基准）</Typography.Text>
                          <Table
                            size="small"
                            pagination={false}
                            rowKey={(r: any, idx) => String(r?.material_ref_id ?? r?.material_code ?? idx)}
                            dataSource={detail.base_material_lines ?? []}
                            columns={[
                              { title: '编码', dataIndex: 'material_code', width: 120, render: (v) => v ?? '-' },
                              { title: '名称', dataIndex: 'material_name', width: 220, ellipsis: true, render: (v) => v ?? '-' },
                              { title: '基准数量', dataIndex: 'base_quantity', width: 90, render: (v) => (v == null ? '-' : String(v)) },
                              { title: '单位', dataIndex: 'unit_of_measure', width: 90, render: (v) => v ?? '-' },
                              { title: '计量方式', dataIndex: 'calculation_method', width: 90, render: (v) => String(v ?? '-') },
                              { title: '损耗%', dataIndex: 'loss_rate', width: 90, render: (v) => (v == null ? '-' : String(v)) },
                              { title: '单价', dataIndex: 'unit_cost', width: 90, render: (v) => formatMoney(String(v ?? '')) },
                              { title: '备注', dataIndex: 'notes', render: (v) => String(v ?? '-') },
                            ]}
                            scroll={{ x: 950 }}
                          />

                          <Typography.Text strong>工序组（基准）</Typography.Text>
                          <Table
                            size="small"
                            pagination={false}
                            rowKey={(r: any, idx) => String(r?.process_id ?? '') + '-' + String(idx ?? 0)}
                            dataSource={detail.base_process_lines ?? []}
                            columns={[
                              { title: '工序编码', dataIndex: 'process_code', width: 120, ellipsis: true },
                              { title: '工序名称', dataIndex: 'process_name', width: 220, ellipsis: true },
                              { title: '班组', dataIndex: 'team_name', width: 110, ellipsis: true },
                              { title: '计量', dataIndex: 'pricing_method', width: 90 },
                              { title: '分钟单价', dataIndex: 'rate_per_minute', width: 90, render: (v) => formatMoney(String(v ?? '')) },
                              { title: '计件单价', dataIndex: 'piece_rate', width: 90, render: (v) => formatMoney(String(v ?? '')) },
                              { title: '备注', dataIndex: 'notes', render: (v) => String(v ?? '-') },
                            ]}
                            scroll={{ x: 950 }}
                          />
                        </Space>
                      ),
                    },
                    {
                      key: 'deduction',
                      label: '扣库单',
                      children: (
                        <Space direction="vertical" style={{ width: '100%' }} size={12}>
                          <Alert
                            type="info"
                            showIcon
                            message="扣库单口径"
                            description="优先展示该样本发货行“落库扣库单”（更适合对账）；若没有落库数据，也可参考样本BOM trace.inventory。"
                          />
                          <Typography.Text strong>扣库单（落库）</Typography.Text>
                          <Table
                            size="small"
                            pagination={false}
                            rowKey={(r: any, idx) => String(r?.material_code ?? idx)}
                            dataSource={detail.persisted_deductions ?? []}
                            columns={deductionColumns}
                            locale={{ emptyText: '暂无落库扣库单（可能是历史批次/未执行扣库）' }}
                            scroll={{ x: 650 }}
                          />

                          <Typography.Text strong>扣库单（trace）</Typography.Text>
                          <Table
                            size="small"
                            pagination={false}
                            rowKey={(r: any, idx) => String(r?.material_code ?? idx)}
                            dataSource={(traceInventoryLines ?? []).map((r: any) => ({
                              ...r,
                              sources: Array.isArray(r?.sources) ? r.sources.length : r?.sources,
                            }))}
                            columns={deductionColumns}
                            locale={{ emptyText: '暂无 trace 扣库单（请先确保样本BOM生成成功）' }}
                            scroll={{ x: 650 }}
                          />
                        </Space>
                      ),
                    },
                  ]}
                />
              </>
            ) : (
              <Alert type="info" showIcon message="请从左侧点击一个模型" />
            )}
          </Card>
        </Col>
      </Row>
    </div>
  )
}

export default ProfitInsightsPage

