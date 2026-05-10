# finance → costing C1 契约 v1.3 双方对齐版（终态）

> **本文档作用**：在 finance 团队 2026-05-10 13:00 备忘录 (`/home/admin/projects/finance-analyzer/DOC/contracts/c1_hub_boundary_memo.md`) 的基础上做的双方对齐版。**这是 costing 侧最终权威清单**。
> **创建日期**：2026-05-10 13:30 北京时间
> **触发原因**：finance 主动提案 v1.2.1 加 `payment_requests` 接口 + 边界 align。本 v1.3 一次性收口。
> **关联文档**：
> - finance 侧权威：`/home/admin/projects/finance-analyzer/DOC/contracts/c1_hub_boundary_memo.md`（双方对照实施版）
> - costing 侧权威：本文件
> - 历史存档：`finance_to_costing_c1_contract_v1.0/v1.1/v1.2_global.md`（不再使用）

---

## 0. 30 秒摘要（双方负责人看这段）

经过 finance 备忘录 align，C1 契约**终态确定**为 9 件事：

```
✅ 已完成（v1.0 finance Agent 在 feat/c1-costing-contract-v1 branch）：
  1. GET /api/v1/c1/companies
  2. GET /api/v1/c1/stores
  3. GET /api/v1/c1/employees（参考字段）
  4. GET /api/v1/c1/fixed-costs（v1.3 降级为"汇总视图"，摊销字段不加）
  5. GET /api/v1/c1/payroll（v1.3 强化 by_employee 必须真支持，含 2026+/≤2025 双源策略）

🆕 v1.3 新增（finance 1.5~2 人天）：
  6. master_companies 加 4 个业务画像 Boolean 标签字段
  7. GET /api/v1/c1/stores/revenue（基于 LedgerMonthlySummary）
  8. GET /api/v1/c1/payment-requests（finance 主动提案，含 amort + 6 类 expense_category + pay_company）
  9. 所有 GET 加 ?since/?until 增量参数

❌ v1.3 撤回（finance 不做）：
  - v1.2 §4.3 fixed_monthly_costs 加 amortization 字段（用 payment_requests 替代）
  - v1.1.1 §3.7 GET /api/v1/c1/fixed-cost-allocations（摊法归 costing 自建）
```

**终态工作量**：finance 1.5~2 人天 + finance ops 0.5~1 天 + costing 1~1.5 天 + 联调 0.5 天 = **2~2.5 天 wall clock**

---

## 1. v1 演进收口（最后一次 — 不再修订）

| 版本 | 时间 | 关键决策 | 状态 |
|---|---|---|---|
| v1.0 | 05-10 07:40 | 5 个原始 API + master_companies canonical | ✅ 已实施（branch 待 push）|
| v1.1 | 05-10 12:10 | 加班组聚合 + cost_center_mapping | ❌ 撤回（班组归 costing）|
| v1.1.1 | 05-10 12:18 | 拆 gross_salary 5 项 | ❌ 撤回（财务 total 已含全部）|
| v1.2 | 05-10 12:25 | 加 4 标签 + stores/revenue + amort 字段 + ?since | 🟡 部分采纳 |
| **v1.3** | **05-10 13:30** | **基于 finance 备忘录 align：撤回 amort 字段 + 撤回 fixed-cost-allocations + 接受 payment_requests 提案** | ✅ **终态** |

---

## 2. 终态边界矩阵（与 finance 备忘录 §1 完全一致）

