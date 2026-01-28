import { Card, Col, Input, Row, Select, Space, Table, Tag, Tooltip, Typography } from 'antd'
import InfoCircleOutlined from '@ant-design/icons/lib/icons/InfoCircleOutlined'
import type { ColumnsType } from 'antd/es/table'
import dayjs from 'dayjs'
import { useEffect, useMemo, useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'

import { fetchBundleTemplates, fetchPublishedStandardModels, fetchSkuMaster } from '@/services/planner'
import type { SkuMaster } from '@/types/planner'

const { Text, Title } = Typography

const DEFAULT_PAGE_SIZE = 100
const PAGE_SIZE_STORAGE_KEY = 'costing_product_info_page_size_v1'

const formatTime = (v?: string | null) => {
  if (!v) return '-'
  const d = dayjs(v)
  return d.isValid() ? d.format('YYYY-MM-DD HH:mm:ss') : String(v)
}

const safeString = (v: unknown): string => {
  if (v === null || v === undefined) return ''
  return String(v)
}

const isFilled = (v: unknown): boolean => !!safeString(v).trim()

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
      }),
    placeholderData: keepPreviousData,
  })

  const items = (listQuery.data?.items ?? []) as SkuMaster[]

  const columns: ColumnsType<SkuMaster> = useMemo(
    () => [
      {
        title: '货品条码（系统）',
        dataIndex: 'erp_sku_barcode',
        width: 170,
        fixed: 'left',
        render: (v) => <Text style={{ fontFamily: 'monospace' }}>{safeString(v).trim() || '-'}</Text>,
      },
      { title: '店铺', dataIndex: 'channel', width: 120, render: (v) => safeString(v) || '-' },
      { title: '商家编码', dataIndex: 'shop_spec_code', width: 160, render: (v) => safeString(v) || '-' },
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
          return (
            <Space direction="vertical" size={2}>
              <div style={{ whiteSpace: 'normal', wordBreak: 'break-word', lineHeight: 1.2 }}>{text || '-'}</div>
              {fromFallback ? <Tag color="orange">回退：网店规格</Tag> : null}
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
              商品信息（只读）
            </Title>
            <Tooltip
              title={
                <div style={{ maxWidth: 520 }}>
                  <div>口径：解析结果以“用于解析的规格（发货规格优先，缺省回退网店规格）”与预解析缓存为准。</div>
                  <div>筛选：二级 selector 仅用于套装筛选（不改变解析口径）。</div>
                  <div>操作入口：绑定与批量作业在“自动化/作业中心”。</div>
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
                placeholder="店铺"
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
          scroll={{ x: 2200 }}
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

