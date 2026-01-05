import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Button, Input, Modal, Space, Switch, Table, Tag, Typography, Tooltip } from 'antd'
import type { Material, MaterialQueryParams } from '../../types/planner'
import { fetchMaterials } from '../../services/planner'
import { normalizeUnit as normalizeUnitText } from '@/utils/unit'

const { Text } = Typography

export interface MaterialSelectModalProps {
  open: boolean
  onClose: () => void
  onSelect: (m: Material) => void
  title?: string
  /**
   * Line-variants 的“最稳第一步”建议仅选择 BOM 物料（同单位平替），
   * 这里默认只展示 BOM 物料候选，避免误选“非 BOM 物料”。
   */
  onlyBom?: boolean
  /**
   * 用于“同单位优先/筛选”。传入时会将候选按“同单位”置顶，
   * 并允许用户一键切换“仅同单位”。
   */
  baseUnit?: string | null
}

export default function MaterialSelectModal({
  open,
  onClose,
  onSelect,
  title = '选择物料',
  onlyBom = true,
  baseUnit = null,
}: MaterialSelectModalProps) {
  const [keyword, setKeyword] = useState('')
  const [onlySameUnit, setOnlySameUnit] = useState(false)

  const normalizedBaseUnit = useMemo(() => {
    const s = normalizeUnitText(String(baseUnit ?? ''))
    return s ? s : null
  }, [baseUnit])

  const params: MaterialQueryParams = useMemo(
    () => ({
      search: keyword || undefined,
      status: 'active',
      is_active: true,
      page: 1,
      page_size: 50,
      is_bom_material: onlyBom ? true : undefined,
    }),
    [keyword, onlyBom],
  )

  const q = useQuery({
    queryKey: ['materialsPicker', params],
    queryFn: ({ signal }) => fetchMaterials(params, { signal }),
    enabled: open,
  })

  const sortedItems = useMemo(() => {
    const items = (q.data?.items ?? []) as Material[]
    const baseU = normalizedBaseUnit
    const withIdx = items.map((m, idx) => ({ m, idx }))
    const rankOf = (m: Material): number => {
      if (!baseU) return 1
      const u = normalizeUnitText(String((m as any)?.unit ?? ''))
      return u && u === baseU ? 0 : 1
    }
    withIdx.sort((a, b) => {
      const ra = rankOf(a.m)
      const rb = rankOf(b.m)
      if (ra !== rb) return ra - rb
      return a.idx - b.idx // stable
    })
    const sorted = withIdx.map((x) => x.m)
    if (onlySameUnit && baseU) {
      return sorted.filter((m) => normalizeUnitText(String((m as any)?.unit ?? '')) === baseU)
    }
    return sorted
  }, [q.data?.items, normalizedBaseUnit, onlySameUnit])

  return (
    <Modal title={title} open={open} onCancel={onClose} footer={null} width={920} destroyOnClose>
      <Space wrap style={{ marginBottom: 12 }}>
        {onlyBom ? <Tag color="blue">仅 BOM 物料</Tag> : null}
        {normalizedBaseUnit ? <Tag color="geekblue">基准单位：{normalizedBaseUnit}</Tag> : <Tag>基准单位：未知</Tag>}
        <Input.Search
          allowClear
          placeholder="搜索编码/名称"
          style={{ width: 360 }}
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
        />
        <Tooltip title={normalizedBaseUnit ? '仅展示与基准行同单位的候选' : '基准单位缺失：请先保存清单/补齐主数据单位'}>
          <span>
            <Switch
              checked={onlySameUnit}
              disabled={!normalizedBaseUnit}
              onChange={(v) => setOnlySameUnit(v)}
              checkedChildren="仅同单位"
              unCheckedChildren="同单位置顶"
            />
          </span>
        </Tooltip>
        <Text type="secondary" style={{ fontSize: 12 }}>
          提示：优先选“同单位”的替换物料（启用时会强校验）。
        </Text>
      </Space>

      <Table
        rowKey="id"
        loading={q.isLoading}
        dataSource={sortedItems}
        pagination={false}
        size="small"
        columns={[
          { title: '编码', dataIndex: 'material_code', width: 140 },
          { title: '名称', dataIndex: 'material_name' },
          { title: '分类', dataIndex: 'category', width: 120, render: (v) => v ?? '-' },
          { title: '单位', dataIndex: 'unit', width: 80, render: (v) => v ?? '-' },
          {
            title: '操作',
            width: 96,
            render: (_: any, r: Material) => (
              <Button
                type="primary"
                size="small"
                onClick={() => {
                  onSelect(r)
                  onClose()
                }}
              >
                选择
              </Button>
            ),
          },
        ]}
      />
    </Modal>
  )
}


