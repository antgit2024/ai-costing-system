# Cost Rate Hub MVP — 全栈大任务单（v1.3 落地）

> **派单类型**：全栈大任务（后端 + 前端 + 测试 + 接入），按 `task_distribution_standard.md` v2.0 §3.1 模板
> **派单日期**：2026-05-09 18:05 北京时间
> **派单人**：Hub Agent
> **承接 Agent 角色**：`@Fullstack Agent`（任意全栈 Agent，scope 内拥有**完整自主权限**）
> **本任务一次性合并 system_capability_inventory.md §13.1 的 U5 + U6 + U7 三项**

---

## 0. 30 秒摘要（最重要的事写最前）

把 Cost Rate Hub v1.3（成本参数中枢）从"设计文档"落到"用户能用"：

1. **后端**：扩展现有 `long_tail_cogs_rate_strategies` 表为 `cost_rate_master`（Migration 0038，加 11 字段 + 表改名 + 兼容视图），扩展 `_resolve_overhead_rate` 走新 4 层链
2. **前端**：现有 `LongTailCogsRatePage.tsx` 加 1 个 Tab「制造费率治理（overhead_rate）」
3. **接入**：KB8 模型走通端到端 — Hub 配置 `model='KB8'` overhead=0.25 → KB8 实时核价反映新值 → 发货台账"成本拆分"用上新值

**用户验收**：你（用户）登录系统，在 `/costing/admin/cost-rate-hub` 配 KB8 的 overhead=0.25，KB8 实时核价从 23% 折算占比变成 20% 折算占比（0.25/(1+0.25)=20%），发货台账新发货行的"成本拆分"也反映此变化。

---

## 1. 任务范围（执行 Agent 在此 scope 内有**完整自主权限**）

### 1.1 后端（Backend scope）

| 文件 | 动作 | 关键变化 |
|---|---|---|
| `backend/migrations/versions/0038_cost_rate_master.py` | **新建** | 见 §3 SQL（已写好可直接抄） |
| `backend/src/planner/models.py` | **修改** | `LongTailCogsRateStrategy` ORM 加 11 字段 + 类改名 `CostRateMaster`（保留旧类名 alias）|
| `backend/src/planner/services/long_tail_strategy_service.py` | **修改** | 新增 `resolve_overhead_rate(db, *, model_id, category, cost_center_id) -> Decimal` |
| `backend/src/planner/services/bom_generation_service.py` | **修改** | `_resolve_overhead_rate` (line 2009-2047) 在第 1 步前插入 cost_rate_master 4 层 resolve；保留 metadata_json 兜底 |
| `backend/src/planner/routers/long_tail_strategies.py` | **修改** | list/create/patch 加 `rate_type` query/body 字段（默认 `cogs` 兼容旧调用）|
| `backend/src/planner/schemas/long_tail_strategies.py` | **修改** | Pydantic schema 加 11 字段 |
| `backend/tests/planner/test_cost_rate_hub.py` | **新建** | 见 §4 完成标准的测试场景 |

### 1.2 前端（Frontend scope）

| 文件 | 动作 | 关键变化 |
|---|---|---|
| `frontend/src/pages/costing/admin/LongTailCogsRatePage.tsx` | **修改** | 顶部加 Tabs：Tab1「长尾成本兜底（cogs）」（现有）+ Tab2「制造费率治理（overhead_rate）」（新）；Tab2 表单加 scope_type/scope_id 选择 |
| `frontend/src/services/longTailStrategies.ts`（如存在）| **修改** | 调用加 `rate_type` 参数 |
| `frontend/src/App.tsx` | **可选** | 新增路由 `/costing/admin/cost-rate-hub` 复用 `LongTailCogsRatePage`（带 default Tab=overhead_rate）— 也可不做，直接用旧路由切 Tab |

### 1.3 不在 scope 内（禁止改）

