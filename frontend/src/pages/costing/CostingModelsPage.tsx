import { Card, Col, Empty, Row, Skeleton, Space, Tag, Typography } from 'antd'

const CostingModelsPage = () => {
  return (
    <Space direction="vertical" size={24} style={{ width: '100%' }}>
      <div>
        <Typography.Title level={3} style={{ marginBottom: 0 }}>
          成本模型配置
        </Typography.Title>
        <Typography.Text type="secondary">
          该页面将挂载物料、人工、制造费用等模型配置能力，目前为占位骨架。
        </Typography.Text>
      </div>
      <Row gutter={[24, 24]}>
        <Col xs={24} lg={10}>
          <Card title="模型概览" bordered={false}>
            <Skeleton active paragraph={{ rows: 3 }} />
          </Card>
          <Card title="最近变更" style={{ marginTop: 16 }}>
            <Empty description="尚无模型发布记录" image={Empty.PRESENTED_IMAGE_SIMPLE} />
          </Card>
        </Col>
        <Col xs={24} lg={14}>
          <Card
            title={
              <Space size={12}>
                <span>模型结构预览</span>
                <Tag color="blue">即将开放</Tag>
              </Space>
            }
          >
            <Skeleton active paragraph={{ rows: 6 }} />
          </Card>
        </Col>
      </Row>
    </Space>
  )
}

export default CostingModelsPage


