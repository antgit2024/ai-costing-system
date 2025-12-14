import {
  Card,
  Input,
  List,
  Select,
  Space,
  Tag,
  Typography,
  Skeleton,
  Empty,
} from 'antd'
import TeamOutlined from '@ant-design/icons/lib/icons/TeamOutlined'
import type { Initiative, PaginatedResponse } from '@/types/planner'
import { INITIATIVE_STATUS_OPTIONS } from '@/constants/planner'

const { Paragraph, Text } = Typography

export interface InitiativeListFilters {
  status?: string
  owner_id?: string
  tag?: string
}

interface InitiativeListCardProps {
  data?: PaginatedResponse<Initiative>
  loading: boolean
  selectedId?: string
  filters: InitiativeListFilters
  page: number
  onSelect: (initiative: Initiative) => void
  onFiltersChange: (next: InitiativeListFilters) => void
  onPageChange: (page: number) => void
}

const InitiativeListCard = ({
  data,
  loading,
  selectedId,
  filters,
  page,
  onSelect,
  onFiltersChange,
  onPageChange,
}: InitiativeListCardProps) => {
  const initiatives = data?.items ?? []

  return (
    <Card
      title="Initiative 列表"
      className="initiative-list-card planner-section"
      extra={
        <Space size={8}>
          <Select
            placeholder="状态"
            size="small"
            style={{ width: 120 }}
            value={filters.status}
            onChange={(value) => onFiltersChange({ ...filters, status: value })}
            options={INITIATIVE_STATUS_OPTIONS}
            allowClear
          />
          <Input
            placeholder="Owner ID"
            size="small"
            style={{ width: 120 }}
            value={filters.owner_id}
            onChange={(e) => onFiltersChange({ ...filters, owner_id: e.target.value || undefined })}
          />
          <Input
            placeholder="Tag"
            size="small"
            style={{ width: 120 }}
            value={filters.tag}
            onChange={(e) => onFiltersChange({ ...filters, tag: e.target.value || undefined })}
          />
        </Space>
      }
    >
      {loading ? (
        <Skeleton active paragraph={{ rows: 6 }} />
      ) : initiatives.length === 0 ? (
        <Empty description="暂无数据" />
      ) : (
        <List
          dataSource={initiatives}
          pagination={{
            pageSize: data?.page_size ?? 6,
            current: page,
            total: data?.total ?? 0,
            size: 'small',
            onChange: onPageChange,
          }}
          renderItem={(item) => (
            <List.Item
              key={item.id}
              style={{
                borderRadius: 10,
                border: item.id === selectedId ? '1px solid #3057e1' : '1px solid #edf0f7',
                padding: '12px 16px',
                cursor: 'pointer',
                background: item.id === selectedId ? 'rgba(48,87,225,0.04)' : '#fff',
              }}
              onClick={() => onSelect(item)}
            >
              <List.Item.Meta
                title={
                  <Space size={12}>
                    <Text strong>{item.name}</Text>
                    <Tag color="blue">{item.status}</Tag>
                    <Text type="secondary">#{item.code}</Text>
                  </Space>
                }
                description={
                  <Space direction="vertical" size={4} style={{ width: '100%' }}>
                    <Paragraph ellipsis={{ rows: 2 }}>{item.description || '暂无描述'}</Paragraph>
                    <Space size={16}>
                      <Text type="secondary">
                        <TeamOutlined /> Owner: {item.owner_id}
                      </Text>
                      {item.tags?.slice(0, 3).map((tag) => (
                        <Tag key={tag}>{tag}</Tag>
                      ))}
                    </Space>
                  </Space>
                }
              />
            </List.Item>
          )}
        />
      )}
    </Card>
  )
}

export default InitiativeListCard

