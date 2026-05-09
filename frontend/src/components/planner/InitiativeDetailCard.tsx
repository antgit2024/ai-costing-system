import { Card, Col, Descriptions, Empty, Row, Skeleton, Space, Statistic, Tag } from 'antd'
import type { Initiative } from '@/types/planner'
import { formatBeijingTime } from '@/utils/beijingTime'

interface InitiativeDetailCardProps {
  initiative?: Initiative | null
  loading: boolean
}

const InitiativeDetailCard = ({ initiative, loading }: InitiativeDetailCardProps) => {
  return (
    <Card title="Initiative 详情" className="initiative-detail-card planner-section" bodyStyle={{ minHeight: 240 }}>
      {loading ? (
        <Skeleton active paragraph={{ rows: 6 }} />
      ) : !initiative ? (
        <Empty description="请选择一个 initiative" />
      ) : (
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          <Row gutter={16}>
            <Col span={12}>
              <Statistic title="状态" valueRender={() => <Tag color="blue">{initiative.status}</Tag>} />
            </Col>
            <Col span={12}>
              <Statistic
                title="目标上线时间"
                value={initiative.target_launch_date ? formatBeijingTime(initiative.target_launch_date, 'YYYY-MM-DD') : 'N/A'}
              />
            </Col>
          </Row>
          <Descriptions column={1} colon={false} size="small">
            <Descriptions.Item label="Sponsor">{initiative.sponsor || '未指定'}</Descriptions.Item>
            <Descriptions.Item label="Owner">{initiative.owner_id}</Descriptions.Item>
            <Descriptions.Item label="Currency">{initiative.currency}</Descriptions.Item>
            <Descriptions.Item label="Tags">
              <Space size={6}>
                {initiative.tags?.length
                  ? initiative.tags.map((tag) => (
                      <Tag color="geekblue" key={tag}>
                        {tag}
                      </Tag>
                    ))
                  : '暂无'}
              </Space>
            </Descriptions.Item>
            <Descriptions.Item label="描述">{initiative.description || '无'}</Descriptions.Item>
          </Descriptions>
        </Space>
      )}
    </Card>
  )
}

export default InitiativeDetailCard



















































