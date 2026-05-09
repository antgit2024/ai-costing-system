# Phase 0 评审清单（四方评审，v1.2）

> 状态：等待签字
> 目的：在启动 Phase 1 编码前，让财务 / 工厂 / 运营 / finance-analyzer 团队四方对"价格成本盈亏分析专业版"的核心口径达成一致
> 评审会建议时长：3 小时（含 Hub 决策追加 30 min）
> 评审会建议参与人：老板 + 集团财务负责人 + 工厂总账 + 运营负责人 + HR + 班组长代表 + finance-analyzer 技术负责人 + ai-costing 技术负责人
>
> **v1.2 关键变化（必读，2026-05-09 重大修订 + 当日二次校准）**：
>
> **首次重大转向**（决策 #29-#39）：
> - **现状审计发现**：4 个 Insights 看板（4170 行）+ shipment_costing_results 表已生产 → Phase 1 改为"增量改造"而非新建（决策 #29）
> - **Phase 1 顺序倒过来**：「数据可信度治理」优先，「决策语言」（GM1/GM2/NP3、5 类亏损）后置（决策 #30）
> - **新增 Phase 1 核心交付物：Cost Rate Hub**（成本费率与费用归集中枢，决策 #34）— 把"算法依赖"降级为"治理依赖"
> - **三阶段路线**：Stage 1 Hub 骨架（2.5-3 周）→ Stage 2 物料做实（1 周）→ Stage 3 专业能力按需扩展（无限期）
>
> **当日二次校准**（决策 #40-#47）：
> - 🆕 **关键事实校准**：3 法人物理一体在一栋楼，是 1 个生产体系 → Hub 不分 factory（决策 #41）
> - 🆕 **4 个组织概念正交拆分**（来自 Manus 第四轮评审，决策 #42）：production_unit / purchase_entity / cost_center / legal_entity
> - 🆕 **现状审计校准**：复用现有 4 个页面（ProcessesPage 1027 + ProcessModulesPage 3039 + MaterialMasterPage 1956 + VirtualMaterialsPage 2434 = 8456 行 UI）+ 5 张后端表 → 不新建 cost_rate_master 主表（决策 #43）
> - 🆕 **Hub v1 优先级链 4 层**：model > category > cost_center > global（schema 留 8 层枚举，决策 #44）
> - 🆕 **Stage 2 物料端 4 字段**：`materials` 加 purchase_entity_id / tax_included_flag / tax_rate / price_source / effective_from（决策 #45）
> - 🆕 **新建 cost_center 表（5-7 行数据）**：与现有 processes.team_name 共存（决策 #46）
> - 🆕 **Hub 控制台 8 面板架构**：v1 实做 Tab 1+2，留 6 个槽位 Stage 2/3 加（决策 #47）
> - 🆕 **新增 H4 决策点**：cost_center 初稿清单老板拍板
>
> **专业能力（sku_role / volume_tier / 学习曲线 / 单位时间毛利）通过 Hub 接口扩展**，算法层不动（决策 #35）
> **物料成本不进 Hub 主表**，做稳做实路线（决策 #36）
> **Hub v1 必须做 cost_snapshot 锁版本 + 已结账月不可改硬规则**（决策 #38 升级），防止改费率污染历史
>
> **早期已采纳**：
> - Manus 外部评审第 1 轮：Phase 1 收敛为「订单利润作战室 MVP」
> - Manus 外部评审第 2 轮：制造费拆 3 类 + 4 个固定费用池 + 三视图（FI/CO/Group）
> - 转移价"市场线约束 + 高于同行报警 + 战略补贴单独入账"
> - 月度差异分摊 `monthly_cost_variance` 表 + 异常拦截（Phase 2）
>
> **外部评审录档**（5 份）：`DOC/基础表单/专业版盈亏分析模块初步评审报告VI.md` + `多主体核算与品类制造费率补充评审报告.md` + `成本参数Hub与月度调节面板：评审与设计建议.md` + `对用户解答的二次评审：factory 维度修正版结论.md` + finance 仓库实地审计

---

## 一、本轮 Phase 0 交付物（6 份核心 + 2 份外部评审）

请评审前**至少粗读以下文档**：

| 文档 | 路径 | 主要受众 | 评审重点 |
|---|---|---|---|
| 总图（必读） | [pnl_analytics_module_design.md](../blueprints/pnl_analytics_module_design.md) v1.1 | 全员 | 整体架构、4 个 Phase 节奏 |
| **Cost Rate Hub v1.2（Phase 1 核心，本版重大变化）** | [cost_rate_hub_design_v1.md](../blueprints/cost_rate_hub_design_v1.md) | 全员 | 数据治理中枢、复用现有 Process/Material、4 概念正交、cost_center 上层归集、4 层优先级链、8 面板架构 |
| **外部评审 §4 §5（NEW v1.2）** | [pnl_external_reviews/INDEX.md](./pnl_external_reviews/INDEX.md) | 全员 | Manus 第三轮（Hub 设计建议）+ 第四轮（factory 维度修正） |
| 价格计算 v2.1 | [price_calculation_guide.md](../manuals/guides/price_calculation_guide.md) | 财务+工厂 | 三层价格 + 三层利润 + 月度反推 + 标准下料占用面积 |
| 内部转移价手册 | [transfer_pricing_handbook.md](../manuals/transfer_pricing_handbook.md) | 财务+老板 | 工厂利润率参数 + 四线约束（成本/市场/税务/战略） |
| SKU 组合管理 v1.1 | [sku_portfolio_management_v1.md](../blueprints/sku_portfolio_management_v1.md) | 运营+老板 | SKU 角色 + 5 类亏损决策规则（健康度评分延后到 Phase 3） |
| finance 集成方案 v1.1 | [finance_analyzer_integration_v1.md](../blueprints/finance_analyzer_integration_v1.md) | 技术+finance 团队 | API 契约 + 多主体合并 + 月度差异分摊 |
| 外部评审报告 1 | [专业版盈亏分析模块初步评审报告VI.md](../../基础表单/专业版盈亏分析模块初步评审报告VI.md) | 全员 | Manus AI 第一轮，已采纳关键建议 |
| 外部评审报告 2 | [多主体核算与品类制造费率补充评审报告.md](../../基础表单/多主体核算与品类制造费率补充评审报告.md) | 全员 | Manus AI 第二轮，多主体与品类费率 |

