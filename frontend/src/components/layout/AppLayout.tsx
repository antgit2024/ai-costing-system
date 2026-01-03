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

type TaskCenterResp = Awaited<ReturnType<typeof fetchTaskCenter>>
type TaskProbe = {
  statuses: string[]
  runningCount: number
}

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
        key: '/costing/structure-standards',
        label: <Link to="/costing/structure-standards">结构标准</Link>,
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
      // 降低频率：运行中 5s / 空闲 15s
      return hasRunning ? 5000 : 15000
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

