/**
 * <ProductInfoDetailDrawer /> — 商品档案行详情抽屉
 *
 * 业务背景
 * --------
 * 商品档案 (/costing/products-info) 是【生产维护主战场】。运营在列表里发现需要维护的商品，
 * 点击行打开本抽屉，按 Tab 分层维护：基础只读 / 字段编辑(4 字段一次保存+自动重识别) / 店铺映射 / 反写历史。
 *
 * 「字段编辑」统一表单 (M5)
 * --------------------------
 * 把原来分散在 3 个 Tab 的字段 (production_process / sku_flag / shop_spec_code) +
 * 新增的 spec_text 统一到一个表单, 一次保存. 后端走 POST /sku-master/edit-form 接口
 * (见 backend/src/planner/services/sku_master_service.py::edit_sku_form).
 *
 * 字段-反写目标对照:
 *   生产工艺 (production_process)  ↔ 吉客云「工艺说明(规)」/ process_instructions
 *   规格标记 (sku_flag)             ↔ 吉客云「规格标记」 / skuFlag
 *   模型编码 (shop_spec_code) ⭐    ↔ 吉客云「模型编码(规)」/ model_code (反写源=识别后的 bound_variant_code)
 *   属性规格 (spec_text)            ↔ 吉客云「规格」 / skuName
 *
 * 模型编码字段的特殊行为
 * --------------------
 * 编辑 shop_spec_code 保存后, 后端会自动 deactivate 当前 active binding +
 * 触发单条 auto_bind_execute → bound_variant_code 跟随重识别 (P0 商家编码锚点 > P1 关键词).
 * 表单展示重识别前后对比, 用户立即看到效果.
 *
 * 与商品关联的关系
 * ------------------
 * - 单条编辑(本抽屉) → 直接调 editSkuForm, 不跳转
 * - 批量编辑(商品档案顶部"批量改"按钮) → 写 sessionStorage + 跳转 /sku-master?workbenchTab=field_update
 *
 * Tabs (M5 后)
 * ----
 * 1. 基础: 三标签对账(只读) + 主图 + 基础信息 + 规格对照
 * 2. 字段编辑: 4 字段统一表单 + 单一保存 + 重识别结果提示
 * 3. 店铺映射: shop_sku_mappings (一个 ERP 货品可在多店铺销售)
 * 4. 反写历史: integration_writeback_jobs 表 (按本 SKU 条码筛选, 倒序展示 jobs)
 * 5. 原始 metadata: JSON 折叠 (debug)
 */

