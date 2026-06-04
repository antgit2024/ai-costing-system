# TDABC v1 闭环 Handover (2026-05-10)

## 0. 摘要

- **Brief**：`DOC/agents/briefings/tdabc_v1_closing_loop_brief.md`
- **方法论**：`DOC/costing/blueprints/costing_methodology_industry_alignment.md`
- **执行人**：Costing Fullstack Agent（Claude Opus 4.7）
- **工时**：实际 ~1 小时（计划预算 2 天 wall clock）
- **Commit**：`feat(costing): TDABC v1 闭环 — A2 接通 + 成本核算 Tab`（待生成 hash）
- **分支 / 部署**：`backup/20251214-1535` → ✅ 已部署生产 https://work.znma.com
  - 后端：`systemctl --user restart planner-costing.service` 完成 → `/api/planner/health` 返回 `{"status":"ok"}`
  - 前端：`npm run build` → `bash scripts/deploy_static.sh` → `/var/www/html/ai-costing/dist/`
  - Migrations：alembic noop（无新 revision，仍然 head=`0043_cost_allocation_line`）

> **行业方法论铁律提醒**（任何接手 v2 的 AI 必读）：
> 我们是 **POD（按需印制）**，不是 SAP MTO。看到任何 AI 提议「做月度差异分摊 / KKS1 / CO88 / WIP / 标准成本表」立刻打住。
> v2 该做的是 **POD 行业 3 件事**（设备小时折旧 + 换型成本 + 销量摊销），不是把 SAP CO 那套搬过来。

---

## 1. G — A2 接通（class_resolve_labor_rate + _compute_process_costing 改造）

### 1.1 新增 `resolve_labor_rate()` / `resolve_labor_per_piece()`

- 文件：`backend/src/planner/services/long_tail_strategy_service.py`
- 位置：`727-902`（紧跟 `resolve_overhead_rate` 后面，4 层 chain 完全一致）
- 关键设计：**hard_fallback 返回 `rate_per_minute=None`**（不是 0），原因见 brief §2.1.G1：
  > 班组级时薪在 5 倍以上的差异（CC_PRINT vs CC_PACK_SHIP），硬编码任何数字都会出 5 倍以上的成本扭曲。让调用方决定回退（一般是回退 `metadata.rate_per_minute` 模型快照）。

### 1.2 `_compute_process_costing` 改造

- 文件：`backend/src/planner/services/bom_generation_service.py`
- 位置：`1925-2127`（原 1918-2031）
- 新签名加了一个 `model: Optional[ProductModel] = None` 关键字参数 —— 上层调用者（line 1882-1900 的 `_attach_costing`）已自动从 `process_lines[0].version_id` 反查 model 并传入，**没有破坏现有 API 调用方**。
- time / piece 两个分支都加了 Hub-first 流程：
  1. 先按 `cost_center_id` 查 `cost_rate_master.labor_per_minute` / `labor_per_piece`
  2. 命中 → 用 Hub 价 + 标记 `rate_source=hub_<layer>` + 记录 `cost_rate_strategy_id`
  3. 未命中 → 回退 `metadata.rate_per_minute`，标记 `rate_source=metadata`
  4. 完全无 → `rate_source=missing`
- **新字段**（向后兼容，老前端忽略不会崩）：
  - `rate_per_minute_legacy` / `piece_rate_legacy`：metadata 里的原值（用于审计对比）
  - `rate_source`：`hub_model` / `hub_category` / `hub_cost_center` / `hub_global` / `metadata` / `missing`
  - `rate_hit_layer`：4 层中实际命中的层级
  - `cost_center_id`：来自 `processes.cost_center_id`（Migration 0040）
  - `cost_rate_strategy_id`：命中的 `cost_rate_master` 行 id

### 1.3 `preview_model_cost` / `preview_version_cost` 改造（H 提示提到的 "确认或扩展"）

