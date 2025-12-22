# SKU 绑定 → 规格解析 → 动态 BOM → 发货/扣库/核算对账（ERP 方案与计划 v0.1）

> 本文只给**方案与计划**（先定口径/数据结构/闭环边界），暂不执行落地开发。  
> 输入来源：  
> - `DOC/基础表单/SKU绑定与BOM生成业务逻辑说明文档.md`  
> - `DOC/index/extracted/shipment_xlsx_extracted_20251222T000000+0800.md`（发货单样例表头提炼）

## 1. 现状评估（你原方案哪里对、哪里需要“ERP化”）

- **对的**（继续坚持）
  - **SKU 主键**：以“货品条码”作为 SKU 唯一键，SKU→标准模型（或标准版本）一对一绑定。
  - **spec_text 是动态输入**：以“交易规格”做解析输入，提取 tokens + 尺寸派生量（宽/高/面积/周长等）。
  - **BOM 必须落快照**：库存扣减、成本核算、审计追溯都以“当次生成的 BOM 快照”为准，不受后续规则变更影响。
  - **先简单后复杂**：MVP 只做 `replace_self + 同单位 1→1` 的变体替换，避免一次做成规则引擎地狱。

- **需要优化**（从“业务说明”升级为“可运营的 ERP 流程”）
  1) **发货单导入先标准化**：样例 xlsx 数据行存在 Excel 日期序列值、且部分行疑似列位移（例如“交易规格”出现到 B 列等）。ERP 化必须先做：导入→标准化→去重→再计算。
  2) **绑定粒度建议升级为“SKU→标准版本（published）”**：不是绑定到“模型”抽象概念，而是绑定到“某个已发布标准版本”，这样扣库快照可追溯“当时用的是哪个版本”。
  3) **规格解析要可控、可回放**：解析结果要保存 hash/版本与 trace（否则规格变更审批无法落地）。
  4) **异常必须有队列与归因**：未绑定 SKU、解析失败、数量为0、单位不一致、命中多条规则冲突等，都要进入“待处理队列”，否则系统最终会变成黑箱。

## 2. 数据口径（从发货单到“可计算订单行”）

### 2.1 发货单关键字段（来自提炼件）

样例表头（节选）：付款时间、发货单号、状态、完成时间、物流公司、物流单号、数量合计、销售渠道、实付金额、货品编号、货品名称、数量、货品条码、金额、单价（以及可能存在“交易规格”等列在后续列中）。

> 结论：发货单里我们真正用于“算 BOM/扣库/核算”的最小字段集是：
- **shipment_no**：发货单号（建议作为订单号/出库单号的上游键）
- **completed_at**：完成时间（建议作为核算归属时间口径）
- **channel**：销售渠道（用于店铺维度统计）
- **sku_code**：货品条码（SKU 主键）
- **spec_text**：交易规格（解析输入）
- **qty**：数量（BOM 乘数）
- **revenue_amount**：金额（用于收入侧核算）

### 2.2 导入标准化（必须先做，否则对账会漂）

建议将导入拆两层：
- **raw_shipment_rows（原始层）**：保存原始整行（包含原始列名、原始值字符串），只做“可追溯”，不做业务计算。
- **shipment_lines（标准化层）**：把 raw 映射成稳定字段：
  - 时间：支持 Excel serial date 与字符串日期两种格式
  - 关键列位移/缺失：用“表头映射 + 弱校验”容错，但落库前必须记录 `normalize_warnings`

去重建议：
- `shipment_line_key = (shipment_no, sku_code, spec_text, qty, revenue_amount)` + 行序号/原始行号（必要时）

## 3. 业务对象与“单一真相”

### 3.1 四个单一真相（ERP必须明确）

- **标准版本（published）**：生产可用的“基准清单 + 工序 + 变体规则 overlay 的宿主”。
- **SKU→标准版本绑定**：决定“一个 sku_code 走哪套标准版本”。
- **解析结果快照（spec snapshot）**：spec_text → tokens + dimensions（带 hash、版本、trace）。
- **BOM 快照（inventory snapshot）**：本次出库/核算采用的最终物料需求清单（带 trace、绑定版本号、解析结果）。

