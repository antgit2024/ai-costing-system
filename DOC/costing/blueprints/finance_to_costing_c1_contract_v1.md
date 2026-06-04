# finance → costing C1 契约规格书 v1.0

> **本文档作用**：让 finance-analyzer 团队/Agent 拿到此文档即可实施，不需要回看 costing 侧任何聊天/历史。
> **产权方**：本契约 jointly owned by ai-costing-system 团队 + finance-analyzer 团队。修改任何一条都需双方书面同意（见 §5 C3 SLA）。
> **创建日期**：2026-05-10 北京时间
> **关联文档**：
> - `DOC/costing/blueprints/cost_rate_hub_design_v1.md` v1.3 §0.2 4 概念正交
> - `DOC/costing/blueprints/finance_analyzer_integration_v1.md` v1.1（架构层，待校准为 v1.2）
> - `DOC/costing/handovers/system_capability_inventory.md` §13.1 U2

---

## 0. 30 秒摘要（finance 老板看这段就够了）

ai-costing-system 要做"店铺利润分析"，需要 finance 提供 5 类只读数据：法人主体 / 店铺 / 员工 / 固定开支 / 工资单。finance 这边主数据已经有了（审计确认），**只需要把它们包装成 5 个标准 GET API 暴露给 costing 即可**。

- **finance 工作量**：3~5 人天（or 1 个 Agent 后台跑 4~6 小时）
- **costing 工作量**：C1 拉取 service 1~2 人天（与 finance 并行）
- **双方并行 → 5 天内端到端跑通**

---

## 1. 核心决策（已拍板，不要再讨论）

### 1.1 canonical subject ID = `master_companies.id`

| 决策项 | 拍板 | 时间 / 拍板人 |
|---|---|---|
| 哪个表是 costing 对接的"主体唯一标识" | **`master_companies.id`**（业务主数据，字段完整）| 2026-05-10 07:35 用户 |
| `companies` 表怎么办 | finance 内部继续保留用于登录/权限；与 master_companies 之间维护 1:N 或 1:1 映射（finance 自己定）| 同上 |
| costing 看到的"公司"概念是 | **`master_companies` 行**（不是 `companies` 行）| 同上 |

### 1.2 双轨主体处理建议（给 finance 内部参考）

finance 现状：`companies` (Company, 登录权限) vs `master_companies` (MasterCompany, 主数据)。两轨长期并存有 3 种处理方式，**任选其一**（不影响本契约）：

- **方案 A（推荐）**：保留双轨，在 `companies` 表加 `master_company_id` 外键引 master_companies；登录后把 `master_company_id` 注入 session
- **方案 B**：合并到 master_companies，company 表逐步废弃（工作量大但终极方案）
- **方案 C**：长期双轨，只在 C1 API 层面以 master_companies 为准（最小改动）

**costing 不关心你选哪种**，本契约只认 `master_companies.id`。

### 1.3 4 个组织概念正交映射（与 cost_rate_hub_design_v1.md v1.3 §0.2 对齐）

| 概念 | finance 提供方 | costing 消费方 |
|---|---|---|
| `legal_entity_id`（法人/纳税主体）| `master_companies.id` | costing 的 `cost_center_master.legal_entity_id` 外键 |
| `purchase_entity_id`（采购法人）| 同 `master_companies.id`（同一张表，按 `taxpayer_type` 区分一般/小规模）| `materials.purchase_entity_id`（v1 字符串占位 → C1 通后 map 到 UUID）|
| `production_unit_id`（生产单元）| ❌ finance 不管 | costing 自己维护（v1 仅 1 个默认值）|
| `cost_center_id`（费用中心/班组）| ❌ finance 不管 | costing 自己维护（基于 `taxonomy.team`）|

---

## 2. finance 侧实施清单（你要做的事）

### 2.1 数据层补字段（如有缺失）

对照下表 check `master_companies` 是否含以下字段；缺哪个补哪个：

| 字段名 | 类型 | 必需 | 说明 |
|---|---|---|---|
| `id` | UUID / String(36) | ✅ | canonical subject ID |
| `legal_name` | String | ✅ | 主体公司全称 |
| `tax_payer_type` | Enum | ✅ | `general` / `small_scale` |
| `unified_social_credit_code` | String(18) | 推荐 | 统一社会信用代码 |
| `entity_role` | Enum | ✅ | `factory` / `shop` / `holding` / `mixed` — 标识主体角色（让 costing 知道这是工厂主体还是店铺主体） |
| `parent_company_id` | UUID | 可选 | 母公司关联（如果有） |
| `is_active` | Boolean | ✅ | 是否启用 |
| `effective_from` | Date | 可选 | 启用日期（用于历史数据归档） |
| `effective_to` | Date | 可选 | 注销日期 |
| `created_at` / `updated_at` | DateTime | ✅ | 标准时间戳 |

