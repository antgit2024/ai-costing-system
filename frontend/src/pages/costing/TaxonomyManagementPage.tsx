import { useState } from 'react'
import { Button, Card, Form, Input, InputNumber, Modal, Select, Space, Switch, Table, Tabs, Typography, message } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useMutation, useQuery } from '@tanstack/react-query'
import { QuestionCircleOutlined } from '@ant-design/icons'

import {
  archiveTaxonomyItem,
  createTaxonomyItem,
  fetchTaxonomyItems,
  updateTaxonomyItem,
} from '@/services/planner'
import type { TaxonomyItemRead } from '@/types/planner'
import GuideDrawer from '@/components/common/GuideDrawer'
import teamRateGuide from '@doc/costing/manuals/guides/team_rate_guide.md?raw'

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
  const [teamRateGuideOpen, setTeamRateGuideOpen] = useState(false)
  const [form] = Form.useForm<{
    name: string
    is_active: boolean
    sort_order: number
    rate_per_minute?: number
  }>()

  const listQuery = useQuery({
    queryKey: ['taxonomy-items', activeDomain, 'admin'],
    queryFn: () => fetchTaxonomyItems(activeDomain, { include_inactive: true }),
  })

  const DEFAULT_SCOPES = ['*']

  const openCreate = () => {
    setEditing(null)
    form.resetFields()
    form.setFieldsValue({
      name: '',
      is_active: true,
      sort_order: 0,
      rate_per_minute: undefined,
    })
    setModalOpen(true)
  }

  const openEdit = (item: TaxonomyItemRead) => {
    setEditing(item)
    form.resetFields()
    form.setFieldsValue({
      name: item.name,
      is_active: item.is_active,
      sort_order: item.sort_order ?? 0,
      rate_per_minute: Number((item as any)?.metadata?.rate_per_minute ?? (item as any)?.metadata_json?.rate_per_minute),
    })
    setModalOpen(true)
  }

  const createMutation = useMutation({
    mutationFn: (payload: { domain: string; name: string; is_active: boolean; sort_order: number }) =>
      createTaxonomyItem({
        domain: payload.domain,
        name: payload.name,
        scopes: DEFAULT_SCOPES,
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
    mutationFn: (payload: { id: string; name: string; is_active: boolean; sort_order: number; metadata?: any }) =>
      updateTaxonomyItem(payload.id, {
        name: payload.name,
        is_active: payload.is_active,
        sort_order: payload.sort_order,
        ...(payload.metadata ? { metadata: payload.metadata } : {}),
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
    ...(activeDomain === 'team'
      ? ([
          {
            title: '默认单价(元/分)',
            width: 140,
            render: (_: any, r: TaxonomyItemRead) => {
              const meta: any = (r as any)?.metadata ?? (r as any)?.metadata_json ?? {}
              const v = Number(meta?.rate_per_minute)
              return Number.isFinite(v) ? v.toFixed(2) : '-'
            },
          },
        ] as ColumnsType<TaxonomyItemRead>)
      : []),
    {
      title: '启用',
      width: 90,
      render: (_: any, r: TaxonomyItemRead) => (
        <Switch
          checked={r.is_active}
          onChange={(checked) => updateMutation.mutate({ id: r.id, name: r.name, is_active: checked, sort_order: r.sort_order })}
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
      </Card>

      <Modal
        title={editing ? '编辑分类' : '新增分类'}
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        okText="保存"
        onOk={async () => {
          const values = await form.validateFields()
          const metadata =
            activeDomain === 'team'
              ? {
                  rate_per_minute:
                    values.rate_per_minute === undefined || values.rate_per_minute === null
                      ? undefined
                      : Number(values.rate_per_minute),
                }
              : undefined
          if (editing) {
            updateMutation.mutate({
              id: editing.id,
              name: values.name,
              is_active: values.is_active,
              sort_order: values.sort_order,
              ...(metadata ? { metadata } : {}),
            })
            return
          }
          createMutation.mutate({
            domain: activeDomain,
            name: values.name,
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
          {activeDomain === 'team' ? (
            <Form.Item
              label="默认单价（元/分）"
              name="rate_per_minute"
              tooltip="选择该班组后，工艺模块会自动带出此分钟单价（仅在该步骤未手填单价时生效）。"
            >
              <Space>
                <InputNumber min={0} precision={2} style={{ width: 220 }} placeholder="例如：0.80" />
                <Button icon={<QuestionCircleOutlined />} onClick={() => setTeamRateGuideOpen(true)}>
                  工价指南
                </Button>
              </Space>
            </Form.Item>
          ) : null}
        </Form>
      </Modal>

      <GuideDrawer
        open={teamRateGuideOpen}
        onClose={() => setTeamRateGuideOpen(false)}
        title="工价指南（班组默认单价：元/分）"
        content={teamRateGuide}
        tip="提示：这是“班组管理”的工价口径说明。建议在录入默认单价前先按本指南统一口径。"
      />
    </Space>
  )
}

export default TaxonomyManagementPage


