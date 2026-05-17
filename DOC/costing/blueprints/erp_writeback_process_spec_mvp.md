# ERP 回传（Write-back）MVP：把“可生产的工艺/规格”回写到 ERP

## 0A. 与 2026-05-16 v3 口径对齐

本文件是早期反写蓝图，字段名需要按当前 `jackyun_erp_goods_master_sync_backlog.md` §15 解释：

- 系统侧可执行工艺说明统一叫 `production_process`（Phase0 / 代码侧沿用）。本文历史名 `process_instructions_text` 只作语义别名。
- 吉客云 ERP 货品档案反写目标是 `工艺说明(规)`，同步镜像落 `metadata.erp.process_instructions_reg`。
- 禁止把 ERP 同步下来的 `工艺说明(规)` 反灌覆盖 `production_process`；`production_process` 是我方源，`process_instructions_reg` 是 ERP 端镜像。
- 网店商家编码 / 模型编码统一叫 `shop_spec_code`，反写到 ERP `outSkuCode`，同步镜像落 `out_sku_code`。

## 0. 背景（为什么必须回传）

- ERP 的“交易规格/商品规格”是面向交易展示的文本，**不等于可生产的工艺单**（对工人不可直接执行）。
- 我们系统在“SKU + 规格解析 + 已发布标准模型 + 行级变体”基础上，会生成**可追溯的生产工艺/用料/尺寸摘要**。
- 因此需要把关键结果**回写到 ERP 的专用字段**（或生成 ERP 可导入的表），让 ERP 侧能直接驱动生产与对账。

## 1. 回传写到哪里（写回对象）

按业务优先级从高到低：

1) **发货/订单明细行（强烈推荐）**
   - 目标：每一条实际要生产/发出的行，写回“生产规格/工艺说明/追溯ID”
   - 好处：最贴近实际交易与生产，最不容易产生错配

2) **SKU 主档（可选）**
   - 目标：为 SKU 沉淀“默认生产说明/默认模型提示”
   - 注意：SKU 主档适合放“默认值/提示”，但交易规格变化时仍应以明细行为准

3) **生产工单/生产单（如果 ERP 有该对象）**
   - 目标：把工艺说明直接挂到工单，工人只看工单即可

## 2. 回传字段清单（MVP 必须 / 建议）

### 2.1 必须字段（最低可用闭环）

**业务可读字段（给工人/现场）**
- `production_spec_text`：生产规格（结构化摘要拼成一段可读文字）
- `process_instructions_text`：工艺说明（可执行步骤/注意事项）

**追溯字段（给系统/审计）**
- `costing_trace_id`：我方生成的追溯ID（建议 = `bom_snapshot.id` 或 `shipment_line.id + revision`）
- `model_code`：标准模型编码（用于人工定位）
- `version_label`：版本号/版本标签（用于人工定位）
- `spec_hash`：交易规格 hash（用于幂等/重跑）

### 2.2 建议字段（提升可操作性）

- `dimensions_text`：尺寸摘要（如 `50×140cm`、面积/周长）
- `materials_pick_summary`：领料摘要（面向仓库/领料，MVP 可只写关键物料+用量）
- `quality_notes`：质检/颜色/包边/孔位等关键提示

## 3. 字段放在 ERP 的什么位置（强制“专用字段”，不污染原字段）

原则：
- **不覆盖** ERP 的 `交易规格`/`商品规格` 原字段（这些是交易原始事实）
- 回写必须落到 ERP 的 **自定义字段/备注字段/扩展字段**，例如：
  - 订单明细行：`自定义字段1/2/3`、`生产备注`、`工艺说明` 等
  - SKU 主档：`自定义属性`、`扩展描述`

如果 ERP 字段数量有限（比如只有 1 个备注字段）：
- MVP 先把 `process_instructions_text + production_spec_text` 合并为一段（带清晰分隔符）
- `costing_trace_id/spec_hash/model_code/version_label` 以短前缀方式放在末尾，便于检索

## 4. 回传触发时机（何时写回）

### 4.1 发货导入触发（推荐默认）

当我们在发货导入链路中生成了 `bom_snapshot`（成功）：
- 立刻生成 `production_spec_text/process_instructions_text`
- 入库我方“回传任务”（异步队列/作业表）
- 回传成功后在我方记录 `writeback_status=success`，失败进入异常队列可重试

### 4.2 重新计算触发（规格变化/模型更新）

当发现 `spec_mismatch=true` 或用户手工重绑/重算：
- 生成新快照（新 `costing_trace_id`）
- 触发“回传更新”（必须幂等）

## 5. 幂等与治理（避免重复写、避免写错）

### 5.1 幂等键（建议）

- 订单明细行回传：`external_line_key_hash + spec_hash + version_id`
- 或者 ERP 提供的 `line_id` + 我方 `snapshot_revision`

### 5.2 不覆盖原则

- 若 ERP 明细行已经被人工修改过工艺字段，必须有“锁定/不覆盖”策略（MVP 可先不覆盖）

### 5.3 写回历史

我方应落库写回历史（MVP 可简化为一张表）：
- `target_system`（ERP）
- `target_object_type`（order_line/sku/work_order）
- `target_object_key`
- `payload_json`（写回内容）
- `status/attempts/last_error`
- `idempotency_key`

## 6. 需要 ERP/吉客云支持的能力（你拿去谈判）

至少满足其一：

### 方案A：提供 API（最佳）
- 更新订单明细行自定义字段/备注字段（按 `line_id` 或可唯一定位的键）
- 支持批量更新（强烈建议，减少限流压力）

### 方案B：提供“可导入的模板”（无 API 也能落地）
- 允许我们导出一个 Excel/CSV，ERP 支持导入更新到订单明细行的自定义字段
- 必须支持：按唯一键（如发货单号+行号/外部明细ID/货品条码+时间）定位更新

### 方案C：webhook/回调（可选增强）
- 订单/发货完成事件回调，减少轮询

## 7. MVP 交付边界（建议）

本轮只做：
- 生成 `production_spec_text/process_instructions_text`（最小但可用）
- 写回对象优先：**订单明细行**（若无 API 则先导出“ERP 可导入表”）
- 严格幂等、写回历史可追溯


