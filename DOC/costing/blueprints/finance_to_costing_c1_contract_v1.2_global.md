# ⚠️ 本 v1.2 已被 v1.3 替代 — 仅作历史存档

> **❌ 替代通知（2026-05-10 13:30）**：finance 团队 13:00 主动提案 `payment_requests` 接口取代 fixed_monthly_costs.amortization 字段，并 align 边界（撤回 fixed-cost-allocations API）。
>
> **唯一权威**：`finance_to_costing_c1_contract_v1.3_aligned.md`
>
> 本 v1.2 不再使用，仅作 v1.0 → v1.1 → v1.1.1 → v1.2 → v1.3 决策演进留档。
>
> ---

# finance → costing C1 契约 v1.2 全局优化版（已废弃，仅存档）

> **本文档作用**：把 v1.0 + v1.1 + v1.1.1 的所有决策、撤回、新增汇总成 1 份权威清单。**财务团队/Agent 看这一份就够，不用翻历史**。
> **创建日期**：2026-05-10 12:25 北京时间
> **触发原因**：用户 12:18 指出"挤牙膏式深入是错的，应该全局体系化评审"。本 v1.2 一次性覆盖所有该补的内容，避免再迭代。
> **关联历史文档**（仅供存档参考，不要按它们做事）：
> - `finance_to_costing_c1_contract_v1.md` v1.0（5 个原始 API，已 finance Agent 实施）
> - `finance_to_costing_c1_contract_v1.1_increment.md` v1.1 + v1.1.1 修订（部分撤回，部分保留，本 v1.2 已合并）

---

## 0. 30 秒摘要（财务老板看这段就够了）

ai-costing-system 跟你们对接的最终需求清单。**总共 8 件事**（已完成 5 件 + 新增 3 件）：

```
✅ 已完成（v1.0，finance Agent 在 feat/c1-costing-contract-v1 branch 上）：
  1. GET /api/v1/c1/companies 
  2. GET /api/v1/c1/stores
  3. GET /api/v1/c1/employees（参考字段，不是权威）
  4. GET /api/v1/c1/fixed-costs
  5. GET /api/v1/c1/payroll（v1.2 强化 by_employee 必须支持）

🆕 本 v1.2 新增（建议 1~1.5 天搞定）：
  6. master_companies 加 4 个业务画像标签字段（核心 1）
  7. GET /api/v1/c1/stores/revenue（核心 2，新接口，按月真实营业额）
  8. fixed_monthly_cost 加 amortization_months 字段（工程优化 1，跨期摊销）

🔧 全局加（所有 endpoint 一起改）：
  9. 所有 GET 加 ?since=YYYY-MM-DDTHH:MM:SS 增量参数（工程优化 2）
```

**估时**：finance Agent 1~1.5 人天 / costing Agent 0.5 人天 / 双方测试 0.5 天 = **2 天 wall clock**

---

## 1. v1 演进历史（让财务理解为什么有多个版本）

| 版本 | 时间 | 关键决策 | 为什么 |
|---|---|---|---|
| v1.0 | 2026-05-10 07:40 | 5 个原始 API + master_companies canonical | 起点 |
| v1.1 | 2026-05-10 12:10 | 加 cost-centers/aggregate + cost_center_mapping 表 | 错误尝试（让财务做班组聚合）|
| v1.1.1 | 2026-05-10 12:18 | **撤回**让财务做班组聚合（班组归属归 costing）| 用户指出"班组是生产端事，不归财务"|
| **v1.2** | **2026-05-10 12:25** | **撤回**让财务拆工资项 + **新增**主体业务画像 + 月度营收 + 跨期摊销 + 增量参数 | 用户指出"挤牙膏式深入是错，要全局评审" |

**结论**：v1.2 是终态。除非业务发生重大变化，**不会再修订**。

---

## 2. 核心决策（沿用 v1.0，未变动）

- canonical subject ID = `master_companies.id`
- 4 组织概念正交：legal_entity / purchase_entity / production_unit / cost_center
- 鉴权：HTTP Header `X-Costing-Api-Key`
- 缓存：companies/stores 5 分钟，employees/fixed-costs 1 小时，payroll 不缓存
- 错误码：HTTP 标准 + 自定义 code

详见 `finance_to_costing_c1_contract_v1.md` v1.0 §1 §6（不在此重复）。

---

## 3. v1.2 撤回清单（财务不要做这些）

### 3.1 撤回 v1.1 全部 — 班组聚合归 costing

