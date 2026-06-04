# ⚠️ 本文档已被 v1.2 全局版替代 — 仅作历史存档

> **❌ 废弃通知（2026-05-10 12:25）**：
>
> 用户 12:18 指出本契约的两次迭代都是"挤牙膏式深入"，应该全局体系化评审。本 v1.1 + v1.1.1 增量已被合并/修订/撤回，全部内容收口到：
>
> **`finance_to_costing_c1_contract_v1.2_global.md`** — 这是给 finance 团队的**唯一权威清单**。
>
> 本 v1.1 文档保留作为决策演进留档（v1.0 → v1.1 错误尝试 → v1.1.1 部分撤回 → v1.2 全局收口）。**不要按本文档实施**。
>
> ---

# finance → costing C1 契约 v1.1 增量需求（已废弃，仅存档）

> **本文档作用**：在 `finance_to_costing_c1_contract_v1.md` v1.0 基础上**只增不改**的需求增量。
> **触发原因**：用户 2026-05-10 12:08 明确分工，2026-05-10 12:15 进一步指出"班组归属权应该归 costing，不应让财务维护员工→班组映射"。本 v1.1 把"班组聚合公式"和"摊法计算公式"写死，财务按公式实现新 API。
> **创建日期**：2026-05-10 12:10 北京时间（**12:18 重大修订 v1.1.1：撤回让财务做班组聚合的设计**）

---

## 🔴 v1.1.1 重大修订（2026-05-10 12:18）

**修订内容**：用户 12:15 客观评审指出 — 「让财务维护员工→班组映射 = 让财务部做生产端的活 = 反人性」。专业判断采纳：**班组归属权归 costing，财务不做班组聚合**。

| 原 v1.1 设计 | v1.1.1 修订后 |
|---|---|
| §3.6 让 finance 实现 `cost-centers/aggregate` 聚合接口 | ❌ **取消**。班组聚合 costing 自己做 |
| §2.9.1 让 finance 建 `cost_center_mapping` 表 | ❌ **取消**。映射在 costing 内部 |
| §3.6.3 cost_center_mapping 初始化由 costing 提供 | ❌ **取消**（同上）|
| §3.5 payroll 默认 `by_department` 聚合 | 🟡 **强化**：必须支持 `aggregation=by_employee` 明细返回（不只是 department 聚合）|
| 新增 §3.8 `cost-centers/aggregate` ❌ → 改为 costing 内部 service | ✅ 在 ai-costing-system 内部新建 `cost_center_aggregator_service` |

**保留不变**：
- §3.7 `fixed-cost-allocations` 摊法计算接口 — **保留**，因为摊法的"驱动因子数据"（floor_area / 班组人数 / 营业额）一部分在财务，一部分在 costing，让财务出最终摊法结果是双方数据 join 的最优点
- §2.11 master_companies 加 `floor_area_sqm` 字段 — **保留**
- §2.12 fixed_monthly_cost 加 `cost_subcategory_v2` 字段 — **保留**

**新增条款见文末「§10 v1.1.1 修订条款」**。
> **产权方**：与 v1.0 同 — costing + finance 双方共有
> **关联文档**：`finance_to_costing_c1_contract_v1.md` v1.0
> **本增量影响范围**：finance 侧加 2 个新 API + 2 个新字段 + 1 张 mapping 表；costing 侧只消费不实施

---

## 0. 30 秒摘要（增量）

v1.0 已让 finance 暴露了「公司/店铺/员工/固开/工资」5 个原始数据 API。但 costing 算"每个班组的工时单价""每项固开摊到每个班组的金额"还需要财务按 costing 定义的**聚合公式**返回结果。本 v1.1 加 2 个聚合 API：

```
GET /api/v1/c1/cost-centers/aggregate    (按 costing 公式聚合班组数据)
GET /api/v1/c1/fixed-cost-allocations    (按 costing 公式分摊固开)
```

**关键变化**：财务**不出**任何业务判断（哪个班组做什么品类 / 摊法是否合理）— 所有规则、公式、默认值都写在本契约里，财务 1:1 照搬。

---

## 1. 新分工原则（不再变了）

