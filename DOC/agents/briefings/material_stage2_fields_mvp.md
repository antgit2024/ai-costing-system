# Materials Stage 2 字段扩展 — 全栈大任务单

> **派单类型**：全栈大任务（Migration + ORM + Pydantic + 后端 router + 前端 UI + 宜搭同步兼容），按 `task_distribution_standard.md` v2.0 §3.1 模板
> **派单日期**：2026-05-10 07:05 北京时间
> **派单人**：Hub Agent
> **承接 Agent 角色**：`@Fullstack Agent`（scope 内拥有**完整自主权限**）
> **预估工作量**：1 人天（AI Agent 跑约 4~6 小时）
> **关联设计文档**：`cost_rate_hub_design_v1.md` v1.3 §4.5 + §13 Stage 2

---

## 0. 30 秒摘要

把 `materials` 表加 6 个税务/采购/效期字段，让物料成本从"近似"变"坐实"：

1. **后端**：Migration 0039 + ORM + Pydantic schema + base_config.py PATCH/POST/GET 暴露新字段
2. **前端**：MaterialMasterPage.tsx 编辑抽屉 + 列表加显示
3. **宜搭同步兼容**：MaterialSyncJob 3 种 mode（full/new_only/core_fields）保持向后兼容，新字段同步策略由你判断（建议：宜搭无映射时不覆盖）
4. **不动**：BOM 计算逻辑（v1 仍走 `materials.unit_price`，effective_from 按发货日期取价是 Stage 3 的事）

**用户验收**：你登录 `/costing/materials`，编辑任一物料抽屉里能看到/编辑「采购主体 / 含税标 / 税率 / 价格来源 / 生效期 / 失效期」6 个新字段；保存后再次打开值还在。

---

## 1. 任务范围（你拥有完整自主权限）

### 1.1 后端（Backend scope）

| 文件 | 动作 | 关键变化 |
|---|---|---|
| `backend/migrations/versions/0039_materials_stage2_fields.py` | **新建** | 见 §3.1 SQL（已写好可直接抄）|
| `backend/src/planner/models.py` | **修改** | `Material` ORM（line 301）加 6 字段 |
| `backend/src/planner/schemas/`（按需 grep 实际位置）| **修改** | Material 相关 Pydantic Read/Create/Update/Patch 加 6 字段（全 optional）|
| `backend/src/planner/routers/base_config.py` | **修改** | GET /base-config/materials + PATCH /base-config/materials/{id} 暴露新字段；POST 创建时支持新字段 |
| `backend/src/planner/services/material_*.py`（按需 grep）| **修改** | 如有专用 service 层，处理新字段读写 |
| `backend/src/planner/services/yida_*.py` 或 `material_sync_*.py`（按需 grep）| **修改** | MaterialSyncJob 同步逻辑：3 种 mode（full/new_only/core_fields）全部保持向后兼容；**新字段宜搭无字段映射时不覆盖本地值** |
| `backend/tests/planner/test_materials_stage2_fields.py` | **新建** | 见 §4 完成标准的 4 个测试场景 |

### 1.2 前端（Frontend scope）

| 文件 | 动作 | 关键变化 |
|---|---|---|
| `frontend/src/pages/costing/MaterialMasterPage.tsx` | **修改** | 编辑抽屉/创建表单加 6 字段输入；列表加 1~2 列显示（建议「采购主体」+「税率(含税)」 — 详见 §3.4）|
| `frontend/src/types/planner.ts` 或 `frontend/src/services/materials.ts`（按需 grep）| **修改** | TS 类型定义同步 6 字段 |

### 1.3 不在 scope 内（禁止改）

按设计文档 §13 Stage 2 范围更广，但本任务**只做字段落地**，不做以下：

- ❌ BOM 计算逻辑（不接月度加权平均 worker，v1 仍直读 `materials.unit_price`）
- ❌ 按 `effective_from` 取价（这是 Stage 3）
- ❌ 接采购系统拉 PO 数据
- ❌ Hub Tab 1 「物料价格治理」卡片（这是后续单独派单）
- ❌ BOM 用量审计 / 辅料补全（这是工厂业务，不是技术任务）
- ❌ 新建 `purchase_entity` 主表（设计文档 §4.5 明确：v1 用枚举字符串，Phase 2 再建主表）