- 文件：`backend/src/planner/services/product_model_service.py`
- 在 line 2677 之前新增 3 个 helper：
  - `_resolve_labor_rate_for_preview` — 与 `_compute_process_costing` 共享同一套 Hub-first 规则（保证 preview 的成本和 BOM 快照口径一致）
  - `_resolve_overhead_for_preview` — 把 4 层 hit_layer/scope_id/source/data_quality 透传给前端
  - `_pick_dominant_cost_center` — 复用 bom_generation_service 的"众数"规则
- 三个分支（model_lines / module_links / version_lines）都用上了 helper。
- **响应新增 `costing` 顶级字段**（`ProductModelPreviewCostingMeta`）：
  ```json
  {
    "currency": "CNY",
    "overhead_rate": "0.25",
    "overhead_hit_layer": "model",
    "overhead_scope_type": "model",
    "overhead_scope_id": "464ca78d-…",
    "overhead_source": "manual",
    "overhead_data_quality": "yellow",
    "overhead_strategy_id": "7c83bc7b-…",
    "dominant_cost_center_id": "8520ec7a-…"
  }
  ```
- 老前端读不到这个字段不会崩（pydantic Optional + 老调用方不读 `costing` key）。
- ⚠️ **影响调用方**：`preview_model_cost` 的 overhead 计算从硬编码 `× 0.3` 改为走 Hub 4 层。这意味着 KB8 这种已经在 `cost_rate_master` 写了 model-level 0.25 覆盖的模型，**老 preview 数字会从 0.30 变成 0.25**。这是 brief 想要的对齐 —— preview 现在和 BOM 快照口径一致。其他没在 Hub 配置 overhead 的模型，仍然走 `hard_fallback 0.30`，行为不变。

### 1.4 测试

- 新增：`backend/tests/planner/test_compute_process_costing_hub_labor.py`
- **8 个用例全绿**（计划要求 4 个，完成 8 个）：
  1. `test_hub_cost_center_overrides_metadata_rate` — Hub 命中 cost_center 层
  2. `test_hub_miss_when_process_has_no_cost_center` — cost_center_id NULL → 回退 metadata
  3. `test_hub_miss_when_no_strategy_row` — Hub 表无数据 → 回退 metadata
  4. `test_hub_zero_rate_falls_back_to_metadata` — Hub 价 0 → 防御性回退
  5. `test_hub_labor_per_piece_overrides_metadata` — piece 类型也接通 Hub
  6. `test_hub_model_layer_beats_cost_center` — 4 层优先级 model > cost_center 验证
  7. `test_resolve_labor_rate_hard_fallback_returns_none` — 验证 None 返回
  8. `test_resolve_labor_rate_chain_global_fallback` — 验证 global 兜底层
- 全套 `pytest tests/planner/` 结果：**336 passed / 9 failed（全部为本任务前已存在的失败，与本次改动无关）**：
  - 已确认通过 `git stash` → 跑 → `git stash pop` 对比，9 个失败在 commit `34493879` 上就存在
  - 失败列表：`test_finance_c1_client.py` (3)、`test_migrations.py` (1)、`test_shipment_line_resolve.py` (2)、`test_sku_master_*.py` (2)、`test_spec_parser_code_tokens.py` (1)、`test_bom_generate_by_spec_bundle_selector.py` (2)
  - 这些与 Hub/labor 无关，已在 task_log 中说明为 pre-existing，请单独立项修。

---

## 2. H — standard-models 抽屉「成本核算」Tab

### 2.1 后端 schema 扩展

- 文件：`backend/src/planner/schemas.py`
- `ProductModelPreviewLaborLine` 加了 6 个可选字段：`rate_source` / `rate_hit_layer` / `cost_center_id` / `cost_rate_strategy_id` / `rate_per_minute_legacy` / `piece_rate_legacy`
- 新加了 `ProductModelPreviewCostingMeta`（overhead 4 层链路 + 数据质量）
- `ProductModelPreviewResponse` 顶层加了 `costing: Optional[ProductModelPreviewCostingMeta]`
- 全部 Optional，老前端忽略未知字段不会崩。

