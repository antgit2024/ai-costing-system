/**
 * 吉客云 ERP 货品档案 Excel 导入卡片（3 步向导）。
 *
 * Blueprint: DOC/costing/blueprints/jackyun_erp_goods_master_sync_backlog.md §10.2 (C)
 *
 * Flow:
 *   1. 选文件 → inspect → 显示「列映射表」（可手动改 / 加 / 忽略）
 *   2. 确认映射 → dry-run（后台任务）→ 轮询 sync_run，展示 diff 报告 + 抽样
 *   3. 用户勾选「已确认无误」→ commit（后台任务）→ 轮询 sync_run，进度条 + 完成摘要
 *
 * 文件上传：每一步都重传同一份文件（最简单的方案；52MB 在局域网内 ≤ 10s）。
 * 进度跟踪：复用 IntegrationSyncRun + GET /integrations/sync-runs/{id}。
 */
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Modal,
  Progress,
  Result,
  Select,
  Space,
  Statistic,
  Steps,
  Table,
  Tag,
  Typography,
  message,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import CheckCircleOutlined from '@ant-design/icons/lib/icons/CheckCircleOutlined'
import CloseCircleOutlined from '@ant-design/icons/lib/icons/CloseCircleOutlined'
import InboxOutlined from '@ant-design/icons/lib/icons/InboxOutlined'
import LoadingOutlined from '@ant-design/icons/lib/icons/LoadingOutlined'
import ThunderboltOutlined from '@ant-design/icons/lib/icons/ThunderboltOutlined'

import {
  type JackyunGoodsImportInspectResponse,
  commitJackyunGoodsXlsx,
  dryRunJackyunGoodsXlsx,
  getSyncRunDetail,
  inspectJackyunGoodsXlsx,
} from '@/services/integrations'

const { Text, Paragraph } = Typography

const STEPS = [
  { title: '上传 + 列识别', description: 'inspect' },
  { title: 'Dry-run 预演', description: '不写库' },
  { title: '正式导入', description: 'commit' },
] as const

interface JackyunGoodsImportCardProps {
  onCommitted?: () => void
}

interface ColumnMappingRow {
  col_idx: number
  header: string
  target_field: string | '__ignore__'
}

const IGNORE_TARGET = '__ignore__'