> **如果 `entity_role` 字段没有**：这是新增字段。请在 master_companies 加这个字段并初始化数据（4 个店铺主体 = 'shop' / 3 个工厂主体 = 'factory'）。

### 2.2 暴露 5 个标准 GET API（**详细规格见 §3**）

```
GET /api/v1/c1/companies            (法人主体清单)
GET /api/v1/c1/stores               (店铺清单)
GET /api/v1/c1/employees            (员工花名册)
GET /api/v1/c1/fixed-costs          (固定开支台账)
GET /api/v1/c1/payroll              (工资单按月)
```

**为什么用 `/api/v1/c1/` 前缀**：
- 与现有 `/api/v1/companies` 区分（现有是 finance 内部用，可能含敏感字段如登录账号）
- `c1` = "Contract 1"，明确这是给 costing 跨域消费的"对外只读视图"
- 未来 v2 加 webhook 时用 `/api/v1/c2/...` 不冲突

### 2.3 加鉴权

- 方式：HTTP Header `X-Costing-Api-Key: <secret>`
- key 由 finance 团队生成 1 个长 token（≥ 32 字节随机），通过安全渠道发给 costing 团队
- key 配置在 finance 的 env 里（如 `COSTING_API_KEY`）
- 请求方携带这个 key 的请求才放行；不携带或错误 → HTTP 401

### 2.4 加版本头

- 所有 C1 API response 加 Header：`X-Api-Version: 1.0`
- 所有 C1 API response body 顶层加字段：`"_api_version": "1.0"`
- 向后不兼容修改时升 v2.0 + 保留 v1.0 至少 30 天

### 2.5 加 C3 双向 SLA 文档

在 finance-analyzer 仓库 `DOC/contracts/` 目录加一份 `c1_change_sla.md`，内容见 §5。

### 2.6 finance **不需要做**的事

- ❌ 写回（costing 算的成本回 finance 入账）— 这是 v2 计划
- ❌ Webhook 主动推送 — 这是 v2 计划，v1 用 polling
- ❌ 三视图（Tax/Mgmt/Group）— 这是 finance 内部 BI 任务
- ❌ 主数据合并双轨 — 见 §1.2，可以延后
- ❌ 任何 UI 改动 — 本契约只涉及 API

---

## 3. 5 个 GET API 详细规格

### 3.1 `GET /api/v1/c1/companies` — 法人主体清单

**用途**：costing 用此获取所有法人主体，建立 cost_center → legal_entity 映射。

**Query Parameters**：
```
?entity_role=factory|shop|holding|mixed     (可选，过滤主体角色)
?is_active=true|false                       (可选，默认 true)
?effective_at=2026-05-10                    (可选，按生效日期过滤；默认今天)
?page=1&page_size=100                       (可选，分页；默认 page_size=100，max=500)
```

**Response 200**：
```json
{
  "_api_version": "1.0",
  "data": [
    {
      "id": "uuid-string-36",
      "legal_name": "杭州某某家居饰品有限公司",
      "tax_payer_type": "general",
      "unified_social_credit_code": "91330000XXXXXXXXXX",
      "entity_role": "factory",
      "parent_company_id": null,
      "is_active": true,
      "effective_from": "2024-01-01",
      "effective_to": null,
      "metadata": {
        "city": "杭州",
        "address": "...",
        "legal_representative": "..."
      }
    }
  ],
  "pagination": {
    "page": 1,
    "page_size": 100,
    "total": 7,
    "total_pages": 1
  }
}
```

**Error Responses**：
- 401 `{"error": "MISSING_OR_INVALID_API_KEY"}`
- 400 `{"error": "INVALID_QUERY", "detail": "entity_role 必须是 factory/shop/holding/mixed 之一"}`
- 500 `{"error": "INTERNAL", "trace_id": "..."}`

---

### 3.2 `GET /api/v1/c1/stores` — 店铺清单

**用途**：costing 用此获取店铺数据，建立 4 个店铺与 master_companies 的关系。

**Query Parameters**：
```
?company_id=<uuid>                          (可选，过滤某主体下的店铺)
?platform=tmall|taobao|jd|douyin|...        (可选，按平台过滤)
?is_active=true|false                       (可选，默认 true)
?page=1&page_size=100
```

