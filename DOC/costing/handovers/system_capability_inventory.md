# 系统能力清单（System Capability Inventory）

> **版本**：v1.0
> **维护人**：PnL/Hub Agent（Planner-Optimization 角色）
> **最近校对（北京时间 GMT+8）**：2026-05-09 17:30
> **来源**：本文档不是凭印象写的，每条都对应 `backend/src/planner/{routers,services}/` 真实文件 / `frontend/src/pages/costing/` 真实路由 / `backend/migrations/versions/` 真实迁移 / `DOC/agents/{state,task_log,known_issues}.md` 已落地条目。任何后续 PnL/Hub Agent 接力前**必须先把本文读完**，再动 PnL/Hub 任何设计文档。

---

## 0. 必读约束（任何 Agent 接力 PnL/Hub 任务时第一份要读的文档）

### 0.1 教训（2026-05-09，必须承认）

第一轮 PnL/Hub 设计走偏的根因：

1. **没读 `DOC/agents/state.md`**（3317 行真相文档）→ 把 4 个早已上线的 Insights 看板 + `shipment_costing_results` 表当成"待新建"
2. **没读 `DOC/agents/known_issues.md` Issue 23/28**（SKU 治理 4 态 + LongTailCogsRateStrategy）→ 把雏形版 Cost Rate Hub 当成"待原创设计"
3. **没读 `DOC/costing/blueprints/profit_and_returns_analytics_plan_2025_2026_v0_1.md`** → 把项目原配蓝图当成"待新写"
4. **没读 `DOC/agents/agent_rules.md` + `task_distribution_standard.md`** → 一次大刀阔斧改 9~12 个文档，违反"一轮一闭环 + 跨文件风暴"规则
5. **23% 误读**：把 Guides Agent 2026-01-13 落地的"30%/(1+30%)=23.08%"数学折算错当成"反推真实费率"

### 0.2 强制纪律

- **永远先读 `DOC/agents/agent_rules.md`** — 这是仓库级硬约束（一轮一闭环 / 大文件不直读 / 北京时间口径 / 跨文件风暴禁令）
- **永远先读 `DOC/agents/task_distribution_standard.md`** — Hub Agent 派单体系 / 任务单模板 / 三件强制（任务表 / 唯一硬验收 / 分歧处理）
- **永远先读 `DOC/agents/state.md` 但不能全读** — 用 `grep` 搜关键词，只读 ±50 行段落
- **永远先看 `DOC/agents/known_issues.md`** — 33+ 已知坑位每个都附带 service / router / table / 测试文件位置
- **PnL/Hub Agent 是 Hub 角色** — 不直接写代码，写代码必须派 Backend / Frontend Agent 闭环任务单

---

## 1. 一句话总结（PnL/Hub 模块站在什么位置）

> **`ai-costing-system` 已经是一个 30 + 前端页面 / 33 后端 router / 37 个 Alembic 迁移 / 5 个雏形子系统的运行系统。PnL/Cost Rate Hub 是在这个运行系统上"补可信度治理 + 结构化费率管理"，而不是从 0 起新模块。**

---

## 2. 现有前端页面（30 个生产路由 + 11 个组件）

> 来源：`frontend/src/App.tsx` + `frontend/src/pages/costing/**/*.tsx`

### 2.1 主数据维护类（8 个）

| 路由 | 中文名 | 文件 | PnL/Hub 复用关系 |
|---|---|---|---|
| `/costing/materials` | 真实物料主档 | `MaterialMasterPage.tsx` | **Stage 2 物料成本固化的入口**（含引用关系区块、单价历史） |
| `/costing/virtual-materials` | 虚拟物料 | `VirtualMaterialsPage.tsx` | Stage 2 物料分摊参考 |
| `/costing/processes` | 工序管理 | `ProcessesPage.tsx` | Hub `labor_per_minute` 费率源头（`standard_rate` + `charging_mode`） |
| `/costing/process-modules` | 工艺模块 | `ProcessModulesPage.tsx` | 含 `ai_spec` 与结构标签，不直接出现费率 |
| `/costing/taxonomy` | 分类管理（含班组） | `TaxonomyManagementPage.tsx` | **班组主数据所在地**（`domain='team'` + `default_minute_rate`），Hub 班组维度的真相 |
| `/costing/structure-standards` | 结构标准 | `StructureStandardsPage.tsx` | 与 PnL/Hub 无直接关系（结构骨架字典） |
| `/costing/sample-models` | 打样模型 | `SampleModelsPage.tsx` | 模型 BOM 编辑入口（draft 路径） |
| `/costing/standard-models` | 标准模型 | `StandardModelsPage.tsx` | **KB8 的"清单编辑"抽屉** = 物料费 26.93 / 人工费 7.34 / 制造费(23%) 10.28 / 合计 44.55 的 UI 来源 |

### 2.2 业务运营类（8 个）

| 路由 | 中文名 | 文件 | PnL/Hub 复用关系 |
|---|---|---|---|
| `/costing/shipments` | 发货台账 | `ShipmentLedgerPage.tsx` | **Phase 1 主战场**：抽屉含 BOM 物料 / 成本拆分 / 工序明细 / 扣库行 4 个 Tab |
| `/costing/shipments/ops` | 发货作业中心 | `ShipmentMonitorPage.tsx` + `ShipmentOpsPage.tsx` | 写操作总入口（异常队列 / 重算 / 批量计价） |
| `/costing/biz/shipments` | 发货管理（业务派） | `biz/ShipmentManagementPage.tsx` | 4 阶段 Tab：待处理/处理中/已完成/长尾池 |
| `/costing/biz/after-sales` | 售后管理 | `biz/AfterSalesManagementPage.tsx` | 售后退货导入 + 查询 |
| `/costing/sku-master` | SKU 主档工作台 | `SkuMasterWorkspacePage.tsx` | 含 100w SKU 治理 + 4 态状态机 + 长尾品类标记 |
| `/costing/spec-matching` | 规格匹配 | `SkuSpecMatchingPage.tsx` | spec → tokens 预解析 |
| `/costing/integrations` | 外部数据同步 | `IntegrationsHubPage.tsx` | Jackyun 同步 + 状态查看 |
| `/costing/products-info` | 产品信息 | `ProductInfoPage.tsx` | 上架/产品中心 |

### 2.3 数据洞察类（4 个，**与 PnL 强相关，第一轮被忽略**）

| 路由 | 中文名 | 文件 | PnL/Hub 复用关系 |
|---|---|---|---|
| `/costing/insights/sales` | 销售数据 | `SalesInsightsPage.tsx` | 已上线，按时间 + 渠道汇总 |
| `/costing/insights/shops` | 店铺数据 | `ShopInsightsPage.tsx` | **已上线**：利润 + 退货率两 Tab + 覆盖率筛选 |
| `/costing/insights/models` | 模型分析（利润） | `ProfitInsightsPage.tsx` | **已上线**：货品/模型两 Tab，调用 `/profit/sku` + `/profit/model` |
| `/costing/insights/after-sales` | 售后分析 | `AfterSalesInsightsPage.tsx` | **已上线**：退货率，含售后 xlsx 导入入口 |

