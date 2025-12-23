import { useMemo, useState } from 'react'
import { Button, Card, Col, Input, Modal, Row, Space, Table, Tag, Typography, message } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useQuery } from '@tanstack/react-query'

import { createProductModel, fetchProductModels } from '@/services/planner'
import type { ProductModel } from '@/types/planner'
import ProductModelEditorDrawer from '@/components/costing/ProductModelEditorDrawer'

const { Title, Text } = Typography

export default function SampleModelsPage() {
  const [search, setSearch] = useState('')
  const [editorOpen, setEditorOpen] = useState(false)
  const [editingModelId, setEditingModelId] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [createModalOpen, setCreateModalOpen] = useState(false)
  const [createName, setCreateName] = useState<string>('未命名打样模型')

  const params = useMemo(
    () => ({
      search: search || undefined,
      page: 1,
      page_size: 50,
    }),
    [search],
  )

  const listQuery = useQuery({
    queryKey: ['sampleModels', params],
    queryFn: () => fetchProductModels(params as any),
  })

  const columns: ColumnsType<ProductModel> = [
    { title: '总编码', dataIndex: 'model_code', width: 120 },
    { title: '模型名称', dataIndex: 'model_name' },
    { title: '状态', dataIndex: 'status', width: 110, render: (v: string) => <Tag>{v}</Tag> },
    { title: '打样版本数', width: 110, render: (_, r) => (r.sample_version_count ?? '-') },
    { title: '标准版本数', width: 110, render: (_, r) => (r.standard_version_count ?? '-') },
    { title: '当前发布标准', width: 180, render: (_, r) => r.current_published_standard_version_label ?? '-' },
    { title: '更新时间', dataIndex: 'updated_at', width: 180 },
    {
      title: '操作',
      width: 140,
      render: (_, r) => (
        <Button
          type="primary"
          onClick={() => {
            setEditingModelId(r.id)
            setEditorOpen(true)
          }}
        >
          进入打样管理
        </Button>
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
              dataSource={(listQuery.data as any)?.items ?? []}
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
      />
    </div>
  )
}


