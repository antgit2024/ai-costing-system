import { Alert, Card, Col, Descriptions, Input, Row, Select, Space, Table, Tag, Typography } from 'antd'
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table'
import dayjs from 'dayjs'
import { useEffect, useMemo, useState } from 'react'
import { keepPreviousData, useMutation, useQuery } from '@tanstack/react-query'

import { fetchSkuMaster, parseSpec } from '@/services/planner'
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

  useEffect(() => {
    try {
      localStorage.setItem(PAGE_SIZE_STORAGE_KEY, String(pageSize))
    } catch {
      // ignore
    }
  }, [pageSize])

  const listQuery = useQuery({
    queryKey: ['sku-spec-matching', 'list', page, pageSize, search, channel, matchStatus, includeTerms, excludeTerms, matchScope],
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
      }),
    placeholderData: keepPreviousData,
  })

  const items = (listQuery.data?.items ?? []) as SkuMaster[]
  const total = listQuery.data?.total ?? 0

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
  }, [activeSku?.id])

  useEffect(() => {
    if (!effectiveSpecText) return
    parseMutation.mutate(effectiveSpecText)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [effectiveSpecText])

  const columns: ColumnsType<SkuMaster> = useMemo(
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
        render: (v) => (
          <div style={{ whiteSpace: 'normal', wordBreak: 'break-word', lineHeight: 1.2 }}>{safeString(v) || '-'}</div>
        ),
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
            <Card size="small" title="第一步：规格解析（尺寸提取）">
              {!activeSku ? (
                <Alert type="info" showIcon message="请在右侧列表选择一条已绑定SKU，系统会自动解析尺寸。" />
              ) : (
                <Space direction="vertical" style={{ width: '100%' }}>
                  <Space wrap>
                    <Tag color="green">已绑定</Tag>
                    {activeSku.bound_model_code ? <Tag color="blue">{activeSku.bound_model_code}</Tag> : null}
                    {activeSku.bound_model_name ? <span>{activeSku.bound_model_name}</span> : null}
                  </Space>
                  <Text type="secondary">用于解析的规格文本（可手工覆写调试）：</Text>
                  <Input.TextArea
                    rows={4}
                    value={effectiveSpecText}
                    onChange={(e) => setSpecTextDraft(e.target.value)}
                    placeholder="优先发货规格，其次网店规格；你也可以在这里粘贴一段规格文本进行解析"
                  />
                  <Descriptions bordered size="small" column={2} style={{ marginTop: 8 }}>
                    <Descriptions.Item label="宽(cm)">{specParsed?.width_cm ?? '-'}</Descriptions.Item>
                    <Descriptions.Item label="高(cm)">{specParsed?.height_cm ?? '-'}</Descriptions.Item>
                    <Descriptions.Item label="直径(cm)">{specParsed?.diameter_cm ?? '-'}</Descriptions.Item>
                    <Descriptions.Item label="面积(m²)">{specParsed?.area_m2 ?? '-'}</Descriptions.Item>
                    <Descriptions.Item label="周长(m)">{specParsed?.perimeter_m ?? '-'}</Descriptions.Item>
                    <Descriptions.Item label="tokens数">{(specParsed?.tokens ?? []).length}</Descriptions.Item>
                  </Descriptions>
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
            <Table
              rowKey="id"
              size="small"
              loading={listQuery.isFetching}
              columns={columns}
              dataSource={items}
              pagination={{
                current: page,
                pageSize,
                total,
                showSizeChanger: true,
              }}
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