> **结论**：PnL Phase 1 不需要"造新看板"，应该是给这 4 个已上线看板加"成本可信度三色徽章 / 三视图（FI/CO/集团）切换" → 派 Frontend Agent 1 个任务单即可。

### 2.4 工具/规则/管理类（6 个）

| 路由 | 中文名 | 文件 | PnL/Hub 复用关系 |
|---|---|---|---|
| `/costing/pricing-tools` | 定价工具 | `PricingToolsPage.tsx` | 与定价相关（待评估是否做 Hub 入口） |
| `/costing/shipping-rules` | 运费规则 | `ShippingRulesPage.tsx` | 净利润计算的运费来源 |
| `/costing/admin/long-tail-cogs-rate` | **长尾成本策略** | `admin/LongTailCogsRatePage.tsx` | **雏形版 Cost Rate Hub**（4 层优先级 + history） — 必须复用而非另起 |
| `/costing/bundle-templates` | 套装模板 | `BundleTemplatesPage.tsx` | 复杂 BOM 来源 |
| `/costing/product-listing` | 产品上架（测试台） | `ProductListingPage.tsx` | spec 解析/变体演练 |
| `/costing/production-scan` | 生产扫码 | `ProductionScanPage.tsx` | 产线扫码（车间） |

### 2.5 套装/天猫工具类（4 个）

`/costing/tmall-sku-generator` `/costing/tmall-sku-generator/:templateId` `/costing/system/target-picker-playground` `/costing/biz/shipments` 子组件 `LineResolveActions`、`ModelPickerDrawer`、`PendingTab`、`DoneTab`、`shipment-ops/components/{BatchWorkbench,GovernanceBacklogTab,BulkCostingTab,ImportWizardModal}`

---

## 3. 现有后端 Routers（33 个，已纳入 `/api/planner/*` 总路由）

> 来源：`backend/src/planner/routers/*.py` + `backend/src/planner/router.py`

### 3.1 主数据/产品类（10 个）

`base_config.py`（真实物料/虚拟物料/分类）、`taxonomy.py`（含 `domain='team'` 班组）、`structure_standards`（在 taxonomy）、`processes.py`、`process_modules.py`、`product_models.py`、`product_model_versions.py`、`bom.py`（动态 BOM）、`specs.py`（spec/parse）、`line_variants.py`

### 3.2 业务运营/发货类（8 个）

`shipments.py`（发货导入/批次/异常队列/BOM 快照）、`after_sales.py`、`sku_master.py`（含 governance/long-tail-category）、`bundle_templates.py`、`shipping_rules.py`、`integrations.py`、`callbacks.py`、`jobs.py`

### 3.3 分析/报告/审计类（5 个，**与 PnL 强相关**）

| Router | 关键 endpoint | PnL/Hub 复用关系 |
|---|---|---|
| `analytics.py` | `/profit/sku` `/profit/model` `/profit/channel` `/returns-rate/sku` `/returns-rate/channel` `/models/summary` `/models/materials-summary` | **PnL Phase 1 主接口已经在这里** |
| `reports.py` | 报表导出 | 月度变成本/差异报表的载体 |
| `audit.py` | 审计日志 | Hub 改 rate 的 audit 落地 |
| `benchmarks.py` | 基准 | 对比基线 |
| `assumptions.py` | 假设 | Scenario 假设 |

### 3.4 Phase 1-3.5 既有架构 Routers（5 个）

`initiatives.py` `packages.py` `scenarios.py` `approvals.py` `line_items.py`（Phase 1-3.5 既有架构，详见 `DOC/costing/architecture.md`）

### 3.5 工具/AI/健康类（5 个）

`ai.py`、`codes.py`、`tmall_sku_template.py`、`binding_targets.py`、`health.py`、`long_tail_strategies.py`（**雏形版 Hub 的 router**）

---

## 4. 现有后端 Services（34 个）

> 来源：`backend/src/planner/services/*.py`

### 4.1 与 PnL/Hub 强相关的 6 个核心 Service

| Service | 文件 | PnL/Hub 必须知道 |
|---|---|---|
| **`bom_generation_service.py`** | 动态 BOM + 成本计算（`_resolve_overhead_rate` 含 0.30 兜底） | 改 overhead 兜底/制造费率必须改这里 |
| **`analytics_service.py`** | profit/returns/coverage 全部聚合 | 加成本可信度徽章必须改这里 |
| **`shipment_import_service.py`** | 发货导入 + 异常队列 + sweep + auto-resolve（**5000+ 行**） | 任何"发货级别成本快照"逻辑都在这里 |
| **`long_tail_strategy_service.py`** | **雏形版 Cost Rate Hub Service**（4 层优先级 resolve + history audit） | Hub 设计必须 fork 这个文件而非新写 |
| **`data_quality_service.py`** | nightly + mark_only + 三色徽章雏形 | 成本可信度徽章应该挂在这里 |
| **`sku_master_service.py`** | SKU 治理 4 态 + auto_bind + long_tail_category | Hub 与 SKU 治理状态机的耦合点 |

### 4.2 其他 28 个

`product_model_service.py`、`shipment_import_worker.py`、`after_sales_import_service.py`、`spec_parser_service.py`、`line_variant_service.py`、`report_snapshot_service.py`、`binding_target_service.py`、`bundle_template_service.py`、`yida_sync.py`、`dingtalk_client.py`、`shipping_rule_service.py`、`material_service.py`、`variant_rule_service.py`、`material_image_storage.py`、`metrics.py`、`audit_service.py`、`notification_service.py`、`snapshot_service.py`、`quote_service.py`、`import_service.py`、`sku_master_image_storage.py`、`model_version_image_storage.py`、`process_module_service.py`、`llm_text_service.py`、`process_service.py`、`material_bom_derivation.py`、`code_generator_service.py`、`executor_client.py`

---

## 5. 现有数据表（按 Alembic 迁移按时间倒序，37 个）

> 来源：`backend/migrations/versions/0001 ~ 0037`

### 5.1 与 PnL/Hub 强相关的 7 个迁移

| 迁移 | 表/能力 | PnL/Hub 复用关系 |
|---|---|---|
| `0027_shipment_costing_results_no_snapshot` | **`shipment_costing_results` 表**：`cost_material_total` / `cost_process_total` / `cost_overhead_total` / `cost_total` | **Phase 1 已有的成本结果落库表**，PnL 不需要造新表 |
| `0035_long_tail_cogs_rate_strategy` | `long_tail_cogs_rate_strategies` 表：`category` / `rate` / `keywords` / `priority` / `metadata.history` | **雏形版 Hub** 的存储表 |
| `0017_shipment_import_bom_snapshots_mvp` | `bom_snapshots` + `shipment_exception_queue` + `spec_parse_snapshots` | BOM 快照、异常队列基础 |
| `0018_sku_master_import_mvp` | `sku_master` 表 + governance metadata | SKU 治理基础 |
| `0019_taxonomy_management` | `taxonomy_items` 表 + `domain='team'` | **班组主数据**（`default_minute_rate` 在这） |
| `0025_after_sales_import_mvp` | `after_sales_lines` + `returns_*` | 退货分析基础 |
| `0028_returns_rate_indexes` | 退货率索引 | 性能 |

