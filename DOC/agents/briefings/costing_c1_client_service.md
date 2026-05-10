# costing C1 Client Service — 全栈中等任务单（2026-05-10）

> 派单类型：后端中等任务（在 ai-costing-system 写 finance C1 拉取 client + 缓存 + 降级 + UI 接入）
> 预估工作量：3~6 小时（AI Agent）
> 承接 Agent 角色：`@Costing Backend Agent`（完整自主权）
> 唯一硬约束：finance API 还没真起，所以**先用 mock 跑通**，预留切换真接口的开关

---

## 0. 30 秒摘要

按契约 `/home/admin/ai-costing-system/DOC/costing/blueprints/finance_to_costing_c1_contract_v1.md` §3，在 ai-costing-system 写 1 个 `finance_c1_client.py` service：拉 5 个 endpoint + 5 分钟 TTL 缓存 + finance 挂时降级到 cache。完成后跑契约 §4.2 的 5 条消费测试 + UI 在 `/costing/admin/cost-centers` 展示从 finance 拉来的公司列表（只读）。

---

## 1. 必读 3 步

```
[ ] 1. 通读契约 finance_to_costing_c1_contract_v1.md（重点 §3 5 个 API + §4.2 消费测试 + §6 鉴权限流）
[ ] 2. 看现有 backend/src/planner/services/ 里有没有类似 client（grep "httpx" 或 "requests"）确认风格
[ ] 3. 看现有 frontend/src/pages/costing/admin/ 有哪些 admin 页面参考 UI 风格
```

---

## 2. 任务范围

### 2.1 后端 — finance C1 client service

新建 `backend/src/planner/services/finance_c1_client.py`，含 5 个方法：

```python
class FinanceC1Client:
    def __init__(self, base_url: str, api_key: str, payroll_authorized: bool = False):
        self.base_url = base_url
        self.api_key = api_key
        self.payroll_authorized = payroll_authorized
        self._cache = TTLCache(maxsize=128, ttl=300)  # 5 min default

    def list_companies(self, entity_role=None, is_active=True) -> list[dict]: ...
    def list_stores(self, company_id=None) -> list[dict]: ...
    def list_employees(self, contract_company_id=None) -> list[dict]: ...
    def list_fixed_costs(self, period_year: int, period_month: int) -> list[dict]: ...
    def list_payroll(self, company_id: str, period_year: int, period_month: int) -> list[dict]: ...
```

**关键行为**：
- 用 `httpx` (sync 或 async 都可，看 finance 仓库现有风格匹配)
- Header 自动注入 `X-Costing-Api-Key: <self.api_key>`
- payroll 自动加 `X-Payroll-Authorized: true`（如果 payroll_authorized=True）
- 缓存 keyed by 完整 query params
- 失败降级：`httpx.RequestError` 或 5xx → 返回最近一次 cache + log warning + 在返回的 dict 加 `_data_source: "cache"` 标记
- 401/403 → 抛 `FinanceC1AuthError`（不降级，让上层知道）

### 2.2 后端 — Pydantic schemas

新建 `backend/src/planner/schemas/finance_c1.py`，对应契约 §3.1~§3.5 example response 的字段：

```python
class FinanceCompanyDTO(BaseModel):
    id: str
    legal_name: str
    tax_payer_type: Literal["general", "small_scale"]
    entity_role: Literal["factory", "shop", "holding", "mixed"]
    is_active: bool
    # ... 按契约 §3.1 完整列

class FinanceStoreDTO(BaseModel): ...
class FinanceEmployeeDTO(BaseModel): ...
class FinanceFixedCostDTO(BaseModel): ...
class FinancePayrollDTO(BaseModel): ...
```

### 2.3 后端 — Mock server（关键，必须做）

因为 finance 那边还没起 API，所以新建 `backend/tests/mocks/finance_c1_mock.py`：

```python
"""
Mock finance C1 API responses，按契约 §3 example response 1:1 复制。
跑测试 + 本地 dev 时用。Production 切到真 finance API。
"""

MOCK_COMPANIES = [
    {
        "id": "mock-company-uuid-1",
        "legal_name": "杭州某某家居饰品有限公司",
        "tax_payer_type": "general",
        "entity_role": "factory",
        # ... 按契约 §3.1
    },
    # 至少 7 条（3 工厂 + 4 店铺）
]

MOCK_STORES = [...]   # 4 条
MOCK_EMPLOYEES = [...]  # 至少 3 条
MOCK_FIXED_COSTS = [...]  # 11 条（每个 cost_category 至少 1 条）
MOCK_PAYROLL = [...]  # 至少 6 条（6 班组）
```

### 2.4 后端 — 配置开关

在 `backend/src/planner/settings.py`（或 finance_c1 配置文件）加：

```python
FINANCE_C1_BASE_URL = os.getenv("FINANCE_C1_BASE_URL", "http://localhost:8001")
FINANCE_C1_API_KEY = os.getenv("FINANCE_C1_API_KEY", "dev-key-change-in-prod")
FINANCE_C1_USE_MOCK = os.getenv("FINANCE_C1_USE_MOCK", "true").lower() == "true"
```

如果 `FINANCE_C1_USE_MOCK=true`，client 不发 HTTP 请求，直接返回 mock 数据。

### 2.5 后端 — Router（轻量代理）

新建 `backend/src/planner/routers/finance_c1_proxy.py`，提供 5 个 GET endpoint 给前端用：

```python
GET /api/planner/finance/companies     → FinanceC1Client.list_companies
GET /api/planner/finance/stores        → FinanceC1Client.list_stores
# ... 等
```

**为什么要代理**：前端不应该直接调 finance API（鉴权 + 跨域 + key 管理）；走 costing 后端代理更安全。