import { useEffect, useMemo, useState } from 'react'
import {
  Alert,
  Button,
  Card,
  Descriptions,
  Drawer,
  Form,
  Image,
  Input,
  Space,
  Table,
  Tabs,
  Tag,
  Tooltip,
  Typography,
  message,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import {
  downloadErpWritebackExcel,
  editSkuForm,
  enqueueErpWriteback,
  ERP_WRITEBACK_FIELD_LABELS,
  fetchErpWritebackHistory,
  fetchSkuMasterByBarcode,
  fetchSkuMasterDetail,
  triggerBrowserDownload,
} from '@/services/planner'
import type {
  ErpWritebackField,
  ErpWritebackHistoryItem,
  SkuEditFormField,
  SkuMasterEditFormResponse,
} from '@/services/planner'
import type { ShopSkuMappingRead, SkuMaster } from '@/types/planner'
import { formatBeijingTime } from '@/utils/beijingTime'
import { IMAGE_FALLBACK_SVG, pickRowImageUrl } from '@/utils/imageUrl'
import {
  computeTripleTagState,
  describeConflict,
  isShopSpecCodeClean,
  OVERALL_LABEL,
  TAG_COLORS,
} from '@/utils/skuMasterTagState'
import { normalizeSpecForCompare, prettifyDisplaySpec } from '@/utils/specNormalize'

const { Text } = Typography
const { TextArea } = Input

interface Props {
  skuId: string | null
  open: boolean
  onClose: () => void
  /** Called after successful single-row update; parent typically refetches the list. */
  onUpdated?: () => void
}

const formatTime = (v?: string | null) => formatBeijingTime(v, 'YYYY-MM-DD HH:mm:ss')

const asArray = (v: unknown): string[] => {
  if (Array.isArray(v)) return v.map((x) => String(x ?? '')).filter(Boolean)
  if (v == null || v === '') return []
  return [String(v)]
}

// 比较两个字符串数组是否等值 (用于 sku_flag dirty 判断)
const sameStrArray = (a: string[], b: string[]): boolean => {
  if (a.length !== b.length) return false
  for (let i = 0; i < a.length; i += 1) if (a[i] !== b[i]) return false
  return true
}

interface FormDraft {
  production_process: string
  sku_flag: string[]
  shop_spec_code: string
  spec_text: string
}

const emptyDraft: FormDraft = {
  production_process: '',
  sku_flag: [],
  shop_spec_code: '',
  spec_text: '',
}

const draftFromSku = (sku: SkuMaster | undefined): FormDraft => {
  if (!sku) return emptyDraft
  const erp = ((sku.metadata_json ?? {}) as any)?.erp ?? {}
  return {
    production_process: String(sku.production_process ?? ''),
    sku_flag: asArray(erp?.sku_flag),
    shop_spec_code: String(sku.shop_spec_code ?? ''),
    spec_text: String(sku.spec_text ?? ''),
  }
}

export default function ProductInfoDetailDrawer({ skuId, open, onClose, onUpdated }: Props) {
  const queryClient = useQueryClient()
  const [draft, setDraft] = useState<FormDraft>(emptyDraft)
  const [flagInput, setFlagInput] = useState<string>('')
  const [lastSaveResult, setLastSaveResult] = useState<SkuMasterEditFormResponse | null>(null)
  const [requestedBy] = useState<string>('product-info-drawer')

  const detailQuery = useQuery({
    queryKey: ['product-info', 'detail', skuId],
    queryFn: () => fetchSkuMasterDetail(skuId as string),
    enabled: !!skuId && open,
  })

  const sku = detailQuery.data as SkuMaster | undefined
  const barcode = sku?.erp_sku_barcode

  // 店铺映射: 按条码查询返回 {sku_master, shop_skus[]}
  const shopsQuery = useQuery({
    queryKey: ['product-info', 'shop-mappings', barcode],
    queryFn: () => fetchSkuMasterByBarcode(barcode as string, { limit: 50 }),
    enabled: open && !!barcode,
  })

  // ERP 反写历史 (单条 SKU)
  const writebackHistoryQuery = useQuery({
    queryKey: ['product-info', 'erp-writeback-history', sku?.id],
    queryFn: () => fetchErpWritebackHistory(sku!.id, 50),
    enabled: open && !!sku?.id,
  })

  // Server 数据回流时, 同步 draft (除非用户有未保存修改)
  useEffect(() => {
    if (sku) {
      setDraft(draftFromSku(sku))
      setLastSaveResult(null)
      setFlagInput('')
    }
  }, [sku?.id, sku?.production_process, sku?.shop_spec_code, sku?.spec_text, sku?.metadata_json])

  const syncedFlags = useMemo(() => {
    const meta = (sku?.metadata_json ?? {}) as Record<string, unknown>
    const erp = (meta?.erp ?? {}) as Record<string, unknown>
    return asArray(erp?.sku_flag_synced)
  }, [sku])

  // dirty fields: 用户改了的字段
  const dirtyFields: SkuEditFormField[] = useMemo(() => {
    const base = draftFromSku(sku)
    const dirty: SkuEditFormField[] = []
    if (draft.production_process !== base.production_process) dirty.push('production_process')
    if (!sameStrArray(draft.sku_flag, base.sku_flag)) dirty.push('sku_flag')
    if (draft.shop_spec_code !== base.shop_spec_code) dirty.push('shop_spec_code')
    if (draft.spec_text !== base.spec_text) dirty.push('spec_text')
    return dirty
  }, [draft, sku])

  // ============================================================
  // Mutation: 统一表单保存 (调 editSkuForm)
  // ============================================================

  const editFormMutation = useMutation({
    mutationFn: async () => {
      if (!sku?.id) throw new Error('no sku selected')
      if (dirtyFields.length === 0) throw new Error('没有需要保存的修改')
      return editSkuForm({
        sku_master_id: sku.id,
        update_fields: dirtyFields,
        production_process: dirtyFields.includes('production_process')
          ? draft.production_process.trim() || null
          : undefined,
        sku_flag: dirtyFields.includes('sku_flag') ? draft.sku_flag : undefined,
        shop_spec_code: dirtyFields.includes('shop_spec_code')
          ? draft.shop_spec_code.trim() || null
          : undefined,
        spec_text: dirtyFields.includes('spec_text')
          ? draft.spec_text.trim() || null
          : undefined,
        trigger_rebind: true,
        requested_by: requestedBy,
      }, { timeoutMs: 30_000 })
    },
    onSuccess: (resp) => {
      setLastSaveResult(resp)
      const updated = resp.per_field_results.filter((r) => r.updated).length
      const noChange = resp.per_field_results.filter((r) => r.no_change).length
      const errors = resp.per_field_results.flatMap((r) => r.errors || [])
      if (errors.length > 0) {
        message.warning(`保存有错误: ${errors[0]?.error || '未知'}`)
      } else if (updated > 0) {
        if (resp.rebind?.triggered) {
          const before = resp.rebind.before_variant || '(无)'
          const after = resp.rebind.after_variant || '(无)'
          if (before !== after) {
            message.success(`已保存 ${updated} 个字段；商家编码触发重识别: ${before} → ${after}`)
          } else {
            message.success(`已保存 ${updated} 个字段；重识别完成 (结果未变: ${after})`)
          }
        } else {
          message.success(`已保存 ${updated} 个字段`)
        }
      } else if (noChange > 0) {
        message.info('值未变化, 跳过')
      }
      detailQuery.refetch()
      onUpdated?.()
      queryClient.invalidateQueries({ queryKey: ['product-info', 'list'] })
      queryClient.invalidateQueries({ queryKey: ['product-info', 'triple-tag-overview'] })
    },
    onError: (e: any) => {
      message.error(e?.response?.data?.detail || e?.message || '保存失败')
    },
  })

  // ============================================================
  // Mutation: M6 ERP 反写 — 单条 Excel 下载 + 单条入队
  // ============================================================

  const writebackExcelMutation = useMutation({
    mutationFn: async () => {
      if (!sku?.id) throw new Error('no sku selected')
      return downloadErpWritebackExcel(
        { sku_master_ids: [sku.id] },
        { timeoutMs: 30_000 },
      )
    },
    onSuccess: (result) => {
      triggerBrowserDownload(result.blob, result.filename)
      message.success(`已生成 ${result.totalRows} 行 Excel: ${result.filename}`)
    },
    onError: (e: any) => {
      message.error(e?.response?.data?.detail || e?.message || '导出失败')
    },
  })

  const writebackEnqueueMutation = useMutation({
    mutationFn: async () => {
      if (!sku?.id) throw new Error('no sku selected')
      return enqueueErpWriteback(
        {
          sku_master_ids: [sku.id],
          requested_by: requestedBy,
        },
        { timeoutMs: 30_000 },
      )
    },
    onSuccess: (resp) => {
      if (resp.skipped_count > 0 && resp.enqueued_count === 0) {
        const reason = resp.skipped?.[0]?.reason
        message.warning(`未入队: ${reason || '无可反写值'}`)
        return
      }
      if (resp.superseded_count > 0) {
        message.success(`已入队 (合并旧任务 ${resp.superseded_count} 条)`)
      } else {
        message.success(`已加入反写队列 (${resp.enqueued_count} 条)`)
      }
      writebackHistoryQuery.refetch()
    },
    onError: (e: any) => {
      message.error(e?.response?.data?.detail || e?.message || '入队失败')
    },
  })

  const handleAddFlag = () => {
    const t = flagInput.trim()
    if (!t) return
    if (draft.sku_flag.includes(t)) {
      message.info('标签已存在')
      return
    }
    setDraft({ ...draft, sku_flag: [...draft.sku_flag, t] })
    setFlagInput('')
  }

  const handleRemoveFlag = (tag: string) => {
    setDraft({ ...draft, sku_flag: draft.sku_flag.filter((x) => x !== tag) })
  }

  const handleResetDraft = () => {
    setDraft(draftFromSku(sku))
    setFlagInput('')
    setLastSaveResult(null)
  }

  const handleFillSpecTextFromShipment = () => {
    const shipment = ((sku?.last_shipment_spec_text || '') as string).trim()
    if (!shipment) {
      message.info('无最后发货规格')
      return
    }
    const pretty = prettifyDisplaySpec(shipment) || shipment
    setDraft({ ...draft, spec_text: pretty })
  }

  // ============================================================
  // Render
  // ============================================================

  const tagState = sku ? computeTripleTagState(sku) : null
  const erpModelCodeReg = (() => {
    if (!sku) return ''
    const erp = ((sku.metadata_json ?? {}) as any).erp ?? {}
    return String(erp.model_code_reg ?? '').trim()
  })()

  // ---- Tab 1: 基础 (只读三标签对账 + 主图 + 基础信息 + 规格对照) ----
  const tabBasic = sku ? (
    <Space direction="vertical" size={12} style={{ width: '100%' }}>
      {tagState ? (
        <Card
          size="small"
          title={
            <span>
              三标签对账{' '}
              <Text type="secondary" style={{ fontSize: 12, fontWeight: 'normal' }}>
                — 系统是真源, 商家是输入, ERP 是反写后的下游镜像
              </Text>
            </span>
          }
        >
          <div style={{ marginBottom: 8 }}>
            <Tag color={OVERALL_LABEL[tagState.overall].color} style={{ fontSize: 12 }}>
              {OVERALL_LABEL[tagState.overall].text}
            </Tag>
          </div>
          {(() => {
            const cd = describeConflict(tagState.conflict)
            if (!cd) return null
            const sev = tagState.conflict.kind
            const alertType: 'error' | 'warning' =
              sev === 'shop_model_diff' ? 'error' : 'warning'
            return (
              <Alert
                type={alertType}
                showIcon
                style={{ marginBottom: 12 }}
                message={cd.title}
                description={
                  <div style={{ lineHeight: 1.7 }}>
                    <div>{cd.detail}</div>
                    <div style={{ marginTop: 6, color: '#888', fontSize: 12 }}>
                      处理建议: 先确认哪一边是对的 →
                      {sev === 'shop_model_diff' || sev === 'shop_variant_diff' ? (
                        <span>
                          {' '}如果<b>系统识别错了</b>, 到「商品关联」重新绑定;
                          如果<b>商家编码填错了</b>, 切到「字段编辑」Tab 把模型编码改成正确值并保存 (会自动重识别)
                        </span>
                      ) : (
                        <span> ERP 端值偏离, 切到「字段编辑」Tab 保存后, 用「下载反写 Excel」或「加入反写队列」推送系统真源.</span>
                      )}
                    </div>
                  </div>
                }
              />
            )
          })()}
          <Descriptions size="small" column={1} bordered>
            <Descriptions.Item
              label={
                <Tooltip title="我们系统权威识别的标准模型变体编码 — 真源. 来自商品关联绑定结果 (bound_model_code + bound_variant_code).">
                  <span>🅂 系统标签 (真源)</span>
                </Tooltip>
              }
            >
              {tagState.sys.kind === 'matched' ? (
                <Space>
                  <Tag color={TAG_COLORS.sys_matched}>{tagState.sys.variantCode || tagState.sys.modelCode}</Tag>
                  {tagState.sys.modelName ? <Text type="secondary">{tagState.sys.modelName}</Text> : null}
                  <Text type="success" style={{ fontSize: 12 }}>✓ 可作为 ERP 反写源</Text>
                </Space>
              ) : tagState.sys.kind === 'bundle' ? (
                <Space>
                  <Tag color={TAG_COLORS.sys_bundle}>{`B-${tagState.sys.bundleCode}${tagState.sys.presetSelector || ''}`}</Tag>
                  {tagState.sys.bundleName ? <Text type="secondary">{tagState.sys.bundleName}</Text> : null}
                </Space>
              ) : (
                <Space>
                  <Tag color={TAG_COLORS.sys_unmatched}>未匹配</Tag>
                  <Text type="warning" style={{ fontSize: 12 }}>请到「商品关联」做绑定</Text>
                </Space>
              )}
              {sku.recognition_source ? (
                <div style={{ marginTop: 6, fontSize: 12, color: '#888' }}>
                  识别依据:{' '}
                  {sku.recognition_source === 'merchant_code' ? '🟢 商家编码直锁' :
                    sku.recognition_source === 'keyword_variant'
                      ? `🔵 关键词→变体${sku.recognition_input_source === 'shipment' ? ' (发货)' : sku.recognition_input_source === 'archive' ? ' (档案)' : ''}`
                      : sku.recognition_source === 'keyword_model_only'
                        ? `🟡 关键词→仅模型${sku.recognition_input_source === 'shipment' ? ' (发货)' : sku.recognition_input_source === 'archive' ? ' (档案)' : ''}`
                        : sku.recognition_source === 'bundle' ? '🟣 套装模板' : '⚪ 未识别'}
                </div>
              ) : null}
            </Descriptions.Item>
            <Descriptions.Item
              label={
                <Tooltip title="网店运营在商家编码字段录入的原始值. 历史脏值认了, 新上架的会按规范填. 编辑入口在「字段编辑」Tab.">
                  <span>🅑 商家标签 (输入材料)</span>
                </Tooltip>
              }
            >
              <Space wrap>
                {tagState.shop.kind === 'clean' ? (
                  <Tag color={TAG_COLORS.shop_clean}>✓ 已识别 {tagState.shop.value}</Tag>
                ) : tagState.shop.kind === 'dirty' ? (
                  <Tag color={TAG_COLORS.shop_dirty}>⚠ 未识别 (原值: {tagState.shop.value})</Tag>
                ) : (
                  <Tag color={TAG_COLORS.shop_empty}>— 网店未填</Tag>
                )}
                {tagState.shop.kind !== 'empty' && tagState.shop.rawIfChanged ? (
                  <Text type="secondary" style={{ fontSize: 12 }}>(原始: {tagState.shop.rawIfChanged})</Text>
                ) : null}
              </Space>
            </Descriptions.Item>
            <Descriptions.Item
              label={
                <Tooltip title="ERP 那边的 outSkuCode 字段值 — 反写后的下游镜像, 给工厂排产/采购/对账用. 严禁用它反推系统真源.">
                  <span>🅔 ERP 标签 (下游镜像)</span>
                </Tooltip>
              }
            >
              {tagState.erp.kind === 'synced' ? (
                <Space>
                  <Tag color={TAG_COLORS.erp_synced}>✓ 已反写 {tagState.erp.value}</Tag>
                  <Text type="secondary" style={{ fontSize: 12 }}>工厂可按此查询</Text>
                </Space>
              ) : tagState.erp.kind === 'mismatch' ? (
                <Space wrap>
                  <Tag color={TAG_COLORS.erp_mismatch}>≠ 不一致</Tag>
                  <Text type="danger" style={{ fontSize: 12 }}>ERP={tagState.erp.erpValue} ≠ 系统期望={tagState.erp.sysExpected}</Text>
                </Space>
              ) : (
                <Space>
                  <Tag color={TAG_COLORS.erp_waiting}>— 待反写</Tag>
                  <Text type="secondary" style={{ fontSize: 12 }}>用「字段编辑 / 反写」按钮把系统真源推到 ERP</Text>
                </Space>
              )}
            </Descriptions.Item>
            {erpModelCodeReg ? (
              <Descriptions.Item
                label={
                  <Tooltip title="ERP 那边原有的「模型编码(规)」字段值, 仅做参考显示. 不会自动覆盖我们的系统真源 — 用户已对齐这是铁律.">
                    <span>ERP 原有 model_code_reg (仅参考)</span>
                  </Tooltip>
                }
              >
                <Tag color="default">{erpModelCodeReg}</Tag>
                {tagState.sys.kind === 'matched' &&
                erpModelCodeReg.toUpperCase() !== tagState.sys.modelCode.toUpperCase() ? (
                  <Text type="warning" style={{ fontSize: 12, marginLeft: 6 }}>
                    ⚠ 跟系统真源不同 (系统: {tagState.sys.modelCode}). 决定权在运营, 不自动同步.
                  </Text>
                ) : null}
              </Descriptions.Item>
            ) : null}
          </Descriptions>
        </Card>
      ) : null}

      <div style={{ display: 'flex', gap: 16, alignItems: 'flex-start' }}>
        {(() => {
          const previewUrl = pickRowImageUrl(sku.images_json, 600)
          if (!previewUrl) {
            return (
              <div
                style={{
                  width: 120, height: 120,
                  background: '#fafafa', border: '1px dashed #ddd', borderRadius: 4,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  color: '#bbb', fontSize: 12,
                }}
              >
                无主图
              </div>
            )
          }
          return (
            <Image
              src={previewUrl}
              alt="主图"
              width={120}
              height={120}
              style={{ objectFit: 'cover', borderRadius: 4 }}
              fallback={IMAGE_FALLBACK_SVG}
              preview={{ src: previewUrl }}
            />
          )
        })()}
        <div style={{ flex: 1, minWidth: 0 }}>
          <Descriptions size="small" column={2} bordered>
            <Descriptions.Item label="货品条码" span={2}>
              <Text copyable style={{ fontFamily: 'monospace' }}>{sku.erp_sku_barcode || '-'}</Text>
            </Descriptions.Item>
            <Descriptions.Item label="货品名称" span={2}>
              {sku.product_name || <Text type="secondary">—</Text>}
            </Descriptions.Item>
            <Descriptions.Item label="货品编号">{sku.product_code || '-'}</Descriptions.Item>
            <Descriptions.Item label="主渠道">{sku.channel || '-'}</Descriptions.Item>
            <Descriptions.Item label="ERP 货品 ID">{sku.erp_goods_id || '-'}</Descriptions.Item>
            <Descriptions.Item label="ERP 规格 ID">{sku.erp_sku_id || '-'}</Descriptions.Item>
            <Descriptions.Item
              label={
                <Tooltip title="ERP 货品档案的「分类」(category). 用于业务/财务的分组与统计.">
                  <span>分类</span>
                </Tooltip>
              }
            >
              {(() => {
                const erp = ((sku.metadata_json ?? {}) as any)?.erp ?? {}
                const cat = String(erp?.category ?? '').trim()
                return cat ? <Tag>{cat}</Tag> : <Text type="secondary">—</Text>
              })()}
            </Descriptions.Item>
            <Descriptions.Item
              label={
                <Tooltip title="该 ERP 货品在 shop_sku_mappings 里的店铺映射数 (一个 ERP 货品可在多店铺销售). 0 = 未在任何店铺发过货.">
                  <span>店铺数</span>
                </Tooltip>
              }
            >
              {(() => {
                const n = Number((sku as any)?.shop_count ?? 0)
                if (n === 0) return <Text type="secondary">—</Text>
                return <Tag color={n >= 3 ? 'green' : 'blue'}>{n} 店</Tag>
              })()}
            </Descriptions.Item>
            <Descriptions.Item label="状态" span={2}>
              {sku.is_blocked ? <Tag color="red">停用</Tag> : null}
              {sku.is_deleted_at_source ? <Tag color="default">ERP 已删除</Tag> : null}
              {!sku.is_blocked && !sku.is_deleted_at_source ? <Tag color="success">正常</Tag> : null}
            </Descriptions.Item>
            <Descriptions.Item label="更新时间" span={2}>
              {formatTime(sku.updated_at)}
            </Descriptions.Item>
          </Descriptions>
        </div>
      </div>

      <Card
        size="small"
        title={
          <span>
            规格对照{' '}
            <Text type="secondary" style={{ fontSize: 12, fontWeight: 'normal' }}>
              — 档案 vs 发货 vs 归一化后, 看穿"看着不一样实际一样"
            </Text>
          </span>
        }
      >
        {(() => {
          const archive = (sku.spec_text || '').trim()
          const shipment = (sku.last_shipment_spec_text || '').trim()
          const archiveNorm = normalizeSpecForCompare(archive)
          const shipmentNorm = normalizeSpecForCompare(shipment)
          const hasBoth = !!archive && !!shipment
          const normEqual = hasBoth && archiveNorm === shipmentNorm
          const lookDiff = hasBoth && archive !== shipment
          return (
            <Descriptions size="small" column={1} bordered>
              <Descriptions.Item label="档案规格 (网店)">
                <div style={{ whiteSpace: 'normal', wordBreak: 'break-word' }}>{archive || <Text type="secondary">—</Text>}</div>
              </Descriptions.Item>
              <Descriptions.Item label="最后发货规格">
                {shipment ? (
                  (() => {
                    const pretty = prettifyDisplaySpec(shipment)
                    const beautified = pretty !== shipment
                    return (
                      <Space direction="vertical" size={4} style={{ width: '100%' }}>
                        <div style={{ whiteSpace: 'normal', wordBreak: 'break-word' }}>{pretty || shipment}</div>
                        {beautified ? (
                          <details style={{ fontSize: 12 }}>
                            <summary style={{ color: '#888', cursor: 'pointer' }}>查看原文 (含天猫属性标签前缀)</summary>
                            <div style={{ marginTop: 4, color: '#666', whiteSpace: 'normal', wordBreak: 'break-word' }}>{shipment}</div>
                          </details>
                        ) : null}
                      </Space>
                    )
                  })()
                ) : (
                  <Text type="secondary">— (这条 SKU 还未发过货, 识别会退回到档案规格)</Text>
                )}
              </Descriptions.Item>
              {hasBoth ? (
                <Descriptions.Item
                  label={
                    <Tooltip title="把档案规格 / 发货规格 都按规则归一化 (统一全角半角标点, 剥掉「颜色分类:」「规格:」「组合形式:」等中文属性标签前缀), 再字面比较. 与后端 spec_parser_service.normalize_tx_spec_text 保持同语义.">
                      <span>归一化后比对</span>
                    </Tooltip>
                  }
                >
                  <Space direction="vertical" size={4} style={{ width: '100%' }}>
                    <div>
                      <Tag color="default">档案 →</Tag>
                      <Text code style={{ fontSize: 12 }}>{archiveNorm || '—'}</Text>
                    </div>
                    <div>
                      <Tag color="default">发货 →</Tag>
                      <Text code style={{ fontSize: 12 }}>{shipmentNorm || '—'}</Text>
                    </div>
                    {normEqual ? (
                      <Tag color="green">✓ 归一化后完全一致 {lookDiff ? '(原始文本看着不同, 仅属性标签/标点差异)' : ''}</Tag>
                    ) : (
                      <Tag color="red">✗ 真实差异 (尺寸/材质/颜色)</Tag>
                    )}
                  </Space>
                </Descriptions.Item>
              ) : null}
              <Descriptions.Item label="解析尺寸">
                {(() => {
                  const dims = (sku.preparse_dimensions ?? {}) as Record<string, unknown>
                  const w = dims?.width_cm ?? dims?.width
                  const h = dims?.height_cm ?? dims?.height
                  if (!w || !h) return <Tag>未解析</Tag>
                  return <Tag color="green">宽{String(w)}×高{String(h)}cm</Tag>
                })()}
              </Descriptions.Item>
              <Descriptions.Item
                label={
                  <Tooltip title="规格文本被解析器切成的语义片段 (token), 用于关键词匹配 / 去重 / 审计.">
                    <span>解析 TOKEN</span>
                  </Tooltip>
                }
              >
                {(() => {
                  const tokens = (sku.preparse_tokens ?? []) as string[]
                  if (!Array.isArray(tokens) || tokens.length === 0) return <Text type="secondary">—</Text>
                  return (
                    <Space wrap size={4}>
                      {tokens.map((t, i) => (
                        <Tag key={i} style={{ margin: 0 }}>{String(t)}</Tag>
                      ))}
                    </Space>
                  )
                })()}
              </Descriptions.Item>
              <Descriptions.Item label="已绑定">
                {sku.bound_model_code ? (
                  <Space wrap>
                    <Tag color="blue">{sku.bound_model_code}</Tag>
                    {sku.bound_model_name ? <Text type="secondary">{sku.bound_model_name}</Text> : null}
                    {sku.bound_variant_label ? <Tag color="purple">{sku.bound_variant_label}</Tag> : null}
                  </Space>
                ) : sku.bundle_template_code ? (
                  <Tag color="purple">B-{sku.bundle_template_code}{sku.bundle_preset_selector || ''}</Tag>
                ) : (
                  <Tag>未关联</Tag>
                )}
              </Descriptions.Item>
            </Descriptions>
          )
        })()}
      </Card>
    </Space>
  ) : null

  // ---- Tab 2: 字段编辑 (4 字段统一表单 + 单一保存按钮) ----
  const tabEditForm = sku ? (
    <Space direction="vertical" size={12} style={{ width: '100%' }}>
      <Alert
        type="info"
        showIcon
        message="字段编辑 — 4 个反写字段一次保存"
        description={
          <div style={{ lineHeight: 1.7 }}>
            修改下面 4 个字段后点「保存」, 后端按需更新本地库, <b>修改商家编码会自动触发重识别</b>
            (auto_bind_execute), 你会立刻看到系统真源 (bound_variant_code) 跟随更新.
            <br />
            <Text type="secondary" style={{ fontSize: 12 }}>
              4 个字段对应吉客云后台「规格」「模型编码(规)」「工艺说明(规)」「规格标记」, 保存后用下方
              「下载反写 Excel」(在吉客云后台手动导入) 或「加入反写队列」(等 worker 异步推送) 推回 ERP.
            </Text>
          </div>
        }
      />

      <Card size="small">
        <Form layout="vertical" size="small">
          {/* 1. 模型编码 (shop_spec_code) */}
          <Form.Item
            label={
              <Space>
                <span><Tag color="blue" style={{ margin: 0 }}>模型编码</Tag></span>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  ↔ 吉客云「模型编码(规)」(反写源 = 识别后的标准变体码)
                </Text>
              </Space>
            }
          >
            <Input
              value={draft.shop_spec_code}
              onChange={(e) => setDraft({ ...draft, shop_spec_code: e.target.value })}
              placeholder="例: KB8-001 / OZU-004"
              suffix={
                draft.shop_spec_code && isShopSpecCodeClean(draft.shop_spec_code) ? (
                  <Tag color="green" style={{ margin: 0, fontSize: 11 }}>格式合规</Tag>
                ) : draft.shop_spec_code ? (
                  <Tag color="orange" style={{ margin: 0, fontSize: 11 }}>非标准</Tag>
                ) : null
              }
            />
            <div style={{ marginTop: 6, fontSize: 12, color: '#666', lineHeight: 1.7 }}>
              <div>
                🅂 <b>系统识别 (真源, 反写到 ERP 推这个):</b>{' '}
                {sku.bound_variant_code ? (
                  <Tag color="blue" style={{ margin: 0 }}>{sku.bound_variant_code}</Tag>
                ) : sku.bound_model_code ? (
                  <Tag color="cyan" style={{ margin: 0 }}>{sku.bound_model_code} (仅模型)</Tag>
                ) : (
                  <Tag>未识别</Tag>
                )}
                {sku.recognition_source ? (
                  <span style={{ marginLeft: 8, color: '#888' }}>
                    来自:{' '}
                    {sku.recognition_source === 'merchant_code' ? '🟢 商家编码直锁' :
                      sku.recognition_source === 'keyword_variant'
                        ? `🔵 关键词→变体${sku.recognition_input_source === 'shipment' ? ' (发货)' : ' (档案)'}`
                        : sku.recognition_source === 'keyword_model_only'
                          ? `🟡 关键词→仅模型${sku.recognition_input_source === 'shipment' ? ' (发货)' : ' (档案)'}`
                          : sku.recognition_source === 'bundle' ? '🟣 套装模板' : '⚪ 未识别'}
                  </span>
                ) : null}
              </div>
              <div>
                🅑 <b>商家原值 (即将编辑的物理列):</b>{' '}
                <Text code style={{ fontSize: 12 }}>{sku.shop_spec_code || '—'}</Text>
              </div>
              <div>
                🅔 <b>ERP 当前值:</b>{' '}
                <Text code style={{ fontSize: 12 }}>{sku.out_sku_code || '— (待反写)'}</Text>
                {erpModelCodeReg ? (
                  <span style={{ marginLeft: 12, color: '#888' }}>
                    ERP「模型编码(规)」: <Text code style={{ fontSize: 12 }}>{erpModelCodeReg}</Text>
                  </span>
                ) : null}
              </div>
              <div style={{ color: '#888', marginTop: 4 }}>
                💡 编辑此字段后保存, 会强制走「商家编码 P0 锚点」, 覆盖之前的关键词识别结果.
              </div>
            </div>
          </Form.Item>

          {/* 2. 属性规格 (spec_text) */}
          <Form.Item
            label={
              <Space>
                <span><Tag color="purple" style={{ margin: 0 }}>属性规格</Tag></span>
                <Text type="secondary" style={{ fontSize: 12 }}>↔ 吉客云「规格」(skuName)</Text>
              </Space>
            }
          >
            <TextArea
              value={draft.spec_text}
              onChange={(e) => setDraft({ ...draft, spec_text: e.target.value })}
              rows={2}
              placeholder="商品档案规格文本, 例: Q26041801B冰丝凉感-沙发垫;90*240cm"
              maxLength={1000}
              showCount
            />
            <div style={{ marginTop: 6 }}>
              <Space size={8}>
                <Button
                  size="small"
                  type="link"
                  onClick={handleFillSpecTextFromShipment}
                  disabled={!sku.last_shipment_spec_text}
                >
                  ⟸ 用最后发货规格填充
                </Button>
                {sku.last_shipment_spec_text ? (
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    发货: {prettifyDisplaySpec(sku.last_shipment_spec_text) || sku.last_shipment_spec_text}
                  </Text>
                ) : null}
              </Space>
            </div>
          </Form.Item>

          {/* 3. 规格标记 (sku_flag) */}
          <Form.Item
            label={
              <Space>
                <span><Tag color="orange" style={{ margin: 0 }}>规格标记</Tag></span>
                <Text type="secondary" style={{ fontSize: 12 }}>↔ 吉客云「规格标记」(skuFlag)</Text>
              </Space>
            }
          >
            <Space wrap>
              {draft.sku_flag.length === 0 ? <Text type="secondary">(无标签)</Text> : null}
              {draft.sku_flag.map((tag) => (
                <Tag
                  key={tag}
                  color="purple"
                  closable
                  onClose={(e) => {
                    e.preventDefault()
                    handleRemoveFlag(tag)
                  }}
                  style={{ fontSize: 13, padding: '2px 8px' }}
                >
                  {tag}
                </Tag>
              ))}
            </Space>
            <Space.Compact style={{ width: '100%', maxWidth: 400, marginTop: 6 }}>
              <Input
                value={flagInput}
                onChange={(e) => setFlagInput(e.target.value)}
                onPressEnter={handleAddFlag}
                placeholder="新标签 (回车添加; 例: 爆款 / 新品 / 清仓)"
              />
              <Button onClick={handleAddFlag} disabled={!flagInput.trim()}>
                添加
              </Button>
            </Space.Compact>
            {syncedFlags.length > 0 ? (
              <div style={{ marginTop: 8, fontSize: 12 }}>
                <Text type="secondary">ERP 当前值 (影子, 每日 03:30 同步; 冲突以本地为准): </Text>
                <Space wrap size={4}>
                  {syncedFlags.map((tag) => (
                    <Tag key={tag} color="default" style={{ fontSize: 12 }}>{tag}</Tag>
                  ))}
                </Space>
              </div>
            ) : null}
          </Form.Item>

          {/* 4. 生产工艺 (production_process) */}
          <Form.Item
            label={
              <Space>
                <span><Tag color="green" style={{ margin: 0 }}>生产工艺</Tag></span>
                <Text type="secondary" style={{ fontSize: 12 }}>↔ 吉客云「工艺说明(规)」(process_instructions)</Text>
              </Space>
            }
          >
            <TextArea
              value={draft.production_process}
              onChange={(e) => setDraft({ ...draft, production_process: e.target.value })}
              rows={4}
              placeholder="例: 高频热压裁边 / 数码印 / 双面贴合..."
              maxLength={2000}
              showCount
            />
          </Form.Item>

          {/* 保存按钮 */}
          <Form.Item style={{ marginBottom: 0 }}>
            <Space>
              <Button
                type="primary"
                onClick={() => editFormMutation.mutate()}
                disabled={dirtyFields.length === 0 || editFormMutation.isPending}
                loading={editFormMutation.isPending}
              >
                保存 {dirtyFields.length > 0 ? `(${dirtyFields.length} 个字段已修改)` : ''}
              </Button>
              <Button
                onClick={handleResetDraft}
                disabled={dirtyFields.length === 0 || editFormMutation.isPending}
              >
                撤销修改
              </Button>
              <Tooltip
                title={
                  dirtyFields.length > 0
                    ? '当前还有未保存的修改, 建议先保存再反写, 避免推送旧值. 也可以直接反写, 推送的是当前数据库里的真源值.'
                    : '推送 4 个字段 (规格 / 模型编码(规) / 工艺说明(规) / 规格标记) 到吉客云后台. 推送源 = 数据库里的真源.'
                }
              >
                <Button
                  onClick={() => writebackExcelMutation.mutate()}
                  loading={writebackExcelMutation.isPending}
                  disabled={!sku || editFormMutation.isPending}
                >
                  下载反写 Excel
                </Button>
              </Tooltip>
              <Tooltip title="把反写任务入队 (整理在「反写历史」Tab). 后续 worker 会自动调吉客云接口直推, 当前为 pending 状态.">
                <Button
                  onClick={() => writebackEnqueueMutation.mutate()}
                  loading={writebackEnqueueMutation.isPending}
                  disabled={!sku || editFormMutation.isPending}
                >
                  加入反写队列
                </Button>
              </Tooltip>
              {dirtyFields.length > 0 ? (
                <Text type="warning" style={{ fontSize: 12 }}>
                  待保存: {dirtyFields.map((f) => {
                    const label: Record<SkuEditFormField, string> = {
                      production_process: '生产工艺',
                      sku_flag: '规格标记',
                      shop_spec_code: '模型编码',
                      spec_text: '属性规格',
                    }
                    return label[f]
                  }).join(' / ')}
                </Text>
              ) : null}
            </Space>
          </Form.Item>
        </Form>
      </Card>

      {/* 保存后展示重识别结果 */}
      {lastSaveResult ? (
        <Alert
          type={
            (lastSaveResult.per_field_results.flatMap((r) => r.errors || [])).length > 0
              ? 'error'
              : 'success'
          }
          showIcon
          message="保存结果"
          description={
            <div style={{ lineHeight: 1.7, fontSize: 13 }}>
              {lastSaveResult.per_field_results.map((r) => {
                const label: Record<SkuEditFormField, string> = {
                  production_process: '生产工艺',
                  sku_flag: '规格标记',
                  shop_spec_code: '模型编码',
                  spec_text: '属性规格',
                }
                return (
                  <div key={r.field}>
                    {r.updated ? '✓' : r.no_change ? '○' : '✗'} {label[r.field]}{' '}
                    {r.updated ? <Text type="success">已更新</Text> :
                      r.no_change ? <Text type="secondary">无变化</Text> :
                        <Text type="danger">{(r.errors || [])[0]?.error || '失败'}</Text>}
                  </div>
                )
              })}
              {lastSaveResult.rebind?.triggered ? (
                <div style={{ marginTop: 8, padding: 8, background: '#fff7e6', borderRadius: 4 }}>
                  ⚙️ <b>商家编码触发了自动重识别:</b>{' '}
                  <Tag color="default">前: {lastSaveResult.rebind.before_variant || '(无)'}</Tag>
                  →
                  <Tag color={lastSaveResult.rebind.bound ? 'green' : 'orange'}>
                    后: {lastSaveResult.rebind.after_variant || '(无)'}
                  </Tag>
                  {lastSaveResult.rebind.before_variant === lastSaveResult.rebind.after_variant ? (
                    <Text type="secondary" style={{ fontSize: 12, marginLeft: 6 }}>(结果未变, 可能商家编码格式不规范或模型未发布)</Text>
                  ) : null}
                  {(lastSaveResult.rebind.errors || []).length ? (
                    <div style={{ color: '#c00', marginTop: 4 }}>
                      重识别错误: {(lastSaveResult.rebind.errors || [])[0]?.error}
                    </div>
                  ) : null}
                </div>
              ) : null}
            </div>
          }
          closable
          onClose={() => setLastSaveResult(null)}
        />
      ) : null}
    </Space>
  ) : null

  // ---- Tab 3: 店铺映射 ----
  const shopColumns: ColumnsType<ShopSkuMappingRead> = useMemo(
    () => [
      { title: '渠道', dataIndex: 'channel', width: 90, render: (v) => v ? <Tag>{v}</Tag> : '-' },
      {
        title: '平台 SKU ID',
        dataIndex: 'platform_sku_id',
        width: 160,
        render: (v) => <Text copyable style={{ fontFamily: 'monospace', fontSize: 12 }}>{v}</Text>,
      },
      {
        title: '平台货品 ID',
        dataIndex: 'platform_product_id',
        width: 160,
        render: (v) => v ? <Text copyable style={{ fontFamily: 'monospace', fontSize: 12 }}>{v}</Text> : '-',
      },
      {
        title: '商家编码 (店铺侧)',
        dataIndex: 'shop_spec_code',
        width: 140,
        render: (v) => v || '-',
      },
      { title: '更新', dataIndex: 'updated_at', width: 160, render: (v) => formatTime(v) },
    ],
    [],
  )

  const tabShops = (
    <Space direction="vertical" style={{ width: '100%' }}>
      <Alert
        type="info"
        showIcon
        message={`本货品 (条码 ${barcode}) 在 ${shopsQuery.data?.shop_skus?.length ?? 0} 个店铺有映射`}
        description={
          <Text type="secondary" style={{ fontSize: 12 }}>
            来自 shop_sku_mappings (active). 一个 ERP 货品 (条码) 可在多个店铺销售。
          </Text>
        }
      />
      <Table
        rowKey="id"
        size="small"
        loading={shopsQuery.isFetching}
        columns={shopColumns}
        dataSource={shopsQuery.data?.shop_skus ?? []}
        pagination={false}
        scroll={{ y: 400 }}
        locale={{ emptyText: '暂无店铺映射 (该货品可能还未在任何店铺发过货)' }}
      />
    </Space>
  )

  // ---- Tab 4: 反写历史 (真实数据, M6) ----
  const writebackStatusColor: Record<string, string> = {
    pending: 'gold',
    retrying: 'orange',
    succeeded: 'green',
    failed: 'red',
    superseded: 'default',
  }

  const writebackHistoryColumns: ColumnsType<ErpWritebackHistoryItem> = [
    {
      title: '入队时间',
      dataIndex: 'created_at',
      width: 150,
      render: (v) => <Text style={{ fontSize: 12 }}>{formatTime(v)}</Text>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (v: string, row) => (
        <Space size={4}>
          <Tag color={writebackStatusColor[v] || 'default'}>{v}</Tag>
          {row.attempt > 0 ? (
            <Text type="secondary" style={{ fontSize: 11 }}>
              {row.attempt}/{row.max_attempts}
            </Text>
          ) : null}
        </Space>
      ),
    },
    {
      title: '反写字段',
      dataIndex: 'payload',
      width: 240,
      render: (_p, row) => {
        const fields = (row.payload?.fields as string[]) || []
        const values = (row.payload?.values as Record<string, unknown>) || {}
        if (!fields.length) return <Text type="secondary">-</Text>
        return (
          <Space direction="vertical" size={2} style={{ width: '100%' }}>
            {fields.map((f) => {
              const apiName = {
                spec_text: 'skuName',
                model_code_reg: 'model_code',
                process_instructions_reg: 'process_instructions',
                sku_flag: 'flagData',
              }[f] as string | undefined
              const v = apiName ? values[apiName] : null
              const label =
                ERP_WRITEBACK_FIELD_LABELS[f as ErpWritebackField] || f
              return (
                <div key={f} style={{ fontSize: 12 }}>
                  <Text type="secondary">{label}:</Text>{' '}
                  {v == null || v === '' ? (
                    <Text type="secondary" italic>
                      (空)
                    </Text>
                  ) : (
                    <Text>{String(v)}</Text>
                  )}
                </div>
              )
            })}
          </Space>
        )
      },
    },
    {
      title: '操作人',
      dataIndex: 'requested_by',
      width: 100,
      render: (v) => v || <Text type="secondary">-</Text>,
    },
    {
      title: '最后错误',
      dataIndex: 'last_error',
      render: (v) =>
        v ? (
          <Text type="danger" style={{ fontSize: 12 }}>
            {v}
          </Text>
        ) : (
          <Text type="secondary">-</Text>
        ),
    },
  ]

  const tabWriteback = (
    <Space direction="vertical" size={12} style={{ width: '100%' }}>
      <Alert
        type="info"
        showIcon
        message="ERP 反写历史"
        description={
          <div style={{ lineHeight: 1.7, fontSize: 12 }}>
            按时间倒序展示本 SKU (条码 <Text code>{barcode || '-'}</Text>) 的反写记录.
            <br />
            <b>状态说明:</b>
            <Space wrap size={4} style={{ marginLeft: 6 }}>
              <Tag color="gold">pending</Tag>
              <Text type="secondary">等待 worker 推送</Text>
              <Tag color="orange">retrying</Tag>
              <Text type="secondary">已失败重试中</Text>
              <Tag color="green">succeeded</Tag>
              <Text type="secondary">已成功推送到吉客云</Text>
              <Tag color="red">failed</Tag>
              <Text type="secondary">达到最大重试次数仍失败</Text>
              <Tag color="default">superseded</Tag>
              <Text type="secondary">被更新的入队任务覆盖</Text>
            </Space>
            <br />
            Excel 路径不入这个表 (运营在吉客云后台导入 Excel 时是直接覆盖, 不需要本地记录).
          </div>
        }
      />
      {writebackHistoryQuery.isFetching ? (
        <Text type="secondary">加载中…</Text>
      ) : (writebackHistoryQuery.data?.items?.length ?? 0) === 0 ? (
        <Alert
          type="warning"
          showIcon
          message="尚无反写记录"
          description="可在「字段编辑」Tab 点击「加入反写队列」或「下载反写 Excel」生成第一条."
        />
      ) : (
        <Table<ErpWritebackHistoryItem>
          size="small"
          rowKey="id"
          dataSource={writebackHistoryQuery.data?.items || []}
          columns={writebackHistoryColumns}
          pagination={false}
        />
      )}
    </Space>
  )

  // ---- Tab 5: 原始 metadata (debug) ----
  const tabRawMeta = sku ? (
    <Card size="small" title="原始 metadata_json (debug)">
      <pre
        style={{
          background: '#fafafa',
          padding: 12,
          borderRadius: 4,
          maxHeight: 500,
          overflow: 'auto',
          fontSize: 11,
          lineHeight: 1.5,
        }}
      >
        {JSON.stringify(sku.metadata_json ?? {}, null, 2)}
      </pre>
    </Card>
  ) : null

  return (
    <Drawer
      title={
        <Space>
          <span>{sku ? `商品档案详情 — ${sku.erp_sku_barcode || '(无条码)'}` : '商品档案详情'}</span>
          {dirtyFields.length > 0 ? (
            <Tag color="orange">有 {dirtyFields.length} 个字段待保存</Tag>
          ) : null}
        </Space>
      }
      open={open}
      width={1080}
      onClose={() => {
        if (dirtyFields.length > 0) {
          if (!window.confirm(`有 ${dirtyFields.length} 个字段未保存, 确定关闭吗?`)) return
        }
        onClose()
      }}
      destroyOnClose
    >
      {detailQuery.isFetching && !sku ? (
        <Text type="secondary">加载中…</Text>
      ) : !sku ? (
        <Alert type="error" message="加载失败或无该商品" />
      ) : (
        <Tabs
          defaultActiveKey="basic"
          items={[
            { key: 'basic', label: '基础', children: tabBasic },
            {
              key: 'edit-form',
              label: dirtyFields.length > 0 ? `字段编辑 (${dirtyFields.length})` : '字段编辑',
              children: tabEditForm,
            },
            { key: 'shops', label: `店铺映射 (${shopsQuery.data?.shop_skus?.length ?? 0})`, children: tabShops },
            {
              key: 'writeback',
              label: `反写历史 (${writebackHistoryQuery.data?.items?.length ?? 0})`,
              children: tabWriteback,
            },
            { key: 'raw', label: '原始 metadata', children: tabRawMeta },
          ]}
        />
      )}
    </Drawer>
  )
}
