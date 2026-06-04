# Cost Rate Hub — 成本费率与费用归集中枢设计 v1.3

> **状态**：v1.3 已采纳系统能力清单 v1.0（2026-05-09 立项；2026-05-09 二次校准；2026-05-09 17:50 三次校准 v1.3）
> **定位**：Phase 1 的核心交付物，**替代**之前规划的"直接接 finance 反推"方案
> **核心思想**：**先做平台，再做能力**。Hub v1 只做骨架（最小可行），所有"专业能力"通过 Hub 接口扩展，算法层不动
> **关键约定**：物料成本**一期不进 Hub**（直接从 BOM + 物料台账读，做稳做实）；人工 + 制造费**全部经 Hub** 治理；Stage 2 物料端补 4 个税务/采购字段后接入 Hub 价格管理

---

## -1. v1.3 关键校准（**任何后续 Agent 接力前必读** — 替代 v1.2 哪些段落）

> **本节不可删**。本节是 v1.3 校准对 v1.2 设计的"显式纠错与升级"。任何 PnL/Hub 文档（包括 v1.1 蓝图、v1.2 handovers、外部评审）若与本节冲突，**以本节为准**。
>
> 先决条件文档：`DOC/costing/handovers/system_capability_inventory.md` v1.0+§12（**首读**）；`DOC/agents/state.md` + `DOC/agents/known_issues.md`（按需 grep）。

### -1.1 v1.3 相对 v1.2 的 5 项结构性变化

| # | v1.2 错的或不精确的设计 | v1.3 校准为 | 影响章节 |
|---|---|---|---|
| C1 | "Phase 1 必须新建 `overhead_rate_master` 表" | **扩展现有 `long_tail_cogs_rate_strategies` 表**（已有 4 层优先级 + history audit + resolve API + UI），加 `rate_type`（cogs/labor_per_minute/overhead_rate）+ `scope_type`（model/category/cost_center/global）+ 改名为 `cost_rate_master`（保留 long-tail 兼容视图） | §0.3 / §1.1 / §4.3 / §8 / §9 |
| C2 | "新建 `/costing/cost-rate-hub` 路由 + 从 0 造 Tab 1/Tab 2 页面" | **扩展现有 `/costing/admin/long-tail-cogs-rate` 页面（`LongTailCogsRatePage.tsx`）**，加 Hub 总览 Tab + 费率编辑器 Tab，路由可同步改名为 `/costing/admin/cost-rate-hub`（保留旧路由 301 重定向） | §7 / §8 |
| C3 | "三色徽章需要从 0 造新 service" | **复用现有 `data_quality_service`**（已有 nightly + mark_only + 三色徽章雏形）加 `cost_quality` 维度（material/labor/overhead 三个 enum） | §3 末新增 §3.2 / §8 |
| C4 | "Hub 与 SKU 治理状态机无关" | **成本可信度徽章必须与 SKU 治理 4 态对齐**：`auto_bound`=🟢 / `pending_model`=🟡 / `do_not_model`=🔴（长尾兜底） | §5 末新增 §5.4 |
| C5 | "Stage 3 在 `shipment_pnl_lines` 加 `unit_minute_margin`"（W2 错误：Phase 1 根本不应该新建 `shipment_pnl_lines` 表） | Stage 3 在**现有 `shipment_costing_results.metadata_json`** 加 `unit_minute_margin`；盈亏分析 SQL view 直接 JOIN `shipment_costing_results`（迁移 0027 已落地） | §13 |

### -1.2 v1.3 明确"废弃"的过往叙述（与 system_capability_inventory.md §12.3 W1~W8 一致）

| W# | 废弃叙述 | 替代叙述 |
|---|---|---|
| W1 | "23% 是真实制造费率，需要反推" | 23%=30%/(1+30%)=23.08% 是数学折算占比；30% 是 `bom_generation_service.py:2047 _resolve_overhead_rate` 的兜底，需要 Hub 提供 model/cost_center 维度的真实 overhead_rate 覆盖 |
| W2 | "Phase 1 必须新建 `shipment_pnl_lines` 表" | 复用 `shipment_costing_results` 表（迁移 0027，含 `cost_material_total` / `cost_process_total` / `cost_overhead_total` / `cost_total`） |
| W3 | "Phase 1 必须新建 `overhead_rate_master` 表" | 见 C1：扩展 `long_tail_cogs_rate_strategies` 表 |
| W4 | "factory 是 v1 必需维度" | 3 法人物理一体（一栋楼一个生产体系）；4 概念正交（production_unit/purchase_entity/cost_center/legal_entity），cost_center 是 v1 核心 |
| W5（已修正措辞）| "在 processes 表加 cost_center_id 等同于把班组人工费率主数据搬过来" | ✅ processes 加 `cost_center_id`（费用归集外键）合理，v1.3 保留 §4.2；❌ 不要把 `taxonomy.team.default_minute_rate` 复制到 processes（两者是费用归集 vs 班组运营两个正交维度） |
| W6 | "Phase 1 需要造 4 个新看板" | 4 个 Insights 看板（`/costing/insights/{models,shops,sales,after-sales}`）已上线；Phase 1 = 加成本可信度徽章 + 三视图切换 |
| W7 | "Cost Rate Hub 是从 0 设计的全新模块" | Hub 是 `LongTailCogsRateStrategy` 雏形（4 层优先级 + history audit）的 superset 扩展 |
| W8 | "Hub 三色徽章需要从 0 造新 service" | 见 C3：复用 `data_quality_service` |

### -1.3 v1.3 复用清单（**vs v1.2 减少 4 张新表 / 减少 1 个新页面 / 减少 1 个新 service**）

| 雏形子系统 | 现有代码 | v1.3 扩展点 |
|---|---|---|
| **`LongTailCogsRateStrategy`**（雏形 Hub）| `backend/src/planner/services/long_tail_strategy_service.py` + `backend/src/planner/routers/long_tail_strategies.py` + `frontend/src/pages/costing/admin/LongTailCogsRatePage.tsx` | 加 `rate_type` + `scope_type` + UI Tab；改名 `cost_rate_master` 表（保留 long-tail 兼容视图） |
| **`shipment_costing_results`**（成本结果落库表）| 迁移 `0027_shipment_costing_results_no_snapshot` + `models.ShipmentCostingResult` | Phase 1 三段成本数据源；盈亏 SQL view 直接 JOIN |
| **4 个 Insights 看板** | `frontend/src/pages/costing/{Profit,Shop,Sales,AfterSales}InsightsPage.tsx` + `analytics_service.py` + `routers/analytics.py` | 加成本可信度徽章 + 三视图切换 |
| **`data_quality_service`**（可信度治理）| `backend/src/planner/services/data_quality_service.py` + `frontend/src/pages/costing/SkuMasterWorkspacePage.tsx` 红 Tag | 加 `cost_quality` 维度（material/labor/overhead 三个 enum） |
| **SKU 治理 4 态状态机** | `backend/src/planner/services/sku_master_service.py::set_sku_governance` + `frontend/src/pages/costing/shipment-ops/components/GovernanceBacklogTab.tsx` | 与成本可信度徽章对齐 |
| **`taxonomy.team` + `default_minute_rate`** | `backend/src/planner/routers/taxonomy.py` `domain='team'` | 班组维度费率源头；Hub Tab 1 聚合显示 |

