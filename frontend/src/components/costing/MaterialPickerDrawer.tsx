import { useEffect, useMemo, useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { Button, Checkbox, Drawer, Input, Select, Space, Table, Tabs, Typography, message } from 'antd'
import type { Key } from 'react'

import type {
  Material,
  MaterialQueryParams,
  VirtualMaterial,
  VirtualMaterialQueryParams,
} from '@/types/planner'
import { fetchMaterials, fetchTaxonomyItems, fetchVirtualMaterials } from '@/services/planner'

const { Text } = Typography

export type MaterialPickerTab = 'real' | 'virtual'

export type MaterialPickerResult =
  | { kind: 'real' | 'bom'; materials: Material[] }
  | { kind: 'virtual'; materials: VirtualMaterial[] }

export interface MaterialPickerDrawerProps {
  open: boolean
  onClose: () => void
  onConfirm: (result: MaterialPickerResult) => void
  title?: string
  initialTab?: MaterialPickerTab
  /** 真实物料默认仅显示 BOM 物料（你要求默认勾选） */
  defaultOnlyBom?: boolean
}

export default function MaterialPickerDrawer({
  open,
  onClose,
  onConfirm,
  title = '选择物料',
  initialTab = 'real',
  defaultOnlyBom = true,
}: MaterialPickerDrawerProps) {
  const [activeTab, setActiveTab] = useState<MaterialPickerTab>(initialTab)

  // real tab filters
  const [realSearch, setRealSearch] = useState('')
  const [realCategory, setRealCategory] = useState<string | undefined>(undefined)
  const [onlyBom, setOnlyBom] = useState(defaultOnlyBom)
  const [realPagination, setRealPagination] = useState({ current: 1, pageSize: 10 })
  const [realSelectedKeys, setRealSelectedKeys] = useState<Key[]>([])
  const [realSelectedRows, setRealSelectedRows] = useState<Material[]>([])

  // virtual tab filters
  const [virtualSearch, setVirtualSearch] = useState('')
  const [virtualCategory, setVirtualCategory] = useState<string | undefined>(undefined)
  const [virtualPagination, setVirtualPagination] = useState({ current: 1, pageSize: 10 })
  const [virtualSelectedKeys, setVirtualSelectedKeys] = useState<Key[]>([])
  const [virtualSelectedRows, setVirtualSelectedRows] = useState<VirtualMaterial[]>([])

  useEffect(() => {
    if (!open) return
    setActiveTab(initialTab)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  useEffect(() => {
    if (!open) {
      setRealSearch('')
      setRealCategory(undefined)
      setOnlyBom(defaultOnlyBom)
      setRealPagination({ current: 1, pageSize: 10 })
      setRealSelectedKeys([])
      setRealSelectedRows([])

      setVirtualSearch('')
      setVirtualCategory(undefined)
      setVirtualPagination({ current: 1, pageSize: 10 })
      setVirtualSelectedKeys([])
      setVirtualSelectedRows([])
    }
  }, [defaultOnlyBom, open])

  const realCategoryQuery = useQuery({
    queryKey: ['taxonomy-items', 'material_category', 'material-picker'],
    queryFn: () => fetchTaxonomyItems('material_category', { include_inactive: false }),
    enabled: open,
  })

  const virtualCategoryQuery = useQuery({
    queryKey: ['taxonomy-items', 'virtual_material_category', 'material-picker'],
    queryFn: () => fetchTaxonomyItems('virtual_material_category', { include_inactive: false }),
    enabled: open,
  })

  const realParams: MaterialQueryParams = useMemo(
    () => ({
      search: realSearch.trim() || undefined,
      category: realCategory?.trim() || undefined,
      status: 'active',
      is_active: true,
      is_bom_material: onlyBom ? true : undefined,
      page: realPagination.current,
      page_size: realPagination.pageSize,
    }),
    [onlyBom, realCategory, realPagination.current, realPagination.pageSize, realSearch],
  )

  const realQuery = useQuery({
    queryKey: ['material-picker', 'real', realParams],
    queryFn: ({ signal }) => fetchMaterials(realParams, { signal }),
    enabled: open && activeTab === 'real',
    placeholderData: keepPreviousData,
  })

  const virtualParams: VirtualMaterialQueryParams = useMemo(
    () => ({
      search: virtualSearch.trim() || undefined,
      category: virtualCategory || undefined,
      status: 'active',
      page: virtualPagination.current,
      page_size: virtualPagination.pageSize,
    }),
    [virtualCategory, virtualPagination.current, virtualPagination.pageSize, virtualSearch],
  )

  const virtualQuery = useQuery({
    queryKey: ['material-picker', 'virtual', virtualParams],
    queryFn: () => fetchVirtualMaterials(virtualParams),
    enabled: open && activeTab === 'virtual',
    placeholderData: keepPreviousData,
  })

  const handleConfirm = () => {
    if (activeTab === 'real') {
      if (!realSelectedRows.length) {
        message.warning('请选择至少一个真实物料')
        return
      }
      onConfirm({ kind: onlyBom ? 'bom' : 'real', materials: realSelectedRows })
      onClose()
      return
    }
    if (!virtualSelectedRows.length) {
      message.warning('请选择至少一个虚拟物料')
      return
    }
    onConfirm({ kind: 'virtual', materials: virtualSelectedRows })
    onClose()
  }

  return (
    <Drawer
      title={title}
      open={open}
      onClose={onClose}
      width={980}
      destroyOnClose
      extra={
        <Space>
          <Button onClick={onClose}>取消</Button>
          <Button type="primary" onClick={handleConfirm}>
            添加
          </Button>
        </Space>
      }
    >
      <Tabs
        activeKey={activeTab}
        onChange={(key) => setActiveTab(key as MaterialPickerTab)}
        items={[
          { key: 'real', label: '真实物料' },
          { key: 'virtual', label: '虚拟物料' },
        ]}
      />

      {activeTab === 'real' ? (
        <Space direction="vertical" style={{ width: '100%' }} size={12}>
          <Space wrap align="start">
            <Input.Search
              placeholder="搜索编码/名称"
              allowClear
              style={{ width: 260 }}
              value={realSearch}
              onChange={(e) => {
                setRealSearch(e.target.value)
                setRealPagination((p) => ({ ...p, current: 1 }))
              }}
              onSearch={() => setRealPagination((p) => ({ ...p, current: 1 }))}
            />
            <Select
              allowClear
              showSearch
              optionFilterProp="label"
              placeholder="分类"
              style={{ width: 220 }}
              value={realCategory}
              onChange={(v) => {
                setRealCategory(v)
                setRealPagination((p) => ({ ...p, current: 1 }))
              }}
              filterOption={(input, opt) => {
                const label = String((opt as any)?.label ?? '')
                return label.toLowerCase().includes(String(input ?? '').toLowerCase())
              }}
              options={(realCategoryQuery.data?.items ?? []).map((it: any) => ({
                label: it.name,
                value: it.name,
              }))}
            />
            <Checkbox
              checked={onlyBom}
              onChange={(e) => {
                setOnlyBom(e.target.checked)
                setRealPagination((p) => ({ ...p, current: 1 }))
              }}
            >
              仅 BOM 物料
            </Checkbox>
            <Text type="secondary" style={{ fontSize: 12 }}>
              默认勾选 BOM 物料（更符合“工艺模块清单”的主路径）
            </Text>
          </Space>

          <Table<Material>
            rowKey="id"
            loading={realQuery.isLoading}
            dataSource={realQuery.data?.items ?? []}
            rowSelection={{
              selectedRowKeys: realSelectedKeys,
              onChange: (keys, rows) => {
                setRealSelectedKeys(keys)
                setRealSelectedRows(rows)
              },
            }}
            pagination={{
              current: realPagination.current,
              pageSize: realPagination.pageSize,
              total: realQuery.data?.total ?? 0,
              showSizeChanger: true,
              onChange: (page, pageSize) => setRealPagination({ current: page, pageSize: pageSize ?? 10 }),
            }}
            columns={[
              { title: '编码', dataIndex: 'material_code', width: 160, render: (v: string) => <Text code>{v}</Text> },
              { title: '名称', dataIndex: 'material_name' },
              { title: '分类', dataIndex: 'category', width: 160, render: (v?: string) => v || '-' },
              { title: '单位', dataIndex: 'unit', width: 100, render: (v?: string) => v || '-' },
            ]}
          />
        </Space>
      ) : (
        <Space direction="vertical" style={{ width: '100%' }} size={12}>
          <Space wrap align="start">
            <Input.Search
              placeholder="搜索编码/名称"
              allowClear
              style={{ width: 260 }}
              value={virtualSearch}
              onChange={(e) => {
                setVirtualSearch(e.target.value)
                setVirtualPagination((p) => ({ ...p, current: 1 }))
              }}
              onSearch={() => setVirtualPagination((p) => ({ ...p, current: 1 }))}
            />
            <Select
              allowClear
              showSearch
              optionFilterProp="label"
              placeholder="分类"
              style={{ width: 220 }}
              value={virtualCategory}
              onChange={(v) => {
                setVirtualCategory(v)
                setVirtualPagination((p) => ({ ...p, current: 1 }))
              }}
              filterOption={(input, opt) => {
                const label = String((opt as any)?.label ?? '')
                return label.toLowerCase().includes(String(input ?? '').toLowerCase())
              }}
              options={(virtualCategoryQuery.data?.items ?? []).map((it: any) => ({
                label: it.name,
                value: it.name,
              }))}
            />
            <Text type="secondary" style={{ fontSize: 12 }}>
              虚拟物料默认只显示“启用”状态
            </Text>
          </Space>

          <Table<VirtualMaterial>
            rowKey="id"
            loading={virtualQuery.isLoading}
            dataSource={virtualQuery.data?.items ?? []}
            rowSelection={{
              selectedRowKeys: virtualSelectedKeys,
              onChange: (keys, rows) => {
                setVirtualSelectedKeys(keys)
                setVirtualSelectedRows(rows)
              },
            }}
            pagination={{
              current: virtualPagination.current,
              pageSize: virtualPagination.pageSize,
              total: virtualQuery.data?.total ?? 0,
              showSizeChanger: true,
              onChange: (page, pageSize) =>
                setVirtualPagination({ current: page, pageSize: pageSize ?? 10 }),
            }}
            columns={[
              {
                title: '编码',
                dataIndex: 'virtual_code',
                width: 160,
                render: (v: string) => <Text code>{v}</Text>,
              },
              { title: '名称', dataIndex: 'name' },
              { title: '分类', dataIndex: 'category', width: 160, render: (v?: string) => v || '-' },
              { title: '类型', dataIndex: 'virtual_kind', width: 120, render: (v?: string) => v || '-' },
            ]}
          />
        </Space>
      )}
    </Drawer>
  )
}


