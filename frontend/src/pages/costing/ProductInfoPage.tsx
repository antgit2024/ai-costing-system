import { Card, Col, Image, Input, Row, Select, Space, Table, Tag, Tooltip, Typography } from 'antd'
import InfoCircleOutlined from '@ant-design/icons/lib/icons/InfoCircleOutlined'
import ShopOutlined from '@ant-design/icons/lib/icons/ShopOutlined'
import type { ColumnsType } from 'antd/es/table'
import { useEffect, useMemo, useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'

import { fetchBundleTemplates, fetchPublishedStandardModels, fetchSkuMaster } from '@/services/planner'
import type { SkuMaster } from '@/types/planner'
import { formatBeijingTime } from '@/utils/beijingTime'
import { IMAGE_FALLBACK_SVG, pickRowImageUrl } from '@/utils/imageUrl'

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

  // “模型分类/一级/二级”：
  // - 目标类型：any/model/bundle
  // - 一级：模型/套装模板
  // - 二级：套装 selector（AA/AB...）
  const [targetKind, setTargetKind] = useState<'any' | 'model' | 'bundle'>('any')
  const [modelSearch, setModelSearch] = useState<string>('')
  const [boundModelId, setBoundModelId] = useState<string | undefined>(undefined)
  const [onlyPublishedVersion, setOnlyPublishedVersion] = useState<boolean>(false)
  const [bundleSearch, setBundleSearch] = useState<string>('')
  const [selectedBundleTemplateId, setSelectedBundleTemplateId] = useState<string | undefined>(undefined)
  const [selectedBundlePresetSelector, setSelectedBundlePresetSelector] = useState<string | undefined>(undefined)

  useEffect(() => {
    try {
      localStorage.setItem(PAGE_SIZE_STORAGE_KEY, String(pageSize))
    } catch {
      // ignore
    }
  }, [pageSize])

  useEffect(() => {
    // 切换目标类型时清理无效筛选，避免“看不见数据”的误解
    if (targetKind === 'model') {
      setSelectedBundleTemplateId(undefined)
      setSelectedBundlePresetSelector(undefined)
    } else if (targetKind === 'bundle') {
      setBoundModelId(undefined)
      setOnlyPublishedVersion(false)
    }
    setPage(1)
  }, [targetKind])

  const publishedModelsQuery = useQuery({
    queryKey: ['product-info', 'published-standard-models', modelSearch],
    queryFn: () => fetchPublishedStandardModels({ search: modelSearch || undefined, limit: 50 }),
    placeholderData: keepPreviousData,
  })

  const publishedModelById = useMemo(() => {
    const items = (publishedModelsQuery.data as any)?.items ?? []
    const m = new Map<string, any>()
    for (const it of items) {
      const id = String(it?.model_id ?? '').trim()
      if (!id) continue
      m.set(id, it)
    }
    return m
  }, [publishedModelsQuery.data])

  const boundVersionId = useMemo(() => {
    if (!onlyPublishedVersion || !boundModelId) return undefined
    const hit = publishedModelById.get(String(boundModelId))
    const vid = String(hit?.published_version_id ?? '').trim()
    return vid || undefined
  }, [onlyPublishedVersion, boundModelId, publishedModelById])

  const modelOptions = useMemo(() => {
    const items = (publishedModelsQuery.data as any)?.items ?? []
    return (items as any[])
      .map((m: any) => ({
        label: `${String(m?.model_code ?? '').trim()} ${String(m?.model_name ?? '').trim()}`.trim(),
        value: String(m?.model_id ?? '').trim(),
      }))
      .filter((x: any) => x.value)
  }, [publishedModelsQuery.data])

  const bundleTemplatesQuery = useQuery({
    queryKey: ['product-info', 'bundle-templates', bundleSearch],
    queryFn: () => fetchBundleTemplates({ search: bundleSearch || undefined, page: 1, page_size: 50 }),
    placeholderData: keepPreviousData,
  })

  const bundleTemplates = useMemo(() => {
    const items = (bundleTemplatesQuery.data as any)?.items
    return Array.isArray(items) ? (items as any[]) : []
  }, [bundleTemplatesQuery.data])

  const bundleTemplateOptions = useMemo(() => {
    return (bundleTemplates as any[])
      .map((t) => ({
        label: `${safeString((t as any)?.code)} ${safeString((t as any)?.name)}`.trim(),
        value: String((t as any)?.id ?? '').trim(),
      }))
      .filter((x) => x.value)
  }, [bundleTemplates])

  const bundlePresetsForSelectedTemplate = useMemo(() => {
    if (!selectedBundleTemplateId) return []
    const hit = (bundleTemplates as any[]).find((x) => String((x as any)?.id ?? '') === String(selectedBundleTemplateId))
    const meta = (hit as any)?.metadata ?? (hit as any)?.metadata_json ?? hit ?? {}
    const pp = Array.isArray((meta as any)?.phrase_presets) ? (meta as any).phrase_presets : []
    if (!pp.length) return [{ selector: 'AA', phrase: '默认', mode: 'parse', enabled: true }]
    const normalize = (s: string) => String(s || '').trim().toUpperCase().replace(/[^A-Z0-9]/g, '')
    return pp
      .map((p: any) => ({
        selector: String(p?.selector ?? '').trim().toUpperCase(),
        phrase: String(p?.phrase ?? '').trim(),
        mode: String(p?.mode ?? 'parse').trim(),
        enabled: p?.enabled !== false,
        _norm: normalize(String(p?.selector ?? '')),
      }))
      .filter((p: any) => !!p.selector)
  }, [bundleTemplates, selectedBundleTemplateId])

  const bundlePresetOptions = useMemo(() => {
    return (bundlePresetsForSelectedTemplate as any[]).map((p) => {
      const mode = String(p.mode || 'parse').trim() === 'force' ? '指定' : '解析'
      const label = `${p.selector}（${mode}）${p.phrase ? ` ${p.phrase}` : ''}`.trim()
      return { label, value: p.selector }
    })
  }, [bundlePresetsForSelectedTemplate])

  useEffect(() => {
    if (targetKind !== 'bundle') return
    if (!selectedBundleTemplateId) {
      setSelectedBundlePresetSelector(undefined)
      return
    }
    const first =
      (bundlePresetsForSelectedTemplate as any[]).find((x: any) => x?.enabled !== false) ??
      (bundlePresetsForSelectedTemplate as any[])?.[0]
    const sel = String((first as any)?.selector ?? '').trim().toUpperCase()
    setSelectedBundlePresetSelector(sel || undefined)
  }, [targetKind, selectedBundleTemplateId, bundlePresetsForSelectedTemplate])

  const listQuery = useQuery({
    queryKey: [
      'product-info',
      'list',
      page,
      pageSize,
      search,
      channel,
      matchStatus,
      targetKind,
      boundModelId,
      boundVersionId,
      selectedBundleTemplateId,
      selectedBundlePresetSelector,
    ],
    queryFn: () =>
      fetchSkuMaster({
        page,
        page_size: pageSize,
        search: search || undefined,
        channel,
        match_status: matchStatus,
        target_kind: targetKind === 'any' ? 'any' : targetKind,
        bound_state: targetKind === 'model' ? 'bound' : 'all',
        bound_model_id: boundModelId,
        bound_version_id: boundVersionId,
        bundle_bound_state: targetKind === 'bundle' ? 'bound' : undefined,
        bundle_template_id: selectedBundleTemplateId,
        bundle_preset_selector: selectedBundlePresetSelector,
        preparse_state: undefined,
        compute_total: false,
        include_shop_count: true,
      }),
    placeholderData: keepPreviousData,
  })

  const items = (listQuery.data?.items ?? []) as SkuMaster[]

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
      { title: '商家编码', dataIndex: 'shop_spec_code', width: 160, render: (v) => safeString(v) || '-' },
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
            const tpl = (bundleTemplates as any[]).find((t: any) => normalize(String(t?.code ?? '')) === base)
            const name = String((tpl as any)?.name ?? '').trim()
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
                        建议以“发货规格”为准；如网店规格长期不可信，可通过自动化/作业中心做批量修正或建立更稳定的商家编码锚点。
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
    [bundleTemplates],
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
                placeholder="搜索：条码/商家编码/规格/商品名"
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
            <Col xs={24} lg={3}>
              <Select
                value={targetKind}
                onChange={(v) => setTargetKind(v)}
                style={{ width: '100%' }}
                options={[
                  { value: 'any', label: '目标类型：全部' },
                  { value: 'model', label: '目标类型：标准模型' },
                  { value: 'bundle', label: '目标类型：套装模板' },
                ]}
              />
            </Col>
            <Col xs={24} lg={9}>
              <Space.Compact style={{ width: '100%' }}>
                {targetKind === 'model' ? (
                  <>
                    <Select
                      showSearch
                      allowClear
                      placeholder="一级：标准模型（已发布）"
                      value={boundModelId}
                      options={modelOptions as any}
                      onSearch={(q) => setModelSearch(q)}
                      onChange={(v) => {
                        setBoundModelId(v)
                        setPage(1)
                      }}
                      // 运营常用：模型名较长，但这里主用于筛选，缩窄以给“版本”更多空间
                      style={{ width: 160 }}
                      filterOption={false}
                      loading={publishedModelsQuery.isFetching}
                    />
                    <Select
                      value={onlyPublishedVersion ? 'published' : 'all'}
                      onChange={(v) => {
                        setOnlyPublishedVersion(v === 'published')
                        setPage(1)
                      }}
                      // 放大版本筛选，避免“二级：版本(全部)”挤压
                      style={{ width: 400 }}
                      options={[
                        { value: 'all', label: '二级：版本(全部)' },
                        { value: 'published', label: '二级：仅发布' },
                      ]}
                      disabled={!boundModelId}
                    />
                  </>
                ) : targetKind === 'bundle' ? (
                  <>
                    <Select
                      showSearch
                      allowClear
                      placeholder="一级：套装模板"
                      value={selectedBundleTemplateId}
                      options={bundleTemplateOptions as any}
                      onSearch={(q) => setBundleSearch(q)}
                      onChange={(v) => {
                        setSelectedBundleTemplateId(v)
                        setSelectedBundlePresetSelector(undefined)
                        setPage(1)
                      }}
                      style={{ width: 160 }}
                      filterOption={false}
                      loading={bundleTemplatesQuery.isFetching}
                    />
                    <Select
                      allowClear
                      placeholder="二级：selector"
                      value={selectedBundlePresetSelector}
                      options={bundlePresetOptions as any}
                      onChange={(v) => {
                        setSelectedBundlePresetSelector(v)
                        setPage(1)
                      }}
                      style={{ width: 400 }}
                      disabled={!selectedBundleTemplateId}
                    />
                  </>
                ) : (
                  <Select disabled placeholder="一级/二级筛选" style={{ width: '100%' }} />
                )}
              </Space.Compact>
            </Col>
          </Row>
        </Card>

        <div style={{ marginTop: 4, marginBottom: 4 }}>
          <Space size={8} align="center">
            <Text type="secondary">当前页：{items.length} 条</Text>
            <Tooltip title="默认不计算总数（compute_total=false），以支持后续几十万条数据仍能快速首屏加载。需要统计总数再单独加“统计总数”入口。">
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
            onChange: (p) => setPage(p),
            showSizeChanger: true,
            pageSizeOptions: [50, 100, 200, 500],
            onShowSizeChange: (_p, ps) => {
              setPage(1)
              setPageSize(ps)
            },
          }}
          locale={{ emptyText: '暂无数据（先调整筛选条件）' }}
        />
      </Space>
    </div>
  )
}