### 1.4 完整自主权范围

同昨天 Hub MVP / U7-A 任务单 §1.4：scope 内自由读写、自由跑测、自主拆 commit、scope 内不需请示；仅在 scope 不够 / 架构冲突 / ≥ 3 方案卡死时回 Hub。

---

## 2. 必读上下文

### 2.1 必读 3 步

```
[ ] 1. DOC/agents/agent_rules.md（v2.0 §2/§7）
[ ] 2. DOC/costing/blueprints/cost_rate_hub_design_v1.md v1.3 §4.5（materials Stage 2 改造完整 SQL + 设计意图）
[ ] 3. DOC/costing/blueprints/cost_rate_hub_design_v1.md v1.3 §13 Stage 2（更广范围，了解本任务是 Stage 2 的第 1 步）
```

### 2.2 关键代码定位（不需要 grep 找）

| 关键点 | 路径 | 行号 |
|---|---|---|
| `Material` ORM 主表 | `backend/src/planner/models.py` | 301（继承 TimestampMixin / SoftDeleteMixin）|
| `MaterialSyncJob`（宜搭同步）| `backend/src/planner/models.py` | 886 |
| 现有 materials router | `backend/src/planner/routers/base_config.py` | 全文（含 PATCH /base-config/materials/{id}）|
| 现有 materials 前端页面 | `frontend/src/pages/costing/MaterialMasterPage.tsx` | 全文（1956 行，含编辑抽屉 + 同步按钮）|
| 宜搭同步配置 | `backend/config/yida_materials.json` | 全文（看现有 fieldId 映射风格）|
| 已落地的 effective_from/to 先例 | `backend/src/planner/models.py` | 1573-1574（`cost_rate_master` 已用过同名字段，可参考类型/Migration 风格）|

---

## 3. 关键技术决策（已定，不要再讨论）

### 3.1 Migration 0039 SQL 骨架（按设计文档 §4.5）

```python
# backend/migrations/versions/0039_materials_stage2_fields.py
"""materials Stage 2: 加 purchase_entity_id / tax_included_flag / tax_rate / price_source / effective_from / effective_to

Revision ID: 0039_materials_stage2_fields
Revises: 0038_cost_rate_master
Create Date: 2026-05-10
"""
from alembic import op
import sqlalchemy as sa

revision = "0039_materials_stage2_fields"
down_revision = "0038_cost_rate_master"

def upgrade():
    # 6 个字段全部 nullable，向后兼容（老数据 = 全 NULL）
    op.add_column("materials", sa.Column("purchase_entity_id", sa.String(36), nullable=True))
    op.add_column("materials", sa.Column("tax_included_flag", sa.Boolean, nullable=False, server_default=sa.false()))
    op.add_column("materials", sa.Column("tax_rate", sa.Numeric(6, 4), nullable=True))
    op.add_column("materials", sa.Column("price_source", sa.String(32), nullable=True))
    op.add_column("materials", sa.Column("effective_from", sa.Date, nullable=True))
    op.add_column("materials", sa.Column("effective_to", sa.Date, nullable=True))

    # 索引：按"采购主体 + 生效期"取最新有效价（Stage 3 worker 会用到）
    op.create_index(
        "idx_materials_purchase_entity_effective",
        "materials",
        ["purchase_entity_id", sa.text("effective_from DESC")],
        postgresql_where=sa.text("effective_to IS NULL OR effective_to >= CURRENT_DATE"),
    )

def downgrade():
    op.drop_index("idx_materials_purchase_entity_effective", table_name="materials")
    for col in ["effective_to", "effective_from", "price_source", "tax_rate",
                "tax_included_flag", "purchase_entity_id"]:
        op.drop_column("materials", col)
```

### 3.2 ORM（models.py:301 加 6 字段）

