# finance C1 APIs 实施 — 跨仓库大任务单（2026-05-10）

> 派单类型：跨仓库后端大任务（去 `/home/admin/projects/finance-analyzer` 实施 5 个 GET API）
> 预估工作量：4~10 小时（AI Agent）
> 承接 Agent 角色：`@Finance Backend Agent`（完整自主权，但跨仓库强约束）
> 唯一硬约束：**绝对不准 push 到 origin、不准动现有 dirty 文件、不准 force / amend / rebase / 改 git config**

---

## 0. 30 秒摘要

ai-costing-system 已经把契约规格书写好了：`/home/admin/ai-costing-system/DOC/costing/blueprints/finance_to_costing_c1_contract_v1.md`。你只需要按它的 §2 §3 §4.1 §6 把 5 个 GET API 在 finance-analyzer 仓库实现 + 跑 5 条自测，commit 在新 branch 但**不 push**，告诉我 branch 名和 commit hash 即可。

---

## 1. 必读 3 步（开工前必做）

```
[ ] 1. 完整通读 /home/admin/ai-costing-system/DOC/costing/blueprints/finance_to_costing_c1_contract_v1.md（约 460 行）
[ ] 2. cd /home/admin/projects/finance-analyzer && ls backend/app/models/ backend/app/api/routes/ 摸清现状
[ ] 3. 读 backend/app/models/ 下：company.py / shop.py / employee.py / fixed_monthly_cost.py / payroll*.py（如有）确认 master_companies 表是否含 entity_role 字段
```

---

## 2. 任务范围（只做这些）

### 2.1 数据层（如 entity_role 字段缺失）

- 在 `backend/app/models/master_company.py`（或对应文件）的 `MasterCompany` ORM 加：
  ```python
  entity_role = Column(String(20), nullable=False, server_default="mixed")  # factory/shop/holding/mixed
  ```
- 加对应 Alembic migration（按 finance-analyzer 现有 migration 风格）
- 加初始化数据脚本（4 个店铺主体 → 'shop'，3 个工厂主体 → 'factory'）：
  - 如果数据已有，写一个 SQL update 或 management command
  - 如果数据没有，跳过（让 finance 团队自己填）

### 2.2 API 层（新建 5 个 router）

新建 `backend/app/api/routes/c1_costing.py`，含 5 个 endpoint，对应契约 §3.1~§3.5：

```python
# 全部带前缀 /api/v1/c1/
GET /api/v1/c1/companies
GET /api/v1/c1/stores
GET /api/v1/c1/employees
GET /api/v1/c1/fixed-costs
GET /api/v1/c1/payroll
```

- Response schema **严格按契约 §3.1~§3.5 的 example response**（字段名 / 类型 / 嵌套 1:1 对照）
- 含字段：`_api_version`: "1.0" + `data` + `pagination`
- payroll 默认 `aggregation=by_department` 聚合（不返回个人明细）

### 2.3 鉴权层

- 新建 `backend/app/api/deps_costing.py`（不要混进现有 deps.py，避免污染别的 endpoint）
- 实现 `verify_costing_api_key`：从 Header `X-Costing-Api-Key` 拿 key，比对 env `COSTING_API_KEY`
- payroll endpoint 额外校验 Header `X-Payroll-Authorized: true`

### 2.4 Response Header

- 加 middleware 或在每个 endpoint 加 `X-Api-Version: 1.0` Header
- 加 `Cache-Control: max-age=300`（companies/stores/fixed-costs）
- payroll 用 `Cache-Control: no-store`

### 2.5 配置

- 在 `.env.example` 加：
  ```
  COSTING_API_KEY=please-rotate-this-32-byte-secret
  ```
- 在 README 或 docs 里说明：生产环境必须替换为真随机 token

### 2.6 自测脚本

新建 `backend/tests/c1/test_costing_contract.py`（或 finance-analyzer 现有 tests 目录风格），实现契约 §4.1 的 5 条：

```python
def test_t1_companies_returns_valid_entity_roles():
    response = client.get("/api/v1/c1/companies", headers={"X-Costing-Api-Key": "test-key"})
    assert response.status_code == 200
    for company in response.json()["data"]:
        assert company["entity_role"] in ["factory", "shop", "holding", "mixed"]

def test_t2_stores_filter_by_company():
    # ...

def test_t3_employees_id_card_masked():
    # ...

def test_t4_fixed_costs_categories_in_whitelist():
    # ...

def test_t5_unauthorized_returns_401():
    response = client.get("/api/v1/c1/companies")
    assert response.status_code == 401
```

### 2.7 SLA 文档

新建 `DOC/contracts/c1_inbound_costing.md`（或 finance-analyzer 现有文档目录），把契约 §5 C3 SLA 全文搬过去。

### 2.8 不在 scope 内（不要做）

- ❌ 不做 webhook（v2）
- ❌ 不做写回（v2）
- ❌ 不动现有任何 endpoint（不要改 /api/v1/companies 等）
- ❌ 不动现有 dirty 文件（10 个 modified 文件是别人 in-progress 工作）
- ❌ 不动 frontend
- ❌ 不动 Docker / CI 配置