---

## 二、必须签字的 12 个核心决策（8 原决策 + 4 个 Hub 决策 H1/H2/H3/**H4**，v1.2 当日二次校准新增 H4）

> **⚠️ 重大顺序变更**：
> - 决策 1（制造费率反推）+ 决策 2（班组单价反推）的**实现路径**改为"经 Cost Rate Hub 治理"，不再是直接接 finance API
> - 决策 6.c（finance 三表）的"硬卡点"降级为"弱依赖"——Hub v1 上线**不阻塞 finance C2 测试**
> - 新增决策 H1/H2/H3 是 Cost Rate Hub v1 的初始化与治理边界
> - 🆕 新增决策 H4 是 cost_center 初稿清单（v1.2 当日校准后必须老板签字）

### 决策 1：制造费率从"写死 0.3"改为"月度从 finance 反推"

> 关联：`price_calculation_guide.md §3` + `finance_analyzer_integration_v1.md §3.1`

**当前现状**：6 处代码写死 `Decimal("0.3")`，导致同行卖 26 元，我们算出 44.55，运营拿不下手。

**新方案**：
- 每月 5 号 cron 自动从 finance `GET /api/v1/ledger/summaries?period=YYYYMM` 取真实间接费
- 反推公式：`制造费率 = 当月间接费 / (当月直接物料 + 当月直接人工)`
- 三级回退：finance API → 手工配置 → 兜底 0.3
- 月度差异 > 5% 自动钉钉报警

**评审打勾**：

- [ ] **财务负责人确认**：哪些会计科目算"间接费"？请按下面 finance 已有的科目代码勾选：

| finance 科目代码 | 名称 | 是否计入间接费？ |
|---|---|---|
| A01 | 管理费用 纳税社保 | [ ] 是 [ ] 否 |
| A05 | 管理费用 折旧 | [ ] 是 [ ] 否 |
| A06 | 管理费用 办公 | [ ] 是 [ ] 否 |
| A08 | 管理费用 物流费用 | [ ] 是 [ ] 否（建议否，单列运费） |
| A18 | 管理费用 租金/物业 | [ ] 是 [ ] 否 |
| A19 | 管理费用 水电费 | [ ] 是 [ ] 否 |
| A21 | 管理费用 劳务费（非生产） | [ ] 是 [ ] 否 |
| C05 | 财务费用 手续费 | [ ] 是 [ ] 否 |
| D01 | 采购应付款 主材 | [ ] 是 [ ] 否（建议否，是直接物料） |

- [ ] **代账会计确认**：上述清单符合现行会计准则
- [ ] **老板批准**：制造费率不再写死 0.3，可能导致单 SKU 成本浮动

---

### 决策 2：班组单价从"拍脑袋"改为"finance 反推"

> 关联：`price_calculation_guide.md §2.2` + `finance_analyzer_integration_v1.md §3.2`

**当前现状**：班组单价用 `月工资 / (26×8×60×0.85)`，**不含社保福利**，效率系数 0.85 偏高。

**新方案**：
- 每月 5 号 cron 自动从 finance `GET /api/v1/employees/labor-costs?period=YYYYMM` 取真实人工
- 公式：`单价 = (工资+社保+公积金+福利) / (人头数 × 26 × 8 × 60 × 效率系数)`
- 效率系数按班组类型分档（缝纫 0.7、质检 0.6、打包 0.8）

**评审打勾**：

- [ ] **财务负责人确认**：finance 是否已有 `/api/v1/employees/labor-costs` endpoint？
  - [ ] 是，返回字段含 salary / social / housing / welfare / headcount
  - [ ] 否，需要 finance 团队本次开发新增（约 3 天工作量）

- [ ] **工厂总账确认**：当前各班组分组与人头数清单
  - [ ] 已建立班组主数据
  - [ ] 待建立（需要工厂提供清单）

- [ ] **工厂总账确认**：效率系数 0.7 是否合理？
  - [ ] 同意（缝纫/裁剪/印刷 默认 0.70）
  - [ ] 调整为：______
  - [ ] 不区分班组类型，全员用 ______

---

### 决策 3：物料用量按"原料幅宽切割"算（解决 70/90 不公平）

> 关联：`price_calculation_guide.md §1.2`

**当前现状**：120cm 原料切 70cm 产品和 90cm 产品，废料率分别是 42% 和 25%，但 v1 都按"产品面积 × 损耗率"算，70cm 产品反而被算便宜了。

**新方案**：
- `Material` 表新增 `roll_width_mm` 字段
- 计算口径新增 `area_with_cutting`：`实际消耗 = ceil(产品宽 / 原料宽) × 原料宽 × 产品长`
- 边角料按"边角料价值率"冲减（默认 0.30，可按物料类型调整）

