import { Alert, Button, Card, Drawer, Form, Input, Select, Space, Switch, Table, Tag, Typography, message } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useMemo, useState } from 'react'
import { keepPreviousData, useQuery, useQueryClient } from '@tanstack/react-query'

import {
  activateStructureStandard,
  createStructureStandard,
  deactivateStructureStandard,
  fetchStructureStandards,
  updateStructureStandard,
} from '@/services/planner'
import type { StructureStandardRead, StructureStandardStatus } from '@/types/planner'

const { Title, Text } = Typography

const DEFAULT_PAGE_SIZE = 20

type DrawerMode = 'create' | 'edit'

const normalizeSlots = (raw: any): string[] => {
  const arr = Array.isArray(raw) ? raw : raw ? [raw] : []
  const out = arr.map((x: any) => String(x ?? '').trim()).filter(Boolean)
  // de-dup preserve order
  const seen = new Set<string>()
  return out.filter((x) => (seen.has(x) ? false : (seen.add(x), true)))
}

export default function StructureStandardsPage() {
  const queryClient = useQueryClient()
  const [filtersForm] = Form.useForm()
  const [editorForm] = Form.useForm()

  const [filters, setFilters] = useState<{ search?: string; status?: 'all' | StructureStandardStatus }>({
    status: 'all',
  })
  const [pagination, setPagination] = useState({ current: 1, pageSize: DEFAULT_PAGE_SIZE })

  const [drawerOpen, setDrawerOpen] = useState(false)
  const [drawerMode, setDrawerMode] = useState<DrawerMode>('create')
  const [activeRecord, setActiveRecord] = useState<StructureStandardRead | null>(null)
  const [saving, setSaving] = useState(false)

  const listQuery = useQuery({
    queryKey: ['structure-standards', filters, pagination],
    queryFn: () =>
      fetchStructureStandards({
        search: filters.search,
        status: filters.status ?? 'all',
        page: pagination.current,
        page_size: pagination.pageSize,
      }),
    placeholderData: keepPreviousData,
  })

  const handleFilterSubmit = () => {
    const values = filtersForm.getFieldsValue()
    setFilters({
      search: String(values.search ?? '').trim() || undefined,
      status: (values.status ?? 'all') as any,
    })
    setPagination((prev) => ({ ...prev, current: 1 }))
  }

  const handleFilterReset = () => {
    filtersForm.resetFields()
    setFilters({ status: 'all' })
    setPagination({ current: 1, pageSize: DEFAULT_PAGE_SIZE })
  }

  const openCreate = () => {
    setDrawerMode('create')
    setActiveRecord(null)
    editorForm.setFieldsValue({
      code: '',
      name: '',
      slots: [],
      is_active: true,
    })
    setDrawerOpen(true)
  }

  const openEdit = (record: StructureStandardRead) => {
    setDrawerMode('edit')
    setActiveRecord(record)
    editorForm.setFieldsValue({
      code: record.code,
      name: record.name,
      slots: record.slots ?? [],
      is_active: record.status === 'active',
    })
    setDrawerOpen(true)
  }

  const columns: ColumnsType<StructureStandardRead> = useMemo(
    () => [
      {
        title: 'code',
        dataIndex: 'code',
        width: 220,
        render: (v) => <Text code>{String(v ?? '') || '-'}</Text>,
      },
      {
        title: '名称',
        dataIndex: 'name',
        width: 260,
        ellipsis: true,
        render: (v) => String(v ?? '') || '-',
      },
      {
        title: 'slots',
        key: 'slots',
        render: (_, r) => {
          const slots = Array.isArray(r.slots) ? r.slots : []
          if (!slots.length) return <Text type="secondary">-</Text>
          const show = slots.slice(0, 3)
          const rest = slots.length - show.length
          return (
            <Space size={6} wrap>
              {show.map((s) => (
                <Tag
                  key={s}
                  style={{
                    marginInlineEnd: 0,
                    borderRadius: 999,
                    padding: '0 6px',
                    fontSize: 12,
                    lineHeight: '18px',
                  }}
                >
                  {s}
                </Tag>
              ))}
              {rest > 0 ? (
                <Tag
                  style={{
                    marginInlineEnd: 0,
                    borderRadius: 999,
                    padding: '0 6px',
                    fontSize: 12,
                    lineHeight: '18px',
                  }}
                >
                  …+{rest}
                </Tag>
              ) : null}
            </Space>
          )
        },
      },
      {
        title: '状态',
        dataIndex: 'status',
        width: 120,
        render: (v: StructureStandardStatus) => {
          const s = String(v ?? '')
          return <Tag color={s === 'active' ? 'green' : 'default'}>{s}</Tag>
        },
      },
      {
        title: '操作',
        key: 'actions',
        width: 200,
        fixed: 'right',
        render: (_, record) => {
          const isActive = record.status === 'active'
          return (
            <Space size={8}>
              <Button size="small" onClick={() => openEdit(record)}>
                编辑
              </Button>
              {isActive ? (
                <Button
                  size="small"
                  danger
                  onClick={async () => {
                    try {
                      await deactivateStructureStandard(record.id)
                      message.success('已停用')
                      queryClient.invalidateQueries({ queryKey: ['structure-standards'] })
                    } catch (err: any) {
                      message.error(err?.response?.data?.detail ?? err?.message ?? '停用失败（可能需要管理员密钥）')
                    }
                  }}
                >
                  停用
                </Button>
              ) : (
                <Button
                  size="small"
                  type="primary"
                  onClick={async () => {
                    try {
                      await activateStructureStandard(record.id)
                      message.success('已启用')
                      queryClient.invalidateQueries({ queryKey: ['structure-standards'] })
                    } catch (err: any) {
                      message.error(err?.response?.data?.detail ?? err?.message ?? '启用失败（可能需要管理员密钥）')
                    }
                  }}
                >
                  启用
                </Button>
              )}
            </Space>
          )
        },
      },
    ],
    [editorForm, queryClient],
  )

  const handleSave = async () => {
    await editorForm.validateFields()
    const values = editorForm.getFieldsValue()
    const code = String(values.code ?? '').trim()
    const name = String(values.name ?? '').trim()
    const slots = normalizeSlots(values.slots)
    const status: StructureStandardStatus = values.is_active ? 'active' : 'inactive'

    if (drawerMode === 'create') {
      if (!code) {
        message.error('code 必填')
        return
      }
      if (code.length < 3 || code.length > 64) {
        message.error('code 长度需在 3~64')
        return
      }
    }

    setSaving(true)
    try {
      if (drawerMode === 'create') {
        await createStructureStandard({ code, name, slots, status })
        message.success('结构标准已创建')
      } else if (activeRecord) {
        // MVP: 编辑时锁定 code（避免变更唯一键造成引用漂移）
        await updateStructureStandard(activeRecord.id, { name, slots, status })
        message.success('结构标准已更新')
      }
      setDrawerOpen(false)
      queryClient.invalidateQueries({ queryKey: ['structure-standards'] })
    } catch (err: any) {
      message.error(err?.response?.data?.detail ?? err?.message ?? '保存失败（可能需要管理员密钥）')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <div>
        <Title level={3} style={{ marginBottom: 0 }}>
          结构标准（字典）
        </Title>
        <Text type="secondary">
          用于统一维护结构 code/name/slots，避免手填 code 漂移；后续可用于结构地图(slot→模块绑定)与发布校验。
        </Text>
      </div>

      <Card
        title="筛选"
        size="small"
        extra={
          <Space>
            <Button onClick={() => listQuery.refetch()}>刷新</Button>
            <Button type="primary" onClick={openCreate}>
              新增结构标准
            </Button>
          </Space>
        }
      >
        <Form form={filtersForm} layout="inline" onFinish={handleFilterSubmit} initialValues={{ status: 'all' }}>
          <Form.Item name="search" label="搜索">
            <Input.Search
              allowClear
              placeholder="code / name"
              style={{ width: 260 }}
              onSearch={handleFilterSubmit}
            />
          </Form.Item>
          <Form.Item name="status" label="状态">
            <Select
              style={{ width: 160 }}
              options={[
                { label: '全部', value: 'all' },
                { label: '启用', value: 'active' },
                { label: '停用', value: 'inactive' },
              ]}
            />
          </Form.Item>
          <Form.Item>
            <Space>
              <Button type="primary" htmlType="submit">
                查询
              </Button>
              <Button onClick={handleFilterReset}>重置</Button>
            </Space>
          </Form.Item>
        </Form>
        <Alert
          style={{ marginTop: 12 }}
          type="info"
          showIcon
          message="说明"
          description={
            <Text type="secondary">
              当前实现复用后端 Taxonomy：domain=<Text code>structure_standard</Text>；写操作需要管理员密钥（未配置时会报 401/403）。
            </Text>
          }
        />
      </Card>

      <Card size="small">
        <Table<StructureStandardRead>
          rowKey="id"
          size="small"
          loading={listQuery.isFetching}
          columns={columns}
          dataSource={listQuery.data?.items ?? []}
          pagination={{
            current: pagination.current,
            pageSize: pagination.pageSize,
            total: listQuery.data?.total ?? 0,
            showSizeChanger: true,
            onChange: (current, pageSize) => setPagination({ current, pageSize }),
          }}
          scroll={{ x: 1100 }}
        />
      </Card>

      <Drawer
        open={drawerOpen}
        title={drawerMode === 'create' ? '新增结构标准' : '编辑结构标准'}
        width={720}
        onClose={() => setDrawerOpen(false)}
        destroyOnClose
        extra={
          <Space>
            <Button onClick={() => setDrawerOpen(false)}>取消</Button>
            <Button type="primary" loading={saving} onClick={handleSave}>
              保存
            </Button>
          </Space>
        }
      >
        <Form form={editorForm} layout="vertical">
          <Form.Item
            label="code"
            name="code"
            rules={[
              { required: true, message: '请输入 code' },
              { min: 3, max: 64, message: '长度需在 3~64' },
            ]}
          >
            <Input placeholder="例如 pillowcase_v1" disabled={drawerMode === 'edit'} />
          </Form.Item>
          <Form.Item label="name" name="name" rules={[{ required: true, message: '请输入名称' }]}>
            <Input placeholder="例如 枕套（v1）" />
          </Form.Item>
          <Form.Item label="slots" name="slots">
            <Select mode="tags" placeholder="回车新增，可删除（例如 zipper / edging）" />
          </Form.Item>
          <Form.Item label="状态" name="is_active" valuePropName="checked">
            <Switch checkedChildren="启用" unCheckedChildren="停用" />
          </Form.Item>
        </Form>
      </Drawer>
    </Space>
  )
}


