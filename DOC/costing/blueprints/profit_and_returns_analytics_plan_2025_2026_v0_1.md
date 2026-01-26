# 数据分析方案：利润与售后退货（2025 仅分析 / 2026 扣库落库）v0.1

> 目标：在不依赖聊天历史的前提下，给出可落地的 ERP 级分析方案，并与现有“发货时再解析 → BOM 快照/异常队列”主链兼容。
>
> 关键约束（已确认）：
> - **2025 年**：需要“扣库相关数据/流水/结存/对账”，但**不要求每条发货行落一条 BOM 快照（trace_json）**；成本/用量可运行时计算，并将**扣库凭证（轻量结果）**落库即可（不落大快照）。
> - **2026 年**：在 2025 的扣库闭环稳定后，再完善“冲销/返库/报废语义 + 成本策略（移动平均/批次成本等）”。

## 1. 背景与现状（仓库证据）

- 主链蓝图：`DOC/costing/blueprints/sku_binding_bom_shipment_plan.md`
- 发货导入样例提炼：`DOC/index/extracted/shipment_xlsx_extracted_20251222T000000+0800.md`
- 售后表格提炼：`DOC/index/extracted/after_sales_xlsx_extracted_20260125T000000+0800.md`

现状（已走通的能力）：产品模型/商品关联/SKU 绑定/规格解析/发货导入/BOM 快照/异常队列。

## 2. 分析要回答的问题（ERP 视角）

### 2.1 利润（每日/每月）

必须支持维度：
- 时间：日 / 月（以完成时间 completed_at 作为归属期口径，和发货主链一致）
- 货品：按 **SKU 主键**（优先货品条码；若售后缺条码则退回“货品编号”作为分析键）
- 模型：按绑定到的 **已发布标准版本 / 模型** 聚合（从 BOM 快照 trace 回填）
- 渠道：销售渠道

核心指标：
- 销售额（revenue）
- 销量（qty）
- 成本（cogs）
- 毛利（gross_profit）
- 毛利率（gross_margin）

### 2.2 退货率（每货品/每模型）

必须支持维度：
- 时间：日 / 月（以售后单完成时间/创建时间为归属期；若缺失则以导入时间兜底并标记）
- 货品：同上（SKU/货品编号）
- 模型：能关联到发货行或 BOM 快照时才可统计“模型退货率”，否则落入“待关联”异常队列
- 渠道、原因：销售渠道、退换原因

核心指标：
- 退货率（按件）= 退货数量 / 发货数量
- 退货率（按金额）= 退货金额 / 发货金额
- 退货原因分布
- 退货时滞（如具备“原订单/发货时间”可计算）

## 3. 2025：扣库但不落快照（轻量结果） + 校准 Run（解决“不断调参校准”）

> 2025 的目标不是“一次算对”，而是通过多次试算把“物料用量/损耗/工时/费率”的口径校准到业务认可，并沉淀到模型版本。

### 3.1 核心原则（更新：与“2025 不落快照但要扣库”一致）

- **输入数据只读**：发货行/售后行不回写（保持可追溯）。
- **扣库要落库**：为结存/对账需要落库存扣减流水（或等价凭证）。
- **不强制落 BOM 快照**：不为每条发货行持久化 `bom_snapshots.trace_json`；如需追溯，优先走“轻量结果字段 + 版本归因”而不是大 trace。
- **每次试算都产出一个 Run**：可以随时切换 Run 查看报表；Run 之间可做差异对比。
- **调参不直接改历史结果**：调参只影响“新 Run 的计算结果”。

### 3.2 Run 里允许调哪些参数（分层管理）

1) **版本层（沉淀口径）**：模型版本清单/工序步骤的本品用量、损耗%、工时参数等（用于最终固化）。
2) **Run 参数集层（快速试算）**：
   - 人工分钟单价倍率（全局或按渠道/工序组）
   - 工时倍率（按工序/工艺模块/模型）
   - 损耗倍率（按物料/计量方式/模型）
   - 制造费比例、管理费比例（如果你们要在 2025 也看“完整成本”）
3) **小范围覆盖（谨慎使用）**：对少量异常 SKU/模型单点修正（必须可解释、可审计）。

### 3.3 “切换版本试算”怎么做（不污染生产绑定）

建议引入 **分析绑定**（仅在 run_id 作用域内生效）：
- 生产绑定：SKU → published standard version（现有主链口径，不动）
- 分析绑定：`run_id + sku_key → version_id`（用于对比 V1/V2/V3 在 2025 的表现）

### 3.4 轻量结果（扣库凭证）建议（替代“每行快照落库”）

> 目的：满足“2025 要扣库，但不落每条发货行的 BOM 快照”的诉求。

建议引入（命名可调整）：
- `shipment_costing_results`（或 `shipment_deduction_results`）：
  - 主键：`shipment_line_id`
  - 关键归因：`model_version_id`（必须落，否则版本变化后无法解释历史扣库）
  - 关键口径：`spec_hash` / `parser_version` / `computed_at`
  - 结果字段：`cost_total`（可选分段：material/process/overhead）
  - 关联：`deduction_job_id`（一次批处理 ID，便于对账与回滚）
