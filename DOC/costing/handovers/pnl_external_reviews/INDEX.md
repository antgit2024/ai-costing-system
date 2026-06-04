# PnL 模块外部评审报告索引

> **目的**：归档所有外部评审报告（AI / 第三方顾问 / 老板手稿），方便后人追溯"为什么采纳 / 为什么不采纳"。
> **维护规则**：每次收到外部评审 → 创建索引条目 + 复制原文到本目录 / 引用绝对路径。
> **不删除老评审**：即使方案被推翻，原报告必须保留。

---

## 评审表（按时间倒序）

| # | 日期 | 报告标题 | 作者 | 评审范围 | 采纳率 | 关键转向 | 原文位置 |
|---|---|---|---|---|---|---|---|
| 5 | 2026-05-09 | 对用户解答的二次评审：factory 维度修正版结论 | Manus AI | Cost Rate Hub 第三轮评审中 factory 维度的修正 | ~95% | **关键校准**：3 法人物理一体在一栋楼 → Hub 不分 factory；4 概念正交（production_unit / purchase_entity / cost_center / legal_entity）替代单一 factory | [`/home/admin/ai-costing-system/DOC/基础表单/对用户解答的二次评审：factory 维度修正版结论.md`](../../../基础表单/对用户解答的二次评审：factory%20维度修正版结论.md) |
| 4 | 2026-05-09 | 成本参数Hub与月度调节面板：评审与设计建议 | Manus AI | Cost Rate Hub v1.0 设计 | ~85% | 8 面板架构 / 4 概念正交（首次提出，第五轮被部分校正）/ rate_type 扩展为 3 种 / cost_pool + allocation_basis / 已结账月不可改硬规则 / 留 8 层 scope_type enum / 凭证上传 + 撤销窗口 + API 版本化 | [`/home/admin/ai-costing-system/DOC/基础表单/成本参数Hub与月度调节面板：评审与设计建议.md`](../../../基础表单/成本参数Hub与月度调节面板：评审与设计建议.md) |
| 3 | 2026-05-09 | finance-analyzer 三表完成度审计 | Cursor Subagent (explore) | finance 仓库实地代码调查 | — | 推翻"硬卡三表测试"原方案，改为 3 个具体契约（C1/C2/C3） | 见 §3 |
| 2 | 2026-05-09 | 多主体核算与品类制造费率补充评审报告 | Manus AI | 多主体方案 + 品类费率 | ~70% | 制造费拆 3 类 + 4 个固定费用池 + cost_center/work_team + 三视图（FI/CO/Group） | [`/home/admin/ai-costing-system/DOC/基础表单/多主体核算与品类制造费率补充评审报告.md`](../../../基础表单/多主体核算与品类制造费率补充评审报告.md) |
| 1 | 2026-05-09 | 专业版盈亏分析模块初步评审报告VI | Manus AI | v1 整体架构 | ~80% | Phase 1 严格收敛为"订单利润作战室 MVP" + 三层利润 + 成本快照 + 5 类亏损规则 | [`/home/admin/ai-costing-system/DOC/基础表单/专业版盈亏分析模块初步评审报告VI.md`](../../../基础表单/专业版盈亏分析模块初步评审报告VI.md) |

---

## §1. Manus 第一轮评审 - 关键采纳点

**评审日期**：2026-05-09
**评审范围**：6 份 v1.0 文档（pnl 总图 + price + transfer + sku + finance + checklist）
**总评**：方案方向对，但偏"大而全"，必须收敛为 MVP

### 完全采纳（生效到 v1.1）

1. ✅ Phase 1 收敛为"订单利润作战室 MVP" → `pnl_decision_log.md` 决策 #10
2. ✅ `shipment_pnl_lines` 提到 Phase 1（核心底座）→ 决策 #11
3. ✅ 三层利润 GM1/GM2/NP3 → 决策 #12
4. ✅ 砍 SKU 看 GM1，不看 NP3 → 决策 #13
5. ✅ 5 类亏损分类 → 决策 #14
6. ✅ `cost_snapshot_id` + 6 个版本字段 → 决策 #15
7. ✅ `monthly_cost_variance` 月度差异分摊 → 决策 #16
8. ✅ 转移价 + 市场线锚定 → 决策 #17
9. ✅ 幅宽措辞改"标准下料占用面积" → 决策 #19
10. ✅ 成本优化机会榜（按可节省金额排序）→ Phase 2

### 部分采纳

- 命名"订单利润作战室"作为别名，主名仍叫"专业版盈亏分析模块"

### 不采纳（已写入 `pnl_module_handover.md` §8）

- ❌ 完全没提到多主体核算与品类制造费率（他没看到我们 §7.5 / 决策 6）→ 不是反对，是不知道

---

## §2. Manus 第二轮评审 - 关键采纳点

**评审日期**：2026-05-09
**评审范围**：多主体核算（决策 6）+ 品类制造费率
**总评**：多主体核算必须由 finance 侧单独做调节层；品类需分但不要一步分到 SKU

### 完全采纳

