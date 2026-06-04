# TDABC v1 闭环 Brief — POD 成本核算工作台

> **状态**：v1.0 待派单
> **派单人**：Costing Hub Agent（Cursor / Claude Opus 4.7）
> **创建**：2026-05-10
> **执行人**：Fullstack Agent（Sonnet 4.6 medium thinking）
> **预计工时**：2 天（自主闭环，单 commit）
> **方法论文档**：`DOC/costing/blueprints/costing_methodology_industry_alignment.md`（**必读**）

---

## 0. 一句话目标

> **让 KB8 这个模型在 standard-models 抽屉里，能看到唯一真实的物料/人工/制造费三层成本，每一项数据来源透明可追，工艺特殊时可单独覆盖人工/制造费率。**

完成后效果：

```
KB8 (转印包边垫类)        [基础信息][清单编辑][成本核算]   ← 新 Tab
                                                  ▲
                              点开后：实时试算 + 4 层链路 + 一键覆盖
```

---

## 1. 背景（一定要先读）

### 1.1 我们是 POD，不是 MTO
- 详见 `DOC/costing/blueprints/costing_methodology_industry_alignment.md`
- **不要做** SAP 标准成本表 / 月度差异分摊 / 生产订单结算
- **要做** TDABC（时间驱动作业成本法）的闭环

### 1.2 我们 TDABC 现状（已完成 60%）
- ✅ `cost_center_aggregator_service` 已写：班组真工资 ÷ 班组工时容量 = 班组人均时薪 → upsert `cost_rate_master.labor_per_minute scope=cost_center`
- ✅ `cost_allocator_service` 已写：固定费按面积/人头/营收摊到班组 → upsert `cost_rate_master.overhead_rate scope=cost_center`
- ✅ `_resolve_overhead_rate` 已接 4 层 Hub（model > category > cost_center > global）
- ❌ **致命漏洞**：`_compute_process_costing` 仍读 `meta.get("rate_per_minute")`（模型快照里的死数），**没有读 A2 写入的 cost_rate_master.labor_per_minute** → A2 数据是孤儿

### 1.3 这次 v1 修什么
- **G**：把 A2 接通（让 _compute_process_costing 读 cost_rate_master.labor_per_minute）
- **H**：standard-models 抽屉加「成本核算」Tab（实时试算 + 4 层链路 + 模型级覆盖）

### 1.4 这次 v1 不做什么（明确砍掉）
- ❌ SKU 角色（traffic/profit/brand/clearance/new）— 用户已确认不影响成本，纯运营标签
- ❌ ShipmentPnlComputeService（5 损益分类）— 推到 v3
- ❌ cost_snapshot 表 — 推到 v3
- ❌ SkuMaster.sku_role / ProductModel.sku_role 字段 — 角色独立做时再说
- ❌ POD 行业 3 件关键事（设备小时折旧 / 换型成本 / 销量摊销层）— 推到 v2

---

## 2. 任务 G — A2 接通（0.5 天）

### 2.1 后端代码改造

#### G1. 新建 `resolve_labor_rate()` 函数

**文件**：`backend/src/planner/services/long_tail_strategy_service.py`

**位置**：紧跟 `resolve_overhead_rate`（line 641）后面

**签名（参考 resolve_overhead_rate 复制）**：

```python
@dataclass(frozen=True)
class ResolvedLaborRate:
    rate_per_minute: Decimal           # 元/分钟
    hit_layer: str                     # model | category | cost_center | global | hard_fallback | none
    strategy_id: Optional[str]
    scope_id: Optional[str]
    source: Optional[str]              # auto_aggregated_from_finance | manual | ...
    data_quality: Optional[str]
    effective_from: Optional[datetime]
    effective_to: Optional[datetime]


def resolve_labor_rate(
    db: Session,
    *,
    model_id: Optional[str] = None,
    category: Optional[str] = None,
    cost_center_id: Optional[str] = None,
    as_of: Optional[datetime] = None,
) -> ResolvedLaborRate:
    """Cost Rate Hub v1.3 §5.1 4-layer resolve for labor_per_minute.

    Priority: model > category > cost_center > global > hard_fallback (None).
    Hard fallback returns rate=None (caller must fall back to legacy
    metadata.rate_per_minute) — DO NOT default to a hardcoded number,
    because labor varies by 5x between teams (打印 vs 包装).
    """
```