**评审打勾**：

- [ ] **工厂总账确认**：1500+ 物料中，"卷材/板材类"占比？
  - [ ] 主要物料（80%+）→ 必须 Phase 1 全量补幅宽
  - [ ] 部分物料（30-80%）→ 按品类批量补默认值
  - [ ] 少量物料（<30%）→ 仅给关键 SKU 补

- [ ] **采购确认**：原料幅宽数据来源
  - [ ] 采购系统/物料主数据有
  - [ ] 需要采购人工补录（多少天能补完？_____）

- [ ] **运营确认**：边角料是否回收？回收率多少？
  - [ ] 默认 0.30 合理
  - [ ] 调整为：_____

---

### 决策 4：引入"内部转移价"机制（含市场线约束）

> 关联：`transfer_pricing_handbook.md` 全文

**新方案**：
- 给每个 SKU 算 8 个价格层（变动/全成本/转移价/批发/零售）
- 工厂目标利润率按品类分档（常规 8-12%，定制 15-20%）
- 月度调节系数 = 1 - (上月实际利润率 - 目标) × 0.5
- 财务+老板每月 10 号前双签锁定本月转移价

**评审打勾**：

- [ ] **老板确认**：愿意按"工厂全成本 × (1 + 8-12%)"作为运营采购成本
  - [ ] 同意
  - [ ] 利润率太低，调整为 _____
  - [ ] 反对，按其他方式

- [ ] **集团财务确认**：每月 5-10 号能完成"调节系数计算 + 三方评审 + 双签锁定"流程
  - [ ] 能
  - [ ] 流程需要简化（说明：_____）

- [ ] **工厂确认**：理解"工厂全成本"和"内部转移价"是不同口径
  - [ ] 理解
  - [ ] 需要培训

- [ ] **运营确认**：理解"内部转移价"作为采购成本来对外报价
  - [ ] 理解
  - [ ] 需要培训

- [ ] **税务/代账会计确认**：内部转移价的关联交易开票合规
  - [ ] 当前转移价区间符合公允性要求
  - [ ] 需要调整以避免税务风险

- [ ] **采购+老板确认（v1.1 新增）**：转移价 4 线约束的"市场线"数据来源（详见 `transfer_pricing_handbook.md §二·补`）
  - [ ] 同意：1688 / 拼多多 / 同行询价单 季度采集，落 `market_price_reference` 表
  - [ ] 同意：转移价 > 市场线 × 1.05 触发"工厂成本竞争力不足"报警（不强制压价）
  - [ ] 同意：引流 / 清仓 / 爆款打造时低于全成本 → 走特批 + 单独入"战略补贴账"

---

### 决策 5：SKU 角色与店铺组合管理（v1.1 收敛）

> 关联：`sku_portfolio_management_v1.md` 全文

**新方案**：
- 每个 SKU 打一个角色标签：引流款 / 利润款 / 形象款 / 清仓款 / 新品
- 引流款允许在"亏损池预算"内合理亏损（默认店铺月度目标净利的 10-15%）
- 店铺月度组合健康度评分（0-100），失衡自动报警
- 下架决策必须经过"组合影响评估"，不能凭单 SKU 数字一刀切

**评审打勾**：

- [ ] **运营负责人确认**：5 种 SKU 角色定义合理
  - [ ] 同意（traffic / profit / brand / clearance / new）
  - [ ] 需要新增/合并：_____

- [ ] **运营负责人确认**：默认组合配比合理
  - [ ] 流量型新店：traffic 30-40% / profit 50-60% / brand 5-10%
  - [ ] 成熟主力店：traffic 15-25% / profit 60-75% / brand 10-15%
  - [ ] 调整为：_____

- [ ] **运营负责人确认**：引流亏损池预算公式
  - [ ] 默认 = 店铺月度目标净利 × 10-15%
  - [ ] 调整为：_____

- [ ] **店铺运营确认**：愿意每月 1 号前在系统设定本月组合计划
  - [ ] 同意
  - [ ] 流程需要简化

- [ ] **老板确认**：支持"不再凭单 SKU 亏损一刀切下架"的判断逻辑
  - [ ] 同意
  - [ ] 反对（理由：_____）

- [ ] **运营+老板确认（v1.1 新增）**：5 类亏损 SKU 决策规则（详见 `sku_portfolio_management_v1.md §1.4`）
  - [ ] 同意：`true_loss / op_loss / fullcost_loss / traffic_loss / data_anomaly / profit` 6 类自动分类
  - [ ] 同意：**砍 SKU 优先看 GM1（贡献毛利一）**，不看 NP3（全成本利润三）
  - [ ] 同意：`fullcost_loss` 决策权交财务+老板，不能运营自动下架
  - [ ] 同意：组合健康度评分 + 下架决策工作流 **延后到 Phase 3**，Phase 1 仅出"建议动作"

---

### 决策 6：多主体核算与品类制造费率（多法人 + 店铺级独立核算）

> 关联：`finance_analyzer_integration_v1.md §7.5`

**当前现状**：
- 工厂端 3 法人（1 一般纳税人 + 2 小规模），实际办公在一起，房租分散在 2 家、生活/办公等共用费用集中在 1 家
- 运营端 4 法人，单独报税，**1 个法人下可能有多个店铺**，固定开支集中在 1 家大公司付，人员在多家法人间随意发薪
- finance 端目前未按"管理口径"做合并；品类（家居饰品 / 家居布艺）工艺人员差距 10 倍（4-5 人 vs 4-50 人），统一费率必失真

