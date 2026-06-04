# 单店低成本验证（Phase0）：字段口径 & 样例 xlsx（Integration Agent 交付 A）

目标：按现有闭环跑通 **SKU 主档（商品关联）→ 发货明细导入（xlsx）→ spec 解析（spec_hash 缓存）→ 动态 BOM → BOM 快照/异常队列/可重试**。

验收方式（UI）：
- 在 `/costing/shipments` 上传本文件生成的样例 xlsx
- 预期看到：
  - 至少 1 条 **BOM 快照**（前提：样例里“已绑定SKU”确实在你环境已绑定到“已发布标准版本”）
  - 异常队列里看到 `SKU_NOT_BOUND` / `MISSING_SKU` / `SPEC_EMPTY` 分流
- 若 `SKU_NOT_BOUND` 很多：回到 `/costing/sku-master` 绑定到“已发布标准版本”后，再到 `/costing/shipments` 重试异常

---

## 1) `/costing/sku-master`（商品关联/SKU 主档）当前“实际字段”

> 这是你现在在 UI 里真正能操作/能看到的字段口径（有变动时，以此为准）。

### 1.1 你能**填写/提交**的字段（绑定动作）
- **右侧列表勾选**：`sku_master_ids`（多选）
- **左侧绑定工作台 - 人工审核**：
  - **目标标准模型**：`model_id`（只能选“已发布”的标准模型候选）
  - **操作人/审核人**：`requested_by`（可选）
- **提交接口**：`POST /api/planner/sku-master/bind-by-model`
  - payload：`{ model_id, sku_master_ids, requested_by? }`

### 1.2 你能**上传**的字段（SKU 主档导入，可选）
- **xlsx 文件**：`file`
- **requested_by**：可选
- **提交接口**：`POST /api/planner/sku-master/import`

### 1.3 右侧列表/详情抽屉展示的核心字段（主档数据本体）
最关键（用于“字段齐全率/对接就绪”口径）：
- `erp_sku_barcode`：货品条码（系统/ERP 侧 SSOT，**后续所有ERP表单都用它关联**）
- `channel`：销售渠道/店铺
- `product_name`：商品名称（网店）
- `product_code`：商品编码（网店）
- `spec_text`：交易规格原文（网店）
- `platform_product_id`：平台商品Id（网店）
- `platform_sku_id`：平台规格Id（网店，**店铺侧唯一SKU id；通常只在“商品关联下载表”里出现**）

为反向同步预留（当前落在 `metadata_json`）：
- `metadata_json.shop_spec_code`：规格编码（网店，**新品会写入我们系统编码；老品可能为空**）
- `metadata_json.production_process`：生产工艺（用于回传ERP，打印生产单可见；**兼容旧列名“生产工艺注”**）
- `metadata_json.match_method`：匹配方式（用于排查同步链路）

绑定/解析相关（用于排障）：
- `active_model_version_id`：是否已绑定（本系统）
- `bound_model_code` / `bound_model_name` / `bound_version_label`：已绑定信息
- `erp_spec_hash` / `erp_parser_version` / `erp_dimensions` / `erp_tokens`：ERP 解析结果（若有）
- `last_shipment_spec_text` / `last_shipment_spec_hash` / `spec_mismatch`：最近发货回写与差异信号

---

## 2) 发货导入 xlsx：表头→系统字段映射（最小闭环）

系统会按表头（中文列名）读取并归一化为以下字段：

| 系统归一化字段 | 用途 | 推荐表头（优先） | 允许的同义表头（系统已支持） | 备注 |
|---|---|---|---|---|
| `shipment_no` | 发货单幂等/追溯 | `发货单号` | `单号` / `订单号` | 建议非空 |
| `completed_at` | 发货完成时间 | `完成时间` | `付款时间` | 支持 Excel 日期序列号/常见字符串 |
| `channel` | 渠道/店铺 | `销售渠道` | `店铺` / `渠道` | 建议非空 |
| `sku_code` | SKU 唯一键 | `货品条码` | `SKU` / `sku_code` | **决定是否命中绑定** |
| `spec_text` | 规格原文 | `交易规格` | `规格` / `规格信息` | 为空会 `SPEC_EMPTY` |
| `qty` | 数量 | `数量` | `数量合计` | 为空默认按 1 |
| `revenue_amount` | 金额（可选但建议） | `金额` | `实付金额` | 用于后续对账/收入口径 |

