# 路径 A — 让真数据通电（cost_center 主表 + 3 个核心 service + Hub 面板自动/手动切换）

> **派单时间**：2026-05-10 15:40 北京时间
> **派单人**：Hub Agent
> **承接人**：1 个 Fullstack Agent（自主完成 5~8 天，中间过程不汇报）
> **必读优先级**：P0 — 上工前必读 §0 + §1 + §11；遇到具体步骤再读对应章节
> **完整自主权声明**：scope 内无需事先报备，直接做。仅遇到 §11 列出的 3 种情况才回 Hub。

---

## 0. 30 秒摘要

finance C1 v1.3 已**端到端真闭环**（生产 KEY 已切线，7/7 endpoint live OK），但 costing 这边 **3 个核心 service 一行没写**，Hub 4 层 resolve 链里 `cost_center_id=None` 写死（`bom_generation_service.py:2066`）—— **Hub 这台车造好了发动机，但没接油管**。

本任务把油管接上：

```
finance 真数据  →  cost_center_aggregator     →  cost_rate_master
(已就绪)             fixed_cost_amortizer            (Hub 4 层链)
                     cost_allocator                       ↓
                                                    bom_generation
                                                         ↓
                                                  shipment_costing_results
                                                         ↓
                                                  4 张 Insights 看板
                                                  （自动 vs 手动徽章）
```

完成后效果：老板打开 Hub → KB8 → 看到「人工费 ¥7.34」是**从财务真实工资 + 班组工时自动算出来**的（之前是手填的占位符），并能在面板上一键切回手动 override。

**总工作量 7 天 wall-clock**，5 步串联（A1→A2→A3→A4→A5），1 个 Fullstack Agent 自主完成。

---

## 1. 必读文档（按顺序，约 30 分钟）

| # | 文档 | 看什么 |
|---|---|---|
| 1 | `DOC/costing/handovers/system_capability_inventory.md` §13.1 | U1~U9 全状态 + 本任务的位置（U7-B 已合并到本任务 A5 步） |
| 2 | `DOC/costing/blueprints/cost_rate_hub_design_v1.md` §4.1 + §4.2 + §5.1 | cost_center 表 schema（直接抄）+ processes 改造 + 4 层 resolve 优先级 |
| 3 | `DOC/costing/blueprints/finance_to_costing_c1_contract_v1.3_aligned.md` §4.2 + §4.5 + §4.6 + §4.10 | finance 真数据 schema：stores/revenue + payroll by_employee + payment_requests + master_companies.floor_area_sqm |
| 4 | `DOC/costing/blueprints/pnl_analytics_module_design.md` v1.2 §3.1 + §3.4 | 实体关系图 + cost_snapshot（不用真改这张表，只是理解上下文） |
| 5 | `backend/src/planner/services/finance_c1_client.py` line 402-620 | 7 个 list_* 方法签名 + envelope 结构（直接调用，已通过 KEY 校验和 smoke 7/7） |
| 6 | `backend/src/planner/services/bom_generation_service.py` line 2034-2080 `_resolve_overhead_rate` | 当前 Hub 4 层 resolve 链 + `cost_center_id=None` 写死的接入点 |
| 7 | `backend/src/planner/services/long_tail_strategy_service.py` resolve_overhead_rate / cost_rate_master CRUD | Hub Tab 后端服务，直接复用 |

**禁止读**（避免被旧设计带偏）：

- `DOC/基础表单/cost_center_master_填报模板_v1.md` / `v2.md`（已废弃，老板 0 工作量，已自动化）
- `DOC/agents/briefings/cost_center_master_draft_from_finance.md`（已废弃）
- `finance_to_costing_c1_contract_v1.0/v1.1/v1.2.md`（已被 v1.3 替代）

---

## 2. 任务范围（5 步串联）

### A1 · cost_center 主表 + 6 班组初稿（1 天）

#### A1.1 后端

**Migration `0040_cost_center.py`** — 直接抄 `cost_rate_hub_design_v1.md §4.1`：

