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
  Select,
  Space,
  Steps,
  Table,
  Tag,
  Typography,
  message,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import InboxOutlined from '@ant-design/icons/lib/icons/InboxOutlined'
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
        message.warning(`缺少必填字段：${data.missing_required.join(', ')}`)
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

  useEffect(() => {
    if (commitQuery.data?.run?.status === 'success' && onCommitted) {
      onCommitted()
    }
  }, [commitQuery.data?.run?.status, onCommitted])

  // ---- target field options for the mapping column ----
  const targetOptions = useMemo(() => {
    if (!inspect) return []
    const all = [
      ...inspect.physical_targets,
      ...inspect.metadata_targets,
      ...inspect.image_targets,
      ...inspect.dimension_targets,
    ]
    const opts = Array.from(new Set(all))
      .sort()
      .map((t) => ({ value: t, label: t }))
    opts.unshift({ value: IGNORE_TARGET, label: '— 忽略此列 —' })
    return opts
  }, [inspect])

  const usedTargets = useMemo(
    () => new Set(mappingRows.map((r) => r.target_field).filter((t) => t !== IGNORE_TARGET)),
    [mappingRows],
  )

  const mappingColumns: ColumnsType<ColumnMappingRow> = [
    { title: 'Excel 列', dataIndex: 'col_idx', width: 70, render: (n: number) => `#${n + 1}` },
    {
      title: 'Excel 表头',
      dataIndex: 'header',
      ellipsis: true,
      render: (h: string) => h || <Text type="secondary">(空)</Text>,
    },
    {
      title: '映射到系统字段',
      dataIndex: 'target_field',
      width: 300,
      render: (_: unknown, row) => (
        <Select
          size="small"
          style={{ width: '100%' }}
          value={row.target_field}
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
      title: '识别状态',
      width: 110,
      render: (_: unknown, row) => {
        if (row.target_field === IGNORE_TARGET) {
          return <Tag>忽略</Tag>
        }
        const wasAuto = inspect?.auto_mapping[String(row.col_idx)] === row.target_field
        return wasAuto ? <Tag color="green">自动</Tag> : <Tag color="orange">手动</Tag>
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
              description="如有未识别列（橙色标识），可手动从下拉选择目标字段，或选「忽略」跳过。映射方案需保留缺一不可的 erp_sku_barcode。"
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
                    message={`缺少必填字段：${inspect.missing_required.join(', ')}`}
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
                status={dryRunQuery.data?.run?.status ?? 'pending'}
                report={dryRunReport ?? null}
                errorMessage={dryRunQuery.data?.run?.error_message ?? null}
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
                status={commitQuery.data?.run?.status ?? 'pending'}
                report={commitReport ?? null}
                errorMessage={commitQuery.data?.run?.error_message ?? null}
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
// Dry-run / commit 报告统一渲染
// ---------------------------------------------------------------------------

interface DryRunReportPanelProps {
  status: string
  report: Record<string, any> | null
  errorMessage: string | null
}

const DryRunReportPanel = ({ status, report, errorMessage }: DryRunReportPanelProps) => {
  if (status === 'pending' || status === 'running') {
    return (
      <Space direction="vertical" style={{ width: '100%' }}>
        <Text type="secondary">运行中…{report?.parsed_rows ? `（已解析 ${report.parsed_rows} 行）` : ''}</Text>
        {report?.total_rows ? (
          <Text type="secondary">本次共 {report.total_rows} 行，预计 {report.mode === 'dry_run' ? '60-120s' : '5-30 分钟'} 完成</Text>
        ) : null}
      </Space>
    )
  }
  if (status === 'failed') {
    return <Alert type="error" message="任务失败" description={errorMessage ?? '未知错误'} showIcon />
  }
  if (status !== 'success' || !report) {
    return <Text type="secondary">等待结果…</Text>
  }

  return (
    <Space direction="vertical" size={12} style={{ width: '100%' }}>
      <Space wrap>
        <Tag>总行数 {report.total_rows ?? 0}</Tag>
        <Tag color="green">新增 {report.new_rows ?? 0}</Tag>
        <Tag color="blue">更新 {report.updated_rows ?? 0}</Tag>
        <Tag>实际字段变更 {report.fields_changed ?? 0}</Tag>
        <Tag>无条码跳过 {report.skipped_no_barcode ?? 0}</Tag>
        <Tag>文件内重复 {report.duplicate_in_file ?? 0}</Tag>
        <Tag color={(report.errors?.length ?? 0) > 0 ? 'red' : 'default'}>错误 {report.errors?.length ?? 0}</Tag>
        <Tag color="purple">耗时 {report.elapsed_seconds ?? 0}s</Tag>
      </Space>

      {report.sample_changes?.length ? (
        <Card size="small" title="抽样变更（前 5 行）">
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
                width: 90,
                render: (a: string) => (
                  <Tag color={a === 'new' ? 'green' : 'blue'}>{a}</Tag>
                ),
              },
              {
                title: '变更字段',
                dataIndex: 'fields_changed',
                width: 100,
                render: (n: number | undefined) => (n !== undefined ? n : '-'),
              },
              {
                title: '物理列',
                dataIndex: 'physical',
                render: (p: Record<string, string> | undefined) =>
                  p ? (
                    <Space wrap size={4}>
                      {Object.entries(p).map(([k, v]) => (
                        <Tag key={k} style={{ fontFamily: 'monospace', fontSize: 11 }}>
                          {k}={v}
                        </Tag>
                      ))}
                    </Space>
                  ) : (
                    '-'
                  ),
              },
            ]}
          />
        </Card>
      ) : null}

      {report.errors?.length ? (
        <Card size="small" title={`错误明细（前 ${Math.min(report.errors.length, 50)} 条）`}>
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