| 项 | 撤回原因 |
|---|---|
| ❌ cost_center_mapping 表 | 班组归属归 costing，财务不维护映射 |
| ❌ GET /api/v1/c1/cost-centers/aggregate 接口 | costing 拉员工明细工资 + 自己内部映射 + 自己聚合 |

### 3.2 撤回 v1.1.1 §10.2 部分内容 — 工资不要拆细

| 项 | 撤回原因 |
|---|---|
| ❌ 拆 gross_salary 为 5 项（base / performance / allowance / one_time / overtime）| 用户指出："员工给一个总工资就够了，福利加班都在工资里，财务核算"。total_labor_cost 已是公司总成本，足够算工时单价 |

**v1.1.1 §10.2 仍保留的部分**：
- ✅ payroll 必须真实支持 `aggregation=by_employee` 明细返回（每员工每月 1 行）
- ✅ `total_labor_cost = gross_salary + employer_insurance` 1 个汇总字段（不拆）
- ✅ `department_raw` 字段保留作"参考"（不是权威）

---

## 4. v1.2 新增条款（finance 侧 3 件事）

### 4.1 核心 1：master_companies 加 4 个业务画像标签

**问题背景**：用户真实场景"3 工厂主体名义分开但实际共用，固开都从 1 家走、工资从另 1 家走、销售开票走第 3 家"。如果不告诉 costing 每个主体的"业务角色"，costing 看到 fixed_cost 数据时无法判断"这是真实成本还是只是开票主体"。

**新增字段**（master_companies 表）：

| 字段名 | 类型 | 必需 | 说明 | 默认值 |
|---|---|---|---|---|
| `revenue_recognition` | Boolean | ✅ | 真实营收归此主体（销售开票主体）| false |
| `material_purchase_recognition` | Boolean | ✅ | 真实材料成本归此主体（采购开票主体）| false |
| `payroll_recognition` | Boolean | ✅ | 真实人工成本归此主体（工资发放主体）| false |
| `fixed_cost_recognition` | Boolean | ✅ | 真实固开归此主体（固开发票主体）| false |

**实施方法**：
- 加 4 个 Boolean 字段到 master_companies
- 财务 ops 给 7 个主体填值（举例：工厂主体 A 是 payroll/material 主，店铺主体 B 是 revenue 主）
- 一个主体可以同时是多个 recognition（多个字段都 true）
- 一个 recognition 可以分散在多个主体（多个公司都为 true）

**反映到 §3.1 GET /api/v1/c1/companies response**：每条记录加 4 个 Boolean 字段返回。

### 4.2 核心 2：店铺月度真实营业额 API

**问题背景**：v1.0 §3.2 master_stores 的 `monthly_revenue_avg` 是"均值"。算 4 月成本时摊平台佣金，必须用 4 月**真实**营业额（4 月可能大促，某店铺占 60%），均值会算错。

**新接口**：

```
GET /api/v1/c1/stores/revenue?period_year=2026&period_month=4
                              [&store_id=<uuid>]
                              [&since=2026-04-15T00:00:00]
```

**Response 200**：
```json
{
  "_api_version": "1.2",
  "period": {"year": 2026, "month": 4},
  "data": [
    {
      "store_id": "uuid-string-36",
      "store_name": "某某家居旗舰店",
      "company_id": "uuid",                          // 营收归属主体（应是 revenue_recognition=true 的主体）
      "platform": "tmall",
      "gross_revenue": 285000.00,                    // 平台总成交额（GMV）
      "net_revenue": 245000.00,                      // 扣除退货后净营收
      "platform_fee_paid": 28500.00,                 // 该月真实付的平台佣金（用于反向校验摊费）
      "data_source": "platform_api",                 // platform_api / financial_invoice / manual
      "data_quality": "green",                       // green: 平台API直接拉; yellow: 财务对账后; red: 手填
      "snapshot_at": "2026-05-08T10:00:00+08:00"
    }
  ],
  "summary": {
    "total_gross_revenue": 1100000.00,
    "total_net_revenue": 980000.00,
    "stores_count": 4,
    "warnings": []
  }
}
```

**关键约束**：
- 月度数据**月底 +5 工作日内必须 ready**（让 costing 能在月初 10 号前算上月成本）
- 历史数据可回溯查（`?period_year=2025&period_month=12`）
- 如果某店铺当月数据缺失，在 warnings 里报，不要返回 0

### 4.3 工程优化 1：跨期摊销字段