- ❌ `backend/src/planner/services/data_quality_service.py`（v1 不动可信度徽章接入，留 Stage 2）
- ❌ `frontend/src/pages/costing/{Profit,Shop,Sales,AfterSales}InsightsPage.tsx`（4 个看板加徽章是 U7 后续单独派单）
- ❌ `cost_center` 表（v1.3 §4.1 设计了，但 cost_center 维度 v1 数据可以全为空，先把 model/category/global 三层跑通即可；cost_center 表的新建可作为这个任务的可选项 — 由你自主决定要不要做）
- ❌ `backend/src/planner/services/data_quality_service.py` 的 `cost_quality` 维度扩展（Stage 2）

### 1.4 自主权范围明确

你**完全自主**：
- ✅ 中间步骤拆分（先写 migration / 先写 service / 先写前端，由你决定）
- ✅ 子 commit 数量（一次大 commit 或 3~5 个子 commit）
- ✅ 调用 subagent / Shell / Read / Grep / MCP 等工具（不需要请示）
- ✅ 任务单未明确的细节（如 Pydantic 字段命名风格、错误信息文案、Tab 顺序）按现有代码风格自主决定
- ✅ 在 scope 文件内自由读改（不需要逐个文件加 workset）

你**仅在 3 种情况必须立即回 Hub**：
1. 发现需要改 scope 外的文件 → 申请扩 workset
2. 发现 cost_rate_hub_design_v1.md v1.3 与现有代码有架构冲突 → 同步设计
3. 尝试 ≥ 3 种方案后仍无法推进 → 求助

---

## 2. 必读上下文（10 分钟内可掌握）

按 `system_capability_inventory.md §12.5` 的「3 步必读 + 按需软指引」：

### 2.1 必读 3 步

```
[ ] 1. DOC/agents/agent_rules.md（v2.0 重大修订 — §2 任务粒度区分 + §7 交接成本约束）
[ ] 2. DOC/costing/handovers/system_capability_inventory.md §12 + §13（事实清单 + 防忘表 U5/U6/U7）
[ ] 3. DOC/costing/blueprints/cost_rate_hub_design_v1.md v1.3（Hub 设计真相 — §-1 / §4.3 / §5 / §8）
```

### 2.2 按需扩读

- 想理解 23% 折算逻辑 → `state.md` grep "23%" + `price_calculation_guide.md` v2.1
- 想理解长尾兜底现有行为 → `known_issues.md` Issue 28 + `long_tail_strategy_service.py` 全文
- 想理解 KB8 模型现状 → `frontend/src/pages/costing/StandardModelsPage.tsx` 抽屉 + `ProductModelEditorDrawer.tsx`

### 2.3 关键代码定位（不需要再 grep）

| 关键点 | 路径 | 行号 | 说明 |
|---|---|---|---|
| 现有 `_resolve_overhead_rate` | `backend/src/planner/services/bom_generation_service.py` | 2009-2047 | 这里是 Hub 接入点，在第 1 步前插入新链 |
| 现有 0.30 兜底（真兜底）| `backend/src/planner/services/bom_generation_service.py` | 2047 | 改为 `cost_rate_master` global resolve 兜底；保留 0.30 作为最后一层 hard fallback |
| 0.30 出现的其他位置 | `backend/src/planner/services/bom_generation_service.py` | 1129, 1487 | bundle merge accumulator 默认值，**不要动**（与本任务无关）|
| 现有 long-tail Migration | `backend/migrations/versions/0035_long_tail_cogs_rate_strategy.py` | 全文 | 抄表结构作为 0038 的 baseline |
| 现有 long-tail router | `backend/src/planner/routers/long_tail_strategies.py` | 49-132 | 5 个 endpoint，加 rate_type 过滤即可 |
| 现有 long-tail UI | `frontend/src/pages/costing/admin/LongTailCogsRatePage.tsx` | 全文 | 用 Ant Design Tabs 包一层 |
| KB8 实时核价 API | `backend/src/planner/routers/product_models.py`（按需 grep `preview`）| - | KB8 页面"实时核价"按钮调用 |

---

## 3. 关键技术决策（已定，**不要再讨论**）

### 3.1 Migration 0038 SQL 骨架（按 v1.3 §4.3.2 直接抄）

