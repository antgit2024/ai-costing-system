# 吉客云/ERP 对接 API 需求表单（v1，谈判用）

> 目的：在**不提供试用 API**的情况下，先把“必须能力/必须字段/限流/幂等/写回”一次谈清楚，避免后续返工。  
> 我方核心闭环：**SKU 主档同步 → 发货明细同步（含交易规格）→ 解析/匹配/生成 BOM 快照 → 回写可生产工艺到 ERP**。  
> 我方唯一关联键：**货品条码（系统）**（发货明细必须带它；平台规格Id/平台商品Id仅追溯展示）。

---

## A. 鉴权/安全/限流（必须确认）

| 项 | 要求 | 说明 |
|---|---|---|
| 鉴权方式 | AppKey/AppSecret + Token 或 OAuth2 | 必须提供 token 获取/刷新规则 |
| Token 有效期 | ≥ 2 小时（建议） | 需明确 refresh 机制与失效返回码 |
| IP 白名单 | 支持 | 如要求白名单，我方提供固定出口 IP |
| HTTPS | 必须 | |
| 速率限制 | 必须书面提供 | QPS、并发、日限额、分页上限、超限错误码（如 429）与退避建议 |
| 批量接口 | 强烈建议 | 允许一次提交多条写回，减少调用量 |
| 沙箱/样例 | 至少提供其一 | 无沙箱则必须提供“离线样例响应 JSON/字段字典” |

---

## B. 数据对象与主键（必须书面确认）

| 我方对象 | 对方对象 | 必须提供的唯一键 | 备注 |
|---|---|---|---|
| SKU 主档 | SKU/平台规格 | **货品条码（系统）** | 平台规格Id/平台商品Id可选（追溯） |
| 发货单 | 发货/出库单 | 发货单号 `shipment_no` | 必须可增量 |
| 发货明细行 | 发货单明细行 | **明细行唯一键 line_id**（或稳定组合键） | 否则无法幂等/重跑 |
| 退货/取消 | 售后/退货/作废 | 售后单号/明细行唯一键 | 用于冲销扣料/对账 |
| 写回目标（推荐） | 订单/发货明细行 | line_id 或可唯一定位键 | 写回“减少人工转抄” |

> 若对方无法提供 `line_id`：至少保证以下组合键稳定唯一：`shipment_no + 行号` 或 `外部订单号 + 商品行ID`。

---

## C. 读取接口需求（Read APIs）

### C1. SKU 主档列表（增量+分页）

| 字段 | 要求 |
|---|---|
| Method/Path | `GET /skus`（示例，按对方实际） |
| 目的 | 同步 SKU 主档（商品关联） |
| 查询参数 | `updated_at_from`（必需）、`updated_at_to`（建议）、`page`、`page_size` |
| 必须返回字段 | `erp_sku_barcode`（货品条码）、`updated_at` |
| 建议返回字段 | `platform_sku_id`、`platform_product_id`、`product_name`、`product_code`、`channel/shop`、`spec_text`、图片URL |
| 分页约束 | 必须支持稳定分页；明确 `page_size` 上限 |

### C2. SKU 单条查询（按条码）

| 字段 | 要求 |
|---|---|
| Method/Path | `GET /skus/by-barcode?barcode=...`（示例） |
| 目的 | 发货触发时补齐主档信息（若主档缺失） |
| 必须返回字段 | `erp_sku_barcode` |
| 建议返回字段 | 同 C1 |

### C3. 发货单列表（增量+分页）

| 字段 | 要求 |
|---|---|
| Method/Path | `GET /shipments`（示例） |
| 目的 | 增量同步发货单头（用于拉明细） |
| 查询参数 | `completed_at_from` 或 `updated_at_from`（必需）、`page`、`page_size` |
| 必须返回字段 | `shipment_no`、`completed_at/updated_at` |
| 建议返回字段 | `channel/shop`、`status`（完成/作废/撤销） |

### C4. 发货单明细行（关键：必须含交易规格）

