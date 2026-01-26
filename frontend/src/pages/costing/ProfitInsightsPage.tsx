import { Alert, Button, Card, DatePicker, Descriptions, Divider, Form, Row, Col, Select, Space, Table, Tabs, Tag, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import dayjs from 'dayjs'
import { useMemo, useState } from 'react'

import { fetchModelInsightsDetail, fetchModelInsightsSummary } from '@/services/planner'
import type {
  ModelInsightsDetailResponse,
  ModelInsightsSummaryItem,
  ModelInsightsSummaryResponse,
} from '@/types/planner'

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
  const [selectedModelCode, setSelectedModelCode] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const summaryColumns = useMemo<ColumnsType<ModelInsightsSummaryItem>>(
    () => [
      { title: '店铺', dataIndex: 'channel', key: 'channel', width: 140 },
      { title: '模型编码', dataIndex: 'model_code', key: 'model_code', width: 160 },
      { title: '模型名称', dataIndex: 'model_name', key: 'model_name', width: 200, ellipsis: true },
      {
        title: '主版本',
        key: 'top_version',
        width: 200,
        ellipsis: true,
        render: (_, r) => {
          const label = String(r.top_version_label ?? '').trim()
          const kind = String(r.top_version_kind ?? '').trim()
          const status = String(r.top_version_status ?? '').trim()
          const main = [label, [kind, status].filter(Boolean).join('/')].filter(Boolean).join(' ')
          const cnt = Number(r.version_count ?? 0)
          if (!main) return '-'
          return cnt > 1 ? `${main}（${cnt} 个版本）` : main
        },
      },
      { title: '发货数量', dataIndex: 'shipped_qty', key: 'shipped_qty', width: 100, render: formatQty },
      { title: '销售额', dataIndex: 'revenue_amount', key: 'revenue_amount', width: 110, render: formatMoney },
      { title: '物料成本', dataIndex: 'cost_material_amount', key: 'cost_material_amount', width: 110, render: formatMoney },
      { title: '人工成本', dataIndex: 'cost_process_amount', key: 'cost_process_amount', width: 110, render: formatMoney },
      { title: '制造费用', dataIndex: 'cost_overhead_amount', key: 'cost_overhead_amount', width: 110, render: formatMoney },
      { title: '成本', dataIndex: 'cost_amount', key: 'cost_amount', width: 110, render: formatMoney },
      { title: '毛利', dataIndex: 'gross_profit', key: 'gross_profit', width: 110, render: formatMoney },
      { title: '毛利率', dataIndex: 'gross_margin', key: 'gross_margin', width: 100, render: formatPercent },
      { title: '退款金额', dataIndex: 'refund_amount', key: 'refund_amount', width: 110, render: formatMoney },
      { title: '净利润', dataIndex: 'net_profit', key: 'net_profit', width: 110, render: formatMoney },
      { title: '净利率', dataIndex: 'net_margin', key: 'net_margin', width: 100, render: formatPercent },
    ],
    [],
  )

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
              rowKey={(r) => `${r.channel ?? ''}-${r.model_id}`}
              size="small"
              loading={loadingSummary}
              columns={summaryColumns}
              dataSource={summary?.items ?? []}
              pagination={{ pageSize: 20, showSizeChanger: true }}
              scroll={{ x: 1500 }}
              onRow={(record) => ({
                onClick: async () => {
                  const code = String(record.model_code || '').trim()
                  if (!code) return
                  setSelectedModelCode(code)
                  await loadDetail(code)
                },
              })}
              rowClassName={(r) => (String(r.model_code || '') === String(selectedModelCode || '') ? 'ant-table-row-selected' : '')}
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

                <Descriptions bordered size="small" column={2} style={{ marginBottom: 12 }}>
                  <Descriptions.Item label="样本发货时间">{detail.sample_completed_at ?? '-'}</Descriptions.Item>
                  <Descriptions.Item label="样本货品条码">{detail.sample_sku_code ?? '-'}</Descriptions.Item>
                  <Descriptions.Item label="样本交易规格" span={2}>
                    <Typography.Text>{detail.sample_spec_text ?? '-'}</Typography.Text>
                  </Descriptions.Item>
                </Descriptions>

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
                        render: (_: any, r: any) => (
                          <Space size={8}>
                            <Typography.Text strong>{String(r.version_label ?? String(r.version_id).slice(0, 8))}</Typography.Text>
                            {r.version_status ? (
                              <Tag color={String(r.version_status) === 'published' ? 'green' : 'orange'}>{String(r.version_status)}</Tag>
                            ) : null}
                            {r.version_kind ? <Tag>{String(r.version_kind)}</Tag> : null}
                          </Space>
                        ),
                      },
                      { title: '发货数量', dataIndex: 'shipped_qty', width: 100, render: formatQty },
                      { title: '销售额', dataIndex: 'revenue_amount', width: 110, render: formatMoney },
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
                    scroll={{ x: 900 }}
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

