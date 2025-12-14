# Costing Planner Requirements & Delivery Plan

> Status: draft v0.1 (2025-12-13). This file captures the initial scope, data
> design, and implementation milestones for the `feature/costing-planner`
> initiative. Update after every major decision or scope change.

## 1. Business Context & Objectives

- `AI Costing System` currently lacks an upstream planning workspace. Finance,
  procurement, and product ops teams need a structured way to capture demand,
  model cost scenarios, and hand off approved baselines to execution services.
- The planner module should enable:
  1. **Centralized initiatives** – aggregate all cost items for a launch/event.
  2. **Modular cost packages** – break initiatives into workstreams (materials,
     labor, logistics, tooling).
  3. **Scenario modeling** – versioned assumptions, supplier quotes, exchange
     rates, and markup strategies.
  4. **Workflow visibility** – status tracking, review history, AI suggestions,
     and integration-ready outputs.

Success metrics (MVP):
- All initiatives captured inside the planner with clear ownership.
- Versioned cost scenarios (min. 2 per initiative) stored and retrievable.
- <5 min to export an approved baseline to downstream costing execution.

## 2. Personas & Typical Flows

| Persona | Goals | Key Actions |
| --- | --- | --- |
| Costing PM | Build initiative structure, coordinate inputs, finalize baseline | Create initiatives, define milestones, lock scenarios |
| Cost Analyst | Provide detailed line items & assumptions | Import BOM, attach quotes, adjust parameters |
| Procurement Lead | Manage supplier quotes & negotiations | Upload quote revisions, approve vendor selection |
| Exec Reviewer | Approve baseline & track savings | Review dashboards, comment, approve |

High-level workflow:
1. **Initiation** – PM creates initiative, defines timeframe, currency, owner.
2. **Structure** – break into cost packages, add milestones and required inputs.
3. **Data capture** – analysts import BOM, add labor/logistics lines,
   procurement links quotes, AI assistant suggests benchmarks.
4. **Scenario modeling** – clone baseline, tweak assumptions (FX, volume,
   supplier mix), run calculations.
5. **Review & approval** – gather comments, run AI QA checklist, freeze
   baseline version.
6. **Handoff** – approved baseline pushes to execution layer / exports.

## 3. Functional Scope (MVP → Next)

### MVP (Phase 1)
- Initiative management (CRUD, status, owners, tags).
- Cost package hierarchy (2-level tree: package → line items).
- Scenario versions with basic diff (cost, variance %, comments).
- Input assumption registry (FX rates, inflation, utilization).
- Supplier quote attachments + structured fields (currency, lead time, MOQ).
- Approval log (submitted → reviewing → approved/rejected).
- AI helper hooks (placeholder APIs) for benchmark suggestions.

### Phase 2+
- Multi-scenario comparison dashboard (chart & gap analysis).
- Task assignments & notifications per line item.
- Integration hooks:
  - Push approved scenario to costing execution service.
  - Sync exchange rates from finance API.
- Audit trails & change tracking per field.
- Collaboration (mention, comment threads).

## 4. Data Model (Relational)

### Entity Overview

| Table | Purpose | Key Relationships |
| --- | --- | --- |
| `cost_initiatives` | Top-level project/initiative | 1→many `cost_packages`, `scenario_versions` |
| `cost_packages` | Logical grouping (materials, logistics) | Parent initiative, 1→many `cost_line_items` |
| `cost_line_items` | Smallest cost element (SKU, service) | Belongs to package, optional supplier link |
| `supplier_quotes` | Structured supplier offer | Linked to line items, may store multiple revisions |
| `input_assumptions` | Shared parameters (FX, labor rate) | Referenced by scenarios & calculations |
| `scenario_versions` | Snapshot of line items + assumptions | 1→many `scenario_line_snapshots` |
| `scenario_line_snapshots` | Denormalized values per line in a scenario | Stores calculated totals |
| `approval_records` | Workflow state & comments | Linked to initiative or scenario |
| `attachments` | Files (BOM, quote PDFs) | Polymorphic link to initiatives/packages/lines |

### Table Sketches

`cost_initiatives`
- `id` (uuid), `code`, `name`, `description`, `owner_id`, `sponsor`,
  `currency`, `status` (draft/in_progress/review/approved/archived),
  `target_launch_date`, `created_at`, `updated_at`, `tags` (jsonb).

`cost_packages`
- `id`, `initiative_id`, `name`, `category` (materials/logistics/etc),
  `parent_package_id` (nullable for future nesting), `owner_id`,
  `status`, `notes`, timestamps.