### 5.2 其他 30 个迁移（按需 grep）

`0001_init` ~ `0037_shipment_exception_queue_line_idx`，含 SKU master、BOM 套装模板、Jackyun 全字段、Tmall SKU 模板、运费规则、整合层等。

### 5.3 PnL/Hub Phase 1 真正缺的表（必须新建）

| 表 | 作用 | 优先级 |
|---|---|---|
| `cost_center` | 4 概念里的 `cost_center_id` 主数据（v1 必需） | **P0** |
| `overhead_rate_master` | 制造费率主数据（model/category/cost_center/global 4 层） | **P0** |
| `cost_rate_history`（可复用 long-tail 的 metadata.history 模式） | Hub 改 rate 审计 | P1 |
| `monthly_cost_variance` | 标准成本 vs 实际成本月度差异 | P2 |
| `cost_pool_master`（v1.2 设计） | 4 个固定费用池 | P2 |

---

## 6. 5 个雏形子系统（**第一轮设计被忽略，必须先研究再扩展**）

### 6.1 LongTailCogsRateStrategy（雏形版 Cost Rate Hub）

- **代码**：`backend/src/planner/services/long_tail_strategy_service.py` + `backend/src/planner/routers/long_tail_strategies.py` + `frontend/src/pages/costing/admin/LongTailCogsRatePage.tsx`
- **能力**：4 层优先级 resolve（人工指定 > keyword 命中 > category default > global fallback）+ metadata.history audit + CRUD + resolve-preview + auto-suggest 自动标品类
- **关键 API**：`GET/POST/PATCH/DELETE /api/planner/long-tail-strategies` + `POST /resolve-preview` + `POST /auto-suggest/preview` + `/auto-suggest/execute`
- **测试**：`backend/tests/planner/test_long_tail_strategy.py` 16/16 + `test_long_tail_auto_suggest.py` 9/9
- **PnL/Hub 行动**：Cost Rate Hub v1.3 设计应该是"扩展 long-tail 模式到 labor / overhead 维度"，而不是另起新表。具体方案：在 `long_tail_cogs_rate_strategies` 基础上加 `rate_type`（cogs / labor_per_minute / overhead_rate）+ `scope_type`（model / category / cost_center / global）即可同名升级。

### 6.2 SKU 治理 4 态状态机

- **代码**：`backend/src/planner/services/sku_master_service.py::set_sku_governance` + `frontend/src/pages/costing/shipment-ops/components/GovernanceBacklogTab.tsx`
- **状态**：`unmanaged` / `auto_bound` / `pending_model` / `do_not_model`
- **关键 API**：`POST /api/planner/sku-master/governance` + `GET ...?status=` + `POST .../promote-from-model`
- **PnL/Hub 行动**：成本可信度徽章应该跟 SKU 治理状态机对齐 — `auto_bound` = 🟢 / `pending_model` = 🟡 / `do_not_model` = 🔴（长尾兜底）

### 6.3 data_quality_service（雏形版可信度治理）

- **代码**：`backend/src/planner/services/data_quality_service.py` + `frontend/src/pages/costing/SkuMasterWorkspacePage.tsx` 红 Tag
- **能力**：nightly 自动跑（`ai-costing-data-quality.timer`）+ mark_only 模式 + SPU 属性冲突检测
- **PnL/Hub 行动**：成本可信度三色徽章可以在 `data_quality_service` 里加 `cost_quality` 维度（material/labor/overhead 三个 enum），而不是新写 service

### 6.4 shipment_costing_results（轻量成本结果落库）

- **代码**：迁移 `0027` + `backend/src/planner/models.py::ShipmentCostingResult`
- **字段**：`cost_material_total` / `cost_process_total` / `cost_overhead_total` / `cost_total` + `metadata_json.kind='long_tail_fallback'`
- **PnL/Hub 行动**：Phase 1 三段成本数据已经在产，不需要新建 `shipment_pnl_lines` 表。盈亏分析 SQL view 直接 JOIN `shipment_costing_results` 即可。

### 6.5 4 个 Insights 看板（已上线）

- **代码**：`frontend/src/pages/costing/{Profit,Shop,Sales,AfterSales}InsightsPage.tsx` + `backend/src/planner/services/analytics_service.py` + `backend/src/planner/routers/analytics.py`
- **API**：`/profit/sku` `/profit/model` `/profit/channel` `/returns-rate/sku` `/returns-rate/channel`
- **现状**：已支持时间窗 + 渠道筛选 + 覆盖率显示 + xlsx 导入 + 按用户点查询
- **PnL/Hub 行动**：Phase 1 不需要造新看板，给现有 4 个加"成本可信度徽章 + 三视图切换"。

---

## 7. 关键事实（PnL/Hub Agent 必须先承认，否则设计直接错）

### 7.1 23% 真相（已证）

- **源头**：`task_log.md:15` 2026-01-13 Guides Agent 落地 / `state.md:1823-1843` 详细推导
- **数学事实**：制造费 = (物料费 + 人工费) × 30% → 占合计比例 = 30% / (1 + 30%) = **23.08%**
- **后端代码**：`bom_generation_service.py:2047 _resolve_overhead_rate` 兜底 `0.3`（30%），未变
- **UI 显示**：`StandardModelsPage` 抽屉显示"制造费(23%)：10.28"，这是数学折算后的占比展示，**不是反推真实费率**
- **PnL/Hub 行动**：
  - ❌ 不要写"把 30% 替换成真实 23%" / "反推制造费率" / "23% 是 UI 误差" 等任何错误叙述
  - ✅ 应写"30% 是兜底默认值，需要 Hub 提供 model/category/cost_center 维度的真实 overhead_rate 覆盖兜底"

### 7.2 3 法人物理一体（已证）

- **事实**：3 工厂在一栋楼，是 1 个生产体系；只有材料采购（一般纳税人 / 小规模）+ 人员归属有税务/合规分别
- **PnL/Hub 行动**：
  - ❌ 不要写"按 factory 分摊" / "factory 是 v1 必需维度"
  - ✅ 应写 4 概念正交：`production_unit_id`（生产物理单元，v1 = 1）/ `purchase_entity_id`（采购法人，v1 = 3）/ `cost_center_id`（成本中心，v1 = 班组级别）/ `legal_entity_id`（法人，FI 视图用）

### 7.3 班组主数据所在地（已证）

- **事实**：班组在 `taxonomy` 表 `domain='team'`，含 `default_minute_rate` 字段
- **PnL/Hub 行动**：
  - ❌ 不要在 `processes` 表加 `cost_center_id` / `team_id`
  - ✅ 班组维度费率应该 fork `taxonomy.team.default_minute_rate` 再扩展，并参考 long-tail 的 4 层 resolve 模式

### 7.4 多 Agent 协作体制（已证）

