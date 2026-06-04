# PnL 模块接力交接文档（活文档 / Living Doc）

> **状态**：v1.2 已立项，Phase 0 评审准备中，Phase 1 编码尚未启动
> **本文档定位**：PnL（盈亏分析专业版）模块的**唯一接力总入口**。任何新接手的人或 AI Agent 第一份要读的文档。
> **维护规则**：每次有重大变化（决策 / 进度 / 阻塞 / 联调）必须更新对应的子文档（见 §2），主文档 §3 当前状态每周更新一次。
> **最近更新**：2026-05-09（v1.2，加 Manus 第三+第四轮采纳 + 现状审计校准）

---

## 0. 30 秒电梯总结

**我们在做什么**：把 ai-costing 升级为「**专业版盈亏分析模块**」，让老板每天能看到昨天发出去的订单按 SKU/店铺/Cost Center/品类**真实赚多少 / 亏多少 / 亏在哪**。

### 0.1 业务事实校准（v1.2 必读）

| 事实 | 对架构的影响 |
|---|---|
| **3 个工厂法人物理一体在一栋楼**，是 1 个生产体系 | **Hub 不分 factory；不会出现"同一商品两个工厂做"** |
| 1 一般纳税人 + 2 小规模 | 部分材料采购按法人分流 → Stage 2 加 `purchase_entity_id` 字段（不入 Hub） |
| 4 个店铺主体单独报税 + 工厂 3 法人单独报税 | Phase 2 三视图（FI/CO/合并）才需要 `legal_entity` |
| 工人按**班组**分（饰品 / 布艺），按**品类**完全可分开 | v1 Hub 用 `cost_center` 做"班组的财务侧抽象" |
| 物料按 SKU 完全可分 | v1 直读 BOM × 物料价（不入 Hub）|
| 固定费用合在一起 | v1 总制造费率治理；Phase 2 拆 4 个固定费用池 |

### 0.2 4 个组织概念正交拆分（来自 Manus 第四轮评审 / 决策 #42）

> 不再用单一 `factory` 字段表达 4 件事，拆开建模：

- `production_unit_id`：实际生产单元（v1 仅 1 个默认值；Phase 2 多场地时用）
- `purchase_entity_id`：采购法人（一般纳税人 / 小规模 A / 小规模 B；Stage 2 物料端用）
- `cost_center_id`：费用中心（**v1 Hub 核心维度**，5-7 个班组 + 公共 + 行政）
- `legal_entity_id`：税务/财务法人（Phase 2 三视图用）

### 0.3 核心交付（2026-05-09 v1.2 修订）

- **Phase 1 核心 = Cost Rate Hub v1.2**（成本费率与费用归集中枢，决策 #34/#43-#47）
- **复用现有 `processes` + `process_modules` + `materials` + `virtual_materials`**（8456 行 UI / 5 张后端表）
- **新建 3 张表**：`cost_center`（5-7 行）+ `overhead_rate_master` + `cost_rate_history`
- **改造 1 张表**：`processes` 加 `cost_center_id` FK + `trust_level`
- **优先级链 v1 实做 4 层**：model > category > cost_center > global（schema 留 8 层枚举）
- **Stage 2 物料端 4 字段**（决策 #45）：`materials` 加 `purchase_entity_id` / `tax_included_flag` / `tax_rate` / `price_source` / `effective_from`
- **Hub 控制台 8 面板架构**（v1 实做 Tab 1+2，留 6 个槽位 Stage 2/3 加）
- 物料成本走"做稳做实"路线（不进 Hub 主表，决策 #36）
- 人工 + 制造费走"治理路线"（经 Hub，财务月度调节）
- 专业能力（sku_role / volume_tier / 学习曲线 / 单位时间毛利）通过 Hub 接口扩展（决策 #35），算法层不动
- **三阶段顺序**：Stage 1 Hub 骨架（2.5-3 周）→ Stage 2 物料做实（1 周）→ Stage 3 专业能力按需扩展（无限期）
- 后续：发货利润事实表 `shipment_pnl_lines` + cost_snapshot 锁版本 + GM1/GM2/NP3 三层利润 + 5 类亏损分类 + 多主体核算

**生命周期**：1 年长周期，5 个 Phase，当前在 Phase 0（评审）。

