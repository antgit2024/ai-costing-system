## 工作集（允许读取的关键文件/目录）

> 目的：把“上下文”从聊天迁到可引用的工作集；新 Agent 只需读这些，不要全仓扫描。

> 最近校对（北京时间 GMT+8）：2026-02-10

### 1) 前端：产品模型（迁移编辑器的核心工作区）

- `frontend/src/components/costing/ProductModelEditorDrawer.tsx`（目标：承载完整编辑器逻辑）
- `frontend/src/components/costing/LineVariantDrawer.tsx`（行级变体 Overlay Drawer：对接 line-variants/spec/parse/bom）
- `DOC/index/extracted/ProductModelEditorDrawer_confirmed_20251221T042643Z.tsx`（已确认正确的快照备份）
- `frontend/src/guides/`（编辑器内嵌的统一 Markdown 指南：通过 `?raw` 导入）
- `frontend/src/guides/derive_standard_per_sqm_tablecloth_example.md`（推导标准版本：按㎡口径示例）
- `frontend/src/components/common/GuideDrawer.tsx`（统一 Markdown 指南展示组件）
- `frontend/src/pages/costing/CostingModelsPage.tsx`（旧编辑器来源：迁移参考）
- `frontend/src/pages/costing/SampleModelsPage.tsx`（打样模型入口：entryContext="sample"）
- `frontend/src/pages/costing/StandardModelsPage.tsx`（标准模型入口：entryContext="standard" + initialVersionId）
- `frontend/src/pages/costing/ShipmentMonitorPage.tsx`（发货批次/异常队列/BOM快照只读页：/costing/shipments）
- `frontend/src/pages/costing/AfterSalesInsightsPage.tsx`（数据洞察：售后分析（退货率）页：/costing/insights/after-sales；仅按用户选择范围查询，不做全量重算）
- `frontend/src/pages/costing/ProfitInsightsPage.tsx`（数据洞察：模型分析（利润）页：/costing/insights/models；货品/模型两Tab；仅按用户选择范围查询）
- `frontend/src/pages/costing/ShopInsightsPage.tsx`（数据洞察：店铺数据（按渠道汇总）页：/costing/insights/shops；利润/退货率两Tab；支持覆盖率筛选）
- `frontend/src/pages/costing/ProductListingPage.tsx`（产品上架（测试台）：交易规格解析/变体命中/最终BOM预演）
- `frontend/src/pages/costing/SkuMasterWorkspacePage.tsx`（SKU 主档工作台：/costing/sku-master）
- `frontend/src/pages/costing/BundleTemplatesPage.tsx`（套装模板：短语 presets/组件行编辑器工作台，本轮改造抽屉为左右两栏）
- `frontend/src/pages/costing/MaterialMasterPage.tsx`（真实物料主档：列表+详情抽屉；本轮接入“引用关系”区块）
- `frontend/src/services/planner.ts`（前端接口单一真相）
- `frontend/src/types/planner.ts`（前端类型单一真相）
- `frontend/src/App.tsx`（路由：/costing/sample-models & /costing/standard-models）
- `frontend/src/pages/costing/ProcessModulesPage.tsx`（工艺模块主页面：AI生成/模块描述/工序选择与回填）
- `frontend/src/components/costing/ProcessModuleAIDrawer.tsx`（工艺模块AI语义抽屉：从工序汇总 + 手工锁定）
- `frontend/src/pages/costing/ProcessesPage.tsx`（工序管理：两行列表风格参考实现）
- `frontend/src/pages/costing/VirtualMaterialsPage.tsx`（虚拟物料：列表/抽屉/绑定/盘点折算；本轮改动集中在此）
- `frontend/src/components/costing/MaterialSelectModal.tsx`（物料选择器：用于“添加物料/替换物料”等弹窗复用）
- `frontend/src/components/costing/MaterialPickerDrawer.tsx`（统一物料选择器：真实/虚拟双Tab + 筛选区 + 列表）
- `frontend/src/components/costing/ProcessSelectModal.tsx`（工序选择器：用于“添加工序/引用工序”等弹窗复用）
- `frontend/src/guides/table_list_style_two_line_cells.md`（两行列表风格规范：可复用）
- `frontend/src/components/layout/AppLayout.tsx`（全局布局：任务角标轮询与性能）
- `frontend/scripts/deploy_static.sh`（静态资源发布脚本：需要原子发布避免 chunk 404→HTML 回退）
- `DOC/agents/known_issues.md`（已知问题：MIME=text/html 导致模块加载失败）