- **事实**：项目 13 个 Agent 角色（Hub/Planner/Backend/Frontend/Docs/Rules/Guides/POD/Integration/Optimization/...）+ 任务单制度 + state.md 是单一真相
- **PnL/Hub 行动**：
  - ❌ Hub Agent 不直接改 `frontend/src/` `backend/src/` 任何代码
  - ✅ Hub Agent 只产 `DOC/costing/blueprints/` `DOC/costing/handovers/` 文档 + 派 `DOC/agents/briefings/<task>.md` 任务单

---

## 8. PnL/Hub 真正缺什么（v1.3 校准方向）

### 8.1 复用什么（不要再造）

1. ✅ `long_tail_cogs_rate_strategies` 表 + service + router → **直接扩展为 Hub**（加 `rate_type` + `scope_type`）
2. ✅ `shipment_costing_results` 表 → **Phase 1 三段成本数据源**，盈亏 SQL view 直接 JOIN
3. ✅ 4 个 Insights 看板（`/profit/*` + `/returns-rate/*`）→ **加成本可信度徽章 + 三视图切换**
4. ✅ `data_quality_service` → 加 `cost_quality` 维度
5. ✅ SKU 治理 4 态 → 与成本可信度徽章对齐
6. ✅ `taxonomy.team` + `default_minute_rate` → 班组维度费率源头

### 8.2 真正缺的（v1.3 必须新建）

1. ❌ `cost_center` 主数据表（v1 = 班组级别 6~10 个，运营人 1 周内可初稿）
2. ❌ `overhead_rate_master` 表（或在 long-tail 表上扩展 `rate_type='overhead_rate'`）
3. ❌ `cost_rate_history`（可复用 long-tail 的 metadata.history 模式）
4. ❌ Frontend 的"Cost Rate Hub" 入口页（**v1 仅 2 个 Tab**：Overview + Editor）
5. ❌ `monthly_cost_variance` 表（v1 可推迟到 Phase 2）
6. ❌ 三视图切换（FI / CO / 集团）— v1.3 设计 UI 即可，后端在 view 层加 `entity_type` filter

### 8.3 v1.3 必读外部评审

- `DOC/基础表单/专业版盈亏分析模块初步评审报告VI.md`（Manus 第 1 轮）
- `DOC/基础表单/多主体核算与品类制造费率补充评审报告.md`（Manus 第 2 轮）
- `DOC/基础表单/成本参数Hub与月度调节面板：评审与设计建议.md`（Manus 第 3 轮，**最有价值**）
- `DOC/基础表单/对用户解答的二次评审：factory 维度修正版结论.md`（Manus 第 4 轮，4 概念修正）

---

## 9. 文档全景（PnL/Hub Agent 接力时必须知道的所有文档）

### 9.1 Agent 体系（5 个，**强制读**）

| 文档 | 作用 |
|---|---|
| `DOC/agents/agent_rules.md` | 仓库级硬约束 |
| `DOC/agents/task_distribution_standard.md` | Hub 派单体系 |
| `DOC/agents/state.md` | 3317 行真相文档（grep 不直读） |
| `DOC/agents/known_issues.md` | 33+ 已知坑位 + 雏形子系统设计明细 |
| `DOC/agents/task_log.md` | 变更日志 |

### 9.2 Handoff 接力包（7 个，按角色）

`handoff_planner.md` `handoff_frontend.md` `handoff_backend.md` `handoff_docs.md` `handoff_pod.md` `handoff_rules.md`

### 9.3 项目蓝图（12 份 blueprints）

`profit_and_returns_analytics_plan_2025_2026_v0_1.md`（**原配蓝图**）、`pnl_analytics_module_design.md`、`cost_rate_hub_design_v1.md`、`finance_analyzer_integration_v1.md`、`sku_portfolio_management_v1.md`、`sku_binding_bom_shipment_plan.md`、`standard_model_variants_plan.md`、`erp_writeback_process_spec_mvp.md`、`bundle_templates_z_b_protocol.md`、`pod_personalization_print_pipeline_phase0.md`、`jky_api_requirements_form_v1.md`、`jky_after_sales_returns_requirements_form_v1.md`

### 9.4 用户指南（16 份 guides）

`price_calculation_guide.md`（含 23% 数学折算）、`team_rate_guide.md`、`materials_guide.md`、`usage_calculation_guide.md`、`product_model_guide.md`、`virtual_materials_guide.md`、`process_create_guide.md`、`process_modules_guide.md`、`structure_standards_guide.md`、`sample_lines_guide.md`、`standard_lines_guide.md`、`access_control_quick_guard.md`、`derive_standard_per_sqm_tablecloth_example.md`、`table_list_style_two_line_cells.md`、`virtual_materials_design_draft_v0_1.md`、`README.md`

### 9.5 业务规则（3 份 rules + 1 个 README）

`rules/README.md`（含 draft/active/deprecated 治理模板）、`R-MAT-001_material_usage_class_trinary.md`、`R-TEAM-001_team_rate_default_yuan_per_min.md`

### 9.6 PnL/Hub 任务历史产出（11 份，**v1.3 校准对象**）

详见 `workset.md §7.3`。

---

## 10. PnL/Hub Agent 下一轮闭环建议（v1.3 校准计划）

> **基于本清单，建议 PnL/Hub Agent 下一轮以"小步快跑、一份一闭环"方式校准**。

### 10.1 v1.3 校准 — 第 1 轮闭环（推荐）

**任务**：校准 `DOC/costing/blueprints/cost_rate_hub_design_v1.md` 为 v1.3
**核心动作**：
1. 整段重写"§1 现状"，改为"基于 long-tail 雏形扩展"
2. 整段删除"§3 新建表清单"中重复造的部分（`overhead_rate_master` 改为 long-tail 表 schema 扩展）
3. 整段删除"23% 反推"叙述，写入 30% 兜底 + Hub 覆盖逻辑
4. 整段删除"factory 维度"叙述，写入 4 概念正交
5. 整段重写"§5 UI"，改为"加在 LongTailCogsRatePage 之上的扩展 Tab"

**验收命令**：
```bash
grep -nF "v1.3" DOC/costing/blueprints/cost_rate_hub_design_v1.md && \
grep -nF "long_tail_cogs_rate_strategies 表 + service + router 直接扩展" DOC/costing/blueprints/cost_rate_hub_design_v1.md && \
grep -nF "30% 是兜底默认值" DOC/costing/blueprints/cost_rate_hub_design_v1.md
```

### 10.2 v1.3 校准 — 第 2~5 轮闭环（先不做）

校准 `pnl_analytics_module_design.md` / `pnl_module_handover.md` / `pnl_phase_status.md` / `pnl_decision_log.md` 为 v1.3 — 等用户确认本清单后再启动，避免再次跨文件风暴。

---

## 11. 验收命令（本文产出闭环）

```bash
test -f DOC/costing/handovers/system_capability_inventory.md && \
grep -c "^## " DOC/costing/handovers/system_capability_inventory.md && \
grep -nF "PnL / Cost Rate Hub 任务工作集" DOC/agents/workset.md && \
grep -nF "system_capability_inventory" DOC/agents/task_log.md
```

预期：
- `test -f` → 0
- `grep -c "^## "` → 12（11 个二级标题 + Title 不算）
- 后两条 `grep -nF` → 各返回 1 行命中