```python
# backend/migrations/versions/0038_cost_rate_master.py
"""extend long_tail_cogs_rate_strategies to cost_rate_master (v1.3 Cost Rate Hub)

Revision ID: 0038_cost_rate_master
Revises: 0037_shipment_exception_queue_line_idx
Create Date: 2026-05-09
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0038_cost_rate_master"
down_revision = "0037_shipment_exception_queue_line_idx"

def upgrade():
    # 1. 加 11 个字段
    op.add_column("long_tail_cogs_rate_strategies", sa.Column("rate_type", sa.String(32), nullable=False, server_default="cogs"))
    op.add_column("long_tail_cogs_rate_strategies", sa.Column("scope_type", sa.String(32), nullable=False, server_default="category"))
    op.add_column("long_tail_cogs_rate_strategies", sa.Column("scope_id", sa.String(128), nullable=True))
    op.add_column("long_tail_cogs_rate_strategies", sa.Column("rate_basis", sa.String(32), nullable=False, server_default="pct_of_revenue"))
    op.add_column("long_tail_cogs_rate_strategies", sa.Column("source", sa.String(64), nullable=False, server_default="manual"))
    op.add_column("long_tail_cogs_rate_strategies", sa.Column("effective_from", sa.DateTime, nullable=True))
    op.add_column("long_tail_cogs_rate_strategies", sa.Column("effective_to", sa.DateTime, nullable=True))
    op.add_column("long_tail_cogs_rate_strategies", sa.Column("data_quality", sa.String(16), nullable=True))  # green/yellow/red
    op.add_column("long_tail_cogs_rate_strategies", sa.Column("cost_center_id", sa.Integer, nullable=True))  # 留位，v1 可全 NULL
    op.add_column("long_tail_cogs_rate_strategies", sa.Column("legal_entity_id", sa.Integer, nullable=True))
    op.add_column("long_tail_cogs_rate_strategies", sa.Column("production_unit_id", sa.Integer, nullable=True))

    # 2. 老数据回填（保证向后兼容）
    op.execute("""
        UPDATE long_tail_cogs_rate_strategies
        SET rate_type='cogs',
            scope_type='category',
            scope_id=category,
            rate_basis='pct_of_revenue',
            source='long_tail_legacy'
        WHERE rate_type IS NULL OR rate_type='cogs'
    """)

    # 3. 索引
    op.create_index(
        "idx_cost_rate_lookup",
        "long_tail_cogs_rate_strategies",
        ["rate_type", "scope_type", "scope_id", "enabled", sa.text("effective_from DESC")],
        postgresql_where=sa.text("is_archived = FALSE"),
    )
    op.create_index(
        "idx_cost_rate_global_active",
        "long_tail_cogs_rate_strategies",
        ["rate_type", sa.text("effective_from DESC")],
        postgresql_where=sa.text("enabled = TRUE AND is_archived = FALSE AND scope_type = 'global'"),
    )

    # 4. 表改名 + 兼容视图
    op.rename_table("long_tail_cogs_rate_strategies", "cost_rate_master")
    op.execute("""
        CREATE OR REPLACE VIEW long_tail_cogs_rate_strategies AS
        SELECT * FROM cost_rate_master WHERE rate_type = 'cogs'
    """)

def downgrade():
    op.execute("DROP VIEW IF EXISTS long_tail_cogs_rate_strategies")
    op.rename_table("cost_rate_master", "long_tail_cogs_rate_strategies")
    op.drop_index("idx_cost_rate_global_active", table_name="long_tail_cogs_rate_strategies")
    op.drop_index("idx_cost_rate_lookup", table_name="long_tail_cogs_rate_strategies")
    for col in ["production_unit_id", "legal_entity_id", "cost_center_id", "data_quality",
                "effective_to", "effective_from", "source", "rate_basis",
                "scope_id", "scope_type", "rate_type"]:
        op.drop_column("long_tail_cogs_rate_strategies", col)
```

### 3.2 `resolve_overhead_rate` 的 4 层链（按 v1.3 §5.1）

