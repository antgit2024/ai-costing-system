import { useEffect, useState } from 'react'
import { Col, Empty, Result, Row, Space, Spin } from 'antd'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import InitiativeListCard, { type InitiativeListFilters } from '@/components/planner/InitiativeListCard'
import InitiativeDetailCard from '@/components/planner/InitiativeDetailCard'
import PackageTreePanel from '@/components/planner/PackageTreePanel'
import LineItemsTable from '@/components/planner/LineItemsTable'
import { fetchInitiativeById, fetchInitiatives, fetchPackageTree } from '@/services/planner'
import { usePlannerStore } from '@/store/plannerStore'
import type { Initiative, PaginatedResponse, PackageNode } from '@/types/planner'

const PlannerWorkspace = () => {
  const {
    selectedInitiativeId,
    setSelectedInitiativeId,
    selectedInitiative,
    setSelectedInitiative,
    selectedPackageId,
    setSelectedPackageId,
  } = usePlannerStore()
  const [initiativeFilters, setInitiativeFilters] = useState<InitiativeListFilters>({})
  const [initiativePage, setInitiativePage] = useState(1)

  const initiativesQuery = useQuery<PaginatedResponse<Initiative>>({
    queryKey: ['initiatives', initiativeFilters, initiativePage],
    queryFn: () =>
      fetchInitiatives({
        ...initiativeFilters,
        page: initiativePage,
        page_size: 6,
      }),
    placeholderData: keepPreviousData,
  })

  const initiativeDetailQuery = useQuery<Initiative>({
    enabled: !!selectedInitiativeId,
    queryKey: ['initiative-detail', selectedInitiativeId],
    queryFn: () => fetchInitiativeById(selectedInitiativeId!),
  })

  useEffect(() => {
    if (initiativeDetailQuery.data) {
      setSelectedInitiative(initiativeDetailQuery.data)
    }
  }, [initiativeDetailQuery.data, setSelectedInitiative])

  const packageTreeQuery = useQuery<PackageNode[]>({
    enabled: !!selectedInitiativeId,
    queryKey: ['package-tree', selectedInitiativeId],
    queryFn: () => fetchPackageTree(selectedInitiativeId!),
  })

  useEffect(() => {
    if (!selectedInitiativeId && initiativesQuery.data?.items?.length) {
      setSelectedInitiativeId(initiativesQuery.data.items[0].id)
    }
  }, [initiativesQuery.data, selectedInitiativeId, setSelectedInitiativeId])

  const handleInitiativeSelect = (initiative: Initiative) => {
    setSelectedInitiativeId(initiative.id)
    setSelectedInitiative(initiative)
    setSelectedPackageId(undefined)
  }

  return (
    <Space direction="vertical" size={24} style={{ width: '100%' }}>
      <Row gutter={24}>
        <Col xs={24} lg={10}>
          <InitiativeListCard
            data={initiativesQuery.data}
            loading={initiativesQuery.isLoading}
            selectedId={selectedInitiativeId}
            filters={initiativeFilters}
            page={initiativePage}
            onFiltersChange={(next) => {
              setInitiativeFilters(next)
              setInitiativePage(1)
            }}
            onPageChange={setInitiativePage}
            onSelect={handleInitiativeSelect}
          />
        </Col>
        <Col xs={24} lg={14}>
          <InitiativeDetailCard initiative={selectedInitiative} loading={initiativeDetailQuery.isLoading} />
        </Col>
      </Row>

      <Row gutter={24}>
        <Col xs={24} lg={10}>
          {selectedInitiativeId ? (
            <PackageTreePanel
              data={packageTreeQuery.data}
              loading={packageTreeQuery.isLoading}
              onSelectPackage={setSelectedPackageId}
            />
          ) : (
            <Empty description="请选择 initiative 以加载成本包" />
          )}
        </Col>
        <Col xs={24} lg={14}>
          <LineItemsTable initiativeId={selectedInitiativeId} packageId={selectedPackageId} />
        </Col>
      </Row>

      {!selectedInitiativeId && !initiativesQuery.isLoading && (
        <Result status="info" title="还没有 Initiative" subTitle="请先在后端创建或导入 initiative 数据。" />
      )}
      {initiativesQuery.isLoading && !initiativesQuery.data && (
        <Spin tip="加载中..." style={{ width: '100%' }} size="large" />
      )}
    </Space>
  )
}

export default PlannerWorkspace