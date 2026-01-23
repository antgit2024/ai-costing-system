import { Navigate, Route, Routes } from 'react-router-dom'
import { Suspense, lazy } from 'react'
import { Spin } from 'antd'
import AppLayout from './components/layout/AppLayout'

const PlannerWorkspace = lazy(() => import('./pages/PlannerWorkspace'))
const ScenarioBuilderPage = lazy(() => import('./pages/ScenarioBuilderPage'))
const ScenarioListPage = lazy(() => import('./pages/ScenarioListPage'))
const MaterialMasterPage = lazy(() => import('./pages/costing/MaterialMasterPage'))
const SampleModelsPage = lazy(() => import('./pages/costing/SampleModelsPage'))
const StandardModelsPage = lazy(() => import('./pages/costing/StandardModelsPage'))
const VirtualMaterialsPage = lazy(() => import('./pages/costing/VirtualMaterialsPage'))
const ProcessModulesPage = lazy(() => import('./pages/costing/ProcessModulesPage'))
const ProcessesPage = lazy(() => import('./pages/costing/ProcessesPage'))
const PricingToolsPage = lazy(() => import('./pages/costing/PricingToolsPage'))
const ShipmentMonitorPage = lazy(() => import('./pages/costing/ShipmentMonitorPage'))
const ShippingRulesPage = lazy(() => import('./pages/costing/ShippingRulesPage'))
const SkuMasterWorkspacePage = lazy(() => import('./pages/costing/SkuMasterWorkspacePage'))
const SkuSpecMatchingPage = lazy(() => import('./pages/costing/SkuSpecMatchingPage'))
const TaxonomyManagementPage = lazy(() => import('./pages/costing/TaxonomyManagementPage'))
const StructureStandardsPage = lazy(() => import('./pages/costing/StructureStandardsPage'))
const ProductListingPage = lazy(() => import('./pages/costing/ProductListingPage'))
const BundleTemplatesPage = lazy(() => import('./pages/costing/BundleTemplatesPage'))
const ProductionScanPage = lazy(() => import('./pages/costing/ProductionScanPage'))
const TmallSkuTemplateGeneratorPage = lazy(() => import('./pages/costing/TmallSkuTemplateGeneratorPage'))
const SpecModulesPage = lazy(() => import('./pages/costing/SpecModulesPage'))

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
          <Route path="/costing/virtual-materials" element={<VirtualMaterialsPage />} />
          <Route path="/costing/sample-models" element={<SampleModelsPage />} />
          <Route path="/costing/standard-models" element={<StandardModelsPage />} />
          <Route path="/costing/process-modules" element={<ProcessModulesPage />} />
          <Route path="/costing/processes" element={<ProcessesPage />} />
          <Route path="/costing/taxonomy" element={<TaxonomyManagementPage />} />
          <Route path="/costing/structure-standards" element={<StructureStandardsPage />} />
          <Route path="/costing/pricing-tools" element={<PricingToolsPage />} />
          <Route path="/costing/shipments" element={<ShipmentMonitorPage />} />
          <Route path="/costing/shipping-rules" element={<ShippingRulesPage />} />
          <Route path="/costing/product-listing" element={<ProductListingPage />} />
          <Route path="/costing/bundle-templates" element={<BundleTemplatesPage />} />
          <Route path="/costing/tmall-sku-generator" element={<SpecModulesPage />} />
          <Route path="/costing/tmall-sku-generator/:templateId" element={<TmallSkuTemplateGeneratorPage />} />
          <Route path="/costing/sku-master" element={<SkuMasterWorkspacePage />} />
          <Route path="/costing/production-scan" element={<ProductionScanPage />} />
          <Route path="/costing/spec-matching" element={<SkuSpecMatchingPage />} />
          <Route path="*" element={<Navigate to="/planner" replace />} />
        </Routes>
      </Suspense>
    </AppLayout>
  )
}

export default App
