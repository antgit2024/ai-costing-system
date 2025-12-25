import { Alert, Button, Card, Col, Descriptions, Input, InputNumber, Row, Select, Space, Table, Tabs, Tag, Typography, message } from 'antd'
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table'
import dayjs from 'dayjs'
import { useEffect, useMemo, useState } from 'react'
import { keepPreviousData, useMutation, useQuery } from '@tanstack/react-query'

import {
  executeSkuMasterSpecPreparse,
  fetchSkuMaster,
  parseSpec,
  previewSkuMasterSpecPreparse,
  saveSkuMasterSpecPreparse,
} from '@/services/planner'
import type { SkuMaster, SpecParseResponse } from '@/types/planner'

const { Title, Text } = Typography

const DEFAULT_PAGE_SIZE = 100
const PAGE_SIZE_STORAGE_KEY = 'costing_sku_spec_matching_page_size_v1'

const formatTime = (v?: string | null) => {
  if (!v) return '-'
  const d = dayjs(v)
  return d.isValid() ? d.format('YYYY-MM-DD HH:mm:ss') : String(v)
}

const safeString = (v: unknown): string => {
  if (v === null || v === undefined) return ''
  return String(v)
}

const dimGet = (dims: any, key: string): string => {
  const v = dims?.[key]
  if (v === null || v === undefined || v === '') return '-'
  return String(v)
}