`cost_line_items`
- `id`, `package_id`, `type` (material/labor/service), `reference_code`,
  `description`, `unit_of_measure`, `quantity`, `unit_cost_estimate`,
  `currency`, `supplier_id` (nullable), `status`, `metadata` (jsonb).

`supplier_quotes`
- `id`, `supplier_name`, `contact`, `line_item_id`, `quote_version`,
  `currency`, `unit_cost`, `moq`, `lead_time_days`, `valid_through`,
  `attachments`, `notes`.

`input_assumptions`
- `id`, `initiative_id`, `name`, `type` (fx/inflation/utilization/custom),
  `value`, `unit`, `effective_date`, `source`, `metadata`.

`scenario_versions`
- `id`, `initiative_id`, `code`, `name`, `baseline_flag`,
  `status` (draft/review/approved), `assumption_set_id`,
  `total_cost`, `variance_vs_baseline`, `notes`, timestamps.

`scenario_line_snapshots`
- `id`, `scenario_id`, `line_item_id`, `quantity`, `unit_cost`,
  `currency`, `fx_rate_used`, `markup_percent`, `total_cost`,
  `drivers` (jsonb for assumption references).

`approval_records`
- `id`, `target_type`, `target_id`, `action` (submit/approve/reject),
  `actor_id`, `comment`, `created_at`.

`attachments`
- `id`, `target_type`, `target_id`, `file_name`, `file_url`, `mime_type`,
  `uploader_id`, `uploaded_at`, `category` (BOM/quote/spec).
`scenario_favorites`
- `id`, `scenario_id`, `user_id`, `created_at`（用于 Planner 场景列表收藏与筛选）。
`benchmark_favorites`
- `id`, `benchmark_key`, `user_id`, `payload`, `created_at`（存储 AI Benchmark 收藏及其参数）。
`planner_executor_callbacks`
- `id`, `scenario_id`, `callback_url`, `signature`, `status`, `payload`, `trace_id`,
  `created_at`, `updated_at`（追踪外部执行器回调签名与状态）。
`audit_logs`
- `id`, `target_type`, `target_id`, `action`, `actor_id`, `payload`, `trace_id`,
  `created_at`（Phase3.5 起要求所有审批/导出/回调等操作保留 trace）。

### Integration Notes
- All monetary fields stored in native currency plus normalized base currency
  column (`amount_base`). Base conversion uses snapshot of assumption at the
  time of scenario freeze.
- Soft deletes preferred (`is_archived`) to preserve auditability.

## 5. API & Module Boundaries

- `/api/planner/initiatives`: CRUD, filters by owner/status, metrics (total
  cost, scenario count).
- `/api/planner/packages`: CRUD, supports tree queries.
- `/api/planner/line-items`: CRUD, bulk import (CSV/XLSX), supplier binding.
- `/api/planner/assumptions`: versioned parameters (GET latest, POST new).
- `/api/planner/scenarios`: 列表分页 + filters（initiative/status/baseline/favorite/search）、
  收藏 `POST/DELETE /scenarios/{id}/favorite`、create from baseline、diff vs other
  scenarios、export job + executor callback。
- `/api/planner/approvals`: workflow transitions + comment log.
- `/api/planner/uploads`: signed URL issuance for attachments.
- `/api/planner/benchmarks/suggest`: 代理外部 Benchmark 服务并支持缓存；
  `/api/planner/benchmarks/favorites` 负责收藏同步。
- `/api/planner/executor/callback`: 执行器回调入口，附 HMAC 签名校验与 trace。
- Benchmark Provider 必须具备降级策略：`BENCHMARK_FAIL_OPEN=true` 时请求失败会
  自动返回 fallback/缓存数据；若需完全切换至 mock，可设置
  `PLANNER_FEATURE_FLAG_MOCK_INTEGRATIONS=true`。

Backend service boundaries:
1. **Planner Service** (new FastAPI app or module) – owns tables above.
2. **AI Assistant hooks** – asynchronous worker queue for benchmark lookup.
3. **Sync/export jobs** – push approved baseline to costing executor service.

## 6. Delivery Plan & Task Breakdown

### Phase 0 – Foundations (ETA: 1 day)
- Finalize requirements (this doc) + open questions list.
- Create ERD & migration stubs in backend (SQLModel or Alembic).
- Define API routers & Pydantic schemas.