**Response 200**：
```json
{
  "_api_version": "1.0",
  "data": [
    {
      "id": "uuid-string-36",
      "store_name": "某某家居旗舰店",
      "company_id": "uuid-string-36",          // 引 master_companies.id
      "platform": "tmall",
      "platform_shop_id": "12345678",
      "manager_name": "张三",
      "main_category": "家居饰品",             // 自由文本，建议规范化为 "家居饰品" / "家居布艺" / "混合"
      "monthly_revenue_avg": 250000.00,        // 月均营业额（元，可选）
      "is_active": true,
      "metadata": {}
    }
  ],
  "pagination": {...}
}
```

---

### 3.3 `GET /api/v1/c1/employees` — 员工花名册

**用途**：costing 用此获取员工归属（哪家公司发工资 / 实际服务哪个班组）。**v1 暂不强消费**，留给 Stage 3 做精细人工成本时用。

**Query Parameters**：
```
?contract_company_id=<uuid>                  (可选)
?is_active=true|false                        (可选，默认 true)
?effective_at=2026-05-10                     (可选)
?page=1&page_size=100
```

**Response 200**：
```json
{
  "_api_version": "1.0",
  "data": [
    {
      "id": "uuid-string-36",
      "employee_no": "E0001",
      "name": "张三",
      "contract_company_id": "uuid-string-36",  // 工资发放主体（引 master_companies.id）
      "department": "缝纫一组",                  // 文本，对应 costing 的 cost_center 名称
      "position": "缝纫工",
      "hire_date": "2023-03-15",
      "leave_date": null,
      "is_active": true,
      "metadata": {
        "id_card_masked": "330***********1234",
        "phone_masked": "138****5678"
      }
    }
  ],
  "pagination": {...}
}
```

> **隐私字段**（身份证 / 电话 / 银行卡 / 真实工资数）：身份证/电话脱敏返回；工资真实数走 §3.5 payroll 接口（要更高权限）。

---

### 3.4 `GET /api/v1/c1/fixed-costs` — 固定开支台账

**用途**：costing 用此获取固定开支金额（房租 / 水电 / 管理工资等），按 cost_center_master 表 2 的分摊规则摊到 6 班组 / 4 店铺。

**Query Parameters**：
```
?company_id=<uuid>                           (可选，过滤付款主体)
?period_year=2026&period_month=4             (可选，过滤期间；默认最近 1 个月)
?cost_category=rent|utility|salary|...       (可选，按费用类别过滤)
?page=1&page_size=100
```

**Response 200**：
```json
{
  "_api_version": "1.0",
  "data": [
    {
      "id": "uuid-string-36",
      "company_id": "uuid-string-36",          // 实际付款主体
      "period_year": 2026,
      "period_month": 4,
      "cost_category": "rent",                 // 标准枚举：见 §3.4.1
      "cost_subcategory": "factory_workshop",  // 子类（房租按区域分）
      "amount": 35000.00,                      // 含税金额，元
      "tax_included": true,
      "tax_rate": 0.06,
      "description": "厂区 3 楼车间房租",
      "approver": "李四",
      "metadata": {}
    }
  ],
  "pagination": {...}
}
```

#### 3.4.1 `cost_category` 标准枚举（finance 必须按此分类）

```
rent              房租
utility           水电
salary_admin      管理人员工资
insurance_admin   管理人员五险一金
office_supplies   办公耗材
depreciation      设备折旧
logistics         物流（厂出）
platform_fee      平台佣金/推广（仅店铺）
after_sales       售后退换运费（仅店铺）
others            其他
```

> 如果 finance 现有 `fixed_monthly_cost.cost_category` 字段值与此不一致，请在 API 层做 mapping（不强制改底层数据）。

---

### 3.5 `GET /api/v1/c1/payroll` — 工资单按月（高敏感）

**用途**：costing 用此算"班组实际工时单价"（替代 cost_center_master 表 1 的手填默认值）。**v1 仅做 Stage 2 接入，v1.5 才生效**。

**Query Parameters**：
```
?company_id=<uuid>                           (必需)
?period_year=2026&period_month=4             (必需)
?aggregation=by_employee|by_department       (可选，默认 by_department 聚合)
?page=1&page_size=100
```

**Response 200**（by_department 聚合）：
```json
{
  "_api_version": "1.0",
  "data": [
    {
      "company_id": "uuid-string-36",
      "department": "缝纫一组",
      "period_year": 2026,
      "period_month": 4,
      "headcount": 8,
      "total_gross_salary": 45000.00,           // 应发工资总额
      "total_employer_insurance": 9000.00,      // 公司承担五险一金
      "total_labor_cost": 54000.00,             // 总人工成本
      "avg_workdays": 21.5,
      "metadata": {}
    }
  ],
  "pagination": {...}
}
```

