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
import { useMemo, useState } from 'react'
import { keepPreviousData, useQuery, useQueryClient } from '@tanstack/react-query'

import { fetchSkuMaster, fetchSkuMasterDetail, importSkuMasterXlsx } from '@/services/planner'
import type { SkuMaster } from '@/types/planner'

const { Title, Text } = Typography

const DEFAULT_PAGE_SIZE = 10

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
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE)
  const [search, setSearch] = useState<string>('')
  const [specKeyword, setSpecKeyword] = useState<string>('') // MVP: client-side filter on current page
  const [channel, setChannel] = useState<string | undefined>(undefined)
  const [matchStatus, setMatchStatus] = useState<string | undefined>(undefined)

  const [uploading, setUploading] = useState(false)
  const [uploadFile, setUploadFile] = useState<File | null>(null)
  const [requestedBy, setRequestedBy] = useState<string>('planner_user')

  const [drawerOpen, setDrawerOpen] = useState(false)
  const [activeId, setActiveId] = useState<string | null>(null)

  const listQuery = useQuery({
    queryKey: ['sku-master', 'list', page, pageSize, search, channel, matchStatus],
    queryFn: () =>
      fetchSkuMaster({
        page,
        page_size: pageSize,
        search: search || undefined,
        channel,
        match_status: matchStatus,
      }),
    placeholderData: keepPreviousData,
  })

  const items = listQuery.data?.items ?? []
  const total = listQuery.data?.total ?? 0

  const filteredItems = useMemo(() => {
    const kw = specKeyword.trim()
    if (!kw) return items
    return items.filter((x) => (x.spec_text ?? '').includes(kw))
  }, [items, specKeyword])

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
      width: 180,
      ellipsis: true,
      render: (v) => safeString(v) || '-',
    },
    {
      title: '销售渠道',
      dataIndex: 'channel',
      width: 140,
      ellipsis: true,
      render: (v) => safeString(v) || '-',
    },
    {
      title: '商品规格（网店）',
      dataIndex: 'spec_text',
      width: 220,
      ellipsis: true,
      render: (v) => safeString(v) || '-',
    },
    {
      title: '模型提示',
      dataIndex: 'model_code_hint',
      width: 120,
      ellipsis: true,
      render: (v) => safeString(v) || '-',
    },
    {
      title: '对接状态（本系统）',
      dataIndex: 'active_model_version_id',
      width: 240,
      render: (v, record) => {
        const bound = isFilled(v as any)
        const source = safeString((record.metadata_json as any)?.source)
        const srcTag =
          source === 'shipment_autobackfill' ? <Tag color="gold">发货回写</Tag> : <Tag>ERP导入</Tag>
        return (
          <Space size={6}>
            {bound ? <Tag color="green">已绑定</Tag> : <Tag color="red">未绑定</Tag>}
            {record.spec_mismatch ? <Tag color="orange">规格差异</Tag> : null}
            {record.bound_model_code ? <Tag color="blue">{record.bound_model_code}</Tag> : null}
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
                items={[
                  {
                    key: 'auto',
                    label: '自动',
                    children: (
                      <Space direction="vertical" style={{ width: '100%' }}>
                        <Text type="secondary">
                          自动绑定仅建议用于“确定性强”的规则（如 spec_text 中的 model_code_hint 唯一命中已发布标准版本）。
                        </Text>
                        <Button block disabled>
                          预览命中范围（待接）
                        </Button>
                        <Button block type="primary" disabled>
                          执行自动绑定（待接）
                        </Button>
                      </Space>
                    ),
                  },
                  {
                    key: 'manual',
                    label: '手工',
                    children: (
                      <Space direction="vertical" style={{ width: '100%' }}>
                        <Text type="secondary">面向“未绑定/不确定”的SKU，人工选择已发布标准版本并批量绑定。</Text>
                        <Button block disabled>
                          批量绑定所选（待接）
                        </Button>
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
                <Input
                  style={{ width: 260 }}
                  placeholder="搜索：条码/名称/编码"
                  value={search}
                  onChange={(e) => {
                    setSearch(e.target.value)
                    setPage(1)
                  }}
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
                <Tag>
                  本页：{pageStats.totalRows} ERP匹配填充率：{pageStats.erpMatchedRate} 对接就绪率：
                  {pageStats.linkedRate} 字段齐全率：{pageStats.completeRate}
                </Tag>
              </Space>
            }
          >
            <Tabs
              items={[
                { key: 'all', label: '全部', children: null },
                { key: 'unbound', label: '未绑定', children: null },
                { key: 'mismatch', label: '规格差异', children: null },
              ]}
            />
            <Table
              rowKey="id"
              size="small"
              loading={listQuery.isFetching}
              columns={columns}
              dataSource={filteredItems}
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


