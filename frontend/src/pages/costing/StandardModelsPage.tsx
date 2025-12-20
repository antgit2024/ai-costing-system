import { useMemo, useState } from 'react'
import { Button, Card, Input, Space, Table, Tag } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useQuery } from '@tanstack/react-query'

import { fetchProductModelVersionsPaged } from '@/services/planner'
import type { ProductModelVersionListItem } from '@/types/planner'
import ProductModelEditorDrawer from '@/components/costing/ProductModelEditorDrawer'

export default function StandardModelsPage() {
  const [search, setSearch] = useState('')
  const [page] = useState(1)
  const [pageSize] = useState(50)

  const [editorOpen, setEditorOpen] = useState(false)
  const [editingModelId, setEditingModelId] = useState<string | null>(null)
  const [editingVersionId, setEditingVersionId] = useState<string | null>(null)

  const params = useMemo(
    () => ({
      search: search || undefined,
      version_kind: 'standard',
      page,
      page_size: pageSize,
    }),
    [page, pageSize, search],
  )

  const listQuery = useQuery({
    queryKey: ['standardModelVersions', params],
    queryFn: () => fetchProductModelVersionsPaged(params),
  })

  const columns: ColumnsType<ProductModelVersionListItem> = [
    { title: '三位编码', dataIndex: 'model_code', width: 100 },
    { title: '模型名称', dataIndex: 'model_name', width: 180 },
    { title: '版本号', dataIndex: 'version_label', width: 220, render: (v) => v ?? '-' },
    { title: '版本类型', dataIndex: 'version_kind', width: 90, render: (v) => <Tag>{v}</Tag> },
    { title: '版本状态', dataIndex: 'version_status', width: 110, render: (v) => <Tag>{v}</Tag> },
    { title: '更新时间', dataIndex: 'updated_at', width: 180 },
    {
      title: '操作',
      width: 120,
      render: (_, r) => (
        <Button
          type="primary"
          onClick={() => {
            setEditingModelId(r.model_id)
            setEditingVersionId(r.version_id)
            setEditorOpen(true)
          }}
        >
          编辑
        </Button>
      ),
    },
  ]

  return (
    <Space direction="vertical" size={12} style={{ width: '100%' }}>
      <Card size="small" title="标准模型（版本列表）">
        <Space wrap>
          <Input.Search
            allowClear
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onSearch={() => listQuery.refetch()}
            placeholder="搜索三位编码 / 模型名 / 版本号"
            style={{ width: 420 }}
          />
        </Space>
      </Card>

      <Card>
        <Table
          rowKey={(r) => r.version_id}
          loading={listQuery.isLoading}
          dataSource={(listQuery.data as any)?.items ?? []}
          columns={columns}
          pagination={false}
        />
      </Card>

      <ProductModelEditorDrawer
        open={editorOpen}
        onClose={() => setEditorOpen(false)}
        entryContext="standard"
        modelId={editingModelId}
        initialVersionId={editingVersionId}
      />
    </Space>
  )
}