const JackyunGoodsImportCard = ({ onCommitted }: JackyunGoodsImportCardProps) => {
  const [open, setOpen] = useState(false)
  const [step, setStep] = useState(0)
  const [file, setFile] = useState<File | null>(null)
  const [inspect, setInspect] = useState<JackyunGoodsImportInspectResponse | null>(null)
  const [mappingRows, setMappingRows] = useState<ColumnMappingRow[]>([])
  const [dryRunId, setDryRunId] = useState<string | null>(null)
  const [commitRunId, setCommitRunId] = useState<string | null>(null)
  const [confirmedDry, setConfirmedDry] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const reset = () => {
    setStep(0)
    setFile(null)
    setInspect(null)
    setMappingRows([])
    setDryRunId(null)
    setCommitRunId(null)
    setConfirmedDry(false)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const handleClose = () => {
    setOpen(false)
    reset()
  }

  // ---- Step 1: inspect ----
  const inspectMutation = useMutation({
    mutationFn: (f: File) => inspectJackyunGoodsXlsx(f),
    onSuccess: (data) => {
      setInspect(data)
      // Build initial mapping rows from auto_mapping
      const rows: ColumnMappingRow[] = data.headers.map((header, idx) => ({
        col_idx: idx,
        header,
        target_field: data.auto_mapping[String(idx)] ?? IGNORE_TARGET,
      }))
      setMappingRows(rows)
      if (data.missing_required.length > 0) {
        const labels = (data.target_labels ?? {}) as Record<string, string>
        const pretty = data.missing_required
          .map((t) => `${labels[t] ?? t}（${t}）`)
          .join('、')
        message.warning(`缺少必填字段：${pretty}`)
      } else {
        message.success(
          `识别成功：${data.total_cols} 列，${Object.keys(data.auto_mapping).length} 列自动匹配`,
        )
      }
    },
    onError: (err: any) => {
      message.error(`识别失败：${err?.response?.data?.detail ?? err?.message ?? '未知错误'}`)
    },
  })

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    if (!f) return
    setFile(f)
    setInspect(null)
    setMappingRows([])
    inspectMutation.mutate(f)
  }

  // ---- Step 2: dry-run trigger + poll ----
  const dryRunMutation = useMutation({
    mutationFn: () => {
      if (!file) throw new Error('no_file')
      const mapping: Record<string, string> = {}
      mappingRows.forEach((r) => {
        if (r.target_field && r.target_field !== IGNORE_TARGET) {
          mapping[String(r.col_idx)] = r.target_field
        }
      })
      return dryRunJackyunGoodsXlsx(file, mapping, { requested_by: 'ui-goods-import' })
    },
    onSuccess: (resp) => {
      setDryRunId(resp.sync_run_id)
      setStep(1)
      message.success('已派发 Dry-run 任务，等待结果…')
    },
    onError: (err: any) => {
      message.error(`Dry-run 触发失败：${err?.response?.data?.detail ?? err?.message ?? '未知错误'}`)
    },
  })

  const dryRunQuery = useQuery({
    queryKey: ['jackyun-goods-import-run', dryRunId],
    queryFn: () => getSyncRunDetail(dryRunId as string),
    enabled: !!dryRunId,
    refetchInterval: (q) => {
      const s = q.state.data?.run?.status
      return s === 'running' || s === 'pending' ? 1500 : false
    },
  })

  const dryRunReport = dryRunQuery.data?.run?.result as Record<string, any> | null | undefined

  // ---- Step 3: commit trigger + poll ----
  const commitMutation = useMutation({
    mutationFn: () => {
      if (!file) throw new Error('no_file')
      const mapping: Record<string, string> = {}
      mappingRows.forEach((r) => {
        if (r.target_field && r.target_field !== IGNORE_TARGET) {
          mapping[String(r.col_idx)] = r.target_field
        }
      })
      return commitJackyunGoodsXlsx(file, mapping, {
        requested_by: 'ui-goods-import',
        batch_size: 5000,
      })
    },
    onSuccess: (resp) => {
      setCommitRunId(resp.sync_run_id)
      setStep(2)
      message.success('已派发正式导入任务，跑批中…')
    },
    onError: (err: any) => {
      message.error(`正式导入触发失败：${err?.response?.data?.detail ?? err?.message ?? '未知错误'}`)
    },
  })

  const commitQuery = useQuery({
    queryKey: ['jackyun-goods-import-run', commitRunId],
    queryFn: () => getSyncRunDetail(commitRunId as string),
    enabled: !!commitRunId,
    refetchInterval: (q) => {
      const s = q.state.data?.run?.status
      return s === 'running' || s === 'pending' ? 2000 : false
    },
  })

  const commitReport = commitQuery.data?.run?.result as Record<string, any> | null | undefined

  // 把 onCommitted 放进 ref 避免父组件 inline arrow function 引用变化导致 useEffect 死循环
  // (React Error #185: bumpRefresh 是父组件每次 render 新建的箭头函数, 旧版把它列入 useEffect 依赖
  //  导致 status='success' 后无限触发 setRefreshKey → 子组件 props 变 → effect 再触发).
  const onCommittedRef = useRef(onCommitted)
  useEffect(() => {
    onCommittedRef.current = onCommitted
  }, [onCommitted])
  const commitNotifiedRef = useRef(false)
  useEffect(() => {
    if (
      commitQuery.data?.run?.status === 'success' &&
      !commitNotifiedRef.current
    ) {
      commitNotifiedRef.current = true
      onCommittedRef.current?.()
    }
  }, [commitQuery.data?.run?.status])

  // 中文 label / 必填集 (从 inspect 响应拿)
  const targetLabels = inspect?.target_labels ?? {}
  const requiredSet = useMemo(
    () => new Set(inspect?.required_targets ?? []),
    [inspect?.required_targets],
  )
  const labelFor = (target: string): string => targetLabels[target] ?? target

  // ---- target field options for the mapping column ----
  // option label 渲染为 "中文 · english_key"; 必填字段前面加红 ★。
  const targetOptions = useMemo(() => {
    if (!inspect) return []
    const all = [
      ...inspect.physical_targets,
      ...inspect.metadata_targets,
      ...inspect.image_targets,
      ...inspect.dimension_targets,
    ]
    const opts = Array.from(new Set(all))
      .sort((a, b) => {
        const aReq = requiredSet.has(a) ? 0 : 1
        const bReq = requiredSet.has(b) ? 0 : 1
        if (aReq !== bReq) return aReq - bReq
        return labelFor(a).localeCompare(labelFor(b), 'zh-Hans-CN')
      })
      .map((t) => {
        const cn = labelFor(t)
        const isReq = requiredSet.has(t)
        return {
          value: t,
          // 已选状态的显示值 (Select 默认 fallback)
          label: (
            <span>
              {isReq ? <span style={{ color: '#ff4d4f', marginRight: 4 }}>★</span> : null}
              <span>{cn}</span>
              <Text type="secondary" style={{ marginLeft: 6, fontFamily: 'monospace', fontSize: 11 }}>
                {t}
              </Text>
            </span>
          ),
          // 用于 Select 的过滤搜索
          searchText: `${cn} ${t}`,
        }
      })
    opts.unshift({
      value: IGNORE_TARGET,
      label: <Text type="secondary">— 忽略此列 —</Text>,
      searchText: '忽略 ignore',
    })
    return opts
  }, [inspect, requiredSet])

  const usedTargets = useMemo(
    () => new Set(mappingRows.map((r) => r.target_field).filter((t) => t !== IGNORE_TARGET)),
    [mappingRows],
  )

  const mappingColumns: ColumnsType<ColumnMappingRow> = [
    { title: 'Excel 列', dataIndex: 'col_idx', width: 70, render: (n: number) => `#${n + 1}` },
    {
      title: 'Excel 表头',
      dataIndex: 'header',
      width: 160,
      ellipsis: true,
      render: (h: string) => h || <Text type="secondary">(空)</Text>,
    },
    {
      title: '映射到系统字段',
      dataIndex: 'target_field',
      width: 360,
      render: (_: unknown, row) => (
        <Select
          size="small"
          style={{ width: '100%' }}
          value={row.target_field}
          showSearch
          optionFilterProp="searchText"
          filterOption={(input, opt) =>
            ((opt as { searchText?: string })?.searchText ?? '')
              .toLowerCase()
              .includes(input.toLowerCase())
          }
          options={targetOptions.map((o) => ({
            ...o,
            disabled:
              o.value !== IGNORE_TARGET &&
              o.value !== row.target_field &&
              usedTargets.has(o.value),
          }))}
          onChange={(v) => {
            setMappingRows((rows) =>
              rows.map((r) => (r.col_idx === row.col_idx ? { ...r, target_field: v } : r)),
            )
          }}
        />
      ),
    },
    {
      title: '映射含义',
      width: 180,
      render: (_: unknown, row) => {
        if (row.target_field === IGNORE_TARGET) {
          return <Text type="secondary">—</Text>
        }
        const cn = labelFor(row.target_field)
        const isReq = requiredSet.has(row.target_field)
        return (
          <span>
            {isReq ? (
              <span style={{ color: '#ff4d4f', marginRight: 4 }} title="必填字段">
                ★
              </span>
            ) : null}
            <Text>{cn}</Text>
          </span>
        )
      },
    },
    {
      title: '识别状态',
      width: 110,
      render: (_: unknown, row) => {
        if (row.target_field === IGNORE_TARGET) {
          return <Tag>忽略</Tag>
        }
        const wasAuto = inspect?.auto_mapping[String(row.col_idx)] === row.target_field
        const isReq = requiredSet.has(row.target_field)
        return (
          <Space size={4}>
            {isReq ? <Tag color="red">必填</Tag> : null}
            {wasAuto ? <Tag color="green">自动</Tag> : <Tag color="orange">手动</Tag>}
          </Space>
        )
      },
    },
  ]

  const hasMissingRequired = inspect?.missing_required.length ? inspect.missing_required.length > 0 : false
  const requiredOk = !hasMissingRequired

  return (
    <>
      <Card
        size="small"
        title={
          <Space>
            <InboxOutlined style={{ color: '#fa8c16' }} />
            <span>吉客云 · 货品档案 Excel 导入</span>
            <Tag color="orange">首次铺底用 / 后续走 API 增量</Tag>
          </Space>
        }
        extra={
          <Button
            type="primary"
            icon={<InboxOutlined />}
            onClick={() => {
              reset()
              setOpen(true)
            }}
          >
            上传 Excel…
          </Button>
        }
      >
        <Paragraph type="secondary" style={{ marginBottom: 0 }}>
          一次性铺底吉客云 40+ 万行 ERP 货品档案。
          走 <Text strong>3 步向导</Text>：①列识别 → ②Dry-run 预演 → ③正式导入。
          默认<Text strong>窄覆盖</Text>策略：只有 Excel 表头里出现的列才覆盖 sku_master，未出现的字段（如 production_process、sku_flag）保持不动。
          单次最多 50 万行，5000 行 / 事务批提交，43 万行预计 20-30 分钟。
        </Paragraph>
      </Card>

      <Modal
        title="吉客云 · 货品档案 Excel 导入向导"
        open={open}
        onCancel={handleClose}
        width={1100}
        footer={null}
        destroyOnClose
      >
        <Steps current={step} items={STEPS as unknown as Array<{ title: string; description?: string }>} style={{ marginBottom: 24 }} />

        {/* Step 0: 选文件 + 列映射 */}
        {step === 0 ? (
          <Space direction="vertical" size={16} style={{ width: '100%' }}>
            <Alert
              type="info"
              showIcon
              message="第一步：上传文件，系统会自动识别列名并映射到 sku_master 字段"
              description={
                <span>
                  如有未识别列（橙色「手动」标识），可手动从下拉选择目标字段，或选「忽略」跳过。
                  下拉选项格式：<Text strong>中文名</Text>
                  <Text type="secondary" style={{ fontFamily: 'monospace', marginLeft: 4 }}>english_key</Text>
                  ，前缀 <span style={{ color: '#ff4d4f' }}>★</span> 表示必填。
                  映射方案需保留缺一不可的 <span style={{ color: '#ff4d4f' }}>★</span>条码（erp_sku_barcode）。
                </span>
              }
            />
            <Card size="small" title="① 选择文件">
              <input
                ref={fileInputRef}
                type="file"
                accept=".xlsx"
                onChange={handleFileChange}
                style={{ marginBottom: 8 }}
              />
              {file ? (
                <Text type="secondary">
                  {file.name}（{(file.size / 1024 / 1024).toFixed(1)} MB）
                </Text>
              ) : null}
              {inspectMutation.isPending ? (
                <Text type="secondary"> · 识别中…</Text>
              ) : null}
            </Card>

            {inspect ? (
              <Card size="small" title={`② 列映射（${inspect.total_cols} 列）`}>
                {hasMissingRequired ? (
                  <Alert
                    type="error"
                    showIcon
                    message={
                      <span>
                        缺少必填字段：
                        {inspect.missing_required.map((t, i) => (
                          <span key={t}>
                            {i > 0 ? '、' : null}
                            <span style={{ color: '#ff4d4f', marginRight: 2 }}>★</span>
                            {labelFor(t)}
                            <Text type="secondary" style={{ fontFamily: 'monospace', fontSize: 11, marginLeft: 4 }}>
                              ({t})
                            </Text>
                          </span>
                        ))}
                      </span>
                    }
                    description="请检查 Excel 是否包含「条码」列（候选名：条码 / 货品条码 / SKU条码 / barcode）"
                    style={{ marginBottom: 12 }}
                  />
                ) : null}
                <Table<ColumnMappingRow>
                  rowKey="col_idx"
                  size="small"
                  columns={mappingColumns}
                  dataSource={mappingRows}
                  pagination={false}
                  scroll={{ y: 360 }}
                />
                <div style={{ marginTop: 16, textAlign: 'right' }}>
                  <Space>
                    <Button onClick={handleClose}>取消</Button>
                    <Button
                      type="primary"
                      icon={<ThunderboltOutlined />}
                      disabled={!requiredOk}
                      loading={dryRunMutation.isPending}
                      onClick={() => dryRunMutation.mutate()}
                    >
                      继续 → Dry-run 预演
                    </Button>
                  </Space>
                </div>
              </Card>
            ) : null}
          </Space>
        ) : null}

        {/* Step 1: Dry-run 报告 */}
        {step === 1 ? (
          <Space direction="vertical" size={16} style={{ width: '100%' }}>
            <Alert
              type="warning"
              showIcon
              message="第二步：Dry-run 预演 — 完整解析全文件，模拟 upsert，但不写库"
              description="确认报告数据无误后，再勾选下方「已确认无误」并点击「正式导入」。"
            />
            <Card size="small" title="① Dry-run 运行状态">
              <DryRunReportPanel
                mode="dry_run"
                status={dryRunQuery.data?.run?.status ?? 'pending'}
                report={dryRunReport ?? null}
                errorMessage={dryRunQuery.data?.run?.error_message ?? null}
                startedAt={dryRunQuery.data?.run?.started_at ?? null}
              />
            </Card>
            <div style={{ textAlign: 'right' }}>
              <Space>
                <Button onClick={() => setStep(0)}>← 返回映射</Button>
                <Checkbox
                  checked={confirmedDry}
                  onChange={(e) => setConfirmedDry(e.target.checked)}
                  disabled={dryRunQuery.data?.run?.status !== 'success'}
                >
                  已确认 Dry-run 无误
                </Checkbox>
                <Button
                  type="primary"
                  danger
                  icon={<ThunderboltOutlined />}
                  disabled={!confirmedDry || dryRunQuery.data?.run?.status !== 'success'}
                  loading={commitMutation.isPending}
                  onClick={() => commitMutation.mutate()}
                >
                  正式导入
                </Button>
              </Space>
            </div>
          </Space>
        ) : null}

        {/* Step 2: commit 进度 */}
        {step === 2 ? (
          <Space direction="vertical" size={16} style={{ width: '100%' }}>
            <Alert
              type="success"
              showIcon
              message="第三步：正式导入 — 5000 行 / 事务批提交"
              description={`一旦开始即不可中断；43 万行预计 20-30 分钟。完成后可在 sync_run_id=${commitRunId} 查看历史。`}
            />
            <Card size="small" title="导入运行状态">
              <DryRunReportPanel
                mode="commit"
                status={commitQuery.data?.run?.status ?? 'pending'}
                report={commitReport ?? null}
                errorMessage={commitQuery.data?.run?.error_message ?? null}
                startedAt={commitQuery.data?.run?.started_at ?? null}
              />
            </Card>
            <div style={{ textAlign: 'right' }}>
              <Button type="primary" onClick={handleClose}>
                完成 / 关闭
              </Button>
            </div>
          </Space>
        ) : null}
      </Modal>
    </>
  )
}