**新方案**：
- **三层主体模型**：法人(L1) → 经营单元 BU(L2，每法人 = 1 BU) → 店铺/班组/品类(L3)
- finance 端**不做核算调节**，只暴露"按月 × 按法人 × 按科目"明细；**调节全部放在 ai-costing**
- 新增 `legal_entity` / `business_unit` / `shop_master` / `employee_attribution` / `cost_allocation_rule` / `category_overhead_rate_history` 6 张表
- 制造费率 **从 Phase 1 起就按品类分**（替代原计划的"先一个工厂费率"），按班组工时占比分摊间接费到品类
- 人工成本与"在哪个法人发薪"解耦，用 `employee_attribution` 表分摊

**评审打勾**：

- [ ] **集团财务负责人确认**：同意"finance 不动法人账、ai-costing 在上层做管理口径合并"
  - [ ] 同意
  - [ ] 反对，希望 finance 直接出"管理口径报表"（说明：_____）

- [ ] **集团财务负责人确认**：法人 → BU 映射初稿（每法人对应 1 个 BU）
  | 法人主体 | 主体类型 | BU code | BU 名称 | 备注 |
  |---|---|---|---|---|
  | 工A | 一般纳税人 | bu_factory_a | _____ | _____ |
  | 工B | 小规模 | bu_factory_b | _____ | _____ |
  | 工C | 小规模 | bu_factory_c | _____ | _____ |
  | 运A | 主体 | bu_op_a | _____ | 含店铺：_____ |
  | 运B | 主体 | bu_op_b | _____ | 含店铺：_____ |
  | 运C | 主体 | bu_op_c | _____ | 含店铺：_____ |
  | 运D | 主体 | bu_op_d | _____ | 含店铺：_____ |
  - [ ] 此 7-BU 映射可用
  - [ ] 调整为：_____

- [ ] **集团财务+老板确认**：跨法人共享开支的分摊基准（首批关键科目）
  | 共享开支 | 发生在哪家法人 | 拟分摊到 | 分摊基准 | 比例/规则 |
  |---|---|---|---|---|
  | 房租 / 物业 | _____ | 工厂 BU 群 / 运营 BU 群 | fixed_pct | _____ / _____ |
  | 水电 | _____ | 工厂 BU 群 / 运营 BU 群 | floor_area | 按实际占用 |
  | 办公用品 | _____ | 全 BU | headcount | 按人头 |
  | 后勤工资 | _____ | 工厂 BU 群 / 运营 BU 群 | headcount | 按服务对象 |
  | 共享广告 | _____ | 各运营 BU 旗下店铺 | revenue | 按上月营收 |
  - [ ] 上述基准合理
  - [ ] 调整为：_____

- [ ] **HR + 工厂厂长 + 运营负责人确认**：员工归属表 (`employee_attribution`) 维护方
  - [ ] 工厂员工归属由工厂厂长 + 班组长每季度复核
  - [ ] 后勤/管理员工归属由 HR + 集团财务每季度复核
  - [ ] 运营员工归属由集团运营 + HR 每季度复核
  - [ ] 调整为：_____

- [ ] **工厂总账确认**：品类制造费率从 Phase 1 起就分（替代"先统一一个工厂费率"的原计划）
  - [ ] 同意（按班组工时占比把 BU 月度间接费分摊到品类）
  - [ ] 反对，原因：_____
  - [ ] 同意但希望先跑 1-2 个月统一费率作对照

- [ ] **运营负责人确认**：店铺级独立 P&L（含同一法人下多店铺）
  - [ ] 需要店铺级 P&L
  - [ ] 只看 BU 级即可，店铺级延后

- [ ] **税务/代账会计确认**：跨法人分摊的 "管理口径" 与 finance 法人账并存
  - [ ] 不影响税务对账（分摊结果只用于内部考核 / 决策）
  - [ ] 担心：_____

- [ ] **finance 团队确认**：能否提供"按月 × 按法人 × 按一级科目"明细导出（对应 `finance_analyzer_integration_v1.md §4.1.2 monthly_summary` 接口）
  - [ ] 已有，按法人维度可过滤
  - [ ] 已有，但需要按法人维度新增过滤参数（约 1 天工作量）
  - [ ] 当前只能按全集团出，需要新开发（约 3 天工作量）

---

### 决策 6.b：管理会计深化（v1.1 新增 / 第二轮外部评审）

> 关联：`finance_analyzer_integration_v1.md §7.5.4·b / §7.5.5·b / §7.5.10 / §7.5.11`，`price_calculation_guide.md §3.0`

**当前现状**：v1.1 第一轮已加多主体核算（决策 6），但 Manus 第二轮评审指出仍欠 4 个深化点：
1. 制造费需拆"变动 / 固定 / 异常"三类，而非一个综合费率；
2. 固定费用需归集到"工厂固定 / 运营固定 / 集团管理 / 异常战略"4 个池，分摊路径与决策用途完全不同；
3. `shipment_pnl_lines` 还应加 `cost_center_id` + `work_team_id` + `factory_legal_entity` 字段，做到管理维度可下钻；
4. 必须明确"经营 / 法人 / 集团合并"三视图切换，砍 SKU 决策只在经营视图生效。

**评审打勾**：

