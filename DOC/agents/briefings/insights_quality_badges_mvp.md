# Insights 看板成本可信度徽章 — 全栈中等任务单（U7-A）

> **派单类型**：全栈中等任务（后端 5 endpoint 微调 + 前端 4 看板加列），按 `task_distribution_standard.md` v2.0 §3.1 模板
> **派单日期**：2026-05-09 18:35 北京时间
> **派单人**：Hub Agent
> **承接 Agent 角色**：`@Fullstack Agent`（scope 内拥有**完整自主权限**）
> **本任务对应**：`system_capability_inventory.md §13.1 U7` 的 **A 部分**（可信度徽章）；B 部分（三视图切换）因依赖 `cost_center_master` 主表 + 4 店铺 `legal_entity` 录入 + finance 集成，**已拆出留待主数据就绪后单独派单**

---

## 0. 30 秒摘要

让用户在 4 个 Insights 看板（销售/店铺/模型/售后）上**直接看到** Cost Rate Hub 的成本可信度信号 — 哪些 SKU/订单的成本是 🟢 真实命中、🟡 默认兜底、🔴 长尾 hard fallback：

1. **后端**：5 个 analytics endpoint 的 response 加 `cost_quality` 字段聚合（按 `Hub.resolve_overhead_rate` 返回的 `hit_layer` / `data_quality` 推导）
2. **前端**：4 个 Insights 看板表格加一列 "成本可信度"（🟢/🟡/🔴 + tooltip 解释）
3. **不动**：现有看板的所有筛选/排序/数值列保留（向后兼容）

**用户验收**：你登录 4 个 Insights 看板，每行都能看到 1 个新列「成本可信度」；点击徽章能看到 tooltip「命中层级：model / 来源：cost_rate_hub / 时间：2026-05-09」。

---

## 1. 任务范围

### 1.1 后端（Backend scope）

| 文件 | 动作 | 关键变化 |
|---|---|---|
| `backend/src/planner/routers/analytics.py` | **修改** | 5 个 endpoint response 加 `cost_quality` 字段（聚合逻辑）|
| `backend/src/planner/schemas/analytics.py`（按需 grep 实际路径）| **修改** | 5 个 Pydantic Response 模型加 `cost_quality: Optional[CostQualityBadge]` |
| `backend/src/planner/services/analytics_service.py` | **修改** | 5 个 service function 在算 sku/model/channel 聚合时调用 `Hub.resolve_overhead_rate` 拿 `hit_layer`，按 §3.2 推导规则映射成 `cost_quality` |
| `backend/tests/planner/test_analytics_quality.py` | **新建** | 3 个核心场景测试（详见 §4） |

### 1.2 前端（Frontend scope）

| 文件 | 动作 | 关键变化 |
|---|---|---|
| `frontend/src/pages/costing/ProfitInsightsPage.tsx` | **修改** | Table columns 加「成本可信度」列（最右）|
| `frontend/src/pages/costing/ShopInsightsPage.tsx` | **修改** | 同上 |
| `frontend/src/pages/costing/SalesInsightsPage.tsx` | **修改** | 同上 |
| `frontend/src/pages/costing/AfterSalesInsightsPage.tsx` | **修改** | 同上 |
| `frontend/src/components/costing/CostQualityBadge.tsx` | **新建** | 复用组件：3 色 Tag + tooltip 显示 hit_layer / source / updated_at |
| `frontend/src/types/planner.ts`（或 services/analytics.ts）| **修改** | 加 `CostQualityBadge` 类型定义 |

### 1.3 不在 scope 内（禁止改）

- ❌ 三视图切换（Tax/Mgmt/Group）— 留待 `cost_center_master` + 4 店铺 `legal_entity` 录入后单独派单（U7-B）
- ❌ `cost_center_master` 主表新建 — 需要用户先确认 4 店铺 + 6 班组初稿
- ❌ 新增看板 / 调整现有筛选条件 / 改 4 个 profit API 数值列含义
- ❌ Hub 端的 `cost_rate_master` 表本身（已落地，本任务只是消费它）

### 1.4 自主权范围明确

你**完全自主**（同 Hub MVP 任务单 §1.4）：自由拆分中间步骤、自由 commit、自由调用工具、scope 内无需请示。

仅 3 种情况立即回 Hub：scope 不够 / 架构冲突 / ≥ 3 方案仍卡死。

---

## 2. 必读上下文（10 分钟内可掌握）

### 2.1 必读 3 步

```
[ ] 1. DOC/agents/agent_rules.md（v2.0 §2/§7 — 任务粒度 + 交接成本约束）
[ ] 2. DOC/costing/handovers/system_capability_inventory.md §12 + §13.1 U7
[ ] 3. DOC/agents/briefings/cost_rate_hub_mvp.md（你的前序任务，已交付 commit 8c7349cd）
```

