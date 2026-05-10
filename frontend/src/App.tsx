import { Navigate, Route, Routes } from 'react-router-dom'
import { Suspense, lazy } from 'react'
import { Spin } from 'antd'
import AppLayout from './components/layout/AppLayout'
import AuthGuard from './components/AuthGuard'
import LoginPage from './pages/LoginPage'

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
const ShipmentLedgerPage = lazy(() => import('./pages/costing/ShipmentLedgerPage'))
const ShippingRulesPage = lazy(() => import('./pages/costing/ShippingRulesPage'))
const SkuMasterWorkspacePage = lazy(() => import('./pages/costing/SkuMasterWorkspacePage'))
const SkuSpecMatchingPage = lazy(() => import('./pages/costing/SkuSpecMatchingPage'))
const ProductInfoPage = lazy(() => import('./pages/costing/ProductInfoPage'))
const TaxonomyManagementPage = lazy(() => import('./pages/costing/TaxonomyManagementPage'))
const StructureStandardsPage = lazy(() => import('./pages/costing/StructureStandardsPage'))
const ProductListingPage = lazy(() => import('./pages/costing/ProductListingPage'))
const BundleTemplatesPage = lazy(() => import('./pages/costing/BundleTemplatesPage'))
const ProductionScanPage = lazy(() => import('./pages/costing/ProductionScanPage'))
const TmallSkuTemplateGeneratorPage = lazy(() => import('./pages/costing/TmallSkuTemplateGeneratorPage'))
const SpecModulesPage = lazy(() => import('./pages/costing/SpecModulesPage'))
const AfterSalesInsightsPage = lazy(() => import('./pages/costing/AfterSalesInsightsPage'))
const ProfitInsightsPage = lazy(() => import('./pages/costing/ProfitInsightsPage'))
const ShopInsightsPage = lazy(() => import('./pages/costing/ShopInsightsPage'))
const SalesInsightsPage = lazy(() => import('./pages/costing/SalesInsightsPage'))
const IntegrationsHubPage = lazy(() => import('./pages/costing/IntegrationsHubPage'))
const ShipmentManagementPage = lazy(() => import('./pages/costing/biz/ShipmentManagementPage'))
const AfterSalesManagementPage = lazy(() => import('./pages/costing/biz/AfterSalesManagementPage'))
const LongTailCogsRatePage = lazy(() => import('./pages/costing/admin/LongTailCogsRatePage'))
const FinanceMasterDataPage = lazy(() => import('./pages/costing/admin/FinanceMasterDataPage'))
// 系统运维：通用绑定目标选择器（模型筛选器）演练页 —— 既用于内部验收，也作为运营快速校验
// 模型/套装层级、preset 与 token 拼装的工具页面。
const TargetPickerPlaygroundPage = lazy(() => import('./pages/dev/TargetPickerPlaygroundPage'))

const ProtectedShell = () => (
  <AuthGuard>
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
          <Route path="/costing/shipments" element={<ShipmentLedgerPage />} />
          <Route path="/costing/shipments/ops" element={<ShipmentMonitorPage />} />
          <Route path="/costing/shipping-rules" element={<ShippingRulesPage />} />
          <Route path="/costing/product-listing" element={<ProductListingPage />} />
          <Route path="/costing/bundle-templates" element={<BundleTemplatesPage />} />
          <Route path="/costing/tmall-sku-generator" element={<SpecModulesPage />} />
          <Route path="/costing/tmall-sku-generator/:templateId" element={<TmallSkuTemplateGeneratorPage />} />
          <Route path="/costing/products-info" element={<ProductInfoPage />} />
          <Route path="/costing/sku-master" element={<SkuMasterWorkspacePage />} />
          <Route path="/costing/production-scan" element={<ProductionScanPage />} />
          <Route path="/costing/spec-matching" element={<SkuSpecMatchingPage />} />
          <Route path="/costing/insights/after-sales" element={<AfterSalesInsightsPage />} />
          <Route path="/costing/insights/models" element={<ProfitInsightsPage />} />
          <Route path="/costing/insights/shops" element={<ShopInsightsPage />} />
          <Route path="/costing/insights/sales" element={<SalesInsightsPage />} />
          <Route path="/costing/integrations" element={<IntegrationsHubPage />} />
          <Route path="/costing/biz/shipments" element={<ShipmentManagementPage />} />
          <Route path="/costing/biz/after-sales" element={<AfterSalesManagementPage />} />
          <Route path="/costing/admin/long-tail-cogs-rate" element={<LongTailCogsRatePage />} />
          {/* v1.3 Cost Rate Hub — same page, default Tab=overhead_rate via query string. */}
          <Route
            path="/costing/admin/cost-rate-hub"
            element={<Navigate to="/costing/admin/long-tail-cogs-rate?tab=overhead_rate" replace />}
          />
          {/* C1 finance 主数据只读页(派单 costing_c1_client_service.md §2.7)·
              数据来自 finance-analyzer · 通过 /api/planner/finance/* 代理拉。 */}
          <Route path="/costing/admin/finance-master" element={<FinanceMasterDataPage />} />
          {/* 模型筛选器演练页：已正式纳入"系统运维"导航，旧路径 /dev/target-picker 保留兼容（避免外链失效）。 */}
          <Route path="/costing/system/target-picker-playground" element={<TargetPickerPlaygroundPage />} />
          <Route path="/dev/target-picker" element={<Navigate to="/costing/system/target-picker-playground" replace />} />
          <Route path="*" element={<Navigate to="/planner" replace />} />
        </Routes>
      </Suspense>
    </AppLayout>
  </AuthGuard>
)

const App = () => {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/*" element={<ProtectedShell />} />
    </Routes>
  )
}

export default App