额外说明：
- 如果 `交易规格` 列缺失或某行为空，系统会尝试从该行任意单元格中“猜”出形如 `颜色分类:...;尺寸:...` 的文本作为 `spec_text`（用于处理脏导出）。
- 导入后行级异常原因（常见）：
  - `MISSING_SKU`：`sku_code` 为空
  - `SPEC_EMPTY`：`spec_text` 为空
  - `SKU_NOT_BOUND`：SKU 未绑定“已发布标准版本”（请回到 `/costing/sku-master` 绑定后重试）

---

## 3) 交付物：10 行造数样例 xlsx（可直接上传）

生成脚本：
- `tools/integration/generate_sample_shipments_xlsx.py`

默认输出路径：
- `DOC/agents/fixtures/shipments_import_sample_10rows.xlsx`

运行方式（使用后端 venv，确保依赖 openpyxl 可用）：

```bash
cd /home/admin/ai-costing-system
/home/admin/ai-costing-system/backend/venv/bin/python tools/integration/generate_sample_shipments_xlsx.py
```

样例数据覆盖点：
- 1 行“已绑定 SKU”（用于产出 BOM 快照；若你环境尚未绑定，请先在 `/costing/sku-master` 完成绑定）
- 1+ 行 `SKU_NOT_BOUND`
- 1 行 `MISSING_SKU`
- 1 行 `SPEC_EMPTY`
- 1 行：`交易规格` 为空但在“客服备注”里包含 `颜色分类:...;尺寸:...`（用于覆盖 spec 猜测逻辑）

---

## 4) 18万SKU“平台商品列表”导入建议（单店场景）

你给的示例文件：`DOC/基础表单/天猫绮妙店铺平台商品列表(22026.1.10).xlsx`

### 4.1 重要坑：这个文件的 xlsx 维度（dimension）是坏的

该类文件常见问题：`xl/worksheets/sheet1.xml` 里写死了 `<dimension ref="A1"/>`，导致 openpyxl/Excel 以外的解析器只能读到 A1（看起来像“只有表头/只有一行”）。

结论：**不要直接用 UI 上传这个原始文件到 `/costing/sku-master`**（后端会读不到有效数据）。

### 4.2 推荐流程：先归一化/分片，再导入

我们已经提供脚本将其“修复维度 + 分片输出”为标准可导入 xlsx：

- 脚本：`tools/integration/normalize_tmall_platform_list_xlsx.py`
- 输出目录（默认）：`DOC/agents/fixtures/tmall_platform_list_chunks/`

运行示例（建议先小范围验证）：

```bash
/home/admin/ai-costing-system/backend/venv/bin/python \
  /home/admin/ai-costing-system/tools/integration/normalize_tmall_platform_list_xlsx.py \
  --in "/home/admin/ai-costing-system/DOC/基础表单/天猫绮妙店铺平台商品列表(22026.1.10).xlsx" \
  --out-dir /home/admin/ai-costing-system/DOC/agents/fixtures/tmall_platform_list_chunks \
  --chunk-size 20000 \
  --max-rows 50000
```

然后把输出的 `chunk_0001.xlsx ...` 逐个导入 `/costing/sku-master`（导入是 upsert：同条码会更新，不会重复插入）。

### 4.3 关于“之前测试上传的文件/数据会不会被清掉？”

- **不会自动清除**：SKU 主档、发货批次、异常队列都落在数据库里，默认会保留（方便追溯/重试）。
- **发货预览缓存文件**：发货导入预览会在后端 `logs/shipment_previews/` 留存 xlsx（用于预览/重放）；如需清理磁盘可以删该目录文件（不影响已落库的批次/行）。

### 4.4 发货时按需同步（你当前选择的方案）

当发货导入遇到“该货品条码在 SKU 主档里不存在”：
- 系统会自动创建一条**最小SKU主档**（`source=shipment_autobackfill`，带上本次发货的 `channel/spec_text` 及 last_shipment_* 追溯信息）
- 并打标：
  - `metadata_json.needs_erp_sync=true`
  - `metadata_json.erp_sync_status=pending`

这样后续你们可以用“按需拉取ERP商品关联”去补齐平台字段（平台规格Id/规格编码/生产工艺等），再回到 `/costing/shipments` 重试异常即可。

#### 实用清理脚本（默认 dry-run，避免误删）

- 清理发货预览缓存文件（只动磁盘，不动数据库）：

```bash
python /home/admin/ai-costing-system/tools/integration/cleanup_shipment_previews.py --dry-run --older-than-days 7
```

- 按“边界”回滚 SKU 主档导入（建议仅测试/误导入使用；默认软删除）：

```bash
/home/admin/ai-costing-system/backend/venv/bin/python \
  /home/admin/ai-costing-system/tools/integration/purge_sku_master_imports.py \
  --requested-by tester \
  --source erp_import \
  --dry-run
```



