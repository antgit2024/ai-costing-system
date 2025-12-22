## 工作集（允许读取的关键文件/目录）

> 目的：把“上下文”从聊天迁到可引用的工作集；新 Agent 只需读这些，不要全仓扫描。

> 最近校对（北京时间 GMT+8）：2025-12-21

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
- `frontend/src/services/planner.ts`（前端接口单一真相）
- `frontend/src/types/planner.ts`（前端类型单一真相）
- `frontend/src/App.tsx`（路由：/costing/sample-models & /costing/standard-models）

### 2) 后端：接口契约（只读校对用）

- `backend/src/planner/routers/product_models.py`
- `backend/src/planner/routers/product_model_versions.py`
- `backend/src/planner/routers/specs.py`（spec/parse：规格解析 tokens）
- `backend/src/planner/routers/bom.py`（bom/generate：动态 BOM 预演）
- `backend/src/planner/routers/line_variants.py`（version-scoped 行级变体 CRUD）
- `backend/src/planner/schemas.py`（如需核对字段名/response 结构）
- `backend/src/planner/services/bom_generation_service.py`（动态 BOM 生成：overlay 套用与 replace_bundle 语义）
- `backend/src/planner/services/line_variant_service.py`（行级变体：bundle 选择范围与 CRUD 细节）

### 3) 文档：口径与验收

- `DOC/costing/ui_specs/product_model.md`（产品模型 UI 规格/口径）
- `DOC/costing/manuals/standard_model_variants_ops_rules.md`（标准模型行级变体：运营/实施规范）
- `DOC/index/extracted/variants_discussion_extracted_20251221T200250+0800.md`（变体讨论提炼件：禁止直读导出全文）
- `DOC/agents/task_log.md`（最新变更/决策记录）

### 3.1) 业务输入（基础表单/场景说明，仅限本轮变体方案）

- `DOC/基础表单/BOM动态生成引擎业务需求说明.md`（标准模型变体/动态 BOM 业务逻辑与场景说明）

### 3.2) 方案产出（本轮交付物）

- `DOC/costing/blueprints/standard_model_variants_plan.md`（标准模型：变体/动态 BOM 功能方案）

### 3.3) 派单任务单（供执行 Agent 闭环）

- `DOC/agents/briefings/backend_line_variants_mvp.md`（后端闭环：行级变体 overlay + spec/parse tokens + bom/generate MVP）
- `DOC/agents/briefings/frontend_line_variants_panel_mvp.md`（前端闭环：物料行变体按钮 + overlay Drawer + 预演对接）
- `DOC/agents/briefings/frontend_line_variants_material_picker_mvp.md`（前端闭环：变体替换物料选择器，替代手输ID）
- `DOC/agents/briefings/ops_deploy_line_variants_to_4799.md`（运维闭环：部署行级变体到 47.99.89.206 + curl 验收）

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