// ---------------------------------------------------------------------------
// 工具：秒数 → "Xm Ys" 字符串
// ---------------------------------------------------------------------------
const formatDuration = (seconds: number): string => {
  const s = Math.max(0, Math.round(seconds))
  if (s < 60) return `${s} 秒`
  const m = Math.floor(s / 60)
  const r = s % 60
  return r === 0 ? `${m} 分` : `${m} 分 ${r} 秒`
}

// 实时计时 hook：从 startedAt 开始计已用秒数（每 1s 触发 re-render）
const useElapsedSeconds = (startedAt: string | null | undefined, active: boolean): number => {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!active || !startedAt) return
    const iv = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(iv)
  }, [active, startedAt])
  if (!startedAt) return 0
  return Math.max(0, (now - new Date(startedAt).getTime()) / 1000)
}

// ---------------------------------------------------------------------------
// Dry-run / commit 报告统一渲染（重写：状态徽章 + Statistic + 进度条）
// ---------------------------------------------------------------------------
interface DryRunReportPanelProps {
  status: string
  report: Record<string, any> | null
  errorMessage: string | null
  startedAt?: string | null
  mode: 'dry_run' | 'commit'
}

// commit / dry_run 估算完成时长（秒）— 用于运行中进度条
const ESTIMATED_TOTAL_S = { dry_run: 380, commit: 480 }

