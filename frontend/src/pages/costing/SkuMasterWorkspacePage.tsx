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
    const matched = rows.filter((x) => isFilled(x.match_status)).length
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
      matched,
      complete,
      matchedRate: rate(matched),
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
      title: '商品名称（网店）',
      dataIndex: 'product_name',
      ellipsis: true,
      render: (v) => safeString(v) || '-',
    },
    {
      title: '商品编码（网店）',
      dataIndex: 'product_code',
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
      title: '平台商品Id（网店）',
      dataIndex: 'platform_product_id',
      width: 160,
      ellipsis: true,
      render: (v) => safeString(v) || '-',
    },
    {
      title: '平台规格Id（网店）',
      dataIndex: 'platform_sku_id',
      width: 160,
      ellipsis: true,
      render: (v) => safeString(v) || '-',
    },
    {
      title: '匹配状态',
      dataIndex: 'match_status',
      width: 120,
      render: (v) => {
        const s = safeString(v) || '—'
        const color = s.includes('匹配') || s.includes('命中') || s.toLowerCase().includes('match') ? 'green' : 'default'
        return <Tag color={color}>{s}</Tag>
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
            SKU 主档工作台（MVP）
          </Title>
          <Text type="secondary">
            用于导入 ERP SKU 主档（货品条码为主键），并快速查看命中率/字段齐全情况（MVP 统计以当前页为准）。
          </Text>
        </div>
        <Button onClick={() => listQuery.refetch()}>刷新</Button>
      </div>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col span={24}>
          <Card title="导入 SKU 主档（xlsx）">
            <Alert
              type="info"
              showIcon
              style={{ marginBottom: 12 }}
              message="上传文件：ERP 理 平台商品列表.xlsx"
              description="导入后会写入 sku_master，后续发货导入会优先命中该主档（以货品条码为关联键）。"
            />
            <Space wrap>
              <Upload
                accept=".xlsx"
                beforeUpload={(file) => {
                  setUploadFile(file as File)
                  return false
                }}
                fileList={uploadFile ? ([{ uid: '1', name: uploadFile.name }] as any) : []}
                onRemove={() => {
                  setUploadFile(null)
                }}
                maxCount={1}
              >
                <Button>选择文件</Button>
              </Upload>
              <Input
                style={{ width: 220 }}
                placeholder="requested_by（可选）"
                value={requestedBy}
                onChange={(e) => setRequestedBy(e.target.value)}
              />
              <Button type="primary" loading={uploading} onClick={handleImport}>
                开始导入
              </Button>
            </Space>
          </Card>
        </Col>

        <Col span={24}>
          <Card
            title="SKU 主档列表（分页）"
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
                  style={{ width: 160 }}
                  placeholder="匹配状态"
                  options={matchStatusOptions}
                  value={matchStatus}
                  onChange={(v) => {
                    setMatchStatus(v)
                    setPage(1)
                  }}
                />
                <Tag color="blue">总数：{total}</Tag>
                <Tag>
                  本页：{pageStats.totalRows} 命中率：{pageStats.matchedRate} 字段齐全率：
                  {pageStats.completeRate}
                </Tag>
              </Space>
            }
          >
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
                <Descriptions.Item label="product_name">
                  {detailQuery.data.product_name ?? '-'}
                </Descriptions.Item>
                <Descriptions.Item label="product_code">
                  {detailQuery.data.product_code ?? '-'}
                </Descriptions.Item>
                <Descriptions.Item label="spec_text" span={2}>
                  {detailQuery.data.spec_text ?? '-'}
                </Descriptions.Item>
                <Descriptions.Item label="platform_product_id">
                  {detailQuery.data.platform_product_id ?? '-'}
                </Descriptions.Item>
                <Descriptions.Item label="platform_sku_id">
                  {detailQuery.data.platform_sku_id ?? '-'}
                </Descriptions.Item>
                <Descriptions.Item label="match_status">
                  {detailQuery.data.match_status ?? '-'}
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


