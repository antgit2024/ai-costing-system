import { Card, Tabs, Typography, Empty, Space, Tag, Alert } from 'antd'
import { useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'

const { Title, Text } = Typography

type AfterSalesBizTabKey = 'pending' | 'refunded' | 'reship' | 'exception'

/**
 * 🔄 售后管理 — 上架员/客服日常工作台(骨架版)
 *
 * 现状(2026-05-07):
 *   - 后端数据完整: AfterSalesImportBatch / AfterSalesLine / AfterSalesExceptionQueue + Jackyun 同步
 *   - 但之前只有"售后分析"看板(/costing/insights/after-sales),没有作业页
 *   - 本页是新开口子,跟"发货管理"并列,统一"业务数据管理"心智
 *
 * v0.1 范围(本周):
 *   - 只渲染骨架(Tab + 筛选器 placeholder + Empty),不接真实数据
 *   - 让员工/老板先看到"位置和形态",下周填实现
 */
export default function AfterSalesManagementPage() {
  const [sp, setSp] = useSearchParams()

  const initialTab: AfterSalesBizTabKey = useMemo(() => {
    const t = String(sp.get('tab') ?? '').trim() as AfterSalesBizTabKey
    if (t === 'refunded' || t === 'reship' || t === 'exception') return t
    return 'pending'
  }, [sp])

  const [activeTab, setActiveTab] = useState<AfterSalesBizTabKey>(initialTab)

  const handleTabChange = (k: string) => {
    setActiveTab(k as AfterSalesBizTabKey)
    const next = new URLSearchParams(sp)
    next.set('tab', k)
    setSp(next, { replace: true })
  }

  return (
    <div style={{ padding: 16 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between' }}>
        <div>
          <Title level={3} style={{ marginBottom: 4 }}>
            🔄 售后管理
          </Title>
          <Text type="secondary">
            统一处理来自吉客云的退款/补发/换货等售后单。下周上线交互,本周先看骨架。
          </Text>
        </div>
        <Space>
          <Tag color="orange">骨架版 v0.1</Tag>
          <Tag>下周上线</Tag>
        </Space>
      </div>

      <Alert
        type="info"
        showIcon
        style={{ marginTop: 12 }}
        message="本页为骨架占位。后端数据已经全部接入(AfterSalesLine / AfterSalesExceptionQueue),下周填充列表+操作按钮。"
        description={
          <Space direction="vertical" size={2}>
            <Text type="secondary">如需查看售后分析数据,请去 数据洞察 → 售后分析</Text>
            <Text type="secondary">如需查看售后明细单,目前还需要直接通过 API 查询(尚未做 UI)</Text>
          </Space>
        }
      />

      <div style={{ marginTop: 12 }}>
        <Tabs
          activeKey={activeTab}
          onChange={handleTabChange}
          items={[
            {
              key: 'pending',
              label: '🔴 待退款审核',
              children: (
                <Card size="small">
                  <Empty description="待退款审核列表(开发中)" />
                </Card>
              ),
            },
            {
              key: 'refunded',
              label: '✅ 已退款',
              children: (
                <Card size="small">
                  <Empty description="已退款列表(开发中)" />
                </Card>
              ),
            },
            {
              key: 'reship',
              label: '📦 待补发',
              children: (
                <Card size="small">
                  <Empty description="待补发列表(开发中)" />
                </Card>
              ),
            },
            {
              key: 'exception',
              label: '⚠️ 异常',
              children: (
                <Card size="small">
                  <Empty description="售后异常队列(开发中)" />
                </Card>
              ),
            },
          ]}
        />
      </div>
    </div>
  )
}
