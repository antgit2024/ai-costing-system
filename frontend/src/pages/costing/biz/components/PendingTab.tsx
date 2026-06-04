import {
  Alert,
  Button,
  Card,
  DatePicker,
  Drawer,
  Input,
  message,
  Modal,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
} from 'antd'
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table'
import dayjs, { Dayjs } from 'dayjs'
import { useMemo, useState } from 'react'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'

import {
  autoResolvePendingShipmentLinesExecute,
  autoResolvePendingShipmentLinesPreview,
  bulkResolveShipmentLines,
  fetchShipmentLines,
  fetchShipmentLinesRecentStats,
  regenerateBoundPendingSnapshots,
} from '@/services/planner'
import type {
  ShipmentLineListItem,
  ShipmentLinesAutoResolveCandidate,
} from '@/types/planner'
import { ShopSpecCodeCell } from '@/components/common/ShopSpecCodeCell'
import { formatBeijingRelativeTime, formatBeijingTime } from '@/utils/beijingTime'

import LineResolveActions from './LineResolveActions'

const { Text } = Typography
const { RangePicker } = DatePicker

const DEFAULT_PAGE_SIZE = 20

/**
 * 「📦 业务管理 → 🚚 发货管理 → 🔴 待处理」Tab
 *
 * v0.3 设计要点(对照 v0.2 反馈):
 *   1. 顶部「同步状态条」常驻 - 显示上次同步时间 + 24h 新进 N 条 (拆源) + 跳同步管理
 *      → 让上架员"跟着同步节奏走", 而不是"看见 13k 条积压懵掉"
 *   2.「⚡ 一键自动绑定」从 banner 改成筛选行右侧常驻按钮
 *      → 进入页面不再被动扫描 5,779 个 SKU; 用户主动点才触发
 *      → 处理完按钮也不消失, 新建模型后还能再点
 *   3. 表格加 rowSelection + 浮出批量工具栏
 *      → 100+ 条/天的真实场景不能强迫人逐条点
 *   4. 操作列 fixed:right + 行内 4 按钮右靠齐
 *
 * 接口策略(2026-05-07 终态):
 *   - 行级单条: services/planner.ts/resolveShipmentLine (Issue 29 后内部=单次 POST)
 *   - 批量: services/planner.ts/bulkResolveShipmentLines (一次 POST, 后端 best-effort 处理)
 */