```python
op.create_table(
    "cost_center",
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("code", sa.String(64), nullable=False),
    sa.Column("name", sa.String(128), nullable=False),
    sa.Column("type", sa.String(32), nullable=False),     # production|auxiliary|admin
    sa.Column("description", sa.Text),
    sa.Column("default_allocation_basis", sa.String(32)), # headcount|team_hours|revenue|floor_area|fixed_pct
    sa.Column("legacy_team_names", JSONB, server_default=sa.text("'[]'::jsonb")),
    sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
    sa.Column("metadata_json", JSONB, server_default=sa.text("'{}'::jsonb")),
    sa.Column("created_at", sa.TIMESTAMP, nullable=False, server_default=sa.func.now()),
    sa.Column("updated_at", sa.TIMESTAMP, nullable=False, server_default=sa.func.now()),
    sa.Column("deleted_at", sa.TIMESTAMP),
)
op.create_unique_constraint("uq_cost_center_code", "cost_center", ["code"])
op.create_index("idx_cost_center_active", "cost_center", ["is_active"])

# processes 加 cost_center_id FK
op.add_column("processes", sa.Column("cost_center_id", sa.String(36), nullable=True))
op.create_foreign_key("fk_processes_cost_center", "processes", "cost_center", ["cost_center_id"], ["id"])
op.create_index("idx_processes_cost_center", "processes", ["cost_center_id"])
```

**6 班组初稿数据**（Migration 同时 INSERT）：

| code | name | type | default_allocation_basis | legacy_team_names（与现有 processes.team_name 字符串匹配）|
|---|---|---|---|---|
| CC_DECOR_PROD | 家居饰品生产组 | production | team_hours | （Agent 跑 SQL 看 processes.team_name distinct 后人工分配，记录到 metadata.assignment_log）|
| CC_FABRIC_PROD | 布艺生产组 | production | team_hours | |
| CC_PRINT | 印花打印组 | auxiliary | team_hours | |
| CC_CUT_EDGE | 裁剪包边组 | auxiliary | team_hours | |
| CC_PACK_SHIP | 包装发货组 | auxiliary | headcount | |
| CC_ADMIN | 公共管理 | admin | headcount | |

> **班组名最终决定**：Agent 自主 — 拉 finance `/employees` 看 100 个员工的 `department` 字段聚合 → 与上面 6 个对齐 → 不一致时**以 finance 数据为准**调整 name（保持 code 不变），并把 finance department → cost_center mapping 写入 cost_center.metadata.finance_department_mapping 数组。

**老 processes.team_name 数据迁移**：Migration 跑完后，对每个 team_name distinct 值做模糊匹配（"家居"/"饰品" → CC_DECOR_PROD；"布艺"/"窗帘" → CC_FABRIC_PROD；"印花"/"转印" → CC_PRINT；"裁剪"/"包边" → CC_CUT_EDGE；"包装"/"发货"/"质检" → CC_PACK_SHIP；其他 → NULL 待人工补），写入 cost_center_id。匹配不上的行保留 NULL（不阻塞）。

**ORM**：`backend/src/planner/models.py` 加 `class CostCenter(Base)` + `Process.cost_center_id` 字段 + 双向 relationship。

**Service `cost_center_service.py`**：CRUD（list / get / create / update / soft_delete）+ `get_by_code(code)` + `list_active()` + `assign_processes(cost_center_id, process_ids)` 批量绑定。

**Router `cost_centers.py`**：

```
GET    /api/planner/cost-centers                # 含 process_count + employee_count（finance 真拉）
GET    /api/planner/cost-centers/{id}
POST   /api/planner/cost-centers                # 守卫 require_staff_role
PATCH  /api/planner/cost-centers/{id}
DELETE /api/planner/cost-centers/{id}            # soft delete
POST   /api/planner/cost-centers/{id}/assign-processes
```

#### A1.2 前端

**新建 `frontend/src/pages/costing/admin/CostCenterMasterPage.tsx`**：

- 表格列：code / name / type / 班组人数（拉 finance employees 按 cost_center.metadata.finance_department_mapping 反查）/ processes 数量 / default_allocation_basis / 操作
- 顶部操作：新建 / 批量分配工序
- 编辑抽屉：6 字段 + JSON 编辑器（legacy_team_names + finance_department_mapping）
- 路由：`/costing/admin/cost-centers`，挂在「系统运维」侧栏

#### A1.3 验收 A1

- [ ] Migration 0040 PG 双向跑通（upgrade head + downgrade -1 + upgrade head 数据完好）
- [ ] 6 个 cost_center 行已落库 + 至少 5 行 processes 自动迁移到 cost_center_id（具体数取决于现有 team_name 分布）
- [ ] `/costing/admin/cost-centers` 能 CRUD + 显示员工数和工序数
- [ ] `pytest backend/tests/planner/test_cost_center_service.py` 至少 8 条 PASS（CRUD + 6 班组 fixture + finance 反查 mock）

---

### A2 · cost_center_aggregator_service（1.5 天）

**目标**：用 finance 真 payroll by_employee 数据，按月聚合出每个 cost_center 的「人均工资 / 总工资 / 总工时（如果有）/ 人均时薪」。

#### A2.1 设计

**核心方法**：

