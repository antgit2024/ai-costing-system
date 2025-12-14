import { Card, Col, Empty, List, Row, Skeleton, Space, Tag, Typography } from 'antd'

const mockStages = ['BOM 解析', '产线工艺', '质检节点']

const ProcessModulesPage = () => {
  return (
    <Space direction="vertical" size={24} style={{ width: '100%' }}>
      <div>
        <Typography.Title level={3} style={{ marginBottom: 0 }}>
          工艺模块
        </Typography.Title>
        <Typography.Text type="secondary">
          这里将承载工序模板、产线配置、工时参数等模块化配置能力。
        </Typography.Text>
      </div>
      <Row gutter={[24, 24]}>
        <Col xs={24} lg={8}>
          <Card title="工艺阶段">
            <List
              dataSource={mockStages}
              renderItem={(item) => (
                <List.Item>
                  <Space>
                    <Tag color="cyan">{item}</Tag>
                    <Typography.Text type="secondary">占位中</Typography.Text>
                  </Space>
                </List.Item>
              )}
            />
          </Card>
        </Col>
        <Col xs={24} lg={16}>
          <Card title="工艺详情">
            <Skeleton active paragraph={{ rows: 5 }} />
            <Empty description="等待后续模块挂载" imageStyle={{ marginTop: 16 }} />
          </Card>
        </Col>
      </Row>
    </Space>
  )
}

export default ProcessModulesPage