### -1.4 v1.3 真正新建的（vs v1.2 大幅缩减）

| 新建项 | 必要性 | 复用对照 |
|---|---|---|
| `cost_center` 主数据表 | ✅ P0 必新建（v1 = 班组级别 6~10 个） | 无现成替代 |
| `cost_rate_history` 表（v1 通用变更日志，可选）| 🟡 可暂用 `long_tail_cogs_rate_strategies.metadata.history` 模式延后做 | 已有 long-tail history 模式 |
| Hub 总览 Tab（在现有 LongTailCogsRatePage 上加） | ✅ v1 必加 | 复用页面壳 |
| Hub 费率编辑器 Tab（同上） | ✅ v1 必加 | 复用页面壳 |

### -1.5 v1.3 估工作量（vs v1.2 大幅降低）

| 项 | v1.2 估算 | v1.3 估算 | 降低原因 |
|---|---|---|---|
| 后端 service + router | 4 天 | **2 天** | 复用 `long_tail_strategy_service` 加字段 |
| 前端 Hub 页面 | 4 天 | **2 天** | 复用 `LongTailCogsRatePage` 加 Tab |
| 算法层改造（`_resolve_overhead_rate`）| 1 天 | **0.5 天** | 复用 `resolve_rate_for_sku` 模式 |
| Migration | 0.5 天 | 0.5 天 | 持平（仍需新建 `cost_center` + 扩字段） |
| 4 个 Insights 加徽章 | 1 天 | 1 天 | 持平 |
| 已结账月保护触发器 | 1 天 | 1 天 | 持平 |
| **总计** | **13.5 人日 ≈ 2.5-3 周** | **8 人日 ≈ 1.5-2 周** | **省 5.5 人日** |

---

## 0. 业务事实校准（v1.2 必读 — 决定所有架构选择的前提）

### 0.1 真实组织结构（已和老板核对）

| 维度 | 真实情况 | 对架构的影响 |
|---|---|---|
| **物理生产** | **3 个法人物理一体在一栋楼**，整个工厂是一个生产体系 | **Hub 不分 factory；不会出现"同一商品两个工厂做"的情况** |
| **采购法人** | 1 一般纳税人 + 2 小规模，**部分材料采购按法人分流** | Stage 2 物料端加 `purchase_entity_id`（不在 v1 Hub 范围） |
| **税务法人** | 4 个店铺主体单独报税 + 3 个工厂法人单独报税 | Phase 2 三视图（FI/CO/合并）才需要 `legal_entity`；v1 Hub 不需要 |
| **生产组织** | 工人按**班组**分（家居饰品组 / 布艺组），按**品类**完全可分开 | v1 Hub 用 `cost_center` 作为"班组的财务侧抽象" |
| **物料归属** | 材料按 SKU 可完全分开 | v1 直接读 BOM × 物料价（不进 Hub） |
| **固定费用** | 房租 / 水电 / 行政 / 管理 都是合在一起的 | v1 Hub 总制造费率治理；Phase 2 才拆 4 个费用池 |

### 0.2 4 个组织概念正交拆分（来自 Manus 第四轮评审）

> **关键洞察**：以前我们用一个 `factory` 字段同时表达"在哪生产/谁采购/费用归谁/谁报税"，这是错的。这 4 件事正交。

| 概念 | 含义 | v1 是否使用 | 谁使用 |
|---|---|---|---|
| `production_unit_id` | **实际生产单元**（一栋楼 = 1 个） | ❌ v1 仅 1 个默认值 | Phase 2 多场地时 |
| `purchase_entity_id` | **采购法人**（一般纳税人 / 小规模 A / 小规模 B） | ❌ v1 不进 Hub | **Stage 2 物料端** |
| `cost_center_id` | **费用中心**（班组 + 公共 / 行政 的财务归集） | ✅ **v1 Hub 核心** | **v1 Hub 人工 + 制造费** |
| `legal_entity_id` | **税务/财务法人** | ❌ v1 不进 Hub | **Phase 2 三视图（FI/CO/合并）** |

**v1 Hub 只用 `cost_center`**，因为它直接对应"人工费率治理 + 制造费分摊"这 2 个 v1 必须解决的问题。

### 0.3 与现有架构对齐（2026-05-09 现状审计结果）

> **重要发现**：Cost Rate Hub 80% 的能力**现有 `processes` + `materials` + `process_modules` + `virtual_materials` 已经具备**。Hub v1 不应该"另起炉灶建一张主表"，而是**整合现有 + 加 cost_center 上层 + 加版本审计 + 加总览面板**。

| 现有 | 已有能力 | 缺什么（v1 补） |
|---|---|---|
| `processes`（1027 行 UI） | `charging_mode`(rate_type) + `standard_rate` + `team_name` + `category` | `cost_center_id` 外键 + 版本/审计 + 凭证 |
| `process_modules`（3039 行 UI） | 工艺路线（多 process + 多物料） | 不动 |
| `materials`（1956 行 UI） | `unit_price` + `supplier_code` + `category` | **Stage 2 加** `purchase_entity_id` / `tax_rate` / `tax_included_flag` / `price_source` / `effective_from` |
| `virtual_materials`（2434 行 UI） | 虚拟物料 + bindings | 不动 |
| **`long_tail_cogs_rate_strategies`**（雏形 Hub）| 4 层优先级 resolve + history audit + CRUD + UI 页面 | **v1.3 扩展**：加 `rate_type` + `scope_type`，改名 `cost_rate_master`（保留 long-tail 兼容视图） |
| `ProductModelVersion.metadata_json` | 散落的 `overhead_rate` 配置 | 通过扩展后的 `cost_rate_master`（基于 long-tail 升级）替代散落配置 |

**v1.3 新建表从 3 张 → 1 张**（仅 `cost_center` 必新建；`cost_rate_master` 是 `long_tail_cogs_rate_strategies` 的扩展；`cost_rate_history` 可暂用 long-tail 的 `metadata.history` 模式延后做），**不再重写人工费率体系**，大幅降低风险。

---

## 1. v1 范围与不做清单（必读）

### 1.1 v1 做什么（v1.3 已校准为复用 long-tail 雏形）