```python
def aggregate_cost_center_payroll(
    db: Session,
    *,
    cost_center_id: str,
    period: str,  # 'YYYY-MM'
) -> CostCenterPayrollSnapshot:
    """
    1. 拉 cost_center.metadata.finance_department_mapping → 得到 finance department 列表
    2. 调 finance_c1_client.list_payroll(period_year, period_month, aggregation='by_employee')
       → 得到该月每个员工的 actual_paid + payment_source_types + fallback_reason
    3. 按 department 过滤命中本 cost_center 的员工
    4. 聚合：headcount / total_paid / avg_salary_per_employee
    5. 工时：当月 cost_center 关联 processes 在 model_version_processes 出现的总分钟数
       (通过 shipment_costing_results.metadata.process_minutes 累加，无 shipment 则跳过)
    6. 写入 cost_center_payroll_snapshot 表（新建，按 (cost_center_id, period) UNIQUE）
    7. 触发 cost_rate_master upsert：
       scope_type='cost_center' / scope_id=cost_center_id / rate_type='labor_per_minute'
       rate = total_paid / total_minutes (如果 total_minutes>0)
       source='auto_aggregated_from_finance' / data_quality='yellow' (自动算的不是手填)
       effective_from=period 第一天
    """
```

**新建表 `cost_center_payroll_snapshot`**（Migration 0041）：

```python
op.create_table(
    "cost_center_payroll_snapshot",
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("cost_center_id", sa.String(36), sa.ForeignKey("cost_center.id"), nullable=False),
    sa.Column("period", sa.String(7), nullable=False),  # 'YYYY-MM'
    sa.Column("headcount", sa.Integer, nullable=False),
    sa.Column("total_paid", sa.Numeric(14, 2), nullable=False),
    sa.Column("avg_salary", sa.Numeric(12, 2), nullable=False),
    sa.Column("total_minutes", sa.Numeric(14, 2)),       # 可空，无 shipment 时
    sa.Column("rate_per_minute", sa.Numeric(10, 4)),     # 可空，total_minutes=0 时
    sa.Column("data_source", sa.String(32), nullable=False),  # 'finance_payroll'|'finance_payroll_fallback'|'manual'
    sa.Column("data_quality", sa.String(16), nullable=False), # 'green'|'yellow'|'red'
    sa.Column("warnings", JSONB, server_default=sa.text("'[]'::jsonb")),  # finance fallback_reason 等
    sa.Column("metadata_json", JSONB, server_default=sa.text("'{}'::jsonb")),
    sa.Column("created_at", sa.TIMESTAMP, nullable=False, server_default=sa.func.now()),
    sa.Column("updated_at", sa.TIMESTAMP, nullable=False, server_default=sa.func.now()),
)
op.create_unique_constraint("uq_cost_center_payroll_period", "cost_center_payroll_snapshot", ["cost_center_id", "period"])
```

#### A2.2 集成点

**Router `cost_centers.py` 加 endpoint**：

```
POST /api/planner/cost-centers/{id}/aggregate-payroll?period=2026-04
GET  /api/planner/cost-centers/{id}/payroll-snapshots?since=YYYY-MM&until=YYYY-MM
POST /api/planner/cost-centers/aggregate-payroll-batch?period=2026-04   # 6 个 cost_center 一起跑
```

**触发 cost_rate_master upsert** 时复用 long_tail_strategy_service 现有 CRUD（不要直接改表，避免破坏审计 history）。

#### A2.3 验收 A2

- [ ] Migration 0041 PG 双向跑通
- [ ] 跑 `POST /cost-centers/aggregate-payroll-batch?period=2026-04`：6 个 cost_center 各产出 1 个 snapshot 行（即使 finance 4 月 payroll 0 行也要产出 fallback snapshot + warning）
- [ ] cost_rate_master 新增 ≤ 6 行 `rate_type='labor_per_minute'` `scope_type='cost_center'` 行（仅有工时数据的产出，total_minutes=0 不产出）
- [ ] `pytest backend/tests/planner/test_cost_center_aggregator.py` 至少 10 条 PASS（含 finance mock 模式 + finance 401/500 降级 + total_minutes=0 跳过 + finance department 不匹配警告）

---

### A3 · fixed_cost_amortizer_service（1.5 天）

**目标**：用 finance 真 payment_requests 数据（含完整 amort 5 字段），按月算出每个法人主体的固开月度分摊金额。

#### A3.1 设计

**核心方法**：