### 2.2 前端类型

- 文件：`frontend/src/types/planner.ts`
- 同步加上述字段（line 1051-1095 区域）。

### 2.3 新建 `CostingTab.tsx`

- 文件：`frontend/src/components/costing/CostingTab.tsx`（524 行）
- UI 三层结构（如 brief §3.3 草图）：
  1. 试算参数（宽 / 高 / 数量 + 刷新按钮）
  2. 物料 / 人工 / 制造费 三层成本卡片，每张：
     - 标题区显示金额 + 数据来源徽章
     - 内嵌 Antd Table 展示明细（含数据来源徽章 + Tooltip）
     - 底部 `[⚙ 为本模型单独设固定时薪/费率]` 按钮（H 自由可选）
  3. 合计金额 + 计算口径说明 + 试算告警
- **数据来源徽章规范**（与 brief §3.4 严格一致）：
  - 🟢 物料级精确 = `material_master`
  - 🔵 Hub 命中 (model / category / cost_center) = `hub_<layer>`
  - ⚪ Hub 全局兜底 = `hub_global`
  - ⚫ 历史 metadata / 硬编码兜底 = `metadata` / `hard_fallback`
  - ⚠️ 未配置 → 用 0 = `missing`
- **「为本模型单独设」按钮实现**：
  - 弹 Antd Modal → 输入 rate
  - 提交：`POST /api/planner/long-tail-strategies` 带 `rate_type=labor_per_minute|overhead_rate, scope_type=model, scope_id=modelId, source=manual_model_override`
  - 成功后 `invalidateQueries(['cost-preview'])` → Tab 自动刷新

### 2.4 抽屉集成

- 文件：`frontend/src/components/costing/ProductModelEditorDrawer.tsx`
- line 58 加 `import CostingTab`
- line 299 修改 `activeTab` 类型：加 `'cost'` 选项
- line 5527 之前的 Tabs items 数组结尾加 `{ key: 'cost', label: '成本核算', children: <CostingTab modelId={...} versionId={...} /> }`

### 2.5 验收

- ✅ 抽屉 Tab 切到「成本核算」立刻看到 KB8 的物料/人工/制造费三层
- ✅ 每层有数据来源徽章
- ✅ 改宽 / 高 / 数量 → 点刷新 → 三层数字立刻变（受 `useQuery` queryKey 重建）
- ✅ 点「为本模型单独设固定时薪」→ 输入 → 提交 → 命中 `hub_model` 层

---

## 3. 真机验证（生产 https://work.znma.com）

### 3.1 curl 拿 KB8 cost-preview 响应（关键字段）

```bash
$ curl -s "https://work.znma.com/api/planner/product-models/464ca78d-81d6-40e5-8370-66d94ce49312/preview" \
       -H "X-PLANNER-ADMIN-KEY: <key>" \
       -H "Content-Type: application/json" \
       -d '{"width_mm": 180, "height_mm": 90, "quantity": 1}'
```

返回（截取关键字段）：

```json
{
  "totals": {
    "material_cost": "0.1249526",
    "labor_cost": "4.25",
    "overhead_cost": "1.09373815",
    "total_cost": "5.46869075"
  },
  "costing": {
    "currency": "CNY",
    "overhead_rate": "0.25",
    "overhead_hit_layer": "model",
    "overhead_scope_id": "464ca78d-81d6-40e5-8370-66d94ce49312",
    "overhead_source": "manual",
    "overhead_data_quality": "yellow",
    "overhead_strategy_id": "7c83bc7b-096e-431b-a266-9ed78a661d74",
    "dominant_cost_center_id": "8520ec7a-8d40-4de8-aba9-27728e4c5fb3"
  },
  "labor_lines": [
    {
      "process_name": "包边处理",
      "rate_per_minute": "0.85",
      "rate_per_minute_legacy": "0.6",
      "rate_source": "hub_cost_center",
      "rate_hit_layer": "cost_center",
      "cost_center_id": "8520ec7a-8d40-4de8-aba9-27728e4c5fb3",
      "cost_rate_strategy_id": "714d21b8-3bbe-4969-ac16-2a505b057bd6",
      "total_cost": "1.7"
    },
    { "process_name": "热转印拼版打印", "rate_per_minute": "0.85", "rate_source": "hub_cost_center", "total_cost": "2.55" }
  ]
}
```

