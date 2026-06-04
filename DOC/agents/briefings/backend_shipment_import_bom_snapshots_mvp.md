# Backend 闭环任务单：发货单 Excel 导入 → spec_hash 缓存解析 → BOM 快照生成 + 异常队列（MVP）

> 角色：@Backend Agent  
> 决策：**发货时再解析**（导入昨日发货 Excel 时解析 spec_text），配合 `spec_hash` 缓存与异常队列。  
> 目标：形成一个“可对账、可追溯、可重跑但不回写历史”的最小闭环。

## 1) 本轮范围（必须很小）

只做一个闭环：**导入 1 份发货单 xlsx → 落 raw/标准化行 → 去重/修订 → 生成 bom_snapshot（或入异常队列）**。

不做：
- 不做 ERP API 拉取（先以 Excel 导入为主）
- 不做前端页面（仅后端接口 + 单测）
- 不做利润报表/成本分摊（先保证“快照可用”）

## 2) 输入样例与字段口径

样例文件（用于开发自测）：`DOC/基础表单/发货单-理.xlsx`  
表头提炼件：`DOC/index/extracted/shipment_xlsx_extracted_20251222T000000+0800.md`

最小字段集（标准化层必须产出）：
- `shipment_no`（发货单号）
- `completed_at`（完成时间；支持 Excel serial date 与字符串）
- `channel`（销售渠道）
- `sku_code`（货品条码）
- `spec_text`（交易规格；可为空但会进异常）
- `qty`（数量）
- `revenue_amount`（金额；可为空，不影响 BOM 但用于后续核算）

## 3) 幂等与去重（必须一次做好，否则对账会漂）

### 3.1 文件级幂等（防“同文件重复导入”）

- `file_hash = sha1(xlsx_bytes)`
- `shipment_import_batch`：记录 `file_hash/export_date/imported_by/imported_at/status`
- 若 `file_hash` 已存在且 status=success → **跳过**（返回 batch 信息）

### 3.2 行级幂等（防“跨天重复导出/重复统计”）

- `external_line_key = (shipment_no, sku_code, spec_text, qty, revenue_amount)`
- `external_line_key_hash = sha1(joined_string)`
- `shipment_line` 表对 `external_line_key_hash` 建唯一约束（或逻辑唯一：仅 active）

修订处理（同 key 再次出现但字段变化）：
- 允许写入 `revision_no` 或 `superseded_by`，保留修订链路
- **绝不回写历史 bom_snapshot**：只新增新快照并关联修订

## 4) spec_hash 缓存与快照原则

### 4.1 spec_hash

- `spec_hash = sha1(spec_text)`
- 对同一个 `spec_hash`：优先复用已有 `spec_parse_snapshot`（节省解析成本；你们日活 1000 左右且重复多，收益高）

### 4.2 解析版本化

`spec_parse_snapshot` 必须带 `parser_version`（后续升级解析器/词典可回放）。

## 5) BOM 快照生成

对每条标准化 `shipment_line`：
1) 校验是否有 sku→published 版本绑定（`SkuModelVersionMapping` 的 active 绑定）
2) 若无绑定：写入 `shipment_exception_queue`（reason=`SKU_NOT_BOUND`）
3) 解析 spec_text（或复用 cache），拿到 tokens/dimensions
4) 调用现有 `bom_generation_service.generate_bom(..., sku_code=sku_code, quantity=qty)` 或等价 service
5) 落 `bom_snapshot`（包含：shipment_no、sku_code、model_version_id、spec_hash、qty、final_lines_json、trace_json、generated_at）

## 6) API 设计（建议）

### 6.1 导入接口（新增）

- `POST /api/planner/shipments/import`
- multipart/form-data：
  - `file`：xlsx
  - `export_date`：字符串（你们“昨日导出”的日期，用于批次记录）
  - `requested_by`
- 返回：`shipment_import_batch`（含 batch_id、file_hash、status、counts、warnings 摘要）

### 6.2 查询接口（新增/或复用 jobs）

- `GET /api/planner/shipments/import-batches/{batch_id}`
- `GET /api/planner/shipments/exceptions?batch_id=...`
- `GET /api/planner/shipments/bom-snapshots?batch_id=...`

> 你们仓库已有 `line-items/import` 的 job 模式，可复用同一套 `PlannerJob`/background task 结构。

## 7) 单测（必须最小覆盖）

新增：`backend/tests/planner/test_shipment_import_bom_snapshots_mvp.py`

至少覆盖：
- 同一 xlsx 重复导入：命中文件级幂等（不重复生成 batch）
- 同一订单行跨批次重复出现：命中行级幂等（不重复生成 shipment_line/bom_snapshot）
- 未绑定 SKU：进入异常队列
- 已绑定 SKU：生成 bom_snapshot（final_lines_json 至少 1 行，且 trace 带 bound_version_id/spec_hash）

## 8) 验收命令（只给 1 条）

`pytest backend/tests/planner/test_shipment_import_bom_snapshots_mvp.py -q`


