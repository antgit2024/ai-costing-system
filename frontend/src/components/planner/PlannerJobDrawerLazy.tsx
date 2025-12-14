import { lazy, Suspense } from 'react'
import { Drawer, Skeleton } from 'antd'
import type { PlannerJobDrawerProps } from './PlannerJobDrawer'

const LazyJobDrawer = lazy(() => import('./PlannerJobDrawer'))

const PlannerJobDrawerLazy = (props: PlannerJobDrawerProps) => (
  <Suspense
    fallback={
      props.open ? (
        <Drawer open title={props.title ?? '作业进度'} width={props.width ?? 440} onClose={props.onClose}>
          <Skeleton active paragraph={{ rows: 6 }} />
        </Drawer>
      ) : null
    }
  >
    <LazyJobDrawer {...props} />
  </Suspense>
)

export default PlannerJobDrawerLazy

