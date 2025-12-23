import { useEffect, useMemo, useState } from 'react'
import { Button, Card, Col, Input, Modal, Row, Space, Table, Tag, Typography, message } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useQuery } from '@tanstack/react-query'
import { useLocation, useNavigate } from 'react-router-dom'

import { createProductModel, createProductModelVersion, fetchProductModelVersionsPaged } from '@/services/planner'
import type { ProductModelVersionListItem } from '@/types/planner'
import ProductModelEditorDrawer from '@/components/costing/ProductModelEditorDrawer'

const { Title, Text } = Typography

export default function StandardModelsPage() {
  const location = useLocation() as any
  const navigate = useNavigate()
  const [search, setSearch] = useState('')
  const [page] = useState(1)
  const [pageSize] = useState(50)

  const [editorOpen, setEditorOpen] = useState(false)
  const [editingModelId, setEditingModelId] = useState<string | null>(null)
  const [editingVersionId, setEditingVersionId] = useState<string | null>(null)
  const [createModalOpen, setCreateModalOpen] = useState(false)
  const [createName, setCreateName] = useState<string>('未命名标准模型')
  const [creating, setCreating] = useState(false)

  useEffect(() => {
    const st = (location as any)?.state ?? {}
    const openModelId = String(st?.openModelId ?? '').trim()
    const openVersionId = String(st?.openVersionId ?? '').trim()
    if (!openModelId || !openVersionId) return

    setEditingModelId(openModelId)
    setEditingVersionId(openVersionId)
    setEditorOpen(true)
    // 清掉 state，避免刷新/返回时重复弹抽屉
    navigate(location.pathname, { replace: true, state: null })
  }, [location, navigate])

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

  const handleGuideToDerive = () => {
    Modal.info({
      title: '推荐做法：从打样推导标准模型',
      content: (
        <div>
          <div style={{ marginBottom: 8 }}>
            标准模型建议由打样版本推导生成，避免直接新建造成口径不一致。
          </div>
          <div style={{ marginBottom: 8 }}>
            操作路径：进入“打样模型” → 进入打样管理 → 选择打样版本 → 点击“推导标准模型”。
          </div>
        </div>
      ),
      okText: '前往打样模型',
      onOk: () => navigate('/costing/sample-models'),
    })
  }

  const handleCreateStandardDirect = async () => {
    if (creating) return
    const name = String(createName || '').trim()
    if (!name) {
      message.warning('请输入模型名称')
      return
    }
    setCreating(true)
    try {
      const model = await createProductModel({
        model_name: name,
        metadata_json: { created_from: 'ui', entry_context: 'standard', note: 'direct_create_standard' },
      })
      const version = await createProductModelVersion(model.id, { version_kind: 'standard', metadata_json: {} } as any)
      message.success(`已创建标准模型：${model.model_code}`)
      setCreateModalOpen(false)
      setEditingModelId(model.id)
      setEditingVersionId(version.id)
      setEditorOpen(true)
      await listQuery.refetch()
    } catch (err: any) {
      message.error(err?.response?.data?.detail ?? '新建标准模型失败')
    } finally {
      setCreating(false)
    }
  }

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between' }}>
        <div>
          <Title level={3} style={{ marginBottom: 4 }}>
            标准模型
          </Title>
          <Text type="secondary">标准模型以“标准版本（100×100cm×1）”为核算单元，支持发布与SKU绑定。</Text>
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
                placeholder="搜索三位编码 / 模型名 / 版本号"
                style={{ width: 420 }}
              />
            </Space>
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card size="small" title="操作">
            <Space wrap>
              <Button type="primary" onClick={handleGuideToDerive}>
                从打样推导（推荐）
              </Button>
              <Button onClick={() => setCreateModalOpen(true)}>直接新建标准（高级）</Button>
              <Button onClick={() => listQuery.refetch()}>刷新</Button>
            </Space>
          </Card>
        </Col>

        <Col span={24}>
          <Card>
            <Table
              rowKey={(r) => r.version_id}
              loading={listQuery.isLoading}
              dataSource={(listQuery.data as any)?.items ?? []}
              columns={columns}
              pagination={false}
              scroll={{ x: 980 }}
            />
          </Card>
        </Col>
      </Row>

      <Modal
        title="直接新建标准模型（高级）"
        open={createModalOpen}
        okText="创建并进入"
        cancelText="取消"
        confirmLoading={creating}
        onOk={handleCreateStandardDirect}
        onCancel={() => {
          if (creating) return
          setCreateModalOpen(false)
        }}
      >
        <Space direction="vertical" style={{ width: '100%' }}>
          <Input value={createName} onChange={(e) => setCreateName(e.target.value)} placeholder="模型名称（必填）" />
          <Text type="secondary">
            注意：专业建议走“从打样推导”。仅在明确无需打样口径/模板推导时，才使用直接新建。
          </Text>
        </Space>
      </Modal>

      <ProductModelEditorDrawer
        open={editorOpen}
        onClose={() => setEditorOpen(false)}
        entryContext="standard"
        modelId={editingModelId}
        initialVersionId={editingVersionId}
      />
    </div>
  )
}













