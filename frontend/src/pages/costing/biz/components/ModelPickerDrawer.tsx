import { Alert, Button, Drawer, Empty, Input, List, Space, Spin, Tag, Typography } from 'antd'
import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'

import { fetchPublishedStandardModels } from '@/services/planner'
import type { PublishedStandardModelCandidate } from '@/types/planner'

const { Text } = Typography

export interface ModelPickerDrawerProps {
  open: boolean
  /** 用于搜索框上方的"上下文卡片",告诉员工"当前在为哪条 SKU 选模型" */
  context?: {
    skuCode?: string | null
    specText?: string | null
    /** "系统建议"模型(如有,放在第一位高亮) */
    suggestedModelId?: string | null
  }
  onClose: () => void
  onPicked: (candidate: PublishedStandardModelCandidate) => void
  /** 可选: 抽屉默认搜索词(比如自动用 SKU 编码前缀) */
  initialSearch?: string
}

/**
 * 选模型抽屉 - 共享组件
 *
 * 服务于"业务管理"下任何需要"绑定到现有模型"的场景:
 *   - 🚚 发货管理 行级"选其他模型..."
 *   - (未来) 🔄 售后管理 行级"选其他模型..."
 *
 * 设计原则:
 *   - 显示 SKU 上下文(规格文本),让员工能直观判断
 *   - 系统建议的模型置顶高亮(如有传入 suggestedModelId)
 *   - 搜索框 debounce + React Query 缓存,响应迅速
 *   - 单选确认而非"列表里点一下就生效",避免误触
 */
export default function ModelPickerDrawer({
  open,
  context,
  onClose,
  onPicked,
  initialSearch,
}: ModelPickerDrawerProps) {
  const [search, setSearch] = useState<string>(initialSearch ?? '')
  const [picked, setPicked] = useState<PublishedStandardModelCandidate | null>(null)

  useEffect(() => {
    if (open) {
      setSearch(initialSearch ?? '')
      setPicked(null)
    }
  }, [open, initialSearch])

  const listQuery = useQuery({
    queryKey: ['model-picker-published', search],
    queryFn: () => fetchPublishedStandardModels({ search: search.trim() || undefined, limit: 50 }),
    enabled: open,
    staleTime: 30_000,
  })

  const items = useMemo(() => listQuery.data?.items ?? [], [listQuery.data?.items])

  // 系统建议置顶
  const sortedItems = useMemo(() => {
    const suggestedId = context?.suggestedModelId
    if (!suggestedId) return items
    const idx = items.findIndex((it) => it.model_id === suggestedId)
    if (idx <= 0) return items
    return [items[idx], ...items.slice(0, idx), ...items.slice(idx + 1)]
  }, [items, context?.suggestedModelId])

  return (
    <Drawer
      title="选一个商品模型"
      placement="right"
      width={520}
      open={open}
      onClose={onClose}
      footer={
        <Space style={{ width: '100%', justifyContent: 'space-between' }}>
          <Text type="secondary">
            {picked ? (
              <>
                已选: <Tag color="blue">{picked.model_code}</Tag> {picked.model_name}
              </>
            ) : (
              '从下方列表选一个模型,然后点"确认绑定"'
            )}
          </Text>
          <Space>
            <Button onClick={onClose}>取消</Button>
            <Button
              type="primary"
              disabled={!picked}
              onClick={() => {
                if (picked) onPicked(picked)
              }}
            >
              确认绑定
            </Button>
          </Space>
        </Space>
      }
    >
      {context?.skuCode || context?.specText ? (
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 12 }}
          message={
            <Space direction="vertical" size={2} style={{ width: '100%' }}>
              {context.skuCode ? (
                <Text>
                  当前 SKU: <Text strong>{context.skuCode}</Text>
                </Text>
              ) : null}
              {context.specText ? (
                <Text type="secondary" style={{ fontSize: 12 }}>
                  规格: {context.specText}
                </Text>
              ) : null}
            </Space>
          }
        />
      ) : null}

      <Input.Search
        placeholder="按模型编码/名称搜索"
        allowClear
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        onSearch={(v) => setSearch(v)}
        style={{ marginBottom: 12 }}
      />

      {listQuery.isLoading ? (
        <div style={{ textAlign: 'center', padding: 32 }}>
          <Spin />
        </div>
      ) : sortedItems.length === 0 ? (
        <Empty description="没有匹配的已发布模型(请先去模型管理建模并发布)" />
      ) : (
        <List
          size="small"
          bordered
          dataSource={sortedItems}
          renderItem={(item) => {
            const isPicked = picked?.model_id === item.model_id
            const isSuggested = context?.suggestedModelId === item.model_id
            return (
              <List.Item
                onClick={() => setPicked(item)}
                style={{
                  cursor: 'pointer',
                  background: isPicked ? 'rgba(141, 166, 194, 0.10)' : undefined,
                }}
              >
                <Space direction="vertical" size={2} style={{ width: '100%' }}>
                  <Space wrap>
                    <Tag color={isSuggested ? 'gold' : 'blue'}>{item.model_code}</Tag>
                    <Text strong>{item.model_name}</Text>
                    {isSuggested ? <Tag color="gold">系统建议</Tag> : null}
                    {isPicked ? <Tag color="green">已选</Tag> : null}
                  </Space>
                  {item.version_label ? (
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      已发布版本: {item.version_label}
                    </Text>
                  ) : null}
                </Space>
              </List.Item>
            )
          }}
        />
      )}
    </Drawer>
  )
}
