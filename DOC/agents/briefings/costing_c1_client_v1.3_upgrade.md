# costing C1 Client v1.3 升级 + 联调准备 — 后端中等任务单（2026-05-10）

> 派单类型：后端中等任务（升级现有 finance_c1_client + mock + 新增 2 个 endpoint client + 联调测试）
> 预估工作量：2~4 小时（AI Agent）
> 承接 Agent 角色：`@Costing Backend Agent`（完整自主权 + ai-costing-system 仓库内部）
> 唯一硬约束：finance staging URL + test key 还没拿到，**先用 mock 跑通**，预留切换真接口的开关；不要等 staging

---

## 0. 30 秒摘要

finance 已经完成 v1.3 全部 9 件事（commit `f8b691c` on `feat/c1-costing-contract-v1`），含 2 个新 endpoint：
- `GET /api/v1/c1/stores/revenue` (店铺月度真实营收)
- `GET /api/v1/c1/payment-requests` (含 amort + 6 类 + pay_company)

costing 这边现有 client（commit `4e5cba5b`）只覆盖了 v1.0 的 5 个原始 endpoint。本任务升级到 v1.3 终态：加 2 个新 endpoint 方法 + ?since/?until 参数支持 + envelope 升 v1.3 + mock 数据扩展。

---

## 1. 必读 3 步

```
[ ] 1. 完整读契约 v1.3 终态：
       /home/admin/ai-costing-system/DOC/costing/blueprints/finance_to_costing_c1_contract_v1.3_aligned.md
       重点：§4.6 payment-requests / §4.10 floor_area / §4.2 stores/revenue

[ ] 2. 读 finance 备忘录（理解他们落地实现细节）：
       /home/admin/projects/finance-analyzer/DOC/contracts/c1_inbound_costing.md（v1.3）
       重点：7 endpoint 一览 + 完整字段映射 + payroll 数据源表

[ ] 3. 看 commit 4e5cba5b 现有 costing client 实现：
       cd /home/admin/ai-costing-system && git show 4e5cba5b --stat
       关键文件：backend/src/planner/services/finance_c1_client.py
                 backend/src/planner/services/finance_c1_schemas.py
                 backend/tests/mocks/finance_c1_mock.py
                 backend/src/planner/routers/finance_c1_proxy.py
                 frontend/src/pages/costing/admin/FinanceMasterDataPage.tsx
```

---

## 2. 任务范围

### 2.1 新增 2 个 client 方法 + 对应 schemas + mock 数据

#### `list_stores_revenue`

```python
def list_stores_revenue(
    self,
    period_year: int,
    period_month: int,
    store_id: str | None = None,
    since: str | None = None,
) -> dict:
    """GET /api/v1/c1/stores/revenue"""
```

mock 数据：4 店铺 × 至少 1 个月（4 月），按契约 §4.2 example response 1:1 复制；含 gross_revenue / net_revenue / platform_fee_paid / data_source / data_quality 字段。

#### `list_payment_requests`

```python
def list_payment_requests(
    self,
    period: str | None = None,                # YYYYMM
    company_id: str | None = None,
    pay_company: str | None = None,
    expense_category: str | None = None,
    is_amortized: bool | None = None,
    amort_covers_period: str | None = None,    # YYYYMM (finance 加的额外参数)
    since: str | None = None,
) -> dict:
    """GET /api/v1/c1/payment-requests"""
```

mock 数据：至少 12 条凭证（覆盖 6 类 expense_category 各 2 条），含完整 amort 配置 + pay_company vs company_name 不同的场景。按契约 v1.3 §4.6 example response 1:1 复制。

### 2.2 现有 5 方法 + 新 2 方法统一加 ?since/?until 支持

所有 7 个方法签名加 `since: str | None = None, until: str | None = None` 参数，传给 GET 请求。

### 2.3 envelope 升 v1.3

- mock response 顶层 `_api_version` 从 `1.0` 升到 `1.3`
- 加 `pagination.last_updated_at` 字段（mock 数据用 `datetime.now().isoformat()`）

### 2.4 master_companies 加 5 字段（4 recognition + floor_area_sqm）

`FinanceCompanyDTO`（schemas）+ mock 数据加：
- `revenue_recognition: bool`
- `material_purchase_recognition: bool`
- `payroll_recognition: bool`
- `fixed_cost_recognition: bool`
- `floor_area_sqm: Decimal | None`（部分主体填值，部分留 NULL 演示 fallback 场景）

### 2.5 payroll mock 升级到 by_employee 模式

- 每员工每月 1 行（不按 department 聚合）
- mock 数据 metadata 含 `actual_paid / payment_source_types / fallback_reason` 字段（按 finance 备忘录 §4.5 落地版本）

### 2.6 finance_c1_proxy.py 加 2 个新 endpoint

```python
GET /api/planner/finance/stores/revenue   → list_stores_revenue
GET /api/planner/finance/payment-requests → list_payment_requests
```