### 2.2 按需扩读

- 想理解 Hub 的 `hit_info` 结构 → `backend/src/planner/services/long_tail_strategy_service.py::resolve_overhead_rate`（已存在，子 Agent 实现）
- 想理解 4 个看板的现状数据流 → `DOC/costing/blueprints/profit_and_returns_analytics_plan_2025_2026_v0_1.md`（v0.1 原配蓝图）
- 想看 `data_quality_service` 的 3 色雏形 → `backend/src/planner/services/data_quality_service.py`

### 2.3 关键代码定位（不需要再 grep）

| 关键点 | 路径 | 行号 |
|---|---|---|
| 5 个 analytics endpoint | `backend/src/planner/routers/analytics.py` | 30 (returns-rate/sku) / 59 (returns-rate/channel) / 115 (profit/sku) / 143 (profit/channel) / 169 (profit/model) |
| Hub `resolve_overhead_rate` 返回 hit_info | `backend/src/planner/services/long_tail_strategy_service.py` | 子 Agent 新增（含 `hit_layer` / `data_quality` / `source` 字段）|
| 现有 `data_quality_service` 三色雏形 | `backend/src/planner/services/data_quality_service.py` | 全文 |
| 4 个 InsightsPage 文件 | `frontend/src/pages/costing/{Profit,Shop,Sales,AfterSales}InsightsPage.tsx` | 全文 |

---

## 3. 关键技术决策（已定，不要再讨论）

### 3.1 `CostQualityBadge` 类型契约（前后端共用）

```typescript
// frontend/src/types/planner.ts
export interface CostQualityBadge {
  level: 'green' | 'yellow' | 'red';
  hit_layer: 'model' | 'category' | 'cost_center' | 'global' | 'metadata_json' | 'hard_fallback';
  source: string;        // 'cost_rate_hub' | 'metadata_json' | 'long_tail_legacy' | 'hardcoded_0.30'
  updated_at?: string;   // ISO 8601
}
```

```python
# backend/src/planner/schemas/analytics.py
from pydantic import BaseModel
from typing import Optional, Literal

class CostQualityBadge(BaseModel):
    level: Literal["green", "yellow", "red"]
    hit_layer: Literal["model", "category", "cost_center", "global", "metadata_json", "hard_fallback"]
    source: str
    updated_at: Optional[str] = None
```

### 3.2 后端推导规则（hit_layer → level）

```python
HIT_LAYER_TO_LEVEL = {
    "model":          "green",   # 🟢 model 命中 = 真实精准
    "category":       "yellow",  # 🟡 category 命中 = 同类近似
    "cost_center":    "yellow",  # 🟡 cost_center 命中 = 同班组近似
    "global":         "red",     # 🔴 global 命中 = 全局兜底（精度低）
    "metadata_json":  "yellow",  # 🟡 metadata 兜底 = 历史配置
    "hard_fallback":  "red",     # 🔴 0.30 hard fallback = 完全不可信
}
```

### 3.3 聚合规则（多个 SKU/订单聚合到一行时）

聚合一行（如某个 model 包含 100 个 SKU）的 `cost_quality.level`：

```python
def aggregate_quality(badges: List[CostQualityBadge]) -> CostQualityBadge:
    """取最差 level 作为聚合 level（保守显示）"""
    levels = {b.level for b in badges}
    if "red" in levels:    return red_badge
    if "yellow" in levels: return yellow_badge
    return green_badge  # 全 green 才显示 green
```

### 3.4 前端 Badge 组件（参考 Ant Design Tag）

```tsx
// frontend/src/components/costing/CostQualityBadge.tsx
import { Tag, Tooltip } from 'antd';

const COLOR_MAP = { green: 'success', yellow: 'warning', red: 'error' } as const;
const LABEL_MAP = { green: '高', yellow: '中', red: '低' } as const;
const HIT_LAYER_LABEL = {
  model: '模型级精确',
  category: '类目级近似',
  cost_center: '班组级近似',
  global: '全局兜底',
  metadata_json: '历史配置',
  hard_fallback: '硬编码 0.30',
} as const;

export const CostQualityBadge: React.FC<{ badge?: CostQualityBadge }> = ({ badge }) => {
  if (!badge) return <Tag>-</Tag>;
  return (
    <Tooltip title={`命中：${HIT_LAYER_LABEL[badge.hit_layer]} / 来源：${badge.source}${badge.updated_at ? ` / ${badge.updated_at.slice(0, 10)}` : ''}`}>
      <Tag color={COLOR_MAP[badge.level]}>{LABEL_MAP[badge.level]}</Tag>
    </Tooltip>
  );
};
```

### 3.5 性能注意

5 个 analytics endpoint 通常返回 100~1000 行，**不要**对每行单独调 `resolve_overhead_rate`（会触发 N 次 DB query）。建议：

