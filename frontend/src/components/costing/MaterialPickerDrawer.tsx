import { useEffect, useMemo, useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { Button, Checkbox, Drawer, Input, Select, Space, Switch, Table, Tabs, Tag, Typography, message } from 'antd'
import type { Key } from 'react'

import type {
  Material,
  MaterialQueryParams,
  VirtualMaterial,
  VirtualMaterialQueryParams,
} from '@/types/planner'
import { fetchMaterials, fetchTaxonomyItems, fetchVirtualMaterials } from '@/services/planner'
import { normalizeUnit } from '@/utils/unit'

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
  /** 可选：用于同单位优先/筛选（行级变体“同单位平替”场景） */
  baseUnit?: string | null
  /** 可选：限制选择数量（1 表示单选） */
  maxSelection?: number
  /** 可选：确认按钮文案 */
  confirmText?: string
  /** 可选：默认分页大小（行级变体建议更大些） */
  defaultPageSize?: number
  /** 可选：真实物料查询额外参数（例如 usage_class=conditional） */
  realQueryOverrides?: Partial<MaterialQueryParams>
  /**
   * 可选：真实物料是否排除“间接耗材”（usage_class=indirect）。
   * 默认 true：在“新增物料”场景避免把周期领用耗材混进BOM/模型清单/工艺模块。
   */
  excludeIndirectReal?: boolean
}

