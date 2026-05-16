import { Card, Col, Image, Input, Row, Select, Space, Table, Tag, Tooltip, Typography } from 'antd'
import InfoCircleOutlined from '@ant-design/icons/lib/icons/InfoCircleOutlined'
import ShopOutlined from '@ant-design/icons/lib/icons/ShopOutlined'
import type { ColumnsType } from 'antd/es/table'
import { useEffect, useMemo, useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'

import { fetchSkuMaster } from '@/services/planner'
import type { SkuMaster } from '@/types/planner'
import { formatBeijingTime } from '@/utils/beijingTime'
import { IMAGE_FALLBACK_SVG, pickRowImageUrl } from '@/utils/imageUrl'
import {
  TargetPickerBrowserButton,
  renderTargetSelectionTags,
} from '@/components/common/TargetPicker'
import type { TargetSelection } from '@/components/common/TargetPicker'

const { Text, Title } = Typography

const DEFAULT_PAGE_SIZE = 100
const PAGE_SIZE_STORAGE_KEY = 'costing_product_info_page_size_v1'

const formatTime = (v?: string | null) => {
  return formatBeijingTime(v, 'YYYY-MM-DD HH:mm:ss')
}

const safeString = (v: unknown): string => {
  if (v === null || v === undefined) return ''
  return String(v)
}

const isFilled = (v: unknown): boolean => !!safeString(v).trim()

const normalizeSpecForCompare = (v: unknown): string => {
  const s = safeString(v).trim()
  if (!s) return ''
  return (
    s
      // unify whitespace
      .replace(/\s+/g, ' ')
      // unify common punctuation variants
      .replace(/；/g, ';')
      .replace(/：/g, ':')
      .replace(/，/g, ',')
      .replace(/（/g, '(')
      .replace(/）/g, ')')
      .trim()
  )
}

const tokensPreview = (tokens: any): string => {
  if (!Array.isArray(tokens) || tokens.length === 0) return '-'
  const parts = tokens
    .slice(0, 4)
    .map((t) => String(t ?? '').trim())
    .filter(Boolean)
  const more = tokens.length > 4 ? '…' : ''
  return parts.length ? `${parts.join(' / ')}${more}` : '-'
}

export default function ProductInfoPage() {
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(() => {
    try {
      const raw = localStorage.getItem(PAGE_SIZE_STORAGE_KEY)
      const n = raw ? Number(raw) : NaN
      if (!Number.isFinite(n) || n <= 0) return DEFAULT_PAGE_SIZE
      return Math.min(Math.max(Math.floor(n), 10), 500)
    } catch {
      return DEFAULT_PAGE_SIZE
    }
  })

  const [search, setSearch] = useState<string>('')
  const [channel, setChannel] = useState<string | undefined>(undefined)
  const [matchStatus, setMatchStatus] = useState<string | undefined>(undefined)

  // 绑定目标（标准模型 / 套装模板）— 统一通过浏览弹窗（target-picker-playground 模式 0）选择。
  // - 不选 → 不按目标筛选（target_kind=any）
  // - 选 model → bound_state=bound + bound_model_id
  // - 选 bundle → bundle_bound_state=bound + bundle_template_id + bundle_preset_selector
  const [pickedTarget, setPickedTarget] = useState<TargetSelection | null>(null)

  useEffect(() => {
    try {
      localStorage.setItem(PAGE_SIZE_STORAGE_KEY, String(pageSize))
    } catch {
      // ignore
    }
  }, [pageSize])

  // 派生后端筛选参数：把统一 TargetSelection 转成 list_sku_master 接受的扁平参数
  const targetFilters = useMemo(() => {
    if (!pickedTarget) {
      return {
        target_kind: 'any' as const,
        bound_state: 'all' as const,
        bound_model_id: undefined as string | undefined,
        bundle_bound_state: undefined as 'bound' | undefined,
        bundle_template_id: undefined as string | undefined,
        bundle_preset_selector: undefined as string | undefined,
      }
    }
    if (pickedTarget.kind === 'model') {
      return {
        target_kind: 'model' as const,
        bound_state: 'bound' as const,
        bound_model_id: pickedTarget.model_id,
        bundle_bound_state: undefined,
        bundle_template_id: undefined,
        bundle_preset_selector: undefined,
      }
    }
    return {
      target_kind: 'bundle' as const,
      bound_state: 'all' as const,
      bound_model_id: undefined,
      bundle_bound_state: 'bound' as const,
      bundle_template_id: pickedTarget.bundle_id,
      bundle_preset_selector: pickedTarget.preset_selector ?? undefined,
    }
  }, [pickedTarget])

  const listQuery = useQuery({
    queryKey: [
      'product-info',
      'list',
      page,
      pageSize,
      search,
      channel,
      matchStatus,
      targetFilters.target_kind,
      targetFilters.bound_state,
      targetFilters.bound_model_id,
      targetFilters.bundle_bound_state,
      targetFilters.bundle_template_id,
      targetFilters.bundle_preset_selector,
    ],
    queryFn: () =>
      fetchSkuMaster({
        page,
        page_size: pageSize,
        search: search || undefined,
        channel,
        match_status: matchStatus,
        target_kind: targetFilters.target_kind,
        bound_state: targetFilters.bound_state,
        bound_model_id: targetFilters.bound_model_id,
        bound_version_id: undefined,
        bundle_bound_state: targetFilters.bundle_bound_state,
        bundle_template_id: targetFilters.bundle_template_id,
        bundle_preset_selector: targetFilters.bundle_preset_selector,
        preparse_state: undefined,
        compute_total: true,
        include_shop_count: true,
      }),
    placeholderData: keepPreviousData,
  })

  const items = (listQuery.data?.items ?? []) as SkuMaster[]
  const total = Number((listQuery.data as any)?.total ?? -1)

  const columns: ColumnsType<SkuMaster> = useMemo(
    () => [
      {
        title: '主图',
        key: 'main_image',
        width: 64,
        fixed: 'left',
        render: (_v, row: any) => {
          // 缩略 96px (Retina 屏 44px 显示更清晰); 预览大图用 800px 重新拿
          const thumbUrl = pickRowImageUrl(row?.images_json, 96)
          const previewUrl = pickRowImageUrl(row?.images_json, 800)
          if (!thumbUrl) {
            return (
              <div
                style={{
                  width: 44,
                  height: 44,
                  background: 'rgba(0,0,0,0.04)',
                  borderRadius: 4,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                <Text type="secondary" style={{ fontSize: 10 }}>
                  无图
                </Text>
              </div>
            )
          }
          return (
            <Image
              src={thumbUrl}
              width={44}
              height={44}
              style={{ borderRadius: 4, objectFit: 'cover' }}
              fallback={IMAGE_FALLBACK_SVG}
              preview={{
                src: previewUrl,
                mask: <Text style={{ color: '#fff', fontSize: 11 }}>预览</Text>,
              }}
            />
          )
        },
      },
      {
        title: '货品条码（系统）',
        dataIndex: 'erp_sku_barcode',
        width: 170,
        fixed: 'left',
        render: (v) => <Text style={{ fontFamily: 'monospace' }}>{safeString(v).trim() || '-'}</Text>,
      },
      {
        title: '货品名称',
        dataIndex: 'product_name',
        width: 200,
        ellipsis: true,
        render: (v) => safeString(v) || <Text type="secondary">—</Text>,
      },
      {
        title: (
          <Tooltip title="ERP 自定义字段「模型编码」(skuField1) 的系统侧规范值，从发货明细自动解析（如 KB8-001）。读 sku_master.shop_spec_code，反写时映射到 ERP outSkuCode。">
            <span>
              模型编码{' '}
              <Text type="secondary" style={{ fontSize: 11 }}>
                ⓘ
              </Text>
            </span>
          </Tooltip>
        ),
        dataIndex: 'shop_spec_code',
        width: 160,
        render: (v) => safeString(v) || <Text type="secondary">—</Text>,
      },
      {
        title: (
          <Tooltip title="ERP 货品档案的「外部编码」(outSkuCode)，反写目标字段。当前若为空，表示还未把「模型编码」反写到 ERP；下一轮 G1/H 反写后会回灌此列。">
            <span>
              ERP 外部编码{' '}
              <Text type="secondary" style={{ fontSize: 11 }}>
                ⓘ
              </Text>
            </span>
          </Tooltip>
        ),
        dataIndex: 'out_sku_code',
        width: 160,
        render: (v) => {
          const s = safeString(v).trim()
          if (!s) return <Tag color="default" style={{ fontSize: 11 }}>待反写</Tag>
          return <Text style={{ fontFamily: 'monospace' }}>{s}</Text>
        },
      },
      {
        title: '分类',
        key: 'erp_category',
        width: 130,
        render: (_v, row: any) => {
          const erp = (row?.metadata_json as any)?.erp ?? {}
          const cat = safeString(erp?.category).trim()
          return cat ? <Tag>{cat}</Tag> : <Text type="secondary">—</Text>
        },
      },
      {
        title: (
          <Tooltip title="ERP 货品档案里的「规格标记」(skuFlag) — 多值字段, 用于业务标签 / 分组. 来自 metadata.erp.sku_flag_synced">
            <span>
              规格标记{' '}
              <Text type="secondary" style={{ fontSize: 11 }}>
                ⓘ
              </Text>
            </span>
          </Tooltip>
        ),
        key: 'sku_flag',
        width: 200,
        render: (_v, row: any) => {
          const erp = (row?.metadata_json as any)?.erp ?? {}
          const flags = erp?.sku_flag_synced
          const arr = Array.isArray(flags) ? flags : flags ? [String(flags)] : []
          if (!arr.length) return <Text type="secondary">—</Text>
          return (
            <Space wrap size={[4, 4]}>
              {arr.slice(0, 4).map((f, i) => (
                <Tag key={i} color="purple" style={{ margin: 0 }}>
                  {String(f)}
                </Tag>
              ))}
              {arr.length > 4 ? <Text type="secondary">+{arr.length - 4}</Text> : null}
            </Space>
          )
        },
      },
      {
        title: (
          <Tooltip title="该商品在 shop_sku_mappings 里的店铺映射数 (一个 ERP 货品可能在多个店铺销售). 0 = 还未在任何店铺发过货. 详细映射见详情抽屉(待开发).">
            <span>
              店铺数{' '}
              <Text type="secondary" style={{ fontSize: 11 }}>
                ⓘ
              </Text>
            </span>
          </Tooltip>
        ),
        key: 'shop_count',
        width: 90,
        align: 'center' as const,
        render: (_v, row: any) => {
          const n = Number(row?.shop_count ?? 0)
          if (n === 0) return <Text type="secondary">—</Text>
          return (
            <Tag icon={<ShopOutlined />} color={n >= 3 ? 'green' : 'blue'}>
              {n} 店
            </Tag>
          )
        },
      },
      {
        title: '已绑定目标',
        key: 'bound_target',
        width: 320,
        render: (_v, row: any) => {
          const modelCode = safeString(row?.bound_model_code).trim()
          const modelName = safeString(row?.bound_model_name).trim()
          const hasModel = !!modelCode

          const meta = row?.metadata_json ?? {}
          const codeRaw = safeString(row?.bundle_template_code ?? meta?.bundle_template_code).trim()
          const selRaw = safeString(row?.bundle_preset_selector ?? meta?.bundle_preset_selector).trim().toUpperCase()
          const hasBundle = !!codeRaw

          if (!hasModel && !hasBundle) return <Tag>未关联</Tag>

          const normalize = (s: string) =>
            String(s || '')
              .trim()
              .toUpperCase()
              .replace(/^([BZ])-/, '')
              .replace(/[^A-Z0-9]/g, '')

          const bundleTag = (() => {
            if (!hasBundle) return null
            const base = normalize(codeRaw)
            const sel = normalize(selRaw)
            let displayBase = base
            if (sel && !displayBase.endsWith(sel)) displayBase = `${displayBase}${sel}`
            const label = `B-${displayBase}`
            const name = String(
              (row as any)?.bundle_template_name ?? (meta as any)?.bundle_template_name ?? '',
            ).trim()
            const text = name ? `${label} ${name}` : label
            return <Tag color="purple">{text}</Tag>
          })()

          return (
            <Space direction="vertical" size={2}>
              {hasModel ? (
                <span>
                  <Tag color="blue">{modelCode}</Tag>
                  {modelName ? <span style={{ color: '#666' }}> {modelName}</span> : null}
                </span>
              ) : null}
              {bundleTag}
            </Space>
          )
        },
      },
      {
        title: '商品规格（网店）',
        dataIndex: 'spec_text',
        width: 520,
        render: (v) => <div style={{ whiteSpace: 'normal', wordBreak: 'break-word', lineHeight: 1.2 }}>{safeString(v) || '-'}</div>,
      },
      {
        title: '用于解析的规格',
        dataIndex: 'last_shipment_spec_text',
        width: 360,
        render: (v, row: any) => {
          const ship = safeString(v).trim()
          const shop = safeString(row?.spec_text).trim()
          const text = ship || shop
          const fromFallback = !ship && !!shop
          const mismatch = !!ship && !!shop && normalizeSpecForCompare(ship) !== normalizeSpecForCompare(shop)
          return (
            <Space direction="vertical" size={2}>
              <div style={{ whiteSpace: 'normal', wordBreak: 'break-word', lineHeight: 1.2 }}>{text || '-'}</div>
              {fromFallback ? <Tag color="orange">回退：网店规格</Tag> : null}
              {mismatch ? (
                <Tooltip
                  title={
                    <div style={{ maxWidth: 560 }}>
                      <div>
                        <b>发货规格（用于解析）</b>：{ship}
                      </div>
                      <div style={{ marginTop: 6 }}>
                        <b>网店规格</b>：{shop}
                      </div>
                      <div style={{ marginTop: 6, color: 'var(--ant-color-text-secondary)' }}>
                        建议以“发货规格”为准；如网店规格长期不可信，可通过自动化/作业中心做批量修正或建立更稳定的模型编码锚点。
                      </div>
                    </div>
                  }
                >
                  <Tag color="red" style={{ cursor: 'help' }}>
                    规格不一致
                  </Tag>
                </Tooltip>
              ) : null}
            </Space>
          )
        },
      },
      {
        title: '预解析尺寸',
        dataIndex: 'preparse_dimensions',
        width: 160,
        render: (_v, row: any) => {
          const meta = row?.metadata_json ?? {}
          const dims = row?.preparse_dimensions ?? meta?.preparse_dimensions
          const w = dims?.width_cm ?? dims?.width ?? null
          const h = dims?.height_cm ?? dims?.height ?? null
          if (!isFilled(w) || !isFilled(h)) return <Tag>未解析</Tag>
          return <Tag color="green">宽{String(w)}×高{String(h)}cm</Tag>
        },
      },
      {
        title: '预解析TOKEN',
        dataIndex: 'preparse_tokens',
        width: 240,
        render: (_v, row: any) => {
          const meta = row?.metadata_json ?? {}
          const tokens = row?.preparse_tokens ?? meta?.preparse_tokens
          return <Text>{tokensPreview(tokens)}</Text>
        },
      },
      {
        title: '状态',
        key: 'status',
        width: 110,
        render: (_v, row: any) => {
          const tags: React.ReactNode[] = []
          if (row?.is_blocked) tags.push(<Tag key="b" color="red">停用</Tag>)
          if (row?.is_deleted_at_source) tags.push(<Tag key="d" color="default">ERP 已删除</Tag>)
          return tags.length ? <Space size={4}>{tags}</Space> : <Tag color="success">正常</Tag>
        },
      },
      { title: '更新时间', dataIndex: 'updated_at', width: 170, render: (v) => formatTime(v) },
    ],
    [],
  )

  return (
    <div style={{ padding: 16 }}>
      <Space direction="vertical" size={12} style={{ width: '100%' }}>
        <div>
          <Space align="center" size={8}>
            <Title level={4} style={{ margin: 0 }}>
              商品档案（ERP 视角，只读）
            </Title>
            <Tooltip
              title={
                <div style={{ maxWidth: 560 }}>
                  <div>
                    <b>定位</b>：以 ERP 货品 (erp_sku_barcode) 为主键的商品主档；
                    所有 ERP 字段 (分类 / 规格标记 / 主图 / 规格 / 物理参数) 已在「吉客云·货品档案 Excel 导入」铺底。
                  </div>
                  <div style={{ marginTop: 6 }}>
                    <b>多店铺</b>：「店铺数」一列取自 shop_sku_mappings (active),
                    一个 ERP 货品可在 N 个店铺销售；上面的「主渠道」筛选器只代表最后一次同步覆盖的渠道, 仅用于检索辅助。
                  </div>
                  <div style={{ marginTop: 6 }}>
                    <b>解析口径</b>：「用于解析的规格」= 发货规格优先 + 缺省回退网店规格 (spec_text)；预解析缓存请见「自动化 / 作业中心」。
                  </div>
                </div>
              }
            >
              <InfoCircleOutlined style={{ color: '#999' }} />
            </Tooltip>
          </Space>
        </div>

        <Card size="small">
          <Row gutter={[12, 12]}>
            <Col xs={24} lg={6}>
              <Input.Search
                allowClear
                placeholder="搜索：条码/模型编码/外部编码/规格/商品名"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                onSearch={() => setPage(1)}
              />
            </Col>
            <Col xs={24} lg={3}>
              <Select
                allowClear
                placeholder="主渠道（最后同步）"
                value={channel}
                onChange={(v) => {
                  setChannel(v)
                  setPage(1)
                }}
                style={{ width: '100%' }}
                options={[
                  { value: 'tmall', label: 'tmall' },
                  { value: 'douyin', label: 'douyin' },
                  { value: 'pdd', label: 'pdd' },
                  { value: 'jd', label: 'jd' },
                  { value: 'other', label: 'other' },
                ]}
              />
            </Col>
            <Col xs={24} lg={3}>
              <Select
                allowClear
                placeholder="关联状态"
                value={matchStatus}
                onChange={(v) => {
                  setMatchStatus(v)
                  setPage(1)
                }}
                style={{ width: '100%' }}
                options={[
                  { value: 'bound', label: '已关联' },
                  { value: 'unbound', label: '未关联' },
                  { value: 'diff', label: '规格差异' },
                ]}
              />
            </Col>
            <Col xs={24} lg={12}>
              <Space size={8} wrap style={{ width: '100%' }}>
                <Tooltip title="按已绑定的「标准模型 / 套装模板」筛选。点击按钮打开浏览弹窗（Tab 切换 + 一级展开二级），不知道叫什么也能浏览全候选；选完即筛。再次点击可改选或清除。">
                  <span>
                    <TargetPickerBrowserButton
                      value={pickedTarget}
                      onChange={(next) => {
                        setPickedTarget(next)
                        setPage(1)
                      }}
                      buttonProps={{ type: pickedTarget ? 'primary' : 'default' }}
                      placeholder="按绑定目标筛选（标准模型 / 套装模板）"
                    />
                  </span>
                </Tooltip>
                {pickedTarget ? (
                  <>
                    <Text type="secondary">已选：</Text>
                    {renderTargetSelectionTags(pickedTarget)}
                  </>
                ) : (
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    未筛选目标 — 显示全部商品（含未关联）
                  </Text>
                )}
              </Space>
            </Col>
          </Row>
        </Card>

        <div style={{ marginTop: 4, marginBottom: 4 }}>
          <Space size={8} align="center">
            <Text type="secondary">
              当前页：{items.length} 条{total >= 0 ? `，全库共 ${total.toLocaleString()} 条` : ''}
            </Text>
            <Tooltip title="开启精确总数（compute_total=true）。商品档案是生产维护主战场，需要明确的『还有多少待维护』感知。如后续超过 100 万行性能下降，会切换到 pg_class.reltuples 近似估算。">
              <InfoCircleOutlined style={{ color: '#999' }} />
            </Tooltip>
          </Space>
        </div>

        <Table<SkuMaster>
          rowKey={(r) => String(r.id)}
          size="small"
          bordered
          scroll={{ x: 2700 }}
          loading={listQuery.isFetching}
          columns={columns}
          dataSource={items}
          pagination={{
            current: page,
            pageSize,
            total: total >= 0 ? total : undefined,
            onChange: (p) => setPage(p),
            showSizeChanger: true,
            showQuickJumper: true,
            pageSizeOptions: [50, 100, 200, 500],
            onShowSizeChange: (_p, ps) => {
              setPage(1)
              setPageSize(ps)
            },
            showTotal: (t, range) => `第 ${range[0]}-${range[1]} 条，共 ${t.toLocaleString()} 条`,
          }}
          locale={{ emptyText: '暂无数据（先调整筛选条件）' }}
        />
      </Space>
    </div>
  )
}

