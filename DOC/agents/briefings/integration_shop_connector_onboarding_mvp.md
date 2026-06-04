# Integration Agent 入职简报：店铺对接（以“商品关联/SKU 主档”为中心）

> 目标：让你在 **1 天内**跑通“拉店铺数据 → 写入/导入本系统 → 看到 BOM/扣库清单/异常原因”的闭环，用于低成本验证对接价值（避免一上来就做 18 万/店铺的深对接）。
>
> 适用范围：当前系统已实现 **SKU 主档（商品关联）+ 发货导入（xlsx）+ spec 解析（spec_hash 缓存）+ 动态 BOM 生成 + BOM 快照/异常队列 + 重试异常**。

---

## 你要对接的“最小闭环”到底是什么

### 主链路（你只需要喂数据，不需要改模型）

- **输入**：店铺侧“出库/发货明细”（或订单履约明细），至少包含：
  - `sku_code`（你们口径：货品条码/系统条码，SSOT）
  - `spec_text`（交易规格原文）
  - `qty`（数量）
  - `revenue_amount`（金额，可选但强烈建议）
  - `shipment_no`（发货单号/履约单号）
  - `completed_at`（发货/出库完成时间）
  - `channel`（店铺/渠道标识）
- **系统处理**（你不需要改代码）：
  - 若 `sku_code` 能找到 **已发布标准版本** → 解析规格 → 生成 BOM 快照（含 trace/扣库清单）
  - 找不到则进异常队列：`SKU_NOT_BOUND`
- **输出**：
  - BOM 快照（可追溯、可重跑）
  - 扣库清单（真实物料展开，给库存/盘点对账口径）
  - 异常队列（未绑定/解析失败等）

---

## 你应该先读哪些文件（不要全仓扫描）

- **系统主线与术语**：
  - `DOC/costing/reviews/shipment_time_parse_review_phase0_phase1_20251222.md`
  - `DOC/costing/reviews/erp_guardrails_addendum_20251222.md`
- **发货 xlsx 的字段口径/表头样例（你对接时最重要）**：
  - `DOC/index/extracted/shipment_xlsx_extracted_20251222T000000+0800.md`
- **SKU 主档（商品关联）与绑定工作台（UI/流程）**：
  - 前端页面：`/costing/sku-master`
  - 任务记录（理解“为什么 SKU_NOT_BOUND”）：`DOC/agents/known_issues.md`（§7）

---

## 系统现状：你能直接用的入口

### 1) SKU 主档（商品关联）

- 页面：`/costing/sku-master`
- 目标：把店铺/ERP 的 SKU（货品条码）关联到“已发布标准版本”
- 结果：后续导入发货行时，能消灭 `SKU_NOT_BOUND`

### 2) 发货导入与对账监控

- 页面：`/costing/shipments`
- API（后端）：`POST /api/planner/shipments/import`（xlsx 导入）
- 结果：
  - 生成批次 + 行
  - 对每行生成 BOM 快照或入异常队列

### 3) 产品上架（测试台）：快速预演 spec 解析与 BOM（可选）

- 页面：`/costing/product-listing`
- 用途：不必走“发货导入”也能先验证某个 `spec_text` 的解析/tokens/BOM 是否符合预期

---

## 对接策略（强烈建议）：先做“导出 xlsx → 导入系统”

> 这是最低成本、最可控、最容易验收的一条路；先跑通再考虑直连 API。

### Phase0：离线/半自动（最快验证价值）

- 方式：从店铺后台导出“发货明细/订单履约明细” → 转换成系统需要的 xlsx 表头 → 上传到 `/costing/shipments`
- 优点：
  - 不需要店铺开放 API
  - 不需要系统改接口
  - 一天内可完成首轮测试

### Phase1：自动化导入（对接成本开始可控）

- 方式：写一个小的 connector（脚本/定时任务）：
  - 拉店铺数据 → 生成 xlsx → 调 `POST /shipments/import`
  - 或未来扩展为 JSON 直传（若我们后续加新接口）

---

## 你交付的“最小可验收产物”是什么（给你 3 选 1）

> 你可以任选其一作为你第一周闭环；不要一上来做全自动。

### 选项 A：一份“字段映射表 + 造数 xlsx”

- 输出：
  - 店铺导出字段 → 系统 xlsx 字段的映射表（含数据清洗规则）
  - 10 行可导入样例 xlsx（覆盖：已绑定/未绑定/交易规格异常）
- 验收：把该 xlsx 上传到 `/costing/shipments`，能看到 BOM 快照与异常队列分流

### 选项 B：一个“导出→上传”的脚本（半自动）

- 输出：脚本 `tools/integration/<shop>/export_to_shipments_xlsx.py`（若本仓暂无 `tools/`，先放你自己的 repo 也行）
- 验收：运行脚本产出 xlsx，导入成功（见下方验收命令）

### 选项 C：一条最小“自动导入”流水线（定时/手动触发）

- 输出：定时任务或手动命令：拉一天的履约明细 → 产 xlsx → 调用导入 API
- 验收：当天数据能落一个 batch，异常/快照可追溯

---

## 验收命令（本地/服务器，任选其一）

> 你不需要改代码也能验收；只要能导入一份 xlsx。

- **方式 1（UI）**：打开 `/costing/shipments` 上传 xlsx，检查：
  - 批次列表新增 1 条
  - 异常队列里看到 `SKU_NOT_BOUND`（若你故意放了未绑定 SKU）
  - BOM 快照里至少 1 条能打开详情并看到“扣库清单（真实物料）”

- **方式 2（API smoke，需你准备 xlsx 文件路径）**：
  - `curl -sS -X POST "http://127.0.0.1:8800/api/planner/shipments/import" -F "file=@<你的xlsx路径>" -F "requested_by=integration_agent" | python -m json.tool`

---

## 常见坑（你踩一次就会浪费一周）

- **SKU_NOT_BOUND 不是系统报错，是治理信号**：先用 `/costing/sku-master` 把该 SKU 绑定到“已发布标准版本”，再回到 `/costing/shipments` 点“重试本批未解决异常”。
- **不要在浏览器里直连 `:8800`**：生产联调用 nginx 同源 `/api/planner`（跨域会踩坑，见 `DOC/agents/known_issues.md`）。
- **spec_text 不稳定是常态**：系统用 `spec_hash` 做缓存与追溯；不要试图“导入时改写历史”，要靠重试/重跑产出新快照。

---

## 你需要业务/甲方给你的 3 个确认（越早越好）

1) **SKU 唯一键**：你们店铺导出的哪一列能稳定映射到 `sku_code`（货品条码/系统条码）？
2) **发货行唯一键**：`shipment_no + sku_code + spec_text + qty + amount` 能否唯一？（用于幂等/去重）
3) **交易规格样式**：`spec_text` 常见模式清单（10 条样例即可），用于确认解析/变体命中策略是否需要补词典。


