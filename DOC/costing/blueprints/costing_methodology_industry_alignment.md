# 成本核算方法论 — 行业对标与定位

> **状态**：v1.0  权威文档（任何 AI 接手必读）
> **作者**：Costing Hub Agent（Cursor / Claude Opus 4.7）
> **创建**：2026-05-10
> **更新**：2026-05-10
> **目的**：避免任何 AI（包括我自己）下次又把我们当成传统 SAP MTO 工厂，去套标准成本法那一套。

---

## 0. 5 句话给任何 AI 接手者

1. **我们是 POD（按需印制）模式**，不是传统 MTO（按订单大批量制造），SAP CO 标准成本法+月度差异分摊 **不能照搬**。
2. **行业最佳实践 = TDABC**（时间驱动作业成本法）+ **每单实际料 + 月销量摊间接费 + 机器小时折旧**，对标 Printful / Printify / DTF 数码印花行业。
3. **我们 TDABC 已完成 60%**：班组工时容量、finance 真工资、Hub 4 层 resolve 都有，但 A2 写入的 `labor_per_minute` 下游没读（孤儿数据），还差 POD 行业 3 件关键事（设备小时折旧 / 换型成本 / 销量摊销层）。
4. **路线图**：v1（2 天）TDABC 闭环 → v2（5 天）补 POD 关键 3 件事 → v3（后续）成本快照+月度差异作传统会计兜底。
5. **不要再问"要不要做月度变动差异"** — POD 单单粒度天然清晰，不需要 SAP 那套 KKS1/CO88 流程；要做的是 **每单实际成本** + **月度真工资回算 Hub 费率**。

---

## 1. 我们是谁（业务定位）

| 维度 | 我们的实际情况 |
|---|---|
| **生产模式** | POD（Print on Demand 按需印制） |
| **品类** | 家居饰品 + 家居布艺（转印垫、餐垫、抱枕、桌布等）|
| **批量** | 单件 ~10 件 / 单（极少超过 50 件）|
| **SKU 数量** | 100 万+ |
| **新品节奏** | 每天上新（高度数字化设计 + 实物化生产）|
| **发货时效** | 24-72 小时 |
| **核心工艺** | 数码转印 + 缝纫包边 + 质检包装 |
| **工厂结构** | 1 栋楼内 3 个名义工厂（1 般+2 小规模），实际 1 个体系 |
| **班组结构** | 6 个班组（design/print/decor/sew/qc/pack）|

**关键判断**：
- 我们是**电商驱动的小批量数字化制造**（接近"工业化定制 mass-customization"）
- 不是**传统订单批量生产**（一单做几千件，半年发完）
- 也不是**纯 POD 平台**（如 Printful 自己不持有库存，我们持有原材料库存）
- 最接近的对标：**国内家居布艺类目的"家居 POD 工厂"**（如蜂窝家纺、当客印品、米兔印品的部分业务线）

---

## 2. 我们 ≠ 传统 MTO（关键差异）

| 维度 | 传统 MTO（SAP CO 适用） | POD（我们的情况）|
|---|---|---|
| 批量 | 100~10000 件/单 | **1~10 件/单** |
| 生产订单粒度 | 一个订单生产几千件同款 | **一个订单一两件，可能每件 SKU 都不同** |
| 标准成本表 | 几千个 SKU 算一次标准成本 | **算一次只用 1 次**（下次 SKU 又变了）|
| 月度差异分摊 | 标准成本 vs 实际成本月底分摊 | **每单粒度本身就是实际成本**，不需要月度反算 |
| 工序标准工时 | 工业工程师测一次用几年 | **每个图案、每种材质都不同**（新品天天上）|
| 机器换型成本 | 摊到大批量后忽略（< 1%）| **每款都要换**，占成本 5-15% |
| 设备折旧 | 全厂按工时摊 | **DTF/转印机折旧每小时几十块**，需单独建模 |
| 班组工人 | 专人专线 | **一组人多机种轮流**（明天打印、后天打包）|

**直接结论**：
- ❌ 不要做：标准成本表 / 月度成本中心结算 / KKS1 差异计算 / WIP 在制品计算 / CO88 订单结算
- ✅ 要做：**每单实际料工费**（基于实时 BOM + 班组真时薪 + Hub 费率）

---

## 3. 行业对标（带链接，免得下次又编）

### 3.1 POD 平台公开做法

#### **Printify**（POD 全球第二大平台）
- URL: https://printify.com/blog/how-to-price-a-product-for-ultimate-success/
- **公式**：`COGS per unit = Direct cost per unit + Indirect cost per unit`
  - **直接费**：物料 + 印制商费 + 包装（每单粒度真实数据）
  - **间接费**：`Indirect cost per unit = Monthly total overhead ÷ average units sold per month`（**月销量摊间接费**，不是按工时）