| 项 | v1.3 范围（vs v1.2） |
|---|---|
| **新建表** | **`cost_center`**（仅此 1 张必新建，对应 cost_center 主数据） |
| **扩展现有表** | **`long_tail_cogs_rate_strategies`** 加 `rate_type` + `scope_type`，并改名 `cost_rate_master`（v1.2 的 `overhead_rate_master` 设计已废弃，见 §-1.1 C1） |
| **改造现有表** | `processes` 加 `cost_center_id`（FK 可空，向后兼容） |
| **变更日志** | 暂用 `cost_rate_master.metadata_json.history`（long-tail 已有模式），v2 再独立 `cost_rate_history` 表 |
| **scope_type** | `global` + `category` + `cost_center` + `model` （**v1 实做这 4 层**；schema 留 8 层枚举） |
| **rate_type** | `labor_per_minute` + `labor_per_piece` + `labor_per_sqm` + `overhead_rate` |
| **控制台 Tab** | Tab 1 总览 + Tab 2 编辑（v1 实做 2 个，留 8 个面板的扩展位） |
| **可信度徽章** | 🟢真实 / 🟡估算 / 🔴默认 三色 |
| **变更历史** | 每次变更全留痕（cost_rate_history 整 Hub 共用）|
| **后端代码改造** | `_resolve_overhead_rate` 走 `overhead_rate_master` 优先级链；`_compute_process_costing` 仍读 `processes` 但带 cost_center 聚合 |
| **4 个 Insights 警示横条** | 综合可信度 < 80% 时显示警示 |
| **硬规则** | **已结账月份的 `shipment_costing_results` 快照永远不可被费率变更影响** |

### 1.2 v1 不做什么（明确划清）

| 不做的 | 何时做 | 为什么不在 v1 |
|---|---|---|
| `purchase_entity_id` 物料端 | **Stage 2**（v1 上线 +1 周） | v1 物料直读 BOM，先把人工/制造费做稳 |
| scope_type: `production_unit` / `purchase_entity` / `legal_entity` / `sku_role` / `volume_tier` | Stage 3 按需扩展 | v1 不需要，且全部能通过 enum 扩展 |
| Tab 3 财务月度录入 / Tab 4 影响分析 / Tab 5 学习曲线 / Tab 6 SKU 角色 / Tab 7 量价档位 / Tab 8 治理健康度 | v2-Stage3 | v1 财务在 Tab 2 直接录值附凭证 |
| 审批流 | v2 | v1 直接 active，依赖"撤销最近 1 次变更"作为防御 |
| 学习曲线参数化 | Phase 4 AI | 需要机器学习拟合，v1 用月度反推自然包含 |
| 单位时间盈利指标（unit_minute_margin）| Stage 3 | 需要 `shipment_pnl_lines` 完成后才能加 |
| 接 finance API 自动反推 | v2 / 看 C2 契约进展 | v1 财务手工录，弱依赖 finance 团队 |
| 工艺模块（process_modules）改造 | 不做 | 现有 3039 行已成熟，Hub 不动 |
| 虚拟物料（virtual_materials）改造 | 不做 | 现有 2434 行已成熟，Hub 不动 |

### 1.3 关键边界

- **物料成本**：v1 不进 Hub，从 BOM × 实时物料价 × 真实用量算；Stage 2 加 4 字段后由 Hub 总览页面"挂接"（不是迁移到 Hub 表）
- **人工费率**：仍存 `processes.standard_rate`（已有），Hub 提供 `cost_center` 维度的"上层归集 + 总览 + 审计"
- **制造费率（overhead）**：从 `ProductModelVersion.metadata_json` 散落配置 → 集中到 **新建** `overhead_rate_master`
- **变动制造费 vs 固定制造费**：v1 不区分（按总制造费率走），Phase 2 拆 4 个费用池

---

## 2. 一句话定义

**Cost Rate Hub** = 把现有"人工 / 制造费率 / Stage2 后含物料价"的**输入、调节、出口、审计**集中到一个面板。算法层只负责"按规则取数"，所有"数字治理"由人在面板上做。本质是把**算法依赖**降级为**治理依赖**。

---

## 3. 核心架构图（v1.2）

```
                    ┌────────────────────────────────────────────────────────────────┐
                    │  Cost Rate Hub (成本费率与费用归集中枢) v1                       │
                    ├────────────────────────────────────────────────────────────────┤
   ┌─输入端─────┐   │                                                                  │   ┌─出口端──────┐
   │ 财务月度数据 │ → │  ┌─Tab1─总览──┐ ┌─Tab2─编辑──┐                                │ → │ bom_generation│
   │ HR 工资数据  │   │  │ 当前生效费率│ │ 4 层 scope │                                │   │ _service 读取 │
   │ 手工预设值   │   │  │ 三色徽章    │ │ 版本号+生效│                                │   │ + 可信度透传  │
   └────────────┘   │  └────────────┘ └────────────┘                                │   │ + 审计追溯    │
                    │                                                                  │   └────────────┘
                    │  ┌─底层数据 4 张表──────────────────────────────────────────┐  │
   ┌─现有 4 页面─┐  │  │ ① processes (现有) + cost_center_id (新加 FK)             │  │   ┌─Insight 看板┐
   │ /processes  │ ─┼──│ ② process_modules (现有，不动)                            │  │ → │ 4 个页面顶部 │
   │ /process-mod│  │  │ ③ materials (现有，Stage 2 加 4 字段)                     │  │   │ 显示综合可信度│
   │ /materials  │  │  │ ④ virtual_materials (现有，不动)                          │  │   │ 加可信度徽章列│
   │ /virtual-mat│  │  │ ─── v1 新建 ────────────────────────────────────────────  │  │   └────────────┘
   └────────────┘   │  │ ⑤ cost_center (5-7 行数据)                                │  │
                    │  │ ⑥ overhead_rate_master (集中制造费率，含 4 层 scope)      │  │
                    │  │ ⑦ cost_rate_history (整 Hub 通用变更日志)                 │  │
                    │  └──────────────────────────────────────────────────────────┘  │
                    │                                                                  │
                    │   ┌── 4 个扩展点（保证未来不改主流程）──┐                        │
                    │   │ 1. scope_type enum 可扩展             │                        │
                    │   │ 2. derivation_strategy 字段           │                        │
                    │   │ 3. metadata_json 自定义               │                        │
                    │   │ 4. API 版本化 /v1/...                 │                        │
                    │   └────────────────────────────────────────┘                        │
                    └────────────────────────────────────────────────────────────────┘
```

---

## 4. 数据模型

### 4.1 `cost_center`（费用中心，v1 新建）

```sql
CREATE TABLE cost_center (
    id              VARCHAR(36) PRIMARY KEY,
    code            VARCHAR(64) UNIQUE NOT NULL,        -- e.g. 'CC_FABRIC_PROD'
    name            VARCHAR(128) NOT NULL,              -- e.g. '布艺生产组'
    type            VARCHAR(32)  NOT NULL,              -- 'production'|'auxiliary'|'admin'
    description     TEXT,
    -- 默认分摊基础（v1 用作总览展示，不强制约束算法）
    default_allocation_basis VARCHAR(32),               -- 'headcount'|'team_hours'|'revenue'|'floor_area'|'fixed_pct'
    -- 关联现有 team 字符串（迁移过渡期）
    legacy_team_names JSONB DEFAULT '[]',               -- 老的 processes.team_name 映射
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    metadata_json   JSONB DEFAULT '{}',
    created_at      TIMESTAMP NOT NULL DEFAULT now(),
    updated_at      TIMESTAMP NOT NULL DEFAULT now(),
    deleted_at      TIMESTAMP
);
```