| 谁 | 干啥 | 不干啥 |
|---|---|---|
| **costing（业务大脑）** | 定义所有业务规则 + 聚合公式 + 摊法 + 业务标签维护 + 消费 API | 不去财务系统改字段 / 不让财务改业务规则 |
| **finance（数据原材料 + 算盘）** | 按 costing 给的公式纯机械计算 + 加字段 + 暴露 API | 不出业务建议 / 不判断"摊得对不对" |
| **老板** | 一次性 confirm 关键业务规则（品类标签 / 班组合并）+ 看最终结果 | 不填模板 / 不 review 中间稿 |

---

## 2. finance 侧实施清单（增量）

### 2.9 加 2 张可选辅助表（如果不存在）

#### 2.9.1 `cost_center_mapping` 表（存「员工 department → costing 班组 code」映射）

| 字段 | 类型 | 必需 | 说明 |
|---|---|---|---|
| id | UUID | ✅ | |
| department_raw | String(64) | ✅ | employees.department 的原始值 |
| cost_center_code | String(32) | ✅ | costing 定义的班组 code（来自 §3.6.3 mapping）|
| effective_from | Date | ✅ | 生效日 |
| effective_to | Date | 可选 | 失效日 |

**初始化**：finance 侧先把 employees.department 的所有 distinct 值列出来 → 由 costing 提供初始 mapping（见 §3.6.3）→ insert 进表。

#### 2.9.2 `cost_center_allocation_rule` 表（存「11 项固开 → 摊法」规则）

| 字段 | 类型 | 必需 | 说明 |
|---|---|---|---|
| id | UUID | ✅ | |
| cost_category | String(32) | ✅ | 与 v1.0 §3.4.1 枚举一致 |
| target_scope | Enum | ✅ | `cost_center` / `store` / `both` |
| driver | Enum | ✅ | `floor_area` / `headcount` / `team_hours` / `revenue` / `fixed_pct` |
| share_pct | Decimal(5,2) | 可选 | 当 driver=`fixed_pct` 时用，0~100 |
| effective_from | Date | ✅ | |
| effective_to | Date | 可选 | |

**初始化**：本契约 §3.7.3 直接给 11 项默认规则，finance 侧 1:1 insert 即可。

> **注**：这 2 张表如果你们现有数据库已有类似设计，**不强制建新表**，能在 API 层 join 出对应字段即可。

### 2.10 加 2 个新 API endpoint（详见 §3.6 §3.7）

```
GET /api/v1/c1/cost-centers/aggregate
GET /api/v1/c1/fixed-cost-allocations
```

### 2.11 给 master_companies 加 1 个字段（v1.0 漏的）

| 字段名 | 类型 | 必需 | 说明 |
|---|---|---|---|
| `floor_area_sqm` | Decimal(10,2) | 可选 | 该主体占用厂房/办公面积（平方米），用于按面积摊房租 |

**初始化**：财务 ops 自己填（你们最清楚每个主体多少面积）。

### 2.12 给 fixed_monthly_cost 加 1 个字段（v1.0 漏的）

| 字段名 | 类型 | 必需 | 说明 |
|---|---|---|---|
| `cost_subcategory_v2` | String(32) | 可选 | 区分"生产区域 / 办公区域"等子类，让 costing 能精细摊费（如 `rent_factory` / `rent_office`）|

**初始化**：财务 ops 给历史房租数据补这个标签即可。

---

## 3. 2 个新 API 详细规格

### 3.6 `GET /api/v1/c1/cost-centers/aggregate` — 班组聚合数据

**用途**：costing 一次拿到「6~10 个班组的人数 / 工时单价 / 归属主体」，省掉 costing 自己 join 员工表的麻烦。

**鉴权**：`X-Costing-Api-Key`（与 v1.0 一致）

#### 3.6.1 Query Parameters

```
?period_window=last_3_months                 (枚举：last_3_months / last_6_months / last_12_months / specific_yyyymm-yyyymm)
?period_specific=2026-02_2026-04             (当 period_window=specific 时必填，格式 YYYYMM_YYYYMM)
?min_headcount=3                             (可选，过滤员工数 < min_headcount 的小班组；默认 3)
?max_count=10                                (可选，最多返回前 N 个班组按人数倒序；默认 10)
?include_inactive=false                      (可选，默认 false)
```

#### 3.6.2 Response 200