| 能力 | finance | costing | 备注 |
|---|---|---|---|
| 主体/店铺/银行账户 主数据 | ✅ | ❌ | 含 4 业务画像标签 |
| 员工花名册 + 工资真实数据 | ✅ | ❌ | 2026+ reconciliation / ≤2025 declaration |
| 固开台账（汇总视图）| ✅ | ❌ | fixed_monthly_costs |
| 固开凭证（含摊销 + 6 类 + pay vs receive 主体）| ✅ | ❌ | **payment_requests（v1.3 新增暴露）**|
| 店铺月度真实营业额 | ✅ | ❌ | stores/revenue |
| 银行流水 / 平台扣款 | ✅ | ❌ | LedgerMonthlySummary |
| 班组（cost_center）归属 + 比例 | ❌ | ✅ | costing 自建 |
| 共享费用分摊规则引擎 | ❌ | ✅ | costing 自建（v1.3 撤回 finance 摊法 API）|
| 跨期摊销执行（按 amort_months 平摊到月份）| ❌ | ✅ | costing 用 payment_requests 数据自己摊 |
| 品类/工序/SKU 制造费率 | ❌ | ✅ | cost_rate_hub |
| 发货利润事实表 | ❌ | ✅ | shipment_profit_fact |
| 三视图 (FI/CO/Group) | finance 只给 FI 事实 | CO + 合并归 costing | |
| webhook / 写回 | ❌ | ❌ | v2 计划 |

---

## 3. v1.3 撤回清单（finance 不要做的事）

### 3.1 撤回 v1.2 §4.3 fixed_monthly_costs 加 amortization 字段

**原因**：finance payment_requests 已有完整摊销引擎（amort_months/start/end/monthly_amount），重复造轮子无意义。

**替代**：costing 用 payment_requests（v1.3 §4.6）数据 + 内部 amortization service，把跨期费用平摊到正确月份。

### 3.2 撤回 v1.1.1 §3.7 GET /api/v1/c1/fixed-cost-allocations

**原因**：分摊规则属于"经营建模"（每家工厂规则不同、可能频繁调整），按 finance 备忘录边界主张归 costing。

**替代**：costing 自建 `cost_allocator_service` + 自己定义 11 项摊法 + 用 finance 给的原始 driver 数据（floor_area, 营业额, 班组人数等）算摊法结果。

### 3.3 撤回 v1.1.1 §10.2 拆 gross_salary 5 项（沿用 v1.2 撤回）

**原因**：财务 total_labor_cost 已含全部，拆细 = 财务做无用功。

---

## 4. v1.3 finance 侧实施清单（终态 9 件事）

### 4.1 master_companies 加 4 个业务画像标签（保留 v1.2 §4.1）

| 字段 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `revenue_recognition` | Boolean | false | 真实营收归此主体 |
| `material_purchase_recognition` | Boolean | false | 真实材料成本归此主体 |
| `payroll_recognition` | Boolean | false | 真实人工成本归此主体 |
| `fixed_cost_recognition` | Boolean | false | 真实固开归此主体 |

**与 payment_requests 关系**：4 个标签是"主体的稳定业务画像"（管理会计层），payment_requests.pay_company / company_name 是"每笔付款的具体主体"（事实层）。两者互补：标签让 costing 快速理解主体角色，凭证让 costing 追溯具体归属。

### 4.2 新增 GET /api/v1/c1/stores/revenue（保留 v1.2 §4.2）

基于 `LedgerMonthlySummary` WHERE `profile_name='alipay_monthly_statement'`，零业务逻辑改动。

详细 schema 沿用 v1.2 §4.2，不重复（见 finance 备忘录 §4.2）。

### 4.3 GET /api/v1/c1/fixed-costs 不变（v1.0 已实施）

**v1.3 调整**：response **不加** amortization 字段（撤回 v1.2 §4.3）。

**定位明确**：fixed_monthly_costs 是"已聚合的月度视图"（按主体按月按 cost_category 11 类）。如果 costing 需要凭证级 + 摊销详情，走 §4.6 payment_requests 接口。

**与 payment_requests 的取数策略**（costing 内部约定）：
- 算月度成本汇总 → 用 fixed_monthly_costs（性能好）
- 跨期费用摊销 → 用 payment_requests（含 amort 配置）
- 异常诊断/凭证追溯 → 用 payment_requests
- 应付账款分析 → 用 payment_requests（含 invoice_status）