```python
# backend/src/planner/services/long_tail_strategy_service.py
def resolve_overhead_rate(
    db: Session,
    *,
    model_id: Optional[int] = None,
    category: Optional[str] = None,
    cost_center_id: Optional[int] = None,
    as_of: Optional[datetime] = None,
) -> Tuple[Decimal, Dict[str, Any]]:
    """
    按 v1.3 §5.1 的 4 层优先级链 resolve overhead_rate。
    Returns: (rate, hit_info) — hit_info 包含 {scope_type, scope_id, source, data_quality}
    给前端可信度徽章 / 调试用。
    """
    # priority: model > category > cost_center > global
    for scope_type, scope_id in [
        ("model", str(model_id) if model_id else None),
        ("category", category),
        ("cost_center", str(cost_center_id) if cost_center_id else None),
        ("global", None),
    ]:
        if scope_type != "global" and not scope_id:
            continue
        row = (
            db.query(models.CostRateMaster)
            .filter(
                models.CostRateMaster.rate_type == "overhead_rate",
                models.CostRateMaster.scope_type == scope_type,
                models.CostRateMaster.scope_id == scope_id if scope_type != "global" else True,
                models.CostRateMaster.enabled == True,
                models.CostRateMaster.is_archived == False,
            )
            .order_by(models.CostRateMaster.effective_from.desc().nullslast())
            .first()
        )
        if row and (row.effective_from is None or row.effective_from <= (as_of or datetime.utcnow())):
            return Decimal(str(row.rate)), {
                "scope_type": scope_type,
                "scope_id": scope_id,
                "source": row.source,
                "data_quality": row.data_quality,
                "hit_layer": scope_type,
            }
    # 4 层都没命中 → 调用方自己兜 hard fallback 0.30
    return Decimal("0.30"), {"scope_type": "hard_fallback", "data_quality": "red"}
```

### 3.3 `bom_generation_service._resolve_overhead_rate` 接入

```python
# backend/src/planner/services/bom_generation_service.py
def _resolve_overhead_rate(db, *, model_version_processes):
    """v1.3 接入 Cost Rate Hub 4 层链"""
    version_id = model_version_processes[0].version_id if model_version_processes else None
    version = db.get(models.ProductModelVersion, version_id) if version_id else None
    model = db.get(models.ProductModel, version.model_id) if version else None

    # === v1.3 新增：先走 Cost Rate Hub 4 层链 ===
    from .long_tail_strategy_service import resolve_overhead_rate as _hub_resolve
    rate, hit = _hub_resolve(
        db,
        model_id=model.id if model else None,
        category=getattr(model, "category", None) if model else None,
        cost_center_id=None,  # v1 暂传 None，Stage 2 接入
    )
    if hit.get("hit_layer") in {"model", "category", "cost_center", "global"}:
        return rate

    # === 回退到旧链：metadata_json.costing.overhead_rate ===
    # ...保留原 line 2017-2046 逻辑作为 metadata_json 兜底...
    # 最终 hard fallback 0.30
```

### 3.4 前端 Tab 结构

```tsx
// frontend/src/pages/costing/admin/LongTailCogsRatePage.tsx
<Tabs
  defaultActiveKey={searchParams.get("tab") || "cogs"}
  items={[
    { key: "cogs", label: "长尾成本兜底（cogs）", children: <ExistingLongTailTable /> },
    { key: "overhead_rate", label: "制造费率治理（overhead_rate）", children: <OverheadRateTable /> },
  ]}
/>
```

`OverheadRateTable` 列：scope_type / scope_id / rate / rate_basis / source / data_quality / effective_from / 操作（编辑/归档）。表单加 scope_type 下拉（model/category/cost_center/global）。

---

## 4. 完成标准（用户能验收的 5 条 — 缺一不可）