```json
{
  "_api_version": "1.1",
  "data_window": {
    "period_from": "2026-02-01",
    "period_to": "2026-04-30",
    "snapshot_at": "2026-05-10T12:00:00+08:00"
  },
  "data": [
    {
      "cost_center_code": "SEW01",                     // 来自 cost_center_mapping 表
      "department_raw_list": ["缝纫一组", "缝纫1组"],   // 归一化前的所有 raw 值
      "headcount": 8,
      "headcount_active": 8,
      "headcount_leader": 1,                            // 该班组里 position LIKE '%班长%' OR '%组长%' 的人数
      "leader_name": "张三",                            // 第一个 leader 的姓名（如有多个）
      "primary_legal_entity_id": "uuid-string-36",      // 该班组员工 contract_company_id 占比最大的那个
      "primary_legal_entity_share": 0.875,              // 占比（0~1，例如 7/8 = 0.875）
      "legal_entity_distribution": {                    // 详细分布
        "uuid-A": 7,
        "uuid-B": 1
      },
      "labor_rate_per_minute": 0.42,                    // 工时单价（元/分钟），按 §3.6.4 公式算
      "labor_rate_quality": "green",                    // green/yellow/red，按 §3.6.5 评级
      "labor_rate_calc_detail": {                       // 算法透明化
        "total_gross_salary_window": 540000.00,
        "total_employer_insurance_window": 108000.00,
        "total_labor_cost_window": 648000.00,
        "total_workdays_window": 540,                   // 8 人 × 21.5 天 × 3 个月 ≈ 540
        "minutes_per_workday": 480,                     // 写死 8h × 60min
        "formula": "labor_rate = total_labor_cost / (total_workdays × 480)"
      }
    }
  ],
  "summary": {
    "total_cost_centers": 8,
    "total_headcount": 56,
    "unmapped_departments": ["新某组", "试制车间"],     // mapping 表里没配的 raw department，留给 costing 补
    "warnings": [
      "班组 PKG02 在 last_3_months 内 contract_company_id 分散在 5 个法人主体，主体集中度 < 60%"
    ]
  }
}
```

#### 3.6.3 `cost_center_mapping` 初始映射（**costing 提供的初始数据，finance 1:1 insert 即可**）

> 财务侧第一次跑 `SELECT DISTINCT department FROM employees WHERE is_active=true`，把结果发给 costing；costing 在本契约 v1.2 增量里补充完整 mapping 表。**v1.1 阶段 finance 可以先按"原始值 = code"占位**（如 raw="缝纫一组" → code="缝纫一组"），等 costing 提供正式 code。

**Bootstrap 模板**（v1.1 阶段先用这个）：

| department_raw | cost_center_code（v1.1 占位）|
|---|---|
| {finance distinct 出来的每个值} | 同 raw 值（汉字保留）|

**v1.2 阶段 costing 会替换为标准 code**（如 SEW01 / PKG01 等）。

#### 3.6.4 `labor_rate_per_minute` 计算公式（写死，财务严格 1:1 实现）

```
labor_rate_per_minute = total_labor_cost_window / (total_workdays_window × 480)

其中：
  total_labor_cost_window = SUM(
    payroll.gross_salary + payroll.employer_insurance
  ) WHERE employee.cost_center_code = X 
    AND payroll.period BETWEEN window_from AND window_to

  total_workdays_window = SUM(payroll.workdays) WHERE 同上

  480 = 每个工作日的"标准工时分钟数"（8 小时 × 60 分钟，写死，不要改）
```

**特殊情况**：
- 若 `total_workdays_window = 0`：返回 `labor_rate_per_minute = null`，`labor_rate_quality = "red"`
- 若 window 内某月 payroll 缺失：跳过该月，但在 `labor_rate_calc_detail.warnings` 里写「2026-03 缺工资数据，已跳过」
- 若 employer_insurance 字段为 null：当 0 处理，但在 warnings 里提示

#### 3.6.5 `labor_rate_quality` 评级规则（写死）

| 等级 | 触发条件 |
|---|---|
| `green` | window 内每个月都有 payroll 数据 + headcount ≥ 3 + 主体集中度 ≥ 80% |
| `yellow` | window 内 ≥ 50% 月份有数据 + headcount ≥ 2 |
| `red` | 数据缺失 ≥ 50% 月份 OR headcount < 2 OR labor_rate = null |

---

### 3.7 `GET /api/v1/c1/fixed-cost-allocations` — 固开按月分摊结果

**用途**：costing 一次拿到「11 项固开按指定月份摊到每个班组/店铺的金额」，省掉 costing 自己实现摊费引擎。

