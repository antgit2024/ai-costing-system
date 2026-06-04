# 吉客云/ERP 售后/退货（冲销）对接需求表单（v1，谈判用）

> 目的：我们需要把“发货扣料/成本快照”在发生退货/退款/作废/换货/重发时做**可追溯的冲销与对账**。  
> 关键原则：必须能把售后明细行**稳定映射回原始发货/订单明细行**（否则无法准确冲销）。

---

## A. 必须确认的业务语义（先谈清楚，否则接口再全也对不上）

| 场景 | ERP/吉客云侧含义 | 我方需要的最小语义 |
|---|---|---|
| 仅退款（未退货） | 库存不回滚 | 只影响财务，不冲销领料（可记录但不回滚库存） |
| 退货退款（已退回） | 库存回仓/重入库 | 需要按退货数量冲销扣料；必要时生成“退料/返库”记录 |
| 换货 | 退旧+发新 | 需要能关联“退货行”和“新发货行” |
| 重发/补发 | 同订单再次发货 | 需要能识别是“补发”还是“新订单”，避免重复冲销 |
| 发货单作废/撤销 | 原发货不成立 | 必须能标记原发货行无效，并冲销其扣料/快照 |

---

## B. 售后/退货数据对象与唯一键（必须书面确认）

| 我方对象 | 对方对象 | 必须提供的唯一键 | 必须能映射回 |
|---|---|---|---|
| 售后单 | after_sales / return_order | `after_sales_no`（或唯一ID） | 订单号/发货单号（至少其一） |
| 售后明细行 | after_sales_line | **`after_sales_line_id`**（或稳定组合键） | **原始订单明细行 `order_line_id` 或 原始发货明细行 `shipment_line_id`** |
| 退货入库单（如有） | return_inbound | `inbound_no/id` | after_sales_no |

> **强制要求**：售后明细行必须能提供 `related_line_id`（关联到原订单/发货明细行的ID）。  
> 如果只能提供“条码+规格”类弱关联：必须同时提供“订单号/发货单号 + 行号/商品行ID”才能保证唯一。

---

## C. 读取接口需求（Read APIs）

### C1. 售后单列表（增量+分页）

| 字段 | 要求 |
|---|---|
| Method/Path | `GET /after-sales`（示例，按对方实际） |
| 目的 | 增量拉取售后单头，触发拉明细 |
| 查询参数 | `updated_at_from`（必需）、`updated_at_to`（建议）、`page`、`page_size` |
| 必须返回字段 | `after_sales_no/id`、`updated_at`、`status`、`type`（仅退款/退货退款/换货等） |
| 建议返回字段 | `order_no`、`shipment_no`（如有）、`reason`、`channel/shop` |

### C2. 售后明细行（关键）

| 字段 | 要求 |
|---|---|
| Method/Path | `GET /after-sales/{after_sales_no}/lines`（示例） |
| 目的 | 生成冲销事件：影响扣料/库存/成本对账 |
| 必须返回字段 | `after_sales_line_id`、`after_sales_no`、`type`、`status`、`qty`、`updated_at` |
| 必须返回字段（关联） | `related_order_line_id` 或 `related_shipment_line_id`（至少其一） |
| 必须返回字段（商品） | `erp_sku_barcode`（货品条码）、`spec_text`（交易规格，若售后时可变更也要给） |
| 建议返回字段 | `refund_amount`、`warehouse_inbound_no`、`logistics_no` |

### C3. 作废/撤销/状态变更（强烈建议）

| 字段 | 要求 |
|---|---|
| Method/Path | `GET /after-sales/changes` 或在 C1/C2 的 `updated_at` 中体现 |
| 目的 | 售后单可能从“申请→通过→入库→完成/取消”，我方需可重算冲销 |
| 必须返回字段 | `updated_at`、`status`、`revision`（若有） |

---

## D. 写回/反写需求（可选，但谈下来更省人力）

> 我方希望把“冲销状态/追溯ID”写回 ERP，便于客服/仓库看到处理结果。

| 项 | 要求 |
|---|---|
| 写回对象 | 售后单/售后明细行（优先）或订单明细行 |
| 必须字段 | `costing_reverse_trace_id`、`reverse_status`、`reverse_message`、`reverse_updated_at` |
| 定位键 | `after_sales_line_id` 或 `related_*_line_id` |
| 幂等键 | `idempotency_key`（建议支持） |

---

## E. 幂等、重跑与对账口径（必须确认）

| 项 | 要求 |
|---|---|
| 幂等键 | `after_sales_line_id + status + updated_at` 或对方提供 `revision` |
| 重跑语义 | 同一售后行状态变化时，允许我方生成新“冲销快照/冲销事件”并覆盖旧的活动状态 |
| 对账口径 | 售后“完成/入库完成”才触发库存回滚；“仅退款/未入库”不回滚库存（仅记账） |

---

## F. 对方需提供的字段字典/样例（无试用 API 时必需）

请对方至少提供：
- 售后单/明细接口字段字典（字段名、类型、状态枚举、type枚举）
- 2-3 份真实样例响应 JSON（含：退货退款、仅退款、换货/补发）
- 限流策略说明（QPS/并发/分页上限/错误码）


