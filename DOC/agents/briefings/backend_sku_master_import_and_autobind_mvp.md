# Backend 闭环任务单：SKU 主档导入（ERP 平台商品列表）+ 发货导入自动回写（MVP）

> 角色：@Backend Agent  
> 目标：让系统具备“先导入 SKU 主档（以货品条码为主键）→ 发货导入优先命中主档 → 未命中则从发货 spec_text 解析并回写主档”的闭环能力。  
> 核心口径：**发货关联键=货品条码（系统）**；`平台规格Id` 仅展示/追溯，不作为发货关联键。

## 1) 本轮范围（必须很小）

只交付 3 件事：
1) `sku_master`（SKU 主档）落库与查询 API  
2) ERP 导出表（`ERP 理 平台商品列表.xlsx`）导入 API（过滤字段）  
3) 发货导入时若未命中主档：基于发货行创建最小主档（回写）以便下次命中

不做：
- 不做完整“模型编码提取/自动绑定版本”策略（后续单开迭代）
- 不做大规模 40 万全量导入性能优化（先跑通正确性）
- 不做权限系统/审批流

## 2) 输入文件与字段过滤

来源：`DOC/基础表单/ERP 理 平台商品列表.xlsx`（用户已精简字段）  
导入时 **只读以下字段**，其余忽略：
- `规格图片（网店）`
- `销售渠道`
- `商品名称（网店）`
- `商品编码（网店）`
- `商品图片（网店）`
- `商品规格（网店）`（= spec_text 来源之一）
- `平台商品Id（网店）`
- `平台规格Id（网店）`（仅展示/追溯）
- `匹配状态`
- `货品条码（系统）`（**主键/唯一关联键**）
- `最后更新时间`

## 3) 数据模型（建议最小）

新增表：`sku_master`
- `id` (uuid)
- `erp_sku_barcode`（货品条码（系统），unique，非空）
- `platform_product_id`（平台商品Id）
- `platform_sku_id`（平台规格Id，仅展示）
- `channel`（销售渠道）
- `product_name`（商品名称）
- `product_code`（商品编码）
- `spec_text`（商品规格（网店））
- `images_json`（规格图片/商品图片等）
- `match_status`（匹配状态）
- `source_updated_at`（最后更新时间）
- `metadata_json`（扩展：未来写入 model_hint/解析结果/审计信息）
- `created_at/updated_at/is_archived`

## 4) API（建议）

### 4.1 主档导入（新增）
- `POST /api/planner/sku-master/import`（multipart：xlsx + requested_by）
- 返回：导入批次/统计（total/inserted/updated/skipped/errors）

### 4.2 主档查询（新增）
- `GET /api/planner/sku-master?search=&channel=&match_status=&page=&page_size=`
- `GET /api/planner/sku-master/{id}`

### 4.3 发货导入回写（增强现有）
在现有 `POST /api/planner/shipments/import` 内：
- 对每条发货行先按 `货品条码（系统）` 查 `sku_master`
- 若不存在：创建一条最小主档
  - `erp_sku_barcode`=sku_code
  - `spec_text`=发货 `spec_text`（交易规格）
  - `channel`=发货 `channel`（如有）
  - `metadata_json.source="shipment_autobackfill"` + `batch_id/shipment_no/spec_hash`

> 注意：本轮回写主档不要求补齐 platform_sku_id（线上发货单没有此字段）。

## 5) 幂等与更新策略

- 主档导入以 `erp_sku_barcode` 去重：存在则 update（按 `source_updated_at` 或简单覆盖，MVP 可覆盖）
- 发货导入回写：只在 `sku_master` 不存在时创建（不覆盖已存在主档）

## 6) 单测（必须）

新增：`backend/tests/planner/test_sku_master_import_mvp.py`
至少覆盖：
- 导入 2 行：一个新建、一个更新（同 barcode）
- 发货导入时未命中主档会自动创建主档
- 发货导入时已存在主档不会覆盖（metadata 保持）

## 7) 验收命令（只给 1 条）

`pytest backend/tests/planner/test_sku_master_import_mvp.py -q`