export default function MaterialPickerDrawer({
  open,
  onClose,
  onConfirm,
  title = '选择物料',
  initialTab = 'real',
  defaultOnlyBom = true,
  baseUnit = null,
  maxSelection,
  confirmText,
  defaultPageSize = 10,
  realQueryOverrides,
  excludeIndirectReal = true,
}: MaterialPickerDrawerProps) {
  const [activeTab, setActiveTab] = useState<MaterialPickerTab>(initialTab)
  const [onlySameUnit, setOnlySameUnit] = useState(false)

  // real tab filters
  const [realSearch, setRealSearch] = useState('')
  const [realCategory, setRealCategory] = useState<string | undefined>(undefined)
  const [onlyBom, setOnlyBom] = useState(defaultOnlyBom)
  const [realPagination, setRealPagination] = useState({ current: 1, pageSize: defaultPageSize })
  const [realSelectedKeys, setRealSelectedKeys] = useState<Key[]>([])
  const [realSelectedRows, setRealSelectedRows] = useState<Material[]>([])

  // virtual tab filters
  const [virtualSearch, setVirtualSearch] = useState('')
  const [virtualCategory, setVirtualCategory] = useState<string | undefined>(undefined)
  const [virtualPagination, setVirtualPagination] = useState({ current: 1, pageSize: defaultPageSize })
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
      setRealPagination({ current: 1, pageSize: defaultPageSize })
      setRealSelectedKeys([])
      setRealSelectedRows([])

      setVirtualSearch('')
      setVirtualCategory(undefined)
      setVirtualPagination({ current: 1, pageSize: defaultPageSize })
      setVirtualSelectedKeys([])
      setVirtualSelectedRows([])
      setOnlySameUnit(false)
    }
  }, [defaultOnlyBom, defaultPageSize, open])

  const normalizedBaseUnit = useMemo(() => {
    const s = normalizeUnit(String(baseUnit ?? ''))
    return s ? s : null
  }, [baseUnit])

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
      ...(realQueryOverrides || {}),
      page: realPagination.current,
      page_size: realPagination.pageSize,
    }),
    [
      onlyBom,
      realCategory,
      realPagination.current,
      realPagination.pageSize,
      realQueryOverrides,
      realSearch,
    ],
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
      if (maxSelection === 1 && realSelectedRows.length !== 1) {
        message.warning('当前仅允许选择 1 个真实物料')
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
    if (maxSelection === 1 && virtualSelectedRows.length !== 1) {
      message.warning('当前仅允许选择 1 个虚拟物料')
      return
    }
    onConfirm({ kind: 'virtual', materials: virtualSelectedRows })
    onClose()
  }

  const realItems = useMemo(() => {
    const items = (realQuery.data?.items ?? []) as Material[]
    const baseU = normalizedBaseUnit
    let arr = items.slice()
    if (excludeIndirectReal) {
      arr = arr.filter((m) => {
        const meta = ((m as any)?.metadata_json ?? {}) as Record<string, any>
        const usage = String(meta?.usage_class ?? '').trim().toLowerCase()
        return usage !== 'indirect'
      })
    }
    const rankOf = (m: Material): number => {
      if (!baseU) return 1
      const u = normalizeUnit(String((m as any)?.unit ?? ''))
      return u && u === baseU ? 0 : 1
    }
    arr.sort((a, b) => rankOf(a) - rankOf(b))
    if (onlySameUnit && baseU) {
      return arr.filter((m) => normalizeUnit(String((m as any)?.unit ?? '')) === baseU)
    }
    return arr
  }, [excludeIndirectReal, normalizedBaseUnit, onlySameUnit, realQuery.data?.items])

  const virtualItems = useMemo(() => {
    const items = (virtualQuery.data?.items ?? []) as VirtualMaterial[]
    const baseU = normalizedBaseUnit
    const arr = items.slice()
    const rankOf = (m: VirtualMaterial): number => {
      if (!baseU) return 1
      const u = normalizeUnit(String((m as any)?.unit ?? ''))
      return u && u === baseU ? 0 : 1
    }
    arr.sort((a, b) => rankOf(a) - rankOf(b))
    if (onlySameUnit && baseU) {
      return arr.filter((m) => normalizeUnit(String((m as any)?.unit ?? '')) === baseU)
    }
    return arr
  }, [normalizedBaseUnit, onlySameUnit, virtualQuery.data?.items])

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
            {confirmText ?? '添加'}
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
            {normalizedBaseUnit ? <Tag color="geekblue">基准单位：{normalizedBaseUnit}</Tag> : null}
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
            {normalizedBaseUnit ? (
              <Switch
                checked={onlySameUnit}
                onChange={(v) => setOnlySameUnit(v)}
                checkedChildren="仅同单位"
                unCheckedChildren="同单位置顶"
              />
            ) : null}
            <Text type="secondary" style={{ fontSize: 12 }}>
              默认勾选 BOM 物料（更符合“工艺模块清单”的主路径）
            </Text>
          </Space>

          <Table<Material>
            rowKey="id"
            loading={realQuery.isLoading}
            dataSource={realItems}
            rowSelection={{
              selectedRowKeys: realSelectedKeys,
              onChange: (keys, rows) => {
                if (maxSelection === 1) {
                  const lastKey = keys.length ? keys[keys.length - 1] : undefined
                  const lastRow = rows.length ? rows[rows.length - 1] : undefined
                  setRealSelectedKeys(lastKey != null ? [lastKey] : [])
                  setRealSelectedRows(lastRow ? [lastRow] : [])
                  return
                }
                setRealSelectedKeys(keys)
                setRealSelectedRows(rows)
              },
            }}
            pagination={{
              current: realPagination.current,
              pageSize: realPagination.pageSize,
              total: realQuery.data?.total ?? 0,
              showSizeChanger: true,
              onChange: (page, pageSize) => setRealPagination({ current: page, pageSize: pageSize ?? defaultPageSize }),
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
            {normalizedBaseUnit ? <Tag color="geekblue">基准单位：{normalizedBaseUnit}</Tag> : null}
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
            {normalizedBaseUnit ? (
              <Switch
                checked={onlySameUnit}
                onChange={(v) => setOnlySameUnit(v)}
                checkedChildren="仅同单位"
                unCheckedChildren="同单位置顶"
              />
            ) : null}
            <Text type="secondary" style={{ fontSize: 12 }}>
              虚拟物料默认只显示“启用”状态
            </Text>
          </Space>

          <Table<VirtualMaterial>
            rowKey="id"
            loading={virtualQuery.isLoading}
            dataSource={virtualItems}
            rowSelection={{
              selectedRowKeys: virtualSelectedKeys,
              onChange: (keys, rows) => {
                if (maxSelection === 1) {
                  const lastKey = keys.length ? keys[keys.length - 1] : undefined
                  const lastRow = rows.length ? rows[rows.length - 1] : undefined
                  setVirtualSelectedKeys(lastKey != null ? [lastKey] : [])
                  setVirtualSelectedRows(lastRow ? [lastRow] : [])
                  return
                }
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
                setVirtualPagination({ current: page, pageSize: pageSize ?? defaultPageSize }),
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
              { title: '单位', dataIndex: 'unit', width: 100, render: (v?: string) => v || '-' },
            ]}
          />
        </Space>
      )}
    </Drawer>
  )
}


