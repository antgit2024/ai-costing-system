import { Button, Space, Tabs, Typography } from 'antd'
import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'

import BatchWorkbench from './components/BatchWorkbench'
import BulkCostingTab from './components/BulkCostingTab'
import ImportWizardModal from './components/ImportWizardModal'

const { Title, Text } = Typography

export default function ShipmentOpsPage() {
  const navigate = useNavigate()
  const [sp] = useSearchParams()

  const initialTab = useMemo(() => {
    const t = String(sp.get('tab') ?? '').trim()
    if (t === 'bulk') return 'bulk'
    if (String(sp.get('from') ?? '').trim() === 'ledger') return 'bulk'
    return 'documents'
  }, [sp])

  const [activeTab, setActiveTab] = useState<'documents' | 'bulk'>(initialTab as any)
  const [importOpen, setImportOpen] = useState(false)

  useEffect(() => {
    // keep in sync when user navigates with query params
    setActiveTab(initialTab as any)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialTab])

  return (
    <div style={{ padding: 16 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between' }}>
        <div>
          <Title level={3} style={{ marginBottom: 4 }}>
            发货作业中心
          </Title>
          <Text type="secondary">
            ERP 作业口径：导入发货单 → 处理待办（未绑定/缺规格/失败） → 查看成本快照 → 批量计价快照（按台账筛选范围）。
          </Text>
        </div>
        <Space wrap>
          <Button type="primary" onClick={() => setImportOpen(true)}>
            导入发货单
          </Button>
          <Button onClick={() => navigate('/costing/shipments')}>去发货台账</Button>
        </Space>
      </div>

      <div style={{ marginTop: 12 }}>
        <Tabs
          activeKey={activeTab}
          onChange={(k) => setActiveTab(k as any)}
          items={[
            {
              key: 'documents',
              label: '单据/待处理/快照',
              children: <BatchWorkbench onOpenImport={() => setImportOpen(true)} />,
            },
            {
              key: 'bulk',
              label: '批量计价快照（按台账范围）',
              children: <BulkCostingTab />,
            },
          ]}
        />
      </div>

      <ImportWizardModal
        open={importOpen}
        onClose={() => setImportOpen(false)}
        onImported={(batchId) => {
          // imported → return to documents tab, focus the new batch
          setImportOpen(false)
          setActiveTab('documents')
          if (batchId) {
            navigate(`/costing/shipments/ops?tab=documents&batch_id=${encodeURIComponent(batchId)}`)
          }
        }}
      />
    </div>
  )
}