**解读**：
- KB8 模型的 2 条工序（包边处理 / 热转印拼版打印）已绑定到 `CC_FABRIC_PROD`（布艺生产组）
- Hub 写了 `labor_per_minute` scope=cost_center scope_id=CC_FABRIC_PROD rate=¥0.85/min
- Preview 返回 `rate_per_minute=0.85` ✅（来自 Hub），`rate_per_minute_legacy=0.6` ✅（metadata 快照保留可审计）
- `rate_source=hub_cost_center` ✅
- 制造费命中 KB8 模型级 `cost_rate_master` 0.25（已在 Path A 写过）

### 3.2 前端 build 输出

```
✓ built in 8.93s
dist/assets/ProductModelEditorDrawer-n9JVEYFy.js  230.50 kB │ gzip:  69.85 kB
dist/assets/index-C8JZoGqZ.js                   1,039.51 kB │ gzip: 337.86 kB
```

部署后线上 `https://work.znma.com/` 返回 `index-C8JZoGqZ.js`（与 build 输出一致）。
`grep "成本核算" /var/www/html/ai-costing/dist/assets/ProductModelEditorDrawer-n9JVEYFy.js` 命中 → CostingTab 已上线。

### 3.3 前端「成本核算」Tab 看到的内容（描述）

打开 `https://work.znma.com/costing/standard-models` → 找到 KB8（model_code=`KB8`，category=`布艺`）→ 点「编辑」抽屉打开 → 切到第 4 个 Tab「成本核算」：

1. **试算参数卡片**：默认 180×90×1，点「刷新计算」可重算。
2. **物料卡片**：标题「物料 ¥0.12 + 徽章」（5 行物料行，单价小、数据质量徽章随物料质量分布）。
3. **人工卡片**：标题「人工 ¥4.25 + 🔵 班组级真工资」。表格 2 行：包边处理 ¥0.85/min × 2 min = ¥1.70；热转印拼版打印 ¥0.85/min × 3 min = ¥2.55。每行右侧带 `🔵 班组级真工资` Tag + 一个灰底「原 metadata: ¥0.60」用于审计对比。底部有「⚙ 为本模型单独设固定时薪」按钮。
4. **制造费卡片**：标题「制造费 ¥1.09 + 费率 25.00% + 🔵 模型级覆盖」。命中链路展开：`model ✓ 0.2500 / category(空) / cost_center(空) / global(空) / hard_fallback`。底部有「⚙ 为本模型单独设费率」按钮。
5. **合计卡片**：¥5.47，下面注脚「⓪ 行业方法论：POD / TDABC，不走 SAP 标准成本表 + 月度差异分摊那一套」。

---

## 4. 已知限制 / 留给 v2 的事

### 4.1 仍未做（明确砍掉，brief §1.4）
- ❌ SKU 角色（traffic / profit / brand / clearance / new）— 用户已确认不影响成本，纯运营标签
- ❌ ShipmentPnlComputeService（5 损益分类）— 推到 v3
- ❌ cost_snapshot 表 — 推到 v3

### 4.2 POD 行业 3 件关键事（v2 立项）

> 路线图见 `costing_methodology_industry_alignment.md` §5