### 4.4 所有 GET 加 ?since=/?until= 增量参数（保留 v1.2 §4.4）

无变化。

### 4.5 GET /api/v1/c1/payroll 真实落地 by_employee（保留 v1.2 §4.5 + finance 备忘录补强）

**关键补强**（来自 finance 备忘录 §4.5）：
- 数据源策略：**2026+ 用 salary_reconciliation**（实发，排除 payment_method='cash' 避免与 payment_requests 现金重复）
- ≤2025 用 salary_declaration_details
- **绝对禁止**用 A21 银行流水"劳务费"科目（混合内容）+ 跨年回退/扩白名单（导致虚增）

字段沿用 v1.2 §4.5，不变。

### 4.6 新增 GET /api/v1/c1/payment-requests（v1.3 新增 — finance 主动提案）

**用途**：暴露付款凭证级数据（含摊销配置 + 6 类管理会计分类 + 付款主体/受益主体分离）。

```
GET /api/v1/c1/payment-requests
    ?period=YYYYMM                    (可选，按 belong_month 过滤)
    [&company_id=<uuid>]               (可选，按受益主体)
    [&pay_company=<string>]            (可选，按付款主体)
    [&expense_category=cogs|selling|admin|financial|capital_recovery|platform_recharge]
    [&is_amortized=true|false]         (可选，过滤摊销/非摊销)
    [&since=...]&[until=...]
```

**Response 200**（基于现有 PaymentRequest ORM 字段）：

```json
{
  "_api_version": "1.3",
  "data": [
    {
      "id": "uuid",
      "payment_date": "2026-04-15",
      "belong_month": "202604",
      "amount": 12000.00,
      "company_name": "杭州某某家居饰品有限公司",     // 费用承担主体（受益）
      "company_id": "uuid",
      "pay_company": "杭州某某店铺有限公司",          // 实际付款主体
      "store_department": "天猫旗舰店",               // 店铺/部门归属
      "primary_subject": "管理费用",                  // 一级科目
      "secondary_subject": "办公费",                  // 二级科目
      "expense_category": "admin",                    // 6 类管理会计分类
      "is_monthly_amortized": true,
      "amort_months": 12,
      "amort_start_period": "202601",
      "amort_end_period": "202612",
      "amort_monthly_amount": 1000.00,
      "reason": "全年办公耗材采购",
      "match_status": "full",                         // 银行流水匹配状态
      "matched_amount": 12000.00,
      "invoice_status": "已回票",
      "invoice_gap": 0.00
    }
  ],
  "pagination": {
    "page": 1,
    "page_size": 100,
    "total": 245,
    "last_updated_at": "2026-05-10T12:00:00+08:00"
  }
}
```

**鉴权**：与其他接口一致（`X-Costing-Api-Key`）。

**costing 内部消费策略**（不在 finance scope，记录在此让双方理解）：

```python
# costing 侧 fixed_cost_amortizer_service（内部新建）
def get_amortized_costs_for_month(target_year: int, target_month: int) -> dict:
    """
    拉 payment_requests，按 amort 配置把跨期费用平摊到 target_month
    """
    target_period = f"{target_year:04d}{target_month:02d}"
    
    # 拉所有 amort_start <= target <= amort_end 的凭证
    requests = c1_client.list_payment_requests(
        amort_covers_period=target_period
    )
    
    return {
        "amortized_total": sum(r["amort_monthly_amount"] for r in requests if r["is_monthly_amortized"]),
        "non_amortized_total": sum(r["amount"] for r in requests if not r["is_monthly_amortized"] and r["belong_month"] == target_period),
        "by_expense_category": group_by(requests, "expense_category"),
        "by_pay_company_vs_company": pivot(requests, "pay_company", "company_name"),
    }
```

---

## 5. costing 内部要做的（基于 finance 备忘录 §1 边界 + v1.3 调整）

