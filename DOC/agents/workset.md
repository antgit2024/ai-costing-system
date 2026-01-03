## 工作集（允许读取的关键文件/目录）

> 目的：把“上下文”从聊天迁到可引用的工作集；新 Agent 只需读这些，不要全仓扫描。

> 最近校对（北京时间 GMT+8）：2025-12-27

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
- `frontend/src/pages/costing/SkuMasterWorkspacePage.tsx`（SKU 主档工作台：/costing/sku-master）
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
- `backend/src/planner/routers/specs.py`（spec/parse：规格解析 tokens）
- `backend/src/planner/routers/bom.py`（bom/generate：动态 BOM 预演）
- `backend/src/planner/routers/line_variants.py`（version-scoped 行级变体 CRUD）
- `backend/src/planner/routers/shipments.py`（发货导入/批次/异常队列/BOM快照：/api/planner/shipments/*）
- `backend/src/planner/routers/base_config.py`（基础配置：真实物料/虚拟物料/分类等；本轮新增虚拟物料筛选参数）
- `backend/src/planner/routers/taxonomy.py`（分类管理：taxonomy items/mappings）
- `backend/src/planner/schemas.py`（如需核对字段名/response 结构）
- `backend/src/planner/services/bom_generation_service.py`（动态 BOM 生成：overlay 套用与 replace_bundle 语义）
- `backend/src/planner/services/line_variant_service.py`（行级变体：bundle 选择范围与 CRUD 细节）
- `backend/tests/planner/test_clone_model_from_standard_version.py`（克隆新标准模型：从标准版本克隆新模型+新版本+复制清单/变体的最小验收用例）

### 3) 文档：口径与验收

- `DOC/costing/ui_specs/product_model.md`（产品模型 UI 规格/口径）
- `DOC/costing/manuals/standard_model_variants_ops_rules.md`（标准模型行级变体：运营/实施规范）
- `DOC/costing/reviews/shipment_time_parse_review_phase0_phase1_20251222.md`（方案评审稿：发货时再解析 + SKU→已发布标准版本绑定，含 Phase0/Phase1 优先级）
- `DOC/costing/reviews/erp_guardrails_addendum_20251222.md`（ERP口径补强清单：版本为最小核算单元、重跑语义、编码定位、解析版本化、异常工作台、成本口径）
- `DOC/index/extracted/variants_discussion_extracted_20251221T200250+0800.md`（变体讨论提炼件：禁止直读导出全文）
- `DOC/agents/task_log.md`（最新变更/决策记录）

### 6) 环境文件治理（安全/可恢复）

- `.gitignore`（环境文件是否应被追踪/忽略的唯一入口）
- `.env.sample`（根目录环境变量模板）
- `frontend/env.production.example`（前端生产环境变量模板）
- `frontend/.env.production`（前端生产环境变量：通常不应进 Git，仅本机/服务器保留）
- `.env`（根目录真实环境变量：通常不应进 Git，仅本机/服务器保留）

### 3.1) 业务输入（基础表单/场景说明，仅限本轮变体方案）

- `DOC/基础表单/BOM动态生成引擎业务需求说明.md`（标准模型变体/动态 BOM 业务逻辑与场景说明）
- `DOC/基础表单/SKU绑定与BOM生成业务逻辑说明文档.md`（SKU 绑定/规格解析/BOM 生成主链路业务说明）
- `DOC/基础表单/发货单-理.xlsx`（发货单样例：对账字段/扣库清单落地参考）

### 3.2) 方案产出（本轮交付物）

- `DOC/costing/blueprints/standard_model_variants_plan.md`（标准模型：变体/动态 BOM 功能方案）
 - `DOC/costing/blueprints/sku_binding_bom_shipment_plan.md`（SKU 绑定→BOM 快照→发货/扣库对账：ERP 方案与计划）
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
- `DOC/agents/state.md`（当前状态：阶段、时间口径、提炼件索引、下一步）
- `DOC/agents/commands.md`（唯一可执行的验收/启动/排错命令清单）
- `DOC/agents/known_issues.md`（已知问题与规避手册）
- `DOC/agents/agent_rules.md`（仓库级工作规则/约束）
- `DOC/agents/task_log.md`（变更记录与决策依据）
- `DOC/index/extracted/`（大文件/日志提炼件目录：禁止直读导出日志，必须先提炼）