### Phase 1 – Core Planner CRUD (ETA: 1.5 weeks)
- Backend:
  - Implement initiative/package/line item endpoints.
  - Bulk import pipeline (CSV → job table → validation).
  - Supplier quote linking & validation rules.
  - Input assumption service w/ versioning + effective dates.
- Frontend:
  - Planner workspace pages (initiative list/detail, package tree, line item
    grid with inline edit).
  - Scenario builder UI skeleton.
- QA:
  - Unit tests for models & services.
  - API contract tests for CRUD & validation.

### Phase 2 – Scenario Modeling & Approvals (ETA: 1 week)
- Backend:
  - Snapshot engine (`scenario_line_snapshots`), variance calculations,
    baseline locking.
  - Approval workflow endpoints + notifications hook.
- Frontend:
  - Scenario comparison view, diff table, approval modal.
  - Assumption panel w/ inline edits referencing scenarios.
- QA:
  - Scenario diff tests.
  - Migration of legacy spreadsheets (sample data import).

### Phase 3 – Integrations & Enhancements (ETA: 1 week)
- Export service to costing executor (API client + job state).
- AI benchmark suggestions placeholder UI (calls existing insight API).
- Audit log & attachment viewer components.

### Staffing / Ownership
- Planner (you): maintain requirements & sequencing.
- Backend executor: DB migrations, API, integrations.
- Frontend executor: UX, state management, import flows.
- QA/Analyst: data validation rules, test datasets.

## 7. Open Questions / Risks (Decisions as of 2025-12-13)

1. **Currency handling** – confirmed single-base currency: CNY. Historical FX
   snapshots will be provided manually/by finance exports, so no additional API
   integration is required at this stage.
2. **User identity source** – confirmed reuse of existing SSO/Auth stack and
   role model; evaluate whether project-level ACLs are required.
3. **Attachment storage** – must provision a dedicated OSS bucket/namespace for
   costing artifacts (cannot reuse ai-material-system). Define access control
   and lifecycle policies.
4. **AI assistant data** – business team can supply benchmark datasets. Planner
   must specify ingestion format, retention, and refresh cadence.
5. **Performance limits** – assume large datasets; enforce server-side
   pagination/filtering for line items, make imports & calculations asynchronous,
   and design multi-tier caching to handle >20k lines per initiative.

## 8. Branch Strategy & Ownership

- `feature/costing-planner`: planning branch for requirements, ERDs, DB design,
  and work breakdown.
- `feature/costing-backend`: backend branch handling Planner/Costing APIs,
  algorithms, imports/exports, and data sync.
- `feature/costing-frontend`: frontend branch building Planner UI, menus, and
  module-specific interactions decoupled from the main app shell.
- `feature/costing-docs`: documentation branch for specs, manuals, runbooks, and
  architecture updates to keep implementation in sync.

> Sub-tasks (e.g., scenario engine, FX sync) can spawn child branches such as
> `feature/costing-backend/scenario-engine` to retain clarity.

Document owner: Planner. Please annotate in PRs and update after stakeholder
reviews.

## 附录：中文说明（详版）

### 1. 业务背景与目标
- `AI Costing System` 暂无面向上游的规划工作区，财务、采购、产品运营无法统一记录需求、假设和成本版本，Approved 基线也缺少标准化交接路径。
- Planner 模块需支持：集中化的项目管理、以成本包为单位的拆解、带版本的场景建模（假设包括汇率、供应商报价、加成策略等），以及流程状态/审核历史的透明度。
- MVP 成功标准：
  1. 所有成本项目/活动都在 Planner 中创建并分配责任人。
  2. 每个项目至少保留 2 个可回溯的成本场景版本。
  3. 当场景被批准后，可在 5 分钟内导出并推送到下游成本执行服务。

### 2. 角色与典型流程
- 角色与职责：
  - **Costing PM**：建立项目结构、设定里程碑、最终锁定基线。
  - **Cost Analyst**：导入 BOM、录入明细与假设、维护数量/单价。
  - **Procurement Lead**：管理供应商报价及谈判记录，确认最终供应商。
  - **Exec Reviewer**：对基线进行审核、给出批注、批准或驳回。
- 流程六步：
  1. **Initiation 发起**：创建项目，设置时间范围、币种、负责人。
  2. **Structure 结构化**：拆成成本包，补充所需输入和里程碑。
  3. **Data Capture 数据采集**：分析师导入 BOM、录入人工/物流行，采购绑定报价，AI 助手提供基准建议。
  4. **Scenario Modeling 场景建模**：克隆基线场景，调整假设（汇率、批量、供应商组合）并计算成本。
  5. **Review & Approval 审批**：汇总评论，跑 AI QA 清单，冻结基线。
  6. **Handoff 交接**：批准场景推送到执行层或导出报表。