| 字段 | 要求 |
|---|---|
| Method/Path | `GET /shipments/{shipment_no}/lines`（示例） |
| 目的 | 生成 BOM 快照/扣料/成本核算的输入 |
| 必须返回字段 | `line_id`（或稳定唯一键）、`shipment_no`、`erp_sku_barcode`、`spec_text`（交易规格）、`qty`、`completed_at` |
| 建议返回字段 | `amount`、`channel/shop`、`order_no`（若有） |
| 重要说明 | **如果没有 `spec_text`（交易规格），无法做按规格动态 BOM/工艺回传** |

### C5. 退货/取消/作废（建议，但强烈）

| 字段 | 要求 |
|---|---|
| Method/Path | `GET /returns` 或 `GET /after-sales`（示例） |
| 目的 | 冲销已扣料/对账一致性 |
| 必须返回字段 | `related_line_id`（或可映射键）、`qty`、`updated_at`、`status` |

---

## D. 写回接口需求（Write-back APIs：把可生产工艺回写到 ERP）

> 背景：ERP“交易规格”不等于生产工艺；我方生成更完整的“生产规格/工艺说明/追溯ID”。  
> 原则：**不覆盖交易规格原字段**；写入 ERP 自定义字段/工艺字段/备注字段。

### D1. 写回到订单/发货明细行（推荐优先）

| 字段 | 要求 |
|---|---|
| Method/Path | `POST /writeback/order-lines`（批量）或 `PATCH /order-lines/{line_id}`（示例） |
| 目标对象 | 订单明细行 或 发货明细行（需对方确认哪个能给工人看） |
| 定位键 | `line_id`（首选）或稳定组合键 |
| 幂等键 | `idempotency_key`（必需，建议对方支持幂等写） |
| 必须写入字段 | `production_spec_text`（生产规格）、`process_instructions_text`（工艺说明）、`costing_trace_id`（追溯ID）、`model_code`、`version_label`、`spec_hash` |
| 建议写入字段 | `dimensions_text`、`materials_pick_summary`、`quality_notes` |
| 响应要求 | 返回每条写回的成功/失败原因（批量） |

### D2. 写回到工单/生产单（如果 ERP 有该对象）

| 字段 | 要求 |
|---|---|
| Method/Path | `POST /writeback/work-orders` 或 `PATCH /work-orders/{id}`（示例） |
| 目标对象 | 工单/生产单 |
| 定位键 | `work_order_id` 或 `order_line_id` |
| 必须写入字段 | 同 D1（至少生产规格+工艺说明+追溯ID） |

### D3. 无 API 兜底方案（必须二选一，否则无法上线）

| 方案 | 要求 |
|---|---|
| ERP 导入模板 | ERP 支持导入更新订单明细行自定义字段（CSV/Excel） |
| 唯一定位键 | 导入模板中必须有 `line_id` 或稳定组合键 |
| 字段数量限制 | 若只有 1 个备注字段，允许合并写入（带分隔符 + trace_id/spec_hash） |

---

## E. 规格变更与重跑语义（必须确认）

| 场景 | 我方策略 | 对方需要支持 |
|---|---|---|
| 同一明细行 `spec_text` 被修改 | 我方生成新快照并回写更新；保留历史 trace_id | 明细行必须有 `updated_at/revision` 便于增量检测 |
| 发货单作废/撤销 | 我方标记冲销（后续扣料回滚/对账） | 提供状态字段或售后/作废接口 |
| 幂等重跑 | 我方按 `line_id + spec_hash + version_id` 幂等 | 对方写回最好支持幂等键或可安全覆盖写回字段 |

---

## F. 对方需要提供的“字段字典/样例”清单（无试用 API 时必需）

请对方至少提供：
- 每个接口的字段字典（字段名、类型、是否必填、枚举值）
- 2-3 份真实样例响应 JSON（SKU/发货单/发货明细/写回响应）
- 限流策略说明（QPS/并发/日限额/分页上限/错误码）


