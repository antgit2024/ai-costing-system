import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Button, Drawer, Input, Select, Space, Table, Typography, message } from 'antd'
import type { Key } from 'react'

import type { ProcessQueryParams, ProcessReference } from '@/types/planner'
import { fetchProcessReferences, fetchTaxonomyItems } from '@/services/planner'
import { normalizeUnit } from '@/utils/unit'

const { Text } = Typography

const PRICING_METHOD_OPTIONS = [
  { label: '面积', value: 'area' },
  { label: '周长', value: 'perimeter' },
  { label: '数量', value: 'count' },
  { label: '宽度', value: 'width' },
  { label: '高度', value: 'height' },
  { label: '长边', value: 'long_side' },
  { label: '短边', value: 'short_side' },
]

export interface ProcessSelectModalProps {
  open: boolean
  onClose: () => void
  onConfirm: (process: ProcessReference) => void
  title?: string
}

export default function ProcessSelectModal({
  open,
  onClose,
  onConfirm,
  title = '选择工序（全局工序库）',
}: ProcessSelectModalProps) {
  const [search, setSearch] = useState('')
  const [chargingMode, setChargingMode] = useState<string | undefined>(undefined)
  const [category, setCategory] = useState<string | undefined>(undefined)
  const [selectedRowKeys, setSelectedRowKeys] = useState<Key[]>([])
  const [selectedRows, setSelectedRows] = useState<ProcessReference[]>([])

  const taxonomyCategoriesQuery = useQuery({
    queryKey: ['taxonomy-items', 'process_category', 'process-picker'],
    queryFn: () => fetchTaxonomyItems('process_category', { include_inactive: false }),
    enabled: open,
  })

  useEffect(() => {
    if (!open) {
      setSearch('')
      setChargingMode(undefined)
      setCategory(undefined)
      setSelectedRowKeys([])
      setSelectedRows([])
    }
  }, [open])

  const params: ProcessQueryParams = useMemo(
    () => ({
      search: search.trim() || undefined,
      charging_mode: chargingMode || undefined,
      category: category || undefined,
      status: 'active',
      limit: 200,
    }),
    [category, chargingMode, search],
  )

  const query = useQuery<ProcessReference[]>({
    queryKey: ['process-picker', params],
    queryFn: () => fetchProcessReferences(params),
    enabled: open,
  })

  const handleConfirm = () => {
    if (!selectedRows.length) {
      message.warning('请选择一个工序')
      return
    }
    onConfirm(selectedRows[0])
    onClose()
  }

  return (
    <Drawer
      title={title}
      open={open}
      onClose={onClose}
      width={920}
      destroyOnClose
      extra={
        <Space>
          <Button onClick={onClose}>取消</Button>
          <Button type="primary" onClick={handleConfirm}>
            选择
          </Button>
        </Space>
      }
    >
      <Space direction="vertical" style={{ width: '100%' }}>
        <Space align="start" wrap>
          <Input.Search
            placeholder="搜索编码/名称"
            allowClear
            style={{ width: 260 }}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <Select
            allowClear
            placeholder="分类"
            style={{ width: 220 }}
            value={category}
            onChange={(value) => setCategory(value)}
            options={(taxonomyCategoriesQuery.data?.items ?? []).map((it: any) => ({
              label: it.name,
              value: it.name,
            }))}
          />
          <Select
            allowClear
            placeholder="计价方式"
            style={{ width: 200 }}
            value={chargingMode}
            onChange={(value) => setChargingMode(value)}
            options={PRICING_METHOD_OPTIONS}
          />
        </Space>

        <Table<ProcessReference>
          rowKey="id"
          loading={query.isLoading}
          dataSource={query.data ?? []}
          pagination={{ pageSize: 10 }}
          rowSelection={{
            type: 'radio',
            selectedRowKeys,
            onChange: (keys, rows) => {
              setSelectedRowKeys(keys)
              setSelectedRows(rows)
            },
          }}
          columns={[
            {
              title: '编码',
              dataIndex: 'process_code',
              width: 160,
              render: (code: string) => <Text code>{code}</Text>,
            },
            { title: '名称', dataIndex: 'process_name', width: 260, ellipsis: true },
            { title: '分类', dataIndex: 'category', width: 160, render: (v?: string) => v || '-' },
            { title: '计价方式', dataIndex: 'charging_mode', width: 120, render: (v?: string) => v || '-' },
            {
              title: '标准单价',
              dataIndex: 'standard_rate',
              width: 160,
              render: (value: string | number | null, record) => {
                if (value === null || value === undefined) return '-'
                return `${value} / ${normalizeUnit(record.unit_of_measure) || '-'}`
              },
            },
          ]}
        />
      </Space>
    </Drawer>
  )
}