### 3. 功能范围（MVP → Phase 2+）
- **MVP/Phase 1**
  - 项目（Initiative）及状态/标签管理。
  - 成本包两级结构（包 → 行项目）。
  - 场景版本及基础差异（总成本、偏差%、备注）。
  - 输入假设库（汇率、通胀、工时利用率等）。
  - 供应商报价附件与结构化字段（币种、交期、MOQ）。
  - 审批日志：提交、审核、批准/驳回全链路。
  - AI 助手机制：先提供占位接口，便于未来扩展基准建议。
- **Phase 2+**
  - 多场景对比看板和差异图表。
  - 行项目级任务指派与提醒。
  - 系统集成：Approved 场景推送成本执行服务；自动同步汇率。
  - 字段级审计与变更追踪。
  - 协同功能：@提及、评论线程等。

### 4. 数据模型（关系型）
- 核心实体：
  - `cost_initiatives`：项目/活动。字段包含 code、name、owner、status、currency、target_launch_date、tags 等。
  - `cost_packages`：成本包，挂在 initiative 下，可区分材料/物流/人工等类别，支持未来多级嵌套。
  - `cost_line_items`：最小成本单元（SKU/服务），含类型、编码、单位、数量、预估单价、供应商引用、状态、metadata。
  - `supplier_quotes`：供应商报价的结构化记录，可追踪多版本、MOQ、交期、有效期以及附件。
  - `input_assumptions`：共用假设（汇率、通胀、利用率、自定义参数），带生效日期与来源。
  - `scenario_versions`：场景版本，记录是否 baseline、状态、关联的假设集、总成本及与基线差异。
  - `scenario_line_snapshots`：场景下各行项目的快照，保存数量、单价、币种、汇率、加成、总成本以及驱动因素引用。
  - `approval_records`：审批动作（提交、批准、驳回）及评论，支持多态关联 initiative 或 scenario。
  - `attachments`：文件附件（BOM、报价、规格），统一存储并记录上传人/时间。
- 集成注意事项：
  - 金额字段需同时保存本币与基准币（`amount_base`），基准转换基于场景冻结时的汇率快照。
  - 建议使用软删除（`is_archived`）以便保留审计轨迹。

### 5. API 与模块边界
- 规划 REST 接口：
  - `/api/planner/initiatives`：项目 CRUD、按负责人/状态过滤、输出指标（总成本、场景数）。
  - `/api/planner/packages`：成本包 CRUD，支持树形查询。
  - `/api/planner/line-items`：行项目 CRUD，支持 CSV/XLSX 批量导入及供应商绑定。
  - `/api/planner/assumptions`：假设版本管理，GET latest / POST 新版本。
  - `/api/planner/scenarios`：从基线复制、与其他场景对比、标记批准、触发导出任务。
  - `/api/planner/approvals`：审批流状态迁移与评论。
  - `/api/planner/uploads`：附件上传的签名 URL 服务。
- 后端模块：
  1. **Planner Service**：FastAPI 模块，负责上述实体及业务规则。
  2. **AI Assistant Hooks**：异步队列，用于获取行业基准或自动检查。
  3. **Sync/Export Jobs**：将批准场景推送给下游成本执行系统或外部报表。

### 6. 交付计划与任务拆解
- **Phase 0 – 基础准备（1 天）**
  - 固化需求（本文档）并列出未决问题。
  - 绘制 ERD，搭建数据库迁移骨架（SQLModel/Alembic）。
   - 定义 API Router 与 Pydantic Schema。
- **Phase 1 – 核心 Planner CRUD（约 1.5 周）**
  - 后端：实现 initiative/package/line item 接口；批量导入流水线（CSV → job 表 → 校验）；供应商报价校验；假设版本服务。
  - 前端：Planner 工作区（列表、详情、包树、行项目表格、场景 builder 骨架）。
  - QA：模型/服务单测；CRUD/API 合约测试。
- **Phase 2 – 场景建模与审批（约 1 周）**
  - 后端：快照引擎、差异计算、基线锁定；审批工作流与通知钩子。
  - 前端：场景对比视图、差异表格、审批弹窗；假设面板可联动场景。
  - QA：场景差异测试；示例数据迁移/回放。
- **Phase 3 – 集成与增强（约 1 周）**
  - 完成与成本执行服务的导出/同步；AI 基准提示 UI（对接占位接口）；审计日志与附件查看器。
  - 视情况安排后续 Phase（如协作功能、任务指派等）。