### 2.7 前端：FinanceMasterDataPage.tsx 加 2 个 Tab

新增：
- **「店铺营收」Tab**：表格列 store_name / company_id / gross_revenue / net_revenue / platform_fee_paid / data_quality（用现有 CostQualityBadge 复用色系）
- **「付款凭证」Tab**：表格列 payment_date / belong_month / amount / company_name / pay_company / expense_category / amort_months / match_status

加 2 个 fetcher 在 `frontend/src/services/financeC1.ts`，加 2 个 DTO 类型。

### 2.8 联调脚本（可在没 staging URL 时先跑 mock）

新建 `backend/scripts/finance_c1_e2e_smoke.py`：
- 对 7 个 endpoint 各发 1 个标准请求 + assert 响应基本结构 + 输出"all 7 endpoints consumed OK / X failed"
- 支持 `--mock` (走本地 mock) 和 `--live --base-url=<finance staging>` (走真接口) 两种模式
- 默认 `--mock` 自检通过 → 等用户拿到 staging URL 时切 `--live` 一键跑联调

### 2.9 不在 scope 内（不要做）

- ❌ 不动 BOM / Hub / Insights / Stage 2 物料相关
- ❌ 不实现 `cost_center_aggregator_service`（U2 后续任务）
- ❌ 不实现 `fixed_cost_amortizer_service`（依赖真 payment_requests 数据）
- ❌ 不实现 `cost_allocator_service`（依赖真 floor_area 数据 + Stage 3）
- ❌ 不动现有契约文档

---

## 3. 完成标准

```
[ ] B1 list_stores_revenue / list_payment_requests 2 个方法实现完毕
[ ] B2 7 个方法都支持 ?since/?until 参数
[ ] B3 mock 数据按 v1.3 契约 1:1 复制（envelope 1.3 + 7 endpoint 全 mock 覆盖）
[ ] B4 4 recognition Boolean + floor_area_sqm 在 mock companies 数据 + Pydantic DTO 都体现
[ ] B5 payroll mock 按 by_employee 每员工每月 1 行返回（不 group）
[ ] B6 2 个新 proxy endpoint 在 /api/planner/finance/* 可用
[ ] B7 backend/tests/planner/test_finance_c1_client.py 加 5 条新 case 覆盖 v1.3（stores_revenue / payment_requests / since / new fields / by_employee mode）全过
[ ] B8 backend/scripts/finance_c1_e2e_smoke.py --mock 跑通：7/7 endpoints OK
[ ] F1 FinanceMasterDataPage.tsx 加「店铺营收」+「付款凭证」2 个 Tab，数据来源 mock 时正确显示
[ ] F2 顶部 Badge 仍正确反映 mock / cache / live 三态
[ ] F3 frontend npm run build 无错误
[ ] G1 没碰 BOM / Hub / Insights / 契约文档（git diff 验证）
```

---

## 4. 验收命令（自主选 1~3 条）

```bash
# A) 单元测试
cd /home/admin/ai-costing-system
pytest backend/tests/planner/test_finance_c1_client.py -v

# B) E2E smoke (mock)
PYTHONPATH=backend python -m backend.scripts.finance_c1_e2e_smoke --mock

# C) 前端 build
cd frontend && npm run build
```

---

## 5. 收工归集 3 件

1. **commit 1 次**（标题 `feat(finance-c1-v1.3): client 升级 2 个新 endpoint + ?since 参数 + 4 recognition + floor_area + by_employee mock`）
2. **更新 task_log.md** 加 1 行
3. **更新 system_capability_inventory.md §13.1 U2 状态** → 🟢 **costing 侧 v1.3 client 完成（mock 联调通，等 finance staging URL）**

push 自决（ai-costing-system 仓库可以 push）。

---

## 6. 唯一回 Hub 的 3 种情况

1. **scope 不够**：契约 v1.3 某字段在 mock 设计 / 现有 client 无法表达
2. **架构冲突**：现有 finance_c1_client 升级到 v1.3 会破坏 Hub MVP / Insights 的现有消费
3. **完全卡死**：超过 30 分钟无进展

其他全部自主决策。

---

## 7. 元信息

| 项 | 值 |
|---|---|
| 创建日期 | 2026-05-10 14:35 北京时间 |
| 触发原因 | finance 完成 v1.3 5 项增量（commit `f8b691c`），等 costing client 升级后联调 |
| 关联文档 | `finance_to_costing_c1_contract_v1.3_aligned.md` v1.3 + finance 备忘录 v0.4 |
| 关联 commit | 4e5cba5b（v1.0 client 已就绪，本任务升级到 v1.3）|
| 期望承接 | Costing Backend Agent |
| 期望完工 | 2~4 小时后台 |
| 完工后 Hub 动作 | 等用户拿到 finance staging URL + test key → smoke --live 跑联调 → 回执 finance → 双方签字闭环 |