1. ✅ 制造费拆 3 类（变动 / 固定 / 异常）→ 决策 #21
2. ✅ 4 个固定费用池（工厂固定 / 运营固定 / 集团管理 / 异常战略）→ 决策 #22
3. ✅ `shipment_pnl_lines` 加 `cost_center_id / work_team_id / factory_legal_entity` → 决策 #23
4. ✅ 三视图（FI / CO / Group）→ 决策 #24（但用 SQL 视图实现，无需新表）
5. ✅ 费用按动因分摊矩阵（房租按面积 / 客服按订单数 ...）→ finance §7.5.5·b

### 不采纳（重要！必读）

- ❌ **在 finance 端建 `management_accounting_adjustment` 表** → 决策 #25
  - 理由 1：finance 端已有"按主体三表"雏形（用户透露），重复建设
  - 理由 2：我们 ai-costing 端已有 `cost_allocation_rule` + `employee_attribution`，本质就是"管理会计调整账"
  - 理由 3：finance ↔ ai-costing 已双向耦合，再加新表会让协调成本暴增

- ❌ **`shipment_profit_fact` 加 `intercompany_elimination_flag`** → Phase 1 工厂还没真按转移价开票，加了用不上

- ❌ **`allocation_rule_version` 直接落 pnl_lines** → 已通过 `cost_snapshot.material_price_version` 等版本号实现

- ❌ **每条 pnl_line 加 `management_adjustment_amount`** → Phase 2 用 `monthly_variance_allocated` 已覆盖

### 给 Manus 的反馈（如需第三轮评审）

下次给 Manus 评审时**必须先告诉他**：
1. 我们已经做了多主体核算（§7.5）+ 决策 6
2. finance 端已有按主体三表（不要建议在那边新建表）
3. ai-costing 当前架构是 `cost_allocation_rule` + `employee_attribution`，不是空白

---

## §3. finance 仓库实地审计（Cursor Subagent）

**评审日期**：2026-05-09
**评审方式**：只读 explore subagent 实地读 `/home/admin/projects/finance-analyzer/` 仓库代码
**评审范围**：finance 端 3 个领域报表的实际完成度
**总评**：架构存在但远不如想象的成熟；硬卡测试通过会卡死自己（双向耦合）

### 关键发现（推翻原方案）

1. **三个报表 ≠ 三张表**：
   - 现金流领域 = `ledger_monthly_summaries`（不是标准现金流量表）
   - 权责制领域 = `accrual_snapshots` + `store_ops_reports`
   - 税务领域 = `tax_declarations` + `tax_declaration_items`

2. **没有 `legal_entity` 字段**：主体键是 `company_id (UUID)` + `company_name`（规范全称）

3. **双向耦合已存在**：`finance/accrual_report` 反向调用 `ai-costing/costing_system_client`

4. **关键路径自动化测试覆盖近零**：
   - `/accrual-report/pl-summary` 无 pytest
   - `/tax/declarations` 无 pytest
   - `/accrual/snapshots/refresh` 无 pytest
   - `/store-ops-report` 无 pytest

5. **店铺未独立成 ID**：`StoreOpsReport` 用 `store_name + platform`

### 推翻的原方案

- ❌ **硬卡 finance 三表测试通过才启动 Phase 1** → 决策 #26
  - 理由：双向耦合下硬卡 = 卡死自己；finance 也在等我们的 ai-costing 才能完成权责利润

### 取代方案：3 个具体契约（C1/C2/C3）

详见 `finance_analyzer_integration_v1.md §9`：
- **C1 主体标识契约**：finance 提供 7 法人 UUID + 规范全称 + 业务别名对照表
- **C2 API 关键路径冒烟测试**：finance 1 周内为 4 个核心接口加 pytest（5-10 case，覆盖率 ≥ 60%）
- **C3 双向 SLA 与鉴权**：双方互发 token + 互签 SLA + 实现降级

### 完整原文

由于 subagent 输出在 chat 中已显示给用户，本目录暂未单独存档。如需查证：
- chat 时间：2026-05-09 08:25-08:29
- 主线 Agent ID 见 `pnl_decision_log.md` 决策 #26 关联

---

## §4. Manus 第三轮评审 - 关键采纳点

**评审日期**：2026-05-09
**评审范围**：Cost Rate Hub v1.0 设计文档
**总评**：方向高度一致，但 v1.0 设计偏轻；需要"留好扩展骨架，避免 Stage 3 时返工"

### 完全采纳（生效到 cost_rate_hub_design v1.2）

1. ✅ **8 面板架构（v1 实做 2，留 6 个槽位）** → 决策 #47 + Hub v1.2 §7
   - Tab 1 总览 / Tab 2 编辑（v1）
   - Tab 3 财务月度录入 / Tab 4 影响分析 / Tab 5 学习曲线 / Tab 6 SKU 角色 / Tab 7 量价档位 / Tab 8 治理健康度（Stage 2/3）