### 2.6 后端 — 5 条消费测试（契约 §4.2）

新建 `backend/tests/test_finance_c1_client.py`，实现 §4.2 的 C1~C5 5 条：

```python
def test_c1_companies_dict():
    """拉取 companies 后能正确 build subject_id → legal_name dict"""

def test_c2_stores_company_id_resolves():
    """拉取 stores 后 store.company_id 都能在 companies 里命中"""

def test_c3_fixed_costs_aggregated():
    """fixed-costs 按 cost_category 聚合得到 11 项"""

def test_c4_invalid_api_key_graceful():
    """X-Costing-Api-Key 错误时优雅降级"""

def test_c5_finance_down_uses_cache():
    """finance 服务挂时用本地缓存"""
```

### 2.7 前端 — Admin 只读展示页

新建 `frontend/src/pages/costing/admin/FinanceMasterDataPage.tsx`：

- 顶部 Tabs: 公司主体 / 店铺 / 员工 / 固定开支
- 每个 Tab 一个表格，列按契约 §3.1~§3.4 字段（核心字段即可，metadata 不展示）
- 数据源：调 `/api/planner/finance/companies` 等
- 顶部加 1 个 Badge：`数据来源: finance-analyzer / cache (5 min ago) / mock (dev)`
- 加路由 `/costing/admin/finance-master`

### 2.8 前端 — service + types

- 新建 `frontend/src/services/financeC1.ts`（5 个 fetcher）
- 新建 `frontend/src/types/financeC1.ts`（4 个 DTO 类型）

### 2.9 不在 scope 内（不要做）

- ❌ 不写 cost_center_master 主表的 CRUD（U2 后续任务）
- ❌ 不集成到 BOM / 实时核价 / Insights 看板（v1.5 后续）
- ❌ 不做 webhook 监听（v2）
- ❌ 不动现有 Hub / Insights / BOM 相关代码

---

## 3. 关键技术决策

### 3.1 同步 vs 异步

看 finance-analyzer **现有 router 风格**（看 `backend/app/api/routes/` 里 def 还是 async def）。如果 finance 是 sync，我们用 sync httpx；如果 async，用 async httpx。**保持双方风格一致便于未来联调 debug。**

不确定时默认用 sync（更简单）。

### 3.2 缓存实现

用 `cachetools.TTLCache`（轻量，无外部依赖）。如果 ai-costing-system 已用 Redis，改用 Redis（看 `backend/src/planner/cache/`）。

### 3.3 失败降级语义

- 网络错误 / 5xx → 用 cache（如有）+ log warning + 在 response 加 `_data_source: "cache"`
- 401 / 403 → 抛异常（不降级，配置错误必须修）
- 400 → 抛异常（程序 bug 必须修）

### 3.4 前端"数据来源" Badge 颜色

- 🟢 `finance-analyzer`：实时拉取成功
- 🟡 `cache (Xm ago)`：finance 挂了用缓存
- 🔵 `mock (dev)`：开发环境 mock 数据
- 🔴 `error`：连缓存都没有

---

## 4. 完成标准

```
[ ] B1 finance_c1_client.py 5 个方法实现完毕
[ ] B2 mock 数据按契约 §3 example response 1:1 复制（至少 7 公司 / 4 店铺 / 3 员工 / 11 固开 / 6 工资）
[ ] B3 §4.2 的 5 条 pytest 全过
[ ] B4 5 个 proxy endpoint 在 /api/planner/finance/* 可用
[ ] B5 切换 FINANCE_C1_USE_MOCK=true/false 不报错（false 时走真 HTTP，可指向 mock server 或 finance dev env）
[ ] F1 FinanceMasterDataPage.tsx 4 个 Tab 都能显示数据
[ ] F2 顶部"数据来源" Badge 正确反映 mock / cache / live 状态
[ ] F3 路由 /costing/admin/finance-master 可访问
[ ] F4 没碰 BOM / Hub / Insights 任何代码（git diff 验证）
```

---

## 5. 验收命令（自主选 1~3 条）

```bash
# 选项 A：全功能验证
cd /home/admin/ai-costing-system
pytest backend/tests/test_finance_c1_client.py -v

# 选项 B：前端构建
cd frontend && npm run build

# 选项 C：Mock 数据完整性
python -c "from backend.tests.mocks.finance_c1_mock import MOCK_COMPANIES, MOCK_STORES, MOCK_EMPLOYEES, MOCK_FIXED_COSTS, MOCK_PAYROLL; assert len(MOCK_COMPANIES) >= 7; assert len(MOCK_STORES) >= 4; assert len(MOCK_FIXED_COSTS) >= 11; print('mock data OK')"
```

---

## 6. 收工归集 3 件

1. **commit 1 次**（标题 `feat(finance-c1): 实施 C1 client + mock + admin 只读 UI`）
2. **更新 task_log.md** 加 1 行
3. **更新 system_capability_inventory.md §13.1 U2 进度**：从🟢部分启动 → 🟢 costing 侧 client 完成（等 finance 侧实施）

---

## 7. 唯一回 Hub 的 3 种情况

1. **scope 不够**：契约某字段无法在 mock / 现有体系实现
2. **架构冲突**：现有 ai-costing-system 已有 finance integration（grep 一下，避免重复）
3. **完全卡死**：超过 30 分钟无进展

其他全部自主决策。

---

## 8. 元信息

| 项 | 值 |
|---|---|
| 创建日期 | 2026-05-10 07:55 北京时间 |
| 关联契约 | `DOC/costing/blueprints/finance_to_costing_c1_contract_v1.md` v1.0 |
| 配套 finance 侧任务 | `DOC/agents/briefings/finance_c1_apis_implementation.md` |
| 期望完工时间 | 后台跑 3~6 小时 |
