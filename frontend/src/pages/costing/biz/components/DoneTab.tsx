import {
  Alert,
  Button,
  Card,
  DatePicker,
  Input,
  message,
  Modal,
  Space,
  Switch,
  Table,
  Tag,
  Tooltip,
  Typography,
} from 'antd'
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table'
import dayjs, { Dayjs } from 'dayjs'
import { useMemo, useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'

import { ShopSpecCodeCell } from '@/components/common/ShopSpecCodeCell'
import {
  fetchShipmentLines,
  resolveSkuMasterSuspectMisbindByBarcode,
} from '@/services/planner'
import type { ShipmentLineListItem } from '@/types/planner'
import { formatBeijingTime } from '@/utils/beijingTime'

const { Text } = Typography
const { RangePicker } = DatePicker

const DEFAULT_PAGE_SIZE = 20

const formatMoney = (v?: string | number | null): string => {
  if (v === null || v === undefined || v === '') return '-'
  const n = typeof v === 'string' ? Number(v) : v
  if (!Number.isFinite(n)) return String(v)
  return `¥${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

/**
 * 「📦 业务管理 > 🚚 发货管理 > ✅ 已完成」Tab
 *
 * 展示已绑定模型 + 已出 BOM 快照（或老模式 ShipmentCostingResult）的发货行,
 * 包括两类:
 *   1. 系统通过「⚡ 一键自动绑定」自动关联的(待处理 → 已完成)
 *   2. 上架员手动「✅ 选模型」处理过的
 *
 * 业务上架员视角(对照老的 /costing/shipments 财务台账页):
 *   - 财务台账关心: 利润分布 / 毛利异常 / 成本拆分(20+ 列, 看历史)
 *   - 本 Tab 关心: 我处理过的发货行有没有翻车的迹象(疑似绑错 / 尺寸异常 / 需重建快照)
 *
 * 默认按"发货时间"倒序拉近 30 天。提供「只看异常」开关让上架员
 * 一秒钟看出今天哪几条需要回头检查。
 *
 * 行级"操作"目前只提供"看 BOM 详情"(跳老台账页用 SKU 过滤);
 * 不提供"重新绑定/重算快照",因为:
 *   - 这些是高风险动作,业务派不应该误点;
 *   - 工程师/运维如需重算请用 /costing/shipments/ops 作业中心。
 */
export default function DoneTab() {
  const navigate = useNavigate()

  // PERF: list_shipment_lines status=processed 当前在 30 天窗口下要 ~25s
  // (root cause: 多个 scalar_subquery + count, 见 known_issues.md Issue 31).
  // 默认收窄到 7 天 (~2s)。用户可手动扩大, 由 banner 给出预期。
  const [dateRange, setDateRange] = useState<[Dayjs, Dayjs]>(() => [
    dayjs().subtract(7, 'day').startOf('day'),
    dayjs().endOf('day'),
  ])
  const [skuKeyword, setSkuKeyword] = useState<string>('')
  const [channelKeyword, setChannelKeyword] = useState<string>('')
  const [specKeyword, setSpecKeyword] = useState<string>('')
  const [boundModelCode, setBoundModelCode] = useState<string>('')
  const [onlyAnomaly, setOnlyAnomaly] = useState<boolean>(false)
  const [onlyNeedRebuild, setOnlyNeedRebuild] = useState<boolean>(false)
  const [page, setPage] = useState<number>(1)
  const [pageSize, setPageSize] = useState<number>(DEFAULT_PAGE_SIZE)

  const queryParams = useMemo(
    () => ({
      page,
      page_size: pageSize,
      start: dateRange[0].toISOString(),
      end: dateRange[1].toISOString(),
      status: 'processed' as const,
      sku_code: skuKeyword.trim() || undefined,
      channel: channelKeyword.trim() || undefined,
      spec_text: specKeyword.trim() || undefined,
      bound_model_code: boundModelCode.trim() || undefined,
      suspected_mismatch: onlyAnomaly ? true : undefined,
      need_rebuild_snapshot: onlyNeedRebuild ? true : undefined,
      include_issue_hints: true,
    }),
    [
      page,
      pageSize,
      dateRange,
      skuKeyword,
      channelKeyword,
      specKeyword,
      boundModelCode,
      onlyAnomaly,
      onlyNeedRebuild,
    ],
  )

  const listQuery = useQuery({
    queryKey: ['biz-shipments-done', queryParams],
    queryFn: () => fetchShipmentLines(queryParams),
    placeholderData: keepPreviousData,
    staleTime: 10_000,
  })

  const items = listQuery.data?.items ?? []
  const total = listQuery.data?.total ?? 0

  const dateRangeDays = useMemo(() => {
    return Math.max(1, dateRange[1].diff(dateRange[0], 'day') + 1)
  }, [dateRange])

  // Lightweight client-side aggregates for the banner — not authoritative
  // (only over current page), but a useful at-a-glance signal.
  const anomalyOnPage = useMemo(() => {
    let mismatch = 0
    let size = 0
    let rebuild = 0
    for (const r of items) {
      if (r.suspected_mismatch) mismatch += 1
      if (r.suspected_size_anomaly) size += 1
      if (r.needs_rebuild_snapshot) rebuild += 1
    }
    return { mismatch, size, rebuild }
  }, [items])

  const columns: ColumnsType<ShipmentLineListItem> = [
    {
      title: '发货时间',
      dataIndex: 'completed_at',
      key: 'completed_at',
      width: 140,
      render: (v?: string | null) => {
        return v ? formatBeijingTime(v, 'MM-DD HH:mm') : <Text type="secondary">-</Text>
      },
    },
    {
      title: '店铺',
      dataIndex: 'channel',
      key: 'channel',
      width: 110,
      render: (v?: string | null) => v || <Text type="secondary">-</Text>,
    },
    {
      title: 'SKU',
      dataIndex: 'sku_code',
      key: 'sku_code',
      width: 140,
      render: (v?: string | null) =>
        v ? (
          <Text copyable={{ text: v }} style={{ fontFamily: 'monospace', fontSize: 12 }}>
            {v}
          </Text>
        ) : (
          <Text type="secondary">-</Text>
        ),
    },
    {
      // 商家编码 = 网店端的"商家编码 / 商家货号"。吉客云 raw_row.detail.tradeGoodsno；老 Excel raw_row.商家编码。
      // 视觉分级（共用 ShopSpecCodeCell）：可自动匹配 / 平台默认ID / 不规范 / 未同步，运营一眼可判。
      title: '商家编码',
      dataIndex: 'shop_spec_code',
      key: 'shop_spec_code',
      width: 220,
      render: (v?: string | null) => <ShopSpecCodeCell value={v ?? null} />,
    },
    {
      title: '绑定模型',
      key: 'bound_model',
      width: 220,
      render: (_: unknown, row: ShipmentLineListItem) => {
        if (!row.bound_model_code) return <Text type="secondary">-</Text>
        // 有 bound_variant_label 时优先展示具体变体（如 "麻感冰丝(KB8-001)"）；
        // 兜底（按模型基础线绑定）回退到 bound_model_name。
        const variantLabel = (row.bound_variant_label || '').trim()
        return (
          <Space direction="vertical" size={2}>
            <Tag color="blue">{row.bound_model_code}</Tag>
            {variantLabel ? (
              <Tag color="cyan" style={{ marginInlineEnd: 0 }}>
                {variantLabel}
              </Tag>
            ) : row.bound_model_name ? (
              <Text style={{ fontSize: 12 }}>{row.bound_model_name}</Text>
            ) : null}
            {row.bound_version_label ? (
              <Text type="secondary" style={{ fontSize: 11 }}>
                {row.bound_version_label}
              </Text>
            ) : null}
          </Space>
        )
      },
    },
    {
      title: '规格文本',
      dataIndex: 'spec_text',
      key: 'spec_text',
      ellipsis: { showTitle: true },
      render: (v?: string | null) => (
        <Tooltip title={v || ''}>
          <Text style={{ fontSize: 12 }}>{v || <Text type="secondary">-</Text>}</Text>
        </Tooltip>
      ),
    },
    {
      title: '成本',
      dataIndex: 'cost_total',
      key: 'cost_total',
      width: 110,
      align: 'right',
      render: (v?: string | null) => (
        <Text style={{ fontFamily: 'monospace' }}>{formatMoney(v)}</Text>
      ),
    },
    {
      title: '状态',
      key: 'flags',
      width: 220,
      render: (_: unknown, row: ShipmentLineListItem) => {
        const tags: React.ReactNode[] = []
        if (row.processed_source === 'bom_snapshot') {
          tags.push(
            <Tag key="src" color="geekblue">
              BOM 快照{row.mode === '2026' ? ' · 新模式' : ''}
            </Tag>,
          )
        } else if (row.processed_source === 'costing_result') {
          tags.push(
            <Tag key="src" color="default">
              老 costing
            </Tag>,
          )
        }
        if (row.needs_rebuild_snapshot) {
          tags.push(
            <Tooltip key="rebuild_t" title="模型版本已更新, 当前快照过时, 建议重算">
              <Tag color="orange">需重建</Tag>
            </Tooltip>,
          )
        }
        if (row.suspected_mismatch) {
          tags.push(
            <Tooltip
              key="mis_t"
              title={(row.mismatch_warnings || []).join('\n') || '系统检测到规格关键字与绑定模型品类有出入'}
            >
              <Tag color="red">疑似绑错</Tag>
            </Tooltip>,
          )
        }
        if (row.suspected_size_anomaly) {
          tags.push(
            <Tooltip key="size_t" title={row.size_anomaly_detail || '解析尺寸与计价尺寸/面积差异较大'}>
              <Tag color="volcano">尺寸异常</Tag>
            </Tooltip>,
          )
        }
        if (row.sku_data_quality_status === 'spu_attribute_conflict') {
          tags.push(
            <Tooltip
              key="dq_t"
              title={
                <span>
                  该 SKU 主档被标记为「SPU 属性冲突」——同一条码历史发货跨多个不相关品类。
                  <br />
                  本行成本仍按当前绑定计算，但<b>自动绑定结果不可信</b>，建议去 SKU 主档详情核对绑定与变体选择。
                </span>
              }
            >
              <Tag color="default">SPU 错配</Tag>
            </Tooltip>,
          )
        }
        if (!tags.length) {
          tags.push(
            <Tag key="ok" color="green">
              正常
            </Tag>,
          )
        }
        return <Space wrap size={4}>{tags}</Space>
      },
    },
    {
      title: '操作',
      key: 'actions',
      width: 220,
      fixed: 'right',
      render: (_: unknown, row: ShipmentLineListItem) => (
        <Space size={4} wrap>
          <Tooltip title="去发货台账查看 BOM 物料 / 成本拆分 / 利润">
            <Button
              size="small"
              onClick={() => {
                const sku = String(row.sku_code || '').trim()
                if (!sku) return
                const qp = new URLSearchParams()
                qp.set('sku_code', sku)
                qp.set('tab', 'processed')
                navigate(`/costing/shipments?${qp.toString()}`)
              }}
              disabled={!row.sku_code}
            >
              详情
            </Button>
          </Tooltip>
          {row.suspected_mismatch ? (
            <>
              <Tooltip title="跳到 SKU 主档详情，按 SKU 编码定位，重新选择正确的模型/变体">
                <Button
                  size="small"
                  type="primary"
                  onClick={() => {
                    const sku = String(row.sku_code || '').trim()
                    if (!sku) return
                    navigate(`/costing/sku-master?search=${encodeURIComponent(sku)}`)
                  }}
                  disabled={!row.sku_code}
                >
                  重新绑定
                </Button>
              </Tooltip>
              <Tooltip title='如果你确认这条绑定是对的（例如算法误报），可标记忽略。该 SKU 的所有发货行都将不再触发"疑似绑错"提示，直到下次绑定变更。'>
                <Button
                  size="small"
                  onClick={() => {
                    const sku = String(row.sku_code || '').trim()
                    if (!sku) return
                    Modal.confirm({
                      title: '忽略「疑似绑错」提示？',
                      content: (
                        <div style={{ lineHeight: 1.7 }}>
                          <p>
                            SKU <Text code>{sku}</Text> 的<b>所有历史/未来发货行</b>都将不再显示
                            「疑似绑错」红色 Tag，也不再计入「只看疑似绑错」总数。
                          </p>
                          <p style={{ color: '#999' }}>
                            一旦绑定变更（手工 / 自动重绑），忽略状态会自动撤销，重新走判定。
                          </p>
                        </div>
                      ),
                      okText: '确认忽略',
                      cancelText: '取消',
                      onOk: async () => {
                        try {
                          await resolveSkuMasterSuspectMisbindByBarcode(sku)
                          message.success('已忽略，列表将刷新')
                          listQuery.refetch()
                        } catch (e: any) {
                          message.error(`忽略失败：${e?.response?.data?.detail || e?.message || e}`)
                        }
                      },
                    })
                  }}
                  disabled={!row.sku_code}
                >
                  忽略提示
                </Button>
              </Tooltip>
            </>
          ) : null}
        </Space>
      ),
    },
  ]

  const pagination: TablePaginationConfig = {
    current: page,
    pageSize,
    total,
    showSizeChanger: true,
    pageSizeOptions: ['20', '50', '100'],
    showTotal: (t) => `共 ${t} 条`,
    onChange: (p, ps) => {
      setPage(p)
      if (ps !== pageSize) setPageSize(ps)
    },
  }

  return (
    <div>
      <Card size="small" style={{ marginBottom: 12 }}>
        <Space wrap size={12} style={{ width: '100%' }}>
          <Space>
            <Text type="secondary">日期:</Text>
            <RangePicker
              value={dateRange}
              onChange={(v) => {
                if (v && v[0] && v[1]) {
                  setDateRange([v[0].startOf('day'), v[1].endOf('day')])
                  setPage(1)
                }
              }}
              allowClear={false}
            />
          </Space>
          <Space>
            <Text type="secondary">店铺:</Text>
            <Input
              placeholder="店铺关键字"
              value={channelKeyword}
              onChange={(e) => setChannelKeyword(e.target.value)}
              onPressEnter={() => setPage(1)}
              style={{ width: 140 }}
              allowClear
            />
          </Space>
          <Space>
            <Text type="secondary">SKU:</Text>
            <Input
              placeholder="SKU 关键字"
              value={skuKeyword}
              onChange={(e) => setSkuKeyword(e.target.value)}
              onPressEnter={() => setPage(1)}
              style={{ width: 160 }}
              allowClear
            />
          </Space>
          <Space>
            <Text type="secondary">规格:</Text>
            <Input
              placeholder="规格关键字"
              value={specKeyword}
              onChange={(e) => setSpecKeyword(e.target.value)}
              onPressEnter={() => setPage(1)}
              style={{ width: 160 }}
              allowClear
            />
          </Space>
          <Space>
            <Text type="secondary">模型代码:</Text>
            <Input
              placeholder="如 F6A / OZU"
              value={boundModelCode}
              onChange={(e) => setBoundModelCode(e.target.value)}
              onPressEnter={() => setPage(1)}
              style={{ width: 130 }}
              allowClear
            />
          </Space>
          <Space>
            <Text type="secondary">只看疑似绑错:</Text>
            <Switch
              checked={onlyAnomaly}
              onChange={(v) => {
                setOnlyAnomaly(v)
                setPage(1)
              }}
            />
          </Space>
          <Space>
            <Text type="secondary">只看需重建:</Text>
            <Switch
              checked={onlyNeedRebuild}
              onChange={(v) => {
                setOnlyNeedRebuild(v)
                setPage(1)
              }}
            />
          </Space>
          <Button onClick={() => listQuery.refetch()} loading={listQuery.isFetching}>
            刷新
          </Button>
        </Space>
      </Card>

      {listQuery.error ? (
        <Alert
          type="error"
          showIcon
          style={{ marginBottom: 12 }}
          message="加载失败"
          description={String((listQuery.error as any)?.message || listQuery.error)}
        />
      ) : null}

      {dateRangeDays > 14 ? (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 12 }}
          message={`你选了 ${dateRangeDays} 天的范围, 当前接口在大窗口下加载较慢 (~10-30 秒)`}
          description="如只是想看最近几天的处理结果, 建议把日期收窄到 7 天内 (~2 秒); 需要历史数据可去「发货台账」(/costing/shipments) 查看, 那边专为多列报表优化。后端正在排期彻底优化此接口 (见 Issue 31)。"
        />
      ) : null}

      {/* 异常摘要 banner — 仅基于"当前页", 让上架员一眼看到今天有没有翻车迹象 */}
      {!listQuery.isLoading && items.length > 0 ? (
        <Alert
          type={
            anomalyOnPage.mismatch + anomalyOnPage.size + anomalyOnPage.rebuild === 0
              ? 'success'
              : 'warning'
          }
          showIcon
          style={{ marginBottom: 12 }}
          message={
            <Space wrap size={8}>
              <Text strong>本页 {items.length} 条 (共 {total} 条):</Text>
              <Tag color={anomalyOnPage.mismatch ? 'red' : 'default'}>
                疑似绑错 {anomalyOnPage.mismatch}
              </Tag>
              <Tag color={anomalyOnPage.size ? 'volcano' : 'default'}>
                尺寸异常 {anomalyOnPage.size}
              </Tag>
              <Tag color={anomalyOnPage.rebuild ? 'orange' : 'default'}>
                需重建 {anomalyOnPage.rebuild}
              </Tag>
            </Space>
          }
          description={
            anomalyOnPage.mismatch + anomalyOnPage.size + anomalyOnPage.rebuild > 0
              ? (
                <span>
                  <b>「已处理」仅表示快照已生成</b>，不代表绑定一定正确——
                  <Text type="danger">疑似绑错</Text> 的行成本可能算错，请用行级「重新绑定」按钮改绑定，
                  或确认无误后点「忽略提示」消除噪音。
                  <br />
                  打开「只看疑似绑错 / 只看需重建」开关可集中处理；重算快照请去「⚙ 系统运维 → 发货作业中心」。
                </span>
              )
              : '本页所有行系统未检测到异常迹象。'
          }
        />
      ) : null}

      <Card size="small">
        <div style={{ marginBottom: 8 }}>
          <Space wrap>
            <Tag color="green">已完成 {total} 条</Tag>
            <Text type="secondary" style={{ fontSize: 12 }}>
              提示: 已完成 = 绑定了模型 + 出过 BOM 快照(或老 costing 结果)。同 SKU 的未来发货会自动用同一模型算价。
            </Text>
          </Space>
        </div>
        <Table<ShipmentLineListItem>
          rowKey="id"
          size="small"
          loading={listQuery.isLoading}
          dataSource={items}
          columns={columns}
          pagination={pagination}
          scroll={{ x: 1800 }}
        />
      </Card>
    </div>
  )
}
