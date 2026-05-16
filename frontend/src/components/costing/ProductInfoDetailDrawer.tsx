/**
 * <ProductInfoDetailDrawer /> — 商品档案行详情抽屉
 *
 * 业务背景
 * --------
 * 商品档案 (/costing/products-info) 是【生产维护主战场】。运营在列表里发现需要维护的商品，
 * 点击行打开本抽屉，按 Tab 分层维护：基础信息只读 / 工艺与标签可编辑 / 反写历史与店铺映射查看。
 *
 * 与商品关联的关系
 * ------------------
 * - 单条编辑（本抽屉里）→ 直接调 updateSkuMasterFieldBulk(sku_master_ids=[id])，不跳转
 * - 批量编辑（M3-P4 列表顶部"批量改"按钮）→ 写 sessionStorage + 跳转 /sku-master?workbenchTab=field_update
 *   走商品关联 FieldUpdateWorkbenchTab 的"一键跑完"
 *
 * Tabs
 * ----
 * 1. 基础: 主图、条码、名称、规格、物理参数、分类、状态（只读）
 * 2. 工艺: production_process 输入框 + 保存（调 update-field-bulk set 模式）
 * 3. 标签: metadata.erp.sku_flag 数组 + 添加/移除（P3 标签字典 MVP 暂为自由输入, 字典化下一轮）
 * 4. 店铺映射: shop_sku_mappings (一个 ERP 货品可在多店铺销售)
 * 5. 反写历史: 从 metadata.erp.*_writeback 读 (M4-5 完成后才有数据)
 * 6. 原始 metadata: JSON 折叠 (debug 用)
 */