- `inventory_transactions`（若库存域已实现）：按“物料/单位/数量/批次/仓库”记录扣减流水；`shipment_line_id` 作为来源外键。

说明：
- 若库存域暂未实现，可先落 `shipment_costing_results`，并把“物料扣减明细”作为可选字段（例如 JSONB）或延后到库存域落地时再拆表。

## 4. 数据摄取（Import）与事实表（Fact）建议

### 4.1 售后导入（新增）

来源：`售后退货明细账.xlsx`（字段提炼见 extracted 文档）。

建议新增表（类比 shipments import）：
- `after_sales_import_batches`
- `after_sales_lines`
- `after_sales_exception_queue`（重点：缺关键字段/关联失败/歧义冲突）

字段最小集（以当前表头为准）：
- `after_sales_no`（退换补发单号）
- `channel`（销售渠道）
- `reason`（退换原因）
- `product_code`（货品编号）
- `product_name`（货品名称）
- `spec_text`（规格）
- `sale_unit_price`（销售单价）
- `return_qty`（退货数量）
- `refund_amount`（退货金额）
- 可选留痕：`customer_account`、`actual_return_qty`、`return_discount`、`allocated_amount`、`allocated_refund_amount`、源表 `gross_profit/gross_profit_rate_pct`

幂等策略建议：
- 文件级：`file_hash = sha1(xlsx_bytes)`
- 行级：`external_line_key_hash = sha1(after_sales_no|channel|product_code|spec_text|return_qty|refund_amount)`

### 4.2 关联策略：售后行 ↔ 发货行（多策略，带置信度）

现实约束：当前售后表不包含“发货单号/原订单明细ID”。因此关联必须“可解释+可回放+可人工兜底”。

建议输出一个 `after_sales_match_snapshot`（或在 after_sales_lines 中记录关联结果）：
- `matched_shipment_line_id`（可空）
- `match_method`：`exact`/`heuristic`/`manual`
- `match_confidence`：0~1
- `match_explanation`：命中理由（例如：同渠道+货品编号+规格+金额+时间窗）

匹配候选键（由强到弱）：
- P0：若后续表格补齐“原订单行ID/原发货明细ID”→ 直接用
- P1：`channel + product_code + spec_text + sale_unit_price`（必要时加数量）
- P2：`channel + product_code + spec_text`（时间窗兜底）
- P3：`product_code + spec_text`（仅用于“退货率按货品编号”统计，不用于模型归因）

### 4.3 事实表与预聚合（提高查询性能）

建议新增（或用视图/物化视图）：
- `fact_shipments`：从 `shipment_lines + bom_snapshots` 抽取分析字段
- `fact_returns`：从 `after_sales_lines + match_snapshot` 抽取分析字段
- `fact_profit_daily` / `fact_profit_monthly`（可选）：按日/月预聚合（sku_key/model/channel）
- `fact_returns_daily` / `fact_returns_monthly`（可选）

## 5. 成本口径（2025 当前价估算）与可解释性

2025 成本口径建议：
- **COGS = BOM 快照展开的物料成本 +（可选）工序人工 +（可选）制造费**
- 价格策略：**按当前价估算**（必须在结果中写 `price_strategy=current`，避免误解为财务结算数）

可解释性（必须做）：
- 任意报表指标可下钻到：
  - 发货行（shipment_line）
  - BOM 快照（bom_snapshot，含 trace）
  - Run 信息（run_id、版本/参数集、override 明细）

## 6. 2026：扣库落库（在 2025 分析稳定后再做）

2026 的核心变化：
- 引入库存域（inventory_transactions / balances / deduction_jobs）
- 售后导致冲销（reverse) / 返库（如业务允许再售）/ 报废（不可再售）三类语义
- 成本口径从“当前价估算”升级为“扣库成本”（移动平均/批次成本等，视你们库存策略）

## 7. MVP 交付清单（建议拆两轮闭环）

### 闭环 A（2025：售后导入 + 退货率）
- 导入售后 xlsx → 落库 → 幂等 → 异常队列
- 报表：SKU/货品编号退货率（按日/月、按渠道、按原因）
- 关联：先做 P1/P2，无法关联到发货行则只做“货品维度退货率”，并入异常队列等待补键

### 闭环 B（2025：利润 Run + 校准）
- 引入 `costing_runs`（run 参数集、分析绑定）
- 利润报表（SKU/模型/渠道 日/月）
- Run 对比（Run A vs Run B 差异：来自哪个版本/参数/工时/损耗）

## 8. 验收（文档闭环）

- `grep -nF \"数据分析方案：利润与售后退货（2025 仅分析 / 2026 扣库落库）\" DOC/costing/blueprints/profit_and_returns_analytics_plan_2025_2026_v0_1.md`

