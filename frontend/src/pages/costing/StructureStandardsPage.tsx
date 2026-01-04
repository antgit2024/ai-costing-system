import { Alert, Button, Card, Drawer, Form, Input, Modal, Select, Space, Switch, Table, Tag, Tooltip, Typography, message } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useMemo, useState } from 'react'
import { keepPreviousData, useQuery, useQueryClient } from '@tanstack/react-query'

import {
  activateStructureStandard,
  createStructureStandard,
  deactivateStructureStandard,
  deleteStructureStandard,
  fetchStructureStandards,
  updateStructureStandard,
} from '@/services/planner'
import type { StructureStandardRead, StructureStandardStatus } from '@/types/planner'
import { toPinyinCode } from '@/utils/pinyin'

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

type SlotRow = { cn?: string; code?: string; enabled?: boolean }

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
      slot_rows: [],
      is_active: true,
    })
    setDrawerOpen(true)
  }

  const openEdit = (record: StructureStandardRead) => {
    setDrawerMode('edit')
    setActiveRecord(record)
    const rows: SlotRow[] = (record.slot_defs?.length
      ? record.slot_defs
      : (record.slots ?? []).map((code) => ({ code, enabled: true, name_cn: record.slot_display_names?.[code] ?? '' })) // compat
    )
      .map((r: any) => ({
        code: String(r?.code ?? '').trim(),
        cn: String(r?.name_cn ?? r?.cn ?? '').trim(),
        enabled: r?.enabled === false ? false : true,
      }))
      .filter((r) => r.code)
    editorForm.setFieldsValue({
      code: record.code,
      name: record.name,
      slot_rows: rows,
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
          const defs = Array.isArray(r.slot_defs) ? r.slot_defs : []
          const enabled = defs.length ? defs.filter((d) => d.enabled !== false).map((d) => d.code) : Array.isArray(r.slots) ? r.slots : []
          const disabled = defs.length ? defs.filter((d) => d.enabled === false).map((d) => d.code) : []
          const slots = enabled
          if (!slots.length && !disabled.length) return <Text type="secondary">-</Text>
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
                  {r.slot_display_names?.[s] ? (
                    <Tooltip title={s}>
                      <span>{r.slot_display_names?.[s]}</span>
                    </Tooltip>
                  ) : (
                    s
                  )}
                </Tag>
              ))}
              {disabled.length ? (
                <Tooltip title={`不启用（不参与工艺模块下拉）：${disabled.join('、')}`}>
                  <Tag color="default" style={{ marginInlineEnd: 0, borderRadius: 999, padding: '0 6px', fontSize: 12, lineHeight: '18px' }}>
                    可选位 {disabled.length}
                  </Tag>
                </Tooltip>
              ) : null}
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

              <Tooltip title={isActive ? '请先停用，再删除（归档）' : '删除（归档）后不可恢复'}>
                <Button
                  size="small"
                  danger
                  disabled={isActive}
                  onClick={() => {
                    Modal.confirm({
                      title: '删除结构标准（归档）',
                      content: (
                        <div>
                          <div>
                            确认删除（归档）：<Text code>{record.code}</Text> {record.name}？
                          </div>
                          <div style={{ marginTop: 8 }}>
                            <Text type="secondary">建议：如已被模型版本/工艺模块引用，请先确认不会影响后续筛选与推荐。</Text>
                          </div>
                        </div>
                      ),
                      okText: '删除',
                      okButtonProps: { danger: true },
                      cancelText: '取消',
                      onOk: async () => {
                        try {
                          await deleteStructureStandard(record.id)
                          message.success('已删除（归档）')
                          queryClient.invalidateQueries({ queryKey: ['structure-standards'] })
                        } catch (err: any) {
                          message.error(err?.response?.data?.detail ?? err?.message ?? '删除失败（可能需要管理员密钥）')
                        }
                      },
                    })
                  }}
                >
                  删除
                </Button>
              </Tooltip>
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
    const rows: SlotRow[] = Array.isArray(values.slot_rows) ? values.slot_rows : []
    const slot_display_names: Record<string, string> = {}
    const slotCodesAll: string[] = []
    const slotCodesActive: string[] = []
    const slot_defs: Array<{ code: string; name_cn?: string; enabled?: boolean }> = []
    for (const row of rows) {
      const cn = String(row?.cn ?? '').trim()
      const rawCode = String(row?.code ?? '').trim()
      const c = rawCode ? toPinyinCode(rawCode) : toPinyinCode(cn)
      if (!c) continue
      const enabled = row?.enabled === false ? false : true
      if (!slotCodesAll.includes(c)) slotCodesAll.push(c)
      if (enabled && !slotCodesActive.includes(c)) slotCodesActive.push(c)
      if (cn) slot_display_names[c] = cn
      slot_defs.push({ code: c, name_cn: cn || undefined, enabled })
    }
    const slots = normalizeSlots(slotCodesActive)
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
        await createStructureStandard({ code, name, slots, slot_display_names, slot_defs, status })
        message.success('结构标准已创建')
      } else if (activeRecord) {
        // MVP: 编辑时锁定 code（避免变更唯一键造成引用漂移）
        await updateStructureStandard(activeRecord.id, { name, slots, slot_display_names, slot_defs, status })
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
          <Form.Item
            label="slots（中文名 + 自动拼音短码）"
            extra={
              <Space direction="vertical" size={4}>
                <Text type="secondary">左侧填中文名；右侧会自动生成拼音短码（可手改）。保存时以“拼音短码”为系统键。</Text>
                <Text type="secondary">
                  规则：这里建立的 slots 表达的是<strong>结构位置/部位</strong>（结构），用于标记“某个位置上适用哪些工艺模块”；
                  <strong>工艺</strong>指生产时的工序/方法，通常做成工艺模块并按 <Text code>global</Text> /{' '}
                  <Text code>slot_internal</Text> / <Text code>assembly</Text> 来表示适用范围。通用工艺（如印染/打印/包装）可用{' '}
                  <Text code>GLOBAL</Text> 模块表达，<strong>不一定需要</strong>在结构里额外建“通用位”。
                </Text>
                <Text type="secondary">
                  勾选“启用”的 slot 会出现在工艺模块的 slot(s) 下拉里；取消勾选表示“骨架可选位”，仅用于展示/规划，不参与下拉选择。
                </Text>
              </Space>
            }
          >
            <Form.List name="slot_rows">
              {(fields, { add, remove }) => (
                <Space direction="vertical" style={{ width: '100%' }} size={8}>
                  {fields.map((field) => (
                    <Space key={field.key} style={{ display: 'flex' }} align="baseline">
                      <Form.Item
                        {...field}
                        name={[field.name, 'cn']}
                        style={{ marginBottom: 0, width: 260 }}
                        rules={[{ required: true, message: '请输入中文名' }]}
                      >
                        <Input
                          placeholder="中文名，例如：拉链位"
                          onChange={(e) => {
                            const cn = String(e.target.value ?? '')
                            const currentRows: SlotRow[] = editorForm.getFieldValue('slot_rows') ?? []
                            const idx = Number(field.name)
                            const curCode = String(currentRows?.[idx]?.code ?? '').trim()
                            // only auto-fill when code is empty
                            if (!curCode) {
                              const next = toPinyinCode(cn)
                              editorForm.setFieldValue(['slot_rows', idx, 'code'], next)
                            }
                          }}
                        />
                      </Form.Item>
                      <Form.Item {...field} name={[field.name, 'code']} style={{ marginBottom: 0, width: 260 }}>
                        <Input placeholder="拼音短码（自动生成，可手改），例如：lalianwei / lalian" />
                      </Form.Item>
                      <Form.Item {...field} name={[field.name, 'enabled']} valuePropName="checked" style={{ marginBottom: 0 }}>
                        <Switch checkedChildren="启用" unCheckedChildren="不启用" defaultChecked />
                      </Form.Item>
                      <Button danger onClick={() => remove(field.name)}>
                        删除
                      </Button>
                    </Space>
                  ))}
                  <Button
                    type="dashed"
                    onClick={() => add({ cn: '', code: '', enabled: true })}
                    style={{ width: 540 }}
                  >
                    新增 slot
                  </Button>
                </Space>
              )}
            </Form.List>
          </Form.Item>
          <Form.Item label="状态" name="is_active" valuePropName="checked">
            <Switch checkedChildren="启用" unCheckedChildren="停用" />
          </Form.Item>
        </Form>
      </Drawer>
    </Space>
  )
}