```python
def amortize_fixed_costs_for_period(
    db: Session,
    *,
    period: str,  # 'YYYY-MM'
) -> List[FixedCostAmortizationLine]:
    """
    1. 调 finance_c1_client.list_payment_requests(amort_covers_period=period)
       → 拿到所有覆盖本月的付款凭证（finance 已替我们做了时间段过滤）
    2. 对每条 payment_request：
       - 如果 is_monthly_amortized=True: amount = amort_monthly_amount
       - 如果 is_monthly_amortized=False 但 belong_month=period: amount = amount (一次性计入本月)
       - 否则: 跳过 (不属于本月)
    3. 按 expense_category 分类聚合 (cogs/selling/admin/financial/capital_recovery/platform_recharge)
    4. 按 company_name (受益主体) 进一步分组 (注意 pay_company vs company_name 的差异，按 company_name 归集)
    5. 写入 fixed_cost_amortization_line 表
    """
```

**新建表 `fixed_cost_amortization_line`**（Migration 0042）：

```python
op.create_table(
    "fixed_cost_amortization_line",
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("period", sa.String(7), nullable=False),
    sa.Column("payment_request_id", sa.String(36), nullable=False),  # finance 那边的 id
    sa.Column("beneficiary_company_id", sa.String(36)),  # finance master_companies.id (company_name)
    sa.Column("payer_company_id", sa.String(36)),         # finance master_companies.id (pay_company)，可能不同
    sa.Column("expense_category", sa.String(32), nullable=False),
    sa.Column("amount_amortized", sa.Numeric(14, 2), nullable=False),
    sa.Column("is_monthly_amortized", sa.Boolean, nullable=False),
    sa.Column("amort_months", sa.Integer),
    sa.Column("amort_start_period", sa.String(7)),
    sa.Column("metadata_json", JSONB, server_default=sa.text("'{}'::jsonb")),  # finance 原始 payload + match_status + invoice_status
    sa.Column("created_at", sa.TIMESTAMP, nullable=False, server_default=sa.func.now()),
)
op.create_index("idx_fca_period", "fixed_cost_amortization_line", ["period"])
op.create_index("idx_fca_beneficiary", "fixed_cost_amortization_line", ["beneficiary_company_id"])
op.create_index("idx_fca_category", "fixed_cost_amortization_line", ["expense_category"])
op.create_unique_constraint("uq_fca_period_payment", "fixed_cost_amortization_line", ["period", "payment_request_id"])
```

#### A3.2 集成点

**Router `fixed_costs_amortization.py`**：

```
POST /api/planner/fixed-costs/amortize?period=2026-04          # 拉 + 重算
GET  /api/planner/fixed-costs/amortization?period=2026-04
GET  /api/planner/fixed-costs/amortization/by-company?period=2026-04   # 聚合到 master_companies.id
GET  /api/planner/fixed-costs/amortization/by-category?period=2026-04  # 聚合到 6 类 expense_category
```

#### A3.3 验收 A3

- [ ] Migration 0042 PG 双向跑通
- [ ] 跑 `POST /fixed-costs/amortize?period=2026-04`：能从 finance staging 拉到 100 行 payment_requests 并按 amort_covers_period 落库
- [ ] `GET /fixed-costs/amortization/by-company?period=2026-04` 返回每家受益主体的本月固开总额（**注意 pay_company ≠ company_name 的场景：A 公司付钱 B 公司受益，按 B 归集**）
- [ ] `pytest backend/tests/planner/test_fixed_cost_amortizer.py` 至少 12 条 PASS（含 6 类 expense_category + amort 多月分摊 + 一次性 + pay_company≠company_name + finance 5xx 降级）

---

### A4 · cost_allocator_service（1.5 天）

**目标**：把 A3 算出的固开（按 master_companies 分组）按多级 fallback 分摊到 cost_center，让"固定开支"能落到具体班组上。

#### A4.1 设计

按 v1.3 §4.10 的多级 fallback：

| 费用类型 | 主分摊基础 | fallback 1 | fallback 2 |
|---|---|---|---|
| 房租 / 水电 / 物业 | floor_area_sqm | headcount | revenue |
| 平台佣金 / 售后 | revenue（按店铺）| - | - |
| 管理 / 办公 / 行政 | headcount | floor_area_sqm | 均摊 |

**核心方法**：

```python
def allocate_fixed_costs_to_cost_centers(
    db: Session,
    *,
    period: str,
    fallback_mode: Literal['strict', 'permissive'] = 'permissive',
) -> List[CostAllocationLine]:
    """
    1. 读 fixed_cost_amortization_line WHERE period=? GROUP BY beneficiary_company_id, expense_category
    2. 对每条 (company_id, expense_category, amount):
       a. 决定分摊基础 (rule table 见上)
       b. 拉对应的 driver:
          - floor_area: finance master_companies.floor_area_sqm (NULL → fallback)
          - headcount: finance employees count by department → cost_center
          - revenue: finance stores/revenue by store
       c. 按 driver 加权分摊到 cost_centers
       d. 写入 cost_allocation_line 表
    3. 返回总额 + 分摊结果 + fallback 路径审计
    """
```