**鉴权**：`X-Costing-Api-Key`

#### 3.7.1 Query Parameters

```
?period_year=2026&period_month=4             (必需)
?cost_category=rent|utility|...               (可选，过滤某项；默认全部 11 项)
?target_scope=cost_center|store|both          (可选，过滤分摊目标；默认 both)
```

#### 3.7.2 Response 200

```json
{
  "_api_version": "1.1",
  "period": {"year": 2026, "month": 4},
  "data": [
    {
      "cost_category": "rent",
      "cost_subcategory": "rent_factory",                  // 来自 §2.12 新字段
      "total_amount": 35000.00,
      "currency": "CNY",
      "tax_included": true,
      "rule_applied": {
        "target_scope": "cost_center",
        "driver": "floor_area",
        "rule_id": "uuid-of-cost_center_allocation_rule",
        "rule_effective_from": "2026-01-01"
      },
      "allocations": [
        {
          "target_type": "cost_center",
          "target_id": "SEW01",                            // 班组 code
          "target_name": "缝纫一组",
          "driver_value": 80.0,                            // 该班组占地 80 平方米
          "driver_total": 320.0,                           // 全厂占地 320 平方米
          "share_pct": 0.25,                               // 80/320 = 25%
          "allocated_amount": 8750.00                      // 35000 × 0.25
        }
      ],
      "calculation_quality": "green",                       // 评级见 §3.7.4
      "warnings": []
    }
  ],
  "summary": {
    "total_categories_processed": 11,
    "total_allocated": 178500.00,
    "unallocated_categories": [],                          // 数据缺失无法分摊的项
    "global_warnings": []
  }
}
```

#### 3.7.3 11 项默认摊法规则（**costing 写死，finance 1:1 insert 进 cost_center_allocation_rule 表**）

| # | cost_category | cost_subcategory | target_scope | driver | 备注 |
|---|---|---|---|---|---|
| 1 | rent | rent_factory | cost_center | floor_area | 生产区域房租按班组占地面积 |
| 2 | rent | rent_office | both | headcount | 办公区域房租按总人头摊（管理+生产）|
| 3 | utility | (空) | cost_center | floor_area | 水电主要生产用，按面积近似 |
| 4 | salary_admin | (空) | both | headcount | 管理工资按总人头 |
| 5 | insurance_admin | (空) | both | headcount | 管理五险一金按总人头 |
| 6 | office_supplies | (空) | both | headcount | 办公耗材按总人头 |
| 7 | depreciation | (空) | cost_center | team_hours | 设备折旧按班组实际工时 |
| 8 | logistics | (空) | cost_center | team_hours | 厂出物流按班组工时（生产端）|
| 9 | platform_fee | (空) | store | revenue | 平台佣金按店铺营业额 |
| 10 | after_sales | (空) | store | revenue | 售后退换按店铺营业额 |
| 11 | others | (空) | both | headcount | 其他默认按人头 |

**驱动因子数据来源**（写死给 finance 怎么算 driver_value）：

| driver | driver_value 取自 | driver_total 取自 |
|---|---|---|
| floor_area | `master_companies.floor_area_sqm`（按主体）or 班组分配比例（如有）| 全厂主体的 sum |
| headcount | `cost_centers/aggregate` 接口返回的 headcount | 所有班组 sum |
| team_hours | finance 内部工时表（如有），无则 fallback 到 headcount + 标注 `calculation_quality=yellow` | 同上 |
| revenue | `master_stores.monthly_revenue_avg` × 该月调整因子 | 4 店铺 sum |
| fixed_pct | `cost_center_allocation_rule.share_pct` | 100% |

#### 3.7.4 `calculation_quality` 评级（写死）

| 等级 | 触发条件 |
|---|---|
| `green` | total_amount 与 fixed_monthly_cost 表完全对得上 + 所有 driver_value 都有真实数据 |
| `yellow` | driver_value 用了 fallback（如 team_hours 缺数据 fallback 到 headcount）|
| `red` | total_amount 缺失 OR driver_total = 0（除数为 0）|

---

## 4. 新增 C2 自动化测试用例（在 v1.0 §4 基础上加）

### 4.1.1 finance 侧自测增量（5 条）

