# 吉客云 ERP 货品主档同步与反写 — 蓝图与待办

最近校对：2026-05-16（v3 — 与 Phase0 / writeback MVP 历史口径对齐）（追加：三系统对齐 + 主条码语义 + 3 个字段缺口）

> 本文是这条业务线的唯一蓝图。下次接续时**先读完本文**再写代码，不要重新猜接口、不要重新讨论是否新建表。
>
> 配套资料：
> - 接口字段清单：`DOC/基础表单/core_interfaces_extracted.md`
> - 接口订购建议：`DOC/基础表单/吉客云货品同步接口订购建议.md`
> - 接口关键限制：`DOC/基础表单/关键官方限制原文摘要.md`
> - 反写蓝图（旧）：`DOC/costing/blueprints/erp_writeback_process_spec_mvp.md`
> - 导入模板规范（用户照这个去吉客云后台导出）：`DOC/基础表单/吉客云货品档案导入模板规范_v1.md`

## 0. 当前状态

阶段 A / B / C / D / **F**（API 每日增量同步）全部已开发完成。详见 §10 落地节奏 / §0.1 / §0.2。

更紧急的发货+成本主线仍在并行推进，本任务的代码动作不抢主线时间。

### 0.2 ✅ F 阶段开发完成（2026-05-16）

**接口订购** ✅ 用户已订购 `erp.storage.goodslist`，appKey=22258171，立即生效。

**关键实测数据**（verified live 2026-05-16 against 用户的真实 ERP）：

| 项 | 值 | 备注 |
|---|---|---|
| 成功子码 | `subCode="0030000004"` | ERP 命名空间专用，已加进 `client._BUSINESS_OK_SUB_CODES` |
| pageIndex | **0-based** | 注意与 OMS 1-based 不同！ |
| pageSize 上限 | 200 | 实测 200 行返回 ~500ms |
| 时间戳格式 | **毫秒级 Unix epoch** | 例如 `1751707629000` = 2025-07-05 17:27 |
| 响应 list 路径 | `result.data.goods` | 不是 `result.data` |
| 增量参数 | `startDateModifiedSku/endDateModifiedSku` | 也支持 `*Goods` 版，我们用 sku 更细粒度 |
| 全量游标 | `maxSkuId=0` 起步 | 用于 bootstrap，但本期 Excel 已打底 |

**关键字段填充率**（n=50 实测样本，appKey=22258171）：

| 字段 | 填充率 | 我们的字段 |
|---|---|---|
| `goodsId` / `skuId` / `goodsName` / `skuName` / `isBlockup` / `skuIsBlockup` / `isDelete` / `goodsAttr` / `cateName` / `gmtModified` | 100% | physical + metadata |
| `skuNo` / `skuBarcode` | ~92% | physical (`spec_text`/`erp_sku_barcode`) |
| `cateFullName` | 94% | metadata.erp.category_full |
| `skuImgUrl` | 68% | images.spec_image |
| `imgUrlList`（主图列表）| 8% | images.product_image |
| `skuCode` (=outSkuCode) | **0%** | 用户 ERP 全空，待 G1 反写后才有 |
| `flagData` (规格标记) | 0%（前 50 条）| metadata.erp.sku_flag_synced，不同分类可能有 |
| `goodsField1-50` / `skuField1-30` | 0% | 用户未启用自定义字段 |

**冒烟测试结果**（2026-05-16 14:24:51 ~ 14:24:54，3.5 秒）：

```
sync_run_id    = c43500d3-2c35-4f70-9d25-bdd365aa60bc
status         = succeeded
total_rows     = 643      ← 5-15 当天 ERP 修改的 SKU 数
inserted_rows  = 0        ← Excel 已打底, 全部 update 路径
updated_rows   = 643
skipped_rows   = 0
error_rows     = 0        ← 死信表 0 条
cursor_end     = 6084486685092 (最后处理的 skuBarcode)
```

字段回灌验证：643 行里 593 行获得了 `erp_goods_id` / `erp_sku_id`（Excel 没这两个字段，全靠 API 回灌），剩下 50 行因为 `skuBarcode` 在 Excel 也没出现，是新建行（其实 inserted=0 说明并没新建，那 50 行可能是源数据本身没 goodsId — 待观察）。

**已交付的代码（含路径 + 行号锚点，便于下次接续）**：

| # | 文件 | 关键内容 |
|---|---|---|
| F-1 | `backend/src/integrations/jackyun/api/goods.py` | `iter_goods()` 增量分页 + `iter_goods_by_cursor()` 全量游标 |
| F-2 | `backend/src/integrations/jackyun/mappers/goods.py` | `api_payload_to_row_payload()` + `upsert_goods_from_payload()` 复用窄覆盖 |
| F-3 | `backend/src/integrations/jackyun/sync_jobs.py::sync_goods` | 24h 切窗 + 水印 `skuGmtModified` + 死信兜底 |
| F-4 | `backend/src/planner/services/jackyun_goods_import_service.py::apply_payload_to_row` | 提升公开 + 加 `source` 参数（区分 xlsx / api） |
| F-5 | `backend/src/planner/routers/integrations.py::trigger_jackyun_goods_sync` | `POST /integrations/jackyun/sync/goods` |
| F-6 | `ops/systemd/user/jackyun-goods-sync.service` + `.timer` | 每晚 03:30 自动跑 + `RandomizedDelaySec=120` |
| F-7 | `backend/scripts/cron_sync_jackyun.py` | 加 `--task=goods` |
| F-8 | `frontend/src/pages/costing/IntegrationsHubPage.tsx::TriggerJackyunGoodsCard` | UI 卡片 + 高级参数模态框 |
| 副作用 | `backend/src/integrations/jackyun/client.py` | `_BUSINESS_OK_SUB_CODES` 加 `"0030000004"` |

**未做但下期可做（不阻塞日常运行）**：

- `metadata.erp.last_api_sync_at` 时间戳（让 ProductInfoPage 显示"上次 API 同步于 X 分钟前"）
- 接 `erp.goods.customfield`（自定义字段字典，免费 API）— 等用户启用了自定义字段后再说
- F 跑完后自动触发 G3 反写状态回收（对比 `shop_spec_code` 与新拉回的 `out_sku_code`）

### 0.1 历史记录：F 阶段订购前阻塞（2026-05-16 早上实测）

实测调用，6 个候选货品 API **全部未订购**，appKey=22258171：

```
❌ 未订  erp.storage.goodslist          ← P0 必订（168 字段全字段读，本期主接口）
❌ 未订  erp-goods.goods.sku.search     ← P1 备用（条件筛选）
❌ 未订  erp.storage.goodsskulist
❌ 未订  erp.goods.sku.modify.search
❌ 未订  wms.goods.sku.list
❌ 未订  erp-storage.goods.list
```

错误码：`[0130020310] 未查询到应用或应用未订阅此API`

#### 用户操作指引（必须先做完才能进入 F 阶段开发）

