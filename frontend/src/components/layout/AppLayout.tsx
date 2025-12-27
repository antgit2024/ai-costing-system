import { Badge, Button, Layout, Menu, Space } from 'antd'
import AreaChartOutlined from '@ant-design/icons/lib/icons/AreaChartOutlined'
import CalculatorOutlined from '@ant-design/icons/lib/icons/CalculatorOutlined'
import DeploymentUnitOutlined from '@ant-design/icons/lib/icons/DeploymentUnitOutlined'
import ExperimentOutlined from '@ant-design/icons/lib/icons/ExperimentOutlined'
import HomeOutlined from '@ant-design/icons/lib/icons/HomeOutlined'
import SettingOutlined from '@ant-design/icons/lib/icons/SettingOutlined'
import UnorderedListOutlined from '@ant-design/icons/lib/icons/UnorderedListOutlined'
import type { MenuProps } from 'antd'
import { useMemo, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'

import TaskCenterDrawer from '@/components/common/TaskCenterDrawer'
import { fetchTaskCenter } from '@/services/planner'

const { Header, Sider, Content } = Layout

const menuItems: MenuProps['items'] = [
  {
    key: '/',
    icon: <HomeOutlined />,
    label: <Link to="/">总览</Link>,
  },
  {
    key: '/planner',
    icon: <DeploymentUnitOutlined />,
    label: <Link to="/planner">Planner 工作区</Link>,
  },
  {
    key: '/planner/scenarios',
    icon: <UnorderedListOutlined />,
    label: <Link to="/planner/scenarios">场景列表</Link>,
  },
  {
    key: '/planner/scenario-builder',
    icon: <AreaChartOutlined />,
    label: <Link to="/planner/scenario-builder">场景 Builder</Link>,
  },
  {
    key: '/costing',
    icon: <CalculatorOutlined />,
    label: '成本核算',
    children: [
      {
        key: '/costing/materials',
        label: <Link to="/costing/materials">物料管理</Link>,
      },
      {
        key: '/costing/virtual-materials',
        label: <Link to="/costing/virtual-materials">虚拟物料</Link>,
      },
      {
        key: '/costing/processes',
        label: <Link to="/costing/processes">工序管理</Link>,
      },
      {
        key: '/costing/process-modules',
        label: <Link to="/costing/process-modules">工艺模块</Link>,
      },
      {
        key: '/costing/taxonomy',
        icon: <SettingOutlined />,
        label: (
          <Link to="/costing/taxonomy">
            分类管理
          </Link>
        ),
      },
      {
        key: '/costing/sample-models',
        label: <Link to="/costing/sample-models">打样模型</Link>,
      },
      {
        key: '/costing/standard-models',
        label: <Link to="/costing/standard-models">标准模型</Link>,
      },
      {
        key: '/costing/pricing-tools',
        label: <Link to="/costing/pricing-tools">核价工具</Link>,
      },
      {
        key: '/costing/shipments',
        label: <Link to="/costing/shipments">发货批次 / BOM快照</Link>,
      },
      {
        key: '/costing/sku-master',
        label: <Link to="/costing/sku-master">SKU 主档 / 商品关联</Link>,
      },
      {
        key: '/costing/spec-matching',
        label: <Link to="/costing/spec-matching">规格匹配工作台（尺寸解析）</Link>,
      },
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

  const taskProbeQuery = useQuery({
    queryKey: ['task-center-probe'],
    queryFn: () => fetchTaskCenter({ limit: 30 }),
    refetchInterval: (q) => {
      const items = q.state.data?.items ?? []
      const hasRunning = items.some((t) => ['pending', 'running', 'processing'].includes(String(t.status)))
      return hasRunning ? 2000 : 8000
    },
  })

  const runningCount =
    taskProbeQuery.data?.items?.filter((t) =>
      ['pending', 'running', 'processing'].includes(String(t.status)),
    ).length ?? 0

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
        return ['/costing/shipments']
      }
      if (location.pathname.startsWith('/costing/sku-master')) {
        return ['/costing/sku-master']
      }
      if (location.pathname.startsWith('/costing/spec-matching')) {
        return ['/costing/spec-matching']
      }
      return ['/costing']
    }
    return ['/']
  }, [location.pathname])

  return (
    <>
      <Layout className="app-layout">
        <Sider width={240} theme="dark">
          <div className="sidebar-logo">AI Costing</div>
          <Menu
            theme="dark"
            mode="inline"
            selectedKeys={selectedKeys}
            items={menuItems}
            style={{ borderInlineEnd: 0 }}
          />
        </Sider>
        <Layout>
          <Header className="app-header">
            <div className="app-header-inner">
              <div>Planner 控制台</div>
              <Space>
                <Badge count={runningCount} size="small" className={runningCount ? 'task-badge-blink' : undefined}>
                  <Button icon={<UnorderedListOutlined />} onClick={() => setTaskOpen(true)}>
                    任务列表
                  </Button>
                </Badge>
              </Space>
            </div>
          </Header>
          <Content className="app-content">{children}</Content>
        </Layout>
      </Layout>
      <TaskCenterDrawer open={taskOpen} onClose={() => setTaskOpen(false)} />
    </>
  )
}

export default AppLayout