---

## 12. 历史已动 11 份 PnL/Hub 文档全清单 + v1.3 校准生效后的文档优先级规则

> **本节是为了解决"PnL/Hub Agent 反复忘记之前动过哪些文档 → 重复造轮子"的根因。任何后续 Agent 接力时，先看本节，就能一眼知道"哪份是当前真相 / 哪份过时了哪段 / 校准时该改谁不该改谁"。**
>
> 维护契约：本节的"当前版本号"与"冲突点"列必须在每次校准动作完成后**当轮立刻更新**。如果 Agent 改了文档但没更新本节，等同于没完成闭环。

### 12.1 历史已动 11 份文档（按校准生效后的"真相强弱"排序）

| 序号 | 文档 | 当前版本 | 性质 | 含义 / 冲突点（v1.3 校准生效后的判定） |
|---|---|---|---|---|
| 0 | `DOC/costing/handovers/system_capability_inventory.md` | **v1.0**（含 §12，本节） | **🟢 真相基准** | 所有事实/复用边界/23% 真相/4 概念/雏形子系统代码定位的单一真相。其他文档若有冲突，**以本文为准**。 |
| 1 | `DOC/costing/blueprints/cost_rate_hub_design_v1.md` | **v1.3**（待本轮升级，原 v1.2） | **🟢 Hub 设计真相** | Cost Rate Hub 架构/表/API/UI/三阶段计划的单一真相。其他文档对 Hub 的描述若与 v1.3 冲突，**以本文 v1.3 为准**。 |
| 2 | `DOC/costing/blueprints/profit_and_returns_analytics_plan_2025_2026_v0_1.md` | **v0.1**（**未动过 — 项目原配蓝图**） | **🟢 PnL 原配蓝图** | 4 个 Insights 看板 / 3 个 profit API / shipment_costing_results 表 / cost_snapshot 概念的源头。**禁止覆盖**。 |
| 3 | `DOC/costing/manuals/guides/price_calculation_guide.md` | **v2.1**（已与财务团队建立口径） | **🟢 财务口径** | 三层价格定义 + 23% 数学折算（30%/(1+30%)=23.08%）。**只读不动**。 |
| 4 | `DOC/costing/manuals/transfer_pricing_handbook.md` | （无明文版本号） | **🟢 定价口径** | 内部转移价四线约束 + market_price_reference + strategic_subsidy_log。**与 Hub 是接口关系，不合并**。 |
| 5 | `DOC/costing/blueprints/pnl_analytics_module_design.md` | **v1.1** | 🟡 待校准 | 含"shipment_pnl_lines 新表"叙述 → **v1.3 起以"复用 shipment_costing_results 表"为准**（不动正文，靠优先级规则覆盖）。其余内容（GM1/GM2/NP3 + 三视图）保留。 |
| 6 | `DOC/costing/blueprints/sku_portfolio_management_v1.md` | **v1.1** | 🟡 待校准 | 含"factory 维度"叙述 → **v1.3 起以"4 概念正交（无 factory v1）"为准**。5 类亏损决策内容保留。 |
| 7 | `DOC/costing/blueprints/finance_analyzer_integration_v1.md` | **v1.1** | 🟡 待校准 | 含"new overhead_rate_master 表"叙述 → **v1.3 起以"扩展 long_tail_cogs_rate_strategies 表"为准**。三层结构 + C1/C2/C3 契约保留。 |
| 8 | `DOC/costing/handovers/pnl_module_handover.md` | **v1.2** | 🟡 v1.3 同步 | 接力总入口。本轮 v1.3 校准后，本文"必读文档"列表需补上 `system_capability_inventory.md` 与 `cost_rate_hub_design_v1.md v1.3`。**正文不动，靠引用即可生效**。 |
| 9 | `DOC/costing/handovers/pnl_decision_log.md` | **v1.2**（决策 #1~#47 + H4） | 🟡 v1.3 同步 | 决策日志。本轮校准后追加决策 #48 = "v1.3 校准生效，文档优先级规则见 system_capability_inventory.md §12"。 |
| 10 | `DOC/costing/handovers/pnl_phase_status.md` | **v1.2** | 🟡 v1.3 同步 | 进度看板。Hub 三阶段计划以 cost_rate_hub_design_v1.md v1.3 §11 为准。 |
| 11 | `DOC/costing/handovers/pnl_external_reviews/INDEX.md` | **v1.2** | 🟡 v1.3 同步 | 外部评审 5 份归档。本轮校准后，需在末尾追加 §6「v1.3 校准依据：系统能力清单 + 4 份外部评审反思」。 |
| 12 | `DOC/costing/handovers/phase0_review_checklist.md` | **v1.2.1** | 🟡 v1.3 同步 | 评审清单。本轮校准后，需把决策项 H1/H2/H3 改为引用 v1.3，新增 H5 = "采纳系统能力清单 v1.0 作为后续接力第 1 份必读"。 |

### 12.2 v1.3 校准生效后的"文档冲突时优先级规则"

> 如果两份文档对同一问题给出不同答案，**按本规则排序解决**：

```
P0 - DOC/agents/state.md（项目真相）
P0 - DOC/agents/known_issues.md（雏形子系统真相）
P1 - DOC/costing/handovers/system_capability_inventory.md（本文，事实清单）
P2 - DOC/costing/blueprints/cost_rate_hub_design_v1.md v1.3（Hub 设计真相）
P3 - DOC/costing/blueprints/pnl_analytics_module_design.md v1.2（**全员必读总图**，2026-05-09 17:55 升 v1.2 同步 Hub v1.3）
P3 - DOC/costing/blueprints/profit_and_returns_analytics_plan_2025_2026_v0_1.md（PnL 原配蓝图）
P3 - DOC/costing/manuals/guides/price_calculation_guide.md v2.1（财务口径）
P3 - DOC/costing/manuals/transfer_pricing_handbook.md（定价口径）
P4 - 其他 v1.1 蓝图（sku_portfolio_management / finance_analyzer_integration — 仍待校准为 v1.2，见 §13 防忘追踪）
P4 - 其他 PnL handovers（pnl_module_handover / pnl_decision_log / pnl_phase_status / phase0_review_checklist / pnl_external_reviews/INDEX）
```

冲突解决方式：**高优先级覆盖低优先级**，无需逐字修改 P5 文档的过时叙述（避免跨文件风暴）。低优先级文档作为"历史方案蓝图"保留，但读者必须明白其中部分叙述已被 P2/P1 覆盖。

### 12.3 v1.3 校准明确"废弃"的过往叙述（任何后续 Agent 不得引用以下任何 1 条）