- 在 service 层一次性查出所有相关 model 的 cost_rate_master 行（按 `model_id IN (...)`）
- 内存里 build `Dict[model_id, CostQualityBadge]` 索引
- 聚合时直接查字典

---

## 4. 完成标准（用户能验收的 5 条）

```
[ ] 1. 4 个 Insights 看板每行都有「成本可信度」列（🟢/🟡/🔴 Tag）
[ ] 2. 鼠标 hover Tag 显示 tooltip：命中层级 + 来源 + 更新时间
[ ] 3. KB8 配过 model 级 overhead_rate=0.25 → KB8 行显示 🟢「模型级精确」
[ ] 4. 没配 overhead_rate 的模型 → 显示 🔴「全局兜底」或 🔴「硬编码 0.30」
[ ] 5. 5 个 analytics endpoint 性能未明显退化（前后对比，请求 ≤ 之前 + 200ms）
```

---

## 5. 验收命令（自主选 1~3 条）

```bash
# 后端单测
python -m pytest backend/tests/planner/test_analytics_quality.py -v

# 后端 endpoint 返回新字段
curl http://localhost:8002/api/planner/analytics/profit/model | jq '.[0] | {model_name, cost_quality}'

# 前端 build
npm -C frontend run build

# 前端类型检查
npm -C frontend run typecheck   # 或 npx tsc --noEmit
```

---

## 6. 依赖契约

### 6.1 API 响应字段（5 个 endpoint 同样新增）

```diff
{
  "model_id": "...",
  "model_name": "KB8",
  "revenue_total": 12345.67,
  "cost_total": 8901.23,
  "profit_total": 3444.44,
+ "cost_quality": {
+   "level": "green",
+   "hit_layer": "model",
+   "source": "cost_rate_hub",
+   "updated_at": "2026-05-09T18:00:00Z"
+ }
}
```

向后兼容：旧前端调用读不到 `cost_quality` 字段也不会崩（optional）。

### 6.2 不影响的契约

- 现有 5 个 endpoint 的 query parameter / 数值列含义 / 排序逻辑 — **0 改动**
- 现有 4 个看板的筛选条件 / 时间范围切换 / 钻取行为 — **0 改动**

---

## 7. 完成后归集（任务交付时 3 件）

按 `task_distribution_standard.md` v2.0 §3.2：

```
[ ] DOC/agents/state.md：末尾加一段「2026-05-XX U7-A 看板可信度徽章完成快照」
[ ] DOC/agents/task_log.md：追加 1 行
[ ] DOC/costing/handovers/system_capability_inventory.md §13.1 U7：状态改为「✅ A 部分完成（badges_mvp.md），B 部分（三视图）待 cost_center + legal_entity 主数据就绪后单独派单」
[ ] git commit 1 次大 commit 或 2~3 子 commit；不要 push
```

---

## 8. 不在本次范围（v1 后续单独派单）

| 项 | 何时启动 |
|---|---|
| **U7-B 三视图切换**（Tax/Mgmt/Group） | `cost_center_master` 主表 + 4 店铺 `legal_entity` 录入 + finance C1 契约就绪后单独派单 |
| `cost_center_master` 主表新建 + 6 班组初稿 | 用户决定 cost_center 初稿后 |
| Stage 2 物料端 4 字段 | 独立任务 |
| `data_quality_service` 加 `cost_quality` 维度 | Stage 2（本任务先用 Hub 的 hit_info 自推） |

---

## 9. 关键风险

| 风险 | 规避 |
|---|---|
| 5 个 endpoint 加字段后老前端报错 | 字段是 optional，老前端忽略未知字段不会崩；如有 strict mode 测试再加 |
| 性能退化（N+1 查询）| 见 §3.5，service 层批量查 cost_rate_master 一次性 build dict |
| `cost_quality` 概念与现有 `data_quality_service` 字段名重叠 | 本任务用独立类型 `CostQualityBadge`；与 `data_quality_service` 的 SKU 数据质量是不同维度，前端列名分别叫「成本可信度」vs「数据质量」即可 |
| KB8 在多个看板出现导致徽章不一致 | §3.3 聚合规则保守取最差，已规避 |

---

## 10. 元信息

| 项 | 值 |
|---|---|
| 任务单版本 | v1.0 |
| 派单日期 | 2026-05-09 18:35 北京时间 |
| 派单人 | Hub Agent |
| 承接 Agent | `@Fullstack Agent` |
| 预估工作量 | 1.5~2 人天（AI Agent 跑约 2~4 小时）|
| 前序依赖 | Hub MVP commit 8c7349cd（已落地）|
| 关联 U# | system_capability_inventory.md §13.1 U7 (A 部分) |

---

## 11. 一句话给执行 Agent

读完 §0 + §2.1 三步必读 + §3 关键技术决策（共约 15 分钟），就开始动手；2~4 小时后回来交付 + 归集。