**v1 初稿数据（评审会前老板拍板）**：

| code | name | type |
|---|---|---|
| CC_DECOR_PROD | 家居饰品生产组 | production |
| CC_FABRIC_PROD | 布艺生产组 | production |
| CC_PRINT | 印花打印组 | auxiliary |
| CC_CUT_EDGE | 裁剪包边组 | auxiliary |
| CC_PACK_SHIP | 包装发货组 | auxiliary |
| CC_ADMIN | 公共管理 | admin |

> ⚠️ **评审会前置物**：老板按真实班组校对此清单（H4 决策点）。

### 4.2 `processes` 改造（现有表加 1 字段）

```sql
ALTER TABLE processes 
    ADD COLUMN cost_center_id VARCHAR(36) REFERENCES cost_center(id);

-- 数据迁移：从现有 team_name 字符串映射到 cost_center_id
-- 由 Hub v1 上线时的 migration 脚本完成
CREATE INDEX idx_processes_cost_center ON processes(cost_center_id);
```

**保持向后兼容**：`team_name` 字段保留（前端 ProcessesPage 仍用），新加 `cost_center_id` 作为 Hub 治理维度。

### 4.3 `cost_rate_master`（v1.3 校准：扩展现有 `long_tail_cogs_rate_strategies` 表，**不新建**）

> **v1.3 关键变化**：v1.2 设计的"新建 `overhead_rate_master` 表"已废弃（见 §-1.1 C1）。v1.3 改为扩展现有 `long_tail_cogs_rate_strategies` 表（迁移 0035 已落地，含 4 层优先级 resolve + history audit + CRUD + UI），加 11 个字段后改名 `cost_rate_master`，原 long-tail 行为通过 `rate_type='cogs'` 兼容保留。

#### 4.3.1 现状（不重读直接复用）

`long_tail_cogs_rate_strategies` 表当前字段（迁移 0035）：
- `id` / `category`(unique) / `rate`(Decimal 0~1) / `keywords`(JSON) / `priority`(int) / `enabled`(bool) / `note` / `metadata_json.history`（最近 20 次审计） / `is_archived` / `created_at` / `updated_at`

`long_tail_strategy_service.resolve_rate_for_sku` 当前 4 层 resolve：
1. `SkuMaster.metadata.long_tail_category`（人工指定）
2. `keywords` 命中 spec_text+product_name+...（priority 高优先）
3. `category='default'` 兜底策略
4. 全局 `settings.long_tail_cogs_rate`（0.55）

#### 4.3.2 v1.3 扩展字段（Migration 0038 新增）

```sql
-- v1.3 Migration 0038: 扩展 long_tail_cogs_rate_strategies → cost_rate_master
ALTER TABLE long_tail_cogs_rate_strategies
    ADD COLUMN rate_type      VARCHAR(32) NOT NULL DEFAULT 'cogs',
    -- v1 enum: 'cogs' (兼容老 long-tail) | 'labor_per_minute' | 'labor_per_piece' | 'labor_per_sqm' | 'overhead_rate'
    ADD COLUMN scope_type     VARCHAR(32) NOT NULL DEFAULT 'category',
    -- v1 enum: 'global' | 'category' | 'cost_center' | 'model'
    -- 扩展 enum: + 'production_unit' | 'purchase_entity' | 'legal_entity' | 'sku_role' | 'volume_tier'
    ADD COLUMN scope_id       VARCHAR(64),                  -- global 时为 NULL；category 时存 category 名；cost_center 时存 cost_center.id；model 时存 model_version_id
    ADD COLUMN rate_basis     VARCHAR(32) NOT NULL DEFAULT 'as_pct_of_direct_cost',
    -- 'as_pct_of_direct_cost' | 'per_minute' | 'per_piece' | 'per_sqm' | 'pct_of_revenue' (老 long-tail cogs 用此)
    ADD COLUMN allocation_basis VARCHAR(32),                -- 'headcount'|'team_hours'|'revenue'|'floor_area'|'fixed_pct'
    ADD COLUMN effective_from DATE,                         -- NULL 等价于"立即生效"
    ADD COLUMN effective_to   DATE,                         -- NULL = 当前生效
    ADD COLUMN trust_level    VARCHAR(16) NOT NULL DEFAULT 'medium',  -- 'low' | 'medium' | 'high'
    ADD COLUMN source         VARCHAR(32) NOT NULL DEFAULT 'manual_preset',
    -- 'manual_preset' | 'finance_pushback' | 'imported_excel' | 'system_calculated' | 'long_tail_legacy'
    ADD COLUMN derivation_strategy VARCHAR(32),             -- 扩展点 2（沿用 v1.2 §6 设计）
    ADD COLUMN approved_by    VARCHAR(64),
    ADD COLUMN approved_at    TIMESTAMP,
    ADD COLUMN supporting_doc_url VARCHAR(512);

-- 老 long-tail 行兼容：rate_type='cogs' / scope_type='category' / scope_id=category 字段值
UPDATE long_tail_cogs_rate_strategies
SET rate_type='cogs', scope_type='category', scope_id=category, rate_basis='pct_of_revenue', source='long_tail_legacy'
WHERE rate_type IS NULL OR rate_type='cogs';

-- 关键索引：按"取数路径"优化
CREATE INDEX idx_cost_rate_lookup ON long_tail_cogs_rate_strategies
    (rate_type, scope_type, scope_id, enabled, effective_from DESC)
    WHERE enabled = TRUE AND is_archived = FALSE;

CREATE INDEX idx_cost_rate_global_active ON long_tail_cogs_rate_strategies
    (rate_type, effective_from DESC)
    WHERE enabled = TRUE AND is_archived = FALSE AND scope_type = 'global';

-- v1.3 表名通过 ALTER TABLE 改名（Postgres 安全；保留 long-tail 名作为 view 供老代码 1-2 周过渡）
ALTER TABLE long_tail_cogs_rate_strategies RENAME TO cost_rate_master;
CREATE VIEW long_tail_cogs_rate_strategies AS
    SELECT * FROM cost_rate_master WHERE rate_type = 'cogs';  -- 兼容旧 SQL/老 service
```

#### 4.3.3 v1.3 字段映射对照（v1.2 设计 vs v1.3 实际）