- [ ] **集团财务+老板确认**：制造费在 finance 端按 `rate_type = variable / fixed / abnormal` 三类归集
  - [ ] 同意 Phase 1 至少先拆"变动 / 固定"两类
  - [ ] 同意"异常制造费永远不摊到单 SKU"（单独立项 + 财务追责）
  - [ ] 同意 GM1 仅含变动制造费，固定制造费仅进 NP3

- [ ] **集团财务+老板确认**：4 个固定费用池映射（详见 §7.5.4·b）
  - [ ] 同意：`pool_factory_fixed`（进 NP3，不进 GM1）
  - [ ] 同意：`pool_ops_fixed`（进店铺 P&L，不进单 SKU）
  - [ ] 同意：`pool_group_overhead`（仅进集团合并，**完全不压到任何 SKU**）
  - [ ] 同意：`pool_abnormal_strategic`（与 `strategic_subsidy_log` 协同，单独列示）

- [ ] **集团财务+老板确认**：费用按动因分摊矩阵首批（详见 §7.5.5·b）
  - [ ] 房租 → `pool_factory_fixed`，按面积分摊 ✓
  - [ ] 水电气 → `pool_factory_fixed`，按机器工时 / 产值 ✓
  - [ ] 客服工资 → `pool_ops_fixed`，按订单数 / 咨询量 ✓
  - [ ] 老板办公室/集团行政 → `pool_group_overhead` ✓
  - [ ] 引流补贴 / 清仓补贴 / 质量事故 → `pool_abnormal_strategic` ✓
  - [ ] 同意"分摊规则最快每季度调整一次，不能为某主体好看每月动"

- [ ] **工厂总账确认**：成本中心 + 班组主数据（详见 §7.5.10）
  - [ ] 工厂端能列出 `cost_center` 完整清单（如 cc_factory_a_cutting / cc_factory_a_sewing / cc_factory_a_packing）
  - [ ] 工厂端能给每个 `work_team` 配 `efficiency_factor`（缝纫 0.70 / 质检 0.60 / 打包 0.80 等）
  - [ ] 工厂端同意每月给 MES / 工时打卡里"班组工时占比"作为固定费用分摊基数

- [ ] **运营+老板确认**：三视图切换（详见 §7.5.11）
  - [ ] 同意 SKU 利润详情页 / 赚钱榜亏钱榜 默认走"经营视图（CO）"
  - [ ] 同意"砍 SKU 决策仅在经营视图下生效"（法人视图的负 GM1 可能只是开票归属问题）
  - [ ] 同意"集团合并视图"老板专享，含全部费用 + 内部交易抵消

- [ ] **税务/合规顾问确认**：`legal_entity` 与 `factory_legal_entity` 双轨字段不影响税务对账
  - [ ] 销售开票法人 = `legal_entity`（沿用现行口径）
  - [ ] 实际生产法人 = `factory_legal_entity`（用于工厂效率核算，不影响开票）

---

### 决策 6.c：finance 集成的 3 个前置契约（v1.1 修订 / 已采纳 finance 仓库调查结论）

> **背景修订（2026-05-09 调查后）**：原计划"硬卡三表测试通过"在调查 finance-analyzer 仓库后被推翻。实际情况是：
> - finance 端是 **3 个领域**而非 3 张同构物理表：① ledger 月汇总（`ledger_monthly_summaries`）= 现金流事实；② 权责快照 + 店铺月报（`accrual_snapshots` + `store_ops_reports`）= 权责制；③ 税务申报（`tax_declarations`）= 报税。
> - **没有 `legal_entity` 字段**——主体键是 `company_id (UUID)` + `company_name (规范全称)`。
> - **双向耦合已存在**：finance 的 `accrual_report` **反向调用 ai-costing** 的 BOM/利润 API（`costing_system_client`），硬卡 finance 测试 = 也卡死自己。
> - **核心接口测试覆盖近零**：`pl-summary` / `tax declarations` / `snapshots refresh` / `store-ops-report` 4 个关键接口几乎无 pytest。
>
> **修订方案**：放弃"硬卡三表测试"，改为**签 3 个具体契约**——这 3 件事 1 周内能交付，签完即可启动 ai-costing Phase 1。

**评审打勾**：

- [ ] **契约 C1 — 主体标识契约**（详见 `finance_analyzer_integration_v1.md §9.1`）
  - [ ] finance 团队提供 `company_id (UUID) + company_name (规范全称) + 业务别名（工A/工B...）` 三者的对照表
  - [ ] ai-costing 端建 `legal_entity_alias_map` 表消费此映射
  - [ ] **本次评审会现场签字**：业务别名清单（7 法人）已确认
  - [ ] 评审后 3 天内 finance 提交规范全称 + UUID 列表
  - 责任人：finance 技术 + 集团财务

- [ ] **契约 C2 — API 关键路径冒烟测试**（详见 `finance_analyzer_integration_v1.md §9.2`）
  - [ ] finance 团队承诺 1 周内为以下 4 个接口加 5-10 个 pytest（happy path + 1-2 个错误路径）：
    - [ ] `GET /accrual-report/pl-summary`（按 scope=group/store/factory + company_name 过滤）
    - [ ] `GET /tax/declarations`（按 year + company_id 过滤）
    - [ ] `POST /accrual/snapshots/refresh` 或等价接口
    - [ ] `GET /store-ops-report`（按 period 过滤）
  - [ ] 提供测试 fixtures（至少 1 个法人 1 个月真实数据脱敏样本）
  - [ ] CI 集成（每次推送跑），ai-costing 团队可订阅 webhook
  - 工作量估算：3-8 人日（subagent 调查结论）；责任人：finance 技术