**问题背景**：年付的房租 / 季付的保险 / 一次性的设备折旧，财务按"实际付款月"记账。如果 costing 直接按当月数据算，1 月 KB8 成本会暴涨 12 倍（因为 12 万房租全摊到 1 月）。

**新增字段**（fixed_monthly_cost 表）：

| 字段名 | 类型 | 必需 | 说明 | 默认值 |
|---|---|---|---|---|
| `amortization_months` | Integer | ✅ | 该笔费用受益月数（年付房租=12, 季付=3, 普通月费=1）| 1 |
| `amortization_start_year` | Integer | 可选 | 受益期起始年（默认=period_year）| 同 period_year |
| `amortization_start_month` | Integer | 可选 | 受益期起始月（默认=period_month）| 同 period_month |

**反映到 §3.4 GET /api/v1/c1/fixed-costs response**：每条加这 3 个字段。

**示例**：
```json
{
  "id": "uuid",
  "company_id": "uuid",
  "period_year": 2026, "period_month": 1,           // 财务实际记账月
  "cost_category": "rent",
  "amount": 120000.00,                               // 全年房租
  "amortization_months": 12,                         // 摊 12 个月
  "amortization_start_year": 2026,
  "amortization_start_month": 1,                     // 受益期 2026-01 ~ 2026-12
  "description": "全年房租预付"
}
```

**costing 处理逻辑**（不在 finance scope，但记录在此让双方理解）：
- costing 拉到这条数据后，自动按 `amount / amortization_months` 平摊到 `amortization_start_month` 起的 N 个月
- 算 4 月成本时，这条 1 月预付的房租会贡献 10000 元到 4 月

**实施方法**：
- 加 3 个字段，全部带默认值，老数据不影响（默认 amortization_months=1 = 当月全摊，与 v1 行为一致）
- 财务 ops 给历史的"年付/季付/预付"类记录补正确的 amortization_months 值

### 4.4 工程优化 2：所有 endpoint 加增量同步参数

**问题背景**：finance 数据库未来会有几万条工资记录、几千条固开记录。每次全量拉浪费带宽 + 慢。

**所有 GET endpoint 统一加 query parameter**：

```
?since=2026-04-01T00:00:00       (可选，按 updated_at >= since 过滤；默认无限制)
?until=2026-05-01T00:00:00       (可选，按 updated_at < until 过滤；默认无限制)
```

**实施方法**：
- 所有目标表加 `updated_at` 字段（如已有跳过）
- 加 `since` / `until` 过滤逻辑（标准做法，~30 分钟实现）
- response 加 `pagination.last_updated_at` 让 costing 下次能从这个时间开始拉

### 4.5 v1.0 §3.5 payroll 强化（沿用 v1.1.1 §10.2 修订后版本）

**关键点**（v1.2 不变 v1.1.1 已定）：
- 必须真实支持 `aggregation=by_employee` 明细返回
- 每员工每月 1 行
- 字段：`employee_id` + `employee_no` + `name_masked` + `company_id`（=工资发放主体）+ `department_raw`（参考）+ `period_year/month` + `workdays` + `gross_salary` + `employer_insurance` + `total_labor_cost`
- **不要拆 gross_salary**（保留 1 个总数字段即可）

---

## 5. costing 内部要做的（不在 finance scope，记录在此让双方都清楚）

| # | 项 | 说明 |
|---|---|---|
| 1 | 新表 `employee_cost_center_assignment` | 员工 → 班组的细粒度映射（支持按比例）|
| 2 | 新 service `cost_center_aggregator_service` | 拉 §3.5 by_employee + 内部映射 + 自己聚合算 labor_rate |
| 3 | 新 service `fixed_cost_amortizer_service` | 处理 amortization_months，把跨期费用平摊到正确月份 |
| 4 | 新 UI `/costing/admin/cost-centers` | 班长用，拖员工到班组 |
| 5 | 新 UI `/costing/admin/legal-entities` | 老板用，看 4 个 recognition 标签是否对，可只读展示 |
| 6 | 新 UI `/costing/admin/finance-master` 加 revenue Tab | 显示 4 店铺月度真实营收 + 平台佣金 |
| 7 | C1 client 加 since/until 增量参数支持 + 本地 last_sync_at 状态 | 性能优化 |

---

## 6. v1.2 finance 侧实施清单（按文件分组）

### 6.1 数据层（migrations / 字段补全）