import { useEffect, useMemo, useState } from 'react'
import {
  Alert,
  Button,
  Card,
  Descriptions,
  Drawer,
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
  fetchSkuMasterByBarcode,
  fetchSkuMasterDetail,
  updateSkuMasterFieldBulk,
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
import { normalizeSpecText } from '@/utils/specNormalize'

const { Text, Paragraph } = Typography
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

export default function ProductInfoDetailDrawer({ skuId, open, onClose, onUpdated }: Props) {
  const queryClient = useQueryClient()
  const [processDraft, setProcessDraft] = useState<string>('')
  const [flagDraft, setFlagDraft] = useState<string>('')
  const [shopSpecDraft, setShopSpecDraft] = useState<string>('')
  const [requestedBy] = useState<string>('product-info-drawer')

  const detailQuery = useQuery({
    queryKey: ['product-info', 'detail', skuId],
    queryFn: () => fetchSkuMasterDetail(skuId as string),
    enabled: !!skuId && open,
  })

  const sku = detailQuery.data as SkuMaster | undefined
  const barcode = sku?.erp_sku_barcode

  // Shop mappings: scan by barcode returns {sku_master, shop_skus[]}
  const shopsQuery = useQuery({
    queryKey: ['product-info', 'shop-mappings', barcode],
    queryFn: () => fetchSkuMasterByBarcode(barcode as string, { limit: 50 }),
    enabled: open && !!barcode,
  })

  // sync draft with server value whenever sku changes
  useEffect(() => {
    if (sku) {
      setProcessDraft(String(sku.production_process ?? ''))
      setShopSpecDraft(String(sku.shop_spec_code ?? ''))
    }
  }, [sku?.id, sku?.production_process, sku?.shop_spec_code])

  const currentFlags = useMemo(() => {
    const meta = (sku?.metadata_json ?? {}) as Record<string, unknown>
    const erp = (meta?.erp ?? {}) as Record<string, unknown>
    return asArray(erp?.sku_flag)
  }, [sku])

  const syncedFlags = useMemo(() => {
    const meta = (sku?.metadata_json ?? {}) as Record<string, unknown>
    const erp = (meta?.erp ?? {}) as Record<string, unknown>
    return asArray(erp?.sku_flag_synced)
  }, [sku])

  // ============================================================
  // Mutations: 单条 update (调 update-field-bulk with sku_master_ids=[id])
  // ============================================================

  const saveProcessMutation = useMutation({
    mutationFn: async (newValue: string) => {
      if (!sku?.id) throw new Error('no sku selected')
      return updateSkuMasterFieldBulk(
        {
          field_name: 'production_process',
          new_value: newValue.trim() || null,
          mode: 'set',
          sku_master_ids: [sku.id],
          requested_by: requestedBy,
        },
        { timeoutMs: 30_000 },
      )
    },
    onSuccess: (resp) => {
      if (resp.errors.length > 0) {
        message.warning(`保存有错误: ${resp.errors[0].error}`)
      } else if (resp.skipped_no_change > 0) {
        message.info('值未变化, 跳过')
      } else if (resp.updated_count > 0) {
        message.success('工艺已保存')
      }
      detailQuery.refetch()
      onUpdated?.()
      queryClient.invalidateQueries({ queryKey: ['product-info', 'list'] })
    },
    onError: (e: any) => {
      message.error(e?.response?.data?.detail || e?.message || '保存失败')
    },
  })

  const addFlagMutation = useMutation({
    mutationFn: async (tag: string) => {
      if (!sku?.id) throw new Error('no sku selected')
      const t = tag.trim()
      if (!t) throw new Error('请输入标签')
      return updateSkuMasterFieldBulk(
        {
          field_name: 'metadata.erp.sku_flag',
          new_value: [t],
          mode: 'append_unique',
          sku_master_ids: [sku.id],
          requested_by: requestedBy,
        },
        { timeoutMs: 30_000 },
      )
    },
    onSuccess: (resp) => {
      if (resp.updated_count > 0) {
        message.success('标签已添加')
        setFlagDraft('')
      } else if (resp.skipped_no_change > 0) {
        message.info('标签已存在')
      } else if (resp.errors.length > 0) {
        message.warning(`添加失败: ${resp.errors[0].error}`)
      }
      detailQuery.refetch()
      onUpdated?.()
      queryClient.invalidateQueries({ queryKey: ['product-info', 'list'] })
    },
    onError: (e: any) => {
      message.error(e?.response?.data?.detail || e?.message || '添加失败')
    },
  })

  // shop_spec_code — 让运营把脏值 (Q26041801KB8-001) 手动改成干净的 KB8-001
  const saveShopSpecMutation = useMutation({
    mutationFn: async (newValue: string) => {
      if (!sku?.id) throw new Error('no sku selected')
      return updateSkuMasterFieldBulk(
        {
          field_name: 'shop_spec_code',
          new_value: newValue.trim() || null,
          mode: 'set',
          sku_master_ids: [sku.id],
          requested_by: requestedBy,
        },
        { timeoutMs: 30_000 },
      )
    },
    onSuccess: (resp) => {
      if (resp.errors.length > 0) {
        message.warning(`保存有错误: ${resp.errors[0].error}`)
      } else if (resp.skipped_no_change > 0) {
        message.info('值未变化, 跳过')
      } else if (resp.updated_count > 0) {
        message.success('商家编码已保存')
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

  const removeFlagMutation = useMutation({
    mutationFn: async (tag: string) => {
      if (!sku?.id) throw new Error('no sku selected')
      return updateSkuMasterFieldBulk(
        {
          field_name: 'metadata.erp.sku_flag',
          new_value: [tag],
          mode: 'remove',
          sku_master_ids: [sku.id],
          requested_by: requestedBy,
        },
        { timeoutMs: 30_000 },
      )
    },
    onSuccess: (resp) => {
      if (resp.updated_count > 0) {
        message.success('标签已移除')
      }
      detailQuery.refetch()
      onUpdated?.()
      queryClient.invalidateQueries({ queryKey: ['product-info', 'list'] })
    },
    onError: (e: any) => {
      message.error(e?.response?.data?.detail || e?.message || '移除失败')
    },
  })

  // ============================================================
  // Render: Tabs
  // ============================================================

  const tagState = sku ? computeTripleTagState(sku) : null
  const erpModelCodeReg = (() => {
    if (!sku) return ''
    const erp = ((sku.metadata_json ?? {}) as any).erp ?? {}
    return String(erp.model_code_reg ?? '').trim()
  })()

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
            // 高风险用 error, 中风险用 warning
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
                          如果<b>商家编码填错了</b>, 在下面的「商家标签」输入框里直接改成正确值并保存
                        </span>
                      ) : (
                        <span> ERP 端值偏离, 点击下方的「立即反写」按钮重新覆盖 ERP</span>
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
            </Descriptions.Item>
            <Descriptions.Item
              label={
                <Tooltip title="网店运营在商家编码字段录入的原始值. 历史脏值 (Q24091001 这种款号) 几十万存量认了, 新上架的会按规范填.">
                  <span>🅑 商家标签 (输入材料)</span>
                </Tooltip>
              }
            >
              <Space direction="vertical" style={{ width: '100%' }} size={6}>
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
                <Space.Compact style={{ width: '100%', maxWidth: 420 }}>
                  <Input
                    value={shopSpecDraft}
                    onChange={(e) => setShopSpecDraft(e.target.value)}
                    placeholder="可手动修正为标准变体码 (如 KB8-001)"
                    disabled={saveShopSpecMutation.isPending}
                    suffix={
                      shopSpecDraft && isShopSpecCodeClean(shopSpecDraft) ? (
                        <Tag color="green" style={{ margin: 0, fontSize: 11 }}>格式合规</Tag>
                      ) : shopSpecDraft ? (
                        <Tag color="orange" style={{ margin: 0, fontSize: 11 }}>非标准</Tag>
                      ) : null
                    }
                  />
                  <Button
                    type="primary"
                    loading={saveShopSpecMutation.isPending}
                    onClick={() => saveShopSpecMutation.mutate(shopSpecDraft)}
                    disabled={shopSpecDraft === (sku.shop_spec_code ?? '')}
                  >
                    保存
                  </Button>
                </Space.Compact>
                <Text type="secondary" style={{ fontSize: 11 }}>
                  修正脏数据为标准格式 (例: KB8-001 / OZU-004) 后, 才能被自动绑定到标准模型。
                </Text>
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
                  <Text type="secondary" style={{ fontSize: 12 }}>等 M4 反写阶段把系统真源推过去</Text>
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
          const archiveNorm = normalizeSpecText(archive)
          const shipmentNorm = normalizeSpecText(shipment)
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
                  <div style={{ whiteSpace: 'normal', wordBreak: 'break-word' }}>{shipment}</div>
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

  const tabProcess = sku ? (
    <Space direction="vertical" size={12} style={{ width: '100%' }}>
      <Alert
        type="info"
        showIcon
        message="工艺说明 (production_process)"
        description={
          <div style={{ lineHeight: 1.7 }}>
            这是系统内运营/生产侧维护的"可执行工艺说明"。
            <br />
            保存后会立即落本系统库 <Text code>sku_master.production_process</Text>，
            <b>不会立即反写 ERP</b> — ERP 反写走"反写到 ERP"按钮 (M4 模块, 待实现)。
          </div>
        }
      />
      <Card size="small" title="编辑工艺说明">
        <Space direction="vertical" style={{ width: '100%' }}>
          <TextArea
            value={processDraft}
            onChange={(e) => setProcessDraft(e.target.value)}
            rows={6}
            placeholder="例: 高频热压裁边 / 数码印 / 双面贴合..."
            showCount
            maxLength={2000}
          />
          <Space>
            <Button
              type="primary"
              loading={saveProcessMutation.isPending}
              onClick={() => saveProcessMutation.mutate(processDraft)}
              disabled={processDraft === (sku.production_process ?? '')}
            >
              保存
            </Button>
            <Button
              onClick={() => setProcessDraft(String(sku.production_process ?? ''))}
              disabled={processDraft === (sku.production_process ?? '')}
            >
              撤销修改
            </Button>
            {processDraft !== (sku.production_process ?? '') ? (
              <Text type="warning" style={{ fontSize: 12 }}>有未保存修改</Text>
            ) : null}
          </Space>
        </Space>
      </Card>
      <Card size="small" title="当前值 (服务器)">
        <Paragraph style={{ whiteSpace: 'pre-wrap', margin: 0 }}>
          {sku.production_process || <Text type="secondary">(空)</Text>}
        </Paragraph>
      </Card>
    </Space>
  ) : null

  const tabFlags = sku ? (
    <Space direction="vertical" size={12} style={{ width: '100%' }}>
      <Alert
        type="info"
        showIcon
        message="规格标记 (metadata.erp.sku_flag)"
        description={
          <div style={{ lineHeight: 1.7 }}>
            多值标签，用于业务分类 (如 "爆款" / "新品" / "清仓")。本地为真源，
            <b>反写到 ERP "规格标记" 字段</b> (M4 待实现)。
            <br />
            <Text type="secondary" style={{ fontSize: 12 }}>
              当前 MVP 自由输入；标签字典化 (统一颜色/拼写) 待下一轮 P3 实现。
            </Text>
          </div>
        }
      />
      <Card size="small" title="本地标签 (真源, 反写源)">
        <Space wrap>
          {currentFlags.length === 0 ? <Text type="secondary">(无标签)</Text> : null}
          {currentFlags.map((tag) => (
            <Tag
              key={tag}
              color="purple"
              closable
              onClose={(e) => {
                e.preventDefault()
                removeFlagMutation.mutate(tag)
              }}
              style={{ fontSize: 13, padding: '2px 8px' }}
            >
              {tag}
            </Tag>
          ))}
        </Space>
        <div style={{ marginTop: 12 }}>
          <Space.Compact style={{ width: '100%', maxWidth: 400 }}>
            <Input
              value={flagDraft}
              onChange={(e) => setFlagDraft(e.target.value)}
              onPressEnter={() => flagDraft.trim() && addFlagMutation.mutate(flagDraft)}
              placeholder="新标签 (回车添加)"
              disabled={addFlagMutation.isPending}
            />
            <Button
              type="primary"
              onClick={() => addFlagMutation.mutate(flagDraft)}
              loading={addFlagMutation.isPending}
              disabled={!flagDraft.trim()}
            >
              添加
            </Button>
          </Space.Compact>
        </div>
      </Card>
      {syncedFlags.length > 0 ? (
        <Card size="small" title="ERP 当前值 (影子, 同步拉回, 不覆盖本地)">
          <Space wrap>
            {syncedFlags.map((tag) => (
              <Tag key={tag} color="default" style={{ fontSize: 12 }}>
                {tag}
              </Tag>
            ))}
          </Space>
          <div style={{ marginTop: 8 }}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              来自 metadata.erp.sku_flag_synced — 每日 03:30 同步拉回。冲突时以本地为准。
            </Text>
          </div>
        </Card>
      ) : null}
    </Space>
  ) : null

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

  const tabWriteback = (
    <Alert
      type="warning"
      showIcon
      message="反写历史 — 待 M4 模块实现"
      description={
        <div style={{ lineHeight: 1.7 }}>
          本 Tab 将显示该 SKU 的 ERP 反写历史 (何时反写, 反写哪些字段, 成功/失败, payload)。
          <br />
          数据源: <Text code>metadata.erp.*_writeback</Text> + 独立 <Text code>erp_writeback_log</Text> 表。
          <br />
          反写按钮 (单条 / 批量 / Excel 导出) 同样在 M4 实现。
        </div>
      }
    />
  )

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
      title={sku ? `商品档案详情 — ${sku.erp_sku_barcode || '(无条码)'}` : '商品档案详情'}
      open={open}
      width={1080}
      onClose={onClose}
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
            { key: 'process', label: '工艺', children: tabProcess },
            { key: 'flags', label: '规格标记', children: tabFlags },
            { key: 'shops', label: `店铺映射 (${shopsQuery.data?.shop_skus?.length ?? 0})`, children: tabShops },
            { key: 'writeback', label: '反写历史', children: tabWriteback },
            { key: 'raw', label: '原始 metadata', children: tabRawMeta },
          ]}
        />
      )}
    </Drawer>
  )
}
