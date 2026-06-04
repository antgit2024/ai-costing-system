---
rule_id: R-MAT-001
title: 真实物料“用途三选一”口径（直接BOM/条件物料/间接耗材）
status: active
effective_from: 2026-01-12
owner: Rules Agent
updated: 2026-01-13
---

## 适用范围

- 页面：`/costing/materials`（真实物料）
- 影响链路：物料选择器 → 产品模型/工艺模块明细 → BOM 快照/扣库清单 → 成本核算
- 关联 UI“新建指南”：`DOC/costing/manuals/guides/materials_guide.md`

## 问题背景

历史上 UI 同时存在“是否 BOM 物料（is_bom_material）”与“物料用途（本地分类）”等多套入口，容易出现**双控矛盾**，导致：

- 新人不知道“到底该选哪个字段”
- 选择器误过滤（把应出现在主链路的物料藏掉）
- 后续扣库与成本口径漂移，难追溯

## 规则正文（可执行口径）

真实物料的“用途”必须收口为**三选一**，且每个选项有明确语义：

- **直接BOM**：主线扣库/核算物料，稳定进入产品模型/工艺模块 BOM 行。
- **条件物料**：也是 BOM 物料，但仅在满足“订单/批次/组合条件”时才发生（Phase0 先标记与筛选；条件表达式/生效规则属于 Phase1 另开闭环）。
- **间接耗材**：非必选或不稳定直接调用的消耗品（如清洗液、无纺布、焊锡等），通常不建议进入主链路 BOM 明细。

### 落库映射（UI 保存时必须保证一致）

- 选 **间接耗材**：
  - `is_bom_material=false`
- 选 **直接BOM / 条件物料**：
  - `is_bom_material=true`
  - `metadata_json.usage_class` 记录为 `direct` 或 `conditional`（值名以实际实现为准，但必须能区分两类）

### 选择器过滤口径（避免误伤）

所有“新增物料/选择物料”的选择器，仅过滤 **间接耗材**：

- 过滤条件：`usage_class=indirect`
- 禁止：用 `is_bom_material=false` 一刀切过滤（会误伤“条件物料”的未来演进）

## 正例

- 纸箱/包装配件：选择 **条件物料**（是否发生由订单条件决定）
- 主材布料：选择 **直接BOM**
- 清洗液/抹布：选择 **间接耗材**

## 反例

- 把主材布料选成“间接耗材”，导致模型/工艺模块里选不到或被隐藏
- 用 `is_bom_material=false` 过滤选择器，导致未来“条件物料”也被误过滤

## 边界与例外

- Phase0：条件物料仅做标记与筛选，不要求具备可执行条件表达式
- Phase1：若要条件物料真正“按条件生效”，必须另开闭环补齐条件表达式/生效规则与验收用例

## 验收方式（最小闭环）

- 决议留痕存在性（已记录在 Task Log）：
  - `grep -nF "Materials（物料口径）" DOC/agents/task_log.md | head`
- UI 指南一致性（用途三选一存在）：
  - `grep -nF "用途口径（三选一" DOC/costing/manuals/guides/materials_guide.md`

## 变更记录

- 2026-01-12：口径决议落在 `DOC/agents/task_log.md`（Materials 物料口径），本规则页为提炼件（不改变既有口径）。