| v1.2 旧字段 | v1.3 落点 | 说明 |
|---|---|---|
| `overhead_rate_master.rate_value` | `cost_rate_master.rate` | 沿用 long-tail 字段名 |
| `overhead_rate_master.notes` | `cost_rate_master.note` | 沿用 long-tail 字段名 |
| `overhead_rate_master.created_by` | `cost_rate_master.metadata_json.history[].actor` | 复用 long-tail history 模式 |
| `overhead_rate_master.UNIQUE(scope_type,scope_id,version_no)` | `cost_rate_master` 不强约束 unique（用 effective_from 区分版本） | long-tail 历史用 history 数组 |

#### 4.3.4 关键不变量（与 long-tail 行为 100% 兼容）

- `rate_type='cogs'` 的行 = 原 long-tail 策略（老 service `resolve_rate_for_sku` 行为不变）
- `rate_type='overhead_rate'` 的行 = 新 Hub 制造费率（新 service `resolve_overhead_rate` 调用 4 层链）
- 现有 `frontend/src/pages/costing/admin/LongTailCogsRatePage.tsx` 通过 query 参数 `?rate_type=cogs` 仅显示 long-tail，加新 Tab 后通过 `?rate_type=overhead_rate` 显示 Hub 数据
- 现有 25 个 pytest 测试（`test_long_tail_strategy.py` 16/16 + `test_long_tail_auto_suggest.py` 9/9）必须 100% 通过

### 4.4 `cost_rate_history`（变更历史，v1 新建，整 Hub 通用）

```sql
CREATE TABLE cost_rate_history (
    id              VARCHAR(36) PRIMARY KEY,
    -- 关联到任意一个被治理对象（多态）
    target_table    VARCHAR(64) NOT NULL,
    -- 'overhead_rate_master' | 'processes' | 'materials' | 'cost_center'
    target_id       VARCHAR(36) NOT NULL,
    change_type     VARCHAR(32) NOT NULL,
    -- 'create' | 'value_change' | 'status_change' | 'extend_period' | 'archive'
    old_value       JSONB,                            -- 改前 snapshot
    new_value       JSONB,                            -- 改后 snapshot
    changed_by      VARCHAR(64) NOT NULL,
    changed_at      TIMESTAMP NOT NULL DEFAULT now(),
    change_reason   TEXT,
    revertable      BOOLEAN DEFAULT TRUE,
    metadata_json   JSONB DEFAULT '{}'                -- 含变更影响范围（影响 N 个 SKU 等）
);

CREATE INDEX idx_cost_rate_history_target ON cost_rate_history (target_table, target_id, changed_at DESC);
CREATE INDEX idx_cost_rate_history_changed_at ON cost_rate_history (changed_at DESC);
```

**永不删除**。Hub 的所有变更（含 `processes.standard_rate` 修改、`materials.unit_price` 修改）都有迹可查。

### 4.5 `materials` Stage 2 改造（不在 v1 范围，仅记录）

```sql
-- Stage 2 才执行（v1 上线后第 +1 周）
ALTER TABLE materials 
    ADD COLUMN purchase_entity_id   VARCHAR(36),
    ADD COLUMN tax_included_flag    BOOLEAN DEFAULT FALSE,
    ADD COLUMN tax_rate             NUMERIC(6,4),
    ADD COLUMN price_source         VARCHAR(32),  -- 'manual'|'po_avg_30d'|'last_po'|'contract'|'system_imported'
    ADD COLUMN effective_from       DATE,
    ADD COLUMN effective_to         DATE;

-- 注意：不新建 purchase_entity 表，先用枚举值字符串
-- ('一般纳税人' / '小规模A' / '小规模B') ，Phase 2 再建主数据
```

---

## 5. 优先级链（v1 实做 4 层；schema 留 8 层枚举）

### 5.1 制造费率 `_resolve_overhead_rate` 解析顺序

```
v1 实做（自上而下，命中即返回）：
    1. model       (scope_type='model',       scope_id=<model_id>)
    2. category    (scope_type='category',    scope_id=<category_name>)
    3. cost_center (scope_type='cost_center', scope_id=<cost_center_id>)
    4. global      (scope_type='global',      scope_id=NULL)
    5. fallback    0.30 + 标 source='hardcoded_fallback' + trust_level='low'

Schema 留位的扩展（Stage 3 按需开启）：
    + production_unit / purchase_entity / legal_entity
    + sku_role / volume_tier
```

### 5.2 人工费率（v1 仍走 `processes.standard_rate`）

人工费率**不存到 `overhead_rate_master`**，因为现有 `processes` 表已经是天然的"按工序 + 班组的费率主表"。Hub 做的是：

1. **总览**：在 Hub Tab 1 聚合显示"按 cost_center 的人工费率分布"
2. **审计**：当 ProcessesPage 修改 `standard_rate` 时，触发器写一条 `cost_rate_history`
3. **可信度透传**：`processes` 加 `trust_level` 字段（v1 加），Hub 总览汇总

### 5.3 物料价格（v1 不变）

`materials.unit_price` 直接读，BOM 一次性算清。Stage 2 加效期字段后，按发货日期取价（也仍不进 `cost_rate_master`）。

### 5.4 与 SKU 治理 4 态状态机对齐（v1.3 新增，见 §-1.1 C4）

> 成本可信度徽章必须与现有 SKU 治理状态机（见 `DOC/agents/known_issues.md` Issue 23）对齐，避免做"两套并行的可信度系统"。

| SKU 治理状态 | 含义 | 成本可信度徽章 | Hub 提供的 rate 来源 |
|---|---|---|---|
| `auto_bound` | 已绑定 published 模型版本 | 🟢 高 | `cost_rate_master` 4 层 resolve（model 命中率高）+ 真实 BOM × 真实物料价 |
| `pending_model` | 决定要建模、模型还没发布 | 🟡 中 | `cost_rate_master` resolve（category 兜底）+ BOM 缺失 → 提示运营 |
| `do_not_model` | 长尾 SKU，一月一单不值得建 | 🔴 低（长尾兜底）| 老 long-tail 路径不变（`rate_type='cogs'` 的行 + `revenue × rate` 兜底）|
| `unmanaged` | 默认；运营还没看过 | ⚪ 未识别 | 入异常队列，不出快照 |

**实现方式**：`shipment_costing_results.metadata_json` 已有 `kind='long_tail_fallback'` 字段，v1.3 扩展 `cost_quality` 嵌套对象：
```json
{
  "cost_quality": {
    "material": "high",     // 真实 BOM × 真实物料价 → high
    "labor":    "medium",   // taxonomy.team.default_minute_rate → medium
    "overhead": "low",      // 30% 兜底未被 Hub 覆盖 → low
    "overall":  "low",      // min() 聚合
    "sku_governance_status": "auto_bound"  // 透传
  }
}
```

---

## 6. 4 个扩展点（保证未来不需要改主流程）

> **这是 Hub 设计的核心** — 让所有"未来专业能力"都通过 Hub 接口扩展，**算法层永远只读 4 张表**。

### 扩展点 1：`scope_type` 是 enum 字段，新增类型只要加枚举值