> **更高鉴权**：本 endpoint 在 §2.3 的 X-Costing-Api-Key 之外，必须额外加 Header `X-Payroll-Authorized: true`，且 finance 侧 log 完整审计（IP / 时间 / 拉取的 company_id / period）。

---

## 4. C2 自动化测试用例

### 4.1 finance 侧自测（5 条 — finance Agent 提交前必跑）

```
[ ] T1 GET /api/v1/c1/companies 返回 200 + entity_role 字段都在白名单内
[ ] T2 GET /api/v1/c1/stores?company_id=<某 master_companies.id> 返回该公司下所有店铺
[ ] T3 GET /api/v1/c1/employees 身份证字段已脱敏（含 ***）
[ ] T4 GET /api/v1/c1/fixed-costs?period_year=2026&period_month=4 返回当月数据，cost_category 都在 §3.4.1 枚举内
[ ] T5 不带 X-Costing-Api-Key 的请求返回 401
```

### 4.2 costing 侧消费测试（5 条 — costing Agent 写完 C1 service 必跑）

```
[ ] C1 拉取 companies 后能正确 build subject_id → legal_name dict
[ ] C2 拉取 stores 后 store.company_id 都能在 companies 里命中（无孤立外键）
[ ] C3 拉取 fixed-costs 按 cost_category 聚合得到 11 项分类总和
[ ] C4 X-Costing-Api-Key 错误时优雅降级（不崩溃，缓存上一次成功结果）
[ ] C5 finance 服务挂时（连接超时）触发 fallback：用本地缓存的最近 1 次数据 + UI 提示"数据来源：cache (5 分钟前)"
```

### 4.3 双向连通性测试（3 条 — 双方一起跑）

```
[ ] E2E1 finance master_companies 加 1 个新公司 → costing 5 分钟内能拉到（缓存 TTL）
[ ] E2E2 finance 把某公司 is_active 改 false → costing 默认查询不返回（除非显式 ?is_active=false）
[ ] E2E3 finance 升级到 v2.0（含 break change） → costing 仍能用 v1.0（30 天缓冲期）
```

---

## 5. C3 双向变更 SLA

### 5.1 finance 改 C1 API 字段 → costing 影响通报机制

| 修改类型 | 通报方式 | 通报时长 | 是否需要 costing 同意 |
|---|---|---|---|
| 加新字段（向后兼容）| 群消息 + 文档更新 | T+0 | ❌ 自动通过 |
| 改字段类型/语义 | issue + 评估会议 | T-7 天 | ✅ 必须 |
| 删除字段 | issue + 双方书面 + v2 升级 | T-30 天 | ✅ 必须 |
| 改路由路径 | 加新路由 + deprecation header + v2 升级 | T-30 天 | ✅ 必须（旧路由保留 30 天）|

### 5.2 costing 增字段需求 → finance 评估流程

1. costing 在 finance 仓库 `DOC/contracts/c1_pending_requests.md` 提需求（含字段名 / 类型 / 用途 / 拉取频率）
2. finance 评估（≤ 3 工作日给反馈）：可立即加 / 已有可直接暴露 / 需要业务侧准备 / 拒绝（含理由）
3. 双方评审通过后 finance 加字段 + 升级 API 文档 + 通知 costing

### 5.3 字段废弃流程

任何字段废弃必须：
1. finance 在 response 加 deprecation 标记（字段名加 `_deprecated_<sunset_date>` 后缀，或 response Header `Deprecation: <date>`）
2. 至少 30 天后才能真正下线
3. 期间 costing 必须迁移到替代字段

---

## 6. 鉴权 / 限流 / 缓存 / 错误码

### 6.1 鉴权

- Header `X-Costing-Api-Key: <secret>`
- payroll endpoint 额外 `X-Payroll-Authorized: true`
- key rotation：每 6 个月轮换 1 次，提前 30 天通知

### 6.2 限流

- 单个 API key：100 QPS
- 超限返回 429 `Retry-After: <seconds>`

### 6.3 缓存（finance 侧建议）

- companies / stores：缓存 5 分钟（TTL=300s）
- employees：缓存 1 小时（TTL=3600s）
- fixed-costs：缓存 1 小时
- payroll：不缓存（每次实时查）
- 用 `Cache-Control: max-age=300` Header 标识

