import { useMemo, useState } from 'react'
import { Button, Card, Form, Input, Modal, Select, Space, Switch, Table, Tabs, Tag, Typography, message } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useMutation, useQuery } from '@tanstack/react-query'

import {
  archiveTaxonomyItem,
  createTaxonomyItem,
  fetchTaxonomyItems,
  fetchTaxonomyScopeOptions,
  updateTaxonomyItem,
} from '@/services/planner'
import type { TaxonomyItemRead } from '@/types/planner'

const { Text } = Typography

type DomainKey =
  | 'material_category'
  | 'virtual_material_category'
  | 'process_category'
  | 'process_module_category'
  | 'team'
  | 'product_model_category'

const DOMAIN_LABELS: Record<DomainKey, string> = {
  material_category: '真实物料分类',
  virtual_material_category: '虚拟物料分类',
  process_category: '工序分类',
  process_module_category: '工艺模块分类',
  team: '班组管理',
  product_model_category: '模型品类',
}

const TaxonomyManagementPage = () => {
  const [activeDomain, setActiveDomain] = useState<DomainKey>('material_category')
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<TaxonomyItemRead | null>(null)
  const [form] = Form.useForm<{
    name: string
    scopes: string[]
    is_active: boolean
    sort_order: number
  }>()

  const scopeOptionsQuery = useQuery({
    queryKey: ['taxonomy-scope-options'],
    queryFn: () => fetchTaxonomyScopeOptions(),
  })

  const listQuery = useQuery({
    queryKey: ['taxonomy-items', activeDomain, 'admin'],
    queryFn: () => fetchTaxonomyItems(activeDomain, { include_inactive: true }),
  })

  const scopeSelectOptions = useMemo(() => {
    const defaultScopes = scopeOptionsQuery.data?.default_scopes ?? ['布艺', '画艺']
    const universal = scopeOptionsQuery.data?.universal_scope ?? '*'
    return [
      { label: `通用（${universal}）`, value: universal },
      ...defaultScopes.map((s) => ({ label: s, value: s })),
    ]
  }, [scopeOptionsQuery.data?.default_scopes, scopeOptionsQuery.data?.universal_scope])

  const normalizeScopes = (raw: string[]) => {
    const universal = scopeOptionsQuery.data?.universal_scope ?? '*'
    const cleaned = Array.from(
      new Set((raw ?? []).map((s) => String(s ?? '').trim()).filter(Boolean)),
    )
    if (cleaned.includes(universal)) {
      return [universal]
    }
    return cleaned
  }

  const openCreate = () => {
    setEditing(null)
    form.resetFields()
    form.setFieldsValue({ name: '', scopes: [scopeOptionsQuery.data?.universal_scope ?? '*'], is_active: true, sort_order: 0 })
    setModalOpen(true)
  }

  const openEdit = (item: TaxonomyItemRead) => {
    setEditing(item)
    form.resetFields()
    form.setFieldsValue({
      name: item.name,
      scopes: item.scopes,
      is_active: item.is_active,
      sort_order: item.sort_order ?? 0,
    })
    setModalOpen(true)
  }

  const createMutation = useMutation({
    mutationFn: (payload: { domain: string; name: string; scopes: string[]; is_active: boolean; sort_order: number }) =>
      createTaxonomyItem({
        domain: payload.domain,
        name: payload.name,
        scopes: payload.scopes,
        is_active: payload.is_active,
        sort_order: payload.sort_order,
        source: 'local',
      }),
    onSuccess: async () => {
      message.success('已创建')
      setModalOpen(false)
      await listQuery.refetch()
    },
    onError: (err: any) => {
      message.error(err?.response?.data?.detail ?? err?.message ?? '创建失败')
    },
  })

  const updateMutation = useMutation({
    mutationFn: (payload: { id: string; name: string; scopes: string[]; is_active: boolean; sort_order: number }) =>
      updateTaxonomyItem(payload.id, {
        name: payload.name,
        scopes: payload.scopes,
        is_active: payload.is_active,
        sort_order: payload.sort_order,
      }),
    onSuccess: async () => {
      message.success('已保存')
      setModalOpen(false)
      await listQuery.refetch()
    },
    onError: (err: any) => {
      message.error(err?.response?.data?.detail ?? err?.message ?? '保存失败')
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => archiveTaxonomyItem(id),
    onSuccess: async () => {
      message.success('已删除（归档）')
      await listQuery.refetch()
    },
    onError: (err: any) => {
      message.error(err?.response?.data?.detail ?? err?.message ?? '删除失败')
    },
  })

  const items = listQuery.data?.items ?? []

  const columns: ColumnsType<TaxonomyItemRead> = [
    { title: '名称', dataIndex: 'name', ellipsis: true },
    {
      title: '适用范围',
      width: 220,
      render: (_: any, r: TaxonomyItemRead) => (
        <Space wrap size={[4, 4]}>
          {(r.scopes ?? []).map((s) => (
            <Tag key={s} color={s === '*' ? 'blue' : undefined}>
              {s === '*' ? '通用' : s}
            </Tag>
          ))}
        </Space>
      ),
    },
    {
      title: '启用',
      width: 90,
      render: (_: any, r: TaxonomyItemRead) => (
        <Switch
          checked={r.is_active}
          onChange={(checked) => updateMutation.mutate({ id: r.id, name: r.name, scopes: r.scopes, is_active: checked, sort_order: r.sort_order })}
        />
      ),
    },
    { title: '排序', dataIndex: 'sort_order', width: 80 },
    { title: '来源', dataIndex: 'source', width: 90, render: (v: any) => <Text type="secondary">{String(v ?? '-')}</Text> },
    { title: '更新时间', dataIndex: 'updated_at', width: 160, render: (v: any) => <Text type="secondary">{String(v ?? '-')}</Text> },
    {
      title: '操作',
      width: 180,
      render: (_: any, r: TaxonomyItemRead) => (
        <Space>
          <Button size="small" onClick={() => openEdit(r)}>
            编辑
          </Button>
          <Button
            size="small"
            danger
            onClick={() => {
              Modal.confirm({
                title: '删除分类',
                content: `确认删除（归档）：${r.name}？`,
                okText: '删除',
                okButtonProps: { danger: true },
                cancelText: '取消',
                onOk: async () => deleteMutation.mutate(r.id),
              })
            }}
          >
            删除
          </Button>
        </Space>
      ),
    },
  ]

  return (
    <Space direction="vertical" style={{ width: '100%' }} size={12}>
      <Card
        title="分类管理（管理员）"
        extra={
          <Space>
            <Button onClick={() => listQuery.refetch()}>刷新</Button>
            <Button type="primary" onClick={openCreate}>
              新增分类
            </Button>
          </Space>
        }
      >
        <Tabs
          activeKey={activeDomain}
          onChange={(k) => setActiveDomain(k as DomainKey)}
          items={(Object.keys(DOMAIN_LABELS) as DomainKey[]).map((k) => ({
            key: k,
            label: DOMAIN_LABELS[k],
            children: (
              <Table
                rowKey="id"
                size="small"
                loading={listQuery.isLoading}
                dataSource={items}
                columns={columns}
                pagination={false}
              />
            ),
          }))}
        />
        <div style={{ marginTop: 8 }}>
          <Text type="secondary">
            说明：适用范围必选。推荐用“通用(*)”覆盖全部品类；布艺/画艺只是默认快捷标签（可继续扩展新标签，不需要改库）。
          </Text>
        </div>
      </Card>

      <Modal
        title={editing ? '编辑分类' : '新增分类'}
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        okText="保存"
        onOk={async () => {
          const values = await form.validateFields()
          const scopes = normalizeScopes(values.scopes)
          if (!scopes.length) {
            message.error('适用范围为必选')
            return
          }
          if (editing) {
            updateMutation.mutate({
              id: editing.id,
              name: values.name,
              scopes,
              is_active: values.is_active,
              sort_order: values.sort_order,
            })
            return
          }
          createMutation.mutate({
            domain: activeDomain,
            name: values.name,
            scopes,
            is_active: values.is_active,
            sort_order: values.sort_order,
          })
        }}
        confirmLoading={createMutation.isPending || updateMutation.isPending}
        destroyOnClose
      >
        <Form form={form} layout="vertical" preserve={false}>
          <Form.Item label="名称" name="name" rules={[{ required: true, message: '请输入名称' }]}>
            <Input placeholder="例如：包装材料 / 画框线条 / 装裱..." />
          </Form.Item>
          <Form.Item
            label="适用范围（必选）"
            name="scopes"
            rules={[
              { required: true, message: '请选择适用范围' },
              {
                validator: async (_, v) => {
                  const arr = Array.isArray(v) ? v : []
                  if (normalizeScopes(arr).length < 1) {
                    throw new Error('适用范围为必选')
                  }
                },
              },
            ]}
          >
            <Select
              mode="tags"
              style={{ width: '100%' }}
              placeholder="必选：通用(*) 或 布艺/画艺..."
              options={scopeSelectOptions}
              onChange={(v) => form.setFieldValue('scopes', normalizeScopes(v as any))}
            />
          </Form.Item>
          <Space>
            <Form.Item label="启用" name="is_active" valuePropName="checked" initialValue>
              <Switch />
            </Form.Item>
            <Form.Item label="排序" name="sort_order" initialValue={0}>
              <Select
                style={{ width: 120 }}
                options={[0, 10, 20, 50, 100].map((n) => ({ label: n, value: n }))}
              />
            </Form.Item>
          </Space>
          <div style={{ marginTop: 8 }}>
            <Text type="secondary">
              快捷标签：布艺 / 画艺（可点击选择）。若选“通用(*)”，将自动覆盖所有品类并清空其它标签。
            </Text>
          </div>
        </Form>
      </Modal>
    </Space>
  )
}

export default TaxonomyManagementPage