- [ ] **契约 C3 — 双向耦合 SLA 与鉴权**（详见 `finance_analyzer_integration_v1.md §9.3`）
  - [ ] ai-costing 给 finance 颁发稳定的 `X-PLANNER-ADMIN-KEY`（1 年有效期）
  - [ ] ai-costing 承诺 BOM/利润接口 SLA：响应 ≤ 2s，月度 99% 可用
  - [ ] finance 给 ai-costing 颁发服务账号 token（1 年有效期）
  - [ ] 双方约定降级行为：
    - [ ] finance 调 ai-costing 失败 → 利润里 BOM 成本回退 0，加日志 + 告警，不阻塞接口
    - [ ] ai-costing 调 finance 失败 → 走 `price_calculation_guide.md §3.4` 三级回退（手工配置 / 兜底常量）+ 钉钉告警
  - 责任人：双方技术负责人

- [ ] **3 个契约全部签字 → 立即启动 ai-costing Phase 1 编码**
  - [ ] 同意（不再硬卡 finance 测试通过，因为双向耦合已存在 + Hub v1 弱依赖 finance）
  - [ ] 反对，理由：_____

- [ ] **可与契约并行的 ai-costing 工作**（不必等契约签字）

---

### 决策 H1：Cost Rate Hub v1 全局默认 2 个费率初始值（v1.2 新增）

**背景**：Cost Rate Hub v1 上线时，需要为"全局默认"录入 2 个初始费率。Hub 上线后所有 SKU 计算成本时，没有 model 级 override 时就读这 2 个值。

**需要拍板**：
- [ ] **制造费率 (overhead_rate) 全局初始值**：
  - [ ] 维持当前默认 0.30（`bom_generation_service.py:2047` 写死值，最稳，但仍 🔴 不可信）
  - [ ] 选某月真实反推值（如 4 月反推 0.18 / 0.22 ...）
  - [ ] 其他：_____ （需财务现场算）

- [ ] **班组人工 (process_per_minute) 全局初始值**：
  - [ ] 维持 0.45 元/分钟（v1 公式估算）
  - [ ] 用 4 月全口径工资反推值：_____ 元/分钟
  - [ ] 其他：_____

- 责任人：集团财务 + 老板

---

### 决策 H2：Cost Rate Hub 编辑权限（v1.2 新增）

**需要拍板**：谁可以在 Hub 改费率？

- [ ] **方案 A**：仅财务 + 老板
- [ ] **方案 B**：财务 + 老板 + ai-costing 实施负责人（推荐，便于初期调试）
- [ ] **方案 C**：开放给所有"集团财务部"账号

**所有变更都强制留痕**（cost_rate_history），但**写入权限**需要拍板。

- 责任人：老板

---

### 决策 H3："撤销最近 1 次变更"按钮的可用窗口（v1.2 新增）

**背景**：Hub v1 不做审批流（决策 #39），靠"撤销"按钮做防御。但撤销窗口要多大？

**需要拍板**：
- [ ] 24 小时内可撤销（保守，防止历史数据已锁 snapshot 后的"伪撤销"）
- [ ] 7 天内可撤销（中等）
- [ ] 永久可撤销但需老板二次确认

**关联依赖**：决策 #38 — Hub v1 必须做 `cost_snapshot` 锁版本，否则撤销可能导致历史数据跳变。

- 责任人：老板 + 财务
  - schema migration 编写（独立于 finance 数据）
  - 6 张多主体表 + cost_pool_master + cost_center 等主数据初始化
  - frontend `<ViewSwitcher>` 控件骨架
  - jackyun 发货接入升级（不依赖 finance）

---

### 决策 H4：cost_center 初稿清单（v1.2 当日二次校准新增）

> **背景（必读）**：v1.2 校准把 `factory` 维度替换为 4 个正交概念（决策 #41/#42），其中 `cost_center` 成为 Hub v1 唯一新引入的"生产/费用归集"维度（决策 #44）。需要老板和工厂厂长拍板初稿清单 5-7 个 cost_center，作为 Hub v1 上线时 `processes.team_name → cost_center_id` 数据迁移的前置物。

**Agent 提供的初稿（请评审 + 调整）**：

| code | name（中文） | type | 默认分摊基础 | 备注 |
|---|---|---|---|---|
| CC_DECOR_PROD | 家居饰品生产组 | production | team_hours | 主要承载饰品类工序 |
| CC_FABRIC_PROD | 布艺生产组 | production | team_hours | 主要承载布艺类工序 |
| CC_PRINT | 印花打印组 | auxiliary | machine_hours | 跨品类共享 |
| CC_CUT_EDGE | 裁剪包边组 | auxiliary | team_hours | 跨品类共享 |
| CC_PACK_SHIP | 包装发货组 | auxiliary | order_count | 跨品类共享 |
| CC_ADMIN | 公共管理 | admin | headcount | 不承载产品成本，仅承载固定费 |

**评审打勾**：

- [ ] **工厂厂长确认**：上述 6 个 cost_center 与现实班组对应关系
  - [ ] 完全对应，可直接用
  - [ ] 需新增：_____ （如：质检组 / 五金加工组 / 模板房等）
  - [ ] 需合并：_____ （如：印花 + 裁剪并入"前道工序"）
  - [ ] 需删除：_____