| 想加什么 | 怎么加 | 算法层是否要改 |
|---|---|---|
| 引流款 vs 利润款（sku_role）| 加 enum `sku_role`，插入 `(scope_type='sku_role', scope_id='traffic_driver', rate=0.10)` | ❌ 不改 |
| 产量档位（volume_tier） | 加 enum `volume_tier`，加月度 worker 自动选档 | ❌ 不改 |
| 多法人（legal_entity） | 加 enum `legal_entity`，按公司 UUID 插入 | ❌ 不改 |
| 多采购法人（purchase_entity） | 加 enum `purchase_entity`，按主体 ID 插入 | ❌ 不改 |
| 多生产单元（production_unit） | 加 enum `production_unit`，按场地 ID 插入 | ❌ 不改 |

### 扩展点 2：`derivation_strategy` 字段

| derivation_strategy | 含义 | 谁写入 |
|---|---|---|
| `manual` | 财务/老板手工录入 | UI |
| `finance_pushback_monthly` | finance API 月度反推 | worker (v2) |
| `volume_tier_auto` | 按月产量自动选档 | worker (Stage 3) |
| `learning_curve_fit` | 学习曲线拟合 | worker (Phase 4) |
| `category_template` | 品类模板继承 | UI / migration |

### 扩展点 3：`metadata_json` 自定义字段

每条 rate 可挂任意附加信息（sku_role 策略、volume_tier 阈值、学习曲线拟合参数等）。

### 扩展点 4：API 版本化 `/api/cost-rate-hub/v1/...`

```
GET  /api/cost-rate-hub/v1/cost-centers                # 列出 cost_center
POST /api/cost-rate-hub/v1/cost-centers                # 新增 cost_center
GET  /api/cost-rate-hub/v1/overhead-rates              # 列出当前生效制造费率
POST /api/cost-rate-hub/v1/overhead-rates              # 新增/编辑制造费率
GET  /api/cost-rate-hub/v1/overhead-rates/{id}/history # 变更历史
POST /api/cost-rate-hub/v1/overhead-rates/{id}/revert  # 撤销最近 1 次变更
GET  /api/cost-rate-hub/v1/resolve                     # 给算法用：按 (scope_type, scope_id, rate_type) 解析
GET  /api/cost-rate-hub/v1/quality-summary             # 给 Insights 用：综合可信度
GET  /api/cost-rate-hub/v1/labor-summary               # 聚合现有 processes 按 cost_center
```

---

## 7. 控制台 8 个面板架构（v1 实做 2 个，Stage 2/3 加 6 个）

> 来自 Manus 第三轮评审建议，留好 8 个面板的扩展位，避免后续重构。

| Tab # | 名称 | v1 / v2 / Stage 3 | 说明 |
|---|---|---|---|
| **Tab 1** | **费率总览** | **v1** | 当前生效费率全景图（global + cost_center + category + model）三色徽章 |
| **Tab 2** | **费率编辑器** | **v1** | 4 层 scope 录值 + 凭证上传 + 影响预览 |
| Tab 3 | 财务月度录入 | v2 | finance 团队按月手工录入 / 反推数据导入 |
| Tab 4 | 影响分析 | v2 | 改一个值，预计毛利变动 / 影响 SKU 列表 |
| Tab 5 | 学习曲线（Phase 4） | Stage 3 | 历史用工时长拟合 + 自动费率推荐 |
| Tab 6 | SKU 角色管理 | Stage 3 | 引流款/利润款/形象款分类 + 差异化费率 |
| Tab 7 | 量价档位（volume_tier） | Stage 3 | 按月产量自动选档 + 阶梯成本 |
| Tab 8 | 治理健康度 | Stage 3 | 综合可信度看板 + 长期未更新告警 + 老板周报 |

### Tab 1 v1 草图：费率总览 `/costing/admin/cost-rate-hub`（v1.3：扩展现有 `/costing/admin/long-tail-cogs-rate` 页面，加 Tab；旧路由 301 重定向兼容）

```text
┌────────────────────────────────────────────────────────────────────┐
│ 成本费率治理中枢                              [+ 新增费率]          │
├────────────────────────────────────────────────────────────────────┤
│  当前生效综合可信度：72% 🟡  最后更新：2026-04-30 by 张会计         │
├────────────────────────────────────────────────────────────────────┤
│  全局默认 (Global)                                                  │
│  ┌──────────────────────────────┐  ┌──────────────────────────────┐│
│  │ 制造费率 0.30  🔴 默认值       │  │ 总览：人工费率分布            ││
│  │ 生效自 2025-01-01             │  │ 中位数 0.45 元/分钟  🟡       ││
│  │ source: manual_preset          │  │ 来源：聚合 processes 表       ││
│  │ [编辑]  [查看历史]             │  │ [跳转 ProcessesPage 编辑]     ││
│  └──────────────────────────────┘  └──────────────────────────────┘│
├────────────────────────────────────────────────────────────────────┤
│  按品类 (Category Override) — 2 个                                  │
│  家居饰品   制造费 0.25 🟡 财务录入 4 月  人工 (聚合 6 工序)         │
│  家居布艺   制造费 0.32 🟡 财务录入 4 月  人工 (聚合 8 工序)         │
├────────────────────────────────────────────────────────────────────┤
│  按 Cost Center — 6 个                                              │
│  CC_FABRIC_PROD    制造费 (继承品类)  人工 0.48 元/分 🟢 4 月实测   │
│  CC_DECOR_PROD     制造费 (继承品类)  人工 0.42 元/分 🟢 4 月实测   │
│  CC_PRINT          制造费 (继承全局)  人工 0.55 元/分 🟡            │
│  CC_ADMIN          仅承载固定费 ───  人工 不参与产品成本             │
│  ...                                                                │
├────────────────────────────────────────────────────────────────────┤
│  模型级 (Model Override) — 5 个                                     │
│  KB8     制造费 0.18 🟢 finance反推 4 月  人工 0.62 元/分 🟡 5月待校│
│  KB12    制造费 0.22 🟡 (覆盖默认)        人工 (继承 cost_center)   │
│  ...                                                                │
│  [展示更多]                                                         │
└────────────────────────────────────────────────────────────────────┘
```

### Tab 2 v1 草图：费率编辑器

```text
┌────────────────────────────────────────────────────────────────────┐
│ 编辑制造费率                                                        │
├────────────────────────────────────────────────────────────────────┤
│  范围：[模型 ▼ / 品类 / Cost Center / 全局]  [KB8 ▼]                 │
│  当前值：0.30 🔴  生效自 2025-01-01                                 │
│  当前实际溯源：global → fallback 0.30                                │
│                                                                     │
│  新值：[___]                                                        │
│  生效日期：[2026-05-01 ▼]                                           │
│  数据来源：[手工预设 / Finance反推 / Excel导入 ▼]                  │
│  可信度：[🔴低 / 🟡中 / 🟢高] (根据来源自动建议，可手工调)          │
│  备注（必填）：[这次为什么改？基于什么数据？]                        │
│  上传凭证：[选择文件] (Excel/PDF，可选)                            │
│                                                                     │
│  ⚠️ 影响预览：本次变更将影响 KB8 的 ___ 个 SKU                     │
│      （v2 加：预计毛利变动 ___%）                                  │
│                                                                     │
│  ⛔ 已结账月份警告：本变更不会影响 2026-04 及之前已结账的成本快照   │
│                                                                     │
│  [取消]  [保存为草稿]  [直接生效]                                   │
└────────────────────────────────────────────────────────────────────┘
```