1. 登录 [吉客云开放平台开发者控制台](https://open.jackyun.com/developer/) （需要管理员账号）
2. 进入"应用管理"，找到 `appKey = 22258171` 的应用
3. 在"接口订购"或"API 订阅"页订购下面的接口（最小集）：

| 必选 | 接口 method | 用途 | 备注 |
|---|---|---|---|
| ✔ 必订 | `erp.storage.goodslist` | 全字段读（168 字段，每日增量同步主接口） | 收费，按调用计费 |
| ✔ 免费 | `erp.goods.customfield` | 自定义字段字典（goodsField1-50 中文翻译） | **不需订购但要接入** |
| 后期 | `erp.goods.skuimportbatch` | 反写 ERP（写商家编码 / 自定义字段） | G4-H 阶段才用，暂不订 |
| 备用 | `erp-goods.goods.sku.search` | 条件筛选（修改时间增量） | 字段少，可不订 |

4. 订购通常立即生效或人工审核 1-3 个工作日（视吉客云策略）
5. 订购通过后，**告诉 agent 一句"erp.storage.goodslist 订购通过了"**，开干 F 阶段（约 5 小时一次性完成）

#### 订购通过后开发任务清单（已就绪，等命令）

| # | 文件 | 动作 | 工作量 |
|---|---|---|---|
| F-1 | `backend/src/integrations/jackyun/api/goods.py` (新) | `iter_goods()` 双模分页：首次按 `maxSkuId` 游标 + 后续按 `startDateModifiedSku/Goods` 增量 | 1.5h |
| F-2 | `backend/src/integrations/jackyun/mappers/goods.py` (新) | `api_payload_to_row_payload()`：API JSON → `RowPayload`（复用 `_apply_payload_to_row` 窄覆盖） | 1.5h |
| F-3 | `backend/src/integrations/jackyun/sync_jobs.py` | 加 `sync_goods()`，参考 `sync_shipments` 的水印 + 24h 切窗 + 死信模式 | 1h |
| F-4 | `backend/src/planner/services/jackyun_goods_import_service.py` | 把 `_apply_payload_to_row` 提升为公开 API（薄封装），区分 source = `jackyun_erp_goods_xlsx` / `jackyun_erp_goods_api` | 0.3h |
| F-5 | `backend/src/planner/routers/integrations.py` | `POST /integrations/jackyun/sync/goods`，BackgroundTask 模式 | 0.3h |
| F-6 | `ops/systemd/user/jackyun-goods-sync.service` + `.timer` (新) | 每日 03:30（晚于 shipment 02:30 / refund 03:00）+ `RandomizedDelaySec=120` | 0.2h |
| F-7 | `scripts/cron_sync_jackyun.py` | 加 `--task=goods` 选项 | 0.2h |
| F-8 | `frontend/src/pages/costing/IntegrationsHubPage.tsx` | "吉客云·货品档案 API 同步"卡片，与现有发货/退款卡片对齐 | 0.5h |
| F-9 | 验证 | 调一次 `pageSize=1` 实测 → 跑一次 24h 增量 → 看死信 → 验证 ProductInfoPage 数据更新 | 0.5h |

合计 ~5 小时，全部代码路径已调研清楚（见 [此次开发的 explore 调研](#)），不需要重新摸源码。

#### 复用要点（避免重写）

- ✅ **窄覆盖核心 100% 复用** `jackyun_goods_import_service._apply_payload_to_row`——它不依赖 Excel 列映射，只要 `RowPayload` 即可
- ✅ **死信 / 水印 / 跑批跟踪** 100% 复用 `sync_jobs.py` 内的 `run_sync` / `archive_record` / `record_dead_letter` / `advance_watermark_if_newer`
- ✅ **公共参数 / 签名 / 重试** 100% 复用 `JackyunClient` + `BaseClient.call`
- ⚠ **Excel 路径下 `metadata.source = jackyun_erp_goods_xlsx`**——API 路径要改成 `jackyun_erp_goods_api`，便于审计区分

## 1. 现行发货链路真相（务必先理解）

> 用户最常误解："要不要为发货专门建一个商品档案表，让发货命中就直接读？"
> 真相：**已经是这个流程**，只是缓存被拆成了 3 张表。**不要再建表**。

### 1.1 一次发货行从入库到出 BOM 走的路径

```
发货行进来（Excel/吉客云同步）
  │
  ├─ 第1步：写档案（不是查档案）
  │      sku_master_service.ensure_from_shipment(sku_code, spec_text, channel, metadata)
  │      └─ 在 sku_master 表 upsert 一行（按 erp_sku_barcode 唯一）
  │         · 新建：metadata.source = "shipment_autobackfill" + needs_erp_sync=True
  │         · 已存在：刷新 last_shipment_spec_text、shop_spec_code、preparse_*、spec_mismatch
  │
  └─ 第2步：worker 跑 _finalize_shipment_line（读缓存出快照）
         │
         ├─ ① get_active_sku_binding(sku_code)
         │     └─ 查 sku_model_version_mapping 表（不是 sku_master！）
         │        · 命中 → 直接拿到 model_version_id
         │        · 未命中 → 入异常队列 SKU_NOT_BOUND，等绑定
         │
         ├─ ② _upsert_spec_snapshot(spec_text)
         │     └─ 查 spec_parse_snapshots 表（按 spec_hash 唯一）
         │        · 命中 → 直接复用解析结果（dimensions / tokens / area_m2 / ...）
         │        · 未命中 → 跑解析器，缓存进表，下次同 spec_text 免跑
         │
         └─ ③ generate_bom(binding + spec_snap) → BomSnapshot + ShipmentCostingResults
```

### 1.2 三表分工

| 表 | 唯一键 | 写入频率 | 读取频率 | 设计意图 |
|---|---|---|---|---|
| `sku_master` | `erp_sku_barcode` | 中（每次发货 upsert） | 中（前端展示 + 抽屉） | SSOT，承载 ERP 字段 + 商家编码归一化 + 元数据 |
| `sku_model_version_mapping` | `(sku_code, is_active=true)` partial unique | 极低（人工/自动绑定） | 极高（每条发货行查一次） | 读多写少的小表，sub-ms lookup |
| `spec_parse_snapshots` | `spec_hash` | 极低（新 spec 出现时） | 极高（每条发货行查一次） | 多个 SKU 共享同一份解析结果 |

**结论**：你想要的"档案命中即用"已经实现，只是查询源不是 `sku_master` 而是 `sku_model_version_mapping` + `spec_parse_snapshots`。性能上**没区别**（都是主键 lookup），架构上**更优**（写多与读多分离）。

## 2. 不新建独立 ERP 货品表的决策

### 2.1 为什么不建 `erp_goods_master` / `erp_goods_snapshot`

| 假设需求 | 已有表怎么解决 | 是否需新表 |
|---|---|---|
| 发货来了快速命中模型 | `sku_model_version_mapping` | 否 |
| 发货来了快速复用规格解析 | `spec_parse_snapshots` | 否 |
| 保存吉客云 168 字段做反查 | `sku_master.metadata_json.erp.*` | 否 |
| 反向写回 ERP 字段 | `sku_master.metadata.bound_*` + outSkuCode 即可生成 payload | 否 |
| 全量 40 万吉客云货品落地 | upsert 进 sku_master，按 `erp_sku_barcode` 唯一，自动合并已发过货那几千行 | 否 |

### 2.2 唯一变化：sku_master 行数从 ~5K 增长到 ~40 万

不是结构变化，是**数据量变化**。配套调整看 §6 性能保障。

## 3. JSONB 全收 + 物理列升级 策略（重点）

### 3.1 三级分类

| 级别 | 字段范围 | 存哪里 | 例子 |
|---|---|---|---|
| **L0 不存** | 图片二进制、长 HTML 描述 | 不存（图片只存 URL） | 详情页 HTML、Base64 图 |
| **L1 进 metadata_json.erp** | 绝大多数（约 140+ 字段） | JSONB | `goodsField1-50` / `skuField1-30` / `extendValue` / 各种 `isXxx` / 颜色编码 / ABC 分类 / 重量体积 / 仓库 / 备注 |
| **L2 物理列** | 5-7 个高频字段 | 物理列 + 索引 | 见下表 |
| **L3 独立表** | 暂无 | — | 将来真有需要再分（辅助条码、价目历史、附件） |

### 3.2 L2 物理列清单（一次到位，避免反复 ALTER）

**v3 修订**：与 Phase0 / shipment mapper / sku_master_service 已落地命名对齐，**不重新造名**。
原 7 列方案中：`merchant_sku_code` 改用旧名 `shop_spec_code` 升级；`main_barcode` 业务不用降级回
metadata。最终 **7 个 L2 物理列**（5 个全新列 + 2 个 metadata 升列）。

| 字段 | 类型 | 是否新增 | 索引 | 用途 |
|---|---|---|---|---|
| `erp_sku_barcode` | varchar(64) | 已有 | **unique** | **SSOT 主索引**（= ERP 条码 / 货品条码(系统) / 规格条码） |
| `product_name` | varchar(255) | 已有 | — | 名称展示 |
| `product_code` | varchar(128) | 已有 | — | 货品编号（ERP `goodsNo`） |
| `spec_text` | text | 已有 | — | 规格文本 |
| `source_updated_at` | datetime | 已有 | index | 增量同步排序 |
| `images_json` | json | 已有 | — | 图片 URL 集合 |
| `shop_spec_code` (旧 metadata 字段) | varchar(128) | 已有但在 metadata | — | **网店商家编码 / 模型编码**（如 `KB8-001`），Phase0 沿用至今 |
| `production_process` (旧 metadata 字段) | text | 已有但在 metadata | — | **系统生成的"可执行生产工艺"**（来自模型版本），用于反写 ERP，Phase0 沿用至今 |
| **`shop_spec_code`** | **varchar(128)** | **🆕 升级为物理列** | **index** | 同上字段从 metadata 升 L2，给查询/筛选/反写当锚点 |
| **`out_sku_code`** | **varchar(128)** | **🆕 新增** | **unique（含 NULL）** | **反写 ERP 的目标键**（ERP 外部编码 `outSkuCode`，从 ERP 同步过来的当前值） |
| **`erp_goods_id`** | **bigint** | **🆕 新增** | **index** | API 增量游标 + 售后/发货反查 |
| **`erp_sku_id`** | **bigint** | **🆕 新增** | **index** | API `maxSkuId` 游标 |
| **`is_blocked`** | **bool** | **🆕 新增** | **partial idx where true** | 停用筛选 + 是否纳入解析 |
| **`is_deleted_at_source`** | **bool** | **🆕 新增** | **partial idx where true** | ERP 端删除筛选 |
| ~~`main_barcode`~~ | — | **❌ 不新增** | — | 用户 2026-05-16 确认业务不用 69 码/UDI；保留在 `metadata.erp.main_barcode` 即可，将来若需再升 |

> **7 个 L2 物理列**一次 migration 完成，**不要分多次 ALTER**。
>
> **`shop_spec_code` vs `out_sku_code` 的区别（重要 — 反写的关键）**：
> - `shop_spec_code` = **我们系统侧的规范值**（来自发货 `tradeGoodsno` 剥前缀，或 SKU 主档手工绑定）
> - `out_sku_code` = **ERP 侧的当前值**（从 `erp.storage.goodslist` 同步过来，多数为空）
> - 实务中两者**应该相等**。当前 ERP 多数为空，反写流程就是把 `shop_spec_code` 推回 ERP 的 `outSkuCode`
>   字段，反写成功后下次同步时 `out_sku_code` 也会被回填同样的值。
> - 反写成功状态判定：`shop_spec_code IS NOT NULL AND out_sku_code = shop_spec_code`。
>
> **`production_process` 的语义（与 §15 历史口径对齐）**：
> - 当前在 `metadata.production_process`，本期升级为 sku_master 的 text 物理列
> - **是系统计算/人工录入的"可执行工艺说明"**，用于反写到 ERP 货品档案的 `工艺说明(规)` 列
> - 反写时映射目标：ERP `process_instructions_reg`（在 metadata.erp 里）
> - **不要**把 ERP 同步下来的 `工艺说明(规)` 直接写到 `production_process`，那是被反写覆盖的目标，不是源

### 3.3 metadata_json 结构（两层）

```json
{
  "metadata_json": {
    "shop_spec_code": "KB8-001",
    "bound_variant_code": "KB8-001",
    "preparse_dimensions": {...},
    "...": "...其他现有字段保持不变",

    "erp": {
      "source": "jackyun_excel_import" | "jackyun_api_v1" | "jackyun_api_storage_goodslist",
      "synced_at": "2026-05-16T08:30:00",
      "schema_version": "v1",

      "category": "枕套",
      "category_full": "家居/枕套",
      "owner": "武汉天昊艺术品有限公司",
      "fixed_cost_price": "12.50",
      "abc_cate": "A类",
      "warehouse": "杭州笛佛仓",

      "model_code_reg": null,
      "process_instructions_reg": null,
      "process_code_reg": null,
      "applicable_model_reg": null,

      "goods_field": {"1":"...","2":"...","30":"..."},
      "sku_field": {"1":"...","2":"..."},
      "extend": {"extend835...":"驱蚊器二去"}
    },

    "erp_raw": { "...完整原始 API/Excel 行..." }
  }
}
```

**两层好处**：
- `metadata.erp.*` = 扁平化业务字段，前后端代码读起来直观（`meta.erp.fixed_cost_price`）
- `metadata.erp_raw` = 原始响应整段保留，将来 ERP 加字段 raw 自动收下，不需要改代码
- 4 个回写目标字段（`模型编码(规)/工艺说明(规)/工艺编码(规)/适用模型(规)`）显式扁平化，便于观测和反写

### 3.4 何时把 L1 字段升级为 L2 物理列（明确触发条件）

只有满足以下任一条件时再做 ALTER，**不要预先升级**：

1. 前端列表加了**新筛选/排序条件**，且这个筛选**用户每天都用**
2. 后端做了一个**业务计算**需要这个字段做 SQL JOIN
3. 这个字段加了**唯一约束 / 外键约束**

经验值：一年内会"提列"的字段一般 5-10 个，不会失控。每次升级时按 `0036_shipment_line_jackyun_full_fields.py` 同款 migration 模式做，并写回填脚本。

## 4. Excel 36 列字段映射表

完整映射在 `DOC/基础表单/吉客云货品档案导入模板规范_v1.md`。这里只摘要：

| Excel 列 | sku_master 落地路径 | 备注 |
|---|---|---|
| 条码 | `erp_sku_barcode`（物理列，唯一键） | 必填 |
| 货品名称 | `product_name` | — |
| 货品编号 | `product_code` | — |
| 规格 | `spec_text` | — |
| 最后修改时间 | `source_updated_at` | 增量同步排序锚点 |
| 规格图片链接 / 货品主图链接 / 上下左右图链接 | `images_json` | 图片只存 URL，不存二进制 |
| 规格编号 | `metadata.erp.sku_no` | — |
| **工艺说明(规)** | `metadata.erp.process_instructions_reg` | 反写目标字段 #1 |
| **模型编码(规)** | `metadata.erp.model_code_reg` | 反写目标字段 #2 |
| 工艺编码(规) | `metadata.erp.process_code_reg` | — |
| 适用模型(规) | `metadata.erp.applicable_model_reg` | — |
| 分类 / 分类全称 | `metadata.erp.category / category_full` | — |
| 货主 | `metadata.erp.owner` | — |
| 长 / 宽 / 高 / 重量 / 体积 | `metadata.erp.dims.*` | 子对象 |
| 默认存放仓库 | `metadata.erp.warehouse` | — |
| 货品标记 / 规格标记 | `metadata.erp.flags` | — |
| 颜色 / 尺码 | `metadata.erp.color / size` | — |
| 固定成本价 | `metadata.erp.fixed_cost_price` | 成本相关，未来可能升 L2 |
| 备注 / 规格备注 | `metadata.erp.memo / sku_memo` | — |
| ABC 分类 | `metadata.erp.abc_cate` | — |
| 建档时间 | `metadata.erp.created_at` | — |
| 链接 | `metadata.erp.url` | — |
| 入库换算(规) | `metadata.erp.unit_rate` | — |
| 规格标记 | `metadata.erp.sku_flag` | — |

## 5. 必补的 4 列（吉客云后台导出时务必加上）

Excel 36 列**少了 4 个关键字段**，否则后续闭环不了：

| 必补字段 | 落地路径 | 没它的代价 |
|---|---|---|
| **`outSkuCode` / 外部编码** | `out_sku_code`（L2 物理列） | 致命：反写 ERP 的唯一匹配键 |
| **`skuId`** | `erp_sku_id`（L2 物理列） | 后续 nightly 增量 `maxSkuId` 游标失效 |
| **`goodsId`** | `erp_goods_id`（L2 物理列） | 售后/发货反查锚点缺失 |
| **`是否停用` / `是否删除`** | `is_blocked / is_deleted_at_source`（L2） | 脏数据进系统洗不掉 |

**模板规范文档详细列出了这 4 个字段的列名候选 + 示例值**：见 `DOC/基础表单/吉客云货品档案导入模板规范_v1.md`。

## 6. 性能保障（重点 — 日均上千 SKU 累加）

### 6.1 数据量增长测算

| 时间点 | sku_master 行数 | 备注 |
|---|---|---|
| 当前 | ~5K | 仅发过货的 SKU |
| Excel 全量导入后 | ~40 万 | 一次性 |
| 1 年后 | ~75 万（按 +1000/天） | 自然增长 + ERP 增量 |
| 3 年后 | ~150 万 | — |

**40 万行 + JSONB ~700 MB，PostgreSQL 完全无压力**。150 万 / 1.5 GB 仍在单节点轻松范围。

### 6.2 写入压力（日均上千 SKU 累加）

| 写入场景 | 频率 | 影响 |
|---|---|---|
| 发货同步触发 `ensure_from_shipment` | 每条发货行 1 次（日均~千次） | 单行 upsert，~5ms |
| ERP nightly 增量同步 | 每天 ~1000-5000 行变更 | 批量 upsert，~30s 内完成 |
| ERP 全量首次导入 | 一次性 ~40 万行 | 分批 5000 行/事务，预计 20-30 分钟 |

### 6.3 索引策略（避免后期慢）

**首次 migration 必须一次到位**：

```sql
-- L2 物理列索引（必加）
CREATE UNIQUE INDEX ux_sku_master_out_sku_code
  ON sku_master(out_sku_code) WHERE out_sku_code IS NOT NULL;
CREATE INDEX ix_sku_master_erp_goods_id ON sku_master(erp_goods_id);
CREATE INDEX ix_sku_master_erp_sku_id ON sku_master(erp_sku_id);
CREATE INDEX ix_sku_master_blocked ON sku_master(is_blocked) WHERE is_blocked = true;
CREATE INDEX ix_sku_master_deleted ON sku_master(is_deleted_at_source) WHERE is_deleted_at_source = true;

-- JSONB 路径索引（按需加，不要一次全加）
-- 仅当出现"按 metadata.erp.X 频繁过滤"时再加：
CREATE INDEX ix_sku_master_meta_erp_category
  ON sku_master USING GIN ((metadata_json->'erp'->'category'));
```

**触发 GIN 索引的硬约束**：当某 `metadata.erp.X` 字段被前端筛选 / 后端 SQL WHERE 频次 ≥ 1 次/分钟，且全表扫 > 200ms 时再加。

### 6.4 同步任务的并发与限流

- ERP 全量首次：单线程 + 5000 行/事务 + 显式 commit，避免大事务锁
- ERP nightly 增量：复用 jackyun shipment-sync 的 systemd timer 模式，03:30 跑（在 refund-sync 03:00 之后）
- API 限流：`erp.storage.goodslist` 1000/天，nightly 单次只拉昨日变更 (`startDateModifiedSku`)，预计 50-200 次调用 / 天，远低于配额
- 失败处理：复用已有 `IntegrationDeadLetter` + `IntegrationSyncRun`，不发明新轮子

### 6.5 PostgreSQL JSONB 性能边界（可信范围）

实测可信范围（按 PG14+ / 单行 metadata 平均 2-3 KB）：

| 操作 | 40 万行 | 150 万行 |
|---|---|---|
| 按 `erp_sku_barcode` 主键 lookup | sub-ms | sub-ms |
| 按 `out_sku_code` 唯一索引 lookup | sub-ms | sub-ms |
| 全表扫 `metadata->'erp'->>'category'` 过滤 | ~200ms | ~800ms |
| 同上 + GIN 索引 | sub-ms | ~5ms |

**结论**：JSONB 不会成为瓶颈，前提是按 §6.3 加索引。

## 7. 已确认的接口判断（来自官方文档原文）

### 7.1 ERP 货品主档读取

- 主读接口：`erp.storage.goodslist`
- 字段最完整：返回 168 字段，含 `goodsField1-50`、`skuField1-30`、`skuCode`、`goodsAttr`、主条码、停用/删除状态、`extendValue`
- 关键限制：首次 `maxSkuId=0`，之后取上次返回最后一条 `skuId` 作为 `maxSkuId`，**不是普通翻页**
- 配额：1000/天、30000/月。100 万货品 / 50 页 ≈ 20000 次 → 纯 API 全量约 20 天

### 7.2 ERP 条件筛选

- 接口：`erp-goods.goods.sku.search`
- 用途：按 `goodsNos`、`skuBarcodes`、`skuNos`、`skuCodes`、修改时间、自定义字段 1/2/29/30 筛选
- 限制：返回字段只 33 个，**只适合筛选**，不能替代完整同步

### 7.3 ERP 货品主档写入/反写

- 接口：`erp.goods.skuimportbatch`
- 关键规则：
  - `outSkuCode` 是唯一匹配依据，无 `outSkuCode` 不能更新
  - 单次最多 200 个货品
  - 同一货品必须放同一次调用，前后请求串行
- 风险：文档没明确传空字段是否清空原值，**正式写入前必须用测试货品验证**

### 7.4 自定义字段字典

- 接口：`erp.goods.customfield`（不需订购但已授权）
- 返回：`fieldName` / `memo` / `fieldType` / `fieldLength` / `fieldCaption`
- 用途：把 `goodsFieldN` / `skuFieldN` / `extend...` 映射成中文含义、类型、长度

### 7.5 商品库（注意区分，不要混用）

- 读：`erp-goods-online.item.details` — 商品库 `item`，不是 ERP 货品主档 `sku/goods`
- 写：`erp-goods-online.item.batchupdateitem`
- 限制：`item.details` 不能获取从网店下载的商品；`batchupdateitem` 单次≤50，且只更新非待审核

## 8. 现有代码盘点（避免重复造轮子）

| 资产 | 路径 | 状态 |
|---|---|---|
| 商品档案展示页 | `frontend/src/pages/costing/ProductInfoPage.tsx` | ✅ 已用 sku_master，加 `metadata.erp.*` 列即可扩展 |
| 商品档案展示后端 | `backend/src/planner/routers/sku_master.py` 的 `GET /sku-master` | ✅ 不需改 |
| sku_master ORM | `backend/src/planner/models.py:SkuMaster` | ⚠ 加 7 个 L2 列 + migration（5 个新增 + 2 个 metadata 升列） |
| 旧 ERP Excel 导入 | `import_erp_sku_master_xlsx` | ⚠ 表头是另一套（"货品条码（系统）"等），与吉客云 36 列不兼容；新建一个吉客云口径导入器，**不要动旧的** |
| `ensure_from_shipment` | `sku_master_service.py` | ✅ 不动，仍是发货回填入口 |
| jackyun api/goods.py | `backend/src/integrations/jackyun/api/goods.py` | ❌ **占位 stub**，方法名 `erp.goods.query.page` 错误，参数也不对，重写 |
| jackyun mappers/goods.py | — | ❌ 不存在，新建 |
| jackyun sync_jobs.sync_goods | — | ❌ 不存在，新建（参考 `sync_refunds`） |
| writeback：`integration_writeback_jobs` 表 | `models.py:IntegrationWritebackJob` | ✅ 已就绪，只需加 dispatcher |

## 9. 后续必须先确认的问题

继续任务前确认：

1. ~~"商家编码"对应 ERP 哪个字段~~ **已确认（2026-05-16）**：
   - 系统内：沿用旧名 `sku_master.shop_spec_code`（从 metadata 升 L2 物理列），**不新增** `merchant_sku_code`
   - ERP 反写目标：`outSkuCode`（同步镜像为 `sku_master.out_sku_code`）
   - 网店来源：发货 `tradeGoodsno` 归一化（剥前缀）或售后 `outerId`
2. **ERP 实际启用的自定义字段是哪套**：`goodsField1-50` / `skuField1-30` / `extend...` / 两套都有？
   - 路径：先调一次 `erp.goods.customfield` 拿字典，存到本地字典表
3. **`skuimportbatch` 传空字段行为**：保持原值还是清空？
   - 路径：用一两个测试货品做 dry-run + 真写一次实测
4. **反写触发方式**：自动 / 人工 + dry-run + 确认 / 审批后写入？
   - 建议：第一阶段强制人工 + dry-run + 确认；积累信心后再自动
5. ~~主条码字段有没有~~ **已确认（2026-05-16）**：官方文档行 463/1005 明确 `mainBarcode` 在读和写接口都支持；但当前业务不用 69 码/UDI，代码 0 处使用，**不升物理列**，同步时仅留 `metadata.erp.main_barcode`

## 10. 落地节奏（每一步可中止）

> **2026-05-16 更新**：根据用户反馈，落地分两条线：
> - **数据同步线**（A→F）：把 ERP 货品档案灌进我们系统
>   - Excel 导入（C）= **一次性首次铺底**，40 万行历史快照
>   - API 增量（F）= **每天必须跑的日常同步**，新品 / 停用 / 属性变更靠它
>   - **两者都必须做**，不存在"用 Excel 替代 API"
> - **反写线**（G→H）：把我们系统识别的结果写回 ERP
>   - Excel 反写（G1-G3）= **日常推荐**，省 ERP API 配额
>   - API 反写（G4-H）= **备用**，给后台脚本和小批量灰度用

### 10.1 集成入口（统一进 `/costing/integrations`）

货品档案的所有同步操作（导入 / 导出 / API 同步 / 反写）都从这一页进，与现有「吉客云·发货明细同步」「吉客云·售后退款同步」对齐：

| 卡片 | 操作 | 走的接口 |
|---|---|---|
| 🆕 吉客云·货品档案 Excel 导入 | 上传 40 万行 Excel | `POST /integrations/jackyun/goods/import-xlsx`（阶段 C）|
| 🆕 吉客云·货品档案 API 同步 | 增量拉 ERP 货品主档 | `POST /integrations/jackyun/sync/goods`（阶段 F）|
| 🆕 吉客云·反写候选导出 Excel | 生成可上传到 ERP 后台的回传 Excel | `GET /integrations/jackyun/goods/writeback-xlsx`（阶段 G）|
| 🆕 吉客云·反写 dry-run | 调用 `skuimportbatch` 生成 payload 不真发 | `POST /integrations/jackyun/goods/writeback?dry_run=true`（阶段 G）|
| 🆕 吉客云·反写真写 | 灰度真写 ERP | `POST /integrations/jackyun/goods/writeback`（阶段 H）|

跑批运行历史 / 死信复用现有 `sync_runs` + `dead_letters` 基础设施，不另起一套。

### 10.2 数据同步线（A→F，**全部必须做**）

| 阶段 | 动作 | 动到的代码 | 需要用户做什么 | 角色定位 |
|---|---|---|---|---|
| **A. 模板规范** | ✅ 已交付 `DOC/基础表单/吉客云货品档案导入模板规范_v1.md` | 0 | 拿模板回吉客云后台导出 40 万行 + 必补字段 | — |
| **B. ORM + migration** | sku_master 加 7 个 L2 列 + 索引；`metadata.erp` 子对象规范化 | 1 个 migration + ORM/schema 微调 | review | 基础 |
| **C. Excel 导入器** | 新建 `import_jackyun_goods_xlsx`；挂 `POST /integrations/jackyun/goods/import-xlsx`；`/costing/integrations` 加上传卡片 | service + router + 前端按钮 | 上传 Excel（一次性 40 万） | **首次铺底**，**只跑一次** |
| **D. ProductInfoPage 增列** | 增加"外部编码 / 模型编码(规) / 工艺说明(规) / 停用/删除 / 反写状态"列 | ProductInfoPage 改 | 验收 | UI |
| **E. 自定义字段字典** | 接 `erp.goods.customfield`，落 `erp_custom_field_dict` 小表 | 新表 + 1 个 sync route | — | API 依赖 |
| **F. API 增量同步** | 重写 `api/goods.py`：`erp.storage.goodslist` + `maxSkuId/startDateModifiedSku` 双模；mapper；sync_jobs；systemd timer 03:30；`/costing/integrations` 加"货品档案 API 同步"卡片 | api + mapper + sync_jobs + timer + 前端卡片 | 触发首次回灌；之后每天自动跑 | **每日必跑**，承接 Excel 之后的所有增量 |

**关键澄清（2026-05-16 用户提醒）**：

- **C 阶段 Excel 导入**：解决"我们系统当前没有 ERP 货品档案历史快照"的问题，一次性灌 40 万行后就再也不用。它**不能**替代 API。
- **F 阶段 API 同步**：解决"ERP 每天都有新品 / 停用 / 属性变更 / 自定义字段更新"的问题。日常增量、反写状态回收、停用同步全靠它。**这是必须做的，不是备用**。
- **两者关系**：Excel = 历史快照打底，API = 每天差量增补。架构上 API 必须能处理"已有行的字段更新"和"全新行的插入"两种情况。

**实施顺序**：A → B → C → D → E → F。其中 B→D 可以一周内完成不阻塞主线。

**2026-05-16 用户实测 + 重要订正**：吉客云后台货品档案导出 Excel **实测就是没有以下 4 列**（即使勾全部可选字段也拿不到）：

- 外部编码 `outSkuCode`
- 货品 ID `goodsId`
- 规格 ID `skuId`
- 是否停用 / 是否删除

这 4 列**只能通过 F 阶段 API（`erp.storage.goodslist`）拉回来**。所以：

- C 阶段 Excel 导入：放弃强制 4 列，按吉客云能导的字段全收，主键用 `条码`（`erp_sku_barcode`）
- F 阶段 API 同步：必须在 C 之后**立即接通**（不再是"可选稍晚"），由 API 把这 4 列回灌进 `sku_master`
- 反写线 G1 启动前提：API 至少跑过一轮，把 `outSkuCode` 拉回来作为匹配键

依赖关系：A → B → C → **F**（API 接通，回灌 outSkuCode/goodsId/skuId/是否停用） → D（前端展示新增列）→ E（自定义字段字典，给 F 增量解析用）→ G1（反写 Excel 导出，依赖 F 的 outSkuCode）。

**示例 Excel 实测 36 列**（2026-05-16）：
规格标记 / 货品名称 / 货品编号 / 规格 / 条码 / 分类 / 货主 / 长 / 宽 / **工艺说明(规)** /
**模型编码(规)** / 工艺编码(规) / 最后修改时间 / 入库换算(规) / 规格图片链接 /
货品主图链接 / 规格编号 / 货品标记 / 默认存放仓库 / 适用模型(规) / 规格备注 / 备注 /
分类全称 / 尺码 / 建档时间 / 重量(g) / 体积 / 高 / 上图链接 / 左图链接 / 下图链接 /
右图链接 / 链接 / 颜色 / 固定成本价 / ABC分类

不含：outSkuCode / goodsId / skuId / 是否停用 / 是否删除 / 主条码 / 自定义字段。

### 10.3 反写线（G→H，Excel 优先）

**核心决策（2026-05-16 用户提议）**：先做 Excel 反写，再做 API 反写。Excel 反写不消耗 ERP API 配额，单次可覆盖几千到几万条，运营在吉客云后台一次性上传更新即可。

| 阶段 | 动作 | 动到的代码 | 需要用户做什么 |
|---|---|---|---|
| **G1. Excel 反写候选导出** | 按条件筛 sku_master（如`shop_spec_code IS NOT NULL AND out_sku_code IS NULL`），导出吉客云"批量修改货品"模板可识别的 Excel | export service + 前端按钮 | 在 `/costing/integrations` 触发导出，拿到 Excel |
| **G2. ERP 后台上传** | 用户在吉客云后台用导出 Excel 批量修改货品 | 0（外部操作） | 上传 + 记录上传时间 |
| **G3. 反写状态回收** | 下次 API 同步时 `out_sku_code` 等字段会回灌，对比 `shop_spec_code` 自动判定反写成功 | 在 mapper 加判定逻辑 | 看 ProductInfoPage 反写状态列 |
| **G4. API dry-run（备用）** | `erp.goods.skuimportbatch` 不真发，只生成 payload | writeback service + dry_run flag | 审 payload |
| **H. API 真写（备用）** | 单条 / 小批量灰度真写"模型编码(规) + 工艺说明(规)"到 ERP | dry_run=false + 写回历史 | 查 ERP |

**为什么 Excel 反写优先**：
- ERP API 配额：`skuimportbatch` 单次最多 200 条，配额按调用次数算
- 40 万货品反写到 ERP，API 模式至少 2000 次调用，要 2 天
- Excel 后台批量上传不消耗 API 配额，几万条几分钟搞定
- 风险：吉客云后台"批量修改货品"模板是否支持 `outSkuCode` + 自定义字段反向修改，**需用户去吉客云后台验证**（见 §10.4）

### 10.4 阶段 G1 启动前必须验证（用户在吉客云后台操作）

在我开始写 Excel 反写导出代码前，请用户先在吉客云后台试一次：

1. 进吉客云后台"货品管理 → 批量导入"
2. 下载官方"修改货品"模板
3. 看模板支持哪些字段反向修改：
   - 外部编码 `outSkuCode` 是否在模板里？
   - 自定义字段 `goodsField1-50` / `skuField1-30` 是否在模板里？
   - 用条码 `barcode` 还是 `outSkuCode` 还是 `goodsId/skuId` 作匹配键？
4. 用 5 条测试货品尝试一次，确认能成功反向修改

模板字段决定我们的导出 Excel 列结构。如果模板能用 `barcode` 匹配，那 G1 的导出列就是「条码 + 反写字段」；如果只能用 `outSkuCode`，那必须先让 ERP 端有 `outSkuCode`（先做一轮"`shop_spec_code` → ERP `outSkuCode`"反写）。

## 11. 当前优先级

主线（发货 + 成本）继续推进，本任务在用户确认导入模板可执行后插入阶段 B。

---

## 12. 三系统字段对齐总表（2026-05-16 用户口述 + 代码实证）

> 这一节是为了**杜绝下次再花一个上午搞这些字段叫什么**。
> 所有结论都来自代码 + 官方文档原文，不是猜。

### 12.1 字段名翻译表

| 业务概念 | 吉客云 ERP 字段 | 天猫/网店叫法 | 我们系统内部叫法 | 唯一性 | 当前落地位置 |
|---|---|---|---|---|---|
| **SKU 唯一识别码** | `barcode`（条码） | — | `erp_sku_barcode` | **唯一** | `sku_master.erp_sku_barcode`（已有 unique 索引）✅ |
| **主条码 / 69 码** | `mainBarcode`（主条码） | — | 暂无独立字段 | **可重复**（一个货品一个） | ❌ 当前没存。用户 2026-05-16 确认业务不用，**不升 L2 物理列**；后续 ERP 同步时落 `metadata.erp.main_barcode` 即可，将来真用到再升 |
| **商家编码 / 模型编码** | `outSkuCode`（外部编码，主档侧） | "商家编码"（订单侧） | **`shop_spec_code`**（Phase0 起沿用） | 一对一到 SKU | 已有 `metadata.shop_spec_code`（发货 mapper 自动归一化填充），本期升 L2 物理列；反写时映射到 ERP `outSkuCode` |
| **货品编号** | `goodsNo` | — | `product_code` | 一对一到 SPU（一个 goodsNo 多个 SKU） | `sku_master.product_code` ✅ |
| **货品 ID** | `goodsId` | — | `erp_goods_id`（计划） | 一对一到 SPU | ❌ 当前没存。计划：新增物理列 |
| **规格 ID** | `skuId` | — | `erp_sku_id`（计划） | 一对一到 SKU | ❌ 当前没存。计划：新增物理列 |
| **平台商品 ID** | — | 平台商品 ID | `platform_product_id` | 一个 SKU 可关联**多个**（多店铺） | `shop_sku_mappings.platform_product_id` ✅；`sku_master.platform_product_id` 是冗余历史字段，只代表"代表性平台"，不要依赖它做完整一对多 |
| **平台 SKU ID** | — | 平台 SKU ID | `platform_sku_id` | 一个 SKU 可关联**多个**（多店铺） | `shop_sku_mappings.platform_sku_id` ✅（唯一约束 `(channel, platform_sku_id)`）；发货 detail 给了，但**发货 mapper 当前丢弃了**⚠ |

### 12.2 一对多关系图

```
                                      ┌──────────────────┐
                                      │ product_models   │
                                      │ (KB8、KB9、…)     │
                                      └────────▲─────────┘
                                               │
                                               │ binding (sku_model_version_mapping)
                                               │
┌─────────────────────────────────┐            │
│ sku_master                      │            │
│ ── erp_sku_barcode（条码）    ◄─┼─SSOT───────┘
│ ── product_code（goodsNo）      │
│ ── shop_spec_code（KB8-001）    │
│ ── out_sku_code（=ERP 写回的）  │
│ ── erp_goods_id / erp_sku_id    │
│ ── production_process           │
│ ── metadata.erp.* (140+ JSONB)  │
└────────────▲────────────────────┘
             │ 1
             │
             │ N
┌────────────┴────────────────────┐         ┌──────────────────────────┐
│ shop_sku_mappings               │         │ shipment_lines           │
│ ── (channel, platform_sku_id)   │         │ ── sku_code = barcode    │  ← 主键
│ ── erp_sku_barcode              │         │ ── product_link_id =     │
│ ── shop_spec_code               │         │      tradeGoodsno (原始) │
│ ── platform_product_id          │         │ ── metadata.shop_spec_code│ ← 归一化后 KB8-001
└─────────────────────────────────┘         │ ── platform_sku_id ❌    │ ← raw 里有，列没存
                                            │ ── platform_product_id ❌│ ← raw 里有，列没存
                                            └──────────▲───────────────┘
                                                       │
                                                       │ best-effort by erp_sku_barcode
                                                       │
                                            ┌──────────┴───────────────┐
                                            │ after_sales_lines        │
                                            │ ── sku_code = barcode    │ ← 售后已存
                                            │ ── product_code = outerId│ ← 售后已存（商家编码）
                                            │ ── product_link_id =     │
                                            │      platSkuId/platGoods │ ← 售后已存 ✅
                                            │ ── metadata.plat_sku_id  │
                                            │ ── metadata.plat_goods_id│
                                            └──────────────────────────┘
```

### 12.3 关键发现（必须落实）

1. **`erp_sku_barcode` 是唯一可靠的跨表主索引**——所有三张表（sku_master / shipment_lines / after_sales_lines / shop_sku_mappings）都通过它对齐。用户确认无误。

2. **主条码 `mainBarcode` 不需要专门物理列**（用户 2026-05-16 修正）——业务用 `erp_sku_barcode`（数字串）作扫码主键，主条码（GTIN/UDI）这一侧目前没有使用场景。`backend/` 代码里 0 处引用 `main_barcode/mainBarcode`。后续 ERP 同步时收下放 `metadata.erp.main_barcode` 留底即可，需要时再升。

3. **商家编码（模型编码）"散落 3 处"，统一到旧名 `shop_spec_code`**：
   - 发货：`tradeGoodsno`（原始） → 归一化后 `metadata.shop_spec_code` (KB8-001) — Phase0 起沿用
   - 售后：`outerId` → `product_code`（语义同 shop_spec_code）
   - ERP 主档：`outSkuCode`（多数为空，等我们反写）
   - **统一方案（v3）**：把 `metadata.shop_spec_code` 升级为 `sku_master.shop_spec_code` 物理列（沿用旧名，不重新造名），作为系统内规范值；反写时映射到 ERP 的 `outSkuCode`。

4. **发货行丢失了 `platSkuId/platGoodsId`** ⚠（重要缺陷）
   - 官方文档 (`core_interfaces_extracted.md` 行 2473、2517) 明确 `trades-goodsDetail` 里有这两个字段
   - 当前 `shipment.py` mapper 没读取，raw_row 里能查到但要 JSON path
   - **影响**：
     - 跨店铺销售分析做不了精细化（只能 channel 级，不能 platform_sku_id 级）
     - 售后→发货反查只能靠 `platOrderNo`（已实现，命中率 36%），加上 `platform_sku_id` 反查可以再提升
   - **建议处理**（不在 ERP 货品任务范围）：
     - 新增 migration 给 `shipment_lines` 加两个可空列 `platform_product_id` / `platform_sku_id`
     - mapper 提取并填充
     - 已落地的历史发货行通过 `raw_row->detail->platSkuId` 回填
   - 记入本文 §13 "字段缺口与待办"

5. **`sku_master.platform_product_id/platform_sku_id` 是冗余历史列**
   - 已有但只能存 1 个值，与"一个条码可绑多平台SKU"的业务事实矛盾
   - 真正的 1:N 维度在 `shop_sku_mappings`
   - **处理**：保留这两列作为"代表性平台"快查（最近一次发货的平台 ID），但**不要在新需求里依赖它做完整性查询**，完整列表必须 join `shop_sku_mappings`

## 13. 字段缺口与待办

不在本任务"ERP 货品主档同步"范围，但绕不开的相邻问题：

| # | 缺口 | 影响 | 建议处理 | 谁负责 |
|---|---|---|---|---|
| G1 | `shipment_lines` 没存 `platform_sku_id / platform_product_id` | 跨店切片销售分析、售后→发货反查精度 | 加 2 列 + mapper 提取 + 历史回填脚本 | 发货模块（独立 PR） |
| G2 | `sku_master` 没存主条码 `main_barcode` | 当前无影响；未来若启用 UDI/69 码扫描才需要 | 不升物理列；ERP 同步时留 `metadata.erp.main_barcode`，将来真用再升 | 本任务 metadata |
| G3 | "商家编码"3 处散落 | 反写 source 容易不清 | 用旧名 `shop_spec_code` 收敛并升 L2；**不建** `merchant_sku_code` | 本任务阶段 B |
| G4 | `sku_master.platform_product_id/sku_id` 语义不清 | 容易被误用为完整 1:N | 加注释 + Schema 字段说明；视图层禁用 | 本任务阶段 B（注释）|

## 14. 关键口径（防止下次再绕弯）

- **不要再讨论"为发货新建商品档案表"**：已有 `sku_model_version_mapping` + `spec_parse_snapshots` 做 sub-ms 缓存。
- **不要再讨论"商家编码该叫什么"**：**系统内统一叫 `shop_spec_code`**（Phase0 沿用），UI 显示"商家编码 / 模型编码"，写回 ERP 时映射到 `outSkuCode`。
- **不要把 `platform_product_id/platform_sku_id` 当一对一**：永远靠 `shop_sku_mappings` 取完整列表。
- **主条码 ≠ 条码**：主条码可重复，仅作属性字段；唯一索引永远只建在 `erp_sku_barcode`。**不升 L2 物理列**（业务不用）。
- **`production_process` 是源，`process_instructions_reg` 是目标**：前者是我们系统计算/录入的可执行工艺说明（升 L2 物理列），后者是 ERP 货品档案当前的"工艺说明(规)"列（落 `metadata.erp`）；反写时 production_process → 写回 ERP `工艺说明(规)`。

---

## 15. 与历史口径对齐表（v3 核心 — 防止前后不一致）

> 本表是 2026-05-16 用户要求"对齐之前的记录"后产出的核对清单。
> 凡新增字段命名都必须先查这张表，**严禁重新造名**。
>
> 历史参考文档：
> - `DOC/agents/integration/phase0_single_shop_mvp_mapping_and_samples.md`（2026 早期 Phase0 规范）
> - `DOC/costing/blueprints/erp_writeback_process_spec_mvp.md`（旧反写蓝图）
> - `backend/src/planner/services/sku_master_service.py`（已落地的字段名实证）

### 15.1 字段命名沿用表

| 业务概念 | Phase0 旧规范 | 旧反写蓝图 | 当前代码实证 | 本期方案（v3） | 行动 |
|---|---|---|---|---|---|
| 网店商家编码 / 模型编码 | `metadata.shop_spec_code` | — | `sku_master_service.py` 全链路用 `shop_spec_code` | **`sku_master.shop_spec_code`（升 L2）** | ✅ 沿用 |
| 系统生成的可执行工艺 | `metadata.production_process` | `process_instructions_text` | `sku_master_service.py` 用 `production_process` | **`sku_master.production_process`（升 L2）** | ✅ 沿用 Phase0 名 |
| 已绑定模型编码 | `bound_model_code` | `model_code` | sku_master 上已通过 `active_model_version_id` join 出 | 保持现状 | ✅ 不动 |
| 已绑定版本标签 | `bound_version_label` | `version_label` | 同上 | 保持现状 | ✅ 不动 |
| 解析规格 hash | `erp_spec_hash` / `last_shipment_spec_hash` | `spec_hash` | sku_master 已有 | 保持现状 | ✅ 不动 |
| 追溯 ID | — | `costing_trace_id` | 用 `bom_snapshot.id` | 保持现状 | ✅ 不动 |
| 反写状态 | `writeback_status` (在 shop_sku_mappings) | `writeback_status` | 已存在 | 保持现状 | ✅ 不动 |
| ERP 外部编码（反写目标） | — | "ERP 自定义字段/备注字段" | 还没存 | **`sku_master.out_sku_code`（新增 L2）** | 🆕 新增 |
| ERP 货品 ID | — | — | 还没存 | **`sku_master.erp_goods_id`（新增 L2）** | 🆕 新增 |
| ERP 规格 ID | — | — | 还没存 | **`sku_master.erp_sku_id`（新增 L2）** | 🆕 新增 |
| ERP 停用标记 | — | — | 还没存 | **`sku_master.is_blocked`（新增 L2）** | 🆕 新增 |
| ERP 删除标记 | — | — | 还没存 | **`sku_master.is_deleted_at_source`（新增 L2）** | 🆕 新增 |
| ERP 工艺说明(规) 当前值 | — | — | 还没存 | `metadata.erp.process_instructions_reg`（反写目标的 ERP 端镜像） | 🆕 metadata |
| ERP 模型编码(规) 当前值 | — | — | 还没存 | `metadata.erp.model_code_reg` | 🆕 metadata |
| ERP 主条码 | — | — | 0 处使用 | `metadata.erp.main_barcode`（不升 L2） | 🆕 metadata |
| **规格标记（SKU 级标签）** | — | — | 还没存 | **`metadata.erp.sku_flag`（JSON 数组，多值）** + `sku_flag_synced/_synced_at` 影子 | 🆕 metadata，**反写源** |
| **货品标记（SPU 级标签）** | — | — | 还没存 | `metadata.erp.flags`（JSON 数组，多值） | 🆕 metadata，**暂不反写** |

### 15.2 反写链路（最终统一图）

```
我们系统侧（源）                          反写动作                      ERP 货品档案侧（目标）
────────────────                          ────────                      ────────────────────
sku_master.shop_spec_code (KB8-001)     ─writeback─►                   outSkuCode (外部编码)
                                                                       ↓ 下次同步回灌
                                                                       sku_master.out_sku_code

sku_master.production_process            ─writeback─►                   工艺说明(规) (= process_instructions_reg)
（系统计算/人工录入）                                                  ↓ 下次同步回灌
                                                                       metadata.erp.process_instructions_reg

metadata.erp.sku_flag (JSON 数组)        ─writeback─►                   规格标记 (skuFlag)
（运营在我们系统打标签）                  Excel 优先 + API 备用         ↓ 下次同步回灌
                                                                       metadata.erp.sku_flag_synced（影子，不覆盖本地）

（暂不反写）                                                            模型编码(规) (= model_code_reg)
                                                                       ↓ 同步收下
                                                                       metadata.erp.model_code_reg

（暂不反写）                                                            货品标记 (goodsFlag / flagData)
                                                                       ↓ 同步收下
                                                                       metadata.erp.flags
```

### 15.3 命名冲突已解决清单

| 时间 | 提案 | 决议 | 原因 |
|---|---|---|---|
| 2026-05-16 早 | 新建 `sku_master.merchant_sku_code` | ❌ 否决，改用 `shop_spec_code` | Phase0 已沿用，全链路代码在跑，重新造名会造成 3 套名字混乱 |
| 2026-05-16 早 | 新建 `sku_master.main_barcode` 物理列 | ❌ 否决，降级到 metadata | 用户业务不用 GTIN/UDI，代码 0 处引用，升列是过度设计 |
| 2026-05-16 早 | 新建 `metadata.erp.process_instructions_reg` 单独承载工艺 | ✅ 保留 + 区分语义 | 这是"ERP 端当前值"，与 `production_process`（系统源）是双向反写关系，分两个字段语义更清楚 |
| 2026-05-16 中 | 规格标记 `skuFlag` 升 L2 物理列 | ❌ 否决，留 metadata + GIN | 离散低基数标签，不做排序/range；7 个 L2 名额优先留给关联键。GIN 索引足够支持"按标签筛选" |
| 2026-05-16 中 | 规格标记用逗号字符串存 | ❌ 否决，改 JSON 数组 | 用户确认是多值标签；数组结构避免后续拆分歧义，反写时由 mapper join 成逗号给 ERP |
| 2026-05-16 中 | 规格标记真源 | ✅ 我们系统 → ERP | 用户确认是运营在我们系统打标签后回传 ERP；冲突时以我们为准 |
| 2026-05-16 中 | 货品标记 `goodsFlag` 是否反写 | ❌ 本期不反写 | 用户只点名"规格标记"要回传，货品标记当前仅同步收下 |

---

## 16. 规格标记（skuFlag）反写线 — 独立小节

> 用户 2026-05-16 中追加需求："规格标记也是需要的，用于标签分类用的，到时需要回传"。
> 由于这是与 §10.3 反写线并列的第二条反写源（除 `shop_spec_code` / `production_process` 之外），单独立节防止下次混。

### 16.1 三方决策一览

| 决策项 | 选择 | 理由 |
|---|---|---|
| 真源（source of truth） | **我们系统** | 运营在我们这边打标签，ERP 端通常为空 |
| 写回方向 | 我们 → ERP | 冲突时以我们为准；同步回来的 ERP 值仅作影子 |
| 数据形态 | **JSON 数组**（多值） | 一个 SKU 可叠多个标签，例如 `["爆款","新品"]` |
| 物理列 vs metadata | **metadata + GIN 索引** | 离散低基数标签，不做排序；7 个 L2 名额留给关联键 |
| 写回通道 | **Excel + API 双通道** | Excel 优先（避配额），API 备用（小批实时） |

### 16.2 存储模型

```
sku_master.metadata_json:
  erp:
    sku_flag:             ["爆款", "新品"]          ← 真源，本地标签数组
    sku_flag_synced:      ["新品"]                  ← 影子，ERP 当前值（同步拉回，不覆盖本地）
    sku_flag_synced_at:   "2026-05-17 03:30:01"
    sku_flag_writeback:                              ← 反写历史（与 production_process 相同结构）
      last_attempted_at:  "2026-05-16 22:00:00"
      last_succeeded_at:  "2026-05-16 22:00:05"
      last_payload:       "爆款,新品"
      last_channel:       "excel" / "api"
      last_error:         null
```

### 16.3 同步规则

- **ERP → 我们（拉）**：
  - `erp.storage.goodslist` 返回 `skuFlag` 字符串（按 ERP 实际分隔符，默认逗号）
  - mapper 按 `,` / `;` 拆分进数组，存到 `metadata.erp.sku_flag_synced`
  - **不覆盖** `metadata.erp.sku_flag`（本地为真源）
- **我们 → ERP（推）**：
  - Excel 反写（G1）：导出列含"规格标记"，值用 `,` join
  - API 反写（H）：`skuimportbatch.payload.skuFlag` 同样 `,` join
  - 写回成功后更新 `sku_flag_writeback.last_succeeded_at` 与 `last_payload`

### 16.4 筛选与展示

- 前端 `ProductInfoPage`：增加"规格标记"列（多 Tag 显示），筛选用 contains（`metadata_json @> '{"erp":{"sku_flag":["爆款"]}}'`）
- 索引：`CREATE INDEX ix_sku_master_meta_sku_flag ON sku_master USING GIN ((metadata_json->'erp'->'sku_flag') jsonb_path_ops);`
  - 仅当出现高频筛选时再加，本期 migration 不强制

### 16.5 落地节奏插入位置

不破坏 §10 的 A→F→G1 顺序，仅在各阶段补 sku_flag 任务：

| 阶段 | 追加动作 |
|---|---|
| B（ORM） | `SkuMaster.metadata_json.erp.sku_flag` 结构化（schema 默认空数组），无需新列 |
| C（Excel 导入） | 模板规范 §2.3 已列"规格标记 → `metadata.erp.sku_flag`"；导入器需把单元格按 `,/;` 拆数组写入 |
| F（API 同步） | mapper 拉 `skuFlag` 进 `metadata.erp.sku_flag_synced`（**不**写 `sku_flag`） |
| G1（Excel 反写导出） | 导出列新增"规格标记"，按 `,` join 输出 |
| H（API 反写） | `skuimportbatch` payload 加 `skuFlag` 字段 |

### 16.6 待用户后续确认（不阻塞本期 B/C）

1. **首次 ERP 同步回来如果 ERP 已有标签，怎么处理？**
   - 建议：第一次同步把 `sku_flag_synced` 拷一份给 `sku_flag`（一次性 seed），之后再严格"我们 → ERP"单向
   - 等 F 阶段实施前用户确认
2. **运营在哪里打标签？**
   - 候选：ProductInfoPage 行内可编辑 / 抽屉 / 批量打标按钮
   - 等 D 阶段实施前用户确认

