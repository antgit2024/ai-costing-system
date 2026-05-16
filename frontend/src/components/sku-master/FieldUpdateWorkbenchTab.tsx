/**
 * <FieldUpdateWorkbenchTab /> — 商品关联工作台「字段维护」 Tab
 *
 * 业务背景
 * --------
 * 商品关联（/sku-master）是本系统侧的【通用批量落库引擎】，原本只有"绑定/解绑"两个 mutation；
 * 用户在 2026-05-16 提出："商品档案那边批量改工艺/标签如果几万条要落库，
 * 不要重复造分批写库的轮子，直接复用商品关联的'一键跑完'机制即可"。
 *
 * 本 Tab 就是这个机制的入口：
 *   1. 用户在 /products-info 选好"改什么字段、新值、目标范围" → 写 sessionStorage + 跳转
 *      `navigate('/sku-master?workbenchTab=field_update&from=products-info')`
 *   2. 本 Tab 自动激活，从 sessionStorage 读取待执行参数
 *   3. 用户可"预览影响行数" → 调 /update-field-bulk/preview (dry_run=true)
 *   4. 用户点"一键跑完" → 循环调 /update-field-bulk 直到 has_more=false
 *   5. 完成后清理 sessionStorage
 *
 * 设计要点
 * - 与 manual / auto Tab 的"一键跑完"循环结构一致（防止重复造 progress UI）
 * - mutation 范围：production_process / metadata.erp.sku_flag（白名单同后端）
 * - 安全：未携带 pendingFieldUpdate 时只显示"无待执行任务"占位（防止误操作）
 *
 * 与 ERP 反写的区别
 * - 本 Tab 只管【本系统落库】。ERP 反写是【独立模块】（M4 系列），
 *   入口在商品档案的"反写到 ERP"按钮，不走本 Tab。
 */

import { useEffect, useRef, useState } from 'react'
import { Alert, Button, Card, Descriptions, Modal, Space, Tag, Typography, message } from 'antd'

import {
  previewUpdateSkuMasterFieldBulk,
  updateSkuMasterFieldBulk,
  type SkuMasterUpdateFieldBulkRequest,
  type SkuMasterUpdateFieldMode,
  type SkuMasterUpdateFieldName,
} from '@/services/planner'

const { Text } = Typography

// sessionStorage key — 与商品档案侧（M3-P4 顶部"批量改"按钮）保持一致
export const PENDING_FIELD_UPDATE_SESSION_KEY = 'sku_master_pending_field_update'

const FIELD_LABELS: Record<string, string> = {
  production_process: '工艺说明 (production_process, 物理列)',
  'metadata.erp.sku_flag': '规格标记 (metadata.erp.sku_flag, JSON 数组)',
}

const MODE_LABELS: Record<SkuMasterUpdateFieldMode, string> = {
  set: '覆盖 (set)',
  append_unique: '追加去重 (append_unique, 仅数组)',
  remove: '移除指定项 (remove, 仅数组)',
}

const SOURCE_LABELS: Record<string, string> = {
  'products-info': '商品档案',
  manual: '手动构造',
}

export interface PendingFieldUpdate {
  field_name: SkuMasterUpdateFieldName | string
  new_value: unknown
  mode?: SkuMasterUpdateFieldMode
  requested_by?: string
  // 调用方式：sku_master_ids 与 filters 互斥
  sku_master_ids?: string[]
  filters?: {
    search?: string
    channel?: string
    match_status?: string
    spec_mismatch?: boolean
    preparse_state?: string
    include_terms?: string
    exclude_terms?: string
    match_scope?: 'spec' | 'name' | 'auto' | 'spec_or_name'
    bound_state?: 'bound' | 'unbound' | 'all'
    bound_model_id?: string
    bound_model_code?: string
    bound_version_id?: string
    bundle_bound_state?: 'bound' | 'unbound' | 'all'
    bundle_template_id?: string
    bundle_preset_selector?: string
  }
  excluded_sku_master_ids?: string[]
  // 元数据
  source?: string
  display_label?: string
  timestamp?: string
}

interface RunProgress {
  round: number
  total_updated: number
  total_skipped: number
  total_errors: number
  last_update: string
  note?: string
  done: boolean
}

const formatValue = (v: unknown): string => {
  if (v === null || v === undefined) return '(清空)'
  if (Array.isArray(v)) return v.length ? `[${v.map((x) => String(x)).join(', ')}]` : '[]'
  return String(v)
}

