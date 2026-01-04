import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Button, Input, Modal, Space, Table, Tag, Typography } from 'antd'
import type { Material, MaterialQueryParams } from '../../types/planner'
import { fetchMaterials } from '../../services/planner'

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
}

export default function MaterialSelectModal({
  open,
  onClose,
  onSelect,
  title = '选择物料',
  onlyBom = true,
}: MaterialSelectModalProps) {
  const [keyword, setKeyword] = useState('')

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

  return (
    <Modal title={title} open={open} onCancel={onClose} footer={null} width={920} destroyOnClose>
      <Space wrap style={{ marginBottom: 12 }}>
        {onlyBom ? <Tag color="blue">仅 BOM 物料</Tag> : null}
        <Input.Search
          allowClear
          placeholder="搜索编码/名称"
          style={{ width: 360 }}
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
        />
        <Text type="secondary" style={{ fontSize: 12 }}>
          提示：优先选“同单位”的替换物料（启用时会强校验）。
        </Text>
      </Space>

      <Table
        rowKey="id"
        loading={q.isLoading}
        dataSource={q.data?.items ?? []}
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