**最大当前阻塞**：评审会未召集（finance C1/C2/C3 + Hub H1/H2/H3/**H4** 7 个决策待签字，详见 §3）。

---

## 1. 你必须先读的 4 份文档（按顺序，40 分钟读完）

| # | 文档 | 路径 | 为什么读 |
|---|---|---|---|
| 1 | 总图（v1.1） | [pnl_analytics_module_design.md](../blueprints/pnl_analytics_module_design.md) | 整体架构、5 个 Phase 节奏、核心表 schema |
| 2 | **Cost Rate Hub v1.2 设计（Phase 1 的核心）** | [cost_rate_hub_design_v1.md](../blueprints/cost_rate_hub_design_v1.md) | Phase 1 实际核心交付物。读完这份再去看其他设计文档 |
| 3 | **外部评审 §4 §5（必读 v1.2 来源）** | [pnl_external_reviews/INDEX.md](./pnl_external_reviews/INDEX.md) | Manus 第三+第四轮评审是 v1.2 设计变更的核心依据 |
| 4 | Phase 0 评审清单（v1.2） | [phase0_review_checklist.md](./phase0_review_checklist.md) | 8 个核心决策 + 3 个 finance 契约 + 4 个 Hub 决策（含 H4） |
| 5 | 本文档下面的 §3 当前状态 | 见下 | 这周到底卡在哪 |

读完这 4 份，你就能跟任何角色对话不掉链子。需要细节再去看 §6 文档地图。

---

## 2. 接力文档体系（5 份，本文档是入口）

| 文档 | 用途 | 更新频率 | 谁更新 |
|---|---|---|---|
| **本文档** `pnl_module_handover.md` | 接力总入口 + 当前状态摘要 + 模块边界 | 每周 | 当前实施负责人 |
| [`pnl_decision_log.md`](./pnl_decision_log.md) | 设计决策时间线（每个决策一行） | 决策发生时 | 决策人 |
| [`pnl_phase_status.md`](./pnl_phase_status.md) | 进度看板 + 阻塞清单 | 每周 | PM / 实施负责人 |
| [`pnl_incident_log.md`](./pnl_incident_log.md) | 线上异常 / 数据修正 / 报警事件 | 事件发生时 | 处理人 |
| [`pnl_external_reviews/INDEX.md`](./pnl_external_reviews/INDEX.md) | 外部评审报告归档索引 | 评审到来时 | 评审协调人 |

---

## 3. 当前状态（每周更新）

### 3.1 Phase 进度

| Phase | 名称 | 状态 | 预计 / 实际起止 | 负责人 |
|---|---|---|---|---|
| **Phase 0** | 口径文档 + 评审 | 🔵 文档定稿 v1.1，等评审会 | 2026-05-08 ~ 2026-05-15（预） | 文档：本 Agent；评审：老板召集 |
| Phase 1 | 订单利润作战室 MVP | ⚪ 待启动（需 3 契约签字） | 评审后 3-4 周 | 待定 |
| Phase 2 | 月度差异 + 成本优化机会榜 | ⚪ 待启动 | Phase 1 后 1-2 周 | 待定 |
| Phase 3 | 店铺组合工作台 | ⚪ 待启动 | Phase 2 后 2-3 周 | 待定 |
| Phase 4 | AI 周报 / NLQ / 优化建议 | ⚪ 待启动 | Phase 3 后 2 周 | 待定 |
| Phase 5 | 决策工作流（自动调价/下架） | 后置 | 待评估 | — |

### 3.2 当前阻塞（按严重度排序，2026-05-09 重排）

| # | 阻塞 | 影响 | 解锁条件 | 责任人 |
|---|---|---|---|---|
| **0** | **🔴 KB8 单 SKU 反向核算诊断未启动**（决策 #33） | **整个 Phase 1 数据可信度无基线** | 1-2 天对账（不写代码）| 老板 + 财务 + 工厂厂长 + Agent |
| 1 | **finance 3 个前置契约未签字（C1/C2/C3）** | Phase 1 不能启动 | 评审会现场签字 | 集团财务 + 双方技术负责人 |
| 2 | **finance 端 7 法人 UUID + 规范全称对照表未交付** | C1 契约具体落不下来 | 评审后 3 天内交付 | finance 团队 |
| 3 | **finance 4 个核心接口 pytest 覆盖近零** | C2 契约风险高 | 评审后 1 周内补完（3-8 人日） | finance 技术 |
| 4 | **HR 还没有出 `employee_attribution` 全员归属初稿** | 决策 6 签字延迟 | 评审会前 3 天交付 | HR + 工厂厂长 + 运营负责人 |
| 5 | **跨法人共享开支分摊基准（5 类首批）未确认** | 决策 6.b 签字依赖 | 评审会现场拍板 | 集团财务 + 老板 |
| **6** | **🟡 cost_center 初稿清单未老板签字（H4，v1.2 新增）** | Hub v1 启动后无法做 processes → cost_center 数据迁移 | 评审会前 3 天工厂厂长出初稿；评审会现场老板签字 | 老板 + 工厂厂长 |

### 3.3 本周完成

- 2026-05-09：v1.1 文档全套定稿（6 份核心 + 2 份外部评审采纳 + finance 仓库实地调查）
- 2026-05-09：Phase 0 评审清单升级到 8 个核心决策（含 6.b 管理会计深化 + 6.c finance 3 契约）
- 2026-05-09：模块边界划清规划（见 §4）+ 接力文档体系初版建立
- 2026-05-09 下午：现状审计 4 个现有页面（ProcessesPage 1027 / ProcessModulesPage 3039 / MaterialMasterPage 1956 / VirtualMaterialsPage 2434 行 = 8456 行 UI），确认 Hub v1 应复用而非重建
- 2026-05-09 下午：Manus 第三轮（成本参数Hub设计建议）+ 第四轮（factory 维度修正）评审纳入 → cost_rate_hub_design v1.0 升级为 **v1.2**
- 2026-05-09 下午：决策 #40-#47 入 decision_log；INDEX 加 §4 §5；handover §0 加业务事实 + 4 概念正交

### 3.4 下周计划

- 评审会召集 + 现场签字（含 finance C1/C2/C3 + Hub H1/H2/H3/**H4** 共 7 个新决策）
- 评审后 3 天：finance 团队交付主体对照表（C1）
- 评审后 7 天：finance 团队 4 个接口 pytest 入仓（C2）
- 评审后 7 天：双方鉴权 token 互发（C3）
- 评审后 5 天：财务整理 Hub 全局默认 2 个费率初始值（H1）
- **评审会前 3 天**：工厂厂长出 cost_center 初稿 6-7 行（H4）
- 全部签字达成后：启动 Phase 1 = **Cost Rate Hub Stage 1**（详见 cost_rate_hub_design_v1.md §9）

---

## 4. 模块边界（v1.1 已采纳"在仓库内强划边界"方案）

> **决策背景**：拒绝立即拆独立项目（理由见 `pnl_decision_log.md` 2026-05-09 决策 #5），但必须在 ai-costing 仓库内强划边界，方便 Phase 3 末重新评估是否拆分。

### 4.1 后端边界

```text
backend/src/pnl/                              # PnL 模块根目录（Phase 1 编码时建立）
├── __init__.py
├── README.md                                 # 模块责任声明（必读）
│
├── cost_rate_hub/                            # Stage 1 核心子模块（Phase 1 主交付，v1.2）
│   ├── __init__.py
│   ├── README.md                             # Hub 模块责任声明
│   ├── models.py                             # cost_center / overhead_rate_master / cost_rate_history ORM
│   ├── services/
│   │   ├── cost_center_service.py            # cost_center CRUD + 与 processes 的映射
│   │   ├── rate_resolver_service.py          # 4 层优先级链查询（算法层调这个）
│   │   ├── rate_management_service.py        # 增/改/历史/撤销
│   │   ├── labor_summary_service.py          # 聚合现有 processes 表按 cost_center
│   │   └── quality_summary_service.py        # 给 Insights 看板用
│   ├── routers/
│   │   └── cost_rate_hub.py                  # /api/cost-rate-hub/v1/*（cost-centers / overhead-rates / labor-summary / resolve / quality-summary）
│   └── schemas/
│       └── cost_rate.py
│
├── domain/                                   # 后续 Phase 加
│   ├── shipment_pnl_line.py
│   ├── cost_snapshot.py
│   └── loss_classification.py
├── services/
│   ├── shipment_pnl_compute_service.py
│   ├── cost_snapshot_service.py
│   ├── allocation_service.py
│   └── pnl_view_service.py
├── routers/
│   └── pnl.py
├── schemas/
│   └── pnl.py
└── workers/
    ├── shipment_pnl_worker.py
    └── volume_tier_selector_worker.py        # Stage 3 加：月度自动选档
```

**核心改造点**（连接 Hub 与现有代码，v1.2）：
- `backend/src/planner/services/bom_generation_service.py:_resolve_overhead_rate` → 改为调 `pnl/cost_rate_hub/services/rate_resolver_service.resolve('overhead_rate', ...)` 走 4 层优先级链（model > category > cost_center > global）
- `backend/src/planner/services/bom_generation_service.py:_compute_process_costing` → **不重写**，仍读现有 `processes.standard_rate`，但响应里加 `cost_center_id` + `trust_level` 透传
- `backend/src/planner/services/shipment_import_service.py:写 ShipmentCostingResult 处` → 加 `cost_quality` 字段（含 rate_id + source + trust_level）+ **已结账月保护触发器**
- `backend/src/planner/models.py:Process` → 加 `cost_center_id` FK + `trust_level` 字段（migration 时一次性从 `team_name` 映射到 `cost_center_id`）

**与现有 4 个页面的关系**（v1.2 重要边界）：
- `frontend/src/pages/costing/ProcessesPage.tsx` (1027 行) → **不动**，但保存时通过 service 层触发写 `cost_rate_history`；前端加显示"当前归属 cost_center: ___"
- `frontend/src/pages/costing/ProcessModulesPage.tsx` (3039 行) → **完全不动**
- `frontend/src/pages/costing/MaterialMasterPage.tsx` (1956 行) → v1 不动，Stage 2 加 4 个税务/采购字段编辑控件
- `frontend/src/pages/costing/VirtualMaterialsPage.tsx` (2434 行) → **完全不动**
- 新建 `frontend/src/modules/pnl/cost-rate-hub/CostRateHubOverviewPage.tsx` → Hub Tab 1 总览（聚合显示 4 个现有页面 + 新表的费率视图）

**模块导入纪律**（写到 `pnl/README.md`）：
- ✅ pnl 模块**可以** import：`backend/src/planner/integrations/finance_analyzer/`、`backend/src/planner/models/sku_master.py`、`shipment_lines.py`、`material.py`、`processes.py`、`process_modules.py`（只读）
- ❌ pnl 模块**不能** import：planner routers / planner UI service / 任何与"打样 / 标准模型编辑 / 物料编辑"相关的代码
- ❌ planner 其他模块**不能** import pnl 内部细节（只能调 pnl 暴露的 service 接口）

### 4.2 前端边界

```text
frontend/src/modules/pnl/                     # PnL 前端模块根目录
├── README.md
│
├── cost-rate-hub/                            # Stage 1 核心子模块（Phase 1 主交付）
│   ├── README.md
│   ├── pages/
│   │   ├── CostRateHubOverviewPage.tsx       # Tab 1 总览（路由 /costing/cost-rate-hub）
│   │   └── CostRateEditorPage.tsx            # Tab 2 编辑器
│   ├── components/
│   │   ├── TrustBadge.tsx                    # 🟢🟡🔴 三色徽章（公共组件，Insights 也用）
│   │   ├── RateScopeSelector.tsx
│   │   ├── RateHistoryDrawer.tsx
│   │   └── ImpactPreviewCard.tsx
│   └── api/
│       └── cost-rate-hub-client.ts
│
├── pages/                                    # 后续 Phase 加
│   ├── PnlLeaderboardPage.tsx
│   ├── SkuProfitDetailPage.tsx
│   ├── CostOptimizationPage.tsx
│   └── ShopPortfolioWorkbenchPage.tsx
├── components/
│   ├── PnlViewSwitcher.tsx
│   ├── ProfitWaterfall.tsx
│   └── LossClassificationBadge.tsx
└── api/
    └── pnl-client.ts
```

**改造现有 4 个 Insights 页面**（不挪位置）：
- `pages/costing/ProfitInsightsPage.tsx` 顶部加可信度警示横条 + 列里加 `<TrustBadge>` 徽章
- `pages/costing/ShopInsightsPage.tsx` 同上
- `pages/costing/SalesInsightsPage.tsx` 同上
- `pages/costing/AfterSalesInsightsPage.tsx` 暂不（不显示成本）

### 4.3 数据库边界

PnL 模块**专属表**（前缀 `pnl_*` 或归在新 schema）：
- `shipment_pnl_lines` / `cost_snapshot` / `cost_pool_master` / `cost_allocation_rule` / `legal_entity_alias_map` / `category_overhead_rate_history` / `monthly_cost_variance` 等

PnL 模块**只读**的表：
- `sku_master` / `shipment_lines` / `material` / `product_model_*`（这些是 planner / 打样模块的）

PnL 模块**写入**会触发其他模块的表：
- 没有（保持单向：pnl 消费打样数据，不反向写）

### 4.4 何时重新评估"是否拆独立项目"

满足**任意 2 条**才考虑拆：
- pnl 模块代码量 > ai-costing 总代码 40%
- pnl 团队 ≥ 2 个独立工程师
- pnl 发版独立性诉求 ≥ 4 次/月
- 出现"pnl 改动需要 freeze 整个 ai-costing 部署"的痛点

**评估时点**：Phase 3 末（约 6-8 周后）。

---

## 5. 跟我无关的事（防止越界）

PnL 模块**不做**以下事情：

| 不做的事 | 该谁做 |
|---|---|
| 单据级会计核算（凭证 / 总账 / 应收应付） | finance-analyzer |
| 库存周转 / 物流仓配 / WMS | 吉客云 / 外部 WMS |
| 精细 SEO / 广告投放配置 | 各电商平台后台 |
| OKR / KPI 考核管理 | HR 系统 |
| 物料主数据维护 | ai-costing 的物料管理模块 |
| 标准模型 / BOM 编辑 / 打样工艺 | ai-costing 的 planner 模块 |
| 订单创建 / 发货执行 | 吉客云 / 平台 |

---

## 6. 文档地图（v1.1）

### 6.1 设计文档（蓝图）

| 文档 | 路径 | 受众 |
|---|---|---|
| 总图 | [pnl_analytics_module_design.md](../blueprints/pnl_analytics_module_design.md) | 全员 |
| **Cost Rate Hub v1（Phase 1 核心）** | [cost_rate_hub_design_v1.md](../blueprints/cost_rate_hub_design_v1.md) | 全员（必读） |
| 价格计算 v2.1 | [price_calculation_guide.md](../manuals/guides/price_calculation_guide.md) | 财务 + 工厂 |
| 内部转移价手册 | [transfer_pricing_handbook.md](../manuals/transfer_pricing_handbook.md) | 财务 + 老板 |
| SKU 组合管理 v1.1 | [sku_portfolio_management_v1.md](../blueprints/sku_portfolio_management_v1.md) | 运营 + 老板 |
| finance 集成方案 v1.1 | [finance_analyzer_integration_v1.md](../blueprints/finance_analyzer_integration_v1.md) | 技术 + finance |

### 6.2 评审文档

| 文档 | 路径 | 受众 |
|---|---|---|
| Phase 0 评审清单 v1.1 | [phase0_review_checklist.md](./phase0_review_checklist.md) | 评审会全员 |

### 6.3 接力 / 运维文档（本系列）

见 §2 表格。

### 6.4 PDF 镜像（评审会派发）

`DOC/基础表单/Phase0_*.pdf` 共 6 份（v1.1）

---

## 7. 联系人 + 责任矩阵

| 角色 | 责任 | 负责人 | 是否签字必须 |
|---|---|---|---|
| 项目发起人 | 拍板路线 + 资源 | 老板 | ✓ |
| 集团财务负责人 | 间接费科目 + 4 池 + 分摊基准 | TBD | ✓ |
| 代账会计 | 科目分类合规 | TBD | ✓ |
| 工厂总账 | 班组 + 效率系数 + 成本中心 | TBD | ✓ |
| 工厂厂长 | `employee_attribution` 工厂端 | TBD | ✓ |
| 集团运营负责人 | 平台扣款 + SKU 角色 + 5 类亏损规则 | TBD | ✓ |
| 各店铺运营 | 店铺组合计划（Phase 3） | 多人 | Phase 3 |
| 采购负责人 | 物料幅宽 + 市场价对标 | TBD | ✓ |
| HR 负责人 | `employee_attribution` 维护机制 | TBD | ✓ |
| 班组长代表 | 班组工时口径 | TBD | ✓ |
| 税务 / 合规顾问 | 多主体口径分离 + 关联交易 | TBD | ✓ |
| finance-analyzer 技术负责人 | 3 个契约（C1/C2/C3）+ API 颁发 | TBD | ✓ |
| ai-costing 技术负责人 | 实施可行性 + 双向 SLA 承诺 | TBD | ✓ |
| **当前实施负责人** | 主文档 + 进度看板更新 | 待 Phase 0 评审后任命 | — |

---

## 8. 已废弃方案（防止后人重复讨论）

详细决策见 [`pnl_decision_log.md`](./pnl_decision_log.md)，这里只列**废弃**：

- ❌ **在 finance 端建 `management_accounting_adjustment` 表** → 重复建设（finance 已有按主体三表 + ai-costing 已有 `cost_allocation_rule`）
- ❌ **现在拆独立项目** → finance ↔ ai-costing 双向耦合已是最大风险，再加新项目变三向耦合
- ❌ **Phase 1 一上来做组合健康度评分 / 矩阵 / 货架模拟** → MVP 收敛后延后到 Phase 3
- ❌ **Phase 1 制造费率统一 1 个工厂费率（不分品类）** → 布艺 vs 饰品工艺差距 10 倍，必须 Phase 1 就分（决策 6）
- ❌ **硬卡 finance 三表测试通过才启动 Phase 1** → 双向耦合下硬卡 = 卡死自己；改为 3 个具体契约（C1/C2/C3）
- ❌ **`shipment_profit_fact` 加 `intercompany_elimination_flag` 字段** → Phase 1 工厂还没真按转移价开票，加了用不上
- ❌ **`allocation_rule_version` 直接落 `shipment_pnl_lines`** → 已通过 `cost_snapshot.material_price_version` 等版本号实现追溯
- ❌ **每条 pnl_line 加 `management_adjustment_amount` 字段** → Phase 2 用 `monthly_variance_allocated` 已覆盖；Phase 1 不必每单算调整金额（性能差）
- ❌ **Phase 1 顺序：先做决策语言（GM1/GM2/NP3、5 类亏损）→ 最后试跑数据** → 数据不可信下决策语言只会放大错误。**新顺序：数据治理优先，决策语言后置**（决策 #30）
- ❌ **Phase 1 新建 `shipment_pnl_lines` 表 + 新建 PnL 看板页面** → 现状审计发现 `shipment_costing_results` 表（migration 0027）+ 4 个 Insights 看板页面已生产，4170 行前端代码已落地。Phase 1 改为**增量改造**（决策 #29）
- ❌ **不加可信度标签直接展示数字** → 用户会以为"数字 = 真相"。**新方法论：每个数字旁加 🟢真实 / 🟡估算 / 🔴默认 三色徽章**（决策 #31）

---

## 8.b 数据可信度治理路线（决策 #30-#33 的展开）

> 这是 Phase 1 的**新核心**，2026-05-09 老板拍板"数据不可信 = 一切归零"后确立。
> 详细 Excel 模板与对账方法见后续 `DOC/costing/handovers/kb8_reverse_audit_template.md`（待建）。

### 8.b.1 当前 KB8 三段成本的预期偏差（基于工程审计）

| 维度 | 当前算法 | 预期偏差 | 严重度 |
|---|---|---|---|
| **物料单价** | BOM 写死价（可能 3 个月没更新） | ±10-30% | 🔴 高 |
| **物料用量** | BOM 配置（损耗率经验值，常漏辅料） | ±10-20% | 🟡 中 |
| **班组工时** | 工艺模板预设（无真实计时） | 高 20-50% | 🔴 极高 |
| **班组单价** | 月工资 / (26×8×60×0.85)（**不含社保福利公积金**） | 低约 40% | 🔴 极高 |
| **制造费率** | 默认 0.3 写死 | ±30-100% | 🔴 极高 |

**最致命的问题**：班组单价偏低 40% × 班组工时偏高 30% → 巧合下"总人工成本看起来对"，但单 SKU 维度全错 → 决策必错。

### 8.b.2 治理路线（4-6 周）

| 周 | 动作 | 谁做 | 产出 |
|---|---|---|---|
| W0（诊断） | KB8 反向核算 | Agent + 财务 + 工厂 | 4 个口径的真实偏差报告 |
| W1 | 制造费率：finance 反推 worker 替换默认值 | finance + ai-costing | 月度反推 cron + 替换 |
| W2 | 班组单价：finance 全口径反推（含社保福利公积金） | finance + ai-costing | 全口径单价表 |
| W3 | 物料单价：接采购系统 / 月度加权平均 | 采购 + ai-costing | 价格更新 worker |
| W4 | BOM 用量审计 | 工厂 + ai-costing | 修后的 BOM |
| W5 | 可信度徽章上线 | ai-costing | 4 个 Insights 页面增量 |
| W6 | cost_snapshot 锁版本 + monthly_cost_variance | ai-costing | 防漂移机制 |

### 8.b.3 可信度徽章规则

- 🟢 **真实** — 来自 finance 反推 / 真实交易，可直接用于决策
- 🟡 **估算** — 基于历史平均 / 上月反推，仅用于趋势观察
- 🔴 **默认** — 写死值 / 未校准，**不可用于决策**
- 综合可信度 < 80% 时，前端"砍 SKU / 调价"决策按钮**自动禁用**

### 8.b.4 给后人的提示（最关键的 1 句）

> **看到现有 4 个 Insights 页面的数字时，第一件事不是"分析数字"，而是"看徽章颜色"**。如果还看到大量 🔴 → 立即停止决策动作，回去做数据治理。

---

## 9. 给新 Agent 的快速行动指引

### 9.1 如果你被叫来做 X，请先看 Y，避开 Z

| 你的任务 | 先看 | 避开 |
|---|---|---|
| 改成本计算公式 | `price_calculation_guide.md` v2.1 + `pnl_decision_log.md` 决策 #1 | 不要碰 finance 端代码（口径在我们这边定） |
| 改 SKU 决策规则 | `sku_portfolio_management_v1.md` §1.4 + 本文档 §8 已废弃 | 不要复活组合健康度评分（Phase 3 才做）|
| 接 finance 新接口 | `finance_analyzer_integration_v1.md` §3 + §9 | 不要绕过 `legal_entity_alias_map`（C1 契约要求） |
| 加表 / 加字段 | `pnl_analytics_module_design.md` §3 + 本文档 §4.3 | 不要在 planner 里加 pnl 表，要在 `backend/src/pnl/` 下 |
| AI 相关功能 | 别看了，Phase 4 才做 | 不要预设 AI 早做（外部评审明确 P4）|
| 性能优化 | `pnl_analytics_module_design.md` §6 | 不要先优化没跑过的代码 |
| 写迁移脚本 | 现有 alembic migration | 不要直接 ALTER TABLE 生产库 |
| 紧急修线上数据 | `pnl_incident_log.md` 找历史先例 | 不要 silent 修复，必须留 incident 记录 |

### 9.2 你接手前必须问当前实施负责人的 5 个问题

1. **3 个 finance 契约是否已经签字？**（如未签 → Phase 1 不能启动）
2. **当前在哪个 Phase？最大阻塞是什么？**（看 §3）
3. **本周 / 上周有没有重大决策变更？**（看 `pnl_decision_log.md` 最新 5 条）
4. **有没有线上 incident 在调查？**（看 `pnl_incident_log.md` 状态 = open 的）
5. **你接手要做的事在 §9.1 表里能找到吗？找不到先回来确认**

### 9.3 你做完事后必须更新

- 决策类 → 写到 `pnl_decision_log.md`
- 进度类 → 更新 `pnl_phase_status.md` + 本文档 §3
- 异常类 → 写到 `pnl_incident_log.md`
- 边界变化 → 更新本文档 §4
- 废弃方案 → 写到本文档 §8

---

## 10. 元信息

| 项 | 值 |
|---|---|
| 文档版本 | **v1.2** |
| 创建日期 | 2026-05-09 |
| 维护节奏 | 每周一次 + 重大事件随时 |
| 写作约定 | 每个 Phase / 重大决策 必须有日期 + 责任人 + 链接到子文档 |
| 失效条件 | 项目终止 / Phase 5 全部上线后 6 个月 |
| 上一版 | v1.1 → v1.2 |
| v1.2 更新摘要 | (1) §0 加业务事实校准 + 4 概念正交；(2) §0 升级为 v1.2 三阶段；(3) §1 必读文档加 Hub v1.2 + 外部评审 INDEX；(4) §3.2 加阻塞 #6（H4 cost_center 初稿）；(5) §3.3/3.4 加现状审计完成 + 评审会 7 决策；(6) §4.1 cost_rate_hub 子模块改为 3 张新表；(7) §4.1 加现有 4 页面边界 |

---

*本文档是 PnL 模块的活文档，请保持更新。如果你读到这里发现 §3 状态超过 14 天没动 → 立即询问当前实施负责人是否项目暂停了。*