| 序号 | 被废弃的叙述 | 出现位置（不需要去删，但读到时必须知道已废弃） | 替代叙述 |
|---|---|---|---|
| W1 | "23% 是真实制造费率，30% 是错误兜底，需要反推真实 23%" | 任何 PnL 文档若隐含此意 | 23% = 30%/(1+30%) = 23.08% 是数学折算占比；30% 是后端兜底，需要 Hub 提供 model/cost_center 维度的真实 overhead_rate 覆盖 |
| W2 | "Phase 1 必须新建 shipment_pnl_lines 表" | `pnl_analytics_module_design.md` v1.1 | Phase 1 复用已有的 `shipment_costing_results` 表（迁移 0027），盈亏 SQL view 直接 JOIN |
| W3 | "Phase 1 必须新建 overhead_rate_master 表" | `cost_rate_hub_design_v1.md` v1.2 / `finance_analyzer_integration_v1.md` v1.1 | 在 `long_tail_cogs_rate_strategies` 表加 `rate_type`（cogs/labor_per_minute/overhead_rate）+ `scope_type`（model/category/cost_center/global）即可同名升级 |
| W4 | "factory 是 v1 必需维度" | 任何文档若隐含此意 | 3 法人物理一体（一栋楼一个生产体系），factory v1 不必需；4 概念正交（production_unit/purchase_entity/cost_center/legal_entity），cost_center 是 v1 核心 |
| W5 | "在 processes 表加 cost_center_id 等同于在 processes 加班组人工费率主数据" | 任何文档若隐含此意 | **修正措辞（2026-05-09 17:55）**：✅ processes 表加 `cost_center_id`（费用归集外键）是合理的，v1.3 保留 cost_rate_hub_design_v1.md §4.2 的设计；❌ 不要把 `taxonomy.team` 的 `default_minute_rate` 复制到 processes 表（人工费率主数据归 `taxonomy.team`，processes 仅持有 `cost_center_id` 外键 + 自身的 `standard_rate`）。两者是费用归集（cost_center）vs 班组运营（team）两个正交维度。 |
| W6 | "Phase 1 需要造新的 4 个看板" | 任何文档若隐含此意 | 4 个 Insights 看板已上线（/profit/sku /profit/model /profit/channel /returns-rate/sku /returns-rate/channel），Phase 1 = 加成本可信度徽章 + 三视图切换 |
| W7 | "Cost Rate Hub 是从 0 设计的全新模块" | `cost_rate_hub_design_v1.md` v1.0~v1.2 | Hub 是 `LongTailCogsRateStrategy` 雏形（4 层优先级 + history audit）的 superset 扩展；扩展点是加 rate_type + scope_type + UI Tab |
| W8 | "Hub 的可信度治理需要从 0 设计三色徽章 service" | `cost_rate_hub_design_v1.md` v1.2 | 已有 `data_quality_service`（nightly + mark_only + 三色徽章雏形），Hub 在它上面加 `cost_quality` 维度即可 |

### 12.4 后续校准的"减法工作流"（避免再次跨文件风暴）

> 对低优先级（P4/P5）的过往文档，**默认不修改正文**。当某次新功能开发涉及它们时，再做"按需校准"，原则：
>
> 1. **能引用就不复制** — 在新文档里引用"详见 system_capability_inventory.md §X"，而不是把内容复制过来
> 2. **能加注就不重写** — 在被废弃叙述附近加 `> ⚠️ 已废弃，详见 system_capability_inventory.md §12.3 W1`
> 3. **能延期就不立即** — 除非该叙述会误导即将开发的功能，否则可以等到下一次结构性升级时一起处理

### 12.5 接力前的强制 3 步检查（2026-05-09 18:00 修订 — 减少形式主义）

> **修订背景**：之前 8 步硬性勾选清单本身就是"形式大于实用"。新规：**3 步必读** + 5 条按需查阅的软指引。

#### 12.5.1 必读 3 步（任何 Agent 接力前都必须完成）

```
[ ] 1. 读 DOC/agents/agent_rules.md（含 2026-05-09 §2/§7 重大修订：任务粒度区分 + 交接成本约束）
[ ] 2. 读 DOC/costing/handovers/system_capability_inventory.md §12 + §13（本文，事实清单 + 防忘表）
[ ] 3. 读本任务相关的 1~2 份蓝图文档（由派单的任务单"必读上下文"列指明）
```

#### 12.5.2 按需查阅的软指引（不强制全部完成，按本次任务需要选用）

- 设计 Hub / 改 cost_rate_master 表 → 加读 `cost_rate_hub_design_v1.md v1.3`
- 改总图 / 改 PnL 架构 → 加读 `pnl_analytics_module_design.md v1.2`
- 改前端 4 个 Insights 看板 → 加读 `profit_and_returns_analytics_plan_2025_2026_v0_1.md`
- 改 finance 集成 → 加读 `finance_analyzer_integration_v1.md`
- 排查雏形子系统问题 → 在 `known_issues.md` grep 相关 Issue（Issue 23 / Issue 28 / §0.0j）

> **关键**：执行 Agent 在 scope 内拥有完整自主权（详见 `task_distribution_standard.md §0.2`），自主判断要不要扩读。Hub 不强制每项打勾。

---

## 13. v1.3 校准未完事项追踪 + 防忘机制（2026-05-09 17:55 新增）

> **背景**：用户 2026-05-09 17:40 明确指出"你做了 Hub 又把总图给忘了"。本节是为了**永远不再忘**：把"v1.3 校准还没做完的事"显式列出 + 给每件事一个明确的"触发条件" + 让任何后续 Agent 看到表就知道该做什么。
>
> **维护契约**：本表的"状态"列必须在每次相关动作完成时**当轮立刻更新**。如果某项被勾掉就必须把 `状态` 列改为 `✅ <日期 + 完成动作>`，不能空着。

### 13.1 未完事项追踪表