---

## 8. 与现有代码的对接（精确改造点，v1.3 已校准为复用模式）

| 现有代码位置 | 改造内容 | 工作量 |
|---|---|---|
| `bom_generation_service.py:2047` `_resolve_overhead_rate` | 改为调 `cost_rate_master_service.resolve_overhead_rate(model_id, category, cost_center_id)` 4 层优先级链；返回 `(rate, source, trust_level)`；30% 兜底保留为最后一层 | 0.5 天 |
| `bom_generation_service.py:1893` `_compute_process_costing` | 仍读 `processes.standard_rate`，但响应结构里加 `cost_center_id` + `trust_level` 透传 | 0.5 天 |
| `bom_generation_service.py:1129/1487` Bundle 合并 | 移除写死 `Decimal("0.3")`，改为按 group 取实际 rate（调用同一 resolver） | 0.5 天 |
| `shipment_import_service.py` 写 `ShipmentCostingResult` | 加 `cost_quality` 嵌套对象到 `metadata_json`（material/labor/overhead/overall/sku_governance_status）；**已结账月不可被覆盖**触发器 | 1 天 |
| `analytics_service.profit_by_model` 等 | 响应加 `cost_quality_summary`（按 trust_level 统计 SKU 占比） | 0.5 天 |
| 4 个 Insights 页面（`{Profit,Shop,Sales,AfterSales}InsightsPage.tsx`） | 顶部加可信度警示横条 + 列里加可信度徽章 + 三视图切换控件 | 1 天 |
| `processes` 表 migration | 加 `cost_center_id` + `trust_level` 字段；从 `team_name` 写迁移脚本到 `cost_center_id`（用 H4 老板拍板的初稿映射） | 0.5 天 |
| **扩展（不新建）** `backend/src/planner/services/long_tail_strategy_service.py` | 加 `resolve_overhead_rate()` 等 Hub resolver 方法；老 `resolve_rate_for_sku()` 通过 `rate_type='cogs'` filter 完全保留 | 1 天 |
| **扩展（不新建）** `backend/src/planner/routers/long_tail_strategies.py` | 加 `POST /api/planner/cost-rate/resolve` + `GET /list?rate_type=overhead_rate` + `GET /labor-summary`；老 `/api/planner/long-tail-strategies/*` 完全保留 | 1 天 |
| **扩展（不新建）** `frontend/src/pages/costing/admin/LongTailCogsRatePage.tsx` | 改为顶部 Tabs：①长尾策略（老）②Hub 总览（新）③Hub 编辑器（新）；通过 `?rate_type=cogs` vs `?rate_type=overhead_rate` 过滤；新路由 `/costing/admin/cost-rate-hub` 加 301 重定向 | 2 天 |
| **复用** `data_quality_service.py` | 加 `cost_quality` 维度（不新建 service） | 0.5 天 |
| **新建** `cost_center` 表 migration + service + router | 这是 v1.3 唯一必须新建的资产 | 0.5 天 |
| Migration 0038（rename + 加字段）| `long_tail_cogs_rate_strategies → cost_rate_master` + 加 11 字段 + 加 view 兼容 | 0.5 天 |

**v1.3 总工作量：约 8 人日 ≈ 1.5-2 周**（vs v1.2 估的 13.5 天降低 ~40%）

---

## 9. v1 实施清单（W2-W6）

| 周 | 后端 | 前端 | 数据治理 |
|---|---|---|---|
| W2 | Migration: 3 张新表 + processes 加 cost_center_id + trust_level；初始化 cost_center 数据 | 模块骨架 + 路由 | 财务把当前所有"隐式"费率（model meta 里的）整理为初始数据；老板拍 cost_center 清单 |
| W3 | Hub service + API（resolve / list / create / history / revert / labor-summary）+ 改造 `_resolve_overhead_rate` 走 4 层优先级 | Tab 1 总览 + 公共组件（可信度徽章 / 历史抽屉 / cost_center 分组卡片） | KB8 反向核算诊断同步进行（独立路径） |
| W4 | 改造 `shipment_import_service` 落 `cost_quality` + 改造 `analytics_service` 加 quality summary + 已结账月保护触发器 | Tab 2 编辑器 + 影响预览 SKU 数 | 财务录入"全局制造费率""按品类制造费率"初始值 |
| W5 | 4 个 Insights 加警示横条 + 列徽章 | 联调 + KB8 实操：财务录 4 月反推值 → 重跑 KB8 → 老板看新旧对比 ★ | 财务录入 KB8 的 model 级 override |
| W6 | 灰度 + 监控 | 上线 + SOP | 全模型铺开 |

**演示日 W5**：老板第一次看到"可信"的 KB8 数据 + 控制台能改值。

---

## 10. 待评审会拍板的 4 个点（v1.2 增加 H4）

| # | 议题 | 选项 | 谁拍板 |
|---|---|---|---|
| H1 | 全局默认的 2 个费率初始值 | 维持 0.30 制造费 + 0.45 元/分钟人工 / 或先按某月反推值 | 老板 + 财务 |
| H2 | 谁有 Hub 编辑权 | 仅财务 + 老板 / 加 ai-costing 实施负责人 | 老板 |
| H3 | "撤销最近 1 次变更"按钮的可用窗口 | 24 小时 / 7 天 / 永久 | 老板 + 财务 |
| **H4** | **cost_center 初稿清单** | 6 个（饰品/布艺/印花/裁剪包边/包装发货/管理）/ 老板按真实班组校对 | **老板 + 工厂厂长** |

---

## 11. 风险与应对