export default function SkuSpecMatchingPage() {
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
  const [includeTerms, setIncludeTerms] = useState<string>('')
  const [excludeTerms, setExcludeTerms] = useState<string>('')
  const [matchScope, setMatchScope] = useState<'spec' | 'name'>('spec')
  const [channel, setChannel] = useState<string | undefined>(undefined)
  const [matchStatus, setMatchStatus] = useState<string | undefined>(undefined)

  const [activeSku, setActiveSku] = useState<SkuMaster | null>(null)
  const [specTextDraft, setSpecTextDraft] = useState<string>('')
  const [specParsed, setSpecParsed] = useState<SpecParseResponse | null>(null)
  const [manualWidthCm, setManualWidthCm] = useState<number | null>(null)
  const [manualHeightCm, setManualHeightCm] = useState<number | null>(null)
  const [manualDiameterCm, setManualDiameterCm] = useState<number | null>(null)
  const [bulkLimit, setBulkLimit] = useState<number>(200)
  const [isPreviewMode, setIsPreviewMode] = useState<boolean>(false)
  const [previewItems, setPreviewItems] = useState<any[]>([])
  const [previewSelectedKeys, setPreviewSelectedKeys] = useState<string[]>([])
  const [previewSaved, setPreviewSaved] = useState<boolean>(false)
  const [listTab, setListTab] = useState<'all' | 'parsed' | 'unparsed'>('all')

  useEffect(() => {
    try {
      localStorage.setItem(PAGE_SIZE_STORAGE_KEY, String(pageSize))
    } catch {
      // ignore
    }
  }, [pageSize])

  const listQuery = useQuery({
    queryKey: [
      'sku-spec-matching',
      'list',
      listTab,
      page,
      pageSize,
      search,
      channel,
      matchStatus,
      includeTerms,
      excludeTerms,
      matchScope,
    ],
    queryFn: () =>
      fetchSkuMaster({
        page,
        page_size: pageSize,
        search: search || undefined,
        channel,
        match_status: matchStatus,
        include_terms: includeTerms || undefined,
        exclude_terms: excludeTerms || undefined,
        match_scope: matchScope,
        bound_state: 'bound', // 规格模块：只看已绑定模型的商品
        preparse_state: listTab === 'parsed' ? 'parsed' : listTab === 'unparsed' ? 'unparsed' : undefined,
      }),
    placeholderData: keepPreviousData,
  })

  const items = (listQuery.data?.items ?? []) as SkuMaster[]
  const total = listQuery.data?.total ?? 0
  const tableRows = isPreviewMode ? previewItems : items
  const tableTotal = isPreviewMode ? previewItems.length : total

  const channelOptions = useMemo(() => {
    const set = new Set<string>()
    for (const it of items) {
      const c = safeString(it.channel).trim()
      if (c) set.add(c)
    }
    return Array.from(set)
      .sort()
      .map((c) => ({ label: c, value: c }))
  }, [items])

  const matchStatusOptions = useMemo(() => {
    const set = new Set<string>()
    for (const it of items) {
      const s = safeString(it.match_status).trim()
      if (s) set.add(s)
    }
    return Array.from(set)
      .sort()
      .map((s) => ({ label: s, value: s }))
  }, [items])

  const parseMutation = useMutation({
    mutationFn: (spec_text: string) => parseSpec({ spec_text }),
    onSuccess: (res) => setSpecParsed(res),
    onError: () => setSpecParsed(null),
  })

  const effectiveSpecText = useMemo(() => {
    const s = (specTextDraft || '').trim()
    if (s) return s
    const src = activeSku?.last_shipment_spec_text || activeSku?.spec_text || ''
    return String(src || '').trim()
  }, [activeSku, specTextDraft])

  useEffect(() => {
    // 切换行时：默认用“发货规格”优先，其次用 ERP 规格，并清空手工覆写
    setSpecTextDraft('')
    setSpecParsed(null)
    setManualWidthCm(null)
    setManualHeightCm(null)
    setManualDiameterCm(null)
  }, [activeSku?.id])

  useEffect(() => {
    if (!effectiveSpecText) return
    parseMutation.mutate(effectiveSpecText)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [effectiveSpecText])

  const savePreparseMutation = useMutation({
    mutationFn: async () => {
      if (!activeSku?.id) throw new Error('请先选择一条SKU')
      const baseDims = specParsed || ({} as any)
      const width = manualWidthCm != null ? manualWidthCm : baseDims?.width_cm ?? null
      const height = manualHeightCm != null ? manualHeightCm : baseDims?.height_cm ?? null
      const dia = manualDiameterCm != null ? manualDiameterCm : baseDims?.diameter_cm ?? null
      return saveSkuMasterSpecPreparse(activeSku.id, {
        spec_text: effectiveSpecText,
        width_cm: width as any,
        height_cm: height as any,
        diameter_cm: dia as any,
        requested_by: null,
      })
    },
    onSuccess: (res) => {
      message.success('已保存为预解析缓存（用于加速/预填，不影响发货快照口径）')
      // 本地刷新选中行的展示（避免必须手动刷新列表）
      setActiveSku((prev) =>
        prev
          ? ({
              ...prev,
              preparse_spec_hash: res.preparse_spec_hash,
              preparse_dimensions: res.preparse_dimensions,
              preparse_tokens: res.preparse_tokens,
              preparse_saved_at: res.preparse_saved_at ?? null,
              preparse_saved_by: res.preparse_saved_by ?? null,
            } as any)
          : prev,
      )
      listQuery.refetch()
    },
    onError: (err: any) => {
      message.error(err?.response?.data?.detail ?? err?.message ?? '保存失败')
    },
  })

  const previewMutation = useMutation({
    mutationFn: async () => {
      return previewSkuMasterSpecPreparse({
        limit: bulkLimit,
        search: search || undefined,
        channel: channel || undefined,
        match_status: matchStatus || undefined,
        include_terms: includeTerms || undefined,
        exclude_terms: excludeTerms || undefined,
        match_scope: matchScope,
      })
    },
    onSuccess: (res) => {
      const rows = (res.items ?? []).map((x) => ({
        id: x.sku_id,
        erp_sku_barcode: x.erp_sku_barcode,
        channel: x.channel ?? null,
        product_name: (x as any).product_name ?? null,
        product_code: (x as any).product_code ?? null,
        spec_text: (x as any).spec_text ?? null,
        bound_model_code: (x as any).bound_model_code ?? null,
        bound_model_name: (x as any).bound_model_name ?? null,
        bound_version_label: (x as any).bound_version_label ?? null,
        // show used spec as shipment spec column
        last_shipment_spec_text: x.spec_text_used,
        _preview_spec_hash: x.spec_hash,
        _preview_dims: {
          width_cm: x.width_cm ?? null,
          height_cm: x.height_cm ?? null,
          diameter_cm: x.diameter_cm ?? null,
          area_m2: x.area_m2 ?? null,
          perimeter_m: x.perimeter_m ?? null,
        },
      }))
      setIsPreviewMode(true)
      setPreviewSaved(false)
      setPreviewItems(rows as any[])
      setPreviewSelectedKeys(rows.map((r) => String(r.id)))
      message.success(`预览解析完成：${rows.length} 条（默认全选）`)
    },
    onError: (err: any) => {
      message.error(err?.response?.data?.detail ?? err?.message ?? '预览解析失败')
    },
  })

  const executePreviewSaveMutation = useMutation({
    mutationFn: async () => {
      const ids = previewSelectedKeys
      return executeSkuMasterSpecPreparse({ sku_ids: ids, skip_if_same_hash: true })
    },
    onSuccess: (res) => {
      const errs = (res as any)?.errors ?? []
      if (Array.isArray(errs) && errs.length) {
        const first = errs[0] ?? {}
        message.error(`保存失败：${first?.error ?? '未知错误'}`)
        return
      }
      message.success(`保存完成：扫描${res.scanned}，保存${res.saved}，跳过${res.skipped_same_hash}`)
      // 保存后，保留预览列表作为“回执确认”，避免用户觉得记录消失
      setPreviewSaved(true)
      setPreviewItems((prev) =>
        (prev ?? []).map((r) => ({
          ...r,
          preparse_spec_hash: r?._preview_spec_hash ?? r?.preparse_spec_hash ?? 'saved',
          preparse_dimensions: r?._preview_dims ?? r?.preparse_dimensions ?? {},
          preparse_saved_at: new Date().toISOString(),
        })),
      )
      // 同步刷新后台列表数据（退出预览后会自动落到“已解析”Tab）
      listQuery.refetch()
    },
    onError: (err: any) => {
      message.error(err?.response?.data?.detail ?? err?.message ?? '保存失败')
    },
  })

  const columns: ColumnsType<any> = useMemo(
    () => [
      {
        title: '货品条码（系统）',
        dataIndex: 'erp_sku_barcode',
        width: 170,
        fixed: 'left',
        render: (v) => <Text style={{ fontFamily: 'monospace' }}>{safeString(v) || '-'}</Text>,
      },
      { title: '销售渠道', dataIndex: 'channel', width: 120, render: (v) => safeString(v) || '-' },
      {
        title: '已绑定模型',
        dataIndex: 'bound_model_code',
        width: 180,
        render: (_v, row) =>
          row.bound_model_code ? (
            <Space size={6}>
              <Tag color="blue">{row.bound_model_code}</Tag>
              <span style={{ color: '#666' }}>{row.bound_model_name || ''}</span>
            </Space>
          ) : (
            <Tag color="red">未绑定</Tag>
          ),
      },
      { title: '标准版本', dataIndex: 'bound_version_label', width: 120, render: (v) => safeString(v) || '-' },
      {
        title: '商品名称（网店）',
        dataIndex: 'product_name',
        width: 260,
        render: (v) => (
          <div style={{ whiteSpace: 'normal', wordBreak: 'break-word', lineHeight: 1.2 }}>{safeString(v) || '-'}</div>
        ),
      },
      { title: '商品编码（网店）', dataIndex: 'product_code', width: 140, render: (v) => safeString(v) || '-' },
      {
        title: '商品规格（网店）',
        dataIndex: 'spec_text',
        width: 520,
        render: (v) => (
          <div style={{ whiteSpace: 'normal', wordBreak: 'break-word', lineHeight: 1.2 }}>{safeString(v) || '-'}</div>
        ),
      },
      {
        title: '发货规格（优先用于解析）',
        dataIndex: 'last_shipment_spec_text',
        width: 360,
        render: (v, row) => {
          const text = safeString(v) || '-'
          const dims = (row as any)?._preview_dims
          if (!dims) {
            return <div style={{ whiteSpace: 'normal', wordBreak: 'break-word', lineHeight: 1.2 }}>{text}</div>
          }
          const w = dims?.width_cm ?? '-'
          const h = dims?.height_cm ?? '-'
          return (
            <div style={{ whiteSpace: 'normal', wordBreak: 'break-word', lineHeight: 1.2 }}>
              <div>{text}</div>
              <Tag color="purple" style={{ marginTop: 4 }}>
                解析尺寸：宽{w}cm × 高{h}cm
              </Tag>
            </div>
          )
        },
      },
      {
        title: '预解析尺寸（已落库）',
        dataIndex: 'preparse_dimensions',
        width: 220,
        render: (_v, row) => {
          const dims = (row as any)?.preparse_dimensions
          const hash = (row as any)?.preparse_spec_hash
          if (!hash) return <Tag>未解析</Tag>
          const w = dimGet(dims, 'width_cm')
          const h = dimGet(dims, 'height_cm')
          return (
            <Space size={6} wrap>
              <Tag color="geekblue">已解析</Tag>
              <Tag color="purple">
                宽{w}×高{h}cm
              </Tag>
            </Space>
          )
        },
      },
      { title: '宽(cm)(ERP缓存)', dataIndex: 'erp_dimensions', width: 120, render: (dims) => dimGet(dims, 'width_cm') },
      { title: '高(cm)(ERP缓存)', dataIndex: 'erp_dimensions', width: 120, render: (dims) => dimGet(dims, 'height_cm') },
      { title: 'ERP规格Hash', dataIndex: 'erp_spec_hash', width: 160, render: (v) => safeString(v) || '-' },
      { title: '更新时间', dataIndex: 'updated_at', width: 170, render: (v) => formatTime(v as any) },
    ],
    [],
  )

  const handlePaginationChange = (pagination: TablePaginationConfig) => {
    const nextPage = Number(pagination.current || 1)
    const nextSize = Number(pagination.pageSize || pageSize)
    setPage(nextPage)
    setPageSize(nextSize)
  }

  return (
    <div>
      <Title level={3} style={{ marginTop: 0 }}>
        规格匹配工作台（第一步：尺寸/规格解析）
      </Title>
      <Text type="secondary">
        本页面仅展示<strong>已绑定模型</strong>的 SKU；解析优先使用“发货规格”，缺失时回退到“商品规格（网店）”。变体规则与词典先不启用，等你们跑完70%再上。
      </Text>

      <Row gutter={[16, 16]} style={{ marginTop: 12 }}>
        {/* 左侧 1/4：解析工作台 */}
        <Col xs={24} lg={6}>
          <Space direction="vertical" style={{ width: '100%' }}>
            <Card
              size="small"
              title="工作台（与商品匹配同款：预览解析 → 保存落库）"
              extra={isPreviewMode ? <Tag color="purple">预览中</Tag> : <Tag>未预览</Tag>}
            >
              <Space wrap>
                <Tag color="purple">模式：自动识别</Tag>
                <InputNumber
                  addonBefore="预览数"
                  min={1}
                  max={5000}
                  value={bulkLimit}
                  onChange={(v) => setBulkLimit(typeof v === 'number' ? v : 200)}
                />
                <Button type="primary" loading={previewMutation.isPending} onClick={() => previewMutation.mutate()}>
                  预览解析
                </Button>
                <Button
                  type="primary"
                  danger
                  loading={executePreviewSaveMutation.isPending}
                  disabled={!isPreviewMode || previewSelectedKeys.length === 0}
                  onClick={() => executePreviewSaveMutation.mutate()}
                >
                  保存预览解析
                </Button>
                {isPreviewMode ? (
                  <Button
                    onClick={() => {
                      // 退出预览：回到“已解析”视图查看落库结果
                      setIsPreviewMode(false)
                      setPreviewItems([])
                      setPreviewSelectedKeys([])
                      setPreviewSaved(false)
                      setListTab('parsed')
                      setPage(1)
                      listQuery.refetch()
                    }}
                  >
                    退出预览
                  </Button>
                ) : null}
              </Space>
              {isPreviewMode ? (
                <Alert
                  style={{ marginTop: 8 }}
                  type="info"
                  showIcon
                  message={`当前为预览模式：右侧列表默认全选 ${previewItems.length} 条；可取消勾选后再“保存预览解析”。`}
                />
              ) : null}
              {isPreviewMode && previewSaved ? (
                <Alert
                  style={{ marginTop: 8 }}
                  type="success"
                  showIcon
                  message="已落库成功：右侧仍展示本次保存的记录作为回执；点击“退出预览”将自动切到“已解析”TAB。"
                />
              ) : null}
            </Card>

            <Card size="small" title="单条人工审核（可选）">
              {!activeSku ? (
                <Alert type="info" showIcon message="请在右侧列表选择一条已绑定SKU，系统会自动解析尺寸。" />
              ) : (
                <Space direction="vertical" style={{ width: '100%' }}>
                  <Space wrap>
                    <Tag color="green">已绑定</Tag>
                    {activeSku.bound_model_code ? <Tag color="blue">{activeSku.bound_model_code}</Tag> : null}
                    {activeSku.bound_model_name ? <span>{activeSku.bound_model_name}</span> : null}
                  </Space>
                  <Space wrap>
                    <Tag color="purple">模式：人工审核</Tag>
                    {activeSku.preparse_spec_hash ? <Tag color="geekblue">已保存预解析</Tag> : <Tag>未保存</Tag>}
                  </Space>
                  <Text type="secondary">用于解析的规格文本（可手工覆写调试）：</Text>
                  <Input.TextArea
                    rows={4}
                    value={effectiveSpecText}
                    onChange={(e) => setSpecTextDraft(e.target.value)}
                    placeholder="优先发货规格，其次网店规格；你也可以在这里粘贴一段规格文本进行解析"
                  />
                  <Space wrap>
                    <span style={{ color: '#666' }}>人工校对：</span>
                    <InputNumber
                      addonBefore="宽cm"
                      value={manualWidthCm}
                      onChange={(v) => setManualWidthCm(typeof v === 'number' ? v : null)}
                      placeholder={specParsed?.width_cm != null ? String(specParsed.width_cm) : '—'}
                    />
                    <InputNumber
                      addonBefore="高cm"
                      value={manualHeightCm}
                      onChange={(v) => setManualHeightCm(typeof v === 'number' ? v : null)}
                      placeholder={specParsed?.height_cm != null ? String(specParsed.height_cm) : '—'}
                    />
                    <InputNumber
                      addonBefore="直径cm"
                      value={manualDiameterCm}
                      onChange={(v) => setManualDiameterCm(typeof v === 'number' ? v : null)}
                      placeholder={specParsed?.diameter_cm != null ? String(specParsed.diameter_cm) : '—'}
                    />
                    <Button
                      type="primary"
                      loading={savePreparseMutation.isPending}
                      onClick={() => savePreparseMutation.mutate()}
                      disabled={!effectiveSpecText || !activeSku?.id}
                    >
                      保存预解析
                    </Button>
                  </Space>
                  <Alert
                    type="info"
                    showIcon
                    message="提示：系统会识别“竖/横/宽/高/长”这类带方向的尺寸写法，例如：竖120CM*横150CM → 高=120cm，宽=150cm。"
                    style={{ marginTop: 8 }}
                  />
                  <Descriptions bordered size="small" column={2} style={{ marginTop: 8 }}>
                    <Descriptions.Item label="宽(cm)">{specParsed?.width_cm ?? '-'}</Descriptions.Item>
                    <Descriptions.Item label="高(cm)">{specParsed?.height_cm ?? '-'}</Descriptions.Item>
                    <Descriptions.Item label="直径(cm)">{specParsed?.diameter_cm ?? '-'}</Descriptions.Item>
                    <Descriptions.Item label="面积(m²)">{specParsed?.area_m2 ?? '-'}</Descriptions.Item>
                    <Descriptions.Item label="周长(m)">{specParsed?.perimeter_m ?? '-'}</Descriptions.Item>
                    <Descriptions.Item label="tokens数">{(specParsed?.tokens ?? []).length}</Descriptions.Item>
                  </Descriptions>
                  {activeSku.preparse_saved_at ? (
                    <Text type="secondary">预解析保存时间：{formatTime(activeSku.preparse_saved_at)}</Text>
                  ) : null}
                  <Card size="small" title="解析 tokens（原始分段）" style={{ marginTop: 8 }}>
                    <div style={{ whiteSpace: 'normal', wordBreak: 'break-word', lineHeight: 1.2 }}>
                      {(specParsed?.tokens ?? []).slice(0, 50).map((t, idx) => (
                        <Tag key={`${t}-${idx}`}>{t}</Tag>
                      ))}
                      {(specParsed?.tokens ?? []).length > 50 ? <Tag>…</Tag> : null}
                    </div>
                  </Card>
                  {parseMutation.isPending ? <Text type="secondary">解析中…</Text> : null}
                </Space>
              )}
            </Card>

            <Card size="small" title="后续：变体规则（暂不启用）">
              <Alert
                type="warning"
                showIcon
                message="先完成“尺寸解析”与70%主流程；等进入变体实操阶段，再引入 token 词典与行级变体规则（Overlay）。"
              />
            </Card>
          </Space>
        </Col>

        {/* 右侧 3/4：筛选 + 列表 */}
        <Col xs={24} lg={18}>
          <Card
            title="已绑定SKU列表"
            extra={
              <Space wrap>
                <Input
                  style={{ width: 240 }}
                  placeholder="搜索：条码/商品名/编码"
                  value={search}
                  onChange={(e) => {
                    setSearch(e.target.value)
                    setPage(1)
                  }}
                />
                <Input
                  style={{ width: 220 }}
                  placeholder="包含关键词（AND，多词空格分隔）"
                  value={includeTerms}
                  onChange={(e) => {
                    setIncludeTerms(e.target.value)
                    setPage(1)
                  }}
                />
                <Input
                  style={{ width: 200 }}
                  placeholder="排除关键词（AND NOT）"
                  value={excludeTerms}
                  onChange={(e) => {
                    setExcludeTerms(e.target.value)
                    setPage(1)
                  }}
                />
                <Select
                  style={{ width: 170 }}
                  value={matchScope}
                  onChange={(v) => setMatchScope(v)}
                  options={[
                    { label: '商品规格', value: 'spec' },
                    { label: '商品名称', value: 'name' },
                  ]}
                />
                <Select
                  allowClear
                  style={{ width: 150 }}
                  placeholder="渠道"
                  options={channelOptions}
                  value={channel}
                  onChange={(v) => {
                    setChannel(v)
                    setPage(1)
                  }}
                />
                <Select
                  allowClear
                  style={{ width: 190 }}
                  placeholder="ERP匹配状态（网店↔ERP）"
                  options={matchStatusOptions}
                  value={matchStatus}
                  onChange={(v) => {
                    setMatchStatus(v)
                    setPage(1)
                  }}
                />
                <Tag color="blue">总数：{total}</Tag>
              </Space>
            }
          >
            {!isPreviewMode ? (
              <Tabs
                activeKey={listTab}
                onChange={(k) => {
                  setListTab(k as any)
                  setPage(1)
                }}
                items={[
                  { key: 'all', label: '全部' },
                  { key: 'parsed', label: '已解析' },
                  { key: 'unparsed', label: '未解析' },
                ]}
              />
            ) : null}
            <Table
              rowKey="id"
              size="small"
              loading={listQuery.isFetching}
              columns={columns}
              dataSource={tableRows}
              rowSelection={
                isPreviewMode
                  ? {
                      selectedRowKeys: previewSelectedKeys,
                      onChange: (keys) => setPreviewSelectedKeys((keys ?? []) as string[]),
                    }
                  : undefined
              }
              pagination={
                isPreviewMode
                  ? {
                      current: 1,
                      pageSize: tableTotal,
                      total: tableTotal,
                      showSizeChanger: false,
                    }
                  : {
                      current: page,
                      pageSize,
                      total: tableTotal,
                      showSizeChanger: true,
                    }
              }
              onChange={handlePaginationChange}
              onRow={(record) => ({
                onClick: () => setActiveSku(record),
              })}
              rowClassName={(record) => (record.id === activeSku?.id ? 'row-selected' : '')}
              scroll={{ x: 2200 }}
            />
          </Card>
        </Col>
      </Row>
    </div>
  )
}