| # | 未完事项 | 触发条件（满足任一就必须立即做） | 当前状态 | 完成定义 |
|---|---|---|---|---|
| **U1** | 校准 `sku_portfolio_management_v1.md` v1.1 → v1.2 | (a) 用户启动"SKU 角色 / 5 类亏损 / 引流款 vs 利润款"功能开发 (b) 用户提及 sku_portfolio 文档 (c) Phase 2 开始 | 🟡 待启动 | 头部升 v1.2 + 加 v1.2 校准段（与 W1~W8 + Hub v1.3 对齐）+ §3.1 关联 cost_rate_master 而非 overhead_rate_master + 元信息升 v1.2 |
| **U2** | 校准 `finance_analyzer_integration_v1.md` v1.1 → v1.2 | (a) 用户启动 finance 集成 / monthly_cost_variance / 多主体合并 (b) 用户提及 finance_analyzer 文档 (c) Phase 1 W4 开始（finance 录入） | 🟢 **2026-05-10 07:40 部分启动**：C1 契约规格书已落地为 `finance_to_costing_c1_contract_v1.md`（含 master_companies canonical 决策 + 5 个 GET API 详细规格 + C2 测试 + C3 SLA + 验收 13 条）。`finance_analyzer_integration_v1.md` v1.1→v1.2 架构层校准延后（按减法工作流，等 finance 实施落地后一起做）| C1 契约 v1.0 上线 + finance 侧 §8.1 5 条 + costing 侧 §8.2 5 条全过 |
| **U3** | 同步 4 份 PnL handovers（pnl_module_handover / pnl_decision_log / pnl_phase_status / pnl_external_reviews/INDEX）v1.2 → v1.3 | (a) 用户启动评审会 / 准备签字 (b) 评审会日期前 1 周 (c) 任何 handover 内容引用 Hub v1.2 设计 | 🟡 待启动 | 4 份头部 v1.2 → v1.3 + 各加"v1.3 校准说明"小节（每份 3~5 行即可）+ pnl_decision_log 加决策 #48「v1.3 校准生效」 |
| **U4** | 同步 `phase0_review_checklist.md` v1.2.1 → v1.3 | (a) 评审会前必须 (b) H4/H5 决策项需要拍板时 | 🟡 待启动 | 头部升 v1.3 + 决策项 H1/H2/H3/H4 改为引用 v1.3 + 新增 H5「采纳系统能力清单 v1.0 + Hub v1.3 + 文档优先级规则」 |
| **U5** | 派 Backend Agent 任务单：Migration 0038 + 扩展 long_tail_strategy_service.resolve_overhead_rate | (a) 评审会通过 v1.3 (b) 用户给开干指令 (c) Phase 1 W2 开始 | ✅ **2026-05-09 完成**（cost_rate_hub_mvp.md 全栈交付）— Migration 0038 PG 双向跑通 + `cost_rate_master` 表 + `resolve_overhead_rate` 4 层链 + KB8 端到端 0.30→0.25 验证 | 任务单完成标准 §4 五条全过 |
| **U6** | 派 Frontend Agent 任务单：LongTailCogsRatePage 扩展 Hub Tab | (a) 与 U5 联动启动 (b) Phase 1 W3 开始 | ✅ **2026-05-09 完成**（同 U5 同 commit）— `LongTailCogsRatePage` 改 2 Tabs（cogs / overhead_rate）+ 新 `OverheadRateTab` CRUD + 试算面板 + `?tab=` URL 同步；老路由保留 + 新增 `/costing/admin/cost-rate-hub` 重定向 | 同 U5 |
| **U7** | 4 个 Insights 看板加成本可信度徽章 + 三视图切换 | (a) 与 U5/U6 联动 (b) Phase 1 W4-W5 开始 | ✅ **A 部分完成**（`badges_mvp.md` 2026-05-09 全栈交付 — 5 个 analytics endpoint 透传 `cost_quality` + 4 看板渲染 🟢/🟡/🔴 Tag + tooltip）；**B 部分（三视图 Tax/Mgmt/Group）待 `cost_center` 主表 + `legal_entity` 录入主数据就绪后单独派单** | A 部分：5 条用户验收标准全过；B 部分：另派单 `frontend_insights_three_views_mvp.md` |
| **U8** | 校准 `pnl_analytics_module_design.md` v1.1 → v1.2（**全员必读总图**） | **🔴 立即** — 全员必读不能等 | ✅ 2026-05-09 17:55 本轮闭环完成 | 头部升 v1.2 + 加 v1.2 校准段 + §0 mermaid 图 shipment_pnl_lines → shipment_costing_results + §1.3 加 5 个雏形子系统 + §3.3 加废弃声明 + 关联清单加 cost_rate_hub_design_v1.md v1.3 + system_capability_inventory.md |
| **U9** | 把 6 份核心文档关联到 DOC/agents/ 运维体系 | **🔴 立即** — 用户明确指出"没关联到运维里" | ✅ 2026-05-09 17:55 本轮闭环完成（workset.md §7.10） | 在 workset.md §7 末尾加 §7.10「6 份核心必读文档（按受众分类）」+ 列出总图/价格指南/转移价手册/SKU 组合/finance 集成/评审清单 |

### 13.2 防忘机制（2026-05-09 18:00 修订 — 5 条硬规则 → 3 条软原则）

> **修订背景**：用户 2026-05-09 17:45 指出"派活 Token > 编码 Token"是规则失败。本次把 5 条硬规则简化为 3 条软原则，移除"每月 1 号扫表"等容易变成形式主义的硬性要求。

#### 13.2.1 核心 3 条软原则（执行 Agent 自主把握）

1. **触发即做**：任何 Agent 接力时扫一次 §13.1 表的"触发条件"列，本次任务触发的 U# **必须当轮做完**（不允许"知道有但不做"）；未触发的不强求。
2. **完成即更新**：任何 v# 升级动作完成时，把对应行状态从 🟡 改为 ✅ + 完成日期。这是给下个接力 Agent 看的，不是为了打卡。
3. **§13 是单一真相**：任何"未完事项"叙述（task_log 待办列、外部评审报告、用户口头交代）若与 §13 表冲突，**以 §13 为准**。新增延后任务必须登记一行（含触发条件 + 完成定义）。

#### 13.2.2 已废弃的硬规则（不再执行）

- ~~"每月 1 号自动重审一次"~~ → 实际从未执行，纯形式主义，废弃。改为：用户启动相关功能时自然触发。
- ~~"任何 v# 升级必须在 6 份联动文档全部勾掉对应行"~~ → 实际是过度联动，按 §12.4 减法工作流处理即可。

### 13.3 v1.3 校准已完成事项（汇总，便于审计）