**新建表 `cost_allocation_line`**（Migration 0043）：

```python
op.create_table(
    "cost_allocation_line",
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("period", sa.String(7), nullable=False),
    sa.Column("source_company_id", sa.String(36), nullable=False),     # 受益主体
    sa.Column("source_expense_category", sa.String(32), nullable=False),
    sa.Column("source_total_amount", sa.Numeric(14, 2), nullable=False), # 该类别总额
    sa.Column("target_cost_center_id", sa.String(36), sa.ForeignKey("cost_center.id"), nullable=False),
    sa.Column("allocation_basis", sa.String(32), nullable=False),     # 实际用的分摊基础
    sa.Column("allocation_basis_value", sa.Numeric(14, 4), nullable=False), # 该 cost_center 的 driver 值
    sa.Column("allocation_basis_total", sa.Numeric(14, 4), nullable=False), # 全部 cost_center 的 driver 总和
    sa.Column("allocation_weight", sa.Numeric(8, 6), nullable=False), # = value / total
    sa.Column("amount_allocated", sa.Numeric(14, 2), nullable=False),
    sa.Column("fallback_chain", JSONB, server_default=sa.text("'[]'::jsonb")),  # ['floor_area', 'headcount'] 表示降级
    sa.Column("warnings", JSONB, server_default=sa.text("'[]'::jsonb")),
    sa.Column("metadata_json", JSONB, server_default=sa.text("'{}'::jsonb")),
    sa.Column("created_at", sa.TIMESTAMP, nullable=False, server_default=sa.func.now()),
)
op.create_index("idx_cal_period_cc", "cost_allocation_line", ["period", "target_cost_center_id"])
op.create_index("idx_cal_company", "cost_allocation_line", ["source_company_id"])
```

**触发 cost_rate_master upsert**：

每个 (cost_center, period) 算出总固开后，按 cost_center 当月总产出折算 overhead_rate：

```
cost_rate_master:
  scope_type='cost_center'
  scope_id=<cost_center.id>
  rate_type='overhead_rate'
  rate = sum(amount_allocated WHERE target_cost_center_id=cc) / cost_center_total_revenue
  source='auto_allocated_from_finance'
  data_quality='yellow'
  effective_from=period 第一天
```

#### A4.2 集成点

**Router `cost_allocation.py`**：

```
POST /api/planner/cost-allocation/run?period=2026-04
GET  /api/planner/cost-allocation/lines?period=2026-04
GET  /api/planner/cost-allocation/by-cost-center?period=2026-04
```

**接 bom_generation_service**：把 `_resolve_overhead_rate` 第 2055~2073 行的 `cost_center_id=None` 改为从 model 反推（model → product_model_versions → model_version_processes → process.cost_center_id 取众数 → 传给 _hub_resolve）。

#### A4.3 验收 A4

- [ ] Migration 0043 PG 双向跑通
- [ ] 跑 `POST /cost-allocation/run?period=2026-04`：能从 A3 数据 + finance 真 driver 算出每个 cost_center 的固开分摊（即使 finance 4 月 stores/revenue 0 行也要走 fallback 而不是报错）
- [ ] cost_rate_master 新增 ≤ 6 行 `rate_type='overhead_rate'` `scope_type='cost_center'` 行
- [ ] `_resolve_overhead_rate` 端到端：KB8（已配 model 级 0.25）仍命中 model 层 → 0.25；未配 model 但所属 cost_center 已有自动算的 overhead_rate → 命中 cost_center 层 → 自动值
- [ ] `pytest backend/tests/planner/test_cost_allocator.py` 至少 12 条 PASS（含 4 种费用类型 × 多级 fallback 全场景 + finance master_companies floor_area 全 NULL 降级 + warnings 完整记录）

---

### A5 · Hub 面板「自动 vs 手动」切换 + 数据来源徽章 + Insights 4 看板加「按店铺主体」筛选（1.5 天）

#### A5.1 Hub 面板增强

`frontend/src/pages/costing/admin/LongTailCogsRatePage.tsx` 当前 2 Tabs（cogs / overhead_rate），加：

**OverheadRateTab + LaborRateTab** 列表新增 3 列：