- **目标毛利**：30-50% markup → 30%+ profit margin

#### **Printful**（POD 全球第一大平台）
- URL: https://printful.com/blog/print-on-demand-costs
- **完整成本拼图**：COGS（料+工+印制） + Shipping + Taxes + Customization fees
- **批量折扣**：25+ 件单独定价（行业惯例）

### 3.2 数码印花/DTF 行业（中文资料）

#### **数码印刷成本核算**
- URL: https://www.cnzhixiang.com/news/105/1/3199.html
- **核心方法：小时费率法**
  - `小时费率 = 总生产成本 ÷ 应收费生产时间`
  - 总生产成本 = 设备折旧 + 厂房 + 班组直工资 + 间接劳动力 + 全厂性开支按比例分配

#### **DTF 印刷单件成本拆解**
- URL: https://www.quickconver.com/zh-hant/dtf-print-cost-calculator/
- **典型成本结构**：
  - 材料成本：60-75%（转印膜 + 墨水 + 转印粉）
  - 设备折旧：10-15%（DTF 印表机 + 热压机）
  - 人工运营：10-25%（操作员 + 电费 + 间接成本）
- **批量效应**：200 件以上批次单位成本可降 30-50%

#### **小批量定制成本拆解**
- URL: https://heyijiapack.com/news/read-23740.html
- 关键发现：**小批量高成本本质 = 固定成本（版费、开机费）被极少数量分摊**

### 3.3 学术研究（TDABC 在小型纺织/印刷的实证）

#### TDABC 在厄瓜多尔小型纺织厂
- URL: https://dspace.ucuenca.edu.ec/handle/123456789/38684
- 结论：传统标准成本法**低估单件成本 2~75%**（最高 75%！）

#### TDABC 在巴西小型定制服装厂
- URL: https://www.repositorio.ufal.br/handle/123456789/14940
- 结论：TDABC 能捕捉小批量定制特殊性，传统方法不行

#### TDABC 在印刷厂
- URL: http://www.um.edu.mt/library/oar/handle/123456789/10410
- 结论：传统算法只算直接料工，**显著低估实际成本**；TDABC 时间方程比报价系统更接近真实

### 3.4 SAP CO（不适用我们，但要知道为什么不适用）

- URL: https://blog.csdn.net/stone0823/article/details/54318952
- 流程：CO01 → MB1A → CO11N → MB31 → KSV5/KSU5 → KKS1 → CO88
- **不适用原因**：每流程节点都假设"批量生产、生产订单几千件"，我们一单 1-2 件，所有流程节点都失去意义
- 但有 1 件可借鉴：**KSV5/KSU5 的成本中心分摊思想** = 我们 `cost_allocator_service` 已用上

---

## 4. 我们的位置（TDABC 完成度评估）

### 4.1 已完成（✅）

| POD 行业关键算法 | 我们的实现 | 文件 |
|---|---|---|
| 班组小时单价（TDABC 核心）| `cost_center_aggregator_service`（班组真工资 ÷ 班组工时容量）| `backend/src/planner/services/cost_center_aggregator_service.py` |
| 真工资数据来源 | finance C1 v1.3 集成 `/payroll?aggregation=by_employee` | `backend/src/planner/services/finance_c1_client.py` |
| 4 层 Hub resolve | `long_tail_strategy_service.resolve_overhead_rate` | `backend/src/planner/services/long_tail_strategy_service.py` |
| 物料每单实际价 | Stage 2 字段（含税还原 + 时效 + 采购主体）| `backend/src/planner/services/bom_generation_service._resolve_material_price` |
| 固定费按面积/人头/营收摊 | `cost_allocator_service`（多级 fallback）| `backend/src/planner/services/cost_allocator_service.py` |
| 班组与工序绑定 | `Process.cost_center_id` FK（Migration 0040）| `backend/migrations/versions/0040_cost_center.py` |

### 4.2 已写但下游没读（⚠️ 路径 A 漏洞）

| 漏洞 | 现状 | 修复 |
|---|---|---|
| **A2 labor_per_minute 是孤儿** | `cost_center_aggregator_service` 已写 `cost_rate_master.labor_per_minute scope=cost_center`，但 `bom_generation_service._compute_process_costing` 没读 | **v1 G 修复**（0.5 天）|

### 4.3 POD 行业关键缺失（v2 补）

| 缺失 | POD 行业重要性 | 估时 |
|---|---|---|
| **设备小时折旧**（DTF / 热压 / 缝纫机）| 占成本 10-15% | 2 天 |
| **换型/开机成本**（每款打样首件 + 多 SKU 切换工时）| 占成本 5-15% | 2 天 |
| **Printify 风格销量摊销层**（月间接费 ÷ 月销量）| 兜底 SKU 成本 | 1 天 |