- **Phase 3.5 – 生产级集成（约 1.5 周）**
  - 后端：替换执行器 mock，接入真实 HTTP/gRPC 客户端，补充重试/trace/失败队列/监控；AI Benchmark 对接真实服务并持久化收藏；通知钩子对接消息总线。
  - 前端：新增基于 `/api/planner/scenarios` 的场景列表与收藏，持久化 AI 建议，展示导出历史与分页审计日志；继续懒加载 Job/Audit Drawer 并输出 bundle 报告。
  - 文档/QA：更新截图与操作手册，记录集成回滚方案；准备包含执行器回调与 AI 建议的回归数据集，扩充 QA 检查清单。
- **Phase 4 – 上线前冲刺（约 1 周）**
  - 后端：完善环境配置样例、Prometheus/Grafana 监控、压测与回滚剧本，打通 trace→audit→job→log 一键定位。
  - 前端：优化 bundle（目标 main < 400kB）、完成真实数据 UAT、提供 trace/job 可复制信息、更新生产环境 `.env` 与截图。
  - Docs/QA：发布运行手册、上线 checklist、回归脚本与结果；同步 incident/rollback 文档。
- **角色分工**
  - Planner：持续维护需求与节奏。
  - Backend Executor：DB 迁移、API、外部集成。
  - Frontend Executor：页面与状态管理、导入流程。
  - QA/Analyst：业务规则校验、测试数据准备。

### 7. 已确认事项 / 风险提示
1. **货币策略**：仅采用 CNY 作为基准币种，历史汇率由财务导出或手工录入即可，当前阶段无需新增 API 对接，但场景仍需保存快照。
2. **用户身份**：沿用现有 SSO/Auth 与角色体系，如需细化到项目层面的 ACL 另行评估。
3. **附件存储**：启用独立的对象存储空间（不可复用 ai-material-system Bucket），需定义访问控制与生命周期策略。
4. **AI 助手数据**：业务方可提供基准数据，Planner 需确认数据格式、入库方式、更新节奏。
5. **性能边界**：按大批量设计（>20k 行项目），列表必须服务端分页/筛选，导入和计算流程走异步队列，并考虑分层缓存；Phase 3.5
   起 executor/benchmark 调用需要 trace_id、Prometheus metrics 以及 Kafka/RabbitMQ 事件，方便观测与快速降级。

### 8. 研发分支策略
- `feature/costing-planner`：聚焦需求和架构规划、数据库设计、任务拆解。
- `feature/costing-backend`：负责后端 API、算法、数据同步、导入导出。
- `feature/costing-frontend`：负责 Planner 页面/交互/菜单，与主系统 UI 解耦。
- `feature/costing-docs`：专门维护需求、操作手册、架构文档，确保版本同步。

> 若需细分子功能，可在上述分支下再建语义化子分支，例如
> `feature/costing-backend/scenario-engine`。

> 如需进一步把英文段落逐条翻译成中文，可在以上详版基础上继续扩展；若有特定章节需要增删，请直接指出。

---

## 11. 产品模型主线要点（2025-12-14）

1. **工艺模块**：坚持“三层架构”，工序作为“物料 + 人工”的最小复用单元，产品模型仅引用工序并按条件进行替换/添加，避免散落配置。
2. **虚拟物料/管理费**：允许在工序中配置虚拟物料以计提管理费、能耗等费用，但必须记录在 `process_materials`，便于审计与统计。
3. **标准尺寸 vs 实际尺寸**：所有模型以 1m × 1m 标准尺寸维护单价/耗损；实际订单按面积/周长比例放大或缩小，超过阈值时自动替换厚板、龙骨等物料。
4. **变体规则**：仅处理工序内部“物料替换/添加”场景；触发条件限定为 SKU 特征匹配、面积阈值、周长阈值。若工序差异本质不同，应新建独立模型。
5. **SKU 绑定策略**：新品上架时执行一次标准化（AI 解析 + 运营确认），之后只依据 `SKU ID` 绑定模型，运营可自由修改标题。
6. **数据来源**：物料、工序、模型、规则等核心数据以本地数据库为准；宜搭/表单（见 `DOC/基础表单/*.pdf/.xlsx`）作为只读源，通过同步服务导入并校验字段。
7. **Phase0 样本与验收**：按 `DOC/costing/phase0_sample_data.md` 的模板导入样本物料/工序/模型，完成字段映射与计算导出验证后，再扩展至大规模数据。