### 3.2 推荐的落库最小字段（MVP）

- `sku_model_version_mapping`
  - `sku_code`
  - `model_version_id`（必须 published）
  - `enabled`
  - `notes`

- `spec_parse_snapshot`
  - `sku_code`
  - `spec_text`
  - `spec_hash`（如 sha1(spec_text)）
  - `tokens_json`
  - `dimensions_json`（width/height/area/perimeter 等）
  - `parser_version`
  - `created_at`

- `bom_snapshot`
  - `shipment_no`（或外部订单号）
  - `sku_code`
  - `model_version_id`
  - `spec_hash`
  - `qty`
  - `final_lines_json`（物料行：material_ref_id/code/name/uom/computed_quantity…）
  - `trace_json`（命中规则、替换链路、计算过程摘要）
  - `generated_at`

> 注意：BOM 快照建议存“可读字段”（code/name/uom）以减少主数据变更导致的历史不可读。

## 4. 端到端流程（闭环）

### 4.1 线上主链路（每日批处理/实时皆可）

1) 导入发货单 → 标准化为 `shipment_lines`  
2) 对每个 `shipment_line`：
   - 用 `sku_code` 查询 SKU→版本绑定（必须命中 published）
   - 对 `spec_text` 做解析（生成 `spec_parse_snapshot`，或命中已有 hash 复用）
   - 调用 BOM 生成（基准清单 + 行级变体 overlay），得到 `final_lines`
   - `final_lines` × `qty` 形成“扣库需求”
   - 落 `bom_snapshot`（带 trace，可审计/可回放）
3) 统计报表：按 completed_at、channel、货品编号、sku_code 聚合收入/成本/毛利

### 4.2 异常队列（ERP 强烈建议一起做，至少能落原因）

将以下情况写入 `known_issues/queue`（或一张表）：
- SKU 未绑定
- spec_text 解析失败/缺少尺寸
- 命中规则冲突（同一 base_line_id 命中多条且 stop_on_hit=false）
- 单位不一致（replace_self 同单位校验失败）
- computed_quantity = 0（需兜底继承/提示重录）

## 5. 对你原文的“专业优化点”（不改变方向，只加护栏）

- **绑定建议**：从“SKU→模型ID”改为 **SKU→已发布标准版本ID**（模型会有多个版本；ERP 扣库必须可回放到具体版本）。
- **spec 变更审批落地**：不是比对“文本变化”，而是比对 **spec_hash + tokens + dimensions** 的变化；变化触发审批/重新预演。
- **Token 词典**：建议区分三类 token：
  - 结构化维度 token（SIZE_S/M/L 等）
  - 工艺/材质 token（FRAME_024 / MATERIAL_FLEECE）
  - 渠道/系列 token（可选，用于默认绑定建议）
- **成本口径建议**（先占位，后续迭代）
  - 收入：发货单“金额”
  - 成本：BOM 快照中的物料成本（按当期价格策略：标准价/移动平均/批次成本）
  - 归属期：按“完成时间”（你文档建议 B，符合权责发生）

## 6. 分阶段计划（建议 3 个闭环迭代）

### 阶段 A（MVP，1 个闭环）
目标：从 API 角度打通 “sku_code + spec_text + qty → bom_snapshot”  
- 后端：新增/固化 `sku-bom/generate` 接口（或在现有 bom/generate 上封装），并补最小 pytest

### 阶段 B（对账可用，1 个闭环）
目标：导入发货单 → 自动生成 bom_snapshot  
- 后端：新增“发货单导入/标准化”作业 + 异常队列

### 阶段 C（运营可持续，1 个闭环）
目标：绑定治理 + 变更审批 + 解析回放  
- 前端：SKU 待绑定队列、绑定/改绑、解析预演、审批记录

## 7. 本文验收（文档闭环）

`grep -nF \"SKU 绑定 → 规格解析 → 动态 BOM → 发货/扣库/核算对账\" DOC/costing/blueprints/sku_binding_bom_shipment_plan.md`