2. ✅ **4 个组织概念正交（首次提出，第五轮校正）** → 决策 #42
   - production_unit / purchase_entity / cost_center / legal_entity
   - 注：Manus 第三轮把 `factory` 当作 v1 必需维度，第四轮被用户校正（见 §5）

3. ✅ **rate_type 扩展为 3 种** → Hub v1.2 §1.1
   - `labor_per_minute` + `labor_per_piece` + `labor_per_sqm` + `overhead_rate`

4. ✅ **cost_pool + allocation_basis 字段** → Hub v1.2 §4.3
   - `overhead_rate_master.allocation_basis`: 'headcount' / 'team_hours' / 'revenue' / 'floor_area' / 'fixed_pct'

5. ✅ **已结账月不可改硬规则** → 决策 #38（升级）+ Hub v1.2 §1.1 §11 R1
   - "已结账月份的 `shipment_costing_results` 快照永远不可被费率变更影响"
   - 实现方式：触发器 + Tab 2 编辑器 UI 警告

6. ✅ **scope_type 留 8 层 enum**（v1 实做 4 层）→ 决策 #44 + Hub v1.2 §5
   - v1 实做：global / category / cost_center / model
   - 留位：production_unit / purchase_entity / legal_entity / sku_role / volume_tier

7. ✅ **cost_quality 三色徽章 + Insights 可见** → 决策 #31 + Hub v1.2 §1.1
8. ✅ **变更必须附凭证（supporting_doc_url）** → Hub v1.2 §4.3
9. ✅ **撤销最近 1 次变更窗口** → 评审会决策点 H3
10. ✅ **API 版本化 `/v1/...`** → Hub v1.2 §6 扩展点 4
11. ✅ **治理健康度看板（Tab 8 Stage 3）** → Hub v1.2 §7

### 部分采纳

- 🟡 **factory 维度作为 v1 必需** → 第五轮校正，仅在 Phase 2 用 production_unit + purchase_entity 替代

### 不采纳

- ❌ **新建 cost_rate_master 主表统管所有费率** → 决策 #43
  - 理由：现状审计发现 `processes` + `materials` 已覆盖 80% 能力，重写会造成双轨数据不一致

---

## §5. Manus 第四轮评审 - factory 维度校正

**评审日期**：2026-05-09
**评审范围**：第三轮中"factory 是 v1 必需"的建议在用户业务事实下的修正
**触发事件**：用户回应"我们 3 法人物理一体在一栋楼，不会出现同商品两个工厂做"
**总评**：第三轮的方向对，但 factory 一刀切式建模错了，要拆成 4 个正交概念

### 关键校正（推翻第三轮的 factory 部分）

| 第三轮主张 | 第四轮校正 | 决策 |
|---|---|---|
| 用单一 factory 字段表达"在哪生产/谁采购/费用归谁/谁报税" | **拆成 4 个正交字段**：`production_unit_id` / `purchase_entity_id` / `cost_center_id` / `legal_entity_id` | #42 |
| factory 是 v1 必需 | v1 仅 cost_center 必需；其余 3 个概念按需在 Stage 2/3/Phase 2 加 | #41 + #42 |
| KB8 在不同工厂可能成本不同 | KB8 在 1 个生产体系做（一栋楼一支生产队伍）；不会产生工厂间差异 | #41 |

### 采纳的具体动作

1. ✅ Hub v1 不引入 factory 维度 → 决策 #41 + Hub v1.2 §0.1
2. ✅ 4 概念正交拆分写入 Hub v1.2 §0.2
3. ✅ cost_center 作为 v1 唯一新引入的"生产/费用归集"维度 → 决策 #44 + Hub v1.2 §5
4. ✅ purchase_entity 推迟到 Stage 2 物料端，作为 `materials` 表的字段而不是 `cost_rate` 的 scope → 决策 #45 + Hub v1.2 §4.5
5. ✅ legal_entity 推迟到 Phase 2 三视图（FI/CO/Group）→ 决策 #24（已生效）

### 文档影响

- `cost_rate_hub_design_v1.md` 由 v1.0 升级为 **v1.2**（跳过 v1.1）
- `pnl_decision_log.md` 加决策 #40-#47（其中 #41/#42 直接来自第四轮）
- `pnl_module_handover.md` §0 加业务事实陈述
- 评审会决策点新增 H4（cost_center 初稿清单老板拍板）

---

## 评审报告归档原则

1. **原文必须存档**：哪怕方案被推翻，原报告必须保留
2. **采纳决策必须留痕**：每个评审建议对应到 `pnl_decision_log.md` 的某条决策
3. **不采纳的也要写**：标注"不采纳 + 理由"，避免后人重复讨论
4. **下次评审前看一眼**：如果有新评审进来，先看本索引判断"是不是已经评过了"

---

## 元信息

| 项 | 值 |
|---|---|
| 文档版本 | **v1.2** |
| 创建日期 | 2026-05-09 |
| 维护节奏 | 评审到来时随时更新 |
| 当前评审数 | **5 份** |
| v1.2 更新 | 加 §4 Manus 第三轮（Cost Rate Hub）+ §5 Manus 第四轮（factory 校正） |
