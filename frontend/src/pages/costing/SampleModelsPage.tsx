import { useMemo, useState } from 'react'
import dayjs from 'dayjs'
import { Button, Card, Col, Input, Modal, Row, Select, Space, Switch, Table, Tag, Tooltip, Typography, message } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useQuery } from '@tanstack/react-query'

import { archiveSampleVersionsOnly, createProductModel, fetchProductModels, fetchTaxonomyItems } from '@/services/planner'
import type { ProductModel } from '@/types/planner'
import ProductModelEditorDrawer from '@/components/costing/ProductModelEditorDrawer'

const { Title, Text } = Typography

export default function SampleModelsPage() {
  const [search, setSearch] = useState('')
  const [category, setCategory] = useState<string | undefined>(undefined)
  const [includeArchived, setIncludeArchived] = useState(false)
  const [editorOpen, setEditorOpen] = useState(false)
  const [editingModelId, setEditingModelId] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [createModalOpen, setCreateModalOpen] = useState(false)
  const [createName, setCreateName] = useState<string>('未命名打样模型')

  const params = useMemo(
    () => ({
      search: search || undefined,
      category: category || undefined,
      include_archived: includeArchived || undefined,
      page: 1,
      page_size: 50,
    }),
    [category, includeArchived, search],
  )

  const listQuery = useQuery({
    queryKey: ['sampleModels', params],
    queryFn: () => fetchProductModels(params as any),
  })

  const taxonomyCategoryQuery = useQuery({
    queryKey: ['taxonomy-items', 'product_model_category', 'sample-models'],
    queryFn: () => fetchTaxonomyItems('product_model_category', { include_inactive: true }),
  })

  const listItems = useMemo(() => {
    // 打样列表：只展示“打样入口”或“存在打样版本”的模型。
    // 目的：确保标准模型不会“自动出现在打样模型列表”，只有存在打样版本才会出现。
    const raw = ((((listQuery.data as any)?.items ?? []) as any[]) || []).slice()
    return raw.filter((r: any) => {
      const meta: any = r?.metadata_json ?? {}
      const entry = String(meta?.entry_context ?? '').trim().toLowerCase()
      const sampleCnt = Number((r as any)?.sample_version_count ?? 0)
      const hasLatestSample = Boolean(String((r as any)?.latest_sample_version_id ?? '').trim())
      return entry === 'sample' || (Number.isFinite(sampleCnt) && sampleCnt > 0) || hasLatestSample
    })
  }, [listQuery.data])

  const handleDeleteModel = async (model: ProductModel) => {
    Modal.confirm({
      title: '删除打样',
      content: `确认删除（归档）打样版本：${model.model_code} - ${model.model_name}？（不会影响标准版本）`,
      okText: '删除打样',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        try {
          await archiveSampleVersionsOnly(model.id)
          message.success('已删除打样（归档打样版本）')
          await listQuery.refetch()
        } catch (err: any) {
          message.error(err?.response?.data?.detail ?? err?.message ?? '删除失败')
        }
      },
    })
  }

  const columns: ColumnsType<ProductModel> = [
    {
      title: '缩略图',
      width: 72,
      render: (_: any, r: any) => {
        const vid = String((r as any)?.latest_sample_version_id ?? '').trim()
        const has = !!vid
        const url = has ? `/api/planner/product-model-versions/${vid}/images/0` : ''
        return (
          <div
            style={{
              width: 48,
              height: 48,
              borderRadius: 8,
              background: 'var(--app-surface)',
              border: '1px solid var(--app-border)',
              overflow: 'hidden',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            {has ? (
              <img
                src={url}
                alt={String(r.model_name || r.model_code || 'sample-model')}
                width={48}
                height={48}
                loading="lazy"
                decoding="async"
                style={{ objectFit: 'cover', display: 'block' }}
                onError={(e) => {
                  ;(e.currentTarget as HTMLImageElement).style.visibility = 'hidden'
                }}
              />
            ) : (
              <span>-</span>
            )}
          </div>
        )
      },
    },
    { title: '总编码', dataIndex: 'model_code', width: 120 },
    { title: '模型名称', dataIndex: 'model_name' },
    { title: '品类', dataIndex: 'category', width: 140, render: (v: any) => String(v ?? '').trim() || '-' },
    {
      title: '入口',
      width: 90,
      render: (_: any, r: any) => {
        const meta: any = (r as any)?.metadata_json ?? {}
        const entry = String(meta?.entry_context ?? '').trim() || '-'
        return <Tag>{entry}</Tag>
      },
    },
    {
      title: '打样人',
      width: 120,
      render: (_: any, r: any) => {
        const meta: any = (r as any)?.metadata_json ?? {}
        const owner = String(meta?.sample_owner ?? '').trim()
        return owner || '-'
      },
    },
    { title: '状态', dataIndex: 'status', width: 110, render: (v: string) => <Tag>{v}</Tag> },
    { title: '打样版本数', width: 110, render: (_, r) => (r.sample_version_count ?? '-') },
    { title: '标准版本数', width: 110, render: (_, r) => (r.standard_version_count ?? '-') },
    { title: '当前发布标准', width: 180, render: (_, r) => r.current_published_standard_version_label ?? '-' },
    {
      title: '更新时间',
      dataIndex: 'updated_at',
      width: 170,
      render: (v: any) => {
        const s = String(v ?? '').trim()
        if (!s) return '-'
        const d = dayjs(s)
        return d.isValid() ? d.format('YYYY-MM-DD HH:mm') : s
      },
    },
    {
      title: '操作',
      width: 240,
      render: (_, r) => (
        <Space>
          <Button
            type="primary"
            onClick={() => {
              setEditingModelId(r.id)
              setEditorOpen(true)
            }}
          >
            管理
          </Button>
          <Tooltip title="删除为“归档删除”。规则：存在已发布标准版本或存在SKU绑定则不允许删除；否则允许删除。">
            <Button danger disabled={Boolean((r as any).current_published_standard_version_id)} onClick={() => handleDeleteModel(r)}>
              删除
            </Button>
          </Tooltip>
        </Space>
      ),
    },
  ]

  const handleCreate = async () => {
    if (creating) return
    const name = String(createName || '').trim()
    if (!name) {
      message.warning('请输入模型名称')
      return
    }
    setCreating(true)
    try {
      const created = await createProductModel({
        model_name: name,
        metadata_json: { created_from: 'ui', entry_context: 'sample' },
      })
      message.success(`已创建：${created.model_code}`)
      setCreateModalOpen(false)
      setEditingModelId(created.id)
      setEditorOpen(true)
      await listQuery.refetch()
    } catch (err: any) {
      message.error(err?.response?.data?.detail ?? '新建打样模型失败')
    } finally {
      setCreating(false)
    }
  }

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between' }}>
        <div>
          <Title level={3} style={{ marginBottom: 4 }}>
            打样模型
          </Title>
          <Text type="secondary">用于打样版本管理，并可从打样版本推导生成标准版本。</Text>
        </div>
      </div>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} lg={12}>
          <Card size="small" title="筛选">
            <Space wrap>
              <Input.Search
                allowClear
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                onSearch={() => listQuery.refetch()}
                placeholder="搜索总编码 / 名称"
                style={{ width: 360 }}
              />
              <Select
                allowClear
                showSearch
                optionFilterProp="label"
                placeholder="品类"
                style={{ width: 200 }}
                value={category}
                onChange={(v) => setCategory(v ?? undefined)}
                options={(taxonomyCategoryQuery.data?.items ?? []).map((it: any) => ({ label: it.name, value: it.name }))}
              />
              <Space size={6}>
                <Switch checked={includeArchived} onChange={setIncludeArchived} />
                <Text type="secondary">显示已归档</Text>
              </Space>
            </Space>
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card size="small" title="操作">
            <Space wrap>
              <Button type="primary" onClick={() => setCreateModalOpen(true)}>
                新建打样模型
              </Button>
              <Button onClick={() => listQuery.refetch()}>刷新</Button>
            </Space>
          </Card>
        </Col>

        <Col span={24}>
          <Card>
            <Table
              rowKey="id"
              loading={listQuery.isLoading}
              dataSource={listItems}
              columns={columns}
              pagination={false}
              scroll={{ x: 1100 }}
            />
          </Card>
        </Col>
      </Row>

      <Modal
        title="新建打样模型"
        open={createModalOpen}
        okText="创建并进入"
        cancelText="取消"
        confirmLoading={creating}
        onOk={handleCreate}
        onCancel={() => {
          if (creating) return
          setCreateModalOpen(false)
        }}
      >
        <Space direction="vertical" style={{ width: '100%' }}>
          <Input
            value={createName}
            onChange={(e) => setCreateName(e.target.value)}
            placeholder="模型名称（必填）"
          />
          <Text type="secondary">创建后会自动生成一个草稿打样版本，进入抽屉继续配置物料/工序。</Text>
        </Space>
      </Modal>

      <ProductModelEditorDrawer
        open={editorOpen}
        onClose={() => setEditorOpen(false)}
        entryContext="sample"
        modelId={editingModelId}
        includeArchived={includeArchived}
      />
    </div>
  )
}