| # | 项 | 说明 | 用什么数据 |
|---|---|---|---|
| 1 | 新表 `employee_cost_center_assignment` | 员工→班组细粒度映射（支持比例）| 内部 + payroll by_employee |
| 2 | 新 service `cost_center_aggregator_service` | 班组人均工时单价聚合 | payroll by_employee |
| 3 | 新 service `fixed_cost_amortizer_service` | 跨期摊销平摊 | **payment_requests**（不是 fixed_monthly_costs）|
| 4 | 新 service `cost_allocator_service` | 11 项摊法计算（撤回 finance §3.7）| fixed_monthly_costs + master_companies.floor_area + stores/revenue |
| 5 | 新 UI `/costing/admin/cost-centers` | 班长拖员工到班组 | - |
| 6 | 新 UI `/costing/admin/legal-entities` | 老板看 4 个 recognition 标签 | companies |
| 7 | 新 UI `/costing/admin/finance-master` 加 revenue Tab | 显示 4 店铺月度真实营收 | stores/revenue |
| 8 | 新 UI `/costing/admin/payment-vouchers` | 凭证级追溯（异常诊断用）| payment_requests |
| 9 | C1 client 加 `list_payment_requests / list_stores_revenue` 方法 + ?since 增量参数 | 性能优化 | - |

---

## 6. 验收标准（沿用 finance 备忘录 §7，加 1 条）

### 6.1 finance 侧 ✅（11 条 = 备忘录 10 条 + v1.3 新增 1 条）

```
[ ] F1~F10 见 finance 备忘录 §7.1
[ ] F11 撤回 fixed_monthly_costs 不加 amortization 字段（避免老 v1.2 sub-agent 走错路径）
```

### 6.2 双方联调 ✅（沿用 finance 备忘录 §7.2 5 条 + 加 1 条）

```
[ ] E1~E5 见 finance 备忘录 §7.2
[ ] E6  costing 用 payment_requests + 内部 amortizer 算 4 月跨期摊销，结果与 finance ops 人工核对一致
```

---

## 7. 工作量（v1.3 终态）

| 角色 | 任务 | 人天 | AI Agent 时长 |
|---|---|---|---|
| finance Agent | §4.1~§4.6 八件事 + payment-requests 接口 | 1.5~2 | 6~8 小时 |
| finance ops | 7 主体标签 + 历史 amort 数据补值（如还需）| 0.5~1 | — |
| costing Agent | §5 中 9 项内部建设 | 1~1.5 | 4~5 小时 |
| 双方联调 | E1~E6 共 6 条 | 0.5 | — |
| **总 wall clock** | | **2~2.5 天**（双 AI Agent 并行 + ops 配合）| |

---

## 8. 元信息

| 项 | 值 |
|---|---|
| 文档版本 | v1.3 双方对齐版（终态）|
| 创建日期 | 2026-05-10 13:30 北京时间 |
| 拍板人 | costing Hub Agent + 待 finance 负责人确认 |
| 触发 | finance 备忘录 `/home/admin/projects/finance-analyzer/DOC/contracts/c1_hub_boundary_memo.md` v1.2-boundary-memo |
| 替代关系 | 本 v1.3 是 costing 侧**唯一权威清单**；与 finance 备忘录配对使用 |
| 状态 | 终态（除非业务重大变化不再修订）|
| 期望承接 | finance Agent + finance ops + costing Agent |
| 期望完工 | 2~2.5 天 wall clock |

---

## 9. 双方负责人签字栏

```
finance 负责人 (待签字 2026-05-_____): __________________
costing 负责人 (Hub Agent 已确认 2026-05-10): __________________
```

---

## 10. 一句话给 finance 团队

收到你们 13:00 备忘录 + payment_requests 提案，**全部采纳**。最终清单见 §0。撤回 v1.2 §4.3 (fixed_monthly_costs 不加 amortization) + v1.1.1 §3.7 (fixed-cost-allocations 不做)，加 v1.3 §4.6 (payment-requests)。其余沿用 v1.2。**双方负责人签字后即可启动实施**。
