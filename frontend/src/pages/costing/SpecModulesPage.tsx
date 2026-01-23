import dayjs from 'dayjs'
import { useMemo, useState } from 'react'
import { Button, Card, Col, Input, Modal, Row, Select, Space, Table, Tag, Typography } from 'antd'
import { Link, useNavigate } from 'react-router-dom'
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons'

import { loadTemplateIndex, upsertTemplateMeta, type SpecModuleType, type TmallSkuTemplateMeta } from './tmallSkuGeneratorTemplates'

const { Title, Text } = Typography

const ensureSeed = (): TmallSkuTemplateMeta[] => {
  const cur = loadTemplateIndex()
  if (cur.length) return cur
  const now = new Date().toISOString()
  const seed: TmallSkuTemplateMeta = {
    id: 'mvp',
    name: '天猫布艺 SKU规格生成器（MVP）',
    type: '家居布艺',
    published_at: now,
    matrix_count: null,
  }
  upsertTemplateMeta(seed)
  return [seed]
}

export default function SpecModulesPage() {
  const navigate = useNavigate()
  const [refreshKey, setRefreshKey] = useState(0)
  const [search, setSearch] = useState('')
  const [type, setType] = useState<SpecModuleType | undefined>(undefined)
  const [createOpen, setCreateOpen] = useState(false)
  const [createName, setCreateName] = useState('未命名模板')
  const [createType, setCreateType] = useState<SpecModuleType>('家居布艺')

  const rows = useMemo(() => {
    // refreshKey triggers re-eval (localStorage)
    void refreshKey
    return ensureSeed()
  }, [refreshKey])

  const filtered = useMemo(() => {
    const q = String(search ?? '').trim().toLowerCase()
    return (rows ?? []).filter((r) => {
      if (r?.archived) return false
      if (type && r.type !== type) return false
      if (!q) return true
      const hay = `${r.id} ${r.name} ${r.type}`.toLowerCase()
      return hay.includes(q)
    })
  }, [rows, search, type])

  const onCreate = () => {
    const id = `t_${Date.now().toString(36)}`
    const now = new Date().toISOString()
    const meta: TmallSkuTemplateMeta = {
      id,
      name: String(createName || '').trim() || '未命名模板',
      type: createType,
      published_at: now,
      matrix_count: 0,
    }
    upsertTemplateMeta(meta)
    setCreateOpen(false)
    setRefreshKey((x) => x + 1)
    navigate(`/costing/tmall-sku-generator/${id}`)
  }

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between' }}>
        <div>
          <Title level={3} style={{ marginBottom: 4 }}>
            规格模块
          </Title>
          <Text type="secondary">列表风格与“标准模型”一致；模板名称可在详情页编辑。</Text>
        </div>
      </div>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} lg={12}>
          <Card size="small" title="筛选">
            <Space wrap>
              <Input.Search
                allowClear
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="搜索模板名称 / ID"
                style={{ width: 420 }}
              />
              <Select
                allowClear
                placeholder="类型"
                style={{ width: 200 }}
                value={type}
                onChange={(v) => setType((v as any) ?? undefined)}
                options={[
                  { label: '家居布艺', value: '家居布艺' },
                  { label: '家居饰品', value: '家居饰品' },
                ]}
              />
            </Space>
          </Card>
        </Col>

        <Col xs={24} lg={12}>
          <Card size="small" title="操作">
            <Space wrap>
              <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
                新建模板
              </Button>
              <Button icon={<ReloadOutlined />} onClick={() => setRefreshKey((x) => x + 1)}>
                刷新
              </Button>
            </Space>
          </Card>
        </Col>

        <Col span={24}>
          <Card>
            <Table<TmallSkuTemplateMeta>
              rowKey="id"
              dataSource={filtered}
              pagination={false}
              scroll={{ x: 900 }}
              columns={[
                {
                  title: '模板名称',
                  dataIndex: 'name',
                  render: (v: any, r) => <Link to={`/costing/tmall-sku-generator/${r.id}`}>{String(v ?? '')}</Link>,
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
                  render: (v: any) => {
                    const s = String(v ?? '').trim()
                    if (!s) return <Text type="secondary">-</Text>
                    const d = dayjs(s)
                    return d.isValid() ? d.format('YYYY-MM-DD HH:mm') : s
                  },
                },
                {
                  title: '操作',
                  key: 'actions',
                  width: 140,
                  render: (_: any, r) => (
                    <Space>
                      <Button type="primary" size="small">
                        <Link to={`/costing/tmall-sku-generator/${r.id}`}>进入</Link>
                      </Button>
                    </Space>
                  ),
                },
              ]}
            />
          </Card>
        </Col>
      </Row>

      <Modal
        title="新建模板"
        open={createOpen}
        okText="创建并进入"
        cancelText="取消"
        onOk={onCreate}
        onCancel={() => setCreateOpen(false)}
      >
        <Space direction="vertical" style={{ width: '100%' }}>
          <Input value={createName} onChange={(e) => setCreateName(e.target.value)} placeholder="模板名称（必填）" />
          <Select
            value={createType}
            onChange={(v) => setCreateType(v as SpecModuleType)}
            options={[
              { label: '家居布艺', value: '家居布艺' },
              { label: '家居饰品', value: '家居饰品' },
            ]}
          />
          <Text type="secondary">当前先用浏览器本地存储做模板管理；后续可接入后端发布/版本化。</Text>
        </Space>
      </Modal>
    </div>
  )
}

