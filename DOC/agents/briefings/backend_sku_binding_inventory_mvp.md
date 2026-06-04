# Backend 闭环任务单：SKU 绑定 + 规格解析尺寸/条件 + 生成库存扣料清单（BOM 快照）MVP

> 角色：@Backend Agent  
> 背景：产品模型（standard）+ 行级变体（overlay）+ spec/parse + bom/generate 已打通并已上线；现在要闭合“订单入口=SKU”的主链路。  
> 目标：给运营/实施一个最小可用的后端链路：输入 sku_code + spec_text → 找到绑定的标准版本 → 解析规格尺寸/tokens → 套用变体 → 输出最终 BOM（用于库存扣料/出库/核算的快照）。

## 1) 本轮范围（必须很小）

只做一个可验收闭环（不做 UI 工作台、不做智能推荐、不做跨系统对接）：

1. SKU→标准版本绑定（复用已有表/接口，若已有则只补齐缺口）
2. “按 SKU 生成最终 BOM”一键接口（把调用方从“传 version_id”升级为“传 sku_code”）
3. 最小单测（pytest）覆盖：绑定→生成→trace 回放关键字段

## 2) 完成标准

- 能用 API 完成一次：
  - 绑定：sku_code → model_version_id（必须是已发布 standard 版本）
  - 生成：传入 sku_code + spec_text（可选 quantity） → 返回 final_material_lines + trace
- 输出的 final_material_lines 可直接作为“扣库/出库/核算快照”的来源（至少包含 material_ref_id/material_code/material_name/unit_of_measure/computed_quantity）
- `pytest backend/tests/planner/test_sku_binding_inventory_mvp.py -q` 通过

## 3) API 契约（建议，尽量复用已有）

### 3.1 绑定（如已存在则不重复造轮子）

优先复用：
- `POST /api/planner/sku-model-version-mapping`
  - `{ sku_code, model_version_id, metadata_json? }`

约束（MVP 强校验）：
- 仅允许绑定到 `standard` 且 `published` 的版本

### 3.2 生成库存扣料清单（新增闭环接口）

- `POST /api/planner/sku-bom/generate`
- Request：
  - `{ "sku_code": string, "spec_text": string, "quantity"?: number }`
- 处理流程：
  1) 查 sku_code 绑定到的 `model_version_id`（若未绑定：返回 400/404，并给出明确提示）
  2) 调用 `spec/parse` 解析 tokens/尺寸派生量
  3) 调用 `bom/generate`（或复用内部 service）生成 `final_material_lines`
  4) 返回 `trace`：至少包含 `bound_version_id`、`parsed.tokens`、命中规则摘要（variant ids/actions）

### 3.3 可选（若已有 sku-preview 且已做尺寸解析，可复用）

如果仓库已有 `POST /api/planner/sku-preview`（按 SKU 解析并预览），允许将其内部逻辑下沉复用；但本轮验收以 `sku-bom/generate` 为准。

## 4) 单测建议（最小即可）

文件：`backend/tests/planner/test_sku_binding_inventory_mvp.py`

- 准备：
  - 创建一个 published standard version（可复用现有测试工厂/fixtures）
  - 写入 sku binding
  - 构造一个 spec_text（含尺寸 + token）
- 断言：
  - `sku-bom/generate` 返回 200
  - trace 包含 `bound_version_id`、tokens
  - final_material_lines 至少 1 行且 computed_quantity > 0（或符合预期）

## 5) 验收命令（只给 1 条）

`pytest backend/tests/planner/test_sku_binding_inventory_mvp.py -q`