```
[ ] T7  GET /api/v1/c1/cost-centers/aggregate?period_window=last_3_months 返回 200 + 至少 3 个班组
[ ] T8  返回的 labor_rate_per_minute 与手动算「total_labor_cost / (workdays × 480)」结果一致（误差 < 0.001）
[ ] T9  当某班组 contract_company_id 分散在 ≥ 3 个主体时 warnings 含「主体集中度 < 60%」
[ ] T10 GET /api/v1/c1/fixed-cost-allocations?period_year=2026&period_month=4 返回 11 项 + 每项 allocations 的 share_pct 之和 = 1.0（误差 < 0.001）
[ ] T11 当 fixed_monthly_cost 某项数据缺失时 unallocated_categories 含该项 + global_warnings 提示
```

### 4.2.1 costing 侧消费测试增量（3 条）

```
[ ] C6  cost-centers/aggregate 拉来后能直接 insert 进 ai-costing-system 的 cost_center_master 表
[ ] C7  fixed-cost-allocations 拉来后每个班组能聚合得到「本月分摊总成本」用于 BOM 制造费率
[ ] C8  unmapped_departments 非空时 UI 提示运维「请补 cost_center_mapping」
```

---

## 5. 验收标准（在 v1.0 §8 基础上加）

### 5.1 finance 侧增量 ✅（4 条）

```
[ ] F6 master_companies 加 floor_area_sqm 字段 + 7 主体已填值
[ ] F7 fixed_monthly_cost 加 cost_subcategory_v2 字段 + 历史房租已补 rent_factory/rent_office 标签
[ ] F8 cost_center_allocation_rule 表已建 + 11 项默认规则按 §3.7.3 1:1 insert
[ ] F9 §4.1.1 的 5 条 pytest 全过
```

### 5.2 costing 侧增量 ✅（3 条）

```
[ ] C9 finance_c1_client.py 加 list_cost_centers_aggregate / list_fixed_cost_allocations 2 个方法
[ ] C10 §4.2.1 的 3 条消费测试全过
[ ] C11 cost_center_master 主表落地（用 §3.6 数据预填）+ UI 让老板配「主要服务品类」标签
```

---

## 6. 工作量预估（增量）

| 角色 | 任务 | 人天 |
|---|---|---|
| finance Agent | §2.9~§2.12 加表/字段 + §3.6 §3.7 实现 + §4.1.1 测试 | 2~3 天（AI Agent 4~6 小时）|
| costing Agent | C1 client 加 2 个方法 + cost_center_master 主表 + UI 配业务标签 | 1~2 天（AI Agent 3~4 小时）|
| **总计（双方并行）** | | **3 天 wall clock**（双 AI Agent 并行 1 天）|

---

## 7. 不在本增量内（划清边界）

- ❌ 不做 webhook（仍是 v2 计划）
- ❌ 不做写回（仍是 v2 计划）
- ❌ finance 不出任何业务建议 — 班组怎么分、摊法怎么定，全由本契约写死
- ❌ 老板不需要填任何模板 — 业务标签（品类）在 ai-costing-system 内部 UI 里点

---

## 8. 元信息

| 项 | 值 |
|---|---|
| 文档版本 | v1.1 增量 |
| 创建日期 | 2026-05-10 12:10 北京时间 |
| 触发原因 | 用户 12:08 明确分工：costing 出规则、finance 执行、老板看结果 |
| 替代关系 | 本增量取代 `cost_center_master_draft_from_finance.md`（已废弃）|
| 配套文档变化 | `cost_center_master_填报模板_v2.md` 再次升级为「等系统 UI 而不是填模板」|
| 关联 v1.0 | `finance_to_costing_c1_contract_v1.md` v1.0（不动，本文档只增量）|

---

## 9. 一句话给 finance 团队 / Agent（v1.1.1 修订后）

v1.0 的 5 个 API 你已经做完了。v1.1.1 在此基础上**只加 1 个聚合 API + 2 个字段 + 1 张辅助表**（v1.1 原本 2 个聚合 API，§3.6 班组聚合已撤回）：

**finance 侧只需要做的**：
1. §3.7 `GET /api/v1/c1/fixed-cost-allocations` 摊法计算接口（11 项默认规则在本文档写死，1:1 实现）
2. §2.11 master_companies 加 `floor_area_sqm` 字段
3. §2.12 fixed_monthly_cost 加 `cost_subcategory_v2` 字段
4. §2.9.2 cost_center_allocation_rule 表（11 项默认规则 1:1 insert）
5. **强化 v1.0 §3.5 payroll**：必须真正支持 `aggregation=by_employee` 明细返回（每个 employee_id 一行 + 月度工资 + 员工合同主体），**不要按 department 聚合**

