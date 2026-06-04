import { Tabs, Typography, Space, Tag } from 'antd'
import { useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import GovernanceBacklogTab from '@/pages/costing/shipment-ops/components/GovernanceBacklogTab'

import DoneTab from './components/DoneTab'
import PendingTab from './components/PendingTab'

const { Title, Text } = Typography

type ShipmentBizTabKey = 'pending' | 'processing' | 'done' | 'long_tail'

/**
 * 🚚 发货管理 — 上架员日常工作台
 *
 * 设计目标(对照老的 /costing/shipments/ops):
 *   - /costing/shipments/ops 是工程师/运维视角:按"批次"组织,每个批次进去再处理异常
 *   - 本页是上架员视角:按"业务对象(发货行)"组织,跨所有批次汇总成 4 个 Tab
 *     - 待处理: 所有 unbound 发货行,等待员工决策
 *     - 处理中: pending_model SKU(已决定建模,等模型发布)
 *     - 已完成: 已绑定模型 + 已出 BomSnapshot
 *     - 长尾池: 标记为 do_not_model 的 SKU
 *
 * 接口策略(防返工):
 *   - 当前: 行级操作前端编排 bind + governance + recompute 多个接口
 *   - 未来: 后端落地 POST /shipments/lines/{id}/resolve 后,本页只改
 *     services/planner.ts 里的 resolveShipmentLine 函数,UI/组件 0 改动
 *   - 详见 known_issues.md Issue 26
 */
export default function ShipmentManagementPage() {
  const [sp, setSp] = useSearchParams()

  const initialTab: ShipmentBizTabKey = useMemo(() => {
    const t = String(sp.get('tab') ?? '').trim() as ShipmentBizTabKey
    if (t === 'processing' || t === 'done' || t === 'long_tail') return t
    return 'pending'
  }, [sp])

  const [activeTab, setActiveTab] = useState<ShipmentBizTabKey>(initialTab)

  const handleTabChange = (k: string) => {
    setActiveTab(k as ShipmentBizTabKey)
    const next = new URLSearchParams(sp)
    next.set('tab', k)
    setSp(next, { replace: true })
  }

  return (
    <div style={{ padding: 16 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between' }}>
        <div>
          <Title level={3} style={{ marginBottom: 4 }}>
            🚚 发货管理
          </Title>
          <Text type="secondary">
            日常工作:看到新发货 → 给每条选商品模型 → 系统自动算成本。处理过的下次同款自动用,不需要重复操作。
          </Text>
        </div>
        <Space>
          <Tag color="blue">本周新建</Tag>
          <Tag color="green">v0.2 全 Tab 接入</Tag>
        </Space>
      </div>

      <div style={{ marginTop: 12 }}>
        <Tabs
          activeKey={activeTab}
          onChange={handleTabChange}
          items={[
            {
              key: 'pending',
              label: '🔴 待处理',
              children: <PendingTab />,
            },
            {
              key: 'processing',
              label: '⏸️ 处理中',
              children: (
                <GovernanceBacklogTab status="pending_model" primaryActionLabel="去建模" />
              ),
            },
            {
              key: 'done',
              label: '✅ 已完成',
              children: <DoneTab />,
            },
            {
              key: 'long_tail',
              label: '🚫 长尾池',
              children: <GovernanceBacklogTab status="do_not_model" />,
            },
          ]}
        />
      </div>
    </div>
  )
}