**实现要求**：
- 4 层 chain 与 `resolve_overhead_rate` 完全一致（model > category > cost_center > global）
- 查询 `cost_rate_master` 时 `rate_type='labor_per_minute'`
- `effective_from <= as_of` AND (`effective_to IS NULL OR effective_to > as_of`)
- `enabled=true AND archived=false`
- **hard_fallback 返回 `rate_per_minute=None`**（不是 0，让调用方决定回退策略）

#### G2. `_compute_process_costing` 改造

**文件**：`backend/src/planner/services/bom_generation_service.py`

**位置**：line 1918-2031

**改造 line 1979-1982**（time 类型计算分支）：

**改造前**：
```python
if cost_type == "time":
    total_minutes = base_minutes + (unit_minutes * measure_qty)
    if rate is not None and rate > 0:
        total_cost = total_minutes * rate
    else:
        warnings.append("未配置分钟单价（rate_per_minute）")
        ...
```

**改造后**：
```python
if cost_type == "time":
    total_minutes = base_minutes + (unit_minutes * measure_qty)

    # === TDABC v1 G: try Hub labor_per_minute first ===
    hub_labor_rate: Optional[Decimal] = None
    hub_hit_layer: Optional[str] = None
    if proc and getattr(proc, "cost_center_id", None):
        try:
            from .long_tail_strategy_service import resolve_labor_rate as _hub_labor
            # Pull model_id / category from version's model if available
            # (process is per-line so model is fixed for the whole call)
            hub_hit = _hub_labor(
                db,
                model_id=None,            # process 级别的 model 信息上层未传，本轮不接 model 层
                category=None,
                cost_center_id=str(proc.cost_center_id),
            )
            if hub_hit.rate_per_minute is not None and hub_hit.hit_layer != "hard_fallback":
                hub_labor_rate = Decimal(str(hub_hit.rate_per_minute))
                hub_hit_layer = hub_hit.hit_layer
        except Exception:
            # Hub 错误绝不阻塞计算 — 静默回退到 metadata.rate_per_minute
            pass

    final_rate = hub_labor_rate if hub_labor_rate is not None and hub_labor_rate > 0 else rate
    if final_rate is not None and final_rate > 0:
        total_cost = total_minutes * final_rate
    else:
        warnings.append("未配置分钟单价（rate_per_minute）")
        missing_price_process_lines += 1
        if proc and proc.process_code:
            missing_price_process_codes.append(str(proc.process_code))
```

**还要在 process_cost_lines 里多记录**：

```python
process_cost_lines.append({
    ...
    "rate_per_minute": final_rate if cost_type == "time" else rate,  # 实际用的
    "rate_per_minute_legacy": rate,  # metadata 里的原值，用于审计
    "rate_source": (
        f"hub_{hub_hit_layer}" if hub_hit_layer
        else ("metadata" if rate is not None and rate > 0 else "missing")
    ),
    "cost_center_id": getattr(proc, "cost_center_id", None) if proc else None,
    ...
})
```

#### G3. piece 类型也加 Hub 支持（可选，本轮做）

类似 G2，但查 `rate_type='labor_per_piece'`。如果暂时没数据，hub_hit 会返回 hard_fallback，自动回退 metadata.piece_rate。代码结构对称即可，不必担心 hub 表里没数据。

#### G4. 单元测试

**文件**：`backend/tests/services/test_compute_process_costing_hub_labor.py`（新建）

**至少 4 个测试用例**：
1. **hub 命中 cost_center 层** → 用 hub 价
2. **hub 未命中**（cost_center_id 为 None）→ 回退 metadata.rate_per_minute
3. **hub 未命中**（cost_center_id 有但 cost_rate_master 没数据）→ 回退 metadata.rate_per_minute
4. **hub 命中但值为 0** → 回退 metadata（防御性）

### 2.2 验收

- ✅ 跑 `pytest backend/tests/services/test_compute_process_costing_hub_labor.py` 全绿
- ✅ 跑 `pytest backend/tests/` 全绿（无回归）
- ✅ 拿真实 KB8 模型 preview，确认 process_cost_lines 里出现 `rate_source: "hub_cost_center"`（前提：cost_rate_master 里至少有 1 行 labor_per_minute scope=cost_center scope_id=KB8 的 cost_center_id）
- ✅ 如果 cost_rate_master 里完全没数据，preview 结果 100% 等价于改造前

---

## 3. 任务 H — standard-models 抽屉加「成本核算」Tab（1.5 天）

### 3.1 后端 API（如果 preview_model_cost 已经返回完整信息，可不改）