```python
# 在 Material 类内部追加（按现有字段风格）
class Material(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "materials"
    # ... 现有字段 ...

    purchase_entity_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    tax_included_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa.false())
    tax_rate: Mapped[Decimal | None] = mapped_column(Numeric(6, 4), nullable=True)
    price_source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    effective_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
```

### 3.3 字段语义/枚举值（前后端共用，写进 Pydantic + TS）

```python
# Pydantic
PurchaseEntityCode = Literal["一般纳税人", "小规模A", "小规模B"]  # v1 先用枚举字符串，Phase 2 再换 cost_center_master 表 2 的真实主体 ID
PriceSource = Literal["manual", "po_avg_30d", "last_po", "contract", "system_imported", "yida_sync"]
# tax_rate: 0.0000 ~ 1.0000 (e.g. 0.13 表示 13%)
# tax_included_flag: True = 物料价已含税，False = 不含税（净价）
# effective_from / effective_to: NULL 表示"立即生效 / 当前生效"
```

> **`purchase_entity_id` 暂用字符串枚举的原因**：cost_center_master 表 2 还没建（用户在填模板），v1 先用字面字符串，Phase 2 用户填完后单独派 Agent 把字符串迁移到真实 UUID。**Migration 0039 字段类型用 String(36) 是为 Phase 2 的 UUID 留位，不需要现在就改类型**。

### 3.4 前端 UI 设计（MaterialMasterPage 编辑抽屉）

在现有「基础信息」/「BOM 单位」/「采购单价」等分组之后，加一个新分组「税务/采购/效期 (Stage 2)」：

```
┌─ 税务/采购/效期 (Stage 2) ──────────────────┐
│ 采购主体：    [下拉: 一般纳税人 / 小规模A / 小规模B / ?] │
│ 含税标志：    [Switch: 含税 / 不含税]               │
│ 税率：        [InputNumber: 0~100, 后缀 %]          │
│ 价格来源：    [下拉: 手工 / 30天均价 / 最近一次 PO /  │
│                合同 / 系统导入 / 宜搭同步]            │
│ 生效期：      [DatePicker]                          │
│ 失效期：      [DatePicker]                          │
└────────────────────────────────────────────┘
```

列表加 2 列（默认显示，但用户可在"列设置"里隐藏）：
- 「采购主体」（显示 purchase_entity_id 的简称：一般 / 小A / 小B / `-`）
- 「税率」（显示 `13% (含税)` / `13% (不含税)` / `-`）

### 3.5 宜搭同步策略（MaterialSyncJob 兼容）

3 种 mode 处理 6 个新字段的策略：

| Mode | 6 字段处理 |
|---|---|
| `full` | 不覆盖（宜搭未提供这 6 字段，避免清空本地）|
| `new_only` | 不写入（仅新建物料用宜搭基础字段，6 个新字段保持 NULL，等用户手填）|
| `core_fields` | 不动（mode 名义只更新入库价/采购价/单位，不碰这 6 个新字段）|

> **如果未来宜搭加了对应字段映射**：在 `backend/config/yida_materials.json` 加 fieldId 映射后，`full` mode 即可同步；本任务不需要预先做映射。

---

## 4. 完成标准（用户能验收的 5 条）

```
[ ] 1. Migration 0039 跑通（alembic upgrade head + downgrade -1 双向；老物料数据 6 字段全 NULL/默认值；现有 BOM/物料同步流程零回归）
[ ] 2. PATCH /api/planner/base-config/materials/{id} 能写入 6 个新字段；GET 能读回；POST 创建能携带
[ ] 3. /costing/materials 编辑抽屉有「税务/采购/效期 (Stage 2)」新分组，6 字段可填可保存可读回
[ ] 4. /costing/materials 列表有「采购主体」+「税率」2 列；老物料显示 `-`
[ ] 5. 现有宜搭同步 3 种 mode 跑通（用 1 个测试物料各跑 1 次）+ 6 个新字段不被覆盖（保持本地值）
```

---

## 5. 验收命令（自主选 1~3 条）

