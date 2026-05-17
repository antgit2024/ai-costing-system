import { Button, Card, Col, Form, Image, Input, Modal, Radio, Row, Select, Space, Table, Tag, Tooltip, Typography, message } from 'antd'
import InfoCircleOutlined from '@ant-design/icons/lib/icons/InfoCircleOutlined'
import EditOutlined from '@ant-design/icons/lib/icons/EditOutlined'
import type { ColumnsType } from 'antd/es/table'
import { useEffect, useMemo, useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'

import { fetchSkuMaster, fetchTripleTagOverview } from '@/services/planner'
import type { SkuMaster } from '@/types/planner'
import { formatBeijingTime } from '@/utils/beijingTime'
import { IMAGE_FALLBACK_SVG, pickRowImageUrl } from '@/utils/imageUrl'
import {
  TargetPickerBrowserButton,
  renderTargetSelectionTags,
} from '@/components/common/TargetPicker'
import type { TargetSelection } from '@/components/common/TargetPicker'
import ProductInfoDetailDrawer from '@/components/costing/ProductInfoDetailDrawer'
import { PENDING_FIELD_UPDATE_SESSION_KEY, type PendingFieldUpdate } from '@/components/sku-master/FieldUpdateWorkbenchTab'
import { computeTripleTagState, describeConflict, TAG_COLORS } from '@/utils/skuMasterTagState'
import { normalizeSpecForCompare as normalizeSpecForCompareImpl, prettifyDisplaySpec } from '@/utils/specNormalize'

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

// 规格比对用 normalizeSpecForCompare (utils/specNormalize.ts),
// 与后端 normalize_for_compare 保持同语义 — 比 normalize_tx_spec_text 更激进, 把空格也视为分隔符.
const normalizeSpecForCompare = (v: unknown): string => normalizeSpecForCompareImpl(v)

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
  // 跟 sku-master 候选列表对齐: 包含/排除关键词 + 范围 (规格 / 商品名). 用户填了 → 直接落到 list API,
  // 也会跟着 sessionStorage 同步到 商品关联 (FieldUpdateWorkbenchTab 已支持 include_terms/exclude_terms/match_scope).
  const [includeTerms, setIncludeTerms] = useState<string>('')
  const [excludeTerms, setExcludeTerms] = useState<string>('')
  const [matchScope, setMatchScope] = useState<'spec' | 'name' | 'spec_or_name'>('spec_or_name')
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

  const navigate = useNavigate()

  const [detailOpenId, setDetailOpenId] = useState<string | null>(null)

  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([])

  // 跨页"按筛选执行"模式: false=仅勾选的; true=按当前筛选所有匹配 (跳过去 sku-master 一键跑完)
  const [batchByFilterMode, setBatchByFilterMode] = useState<boolean>(false)

  const [batchModalOpen, setBatchModalOpen] = useState<boolean>(false)
  const [batchForm] = Form.useForm<{
    field_name: 'production_process' | 'metadata.erp.sku_flag'
    mode: 'set' | 'append_unique' | 'remove'
    value_text: string
  }>()

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

  const overviewQuery = useQuery({
    queryKey: ['product-info', 'triple-tag-overview', channel],
    queryFn: () => fetchTripleTagOverview({ channel: channel || undefined }),
    staleTime: 60_000, // 1 分钟内不重新拉, 切筛选会重新拉
  })

  const listQuery = useQuery({
    queryKey: [
      'product-info',
      'list',
      page,
      pageSize,
      search,
      includeTerms,
      excludeTerms,
      matchScope,
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
        include_terms: includeTerms || undefined,
        exclude_terms: excludeTerms || undefined,
        match_scope: matchScope,
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
          <Tooltip
            title={(
              <div style={{ lineHeight: 1.7, maxWidth: 380 }}>
                <div style={{ fontWeight: 600, marginBottom: 4 }}>模型编码 — 两行布局</div>
                <div><b>第 1 行</b>: 已绑定的标准模型 / 套装的可读描述</div>
                <div style={{ marginLeft: 10 }}>例: OZU 直喷切割垫类 科技皮(OZU-004) / B-DB9EAE</div>
                <div style={{ marginTop: 4 }}><b>第 2 行</b>: 模型编码三路来源 (真源 / 输入 / ERP 镜像)</div>
                <div style={{ marginLeft: 10 }}><b>🅂 系统</b> (蓝/紫) — 我们权威识别的标准模型变体, 真源</div>
                <div style={{ marginLeft: 10 }}><b>🅑 商家</b> (绿=干净 / 橙=历史脏) — 网店原值 shop_spec_code</div>
                <div style={{ marginLeft: 10 }}><b>🅔 ERP</b> (绿=已反写 / 红=不一致 / 灰=待反写) — ERP outSkuCode</div>
                <div style={{ marginTop: 6, color: '#999', fontSize: 12 }}>
                  数据流: 商家 → 系统 → ERP. 系统标签是真源, ERP 不能反向覆盖.
                </div>
              </div>
            )}
          >
            <span>
              模型编码{' '}
              <Text type="secondary" style={{ fontSize: 11 }}>ⓘ</Text>
            </span>
          </Tooltip>
        ),
        key: 'triple_tag',
        width: 360,
        render: (_v, row: any) => {
          const s = computeTripleTagState(row)
          // 第 1 行: "已绑定" 的可读描述 (复用抽屉「已绑定」字段同源数据)
          const boundLine = (() => {
            const modelCode = safeString(row?.bound_model_code).trim()
            const modelName = safeString(row?.bound_model_name).trim()
            const variantLabel = safeString(row?.bound_variant_label).trim()
            const bundleCode = safeString(row?.bundle_template_code).trim()
            const bundleSelector = safeString(row?.bundle_preset_selector).trim()
            if (modelCode) {
              return (
                <Space size={4} wrap style={{ fontSize: 12, lineHeight: 1.3 }}>
                  <Tag color="blue" style={{ margin: 0 }}>{modelCode}</Tag>
                  {modelName ? <Text type="secondary">{modelName}</Text> : null}
                  {variantLabel ? <Tag color="purple" style={{ margin: 0 }}>{variantLabel}</Tag> : null}
                </Space>
              )
            }
            if (bundleCode) {
              return (
                <Tag color="purple" style={{ margin: 0, fontSize: 12 }}>
                  B-{bundleCode}{bundleSelector || ''}
                </Tag>
              )
            }
            return <Text type="secondary" style={{ fontSize: 12 }}>未关联</Text>
          })()

          const sysTag = (() => {
            if (s.sys.kind === 'matched') {
              const display = s.sys.variantCode && s.sys.variantCode !== s.sys.modelCode ? s.sys.variantCode : s.sys.modelCode
              return (
                <Tooltip title={`系统标签 (真源): 已绑定标准模型 ${s.sys.modelCode}${s.sys.modelName ? ' / ' + s.sys.modelName : ''}${s.sys.variantCode ? '; 变体: ' + s.sys.variantCode : ''}`}>
                  <Tag color={TAG_COLORS.sys_matched} style={{ margin: 0, fontSize: 11 }}>系 {display}</Tag>
                </Tooltip>
              )
            }
            if (s.sys.kind === 'bundle') {
              const label = `B-${s.sys.bundleCode}${s.sys.presetSelector || ''}`
              return (
                <Tooltip title={`系统标签 (真源): 已绑定套装 ${label}${s.sys.bundleName ? ' / ' + s.sys.bundleName : ''}`}>
                  <Tag color={TAG_COLORS.sys_bundle} style={{ margin: 0, fontSize: 11 }}>系 {label}</Tag>
                </Tooltip>
              )
            }
            return (
              <Tooltip title="系统标签: 未匹配到标准模型/套装. 是真源的缺口, 需要去商品关联做绑定.">
                <Tag color={TAG_COLORS.sys_unmatched} style={{ margin: 0, fontSize: 11 }}>系 未匹配</Tag>
              </Tooltip>
            )
          })()

          const shopTag = (() => {
            if (s.shop.kind === 'empty') {
              return (
                <Tooltip title="商家标签: 网店未填商家编码. 旧 SKU 居多, 新上架的会强制按规范填.">
                  <Tag color={TAG_COLORS.shop_empty} style={{ margin: 0, fontSize: 11 }}>商 —</Tag>
                </Tooltip>
              )
            }
            if (s.shop.kind === 'clean') {
              const tip = `商家标签 (干净): 网店端按规范录入的标准变体码${s.shop.rawIfChanged ? '\\n归一化前原值: ' + s.shop.rawIfChanged : ''}`
              return (
                <Tooltip title={tip.split('\\n').map((line, i) => <div key={i}>{line}</div>)}>
                  <Tag color={TAG_COLORS.shop_clean} style={{ margin: 0, fontSize: 11 }}>商 {s.shop.value}</Tag>
                </Tooltip>
              )
            }
            return (
              <Tooltip
                title={(
                  <div style={{ lineHeight: 1.7, maxWidth: 320 }}>
                    <div><b>商家标签: 未识别</b> — 网店历史值, 不符合标准变体码格式</div>
                    <div style={{ marginTop: 4, color: '#ccc' }}>值: {s.shop.value}{s.shop.rawIfChanged ? ` (raw: ${s.shop.rawIfChanged})` : ''}</div>
                    <div style={{ marginTop: 4 }}>详情/手修请打开抽屉的「三标签对账」面板</div>
                  </div>
                )}
              >
                <Tag color={TAG_COLORS.shop_dirty} style={{ margin: 0, fontSize: 11 }}>商 未识别</Tag>
              </Tooltip>
            )
          })()

          const erpTag = (() => {
            if (s.erp.kind === 'waiting') {
              return (
                <Tooltip title="ERP 标签: 待反写. ERP 那边的 outSkuCode 字段还是空, 等 M4 反写阶段把系统真源推过去.">
                  <Tag color={TAG_COLORS.erp_waiting} style={{ margin: 0, fontSize: 11 }}>ERP —</Tag>
                </Tooltip>
              )
            }
            if (s.erp.kind === 'synced') {
              return (
                <Tooltip title={`ERP 标签: 已反写. ERP 端 outSkuCode = ${s.erp.value}, 跟系统真源一致. 工厂可按这个值查工艺/排产/采购.`}>
                  <Tag color={TAG_COLORS.erp_synced} style={{ margin: 0, fontSize: 11 }}>ERP ✓</Tag>
                </Tooltip>
              )
            }
            return (
              <Tooltip title={`⚠ ERP 标签: 不一致! ERP 端 outSkuCode = ${s.erp.erpValue}, 但系统真源是 ${s.erp.sysExpected}. 可能是 ERP 端有人手改了, 或本次重新绑定后未触发反写. 请人工核对.`}>
                <Tag color={TAG_COLORS.erp_mismatch} style={{ margin: 0, fontSize: 11 }}>ERP ≠</Tag>
              </Tooltip>
            )
          })()

          const conflictDesc = describeConflict(s.conflict)
          const conflictColor =
            s.conflict.kind === 'shop_model_diff'
              ? '#cf1322' // 深红, 高风险
              : s.conflict.kind === 'shop_variant_diff'
                ? '#fa541c' // 橙红, 中风险
                : s.conflict.kind === 'erp_diff'
                  ? '#d4380d' // 红, ERP 端值偏离
                  : null

          return (
            <Space direction="vertical" size={2} style={{ width: '100%' }}>
              {boundLine}
              <Space wrap size={4} align="center">
                {sysTag}
                {shopTag}
                {erpTag}
                {conflictDesc ? (
                  <Tooltip
                    title={(
                      <div style={{ lineHeight: 1.7, maxWidth: 360 }}>
                        <div style={{ fontWeight: 600, marginBottom: 4 }}>{conflictDesc.title}</div>
                        <div>{conflictDesc.detail}</div>
                        <div style={{ marginTop: 6, color: '#ccc', fontSize: 12 }}>点击右侧「查看」打开抽屉, 在「三标签对账」面板里核对处理</div>
                      </div>
                    )}
                  >
                    <span
                      style={{
                        color: conflictColor!,
                        fontWeight: 700,
                        fontSize: 14,
                        cursor: 'help',
                        marginLeft: 2,
                      }}
                    >
                      ⚠
                    </span>
                  </Tooltip>
                ) : null}
              </Space>
            </Space>
          )
        },
      },
      // 「分类」「店铺数」已移到行抽屉的"基础"区, 列表不再展示.
      // 「识别依据」「规格标记」「操作」列在下方按用户要求重新组织顺序:
      //   模型编码 → 规格(档案/发货) → 识别依据 → 解析尺寸 → 状态 → 规格标记 → 操作 → 更新时间
      {
        title: (
          <Tooltip title="档案 = 商品规格(网店) spec_text; 发货 = last_shipment_spec_text. 发货展示时已剥天猫属性标签前缀, hover 可看原文. 两边归一化后仍不同, 显示红色「规格不一致」.">
            <span>
              规格 (档案 / 发货){' '}
              <Text type="secondary" style={{ fontSize: 11 }}>
                ⓘ
              </Text>
            </span>
          </Tooltip>
        ),
        key: 'spec_combined',
        width: 560,
        render: (_v, row: any) => {
          const shop = safeString(row?.spec_text).trim()
          const ship = safeString(row?.last_shipment_spec_text).trim()
          const shipPretty = ship ? prettifyDisplaySpec(ship) : ''
          const beautified = !!ship && shipPretty !== ship
          const mismatch = !!shop && !!ship && normalizeSpecForCompare(ship) !== normalizeSpecForCompare(shop)
          // 两行布局: 档案 / 发货. 任一为空就只显示有的那行.
          return (
            <Space direction="vertical" size={2} style={{ width: '100%' }}>
              {shop ? (
                <div style={{ display: 'flex', gap: 6, lineHeight: 1.3 }}>
                  <Text type="secondary" style={{ flexShrink: 0, fontSize: 12 }}>档案:</Text>
                  <div style={{ whiteSpace: 'normal', wordBreak: 'break-word' }}>{shop}</div>
                </div>
              ) : null}
              {ship ? (
                <div style={{ display: 'flex', gap: 6, lineHeight: 1.3, alignItems: 'flex-start' }}>
                  <Text type="secondary" style={{ flexShrink: 0, fontSize: 12 }}>发货:</Text>
                  <div style={{ whiteSpace: 'normal', wordBreak: 'break-word', flex: 1 }}>
                    {beautified ? (
                      <Tooltip
                        title={
                          <div style={{ maxWidth: 560, lineHeight: 1.6 }}>
                            <div style={{ color: '#ccc', fontSize: 12, marginBottom: 4 }}>显示已剥前缀, 原文如下:</div>
                            <div>{ship}</div>
                          </div>
                        }
                      >
                        <span style={{ cursor: 'help' }}>{shipPretty}</span>
                      </Tooltip>
                    ) : (
                      shipPretty
                    )}
                    {mismatch ? (
                      <Tooltip
                        title={
                          <div style={{ maxWidth: 560 }}>
                            <div>
                              <b>档案规格 (网店)</b>: {shop}
                            </div>
                            <div style={{ marginTop: 6 }}>
                              <b>最后发货规格 (原文)</b>: {ship}
                            </div>
                            <div style={{ marginTop: 6, color: '#ccc' }}>
                              归一化后两边仍不同, 说明档案规格 与实际发货规格 有真实差异 (尺寸/材质/颜色等).
                              系统会以「最后发货规格」为识别真源. 详见行抽屉的「规格对照」区.
                            </div>
                          </div>
                        }
                      >
                        <Tag color="red" style={{ cursor: 'help', marginLeft: 6 }}>
                          规格不一致
                        </Tag>
                      </Tooltip>
                    ) : null}
                  </div>
                </div>
              ) : null}
              {!shop && !ship ? <Text type="secondary">—</Text> : null}
            </Space>
          )
        },
      },
      {
        title: (
          <Tooltip title="系统标签 (左侧蓝色) 是怎么得出来的 — 5 种识别依据按优先级排:&#10;1) 商家编码直锁 (P0, 最可靠) - shop_spec_code 抽出 KB8-001 → 100% 锁定&#10;2) 关键词 命中变体 (P1) - 规格命中 recognition_keywords + 变体级 conditions 推 variant&#10;3) 关键词 仅锁模型 (P1') - 只到 KB8, 变体待定&#10;4) 套装模板 (P2) - bundle_template_id 强绑, 独立通道&#10;5) 未识别 - 都没命中, 需要去「商品关联」做绑定">
            <span>
              识别依据{' '}
              <Text type="secondary" style={{ fontSize: 11 }}>
                ⓘ
              </Text>
            </span>
          </Tooltip>
        ),
        key: 'recognition_source',
        width: 200,
        render: (_v, row: any) => {
          const src = (row?.recognition_source ?? 'none') as
            | 'merchant_code'
            | 'keyword_variant'
            | 'keyword_model_only'
            | 'bundle'
            | 'none'
          const inputSrc = row?.recognition_input_source as 'shipment' | 'archive' | null | undefined
          const variant = safeString(row?.bound_variant_code).trim().toUpperCase()
          const modelCode = safeString(row?.bound_model_code).trim().toUpperCase()
          const bundleCode = safeString(row?.bundle_template_code).trim().toUpperCase()

          const defs = {
            merchant_code: {
              color: 'green',
              icon: '🟢',
              text: '商家编码',
              value: variant || modelCode,
              hint: '从 ERP 网店规格编码字段抽出 → 直接锁定',
            },
            keyword_variant: {
              color: 'blue',
              icon: '🔵',
              text: '关键词',
              value: variant || modelCode,
              hint: '命中标准模型识别关键词 + 变体级条件',
            },
            keyword_model_only: {
              color: 'cyan',
              icon: '🔷',
              text: '关键词',
              value: `${modelCode} (变体待定)`,
              hint: '只锁到模型, 未识别到具体变体',
            },
            bundle: {
              color: 'purple',
              icon: '🟣',
              text: '套装',
              value: bundleCode || '—',
              hint: '套装模板强绑, 独立通道',
            },
            none: {
              color: 'default',
              icon: '⚪',
              text: '未识别',
              value: '',
              hint: '请到「商品关联」做绑定',
            },
          }
          const def = defs[src] || defs.none
          const inputLabel =
            inputSrc === 'shipment'
              ? '基于最后发货规格'
              : inputSrc === 'archive'
                ? '基于档案规格 (未发过货)'
                : null
          return (
            <Tooltip
              title={
                <div style={{ maxWidth: 360, lineHeight: 1.7 }}>
                  <div style={{ fontWeight: 600, marginBottom: 4 }}>
                    {def.icon} {def.text}
                    {def.value ? ` ${def.value}` : ''}
                  </div>
                  <div>{def.hint}</div>
                  {inputLabel ? (
                    <div style={{ marginTop: 6, color: '#ccc', fontSize: 12 }}>{inputLabel}</div>
                  ) : null}
                </div>
              }
            >
              <Space direction="vertical" size={0} style={{ cursor: 'help' }}>
                <Tag color={def.color} style={{ margin: 0 }}>
                  {def.icon} {def.text}
                  {def.value ? ` ${def.value}` : ''}
                </Tag>
                {inputLabel ? (
                  <Text type="secondary" style={{ fontSize: 10, marginTop: 2 }}>
                    {inputSrc === 'archive' ? '⚠ 未发过货' : '✓ 来自发货'}
                  </Text>
                ) : null}
              </Space>
            </Tooltip>
          )
        },
      },
      {
        title: (
          <Tooltip title="把「最后发货规格」(优先) 或「商品规格(网店)」(回退) 喂给规格解析器后, 抽出的结构化宽×高. 解析不出时显示「未解析」(如定制尺寸 / 联系客服).">
            <span>
              解析尺寸{' '}
              <Text type="secondary" style={{ fontSize: 11 }}>
                ⓘ
              </Text>
            </span>
          </Tooltip>
        ),
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
      // 「预解析TOKEN」已从列表移除, 详情见行抽屉的「规格解析」区 (debug 用途, 运营无需常看).
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
        title: '操作',
        key: 'actions',
        width: 130,
        fixed: 'right',
        render: (_v, row: any) => (
          <Space size={4}>
            <Button
              size="small"
              type="link"
              onClick={(e) => {
                e.stopPropagation()
                setDetailOpenId(String(row.id))
              }}
            >
              查看
            </Button>
            <Tooltip title="把本地字段 (生产工艺 / 规格标记 / 模型编码 / 属性规格) 推送到 ERP 货品档案. M6 反写模块开发中.">
              <Button size="small" type="link" disabled>
                反写
              </Button>
            </Tooltip>
          </Space>
        ),
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
                    <b>定位</b>：商品维护主战场。三标签 (系统/商家/ERP) 是模型编码的三路来源，
                    系统标签是真源 (bound_variant_code), 商家是输入材料 (历史脏认了, 新上架按规范填),
                    ERP 是反写后给工厂用的下游镜像。
                  </div>
                  <div style={{ marginTop: 6 }}>
                    <b>数据流</b>: 商家 → 系统 → ERP. 严禁 ERP 反推系统 (那样会让我们系统失去权威性)。
                  </div>
                </div>
              }
            >
              <InfoCircleOutlined style={{ color: '#999' }} />
            </Tooltip>
          </Space>
        </div>

        {(() => {
          const ov = overviewQuery.data
          if (!ov) {
            return (
              <Card size="small" loading={overviewQuery.isFetching} bodyStyle={{ padding: '10px 16px' }}>
                <Text type="secondary">指标加载中…</Text>
              </Card>
            )
          }
          const pct = (n: number) => (ov.total > 0 ? ((100 * n) / ov.total).toFixed(1) : '0')
          const Block: React.FC<{ label: string; value: number; sub?: string; color: string; tip: string }> = ({ label, value, sub, color, tip }) => (
            <Tooltip title={tip}>
              <div style={{ flex: '1 1 0', minWidth: 130, padding: '6px 10px', borderLeft: `3px solid ${color}` }}>
                <div style={{ fontSize: 11, color: '#999' }}>{label}</div>
                <div style={{ fontSize: 18, fontWeight: 600, color, lineHeight: 1.2 }}>
                  {value.toLocaleString()}
                  {sub ? <span style={{ fontSize: 11, color: '#999', marginLeft: 4, fontWeight: 400 }}>{sub}</span> : null}
                </div>
              </div>
            </Tooltip>
          )
          return (
            <Card size="small" bodyStyle={{ padding: '8px 12px' }}>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, alignItems: 'stretch' }}>
                <Block
                  label="全库总数"
                  value={ov.total}
                  color="#666"
                  tip="sku_master 表 is_archived=false 的总条数 (不含归档/删除)"
                />
                <Block
                  label="🅂 系统标签 已绑标模"
                  value={ov.sys_bound}
                  sub={`${pct(ov.sys_bound)}%`}
                  color="#1890ff"
                  tip="已绑定到 standard_models 的 SKU 数. 这是真源, 也是 M4 反写 ERP 的真正目标量."
                />
                <Block
                  label="🅑 商家标签 干净 (KB8-001)"
                  value={ov.shop_clean}
                  sub={`${pct(ov.shop_clean)}%`}
                  color="#52c41a"
                  tip="shop_spec_code 符合标准变体码格式 (^[A-Z0-9]{3}-[A-Z0-9]{2,8}). 新上架按规范填的才会落到这里, 极少."
                />
                <Block
                  label="🅑 商家标签 未识别"
                  value={ov.shop_dirty}
                  sub={`${pct(ov.shop_dirty)}%`}
                  color="#faad14"
                  tip="shop_spec_code 有值但不符合规范 (Q24091001 这种历史款号), 我们识别不出标准变体码. 历史几十万存量, 不强求人工梳理, 进抽屉可手修."
                />
                <Block
                  label="🅔 ERP 标签 已反写"
                  value={ov.erp_synced}
                  sub={`${pct(ov.erp_synced)}%`}
                  color="#52c41a"
                  tip="out_sku_code 非空, 表示已经把系统真源反推到了 ERP. M4 阶段会大量增加."
                />
                <Block
                  label="🚀 待反写 ERP"
                  value={ov.ready_to_writeback}
                  sub={`${pct(ov.ready_to_writeback)}%`}
                  color="#722ed1"
                  tip="已绑标模 AND ERP 端为空 = M4 反写阶段一开就能立刻处理的量. 这是真正可以闭环的目标."
                />
              </div>
            </Card>
          )
        })()}

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
            <Col xs={24} lg={4}>
              <Tooltip title="包含关键词 (AND, 多词空格分隔). 与「按筛选维护字段」共用一套条件 → 跳转商品关联时一起带过去, 跨页落库.">
                <Input
                  allowClear
                  placeholder="包含关键词 (AND, 多词空格)"
                  value={includeTerms}
                  onChange={(e) => {
                    setIncludeTerms(e.target.value)
                    setPage(1)
                  }}
                />
              </Tooltip>
            </Col>
            <Col xs={24} lg={4}>
              <Tooltip title="排除关键词 (AND NOT). 命中即排除. 同样会同步到商品关联.">
                <Input
                  allowClear
                  placeholder="排除关键词 (AND NOT)"
                  value={excludeTerms}
                  onChange={(e) => {
                    setExcludeTerms(e.target.value)
                    setPage(1)
                  }}
                />
              </Tooltip>
            </Col>
            <Col xs={24} lg={3}>
              <Tooltip title="包含/排除关键词的匹配范围: 商品规格 (spec_text) / 商品名称 (product_name) / 两者. 小红书/京东等渠道 spec 常 写到 name 里, 用「两者」覆盖更全.">
                <Select
                  value={matchScope}
                  onChange={(v) => {
                    setMatchScope(v)
                    setPage(1)
                  }}
                  style={{ width: '100%' }}
                  options={[
                    { value: 'spec_or_name', label: '规格 + 商品名' },
                    { value: 'spec', label: '仅商品规格' },
                    { value: 'name', label: '仅商品名称' },
                  ]}
                />
              </Tooltip>
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

        <div style={{ marginTop: 4, marginBottom: 4, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
          <Space size={8} align="center" wrap>
            <Text type="secondary">
              当前页：{items.length} 条{total >= 0 ? `，全库共 ${total.toLocaleString()} 条` : ''}
            </Text>
            <Tooltip title="开启精确总数（compute_total=true）。商品档案是生产维护主战场，需要明确的『还有多少待维护』感知。如后续超过 100 万行性能下降，会切换到 pg_class.reltuples 近似估算。">
              <InfoCircleOutlined style={{ color: '#999' }} />
            </Tooltip>
            {selectedRowKeys.length > 0 ? (
              <Tag color="blue">已勾选 {selectedRowKeys.length} 条</Tag>
            ) : null}
          </Space>
          <Space size={6} wrap>
            <Tooltip title="勾选模式：勾选行 → 点'批量改' 只对勾选行生效；按筛选模式 → 跳到商品关联用'一键跑完'对当前筛选所有匹配（含未在本页的）执行">
              <Tag.CheckableTag
                checked={batchByFilterMode}
                onChange={(c) => setBatchByFilterMode(c)}
                style={{ fontSize: 12 }}
              >
                {batchByFilterMode ? '按筛选模式 (跨页)' : '勾选模式 (仅本页)'}
              </Tag.CheckableTag>
            </Tooltip>
            <Button
              icon={<EditOutlined />}
              type="primary"
              size="small"
              disabled={!batchByFilterMode && selectedRowKeys.length === 0}
              onClick={() => {
                batchForm.resetFields()
                setBatchModalOpen(true)
              }}
            >
              批量改字段
            </Button>
            <Tooltip title="清除勾选">
              {selectedRowKeys.length > 0 ? (
                <Button size="small" onClick={() => setSelectedRowKeys([])}>清除</Button>
              ) : null}
            </Tooltip>
          </Space>
        </div>

        <Table<SkuMaster>
          rowKey={(r) => String(r.id)}
          size="small"
          bordered
          scroll={{ x: 2400 }}
          loading={listQuery.isFetching}
          columns={columns}
          dataSource={items}
          rowSelection={{
            selectedRowKeys,
            onChange: (keys) => setSelectedRowKeys(keys),
            preserveSelectedRowKeys: true,
          }}
          // 行点击改为右侧操作列「查看」按钮触发, 避免误触 + 给「反写」按钮独立位置.
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

      <ProductInfoDetailDrawer
        skuId={detailOpenId}
        open={!!detailOpenId}
        onClose={() => setDetailOpenId(null)}
        onUpdated={() => listQuery.refetch()}
      />

      <Modal
        title={
          <span>
            批量改字段{' '}
            <Text type="secondary" style={{ fontSize: 12, fontWeight: 'normal' }}>
              将跳到「商品关联 / 字段维护」 Tab 执行
            </Text>
          </span>
        }
        open={batchModalOpen}
        onCancel={() => setBatchModalOpen(false)}
        okText="确认并跳转执行"
        cancelText="取消"
        onOk={async () => {
          try {
            const v = await batchForm.validateFields()
            const fieldName = v.field_name
            const mode = v.mode
            const raw = v.value_text ?? ''
            let newValue: unknown
            if (fieldName === 'production_process') {
              newValue = raw.trim() || null
            } else {
              // metadata.erp.sku_flag — 多值, 支持逗号/分号/换行/空格分隔
              const arr = raw
                .split(/[,;，；\n\t]+/)
                .map((s) => s.trim())
                .filter(Boolean)
              newValue = arr
              if (mode !== 'set' && arr.length === 0) {
                message.error('append_unique / remove 模式至少需要 1 个标签')
                return
              }
            }

            const pending: PendingFieldUpdate = {
              field_name: fieldName,
              new_value: newValue,
              mode,
              requested_by: 'products-info-batch',
              source: 'products-info',
              display_label: fieldName === 'production_process' ? '工艺说明' : '规格标记',
              timestamp: new Date().toLocaleString('zh-CN'),
            }
            if (batchByFilterMode) {
              // 跨页按筛选: 把当前筛选参数全部带过去
              // include_terms/exclude_terms/match_scope 是给跨页"按筛选"维护字段用的最强抓手 —
              // 商品关联那边 FieldUpdateWorkbenchTab 已支持这三个 (buildBaseRequest 会原样转发).
              pending.filters = {
                search: search || undefined,
                include_terms: includeTerms || undefined,
                exclude_terms: excludeTerms || undefined,
                match_scope: matchScope,
                channel,
                match_status: matchStatus,
                bound_state: targetFilters.bound_state,
                bound_model_id: targetFilters.bound_model_id,
                bundle_bound_state: targetFilters.bundle_bound_state,
                bundle_template_id: targetFilters.bundle_template_id,
                bundle_preset_selector: targetFilters.bundle_preset_selector,
              }
            } else {
              // 勾选模式: 显式 ID
              pending.sku_master_ids = selectedRowKeys.map((k) => String(k))
            }

            try {
              sessionStorage.setItem(PENDING_FIELD_UPDATE_SESSION_KEY, JSON.stringify(pending))
            } catch (e) {
              message.error('浏览器 sessionStorage 不可用, 无法跳转')
              return
            }

            setBatchModalOpen(false)
            message.success('参数已准备, 正在跳转到商品关联...')
            navigate('/costing/sku-master?workbenchTab=field_update&from=products-info')
          } catch {
            // form validation error
          }
        }}
        width={580}
      >
        <Form form={batchForm} layout="vertical" initialValues={{ field_name: 'production_process', mode: 'set' }}>
          <Form.Item label="目标范围">
            {batchByFilterMode ? (
              <Tag color="orange" style={{ fontSize: 13, padding: '4px 12px' }}>
                按当前筛选条件 (跨页, 所有匹配行)
              </Tag>
            ) : (
              <Tag color="blue" style={{ fontSize: 13, padding: '4px 12px' }}>
                已勾选 {selectedRowKeys.length} 条 (仅本页)
              </Tag>
            )}
          </Form.Item>
          <Form.Item name="field_name" label="要修改的字段" rules={[{ required: true }]}>
            <Radio.Group
              onChange={() => {
                // 切字段时重置模式 (production_process 只支持 set)
                batchForm.setFieldsValue({ mode: 'set' })
              }}
            >
              <Space direction="vertical">
                <Radio value="production_process">
                  <b>工艺说明</b> (production_process, 物理列, 仅 set 模式)
                </Radio>
                <Radio value="metadata.erp.sku_flag">
                  <b>规格标记</b> (metadata.erp.sku_flag, JSON 数组, 支持 set / append_unique / remove)
                </Radio>
              </Space>
            </Radio.Group>
          </Form.Item>
          <Form.Item dependencies={['field_name']} noStyle>
            {({ getFieldValue }) => {
              const fn = getFieldValue('field_name')
              if (fn === 'production_process') return null
              return (
                <Form.Item name="mode" label="操作模式" rules={[{ required: true }]}>
                  <Radio.Group>
                    <Radio value="set">set (整组覆盖)</Radio>
                    <Radio value="append_unique">append_unique (追加去重)</Radio>
                    <Radio value="remove">remove (移除指定项)</Radio>
                  </Radio.Group>
                </Form.Item>
              )
            }}
          </Form.Item>
          <Form.Item dependencies={['field_name', 'mode']} noStyle>
            {({ getFieldValue }) => {
              const fn = getFieldValue('field_name')
              if (fn === 'production_process') {
                return (
                  <Form.Item name="value_text" label="新工艺说明" rules={[{ required: false }]}>
                    <Input.TextArea rows={4} placeholder="留空 = 清空; 例: 高频热压 / 数码印 / 双面贴合" />
                  </Form.Item>
                )
              }
              const mode = getFieldValue('mode')
              return (
                <Form.Item
                  name="value_text"
                  label={`${mode === 'set' ? '替换为' : mode === 'append_unique' ? '追加这些标签' : '移除这些标签'} (多个用逗号 / 分号 / 换行分隔)`}
                  rules={[{ required: mode !== 'set' }]}
                >
                  <Input.TextArea rows={3} placeholder="例: 爆款, 新品, 春季" />
                </Form.Item>
              )
            }}
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

