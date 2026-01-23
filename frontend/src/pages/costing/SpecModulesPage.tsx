import { Button, Card, Space, Table, Tag, Typography } from 'antd'
import { Link } from 'react-router-dom'

const { Text } = Typography

type SpecModuleRow = {
  id: string
  name: string
  type: '家居布艺' | '家居饰品'
  matrix_count: number | null
  published_at: string | null
  to: string
}

const rows: SpecModuleRow[] = [
  {
    id: 'tmall-sku-generator-mvp',
    name: '天猫布艺 SKU规格生成器（MVP）',
    type: '家居布艺',
    matrix_count: null,
    published_at: null,
    to: '/costing/tmall-sku-generator/mvp',
  },
]

export default function SpecModulesPage() {
  return (
    <div style={{ padding: 16 }}>
      <Card
        title="规格模块"
        extra={<Text type="secondary">列表页（后续可接入后端模板发布/版本化）</Text>}
        bodyStyle={{ paddingTop: 8 }}
      >
        <Table<SpecModuleRow>
          rowKey="id"
          size="middle"
          bordered
          pagination={false}
          dataSource={rows}
          columns={[
            {
              title: '模板名称',
              dataIndex: 'name',
              render: (v: any, r) => <Link to={r.to}>{String(v ?? '')}</Link>,
            },
            {
              title: '类型',
              dataIndex: 'type',
              width: 120,
              render: (v: any) => <Tag color={String(v) === '家居饰品' ? 'purple' : 'blue'}>{String(v ?? '')}</Tag>,
            },
            {
              title: '矩阵(数量)',
              dataIndex: 'matrix_count',
              width: 120,
              align: 'right',
              render: (v: any) => (Number.isFinite(Number(v)) ? String(Number(v)) : <Text type="secondary">-</Text>),
            },
            {
              title: '发布时间',
              dataIndex: 'published_at',
              width: 160,
              render: (v: any) => (String(v ?? '').trim() ? String(v) : <Text type="secondary">-</Text>),
            },
            {
              title: '操作',
              key: 'actions',
              width: 140,
              render: (_: any, r) => (
                <Space>
                  <Button type="primary" size="small">
                    <Link to={r.to}>进入</Link>
                  </Button>
                </Space>
              ),
            },
          ]}
        />
      </Card>
    </div>
  )
}

