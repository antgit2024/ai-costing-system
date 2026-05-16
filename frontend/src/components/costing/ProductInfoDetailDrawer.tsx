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
    }
  }, [sku?.id, sku?.production_process])

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

  const tabBasic = sku ? (
    <Space direction="vertical" size={12} style={{ width: '100%' }}>
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
            <Descriptions.Item label="模型编码 (shop_spec_code)">
              <Text copyable={!!sku.shop_spec_code}>{sku.shop_spec_code || '-'}</Text>
            </Descriptions.Item>
            <Descriptions.Item label="ERP 外部编码 (out_sku_code)">
              {sku.out_sku_code ? (
                <Text copyable style={{ fontFamily: 'monospace' }}>{sku.out_sku_code}</Text>
              ) : (
                <Tag color="default">待反写</Tag>
              )}
            </Descriptions.Item>
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

      <Card size="small" title="规格信息">
        <Descriptions size="small" column={1}>
          <Descriptions.Item label="商品规格 (网店)">
            <div style={{ whiteSpace: 'normal' }}>{sku.spec_text || '-'}</div>
          </Descriptions.Item>
          <Descriptions.Item label="发货规格 (用于解析)">
            <div style={{ whiteSpace: 'normal' }}>{sku.last_shipment_spec_text || '-'}</div>
          </Descriptions.Item>
          <Descriptions.Item label="预解析尺寸">
            {(() => {
              const dims = (sku.preparse_dimensions ?? {}) as Record<string, unknown>
              const w = dims?.width_cm ?? dims?.width
              const h = dims?.height_cm ?? dims?.height
              if (!w || !h) return <Tag>未解析</Tag>
              return <Tag color="green">宽{String(w)}×高{String(h)}cm</Tag>
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
