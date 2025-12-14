import { lazy, Suspense } from 'react'
import { Drawer, Skeleton } from 'antd'
import type { AuditLogDrawerProps } from './AuditLogDrawer'

const LazyAuditDrawer = lazy(() => import('./AuditLogDrawer'))

const AuditLogDrawerLazy = (props: AuditLogDrawerProps) => (
  <Suspense
    fallback={
      props.open ? (
        <Drawer open width={520} title="审计日志" onClose={props.onClose}>
          <Skeleton active paragraph={{ rows: 8 }} />
        </Drawer>
      ) : null
    }
  >
    <LazyAuditDrawer {...props} />
  </Suspense>
)

export default AuditLogDrawerLazy