**finance 不做的**：
- ❌ 不维护员工 → 班组映射（这是 costing 内部的事，班组归属权归生产端）
- ❌ 不做班组聚合（costing 拉员工明细工资 + 自己内部映射 + 自己聚合）
- ❌ 不出业务判断

**任何"业务上是否合理"的问题不要问 costing**，因为本契约就是 costing 的最终决策；你只需 confirm "技术上能否实现"和 "字段名是否冲突现有 schema"。

---

## 10. v1.1.1 修订条款（2026-05-10 12:18）

### 10.1 撤销条款（finance 不需要做）

- ~~§2.9.1 cost_center_mapping 表~~ — 撤销，移到 costing 内部
- ~~§3.6 GET /api/v1/c1/cost-centers/aggregate~~ — 撤销，costing 自己实现内部聚合 service

### 10.2 强化条款（finance v1.0 §3.5 payroll 需要补强）

**v1.0 §3.5 写法**：「`aggregation=by_employee|by_department`（可选，默认 by_department 聚合）」

**v1.1.1 修订**：必须真正实现 `by_employee` 模式，response 格式如下：

```json
{
  "_api_version": "1.1.1",
  "data": [
    {
      "employee_id": "uuid-string-36",
      "employee_no": "E0001",
      "name_masked": "张*",
      "company_id": "uuid-string-36",         // 工资发放主体（contract_company_id）
      "department_raw": "缝纫一组",            // 财务现有 department 字段，作为参考（不是权威）
      "period_year": 2026,
      "period_month": 4,
      "workdays": 21.5,
      "gross_salary": 5500.00,                 // 应发工资
      "employer_insurance": 1100.00,           // 公司承担五险一金
      "total_labor_cost": 6600.00,             // 公司端总成本
      "metadata": {}
    }
  ],
  "pagination": {...}
}
```

**关键点**：
- `department_raw` 字段是"参考"（财务自己怎么填都可以），不是权威，**costing 不依赖它做班组聚合**
- 每个员工每月 1 行，**不要 group by department**（让 costing 自己 group）
- `employee_id` 是核心，**必须稳定**（员工 ID 不能因为部门变动而改变）

### 10.3 新增条款（finance 帮 costing 做的"中性服务"）

#### 10.3.1 `GET /api/v1/c1/employees/by-ids` — 按员工 ID 批量查

**用途**：costing 内部 cost_center_master 表会存「员工 ID 列表」，需要批量反查员工信息。

**Query Parameters**：
```
?employee_ids=<id1>,<id2>,<id3>     (必需，逗号分隔，单次 ≤ 200 个)
```

**Response 200**：
```json
{
  "_api_version": "1.1.1",
  "data": [
    {
      "id": "uuid",
      "employee_no": "E0001",
      "name_masked": "张*",
      "is_active": true,
      "contract_company_id": "uuid",
      "department_raw": "缝纫一组"   // 参考字段
    }
  ]
}
```

**这个接口让 costing 不需要每次都全量拉花名册**。

### 10.4 costing 内部要做的（不在 finance scope 内，但记录在此让双方都清楚）

**ai-costing-system 内部新增**：

1. **新表 `employee_cost_center_assignment`**（员工 → 班组的细粒度映射）：
   ```
   id, employee_id (引 finance), cost_center_code,
   share_pct (默认 100%，支持一员工多班组按比例), 
   effective_from, effective_to, created_by, updated_at
   ```

2. **新 service `cost_center_aggregator_service`**：拉 §3.5 by_employee 工资明细 + join 内部 employee_cost_center_assignment + 按班组聚合算 labor_rate_per_minute

3. **新 UI `/costing/admin/cost-centers`**：班长可以维护"员工 → 班组"的关系（员工 ID 列表选自 §10.3.1 接口）

4. **预填策略（v1 阶段降低录入成本）**：
   - 第一次拉员工时，**用 finance 的 `department_raw` 字段做"建议初始映射"**（一人一班组）
   - 班长进 UI 后看到预填，调整即可（不用从零配）
   - 班长改了之后，以 costing 内部为准，不再依赖 finance department