```
[ ] master_companies 加 4 个 Boolean 字段（revenue/material/payroll/fixed_cost _recognition）
[ ] master_companies 7 主体填业务画像标签（财务 ops 配合）
[ ] fixed_monthly_cost 加 3 个字段（amortization_months/start_year/start_month）
[ ] fixed_monthly_cost 历史"年付/季付"记录补 amortization 值（财务 ops 配合）
[ ] 所有目标表确保有 updated_at 字段（如缺加上）
```

### 6.2 API 层

```
[ ] §3.1 companies response 加 4 个 recognition 字段
[ ] §3.4 fixed-costs response 加 3 个 amortization 字段
[ ] §3.5 payroll 真实实现 by_employee 明细（每员工每月 1 行，不拆 salary）
[ ] 新增 §4.2 GET /api/v1/c1/stores/revenue
[ ] 所有 GET endpoint 加 ?since / ?until query 参数 + response.pagination.last_updated_at
```

### 6.3 测试层（自测 5 条 + v1.2 新增 5 条 = 10 条）

```
[ ] T1~T5 v1.0 已实施，跑通即可
[ ] T8  companies response 4 个 recognition 字段全部为 Boolean 不为 null
[ ] T9  stores/revenue 4 月数据返回 4 店铺，每个 gross_revenue > 0 OR 在 warnings
[ ] T10 fixed-costs response 包含 amortization_months 字段，老数据默认 = 1
[ ] T11 ?since=2026-05-01 过滤生效，返回的记录 updated_at >= since
[ ] T12 payroll by_employee 模式返回每员工每月 1 行，不按 department 聚合
```

---

## 7. 验收 / 工作量 / SLA

### 7.1 验收（v1.0 沿用 + v1.2 新增）

```
v1.0 验收：见 finance_to_costing_c1_contract_v1.md §8（已基本完成）
v1.2 新增验收：
  [ ] §6.1 数据层 5 条全做完
  [ ] §6.2 API 层 5 条全做完
  [ ] §6.3 测试 10 条 pytest 全过
  [ ] costing 侧消费 §6 中的 7 项内部建设全部走通（mock 已有）
```

### 7.2 工作量

| 角色 | 任务 | 时长 |
|---|---|---|
| finance Agent | §6.1 数据层 + §6.2 API 层 + §6.3 测试 | 1~1.5 人天（AI Agent 4~6 小时）|
| finance ops | 7 主体业务画像标签 + 历史 amortization 补值 | 0.5~1 人天 |
| costing Agent | §5 中的 7 项内部建设 | 1 人天（AI Agent 3~4 小时）|
| 双方联调 | E2E 4 条 | 0.5 天 |
| **总计 wall clock** | | **2 天**（双 AI Agent 并行 + 财务 ops 配合）|

### 7.3 SLA（沿用 v1.0 §5）

无变化。任何字段加/改/删按 v1.0 §5 流程。

---

## 8. 元信息

| 项 | 值 |
|---|---|
| 文档版本 | v1.2 全局优化版 |
| 创建日期 | 2026-05-10 12:25 北京时间 |
| 拍板人 | 用户（2026-05-10 12:18 选 A 全局打包）|
| 状态 | 终态（除非业务重大变化不再修订）|
| 配套撤回 | v1.1 全部 + v1.1.1 §10.2 拆工资项部分 |
| 配套保留 | v1.0 全部 + v1.1.1 §10.3 employees/by-ids 接口 |
| 替代关系 | 本 v1.2 是给 finance 团队的**唯一权威清单**，v1.0 / v1.1 / v1.1.1 仅作历史存档 |
| 期望承接 | Finance Backend Agent + Finance Ops |
| 期望完工时间 | 2 天 wall clock |

---

## 9. 一句话给 finance 团队 / Agent

v1.0 你已经做完了 80%。本 v1.2 在此基础上**只加 3 件事**（4 个标签字段 + 1 个新 API + 1 个跨期摊销字段）+ **1 个工程优化**（所有 endpoint 加 since 增量参数）+ **1 个修订**（payroll by_employee 真支持），**总共 1~1.5 人天**。

**不要做的**：
- ❌ 不要拆员工工资字段（v1.1.1 那个建议已撤回 — 给一个 total_labor_cost 即可）
- ❌ 不要做班组聚合（v1.1 那个建议已撤回 — 给员工明细工资即可）
- ❌ 不要出业务建议（摊法 / 班组 / 主体角色 全是 costing 决策，你们 1:1 实现）

**做完之后**：跑 §6.3 的 10 条测试，全过 → 通知 costing 切 `FINANCE_C1_USE_MOCK=false` → 跑 E2E → 双方完工。