---

## 3. 跨仓库 Git 安全协议（强制）

### 3.1 开工前

```bash
cd /home/admin/projects/finance-analyzer

# 1. 保护现有 dirty 工作
git stash push -u -m "WIP before C1 implementation by Hub Agent (2026-05-10)"

# 2. 确认 stash 成功
git stash list  # 应该看到 stash@{0}: ... C1 implementation ...

# 3. 切到 main 最新
git fetch origin
git checkout main
git pull --ff-only origin main

# 4. 新建 feature branch
git checkout -b feat/c1-costing-contract-v1
```

### 3.2 开工中

- 所有改动只在 `feat/c1-costing-contract-v1` branch 上
- 每完成 1 个子任务（§2.1 / §2.2 / §2.3 / ...）做 1 个 commit，commit message 用：
  ```
  feat(c1): <什么>
  ```
- 用 HEREDOC 格式写 commit message

### 3.3 收工

```bash
# 1. 自检 §4.1 5 条全过
pytest backend/tests/c1/ -v

# 2. 确认 branch 干净
git status  # 应该 nothing to commit

# 3. 切回原工作
git checkout main
git stash pop  # 恢复用户原 dirty 文件

# 4. 验证 stash 已 pop
git stash list  # 应该为空
git status  # 应该看到原 10 个 modified 文件回来了

# 5. 不 push
echo "❌ 绝对不准: git push origin feat/c1-costing-contract-v1"
echo "✅ 等用户/finance 团队 review branch 后自己决定 push"
```

### 3.4 报告内容

完工后给我以下信息（用 Markdown 列表格式）：

```
- branch 名: feat/c1-costing-contract-v1
- commits: <commit hash 列表>
- 文件改动: <new file 列表>
- §4.1 5 条测试结果: ✅ x 条 / ❌ x 条（如有失败说明原因）
- entity_role 字段是否新增: 是 / 否（如否说明已存在）
- master_companies 数据是否初始化: 是 / 否（如否说明留给 finance 团队填）
- 遇到的 blocker: 列表（如无写"无"）
- COSTING_API_KEY 在 .env.example 的位置: 行号
```

---

## 4. 完成标准（finance 侧 § 8.1 5 条 + 跨仓库 § 3 安全）

```
[ ] F1 5 个 GET API 在 finance-analyzer dev 环境 curl 返回 200 + schema 正确
[ ] F2 §4.1 的 5 条 pytest 全过
[ ] F3 master_companies 含 entity_role 字段
[ ] F4 .env.example 含 COSTING_API_KEY
[ ] F5 DOC/contracts/c1_inbound_costing.md 已落地
[ ] G1 branch feat/c1-costing-contract-v1 已建 + commit 完毕
[ ] G2 没有 push 到 origin
[ ] G3 用户原 10 个 dirty 文件已 stash pop 恢复
[ ] G4 没动任何现有 endpoint
[ ] G5 git status (在 main) 与开工前一致
```

---

## 5. 唯一回 Hub 的 3 种情况（其他全部自主决策）

1. **scope 不够**：契约 §3 某个字段在 finance 现有数据里完全找不到（不只是字段名不同，是概念都没有）
2. **架构冲突**：finance 现有 deps.py 鉴权机制与契约 §6.1 X-Costing-Api-Key 严重冲突，无法兼容
3. **完全卡死**：超过 30 分钟无进展（如 ORM 迁移失败、依赖缺失）

其他一切（字段名映射差异、表名不一样、tests 写哪种风格、用 Pydantic 还是 marshmallow、fixture 怎么写）都自主决定。

---

## 6. 风险规避（5 条）

1. ⚠️ **dirty 文件保护**：`git stash` 之前如果 stash 失败（如有 untracked 必须 -u），先用 `git stash push -u -m "..."`
2. ⚠️ **branch 命名冲突**：如 `feat/c1-costing-contract-v1` 已存在，加日期后缀 `-20260510`
3. ⚠️ **migration 冲突**：finance-analyzer 有自己的 alembic head，加 migration 时要 `alembic revision --autogenerate -m "c1: add entity_role to master_companies"` 不要手写编号
4. ⚠️ **测试隔离**：不要在 prod / staging DB 跑测试。用 SQLite in-memory 或 finance-analyzer 现有 test fixture
5. ⚠️ **不要碰 .git config**：不修改 user.name / user.email / remote.url

---

## 7. 元信息

| 项 | 值 |
|---|---|
| 创建日期 | 2026-05-10 07:50 北京时间 |
| 创建人 | Hub Agent (ai-costing-system) |
| 关联契约 | `DOC/costing/blueprints/finance_to_costing_c1_contract_v1.md` v1.0 |
| 关联 task_log | 2026-05-10 07:40 entry |
| 期望承接 | Finance Backend Agent (任意能写 Python/FastAPI 的 generalPurpose subagent) |
| 期望完工时间 | 后台跑 4~10 小时 |