| # | 风险 | 应对 |
|---|---|---|
| 1 | **费率改了，历史 SKU 成本会跟着变 → 老板对账失败** | **必做"已结账月保护"硬规则**：发货时 `cost_snapshot` 锁住当时用的 rate_id + version_no，分析时从 snapshot 读，不从 master 读。**v1 必须做这一条**，否则数据漂移问题会替代"数据不准"成为新的信任危机 |
| 2 | **财务忘了月度更新 → 费率永远停在第一次预设值上** | Hub 总览页"超过 N 天没更新"红色告警 + 钉钉推送 + 老板每周可见的"治理健康度"（Stage 3 Tab 8） |
| 3 | **录错了一个数 → 全 SKU 成本失真** | v1 必须有"撤销最近 1 次变更"按钮 + 影响 > N 个 SKU 时强制确认 |
| 4 | **优先级链复杂，老板看不懂"为什么这个 SKU 用这个费率"** | Tab 2 显示"溯源链"：当前 SKU 的 rate 来自 (scope_type='model', scope_id='KB8', version_no=3, source='finance_pushback')|
| 5 | **Hub 上线后 finance 团队仍未补 C2 测试** | 不影响 Hub v1 上线（弱依赖 finance）；v2 接 finance 自动反推时再卡 C2 |
| 6 | **现有 processes.team_name 与新 cost_center_id 双轨期可能数据不一致** | 迁移脚本一次性映射；上线后 `team_name` 仅作为兼容字段；前端 ProcessesPage 加"当前归属 cost_center: ___"显示 |
| 7 | **cost_center 划分错误导致后续费率归集失真** | 评审会前老板必须签字；v1 上线后留 2 周观察期，发现错误可以重组并触发批量 cost_rate_history 记录 |

---

## 12. v1 vs 之前规划方案的对比

| 维度 | 之前规划（直接接 finance API） | Cost Rate Hub v1.2 |
|---|---|---|
| 依赖 finance 团队 | 强（C2 API + 双向耦合）| **弱**（finance 只提供数据，不接 API） |
| 上线时间 | 6-8 周 | **2.5-3 周（v1 骨架）** |
| 财务参与度 | 被动 | **主动**（每月在 Hub 录入） |
| 审计可追溯 | 部分 | **完整**（每次变更留痕 + 凭证附件） |
| 老板信任度 | 低（系统黑盒） | **高**（财务亲自录 + 老板可见溯源链 + 三色徽章） |
| 调节灵活性 | 低（要改算法） | **高**（在控制台改一个值就行） |
| 多主体支持 | 难 | **天然支持**（scope 加枚举即可，4 概念正交） |
| 专业能力扩展（sku_role / volume_tier / 学习曲线） | 难（每个都要改算法） | **极易**（Hub 加数据，算法不动） |
| 与现有架构兼容 | 需要重写 | **不重写**（复用 processes / process_modules / materials / virtual_materials 4 个现有页面 8456 行 UI） |

---

## 13. Stage 2 与 Stage 3 简述（不在本文档详细展开）

### Stage 2：物料做实（Hub v1 上线后立刻启动，预计 +1 周）

| 范围 | 做法 |
|---|---|
| `materials` 加 4 字段 | `purchase_entity_id` / `tax_included_flag` / `tax_rate` / `price_source` / `effective_from` |
| BOM 物料单价 | 接采购系统 / 月度加权平均价 worker，替换 BOM 写死价 |
| BOM 用量审计 | 抽 5-10 个高销 SKU 的 BOM 跟真实出库台账对比，修 BOM |
| 辅料补全 | 工厂逐项排查 BOM 是否漏了包装/说明书/五金件，补进 BOM |
| Hub Tab 1 加挂"物料价格治理"卡片 | 不是迁移，是把 materials 的价格变更日志聚合显示 |

工作量：约 1 周 + 持续治理。

### Stage 3：专业能力按需扩展（无固定时间表）

按业务诉求逐个加，**每个能力都通过 Hub 接口实现**：

| 能力 | 实现方式 | 关联面板 |
|---|---|---|
| sku_role 差异化费率 | 加 enum `sku_role` + 5 类预设值 + 算法优先级链已有 | Tab 6 |
| volume_tier 阶梯成本 | 加 enum `volume_tier` + 月度选档 worker | Tab 7 |
| legal_entity 多主体费率 | 加 enum `legal_entity` + scope_id 用公司 UUID | — |
| 单位时间盈利指标 | 在**现有 `shipment_costing_results.metadata_json`** 加 `unit_minute_margin`（v1.3 校准：v1.2 误写 `shipment_pnl_lines`，已废弃，见 §-1.1 C5）；盈亏 SQL view JOIN `shipment_costing_results` 计算 | Tab 4 |
| Tab 3 财务月度录入面板 | UI 增量 | Tab 3 |
| Tab 4 影响分析 | UI + 历史回归 | Tab 4 |
| 学习曲线参数化 | 加 worker 拟合 + `derivation_strategy='learning_curve_fit'` | Tab 5 |
| 接 finance API 自动反推 | 加 worker + C2 契约达成 | Tab 3 |
| Tab 8 治理健康度 | 综合可信度看板 + 长期未更新告警 | Tab 8 |

---

## 14. 元信息

| 项 | 值 |
|---|---|
| 文档版本 | **v1.3** |
| 创建日期 | 2026-05-09 上午（首版 v1.0）；2026-05-09 下午（v1.2 校准）；2026-05-09 17:50（**v1.3 三次校准**） |
| 校准事件 | (1) Manus 第三轮评审：8 面板 / 4 概念 / 已结账保护硬规则 (2) Manus 第四轮评审：factory 维度修正 → 4 概念正交 (3) 现状审计：复用现有 processes / process_modules / materials / virtual_materials (4) **v1.3：基于 `system_capability_inventory.md` v1.0 + §12 全面采纳"复用 LongTailCogsRateStrategy 雏形 + data_quality_service + SKU 治理 4 态对齐 + shipment_costing_results 表"** |
| 关联决策 | pnl_decision_log #34-#36（Hub 三阶段路线）/ #40-#45（v1.2 校准）/ **#48（v1.3 校准生效）** |
| 关联蓝图 | pnl_analytics_module_design.md（v1.1 待校准）/ finance_analyzer_integration_v1.md（v1.1 待校准）/ profit_and_returns_analytics_plan_2025_2026_v0_1.md（v0.1 项目原配蓝图，**禁止覆盖**） |
| 关联接力 | pnl_module_handover.md §0 业务事实 / §4 模块边界 / §8.b 数据治理路线 / **system_capability_inventory.md §12（首读）** |
| 上一版 | v1.0（2026-05-09 上午）→ v1.2（2026-05-09 下午）→ **v1.3（2026-05-09 17:50）**；中间无 v1.1 跳号 |
| 评审会决策点 | H1 / H2 / H3 / **H4 cost_center 初稿**（见 §10）/ **H5（v1.3 新增建议）：通过 v1.3 校准方案，承认 v1.2 设计的 5 项结构性变化（C1~C5）** |
| 外部评审引用 | pnl_external_reviews/INDEX.md §3 / §4 / §5 |
| v1.3 强制读 | `DOC/costing/handovers/system_capability_inventory.md` v1.0+§12（**首读**），含 11 份历史已动文档清单 + W1~W8 废弃叙述 + 文档优先级规则 |

---

*本文档是 Cost Rate Hub v1.3 的完整设计。Stage 2 与 Stage 3 后续按需出独立文档。任何与本文 v1.3 冲突的过往叙述（v1.0 / v1.2 / 其他 PnL 文档），以本文 v1.3 为准。*