```
[ ] 1. Migration 0038 跑通（alembic upgrade head 无报错；cost_rate_master 表存在；
      旧 long_tail_cogs_rate_strategies 视图仍可 SELECT）
[ ] 2. POST /api/planner/long-tail-strategies {rate_type:"overhead_rate", scope_type:"model",
      scope_id:"<KB8 model id>", rate:0.25, rate_basis:"pct_of_cost"} 写入成功
[ ] 3. KB8 实时核价（已有按钮）反映新费率：物料费 26.93 + 人工费 7.34 → 制造费 = (26.93+7.34) × 0.25 = 8.57
      （旧值是 (26.93+7.34) × 0.30 = 10.28，差额 1.71，前端需可见此变化）
[ ] 4. 发货台账"成本拆分" Tab：新创建一条 KB8 发货行，cost_overhead_total 反映 0.25 而非 0.30
[ ] 5. LongTailCogsRatePage 有 2 个 Tab，Tab2 表单可创建/编辑/归档 overhead_rate 类型记录；
      旧 Tab1 行为不变（向后兼容）
```

---

## 5. 验收命令（你**自主选** 1~3 条最能证明完成的，不强求 0 退出码）

按 `workset.md §7.9`（v2.0 修订版）："执行 Agent 自主决定，不强制 1 条"。

候选命令：

```bash
# 后端 — Migration 跑通
cd /home/admin/ai-costing-system/backend && alembic upgrade head

# 后端 — Hub service 单测
cd /home/admin/ai-costing-system && python -m pytest backend/tests/planner/test_cost_rate_hub.py -v

# 后端 — 端到端 API
curl -X POST http://localhost:8002/api/planner/long-tail-strategies \
  -H "Content-Type: application/json" \
  -d '{"rate_type":"overhead_rate","scope_type":"model","scope_id":"<KB8 id>","rate":0.25,"rate_basis":"pct_of_cost","note":"v1.3 Hub 验收"}'

# 后端 — KB8 实时核价 API
curl -X POST http://localhost:8002/api/planner/product-models/<KB8 id>/preview \
  -H "Content-Type: application/json" \
  -d '{"length_mm":1000,"width_mm":1000,"qty":1}' | jq '.costing | {overhead_rate, overhead_cost, total_cost}'

# 前端 build
npm -C frontend run build
```

**反模式（避免）**：
- ❌ 用 `ls` 文件存不存在打卡
- ❌ 跑大量 grep 模拟"全面验收"实际只是堆 Token

---

## 6. 依赖契约（跨域必填）

### 6.1 API 契约变化

| Endpoint | 变化 | 兼容性 |
|---|---|---|
| `GET /api/planner/long-tail-strategies` | 加 `?rate_type=cogs\|overhead_rate\|labor_per_minute\|...` query；默认 `cogs` 兼容旧调用 | 旧调用 0 改动 |
| `POST /api/planner/long-tail-strategies` | body 加 `rate_type` / `scope_type` / `scope_id` / `rate_basis` / `source` / `effective_from` / `data_quality`，全部 optional 默认值同 §3.1 SQL | 旧调用 0 改动 |
| `PATCH /api/planner/long-tail-strategies/{id}` | 同 POST | 旧调用 0 改动 |
| `POST /api/planner/long-tail-strategies/resolve-preview` | 加 optional body 字段 `rate_type` / `model_id` / `cost_center_id`；返回加 `hit_layer` / `hit_scope_type` | 旧调用 0 改动 |

### 6.2 类型枚举（Pydantic + TS 同步）

```python
RateType = Literal["cogs", "labor_per_minute", "labor_per_piece", "labor_per_sqm", "overhead_rate"]
ScopeType = Literal["global", "category", "cost_center", "model"]  # v1 实做这 4 层；schema 留 8 层枚举（v1.3 §1.1）
RateBasis = Literal["pct_of_revenue", "pct_of_cost", "per_minute", "per_piece", "per_sqm"]
DataQuality = Literal["green", "yellow", "red"]  # 与 data_quality_service 对齐
```

### 6.3 文档口径

- v1.3 设计真相：`DOC/costing/blueprints/cost_rate_hub_design_v1.md` §-1 / §4.3 / §5 / §8
- 23% 折算逻辑：`DOC/costing/manuals/guides/price_calculation_guide.md` v2.1
- 不要试图改这两份文档（设计已定，本任务是落地）

---

## 7. 完成后归集要求（任务交付时 3 件，**中间过程不强制**）

按 `task_distribution_standard.md` v2.0 §3.2：

