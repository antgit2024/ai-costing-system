import {
  Alert,
  Button,
  Card,
  Col,
  Descriptions,
  Drawer,
  Image,
  Input,
  message,
  Tabs,
  Row,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  Upload,
} from 'antd'
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table'
import dayjs from 'dayjs'
import { useEffect, useMemo, useState } from 'react'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import {
  autoBindSkuMastersExecute,
  autoBindSkuMastersPreview,
  bindSkuMastersByModel,
  fetchPublishedStandardModels,
  fetchSkuMaster,
  fetchSkuMasterDetail,
  importSkuMasterXlsx,
} from '@/services/planner'
import type { PublishedStandardModelCandidate, SkuMaster, SkuMasterAutoBindPreviewItem } from '@/types/planner'

const { Title, Text } = Typography

const DEFAULT_PAGE_SIZE = 100
const PAGE_SIZE_STORAGE_KEY = 'costing_sku_master_page_size_v1'

const formatTime = (v?: string | null) => {
  if (!v) return '-'
  const d = dayjs(v)
  return d.isValid() ? d.format('YYYY-MM-DD HH:mm:ss') : String(v)
}

const safeString = (v: unknown): string => {
  if (v === null || v === undefined) return ''
  return String(v)
}

const isFilled = (v?: string | null) => !!(v && String(v).trim())

const jsonPretty = (obj: unknown) => {
  try {
    return JSON.stringify(obj ?? {}, null, 2)
  } catch {
    return String(obj ?? '')
  }
}