const DryRunReportPanel = ({ status, report, errorMessage, startedAt, mode }: DryRunReportPanelProps) => {
  const isRunning = status === 'pending' || status === 'running'
  const elapsedLive = useElapsedSeconds(startedAt ?? null, isRunning)
  const total = ESTIMATED_TOTAL_S[mode] || 480
  // 运行中进度条：按 elapsed/estimated 估算，封顶 95% 避免假装完成
  const progressPct = Math.min(95, Math.round((elapsedLive / total) * 100))

  // ---- 运行中 ----
  if (isRunning) {
    return (
      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        <Space align="center" size={12}>
          <LoadingOutlined style={{ fontSize: 24, color: '#1677ff' }} spin />
          <Text strong style={{ fontSize: 16 }}>
            {mode === 'dry_run' ? 'Dry-run 预演中…' : '导入进行中…'}
          </Text>
          <Tag color="processing">running</Tag>
        </Space>
        <Progress
          percent={progressPct}
          status="active"
          strokeColor={{ from: '#108ee9', to: '#87d068' }}
        />
        <Space size={32} wrap>
          <Statistic title="已用时长" value={formatDuration(elapsedLive)} />
          <Statistic
            title="预估总时长"
            value={formatDuration(total)}
            valueStyle={{ color: '#888' }}
          />
          <Statistic
            title="预估剩余"
            value={formatDuration(Math.max(0, total - elapsedLive))}
            valueStyle={{ color: '#888' }}
          />
        </Space>
        <Alert
          type="info"
          showIcon
          message="任务在后端独立进程中运行"
          description="可以安全关闭浏览器或断网；任务完成后可在「运行历史」标签查看结果。窗口下次打开会显示最终报告。"
        />
      </Space>
    )
  }

  // ---- 失败 ----
  if (status === 'failed') {
    return (
      <Result
        status="error"
        icon={<CloseCircleOutlined />}
        title="任务失败"
        subTitle={errorMessage ?? '未知错误'}
      />
    )
  }

  // ---- 等待 / 无数据 ----
  if (status !== 'success' || !report) {
    return <Text type="secondary">等待结果…</Text>
  }

  // ---- 成功 ----
  const totalRows = report.total_rows ?? 0
  const newRows = report.new_rows ?? 0
  const updatedRows = report.updated_rows ?? 0
  const fieldsChanged = report.fields_changed ?? 0
  const skipped = report.skipped_no_barcode ?? 0
  const duplicates = report.duplicate_in_file ?? 0
  const errorsLen = report.errors?.length ?? 0
  const elapsedActual = report.elapsed_seconds ?? 0

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      {/* 状态横幅 */}
      <Space align="center" size={12}>
        <CheckCircleOutlined style={{ fontSize: 24, color: '#52c41a' }} />
        <Text strong style={{ fontSize: 16 }}>
          {mode === 'dry_run' ? 'Dry-run 预演完成' : '正式导入完成'}
        </Text>
        <Tag color="success">success</Tag>
        <Text type="secondary">耗时 {formatDuration(elapsedActual)}</Text>
      </Space>

      {/* 4 大统计 */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(4, 1fr)',
          gap: 12,
          padding: 16,
          background: 'rgba(24,144,255,0.04)',
          borderRadius: 8,
        }}
      >
        <Statistic title="解析总行数" value={totalRows} groupSeparator="," />
        <Statistic
          title="新增 SKU"
          value={newRows}
          groupSeparator=","
          valueStyle={{ color: '#52c41a' }}
        />
        <Statistic
          title="更新 SKU"
          value={updatedRows}
          groupSeparator=","
          valueStyle={{ color: '#1677ff' }}
        />
        <Statistic
          title="字段变更"
          value={fieldsChanged}
          groupSeparator=","
          suffix="处"
          valueStyle={{ color: '#faad14' }}
        />
      </div>

      {/* 次要指标 */}
      <Space wrap size={12}>
        <Tag color={skipped > 0 ? 'warning' : 'default'}>无条码跳过 {skipped}</Tag>
        <Tag color={duplicates > 0 ? 'warning' : 'default'}>文件内重复 {duplicates}</Tag>
        <Tag color={errorsLen > 0 ? 'error' : 'default'}>错误 {errorsLen}</Tag>
      </Space>

      {/* 抽样变更 */}
      {report.sample_changes?.length ? (
        <Card size="small" title={`抽样变更（前 ${report.sample_changes.length} 行）`}>
          <Table
            rowKey={(_r, i) => String(i)}
            size="small"
            pagination={false}
            dataSource={report.sample_changes}
            columns={[
              { title: '行号', dataIndex: 'row', width: 70 },
              { title: '条码', dataIndex: 'barcode', width: 160 },
              {
                title: '操作',
                dataIndex: 'action',
                width: 80,
                render: (a: string) =>
                  a === 'new' ? (
                    <Tag color="green">新增</Tag>
                  ) : (
                    <Tag color="blue">更新</Tag>
                  ),
              },
              {
                title: '变更字段数',
                dataIndex: 'fields_changed',
                width: 100,
                align: 'right' as const,
                render: (n: number | undefined) =>
                  n !== undefined ? n : <Text type="secondary">—</Text>,
              },
              {
                title: '物理列写入',
                dataIndex: 'physical',
                render: (p: Record<string, string> | undefined) =>
                  p && Object.keys(p).length ? (
                    <Space wrap size={[4, 4]}>
                      {Object.entries(p).map(([k, v]) => (
                        <Tag key={k} style={{ fontFamily: 'monospace', fontSize: 11, margin: 0 }}>
                          <Text type="secondary">{k}=</Text>
                          {String(v).length > 40 ? String(v).slice(0, 38) + '…' : v}
                        </Tag>
                      ))}
                    </Space>
                  ) : (
                    <Text type="secondary">—</Text>
                  ),
              },
            ]}
          />
        </Card>
      ) : null}

      {/* 错误明细 */}
      {errorsLen > 0 ? (
        <Card size="small" title={`错误明细（前 ${Math.min(errorsLen, 50)} 条）`}>
          <Table
            rowKey={(_r, i) => String(i)}
            size="small"
            pagination={false}
            dataSource={report.errors.slice(0, 50)}
            columns={[
              { title: '行号', dataIndex: 'row', width: 80 },
              { title: 'error', dataIndex: 'error' },
            ]}
          />
        </Card>
      ) : null}
    </Space>
  )
}

export default JackyunGoodsImportCard
