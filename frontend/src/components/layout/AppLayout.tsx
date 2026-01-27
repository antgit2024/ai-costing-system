import { Badge, Button, Layout, Menu, Space } from 'antd'
import AppstoreOutlined from '@ant-design/icons/lib/icons/AppstoreOutlined'
import BarChartOutlined from '@ant-design/icons/lib/icons/BarChartOutlined'
import DatabaseOutlined from '@ant-design/icons/lib/icons/DatabaseOutlined'
import DeploymentUnitOutlined from '@ant-design/icons/lib/icons/DeploymentUnitOutlined'
import ExperimentOutlined from '@ant-design/icons/lib/icons/ExperimentOutlined'
import SettingOutlined from '@ant-design/icons/lib/icons/SettingOutlined'
import ShopOutlined from '@ant-design/icons/lib/icons/ShopOutlined'
import CloudSyncOutlined from '@ant-design/icons/lib/icons/CloudSyncOutlined'
import UnorderedListOutlined from '@ant-design/icons/lib/icons/UnorderedListOutlined'
import ToolOutlined from '@ant-design/icons/lib/icons/ToolOutlined'
import type { MenuProps } from 'antd'
import { useMemo, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'

import TaskCenterDrawer from '@/components/common/TaskCenterDrawer'
import { fetchTaskCenter } from '@/services/planner'
import './appLayoutMenu.css'

const { Header, Sider, Content } = Layout

type TaskCenterResp = Awaited<ReturnType<typeof fetchTaskCenter>>
type TaskProbe = {
  statuses: string[]
  runningCount: number
}

const subItemLabel = (text: string, to: string) => (
  <Link to={to} className="sidebar-sub-link">
    <span className="sidebar-sub-dot" />
    <span className="sidebar-sub-text">{text}</span>
  </Link>
)

const menuItems: MenuProps['items'] = [
  {
    key: '/costing/base',
    icon: <SettingOutlined />,
    label: '基础设置',
    children: [
      { key: '/costing/materials', label: subItemLabel('采购物料', '/costing/materials') },
      { key: '/costing/virtual-materials', label: subItemLabel('虚拟物料', '/costing/virtual-materials') },
      { key: '/costing/structure-standards', label: subItemLabel('结构标准', '/costing/structure-standards') },
      { key: '/costing/process-modules', label: subItemLabel('工艺模块', '/costing/process-modules') },
      { key: '/costing/processes', label: subItemLabel('工序管理', '/costing/processes') },
      { key: '/costing/taxonomy', label: subItemLabel('分类管理', '/costing/taxonomy') },
    ],
  },
  {
    key: '/costing/models',
    icon: <AppstoreOutlined />,
    label: '模型管理',
    children: [
      { key: '/costing/sample-models', label: subItemLabel('打样模型', '/costing/sample-models') },
      { key: '/costing/standard-models', label: subItemLabel('标准模型', '/costing/standard-models') },
      { key: '/costing/bundle-templates', label: subItemLabel('套装模板', '/costing/bundle-templates') },
    ],
  },
  {
    key: '/costing/listing',
    icon: <ShopOutlined />,
    label: '上架测试',
    children: [
      { key: '/costing/product-listing', label: subItemLabel('测试台', '/costing/product-listing') },
      { key: '/costing/tmall-sku-generator', label: subItemLabel('规格生成', '/costing/tmall-sku-generator') },
      { key: '/costing/pricing-tools', label: subItemLabel('价格预推', '/costing/pricing-tools') },
    ],
  },
  {
    key: '/costing/products',
    icon: <DatabaseOutlined />,
    label: '货品管理',
    children: [
      { key: '/costing/sku-master', label: subItemLabel('商品关联', '/costing/sku-master') },
      { key: '/costing/spec-matching', label: subItemLabel('规格解析', '/costing/spec-matching') },
      { key: '/costing/shipments', label: subItemLabel('发货台账', '/costing/shipments') },
      { key: '/costing/shipping-rules', label: subItemLabel('发货规则', '/costing/shipping-rules') },
    ],
  },
  {
    key: '/costing/automation',
    icon: <CloudSyncOutlined />,
    label: '自动化/作业中心',
    children: [{ key: '/costing/shipments/ops', label: subItemLabel('发货作业中心', '/costing/shipments/ops') }],
  },
  {
    key: '/costing/insights',
    icon: <BarChartOutlined />,
    label: '数据洞察',
    children: [
      { key: '/costing/insights/after-sales', label: subItemLabel('售后分析', '/costing/insights/after-sales') },
      { key: '/costing/insights/sales', label: subItemLabel('销售分析', '/costing/insights/sales') },
      { key: '/costing/insights/models', label: subItemLabel('模型分析', '/costing/insights/models') },
      { key: '/costing/insights/shops', label: subItemLabel('店铺数据', '/costing/insights/shops') },
    ],
  },
  {
    key: '/costing/tools',
    icon: <ToolOutlined />,
    label: '生产工具',
    children: [{ key: '/costing/production-scan', label: subItemLabel('生产扫码', '/costing/production-scan') }],
  },
  // 规划区：保持入口，但放到底部
  {
    key: '/planner_group',
    icon: <DeploymentUnitOutlined />,
    label: 'PLANNER',
    children: [
      { key: '/', label: subItemLabel('总览', '/') },
      { key: '/planner', label: subItemLabel('PLANNER 工作区', '/planner') },
      { key: '/planner/scenarios', label: subItemLabel('场景列表', '/planner/scenarios') },
      { key: '/planner/scenario-builder', label: subItemLabel('场景 BUILDER', '/planner/scenario-builder') },
    ],
  },
  {
    key: '/labs',
    icon: <ExperimentOutlined />,
    label: <span style={{ opacity: 0.4 }}>Labs（规划中）</span>,
    disabled: true,
  },
]

interface AppLayoutProps {
  children: React.ReactNode
}

const AppLayout = ({ children }: AppLayoutProps) => {
  const location = useLocation()
  const [taskOpen, setTaskOpen] = useState(false)
  const hideSidebar = location.pathname.startsWith('/costing/production-scan')

  /**
   * 任务角标探针（性能敏感）：
   * - 只需要“runningCount”，不需要完整 payload/result
   * - task-center 的 payload/result 可能很大；频繁轮询会造成 Chrome 主线程卡顿（甚至“页面无响应”）
   * - 因此：limit 降到 5 + select 压缩缓存数据 + 页面不可见时停止轮询 + 降低轮询频率
   */
  const taskProbeQuery = useQuery<TaskCenterResp, Error, TaskProbe>({
    queryKey: ['task-center-probe'],
    queryFn: () => fetchTaskCenter({ limit: 5 }),
    select: (data) => {
      const statuses = (data?.items ?? []).map((t) => String((t as any)?.status ?? ''))
      const runningCount = statuses.filter((s) => ['pending', 'running', 'processing'].includes(s)).length
      return { statuses, runningCount }
    },
    refetchInterval: (q) => {
      // 页面不可见时不轮询，避免后台占用主线程
      if (typeof document !== 'undefined' && document.visibilityState === 'hidden') return false

      // 注意：这里的 q.state.data 是 queryFn 的原始返回（非 select 后的数据）
      const items = (q.state.data?.items ?? []) as any[]
      const hasRunning = items.some((t) =>
        ['pending', 'running', 'processing'].includes(String((t as any)?.status ?? '')),
      )
      // 降低频率：运行中 10s / 空闲 60s（任务角标只是探针，避免频繁轮询占用网络/主线程）
      return hasRunning ? 10000 : 60000
    },
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: false,
  })

  const runningCount =
    taskProbeQuery.data?.runningCount ?? 0

  const selectedKeys = useMemo(() => {
    if (location.pathname.startsWith('/planner/scenario-builder')) {
      return ['/planner/scenario-builder']
    }
    if (location.pathname.startsWith('/planner/scenarios')) {
      return ['/planner/scenarios']
    }
    if (location.pathname.startsWith('/planner')) {
      return ['/planner']
    }
    if (location.pathname.startsWith('/costing')) {
      if (location.pathname.startsWith('/costing/materials')) {
        return ['/costing/materials']
      }
      if (location.pathname.startsWith('/costing/virtual-materials')) {
        return ['/costing/virtual-materials']
      }
      if (location.pathname.startsWith('/costing/processes')) {
        return ['/costing/processes']
      }
      if (location.pathname.startsWith('/costing/process-modules')) {
        return ['/costing/process-modules']
      }
      if (location.pathname.startsWith('/costing/taxonomy')) {
        return ['/costing/taxonomy']
      }
      if (location.pathname.startsWith('/costing/sample-models')) {
        return ['/costing/sample-models']
      }
      if (location.pathname.startsWith('/costing/standard-models')) {
        return ['/costing/standard-models']
      }
      if (location.pathname.startsWith('/costing/pricing-tools')) {
        return ['/costing/pricing-tools']
      }
      if (location.pathname.startsWith('/costing/shipments')) {
        if (location.pathname.startsWith('/costing/shipments/ops')) return ['/costing/shipments/ops']
        return ['/costing/shipments']
      }
      if (location.pathname.startsWith('/costing/product-listing')) {
        return ['/costing/product-listing']
      }
      if (location.pathname.startsWith('/costing/bundle-templates')) {
        return ['/costing/bundle-templates']
      }
      if (location.pathname.startsWith('/costing/sku-master')) {
        return ['/costing/sku-master']
      }
      if (location.pathname.startsWith('/costing/production-scan')) {
        return ['/costing/production-scan']
      }
      if (location.pathname.startsWith('/costing/spec-matching')) {
        return ['/costing/spec-matching']
      }
      if (location.pathname.startsWith('/costing/insights/after-sales')) {
        return ['/costing/insights/after-sales']
      }
      if (location.pathname.startsWith('/costing/insights/sales')) {
        return ['/costing/insights/sales']
      }
      if (location.pathname.startsWith('/costing/insights/models')) {
        return ['/costing/insights/models']
      }
      if (location.pathname.startsWith('/costing/insights/shops')) {
        return ['/costing/insights/shops']
      }
      if (location.pathname.startsWith('/costing/tmall-sku-generator')) {
        return ['/costing/tmall-sku-generator']
      }
      return ['/costing/materials']
    }
    return ['/']
  }, [location.pathname])

  return (
    <>
      <Layout className={hideSidebar ? 'app-layout app-layout--mobile' : 'app-layout'}>
        {!hideSidebar ? (
          <Sider width={240} theme="dark">
            <div className="sidebar-logo">
              <img src="/logo-full.svg" alt="饰家如画©智慧工厂" />
            </div>
            <Menu
              theme="dark"
              mode="inline"
              selectedKeys={selectedKeys}
              items={menuItems}
              style={{ borderInlineEnd: 0 }}
            />
          </Sider>
        ) : null}
        <Layout>
          {!hideSidebar ? (
            <Header className="app-header">
            <div className="app-header-inner">
                    <div className="app-header-brand" aria-label="饰家如画®AI智慧数字工厂">
                      饰家如画®AI智慧数字工厂
                    </div>
              <Space>
                <Badge count={runningCount} size="small" className={runningCount ? 'task-badge-blink' : undefined}>
                  <Button icon={<UnorderedListOutlined />} onClick={() => setTaskOpen(true)}>
                    任务列表
                  </Button>
                </Badge>
              </Space>
            </div>
            </Header>
          ) : null}
          <Content className="app-content">{children}</Content>
        </Layout>
      </Layout>
      <TaskCenterDrawer open={taskOpen} onClose={() => setTaskOpen(false)} />
    </>
  )
}

export default AppLayout