const SkuMasterWorkspacePage = () => {
  const queryClient = useQueryClient()

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
  const [specKeyword, setSpecKeyword] = useState<string>('') // MVP: client-side filter on current page
  const [channel, setChannel] = useState<string | undefined>(undefined)
  const [matchStatus, setMatchStatus] = useState<string | undefined>(undefined)
  const [listTab, setListTab] = useState<'all' | 'unbound' | 'bound'>('all')
  const [selectedRowKeys, setSelectedRowKeys] = useState<string[]>([])

  const [uploading, setUploading] = useState(false)
  const [uploadFile, setUploadFile] = useState<File | null>(null)
  const [requestedBy, setRequestedBy] = useState<string>('')

  const [drawerOpen, setDrawerOpen] = useState(false)
  const [activeId, setActiveId] = useState<string | null>(null)

  // left workbench
  const [workbenchTab, setWorkbenchTab] = useState<'auto' | 'manual'>('manual')
  const [modelSearch, setModelSearch] = useState<string>('')
  const [selectedModelId, setSelectedModelId] = useState<string | undefined>(undefined)
  const [autoPreviewText, setAutoPreviewText] = useState<string>('')
  const [autoPreviewCandidates, setAutoPreviewCandidates] = useState<SkuMasterAutoBindPreviewItem[]>([])
  const [autoCandidatesOnly, setAutoCandidatesOnly] = useState(false)

  useEffect(() => {
    try {
      localStorage.setItem(PAGE_SIZE_STORAGE_KEY, String(pageSize))
    } catch {
      // ignore
    }
  }, [pageSize])

  // Tab 切换：重置分页，避免“第一页空白”的错觉
  useEffect(() => {
    setPage(1)
  }, [listTab])

  const listQuery = useQuery({
    queryKey: ['sku-master', 'list', listTab, page, pageSize, search, channel, matchStatus],
    queryFn: () =>
      fetchSkuMaster({
        page,
        page_size: pageSize,
        search: search || undefined,
        channel,
        match_status: matchStatus,
        bound_state: listTab === 'bound' ? 'bound' : listTab === 'unbound' ? 'unbound' : undefined,
      }),
    placeholderData: keepPreviousData,
    enabled: !autoCandidatesOnly, // 命中候选视图时不依赖服务端分页列表
  })

  const items = autoCandidatesOnly
    ? autoPreviewCandidates.map((x) => ({
        id: x.sku_master_id,
        erp_sku_barcode: x.erp_sku_barcode,
        channel: x.channel ?? null,
        spec_text: x.spec_text ?? null,
        // 预览候选本身就是未绑定
        active_model_version_id: null,
        // 用于表格展示“匹配模型（预览）”
      })) as any[]
    : listQuery.data?.items ?? []
  const total = autoCandidatesOnly ? (autoPreviewCandidates?.length ?? 0) : listQuery.data?.total ?? 0

  const filteredItems = useMemo(() => {
    const kw = specKeyword.trim()
    let rows = items
    if (kw) rows = rows.filter((x) => (x.spec_text ?? '').includes(kw))
    // 注意：unbound/bound/mismatch 已下沉到后端过滤，这里仅保留“命中候选视图”和关键词过滤
    return rows
  }, [items, specKeyword, listTab])

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

  const pageStats = useMemo(() => {
    const rows = filteredItems
    const totalRows = rows.length
    const erpMatched = rows.filter((x) => isFilled(x.match_status)).length
    const linked = rows.filter((x) => isFilled(x.active_model_version_id as any)).length
    const complete = rows.filter((x) => {
      // MVP: “字段齐全” = 条码 + 渠道 + 名称 + 编码 + 规格 + 平台商品Id + 平台规格Id
      return (
        isFilled(x.erp_sku_barcode) &&
        isFilled(x.channel) &&
        isFilled(x.product_name) &&
        isFilled(x.product_code) &&
        isFilled(x.spec_text) &&
        isFilled(x.platform_product_id) &&
        isFilled(x.platform_sku_id)
      )
    }).length
    const rate = (n: number) => (totalRows ? `${Math.round((n / totalRows) * 1000) / 10}%` : '-')
    return {
      totalRows,
      erpMatched,
      linked,
      complete,
      erpMatchedRate: rate(erpMatched),
      linkedRate: rate(linked),
      completeRate: rate(complete),
    }
  }, [filteredItems])

  const detailQuery = useQuery({
    queryKey: ['sku-master', 'detail', activeId],
    queryFn: () => fetchSkuMasterDetail(activeId as string),
    enabled: !!activeId && drawerOpen,
  })

  const columns: ColumnsType<SkuMaster> = [
    {
      title: '货品条码（系统）',
      dataIndex: 'erp_sku_barcode',
      width: 140,
      ellipsis: true,
      render: (v) => safeString(v) || '-',
    },
    {
      title: '销售渠道',
      dataIndex: 'channel',
      width: 110,
      ellipsis: true,
      render: (v) => safeString(v) || '-',
    },
    {
      title: '商品规格（网店）',
      dataIndex: 'spec_text',
      width: 560,
      ellipsis: false,
      render: (v) => {
        const s = safeString(v) || '-'
        return <span style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{s}</span>
      },
    },
    // “模型提示”对业务侧噪声较大：已移到详情抽屉；列表仅展示“已绑定模型(名称)”或“预览匹配模型”
    ...(autoCandidatesOnly
      ? [
    {
            title: '匹配模型（预览）',
            dataIndex: 'id',
            width: 240,
            render: (_: any, record: any) => {
              const hit = autoPreviewCandidates.find((x) => x.sku_master_id === record.id)
              if (!hit) return '-'
              const label = `${hit.model_code} ${hit.model_name}${hit.version_label ? `（${hit.version_label}）` : ''}`
              return (
                <Space size={6}>
                  <Tag color="blue">{label}</Tag>
                  {hit.match_method ? <Tag>{hit.match_method}</Tag> : null}
                  {hit.matched_keyword ? <Tag color="purple">{hit.matched_keyword}</Tag> : null}
                </Space>
              )
            },
          } as any,
        ]
      : []),
    {
      title: '对接状态（本系统）',
      dataIndex: 'active_model_version_id',
      width: 240,
      render: (v, record) => {
        const bound = isFilled(v as any)
        const source = safeString((record.metadata_json as any)?.source)
        const srcTag = source === 'shipment_autobackfill' ? <Tag color="gold">发货回写</Tag> : null
        const modelLabel = record.bound_model_code
          ? `${record.bound_model_code}${record.bound_model_name ? `(${record.bound_model_name})` : ''}`
          : ''
        return (
          <Space size={6}>
            {bound ? <Tag color="green">已绑定</Tag> : <Tag color="red">未绑定</Tag>}
            {record.spec_mismatch ? <Tag color="orange">规格差异</Tag> : null}
            {modelLabel ? <Tag color="blue">{modelLabel}</Tag> : null}
            {srcTag}
          </Space>
        )
      },
    },
    {
      title: '最后更新时间',
      dataIndex: 'updated_at',
      width: 170,
      render: (v) => formatTime(v),
    },
    {
      title: '操作',
      key: 'actions',
      width: 90,
      render: (_, record) => (
        <Button
          size="small"
          onClick={() => {
            setActiveId(record.id)
            setDrawerOpen(true)
          }}
        >
          查看
        </Button>
      ),
    },
  ]

  const handlePaginationChange = (pagination: TablePaginationConfig) => {
    setPage(pagination.current ?? 1)
    setPageSize(pagination.pageSize ?? DEFAULT_PAGE_SIZE)
  }

  const handleImport = async () => {
    if (!uploadFile) {
      message.warning('请先选择要导入的 xlsx 文件')
      return
    }
    setUploading(true)
    try {
      const result = await importSkuMasterXlsx({ file: uploadFile, requested_by: requestedBy || undefined })
      message.success(
        `导入完成：total=${result.total} inserted=${result.inserted} updated=${result.updated} skipped=${result.skipped}`,
      )
      setUploadFile(null)
      await queryClient.invalidateQueries({ queryKey: ['sku-master', 'list'] })
    } catch (e: any) {
      message.error(e?.message || '导入失败')
    } finally {
      setUploading(false)
    }
  }

  const candidatesQuery = useQuery({
    queryKey: ['sku-master', 'published-standard-models', modelSearch],
    queryFn: () => fetchPublishedStandardModels({ search: modelSearch || undefined, limit: 50 }),
    placeholderData: keepPreviousData,
  })

  const modelOptions = useMemo(() => {
    const items = (candidatesQuery.data as any)?.items ?? []
    return (items as PublishedStandardModelCandidate[]).map((m) => ({
      label: `${m.model_code}  ${m.model_name}${m.version_label ? `（${m.version_label}）` : ''}`,
      value: m.model_id,
    }))
  }, [candidatesQuery.data])

  const bindMutation = useMutation({
    mutationFn: async () => {
      if (!selectedModelId) throw new Error('请选择模型')
      return await bindSkuMastersByModel({
        model_id: selectedModelId,
        sku_master_ids: selectedRowKeys,
        requested_by: requestedBy || undefined,
      })
    },
    onSuccess: async (res: any) => {
      message.success(
        `绑定完成：bound=${res.bound_count} skipped(bound)=${res.skipped_already_bound} errors=${(res.errors ?? []).length}`,
      )
      setSelectedRowKeys([])
      await queryClient.invalidateQueries({ queryKey: ['sku-master', 'list'] })
    },
    onError: (e: any) => message.error(e?.message || '绑定失败'),
  })

  const autoPreviewMutation = useMutation({
    mutationFn: () => autoBindSkuMastersPreview({ limit: 200, scan_limit: 50000 }),
    onSuccess: (res: any) => {
      setAutoPreviewText(`未绑定≈${res.total_unbound} 可自动=${res.candidates}（展示${(res.items ?? []).length}）`)
      const cand = (res.items ?? []) as SkuMasterAutoBindPreviewItem[]
      setAutoPreviewCandidates(cand)
      const idSet = new Set(cand.map((x) => x.sku_master_id))
      setAutoCandidatesOnly(true)
      setListTab('unbound')
      // 让右侧尽量展示“命中候选”（200条）
      setPage(1)
      setPageSize(100)
      setSelectedRowKeys(Array.from(idSet))
      message.success('已生成预览')
    },
    onError: (e: any) => message.error(e?.message || '预览失败'),
  })

  const autoExecuteMutation = useMutation({
    mutationFn: () => {
      if (!selectedRowKeys.length) throw new Error('请先在右侧列表勾选要绑定的记录（可先点预览自动全选）')
      // 仅绑定“预览命中候选”中被勾选的
      const allow = new Set(autoPreviewCandidates.map((x) => x.sku_master_id))
      const ids = selectedRowKeys.filter((id) => allow.has(id))
      if (!ids.length) throw new Error('当前勾选项不在“自动命中候选”中，不会执行绑定')
      return autoBindSkuMastersExecute({ limit: 200, requested_by: requestedBy || undefined, sku_master_ids: ids })
    },
    onSuccess: async (res: any) => {
      message.success(
        `自动绑定完成：bound=${res.bound_count} skipped(bound)=${res.skipped_already_bound} errors=${(res.errors ?? []).length}`,
      )
      setAutoPreviewText(
        `未绑定≈${res.preview?.total_unbound} 可自动=${res.preview?.candidates}（展示${(res.preview?.items ?? []).length}）`,
      )
      const cand = (res.preview?.items ?? []) as SkuMasterAutoBindPreviewItem[]
      setAutoPreviewCandidates(cand)
      // 执行完后：跳到“已绑定”列表（便于看到刚绑定的记录），并重置分页避免出现空白第一页
      setAutoCandidatesOnly(false)
      setSelectedRowKeys([])
      setListTab('bound')
      setPage(1)
      setPageSize(DEFAULT_PAGE_SIZE)
      await queryClient.invalidateQueries({ queryKey: ['sku-master', 'list'] })
    },
    onError: (e: any) => message.error(e?.message || '执行失败'),
  })

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between' }}>
        <div>
          <Title level={3} style={{ marginBottom: 4 }}>
            商品关联（SKU 主档）
          </Title>
          <Text type="secondary">
            左侧用于绑定与规则配置，右侧用于筛选与列表查看（统计以当前页为准）。
          </Text>
        </div>
        <Button onClick={() => listQuery.refetch()}>刷新</Button>
      </div>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        {/* 左侧：绑定工作台（1/4） */}
        <Col xs={24} lg={6}>
          <Space direction="vertical" size={12} style={{ width: '100%' }}>
            <Card size="small" title="绑定工作台">
              <Tabs
                activeKey={workbenchTab}
                onChange={(k) => setWorkbenchTab(k as any)}
                items={[
                  {
                    key: 'manual',
                    label: '手工',
                    children: (
                      <Space direction="vertical" style={{ width: '100%' }}>
                        <Text type="secondary">选择“标准模型”（系统会自动落到该模型唯一在线发布版本）。</Text>
                        <Select
                          showSearch
                          allowClear
                          placeholder="选择已发布标准模型"
                          options={modelOptions}
                          value={selectedModelId}
                          onChange={(v) => setSelectedModelId(v)}
                          onSearch={(v) => setModelSearch(v)}
                          filterOption={false}
                          loading={candidatesQuery.isFetching}
                        />
                        <Input
                          value={requestedBy}
                          onChange={(e) => setRequestedBy(e.target.value)}
                          placeholder="操作人（可选）"
                        />
                        <Button
                          block
                          type="primary"
                          disabled={!selectedModelId || selectedRowKeys.length === 0}
                          loading={bindMutation.isPending}
                          onClick={() => bindMutation.mutate()}
                        >
                          绑定所选（{selectedRowKeys.length}）
                        </Button>
                        <Text type="secondary">
                          提示：请在右侧列表勾选未绑定SKU后执行；不会覆盖已有绑定。
                        </Text>
                      </Space>
                    ),
                  },
                  {
                    key: 'auto',
                    label: '自动',
                    children: (
                      <Space direction="vertical" style={{ width: '100%' }}>
                        <Text type="secondary">
                          默认规则：仅对 model_code_hint 唯一命中“已发布标准模型”的SKU自动绑定。
                        </Text>
                        <Input
                          value={requestedBy}
                          onChange={(e) => setRequestedBy(e.target.value)}
                          placeholder="操作人（可选）"
                        />
                        <Button
                          block
                          loading={autoPreviewMutation.isPending}
                          onClick={() => autoPreviewMutation.mutate()}
                        >
                          预览命中范围
                        </Button>
                        <Button
                          block
                          type="primary"
                          loading={autoExecuteMutation.isPending}
                          onClick={() => autoExecuteMutation.mutate()}
                        >
                          执行自动绑定
                        </Button>
                        {autoPreviewText ? <Alert type="info" showIcon message={autoPreviewText} /> : null}
                        {autoCandidatesOnly ? (
                          <Button
                            block
                            onClick={() => {
                              setAutoCandidatesOnly(false)
                              setAutoPreviewCandidates([])
                              setSelectedRowKeys([])
                              // 恢复用户偏好分页（已持久化）
                              setPage(1)
                              message.info('已退出“命中候选”视图')
                            }}
                          >
                            退出命中候选视图
                          </Button>
                        ) : null}
                      </Space>
                    ),
                  },
                ]}
              />
            </Card>

            <Card size="small" title="规则/预设（占位）">
              <Space direction="vertical" style={{ width: '100%' }}>
                <Text type="secondary">后续这里放“规则保存/预设”，避免重复调试。</Text>
                <Button block disabled>
                  新建规则（待接）
                </Button>
                <Button block disabled>
                  管理预设（待接）
                </Button>
              </Space>
            </Card>

            <Card size="small" title="导入（可选）">
              <Space direction="vertical" style={{ width: '100%' }}>
            <Space wrap>
              <Upload
                accept=".xlsx"
                beforeUpload={(file) => {
                  setUploadFile(file as File)
                  return false
                }}
                fileList={uploadFile ? ([{ uid: '1', name: uploadFile.name }] as any) : []}
                    onRemove={() => setUploadFile(null)}
                maxCount={1}
              >
                    <Button>选择xlsx</Button>
              </Upload>
              <Input
                    style={{ width: 180 }}
                    placeholder="requested_by"
                value={requestedBy}
                onChange={(e) => setRequestedBy(e.target.value)}
              />
                </Space>
                <Button type="primary" block loading={uploading} onClick={handleImport}>
                  导入SKU主档
              </Button>
            </Space>
          </Card>
          </Space>
        </Col>

        {/* 右侧：筛选 + 列表（3/4） */}
        <Col xs={24} lg={18}>
          <Card
            title="SKU 列表"
            extra={
              <Space wrap>
                {autoCandidatesOnly ? (
                  <Tag color="purple">命中候选视图：{autoPreviewCandidates.length} 条</Tag>
                ) : null}
                <Input
                  style={{ width: 260 }}
                  placeholder="搜索：条码/名称/编码"
                  value={search}
                  onChange={(e) => {
                    setSearch(e.target.value)
                    setPage(1)
                  }}
                  disabled={autoCandidatesOnly}
                />
                <Input
                  style={{ width: 220 }}
                  placeholder="规格关键字（仅当前页过滤）"
                  value={specKeyword}
                  onChange={(e) => setSpecKeyword(e.target.value)}
                />
                <Select
                  allowClear
                  style={{ width: 160 }}
                  placeholder="渠道"
                  options={channelOptions}
                  value={channel}
                  onChange={(v) => {
                    setChannel(v)
                    setPage(1)
                  }}
                  disabled={autoCandidatesOnly}
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
                  disabled={autoCandidatesOnly}
                />
                <Tag color="blue">总数：{total}</Tag>
                <Tag>
                  本页：{pageStats.totalRows} ERP匹配填充率：{pageStats.erpMatchedRate} 对接就绪率：
                  {pageStats.linkedRate} 字段齐全率：{pageStats.completeRate}
                </Tag>
                {/* exit button moved to tabs (after 已绑定) */}
              </Space>
            }
          >
            {autoCandidatesOnly ? (
              <Alert
                type="info"
                showIcon
                style={{ marginBottom: 8 }}
                message="当前为“命中候选视图”：仅展示自动预览命中的候选记录；要看全部/未绑定/已绑定，请点击右上角“退出候选视图”。"
              />
            ) : null}
            <Tabs
              activeKey={listTab}
              onChange={(k) => setListTab(k as any)}
              items={[
                { key: 'all', label: '全部', children: null },
                { key: 'unbound', label: '未绑定', children: null },
                { key: 'bound', label: '已绑定', children: null },
              ]}
              tabBarExtraContent={
                autoCandidatesOnly ? (
                  <Button
                    size="small"
                    type="link"
                    onClick={() => {
                      setAutoCandidatesOnly(false)
                      setAutoPreviewCandidates([])
                      setSelectedRowKeys([])
                      setPage(1)
                      message.info('已退出“命中候选视图”')
                    }}
                  >
                    退出命中候选视图
                  </Button>
                ) : null
              }
            />
            <Table
              rowKey="id"
              size="small"
              loading={listQuery.isFetching}
              columns={columns}
              dataSource={filteredItems}
              rowSelection={{
                selectedRowKeys,
                onChange: (keys) => setSelectedRowKeys((keys ?? []) as string[]),
              }}
              pagination={{
                current: page,
                pageSize,
                total,
                showSizeChanger: true,
              }}
              onChange={handlePaginationChange}
              scroll={{ x: 1350 }}
            />
          </Card>
        </Col>
      </Row>

      <Drawer
        title="SKU 主档详情（只读）"
        open={drawerOpen}
        width={980}
        onClose={() => {
          setDrawerOpen(false)
          setActiveId(null)
        }}
      >
        {detailQuery.data ? (
          <Row gutter={[16, 16]}>
            <Col span={14}>
              <Descriptions bordered size="small" column={2}>
                <Descriptions.Item label="erp_sku_barcode">
                  {detailQuery.data.erp_sku_barcode}
                </Descriptions.Item>
                <Descriptions.Item label="channel">{detailQuery.data.channel ?? '-'}</Descriptions.Item>
                <Descriptions.Item label="商品名称（网店）" span={2}>
                  {detailQuery.data.product_name ?? '-'}
                </Descriptions.Item>
                <Descriptions.Item label="商品编码（网店）">
                  {detailQuery.data.product_code ?? '-'}
                </Descriptions.Item>
                <Descriptions.Item label="平台商品Id（网店）">
                  {detailQuery.data.platform_product_id ?? '-'}
                </Descriptions.Item>
                <Descriptions.Item label="平台规格Id（网店）">
                  {detailQuery.data.platform_sku_id ?? '-'}
                </Descriptions.Item>
                <Descriptions.Item label="ERP匹配状态（网店↔ERP）">
                  {detailQuery.data.match_status ?? '-'}
                </Descriptions.Item>
                <Descriptions.Item label="spec_text" span={2}>
                  {detailQuery.data.spec_text ?? '-'}
                </Descriptions.Item>
                <Descriptions.Item label="model_code_hint">
                  {detailQuery.data.model_code_hint ?? '-'}
                </Descriptions.Item>
                <Descriptions.Item label="erp_spec_hash">
                  {detailQuery.data.erp_spec_hash ?? '-'}
                </Descriptions.Item>
                <Descriptions.Item label="对接状态（本系统）">
                  {detailQuery.data.active_model_version_id ? (
                    <Tag color="green">已绑定</Tag>
                  ) : (
                    <Tag color="red">未绑定</Tag>
                  )}
                </Descriptions.Item>
                <Descriptions.Item label="active_model_version_id">
                  {detailQuery.data.active_model_version_id ?? '-'}
                </Descriptions.Item>
                <Descriptions.Item label="已绑定模型">
                  {detailQuery.data.bound_model_code ? (
                    <Space size={6}>
                      <Tag color="blue">{detailQuery.data.bound_model_code}</Tag>
                      <span>{detailQuery.data.bound_model_name || ''}</span>
                    </Space>
                  ) : (
                    '-'
                  )}
                </Descriptions.Item>
                <Descriptions.Item label="已绑定版本">
                  {detailQuery.data.bound_version_label || detailQuery.data.bound_version_kind ? (
                    <Space size={6}>
                      {detailQuery.data.bound_version_kind ? <Tag>{detailQuery.data.bound_version_kind}</Tag> : null}
                      {detailQuery.data.bound_version_status ? (
                        <Tag>{detailQuery.data.bound_version_status}</Tag>
                      ) : null}
                      <span>{detailQuery.data.bound_version_label || '-'}</span>
                    </Space>
                  ) : (
                    '-'
                  )}
                </Descriptions.Item>
                <Descriptions.Item label="规格差异（ERP vs 最近发货）">
                  {detailQuery.data.spec_mismatch ? <Tag color="orange">有差异</Tag> : <Tag>无</Tag>}
                </Descriptions.Item>
                <Descriptions.Item label="last_shipment_spec_hash">
                  {detailQuery.data.last_shipment_spec_hash ?? '-'}
                </Descriptions.Item>
                <Descriptions.Item label="source_updated_at">
                  {formatTime(detailQuery.data.source_updated_at ?? null)}
                </Descriptions.Item>
                <Descriptions.Item label="created_at">
                  {formatTime(detailQuery.data.created_at)}
                </Descriptions.Item>
                <Descriptions.Item label="updated_at">
                  {formatTime(detailQuery.data.updated_at)}
                </Descriptions.Item>
              </Descriptions>
            </Col>
            <Col span={10}>
              <Card size="small" title="图片预览（如有）">
                <Space direction="vertical" style={{ width: '100%' }}>
                  {safeString((detailQuery.data.images_json as any)?.product_image) ? (
                    <Image
                      width={260}
                      src={safeString((detailQuery.data.images_json as any)?.product_image)}
                    />
                  ) : (
                    <Text type="secondary">无商品图片</Text>
                  )}
                  {safeString((detailQuery.data.images_json as any)?.spec_image) ? (
                    <Image
                      width={260}
                      src={safeString((detailQuery.data.images_json as any)?.spec_image)}
                    />
                  ) : (
                    <Text type="secondary">无规格图片</Text>
                  )}
                </Space>
              </Card>
              <Card size="small" title="解析摘要（MVP）" style={{ marginTop: 12 }}>
                <Descriptions bordered size="small" column={1}>
                  <Descriptions.Item label="ERP 解析版本">
                    {detailQuery.data.erp_parser_version ?? '-'}
                  </Descriptions.Item>
                  <Descriptions.Item label="ERP 尺寸">
                    {safeString((detailQuery.data.erp_dimensions as any)?.width_cm) ||
                    safeString((detailQuery.data.erp_dimensions as any)?.height_cm) ? (
                      <span>
                        {safeString((detailQuery.data.erp_dimensions as any)?.width_cm) || '?'} ×{' '}
                        {safeString((detailQuery.data.erp_dimensions as any)?.height_cm) || '?'} cm
                      </span>
                    ) : (
                      '-'
                    )}
                  </Descriptions.Item>
                  <Descriptions.Item label="ERP tokens（前10）">
                    {(detailQuery.data.erp_tokens ?? []).slice(0, 10).join('；') || '-'}
                  </Descriptions.Item>
                  <Descriptions.Item label="最近发货规格（如有）">
                    {detailQuery.data.last_shipment_spec_text ?? '-'}
                  </Descriptions.Item>
                  <Descriptions.Item label="规格差异时间">
                    {detailQuery.data.spec_mismatch_at ? formatTime(detailQuery.data.spec_mismatch_at) : '-'}
                  </Descriptions.Item>
                </Descriptions>
              </Card>
              <Card size="small" title="metadata_json" style={{ marginTop: 12 }}>
                <pre style={{ margin: 0, whiteSpace: 'pre-wrap' }}>
                  {jsonPretty(detailQuery.data.metadata_json)}
                </pre>
              </Card>
            </Col>
          </Row>
        ) : detailQuery.isFetching ? (
          <Text>加载中...</Text>
        ) : (
          <Alert type="info" showIcon message="未选择记录" />
        )}
      </Drawer>
    </div>
  )
}

export default SkuMasterWorkspacePage