- [ ] **工厂厂长 + 老板确认**：每个 cost_center 与现有 `processes.team_name` 的映射初稿（评审会前由 Agent 准备）
  - [ ] 评审会前 3 天可以提供初步映射表
  - [ ] 评审会现场拍板

- [ ] **集团财务确认**：默认分摊基础是否合理（决定固定费用从池里分摊到 cost_center 的口径）
  - [ ] 同意上述默认值
  - [ ] 调整为：_____

- [ ] **老板确认**：v1 不引入更细粒度的 work_team（班组工时仍走现有 `processes.team_name`），Phase 2 再评估是否拆 work_team 主数据
  - [ ] 同意（v1 简单优先）
  - [ ] 反对，理由：_____

- [ ] **签字承诺**：cost_center 初稿一旦签字，Hub v1 上线后 2 周内不变更（避免数据迁移反复）；2 周后如需新增/合并，走 `cost_rate_history` 留痕流程

- 责任人：**工厂厂长 + 老板**

---

## 三、技术对接确认（finance 团队 ↔ ai-costing 团队）

> 关联：`finance_analyzer_integration_v1.md §1-§4`

### 3.1 finance 侧确认

- [ ] **finance 生产库 DATABASE_URL 指向**：
  - [ ] PostgreSQL（生产）
  - [ ] SQLite（本地切片）
  - [ ] 其他：_____

- [ ] **finance 生产库 schema 是否包含以下表**：
  - [ ] `ledger_transactions`（已确认）
  - [ ] `ledger_monthly_summaries`（已确认）
  - [ ] `payment_requests`（？）
  - [ ] `tax_invoices`（？）
  - [ ] `salary_declaration_*`（？）
  - [ ] `employee_allocations`（？）
  - [ ] `monthly_labor_costs`（？）
  - [ ] `store_ops_reports`（？）

- [ ] **finance 颁发服务账号方案**：
  - [ ] Bearer JWT（首选，1 年有效期）
  - [ ] X-Costing-Key API Key（次选）
  - [ ] 不能颁发，需要 ai-costing 用用户级 token（最差方案）

- [ ] **finance CORS 是否需要加 ai-costing**：
  - [ ] 当前 `allow_origins=["*"]`，无需改动
  - [ ] 需要白名单，加 `http://127.0.0.1:8800`

- [ ] **finance `ledger_monthly_summaries` 是否需要 rebuild**：
  - [ ] 已 rebuild，可直接用
  - [ ] 未 rebuild，Phase 1 上线前 finance 团队跑一次 `POST /api/v1/ledger/summaries/rebuild`

- [ ] **finance 是否同意按月固定时间提供月度数据**（每月 1-5 号）：
  - [ ] 同意，每月 1 号自动 rebuild
  - [ ] 同意，每月 5 号前手工 rebuild
  - [ ] 实时拉取，不需要预 rebuild

### 3.2 ai-costing 侧确认

- [ ] **新增 `backend/src/integrations/finance_analyzer/client.py` 工作量**：约 2 天
- [ ] **新增 8 个关键 API 调用** + 3 级回退：约 3 天
- [ ] **新增月度对账 cron + 报警**：约 2 天
- [ ] **健康检查 endpoint**：约 0.5 天
- [ ] **前端 finance 对账 banner**：约 1 天

**Phase 1 总工时（含财务接入）**：约 2-2.5 周

---

## 四、风险确认

### 4.1 高风险（必须有应对方案）

- [ ] **finance 生产库与文档不一致** → 应对：Phase 0 评审会现场连 finance 生产库验证 schema
- [ ] **会计科目分类不严格导致反推不准** → 应对：Phase 0 与代账会计共同确认科目清单
- [ ] **新口径上线后历史成本数据"跳变"** → 应对：加 `cost_calculation_version` 字段，老快照保留旧口径
- [ ] **跨法人分摊规则签字后又频繁变更** → 应对：`cost_allocation_rule` 表的 effective_from/to 必须留痕；变更必须财务+老板双签
- [ ] **员工归属表脏数据/失效** → 应对：每季度强制复核；HR 离职流程必须同步更新归属表
- [ ] **品类工时数据缺失** → 应对：MES/工时打卡先上线"班组+品类"两级；缺失时退回"工序标准工时 × 完工数"

### 4.2 中风险（有降级方案即可）

- [ ] **finance API 鉴权问题** → 降级为 API Key
- [ ] **finance API 不稳定** → 三级回退到手工配置/兜底常量
- [ ] **运营给 SKU 角色打标慢** → AI 推荐 + 人工复核
- [ ] **引流款 ROI 归因数据拿不到** → v1 用 naive_baseline，v2 接平台 API

### 4.3 低风险（可观察）

- [ ] AI 周报/月报第一周生成废话 → 人工 review 后发出
- [ ] 边角料价值率不准 → 默认 0.30，按物料类型迭代调整

---

## 五、上线节奏（v1.1 收敛后）