**先确认**：`backend/src/planner/services/product_model_service.py:preview_model_cost()` 是否已返回：
- 物料拆分（含 price_metadata 含税/采购主体/生效期）
- 工序明细（process_code / process_name / cost_center_id / total_minutes / rate_per_minute / rate_source / total_cost）
- overhead_rate（hit_layer / strategy_id / source）
- 三层合计（material_total / labor_total / overhead_total / grand_total）

**如果 preview_model_cost 已经返回上述全部** → 不需要改后端。
**如果缺**：在 `preview_model_cost` 返回的 `costing` dict 里补字段（不要改 API path 不要破坏现有调用）。

**新增/确认 endpoint**：
- `GET /api/v1/product-models/{model_id}/cost-preview?width_mm=&height_mm=&quantity=&version_id=` → 返回完整成本拆解
- 如果已存在 `previewProductModel`，复用即可

### 3.2 前端 Tab 加在哪

**文件**：`frontend/src/components/costing/ProductModelEditorDrawer.tsx`

**改造 line 299**：

```tsx
const [activeTab, setActiveTab] = useState<'basic' | 'versions' | 'lines' | 'cost'>('lines')
```

**改造 line 3018 起的 items 数组**，在 'lines' 项之后追加：

```tsx
{
  key: 'cost',
  label: '成本核算',  // 不带任何角色字样，纯成本
  children: <CostingTab modelId={modelQuery.data?.id} versionId={selectedVersionId} />,
},
```

### 3.3 新建 `CostingTab` 子组件

**文件**：`frontend/src/components/costing/CostingTab.tsx`（新建）

**UI 结构**：

```
┌─────────────────────────────────────────────────────────┐
│ ⚠️ 试算参数                                              │
│   宽 [180] × 高 [90] (mm)   数量 [1]   版本 [v2026-04▼] │
│   [刷新计算]                                             │
├─────────────────────────────────────────────────────────┤
│ 物料 ¥26.93  🟢 物料级精确                              │
│   ├─ 转印膜 380×190  ¥12.50  🟢 含税还原 13%            │
│   ├─ 包边布 长 540    ¥8.20   🟢 含税还原 13%            │
│   └─ ... [展开 5 项]                                    │
│                                                         │
│ 人工 ¥7.34   🔵 班组级真工资 ← rate_source: hub_cost_center │
│   ├─ 转印切割  CC_PRINT  3min × ¥0.85 = ¥2.55          │
│   ├─ 包边缝纫  CC_DECOR  5min × ¥0.92 = ¥4.60          │
│   └─ 质检打包  CC_QC     2min × ¥0.78 = ¥1.56          │
│   时薪来源：🔵 hub_cost_center（A2 finance 真工资自动算）│
│   [⚙ 为本模型单独设固定时薪 ¥0.90]                      │
│                                                         │
│ 制造费 ¥10.28 🔵 班组级 0.28（A4 自动算）               │
│   命中链路: model(空) > category(空) > cc(0.28) > global(0.30) │
│   [⚙ 为本模型单独设费率]                                │
│                                                         │
│ ─────────────────────────────────                       │
│ 合计 ¥44.55                                             │
│                                                         │
│ ⓘ 这是该模型在【当前 Hub 配置】下，按 TDABC 算法得到的    │
│   唯一真实标准成本。修改 Hub 任何一层 → 立即影响。       │
└─────────────────────────────────────────────────────────┘
```

**核心逻辑**：

```tsx
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Card, Button, InputNumber, Space, Tag, Table, Tooltip, Modal, Form, message, Spin } from 'antd'
import { previewProductModel /* or new costPreview API */ } from '@/services/planner'

interface CostingTabProps {
  modelId?: string | null
  versionId?: string | null
}

export default function CostingTab({ modelId, versionId }: CostingTabProps) {
  const [widthMm, setWidthMm] = useState<number>(180)
  const [heightMm, setHeightMm] = useState<number>(90)
  const [quantity, setQuantity] = useState<number>(1)

  const previewQuery = useQuery({
    queryKey: ['cost-preview', modelId, versionId, widthMm, heightMm, quantity],
    enabled: !!modelId,
    queryFn: () => previewProductModel(modelId!, { version_id: versionId, width_mm: widthMm, height_mm: heightMm, quantity }),
  })

  // ... 渲染物料/人工/制造费三块

  // 「为本模型单独设固定时薪」按钮 → 弹 Modal → 写 cost_rate_master scope=model
  // 「为本模型单独设费率」按钮 → 同上

  return (...)
}
```