const buildBaseRequest = (p: PendingFieldUpdate): SkuMasterUpdateFieldBulkRequest => {
  const base: SkuMasterUpdateFieldBulkRequest = {
    field_name: p.field_name,
    new_value: p.new_value,
    mode: p.mode ?? 'set',
    requested_by: p.requested_by,
  }
  if (p.sku_master_ids && p.sku_master_ids.length > 0) {
    base.sku_master_ids = p.sku_master_ids
  } else if (p.filters) {
    Object.assign(base, p.filters)
  }
  if (p.excluded_sku_master_ids && p.excluded_sku_master_ids.length > 0) {
    base.excluded_sku_master_ids = p.excluded_sku_master_ids
  }
  return base
}

export default function FieldUpdateWorkbenchTab() {
  const [pending, setPending] = useState<PendingFieldUpdate | null>(null)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [previewResult, setPreviewResult] = useState<{
    batch_candidates: number
    updated_count: number
    skipped_no_change: number
    errors_count: number
    has_more: boolean
  } | null>(null)
  const [running, setRunning] = useState(false)
  const [progress, setProgress] = useState<RunProgress | null>(null)
  const stopRef = useRef(false)

  // 挂载时从 sessionStorage 读 pending payload
  useEffect(() => {
    try {
      const raw = sessionStorage.getItem(PENDING_FIELD_UPDATE_SESSION_KEY)
      if (raw) setPending(JSON.parse(raw))
    } catch {
      // ignore parse error
    }
  }, [])

  const clearPending = () => {
    try {
      sessionStorage.removeItem(PENDING_FIELD_UPDATE_SESSION_KEY)
    } catch {
      // ignore
    }
    setPending(null)
    setPreviewResult(null)
    setProgress(null)
  }

  const handlePreview = async () => {
    if (!pending) return
    setPreviewLoading(true)
    try {
      const resp = await previewUpdateSkuMasterFieldBulk(buildBaseRequest(pending), { timeoutMs: 60_000 })
      setPreviewResult({
        batch_candidates: resp.batch_candidates,
        updated_count: resp.updated_count,
        skipped_no_change: resp.skipped_no_change,
        errors_count: resp.errors.length,
        has_more: resp.has_more,
      })
      message.success(`预览完成：将影响 ${resp.updated_count} 条 (本批 ${resp.batch_candidates}, ${resp.has_more ? '还有更多' : '已全部'})`)
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || '预览失败')
    } finally {
      setPreviewLoading(false)
    }
  }

  const handleRunAll = async () => {
    if (!pending) return
    const isExplicitIds = !!(pending.sku_master_ids && pending.sku_master_ids.length > 0)
    Modal.confirm({
      title: '确认一键跑完？',
      content: (
        <div style={{ lineHeight: 1.7 }}>
          <div>
            将把字段 <code>{pending.field_name}</code> ({MODE_LABELS[pending.mode ?? 'set']}) 设为：
          </div>
          <div style={{ marginTop: 8, padding: 8, background: '#fafafa', borderRadius: 4 }}>
            <Text code>{formatValue(pending.new_value)}</Text>
          </div>
          <div style={{ marginTop: 8, color: '#999' }}>
            {isExplicitIds
              ? `精确目标：${pending.sku_master_ids!.length} 个 sku_master_id`
              : '按筛选条件跨页执行，每批 200 条循环至完成。'}
          </div>
        </div>
      ),
      okText: '开始执行',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        setRunning(true)
        stopRef.current = false
        let round = 0
        let total_updated = 0
        let total_skipped = 0
        let total_errors = 0
        try {
          while (!stopRef.current) {
            round += 1
            const resp = await updateSkuMasterFieldBulk(
              { ...buildBaseRequest(pending), dry_run: false, limit: 200 },
              { timeoutMs: 90_000 },
            )
            total_updated += resp.updated_count
            total_skipped += resp.skipped_no_change
            total_errors += resp.errors.length
            setProgress({
              round,
              total_updated,
              total_skipped,
              total_errors,
              last_update: new Date().toLocaleTimeString('zh-CN'),
              note: resp.has_more ? '还有更多, 继续...' : undefined,
              done: !resp.has_more,
            })
            // 显式 ID 模式无 has_more 概念, 一轮就结束
            if (isExplicitIds) break
            if (!resp.has_more) break
            if (resp.batch_candidates === 0) break
            // 防御性：如果一轮 0 进展（全部 no_change 也算无进展），停止避免死循环
            if (resp.updated_count === 0 && resp.skipped_no_change === resp.batch_candidates) {
              setProgress((p) => p && { ...p, note: '本轮 0 净进展, 已自动停止' })
              break
            }
          }
          if (stopRef.current) {
            message.warning(`已手动停止：累计 updated=${total_updated} errors=${total_errors}`)
          } else if (total_errors > 0) {
            message.warning(`执行完成（含错误）：updated=${total_updated} errors=${total_errors}`)
          } else {
            message.success(`执行完成：updated=${total_updated} skipped=${total_skipped}`)
          }
          // 成功完成 → 清理 pending (用户可手动"再选一批")
          if (!stopRef.current && total_errors === 0) {
            clearPending()
          }
        } catch (e: any) {
          message.error(e?.response?.data?.detail || e?.message || '执行失败')
        } finally {
          setRunning(false)
        }
      },
    })
  }

  if (!pending) {
    return (
      <Space direction="vertical" style={{ width: '100%' }}>
        <Alert
          type="info"
          showIcon
          message="字段维护 Tab — 无待执行任务"
          description={
            <div style={{ lineHeight: 1.7 }}>
              本 Tab 接收来自<b>商品档案</b>页"批量改"按钮的跳转。
              <br />
              请到 <Text code>/costing/products-info</Text> 选择目标行 + 点"批量改工艺/批量加标签"
              过来执行，本 Tab 即会显示待执行任务。
            </div>
          }
        />
      </Space>
    )
  }

  const isExplicit = !!(pending.sku_master_ids && pending.sku_master_ids.length > 0)
  return (
    <Space direction="vertical" style={{ width: '100%' }} size={12}>
      <Card size="small" title="待执行任务" extra={<Tag color="purple">{SOURCE_LABELS[pending.source || ''] || pending.source || '未知来源'}</Tag>}>
        <Descriptions size="small" column={1} bordered>
          <Descriptions.Item label="目标字段">
            {FIELD_LABELS[pending.field_name] || pending.field_name}
          </Descriptions.Item>
          <Descriptions.Item label="模式">{MODE_LABELS[pending.mode ?? 'set']}</Descriptions.Item>
          <Descriptions.Item label="新值">
            <Text code style={{ whiteSpace: 'normal' }}>
              {formatValue(pending.new_value)}
            </Text>
          </Descriptions.Item>
          <Descriptions.Item label="影响目标">
            {isExplicit ? (
              <span>
                <Tag color="blue">精确 ID</Tag> {pending.sku_master_ids!.length} 个
              </span>
            ) : (
              <span>
                <Tag color="orange">按筛选</Tag>{' '}
                <Text type="secondary" style={{ fontSize: 12 }}>
                  {Object.entries(pending.filters ?? {})
                    .filter(([, v]) => v !== undefined && v !== null && v !== '')
                    .map(([k, v]) => `${k}=${String(v)}`)
                    .join(' & ') || '(无筛选, 全表)'}
                </Text>
                {pending.excluded_sku_master_ids && pending.excluded_sku_master_ids.length > 0 ? (
                  <Tag color="red" style={{ marginLeft: 4 }}>
                    排除 {pending.excluded_sku_master_ids.length}
                  </Tag>
                ) : null}
              </span>
            )}
          </Descriptions.Item>
          {pending.timestamp ? (
            <Descriptions.Item label="跳转时间">
              <Text type="secondary" style={{ fontSize: 12 }}>
                {pending.timestamp}
              </Text>
            </Descriptions.Item>
          ) : null}
        </Descriptions>
      </Card>

      <Space wrap>
        <Button onClick={handlePreview} loading={previewLoading} disabled={running}>
          预览影响行数 (dry_run)
        </Button>
        <Button type="primary" danger onClick={handleRunAll} loading={running}>
          一键跑完
        </Button>
        {running ? (
          <Button
            onClick={() => {
              stopRef.current = true
              message.info('已请求停止：将在本轮执行结束后停止')
            }}
          >
            停止
          </Button>
        ) : null}
        <Button onClick={clearPending} disabled={running}>
          清除任务
        </Button>
      </Space>

      {previewResult ? (
        <Alert
          type="info"
          showIcon
          message="预览结果"
          description={
            <div>
              当前批 {previewResult.batch_candidates} 条 · 将更新 {previewResult.updated_count} 条 · 无需改 {previewResult.skipped_no_change} 条 · 错误 {previewResult.errors_count} 条 · {previewResult.has_more ? '还有更多批次' : '已是最后一批'}
            </div>
          }
        />
      ) : null}

      {progress ? (
        <Alert
          type={progress.done ? 'success' : running ? 'info' : 'warning'}
          showIcon
          message={`进度：第 ${progress.round} 轮 · 累计 updated=${progress.total_updated} · skipped=${progress.total_skipped} · errors=${progress.total_errors}`}
          description={`最后更新：${progress.last_update}${progress.note ? ` · ${progress.note}` : ''}${progress.done ? ' · 已完成' : ''}`}
        />
      ) : null}
    </Space>
  )
}