### 6.4 错误码标准（按 HTTP 标准 + 自定义 code）

```
400 INVALID_QUERY              查询参数错误
401 MISSING_OR_INVALID_API_KEY 鉴权失败
403 PAYROLL_NOT_AUTHORIZED     payroll 需额外鉴权头
404 RESOURCE_NOT_FOUND         资源不存在（如 ?company_id=不存在的 ID）
429 RATE_LIMIT_EXCEEDED        超频
500 INTERNAL                   内部错误（含 trace_id）
503 UPSTREAM_DEPENDENCY_DOWN   依赖服务挂（如数据库）
```

---

## 7. 后续扩展（v2 / v3）

| 版本 | 范围 | 何时启动 |
|---|---|---|
| v1.0 | 本契约（5 个 GET API + 鉴权 + SLA）| **现在** |
| v1.5 | costing 真正消费 payroll 算工时单价 | 本契约稳定运行 1 个月后 |
| v2.0 | finance 主动 webhook 推 costing（数据变更通知）| 季度规划 |
| v2.5 | costing 写回 finance（成本数据回入账）| 半年规划 |
| v3.0 | 三视图（FI/CO/合并）| 看 finance 团队 BI 路线 |

---

## 8. 验收标准

### 8.1 finance 侧 ✅（5 条）

```
[ ] F1 5 个 GET API 全部 deploy 到 finance 测试环境，curl 返回 200 + 正确 schema
[ ] F2 §4.1 的 5 条自测全过
[ ] F3 master_companies 含 entity_role 字段（已初始化好 4 店铺 + 3 工厂的角色）
[ ] F4 X-Costing-Api-Key 已生成并发给 costing 团队（通过安全渠道，不在 git 里）
[ ] F5 DOC/contracts/c1_change_sla.md 已落地
```

### 8.2 costing 侧 ✅（5 条）

```
[ ] C1 backend/src/planner/services/finance_c1_client.py 已写完（拉 + 缓存 + 降级）
[ ] C2 §4.2 的 5 条消费测试全过
[ ] C3 cost_center_master.legal_entity_id 字段类型可接受 finance 返回的 master_companies.id
[ ] C4 materials.purchase_entity_id 可从字符串占位 map 到 finance UUID（写迁移脚本）
[ ] C5 UI 在 /costing/admin/cost-centers 可看到从 finance 拉来的公司列表（只读展示）
```

### 8.3 双方一起 ✅（3 条）

```
[ ] E1 §4.3 的 3 条 E2E 测试全过
[ ] E2 双方负责人签字本契约 v1.0
[ ] E3 双方仓库各 commit 1 次：finance 落 §2 实施 + costing 落 §C1 service
```

---

## 9. 工作量预估

| 角色 | 任务 | 人天 | AI Agent 时长（按 12x 速度估）|
|---|---|---|---|
| finance Agent | §2 全部实施（建 5 个 API + 字段补全 + 测试 + SLA 文档）| 3~5 天 | 6~10 小时 |
| costing Agent | C1 client service + 缓存 + 降级 + UI 接入 | 1~2 天 | 3~4 小时 |
| 双方测试 | §4 全部测试 + §8 验收 | 1 天 | 2~3 小时 |
| **总计（并行）** | | **5 天 wall clock** | 1~2 天 wall clock（双 Agent 并行）|

---

## 10. 元信息

| 项 | 值 |
|---|---|
| 文档版本 | v1.0 |
| 创建日期 | 2026-05-10 07:40 北京时间 |
| 创建人 | Hub Agent（ai-costing-system 侧）|
| 拍板人 | 用户（2026-05-10 07:35 选 master_companies as canonical）|
| 关联 U# | system_capability_inventory.md §13.1 U2（finance_analyzer_integration v1.1→v1.2 校准的实施配套件）|
| 修改任何条款 | 需 finance + costing 双方书面同意 |
| 文档位置（finance 侧拷贝）| 建议 finance 仓库 `DOC/contracts/c1_inbound_costing.md` 同步一份 |

---

## 11. 一句话给 finance 团队 / Agent

按 §2 的实施清单 + §3 的 5 个 API 详细规格做完，跑通 §4.1 的 5 条自测，把 X-Costing-Api-Key 通过安全渠道给 costing，就完成了你这边的工作。预估 3~5 人天。任何不清楚的字段含义 / 边界场景，参考 §3 各 endpoint 的 example response，或在 finance 仓库 `DOC/contracts/c1_pending_requests.md` 提问，48 小时内会给答复。