### 3.4 数据来源徽章规范（统一 UI 语言）

| 徽章 | 含义 | rate_source 值 |
|---|---|---|
| 🟢 | 物料级精确（每物料独立配置）| material_master |
| 🔵 | Hub 命中（model / category / cost_center）| hub_model / hub_category / hub_cost_center |
| ⚪ | Hub 全局兜底 | hub_global |
| ⚫ | 硬编码兜底（hard_fallback 0.30 / metadata 快照）| metadata / hard_fallback |
| ⚠️ | 未配置 → 用 0 | missing |

### 3.5 「为本模型单独设」按钮的实现

点按钮 → 弹 Modal：
- 输入：rate 值
- 提交：POST `/api/v1/long-tail-strategies/`（已存在），body 含：
  - `rate_type`: `labor_per_minute` 或 `overhead_rate`
  - `scope_type`: `model`
  - `scope_id`: `modelId`
  - `category`: 调用 `_synthesize_category_for_hub('labor_per_minute', 'model', modelId)`（参考 long_tail_strategy_service.py:240）
  - `rate`: 用户输入
  - `source`: `manual_model_override`
  - `enabled`: true
- 提交成功 → invalidateQueries(['cost-preview']) → Tab 自动刷新

### 3.6 验收

- ✅ 抽屉 Tab 切到「成本核算」立刻看到 KB8 的物料/人工/制造费三层
- ✅ 每层有数据来源徽章（🟢/🔵/⚪/⚫/⚠️）
- ✅ 改宽/高/数量 → 点刷新 → 三层数字立刻变
- ✅ 点「为本模型单独设固定时薪」→ 输入 0.99 → 提交 → 人工成本立刻按 0.99 重算 + 徽章变 🔵 hub_model
- ✅ 改完后再删除 model 层覆盖（Hub 管理页）→ 回到 cost_center 层

---

## 4. 验收（必跑，缺一不可）

### 4.1 后端
```bash
cd /home/admin/ai-costing-system/backend
source venv/bin/activate
pytest tests/services/test_compute_process_costing_hub_labor.py -v
pytest tests/ -k "not slow"  # 全套回归
```

### 4.2 前端
```bash
cd /home/admin/ai-costing-system/frontend
npm run build  # 必须 0 type error
```

### 4.3 部署到生产（自主完成，不问用户）

```bash
# 1. 后端：alembic upgrade head（本轮无新 migration，应该是 noop，确认即可）
cd /home/admin/ai-costing-system/backend
source venv/bin/activate
alembic upgrade head

# 2. 前端：build + deploy
cd /home/admin/ai-costing-system/frontend
npm run build
bash deploy_static.sh   # 或者参考 task_log.md 的部署命令

# 3. 后端重启（千万不要用 kill -HUP！uvicorn 默认会终止）
#    用 Path A 第一次部署的方式：systemctl 或者 nohup 重启
#    （task_log.md 里有标准命令）
```

### 4.4 真机验证（在生产 https://work.znma.com）
- 打开 https://work.znma.com/costing/standard-models
- 找到 KB8（转印包边垫类）
- 点开抽屉 → 切到「成本核算」Tab
- 截图 3 张：
  1. 三层成本默认渲染
  2. 改宽/高/数量后刷新
  3. 「为本模型单独设固定时薪」覆盖前后对比

---

## 5. 输出物（commit + handover）

### 5.1 单 commit 内容
- `backend/src/planner/services/long_tail_strategy_service.py` (+ resolve_labor_rate)
- `backend/src/planner/services/bom_generation_service.py` (G2 + G3)
- `backend/tests/services/test_compute_process_costing_hub_labor.py` (新增)
- `frontend/src/components/costing/CostingTab.tsx` (新增)
- `frontend/src/components/costing/ProductModelEditorDrawer.tsx` (加 Tab)
- `frontend/src/services/planner.ts` (如果加新 endpoint)
- `DOC/costing/handovers/tdabc_v1_handover_20260512.md`（新增 handover，下面 §5.2）

### 5.2 Handover 文档（必写）

**路径**：`DOC/costing/handovers/tdabc_v1_handover_<YYYYMMDD>.md`