### 2) 后端：接口契约（只读校对用）

- `backend/src/config.py`（数据库连接配置：补齐 Postgres SSL/sslmode=require）
- `backend/src/database.py`（SQLAlchemy engine 初始化：修复 no encryption 导致的全站 500）
- `backend/src/planner/models.py`（数据模型：确认 process_module 字段/状态）
- `backend/src/planner/router.py`（总路由聚合：定位 task-center/recent 的真实挂载位置）
- `backend/src/planner/routers/process_modules.py`（工艺模块路由：列表/详情/创建/更新/启用停用/复制/删除）
- `backend/src/planner/routers/processes.py`（工序路由：/processes 与 /processes/references）
- `backend/src/planner/routers/jobs.py`（任务/作业相关路由：排查 task-center/recent 500）
- `backend/src/planner/services/process_module_service.py`（工艺模块服务：删除/归档口径）
- `backend/src/planner/routers/product_models.py`
- `backend/src/planner/routers/product_model_versions.py`
- `backend/src/planner/services/model_version_image_storage.py`（版本图片存储：上传/读取/删除的底层封装）
- `backend/src/planner/routers/specs.py`（spec/parse：规格解析 tokens）
- `backend/src/planner/routers/bom.py`（bom/generate：动态 BOM 预演）
- `backend/src/planner/routers/line_variants.py`（version-scoped 行级变体 CRUD）
- `backend/src/planner/routers/shipments.py`（发货导入/批次/异常队列/BOM快照：/api/planner/shipments/*）
- `backend/src/planner/routers/base_config.py`（基础配置：真实物料/虚拟物料/分类等；本轮新增虚拟物料筛选参数）
- `backend/src/planner/routers/taxonomy.py`（分类管理：taxonomy items/mappings）
- `backend/src/planner/schemas.py`（如需核对字段名/response 结构）
- `backend/src/planner/services/bom_generation_service.py`（动态 BOM 生成：overlay 套用与 replace_bundle 语义）
- `backend/src/planner/services/line_variant_service.py`（行级变体：bundle 选择范围与 CRUD 细节）
- `backend/src/planner/services/product_model_service.py`（推导标准版本 derive_standard_version：排查“打样版本推导后标准列表出现多个版本/误推导”的根因与最小修复）
- `backend/tests/planner/test_clone_model_from_standard_version.py`（克隆新标准模型：从标准版本克隆新模型+新版本+复制清单/变体的最小验收用例）
- `backend/tests/planner/conftest.py`（测试基座：SQLite 建表/Session fixture；新增表后需确保模型被 import 注册）
- `backend/tests/planner/test_after_sales_import_mvp.py`（售后导入 + 退货率分析：最小验收单测）
- `backend/tests/planner/test_profit_analytics_mvp.py`（利润分析：最小验收单测）
- `backend/tests/planner/test_shop_analytics_mvp.py`（店铺数据：按渠道汇总利润/退货率 + 覆盖率：最小验收单测）

### 3) 文档：口径与验收

- `DOC/costing/ui_specs/product_model.md`（产品模型 UI 规格/口径）
- `DOC/costing/manuals/standard_model_variants_ops_rules.md`（标准模型行级变体：运营/实施规范）
- `DOC/costing/manuals/rules_training_handbook_v1.md`（规则与培训手册：新人必读入口）
- `DOC/costing/reviews/shipment_time_parse_review_phase0_phase1_20251222.md`（方案评审稿：发货时再解析 + SKU→已发布标准版本绑定，含 Phase0/Phase1 优先级）
- `DOC/costing/reviews/erp_guardrails_addendum_20251222.md`（ERP口径补强清单：版本为最小核算单元、重跑语义、编码定位、解析版本化、异常工作台、成本口径）
- `DOC/costing/blueprints/structure_standards/pillow_structure_standard_v1.md`（结构标准口径：抱枕/靠垫 slots 去歧义 + 驱动量建议）
- `DOC/costing/blueprints/structure_standards/tablecloth_structure_standard_v1.md`（结构标准口径：桌布/桌旗/桌垫同构 slots + 驱动量建议）
- `DOC/index/extracted/variants_discussion_extracted_20251221T200250+0800.md`（变体讨论提炼件：禁止直读导出全文）
- `DOC/index/extracted/shipment_xlsx_extracted_20260125T000000+0800.md`（发货单：强关联键（原始单号/商品链接ID/货品条码）提炼）
- `DOC/index/extracted/after_sales_xlsx_extracted_20260125T000000+0800.md`（售后退货单：强关联键（网店订单号/商品链接Id/货品条码/申请时间）提炼）
- `DOC/agents/task_log.md`（最新变更/决策记录：包括 2026-02-10 对《BOM系统优化完整方案_最终版》v2.0 的评审结论）

### 6) 环境文件治理（安全/可恢复）

- `.gitignore`（环境文件是否应被追踪/忽略的唯一入口）
- `.env.sample`（根目录环境变量模板）
- `frontend/env.production.example`（前端生产环境变量模板）
- `frontend/.env.production`（前端生产环境变量：通常不应进 Git，仅本机/服务器保留）
- `.env`（根目录真实环境变量：通常不应进 Git，仅本机/服务器保留）

### 3.1) 业务输入（基础表单/场景说明，仅限本轮变体方案）

- `DOC/基础表单/BOM动态生成引擎业务需求说明.md`（标准模型变体/动态 BOM 业务逻辑与场景说明）
- `DOC/基础表单/SKU绑定与BOM生成业务逻辑说明文档.md`（SKU 绑定/规格解析/BOM 生成主链路业务说明）
- `DOC/基础表单/BOM系统优化完整方案_最终版.md`（30%复杂产品：编码/模型套模型/自动编码 + 可运营流程；与“发货时再解析”主链互补）
- `DOC/基础表单/发货单-理.xlsx`（发货单样例：对账字段/扣库清单落地参考）

### 3.2) 方案产出（本轮交付物）

- `DOC/costing/blueprints/standard_model_variants_plan.md`（标准模型：变体/动态 BOM 功能方案）
 - `DOC/costing/blueprints/sku_binding_bom_shipment_plan.md`（SKU 绑定→BOM 快照→发货/扣库对账：ERP 方案与计划）
- `DOC/costing/blueprints/profit_and_returns_analytics_plan_2025_2026_v0_1.md`（数据分析：利润/退货（2025 仅分析校准 Run / 2026 扣库落库）方案）
- `DOC/costing/blueprints/erp_writeback_process_spec_mvp.md`（ERP 回传MVP：把可生产的工艺/规格回写到 ERP）
- `DOC/costing/blueprints/jky_api_requirements_form_v1.md`（对外谈判用：吉客云/ERP 对接 API 需求表单 v1）
- `DOC/costing/blueprints/jky_after_sales_returns_requirements_form_v1.md`（对外谈判用：售后/退货（冲销）对接需求表单 v1）

### 3.3) 派单任务单（供执行 Agent 闭环）

- `DOC/agents/briefings/backend_line_variants_mvp.md`（后端闭环：行级变体 overlay + spec/parse tokens + bom/generate MVP）
- `DOC/agents/briefings/backend_sku_binding_inventory_mvp.md`（后端闭环：SKU绑定 + spec解析 + 生成库存扣料清单（BOM快照））
- `DOC/agents/briefings/backend_shipment_import_bom_snapshots_mvp.md`（后端闭环：发货单导入→spec_hash缓存解析→BOM快照+异常队列）
- `DOC/agents/briefings/backend_sku_master_import_and_autobind_mvp.md`（后端闭环：SKU主档导入（ERP平台商品列表）+ 发货导入自动回写主档）
- `DOC/agents/briefings/frontend_line_variants_panel_mvp.md`（前端闭环：物料行变体按钮 + overlay Drawer + 预演对接）
- `DOC/agents/briefings/frontend_line_variants_material_picker_mvp.md`（前端闭环：变体替换物料选择器，替代手输ID）
- `DOC/agents/briefings/frontend_sku_master_workspace_mvp.md`（前端闭环：SKU主档工作台（导入/查询/命中率））
- `DOC/agents/briefings/frontend_shipments_retry_exceptions_and_bind_cta_mvp.md`（前端闭环：发货监控页“重试异常”按钮 + SKU_NOT_BOUND 去绑定 CTA）
- `DOC/agents/briefings/frontend_standard_version_structure_code_and_module_filter_mvp.md`（前端闭环：标准模型版本选择结构标准 + 按结构过滤模块候选（MVP））
- `DOC/agents/briefings/frontend_structure_standards_management_mvp.md`（前端闭环：结构标准管理（字典页）MVP）
- `DOC/agents/briefings/frontend_process_modules_applicability_mode_and_auto_tags_mvp.md`（前端闭环：工艺模块适用类型（内用/组合/global）+ 结构标签自动生成（MVP））
- `DOC/agents/briefings/frontend_structure_selection_dropdowns_guardrails_mvp.md`（前端闭环：结构标准/slot 下拉收口（防呆）MVP）
- `DOC/agents/briefings/frontend_structure_slots_bilingual_display_mvp.md`（前端闭环：结构 slot “拼音短码+中文名”双语展示（MVP））
- `DOC/agents/briefings/ops_deploy_line_variants_to_4799.md`（运维闭环：部署行级变体到 47.99.89.206 + curl 验收）
- `DOC/agents/briefings/ops_deploy_shipment_import_bom_snapshots_to_4799.md`（运维闭环：部署发货单导入→BOM快照到 47.99.89.206 + curl/pytest 验收）
- `DOC/agents/briefings/ops_deploy_frontend_shipments_upload_to_4799.md`（运维闭环：部署前端发货单上传入口到 47.99.89.206）
- `DOC/agents/briefings/ops_deploy_retry_exceptions_to_4799.md`（运维闭环：部署“异常队列重试（Retry Exceptions）”到 47.99.89.206）
- `DOC/agents/briefings/backend_retry_shipment_exceptions_mvp.md`（后端闭环：按批次重试未解决异常（Retry Exceptions）MVP）
- `DOC/agents/briefings/backend_structure_tagging_and_filtering_mvp.md`（后端闭环：模型结构化落点（结构标准/工艺模块标签）+ 列表筛选 MVP）
- `DOC/agents/briefings/integration_shop_connector_onboarding_mvp.md`（Integration Agent：店铺对接入职简报（以 SKU 主档/发货导入为中心））
- `DOC/agents/briefings/pod_personalization_phase0_briefing.md`（POD 个性化定制 Phase0 派单简报：先印布→印刷稿→生产包→回传 ERP）
- `DOC/agents/briefings/backend_pod_personalization_phase0_mvp.md`（POD Phase0：后端闭环任务单（MVP，备用；当前不执行））

### 3.4) POD/个性化定制（方案蓝图）

- `DOC/costing/blueprints/pod_personalization_print_pipeline_phase0.md`（先印布：效果图→确稿→印刷稿→工厂下载→回传 ERP，含小程序接入前提）

### 4) 质量门槛（可运行/可验收）

- `frontend/package.json`（build/test 脚本）
- `frontend/tsconfig.app.json`（@/* alias 配置）
- `frontend/vite.config.ts`（alias 配置）

### 5) Agent 接力/恢复包（必须维护）

- `DOC/agents/handoff_planner.md`（Planner 新 Agent 接力包：关键结论/唯一真相/快照/恢复清单）
- `DOC/agents/task_distribution_standard.md`（跨项目复用：Hub派单体系标准说明/模板/必备文件）
- `DOC/agents/handoff_frontend.md`（Frontend 新 Agent 接力包：P0 目标/接口索引/验收命令）
- `DOC/agents/handoff_backend.md`（Backend 新 Agent 接力包：接口契约/验收命令）
- `DOC/agents/handoff_docs.md`（Docs 新 Agent 接力包：口径/产出格式/风险点）
- `DOC/agents/handoff_pod.md`（POD/印刷自动化 Agent 接力包：单裁片PDF→RIP自动拼版→打印/切割→回传ERP）
- `DOC/agents/state.md`（当前状态：阶段、时间口径、提炼件索引、下一步）
- `DOC/agents/commands.md`（唯一可执行的验收/启动/排错命令清单）
- `DOC/agents/known_issues.md`（已知问题与规避手册）
- `DOC/agents/agent_rules.md`（仓库级工作规则/约束）
- `DOC/agents/task_log.md`（变更记录与决策依据）
- `DOC/index/extracted/`（大文件/日志提炼件目录：禁止直读导出日志，必须先提炼）

### 7) PnL / Cost Rate Hub 任务工作集（2026-05-09 新增；后续 PnL/Hub 任何 Agent 接力前必读）

> **背景**：2026-05-09 接到"专业版盈亏分析模块 + Cost Rate Hub"任务的 Agent 第一轮设计走偏（绕开了 `DOC/agents/state.md` 真相文档与现有 5 个雏形子系统直接重复造轮子），本 §7 把 PnL/Hub 任务的"必读最小集 + 必须看的现有能力 + 必须读的 5 份产出文档"显式列出。任何后续 PnL/Hub Agent 接力前**必须先读 §7**。
>
> **必读规则**：先读本 §7 → 再读 `system_capability_inventory.md` → 才能动 PnL/Hub 文档。

#### 7.1 项目真相文档（PnL/Hub Agent 接力第 1 件事）

- `DOC/agents/agent_rules.md`（**强制读 — 2026-05-09 18:00 重大修订**：只读工作集、大文件不直读、**任务粒度区分（设计 vs 执行）**、**交接成本 ≤ 编码成本**硬约束、北京时间口径）
- `DOC/agents/task_distribution_standard.md`（**强制读 — 2026-05-09 18:00 重大修订**：Hub Agent 角色边界、**执行 Agent 完整自主权（§0.2）**、**优先大任务派单（§3）**、微任务直派（§3.3）、何时必须回 Hub 仅 3 种情况（§0.3））
- `DOC/agents/state.md`（**3317 行真相文档** — 禁止全读；按关键词 grep 检索后只读 ±50 行段落）
- `DOC/agents/task_log.md`（变更日志，看最近 30 行了解最近发生了什么）
- `DOC/agents/known_issues.md`（**特别看 §0.0a~§33** — 含 5 个雏形子系统的完整设计 / API / 表结构）

#### 7.2 PnL/Hub 任务"系统能力清单"（必读总入口）

- `DOC/costing/handovers/system_capability_inventory.md`（**第 1 份必读** — 现有页面/路由/表/API/雏形子系统/已落地能力 vs 真正缺什么 / 23% 真相 / 复用边界）

#### 7.3 PnL 任务历史产出文档（已写但需要校准）

> **状态**：2026-05-09 第一轮产出，因未读 §7.1/§7.2 导致部分内容重复造轮子或与现状不符，需基于清单回头校准。

- `DOC/costing/blueprints/pnl_analytics_module_design.md`（v1.1，待校准为 v1.2）
- `DOC/costing/blueprints/cost_rate_hub_design_v1.md`（v1.2，待校准为 v1.3 — 复用 LongTailCogsRateStrategy 雏形 + 23% 真相还原）
- `DOC/costing/blueprints/finance_analyzer_integration_v1.md`（v1.1）
- `DOC/costing/blueprints/sku_portfolio_management_v1.md`（v1.1）
- `DOC/costing/manuals/transfer_pricing_handbook.md`
- `DOC/costing/manuals/guides/price_calculation_guide.md`（v2.1）
- `DOC/costing/handovers/pnl_module_handover.md`（v1.2 接力总入口）
- `DOC/costing/handovers/pnl_decision_log.md`（v1.2 决策日志，#1~#47）
- `DOC/costing/handovers/pnl_phase_status.md`（v1.2 进度看板）
- `DOC/costing/handovers/phase0_review_checklist.md`（v1.2 评审清单）
- `DOC/costing/handovers/pnl_external_reviews/INDEX.md`（v1.2 外部评审 5 份归档）
- `DOC/costing/handovers/pnl_incident_log.md`

#### 7.4 已存在的盈亏蓝图（PnL 任务的"原配" — 第一轮被忽略）

- `DOC/costing/blueprints/profit_and_returns_analytics_plan_2025_2026_v0_1.md`（**v0.1 原配蓝图** — 4 个 Insights 页面 + 3 个 profit API + shipment_costing_results 表都源于此 / 第一轮设计未读此文导致重复）

#### 7.5 项目架构总图

- `DOC/costing/architecture.md`（Phase 1-3.5 既有架构 — Initiative / Cost Package / Scenario / Approvals / Audit，PnL 模块需对齐这套架构而非另起炉灶）

#### 7.6 现有 5 个雏形子系统（必看代码定位）

| 雏形子系统 | 定位 | 后端代码 | 前端代码 | 文档 |
|---|---|---|---|---|
| **LongTailCogsRateStrategy**（雏形版 Cost Rate Hub） | 4 层优先级链 + history + resolve API | `backend/src/planner/services/long_tail_strategy_service.py` + `backend/src/planner/routers/long_tail_strategies.py` | `frontend/src/pages/costing/admin/LongTailCogsRatePage.tsx` | `known_issues.md` Issue 28 |
| **data_quality_service**（雏形版可信度治理） | nightly 自动跑 + mark_only + 三色徽章雏形 | `backend/src/planner/services/data_quality_service.py` | `frontend/src/pages/costing/SkuMasterWorkspacePage.tsx` 红 Tag | `known_issues.md` §0.0j |
| **SKU 治理 4 态**（unmanaged/auto_bound/pending_model/do_not_model） | 状态机 + 长尾兜底成本 | `backend/src/planner/services/sku_master_service.py::set_sku_governance` | `frontend/src/pages/costing/shipment-ops/components/GovernanceBacklogTab.tsx` | `known_issues.md` Issue 23 |
| **shipment_costing_results**（轻量成本结果落库） | 物料/工序/制造费三段成本 | `backend/migrations/versions/0027_shipment_costing_results_no_snapshot.py` | `ShipmentLedgerPage` 抽屉"成本拆分" Tab | `profit_and_returns_analytics_plan_v0_1.md` §3.4 |
| **4 个 Insights 看板** | 模型/店铺/销售/售后利润 | `backend/src/planner/routers/analytics.py` | `frontend/src/pages/costing/{Profit,Shop,Sales,AfterSales}InsightsPage.tsx` | `state.md:13-19` 已落地清单 |

#### 7.7 关键事实（PnL/Hub Agent 必须先承认）

| 事实 | 出处 | 影响 |
|---|---|---|
| **23% 是数学折算（30%/(1+30%)=23.08%）**，后端实际仍是 30% 写死 | `state.md:1823-1843` + `task_log.md:15` Guides Agent 2026-01-13 落地 | 不要写"23% 反推" / "把 30% 换成真实 23%" 等错误叙述 |
| **3 法人物理一体在一栋楼，是 1 个生产体系** | 用户 2026-05-09 当面校准 | Hub 不分 factory，4 概念正交（production_unit/purchase_entity/cost_center/legal_entity） |
| **班组主数据在 `taxonomy` 表 `domain='team'`**，含 `default_minute_rate` | `frontend/src/pages/costing/TaxonomyManagementPage.tsx:32` + `processes.py:72` 注释 | 不要在 `processes` 表加 `cost_center_id` — 班组归属在 `taxonomy.team` |
| **`processes` 表故意不承载班组**（line 72 注释明确） | `frontend/src/pages/costing/ProcessesPage.tsx:72` | 班组工时在 `ModelVersionProcess` / `ProcessModuleStep` 维护 |
| **现有架构有完整的 Hub Agent 派单体系** | `task_distribution_standard.md` 全文 | PnL/Hub Agent 应做 Hub 不直接写代码；派 Backend/Frontend Agent 闭环 |

#### 7.8 PnL/Hub 任务的工作集白名单（先扩展再读，禁止越界）

读取范围：
- 整个 §7.1 ~ §7.7 列出的所有文件
- `backend/src/planner/models.py`（数据模型，按需 grep）
- `backend/src/planner/services/bom_generation_service.py`（成本计算核心）
- `backend/src/planner/services/analytics_service.py`（分析服务）
- `backend/src/planner/services/shipment_import_service.py`（发货导入）
- `frontend/src/components/costing/ProductModelEditorDrawer.tsx`（KB8 抽屉清单编辑）

修改范围：
- 仅限 `DOC/costing/handovers/pnl_*.md` + `DOC/costing/blueprints/cost_rate_hub_design_v1.md` + `DOC/costing/blueprints/pnl_analytics_module_design.md`
- 涉及 `DOC/agents/*` 必须谨慎追加而非覆盖

禁止范围：
- 不动 `frontend/src/` 下任何代码（PnL Agent 是 Hub 角色，写代码要派 Frontend/Backend Agent）
- 不动 `backend/src/` 下任何代码（同上）
- 不动 `DOC/agents/state.md` 主体内容（只能在末尾追加"最近校对"段，且必须用户授权）
- 不动 `DOC/costing/blueprints/profit_and_returns_analytics_plan_2025_2026_v0_1.md`（v0.1 是项目原配蓝图，不能覆盖）

#### 7.9 PnL/Hub 任务的验收命令模板（2026-05-09 18:00 修订 — 不再强制 1 条）

> **修订背景**：旧规则"每轮闭环必须有 1 条 0 退出码命令"在方案设计阶段容易变成形式主义勾选。本次修订为：执行 Agent 自主选最能证明任务完成的 1~3 条，不强求 0 退出码（如有 known issue 可接受 warning）。

执行 Agent 在任务交付时自主选择验收方式：

**候选 1 — 文档型任务**
- 产出新文档：`test -f <path> && grep -nF "<标志性段落>" <path>`
- 改既有文档：`grep -nF "<新加段落>" <path>`

**候选 2 — 代码型任务**
- 前端：`npm -C frontend run build`
- 后端：`python -m pytest backend/tests/planner/test_<相关>*.py -q`
- 端到端：`curl <relevant API>` 或浏览器走通用户场景

**候选 3 — 跨域一致性任务**（如 Hub 升级联动多文档）
- 多条 grep 一起跑，证明所有相关文档都同步了
- 例：`grep -nF "v1.3" DOC/costing/blueprints/cost_rate_hub_design_v1.md && grep -nF "v1.3" DOC/costing/handovers/system_capability_inventory.md`

**反模式（避免）**
- ❌ 为了打卡而跑无意义命令（如 `ls` 文件存不存在）
- ❌ 强求 0 退出码导致掩盖真实 known issue
- ❌ 用大量 grep 命令模拟"全面验收"实际只是堆 Token

#### 7.10 PnL 模块 6 份核心必读文档（**按受众分类**，关联到运维体系，2026-05-09 17:55 新增）

> **背景**：用户 2026-05-09 17:40 明确指出"这最开始的文件需要优化吗？你有没有关联到运维里"。本节把 PnL 模块 6 份核心文档（**全员必读**）按受众分类列出，明确每份的角色与读取顺序。任何 PnL Agent / Backend Agent / Frontend Agent / Rules Agent / Docs Agent 接力前必须先看本表。
>
> **维护契约**：本表的"当前版本号"列必须在每次校准动作完成后**当轮立刻更新**（与 `system_capability_inventory.md` §12.1 表保持一致）。

| # | 文档 | 行数（v1.2 后）| 当前版本 | 路径 | 受众 | 接力顺序 |
|---|---|---|---|---|---|---|
| 0 | **系统能力清单**（含 §12 文档优先级 + §13 防忘追踪） | 580 | **v1.0+§13** | `DOC/costing/handovers/system_capability_inventory.md` | **全员强制首读** | 第 1 |
| 1 | **总图（必读）** | 770 | **v1.2**（2026-05-09 17:55 同步 Hub v1.3）| `DOC/costing/blueprints/pnl_analytics_module_design.md` | **全员强制次读** | 第 2 |
| 2 | **Cost Rate Hub 设计** | 669 | **v1.3**（2026-05-09 17:50）| `DOC/costing/blueprints/cost_rate_hub_design_v1.md` | 全员强制三读 | 第 3 |
| 3 | 价格计算指南 v2 | 421 | v2.1 | `DOC/costing/manuals/guides/price_calculation_guide.md` | 财务 + 工厂 | 按需 |
| 4 | 内部转移价手册 | 369 | （无明文版本号）| `DOC/costing/manuals/transfer_pricing_handbook.md` | 财务 + 老板 | 按需 |
| 5 | SKU 组合管理蓝图 | 660 | v1.1（待 v1.2 校准 — 见 inventory §13.1 U1）| `DOC/costing/blueprints/sku_portfolio_management_v1.md` | 运营 + 老板 | 按需（Phase 2 启动时强制读）|
| 6 | finance 集成方案 | 424 | v1.1（待 v1.2 校准 — 见 inventory §13.1 U2）| `DOC/costing/blueprints/finance_analyzer_integration_v1.md` | 技术 + finance 团队 | 按需（W4 finance 录入启动时强制读）|
| 7 | 评审清单（打勾表） | 311 | v1.2.1（待 v1.3 校准 — 见 inventory §13.1 U4）| `DOC/costing/handovers/phase0_review_checklist.md` | 全员（评审会）| 评审会前 1 周强制读 |

**强制读关系**：
```
新接力 PnL Agent → 必读 #0 + #1 + #2（前 3 份是 P0/P1/P2/P3 真相文档）
新接力 Backend Agent → 必读 #0 + #1 + #2 + #6（finance 相关任务时）
新接力 Frontend Agent → 必读 #0 + #1 + #2（看 §3 数据模型 + §4 接口契约）
新接力 Rules/Guides Agent → 必读 #0 + #3（指南规范）
评审会前 → 全员强制读 #7
Phase 2 启动前 → 全员强制读 #5
```

**这 6 份核心文档与本 §7 工作集的关系**：
- §7.1 项目真相文档（5 份 Agent 体系）= **元规则**
- §7.10 6 份核心文档 = **业务真相**
- §7.2~§7.9 = **任务工作集 + 复用边界 + 验收模板**

三者缺一不可。任何 PnL Agent 接力，应该按"§7.1 → §7.10 → §7.2~§7.9"顺序读。