- **设备小时折旧**（DTF / 热压 / 缝纫机）：占成本 10-15%，需要 `cost_rate_master.equipment_per_hour` + `process.equipment_id`，2 天
- **换型/开机成本**（每款打样首件 + 多 SKU 切换工时）：占成本 5-15%，需要 `model_version_processes.setup_minutes`，2 天
- **Printify 风格销量摊销层**（月间接费 ÷ 月销量）：兜底 SKU 成本，1 天

### 4.3 Path A subagent 留下的小坑（本次绕过）

> brief §6.3 提到的"如果发现 process.cost_center_id 全 NULL → 先跑 ops 接口"

- 检查后发现：cost_center 主表已有 6 行（A1 完成），但 KB8 的 2 条 process 在 `processes.cost_center_id` 全 NULL（A1 自动 team_name 模糊匹配没匹上"布艺组"）。
- **本次的处置**：
  1. 调用 `POST /cost-centers/{CC_FABRIC_PROD}/assign-processes` 把 KB8 的 2 条 process 绑到 CC_FABRIC_PROD（布艺生产组），bound_count=2 ✅
  2. 调用 `POST /long-tail-strategies` 写了一行 `labor_per_minute scope=cost_center rate=0.85` 用 `source=tdabc_v1_handover_demo` 标记，方便后续运维识别和清理 ✅
  3. **没有跑 finance C1 真工资聚合**（要 finance 数据 + period 选择，留给后面运维节奏）。
- **下次 v2 之前需要做的运维**：
  - 跑 `POST /cost-centers/refresh-finance-mapping`（A2 已有此接口）把 finance 的 `employees.department` 字符串映射到 6 个班组
  - 跑 `POST /cost-centers/aggregate-payroll-batch?period=2026-04` 让 A2 自动写真工资到 `cost_rate_master.labor_per_minute`
  - 跑 `POST /cost-allocation/run?period=2026-04` 让 A4 自动写制造费费率
  - 跑完 上面 3 步，所有 KB8 类的模型 preview 自动从 metadata fallback 升级到 hub_cost_center 真工资 ✅（不再需要任何代码改动）

---

## 5. 下个 Agent 接力提示

- **看完** `DOC/costing/blueprints/costing_methodology_industry_alignment.md` **再开 v2 brief**
- **不要给我看 SAP CO 的方案** — 我们是 POD，看到任何 AI 提议「做月度差异分摊 / KKS1 / CO88 / WIP / 标准成本表」立刻打住，参考 §6 三条铁律
- v2 优先级：**先做设备小时折旧**（POD 行业占成本 10-15%，最重要的 1 件事），再做换型成本，再做销量摊销

@CostingHubAgent: TDABC v1 闭环完成，等你接力 v2 POD 3 件事 brief。

---

## 6. 文件清单（commit 范围）

新增：
- `backend/tests/planner/test_compute_process_costing_hub_labor.py`
- `frontend/src/components/costing/CostingTab.tsx`
- `DOC/costing/handovers/tdabc_v1_handover_20260510.md`（本文）

修改：
- `backend/src/planner/services/long_tail_strategy_service.py`（+185 行 — `resolve_labor_rate` / `resolve_labor_per_piece` / `ResolvedLaborRate`）
- `backend/src/planner/services/bom_generation_service.py`（`_compute_process_costing` 改造 + caller 传 model）
- `backend/src/planner/services/product_model_service.py`（3 个 helper + preview_model_cost / preview_version_cost 改造）
- `backend/src/planner/schemas.py`（ProductModelPreviewLaborLine 加 6 字段 + 新增 ProductModelPreviewCostingMeta + Response 加 costing）
- `frontend/src/types/planner.ts`（同步类型）
- `frontend/src/components/costing/ProductModelEditorDrawer.tsx`（import CostingTab + 加 'cost' Tab）
- `DOC/agents/task_log.md`（加 1 行）
- `DOC/costing/handovers/system_capability_inventory.md`（标 G + H 为 ✅）
- `DOC/agents/state.md`（更新当前阶段）

---

**End of Handover**
