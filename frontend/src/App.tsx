import { Navigate, Route, Routes } from 'react-router-dom'
import { Suspense, lazy } from 'react'
import { Spin } from 'antd'
import AppLayout from './components/layout/AppLayout'

const PlannerWorkspace = lazy(() => import('./pages/PlannerWorkspace'))
const ScenarioBuilderPage = lazy(() => import('./pages/ScenarioBuilderPage'))
const ScenarioListPage = lazy(() => import('./pages/ScenarioListPage'))
const MaterialMasterPage = lazy(() => import('./pages/costing/MaterialMasterPage'))
const CostingModelsPage = lazy(() => import('./pages/costing/CostingModelsPage'))
const ProcessModulesPage = lazy(() => import('./pages/costing/ProcessModulesPage'))
const PricingToolsPage = lazy(() => import('./pages/costing/PricingToolsPage'))

const App = () => {
  return (
    <AppLayout>
      <Suspense
        fallback={
          <div style={{ padding: '48px 0', textAlign: 'center' }}>
            <Spin size="large" tip="加载中..." />
          </div>
        }
      >
        <Routes>
          <Route path="/" element={<Navigate to="/planner" replace />} />
          <Route path="/planner" element={<PlannerWorkspace />} />
          <Route path="/planner/scenario-builder" element={<ScenarioBuilderPage />} />
          <Route path="/planner/scenarios" element={<ScenarioListPage />} />
          <Route path="/costing" element={<Navigate to="/costing/materials" replace />} />
          <Route path="/costing/materials" element={<MaterialMasterPage />} />
          <Route path="/costing/models" element={<CostingModelsPage />} />
          <Route path="/costing/processes" element={<ProcessModulesPage />} />
          <Route path="/costing/pricing-tools" element={<PricingToolsPage />} />
          <Route path="*" element={<Navigate to="/planner" replace />} />
        </Routes>
      </Suspense>
    </AppLayout>
  )
}

export default App
