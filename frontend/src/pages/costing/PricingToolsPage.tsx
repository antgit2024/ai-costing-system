import { Button, Card, Col, Empty, Result, Row, Skeleton, Space, Typography } from 'antd'

const PricingToolsPage = () => {
  return (
    <Space direction="vertical" size={24} style={{ width: '100%' }}>
      <div>
        <Typography.Title level={3} style={{ marginBottom: 0 }}>
          核价工具
        </Typography.Title>
        <Typography.Text type="secondary">
          后续将在此集成核价器、情景对比、审批回路等功能模块。
        </Typography.Text>
      </div>
      <Row gutter={[24, 24]}>
        <Col xs={24} lg={14}>
          <Card title="实时核价面板">
            <Skeleton active paragraph={{ rows: 4 }} />
            <Result
              status="info"
              title="核价引擎对接中"
              subTitle="后续将可从此处选择模型、工艺与材料进行一键核价。"
              extra={<Button type="primary" disabled>敬请期待</Button>}
              style={{ marginTop: 16 }}
            />
          </Card>
        </Col>
        <Col xs={24} lg={10}>
          <Card title="历史记录">
            <Empty description="暂无核价记录" />
          </Card>
        </Col>
      </Row>
    </Space>
  )
}

export default PricingToolsPage