**结构**：
```markdown
# TDABC v1 闭环 Handover (<日期>)

## 0. 摘要
- Brief: tdabc_v1_closing_loop_brief.md
- 工时: 实际 X 小时（计划 2 天）
- Commit: <hash>
- 部署: ✅ 已部署生产 https://work.znma.com

## 1. G — A2 接通
- resolve_labor_rate 函数: long_tail_strategy_service.py:<line>
- _compute_process_costing 改造: bom_generation_service.py:<line>
- 测试: test_compute_process_costing_hub_labor.py（4 用例全绿）

## 2. H — 成本核算 Tab
- CostingTab 新组件: components/costing/CostingTab.tsx
- 抽屉集成: ProductModelEditorDrawer.tsx:3018 起
- API: GET /api/v1/product-models/{id}/cost-preview（复用 / 新增）

## 3. 真机验证截图
[贴 3 张截图或描述]

## 4. 已知限制 / 留给 v2 的事
- 仍未做：设备小时折旧、换型成本、销量摊销层（POD 行业 3 件事）
- 仍未做：SKU 角色、cost_snapshot、月度差异
- 这些都在 costing_methodology_industry_alignment.md §5 v2/v3 路线里

## 5. 下个 Agent 接力提示
- 看完 costing_methodology_industry_alignment.md 再开 v2 brief
- 不要给我看 SAP CO 的方案
```

### 5.3 同时更新（不另外开 commit，合并到本次 commit）
- `DOC/agents/task_log.md` 加 1 行
- `DOC/costing/handovers/system_capability_inventory.md` 把 G + H 标 ✅
- `DOC/agents/state.md` 更新当前阶段

---

## 6. 自主权限边界

### 6.1 你完全可以自主决定的
- 实现细节（变量命名、文件拆分粒度、UI 组件用 Card vs Descriptions）
- 新建辅助函数和工具方法
- 测试用例数量（4 个起，更多更好）
- handover 文档格式细节
- commit message 风格（建议 `feat(costing): TDABC v1 闭环 — A2 接通 + 成本核算 Tab`）

### 6.2 必须遵守的
- ❌ **不要扩范围**：不做 SKU 角色、不做 cost_snapshot、不做 5 损益分类、不做 POD 3 件事
- ❌ **不要破坏现有 preview_model_cost API 调用方**（KB8 现有抽屉还得正常工作）
- ❌ **不要给 process_lines 删除原有字段**（向后兼容）
- ❌ **不要 git push --force / git rebase / 改 git config**
- ❌ **不要用 `kill -HUP` 重启 uvicorn**（会终止服务，用 systemctl 或 nohup 重启）
- ✅ **必须真机验证**（https://work.znma.com 真打开看，不要只跑测试就汇报）
- ✅ **必须写 handover 文档**

### 6.3 遇到这些情况停下来问派单人（极少数情况）
- preview_model_cost 改造影响 > 3 个调用方
- 发现 cost_rate_master 表结构有重大缺陷（缺字段）
- 发现 KB8 没有 cost_center_id 关联（process 表里 cost_center_id 全 NULL）→ 这种情况说明 Path A subagent 没真做完，需要先补 process.cost_center_id 数据再继续
- 单个文件改动 > 500 行 → 先停下来确认拆分

---

## 7. 完成定义（DOD）

✅ 所有 backend 测试绿（包括新加的 4 个 + 全套回归）
✅ 前端 build 0 type error
✅ 部署到生产成功（curl health 200）
✅ 真机打开 KB8 抽屉「成本核算」Tab 三层数字渲染正常
✅ 「为本模型单独设固定时薪」按钮可以工作
✅ 单 commit 推到 origin/main
✅ Handover 文档写完
✅ task_log.md / system_capability_inventory.md / state.md 同步更新

**完成后**：在 handover 里加一句 `@CostingHubAgent: TDABC v1 闭环完成，等你接力 v2 POD 3 件事 brief`

---

## 8. 文档关系（再读一遍）

| 必读 | 文档 |
|---|---|
| 🟥 必读 | `DOC/costing/blueprints/costing_methodology_industry_alignment.md`（行业方法论）|
| 🟥 必读 | `DOC/costing/handovers/path_a_handover_20260510.md`（Path A 上下文）|
| 🟦 参考 | `DOC/costing/blueprints/cost_rate_hub_design_v1.md` v1.3（Hub 4 层 resolve）|
| 🟦 参考 | `DOC/costing/blueprints/finance_to_costing_c1_contract_v1.3_aligned.md`（finance 数据）|
| 🟦 参考 | `DOC/agents/briefings/path_a_real_data_wiring_v1.md`（Path A brief）|

---

**End of Brief**