### 7.1 更新恢复包

```
[ ] DOC/agents/state.md：在末尾加一段「2026-05-XX Cost Rate Hub MVP 完成快照」
    内容：cost_rate_master 表已落地 / KB8 端到端验证 / 影响范围 / 下一步（cost_center 表 + Insights 徽章是后续单独派单）
[ ] DOC/agents/task_log.md：追加 1 行（按现有表格格式）
[ ] DOC/agents/known_issues.md：如发现遗留问题 / 待优化项，新增 Issue 段
[ ] DOC/agents/commands.md：加一条 Hub MVP 验收命令（你跑通的那条）
```

### 7.2 更新追踪表

```
[ ] DOC/costing/handovers/system_capability_inventory.md §13.1：
    把 U5 / U6 / U7 三行的"当前状态"列改为 "✅ 2026-05-XX 完成（cost_rate_hub_mvp.md）"
[ ] §13.3 已完成事项审计表：追加 1 行
[ ] §14 修订历史：追加 v1.0+§13+MVP 一行
```

### 7.3 Git 落地

- 1 次大 commit 或 2~3 个子 commit 自主决定（避免 10+ 微 commit 风暴）
- commit message 引用本任务单：`feat(costing): Cost Rate Hub MVP v1.3 (briefings/cost_rate_hub_mvp.md)`
- **不要 push** — 等用户确认后再 push

---

## 8. 不在本次范围（v1 后续单独派单）

| 项 | 何时启动 |
|---|---|
| `cost_center` 表新建 + 数据初始化（4 个店铺主体）| 用户决定 cost_center 初稿后，单独派单 |
| 4 个 Insights 看板加可信度徽章 | Hub MVP 验证通过后单独派单（U7 续作）|
| 三视图切换（Tax/Mgmt/Group） | Phase 1 W4 finance 集成时一起做 |
| `data_quality_service` 加 `cost_quality` 维度 | Stage 2 |
| `materials` 表 Stage 2 字段（purchase_entity_id / tax_rate / effective_from）| Stage 2 |
| 长尾兜底页面拆分 | v2 |

---

## 9. 关键风险（已知，请规避）

| 风险 | 规避 |
|---|---|
| Migration 0038 跑失败导致 long-tail 现有功能挂 | downgrade 已写好；先在本地跑 alembic upgrade head + downgrade base 双向验证 |
| 兼容视图 `long_tail_cogs_rate_strategies` 在 SQLite 测试环境不支持某些语法 | PostgreSQL 是生产环境；如本地测试用 SQLite 需要在 `if dialect == 'sqlite'` 分支跳过视图（按现有 migration 风格）|
| 前端 Tab 切换导致 URL state 丢失 | 用 useSearchParams 同步 `?tab=overhead_rate` |
| `_resolve_overhead_rate` 接入后影响 KB8 之外的所有模型 | 默认 4 层链都没命中时回退 metadata_json，老模型行为完全不变 |
| 老 long-tail Tab 的"创建新策略"表单不知道新加的 11 个字段填什么 | Tab1 表单不变（继续走老 schema，新字段后端 default 自动填）|

---

## 10. 元信息

| 项 | 值 |
|---|---|
| 任务单版本 | v1.0 |
| 派单日期 | 2026-05-09 18:05 北京时间 |
| 派单人 | Hub Agent |
| 承接 Agent | `@Fullstack Agent`（任意全栈 Agent）|
| 预估工作量 | 5~8 人天 |
| 核心设计文档 | `DOC/costing/blueprints/cost_rate_hub_design_v1.md` v1.3（**任何冲突以 v1.3 为准**）|
| 派单规则版本 | `task_distribution_standard.md` v2.0（2026-05-09 18:00 重大修订）|
| 关联 U# | system_capability_inventory.md §13.1 U5 + U6 + U7 |

---

## 11. 一句话给执行 Agent

读完 §0 + §2.1 三步必读 + §3 关键技术决策（共约 20 分钟），就开始动手；scope 内完全自主，5~8 天后回来交付 + 归集，不需要每天汇报。
