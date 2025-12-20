import { useMemo, useState } from 'react'
import { Button, Card, Input, Space, Table, Tag } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useQuery } from '@tanstack/react-query'

import { fetchProductModels } from '@/services/planner'
import type { ProductModel } from '@/types/planner'
import ProductModelEditorDrawer from '@/components/costing/ProductModelEditorDrawer'

export default function SampleModelsPage() {
  const [search, setSearch] = useState('')
  const [editorOpen, setEditorOpen] = useState(false)
  const [editingModelId, setEditingModelId] = useState<string | null>(null)

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

  return (
    <Space direction="vertical" size={12} style={{ width: '100%' }}>
      <Card size="small" title="打样模型">
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

      <Card>
        <Table
          rowKey="id"
          loading={listQuery.isLoading}
          dataSource={(listQuery.data as any)?.items ?? []}
          columns={columns}
          pagination={false}
        />
      </Card>

      <ProductModelEditorDrawer
        open={editorOpen}
        onClose={() => setEditorOpen(false)}
        entryContext="sample"
        modelId={editingModelId}
      />
    </Space>
  )
}