export default function PendingTab() {
  const queryClient = useQueryClient()
  const navigate = useNavigate()

  const [dateRange, setDateRange] = useState<[Dayjs, Dayjs]>(() => [
    dayjs().subtract(30, 'day').startOf('day'),
    dayjs().endOf('day'),
  ])
  const [skuKeyword, setSkuKeyword] = useState<string>('')
  const [channelKeyword, setChannelKeyword] = useState<string>('')
  const [specKeyword, setSpecKeyword] = useState<string>('')
  const [page, setPage] = useState<number>(1)
  const [pageSize, setPageSize] = useState<number>(DEFAULT_PAGE_SIZE)
  const [operatorId, setOperatorId] = useState<string>('')

  // 行选中(批量操作用)
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([])
  const [bulkRunning, setBulkRunning] = useState<boolean>(false)

  // 自动绑定抽屉
  const [autoDrawerOpen, setAutoDrawerOpen] = useState<boolean>(false)
  const [autoCandidates, setAutoCandidates] = useState<ShipmentLinesAutoResolveCandidate[]>([])
  const [autoSelectedSkus, setAutoSelectedSkus] = useState<string[]>([])
  const [autoPreviewLoading, setAutoPreviewLoading] = useState<boolean>(false)

  const queryParams = useMemo(
    () => ({
      page,
      page_size: pageSize,
      start: dateRange[0].toISOString(),
      end: dateRange[1].toISOString(),
      status: 'pending' as const,
      sku_code: skuKeyword.trim() || undefined,
      channel: channelKeyword.trim() || undefined,
      spec_text: specKeyword.trim() || undefined,
      include_issue_hints: true,
    }),
    [page, pageSize, dateRange, skuKeyword, channelKeyword, specKeyword],
  )

  const listQuery = useQuery({
    queryKey: ['biz-shipments-pending', queryParams],
    queryFn: () => fetchShipmentLines(queryParams),
    placeholderData: keepPreviousData,
    staleTime: 10_000,
  })

  // 顶部同步状态条 — 永远拉最近 24h 状态(轻量, ~50ms)
  const recentStatsQuery = useQuery({
    queryKey: ['biz-shipments-pending', 'recent-stats'],
    queryFn: () => fetchShipmentLinesRecentStats({ hours: 24, latest_runs_limit: 3 }),
    staleTime: 30_000,
    refetchOnWindowFocus: false,
    retry: 0,
  })

  const autoResolveDays = useMemo(() => {
    const start = dateRange[0]
    const end = dateRange[1]
    const diff = Math.max(1, end.diff(start, 'day') + 1)
    return Math.min(diff, 365)
  }, [dateRange])

  const autoExecuteMutation = useMutation({
    mutationFn: (skuCodes: string[] | undefined) =>
      autoResolvePendingShipmentLinesExecute({
        days: autoResolveDays,
        limit: 1000,
        sku_codes: skuCodes,
        requested_by: operatorId.trim() || undefined,
      }),
    onSuccess: async (result) => {
      message.success(
        `自动绑定完成: 绑定 ${result.bound_skus_count} 个 SKU, 出快照 ${result.snapshots_created} 条, 解决异常 ${result.exceptions_resolved} 条`,
      )
      setAutoDrawerOpen(false)
      setAutoCandidates([])
      setAutoSelectedSkus([])
      await queryClient.invalidateQueries({ queryKey: ['biz-shipments-pending'] })
    },
    onError: (e: any) => {
      const detail = String(e?.response?.data?.detail ?? '').trim()
      message.error(detail || e?.message || '自动绑定执行失败')
    },
  })

  // 「🔁 回写快照」: 手动触发 sweep, 处理"已绑定但缺快照"的历史行
  // (绑定时 hook 已自动出快照, 这个按钮覆盖兜底场景: hook 失败 / 月底盘点)
  const regenerateSnapshotsMutation = useMutation({
    mutationFn: () => regenerateBoundPendingSnapshots({ lookback_days: 90, limit: 2000 }),
    onSuccess: async (result) => {
      const skipFail = result.failed > 0 ? `, 失败 ${result.failed} 条 (多为 SPEC_EMPTY, 需到异常队列处理)` : ''
      if (result.snapshots_created > 0) {
        message.success(
          `回写完成: 扫描 ${result.scanned} 条, 出快照 ${result.snapshots_created} 条${skipFail} (耗时 ${(result.duration_ms / 1000).toFixed(1)}s)`,
        )
      } else if (result.scanned === 0) {
        message.info('没有需要回写的行: 全部"已绑定+缺快照"的历史行已经处理完了')
      } else {
        message.warning(
          `扫描 ${result.scanned} 条但无新快照产出${skipFail}`,
        )
      }
      await queryClient.invalidateQueries({ queryKey: ['biz-shipments-pending'] })
    },
    onError: (e: any) => {
      const detail = String(e?.response?.data?.detail ?? '').trim()
      message.error(detail || e?.message || '回写快照失败')
    },
  })

  // 用户主动点「⚡ 自动绑定」按钮才触发 preview 扫描
  const handleOpenAutoDrawer = async () => {
    setAutoPreviewLoading(true)
    try {
      const data = await autoResolvePendingShipmentLinesPreview({
        days: autoResolveDays,
        limit: 1000,
      })
      const items = data.items || []
      if (items.length === 0) {
        const totalPending = data.total_pending_lines ?? 0
        Modal.info({
          title: '没找到可自动识别的 SKU',
          content: (
            <div>
              <p>
                已扫描最近 {data.scanned_days} 天的 <Text strong>{totalPending}</Text> 条待处理发货行,
                {' '}
                <Text strong>{data.unique_unbound_skus}</Text> 个未绑定 SKU。
              </p>
              <p>所有 SKU 的规格描述模糊或品类不在已发布模型库中, 需要人工判断模型。</p>
              <p>
                如果你刚<Text strong>新建了模型</Text>, 请重新点这个按钮再扫一次 (新模型的关键字会被纳入识别)。
              </p>
            </div>
          ),
        })
        return
      }
      setAutoCandidates(items)
      setAutoSelectedSkus(items.map((c) => c.sku_code))
      setAutoDrawerOpen(true)
    } catch (e: any) {
      const detail = String(e?.response?.data?.detail ?? e?.message ?? e ?? '加载失败')
      message.error(`自动识别扫描失败: ${detail}`)
    } finally {
      setAutoPreviewLoading(false)
    }
  }

  const handleAutoResolveSelected = () => {
    if (!autoSelectedSkus.length) {
      message.info('请先勾选要自动绑定的候选')
      return
    }
    Modal.confirm({
      title: `确认对勾选的 ${autoSelectedSkus.length} 个 SKU 执行自动绑定?`,
      content:
        '系统将给勾选的 SKU 按系统建议的模型自动绑定 + 立刻出快照。如要换模型, 请关闭此抽屉, 在表格里手动「✅ 选模型」。',
      okText: '开始执行',
      cancelText: '取消',
      onOk: () => autoExecuteMutation.mutateAsync(autoSelectedSkus),
    })
  }

  const items = listQuery.data?.items ?? []
  const total = listQuery.data?.total ?? 0

  const handleResolved = () => {
    void listQuery.refetch()
  }

  // 批量操作: 单次 POST /shipments/lines/bulk-resolve (Issue 29 follow-up).
  // 后端 best-effort 处理, 失败的不影响其他行 — UI 直接展示汇总, 失败行
  // 单击重试。
  const runBulk = async (
    type: 'defer_modeling' | 'mark_long_tail',
    confirmTitle: string,
    confirmContent: React.ReactNode,
  ) => {
    const targets = items.filter((it) => selectedRowKeys.includes(it.id))
    if (!targets.length) {
      message.info('请先勾选要处理的行')
      return
    }
    Modal.confirm({
      title: confirmTitle,
      content: confirmContent,
      okText: `开始执行 (${targets.length} 条)`,
      cancelText: '取消',
      okButtonProps: type === 'mark_long_tail' ? { danger: true } : undefined,
      onOk: async () => {
        setBulkRunning(true)
        const hide = message.loading(`正在批量处理 ${targets.length} 条...`, 0)
        try {
          const resp = await bulkResolveShipmentLines({
            items: targets.map((line) => ({
              shipment_line_id: line.id,
              action: type,
            })),
            operator_id: operatorId.trim() || undefined,
            note:
              type === 'defer_modeling'
                ? '发货管理-批量待建模'
                : '发货管理-批量标长尾',
          })
          hide()
          if (resp.failed === 0) {
            message.success(
              `批量完成: ${resp.succeeded} 条全部成功 (${resp.total_duration_ms} ms)`,
            )
          } else {
            const sample = resp.results.find((r) => !r.ok)?.error || ''
            message.warning(
              `批量完成: 成功 ${resp.succeeded}, 失败 ${resp.failed} — ${sample.slice(0, 80)}${sample.length > 80 ? '…' : ''}`,
            )
          }
          setSelectedRowKeys([])
          await queryClient.invalidateQueries({ queryKey: ['biz-shipments-pending'] })
        } catch (err: any) {
          hide()
          const detail = String(err?.response?.data?.detail || err?.message || err || 'unknown')
          message.error(`批量执行失败: ${detail}`)
        } finally {
          setBulkRunning(false)
        }
      },
    })
  }

  const handleBulkDeferModeling = () =>
    runBulk(
      'defer_modeling',
      `确认把勾选的 ${selectedRowKeys.length} 行加入「待建模」队列?`,
      <div>
        这些 SKU 会进入「⏸️ 处理中」Tab, 等模型上线后由系统自动绑定。
        <br />
        期间这些行从「待处理」消失, 不会重复出现在你视野中。
      </div>,
    )

  const handleBulkMarkLongTail = () =>
    runBulk(
      'mark_long_tail',
      `确认把勾选的 ${selectedRowKeys.length} 行标为「长尾」?`,
      <div>
        这些 SKU 销量很少, 系统不再为它们建模, 而是按"销售额 × 长尾兜底比例"自动估算成本。
        <br />
        高风险操作 — 标错了可在「🚫 长尾池」Tab 撤回。
      </div>,
    )

  const columns: ColumnsType<ShipmentLineListItem> = [
    {
      title: '发货时间',
      dataIndex: 'completed_at',
      key: 'completed_at',
      width: 130,
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
      // 商家编码 = 网店端"商家编码 / 商家货号"。吉客云 raw_row.detail.tradeGoodsno；老 Excel raw_row.商家编码。
      // 待处理 Tab 这一列尤其关键：「未同步」/「平台默认ID」往往就是无法自动绑定的根因，运营要一眼看出。
      title: '商家编码',
      dataIndex: 'shop_spec_code',
      key: 'shop_spec_code',
      width: 220,
      render: (v: string | null | undefined, record: ShipmentLineListItem) => (
        <ShopSpecCodeCell value={v ?? null} rawValue={record.shop_spec_code_raw ?? null} />
      ),
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
      title: '系统提示',
      dataIndex: 'unresolved_reason',
      key: 'unresolved_reason',
      width: 150,
      render: (reason?: string | null, row?: ShipmentLineListItem) => {
        const r = String(reason || '').toUpperCase()
        // 需要人工处理的状态
        if (r === 'SKU_NOT_BOUND')
          return (
            <Tooltip title="该 SKU 还没绑定任何商品模型, 请用「✅ 选模型」或顶部「⚡ 一键自动绑定」">
              <Tag color="red">🟥 无对应模型 (人工)</Tag>
            </Tooltip>
          )
        if (r === 'SPEC_EMPTY')
          return (
            <Tooltip title="发货行的规格文本为空, 系统无法解析尺寸/品类。请回 ERP 补规格, 或对该 SKU「🚫 标长尾」">
              <Tag color="orange">🟧 规格为空 (人工)</Tag>
            </Tooltip>
          )
        if (r === 'SPEC_PARSE_FAILED')
          return (
            <Tooltip title="规格文本不为空, 但解析不出尺寸。可能是描述格式特殊。处理建议: 改规格解析规则, 或「🚫 标长尾」">
              <Tag color="orange">🟧 规格解析失败 (人工)</Tag>
            </Tooltip>
          )
        if (r === 'MODEL_PENDING')
          return (
            <Tooltip title="该 SKU 已被标「⏸️ 待建模」, 等模型上线后系统会自动绑。已在「⏸️ 处理中」Tab 排队中。">
              <Tag color="blue">🟦 待建模 (排队中)</Tag>
            </Tooltip>
          )
        if (r === 'BOM_GENERATION_FAILED')
          return (
            <Tooltip title="模型已绑, 但出 BOM 快照时出错。系统会在 5-10 分钟后自动重试。如果连续多次失败请去「⚙ 系统运维 → 发货作业中心」看异常详情。">
              <Tag color="orange">🟧 出快照失败 (系统重试)</Tag>
            </Tooltip>
          )
        // 已绑定但无快照 — 由 shipment_import_worker 的 snapshot retry sweep
        // 自动补 (默认每 5 分钟扫一次最近 14 天 bound-no-snapshot 的 line)。
        if (row?.bound_model_code)
          return (
            <Tooltip title="模型已绑定 OK, 但成本快照还没出来。系统每 5 分钟扫一次, 自动补出快照, 一般 5-10 分钟内消失。不需要人工处理 — 急用可点右侧「重算」立刻触发。">
              <Tag color="gold">⏳ 等出快照 (5 分钟内自动)</Tag>
            </Tooltip>
          )
        return <Tag>{reason || '需人工判断'}</Tag>
      },
    },
    {
      title: '操作',
      key: 'actions',
      width: 380,
      align: 'right',
      fixed: 'right',
      render: (_: unknown, row: ShipmentLineListItem) => (
        <LineResolveActions line={row} operatorId={operatorId} onResolved={handleResolved} />
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

  // 同步状态条
  const renderSyncBar = () => {
    if (recentStatsQuery.isLoading) {
      return (
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 12 }}
          message="正在加载同步状态..."
        />
      )
    }
    if (recentStatsQuery.isError) {
      return (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 12 }}
          message="同步状态加载失败"
          action={
            <Button size="small" onClick={() => recentStatsQuery.refetch()}>
              重试
            </Button>
          }
        />
      )
    }
    const stats = recentStatsQuery.data
    if (!stats) return null
    const latestRun = stats.latest_runs[0]
    const newLines = stats.total_new_lines
    const sourceTags = stats.by_source_system.filter((b) => b.count > 0)
    const failedCount = stats.recent_failed_runs_count || 0
    const failedRun = stats.latest_failed_run || null
    return (
      <>
        {failedCount > 0 && (
          <Alert
            type="error"
            showIcon
            style={{ marginBottom: 8 }}
            message={
              <Space wrap size={8}>
                <Text strong>
                  ⚠ 最近 {stats.window_hours}h 内有 {failedCount} 次同步失败
                </Text>
                {failedRun?.started_at ? (
                  <Text type="secondary">
                    最近一次:{' '}
                    <Tooltip title={failedRun.started_at}>
                      <Text>{formatBeijingRelativeTime(failedRun.started_at)}</Text>
                    </Tooltip>
                  </Text>
                ) : null}
                {failedRun?.triggered_by ? (
                  <Text type="secondary">触发: {failedRun.triggered_by}</Text>
                ) : null}
                {failedRun?.error_message ? (
                  <Tooltip title={failedRun.error_message}>
                    <Text type="secondary" style={{ maxWidth: 360, display: 'inline-block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', verticalAlign: 'middle' }}>
                      {failedRun.error_message}
                    </Text>
                  </Tooltip>
                ) : null}
              </Space>
            }
            action={
              <Button size="small" danger onClick={() => navigate('/costing/integrations')}>
                → 同步管理排错
              </Button>
            }
          />
        )}
        <Alert
        type={newLines > 0 ? 'success' : 'info'}
        showIcon
        style={{ marginBottom: 12 }}
        message={
          <Space wrap size={10}>
            {latestRun ? (
              <span>
                <Text strong>上次同步:</Text>{' '}
                <Tooltip title={latestRun.finished_at || latestRun.started_at}>
                  <Text>{formatBeijingRelativeTime(latestRun.finished_at || latestRun.started_at)}</Text>
                </Tooltip>{' '}
                {latestRun.status === 'succeeded' ? (
                  <Tag color="green">成功</Tag>
                ) : latestRun.status === 'failed' ? (
                  <Tooltip title={latestRun.error_message || ''}>
                    <Tag color="red">失败</Tag>
                  </Tooltip>
                ) : (
                  <Tag>{latestRun.status}</Tag>
                )}
              </span>
            ) : (
              <Text type="secondary">暂无同步记录</Text>
            )}
            <Text type="secondary">|</Text>
            <span>
              <Text strong>24h 新进:</Text>{' '}
              <Text strong style={{ fontSize: 14, color: newLines > 0 ? '#52c41a' : '#999' }}>
                {newLines}
              </Text>{' '}
              条
              {sourceTags.length > 0 ? (
                <span style={{ marginLeft: 6 }}>
                  ({sourceTags.map((s) => `${s.source_system || '未知'} ${s.count}`).join(' · ')})
                </span>
              ) : null}
            </span>
            <Text type="secondary">|</Text>
            <Text>
              <Text strong>当前待处理总数:</Text> <Tag color="red">{total}</Tag> 条
            </Text>
          </Space>
        }
        action={
          <Space>
            <Tooltip title="扫描当前日期范围内未绑定的 SKU, 找出能按「模型代码提示 / 关键字」自动识别的, 一键完成绑定 + 出快照。新建完模型后再点一次, 新模型也会被纳入识别。">
              <Button
                size="small"
                type="primary"
                loading={autoPreviewLoading || autoExecuteMutation.isPending}
                onClick={handleOpenAutoDrawer}
              >
                ⚡ 一键自动绑定
              </Button>
            </Tooltip>
            <Button size="small" onClick={() => navigate('/costing/integrations')}>
              → 同步管理
            </Button>
            <Button size="small" onClick={() => recentStatsQuery.refetch()}>
              刷新状态
            </Button>
            <Tooltip title="回写最近 90 天「已绑定但缺快照」的历史行。绑定 SKU 时会自动出快照, 这个按钮覆盖少数兜底场景 (hook 失败 / 月底盘点)。">
              <Button
                size="small"
                loading={regenerateSnapshotsMutation.isPending}
                onClick={() => regenerateSnapshotsMutation.mutate()}
              >
                🔁 回写快照
              </Button>
            </Tooltip>
          </Space>
        }
      />
      </>
    )
  }

  return (
    <div>
      {/* 1. 同步状态条 - 常驻 */}
      {renderSyncBar()}

      {/* 2. 筛选行(自动绑定按钮已并入顶部同步状态条) */}
      <Card size="small" style={{ marginBottom: 12 }}>
        <Space wrap size={8}>
          <Space size={4}>
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
          <Space size={4}>
            <Text type="secondary">店铺:</Text>
            <Input
              placeholder="店铺关键字"
              value={channelKeyword}
              onChange={(e) => setChannelKeyword(e.target.value)}
              onPressEnter={() => setPage(1)}
              style={{ width: 130 }}
              allowClear
            />
          </Space>
          <Space size={4}>
            <Text type="secondary">SKU:</Text>
            <Input
              placeholder="SKU 关键字"
              value={skuKeyword}
              onChange={(e) => setSkuKeyword(e.target.value)}
              onPressEnter={() => setPage(1)}
              style={{ width: 150 }}
              allowClear
            />
          </Space>
          <Space size={4}>
            <Text type="secondary">规格:</Text>
            <Input
              placeholder="规格关键字"
              value={specKeyword}
              onChange={(e) => setSpecKeyword(e.target.value)}
              onPressEnter={() => setPage(1)}
              style={{ width: 150 }}
              allowClear
            />
          </Space>
          <Space size={4}>
            <Text type="secondary">操作员:</Text>
            <Input
              placeholder="工号(审计用)"
              value={operatorId}
              onChange={(e) => setOperatorId(e.target.value)}
              style={{ width: 110 }}
              allowClear
            />
          </Space>
          <Button onClick={() => listQuery.refetch()} loading={listQuery.isFetching}>
            🔄 刷新
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

      {/* 3. 批量工具栏 - 仅选中后浮出 */}
      {selectedRowKeys.length > 0 ? (
        <Alert
          type="info"
          showIcon={false}
          style={{ marginBottom: 12, background: '#262626', borderColor: '#434343' }}
          message={
            <Space wrap size={8}>
              <Text strong>
                已勾选 <Text style={{ color: '#1677ff' }}>{selectedRowKeys.length}</Text> 行
              </Text>
              <Button
                size="small"
                onClick={handleBulkDeferModeling}
                loading={bulkRunning}
                disabled={bulkRunning}
              >
                ⏸️ 批量待建模
              </Button>
              <Button
                size="small"
                danger
                onClick={handleBulkMarkLongTail}
                loading={bulkRunning}
                disabled={bulkRunning}
              >
                🚫 批量标长尾
              </Button>
              <Tooltip title="批量按系统建议绑定: 请用页面顶部的「⚡ 一键自动绑定」按钮 (会扫描所有可识别 SKU)">
                <Button size="small" type="primary" disabled>
                  ✅ 批量按建议绑定 (用顶部按钮)
                </Button>
              </Tooltip>
              <Button size="small" type="text" onClick={() => setSelectedRowKeys([])}>
                清除选择
              </Button>
            </Space>
          }
        />
      ) : null}

      {/* 4. 表格 */}
      <Card size="small">
        <Table<ShipmentLineListItem>
          rowKey="id"
          size="small"
          loading={listQuery.isLoading}
          dataSource={items}
          columns={columns}
          pagination={pagination}
          scroll={{ x: 1200 }}
          rowSelection={{
            selectedRowKeys,
            onChange: setSelectedRowKeys,
            preserveSelectedRowKeys: false,
          }}
        />
      </Card>

      {/* 候选清单抽屉 - 用户点「⚡ 一键自动绑定」后弹出 */}
      <Drawer
        title="⚡ 自动识别候选清单"
        placement="right"
        width={920}
        open={autoDrawerOpen}
        onClose={() => setAutoDrawerOpen(false)}
        extra={
          <Space>
            <Button onClick={() => setAutoDrawerOpen(false)}>取消</Button>
            <Button
              type="primary"
              loading={autoExecuteMutation.isPending}
              disabled={!autoSelectedSkus.length}
              onClick={handleAutoResolveSelected}
            >
              对勾选 {autoSelectedSkus.length} 个 SKU 执行绑定
            </Button>
          </Space>
        }
      >
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 12 }}
          message={`系统找到 ${autoCandidates.length} 个可自动识别的 SKU`}
          description="下方列表里, 系统对每个未绑定 SKU 给出了模型推荐 (基于代码提示 / 关键字)。默认全选, 取消勾选不想自动处理的 SKU 即可。"
        />
        <Table<ShipmentLinesAutoResolveCandidate>
          rowKey="sku_code"
          size="small"
          dataSource={autoCandidates}
          rowSelection={{
            selectedRowKeys: autoSelectedSkus,
            onChange: (keys) => setAutoSelectedSkus(keys as string[]),
          }}
          columns={[
            {
              title: 'SKU',
              dataIndex: 'sku_code',
              key: 'sku_code',
              width: 140,
              render: (v) => (
                <Text style={{ fontFamily: 'monospace', fontSize: 12 }} copyable={{ text: v }}>
                  {v}
                </Text>
              ),
            },
            {
              title: '该 SKU 待处理行数',
              dataIndex: 'shipment_line_count_for_sku',
              key: 'cnt',
              width: 100,
              align: 'center',
              render: (v: number) => <Tag color="orange">{v}</Tag>,
            },
            {
              title: '规格示例',
              dataIndex: 'spec_text',
              key: 'spec_text',
              ellipsis: { showTitle: true },
              render: (v) => (
                <Tooltip title={v || ''}>
                  <Text style={{ fontSize: 12 }}>{v || '-'}</Text>
                </Tooltip>
              ),
            },
            {
              title: '系统推荐模型',
              key: 'model',
              width: 200,
              render: (_, row) => (
                <Space direction="vertical" size={2}>
                  <Tag color="blue">{row.model_code}</Tag>
                  <Text style={{ fontSize: 12 }}>{row.model_name}</Text>
                </Space>
              ),
            },
            {
              title: '识别方式',
              dataIndex: 'match_method',
              key: 'method',
              width: 130,
              render: (m: string | null | undefined, row) => {
                if (m === 'model_code_hint')
                  return <Tag color="purple">代码提示</Tag>
                if (m === 'model_keyword')
                  return (
                    <Space direction="vertical" size={2}>
                      <Tag color="cyan">关键字</Tag>
                      {row.matched_keyword ? (
                        <Text style={{ fontSize: 11 }} type="secondary">
                          {row.matched_keyword}
                        </Text>
                      ) : null}
                    </Space>
                  )
                return <Tag>{m || '?'}</Tag>
              },
            },
          ]}
          pagination={{ pageSize: 20, showSizeChanger: true, pageSizeOptions: ['20', '50', '100'] }}
          scroll={{ x: 800 }}
        />
      </Drawer>
    </div>
  )
}