| 列 | 内容 |
|---|---|
| 数据来源 | `<DataSourceBadge>`：🟢 manual（老板手填）/ 🔵 auto_aggregated_from_finance（A2 算的）/ 🟣 auto_allocated_from_finance（A4 算的）/ ⚫ legacy（历史数据）|
| 最近自动算 | rate + 算出日期 + sparkline 近 3 个月 |
| 操作 | 「采用自动值」按钮（一键把当前手填值换成 cost_center_payroll_snapshot 最新值，需要确认）|

**新 Tab「自动算法日志」**（labor_rate_log）：

- 表格：period / cost_center / 算出值 / 触发时间 / 数据源（finance payroll 期次）/ 警告
- 拉 `cost_center_payroll_snapshot` + `cost_allocation_line` 联合视图
- 顶部按钮「重算本月」→ 调 A2 + A3 + A4 三个 batch endpoint

**KB8 试算面板增强**：

实时显示「如果你采用 cost_center 自动算的 overhead_rate (0.247) vs 当前 model 级手填 (0.25)，对模型成本影响：±0.X 元 / ±X.X%」

#### A5.2 Insights 4 看板「按店铺主体」筛选维度

`frontend/src/pages/costing/insights/{ProfitInsightsPage,ShopInsightsPage,SalesInsightsPage,AfterSalesInsightsPage}.tsx` 顶部筛选栏新增：

```tsx
<Select placeholder="按店铺法人主体筛选（默认全部）">
  {/* 拉 finance /companies?entity_role=store 得到 4 店铺 */}
</Select>
```

**后端 5 个 analytics endpoint** 新增 query 参数 `legal_entity_company_id`：

- 透传到 SQL WHERE 条件，过滤 shipment.store.legal_entity_company_id == 该参数
- 不强制要求（不传 = 全部，向后兼容）

#### A5.3 验收 A5

- [ ] Hub 2 个 Tab（labor / overhead）显示「数据来源」徽章 + 「采用自动值」按钮
- [ ] 新 Tab「自动算法日志」可看到 A2 + A4 跑出的所有 snapshot
- [ ] KB8 试算面板能看到「自动 vs 手动」对比
- [ ] 4 看板顶部筛选栏可按 4 店铺主体过滤数据
- [ ] `cd frontend && npm run build` ✓

---

## 3. 关键代码定位（不需要再 grep）

| 用途 | 位置 |
|---|---|
| Hub 4 层 resolve 入口 | `backend/src/planner/services/long_tail_strategy_service.py` `resolve_overhead_rate(db, *, model_id, category, cost_center_id)` |
| BOM 接 Hub 链 | `backend/src/planner/services/bom_generation_service.py:2034` `_resolve_overhead_rate` —— **A4 完成后把 line 2066 的 `cost_center_id=None` 改为反推** |
| finance C1 client | `backend/src/planner/services/finance_c1_client.py` 7 个 list_* 方法（line 402-620）|
| finance C1 schemas | `backend/src/planner/services/finance_c1_schemas.py` 全部 DTO |
| 现有 long_tail UI | `frontend/src/pages/costing/admin/LongTailCogsRatePage.tsx`（已 2 Tabs，加日志 Tab + 自动徽章）|
| Insights 4 看板 | `frontend/src/pages/costing/insights/{Profit,Shop,Sales,AfterSales}InsightsPage.tsx` |
| Analytics service | `backend/src/planner/services/analytics_service.py` 7 个函数（5 endpoint 用）|
| 现有 finance 主数据 UI | `frontend/src/pages/costing/admin/FinanceMasterDataPage.tsx`（参考它的 6 Tabs 结构）|

---

## 4. 数据流（端到端）