---

## 5. 演进路线图

### v1（这次，2 天，TDABC 闭环）

> **目标**：把已建好的 TDABC 引擎真正接通，让单件人工成本 = finance 真工资计算的班组时薪 × 工时

- **G**：A2 接通 — `_compute_process_costing` 改造，按工序的 `cost_center_id` 查 `cost_rate_master.labor_per_minute scope=cost_center`，命中用真工资时薪，未命中回退原 metadata
- **H**：standard-models 抽屉加「成本核算」Tab — 实时试算 + 4 层链路展示 + 模型级覆盖

**Brief**: `DOC/agents/briefings/tdabc_v1_closing_loop_brief.md`

### v2（v1 跑通后立项，5 天，POD 关键 3 件事）

> **目标**：把 POD 行业 3 件关键事做齐，单件成本精度从"接近 Printify"提升到"超过 Printify"

- **设备小时折旧**（cost_rate_master 加 `equipment_per_hour`，process 加 `equipment_id`）
- **换型/开机成本**（model_version_processes 加 `setup_minutes` + 每款首件加价）
- **销量摊销层**（Hub 加第 5 层 fallback：月销量摊间接费）

**Brief**: 待 v1 跑通后写

### v3（更后续，按需）

- 成本快照（cost_snapshot）：发货时锁住所有费率版本，历史可追溯（不是 SAP WIP，是给 Insights 看历史趋势用）
- 月度真工资回算 Hub 费率 → 自动版本化（不是 SAP 月度差异，是给 Hub 自动 self-healing 用）
- SKU 角色（traffic / profit / brand / clearance / new）— **不参与成本计算**，只用于事后定价/分析（用户已确认）

---

## 6. 给任何 AI 接手者的 3 条铁律

1. **不要套 SAP CO 那一套** — 我们没有"生产订单"概念（每单 1-2 件就是一单），没有"标准成本表"概念（SKU 100 万每天上新），没有"WIP 在制品"概念（24-72h 出货）。看到任何 AI 提议"做月度差异分摊 / KKS1 / CO88 / WIP" → 立刻打住。
2. **不要重新设计 TDABC** — 我们已经做完 60%，关键差距是"A2 接通"和"POD 3 件事"，不是另起炉灶。看到任何 AI 提议"重新设计成本算法" → 先看本文 §4.1。
3. **不要混淆"成本算法"和"运营标签"** — SKU 角色（引流款/利润款）**不影响成本**，只影响定价决策。看到任何 AI 提议"按角色给不同费率算成本" → 这是会计错误（成本扭曲），打住。

---

## 7. 文档关系

| 文档 | 关系 |
|---|---|
| `pnl_analytics_module_design.md` | 老的 Phase 1-3 整体规划，**部分内容（cost_snapshot / 5 损益分类）已推到 v3**，本文档是其方法论上层 |
| `cost_rate_hub_design_v1.md` | Hub 自身的 4 层 resolve 设计，本文档复用其结论 |
| `finance_to_costing_c1_contract_v1.3_aligned.md` | 数据来源契约，本文档依赖其 `/payroll by_employee` 提供真工资 |
| `path_a_real_data_wiring_v1.md` | 路径 A 的 brief（已完成 90%，差 G），本文档 §4.2 描述其遗漏 |
| `tdabc_v1_closing_loop_brief.md` | **本文档 v1 的执行 brief**（即将创建）|
| `system_capability_inventory.md` | 系统能力清单，本文档 §4 已与之对齐 |

---

## 8. 引用链接索引

### POD 行业
- Printify pricing methodology: https://printify.com/blog/how-to-price-a-product-for-ultimate-success/
- Printful POD costs: https://printful.com/blog/print-on-demand-costs
- Printify profit guide: https://printify.com/knowledge-hub/printify-profit-navigator-pod-margins-guide/

### 数码印花/DTF 行业（中文）
- 数码印刷成本与定价: https://www.cnzhixiang.com/news/105/1/3199.html
- DTF 打印成本计算器: https://www.quickconver.com/zh-hant/dtf-print-cost-calculator/
- 小批量定制成本拆解: https://heyijiapack.com/news/read-23740.html

### TDABC 学术研究
- 厄瓜多尔纺织厂 TDABC: https://dspace.ucuenca.edu.ec/handle/123456789/38684
- 巴西定制服装厂 TDABC: https://www.repositorio.ufal.br/handle/123456789/14940
- 印刷厂 TDABC: http://www.um.edu.mt/library/oar/handle/123456789/10410

### SAP CO（反面对标，不适用）
- SAP CO 流程: https://blog.csdn.net/stone0823/article/details/54318952
- SAP 工单成本分析: https://cloud.tencent.cn/developer/article/1971316

---

**End of Document**
