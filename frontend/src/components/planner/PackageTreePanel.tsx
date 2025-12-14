import { useMemo, useState } from 'react'
import { Card, Empty, Input, Skeleton, Space, Statistic, Tree } from 'antd'
import type { DataNode, TreeProps } from 'antd/es/tree'
import ApartmentOutlined from '@ant-design/icons/lib/icons/ApartmentOutlined'
import type { PackageNode } from '@/types/planner'

interface PackageTreePanelProps {
  data?: PackageNode[]
  loading: boolean
  onSelectPackage: (packageId?: string) => void
}

const buildTreeData = (nodes: PackageNode[], keyword: string): DataNode[] =>
  nodes
    .map((node) => {
      const children = buildTreeData(node.children ?? [], keyword)
      const matches = keyword ? node.name.toLowerCase().includes(keyword.toLowerCase()) : true
      if (keyword && !matches && children.length === 0) {
        return null
      }
      return {
        key: node.id,
        title: node.name,
        icon: <ApartmentOutlined />,
        children,
      }
    })
    .filter(Boolean) as DataNode[]

const PackageTreePanel = ({ data, loading, onSelectPackage }: PackageTreePanelProps) => {
  const [search, setSearch] = useState('')

  const treeData = useMemo(() => buildTreeData(data ?? [], search.trim()), [data, search])

  const handleSelect: TreeProps['onSelect'] = (_selectedKeys, info) => {
    const key = info.selected ? (info.node.key as string) : undefined
    onSelectPackage(key)
  }

  return (
    <Card
      title="成本包结构"
      className="package-tree-card planner-section"
      extra={<Input.Search placeholder="搜索包名" allowClear size="small" value={search} onChange={(e) => setSearch(e.target.value)} />}
      bodyStyle={{ maxHeight: 360, overflow: 'auto' }}
    >
      {loading ? (
        <Skeleton active paragraph={{ rows: 6 }} />
      ) : !data?.length ? (
        <Empty description="暂无成本包" />
      ) : (
        <Space direction="vertical" style={{ width: '100%' }} size={16}>
          <Statistic title="包数量" value={data.length} />
          <Tree showIcon selectable blockNode treeData={treeData} defaultExpandAll onSelect={handleSelect} />
        </Space>
      )}
    </Card>
  )
}

export default PackageTreePanel