```
┌─ ops 操作 ─────────────────────────┐  ┌─ 老板视角 ──────────────────┐
│ ① Hub 面板「重算本月」按钮      │  │ 打开 KB8 模型详情页        │
└──────────┬─────────────────────────┘  │ 看到「人工费 ¥7.34」       │
           ↓                               │ 旁边徽章：🔵 自动算       │
┌─ A5 Hub Router ────────────────────┐  │ 来源：CC_DECOR_PROD       │
│ POST /cost-rate-hub/recompute      │  │ 算出于：2026-05-10 16:00  │
│  ?period=2026-04                   │  │ 数据源：finance payroll    │
└──────────┬─────────────────────────┘  │ 警告：4 月 reconciliation │
           ↓                               │       未跑，用 declaration│
┌─ A2 cost_center_aggregator ────────┐  └──────────────────────────────┘
│ for cc in active_cost_centers:     │
│   payroll = finance.list_payroll(  │  ┌─ Insights 看板 ────────────┐
│     period_year, period_month,     │  │ 利润分析                    │
│     aggregation='by_employee')     │  │ ┌─筛选─┐                    │
│   filter by cc.finance_dept_map    │  │ │店铺▼ │ ← A5 新增          │
│   write cost_center_payroll_snap   │  │ └────┘                       │
│   upsert cost_rate_master          │  │ KB8 模型行 / 利润 ¥X        │
│     scope=cost_center              │  │   成本可信度 🟢 模型级精确  │
│     rate_type=labor_per_minute     │  └──────────────────────────────┘
└──────────┬─────────────────────────┘
           ↓
┌─ A3 fixed_cost_amortizer ──────────┐
│ payment_requests = finance.list(   │
│   amort_covers_period=period)      │
│ for pr: write fixed_cost_amort_line│
└──────────┬─────────────────────────┘
           ↓
┌─ A4 cost_allocator ────────────────┐
│ for (company, category, amount):   │
│   driver = pick(rule_table)        │
│   for cc in active_cost_centers:   │
│     write cost_allocation_line     │
│   upsert cost_rate_master          │
│     scope=cost_center              │
│     rate_type=overhead_rate        │
└──────────┬─────────────────────────┘
           ↓
┌─ 已有：bom_generation_service ─────┐
│ _resolve_overhead_rate             │
│   Hub 4 层 resolve(cost_center_id) │ ← A4 完成后接通
│   → 命中 cost_center 层 → 自动值  │
└──────────┬─────────────────────────┘
           ↓
┌─ 已有：shipment_costing_results ───┐
│ KB8 4 月发货行成本拆分自动透传    │
└────────────────────────────────────┘
```

---

## 5. 5 条用户验收标准（最终目标）

1. **A1 cost_center 主表**：`/costing/admin/cost-centers` 能看到 6 个班组 + 各班组员工数（finance 真拉）+ 工序数。Migration 0040 PG 双向跑通。
2. **A2 班组工资自动算**：跑 `POST /cost-centers/aggregate-payroll-batch?period=2026-04` 后，6 个 cost_center 各产出 1 个 snapshot（即使 finance 4 月 payroll 0 行也走 fallback 而不是报错），cost_rate_master 出现 ≤ 6 条 `rate_type=labor_per_minute scope_type=cost_center source=auto_aggregated_from_finance` 行。
3. **A3 + A4 固开自动分摊**：跑 `POST /fixed-costs/amortize?period=2026-04` + `POST /cost-allocation/run?period=2026-04` 后，能看到每个 cost_center 的固开分摊金额（含 fallback 路径审计），cost_rate_master 出现 ≤ 6 条 `rate_type=overhead_rate scope_type=cost_center source=auto_allocated_from_finance` 行。
4. **端到端 KB8 验证**：BOM 重算 KB8 时，`_resolve_overhead_rate` 能接到 cost_center 层（之前是写死 None）。如果 model 级仍配置了 0.25 → 命中 model 层（向后兼容）；如果删掉 model 级 → 命中 cost_center 层（自动值）。
5. **Hub 面板 + 4 看板增强**：Hub 显示「数据来源」徽章 + 「采用自动值」按钮 + 「自动算法日志」Tab；4 个 Insights 看板顶部新增「按店铺法人主体」筛选下拉。

---

## 6. 完成后归集（3 件）

1. **commit 一次**（feat(real-data-wiring) — 整个路径 A 一个大 commit，含所有 4 个 migration 0040~0043 + 4 个 service + 4 个 router + 3 个 frontend page + 全部测试）
2. **task_log.md 加 1 行**（按现有模式：日期 + 模块 + 角色 + 任务 + 结论 + 待办）
3. **system_capability_inventory.md 更新**：
   - §13.1 加 U10 行（如果有遗留小事）或在已完成事项审计追加 1 行（路径 A 全栈交付明细）
   - §13.3 追加审计行
   - 修订历史追加本行

---

## 7. 测试期望

- 后端单测覆盖每个 service ≥ 10 条（CRUD + 集成 finance C1 mock + 各种 fallback 场景 + 错误降级）
- `pytest backend/tests/planner -q` 总数：当前 ~290 → 任务后 ≥ 330（不允许任何回归）
- E2E：派单后跑一次 `backend/scripts/finance_c1_e2e_smoke.py --live --base-url=$FINANCE_C1_BASE_URL --api-key=$FINANCE_C1_API_KEY --payroll-authorized` 确认 finance 仍 7/7 全绿（防止你这边改动影响 finance 调用）
- `cd frontend && npm run build` 通过

---

## 8. 性能预算