| 已完成事项 | 完成日期 | 完成位置 |
|---|---|---|
| 系统能力清单 v1.0 + §12（11 份历史已动文档清单）| 2026-05-09 17:30 + 17:45 | system_capability_inventory.md |
| Cost Rate Hub v1.2 → v1.3 | 2026-05-09 17:50 | cost_rate_hub_design_v1.md |
| 总图 pnl_analytics_module_design.md v1.1 → v1.2 | 2026-05-09 17:55 | pnl_analytics_module_design.md |
| 6 份核心文档关联到运维体系（workset.md §7.10）| 2026-05-09 17:55 | workset.md |
| §12.2 文档优先级规则修正（pnl_analytics_module_design P5 → P3）| 2026-05-09 17:55 | system_capability_inventory.md |
| W5 措辞修正（processes 加 cost_center_id 是合理的）| 2026-05-09 17:55 | system_capability_inventory.md |
| **agent_rules.md §2 / §7 + task_distribution_standard.md §0.2 / §3 重大修订** — 区分设计 vs 执行任务粒度 + 给执行 Agent 完整自主权 + 新增"交接成本 ≤ 编码成本"硬约束 + §12.5 8 步检查→3 步 + §13.2 5 条硬规则→3 条软原则 | **2026-05-09 18:00** | agent_rules.md / task_distribution_standard.md / system_capability_inventory.md / workset.md |
| **Cost Rate Hub MVP 全栈大任务单下发**（U5+U6 合并 — 新规则 §3.1 优先大任务）— 含 Migration 0038 SQL 骨架 + 4 层 resolve service 实现 + 前端 Tabs + 接入 bom_generation_service / KB8 实时核价 / 发货台账成本拆分 + 5 条端到端验收标准 + 关键代码定位（不需要再 grep）+ 完整自主权声明（中间过程不汇报）| **2026-05-09 18:05** | `DOC/agents/briefings/cost_rate_hub_mvp.md`（新增 360+ 行）|
| **Cost Rate Hub MVP 全栈交付**（U5 + U6 合并落地 — 新规则首次完整实践）— Migration 0038 落地 PG 生产库（双向验证 + 兼容视图 `long_tail_cogs_rate_strategies` 过滤 cogs）+ ORM 类改名 `CostRateMaster`（保留 `LongTailCogsRateStrategy` alias 兼容老 import）+ 11 字段（rate_type/scope_type/scope_id/rate_basis/source/effective_from/effective_to/data_quality/cost_center_id/legal_entity_id/production_unit_id）+ Hub `resolve_overhead_rate` 4 层 resolve（model > category > cost_center > global > 硬兜底 0.30）+ `bom_generation_service._resolve_overhead_rate` 接 Hub 链 + 前端 2 Tabs（`LongTailCogsTab` 老逻辑不变 + 新 `OverheadRateTab` CRUD/试算/data_quality 徽章）+ 后端 17 新单测全过 + 老 long-tail 27 单测全过（零回归）+ KB8 端到端：模拟 (26.93+7.34) × 0.25 = 8.57 → 折算占比 **20.00%**（vs 旧 23.08%）| **2026-05-09 21:30** | Migration `backend/migrations/versions/0038_cost_rate_master.py` / Service `long_tail_strategy_service.py` / Router `long_tail_strategies.py` / Model `models.py::CostRateMaster` / 前端 `LongTailCogsRatePage.tsx` + `App.tsx` 加 `/costing/admin/cost-rate-hub` 别名 |
| **U7-A Insights 看板成本可信度徽章 MVP 全栈交付**（briefings/`insights_quality_badges_mvp.md` — A 部分落地，B 三视图未做）— **后端**：新建 `cost_quality_service.py`（一次性 dict 查询 → in-memory 4 层 resolve，零 N+1）+ `analytics_service.py` 7 个函数（`profit_by_model/sku/channel`、`returns_rate_by_sku/channel`、`models_summary`、`sales_lines`）每行透传 `cost_quality{level, hit_layer, source, updated_at}` + Pydantic schemas 7 类 item 加 optional 字段（向后兼容）+ 8 新单测（model→green / category→yellow / global→red / hard_fallback→red / aggregate worst-level / pydantic round-trip 全过）；**前端**：新建 `CostQualityBadge.tsx`（Ant Design Tag + Tooltip 显示命中层级 + 来源 + 更新时间 + level 三色高/中/低）+ 4 个 InsightsPage（Profit/Shop/Sales/AfterSales）每张主表加「成本可信度」列（width 110/center）+ 调整 scroll x；KB8（已配 model 级 0.25）显示 🟢「模型级精确」+ 未配模型显示 🔴「全局兜底」/「硬编码 0.30」；性能：`build_overhead_quality_lookup` 1 次 SELECT + `_model_ids_per_period_channel_sku` 1 次 SELECT，零 N+1（5 条 endpoint 请求 ≤ 之前 + 200ms 性能预算内）；frontend `npm run build` 通过；既有 analytics 单测 10/10 无回归 | **2026-05-09 22:00** | Backend: `services/cost_quality_service.py`（新）/ `services/analytics_service.py`（改）/ `schemas.py` / `tests/planner/test_analytics_quality.py`（新）；Frontend: `components/costing/CostQualityBadge.tsx`（新）/ `types/planner.ts` / 4 InsightsPages（仅 U7-A hunks）|

---

## 修订历史

| 版本 | 日期 | 维护人 | 改动摘要 |
|---|---|---|---|
| v1.0 | 2026-05-09 17:30 | PnL/Hub Agent | 首版：基于 backend/src/planner/{routers,services} + frontend/src/App.tsx + Alembic 迁移 + 5 份 Agent 真相文档梳理出系统能力清单。本文将作为后续 PnL/Hub Agent 接力第 1 份必读文档。 |
| v1.0+§12 | 2026-05-09 17:45 | PnL/Hub Agent | 追加 §12「历史已动 11 份 PnL/Hub 文档全清单 + v1.3 校准生效后的文档优先级规则」。解决"Agent 反复忘记之前动过哪些文档→重复造轮子"的根因。固化 8 条被废弃叙述（W1~W8）+ "减法工作流"+ "5 步强制检查"。 |
| v1.0+§13 | 2026-05-09 17:55 | PnL/Hub Agent | 用户指出"做了 Hub 又把总图给忘了"。本次修正：(1) §12.2 把总图 pnl_analytics_module_design 从 P5 提升到 P3（全员必读级别）；(2) W5 措辞精确化（processes 加 cost_center_id 合理）；(3) 新增 §13「v1.3 校准未完事项追踪 + 防忘机制」9 项 U# 表 + 5 条硬规则 + 已完成事项审计表，**永远不再忘**。 |
| v1.0+§13 修订 | 2026-05-09 18:00 | Hub Agent | 用户指出"派活的 Token 费用 > 实际写代码的费用"是规则失败。本次修订：(1) §12.5 8 步硬性检查 → 3 步必读 + 5 条按需软指引；(2) §13.2 5 条硬规则 → 3 条软原则（移除"每月 1 号扫表"等容易变成形式主义的硬性要求）。配合 `agent_rules.md §2/§7` + `task_distribution_standard.md §0.2/§3` 重大修订一起生效。**此后执行 Agent 在 scope 内拥有完整自主权，不需要每小步回 Hub 汇报。** |
| v1.0+§13 + Hub MVP | 2026-05-09 21:30 | Fullstack Agent | Cost Rate Hub MVP 全栈交付完成（U5/U6 → ✅）。本次更新：(1) §13.1 把 U5/U6 状态从 🟢 派单已下发 改为 ✅ 完成；U7 由 🟡 暂留 改为 🟡 可启动（Hub MVP 已验证）。(2) §13.3 已完成事项审计追加 1 行（21:30 Hub MVP 全栈交付明细）。(3) 修订历史追加本行。**所有 5 条用户验收标准全过**（Migration 双向 / POST overhead_rate / KB8 折算 23%→20% / bom 接入 / 前端 Tabs）；后端 17 新单测 + 27 老单测无回归。 |
| v1.0+§13 + Hub MVP + U7-A | 2026-05-09 22:00 | Fullstack Agent | U7-A Insights 看板成本可信度徽章 MVP 全栈交付完成（U7 → ✅ A 部分完成，B 三视图待主数据）。本次更新：(1) §13.1 U7 状态从 🟡 可启动 改为 ✅ A 部分完成 + 显式标注 B 三视图（Tax/Mgmt/Group）等 `cost_center` + `legal_entity` 主数据就绪后单独派单；(2) §13.3 追加 1 行（22:00 U7-A 全栈交付明细）；(3) 修订历史追加本行。**5 条用户验收标准对勾**：① 4 看板「成本可信度」列 ✅；② tooltip 命中层级+来源+更新时间 ✅；③ KB8 🟢「模型级精确」(配 0.25 model 级) ✅（端到端测脚本验证）；④ 未配模型 🔴「全局兜底」/「硬编码 0.30」 ✅；⑤ 性能：`build_overhead_quality_lookup` 1 SELECT + `_model_ids_per_period_channel_sku` 1 SELECT 批量查 dict 方案落地，零 N+1 ✅。后端 8 新单测 + 既有 analytics 10 单测全过（零回归）；frontend build 通过。|