```bash
# 后端
cd backend && alembic upgrade head && alembic downgrade -1 && alembic upgrade head
python -m pytest backend/tests/planner/test_materials_stage2_fields.py -v
python -m pytest backend/tests/planner/test_material_sync_*.py -v   # 回归测

# 端到端
curl -X PATCH http://localhost:8002/api/planner/base-config/materials/<id> \
  -H "Content-Type: application/json" \
  -d '{"purchase_entity_id":"一般纳税人","tax_included_flag":true,"tax_rate":0.13,"price_source":"manual","effective_from":"2026-05-10"}'

# 前端
npm -C frontend run build
```

---

## 6. 依赖契约（API 向后兼容）

```diff
PATCH /api/planner/base-config/materials/{id}
{
  // 现有字段 ...
+ "purchase_entity_id": "一般纳税人",   // optional
+ "tax_included_flag": true,             // optional, default false
+ "tax_rate": 0.13,                      // optional, 0.0~1.0
+ "price_source": "manual",              // optional, enum
+ "effective_from": "2026-05-10",        // optional, ISO date
+ "effective_to": null                   // optional
}
```

旧前端调用（不带新字段）零改动；新前端调用（带新字段）正常工作。

---

## 7. 完成后归集（任务交付时 3 件）

```
[ ] DOC/agents/state.md：末尾加一段「2026-05-XX Materials Stage 2 字段完成快照」
[ ] DOC/agents/task_log.md：追加 1 行
[ ] git add + commit（1 次大 commit 或 2~3 子 commit 自主决定）
[ ] git push origin HEAD（**这次允许直接 push**，因为昨天 dirty 已清干净 + 本任务 scope 清晰）
```

---

## 8. 不在本次范围（Stage 2 后续 / Stage 3）

| 项 | 何时启动 |
|---|---|
| 月度加权平均价 worker（拉 PO 平均价填 `materials.unit_price`）| Stage 2 后续单独派单 |
| Hub Tab 1 「物料价格治理」卡片 | Stage 2 后续单独派单 |
| BOM 按 `effective_from` 取历史价 | Stage 3 |
| 接采购系统 / ERP 拉 PO 数据 | Stage 2 / 3 |
| 把 `purchase_entity_id` 字符串迁移到 cost_center_master 真实 UUID | A 路径完成（用户填完模板）后单独派单 |
| BOM 用量审计 / 辅料补全 | 工厂业务，不在技术任务范畴 |

---

## 9. 关键风险

| 风险 | 规避 |
|---|---|
| 老物料 Excel 历史灌数据导致 effective_from 缺失 | 字段 nullable，老数据全 NULL；BOM 不依赖 effective_from（v1 仍直读 unit_price）|
| `tax_included_flag` 默认 false 与现有 yida 数据真实情况不符 | 默认 false 是最保守选择；用户后续可批量 PATCH 修正；不影响 BOM 算价 |
| 索引 `idx_materials_purchase_entity_effective` 在大表上影响写性能 | partial index，只索引"当前有效"行，影响极小 |
| 前端列加多了导致表格挤 | 只加 2 列（采购主体 + 税率），其余在抽屉里编辑；用户可在列设置隐藏 |
| 宜搭同步把新字段意外覆盖成 NULL | §3.5 明确策略：3 种 mode 都不动新字段；测试 §4.5 必须验证 |

---

## 10. 元信息

| 项 | 值 |
|---|---|
| 任务单版本 | v1.0 |
| 派单日期 | 2026-05-10 07:05 北京时间 |
| 派单人 | Hub Agent |
| 承接 Agent | `@Fullstack Agent` |
| 预估工作量 | 1 人天（AI 4~6 小时）|
| 前序依赖 | commit `c1df055d`（昨天 dirty 已清干净）|
| 关联设计 | `cost_rate_hub_design_v1.md` v1.3 §4.5 + §13 Stage 2 |
| 关联 U# | system_capability_inventory.md §13.1 暂无对应 U#（Stage 2 是设计文档预留段，本任务首次启动）|

---

## 11. 一句话给执行 Agent

读完 §0 + §2.1 三步必读 + §3 关键技术决策（共约 15 分钟），就开始动手；4~6 小时后回报。**这次允许直接 git push**（昨天 dirty 已清，本任务 scope 清晰）。