| 时间 | 里程碑 | 负责人 |
|---|---|---|
| Day 0（评审会当天） | 8 个核心决策签字 + finance 团队答应颁发 token + 法人/BU/4 池/分摊规则初稿落定 + 三表测试承诺时间表 | 全员 |
| Day 1-3 | finance 团队颁发服务账号 token；ai-costing 写 client.py | 双方技术 |
| Day 4-5 | 联调 finance 健康检查 + 第一次反推（拿上月数据） | ai-costing 技术 |
| Week 2-4 | **Phase 1 上线**（订单利润作战室 MVP：`shipment_pnl_lines` + `cost_snapshot` + 三层利润 + 5 类亏损标签 + 赚钱榜/亏钱榜 + 多主体核算） | ai-costing 团队 |
| Week 5-6 | **Phase 2 上线**（月度差异分摊 `monthly_cost_variance` + 财务对账 + 成本优化机会榜） | ai-costing 团队 |
| Week 7-9 | **Phase 3 上线**（店铺组合工作台 + SKU 矩阵 + 健康度评分 + 引流款 ROI 归因） | ai-costing 团队 |
| Week 10-11 | **Phase 4 AI 上线**（周报/月报/NLQ/异常报警/优化建议） | ai-costing 团队 |
| Phase 5 | 决策工作流（自动调价 / 自动下架 / 集采询价单生成） | 后置（Phase 4 稳定后） |

---

## 六、评审会议程建议（3.5 小时，v1.2 当日二次校准重排，加 cost_center 议题）

1. **0-15 min**：开场 + 过本清单"必须签字的 12 个核心决策"
   - **重点强调 v1.2 五个关键转向**：
     - 现状审计发现 4 看板 + shipment_costing_results 已生产 → Phase 1 改为"增量改造"
     - Phase 1 顺序：「数据可信度治理」优先 → 「决策语言」后置
     - Cost Rate Hub 作为 Phase 1 核心交付物（v1.2 复用现有 8456 行 UI）
     - 🆕 一栋楼三法人事实校准 → Hub 不分 factory，4 个组织概念正交（production_unit / purchase_entity / cost_center / legal_entity）
     - 🆕 cost_center 是 v1 唯一新引入的费用归集维度（H4 决策点）
2. **15-40 min**：**决策 H1+H2+H3+H4（Cost Rate Hub v1.2）**，集团财务+老板+工厂厂长主导
   - H1 全局费率初始值 / H2 编辑权 / H3 撤销窗口 / **H4 cost_center 初稿清单（含与现有 team_name 的映射）**
3. **40-55 min**：决策 1-2（制造费率/班组单价反推，**实现路径走 Hub**），财务+代账会计主导
4. **55-70 min**：决策 3（物料切割 + "标准下料占用面积"措辞），工厂+采购主导
5. **70-100 min**：决策 6 + 6.b（多主体 + 品类制造费率 + 法人/BU 映射 + 4 个费用池 + 成本中心/班组），集团财务+老板+HR+工厂总账主导
   - 提示：cost_center 已在 H4 拍板，本环节侧重"分摊基础"
6. **100-125 min**：决策 4-5（转移价 4 线约束 + SKU 5 类亏损规则 + 三视图切换），老板+运营主导
7. **125-160 min**：决策 6.c（finance 三契约 — Hub v1 上线**弱依赖** finance，但 Phase 2 仍需 finance 反推） + 技术对接确认（finance ↔ ai-costing 双方）
8. **160-210 min**：上线节奏与 Day 1 启动确认 + Phase 1 Stage 1 排期承诺，收尾

---

## 七、签字页

| 角色 | 姓名 | 签字 | 日期 |
|---|---|---|---|
| 老板 | | | |
| 集团财务负责人 | | | |
| 代账会计 | | | |
| 工厂总账 | | | |
| 工厂厂长（**v1.2 H4 必签**） | | | |
| 集团运营负责人 | | | |
| 各店铺运营（多人） | | | |
| 采购负责人 | | | |
| HR 负责人（决策 6 — 员工归属表） | | | |
| 各班组长代表（决策 6 — 班组工时口径） | | | |
| 税务/合规顾问（决策 6 — 多主体口径分离） | | | |
| finance-analyzer 技术负责人 | | | |
| ai-costing 技术负责人 | | | |

---

## 八、签字后立即启动的工作（Day 1）

1. ai-costing 团队提交 git commit："Phase 0 文档定稿，签字版"
2. finance 团队启动颁发服务账号流程
3. ai-costing 团队启动 Phase 1 编码（先写 finance_client.py + 6 张多主体表的 schema）
4. 集团财务录入第一份"品类利润率配置"+"间接费科目清单"+"法人 → BU 映射"+"`cost_allocation_rule` 首批关键科目分摊规则"到 staging 环境
5. HR + 工厂厂长 + 运营负责人录入第一份 `employee_attribution`（覆盖全员当前归属）
6. 各店铺运营录入第一份"店铺组合计划"（本月 + 下月）

---

*文档版本：v1.2（2026-05-09 当日二次校准：加 Manus 第三+第四轮评审采纳 + 现状审计校准 + cost_center 拆分 + H4 决策点）*
*创建日期：2026-05-08*
*评审窗口：本文档生成后 1 周内必须完成评审*
*外部评审录档（5 份）：`DOC/基础表单/专业版盈亏分析模块初步评审报告VI.md` + `多主体核算与品类制造费率补充评审报告.md` + `成本参数Hub与月度调节面板：评审与设计建议.md` + `对用户解答的二次评审：factory 维度修正版结论.md` + finance 仓库实地审计（subagent）*
*v1.2 当日二次校准内容摘要*：
*- 头部 v1.2 关键变化重写为"首次重大转向 + 当日二次校准"两段*
*- §一 必读文档加 Hub v1.2 + 外部评审 INDEX*
*- §二 标题改为"12 个核心决策"，加 H4*
*- §二 加决策 H4：cost_center 初稿清单（含 Agent 提供的 6 行初稿）*
*- §六 议程从 3h 扩展到 3.5h，加 cost_center 议题*
*- §七 签字页工厂厂长标注 v1.2 H4 必签*