- **A2 batch**：6 cost_center × 1 个 finance API call = 6 次 finance 调用，应在 5 秒内完成
- **A3**：1 次 finance call 拿全部 payment_requests（已在 finance 那边按 amort_covers_period 过滤），应在 3 秒内完成
- **A4**：纯 SQL，不调 finance，应在 1 秒内完成
- **任何 endpoint** P95 ≤ 2 秒；超过的话用 `cost_center_payroll_snapshot` 之类的物化表替代实时 join

---

## 9. 禁止改动 / 风险规避

- ❌ 不要改 `bom_generation_service._resolve_material_price`（Stage 2 物料链路上一轮已完成，不要再动）
- ❌ 不要改 finance C1 client / schemas / mock（v1.3 已稳定，只 consume 不改）
- ❌ 不要重新计算历史 `shipment_costing_results`（脚本只读，写新数据走新计算）
- ❌ 不要动 `cost_rate_master` 的 schema（已稳定，只 INSERT/UPDATE 数据，不加字段）
- ❌ 不要碰 contracts 文档 `finance_to_costing_c1_contract_v1.3_aligned.md`（已签字归档）
- ❌ 不要碰 `c1_hub_boundary_memo.md`（finance 仓库的，不是你的领地）
- ⚠️  **数据迁移要小心**：A1 给 processes 加 cost_center_id 时是 nullable + FK，不要给现有数据强制赋值（NULL 是合法的，下游 `_resolve_overhead_rate` 已经能 fallback）
- ⚠️  **finance fallback**：finance staging 4 月 payroll/stores 当前是空的（ops 还没导），你的代码必须在空数据下走 fallback + 记 warning 而不是报 500
- ⚠️  **pay_company vs company_name**：A3 一定要按 `company_name`（受益主体）归集，不是 `pay_company`（付款主体），否则成本会算到付款公司导致跨主体补贴还原失败

---

## 10. 完整自主权声明

按 `agent_rules.md §2 + §7` + `task_distribution_standard.md §0.2 + §3.1`：

✅ scope 内（§2 列出的 5 步）你拥有**完整自主权**：
- 表结构 / API 路径 / Pydantic schemas / 前端组件结构 / 测试 fixture 数据 全部你定
- 不需要"先报方案再实施"
- 实现细节遇到二选一时按"复用现有模式 > 新建" + "向后兼容 > 重构" + "测试覆盖 > 性能极致"原则
- 中间过程不汇报，到点交付即可

❌ 仅 3 种情况回 Hub：
1. **scope 外**：发现需要改 finance 契约 / Stage 2 物料链路 / cost_rate_master schema 才能完成 → 立即停下来回 Hub
2. **数据冲突**：finance 真数据出现与 v1.3 契约说明完全相反的 schema（比如 payment_requests 字段缺失）→ 回 Hub 让 Hub 协调 finance
3. **5 条验收标准做不到**：评估发现 7 天工作量做不完 5 条 → 主动汇报当前进度 + 砍掉哪条 + 风险

---

## 11. 6 班组初稿确认（启动前自主决定）

老板给了"c) Agent 自主决定"的指令：

1. 启动后**第一件事**：调 finance staging `/employees`（已通过 KEY 验证）拿 100 个员工 + department 字段聚合
2. 与本任务 §2 A1.1 的 6 班组初稿对照
3. 不一致时**以 finance 数据为准**调整 cost_center.name（保持 code 不变）
4. 把 finance department → cost_center mapping 写入 `cost_center.metadata.finance_department_mapping`
5. 整个决策过程在 cost_center.metadata.assignment_log 记录（带 reasoning），便于后续审计

如果 finance employees 完全没有 department 字段或全部 NULL → 用 §2 A1.1 默认 6 班组初稿，warning 记录到 metadata.warnings。

---

## 12. 元信息

| 项 | 值 |
|---|---|
| 文档版本 | v1.0（首版）|
| 创建日期 | 2026-05-10 15:40 北京时间 |
| 创建人 | Hub Agent |
| 必读文档数 | §1 列出 7 份（约 30 分钟）|
| 估计工作量 | 7 天 wall-clock（5 步串联）|
| 估计 brief Token | ~12K tokens（远低于编码工作量的 30% 上限，符合规则 §7）|
| 完成定义 | §5 五条用户验收标准全过 + §6 三件归集完成 |
| 关联前置 | finance C1 v1.3 真闭环（已完成 2026-05-10 15:35）+ Hub MVP（已完成 2026-05-09 21:30）+ Stage 2 物料 BOM 接入（已完成 2026-05-10 14:30）|
| 关联后续 | U1 SKU 角色（引流款 vs 利润款）/ U3 + U4 评审会前文档同步 / Hub Phase 2 历史价格回溯 |
